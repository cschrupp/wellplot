# DECOMPOSER-PILOT-CONSTRAINT-REDESIGN-01R — Stage A rework (paper/docs)

```
SLICE:
DECOMPOSER-PILOT-CONSTRAINT-REDESIGN-01R

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-CONSTRAINT-REDESIGN-01-REWORK-AUTH-001

STAGE:
A — PAPER/DOCS COMPATIBILITY (REWORK)

PRIOR STAGE-A CANDIDATE:
bce546960284be712e0d3b8f4d80d1eaec14e60f
RESULT: REVISE

STARTING TIP:
c6aba48be4c2f8b7e7cf0954f812b2838883ab12

CANDIDATE SHA:
b249b810908cbc0283e62f18e8780a4a4f7144d3

TIP:
(pending SHA-record commit)

PARENT:
DECOMPOSER-PILOT-PREFLIGHT-01R
ACCEPTED / CLOSED — RESULT: FAIL
CANDIDATE: f5a9f1d947212cd0b2ea0fe588dc1409df126e7f

PRIMARY BACKEND FAMILY:
XGrammar (JSON-Schema route)

XGRAMMAR_STAGE_A:
REJECT_BACKEND

MODEL CALLS:
0

INSTALL:
NOT AUTHORIZED

CODE:
NOT AUTHORIZED

STAGE B:
NOT AUTHORIZED

CFG/EBNF REDESIGN:
NOT PART OF THIS REWORK

PILOT-01:
NOT AUTHORIZED
```

## Rework (R1–R4)

| id | Correction |
|----|------------|
| R1 | XGrammar 0.2.8 / PR #672: non-provably-disjoint `oneOf` **warns** and falls back to **`anyOf`** (`ParseAnyOf`), not fail-closed |
| R2 | Frozen text-vs-`local_ref` XOR object arms are **outside** v0.2.8 published disjointness proofs |
| R3 | **G9** = `UNSUPPORTED`; **G2a** qualifies native fail-closed `oneOf` unavailable for this shape |
| R4 | `XGRAMMAR_STAGE_A` = `REJECT_BACKEND` |

## Problem (frozen)

Hard-enforce the already-frozen patched `ClosedNormalizedProgram` structural
language at token level with the pinned Qwen3-1.7B tokenizer, without changing
decomposer semantics, evaluator, or the six-case pilot.

## Stage A decision rule (unchanged)

Proceed only if no required feature is documented `UNSUPPORTED`, no evidence of
necessary schema weakening, and residual uncertainty is empirical. **Any required
`UNSUPPORTED` gate → reject backend.**

## XOR shape vs XGrammar 0.2.8 disjointness prover (R2)

Frozen branches:

```
branch A: required [kind, text];     kind = shared enum; text = pattern .*\\S.*;     additionalProperties: false
branch B: required [kind, local_ref]; kind = same enum;  local_ref = pattern .*\\S.*; additionalProperties: false
```

Published prover covers (approx.): common required discriminator with **finite
disjoint const/enum** per branch, or simple type/finite-value arms. Here `kind`
is the only finite common required key and its enum **overlaps completely**;
`text` / `local_ref` are not common finite discriminators. Therefore the prover
**cannot** establish pairwise disjointness → documented path:

```
oneOf unsupported for this shape
  → WARNING
  → ParseAnyOf(...)   # anyOf semantics
```

