import os
import shutil
import sys
import tempfile
from pathlib import Path

# Configure before the app is imported: isolated storage and the InstantMesh test double.
_STORAGE = tempfile.mkdtemp(prefix="sketch2shape-tests-")
FAKE_INSTANTMESH = Path(__file__).parent / "fixtures" / "fake_instantmesh"
os.environ["STORAGE_ROOT"] = _STORAGE
os.environ["INSTANTMESH_REPO"] = str(FAKE_INSTANTMESH)
os.environ["INSTANTMESH_PYTHON"] = sys.executable
os.environ["GPU_SAMPLE_INTERVAL_SECONDS"] = "0.2"

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
    monkeypatch.delenv("FAKE_INSTANTMESH_MODE", raising=False)
    monkeypatch.delenv("FAKE_INSTANTMESH_STEP_DELAY", raising=False)
