# Gate 2B-C2 — Bounded Joint Request Compilation (Revision 3)

**Status:** Design candidate for SOL independent architectural review. No C2
implementation or production activation is authorized by this document.

**Reviewed baseline:** `fdfb9ae346cebdcd3664502a679f7b195a350d3e`
<br>
**C1 accepted implementation baseline:** `fe5b750d05e07585c902e61d1f39bc0b0f6e292c`
<br>
**Revised from:** `8c87e975359bde3ba56929ae6a5cf9d8d8312cbd`

**SOL decisions incorporated:** retain `wellplot-request-v1`; approve optional
excluded host-only compilation/scope fields subject to exact custody and public
serialization parity; limit named scope to existing recognized request
syntax; defer necessary-parent admission, dependent execution, scheduling and
publication; reject unmatched members of the bounded compound family before
legacy partial extraction; retain distinct named-clause, selector and scope
anchor provenance; fail closed before planner generation, worker dispatch and
private apply until a later execution gate.
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

Accept exactly these two full-input productions, with the same single
compound outcome and no trailing instruction:

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
- The named form uses only the existing recognized request-scope syntax and
  must independently recover exactly one request-derived
  `EXISTING_SECTION` declaration. The example uses the existing `Main Pass`
  scope name; this does not introduce a grammar for arbitrary section titles.
  No created section, inferred title, or multiple scope is permitted.
- The full request must match one form from start to end. Only bounded
  whitespace variation is allowed. Additional clauses, multiple channels,
  negation, exclusions, another action, conflicting values, extra punctuation,
  a different fill target, or unsupported geometry fail closed.

### Compound-family candidate classifier

The two productions are the only newly accepted joint forms, but failure to
match them must not intercept unrelated requests. Use a bounded classifier
only after the exact fullmatch attempt fails and before legacy fragment
extraction:

1. Remove quoted literals using the existing `_QUOTED_REQUEST_LITERAL_RE` so
   quoted report text is not interpreted as an instruction.
2. Ignore at most one leading scope prefix recognized by the existing
   request-scope extractor. In the remaining text, require both (a) an
   explicit physical-plot action recognized by `_EXPLICIT_PHYSICAL_PLOT_RE`
   at a top-level start boundary and (b) a non-overlapping baseline-fill
   action recognized by `_BASELINE_FILL_REQUEST_RE`. Top-level boundaries are
   input edges or the existing delimiters (`.`, `!`, `?`, `;`, `,`, newline,
   or `and`/`then`, case-insensitive). The baseline-fill action may follow
   within the same sentence; both matches must be outside quoted literals.
   They may appear in either order.
3. If both markers exist, classify as a candidate of this compound family.
   Since fullmatch has already failed, return the existing coverage rejection
   before legacy extraction. Do not salvage the plot fact or fill fragment.
4. If either marker is absent, this classifier does not claim the request.
   Continue through the original compiler behavior, including its existing
   unsupported-request guard. The classifier must not become a general
   compound-request detector.

Examples: standalone physical GR and standalone split-fill remain on their
existing paths; an unrelated report-title request whose quoted literal
contains “split ... curve fill at baseline” remains on the original compiler
path. A reversed, mismatched-target, additional-action, or unsupported-geometry
request containing both top-level markers is a compound candidate and must be
rejected rather than partially compiled.

The regression boundary is deliberately asymmetric: the candidate classifier
is tested to claim only text containing both independently recognized,
unquoted family markers; once claimed, a failed fullmatch must reject before
legacy fact extraction. For example, `Set the report title to 'split the GR
curve fill at baseline 0'.` is not a C2 candidate because its only fill
marker is quoted, and must retain the legacy compiler result. Conversely,
`Plot physical GR. Then split the GR curve fill at baseline 0 and delete
resistivity.` is a C2 candidate and must return coverage failure with no
salvaged plot or fill requirements. These cases make non-interception and
no-partial-fallback independently observable.

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

1. Canonical compiler input is the exact string passed to
   `compile_request_contract()` after the existing `AgentSession._compile()`
   normalization `request.strip()`. Encode that string as strict UTF-8; do not
   apply Unicode normalization, case folding, newline rewriting, or another
   trim. Request SHA-256 and all byte spans refer to those bytes.