([PR #672](https://github.com/mlc-ai/xgrammar/pull/672),
[json_schema_converter.cc](https://github.com/mlc-ai/xgrammar/blob/main/cpp/json_schema_converter.cc)).

Nuance: if `additionalProperties: false` is faithful under the resulting union,
acceptance language **may** still match intended `oneOf` (including `xor_both`
REJECT). That possible equivalence **does not** satisfy G9.

## Nine-gate matrix (+ JSON Schema sub-capabilities)

| ID | Gate | Classification |
|----|------|----------------|
| G1 | Hard token-level enforcement | SUPPORTED |
| G2 | Frozen ClosedNormalizedProgram fidelity | UNCLEAR_REQUIRES_CONSTRUCTION_PROBE |
| G2a | `oneOf` | UNCLEAR_REQUIRES_CONSTRUCTION_PROBE (native fail-closed unavailable for this shape) |
| G2b | `pattern` / non-whitespace | UNCLEAR_REQUIRES_CONSTRUCTION_PROBE |
| G2c | `additionalProperties: false` | SUPPORTED |
| G2d | `$defs` / `$ref` | SUPPORTED |
| G3 | Correct XOR semantics | UNCLEAR_REQUIRES_CONSTRUCTION_PROBE |
| G4 | Correct non-empty / non-whitespace | UNCLEAR_REQUIRES_CONSTRUCTION_PROBE |
| G5 | Pinned Qwen tokenizer compatibility | UNCLEAR_REQUIRES_CONSTRUCTION_PROBE |
| G6 | Constructible without pathological explosion | UNCLEAR_REQUIRES_CONSTRUCTION_PROBE |
| G7 | No semantic repair layer | SUPPORTED |
| G8 | Deterministic / versioned provenance | SUPPORTED |
| G9 | Fail-closed behavior | **UNSUPPORTED** |

Machine-readable detail: `decomposer_pilot_constraint_redesign_01.json`.

### Concise rationale (reworked)

**G1 / G2c / G2d / G7 / G8 SUPPORTED.** Unchanged: hard token masking, closed
objects, `$defs`/`$ref`, no post-decode repair API, pinnable releases.

**G2a UNCLEAR (qualified).** Native fail-closed `oneOf` is **unavailable** for
this XOR shape under v0.2.8 (warn → `anyOf`). Qualification:
`NATIVE_ONEOF_UNSUPPORTED_FOR_THIS_SHAPE`. Resulting-language equivalence to
exact `oneOf` remains empirically testable and is **not** used to proceed.

**G3 UNCLEAR.** Acceptance parity under `anyOf` fallback is unproven; not claimed
false-accept of `xor_both` on paper.

**G2b / G4 / G5 / G6 UNCLEAR.** Pattern/Qwen/compile risks remain paper-open but
**moot** for JSON-Schema Stage B after reject.

**G9 UNSUPPORTED (R3).** Frozen requirement: unsupported/unsound constructs must
**fail closed**, never silently weaken/fallback. XGrammar 0.2.8 does the opposite
for this non-provably-disjoint `oneOf` (warn → `anyOf`). That is documented
behavior, not `UNCLEAR`.

## Stage A disposition

```
XGRAMMAR_STAGE_A:
  REJECT_BACKEND

unsupported_required_features:
  - G9_fail_closed_behavior

json_schema_route_status:
  REJECTED_ON_PAPER
```

**Meaning:** The XGrammar **JSON-Schema** route fails Stage A because required
G9 is `UNSUPPORTED`. This closes Stage B eligibility for that route.

```
REJECT_BACKEND
  ≠ evaluation of CFG/EBNF representation
  ≠ ban on considering XGrammar later as a grammar engine under new AUTH
  ≠ PILOT-01 authorization
```

This rework does **not** authorize or select a next CFG/EBNF candidate.

## Explicit non-authorizations

```
XGrammar install:                    NOT AUTHORIZED
dependency changes:                  NOT AUTHORIZED
implementation code:                 NOT AUTHORIZED
construction probe / Stage B:        NOT AUTHORIZED
schema mutation:                     NOT AUTHORIZED
CFG/EBNF redesign:                   NOT PART OF THIS REWORK
model.generate / forward:            NOT AUTHORIZED
PILOT-01:                            NOT AUTHORIZED
```

STATUS:
STOP FOR INDEPENDENT CONSTRAINT-REDESIGN-01R REVIEW
