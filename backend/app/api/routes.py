import json
import os
import time
import zipfile
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.schemas.models import (GenerateResponse, GenerationOptions, InputDetail, InputResponse, JobListResponse, JobResponse,
                                PreprocessingConfig, PreprocessingResponse, ResultResponse)
from app.services import generation_service as generation
from app.services.inference_service import InferenceError, locate_installation
from app.services.input_service import create_input
from app.services.preprocessing_service import preprocess
from app.services.storage_service import storage
from app.utils.gpu import list_gpus

router = APIRouter(prefix="/api/v1")
_ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def api_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    gpus = list_gpus()
    try:
        locate_installation(settings)
        configured = True
    except InferenceError:
        configured = False
    return {"status": "ok", "version": settings.app_version,
            "storage_available": storage.root.is_dir() and os.access(storage.root, os.W_OK),
            "gpu": {"available": bool(gpus), "name": gpus[0]["name"] if gpus else None,
                    "memory_total_mb": gpus[0]["memory_total_mb"] if gpus else None},
            "inference": {"configured": configured, "model_config": Path(settings.instantmesh_config).stem,
                          **generation.worker_state()}}


async def _create(file: UploadFile, source: str, scene_json: str | None = None) -> dict:
    name = Path(file.filename or "sketch.png").name
    if Path(name).suffix.lower() not in _ALLOWED_SUFFIXES:
        raise api_error(415, "unsupported_media_type", "Only PNG, JPG, JPEG, and WEBP files are supported.")
    data = await file.read(get_settings().max_upload_bytes + 1)
    try:
        return await run_in_threadpool(create_input, data, name, source, scene_json)
    except ValueError as exc:
        raise api_error(400, "invalid_image", str(exc)) from exc


@router.post("/inputs/upload", response_model=InputResponse, status_code=201)
async def upload_image(file: UploadFile = File(...)) -> dict:
    return await _create(file, "upload")


@router.post("/inputs/drawing", response_model=InputResponse, status_code=201)
async def upload_drawing(image: UploadFile = File(...), scene_json: str | None = Form(default=None)) -> dict:
    return await _create(image, "drawing", scene_json)


def _input_metadata(input_id: str) -> dict:
    try:
        metadata_path = storage.input_dir(input_id) / "metadata.json"
    except ValueError as exc:
        raise api_error(404, "input_not_found", "Input not found.") from exc
    if not metadata_path.is_file():
        raise api_error(404, "input_not_found", "Input not found.")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


@router.get("/inputs/{input_id}", response_model=InputDetail)
def get_input(input_id: str) -> dict:
    metadata = _input_metadata(input_id)
    processed_root = storage.root / "processed" / metadata["input_id"]
    artifacts = []
    if processed_root.is_dir():
        for result_file in processed_root.glob("*/result.json"):
            artifacts.extend(json.loads(result_file.read_text(encoding="utf-8"))["available_artifacts"])
    return {**metadata, "artifacts": artifacts}


@router.post("/inputs/{input_id}/preprocess", response_model=PreprocessingResponse)
def preprocess_input(input_id: str, config: PreprocessingConfig = PreprocessingConfig()) -> dict:
    try:
        UUID(input_id)
        return preprocess(input_id, config)
    except FileNotFoundError as exc:
        raise api_error(404, "input_not_found", "Input not found.") from exc
    except ValueError as exc:
        raise api_error(400, "invalid_request", str(exc)) from exc


@router.get("/inputs/{input_id}/artifacts/original.png")
def original_artifact(input_id: str) -> FileResponse:
    try:
        path = storage.input_dir(input_id) / "original.png"
    except ValueError as exc:
        raise api_error(404, "artifact_not_found", "Artifact not found.") from exc
    if not path.is_file():
        raise api_error(404, "artifact_not_found", "Artifact not found.")
    return FileResponse(path, media_type="image/png", filename="original.png")


@router.get("/inputs/{input_id}/processing/{processing_id}/{artifact_name}")
def processed_artifact(input_id: str, processing_id: str, artifact_name: str) -> FileResponse:
    if artifact_name not in {"original.png", "normalized.png", "grayscale.png", "enhanced.png", "edges.png", "binary.png", "preprocessed.png"}:
        raise api_error(404, "artifact_not_found", "Artifact not found.")
    try:
        path = storage.root / "processed" / str(UUID(input_id)) / str(UUID(processing_id)) / artifact_name
    except ValueError as exc:
        raise api_error(404, "artifact_not_found", "Artifact not found.") from exc
    if not path.is_file():
        raise api_error(404, "artifact_not_found", "Artifact not found.")
    return FileResponse(path, media_type="image/png", filename=artifact_name)


def _clean_prompt(prompt: str | None) -> str | None:
    if prompt is None:
        return None
    cleaned = " ".join("".join(char if char.isprintable() else " " for char in prompt).split())
    limit = get_settings().max_prompt_length
    if len(cleaned) > limit:
        raise api_error(422, "invalid_prompt", f"The prompt must be at most {limit} characters.")
    return cleaned or None


