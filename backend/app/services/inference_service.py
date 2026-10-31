"""GPU stages, run as subprocesses of the InstantMesh Python environment.

* ControlNet (Stable Diffusion 1.5 + scribble ControlNet): sketch + prompt -> object image.
* InstantMesh (official TencentARC ``run.py``): image -> textured mesh.

Each stage runs in a fresh subprocess so its GPU memory is fully released before
the next one starts, which matters on 4-8 GB laptop GPUs. A process-wide lock
guarantees only one GPU process (and so one set of model weights) at a time.
"""
import codecs
import json
import logging
import os
import re
import signal
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import Settings, get_settings
from app.utils import gpu

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str, int | None, str], None]
_MAX_LOG_BYTES = 5 * 1024 * 1024
_TQDM_STEP = re.compile(r"(\d{1,3})%\|.*?(\d+)/(\d+)")
_CONTROLNET_STEP = re.compile(r"ControlNet step (\d+)/(\d+)")


def _failures(tool: str) -> tuple:
    return (
        (("out of memory", "outofmemoryerror"), "gpu_out_of_memory",
         f"The GPU ran out of memory during {tool}. Close other GPU applications or lower the steps, then retry."),
        (("no kernel image is available",), "gpu_unsupported",
         f"The PyTorch build in the inference environment has no kernels for this GPU, so {tool} cannot run. Install a newer PyTorch build."),
        (("no cuda gpus are available", "no cuda gpu", "torch not compiled with cuda", "found no nvidia driver",
          "cuda driver version is insufficient"), "gpu_unavailable", f"{tool} could not access a CUDA GPU."),
        (("localentrynotfounderror", "repository not found", "couldn't connect to 'https://huggingface.co'",
          "is not a valid model identifier", ".ckpt"), "model_weights_unavailable",
         f"{tool} model weights could not be downloaded or loaded. Check the internet connection or the Hugging Face cache."),
        (("modulenotfounderror", "importerror", "cannot import name"), "inference_environment_error",
         f"The inference Python environment is missing a package {tool} needs."),
    )


@dataclass(frozen=True)
class Installation:
    repo: Path
    python: Path
    script: Path
    config: Path


@dataclass(frozen=True)
class ProcessStats:
    duration_seconds: float
    gpu_memory_baseline_mb: int | None
    gpu_memory_peak_mb: int | None
    process_memory_peak_mb: int | None


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
    stats: ProcessStats


@dataclass(frozen=True)
class ControlNetRequest:
    control: Path
    output: Path
    log_path: Path
    prompt: str
    negative_prompt: str
    seed: int


@dataclass(frozen=True)
class ControlNetResult:
    image: Path
    stats: ProcessStats
    info: dict = field(default_factory=dict)


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


def classify_failure(log_tail: str, returncode: int, tool: str = "InstantMesh") -> InferenceError:
    lowered = log_tail.lower()
    for needles, code, message in _failures(tool):
        if any(needle in lowered for needle in needles):
            return InferenceError(code, message)
    return InferenceError("inference_failed", f"{tool} exited with code {returncode}. See the job's log for details.")


# ---------------------------------------------------------------------------
# GPU detection: asks the inference environment's own PyTorch, so it works for
# any GPU model rather than a fixed list.

@dataclass(frozen=True)
class GpuStatus:
    state: str  # ready | checking | not_configured | unavailable | unsupported
    message: str
    name: str | None = None
    memory_total_mb: int | None = None
    backend: str | None = None
    torch_version: str | None = None

    @property
    def ready(self) -> bool:
        return self.state == "ready"

    def as_dict(self) -> dict:
        return {"status": self.state, "available": self.ready, "message": self.message, "name": self.name,
                "memory_total_mb": self.memory_total_mb, "backend": self.backend, "torch": self.torch_version}


_ERROR_CODES = {"not_configured": "inference_not_configured", "unavailable": "gpu_unavailable",
                "unsupported": "gpu_unsupported", "checking": "gpu_unavailable"}
_FAILED_PROBE_TTL = 60.0
_probe_lock = threading.Lock()
_probe_cache: tuple[float, GpuStatus] | None = None
_probe_thread: threading.Thread | None = None


