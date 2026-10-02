from __future__ import annotations

from pathlib import Path

import pytest

from opsdevcode_specmint.pins import (
    AUTOMATION_API_VERSION,
    COMPILED_INTENT_API_VERSION,
    MINT_LANGUAGE_VERSION,
    SPEC_API_VERSION,
)
from opsdevcode_specmint.release import (
    first_release_tag,
    ghcr_tag_for_service_version,
    git_tag_for_service_version,
    parse_release_tag,
    refuse_1x_or_alias,
    release_tag_matches_service,
    render_release_notes,
    require_canonical_release_tag,
    require_release_tag,
)
from opsdevcode_specmint.version import service_version

REPO_ROOT = Path(__file__).resolve().parents[1]


def _assert_third_party_actions_use_commit_shas(workflow: str) -> None:
    for raw in workflow.splitlines():
        stripped = raw.strip()
        if not stripped.startswith("uses: "):
            continue
        ref = stripped.split("uses:", 1)[1].strip()
        assert "@" in ref, ref
        pin = ref.split("@", 1)[1].split()[0]
        assert len(pin) == 40, ref
        assert all(char in "0123456789abcdef" for char in pin), ref


def test_accepts_semver_tags() -> None:
    parsed = parse_release_tag("v0.1.0")
    assert parsed.accepted is True
    assert parsed.version == "0.1.0"
    assert require_release_tag("v1.2.3") == "1.2.3"


def test_rejects_alias_and_prerelease_tags() -> None:
    tags = (
        "latest",
        "vlatest",
        "stable",
        "vstable",
        "v1",
        "v1.0.0-rc.1",
        "1.0.0",
        "release",
    )
    for tag in tags:
        result = parse_release_tag(tag)
        assert result.accepted is False
        assert "vMAJOR.MINOR.PATCH" in result.message


def test_accepts_alpha_tag() -> None:
    parsed = parse_release_tag("v0.1.0-alpha.1")
    assert parsed.accepted is True
    assert parsed.version == "0.1.0a1"
    current = parse_release_tag("v0.1.0-alpha.3")
    assert current.accepted is True
    assert current.version == "0.1.0a3"
    pep440_form = parse_release_tag("v0.1.0a3")
    assert pep440_form.accepted is True
    assert pep440_form.version == "0.1.0a3"


def test_maps_pep440_alpha_to_canonical_git_and_ghcr_tags() -> None:
    assert git_tag_for_service_version("0.1.0a3") == "v0.1.0-alpha.3"
    assert ghcr_tag_for_service_version("0.1.0a3") == "0.1.0-alpha.3"
    assert git_tag_for_service_version("0.1.0") == "v0.1.0"


def test_tag_must_match_service_version() -> None:
    current = service_version()
    matched = release_tag_matches_service(tag=f"v{current}", service_version=current)
    assert matched.accepted is True
    hyphenated = release_tag_matches_service(tag="v0.1.0-alpha.3", service_version="0.1.0a3")
    assert hyphenated.accepted is True
    mismatched = release_tag_matches_service(tag="v9.9.9", service_version=current)
    assert mismatched.accepted is False
    assert "pyproject.toml" in mismatched.message
    canonical = require_canonical_release_tag(tag="v0.1.0-alpha.3", service_version="0.1.0a3")
    assert canonical.accepted is True
    noncanonical = require_canonical_release_tag(tag="v0.1.0a3", service_version="0.1.0a3")
    assert noncanonical.accepted is False


def test_refuse_1x_latest_stable() -> None:
    assert refuse_1x_or_alias("v0.1.0-alpha.3").accepted is True
    for tag in ("latest", "stable", "v1.0.0", "v1.0.0-alpha.1"):
        result = refuse_1x_or_alias(tag)
        assert result.accepted is False


