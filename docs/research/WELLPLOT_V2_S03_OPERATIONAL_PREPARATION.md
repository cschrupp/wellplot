# Revised S03 Operational Preparation

Accepted parent: `1d835ff051fd90f4c1a1440c9ab2abf0d027edd5`.
The frozen measured panel, prompt, DTO and rubric are unchanged. No generation
was performed. This record proposes, but does not grant, smoke authority.

## Proposed smoke authority

- Mode: `s03_revised_observation`; case: `S03-REVISED-SMOKE`.
- Exact request: `What is the current report title?`
- [Exact synthetic fixture](../../src/wellplot/agent/code_mode/planner.py):
  `_S03_SMOKE_CASE`. Canonical title is Thermal Survey; context includes the
  inspected TEMP inventory, ordered prior dialogue, and verified published title.
  Expect one informational report objective, not an edit or a feasibility verdict.
- Request SHA-256: `b3a663f797dccb0d296a7c5ef05e7a8a1268bd24470ed55435b77585c037bb5b`.
- Fixture SHA-256: `6d31054ba207949e1a011a2f1adec98f6054b64472c6e72e78234bd6dde6872e`.
- Prompt SHA-256: `807797c9e776c47cd980e7423686c0bec5e4b8dd194a50b8b2d9c4e9218fadca`.
- Schema SHA-256: `8fe2dffed215069f2ec28672c218db45b405efa059b3c5aacf2356b515d582c0`.

Bind the reviewed preparation checkpoint, exact harness SHA, project config,
worktree allowlist, and matching readiness fingerprint. Leave measured
population and first-pass selection fields unset. Use a fresh private smoke
namespace and `scripts/run_d5_live_campaign.sh planner-smoke s03-revised-development AUTH_JSON`
only after separate authority. One logical generation and one physical attempt;
zero SDK retries or corrections, temperature 0, thinking disabled, 4,096 output
tokens and unchanged timeout/watchdog. No access to R01–R06, executable
conversion or downstream work. Stop after the first response or interruption.

## Non-generative readiness and token budget

Authenticated model listing and properties matched the previously qualified
identity: `qwen3.6-35b-a3b`, llama.cpp `b12340-b8645ddda`, 65,536 context,
one slot, template SHA-256
`55d4931433fe502b794226ee7f4d206a6bdd436ac9f80eb7d8ebb4c639f9ea0c`,
runtime defaults SHA-256
`5136c0f2b22a73572fe88f44e8cf32159ffb3b345ced2e33ba7507d612f7f8c3`.
Model-path identity was verified; GGUF binary and standalone vocabulary byte
identities were not available. Counts use the loaded runtime vocabulary itself.
No matching tokenizer/template pair was found locally; no model was downloaded.

On the qualified runtime, submit the exact mock-captured SDK bodies to documented
[`/apply-template` and `/tokenize`](https://github.com/ggml-org/llama.cpp/blob/b12340/tools/server/README.md).
The [upstream release implementation](https://github.com/ggml-org/llama.cpp/blob/b12340/tools/server/server-context.cpp)
uses the same chat parameter parser for template application and chat generation.
The upstream tag resolves to `8954f194837d2ec4d5f67f20c81b84abe63883ba`,
not the runtime's reported `b8645ddda`. Treat release source as documentation,
not exact deployed-source attestation. The deployed runtime's actual endpoints
and the same-runtime historical calibration below support the budget finding.
Count with special-token insertion and parsing enabled, as for text generation.
The exact schema-bearing and schema-free requests rendered byte-identical
prompts on each case: structured output adds **zero prompt tokens** here.
The rendered suffix confirmed thinking disabled. The same counting procedure
reproduced all 990 reported prompt tokens from the sealed H1b smoke without
rerunning it. No completion endpoint was called.

| Input | Tokens |
| --- | ---: |
| R01 | 1,593 |
| R02 | 1,788 |
| R03 | 3,131 |
| R04 | 2,061 |
| R05 | 1,715 |
| R06 | 1,589 |
| S03-REVISED-SMOKE | 1,429 |

All are below 60,000 input tokens, with 4,096 reserved output and 1,440 additional
tokens. The largest has 56,869 input tokens of headroom after both reserves.
No truncation. Readiness evidence SHA-256:
`1418228078639588fc66703c5237906ccaa25b174fef0260dbb530116adf673c`.
Exact-body token evidence SHA-256:
`a90574879576ba3e79fa5c6c1515e2aaf412457781431b57b9d81df8a13056b9`.

## Provider-free qualification

The [focused suite](WELLPLOT_V2_S03_REVISED_EXPERIMENT.md#provider-free-qualification)
passed 385 tests. Existing smoke custody tests now cover success and invalid
first response for S03, verify the actual advertised DTO, zero retries,
no measured panel load and zero downstream calls. H1a and H1b remain covered.
S03 and S03.3 remain in progress; H2 stays blocked. Stop for independent review.
