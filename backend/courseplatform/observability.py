import contextvars
import json
import logging
import sys
import time
import uuid
from typing import Any


request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    "courseplatform_request_id", default=""
)


class JsonFormatter(logging.Formatter):
    """Emit machine-readable logs without serializing request bodies or secrets."""

    _reserved = set(logging.LogRecord(None, 0, "", 0, "", (), None).__dict__)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
        }
        request_id = getattr(record, "request_id", "") or request_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key in self._reserved or key in {"message", "asctime", "event", "request_id"}:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                payload[key] = value
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if any(getattr(handler, "_courseplatform_json", False) for handler in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._courseplatform_json = True  # type: ignore[attr-defined]
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Third-party access logs may include full URLs or provider details. The
    # application emits its own path-only HTTP event, so keep these at warning.
    for logger_name in ("httpx", "httpcore", "urllib3", "multipart", "psycopg"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def normalized_request_id(value: str | None) -> str:
    candidate = (value or "").strip()
    if candidate and len(candidate) <= 64 and all(char.isalnum() or char in "-_." for char in candidate):
        return candidate
    return uuid.uuid4().hex


def monotonic_milliseconds(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))
