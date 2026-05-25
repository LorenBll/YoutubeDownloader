# YoutubeDownloader

YoutubeDownloader is a small local Flask service for downloading YouTube videos or audio. It accepts single or batch requests, queues each download in the background, and exposes task status through polling endpoints. The server binds to `127.0.0.1` and uses the port in [resources/configuration.json](resources/configuration.json).

## About

The service keeps the download workflow local to the machine running it. Runtime configuration lives in [resources/configuration.json](resources/configuration.json), while background job retention can also be controlled with environment variables.

## Setup

### Prerequisites

- Python 3.10 or newer
- `ffmpeg` if you want high-quality `mp4` downloads above 720p

### Install Dependencies

```bash
python -m pip install -r requirements.txt
```

### Configuration

Edit [resources/configuration.json](resources/configuration.json) if you want to change the listening port.

- `port` controls the TCP port the service listens on
- `TASK_RETENTION_MINUTES` and `TASK_CLEANUP_INTERVAL_SECONDS` can be overridden with environment variables
- Set `FFMPEG_PATH` if `ffmpeg` is not on your system `PATH`

## Run

Start the service with:

```bash
python src/main.py
```

On Windows, you can also use:

```bat
scripts\run.bat
```

## Usage

### `POST /api/download`

- **Request type:** `POST`
- **Arguments:** a JSON body with `video_link`, `format`, `quality`, and `folder`
- **Optional arguments:** `name` or `file_name` to override the output filename
- **Batch form:** send a JSON object with a `videos` array
- **What it does:** validates the request, creates a background job, and starts the download worker
- **How it answers:** returns `202 Accepted` with JSON like `{"task_id": "...", "status": "queued"}`

### `GET /api/download/<task_id>`

- **Request type:** `GET`
- **Arguments:** path parameter `task_id`
- **What it does:** returns the current state of a previously queued task
- **How it answers:** returns `200 OK` with JSON containing `task_id` and `status`

### `GET /api/health`

- **Request type:** `GET`
- **Arguments:** none
- **What it does:** reports service health, binding information, task counts, retention settings, and the YouTube client library currently in use
- **How it answers:** returns `200 OK` with JSON containing `status`, `bind`, `port`, `task_counts`, `task_retention_minutes`, `task_cleanup_interval_seconds`, and `youtube_client`

## Project Structure

```text
YoutubeDownloader/
├── deployment/
│   ├── com.service.plist
│   ├── service.service
│   └── startup-windows.vbs
├── resources/
│   └── configuration.json
├── scripts/
│   ├── run.bat
│   ├── run.sh
│   ├── setup.bat
│   └── setup.sh
├── src/
│   └── main.py
├── LICENSE
├── README.md
└── requirements.txt
```

## License

This project is licensed under the terms specified in [LICENSE](LICENSE).