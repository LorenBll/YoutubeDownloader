# YoutubeDownloader

REST API for downloading YouTube videos or audio on a local machine. The server accepts single-video or batch requests, queues each download in the background, and exposes task status through polling endpoints.

## Table of Contents

- [About](#about)
- [Features](#features)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Usage](#usage)
- [Tech Stack](#tech-stack)
- [License](#license)

## About

This project provides a small Flask service that downloads YouTube media to a folder you choose. It supports `mp4` and `mp3`, handles queued background jobs, and can be run in private, unprivate, or public mode depending on `resources/configuration.json`.

## Features

- **REST API:** Simple HTTP interface for queueing downloads and checking task status
- **Single or Batch Downloads:** Submit one video at a time or send a `videos` array
- **Format Support:** Download `mp4` video or `mp3` audio
- **Quality Selection:** Choose video resolution or audio bitrate
- **Background Jobs:** Requests return a task id immediately while downloads continue in worker threads
- **Task Retention:** Completed and failed jobs are kept temporarily and cleaned up automatically
- **Optional API Key Protection:** `unprivate` mode requires an `api_key` in the JSON body or query string

## Project Structure

```text
YoutubeDownloader/
├── deployment/
│   ├── com.service.plist        # macOS launch agent example
│   ├── service.service          # systemd service example
│   └── startup-windows.vbs      # Windows startup helper
├── resources/
│   └── configuration.json       # Host, port, mode, and API key settings
├── scripts/
│   ├── run.bat                  # Windows launcher
│   ├── run.sh                   # macOS/Linux launcher
│   ├── setup.bat                # Windows setup script
│   └── setup.sh                 # macOS/Linux setup script
├── src/
│   └── main.py                  # Flask application entry point
├── LICENSE
├── README.md
└── requirements.txt
```

The code is intentionally compact:
- `src/main.py` contains configuration loading, request validation, background workers, and all API routes.
- `resources/configuration.json` controls the bind address, port, and service mode.
- `scripts/` provides the quickest way to create the virtual environment, install dependencies, and start the server.

## Installation

### Prerequisites

- Python 3.10 or newer
- `ffmpeg` if you want high-quality `mp4` downloads above 720p
- Internet access for installing Python packages and contacting YouTube

### Quick Start

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd YoutubeDownloader
   ```

2. **Configure the service:**
   Edit [resources/configuration.json](resources/configuration.json) and set the mode, IP, port, and API keys as needed.

3. **Install dependencies:**
   - Windows: run [scripts/setup.bat](scripts/setup.bat)
   - macOS/Linux: run [scripts/setup.sh](scripts/setup.sh)

4. **Start the server:**
   - Windows: run [scripts/run.bat](scripts/run.bat)
   - macOS/Linux: run [scripts/run.sh](scripts/run.sh)

### Manual Execution

1. **Create and activate a virtual environment**
2. **Install dependencies:**
   ```bash
   python -m pip install -r requirements.txt
   ```
3. **Run the application:**
   ```bash
   python src/main.py
   ```

### Configuration Notes

- `defaultMode` can be `private`, `unprivate`, or `public`.
- In `unprivate` mode, set `keylist` to the allowed API keys.
- `TASK_RETENTION_MINUTES` and `TASK_CLEANUP_INTERVAL_SECONDS` can be overridden with environment variables.
- Set `FFMPEG_PATH` if `ffmpeg` is not on your system `PATH`.

## Usage

The API exposes three endpoints.

### `POST /api/download`

- **Request type:** `POST`
- **Arguments:** JSON body with the required fields `video_link`, `format`, `quality`, and `folder`.
- **Optional arguments:** `name` or `file_name` to override the output filename. In `unprivate` mode, `api_key` must be supplied in the JSON body or as a query string parameter.
- **Batch form:** send a JSON object with a `videos` array, where each item has the same fields as a single download request.
- **What it does:** validates the request, creates a background job, and starts the download worker.
- **How it answers:** returns `202 Accepted` with JSON like `{"task_id": "...", "status": "queued"}`. Batch requests also include `video_count`. Validation errors return `400`. If the worker thread cannot start, the API returns `500` with an error message and the task id.

### `GET /api/download/<task_id>`

- **Request type:** `GET`
- **Arguments:** path parameter `task_id`. In `unprivate` mode, the same `api_key` rule applies.
- **What it does:** returns the current state of a previously queued task.
- **How it answers:** returns `200 OK` with JSON containing `task_id` and `status`. If the task finished successfully, the response includes `result`. If it failed, the response includes `error`. If the task id does not exist, the API returns `404` with `{"error": "Task not found."}`.

### `GET /api/health`

- **Request type:** `GET`
- **Arguments:** none
- **What it does:** reports service health, binding information, task counts, retention settings, and the YouTube client library currently in use.
- **How it answers:** returns `200 OK` with JSON containing `status`, `mode`, `bind`, `port`, `task_counts`, `task_retention_minutes`, `task_cleanup_interval_seconds`, and `youtube_client`.

### Request Rules

- `format` must be either `mp4` or `mp3`.
- `video_link` must be a valid YouTube URL.
- Playlists are rejected.
- For `mp4`, `quality` should look like `720p` or `1080p`.
- For `mp3`, `quality` should look like an audio bitrate such as `128kbps`.
- Downloads are saved to the folder provided in `folder`, and the folder is created if it does not already exist.

## Tech Stack

- **Language:** Python 3.10+
- **Web Framework:** Flask
- **YouTube Clients:** `pytubefix` or `pytube`
- **Media Processing:** `ffmpeg` for merging separate video and audio streams when needed
- **Concurrency:** Standard library threads
- **Configuration:** JSON file plus optional environment variables

## License

This project is licensed under the terms specified in [LICENSE](LICENSE).