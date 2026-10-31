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


def extract_foreground(image: np.ndarray, tolerance: int = 28) -> np.ndarray:
    """Mask of everything not connected to the image border through background-coloured pixels.

    Works for sketches and product shots on a plain background: the background
    colour is sampled from the border, strokes are slightly dilated to close
    small gaps, and enclosed regions (the inside of a drawn shape) stay foreground.
    """
    h, w = image.shape[:2]
    border = np.concatenate([image[0], image[-1], image[:, 0], image[:, -1]])
    background = np.median(border, axis=0)
    ink = (np.abs(image.astype(np.int16) - background).max(axis=2) > tolerance).astype(np.uint8)
    size = max(3, round(max(h, w) / 150) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    free = (cv2.dilate(ink, kernel) == 0).astype(np.uint8)
    _, labels = cv2.connectedComponents(free, connectivity=4)
    edge_labels = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    outside = np.isin(labels, edge_labels[edge_labels > 0]) & (free == 1)
    mask = cv2.erode((~outside).astype(np.uint8) * 255, kernel)
    count, components, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 1:
        return np.zeros((h, w), np.uint8)
    areas = stats[1:, cv2.CC_STAT_AREA]
    keep = np.flatnonzero(areas >= areas.max() * 0.01) + 1
    return np.isin(components, keep).astype(np.uint8) * 255


def prepare_reconstruction_input(source: Path, destination: Path, remove_background: bool,
                                 canvas: int = 640, fill_ratio: float = 0.85, max_dimension: int = 1024) -> dict:
    """Write the image InstantMesh receives and report how it was produced.

    Images with real transparency use their alpha channel. Otherwise either the
    OpenCV cutout is used (``--no_rembg``), or the resized RGB image is passed on
    for InstantMesh's own rembg background removal and foreground resizing.
    """
    started = time.perf_counter()
    with Image.open(source) as opened:
        rgba = np.asarray(opened.convert("RGBA"))
    rgba = resize_image(rgba, max_dimension)
    alpha = rgba[:, :, 3]
    rgb = cv2.cvtColor(np.asarray(Image.alpha_composite(Image.new("RGBA", (rgba.shape[1], rgba.shape[0]), (255, 255, 255, 255)), Image.fromarray(rgba)).convert("RGB")), cv2.COLOR_RGB2BGR)
    if (alpha < 250).mean() > 0.01:
        mode, mask = "alpha", (alpha > 127).astype(np.uint8) * 255
    elif remove_background:
        if not cv2.imwrite(str(destination), rgb):
            raise RuntimeError("Could not write the reconstruction input.")
        return {"mode": "rembg", "use_rembg": True, "width": rgb.shape[1], "height": rgb.shape[0],
                "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
    else:
        mode, mask = "opencv_cutout", extract_foreground(rgb)
    coverage = float((mask > 0).mean())
    if coverage < 0.0005:
        raise ValueError("No object was found in the image. Draw or upload a clearly visible object on a plain background.")
    ys, xs = np.nonzero(mask)
    top, bottom, left, right = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    crop = np.dstack([rgb[top:bottom, left:right], mask[top:bottom, left:right]])
    scale = canvas * fill_ratio / max(crop.shape[:2])
    crop = cv2.resize(crop, (max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale))),
                      interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    output = np.zeros((canvas, canvas, 4), np.uint8)
    y, x = (canvas - crop.shape[0]) // 2, (canvas - crop.shape[1]) // 2
    output[y:y + crop.shape[0], x:x + crop.shape[1]] = crop
    if not cv2.imwrite(str(destination), output):
        raise RuntimeError("Could not write the reconstruction input.")
    return {"mode": mode, "use_rembg": False, "width": canvas, "height": canvas,
            "foreground_coverage": round(coverage, 4), "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
