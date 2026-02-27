# Changelog

All notable changes to YoutubeDownloader will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Enhanced SECURITY.md with comprehensive operational security guidelines
- Added production deployment checklist
- Added service mode security documentation

### Added
- CHANGELOG.md for tracking project changes
- EXAMPLES.md with usage examples and API documentation

## [1.0.0] - Initial Release

### Features
- Flask-based REST API for YouTube video/audio downloads
- Three service modes: private, unprivate, and public
- API key authentication for unprivate mode
- Asynchronous task processing with background workers
- Support for MP4 (video) and MP3 (audio) downloads
- Quality selection (720p, 1080p, etc. for video; 128kbps, 192kbps, etc. for audio)
- Batch download support via `videos` array
- In-memory task queue with automatic cleanup
- Progressive and adaptive stream support
- FFmpeg integration for high-quality (>720p) video merging
- Task status tracking (queued → in_progress → completed/failed)
- Health monitoring endpoint

### API Endpoints
- `POST /api/download` - Create new download task
- `GET /api/download/{task_id}` - Check download status
- `GET /api/health` - Service health check

### Platform Support
- Windows (setup.bat, run.bat, startup VBS script)
- macOS (setup.sh, run.sh, launchd plist)
- Linux (setup.sh, run.sh, systemd service)

### Dependencies
- Flask 3.1.3
- pytube 15.0.0
- pytubefix (fallback)
- Python 3.10+

### Documentation
- Comprehensive README with installation and usage
- API reference documentation
- Configuration guide for three service modes
- Deployment instructions for all platforms
- Security policy and best practices
- License (see LICENSE file)

### Architecture
- Thread-safe in-memory task storage
- Background cleanup worker for old tasks
- Dynamic YouTube client detection (pytubefix/pytube)
- Configurable task retention (default 30 minutes)
- Automatic virtual environment setup in scripts

---

## Development History

YoutubeDownloader was created to provide a clean HTTP API for YouTube downloads
that can be integrated into other applications. It addresses the need for:

- Reliable async job tracking
- Multi-quality support
- Batch processing
- Clean REST API design
- Cross-platform compatibility
- Easy deployment

### Design Principles

1. **Simplicity:** Easy to install, configure, and use
2. **Reliability:** Robust error handling and task tracking
3. **Flexibility:** Three modes for different security needs
4. **Maintainability:** Well-documented, modular code
5. **Cross-platform:** Works on Windows, macOS, and Linux

### Why This Exists

Most YouTube download tools are:
- Command-line only
- Single-shot scripts
- Hard to integrate
- Lack task tracking
- No API interface

YoutubeDownloader solves these problems with a production-ready REST API.
