"""Sunucu durumu (psutil olmadan, Linux /proc üzerinden; başka OS'ta eksik alanlar None döner)."""
from __future__ import annotations

import os
import platform
import shutil
import time
from pathlib import Path

_START = time.time()


def _meminfo() -> dict | None:
    p = Path("/proc/meminfo")
    if not p.exists():
        return None
    vals = {}
    for line in p.read_text().splitlines():
        k, _, v = line.partition(":")
        vals[k] = int(v.strip().split()[0]) * 1024
    total, avail = vals.get("MemTotal"), vals.get("MemAvailable")
    return {"total": total, "available": avail, "used_pct": round(100 * (1 - avail / total), 1) if total else None}


def _rss() -> int | None:
    p = Path("/proc/self/status")
    if not p.exists():
        return None
    for line in p.read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    return None


def snapshot(data_dir: Path) -> dict:
    du = shutil.disk_usage(data_dir)
    try:
        load = os.getloadavg()
    except OSError:
        load = None
    db_file = data_dir / "bulut.db"
    return {
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "loadavg": [round(x, 2) for x in load] if load else None,
        "memory": _meminfo(),
        "process_rss": _rss(),
        "disk": {"total": du.total, "free": du.free, "used_pct": round(100 * (1 - du.free / du.total), 1)},
        "db_size": db_file.stat().st_size if db_file.exists() else 0,
        "uptime_s": int(time.time() - _START),
    }
