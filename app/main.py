"""Universal Media Downloader API.

Call it from a Telegram bot (or anything else) like this:

    GET /download?url=https://youtu.be/...&media_type=video&quality=720p

It downloads the media with yt-dlp and streams it back as the raw file —
the bot then uploads those bytes straight to Telegram. Set cookies by
dropping a Netscape-format file into ./cookies/ and passing
``cookies=filename.txt``.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import tempfile
import urllib.parse
from pathlib import Path
from queue import Empty
from typing import Optional

from fastapi import (BackgroundTasks, Depends, FastAPI, Header, HTTPException,
                     Query, Request)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               StreamingResponse)
from pydantic import BaseModel, Field, ValidationError, validator

from . import config, jobs, logbuffer
from .downloader import (AUDIO_BITRATES, VIDEO_FORMATS, DownloadError,
                         Downloader, DownloadResult, MEDIA_TYPES)
from .jobs import JobParams
from .landing_page import LANDING_PAGE_HTML
from .logs_page import LOGS_PAGE_HTML
from .telegram import valid_token

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("app.api")

# Attach the in-memory ring buffer that backs the /logs web viewer to the
# root logger so it captures records from every module (app.api, app.jobs,
# app.downloader, uvicorn, etc).
logbuffer.install(capacity=config.LOG_BUFFER_SIZE)

app = FastAPI(
    title="Universal Media Downloader",
    description="yt-dlp powered downloader that returns media files to callers (e.g. a Telegram bot).",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Request models (used for the POST endpoints; GET uses the same fields)
# --------------------------------------------------------------------------

class DownloadRequest(BaseModel):
    url: str
    media_type: str = Field("video", description="video | audio")
    quality: str = Field("best", description="best/720p/etc for video, kbps for audio")
    cookies: Optional[str] = Field(None, description="cookie file name inside ./cookies/")
    playlist: bool = Field(False, description="download all entries of a playlist as a zip")

    @validator("url")
    def _valid_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("url is required")
        if "://" not in v or not urllib.parse.urlparse(v).scheme.lower() in ("http", "https"):
            # yt-dlp needs http(s); reject everything else (also blocks
            # file:// and other scheme tricks).
            raise ValueError("url must be http(s)")
        return v

    @validator("media_type")
    def _valid_media_type(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in MEDIA_TYPES:
            raise ValueError(f"media_type must be one of {MEDIA_TYPES}")
        return v

    @validator("cookies")
    def _valid_cookies(cls, v: Optional[str]) -> Optional[str]:
        if v and not Downloader._resolve_cookie_safe(v):
            raise ValueError("cookies file is invalid or missing")
        return v or None


class InfoRequest(BaseModel):
    url: str
    cookies: Optional[str] = None
    playlist: bool = False

    @validator("url")
    def _valid_url(cls, v: str) -> str:
        v = v.strip()
        if not v or "://" not in v:
            raise ValueError("url must be http(s)")
        return v

    @validator("cookies")
    def _valid_cookies(cls, v: Optional[str]) -> Optional[str]:
        if v and not Downloader._resolve_cookie_safe(v):
            raise ValueError("cookies file is invalid or missing")
        return v or None


class WebhookRequest(BaseModel):
    """Payload your Telegram bot POSTs to /jobs to trigger a push download."""

    url: str
    chat_id: str = Field(..., description="Telegram chat id to deliver into")
    bot_token: str = Field(..., description="Bot token used to send the file")
    media_type: str = Field("video", description="video | audio")
    quality: str = Field("best", description="best/720p/etc for video, kbps for audio")
    cookies: Optional[str] = Field(None, description="cookie file name inside ./cookies/")
    playlist: bool = Field(False, description="download a playlist and send as a zip")
    caption: Optional[str] = Field(None, description="override the message caption")
    reply_to_message_id: Optional[int] = Field(None, description="reply to this message")
    secret: Optional[str] = Field(None, description="shared secret (or use X-Webhook-Secret header)")

    @validator("url")
    def _valid_url(cls, v: str) -> str:
        v = v.strip()
        if not v or "://" not in v or urllib.parse.urlparse(v).scheme.lower() not in ("http", "https"):
            raise ValueError("url must be http(s)")
        return v

    @validator("chat_id")
    def _valid_chat(cls, v: str) -> str:
        v = str(v).strip()
        if not v:
            raise ValueError("chat_id is required")
        return v

    @validator("bot_token")
    def _valid_token(cls, v: str) -> str:
        v = (v or "").strip()
        if not valid_token(v):
            raise ValueError("bot_token looks invalid")
        return v

    @validator("media_type")
    def _valid_media_type(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in MEDIA_TYPES:
            raise ValueError(f"media_type must be one of {MEDIA_TYPES}")
        return v

    @validator("cookies")
    def _valid_cookies(cls, v: Optional[str]) -> Optional[str]:
        if v and not Downloader._resolve_cookie_safe(v):
            raise ValueError("cookies file is invalid or missing")
        return v or None


# --------------------------------------------------------------------------
# Rate limiting (simple in-memory, per-IP)
# --------------------------------------------------------------------------

_requests: dict[str, list[float]] = {}


def rate_limit(request: Request) -> None:
    if config.RATE_LIMIT_MAX <= 0:
        return
    import time
    now = time.monotonic()
    ip = request.client.host if request.client else "unknown"
    window = _requests.setdefault(ip, [])
    window[:] = [t for t in window if now - t < config.RATE_LIMIT_WINDOW]
    if len(window) >= config.RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too many requests. Slow down.")
    window.append(now)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _header_name(name: str | None) -> str:
    return (name or "media").replace("\r", "").replace("\n", "")


def _check_model(model: type[BaseModel], **values) -> BaseModel:
    """Build a request model or lift pydantic errors into HTTP 422."""
    try:
        return model(**values)
    except ValidationError as e:
        errs = e.errors()
        loc = ".".join(str(x) for x in errs[0]["loc"]) if errs else "?"
        raise HTTPException(status_code=422,
                            detail=f"{loc}: {errs[0]['msg'] if errs else 'invalid value'}") from e


def _cleanup_dirs(paths: list[Path]) -> None:
    for p in paths:
        try:
            if p.is_dir():
                Downloader.cleanup(p)
            else:
                p.unlink(missing_ok=True)
        except OSError:
            log.warning("cleanup of %s failed", p)


def _download(url: str, media_type: str, quality: str,
              cookies: Optional[str], playlist: bool, progress: dict) -> DownloadResult:
    d = Downloader(cookie_name=cookies)
    return d.download(url, media_type=media_type, quality=quality,
                      playlist=playlist, progress=progress)


def _fetch_info(req: InfoRequest) -> dict:
    d = Downloader(cookie_name=req.cookies)
    try:
        info = d.info(req.url, playlist=req.playlist)
    except DownloadError as e:
        raise HTTPException(status_code=400, detail=e.msg) from e
    return {"ok": True, **info}


# --------------------------------------------------------------------------
# Routes. NOTE: these are sync `def` so FastAPI runs each blocking
# yt-dlp call in a worker thread and the event loop stays responsive.
# --------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def root() -> HTMLResponse:
    return HTMLResponse(LANDING_PAGE_HTML)


@app.get("/download")
def download_get(
    url: str = Query(...),
    media_type: str = Query("video"),
    quality: str = Query("best"),
    cookies: Optional[str] = Query(None),
    playlist: bool = Query(False),
    background: BackgroundTasks = BackgroundTasks(),
    _: None = Depends(rate_limit),
):
    body = _check_model(DownloadRequest, url=url, media_type=media_type,
                        quality=quality, cookies=cookies, playlist=playlist)
    return _serve_download(body, background)


@app.post("/download")
def download_post(
    body: DownloadRequest,
    background: BackgroundTasks = BackgroundTasks(),
):
    return _serve_download(body, background)


def _serve_download(req: DownloadRequest, background: BackgroundTasks):
    """Perform the download and return the file (or a zip for playlists)."""

    # Whitelist each option against the allowlists BEFORE touching yt-dlp.
    if req.media_type == "video":
        if req.quality not in VIDEO_FORMATS:
            raise HTTPException(status_code=422,
                                detail=f"Unknown video quality '{req.quality}'. "
                                       f"Allowed: {', '.join(VIDEO_FORMATS)}")
    else:
        if req.quality not in AUDIO_BITRATES:
            raise HTTPException(status_code=422,
                                detail=f"Unknown audio quality '{req.quality}'. "
                                       f"Allowed: {', '.join(AUDIO_BITRATES)}")

    progress: dict = {}
    try:
        result = _download(req.url, req.media_type, req.quality,
                           req.cookies, req.playlist, progress)
    except DownloadError as e:
        raise HTTPException(status_code=400, detail=e.msg) from e

    files = result.files
    keep: list[Path] = []
    info = result.info

    if len(files) == 1:
        file_path = files[0]
        keep.append(file_path.parent)
        ext = file_path.suffix.lstrip(".") or "bin"
        media_type_out = "video" if result.media_type == "video" else "audio"
        filename = f"{Downloader.sanitize_filename(info.title)}.{ext}"
        headers = {
            "X-File-Name": filename,
            "X-Media-Type": media_type_out,
            "X-Title": _header_name(info.title or "media"),
            "X-Duration": str(info.duration or ""),
            "X-Thumbnail": _header_name(info.thumbnail or ""),
        }
        mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        # Starlette sets Content-Disposition with the (sanitized) filename.
        response = FileResponse(
            path=file_path, media_type=mime, filename=filename, headers=headers,
        )
    else:
        # multiple files (playlist) -> zip
        tmp = Path(tempfile.mkstemp(prefix="dl_zip_", suffix=".zip",
                                    dir=config.DOWNLOADS_DIR)[1])
        try:
            Downloader.make_zip(files, tmp)
            keep.append(files[0].parent)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise HTTPException(status_code=400,
                                detail="Could not bundle playlist files.")
        keep.append(tmp)
        filename = f"{Downloader.sanitize_filename(info.title) or 'playlist'}.zip"
        response = FileResponse(
            path=tmp, media_type="application/zip", filename=filename,
            headers={"X-File-Count": str(len(files))},
        )

    # Clean the staging dir(s) and zip only after the response is streamed.
    background.add_task(_cleanup_dirs, keep)
    log.info("served %s '%s' (%s files) in %.1fs",
             result.media_type, filename, len(files), result.elapsed)
    return response


@app.get("/info")
def info_get(
    url: str = Query(...),
    cookies: Optional[str] = Query(None),
    playlist: bool = Query(False),
):
    return _fetch_info(_check_model(InfoRequest, url=url, cookies=cookies,
                                    playlist=playlist))


@app.post("/info")
def info_post(body: InfoRequest):
    return _fetch_info(body)


# --------------------------------------------------------------------------
# Webhook / async job flow (Cobalt-style push delivery).
#
#   Your bot ── POST /jobs {url, chat_id, bot_token, ...} ──▶ here
#   We return 202 instantly, download in the background, then send the file
#   straight into the Telegram chat using the supplied bot token.
# --------------------------------------------------------------------------

def _validate_quality(media_type: str, quality: str) -> None:
    if media_type == "video":
        if quality not in VIDEO_FORMATS:
            raise HTTPException(status_code=422,
                                detail=f"Unknown video quality '{quality}'. "
                                       f"Allowed: {', '.join(VIDEO_FORMATS)}")
    elif quality not in AUDIO_BITRATES:
        raise HTTPException(status_code=422,
                            detail=f"Unknown audio quality '{quality}'. "
                                   f"Allowed: {', '.join(AUDIO_BITRATES)}")


@app.post("/jobs", status_code=202)
def create_job(
    body: WebhookRequest,
    x_webhook_secret: Optional[str] = Header(None),
    _: None = Depends(rate_limit),
):
    # Auth: shared secret from header or body (only enforced if configured).
    if config.WEBHOOK_SECRET:
        provided = x_webhook_secret or body.secret
        if provided != config.WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="Invalid or missing webhook secret.")

    _validate_quality(body.media_type, body.quality)

    job = jobs.store.submit(JobParams(
        url=body.url,
        chat_id=body.chat_id,
        bot_token=body.bot_token,
        media_type=body.media_type,
        quality=body.quality,
        cookies=body.cookies,
        playlist=body.playlist,
        caption=body.caption,
        reply_to_message_id=body.reply_to_message_id,
    ))
    log.info("queued job %s -> chat %s (%s)", job.id, body.chat_id, body.media_type)
    return {"ok": True, "job_id": job.id, "status": job.status}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    return {"ok": True, **job.public()}


# --------------------------------------------------------------------------
# Live log viewer (/logs). Read-only, in-memory, process-local — a quick way
# to watch what the service is doing without shelling into Render.
# --------------------------------------------------------------------------

def _check_logs_secret(request: Request, key: Optional[str] = None,
                       x_logs_secret: Optional[str] = None) -> None:
    if not config.LOGS_SECRET:
        return
    provided = x_logs_secret or key or request.query_params.get("key")
    if provided != config.LOGS_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing logs key.")


def _sse_event(entry: dict) -> str:
    return f"data: {json.dumps(entry)}\n\n"


def _log_stream(request: Request):
    buf = logbuffer.buffer
    assert buf is not None  # installed at import time, above
    q = buf.subscribe()
    try:
        for entry in buf.recent():
            yield _sse_event(entry)
        while True:
            try:
                entry = q.get(timeout=15)
                yield _sse_event(entry)
            except Empty:
                # Comment ping keeps proxies/browsers from timing out an
                # idle SSE connection.
                yield ": keep-alive\n\n"
    finally:
        buf.unsubscribe(q)


@app.get("/logs", include_in_schema=False)
def logs_page(request: Request, key: Optional[str] = Query(None)):
    _check_logs_secret(request, key=key)
    return HTMLResponse(LOGS_PAGE_HTML)


@app.get("/logs/stream", include_in_schema=False)
def logs_stream(request: Request, key: Optional[str] = Query(None),
                x_logs_secret: Optional[str] = Header(None)):
    _check_logs_secret(request, key=key, x_logs_secret=x_logs_secret)
    return StreamingResponse(
        _log_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/logs/data", include_in_schema=False)
def logs_data(request: Request, key: Optional[str] = Query(None),
              x_logs_secret: Optional[str] = Header(None),
              limit: int = Query(200, ge=1, le=2000)):
    _check_logs_secret(request, key=key, x_logs_secret=x_logs_secret)
    buf = logbuffer.buffer
    return {"ok": True, "logs": buf.recent(limit) if buf else []}


@app.exception_handler(HTTPException)
async def _http_exc_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"ok": False, "error": str(exc.detail)},
    )


@app.exception_handler(RequestValidationError)
async def _validation_exc_handler(request: Request, exc: RequestValidationError):
    errs = exc.errors()
    loc = ".".join(str(x) for x in errs[0]["loc"]) if errs else "?"
    msg = errs[0]["msg"] if errs else "Invalid parameters"
    return JSONResponse(
        status_code=422,
        content={"ok": False, "error": f"{loc}: {msg}"},
    )


# Purge stale staging dirs on startup.
_stale = 0
for _p in config.DOWNLOADS_DIR.iterdir():
    if _p.is_dir() and _p.name.startswith(("dl_", "dl_zip_")):
        import time as _time
        try:
            age = _time.time() - _p.stat().st_mtime
            if age > config.TEMP_LIFETIME:
                Downloader.cleanup(_p)
            else:
                _stale += 1
        except OSError:
            pass
if _stale:
    log.warning("%s recent temp dirs left from a previous run", _stale)


