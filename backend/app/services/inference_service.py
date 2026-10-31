"""Adapter around the official TencentARC InstantMesh ``run.py`` command line.

Each job runs in a fresh subprocess so the GPU memory is fully released between
jobs, which matters on 4 GB cards. A process-wide lock guarantees that only one
InstantMesh process (and so one copy of the models) exists at a time.
"""
import codecs
import logging
import os
import re
import signal
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings, get_settings
from app.utils import gpu

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str, int | None, str], None]
_MAX_LOG_BYTES = 5 * 1024 * 1024
_STEP = re.compile(r"(\d{1,3})%\|.*?(\d+)/(\d+)")
_FAILURES = (
    (("out of memory", "outofmemoryerror"), "gpu_out_of_memory",
     "The GPU ran out of memory during InstantMesh inference. Close other GPU applications or lower the diffusion steps, then retry."),
    (("no cuda gpus are available", "torch not compiled with cuda", "found no nvidia driver", "cuda driver version is insufficient"),
     "gpu_unavailable", "InstantMesh could not access a CUDA GPU."),
    (("localentrynotfounderror", "repository not found", "couldn't connect to 'https://huggingface.co'", ".ckpt"),
     "model_weights_unavailable", "InstantMesh model weights could not be loaded. Check the checkpoints or Hugging Face cache of the InstantMesh environment."),
    (("modulenotfounderror", "importerror"), "inference_environment_error",
     "The InstantMesh Python environment is missing a required package."),
)


@dataclass(frozen=True)
class Installation:
    repo: Path
    python: Path
    script: Path
    config: Path


@dataclass(frozen=True)
class InferenceRequest:
    image: Path
    output_dir: Path
    log_path: Path
    remove_background: bool
    diffusion_steps: int
    seed: int
    export_texture: bool


@dataclass(frozen=True)
class InferenceResult:
    mesh_path: Path
    multiview_path: Path | None
    duration_seconds: float
    gpu_memory_baseline_mb: int | None
    gpu_memory_peak_mb: int | None
    process_memory_peak_mb: int | None


class InferenceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class InferenceCancelled(Exception):
    pass


def locate_installation(settings: Settings | None = None) -> Installation:
    settings = settings or get_settings()
    if not settings.instantmesh_repo or not settings.instantmesh_python:
        raise InferenceError("inference_not_configured",
                             "InstantMesh is not configured. Set INSTANTMESH_REPO and INSTANTMESH_PYTHON in backend/.env.")
    repo = settings.instantmesh_repo.resolve()
    # Do not resolve symlinks: a venv's bin/python is a symlink to the base
    # interpreter, and resolving it would silently drop the venv's packages.
    python = settings.instantmesh_python.absolute()
    installation = Installation(repo, python, repo / "run.py", repo / settings.instantmesh_config)
    if not python.is_file() or not installation.script.is_file() or not installation.config.is_file():
        raise InferenceError("inference_not_configured",
                             "The InstantMesh checkout, its config file, or its dedicated Python executable could not be found.")
    return installation


def is_configured() -> bool:
    try:
        locate_installation()
        return True
    except InferenceError:
        return False


def classify_failure(log_tail: str, returncode: int) -> InferenceError:
    lowered = log_tail.lower()
    for needles, code, message in _FAILURES:
        if any(needle in lowered for needle in needles):
            return InferenceError(code, message)
    return InferenceError("inference_failed", f"InstantMesh exited with code {returncode}. See the job's inference.log for details.")


def _process_group_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _terminate(process: subprocess.Popen) -> None:
    """Stop the InstantMesh process and anything it spawned, never other processes."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, timeout=15, check=False)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
    except (subprocess.TimeoutExpired, ProcessLookupError, OSError):
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
        process.kill()
        process.wait(timeout=10)


def _peak_rss_mb(pid: int) -> int | None:
    """Peak resident memory of the process (Linux only)."""
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


class _ProgressParser:
    """Turns InstantMesh's console output into stages and real diffusion-step progress."""

    def __init__(self, on_progress: ProgressCallback, steps: int) -> None:
        self.on_progress = on_progress
        self.steps = steps
        self.phase: str | None = None
        self.last_percent: int | None = None

    def _emit(self, phase: str, percent: int | None, message: str) -> None:
        self.phase = phase
        self.last_percent = percent
        self.on_progress(phase, percent, message)

    def __call__(self, line: str) -> None:
        lowered = line.lower()
        if "imagining" in lowered:
            self._emit("multiview_diffusion", 0, f"Generating multi-view images (0/{self.steps} diffusion steps).")
        elif "creating" in lowered:
            self._emit("mesh_reconstruction", None, "Reconstructing the 3D mesh from the generated views.")
        elif "loading" in lowered and self.phase in (None, "loading_models"):
            self._emit("loading_models", None, "Loading InstantMesh models onto the GPU.")
        elif self.phase == "multiview_diffusion" and (match := _STEP.search(line)):
            done, total = int(match[2]), int(match[3])
            percent = min(100, round(100 * done / total)) if total else None
            if percent != self.last_percent:
                self._emit("multiview_diffusion", percent, f"Generating multi-view images ({done}/{total} diffusion steps).")


