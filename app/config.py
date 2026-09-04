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

HOST = os.getenv("YDL_HOST", "0.0.0.0")
PORT = int(os.getenv("YDL_PORT", "8000"))

for _dir in (DOWNLOADS_DIR, COOKIES_DIR):
    _dir.mkdir(parents=True, exist_ok=True)