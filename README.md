# YoutubeDownloader

YoutubeDownloader is a local YouTube download service. It solves the problem of queuing single-video or batch downloads and returning the downloaded media in MP4 or MP3 form through an HTTP API.

## About
YoutubeDownloader is scoped to request validation, background download jobs, and file delivery on the local machine. The service binds to `127.0.0.1` on port `49156`, keeps task state in memory, and uses a cleanup thread to remove finished jobs after a retention period.

## Setup
1. Install the Python dependencies with `pip install -r requirements.txt`.
2. Install `ffmpeg` if you want to merge adaptive MP4 streams above 720p.
3. Review `resources/configuration.json` if you want to change the port.

## Run
1. Windows: run `scripts\run.bat`.
2. Unix-like systems: run `bash scripts/run.sh`.
3. Manual: run `python src/main.py` from the project root.

## API Endpoints
- `POST /api/download` - Queue a single video download or a batch download.
- `GET /api/task/<task_id>` - Check the status or result of a queued download task.
- `GET /api/health` - Return service health and the active YouTube client.

## License
- [LICENSE](LICENSE)

## Author
- [LorenBll](https://github.com/LorenBll)