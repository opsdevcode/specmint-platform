"""End-to-end local sandbox lifecycle. Injected clock and attempt ids."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opsdevcode_specmint.runtime.contract import (
    ATTEMPT_ID_PROVIDER,
    CLOCK,
    ExecutionOutcome,
)
from opsdevcode_specmint.runtime.executor import (
    approve_artifact,
    detect_drift,
    execute_artifact,
    inspect_sandbox,
    rollback_artifact,
    verify_artifact,
    write_evidence_bundle,
)
from opsdevcode_specmint.runtime.providers import AttemptIdProvider, Clock
from opsdevcode_specmint.runtime.sandbox import confined_sandbox


def run_local_lifecycle(
    document: dict[str, Any],
    sandbox: Path,
    *,
    clock: Clock = CLOCK,
    attempts: AttemptIdProvider = ATTEMPT_ID_PROVIDER,
) -> dict[str, Any]:
    root = confined_sandbox(sandbox)
    records: list[ExecutionOutcome] = []
    records.append(approve_artifact(document, root, clock=clock, attempts=attempts))
    records.append(inspect_sandbox(document, root, clock=clock, attempts=attempts))
    records.append(execute_artifact(document, root, clock=clock, attempts=attempts))
    records.append(execute_artifact(document, root, clock=clock, attempts=attempts))
    records.append(verify_artifact(document, root, clock=clock, attempts=attempts))
    records.append(detect_drift(document, root, clock=clock, attempts=attempts))
    records.append(rollback_artifact(document, root, clock=clock, attempts=attempts))
    records.append(execute_artifact(document, root, clock=clock, attempts=attempts))
    records.append(verify_artifact(document, root, clock=clock, attempts=attempts))
    evidence = write_evidence_bundle(
        document,
        root,
        records=tuple(records),
        clock=clock,
        attempts=attempts,
    )
    records.append(evidence)
    return {
        "ok": all(
            item.status in {"approved", "inspected", "completed", "noop", "aligned", "recovered"}
            for item in records
        ),
        "sandbox": str(root),
        "records": [item.to_canonical_dict() for item in records],
        "evidence": evidence.to_canonical_dict(),
    }
