"""Browser automation tool using Playwright with stealth support.

Provides a clean browser context per session for web browsing, scraping,
and interaction. Uses playwright-stealth for bot detection avoidance.

All Playwright operations run in a dedicated worker thread to isolate
Playwright's asyncio event loop from the main thread. Without this
isolation, Playwright's sync API pollutes the main thread's asyncio
state, breaking prompt_toolkit input (causing 'coroutine never awaited'
RuntimeWarnings and silent input failures).
"""

import atexit
import os
import queue
import threading

from ..constants import MAX_OBSERVATION_CHARS

_BROWSER_DEPS_ERROR = (
    "Browser dependencies not installed. "
    "Run: pip install playwright playwright-stealth && playwright install chromium"
)


# ── Browser worker thread ─────────────────────────────────────────────

class _BrowserWorker(threading.Thread):
    """Dedicated thread for all Playwright operations.

    Playwright's sync API creates an asyncio event loop in the calling
    thread. By confining it to this worker thread, we prevent that event
    loop from corrupting the main thread's asyncio state, which would
    break prompt_toolkit (causing 'coroutine never awaited' warnings
    and silent input failures).
    """

    def __init__(self):
        super().__init__(daemon=True, name="playwright-worker")
        self._cmd_q = queue.Queue()
        self._result_q = queue.Queue()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def run(self):
        while True:
            item = self._cmd_q.get()
            if item is None:
                self._cleanup()
                return
            fn, args = item
            try:
                result = fn(*args)
                self._result_q.put(('ok', result))
            except Exception as e:
                self._result_q.put(('err', e))

    def submit(self, fn, *args):
        """Run fn(*args) in worker thread. Blocks until result."""
        self._cmd_q.put((fn, args))
        status, val = self._result_q.get()
        if status == 'err':
            raise val
        return val

    def shutdown(self):
        """Signal worker to stop and wait for cleanup."""
        self._cmd_q.put(None)
        if self.is_alive():
            self.join(timeout=5)

    def _cleanup(self):
        """Close all Playwright resources. Must run in worker thread.

        Catches BaseException (not just Exception) because Playwright's
        sync API can raise KeyboardInterrupt when its dispatcher fiber is
        interrupted during shutdown.
        """
        for obj in [self._page, self._context]:
            try:
                if obj:
                    obj.close()
            except BaseException:
                pass
        try:
            if self._browser:
                self._browser.close()
        except BaseException:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except BaseException:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None


# ── Module-level worker management ────────────────────────────────────

_worker = None
_worker_lock = threading.Lock()


def _get_worker():
    """Get or create the browser worker thread."""
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = _BrowserWorker()
            _worker.start()
        return _worker


def _close_browser():
    """Shut down the browser worker and release all resources."""
    global _worker
    with _worker_lock:
        if _worker and _worker.is_alive():
            _worker.shutdown()
        _worker = None


atexit.register(_close_browser)


_STEALTH_SCRIPT = """
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
"""


def _apply_stealth(page, config):
    """Apply playwright-stealth patches if available and enabled.

    Stealth scripts are applied at the context level (add_init_script) so
    they run once per new document — not re-applied on every page. This
    prevents duplicate script accumulation when pages are recreated.
    """
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
    """Apply additional stealth patches beyond playwright-stealth.

    Uses add_init_script so the script runs automatically on every new
    document navigation, without accumulating duplicates on re-init.
    """
    try:
        page.add_init_script(_STEALTH_SCRIPT)
    except Exception:
        pass  # page may already be closed


def _setup_resource_blocking(page, blocked_types):
    """Block specified resource types from loading via route interception.

    Only blocks document and subresource requests — navigation requests
    (document) are always allowed through to avoid breaking SPA routing.
    """
    if not blocked_types:
        return

    def handle_route(route):
        # Never block the main document/navigation request — this breaks
        # SPA client-side routing that uses history API or fetch-based
        # navigation.
        if route.request.resource_type in blocked_types:
            route.abort()
        else:
            route.continue_()

    try:
        page.route("**/*", handle_route)
    except Exception:
        pass  # route setup can fail on certain pages


