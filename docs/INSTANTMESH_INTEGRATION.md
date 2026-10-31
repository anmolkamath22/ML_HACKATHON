# InstantMesh and ControlNet integration

## Setting up the inference environment

Both GPU stages run in **one** dedicated Python environment: InstantMesh's own environment, not the backend's.

1. Install the official [TencentARC/InstantMesh](https://github.com/TencentARC/InstantMesh) checkout and its Python 3.10 environment as its README describes (CUDA PyTorch, `requirements.txt`). Run its sample once (`python run.py configs/instant-mesh-large.yaml examples/hatsune_miku.png --save_video`) to confirm it works and to download its weights.
2. Make sure that environment can also run ControlNet: `pip install "diffusers>=0.20" accelerate`. diffusers is already an InstantMesh dependency; `accelerate` enables CPU offload on small GPUs.
3. In `backend/.env` set:
   - `INSTANTMESH_REPO`: the checkout.
   - `INSTANTMESH_PYTHON`: that environment's `python`. Venv symlinks are deliberately not resolved, so a venv's packages stay visible.
   - Optionally `INSTANTMESH_CONFIG` (e.g. `configs/instant-mesh-base.yaml` on 4 GB cards) and the `CONTROLNET_*` settings in `.env.example`.
4. Start the backend and open `GET /api/v1/health`. `gpu.status` should be `ready` and `inference.ready` should be `true`. The first ControlNet job downloads Stable Diffusion 1.5 and the scribble ControlNet (about 3–4 GB) into the Hugging Face cache.

## GPU detection

At startup the backend runs `inference_scripts/gpu_probe.py` with `INSTANTMESH_PYTHON` in the background. The script asks that environment's own PyTorch which GPU it can use:

| Result | `gpu.status` | Generate 3D |
|---|---|---|
| CUDA GPU whose architecture this PyTorch build supports (any NVIDIA RTX/GTX/data-centre card) | `ready` | Enabled |
| CUDA GPU newer than the PyTorch build (e.g. RTX 50-series with PyTorch 2.1) | `unsupported` | Disabled. Install a PyTorch build for that GPU |
| AMD (ROCm) or Apple (MPS) | `unsupported` | Disabled. InstantMesh's renderer is CUDA-only |
| No GPU, broken PyTorch, or InstantMesh not configured | `unavailable` / `not_configured` | Disabled, with the reason |

`POST /generate` re-checks readiness and returns 503 `gpu_unavailable`, `gpu_unsupported` or `inference_not_configured` with the same message. Successful checks are cached until restart; failed ones are retried after 60 s.

## Pipeline stages

1. **Image preparation (OpenCV, backend).**
   - Drawings and uploaded sketches: the background colour is sampled from the border and the foreground is everything not connected to it, so the inside of closed shapes stays foreground. The object is cropped and filled to 85% of a 640×640 transparent canvas.
   - Images with real transparency use their alpha channel.
   - Photos are passed on resized for rembg.
   - For ControlNet, the cutout is denoised (non-local means), contrast-enhanced (CLAHE) and thresholded (Otsu) into a 512×512 **white-on-black line map**. Filled silhouettes are reduced to their outline.
2. **AI refinement (`inference_scripts/controlnet_refine.py`).**
   - Stable Diffusion 1.5 with `lllyasviel/control_v11p_sd15_scribble` and a UniPC scheduler, 20 steps by default, in fp16.
   - The prompt is the user's description (or "an object") plus a style suffix for Zero123++: a single centred object, plain white background, studio lighting. A fixed negative prompt discourages clutter, text and line-drawing output.
   - With 8 GB VRAM or more the whole pipeline sits on the GPU; below that it uses `enable_model_cpu_offload()`.
   - Progress comes from the pipeline's step callback (`ControlNet step i/N`).
   - On any ControlNet failure the job continues with the sketch cutout and records `refinement.status = "skipped"` with the reason.
3. **InstantMesh (`run.py`).**
   - Runs `run.py <config> <image> --output_path <job>/instantmesh --diffusion_steps N --seed S [--no_rembg] [--export_texmap]`.
   - `--no_rembg` is passed only for the OpenCV cutout. The ControlNet image and photos go through InstantMesh's rembg and foreground resizing.
   - Progress comes from its log lines (`Loading…`, `Imagining…`, `Creating…`) and its tqdm diffusion bar.
4. **Mesh post-processing (`mesh_service.py`).**
   - Rejects empty or non-finite meshes and out-of-range indices, and removes degenerate faces.
   - Rotates Z-up to Y-up, the same axis permutation as the official app, then centres and scales the model to unit size.
   - Exports a GLB, reloads it independently and checks the counts, bounds and colour or texture.
   - The original OBJ stays under `storage/jobs/<id>/instantmesh/`.

## Process handling

- **One GPU process at a time.** Each GPU stage is a fresh subprocess under one lock, so only one model set is in VRAM and memory is fully released between stages and jobs.
- **Commands.** Arguments are passed as a list, never through a shell. The full output goes to `controlnet.log` / `inference.log` in the job folder. Users see only short categorised messages: out of memory, unsupported GPU, no CUDA, missing weights, missing package, timeout.
- **Cancel, timeout and shutdown** kill only the job's own process group. Queued jobs are re-queued after a restart; jobs that were running are marked `interrupted`.
- **Measurements** taken during each stage:
  - GPU memory, via `nvidia-smi` every 2 s (whole GPU).
  - Process peak RSS (Linux).
  - Per-stage durations.

## Remote GPU

If the computer showing the UI has no suitable GPU, run the backend (`scripts/serve.sh`) on the GPU machine and open its address from the other device. To keep a local development UI instead, start it with `VITE_API_URL=http://<gpu-host>:8000/api/v1` and add its origin to `ALLOWED_ORIGINS` on the GPU host.

## Verification status

Everything except the models' actual output was exercised end to end without a GPU, using the test doubles in `backend/tests/fixtures/`:
- the probe logic for every GPU type
- stage ordering, progress parsing and the ControlNet fallback
- cancel and timeouts
- mesh processing and the UI

Still to check on a real GPU:
- the real ControlNet and InstantMesh output quality
- VRAM use and timings
- the exact upstream log strings

Run one drawing and one photo there, then check each job's logs, `timings` and `gpu_memory_peak_mb`.