2. Attempt full-input recognition against only the two productions in
   Section 3. If neither matches, run the bounded compound-family classifier
   from Section 3 before legacy extraction. Reject a positive candidate with
   `COVERAGE_FAILURE` (or the existing unsupported-geometry diagnostic where
   applicable); do not extract either fragment. For a noncandidate, continue
   the original compiler flow and original unsupported-request guard without
   changing unrelated behavior.
3. For a recognized production, validate its captured geometry against the
   sole supported `baseline_split` form. Reject unsupported geometry before
   extracting facts. Then extract exactly the four facts and one dependency,
   and derive scope from existing request-scope extraction (named arm) or the
   exact anonymous HOST_CONTEXT rule.
4. Independently run anchor extraction over the whole canonical request. The
   expected inventory is exactly four scientific anchors: plot-channel,
   fill-target, fill-geometry and numeric-baseline. The named arm additionally
   requires both (a) one target-kind `section_scope_target` anchor extracted
   using the existing `_SECTION_TARGET_RE` and (b) one scope-kind anchor from
   existing `_SCOPE_NAME_RE` extraction. Keep three byte ranges distinct:
   (i) the complete clause anchor is `_SECTION_TARGET_RE`'s full match, from
   `In` through `section` (excluding the following comma); (ii) the captured
   selector is its `target` group, e.g. `Main Pass`; and (iii) the scope anchor
   is the independently extracted `_SCOPE_NAME_RE` match, also exactly
   `Main Pass`. Verify all three by slicing the original canonical UTF-8
   request bytes: the selector and scope-anchor slices must be byte-identical,
   and that selector slice must lie exactly within the complete clause slice.
   Re-extract clause and selector independently, compare their text and
   offsets, and verify the `ScopeDeclaration` ID, selector, kind, origin,
   request digest, selector byte span and selector span digest against those
   bytes. Do not collapse the declaration provenance to the whole clause or
   expand it to include punctuation. The narrowly identified
   `section_scope_target` anchor is checked against that scope declaration
   rather than requiring a fifth `RequestObligation`; no other target anchor
   receives this treatment. Scope anchors are not scientific requirement
   facts.
5. Construct the complete `CanonicalRequirementSet` with the existing
   `wellplot-request-v1` marker, `dependencies`, and original scope keys on all
   four facts. Verify request digest, fact IDs/spans, dependency endpoint
   identities and exact relation spans, then exact anchor inventory and
   coverage. `verify_anchor_coverage()` receives the complete set, never only
   its facts tuple. It compares freshly extracted anchors with the expected
   field/span inventory: four fact anchors plus, for the named arm, the
   section-target and scope anchors both tied to the independently extracted
   declaration. Empty, fabricated, altered, duplicated or selectively omitted
   anchors cannot establish coverage. Any failure returns the existing
   `COVERAGE_FAILURE` path; a partial set is never usable authority.
6. `SemanticPlanner.plan()` compiles the authoritative request before context
   construction or provider generation. Under R8, validated dependency-bearing
   C2 requests and recognized C2 requests with missing or stripped dependency
   custody fail with `dependency_execution_not_authorized`. Canonical wire
   conversion, attachment and host custody are qualified separately with
   provider-free synthetic fixtures exercising existing production functions.
   No production C2 success path is authorized. Legacy dependency-free requests
   continue through the unchanged planner wire.

   Binding SOL clarification of baseline
   `d6401a5dede0bf1035087a25fb2c371d5fa38bae`: R8 supersedes the prior
   statement that accepted compound syntax gives the planner wire ordinary
   request/context/capabilities. `AUTHORITY_CHECK: PASS`;
   `DRIFT_CHECK: PASS` (R8 clarification only).
7. Before `_attach_compiled_requirements()` rewrites task-copy scope keys and
   requirement IDs, that boundary revalidates the original normalized request
   against the original complete set and freshly recovered anchors. The
   helper therefore receives the canonical request as an argument. It
   preserves `RequestCompilationResult` unchanged on `SemanticPlan`; assigned
   task obligations are derived copies. At this attachment boundary, verify
   every generated `requirement_refs` entry against the exact derived copy
   ID, with one reference per original fact and no extras.
