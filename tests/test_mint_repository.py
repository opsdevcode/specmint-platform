from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest

from opsdevcode_specmint.cli import main as specmint_main
from opsdevcode_specmint.mint.adapters.plan import plan_mint_ir
from opsdevcode_specmint.mint.adapters.snapshot import parse_snapshot
from opsdevcode_specmint.mint.adapters.types import digest_bytes
from opsdevcode_specmint.mint.cli import _build_parser, main
from opsdevcode_specmint.mint.compile import compile_mint
from opsdevcode_specmint.mint.errors import MintError

_EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "projects"


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


def _mint(
    *,
    owner: str = "opsdevcode",
    name: str = "specmint",
    target: str = "primary",
    use: str = "repo.branch_protection",
    extras: str = "",
    config_extra: str = "",
    intent: str = "Require governed GitHub repository settings",
) -> str:
    caps = f"\n  capabilities {extras}" if extras else ""
    return f'''mint v0
namespace example.repo
target {target} {{
  kind repo.github
  config {{
    owner "{owner}"
    name "{name}"{config_extra}
  }}
}}
automation as-repo-guard-1 {{
  owner "platform@opsdevcode.com"
  intent "{intent}"
  use {use} v1alpha1{caps}
  apply {target}
  evidence branch.protection
  require authorization
  forbid mutation
  status draft
}}
'''


