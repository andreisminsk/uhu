"""Tool configuration — loaded from .ollama_agent.json with built-in defaults."""

import json
import os

# ── Configuration ────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "llm_query": {
        "api_url": "http://localhost:11434",
        "model": "kimi-k2.5:cloud",
        "temperature": 0.3,
        "timeout": 120
    },
    "web_fetch": {
        "llm_model": "kimi-k2.5:cloud",
        "llm_summarize": True,
        "max_chars": 3000
    },
    "tools": {
        "image_analysis": {
            "base_url": "http://localhost:11434/",
            "model": "gemma4:31b-cloud"
        },
        "google_calendar": {
            "credentials_path": "~/.ollama_gcal/gs-cred.json",
            "calendar_id": "primary",
            "timezone": "UTC"
        },
        "browser": {
            "headless": True,
            "slow_mo": 50,
            "viewport": {"width": 1920, "height": 1080},
            "stealth": True,
            "timeout": 30,
            "user_agent": None,
            "block_resources": []
        }
    },
    "memory": {
        "max_lines": 50,
        "warn_threshold": 40
    }
}

CONFIG_FILENAME = ".ollama_agent.json"

# Module-level config cache, initialized on first load
_config = None


def _agent_dir():
    """Find the uhu agent installation directory (where .ollama_agent.json lives)."""
    # ollama_agent/tools/_config.py → project root
    this_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(this_dir))


def load_config(workdir=None):
    """Load tool configuration from .ollama_agent.json.

    Search order: workdir first, then agent installation dir, then home directory.
    Falls back to built-in defaults if no config file is found.
    Caches the result for subsequent get_config() calls.
    """
    global _config
    config = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    paths = []
    if workdir:
        paths.append(os.path.join(workdir, CONFIG_FILENAME))
    paths.append(os.path.join(_agent_dir(), CONFIG_FILENAME))
    paths.append(os.path.join(os.path.expanduser("~"), CONFIG_FILENAME))
    for path in paths:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                _deep_merge(config, user_config)
                break  # first found wins
            except Exception:
                pass
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