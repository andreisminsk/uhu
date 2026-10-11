"""Secrets management — .env loading and ${VAR} resolution.

Pattern (adopted from ~/.mercury): config stores only the env var NAME
("auth_token_env": "GITHUB_MCP_TOKEN"); the value lives in
~/.uhu/.secrets/.env or the OS environment. OS env wins over .env,
allowing per-session overrides.

See dev-docs/UHU-HOME-ARCH.md.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")

# One-time migration hints (avoid nagging on every call)
_hinted = set()


def secrets_dir():
    """Return the secrets directory (~/.uhu/.secrets)."""
    from .home import uhu_home
    return os.path.join(uhu_home(), ".secrets")


def dotenv_path():
    """Return the .env file path (~/.uhu/.secrets/.env)."""
    return os.path.join(secrets_dir(), ".env")


def load_dotenv(override=False):
    """Load KEY=VALUE pairs from ~/.uhu/.secrets/.env into os.environ.

    OS environment wins by default (override=False) — .env only fills gaps.
    Supports: KEY=VALUE, 'export KEY=VALUE', # comments, blank lines,
    single/double-quoted values. Returns the number of variables set.
    """
    path = dotenv_path()
    if not os.path.isfile(path):
        return 0
    count = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].lstrip()
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                if not re.match(r"[A-Za-z_][A-Za-z0-9_]*\Z", key):
                    continue
                if override or key not in os.environ:
                    os.environ[key] = value
                    count += 1
    except OSError as e:
        logger.debug("Failed to read %s: %s", path, e)
    return count


def resolve_value(value):
    """Expand ${VAR} and ${VAR:-default} in a string value.

    Returns None if a referenced var is missing and has no default
    (caller should treat the field as absent — never an empty credential).
    Non-string values pass through unchanged.
    """
    if not isinstance(value, str):
        return value
    missing = False

    def _sub(m):
        nonlocal missing
        var, default = m.group(1), m.group(2)
        val = os.environ.get(var)
        if not val:
            if default is not None:
                return default
            missing = True
            return ""
        return val

    result = _VAR_PATTERN.sub(_sub, value)
    if missing:
        return None
    return result


def resolve_config_secrets(config):
    """Expand ${VAR} in known secret-bearing config fields, in place.

    Fields: mcpServers.*.headers.*, mcpServers.*.env.*,
            tools.*.api_key, llm_parser.api_key, skills.*.api_key.
    A missing env var (no default) → field removed with a warning.
    """
    def _resolve_dict(d, label):
        for k in list(d.keys()):
            v = d[k]
            if isinstance(v, str) and "${" in v:
                resolved = resolve_value(v)
                if resolved is None:
                    logger.warning("Secret env var not set for %s.%s — field removed", label, k)
                    del d[k]
                else:
                    d[k] = resolved

    for name, server in (config.get("mcpServers") or {}).items():
        if isinstance(server, dict):
            if isinstance(server.get("headers"), dict):
                _resolve_dict(server["headers"], f"mcpServers.{name}.headers")
            if isinstance(server.get("env"), dict):
                _resolve_dict(server["env"], f"mcpServers.{name}.env")

    for tname, tcfg in (config.get("tools") or {}).items():
        if isinstance(tcfg, dict) and isinstance(tcfg.get("api_key"), str) and "${" in tcfg["api_key"]:
            resolved = resolve_value(tcfg["api_key"])
            if resolved is None:
                logger.warning("Secret env var not set for tools.%s.api_key — field removed", tname)
                tcfg.pop("api_key", None)
            else:
                tcfg["api_key"] = resolved

    # llm_parser.api_key is a direct field of the section
    lp = config.get("llm_parser")
    if isinstance(lp, dict) and isinstance(lp.get("api_key"), str) and "${" in lp["api_key"]:
        resolved = resolve_value(lp["api_key"])
        if resolved is None:
            logger.warning("Secret env var not set for llm_parser.api_key — field removed")
            lp.pop("api_key", None)
        else:
            lp["api_key"] = resolved

    # skills.<name>.api_key are nested per-skill dicts
    for key, val in (config.get("skills") or {}).items():
        if isinstance(val, dict) and isinstance(val.get("api_key"), str) and "${" in val["api_key"]:
            resolved = resolve_value(val["api_key"])
            if resolved is None:
                logger.warning("Secret env var not set for skills.%s.api_key — field removed", key)
                val.pop("api_key", None)
            else:
                val["api_key"] = resolved
    return config


def migration_hint(legacy_path, home_path):
    """Print a one-time hint suggesting migration to ~/.uhu/.secrets."""
    key = os.path.normcase(os.path.abspath(legacy_path))
    if key in _hinted:
        return
    _hinted.add(key)
    try:
        from .actions import agent_print
        agent_print(
            f"[⚠ Secret file found at legacy location: {legacy_path}. "
            f"Run /migrate to copy it to {home_path}]"
        )
    except Exception:
        pass
