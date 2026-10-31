from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings

ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}


def inspect_image(data: bytes) -> tuple[Image.Image, str, int, int]:
    settings = get_settings()
    if not data:
        raise ValueError("The uploaded image is empty.")
    if len(data) > settings.max_upload_bytes:
        raise ValueError(f"Image exceeds the {settings.max_upload_bytes // (1024 * 1024)} MB upload limit.")
    try:
        with Image.open(BytesIO(data)) as probe:
            fmt = (probe.format or "").upper()
            width, height = probe.size
            if fmt not in ALLOWED_FORMATS:
                raise ValueError("Only PNG, JPEG, and WEBP images are supported.")
            if width <= 0 or height <= 0 or width * height > settings.max_image_pixels:
                raise ValueError("Image dimensions exceed the supported pixel limit.")
            if max(width, height) > settings.max_image_dimension:
                raise ValueError("An image dimension exceeds the supported maximum.")
            probe.verify()
        with Image.open(BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image).copy()
            image.load()
        return image, fmt, image.width, image.height
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith(("Only PNG", "Image dimensions", "An image dimension")):
            raise
        raise ValueError("The file is not a valid supported image.") from exc
