# Mint Language v1 (compatibility note)

Mint is a language. SpecMint is a product host.

Normative edition `v0` lives in [mint/v0/language.md](mint/v0/language.md).
`mint v1alpha1` remains a source-edition alias from PR 11. New programs
should start with `mint v0`.

The language artifact is `MintIR` `mint.opsdevcode.io/v0`. SpecMint may
project that IR to `AutomationSpecification` and then emit
`AutomationIntent`. That host path is not the language.

Historical frontend notes from PR 11 (media types, Markdown fence, closed
`local.sandbox.ensure_marker` verb) still apply to the SpecMint host.
They are not a second language definition.
