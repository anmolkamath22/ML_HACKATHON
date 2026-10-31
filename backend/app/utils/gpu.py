"""Cheap NVIDIA GPU queries through nvidia-smi; the backend environment does not import torch."""
import shutil
import subprocess
import threading
import time

_cache: tuple[float, list[dict]] | None = None
_cache_lock = threading.Lock()
_CACHE_SECONDS = 30.0


def _query(fields: str) -> list[list[str]] | None:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None
    try:
        completed = subprocess.run([executable, f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
                                   capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return [[part.strip() for part in line.split(",")] for line in completed.stdout.splitlines() if line.strip()]


def list_gpus() -> list[dict]:
    """GPU names and memory, cached so the health endpoint stays inexpensive."""
    global _cache
    with _cache_lock:
        if _cache and time.monotonic() - _cache[0] < _CACHE_SECONDS:
            return _cache[1]
        rows = _query("name,memory.total") or []
        gpus = []
        for row in rows:
            if len(row) == 2:
                gpus.append({"name": row[0], "memory_total_mb": int(float(row[1])) if row[1].replace(".", "").isdigit() else None})
        _cache = (time.monotonic(), gpus)
        return gpus


def memory_used_mb() -> int | None:
    """Current memory in use across all GPUs (includes other processes)."""
    rows = _query("memory.used")
    if not rows:
        return None
    try:
        return sum(int(float(row[0])) for row in rows)
    except (ValueError, IndexError):
        return None
