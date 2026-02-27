"""YouTube Downloader API Service

A Flask-based REST API service for downloading YouTube videos and audio.
This service provides:
- Multiple authentication modes (private, unprivate, public)
- Asynchronous download task processing with progress tracking
- Support for MP4 (video) and MP3 (audio) formats
- Batch download support
- High-quality stream selection (up to 4K)
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from flask import Flask, jsonify, request


# ============================================================================
# YOUTUBE CLIENT INITIALIZATION
# ============================================================================


def _resolve_youtube_client() -> tuple[Any, str]:
    """Dynamically detect and load an available YouTube client library.

    Tries to import YouTube client libraries in order of preference:
    1) pytubefix - More actively maintained, better compatibility with recent YouTube changes
    2) pytube - Original library, may have compatibility issues with newer videos

    Returns:
        tuple: (YouTube class, module name string)

    Raises:
        RuntimeError: If neither pytubefix nor pytube is installed
    """
    # Try each supported YouTube client library in order
    for module_name in ("pytubefix", "pytube"):
        try:
            module = importlib.import_module(module_name)
            youtube_class = getattr(module, "YouTube", None)
            if youtube_class is not None:
                return youtube_class, module_name
        except ImportError:
            continue  # Try next library

    # No supported library found - this is a fatal error
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
SERVICE_MODE = None  # One of: 'private', 'unprivate', 'public'
SERVICE_HOST = None  # IP address to bind to (e.g., '127.0.0.1' or '0.0.0.0')
SERVICE_PORT = None  # Port number to listen on (e.g., 49153)
API_KEYLIST = []     # List of valid API keys (used only in 'unprivate' mode)

# API request validation constants
REQUIRED_FIELDS = ["video_link", "format", "quality", "folder"]  # Mandatory fields in download requests
ALLOWED_FORMATS = {"mp4", "mp3"}  # Supported output formats
PLAYLIST_NOT_SUPPORTED_ERROR = "Playlist download is not supported. Please provide a single video URL."

# Task retention settings (configurable via environment variables)
# These control how long completed tasks are kept in memory before automatic cleanup
try:
    TASK_RETENTION_MINUTES = int(os.getenv("TASK_RETENTION_MINUTES", "30"))
except (ValueError, TypeError):
    TASK_RETENTION_MINUTES = 30  # Default: keep completed tasks for 30 minutes

try:
    TASK_CLEANUP_INTERVAL_SECONDS = int(os.getenv("TASK_CLEANUP_INTERVAL_SECONDS", "60"))
except (ValueError, TypeError):
    TASK_CLEANUP_INTERVAL_SECONDS = 60  # Default: check for old tasks every 60 seconds



# ============================================================================
# CONFIGURATION LOADING
# ============================================================================

def _load_configuration() -> dict[str, Any]:
    """Load and parse service configuration from resources/configuration.json.
    
    The configuration file contains settings for different service modes
    (private, unprivate, public) including host/port bindings and API keys.
    
    Returns:
        dict: Parsed configuration data
        
    Raises:
        FileNotFoundError: If configuration.json doesn't exist
        ValueError: If configuration.json contains invalid JSON
        RuntimeError: If configuration file cannot be read
    """
    # Resolve configuration file path relative to this script's location
    # Expected structure: src/main.py -> resources/configuration.json
    script_dir = Path(__file__).parent
    config_path = script_dir.parent / "resources" / "configuration.json"
    
    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found at {config_path}. "
            "Ensure resources/configuration.json exists."
        )
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Configuration file at {config_path} contains invalid JSON: {exc}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"Failed to read configuration file at {config_path}: {exc}"
        ) from exc
    
    return config


def _initialize_service_config() -> None:
    """Initialize global service configuration variables from configuration.json.
    
    This function:
    1. Loads the configuration file
    2. Determines which mode to use (private/unprivate/public)
    3. Sets global variables for host, port, and API keys
    4. Validates that the configuration is complete and correct
    
    Raises:
        ValueError: If configuration is invalid or incomplete
    """
    global SERVICE_MODE, SERVICE_HOST, SERVICE_PORT, API_KEYLIST
    
    # Load the raw configuration dictionary
    config = _load_configuration()
    
    # Determine which service mode to use (defaults to 'private' for security)
    SERVICE_MODE = config.get("defaultMode", "private").lower()
    
    if SERVICE_MODE not in {"private", "unprivate", "public"}:
        raise ValueError(
            f"Invalid defaultMode '{SERVICE_MODE}' in configuration.json. "
            "Must be one of: private, unprivate, public"
        )
    
    # Load mode-specific configuration
    mode_config = config.get(SERVICE_MODE)
    if mode_config is None:
        raise ValueError(
            f"Configuration for mode '{SERVICE_MODE}' not found in configuration.json"
        )
    
    SERVICE_HOST = mode_config.get("ip", "127.0.0.1")
    SERVICE_PORT = mode_config.get("port", 49153)
    
    # For unprivate mode, load and validate the API keylist
    # (only unprivate mode requires API key authentication)
    if SERVICE_MODE == "unprivate":
        API_KEYLIST = mode_config.get("keylist", [])
        if not isinstance(API_KEYLIST, list):
            raise ValueError(
                "keylist in unprivate configuration must be an array of API keys"
            )


# ============================================================================
# AUTHENTICATION DECORATOR
# ============================================================================


def _require_api_key(f):
    """Decorator to enforce API key authentication when running in unprivate mode.

    This decorator checks for a valid API key in the request body (JSON) or
    query string before allowing access to protected endpoints. In private or
    public modes, this decorator does nothing.

    Supported inputs:
    - JSON body field: api_key
    - Query string: ?api_key=<api-key> (useful for GET requests)

    Returns:
        401: If no API key is provided
        403: If API key is invalid
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip authentication check if not in unprivate mode
        if SERVICE_MODE != "unprivate":
            return f(*args, **kwargs)
        
        api_key = None

        # Primary: API key in JSON body (POST requests)
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            if isinstance(payload, dict):
                api_key = str(payload.get("api_key", "")).strip() or None

        # Fallback: API key in query string (useful for GET requests)
        if not api_key:
            api_key = request.args.get("api_key", "").strip() or None
        
        # Validate that an API key was provided
        if not api_key:
            return jsonify({
                "error": "Authentication required. Provide api_key in JSON body or query string."
            }), 401
        
        # Verify API key against the configured keylist
        if api_key not in API_KEYLIST:
            return jsonify({
                "error": "Invalid API key."
            }), 403
        
        # Authentication successful - proceed to the wrapped endpoint
        return f(*args, **kwargs)
    
    return decorated_function


