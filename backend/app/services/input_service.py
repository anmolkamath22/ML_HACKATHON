from datetime import datetime, timezone
from uuid import uuid4

from app.services.storage_service import storage
from app.utils.image_validation import inspect_image


def create_input(data: bytes, filename: str, source: str, scene_json: str | None = None) -> dict:
    image, fmt, width, height = inspect_image(data)
    input_id = str(uuid4())
    folder = storage.input_dir(input_id)
    folder.mkdir(parents=True, exist_ok=False)
    image_path = folder / "original.png"
    image.save(image_path, format="PNG")
    if scene_json:
        (folder / "scene.json").write_text(scene_json, encoding="utf-8")
    result = {
        "input_id": input_id,
        "source": source,
        "filename": filename[:255],
        "width": width,
        "height": height,
        "format": fmt,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "stored",
        "original_url": f"/api/v1/inputs/{input_id}/artifacts/original.png",
    }
    storage.write_json(folder / "metadata.json", result)
    return result
