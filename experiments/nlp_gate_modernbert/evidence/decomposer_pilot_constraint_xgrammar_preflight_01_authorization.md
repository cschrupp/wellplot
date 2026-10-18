# DECOMPOSER-PILOT-CONSTRAINT-XGRAMMAR-PREFLIGHT-01 — Authorization

```
AUTHORITY:
WELLPLOT-NLP-RUNTIME-V2-DECOMPOSER-PILOT-CONSTRAINT-XGRAMMAR-PREFLIGHT-01-AUTH-001

SLICE:
DECOMPOSER-PILOT-CONSTRAINT-XGRAMMAR-PREFLIGHT-01

MODE:
SELECTED-BACKEND ZERO-MODEL PREFLIGHT

STARTING TIP:
e04cf55a5efdbcc242b92f592c8861f1730de348

SELECTED BACKEND:
XGrammar 0.2.8 / native EBNF

MODEL CALLS:
0

MODEL WEIGHTS LOADED:
false

PILOT-01:
NOT AUTHORIZED
```

## Purpose

Prove that the exact infrastructure intended for the frozen six-case
`DECOMPOSER-PILOT-01` can be constructed and frozen **without loading model
weights or running inference**.

This slice is the last infrastructure gate before a possible model pilot. It is
not itself a model-capability experiment.

## Frozen path

```
ClosedNormalizedProgram contract
        ↓
accepted WELL-EBNF-1
f8cfd0c2b8a2cb2c708e464147080ebd7400e40e8060fa0426e423d70396d9d3
        ↓
well_ebnf1_to_xgrammar_ebnf.v1
source SHA:
216976a6e7b8a6838862198fa4d37168666fab602ec643c7369ca100179d377e
        ↓
XGrammar-native EBNF
506ccd08aceb6428e9ba7508afddc143a65adf2e7f959bd4419021c178f24c89
        ↓
XGrammar 0.2.8
        ↓
pinned Qwen/Qwen3-1.7B tokenizer
        ↓
future pilot hard-mask adapter
```

No component in that chain may be changed in this preflight.

## Model snapshot boundary

The existing local Qwen3-1.7B snapshot may be inspected only for immutable
provenance.

Authorized:

- verify file existence
- verify byte size
- SHA-256 model/config/tokenizer files
- load tokenizer/config metadata locally

Forbidden:

- `AutoModel*.from_pretrained`
- deserializing safetensors into model tensors
- model forward
- model generation
- real model logits
- download/substitution/fallback

Expected weight manifest:

```
model-00001-of-00002.safetensors
  3441185608 bytes
  169ad53ec313c3a34b06c0809216e4fc072cce444a5d4ff2b59690d064130ed5

model-00002-of-00002.safetensors
  622329984 bytes
  912becff8d60672aa8628ef08c05898d9adf17c2ad4ae3caf99b065622fdeff9

aggregate manifest:
005d20550c04f4e246e5b434448786b44a0196b47d758d0acc77aba279e5bbc5
```

## Frozen prompt and serialization

Zero-shot only.

```
system_prompt_sha256:
e617d84e535f72423285f8824014d52c67f40533aaae660783a7dbcb5988b8f4

user_template_sha256:
5662a961cf892c5aafc9448f5daa18ac2f93bc24efda0c07d3da19b5fb9aaddb

chat_template_text_sha256:
e255510bc9a300c02dda23801a72e4c6a5736d5a995768cb44791f9651727b03

workspace serializer implementation:
95514c73fc1a25c5c52d784a3c2126543dfd8845f8f21aabafd103642a152740
```

Prompt/schema/serializer tuning is forbidden.

Frozen inference configuration for the future pilot manifest:

```
temperature       = 0
do_sample         = false
thinking          = disabled
max_new_tokens    = 1024
seed              = 20261016
adapters          = NONE
retries           = 0
repair            = 0
best_of_n         = 0
```

These are provenance/configuration values only. No inference occurs here.

## Preflight work authorized

### A. Immutable provenance

Verify the accepted grammar, XGrammar lowering, backend version, tokenizer
artifacts, model config and weight-file manifest from local files only.

Any mismatch fails closed.

### B. Exact pilot adapter

