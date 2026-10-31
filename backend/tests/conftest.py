import os
import shutil
import sys
import tempfile
from pathlib import Path

# Configure before the app is imported: isolated storage and test doubles for every GPU stage.
_STORAGE = tempfile.mkdtemp(prefix="sketch2shape-tests-")
FIXTURES = Path(__file__).parent / "fixtures"
os.environ["STORAGE_ROOT"] = _STORAGE
os.environ["INSTANTMESH_REPO"] = str(FIXTURES / "fake_instantmesh")
os.environ["INSTANTMESH_PYTHON"] = sys.executable
os.environ["CONTROLNET_SCRIPT"] = str(FIXTURES / "fake_controlnet.py")
os.environ["CONTROLNET_STEPS"] = "5"
os.environ["GPU_PROBE_SCRIPT"] = str(FIXTURES / "fake_gpu_probe.py")
os.environ["GPU_SAMPLE_INTERVAL_SECONDS"] = "0.2"
os.environ["FRONTEND_DIST"] = str(Path(_STORAGE) / "no-frontend")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client
    shutil.rmtree(_STORAGE, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_fake(monkeypatch):
    for name in ("FAKE_INSTANTMESH_MODE", "FAKE_INSTANTMESH_STEP_DELAY", "FAKE_CONTROLNET_MODE", "FAKE_GPU"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fake_gpu(monkeypatch):
    """Switch the reported GPU for one test; the cached probe result is reset before and after."""
    from app.services.inference_service import reset_gpu_status

    def use(profile: str) -> None:
        monkeypatch.setenv("FAKE_GPU", profile)
        reset_gpu_status()
    yield use
    reset_gpu_status()
