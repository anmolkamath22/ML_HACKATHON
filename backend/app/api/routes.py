import json
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.schemas.models import GenerationRequest, InputDetail, InputResponse, JobResponse, PreprocessingConfig, PreprocessingResponse, ReconstructionRequest
from app.services.input_service import create_input
from app.services.preprocessing_service import preprocess
from app.services.storage_service import storage
from app.services.reconstruction_service import get_asset, get_job, submit_job

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    configured = bool(settings.instantmesh_repo and settings.instantmesh_python
                      and settings.instantmesh_repo.is_dir() and settings.instantmesh_python.is_file()
                      and (settings.instantmesh_repo / "run.py").is_file()
                      and (settings.instantmesh_repo / settings.instantmesh_config).is_file())
    return {"status": "ok", "version": settings.app_version, "opencv_available": True,
            "storage_available": storage.root.is_dir(), "inference_configured": configured,
            "inference_worker_available": configured}


async def _create(file: UploadFile, source: str, scene_json: str | None = None) -> dict:
    name = file.filename or "sketch.png"
    suffix = Path(name).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(415, "Only PNG, JPG, JPEG, and WEBP files are supported.")
    data = await file.read(get_settings().max_upload_bytes + 1)
    try:
        return create_input(data, name, source, scene_json)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/inputs/upload", response_model=InputResponse, status_code=201)
async def upload_image(file: UploadFile = File(...)) -> dict:
    return await _create(file, "upload")


@router.post("/inputs/drawing", response_model=InputResponse, status_code=201)
async def upload_drawing(image: UploadFile = File(...), scene_json: str | None = Form(default=None), source: str = Form(default="drawing")) -> dict:
    return await _create(image, "drawing", scene_json)


@router.get("/inputs/{input_id}", response_model=InputDetail)
def get_input(input_id: str) -> dict:
    try:
        folder = storage.input_dir(input_id)
    except ValueError as exc:
        raise HTTPException(404, "Input not found.") from exc
    metadata_path = folder / "metadata.json"
    if not metadata_path.is_file():
        raise HTTPException(404, "Input not found.")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    processed_root = storage.root / "processed" / input_id
    artifacts = []
    if processed_root.is_dir():
        for result_file in processed_root.glob("*/result.json"):
            result = json.loads(result_file.read_text(encoding="utf-8"))
            artifacts.extend(result["available_artifacts"])
    return {**metadata, "artifacts": artifacts}


@router.post("/inputs/{input_id}/preprocess", response_model=PreprocessingResponse)
def preprocess_input(input_id: str, config: PreprocessingConfig = PreprocessingConfig()) -> dict:
    try:
        UUID(input_id)
        return preprocess(input_id, config)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, "Image preprocessing failed.") from exc


@router.get("/inputs/{input_id}/artifacts/original.png")
def original_artifact(input_id: str) -> FileResponse:
    path = storage.input_dir(input_id) / "original.png"
    if not path.is_file():
        raise HTTPException(404, "Artifact not found.")
    return FileResponse(path, media_type="image/png", filename="original.png")


@router.get("/inputs/{input_id}/processing/{processing_id}/{artifact_name}")
def processed_artifact(input_id: str, processing_id: str, artifact_name: str) -> FileResponse:
    if artifact_name not in {"original.png", "normalized.png", "grayscale.png", "enhanced.png", "edges.png", "binary.png", "preprocessed.png"}:
        raise HTTPException(404, "Artifact not found.")
    try:
        path = storage.root / "processed" / str(UUID(input_id)) / str(UUID(processing_id)) / artifact_name
    except ValueError as exc:
        raise HTTPException(404, "Artifact not found.") from exc
    if not path.is_file():
        raise HTTPException(404, "Artifact not found.")
    return FileResponse(path, media_type="image/png", filename=artifact_name)


@router.post("/generate", response_model=JobResponse, status_code=202)
@router.post("/reconstruction", response_model=JobResponse, status_code=202)
def create_generation(request: GenerationRequest | ReconstructionRequest) -> dict:
    try:
        return submit_job(request.input_id, request.processing_id, request.selected_artifact, request.prompt)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/jobs/{job_id}", response_model=JobResponse)
def job_status(job_id: str) -> dict:
    try:
        UUID(job_id)
        return get_job(job_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, "Generation job was not found.") from exc


@router.get("/jobs/{job_id}/result")
def job_result(job_id: str) -> dict:
    job = job_status(job_id)
    if job["status"] != "completed":
        raise HTTPException(409, "Generation result is not ready.")
    return {"job_id": job_id, "status": job["status"], "mesh": job.get("mesh"),
            "formats": [{"format": "GLB", "url": job["result_url"]},
                        {"format": "OBJ", "url": f"/api/v1/jobs/{job_id}/assets/model.obj"}]}


@router.get("/jobs/{job_id}/assets/{name}")
def job_asset(job_id: str, name: str) -> FileResponse:
    try:
        UUID(job_id)
        path = get_asset(job_id, name)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, "Model asset was not found.") from exc
    media_type = "model/gltf-binary" if name == "model.glb" else "text/plain"
    return FileResponse(path, media_type=media_type, filename=name)
