# Backend guide

FastAPI initializes in `app/main.py`, adds local CORS and registers the versioned router. Pydantic contracts are in `schemas/models.py`. Routes handle HTTP and delegate input/storage/processing. `input_service` validates actual decoded content and stores safe UUID paths. `storage_service` owns directories and metadata JSON. `preprocessing_service` resolves the original internally and calls the reusable CV pipeline. Add a route in `api/routes.py`, define its response contract in schemas, and keep image/storage work in services. Settings come from environment or backend `.env`.

The reconstruction request is defined, but the route deliberately returns 501. Add implementation in a reconstruction service using a selected artifact resolver and a typed response; do not let the adapter depend on source mode.
