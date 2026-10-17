# DECOMPOSER-PILOT-PREFLIGHT-01R — STOP handoff

```
SLICE:
DECOMPOSER-PILOT-PREFLIGHT-01R

AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-PREFLIGHT-01-REWORK-AUTH-001

PARENT DESIGN:
decomposer_pilot_design_01 @ d180050eddee5bb8e4f1a9a370fe1a8c83ddd7bc

PRIOR PREFLIGHT-01 CANDIDATE:
4d140dc1c0805ee77dbb906ea3f2866cf15f1152
RESULT: REVISE

STARTING TIP:
1d84071576704909c9dce7e24011eb813009201c

CANDIDATE SHA:
f5a9f1d947212cd0b2ea0fe588dc1409df126e7f

TIP:
(pending SHA-record commit)

MODEL CALLS:
0

PILOT-01:
NOT_AUTHORIZED

RESULT:
FAIL
```

## Claim

PREFLIGHT-01R **FAIL** under the frozen fail-closed rules. The R1 pattern
`.*\S.*` is present in the persisted patched schema and is enforced by
jsonschema, but (1) Outlines language validation false-accepts `xor_both` and
tab-only strings, and (2) `outlines_core` Index construction against the pinned
Qwen tokenizer exceeds the DFA state limit. No backend swap, CFG workaround,
pattern weakening, or model load was performed.

This provides **zero** model-performance evidence and does **not** authorize
DECOMPOSER-PILOT-01.

Rework corrections attempted: R1 non-whitespace XOR pattern; R2 outlines_core
token-guide construction (tokenizer-only); R3 serializer wording +
patch/canonicalization pins.

## Failures

- parity_failed:['xor_both', 'xor_text_whitespace_tab', 'xor_local_ref_whitespace_tab']
- token_level_constraint:Failed to build DFA number of DFA states exceeds limit of 2147483647

## Evidence artifacts

- `decomposer_pilot_preflight_01_run_manifest.json`
- `decomposer_pilot_preflight_01_parity.json`
- `decomposer_pilot_preflight_01_constraint.schema.json`
- `decomposer_pilot_preflight_01.md`

## Explicit non-authorization

```
DECOMPOSER-PILOT-01:     NOT AUTHORIZED
model.generate:          NOT AUTHORIZED
model download:          NOT AUTHORIZED
CFG fallback:            NOT AUTHORIZED
backend swap:            NOT AUTHORIZED
prompt sealed-six tune:  NOT AUTHORIZED
```

STATUS:
STOP FOR INDEPENDENT DECOMPOSER-PILOT-PREFLIGHT-01R REVIEW
