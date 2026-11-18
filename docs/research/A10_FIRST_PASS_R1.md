# A10 first-pass contract: R1 candidate

**Status:** Provider-free candidate. No live observations.
**DRIFT_CHECK: PASS.** Keeps the existing planner, provider, campaign runner,
validation, custody, and host authority. No alternate workflow or scorer.

## Change and rationale

The completed A10 audit found zero first-pass typed successes. Missing CREATE
or ENSURE `semantic_ref` was the only substantive recorded validation error
in 40 of 52 returned initial attempts. R1 adds the existing operation, value
state, reference, condition, and intent-preservation rules to the initial
request, with two synthetic operation examples. It does not change the system
prompt, wire schema, validators, or correction policy. The existing generic
retry still repeats its initial request; specialized correction text is unchanged.

The existing A10 campaign authority can opt in with
`planner_first_pass_max_output_tokens: 4096`. This pins the exposed panel
`A01, B01, C01, D01, D05, E01, F04, G01, G02, H01` in frozen order and
allows one logical and one physical attempt per case, at most ten per
namespace, zero SDK retries, and no workers. The 4,096-token cap is a deliberate
development control, not a production default. The largest returned initial
completion in the baseline was 886 tokens; the cap leaves room for more complex
plans. The adapter uses its existing `max_tokens` control; effectiveness on the
deployed server remains to be qualified.

## Interpretation and next gate

Open question: does the revised initial contract deliver usable first
responses with the same model and schema? Prior correction results do not
answer this, and R1 combines a prompt change and an output ceiling, so it
cannot independently attribute any improvement to one of those controls.
Assess typed validity, intent preservation, safe abstention, and infrastructure
outcomes separately. A deterministic pre-generation rejection is not a model
pass. Preserve any truncation or timeout as observed, without automatic replay.
Wire validity cannot demonstrate what the canonical host would execute.

The provider-free SDK/transport regression exercises the actual planner and
campaign path with mock HTTP responses. It checks the cap on the wire, no
correction after an invalid response, timeout interruption, sealed diagnostics
and raw I/O, and no execution past the wire boundary. The wire schema SHA-256
remains `b6b05fec2caabbc62708d17b1d752d8888e6cf7e2b91b4b67889eb583b080cbb`.
Planner, campaign, and workflow suites: 262 passed. Targeted Ruff, formatting,
compilation, diff check, production attestation, and reachability passed.

The intended entrypoint is unchanged:

```bash
export PYTHONPATH="$PWD:$PWD/src"
.venv/bin/python -m scripts.nlp_d5_live_semantic_qualification \
  --provider-free-preflight --population a10-53 --authorization-json "$authority"
```

For a qualified live candidate, the same command uses `--execute-live`
instead of `--provider-free-preflight`, with private custody, a fresh
namespace and the separately bound watchdog. The existing K-06 gate requires
an accepted smoke applicable to the exact executable and controls before live
admission. The previous smoke did not exercise the new prompt and output cap.
No authority descriptor or live evidence namespace was created. R2 and R3
remain contingent on observed R1 failures; the full 53-case comparison remains
out of scope.
