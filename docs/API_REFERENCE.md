# API reference

Base URL `http://127.0.0.1:8000`; all routes are under `/api/v1`. Swagger is `/docs`. Errors use FastAPI `{ "detail": "..." }`.

## Health
`GET /api/v1/health` → 200 `{status, version, opencv_available, storage_available}`.

## Create upload
`POST /api/v1/inputs/upload`, multipart field `file`. PNG/JPEG/WEBP; 10 MB default. Returns 201 with `input_id`, `source`, `filename`, dimensions, format, timestamp, and `original_url`. Errors: 400 invalid/corrupt content; 413 framework body limit may apply; 415 extension unsupported.

```bash
curl -F "file=@samples/sketches/example.png" http://127.0.0.1:8000/api/v1/inputs/upload
```

## Create drawing
`POST /api/v1/inputs/drawing`, multipart `image` (PNG), optional text `scene_json`, `source`. Returns the same input schema with `source=drawing`.

```bash
curl -F "image=@sketch.png" -F 'scene_json={}' -F 'source=drawing' http://127.0.0.1:8000/api/v1/inputs/drawing
```

## Retrieve input
`GET /api/v1/inputs/{input_id}` returns input metadata plus `artifacts`. 404 for unknown ID.

## Preprocess
`POST /api/v1/inputs/{input_id}/preprocess`; optional JSON `max_dimension` (64–4096), `denoise`, `denoise_strength`, `enhance_contrast`, `detect_edges`, `canny_low`, `canny_high`, `threshold_method` (`adaptive`/`otsu`), `background`, `recommendation` (`enhanced`/`normalized`/`edges`/`binary`). Returns processing ID, dimensions, elapsed time, config, recommendation and artifact names/URLs.

```bash
curl -X POST -H 'Content-Type: application/json' -d '{"max_dimension":1536,"recommendation":"enhanced"}' http://127.0.0.1:8000/api/v1/inputs/INPUT_ID/preprocess
```

## Retrieve artifact
`GET /api/v1/inputs/{input_id}/artifacts/original.png` or `GET /api/v1/inputs/{input_id}/processing/{processing_id}/{artifact_name}`. Allowlisted names: `original.png`, `normalized.png`, `grayscale.png`, `enhanced.png`, `edges.png`, `binary.png`, `preprocessed.png`. 404 if missing.

## Reconstruction placeholder
`POST /api/v1/reconstruction` JSON `{input_id, processing_id?, selected_artifact, settings?, prompt?}`. Always returns 501 in this phase; no model is generated.
