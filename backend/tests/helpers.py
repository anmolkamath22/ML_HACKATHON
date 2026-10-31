import time
from io import BytesIO

from PIL import Image, ImageDraw

TERMINAL = {"completed", "failed", "cancelled"}


def encode(image: Image.Image, fmt: str = "PNG") -> bytes:
    out = BytesIO()
    image.save(out, format=fmt)
    return out.getvalue()


def blank_image(fmt="PNG", mode="RGB", size=(96, 64)) -> bytes:
    color = 0 if mode == "L" else (255, 255, 255, 0) if mode == "RGBA" else "white"
    return encode(Image.new(mode, size, color), fmt)


def cube_sketch() -> bytes:
    """A line drawing of a cube, like an Excalidraw export: dark strokes on white."""
    image = Image.new("RGB", (400, 360), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 130, 260, 310), outline="#1e1e1e", width=4)
    draw.rectangle((150, 60, 330, 240), outline="#1e1e1e", width=4)
    for (x1, y1), (x2, y2) in zip([(80, 130), (260, 130), (80, 310), (260, 310)], [(150, 60), (330, 60), (150, 240), (330, 240)]):
        draw.line((x1, y1, x2, y2), fill="#1e1e1e", width=4)
    return encode(image)


def bottle_photo() -> bytes:
    """A synthetic product shot: a coloured bottle silhouette on a light grey backdrop."""
    image = Image.new("RGB", (480, 640), (228, 230, 232))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((170, 220, 310, 590), radius=40, fill=(40, 110, 70))
    draw.rectangle((215, 120, 265, 230), fill=(40, 110, 70))
    draw.rectangle((210, 95, 270, 125), fill=(200, 60, 40))
    return encode(image, "JPEG")


def wait_for(client, job_id: str, statuses=TERMINAL, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    job = {}
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in statuses:
            return job
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} did not reach {statuses}; last state {job}")


def submit(client, data: bytes | None = None, *, filename="sketch.png", mime="image/png", **form):
    files = {"image": (filename, data if data is not None else cube_sketch(), mime)}
    form.setdefault("source", "drawing")
    return client.post("/api/v1/generate", files=files, data={key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in form.items()})
