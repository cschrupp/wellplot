# DECOMPOSER-PILOT-CONSTRAINT-XGRAMMAR-PREFLIGHT-01R — Closeout

```
SLICE:
DECOMPOSER-PILOT-CONSTRAINT-XGRAMMAR-PREFLIGHT-01R

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-CONSTRAINT-XGRAMMAR-PREFLIGHT-01-AUTH-001

MODE:
BOUNDED PREFLIGHT HARDENING

PRIOR CANDIDATE:
a445c451e356b713cd24fcfb532a404421bc269e
RESULT: REVISE (F001–F004)

STARTING TIP:
96d5a75a08a3a885cc10596092ad4d41409ef3e8

AUTHORITY REMOTE HEAD:
b6352a778f62982b4c42ff2ef773a622e351dcf7

CANDIDATE SHA:
b0641eef502530aa841b3c5c6fa6cc60ca089dfb

TIP:
(pending SHA-record commit)

RESULT:
PASS

MODEL CALLS:
0

MODEL WEIGHTS LOADED:
false

MODEL FORWARD CALLS:
0

MODEL GENERATE CALLS:
0

PILOT-01:
NOT AUTHORIZED
```

## Corrective scope (R1–R5)

| ID | Correction |
|----|------------|
| R1 | P2 field-level Q6 MODEL completeness from full provenance |
| R2 | P7 adversarial fail-closed suite (evidence-derived) |
| R3 | P8 forward + autodownload guards with negative tests |
| R4 | P5 HF LogitsProcessor progressive synthetic replay |
| R5 | Regenerated evidence / P1–P9 |

## Gates

| Gate | Result | Summary |
|------|--------|---------|
| P1 | PASS | immutable identities/hashes |
| P2 | PASS | field-level Q6 run manifest completeness |
| P3 | PASS | frozen prompt/template smoke |
| P4 | PASS | XGrammar construction + parity |
| P5 | PASS | adapter + HF LogitsProcessor synthetic replay |
| P6 | PASS | six-case pre-inference hashes |
| P7 | PASS | adversarial fail-closed suite (evidence-derived) |
| P8 | PASS | zero model + load/forward/generate/download guards |
| P9 | PASS | resource/setup evidence |

## Selected path

```
WELL-EBNF-1 f8cfd0c2b8a2cb2c708e464147080ebd7400e40e8060fa0426e423d70396d9d3
  → well_ebnf1_to_xgrammar_ebnf.v1
  → XGrammar EBNF 506ccd08aceb6428e9ba7508afddc143a65adf2e7f959bd4419021c178f24c89
  → XGrammar 0.2.8
  → pinned Qwen3-1.7B tokenizer
  → PilotXGrammarHardMaskAdapter / xgr.contrib.hf.LogitsProcessor
```

## Evidence artifacts

- `decomposer_pilot_constraint_xgrammar_preflight_01_run_manifest.json`
- `decomposer_pilot_constraint_xgrammar_preflight_01_parity.json`
- `decomposer_pilot_constraint_xgrammar_preflight_01_adapter.json`
- `decomposer_pilot_constraint_xgrammar_preflight_01_case_hashes.json`
- `decomposer_pilot_constraint_xgrammar_preflight_01_fail_closed.json`
- `decomposer_pilot_constraint_xgrammar_preflight_01.json`
- `decomposer_pilot_constraint_xgrammar_preflight_01.md`

## Explicit non-authorizations

```
AutoModel / model weight load: NOT AUTHORIZED
model.forward:                 NOT AUTHORIZED
model.generate:                NOT AUTHORIZED
real model logits:             NOT AUTHORIZED
autodownload:                  NOT AUTHORIZED
PILOT-01:                      NOT AUTHORIZED
```

## Terminal state

```
IMPLEMENTATION_COMPLETE_AWAITING_INDEPENDENT_REVIEW
```

STATUS:
STOP FOR INDEPENDENT DECOMPOSER-PILOT-CONSTRAINT-XGRAMMAR-PREFLIGHT-01R REVIEW
