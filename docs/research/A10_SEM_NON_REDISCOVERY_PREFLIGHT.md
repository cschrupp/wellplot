# A10 Semantic Non-Rediscovery Preflight

**Status:** `A10_SEM_NON_REDISCOVERY_PREFLIGHT_ACCEPTED_WITH_BACKEND_PROVENANCE_EXCEPTION`
**Purpose:** accepted non-rediscovery inventory; no prompt/schema design,
semantic benchmark, or production semantic changes.

## 1. Scope and terminal status

The scope is to preserve the current A10 branch, bind current work to existing
historical evidence, inspect the current planner contract, and identify the
remaining backend-specific unknown without another generation call.

The A10 branch is `engineering-d5-binding-path-repair`. The harness-only wire
observability change was committed as `79eb8ebdea02777af99035601362109b3e3ab0c9`
(parent `f7a99f642d272599a3db1e595aab8c073ed25911`) and pushed to the same
branch. A subsequent read-only `git ls-remote` returned that exact SHA. The
commit changes only `scripts/nlp_d5_live_semantic_qualification.py` and
`tests/test_nlp_d5_live_semantic_qualification.py`. Existing notebook edits and
untracked `examples/families/` were not staged or changed.

Provider/model generation calls: `0`. The only successful server request in
this audit was one credential-bearing, non-generative `GET /props`; a preceding
unauthenticated `GET /props` returned HTTP 401. No completion, chat, tokenization,
or apply-template POST was issued.

The non-rediscovery inventory is accepted as useful and complete for corpus
adaptation. The exact deployed converter source remains unresolved, but that
provenance exception does not block the separately authorized bounded
synthetic schema-behavior probe. No backend mismatch is claimed here.

## 2. Non-rediscovery decision table

| Question / asset | Classification | Established evidence and boundary |
| --- | --- | --- |
| TW-02 / TW-02I: model-owned versus host-owned facts; input sufficiency | `ALREADY_ANSWERED` | Typed input ownership and provider-visible sufficiency were investigated. Reuse the ownership/input audit; do not rerun the historical factorial. |
| TW-03 / TW-03S: structural validity versus semantic correctness | `ALREADY_ANSWERED` | Structural constraints and semantic grading are distinct. Valid JSON/schema output is not semantic acceptance. |
| TW-05 / TW-06: exact schema representation and controlled bisects | `ALREADY_ANSWERED` | Exact schema hashes and one-variable bisects already showed schema representation can affect structured generation. Reuse that method if a new current-IR question is approved. |
| TW-07 / TW-08: defaulted versus required discriminator | `HYPOTHESIS_TRANSFER_ONLY` | Historical result is tied to a discriminated-union mechanism absent from the current `_PlannerWirePlan`; it motivates testing exact current conversion but is not a conclusion about this schema. |
| CM-56R8: capability-local semantic text | `ALREADY_ANSWERED` | It recovered selected mappings in its tested scope, not a universal semantic repair. |
| CM-57P10: prompt structure | `ALREADY_ANSWERED` | The controlled prompt comparison established a large effect on its frozen population. It does not authorize reusing RC. |
| CM-57P5 / P7 / P10 / CM-59A-E2 corpora | `ALREADY_ANSWERED` | The historical cases and gold semantics are locally present and verified below. Adapt scoring to current IR rather than rebuilding cases. |
| CM-57P8 canary labels | `ALREADY_ANSWERED` | The manifest has labels/hashes, not request text; its 12 cases join to P7 exactly. |
| CM-57IB | `HISTORICAL_REFERENCE_ONLY` | `WORKER_LAYER_HISTORICAL_ASSET`; typed-worker/input-boundary study, not planner data. |
| RC | `HISTORICAL_REFERENCE_ONLY` | `HISTORICAL_REJECTED_REFERENCE`; not an authorized arm and must not be run or adapted into production. |
| Current `_PlannerWirePlan` schema in exact deployed converter | `BACKEND_VERSION_SPECIFIC` | Runtime identity is observed, but no non-generative endpoint or local executable for its JSON-Schema-to-grammar converter was found. Unresolved; no substitute build/master inference is permitted. |
| Current schema/Pydantic parity | `MECHANISM_KNOWN_CURRENT_IR_UNTESTED` | Source inspection identifies current Python-only cross-field rules. Exact deployed grammar enforcement remains unknown. |
| B01 contamination of A10-SEM-01 holdout | `ALREADY_ANSWERED` | Exact request match and SHA confirmed below; B01 is exposed diagnostic data, not a fresh holdout. |
| A new live prompt/schema study | `LIVE_REVALIDATION_REQUIRED` / not proposed | No new study is proposed here. Existing evidence must be used first, and a future study requires its own explicit scope/decision. |