# Initialize Flask application
app = Flask(__name__)


# ============================================================================
# IN-MEMORY TASK STORAGE
# ============================================================================

# Shared in-memory task store for tracking download jobs
# Note: All task data is lost on service restart (intentional design for simplicity)
jobs_lock = Lock()  # Thread-safe access to the jobs dictionary
jobs: dict[str, dict[str, Any]] = {}  # Map of task_id -> task metadata

# Background cleanup thread lifecycle guards
# The cleanup thread runs as a daemon and periodically removes old completed tasks
cleanup_lock = Lock()  # Ensures cleanup thread is started only once
cleanup_thread_started = False  # Flag to track if cleanup thread is running


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def _utc_iso() -> str:
    """Return current UTC time in ISO-8601 format.
    
    Used for timestamping task events (created_at, updated_at fields).
    """
    return datetime.now(timezone.utc).isoformat()


def _resolution_to_int(resolution: str | None) -> int | None:
    """Parse video resolution string to integer height value.
    
    Examples:
        '720p' -> 720
        '1080p' -> 1080
        '480' -> None (missing 'p' suffix)
        None -> None
    
    Args:
        resolution: Resolution string (e.g., '720p', '1080p')
    
    Returns:
        int: Height in pixels, or None if format is invalid
    """
    if not resolution:
        return None
    
    value = resolution.strip().lower()
    
    # Resolution must end with 'p' (e.g., '720p')
    if not value.endswith("p"):
        return None
    
    # Extract numeric part and validate
    number = value[:-1]
    if not number.isdigit():
        return None
    
    return int(number)


