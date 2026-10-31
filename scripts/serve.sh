#!/usr/bin/env bash
# Build the UI and serve it together with the API on one port.
#   scripts/serve.sh            anyone on the same Wi-Fi/LAN can open it
#   scripts/serve.sh --public   also creates a public https link that works on any
#                               device and any network (Cloudflare quick tunnel)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${SERVE_PORT:-8000}"
HOST="${SERVE_HOST:-0.0.0.0}"
PUBLIC=0
[[ "${1:-}" == "--public" ]] && PUBLIC=1
PYTHON="$ROOT/backend/.venv/bin/python"
[[ -x "$PYTHON" ]] || { echo "Backend environment missing; run scripts/setup_linux.sh first." >&2; exit 1; }
[[ -d "$ROOT/frontend/node_modules" ]] || { echo "Frontend dependencies missing; run scripts/setup_linux.sh first." >&2; exit 1; }
if (( PUBLIC )) && ! command -v cloudflared >/dev/null; then
  cat >&2 <<'EOF'
A public link needs the free cloudflared tool. Install it once, then rerun:
  Ubuntu/Debian: download the .deb from https://github.com/cloudflare/cloudflared/releases
                 (cloudflared-linux-amd64.deb) and run: sudo dpkg -i cloudflared-linux-amd64.deb
  macOS:         brew install cloudflared
EOF
  exit 1
fi
(cd "$ROOT/frontend" && npm run build)
echo
echo "Sketch2Shape is starting."
echo "  On this computer:   http://127.0.0.1:$PORT"
addresses="$(hostname -I 2>/dev/null || ipconfig getifaddr en0 2>/dev/null || true)"
for ip in $addresses; do
  [[ "$ip" == *:* ]] || echo "  Same Wi-Fi/LAN:     http://$ip:$PORT"
done
cd "$ROOT/backend"
if (( PUBLIC )); then
  "$PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT" &
  SERVER=$!
  trap 'kill "$SERVER" 2>/dev/null || true' EXIT INT TERM
  echo
  echo "  Public link:        wait for the https://....trycloudflare.com address below and share it."
  echo "                      It works from any device on any Wi-Fi or mobile data while this keeps running."
  echo "                      Press Ctrl+C to stop sharing."
  echo
  cloudflared tunnel --url "http://127.0.0.1:$PORT"
else
  echo "For a link that works on any network, run: scripts/serve.sh --public"
  echo
  exec "$PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
fi