8. Existing scope binding remains authoritative. For the anonymous arm, one
   eligible section is host-selected and ambiguity fails closed. For the named
   joint arm only, `_attach_compiled_requirements()` must reject unless there
   is exactly one section task whose nonempty `existing_section_hint` matches
   the independently recovered request selector under existing exact scope
   normalization. This check must run before `_resolve_section_scope_ids()`:
   its existing one-scope/one-task fallback can otherwise assign the only
   request scope when the model omits the hint. Do not change that fallback
   for legacy requests outside these two dependency-bearing productions. The
   matched request selector is still only a symbolic scope; the attached task
   scope ID is a separate host assignment; the actual canonical section ID is
   established by the existing resolver/enrichment against the current
   document. A hint alone never establishes that canonical identity.

### Production non-execution boundary

#### Planner inference gate

The dependency-bearing request must not reach model generation in C2. In the
existing `SemanticPlanner.plan()` flow, place the fail-closed check immediately
after `compile_request_contract(request)` has returned a fully validated
original `RequestCompilationResult` and after its existing non-success status
handling, but before planner context construction and before the nested
`generate()` function can call `backend.generate_structured()`. If the
validated original set has any dependency, raise the existing
`PlannerSemanticFailure` with code
`dependency_execution_not_authorized`. This uses the established typed
failure path; it does not change the provider request, schema, prompt, retry
policy, or backend.

An empty dependency tuple alone is not enough to establish that a recognized
C2 request is dependency-free. Reuse one bounded C2-family membership helper
shared with `compile_request_contract()`: it recognizes the two exact
productions and delegates failed fullmatches to the existing post-fullmatch
candidate classifier. This helper only answers family membership; it does not
extract requirements, validate dependencies, or compile a second plan. If the
original request is recognized as a C2 family member but the returned
compilation is missing, has stripped, or otherwise lacks its required
dependency custody, raise the same typed failure before generation. The
compiler's full-input match, candidate classification, complete-set
verification, and dependency validation remain the single recognition and
validation authority; the membership guard only prevents missing custody from
becoming permission to plan. Unrelated noncandidate requests with the
existing empty dependency tuple preserve their current planner behavior.

Provider-free qualification uses synthetic fixtures and the existing
production functions. Exercise `compile_request_contract()` and its complete
validators, then exercise canonical-plan conversion, planner attachment, and
host-only envelope/custody verification with those verified fixtures. At the
`SemanticPlanner.plan()` boundary, use a provider test double solely to count
calls: a valid dependency-bearing set and a recognized compound request with
dependency custody removed both must raise the typed failure with zero calls
to `generate_structured()`. A legacy dependency-free request must retain the
existing behavior, demonstrated with the same bounded fake backend and its
expected call count. The direct conversion/attachment/envelope tests qualify
those existing components without turning them into an alternate production
success route; production `plan()` has no C2 success path in this gate.

Across the existing graph and adapter boundaries, assert the dependency
failure yields zero worker dispatch/compilation, zero intent merge, zero
private mutation, zero persistence, and zero publication/render. No live
provider, worker, document mutation, or publication is used by these tests.

Evidence classification: failing before a provider call when validated
host-owned requirements are not authorized is **ADAPTED** from the existing
typed request-compilation failure boundary. Reusing the bounded C2-family
membership helper to reject missing dependency custody is **NOVEL** in
WellPlot. Merely checking for a present dependency would leave stripped
custody fail-open; treating every empty-dependency request as C2 would break
legacy behavior. The shared bounded helper is the narrower alternative. Its
risks are false family classification and accidental legacy interception;
the positive non-interception and missing-custody tests above bound these.
The guard is reversible only by a later explicit gate, and should be revisited
if exact family membership cannot be determined from the original request
without duplicating or broadening the compiler grammar.

The reviewed graph route is `SemanticPlanner.plan()` in `plan_node` → safety
nodes → enrichment and semantic-publication preparation → `dispatch_workers()`
→ `compile_worker_node()` → `merge_node()` → facade result projection. Notebook
and MCP adapters invoke `_apply_private_authoring()` only for a successful
session result; private reconciliation/execution and postconditions precede
adapter persistence. Therefore C2 dependency metadata must not be allowed to
flow through this route as executable work.

Until a later separately authorized gate enables dependency-aware execution,
the existing `plan_node` boundary must fail closed immediately after
`SemanticPlanner.plan()` returns a fully validated/attached plan and before
returning graph state. If its original `RequestCompilationResult` contains a
nonempty dependency tuple, return/raise the existing typed planner failure
with a stable `dependency_execution_not_authorized` code. The failure must
propagate out of the graph; it must not create worker `Send`s, call
`dispatch_workers`, merge intent, project a successful facade/session result,
or reach either adapter's private apply. This adds a condition to an existing
node, not a node, edge, graph, worker contract or alternate route. Empty or
legacy dependency sets continue normally.

