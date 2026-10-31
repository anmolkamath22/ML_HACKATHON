from pathlib import Path

import numpy as np
import pytest
import trimesh
from PIL import Image, ImageDraw

from app.cv.pipeline import extract_foreground, prepare_reconstruction_input
from app.services import mesh_service
from app.services.job_store import JobStore


def _write_box(path: Path, extra: str = "") -> Path:
    box = trimesh.creation.box(extents=(2.0, 0.5, 1.0))
    box.visual.vertex_colors = np.tile([200, 40, 40, 255], (len(box.vertices), 1))
    path.write_text(box.export(file_type="obj") + extra)
    return path


def test_mesh_pipeline_preserves_vertex_colours(tmp_path):
    meshes, report = mesh_service.load_and_prepare(_write_box(tmp_path / "box.obj"), convert_z_up=True, max_faces=10_000)
    assert report["has_vertex_colors"] and not report["has_texture"] and report["watertight"]
    model = mesh_service.export_glb(meshes, tmp_path / "model.glb", report)
    assert np.allclose(model["dimensions"], [0.25, 0.5, 1.0])
    assert model["glb_bytes"] == (tmp_path / "model.glb").stat().st_size
    reloaded = trimesh.load(tmp_path / "model.glb", force="scene")
    colors = next(iter(reloaded.geometry.values())).visual.vertex_colors
    assert (colors[:, :3] == [200, 40, 40]).all()


def test_mesh_pipeline_preserves_texture(tmp_path):
    box = trimesh.creation.box(extents=(1, 1, 1))
    texture = Image.new("RGB", (8, 8), (10, 120, 200))
    box.visual = trimesh.visual.TextureVisuals(uv=np.random.default_rng(0).random((len(box.vertices), 2)), image=texture)
    box.export(tmp_path / "textured.obj")
    meshes, report = mesh_service.load_and_prepare(tmp_path / "textured.obj", convert_z_up=False, max_faces=10_000)
    assert report["has_texture"]
    mesh_service.export_glb(meshes, tmp_path / "model.glb", report)
    reloaded = next(iter(trimesh.load(tmp_path / "model.glb", force="scene").geometry.values()))
    assert reloaded.visual.kind == "texture"


def test_degenerate_faces_removed(tmp_path):
    path = _write_box(tmp_path / "box.obj", "f 1 1 2\n")
    meshes, report = mesh_service.load_and_prepare(path, convert_z_up=False, max_faces=10_000)
    assert report["degenerate_faces_removed"] == 1 and sum(len(m.faces) for m in meshes) == 12


@pytest.mark.parametrize("content, message", [
    ("", "no vertices"),
    ("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 9\n", ""),
    ("v 0 0 0\nv 0 0 0\nv 0 0 0\nf 1 2 3\n", ""),
])
def test_invalid_meshes_rejected(tmp_path, content, message):
    path = tmp_path / "bad.obj"
    path.write_text(content)
    with pytest.raises(mesh_service.MeshError, match=message):
        mesh_service.load_and_prepare(path, convert_z_up=True, max_faces=10_000)


def test_face_limit(tmp_path):
    with pytest.raises(mesh_service.MeshError, match="face limit"):
        mesh_service.load_and_prepare(_write_box(tmp_path / "box.obj"), convert_z_up=True, max_faces=4)


def test_foreground_keeps_enclosed_interior():
    image = Image.new("RGB", (300, 300), "white")
    ImageDraw.Draw(image).ellipse((60, 60, 240, 240), outline="black", width=3)
    mask = extract_foreground(np.asarray(image)[:, :, ::-1].copy())
    assert mask[150, 150] == 255 and mask[5, 5] == 0 and mask[150, 20] == 0


def test_prepare_modes(tmp_path):
    sketch = tmp_path / "sketch.png"
    image = Image.new("RGB", (500, 300), "white")
    ImageDraw.Draw(image).rectangle((50, 100, 150, 200), outline="black", width=3)
    image.save(sketch)
    cut = prepare_reconstruction_input(sketch, tmp_path / "cut.png", remove_background=False)
    assert cut["mode"] == "opencv_cutout" and not cut["use_rembg"]
    out = np.asarray(Image.open(tmp_path / "cut.png"))
    assert out.shape == (640, 640, 4) and out[320, 320, 3] == 255 and out[0, 0, 3] == 0
    ys, xs = np.nonzero(out[:, :, 3])
    assert max(np.ptp(ys), np.ptp(xs)) + 1 == pytest.approx(640 * 0.85, abs=3)  # object fills 85% of the canvas
    assert (ys.min() + ys.max()) / 2 == pytest.approx(320, abs=2) and (xs.min() + xs.max()) / 2 == pytest.approx(320, abs=2)

    rembg = prepare_reconstruction_input(sketch, tmp_path / "rgb.png", remove_background=True)
    assert rembg["mode"] == "rembg" and rembg["use_rembg"] and Image.open(tmp_path / "rgb.png").mode == "RGB"

    transparent = tmp_path / "alpha.png"
    rgba = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    ImageDraw.Draw(rgba).rectangle((40, 40, 160, 160), fill=(255, 0, 0, 255))
    rgba.save(transparent)
    assert prepare_reconstruction_input(transparent, tmp_path / "a.png", remove_background=True)["mode"] == "alpha"

    blank = tmp_path / "blank.png"
    Image.new("RGB", (200, 200), "white").save(blank)
    with pytest.raises(ValueError, match="No object"):
        prepare_reconstruction_input(blank, tmp_path / "b.png", remove_background=False)


def test_job_store_transitions(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    base = {"input_id": "i", "source": "upload", "status": "queued", "stage": "queued", "message": "", "options": {}, "created_at": "2026-01-01"}
    store.create({**base, "job_id": "a"})
    store.create({**base, "job_id": "b"})
    assert store.queue_position("b", "2026-01-01") == 2
    assert store.update("a", only_if_status=("queued",), status="generating")
    assert not store.update("a", only_if_status=("queued",), status="cancelled")
    assert store.get("a")["status"] == "generating" and store.count_active() == 2
    assert store.queue_position("b", "2026-01-01") == 2  # one running job ahead
    store.update("a", status="completed", result={"model": {"faces": 1}})
    assert store.get("a")["result"] == {"model": {"faces": 1}} and [job["job_id"] for job in store.active()] == ["b"]
    with pytest.raises(KeyError):
        store.update("a", bogus=1)
