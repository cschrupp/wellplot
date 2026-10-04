# SR7-P0 Evidence Contract

The future evidence population contains exactly one bounded row for each of
the 96 scheduled logical attempts. Each row binds the configuration fingerprint,
case/request, prompts, schema, gold, mask, comparison contract, semantic
dimension contract, semantic grader source identity, and runtime material
attestation. It preserves initial and retry statuses, usage/latency,
canonical V2R semantics, dimension results, compiler outcome, safety actions,
and separate system results.

Canonical generated V2R objects may be retained as grading evidence. Provider
reasoning text, credentials, authorization headers, environment dumps, and
hidden reasoning content are never required or retained. Provider metadata is
limited to bounded model, finish reason, usage, latency, reasoning-token count,
and HTTP category fields.

Duplicate logical attempts, missing schedule rows, hash drift, unknown cases or
configurations, and retry-limit violations invalidate the population. The
pre-live evidence schema and its SHA-256 are frozen before inference.
