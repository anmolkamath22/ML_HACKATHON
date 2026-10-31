from uuid import uuid4

from app.cv.pipeline import run_pipeline
from app.schemas.models import PreprocessingConfig
from app.services.storage_service import storage


def preprocess(input_id: str, config: PreprocessingConfig) -> dict:
    folder = storage.input_dir(input_id)
    source = folder / "original.png"
    if not source.is_file():
        raise FileNotFoundError("Input image was not found.")
    processing_id = str(uuid4())
    output = storage.processing_dir(input_id, processing_id)
    result = run_pipeline(source, output, config)
    payload = {
        "input_id": input_id,
        "processing_id": processing_id,
        "status": "completed",
        "width": result["width"],
        "height": result["height"],
        "color_mode": result["color_mode"],
        "processing_duration_ms": result["processing_duration_ms"],
        "processing_config": config.model_dump(),
        "recommended_image": result["recommended_image"],
        "available_artifacts": [{"name": name, "url": f"/api/v1/inputs/{input_id}/processing/{processing_id}/{name}"} for name in result["files"]],
    }
    storage.write_json(output / "result.json", payload)
    return payload
