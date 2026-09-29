from __future__ import annotations

from pathlib import Path

import pytest

from opsdevcode_specmint.platform.composite import CompositeInputs, run_composite_lifecycle
from opsdevcode_specmint.platform.errors import PlatformProblem
from opsdevcode_specmint.platform.identity import StaticAuthorizer, parse_caller
from opsdevcode_specmint.platform.manifest import (
    load_manifest_dir,
    parse_capability_manifest,
    registry_from_manifests,
)
from opsdevcode_specmint.platform.object_store import MemoryObjectStore

MANIFEST_DIR = (
    Path(__file__).resolve().parents[1] / "conformance" / "platform" / "v1alpha1" / "manifests"
)


def _caller():
    return parse_caller(
        {"tenant": "acme", "organization": "acme", "subject": "tester", "roles": ["owner"]}
    )


def _grants() -> StaticAuthorizer:
    return StaticAuthorizer(
        grants=frozenset(
            {
                ("acme", "repo.github.governance"),
                ("acme", "specmint.compile"),
                ("acme", "infrastructure.lifecycle"),
                ("acme", "economics.budget.guard"),
                ("acme", "dispatch.notify"),
            }
        ),
        products_by_tenant={
            "acme": ("repave", "overpass", "toll", "dispatch", "specmint"),
        },
    )


def test_federated_manifests_route_v1alpha1() -> None:
    manifests = load_manifest_dir(MANIFEST_DIR)
    registry = registry_from_manifests(manifests, authorizer=_grants())
    decision = registry.route(
        capability_id="infrastructure.lifecycle",
        target_kind="aws",
        version="v1alpha1",
        caller=_caller(),
    )
    assert decision.status == "ok"
    assert decision.descriptor is not None
    assert decision.descriptor.owner_product == "overpass"


def test_missing_product_manifest_fails_closed(tmp_path: Path) -> None:
    for name in ("specmint.json", "toll.json", "dispatch.json"):
        (tmp_path / name).write_text((MANIFEST_DIR / name).read_text(encoding="utf-8"))
        with pytest.raises(PlatformProblem) as exc:
            registry_from_manifests(load_manifest_dir(tmp_path), authorizer=_grants())
        assert "overpass" in exc.value.detail


def test_duplicate_capability_owner_fails_closed() -> None:
    raw = {
        "apiVersion": "opsdevcode.capability-manifest/v1alpha1",
        "kind": "CapabilityManifest",
        "metadata": {"product": "intruder"},
        "spec": {
            "purpose": "steal",
            "mode": "fake-local",
            "capabilities": [
                {
                    "capabilityId": "infrastructure.lifecycle",
                    "versions": ["v1alpha1"],
                    "targetKinds": ["aws"],
                    "observation": True,
                    "planning": True,
                    "execution": True,
                    "verification": True,
                    "rollback": True,
                    "approvalSchema": "opsdevcode.approval-requirement/v0",
                    "evidenceSchema": "opsdevcode.evidence-envelope/v0",
                }
            ],
            "contracts": [
                {"schema": "opsdevcode.environment-contract/v1alpha1", "owner": "intruder"}
            ],
        },
    }
    manifests = (*load_manifest_dir(MANIFEST_DIR), parse_capability_manifest(raw))
    with pytest.raises(PlatformProblem) as exc:
        registry_from_manifests(manifests, authorizer=_grants())
    assert "multiple owners" in exc.value.detail


def test_composite_lifecycle_stores_evidence() -> None:
    manifests = load_manifest_dir(MANIFEST_DIR)
    registry = registry_from_manifests(manifests, authorizer=_grants())
    store = MemoryObjectStore()
    result = run_composite_lifecycle(
        caller=_caller(),
        registry=registry,
        manifests=manifests,
        inputs=CompositeInputs(
            environment={
                "schema": "opsdevcode.environment-contract/v1alpha1",
                "mode": "fake-local",
                "providers": ["aws"],
                "iacStrategy": "terraform",
                "maxLifetimeHours": 8,
                "teardownPolicy": "destroy",
            },
            budget={
                "allowed": True,
                "schema": "opsdevcode.budget-decision/v0",
                "limit": 20,
                "remaining": 50,
            },
            notification={
                "channel": "slack",
                "schema": "opsdevcode.notification-request/v0",
                "transport": "relay",
            },
            snapshot=None,
            approve=True,
        ),
        object_store=store,
    )
    assert result["status"] == "verified"
    key = str(result["evidenceObject"]["key"])
    assert store.get_bytes(key) is not None


def test_live_environment_mode_refused() -> None:
    manifests = load_manifest_dir(MANIFEST_DIR)
    registry = registry_from_manifests(manifests, authorizer=_grants())
    with pytest.raises(PlatformProblem):
        run_composite_lifecycle(
            caller=_caller(),
            registry=registry,
            manifests=manifests,
            inputs=CompositeInputs(
                environment={
                    "schema": "opsdevcode.environment-contract/v1alpha1",
                    "mode": "aws-live",
                    "providers": ["aws"],
                    "iacStrategy": "terraform",
                    "maxLifetimeHours": 8,
                    "teardownPolicy": "destroy",
                },
                budget={"allowed": True, "schema": "opsdevcode.budget-decision/v0"},
                notification={"channel": "email", "schema": "opsdevcode.notification-request/v0"},
                snapshot=None,
                approve=True,
            ),
            object_store=MemoryObjectStore(),
        )
