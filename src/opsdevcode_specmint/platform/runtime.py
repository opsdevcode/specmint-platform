"""Platform runtime mode. Fixture identity is never a production default."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from opsdevcode_specmint.platform.authn import FixtureIdentityProvider, IdentityVerifier

PRODUCTION_ENVS = frozenset({"production", "prod"})
_CLIENT_AUTHORITY_KEYS = frozenset({"roles", "grants", "entitlements", "capabilities", "authority"})


@dataclass(frozen=True, slots=True)
class PlatformRuntime:
    environment: str
    fixture_identity_enabled: bool
    identity_verifier: IdentityVerifier | None

    @property
    def is_production(self) -> bool:
        return self.environment in PRODUCTION_ENVS


def load_platform_runtime(
    environ: Mapping[str, str] | None = None,
    *,
    for_tests: bool = False,
) -> PlatformRuntime:
    env = dict(os.environ if environ is None else environ)
    environment = str(env.get("SPECMINT_ENV", "development")).strip().lower() or "development"
    fixture_flag = _truthy(env.get("SPECMINT_FIXTURE_IDENTITY", ""))
    if for_tests:
        secret = env.get("SPECMINT_FIXTURE_IDENTITY_SECRET", "specmint-test-fixture-secret-v0")
        verifier: IdentityVerifier | None = FixtureIdentityProvider.for_tests(
            secret=secret.encode("utf-8"),
            allow_self_approve=_truthy(env.get("SPECMINT_ALLOW_SELF_APPROVE", "1")),
        )
        return PlatformRuntime(
            environment="test",
            fixture_identity_enabled=True,
            identity_verifier=verifier,
        )
    if environment in PRODUCTION_ENVS and fixture_flag:
        raise ValueError(
            "refuse FixtureIdentityProvider when SPECMINT_ENV is production; "
            "unset SPECMINT_FIXTURE_IDENTITY and configure a production IdentityVerifier"
        )
    if not fixture_flag:
        return PlatformRuntime(
            environment=environment,
            fixture_identity_enabled=False,
            identity_verifier=None,
        )
    raw_secret = env.get("SPECMINT_FIXTURE_IDENTITY_SECRET", "").strip()
    if not raw_secret:
        raise ValueError(
            "set SPECMINT_FIXTURE_IDENTITY_SECRET when SPECMINT_FIXTURE_IDENTITY=1; "
            "do not rely on a built-in production default"
        )
    if raw_secret in {
        "specmint-fixture-identity-v0",
        "changeme",
        "secret",
        "production",
    }:
        raise ValueError(
            "SPECMINT_FIXTURE_IDENTITY_SECRET is a forbidden default; "
            "set a unique non-production fixture secret"
        )
    verifier = FixtureIdentityProvider.for_local_dev(
        secret=raw_secret.encode("utf-8"),
        allow_self_approve=_truthy(env.get("SPECMINT_ALLOW_SELF_APPROVE", "")),
    )
    return PlatformRuntime(
        environment=environment,
        fixture_identity_enabled=True,
        identity_verifier=verifier,
    )


def _truthy(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}
