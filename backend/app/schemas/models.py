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


JobStatus = Literal["queued", "preprocessing", "generating", "postprocessing", "exporting", "completed", "failed", "cancelled"]
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


class GenerationOptions(BaseModel):
    # True hands background removal to InstantMesh's rembg (best for photos);
    # False uses the OpenCV cutout (best for sketches on a plain background).
    remove_background: bool
    diffusion_steps: int = Field(default=75, ge=20, le=100)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    export_texture: bool = False


class JobError(BaseModel):
    code: str
    message: str


class JobResponse(BaseModel):
    job_id: str
    input_id: str
    source: str
    status: JobStatus
    stage: str
    progress: int | None = None
    message: str
    prompt: str | None = None
    options: dict[str, Any]
    error: JobError | None = None
    queue_position: int | None = None
    input_url: str
    preview_url: str | None = None
    multiview_url: str | None = None
    result_url: str | None = None
    timings: dict[str, float] = Field(default_factory=dict)
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str


class GenerateResponse(BaseModel):
    success: bool = True
    job_id: str
    status: JobStatus
    message: str
    status_url: str
    job: JobResponse


class JobListResponse(BaseModel):
    jobs: list[JobResponse]


class ResultResponse(BaseModel):
    success: bool = True
    job_id: str
    status: Literal["completed"]
    glb_url: str
    obj_url: str
    obj_format: Literal["obj", "zip"]
    model: dict[str, Any]
    timings: dict[str, float]
