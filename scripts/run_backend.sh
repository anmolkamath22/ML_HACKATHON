#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/backend/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python3
cd "$ROOT/backend"
exec "$PYTHON" -m uvicorn app.main:app --reload --host "${BACKEND_HOST:-127.0.0.1}" --port "${BACKEND_PORT:-8000}"
