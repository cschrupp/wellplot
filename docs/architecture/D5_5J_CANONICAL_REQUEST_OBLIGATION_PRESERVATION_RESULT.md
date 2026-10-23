# D5-5J Canonical Request-Obligation Preservation

## Status

This document records the provider-free implementation checkpoint for
`WELLPLOT-D5-5J-CANONICAL-REQUEST-OBLIGATION-PRESERVATION-IMPL-REWORK2-AUTH-001`.
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

Targeted channel obligations remain task-local; only genuinely request-wide
facts are global. Every supported lexical anchor is independently checked for
conversion into an exact-span obligation before planner validation.

The direct-notebook host transaction now verifies the baseline-to-candidate
document diff against the canonical reconciliation operation set before
persistence. Unrelated mutations are rejected even when the requested fact is
present. Host-owned reconciliation, private execution, canonical validation,
post-lowering obligation, preservation, persistence, reload, and render stages
are emitted separately in the result evidence.

## Evidence

Prospective worker results expose a `SemanticStageEvidence` contract for the
provider wire, Python validation, planner, worker, lowering, reconciliation,
execution, post-lowering, preservation, persistence, reload, and render
boundaries. Existing historical D5-5I evidence is not rewritten.

Private governed evidence is staged under `.wellplot/governed-evidence/`, but
the closeout archive is copied and digest-verified under the persistent project
storage path `/home/user/projects/well_log_os/.wellplot/governed-evidence/`.
`scripts/archive_governed_run.py` now requires that separate durable
destination and independently restore-checks the published archive.
Credential-like files are refused case-insensitively. The resulting archive
digest and source inventory are recorded in
`docs/evidence/manifests/d5-5j-provider-free-closeout.json`.

## Provider-free validation

The focused obligation/archive tests cover exact request/span custody,
UTF-8 byte offsets, tamper rejection, paraphrased add-track extraction,
negation/conflict states, one-to-one and targeted multi-section partitioning,
independent anchor coverage, final preservation containment, correction-scope
containment, deterministic archive bytes, durable-copy verification, and
secret-name rejection. The focused obligation/archive/session suite passes 37
tests. The canonical
Code Mode/planner/enrichment/workflow/graph and provider-free lane regression
surface passes 275 tests. No endpoint, provider, model, or live campaign calls
were made for D5-5J.

## Checkpoint lineage

The implementation was kept in reviewable implementation checkpoints,
followed by this bounded corrective rework and attestation closeout:

1. durable evidence and prospective stage observability;
2. canonical obligation extraction, capability closure, worker checks, and
   pre-persistence candidate verification;
3. provider-free obligation qualification;
4. result/provenance closeout;
5. request-obligation rework and evidence hardening;
6. production-manifest rebaseline and attestation verification;
7. bounded rework for task ownership, final preservation, host-stage evidence,
   and durable archive publication.

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
