from __future__ import annotations

from pathlib import Path

from opsdevcode_specmint.pins import CUE_VERSION

_ROOT = Path(__file__).resolve().parents[1]


def test_cue_checksums_cover_linux_and_darwin() -> None:
    text = (_ROOT / "tools" / "cue.sha256").read_text(encoding="utf-8")
    required = (
        f"cue_v{CUE_VERSION}_darwin_amd64.tar.gz",
        f"cue_v{CUE_VERSION}_darwin_arm64.tar.gz",
        f"cue_v{CUE_VERSION}_linux_amd64.tar.gz",
        f"cue_v{CUE_VERSION}_linux_arm64.tar.gz",
    )
    for name in required:
        assert name in text, f"pin tools/cue.sha256 for {name}"


def test_install_script_selects_host_os() -> None:
    script = (_ROOT / "scripts" / "install-cue.sh").read_text(encoding="utf-8")
    assert 'CUE_ARCH="darwin_arm64"' in script
    assert 'CUE_ARCH="linux_amd64"' in script
    assert "uname -s" in script
