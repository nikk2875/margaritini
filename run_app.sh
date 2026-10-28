#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

for tool in uv npm; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Margaritini needs '$tool' on your PATH. Please install it and try again." >&2
    exit 1
  fi
done

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "Frontend packages are missing. Run 'npm install' in ./frontend first." >&2
  exit 1
fi

cleanup() {
  trap - EXIT INT TERM
  kill "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
  wait "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(
  cd "$BACKEND_DIR"
  uv run alembic upgrade head
  # Loopback only: the API has no authentication by default.
  uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

(
  cd "$FRONTEND_DIR"
  npm run dev -- --host 127.0.0.1 --strictPort
) &
FRONTEND_PID=$!

echo "Margaritini is starting:"
echo "  Frontend: http://localhost:6002"
echo "  API:      http://localhost:8000/api"
echo "Press Ctrl+C to stop both services."

wait "$BACKEND_PID" "$FRONTEND_PID"
