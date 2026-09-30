# CM-59A-E2 - Remediated System Reevaluation

## Status

- Parent baseline: `e1791dce60f789673a1a301c948d079a90af4915`
- Provider calls during implementation and verification: `0`
- Endpoint calls during implementation and verification: `0`
- Production changes: `0`
- Live inference: not run; requires separate authorization and reviewed checkpoint
- CM-57D: blocked

CM-59A-E2 is the fresh evaluation harness for the complete remediated planner
and deterministic CM-58 safety stack. It reuses the unchanged CM-59A corpus and
historical evaluation primitives without modifying the historical CM-59A
harness, corpus, raw evidence, summary, or endpoint fingerprints.

## Frozen Evaluation

The population is 24 cases, two attempts per case, six families, and four cases
per family. The original CM-59A acceptance contract remains unchanged: 22/24
stable passes, 3/4 per family, both Lichen and Mariner residual cases passing,
zero planner terminal failures, wrong final-plan escapes, safety regressions,
unstable cases, unexpected references, missing required references,
parent-closure violations, and duplicate capability types.

The E2 evaluation contract is:

`cm59a.e2.system-reevaluation.v1`

The provider-call budget is bounded to 48 planner executions and at most two
provider calls per execution, for 48-96 provider calls. The only permitted
planner call kinds are `INITIAL`, `INVALID_RESPONSE_RETRY`,
`SCHEMA_CORRECTION`, and `SEMANTIC_CORRECTION`. Call traces are valid only for
the one-call initial path or one of the corresponding bounded two-call paths.

The E2 harness records only bounded structured-response diagnostics. A
`StructuredResponseProviderError` contributes its enum `response_reason`; an
ordinary `ProviderRequestError` contributes no response reason. Raw provider
responses, safe messages, and response text are never retained.

The protected production artifact set is explicit and includes:

- `src/wellplot/agent/code_mode/planner.py`
- `src/wellplot/agent/code_mode/capability_safety.py`
- `src/wellplot/agent/code_mode/report_boundary_safety.py`
- `src/wellplot/agent/code_mode/section_leaf_safety.py`
- `src/wellplot/agent/code_mode/workflow.py`
- `src/wellplot/capabilities/builtins.py`
- `src/wellplot/agent/providers/base.py`
- `src/wellplot/agent/providers/openai_compat_v2.py`
- `src/wellplot/agent/providers/response_diagnostics.py`
- `scripts/cm57p9_runtime_fingerprint.py`

The harness binds its provenance to the parent checkpoint and requires current
production bytes to match that checkpoint before a future live run or
finalization. It also requires the normalized endpoint identity:

`23afb5ebf67063154bcf02ada6d25b2c929250b14c6a4cad06e8649d087bc980`

## Remediation Targets

The three previously identified residuals are hard gates in addition to the
general acceptance threshold. Each must be `STABLE_PASS` across both attempts;
a stable safe rejection cannot consume the general two-case allowance.

- Fig: `cm59-single-fig-05`, report intent `SECTION_ONLY`
- Linden: `cm59-reference-linden-10`, report intent `SECTION_ONLY`
- Xenon: `cm59-mixed-xenon-21`, report intent `MIXED`

The target gold remains sourced from the unchanged corpus. No new corpus label,
request, semantic expectation, or provider-specific exception was introduced.

## Live Boundary

The E2 harness has a guarded live path, but this implementation/verification
slice did not execute it. Before any endpoint or provider access, the live path
rejects non-empty evidence/fingerprint/summary artifacts, verifies the exact
authorized checkout and frozen contract, and captures a PRE endpoint
fingerprint. The PRE fingerprint must already match the expected normalized
identity before provider construction. It then runs all 48 planner executions
sequentially, flushes each JSONL row, captures POST immediately, and stops.

Finalization is provider-free and records exact SHA-256 values for the raw
evidence, PRE fingerprint file, and POST fingerprint file. No append, resume,
smoke request, selective rerun, worker/program call, prompt change, schema
change, or production routing change is implemented or authorized here.

## Verification

- E2 focused suite: `58 passed`
- Adjacent planner/provider/safety suites: `243 passed`
- Full repository suite: `2274 passed, 13 accepted pre-existing failures, 3 skipped`
- Ruff lint: passed
- Ruff formatting: passed
- Python compilation: passed
- `git diff --check`: passed
- Provider-free pre-live CLI: `PRELIVE_READY`
- Provider, endpoint, worker, and program calls: `0`

The full-suite failures are the established unrelated baseline categories:
MCP helper signature drift, the tool-budget threshold, missing historical R6
evidence, the stale P7 artifact expectation, and unrelated graph-worker test
fixtures/contracts. No E2 test failed and no new E2-attributable failure was
observed.

## Hard Stop

This slice stops at the provider-free implementation checkpoint. Do not run the
E2 live population, Xenon-only retest, production adoption, CM-58.4, P11, or
CM-57D without separate authorization and independent review.
