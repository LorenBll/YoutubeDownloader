"""YoutubeDownloader local web service."""

from __future__ import annotations

import importlib
import ipaddress
import json
import logging
import os
import socket
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
import urllib.error
import urllib.request
from uuid import uuid4

from flask import Flask, jsonify, request

from models import PostResponse, PostRequest

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "resources" / "configuration.json"
DEFAULT_SERVICE_PORT = 49156
ALLOWED_ROOTS: list[Path] = []
BLACKLISTED_ROOTS: list[Path] = []


# ============================================================================
# YOUTUBE CLIENT INITIALIZATION
# ============================================================================


def _resolve_youtube_client() -> tuple[Any, str]:
    """Load available YouTube client library (pytubefix or pytube)."""
    for module_name in ("pytubefix", "pytube"):
        try:
            module = importlib.import_module(module_name)
            youtube_class = getattr(module, "YouTube", None)
            if youtube_class is not None:
                return youtube_class, module_name
        except ImportError:
            continue

    raise RuntimeError(
        "No supported YouTube client found. Install pytubefix or pytube using: "
        "pip install pytubefix"
    )


# Initialize YouTube client (detect which library is installed)
YouTubeClient, YOUTUBE_CLIENT_NAME = _resolve_youtube_client()


# ============================================================================
# CONFIGURATION AND GLOBAL VARIABLES
# ============================================================================

# Service configuration (loaded from configuration.json at startup)
SERVICE_BIND_ADDRESS = "127.0.0.1"
SERVICE_PORT = None

SERVICEHANDLER_HASH = None

# API request validation constants
REQUIRED_FIELDS = ["video_link", "format", "quality", "folder"]
ALLOWED_FORMATS = {"mp4", "mp3"}
PLAYLIST_NOT_SUPPORTED_ERROR = (
    "Playlist download is not supported. Please provide a single video URL."
)

# Task retention settings (configurable via environment variables)
try:
    TASK_RETENTION_MINUTES = int(os.getenv("TASK_RETENTION_MINUTES", "30"))
except (ValueError, TypeError):
    TASK_RETENTION_MINUTES = 30

try:
    TASK_CLEANUP_INTERVAL_SECONDS = int(
        os.getenv("TASK_CLEANUP_INTERVAL_SECONDS", "60")
    )
except (ValueError, TypeError):
    TASK_CLEANUP_INTERVAL_SECONDS = 60


# ============================================================================
# CONFIGURATION LOADING
# ============================================================================


