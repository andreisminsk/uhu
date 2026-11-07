"""Command-line interface and entry point."""

import argparse
import logging
import os
import shutil
import sys

logging.basicConfig(level=logging.ERROR, format="%(asctime)s %(name)s %(levelname)s: %(message)s")

from .session import ChatSession

try:
    import setproctitle
    setproctitle.setproctitle("uhu")
except Exception:
    pass


def print_logo():
    """Print the ASCII logo from uhu-appicon.txt in neon green (AI output color).

    Skipped when the terminal is narrower than 47 columns.
    """
    if shutil.get_terminal_size().columns < 47:
        return
    # Resolve logo: package data first (pip installs), repo root fallback (git checkout)
    _pkg_dir = os.path.dirname(os.path.abspath(__file__))
    _logo_candidates = [
        os.path.join(_pkg_dir, "uhu-appicon.txt"),
        os.path.join(_pkg_dir, "..", "uhu-appicon.txt"),
    ]
    logo_path = next((p for p in _logo_candidates if os.path.isfile(p)), _logo_candidates[0])
    try:
        with open(logo_path, "r", encoding="utf-8") as f:
            logo = f.read()
    except OSError:
        return
    from .constants import ANSI_AI, ANSI_RESET
    from .platform import terminal
    print()
    terminal.enable_ansi()
    if sys.stdout.isatty():
        print(ANSI_AI + logo.rstrip("\n") + ANSI_RESET)
    else:
        print(logo.rstrip("\n"))
    print()


