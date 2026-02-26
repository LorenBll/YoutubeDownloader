from __future__ import annotations

import importlib
import os
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
from uuid import uuid4

from flask import Flask, jsonify, request

# Local-only service bind details.
SERVICE_HOST = "127.0.0.45"
SERVICE_PORT = 8000

# API contract fields (mandatory).
REQUIRED_FIELDS = ["video_link", "format", "quality", "folder"]
ALLOWED_FORMATS = {"mp4", "mp3"}
PLAYLIST_NOT_SUPPORTED_ERROR = "Playlist download is not supported. Please provide a single video URL."

# In-memory task metadata retention knobs.
try:
    TASK_RETENTION_MINUTES = int(os.getenv("TASK_RETENTION_MINUTES", "30"))
except (ValueError, TypeError):
    TASK_RETENTION_MINUTES = 30
try:
    TASK_CLEANUP_INTERVAL_SECONDS = int(os.getenv("TASK_CLEANUP_INTERVAL_SECONDS", "60"))
except (ValueError, TypeError):
    TASK_CLEANUP_INTERVAL_SECONDS = 60


def _resolve_youtube_client () -> tuple[Any,str]:
    
    """Return the first available YouTube client class and module name.

    Preferred order:
    1) pytubefix (better compatibility with recent YouTube changes)
    2) pytube (fallback)
    """
    
    for module_name in ("pytubefix", "pytube"):
        try:
            module = importlib.import_module(module_name)
            youtube_class = getattr(module, "YouTube", None)
            if youtube_class is not None:
                return youtube_class, module_name
        except ImportError:
            continue

    raise RuntimeError("No supported YouTube client found. Install pytubefix or pytube.")


YouTubeClient, YOUTUBE_CLIENT_NAME = _resolve_youtube_client()
app = Flask(__name__)

# Shared in-memory task store 
# (in-memory means all tasks are lost on backend restart, which is acceptable for this simple service).
jobs_lock = Lock()
jobs: dict[str, dict[str, Any]] = {}

# Cleanup worker lifecycle guard
# (cleanup thread is daemonized, so it won't block process exit; we just want to start it once when needed).
cleanup_lock = Lock()
cleanup_thread_started = False



def _utc_iso () -> str:
    
    """Return current UTC time in ISO-8601 format."""
    
    return datetime.now(timezone.utc).isoformat()

def _resolution_to_int ( resolution:str | None ) -> int|None:
    
    """Convert a resolution like '720p' to integer 720, else None."""
    
    if not resolution:
        return None
    
    value = resolution.strip().lower()
    if not value.endswith("p"):
        return None
    
    number = value[:-1]
    if not number.isdigit():
        return None
    
    return int(number)


def _normalize_quality( quality:str , requested_format:str ) -> str:
    
    """Normalize quality for stream lookup.

    - mp4: '720' -> '720p'
    - mp3: '128' -> '128kbps'
    """
    
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


def _build_safe_filename ( file_name:str ) -> str:
    
    """Sanitize filename by removing path separators and empty names."""
    
    cleaned = file_name.strip().replace("\\", "_").replace("/", "_")
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        raise ValueError("name must contain at least one non-space character")
    
    return Path(cleaned).stem or "download"


def _resolve_unique_path ( directory:Path , stem:str , suffix:str ) -> Path:

    """Return a unique path by appending a numeric suffix when needed."""

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

    """Return True when URL appears to be a valid YouTube URL."""
    
    link = video_link.strip().lower()
    parsed = urlparse(link)
    
    # Check for youtube.com or youtu.be domain
    hostname = parsed.hostname or ""
    valid_hosts = {"youtube.com", "www.youtube.com", "youtu.be", "www.youtu.be", "m.youtube.com"}
    if not any(hostname.endswith(host.replace("www.", "")) for host in valid_hosts):
        return False
    
    # Basic structure check: should have something in path or query
    return bool(parsed.path.strip("/") or parsed.query)


def _is_playlist_url(video_link: str) -> bool:

    """Return True when URL appears to target a playlist."""

    parsed = urlparse(video_link.strip())
    query_params = parse_qs(parsed.query)

    if "list" in query_params:
        return True

    path = parsed.path.lower()
    return path.startswith("/playlist")


def _cleanup_finished_jobs_forever () -> None:
    
    """Background loop: periodically purge old completed/failed tasks."""
    
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
                    if isinstance(finished_at, (int, float)) and (now - finished_at) >= retention_seconds:
                        removable_task_ids.append(task_id)

                for task_id in removable_task_ids:
                    jobs.pop(task_id, None)
        except Exception as exc:
            # Log but don't crash the cleanup thread
            print(f"[Cleanup Thread Error] {exc}", flush=True)


