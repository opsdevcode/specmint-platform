"""HTTP problem payloads. Operational codes, not policy decisions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpecProblem(Exception):
    status: int
    code: str
    title: str
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "type": f"about:specmint/{self.code.lower()}",
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "code": self.code,
        }


class DocumentParseError(SpecProblem):
    def __init__(self, detail: str) -> None:
        super().__init__(400, "DOCUMENT_PARSE_FAILED", "Document parse failed", detail)


class UnsupportedMediaError(SpecProblem):
    def __init__(self, detail: str) -> None:
        super().__init__(415, "UNSUPPORTED_MEDIA_TYPE", "Unsupported media type", detail)


class DocumentTooLargeError(SpecProblem):
    def __init__(self) -> None:
        super().__init__(
            413,
            "DOCUMENT_TOO_LARGE",
            "Document too large",
            "Specification documents must be 65536 bytes or smaller.",
        )


class CueUnavailableError(SpecProblem):
    def __init__(self, detail: str) -> None:
        super().__init__(503, "CUE_UNAVAILABLE", "CUE engine unavailable", detail)


class SpecInvalidError(SpecProblem):
    def __init__(self, detail: str) -> None:
        super().__init__(422, "SPEC_INVALID", "Specification invalid", detail)


class SpecUnsupportedError(SpecProblem):
    def __init__(self, detail: str) -> None:
        super().__init__(422, "SPEC_UNSUPPORTED", "Specification unsupported", detail)


class CompilationFailureError(SpecProblem):
    def __init__(self, detail: str) -> None:
        super().__init__(422, "COMPILATION_FAILURE", "Compilation failed", detail)
