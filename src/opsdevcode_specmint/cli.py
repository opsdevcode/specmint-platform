"""CLI adapter over the specification compiler core and local executor."""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import IO, Any, TextIO

from opsdevcode_specmint import __version__
from opsdevcode_specmint.compiler import (
    compile_specification,
    inspect_artifact,
    validate_specification,
)
from opsdevcode_specmint.errors import DocumentParseError, SpecProblem
from opsdevcode_specmint.parse import decode_body, decode_path, media_type_for_format
from opsdevcode_specmint.runtime.contract import ATTEMPT_ID_PROVIDER, CLOCK, EXECUTOR_CONTRACT
from opsdevcode_specmint.runtime.executor import (
    approve_artifact,
    detect_drift,
    execute_artifact,
    inspect_sandbox,
    rollback_artifact,
    verify_artifact,
    write_evidence_bundle,
)
from opsdevcode_specmint.runtime.lifecycle import run_local_lifecycle


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: IO[bytes] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.show_version or args.command == "version":
        out.write(f"specmint {__version__}\n")
        return 0
    if args.command is None:
        parser.print_help(out)
        return 0
    try:
        if args.command == "serve":
            from opsdevcode_specmint.main import run

            run()
            return 0
        if args.command == "platform":
            from opsdevcode_specmint.platform.migrate import main as migrate_main

            if args.platform_verb == "migrate":
                return migrate_main()
            err.write("set platform verb: migrate\n")
            return 2
        if args.command == "mint":
            from opsdevcode_specmint.mint.cli import main as mint_main

            raw_in = b"" if stdin is None else stdin.read()
            text = raw_in.decode("utf-8") if isinstance(raw_in, bytes | bytearray) else str(raw_in)
            return mint_main(list(args.mint_args), stdin=io.StringIO(text), stdout=out, stderr=err)
        if args.command == "execute":
            return _run_execute(args, stdin=stdin, stdout=out)
        document = _load_document(args.path, stdin=stdin, format=getattr(args, "format", None))
        if args.command == "validate":
            payload = validate_specification(document)
        elif args.command == "compile":
            payload = compile_specification(document)
        else:
            payload = inspect_artifact(document)
        out.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return 0
    except SpecProblem as exc:
        err.write(json.dumps(exc.as_dict(), indent=2, sort_keys=True) + "\n")
        return 1


