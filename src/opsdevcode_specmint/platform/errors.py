"""Structured platform diagnostics. Expected failures stay data where possible."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opsdevcode_specmint.errors import SpecProblem


@dataclass(frozen=True)
class PlatformProblem(SpecProblem):
    extra: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, object]:
        # Build explicitly: Exception subclasses must stay traceback-assignable.
        body: dict[str, object] = {
            "type": f"about:specmint/{self.code.lower()}",
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "code": self.code,
        }
        if self.extra:
            body.update(self.extra)
        return body


def refuse(
    code: str,
    detail: str,
    *,
    status: int = 422,
    extra: dict[str, Any] | None = None,
) -> PlatformProblem:
    return PlatformProblem(
        status=status,
        code=code,
        title=code.replace("_", " ").title(),
        detail=detail,
        extra=extra,
    )