Do not rebuild TW-05/06 without their established one-variable method; do not
label generic structured-output failure a new mechanism; do not treat missing
raw-I/O custody as a discovery; do not reopen RC; do not transfer CM-57IB worker
effects into planner prompt instructions; and do not use old aggregate scores as
current acceptance thresholds.

## 3. Historical planner corpus inventory

Each accepted experiment summary identifies the checkpoint used for its
execution. Git blob IDs were compared between those checkpoints and current
HEAD `79eb8ebdea02777af99035601362109b3e3ab0c9`.

| Corpus | Fixture | Accepted checkpoint | Git blob at checkpoint = current | Cases / requests | Family distribution |
| --- | --- | --- | --- | ---: | --- |
| CM-57P5 | `tests/fixtures/typed_worker/cm57p5_fresh_holdout.json` | `aea88a0611804b88bf1694448283cd5818977c55` | `9a28e601617aae0151d0d8e9d93e08dd7f7a2902` | 24 / 24 | REPORT_ONLY 4; SINGLE_SECTION 4; HETEROGENEOUS_SECTION 4; MULTI_SECTION 4; MIXED_REPORT_SECTION 4; CAPABILITY_MULTIPLICITY 4 |
| CM-57P7 | `tests/fixtures/typed_worker/cm57p7_fresh_promotion.json` | `f952c64f735b6c3bc7519677c2d36ca80e980609` | `aae31fb572a95e76b1633a462df67baa9aa56350` | 24 / 24 | REPORT_ONLY 4; SINGLE_SECTION 4; HETEROGENEOUS_SECTION 4; MULTI_SECTION 4; MIXED_REPORT_SECTION 4; CAPABILITY_MULTIPLICITY 4 |
| CM-57P10 | `tests/fixtures/typed_worker/cm57p10_final_promotion_cases.json` | `fd3448487cbd3418bbcb33a89ce5e5b809198e42` | `2fc48cadeb56f1dd4d4d08634b1d3fb4b0559dfc` | 24 / 24 | REPORT_ONLY 4; SINGLE_SECTION_NO_REFERENCE 4; MULTITRACK_SINGLE_SECTION 4; MULTI_SECTION 4; MIXED_REPORT_SECTION 4; REFERENCE_REQUIRED 4 |
| CM-59A-E2 | `tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json` | `038a68a4f582215b11648e2c659d130adba948e8` | `c2bc13649f87cb87f7fd51fc075752e4bd76d7b0` | 24 / 24 | REPORT_ONLY 4; SINGLE_SECTION 4; MULTI_SECTION_ALLOCATION 4; REFERENCE_REQUIRED 4; MIXED_REPORT_SECTION 4; MULTITRACK_SINGLE_SECTION 4 |

Combined inventory: 96 cases, 96 request strings, **zero duplicate exact
request strings**. Gold fields include report capability IDs, section
capability sets, and expected unresolved counts; CM-59A additionally carries a
residual-class label. This is a historical typed-worker capability signature,
not current `SemanticOperation` wire serialization.

The union of expected capability IDs is:
`annotation.typed`, `binding.curve`, `binding.raster`, `report.standard`,
`section.log_plot`, `track.annotation`, `track.array`, `track.normal`, and
`track.reference`. All nine are present in the current built-in production
registry (10 total built-ins). No expected capability is missing.

