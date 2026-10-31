# Troubleshooting

## Generate 3D is disabled

The reason appears under the button, and in `GET /api/v1/health` as `inference.reason`.

| Message | Fix |
|---|---|
| InstantMesh is not configured | Set `INSTANTMESH_REPO` and `INSTANTMESH_PYTHON` in `backend/.env`, then restart the backend |
| No CUDA-capable NVIDIA GPU is visible | Run the backend on a machine with an NVIDIA GPU. Check `nvidia-smi`, and that `INSTANTMESH_PYTHON -c "import torch; print(torch.cuda.is_available())"` prints `True` |
| … is not supported by PyTorch X in the InstantMesh environment | The GPU is newer than that PyTorch build (e.g. RTX 50-series with PyTorch 2.1). Install a PyTorch build that supports it (CUDA 12.8+ for RTX 50) in the InstantMesh environment |
| AMD (ROCm) / Apple GPU found | InstantMesh's renderer is CUDA-only. Run the backend on an NVIDIA machine and open it from this device |
| PyTorch could not be loaded | The InstantMesh environment is broken or incomplete. Reinstall it following the official README |
| Checking GPU… | The startup check is still running (it imports PyTorch). Wait a few seconds |

## Generation fails or is slow

- **GPU ran out of memory.** Close other GPU programs, choose a lower quality (fewer steps), or set `INSTANTMESH_CONFIG=configs/instant-mesh-base.yaml`. ControlNet uses CPU offload automatically below 8 GB. Force it with `CONTROLNET_MEMORY=offload`.
- **Model weights could not be loaded.** The first run needs internet access to download about 10 GB from Hugging Face. Check access to huggingface.co, or pre-download the weights into the HF cache.
- **AI refinement was skipped.** ControlNet failed, so the job continued with the plain sketch cutout. The reason is shown on the job, and the full log is in `storage/jobs/<id>/controlnet.log`. If `diffusers` or `accelerate` is missing, install them in the InstantMesh environment.
- **Other InstantMesh errors.** Read `storage/jobs/<id>/inference.log`.
- **Timeouts.** Raise `INFERENCE_TIMEOUT_SECONDS` / `CONTROLNET_TIMEOUT_SECONDS` for slow GPUs.

## Opening the app from another device

- **Different networks (judges, mobile data):** run `scripts/serve.sh --public` or `scripts\serve.cmd --public` and share the `https://….trycloudflare.com` link. If it says `cloudflared` is missing, install it as shown and open a new terminal. The link stops working when you close the windows, and a new link is made on each start.
- **Same network:** run `scripts/serve.sh` or `scripts\serve.cmd` and use the `http://<ip>:8000` address it prints. A `127.0.0.1` address only works on the computer itself. Guest Wi-Fi and campus networks often isolate devices from each other; use `--public` there.
- **Windows:** allow Python through Windows Defender Firewall for private networks. If the prompt was dismissed, allow `python.exe` in Firewall settings.
- **Blank page on port 8000:** build the UI (`cd frontend && npm run build`). `serve` does this for you.

## Setup and development

- **Excalidraw missing or canvas has no height:** install the frontend dependencies; `.excalidraw-host` has a fixed height.
- **Upload rejected:** use a PNG, JPEG or WEBP under 10 MB that is a real image of that type.
- **Backend offline in the dev UI (`run_all`):** the Vite dev server forwards `/api` to `127.0.0.1:8000`, so start the backend too. Set `BACKEND_URL` for Vite if the backend runs elsewhere.
- **OpenCV import failure:** use the pinned `opencv-python-headless` in `backend/.venv`.
- **Windows shells:** use the `.cmd` scripts; the `.sh` files need Bash. Activating the venv is optional (`. .\backend\.venv\Scripts\Activate.ps1`).
- **npm says `esbuild.exe` is an invalid application:** frontend setup failed at esbuild's native binary. Check that the Node and Windows architectures match and whether security software quarantined the file, then rerun `npm.cmd ci --cache .npm-cache --no-audit --no-fund` in `frontend`.
- **Port conflict:** set `SERVE_PORT` for `serve`, or `BACKEND_PORT` / `FRONTEND_PORT` for the dev scripts.
- **Missing storage:** it is created at startup under `STORAGE_ROOT`. Check that it is writable.
