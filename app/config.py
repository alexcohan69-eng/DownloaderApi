"""Configuration for the media downloader API.

Everything is overridable via environment variables so the same code
works in a container, on a VPS, or on Termux.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Where temporary download staging directories live.
DOWNLOADS_DIR = Path(os.getenv("YDL_DOWNLOADS_DIR", str(BASE_DIR / "downloads")))

# Where Netscape-format cookie files live (one per site).
COOKIES_DIR = Path(os.getenv("YDL_COOKIES_DIR", str(BASE_DIR / "cookies")))

# Overall wall-clock budget for a single download, in seconds.
DOWNLOAD_TIMEOUT = float(os.getenv("YDL_TIMEOUT", "600"))

# Max entries downloaded when a playlist URL is requested.
MAX_PLAYLIST_ITEMS = int(os.getenv("YDL_MAX_PLAYLIST_ITEMS", "20"))

# Temp dirs older than this (seconds) are purged on startup.
TEMP_LIFETIME = int(os.getenv("YDL_TEMP_LIFETIME", "3600"))

# Optional global proxy for yt-dlp (e.g. "socks5://127.0.0.1:1080").
PROXY = os.getenv("YDL_PROXY") or None

# Simple in-memory rate limit: max requests per IP per window.
RATE_LIMIT_MAX = int(os.getenv("YDL_RATE_LIMIT_MAX", "10"))
RATE_LIMIT_WINDOW = int(os.getenv("YDL_RATE_LIMIT_WINDOW", "60"))

# --------------------------------------------------------------------------
# Webhook / async job settings (the Cobalt-style push flow).
# --------------------------------------------------------------------------

# Telegram Bot API base URL. Override this to point at a self-hosted
# telegram-bot-api server (which lifts the upload limit to ~2 GB), e.g.
# "https://my-bot-api.example.com".
TELEGRAM_API_BASE = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")

# Max file size (MB) we will try to upload to Telegram. The public Bot API
# caps bot uploads at 50 MB; a self-hosted server allows ~2000 MB.
MAX_TELEGRAM_UPLOAD_MB = int(os.getenv("YDL_MAX_UPLOAD_MB", "50"))

# How many downloads may run at once. Keep small on free tiers (limited CPU
# and RAM); each job holds a worker thread for its whole download.
MAX_CONCURRENT_JOBS = int(os.getenv("YDL_MAX_CONCURRENT_JOBS", "2"))

# Optional shared secret. When set, every POST /jobs request must send the
# same value in the "X-Webhook-Secret" header (or a "secret" body field),
# so only your bot can trigger downloads on a public URL.
WEBHOOK_SECRET = os.getenv("YDL_WEBHOOK_SECRET") or None

# How long finished job records live in the in-memory status store (seconds).
JOB_RECORD_LIFETIME = int(os.getenv("YDL_JOB_RECORD_LIFETIME", "1800"))

# How many recent log lines the live log viewer (/logs) keeps in memory.
LOG_BUFFER_SIZE = int(os.getenv("YDL_LOG_BUFFER_SIZE", "500"))

# Optional shared secret protecting the /logs web viewer. When set, requests
# must include it as "?key=..." (query string) or an "X-Logs-Secret" header.
# Leave unset to leave the viewer open (fine for a private/unlisted URL).
LOGS_SECRET = os.getenv("YDL_LOGS_SECRET") or None

HOST = os.getenv("YDL_HOST", "0.0.0.0")
PORT = int(os.getenv("YDL_PORT", "8000"))

for _dir in (DOWNLOADS_DIR, COOKIES_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
