# Security Policy

## Supported Versions

Only the latest released version receives security updates.

| Version | Supported |
| ------- | --------- |
| Latest  | Yes       |

## Reporting a Vulnerability

If you believe you have found a security issue in YoutubeDownloader, please report it privately to the maintainers rather than opening a public issue.

YoutubeDownloader is a local YouTube download service that involves:
- **YouTube API interaction** — downloading video and audio streams via pytubefix or pytube
- **File output handling** — writing downloaded media files to user-specified directories
- **FFmpeg subprocess execution** — merging adaptive streams above 720p using an external ffmpeg binary
- **Path validation** — enforcing allowlist and blacklist policies for output directories
- **Background task processing** — queuing and cleaning up download jobs

Include as much detail as possible, such as:
- A clear description of the issue and the affected component or feature
- Steps to reproduce the problem
- Any relevant logs, screenshots, or proof of concept code
- The potential impact and how severe you believe it is

If the report involves credentials or secrets, redact sensitive values before sharing.

## What To Expect

After a report is received:

1. The issue will be reviewed and triaged.
2. You may be contacted for clarification or additional details.
3. A fix may be developed and validated before public disclosure.
4. The reporter may be credited unless they prefer to remain anonymous.

## Security Guidelines

This project is intended to follow basic security hygiene:

- **Localhost binding** — The service binds to `127.0.0.1:49156` and rejects non-local requests. Do not change the bind address to a non-loopback interface.
- **Output path validation** — All download destination folders are validated against the allowlist and blacklist policy. Configure these lists carefully; an empty allowlist permits all paths on the system.
- **Filename sanitization** — User-supplied file names are sanitized to remove dangerous filesystem characters. Empty or whitespace-only names are rejected.
- **Third-party library risks** — pytubefix and pytube handle network requests to YouTube and may introduce upstream vulnerabilities. The optional ffmpeg binary is executed as a subprocess — ensure it is from a trusted source.
- **Playlist rejection** — YouTube playlist URLs are detected and rejected at the API layer.
- **Background task cleanup** — Completed and failed download tasks are automatically removed after a configurable retention period to prevent memory exhaustion.
- **Secrets management** — No API keys or authentication tokens are required for the download API. Keep configuration files local and exclude them from version control.
- **Least privilege** — Run the service with the minimum filesystem permissions necessary for its configured output directories.
- **Treat all externally supplied input as untrusted** and validate it before use. The API validates URLs, output paths, and configuration values across all endpoints.

## Disclosure Notes

Do not publicly disclose an unpatched vulnerability until maintainers have had reasonable time to investigate and respond. If a coordinated disclosure timeline is needed, it can be discussed during the report process.
