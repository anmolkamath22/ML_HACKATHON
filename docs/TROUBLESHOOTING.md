# Troubleshooting

- Excalidraw missing: install frontend dependencies; verify `@excalidraw/excalidraw` is present and its CSS import loads.
- Canvas has no height: `.excalidraw-host` has an explicit 450 px height; ensure the container is not hidden/collapsed.
- PNG export errors: draw at least one non-deleted element and retry; inspect browser console.
- Upload rejected: use PNG/JPEG/WEBP, valid decoded image bytes, under 10 MB and configured pixel/dimension limits.
- CORS/backend offline: start port 8000 and set `ALLOWED_ORIGINS` / `VITE_API_URL` for the frontend origin.
- OpenCV import failure: use the pinned `opencv-python-headless` package in the backend virtual environment.
- Windows PowerShell startup: use `scripts\setup_windows.cmd`, `scripts\run_backend.cmd`, and `scripts\run_frontend.cmd`; the `.sh` files require Bash.
- npm says `esbuild.exe` is an invalid application: Python may already be installed, but frontend setup failed at esbuild's native binary. Confirm Node and Windows architectures match, and check whether endpoint security quarantined the binary. The setup scripts use `npm ci` and the committed lockfile, which replaces stale partial dependencies. For a manual clean retry in PowerShell, run `Set-Location frontend; npm.cmd ci --cache .npm-cache --no-audit --no-fund` from the repository root. PowerShell activation syntax is `. .\backend\.venv\Scripts\Activate.ps1`; activation is optional with the provided launchers.
- Missing storage: it is created at startup under configured `STORAGE_ROOT`; check write access.
- Port conflict: set `BACKEND_PORT` / `FRONTEND_PORT` when running individual scripts; `run_all.sh` and `run_all.cmd` check configured ports.
- Preprocessing error: inspect backend logs; verify source input exists and selected config values are in schema limits.