For defense at the shared mutation boundary, `_apply_private_authoring()` must
also reject a received host-only compilation with dependencies before
constructing/reconciling the private authoring plan. This does not replace the
pre-dispatch guard: it prevents any future internal bypass from mutating or
publishing a dependency-bearing result. Both checks remain unconditionally
closed in C2. Removing either requires a later explicit authorization; no
configuration flag, planner output, or model-provided value may open them.

Provider-free qualification stops before any production worker runs. It uses
the real compiler, full dependency validator, planner conversion/attachment,
and existing graph pre-dispatch boundary with a synthetic planner response
fixture. Spies assert zero worker dispatch/compilation, zero merge, zero
`_apply_private_authoring`, and zero persistence/render calls. Separate pure
host-envelope tests validate exact custody and serialization parity without
calling worker compilers or private execution. No test-only success path or
second graph is introduced. The existing graph, workers, shared verifier and
publication implementation remain unchanged apart from the fail-closed
conditions above.

### Narrow dependency-validator change

Section 8's prior blanket prohibition on validator changes was too broad and
conflicted with this contract. The one authorized validator change is a narrow
extension of the existing `_verify_request_dependencies()` in
`obligations.py`; do not add a parallel validator. It continues to validate
the anonymous HOST_CONTEXT arm exactly as accepted by C1 and adds only the
named REQUEST arm for the existing recognized scope syntax. For that arm it
independently re-extracts and compares the one declaration's ID, selector,
`REQUEST` origin, `EXISTING_SECTION` kind, exact UTF-8 selector span, span
SHA-256 and original request SHA-256. The validator accepts exactly the two
complete productions in Section 3 and rejects every other dependency-bearing
request, extra dependency, scope, fact, or relation span. Typed Pydantic
validators and all unrelated validation rules remain unchanged.

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
  fields to `CodeModeCompileResult` and `AgentSessionResult`, excluded from
  public JSON and inspection serialization like the existing inspection and
  semantic-publication fields. Acceptance is conditional on regression tests
  proving the existing public `model_dump(mode="json")` and inspection output
  remain value-identical to their pre-C2 contract, with no new exposed fields.
- Project them from the validated `SemanticPlan`; preserve the original
  compilation object, not a reconstructed dependency from task copies.
- At the existing Notebook/MCP adapter call to `_apply_private_authoring`,
  pass the exact canonical compiler input (`request.strip()` as used by
  `AgentSession._compile()`), original compilation and existing scope binding.
  This means trim only the leading/trailing characters removed by Python
  `str.strip()` at the session boundary, then hash the strict UTF-8 encoding;
  do not Unicode-normalize, case-fold, or rewrite interior bytes. At receipt,
  independently check the exact request SHA, complete four-fact
  set, dependency, scope declaration and freshly extracted anchors against
  that request before reconciliation or mutation admission. Do not trust the
  compilation's own stored anchors as the expected anchors.
- Resolve dependency endpoint IDs only by exact lookup in the independently
  verified original requirement set; require each ID to identify one unique
  fact. Verify that `ScopeBindingResult` has exactly one expected, assigned
  and task scope ID, all equal to the host-derived `_scope_id()` for the
  recovered declaration; require exactly one attached section task with that
  symbolic scope ID. For each exact original fact derive only the existing
  host attachment transform:
  `scope_key = assigned_scope_id` and
  `requirement_id = original_id + "." + _scope_key(assigned_scope_id)`.
  Compare the complete expected `RequestObligation` (all unchanged fields,
  provenance and value/state plus those two exact changes) with exactly one
  item in the returned bound obligations. `requirement_refs` are checked at
  planner attachment against that complete derived ID, where the task is
  available; do not claim they are transported in the session result.
  Require exactly one copy of each of the four original facts in the one
  matching scope, with no duplicate or wrong-scope copy. A conditionally
  omitted fact is missing from the returned obligations and must be rejected
  just like any other omission. Reject missing, altered, duplicated, or
  wrong-scope copies. Require `inspection_context.sections` to contain exactly
  one entry with `task_index == 0`; its section ID must identify exactly one
  section in the current canonical document and match the existing resolved
  snapshot. Both original dependency endpoints map through that same task and
  section. Do not
  join by mnemonic, owner text, ID suffix alone, or a relationship
  reconstructed from attached copies.
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

