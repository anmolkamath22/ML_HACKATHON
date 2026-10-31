# Testing guide

## Backend

```bash
cd backend && .venv/bin/python -m pytest          # Windows: .venv\Scripts\python.exe -m pytest
```

Tests run against isolated temporary storage, with every GPU stage replaced by a **test double** in `tests/fixtures/`. They need no GPU and never claim model quality.

| Test double | Stands in for | Behaviour | Failure switch |
|---|---|---|---|
| `fake_instantmesh/run.py` | InstantMesh `run.py` | Same arguments, progress output and output layout; always writes a fixed Z-up box with vertex colours | `FAKE_INSTANTMESH_MODE`: `oom`, `crash`, `missing_weights`, `no_output`, `nan`, `hang`. `FAKE_INSTANTMESH_STEP_DELAY` slows its steps |
| `fake_controlnet.py` | `inference_scripts/controlnet_refine.py` | Same arguments and step lines; writes a tinted copy of the line map | `FAKE_CONTROLNET_MODE`: `oom`, `missing_weights`, `no_output`, `hang` |
| `fake_gpu_probe.py` | `inference_scripts/gpu_probe.py` | Reports a chosen GPU | `FAKE_GPU`: `cuda` (RTX 4050), `none`, `rocm`, `mps`, `old_torch` (RTX 5050 on PyTorch 2.1), `broken` |

The tests cover:
- **Upload:** validation (type, content, size, filename), plus the error format and path traversal attempts.
- **Full pipeline:** sketch → OpenCV cutout → ControlNet line map and prompt → InstantMesh with rembg → GLB/OBJ download, including the Y-up conversion and vertex colours.
- **ControlNet:** auto-on for drawings and uploaded sketches, off for photos; falls back to the cutout when ControlNet fails; can be cancelled mid-run.
- **GPU gating:** NVIDIA allowed; AMD, Apple, too-new and missing GPUs rejected with a reason.
- **CV helpers:** sketch detection and a clean line map from a faint, noisy scan.
- **Photo uploads:** these use rembg, and the steps and seed options are passed through.
- **Progress:** real diffusion-step progress reported by the job.
- **Retry:** retry from a stored input.
- **Failures:** each failure category, cancelling queued and running jobs, timeouts, the queue limit, the "not configured" rejection, job history and restart recovery.
- **Mesh:** textures preserved, degenerate faces removed, invalid meshes rejected, the face limit.
- **CV modes and the SQLite job store.**

## Frontend

```bash
cd frontend && npm test && npm run build
```

Vitest and Testing Library cover the following:
- The API client: form contents, error envelope, URLs.
- Polling: stops when the job finishes, cleans up on unmount, backs off after errors.
- The upload checks and preview URL clean-up.
- Canvas export: a white background and visible elements only.
- Viewer setup, display modes and the fullscreen fallback.
- The Workspace flow: sketch → progress → viewer → downloads → generate another, plus upload, errors, failure with retry, cancel, the "not configured" state and history.

## Browser end-to-end

Steps:
1. Start the backend with `INSTANTMESH_REPO=backend/tests/fixtures/fake_instantmesh`, `INSTANTMESH_PYTHON=<backend venv python>` and a scratch `STORAGE_ROOT`.
2. Start the frontend.
3. Drive the browser with Playwright through these steps:
   - Draw a cube with the Excalidraw tools.
   - Generate it and watch the progress.
   - Inspect the GLB in material, clay and wireframe modes, orbit, zoom and reset.
   - Download the GLB and OBJ.
   - Choose Generate another, upload a bottle photo and generate again.
   - Open the history, switch to dark mode and check the layout at 390 px.

Check for console errors as you go. The stand-in produces the same box for every input, so this tests the plumbing, not reconstruction quality.

## On the GPU machine (real InstantMesh)

Not runnable in CI. With `.env` pointing at the real installation, generate:
- a drawn cube
- a bottle photo
- a chair photo
- a run with no prompt
- a run with a texture map

Afterwards, check each job's `inference.log`, the `timings` and the `gpu_memory_peak_mb` value in `/jobs/{id}/result`. Then try cancelling during diffusion and confirm that `nvidia-smi` shows no leftover process.