def _load_configuration() -> dict[str, Any]:
    """Load configuration from resources/configuration.json."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            "Configuration file not found. Ensure resources/configuration.json exists."
        )

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            config = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError("Configuration file contains invalid JSON") from exc
    except Exception as exc:
        raise RuntimeError("Failed to read configuration file") from exc

    return config


def _is_within_directory(child: Path, parent: Path) -> bool:
    """Return True if `child` is inside `parent` (or equal), after resolving."""
    try:
        child_resolved = child.resolve()
        parent_resolved = parent.resolve()
    except Exception:
        return False

    try:
        child_resolved.relative_to(parent_resolved)
        return True
    except Exception:
        return False


def _is_within_any_directory(child: Path, parents: list[Path]) -> bool:
    """Return True if `child` is inside any configured parent directory."""
    for parent in parents:
        if _is_within_directory(child, parent):
            return True
    return False


def _initialize_service_config() -> None:
    """Load and validate service configuration."""
    global SERVICE_PORT
    global ALLOWED_ROOTS, BLACKLISTED_ROOTS
    config = _load_configuration()

    try:
        configured_port = config.get("port", DEFAULT_SERVICE_PORT)
        SERVICE_PORT = int(configured_port)
    except (TypeError, ValueError) as exc:
        raise ValueError("port in configuration.json must be an integer") from exc

    repo_root = Path(__file__).resolve().parent.parent

    allowed_roots: list[Path] = []
    configured_allowed = config.get("allowed_roots")
    if isinstance(configured_allowed, list) and configured_allowed:
        for item in configured_allowed:
            if not isinstance(item, str) or not item.strip():
                continue
            path = Path(item)
            if not path.is_absolute():
                path = (repo_root / path).resolve(strict=False)
            allowed_roots.append(path.resolve())

    blacklisted_roots: list[Path] = []
    configured_blacklisted = config.get("blacklisted_roots")
    if isinstance(configured_blacklisted, list) and configured_blacklisted:
        for item in configured_blacklisted:
            if not isinstance(item, str) or not item.strip():
                continue
            path = Path(item)
            if not path.is_absolute():
                path = (repo_root / path).resolve(strict=False)
            blacklisted_roots.append(path.resolve())

    ALLOWED_ROOTS = allowed_roots
    BLACKLISTED_ROOTS = blacklisted_roots


def _is_path_permitted(path: Path) -> bool:
    """Return True if `path` is permitted by the configured folder policy."""
    try:
        resolved = path.resolve()
    except Exception:
        return False

    if ALLOWED_ROOTS:
        return _is_within_any_directory(resolved, ALLOWED_ROOTS)

    if BLACKLISTED_ROOTS:
        return not _is_within_any_directory(resolved, BLACKLISTED_ROOTS)

    return True


def _collect_local_ip_addresses() -> list[str]:
    """Gather the IPv4 addresses resolved for the local machine."""
    addresses: set[str] = {"127.0.0.1"}
    hostnames = {socket.gethostname(), socket.getfqdn(), "localhost"}

    for hostname in hostnames:
        if not hostname:
            continue

        try:
            _, _, resolved_addresses = socket.gethostbyname_ex(hostname)
        except OSError:
            resolved_addresses = []

        for address in resolved_addresses:
            if _is_ipv4_address(address):
                addresses.add(address)

        try:
            for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
                if family == socket.AF_INET and sockaddr:
                    candidate = sockaddr[0]
                    if _is_ipv4_address(candidate):
                        addresses.add(candidate)
        except OSError:
            continue

    return sorted(addresses, key=_sort_ip_address)


def _is_ipv4_address(value: object) -> bool:
    """Check whether a value is a valid IPv4 address string."""
    if not isinstance(value, str):
        return False

    parts = value.strip().split(".")
    if len(parts) != 4:
        return False

    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False


def _sort_ip_address(value: str) -> tuple[int, int, int, int]:
    """Sort IP addresses numerically while keeping loopback near the front."""
    parts = value.split(".")
    if len(parts) != 4:
        return (255, 255, 255, 255)

    try:
        return tuple(int(part) for part in parts)  # type: ignore[return-value]
    except ValueError:
        return (255, 255, 255, 255)


def _get_primary_ip() -> str:
    """Return the first non-loopback IPv4 address, or loopback as a fallback."""
    for address in _collect_local_ip_addresses():
        if address != "127.0.0.1":
            return address
    return "127.0.0.1"


app = Flask(__name__)


def _get_local_device_addresses() -> set[str]:
    local_addresses: set[str] = set()
    candidate_names = {socket.gethostname(), socket.getfqdn()}

    for candidate_name in candidate_names:
        if not candidate_name:
            continue

        try:
            local_addresses.update(
                address_info[4][0]
                for address_info in socket.getaddrinfo(candidate_name, None)
            )
        except OSError:
            pass

        try:
            local_addresses.update(socket.gethostbyname_ex(candidate_name)[2])
        except OSError:
            pass

    for probe_address in ("8.8.8.8", "1.1.1.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as socket_handle:
                socket_handle.connect((probe_address, 80))
                local_addresses.add(socket_handle.getsockname()[0])
        except OSError:
            pass

    normalized_addresses: set[str] = set()
    for address_value in local_addresses:
        try:
            normalized_addresses.add(ipaddress.ip_address(address_value).compressed)
        except ValueError:
            continue

    normalized_addresses.update({"127.0.0.1", "::1"})
    return normalized_addresses


def _is_local_request() -> bool:
    remote_address = request.remote_addr
    if not isinstance(remote_address, str) or not remote_address.strip():
        return False

    try:
        client_ip = ipaddress.ip_address(remote_address.strip())
    except ValueError:
        return False

    if client_ip.is_loopback:
        return True

    return client_ip.compressed in _get_local_device_addresses()


@app.before_request
def restrict_to_local_device() -> tuple | None:
    if request.path.startswith("/api/") and not _is_local_request():
        return _error_response("Local device access only.", 403)

    return None


@app.after_request
def set_connection_header(response):
    content_type = response.headers.get("Content-Type", "")
    if content_type.startswith("text/html"):
        response.headers["Connection"] = "keep-alive"
    else:
        response.headers["Connection"] = "close"
    return response


def _options_response(allowed_methods: list[str]) -> tuple:
    """Return an OPTIONS response with allowed methods."""
    response = jsonify({})
    response.headers["Allow"] = ", ".join(allowed_methods)
    response.headers["Access-Control-Allow-Methods"] = ", ".join(allowed_methods)
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response, 200


def _head_response() -> tuple:
    """Return a HEAD response with no body."""
    response = jsonify({})
    return response, 200


def _error_response(message: str, status_code: int = 400, **extra) -> tuple:
    """Return a JSON error response using PostResponse model."""
    data = {"error": message, **extra}
    body = json.dumps(data)
    resp = PostResponse(
        status_code=status_code,
        reason="error",
        body=body,
        body_size=len(body),
        headers={"Content-Type": "application/json"},
        json_body=data,
    )
    return jsonify(resp.json_body), resp.status_code


def _success_response(data: dict, status_code: int = 200) -> tuple:
    """Return a JSON success response using PostResponse model."""
    body = json.dumps(data)
    resp = PostResponse(
        status_code=status_code,
        reason="OK",
        body=body,
        body_size=len(body),
        headers={"Content-Type": "application/json"},
        json_body=data,
    )
    return jsonify(resp.json_body), resp.status_code


jobs_lock = Lock()
jobs: dict[str, dict[str, Any]] = {}

cleanup_lock = Lock()
cleanup_thread_started = False


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def _utc_iso() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _resolution_to_int(resolution: str | None) -> int | None:
    """Parse resolution string like "720p" to integer height."""
    if not resolution:
        return None
    value = resolution.strip().lower()
    if not value.endswith("p"):
        return None
    number = value[:-1]
    if not number.isdigit():
        return None
    return int(number)


def _normalize_quality(quality: str, requested_format: str) -> str:
    """Normalize quality string (add 'p' for mp4, 'kbps' for mp3)."""
    value = quality.strip().lower()
    if requested_format == "mp4":
        if value.endswith("p"):
            return value
        if value.isdigit():
            return f"{value}p"
    if requested_format == "mp3":
        if value.endswith("kbps"):
            return value
        if value.isdigit():
            return f"{value}kbps"
    return quality.strip()


def _build_safe_filename(file_name: str) -> str:
    """Sanitize filename for safe filesystem operations."""
    cleaned = file_name.strip()
    invalid_chars = r'<>:"/\|?*&'
    for char in invalid_chars:
        cleaned = cleaned.replace(char, "_")
    cleaned = "".join(char for char in cleaned if ord(char) >= 32 or char in "\t\n\r")
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        raise ValueError("name must contain at least one non-space character")
    return Path(cleaned).stem or "download"


def _normalize_folder_path(folder: object) -> Path:
    """Normalize and validate the requested download folder path."""
    folder_value = _require_string(folder, "folder")
    try:
        save_dir = Path(folder_value).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(
            f"Invalid folder path '{folder_value}'. Path contains invalid characters or is malformed."
        ) from exc

    if not _is_path_permitted(save_dir):
        raise ValueError("Requested folder is not permitted by server policy.")

    return save_dir


def _resolve_unique_path(directory: Path, stem: str, suffix: str) -> Path:
    """Generate unique filepath by appending counter if file exists."""
    candidate = directory / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    counter = 1
    while True:
        candidate = directory / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _is_valid_youtube_url(video_link: str) -> bool:
    """Validate YouTube URL format."""
    link = video_link.strip().lower()
    parsed = urlparse(link)
    hostname = parsed.hostname or ""
    valid_hosts = {
        "youtube.com",
        "www.youtube.com",
        "youtu.be",
        "www.youtu.be",
        "m.youtube.com",
    }
    if not any(hostname.endswith(host.replace("www.", "")) for host in valid_hosts):
        return False
    return bool(parsed.path.strip("/") or parsed.query)


def _is_playlist_url(video_link: str) -> bool:
    """Detect if URL is a playlist (unsupported)."""
    parsed = urlparse(video_link.strip())
    query_params = parse_qs(parsed.query)
    if "list" in query_params:
        return True
    path = parsed.path.lower()
    return path.startswith("/playlist")


# ============================================================================
# BACKGROUND TASK CLEANUP
# ============================================================================


def _cleanup_finished_jobs_forever() -> None:
    """Remove old completed/failed tasks in background loop."""
    retention_seconds = max(60, TASK_RETENTION_MINUTES * 60)
    interval_seconds = max(10, TASK_CLEANUP_INTERVAL_SECONDS)
    while True:
        try:
            time.sleep(interval_seconds)
            now = time.time()
            removable_task_ids: list[str] = []
            with jobs_lock:
                for task_id, task in jobs.items():
                    if task.get("status") not in {"completed", "failed"}:
                        continue
                    finished_at = task.get("finished_at_unix")
                    if (
                        isinstance(finished_at, (int, float))
                        and (now - finished_at) >= retention_seconds
                    ):
                        removable_task_ids.append(task_id)
                for task_id in removable_task_ids:
                    jobs.pop(task_id, None)

        except Exception as exc:
            logger.error(f"Cleanup Thread Error: {exc}")


def _ensure_cleanup_thread_started() -> None:
    """Start cleanup thread exactly once (thread-safe)."""
    global cleanup_thread_started
    with cleanup_lock:
        if cleanup_thread_started:
            return
        cleanup_thread = Thread(
            target=_cleanup_finished_jobs_forever,
            name="youtube-task-cleanup-worker",
            daemon=True,
        )
        cleanup_thread.start()
        cleanup_thread_started = True


# ============================================================================
# YOUTUBE STREAM SELECTION AND DOWNLOADING
# ============================================================================


def _select_progressive_mp4_stream(yt: Any, normalized_quality: str) -> tuple[int, Any]:
    """Select best progressive MP4 stream (up to 720p)."""
    requested_height = _resolution_to_int(normalized_quality)
    if requested_height is None:
        raise ValueError(
            "For mp4, quality must be a value like '720p' (or numeric like '720')."
        )

    try:
        candidate_streams = list(
            yt.streams.filter(progressive=True, file_extension="mp4")
            .order_by("resolution")
            .desc()
        )
    except HTTPError as exc:
        raise ValueError(
            "YouTube request failed while fetching available mp4 streams. "
            "Try again later or test another video. "
            f"Upstream error: HTTP {exc.code}."
        ) from exc

    # Build list of available resolutions with their stream objects
    available: list[tuple[int, Any]] = []
    for candidate in candidate_streams:
        height = _resolution_to_int(getattr(candidate, "resolution", None))
        if height is not None:
            available.append((height, candidate))

    if not available:
        raise ValueError("No mp4 progressive streams are available for this video.")

    available.sort(key=lambda item: item[0], reverse=True)
    return next(((h, s) for h, s in available if h <= requested_height), available[-1])


def _select_adaptive_mp4_stream(yt: Any, normalized_quality: str) -> tuple[int, Any]:
    """Select best adaptive MP4 video stream (>720p, no audio)."""

    # Parse requested quality to integer height
    requested_height = _resolution_to_int(normalized_quality)
    if requested_height is None:
        raise ValueError(
            "For mp4, quality must be a value like '1080p' (or numeric like '1080')."
        )

    try:
        candidate_streams = list(
            yt.streams.filter(adaptive=True, only_video=True, file_extension="mp4")
            .order_by("resolution")
            .desc()
        )
    except HTTPError as exc:
        raise ValueError(
            "YouTube request failed while fetching available adaptive mp4 streams. "
            "Try again later or test another video. "
            f"Upstream error: HTTP {exc.code}."
        ) from exc

    available: list[tuple[int, Any]] = []
    for candidate in candidate_streams:
        height = _resolution_to_int(getattr(candidate, "resolution", None))
        if height is not None:
            available.append((height, candidate))

    if not available:
        raise ValueError("No adaptive mp4 video streams are available for this video.")

    available.sort(key=lambda item: item[0], reverse=True)
    return next(((h, s) for h, s in available if h <= requested_height), available[-1])


def _select_best_audio_stream_for_mp4(yt: Any) -> Any:
    """Select highest quality audio stream for MP4 merging."""
    try:
        stream = (
            yt.streams.filter(only_audio=True, mime_type="audio/mp4")
            .order_by("abr")
            .desc()
            .first()
        )
        if stream is None:
            stream = yt.streams.filter(only_audio=True).order_by("abr").desc().first()
    except HTTPError as exc:
        raise ValueError(
            "YouTube request failed while fetching available audio streams. "
            "Try again later or test another video. "
            f"Upstream error: HTTP {exc.code}."
        ) from exc

    if stream is None:
        raise ValueError("No audio stream found for this video.")
    return stream


def _resolve_ffmpeg_path() -> str:
    """Locate ffmpeg executable (env FFMPEG_PATH or system PATH)."""
    env_path = os.getenv("FFMPEG_PATH")
    if env_path:
        if Path(env_path).exists():
            return env_path
        raise ValueError(
            f"FFMPEG_PATH was set to '{env_path}' but the file does not exist. "
            "Update FFMPEG_PATH or install ffmpeg."
        )

    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path
    raise ValueError(
        "ffmpeg is required to merge high-quality mp4 streams, but it was not found. "
        "Install ffmpeg or set FFMPEG_PATH to the ffmpeg executable."
    )


def _merge_av_with_ffmpeg(
    ffmpeg_path: str, video_path: Path, audio_path: Path, output_path: Path
) -> None:
    """Merge video and audio streams using FFmpeg."""
    # Build ffmpeg command with appropriate parameters
    command = [
        ffmpeg_path,
        "-y",  # Overwrite output without asking
        "-i",
        str(video_path),  # Input video
        "-i",
        str(audio_path),  # Input audio
        "-c:v",
        "copy",  # Copy video codec (no re-encoding)
        "-c:a",
        "aac",  # Encode audio as AAC
        "-movflags",
        "+faststart",  # Web-optimized MP4
        str(output_path),  # Output file
    ]

    # Execute ffmpeg and handle potential errors
    try:
        completed = subprocess.run(
            command,
            check=True,  # Raise exception on non-zero exit
            capture_output=True,  # Capture stdout/stderr
            text=True,  # Return strings, not bytes
        )
    except FileNotFoundError as exc:
        raise ValueError(
            "ffmpeg executable could not be found. "
            "Install ffmpeg or set FFMPEG_PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        # FFmpeg failed - extract error details from stderr
        stderr = exc.stderr.strip() if exc.stderr else ""
        message = "ffmpeg failed while merging audio and video streams."
        if stderr:
            message += f" Details: {stderr}"
        raise ValueError(message) from exc


def _select_audio_stream(yt: Any, normalized_quality: str) -> Any:
    """Select audio stream matching requested bitrate."""
    try:
        # Search for audio streams with the exact requested bitrate
        stream = (
            yt.streams.filter(only_audio=True, abr=normalized_quality)
            .order_by("abr")
            .desc()
            .first()
        )
    except HTTPError as exc:
        raise ValueError(
            "YouTube request failed while fetching available audio streams. "
            "Try again later or test another video. "
            f"Upstream error: HTTP {exc.code}."
        ) from exc

    # Verify we found a matching stream
    if stream is None:
        raise ValueError(f"No audio stream found for quality '{normalized_quality}'.")

    return stream


# ============================================================================
# DOWNLOAD TASK PROCESSING
# ============================================================================


def _download_with_pytube(payload: dict[str, Any]) -> dict[str, Any]:
    """Download video or audio and return metadata."""
    # Extract and normalize request parameters
    video_link = payload["video_link"].strip()
    requested_format = payload["format"].strip().lower()
    quality = payload["quality"].strip()
    requested_name = str(payload.get("name", payload.get("file_name", ""))).strip()
    folder = payload["folder"].strip()

    # Validate format
    if requested_format not in ALLOWED_FORMATS:
        raise ValueError("format must be either 'mp4' or 'mp3'")

    # Normalize quality string for stream lookup
    normalized_quality = _normalize_quality(quality, requested_format)

    # Validate and create save directory if it doesn't exist
    try:
        save_dir = _normalize_folder_path(folder)
        save_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as exc:
        raise ValueError(
            f"Cannot create or access download folder '{folder}'. "
            f"Check permissions and disk space. Details: {exc}"
        ) from exc
    except (ValueError, TypeError) as exc:
        raise ValueError(str(exc)) from exc

    # Initialize YouTube client for this video
    try:
        yt = YouTubeClient(video_link)
    except (HTTPError, Exception) as exc:
        # Handle HTTP errors separately for better diagnostics
        if isinstance(exc, HTTPError):
            raise ValueError(
                "YouTube request failed while preparing the download. "
                "This may be temporary or related to pytube parsing for this video. "
                f"Upstream error: HTTP {exc.code}."
            ) from exc
        # Generic error (invalid URL, network issues, etc.)
        raise ValueError(
            f"Failed to load YouTube video. The URL may be invalid or the video unavailable. "
            f"Details: {exc}"
        ) from exc

    # Fetch video title (will be used as filename if user didn't provide one)
    try:
        video_title = yt.title
    except HTTPError as exc:
        raise ValueError(
            "YouTube request failed while reading video metadata. "
            "Try again later or test a different video URL. "
            f"Upstream error: HTTP {exc.code}."
        ) from exc

    # Determine final filename (user-provided name takes priority)
    save_name = requested_name if requested_name else video_title
    safe_stem = _build_safe_filename(save_name)  # Sanitize for filesystem

    # ========================================================================
    # MP4 VIDEO DOWNLOAD LOGIC
    # ========================================================================
    if requested_format == "mp4":
        # Parse and validate quality for video
        requested_height = _resolution_to_int(normalized_quality)
        if requested_height is None:
            raise ValueError(
                "For mp4, quality must be a value like '720p' (or numeric like '720')."
            )

        # Decide stream type based on quality:
        # - Progressive (video+audio combined): Up to 720p
        # - Adaptive (separate video/audio): Above 720p or if progressive unavailable
        use_adaptive = requested_height > 720
        if not use_adaptive:
            # Try progressive first for ≤720p
            try:
                selected_height, stream = _select_progressive_mp4_stream(
                    yt, normalized_quality
                )
            except ValueError:
                # Progressive not available, fall back to adaptive
                use_adaptive = True

        # ------------------------------------------------------------------------
        # PROGRESSIVE MP4 DOWNLOAD (≤720p, simpler single-file download)
        # ------------------------------------------------------------------------
        if not use_adaptive:
            try:
                # Generate unique filename and download stream
                output_path = _resolve_unique_path(save_dir, safe_stem, ".mp4")
                output_path = Path(
                    stream.download(
                        output_path=str(save_dir), filename=output_path.name
                    )
                )
            except HTTPError as exc:
                raise ValueError(
                    "YouTube rejected the mp4 stream download request. "
                    "Try a different video or quality (for example 720p). "
                    f"Upstream error: HTTP {exc.code}."
                ) from exc
            except (OSError, PermissionError) as exc:
                raise ValueError(
                    f"Cannot write mp4 file to '{save_dir}'. Check disk space, permissions, or folder path. "
                    f"Details: {exc}"
                ) from exc
            except Exception as exc:
                raise ValueError(
                    f"Unexpected error downloading mp4 stream: {exc}"
                ) from exc

            # Return metadata about successful progressive download
            return {
                "name": output_path.stem,
                "format": "mp4",
                "requested_quality": normalized_quality,
                "actual_quality": f"{selected_height}p",
                "save_path": str(output_path),
            }

        # ------------------------------------------------------------------------
        # ADAPTIVE MP4 DOWNLOAD (>720p, requires ffmpeg merge)
        # ------------------------------------------------------------------------

        # Locate ffmpeg executable (required for merging)
        ffmpeg_path = _resolve_ffmpeg_path()

        # Select video and audio streams
        selected_height, video_stream = _select_adaptive_mp4_stream(
            yt, normalized_quality
        )
        audio_stream = _select_best_audio_stream_for_mp4(yt)

        # Download video and audio to temporary directory, then merge
        try:
            with tempfile.TemporaryDirectory(prefix="yt-downloader-") as temp_dir:
                temp_dir_path = Path(temp_dir)

                # Download video stream
                video_path = Path(
                    video_stream.download(
                        output_path=str(temp_dir_path), filename="video.mp4"
                    )
                )

                # Download audio stream
                audio_path = Path(
                    audio_stream.download(
                        output_path=str(temp_dir_path), filename="audio.m4a"
                    )
                )

                # Merge video and audio using ffmpeg
                output_path = _resolve_unique_path(save_dir, safe_stem, ".mp4")
                _merge_av_with_ffmpeg(ffmpeg_path, video_path, audio_path, output_path)

                # Temporary directory is automatically cleaned up when exiting context

        except HTTPError as exc:
            raise ValueError(
                "YouTube rejected the high-quality mp4 stream download request. "
                "Try a different video or quality. "
                f"Upstream error: HTTP {exc.code}."
            ) from exc
        except (OSError, PermissionError) as exc:
            raise ValueError(
                f"Cannot write mp4 file to '{save_dir}'. Check disk space, permissions, or folder path. "
                f"Details: {exc}"
            ) from exc
        except Exception as exc:
            raise ValueError(
                f"Unexpected error downloading high-quality mp4 stream: {exc}"
            ) from exc

        # Return metadata about successful adaptive download
        return {
            "name": output_path.stem,
            "format": "mp4",
            "requested_quality": normalized_quality,
            "actual_quality": f"{selected_height}p",
            "save_path": str(output_path),
            "merge": "ffmpeg",  # Indicate that ffmpeg was used for merging
        }

    # ========================================================================
    # MP3 AUDIO DOWNLOAD LOGIC
    # ========================================================================

    # Select audio stream matching requested bitrate
    stream = _select_audio_stream(yt, normalized_quality)

    # Download audio stream
    try:
        target_path = _resolve_unique_path(save_dir, safe_stem, ".mp3")
        downloaded_path = Path(
            stream.download(output_path=str(save_dir), filename=target_path.name)
        )
    except HTTPError as exc:
        raise ValueError(
            "YouTube rejected the audio stream download request. "
            "Try a different video or quality. "
            f"Upstream error: HTTP {exc.code}."
        ) from exc
    except (OSError, PermissionError) as exc:
        raise ValueError(
            f"Cannot write mp3 file to '{save_dir}'. Check disk space, permissions, or folder path. "
            f"Details: {exc}"
        ) from exc
    except Exception as exc:
        raise ValueError(f"Unexpected error downloading audio stream: {exc}") from exc

    # Ensure file is in the correct location (sometimes pytube may use a different path)
    if downloaded_path != target_path and downloaded_path.exists():
        try:
            downloaded_path.replace(target_path)
        except (OSError, PermissionError) as exc:
            raise ValueError(
                f"Cannot move mp3 file to target location. Check permissions and disk space. "
                f"Details: {exc}"
            ) from exc

    # Return metadata about successful audio download
    return {
        "name": target_path.stem,
        "format": "mp3",
        "requested_quality": normalized_quality,
        "actual_quality": str(
            getattr(stream, "abr", normalized_quality) or normalized_quality
        ),
        "save_path": str(target_path),
    }


def _validate_payload(payload: Any) -> tuple[dict[str, Any] | None, Any | None, int]:
    """Validate download request payload (single or batch)."""
    # Basic type check
    if not isinstance(payload, dict):
        return None, {"error": "Request body must be valid JSON."}, 400

    # Check if this is a batch request (with 'videos' array)
    videos_payload = payload.get("videos")
    if videos_payload is not None:
        # Validate batch request structure
        if not isinstance(videos_payload, list) or not videos_payload:
            return None, {"error": "videos must be a non-empty array."}, 400

        # Validate each video in the batch
        video_errors: list[dict[str, Any]] = []
        validated_videos: list[dict[str, Any]] = []

        for index, video_payload in enumerate(videos_payload):
            # Each item must be a dictionary
            if not isinstance(video_payload, dict):
                video_errors.append(
                    {
                        "index": index,
                        "error": "Each video item must be a JSON object.",
                    }
                )
                continue

            # Check for required fields
            missing_fields = [
                field
                for field in REQUIRED_FIELDS
                if field not in video_payload or str(video_payload[field]).strip() == ""
            ]
            if missing_fields:
                video_errors.append(
                    {
                        "index": index,
                        "error": "Missing required fields.",
                        "missing_fields": missing_fields,
                    }
                )
                continue

            # Validate format
            requested_format = str(video_payload.get("format", "")).strip().lower()
            if requested_format not in ALLOWED_FORMATS:
                video_errors.append(
                    {
                        "index": index,
                        "error": "format must be either 'mp4' or 'mp3'",
                    }
                )
                continue

            # Validate video URL
            video_link = str(video_payload.get("video_link", "")).strip()
            if not _is_valid_youtube_url(video_link):
                video_errors.append(
                    {
                        "index": index,
                        "error": "video_link must be a valid YouTube URL (youtube.com or youtu.be).",
                    }
                )
                continue

            # Reject playlists
            if _is_playlist_url(video_link):
                video_errors.append(
                    {
                        "index": index,
                        "error": PLAYLIST_NOT_SUPPORTED_ERROR,
                    }
                )
                continue

            # Validate target folder against server policy
            try:
                _normalize_folder_path(video_payload.get("folder"))
            except ValueError as exc:
                logger.warning(
                    "Invalid folder path in batch payload at index %s",
                    index,
                    exc_info=True,
                )
                video_errors.append(
                    {
                        "index": index,
                        "error": "Invalid folder path.",
                    }
                )
                continue

            # Video passed all validation checks
            validated_videos.append(video_payload)

        # If any videos failed validation, return all errors
        if video_errors:
            return (
                None,
                {
                    "error": "Invalid videos payload.",
                    "video_errors": video_errors,
                },
                400,
            )

        # All videos validated successfully
        return {"videos": validated_videos}, None, 200

    # Single video request validation

    # Check for required fields
    missing_fields = [
        field
        for field in REQUIRED_FIELDS
        if field not in payload or str(payload[field]).strip() == ""
    ]

    if missing_fields:
        return (
            None,
            {
                "error": "Missing required fields.",
                "missing_fields": missing_fields,
            },
            400,
        )

    # Validate format
    requested_format = str(payload.get("format", "")).strip().lower()
    if requested_format not in ALLOWED_FORMATS:
        return None, {"error": "format must be either 'mp4' or 'mp3'"}, 400

    # Validate video URL
    video_link = str(payload.get("video_link", "")).strip()
    if not _is_valid_youtube_url(video_link):
        return (
            None,
            {
                "error": "video_link must be a valid YouTube URL (youtube.com or youtu.be)."
            },
            400,
        )

    # Reject playlists
    if _is_playlist_url(video_link):
        return None, {"error": PLAYLIST_NOT_SUPPORTED_ERROR}, 400

    # Validate target folder against server policy
    try:
        _normalize_folder_path(payload.get("folder"))
    except ValueError as exc:
        logger.warning("Invalid folder path in request payload", exc_info=True)
        return None, {"error": "Invalid folder path."}, 400

    # Payload is valid
    return payload, None, 200


def _download_worker(task_id: str, payload: dict[str, Any]) -> None:
    """Run a download task in a background thread.

    Args:
        task_id: Unique task identifier.
        payload: Validated download request.
    """
    # Mark task as in progress
    with jobs_lock:
        jobs[task_id]["status"] = "in_progress"
        jobs[task_id]["updated_at"] = _utc_iso()

    # Check if this is a batch request (multiple videos)
    videos = payload.get("videos")
    if isinstance(videos, list):
        # Process batch: download each video independently
        item_results: list[dict[str, Any]] = []
        completed_count = 0
        failed_count = 0

        for index, video_payload in enumerate(videos):
            try:
                # Attempt to download this video
                result = _download_with_pytube(video_payload)
                item_results.append(
                    {
                        "index": index,
                        "status": "completed",
                        "result": result,
                    }
                )
                completed_count += 1
            except Exception as exc:
                # Video failed, but continue with remaining videos
                item_results.append(
                    {
                        "index": index,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                failed_count += 1

        # Update task with batch results (always mark as completed, even if some videos failed)
        with jobs_lock:
            jobs[task_id]["status"] = "completed"
            jobs[task_id]["result"] = {
                "items": item_results,  # Individual results for each video
                "summary": {
                    "total": len(videos),
                    "completed": completed_count,
                    "failed": failed_count,
                },
            }
            jobs[task_id]["updated_at"] = _utc_iso()
            jobs[task_id]["finished_at_unix"] = time.time()  # For cleanup tracking

        return  # Batch processing complete

    # Single video request processing
    try:
        # Attempt to download
        result = _download_with_pytube(payload)

        # Update task with success result
        with jobs_lock:
            jobs[task_id]["status"] = "completed"
            jobs[task_id]["result"] = result
            jobs[task_id]["updated_at"] = _utc_iso()
            jobs[task_id]["finished_at_unix"] = time.time()

    except Exception as exc:
        # Download failed - record error
        with jobs_lock:
            jobs[task_id]["status"] = "failed"
            jobs[task_id]["error"] = str(exc)
            jobs[task_id]["updated_at"] = _utc_iso()
            jobs[task_id]["finished_at_unix"] = time.time()


# ============================================================================
# API ENDPOINTS
# ============================================================================


@app.route("/api/download", methods=["POST", "HEAD", "OPTIONS"])
def download() -> tuple[Any, int]:
    """Queue a download task. Returns task_id (202 Accepted)."""
    if request.method == "OPTIONS":
        return _options_response(["POST", "HEAD", "OPTIONS"])
    if request.method == "HEAD":
        return _head_response()

    # Ensure background cleanup thread is running
    _ensure_cleanup_thread_started()

    # Parse and validate request body
    payload = request.get_json(silent=True)
    validated_payload, error_body, status_code = _validate_payload(payload)
    if error_body is not None:
        msg = error_body.get("error", "Invalid request")
        extra = {k: v for k, v in error_body.items() if k != "error"}
        return _error_response(msg, status_code, **extra)

    # Generate unique task ID and create task record
    task_id = str(uuid4())
    now = _utc_iso()

    with jobs_lock:
        jobs[task_id] = {
            "task_id": task_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
        }

    # Start background worker thread for this download
    try:
        download_thread = Thread(
            target=_download_worker,
            args=(task_id, validated_payload),
            name=f"youtube-download-worker-{task_id}",
            daemon=False,
        )
        download_thread.start()
    except Exception as exc:
        with jobs_lock:
            jobs[task_id]["status"] = "failed"
            jobs[task_id]["error"] = f"Failed to start download worker: {exc}"
            jobs[task_id]["updated_at"] = _utc_iso()
            jobs[task_id]["finished_at_unix"] = time.time()
        return _error_response(
            "Could not start download worker. The server may be under heavy load.",
            500,
            task_id=task_id,
        )

    response_body: dict[str, Any] = {
        "task_id": task_id,
        "status": "queued",
    }
    if isinstance(validated_payload.get("videos"), list):
        response_body["video_count"] = len(validated_payload["videos"])

    return _success_response(response_body, 202)


@app.route("/api/task/<task_id>", methods=["GET", "HEAD", "OPTIONS"])
def task_status(task_id: str) -> tuple[Any, int]:
    """Get download task status and result."""
    if request.method == "OPTIONS":
        return _options_response(["GET", "HEAD", "OPTIONS"])
    if request.method == "HEAD":
        return _head_response()

    # Ensure cleanup thread is running
    _ensure_cleanup_thread_started()

    # Retrieve task from in-memory store
    with jobs_lock:
        task = jobs.get(task_id)

    if task is None:
        return _error_response("Task not found.", 404)

    response_body: dict[str, Any] = {
        "task_id": task["task_id"],
        "status": task["status"],
    }

    if task["status"] == "completed":
        response_body["result"] = task.get("result", {})

    if task["status"] == "failed":
        response_body["error"] = task.get("error", "Unknown error")

    return _success_response(response_body)


@app.route("/api/health", methods=["GET", "HEAD", "OPTIONS"])
def health() -> tuple[Any, int]:
    """Health check with service status and task statistics."""
    if request.method == "OPTIONS":
        return _options_response(["GET", "HEAD", "OPTIONS"])
    if request.method == "HEAD":
        return _head_response()

    # Ensure cleanup thread is running
    _ensure_cleanup_thread_started()

    # Get snapshot of all tasks (thread-safe)
    with jobs_lock:
        snapshot = list(jobs.values())

    # Calculate task counts by status
    counts = {
        "queued": 0,
        "in_progress": 0,
        "completed": 0,
        "failed": 0,
        "total": len(snapshot),
    }
    for task in snapshot:
        status = task.get("status")
        if status in counts:
            counts[status] += 1

    return _success_response(
        {
            "status": "ok",
            "service": "YoutubeDownloader",
            "bind_address": SERVICE_BIND_ADDRESS,
            "port": SERVICE_PORT,
            "hostname": socket.gethostname(),
            "pid": os.getpid(),
            "task_counts": counts,
            "task_retention_minutes": TASK_RETENTION_MINUTES,
            "task_cleanup_interval_seconds": TASK_CLEANUP_INTERVAL_SECONDS,
            "youtube_client": YOUTUBE_CLIENT_NAME,
        }
    )


# ============================================================================
# APPLICATION ENTRY POINT
# ============================================================================


def _register_endpoints_with_servicehandler() -> None:
    """Register this service's API endpoints with ServiceHandler."""
    global SERVICEHANDLER_HASH
    if not SERVICEHANDLER_HASH:
        return

    config = _load_configuration()
    sh_port = config.get("servicehandlerPort", 49155)

    endpoints = [
        {
            "verb": "POST",
            "path": "/api/download",
            "path_variables": [],
            "body_schema": {
                "type": "object",
                "properties": {
                    "video_link": {"type": "string", "description": "Valid YouTube URL."},
                    "format": {"type": "string", "description": "Download format: mp4 or mp3."},
                    "quality": {"type": "string", "description": "Requested quality (e.g. 720p, 128kbps)."},
                    "folder": {"type": "string", "description": "Destination folder path."},
                    "videos": {"type": "array", "description": "Array of video objects for batch download."}
                },
                "required": ["video_link", "format", "quality", "folder"]
            },
            "description": "Queue a single or batch YouTube download task.",
        },
        {
            "verb": "GET",
            "path": "/api/task/<task_id>",
            "path_variables": ["task_id"],
            "body_schema": {},
            "description": "Return the current status and result of a download task.",
        },
        {
            "verb": "GET",
            "path": "/api/health",
            "path_variables": [],
            "body_schema": {},
            "description": "Service health check with task queue statistics.",
        },
    ]

    for ep in endpoints:
        try:
            payload = json.dumps({
                "hash": SERVICEHANDLER_HASH,
                **ep
            }).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{sh_port}/api/register/endpoint",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 201:
                    logger.info(f"Registered endpoint: {ep['verb']} {ep['path']}")
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                logger.debug(f"Endpoint already registered: {ep['verb']} {ep['path']}")
            else:
                logger.warning(f"Failed to register endpoint {ep['verb']} {ep['path']} (HTTP {exc.code})")
        except Exception as exc:
            logger.warning(f"Failed to register endpoint {ep['verb']} {ep['path']}: {exc}")


