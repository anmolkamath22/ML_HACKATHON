from pathlib import Path
import time

import cv2
import numpy as np
from PIL import Image

from app.schemas.models import PreprocessingConfig


def load_image(path: Path, background: str = "white") -> np.ndarray:
    with Image.open(path) as source:
        image = source.convert("RGBA")
    bg = (0, 0, 0, 255) if background.lower() in {"black", "dark"} else (255, 255, 255, 255)
    canvas = Image.new("RGBA", image.size, bg)
    return cv2.cvtColor(np.asarray(Image.alpha_composite(canvas, image).convert("RGB")), cv2.COLOR_RGB2BGR)


def resize_image(image: np.ndarray, maximum: int) -> np.ndarray:
    h, w = image.shape[:2]
    scale = min(1.0, maximum / max(h, w))
    if scale == 1.0:
        return image
    return cv2.resize(image, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)


def run_pipeline(source: Path, output_dir: Path, config: PreprocessingConfig) -> dict:
    started = time.perf_counter()
    original = load_image(source, config.background)
    normalized = resize_image(original, config.max_dimension)
    gray = cv2.cvtColor(normalized, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, None, config.denoise_strength, 7, 21) if config.denoise else gray
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(denoised) if config.enhance_contrast else denoised
    edges = cv2.Canny(enhanced, config.canny_low, config.canny_high) if config.detect_edges else np.zeros_like(enhanced)
    if config.threshold_method == "otsu":
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        window = max(3, min(31, (min(enhanced.shape) // 8) | 1))
        binary = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, window, 7)
    chosen = {"enhanced": enhanced, "normalized": normalized, "edges": edges, "binary": binary}[config.recommendation]
    artifacts = {
        "original.png": original,
        "normalized.png": normalized,
        "grayscale.png": gray,
        "enhanced.png": enhanced,
        "edges.png": edges,
        "binary.png": binary,
        "preprocessed.png": chosen,
    }
    for name, image in artifacts.items():
        if not cv2.imwrite(str(output_dir / name), image):
            raise RuntimeError(f"Could not write {name}.")
    return {"width": normalized.shape[1], "height": normalized.shape[0], "color_mode": "grayscale", "processing_duration_ms": round((time.perf_counter() - started) * 1000, 2), "files": list(artifacts), "recommended_image": config.recommendation}