def main():
    parser = argparse.ArgumentParser(description="Interactive Ollama chat with agentic coder mode")
    parser.add_argument("-v", "--version", action="store_true",
                        help="Show version and exit")
    parser.add_argument("--host", default="http://localhost:11434",
                        help="Ollama server URL (default: http://localhost:11434)")
    parser.add_argument("--api-ollama", action="store_true", dest="api_ollama",
                        default=True, help="Use native Ollama API (default)")
    parser.add_argument("--api-openai", action="store_true", dest="api_openai",
                        help="Use OpenAI-compatible API endpoint")
    parser.add_argument("--api-key", default=None,
                        help="API key for OpenAI-compatible endpoint (default: ollama)")
    parser.add_argument("--openai-extra-body", default=None,
                        help="Path to JSON file with extra request body params for OpenAI-compatible API (e.g. ~/.uhu/glm-extras.json)")
    parser.add_argument("--model", default="glm-5.3-flash:cloud",
                        help="Model name to use for chat (default: glm-5.3-flash:cloud)")
    parser.add_argument("--ctx", type=int, default=1024000,
                        help="Context window size in tokens (default: 1024000)")
    parser.add_argument("--no-stream", action="store_false", dest="stream",
                        help="Disable streaming output (streaming is enabled by default)")
    parser.add_argument("--no-log", action="store_true",
                        help="Disable conversation logging (logging is enabled by default)")
    parser.add_argument("--sessions-dir", default=None,
                        help="Directory for saving and restoring chat sessions (default: workdir/.uhu/.sessions)")
    parser.add_argument("--no-agent", action="store_false", dest="agent",
                        help="Disable agentic coder mode (enabled by default)")
    parser.add_argument("--workdir", default=".",
                        help="Working directory for file writes and command execution (default: .)")
    parser.add_argument("--no-tools", action="store_false", dest="tools",
                        help="Disable tools mode (enabled by default)")
    parser.add_argument("--skills", action="store_true",
                        help="Enable skills mode — allow the model to invoke structured development skills (code-review, test-gen, doc-gen, plan)")
    parser.add_argument("--skills-dir", default="./.skills",
                        help="Directory for custom skill definitions — SKILL.md directories, Python (.py) or JSON (.json) files (default: ./.skills)")
    parser.add_argument("--no-autosave", action="store_true",
                        help="Disable automatic session saving after each model reply")
    parser.add_argument("--no-thinking", action="store_false", dest="thinking",
                        help="Disable thinking mode (enabled by default)")
    parser.add_argument("--think-level", default=None, dest="think_level",
                        help="Thinking effort for reasoning models: off, low, medium, high, max (default: model default). Ollama native API sends top-level 'think'; OpenAI-compatible API sends reasoning_effort. Change mid-session with /think")
    parser.add_argument("--no-cache", action="store_true",
                        help="Disable file caching to .uhu/.cache/ directory")
    parser.add_argument("--mcp", action="store_true",
                        help="Enable MCP server tools (configured in .ollama_agent.json)")
    parser.add_argument("--tpm", type=int, default=None,
                        help="Tokens-per-minute limit for OpenAI-compatible backends (enables proactive TPM tracking and aggressive 429 retry)")
    parser.add_argument("--max-context", type=int, default=None,
                        help="Max context cap for history trimming (OpenAI-compatible + --tpm only, default: 16384)")
    parser.add_argument("--temperature", type=float, default=None,
                        help="Sampling temperature 0.0-2.0 (default: 0.0 for Ollama native API; provider default for OpenAI-compatible API). Change mid-session with /temperature")
    parser.add_argument("--top-p", type=float, default=None, dest="top_p",
                        help="Top-p (nucleus) sampling 0.0-1.0 (default: model/provider default). Change mid-session with /top-p")
    parser.add_argument("--no-sound", action="store_true",
                        help="Disable event sounds (done/question notifications). Toggled mid-session with /sound")
    parser.add_argument("--max-rounds", type=int, default=None, dest="max_rounds",
                        help="Max feedback-loop rounds per message (default: 3 interactive, 7 one-shot). Changeable mid-session with /max-rounds")
    parser.add_argument("--no-llm-parsing", action="store_true",
                        help="Disable LLM fallback parsing (configured via llm_parser section in .ollama_agent.json)")
    parser.add_argument("--prompt-file", default=None, dest="prompt_file",
                        help="Read the one-shot prompt from a file ('-' = stdin) instead of positional prompt args. Mutually exclusive with positional prompt")
    parser.add_argument("--no-logo", action="store_true",
                        help="Do not print the ASCII logo at startup")
    parser.add_argument("prompt", nargs="*", default=[],
                        help="One-shot prompt — execute and exit (no interactive loop)")
    args = parser.parse_args()

    # Strip surrounding quotes that Windows shell may include in arguments
    if args.version:
        from .utils import get_local_version
        version = get_local_version()
        if version:
            print(f"uhu v{version}")
        else:
            print("[Version not found]")
        return

    is_oneshot = bool(args.prompt) or args.prompt_file is not None
    if not args.no_logo and not is_oneshot:
        print_logo()

    workdir = args.workdir
    if workdir and len(workdir) >= 2 and (
        (workdir.startswith('"') and workdir.endswith('"')) or
        (workdir.startswith("'") and workdir.endswith("'"))
    ):
        workdir = workdir[1:-1]

    # Bootstrap ~/.uhu skeleton (idempotent; respects UHU_HOME) — see dev-docs/UHU-HOME-ARCH.md
    from .home import bootstrap
    bootstrap(quiet=is_oneshot)

    # Load ~/.uhu/.secrets/.env into os.environ (OS env wins) before any
    # config resolution — enables auth_token_env / ${VAR} secrets.
    from .secrets import load_dotenv
    load_dotenv()

    sessions_dir = args.sessions_dir or os.path.join(os.path.abspath(workdir), ".uhu", ".sessions")
    # Compute default log path: <workdir>/.uhu/uhu-<workdir-basename>.log
    if args.no_log:
        log_path = None
    else:
        log_path = os.path.join(os.path.abspath(workdir), ".uhu", f"uhu-{os.path.basename(os.path.abspath(workdir))}.log")
    # Validate --temperature early (fail fast)
    if args.temperature is not None and not (0.0 <= args.temperature <= 2.0):
        print("[Error: --temperature must be between 0.0 and 2.0]")
        sys.exit(1)

    # Validate --top-p early (fail fast)
    if args.top_p is not None and not (0.0 <= args.top_p <= 1.0):
        print("[Error: --top-p must be between 0.0 and 1.0]")
        sys.exit(1)

    # Determine API type
    api_type = "openai" if args.api_openai else "ollama"
    
    # Validate --openai-extra-body early (fail fast with clean error)
    if args.openai_extra_body:
        import json as _json
        _p = os.path.expanduser(args.openai_extra_body)
        if not os.path.isfile(_p):
            print(f"[Error: --openai-extra-body file not found: {_p}]")
            sys.exit(1)
        try:
            with open(_p, "r", encoding="utf-8") as _f:
                _json.load(_f)
        except (ValueError, OSError) as _e:
            print(f"[Error: --openai-extra-body file is invalid: {_p}: {_e}]")
            sys.exit(1)

    # Validate --max-rounds early (fail fast) — same bounds as /max-rounds
    if args.max_rounds is not None and not (1 <= args.max_rounds <= 20):
        print("[Error: --max-rounds must be between 1 and 20]")
        sys.exit(1)

    # --prompt-file: read the one-shot prompt from a file or stdin ('-').
    # Mutually exclusive with the positional prompt — fail fast on both.
    prompt_text = None
    if args.prompt_file:
        if args.prompt:
            print("[Error: --prompt-file cannot be combined with a positional prompt — use one or the other]")
            sys.exit(1)
        if args.prompt_file == "-":
            prompt_text = sys.stdin.read()
        else:
            _pf = os.path.expanduser(args.prompt_file)
            if not os.path.isfile(_pf):
                print(f"[Error: --prompt-file file not found: {_pf}]")
                sys.exit(1)
            try:
                with open(_pf, "r", encoding="utf-8") as _f:
                    prompt_text = _f.read()
            except OSError as _e:
                print(f"[Error: --prompt-file cannot be read: {_pf}: {_e}]")
                sys.exit(1)
        # Normalize line endings (files edited on Windows may carry \r\n)
        prompt_text = prompt_text.replace("\r\n", "\n").replace("\r", "\n")
        if not prompt_text.strip():
            _src = "(stdin)" if args.prompt_file == "-" else args.prompt_file
            print(f"[Error: --prompt-file is empty: {_src}]")
            sys.exit(1)

    session = ChatSession(
        host=args.host,
        model=args.model,
        ctx_size=args.ctx,
        stream=args.stream,
        log_path=log_path,
        sessions_dir=sessions_dir,
        agent=args.agent,
        workdir=workdir,
        tools=args.tools,
        skills=args.skills,
        skills_dir=args.skills_dir,
        autosave=not args.no_autosave,
        cache_files=not args.no_cache,
        thinking=args.thinking,
        quiet=is_oneshot,
        mcp=args.mcp,
        api_type=api_type,
        api_key=args.api_key,
        openai_extra_body=args.openai_extra_body,
        tpm_limit=args.tpm,
        max_context=args.max_context,
        no_llm_parsing=args.no_llm_parsing,
        temperature=args.temperature,
        top_p=args.top_p,
        think_level=args.think_level,
        max_rounds=args.max_rounds,
    )

    # Event sounds — single point of muting for all playback
    if args.no_sound:
        from .sound import set_enabled
        set_enabled(False)

    if args.prompt:
        session.run_once(" ".join(args.prompt))
    elif prompt_text is not None:
        session.run_once(prompt_text)
    else:
        while session is not None:
            session = session.run()


if __name__ == "__main__":
    main()
