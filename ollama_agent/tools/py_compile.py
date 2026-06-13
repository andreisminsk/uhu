"""Python compile/import/check tool — replaces python -c one-liners with an auto-approvable tool."""

import os
import sys
import traceback


class PyCompileTool:
    name = "py_compile"
    description = "Check Python syntax, import modules, or run Python expressions"
    system_prompt = (
        "## py_compile\n"
        "Check Python syntax, import modules, or run Python expressions.\n"
        "ALWAYS prefer this over RUN with `python -c '...'` — it is auto-approvable and cross-platform.\n"
        "Parameters (JSON object):\n"
        "- action (string, required): One of:\n"
        "    'syntax' — check syntax of a file (no execution)\n"
        "    'import' — import a module and report success or error\n"
        "    'run' — run a Python expression and return the result\n"
        "- path (string): File path for 'syntax' action\n"
        "- module (string): Module name(s) for 'import' action:\n"
        "      Single: 'ollama_agent.parser'\n"
        "      Multiple (comma-separated): 'ollama_agent.parser,ollama_agent.session'\n"
        "      From-style: 'from ollama_agent.parser import parse_actions'\n"
        "- code (string): Python code for 'run' action\n"
        "- workdir (string, optional): Working directory for 'run' action\n"
    )

    def execute(self, params, workdir=None):
        action = params.get("action", "")
        if action == "syntax":
            return self._check_syntax(params, workdir)
        elif action == "import":
            return self._check_import(params, workdir)
        elif action == "run":
            return self._run_code(params, workdir)
        else:
            return (f"Error: Unknown action '{action}'. "
                    f"Use 'syntax', 'import', or 'run'.")

    def _check_syntax(self, params, workdir=None):
        """Check Python syntax of a file without executing it."""
        path = params.get("path", "")
        if not path:
            return "Error: 'path' is required for syntax check"

        full_path = os.path.join(workdir, path) if workdir and not os.path.isabs(path) else path
        if not os.path.isfile(full_path):
            return f"Error: File not found: {path}"

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
        except Exception as e:
            return f"Error reading file: {e}"

        import py_compile
        try:
            py_compile.compile(full_path, doraise=True)
            return f"[OK] {path}: syntax check passed"
        except py_compile.PyCompileError as e:
            return f"[FAIL] {path}: {e}"

    def _check_import(self, params, workdir=None):
        """Import a module and report success or error.
        
        Supports multiple import patterns:
        - Single module: 'ollama_agent.parser'
        - Multiple modules (comma-separated): 'ollama_agent.parser,ollama_agent.session'
        - From-style imports: 'from ollama_agent.parser import parse_actions'
        """
        module = params.get("module", "")
        if not module:
            return "Error: 'module' is required for import check"

        # Add workdir to sys.path so local modules can be imported
        added_path = None
        if workdir and workdir not in sys.path:
            sys.path.insert(0, workdir)
            added_path = workdir

        try:
            results = []
            # Support comma-separated modules for batch checking
            modules_to_check = [m.strip() for m in module.split(",") if m.strip()]
            
            for mod in modules_to_check:
                if mod.startswith("from "):
                    # Handle 'from module import something' style
                    try:
                        exec(mod)
                        results.append(f"[OK] import: {mod}")
                    except Exception as e:
                        results.append(f"[FAIL] import: {mod} - {type(e).__name__}: {e}")
                else:
                    # Handle regular 'import module' style
                    try:
                        __import__(mod)
                        results.append(f"[OK] import {mod}: success")
                    except Exception as e:
                        results.append(f"[FAIL] import {mod}: {type(e).__name__}: {e}")
            
            return "\n".join(results)
        finally:
            if added_path and added_path in sys.path:
                sys.path.remove(added_path)

    def _run_code(self, params, workdir=None):
        """Run a Python expression and return the result."""
        code = params.get("code", "")
        if not code:
            return "Error: 'code' is required for run action"

        # Add workdir to sys.path so local modules can be imported
        added_path = None
        if workdir and workdir not in sys.path:
            sys.path.insert(0, workdir)
            added_path = workdir

        # Save and restore cwd
        old_cwd = os.getcwd()
        if workdir:
            os.chdir(workdir)

        # Capture stdout
        import io
        import contextlib

        output = io.StringIO()
        result_var = {}

        try:
            with contextlib.redirect_stdout(output):
                # Try eval first (expressions), then exec (statements)
                try:
                    result_var["value"] = eval(code)
                    if result_var["value"] is not None:
                        out = output.getvalue()
                        if out:
                            return out.rstrip()
                        return str(result_var["value"])
                    return output.getvalue().rstrip() or "[OK] (no output)"
                except SyntaxError:
                    exec(code)
                    return output.getvalue().rstrip() or "[OK] (no output)"
        except Exception:
            tb = traceback.format_exc()
            # Trim traceback to keep it concise
            lines = tb.splitlines()
            if len(lines) > 15:
                lines = lines[:5] + ["..."] + lines[-5:]
            return f"[FAIL] {chr(10).join(lines)}"
        finally:
            os.chdir(old_cwd)
            if added_path and added_path in sys.path:
                sys.path.remove(added_path)