@router.post("/generate", response_model=GenerateResponse, status_code=202)
async def generate(
    image: Annotated[UploadFile | None, File(description="Sketch export or uploaded image (PNG, JPG or WEBP).")] = None,
    input_id: Annotated[str | None, Form(description="Reuse a stored input instead of sending an image.")] = None,
    source: Annotated[Literal["drawing", "upload"], Form()] = "upload",
    scene_json: Annotated[str | None, Form()] = None,
    prompt: Annotated[str | None, Form(description="Optional description. Stored with the job; InstantMesh geometry is image-driven.")] = None,
    remove_background: Annotated[bool | None, Form(description="Use InstantMesh rembg (default for uploads) instead of the OpenCV cutout.")] = None,
    diffusion_steps: Annotated[int, Form(ge=20, le=100)] = 75,
    seed: Annotated[int, Form(ge=0, le=2_147_483_647)] = 42,
    export_texture: Annotated[bool, Form()] = False,
) -> dict:
    if (image is None) == (input_id is None):
        raise api_error(400, "invalid_request", "Send either an image or an input_id.")
    cleaned_prompt = _clean_prompt(prompt)
    try:
        locate_installation()
    except InferenceError as exc:
        raise api_error(503, exc.code, exc.message) from exc
    timings: dict = {}
    if image is not None:
        begun = time.perf_counter()
        created = await _create(image, source, scene_json)
        timings["input_seconds"] = round(time.perf_counter() - begun, 3)
    else:
        created = _input_metadata(input_id)
    options = GenerationOptions(remove_background=created["source"] == "upload" if remove_background is None else remove_background,
                                diffusion_steps=diffusion_steps, seed=seed, export_texture=export_texture)
    try:
        job = generation.submit_job(created["input_id"], created["source"], cleaned_prompt, options, timings)
    except InferenceError as exc:
        raise api_error(503, exc.code, exc.message) from exc
    except generation.QueueFull as exc:
        raise api_error(503, "queue_full", "The generation queue is full. Wait for a job to finish, then try again.") from exc
    except FileNotFoundError as exc:
        raise api_error(404, "input_not_found", "Input not found.") from exc
    return {"success": True, "job_id": job["job_id"], "status": job["status"], "message": "Generation submitted successfully",
            "status_url": f"/api/v1/jobs/{job['job_id']}", "job": generation.public_job(job)}


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(limit: Annotated[int, Query(ge=1, le=100)] = 20) -> dict:
    return {"jobs": [generation.public_job(job) for job in generation.store.recent(limit)]}


def _job(job_id: str) -> dict:
    try:
        return generation.get_job(job_id)
    except generation.JobNotFound as exc:
        raise api_error(404, "job_not_found", "Generation job was not found.") from exc


@router.get("/jobs/{job_id}", response_model=JobResponse)
def job_status(job_id: str) -> dict:
    return generation.public_job(_job(job_id))


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse, status_code=202)
def cancel_job(job_id: str) -> dict:
    _job(job_id)
    try:
        return generation.public_job(generation.cancel_job(job_id))
    except generation.JobConflict as exc:
        raise api_error(409, exc.code, exc.message) from exc


def _result(job_id: str) -> tuple[dict, Path, Path]:
    _job(job_id)
    try:
        job, glb, obj = generation.result_paths(job_id)
    except generation.JobConflict as exc:
        raise api_error(409, exc.code, exc.message) from exc
    if not glb.is_file() or not obj.is_file():
        raise api_error(404, "asset_not_found", "The model files for this job are missing.")
    return job, glb, obj


@router.get("/jobs/{job_id}/result", response_model=ResultResponse)
def job_result(job_id: str) -> dict:
    job, _, obj = _result(job_id)
    base = f"/api/v1/jobs/{job_id}/download"
    return {"success": True, "job_id": job_id, "status": "completed", "glb_url": f"{base}/glb", "obj_url": f"{base}/obj",
            "obj_format": "zip" if job["result"]["model"]["obj_has_companion_files"] else "obj",
            "model": job["result"]["model"], "timings": job["timings"] or {}}


@router.get("/jobs/{job_id}/download/{file_format}")
def download(job_id: str, file_format: Literal["glb", "obj"]) -> FileResponse:
    job, glb, obj = _result(job_id)
    stem = f"sketch2shape-{job_id[:8]}"
    if file_format == "glb":
        return FileResponse(glb, media_type="model/gltf-binary", filename=f"{stem}.glb")
    companions = sorted(path for path in obj.parent.iterdir() if path.is_file() and path != obj)
    if not companions:
        return FileResponse(obj, media_type="model/obj", filename=f"{stem}.obj")
    # Textured OBJ output references its .mtl and texture image, so ship them together.
    archive = generation.job_dir(job_id) / "model_obj.zip"
    if not archive.is_file():
        temporary = archive.with_suffix(".zip.tmp")
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in (obj, *companions):
                bundle.write(path, path.name)
        temporary.replace(archive)
    return FileResponse(archive, media_type="application/zip", filename=f"{stem}-obj.zip")


@router.get("/jobs/{job_id}/files/{name}")
def job_file(job_id: str, name: str) -> FileResponse:
    _job(job_id)
    try:
        path = generation.job_file(job_id, name)
    except FileNotFoundError as exc:
        raise api_error(404, "file_not_found", "File not found.") from exc
    return FileResponse(path, media_type="image/png")
