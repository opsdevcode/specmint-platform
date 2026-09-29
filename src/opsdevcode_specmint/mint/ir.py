"""MintIR v0 canonical artifact."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from opsdevcode_specmint.mint.ast import ConstDecl, TargetDecl
from opsdevcode_specmint.mint.catalog import REPO_GITHUB_KIND, sorted_catalog_ids
from opsdevcode_specmint.mint.errors import coded_error
from opsdevcode_specmint.mint.resolve import BoundProgram, Symbol

MINT_IR_API_VERSION = "mint.opsdevcode.io/v0"
MINT_IR_KIND = "MintIR"
MINT_LANGUAGE_EDITION = "v0"
DIGEST_INPUTS = (
    "declared-unit-text",
    "logical-unit-id",
    "edition",
    "closed-catalog",
    "extension-identity",
    "extension-version",
    "root-unit-id",
)


@dataclass(frozen=True, slots=True)
class MintIR:
    source_edition: str
    unit_id: str
    owner: str
    statement: str
    verb_type: str
    verb_version: str
    sandbox: str
    evidence: tuple[str, ...]
    status: str
    namespace: str
    root_unit: str
    imports: tuple[str, ...]
    extensions: tuple[tuple[str, str], ...]
    references: tuple[tuple[str, str], ...]
    targets: tuple[dict[str, Any], ...]
    capabilities: tuple[tuple[str, str], ...]
    fqid: str
    catalog: tuple[str, ...]
    declarations: tuple[dict[str, Any], ...]

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": MINT_IR_API_VERSION,
            "kind": MINT_IR_KIND,
            "language": {
                "digestInputs": list(DIGEST_INPUTS),
                "edition": MINT_LANGUAGE_EDITION,
                "sourceEdition": self.source_edition,
            },
            "module": {
                "imports": list(self.imports),
                "namespace": self.namespace,
                "rootUnit": self.root_unit,
            },
            "catalog": list(self.catalog),
            "declarations": list(self.declarations),
            "extensions": [
                {"namespace": namespace, "version": version}
                for namespace, version in self.extensions
            ],
            "unit": {
                "capabilities": [
                    {"type": cap_type, "version": version}
                    for cap_type, version in self.capabilities
                ],
                "constraints": {
                    "authorization": "required",
                    "mutation": "forbidden",
                },
                "evidence": list(self.evidence),
                "fqid": self.fqid,
                "id": self.unit_id,
                "kind": "automation",
                "owner": self.owner,
                "placement": {
                    "id": self.sandbox,
                    "kind": "sandbox",
                },
                "references": [{"fqid": fqid, "name": name} for name, fqid in self.references],
                "statement": self.statement,
                "status": self.status,
                "targets": list(self.targets),
                "verb": {
                    "type": self.verb_type,
                    "version": self.verb_version,
                },
            },
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_canonical_dict())

    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()


def build_mint_ir(
    bound: BoundProgram,
    *,
    extensions: tuple[tuple[str, str], ...] = (),
) -> MintIR:
    program = bound.automation
    capabilities = _capabilities(program)
    verb_type = program.automation_type or (capabilities[0][0] if capabilities else "")
    verb_version = program.automation_version or (capabilities[0][1] if capabilities else "")
    targets = _targets(bound, program)
    return MintIR(
        source_edition=program.edition,
        unit_id=program.automation_id,
        owner=program.owner,
        statement=program.intent,
        verb_type=verb_type,
        verb_version=verb_version,
        sandbox=program.sandbox,
        evidence=program.evidence,
        status=program.status,
        namespace=bound.root.namespace,
        root_unit=bound.root.unit_id,
        imports=tuple(sorted(item.namespace for item in bound.root.imports)),
        extensions=tuple(sorted(extensions)),
        references=bound.references,
        targets=targets,
        capabilities=capabilities,
        fqid=f"{bound.root.namespace}/automation/{program.automation_id}",
        catalog=sorted_catalog_ids(),
        declarations=_declarations(bound),
    )


def _capabilities(program: Any) -> tuple[tuple[str, str], ...]:
    items: list[tuple[str, str]] = []
    if program.automation_type:
        items.append((program.automation_type, program.automation_version))
    items.extend(program.extra_capabilities)
    return tuple(sorted(set(items)))


_SECRET_CONFIG_KEYS = frozenset(
    {
        "token",
        "password",
        "secret",
        "credential",
        "credentials",
        "apikey",
        "api_key",
        "access_key",
        "endpoint",
        "url",
        "href",
    }
)


def _targets(bound: BoundProgram, program: Any) -> tuple[dict[str, Any], ...]:
    targets: list[dict[str, Any]] = []
    if program.sandbox:
        targets.append(
            {
                "fqid": f"{bound.root.namespace}/target/{program.sandbox}",
                "id": program.sandbox,
                "kind": "sandbox",
            }
        )
    for _name, symbol in bound.applied:
        target = symbol.value
        if not isinstance(target, TargetDecl):
            raise coded_error("MINT_PLAN", "applied target must be a declared target")
        entry: dict[str, Any] = {
            "fqid": symbol.fqid,
            "id": symbol.name,
            "kind": target.kind,
        }
        config = _resolved_config(bound, target)
        if config:
            entry["config"] = config
        if target.kind == REPO_GITHUB_KIND:
            entry["identity"] = {
                "name": str(config.get("name", "")),
                "owner": str(config.get("owner", "")),
            }
        targets.append(entry)
    return tuple(sorted(targets, key=lambda item: item["fqid"]))


def _resolved_config(bound: BoundProgram, target: TargetDecl) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for key, value in target.config:
        lowered = key.lower().replace("-", "_")
        if lowered in _SECRET_CONFIG_KEYS:
            raise coded_error(
                "MINT_ADAPTER",
                f"refuse target config {key}; adapters do not accept credentials or API endpoints",
            )
        config[key] = _resolve_value(value, bound.symbols)
    return {key: config[key] for key in sorted(config)}


def _resolve_value(value: Any, symbols: tuple[Symbol, ...]) -> Any:
    if isinstance(value, tuple) and len(value) == 2 and value[0] == "ref":
        raw = str(value[1])
        short = raw.rsplit(".", 1)[-1]
        matches = [
            item
            for item in symbols
            if item.kind == "const"
            and isinstance(item.value, ConstDecl)
            and item.name in {raw, short}
        ]
        if len(matches) == 1:
            return _resolve_value(matches[0].value.value, symbols)
        return {"ref": raw}
    if isinstance(value, dict):
        return {key: _resolve_value(inner, symbols) for key, inner in sorted(value.items())}
    return value


def _declarations(bound: BoundProgram) -> tuple[dict[str, Any], ...]:
    items: list[dict[str, Any]] = []
    for symbol in bound.symbols:
        entry: dict[str, Any] = {
            "fqid": symbol.fqid,
            "kind": symbol.kind,
            "name": symbol.name,
            "namespace": symbol.namespace,
        }
        if symbol.kind == "const" and hasattr(symbol.value, "value"):
            entry["value"] = _literal(symbol.value.value)
        items.append(entry)
    return tuple(items)


def _literal(value: Any) -> Any:
    if isinstance(value, tuple) and len(value) == 2 and value[0] == "ref":
        return {"ref": value[1]}
    if isinstance(value, dict):
        return {key: _literal(inner) for key, inner in sorted(value.items())}
    return value


def canonical_json_bytes(mapping: dict[str, Any]) -> bytes:
    payload = json.dumps(mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{payload}\n".encode()
