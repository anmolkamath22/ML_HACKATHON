"""GPU memory sampling through nvidia-smi while a GPU stage runs (NVIDIA only; optional)."""
import shutil
import subprocess


def memory_used_mb() -> int | None:
    """Current memory in use across all NVIDIA GPUs (includes other processes), or None if unknown."""
    executable = shutil.which("nvidia-smi")
    if not executable:
        return None
    try:
        completed = subprocess.run([executable, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                   capture_output=True, text=True, timeout=5, check=False)
        if completed.returncode != 0:
            return None
        return sum(int(float(line.strip())) for line in completed.stdout.splitlines() if line.strip())
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