| Input | Compiler result | Scope result | Execution/publication result in C2 |
| --- | --- | --- | --- |
| Exact anonymous reference request | Four facts + one relation; `EXTRACTION_COMPLETE` | Existing anonymous HOST_CONTEXT; four scientific anchors | Production graph fails closed before graph state reaches safety/enrichment/dispatch; no worker or publication. |
| Exact supported named-section form with matching planner hint | Four facts + one relation; `EXTRACTION_COMPLETE` | One REQUEST declaration; four scientific anchors plus clause, selector and scope-anchor ranges | Same pre-dispatch rejection; symbolic selector, attached task scope and canonical section ID remain distinct. |
| Exact supported named-section form with missing/mismatched hint | Compilation may be valid; named-arm attachment rejects before `_resolve_section_scope_ids()` can use its one-scope fallback | No attached scope | Rejected before enrichment/reconciliation; legacy fallback remains unchanged outside the new form. |
| Failed grammar match with both physical-plot and baseline-fill family markers | Existing `COVERAGE_FAILURE`; no legacy partial extraction | No attached scope | Rejected before workers, intent merge, private apply or persistence. |
| Failed grammar match without both compound-family markers | Original compiler/unsupported-guard behavior | Existing legacy result | Unrelated requests are not intercepted by C2. |
| Quoted report-title text contains the fill wording, but no unquoted fill action | Original compiler result | Existing scope policy | Positive non-interception case; quoted data is not classified as C2 syntax. |
| Both unquoted family markers plus an extra delete instruction | `COVERAGE_FAILURE`, with no partial facts | No attached scope | Negative candidate case; legacy extraction cannot salvage the two familiar fragments. |
| Exact/dependency-free standalone or legacy request | Existing result | Existing scope policy | Existing graph/worker/adapter behavior unchanged. |
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
| Exact `In the Main Pass section, ...` request | Same facts/relation; one REQUEST scope independently derived from canonical normalized bytes; exact declaration identity, selector, origin, kind, span and request/span digests verify. |
| Named clause/selector/scope anchor provenance | Independently slice the complete section-target clause, captured selector group, and scope extractor's anchor from the exact canonical UTF-8 request bytes. Verify each anchor's own start/end and bytes; verify selector is contained in clause and selector bytes equal scope-anchor/declaration-selector bytes. The clause range/digest must never substitute for the selector's provenance range/digest. |
| Standalone physical GR and standalone supported split | Existing result remains identical; dependencies empty. |
| `GR` plotted but `CGR` filled; case-changed or otherwise different mnemonic | Coverage failure; no relation. |
| Missing plot outcome, missing fill target, missing geometry/baseline, or extra outcome | Coverage failure; never return a usable partial set. |
| Extra delete/style/source/depth/scale instruction, negation, or second compound clause within the candidate family | Candidate classifier catches both family markers; full-input rejection before legacy extraction. |
| Unrelated request lacking either family marker | Candidate classifier does not intercept; existing compiler path and result remain unchanged. |
| Quoted fill phrase inside a report-title literal | Positive R5 non-interception regression; classifier removes the quoted literal and original compiler behavior is preserved. |
| Both unquoted family markers with an extra delete/style action | Negative R5 interception regression; candidate is rejected before legacy extraction and no familiar fragment survives as an obligation. |
| Swapped predecessor/dependent IDs; duplicate or unknown endpoint; changed relation kind | Dependency validation failure. |
| Altered fact value, owner, field, original ID, duplicate ID, or swapped fact span | Dependency/span validation failure. |
| Stale request digest; wrong UTF-8 byte offsets/span digest; changed `Then` or target relation span | Coverage failure, including non-ASCII prefix offsets. |
| Anonymous declaration changed to REQUEST, selector added, or HOST_CONTEXT given invented provenance | Scope validation failure. |
| Named scope forged, missing, duplicated, mismatched selector, wrong origin/kind, or span from a different request | Scope/coverage failure; planner hint cannot repair it. |
| Same named selector absent or ambiguous in document | Existing host resolver rejects; no mutation admission. |
| Original dependency valid but task copies rewrite scope key/IDs | Exact lookup by original endpoint IDs, exact `model_copy` derivation of the two permitted attachment fields from the verified task scope, complete object equality, and unique `requirement_refs` check at attachment succeed; no suffix-only or mnemonic join. |
| Missing, duplicate, altered, conditionally omitted or wrong-scope fact copy at the adapter boundary | Host-only transport rejects before reconciliation, including when the original relation remains intact. |
| Empty, fabricated, altered or selectively omitted compilation anchors | Fresh extraction requires all four fact anchors and, for named scope, both the section-target and scope anchors matching the recovered declaration; stored anchors alone cannot establish coverage. |
| Named section-target clause anchor, captured selector, or independent scope anchor independently missing, duplicated, or span-mismatched | Complete-set validation rejects; each range is checked against original UTF-8 bytes; neither anchor substitutes for another and none becomes a fifth scientific fact. |
| Clause, selector, or scope-anchor offsets shifted by punctuation, multibyte text, or whitespace | Independently sliced original-byte ranges disagree, or selector is not contained in the clause; scope/dependency validation rejects. |
| Named scope hint omitted, mismatched, duplicated, or replaced by a planner-selected selector | Named-form host attachment check rejects before the generic one-scope fallback; unrelated legacy attachment behavior remains unchanged. |
| Session input has outer whitespace, changed interior bytes, or mismatched request digest | `request.strip()` defines canonical compiler bytes; receiver recomputes the exact UTF-8 digest and rejects any mismatch. |
| Host-only result fields accidentally enter public JSON/inspection | Serialization-parity regression fails; the optional excluded fields are not accepted until parity is demonstrated. |
| Dependency-bearing plan reaches the existing `plan_node` return boundary | Stable `dependency_execution_not_authorized` failure before graph state is returned; worker dispatch and merge spies remain at zero. |
| Validated dependency-bearing C2 request reaches `SemanticPlanner.plan()` | After full original-set validation but before context/generation, raises `PlannerSemanticFailure` with `dependency_execution_not_authorized`; `generate_structured()` call count is zero. |
| Recognized C2-family request has missing or stripped dependency custody | Reused bounded family recognition detects the family despite the empty/altered dependency tuple; same typed failure occurs before provider generation, with zero worker calls, mutations, or publications downstream. |
| Legacy request is dependency-free and not a C2-family member | Existing `SemanticPlanner.plan()` behavior is preserved; a bounded fake backend observes the normal existing generation call count. |
| Canonical graph receives a dependency-bearing synthetic planner result | Exercise the existing graph/`plan_node` boundary; assert the typed fail-closed terminal and zero calls to worker dispatch/compilation, intent merge, adapter private apply, persistence, and render. No worker node executes. |
| Dependency-bearing `AgentSessionResult` is injected at the shared private-apply boundary | Entry guard rejects before `AuthoringService`, reconciliation, executor, verifier, persistence or rendering. |
| Adapter receives the planner failure | Notebook/MCP do not call `_apply_private_authoring`; persistence and render spies remain at zero. |
| Legacy empty-dependency plan | Fail-closed dependency guard does not trigger; normal accepted path remains unchanged. |
| Graph serialization/model validation round-trip | Full original compilation survives, then request/fact/relation/scope/anchor and copy-derivation checks run; serialization alone does not pass the trust check. |
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
- Do not change planner wire schema/prompts, typed Pydantic validators, worker
  or operation contracts, capability authority, resolver/reconciler/executor,
  private-apply execution semantics, persistence, shared postconditions,
  semantic catalog, source authority, or adapters' public behavior. The sole
  permitted validator extension is the two-production
  `_verify_request_dependencies()` change specified in Section 5.
- Do not introduce general conjunction parsing, arbitrary action lists,
  expression evaluation, aliases, fuzzy channel selection, unit conversion,
  source substitution, task-order inference, dependency scheduling, retries,
  necessary-parent admission, worker execution, or publication.
- Do not claim the complete C1 matrix is closed. Named REQUEST support remains
  open outside this one positively qualified bounded scope form.

## 9. Decisions still deferred

Whether and how a later gate may admit a necessary parent, map request
outcomes to operations, or sequence dependent work is expressly undecided and
excluded here. A valid compile result is not execution permission. General
section-title grammar and the complete C1 named-REQUEST matrix also remain
deferred; this design uses only existing recognized request-scope syntax and
does not claim C1 closure.

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