def _ensure_cleanup_thread_started () -> None:
    
    """Start the cleanup worker exactly once (thread-safe)."""
    
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


def _select_progressive_mp4_stream ( yt:Any , normalized_quality:str ) -> tuple[int,Any]:
    
    """Select best progressive mp4 stream.

    The requested quality is treated as a target maximum.
    - If exact target exists, it is selected.
    - Otherwise select the closest available progressive quality below target.
    - If nothing is below target, use the smallest available progressive quality.
    """
    
    requested_height = _resolution_to_int(normalized_quality)
    if requested_height is None:
        raise ValueError("For mp4, quality must be a value like '720p' (or numeric like '720').")

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

    available: list[tuple[int, Any]] = []
    for candidate in candidate_streams:
        height = _resolution_to_int(getattr(candidate, "resolution", None))
        if height is not None:
            available.append((height, candidate))

    if not available:
        raise ValueError("No mp4 progressive streams are available for this video.")

    available.sort(key=lambda item: item[0], reverse=True)
    return next(((h, s) for h, s in available if h <= requested_height), available[-1])


def _select_adaptive_mp4_stream ( yt:Any , normalized_quality:str ) -> tuple[int,Any]:

    """Select best adaptive mp4 video-only stream.

    The requested quality is treated as a target maximum.
    - If exact target exists, it is selected.
    - Otherwise select the closest available adaptive quality below target.
    - If nothing is below target, use the smallest available adaptive quality.
    """

    requested_height = _resolution_to_int(normalized_quality)
    if requested_height is None:
        raise ValueError("For mp4, quality must be a value like '1080p' (or numeric like '1080').")

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


def _select_best_audio_stream_for_mp4 ( yt:Any ) -> Any:

    """Select highest bitrate audio stream for mp4 container."""

    try:
        stream = (
            yt.streams.filter(only_audio=True, mime_type="audio/mp4")
            .order_by("abr")
            .desc()
            .first()
        )
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

    if stream is None:
        raise ValueError("No audio stream found for this video.")

    return stream


def _resolve_ffmpeg_path () -> str:

    """Return ffmpeg executable path or raise a friendly error."""

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


def _merge_av_with_ffmpeg ( ffmpeg_path:str , video_path:Path , audio_path:Path , output_path:Path ) -> None:

    """Merge video-only and audio-only streams into a single mp4 file."""

    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ValueError(
            "ffmpeg executable could not be found. "
            "Install ffmpeg or set FFMPEG_PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        message = "ffmpeg failed while merging audio and video streams."
        if stderr:
            message += f" Details: {stderr}"
        raise ValueError(message) from exc


def _select_audio_stream ( yt:Any , normalized_quality:str ) -> Any:
    
    """Select audio-only stream matching requested bitrate."""
    
    try:
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

    if stream is None:
        raise ValueError(f"No audio stream found for quality '{normalized_quality}'.")

    return stream


def _download_with_pytube ( payload:dict[str,Any] ) -> dict[str,Any]:
    
    """Download media according to request payload and return result metadata."""
    
    video_link = payload["video_link"].strip()
    requested_format = payload["format"].strip().lower()
    quality = payload["quality"].strip()
    requested_name = str(payload.get("name", payload.get("file_name", ""))).strip()
    folder = payload["folder"].strip()

    if requested_format not in ALLOWED_FORMATS:
        raise ValueError("format must be either 'mp4' or 'mp3'")

    normalized_quality = _normalize_quality(quality, requested_format)

    # Validate and prepare save directory
    try:
        save_dir = Path(folder).expanduser()
        save_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as exc:
        raise ValueError(
            f"Cannot create or access download folder '{folder}'. "
            f"Check permissions and disk space. Details: {exc}"
        ) from exc
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"Invalid folder path '{folder}'. Path contains invalid characters or is malformed."
        ) from exc

    try:
        yt = YouTubeClient(video_link)
    except (HTTPError, Exception) as exc:
        if isinstance(exc, HTTPError):
            raise ValueError(
                "YouTube request failed while preparing the download. "
                "This may be temporary or related to pytube parsing for this video. "
                f"Upstream error: HTTP {exc.code}."
            ) from exc
        raise ValueError(
            f"Failed to load YouTube video. The URL may be invalid or the video unavailable. "
            f"Details: {exc}"
        ) from exc

    try:
        video_title = yt.title
    
    except HTTPError as exc:
        raise ValueError(
            "YouTube request failed while reading video metadata. "
            "Try again later or test a different video URL. "
            f"Upstream error: HTTP {exc.code}."
        ) from exc

    save_name = requested_name if requested_name else video_title
    safe_stem = _build_safe_filename(save_name)

    if requested_format == "mp4":

        requested_height = _resolution_to_int(normalized_quality)
        if requested_height is None:
            raise ValueError("For mp4, quality must be a value like '720p' (or numeric like '720').")

        use_adaptive = requested_height > 720
        if not use_adaptive:
            try:
                selected_height, stream = _select_progressive_mp4_stream(yt, normalized_quality)
            except ValueError:
                use_adaptive = True

        if not use_adaptive:
            try:
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

            return {
                "name": output_path.stem,
                "format": "mp4",
                "requested_quality": normalized_quality,
                "actual_quality": f"{selected_height}p",
                "save_path": str(output_path),
            }

        ffmpeg_path = _resolve_ffmpeg_path()
        selected_height, video_stream = _select_adaptive_mp4_stream(yt, normalized_quality)
        audio_stream = _select_best_audio_stream_for_mp4(yt)

        try:
            with tempfile.TemporaryDirectory(prefix="yt-downloader-") as temp_dir:
                temp_dir_path = Path(temp_dir)
                video_path = Path(
                    video_stream.download(output_path=str(temp_dir_path), filename="video.mp4")
                )
                audio_path = Path(
                    audio_stream.download(output_path=str(temp_dir_path), filename="audio.m4a")
                )
                output_path = _resolve_unique_path(save_dir, safe_stem, ".mp4")
                _merge_av_with_ffmpeg(ffmpeg_path, video_path, audio_path, output_path)
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

        return {
            "name": output_path.stem,
            "format": "mp4",
            "requested_quality": normalized_quality,
            "actual_quality": f"{selected_height}p",
            "save_path": str(output_path),
            "merge": "ffmpeg",
        }

    stream = _select_audio_stream(yt, normalized_quality)

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

    if downloaded_path != target_path and downloaded_path.exists():
        try:
            downloaded_path.replace(target_path)
        except (OSError, PermissionError) as exc:
            raise ValueError(
                f"Cannot move mp3 file to target location. Check permissions and disk space. "
                f"Details: {exc}"
            ) from exc

    return {
        "name": target_path.stem,
        "format": "mp3",
        "requested_quality": normalized_quality,
        "actual_quality": str(getattr(stream, "abr", normalized_quality) or normalized_quality),
        "save_path": str(target_path),
    }


