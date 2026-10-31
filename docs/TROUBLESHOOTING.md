# Troubleshooting

- Excalidraw missing: install frontend dependencies; verify `@excalidraw/excalidraw` is present and its CSS import loads.
- Canvas has no height: `.excalidraw-host` has an explicit 450 px height; ensure the container is not hidden/collapsed.
- PNG export errors: draw at least one non-deleted element and retry; inspect browser console.
- Upload rejected: use PNG/JPEG/WEBP, valid decoded image bytes, under 10 MB and configured pixel/dimension limits.
- CORS/backend offline: start port 8000 and set `ALLOWED_ORIGINS` / `VITE_API_URL` for the frontend origin.
- OpenCV import failure: use the pinned `opencv-python-headless` package in the backend virtual environment.
- Missing storage: it is created at startup under configured `STORAGE_ROOT`; check write access.
- Port conflict: set `BACKEND_PORT` / `FRONTEND_PORT` when running individual scripts; `run_all.sh` checks default ports.
- Preprocessing error: inspect backend logs; verify source input exists and selected config values are in schema limits.
