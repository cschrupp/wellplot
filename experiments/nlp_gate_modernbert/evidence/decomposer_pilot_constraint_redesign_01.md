# DECOMPOSER-PILOT-CONSTRAINT-REDESIGN-01 — Stage A (paper/docs)

```
SLICE:
DECOMPOSER-PILOT-CONSTRAINT-REDESIGN-01

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-CONSTRAINT-REDESIGN-01-AUTH-001

STAGE:
A — PAPER/DOCS COMPATIBILITY

PARENT:
DECOMPOSER-PILOT-PREFLIGHT-01R
ACCEPTED / CLOSED — RESULT: FAIL
CANDIDATE: f5a9f1d947212cd0b2ea0fe588dc1409df126e7f

STARTING TIP:
b16b338bcdd1605f96cf026ecafde80907e57aa5

CANDIDATE SHA:
bce546960284be712e0d3b8f4d80d1eaec14e60f

TIP:
(pending SHA-record commit)

PRIMARY BACKEND FAMILY:
XGrammar

XGRAMMAR_STAGE_A:
PROCEED_TO_STAGE_B_ELIGIBLE

MODEL CALLS:
0

INSTALL:
NOT AUTHORIZED

CODE:
NOT AUTHORIZED

STAGE B:
NOT AUTHORIZED

PILOT-01:
NOT AUTHORIZED
```

## Problem (frozen)

Hard-enforce the already-frozen patched `ClosedNormalizedProgram` structural
language at token level with the pinned Qwen3-1.7B tokenizer, without changing
decomposer semantics, evaluator, or the six-case pilot.

## Stage A scope

Public documentation and published converter/source evidence only. No install,
no code, no model load. Classification vocabulary:

- `SUPPORTED`
- `UNSUPPORTED`
- `UNCLEAR_REQUIRES_CONSTRUCTION_PROBE`

Proceed to Stage B eligibility only if: no required feature is documented
unsupported; no evidence of necessary schema weakening; residual uncertainty is
empirical/constructibility.

## Nine-gate matrix (+ JSON Schema sub-capabilities)

| ID | Gate | Classification |
|----|------|----------------|
| G1 | Hard token-level enforcement | SUPPORTED |
| G2 | Frozen ClosedNormalizedProgram fidelity | UNCLEAR_REQUIRES_CONSTRUCTION_PROBE |
| G2a | `oneOf` | UNCLEAR_REQUIRES_CONSTRUCTION_PROBE |
| G2b | `pattern` / non-whitespace | UNCLEAR_REQUIRES_CONSTRUCTION_PROBE |
| G2c | `additionalProperties: false` | SUPPORTED |
| G2d | `$defs` / `$ref` | SUPPORTED |
| G3 | Correct XOR semantics | UNCLEAR_REQUIRES_CONSTRUCTION_PROBE |
| G4 | Correct non-empty / non-whitespace | UNCLEAR_REQUIRES_CONSTRUCTION_PROBE |
| G5 | Pinned Qwen tokenizer compatibility | UNCLEAR_REQUIRES_CONSTRUCTION_PROBE |
| G6 | Constructible without pathological explosion | UNCLEAR_REQUIRES_CONSTRUCTION_PROBE |
| G7 | No semantic repair layer | SUPPORTED |
| G8 | Deterministic / versioned provenance | SUPPORTED |
| G9 | Fail-closed behavior | UNCLEAR_REQUIRES_CONSTRUCTION_PROBE |

Machine-readable detail (same classifications/citations):  
`decomposer_pilot_constraint_redesign_01.json`.

### Concise rationale

