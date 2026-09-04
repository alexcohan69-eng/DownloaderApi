#!/usr/bin/env bash
# Start the Universal Media Downloader API.
# Uses the first python on PATH that has yt-dlp + fastapi installed.
set -euo pipefail

cd "$(dirname "$0")"

# Pick a python interpreter that has our deps (handles Termux where the
# default `python3` may be a system interpreter without yt-dlp).
for PY in "${PYTHON:-}" python python3; do
  if command -v "$PY" >/dev/null 2>&1 && \
     "$PY" -c 'import yt_dlp, fastapi, uvicorn' >/dev/null 2>&1; then
    break
  fi
  PY=""
done

if [ -z "${PY:-}" ]; then
  echo "ERROR: no python found with yt_dlp, fastapi and uvicorn." >&2
  echo "Install them with:  python -m pip install -r requirements.txt" >&2
  exit 1
fi

echo "Using: $PY"
exec "$PY" -m uvicorn app.main:app \
  --host "${YDL_HOST:-0.0.0.0}" \
  --port "${YDL_PORT:-8000}" \
  --log-level "${YDL_LOG:-info}" \
  "$@"