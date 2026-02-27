# YoutubeDownloader (Flask API)

Lightweight local API service that downloads single YouTube videos as MP4 or MP3, with async job tracking and batch support.

## Table of contents

- [Why this project](#why-this-project)
- [Features](#features)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Installation](#installation)
- [Configuration](#configuration)
- [Run and service modes](#run-and-service-modes)
- [API reference](#api-reference)
- [Usage examples](#usage-examples)
- [Notes and limitations](#notes-and-limitations)
- [Troubleshooting](#troubleshooting)
- [Security](#security)
- [Changelog](#changelog)
- [Developer](#developer)

## Why this project

Most download scripts are one-off and hard to integrate. This service exposes a clean HTTP API that lets apps queue downloads and poll status reliably.

### Client options

Users can interact with this service in several ways:

- **API directly:** Call HTTP endpoints from any language or application
- **[YoutubeDownloader-Client](https://github.com/LorenBll/YoutubeDownloader-Client):** CLI client for easy batch downloads and task management
- **Custom integrations:** Build your own tools using the REST API

## Features

- Async download jobs with task IDs
- MP4 (video) and MP3 (audio) support
- Batch request support via `videos` array
- Strong input validation with helpful error messages
- YouTube URL validation (youtube.com/youtu.be only)
- Playlist URLs rejected (single videos only)
- Permission and disk space error handling
- Health endpoint with queue/runtime metrics
- In-memory task retention with automatic cleanup worker
- Uses `pytubefix` first, falls back to `pytube`
- Background service mode (runs silently without terminal)
- Auto-startup configuration for Windows, Linux, and macOS

## Tech stack

- Python 3.10+
- Flask
- pytubefix / pytube

## Project structure

```text
.
├─ src/
│  └─ main.py                       # Main Flask application
├─ scripts/
│  ├─ run.bat                       # Windows run script
│  └─ run.sh                        # Unix run script
├─ deployment/
│  ├─ startup-windows.vbs           # Windows auto-startup wrapper
│  ├─ youtube-downloader.service    # Linux systemd service file
│  └─ com.youtube-downloader.plist  # macOS launchd configuration
├─ resources/
│  └─ configuration.json            # Service configuration
├─ requirements.txt                 # Python dependencies
├─ LICENSE
└─ README.md
```

## Installation

### Prerequisites

- Python 3.10 or newer
- Windows, macOS, or Linux

### Quick start

1. Clone the repository:
   ```bash
   git clone https://github.com/LorenBll/youtube-downloader.git
   cd youtube-downloader
   ```

2. Make the run script executable (macOS/Linux only):
   ```bash
   chmod +x scripts/run.sh
   ```

3. Run the application:
   - **Windows:**
     ```bash
     scripts\run.bat
     ```
   - **macOS/Linux:**
     ```bash
     ./scripts/run.sh
     ```

By default, the service starts in the background. To see real-time output and debug information, use the `--verbose` flag:
- **Windows:**
  ```bash
  scripts\run.bat --verbose
  ```
- **macOS/Linux:**
  ```bash
  ./scripts/run.sh --verbose
  ```

The run scripts create a virtual environment and install dependencies on first run.

### Manual execution

If you prefer to manage the environment yourself:

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the API:
   ```bash
   python src/main.py
   ```

The API binds to `127.0.0.1:49153` by default.

## Configuration

Configuration is loaded from `resources/configuration.json`. It supports three modes:

- **private:** Local-only service with no authentication
- **unprivate:** Requires API keys for protected endpoints
- **public:** No authentication and intended for LAN access

Example structure:

```json
{
   "defaultMode": "private",
   "private": {"ip": "127.0.0.1", "port": 49153},
   "unprivate": {"ip": "127.0.0.1", "port": 49153, "keylist": ["your-key"]},
   "public": {"ip": "0.0.0.0", "port": 49153}
}
```

Optional environment variables:

- `TASK_RETENTION_MINUTES` (default `30`): How long completed/failed tasks stay in memory
- `TASK_CLEANUP_INTERVAL_SECONDS` (default `60`): Cleanup worker interval
- `FFMPEG_PATH` (optional): Full path to the ffmpeg executable

## Run and service modes

### Background mode

The run scripts start the service in the background without displaying a terminal window.

- **Background mode (default):** Terminal closes after startup
- **Verbose mode:** Use `--verbose` to keep the terminal open

Verify the service is running:

```bash
curl http://127.0.0.1:49153/api/health
```

### Auto-startup configuration

Use the files in `deployment/` to start the service automatically on boot:

- Windows: `deployment/startup-windows.vbs` (Startup folder or Task Scheduler)
- Linux: `deployment/youtube-downloader.service` (systemd)
- macOS: `deployment/com.youtube-downloader.plist` (launchd)

## API reference

### Authentication (unprivate mode only)

Provide the API key in the request body or query string:

- **POST requests:** include `api_key` in the JSON body
- **GET requests:** add `?api_key=<api-key>` to the URL

Example (POST):

```json
{
   "api_key": "your-key",
   "video_link": "https://www.youtube.com/watch?v=...",
   "format": "mp4",
   "quality": "720p",
   "folder": "C:/Downloads",
   "name": "optional-file-name"
}
```

Example (GET):

```
GET /api/download/<task_id>?api_key=your-key
```

### POST `/api/download`

Create a new async download task.

Single-item payload:

```json
{
   "api_key": "your-key",
   "video_link": "https://www.youtube.com/watch?v=...",
   "format": "mp4",
   "quality": "720p",
   "folder": "C:/Downloads",
   "name": "optional-file-name"
}
```

Batch payload:

```json
{
   "api_key": "your-key",
   "videos": [
      {
         "video_link": "https://www.youtube.com/watch?v=...",
         "format": "mp3",
         "quality": "128kbps",
         "folder": "C:/Downloads"
      }
   ]
}
```

Response (`202`):

```json
{
   "task_id": "uuid",
   "status": "queued"
}
```

Batch response (`202`):

```json
{
   "task_id": "uuid",
   "status": "queued",
   "video_count": 1
}
```

Notes:

- `quality` is normalized: mp4 expects values like `720p` (or digits like `720`), mp3 expects `128kbps` (or digits like `128`).
- Playlist URLs are rejected.

### GET `/api/download/<task_id>`

Returns task status (`queued`, `in_progress`, `completed`, `failed`) and result/error payload.

Success response (single item, `completed`):

```json
{
   "task_id": "uuid",
   "status": "completed",
   "result": {
      "name": "My Video",
      "format": "mp4",
      "requested_quality": "720p",
      "actual_quality": "720p",
      "save_path": "C:/Downloads/My Video.mp4"
   }
}
```

Success response (batch, `completed`):

```json
{
   "task_id": "uuid",
   "status": "completed",
   "result": {
      "items": [
         {
            "index": 0,
            "status": "completed",
            "result": {
               "name": "Track",
               "format": "mp3",
               "requested_quality": "128kbps",
               "actual_quality": "128kbps",
               "save_path": "C:/Downloads/Track.mp3"
            }
         }
      ],
      "summary": {
         "total": 1,
         "completed": 1,
         "failed": 0
      }
   }
}
```

Failed response (`failed`):

```json
{
   "task_id": "uuid",
   "status": "failed",
   "error": "Invalid API key."
}
```

### GET `/api/health`

Health report including bind/port, task counts, retention settings, and active YouTube client.

## Notes and limitations

- Playlist URLs are intentionally rejected.
- MP4 uses progressive streams up to 720p. Higher qualities use separate video/audio streams that are merged with ffmpeg.
- Task data is in-memory and cleared on process restart.

### Install ffmpeg

High-quality MP4 downloads (above 720p) require ffmpeg to merge video and audio streams.

**Windows**

1. Download the Release full build from https://www.gyan.dev/ffmpeg/builds/
2. Extract the zip (for example: `C:\ffmpeg`)
3. Add `C:\ffmpeg\bin` to your PATH
4. Open a new terminal and run:
   ```bash
   ffmpeg -version
   ```

**macOS (Homebrew)**

```bash
brew install ffmpeg
ffmpeg -version
```

**Linux (Ubuntu/Debian)**

```bash
sudo apt update
sudo apt install ffmpeg
ffmpeg -version
```

## Troubleshooting

**"Address already in use"**
- Another process is using the configured port
- Update `resources/configuration.json` to use a different port

**"Permission denied"**
- On Linux/macOS, ports below 1024 require root privileges
- Use a port >= 1024 or run with `sudo` if necessary

**"Cannot create or access download folder"**
- The folder does not exist or is not writable
- Ensure the folder exists and your user account has write access
- Check available disk space

**"Cannot write file"**
- Verify the output folder path is valid and accessible
- Check disk space; YouTube videos can require large temporary space
- On Windows, avoid paths over 260 characters

## Usage examples

For comprehensive usage examples including:
- Single and batch downloads
- Python and JavaScript client examples
- cURL commands
- Common use cases and error handling

See the [EXAMPLES.md](EXAMPLES.md) file.

### Quick Example

Download a video:
```bash
curl -X POST http://localhost:49153/api/download \
  -H "Content-Type: application/json" \
  -d '{
    "video_link": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "mp4",
    "quality": "720p",
    "folder": "/Users/username/Downloads"
  }'
```

Check status:
```bash
curl http://localhost:49153/api/download/{task_id}
```

## Security

This service supports three modes with different security characteristics:

- **Private mode** (default): Localhost only, no authentication
- **Unprivate mode**: Network-accessible with API key authentication
- **Public mode**: Network-accessible without authentication (use with caution)

For detailed security considerations, best practices, and production deployment guidelines, see [SECURITY.md](SECURITY.md).

### Security Quick Tips

- Never expose public mode to the internet
- Use strong API keys in unprivate mode
- Deploy with HTTPS (reverse proxy) in production
- Keep dependencies updated
- Monitor for unusual activity

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed history of changes, features, and improvements.

## Developer

Created by [LorenBll](https://github.com/LorenBll)
