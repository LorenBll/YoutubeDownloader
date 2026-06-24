# YoutubeDownloader

YoutubeDownloader is a local YouTube download service. It solves the problem of queuing single-video or batch downloads and returning the downloaded media in MP4 or MP3 form through an HTTP API.

## About
YoutubeDownloader is scoped to request validation, background download jobs, and file delivery on the local machine. The service binds to `127.0.0.1` on port `49156`, keeps task state in memory, and uses a cleanup thread to remove finished jobs after a retention period.

## Setup
1. Install the Python dependencies with `pip install -r requirements.txt`.
2. Install `ffmpeg` if you want to merge adaptive MP4 streams above 720p.
3. Review `resources/configuration.json` to configure `port`, `allowed_roots`, and `blacklisted_roots`.
		- `allowed_roots`: list of root paths the API is allowed to write downloads into. If this list is non-empty, ONLY these roots are permitted and the blacklist is ignored.
		- `blacklisted_roots`: list of root paths that are forbidden when `allowed_roots` is empty. If `allowed_roots` is empty and `blacklisted_roots` is non-empty, any path inside a blacklisted root is forbidden.
		- Behavior summary:
			- If `allowed_roots` is non-empty → only those roots are permitted (blacklist ignored).
			- Else if `blacklisted_roots` is non-empty → all paths are permitted except any inside a blacklisted root.
			- Else (both lists empty) → all paths on the system are permitted.
4. Leave the project structure intact so the service can find `resources/` and `src/`.

## Run
1. Windows: run `scripts\run.bat`.
2. Unix-like systems: run `bash scripts/run.sh`.
3. Manual: run `python src/main.py` from the project root.

## API Endpoints

All endpoints also support `OPTIONS`; `GET` endpoints additionally support `HEAD`.

### `POST /api/download` (also `OPTIONS`)
Queues a single or batch download task and returns a task ID.

- Body (JSON object):
	- Single-download mode (required fields):
		- `video_link` (string, required): valid YouTube URL (`youtube.com` or `youtu.be`), playlists are rejected.
		- `format` (string, required): `mp4` or `mp3`.
		- `quality` (string, required):
			- mp4: values like `720`, `720p`, `1080`, `1080p`
			- mp3: values like `128`, `128kbps`, `160`, `160kbps`
		- `folder` (string, required): destination folder path (created if missing).
			- The folder must be allowed by `resources/configuration.json`.
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
Returns current task status and final result/error.

- Path parameters:
	- `task_id` (string, required): task identifier returned by `POST /api/download`.
- Returns:
	- `200` queued/in progress -> `{ "task_id": "<uuid>", "status": "queued|in_progress" }`
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

- Body: none
- Returns:
	- `200` ->
		```json
		{
			"status": "ok",
			"service": "YoutubeDownloader",
			"bind_address": "127.0.0.1",
			"port": 49156,
			"task_counts": {
				"queued": 0,
				"in_progress": 0,
				"completed": 0,
				"failed": 0,
				"total": 0
			},
			"task_retention_minutes": 60,
			"task_cleanup_interval_seconds": 60,
			"youtube_client": "WEB",
			"hostname": "...",
			"primary_ip": "...",
			"local_ips": ["..."]
		}
		```

## License
- [LICENSE](LICENSE)

## Author
- [LorenBll](https://github.com/LorenBll)