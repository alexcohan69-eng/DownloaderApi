"""
Minimal Telegram bot that uses the downloader API.

Flow:
    user sends a URL  ->  bot calls GET /info (preview caption)
                      ->  bot calls GET /download (raw file bytes)
                      ->  bot uploads the file to Telegram

Run it from a machine that can reach the API:

    pip install python-telegram-bot requests
    export BOT_TOKEN="123456:ABC..."
    export DOWNLOADER_API="http://127.0.0.1:8000"
    python examples/telegram_bot.py

This is a single-file example on purpose — adapt it to your own bot.
"""

from __future__ import annotations

import asyncio
import os
import re

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

API = os.getenv("DOWNLOADER_API", "http://127.0.0.1:8000").rstrip("/")
BOT_TOKEN = os.environ["BOT_TOKEN"]
# Set per-request (e.g. which site the user is pulling from):
COOKIE_FILE = os.getenv("COOKIE_FILE")  # e.g. "youtube.txt" from ./cookies/

URL_RE = re.compile(r"https?://\S+", re.I)


def pick_url(text: str) -> str | None:
    m = URL_RE.search(text or "")
    if not m:
        return None
    return m.group(0).rstrip(".,;!?)")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Send me any media URL. I'll download it for you.\n"
        "Prefix with `-a` for audio only, e.g.:  -a https://youtu.be/x\n"
        "Prefix with `-a 128` to choose a bitrate, or `-v 720p` for video quality."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    audio = bool(re.search(r"(^|\s)-a(\s|$)", text))
    quality = "best"

    m_quality = re.search(r"-a\s+(320|256|192|128|96|64)\b", text) or \
                re.search(r"-v\s+(best|2160p|1440p|1080p|720p|480p|360p)\b", text)
    if m_quality:
        quality = m_quality.group(1)

    url = pick_url(text)
    if not url:
        await update.message.reply_text("No URL found in your message.")
        return

    chat = update.effective_chat.id
    msg = await update.message.reply_text("🔍 Getting media info…")
    info: dict = {}

    # 1) Preview (optional but nice)
    try:
        # Fixed: Running the blocking requests.get in a background thread
        r = await asyncio.to_thread(requests.get, f"{API}/info", params={"url": url}, timeout=30)
        r.raise_for_status()
        info = r.json()
        caption = (
            f"📺 {info.get('title') or 'Media'}"
            + (f"\n👤 {info.get('uploader')}" if info.get("uploader") else "")
            + (f"\n⏱ {info.get('duration') or 0:.0f}s" if isinstance(info.get("duration"), (int, float)) else "")
            + ("\n📚 Playlist" if info.get("is_playlist") else "")
        )
        await msg.edit_text(f"{caption}\n\n⬇️ Downloading…")
    except requests.RequestException as e:
        await msg.edit_text(f"⚠️ Could not reach info API: {e}")

    # 2) Download the raw bytes
    params = {"url": url, "media_type": "audio" if audio else "video", "quality": quality}
    if COOKIE_FILE:
        params["cookies"] = COOKIE_FILE

    try:
        # Fixed: Running the long blocking download request in a background thread
        resp = await asyncio.to_thread(requests.get, f"{API}/download", params=params, timeout=1800)
    except requests.RequestException as e:
        await msg.edit_text(f"⚠️ Download request failed: {e}")
        return

    if resp.status_code != 200:
        try:
            err = resp.json().get("error")
        except ValueError:
            err = resp.text[:300]
        await msg.edit_text(f"❌ {err}")
        return

    file_name = resp.headers.get("X-File-Name") or f"media.download"
    # Save to a temp file, then send it.
    tmp_path = f"/tmp/dl_{os.getpid()}_{os.urandom(4).hex()}_{file_name}"
    with open(tmp_path, "wb") as fh:
        fh.write(resp.content)

    try:
        with open(tmp_path, "rb") as fh:
            if audio:
                await context.bot.send_audio(
                    chat_id=chat, audio=fh, filename=file_name,
                    caption=info.get("title", ""),
                )
            else:
                await context.bot.send_video(
                    chat_id=chat, video=fh, filename=file_name,
                    caption=info.get("title", ""),
                )
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Sending failed: {e}")
    finally:
        os.remove(tmp_path)


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
