"""Universal media downloader built on yt-dlp.

Security note: every user-supplied option is mapped through an allowlist
below. We never pass raw caller input into yt-dlp options — only the URL
and a whitelisted cookie-file name ever reach the API from outside.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import time
import urllib.parse
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yt_dlp

from . import config

log = logging.getLogger("app.downloader")

# --------------------------------------------------------------------------
# Safe allowlists. Anything not in here is rejected before reaching yt-dlp.
# --------------------------------------------------------------------------

# Video: yt-dlp format-selector strings. "p" suffixes mean height caps.
# We *prefer* H.264 + AAC (the pair every Telegram/PWA client plays) and
# fall back to whatever "best" is when no H.264 stream exists.
A = "[acodec^=mp4a]"       # AAC
V = "[vcodec^=avc1]"       # H.264
VIDEO_FORMATS: dict[str, str] = {
    "best":  f"bestvideo{V}+bestaudio{A}/best{V}/best",
    "worst": "worst",
    "4320p": f"bestvideo[height<=4320]{V}+bestaudio{A}/best[height<=4320]{V}/best[height<=4320]/best",
    "2160p": f"bestvideo[height<=2160]{V}+bestaudio{A}/best[height<=2160]{V}/best[height<=2160]/best",
    "1440p": f"bestvideo[height<=1440]{V}+bestaudio{A}/best[height<=1440]{V}/best[height<=1440]/best",
    "1080p": f"bestvideo[height<=1080]{V}+bestaudio{A}/best[height<=1080]{V}/best[height<=1080]/best",
    "720p":  f"bestvideo[height<=720]{V}+bestaudio{A}/best[height<=720]{V}/best[height<=720]/best",
    "480p":  f"bestvideo[height<=480]{V}+bestaudio{A}/best[height<=480]{V}/best[height<=480]/best",
    "360p":  f"bestvideo[height<=360]{V}+bestaudio{A}/best[height<=360]{V}/best[height<=360]/best",
}

# Audio: preferredcodec is always mp3; bitrate is passed as kbps.
AUDIO_BITRATES: dict[str, int] = {
    "best": 0,   # 0 -> VBR "best" quality
    "320": 320,
    "256": 256,
    "192": 192,
    "128": 128,
    "96": 96,
    "64": 64,
    "worst": 64,
}

MEDIA_TYPES = {"video", "audio"}

# YouTube periodically breaks yt-dlp's default ("web") player client,
# producing errors like "Failed to extract any player response". Trying
# a few alternate clients as fallback makes extraction far more resilient
# without needing an immediate yt-dlp release to fix it. The "tv" and
# "tv_embedded" clients are also the ones yt-dlp uses to fetch age-gated
# and "sign in to confirm your age" videos *without* needing a logged-in
# cookie, so listing them ahead of "web" lets most age-restricted videos
# through automatically. If a video is *also* private/unlisted, a fresh
# cookies file for an account that can view it is still required.
_YOUTUBE_EXTRACTOR_ARGS = {
    "youtube": {"player_client": ["tv", "tv_embedded", "android", "web", "ios"]}
}

# X (formerly Twitter)'s GraphQL API sometimes answers a perfectly normal
# post with reason: "Suspended" — or, for posts that clearly contain
# media, a false "No video could be found in this tweet" — when the
# *querying session* (i.e. the account behind our cookies/x.txt) has
# itself been locked, limited, rate-limited, or suspended, not because
# the post's author is actually suspended or media-less. yt-dlp surfaces
# these verbatim as "[twitter] <id>: Suspended." or "[twitter] <id>: No
# video could be found in this tweet.". The fix is to retry the same URL
# as a logged-out guest (dropping our cookies) and, if that still fails,
# force the public syndication API, both of which sidestep the broken
# session entirely.
_X_HOSTS = {
    "twitter.com", "www.twitter.com", "mobile.twitter.com", "m.twitter.com",
    "x.com", "www.x.com", "mobile.x.com", "m.x.com",
}


def _is_x_url(url: str) -> bool:
    try:
        return urllib.parse.urlparse(url).netloc.lower() in _X_HOSTS
    except Exception:
        return False


def _is_retryable_x_error(exc: BaseException) -> bool:
    msg = str(getattr(exc, "msg", None) or exc).lower()
    return "suspend" in msg or "no video could be found" in msg


def _extract_with_fallback(base_opts: dict[str, Any], url: str,
                            download: bool) -> Any:
    """Run yt-dlp's extraction, retrying X's false "Suspended" / "No video
    could be found" errors.

    Only kicks in for x.com/twitter.com URLs that were fetched with a
    cookiefile; other sites and errors behave exactly as before.
    """
    attempts = [base_opts]
    if base_opts.get("cookiefile") and _is_x_url(url):
        guest_opts = {k: v for k, v in base_opts.items() if k != "cookiefile"}
        attempts.append(guest_opts)
        syndication_opts = dict(guest_opts)
        syndication_opts["extractor_args"] = {
            **guest_opts.get("extractor_args", {}),
            "twitter": {"api": ["syndication"]},
        }
        attempts.append(syndication_opts)

    last_exc: Optional[yt_dlp.utils.DownloadError] = None
    for i, opts in enumerate(attempts):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=download)
        except yt_dlp.utils.DownloadError as e:
            last_exc = e
            is_last = i == len(attempts) - 1
            if is_last or not _is_retryable_x_error(e):
                raise
            log.warning("X reported a false '%s' error using the "
                       "authenticated session for %s; retrying with a "
                       "different session (attempt %d/%d)",
                       str(getattr(e, "msg", None) or e).strip(), url, i + 2, len(attempts))
    raise last_exc  # pragma: no cover - unreachable, loop always returns or raises


def _summarize_formats(formats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trim yt-dlp's format list to the fields a bot wants to show."""
    out = []
    for f in formats[:40]:
        res = f.get("resolution")
        if not res and (f.get("width") or f.get("height")):
            res = f"{f.get('width') or ''}x{f.get('height') or ''}"
        out.append({
            "format_id": f.get("format_id"),
            "ext": f.get("ext"),
            "resolution": res,
            "fps": f.get("fps"),
            "vcodec": f.get("vcodec"),
            "acodec": f.get("acodec"),
            "filesize": f.get("filesize") or f.get("filesize_approx"),
        })
    return out


