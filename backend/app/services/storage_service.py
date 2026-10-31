import json
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings


class StorageService:
    def __init__(self) -> None:
        self.root = get_settings().storage_root
        for directory in ("inputs", "processed", "jobs"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)

    def input_dir(self, input_id: str) -> Path:
        safe_id = str(UUID(input_id))
        path = (self.root / "inputs" / safe_id).resolve()
        if not path.is_relative_to((self.root / "inputs").resolve()):
            raise ValueError("Invalid input identifier.")
        return path

    def processing_dir(self, input_id: str, processing_id: str) -> Path:
        safe_processing = str(UUID(processing_id))
        path = (self.root / "processed" / str(UUID(input_id)) / safe_processing).resolve()
        path.mkdir(parents=True, exist_ok=False)
        return path

    @staticmethod
    def write_json(path: Path, data: dict) -> None:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


storage = StorageService()
