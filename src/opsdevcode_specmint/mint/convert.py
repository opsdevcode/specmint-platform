"""Legacy JSON/YAML/Markdown authoring → canonical Mint.

Not a second compiler. Legacy parse → representable automation → format_module
→ existing Mint parser/compiler. MintIR is not a source for Mint.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opsdevcode_specmint.automation import is_automation_document, is_automation_intent
from opsdevcode_specmint.compiler import compile_specification
from opsdevcode_specmint.errors import DocumentParseError, SpecProblem
from opsdevcode_specmint.markdown_spec import parse_markdown_specification
from opsdevcode_specmint.mint.ast import MintModule, MintProgram, SourceSpan
from opsdevcode_specmint.mint.compile import SourceUnit, compile_program
from opsdevcode_specmint.mint.errors import MintError, coded_error
from opsdevcode_specmint.mint.fmt import format_module, format_source
from opsdevcode_specmint.mint.host import project_automation_specification
from opsdevcode_specmint.mint.ir import MintIR, canonical_json_bytes
from opsdevcode_specmint.mint.parser import parse_mint_text
from opsdevcode_specmint.mint.project import (
    LOCK_NAME,
    MANIFEST_NAME,
    discover_manifest,
    load_manifest,
)
from opsdevcode_specmint.parse import (
    content_type_for_path,
    load_source,
    media_type_for_format,
)
from opsdevcode_specmint.pins import COMPILED_INTENT_KIND, SPEC_KIND

REPORT_KIND = "mint.migration-report/v0"
_FRONT_MATTER = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n(.*)\Z", re.DOTALL)
_OTHER_FENCE = re.compile(r"^```(?!specmint$|mint$)[^\n`]+", re.MULTILINE)
_AUTHORING_SUFFIXES = frozenset({".json", ".yaml", ".yml", ".md", ".markdown", ".mint"})
_MACHINE_LOCK_SCHEMA = "mint.lock/v0"
_ALLOWED_DOCUMENT_KEYS = frozenset({"apiVersion", "kind", "metadata", "spec"})
_ALLOWED_METADATA_KEYS = frozenset({"id"})
_ALLOWED_SPEC_KEYS = frozenset(
    {
        "owner",
        "intent",
        "automation",
        "placement",
        "required_evidence",
        "constraints",
        "status",
    }
)
_ALLOWED_AUTOMATION_KEYS = frozenset({"type", "version"})
_ALLOWED_PLACEMENT_KEYS = frozenset({"sandbox"})
_ALLOWED_CONSTRAINT_KEYS = frozenset({"require_authorization", "allow_platform_mutation"})


@dataclass(frozen=True, slots=True)
class ConvertedUnit:
    mint_source: str
    ir: MintIR
    ir_digest: str
    source_digest: str
    mint_digest: str
    format: str
    excluded: tuple[str, ...]
    lossy: tuple[str, ...]
    codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConversionItem:
    source: str
    format: str
    destination: str
    status: str
    source_digest: str = ""
    mint_digest: str = ""
    ir_digest: str = ""
    codes: tuple[str, ...] = ()
    lossy: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    collision: bool = False
    message: str = ""

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "codes": list(self.codes),
            "collision": self.collision,
            "destination": self.destination,
            "excluded": list(self.excluded),
            "format": self.format,
            "irDigest": self.ir_digest,
            "lossy": list(self.lossy),
            "message": self.message,
            "mintDigest": self.mint_digest,
            "source": self.source,
            "sourceDigest": self.source_digest,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class MigrationReport:
    ok: bool
    items: tuple[ConversionItem, ...]
    preview: bool = False
    collisions: tuple[str, ...] = ()
    safety: tuple[str, ...] = ()

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "collisions": list(self.collisions),
            "items": [item.to_canonical_dict() for item in self.items],
            "kind": REPORT_KIND,
            "ok": self.ok,
            "preview": self.preview,
            "safety": list(self.safety),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_canonical_dict())


def convert_error(message: str, *, span: SourceSpan | None = None) -> MintError:
    return coded_error("MINT_CONVERT", message, span=span)


def digest_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def convert_text(
    source: str,
    *,
    format: str,
    unit_id: str = "root",
    logical_source: str = "-",
) -> ConvertedUnit:
    normalized = _normalize_format(format)
    excluded: list[str] = []
    lossy: list[str] = []
    if normalized in {"yaml", "yml"}:
        lossy.append("comments")
        excluded.append("comments")
        document = _load_mapping(source.encode("utf-8"), "yaml")
        module = _module_from_document(document, unit_id=unit_id)
    elif normalized == "json":
        document = _load_mapping(source.encode("utf-8"), "json")
        module = _module_from_document(document, unit_id=unit_id)
    elif normalized in {"markdown", "md"}:
        module, md_excluded, document = _module_from_markdown(source, unit_id=unit_id)
        excluded.extend(md_excluded)
        lossy.extend(md_excluded)
        mint_source = format_module(module)
        return _finish_mint(
            mint_source,
            source_text=source,
            format="markdown",
            unit_id=unit_id,
            excluded=tuple(excluded),
            lossy=tuple(lossy),
            original_document=document,
        )
    elif normalized == "mint":
        formatted = format_source(source, unit_id=unit_id)
        return _finish_mint(
            formatted,
            source_text=source,
            format="mint",
            unit_id=unit_id,
            excluded=(),
            lossy=(),
        )
    else:
        raise convert_error(f"unknown format {format}; set --from to json, yaml, markdown, or mint")
    mint_source = format_module(module)
    return _finish_mint(
        mint_source,
        source_text=source,
        format="markdown"
        if normalized in {"markdown", "md"}
        else normalized.replace("yml", "yaml"),
        unit_id=unit_id,
        excluded=tuple(excluded),
        lossy=tuple(lossy),
        original_document=document,
    )


def convert_path(
    path: Path,
    *,
    format: str | None = None,
    destination: Path | None = None,
    replace: bool = False,
    check: bool = False,
    preview: bool = False,
    write: bool = False,
) -> tuple[ConvertedUnit, ConversionItem]:
    fmt = format or _format_from_path(path)
    text = _read_text(path)
    logical = path.name
    dest = destination if destination is not None else path.with_suffix(".mint")
    unit = convert_text(text, format=fmt, unit_id=path.name, logical_source=logical)
    if write:
        _refuse_overwrite_input(path, dest)
    collision = dest.exists()
    if write and collision and not replace and not check and not preview:
        raise convert_error(
            f"refuse existing destination {dest.name}; pass --replace to replace safely"
        )
    item = ConversionItem(
        source=logical,
        format=unit.format,
        destination=dest.name,
        status="converted",
        source_digest=unit.source_digest,
        mint_digest=unit.mint_digest,
        ir_digest=unit.ir_digest,
        codes=unit.codes,
        lossy=unit.lossy,
        excluded=unit.excluded,
        collision=collision,
    )
    return unit, item


def convert_project(
    start: Path,
    *,
    preview: bool = False,
    replace: bool = False,
) -> tuple[MigrationReport, dict[Path, str]]:
    manifest_path = discover_manifest(start)
    manifest = load_manifest(manifest_path)
    root = manifest.directory.resolve()
    pending: list[tuple[Path, str]] = []
    items: list[ConversionItem] = []
    writes: dict[Path, str] = {}
    collisions: list[str] = []
    safety: list[str] = []
    ok = True
    for path in _inventory_authoring(root):
        logical = _logical_path(root, path)
        fmt = _format_from_path(path)
        try:
            text = _read_text(path)
            classification = _classify_bytes(text.encode("utf-8"), fmt)
            if classification == "machine":
                items.append(
                    ConversionItem(
                        source=logical,
                        format=fmt,
                        destination="",
                        status="skipped-machine",
                        source_digest=digest_text(text),
                        message="machine JSON is not converted",
                    )
                )
                continue
            if classification == "mint-idempotent":
                unit = convert_text(text, format="mint", unit_id=path.name, logical_source=logical)
                dest = path
                items.append(
                    ConversionItem(
                        source=logical,
                        format="mint",
                        destination=logical,
                        status="idempotent",
                        source_digest=unit.source_digest,
                        mint_digest=unit.mint_digest,
                        ir_digest=unit.ir_digest,
                    )
                )
                continue
            dest = path.with_suffix(".mint")
            dest_logical = _logical_path(root, dest) if dest.exists() else _dest_logical(root, dest)
            unit = convert_text(text, format=fmt, unit_id=path.name, logical_source=logical)
            collision = dest.exists()
            if collision:
                collisions.append(dest_logical)
            if dest.exists() and dest.is_symlink():
                safety.append(dest_logical)
                raise convert_error(
                    f"refuse symlink destination {dest_logical}; write a regular file"
                )
            _assert_safe_destination(root, dest)
            if collision and not replace:
                raise convert_error(
                    f"collision at {dest_logical}; pass --replace or choose another destination"
                )
            writes[dest] = unit.mint_source
            pending.append((dest, dest_logical))
            items.append(
                ConversionItem(
                    source=logical,
                    format=unit.format,
                    destination=dest_logical,
                    status="preview" if preview else "converted",
                    source_digest=unit.source_digest,
                    mint_digest=unit.mint_digest,
                    ir_digest=unit.ir_digest,
                    lossy=unit.lossy,
                    excluded=unit.excluded,
                    collision=collision,
                )
            )
        except MintError as exc:
            ok = False
            items.append(
                ConversionItem(
                    source=logical,
                    format=fmt,
                    destination=_dest_logical(root, path.with_suffix(".mint")),
                    status="failed",
                    codes=(exc.diagnostic.code,),
                    message=exc.diagnostic.message,
                )
            )
        except SpecProblem as exc:
            ok = False
            items.append(
                ConversionItem(
                    source=logical,
                    format=fmt,
                    destination=_dest_logical(root, path.with_suffix(".mint")),
                    status="failed",
                    codes=("MINT_CONVERT",),
                    message=exc.detail,
                )
            )
    ordered = tuple(sorted(items, key=lambda item: item.source))
    if not ok or preview:
        writes = {}
    else:
        for dest, _logical in pending:
            if dest in writes:
                _atomic_write_text(dest, writes[dest])
    report = MigrationReport(
        ok=ok,
        items=ordered,
        preview=preview,
        collisions=tuple(sorted(collisions)),
        safety=tuple(sorted(safety)),
    )
    return report, writes


def write_report(path: Path, report: MigrationReport) -> None:
    _assert_report_path(path)
    _atomic_write_bytes(path, report.canonical_bytes())


def _finish_mint(
    mint_source: str,
    *,
    source_text: str,
    format: str,
    unit_id: str,
    excluded: tuple[str, ...],
    lossy: tuple[str, ...],
    original_document: dict[str, Any] | None = None,
) -> ConvertedUnit:
    formatted = format_source(mint_source, unit_id=unit_id)
    if formatted != mint_source:
        raise convert_error(
            "emitted Mint is not stable under mint fmt; report this as a converter bug"
        )
    result = compile_program(root=unit_id, units=(SourceUnit(unit_id, formatted),))
    if not result.ok or result.ir is None or result.digest is None:
        diagnostic = result.diagnostic
        message = diagnostic.message if diagnostic else "generated Mint failed to compile"
        raise convert_error(f"semantic mismatch: {message}")
    again = compile_program(root=unit_id, units=(SourceUnit(unit_id, formatted),))
    if again.digest != result.digest or again.ir is None:
        raise convert_error("semantic mismatch: MintIR digest is not deterministic")
    if original_document is not None:
        _assert_semantic_equivalence(original_document, result.ir)
    elif format == "mint":
        original = compile_program(root=unit_id, units=(SourceUnit(unit_id, source_text),))
        if not original.ok or original.digest != result.digest:
            raise convert_error("semantic mismatch: formatted Mint does not match source MintIR")
    parse_mint_text(formatted, unit_id=unit_id)
    return ConvertedUnit(
        mint_source=formatted,
        ir=result.ir,
        ir_digest=result.digest,
        source_digest=digest_text(source_text),
        mint_digest=digest_text(formatted),
        format=format,
        excluded=excluded,
        lossy=lossy,
    )


def _module_from_markdown(
    source: str, *, unit_id: str
) -> tuple[MintModule, tuple[str, ...], dict[str, Any]]:
    try:
        document, description = parse_markdown_specification(source)
    except DocumentParseError as exc:
        detail = exc.detail
        if "fence" in detail:
            raise convert_error(f"ambiguous markdown: {detail}") from exc
        raise convert_error(f"malformed markdown: {detail}") from exc
    excluded: list[str] = []
    if description.strip():
        excluded.append("markdown-prose")
    if _has_unsupported_fences(source):
        excluded.append("unsupported-fences")
    module = _module_from_document(document, unit_id=unit_id)
    return module, tuple(excluded), document


def _has_unsupported_fences(source: str) -> bool:
    match = _FRONT_MATTER.match(source)
    body = match.group(1) if match else source
    return _OTHER_FENCE.search(body) is not None


def _module_from_document(document: dict[str, Any], *, unit_id: str) -> MintModule:
    kind = document.get("kind")
    if kind == SPEC_KIND:
        raise convert_error(
            "unsupported DeliverySpecification; Mint v0 convert emits automation programs only"
        )
    if is_automation_intent(document) or kind == COMPILED_INTENT_KIND or kind == "MintIR":
        raise convert_error(
            "unrepresentable machine contract; keep JSON for MintIR, plans, intents, and reports"
        )
    if not is_automation_document(document):
        raise convert_error(
            "unsupported document; convert AutomationSpecification json, yaml, or markdown"
        )
    _assert_representable_automation(document)
    spec = document["spec"]
    automation = spec["automation"]
    placement = spec["placement"]
    evidence = spec.get("required_evidence") or []
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        raise convert_error("malformed required_evidence; use a list of strings")
    span = SourceSpan(1, 1, unit_id)
    program = MintProgram(
        edition="v0",
        automation_id=str(document["metadata"]["id"]),
        owner=str(spec["owner"]),
        intent=str(spec["intent"]),
        automation_type=str(automation["type"]),
        automation_version=str(automation["version"]),
        sandbox=str(placement["sandbox"]),
        evidence=tuple(evidence),
        status=str(spec["status"]),
        span=span,
    )
    return MintModule(
        edition="v0",
        unit_id=unit_id,
        namespace="mint.local",
        imports=(),
        consts=(),
        types=(),
        targets=(),
        extensions=(),
        automations=(program,),
        classic=True,
        span=span,
    )


def _assert_representable_automation(document: dict[str, Any]) -> None:
    extra_doc = set(document) - _ALLOWED_DOCUMENT_KEYS
    if extra_doc:
        names = ", ".join(sorted(str(key) for key in extra_doc))
        raise convert_error(f"unrepresentable fields {names}; remove them or keep legacy JSON")
    metadata = document.get("metadata")
    spec = document.get("spec")
    if not isinstance(metadata, dict) or not isinstance(spec, dict):
        raise convert_error("malformed AutomationSpecification; set metadata and spec objects")
    extra_meta = set(metadata) - _ALLOWED_METADATA_KEYS
    if extra_meta:
        names = ", ".join(sorted(str(key) for key in extra_meta))
        raise convert_error(f"unrepresentable metadata {names}")
    extra_spec = set(spec) - _ALLOWED_SPEC_KEYS
    if extra_spec:
        names = ", ".join(sorted(str(key) for key in extra_spec))
        raise convert_error(f"unrepresentable spec fields {names}")
    automation = spec.get("automation")
    placement = spec.get("placement")
    constraints = spec.get("constraints")
    if not isinstance(automation, dict) or not isinstance(placement, dict):
        raise convert_error("malformed automation or placement")
    if set(automation) - _ALLOWED_AUTOMATION_KEYS:
        raise convert_error("unrepresentable automation fields")
    if set(placement) - _ALLOWED_PLACEMENT_KEYS:
        raise convert_error("unrepresentable placement fields")
    if not isinstance(constraints, dict):
        raise convert_error("malformed constraints")
    if set(constraints) - _ALLOWED_CONSTRAINT_KEYS:
        raise convert_error("unrepresentable constraint fields")
    if constraints.get("require_authorization") is not True:
        raise convert_error("unrepresentable constraints; Mint requires authorization")
    if constraints.get("allow_platform_mutation") is not False:
        raise convert_error("unrepresentable constraints; Mint forbids mutation")


def _assert_semantic_equivalence(original: dict[str, Any], ir: MintIR) -> None:
    projected = project_automation_specification(ir)
    closed_original = compile_specification(original)
    closed_mint = compile_specification(projected)
    if closed_original != closed_mint:
        raise convert_error(
            "semantic mismatch: compatibility compile disagrees with generated Mint"
        )
    fields = _semantic_fields(ir)
    expected = {
        "namespace": "mint.local",
        "id": original["metadata"]["id"],
        "owner": original["spec"]["owner"],
        "intent": original["spec"]["intent"],
        "verb": original["spec"]["automation"]["type"],
        "verb_version": original["spec"]["automation"]["version"],
        "sandbox": original["spec"]["placement"]["sandbox"],
        "evidence": tuple(original["spec"].get("required_evidence") or ()),
        "status": original["spec"]["status"],
        "extensions": (),
        "apply_targets": (),
    }
    comparable = {key: value for key, value in fields.items() if key != "edition"}
    if comparable != expected or fields["edition"] not in {"v0", "v1alpha1"}:
        raise convert_error("semantic mismatch: MintIR fields differ from the legacy document")


def _semantic_fields(ir: MintIR) -> dict[str, Any]:
    return {
        "edition": ir.source_edition,
        "namespace": ir.namespace,
        "id": ir.unit_id,
        "owner": ir.owner,
        "intent": ir.statement,
        "verb": ir.verb_type,
        "verb_version": ir.verb_version,
        "sandbox": ir.sandbox,
        "evidence": ir.evidence,
        "status": ir.status,
        "extensions": ir.extensions,
        "apply_targets": tuple(
            item.get("id") for item in ir.targets if item.get("kind") != "sandbox"
        ),
    }


def _load_mapping(raw: bytes, source: str) -> dict[str, Any]:
    media = "application/json" if source == "json" else "application/yaml"
    try:
        loaded = load_source(raw, content_type=media)
    except SpecProblem as exc:
        raise convert_error(f"malformed {source}: {exc.detail}") from exc
    document = loaded.document
    if not isinstance(document, dict):
        raise convert_error(f"malformed {source}: document must be an object")
    return document


def _classify_bytes(raw: bytes, fmt: str) -> str:
    if fmt == "mint":
        return "mint-idempotent"
    if fmt == "markdown":
        return "authoring"
    try:
        document = _load_mapping(raw, "json" if fmt == "json" else "yaml")
    except MintError:
        return "machine"
    kind = document.get("kind")
    schema = document.get("schema")
    if schema == _MACHINE_LOCK_SCHEMA:
        return "machine"
    if kind in {"MintIR", COMPILED_INTENT_KIND} or is_automation_intent(document):
        return "machine"
    if set(document) <= {"root", "units", "extensions"} and "root" in document:
        return "machine"
    if is_automation_document(document) or kind == SPEC_KIND:
        return "authoring"
    return "machine"


def _inventory_authoring(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        directory = Path(dirpath)
        if directory.is_symlink():
            dirnames[:] = []
            continue
        dirnames[:] = sorted(name for name in dirnames if not (directory / name).is_symlink())
        for name in sorted(filenames):
            if name in (LOCK_NAME, MANIFEST_NAME):
                continue
            path = directory / name
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix.lower() not in _AUTHORING_SUFFIXES:
                continue
            try:
                _logical_path(root, path)
            except MintError:
                continue
            found.append(path)
    return found


def _format_from_path(path: Path) -> str:
    if content_type_for_path(path) is None:
        raise convert_error(
            f"unknown format for {path.name}; "
            "set a .mint, .json, .yaml, or .md suffix or pass --from"
        )
    suffix = path.suffix.lower()
    mapping = {
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".md": "markdown",
        ".markdown": "markdown",
        ".mint": "mint",
    }
    fmt = mapping.get(suffix)
    if fmt is None:
        raise convert_error(
            f"unknown format for {path.name}; "
            "set a .mint, .json, .yaml, or .md suffix or pass --from"
        )
    return fmt


def _normalize_format(fmt: str) -> str:
    normalized = fmt.strip().lower()
    if normalized in {"json", "yaml", "yml", "markdown", "md", "mint"}:
        return normalized
    raise convert_error(f"unknown format {fmt}; set --from to json, yaml, markdown, or mint")


def _read_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise convert_error(f"malformed path {path.name}; pass a regular file, not a symlink")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise convert_error(f"malformed input; unable to read {path.name}") from exc


def _refuse_overwrite_input(source: Path, dest: Path) -> None:
    try:
        if source.resolve() == dest.resolve() and source.suffix.lower() != ".mint":
            raise convert_error("never overwrite the input path; pass --output to a .mint file")
    except OSError as exc:
        raise convert_error("unsafe path; unable to resolve input and output") from exc


def _assert_safe_destination(root: Path, dest: Path) -> None:
    if dest.is_absolute() is False and ".." in dest.parts:
        raise convert_error(f"unsafe path {dest.as_posix()}; no parent traversal")
    resolved_root = root.resolve()
    resolved = dest.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise convert_error("unsafe path; destination escapes the project directory") from exc
    parent = dest.parent
    if parent.exists() and (parent.is_symlink() or not parent.is_dir()):
        raise convert_error("unsafe path; refuse symlink or non-directory parents")
    if dest.exists() and dest.is_symlink():
        raise convert_error("refuse symlink destination; write a regular file")


def _logical_path(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved = path if path.is_absolute() else (root / path)
    resolved = resolved.resolve()
    try:
        relative = resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise convert_error("unsafe path; stay inside the mint.toml project") from exc
    if ".." in relative.parts:
        raise convert_error("unsafe path; no parent traversal")
    return relative.as_posix()


def _dest_logical(root: Path, dest: Path) -> str:
    try:
        return _logical_path(root, dest)
    except MintError:
        return dest.name


def _assert_report_path(path: Path) -> None:
    if path.suffix.lower() != ".json":
        raise convert_error("set --report to a .json path; migration reports stay machine JSON")
    if path.is_symlink() or (path.parent.exists() and path.parent.is_symlink()):
        raise convert_error("refuse symlink report path")
    if ".." in path.parts:
        raise convert_error("unsafe path; report must not use parent hops")


def _atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    try:
        tmp.write_bytes(payload)
        os.replace(tmp, path)
    except OSError:
        if tmp.exists():
            tmp.unlink()
        raise


def resolve_input_format(*, path: str, from_format: str | None) -> str:
    if path == "-":
        if not from_format:
            raise convert_error("stdin requires --from json|yaml|markdown|mint; do not sniff stdin")
        return _normalize_format(from_format)
    if from_format:
        try:
            media_type_for_format("markdown" if from_format == "md" else from_format)
        except DocumentParseError as exc:
            raise convert_error(exc.detail) from exc
        return _normalize_format(from_format)
    return _format_from_path(Path(path))
