# SI-V2R-BR2 Provenance

## Historical LQ0

Historical converter provenance is `UNRESOLVED`. The retained evidence records
the reported llama.cpp label `b11160-a3c12db9d`, the frozen LQ0 evidence hash,
and the normalized endpoint identity. It does not retain an authenticated
llama-server binary hash, process identity, converter source tree, or warning
stream. The reported suffix does not resolve to an authenticated public
upstream commit.

The current read-only endpoint observations are classified as `CURRENT_ONLY`:
they report the same model alias and build label, but current endpoint state
does not establish historical continuity.

## Future reference source

The provider-free reference converter source is pinned to:

```text
llama.cpp source commit: bed0a856606ee4a24a164066f73d2379447033f5
source archive SHA-256: 0984123c33b7e959f8003f9169e9109897112d9448b681737813911083eca4cc
```

This is source-level qualification evidence only. It is not an authenticated
identity for the remote serving binary. No adapter or production conclusion
follows from the source reference alone.
