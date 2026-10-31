# Testing guide

## Backend

```bash
cd backend && .venv/bin/python -m pytest          # Windows: .venv\Scripts\python.exe -m pytest
```

Tests run against isolated temporary storage. Inference uses `tests/fixtures/fake_instantmesh/run.py`, a **test double** of InstantMesh's `run.py`. It accepts the same arguments, prints the same kinds of progress output and writes the same output layout, but always produces a fixed Z-up box with vertex colours. `FAKE_INSTANTMESH_MODE` selects a failure mode: `oom`, `crash`, `missing_weights`, `no_output`, `nan` or `hang`. `FAKE_INSTANTMESH_STEP_DELAY` slows the fake diffusion steps.

The tests cover:
- **Upload:** validation (type, content, size, filename), plus the error format and path traversal attempts.
- **Full pipeline:** sketch → OpenCV cutout → job → GLB/OBJ download, including the Y-up conversion and vertex colours.
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
