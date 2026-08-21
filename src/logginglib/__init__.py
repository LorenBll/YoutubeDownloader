"""JSON logging library implementing the shared logging standard.

Logs are stored as JSON files containing a list of events. Each event has
``timestamp``, ``type`` (ERROR/WARN/INFO/DEBUG), ``title``, ``data`` and a
``hash`` computed over ``(timestamp, title, data)`` so entries can be
referenced uniquely by ``(projectName, hash)``.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

_PROJECT_NAME: str | None = None
_DEBUG: bool = False
_LOG_DIR: Path | None = None
_CURRENT_FILE: Path | None = None

_WRITE_LOCK = Lock()
_LOG_TYPES = {"ERROR", "WARN", "INFO", "DEBUG"}
_FILENAME_DATE_RE = re.compile(r"^(\d{2}-\d{2}-\d{4})")
_RETENTION_DAYS = 14


def _project_root() -> Path:
    """Return the project root (parent of the ``src`` package)."""
    return Path(__file__).resolve().parent.parent.parent


def _default_log_dir() -> Path:
    """Return the default log directory (``<project root>/logs``)."""
    return _project_root() / "logs"


def _filename_date(filename: str) -> date | None:
    """Extract the date-only prefix from a log filename (DD-MM-YYYY...)."""
    match = _FILENAME_DATE_RE.match(filename)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%d-%m-%Y").date()
    except ValueError:
        return None


def _prune_expired_logs(log_dir: Path) -> None:
    """Remove log files older than 14 days (dates compared, time ignored)."""
    today = date.today()
    for log_file in log_dir.glob("*.json"):
        file_date = _filename_date(log_file.name)
        if file_date is None:
            try:
                file_date = datetime.fromtimestamp(log_file.stat().st_mtime).date()
            except OSError:
                continue
        if (today - file_date).days > _RETENTION_DAYS:
            try:
                log_file.unlink()
            except OSError:
                pass


def _read_events(log_file: Path) -> list[dict[str, Any]]:
    """Read the current list of events from a log file."""
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            events = json.load(f)
        if isinstance(events, list):
            return events
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _write_events(log_file: Path, events: list[dict[str, Any]]) -> None:
    """Write a list of events to a log file."""
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


def init_logging(
    project_name: str,
    debug: bool = False,
    log_dir: Path | None = None,
) -> None:
    """Initialize logging for the given project.

    Sets the project name, debug flag and log directory, prunes expired logs,
    and opens the current log file ``logs/DD-MM-YYYY_HH.MM.SS.json``.
    """
    global _PROJECT_NAME, _DEBUG, _LOG_DIR, _CURRENT_FILE
    _PROJECT_NAME = project_name
    _DEBUG = debug
    _LOG_DIR = (log_dir or _default_log_dir()).resolve()
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    with _WRITE_LOCK:
        _prune_expired_logs(_LOG_DIR)
        filename = datetime.now().strftime("%d-%m-%Y_%H.%M.%S") + ".json"
        _CURRENT_FILE = _LOG_DIR / filename
        _write_events(_CURRENT_FILE, _read_events(_CURRENT_FILE))


def _compute_hash(timestamp: str, title: str, data: Any) -> str:
    """Compute the event hash over ``(timestamp, title, data)``."""
    canonical = json.dumps(
        [timestamp, title, data], sort_keys=True, default=str, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _log(event_type: str, title: str, data: Any = None) -> None:
    """Append a single event to the current log file (thread-safe)."""
    if _CURRENT_FILE is None:
        return
    if event_type == "DEBUG" and not _DEBUG:
        return
    if event_type not in _LOG_TYPES:
        raise ValueError(f"Invalid log type: {event_type}")

    timestamp = datetime.now(timezone.utc).isoformat()
    entry = {
        "timestamp": timestamp,
        "type": event_type,
        "title": title,
        "data": data,
        "hash": _compute_hash(timestamp, title, data),
    }

    with _WRITE_LOCK:
        events = _read_events(_CURRENT_FILE)
        events.append(entry)
        _write_events(_CURRENT_FILE, events)


def log_error(title: str, data: Any = None) -> None:
    """Log an ERROR event."""
    _log("ERROR", title, data)


def log_warn(title: str, data: Any = None) -> None:
    """Log a WARN event."""
    _log("WARN", title, data)


def log_info(title: str, data: Any = None) -> None:
    """Log an INFO event."""
    _log("INFO", title, data)


def log_debug(title: str, data: Any = None) -> None:
    """Log a DEBUG event (no-op unless ``--debug`` is enabled)."""
    _log("DEBUG", title, data)
