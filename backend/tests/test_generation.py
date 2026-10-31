"""Generation pipeline tests. Every GPU stage is replaced by a test double in tests/fixtures:
fake_instantmesh mirrors the official CLI and output layout but writes a fixed box mesh,
fake_controlnet mirrors controlnet_refine.py, and fake_gpu_probe reports a chosen GPU."""
import json
from io import BytesIO
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

from app.core.config import get_settings
from app.services import generation_service
from tests.helpers import blank_image, bottle_photo, cube_sketch, submit, wait_for


def _argv(job_id: str) -> list[str]:
    return (generation_service.job_dir(job_id) / "instantmesh" / "argv.txt").read_text().splitlines()


def _controlnet_argv(job_id: str) -> list[str]:
    return json.loads((generation_service.job_dir(job_id) / "controlnet_argv.json").read_text())


def test_sketch_to_glb_end_to_end(client):
    response = submit(client, prompt="  a wooden\n crate  ")
    assert response.status_code == 202
    body = response.json()
    assert body["success"] is True and body["status"] == "queued" and body["message"] == "Generation submitted successfully"
    assert body["status_url"] == f"/api/v1/jobs/{body['job_id']}"
    job = wait_for(client, body["job_id"])
    assert job["status"] == "completed", job
    assert job["prompt"] == "a wooden crate"
    assert job["options"] == {"refine_sketch": True, "remove_background": False, "diffusion_steps": 75, "seed": 42, "export_texture": False}
    assert job["started_at"] and job["completed_at"] and job["error"] is None
    assert {"input_seconds", "preprocessing_seconds", "refinement_seconds", "inference_seconds", "postprocessing_seconds",
            "export_seconds", "total_seconds"} <= set(job["timings"])

    # The OpenCV cutout: RGBA, transparent background, square canvas, interior kept.
    preview = Image.open(BytesIO(client.get(job["preview_url"]).content))
    assert preview.mode == "RGBA" and preview.size == (640, 640)
    alpha = np.asarray(preview)[:, :, 3]
    assert alpha[0, 0] == 0 and alpha[320, 320] == 255
    # ControlNet input is white strokes on black; its prompt carries the user's description.
    control = np.asarray(Image.open(BytesIO(client.get(job["control_url"]).content)).convert("L"))
    assert control.shape == (512, 512) and control[0, 0] == 0 and control.max() == 255 and (control > 0).mean() < 0.3
    controlnet_argv = _controlnet_argv(job["job_id"])
    assert controlnet_argv[controlnet_argv.index("--prompt") + 1].startswith("a wooden crate, single object")
    assert job["refinement"]["status"] == "used" and client.get(job["refined_url"]).status_code == 200
    # InstantMesh receives the ControlNet image and removes its background with rembg.
    argv = _argv(job["job_id"])
    assert argv[1].endswith("refined.png") and "--no_rembg" not in argv
    assert client.get(job["multiview_url"]).status_code == 200

    result = client.get(f"/api/v1/jobs/{job['job_id']}/result").json()
    assert result["success"] and result["obj_format"] == "obj"
    model = result["model"]
    assert model["vertices"] == 8 and model["faces"] == 12 and model["has_vertex_colors"]
    # The fake box is 2 (x) x 0.5 (y) x 1 (z), Z-up; after Y-up conversion and unit scaling:
    assert np.allclose(model["dimensions"], [0.25, 0.5, 1.0])
    assert np.allclose(model["source_dimensions"], [2.0, 0.5, 1.0])

    glb = client.get(result["glb_url"])
    assert glb.status_code == 200 and glb.headers["content-type"] == "model/gltf-binary"
    assert f'sketch2shape-{job["job_id"][:8]}.glb' in glb.headers["content-disposition"]
    scene = trimesh.load(BytesIO(glb.content), file_type="glb", force="scene")
    mesh = next(iter(scene.geometry.values()))
    assert np.allclose(scene.extents, [0.25, 0.5, 1.0]) and np.allclose(scene.bounds.mean(axis=0), 0, atol=1e-6)
    assert mesh.visual.kind == "vertex"
    obj = client.get(result["obj_url"])
    assert obj.status_code == 200 and obj.headers["content-type"].startswith("model/obj") and obj.text.startswith("v ")


def test_photo_upload_uses_rembg_and_options(client):
    response = submit(client, bottle_photo(), filename="bottle.jpg", mime="image/jpeg", source="upload",
                      diffusion_steps=30, seed=7, export_texture="false")
    job = wait_for(client, response.json()["job_id"])
    assert job["status"] == "completed" and job["source"] == "upload" and job["prompt"] is None
    assert job["options"]["refine_sketch"] is False and job["refinement"]["status"] == "off" and job["refined_url"] is None
    argv = _argv(job["job_id"])
    assert "--no_rembg" not in argv and argv[argv.index("--diffusion_steps") + 1] == "30" and argv[argv.index("--seed") + 1] == "7"


