from typing import Any, Literal

from pydantic import BaseModel, Field


class Artifact(BaseModel):
    name: str
    url: str


class InputResponse(BaseModel):
    input_id: str
    source: Literal["drawing", "upload"]
    filename: str
    width: int
    height: int
    format: str
    created_at: str
    status: str = "stored"
    original_url: str


class InputDetail(InputResponse):
    artifacts: list[Artifact] = Field(default_factory=list)


class PreprocessingConfig(BaseModel):
    max_dimension: int = Field(default=1536, ge=64, le=4096)
    denoise: bool = True
    denoise_strength: int = Field(default=5, ge=1, le=15)
    enhance_contrast: bool = True
    detect_edges: bool = True
    canny_low: int = Field(default=50, ge=0, le=254)
    canny_high: int = Field(default=150, ge=1, le=255)
    threshold_method: Literal["adaptive", "otsu"] = "adaptive"
    background: str = "white"
    recommendation: Literal["enhanced", "normalized", "edges", "binary"] = "enhanced"


class PreprocessingResponse(BaseModel):
    input_id: str
    processing_id: str
    status: str
    width: int
    height: int
    color_mode: str
    processing_duration_ms: float
    processing_config: dict[str, Any]
    recommended_image: str
    available_artifacts: list[Artifact]


class ReconstructionRequest(BaseModel):
    input_id: str
    processing_id: str | None = None
    selected_artifact: str = "preprocessed.png"
    settings: dict[str, Any] = Field(default_factory=dict)
    prompt: str | None = None
