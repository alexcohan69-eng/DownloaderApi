"""Async download jobs for the webhook flow.

``POST /jobs`` hands a job here and returns immediately. Each job runs on a
small thread pool: it downloads with yt-dlp, then pushes the file straight
into the requested Telegram chat using the per-request bot token. The chat
gets live status messages so it feels like Cobalt.

State lives in memory only — restart-safe delivery would need a real queue
(Redis/RQ, Celery), which is intentionally out of scope for a single small
service. Finished job records are kept briefly so the bot can poll status.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import config
from .downloader import Downloader, DownloadError
from .telegram import TelegramClient, TelegramError

log = logging.getLogger("app.jobs")

_MB = 1024 * 1024


@dataclass
class Job:
    id: str
    chat_id: str | int
    status: str = "queued"          # queued|downloading|uploading|done|error
    detail: str = ""
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)

    def public(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "status": self.status,
            "detail": self.detail,
            "created": round(self.created, 3),
            "updated": round(self.updated, 3),
        }


class JobStore:
    """Thread-safe job registry with a background thread pool."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, config.MAX_CONCURRENT_JOBS),
            thread_name_prefix="dljob",
        )

    def _set(self, job: Job, status: str, detail: str = "") -> None:
        with self._lock:
            job.status = status
            job.detail = detail
            job.updated = time.time()

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def _purge_stale(self) -> None:
        cutoff = time.time() - config.JOB_RECORD_LIFETIME
        with self._lock:
            stale = [
                jid for jid, j in self._jobs.items()
                if j.status in ("done", "error") and j.updated < cutoff
            ]
            for jid in stale:
                self._jobs.pop(jid, None)

    def submit(self, params: "JobParams") -> Job:
        self._purge_stale()
        job = Job(id=uuid.uuid4().hex[:16], chat_id=params.chat_id)
        with self._lock:
            self._jobs[job.id] = job
        self._pool.submit(self._run, job, params)
        return job

    # -- worker ------------------------------------------------------------

    def _run(self, job: Job, p: "JobParams") -> None:
        tg = TelegramClient(p.bot_token, api_base=p.api_base)
        status_msg_id: Optional[int] = None
        keep_dir: Optional[Path] = None
        last_edit = 0.0

        def status(text: str) -> None:
            nonlocal status_msg_id
            if status_msg_id is None:
                try:
                    res = tg.send_message(job.chat_id, text,
                                          reply_to_message_id=p.reply_to_message_id)
                    status_msg_id = res.get("message_id")
                except TelegramError as e:
                    log.warning("status send failed: %s", e.msg)
            else:
                tg.edit_message(job.chat_id, status_msg_id, text)

        try:
            self._set(job, "downloading", "Fetching media")
            status("Downloading your media...")

            progress: dict[str, Any] = {}

            def on_progress() -> None:
                # Throttle chat edits to at most one every 4s to respect
                # Telegram's rate limits.
                nonlocal last_edit
                now = time.monotonic()
                if now - last_edit < 4:
                    return
                pct = progress.get("percent")
                if isinstance(pct, int) and pct > 0:
                    last_edit = now
                    
                    # Run Telegram API calls in a separate thread so yt-dlp isn't blocked
                    def update_tg():
                        tg.send_chat_action(job.chat_id,
                                            "upload_video" if p.media_type == "video"
                                            else "upload_audio")
                        if status_msg_id is not None:
                            tg.edit_message(job.chat_id, status_msg_id,
                                            f"Downloading your media... {pct}%")
                    
                    threading.Thread(target=update_tg, daemon=True).start()

            # Wire the downloader's progress dict to our throttled callback by
            # polling it from a hook. The Downloader mutates ``progress`` in
            # place, so wrap it to also invoke our edit.
            hooked = _ProgressBridge(progress, on_progress)

            d = Downloader(cookie_name=p.cookies)
            result = d.download(
                p.url, media_type=p.media_type, quality=p.quality,
                playlist=p.playlist, progress=hooked,
            )
            keep_dir = result.files[0].parent if result.files else None

            # Bundle a playlist into a single zip for delivery as a document.
            files = result.files
            info = result.info
            caption = p.caption or (info.title or "")[:1024]

            if len(files) > 1:
                self._set(job, "uploading", "Bundling playlist")
                status("Bundling playlist into a zip...")
                zip_path = files[0].parent / f"{Downloader.sanitize_filename(info.title) or 'playlist'}.zip"
                Downloader.make_zip(files, zip_path)
                self._check_size(zip_path)
                self._set(job, "uploading", "Uploading zip")
                status("Uploading to Telegram...")
                tg.send_document(job.chat_id, zip_path, caption=caption,
                                 filename=zip_path.name)
            else:
                file_path = files[0]
                self._check_size(file_path)
                ext = file_path.suffix.lstrip(".") or "bin"
                out_name = f"{Downloader.sanitize_filename(info.title)}.{ext}"
                duration = int(info.duration) if info.duration else None
                self._set(job, "uploading", "Uploading to Telegram")
                status("Uploading to Telegram...")
                if result.media_type == "audio":
                    tg.send_audio(job.chat_id, file_path, caption=caption,
                                  duration=duration, title=info.title,
                                  performer=info.uploader, filename=out_name)
                else:
                    tg.send_video(job.chat_id, file_path, caption=caption,
                                  duration=duration, filename=out_name)

            if status_msg_id is not None:
                tg.delete_message(job.chat_id, status_msg_id)
            self._set(job, "done", "Delivered")
            log.info("job %s delivered %s in %.1fs", job.id,
                     result.media_type, result.elapsed)

        except _TooLarge as e:
            self._set(job, "error", e.msg)
            if status_msg_id is not None:
                tg.edit_message(job.chat_id, status_msg_id, e.msg)
            else:
                _safe_notify(tg, job.chat_id, e.msg)
        except DownloadError as e:
            msg = f"Download failed: {e.msg}"
            self._set(job, "error", msg)
            if status_msg_id is not None:
                tg.edit_message(job.chat_id, status_msg_id, msg)
            else:
                _safe_notify(tg, job.chat_id, msg)
        except TelegramError as e:
            self._set(job, "error", e.msg)
            log.warning("job %s telegram error: %s", job.id, e.msg)
        except Exception as e:  # noqa: BLE001 - last-resort guard
            log.exception("job %s crashed", job.id)
            msg = "Something went wrong while processing your media."
            self._set(job, "error", f"{msg} ({e})")
            if status_msg_id is not None:
                tg.edit_message(job.chat_id, status_msg_id, msg)
        finally:
            if keep_dir is not None:
                Downloader.cleanup(keep_dir)

    @staticmethod
    def _check_size(path: Path) -> None:
        limit = config.MAX_TELEGRAM_UPLOAD_MB * _MB
        size = path.stat().st_size
        if size > limit:
            raise _TooLarge(
                f"This file is {size / _MB:.1f} MB, over the "
                f"{config.MAX_TELEGRAM_UPLOAD_MB} MB Telegram upload limit. "
                f"Try a lower quality (e.g. 720p or 480p) or audio only."
            )


class _TooLarge(Exception):
    def __init__(self, msg: str):
        super().__init__(msg)
        self.msg = msg


class _ProgressBridge(dict):
    """A dict that fires a callback whenever the downloader updates it."""

    def __init__(self, backing: dict[str, Any], cb):
        super().__init__()
        self._backing = backing
        self._cb = cb

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, value)
        self._backing[key] = value
        try:
            self._cb()
        except Exception:  # noqa: BLE001 - progress must never break a job
            pass


def _safe_notify(tg: TelegramClient, chat_id: str | int, text: str) -> None:
    try:
        tg.send_message(chat_id, text)
    except TelegramError:
        pass


@dataclass
class JobParams:
    url: str
    chat_id: str | int
    bot_token: str
    media_type: str = "video"
    quality: str = "best"
    cookies: Optional[str] = None
    playlist: bool = False
    caption: Optional[str] = None
    reply_to_message_id: Optional[int] = None
    api_base: Optional[str] = None


# Single process-wide store.
store = JobStore()
