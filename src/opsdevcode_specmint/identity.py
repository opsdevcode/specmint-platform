"""Specification revision identity. Independent of policy artifact identity."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def revision_digest(compiled: dict[str, Any]) -> str:
    canonical = json.dumps(compiled, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
