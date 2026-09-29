"""Release tag and notes helpers. Does not publish or tag."""

from __future__ import annotations

import re
from dataclasses import dataclass

from opsdevcode_specmint.pins import (
    AUTOMATION_API_VERSION,
    AUTOMATION_INTENT_KIND,
    AUTOMATION_SPEC_KIND,
    COMPILED_INTENT_API_VERSION,
    COMPILED_INTENT_KIND,
    IR_API_VERSION,
    IR_KIND,
    MINT_LANGUAGE_VERSION,
    SPEC_API_VERSION,
    SPEC_KIND,
)

_RELEASE_TAG = re.compile(
    r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-alpha\.(0|[1-9]\d*)|a(0|[1-9]\d*))?$"
)


@dataclass(frozen=True, slots=True)
class ReleaseTagResult:
    accepted: bool
    version: str
    message: str


def parse_release_tag(tag: str) -> ReleaseTagResult:
    candidate = tag.strip()
    match = _RELEASE_TAG.fullmatch(candidate)
    if match is None:
        return ReleaseTagResult(
            False,
            "",
            "set the git tag to vMAJOR.MINOR.PATCH (example: v0.1.0); "
            "prerelease and alias tags are rejected",
        )
    version = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
    alpha = match.group(4) or match.group(5)
    if alpha is not None:
        version = f"{version}a{alpha}"
    return ReleaseTagResult(True, version, "")


def require_release_tag(tag: str) -> str:
    result = parse_release_tag(tag)
    if not result.accepted:
        raise ValueError(result.message)
    return result.version


def release_tag_matches_service(*, tag: str, service_version: str) -> ReleaseTagResult:
    parsed = parse_release_tag(tag)
    if not parsed.accepted:
        return parsed
    if parsed.version != service_version:
        return ReleaseTagResult(
            False,
            parsed.version,
            f"tag {tag} must match service version {service_version}; "
            f"set project.version in pyproject.toml",
        )
    return parsed


def first_release_tag(*, service_version: str) -> str:
    """Return the first allowed service tag. Does not create a git tag."""
    result = release_tag_matches_service(
        tag=f"v{service_version}",
        service_version=service_version,
    )
    if not result.accepted:
        raise ValueError(result.message)
    if not result.version.startswith("0."):
        raise ValueError("first service tag must stay on 0.x; do not tag v1.0.0 from this tree")
    return f"v{result.version}"


def render_release_notes(service_version: str) -> str:
    return (
        f"SpecMint {service_version}\n"
        "\n"
        "Public SpecMint core. SpecMint validates and compiles\n"
        "DeliverySpecification and AutomationSpecification documents.\n"
        "Default execution uses fake providers. mint apply is absent.\n"
        "The hosted service stays private. This alpha is not production-ready.\n"
        "\n"
        "Contracts\n"
        f"- Specification: {SPEC_API_VERSION} {SPEC_KIND}\n"
        f"- Compiled intent: {COMPILED_INTENT_API_VERSION} {COMPILED_INTENT_KIND}\n"
        f"- Automation spec: {AUTOMATION_API_VERSION} {AUTOMATION_SPEC_KIND}\n"
        f"- Automation intent: {AUTOMATION_API_VERSION} {AUTOMATION_INTENT_KIND}\n"
        f"- Intermediate representation: {IR_API_VERSION} {IR_KIND}\n"
        f"- Mint Language: {MINT_LANGUAGE_VERSION}\n"
        "\n"
        "Runtime\n"
        "- YAML, JSON, structured Markdown, and Mint share one compiler core\n"
        "- Mint lowers to AutomationSpecification only\n"
        "- validate, compile, inspect, and local execute adapters\n"
        "- identity.revision is sha256 of the closed artifact body\n"
        "- trusted CUE stays on disk; caller CUE is rejected\n"
        "\n"
        "Artifacts\n"
        "- GitHub source archive\n"
        "- opsdevcode-specmint sdist attached to the GitHub Release\n"
        "\n"
        "Scope\n"
        "- public core extract; hosted service private\n"
        "- no policy-engine evaluation\n"
        "- fake providers in the default distribution\n"
        "- GHCR tag 0.1.0-alpha.1 (no latest) from the container workflow\n"
    )
