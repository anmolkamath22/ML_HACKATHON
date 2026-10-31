import importlib.util
import shutil
import sys

checks = {"python>=3.10": sys.version_info >= (3, 10), "node": shutil.which("node") is not None, "npm": shutil.which("npm") is not None, "fastapi": importlib.util.find_spec("fastapi") is not None, "cv2": importlib.util.find_spec("cv2") is not None}
for name, present in checks.items():
    print(f"{'PASS' if present else 'MISSING'} {name}")
sys.exit(0 if all(checks.values()) else 1)
