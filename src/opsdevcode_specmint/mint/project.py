"""Deterministic Mint project manifest and lockfile. Offline; no registries."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opsdevcode_specmint.mint.catalog import sorted_catalog_ids
from opsdevcode_specmint.mint.compile import SourceUnit, compile_program
from opsdevcode_specmint.mint.errors import MintError, coded_error
from opsdevcode_specmint.mint.inputs import DeclaredProgram, extension_from_dict
from opsdevcode_specmint.mint.ir import MintIR, canonical_json_bytes

PROJECT_SCHEMA = "mint.project/v0"
LOCK_SCHEMA = "mint.lock/v0"
MANIFEST_NAME = "mint.toml"
LOCK_NAME = "mint.lock"
_NAME = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_EDITIONS = frozenset({"v0", "v1alpha1"})
_CREDENTIAL_KEYS = frozenset(
    {
        "access_key",
        "credential",
        "password",
        "private_key",
        "secret",
        "token",
    }
)
_STARTER = """\
mint v0

automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent "Ensure a sandbox marker exists after an authorized plan"
  use local.sandbox.ensure_marker v1alpha1
  sandbox fixture-alpha
  evidence marker.present
  require authorization
  forbid mutation
  status draft
}
"""


@dataclass(frozen=True, slots=True)
class ProjectProfile:
    name: str
    targets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectManifest:
    schema: str
    name: str
    edition: str
    root: str
    units: tuple[str, ...]
    catalogs: tuple[str, ...]
    extension_paths: tuple[str, ...]
    profiles: tuple[ProjectProfile, ...]
    directory: Path

    @property
    def path(self) -> Path:
        return self.directory / MANIFEST_NAME

    @property
    def lock_path(self) -> Path:
        return self.directory / LOCK_NAME

    def profile(self, name: str) -> ProjectProfile:
        for item in self.profiles:
            if item.name == name:
                return item
        raise coded_error(
            "MINT_PROFILE",
            f"unknown profile {name}; declare it under [profiles.{name}] in {MANIFEST_NAME}",
        )


@dataclass(frozen=True, slots=True)
class Lockfile:
    schema: str
    name: str
    edition: str
    root: str
    ir_digest: str
    catalog_digest: str
    units: tuple[tuple[str, str], ...]
    extensions: tuple[tuple[str, str, str], ...]

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "catalogDigest": self.catalog_digest,
            "edition": self.edition,
            "extensions": [
                {"digest": digest, "namespace": namespace, "version": version}
                for namespace, version, digest in self.extensions
            ],
            "irDigest": self.ir_digest,
            "name": self.name,
            "root": self.root,
            "schema": self.schema,
            "units": [{"digest": digest, "path": path} for path, digest in self.units],
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_canonical_dict())


def closed_catalog_document() -> dict[str, Any]:
    return {"ids": list(sorted_catalog_ids()), "version": "v0"}


def catalog_digest() -> str:
    return _digest_bytes(canonical_json_bytes(closed_catalog_document()))


def discover_manifest(start: Path) -> Path:
    current = start.expanduser()
    if not current.exists():
        raise coded_error(
            "MINT_PROJECT",
            f"missing start path {current}; pass an existing directory to mint --project",
        )
    resolved = current.resolve()
    if resolved.is_file():
        resolved = resolved.parent
    for directory in (resolved, *resolved.parents):
        candidate = directory / MANIFEST_NAME
        if candidate.is_file():
            return candidate
    raise coded_error(
        "MINT_PROJECT",
        f"missing {MANIFEST_NAME} under {resolved}; run mint init or pass --project",
    )


def load_manifest(path: Path) -> ProjectManifest:
    if not path.is_file():
        raise coded_error(
            "MINT_PROJECT",
            f"missing {path}; run mint init or pass --project to a {MANIFEST_NAME} directory",
        )
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise coded_error("MINT_PROJECT", f"fix {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise coded_error("MINT_PROJECT", f"set {path} to a TOML table")
    allowed = {"schema", "name", "edition", "root", "units", "catalogs", "extensions", "profiles"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise coded_error(
            "MINT_PROJECT",
            f"remove unknown keys {unknown} from {MANIFEST_NAME}; schema is {PROJECT_SCHEMA}",
        )
    schema = str(raw.get("schema", ""))
    if schema != PROJECT_SCHEMA:
        raise coded_error(
            "MINT_PROJECT",
            f"set {MANIFEST_NAME} schema to {PROJECT_SCHEMA}; got {schema or 'empty'}",
        )
    name = str(raw.get("name", ""))
    if not _NAME.fullmatch(name):
        raise coded_error(
            "MINT_PROJECT",
            f"set {MANIFEST_NAME} name to a lowercase DNS-label like local-marker",
        )
    edition = str(raw.get("edition", ""))
    if edition not in _EDITIONS:
        raise coded_error(
            "MINT_PROJECT",
            f"set {MANIFEST_NAME} edition to v0; got {edition or 'empty'}",
        )
    root = _declared_relative(str(raw.get("root", "")), suffix=".mint")
    units_raw = raw.get("units")
    if not isinstance(units_raw, list) or not units_raw:
        raise coded_error(
            "MINT_PROJECT",
            f"set {MANIFEST_NAME} units to a non-empty list of project-relative .mint paths",
        )
    units = tuple(_declared_relative(str(item), suffix=".mint") for item in units_raw)
    if root not in units:
        raise coded_error("MINT_PROJECT", f"include root {root} in {MANIFEST_NAME} units")
    _reject_duplicates(units, "unit")
    catalogs_raw = raw.get("catalogs", [])
    if catalogs_raw and not isinstance(catalogs_raw, list):
        raise coded_error(
            "MINT_PROJECT", f"set {MANIFEST_NAME} catalogs to a list of relative JSON paths"
        )
    catalogs = tuple(_declared_relative(str(item), suffix=".json") for item in catalogs_raw or [])
    extensions_raw = raw.get("extensions", [])
    if extensions_raw and not isinstance(extensions_raw, list):
        raise coded_error(
            "MINT_PROJECT", f"set {MANIFEST_NAME} extensions to a list of tables with path"
        )
    extension_paths = tuple(_extension_path(item) for item in extensions_raw or [])
    profiles = _load_profiles(raw.get("profiles", {}))
    return ProjectManifest(
        schema=schema,
        name=name,
        edition=edition,
        root=root,
        units=units,
        catalogs=catalogs,
        extension_paths=extension_paths,
        profiles=profiles,
        directory=path.parent.resolve(),
    )


def init_project(directory: Path, *, name: str | None = None) -> ProjectManifest:
    target = directory.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    manifest_path = target / MANIFEST_NAME
    if manifest_path.is_file():
        raise coded_error(
            "MINT_PROJECT",
            f"{manifest_path} already exists; keep it or choose another directory",
        )
    project_name = name or _default_name(target)
    if not _NAME.fullmatch(project_name):
        raise coded_error(
            "MINT_PROJECT",
            "set project name to a lowercase DNS-label like local-marker",
        )
    unit = "main.mint"
    text = (
        f'schema = "{PROJECT_SCHEMA}"\n'
        f'name = "{project_name}"\n'
        f'edition = "v0"\n'
        f'root = "{unit}"\n'
        f'units = ["{unit}"]\n'
        "\n"
        "[profiles.local]\n"
        'targets = ["fixture-alpha"]\n'
    )
    _atomic_write_text(manifest_path, text)
    starter = target / unit
    if not starter.exists():
        _atomic_write_text(starter, _STARTER)
    return load_manifest(manifest_path)


def build_lockfile(manifest: ProjectManifest) -> Lockfile:
    program = load_project_units(manifest)
    _assert_catalog_files(manifest)
    result = compile_program(root=program.root, units=program.units, extensions=program.extensions)
    if not result.ok or result.digest is None:
        if result.diagnostic is None:
            raise coded_error("MINT_STATIC", "compile failed without a diagnostic")
        raise MintError(result.diagnostic)
    units = tuple(sorted((unit.unit_id, _digest_text(unit.source)) for unit in program.units))
    extensions = tuple(sorted(_extension_lock_entries(manifest)))
    return Lockfile(
        schema=LOCK_SCHEMA,
        name=manifest.name,
        edition=manifest.edition,
        root=manifest.root,
        ir_digest=result.digest,
        catalog_digest=catalog_digest(),
        units=units,
        extensions=extensions,
    )


def write_lockfile(manifest: ProjectManifest, lockfile: Lockfile) -> None:
    _atomic_write_bytes(manifest.lock_path, lockfile.canonical_bytes())


def load_lockfile(path: Path) -> Lockfile:
    if not path.is_file():
        raise coded_error(
            "MINT_LOCK",
            f"missing {path}; run mint lock in the project directory",
        )
    raw = path.read_text(encoding="utf-8")
    try:
        document = json.loads(raw)
    except ValueError as exc:
        raise coded_error(
            "MINT_LOCK",
            f"malformed {path.name}: invalid JSON; rewrite it with mint lock",
        ) from exc
    if not isinstance(document, dict):
        raise coded_error("MINT_LOCK", f"malformed {path.name}: set mint.lock to a JSON object")
    units_raw = document.get("units")
    extensions_raw = document.get("extensions")
    if not isinstance(units_raw, list) or (
        extensions_raw is not None and not isinstance(extensions_raw, list)
    ):
        raise coded_error(
            "MINT_LOCK", f"malformed {path.name}: units and extensions must be arrays"
        )
    try:
        expected = Lockfile(
            schema=str(document.get("schema", "")),
            name=str(document.get("name", "")),
            edition=str(document.get("edition", "")),
            root=str(document.get("root", "")),
            ir_digest=str(document.get("irDigest", "")),
            catalog_digest=str(document.get("catalogDigest", "")),
            units=tuple(
                (_declared_relative(str(item["path"]), suffix=".mint"), str(item["digest"]))
                for item in units_raw
            ),
            extensions=tuple(
                (str(item["namespace"]), str(item["version"]), str(item["digest"]))
                for item in extensions_raw or []
            ),
        )
    except (KeyError, TypeError) as exc:
        raise coded_error(
            "MINT_LOCK",
            f"malformed {path.name}: each unit needs path and digest",
        ) from exc
    if expected.schema != LOCK_SCHEMA:
        raise coded_error(
            "MINT_LOCK",
            f"malformed {LOCK_NAME}: schema must be {LOCK_SCHEMA}; "
            f"got {expected.schema or 'empty'}",
        )
    if raw.encode("utf-8") != expected.canonical_bytes():
        raise coded_error(
            "MINT_LOCK",
            f"malformed {path.name}: stored JSON is not canonical; rewrite it with mint lock",
        )
    return expected


def check_lockfile(manifest: ProjectManifest) -> Lockfile:
    on_disk = load_lockfile(manifest.lock_path)
    computed = build_lockfile(manifest)
    if computed.catalog_digest != on_disk.catalog_digest:
        raise coded_error(
            "MINT_CATALOG",
            "catalog digest does not match mint.lock; run mint lock after catalog changes",
        )
    if computed.extensions != on_disk.extensions:
        raise coded_error(
            "MINT_EXTENSION",
            "extension digest does not match mint.lock; run mint lock after extension changes",
        )
    if computed.canonical_bytes() != on_disk.canonical_bytes():
        raise coded_error(
            "MINT_LOCK",
            f"{manifest.lock_path.name} is stale; run mint lock to refresh hashes",
        )
    return on_disk


def load_locked_program(manifest: ProjectManifest) -> DeclaredProgram:
    check_lockfile(manifest)
    return load_project_units(manifest)


def load_project_units(manifest: ProjectManifest) -> DeclaredProgram:
    _assert_catalog_files(manifest)
    units = tuple(
        SourceUnit(
            relative, _contained_file(manifest.directory, relative).read_text(encoding="utf-8")
        )
        for relative in manifest.units
    )
    extensions = tuple(
        extension_from_dict(
            json.loads(_contained_file(manifest.directory, relative).read_text(encoding="utf-8"))
        )
        for relative in manifest.extension_paths
    )
    return DeclaredProgram(
        root=manifest.root,
        units=units,
        extensions=extensions,
        origin=str(manifest.path),
    )


def apply_profile(manifest: ProjectManifest, name: str, ir: MintIR) -> None:
    profile = manifest.profile(name)
    declared = {str(item.get("id")) for item in ir.targets}
    missing = [target for target in profile.targets if target not in declared]
    if missing:
        raise coded_error(
            "MINT_PROFILE",
            f"profile {name} lists undeclared targets {missing}; use ids from the program",
        )


def _load_profiles(raw: object) -> tuple[ProjectProfile, ...]:
    if not raw:
        return ()
    if not isinstance(raw, dict):
        raise coded_error(
            "MINT_PROFILE", f"set {MANIFEST_NAME} profiles to a table of named profiles"
        )
    profiles: list[ProjectProfile] = []
    for name, body in raw.items():
        if not isinstance(body, dict):
            raise coded_error("MINT_PROFILE", f"set [profiles.{name}] to a table with targets")
        credential = sorted(
            key
            for key in body
            if str(key).lower() in _CREDENTIAL_KEYS or "secret" in str(key).lower()
        )
        if credential:
            raise coded_error(
                "MINT_PROFILE",
                f"remove credentials {credential} from [profiles.{name}]; "
                "profiles declare targets only",
            )
        unknown = sorted(set(body) - {"targets"})
        if unknown:
            raise coded_error(
                "MINT_PROFILE",
                f"remove unknown keys {unknown} from [profiles.{name}]; only targets are allowed",
            )
        targets_raw = body.get("targets", [])
        if not isinstance(targets_raw, list) or not targets_raw:
            raise coded_error(
                "MINT_PROFILE",
                f"set [profiles.{name}] targets to a non-empty list of declared target ids",
            )
        targets = tuple(str(item) for item in targets_raw)
        profiles.append(ProjectProfile(name=str(name), targets=targets))
    return tuple(sorted(profiles, key=lambda item: item.name))


def _extension_path(raw: object) -> str:
    if not isinstance(raw, dict) or "path" not in raw:
        raise coded_error("MINT_PROJECT", 'set each [[extensions]] entry to { path = "file.json" }')
    extra = sorted(set(raw) - {"path"})
    if extra:
        raise coded_error(
            "MINT_PROJECT", f"remove unknown extension keys {extra}; use a local JSON path"
        )
    return _declared_relative(str(raw["path"]), suffix=".json")


def _extension_lock_entries(manifest: ProjectManifest) -> tuple[tuple[str, str, str], ...]:
    items: list[tuple[str, str, str]] = []
    for relative in manifest.extension_paths:
        text = _contained_file(manifest.directory, relative).read_text(encoding="utf-8")
        extension = extension_from_dict(json.loads(text))
        items.append((extension.namespace, extension.version, _digest_text(text)))
    return tuple(items)


def _assert_catalog_files(manifest: ProjectManifest) -> None:
    expected = closed_catalog_document()
    for relative in manifest.catalogs:
        text = _contained_file(manifest.directory, relative).read_text(encoding="utf-8")
        try:
            document = json.loads(text)
        except ValueError as exc:
            raise coded_error("MINT_CATALOG", f"fix {relative}: invalid catalog JSON") from exc
        if document != expected:
            raise coded_error(
                "MINT_CATALOG",
                f"{relative} does not match the closed v0 catalog; "
                "copy ids from the language catalog",
            )


def _declared_relative(raw: str, *, suffix: str) -> str:
    text = raw.strip().replace("\\", "/")
    if not text.endswith(suffix):
        raise coded_error(
            "MINT_PATH",
            f"set path {raw!r} to a project-relative {suffix} file",
        )
    candidate = Path(text)
    if candidate.is_absolute() or candidate.anchor:
        raise coded_error(
            "MINT_PATH",
            f"path {raw} must be project-relative; do not use absolute paths",
        )
    if ".." in candidate.parts or any(part == "." for part in candidate.parts):
        raise coded_error(
            "MINT_PATH",
            f"path {raw} must stay inside the project; do not use parent or . segments",
        )
    return candidate.as_posix()


def _contained_file(base: Path, relative: str) -> Path:
    declared = base / Path(relative)
    if declared.is_symlink():
        raise coded_error(
            "MINT_PATH",
            f"{relative} is a symlink; declare a real file inside the project",
        )
    path = declared.resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError:
        raise coded_error(
            "MINT_PATH",
            f"{relative} escapes the project directory; use a path under the manifest",
        ) from None
    if not path.is_file():
        raise coded_error(
            "MINT_PROJECT",
            f"missing Mint input {relative}; add the declared file under the project",
        )
    return path


def _reject_duplicates(items: tuple[str, ...], kind: str) -> None:
    seen: set[str] = set()
    for item in items:
        if item in seen:
            raise coded_error(
                "MINT_PROJECT",
                f"list each {kind} once in {MANIFEST_NAME}; drop duplicate {item}",
            )
        seen.add(item)


def _default_name(directory: Path) -> str:
    raw = directory.name.strip().lower().replace("_", "-")
    cleaned = re.sub(r"[^a-z0-9-]+", "", raw)
    if _NAME.fullmatch(cleaned):
        return cleaned
    return "local-marker"


def _digest_text(source: str) -> str:
    return _digest_bytes(source.encode("utf-8"))


def _digest_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    try:
        tmp.write_bytes(payload)
        os.replace(tmp, path)
    except OSError:
        if tmp.exists():
            tmp.unlink()
        raise
