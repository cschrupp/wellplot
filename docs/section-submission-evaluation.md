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

## Follow-up: Binding Identity

Run `844f01c45ecf461ca7b9867be2d4d8ae` successfully submitted both section
artifacts through the required function. Full packet acceptance still failed:
the planner assigned the same ten binding target IDs to main and repeat passes.
Workers followed those IDs, and canonical document validation rejected them.

Global binding-ID uniqueness is an existing `AuthoringDocumentSpec` and
authoring-context rule. It is a software identity convention, not a restriction
on repeating source channels. Some services already scope their lookups by
section and track; changing the canonical identity rule would require a separate
compatibility review, rather than merely removing this validation error.

The planner now advertises this scope in the target field description and
checks all planned binding targets using registry categories at its existing
semantic acceptance boundary. A collision is returned through the existing
provider correction loop before workers start. Track IDs and source channels
may still repeat. IDs are not silently rewritten.

`tests/test_graph_binding_identity.py` covers collisions between sections,
between tracks, and between curve/raster instances, plus rejected and corrected
submissions through the structured adapter in reconstruction and revision modes.
The live gate remains full CBL packet acceptance and render; this check covers
planned targets, while canonical validation remains responsible for the complete
document, including untouched bindings during revision.

## Follow-up: Track Scale Contract

Run `19ceb0498bc44ed7ab52b394f6327549` accepted all four provider submissions
on their first attempts, then failed canonical validation. Its repeat-pass
reference track explicitly supplied `x_scale`, which the generic track intent
allowed but `ReferenceTrackSpec` forbids.

The section contract now removes the inherited `x_scale` input for reference
and annotation track variants. Pydantic's class-variable override removes the
field from the generated schema and causes submitted values to be rejected
as extra inputs, including null and clear markers. Normal and array track
scales and all curve-binding scales retain their existing semantics.

`tests/test_graph_track_scale_contract.py` checks JSON Schema and Pydantic
acceptance for every track kind, new/existing tracks, and reconstruction/revision.
It also verifies a reversed curve scale inside a reference track. Replaying
the captured repeat artifact now rejects its unsupported scale at submission,
where the existing provider correction loop can report it. Full live packet
acceptance and rendering remain pending.

## Follow-up: Exact Header Slot Identity

Run `06b367606abc4f17ab002e7f5745837f` submitted valid exact detail slot IDs
together with shared labels such as Date. The resolver combined the ID with
label matches and incorrectly reported multiple matching cells. Literal IDs
now take precedence over semantic labels, keys, and configured aliases.
Non-exact requests retain the existing alias-resolution and ambiguity checks.

`tests/test_header_slot_identity.py` covers existing/scaffold headers,
configured aliases, ambiguous/missing requests, and execution that changes
only the selected date cell. Replaying the first rejected report artifact
against the CBL starter fixture now executes successfully with no errors.
This demonstrates applicability of that artifact, not completeness of its
requested report content or acceptance of the full packet. The same live run
also encountered provider overload and a missing repeat-section submission;
those outcomes are independent of this resolver correction.
