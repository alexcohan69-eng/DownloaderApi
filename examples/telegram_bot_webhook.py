"""
Cobalt-style Telegram bot: fire a webhook and forget.

Instead of downloading the file itself, this bot just tells the downloader
service "send this URL to this chat". The downloader does the work and
pushes the finished video/audio straight into the chat — the file never
passes through this bot process, so the bot stays instant and cheap.

Flow:
    user sends a URL
        -> bot POSTs {url, chat_id, bot_token} to  <DOWNLOADER_API>/jobs
        -> downloader replies 202 immediately
        -> downloader posts status + the final file directly to the chat

Run:
    pip install python-telegram-bot requests
    export BOT_TOKEN="123456:ABC..."
    export DOWNLOADER_API="https://media-downloader.onrender.com"
    export WEBHOOK_SECRET="the-same-secret-set-on-the-downloader"   # optional
    python examples/telegram_bot_webhook.py

This is a single-file example — drop the send_job() logic into your own bot.
"""

from __future__ import annotations

import os
import re

import requests
from telegram import Update
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          MessageHandler, filters)

API = os.getenv("DOWNLOADER_API", "http://127.0.0.1:8000").rstrip("/")
BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")          # optional
COOKIE_FILE = os.getenv("COOKIE_FILE")                # e.g. "youtube.txt"

URL_RE = re.compile(r"https?://\S+", re.I)


def pick_url(text: str) -> str | None:
    m = URL_RE.search(text or "")
    return m.group(0).rstrip(".,;!?)") if m else None


def send_job(url: str, chat_id: int, *, audio: bool, quality: str) -> tuple[bool, str]:
    """Fire the webhook. Returns (accepted, message)."""
    payload = {
        "url": url,
        "chat_id": str(chat_id),
        "bot_token": BOT_TOKEN,          # downloader sends the file with this
        "media_type": "audio" if audio else "video",
        "quality": quality,
    }
    if COOKIE_FILE:
        payload["cookies"] = COOKIE_FILE

    headers = {}
    if WEBHOOK_SECRET:
        headers["X-Webhook-Secret"] = WEBHOOK_SECRET

    try:
        r = requests.post(f"{API}/jobs", json=payload, headers=headers, timeout=30)
    except requests.RequestException as e:
        return False, f"Could not reach the downloader: {e}"

    if r.status_code == 202:
        return True, "Queued. The file will arrive here shortly."
    try:
        return False, r.json().get("error", r.text[:300])
    except ValueError:
        return False, f"HTTP {r.status_code}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Send me any media URL and I'll deliver it here.\n"
        "  -a            audio only\n"
        "  -a 128        audio at 128 kbps\n"
        "  -v 720p       video at 720p"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    audio = bool(re.search(r"(^|\s)-a(\s|$)", text))

    quality = "best"
    m = (re.search(r"-a\s+(320|256|192|128|96|64)\b", text)
         or re.search(r"-v\s+(best|2160p|1440p|1080p|720p|480p|360p)\b", text))
    if m:
        quality = m.group(1)

    url = pick_url(text)
    if not url:
        await update.message.reply_text("No URL found in your message.")
        return

    # Fire and forget — the downloader takes over from here.
    ok, msg = send_job(url, update.effective_chat.id, audio=audio, quality=quality)
    if not ok:
        await update.message.reply_text(f"Could not start: {msg}")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
