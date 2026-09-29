# Contract ownership matrix (private preview)

Prefer existing contracts. New envelopes are adapters, not a shared library.

capability-descriptor:
    owner specmint
    version opsdevcode.capability-descriptor/v0
    consumers specmint, repave, overpass, toll, dispatch
    disposition new prototype; does not replace opsdevcode_capabilities

product-registration:
    owner specmint
    version opsdevcode.product-registration/v0
    consumers platform registry
    disposition new

intent-submission / MintIR:
    owner specmint
    version mint.opsdevcode.io/v0 MintIR
    consumers specmint HTTP, repave client
    disposition reuse compiler output

observation-snapshot:
    owner specmint schema, repave producer
    version mint.repository-snapshot/v0
    schemaDigest:
        sha256:5bbc939fd007142ecbe0de043384c54c1101545a3ca43b0b26ec89ca73db58e4
        SHA-256 of committed schemas/mint.repository-snapshot.v0.json bytes
    snapshotDigest:
        SHA-256 of canonical snapshot JSON (sorted keys, trailing newline),
        excluding provenance timestamps; not the schema file digest
    consumers specmint planner, repave translator
    disposition reuse; Repave maps overlay + observe

deterministic-plan:
    owner specmint
    version mint.plan-result/v0
    consumers repave read-only workflow
    disposition reuse

approval-requirement / approval-record:
    owner specmint
    version opsdevcode.approval-*/v0
    consumers specmint run
    disposition new adapter over plan digest

execution-request / execution-result:
    owner specmint contract, repave repository executor later
    version opsdevcode.execution-*/v0
    consumers fake GitHub provider
    disposition new; live GitHub deferred

verification-result / evidence-envelope:
    owner specmint
    version opsdevcode.verification-result/v0, opsdevcode.evidence-envelope/v0
    consumers private preview fixtures
    disposition new

notification-request:
    owner dispatch
    version opsdevcode.notification-request/v0
    consumers sandbox composition
    disposition new stub; Relay remains transport

budget-decision:
    owner toll
    version opsdevcode.budget-decision/v0
    consumers sandbox composition
    disposition new stub; spend.attribute stays in Repave today

environment-lifecycle:
    owner overpass
    version opsdevcode.environment-lifecycle/v0
    consumers sandbox composition
    disposition new stub; inventory/relate/drift/commit unchanged

opsdevcode_capabilities:
    owner repave
    version in-tree package
    consumers repave catalogs; overpass has a copy
    disposition keep; do not rewrite