class _OutputReader(threading.Thread):
    def __init__(self, stream, log_path: Path, on_line: Callable[[str], None]) -> None:
        super().__init__(daemon=True, name="instantmesh-output")
        self.stream = stream
        self.log_path = log_path
        self.on_line = on_line
        self.tail: deque[str] = deque(maxlen=200)

    def run(self) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        pending = ""
        written = 0
        with self.log_path.open("a", encoding="utf-8") as log:
            while chunk := self.stream.read1(8192):
                text = decoder.decode(chunk)
                if written < _MAX_LOG_BYTES:
                    log.write(text)
                    written += len(text)
                *lines, pending = re.split(r"[\r\n]", pending + text)
                for line in lines:
                    self._handle(line)
            self._handle(pending + decoder.decode(b"", final=True))

    def _handle(self, line: str) -> None:
        if not line.strip():
            return
        self.tail.append(line)
        try:
            self.on_line(line)
        except Exception:
            logger.exception("Progress callback failed")


class InstantMeshRunner:
    def __init__(self) -> None:
        self._gpu_lock = threading.Lock()

    @property
    def busy(self) -> bool:
        return self._gpu_lock.locked()

    def run(self, request: InferenceRequest, on_progress: ProgressCallback, cancel: threading.Event) -> InferenceResult:
        settings = get_settings()
        installation = locate_installation(settings)
        command = [str(installation.python), str(installation.script), str(installation.config), str(request.image),
                   "--output_path", str(request.output_dir),
                   "--diffusion_steps", str(request.diffusion_steps), "--seed", str(request.seed)]
        if not request.remove_background:
            command.append("--no_rembg")
        if request.export_texture:
            command.append("--export_texmap")
        request.output_dir.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}

        with self._gpu_lock:
            if cancel.is_set():
                raise InferenceCancelled()
            on_progress("starting", None, "Starting InstantMesh.")
            baseline = peak_gpu = gpu.memory_used_mb()
            peak_rss = None
            started = time.monotonic()
            deadline = started + settings.inference_timeout_seconds
            process = subprocess.Popen(command, cwd=installation.repo, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, env=env, **_process_group_kwargs())
            reader = _OutputReader(process.stdout, request.log_path, _ProgressParser(on_progress, request.diffusion_steps))
            reader.start()
            outcome = "exited"
            next_sample = started
            try:
                while process.poll() is None:
                    if cancel.wait(0.5):
                        outcome = "cancelled"
                        break
                    now = time.monotonic()
                    if now > deadline:
                        outcome = "timeout"
                        break
                    if now >= next_sample:
                        next_sample = now + settings.gpu_sample_interval_seconds
                        used = gpu.memory_used_mb()
                        if used is not None:
                            peak_gpu = max(peak_gpu or 0, used)
                        peak_rss = _peak_rss_mb(process.pid) or peak_rss
            finally:
                _terminate(process)
                reader.join(timeout=10)
                if process.stdout:
                    process.stdout.close()
            duration = time.monotonic() - started

        if outcome == "cancelled":
            raise InferenceCancelled()
        if outcome == "timeout":
            raise InferenceError("inference_timeout", f"InstantMesh exceeded the {settings.inference_timeout_seconds}-second time limit.")
        if process.returncode != 0:
            raise classify_failure("\n".join(reader.tail), process.returncode)
        meshes = sorted(request.output_dir.glob("*/meshes/*.obj"))
        if not meshes:
            raise InferenceError("no_mesh_output", "InstantMesh finished without writing an OBJ mesh.")
        multiview = next(iter(sorted(request.output_dir.glob("*/images/*.png"))), None)
        return InferenceResult(meshes[0], multiview, duration, baseline, peak_gpu, peak_rss)


runner = InstantMeshRunner()
