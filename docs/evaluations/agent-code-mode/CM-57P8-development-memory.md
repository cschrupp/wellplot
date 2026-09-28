# CM-57P8 Development Memory

## Status

CM-57P8 provider-free implementation was frozen at
`ac68fcdc5ec527aa0be4007e4188bdfda1e1c3ac`, with the reviewed evaluator
correction at `d224a015cbd77c6477665daefa5542336416c422`. The authorized live
matrix is complete and recorded below; production adoption remains
unauthorized.

P7 remains accepted as diagnostic evidence with decision
`INCONCLUSIVE_PROMOTION_EVALUATION`. Its exposed raw evidence is frozen at
SHA-256 `b4cb75aaf6a5ffe8c7f88c6e730d32247d973ea974269132a76b814633ff4d2f`.
P7 is not a promotion holdout and must not be treated as fresh acceptance
evidence.

## Purpose

P8 is a 2x2 prompt-factor localization experiment. It asks whether the
report-boundary instruction, the section-composition instruction, or their
interaction explains two P7 observations:

- unexpected `track.reference` selection when `binding.curve` permits
  `track.normal` or `track.reference` as alternative parents;
- repeatable production `PLANNER_SCHEMA_FAILURE` on the two selected P7
  schema targets.

The experiment does not assume that the alternative-parent interpretation is
the cause. It localizes prompt factors only and does not fix, reinterpret, or
promote any result.

## Frozen Design

The arms run in fixed order `P -> R -> C -> RC`:

- `P` is the exact production planner prompt.
- `R` appends the frozen P4 report-boundary instruction.
- `C` appends the frozen P4 section-composition instruction.
- `RC` is the existing frozen P5/P7 combined prompt.

All arms use the production `SemanticPlanner`, production `SemanticPlan`
response schema, production validator and its two-call correction/retry
behavior, the same source summary, registry, request, model, and controls.
No RCV/RCS behavior, non-empty-report schema, invariant planner, worker,
program, repair, catalogue change, or deterministic parent selection is part
of P8.

The selected cases are referenced by ID from the frozen P7 corpus in
`cm57p8_prompt_factor_cases.json`; request text is not copied into the
manifest. The manifest stores request/gold hashes and bounded P/RC historical
anchors derived from the verified P7 raw artifact. The selected roles are one
protected reference target, reference probes, positive and negative reference
controls, and schema-complexity controls.

## Frozen Provenance

P7 corpus SHA-256:
`4aebee0d2734cb272c6ae002aec277e58427dd5dce44e38e5fdf1a14a4dccd12`

P7 live-summary SHA-256:
`c10e909384a6a1d75f11d74979a3804a6f13b8505e56de5a638af3a29032300c`

P7 raw SHA-256:
`b4cb75aaf6a5ffe8c7f88c6e730d32247d973ea974269132a76b814633ff4d2f`

P5 harness SHA-256:
`3170c970d2ad4298f87c09cb106237d015356e4a5854095e3f889ba139bc600e`

Prompt hashes:

- `P`: `5e7a0732af01e4b1f16b3ccf019c005ea2e9ba5c0e93e94870a56a261e2bca18`
- `R`: `fe8db9c9cba4cf7bf13d79c3e838eaa53e19770fbf6dd764cdcf93020008c563`
- `C`: `b140a019889502f247335e34aee6283e0b06848957d9f89f5755170967e4a85e`
- `RC`: `e1710cb516a96c47ec1d0593752e83aacc1bb4502c3026b2b6a9a676c90e4d34`

Production response schema SHA-256:
`3a331166ccc570a74056dea7770d04b16f8fa32dc3641d6c37de6c26cf81d9e3`

Source-summary SHA-256:
`ec6147a1b5e1ac6374e34ae3d66d11275542c6b340337cb26d3ae1d06240532e`

Future controls are model `qwen3.6-35b-a3b`, planner temperature `0.0`,
`max_tokens=16384`, and timeout `900` seconds. The future population is 12
cases x 2 attempts x 4 arms: 24 rows, 96 planner executions, and 96-192
provider calls. Worker/program calls must remain zero.

## Interpretation

The protected reference target is classified only after its own P/RC
historical anchors reproduce on both attempts. The schema targets have an
independent P/RC anchor gate; an unrelated selected-case mismatch must not
erase evidence from the other mechanism axis. The bounded labels are:

