"""Closed language catalog. No product pins, no provider SDKs."""

from __future__ import annotations

from dataclasses import dataclass

from opsdevcode_specmint.mint.errors import catalog_error

ENSURE_MARKER_TYPE = "local.sandbox.ensure_marker"
ENSURE_MARKER_VERSION = "v1alpha1"
MINT_CATALOG_VERSION = "v0"
REPO_GITHUB_KIND = "repo.github"
REPO_SETTINGS_TYPE = "repo.settings"
REPO_BRANCH_PROTECTION_TYPE = "repo.branch_protection"
REPO_SECURITY_TYPE = "repo.security"
REPO_MANAGED_FILE_TYPE = "repo.managed_file"
CAPABILITY_VERSION = "v1alpha1"

SUPPORT_FULL = "full"
SUPPORT_PARTIAL = "partial"
SUPPORT_NONE = "none"


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    automation_type: str
    version: str


@dataclass(frozen=True, slots=True)
class TargetKind:
    kind: str
    fields: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class CapabilityDecl:
    capability_type: str
    version: str
    target_kinds: frozenset[str]
    support: str = SUPPORT_FULL


ENSURE_MARKER = CatalogEntry(ENSURE_MARKER_TYPE, ENSURE_MARKER_VERSION)
CATALOG: frozenset[CatalogEntry] = frozenset({ENSURE_MARKER})

TARGET_KINDS: tuple[TargetKind, ...] = (
    TargetKind("sandbox", (("id", "string"),)),
    TargetKind("local.sandbox", (("id", "string"),)),
    TargetKind("local.dev", (("workspace", "string"),)),
    TargetKind("repo.github", (("owner", "string"), ("name", "string"))),
    TargetKind("k8s.workload", (("name", "string"), ("namespace", "string"))),
    TargetKind("aws.account", (("account", "string"), ("region", "string"))),
    TargetKind("gcp.project", (("project", "string"), ("region", "string"))),
)

CAPABILITIES: tuple[CapabilityDecl, ...] = (
    CapabilityDecl(
        ENSURE_MARKER_TYPE, ENSURE_MARKER_VERSION, frozenset({"sandbox", "local.sandbox"})
    ),
    CapabilityDecl("local.dev.ensure_workspace", "v1alpha1", frozenset({"local.dev"})),
    CapabilityDecl(REPO_SETTINGS_TYPE, CAPABILITY_VERSION, frozenset({REPO_GITHUB_KIND})),
    CapabilityDecl(REPO_BRANCH_PROTECTION_TYPE, CAPABILITY_VERSION, frozenset({REPO_GITHUB_KIND})),
    CapabilityDecl(REPO_SECURITY_TYPE, CAPABILITY_VERSION, frozenset({REPO_GITHUB_KIND})),
    CapabilityDecl(REPO_MANAGED_FILE_TYPE, CAPABILITY_VERSION, frozenset({REPO_GITHUB_KIND})),
    CapabilityDecl("k8s.workload.pod_security", "v1alpha1", frozenset({"k8s.workload"})),
    CapabilityDecl("aws.iam.constraint", "v1alpha1", frozenset({"aws.account"})),
    CapabilityDecl("gcp.iam.constraint", "v1alpha1", frozenset({"gcp.project"})),
    CapabilityDecl(
        "aws.account.audit",
        "v1alpha1",
        frozenset({"aws.account"}),
        support=SUPPORT_PARTIAL,
    ),
)


def bind_catalog_entry(*, automation_type: str, version: str) -> CatalogEntry:
    entry = CatalogEntry(automation_type, version)
    if capability_for(automation_type, version) is None:
        accepted = ", ".join(
            sorted(f"{item.capability_type} {item.version}" for item in CAPABILITIES)
        )
        raise catalog_error(
            f"unknown automation type {automation_type} {version}; "
            f"catalog {MINT_CATALOG_VERSION} accepts {accepted}"
        )
    return entry


def capability_for(capability_type: str, version: str) -> CapabilityDecl | None:
    for item in CAPABILITIES:
        if item.capability_type == capability_type and item.version == version:
            return item
    return None


def target_kind(kind: str) -> TargetKind | None:
    for item in TARGET_KINDS:
        if item.kind == kind:
            return item
    return None


def sorted_catalog_ids() -> tuple[str, ...]:
    return tuple(sorted(f"{item.capability_type}@{item.version}" for item in CAPABILITIES))
