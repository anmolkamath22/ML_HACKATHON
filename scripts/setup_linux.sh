#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || { echo "Python 3.10 or newer is required." >&2; exit 1; }
node -e 'const v=process.versions.node.split(".").map(Number); process.exit(v[0]>=20?0:1)' || { echo "Node.js 20 or newer is required." >&2; exit 1; }
command -v npm >/dev/null || { echo "npm is required." >&2; exit 1; }
python3 -m venv "$ROOT/backend/.venv"
"$ROOT/backend/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/backend/.venv/bin/pip" install -r "$ROOT/backend/requirements.txt"
if [[ ! -f "$ROOT/backend/.env" ]]; then cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"; fi
(cd "$ROOT/frontend" && npm ci --no-audit --no-fund)
echo "Setup complete. Run scripts/run_all.sh to start both servers."