def test_release_notes_name_contracts_not_caller_cue() -> None:
    notes = render_release_notes("0.1.0a3")
    assert "SpecMint 0.1.0a3" in notes
    assert "Integration Protocol v0" in notes
    assert "opsdevcode/specmint-language" in notes
    assert "governed runtime" in notes
    assert SPEC_API_VERSION in notes
    assert COMPILED_INTENT_API_VERSION in notes
    assert AUTOMATION_API_VERSION in notes
    assert f"Mint Language: {MINT_LANGUAGE_VERSION}" in notes
    assert "sdist" in notes
    assert "caller CUE is rejected" in notes
    assert "no policy-engine evaluation" in notes
    assert "application/cue" not in notes
    assert "mint apply is absent" in notes
    assert "not production-ready" in notes
    assert "GHCR tag 0.1.0-alpha.3 (no latest)" in notes
    assert "not published to the PyPI project specmint" in notes


def test_first_release_tag_stays_on_0x() -> None:
    assert first_release_tag(service_version=service_version()) == "v0.1.0-alpha.3"
    with pytest.raises(ValueError, match="0.x|1.x"):
        first_release_tag(service_version="1.0.0")


def test_release_workflow_is_tag_driven_with_supply_chain_gates() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "python -m build --sdist --wheel" in workflow
    assert "dist/*" in workflow
    assert "--prerelease" in workflow
    assert "tags:" in workflow
    assert '"v*"' in workflow or '- "v*"' in workflow
    assert "branches: [main]" not in workflow
    assert "PYPI_TOKEN" not in workflow
    assert "pypi.org" not in workflow.lower()
    assert "twine" not in workflow.lower()
    assert "pypa/gh-action-pypi-publish" not in workflow
    assert "upload_to_pypi = false" in pyproject
    assert "fail closed (do not rebuild or overwrite)" in workflow
    attest = "actions/attest-build-provenance@db473fddc028af60658334401dc6fa3ffd8669fd"
    assert "anchore/sbom-action@66cbf4bc1f1c0d2edc94016e65bc221b6bb0ad6c" in workflow
    assert attest in workflow
    assert "sha256sum" in workflow
    assert "python -m venv" in workflow
    assert ":latest" not in workflow
    assert "never publish latest/stable" in workflow
    _assert_third_party_actions_use_commit_shas(workflow)


def test_container_workflow_publishes_immutable_ghcr_tag() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "container.yml").read_text(encoding="utf-8")
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "tags:" in workflow
    assert "ghcr.io/opsdevcode/specmint" in workflow
    assert "steps.meta.outputs.version" in workflow
    assert 'docker push "${IMAGE}:${VERSION}"' in workflow
    assert 'docker push "${IMAGE}:latest"' not in workflow
    assert "docker push ${IMAGE}:latest" not in workflow
    assert "never push latest" in workflow.lower()
    attest = "actions/attest-build-provenance@db473fddc028af60658334401dc6fa3ffd8669fd"
    assert "anchore/sbom-action@66cbf4bc1f1c0d2edc94016e65bc221b6bb0ad6c" in workflow
    assert attest in workflow
    assert "owner-only" in workflow
    assert "PYPI_TOKEN" not in workflow
    assert "neither trivy nor grype" in workflow
    assert "SPECMINT_BOOTSTRAP=0" in dockerfile
    assert "SPECMINT_BOOTSTRAP=1" not in dockerfile
    _assert_third_party_actions_use_commit_shas(workflow)


def test_docs_forbid_pypi_specmint_and_latest() -> None:
    releases = (REPO_ROOT / "docs" / "releases.md").read_text(encoding="utf-8")
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "untagged" not in changelog.lower()
    assert "Integration Protocol v0" in changelog
    assert "mint apply" in changelog.lower()
    assert "not production-ready" in changelog.lower()
    assert "PyPI project `specmint`" in releases
    assert "never pushes `latest`" in releases.lower() or "Never pushes `latest`" in releases
    assert "upload_to_pypi" in releases
    assert "owner" in releases.lower()
