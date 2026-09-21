#!/usr/bin/env python3
"""
Cross-platform system information script (Windows 11, macOS, Linux).
Outputs: Total/Used/Free/Reclaimable RAM (GB and %), CPU load, GPU load, disk space,
container/cgroup limits (Linux).

Dependencies: psutil (pip install psutil)
GPU detection is best-effort — nvidia-smi, WMI, or /sys/class/drm.
"""

import sys
import os
import re
import platform
import subprocess
import shutil
import time

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


def _ioreg_gpu_sample():
    """One ioreg pass (no sudo): returns (gpu_load, source) or (None, None)."""
    # Try IOGPUDevice first (Intel/older Macs), then AGXAccelerator (Apple Silicon)
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
                    return float(m.group(1)), f"IOKit/{ioreg_class} ({label})"
    return None, None


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
    # GPU load is bursty — a single instantaneous read usually catches 0
    # between short render/compute spikes. Sample several times over ~1 s
    # (mirroring the 1 s CPU sampling window) and keep the peak.
    for _ in range(5):
        load, src = _ioreg_gpu_sample()
        if load is not None and (gpu_load is None or load > gpu_load):
            gpu_load, load_source = load, src
        time.sleep(0.2)

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


def _get_phys_footprint_macos(pid):
    """Get phys_footprint for a process on macOS (matches Activity Monitor).

    Uses proc_pid_rusage with RUSAGE_INFO_V4. The rusage_info_v4 struct has:
      offset 0-15:  ri_uuid (16 bytes)
      offset 16:    ri_user_time
      offset 24:    ri_system_time
      offset 32:    ri_pkg_idle_wkups
      offset 40:    ri_pkg_nonidle_wkups
      offset 48:    ri_pageins
      offset 56:    ri_wired_size
      offset 64:    ri_resident_size
      offset 72:    ri_phys_footprint  <-- this is what Activity Monitor shows
    phys_footprint includes compressed memory, matching Activity Monitor.
    """
    try:
        import ctypes
        import ctypes.util
        import struct
        libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
        # Set argtypes to ensure proper calling convention
        libc.proc_pid_rusage.restype = ctypes.c_int
        libc.proc_pid_rusage.argtypes = [
            ctypes.c_int,        # pid
            ctypes.c_int,        # flavor
            ctypes.POINTER(ctypes.c_char),  # buffer
        ]
        buf = ctypes.create_string_buffer(512)
        # RUSAGE_INFO_V4 = 4; returns 0 on success
        ret = libc.proc_pid_rusage(pid, 4, buf)
        if ret == 0:
            phys_footprint = struct.unpack_from('Q', buf, 72)[0]
            if phys_footprint > 0:
                return phys_footprint
    except Exception:
        pass
    return None


def get_top_processes_ram(n=5):
    """Get top N processes by RAM usage.

    On macOS, uses phys_footprint (includes compressed memory) to match
    Activity Monitor. On other platforms, uses RSS via psutil.
    """
    procs = []
    total_mem = psutil.virtual_memory().total
    use_footprint = sys.platform == "darwin"

    for p in psutil.process_iter(['pid', 'name']):
        try:
            mem_mb = None
            mem_pct = None

            if use_footprint:
                footprint = _get_phys_footprint_macos(p.pid)
                if footprint is not None and footprint > 0:
                    mem_mb = footprint / (1024 * 1024)
                    mem_pct = (footprint / total_mem) * 100

            if mem_mb is None:
                mem_pct = p.memory_percent()
                mem_mb = p.memory_info().rss / (1024 * 1024)

            procs.append({'pid': p.pid, 'name': p.info['name'], 'mem_pct': mem_pct,
                         'mem_mb': mem_mb})
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


# ── Disk ─────────────────────────────────────────────────────────────────────

def get_disk_info():
    """Get disk space info for all mounted volumes."""
    disks = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total_gb": fmt_gb(usage.total),
                "used_gb": fmt_gb(usage.used),
                "used_pct": fmt_pct(usage.used / usage.total) if usage.total else "0%",
                "free_gb": fmt_gb(usage.free),
                "free_pct": fmt_pct(usage.free / usage.total) if usage.total else "0%",
            })
        except (PermissionError, OSError):
            # Skip volumes we can't read (e.g. unmounted, restricted)
            continue
    return disks


# ── Container / cgroup limits ────────────────────────────────────────────────

def _read_file(path):
    """Read a small file, return stripped content or None."""
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return None


def _cgroup_v2_file(filename):
    """Read a cgroup v2 file for this process.

    Inside containers /sys/fs/cgroup is the container's own cgroup root.
    On host systems with systemd the process cgroup is nested — derive
    the path from /proc/self/cgroup.
    """
    val = _read_file(f"/sys/fs/cgroup/{filename}")
    if val is not None:
        return val
    cgroup = _read_file("/proc/self/cgroup")
    if cgroup:
        for line in cgroup.splitlines():
            parts = line.split(":")
            if len(parts) == 3 and parts[0] == "0":
                rel = parts[2].strip("/")
                if rel:
                    val = _read_file(f"/sys/fs/cgroup/{rel}/{filename}")
                    if val is not None:
                        return val
    return None