Adaptation disposition for the four planner corpora:
`REUSE_REQUEST_AND_GOLD_SEMANTICS` plus `ADAPT_SCORER_TO_CURRENT_IR`.
Request bytes and semantic gold remain reusable; current operation ownership,
target semantics, unresolved disposition, source/capability invention, and
safe rejection must be scored invariant-wise. Do not require historical wire
serialization. No case corpus is to be duplicated or rewritten.

## 4. CM-57P8 canary join and CM-57IB separation

`tests/fixtures/typed_worker/cm57p8_prompt_factor_cases.json` has 12 metadata
rows and no request text. All 12 join to CM-57P7 by exact `case_id` and SHA-256
of the P7 authoritative request (`request_sha256`); no missing, duplicate, or
mismatching join was found. The joined P7 request and gold remain authoritative.

The P8 role vocabulary includes protected reference target, reference-probe
schema-failure target, report-only reference probe, reference probe, positive
reference control, positive reference-control schema-failure target, negative
reference control, and mixed-report / schema-complexity controls. Retain the
actual per-case labels in the manifest when adapting tests; do not replace the
P7 text with copies in a new corpus.

CM-57IB remains `WORKER_LAYER_HISTORICAL_ASSET`: five cases derived from the
worker/shadow corpus, 15 planner/enrichment rows and 60 worker calls in its
historical live design. It does not belong in the planner corpus or current
planner regressions. Its input-sufficiency findings may inform analysis, but
its retired typed-worker prompt additions must not be appended to the planner.

## 5. CM-59A latest result and RC status

The applicable latest result is `CM-59A-E2`, not the earlier intermediate
21/24 state. Its retained summary reports 22 stable passes, zero stable wrong
final-plan escapes, four terminal planner failures (all schema-validation
class), and governing decision `SYSTEM_REEVALUATION_REJECTED`. That rejection
stands; the 22 stable passes do not promote the candidate.

CM-57P5's historical P/RC comparison reported P 4/24 stable and RC 16/24
stable, while RC failed its governing decision contract. Later CM-57P10 records
`FINAL_PROMOTION_RC_REJECTED`. RC therefore remains
`HISTORICAL_REJECTED_REFERENCE`, not a current or future experimental arm
without a formal reopen.

## 6. Holdout contamination

The frozen A10-SEM-01 benchmark has 53 cases and is retained unchanged at
`workspace/evaluations/a10-sem-01-20261110/benchmark.json` (SHA-256
`595839779e9ca59d9ce8ff20cbbdaf006ad41138b4510acc0ea26733e080067a`). B01 is
one of those cases, with exact request `Plot Gamma Ray.` and exact UTF-8 request
SHA-256 `404a98eb0f9e40014aaf8312e53aea8a3267ea076963bff7420f1827196d7517`.
This is exact byte equality, not semantic similarity.

Record `A10_HOLDOUT_CASES_EXPOSED = 1`. The benchmark must not be changed or
reworded. B01 is `EXPOSED_DIAGNOSTIC_CASE`, not a fresh holdout observation.
Fresh holdout count is 52 of 53, assuming no other case exposure is established
by the campaign ledger. That assumption must be checked against any later
campaign ledger before reporting an acceptance denominator.

## 7. Current planner schema / validator parity

The transmitted schema is generated from `_PlannerWirePlan.model_json_schema()`
and wrapped by the provider as strict `json_schema` named `_PlannerWirePlan`.
The canonical sorted compact schema SHA-256 is
`b6b05fec2caabbc62708d17b1d752d8888e6cf7e2b91b4b67889eb583b080cbb`.
The exact local schema artifact is
`/tmp/a10-sem02-b01-forensic-planner-wire-schema.json` (file SHA-256
`04e7577473df3bc8c49b3206eb21b5f985f0bd978577ea285a79e23c91bb7faa`).

