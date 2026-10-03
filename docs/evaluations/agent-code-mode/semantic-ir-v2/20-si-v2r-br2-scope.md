# SI-V2R-BR2 Pinned Converter Provenance and Compatibility Audit

## Authority

- Baseline: `d441b84068a06457ded8651cac67708ee17c2cd0`
- Branch: `research/semantic-v2r-br2-converter-audit`
- BR1 records `15` through `19`: frozen and unmodified
- Provider inference calls: `0`
- Worker/program calls: `0`
- Endpoint metadata calls: `2` read-only requests (`/props`, `/v1/models`)

## Questions

BR2 keeps two questions separate:

1. Can the exact converter used by the historical SI-V2R-LQ0 run be
   authenticated from retained evidence?
2. Can a future converter reference implementation be pinned and exercised
   provider-free against the canonical SI-V2 and SI-V2R schemas?

The current endpoint build label is not treated as historical converter
provenance. No model request, completion request, server restart, model reload,
adapter, schema projection, or production change is part of BR2.

## Evidence boundary

The retained historical endpoint identity authenticates a model catalog, not a
remote executable, binary digest, source checkout, or converter warning stream.
BR2 therefore preserves historical converter provenance as `UNRESOLVED`.

The provider-free reference audit uses the public llama.cpp source commit
`bed0a856606ee4a24a164066f73d2379447033f5` only as a future-source reference.
It does not claim that this source produced the historical LQ0 run or that it
is the binary currently serving the remote endpoint.

## Hard stop

BR2 does not implement an adapter and does not run another model qualification.
