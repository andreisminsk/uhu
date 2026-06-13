"""Browser automation tool using Playwright with stealth support.

Provides a clean browser context per session for web browsing, scraping,
and interaction. Uses playwright-stealth for bot detection avoidance.
"""

import atexit
import os

from ..constants import MAX_OBSERVATION_CHARS

_BROWSER_DEPS_ERROR = (
    "Browser dependencies not installed. "
    "Run: pip install playwright playwright-stealth && playwright install chromium"
)

# Module-level browser state (singleton per process)
_browser = None
_context = None
_page = None
_playwright_instance = None


def _apply_stealth(page, config):
    """Apply playwright-stealth patches if available and enabled."""
    if not config.get("stealth", True):
        return
    try:
        from playwright_stealth import stealth_sync
        stealth_sync(page)
    except ImportError:
        pass  # stealth not available, continue without

    # Extra stealth: override navigator.webdriver and other fingerprints
    _apply_extra_stealth(page)


def _apply_extra_stealth(page):
    """Apply additional stealth patches beyond playwright-stealth."""
    try:
        page.add_init_script("""
            // Override navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            // Fake plugins array (non-empty looks more real)
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            // Fake languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            // Remove 'HeadlessChrome' from UA
            const originalUA = navigator.userAgent;
            Object.defineProperty(navigator, 'userAgent', {
                get: () => originalUA.replace('HeadlessChrome/', 'Chrome/'),
            });
            // Override chrome runtime
            window.chrome = { runtime: {} };
            // Override permissions query
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters);
            // Fake connection type
            Object.defineProperty(navigator, 'connection', {
                get: () => ({ effectiveType: '4g', rtt: 50, downlink: 10 }),
            });
        """)
    except Exception:
        pass  # page may already be closed


def _setup_resource_blocking(page, blocked_types):
    """Block specified resource types from loading via route interception."""
    if not blocked_types:
        return

    def handle_route(route):
        if route.request.resource_type in blocked_types:
            route.abort()
        else:
            route.continue_()

    try:
        page.route("**/*", handle_route)
    except Exception:
        pass  # route setup can fail on certain pages


def _close_browser():
    """Close browser, context, and page. Clean up all resources."""
    global _browser, _context, _page, _playwright_instance
    for obj in [_page, _context]:
        try:
            if obj:
                obj.close()
        except Exception:
            pass
    try:
        if _browser:
            _browser.close()
    except Exception:
        pass
    try:
        if _playwright_instance:
            _playwright_instance.stop()
    except Exception:
        pass
    _page = None
    _context = None
    _browser = None
    _playwright_instance = None


atexit.register(_close_browser)


