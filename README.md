# YoutubeDownloader (Flask API)

Lightweight local API service to download single YouTube videos as mp4 (progressive) or mp3 (audio-only), with asynchronous job tracking.

## Table of contents

- [Why this project](#why-this-project)
- [Features](#features)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Installation](#installation)
- [Background service mode](#background-service-mode)
- [API reference](#api-reference)
- [Notes and limitations](#notes-and-limitations)
- [Configuration](#configuration)
- [Developer](#developer)

## Why this project

Many download scripts are one-off and hard to integrate with apps. This project exposes a clean HTTP API that lets desktop tools, web frontends, or automation workflows queue downloads and poll status reliably.

### Client options

Users can interact with this service in several ways:

- **API directly:** Call HTTP endpoints from any language or application
- **[YoutubeDownloader-Client](https://github.com/LorenBll/YoutubeDownloader-Client):** Dedicated terminal client for easy command-line batch downloads and task management
- **Custom integrations:** Build your own tools using the REST API

## Features

- Async download jobs with task IDs
- Single-video support for mp4 and mp3
- Batch request support via `videos` array
- Comprehensive input validation with actionable error messages
- YouTube URL format validation (youtube.com/youtu.be only)
- Playlist URL rejection guard (single videos only)
- Disk space and permission error detection with helpful feedback
- Health endpoint with queue/runtime metrics
- In-memory job retention with automatic cleanup worker
- Works with `pytubefix` first, falls back to `pytube`
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
├─ .gitignore                       # Git ignore patterns
├─ requirements.txt                 # Python dependencies
├─ LICENSE
└─ README.md
```

The project follows a clean organizational structure:
- **src/**: Application source code
- **scripts/**: Runtime launch scripts for development and production use
- **deployment/**: System startup configurations for automatic service launching

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

The run scripts will automatically create a virtual environment and install dependencies on first run.

### Manual execution

If you prefer to manage the environment yourself:

1. Create and activate virtual environment:
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

## Background service mode

The run scripts automatically start the service in the background without displaying a terminal window. This allows the web service to run silently in the background while remaining accessible via the HTTP API.

- **Background mode (default):** The terminal closes immediately after startup. The service continues running and listening for API requests.
- **Verbose mode:** Use the `--verbose` flag to keep the terminal open and observe real-time server output and debug information.

You can query the `/api/health` endpoint to verify the service is running, or check process listings (Task Manager on Windows, or `ps` on macOS/Linux).

### Auto-startup configuration

To have the service start automatically when your system boots, configure the appropriate startup mechanism for your operating system:

#### Windows

**Method 1: Startup Folder (User-level)**

1. Open the startup folder:
   - Press `Win+R`
   - Type `shell:startup`
   - Press Enter

2. Copy `deployment/startup-windows.vbs` to this folder

3. The service will start automatically when you log in

**Method 2: Task Scheduler (System-level)**

1. Open Task Scheduler (`taskschd.msc`)

2. Create a new task:
   - **General tab:**
     - Name: YoutubeDownloader API
     - Run whether user is logged on or not
     - Run with highest privileges

   - **Triggers tab:**
     - New trigger: At startup
     - Delay task for: 30 seconds (recommended)

   - **Actions tab:**
     - Action: Start a program
     - Program/script: `wscript.exe`
     - Arguments: `"C:\path\to\youtube-downloader\deployment\startup-windows.vbs"`
     - Start in: (leave empty)

   - **Conditions tab:**
     - Uncheck "Start only if on AC power" (laptops)

3. Save the task

#### Linux (systemd)

1. Edit `deployment/youtube-downloader.service`:
   - Replace `YOUR_USERNAME` with your actual username
   - Replace `/path/to/youtube-downloader` with the full path to the project directory

2. Copy the service file:
   ```bash
   sudo cp deployment/youtube-downloader.service /etc/systemd/system/
   ```

3. Reload systemd:
   ```bash
   sudo systemctl daemon-reload
   ```

4. Enable the service to start at boot:
   ```bash
   sudo systemctl enable youtube-downloader
   ```

5. Start the service now:
   ```bash
   sudo systemctl start youtube-downloader
   ```

6. Check status:
   ```bash
   sudo systemctl status youtube-downloader
   ```

7. View logs:
   ```bash
   sudo journalctl -u youtube-downloader -f
   ```

To uninstall:
```bash
sudo systemctl stop youtube-downloader
sudo systemctl disable youtube-downloader
sudo rm /etc/systemd/system/youtube-downloader.service
sudo systemctl daemon-reload
```

#### macOS (launchd)

1. Edit `deployment/com.youtube-downloader.plist`:
   - Replace all instances of `/path/to/youtube-downloader` with the full path to the project directory

2. Copy the plist file to the LaunchAgents directory:
   ```bash
   cp deployment/com.youtube-downloader.plist ~/Library/LaunchAgents/
   ```

3. Load the service:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.youtube-downloader.plist
   ```

4. The service will start automatically on login and system restart

5. Check if it's running:
   ```bash
   launchctl list | grep youtube-downloader
   ```

6. View logs:
   ```bash
   tail -f /tmp/youtube-downloader.log
   tail -f /tmp/youtube-downloader-error.log
   ```

To uninstall:
```bash
launchctl unload ~/Library/LaunchAgents/com.youtube-downloader.plist
rm ~/Library/LaunchAgents/com.youtube-downloader.plist
```

#### Verification

After setting up auto-startup, verify the service is running:

1. Reboot your system

2. Check if the service is accessible:
   ```bash
   curl http://127.0.0.1:49153/api/health
   ```

3. You should receive a JSON response with `"status": "ok"`

#### Troubleshooting

**Windows:**
- Check Windows Event Viewer for errors
- Ensure Python and dependencies are installed system-wide or paths are correct
- Verify the working directory in the VBS script or Task Scheduler

**Linux:**
- Check service status: `sudo systemctl status youtube-downloader`
- View detailed logs: `sudo journalctl -u youtube-downloader -n 100`
- Verify file permissions and paths
- Ensure virtual environment is activated correctly

**macOS:**
- Check launchd status: `launchctl list | grep youtube-downloader`
- View logs at `/tmp/youtube-downloader.log` and `/tmp/youtube-downloader-error.log`
- Verify paths are absolute and correct
- Check permissions on the plist file

**Security note:** For production deployments, consider running the service as a dedicated system user with limited permissions. Network access is already restricted to localhost (127.0.0.1) by default.

## API reference

### POST `/api/download`

Create a new async download task.

Single-item payload:

```json
{
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
- In unprivate mode, add an API key header: `Authorization: Bearer <api-key>` or `X-API-Key: <api-key>`.

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

### GET `/api/health`

Health report including bind/port, task counts, retention settings, and active YouTube client.

## Notes and limitations

- Playlist URLs are intentionally rejected.
- mp4 uses progressive streams up to 720p. Higher qualities use separate video/audio streams that are merged with ffmpeg.
- Task data is in-memory and cleared on process restart.

### Install ffmpeg

High-quality mp4 downloads (above 720p) require ffmpeg to merge video and audio streams.

**Windows**

1. Download the “Release full” build from https://www.gyan.dev/ffmpeg/builds/
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

## Configuration

Optional environment variables:

- `TASK_RETENTION_MINUTES` (default `30`) - Completed/failed task retention time in minutes. Invalid values fall back to default.
- `TASK_CLEANUP_INTERVAL_SECONDS` (default `60`) - Background cleanup worker interval in seconds. Invalid values fall back to default.
- `FFMPEG_PATH` (optional) - Full path to the ffmpeg executable when it is not available on PATH.

### Common startup errors

**"Address already in use" on port 8000:**
- Another instance is running, or port 8000 is in use by another service
- Stop the conflicting process or change the code to use a different port

**"Permission denied" error:**
- On Linux/macOS, ports below 1024 require root privileges
- Use a port >= 1024 or run with `sudo` if necessary

**"Cannot create or access download folder" errors:**
- The specified download folder doesn't have write permissions
- Ensure the folder exists and your user account has write access
- Check available disk space; downloads may fail if disk is full

**Download fails with "Cannot write file" error:**
- Verify the output folder path is valid and accessible
- Check disk space: YouTube videos require significant temporary and final space
- On Windows, ensure the path doesn't exceed 260 characters or contains invalid characters

## Developer

Created by [LorenBll](https://github.com/LorenBll)