def _normalize_quality(quality: str, requested_format: str) -> str:
    """Normalize quality string to standard format for stream lookup.

    Ensures quality values match the expected format for pytube/pytubefix:
    - mp4 video: Adds 'p' suffix if missing (e.g., '720' -> '720p')
    - mp3 audio: Adds 'kbps' suffix if missing (e.g., '128' -> '128kbps')

    Args:
        quality: Raw quality value from API request
        requested_format: 'mp4' or 'mp3'

    Returns:
        Normalized quality string
    """
    value = quality.strip().lower()
    
    # For video (mp4), ensure format is like '720p'
    if requested_format == "mp4":
        if value.endswith("p"):
            return value  # Already normalized
        if value.isdigit():
            return f"{value}p"  # Add 'p' suffix
    
    # For audio (mp3), ensure format is like '128kbps'
    if requested_format == "mp3":
        if value.endswith("kbps"):
            return value  # Already normalized
        if value.isdigit():
            return f"{value}kbps"  # Add 'kbps' suffix
    
    # Return as-is if no normalization rule applies
    return quality.strip()


def _build_safe_filename(file_name: str) -> str:
    r"""Sanitize and validate filename for safe filesystem operations.
    
    Removes potentially dangerous characters:
    - Path separators (/ and \) are replaced with underscores
    - Excessive whitespace is collapsed
    - Empty names are rejected
    
    Args:
        file_name: Raw filename from user input or video title
    
    Returns:
        Sanitized filename stem (without extension)
        
    Raises:
        ValueError: If filename is empty after sanitization
    """
    # Replace path separators with underscores to prevent directory traversal
    cleaned = file_name.strip().replace("\\", "_").replace("/", "_")
    
    # Collapse multiple spaces into single spaces
    cleaned = " ".join(cleaned.split())
    
    # Validate that something remains after cleaning
    if not cleaned:
        raise ValueError("name must contain at least one non-space character")
    
    # Return stem only (filename without extension)
    return Path(cleaned).stem or "download"


def _resolve_unique_path(directory: Path, stem: str, suffix: str) -> Path:
    """Generate a unique filepath by appending a counter if file already exists.
    
    Prevents overwriting existing files by adding (1), (2), etc. to the filename.
    
    Examples:
        If 'video.mp4' exists:
        - Returns 'video (1).mp4' if that doesn't exist
        - Returns 'video (2).mp4' if both 'video.mp4' and 'video (1).mp4' exist
    
    Args:
        directory: Target directory for the file
        stem: Filename without extension
        suffix: File extension (e.g., '.mp4', '.mp3')
    
    Returns:
        Path object for a non-existing file
    """
    # Try the original filename first
    candidate = directory / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate

    # File exists, so append a numeric suffix
    counter = 1
    while True:
        candidate = directory / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _is_valid_youtube_url(video_link: str) -> bool:
    """Validate that a URL is a properly formatted YouTube link.
    
    Checks:
    1. Domain is youtube.com, youtu.be, or m.youtube.com
    2. URL has meaningful content (non-empty path or query string)
    
    Args:
        video_link: URL string to validate
    
    Returns:
        True if URL appears to be a valid YouTube link
    """
    link = video_link.strip().lower()
    parsed = urlparse(link)
    
    # Check if domain is one of YouTube's valid hostnames
    hostname = parsed.hostname or ""
    valid_hosts = {"youtube.com", "www.youtube.com", "youtu.be", "www.youtu.be", "m.youtube.com"}
    if not any(hostname.endswith(host.replace("www.", "")) for host in valid_hosts):
        return False
    
    # Basic structure check: URL must have content (path or query parameters)
    return bool(parsed.path.strip("/") or parsed.query)


def _is_playlist_url(video_link: str) -> bool:
    """Detect if a YouTube URL points to a playlist instead of a single video.
    
    Playlists are not supported by this service, so they need to be rejected.
    
    Detection criteria:
    1. URL contains 'list=' query parameter
    2. URL path starts with '/playlist'
    
    Args:
        video_link: YouTube URL to check
    
    Returns:
        True if URL appears to be a playlist
    """
    parsed = urlparse(video_link.strip())
    query_params = parse_qs(parsed.query)

    # Check for 'list' parameter (present in playlist URLs)
    if "list" in query_params:
        return True

    # Check if path explicitly indicates a playlist
    path = parsed.path.lower()
    return path.startswith("/playlist")


# ============================================================================
# BACKGROUND TASK CLEANUP
# ============================================================================