class DownloadError(Exception):
    """A user-facing download failure. ``msg`` is always safe to echo."""

    def __init__(self, msg: str, cause: Optional[Exception] = None):
        super().__init__(msg)
        self.msg = msg
        self.cause = cause


@dataclass
class MediaInfo:
    title: str = ""
    ext: Optional[str] = None
    duration: Optional[float] = None
    thumbnail: Optional[str] = None
    uploader: Optional[str] = None
    webpage_url: Optional[str] = None
    filesize: Optional[int] = None
    format_id: Optional[str] = None
    formats: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DownloadResult:
    files: list[Path]          # one file normally, many for a playlist
    info: MediaInfo
    media_type: str            # "video" | "audio"
    quality: str
    elapsed: float = 0.0


class Downloader:
    """One instance per request; keep it cheap and stateless."""

    def __init__(self, cookie_name: Optional[str] = None, proxy: Optional[str] = None):
        self.cookie_paths: list[Path] = self._get_cookie_paths(cookie_name)
        self.proxy = proxy or config.PROXY

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _resolve_cookie(name: str) -> Path:
        """Resolve a cookie file by name inside COOKIES_DIR, no traversal."""
        if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
            raise DownloadError("Invalid cookie file name.")
        path = (config.COOKIES_DIR / name).resolve()
        if config.COOKIES_DIR.resolve() not in path.parents or not path.is_file():
            raise DownloadError("Cookie file not found.")
        return path

    @staticmethod
    def _resolve_cookie_safe(name: str) -> bool:
        """Validation-only variant used by Pydantic (never raises)."""
        try:
            return bool(Downloader._resolve_cookie(name))
        except DownloadError:
            return False

    @staticmethod
    def _get_cookie_paths(preferred: Optional[str] = None) -> list[Path]:
        """Smart fallback: returns a prioritized list of cookie files to attempt."""
        paths = []
        if preferred:
            try:
                paths.append(Downloader._resolve_cookie(preferred))
            except DownloadError:
                pass
        
        # Always prioritize cookies.txt next
        default_cookie = config.COOKIES_DIR / "cookies.txt"
        if default_cookie.is_file() and default_cookie not in paths:
            paths.append(default_cookie)
            
        # Collect any remaining .txt files from the directory as a fallback
        try:
            for p in config.COOKIES_DIR.glob("*.txt"):
                if p.is_file() and p not in paths:
                    paths.append(p)
        except OSError:
            pass
            
        return paths

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Strip characters that are hostile in a filename or HTTP header."""
        name = re.sub(r"[\r\n\t/\\]", "_", name)
        name = re.sub(r"[^\w .()\[\]'&+,-]", "_", name)
        return name.strip(" ._") or "media"

    @staticmethod
    def _final_files(tmpdir: Path, expected_ext: Optional[str] = None) -> list[Path]:
        """Pick the real output file(s) from a staging dir."""
        files = [
            p for p in tmpdir.iterdir()
            if p.is_file() and not p.name.endswith((".part", ".ytdl", ".temp"))
        ]
        if not files:
            return []
        if len(files) == 1:
            return files
        # Prefer files matching the expected container (merged mp4 / mp3),
        # then the largest, and drop tiny leftovers (e.g. thumbnails we
        # did not ask for).
        if expected_ext:
            ext_files = [p for p in files if p.suffix.lower() == f".{expected_ext}"]
            if ext_files:
                return ext_files
        primary = max(files, key=lambda p: p.stat().st_size)
        return [primary]

    def _progress_hook(self, d: dict[str, Any], progress: dict[str, Any]) -> None:
        try:
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                down = d.get("downloaded_bytes") or 0
                progress["status"] = "downloading"
                progress["percent"] = round(100 * down / total) if total else 0
                progress["speed"] = d.get("speed")
            elif d.get("status") == "finished":
                progress["status"] = "processing"
                progress["percent"] = 100
            elif d.get("status") == "error":
                progress["status"] = "error"
        except Exception:
            pass  # progress reporting must never break a download

    def _run_extraction(self, base_opts: dict[str, Any], url: str, download: bool) -> Any:
        """Run extraction and rotate cookies automatically if an auth/age error occurs."""
        if not self.cookie_paths:
            return _extract_with_fallback(base_opts, url, download=download)
            
        last_exc = None
        for i, cp in enumerate(self.cookie_paths):
            opts = dict(base_opts)
            opts["cookiefile"] = str(cp)
            try:
                return _extract_with_fallback(opts, url, download=download)
            except yt_dlp.utils.DownloadError as e:
                last_exc = e
                msg = str(getattr(e, "msg", None) or e).lower()
                
                # Verify if the error is related to authentication or restrictions
                auth_keywords = ["sign in", "bot", "suspend", "no video", "age", "restrict", "private", "login", "member"]
                is_auth_error = any(k in msg for k in auth_keywords)
                
                if is_auth_error and i < len(self.cookie_paths) - 1:
                    log.warning("Cookie '%s' failed (Auth/Age Issue). Retrying with next cookie...", cp.name)
                    continue
                else:
                    break
                    
        raise last_exc

    # -- main entry point --------------------------------------------------

    def download(self, url: str, media_type: str = "video",
                 quality: str = "best", playlist: bool = False,
                 progress: Optional[dict[str, Any]] = None) -> DownloadResult:
        """Download ``url`` and return the resulting staged file(s).

        The caller is responsible for deleting the staging directory
        afterwards (see ``Downloader.cleanup``).
        """
        media_type = "audio" if media_type == "audio" else "video"
        dl_dir = Path(tempfile.mkdtemp(prefix="dl_", dir=config.DOWNLOADS_DIR))
        start = time.monotonic()
        try:
            if media_type == "video" and quality not in VIDEO_FORMATS:
                raise DownloadError(f"Unknown video quality '{quality}'.")
            if media_type == "audio" and quality not in AUDIO_BITRATES:
                raise DownloadError(f"Unknown audio quality '{quality}'.")

            opts: dict[str, Any] = {
                "outtmpl": str(dl_dir / "%(id)s.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "noplaylist": not playlist,
                "socket_timeout": 30,
                "retries": 3,
                "fragment_retries": 3,
                "continuedl": False,
                "noprogress": True,
                "windowsfilenames": True,
                "logger": log,
                "extractor_args": _YOUTUBE_EXTRACTOR_ARGS,
            }
            if progress is not None:
                opts["progress_hooks"] = [lambda d: self._progress_hook(d, progress)]
            if self.proxy:
                opts["proxy"] = self.proxy

            expected_ext: Optional[str]
            if media_type == "video":
                opts["format"] = VIDEO_FORMATS[quality]
                opts["merge_output_format"] = "mp4"
                expected_ext = "mp4"
            else:
                opts["format"] = "bestaudio/best"
                opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(AUDIO_BITRATES[quality]),
                }]
                expected_ext = "mp3"

            if playlist and config.MAX_PLAYLIST_ITEMS:
                opts["playlist_items"] = f"1:{config.MAX_PLAYLIST_ITEMS}"

            # Execute with automated cookie fallback
            info = self._run_extraction(opts, url, download=True)

            files = self._final_files(dl_dir, expected_ext)
            if not files:
                raise DownloadError("The media downloaded but no output file "
                                    "was produced. This can happen when "
                                    "ffmpeg is missing (needed for merging "
                                    "and audio conversion).")

            return DownloadResult(
                files=files,
                info=self._media_info(info),
                media_type=media_type,
                quality=quality,
                elapsed=time.monotonic() - start,
            )

        except DownloadError:
            self.cleanup(dl_dir)
            raise
        except yt_dlp.utils.DownloadError as e:
            self.cleanup(dl_dir)
            # e.exc_info may hold an UnsupportedError/ExtractorError
            raise DownloadError(self._friendly_error(e), cause=e)
        except Exception as e:
            self.cleanup(dl_dir)
            log.exception("Unexpected download error")
            raise DownloadError(f"Unexpected error: {e}") from e

    def info(self, url: str, playlist: bool = False) -> dict:
        """Fetch metadata only (no download) — used to preview a link.

        Returns a JSON-safe dict the bot can render as a caption: title,
        duration, thumbnail, uploader, and a summary of available formats.
        """
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": not playlist,
            "socket_timeout": 30,
            "skip_download": True,
            "extractor_args": _YOUTUBE_EXTRACTOR_ARGS,
        }
        if self.proxy:
            opts["proxy"] = self.proxy

        try:
            # Execute with automated cookie fallback
            base = self._run_extraction(opts, url, download=False)
        except yt_dlp.utils.DownloadError as e:
            raise DownloadError(self._friendly_error(e), cause=e)

        if isinstance(base, dict) and base.get("_type") == "playlist":
            entries = [e for e in (base.get("entries") or []) if isinstance(e, dict)]
            first = entries[0] if entries else {}
            out = {
                "is_playlist": True,
                "playlist_title": base.get("title"),
                "entry_count": len(entries) or (base.get("playlist_count") or 0),
                "title": first.get("title"),
                "duration": first.get("duration"),
                "thumbnail": first.get("thumbnail"),
                "uploader": first.get("uploader") or first.get("channel"),
                "webpage_url": first.get("webpage_url") or url,
                "formats": _summarize_formats(first.get("formats") or []),
            }
        else:
            d = base if isinstance(base, dict) else {}
            out = {
                "is_playlist": False,
                "playlist_title": None,
                "entry_count": 1,
                "title": d.get("title"),
                "duration": d.get("duration"),
                "thumbnail": d.get("thumbnail"),
                "uploader": d.get("uploader") or d.get("channel") or d.get("creator"),
                "webpage_url": d.get("webpage_url") or url,
                "formats": _summarize_formats(d.get("formats") or []),
            }
        return {k: (v if v is not None else "") for k, v in out.items()}

    # -- misc helpers -------------------------------------------------------

    @staticmethod
    def _media_info(info: Any) -> MediaInfo:
        # If yt-dlp returned a playlist, look at the first entry for info.
        if isinstance(info, dict) and info.get("_type") == "playlist":
            entries = info.get("entries") or []
            first = entries[0] if entries else {}
            info = first if isinstance(first, dict) else {}
        info = info if isinstance(info, dict) else {}
        data = info.get("info_dict", info)  # extract_info may double-wrap

        formats = []
        for f in (data.get("formats") or [])[:40]:
            formats.append({
                "format_id": f.get("format_id"),
                "ext": f.get("ext"),
                "resolution": f.get("resolution") or (
                    f"{f.get('width') or ''}x{f.get('height') or ''}".strip("x")
                ),
                "fps": f.get("fps"),
                "vcodec": f.get("vcodec"),
                "acodec": f.get("acodec"),
                "filesize": f.get("filesize") or f.get("filesize_approx"),
            })

        return MediaInfo(
            title=os.path.basename(str(data.get("title") or "media")),
            ext=data.get("ext"),
            duration=data.get("duration"),
            thumbnail=data.get("thumbnail"),
            uploader=data.get("uploader") or data.get("channel") or data.get("creator"),
            webpage_url=data.get("webpage_url"),
            filesize=sum(f.get("filesize") or 0 for f in data.get("formats") or []),
            format_id=(formats[0]["format_id"] if formats else None),
            formats=formats,
        )

    @staticmethod
    def _friendly_error(e: yt_dlp.utils.DownloadError) -> str:
        msg = (getattr(e, "msg", None) or str(e)).strip()
        if "sign in to confirm you" in msg.lower() and "bot" in msg.lower():
            # YouTube is rejecting anonymous requests from this server's IP
            # (common on cloud/datacenter hosts like Render). yt-dlp's own
            # message suggests --cookies-from-browser, a CLI flag that does
            # not apply here — point at this app's actual cookies feature.
            return ("YouTube is asking to sign in to confirm you're not a "
                    "bot (this is common for server IPs). Add a YouTube "
                    "cookies file to the cookies/ folder and pass its name "
                    "as the 'cookies' field — see README Part 3.")
        if "suspend" in msg.lower():
            # We already retried this as a logged-out guest and via the
            # syndication API (see _extract_with_fallback) and it still
            # failed, so the account really is suspended — or, for
            # non-X callers, this is a genuine "Suspended" response.
            return ("X (Twitter) says this post is unavailable because "
                    "the account is suspended. If you believe this is "
                    "wrong, the session in your X cookies file may itself "
                    "be suspended or locked — replace it with a fresh, "
                    "logged-in export and try again.")
        if "no video could be found" in msg.lower():
            # We already retried this as a logged-out guest and via the
            # syndication API (see _extract_with_fallback) and it still
            # found no video, so the post genuinely has no playable
            # video (e.g. it's text-only, photos-only, or a poll/quote
            # of another post) — or the video was deleted.
            return ("No downloadable video was found in this X (Twitter) "
                    "post. This usually means the post only contains "
                    "text, images, or a poll rather than a video, or the "
                    "video was removed. Double-check the link points "
                    "directly at the post containing the video.")
        if "age" in msg.lower() and ("confirm" in msg.lower() or "restrict" in msg.lower() or "sign in" in msg.lower()):
            # Age-gated content that even the tv/tv_embedded player
            # clients (tried first, see _YOUTUBE_EXTRACTOR_ARGS) could
            # not unlock — this genuinely requires a logged-in cookie
            # from an account old enough to view it.
            return ("This video is age-restricted and requires a logged-in "
                    "session to view. Add a cookies file for an account "
                    "old enough to view the content to the cookies/ "
                    "folder and pass its name as the 'cookies' field.")
        exc = getattr(e, "exc_info", None)
        unsafe = ("unable to extract", "does not support", "no player",
                  "requested format", "unable to download video data")
        if isinstance(exc, BaseException) and not any(s in msg.lower() for s in unsafe):
            inner = getattr(exc, "msg", None) or str(exc)
            if inner and "traceback" not in inner.lower():
                return inner
        # Keep only the first line; it is usually the actionable part.
        first_line = msg.splitlines()[0] if msg else "Unknown download error."
        return re.sub(r"\s+", " ", first_line)[:500]

    @staticmethod
    def cleanup(dl_dir: Path) -> None:
        shutil.rmtree(dl_dir, ignore_errors=True)

    @staticmethod
    def make_zip(files: list[Path], zip_path: Path) -> None:
        """Bundle playlist files into a zip archive."""
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.write(f, arcname=f.name)
