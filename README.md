# YoutubeDownloader

YoutubeDownloader is a local Flask service for downloading YouTube videos or audio. It validates single or batch download requests, runs downloads in background tasks, and exposes task status through polling.

## About

- Scope: local YouTube download orchestration with format and quality selection.
- Runtime model: queued worker tasks for download processing and periodic cleanup.
- Networking: local-only bind (`127.0.0.1`) with health and task-status endpoints.

## Setup

### Prerequisites

- Python 3.10 or newer
- `ffmpeg` for high-quality `mp4` merges above 720p

### Install Dependencies

```bash
python -m pip install -r requirements.txt
```

### Configuration

Edit `resources/configuration.json` as needed:

- `port`: TCP port used by the service

Optional environment variables:

- `TASK_RETENTION_MINUTES`: retention window for finished tasks
- `TASK_CLEANUP_INTERVAL_SECONDS`: cleanup loop interval
- `FFMPEG_PATH`: explicit path to `ffmpeg` when not in `PATH`

## Run

Start with:

```bash
python src/main.py
```

Windows shortcut:

```bat
scripts\run.bat
```

Startup behavior is consistent with the other services in this workspace: structured logging and a threaded Flask server.

## Usage

### `POST /api/download`

- Method: `POST`
- Input: JSON with `video_link`, `format`, `quality`, and `folder` (supports batch through `videos` array)
- Behavior: validates input and queues a download task
- Response: `202 Accepted` with `task_id`

### `GET /api/task/<task_id>`

- Method: `GET`
- Input: path parameter `task_id`
- Behavior: returns task state and result or error details when available
- Response: `200 OK`

### `GET /api/health`

- Method: `GET`
- Input: none
- Behavior: reports service and task health with local networking details
- Response: `200 OK` with `status`, `service`, `bind`, `port`, `task_counts`, `task_retention_minutes`, `task_cleanup_interval_seconds`, `youtube_client`, `hostname`, `primary_ip`, and `local_ips`

## Project Structure

```text
YoutubeDownloader/
├── deployment/
├── resources/
│   └── configuration.json
├── scripts/
├── src/
│   └── main.py
├── LICENSE
├── README.md
├── requirements.txt
└── SECURITY.md
```

## License

This project is licensed under the terms specified in [LICENSE](LICENSE).