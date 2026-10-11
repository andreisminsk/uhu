"""Tool configuration — loaded from .ollama_agent.json with built-in defaults."""

import json
import logging
import os

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    # User's name — the model will address them by name when appropriate.
    # Example: "user_name": "Andrei"
    "user_name": "",
    "llm_query": {
        "api_url": "http://localhost:11434",
        "model": "kimi-k2.6:cloud",
        "temperature": 0.3,
        "timeout": 120
    },
    "web_fetch": {
        "llm_model": "kimi-k2.6:cloud",
        "llm_summarize": True,
        "max_chars": 3000
    },
    "tools": {
        "image_analysis": {
            "base_url": "http://localhost:11434/",
            "model": "glm-5.3-flash:cloud",
            "api_type": "ollama",
            "api_key": "ollama",
            "timeout": 120
        },
        "google_calendar": {
            "credentials_path": "~/.uhu/.secrets/gs-cred.json",
            "calendar_id": "primary",
            "timezone": "UTC"
        },
        "google_search": {
            "enabled": False,
            "api_key": "",
            "cx": ""
        },
        "ollama_balance": {
            "cookie_path": "~/.uhu/.secrets/.cookies/ollama.com_cookies.txt",
            "ttl": 300
        },
        "browser": {
            "headless": True,
            "slow_mo": 50,
            "viewport": {"width": 1920, "height": 1080},
            "stealth": True,
            "timeout": 30,
            "user_agent": None,
            "block_resources": []
        },
        "ui_automation": {
            "output_dir": ".uhu/.cache",
            "default_delay_ms": 800,
            "max_keys_length": 200,
            "timeout": 15
        }
    },
    "privacy": {
        "mode": "standard",          # off | standard | strict
        "policy": "confirm",         # block | confirm | redact (filename tier)
        "filename_patterns": [],      # empty = use defaults from privacy.py
        "content_patterns": [],       # empty = use defaults from privacy.py
        "allow": []                   # user-exempt paths (e.g. ".env.example")
    },
    "memory": {
        "max_lines": 50,
        "warn_threshold": 40
    },
    "skills": {
        "graph-ai": {
            "model": "glm-5.3-flash:cloud",
            "base_url": "http://localhost:11434",
            "api_key": "ollama-local",
            "max_tokens": 131072
        }
    },
    "llm_parser": {
        "enabled": False,
        "model": "",
        "base_url": "",
        "timeout": 60,
        "api_type": "ollama",
        "api_key": "ollama"
    },
    # Extra skill directories (list of paths, in order) — mercury-compatible.
    # Loaded after workdir .skills/ and ~/.uhu/skills/ (see session.py).
    "extra_skills_dirs": []
}

CONFIG_FILENAME = ".ollama_agent.json"

# Module-level config cache, initialized on first load
_config = None


def _agent_dir():
    """Find the uhu agent installation directory (where .ollama_agent.json lives)."""
    # ollama_agent/tools/_config.py → project root
    this_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(this_dir))


def _config_search_paths(workdir=None):
    """Config file paths in precedence order (highest first). All layers merge.

    Layered merge (see dev-docs/UHU-HOME-ARCH.md):
      1. <workdir>/.ollama_agent.json   — project overrides
      2. ~/.uhu/.ollama_agent.json      — user-global home
      3. Legacy: agent install dir, then ~/.ollama_agent.json (backward compat)
    """
    from ..home import uhu_home
    paths = []
    if workdir:
        paths.append(os.path.join(workdir, CONFIG_FILENAME))
    paths.append(os.path.join(uhu_home(), CONFIG_FILENAME))
    # Legacy locations (backward compat): agent install dir, then home dir
    paths.append(os.path.join(_agent_dir(), CONFIG_FILENAME))
    paths.append(os.path.join(os.path.expanduser("~"), CONFIG_FILENAME))
    # Dedupe (UHU_HOME may coincide with workdir or install dir)
    seen = set()
    unique = []
    for p in paths:
        rp = os.path.normpath(os.path.abspath(p))
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


def load_config(workdir=None):
    """Load tool configuration from .ollama_agent.json.

    All existing layers are deep-merged over DEFAULT_CONFIG in precedence
    order (lists replace, dicts merge) — a workdir config setting only
    user_name inherits global MCP/tools config from ~/.uhu.
    Caches the result for subsequent get_config() calls.
    """
    global _config
    config = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    # Merge lowest-precedence first so higher layers override:
    # _config_search_paths returns highest-first, so iterate reversed.
    for path in reversed(_config_search_paths(workdir)):
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                _deep_merge(config, user_config)
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON in %s: %s — skipping layer", path, e)
            except Exception as e:
                logger.warning("Failed to load config from %s: %s — skipping layer", path, e)
    # Expand ${VAR} in secret-bearing fields (see secrets.py / UHU-HOME-ARCH.md)
    from ..secrets import resolve_config_secrets
    resolve_config_secrets(config)
    _config = config
    return config


def _find_config_dir(workdir=None):
    """Find the directory containing .ollama_agent.json (workdir, agent dir, or home)."""
    paths = []
    if workdir:
        paths.append(os.path.join(workdir, CONFIG_FILENAME))
    paths.append(os.path.join(_agent_dir(), CONFIG_FILENAME))
    paths.append(os.path.join(os.path.expanduser("~"), CONFIG_FILENAME))
    for path in paths:
        if os.path.isfile(path):
            return os.path.dirname(path)
    # Default: workdir or current dir
    return workdir or os.getcwd()


def get_config():
    """Return the cached config, loading from defaults if not yet initialized."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def save_config(config, workdir=None):
    """Save tool configuration to .ollama_agent.json in workdir."""
    dir_path = workdir or "."
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, CONFIG_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    return path


def _deep_merge(base, override):
    """Deep merge override into base dict (in-place)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value