# CM-59A-R1 — Report-Boundary Residual Remediation

## Status

- Slice: `CM-59A-R1`
- Baseline: `c7ee15a1a19b400fa4462ca387af5940d016fe2a`
- Origin: `CM-59A SYSTEM_REEVALUATION_REJECTED`
- Result SHA: recorded after the bounded implementation commit
- Provider calls: `0`
- Endpoint calls: `0`
- Worker/program calls: `0`

## Scope

This slice revises only the existing report-boundary safety mechanism:

```text
cm58.report-boundary.v1
    -> cm58.report-boundary.v2
```

The demonstrated Fig safe rejection and Linden wrong escape are addressed by
recognizing only these additional high-confidence section phrases:

- `scalar display`
- `scalar displays`
- `shared display`
- `shared displays`

Bare `display`, `response`, `trace`, and `measurement` signals are not
authorized. Existing report, section, mixed, and unspecified classification
semantics remain unchanged. Repair still uses only the existing
`REMOVE_REPORT_TASK` and `ADD_REPORT_STANDARD` actions, with normal semantic
revalidation.

## Residual Boundaries

- Fig stable safe rejection: addressed
- Linden stable wrong escape: addressed
- Xenon structured-output failure: not addressed
- Lichen remediation: not authorized; historical class passed 2/2
- Mariner remediation: not authorized; historical class passed 2/2

CM-58.1, CM-58.3, graph topology, planner, prompts, schemas, capabilities,
workers, providers, retries, and routing are unchanged. Production code is
limited to `src/wellplot/agent/code_mode/report_boundary_safety.py`.

## Historical Evidence Handling

CM-59A remains permanently identified as an evaluation of
`cm58.report-boundary.v1`. Its corpus, summary, and production-source hashes
are not rewritten. The CM-59A provider-free pre-live test is adapted only to
isolate its provider/endpoint-free property after the current production
policy moved to v2; historical hashes remain untouched.

## Hard Stop

This is a provider-free implementation checkpoint. No Qwen invocation or
endpoint request is authorized. CM-59A-R2A, CM-59A-R2B, CM-59A-E2, and CM-57D
remain blocked pending independent review.
