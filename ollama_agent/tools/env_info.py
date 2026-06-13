"""Environment info tool: system, Python, and installed package information."""

import os
import platform
import subprocess
import sys


class EnvInfoTool:
    """Return system, Python, and installed package information."""
    name = "env_info"
    description = "Return system, Python, and installed package information."
    system_prompt = (
        "## env_info\n"
        "Return system, Python, and installed package information.\n"
        "Parameters (JSON object):\n"
        "- packages (boolean, optional, default true): Include installed pip packages\n"
        "- check (string, optional): Check if a specific package is importable and return its version\n"
        "Use this to understand the runtime environment before writing code that depends on specific versions."
    )
    parameters = {
        "packages": {
            "type": "boolean",
            "description": "Include installed pip packages (default true)",
            "required": False,
        },
        "check": {
            "type": "string",
            "description": "Check if a specific package is importable and return its version",
            "required": False,
        },
    }

    def execute(self, params, workdir=".", **kwargs):
        include_packages = params.get("packages", True)
        check_module = params.get("check", "")

        # If checking a specific module
        if check_module:
            return self._check_module(check_module)

        # General environment info
        info = []
        info.append(f"Platform: {platform.system()} {platform.release()} ({platform.machine()})")
        info.append(f"OS: {platform.platform()}")
        info.append(f"Python: {sys.version}")
        info.append(f"Python path: {sys.executable}")
        info.append(f"CWD: {os.getcwd()}")
        info.append(f"Workdir: {workdir}")

        # Android / JDK environment
        try:
            from .android_build import _find_android_jdk, _find_gradlew
            jdk_path = _find_android_jdk()
            info.append("")
            info.append("Android / JDK:")
            if jdk_path:
                info.append(f"  Android Studio JDK: {jdk_path}")
            else:
                info.append(f"  Android Studio JDK: not found")
            java_home = os.environ.get("JAVA_HOME", "")
            if java_home:
                info.append(f"  JAVA_HOME: {java_home}")
            else:
                info.append(f"  JAVA_HOME: not set")
            gradle_local = os.environ.get("GRADLE_LOCAL_JAVA_HOME", "")
            if gradle_local:
                info.append(f"  GRADLE_LOCAL_JAVA_HOME: {gradle_local}")
            gradlew = _find_gradlew(workdir)
            if gradlew:
                info.append(f"  Gradle wrapper: {os.path.join(gradlew[0], gradlew[1])}")
            android_home = os.environ.get("ANDROID_HOME", os.environ.get("ANDROID_SDK_ROOT", ""))
            if android_home:
                info.append(f"  ANDROID_HOME: {android_home}")
        except Exception:
            pass

        # Encoding
        info.append(f"Default encoding: {sys.getdefaultencoding()}")
        info.append(f"Filesystem encoding: {sys.getfilesystemencoding()}")

        # Shell info
        if sys.platform == "win32":
            try:
                import ctypes
                oem_cp = ctypes.windll.kernel32.GetOEMCP()
                info.append(f"OEM codepage: {oem_cp}")
            except Exception:
                pass
            # Check if key env vars are inherited
            missing_env = []
            for var in ("JAVA_HOME", "GRADLE_LOCAL_JAVA_HOME", "ANDROID_HOME", "ANDROID_SDK_ROOT"):
                if not os.environ.get(var):
                    missing_env.append(var)
            if missing_env:
                info.append(f"  Note: env vars not inherited by shell sandbox: {', '.join(missing_env)}")

        # Key packages
        key_packages = [
            "ollama", "requests", "httpx", "aiohttp",
            "numpy", "pandas", "flask", "fastapi", "django",
            "sqlalchemy", "pydantic", "click", "rich",
        ]
        available = []
        for pkg in key_packages:
            ver = self._get_version(pkg)
            if ver:
                available.append(f"  {pkg}: {ver}")
        if available:
            info.append("Key packages:")
            info.extend(available)

        # Full pip list if requested
        if include_packages:
            try:
                import importlib.metadata
                dists = sorted(
                    importlib.metadata.distributions(),
                    key=lambda d: d.metadata["Name"].lower()
                )
                pkg_list = [f"  {d.metadata['Name']}=={d.metadata['Version']}" for d in dists]
                if pkg_list:
                    info.append(f"Installed packages ({len(pkg_list)}):")
                    info.extend(pkg_list)
            except Exception:
                pass

        return "\n".join(info)

    def _check_module(self, module_name):
        """Check if a module is importable and return its version."""
        try:
            mod = __import__(module_name)
            version = getattr(mod, "__version__", "unknown")
            location = getattr(mod, "__file__", "built-in")
            return f"Module '{module_name}': available\n  Version: {version}\n  Location: {location}"
        except ImportError:
            # Try pip metadata as fallback
            try:
                import importlib.metadata
                dist = importlib.metadata.distribution(module_name)
                return f"Module '{module_name}': installed (pip)\n  Version: {dist.metadata['Version']}\n  Location: {dist._path}"
            except Exception:
                return f"Module '{module_name}': NOT available"

    def _get_version(self, package_name):
        """Get version of a package if installed."""
        try:
            import importlib.metadata
            return importlib.metadata.version(package_name)
        except Exception:
            return None
