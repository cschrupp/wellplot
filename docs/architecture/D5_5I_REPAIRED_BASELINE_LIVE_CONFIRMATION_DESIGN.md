# D5-5I Repaired-Baseline Live Confirmation Design

```yaml
authority: WELLPLOT-D5-5I-REPAIRED-BASELINE-LIVE-CONFIRMATION-DESIGN-AUTH-002
branch: design/d5-5g-inspectable-historical-claim-revalidation
active_baseline: docs/agent-code-mode-current-baseline.md
accepted_h_implementation: e72e726b7f52c1975d862980543cd3f217ee6aa8
provider: openai_compat
model: qwen3.6-35b-a3b
provider_model_calls_during_design: 0
endpoint_calls_during_design: 0
live_execution: NOT_AUTHORIZED
```

## 1. Purpose And Decision Boundary

D5-5I is one bounded end-to-end confirmation of the accepted D5-5H repaired
baseline on the current Qwen production lane. It is not a new architecture,
prompt, schema, model comparison, or A/B experiment. The design is complete
only when the exact live authorization separately pins the executable
checkpoint, runtime identity, custody namespace, and one-shot campaign.

The result may confirm the repaired baseline, identify a residual semantic
failure, or become inconclusive because infrastructure or the evidence path
prevents scientific interpretation. It does not automatically authorize a
follow-up experiment or promote a model, prompt, or implementation change.

## 2. Non-Rediscovery Precheck

The following are settled/inherited from the current active baseline and D5-5H
implementation. D5-5I has no experimental arms for them:

| Settled constraint | D5-5I treatment |
| --- | --- |
| One canonical semantic engine | Exercise only the shared composition root and accepted production path. |
| Executable work-unit schema | Reuse the accepted provider/Python contract and its regressions. |
| Required-key, nullable reconstruction `existing_section_hint` | Reuse the accepted required-key/nullable contract. |
| Deterministic unique capability-parent closure | Observe the existing closure and causal failure behavior. |
| Bounded revision inventory | Use the accepted provider-visible target inventory. |
| Explicit source inspection state | Require `inspected`, `not_inspected`, or `unavailable` state. |
| Inspected channel visibility | Use the accepted bounded channel inventory. |
| Report title/subtitle ownership | Preserve the separation from host header slots. |
| Causal negative grading | Apply the accepted diagnostic-owner and no-mutation contract. |
| Deterministic correction-scope preservation | Exercise the existing guard; do not add a repair mechanism. |
| Semantic CBL verifier | Reuse semantic verification without restoring exact benchmark prose. |

The genuinely open questions are:

1. Does the accepted repaired baseline operate end-to-end with the current Qwen
   production lane?
2. Which semantic failures, if any, remain after H?
3. If a real semantic correction occurs, does the deterministic preservation
   guard accept the intended correction without unrelated semantic loss?

## 3. Frozen Population

Use the existing nine-turn D4 population, unchanged and in this order:

```text
D4-C01:C01
D4-L01:T1
D4-L01:T2
D4-L01:T3
D4-L01:T4
D4-L02:T1
D4-L02:T2
D4-L03:C01
D4-L04:C01
```

The case and gold files remain the accepted frozen artifacts. Their current
custody identities are:

```yaml
cases_sha256: f710581831b29dcd7ab321dd91afc5dd2b4e40b729161f969f8802f3f7a84298
gold_sha256: 99ba5fc73dfd95d67c8a909cb75325a84ff1bbccc724fa524d7850f306d02968
uv_lock_sha256: 0076359f8f68da82efa5e800d61ef38032fad72742340f51b78b6d8e969ff1b6
```

Historical requests, gold, sealed campaigns, and the D4-5G artifacts are
inputs/evidence only. They must not be rewritten or reused as the new campaign
namespace.

## 4. Required Production Execution Path

Every turn must use the accepted production path:

```text
shared composition root
  -> SemanticPlanner
  -> canonical report/section workers
  -> deterministic lowering
  -> reconciliation
  -> execution
  -> persistence
  -> reload
  -> render
  -> deterministic grading
```

The confirmation must not use D5-5G experimental context construction, a
hand-built planner context, a shadow executor, a second planner/worker/
compiler, a model-specific repair path, or an evaluation-only semantic engine.
The existing canonical correction path is the only permitted correction path.

## 5. Local Scientific Asset Gate

Before any credentialed readiness or model request, the execution checkout must
contain and verify all frozen local source assets. Missing assets are an
execution-checkout condition, not evidence that the project assets do not
exist.

| Asset | Required path | Size | SHA-256 |
| --- | --- | ---: | --- |
| LAS | `workspace/data/30-23a-3 8117_d.las` | 5,987,785 | `7e6c69c65713dc33303362ab91b767eb06371fd24a31856add8650e6d3bee1a9` |
| CBL main pass | `workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis` | 111,573,216 | `3ceb9100fd654d710155672a50a9e0f24ce9705db6ef8e424140f29bd02131f7` |
| CBL repeat pass | `workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis` | 3,294,924 | `a4a2e91b495172079fc47bc2e9c936f0ab60c9845bbed8e65bf56555a5e82640` |

The pre-live asset gate must verify file existence, byte size, SHA-256, real
loader parsing, and the required channel inventory. The LAS contract includes
`GR`, `CALI`, and `ILD`, with `RT` absent for the frozen missing-channel case;
the CBL sources must expose the accepted D3 scalar and VDL channels. If any
asset is absent or mismatched, the run stops before endpoint or model calls
with:

```text
LOCAL_ASSET_NOT_PROVISIONED_IN_THIS_CHECKOUT
```