def _ensure_browser(config=None):
    """Lazy-initialize browser, context, and page.

    Returns (page, error_string). If error_string is set, page is None.
    Reuses existing browser if still connected; recovers from crashes.
    """
    global _browser, _context, _page, _playwright_instance

    # Fast path: existing page is still alive
    if _page and not _page.is_closed() and _browser and _browser.is_connected():
        return _page, None

    # Browser alive but page closed — create new page in existing context
    if _browser and _browser.is_connected() and _context:
        try:
            _page = _context.new_page()
            _apply_stealth(_page, config or {})
            blocked = (config or {}).get("block_resources", [])
            _setup_resource_blocking(_page, blocked)
            return _page, None
        except Exception:
            _close_browser()

    # Need fresh start
    _close_browser()
    config = config or {}
    headless = config.get("headless", True)
    slow_mo = config.get("slow_mo", 50)
    viewport = config.get("viewport", {"width": 1920, "height": 1080})
    user_agent = config.get("user_agent")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, _BROWSER_DEPS_ERROR

    try:
        _playwright_instance = sync_playwright().start()
    except Exception as e:
        return None, f"[Error starting Playwright: {e}. {_BROWSER_DEPS_ERROR}]"

    try:
        _browser = _playwright_instance.chromium.launch(
            headless=headless, slow_mo=slow_mo
        )
    except Exception as e:
        err_msg = str(e)
        if "Executable doesn't exist" in err_msg or "playwright install" in err_msg.lower():
            return None, (
                "Browser binaries not installed. "
                "Run: playwright install chromium"
            )
        _close_browser()
        return None, f"[Error launching browser: {e}]"

    context_kwargs = {
        "viewport": viewport,
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "extra_http_headers": {
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-CH-UA": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        },
    }
    if user_agent:
        context_kwargs["user_agent"] = user_agent

    try:
        _context = _browser.new_context(**context_kwargs)
    except Exception as e:
        _close_browser()
        return None, f"[Error creating browser context: {e}]"

    try:
        _page = _context.new_page()
    except Exception as e:
        _close_browser()
        return None, f"[Error creating page: {e}]"

    _apply_stealth(_page, config)
    blocked = config.get("block_resources", [])
    _setup_resource_blocking(_page, blocked)

    return _page, None


_SYSTEM_PROMPT = (
    "## browser\n"
    "Automate web browsing using Playwright with stealth support.\n"
    "Uses a clean browser context per session (no cookies or history from previous sessions).\n"
    "\n"
    "Actions and parameters:\n"
    "\n"
    "### navigate\n"
    "Go to a URL.\n"
    '```json\n'
    '{"action": "navigate", "url": "https://example.com", "wait_until": "domcontentloaded", "timeout": 30}\n'
    '"""\n'
    "Required: url. Optional: wait_until (load|domcontentloaded|networkidle, default: domcontentloaded), timeout (default: 30).\n"
    "\n"
    "### extract_text\n"
    "Get cleaned text content from the page or a specific element.\n"
    '```json\n'
    '{"action": "extract_text", "selector": "body", "max_length": 5000}\n'
    '"""\n'
    "Optional: selector (CSS, default: body), max_length (default: 5000).\n"
    "\n"
    "### extract_links\n"
    "Get all links on the page.\n"
    '```json\n'
    '{"action": "extract_links", "selector": "a", "max_links": 50}\n'
    '"""\n'
    "Optional: selector (CSS, default: 'a'), max_links (default: 50).\n"
    "\n"
    "### screenshot\n"
    "Capture a screenshot of the page or element. Saves to workdir and returns the file path.\n"
    '```json\n'
    '{"action": "screenshot", "selector": null, "full_page": false, "path": "screenshot.png"}\n'
    '"""\n'
    "Optional: selector (CSS, null=full page), full_page (default: false), path (default: screenshot.png).\n"
    "After screenshot, use image-analysis tool to analyze the image.\n"
    "\n"
    "### pdf\n"
    "Save the current page as a PDF file.\n"
    '```json\n'
    '{"action": "pdf", "path": "page.pdf", "format": "A4"}\n'
    '"""\n'
    "Optional: path (default: page.pdf), format (default: A4).\n"
    "Note: PDF export only works in headless mode.\n"
    "\n"
    "### click\n"
    "Click an element.\n"
    '```json\n'
    '{"action": "click", "selector": "#button", "text": null, "timeout": 10}\n'
    '"""\n'
    "Provide either selector or text. Optional: timeout (default: 10).\n"
    "\n"
    "### fill\n"
    "Type text into a form field.\n"
    '```json\n'
    '{"action": "fill", "selector": "#search", "value": "search terms", "press_enter": false}\n'
    '"""\n'
    "Required: selector, value. Optional: press_enter (default: false).\n"
    "\n"
    "### wait_for\n"
    "Wait for an element to appear on the page.\n"
    '```json\n'
    '{"action": "wait_for", "selector": ".results", "timeout": 10}\n'
    '"""\n'
    "Required: selector. Optional: timeout (default: 10).\n"
    "\n"
    "### scroll\n"
    "Scroll the page.\n"
    '```json\n'
    '{"action": "scroll", "direction": "down", "amount": 3, "pause": 500}\n'
    '"""\n'
    "Optional: direction (up|down, default: down), amount (viewport heights, default: 3), pause (ms between scrolls, default: 500).\n"
    "\n"
    "### go_back\n"
    "Navigate back in browser history.\n"
    '```json\n'
    '{"action": "go_back"}\n'
    '"""\n'
    "\n"
    "### evaluate\n"
    "Run JavaScript in the browser and return the result.\n"
    '```json\n'
    '{"action": "evaluate", "script": "document.title"}\n'
    '"""\n'
    "Required: script.\n"
    "\n"
    "### close\n"
    "Close the browser and free resources.\n"
    '```json\n'
    '{"action": "close"}\n'
    '"""\n'
    "Use this when done browsing to free resources.\n"
)


class BrowserTool:
    """Browser automation using Playwright with stealth support."""

    name = "browser"
    description = "Browser automation using Playwright with stealth support"
    system_prompt = _SYSTEM_PROMPT
    parameters = {
        "action": {
            "type": "string",
            "description": (
                "Action to perform: navigate, extract_text, extract_links, "
                "screenshot, pdf, click, fill, wait_for, scroll, go_back, evaluate, close"
            ),
            "required": True,
        },
        "url": {
            "type": "string",
            "description": "URL to navigate to (for navigate action)",
            "required": False,
        },
        "selector": {
            "type": "string",
            "description": "CSS selector for element targeting",
            "required": False,
        },
        "text": {
            "type": "string",
            "description": "Visible text to click on (alternative to selector)",
            "required": False,
        },
        "value": {
            "type": "string",
            "description": "Text to type into a form field (for fill action)",
            "required": False,
        },
        "path": {
            "type": "string",
            "description": "File path for screenshot/pdf output",
            "required": False,
        },
        "full_page": {
            "type": "boolean",
            "description": "Capture full scrollable page (screenshot action, default: false)",
            "required": False,
        },
        "wait_until": {
            "type": "string",
            "description": "Navigation wait condition: load|domcontentloaded|networkidle (default: domcontentloaded)",
            "required": False,
        },
        "timeout": {
            "type": "number",
            "description": "Timeout in seconds (default: varies by action)",
            "required": False,
        },
        "max_length": {
            "type": "number",
            "description": "Maximum text length to return (default: 5000)",
            "required": False,
        },
        "max_links": {
            "type": "number",
            "description": "Maximum number of links to return (default: 50)",
            "required": False,
        },
        "direction": {
            "type": "string",
            "description": "Scroll direction: up or down (default: down)",
            "required": False,
        },
        "amount": {
            "type": "number",
            "description": "Number of viewport heights to scroll (default: 3)",
            "required": False,
        },
        "pause": {
            "type": "number",
            "description": "Milliseconds to pause between scrolls (default: 500)",
            "required": False,
        },
        "press_enter": {
            "type": "boolean",
            "description": "Press Enter after filling text (default: false)",
            "required": False,
        },
        "script": {
            "type": "string",
            "description": "JavaScript code to evaluate",
            "required": False,
        },
        "format": {
            "type": "string",
            "description": "PDF format: A4, Letter, etc. (default: A4)",
            "required": False,
        },
    }

    def execute(self, params, workdir=None):
        from ._config import get_config
        config = get_config()
        browser_config = config.get("tools", {}).get("browser", {})

        action = params.get("action", "").lower()
        if not action:
            return "[Error: 'action' parameter is required]"

        if action == "close":
            _close_browser()
            return "[Browser closed]"

        page, error = _ensure_browser(browser_config)
        if error:
            return error

        try:
            if action == "navigate":
                return self._navigate(page, params, browser_config)
            elif action == "extract_text":
                return self._extract_text(page, params)
            elif action == "extract_links":
                return self._extract_links(page, params)
            elif action == "screenshot":
                return self._screenshot(page, params, workdir)
            elif action == "pdf":
                return self._pdf(page, params, workdir, browser_config)
            elif action == "click":
                return self._click(page, params)
            elif action == "fill":
                return self._fill(page, params)
            elif action == "wait_for":
                return self._wait_for(page, params)
            elif action == "scroll":
                return self._scroll(page, params)
            elif action == "go_back":
                return self._go_back(page)
            elif action == "evaluate":
                return self._evaluate(page, params)
            else:
                return f"[Error: Unknown browser action '{action}']"
        except Exception as e:
            err_msg = str(e)
            # Auto-recover from crashed pages
            if "Target closed" in err_msg or "Page crashed" in err_msg or "Browser closed" in err_msg:
                global _page
                _page = None
                return f"[Error: Browser page crashed. Try again (new page will be created). Details: {e}]"
            return f"[Error: {e}]"

    # ── Action implementations ──────────────────────────────────────────

    def _navigate(self, page, params, config):
        import random
        url = params.get("url")
        if not url:
            return "[Error: 'url' parameter is required for navigate]"
        wait_until = params.get("wait_until", "domcontentloaded")
        timeout = params.get("timeout", config.get("timeout", 30)) * 1000

        # Small random delay to look more human-like
        try:
            page.wait_for_timeout(random.randint(200, 800))
        except Exception:
            pass

        try:
            response = page.goto(url, wait_until=wait_until, timeout=timeout)
            status = response.status if response else "no response"
            title = page.title()
            return f"[Navigated to {url}\nStatus: {status}\nTitle: {title}]"
        except Exception as e:
            return f"[Error navigating to {url}: {e}]"

    def _extract_text(self, page, params):
        selector = params.get("selector", "body")
        max_length = params.get("max_length", 5000)

        try:
            if selector == "body":
                text = page.inner_text("body")
            else:
                try:
                    text = page.inner_text(selector)
                except Exception:
                    text = page.inner_text("body")

            if len(text) > max_length:
                text = text[:max_length] + f"\n... [truncated, {len(text)} total chars]"
            return text
        except Exception as e:
            return f"[Error extracting text: {e}]"

    def _extract_links(self, page, params):
        selector = params.get("selector", "a")
        max_links = params.get("max_links", 50)

        try:
            links = page.evaluate("""(args) => {
                const elements = document.querySelectorAll(args.selector);
                const results = [];
                for (const el of elements) {
                    if (results.length >= args.maxLinks) break;
                    const text = el.innerText.trim().substring(0, 200);
                    const href = el.href;
                    if (href) results.push({ text, href });
                }
                return results;
            }""", {"selector": selector, "maxLinks": max_links})

            if not links:
                return "[No links found]"

            lines = [f"Found {len(links)} links:"]
            for link in links:
                text = link.get("text", "")
                href = link.get("href", "")
                if text:
                    lines.append(f"- [{text}]({href})")
                else:
                    lines.append(f"- {href}")
            return "\n".join(lines)
        except Exception as e:
            return f"[Error extracting links: {e}]"

    def _screenshot(self, page, params, workdir):
        selector = params.get("selector")
        full_page = params.get("full_page", False)
        path = params.get("path", "screenshot.png")

        workdir = workdir or "."
        full_path = os.path.join(workdir, path) if not os.path.isabs(path) else path
        parent = os.path.dirname(full_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        try:
            if selector:
                element = page.locator(selector).first
                element.screenshot(path=full_path)
            else:
                page.screenshot(path=full_path, full_page=full_page)
            return f"[Screenshot saved to {full_path}]"
        except Exception as e:
            return f"[Error taking screenshot: {e}]"

    def _pdf(self, page, params, workdir, config):
        path = params.get("path", "page.pdf")
        fmt = params.get("format", "A4")

        workdir = workdir or "."
        full_path = os.path.join(workdir, path) if not os.path.isabs(path) else path
        parent = os.path.dirname(full_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        if not config.get("headless", True):
            return "[Error: PDF export only works in headless mode. Set headless=true in browser config.]"

        try:
            page.pdf(path=full_path, format=fmt)
            return f"[PDF saved to {full_path}]"
        except Exception as e:
            return f"[Error saving PDF: {e}]"

    def _click(self, page, params):
        selector = params.get("selector")
        text = params.get("text")
        timeout = params.get("timeout", 10) * 1000

        if not selector and not text:
            return "[Error: 'selector' or 'text' parameter is required for click]"

        try:
            if text:
                page.get_by_text(text).first.click(timeout=timeout)
                return f"[Clicked element with text: {text}]"
            else:
                page.locator(selector).first.click(timeout=timeout)
                return f"[Clicked element: {selector}]"
        except Exception as e:
            return f"[Error clicking: {e}]"

    def _fill(self, page, params):
        selector = params.get("selector")
        value = params.get("value", "")
        press_enter = params.get("press_enter", False)

        if not selector:
            return "[Error: 'selector' parameter is required for fill]"

        try:
            page.locator(selector).first.fill(value)
            if press_enter:
                page.locator(selector).first.press("Enter")
            display_val = value[:50] + ("..." if len(value) > 50 else "")
            return f"[Filled '{selector}' with '{display_val}'{' and pressed Enter' if press_enter else ''}]"
        except Exception as e:
            return f"[Error filling: {e}]"

    def _wait_for(self, page, params):
        selector = params.get("selector")
        if not selector:
            return "[Error: 'selector' parameter is required for wait_for]"
        timeout = params.get("timeout", 10) * 1000

        try:
            page.wait_for_selector(selector, timeout=timeout)
            return f"[Element '{selector}' appeared]"
        except Exception as e:
            return f"[Error waiting for '{selector}': {e}]"

    def _scroll(self, page, params):
        direction = params.get("direction", "down")
        amount = params.get("amount", 3)
        pause_ms = params.get("pause", 500)
        delta = -1 if direction == "up" else 1

        try:
            for i in range(amount):
                page.mouse.wheel(0, delta * 500)
                if i < amount - 1:
                    page.wait_for_timeout(pause_ms)
            return f"[Scrolled {direction} {amount} time{'s' if amount != 1 else ''}]"
        except Exception as e:
            return f"[Error scrolling: {e}]"

    def _go_back(self, page):
        try:
            page.go_back()
            title = page.title()
            url = page.url
            return f"[Went back to: {url}\nTitle: {title}]"
        except Exception as e:
            return f"[Error going back: {e}]"

    def _evaluate(self, page, params):
        script = params.get("script")
        if not script:
            return "[Error: 'script' parameter is required for evaluate]"

        try:
            result = page.evaluate(script)
            text = str(result)
            if len(text) > MAX_OBSERVATION_CHARS:
                text = text[:MAX_OBSERVATION_CHARS] + f"\n... [truncated, {len(text)} total chars]"
            return text
        except Exception as e:
            return f"[Error evaluating script: {e}]"