def _run_execute(args: argparse.Namespace, *, stdin: IO[bytes] | None, stdout: TextIO) -> int:
    sandbox = Path(args.sandbox)
    verb = args.execute_verb
    if verb == "contract":
        stdout.write(json.dumps(EXECUTOR_CONTRACT, indent=2, sort_keys=True) + "\n")
        return 0
    document = (
        None
        if verb == "inspect" and args.path is None
        else _load_document(args.path, stdin=stdin, format=getattr(args, "format", None))
    )
    if verb == "lifecycle":
        payload = run_local_lifecycle(
            _require_document(document), sandbox, clock=CLOCK, attempts=ATTEMPT_ID_PROVIDER
        )
        stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return 0 if payload["ok"] else 1
    clock = CLOCK
    attempts = ATTEMPT_ID_PROVIDER
    if verb == "approve":
        outcome = approve_artifact(
            _require_document(document), sandbox, clock=clock, attempts=attempts
        )
    elif verb == "inspect":
        outcome = inspect_sandbox(document, sandbox, clock=clock, attempts=attempts)
    elif verb == "run":
        outcome = execute_artifact(
            _require_document(document), sandbox, clock=clock, attempts=attempts
        )
    elif verb == "verify":
        outcome = verify_artifact(
            _require_document(document), sandbox, clock=clock, attempts=attempts
        )
    elif verb == "drift":
        outcome = detect_drift(_require_document(document), sandbox, clock=clock, attempts=attempts)
    elif verb == "rollback":
        outcome = rollback_artifact(
            _require_document(document), sandbox, clock=clock, attempts=attempts
        )
    else:
        loaded = _require_document(document)
        inspect_first = inspect_sandbox(loaded, sandbox, clock=clock, attempts=attempts)
        outcome = write_evidence_bundle(
            loaded,
            sandbox,
            records=(inspect_first,),
            clock=clock,
            attempts=attempts,
        )
    body = outcome.to_canonical_dict()
    stdout.write(json.dumps(body, indent=2, sort_keys=True) + "\n")
    if outcome.status in {"refused", "unverified", "drifted"}:
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="specmint",
        description=(
            "Validate and compile governed specifications; run the local sandbox executor."
        ),
    )
    parser.add_argument(
        "--version",
        action="store_true",
        dest="show_version",
        help="Print the SpecMint version",
    )
    sub = parser.add_subparsers(dest="command")
    for name, help_text in (
        ("validate", "Check a DeliverySpecification or AutomationSpecification"),
        ("compile", "Emit a closed CompiledIntent or AutomationIntent"),
        ("inspect", "Verify a compiled artifact revision"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument(
            "path", help="Mint path (default), JSON, YAML, Markdown, or - for stdin"
        )
        command.add_argument(
            "--format",
            choices=("mint", "json", "yaml", "markdown"),
            default=None,
            help="Authoring format. Default: suffix, or mint for stdin",
        )
    sub.add_parser("version", help="Print the SpecMint version")
    sub.add_parser("serve", help="Run the HTTP adapter")
    platform = sub.add_parser("platform", help="Platform operator commands")
    platform_sub = platform.add_subparsers(dest="platform_verb", required=True)
    platform_sub.add_parser("migrate", help="Apply durable store SQL migrations")
    mint_cmd = sub.add_parser("mint", help="Run the offline Mint language CLI")
    mint_cmd.add_argument("mint_args", nargs=argparse.REMAINDER, help="Arguments forwarded to mint")
    execute = sub.add_parser(
        "execute",
        help="Local sandbox executor (approve, inspect, run, verify, drift, rollback)",
    )
    execute.add_argument(
        "--sandbox",
        required=True,
        help="Confined sandbox directory for markers, approval, and evidence",
    )
    execute_sub = execute.add_subparsers(dest="execute_verb", required=True)
    for verb, help_text, needs_path, path_optional in (
        ("contract", "Print the versioned local executor contract", False, False),
        ("approve", "Record a digest-bound local approval", True, False),
        ("inspect", "Read-only sandbox inspection", True, True),
        ("run", "Execute the approved local sandbox marker", True, False),
        ("verify", "Post-execution marker verification", True, False),
        ("drift", "Detect marker drift against the approved digest", True, False),
        ("rollback", "Restore the previous marker or recover to absent", True, False),
        ("evidence", "Write a canonical evidence bundle", True, False),
        ("lifecycle", "Run the end-to-end local lifecycle fixture", True, False),
    ):
        verb_parser = execute_sub.add_parser(verb, help=help_text)
        if needs_path and path_optional:
            verb_parser.add_argument(
                "path",
                nargs="?",
                help="AutomationIntent or Mint path, or - for stdin",
            )
        elif needs_path:
            verb_parser.add_argument(
                "path",
                help="AutomationIntent or Mint path, or - for stdin",
            )
        if needs_path:
            verb_parser.add_argument(
                "--format",
                choices=("mint", "json", "yaml", "markdown"),
                default=None,
                help="Input format. Default: suffix, or mint for stdin",
            )
    return parser


def _require_document(document: dict[str, Any] | None) -> dict[str, Any]:
    if document is None:
        raise DocumentParseError("set execute path to an AutomationIntent file or -")
    return document


def _load_document(
    path_arg: str | None,
    *,
    stdin: IO[bytes] | None,
    format: str | None = None,
) -> dict[str, Any]:
    if path_arg is None:
        raise DocumentParseError("set execute path to an AutomationIntent file or -")
    if path_arg == "-":
        raw = (stdin or sys.stdin.buffer).read()
        media = media_type_for_format(format) if format else None
        return decode_body(raw, media)
    return decode_path(Path(path_arg), format=format)