def _cleanup_finished_jobs_forever() -> None:
    """Background thread worker that periodically removes old completed/failed tasks.
    
    This function runs in an infinite loop as a daemon thread. It:
    1. Sleeps for TASK_CLEANUP_INTERVAL_SECONDS
    2. Checks all tasks for old completed/failed entries
    3. Removes tasks older than TASK_RETENTION_MINUTES
    
    This prevents memory leaks from accumulating task metadata.
    """
    # Calculate retention period in seconds (minimum 60 seconds)
    retention_seconds = max(60, TASK_RETENTION_MINUTES * 60)
    # Calculate cleanup check interval (minimum 10 seconds)
    interval_seconds = max(10, TASK_CLEANUP_INTERVAL_SECONDS)

    while True:
        try:
            # Wait before next cleanup cycle
            time.sleep(interval_seconds)
            
            now = time.time()
            removable_task_ids: list[str] = []

            # Thread-safe examination of all tasks
            with jobs_lock:
                for task_id, task in jobs.items():
                    # Only cleanup completed or failed tasks (not queued or in-progress)
                    if task.get("status") not in {"completed", "failed"}:
                        continue

                    # Check if task has aged beyond retention period
                    finished_at = task.get("finished_at_unix")
                    if isinstance(finished_at, (int, float)) and (now - finished_at) >= retention_seconds:
                        removable_task_ids.append(task_id)

                # Remove old tasks from the dictionary
                for task_id in removable_task_ids:
                    jobs.pop(task_id, None)
                    
        except Exception as exc:
            # Log errors but keep the cleanup thread running
            print(f"[Cleanup Thread Error] {exc}", flush=True)


def _ensure_cleanup_thread_started() -> None:
    """Start the background cleanup worker thread (exactly once, thread-safe).
    
    Uses a lock and flag to ensure the cleanup thread is started only once,
    even if multiple requests arrive simultaneously at startup.
    
    The cleanup thread is daemonized, so it won't prevent the service from
    shutting down gracefully.
    """
    global cleanup_thread_started

    # Thread-safe check and start
    with cleanup_lock:
        if cleanup_thread_started:
            return  # Already running

        # Create and start the background cleanup thread
        cleanup_thread = Thread(
            target=_cleanup_finished_jobs_forever,
            name="youtube-task-cleanup-worker",
            daemon=True,  # Daemon thread won't block shutdown
        )
        cleanup_thread.start()
        cleanup_thread_started = True


# ============================================================================
# YOUTUBE STREAM SELECTION AND DOWNLOADING
# ============================================================================


