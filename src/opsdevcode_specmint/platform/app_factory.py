"""Construct PlatformService and FastAPI apps from environment (subprocess / operator bootstrap)."""

from __future__ import annotations

import os

from fastapi import FastAPI

from opsdevcode_specmint.platform.executor import FakeGithubProvider
from opsdevcode_specmint.platform.migrate import apply_migrations
from opsdevcode_specmint.platform.persistence import MemoryStore, PlatformStore
from opsdevcode_specmint.platform.postgres import PostgresStore
from opsdevcode_specmint.platform.runtime import PRODUCTION_ENVS, load_platform_runtime
from opsdevcode_specmint.platform.service import PlatformService


def bootstrap_platform_service_from_env() -> PlatformService:
    """Wire store + fixture/OIDC runtime from SPECMINT_* environment variables."""
    runtime = load_platform_runtime()
    url = os.environ.get("SPECMINT_DATABASE_URL", "").strip()
    allow_memory = _truthy(os.environ.get("SPECMINT_ALLOW_MEMORY_STORE", ""))
    template = PlatformService.in_memory()
    store: PlatformStore
    if runtime.is_production:
        if allow_memory:
            raise ValueError(
                "refuse SPECMINT_ALLOW_MEMORY_STORE in production; "
                "set SPECMINT_DATABASE_URL to PostgreSQL"
            )
        if not url:
            raise ValueError(
                "set SPECMINT_DATABASE_URL for production bootstrap; MemoryStore is not allowed"
            )
        if runtime.fixture_identity_enabled:
            raise ValueError(
                "refuse FixtureIdentityProvider in production; "
                "configure a production IdentityVerifier"
            )
        if runtime.identity_verifier is None:
            raise ValueError(
                "configure a production IdentityVerifier before SPECMINT_ENV=production bootstrap"
            )
        apply_migrations(url)
        store = PostgresStore(url)
        verifier = runtime.identity_verifier
        return PlatformService(
            store=store,
            authorizer=template.authorizer,
            registry=template.registry,
            provider=FakeGithubProvider(),
            identity_verifier=verifier,
            allow_self_approve=False,
        )

    if url:
        apply_migrations(url)
        store = PostgresStore(url)
    elif allow_memory or not runtime.is_production:
        # Development/private-preview may use MemoryStore only with explicit opt-in
        # or when SPECMINT_DATABASE_URL is unset outside production.
        if not allow_memory and os.environ.get("SPECMINT_REQUIRE_DATABASE", "").strip():
            raise ValueError("set SPECMINT_DATABASE_URL or unset SPECMINT_REQUIRE_DATABASE")
        store = MemoryStore()
    else:
        store = MemoryStore()

    if runtime.identity_verifier is None:
        raise ValueError(
            "set SPECMINT_FIXTURE_IDENTITY=1 and SPECMINT_FIXTURE_IDENTITY_SECRET for "
            "private-preview bootstrap, or configure a production IdentityVerifier"
        )
    allow_self = runtime.fixture_identity_enabled and _truthy(
        os.environ.get("SPECMINT_ALLOW_SELF_APPROVE", "")
    )
    return PlatformService(
        store=store,
        authorizer=template.authorizer,
        registry=template.registry,
        provider=FakeGithubProvider(),
        identity_verifier=runtime.identity_verifier,
        allow_self_approve=allow_self,
    )


def create_platform_app(
    *,
    service: PlatformService | None = None,
) -> FastAPI:
    from opsdevcode_specmint.platform.http import (
        configure_platform_service,
        register_platform_routes,
    )

    app = FastAPI(title="SpecMint Platform", docs_url=None, redoc_url=None, openapi_url=None)
    configure_platform_service(service or bootstrap_platform_service_from_env())
    register_platform_routes(app)
    return app


def assert_production_ready(environ: dict[str, str] | None = None) -> None:
    """Fail closed when production env is incomplete. Used by readiness and CI."""
    env = dict(os.environ if environ is None else environ)
    environment = str(env.get("SPECMINT_ENV", "development")).strip().lower()
    if environment not in PRODUCTION_ENVS:
        return
    if _truthy(env.get("SPECMINT_FIXTURE_IDENTITY", "")):
        raise ValueError("refuse FixtureIdentityProvider when SPECMINT_ENV is production")
    if not env.get("SPECMINT_DATABASE_URL", "").strip():
        raise ValueError("set SPECMINT_DATABASE_URL for production")
    if _truthy(env.get("SPECMINT_ALLOW_MEMORY_STORE", "")):
        raise ValueError("refuse MemoryStore override in production")
    if _truthy(env.get("SPECMINT_ENABLE_LIVE_GITHUB", "")):
        raise ValueError("live GitHub execution is disabled in this private-preview build")


def _truthy(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}
