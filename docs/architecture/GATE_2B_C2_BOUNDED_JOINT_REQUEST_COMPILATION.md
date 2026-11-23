# Gate 2B-C2 — Bounded Joint Request Compilation

**Status:** Design candidate for SOL independent architectural review. No C2
implementation or production activation is authorized by this document.

**Reviewed baseline:** `fdfb9ae346cebdcd3664502a679f7b195a350d3e`
<br>
**C1 accepted implementation baseline:** `fe5b750d05e07585c902e61d1f39bc0b0f6e292c`
**Branch:** `design/planner-worker-responsibility-realignment`

## 1. Decision and scope

Extend the existing `compile_request_contract()` with one finite compound
request form, retaining the existing `CanonicalRequirementSet`,
`RequestObligation`, `RequestDependency`, `ScopeDeclaration`, and
`RequestCompilationResult` contracts. The compiler remains the only natural-
language-to-requirement authority. It must either account for the entire
request under an accepted form or return a coverage failure; it must not
compile a convenient subset of a compound request.

Reference request:

> Plot physical GR. Then split the GR curve fill at baseline 0.

C2 is request compilation and host-owned transport only. It does not execute
or schedule either outcome, admit a missing parent operation, change workers,
create a fill, publish a document, or treat the dependency as permission to
perform work. The relation records request intent and a target dependency; it
does not define an execution algorithm.

**DRIFT_CHECK: PASS** — Objective: design bounded joint compilation using the
accepted single compiler and host path. Exit: one reviewable design
checkpoint. Firewall: no second compiler, graph, resolver, worker, verifier,
provider route, or mutation path. Next gate: SOL design review; no
implementation, model calls, workers, publication, or benchmark activity.

## 2. Existing contract and evidence

The following are verified at the reviewed baseline:

| Existing behavior | Source/evidence | Boundary |
| --- | --- | --- |
| `compile_request_contract()` extracts facts and independently checks coverage. | [`obligations.py`](../../src/wellplot/agent/code_mode/obligations.py#L1955) | It currently validates extracted facts before constructing the final `CanonicalRequirementSet`; it emits no dependency for the compound reference request. |
| `CanonicalRequirementSet.dependencies` is an additive tuple defaulting to empty. | [`obligations.py`](../../src/wellplot/agent/code_mode/obligations.py#L319) | Current code accepts legacy serialized sets with no field. A strict older reader rejects new serialized data containing the extra field. |
| C1's `_verify_request_dependencies()` validates one exact joint spelling, four fact records, deterministic IDs, request/span digests, one dependency edge, same-channel identity, fill geometry, and two relation spans. | [`obligations.py`](../../src/wellplot/agent/code_mode/obligations.py#L2238), [`test_d5_5j_obligations.py`](../../tests/test_d5_5j_obligations.py#L960) | It currently requires the anonymous `HOST_CONTEXT` declaration and the reference request currently compiles to `COVERAGE_FAILURE`. |
| Anonymous `HOST_CONTEXT` scope ignores planner hints; explicit request scopes are matched to the request declaration. | [`planner.py`](../../src/wellplot/agent/code_mode/planner.py#L1203), [`GATE_2B_C1_R2_CONSUMER_AUDIT.md`](../reviews/GATE_2B_C1_R2_CONSUMER_AUDIT.md) | The C1 review accepted bounded HOST_CONTEXT behavior only; the complete named REQUEST matrix remains open. |
| The original compilation stays on `SemanticPlan`; attached task obligations are copies with scope/ID rewrites. | [`planner.py`](../../src/wellplot/agent/code_mode/planner.py#L1203) | Task copies are not substitutes for the original compiled requirement set. |
| The graph serializes/revalidates `SemanticPlan`; `CodeModeCompileResult` and `AgentSessionResult` currently project obligations but not the compilation dependency or scope binding. | [`workflow.py`](../../src/wellplot/agent/code_mode/workflow.py#L105), [`facade.py`](../../src/wellplot/agent/code_mode/facade.py#L144), [`session.py`](../../src/wellplot/agent/session.py#L178) | Internal JSON round-tripping is not provenance verification. No current consumer treats a dependency as admission. |
| Notebook and MCP route through `_apply_private_authoring()` and the existing shared postcondition verifier. | [`_private_apply.py`](../../src/wellplot/agent/_private_apply.py#L289), [`direct_notebook.py`](../../src/wellplot/agent/direct_notebook.py#L220), [`agentic.py`](../../src/wellplot/mcp/agentic.py#L125) | The private-apply path currently receives obligations, not a dependency-bearing `CanonicalRequirementSet`. |
| The post-C1 regression triage found no C1 R2 regression in the bounded 215-test selection; the repository-wide run is not a completed green run. | [`POST_C1_CHECKPOINT_REGRESSION_TRIAGE.md`](../reviews/POST_C1_CHECKPOINT_REGRESSION_TRIAGE.md) | This is historical evidence, not a claim that C2 is tested or accepted. |

The accepted C1 consumer audit explicitly says the whole original set must be
checked and that assigned copies must not become dependency authority. C2
preserves that invariant.

## 3. Bounded grammar

Accept exactly two forms, with the same single compound outcome and no trailing
instruction:

```text
Plot physical <MNEMONIC>. Then split the <MNEMONIC> curve fill at baseline <NUMBER>.
In the <SECTION_LABEL> section, plot physical <MNEMONIC>. Then split the <MNEMONIC> curve fill at baseline <NUMBER>.
```

The second form is a request-owned existing-section scope. A concrete positive
example using a name already recognized by the scope extractor is:

> In the Main Pass section, plot physical GR. Then split the GR curve fill at baseline 0.

The compiler must derive `Main Pass` from the original bytes through the
existing scope extraction path. It must not synthesize a `REQUEST` declaration
from a planner task, summary, selected section, or worker assignment. This
example does not close the general named-REQUEST qualification matrix.

Minimum lexical limits:

- `<MNEMONIC>` is the existing bounded uppercase physical-mnemonic form
  `[A-Z][A-Z0-9_]{1,11}` and both occurrences must match byte-for-byte.
- `<NUMBER>` uses the C1 bounded signed decimal form: one to twelve integer
  digits and, optionally, one to twelve fractional digits. Its parsed numeric
  value is retained; no unit conversion or rounding is introduced.
- Keywords may follow the existing case-insensitive keyword behavior. The
  physical mnemonic remains case-sensitive/exact as in C1.
- The named form uses the existing recognized section-target syntax and must
  produce exactly one request-derived `EXISTING_SECTION` declaration. No
  created section, inferred title, or multiple scope is permitted.
- The full request must match one form from start to end. Only bounded
  whitespace variation is allowed. Additional clauses, multiple channels,
  negation, exclusions, another action, conflicting values, extra punctuation,
  a different fill target, or unsupported geometry fail closed.

This is a finite command grammar inside the existing compiler, not a general
English parser. A true full-input match plus exact coverage is important: a
parser that extracts the two familiar fragments while ignoring a third action
would manufacture partial authority. Python's regular-expression API defines
`fullmatch` as requiring the whole string to match; CPython's PEG work provides
a primary-source precedent for explicit grammar productions and unique parse
structure, but neither source establishes natural-language understanding for
WellPlot. See [Python `re.fullmatch`](https://docs.python.org/3.12/library/re.html#re.fullmatch)
and [PEP 617](https://peps.python.org/pep-0617/). The adaptation stops at
finite syntax recognition; user intent outside these forms remains unsupported
or unresolved.

Evidence classification: the existing compiler/models and host scope policy
are **ESTABLISHED** in WellPlot; exact full-input grammar recognition is
**ADAPTED** from established parsing practice; using a request-bound relation
as WellPlot dependency provenance is **NOVEL** and remains subject to SOL
review. No empirical claim is made in this design.

## 4. Requirement and relation contract

For the anonymous reference request, C2 emits one complete
`CanonicalRequirementSet` with exactly four original-byte-grounded facts:

| Role | Existing canonical fields | Value/span |
| --- | --- | --- |
| Requested plotted channel | `EXPLICIT_FIELD`, `BINDING`, owner `request`, field `channel` | Exact first `GR` token. |
| Fill target | `TARGET_REFERENCE`, `FILL`, owner `GR`, field `target` | Exact second `GR` token. |
| Fill geometry | `EXPLICIT_FIELD`, `FILL`, owner `GR`, field `kind` | `baseline_split`, with the exact `split ... baseline ...` clause span. |
| Numeric baseline | `EXPLICIT_FIELD`, `FILL`, owner `GR`, field `baseline` | Parsed value `0.0`, with the exact numeric-token span. |

For the named form, the same four facts and one relation are emitted, and all
four facts use the request-derived scope declaration ID as `scope_key`.
Requirement IDs retain the existing deterministic function based on owner
kind, owner reference, field and original byte start; changing scope assignment
must not regenerate or silently alter the original IDs.

Emit exactly one existing `RequestDependency`:

```text
relation = FILL_TARGET_SATISFIED_BY
predecessor_requirement_id = plotted BINDING.channel requirement ID
dependent_requirement_id = FILL.target requirement ID
provenance[0] = exact `Then` token
provenance[1] = exact `the <MNEMONIC> curve` target phrase
```

All fact and relation provenance binds the exact UTF-8 request bytes with the
existing request SHA-256, byte offsets and span SHA-256. The dependency
validator additionally requires exact IDs, unique endpoints, same physical
mnemonic, same original scope key, exact numeric/geometry facts, and exactly
the two relation spans. The named-scope branch must independently verify its
scope declaration against extraction from the original request: declaration
ID, `EXISTING_SECTION` kind, exact selector, `REQUEST` origin, and selector
span digest. The anonymous branch retains the accepted exact
`HOST_CONTEXT` declaration with no selector or fabricated request provenance.

The relation means only that the request's fill target is explicitly linked
to the requested plotted curve. The word `Then` is retained as request
provenance; neither it nor the relation permits task scheduling, automatic
necessary-parent admission, execution ordering, or a second operation. Those
remain outside C2.

## 5. Compiler, coverage, and planner attachment boundaries

Proposed changes remain in the existing path:

1. `compile_request_contract(request)` recognizes the exact compound form
   before legacy fragment extraction can return partial facts. It extracts
   facts, scope and relation through the existing canonical models.
2. It constructs the full `CanonicalRequirementSet`, including
   `dependencies`, before calling the existing span/dependency/anchor coverage
   validators. The complete set—not a tuple with the dependency absent—must
   pass `verify_anchor_coverage(request, requirement_set, anchors=...)`. The
   independent anchor inventory must account for both clauses, baseline token
   and (for the named arm) section target. Missing or extra anchor coverage
   returns the existing `COVERAGE_FAILURE` path; no subset compilation is
   returned as usable authority.
3. `SemanticPlanner.plan()` continues to compile before provider construction
   or generation. For accepted compound syntax it gives the unchanged planner
   wire only the ordinary request/context/capabilities; the dependency model
   is never added to provider input or schema.
4. Before `_attach_compiled_requirements()` rewrites task-copy scope keys and
   requirement IDs, that boundary revalidates the original request against
   the original complete set and its independent anchors. The attachment
   helper therefore needs the original request as an argument. It preserves
   `RequestCompilationResult` unchanged on `SemanticPlan`; its assigned task
   obligations remain derived copies.
5. Existing scope binding remains authoritative. For the anonymous arm, one
   eligible section is host-selected and ambiguity fails closed. For the named
   arm, the planner's existing-section hint must match the request-derived
   selector under current exact scope normalization; the existing resolver
   then resolves it against the document and rejects absent/ambiguous targets.
   A planner hint cannot create a declaration or override a different request
   selector.

### Internal transport to later host admission

There is currently no dependency transport from the graph result to
`_private_apply.py`: `SemanticPlan` contains the original compilation and
`ScopeBindingResult`, but the facade/session result projects only obligations,
inspection context and semantic-publication contract. C2 must not pretend that
the graph's JSON round-trip is a trust boundary or that task copies preserve
the original relation.

The narrowest compatible transport proposal is to reuse the existing internal
result envelopes and existing types:

- Add optional host-only `RequestCompilationResult` and `ScopeBindingResult`
  fields to `CodeModeCompileResult` and `AgentSessionResult`, marked excluded
  from public JSON/inspection serialization like the existing inspection and
  semantic-publication fields.
- Project them from the validated `SemanticPlan`; preserve the original
  compilation object, not a reconstructed dependency from task copies.
- At the existing Notebook/MCP adapter call to `_apply_private_authoring`,
  pass the original request string already in that adapter's call frame, the
  original compilation, and the existing scope binding. Before reconciliation
  or any mutation admission, re-run the exact request hash, span/dependency,
  anchor-coverage and scope-to-bound-copy checks. Each original relation
  endpoint must map to exactly one attached obligation copy in the one bound
  task/scope; both endpoints must map to the same resolved section in the
  existing inspection context. A missing, duplicate, stale, or mismatched
  mapping rejects before reconciliation.
- The relation is carried as host-only provenance. This transport does not
  admit an operation, alter the current operation contract, authorize a
  prerequisite, or add execution order. C2 does not change
  `verify_document_postconditions()` or publication behavior.

This adds no wire-schema field, new dependency model, resolver, graph, verifier,
or trust source. Internal model serialization can be used for graph mechanics,
but receipt at an adapter must be revalidated against the immutable original
request and current host-bound scope. If SOL determines these host-only fields
constitute an unacceptable result/API contract expansion, implementation must
stop rather than move authority into provider-visible task data.

## 6. Decision matrix

| Input | Compiler result | Scope result | Mutation/admission result in C2 |
| --- | --- | --- | --- |
| Exact anonymous reference request | Four facts + one relation; `EXTRACTION_COMPLETE` | Existing anonymous HOST_CONTEXT | None; C2 is not an execution gate. |
| Exact supported named-section form | Four facts + one relation; `EXTRACTION_COMPLETE` | One REQUEST declaration with exact request provenance | None; later host resolution remains existing behavior. |
| Existing standalone `Plot physical GR.` | Existing standalone facts, empty dependencies | Existing current scope behavior | Unchanged legacy behavior. |
| Existing standalone `split the GR curve fill at baseline 0.` | Existing standalone fill facts, empty dependencies | Existing current scope behavior | Unchanged legacy behavior. |
| Different target (`GR` plotted, `CGR` fill), multiple relation candidates, or a second outcome | `COVERAGE_FAILURE` | No planner assignment can repair it | Rejected before provider output can be attached. |
| Unsupported fixed-baseline geometry or other fill form | Existing unsupported-geometry/coverage rejection | No inferred scope | Rejected; no conversion to `baseline_split`. |
| Additional delete/style/source/ordering instruction outside the grammar | `COVERAGE_FAILURE`, no partial accepted subset | N/A | Rejected before any mutation authority. |
| Forged/stale IDs, scope, relation or span in an internal set | Existing validator rejects | No scope assignment accepted | Rejected before reconciliation. |
| Legacy requirement JSON lacking `dependencies` | Current model reads default `()` | Legacy scope behavior | Preserved; no relation inferred. |

## 7. Adversarial provider-free test matrix for implementation

Tests must use the production compiler, dependency/coverage validator, planner
attachment and host-only transport check. They must not mock successful
validation or infer correctness from a typed object constructed only in the
test.

| Test | Expected result |
| --- | --- |
| Exact anonymous reference request | Four facts, one dependency, exact spans/IDs/digests, anonymous HOST_CONTEXT; complete set verifies. |
| Exact `In the Main Pass section, ...` request | Same facts/relation; one REQUEST scope derived from original bytes; selector and provenance verify. |
| Standalone physical GR and standalone supported split | Existing result remains identical; dependencies empty. |
| `GR` plotted but `CGR` filled; case-changed or otherwise different mnemonic | Coverage failure; no relation. |
| Missing plot outcome, missing fill target, missing geometry/baseline, or extra outcome | Coverage failure; never return a usable partial set. |
| Extra delete/style/source/depth/scale instruction, negation, or second compound clause | Full-input rejection before planner/provider call. |
| Swapped predecessor/dependent IDs; duplicate or unknown endpoint; changed relation kind | Dependency validation failure. |
| Altered fact value, owner, field, original ID, duplicate ID, or swapped fact span | Dependency/span validation failure. |
| Stale request digest; wrong UTF-8 byte offsets/span digest; changed `Then` or target relation span | Coverage failure, including non-ASCII prefix offsets. |
| Anonymous declaration changed to REQUEST, selector added, or HOST_CONTEXT given invented provenance | Scope validation failure. |
| Named scope forged, missing, duplicated, mismatched selector, wrong origin/kind, or span from a different request | Scope/coverage failure; planner hint cannot repair it. |
| Same named selector absent or ambiguous in document | Existing host resolver rejects; no mutation admission. |
| Original dependency valid but task copies rewrite scope key/IDs | Original set remains byte-for-byte/model-equal; unique endpoint-to-copy join succeeds only for the one exact host-assigned scope. |
| Missing, duplicate, wrong-scope or forged task copy at the adapter boundary | Host-only relation transport rejects before reconciliation. |
| Graph serialization/model validation round-trip | Full original compilation survives, then validators still run; serialization alone does not pass the trust check. |
| No publication/mutation | C2 compile/attachment/transport qualification never invokes a worker, private execution, persistence or renderer. |

No test may assert that a dependency causes the compiler, planner or host to
create a parent binding. That behavior is explicitly deferred.

## 8. Backward compatibility and exclusions

- Keep `RequestDependency` and `CanonicalRequirementSet`; do not add a second
  relation/IR type.
- Keep the empty dependency default so existing requirement sets without the
  field continue to load under the current model and preserve standalone
  behavior.
- Preserve compile-only behavior and existing Notebook/MCP public results.
  New compilation/scope transport is host-only and excluded from public dumps.
- Existing strict readers from a pre-dependency revision reject a serialized
  set that contains the additive `dependencies` key (`extra="forbid"`). C2
  makes no cross-version serialized-data compatibility promise and must not
  expose the new field as a public or persisted contract. Any future persisted,
  cross-process, or mixed-version transport requires an explicit versioned
  migration first.
- Do not change planner wire schema/prompts, validators, worker or operation
  contracts, capability authority, resolver/reconciler/executor, private apply
  semantics, persistence, shared postconditions, semantic catalog, source
  authority, or adapters' public behavior.
- Do not introduce general conjunction parsing, arbitrary action lists,
  expression evaluation, aliases, fuzzy channel selection, unit conversion,
  source substitution, task-order inference, dependency scheduling, retries,
  necessary-parent admission, worker execution, or publication.
- Do not claim the complete C1 matrix is closed. Named REQUEST support remains
  open outside this one positively qualified bounded scope form.

## 9. Decisions still open for SOL

1. **Requirement language version:** `CanonicalRequirementSet.language_version`
   currently uses `wellplot-request-v1`. Decide whether dependency-bearing
   sets are still v1 (additive representation of the same bounded language) or
   require a v2 marker. This choice must align with the no-cross-version
   serialization promise; implementation must not silently choose.
2. **Host-only result envelope:** approve or reject the proposed excluded
   compilation/scope fields on `CodeModeCompileResult` and
   `AgentSessionResult`, plus passing the original request to the existing
   `_private_apply` boundary. If rejected, identify an existing carrier that
   preserves original request bytes, dependency, and scope without provider or
   public serialization; do not add a parallel path.
3. **Named REQUEST extent:** this design positively supports the compound
   form with an already recognized explicit section selector (example: Main
   Pass). Whether arbitrary existing-section titles and other request-scope
   syntaxes enter the C1/C2 grammar is deferred and requires separate review.
4. **Dependency semantics after compilation:** whether and how a later gate
   may admit a necessary parent, map request outcomes to operations, and
   sequence dependent work is expressly undecided and excluded here. A valid
   compile result is not execution permission.

## 10. Independent-review disposition requested

SOL is asked to review the grammar's completeness and rejection boundary, the
original-set verification sequence, named-scope provenance, the host-only
transport proposal, strict-reader/version limits, and the test matrix. No
implementation should start until this design is accepted and a distinct
implementation authority is issued.

Deferred gates: C1 complete named-REQUEST matrix; C2 implementation and
provider-free qualification; any separate host admission/necessary-parent
contract; dependent-action sequencing; worker execution; publication; live
inference and benchmarks.