def _detect_container_env():
    """Best-effort detection of the container runtime."""
    env = []
    if os.path.exists("/.dockerenv"):
        env.append("docker")
    if os.path.exists("/run/.containerenv"):
        env.append("podman")
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        env.append("kubernetes")
    if os.environ.get("RUNPOD_POD_ID") or os.environ.get("RUNPOD_METRICS_PORT"):
        env.append("runpod")
    cgroup = _read_file("/proc/1/cgroup") or _read_file("/proc/self/cgroup") or ""
    if "kubepods" in cgroup and "kubernetes" not in env:
        env.append("kubernetes")
    if "docker" in cgroup and "docker" not in env:
        env.append("docker")
    if "lxc" in cgroup:
        env.append("lxc")
    return env


def get_container_limits():
    """Detect container/cgroup resource limits (Linux only).

    In containers (Docker, Kubernetes, RunPod, ...) psutil reports HOST
    totals — the container may be capped far below them. This reports
    the effective limits: usable CPU cores (scheduler affinity, what
    nproc reports), cgroup CPU quota, cgroup memory cap, and the
    detected container environment.

    Returns a dict, or None when nothing constrains this process.
    """
    if platform.system() != "Linux":
        return None

    limits = {}

    # Usable CPU cores — respects cpuset/taskset
    try:
        limits["cpu_usable"] = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        pass

    # CPU quota — cgroup v2 ("max 100000" = unlimited), then v1 fallback
    cpu_max = _cgroup_v2_file("cpu.max")
    if cpu_max:
        parts = cpu_max.split()
        if parts[0] != "max":
            try:
                quota = int(parts[0])
                period = int(parts[1]) if len(parts) > 1 else 100000
                if period > 0:
                    limits["cpu_quota_cores"] = round(quota / period, 2)
            except (ValueError, ZeroDivisionError):
                pass
    if "cpu_quota_cores" not in limits:
        quota = _read_file("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
        period = _read_file("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
        try:
            if quota and int(quota) > 0 and period and int(period) > 0:
                limits["cpu_quota_cores"] = round(int(quota) / int(period), 2)
        except ValueError:
            pass

    # Memory cap — cgroup v2 ("max" = unlimited), then v1 fallback
    mem_max = _cgroup_v2_file("memory.max")
    if mem_max and mem_max != "max":
        try:
            limits["memory_limit_gb"] = fmt_gb(int(mem_max))
        except ValueError:
            pass
    if "memory_limit_gb" not in limits:
        mem_limit = _read_file("/sys/fs/cgroup/memory/memory.limit_in_bytes")
        try:
            # v1 reports a huge sentinel (~2^63) when unlimited
            if mem_limit and 0 < int(mem_limit) < (1 << 60):
                limits["memory_limit_gb"] = fmt_gb(int(mem_limit))
        except ValueError:
            pass

    env = _detect_container_env()
    if env:
        limits["environment"] = env

    if not limits:
        return None
    # Bare metal with no caps and full affinity — nothing to report
    has_cap = any(k in limits for k in ("cpu_quota_cores", "memory_limit_gb", "environment"))
    if not has_cap and limits.get("cpu_usable") == psutil.cpu_count(logical=True):
        return None
    return limits


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

    # Disk
    disks = get_disk_info()
    print("\n── Disk Space ──")
    for d in disks:
        label = f"{d['mountpoint']}"
        if d['device'] and d['device'] != d['mountpoint']:
            label = f"{d['device']} ({d['mountpoint']})"
        print(f"  {label}:  {d['used_gb']} / {d['total_gb']} GB used ({d['used_pct']})  |  {d['free_gb']} GB free ({d['free_pct']})")

    # Container/cgroup limits
    limits = get_container_limits()
    if limits:
        print("\n── Container/Cgroup Limits ──")
        if limits.get("environment"):
            print(f"  Environment:       {', '.join(limits['environment'])}")
        if "cpu_usable" in limits:
            print(f"  Usable CPU cores: {limits['cpu_usable']} (of {cpu['core_count_logical']} visible)")
        if "cpu_quota_cores" in limits:
            print(f"  CPU quota:        {limits['cpu_quota_cores']} cores")
        if "memory_limit_gb" in limits:
            print(f"  Memory cap:       {limits['memory_limit_gb']} GB (of {ram['total_gb']} GB visible)")

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
    data["disk"] = get_disk_info()
    limits = get_container_limits()
    if limits:
        data["limits"] = limits
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