def _interpret_probe(info: dict) -> GpuStatus:
    torch_version = info.get("torch")
    if "error" in info:
        return GpuStatus("unavailable", f"PyTorch could not be loaded in the InstantMesh environment ({info['error'][:200]}).")
    name, memory = info.get("name"), info.get("memory_total_mb")
    if info.get("hip_version"):
        return GpuStatus("unsupported", f"{name or 'An AMD GPU'} (ROCm) was found, but InstantMesh's mesh renderer only runs on NVIDIA CUDA GPUs.",
                         name, memory, "rocm", torch_version)
    if not info.get("cuda_available"):
        if info.get("mps_available"):
            return GpuStatus("unsupported", "An Apple GPU (MPS) was found, but InstantMesh needs an NVIDIA CUDA GPU.", None, None, "mps", torch_version)
        return GpuStatus("unavailable", "No CUDA-capable NVIDIA GPU is visible to PyTorch in the InstantMesh environment.", None, None, None, torch_version)
    if info.get("arch_supported") is False:
        return GpuStatus("unsupported", f"{name} (compute capability {info.get('capability')}) is not supported by PyTorch {torch_version} "
                         "in the InstantMesh environment. Install a PyTorch build that supports this GPU.", name, memory, "cuda", torch_version)
    size = f"{memory / 1024:.1f} GB" if memory else "unknown memory"
    return GpuStatus("ready", f"{name} · {size} VRAM", name, memory, "cuda", torch_version)


def _probe() -> GpuStatus:
    settings = get_settings()
    try:
        installation = locate_installation(settings)
    except InferenceError as exc:
        return GpuStatus("not_configured", exc.message)
    try:
        completed = subprocess.run([str(installation.python), str(settings.gpu_probe_script)], cwd=installation.repo,
                                   capture_output=True, text=True, timeout=180, check=False)
        line = next((line for line in reversed(completed.stdout.splitlines()) if line.startswith("{")), None)
        if line is None:
            raise ValueError((completed.stderr or completed.stdout or f"exit code {completed.returncode}")[-200:])
        return _interpret_probe(json.loads(line))
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return GpuStatus("unavailable", f"The GPU check in the InstantMesh environment failed ({str(exc)[:200]}).")


def _refresh() -> GpuStatus:
    global _probe_cache
    status = _probe()
    _probe_cache = (time.monotonic(), status)
    logger.info("GPU check: %s", status.message)
    return status


def _cached() -> GpuStatus | None:
    if _probe_cache and (_probe_cache[1].ready or time.monotonic() - _probe_cache[0] < _FAILED_PROBE_TTL):
        return _probe_cache[1]
    return None


def gpu_status(wait: bool = False) -> GpuStatus:
    """Cached GPU status. Without ``wait`` a missing result starts a background check and reports 'checking'."""
    global _probe_thread
    cached = _cached()
    if cached:
        return cached
    if wait:
        with _probe_lock:
            return _cached() or _refresh()
    with _probe_lock:
        if _probe_thread is None or not _probe_thread.is_alive():
            _probe_thread = threading.Thread(target=lambda: gpu_status(wait=True), name="gpu-probe", daemon=True)
            _probe_thread.start()
    return GpuStatus("checking", "Checking the GPU in the InstantMesh environment…")


def reset_gpu_status() -> None:
    global _probe_cache
    _probe_cache = None


def ensure_ready() -> GpuStatus:
    """Raise InferenceError unless InstantMesh is configured and a supported GPU is available."""
    locate_installation()
    status = gpu_status(wait=True)
    if not status.ready:
        raise InferenceError(_ERROR_CODES.get(status.state, "gpu_unavailable"), status.message)
    return status


# ---------------------------------------------------------------------------
# Process execution

def _process_group_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _terminate(process: subprocess.Popen) -> None:
    """Stop the GPU process and anything it spawned, never other processes."""
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
    """Peak resident memory of the GPU process (largest of it and its children)."""
    if os.name == "nt":
        # A Windows venv's python.exe is a launcher that starts the real interpreter as a child.
        try:
            import psutil
            process = psutil.Process(pid)
            peaks = [item.memory_info().peak_wset for item in (process, *process.children(recursive=True))]
            return max(peaks) // (1024 * 1024) if peaks else None
        except Exception:  # noqa: BLE001 - psutil missing or the process just exited
            return None
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


class _InstantMeshProgress:
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
        elif self.phase == "multiview_diffusion" and (match := _TQDM_STEP.search(line)):
            done, total = int(match[2]), int(match[3])
            percent = min(100, round(100 * done / total)) if total else None
            if percent != self.last_percent:
                self._emit("multiview_diffusion", percent, f"Generating multi-view images ({done}/{total} diffusion steps).")


