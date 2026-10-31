# Testing guide

Backend tests: `cd backend && .venv/bin/python -m pytest`. Coverage includes health, upload formats, validation, drawing, preprocessing/artifacts, missing input and the reconstruction placeholder. Frontend production type/build check: `cd frontend && npm run build`. Manual integration: upload a valid image or draw, submit, confirm input UUID, inspect all artifact previews and download original; compare its pixels/dimensions to the submitted sketch. Swagger at `/docs` is useful for multipart and configuration requests. Test corrupt files and unsupported suffixes for rejection. Add generated test images in temporary directories rather than committed storage.

Expected run output contains `original.png`, `normalized.png`, `grayscale.png`, `enhanced.png`, `edges.png`, `binary.png`, `preprocessed.png`, and `result.json`. If a stage fails, inspect backend logs and check the configured storage is writable.