def _validate_payload ( payload:Any ) -> tuple[ dict[str,Any] | None , Any | None , int]:
    
    """Validate request JSON payload and report missing fields."""
    
    if not isinstance(payload, dict):
        return None, {"error": "Request body must be valid JSON."}, 400

    videos_payload = payload.get("videos")
    if videos_payload is not None:
        if not isinstance(videos_payload, list) or not videos_payload:
            return None, {"error": "videos must be a non-empty array."}, 400

        video_errors: list[dict[str, Any]] = []
        validated_videos: list[dict[str, Any]] = []

        for index, video_payload in enumerate(videos_payload):
            if not isinstance(video_payload, dict):
                video_errors.append(
                    {
                        "index": index,
                        "error": "Each video item must be a JSON object.",
                    }
                )
                continue

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

            requested_format = str(video_payload.get("format", "")).strip().lower()
            if requested_format not in ALLOWED_FORMATS:
                video_errors.append(
                    {
                        "index": index,
                        "error": "format must be either 'mp4' or 'mp3'",
                    }
                )
                continue

            video_link = str(video_payload.get("video_link", "")).strip()
            if not _is_valid_youtube_url(video_link):
                video_errors.append(
                    {
                        "index": index,
                        "error": "video_link must be a valid YouTube URL (youtube.com or youtu.be).",
                    }
                )
                continue
            if _is_playlist_url(video_link):
                video_errors.append(
                    {
                        "index": index,
                        "error": PLAYLIST_NOT_SUPPORTED_ERROR,
                    }
                )
                continue

            validated_videos.append(video_payload)

        if video_errors:
            return (
                None,
                {
                    "error": "Invalid videos payload.",
                    "video_errors": video_errors,
                },
                400,
            )

        return {"videos": validated_videos}, None, 200

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

    requested_format = str(payload.get("format", "")).strip().lower()
    if requested_format not in ALLOWED_FORMATS:
        return None, {"error": "format must be either 'mp4' or 'mp3'"}, 400

    video_link = str(payload.get("video_link", "")).strip()
    if not _is_valid_youtube_url(video_link):
        return None, {"error": "video_link must be a valid YouTube URL (youtube.com or youtu.be)."}, 400
    if _is_playlist_url(video_link):
        return None, {"error": PLAYLIST_NOT_SUPPORTED_ERROR}, 400

    return payload, None, 200


