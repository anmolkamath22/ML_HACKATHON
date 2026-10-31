import json
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.schemas.models import InputDetail, InputResponse, PreprocessingConfig, PreprocessingResponse, ReconstructionRequest
from app.services.input_service import create_input
from app.services.preprocessing_service import preprocess
from app.services.storage_service import storage

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": get_settings().app_version, "opencv_available": True, "storage_available": storage.root.is_dir()}


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


@router.post("/reconstruction")
def reconstruction_placeholder(request: ReconstructionRequest) -> None:
    raise HTTPException(501, "3D reconstruction is not implemented in this phase.")
