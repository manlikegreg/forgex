export FORGEX_BACKEND_PORT=${FORGEX_BACKEND_PORT:-45555}
set -euo pipefail

# 1) Start backend
python -m uvicorn backend.main:app --host 127.0.0.1 --port $FORGEX_BACKEND_PORT &
BACK_PID=$!

echo "Backend PID: $BACK_PID"

# 2) Start frontend (Vite) and Electron in dev mode from frontend pkg
(cd frontend && npm install && npx concurrently -k "vite" "wait-on tcp:5173 && electron ../electron/main.js")

# Cleanup
kill $BACK_PID || true
