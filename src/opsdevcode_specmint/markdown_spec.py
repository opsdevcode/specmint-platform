"""Structured Markdown frontend. Prose is never executable semantics."""

from __future__ import annotations

import re
from typing import Any, Final

from opsdevcode_specmint.errors import DocumentParseError
from opsdevcode_specmint.mint.lower import load_mint_document
from opsdevcode_specmint.pins import (
    AUTOMATION_API_VERSION,
    AUTOMATION_SPEC_KIND,
    SPEC_API_VERSION,
    SPEC_KIND,
)
from opsdevcode_specmint.strict_load import load_strict_yaml

_FRONT_MATTER: Final = re.compile(r"\A---\r?\n(.*?\r?\n)---\r?\n(.*)\Z", re.DOTALL)
_FENCE: Final = re.compile(r"^```([^\n`]*)\r?\n(.*?)^```[ \t]*\r?$", re.MULTILINE | re.DOTALL)
_IDENTITY_KEYS: Final = frozenset({"apiVersion", "kind", "metadata"})


def parse_markdown_specification(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONT_MATTER.match(text)
    if match is None:
        raise DocumentParseError(
            "Markdown specifications require YAML front matter between --- delimiters."
        )
    front_raw, body = match.group(1), match.group(2)
    body_line_offset = text[: match.start(2)].count("\n")
    try:
        front = load_strict_yaml(front_raw)
    except DocumentParseError as exc:
        raise DocumentParseError(f"Malformed front matter: {exc.detail}") from exc
    if not isinstance(front, dict):
        raise DocumentParseError("Front matter must be a YAML object.")
    extra = set(front) - _IDENTITY_KEYS
    if extra:
        names = ", ".join(sorted(str(key) for key in extra))
        raise DocumentParseError(
            f"Front matter may only contain apiVersion, kind, and metadata; remove {names}."
        )
    delivery = front.get("apiVersion") == SPEC_API_VERSION and front.get("kind") == SPEC_KIND
    automation = (
        front.get("apiVersion") == AUTOMATION_API_VERSION
        and front.get("kind") == AUTOMATION_SPEC_KIND
    )
    if not delivery and not automation:
        raise DocumentParseError(
            "Front matter must declare DeliverySpecification specs.opsdevcode.io/v1alpha1 "
            "or AutomationSpecification automations.opsdevcode.io/v1alpha1."
        )
    metadata = front.get("metadata")
    if not isinstance(metadata, dict):
        raise DocumentParseError("Front matter metadata must be an object.")
    fences = _semantic_fences(body, body_line_offset=body_line_offset)
    if not fences:
        raise DocumentParseError(
            "Markdown specifications require exactly one specmint or mint fence."
        )
    if len(fences) > 1:
        lines = ", ".join(str(line) for line, _, _ in fences)
        raise DocumentParseError(
            "Markdown specifications allow one specmint or mint fence; "
            f"found {len(fences)} at lines {lines}."
        )
    fence_line, language, fence_text = fences[0]
    if language == "mint":
        document = _document_from_mint_fence(
            fence_text,
            fence_line=fence_line,
            front=front,
            metadata=metadata,
            automation=automation,
        )
        return document, body.strip()
    document = _document_from_specmint_fence(
        fence_text,
        fence_line=fence_line,
        front=front,
        metadata=metadata,
    )
    return document, body.strip()


def _document_from_mint_fence(
    fence_text: str,
    *,
    fence_line: int,
    front: dict[str, Any],
    metadata: dict[str, Any],
    automation: bool,
) -> dict[str, Any]:
    if not automation:
        raise DocumentParseError(
            f"mint fence at line {fence_line} requires AutomationSpecification "
            "automations.opsdevcode.io/v1alpha1 front matter."
        )
    try:
        document = load_mint_document(fence_text)
    except DocumentParseError as exc:
        raise DocumentParseError(f"mint fence at line {fence_line}: {exc.detail}") from exc
    front_id = metadata.get("id")
    mint_id = document["metadata"]["id"]
    if front_id != mint_id:
        raise DocumentParseError(
            f"mint fence at line {fence_line}: set metadata.id to {mint_id} "
            f"to match the automation name (front matter has {front_id!r})."
        )
    if document["apiVersion"] != front["apiVersion"] or document["kind"] != front["kind"]:
        raise DocumentParseError(
            f"mint fence at line {fence_line} must match front-matter apiVersion and kind."
        )
    return document


def _document_from_specmint_fence(
    fence_text: str,
    *,
    fence_line: int,
    front: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    try:
        spec = load_strict_yaml(fence_text)
    except DocumentParseError as exc:
        raise DocumentParseError(f"specmint fence at line {fence_line}: {exc.detail}") from exc
    if not isinstance(spec, dict):
        raise DocumentParseError(f"specmint fence at line {fence_line} must be a YAML object.")
    if "apiVersion" in spec or "kind" in spec or "spec" in spec:
        raise DocumentParseError(
            f"specmint fence at line {fence_line} must be the spec object, not a nested document."
        )
    return {
        "apiVersion": front["apiVersion"],
        "kind": front["kind"],
        "metadata": metadata,
        "spec": spec,
    }


def _semantic_fences(body: str, *, body_line_offset: int) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    for match in _FENCE.finditer(body):
        info = match.group(1).strip()
        language = info.split()[0] if info else ""
        if language not in {"specmint", "mint"}:
            continue
        if info != language:
            raise DocumentParseError(
                f"{language} fences must use language {language} with no extra tokens."
            )
        line = body_line_offset + body[: match.start()].count("\n") + 1
        found.append((line, language, match.group(2)))
    return found
