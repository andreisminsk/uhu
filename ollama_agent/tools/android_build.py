"""Android build tool: set up JDK environment and run Gradle builds."""

import os
import subprocess
import sys


# Known Android Studio JDK locations (Windows)
_ANDROID_JDK_PATHS_WIN = [
    r"C:\Program Files\Android\Android Studio\jbr",
    r"C:\Program Files\Android\Android Studio\jre",
]

# Known Android Studio JDK locations (macOS)
_ANDROID_JDK_PATHS_MAC = [
    "/Applications/Android Studio.app/Contents/jbr/Contents/Home",
    "/Applications/Android Studio.app/Contents/jre/Contents/Home",
]

# Known Android Studio JDK locations (Linux)
_ANDROID_JDK_PATHS_LINUX = [
    "/opt/android-studio/jbr",
    os.path.expanduser("~/android-studio/jbr"),
]


def _find_android_jdk():
    """Find Android Studio bundled JDK. Returns path or None."""
    if sys.platform == "win32":
        paths = _ANDROID_JDK_PATHS_WIN
    elif sys.platform == "darwin":
        paths = _ANDROID_JDK_PATHS_MAC
    else:
        paths = _ANDROID_JDK_PATHS_LINUX

    for p in paths:
        if os.path.isdir(p):
            return p
    return None


def _find_gradlew(workdir):
    """Find gradlew/gradlew.bat in workdir or parents. Returns (dir, script_name) or None."""
    script = "gradlew.bat" if sys.platform == "win32" else "gradlew"
    d = os.path.abspath(workdir)
    for _ in range(10):  # walk up max 10 levels
        candidate = os.path.join(d, script)
        if os.path.isfile(candidate):
            return d, script
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def _make_env(jdk_path):
    """Build environment dict with JAVA_HOME set and JDK on PATH."""
    env = os.environ.copy()
    if jdk_path:
        env["JAVA_HOME"] = jdk_path
        jdk_bin = os.path.join(jdk_path, "bin")
        env["PATH"] = jdk_bin + os.pathsep + env.get("PATH", "")
    return env


