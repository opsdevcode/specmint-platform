from __future__ import annotations

import subprocess
import sys
import tarfile
import venv
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_PIN = "build==1.2.2"


def _venv_python(root: Path) -> Path:
    created = root / "venv"
    venv.create(created, with_pip=True, symlinks=True)
    return created / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def _run(argv: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, cwd=cwd, capture_output=True, text=True)


def test_sdist_and_wheel_from_isolated_build_venv(tmp_path: Path) -> None:
    """Do not invoke `python -m build` from the checkout: a leftover ./build dir
    shadows PyPA build even when the extra is installed.
    """
    builder = _venv_python(tmp_path / "builder")
    install = _run(
        [str(builder), "-m", "pip", "install", "--disable-pip-version-check", BUILD_PIN],
        cwd=tmp_path,
    )
    assert install.returncode == 0, install.stderr
    outdir = tmp_path / "dist"
    outdir.mkdir()
    built = _run(
        [
            str(builder),
            "-m",
            "build",
            str(REPO_ROOT),
            "--sdist",
            "--wheel",
            "--outdir",
            str(outdir),
        ],
        cwd=tmp_path,
    )
    assert built.returncode == 0, built.stderr + built.stdout
    sdists = list(outdir.glob("*.tar.gz"))
    wheels = list(outdir.glob("*.whl"))
    assert len(sdists) == 1
    assert len(wheels) == 1
    with tarfile.open(sdists[0]) as archive:
        names = archive.getnames()
    assert any(name.endswith("cue/delivery/v1alpha1/spec.cue") for name in names)
    assert any(name.endswith("schemas/delivery-specification.v1alpha1.json") for name in names)
    assert any(name.endswith("schemas/specmint-ir.v1alpha1.json") for name in names)
    assert any(name.endswith("schemas/mint.repository-snapshot.v0.json") for name in names)
    assert any(name.endswith("specification/mint-language-v1.md") for name in names)
    assert any(name.endswith("specification/mint-language-v1.ebnf") for name in names)
    assert not any(Path(name).name == "cue" and "/tools/" in name for name in names)
    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_names = archive.namelist()
    assert any(name.endswith("opsdevcode_specmint/platform/service.py") for name in wheel_names)


def test_installed_sdist_cli_and_platform_import(tmp_path: Path) -> None:
    builder = _venv_python(tmp_path / "builder")
    install_build = _run(
        [str(builder), "-m", "pip", "install", "--disable-pip-version-check", BUILD_PIN],
        cwd=tmp_path,
    )
    assert install_build.returncode == 0, install_build.stderr
    outdir = tmp_path / "dist"
    outdir.mkdir()
    built = _run(
        [str(builder), "-m", "build", str(REPO_ROOT), "--sdist", "--outdir", str(outdir)],
        cwd=tmp_path,
    )
    assert built.returncode == 0, built.stderr
    sdist = next(outdir.glob("*.tar.gz"))
    runtime = _venv_python(tmp_path / "runtime")
    installed = _run(
        [str(runtime), "-m", "pip", "install", "--disable-pip-version-check", str(sdist)],
        cwd=tmp_path,
    )
    assert installed.returncode == 0, installed.stderr
    version = _run([str(runtime), "-m", "opsdevcode_specmint", "version"], cwd=tmp_path)
    assert version.returncode == 0, version.stderr
    assert "specmint" in version.stdout
    help_out = _run([str(runtime), "-m", "opsdevcode_specmint", "mint", "--help"], cwd=tmp_path)
    assert help_out.returncode == 0, help_out.stderr
    assert "apply" not in help_out.stdout
    imported = _run(
        [
            str(runtime),
            "-c",
            "from opsdevcode_specmint.platform.service import PlatformService; "
            "from opsdevcode_specmint.main import app; "
            "PlatformService.in_memory(); print(app.title)",
        ],
        cwd=tmp_path,
    )
    assert imported.returncode == 0, imported.stderr
    assert "SpecMint" in imported.stdout
