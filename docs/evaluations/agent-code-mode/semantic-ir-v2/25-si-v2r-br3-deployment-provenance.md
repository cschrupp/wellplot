# SI-V2R-BR3 Deployment Provenance

The current read-only endpoint observation reports model alias
`qwen3.6-35b-a3b` and build label `b11160-a3c12db9d`. It does not expose an
authenticated server executable digest, immutable image digest, source commit,
build definition, structured-output backend identity, converter identity, or
grammar-validator identity. The observation is therefore `CURRENT_ONLY`.

The provider-free reference tools use llama.cpp source commit
`bed0a856606ee4a24a164066f73d2379447033f5` and source archive SHA-256
`0984123c33b7e959f8003f9169e9109897112d9448b681737813911083eca4cc`. These
values identify the reference source used for the local audit. They do not
authenticate the historical LQ0 server or the current endpoint.

The machine-readable artifacts retain hashes and bounded classifications only.
They do not retain model paths, authorization headers, credentials, environment
dumps, binaries, images, or generated grammar bodies.