def test_uploaded_sketch_is_refined_automatically(client):
    job = wait_for(client, submit(client, cube_sketch(), filename="scan.png", source="upload").json()["job_id"])
    assert job["status"] == "completed" and job["options"]["refine_sketch"] is True and job["refinement"]["status"] == "used"


def test_refinement_can_be_turned_off(client):
    job = wait_for(client, submit(client, refine_sketch=False).json()["job_id"])
    assert job["status"] == "completed" and job["refinement"]["status"] == "off" and job["control_url"] is None
    argv = _argv(job["job_id"])
    assert argv[1].endswith("reconstruction_input.png") and "--no_rembg" in argv


def test_controlnet_failure_falls_back_to_cutout(client, monkeypatch):
    for mode, code in {"oom": "gpu_out_of_memory", "missing_weights": "model_weights_unavailable", "no_output": "refinement_failed"}.items():
        monkeypatch.setenv("FAKE_CONTROLNET_MODE", mode)
        job = wait_for(client, submit(client).json()["job_id"])
        assert job["status"] == "completed", (mode, job)
        assert job["refinement"]["status"] == "skipped" and job["refinement"]["code"] == code
        assert "Used the sketch cutout instead" in job["refinement"]["message"] and job["refined_url"] is None
        argv = _argv(job["job_id"])
        assert argv[1].endswith("reconstruction_input.png") and "--no_rembg" in argv


def test_cancel_during_refinement(client, monkeypatch):
    monkeypatch.setenv("FAKE_CONTROLNET_MODE", "hang")
    job_id = submit(client).json()["job_id"]
    running = wait_for(client, job_id, {"refining"})
    assert running["stage"].startswith("controlnet")
    client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert wait_for(client, job_id, timeout=30)["status"] == "cancelled"
    assert not (generation_service.job_dir(job_id) / "instantmesh").exists()


def test_generation_needs_a_supported_gpu(client, fake_gpu):
    expected = {"none": ("gpu_unavailable", "No CUDA-capable NVIDIA GPU"), "rocm": ("gpu_unsupported", "AMD Radeon RX 7600"),
                "mps": ("gpu_unsupported", "Apple GPU"), "old_torch": ("gpu_unsupported", "PyTorch 2.1.0"),
                "broken": ("gpu_unavailable", "libcudart")}
    for profile, (code, text) in expected.items():
        fake_gpu(profile)
        response = submit(client)
        assert response.status_code == 503 and response.json()["error"]["code"] == code, profile
        assert text in response.json()["error"]["message"]
        health = client.get("/api/v1/health").json()
        assert health["inference"]["ready"] is False and text in health["inference"]["reason"]
    fake_gpu("cuda")
    assert submit(client).status_code == 202


def test_upload_can_use_opencv_cutout(client):
    job = wait_for(client, submit(client, bottle_photo(), filename="bottle.jpg", mime="image/jpeg", source="upload",
                                  remove_background=False).json()["job_id"])
    assert job["status"] == "completed" and "--no_rembg" in _argv(job["job_id"])
    alpha = np.asarray(Image.open(BytesIO(client.get(job["preview_url"]).content)))[:, :, 3]
    assert alpha[0, 0] == 0 and alpha[320, 320] == 255


def test_progress_reports_real_diffusion_steps(client, monkeypatch):
    monkeypatch.setenv("FAKE_INSTANTMESH_STEP_DELAY", "0.05")
    job_id = submit(client, diffusion_steps=40).json()["job_id"]
    seen = wait_for(client, job_id, {"generating"})
    progress = []
    while seen["status"] not in {"completed", "failed"}:
        if seen["stage"] == "multiview_diffusion" and seen["progress"] is not None:
            progress.append(seen["progress"])
            assert "/40 diffusion steps" in seen["message"]
        seen = client.get(f"/api/v1/jobs/{job_id}").json()
    assert seen["status"] == "completed"
    assert progress and progress == sorted(progress) and all(0 <= value <= 100 for value in progress)


def test_retry_from_stored_input(client):
    first = wait_for(client, submit(client).json()["job_id"])
    again = client.post("/api/v1/generate", data={"input_id": first["input_id"], "seed": "3"})
    assert again.status_code == 202
    job = wait_for(client, again.json()["job_id"])
    assert job["status"] == "completed" and job["input_id"] == first["input_id"] and job["source"] == "drawing"


def test_generate_validation(client):
    assert client.post("/api/v1/generate", data={}).status_code == 400
    both = client.post("/api/v1/generate", files={"image": ("a.png", blank_image(), "image/png")},
                       data={"input_id": "00000000-0000-0000-0000-000000000001"})
    assert both.status_code == 400
    steps = submit(client, diffusion_steps=5)
    assert steps.status_code == 422 and steps.json()["error"]["code"] == "validation_error"
    long_prompt = submit(client, prompt="x" * 501)
    assert long_prompt.status_code == 422 and long_prompt.json()["error"]["code"] == "invalid_prompt"
    assert client.post("/api/v1/generate", data={"input_id": "nope"}).status_code == 404
    assert submit(client, b"not an image").status_code == 400
    assert submit(client, filename="x.gif").status_code == 415


