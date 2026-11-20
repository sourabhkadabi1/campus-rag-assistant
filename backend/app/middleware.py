"""
FastAPI middleware and logging setup.

Phase 6: Adds per-request traceability (X-Request-ID) and
cloud-aggregator-friendly structured JSON logging.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


# ╔════════════════════════════════════════════════════════════════╗
# ║  Request ID Middleware                                        ║
# ╚════════════════════════════════════════════════════════════════╝


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Inject a unique ``X-Request-ID`` into every request and response.

    If the client already supplies one it is reused; otherwise a new
    UUID-hex is generated.  The ID is stored in ``request.state.request_id``
    so that loggers and downstream code can reference it.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id

        start = time.time()
        try:
            response = await call_next(request)
        except Exception as exc:
            logging.getLogger("app.middleware").exception("Unhandled error processing %s %s: %s", request.method, request.url.path, exc)
            from starlette.responses import JSONResponse
            response = JSONResponse(
                {"detail": f"Internal server error: {exc}"},
                status_code=500,
            )
        duration_ms = int((time.time() - start) * 1000)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        # Structured access log (skips /health to reduce noise)
        if request.url.path != "/health":
            logging.getLogger("app.access").info(
                "%s %s %s %dms",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
        return response


# ╔════════════════════════════════════════════════════════════════╗
# ║  Structured JSON Log Formatter                                ║
# ╚════════════════════════════════════════════════════════════════╝


class StructuredJsonFormatter(logging.Formatter):
    """
    Emit log records as single-line JSON objects.

    Designed for log aggregators (Render, Fly.io, Datadog, etc.) that
    parse structured JSON logs automatically.
    """

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include extras set by middleware or application code
        for key in ("request_id", "method", "path", "status", "duration_ms"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, default=str)


# ╔════════════════════════════════════════════════════════════════╗
# ║  Logging Setup                                                ║
# ╚════════════════════════════════════════════════════════════════╝


def setup_logging(*, json_format: bool = False, level: str = "INFO") -> None:
    """
    Configure the root logger.

    Args:
        json_format: When True, all log output is single-line JSON
                     (suitable for cloud log aggregators).
        level: Minimum log level string (DEBUG, INFO, WARNING, …).
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicate output
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    if json_format:
        handler.setFormatter(StructuredJsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
            )
        )
    root.addHandler(handler)
