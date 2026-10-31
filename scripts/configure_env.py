"""Set KEY=VALUE entries in backend/.env, creating it from .env.example first if needed.

Usage: python scripts/configure_env.py INSTANTMESH_REPO=C:\\path INSTANTMESH_PYTHON=C:\\path\\python.exe
"""
import sys
from pathlib import Path

backend = Path(__file__).resolve().parents[1] / "backend"
env = backend / ".env"
if not env.exists():
    env.write_text((backend / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
updates = dict(argument.split("=", 1) for argument in sys.argv[1:])
lines, seen = [], set()
for line in env.read_text(encoding="utf-8").splitlines():
    key = line.split("=", 1)[0].strip()
    if key in updates and not line.lstrip().startswith("#"):
        lines.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        lines.append(line)
lines += [f"{key}={value}" for key, value in updates.items() if key not in seen]
env.write_text("\n".join(lines) + "\n", encoding="utf-8")
for key, value in updates.items():
    print(f"  {key}={value}")
