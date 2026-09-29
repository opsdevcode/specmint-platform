# local-marker

Single-unit `local.sandbox.ensure_marker` project used by the plan-only
adapter SDK.

```bash
mint plan --project examples/projects/local-marker --locked
mint adapters inspect local.sandbox.ensure_marker
```

`plan.json` is the expected `MintPlanResult`. Planning does not write a
sandbox marker on the target filesystem. `mint plan --artifacts DIR`
writes confined plan output only.

Offline local files only. Not a registry package.
