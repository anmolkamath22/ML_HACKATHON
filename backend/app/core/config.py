from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Sketch2Shape AI"
    app_version: str = "1.1.0"
    storage_root: Path = Path("../storage")
    max_upload_bytes: int = 10 * 1024 * 1024
    max_image_pixels: int = 25_000_000
    max_image_dimension: int = 12_000
    max_prompt_length: int = 500
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    instantmesh_repo: Path | None = None
    instantmesh_python: Path | None = None
    instantmesh_config: str = "configs/instant-mesh-large.yaml"
    inference_timeout_seconds: int = 1800
    # Jobs that are queued or running at once; the GPU itself only ever runs one.
    max_active_jobs: int = 4
    # InstantMesh's run.py writes Z-up OBJ files; glTF is Y-up. The official
    # Gradio app applies the same axis rotation before writing its GLB.
    mesh_convert_z_up: bool = True
    mesh_max_faces: int = 2_000_000
    gpu_sample_interval_seconds: float = 2.0
    # Runs with INSTANTMESH_PYTHON; overridable for tests or other environments.
    gpu_probe_script: Path = _BACKEND / "inference_scripts" / "gpu_probe.py"
    # Sketch -> image with Stable Diffusion 1.5 + ControlNet before InstantMesh.
    controlnet_enabled: bool = True
    controlnet_python: Path | None = None  # defaults to INSTANTMESH_PYTHON
    controlnet_script: Path = _BACKEND / "inference_scripts" / "controlnet_refine.py"
    controlnet_base_model: str = "stable-diffusion-v1-5/stable-diffusion-v1-5"
    controlnet_model: str = "lllyasviel/control_v11p_sd15_scribble"
    controlnet_steps: int = 20
    controlnet_guidance: float = 7.5
    controlnet_conditioning_scale: float = 1.0
    controlnet_memory: Literal["auto", "full", "offload"] = "auto"
    controlnet_timeout_seconds: int = 900
    # Built frontend served by the backend, so one address works from any device.
    frontend_dist: Path = _BACKEND.parent / "frontend" / "dist"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    @property
    def origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.storage_root.is_absolute():
        settings.storage_root = (_BACKEND / settings.storage_root).resolve()
    return settings