def _ensure_browser(config=None):
    """Ensure browser is running in the worker thread.

    Returns (None, error_string) on failure, or (True, None) on success.
    All Playwright objects live exclusively in the worker thread.
    """
    worker = _get_worker()

    def _init_in_worker():
        """Run inside worker thread — manages all Playwright objects."""
        cfg = config or {}

        # Fast path: existing page still alive
        if (worker._page and not worker._page.is_closed()
                and worker._browser and worker._browser.is_connected()):
            return None  # no error

        # Browser alive but page closed — create new page
        if worker._browser and worker._browser.is_connected() and worker._context:
            try:
                worker._page = worker._context.new_page()
                _apply_stealth(worker._page, cfg)
                _setup_resource_blocking(
                    worker._page, cfg.get("block_resources", []))
                return None
            except Exception:
                worker._cleanup()

        # Need fresh start
        worker._cleanup()
        headless = cfg.get("headless", True)
        slow_mo = cfg.get("slow_mo", 50)
        viewport = cfg.get("viewport", {"width": 1280, "height": 720})
        user_agent = cfg.get("user_agent")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return _BROWSER_DEPS_ERROR

        try:
            worker._playwright = sync_playwright().start()
        except Exception as e:
            return f"[Error starting Playwright: {e}. {_BROWSER_DEPS_ERROR}]"

        try:
            worker._browser = worker._playwright.chromium.launch(
                headless=headless, slow_mo=slow_mo
            )
        except Exception as e:
            err_msg = str(e)
            if "Executable doesn't exist" in err_msg or "playwright install" in err_msg.lower():
                return ("Browser binaries not installed. "
                        "Run: playwright install chromium")
            worker._cleanup()
            return f"[Error launching browser: {e}]"

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
            worker._context = worker._browser.new_context(**context_kwargs)
        except Exception as e:
            worker._cleanup()
            return f"[Error creating browser context: {e}]"

        try:
            worker._page = worker._context.new_page()
        except Exception as e:
            worker._cleanup()
            return f"[Error creating page: {e}]"

        _apply_stealth(worker._page, cfg)
        _setup_resource_blocking(worker._page, cfg.get("block_resources", []))
        return None

    try:
        error = worker.submit(_init_in_worker)
    except Exception as e:
        return None, f"[Error: {e}]"

    if error:
        return None, error
    return True, None


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
    "### reload\n"
    "Reload the current page (useful after editing a local HTML file).\n"
    '```json\n'
    '{"action": "reload", "wait_until": "domcontentloaded", "timeout": 30}\n'
    '"""\n'
    "Optional: wait_until (load|domcontentloaded|networkidle, default: domcontentloaded), timeout (default: 30).\n"
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
                "screenshot, pdf, click, fill, wait_for, scroll, go_back, reload, evaluate, close"
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

        ok, error = _ensure_browser(browser_config)
        if error:
            return error

        worker = _get_worker()

        def _run_action():
            """Run inside worker thread — page lives here."""
            page = worker._page
            if not page or page.is_closed():
                return "[Error: Browser page is not available. Try again.]"
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
            elif action == "reload":
                return self._reload(page, params, browser_config)
            elif action == "evaluate":
                return self._evaluate(page, params)
            else:
                return f"[Error: Unknown browser action '{action}']"

        _CRASH_MARKERS = (
            "Target closed", "Page crashed", "Browser closed",
            "Browser process crashed", "Connection closed",
            "Protocol error", "Target page, context or browser has been closed",
        )

        try:
            return worker.submit(_run_action)
        except Exception as e:
            err_msg = str(e)
            if not any(m in err_msg for m in _CRASH_MARKERS):
                return f"[Error: {e}]"

            # Full cleanup of all Playwright objects — not just the page.
            # A dead context or browser would cause repeated failures on
            # retry if only _page were reset.
            try:
                worker.submit(worker._cleanup)
            except Exception:
                pass

            # One automatic retry: re-init browser and re-run the action.
            try:
                ok, error = _ensure_browser(browser_config)
                if error:
                    return f"[Error: Browser crashed and recovery failed. Details: {e}]"
                return worker.submit(_run_action)
            except Exception as e2:
                return f"[Error: Browser crashed. Retry also failed. Original: {e}. Retry: {e2}]"

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
                # Try exact match first to avoid clicking wrong elements
                # when the text appears as a substring elsewhere. Fall back
                # to non-exact if exact finds nothing (handles whitespace
                # and minor text differences).
                try:
                    page.get_by_text(text, exact=True).first.click(
                        timeout=timeout)
                except Exception:
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
            # Get actual viewport height so 'amount' means viewport heights,
            # not a fixed pixel value.
            viewport_height = page.evaluate("window.innerHeight") or 1080
            scroll_px = delta * viewport_height

            for i in range(amount):
                page.mouse.wheel(0, scroll_px)
                if i < amount - 1:
                    page.wait_for_timeout(pause_ms)
            return f"[Scrolled {direction} {amount} viewport height{'s' if amount != 1 else ''}]"
        except Exception as e:
            return f"[Error scrolling: {e}]"

    def _go_back(self, page):
        try:
            # go_back() returns None for bfcache navigations even when
            # there IS history, so we can't rely on the return value.
            # Instead, try go_back and check where we landed.
            page.go_back()

            # If we landed on about:blank, there was no real history.
            if page.url == "about:blank":
                page.go_forward()
                return "[Cannot go back — no browser history]"

            title = page.title()
            url = page.url
            return f"[Went back to: {url}\nTitle: {title}]"
        except Exception as e:
            return f"[Error going back: {e}]"

    def _reload(self, page, params, config):
        wait_until = params.get("wait_until", "domcontentloaded")
        timeout = params.get("timeout", config.get("timeout", 30)) * 1000

        try:
            response = page.reload(wait_until=wait_until, timeout=timeout)
            status = response.status if response else "no response"
            title = page.title()
            url = page.url
            return f"[Reloaded {url}\nStatus: {status}\nTitle: {title}]"
        except Exception as e:
            return f"[Error reloading page: {e}]"

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
