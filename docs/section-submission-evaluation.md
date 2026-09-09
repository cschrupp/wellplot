# Section Submission Evaluation

## Evidence

Live run `cc00e2839d9a4e5392f0e7d49e1ead3b` with
`qwen3.6-35b-a3b` accepted the planner (after one semantic correction) and
report artifact. Both section workers returned JSON in assistant text with
`finish_reason=stop`, without calling `submit_section_artifact`. The main
response also lacked the required `section` wrapper. These responses were
not validated artifacts. No draft changes were persisted.

This reproduces the main-section submission failure in run
`b87bbcf3fa7346adbd6d5b43fe93bd30`. It does not establish that section size
caused the failure or that the model lacks sufficient capacity.

## First Change

The section system instruction previously said "Do not emit MCP calls" while
the provider adapter required a function call. Replace that ambiguous wording
with an explicit instruction to call `submit_section_artifact` using its
advertised arguments. Distinguish artifact submission from editing tools.

The adapter already supplies a named required function choice and validates
the full artifact and planned targets. Preserve that behavior. This change
adds no controller, parsing fallback, dependency, or worker stage.

## Acceptance Gate

`tests/test_graph_section_submission.py` checks reconstruction and revision
through the real structured adapter with a fake provider. It verifies the
instruction names the enforced function and invalid unwrapped arguments are
rejected before a valid native submission is accepted. Existing graph tests
cover construction schemas, target ownership, and execution.

Live acceptance remains pending. Restart the notebook kernel and rerun the
same CBL request with the same model/server settings. Retain the JSONL trace.
Repeat once to compare with the two earlier trials. For each run record:

- Whether both sections call `submit_section_artifact` and pass validation.
- Provider rounds, section durations, and prompt/schema character counts.
- Full packet acceptance and final render outcome.

If ordinary assistant JSON persists, inspect the actual server tool-choice
handling and chat template with the same section request before attributing
the failure to task size. Track-sized artifacts are a separate proposed
change, requiring a measured comparison of submission success, total calls,
latency, and packet acceptance. Passing unit tests does not prove live
provider compliance.
