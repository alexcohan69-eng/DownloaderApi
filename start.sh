#!/usr/bin/env bash
# Entrypoint used by Render (and containers). Render injects $PORT;
# falls back to 8000 so the script also runs locally.
set -euo pipefail
cd "$(dirname "$0")"
exec python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --log-level "${YDL_LOG:-info}" \
  "$@"