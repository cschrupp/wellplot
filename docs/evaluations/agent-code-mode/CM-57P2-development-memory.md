# CM-57P2 Development Memory

## Authority And Boundary

CM-57P2 is the planner-only pre-live evaluation harness authorized against
baseline `474f6b014457e06e561db6e72ba3d6faa0605b8e`. It reuses the closed
CM-57C corpus and the accepted CM-57P1 production planner contract. This slice
adds no provider calls, production changes, routing changes, enrichment,
typed-worker execution, compilation, persistence, or live evidence.

The implementation is limited to:

```text
scripts/cm57p2_planner_shadow.py
tests/test_cm57p2_planner_shadow.py
docs/evaluations/agent-code-mode/CM-57P2-development-memory.md
```

The default command performs deterministic pre-live checks only. A future live
run requires an explicit `--live-authorized` flag, a full lowercase checkout
SHA, an explicit base URL, and the configured key source. The future runner
also rejects a non-empty evidence file before provider construction.

## Evaluation Boundary

Each future row calls the actual production `SemanticPlanner.plan()` once for
one corpus case and stops at the planner result or typed planner failure. The
harness does not call `SemanticEnricher`, `TypedSectionCompiler`,
`ProgramSectionCompiler`, or any downstream graph node. The provider wrapper
records only call kind, bounded outcome/category, provider-neutral metrics, and
bounded plan shape projections. It never retains request prose, raw provider
responses, reasoning, paths, or full semantic task text.

The production source-summary helper is reused unchanged:
`production_source_summary(case)` from `scripts/cm56_post_r4_typed_shadow.py`.
Its canonical 16-case matrix is path-free and candidate-ID-free.

The future population is exactly:

```text
16 frozen CM-57C cases
2 independent attempts per case
32 planner rows
```

The response pipeline remains the accepted P1 pipeline:

```text
provider structured response
    -> production SemanticPlan validation
    -> at most one INVALID_RESPONSE retry or semantic correction
    -> bounded planner result/failure evidence
```

No host repair, capability injection, deduplication, source resolution, or
worker fallback is performed by this harness.

## Frozen Controls And Guards

```text
corpus version:              cm57c.shadow.v1
corpus SHA-256:              3acac04abbe8d20902bc1785d71cf3b8b0a9d7caf623ea79ed2eca8617842181
historical summary SHA-256:  97636abb8826d5039e2dd3878ce828126e9f6f6dbcb077d82aa9d45e673cdedf
historical raw evidence SHA: 57df9720bc2eb7b05fcb815de84062815382b13c84f5878da8c948e08e41cba8
source-summary matrix SHA:   7be957d4bd3361457206bbce689c612727cec5c4a3d4cbf392c4dcca52203d8b
planner prompt SHA-256:      5e7a0732af01e4b1f16b3ccf019c005ea2e9ba5c0e93e94870a56a261e2bca18
planner source SHA-256:      0189b290ef4f76bdd776fe2612c454809ff77725379def7d8c5a98d9ae165413
catalog projection SHA-256:  b1b9c85db961cb8b97f1c8b6f914a6a75f5bf57cf49ca4413c64d35311b80d37
```

Future provider controls are frozen to:

```text
model:                qwen3.6-35b-a3b
planner temperature:  0.0
max output tokens:    16384
token parameter:      max_tokens
timeout:              900 seconds
attempts:             2
output:               /tmp/cm57p2-planner-qwen.jsonl
```

The future live guard covers the P2 harness, the P1 planner and capability
authority, the CM-57C corpus and historical summary, the production source
summary helpers, and the source fixture directory. It rejects checkout or
artifact drift before provider construction.

## Bounded Evidence

The serialized plan projection contains only:

```text
report-task presence and report capability IDs
section count
section capability IDs in provider order
source-hint counts
unresolved-requirement count
```

Final comparison is driven solely by the corpus's unique
`expected_capabilities` set. It records actual order, unique IDs, missing IDs,
unexpected IDs, duplicate IDs, exact unique-match status, parent-closure
status, report-task presence, section count, and unresolved count. No expected
generated artifact or hidden canonical semantic result is used.

Initial classifications preserve the first valid planner object when a later
bounded correction succeeds:

```text
INITIAL_CONTRACT_OK
INITIAL_CAPABILITY_CLOSURE_OMISSION
INITIAL_CAPABILITY_DUPLICATION
INITIAL_WRONG_CAPABILITY_SELECTION
INITIAL_PARENT_CLOSURE_FAILURE
INITIAL_WORK_UNIT_MISMATCH
INITIAL_UNEXPECTED_REPORT_TASK
INITIAL_UNRESOLVED_REQUIREMENTS
INITIAL_MULTIPLE_CONTRACT_GAPS
```

Final classifications use the production planner's terminal result and the
frozen precedence:

```text
PLANNER_CONTRACT_OK
CAPABILITY_CLOSURE_OMISSION
CAPABILITY_DUPLICATION
WRONG_CAPABILITY_SELECTION
WORK_UNIT_COUNT_MISMATCH
UNEXPECTED_REPORT_TASK
UNRESOLVED_REQUIREMENTS
REPORT_AND_UNRESOLVED
PLANNER_SEMANTIC_FAILURE
PLANNER_SCHEMA_FAILURE
PROVIDER_INFRA_FAILURE
```

Provider `invalid_response` and `validation` categories are schema failures.
Timeout, transport, rate-limit, authentication, configuration, and provider
rejection categories are infrastructure failures. Unexpected programming
exceptions remain exceptions rather than becoming experiment outcomes.

The future population decision rules are:

```text
invalid population or provider infrastructure failure
    -> INCONCLUSIVE_PLANNER_EVALUATION
historical success regression or new wrong selection
    -> PLANNER_CONTRACT_REGRESSION
all 32 final planner contracts valid
    -> PLANNER_CONTRACT_VALIDATED
more than 11 and fewer than 32 valid contracts
    -> PLANNER_CONTRACT_IMPROVED_BUT_INCOMPLETE
11 or fewer valid contracts
    -> PLANNER_CONTRACT_NOT_IMPROVED
```

Historical CM-57C success/failure transitions and two-attempt final contract
repeatability are retained as separate bounded aggregate evidence.

## Deterministic Validation

Pre-live validation completed without provider calls:

```text
focused CM-57P2 tests: 15 passed
pre-live CLI:           PRELIVE_READY
provider calls:         0
production changes:     0
live inference:         NOT STARTED
```

The harness has not modified CM-57C, CM-57P1, the corpus, historical summary,
or any file under `src/wellplot`. CM-57D remains blocked. Stop here for
independent review and separate live authorization.
