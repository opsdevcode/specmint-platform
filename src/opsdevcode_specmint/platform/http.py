"""HTTP adapters for the private platform service."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request

from opsdevcode_specmint.parse import decode_body, read_capped_stream
from opsdevcode_specmint.platform.authn import extract_caller
from opsdevcode_specmint.platform.metrics import platform_metrics
from opsdevcode_specmint.platform.service import PlatformService

_SERVICE = PlatformService.in_memory()


def configure_platform_service(service: PlatformService) -> None:
    global _SERVICE
    _SERVICE = service


def platform_service() -> PlatformService:
    return _SERVICE


def _maybe_bootstrap_from_env() -> None:
    import os

    if os.environ.get("SPECMINT_BOOTSTRAP", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return
    from opsdevcode_specmint.platform.app_factory import bootstrap_platform_service_from_env

    configure_platform_service(bootstrap_platform_service_from_env())


_maybe_bootstrap_from_env()


def register_platform_routes(app: FastAPI) -> None:
    @app.post("/api/platform/v0/compile")
    async def post_compile(request: Request) -> dict[str, Any]:
        body = await _json(request)
        return _SERVICE.compile_intent(str(body.get("source", "")), caller=_caller(request, body))

    @app.post("/api/platform/v0/capabilities")
    async def post_capabilities() -> dict[str, Any]:
        return _SERVICE.list_capabilities()

    @app.get("/api/platform/v0/capabilities")
    def get_capabilities() -> dict[str, Any]:
        return _SERVICE.list_capabilities()

    @app.post("/api/platform/v0/snapshots")
    async def post_snapshot(request: Request) -> dict[str, Any]:
        body = await _json(request)
        return _SERVICE.bind_snapshot(
            dict(body.get("snapshot") or {}), caller=_caller(request, body)
        )

    @app.post("/api/platform/v0/plans")
    async def post_plan(request: Request) -> dict[str, Any]:
        body = await _json(request)
        return _SERVICE.plan(
            str(body.get("source", "")),
            dict(body.get("snapshot") or {}),
            caller=_caller(request, body),
            idempotency_key=str(body.get("idempotencyKey", "default")),
        )

    @app.get("/api/platform/v0/plans")
    async def get_plans(request: Request) -> dict[str, Any]:
        body = await _json(request) if request.headers.get("content-length") else {}
        limit = int(request.query_params.get("limit", body.get("limit", 50)))
        cursor = request.query_params.get("cursor", body.get("cursor"))
        return _SERVICE.list_plans(
            caller=_caller(request, body),
            limit=limit,
            cursor=str(cursor) if cursor else None,
        )

    @app.post("/api/platform/v0/approvals")
    async def post_approval(request: Request) -> dict[str, Any]:
        body = await _json(request)
        return _SERVICE.accept_approval(
            dict(body.get("approval") or body), caller=_caller(request, body)
        )

    @app.post("/api/platform/v0/runs")
    async def post_run(request: Request) -> dict[str, Any]:
        body = await _json(request)
        caller = _caller(request, body)
        authorized = True
        return _SERVICE.run(body, caller=caller, authorized=authorized)

    @app.get("/api/platform/v0/runs")
    async def get_runs(request: Request) -> dict[str, Any]:
        body = await _json(request) if request.headers.get("content-length") else {}
        limit = int(request.query_params.get("limit", body.get("limit", 50)))
        cursor = request.query_params.get("cursor", body.get("cursor"))
        return _SERVICE.list_runs(
            caller=_caller(request, body),
            limit=limit,
            cursor=str(cursor) if cursor else None,
        )

    @app.post("/api/platform/v0/verifications")
    async def post_verify(request: Request) -> dict[str, Any]:
        body = await _json(request)
        caller = _caller(request, body)
        return _SERVICE.verify_run(
            plan_digest=str(body.get("planDigest", "")),
            snapshot_digest=str(body.get("snapshotDigest", "")),
            caller=caller,
        )

    @app.post("/api/platform/v0/evidence")
    async def post_evidence(request: Request) -> dict[str, Any]:
        body = await _json(request)
        return _SERVICE.evidence(body, caller=_caller(request, body))

    @app.post("/api/platform/v0/sandbox")
    async def post_sandbox(request: Request) -> dict[str, Any]:
        body = await _json(request)
        return _SERVICE.compose(body, caller=_caller(request, body))

    @app.post("/api/platform/v1alpha1/compose")
    async def post_compose_v1alpha1(request: Request) -> dict[str, Any]:
        body = await _json(request)
        caller = _caller(request, body)
        return _SERVICE.compose_v1alpha1(
            caller=caller,
            environment=dict(body.get("environment") or {}),
            budget=dict(body.get("budget") or {}),
            notification=dict(body.get("notification") or {}),
            snapshot=body.get("snapshot") if isinstance(body.get("snapshot"), dict) else None,
            approve=bool(body.get("approve", True)),
            teardown_fails=bool(body.get("teardownFails", False)),
        )

    @app.get("/api/platform/v0/healthz")
    def platform_health() -> dict[str, str]:
        return {"status": "ok", "surface": "platform"}

    @app.get("/api/platform/v0/readyz")
    def platform_ready() -> dict[str, Any]:
        payload = _SERVICE.readyz()
        payload["metrics"] = platform_metrics().snapshot()
        return payload


async def _json(request: Request) -> dict[str, Any]:
    raw = await read_capped_stream(request.headers.get("content-length"), request.stream())
    return decode_body(raw, request.headers.get("content-type") or "application/json")


def _caller(request: Request, body: dict[str, Any]) -> Any:
    return extract_caller(
        authorization=request.headers.get("authorization"),
        body=body,
        verifier=_SERVICE.identity_verifier,
    )