def _servicehandler_keepalive_forever() -> None:
    global SERVICEHANDLER_HASH
    config = _load_configuration()
    ph_port = config.get("servicehandlerPort", 49155)
    service_name = "YoutubeDownloader"

    while True:
        time.sleep(15)
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{ph_port}/api/question/service",
                data=json.dumps({"name": service_name}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    continue
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                logger.warning(f"ServiceHandler question failed (HTTP {exc.code})")
                continue
        except Exception as exc:
            logger.warning(f"ServiceHandler question failed: {exc}")
            continue

        try:
            payload = json.dumps({
                "name": service_name,
                "port": SERVICE_PORT,
                "starting_script": str(Path(__file__).resolve().parent.parent / "scripts" / ("run.bat" if os.name == "nt" else "run.sh")),
                "bind_address": SERVICE_BIND_ADDRESS,
                "hostname": socket.gethostname(),
            }).encode("utf-8")

            req = urllib.request.Request(
                f"http://127.0.0.1:{ph_port}/api/register/service",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 201:
                    data = json.loads(resp.read().decode("utf-8"))
                    SERVICEHANDLER_HASH = data.get("hash")
                    logger.info(f"Registered with ServiceHandler, hash={SERVICEHANDLER_HASH[:16]}...")
                    if SERVICEHANDLER_HASH:
                        _register_endpoints_with_servicehandler()
        except Exception as exc:
            logger.warning(f"ServiceHandler registration attempt failed: {exc}")


if __name__ == "__main__":
    try:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        _initialize_service_config()
    except Exception as exc:
        logger.error(f"Failed to load configuration: {exc}")
        exit(1)

    _ensure_cleanup_thread_started()

    config = _load_configuration()
    if config.get("servicehandlerEnabled", True):
        servicehandler_thread = Thread(
            target=_servicehandler_keepalive_forever,
            name="servicehandler-keepalive",
            daemon=True,
        )
        servicehandler_thread.start()

    try:
        logger.info("=" * 50)
        logger.info("  YoutubeDownloader API Server")
        logger.info("=" * 50)
        logger.info(f"Binding to: http://{SERVICE_BIND_ADDRESS}:{SERVICE_PORT}")
        logger.info("Threading: enabled")
        logger.info(f"YouTube Client: {YOUTUBE_CLIENT_NAME}")
        logger.info(f"Task Retention: {TASK_RETENTION_MINUTES} minutes")
        logger.info(f"Cleanup Interval: {TASK_CLEANUP_INTERVAL_SECONDS} seconds")
        logger.info("Server starting...")
        app.run(
            host=SERVICE_BIND_ADDRESS,
            port=SERVICE_PORT,
            debug=False,
            threaded=True,
        )

    except KeyboardInterrupt:
        logger.info("=" * 50)
        logger.info("  Server Stopped")
        logger.info("=" * 50)

    except OSError as exc:
        if "Address already in use" in str(exc):
            logger.error(
                f"Port {SERVICE_PORT} is already in use. "
                f"Either stop the other process, or change the port in resources/configuration.json"
            )
        elif "Permission denied" in str(exc):
            logger.error(
                f"Permission denied to bind to port {SERVICE_PORT}. "
                f"On Linux/macOS, use a port >= 1024 or run with sudo."
            )
        else:
            logger.error(f"Network binding failed: {exc}")

    except Exception as exc:
        logger.error(f"Server startup failed: {exc}")
