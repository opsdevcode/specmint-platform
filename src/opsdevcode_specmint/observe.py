"""HTTP access logging. Best-effort; never logs request bodies."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("opsdevcode_specmint.access")

REQUEST_ID_HEADER = "x-request-id"
_MAX_REQUEST_ID = 128


def resolve_request_id(raw: str | None) -> str:
    if raw is None:
        return str(uuid.uuid4())
    candidate = raw.strip()
    if (
        1 <= len(candidate) <= _MAX_REQUEST_ID
        and candidate.isascii()
        and all(char.isalnum() or char in "-_" for char in candidate)
    ):
        return candidate
    return str(uuid.uuid4())


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        started = time.perf_counter()
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        duration_ms = int((time.perf_counter() - started) * 1000)
        try:
            logger.info(
                json.dumps(
                    {
                        "duration_ms": duration_ms,
                        "event": "http_request",
                        "method": request.method,
                        "path": request.url.path,
                        "request_id": request_id,
                        "status": response.status_code,
                    },
                    sort_keys=True,
                )
            )
        except Exception:
            logger.exception("access log failed; request still completed")
        return response
