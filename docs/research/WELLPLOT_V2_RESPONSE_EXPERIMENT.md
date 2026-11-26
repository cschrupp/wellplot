# Isolated response-role experiment preparation

Six fresh synthetic cases. Each saved snapshot is the canonical document
state relevant to the question; private output is explicitly not that state.
No numeric samples, provider tools, actions, execution or publication are
needed. At input assembly, use canonical document and inspection projections
and the existing `AuthoringResult` fields for outcome, coverage and
clarification records. Do not send the grading column.

| Case | Original objective and final question | Verified record and context | Required answer |
| --- | --- | --- | --- |
| CR01 | Retitle the report Mesa Review. "Was it saved?" | Published title Mesa Review, previous title Mesa Draft; title verified after reload. | Confirm the title was saved and verified; claim no other edit. |
| CR02 | Change subtitle to Shift 4. "What title and subtitle are saved now?" | Saved title Ridge Report and subtitle Shift 3; private candidate Shift 4 was verified but not published. | Name saved title and subtitle; distinguish unpublished candidate from saved state. |
| CR03 | Save title Core Check and plot physical CALX from Ridge. "Which parts did you finish?" | Title Core Check verified and saved; complete Ridge inventory lacks CALX; no binding added. | Distinguish saved title from blocked curve; state exact reason without substituting. |
| CR04 | Plot physical POR in the Review section. "What do you still need?" | Eligible North and South both contain exact POR; neither selected; verified pending clarification; no edit saved. | Ask which source to use, presenting both; do not choose or claim completion. |
| CR05 | Check whether literal VELX is available in East and West. "Can you confirm it in either?" | East inspected completely: contains VEL but not VELX. West inspection failed; inventory unknown. | Distinguish confirmed East absence from unknown West; do not substitute VEL. |
| CR06 | "What depth units does this report display?" | Published report displays depth in ft; inspected source depth is m; no edit requested or made. | Answer ft, distinguish source units if useful, no conversion or edit claim. |

## Response instructions

The response role communicates authoritative state. Answer the current user
question using the saved document, inspected facts and verified outcome
records. Preserve the distinction between proposed, attempted, privately
verified, saved, blocked and pending work. Never describe a private result
as saved. Do not infer missing scientific facts from an inspection error.
If a consequential choice is pending, ask only the question supported by
the verified record; never resolve it yourself. Do not propose mutations,
tool calls, replacements or execution. Return one object with a non-empty
`response` string and no other properties.

Independent demonstrations:

- A verified candidate renamed Blue Ridge to Quartz, but publication did
  not run: "Quartz was verified in a draft but was not saved. The saved
  title is still Blue Ridge."
- An inspected complete inventory does not list literal RATE7; a second
  source could not be inspected: "RATE7 is absent from the inspected first
  source. I couldn't confirm whether it is present in the second."

## Qualification and decision

Proposed threshold: all six truthful on saved, unsaved or pending status,
zero fabricated facts or execution claims, and at least five complete,
useful replies. Score independently; typed validity alone does not count.
One first response per case, six logical/physical attempts maximum, no
retries or corrections, existing qualified thinking-disabled runtime.

This is a preparation record, not an executable population or authority.
Before execution review, bind exact canonical serialized inputs, dialogue,
manual and DTO; use the existing D4/D5 observation path with truthful
response-role attribution, no planner or authoring calls, and mock HTTP
custody verification. Do not relabel the response as a planner or worker
observation merely to fit the current role allowlist.
