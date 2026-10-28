#!/usr/bin/env bash
set -euo pipefail

# Starts Margaritini with the repository's existing .venv, so `uv` does not
# need to be installed. For the uv-based variant see run_app.sh.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
PYTHON="$ROOT_DIR/.venv/bin/python"

# `python -m ...` is used instead of the .venv/bin scripts so the launcher
# works even when the venv was created under a different absolute path.
if [ ! -x "$PYTHON" ]; then
  echo "Margaritini needs a virtual environment at .venv." >&2
  echo "Create it with 'uv sync --all-groups', or without uv as described in the" >&2
  echo "'Without uv' section of README.md. An existing .venv can also be copied in." >&2
  exit 1
fi

if ! "$PYTHON" -c "import alembic, fastapi, uvicorn" >/dev/null 2>&1; then
  echo "The .venv is missing backend dependencies. Recreate it with" >&2
  echo "'uv sync --all-groups' on a machine with uv, then copy it here." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "Margaritini needs 'npm' on your PATH. Please install it and try again." >&2
  exit 1
fi

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
  "$PYTHON" -m alembic upgrade head
  # Loopback only: the API has no authentication by default.
  exec "$PYTHON" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

(
  cd "$FRONTEND_DIR"
  exec npm run dev -- --host 127.0.0.1 --strictPort
) &
FRONTEND_PID=$!

echo "Margaritini is starting:"
echo "  Frontend: http://localhost:6002"
echo "  API:      http://localhost:8000/api"
echo "Press Ctrl+C to stop both services."

wait "$BACKEND_PID" "$FRONTEND_PID"
