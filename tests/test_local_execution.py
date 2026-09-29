from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.fixtures import valid_automation_spec, valid_spec

from opsdevcode_specmint.cli import main
from opsdevcode_specmint.compiler import compile_specification
from opsdevcode_specmint.errors import SpecProblem
from opsdevcode_specmint.runtime.contract import EXECUTOR_CONTRACT, EXECUTOR_CONTRACT_V0
from opsdevcode_specmint.runtime.executor import (
    approve_artifact,
    detect_drift,
    execute_artifact,
    inspect_sandbox,
    rollback_artifact,
    verify_artifact,
)
from opsdevcode_specmint.runtime.lifecycle import run_local_lifecycle
from opsdevcode_specmint.runtime.providers import SequenceAttemptIds, StaticClock
from opsdevcode_specmint.runtime.sandbox import ExecutionPathError, confined_sandbox

_INSTANT = datetime(2026, 9, 21, 14, 0, tzinfo=UTC)


def _clock() -> StaticClock:
    return StaticClock(_INSTANT)


def _attempts(count: int = 16) -> SequenceAttemptIds:
    return SequenceAttemptIds(tuple(f"attempt-{index:02d}" for index in range(count)))


def _run(argv: list[str], *, stdin: bytes | None = None) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    code = main(
        argv,
        stdin=io.BytesIO(stdin or b""),
        stdout=out,
        stderr=err,
    )
    return code, out.getvalue(), err.getvalue()


def test_executor_contract_is_versioned_and_sandbox_only() -> None:
    contract = EXECUTOR_CONTRACT_V0.to_canonical_dict()
    assert contract["apiVersion"] == "execution.opsdevcode.io/v0"
    assert contract["kind"] == "LocalExecutorContract"
    assert contract["executor"]["id"] == "local.sandbox"
    assert contract["executor"]["version"] == "v0"
    assert contract["executor"]["sandboxOnly"] is True
    assert contract["scope"]["mintApply"] is False
    assert contract["scope"]["providers"] is False
    assert contract == EXECUTOR_CONTRACT
    assert "approve" in contract["executor"]["verbs"]


def test_local_lifecycle_fixture(tmp_path: Path) -> None:
    artifact = compile_specification(valid_automation_spec())
    sandbox = tmp_path / "sandbox"
    result = run_local_lifecycle(artifact, sandbox, clock=_clock(), attempts=_attempts())
    assert result["ok"] is True
    statuses = [item["status"] for item in result["records"]]
    assert statuses[:6] == [
        "approved",
        "inspected",
        "completed",
        "noop",
        "completed",
        "aligned",
    ]
    assert "recovered" in statuses
    assert result["evidence"]["kind"] == "LocalEvidenceBundle"
    bundle = sandbox / "evidence" / "bundle.json"
    assert bundle.is_file()
    written = json.loads(bundle.read_text(encoding="utf-8"))
    assert written["digest"].startswith("sha256:")
    marker = sandbox / "markers" / "fixture-alpha.json"
    assert json.loads(marker.read_text(encoding="utf-8"))["present"] is True
    approval = json.loads((sandbox / "approval.json").read_text(encoding="utf-8"))
    assert approval["artifact"]["revision"] == artifact["identity"]["revision"]
    assert all(item["attemptId"].startswith("attempt-") for item in result["records"])
    assert all(item["recordedAt"] == "2026-09-21T14:00:00Z" for item in result["records"])


def test_execute_refused_without_approval(tmp_path: Path) -> None:
    artifact = compile_specification(valid_automation_spec())
    outcome = execute_artifact(artifact, tmp_path / "box", clock=_clock(), attempts=_attempts())
    assert outcome.status == "refused"
    assert outcome.code == "EXECUTION_REFUSED"
    assert not (tmp_path / "box" / "markers").exists() or not any(
        (tmp_path / "box" / "markers").iterdir()
    )


def test_approval_is_digest_bound(tmp_path: Path) -> None:
    first = compile_specification(valid_automation_spec())
    other = compile_specification(
        valid_automation_spec(
            spec={
                **valid_automation_spec()["spec"],
                "intent": "Different statement",
            }
        )
    )
    sandbox = tmp_path / "box"
    approve_artifact(first, sandbox, clock=_clock(), attempts=_attempts())
    refused = execute_artifact(other, sandbox, clock=_clock(), attempts=_attempts())
    assert refused.status == "refused"
    assert "re-approve" in refused.message


