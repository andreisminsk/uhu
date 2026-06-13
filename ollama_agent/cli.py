"""Command-line interface and entry point."""

import argparse
import logging
import os

logging.basicConfig(level=logging.ERROR, format="%(asctime)s %(name)s %(levelname)s: %(message)s")

from .session import ChatSession


def main():
    parser = argparse.ArgumentParser(description="Interactive Ollama chat with agentic coder mode")
    parser.add_argument("-v", "--version", action="store_true",
                        help="Show version and exit")
    parser.add_argument("--host", default="http://localhost:11434",
                        help="Ollama server URL (default: http://localhost:11434)")
    parser.add_argument("--model", default="glm-5.1:cloud",
                        help="Model name to use for chat (default: glm-5.1:cloud)")
    parser.add_argument("--ctx", type=int, default=202752,
                        help="Context window size in tokens (default: 202752)")
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
    parser.add_argument("--no-cache", action="store_true",
                        help="Disable file caching to .uhu/.cache/ directory")
    args = parser.parse_args()

    # Strip surrounding quotes that Windows shell may include in arguments
    if args.version:
        ver_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uhu-ver.txt")
        try:
            with open(ver_path, "r", encoding="utf-8") as f:
                print(f"uhu v{f.read().strip()}")
            return
        except FileNotFoundError:
            print("[Version file not found]")
            return

    workdir = args.workdir
    if workdir and len(workdir) >= 2 and (
        (workdir.startswith('"') and workdir.endswith('"')) or
        (workdir.startswith("'") and workdir.endswith("'"))
    ):
        workdir = workdir[1:-1]

    sessions_dir = args.sessions_dir or os.path.join(os.path.abspath(workdir), ".uhu", ".sessions")
    # Compute default log path: <workdir>/.uhu/uhu-<workdir-basename>.log
    if args.no_log:
        log_path = None
    else:
        log_path = os.path.join(os.path.abspath(workdir), ".uhu", f"uhu-{os.path.basename(os.path.abspath(workdir))}.log")

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
    )
    session.run()


if __name__ == "__main__":
    main()