def test_blank_drawing_fails_with_clear_error(client):
    job = wait_for(client, submit(client, blank_image(size=(300, 300))).json()["job_id"])
    assert job["status"] == "failed" and job["error"]["code"] == "invalid_input" and "No object" in job["error"]["message"]


def test_failure_modes_are_classified(client, monkeypatch):
    expected = {"oom": "gpu_out_of_memory", "missing_weights": "model_weights_unavailable", "crash": "inference_failed",
                "no_output": "no_mesh_output", "nan": "invalid_mesh"}
    for mode, code in expected.items():
        monkeypatch.setenv("FAKE_INSTANTMESH_MODE", mode)
        job = wait_for(client, submit(client).json()["job_id"])
        assert job["status"] == "failed" and job["error"]["code"] == code, (mode, job)
        message = job["error"]["message"]
        assert "Traceback" not in message and get_settings().storage_root.as_posix() not in message.replace("\\", "/")
        result = client.get(f"/api/v1/jobs/{job['job_id']}/result")
        assert result.status_code == 409 and result.json()["error"]["code"] == "job_failed"
        assert client.get(f"/api/v1/jobs/{job['job_id']}/download/glb").status_code == 409


def test_cancel_running_job_stops_process(client, monkeypatch):
    monkeypatch.setenv("FAKE_INSTANTMESH_MODE", "hang")
    job_id = submit(client).json()["job_id"]
    wait_for(client, job_id, {"generating"})
    response = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert response.status_code == 202
    job = wait_for(client, job_id, timeout=30)
    assert job["status"] == "cancelled" and job["completed_at"]
    assert client.post(f"/api/v1/jobs/{job_id}/cancel").status_code == 409
    assert client.get(f"/api/v1/jobs/{job_id}/result").json()["error"]["code"] == "job_cancelled"


def test_cancel_queued_job_and_queue_limit(client, monkeypatch):
    monkeypatch.setenv("FAKE_INSTANTMESH_MODE", "hang")
    monkeypatch.setattr(get_settings(), "max_active_jobs", 2)
    running = submit(client).json()["job_id"]
    wait_for(client, running, {"generating"})
    queued = submit(client).json()
    assert queued["job"]["queue_position"] == 2
    full = submit(client)
    assert full.status_code == 503 and full.json()["error"]["code"] == "queue_full"
    assert client.post(f"/api/v1/jobs/{queued['job_id']}/cancel").json()["status"] == "cancelled"
    client.post(f"/api/v1/jobs/{running}/cancel")
    assert wait_for(client, running)["status"] == "cancelled"


def test_timeout(client, monkeypatch):
    monkeypatch.setenv("FAKE_INSTANTMESH_MODE", "hang")
    monkeypatch.setattr(get_settings(), "inference_timeout_seconds", 2)
    job = wait_for(client, submit(client).json()["job_id"], timeout=30)
    assert job["status"] == "failed" and job["error"]["code"] == "inference_timeout"


def test_not_configured_is_rejected_up_front(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "instantmesh_repo", Path("/definitely/missing"))
    response = submit(client)
    assert response.status_code == 503 and response.json()["error"]["code"] == "inference_not_configured"
    assert client.get("/api/v1/health").json()["inference"]["configured"] is False


def test_unknown_jobs_and_files(client):
    for path in ("/api/v1/jobs/00000000-0000-0000-0000-000000000001", "/api/v1/jobs/not-a-uuid",
                 "/api/v1/jobs/00000000-0000-0000-0000-000000000001/result",
                 "/api/v1/jobs/00000000-0000-0000-0000-000000000001/download/glb"):
        response = client.get(path)
        assert response.status_code == 404 and response.json()["error"]["code"] == "job_not_found", path
    job = wait_for(client, submit(client).json()["job_id"])
    assert client.get(f"/api/v1/jobs/{job['job_id']}/files/inference.log").status_code == 404
    assert client.get(f"/api/v1/jobs/{job['job_id']}/files/..%2Fjobs.db").status_code == 404
    assert client.get(f"/api/v1/jobs/{job['job_id']}/download/stl").status_code == 422


def test_job_history_lists_recent_jobs(client):
    job_id = submit(client, prompt="history check").json()["job_id"]
    wait_for(client, job_id)
    jobs = client.get("/api/v1/jobs?limit=5").json()["jobs"]
    assert jobs[0]["job_id"] == job_id and jobs[0]["prompt"] == "history check"
    assert client.get("/api/v1/jobs?limit=0").status_code == 422


def test_recovery_after_restart(client):
    job_id = wait_for(client, submit(client).json()["job_id"])["job_id"]
    generation_service.store.update(job_id, status="generating", stage="multiview_diffusion")
    generation_service.recover()
    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "failed" and job["error"]["code"] == "interrupted"
