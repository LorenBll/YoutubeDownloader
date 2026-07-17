# YoutubeDownloader

YoutubeDownloader is a local YouTube download service. It solves the problem of queuing single-video or batch downloads and returning the downloaded media in MP4 or MP3 form through an HTTP API.

## About

YoutubeDownloader is scoped to request validation, background download jobs, and file delivery on the local machine. The service binds to `127.0.0.1` on port `49156` and rejects API calls that do not come from the local device. Task state is kept in memory, and a cleanup thread removes finished jobs after a configurable retention period.

**Features:**

- **Single and Batch Downloads** — queue one or many video downloads in a single API call. Each video in a batch is processed independently.
- **Adaptive Quality Selection** — supports progressive MP4 streams (up to 720p, video and audio combined) and adaptive MP4 streams (above 720p, requires ffmpeg for merging).
- **MP3 Audio Extraction** — download audio-only streams at configurable bitrates (e.g. 128kbps, 160kbps).
- **Playlist Detection** — YouTube playlist URLs are explicitly rejected, keeping the scope limited to single-video downloads.
- **Path Policy** — configurable allowlist and blacklist of root directories control where downloads may be written.
- **Background Task Cleanup** — finished tasks are automatically removed after a configurable retention period.
- **YouTube Client Auto-Detection** — attempts to load `pytubefix` first, falls back to `pytube`.

> **Safety notice**: YoutubeDownloader is intended for local, personal use only. Respect copyright laws and YouTube's Terms of Service when downloading content.

## Setup

1. Windows: run `scripts\setup.bat` or Unix: run `bash scripts/setup.sh` (creates a virtual environment, installs dependencies, checks configuration).
2. Manual: `pip install -r requirements.txt` after creating a virtual environment.
3. Install `ffmpeg` if you want to merge adaptive MP4 streams above 720p.
4. Review `resources/configuration.json` to configure `port`, `servicehandlerEnabled`, `servicehandlerPort`, `allowed_roots`, and `blacklisted_roots`.
   - `allowed_roots`: list of root paths the API is allowed to write downloads into. If this list is non-empty, ONLY these roots are permitted and the blacklist is ignored.
   - `blacklisted_roots`: list of root paths that are forbidden when `allowed_roots` is empty. If `allowed_roots` is empty and `blacklisted_roots` is non-empty, any path inside a blacklisted root is forbidden.
   - Behavior summary:
     - If `allowed_roots` is non-empty -> only those roots are permitted (blacklist ignored).
     - Else if `blacklisted_roots` is non-empty -> all paths are permitted except any inside a blacklisted root.
     - Else (both lists empty) -> all paths on the system are permitted.
5. Leave the project structure intact so the service can find `resources/` and `src/`.

## Run

1. Windows: run `scripts\run.bat`.
2. Unix-like systems: run `bash scripts/run.sh`.
3. Manual: run `python src/main.py` from the project root.

## Integration