class AndroidBuildTool:
    """Set up Android build environment and run Gradle commands.

    Handles JDK detection (Android Studio bundled JDK), environment
    setup (JAVA_HOME, PATH), and Gradle execution with error filtering.
    """
    name = "android_build"
    description = "Set up Android build environment and run Gradle commands."
    system_prompt = (
        "## android_build\n"
        "Set up Android build environment and run Gradle commands.\n"
        "Handles JDK detection (Android Studio bundled JDK), environment setup "
        "(JAVA_HOME, PATH), and Gradle execution with error filtering.\n\n"
        "Actions and parameters:\n\n"
        "### detect\n"
        "Detect Android build environment (JDK, Gradle, Android SDK).\n"
        "```json\n"
        '{"action": "detect"}\n'
        "```\n"
        "No parameters. Returns JDK path, Gradle availability, Android SDK info.\n\n"
        "### run\n"
        "Run a Gradle command with proper JDK environment.\n"
        "```json\n"
        '{"action": "run", "task": ":app:compileDebugKotlin", "args": "--no-daemon"}\n'
        "```\n"
        "- task (string, required): Gradle task(s) to run\n"
        "- args (string, optional): Additional Gradle flags (default: '--no-daemon')\n"
        "- filter (string, optional): Regex pattern to filter output lines\n"
        "- timeout (integer, optional, default 300): Timeout in seconds\n\n"
        "### script\n"
        "Generate a PowerShell or shell script for building.\n"
        "```json\n"
        '{"action": "script", "task": ":app:compileDebugKotlin", "args": "--no-daemon"}\n'
        "```\n"
        "- task (string, required): Gradle task(s)\n"
        "- args (string, optional): Additional flags (default: '--no-daemon')\n"
        "- output (string, optional): Script file path\n\n"
        "When the user says 'build Android', 'run Gradle', 'compile Kotlin' — use detect first, then run.\n"
        "When the user says 'create build script' — use script."
    )
    parameters = {
        "action": {
            "type": "string",
            "description": "Action: detect, run, or script",
            "required": True,
        },
        "task": {
            "type": "string",
            "description": "Gradle task(s) to run (e.g. ':app:compileDebugKotlin')",
            "required": False,
        },
        "args": {
            "type": "string",
            "description": "Additional Gradle flags (default: --no-daemon)",
            "required": False,
        },
        "filter": {
            "type": "string",
            "description": "Regex pattern to filter output lines (e.g. 'error:|e: file|BUILD |FAIL')",
            "required": False,
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds (default 300)",
            "required": False,
        },
        "output": {
            "type": "string",
            "description": "Output script file path (for action=script)",
            "required": False,
        },
    }

    def execute(self, params, workdir=".", **kwargs):
        action = params.get("action", "detect")
        if action == "detect":
            return self._detect(workdir)
        elif action == "run":
            return self._run(params, workdir)
        elif action == "script":
            return self._script(params, workdir)
        else:
            return f"Unknown action: {action}. Use detect, run, or script."

    def _detect(self, workdir):
        """Detect Android build environment."""
        lines = ["Android Build Environment Detection", "=" * 40]

        # JDK detection
        jdk_path = _find_android_jdk()
        java_home = os.environ.get("JAVA_HOME", "")
        gradle_local_java = os.environ.get("GRADLE_LOCAL_JAVA_HOME", "")

        lines.append("")
        lines.append("JDK:")
        if jdk_path:
            lines.append(f"  Android Studio JDK: {jdk_path} [FOUND]")
        else:
            lines.append("  Android Studio JDK: not found at known paths")

        if java_home:
            lines.append(f"  JAVA_HOME (env): {java_home}")
            java_bin = os.path.join(java_home, "bin", "java.exe" if sys.platform == "win32" else "java")
            if os.path.isfile(java_bin):
                lines.append(f"    java binary: [FOUND]")
            else:
                lines.append(f"    java binary: NOT FOUND at {java_bin}")
        else:
            lines.append("  JAVA_HOME (env): not set")

        if gradle_local_java:
            lines.append(f"  GRADLE_LOCAL_JAVA_HOME: {gradle_local_java}")
        else:
            lines.append("  GRADLE_LOCAL_JAVA_HOME: not set")

        # Check java on PATH
        java_on_path = None
        for d in os.environ.get("PATH", "").split(os.pathsep):
            candidate = os.path.join(d, "java.exe" if sys.platform == "win32" else "java")
            if os.path.isfile(candidate):
                java_on_path = candidate
                break
        if java_on_path:
            lines.append(f"  java on PATH: {java_on_path}")
        else:
            lines.append("  java on PATH: not found")

        # Gradle detection
        lines.append("")
        lines.append("Gradle:")
        gradlew_info = _find_gradlew(workdir)
        if gradlew_info:
            gradle_dir, script = gradlew_info
            lines.append(f"  Gradle wrapper: {os.path.join(gradle_dir, script)} [FOUND]")
        else:
            lines.append("  Gradle wrapper: not found in workdir or parents")

        # Android SDK
        lines.append("")
        lines.append("Android SDK:")
        android_home = os.environ.get("ANDROID_HOME", os.environ.get("ANDROID_SDK_ROOT", ""))
        if android_home:
            lines.append(f"  ANDROID_HOME: {android_home}")
            if os.path.isdir(android_home):
                lines.append(f"    [EXISTS]")
                platforms_dir = os.path.join(android_home, "platforms")
                if os.path.isdir(platforms_dir):
                    platforms = os.listdir(platforms_dir)
                    lines.append(f"    platforms: {', '.join(platforms[:5])}")
            else:
                lines.append(f"    [PATH DOES NOT EXIST]")
        else:
            lines.append("  ANDROID_HOME: not set")

        # Recommendation
        lines.append("")
        lines.append("Recommendation:")
        if jdk_path and not java_home:
            lines.append(f"  Set JAVA_HOME={jdk_path} before running Gradle")
            lines.append(f"  Use action=run or action=script to auto-configure")
        elif jdk_path and java_home:
            lines.append(f"  JAVA_HOME is set but may differ from Android Studio JDK")
            lines.append(f"  Current: {java_home}")
            lines.append(f"  Android Studio: {jdk_path}")
        elif not jdk_path and not java_home:
            lines.append(f"  No JDK found — install Android Studio or a JDK")

        return "\n".join(lines)

    def _run(self, params, workdir):
        """Run a Gradle command with proper JDK environment."""
        task = params.get("task", "")
        if not task:
            return "Error: 'task' parameter is required for action=run"
        args = params.get("args", "--no-daemon")
        filter_pattern = params.get("filter", "")
        timeout = params.get("timeout", 300)

        jdk_path = _find_android_jdk() or os.environ.get("JAVA_HOME")
        env = _make_env(jdk_path)

        gradlew_info = _find_gradlew(workdir)
        if not gradlew_info:
            return "Error: gradlew not found in workdir or parent directories"

        gradle_dir, script = gradlew_info
        cmd = [os.path.join(gradle_dir, script)]
        if task:
            cmd.append(task)
        if args:
            cmd.extend(args.split())

        try:
            result = subprocess.run(
                cmd,
                cwd=workdir,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"Gradle command timed out after {timeout}s\nTask: {task}"

        output = result.stdout or ""
        stderr = result.stderr or ""

        # Filter output if requested
        if filter_pattern:
            import re
            pattern = re.compile(filter_pattern, re.IGNORECASE)
            filtered = [line for line in output.splitlines() if pattern.search(line)]
            if stderr:
                for line in stderr.splitlines():
                    if pattern.search(line):
                        filtered.append(line)
            display = "\n".join(filtered)
            if not display:
                display = f"(no lines matched filter '{filter_pattern}', build may have succeeded)\nExit code: {result.returncode}"
            else:
                display += f"\n\n[Filtered {len(filtered)}/{len(output.splitlines())} lines, exit code: {result.returncode}]"
        else:
            # Truncate large output
            display = output
            if len(display) > 8000:
                display = display[:8000] + f"\n... ({len(output) - 8000} more chars)"
            if result.returncode != 0 and stderr:
                display += f"\n\nSTDERR:\n{stderr[:3000]}"
            display += f"\n\n[Exit code: {result.returncode}]"

        return display

    def _script(self, params, workdir):
        """Generate a build script with proper environment setup."""
        task = params.get("task", "")
        if not task:
            return "Error: 'task' parameter is required for action=script"
        args = params.get("args", "--no-daemon")
        output_path = params.get("output", "")

        jdk_path = _find_android_jdk()
        gradlew_info = _find_gradlew(workdir)
        if not gradlew_info:
            return "Error: gradlew not found in workdir or parent directories"

        gradle_dir, script = gradlew_info

        if sys.platform == "win32":
            if not output_path:
                output_path = "build_android.ps1"
            jdk = jdk_path or r"C:\Program Files\Android\Android Studio\jbr"
            content = (
                f"$env:JAVA_HOME = '{jdk}'\n"
                f"$env:Path = $env:JAVA_HOME + '\\bin;' + $env:Path\n"
                f"& '{os.path.join(gradle_dir, script)}' {task} {args}\n"
            )
        else:
            if not output_path:
                output_path = "build_android.sh"
            jdk = jdk_path or "/opt/android-studio/jbr"
            content = (
                f"#!/bin/bash\n"
                f"export JAVA_HOME='{jdk}'\n"
                f"export PATH=\"$JAVA_HOME/bin:$PATH\"\n"
                f"./{script} {task} {args}\n"
            )

        full_path = os.path.join(workdir, output_path)
        with open(full_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

        return f"Build script written to {full_path}\nJDK: {jdk}\nTask: {task} {args}"
