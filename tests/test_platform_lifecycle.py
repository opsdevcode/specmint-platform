from __future__ import annotations

import pytest

from opsdevcode_specmint.platform.errors import PlatformProblem
from opsdevcode_specmint.platform.lifecycle import (
    STATUS_PLANNED,
    STATUS_VERIFIED,
    ensure_transition,
)


def test_invalid_lifecycle_transition() -> None:
    with pytest.raises(PlatformProblem) as exc:
        ensure_transition(STATUS_PLANNED, STATUS_VERIFIED)
    assert exc.value.code == "PLATFORM_LIFECYCLE"
