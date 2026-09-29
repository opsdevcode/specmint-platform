from __future__ import annotations

from typing import Any


def valid_spec(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "apiVersion": "specs.opsdevcode.io/v1alpha1",
        "kind": "DeliverySpecification",
        "metadata": {"id": "ds-repo-observe-1"},
        "spec": {
            "owner": "platform@opsdevcode.com",
            "intent": "Keep repo on recorded governed path",
            "target": {"repository": "https://github.com/opsdevcode/example"},
            "required_capabilities": ["repository.observe"],
            "constraints": {"recorded_baseline_approved": True},
            "status": "draft",
        },
    }
    document.update(overrides)
    return document


def valid_spec_yaml() -> str:
    return """apiVersion: specs.opsdevcode.io/v1alpha1
kind: DeliverySpecification
metadata:
  id: ds-repo-observe-1
spec:
  owner: platform@opsdevcode.com
  intent: Keep repo on recorded governed path
  target:
    repository: https://github.com/opsdevcode/example
  required_capabilities:
    - repository.observe
  constraints:
    recorded_baseline_approved: true
  status: draft
"""


def valid_automation_spec(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "apiVersion": "automations.opsdevcode.io/v1alpha1",
        "kind": "AutomationSpecification",
        "metadata": {"id": "as-local-marker-1"},
        "spec": {
            "owner": "platform@opsdevcode.com",
            "intent": "Ensure a sandbox marker exists after an authorized plan",
            "automation": {"type": "local.sandbox.ensure_marker", "version": "v1alpha1"},
            "placement": {"sandbox": "fixture-alpha"},
            "required_evidence": ["marker.present"],
            "constraints": {
                "require_authorization": True,
                "allow_platform_mutation": False,
            },
            "status": "draft",
        },
    }
    document.update(overrides)
    return document


def valid_automation_yaml() -> str:
    return """apiVersion: automations.opsdevcode.io/v1alpha1
kind: AutomationSpecification
metadata:
  id: as-local-marker-1
spec:
  owner: platform@opsdevcode.com
  intent: Ensure a sandbox marker exists after an authorized plan
  automation:
    type: local.sandbox.ensure_marker
    version: v1alpha1
  placement:
    sandbox: fixture-alpha
  required_evidence:
    - marker.present
  constraints:
    require_authorization: true
    allow_platform_mutation: false
  status: draft
"""


def valid_automation_markdown() -> str:
    return """---
apiVersion: automations.opsdevcode.io/v1alpha1
kind: AutomationSpecification
metadata:
  id: as-local-marker-1
---

# Local sandbox marker

Prose is documentation only.

```specmint
owner: platform@opsdevcode.com
intent: Ensure a sandbox marker exists after an authorized plan
automation:
  type: local.sandbox.ensure_marker
  version: v1alpha1
placement:
  sandbox: fixture-alpha
required_evidence:
  - marker.present
constraints:
  require_authorization: true
  allow_platform_mutation: false
status: draft
```
"""


def valid_mint_source() -> str:
    return """// Local sandbox marker — fixture for Mint Language v1alpha1
mint v1alpha1

automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent "Ensure a sandbox marker exists after an authorized plan"
  use local.sandbox.ensure_marker v1alpha1
  sandbox fixture-alpha
  evidence marker.present
  require authorization
  forbid mutation
  status draft
}
"""


def valid_automation_mint_markdown() -> str:
    return """---
apiVersion: automations.opsdevcode.io/v1alpha1
kind: AutomationSpecification
metadata:
  id: as-local-marker-1
---

# Local sandbox marker

Prose is documentation only.

```mint
mint v1alpha1

automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent "Ensure a sandbox marker exists after an authorized plan"
  use local.sandbox.ensure_marker v1alpha1
  sandbox fixture-alpha
  evidence marker.present
  require authorization
  forbid mutation
  status draft
}
```
"""


def valid_spec_markdown() -> str:
    return """---
apiVersion: specs.opsdevcode.io/v1alpha1
kind: DeliverySpecification
metadata:
  id: ds-repo-observe-1
---

# Repository observe

Human-readable explanation that is preserved as documentation but is
not interpreted as executable policy.

```specmint
owner: platform@opsdevcode.com
intent: Keep repo on recorded governed path
target:
  repository: https://github.com/opsdevcode/example
required_capabilities:
  - repository.observe
constraints:
  recorded_baseline_approved: true
status: draft
```
"""
