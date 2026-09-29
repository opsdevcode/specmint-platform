"""JSON-RPC 2.0 LSP framing over byte streams. Stdio only; no sockets."""

from __future__ import annotations

import json
from typing import IO, Any

_HEADER_END = b"\r\n\r\n"


def encode_message(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


def read_message(stream: IO[bytes]) -> dict[str, Any] | None:
    header = _read_headers(stream)
    if header is None:
        return None
    raw_length = header.get("content-length")
    if raw_length is None:
        raise ValueError("LSP message missing Content-Length; send a framed JSON-RPC body")
    length = int(raw_length)
    body = stream.read(length)
    if len(body) != length:
        return None
    document = json.loads(body.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("LSP message must be a JSON object")
    return document


def write_message(stream: IO[bytes], payload: dict[str, Any]) -> None:
    stream.write(encode_message(payload))
    stream.flush()


def _read_headers(stream: IO[bytes]) -> dict[str, str] | None:
    buffer = bytearray()
    while _HEADER_END not in buffer:
        chunk = stream.read(1)
        if not chunk:
            return None
        buffer.extend(chunk)
        if len(buffer) > 65536:
            raise ValueError("LSP header exceeded 64KiB; send Content-Length then JSON")
    raw = bytes(buffer.split(_HEADER_END, 1)[0])
    headers: dict[str, str] = {}
    for line in raw.split(b"\r\n"):
        if not line:
            continue
        key, _, value = line.decode("ascii").partition(":")
        headers[key.strip().lower()] = value.strip()
    return headers