def _download_worker( task_id:str , payload:dict[str,Any] ) -> None:
    
    """Thread target: perform one download job and persist status/result."""
    
    with jobs_lock:
        jobs[task_id]["status"] = "in_progress"
        jobs[task_id]["updated_at"] = _utc_iso()

    videos = payload.get("videos")
    if isinstance(videos, list):
        item_results: list[dict[str, Any]] = []
        completed_count = 0
        failed_count = 0

        for index, video_payload in enumerate(videos):
            try:
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
                item_results.append(
                    {
                        "index": index,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                failed_count += 1

        with jobs_lock:
            jobs[task_id]["status"] = "completed"
            jobs[task_id]["result"] = {
                "items": item_results,
                "summary": {
                    "total": len(videos),
                    "completed": completed_count,
                    "failed": failed_count,
                },
            }
            jobs[task_id]["updated_at"] = _utc_iso()
            jobs[task_id]["finished_at_unix"] = time.time()

        return

    try:
        result = _download_with_pytube(payload)
        with jobs_lock:
            jobs[task_id]["status"] = "completed"
            jobs[task_id]["result"] = result
            jobs[task_id]["updated_at"] = _utc_iso()
            jobs[task_id]["finished_at_unix"] = time.time()
    
    except Exception as exc:
        with jobs_lock:
            jobs[task_id]["status"] = "failed"
            jobs[task_id]["error"] = str(exc)
            jobs[task_id]["updated_at"] = _utc_iso()
            jobs[task_id]["finished_at_unix"] = time.time()






@app.post("/api/download")
def download () -> tuple[Any,int]:
    
    """Create a new async download task and start a worker thread."""
    
    _ensure_cleanup_thread_started()

    payload = request.get_json(silent=True)
    validated_payload, error_body, status_code = _validate_payload(payload)
    if error_body is not None:
        return jsonify(error_body), status_code

    task_id = str(uuid4())
    now = _utc_iso()

    with jobs_lock:
        jobs[task_id] = {
            "task_id": task_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
        }

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
        return jsonify({
            "error": "Could not start download worker. The server may be under heavy load.",
            "task_id": task_id
        }), 500

    response_body: dict[str, Any] = {
        "task_id": task_id,
        "status": "queued",
    }
    if isinstance(validated_payload.get("videos"), list):
        response_body["video_count"] = len(validated_payload["videos"])

    return jsonify(response_body), 202



@app.get("/api/download/<task_id>")
def download_status (task_id:str) -> tuple[Any,int]:
    
    """Return status/result/error for an existing task."""
    
    _ensure_cleanup_thread_started()

    with jobs_lock:
        task = jobs.get(task_id)

    if task is None:
        return jsonify({"error": "Task not found."}), 404

    response_body: dict[str, Any] = {
        "task_id": task["task_id"],
        "status": task["status"],
    }

    if task["status"] == "completed":
        response_body["result"] = task.get("result", {})
    if task["status"] == "failed":
        response_body["error"] = task.get("error", "Unknown error")

    return jsonify(response_body), 200



@app.get("/api/health")
def health() -> tuple[Any,int]:
    
    """Simple health endpoint with queue stats and runtime settings."""
    
    _ensure_cleanup_thread_started()

    with jobs_lock:
        snapshot = list(jobs.values())

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






if __name__ == "__main__":
    _ensure_cleanup_thread_started()
    try:
        print("\n" + "="*50)
        print("  YoutubeDownloader API Server")
        print("="*50)
        print(f"\nBinding to: http://{SERVICE_HOST}:{SERVICE_PORT}")
        print(f"Threading: enabled")
        print(f"YouTube Client: {YOUTUBE_CLIENT_NAME}")
        print("\nServer starting...\n")
        app.run(host=SERVICE_HOST, port=SERVICE_PORT, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\n\n" + "="*50)
        print("  Server Stopped")
        print("="*50 + "\n")
    except OSError as exc:
        if "Address already in use" in str(exc):
            print(
                f"\n❌ ERROR: Port {SERVICE_PORT} is already in use.\n"
                f"   Either stop the other process, or set a different port\n"
                f"   by running: export FLASK_PORT=8001\n"
            )
        elif "Permission denied" in str(exc):
            print(
                f"\n❌ ERROR: Permission denied to bind to port {SERVICE_PORT}.\n"
                f"   On Linux/macOS, use a port >= 1024 or run with sudo.\n"
            )
        else:
            print(f"\n❌ ERROR: Network binding failed: {exc}\n")
    except Exception as exc:
        print(f"\n❌ ERROR: Server startup failed: {exc}\n")