def _select_progressive_mp4_stream(yt: Any, normalized_quality: str) -> tuple[int, Any]:
    """Select the best progressive MP4 stream for the requested quality.
    
    Progressive streams contain both video and audio in a single file.
    These are available for qualities up to 720p on most videos.
    
    Selection logic (treats requested quality as maximum):
    1. If exact quality match exists, use it
    2. Otherwise, use highest available quality below the requested quality
    3. If nothing below target, use the lowest available quality
    
    This ensures we never exceed the requested quality but get as close as possible.
    
    Args:
        yt: YouTube object from pytube/pytubefix
        normalized_quality: Quality string like '720p' or '480p'
    
    Returns:
        tuple: (actual_height_int, stream_object)
        
    Raises:
        ValueError: If quality format is invalid or no streams are available
    """
    
    # Parse requested quality to integer height (e.g., '720p' -> 720)
    requested_height = _resolution_to_int(normalized_quality)
    if requested_height is None:
        raise ValueError("For mp4, quality must be a value like '720p' (or numeric like '720').")

    # Fetch all progressive MP4 streams from YouTube
    try:
        candidate_streams = list(
            yt.streams.filter(progressive=True, file_extension="mp4")
            .order_by("resolution")
            .desc()  # Start with highest quality
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

    # Verify at least one stream is available
    if not available:
        raise ValueError("No mp4 progressive streams are available for this video.")

    # Sort by resolution (highest first) and select best match
    available.sort(key=lambda item: item[0], reverse=True)
    
    # Find first stream at or below requested quality (or lowest if none below)
    return next(((h, s) for h, s in available if h <= requested_height), available[-1])


def _select_adaptive_mp4_stream(yt: Any, normalized_quality: str) -> tuple[int, Any]:
    """Select the best adaptive MP4 video-only stream for high quality downloads.
    
    Adaptive streams contain only video (no audio). These are used for qualities
    above 720p (e.g., 1080p, 1440p, 4K). Audio must be downloaded separately
    and merged using ffmpeg.
    
    Selection logic (treats requested quality as maximum):
    1. If exact quality match exists, use it
    2. Otherwise, use highest available quality below the requested quality
    3. If nothing below target, use the lowest available quality
    
    Args:
        yt: YouTube object from pytube/pytubefix
        normalized_quality: Quality string like '1080p' or '1440p'
    
    Returns:
        tuple: (actual_height_int, stream_object)
        
    Raises:
        ValueError: If quality format is invalid or no streams are available
    """

    # Parse requested quality to integer height
    requested_height = _resolution_to_int(normalized_quality)
    if requested_height is None:
        raise ValueError("For mp4, quality must be a value like '1080p' (or numeric like '1080').")

    # Fetch all adaptive (video-only) MP4 streams from YouTube
    try:
        candidate_streams = list(
            yt.streams.filter(adaptive=True, only_video=True, file_extension="mp4")
            .order_by("resolution")
            .desc()  # Start with highest quality
        )
    except HTTPError as exc:
        raise ValueError(
            "YouTube request failed while fetching available adaptive mp4 streams. "
            "Try again later or test another video. "
            f"Upstream error: HTTP {exc.code}."
        ) from exc

    # Build list of available resolutions with their stream objects
    available: list[tuple[int, Any]] = []
    for candidate in candidate_streams:
        height = _resolution_to_int(getattr(candidate, "resolution", None))
        if height is not None:
            available.append((height, candidate))

    # Verify at least one stream is available
    if not available:
        raise ValueError("No adaptive mp4 video streams are available for this video.")

    # Sort by resolution (highest first) and select best match
    available.sort(key=lambda item: item[0], reverse=True)
    
    # Find first stream at or below requested quality (or lowest if none below)
    return next(((h, s) for h, s in available if h <= requested_height), available[-1])


def _select_best_audio_stream_for_mp4(yt: Any) -> Any:
    """Select the highest quality audio stream for merging with adaptive video.
    
    Used when downloading high-quality MP4 (>720p) that requires separate
    audio and video streams to be merged.
    
    Selection priority:
    1. Highest bitrate audio/mp4 stream (best compatibility)
    2. Highest bitrate audio stream of any type (fallback)
    
    Args:
        yt: YouTube object from pytube/pytubefix
    
    Returns:
        Audio stream object with highest available bitrate
        
    Raises:
        ValueError: If no audio streams are available or YouTube API fails
    """
    try:
        # First, try to find audio/mp4 streams (best for MP4 container)
        stream = (
            yt.streams.filter(only_audio=True, mime_type="audio/mp4")
            .order_by("abr")  # Sort by audio bitrate
            .desc()  # Highest first
            .first()
        )
        
        # Fallback: accept any audio format and convert later
        if stream is None:
            stream = (
                yt.streams.filter(only_audio=True)
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

    # Verify we found an audio stream
    if stream is None:
        raise ValueError("No audio stream found for this video.")

    return stream


def _resolve_ffmpeg_path() -> str:
    """Locate ffmpeg executable for audio/video merging.
    
    FFmpeg is required for merging high-quality adaptive streams (>720p).
    
    Search order:
    1. FFMPEG_PATH environment variable (if set)
    2. System PATH (using shutil.which)
    
    Returns:
        Absolute path to ffmpeg executable
        
    Raises:
        ValueError: If ffmpeg cannot be found or FFMPEG_PATH is invalid
    """
    # Check if user specified a custom ffmpeg location
    env_path = os.getenv("FFMPEG_PATH")
    if env_path:
        if Path(env_path).exists():
            return env_path
        raise ValueError(
            f"FFMPEG_PATH was set to '{env_path}' but the file does not exist. "
            "Update FFMPEG_PATH or install ffmpeg."
        )

    # Try to find ffmpeg in system PATH
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path

    # FFmpeg not found - provide helpful error message
    raise ValueError(
        "ffmpeg is required to merge high-quality mp4 streams, but it was not found. "
        "Install ffmpeg or set FFMPEG_PATH to the ffmpeg executable."
    )


def _merge_av_with_ffmpeg(ffmpeg_path: str, video_path: Path, audio_path: Path, output_path: Path) -> None:
    """Merge separate video and audio streams into a single MP4 file using ffmpeg.
    
    This is necessary for high-quality downloads (>720p) where YouTube provides
    video and audio as separate adaptive streams.
    
    FFmpeg parameters:
    - -y: Overwrite output file if it exists
    - -i: Input files (video, then audio)
    - -c:v copy: Copy video stream without re-encoding (fast)
    - -c:a aac: Encode audio to AAC (widely compatible)
    - -movflags +faststart: Optimize for web streaming (metadata at start)
    
    Args:
        ffmpeg_path: Path to ffmpeg executable
        video_path: Path to video-only MP4 file
        audio_path: Path to audio-only file
        output_path: Path for merged output file
        
    Raises:
        ValueError: If ffmpeg fails or executable not found
    """
    # Build ffmpeg command with appropriate parameters
    command = [
        ffmpeg_path,
        "-y",              # Overwrite output without asking
        "-i", str(video_path),  # Input video
        "-i", str(audio_path),  # Input audio
        "-c:v", "copy",    # Copy video codec (no re-encoding)
        "-c:a", "aac",     # Encode audio as AAC
        "-movflags", "+faststart",  # Web-optimized MP4
        str(output_path),  # Output file
    ]

    # Execute ffmpeg and handle potential errors
    try:
        completed = subprocess.run(
            command,
            check=True,           # Raise exception on non-zero exit
            capture_output=True,  # Capture stdout/stderr
            text=True,            # Return strings, not bytes
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
    """Select audio-only stream for MP3 downloads.
    
    Attempts to find an audio stream matching the requested bitrate
    (e.g., '128kbps', '192kbps').
    
    Args:
        yt: YouTube object from pytube/pytubefix
        normalized_quality: Bitrate string like '128kbps' or '192kbps'
    
    Returns:
        Audio stream object matching the requested quality
        
    Raises:
        ValueError: If no matching audio stream is found or YouTube API fails
    """
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
    """Execute a single video/audio download based on the request payload.
    
    This is the main download orchestration function. It:
    1. Validates and normalizes input parameters
    2. Initializes the YouTube client
    3. Selects appropriate streams based on format and quality
    4. Downloads and processes the media
    5. Returns metadata about the completed download
    
    Args:
        payload: Dictionary with keys: video_link, format, quality, folder, name (optional)
    
    Returns:
        Dictionary with download result metadata (name, format, quality, save_path, etc.)
        
    Raises:
        ValueError: For various validation and download errors
    """
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
        save_dir = Path(folder).expanduser()  # Expand ~ to user home
        save_dir.mkdir(parents=True, exist_ok=True)  # Create all parent directories
    except (OSError, PermissionError) as exc:
        raise ValueError(
            f"Cannot create or access download folder '{folder}'. "
            f"Check permissions and disk space. Details: {exc}"
        ) from exc
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"Invalid folder path '{folder}'. Path contains invalid characters or is malformed."
        ) from exc

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
            raise ValueError("For mp4, quality must be a value like '720p' (or numeric like '720').")

        # Decide stream type based on quality:
        # - Progressive (video+audio combined): Up to 720p
        # - Adaptive (separate video/audio): Above 720p or if progressive unavailable
        use_adaptive = requested_height > 720
        if not use_adaptive:
            # Try progressive first for ≤720p
            try:
                selected_height, stream = _select_progressive_mp4_stream(yt, normalized_quality)
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
                    stream.download(output_path=str(save_dir), filename=output_path.name)
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
        selected_height, video_stream = _select_adaptive_mp4_stream(yt, normalized_quality)
        audio_stream = _select_best_audio_stream_for_mp4(yt)

        # Download video and audio to temporary directory, then merge
        try:
            with tempfile.TemporaryDirectory(prefix="yt-downloader-") as temp_dir:
                temp_dir_path = Path(temp_dir)
                
                # Download video stream
                video_path = Path(
                    video_stream.download(output_path=str(temp_dir_path), filename="video.mp4")
                )
                
                # Download audio stream
                audio_path = Path(
                    audio_stream.download(output_path=str(temp_dir_path), filename="audio.m4a")
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
        raise ValueError(
            f"Unexpected error downloading audio stream: {exc}"
        ) from exc

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
        "actual_quality": str(getattr(stream, "abr", normalized_quality) or normalized_quality),
        "save_path": str(target_path),
    }

def _validate_payload(payload: Any) -> tuple[dict[str, Any] | None, Any | None, int]:
    """Validate and normalize request payload for download endpoints.
    
    Supports two request formats:
    1. Single video: {video_link, format, quality, folder, name?}
    2. Batch videos: {videos: [{video_link, format, quality, folder, name?}, ...]}
    
    Validation checks:
    - Required fields are present and non-empty
    - Format is 'mp4' or 'mp3'
    - URLs are valid YouTube links
    - URLs are not playlists
    
    Args:
        payload: Raw request body (should be a dictionary)
    
    Returns:
        tuple: (validated_payload or None, error_response or None, http_status_code)
    """
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
        return None, {"error": "video_link must be a valid YouTube URL (youtube.com or youtu.be)."}, 400
    
    # Reject playlists
    if _is_playlist_url(video_link):
        return None, {"error": PLAYLIST_NOT_SUPPORTED_ERROR}, 400

    # Payload is valid
    return payload, None, 200


def _download_worker(task_id: str, payload: dict[str, Any]) -> None:
    """Background thread worker for executing download tasks.
    
    This function runs in a separate thread for each download request.
    It updates the task status in the shared jobs dictionary as it progresses.
    
    Task status flow:
    1. queued -> in_progress (when worker starts)
    2. in_progress -> completed (on success) OR failed (on error)
    
    Args:
        task_id: Unique identifier for this task
        payload: Validated download request (single video or batch)
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






@app.post("/api/download")
@_require_api_key
def download() -> tuple[Any, int]:
    """Create a new asynchronous download task.
    
    This endpoint accepts download requests and queues them for background processing.
    It immediately returns a task_id that can be used to check progress.
    
    Request formats:
    
    Single video:
    {
        "video_link": "https://www.youtube.com/watch?v=...",
        "format": "mp4",
        "quality": "720p",
        "folder": "/path/to/save",
        "name": "optional_custom_name"
    }
    
    Batch videos:
    {
        "videos": [
            {"video_link": "...", "format": "mp4", "quality": "720p", "folder": "..."},
            {"video_link": "...", "format": "mp3", "quality": "128kbps", "folder": "..."}
        ]
    }
    
    Returns:
        202: Task created successfully (returns task_id)
        400: Invalid request (validation errors)
        500: Server error (couldn't start worker)
    """
    # Ensure background cleanup thread is running
    _ensure_cleanup_thread_started()

    # Parse and validate request body
    payload = request.get_json(silent=True)
    validated_payload, error_body, status_code = _validate_payload(payload)
    if error_body is not None:
        return jsonify(error_body), status_code

    # Generate unique task ID and create task record
    task_id = str(uuid4())
    now = _utc_iso()

    with jobs_lock:
        jobs[task_id] = {
            "task_id": task_id,
            "status": "queued",  # Initial status
            "created_at": now,
            "updated_at": now,
        }

    # Start background worker thread for this download
    try:
        download_thread = Thread(
            target=_download_worker,
            args=(task_id, validated_payload),
            name=f"youtube-download-worker-{task_id}",
            daemon=False,  # Not a daemon - we want downloads to complete even during shutdown
        )
        download_thread.start()
    except Exception as exc:
        # Failed to start worker thread - mark task as failed
        with jobs_lock:
            jobs[task_id]["status"] = "failed"
            jobs[task_id]["error"] = f"Failed to start download worker: {exc}"
            jobs[task_id]["updated_at"] = _utc_iso()
            jobs[task_id]["finished_at_unix"] = time.time()
        return jsonify({
            "error": "Could not start download worker. The server may be under heavy load.",
            "task_id": task_id
        }), 500

    # Build response with task information
    response_body: dict[str, Any] = {
        "task_id": task_id,
        "status": "queued",
    }
    # For batch requests, include count of videos
    if isinstance(validated_payload.get("videos"), list):
        response_body["video_count"] = len(validated_payload["videos"])

    # Return 202 Accepted (task is queued, not yet completed)
    return jsonify(response_body), 202



@app.get("/api/download/<task_id>")
@_require_api_key
def download_status(task_id: str) -> tuple[Any, int]:
    """Check the status of a download task.
    
    Returns current state of the task including:
    - status: 'queued', 'in_progress', 'completed', or 'failed'
    - result: Download metadata (if completed)
    - error: Error message (if failed)
    
    Args:
        task_id: Task UUID returned from POST /api/download
    
    Returns:
        200: Task found (with current status)
        404: Task not found (may have been cleaned up or never existed)
    """
    # Ensure cleanup thread is running
    _ensure_cleanup_thread_started()

    # Retrieve task from in-memory store
    with jobs_lock:
        task = jobs.get(task_id)

    if task is None:
        return jsonify({"error": "Task not found."}), 404

    # Build response with task information
    response_body: dict[str, Any] = {
        "task_id": task["task_id"],
        "status": task["status"],
    }

    # Include result details if task completed successfully
    if task["status"] == "completed":
        response_body["result"] = task.get("result", {})
    
    # Include error message if task failed
    if task["status"] == "failed":
        response_body["error"] = task.get("error", "Unknown error")

    return jsonify(response_body), 200



@app.get("/api/health")
def health() -> tuple[Any, int]:
    """Health check endpoint with service status and task statistics.
    
    Public endpoint (no authentication required) for monitoring service health.
    
    Returns information about:
    - Service status and configuration
    - Current task queue statistics
    - Active settings (retention, cleanup interval)
    - YouTube client library being used
    
    Returns:
        200: Service is operational (with stats)
    """
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

    # Return health status with detailed service information
    return (
        jsonify(
            {
                "status": "ok",
                "bind": SERVICE_HOST,
                "port": SERVICE_PORT,
                "task_counts": counts,
                "task_retention_minutes": TASK_RETENTION_MINUTES,
                "task_cleanup_interval_seconds": TASK_CLEANUP_INTERVAL_SECONDS,
                "youtube_client": YOUTUBE_CLIENT_NAME,
            }
        ),
        200,
    )


# ============================================================================
# APPLICATION ENTRY POINT
# ============================================================================






if __name__ == "__main__":
    # ========================================================================
    # SERVICE STARTUP
    # ========================================================================
    
    try:
        # Load configuration from resources/configuration.json
        _initialize_service_config()
    except Exception as exc:
        print(f"\nERROR: Failed to load configuration: {exc}\n")
        exit(1)
    
    # Start background cleanup thread
    _ensure_cleanup_thread_started()
    # Display startup banner and configuration
    try:
        print("\n" + "="*50)
        print("  YoutubeDownloader API Server")
        print("="*50)
        print(f"\nMode: {SERVICE_MODE}")
        print(f"Binding to: http://{SERVICE_HOST}:{SERVICE_PORT}")
        if SERVICE_MODE == "unprivate":
            print(f"API Keys: {len(API_KEYLIST)} key(s) configured")
        print(f"Threading: enabled")
        print(f"YouTube Client: {YOUTUBE_CLIENT_NAME}")
        print(f"Task Retention: {TASK_RETENTION_MINUTES} minutes")
        print(f"Cleanup Interval: {TASK_CLEANUP_INTERVAL_SECONDS} seconds")
        print("\nServer starting...\n")
        
        # Start Flask development server
        app.run(host=SERVICE_HOST, port=SERVICE_PORT, debug=False, threaded=True)
        
    except KeyboardInterrupt:
        # Graceful shutdown on Ctrl+C
        print("\n\n" + "="*50)
        print("  Server Stopped")
        print("="*50 + "\n")
        
    except OSError as exc:
        # Handle common network binding errors
        if "Address already in use" in str(exc):
            print(
                f"\nERROR: Port {SERVICE_PORT} is already in use.\n"
                f"   Either stop the other process, or change the port\n"
                f"   in resources/configuration.json\n"
            )
        elif "Permission denied" in str(exc):
            print(
                f"\nERROR: Permission denied to bind to port {SERVICE_PORT}.\n"
                f"   On Linux/macOS, use a port >= 1024 or run with sudo.\n"
            )
        else:
            print(f"\nERROR: Network binding failed: {exc}\n")
            
    except Exception as exc:
        # Catch-all for unexpected errors
        print(f"\nERROR: Server startup failed: {exc}\n")