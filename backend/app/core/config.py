from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sketch2Shape AI"
    app_version: str = "0.1.0"
    storage_root: Path = Path("../storage")
    max_upload_bytes: int = 10 * 1024 * 1024
    max_image_pixels: int = 25_000_000
    max_image_dimension: int = 12_000
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.storage_root.is_absolute():
        settings.storage_root = (Path(__file__).resolve().parents[2] / settings.storage_root).resolve()
    return settings
