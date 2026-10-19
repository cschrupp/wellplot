# DECOMPOSER-PILOT-01 — Execution Authorization

```
AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-01-AUTH-001

SLICE:
DECOMPOSER-PILOT-01

STARTING TIP:
bad4ad33f1dd6f0c6976e8213012f66e16f19ea9

HUMAN AUTHORIZATION:
GRANTED

MODEL:
Qwen/Qwen3-1.7B
existing pinned local ModelScope snapshot only

CONSTRAINT:
WELL-EBNF-1 → XGrammar 0.2.8 native EBNF
→ pilot_xgrammar_transformers_hard_mask.v1

MODEL INFERENCE:
AUTHORIZED — EXACTLY SIX HIGH-LEVEL CALLS

PILOT-01:
AUTHORIZED
```

## Scientific question

Under the frozen zero-shot prompt, projected workspace, accepted hard constraint, and
no-repair policy, can the pinned Qwen3-1.7B decomposer produce semantically equivalent
`ScopeNormalizedProgram` outputs on the six frozen pilot cases?

This authority executes the already-accepted experiment. It does not reopen design.

## Frozen execution configuration

```
model                  Qwen/Qwen3-1.7B
variant                instruction / non-Base
snapshot               existing local ModelScope snapshot / master
adapters               NONE
autodownload           false
fallback               NONE

temperature            0
do_sample              false
thinking               disabled
max_new_tokens         1024
seed                    20261016
retries                 0
repair                  0
best_of_n               0

runtime                 CPU / float32
torch                   2.14.1+cpu
inference_config_sha    6daab17278547241563d1bc6bec92fcdd882ed48c8de3e18db81e737c732b54b
```

The runtime hash is part of the frozen experiment. If the execution environment does not
reproduce it exactly, **STOP before inference**. Do not silently switch to CUDA, another dtype,
or another torch/runtime configuration.

## Frozen order

Exactly one generation attempt per case:

```
1  D5GAP-0085
2  D5GAP-0089
3  D5GAP-0117
4  D5GAP-0096
5  D5GAP-0101
6  SEED-cm-9643c020e2e02463
```

Exactly six high-level decomposer calls are authorized. No retry is authorized.

## Pre-run barrier

Before model weights are loaded, mechanically reverify:

- model/config/tokenizer/weight hashes
- accepted WELL-EBNF-1 hash
- accepted XGrammar-native grammar hash
- XGrammar version 0.2.8
- frozen prompt/template hashes
- frozen serializer hash
- frozen inference-config hash
- six pre-inference case hashes and order
- no-network/local-only posture
- model-input contamination boundary

Any mismatch is a pre-run STOP with **zero model inference calls**.

## Model loading

After all pre-run gates pass:

- load the pinned local Qwen3-1.7B weights once
- no network
- no substitution
- no adapter
- evaluation/inference mode only

Internal forward passes performed by `generate()` are ordinary implementation details of the
six authorized calls. They do not create additional decomposer attempts.

## Per-case protocol

For each case:

1. Recompute and match the frozen input hashes.
2. Build model input from **utterance + ProjectedWorkspace only**.
3. Instantiate a fresh accepted XGrammar HF `LogitsProcessor`.
4. Invoke greedy generation exactly once.
5. Persist input provenance, generated token IDs, termination/completion metadata and latency.
6. Remove only a trailing authorized framework/XGrammar stop token from the payload token stream.
   Do not trim, repair, normalize or rewrite generated content.
7. Decode the payload deterministically and persist the exact UTF-8 bytes + SHA-256.
8. Freeze the candidate **before any oracle access**.
9. Only after freeze, evaluate through the accepted NL-PROGRAM-EVAL-HARNESS-01R2.
10. Persist the complete machine evaluation result.

If a case-local generation attempt fails, it consumes that case's one authorized call and is
recorded as `DECOMPOSITION_DECODE_FAILURE`. Do not retry.

If shared infrastructure becomes invalid or the same loaded model/runtime cannot safely continue,
STOP and preserve partial evidence as an incomplete run. Do not reload or substitute.

## Mechanical decision

No manual scoring.

```
Layer 0 != 6/6 frozen
    → INCONCLUSIVE

Layer 0 = 6/6 and EQUIVALENT = 6/6
    → STRONG PASS

Layer 0 = 6/6 and EQUIVALENT >= 5/6
    → CONTINUE FAMILY
      unless frozen Layer-2 critical-mechanism veto fires

Layer 0 = 6/6 and EQUIVALENT <= 4/6
    → STOP / REDESIGN

>=5/6 plus critical-mechanism veto
    → STOP / REDESIGN
```

## Explicitly forbidden

- any seventh decomposer call
- retrying any case
- model/tokenizer download
- model substitution
- adapters/fine-tuning
- prompt/schema/grammar/backend changes
- case-specific prompt or grammar
- repair/post-processing
- oracle/gold/expected-result material before freeze
- manual override of evaluator results
- broader heldout evaluation
- production integration

## Completion handoff

Publish:

- candidate / tip / remote head
- exact changed paths
- run manifest
- six per-case records in frozen order
- exact model-call count
- raw constrained outputs and hashes
- freeze/evaluation results
- Layer 0/1/2 summary
- mechanical decision
- material execution diagnostics

Then **STOP for independent scientific review**.

No additional authorization is needed between implementation and execution inside this authority.
