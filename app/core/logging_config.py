"""
Structured JSON logging with per-request trace IDs.

Every log line in production carries a request_id field so any
single request can be traced end-to-end across all log lines.
This is standard practice in financial systems for incident investigation.
"""
import json
import logging
import uuid
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON for log aggregation systems."""

    def format(self, record: logging.LogRecord) -> str:
        log = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge any extra fields attached to the record
        for key, value in record.__dict__.items():
            if key not in (
                "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "name",
                "message", "taskName",
            ):
                log[key] = value

        return json.dumps(log)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Injects a unique request_id into every request.

    The ID is:
    - Returned in the X-Request-ID response header (for client-side tracing)
    - Attached to every log record created during the request lifecycle
    """

    async def dispatch(self, request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Attach request_id to all log records created during this request
        old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            record.request_id = request_id
            return record

        logging.setLogRecordFactory(record_factory)

        try:
            response = await call_next(request)
        finally:
            logging.setLogRecordFactory(old_factory)

        response.headers["X-Request-ID"] = request_id
        return response


def configure_logging() -> None:
    """
    Sets up JSON structured logging for the entire application.
    Call once at startup in main.py.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Quieten noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