Implement/freeze the XGrammar hard-mask adapter intended for the later
Transformers pilot.

Test it using **synthetic logits only**.

The adapter must demonstrate:

- allowed tokens remain available
- disallowed tokens are made impossible
- matcher state advances only on accepted token IDs
- completion/stop handling is correct
- invalid transitions fail closed
- fresh/reset state is deterministic
- no JSON repair or semantic normalization occurs

Do not invoke `model.generate()`.

### C. Constraint replay

Re-run the accepted positive/negative text and token-mask parity checks using
the exact accepted grammar/tokenizer/backend.

This is regression protection, not a new engine bakeoff.

### D. Prompt/tokenizer smoke

Use a fixed **non-sealed dummy request** to verify the exact frozen system
prompt, user template, Qwen chat template, `enable_thinking=False`, and
tokenizer path.

Do not tune prompt text from the sealed six.

### E. Frozen six manifest preparation

Mechanically prepare the six future-pilot pre-inference hash records in this
exact order:

```
D5GAP-0085
D5GAP-0089
D5GAP-0117
D5GAP-0096
D5GAP-0101
SEED-cm-9643c020e2e02463
```

Only these may contribute to the model input:

```
utterance
ProjectedWorkspace
```

`case_id` is evaluator-side provenance only.

Forbidden from the model-input path:

- case/fixture IDs
- oracle witnesses/programs
- accepted candidate fixtures
- coverage atoms/checkers
- expected outcomes
- runtime traces
- prior evaluation results
- gold operations
- representability annotations
- failure taxonomy

Persist hashes/provenance, not fresh copies of sealed raw content.

## Mandatory gates

| Gate | Requirement |
|---|---|
| P1 | all frozen artifact/model/tokenizer identities match |
| P2 | complete Q6 run manifest exists before any future inference |
| P3 | frozen prompt/template/tokenization smoke passes; thinking disabled |
| P4 | XGrammar 0.2.8 exact grammar construction + accepted parity remain PASS |
| P5 | exact future pilot adapter passes synthetic-logits hard-mask/completion/reset tests |
| P6 | six pre-inference hash records exist in frozen order; same prompt/constraint/serializer/config; no contamination |
| P7 | all mismatch/backend/adapter/contamination failures fail closed with zero model calls |
| P8 | model calls/forward/generate = 0; model weights loaded = false; no download |
| P9 | bounded setup/compile/synthetic-mask resource evidence recorded |

All P1–P9 are mandatory.

## Explicitly unauthorized

```
AutoModel/model weight load:              NOT AUTHORIZED
safetensor deserialization as model:      NOT AUTHORIZED
model forward:                            NOT AUTHORIZED
model generate / GenerationMixin.generate:NOT AUTHORIZED
real model logits:                        NOT AUTHORIZED
network/autodownload/substitution:        NOT AUTHORIZED
prompt/schema/serializer changes:         NOT AUTHORIZED
grammar/lowerer/backend-version changes:  NOT AUTHORIZED
case-specific prompt/grammar:             NOT AUTHORIZED
few-shot/retry/repair/self-critique:       NOT AUTHORIZED
production WellPlot changes:              NOT AUTHORIZED
PILOT-01:                                 NOT AUTHORIZED
```

## Result policy

PASS means only:

> the selected XGrammar constrained-decoding infrastructure is ready for an
> independently authorized pilot.

PASS does **not** authorize inference.

On any failed mandatory gate:

```
PREFLIGHT FAIL
MODEL CALLS = 0
STOP
```

Do not fix a failure by changing a frozen scientific variable.

## Execution protocol

Proceed autonomously within this authority. Routine implementation structure is
implementation-agent owned.

Do not return a serial questionnaire.

Only a genuine frozen-contract blocker should produce one batched SOL blocker
handoff.

## Required closeout

Return:

- candidate / tip / remote head
- exact changed paths
- P1–P9 table
- complete pre-inference run manifest
- XGrammar adapter/parity evidence
- six-case hash-manifest evidence
- resource evidence
- explicit model/weight/forward/generate/download counters
- PASS or FAIL
- explicit statement that `PILOT-01` remains unauthorized

Then STOP for independent review.
