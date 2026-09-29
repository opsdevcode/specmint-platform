from __future__ import annotations

import io
import json
import re
import subprocess
import venv
from dataclasses import replace
from hashlib import sha256
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from opsdevcode_specmint.cli import main as specmint_main
from opsdevcode_specmint.mint.adapters.plan import plan_mint_ir
from opsdevcode_specmint.mint.adapters.registry import builtin_registry
from opsdevcode_specmint.mint.adapters.sandbox import SANDBOX_ADAPTER_ID
from opsdevcode_specmint.mint.adapters.types import (
    ARTIFACT_SET_SCHEMA,
    COMPOSITE_PLAN_SCHEMA,
    PLAN_RESULT_SCHEMA,
    TARGET_PLAN_SCHEMA,
    content_digest,
)
from opsdevcode_specmint.mint.cli import _build_parser, main
from opsdevcode_specmint.mint.compile import compile_mint
from opsdevcode_specmint.mint.errors import MintError
from opsdevcode_specmint.mint.project import catalog_digest

_CASES = Path(__file__).resolve().parents[1] / "specification" / "mint" / "v0" / "conformance"
_EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "projects"
_REPO = Path(__file__).resolve().parents[1]
_UNSTABLE = re.compile(
    r"https?://|[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}"
    r"|/(?:Users|home|tmp|var)/"
)


