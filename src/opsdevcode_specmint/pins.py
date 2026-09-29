"""Pinned toolchain versions. Image and CI must match these literals."""

from __future__ import annotations

import os
from typing import Final

PYTHON_VERSION: Final = "3.12"
CUE_VERSION: Final = "0.17.1"
CUE_RELEASE_TAG: Final = f"v{CUE_VERSION}"
SERVICE_NAME: Final = "specmint"
SPEC_API_VERSION: Final = "specs.opsdevcode.io/v1alpha1"
SPEC_KIND: Final = "DeliverySpecification"
COMPILED_INTENT_API_VERSION: Final = "intents.opsdevcode.io/v1alpha1"
COMPILED_INTENT_KIND: Final = "CompiledIntent"
IR_API_VERSION: Final = "ir.opsdevcode.io/v1alpha1"
IR_KIND: Final = "SpecMintIR"
IR_VERSION: Final = "v1alpha1"
NATIVE_TARGET_TYPE: Final = "opsdevcode.compiled-intent"
AUTOMATION_API_VERSION: Final = "automations.opsdevcode.io/v1alpha1"
AUTOMATION_SPEC_KIND: Final = "AutomationSpecification"
AUTOMATION_INTENT_KIND: Final = "AutomationIntent"
LOCAL_AUTOMATION_TYPE: Final = "local.sandbox.ensure_marker"
MINT_LANGUAGE_VERSION: Final = "v1alpha1"
API_VERSION: Final = SPEC_API_VERSION
KIND: Final = SPEC_KIND
MAX_DOCUMENT_BYTES: Final = 65_536
MAX_DOCUMENT_DEPTH: Final = 32
MAX_YAML_ALIASES: Final = 4
CUE_TIMEOUT_SECONDS: Final = 5.0
DEFAULT_BIND_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 8080


def env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes"}
