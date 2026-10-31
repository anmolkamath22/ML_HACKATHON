"""Generation job lifecycle: queueing, the single GPU worker, stages, cancellation and recovery.

QUEUED -> PREPROCESSING -> REFINING (ControlNet, optional) -> GENERATING (InstantMesh)
       -> POSTPROCESSING -> EXPORTING -> COMPLETED   (any stage may end in FAILED or CANCELLED)
"""
import logging
import queue
import shutil
import threading
import time
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.cv.pipeline import looks_like_sketch, make_control_map, prepare_reconstruction_input
from app.schemas.models import TERMINAL_STATUSES, GenerationOptions
from app.services import mesh_service
from app.services.inference_service import (ControlNetRequest, InferenceCancelled, InferenceError, InferenceRequest, ensure_ready,
                                            runner)
from app.services.job_store import ACTIVE_STATUSES, JobStore, now
from app.services.storage_service import storage

logger = logging.getLogger(__name__)
store = JobStore(storage.root / "jobs.db")
JOB_FILES = {"input.png", "control.png", "refined.png", "reconstruction_input.png", "multiview.png"}
# Zero123++ (InstantMesh's first stage) works best on a single centred object on a plain background.
_PROMPT_STYLE = "single object, centered, full view, product photo, plain white background, soft studio lighting, highly detailed"
NEGATIVE_PROMPT = ("multiple objects, text, watermark, cropped, out of frame, blurry, low quality, deformed, "
                   "pencil sketch, line drawing, cluttered background")


def refinement_prompt(prompt: str | None) -> str:
    return f"{prompt or 'an object'}, {_PROMPT_STYLE}"
_queue: "queue.Queue[str]" = queue.Queue()
_submit_lock = threading.Lock()
_worker_lock = threading.Lock()
_worker: threading.Thread | None = None
_cancel_events: dict[str, threading.Event] = {}
_current: str | None = None
_shutting_down = threading.Event()


class JobNotFound(Exception):
    pass


