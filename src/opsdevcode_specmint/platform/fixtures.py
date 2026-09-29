"""Deterministic private-preview scenarios. JSON-serializable; no live I/O."""

from __future__ import annotations

from typing import Any

from opsdevcode_specmint.mint.adapters.snapshot import parse_snapshot

MINT_SETTINGS = """mint v0
namespace example.repo
target primary {
  kind repo.github
  config {
    owner "opsdevcode"
    name "specmint"
  }
}
automation as-repo-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Govern repository settings"
  use repo.settings v1alpha1
  apply primary
  evidence repo.settings
  require authorization
  forbid mutation
  status draft
}
"""

MINT_SETTINGS = """mint v0
namespace example.repo
target primary {
  kind repo.github
  config {
    owner "opsdevcode"
    name "specmint"
    visibility "private"
  }
}
automation as-repo-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Govern repository settings"
  use repo.settings v1alpha1
  apply primary
  evidence repo.settings
  require authorization
  forbid mutation
  status draft
}
"""

MINT_FULL = """mint v0
namespace example.repo
target primary {
  kind repo.github
  config {
    owner "opsdevcode"
    name "specmint"
    pull_request_required true
    required_approving_review_count 1
    secret_scanning true
    push_protection true
    dependency_alerts true
    file_path "SECURITY.md"
    file_content "# Security\\n"
    file_mode "0644"
    required_checks {
      ci true
    }
  }
}
automation as-repo-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Govern repository rules, checks, security, and a managed file"
  use repo.branch_protection v1alpha1
  capabilities repo.settings v1alpha1, repo.security v1alpha1, repo.managed_file v1alpha1
  apply primary
  evidence branch.protection
  require authorization
  forbid mutation
  status draft
}
"""


def complete_snapshot(**overrides: object) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": "mint.repository-snapshot/v0",
        "kind": "MintRepositorySnapshot",
        "identity": {"owner": "opsdevcode", "name": "specmint"},
        "providerKind": "repo.github",
        "settings": {
            "archived": False,
            "allowMergeCommit": True,
            "allowRebaseMerge": False,
            "allowSquashMerge": True,
            "defaultBranch": "main",
            "deleteBranchOnMerge": False,
            "visibility": "private",
        },
        "rules": {
            "allowDeletions": False,
            "allowForcePushes": False,
            "pullRequestRequired": True,
            "requireConversationResolution": False,
            "requiredApprovingReviewCount": 1,
            "requiredStatusChecks": ["ci"],
        },
        "security": {
            "dependencyAlerts": True,
            "pushProtection": True,
            "secretScanning": True,
        },
        "files": [],
        "completeness": {
            "files": "complete",
            "rules": "complete",
            "security": "complete",
            "settings": "complete",
        },
        "unknown": [],
        "unavailable": [],
        "unsupported": [],
        "redacted": [],
    }
    document.update(overrides)
    return parse_snapshot(document, source="fixture").document


def scenario_catalog() -> tuple[dict[str, Any], ...]:
    return (
        {"id": "01-compliant", "mint": MINT_SETTINGS, "snapshot": complete_snapshot()},
        {
            "id": "02-one-setting",
            "mint": MINT_SETTINGS,
            "snapshot": complete_snapshot(
                settings={**complete_snapshot()["settings"], "visibility": "public"}
            ),
        },
        {
            "id": "03-full-change",
            "mint": MINT_FULL,
            "snapshot": complete_snapshot(
                rules={
                    "allowDeletions": False,
                    "allowForcePushes": False,
                    "pullRequestRequired": False,
                    "requireConversationResolution": False,
                    "requiredApprovingReviewCount": 0,
                    "requiredStatusChecks": [],
                }
            ),
        },
        {"id": "04-state-after-approval", "mint": MINT_SETTINGS, "snapshot": complete_snapshot()},
        {
            "id": "05-incomplete",
            "mint": MINT_SETTINGS,
            "snapshot": complete_snapshot(
                completeness={
                    "files": "unavailable",
                    "rules": "unknown",
                    "security": "redacted",
                    "settings": "complete",
                }
            ),
        },
        {"id": "06-unauthorized", "mint": MINT_SETTINGS, "snapshot": complete_snapshot()},
        {"id": "07-duplicate-run", "mint": MINT_SETTINGS, "snapshot": complete_snapshot()},
        {"id": "08-partial-failure", "mint": MINT_SETTINGS, "snapshot": complete_snapshot()},
        {"id": "09-verify-failure", "mint": MINT_SETTINGS, "snapshot": complete_snapshot()},
        {"id": "10-post-success-drift", "mint": MINT_SETTINGS, "snapshot": complete_snapshot()},
        {"id": "11-repave-only", "tenant": "repave-only"},
        {"id": "12-overpass-toll", "tenant": "infra-econ"},
        {"id": "13-full-sandbox"},
        {"id": "14-sandbox-budget"},
        {"id": "15-sandbox-approval"},
        {"id": "16-sandbox-warning", "warning": True},
        {"id": "17-sandbox-teardown"},
        {"id": "18-missing-entitlement"},
        {"id": "19-unsupported-owner"},
        {"id": "20-deterministic-evidence"},
    )
