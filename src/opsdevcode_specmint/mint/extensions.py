"""Deterministic Mint extension registry. No dynamic plugin loading."""

from __future__ import annotations

from dataclasses import dataclass

from opsdevcode_specmint.mint.ast import SourceSpan
from opsdevcode_specmint.mint.catalog import CapabilityDecl, TargetKind
from opsdevcode_specmint.mint.errors import coded_error


@dataclass(frozen=True, slots=True)
class Extension:
    namespace: str
    version: str
    capabilities: tuple[CapabilityDecl, ...] = ()
    target_kinds: tuple[TargetKind, ...] = ()
    types: tuple[str, ...] = ()
    metadata_namespaces: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExtensionRegistry:
    extensions: tuple[Extension, ...]

    def get(self, namespace: str) -> Extension | None:
        for item in self.extensions:
            if item.namespace == namespace:
                return item
        return None

    def identities(self) -> tuple[tuple[str, str], ...]:
        return tuple((item.namespace, item.version) for item in self.extensions)


SAMPLE_EXTENSION = Extension(
    namespace="ext.sample",
    version="v1alpha1",
    capabilities=(
        CapabilityDecl("ext.sample.tag", "v1alpha1", frozenset({"sandbox", "local.sandbox"})),
    ),
    metadata_namespaces=("ext.sample",),
)


def build_registry(extensions: tuple[Extension, ...]) -> ExtensionRegistry:
    by_ns: dict[str, Extension] = {}
    for item in extensions:
        if item.namespace in by_ns:
            raise coded_error(
                "MINT_DUPLICATE_EXTENSION",
                f"extension namespace {item.namespace} is already registered; "
                "keep one extension per namespace",
            )
        by_ns[item.namespace] = item
    ordered = tuple(by_ns[key] for key in sorted(by_ns))
    return ExtensionRegistry(ordered)


def require_extension(
    registry: ExtensionRegistry,
    namespace: str,
    version: str,
    span: SourceSpan,
) -> Extension:
    found = registry.get(namespace)
    if found is None:
        raise coded_error(
            "MINT_UNKNOWN_EXTENSION",
            f"unknown required extension {namespace}; register {namespace} {version} "
            "in the compiler inputs",
            span=span,
        )
    if found.version != version:
        raise coded_error(
            "MINT_UNSUPPORTED_EXTENSION",
            f"unsupported extension version {namespace} {version}; "
            f"registry has {found.namespace} {found.version}",
            span=span,
        )
    return found
