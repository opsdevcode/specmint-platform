"""Supplied repository snapshots. Untrusted input; never fetched live."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opsdevcode_specmint.mint.adapters.types import content_digest
from opsdevcode_specmint.mint.catalog import REPO_GITHUB_KIND
from opsdevcode_specmint.mint.errors import coded_error
from opsdevcode_specmint.mint.ir import canonical_json_bytes

SNAPSHOT_SCHEMA = "mint.repository-snapshot/v0"
SNAPSHOT_KIND = "MintRepositorySnapshot"
COMPLETENESS_STATES = frozenset({"complete", "unknown", "unavailable", "unsupported", "redacted"})
OBSERVATION_KEYS = frozenset({"settings", "rules", "security", "files"})
_FORBIDDEN_SUBSTRINGS = (
    "://",
    "github.com",
    "api.github",
    "/users/",
    "/home/",
    "\\",
    "ghp_",
    "gho_",
    "github_pat_",
)


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    path: str
    identity: tuple[str, str]
    provider_kind: str
    settings: dict[str, Any]
    rules: dict[str, Any]
    security: dict[str, Any]
    files: tuple[dict[str, Any], ...]
    completeness: dict[str, str]
    unknown: tuple[str, ...]
    unavailable: tuple[str, ...]
    unsupported: tuple[str, ...]
    redacted: tuple[str, ...]
    digest: str
    document: dict[str, Any]


def load_snapshot_file(path: Path) -> RepositorySnapshot:
    if not path.is_file():
        raise coded_error(
            "MINT_SNAPSHOT",
            f"missing repository snapshot {path}; pass an explicit snapshot JSON path",
        )
    try:
        raw = path.read_text(encoding="utf-8")
        document = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise coded_error(
            "MINT_SNAPSHOT",
            f"malformed repository snapshot {path}; supply canonical JSON",
        ) from exc
    return parse_snapshot(document, source=str(path))


def parse_snapshot(document: object, *, source: str) -> RepositorySnapshot:
    if not isinstance(document, dict):
        raise coded_error(
            "MINT_SNAPSHOT",
            f"malformed repository snapshot {source}; root must be a JSON object",
        )
    extra = sorted(
        set(document)
        - {
            "schema",
            "kind",
            "identity",
            "providerKind",
            "settings",
            "rules",
            "security",
            "files",
            "completeness",
            "unknown",
            "unavailable",
            "unsupported",
            "redacted",
            "digest",
        }
    )
    if extra:
        raise coded_error(
            "MINT_SNAPSHOT",
            f"malformed repository snapshot {source}; remove unknown fields {extra}",
        )
    if document.get("schema") != SNAPSHOT_SCHEMA or document.get("kind") != SNAPSHOT_KIND:
        raise coded_error(
            "MINT_SNAPSHOT",
            f"malformed repository snapshot {source}; set schema {SNAPSHOT_SCHEMA} "
            f"and kind {SNAPSHOT_KIND}",
        )
    _reject_untrusted_strings(document, source=source)
    identity = _identity(document.get("identity"), source=source)
    provider = document.get("providerKind")
    if provider != REPO_GITHUB_KIND:
        raise coded_error(
            "MINT_SNAPSHOT",
            f"malformed repository snapshot {source}; providerKind must be {REPO_GITHUB_KIND}",
        )
    settings = _object_section(document.get("settings", {}), source=source, name="settings")
    rules = _object_section(document.get("rules", {}), source=source, name="rules")
    security = _object_section(document.get("security", {}), source=source, name="security")
    files = _files(document.get("files", []), source=source)
    completeness = _completeness(document.get("completeness"), source=source)
    unknown = _string_list(document.get("unknown", []), source=source, name="unknown")
    unavailable = _string_list(document.get("unavailable", []), source=source, name="unavailable")
    unsupported = _string_list(document.get("unsupported", []), source=source, name="unsupported")
    redacted = _string_list(document.get("redacted", []), source=source, name="redacted")
    canonical = _canonical_body(
        identity=identity,
        provider=provider,
        settings=settings,
        rules=rules,
        security=security,
        files=files,
        completeness=completeness,
        unknown=unknown,
        unavailable=unavailable,
        unsupported=unsupported,
        redacted=redacted,
    )
    digest = content_digest(canonical)
    declared = document.get("digest")
    if declared not in (None, digest):
        raise coded_error(
            "MINT_SNAPSHOT",
            f"malformed repository snapshot {source}; digest must match canonical snapshot bytes",
        )
    return RepositorySnapshot(
        path=source,
        identity=identity,
        provider_kind=provider,
        settings=settings,
        rules=rules,
        security=security,
        files=files,
        completeness=completeness,
        unknown=unknown,
        unavailable=unavailable,
        unsupported=unsupported,
        redacted=redacted,
        digest=digest,
        document={**canonical, "digest": digest, "kind": SNAPSHOT_KIND, "schema": SNAPSHOT_SCHEMA},
    )


def snapshot_canonical_bytes(snapshot: RepositorySnapshot) -> bytes:
    return canonical_json_bytes(snapshot.document)


def bind_snapshots(
    targets: tuple[dict[str, Any], ...],
    snapshots: tuple[Any, ...],
) -> dict[tuple[str, str], RepositorySnapshot]:
    typed: list[RepositorySnapshot] = []
    for item in snapshots:
        if not isinstance(item, RepositorySnapshot):
            raise coded_error(
                "MINT_SNAPSHOT",
                "malformed repository snapshot; pass mint.repository-snapshot/v0 documents",
            )
        typed.append(item)
    repo_targets = tuple(item for item in targets if item.get("kind") == REPO_GITHUB_KIND)
    for target in repo_targets:
        _target_identity(target)
    if repo_targets and not snapshots:
        raise coded_error(
            "MINT_SNAPSHOT",
            "missing repository snapshot; pass --snapshot PATH for each repo.github target",
        )
    seen: dict[tuple[str, str], RepositorySnapshot] = {}
    for item in typed:
        if item.identity in seen:
            raise coded_error(
                "MINT_SNAPSHOT",
                f"duplicate repository snapshot for {item.identity[0]}/{item.identity[1]}; "
                f"{seen[item.identity].path} and {item.path}",
            )
        seen[item.identity] = item
    bound: dict[tuple[str, str], RepositorySnapshot] = {}
    for target in repo_targets:
        identity = _target_identity(target)
        snapshot = seen.get(identity)
        if snapshot is None:
            raise coded_error(
                "MINT_SNAPSHOT",
                f"missing repository snapshot for {identity[0]}/{identity[1]}; "
                "supply a snapshot whose identity matches the target",
            )
        bound[identity] = snapshot
    extra = sorted(set(seen) - set(bound))
    if extra:
        owner, name = extra[0]
        raise coded_error(
            "MINT_SNAPSHOT",
            f"mismatched repository snapshot {owner}/{name}; every snapshot must bind one target",
        )
    return bound


_OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_REPO = re.compile(r"^[A-Za-z0-9._-]+$")


def _target_identity(target: dict[str, Any]) -> tuple[str, str]:
    identity = target.get("identity")
    if not isinstance(identity, dict):
        raise coded_error(
            "MINT_IDENTITY",
            f"invalid identity on target {target.get('id')}; set config owner and name",
        )
    owner = str(identity.get("owner", "")).strip()
    name = str(identity.get("name", "")).strip()
    assert_repository_identity(owner, name)
    return (owner, name)


def assert_repository_identity(owner: str, name: str) -> None:
    if not _OWNER.fullmatch(owner) or not _REPO.fullmatch(name):
        raise coded_error(
            "MINT_IDENTITY",
            f"invalid identity {owner}/{name}; use GitHub owner and repository name only",
        )
    if owner.lower() in {"http", "https"} or "github.com" in f"{owner}/{name}".lower():
        raise coded_error(
            "MINT_IDENTITY",
            f"invalid identity {owner}/{name}; reject URLs, credentials, and paths",
        )
    if "/" in owner or "/" in name or ":" in owner or ":" in name or "@" in owner or "@" in name:
        raise coded_error(
            "MINT_IDENTITY",
            f"invalid identity {owner}/{name}; reject URLs, credentials, and paths",
        )


def _identity(raw: object, *, source: str) -> tuple[str, str]:
    if not isinstance(raw, dict) or set(raw) - {"owner", "name"}:
        raise coded_error(
            "MINT_IDENTITY",
            f"invalid identity in {source}; use owner and name only, not URLs or tokens",
        )
    owner = raw.get("owner")
    name = raw.get("name")
    if not isinstance(owner, str) or not isinstance(name, str):
        raise coded_error(
            "MINT_IDENTITY",
            f"invalid identity in {source}; owner and name must be strings",
        )
    assert_repository_identity(owner, name)
    return (owner, name)


def _object_section(raw: object, *, source: str, name: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise coded_error(
            "MINT_SNAPSHOT",
            f"malformed repository snapshot {source}; {name} must be an object",
        )
    return {str(key): raw[key] for key in sorted(raw, key=str)}


def _files(raw: object, *, source: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(raw, list):
        raise coded_error(
            "MINT_SNAPSHOT",
            f"malformed repository snapshot {source}; files must be an array",
        )
    items: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise coded_error(
                "MINT_SNAPSHOT",
                f"malformed repository snapshot {source}; each file must be an object",
            )
        extra = sorted(set(entry) - {"path", "digest", "mode"})
        if extra:
            raise coded_error(
                "MINT_SNAPSHOT",
                f"malformed repository snapshot {source}; remove file fields {extra}",
            )
        path = entry.get("path")
        digest = entry.get("digest")
        if not isinstance(path, str) or not isinstance(digest, str):
            raise coded_error(
                "MINT_SNAPSHOT",
                f"malformed repository snapshot {source}; file path and digest must be strings",
            )
        item = {"digest": digest, "path": path}
        if "mode" in entry:
            if not isinstance(entry["mode"], str):
                raise coded_error(
                    "MINT_SNAPSHOT",
                    f"malformed repository snapshot {source}; file mode must be a string",
                )
            item["mode"] = entry["mode"]
        items.append(item)
    return tuple(sorted(items, key=lambda item: item["path"]))


def _completeness(raw: object, *, source: str) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise coded_error(
            "MINT_SNAPSHOT",
            f"malformed repository snapshot {source}; completeness must be an object",
        )
    extra = sorted(set(raw) - OBSERVATION_KEYS)
    missing = sorted(OBSERVATION_KEYS - set(raw))
    if extra or missing:
        raise coded_error(
            "MINT_SNAPSHOT",
            "malformed repository snapshot "
            f"{source}; completeness needs {sorted(OBSERVATION_KEYS)}",
        )
    out: dict[str, str] = {}
    for key in sorted(OBSERVATION_KEYS):
        value = raw[key]
        if value not in COMPLETENESS_STATES:
            raise coded_error(
                "MINT_SNAPSHOT",
                f"malformed repository snapshot {source}; completeness.{key} must be "
                f"one of {sorted(COMPLETENESS_STATES)}",
            )
        out[key] = str(value)
    return out


def _string_list(raw: object, *, source: str, name: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        raise coded_error(
            "MINT_SNAPSHOT",
            f"malformed repository snapshot {source}; {name} must be an array of strings",
        )
    return tuple(sorted(str(item) for item in raw))


def _canonical_body(
    *,
    identity: tuple[str, str],
    provider: str,
    settings: dict[str, Any],
    rules: dict[str, Any],
    security: dict[str, Any],
    files: tuple[dict[str, Any], ...],
    completeness: dict[str, str],
    unknown: tuple[str, ...],
    unavailable: tuple[str, ...],
    unsupported: tuple[str, ...],
    redacted: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "completeness": completeness,
        "files": list(files),
        "identity": {"name": identity[1], "owner": identity[0]},
        "kind": SNAPSHOT_KIND,
        "providerKind": provider,
        "redacted": list(redacted),
        "rules": rules,
        "schema": SNAPSHOT_SCHEMA,
        "security": security,
        "settings": settings,
        "unavailable": list(unavailable),
        "unknown": list(unknown),
        "unsupported": list(unsupported),
    }


def _reject_untrusted_strings(document: object, *, source: str) -> None:
    if isinstance(document, dict):
        for key, value in document.items():
            lowered = str(key).lower()
            if lowered in {"token", "password", "secret", "credential", "url", "endpoint"}:
                raise coded_error(
                    "MINT_SNAPSHOT",
                    f"malformed repository snapshot {source}; refuse {key}",
                )
            _reject_untrusted_strings(value, source=source)
        return
    if isinstance(document, list):
        for item in document:
            _reject_untrusted_strings(item, source=source)
        return
    if isinstance(document, str):
        lowered = document.lower()
        for needle in _FORBIDDEN_SUBSTRINGS:
            if needle in lowered:
                raise coded_error(
                    "MINT_SNAPSHOT",
                    f"malformed repository snapshot {source}; refuse host paths, URLs, or tokens",
                )
