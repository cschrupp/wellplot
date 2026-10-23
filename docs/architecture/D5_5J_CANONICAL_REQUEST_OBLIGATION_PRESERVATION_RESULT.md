# D5-5J Canonical Request-Obligation Preservation

## Status

This document records the provider-free implementation checkpoint for
`WELLPLOT-D5-5J-CANONICAL-REQUEST-OBLIGATION-PRESERVATION-IMPL-AUTH-001`.
It does not authorize provider, endpoint, or model execution.

The implementation remains on the existing path:

`authoritative request -> SemanticPlanner -> canonical workers -> lowering -> reconciliation -> execution`

No alternate planner, semantic engine, evaluator, provider adapter, or renderer
was added.

## Contract

`src/wellplot/agent/code_mode/obligations.py` defines a closed vocabulary for
explicit report, target, track, binding, and source facts. Each extracted fact
is tied to the exact UTF-8 request hash and a byte span/hash. The host, rather
than the provider, re-slices and verifies those spans. Unsupported language is
not silently promoted to executable JSON properties.

Planner coverage is checked independently of the provider's restatement.
Capability parents are closed before category validation. Report and section
workers validate requested values before lowering and retain the existing
bounded correction opportunity; no retry loop was introduced.

Target cardinality is checked before enrichment when one explicit request
target would otherwise authorize multiple section tasks. This is a safety
boundary, not a hard-coded section-name rule.

## Evidence

Prospective worker results expose a `SemanticStageEvidence` contract for the
provider wire, Python validation, planner, worker, lowering, reconciliation,
execution, post-lowering, preservation, persistence, reload, and render
boundaries. Existing historical D5-5I evidence is not rewritten.

Private governed evidence belongs under `.wellplot/governed-evidence/`; raw
content is ignored by Git. `scripts/archive_governed_run.py` creates a
deterministic inventory, archive digest, environment summary, and independent
restore verification. The legacy D5-5I migration source was unavailable in this
environment and was recorded as unavailable rather than reconstructed.

## Provider-free validation

The focused obligation tests cover exact request/span custody, tamper rejection,
repeated values on distinct owners, dropped explicit widths, wrong channels,
report field ownership, non-empty response schema, and the closed vocabulary.
Existing worker, planner, enrichment, workflow, and graph tests remain the
regression surface. No endpoint, provider, model, or live campaign calls were
made for D5-5J.

## Checkpoint lineage

The implementation was kept in four reviewable checkpoints:

1. durable evidence and prospective stage observability;
2. canonical obligation extraction, capability closure, worker checks, and
   pre-persistence candidate verification;
3. provider-free obligation qualification;
4. this result/provenance closeout.

The final commit must be inspected as a descendant of the authorized parent.
The local checkout used for this work contains no live campaign evidence and no
provider credentials.

The D5 single-engine production manifest was rebaselined after the canonical
source changes and passes `scripts/d5_single_engine_attestation.py --check`.

## Boundaries

This result does not claim that every natural-language request is extracted.
Only the bounded supported vocabulary is covered. Unknown, ambiguous, negated,
or conflicting semantics must remain unresolved or fail closed. The next
independent review must inspect the worker action shapes and post-lowering
verification coverage before any live qualification is considered.
