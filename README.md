# Universal Media Downloader

A **universal media downloader that runs as an HTTP API**, built on
[yt-dlp](https://github.com/yt-dlp/yt-dlp) + FastAPI.

Give it any media URL (YouTube, TikTok, Instagram, Twitter/X, Reddit, Vimeo,
Twitch, SoundCloud, Pinterest, …) and it downloads the media and **returns the
raw file bytes** to you. It was designed for a **Telegram bot**: the bot sends
the URL → the API downloads the media → the bot forwards the file to the user.

```
Telegram bot ──URL──▶ Downloader API ──yt-dlp──▶ media file
        ▲                                        │
        └────────────── raw bytes ◀──────────────┘
```

---

## Table of contents

1. [Features](#features)
2. [Requirements](#requirements)
3. [Installation & running](#installation--running)
4. [Quick test](#quick-test)
5. [API reference](#api-reference)
6. [Calling from your own project](#calling-from-your-own-project)
7. [Telegram bot integration](#telegram-bot-integration)
8. [Cookies](#cookies)
9. [Configuration](#configuration)
10. [Project layout](#project-layout)
11. [Notes & limits](#notes--limits)

---

## Features

- **Download from almost any site** — everything yt-dlp supports
- **Video downloads** merged into a single MP4, preferring **H.264 + AAC** (the
  codec pair every Telegram client plays)
- **Audio downloads** converted to **MP3** (choose bitrate)
- **Playlist support** — bundle all entries into a ZIP
- **Cookies** — pass a Netscape cookie file name for sites that need login
- **Info endpoint** — get title/duration/thumbnail/formats without downloading
- **Safe by design** — media type and quality go through strict allowlists, so
  callers can *never* inject yt-dlp flags or read arbitrary files
- **Self-cleaning** — temp files removed after every response
- **Plug-and-play for bots** — raw bytes out, no auth keys to manage

---

## Requirements

- Python 3.9+
- `ffmpeg` in PATH (needed for merging video+audio and for audio→MP3)
- `yt-dlp`, `fastapi`, `uvicorn`, `pydantic`, `python-multipart`

Install ffmpeg if you don't have it:

```bash
# Debian / Ubuntu / PRoot
apt install ffmpeg

# Termux
pkg install ffmpeg
```

---

## Installation & running

```bash
git clone <your-repo-url> && cd downloader   # or just cd into the project dir

python -m pip install -r requirements.txt    # use your project venv if you have one
chmod +x run.sh
./run.sh                                     # → http://0.0.0.0:8000
```

You should see:

```
INFO:     Started server process [28488]
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

Run it in the background if you prefer:

```bash
nohup ./run.sh > /tmp/dl_api.log 2>&1 &
```

> **Note on `requirements.txt`:** it is pinned to versions that build cleanly
> on machines without a Rust toolchain (pydantic v1, pure-Python uvicorn).
> On a normal machine you can safely use the latest versions instead.

---

## Quick test

```bash
# 1. Is it alive?
curl "http://127.0.0.1:8000/"

# 2. Preview metadata (no download)
curl "http://127.0.0.1:8000/info?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# 3. Download best video → file bytes
curl -L -o out.mp4 "http://127.0.0.1:8000/download?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# 4. Audio as MP3 at 128 kbps
curl -L -o out.mp3 "http://127.0.0.1:8000/download?url=https://youtu.be/dQw4w9WgXcQ&media_type=audio&quality=128"

# 5. Video capped at 720p
curl -L -o out.mp4 "http://127.0.0.1:8000/download?url=https://youtu.be/dQw4w9WgXcQ&quality=720p"
```

> Remember: query values must be URL-encoded. The `-L` follows redirects
> (helpers that return 307, e.g. `youtu.be`).

---

## API reference

### `GET | POST /download` — download media, return the file

Query params (GET) / JSON body (POST):

| Parameter   | Values                                                               | Default  |
|-------------|----------------------------------------------------------------------|----------|
| `url`       | any http(s) URL yt-dlp supports                                      | —        |
| `media_type`| `video` \| `audio`                                                   | `video`  |
| `quality`   | video: `best` `worst` `4320p`–`360p`<br>audio: `best` `320` `256` `192` `128` `96` `64` (kbps) | `best` |
| `cookies`   | file name of a cookie file inside `./cookies/` (optional)            | none     |
| `playlist`  | `true` → download all entries (capped at 20) and return a `.zip`     | `false`  |

**Success** → HTTP 200, body is the media file.

Useful response headers:

| Header          | Meaning                                          |
|-----------------|--------------------------------------------------|
| `Content-Type`  | `video/mp4`, `audio/mpeg`, `application/zip`, …  |
| `X-File-Name`   | safe filename to save / upload as                 |
| `X-Media-Type`  | `video` or `audio`                                |
| `X-Title`       | media title (for captions)                        |
| `X-Duration`    | duration in seconds                               |
| `X-Thumbnail`   | thumbnail URL                                     |
| `X-File-Count`  | number of files (only for playlist ZIPs)          |

**Errors** → JSON: `{"ok": false, "error": "<message>"}` with HTTP 400/422/429.

### `GET | POST /info` — metadata only, no download

Returns:

```json
{
  "ok": true,
  "is_playlist": false,
  "title": "Rick Astley - Never Gonna Give You Up (Official Video)",
  "duration": 213,
  "thumbnail": "https://i.ytimg.com/vi/.../hqdefault.jpg",
  "uploader": "Rick Astley",
  "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "formats": [ { "format_id": "137", "ext": "mp4", "resolution": "1920x1080", ... } ]
}
```

---

## Calling from your own project

The API returns raw bytes — whatever language your project is in, you HTTP-GET
the URL (URL-encoded! set a long timeout!) and save/forward the bytes. The same
pattern applies to your Telegram bot.

### Python (requests)

```python
import requests

API = "http://127.0.0.1:8000"
url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Optional: preview metadata
info = requests.get(f"{API}/info", params={"url": url}, timeout=60).json()

# Download the actual file
resp = requests.get(f"{API}/download",
                    params={"url": url, "media_type": "video", "quality": "720p",
                            "cookies": "site.txt"},
                    timeout=1800)          # large files take a while
if resp.status_code != 200:
    raise RuntimeError(resp.json().get("error"))

filename = resp.headers.get("X-File-Name", "media.mp4")
open(filename, "wb").write(resp.content)
```

### Node.js

```js
const url = "https://youtu.be/dQw4w9WgXcQ";
const params = new URLSearchParams({ url, media_type: "video", quality: "720p" });
const resp = await fetch(`${API}/download?${params}`);
const buffer = Buffer.from(await resp.arrayBuffer());    // ← upload this to Telegram
const filename = resp.headers.get("x-file-name") || "media.mp4";
```

### PHP

```php
$u = 'https://youtu.be/dQw4w9WgXcQ';
$resp = file_get_contents("http://127.0.0.1:8000/download?url=" . urlencode($u)
        . "&media_type=video&quality=720p", false, stream_context_create([
    'http' => ['method' => 'GET', 'timeout' => 1800],
]));
file_put_contents('out.mp4', $resp);
```

### curl

```bash
curl -L -o out.mp4 "http://127.0.0.1:8000/download?url=https%3A%2F%2Fyoutu.be%2FdQw4w9WgXcQ&quality=720p"
```

---

## Telegram bot integration

The intended flow:

1. User sends a URL to the bot
2. Bot calls `/info` → shows a preview caption
3. Bot calls `/download` → gets raw bytes
4. Bot uploads the bytes straight to Telegram

Minimal bot handler (Python `python-telegram-bot` + `requests`):

```python
resp = requests.get("http://127.0.0.1:8000/download",
                    params={"url": user_url, "media_type": "video", "quality": "best"})
if resp.status_code == 200:
    await update.message.reply_video(video=resp.content)   # raw bytes → Telegram
    # or: reply_audio(resp.content)                        # for media_type=audio
    # or: reply_document(resp.content)                     # for playlist ZIPs
else:
    await update.message.reply_text(resp.json().get("error", "Download failed"))
```

> If your bot runs on a **different machine** than the API, put the API's
> reachable IP/hostname in place of `127.0.0.1` and open port 8000 in the
> firewall/security group.

A complete, runnable reference bot (with preview captions, audio / quality
commands) is at **`examples/telegram_bot.py`**:

```bash
pip install python-telegram-bot requests
export BOT_TOKEN="123456:ABC..."
export DOWNLOADER_API="http://127.0.0.1:8000"
python examples/telegram_bot.py
```

---

## Cookies

Some sites (Instagram, private Twitter/X, age-restricted content, Vimeo, …)
require your login cookies. Export them as a **Netscape-format** `.txt` file
(`cookies.txt`), drop it into `./cookies/`, and pass its filename:

```bash
# Export with a browser extension like "Get cookies.txt LOCALLY"
mv ~/Downloads/youtube.com_cookies.txt ./cookies/youtube.txt

curl -L -o out.mp4 \
  "http://127.0.0.1:8000/download?url=<private-or-restricted-url>&cookies=youtube.txt"
```

Safety: only a **plain filename** inside `./cookies/` is accepted — path
traversal and arbitrary file reads are rejected. One cookie file may hold
cookies for many domains.

---

## Configuration

Everything is configurable via environment variables:

| Variable                     | Default            | Meaning                                  |
|------------------------------|--------------------|------------------------------------------|
| `YDL_HOST` / `YDL_PORT`      | `0.0.0.0` / `8000` | Bind address / port                      |
| `YDL_COOKIES_DIR`            | `./cookies`        | Cookie file directory                    |
| `YDL_DOWNLOADS_DIR`          | `./downloads`      | Temp download staging                    |
| `YDL_TIMEOUT`                | `600`              | Max seconds for one download             |
| `YDL_MAX_PLAYLIST_ITEMS`     | `20`               | Cap for `playlist=true`                  |
| `YDL_TEMP_LIFETIME`          | `3600`             | Stale temp-dir purge age at startup (s)  |
| `YDL_PROXY`                  | —                  | Proxy for yt-dlp (e.g. `socks5://…`)     |
| `YDL_RATE_LIMIT_MAX` / `YDL_RATE_LIMIT_WINDOW` | `10` / `60` | Per-IP rate limit (set max to `0` to disable) |

Example:

```bash
YDL_PORT=9000 YDL_PROXY="socks5://127.0.0.1:1080" ./run.sh
```

---

## Project layout

```
downloader/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI routes, validation, cleanup
│   ├── downloader.py    # yt-dlp wrapper + format allowlists
│   └── config.py        # settings
├── cookies/             # drop Netscape cookie files here
├── downloads/           # temp staging (auto-purged)
├── examples/
│   └── telegram_bot.py  # reference Telegram bot
├── run.sh               # start script
├── requirements.txt
└── README.md
```

---

## Notes & limits

- **No arbitrary yt-dlp options pass through** — media type and quality are
  mapped through allowlists, so callers can't inject flags.
- Downloads **stream** (no full buffering in RAM); temp files are removed after
  each response; stale dirs are purged at startup.
- **No auth on the API** (by design — only your bot should call it). Keep it on
  an internal network or behind a reverse proxy (nginx/caddy) with request size
  and rate limits. The built-in limiter is per-process.
- Prefer **MP4 (H.264+AAC)** for video and **MP3** for audio → Telegram-friendly.
- HLS/DASH sites may serve more steps (m3u8 segments); large files need a long
  caller timeout.
- If output is partial or missing, double-check **ffmpeg** is installed and on PATH.