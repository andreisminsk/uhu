"""UHU home directory (~/.uhu) — path resolution and first-run bootstrap.

Layout (see dev-docs/UHU-HOME-ARCH.md):

    ~/.uhu/
      .ollama_agent.json          # global config (optional, layered-merged)
      .secrets/
        .env                      # env vars file (phase 2)
        .cookies/                 # per-domain cookie files (phase 2)
      skills/                     # user-global skills

Env override: UHU_HOME replaces ~/.uhu (tests/CI must not pollute real home).
"""

import os

HOME_DIRNAME = ".uhu"


def uhu_home():
    """Return the uhu home directory (UHU_HOME env override or ~/.uhu)."""
    override = os.environ.get("UHU_HOME")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(os.path.expanduser("~"), HOME_DIRNAME)


def _copy_templates(home):
    """Copy packaged templates into ~/.uhu (never overwrites existing files).

    Ships: .ollama_agent.json.example (config skeleton — NOT the live config,
    absence of config is meaningful) and skills/README.md (starter docs).
    """
    import shutil
    try:
        templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
        if not os.path.isdir(templates_dir):
            return
        mapping = [
            (os.path.join(templates_dir, ".ollama_agent.json.example"),
             os.path.join(home, ".ollama_agent.json.example")),
            (os.path.join(templates_dir, "skills", "README.md"),
             os.path.join(home, "skills", "README.md")),
        ]
        for src, dst in mapping:
            if os.path.isfile(src) and not os.path.isfile(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
    except OSError:
        pass


def bootstrap(quiet=False):
    """Create the ~/.uhu skeleton if missing. Idempotent.

    Creates: ~/.uhu/, .secrets/, .secrets/.cookies/, skills/, plus packaged
    templates (.ollama_agent.json.example, skills/README.md — never overwrites).
    Does NOT create .ollama_agent.json — absence of config is meaningful
    (defaults apply); an empty copy would freeze DEFAULT_CONFIG.

    Returns True if anything was created.
    """
    home = uhu_home()
    created = []
    for sub in ("", ".secrets", os.path.join(".secrets", ".cookies"), "skills"):
        path = os.path.join(home, sub) if sub else home
        if not os.path.isdir(path):
            try:
                os.makedirs(path, exist_ok=True)
                created.append(path)
            except OSError:
                pass
    _copy_templates(home)
    if created and not quiet:
        from .actions import agent_print
        agent_print(f"[Initialized {home}]")
    return bool(created)