- `REFERENCE_SECTION_COMPOSITION_SUFFICIENT`
- `REFERENCE_REPORT_BOUNDARY_SUFFICIENT`
- `REFERENCE_RC_INTERACTION_REQUIRED`
- `REFERENCE_MULTIPLE_FACTORS_SUFFICIENT`
- `REFERENCE_FACTOR_UNSTABLE`
- `INCONCLUSIVE_REFERENCE_LOCALIZATION`

The schema targets measure whether a structured `SemanticPlan` becomes
available within the production two-call budget. Invalid structured output is
an experimental schema outcome, not infrastructure failure. The bounded
labels are:

- `SCHEMA_SECTION_COMPOSITION_SUFFICIENT`
- `SCHEMA_REPORT_BOUNDARY_SUFFICIENT`
- `SCHEMA_RC_INTERACTION_REQUIRED`
- `SCHEMA_MULTIPLE_FACTORS_SUFFICIENT`
- `SCHEMA_STABILIZATION_CASE_DEPENDENT`
- `SCHEMA_FACTOR_UNSTABLE`
- `INCONCLUSIVE_SCHEMA_LOCALIZATION`

`SCHEMA_STABILIZATION_CASE_DEPENDENT` is stable and interpretable evidence,
not an inconclusive outcome: it records different stable factor patterns on
the two schema targets. Only `SCHEMA_FACTOR_UNSTABLE` and
`INCONCLUSIVE_SCHEMA_LOCALIZATION` make the schema axis unavailable.

The top-level labels are `PROMPT_FACTOR_LOCALIZATION_COMPLETE`,
`PROMPT_FACTOR_LOCALIZATION_PARTIAL`, and
`INCONCLUSIVE_PROMPT_FACTOR_LOCALIZATION`. Population drift, infrastructure
failure, worker calls, or evidence corruption fail closed. Historical-anchor
failure is axis-specific: one localized axis can produce
`PROMPT_FACTOR_LOCALIZATION_PARTIAL` while the other axis is inconclusive.
Positive reference controls are reported separately so an apparent factor
effect cannot be treated as a remediation if it removes legitimate reference
tracks.

## Evidence Safety and Hard Stop

Rows may retain bounded hashes, call kinds, provider categories, plan shape,
semantic projections, classifications, and execution metadata. They must not
retain provider prose, prompts, hidden reasoning, API keys, authentication
data, or arbitrary filesystem paths. The future JSONL path is
`/tmp/cm57p8-prompt-factor-qwen.jsonl`; it must be absent or empty before any
provider construction, and partial evidence must never be resumed or
appended.

The pre-live implementation checkpoint had provider calls `0`. No remediation
instruction, capability-catalogue change, validator, schema change, routing
change, typed-worker work, or CM-57D work began in P8. Production changes
remain `0`; production adoption is `NOT_AUTHORIZED`; CM-57D remains
`BLOCKED`.

## Live Evaluation

Live inference was authorized only at checkpoint
`d224a015cbd77c6477665daefa5542336416c422`. The complete fresh matrix ran
against the controlled local OpenAI-compatible endpoint at
`http://192.168.2.140:8888/v1` with the frozen Qwen controls. It produced 24
of 24 rows, 96 planner executions, 102 provider calls, and zero worker/program
calls. The raw JSONL remains outside the repository at
`/tmp/cm57p8-prompt-factor-qwen.jsonl` with SHA-256
`0c9bb86c11a229ea387c2e597a374af80cfa9af4204f1da2054865cff6f8b451`.

The result is `INCONCLUSIVE_PROMPT_FACTOR_LOCALIZATION`. Population integrity
passed and all arms produced plans, but the protected reference anchor and
schema-target historical anchors did not reproduce, so neither localization
axis was interpretable under the frozen decision contract. This is not a
production failure and does not authorize prompt adoption or CM-57D.

Two interrupted populations were preserved separately and excluded from the
decision. The first, created while the server network was misconfigured, has
SHA-256 `df7a8dc53310c765bfc14e763319558e5b5b37375a8ae2903ebcc9363752b4ec`.
The second stopped after the endpoint address changed from `.142` and has
SHA-256 `934ec0c77757e020fd6172b0f98e260916813857892179a115a35ee343724ec2`.
Neither artifact was appended to or resumed.

The bounded aggregate is recorded in `CM-57P8-live-summary.json`. Production
changes remain `0`, production adoption remains `NOT_AUTHORIZED`, and CM-57D
remains `BLOCKED`.
