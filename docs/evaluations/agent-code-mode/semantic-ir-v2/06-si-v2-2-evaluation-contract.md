# SI-V2.2 Evaluation Contract

## Evidence Basis

The evaluation separates structural/schema acceptance from semantic correctness
because they are different properties. JSON Schema describes and validates an
instance shape; Pydantic's `model_validate` supplies the local typed-model
check; deterministic projections compare domain meaning. Strict structured
output is therefore an L1 measurement, not the L2 score.

This is adapted from established practice, not a claim that constrained output
guarantees semantic understanding:

- OpenAI's structured-output contract documents strict JSON Schema adherence as
  a schema-format guarantee, with only a supported JSON Schema subset:
  https://platform.openai.com/docs/api-reference/responses-streaming/response/refusal
- JSON Schema documents validation keywords and instance validation separately:
  https://json-schema.org/learn/getting-started-step-by-step
- Pydantic documents `ValidationError` as the result of typed validation:
  https://docs.pydantic.dev/latest/concepts/models/

The WellPlot-specific semantic projection and gold comparison are therefore a
deterministic evaluation design adapted to this project. No LLM judge is used.

## Row Contract

Each row is bounded and binds to:

```text
case_id, family, attempt, request hash
prompt/schema/gold/compiler/registry hashes
endpoint PRE identity and fingerprint hash
provider call count and bounded trace
initial/final structural status
semantic projection and bounded difference paths
context-preservation projection
compiler status/error/signature
CM-58 layer evidence and actions
raw/final system status
```

API keys, headers, arbitrary exception prose, and unbounded raw provider
telemetry are excluded. A parsed `SemanticIRV2` object is retained because it
is the primary evaluation artifact.

## Layer Semantics

### L1 Structural

`STRUCTURAL_PASS` requires a `SemanticIRV2` value validated through the frozen
Pydantic model. Initial failures, retry use, retry recoveries, bounded provider
diagnostic reasons, and terminal failures are all counted separately.

### L2 Semantic

The hard projection compares report presence, section count/order, ordered
feature kinds, reference flags, fill target topology, annotation multiplicity,
extension keys, and report/section allocation. Local semantic IDs are
normalized to feature positions for relationships. Requirements, constraints,
source hints, existing-section hints, and unresolved requirements are reported
as separate normalized context diagnostics and do not receive fuzzy credit.

### L3 Compiler

Every structurally valid intent is compiled, even when its semantic projection
is wrong. Unknown or ambiguous semantic lowering is an expected fail-closed
outcome. A compiler invariant failure is reserved for a gold-equivalent
semantic intent that cannot be lowered or whose downstream signature is wrong.

### L4 CM-58

Every successful compilation is passed through the existing CM-58.1,
CM-58.2, and CM-58.3 functions in order. CM-58 does not alter the recorded L2
result. A changed final plan can be a safe repair, a safety rescue, a wrong
final escape, or a safety regression; these are reported independently.

## Lifecycle and Integrity

`--prelive` validates the 24-case corpus, 24 gold fixtures, exact SI-V2.1
artifacts, prompt restrictions, and gold compilation without constructing a
provider. `--live` requires the exact reviewed checkout, fresh evidence paths,
PRE endpoint fingerprint, then performs 48 sequential attempts and captures
POST immediately. `--finalize` performs no provider or endpoint calls.

The finalizer rejects missing/duplicate/reordered rows, hash drift, checkpoint
drift, provider-call budget violations, worker calls, invalid or changed
endpoint identity, and partial populations. It never resumes or reruns a
population.

## Stop Rule

The first complete valid population is the only qualification population. No
prompt revision, schema change, provider comparison, model substitution,
selective rerun, CM-58 modification, production integration, or SI-V2.3 is
authorized by this contract.
