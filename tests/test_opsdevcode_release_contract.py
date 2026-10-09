"""Local invariants for the opsdevcode.release/v0 contract."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_opsdevcode_release_contract() -> None:
    data = json.loads((REPO / "opsdevcode-release.json").read_text(encoding="utf-8"))
    assert data["schema"] == "opsdevcode.release/v0"
    assert data["repository"] == f"opsdevcode/{REPO.name}"
    assert data["tagPolicy"]["manualTags"] is False
    assert data["tagPolicy"]["retag"] is False
    assert data["prerelease"]["githubMakeLatest"] is False
    assert data["provenance"]["synthesize"] is False
    assert data["downstream"]["ghcr"]["latest"] is False
    assert data["downstream"]["ghcr"]["visibilityChange"] is False
    if data["profile"] == "mint-integration":
        assert data["downstream"]["pypi"]["role"] == "deferred"
    if data["profile"] == "mint-language":
        assert data["canonical"] == "github-release"
        assert data["downstream"]["pypi"]["role"] == "mirror"
    if data["profile"] == "mint-platform":
        assert data["canonical"] == "github-release"
        assert data["downstream"]["ghcr"]["role"] == "mirror"
