import json
import logging
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.schemas.models import PreprocessingConfig
from app.cv.pipeline import run_pipeline
from app.services.storage_service import storage

logger = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="instantmesh")
_lock = threading.Lock()
_active: set[str] = set()
_allowed_artifacts = {"original.png", "normalized.png", "enhanced.png", "preprocessed.png"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_path(job_id: str) -> Path:
    return storage.root / "jobs" / job_id / "job.json"


def _save(job: dict) -> None:
    job["updated_at"] = _now()
    destination = _job_path(job["job_id"])
    temporary = destination.with_suffix(".json.tmp")
    storage.write_json(temporary, job)
    temporary.replace(destination)


def get_job(job_id: str) -> dict:
    path = _job_path(job_id)
    if not path.is_file():
        raise FileNotFoundError("Generation job was not found.")
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_input(input_id: str, processing_id: str | None, artifact: str) -> Path:
    if artifact not in _allowed_artifacts:
        raise ValueError("Unsupported input artifact.")
    source = storage.input_dir(input_id) / "original.png"
    if processing_id:
        processed = storage.root / "processed" / str(UUID(input_id)) / str(UUID(processing_id)) / artifact
        if not processed.is_file():
            raise FileNotFoundError("Selected processed image was not found.")
        return processed
    if artifact != "original.png":
        raise ValueError("Run preprocessing before selecting a processed artifact.")
    if not source.is_file():
        raise FileNotFoundError("Input image was not found.")
    return source


def submit_job(input_id: str, processing_id: str | None, artifact: str, prompt: str | None) -> dict:
    source = _resolve_input(input_id, processing_id, artifact)
    with _lock:
        pending = sum(1 for path in (storage.root / "jobs").glob("*/job.json")
                      if json.loads(path.read_text(encoding="utf-8")).get("status") in {"queued", "preprocessing", "generating", "postprocessing"})
        if pending >= 4:
            raise RuntimeError("The inference queue is full. Wait for a job to finish before submitting another.")
        job_id = str(uuid4())
        folder = storage.root / "jobs" / job_id
        folder.mkdir(parents=True, exist_ok=False)
        job = {"job_id": job_id, "input_id": input_id, "status": "queued", "stage": "queued",
               "message": "Generation is queued.", "error": None, "prompt": prompt,
               "created_at": _now(), "updated_at": _now(), "result_url": None}
        _save(job)
        _active.add(job_id)
    _pool.submit(_run_job, job_id, source)
    return job


def _run_job(job_id: str, source: Path) -> None:
    job = get_job(job_id)
    folder = _job_path(job_id).parent
    settings = get_settings()
    try:
        job.update(status="preprocessing", stage="image_preprocessing", message="Preparing the image for reconstruction.")
        _save(job)
        cv_output = folder / "preprocessing"
        cv_output.mkdir(parents=True, exist_ok=True)
        run_pipeline(source, cv_output, PreprocessingConfig())
        if not settings.instantmesh_repo or not settings.instantmesh_python:
            raise RuntimeError("InstantMesh is not configured. Set INSTANTMESH_REPO and INSTANTMESH_PYTHON to a dedicated official checkout and Python 3.10 environment.")
        repo = settings.instantmesh_repo.resolve()
        python = settings.instantmesh_python.resolve()
        script = repo / "run.py"
        config = repo / settings.instantmesh_config
        if not script.is_file() or not config.is_file() or not python.is_file():
            raise RuntimeError("InstantMesh checkout, configuration, or dedicated Python executable could not be found.")
        job.update(status="generating", stage="instantmesh", message="InstantMesh is generating geometry.")
        _save(job)
        inference_input = folder / "input.png"
        # InstantMesh's image encoder expects RGB. Keep the color-normalized
        # source for inference; the CV pipeline's enhanced recommendation is grayscale.
        inference_input.write_bytes((cv_output / "normalized.png").read_bytes())
        output = folder / "instantmesh-output"
        output.mkdir()
        command = [str(python), str(script), str(config), str(inference_input), "--output_path", str(output), "--no_rembg"]
        started = datetime.now(timezone.utc)
        completed = subprocess.run(command, cwd=repo, capture_output=True, text=True,
                                   timeout=settings.inference_timeout_seconds, check=False,
                                   env={**os.environ, "PYTHONUNBUFFERED": "1"})
        (folder / "stdout.log").write_text(completed.stdout[-100_000:], encoding="utf-8")
        (folder / "stderr.log").write_text(completed.stderr[-100_000:], encoding="utf-8")
        if completed.returncode != 0:
            detail = completed.stderr[-1200:] or completed.stdout[-1200:] or f"InstantMesh exited with code {completed.returncode}."
            if "out of memory" in detail.lower() or "cuda error: out of memory" in detail.lower():
                detail = "InstantMesh ran out of GPU memory. This GPU cannot complete the configured inference run."
            raise RuntimeError(detail)
        job.update(status="postprocessing", stage="mesh_validation", message="Validating mesh geometry and exporting GLB.")
        _save(job)
        obj_files = list(output.glob(f"{Path(settings.instantmesh_config).stem}/meshes/*.obj"))
        if not obj_files:
            raise RuntimeError("InstantMesh completed without producing an OBJ mesh.")
        obj_path = obj_files[0]
        glb_path = folder / "model.glb"
        try:
            import trimesh
            import numpy as np
            mesh = trimesh.load(obj_path, force="scene")
            if not mesh.geometry:
                raise ValueError("Mesh contains no geometry.")
            geometries = [g for g in mesh.geometry.values() if len(g.vertices) and len(g.faces)]
            if not geometries:
                raise ValueError("Mesh contains no vertices or faces.")
            if any(not np.isfinite(g.vertices).all() or g.faces.min() < 0 or g.faces.max() >= len(g.vertices) for g in geometries):
                raise ValueError("Mesh has invalid coordinates or face indices.")
            bounds = mesh.bounds
            extent = bounds[1] - bounds[0]
            largest = float(extent.max())
            if not np.isfinite(bounds).all() or largest <= 0:
                raise ValueError("Mesh has invalid or zero-size bounds.")
            mesh.apply_translation(-bounds.mean(axis=0))
            mesh.apply_scale(1.0 / largest)
            mesh.export(glb_path)
            reloaded = trimesh.load(glb_path, force="scene")
            vertices = sum(len(g.vertices) for g in reloaded.geometry.values())
            faces = sum(len(g.faces) for g in reloaded.geometry.values())
            if not vertices or not faces:
                raise ValueError("Exported GLB did not retain mesh geometry.")
        except ImportError as exc:
            raise RuntimeError("Mesh validation requires the backend trimesh dependency.") from exc
        job.update(status="completed", stage="complete", message="3D mesh is ready.",
                   result_url=f"/api/v1/jobs/{job_id}/assets/model.glb",
                   mesh={"vertices": vertices, "faces": faces, "format": "GLB",
                         "normalization": "centered and scaled to unit largest extent",
                         "duration_seconds": (datetime.now(timezone.utc)-started).total_seconds()})
        (folder / "model.obj").write_bytes(obj_path.read_bytes())
    except subprocess.TimeoutExpired:
        job.update(status="failed", stage="failed", message="InstantMesh exceeded the configured time limit.", error="Inference timed out.")
    except Exception as exc:
        logger.exception("Generation job %s failed", job_id)
        job.update(status="failed", stage="failed", message="3D generation failed.", error=str(exc)[:2000])
    finally:
        _save(job)
        with _lock:
            _active.discard(job_id)


def get_asset(job_id: str, name: str) -> Path:
    if name not in {"model.glb", "model.obj"}:
        raise FileNotFoundError("Model asset was not found.")
    job = get_job(job_id)
    if job.get("status") != "completed":
        raise FileNotFoundError("Model asset is not ready.")
    path = _job_path(job_id).parent / name
    if not path.is_file():
        raise FileNotFoundError("Model asset was not found.")
    return path
