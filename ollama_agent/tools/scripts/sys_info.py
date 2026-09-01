#!/usr/bin/env python3
"""
Cross-platform system information script (Windows 11, macOS, Linux).
Outputs: Total/Used/Free/Reclaimable RAM (GB and %), CPU load, GPU load.

Dependencies: psutil (pip install psutil)
GPU detection is best-effort — nvidia-smi, WMI, or /sys/class/drm.
"""

import sys
import os
import re
import platform
import subprocess
import shutil

try:
    import psutil
except ImportError:
    print("ERROR: psutil is required. Install with: pip install psutil")
    sys.exit(1)

# ── Ensure UTF-8 output on Windows ──────────────────────────────────────────
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# ── Helpers ──────────────────────────────────────────────────────────────────

def bytes_to_gb(b):
    return b / (1024 ** 3)

def fmt_gb(b):
    return f"{bytes_to_gb(b):.2f}"

def fmt_pct(fraction):
    return f"{fraction * 100:.1f}%"

def run_cmd(cmd, timeout=10):
    """Run a command and return stdout, or None on failure."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           shell=isinstance(cmd, str))
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None

# ── RAM ─────────────────────────────────────────────────────────────────────

def get_ram_info():
    mem = psutil.virtual_memory()
    total = mem.total
    free = mem.free
    available = mem.available
    used = mem.used

    # Reclaimable = available - free  (cached/buffers that can be released)
    reclaimable = max(0, available - free)

    return {
        "total_gb": fmt_gb(total),
        "used_gb": fmt_gb(used),
        "used_pct": fmt_pct(used / total) if total else "0%",
        "free_gb": fmt_gb(free),
        "free_pct": fmt_pct(free / total) if total else "0%",
        "reclaimable_gb": fmt_gb(reclaimable),
        "reclaimable_pct": fmt_pct(reclaimable / total) if total else "0%",
        "available_pct": fmt_pct(available / total) if total else "0%",
        "available_gb": fmt_gb(available),
    }

# ── CPU ─────────────────────────────────────────────────────────────────────

def get_cpu_load():
    # psutil gives per-core and overall; interval=None = non-blocking
    overall = psutil.cpu_percent(interval=1)
    per_core = psutil.cpu_percent(interval=0, percpu=True)
    return {
        "overall_pct": f"{overall:.1f}%",
        "per_core_pct": [f"{c:.1f}%" for c in per_core],
        "core_count_physical": psutil.cpu_count(logical=False),
        "core_count_logical": psutil.cpu_count(logical=True),
    }

# ── GPU ──────────────────────────────────────────────────────────────────────

def get_gpu_load_nvidia_smi():
    """Try nvidia-smi for NVIDIA GPU load."""
    if not shutil.which("nvidia-smi"):
        return None

    out = run_cmd([
        "nvidia-smi",
        "--query-gpu=name,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits"
    ])
    if not out:
        return None

    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 4:
            gpus.append({
                "name": parts[0],
                "gpu_load_pct": f"{float(parts[1]):.1f}%",
                "vram_used_mb": float(parts[2]),
                "vram_total_mb": float(parts[3]),
            })
    return gpus if gpus else None


def get_gpu_load_windows_wmi():
    """Try WMI for GPU load on Windows (non-NVIDIA)."""
    try:
        import wmi
        c = wmi.WMI(namespace="root\\OpenHardwareMonitor")
        gpu_loads = []
        for sensor in c.Sensor():
            if sensor.SensorType == "Load" and "GPU" in sensor.Name:
                gpu_loads.append({
                    "name": sensor.Name,
                    "gpu_load_pct": f"{sensor.Value:.1f}%",
                })
        if gpu_loads:
            return gpu_loads
    except Exception:
        pass

    # Fallback: try generic WMI for adapter name only
    try:
        import wmi
        c = wmi.WMI()
        gpus = []
        for gpu in c.Win32_VideoController():
            gpus.append({
                "name": gpu.Name or "Unknown GPU",
                "gpu_load_pct": "N/A (no load sensor)",
            })
        return gpus if gpus else None
    except Exception:
        pass
    return None


def get_gpu_load_linux_sysfs():
    """Try /sys/class/drm for AMD/Intel GPU load on Linux."""
    gpus = []
    drm_path = "/sys/class/drm"
    if not os.path.isdir(drm_path):
        return None

    for entry in os.listdir(drm_path):
        card_dir = os.path.join(drm_path, entry, "device")
        if not entry.startswith("card") or not os.path.isdir(card_dir):
            continue

        # Try to get GPU name
        name_path = os.path.join(card_dir, "product")
        gpu_name = "Unknown GPU"
        if os.path.isfile(name_path):
            try:
                with open(name_path) as f:
                    gpu_name = f.read().strip() or gpu_name
            except Exception:
                pass

        # Try AMD GPU busy percent
        busy_path = os.path.join(drm_path, entry, "device/gpu_busy_percent")
        load = "N/A"
        if os.path.isfile(busy_path):
            try:
                with open(busy_path) as f:
                    val = f.read().strip()
                    float(val)  # validate
                    load = f"{val}%"
            except Exception:
                pass

        if load != "N/A" or gpu_name != "Unknown GPU":
            gpus.append({"name": gpu_name, "gpu_load_pct": load})

    return gpus if gpus else None


def get_gpu_load_macos():
    """Get GPU info on macOS via IOKit (no sudo) or powermetrics (sudo)."""
    # Get GPU names from system_profiler
    out = run_cmd(["system_profiler", "SPDisplaysDataType"])
    names = []
    if out:
        names = [n.strip() for n in re.findall(r"Chipset Model:\s*(.+)", out)]

    gpu_load = None
    load_source = "system_profiler"

    # ── Method 1: ioreg (no sudo, no dependencies) ──
    # Try IOGPUDevice first (Intel/older Macs)
    for ioreg_class, patterns in [
        ("IOGPUDevice", [
            (r'"PerformanceStatistics"\s*=\s*\{([^}]+)\}', [
                (r'"GPU Utilization"\s*=\s*(\d+)', "GPU Utilization"),
                (r'"gpu-utilization"\s*=\s*(\d+)', "gpu-utilization"),
                (r'"utilization"\s*=\s*(\d+)', "utilization"),
            ]),
        ]),
        ("AGXAccelerator", [
            (r'"PerformanceStatistics"\s*=\s*\{([^}]+)\}', [
                (r'"Device Utilization %"\s*=\s*(\d+)', "Device Utilization"),
                (r'"Renderer Utilization %"\s*=\s*(\d+)', "Renderer Utilization"),
                (r'"Tiler Utilization %"\s*=\s*(\d+)', "Tiler Utilization"),
                (r'"GPU Utilization"\s*=\s*(\d+)', "GPU Utilization"),
                (r'"gpu-utilization"\s*=\s*(\d+)', "gpu-utilization"),
            ]),
        ]),
    ]:
        if gpu_load is not None:
            break
        ioreg_out = run_cmd(["ioreg", "-r", "-c", ioreg_class, "-d", "3"])
        if not ioreg_out:
            continue
        for dict_pattern, sub_patterns in patterns:
            dict_match = re.search(dict_pattern, ioreg_out)
            if not dict_match:
                continue
            perf_str = dict_match.group(1)
            for val_pattern, label in sub_patterns:
                m = re.search(val_pattern, perf_str)
                if m:
                    gpu_load = float(m.group(1))
                    load_source = f"IOKit/{ioreg_class} ({label})"
                    break
            if gpu_load is not None:
                break

    # ── Method 3: powermetrics (needs sudo) ──
    if gpu_load is None:
        for cmd_prefix in (["sudo", "-n"], []):
            pm_out = run_cmd(
                cmd_prefix + ["powermetrics", "--samplers", "gpu_power", "-i", "1000", "-n", "1"],
                timeout=10,
            )
            if not pm_out:
                continue
            match = re.search(r"GPU Active Ratio:\s*([\d.]+)%", pm_out)
            if match:
                gpu_load = float(match.group(1))
                load_source = "powermetrics" + (" (sudo)" if cmd_prefix else "")
                break

    # Build result
    gpus = []
    for name in (names or ["Unknown GPU"]):
        entry = {"name": name}
        if gpu_load is not None:
            entry["gpu_load_pct"] = f"{gpu_load:.1f}%"
        else:
            entry["gpu_load_pct"] = "N/A (run with sudo for GPU load)"
        gpus.append(entry)

    return gpus, load_source


def get_gpu_load():
    """Best-effort GPU load detection across platforms."""
    # 1. Try nvidia-smi (all platforms)
    result = get_gpu_load_nvidia_smi()
    if result:
        return result, "nvidia-smi"

    # 2. Platform-specific fallbacks
    system = platform.system()
    if system == "Linux":
        result = get_gpu_load_linux_sysfs()
        if result:
            return result, "/sys/class/drm"
    elif system == "Windows":
        result = get_gpu_load_windows_wmi()
        if result:
            return result, "WMI"
    elif system == "Darwin":
        result, source = get_gpu_load_macos()
        return result, source

    return [{"name": "No GPU detected", "gpu_load_pct": "N/A"}], "none"

# ── Top Processes ───────────────────────────────────────────────────────────

def get_top_processes_cpu(n=5, interval=1.0):
    """Get top N processes by CPU usage (1-second sample)."""
    procs = []
    # First pass: initialize cpu_percent
    for p in psutil.process_iter(['pid', 'name']):
        try:
            p.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    # Sample over interval
    psutil.cpu_percent(interval=interval)
    for p in psutil.process_iter(['pid', 'name']):
        try:
            cpu = p.cpu_percent(interval=None)
            procs.append({'pid': p.pid, 'name': p.info['name'], 'cpu_pct': cpu})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda x: x['cpu_pct'], reverse=True)
    return procs[:n]


def get_top_processes_ram(n=5):
    """Get top N processes by RAM usage."""
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'memory_percent']):
        try:
            mem = p.memory_percent()
            procs.append({'pid': p.pid, 'name': p.info['name'], 'mem_pct': mem,
                         'mem_mb': p.memory_info().rss / (1024 * 1024)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda x: x['mem_pct'], reverse=True)
    return procs[:n]


def get_top_processes_gpu(n=5):
    """Get top N processes by GPU usage (NVIDIA only via nvidia-smi)."""
    if not shutil.which("nvidia-smi"):
        return None

    out = run_cmd([
        "nvidia-smi",
        "--query-compute-apps=pid,gpu_uuid,used_gpu_memory",
        "--format=csv,noheader,nounits"
    ])
    if not out:
        return None

    procs = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3:
            try:
                pid = int(parts[0])
                # Get process name from pid
                name = "unknown"
                try:
                    name = psutil.Process(pid).name()
                except Exception:
                    pass
                procs.append({
                    'pid': pid,
                    'name': name,
                    'gpu_mem_mb': float(parts[2]),
                })
            except (ValueError, IndexError):
                pass

    procs.sort(key=lambda x: x.get('gpu_mem_mb', 0), reverse=True)
    return procs[:n] if procs else None


# ── Display ─────────────────────────────────────────────────────────────────

def display_all():
    print("=" * 60)
    print(f"  System Info — {platform.system()} {platform.release()}")
    print(f"  Host: {platform.node()} | Python {platform.python_version()}")
    print("=" * 60)

    # RAM
    ram = get_ram_info()
    print("\n── Memory (RAM) ──")
    print(f"  Total RAM:         {ram['total_gb']} GB")
    print(f"  Used RAM:          {ram['used_gb']} GB  ({ram['used_pct']})")
    print(f"  Free RAM:          {ram['free_gb']} GB  ({ram['free_pct']})")
    print(f"  Reclaimable RAM:   {ram['reclaimable_gb']} GB  ({ram['reclaimable_pct']})")
    print(f"  Available RAM:     {ram['available_gb']} GB  ({ram['available_pct']}, free + reclaimable)")

    # CPU
    cpu = get_cpu_load()
    print("\n── CPU ──")
    print(f"  CPU Load:          {cpu['overall_pct']}")
    print(f"  Physical Cores:    {cpu['core_count_physical']}")
    print(f"  Logical Cores:     {cpu['core_count_logical']}")
    print(f"  Per-Core Load:     {', '.join(cpu['per_core_pct'])}")

    # GPU
    gpus, method = get_gpu_load()
    print(f"\n── GPU (source: {method}) ──")
    for i, gpu in enumerate(gpus):
        label = f"  GPU {i}" if len(gpus) > 1 else "  GPU"
        name = gpu.get("name", "Unknown")
        load = gpu.get("gpu_load_pct", "N/A")
        line = f"{label}: {name} — Load: {load}"
        if "vram_total_mb" in gpu:
            vram_pct = f"{gpu['vram_used_mb'] / gpu['vram_total_mb'] * 100:.1f}%"
            line += f" | VRAM: {gpu['vram_used_mb']:.0f}/{gpu['vram_total_mb']:.0f} MB ({vram_pct})"
        print(line)

    # Top processes
    print("\n── Top Processes by CPU ──")
    top_cpu = get_top_processes_cpu(n=5)
    for p in top_cpu:
        print(f"  {p['pid']:>7}  {p['cpu_pct']:6.1f}%  {p['name']}")

    print("\n── Top Processes by RAM ──")
    top_ram = get_top_processes_ram(n=5)
    for p in top_ram:
        print(f"  {p['pid']:>7}  {p['mem_pct']:6.1f}%  {p['mem_mb']:7.1f} MB  {p['name']}")

    top_gpu = get_top_processes_gpu(n=5)
    if top_gpu:
        print("\n── Top Processes by GPU Memory ──")
        for p in top_gpu:
            print(f"  {p['pid']:>7}  {p['gpu_mem_mb']:7.0f} MB  {p['name']}")

    print("\n" + "=" * 60)


def collect_all():
    """Collect all system info as a dict (for JSON output)."""
    data = {
        "platform": f"{platform.system()} {platform.release()}",
        "host": platform.node(),
        "python": platform.python_version(),
    }
    data["ram"] = get_ram_info()
    data["cpu"] = get_cpu_load()
    gpus, method = get_gpu_load()
    data["gpu"] = {"source": method, "gpus": gpus}
    data["top_processes_cpu"] = get_top_processes_cpu(n=5)
    data["top_processes_ram"] = get_top_processes_ram(n=5)
    top_gpu = get_top_processes_gpu(n=5)
    if top_gpu:
        data["top_processes_gpu"] = top_gpu
    return data


def display_json():
    """Output all system info as JSON (UTF-8 safe)."""
    import json
    data = collect_all()
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if "--json" in sys.argv:
        display_json()
    else:
        display_all()