class _ControlNetProgress:
    def __init__(self, on_progress: ProgressCallback) -> None:
        self.on_progress = on_progress

    def __call__(self, line: str) -> None:
        if "Loading ControlNet" in line:
            self.on_progress("controlnet_loading", None, "Loading Stable Diffusion and ControlNet.")
        elif match := _CONTROLNET_STEP.search(line):
            done, total = int(match[1]), int(match[2])
            self.on_progress("controlnet_diffusion", min(100, round(100 * done / total)) if total else None,
                             f"Turning the sketch into an object image ({done}/{total} steps).")


class _OutputReader(threading.Thread):
    def __init__(self, stream, log_path: Path, on_line: Callable[[str], None]) -> None:
        super().__init__(daemon=True, name="gpu-process-output")
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


class GpuRunner:
    def __init__(self) -> None:
        self._gpu_lock = threading.Lock()

    @property
    def busy(self) -> bool:
        return self._gpu_lock.locked()

    def _run(self, command: list[str], cwd: Path, log_path: Path, on_line: Callable[[str], None],
             cancel: threading.Event, timeout: int, timeout_error: InferenceError) -> tuple[int, str, ProcessStats]:
        settings = get_settings()
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        with self._gpu_lock:
            if cancel.is_set():
                raise InferenceCancelled()
            baseline = peak_gpu = gpu.memory_used_mb()
            peak_rss = None
            started = time.monotonic()
            deadline = started + timeout
            process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, env=env, **_process_group_kwargs())
            reader = _OutputReader(process.stdout, log_path, on_line)
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
            stats = ProcessStats(round(time.monotonic() - started, 3), baseline, peak_gpu, peak_rss)
        if outcome == "cancelled":
            raise InferenceCancelled()
        if outcome == "timeout":
            raise timeout_error
        return process.returncode, "\n".join(reader.tail), stats

    def run_controlnet(self, request: ControlNetRequest, on_progress: ProgressCallback, cancel: threading.Event) -> ControlNetResult:
        settings = get_settings()
        installation = locate_installation(settings)
        python = (settings.controlnet_python or installation.python).absolute()
        command = [str(python), str(settings.controlnet_script), "--control", str(request.control), "--output", str(request.output),
                   "--prompt", request.prompt, "--negative-prompt", request.negative_prompt, "--seed", str(request.seed),
                   "--steps", str(settings.controlnet_steps), "--guidance", str(settings.controlnet_guidance),
                   "--conditioning-scale", str(settings.controlnet_conditioning_scale), "--memory", settings.controlnet_memory,
                   "--base-model", settings.controlnet_base_model, "--controlnet-model", settings.controlnet_model]
        on_progress("controlnet_starting", None, "Starting ControlNet.")
        returncode, tail, stats = self._run(
            command, installation.repo, request.log_path, _ControlNetProgress(on_progress), cancel, settings.controlnet_timeout_seconds,
            InferenceError("refinement_timeout", f"ControlNet exceeded the {settings.controlnet_timeout_seconds}-second time limit."))
        if returncode != 0:
            raise classify_failure(tail, returncode, "ControlNet")
        if not request.output.is_file():
            raise InferenceError("refinement_failed", "ControlNet finished without writing an image.")
        summary = next((line for line in reversed(tail.splitlines()) if line.startswith("{")), "{}")
        try:
            info = json.loads(summary)
        except ValueError:
            info = {}
        return ControlNetResult(request.output, stats, info)

    def run_instantmesh(self, request: InferenceRequest, on_progress: ProgressCallback, cancel: threading.Event) -> InferenceResult:
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
        on_progress("starting", None, "Starting InstantMesh.")
        returncode, tail, stats = self._run(
            command, installation.repo, request.log_path, _InstantMeshProgress(on_progress, request.diffusion_steps), cancel,
            settings.inference_timeout_seconds,
            InferenceError("inference_timeout", f"InstantMesh exceeded the {settings.inference_timeout_seconds}-second time limit."))
        if returncode != 0:
            raise classify_failure(tail, returncode)
        meshes = sorted(request.output_dir.glob("*/meshes/*.obj"))
        if not meshes:
            raise InferenceError("no_mesh_output", "InstantMesh finished without writing an OBJ mesh.")
        multiview = next(iter(sorted(request.output_dir.glob("*/images/*.png"))), None)
        return InferenceResult(meshes[0], multiview, stats)


runner = GpuRunner()