def test_inspect_is_read_only(tmp_path: Path) -> None:
    artifact = compile_specification(valid_automation_spec())
    sandbox = tmp_path / "empty"
    before = {path.name for path in tmp_path.iterdir()}
    outcome = inspect_sandbox(artifact, sandbox, clock=_clock(), attempts=_attempts())
    assert outcome.status == "inspected"
    assert outcome.payload["readOnly"] is True
    assert outcome.payload["approvalPresent"] is False
    after = {path.name for path in tmp_path.iterdir()}
    assert after == before
    assert not sandbox.exists()


def test_atomic_marker_and_idempotent_noop(tmp_path: Path) -> None:
    artifact = compile_specification(valid_automation_spec())
    sandbox = tmp_path / "box"
    approve_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    first = execute_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    second = execute_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    assert first.status == "completed"
    assert first.payload["wrote"] is True
    assert second.status == "noop"
    assert second.payload["wrote"] is False
    marker = sandbox / "markers" / "fixture-alpha.json"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["revision"] == artifact["identity"]["revision"]
    assert payload["id"] == "fixture-alpha"


def test_verify_drift_and_rollback(tmp_path: Path) -> None:
    artifact = compile_specification(valid_automation_spec())
    sandbox = tmp_path / "box"
    approve_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    execute_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    verified = verify_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    assert verified.status == "completed"
    aligned = detect_drift(artifact, sandbox, clock=_clock(), attempts=_attempts())
    assert aligned.status == "aligned"
    marker = sandbox / "markers" / "fixture-alpha.json"
    marker.write_text('{"present": false}\n', encoding="utf-8")
    drifted = detect_drift(artifact, sandbox, clock=_clock(), attempts=_attempts())
    assert drifted.status == "drifted"
    unverified = verify_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    assert unverified.status == "unverified"
    restored = rollback_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    assert restored.status == "rolled_back"
    assert verify_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts()).status == (
        "completed"
    )


def test_rollback_recovers_created_marker(tmp_path: Path) -> None:
    artifact = compile_specification(valid_automation_spec())
    sandbox = tmp_path / "box"
    approve_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    execute_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    recovered = rollback_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    assert recovered.status == "recovered"
    assert recovered.payload["restored"] == "absent"
    marker = sandbox / "markers" / "fixture-alpha.json"
    assert not marker.exists()


def test_compiled_intent_is_not_executable(tmp_path: Path) -> None:
    artifact = compile_specification(valid_spec())
    with pytest.raises(SpecProblem) as raised:
        execute_artifact(artifact, tmp_path / "box", clock=_clock(), attempts=_attempts())
    assert raised.value.code == "EXECUTION_UNSUPPORTED"


def test_parent_hop_sandbox_is_refused() -> None:
    with pytest.raises(ExecutionPathError):
        confined_sandbox(Path("..") / "outside")


def test_cli_execute_lifecycle_and_contract(tmp_path: Path) -> None:
    artifact = compile_specification(valid_automation_spec())
    intent = tmp_path / "intent.json"
    intent.write_text(json.dumps(artifact), encoding="utf-8")
    sandbox = tmp_path / "sandbox"
    code, out, err = _run(["execute", "--sandbox", str(sandbox), "contract"])
    assert code == 0
    assert err == ""
    assert json.loads(out)["executor"]["id"] == "local.sandbox"
    code, out, err = _run(["execute", "--sandbox", str(sandbox), "lifecycle", str(intent)])
    assert code == 0
    assert err == ""
    body = json.loads(out)
    assert body["ok"] is True
    code, out, err = _run(["execute", "--sandbox", str(sandbox), "inspect", str(intent)])
    assert code == 0
    inspected = json.loads(out)
    assert inspected["readOnly"] is True
    assert inspected["status"] == "inspected"


def test_cli_help_lists_execute_not_apply() -> None:
    code, out, err = _run([])
    assert code == 0
    assert "execute" in out
    assert err == ""
    with pytest.raises(SystemExit) as exited:
        main(["apply"], stdin=io.BytesIO(b""), stdout=io.StringIO(), stderr=io.StringIO())
    assert exited.value.code == 2


