# CM-57C Development Memory

## Authority and Boundary

CM-57C is the broader unseen shadow-validation slice based on authorized
baseline `639332ddb4258569fedd65155eafaf5c220eb6b2`. It tests the inactive
production-native typed section boundary against a new 16-case corpus, with two
future attempts per case. The resulting population is 32 rows and has one
RS-production arm; the earlier P/R/S factorial is not repeated.

This is the design baseline only. A future live run must receive a separate
full lowercase 40-character `--authorized-checkpoint`; the harness requires
the checkout to equal that SHA and records it on every raw row. It also records
`design_baseline_sha` separately. Before provider construction, the harness
compares the reviewed script, corpus, production typed worker/planner, frozen
CM-56 evaluator/corpus, and CM-56 source directory byte-for-byte with the
authorized commit. Unrelated worktree changes remain allowed.

The future path is the real production sequence:

```text
request
  -> SemanticPlanner
  -> SemanticEnricher
  -> TypedSectionCompiler
  -> SectionSemanticDraft validation
  -> deterministic semantic compiler
```

The harness does not manually construct live `SectionTask` values, append
authoritative input, or add semantic metadata. It uses the production provider
input builder, production prompt, response schema, context validation, and
compiler. Existing planner retry/correction behavior remains the only planner
retry behavior. Provider calls in this pre-live slice are `0`.

## Corpus

`tests/fixtures/typed_worker/cm57c_shadow_cases.json` contains exactly 16
distinct unseen requests covering:

- new linear, logarithmic, tangential, reverse, repeated-channel, ordered, and
  reference-track curve semantics;
- alternate-source selection;
- generic and waveform raster profile paraphrases;
- VDL and partial sample-axis semantics;
- independent sample bounds;
- explicit omission of raster profile/sample-axis semantics;
- multiple raster bindings and mixed curve/raster composition.

The corpus reuses only the existing physical source fixture files. Candidate
IDs, request strings, titles, and semantic tuples are new and are audited
against the closed CM-56 corpus. Expected sections, input facts, case IDs,
categories, and evaluation families are evaluator-only and are not provider
input.

## Frozen Controls and Artifacts

Future live controls are fixed at:

```text
model                 qwen3.6-35b-a3b
planner temperature   0.0
worker temperature    0.0
max output tokens     16384
max tokens parameter  max_tokens
timeout               900 seconds
attempts per case     2
```

The production anchors checked by the pre-live harness are:

```text
base prompt                 19b0e289d2fa8ea362840aa94d90ad43cdea5b2ebdc866363df1ef28a38f2d49
request-only prompt         7e519241911d3fbd61d8de4134c71ae69b98646a6b4e5a4ea61ba0a7a0318f69
request-plus-metadata       10ed56fc716165dca783f6d92805b7541f63b4044dcbcd4ac0207191f0771a80
response schema              93f1b7d26f1196a1105b733bc13a8de784da19f44eaaa990989d59abaf9fa2d4
raster metadata projection  67aa2d6f579343e60f9261eb654fd62bde21605b1c8c68f080b5b74ff01c3f46
evaluator                   cm56r8r.corrected-evaluator.v1
evaluator source            4bddc22e5a8267cd36e96624884eba8c8578fdd229c7d71c0bd7986bcab12e49
```

The future evidence path is `/tmp/cm57c-live-qwen.jsonl`; non-empty evidence
is rejected. The default CLI performs only the pre-live audit. Live execution
requires `--live-authorized`, the exact full authorized checkpoint SHA, and an
explicit provider base URL.

## Evaluation Rules

The evaluator reuses only the generic corrected semantic comparison logic from
CM-56R8R. Title fidelity is reported separately and is not part of the primary
scientific gate. Source selection, topology, binding multiplicity, protected
generic semantics, and unrequested scientific extras remain protected. Raster
profile and sample-axis behavior are the target generalization families.

Decision precedence is deterministic and has no aggregate thresholds:

```text
invalid population/artifact or provider infrastructure
  -> INCONCLUSIVE_GENERALIZATION
planner/enrichment/schema/context/compiler failure
  -> GENERALIZATION_PIPELINE_FAILURE
protected generic/source/topology or unrequested-extra regression
  -> GENERALIZATION_REGRESSION
raster target-only semantic gap
  -> GENERALIZATION_TARGET_GAP
all primary semantics pass
  -> GENERALIZATION_VALIDATED
```

Regression is determined from failed scientific families rather than case
category. Source selection, topology, track/binding scale, multiplicity, and
scientific extras dominate raster-profile/sample-axis target gaps. An
unclassified scientific failure also fails closed as a regression. Title
fidelity is reported separately: a title-only mismatch may leave scientific
acceptance true while making full acceptance and title fidelity false.

After a complete population, the append-only raw rows are grouped by case and
the two normalized `semantic_projection` values are compared with only local
`semantic_id` fields removed. The summary reports `same_semantic_projection`,
`stable_cases`, `unstable_cases`, and unavailable projections without making a
statistical claim.

## Hard Stop

The pre-live implementation adds no files under `src/wellplot`, makes no
provider calls, and changes no prompts, schemas, metadata, planner, enricher,
compiler, routing, or active workflow. CM-57D, identity work, title-fidelity
work, and route activation remain unauthorized. Stop after deterministic
validation and independent review; do not run the local provider from this
checkpoint.

## Authorized Live Result

The authorized live population ran from checkpoint
`df9b6181eeb6b70cf26f9b1940449f66a217a248` with the frozen local
`qwen3.6-35b-a3b` OpenAI-compatible provider. The run used 16 cases, two
attempts per case, planner and worker temperature `0.0`, `16384` maximum
output tokens, `max_tokens`, and a 900-second timeout. The raw evidence remains
outside the repository at `/tmp/cm57c-live-qwen.jsonl` with SHA-256
`57df9720bc2eb7b05fcb815de84062815382b13c84f5878da8c948e08e41cba8` and 32
rows.

The population was complete. It made 43 planner calls and 11 worker calls,
with zero provider-infrastructure failures. Eleven rows reached typed
structured validation, context validation, and deterministic compilation; 21
rows stopped at planner/enrichment capability matching. Of the 11 typed rows,
6 passed scientific acceptance, 4 passed full semantic acceptance, and 9
preserved title fidelity. Repeatability was stable for 4 cases, unstable for 1
case, and unavailable for 11 cases because both attempts did not reach a
semantic projection.

The aggregate decision is `GENERALIZATION_PIPELINE_FAILURE`. The failure is
not evidence of a provider outage or a typed-runtime failure: it is evidence
that the existing planner/enricher boundary did not reliably produce the
expected capability decomposition for the unseen corpus. The raw JSONL is
immutable and the committed aggregate is
`CM-57C-live-summary.json`. No production, prompt, schema, metadata, routing,
corpus, or harness changes were made after live authorization. CM-57D remains
blocked.
