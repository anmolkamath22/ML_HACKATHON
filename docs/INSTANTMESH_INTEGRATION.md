# InstantMesh integration

## Configuration

1. Keep the official TencentARC/InstantMesh checkout and its own Python environment (with its weights or Hugging Face cache) exactly as they are.
2. In `backend/.env` set `INSTANTMESH_REPO` (the checkout) and `INSTANTMESH_PYTHON` (that environment's `python`). Venv symlinks are not resolved, so a venv's `bin/python` keeps its own packages.
3. Optionally change `INSTANTMESH_CONFIG` (e.g. `configs/instant-mesh-base.yaml`) and `INFERENCE_TIMEOUT_SECONDS`.
4. `GET /api/v1/health` reports `inference.configured`. Until it is `true`, `POST /generate` returns 503 `inference_not_configured` instead of queueing a job that cannot run.

## What the adapter runs

`app/services/inference_service.py` runs the official CLI as an argument list (no shell):

```
<INSTANTMESH_PYTHON> run.py <config> <job>/reconstruction_input.png --output_path <job>/instantmesh \
    --diffusion_steps N --seed S [--no_rembg] [--export_texmap]
```

- **One process at a time.** One worker thread runs the jobs and a process lock guards the GPU, so only one copy of the models is ever loaded. Every job uses a fresh subprocess, which frees all VRAM afterwards. This matters on a 4 GB card, at the cost of reloading the models each run.
- **Progress.** stdout and stderr are streamed. The output lines `Loading…`, `Imagining…` and `Creating…` map to stages. Diffusion-step percentages come from InstantMesh's own tqdm bar. If upstream changes these messages, progress falls back to stage-only status; nothing is estimated.
- **Failures.** The log tail is sorted into categories: out of memory, no CUDA, missing weights, missing package, timeout, or no OBJ. Users get a short message; the full log is kept in `storage/jobs/<id>/inference.log`.
- **Cancel, timeout and shutdown.** The adapter kills only its own process group (`killpg` on Linux, `taskkill /T` on Windows). Jobs interrupted by a backend shutdown are marked `interrupted`. Queued jobs are re-queued on restart.
- **Measurements.** These are taken during the run: GPU memory used (whole GPU, via `nvidia-smi`, every 2 s) and the process's peak RSS (`/proc/<pid>/status` VmHWM, Linux only). Both are reported with the result.

## Image preparation

- **Drawings** (and uploads with "OpenCV cutout"): the background colour is sampled from the border and the foreground is everything not connected to it. The inside of closed shapes stays foreground. The result is cropped to the object, filled to 85% of a 640×640 transparent canvas, and passed with `--no_rembg`.
- **Photos** (default for uploads): the resized RGB image goes to InstantMesh's own rembg and foreground resizing.
- **Images with real transparency**: the alpha channel is used as the mask.

## Mesh post-processing

`app/services/mesh_service.py` does the following:
1. Loads the OBJ without vertex reordering, so vertex colours stay aligned.
2. Rejects empty geometry, non-finite coordinates and out-of-range indices.
3. Removes degenerate faces.
4. Rotates Z-up to Y-up, the same axis permutation the official Gradio app applies before writing its GLB. `MESH_CONVERT_Z_UP=false` turns this off.
5. Centres the model and scales its largest side to 1, then exports a GLB.
6. Reloads the GLB independently. The vertex and face counts, bounds, and colour or texture must match before the job is marked complete.

The original InstantMesh output is kept untouched under `storage/jobs/<id>/instantmesh/`.

## Prompt

The prompt is validated and stored with the job, and shown in the job panel and history. `run.py` has no text conditioning, so it does not affect the geometry. The UI says so.

## Remote GPU fallback

If the local GPU can't run inference reliably, run the **backend** on the GPU machine instead. This needs no code changes because the API is the same:

1. On the GPU host, configure `backend/.env` as above, add the frontend's origin to `ALLOWED_ORIGINS`, and start uvicorn with `--host 0.0.0.0` (or reach it over an SSH tunnel: `ssh -L 8000:127.0.0.1:8000 gpu-host`).
2. On the machine running the UI, start the frontend with `VITE_API_URL=http://<gpu-host>:8000/api/v1`.

## Verification status

The adapter, progress parsing, failure handling, cancellation, mesh processing and UI were tested end to end against `backend/tests/fixtures/fake_instantmesh/run.py`. That is a test double that follows the official CLI and output layout but writes a fixed box mesh. Real inference, real VRAM figures and the exact upstream log strings still need a run on the RTX 2050 machine. Submit one sketch and one photo there, then check the job's `inference.log`, timings and `gpu_memory_peak_mb`.
