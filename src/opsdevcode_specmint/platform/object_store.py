"""Object-storage slice. Fake memory and local directory only; no cloud providers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from opsdevcode_specmint.platform.errors import refuse


@dataclass(frozen=True, slots=True)
class ObjectRef:
    key: str
    digest: str
    size: int
    content_type: str

    def to_canonical_dict(self) -> dict[str, str | int]:
        return {
            "contentType": self.content_type,
            "digest": self.digest,
            "key": self.key,
            "size": self.size,
        }


class ObjectStore(Protocol):
    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> ObjectRef: ...

    def get_bytes(self, key: str) -> bytes | None: ...

    def head(self, key: str) -> ObjectRef | None: ...


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _require_key(key: str) -> None:
    stripped = key.strip()
    if not stripped or stripped.startswith("/") or ".." in stripped.split("/"):
        raise refuse("PLATFORM_OBJECT_STORE", "set object key to a relative path without '..'")


@dataclass
class MemoryObjectStore:
    _blobs: dict[str, tuple[bytes, ObjectRef]] = field(default_factory=dict)

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> ObjectRef:
        _require_key(key)
        ref = ObjectRef(key=key, digest=_digest(data), size=len(data), content_type=content_type)
        self._blobs[key] = (data, ref)
        return ref

    def get_bytes(self, key: str) -> bytes | None:
        item = self._blobs.get(key)
        if item is None:
            return None
        return item[0]

    def head(self, key: str) -> ObjectRef | None:
        item = self._blobs.get(key)
        if item is None:
            return None
        return item[1]


@dataclass
class LocalDirectoryObjectStore:
    root: Path

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> ObjectRef:
        _require_key(key)
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        meta = path.with_suffix(path.suffix + ".meta")
        meta.write_text(f"{content_type}\n{_digest(data)}\n{len(data)}\n", encoding="utf-8")
        return ObjectRef(key=key, digest=_digest(data), size=len(data), content_type=content_type)

    def get_bytes(self, key: str) -> bytes | None:
        path = self.root / key
        if not path.is_file():
            return None
        return path.read_bytes()

    def head(self, key: str) -> ObjectRef | None:
        data = self.get_bytes(key)
        if data is None:
            return None
        meta = (self.root / key).with_suffix((self.root / key).suffix + ".meta")
        content_type = "application/octet-stream"
        if meta.is_file():
            content_type = meta.read_text(encoding="utf-8").splitlines()[0]
        return ObjectRef(key=key, digest=_digest(data), size=len(data), content_type=content_type)