def _complete(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": "mint.repository-snapshot/v0",
        "kind": "MintRepositorySnapshot",
        "identity": {"owner": "opsdevcode", "name": "specmint"},
        "providerKind": "repo.github",
        "settings": {
            "archived": False,
            "allowMergeCommit": True,
            "allowRebaseMerge": False,
            "allowSquashMerge": True,
            "defaultBranch": "main",
            "deleteBranchOnMerge": False,
            "visibility": "private",
        },
        "rules": {
            "allowDeletions": False,
            "allowForcePushes": False,
            "pullRequestRequired": False,
            "requireConversationResolution": False,
            "requiredApprovingReviewCount": 0,
            "requiredStatusChecks": [],
        },
        "security": {
            "dependencyAlerts": False,
            "pushProtection": False,
            "secretScanning": False,
        },
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
    document.update(overrides)
    parsed = parse_snapshot(document, source="memory")
    return parsed.document


def _write_snapshot(path: Path, **overrides: object) -> Path:
    path.write_text(json.dumps(_complete(**overrides), indent=2, sort_keys=True) + "\n")
    return path


def test_help_lists_repository_snapshot_check() -> None:
    code, out, err = _run([])
    assert code == 0
    assert "repository" in out
    assert err == ""
    assert "apply" not in dict(_build_parser()._subparsers._group_actions[0].choices)


def test_snapshot_check_emits_canonical_digest(tmp_path: Path) -> None:
    path = _write_snapshot(tmp_path / "snap.json")
    code, out, err = _run(["repository", "snapshot", "check", str(path)])
    assert code == 0
    assert err == ""
    body = json.loads(out)
    assert body["schema"] == "mint.repository-snapshot/v0"
    assert body["digest"].startswith("sha256:")
    again = parse_snapshot(body, source="stdout")
    assert again.digest == body["digest"]


def test_specmint_forwards_snapshot_check(tmp_path: Path) -> None:
    path = _write_snapshot(tmp_path / "snap.json")
    code, out, err = _run_specmint(["mint", "repository", "snapshot", "check", str(path)])
    assert code == 0
    assert err == ""
    assert json.loads(out)["kind"] == "MintRepositorySnapshot"


def test_plan_single_repo_pr_and_checks(tmp_path: Path) -> None:
    source = _mint(
        config_extra="""
    required_checks {
      lint true
      test true
    }"""
    )
    snap = _write_snapshot(tmp_path / "snap.json")
    (tmp_path / "main.mint").write_text(source)
    code, out, err = _run(["plan", str(tmp_path / "main.mint"), "--snapshot", str(snap)])
    assert code == 0, err
    assert err == ""
    body = json.loads(out)
    assert body["ok"] is True
    actions = [item["action"] for item in body["plan"]["plans"][0]["operations"]]
    assert actions == ["rules.ensure", "required_checks.ensure"]
    assert "timestamp" not in out.lower()


def test_plan_org_security_multi_repo(tmp_path: Path) -> None:
    source = """mint v0
namespace example.org
target alpha {
  kind repo.github
  config {
    owner "opsdevcode"
    name "alpha"
  }
}
target zeta {
  kind repo.github
  config {
    owner "opsdevcode"
    name "zeta"
  }
}
automation as-repo-guard-1 {
  owner "platform@opsdevcode.com"
  intent "Require org security controls on two repositories"
  use repo.security v1alpha1
  apply zeta, alpha
  evidence branch.protection
  require authorization
  forbid mutation
  status draft
}
"""
    a = _write_snapshot(tmp_path / "a.json", identity={"owner": "opsdevcode", "name": "alpha"})
    z = _write_snapshot(tmp_path / "z.json", identity={"owner": "opsdevcode", "name": "zeta"})
    (tmp_path / "main.mint").write_text(source)
    first = _run(["plan", str(tmp_path / "main.mint"), "--snapshot", str(z), "--snapshot", str(a)])
    second = _run(["plan", str(tmp_path / "main.mint"), "--snapshot", str(a), "--snapshot", str(z)])
    assert first == second
    assert first[0] == 0, first[2]
    plans = json.loads(first[1])["plan"]["plans"]
    names = [item["target"]["id"] for item in plans]
    assert names == ["alpha", "zeta"]
    assert all(item["operations"][0]["action"] == "security.ensure" for item in plans)


def test_plan_managed_policy_file(tmp_path: Path) -> None:
    source = _mint(
        use="repo.managed_file",
        config_extra='''
    file_path "SECURITY.md"
    file_content "# security\\n"
    file_mode "0644"''',
        intent="Ensure a managed security policy file",
    )
    snap = _write_snapshot(tmp_path / "snap.json")
    (tmp_path / "main.mint").write_text(source)
    dest = tmp_path / "artifacts"
    code, out, err = _run(
        ["plan", str(tmp_path / "main.mint"), "--snapshot", str(snap), "--artifacts", str(dest)]
    )
    assert code == 0, err
    body = json.loads(out)
    assert body["plan"]["plans"][0]["operations"][0]["action"] == "file.ensure"
    text = dest / "files" / "opsdevcode" / "specmint" / "SECURITY.md"
    assert text.read_text(encoding="utf-8") == "# security\n"
    assert not (tmp_path / "SECURITY.md").exists()


def test_fully_satisfied_empty_plan(tmp_path: Path) -> None:
    source = _mint()
    snap = _write_snapshot(
        tmp_path / "snap.json",
        rules={
            "allowDeletions": False,
            "allowForcePushes": False,
            "pullRequestRequired": True,
            "requireConversationResolution": True,
            "requiredApprovingReviewCount": 1,
            "requiredStatusChecks": [],
        },
    )
    compiled = compile_mint(source)
    assert compiled.ir is not None
    snapshot = parse_snapshot(json.loads(snap.read_text()), source=str(snap))
    planned = plan_mint_ir(compiled.ir, snapshots=(snapshot,))
    assert planned.ok is True
    assert planned.plans[0].operations == ()
    assert any(item.classification == "plan-summary" for item in planned.artifacts.items)


def test_incomplete_snapshot_fail_closed(tmp_path: Path) -> None:
    source = _mint()
    snap = _write_snapshot(
        tmp_path / "snap.json",
        completeness={
            "files": "complete",
            "rules": "unknown",
            "security": "complete",
            "settings": "complete",
        },
    )
    (tmp_path / "main.mint").write_text(source)
    code, out, err = _run(["plan", str(tmp_path / "main.mint"), "--snapshot", str(snap)])
    assert code == 1
    assert out == ""
    problem = json.loads(err)
    assert problem["code"] == "MINT_SNAPSHOT"
    assert "incomplete" in problem["message"]


def test_missing_snapshot_fails() -> None:
    source = _mint()
    code, out, err = _run(["plan", "-"], stdin=source)
    assert code == 1
    assert json.loads(err)["code"] == "MINT_SNAPSHOT"
    assert "missing" in json.loads(err)["message"]


def test_duplicate_snapshot_fails(tmp_path: Path) -> None:
    source = _mint()
    one = _write_snapshot(tmp_path / "one.json")
    two = _write_snapshot(tmp_path / "two.json")
    (tmp_path / "main.mint").write_text(source)
    code, out, err = _run(
        ["plan", str(tmp_path / "main.mint"), "--snapshot", str(one), "--snapshot", str(two)]
    )
    assert code == 1
    assert json.loads(err)["code"] == "MINT_SNAPSHOT"
    assert "duplicate" in json.loads(err)["message"]


def test_mismatched_snapshot_fails(tmp_path: Path) -> None:
    source = _mint()
    snap = _write_snapshot(
        tmp_path / "other.json", identity={"owner": "opsdevcode", "name": "other"}
    )
    (tmp_path / "main.mint").write_text(source)
    code, out, err = _run(["plan", str(tmp_path / "main.mint"), "--snapshot", str(snap)])
    assert code == 1
    assert json.loads(err)["code"] == "MINT_SNAPSHOT"


def test_malformed_snapshot_fails(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{}\n")
    code, out, err = _run(["repository", "snapshot", "check", str(path)])
    assert code == 1
    assert json.loads(err)["code"] == "MINT_SNAPSHOT"


def test_invalid_identity_url_fails() -> None:
    source = _mint(owner="https", name="github.com")
    compiled = compile_mint(source)
    assert compiled.ir is not None
    try:
        plan_mint_ir(compiled.ir, snapshots=())
    except MintError as exc:
        assert exc.diagnostic.code == "MINT_IDENTITY"
    else:
        raise AssertionError("expected identity failure")


def test_unsafe_managed_file_path_fails(tmp_path: Path) -> None:
    source = _mint(
        use="repo.managed_file",
        config_extra='''
    file_path "../secret"
    file_content "x"''',
        intent="Refuse path traversal in managed files",
    )
    snap = _write_snapshot(tmp_path / "snap.json")
    (tmp_path / "main.mint").write_text(source)
    code, out, err = _run(["plan", str(tmp_path / "main.mint"), "--snapshot", str(snap)])
    assert code == 1
    assert json.loads(err)["code"] == "MINT_PATH"


def test_conflicting_unknown_github_field_fails(tmp_path: Path) -> None:
    source = _mint(config_extra="\n    wiki true")
    snap = _write_snapshot(tmp_path / "snap.json")
    (tmp_path / "main.mint").write_text(source)
    code, out, err = _run(["plan", str(tmp_path / "main.mint"), "--snapshot", str(snap)])
    assert code == 1
    assert json.loads(err)["code"] == "MINT_PLAN"
    assert "wiki" in json.loads(err)["message"]


def test_e2e_mint_to_artifacts(tmp_path: Path) -> None:
    source = _mint(
        extras="repo.settings v1alpha1, repo.security v1alpha1",
        config_extra="""
    visibility "private"
    default_branch "main"
    delete_branch_on_merge true""",
        intent="Govern settings, rules, and security from one Mint program",
    )
    snap = _write_snapshot(tmp_path / "snap.json")
    (tmp_path / "main.mint").write_text(source)
    dest = tmp_path / "out"
    output = tmp_path / "plan.json"
    code, out, err = _run(
        [
            "plan",
            str(tmp_path / "main.mint"),
            "--snapshot",
            str(snap),
            "--artifacts",
            str(dest),
            "--output",
            str(output),
        ]
    )
    assert code == 0, err
    body = json.loads(out)
    assert body["schema"] == "mint.plan-result/v0"
    assert json.loads(output.read_text()) == body
    assert (dest / "policy" / "opsdevcode" / "specmint.json").is_file()
    assert (dest / "summary" / "opsdevcode" / "specmint.json").is_file()
    actions = sorted(
        item["action"] for plan in body["plan"]["plans"] for item in plan["operations"]
    )
    assert "rules.ensure" in actions
    assert "settings.update" in actions
    assert "security.ensure" in actions


def test_example_repository_governance_plans() -> None:
    example = _EXAMPLES / "repository-governance"
    snap = example / "snapshots" / "specmint.json"
    code, out, err = _run(["plan", "--project", str(example), "--locked", "--snapshot", str(snap)])
    assert code == 0, err
    expected = (example / "plan.json").read_text(encoding="utf-8")
    assert out == expected


def test_plan_does_not_call_github(tmp_path: Path) -> None:
    source = _mint()
    snap = _write_snapshot(tmp_path / "snap.json")
    compiled = compile_mint(source)
    assert compiled.ir is not None
    snapshot = parse_snapshot(json.loads(snap.read_text()), source=str(snap))
    planned = plan_mint_ir(compiled.ir, snapshots=(snapshot,))
    blob = planned.canonical_bytes().decode("utf-8")
    assert "api.github" not in blob
    assert "token" not in blob.lower()
    assert digest_bytes(b"x").startswith("sha256:")


def test_unsupported_snapshot_fail_closed(tmp_path: Path) -> None:
    source = _mint()
    snap = _write_snapshot(
        tmp_path / "snap.json",
        completeness={
            "files": "complete",
            "rules": "unsupported",
            "security": "complete",
            "settings": "complete",
        },
    )
    (tmp_path / "main.mint").write_text(source)
    code, out, err = _run(["plan", str(tmp_path / "main.mint"), "--snapshot", str(snap)])
    assert code == 1
    assert out == ""
    problem = json.loads(err)
    assert problem["code"] == "MINT_SNAPSHOT"
    assert "unsupported" in problem["message"]


def test_invalid_required_checks_fail_closed(tmp_path: Path) -> None:
    source = _mint(
        config_extra="""
    required_checks {
      lint true
    }"""
    )
    snap = _write_snapshot(
        tmp_path / "snap.json",
        rules={
            "allowDeletions": False,
            "allowForcePushes": False,
            "pullRequestRequired": True,
            "requireConversationResolution": True,
            "requiredApprovingReviewCount": 1,
            "requiredStatusChecks": {"lint": True},
        },
    )
    (tmp_path / "main.mint").write_text(source)
    code, out, err = _run(["plan", str(tmp_path / "main.mint"), "--snapshot", str(snap)])
    assert code == 1
    assert json.loads(err)["code"] == "MINT_SNAPSHOT"
    assert "invalid" in json.loads(err)["message"]


def test_plan_ignores_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_not_a_real_token")
    monkeypatch.setenv("HOME", "/Users/secret-home")
    source = _mint()
    snap = _write_snapshot(tmp_path / "snap.json")
    (tmp_path / "main.mint").write_text(source)
    code, out, err = _run(["plan", str(tmp_path / "main.mint"), "--snapshot", str(snap)])
    assert code == 0, err
    lowered = out.lower()
    assert "ghp_" not in lowered
    assert "secret-home" not in lowered
    assert os.environ["GITHUB_TOKEN"] == "ghp_not_a_real_token"


def test_repository_plan_is_deterministic(tmp_path: Path) -> None:
    source = _mint()
    snap = _write_snapshot(tmp_path / "snap.json")
    (tmp_path / "main.mint").write_text(source)
    argv = ["plan", str(tmp_path / "main.mint"), "--snapshot", str(snap)]
    first = _run(argv)
    second = _run(argv)
    assert first == second
    assert first[0] == 0, first[2]


def test_apply_remains_unknown_on_product_cli() -> None:
    with pytest.raises(SystemExit) as exited:
        specmint_main(
            ["mint", "apply"], stdin=io.BytesIO(b""), stdout=io.StringIO(), stderr=io.StringIO()
        )
    assert exited.value.code == 2
