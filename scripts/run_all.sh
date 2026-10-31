#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for pair in "8000:Backend" "5173:Frontend"; do
  port="${pair%%:*}"; label="${pair#*:}"
  if command -v lsof >/dev/null && lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then echo "$label port $port is already in use." >&2; exit 1; fi
done
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
command -v npm >/dev/null || { echo "npm is required" >&2; exit 1; }
[[ -d "$ROOT/frontend/node_modules" ]] || { echo "Frontend dependencies missing; run scripts/setup_linux.sh" >&2; exit 1; }
BACKEND_PYTHON="$ROOT/backend/.venv/bin/python"; [[ -x "$BACKEND_PYTHON" ]] || BACKEND_PYTHON=python3
"$BACKEND_PYTHON" -c 'import fastapi, cv2, PIL' || { echo "Backend dependencies missing; run scripts/setup_linux.sh" >&2; exit 1; }
"$ROOT/scripts/run_backend.sh" & BACK_PID=$!
"$ROOT/scripts/run_frontend.sh" & FRONT_PID=$!
cleanup(){ kill "$BACK_PID" "$FRONT_PID" 2>/dev/null || true; wait "$BACK_PID" "$FRONT_PID" 2>/dev/null || true; }
trap cleanup INT TERM EXIT
echo "Frontend: http://127.0.0.1:${FRONTEND_PORT:-5173}"
echo "Backend:  http://127.0.0.1:${BACKEND_PORT:-8000}/docs"
wait -n "$BACK_PID" "$FRONT_PID"
