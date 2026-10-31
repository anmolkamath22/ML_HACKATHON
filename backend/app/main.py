import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.core.config import get_settings
from app.services import generation_service
from app.services.inference_service import gpu_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    generation_service.recover()
    gpu_status()  # start the GPU check in the background so the first request does not wait
    yield
    generation_service.shutdown()


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan,
              description="Sketch or image to 3D mesh: input validation, OpenCV preparation, InstantMesh jobs and GLB export.")
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False,
                   allow_methods=["GET", "POST"], allow_headers=["*"])
app.include_router(router)
if (settings.frontend_dist / "index.html").is_file():
    # One origin for the UI and the API: any device on the network can open http://<host>:8000.
    app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")


def _error(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"success": False, "error": {"code": code, "message": message, **extra}})


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        return _error(exc.status_code, exc.detail["code"], exc.detail["message"])
    code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
    return _error(exc.status_code, code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [{"field": ".".join(str(part) for part in error["loc"][1:]), "message": error["msg"]} for error in exc.errors()]
    summary = "; ".join(f"{item['field']}: {item['message']}" for item in fields) or "The request is invalid."
    return _error(422, "validation_error", summary, fields=fields)


@app.exception_handler(Exception)
async def unhandled_error(_: Request, exc: Exception) -> JSONResponse:
    logging.getLogger("sketch2shape").error("Unhandled request error: %s", exc, exc_info=(type(exc), exc, exc.__traceback__))
    return _error(500, "internal_error", "An internal server error occurred.")
