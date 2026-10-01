# Repository Rules

## Project Decision Protocol

All agents working in this repository must read and follow
`docs/project-decision-protocol.md` before making material architectural,
implementation, evaluation, or remediation decisions.

Operational requirements:

- perform scope and external-evidence checks at material decision points;
- prefer primary sources and mature comparable implementations;
- do not experimentally rediscover established behavior when
  documentation/source/research can answer it;
- classify consequential decisions as `ESTABLISHED`, `ADAPTED`,
  `EMPIRICALLY_SUPPORTED`, or `NOVEL`;
- experiments must be finite and pre-bounded;
- autonomous agents may not silently expand project scope;
- major architecture changes require an explicit decision record and
  independent review.

The complete policy is in `docs/project-decision-protocol.md`.

## MCP Stabilization

During MCP stabilization, no runtime workaround may be added merely because a
provider emitted an unexpected tool call. First inspect the advertised MCP
schema. If the call is permitted or ambiguous under that schema, fix the
schema. A new regex intent heuristic, argument normalizer, fallback executor,
stage controller, or provider-specific branch requires a committed failing
live evaluation and must replace or delete equivalent complexity elsewhere.
