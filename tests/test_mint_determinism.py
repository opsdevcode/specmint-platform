from __future__ import annotations

from pathlib import Path

from opsdevcode_specmint.mint.catalog import CapabilityDecl
from opsdevcode_specmint.mint.compile import SourceUnit, compile_program
from opsdevcode_specmint.mint.conformance import compile_conformance_case, load_conformance_cases
from opsdevcode_specmint.mint.extensions import SAMPLE_EXTENSION, Extension


def test_input_file_order_does_not_change_digest() -> None:
    case = next(item for item in load_conformance_cases() if item.case_id == "C026-imported-symbol")
    forward = compile_program(root=case.root, units=case.units, extensions=())
    reversed_units = tuple(reversed(case.units))
    backward = compile_program(root=case.root, units=reversed_units, extensions=())
    assert forward.ok and backward.ok
    assert forward.digest == backward.digest
    assert forward.ir is not None
    assert forward.ir.canonical_bytes() == backward.ir.canonical_bytes()  # type: ignore[union-attr]


def test_extension_registry_order_does_not_change_digest() -> None:
    other = Extension(
        namespace="ext.other",
        version="v1alpha1",
        capabilities=(CapabilityDecl("ext.other.mark", "v1alpha1", frozenset({"sandbox"})),),
    )
    case = next(
        item for item in load_conformance_cases() if item.case_id == "C037-recognized-extension"
    )
    first = compile_program(root=case.root, units=case.units, extensions=(SAMPLE_EXTENSION, other))
    second = compile_program(root=case.root, units=case.units, extensions=(other, SAMPLE_EXTENSION))
    assert first.digest == second.digest


def test_catalog_like_capability_order_is_sorted_in_ir() -> None:
    case = next(item for item in load_conformance_cases() if item.case_id == "C035-multi-target")
    result = compile_conformance_case(case)
    assert result.ir is not None
    types = [item["type"] for item in result.ir.to_canonical_dict()["unit"]["capabilities"]]
    assert types == sorted(types)


def test_repeated_canonical_bytes_and_digest() -> None:
    case = next(item for item in load_conformance_cases() if item.case_id == "C036-cross-platform")
    first = compile_conformance_case(case)
    second = compile_conformance_case(case)
    assert first.digest == second.digest
    assert first.ir is not None and second.ir is not None
    assert first.ir.canonical_bytes() == second.ir.canonical_bytes()
    assert first.digest == first.ir.digest()


def test_catalog_identities_are_sorted_regardless_of_declaration_order() -> None:
    case = next(item for item in load_conformance_cases() if item.case_id == "C036-cross-platform")
    result = compile_conformance_case(case)
    assert result.ir is not None
    catalog = result.ir.to_canonical_dict()["catalog"]
    assert catalog == sorted(catalog)


def test_qualified_apply_survives_unit_reorder() -> None:
    case = next(item for item in load_conformance_cases() if item.case_id == "C052-qualified-apply")
    forward = compile_program(root=case.root, units=case.units, extensions=())
    backward = compile_program(root=case.root, units=tuple(reversed(case.units)), extensions=())
    assert forward.digest == backward.digest
    assert forward.ir is not None
    targets = forward.ir.to_canonical_dict()["unit"]["targets"]
    assert targets[0]["fqid"] == "example.lib/target/primary"


def test_absolute_checkout_roots_do_not_enter_ir() -> None:
    lib = (Path("/tmp") / "mint-a" / "lib.mint").as_posix()
    main = (Path("/Users/ericskaggs") / "mint-b" / "main.mint").as_posix()
    case = next(item for item in load_conformance_cases() if item.case_id == "C026-imported-symbol")
    units = tuple(SourceUnit(item.unit_id, item.source) for item in case.units)
    result = compile_program(root=case.root, units=units)
    assert result.ok
    assert result.ir is not None
    text = result.ir.canonical_bytes().decode()
    assert lib not in text
    assert main not in text
    assert "/Users/" not in text
    assert "/tmp/" not in text
    assert result.ir.root_unit == "main.mint"