class JobConflict(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class QueueFull(Exception):
    pass


class _Cancelled(Exception):
    pass


def job_dir(job_id: str) -> Path:
    return storage.root / "jobs" / str(UUID(job_id))


def get_job(job_id: str) -> dict:
    try:
        UUID(job_id)
    except ValueError as exc:
        raise JobNotFound() from exc
    job = store.get(job_id)
    if not job:
        raise JobNotFound()
    return job


def public_job(job: dict) -> dict:
    """The API representation of a job; internal paths and raw logs are never exposed."""
    job_id = job["job_id"]
    folder = job_dir(job_id)
    base = f"/api/v1/jobs/{job_id}"

    def file_url(name: str) -> str | None:
        return f"{base}/files/{name}" if (folder / name).is_file() else None

    return {
        **{key: job[key] for key in ("job_id", "input_id", "source", "status", "stage", "progress", "message", "prompt",
                                     "options", "error", "created_at", "started_at", "completed_at", "updated_at")},
        "timings": job["timings"] or {},
        "queue_position": store.queue_position(job_id, job["created_at"]) if job["status"] == "queued" else None,
        "refinement": (job["details"] or {}).get("refinement"),
        "input_url": f"{base}/files/input.png",
        "control_url": file_url("control.png"),
        "refined_url": file_url("refined.png"),
        "preview_url": file_url("reconstruction_input.png"),
        "multiview_url": file_url("multiview.png"),
        "result_url": f"{base}/result" if job["status"] == "completed" else None,
    }


def build_options(input_id: str, source: str, refine_sketch: bool | None, remove_background: bool | None,
                  diffusion_steps: int, seed: int, export_texture: bool) -> GenerationOptions:
    """Resolve 'auto' choices: refine drawings and uploaded sketches; send photos straight to rembg."""
    original = storage.input_dir(input_id) / "original.png"
    if not original.is_file():
        raise FileNotFoundError("Input image was not found.")
    is_sketch = source == "drawing" or looks_like_sketch(original)
    refine = is_sketch if refine_sketch is None else refine_sketch
    return GenerationOptions(refine_sketch=refine and get_settings().controlnet_enabled,
                             remove_background=(not is_sketch) if remove_background is None else remove_background,
                             diffusion_steps=diffusion_steps, seed=seed, export_texture=export_texture)


def submit_job(input_id: str, source: str, prompt: str | None, options: GenerationOptions, timings: dict | None = None) -> dict:
    """Create a job for a stored input and queue it. Returns immediately."""
    ensure_ready()  # fail fast with a clear error instead of queueing a job that cannot run
    original = storage.input_dir(input_id) / "original.png"
    if not original.is_file():
        raise FileNotFoundError("Input image was not found.")
    with _submit_lock:
        if store.count_active() >= get_settings().max_active_jobs:
            raise QueueFull()
        job_id = str(uuid4())
        folder = job_dir(job_id)
        folder.mkdir(parents=True)
        shutil.copyfile(original, folder / "input.png")
        storage.write_json(folder / "request.json", {"job_id": job_id, "input_id": input_id, "source": source,
                                                     "prompt": prompt, "options": options.model_dump(), "created_at": now()})
        job = store.create({"job_id": job_id, "input_id": input_id, "source": source, "status": "queued", "stage": "queued",
                            "message": "Waiting for the GPU worker.", "prompt": prompt, "options": options.model_dump(),
                            "timings": timings or {}, "created_at": now()})
    _enqueue(job_id)
    return job


def cancel_job(job_id: str) -> dict:
    job = get_job(job_id)
    if job["status"] in TERMINAL_STATUSES:
        raise JobConflict("job_finished", f"The job has already {job['status']}.")
    if store.update(job_id, only_if_status=("queued",), status="cancelled", stage="cancelled", progress=None,
                    message="Generation was cancelled.", completed_at=now()):
        return get_job(job_id)
    event = _cancel_events.get(job_id)
    if event:
        event.set()
    store.update(job_id, only_if_status=ACTIVE_STATUSES, message="Cancelling…")
    return get_job(job_id)


def worker_state() -> dict:
    return {"worker": "busy" if _current else "idle", "active_job_id": _current,
            "gpu_locked": runner.busy, "active_jobs": store.count_active(),
            "max_active_jobs": get_settings().max_active_jobs}


def recover() -> None:
    """On startup: requeue jobs that never started and fail jobs interrupted mid-run."""
    for job in store.active():
        if job["status"] == "queued":
            _enqueue(job["job_id"])
        else:
            store.update(job["job_id"], status="failed", stage="failed", progress=None, completed_at=now(),
                         message="Generation was interrupted.",
                         error={"code": "interrupted", "message": "The backend restarted while this job was running. Submit it again."})


def shutdown(timeout: float = 20.0) -> None:
    """Stop the running InstantMesh process and give the worker time to record the outcome."""
    _shutting_down.set()
    for event in list(_cancel_events.values()):
        event.set()
    deadline = time.monotonic() + timeout
    while _current and time.monotonic() < deadline:
        time.sleep(0.1)


def _enqueue(job_id: str) -> None:
    global _worker
    _cancel_events[job_id] = threading.Event()
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _shutting_down.clear()
            _worker = threading.Thread(target=_worker_loop, name="generation-worker", daemon=True)
            _worker.start()
    _queue.put(job_id)


def _worker_loop() -> None:
    global _current
    while True:
        job_id = _queue.get()
        try:
            _current = job_id
            _run(job_id)
        except Exception:
            logger.exception("Worker crashed while handling job %s", job_id)
        finally:
            _current = None
            _cancel_events.pop(job_id, None)
            _queue.task_done()


def _run(job_id: str) -> None:
    cancel = _cancel_events.setdefault(job_id, threading.Event())
    if not store.update(job_id, only_if_status=("queued",), status="preprocessing", stage="image_preparation",
                        message="Preparing the image for reconstruction.", started_at=now()):
        return  # cancelled while queued
    job = get_job(job_id)
    folder = job_dir(job_id)
    options = GenerationOptions(**job["options"])
    timings: dict = dict(job["timings"] or {})
    settings = get_settings()
    started = time.perf_counter()

    def stage(status: str, name: str, message: str, progress: int | None = None) -> None:
        if cancel.is_set():
            raise _Cancelled()
        store.update(job_id, status=status, stage=name, message=message, progress=progress, timings=timings)

    def timed(key: str, begun: float) -> None:
        timings[key] = round(time.perf_counter() - begun, 3)

    def progress_for(status: str):
        def on_progress(name: str, percent: int | None, message: str) -> None:
            if not cancel.is_set():
                store.update(job_id, only_if_status=(status,), stage=name, progress=percent, message=message)
        return on_progress

    try:
        begun = time.perf_counter()
        # Refinement starts from the OpenCV cutout of the sketch, whatever the background option says.
        prepared = prepare_reconstruction_input(folder / "input.png", folder / "reconstruction_input.png",
                                                options.remove_background and not options.refine_sketch)
        if options.refine_sketch:
            prepared["control"] = make_control_map(folder / "reconstruction_input.png", folder / "control.png")
        timed("preprocessing_seconds", begun)
        storage.write_json(folder / "preprocessing.json", prepared)
        inference_input, use_rembg, source_mode = folder / "reconstruction_input.png", prepared["use_rembg"], prepared["mode"]
        stats = []

        refinement = {"status": "off", "message": "AI refinement was off for this image."}
        if options.refine_sketch:
            stage("refining", "controlnet_starting", "Waiting for the GPU.")
            begun = time.perf_counter()
            prompt = refinement_prompt(job["prompt"])
            try:
                refined = runner.run_controlnet(ControlNetRequest(
                    control=folder / "control.png", output=folder / "refined.png", log_path=folder / "controlnet.log",
                    prompt=prompt, negative_prompt=NEGATIVE_PROMPT, seed=options.seed), progress_for("refining"), cancel)
                inference_input, use_rembg, source_mode = refined.image, True, "controlnet"
                stats.append(refined.stats)
                refinement = {"status": "used", "message": "ControlNet turned the sketch into an object image.",
                              "prompt": prompt, "memory_mode": refined.info.get("memory_mode")}
            except InferenceError as exc:
                # Keep going with the plain cutout so a ControlNet problem never costs the user their model.
                logger.warning("ControlNet skipped for job %s: %s", job_id, exc.code)
                (folder / "refined.png").unlink(missing_ok=True)
                refinement = {"status": "skipped", "code": exc.code, "message": f"{exc.message} Used the sketch cutout instead."}
            timed("refinement_seconds", begun)
        store.update(job_id, details={"refinement": refinement})

        stage("generating", "starting", "Waiting for the GPU.")
        begun = time.perf_counter()
        inference = runner.run_instantmesh(InferenceRequest(
            image=inference_input, output_dir=folder / "instantmesh", log_path=folder / "inference.log",
            remove_background=use_rembg, diffusion_steps=options.diffusion_steps, seed=options.seed,
            export_texture=options.export_texture), progress_for("generating"), cancel)
        stats.append(inference.stats)
        timed("inference_seconds", begun)
        if inference.multiview_path:
            shutil.copyfile(inference.multiview_path, folder / "multiview.png")

        stage("postprocessing", "mesh_validation", "Validating and normalising the mesh.")
        begun = time.perf_counter()
        meshes, report = mesh_service.load_and_prepare(inference.mesh_path, settings.mesh_convert_z_up, settings.mesh_max_faces)
        timed("postprocessing_seconds", begun)

        stage("exporting", "glb_export", "Exporting and verifying the GLB.")
        begun = time.perf_counter()
        model = mesh_service.export_glb(meshes, folder / "model.glb", report)
        timed("export_seconds", begun)
        timings["total_seconds"] = round(time.perf_counter() - started, 3)

        companions = [path for path in inference.mesh_path.parent.iterdir() if path != inference.mesh_path]
        model.update(obj_bytes=inference.mesh_path.stat().st_size, obj_has_companion_files=bool(companions),
                     preprocessing_mode=source_mode,
                     gpu_memory_baseline_mb=stats[0].gpu_memory_baseline_mb,
                     gpu_memory_peak_mb=_largest(item.gpu_memory_peak_mb for item in stats),
                     process_memory_peak_mb=_largest(item.process_memory_peak_mb for item in stats))
        store.update(job_id, status="completed", stage="complete", progress=None, message="Your 3D model is ready.",
                     result={"model": model, "obj_path": str(inference.mesh_path.relative_to(folder))},
                     timings=timings, completed_at=now())
    except (_Cancelled, InferenceCancelled):
        if _shutting_down.is_set():
            _fail(job_id, timings, "interrupted", "The backend shut down while this job was running. Submit it again.")
        else:
            store.update(job_id, status="cancelled", stage="cancelled", progress=None, message="Generation was cancelled.",
                         timings=timings, completed_at=now())
    except InferenceError as exc:
        _fail(job_id, timings, exc.code, exc.message)
    except mesh_service.MeshError as exc:
        _fail(job_id, timings, "invalid_mesh", str(exc))
    except ValueError as exc:
        _fail(job_id, timings, "invalid_input", str(exc))
    except Exception:
        logger.exception("Generation job %s failed", job_id)
        _fail(job_id, timings, "internal_error", "An unexpected error stopped this job. Check the backend log for details.")


def _largest(values) -> int | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _fail(job_id: str, timings: dict, code: str, message: str) -> None:
    logger.warning("Generation job %s failed: %s", job_id, code)
    store.update(job_id, status="failed", stage="failed", progress=None, message="3D generation failed.",
                 error={"code": code, "message": message}, timings=timings, completed_at=now())


def job_file(job_id: str, name: str) -> Path:
    get_job(job_id)
    if name not in JOB_FILES:
        raise FileNotFoundError(name)
    path = job_dir(job_id) / name
    if not path.is_file():
        raise FileNotFoundError(name)
    return path


def result_paths(job_id: str) -> tuple[dict, Path, Path]:
    """The completed job, its GLB and its original OBJ, or JobConflict if there is no result."""
    job = get_job(job_id)
    if job["status"] != "completed":
        code = {"failed": "job_failed", "cancelled": "job_cancelled"}.get(job["status"], "result_not_ready")
        raise JobConflict(code, f"The job is {job['status']}; there is no model to return.")
    folder = job_dir(job_id)
    obj = (folder / job["result"]["obj_path"]).resolve()
    if not obj.is_relative_to(folder.resolve()):
        raise FileNotFoundError("model.obj")
    return job, folder / "model.glb", obj
