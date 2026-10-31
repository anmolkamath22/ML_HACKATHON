from io import BytesIO

from PIL import Image

from tests.helpers import blank_image


def test_health(client):
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok" and body["version"]
    assert body["storage_available"] is True
    assert set(body["gpu"]) == {"available", "name", "memory_total_mb"}
    assert body["inference"]["configured"] is True
    assert body["inference"]["worker"] in {"idle", "busy"}


def test_upload_and_preprocess(client):
    created = client.post("/api/v1/inputs/upload", files={"file": ("sketch.png", blank_image(), "image/png")})
    assert created.status_code == 201
    input_id = created.json()["input_id"]
    result = client.post(f"/api/v1/inputs/{input_id}/preprocess", json={})
    assert result.status_code == 200
    assert {item["name"] for item in result.json()["available_artifacts"]} >= {"original.png", "preprocessed.png", "edges.png"}
    original = client.get(f"/api/v1/inputs/{input_id}/artifacts/original.png")
    assert original.status_code == 200 and Image.open(BytesIO(original.content)).size == (96, 64)
    detail = client.get(f"/api/v1/inputs/{input_id}").json()
    assert len(detail["artifacts"]) == 7


def test_jpeg_and_webp_uploads(client):
    for fmt, extension, mime in [("JPEG", "jpg", "image/jpeg"), ("WEBP", "webp", "image/webp")]:
        response = client.post("/api/v1/inputs/upload", files={"file": (f"sketch.{extension}", blank_image(fmt), mime)})
        assert response.status_code == 201


def test_invalid_and_corrupt_images_rejected(client):
    invalid = client.post("/api/v1/inputs/upload", files={"file": ("sketch.svg", b"<svg/>", "image/svg+xml")})
    corrupt = client.post("/api/v1/inputs/upload", files={"file": ("sketch.png", b"not an image", "image/png")})
    disguised = client.post("/api/v1/inputs/upload", files={"file": ("sketch.png", b"GIF89a" + b"\0" * 40, "image/png")})
    assert invalid.status_code == 415 and invalid.json()["error"]["code"] == "unsupported_media_type"
    assert corrupt.status_code == 400 and corrupt.json()["success"] is False
    assert disguised.status_code == 400


def test_oversized_upload_rejected(client, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 1000)
    response = client.post("/api/v1/inputs/upload", files={"file": ("big.png", blank_image(size=(600, 600)) + b"\0" * 2000, "image/png")})
    assert response.status_code == 400 and "upload limit" in response.json()["error"]["message"]


def test_path_like_filename_is_reduced_to_basename(client):
    response = client.post("/api/v1/inputs/upload", files={"file": ("../../etc/sketch.png", blank_image(), "image/png")})
    assert response.status_code == 201 and response.json()["filename"] == "sketch.png"


def test_drawing_input(client):
    drawing = client.post("/api/v1/inputs/drawing", files={"image": ("drawing.png", blank_image("PNG", "RGBA"), "image/png")}, data={"scene_json": "{}"})
    assert drawing.status_code == 201 and drawing.json()["source"] == "drawing"


def test_missing_and_malformed_ids(client):
    assert client.get("/api/v1/inputs/00000000-0000-0000-0000-000000000001").status_code == 404
    assert client.get("/api/v1/inputs/not-a-uuid").status_code == 404
    assert client.get("/api/v1/inputs/not-a-uuid/artifacts/original.png").status_code == 404
    assert client.get("/api/v1/inputs/..%2F..%2Fjobs/artifacts/original.png").status_code == 404
    assert client.get("/api/v1/inputs/00000000-0000-0000-0000-000000000001/processing/00000000-0000-0000-0000-000000000001/secret.txt").status_code == 404


def test_errors_use_one_envelope(client):
    body = client.get("/api/v1/nope").json()
    assert body == {"success": False, "error": {"code": "not_found", "message": "Not Found"}}
