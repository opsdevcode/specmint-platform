"""FastAPI application for the SpecMint specification compiler and platform API."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from opsdevcode_specmint import __version__
from opsdevcode_specmint.api import (
    compile_document,
    healthz,
    inspect_document,
    readyz,
    validate_document,
)
from opsdevcode_specmint.errors import SpecProblem
from opsdevcode_specmint.observe import AccessLogMiddleware
from opsdevcode_specmint.parse import decode_body, read_capped_stream
from opsdevcode_specmint.pins import DEFAULT_BIND_HOST, DEFAULT_PORT
from opsdevcode_specmint.platform.http import register_platform_routes

app = FastAPI(
    title="OpsDevCode SpecMint",
    version=__version__,
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json",
)
app.add_middleware(AccessLogMiddleware)
register_platform_routes(app)


@app.exception_handler(SpecProblem)
async def spec_problem_handler(_request: Request, exc: SpecProblem) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=exc.as_dict())


@app.get("/healthz")
def get_healthz() -> dict[str, Any]:
    return healthz()


@app.get("/readyz")
def get_readyz() -> JSONResponse:
    status, body = readyz()
    return JSONResponse(status_code=status, content=body)


@app.post("/api/specifications/v1/validate")
async def post_validate(request: Request) -> dict[str, Any]:
    raw = await read_capped_stream(request.headers.get("content-length"), request.stream())
    document = decode_body(raw, request.headers.get("content-type"))
    return validate_document(document)


@app.post("/api/specifications/v1/compile")
async def post_compile(request: Request) -> dict[str, Any]:
    raw = await read_capped_stream(request.headers.get("content-length"), request.stream())
    document = decode_body(raw, request.headers.get("content-type"))
    return compile_document(document)


@app.post("/api/specifications/v1/inspect")
async def post_inspect(request: Request) -> dict[str, Any]:
    raw = await read_capped_stream(request.headers.get("content-length"), request.stream())
    document = decode_body(raw, request.headers.get("content-type"))
    return inspect_document(document)


def _listen_port() -> int:
    raw = os.environ.get("PORT", str(DEFAULT_PORT)).strip()
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError("set PORT to an integer between 1 and 65535") from exc
    if not 1 <= port <= 65535:
        raise ValueError("set PORT to an integer between 1 and 65535")
    return port


def run() -> None:
    import uvicorn

    uvicorn.run(
        "opsdevcode_specmint.main:app",
        host=os.environ.get("BIND_HOST", DEFAULT_BIND_HOST).strip() or DEFAULT_BIND_HOST,
        port=_listen_port(),
        factory=False,
    )


if __name__ == "__main__":
    run()
