# SI-V2R-BR3 Deployment Toolchain Pinning

## Authority

- Baseline: `95033de99285db85d5c818e733805b102f08b328`
- Branch: `research/semantic-v2r-br3-deployment-toolchain`
- BR2 records `20` through `23`: frozen and unmodified
- Provider inference calls: `0`
- Worker/program calls: `0`
- Read-only endpoint metadata calls: `2`

## Decision

BR3 audits the deployment artifact, build provenance, structured-output
backend, JSON-Schema converter, grammar validator, and deterministic grammar
behavior in one bounded provider-free pass. A serving endpoint label is not
treated as an authenticated binary, source, build, or converter identity.

The accepted BR2 reference conversion is retained as reference evidence. BR3
does not describe it as complete V2R support because grammar acceptance was not
tested there.

## External evidence

The llama.cpp GBNF documentation describes JSON Schema support as a subset and
warns that unsupported features may be skipped. It recommends testing the
resulting grammar with a validator. SLSA separates artifact identity from
build provenance, and immutable deployment digests follow the same principle.
JSONSchemaBench and PICARD support measuring structural admissibility separately
from task quality.

## Hard stop

If the serving artifact and corresponding structured-output toolchain cannot be
authenticated in this pass, BR3 records
`SI_V2R_BR3_DEPLOYMENT_TOOLCHAIN_UNRESOLVED` and stops converter root-cause
research. No adapter, schema projection, prompt change, model inference, or
production integration is authorized by this slice.
