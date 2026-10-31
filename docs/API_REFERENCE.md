# API reference

Base URL `http://127.0.0.1:8000`; all routes are under `/api/v1`. Interactive docs: `/docs`.

Every error uses one envelope:

```json
{ "success": false, "error": { "code": "queue_full", "message": "The generation queue is full. Wait for a job to finish, then try again." } }
```

Validation errors use `code: "validation_error"` and add `fields: [{field, message}]`. Messages never contain stack traces or server paths; raw InstantMesh output stays in the job's `inference.log` on the server.

## Generation flow

| Method | Path | Purpose | Success | Errors |
|---|---|---|---|---|
| GET | `/health` | Backend, GPU, inference worker and storage status (no inference run; GPU info cached 30 s) | 200 | — |
| POST | `/generate` | Store input, create job, queue inference; returns immediately | 202 | 400, 404, 415, 422, 503 |
| GET | `/jobs?limit=20` | Recent jobs, newest first (history) | 200 | 422 |
| GET | `/jobs/{job_id}` | Status, stage, progress, timings, error | 200 | 404 |
| POST | `/jobs/{job_id}/cancel` | Cancel a queued or running job | 202 | 404, 409 |
| GET | `/jobs/{job_id}/result` | Model metadata and download URLs of a completed job | 200 | 404, 409 |
| GET | `/jobs/{job_id}/download/glb` | Processed GLB (`model/gltf-binary`, attachment) | 200 | 404, 409 |
| GET | `/jobs/{job_id}/download/obj` | Original InstantMesh OBJ (`model/obj`), or a `.zip` with `.mtl` and texture when a texture map was baked | 200 | 404, 409 |
| GET | `/jobs/{job_id}/files/{name}` | `input.png`, `reconstruction_input.png`, `multiview.png` previews | 200 | 404 |

### POST /generate

`multipart/form-data`. Send exactly one of `image` or `input_id`.

| Field | Default | Notes |
|---|---|---|
| `image` | — | PNG, JPEG or WEBP; ≤ 10 MB; content is decoded and verified, not just the extension |
| `input_id` | — | Reuse a stored input (used by "Try again") |
| `source` | `upload` | `drawing` or `upload` |
| `scene_json` | — | Excalidraw scene, stored alongside the input |
| `prompt` | — | ≤ 500 characters, whitespace/control characters normalised. **Stored only**; InstantMesh geometry is image-driven |
| `remove_background` | `true` for uploads, `false` for drawings | `true` → InstantMesh's rembg; `false` → OpenCV cutout and `--no_rembg` |
| `diffusion_steps` | 75 | 20–100, passed to `run.py --diffusion_steps` |
| `seed` | 42 | 0–2³¹−1, passed to `run.py --seed` |
| `export_texture` | `false` | `run.py --export_texmap` (texture map instead of vertex colours) |

```bash
curl -F image=@chair.jpg -F prompt="a wooden chair" http://127.0.0.1:8000/api/v1/generate
```

```json
{ "success": true, "job_id": "…", "status": "queued", "message": "Generation submitted successfully",
  "status_url": "/api/v1/jobs/…", "job": { "…": "same shape as GET /jobs/{id}" } }
```

503 codes: `inference_not_configured`, `queue_full`.

### Job status

`status`: `queued → preprocessing → generating → postprocessing → exporting → completed`, or `failed` / `cancelled`.

`stage` gives detail within a status, e.g. `image_preparation`, `loading_models`, `multiview_diffusion`, `mesh_reconstruction`, `mesh_validation`, `glb_export`.

`progress` is an integer only while InstantMesh reports diffusion steps (parsed from its own progress bar); otherwise `null`. No percentage is estimated.

Other fields: `message`, `prompt`, `options`, `queue_position` (queued only), `error {code, message}`, `timings` (seconds: `input_seconds`, `preprocessing_seconds`, `inference_seconds`, `postprocessing_seconds`, `export_seconds`, `total_seconds`), `created_at`, `started_at`, `completed_at`, `updated_at`, `input_url`, `preview_url`, `multiview_url`, `result_url`.

Failure codes: `invalid_input`, `inference_not_configured`, `gpu_out_of_memory`, `gpu_unavailable`, `model_weights_unavailable`, `inference_environment_error`, `inference_failed`, `inference_timeout`, `no_mesh_output`, `invalid_mesh`, `interrupted`, `internal_error`.

### Result

```json
{ "success": true, "job_id": "…", "status": "completed",
  "glb_url": "/api/v1/jobs/…/download/glb", "obj_url": "/api/v1/jobs/…/download/obj", "obj_format": "obj",
  "model": { "vertices": 31204, "faces": 62400, "dimensions": [0.61, 1.0, 0.58], "source_dimensions": [...],
             "has_vertex_colors": true, "has_texture": false, "watertight": false, "degenerate_faces_removed": 0,
             "glb_bytes": 1234567, "obj_bytes": 2345678, "gpu_memory_peak_mb": 3900, "process_memory_peak_mb": 5100, "…": "…" },
  "timings": { "…": "…" } }
```

409 codes for unfinished jobs: `result_not_ready`, `job_failed`, `job_cancelled`.

## Input and OpenCV analysis routes

| Method | Path | Purpose |
|---|---|---|
| POST | `/inputs/upload` | multipart `file`; store a raster input (201) |
| POST | `/inputs/drawing` | multipart `image`, optional `scene_json` (201) |
| GET | `/inputs/{input_id}` | Input metadata and analysis artifacts |
| POST | `/inputs/{input_id}/preprocess` | Optional JSON config; grayscale/CLAHE/edge/threshold analysis |
| GET | `/inputs/{input_id}/artifacts/original.png` | Stored original |
| GET | `/inputs/{input_id}/processing/{processing_id}/{artifact}` | Allow-listed analysis artifacts |

The `/reconstruction` alias and `/jobs/{id}/assets/*` routes were removed in 1.0.0; use `/generate` and `/jobs/{id}/download/{glb|obj}`.
