#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 -m venv "$ROOT/backend/.venv"
"$ROOT/backend/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/backend/.venv/bin/pip" install -r "$ROOT/backend/requirements.txt"
if [[ ! -f "$ROOT/backend/.env" ]]; then cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"; fi
(cd "$ROOT/frontend" && npm install)
echo "Setup complete. Run scripts/run_all.sh to start both servers."