def test_approval_bindings_and_tamper(tmp_path: Path) -> None:
    artifact = compile_specification(valid_automation_spec())
    sandbox = tmp_path / "box"
    approve_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    path = sandbox / "approval.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["sandboxId"] = "other-sandbox"
    path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    refused = execute_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    assert refused.status == "refused"
    assert refused.payload.get("tampered") is True


def test_symlink_sandbox_refused_at_mutation(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    with pytest.raises(ExecutionPathError, match="symlink"):
        confined_sandbox(link)


def test_leftover_tmp_is_not_promoted(tmp_path: Path) -> None:
    artifact = compile_specification(valid_automation_spec())
    sandbox = tmp_path / "box"
    approve_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    markers = sandbox / "markers"
    markers.mkdir()
    leftover = markers / ".fixture-alpha.json.tmp"
    leftover.write_text("not-a-marker\n", encoding="utf-8")
    completed = execute_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    assert completed.status == "completed"
    assert not leftover.exists()
    marker = markers / "fixture-alpha.json"
    body = json.loads(marker.read_text(encoding="utf-8"))
    assert body["present"] is True


def test_evidence_integrity(tmp_path: Path) -> None:
    artifact = compile_specification(valid_automation_spec())
    sandbox = tmp_path / "sandbox"
    result = run_local_lifecycle(artifact, sandbox, clock=_clock(), attempts=_attempts())
    bundle_path = sandbox / "evidence" / "bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    from opsdevcode_specmint.runtime.executor import evidence_digest_intact

    assert evidence_digest_intact(bundle) is True
    bundle["records"] = []
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    inspected = inspect_sandbox(artifact, sandbox, clock=_clock(), attempts=_attempts())
    assert inspected.payload["evidenceIntact"] is False
    assert result["ok"] is True


def test_lifecycle_is_deterministic(tmp_path: Path) -> None:
    artifact = compile_specification(valid_automation_spec())
    first = run_local_lifecycle(artifact, tmp_path / "a", clock=_clock(), attempts=_attempts())
    second = run_local_lifecycle(artifact, tmp_path / "b", clock=_clock(), attempts=_attempts())
    assert first["records"] == second["records"]


def test_mint_authored_plan_approve_execute_verify(tmp_path: Path) -> None:
    from tests.fixtures import valid_mint_source

    from opsdevcode_specmint.mint.adapters.plan import plan_mint_ir
    from opsdevcode_specmint.mint.compile import compile_mint
    from opsdevcode_specmint.parse import load_source

    source = valid_mint_source()
    loaded = load_source(source.encode(), content_type="text/x-mint")
    artifact = compile_specification(loaded.document)
    compiled = compile_mint(source)
    assert compiled.ok is True
    assert compiled.ir is not None
    plan = plan_mint_ir(compiled.ir)
    assert plan.ok is True
    sandbox = tmp_path / "sandbox"
    approved = approve_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    executed = execute_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    verified = verify_artifact(artifact, sandbox, clock=_clock(), attempts=_attempts())
    from opsdevcode_specmint.runtime.executor import write_evidence_bundle

    evidence = write_evidence_bundle(
        artifact,
        sandbox,
        records=(approved, executed, verified),
        clock=_clock(),
        attempts=_attempts(),
    )
    assert approved.status == "approved"
    assert executed.status == "completed"
    assert verified.status == "completed"
    assert evidence.status == "completed"


def test_installed_package_execute_outside_repo(tmp_path: Path) -> None:
    import subprocess
    import venv

    artifact = compile_specification(valid_automation_spec())
    repo = Path(__file__).resolve().parents[1]
    venv_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    pip = venv_dir / "bin" / "pip"
    specmint = venv_dir / "bin" / "specmint"
    subprocess.run(
        [str(pip), "install", "--no-deps", str(repo)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [str(pip), "install", "pyyaml==6.0.2"],
        check=True,
        capture_output=True,
        text=True,
    )
    work = tmp_path / "outside"
    work.mkdir()
    intent = work / "intent.json"
    intent.write_text(json.dumps(artifact), encoding="utf-8")
    sandbox = work / "sandbox"
    completed = subprocess.run(
        [str(specmint), "execute", "--sandbox", str(sandbox), "lifecycle", str(intent)],
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    body = json.loads(completed.stdout)
    assert body["ok"] is True
    assert (sandbox / "markers" / "fixture-alpha.json").is_file()
