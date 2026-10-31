from io import BytesIO
import time

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

client = TestClient(app)


def image_bytes(fmt="PNG", mode="RGB"):
    image = Image.new(mode, (96, 64), 0 if mode == "L" else (255, 255, 255, 0) if mode == "RGBA" else "white")
    out = BytesIO(); image.save(out, format=fmt); return out.getvalue()


def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200 and response.json()["status"] == "ok"


def test_upload_and_preprocess():
    created = client.post("/api/v1/inputs/upload", files={"file": ("sketch.png", image_bytes(), "image/png")})
    assert created.status_code == 201
    input_id = created.json()["input_id"]
    result = client.post(f"/api/v1/inputs/{input_id}/preprocess", json={})
    assert result.status_code == 200
    assert {item["name"] for item in result.json()["available_artifacts"]} >= {"original.png", "preprocessed.png", "edges.png"}
    original = client.get(f"/api/v1/inputs/{input_id}/artifacts/original.png")
    assert original.status_code == 200 and Image.open(BytesIO(original.content)).size == (96, 64)


def test_jpeg_and_webp_uploads():
    for fmt, extension, mime in [("JPEG", "jpg", "image/jpeg"), ("WEBP", "webp", "image/webp")]:
        response = client.post("/api/v1/inputs/upload", files={"file": (f"sketch.{extension}", image_bytes(fmt), mime)})
        assert response.status_code == 201


def test_invalid_and_corrupt_images_rejected():
    invalid = client.post("/api/v1/inputs/upload", files={"file": ("sketch.svg", b"<svg/>", "image/svg+xml")})
    corrupt = client.post("/api/v1/inputs/upload", files={"file": ("sketch.png", b"not an image", "image/png")})
    assert invalid.status_code == 415
    assert corrupt.status_code == 400


def test_drawing_and_generation_job():
    drawing = client.post("/api/v1/inputs/drawing", files={"image": ("drawing.png", image_bytes("PNG", "RGBA"), "image/png")}, data={"scene_json": "{}", "source": "drawing"})
    assert drawing.status_code == 201 and drawing.json()["source"] == "drawing"
    response = client.post("/api/v1/generate", json={"input_id": drawing.json()["input_id"], "prompt": "a small toy boat"})
    assert response.status_code == 202
    job = response.json()
    assert job["job_id"] and job["prompt"] == "a small toy boat"
    for _ in range(50):
        status = client.get(f"/api/v1/jobs/{job['job_id']}").json()
        if status["status"] in {"failed", "completed"}:
            break
        time.sleep(0.02)
    assert status["status"] == "failed"  # This checkout has no configured InstantMesh environment.
    assert "not configured" in status["error"]


def test_processed_artifact_requires_processing_id():
    created = client.post("/api/v1/inputs/upload", files={"file": ("sketch.png", image_bytes(), "image/png")})
    response = client.post("/api/v1/generate", json={"input_id": created.json()["input_id"], "selected_artifact": "enhanced.png"})
    assert response.status_code == 400


def test_missing_input():
    response = client.get("/api/v1/inputs/00000000-0000-0000-0000-000000000001")
    assert response.status_code == 404
