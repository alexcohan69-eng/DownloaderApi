# Universal Media Downloader

A tiny web service that downloads media from almost any site (YouTube, Instagram,
TikTok, Twitter/X, Facebook, and [1000+ more](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md))
using [yt-dlp](https://github.com/yt-dlp/yt-dlp), and delivers it **straight into
a Telegram chat** — exactly like [Cobalt](https://cobalt.tools), but self-hosted
and controlled by your own bot.

You send it a URL over a webhook. It downloads the media in the background and
sends the finished video/audio into the chat for you. The file never passes
through your bot — so your bot stays fast and cheap.

---

## How it works

```
  Your Telegram bot                 This service (on Render)              Telegram
  ─────────────────                 ────────────────────────             ────────
        │                                     │                             │
   user sends a URL                           │                             │
        │                                     │                             │
        │   POST /jobs                        │                             │
        │   { url, chat_id, bot_token } ─────▶ │                             │
        │                                     │                             │
        │ ◀──── 202 Accepted (instant) ────── │                             │
        │                                     │                             │
        │                          downloads with yt-dlp                    │
        │                                     │                             │
        │                                     │  sendVideo / sendAudio ────▶ │
        │                                     │                             │
        │                                     │            file appears in chat
```

Your bot's only job is to fire one small request and forget about it. This
service does the heavy lifting and talks to Telegram directly.

**Two ways to call it:**

| Mode | Endpoint | Who uploads to Telegram? | Best for |
| --- | --- | --- | --- |
| **Webhook (push)** ⭐ | `POST /jobs` | This service | Telegram bots — recommended |
| **Direct (pull)** | `GET /download` | You do | Scripts, testing, non-Telegram use |

The webhook mode is what you want for a Telegram bot. The direct mode simply
returns the raw file bytes to whoever called it.

---

## Part 1 — Deploy to Render

You need a [GitHub](https://github.com) account and a free
[Render](https://render.com) account.

### Step 1 — Put this project on GitHub

```bash
git init
git add .
git commit -m "Media downloader"
git branch -M main
git remote add origin https://github.com/YOUR_NAME/YOUR_REPO.git
git push -u origin main
```

### Step 2 — Create the service on Render

1. Go to the [Render dashboard](https://dashboard.render.com) → **New +** → **Blueprint**.
2. Connect your GitHub account and pick this repository.
3. Render reads the included [`render.yaml`](render.yaml) and sets everything up
   automatically — it installs **ffmpeg** (needed to merge video + audio) and
   your Python dependencies.
4. Click **Apply**. Wait a few minutes for the first build.

When it's done, Render gives you a public URL like:

```
https://media-downloader-xxxx.onrender.com
```

That URL is your downloader. Open it in a browser — you should see a short help
page. That means it's live.

> **Free plan note:** Render's free services **sleep after 15 minutes** of no
> traffic and take ~30–60 seconds to wake up on the next request. The first
> download after a nap will feel slow. Upgrade to a paid plan to keep it always
> on.

### Step 3 — Protect it with a secret (recommended)

Your URL is public, so anyone who finds it could use your downloader. Lock it to
just your bot with a shared password:

1. In Render → your service → **Environment** → **Add Environment Variable**.
2. Add `YDL_WEBHOOK_SECRET` = *(any long random string you make up)*.
3. Save. Render redeploys automatically.

Now every request must include that secret (shown in Part 2), or it's rejected.

---

## Part 2 — Use it from your Telegram bot project

This is the main use case. In **your bot project**, when a user sends a URL, make
one HTTP request to this downloader. That's it.

### The request

`POST https://your-downloader.onrender.com/jobs`

Send a JSON body with these fields:

| Field | Required | Example | What it does |
| --- | :---: | --- | --- |
| `url` | ✅ | `"https://youtu.be/abc"` | The media link to download |
| `chat_id` | ✅ | `"123456789"` | The Telegram chat to deliver into |
| `bot_token` | ✅ | `"123:ABC..."` | Your bot's token (used to send the file) |
| `media_type` | | `"video"` or `"audio"` | Video (default) or audio-only |
| `quality` | | `"720p"` / `"320"` | Video: `best`,`1080p`,`720p`,`480p`,`360p`… · Audio: `320`,`192`,`128`… |
| `cookies` | | `"youtube.txt"` | Cookie file for logged-in sites (see Part 3) |
| `playlist` | | `true` | Download a whole playlist and send it as a `.zip` |
| `caption` | | `"Here you go!"` | Custom caption on the delivered file |

> **About `bot_token`:** you pass your bot's token so this service can send the
> file *as your bot*, into the same chat your user is talking to. Send the
> request over HTTPS (Render gives you HTTPS automatically) so it stays private.

### The response

You get `202 Accepted` **instantly** — before the download even starts:

```json
{ "ok": true, "job_id": "c71196284bcd4f8a", "status": "downloading" }
```

Your bot is now done. The user will see a live "Downloading…" message in their
chat, and then the finished video or audio a moment later.

### Copy-paste examples

**Python** (drop this into your existing bot):

```python
import requests

DOWNLOADER = "https://your-downloader.onrender.com"
SECRET = "your-webhook-secret"   # the one you set on Render (omit if none)

def download_to_chat(url: str, chat_id: int, bot_token: str, audio=False):
    resp = requests.post(
        f"{DOWNLOADER}/jobs",
        json={
            "url": url,
            "chat_id": str(chat_id),
            "bot_token": bot_token,
            "media_type": "audio" if audio else "video",
            "quality": "720p",
        },
        headers={"X-Webhook-Secret": SECRET},   # remove if you set no secret
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()   # {"ok": True, "job_id": "...", "status": "downloading"}
```

**Node.js / JavaScript:**

```js
async function downloadToChat(url, chatId, botToken, audio = false) {
  const res = await fetch("https://your-downloader.onrender.com/jobs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Webhook-Secret": "your-webhook-secret", // remove if you set no secret
    },
    body: JSON.stringify({
      url,
      chat_id: String(chatId),
      bot_token: botToken,
      media_type: audio ? "audio" : "video",
      quality: "720p",
    }),
  });
  return res.json(); // { ok: true, job_id: "...", status: "downloading" }
}
```

**curl** (to test from a terminal):

```bash
curl -X POST https://your-downloader.onrender.com/jobs \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: your-webhook-secret" \
  -d '{"url":"https://youtu.be/dQw4w9WgXcQ","chat_id":"123456789","bot_token":"123:ABC","quality":"720p"}'
```

### A complete example bot

A full, ready-to-run bot is included at
[`examples/telegram_bot_webhook.py`](examples/telegram_bot_webhook.py). It listens
for URLs and fires the webhook — copy its `send_job()` logic into your own bot.

### Checking on a job (optional)

You usually don't need to, but you can poll a job's progress:

```
GET https://your-downloader.onrender.com/jobs/<job_id>
```

```json
{ "ok": true, "job_id": "c71196284bcd4f8a", "status": "done", "detail": "Delivered" }
```

Status goes: `queued` → `downloading` → `uploading` → `done` (or `error`).

---

## Part 3 — Adding cookies (for logged-in / age-restricted sites)

Some videos need you to be **logged in** — private videos, age-restricted
YouTube, members-only content, Instagram, etc. yt-dlp handles this with a
**cookies file**: a text export of your browser's login for that site.

### Step 1 — Export cookies from your browser

Install a browser extension that exports cookies in **Netscape format**:

- Chrome/Edge: **"Get cookies.txt LOCALLY"**
- Firefox: **"cookies.txt"**

Then:

1. Log in to the site (e.g. YouTube) in your browser as normal.
2. Click the extension while on that site.
3. **Export** → it downloads a file like `cookies.txt`.

> Tip: use a throwaway/secondary account for this — you're handing its login to
> the server.

### Step 2 — Put the file in the `cookies/` folder

Rename it to something clear and drop it into this project's `cookies/` folder,
one file per site:

```
cookies/
├── youtube.txt
├── instagram.txt
└── twitter.txt
```

### Step 3 — Commit and push so Render gets it

The cookie files are committed with your repo **on purpose**, so Render can read
them (see [`.gitignore`](.gitignore) — it allows `cookies/*.txt`):

```bash
git add cookies/youtube.txt
git commit -m "Add YouTube cookies"
git push
```

Render redeploys and the file is now available on the server.

> ⚠️ **Keep your repo PRIVATE.** Cookie files are as sensitive as passwords —
> anyone with them can access your logged-in account. Never push cookies to a
> public repository.

### Step 4 — Reference the file in your request

Pass the **file name** (not a path) in the `cookies` field:

```json
{
  "url": "https://youtube.com/watch?v=PRIVATE",
  "chat_id": "123456789",
  "bot_token": "123:ABC",
  "cookies": "youtube.txt"
}
```

The service safely looks up `cookies/youtube.txt` and uses it for that download.

> Cookies expire over time. If a site starts failing with a login error, just
> re-export the cookies and push the updated file.

---

## Direct mode (optional): `GET /download`

If you want the raw file instead of Telegram delivery (for scripts or testing),
call `/download` and it streams the file back to you:

```bash
# Save a 720p video to a file
curl -L "https://your-downloader.onrender.com/download?url=https://youtu.be/abc&quality=720p" -o video.mp4

# Get info about a link without downloading
curl "https://your-downloader.onrender.com/info?url=https://youtu.be/abc"
```

`/download` accepts the same `url`, `media_type`, `quality`, `cookies`, and
`playlist` fields as query parameters or as a JSON `POST` body. Handy response
headers include `X-File-Name`, `X-Title`, and `X-Duration`. A full example bot
that uses this pull mode lives in [`examples/telegram_bot.py`](examples/telegram_bot.py).

---

## Configuration (environment variables)

All optional — the defaults are sensible. Set any of these in Render →
**Environment**.

| Variable | Default | What it does |
| --- | --- | --- |
| `YDL_WEBHOOK_SECRET` | *(none)* | Password required on `/jobs`. **Set this.** |
| `YDL_MAX_UPLOAD_MB` | `50` | Max file size to send to Telegram (see below) |
| `YDL_MAX_CONCURRENT_JOBS` | `2` | How many downloads run at once (keep low on free plan) |
| `YDL_MAX_PLAYLIST_ITEMS` | `20` | Max videos to grab from a playlist |
| `YDL_TIMEOUT` | `600` | Max seconds for one download |
| `YDL_RATE_LIMIT_MAX` | `10` | Max requests per IP per minute (`0` = off) |
| `YDL_PROXY` | *(none)* | Route yt-dlp through a proxy, e.g. `socks5://host:1080` |
| `TELEGRAM_API_BASE` | `https://api.telegram.org` | Point at a self-hosted Bot API server for big files |

---

## The 50 MB limit (important)

Telegram's public Bot API only lets bots upload files up to **50 MB**. If a
download is bigger, this service won't fail silently — it sends a clear message
to the chat telling the user to pick a lower quality (e.g. `480p`) or audio-only.

**Need bigger files (up to ~2 GB)?** Run your own
[telegram-bot-api](https://github.com/tdlib/telegram-bot-api) server and point
`TELEGRAM_API_BASE` at it, then raise `YDL_MAX_UPLOAD_MB` (e.g. to `2000`).

---

## Run it locally (for testing)

```bash
pip install -r requirements.txt   # you also need ffmpeg installed
./start.sh                        # serves on http://127.0.0.1:8000
```

Then send a test job to `http://127.0.0.1:8000/jobs`. Install ffmpeg first if you
don't have it (`apt install ffmpeg`, or `pkg install ffmpeg` on Termux).

---

## Project layout

```
app/
├── main.py        FastAPI app + all the endpoints
├── downloader.py  yt-dlp wrapper (with safety allowlists)
├── jobs.py        background job runner for the webhook flow
├── telegram.py    minimal Telegram Bot API client
└── config.py      all settings / environment variables
cookies/           your Netscape cookie files (*.txt)
examples/          ready-to-run example Telegram bots
render.yaml        Render deploy blueprint
Dockerfile         optional Docker deploy
start.sh           server entrypoint
```

---

## Security notes

- **Set `YDL_WEBHOOK_SECRET`** so only your bot can use the service.
- **Keep your repo private** — it contains your cookie files.
- User input is validated and allowlisted before it reaches yt-dlp (no shell
  injection, no path traversal on cookie names, only `http(s)` URLs accepted).
- Bot tokens are passed per-request and never written to disk.