| Invariant | Emitted JSON Schema | Pydantic / immediate planner validation | Later host validation |
| --- | --- | --- | --- |
| Root executable work | Custom `allOf` + `anyOf`: non-null `report_task` OR `section_tasks` with `minItems:1` | `_PlannerWirePlan.validate_work_units` repeats work-required invariant | Request-scope attachment, semantic plan validation and reconciliation enforce independently compiled authority |
| Report-task presence | Optional field, but non-null required by one root branch | Optional in model; root validator enforces at least one work unit | Report operations are checked for report scope and capabilities |
| Section-task cardinality | Array; root branch requires at least one; no schema max | Tuple, no explicit max at model field | Resolved task scopes must match request-declared scope set; duplicate scope assignments reject |
| `existing_section_hint` | Schema-extra makes key required; value may be nonempty string or null | `model_validate` rejects omitted key | Revise validation rejects null; host resolves hint to actual section |
| Capability requirements | Section `capability_ids` min 1; report capability list optional; string items | Same field min/default behavior | Registry resolution, canonical ID/category checks, uniqueness and parent closure |
| Operations cardinality | Report and section arrays `minItems:1`, `maxItems:20`; required | Matching Pydantic tuple constraints | Operations are lowered/authorized against request and canonical object contracts |
| CREATE / ENSURE semantic reference | Enum/field schema describes optional `semantic_ref`; no conditional requirement | `SemanticOperation.validate_operation_shape` requires it | Deterministic semantic resolver/lowerer checks supported kind and target |
| SET field-value cardinality | `field_values` is an array; no conditional exactly-one rule for `verb=SET` | Pydantic validator requires exactly one | Typed lowering/field allowlist validation follows |
| Unresolved-only response | Root work-unit constraint rejects summary + unresolved fields without a task | Same root work-unit validator | Unresolved requirements/semantics do not authorize silent publication |
| Object-kind / verb relationships | Separate enums, no cross-field relation encoded | Pydantic checks required operands for CREATE/ENSURE, UPDATE/REMOVE/SET/MOVE and MOVE-only anchors | Semantic action mapping and worker contracts enforce operation/object compatibility |
| Local/scope references | Individual regex patterns are represented; relational references are not | `_validate_operation_references` enforces uniqueness, report scope, section scope, and reference consistency | Host scope binding and canonical target validation |
| Capability closure | Arrays of strings only; dynamic allowed-parent closure is not in JSON Schema | Registry-aware `validate_semantic_plan` closes parents and validates categories | Canonical compiler/worker capability validation remains final authority |

This is a source/schema comparison, not a claim about deployed grammar
enforcement. The current schema does encode the root work-unit invariant that
was missing in the historical SR7 `SemanticIRV2R` example. It does **not** encode
several conditional/registry-dependent Python checks listed above.

## 8. SR7 evidence reconciliation

The authoritative record is
`docs/evaluations/agent-code-mode/semantic-ir-v2/67-si-v2r-sr7-p1-result.md`.
It records 44 initial structural failures that were valid JSON, accepted by the
exact JSON Schema stage, and rejected by canonical Pydantic validation. The
localized earlier mechanism is documented in
`57-si-v2r-sr7-c1-validation-localization.md`: a Python-only `work_required`
root invariant that the then-generated schema did not encode.

Applicability: this proves the general schema/Pydantic parity risk and the need
for exact schema-bound testing. It does not prove the same root gap in current
`_PlannerWirePlan`, whose schema now explicitly carries the `allOf`/`anyOf`
work-unit constraint. Current cross-field operation checks and dynamic
capability closure remain separate parity questions. Do not rerun SR7 as if it
were unknown.

## 9. Exact deployed backend identity and converter gate

The successful non-generative `/props` response identified build
`b11669-378a347ce`, model configuration `qwen3.6-35b-a3b`, context size 65,536,
one server slot, and no GGUF byte identity. The prompt template was present in
the response; its raw body is not copied into this report. No model path or
credential is recorded.