**G1 SUPPORTED.** Docs describe per-step token bitmasks applied to logits;
HF `xgr.contrib.hf.LogitsProcessor(compiled_grammar)` is the documented
Transformers integration
([constrained decoding](https://xgrammar.mlc.ai/docs/latest/start/constrained_decoding.md),
[quick start](https://xgrammar.mlc.ai/docs/latest/start/quick_start.html)).

**G2 UNCLEAR.** `compile_json_schema` accepts schema string/dict/Pydantic
([GrammarCompiler](https://xgrammar.mlc.ai/docs/latest/api/python/grammar_compiler.html));
exact fidelity to our persisted artifact is unproven.

**G2a UNCLEAR.** `oneOf` is recognized; DeepWiki notes fallback to `anyOf` when
branches are not provably disjoint; [PR #672](https://github.com/mlc-ai/xgrammar/pull/672)
documents historical exactly-one loss and proposes fail-closed. Our XOR branches
are exclusive object shapes (`required` + `additionalProperties: false`) and are
not a documented hard unsupported, but parity needs a probe.

**G2b UNCLEAR.** `pattern` is supported via ECMA-262-subset regex conversion
([feature matrix](https://deepwiki.com/mlc-ai/xgrammar/5.2-supported-json-schema-features);
[testing module](https://xgrammar.mlc.ai/docs/_modules/xgrammar/testing.html)).
`.*\S.*` avoids documented unsupported regex features, but tab/JSON-escape
fidelity (Outlines failure mode) is empirical.

**G2c SUPPORTED.** `additionalProperties` / `unevaluatedProperties` handled;
`strict_mode=True` by default
([GrammarCompiler](https://xgrammar.mlc.ai/docs/latest/api/python/grammar_compiler.html);
[PR #594](https://github.com/mlc-ai/xgrammar/pull/594)).

**G2d SUPPORTED.** Converter recognizes `$defs`/`definitions` and `$ref` JSON
Pointers with circular-ref handling
([feature matrix](https://deepwiki.com/mlc-ai/xgrammar/5.2-supported-json-schema-features);
[json_schema_converter.cc](https://github.com/mlc-ai/xgrammar/blob/main/cpp/json_schema_converter.cc)).

**G3 / G4 UNCLEAR.** Depend on G2a/G2b construction parity against the PREFLIGHT
probe suite.

**G5 UNCLEAR.** `TokenizerInfo.from_huggingface` documented; Qwen appears in
upstream matcher tests; must pass `config.vocab_size` when logits dim ≠ tokenizer
vocab
([workflow](https://xgrammar.mlc.ai/docs/latest/start/workflow_of_xgrammar.html)).

**G6 UNCLEAR.** Different engine than `outlines_core` Index (grammar compile +
adaptive mask cache). PREFLIGHT DFA failure does not transfer; full-schema
constructibility remains the central Stage B question.

**G7 SUPPORTED.** Documented path is generative masking only; no semantic
post-decode repair API described for JSON Schema guidance.

**G8 SUPPORTED.** Released versions are pinnable
([releases](https://github.com/mlc-ai/xgrammar/releases)); compile kwargs are
explicit. Stage B must record concrete version + artifact hashes.

**G9 UNCLEAR.** Some unsatisfiable schemas fail closed; `oneOf` anyOf-fallback
is a known non-fail-closed historical path for overlapping branches. Our
exclusive-property XOR is not proven fail-closed on paper.

## Residual risks

1. `oneOf` → `anyOf` fallback if branches are not “provably disjoint.”
2. `pattern: ".*\\S.*"` tab / JSON-escape fidelity.
3. Full patched schema may still fail to compile or explode at Stage B.
4. Qwen `config.vocab_size` vs tokenizer vocab must be pinned correctly.
5. `strict_mode` / separators / `any_order` must be frozen to match canonical
   schema serialization.

## Stage A disposition

```
XGRAMMAR_STAGE_A:
  PROCEED_TO_STAGE_B_ELIGIBLE

unsupported_required_features:
  (none)

known_necessary_schema_weakening:
  false
```

**Meaning:** No documented incompatibility blocks an empirical construction
probe.

```
PROCEED_TO_STAGE_B_ELIGIBLE
  ≠ XGrammar accepted as production constraint engine
  ≠ installation authorized
  ≠ construction probe authorized
  ≠ PILOT-01 authorized
```


Stage B, if authorized later, would be a separate AUTH such as
`DECOMPOSER-PILOT-CONSTRAINT-XGRAMMAR-PROBE-01` (install/pin, tokenizer-only,
exact persisted schema, compile, structural parity; `model_calls=0`).

## Explicit non-authorizations

```
XGrammar install:          NOT AUTHORIZED
implementation code:       NOT AUTHORIZED
Stage B construction:      NOT AUTHORIZED
model.generate / forward:  NOT AUTHORIZED
schema weakening:          NOT AUTHORIZED
PILOT-01:                  NOT AUTHORIZED
CFG auto-fallback:         NOT AUTHORIZED
```

STATUS:
STOP FOR INDEPENDENT CONSTRAINT-REDESIGN-01 STAGE-A REVIEW
