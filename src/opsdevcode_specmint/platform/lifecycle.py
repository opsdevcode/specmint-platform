"""Explicit governance lifecycle states and allowed transitions."""

from __future__ import annotations

from typing import Final

from opsdevcode_specmint.platform.errors import refuse

STATUS_DRAFTED: Final = "drafted"
STATUS_COMPILED: Final = "compiled"
STATUS_PLANNED: Final = "planned"
STATUS_APPROVAL_REQUIRED: Final = "approval_required"
STATUS_APPROVED: Final = "approved"
STATUS_EXECUTION_REQUESTED: Final = "execution_requested"
STATUS_EXECUTING: Final = "executing"
STATUS_EXECUTED: Final = "executed"
STATUS_VERIFICATION_REQUIRED: Final = "verification_required"
STATUS_VERIFIED: Final = "verified"
STATUS_FAILED: Final = "failed"
STATUS_DRIFTED: Final = "drifted"
STATUS_RECOVERY_REQUIRED: Final = "recovery_required"
STATUS_RECOVERED: Final = "recovered"
STATUS_CANCELLED: Final = "cancelled"
STATUS_EXPIRED: Final = "expired"

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {STATUS_VERIFIED, STATUS_FAILED, STATUS_CANCELLED, STATUS_EXPIRED, STATUS_RECOVERED}
)

IMMUTABLE_PLAN_STATUSES: frozenset[str] = frozenset(
    {
        STATUS_APPROVED,
        STATUS_EXECUTION_REQUESTED,
        STATUS_EXECUTING,
        STATUS_EXECUTED,
        STATUS_VERIFICATION_REQUIRED,
        STATUS_VERIFIED,
        STATUS_FAILED,
        STATUS_DRIFTED,
        STATUS_RECOVERY_REQUIRED,
        STATUS_RECOVERED,
    }
)

_ALLOWED: dict[str, frozenset[str]] = {
    STATUS_DRAFTED: frozenset({STATUS_COMPILED, STATUS_PLANNED, STATUS_CANCELLED}),
    STATUS_COMPILED: frozenset({STATUS_PLANNED, STATUS_CANCELLED}),
    STATUS_PLANNED: frozenset({STATUS_APPROVAL_REQUIRED, STATUS_APPROVED, STATUS_CANCELLED}),
    STATUS_APPROVAL_REQUIRED: frozenset(
        {STATUS_APPROVED, STATUS_EXPIRED, STATUS_CANCELLED, STATUS_FAILED}
    ),
    STATUS_APPROVED: frozenset(
        {STATUS_EXECUTION_REQUESTED, STATUS_EXPIRED, STATUS_CANCELLED, STATUS_FAILED}
    ),
    STATUS_EXECUTION_REQUESTED: frozenset({STATUS_EXECUTING, STATUS_FAILED, STATUS_CANCELLED}),
    STATUS_EXECUTING: frozenset(
        {STATUS_EXECUTED, STATUS_VERIFICATION_REQUIRED, STATUS_FAILED, STATUS_DRIFTED}
    ),
    STATUS_EXECUTED: frozenset({STATUS_VERIFICATION_REQUIRED, STATUS_FAILED, STATUS_DRIFTED}),
    STATUS_VERIFICATION_REQUIRED: frozenset({STATUS_VERIFIED, STATUS_FAILED}),
    STATUS_VERIFIED: frozenset({STATUS_DRIFTED, STATUS_RECOVERY_REQUIRED}),
    STATUS_FAILED: frozenset({STATUS_RECOVERY_REQUIRED, STATUS_CANCELLED}),
    STATUS_DRIFTED: frozenset({STATUS_RECOVERY_REQUIRED, STATUS_FAILED}),
    STATUS_RECOVERY_REQUIRED: frozenset({STATUS_RECOVERED, STATUS_FAILED}),
    STATUS_RECOVERED: frozenset(),
    STATUS_CANCELLED: frozenset(),
    STATUS_EXPIRED: frozenset({STATUS_PLANNED, STATUS_APPROVAL_REQUIRED}),
}


def ensure_transition(current: str, target: str) -> None:
    if current == target:
        return
    allowed = _ALLOWED.get(current, frozenset())
    if target not in allowed:
        raise refuse(
            "PLATFORM_LIFECYCLE",
            f"cannot transition from {current} to {target}; reload governance record",
            extra={"current": current, "target": target},
        )


def initial_plan_status(approval_required: bool) -> str:
    return STATUS_APPROVAL_REQUIRED if approval_required else STATUS_PLANNED