No synthetic replacement, alternate source, Git commit, or general asset
provisioning change is part of D5-5I.

## 6. Readiness Contract

The later live authorization and provider-free preflight must bind all of the
following before readiness calls:

- exact executable implementation checkpoint and clean worktree;
- current project/runtime configuration fingerprint;
- provider `openai_compat` and model `qwen3.6-35b-a3b`;
- the previously accepted Qwen endpoint identity;
- context-size minimum and runtime-default fingerprint;
- structured-output contract `json_schema`;
- thinking disabled as an established serving/runtime precondition;
- exact LAS/DLIS source hashes above;
- frozen case, gold, and dependency hashes;
- accepted single-engine production attestation;
- fresh campaign ID and artifact root with no state, journal, or terminal
  artifacts already present.

The readiness sequence is exactly the accepted identity sequence:

```text
credential-bearing GET /v1/models
credential-bearing GET /props
exact frozen Qwen identity comparison
```

The existing accepted runtime identity pins must be reused verbatim. They may
not be inferred, regenerated, weakened, or silently updated. Any mismatch
stops the run before model calls as `NOT_READY` or `INCONCLUSIVE`, according to
the existing readiness taxonomy.

## 7. Custody And Inspection

Reuse the accepted wire-level D4 custody mechanism. Do not reconstruct prompts,
create a second observer, or persist credentials or headers. For every physical
attempt, the sealed evidence must join:

- case and turn identity;
- logical-call identity and generation role;
- exact transmitted request body and hash;
- exact raw response body and hash under the existing secret policy;
- response parsing and structured-output boundary;
- canonical validation and semantic validation;
- deterministic host transforms;
- correction scope and before/after preservation evidence when applicable;
- resulting intent and mutation state;
- persistence, reload, and render evidence;
- deterministic grader result and first divergence.

The evidence must preserve separate provider/structured, planner structural,
semantic, target/source/channel, capability, correction-preservation,
safe-negative, mutation, persistence/reload/render, and terminal outcomes.

## 8. Terminal Taxonomy

Every turn and the campaign receive a bounded terminal classification:

| Classification | Meaning |
| --- | --- |
| `PASS` | The repaired baseline satisfies the frozen population with no disqualifying semantic failure or protected regression. |
| `FAIL / RESIDUAL_SEMANTIC` | Infrastructure and custody are valid, but a genuinely residual semantic failure remains after H. |
| `FAIL / CONTRACT_OR_INPUT` | Live evidence contradicts a supposedly closed H contract or input requirement. |
| `INCONCLUSIVE / PROVIDER` | Provider/runtime behavior prevents scientific interpretation. |
| `INCONCLUSIVE / HARNESS` | Custody, execution, or evaluation prevents scientific interpretation. |

Every non-PASS result must identify the earliest evidence-supported first
divergence. A stable wrong-plan escape is a failure; deterministic host safety
does not turn incorrect semantics into a semantic pass. A failure does not
automatically authorize another experiment.

## 9. Call Budget And One-Shot Rules

The inherited accepted D4 ceiling is the D5-5I ceiling:

```yaml
logical_generation_call_ceiling: 45
physical_attempt_ceiling: 135
sdk_max_retries: 2
experiment_level_replay: FORBIDDEN
selective_rerun: FORBIDDEN
```

The expected call plan is derived from the canonical workflow: one normal
planner call per turn, plus only the existing bounded report/section worker
and correction calls required by production for that turn. No model-generated
extra call, experiment-level retry, or semantic replay is allowed. The live
authorization must record the expected per-turn role budget and these maximums
before execution; the implementation must reject logical call 46 and physical
attempt 136 before delegation.

One campaign is authorized at a time. Once fresh custody reaches `STARTED`,
there is no resume, replay, selective rerun, model substitution, prompt
change, or manual campaign replacement.

## 10. Grading And Scientific Interpretation

The closeout must report each dimension separately:

- provider/structured validity;
- planner structural validity;
- semantic correctness;
- target grounding;
- source/channel grounding;
- capability correctness;
- correction preservation;
- safe-negative correctness;
- mutation correctness;
- persistence/reload/render correctness.

The campaign result must distinguish confirmation from discovery. A PASS
confirms the accepted baseline for this finite population and lane; it does not
prove general model capability. A residual semantic failure is new evidence
only after the H contract, input, custody, and grading gates remain valid.

## 11. Live Authorization Boundary

This design authorizes no provider, endpoint, or model calls. A later explicit
Gate-B authority must pin:

- exact executable checkpoint;
- authorization and campaign IDs;
- fresh artifact root;
- Qwen endpoint/runtime identity pins;
- project/case/gold/source/dependency/production hashes;
- call ceilings and retry policy.

Until that authority exists, D5-5I remains design-only. D5-5G replay, model
comparison, D5-5J, production promotion, and asset provisioning are not
authorized.

## 12. Stop Conditions And Handoff

Stop before live calls if local assets, readiness identity, checkpoint,
configuration, hashes, attestation, or fresh custody fail. Stop after the one
terminal campaign result and preserve all evidence unchanged for independent
review. Do not automatically convert a failure into a new study.

```yaml
D5-5I: DESIGN COMPLETE / READY FOR INDEPENDENT REVIEW
provider_model_calls: 0
endpoint_calls: 0
implementation_changes: 0
source_changes: 0
model_comparison: NOT_AUTHORIZED
D5-5G_REPLAY: NOT_AUTHORIZED
D5-5J: NOT_AUTHORIZED
live_execution: NOT_AUTHORIZED
```
