"""UI automation tool — drive native desktop apps and capture the result.

Actions:
- list_windows: enumerate visible top-level windows (process name + title)
- capture: bring a window to foreground (optional), optionally send keystrokes,
  then capture the screen / window / region to a PNG file
- keys: bring a window to foreground and send keystrokes (no capture)
- click: bring a window to foreground and click (window center or coordinates)

Windows backend uses a one-shot PowerShell script (proven pattern from the
build-screenshots session: Get-Process → SetForegroundWindow → SendKeys →
CopyFromScreen). macOS uses osascript + screencapture. Linux uses xdotool +
maim/scrot (X11 only; Wayland is explicitly unsupported).

Captured PNGs compose with the image_analysis tool — this tool never analyzes
images itself.
"""

import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime

from ._config import DEFAULT_CONFIG


def _platform():
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


# mouse_event flags: left 0x0002/0x0004, right 0x0008/0x0010, middle 0x0020/0x0040
_MOUSE_FLAGS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}


class UiAutomationTool:
    name = "ui_automation"
    description = (
        "Automate native desktop apps: list windows, focus a window, send keystrokes, "
        "click, and capture the screen/window/region to a PNG file."
    )
    system_prompt = """## ui_automation

Automate native desktop applications (NOT web pages — use the browser tool for those).
Actions:
- list_windows: enumerate visible top-level windows (process name + title). Read-only.
- capture: focus a window (optional), optionally send keystrokes, then capture
  screen / window / region to a PNG. Auto-safe without keys; requires approval with keys.
- keys: focus a window and send keystrokes (no capture). Requires approval.
- click: focus a window and click (window center or x/y coordinates). Requires approval.

Typical flow: list_windows → capture (with optional keys) → image_analysis on the PNG.
The capture action supports an optional `keys` param so focus → type → settle → capture
happens in a single invocation, avoiding focus races between separate calls.

DIALOGS (Save As, Open, etc.): a dialog is a separate window owned by the main one —
process-based targeting cannot see it. Use the foreground-relative pattern instead:
1. keys: send the dialog-opening keystroke (e.g. "^s" to the app's process)
2. capture target=foreground → image_analysis to SEE the dialog
3. keys WITHOUT process (goes to foreground = the dialog): type into it, e.g. "hello.txt{ENTER}"
4. capture target=foreground again to verify the dialog closed / state changed
Never assume a dialog's layout — always capture foreground and look before typing.

Parameters (JSON object):
- action (string, optional, default "capture"): "list_windows" | "capture" | "keys" | "click"
- target (string, optional, default "screen"): "screen" | "window" | "region" | "foreground" (capture only).
  "foreground" captures whatever window is currently on top — use it for dialogs (Save As, Open, etc.),
  which are separate HWNDs not reachable via target=window+process.
- process (string, optional): process name to focus (e.g. "mm"). Required for window-targeted actions.
- keys (string, optional): keystrokes to send after focusing. SendKeys syntax on Windows
  (e.g. "hello", "{ENTER}", "{INS}", "^s" for Ctrl+S). Max 200 chars.
- click (object, optional): {"x": int, "y": int, "button": "left"|"right"|"middle"} or
  {"process": "name", "button": "left"} — click window center or absolute coordinates.
- delay_ms (integer, optional, default 800): settle delay after focus and after keys.
- region (object, optional): {"x": int, "y": int, "width": int, "height": int} for target=region.
- path (string, optional): output PNG path. Defaults to .uhu/.cache/ui_automation_<ts>.png

Examples:
- {"action": "list_windows"}
- {"action": "capture", "target": "window", "process": "mm"}
- {"action": "capture", "target": "window", "process": "mm", "keys": "hello{ENTER}world"}
- {"action": "keys", "process": "mm", "keys": "^s"}
- {"action": "click", "click": {"process": "mm", "button": "left"}}"""
    parameters = {
        "action": {"type": "string", "required": False, "description": "list_windows | capture | keys | click"},
        "target": {"type": "string", "required": False, "description": "screen | window | region (capture only)"},
        "process": {"type": "string", "required": False, "description": "Process name to focus"},
        "keys": {"type": "string", "required": False, "description": "Keystrokes to send after focusing"},
        "click": {"type": "object", "required": False, "description": "Click spec: {x,y,button} or {process,button}"},
        "delay_ms": {"type": "integer", "required": False, "description": "Settle delay in ms (default 800)"},
        "region": {"type": "object", "required": False, "description": "Region spec: {x,y,width,height}"},
        "path": {"type": "string", "required": False, "description": "Output PNG path"},
    }

    def __init__(self, config=None):
        self.config = config or DEFAULT_CONFIG

    # ── Config helpers ────────────────────────────────────────────────
    def _cfg(self, key, default):
        section = self.config.get("tools", {}).get("ui_automation", {})
        return section.get(key, default)

    # ── Validation ─────────────────────────────────────────────────────
    def _validate(self, params):
        action = params.get("action", "capture")
        if action not in ("list_windows", "capture", "keys", "click"):
            return None, f"Error: unknown action '{action}'. Use list_windows, capture, keys, or click."
        if action == "keys" and not params.get("keys"):
            return None, "Error: 'keys' action requires a 'keys' parameter."
        if action == "click" and not params.get("click"):
            return None, "Error: 'click' action requires a 'click' parameter."
        if action == "capture":
            target = params.get("target", "screen")
            if target not in ("screen", "window", "region", "foreground"):
                return None, f"Error: unknown target '{target}'. Use screen, window, region, or foreground."
            if target == "window" and not params.get("process"):
                return None, "Error: target=window requires a 'process' parameter."
            if target == "region":
                region = params.get("region")
                if not isinstance(region, dict) or not all(k in region for k in ("x", "y", "width", "height")):
                    return None, "Error: target=region requires a 'region' parameter: {x, y, width, height}."
        max_keys = int(self._cfg("max_keys_length", 200))
        keys = params.get("keys")
        if keys is not None and len(keys) > max_keys:
            return None, f"Error: 'keys' exceeds max length {max_keys} (got {len(keys)})."
        return action, None

    # ── Output path ────────────────────────────────────────────────────
    def _output_path(self, params, workdir):
        path = params.get("path")
        if path:
            full = os.path.join(workdir, path) if not os.path.isabs(path) else path
            parent = os.path.dirname(full)
            if parent:
                os.makedirs(parent, exist_ok=True)
            return full
        out_dir = self._cfg("output_dir", ".uhu/.cache")
        if not os.path.isabs(out_dir):
            out_dir = os.path.join(workdir, out_dir)
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(out_dir, f"ui_automation_{ts}.png")

    # ── Windows backend ────────────────────────────────────────────────
    def _ps_script(self, params, out_path, include_capture):
        """Build the one-shot PowerShell script for capture/keys/click."""
        target = params.get("target", "screen")
        process = params.get("process", "")
        keys = params.get("keys", "")
        delay_ms = int(params.get("delay_ms", self._cfg("default_delay_ms", 800)))
        click = params.get("click") or {}
        region = params.get("region") or {}

        def psq(s):
            # PowerShell single-quoted string: double any single quotes
            return s.replace("'", "''")

        lines = [
            "Add-Type -AssemblyName System.Windows.Forms",
            "Add-Type -AssemblyName System.Drawing",
            'Add-Type @"',
            "using System;",
            "using System.Runtime.InteropServices;",
            "public class W32 {",
            "    [DllImport(\"user32.dll\")] public static extern bool SetForegroundWindow(IntPtr h);",
            "    [DllImport(\"user32.dll\")] public static extern bool ShowWindow(IntPtr h, int n);",
            "    [DllImport(\"user32.dll\")] public static extern bool IsIconic(IntPtr h);",
            "    [DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow();",
            "    [DllImport(\"user32.dll\")] public static extern bool GetWindowRect(IntPtr h, out RECT r);",
            "    [DllImport(\"user32.dll\")] public static extern bool SetCursorPos(int x, int y);",
            "    [DllImport(\"user32.dll\")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);",
            "    [DllImport(\"user32.dll\")] public static extern bool SetProcessDPIAware();",
            "    [DllImport(\"user32.dll\")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);",
            "    public struct RECT { public int Left, Top, Right, Bottom; }",
            "}",
            '"@',
            # DPI awareness: without this, display scaling >100% makes GetWindowRect
            # and CopyFromScreen use virtualized coords → offset/blank captures
            "[void][W32]::SetProcessDPIAware()",
        ]
        if process:
            lines += [
                f"$p = Get-Process -Name '{psq(process)}' -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1",
                "if (-not $p) { Write-Output 'NOT RUNNING'; exit 1 }",
                "$h = $p.MainWindowHandle",
                "if ($h -eq [IntPtr]::Zero) { Write-Output 'NO WINDOW HANDLE'; exit 1 }",
                "if ([W32]::IsIconic($h)) { [W32]::ShowWindow($h, 9) | Out-Null }",
                "[W32]::SetForegroundWindow($h) | Out-Null",
                "Start-Sleep -Milliseconds 300",
                "# Foreground verification + one retry (Windows foreground lock)",
                "if ([W32]::GetForegroundWindow() -ne $h) {",
                "    [W32]::SetForegroundWindow($h) | Out-Null",
                "    Start-Sleep -Milliseconds 300",
                "}",
                f"Start-Sleep -Milliseconds {delay_ms}",
            ]
        if keys:
            lines += [
                f"[System.Windows.Forms.SendKeys]::SendWait('{psq(keys)}')",
                f"Start-Sleep -Milliseconds {delay_ms}",
            ]
        if click:
            if click.get("process"):
                lines += [
                    f"$cp = Get-Process -Name '{psq(click['process'])}' -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowHandle -ne 0 }} | Select-Object -First 1",
                    "if (-not $cp) { Write-Output 'NOT RUNNING'; exit 1 }",
                    "$ch = $cp.MainWindowHandle",
                    "if ($ch -eq [IntPtr]::Zero) { Write-Output 'NO WINDOW HANDLE'; exit 1 }",
                    "$r = New-Object W32+RECT",
                    "[W32]::GetWindowRect($ch, [ref]$r) | Out-Null",
                    "$cx = [int](($r.Left + $r.Right) / 2)",
                    "$cy = [int](($r.Top + $r.Bottom) / 2)",
                ]
            else:
                lines += [
                    f"$cx = {int(click.get('x', 0))}",
                    f"$cy = {int(click.get('y', 0))}",
                ]
            button = click.get("button", "left")
            down, up = _MOUSE_FLAGS.get(button, _MOUSE_FLAGS["left"])
            lines += [
                "[W32]::SetCursorPos($cx, $cy) | Out-Null",
                "Start-Sleep -Milliseconds 100",
                f"[W32]::mouse_event({down}, 0, 0, 0, [UIntPtr]::Zero)",
                f"[W32]::mouse_event({up}, 0, 0, 0, [UIntPtr]::Zero)",
                f"Start-Sleep -Milliseconds {delay_ms}",
            ]
        if include_capture:
            if target == "foreground":
                # Capture whatever window is currently on top (dialogs included)
                lines += [
                    "$fh = [W32]::GetForegroundWindow()",
                    "if ($fh -eq [IntPtr]::Zero) { Write-Output 'NO FOREGROUND WINDOW'; exit 1 }",
                    "$r = New-Object W32+RECT",
                    "[W32]::GetWindowRect($fh, [ref]$r) | Out-Null",
                    "$w = $r.Right - $r.Left",
                    "$ht = $r.Bottom - $r.Top",
                    "if ($w -le 0 -or $ht -le 0) { Write-Output 'INVALID WINDOW RECT'; exit 1 }",
                    "$bmp = New-Object System.Drawing.Bitmap $w, $ht",
                    "$g = [System.Drawing.Graphics]::FromImage($bmp)",
                    "$hdc = $g.GetHdc()",
                    "[void][W32]::PrintWindow($fh, $hdc, 2)",
                    "$g.ReleaseHdc($hdc)",
                ]
            elif target == "region":
                lines += [
                    "$rx = %d" % int(region.get("x", 0)),
                    "$ry = %d" % int(region.get("y", 0)),
                    "$rw = %d" % int(region.get("width", 0)),
                    "$rh = %d" % int(region.get("height", 0)),
                    "if ($rw -le 0 -or $rh -le 0) { Write-Output 'INVALID REGION'; exit 1 }",
                    "$bmp = New-Object System.Drawing.Bitmap $rw, $rh",
                    "$g = [System.Drawing.Graphics]::FromImage($bmp)",
                    "$g.CopyFromScreen($rx, $ry, [System.Drawing.Point]::Empty, (New-Object System.Drawing.Size $rw, $rh), [System.Drawing.CopyPixelOperation]::SourceCopy)",
                ]
            elif target == "window" and process:
                lines += [
                    "$r = New-Object W32+RECT",
                    "[W32]::GetWindowRect($h, [ref]$r) | Out-Null",
                    "$w = $r.Right - $r.Left",
                    "$ht = $r.Bottom - $r.Top",
                    "if ($w -le 0 -or $ht -le 0) { Write-Output 'INVALID WINDOW RECT'; exit 1 }",
                    "$bmp = New-Object System.Drawing.Bitmap $w, $ht",
                    "$g = [System.Drawing.Graphics]::FromImage($bmp)",
                    # PrintWindow with PW_RENDERFULLCONTENT (2): captures even occluded windows",
                    "$hdc = $g.GetHdc()",
                    "[void][W32]::PrintWindow($h, $hdc, 2)",
                    "$g.ReleaseHdc($hdc)",
                ]
            else:  # screen
                lines += [
                    "$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds",
                    "$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height",
                    "$g = [System.Drawing.Graphics]::FromImage($bmp)",
                    "$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size, [System.Drawing.CopyPixelOperation]::SourceCopy)",
                ]
            lines += [
                f"$bmp.Save('{psq(out_path)}')",
                "$g.Dispose(); $bmp.Dispose()",
                "Write-Output 'captured'",
            ]
        else:
            lines.append("Write-Output 'done'")
        return "\n".join(lines)

    def _run_ps(self, script, timeout):
        """Write script to temp file and run via powershell.exe, return (rc, stdout, stderr)."""
        fd, tmp = tempfile.mkstemp(suffix=".ps1", prefix="ui_automation_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
                # Force UTF-8 stdout so non-Latin window titles survive the pipe
                f.write("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n")
                f.write(script)
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", tmp],
                capture_output=True,
                timeout=timeout,
            )
            return (proc.returncode,
                    proc.stdout.decode("utf-8", errors="replace").strip(),
                    proc.stderr.decode("utf-8", errors="replace").strip())
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def _windows_list_windows(self, timeout):
        script = "\n".join([
            'Add-Type @"',
            "using System;",
            "using System.Text;",
            "using System.Runtime.InteropServices;",
            "public class W32 {",
            "    public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);",
            "    [DllImport(\"user32.dll\")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr l);",
            "    [DllImport(\"user32.dll\")] public static extern int GetWindowText(IntPtr h, StringBuilder sb, int max);",
            "    [DllImport(\"user32.dll\")] public static extern int GetWindowTextLength(IntPtr h);",
            "    [DllImport(\"user32.dll\")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);",
            "    [DllImport(\"user32.dll\")] public static extern bool IsWindowVisible(IntPtr h);",
            "}",
            '"@',
            "$results = New-Object System.Collections.ArrayList",
            "$proc = [W32+EnumWindowsProc] {",
            "    param($h, $l)",
            "    if (-not [W32]::IsWindowVisible($h)) { return $true }",
            "    $len = [W32]::GetWindowTextLength($h)",
            "    if ($len -le 0) { return $true }",
            "    $sb = New-Object System.Text.StringBuilder ($len + 1)",
            "    [void][W32]::GetWindowText($h, $sb, $sb.Capacity)",
            "    $title = $sb.ToString()",
            "    if (-not $title) { return $true }",
            "    $wpid = 0",
            "    [void][W32]::GetWindowThreadProcessId($h, [ref]$wpid)",
            "    $p = Get-Process -Id $wpid -ErrorAction SilentlyContinue",
            "    if ($p) { [void]$results.Add(('{0}|{1}' -f $p.ProcessName, $title)) }",
            "    return $true",
            "}",
            "[void][W32]::EnumWindows($proc, [IntPtr]::Zero)",
            "$results | ForEach-Object { Write-Output $_ }",
        ])
        rc, out, err = self._run_ps(script, timeout)
        if rc != 0:
            return f"Error listing windows: {err or out}"
        windows = []
        for line in out.splitlines():
            if "|" in line:
                name, title = line.split("|", 1)
                windows.append(f"{name}: {title}")
        if not windows:
            return "No visible windows found."
        return "Visible windows:\n" + "\n".join(windows)

    # ── macOS backend ─────────────────────────────────────────────────
    def _run_osascript(self, script, timeout):
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, timeout=timeout)
        return (proc.returncode,
                proc.stdout.decode("utf-8", errors="replace").strip(),
                proc.stderr.decode("utf-8", errors="replace").strip())

    def _macos_focus(self, process, delay_ms, timeout):
        script = f'tell application "System Events" to set frontmost of first process whose name is "{process}" to true'
        rc, out, err = self._run_osascript(script, timeout)
        if rc != 0:
            return f"Error focusing process '{process}' (may need Accessibility permission): {err or out}"
        time.sleep(delay_ms / 1000.0)
        return None

    def _macos_send_keys(self, keys, delay_ms, timeout):
        esc = keys.replace("\\", "\\\\").replace('"', '\\"')
        rc, out, err = self._run_osascript(f'tell application "System Events" to keystroke "{esc}"', timeout)
        if rc != 0:
            return f"Error sending keystrokes (may need Accessibility permission): {err or out}"
        time.sleep(delay_ms / 1000.0)
        return None

    def _macos_list_windows(self, timeout):
        rc, out, err = self._run_osascript(
            'tell application "System Events" to get name of every process whose background only is false', timeout)
        if rc != 0:
            return f"Error listing windows (may need Accessibility permission): {err or out}"
        names = [n.strip() for n in out.replace(",", "\n").split("\n") if n.strip()]
        if not names:
            return "No visible windows found."
        return "Visible windows (processes):\n" + "\n".join(names)

    def _macos_capture(self, params, out_path, timeout):
        process = params.get("process", "")
        keys = params.get("keys", "")
        delay_ms = int(params.get("delay_ms", self._cfg("default_delay_ms", 800)))
        if process:
            err = self._macos_focus(process, delay_ms, timeout)
            if err:
                return err
        if keys:
            err = self._macos_send_keys(keys, delay_ms, timeout)
            if err:
                return err
        try:
            proc = subprocess.run(["screencapture", "-x", out_path], capture_output=True, timeout=timeout)
            if proc.returncode != 0:
                return ("Error capturing (may need Screen Recording permission): "
                        + proc.stderr.decode("utf-8", errors="replace").strip())
        except FileNotFoundError:
            return "Error: screencapture not found."
        return None

    def _macos_keys(self, params, timeout):
        process = params.get("process", "")
        keys = params.get("keys", "")
        delay_ms = int(params.get("delay_ms", self._cfg("default_delay_ms", 800)))
        if process:
            err = self._macos_focus(process, delay_ms, timeout)
            if err:
                return err
        return self._macos_send_keys(keys, delay_ms, timeout)

    def _macos_click(self, params, timeout):
        click = params.get("click") or {}
        delay_ms = int(params.get("delay_ms", self._cfg("default_delay_ms", 800)))
        if click.get("process"):
            err = self._macos_focus(click["process"], delay_ms, timeout)
            if err:
                return err
        x = int(click.get("x", 0))
        y = int(click.get("y", 0))
        rc, out, err = self._run_osascript(f"tell application \"System Events\" to click at {{{x}, {y}}}", timeout)
        if rc != 0:
            return f"Error clicking (may need Accessibility permission): {err or out}"
        return None

    # ── Linux backend ──────────────────────────────────────────────────
    def _linux_wayland_error(self):
        return "Error: ui_automation on Linux is X11-only. Wayland is not supported."

    def _linux_find_window(self, process, timeout):
        """Return window id for process name, or error string."""
        try:
            proc = subprocess.run(["xdotool", "search", "--name", process],
                                  capture_output=True, timeout=timeout)
            wids = proc.stdout.decode().split()
            if not wids:
                return None, f"Error: process/window '{process}' not found."
            return wids[0], None
        except FileNotFoundError:
            return None, "Error: xdotool not found. Install it for Linux window automation (X11 only)."

    def _linux_list_windows(self, timeout):
        try:
            proc = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "."],
                                  capture_output=True, timeout=timeout)
            windows = []
            for wid in proc.stdout.decode().split()[:20]:
                p = subprocess.run(["xdotool", "getwindowname", wid], capture_output=True, timeout=timeout)
                name = p.stdout.decode().strip()
                if name:
                    windows.append(f"{wid}: {name}")
            return "Visible windows:\n" + "\n".join(windows) if windows else "No visible windows found."
        except FileNotFoundError:
            return "Error: xdotool not found. Install it for Linux window automation (X11 only)."
        except subprocess.TimeoutExpired:
            return "Error: xdotool timed out."

    def _linux_capture(self, params, out_path, timeout):
        if os.environ.get("WAYLAND_DISPLAY"):
            return self._linux_wayland_error()
        process = params.get("process", "")
        keys = params.get("keys", "")
        delay_ms = int(params.get("delay_ms", self._cfg("default_delay_ms", 800)))
        if process:
            wid, err = self._linux_find_window(process, timeout)
            if err:
                return err
            try:
                subprocess.run(["xdotool", "windowactivate", wid], capture_output=True, timeout=timeout)
                time.sleep(delay_ms / 1000.0)
            except FileNotFoundError:
                return "Error: xdotool not found."
        if keys:
            try:
                subprocess.run(["xdotool", "type", "--delay", "50", keys],
                               capture_output=True, timeout=timeout)
                time.sleep(delay_ms / 1000.0)
            except FileNotFoundError:
                return "Error: xdotool not found."
        tool = None
        for t in ("maim", "scrot"):
            try:
                subprocess.run(["which", t], capture_output=True, timeout=timeout)
                tool = t
                break
            except FileNotFoundError:
                return "Error: maim or scrot required for Linux screen capture (X11 only)."
        if not tool:
            return "Error: maim or scrot required for Linux screen capture (X11 only)."
        try:
            proc = subprocess.run([tool, out_path], capture_output=True, timeout=timeout)
            if proc.returncode != 0:
                return f"Error capturing: {proc.stderr.decode('utf-8', errors='replace').strip()}"
        except subprocess.TimeoutExpired:
            return "Error: capture timed out."
        return None

    def _linux_keys(self, params, timeout):
        if os.environ.get("WAYLAND_DISPLAY"):
            return self._linux_wayland_error()
        process = params.get("process", "")
        keys = params.get("keys", "")
        delay_ms = int(params.get("delay_ms", self._cfg("default_delay_ms", 800)))
        if process:
            wid, err = self._linux_find_window(process, timeout)
            if err:
                return err
            try:
                subprocess.run(["xdotool", "windowactivate", wid], capture_output=True, timeout=timeout)
                time.sleep(delay_ms / 1000.0)
            except FileNotFoundError:
                return "Error: xdotool not found."
        try:
            subprocess.run(["xdotool", "type", "--delay", "50", keys],
                           capture_output=True, timeout=timeout)
            time.sleep(delay_ms / 1000.0)
        except FileNotFoundError:
            return "Error: xdotool not found."
        return None

    def _linux_click(self, params, timeout):
        if os.environ.get("WAYLAND_DISPLAY"):
            return self._linux_wayland_error()
        click = params.get("click") or {}
        delay_ms = int(params.get("delay_ms", self._cfg("default_delay_ms", 800)))
        try:
            if click.get("process"):
                wid, err = self._linux_find_window(click["process"], timeout)
                if err:
                    return err
                subprocess.run(["xdotool", "windowactivate", "--sync", wid], capture_output=True, timeout=timeout)
                time.sleep(delay_ms / 1000.0)
                subprocess.run(["xdotool", "click", "--window", wid, "1"], capture_output=True, timeout=timeout)
            else:
                x = int(click.get("x", 0))
                y = int(click.get("y", 0))
                subprocess.run(["xdotool", "mousemove", str(x), str(y)], capture_output=True, timeout=timeout)
                subprocess.run(["xdotool", "click", "1"], capture_output=True, timeout=timeout)
        except FileNotFoundError:
            return "Error: xdotool not found."
        return None

    # ── Main dispatch ──────────────────────────────────────────────────
    def execute(self, params, workdir=None):
        workdir = workdir or "."
        action, err = self._validate(params)
        if err:
            return err
        timeout = int(self._cfg("timeout", 15))
        platform = _platform()

        if action == "list_windows":
            if platform == "windows":
                return self._windows_list_windows(timeout)
            if platform == "macos":
                return self._macos_list_windows(timeout)
            return self._linux_list_windows(timeout)

        if action == "capture":
            out_path = self._output_path(params, workdir)
            if platform == "windows":
                script = self._ps_script(params, out_path, include_capture=True)
                rc, out, err = self._run_ps(script, timeout)
                if rc != 0 or "NOT RUNNING" in out or "INVALID" in out:
                    return f"Error: capture failed: {out or err}"
                if not os.path.isfile(out_path):
                    return f"Error: capture did not produce {out_path}: {err or out}"
                return f"Captured to {out_path} (target: {params.get('target', 'screen')}). Use image_analysis to analyze the PNG."
            if platform == "macos":
                err = self._macos_capture(params, out_path, timeout)
                if err:
                    return err
                return f"Captured to {out_path} (target: {params.get('target', 'screen')}). Use image_analysis to analyze the PNG."
            err = self._linux_capture(params, out_path, timeout)
            if err:
                return err
            return f"Captured to {out_path} (target: {params.get('target', 'screen')}). Use image_analysis to analyze the PNG."

        if action == "keys":
            if platform == "windows":
                script = self._ps_script(params, "N/A", include_capture=False)
                rc, out, err = self._run_ps(script, timeout)
                if rc != 0 or "NOT RUNNING" in out:
                    return f"Error: keystrokes failed: {out or err}"
            elif platform == "macos":
                err = self._macos_keys(params, timeout)
                if err:
                    return err
            else:
                err = self._linux_keys(params, timeout)
                if err:
                    return err
            return f"Sent keystrokes to '{params.get('process', 'foreground window')}'"

        if action == "click":
            click = params.get("click") or {}
            click_desc = click.get("process") or f"x={click.get('x', 0)}, y={click.get('y', 0)}"
            if platform == "windows":
                script = self._ps_script(params, "N/A", include_capture=False)
                rc, out, err = self._run_ps(script, timeout)
                if rc != 0 or "NOT RUNNING" in out:
                    return f"Error: click failed: {out or err}"
            elif platform == "macos":
                err = self._macos_click(params, timeout)
                if err:
                    return err
            else:
                err = self._linux_click(params, timeout)
                if err:
                    return err
            return f"Clicked ({click_desc})"
