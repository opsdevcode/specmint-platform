"""Authentication fixtures and authorization role checks. No live IdP."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from opsdevcode_specmint.platform.errors import refuse
from opsdevcode_specmint.platform.identity import CallerIdentity, parse_caller

ROLE_APPROVAL = "approval_authority"
ROLE_EXECUTION = "execution_authority"
ROLE_VERIFICATION = "verification_authority"
ROLE_OWNER = "owner"
ROLE_EXECUTOR = "executor"
_PRIVILEGED = frozenset({ROLE_OWNER, ROLE_EXECUTOR})
_CLIENT_AUTHORITY_KEYS = frozenset({"roles", "grants", "entitlements", "capabilities", "authority"})
_GENERIC_AUTH_DETAIL = "authentication failed; present a valid Authorization Bearer token"
FixtureMode = Literal["test", "local_dev"]


class IdentityVerifier(Protocol):
    def verify_bearer(self, token: str) -> CallerIdentity: ...


@dataclass(frozen=True, slots=True)
class FixtureIdentityProvider:
    """Non-production HMAC fixture tokens. Never enable under SPECMINT_ENV=production."""

    secret: bytes
    mode: FixtureMode
    allow_self_approve: bool = False
    allow_legacy_test_token: bool = False

    @classmethod
    def for_tests(
        cls,
        *,
        secret: bytes = b"specmint-test-fixture-secret-v0",
        allow_self_approve: bool = True,
        allow_legacy_test_token: bool = True,
    ) -> FixtureIdentityProvider:
        return cls(
            secret=secret,
            mode="test",
            allow_self_approve=allow_self_approve,
            allow_legacy_test_token=allow_legacy_test_token,
        )

    @classmethod
    def for_local_dev(
        cls,
        *,
        secret: bytes,
        allow_self_approve: bool = False,
    ) -> FixtureIdentityProvider:
        if not secret:
            raise ValueError("set SPECMINT_FIXTURE_IDENTITY_SECRET for local fixture identity")
        return cls(
            secret=secret,
            mode="local_dev",
            allow_self_approve=allow_self_approve,
            allow_legacy_test_token=False,
        )

    def verify_bearer(self, token: str) -> CallerIdentity:
        stripped = token.strip()
        if not stripped:
            raise refuse("PLATFORM_IDENTITY", _GENERIC_AUTH_DETAIL)
        if stripped == "test-token":
            if not self.allow_legacy_test_token or self.mode != "test":
                raise refuse("PLATFORM_IDENTITY", _GENERIC_AUTH_DETAIL)
            return parse_caller(
                {
                    "tenant": "acme",
                    "organization": "acme",
                    "subject": "tester",
                    "roles": ["owner"],
                }
            )
        if stripped.startswith("smint."):
            return _verify_signed(stripped, secret=self.secret)
        raise refuse("PLATFORM_IDENTITY", _GENERIC_AUTH_DETAIL)

    def issue_token(self, caller: CallerIdentity, *, ttl_seconds: int = 3600) -> str:
        payload = {
            "aud": "specmint-platform-v0",
            "iss": f"specmint-fixture/{self.mode}",
            "tenant": caller.tenant,
            "organization": caller.organization,
            "subject": caller.subject,
            "product": caller.product,
            "roles": list(caller.roles),
            "exp": int(datetime.now(tz=UTC).timestamp()) + ttl_seconds,
        }
        body = base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).decode("ascii")
        sig = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
        # Do not log secret or token material.
        return f"smint.{body}.{sig}"


def extract_caller(
    *,
    authorization: str | None,
    body: dict[str, Any],
    verifier: IdentityVerifier | None,
) -> CallerIdentity:
    """Derive identity only from Authorization Bearer. Body never establishes authority."""
    _reject_client_authority_fields(body)
    if not authorization:
        raise refuse("PLATFORM_IDENTITY", "set Authorization: Bearer <token>")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        raise refuse("PLATFORM_IDENTITY", "set Authorization: Bearer <token>")
    if verifier is None:
        raise refuse("PLATFORM_IDENTITY", "bearer auth is not configured on this surface")
    verified = verifier.verify_bearer(value.strip())
    _assert_optional_caller_matches(body.get("caller"), verified)
    for key in ("subject", "tenant", "organization"):
        if key in body and str(body[key]).strip() != getattr(verified, key):
            raise refuse(
                "PLATFORM_IDENTITY",
                "asserted identity fields must match the verified bearer identity",
            )
    return verified


def _reject_client_authority_fields(body: dict[str, Any]) -> None:
    banned = sorted(key for key in body if key in _CLIENT_AUTHORITY_KEYS)
    if banned:
        raise refuse(
            "PLATFORM_IDENTITY",
            f"remove client-supplied authority fields {banned}; "
            "roles and entitlements come from verified identity only",
        )
    caller = body.get("caller")
    if isinstance(caller, dict):
        nested = sorted(key for key in caller if key in _CLIENT_AUTHORITY_KEYS)
        if nested:
            raise refuse(
                "PLATFORM_IDENTITY",
                f"remove client-supplied caller authority fields {nested}; "
                "roles and entitlements come from verified identity only",
            )


def _assert_optional_caller_matches(asserted: object, verified: CallerIdentity) -> None:
    if asserted is None:
        return
    if not isinstance(asserted, dict):
        raise refuse("PLATFORM_IDENTITY", "caller assertion must be a JSON object when present")
    expected = {
        "tenant": verified.tenant,
        "organization": verified.organization,
        "subject": verified.subject,
    }
    for key, value in expected.items():
        if key in asserted and str(asserted[key]).strip() != value:
            raise refuse(
                "PLATFORM_IDENTITY",
                "asserted caller does not match verified identity",
            )


def ensure_tenant_scope(
    caller: CallerIdentity, *, tenant: str, organization: str | None = None
) -> None:
    if caller.tenant != tenant:
        raise refuse(
            "PLATFORM_AUTHORIZATION",
            "caller tenant does not match resource tenant; use the entitled tenant",
        )
    if organization is not None and caller.organization != organization:
        raise refuse(
            "PLATFORM_AUTHORIZATION",
            "caller organization does not match resource organization",
        )


def has_role(caller: CallerIdentity, role: str) -> bool:
    if role in caller.roles:
        return True
    return any(item in caller.roles for item in _PRIVILEGED)


def ensure_approval_authority(
    caller: CallerIdentity,
    *,
    plan_submitter: str,
    allow_self_approve: bool,
) -> None:
    if not has_role(caller, ROLE_APPROVAL):
        raise refuse(
            "PLATFORM_AUTHORIZATION",
            "caller lacks approval_authority; grant approval_authority or owner role",
        )
    if (
        caller.subject == plan_submitter
        and not allow_self_approve
        and not has_role(caller, ROLE_OWNER)
    ):
        raise refuse(
            "PLATFORM_AUTHORIZATION",
            "self-approval is not allowed for this plan; use a different approver subject",
        )


def ensure_execution_authority(caller: CallerIdentity) -> None:
    if not has_role(caller, ROLE_EXECUTION):
        raise refuse(
            "PLATFORM_AUTHORIZATION",
            "caller lacks execution_authority; grant execution_authority or owner role",
        )


def ensure_verification_authority(caller: CallerIdentity) -> None:
    if not has_role(caller, ROLE_VERIFICATION):
        raise refuse(
            "PLATFORM_AUTHORIZATION",
            "caller lacks verification_authority; grant verification_authority or owner role",
        )


def ensure_approval_not_expired(expires_at: str | None, *, now: datetime | None = None) -> None:
    if not expires_at:
        return
    instant = datetime.fromisoformat(expires_at)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    current = now or datetime.now(tz=UTC)
    if current >= instant:
        raise refuse("PLATFORM_APPROVAL", "approval expired; issue a new exact approval")


def ensure_plan_revision(record_revision: int, approval_revision: int) -> None:
    if approval_revision != record_revision:
        raise refuse(
            "PLATFORM_APPROVAL",
            "approval revision must match the current plan revision",
            extra={"planRevision": record_revision, "approvalRevision": approval_revision},
        )


def ensure_executor_match(expected_executor: str, requested_executor: str | None) -> None:
    if requested_executor and requested_executor != expected_executor:
        raise refuse(
            "PLATFORM_EXECUTION",
            f"executor mismatch; expected {expected_executor}",
            extra={"expected": expected_executor, "requested": requested_executor},
        )


def _verify_signed(token: str, *, secret: bytes) -> CallerIdentity:
    try:
        prefix, body, sig = token.split(".", 2)
    except ValueError as exc:
        raise refuse("PLATFORM_IDENTITY", _GENERIC_AUTH_DETAIL) from exc
    if prefix != "smint":
        raise refuse("PLATFORM_IDENTITY", _GENERIC_AUTH_DETAIL)
    expected = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise refuse("PLATFORM_IDENTITY", _GENERIC_AUTH_DETAIL)
    try:
        payload = json.loads(base64.urlsafe_b64decode(body.encode()).decode())
    except (json.JSONDecodeError, ValueError) as exc:
        raise refuse("PLATFORM_IDENTITY", _GENERIC_AUTH_DETAIL) from exc
    if not isinstance(payload, dict):
        raise refuse("PLATFORM_IDENTITY", _GENERIC_AUTH_DETAIL)
    iss = str(payload.get("iss", ""))
    aud = str(payload.get("aud", ""))
    if not iss.startswith("specmint-fixture/"):
        raise refuse("PLATFORM_IDENTITY", _GENERIC_AUTH_DETAIL)
    if aud and aud != "specmint-platform-v0":
        raise refuse("PLATFORM_IDENTITY", _GENERIC_AUTH_DETAIL)
    exp = int(payload.get("exp", 0))
    # 30s clock skew allowance for fixture tokens.
    if exp and datetime.now(tz=UTC).timestamp() > exp + 30:
        raise refuse("PLATFORM_IDENTITY", _GENERIC_AUTH_DETAIL)
    return parse_caller(
        {
            "tenant": payload.get("tenant"),
            "organization": payload.get("organization"),
            "subject": payload.get("subject"),
            "product": payload.get("product", "specmint"),
            "roles": payload.get("roles", ()),
        }
    )