### Upstream provenance exception

Public upstream release records identify build label `b11669` with llama.cpp
v0.7.0 at commit `620d222` ([upstream release workflow](https://github.com/ggml-org/llama.cpp/actions/runs/38766206652/attempts/1)).
The deployed `/props` build string is `b11669-378a347ce`; the suffix does not
identify the deployed source as that public commit. The suffix was not
resolvable as an upstream commit in the checked GitHub repository/API. Thus:

`DEPLOYED_SCHEMA_CONVERTER_SOURCE = UNRESOLVED`

Do not describe the deployed custom build as byte-identical to upstream
v0.7.0, and do not substitute upstream source behavior for direct deployed
behavior. This is a provenance exception, not a blocker to bounded synthetic
decoder probes against the actual configured endpoint.

No local `llama-server` or converter executable was available. The deployed
server's inspected non-generative metadata route is `/props`. Existing project
research records and the upstream server interface distinguish `/apply-template`
(chat-message formatting without inference) from the internal
`json_schema_to_grammar` conversion invoked by structured chat completion. No
non-generative schema-to-grammar route was established here. Calling the
structured chat-completion route, even if expected to reject/stop early, would
be a provider request and could enter inference; it was not used.

Consequently the following remain **NOT ESTABLISHED**: converter output for the
exact current schema; generated grammar bytes/hash; warnings/errors/skipped
keywords; enforcement of `allOf`, `anyOf`, `not`, `minItems`, `pattern`, `$ref`,
`required`, nullable unions, `additionalProperties:false`, and operation
cardinality; and grammar-versus-JSON-Schema-versus-Pydantic acceptance for the
requested synthetic objects. These are assigned to the bounded backend probe;
until then do not infer them from current upstream master, another llama.cpp
build, TW-07/08, or the model's prior response.

The local schema SHA and `/props` build identity are necessary provenance but
are not themselves converter evidence. Do not fabricate grammar results or
claim exact converter source identity without direct evidence.

## 10. Historical-to-current prompt comparison

This is an offline instruction-family comparison; it does not evaluate prompt
quality and does not authorize edits.

| Instruction family | Historical P / rejected RC versus current planner | Classification |
| --- | --- | --- |
| Report ownership | RC explicitly restricts `report_task` to genuinely report-wide work and prohibits placeholder reports for section-only requests. Current prompt explicitly says report-only uses a report task with no sections, but lacks the converse “section-only => `report_task=null`” rule. | `REMOVED` in current relative to RC; report-only rule `RETAINED` |
| Section ownership/composition | RC has explicit “one independently compilable section” and keep heterogeneous tracks together. Current prompt has equivalent section cardinality/track grouping and full capability-set guidance. | `RETAINED`, expanded |
| Source hints | Current prompt requires preserving source clues and exact supplied labels; historical P/RC did not establish this exact current contract. | `NEW` |
| Existing-section targeting | Current prompt requires exact existing section hint in revise mode; schema/Pydantic also require key presence. | `NEW`/strengthened |
| Capability closure | RC says section capability types stay together; current prompt requires allowed-parent closure recursively and no unrequested capabilities. | `RETAINED`, strengthened |
| Unresolved behavior | Current prompt distinguishes unsupported requirements and typed ambiguity; source absence requires inspected-source evidence. | `NEW`/strengthened |
| Operation semantics | Current prompt requires one typed operation per supported change, declared verbs, ownership scopes, and request-local refs. | `NEW` representation layer |
| Correction behavior | Schema correction is generic and does not include the failed assistant body; semantic correction path includes previous plan. | `CONTRADICTORY` to complete-failure-context goal; see §11 |
| Preservation | Current revise prompt says omitted areas are preserved downstream; host remains authoritative. | `NEW`/strengthened |
| Semantic versus physical ownership | Current operations express semantic concepts; host resolution chooses physical sources/channels. | `RETAINED` ownership principle, adapted to new IR |
| Report/operation instruction repetition | Current prompt repeats “for every supported requested change, emit corresponding operation” in two passages and repeats presentation/dependency-order cautions. | `DUPLICATED` |
| Opening wording | Current opening directs report_task work and one SectionTask per requested section; combined with absent section-only converse it could encourage report-task creation. | `POTENTIALLY_AMBIGUOUS`, static observation only |

The RC arm is inspected only as a rejected historical reference. Its precise
known improvement was report-boundary instruction; it also introduced a
regression under its governing evaluation and remains rejected. Do not use it
as a current arm. P5/P7/P10 historical summaries remain their own evidence and
are not current acceptance thresholds.

## 11. Correction-path and raw-I/O custody audit

### Correction paths

Current schema correction uses `_SCHEMA_CORRECTION_INSTRUCTION`, the generic
`schema_validation` diagnostic, and the original context. It does not attach
the invalid raw assistant response. Current semantic correction is distinct:
`_correction_request` includes the previous validated plan plus the semantic
diagnostic. Classification relative to full failed-response diagnostic custody:
`PARTIALLY_REGRESSED`—semantic repair retains prior plan context, schema repair
does not retain the failed body or detailed errors in its next prompt. This is
an observation, not a proposed correction.

### Planner wire observability now present

Commit `79eb8ebdea` adds a separate private planner diagnostic JSONL in the
existing smoke custody. It captures actual HTTP request bytes (base64) and
decoded request JSON (messages plus exact strict response-format schema), raw
response bytes (base64), assistant content before SDK validation, and the
logical response reason/validation-shape record. It is mode `0600`, capped at
1 MiB per record and 6 MiB per file, appended with fsync, and SHA-sealed in the
existing terminal artifact manifest. Limit/private-file rejection marks
capture `INCOMPLETE` and fails closed. It does not alter the redacted model-I/O
ledger or create a second provider path.

Provider-mocked B01/A04 smoke and observer regressions: 12 passed. Ruff,
format, Python compilation, diff check, and single-engine attestation passed
before the preservation commit. No real provider request was issued by these
tests.

The prior A10 capture contract is only partly automated as a single compact
record: model-input state and planner context are separately retained;
request/schema/raw response/assistant text and validation shape are now
available; validated planner wire and subsequent stage traces remain in their
existing canonical artifacts. A dedicated first-divergence projection is not
currently written; it can be derived from ordered stage traces but must not be
claimed as an explicit captured field. The B01 historical raw bodies remain
unrecoverable from the prior run's local artifacts (only hashes and
validation summaries were persisted); this new capture cannot retroactively
recover them.

## 12. Unresolved questions and stop

1. How can the exact deployed `b11669-378a347ce` schema-to-grammar converter be
   invoked without a model-generation request, using a local executable/source
   artifact proven to match that deployment or a dedicated non-generative
   server interface?
2. Once exact grammar bytes exist, which listed schema constructs does that
   exact converter preserve, reject, warn about, or omit?
3. What do grammar, JSON Schema, and Pydantic each accept for root work-unit,
   empty report/section operations, missing required section fields, invalid
   local-reference patterns, extra fields, and valid minimal report/section
   plans?
4. Which current Pydantic-only operation conditions should be represented in
   provider JSON Schema or retained as explicit host validators? This is a
   later design question, not decided here.
5. Before any future holdout score, which A10 campaign records used B01 and
   whether any other frozen case is exposed? Do not reset freshness by
   rewording B01.
6. What machine-readable first-divergence projection should future semantic
   evidence derive from the existing ordered capture artifacts? No mechanism
   is designed or implemented in this preflight.

**Stop:** no prompt/schema changes, no semantic benchmark, no B01 rerun, and no
production semantic changes. The exact deployed converter source remains
unresolved; this does not block the accepted bounded synthetic backend probe.
Do not claim converter grammar behavior unless the exact converter output is
available. The historical corpus adapter and the separately authorized
synthetic probe may proceed under their stated scope and call ceiling.
