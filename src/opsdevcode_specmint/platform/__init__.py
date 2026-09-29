"""Private SpecMint platform host. Not language-core; not production-ready."""

from opsdevcode_specmint.platform.errors import PlatformProblem
from opsdevcode_specmint.platform.service import PlatformService

__all__ = ["PlatformProblem", "PlatformService"]