This service can optionally register with [ServiceHandler](https://www.github.com/LorenBll/ServiceHandler) for service discovery, but does not depend on it. Set `servicehandlerEnabled` in `resources/configuration.json` to control this behavior.

When registered, YoutubeDownloader also registers its API endpoints with ServiceHandler so they can be discovered by other services.

## Auto-Startup

The `deployment/` directory contains platform-specific startup configurations:

- **Windows**: `startup-windows.vbs` — Windows startup script (place in `shell:startup`).
- **macOS**: `com.service.plist` — macOS launchd service definition.
- **Linux**: `service.service` — Linux systemd service unit.

## Access Control

All `/api/*` endpoints are local-device only. Requests from non-local addresses are rejected with:

- `403` -> `{ "error": "Local device access only." }`
- All endpoints also support `HEAD` and `OPTIONS`.
- API responses use `Connection: close`.

## API Endpoints

### `POST /api/download` (also `HEAD`, `OPTIONS`)
Queues a single or batch download task and returns a task ID.

- Auth: local-device only (no API key required)
- Body (JSON object):
  - Single-download mode (required fields):
    - `video_link` (string, required): valid YouTube URL (`youtube.com`, `youtu.be`, or `m.youtube.com`), playlists are rejected.
    - `format` (string, required): `mp4` or `mp3`.
    - `quality` (string, required):
      - mp4: values like `720`, `720p`, `1080`, `1080p`
      - mp3: values like `128`, `128kbps`, `160`, `160kbps`
    - `folder` (string, required): destination folder path (created if missing). The folder must be allowed by `resources/configuration.json`.
    - `name` (string, optional): preferred file name stem.
    - `file_name` (string, optional alias): alternative to `name`.
  - Batch mode:
    - `videos` (array, required): non-empty array of video objects. Each item must include single-download required fields.
- Returns:
  - `202` single -> `{ "task_id": "<uuid>", "status": "queued" }`
  - `202` batch -> `{ "task_id": "<uuid>", "status": "queued", "video_count": <n> }`
  - `400` -> `{ "error": "Request body must be valid JSON." }`
  - `400` -> `{ "error": "Missing required fields.", "missing_fields": ["..."] }`
  - `400` -> `{ "error": "format must be either 'mp4' or 'mp3'" }`
  - `400` -> `{ "error": "video_link must be a valid YouTube URL (youtube.com or youtu.be)." }`
  - `400` -> `{ "error": "Playlist download is not supported. Please provide a single video URL." }`
  - `400` batch validation ->
    ```json
    {
        "error": "Invalid videos payload.",
        "video_errors": [
            { "index": 0, "error": "..." }
        ]
    }
    ```
  - `500` ->
    ```json
    {
        "error": "Could not start download worker. The server may be under heavy load.",
        "task_id": "<uuid>"
    }
    ```

### `GET /api/task/<task_id>` (also `HEAD`, `OPTIONS`)
Returns current task status and final result or error.

- Auth: local-device only (no API key required)
- Path parameters:
  - `task_id` (string, required): task identifier returned by `POST /api/download`.
- Returns:
  - `200` queued or in progress -> `{ "task_id": "<uuid>", "status": "queued|in_progress" }`
  - `200` completed (single) ->
    ```json
    {
        "task_id": "<uuid>",
        "status": "completed",
        "result": {
            "name": "<file-name-stem>",
            "format": "mp4|mp3",
            "requested_quality": "<normalized-request>",
            "actual_quality": "<resolved-stream-quality>",
            "save_path": "<final-file-path>",
            "merge": "ffmpeg"
        }
    }
    ```
    Note: `merge` appears only for adaptive mp4 merges.
  - `200` completed (batch) ->
    ```json
    {
        "task_id": "<uuid>",
        "status": "completed",
        "result": {
            "items": [
                { "index": 0, "status": "completed", "result": { "...": "..." } },
                { "index": 1, "status": "failed", "error": "..." }
            ],
            "summary": { "total": 2, "completed": 1, "failed": 1 }
        }
    }
    ```
  - `200` failed -> `{ "task_id": "<uuid>", "status": "failed", "error": "<reason>" }`
  - `404` -> `{ "error": "Task not found." }`

### `GET /api/health` (also `HEAD`, `OPTIONS`)
Service and queue health snapshot.

- Auth: local-device only (no API key required)
- Body: none
- Returns:
  - `200` ->
    ```json
    {
        "status": "ok",
        "service": "YoutubeDownloader",
        "bind_address": "127.0.0.1",
        "port": 49156,
        "hostname": "...",
        "pid": 12345,
        "task_counts": {
            "queued": 0,
            "in_progress": 0,
            "completed": 0,
            "failed": 0,
            "total": 0
        },
        "task_retention_minutes": 30,
        "task_cleanup_interval_seconds": 60,
        "youtube_client": "pytubefix|pytube"
    }
    ```

---

## Support
- Open an issue on [GitHub](https://github.com/LorenBll/YoutubeDownloader/issues) for bug reports, feature requests, or help.

## License
- [LICENSE](LICENSE)

## Author
- [LorenBll](https://github.com/LorenBll)