def _run(argv: list[str], *, stdin: str = "") -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    code = main(argv, stdin=io.StringIO(stdin), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def _run_specmint(argv: list[str], *, stdin: bytes = b"") -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    code = specmint_main(argv, stdin=io.BytesIO(stdin), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def _marker_source() -> str:
    return (_CASES / "programs" / "C001-valid-local-marker.mint").read_text(encoding="utf-8")


def _choices() -> dict[str, object]:
    parser = _build_parser()
    action = parser._subparsers._group_actions[0]
    return dict(action.choices)


def test_help_lists_adapter_commands() -> None:
    code, out, err = _run([])
    assert code == 0
    for name in ("adapters", "plan"):
        assert name in out
    assert err == ""
    assert "apply" not in _choices()


def test_apply_is_unknown_command() -> None:
    with pytest.raises(SystemExit) as exited:
        main(["apply"])
    assert exited.value.code == 2
    with pytest.raises(SystemExit) as specmint_exited:
        specmint_main(
            ["mint", "apply"], stdin=io.BytesIO(b""), stdout=io.StringIO(), stderr=io.StringIO()
        )
    assert specmint_exited.value.code == 2


def test_adapters_list_is_explicit_builtin() -> None:
    code, out, err = _run(["adapters", "list"])
    assert code == 0
    assert err == ""
    body = json.loads(out)
    assert body["ok"] is True
    assert body["registry"] == "builtin"
    ids = [item["adapterId"] for item in body["adapters"]]
    assert SANDBOX_ADAPTER_ID in ids
    assert "repo.branch_protection" in ids
    assert ids == sorted(ids)
    sandbox = next(item for item in body["adapters"] if item["adapterId"] == SANDBOX_ADAPTER_ID)
    assert sandbox["mode"] == "plan-only"
    assert sandbox["mutation"] == "forbidden"
    assert sandbox["schema"] == "mint.adapter/v0"
    assert "local.sandbox" in sandbox["targetKinds"]


def test_adapters_inspect_named_manifest() -> None:
    code, out, err = _run(["adapters", "inspect", SANDBOX_ADAPTER_ID])
    assert code == 0
    assert err == ""
    body = json.loads(out)
    assert body == builtin_registry().inspect(SANDBOX_ADAPTER_ID).to_canonical_dict()


def test_adapters_inspect_unknown_fails_closed() -> None:
    code, out, err = _run(["adapters", "inspect", "aws.account.live"])
    assert code == 1
    assert out == ""
    problem = json.loads(err)
    assert problem["code"] == "MINT_ADAPTER"
    assert "aws.account.live" in problem["message"]


def test_plan_emits_distinct_schema_identities() -> None:
    source = _marker_source()
    compiled = compile_mint(source)
    assert compiled.ir is not None
    code, out, err = _run(["plan", "-"], stdin=source)
    assert code == 0
    assert err == ""
    planned = plan_mint_ir(compiled.ir)
    assert out.encode("utf-8") == planned.canonical_bytes()
    body = json.loads(out)
    assert body["kind"] == "MintPlanResult"
    assert body["schema"] == PLAN_RESULT_SCHEMA
    assert body["plan"]["schema"] == COMPOSITE_PLAN_SCHEMA
    assert body["plan"]["kind"] == "MintCompositePlan"
    assert body["plan"]["plans"][0]["schema"] == TARGET_PLAN_SCHEMA
    assert body["artifacts"]["schema"] == ARTIFACT_SET_SCHEMA
    assert body["ok"] is True
    assert body["provenance"]["irDigest"] == compiled.digest
    assert body["provenance"]["catalogDigest"] == catalog_digest()
    operation = body["plan"]["plans"][0]["operations"][0]
    assert operation["operationId"] == content_digest(
        {
            "action": operation["action"],
            "desired": operation["desired"],
            "logicalName": operation["logicalName"],
            "targetId": operation["targetId"],
        }
    )
    artifact = body["artifacts"]["items"][0]
    assert artifact["path"] == "markers/fixture-alpha.json"
    assert artifact["mediaType"] == "application/json"
    assert artifact["classification"] == "sandbox-marker"
    assert '"present":true' in artifact["text"].replace(" ", "")
    assert artifact["digest"].startswith("sha256:")
    assert artifact["identity"] == f"{SANDBOX_ADAPTER_ID}/markers/fixture-alpha.json"
    assert artifact["provenance"]["operationId"] == operation["operationId"]


def test_plan_is_deterministic() -> None:
    source = _marker_source()
    first = _run(["plan", "-"], stdin=source)
    second = _run(["plan", "-"], stdin=source)
    assert first == second
    assert first[0] == 0
    blob = first[1]
    assert _UNSTABLE.search(blob) is None
    assert "timestamp" not in blob.lower()
    assert "uuid" not in blob.lower()


def test_plan_does_not_mutate_filesystem(tmp_path: Path) -> None:
    source = _marker_source()
    path = tmp_path / "marker.mint"
    path.write_text(source, encoding="utf-8")
    before = {(item.relative_to(tmp_path), item.stat().st_mtime_ns) for item in tmp_path.rglob("*")}
    code, out, err = _run(["plan", str(path)])
    assert code == 0
    assert err == ""
    assert "fixture-alpha" in out
    after = {(item.relative_to(tmp_path), item.stat().st_mtime_ns) for item in tmp_path.rglob("*")}
    assert before == after


def test_artifacts_cli_writes_confined_atomic_files(tmp_path: Path) -> None:
    source = _marker_source()
    mint_path = tmp_path / "marker.mint"
    mint_path.write_text(source, encoding="utf-8")
    dest = tmp_path / "out"
    code, out, err = _run(["plan", str(mint_path), "--artifacts", str(dest)])
    assert code == 0
    assert err == ""
    marker = dest / "markers" / "fixture-alpha.json"
    assert marker.is_file()
    body = json.loads(marker.read_text(encoding="utf-8"))
    assert body["id"] == "fixture-alpha"
    assert body["present"] is True
    planned = json.loads(out)
    assert (
        planned["artifacts"]["items"][0]["digest"]
        == "sha256:" + sha256(marker.read_bytes()).hexdigest()
    )
    assert not (tmp_path / ".out.mint-plan.tmp").exists()
    assert not list(dest.rglob("*.tmp"))


def test_artifacts_refuse_parent_escape(tmp_path: Path) -> None:
    source = _marker_source()
    mint_path = tmp_path / "marker.mint"
    mint_path.write_text(source, encoding="utf-8")
    code, out, err = _run(["plan", str(mint_path), "--artifacts", "../escape"])
    assert code == 1
    assert out == ""
    assert json.loads(err)["code"] == "MINT_PATH"


def test_unaccounted_capability_fails_closed() -> None:
    ir = compile_mint(_marker_source()).ir
    assert ir is not None
    extra = replace(
        ir,
        capabilities=(*ir.capabilities, ("repo.branch_protection", "v1alpha1")),
    )
    try:
        plan_mint_ir(extra)
    except MintError as exc:
        assert exc.diagnostic.code == "MINT_ACCOUNTING"
        assert "repo.branch_protection" in exc.diagnostic.message
    else:
        raise AssertionError("expected MINT_ACCOUNTING")


def test_route_unknown_capability_fails_closed() -> None:
    ir = compile_mint(_marker_source()).ir
    assert ir is not None
    broken = replace(ir, verb_type="repo.branch_protection", verb_version="v1alpha1")
    try:
        plan_mint_ir(broken)
    except MintError as exc:
        assert exc.diagnostic.code == "MINT_ACCOUNTING"
        assert "repo.branch_protection" in exc.diagnostic.message
    else:
        raise AssertionError("expected MINT_ACCOUNTING")


def test_credentials_in_target_fail_closed() -> None:
    ir = compile_mint(_marker_source()).ir
    assert ir is not None
    poisoned = replace(
        ir,
        targets=(
            {
                "fqid": ir.targets[0]["fqid"],
                "id": ir.targets[0]["id"],
                "kind": ir.targets[0]["kind"],
                "token": "secret",
            },
        ),
    )
    try:
        plan_mint_ir(poisoned)
    except MintError as exc:
        assert exc.diagnostic.code == "MINT_ADAPTER"
        assert "credentials" in exc.diagnostic.message
    else:
        raise AssertionError("expected MINT_ADAPTER")


def test_host_path_target_fails_closed() -> None:
    ir = compile_mint(_marker_source()).ir
    assert ir is not None
    poisoned = replace(
        ir,
        targets=(
            {
                "fqid": "/Users/ericskaggs/secret",
                "id": "fixture-alpha",
                "kind": "sandbox",
            },
        ),
    )
    try:
        plan_mint_ir(poisoned)
    except MintError as exc:
        assert exc.diagnostic.code == "MINT_PLAN"
        assert "host paths" in exc.diagnostic.message
    else:
        raise AssertionError("expected MINT_PLAN")


def test_explicit_adapter_mismatch_fails_closed() -> None:
    source = _marker_source()
    code, out, err = _run(["plan", "--adapter", "missing.adapter", "-"], stdin=source)
    assert code == 1
    assert out == ""
    assert json.loads(err)["code"] == "MINT_ACCOUNTING"


def test_specmint_forwards_plan_and_adapters() -> None:
    source = _marker_source()
    list_code, list_out, list_err = _run_specmint(["mint", "adapters", "list"])
    assert list_code == 0
    assert list_err == ""
    assert SANDBOX_ADAPTER_ID in list_out
    plan_code, plan_out, plan_err = _run_specmint(
        ["mint", "plan", "-"], stdin=source.encode("utf-8")
    )
    assert plan_code == 0
    assert plan_err == ""
    assert json.loads(plan_out)["kind"] == "MintPlanResult"


def test_installed_entry_points_forward_plan() -> None:
    names = {item.name for item in entry_points(group="console_scripts")}
    if "mint" not in names:
        return
    mint_main = next(
        item for item in entry_points(group="console_scripts") if item.name == "mint"
    ).load()
    out, err = io.StringIO(), io.StringIO()
    code = mint_main(["adapters", "list"], stdin=io.StringIO(""), stdout=out, stderr=err)
    assert code == 0, err.getvalue()
    assert SANDBOX_ADAPTER_ID in out.getvalue()


def test_installed_package_plan_outside_repo(tmp_path: Path) -> None:
    venv_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(venv_dir)
    pip = venv_dir / "bin" / "pip"
    mint = venv_dir / "bin" / "mint"
    subprocess.run(
        [str(pip), "install", "--no-deps", str(_REPO)],
        check=True,
        capture_output=True,
        text=True,
    )
    work = tmp_path / "outside"
    work.mkdir()
    (work / "main.mint").write_text(_marker_source(), encoding="utf-8")
    completed = subprocess.run(
        [str(mint), "plan", "main.mint"],
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    body = json.loads(completed.stdout)
    assert body["schema"] == PLAN_RESULT_SCHEMA
    assert body["artifacts"]["items"][0]["path"] == "markers/fixture-alpha.json"
    assert not (work / "markers").exists()
    listed = subprocess.run(
        [str(mint), "adapters", "list"],
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
    )
    assert listed.returncode == 0, listed.stderr
    assert "repo.branch_protection" in listed.stdout
    snapshot = {
        "schema": "mint.repository-snapshot/v0",
        "kind": "MintRepositorySnapshot",
        "identity": {"owner": "opsdevcode", "name": "specmint"},
        "providerKind": "repo.github",
        "settings": {},
        "rules": {},
        "security": {},
        "files": [],
        "completeness": {
            "files": "complete",
            "rules": "complete",
            "security": "complete",
            "settings": "complete",
        },
        "unknown": [],
        "unavailable": [],
        "unsupported": [],
        "redacted": [],
    }
    snap_path = work / "snap.json"
    snap_path.write_text(json.dumps(snapshot) + "\n", encoding="utf-8")
    checked = subprocess.run(
        [str(mint), "repository", "snapshot", "check", str(snap_path)],
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)["schema"] == "mint.repository-snapshot/v0"


def test_local_marker_example_plans() -> None:
    example = _EXAMPLES / "local-marker"
    code, out, err = _run(["plan", "--project", str(example), "--locked"])
    assert code == 0
    assert err == ""
    expected = (example / "plan.json").read_text(encoding="utf-8")
    assert out == expected


def test_license_is_apache() -> None:
    text = (_REPO / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in text
    assert "LicenseRef-Proprietary" not in text


def test_registry_rejects_dynamic_loading() -> None:
    registry = builtin_registry()
    assert len(registry.adapters) == 5
    assert {item.manifest.registry for item in registry.adapters} == {"builtin"}
