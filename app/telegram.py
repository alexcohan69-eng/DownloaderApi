"""Tiny Telegram Bot API client used to push finished media into a chat.

Only the handful of methods the job runner needs are implemented. The bot
token is supplied per request (see ``POST /jobs``), so nothing is stored on
disk. All calls go through ``config.TELEGRAM_API_BASE`` — point that at a
self-hosted telegram-bot-api server to raise the 50 MB upload limit.
"""

from __future__ import annotations

import logging
import mimetypes
import re
from pathlib import Path
from typing import Any, Optional

import requests

from . import config

log = logging.getLogger("app.telegram")

# Telegram bot tokens look like "123456789:AA...". Validate before use so a
# malformed token never gets embedded into a request URL.
_TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")


class TelegramError(Exception):
    """A user-facing Telegram API failure. ``msg`` is safe to surface."""

    def __init__(self, msg: str):
        super().__init__(msg)
        self.msg = msg


def valid_token(token: str) -> bool:
    return bool(_TOKEN_RE.match(token or ""))


class TelegramClient:
    def __init__(self, token: str, api_base: Optional[str] = None,
                 timeout: int = 300):
        if not valid_token(token):
            raise TelegramError("Invalid Telegram bot token.")
        self.token = token
        self.api_base = (api_base or config.TELEGRAM_API_BASE).rstrip("/")
        self.timeout = timeout

    # -- low level ---------------------------------------------------------

    def _url(self, method: str) -> str:
        return f"{self.api_base}/bot{self.token}/{method}"

    def _call(self, method: str, *, data: dict[str, Any],
              files: Optional[dict[str, Any]] = None,
              timeout: Optional[int] = None) -> dict[str, Any]:
        # Drop None values so we don't send empty fields.
        payload = {k: v for k, v in data.items() if v is not None}
        try:
            resp = requests.post(
                self._url(method),
                data=payload,
                files=files,
                timeout=timeout or self.timeout,
            )
        except requests.RequestException as e:
            raise TelegramError(f"Could not reach Telegram: {e}") from e

        try:
            body = resp.json()
        except ValueError:
            raise TelegramError(
                f"Telegram returned a non-JSON response (HTTP {resp.status_code})."
            )

        if not body.get("ok"):
            desc = body.get("description") or f"HTTP {resp.status_code}"
            raise TelegramError(f"Telegram error: {desc}")
        return body.get("result") or {}

    # -- messages ----------------------------------------------------------

    def send_message(self, chat_id: str | int, text: str,
                     reply_to_message_id: Optional[int] = None) -> dict[str, Any]:
        return self._call("sendMessage", data={
            "chat_id": chat_id,
            "text": text,
            "reply_to_message_id": reply_to_message_id,
            "disable_web_page_preview": True,
        }, timeout=30)

    def edit_message(self, chat_id: str | int, message_id: int,
                     text: str) -> Optional[dict[str, Any]]:
        try:
            return self._call("editMessageText", data={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "disable_web_page_preview": True,
            }, timeout=30)
        except TelegramError:
            # Editing is best-effort (e.g. "message is not modified").
            return None

    def delete_message(self, chat_id: str | int, message_id: int) -> None:
        try:
            self._call("deleteMessage", data={
                "chat_id": chat_id, "message_id": message_id,
            }, timeout=30)
        except TelegramError:
            pass

    def send_chat_action(self, chat_id: str | int, action: str) -> None:
        try:
            self._call("sendChatAction", data={
                "chat_id": chat_id, "action": action,
            }, timeout=15)
        except TelegramError:
            pass

    # -- media -------------------------------------------------------------

    def send_video(self, chat_id: str | int, path: Path, *,
                   caption: Optional[str] = None,
                   duration: Optional[int] = None,
                   filename: Optional[str] = None) -> dict[str, Any]:
        mime = mimetypes.guess_type(path.name)[0] or "video/mp4"
        with path.open("rb") as fh:
            return self._call("sendVideo", data={
                "chat_id": chat_id,
                "caption": caption,
                "duration": duration,
                "supports_streaming": True,
            }, files={"video": (filename or path.name, fh, mime)})

    def send_audio(self, chat_id: str | int, path: Path, *,
                   caption: Optional[str] = None,
                   duration: Optional[int] = None,
                   title: Optional[str] = None,
                   performer: Optional[str] = None,
                   filename: Optional[str] = None) -> dict[str, Any]:
        mime = mimetypes.guess_type(path.name)[0] or "audio/mpeg"
        with path.open("rb") as fh:
            return self._call("sendAudio", data={
                "chat_id": chat_id,
                "caption": caption,
                "duration": duration,
                "title": title,
                "performer": performer,
            }, files={"audio": (filename or path.name, fh, mime)})

    def send_document(self, chat_id: str | int, path: Path, *,
                      caption: Optional[str] = None,
                      filename: Optional[str] = None) -> dict[str, Any]:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as fh:
            return self._call("sendDocument", data={
                "chat_id": chat_id,
                "caption": caption,
            }, files={"document": (filename or path.name, fh, mime)})
