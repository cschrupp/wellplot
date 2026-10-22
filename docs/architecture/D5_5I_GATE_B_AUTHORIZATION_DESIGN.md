# D5-5I Gate-B Authorization Design

```yaml
authority: WELLPLOT-D5-5I-GATE-B-AUTHORIZATION-DESIGN-AUTH-001
branch: design/d5-5g-inspectable-historical-claim-revalidation
executable_checkpoint: 661a7eeeabcfa4e6364aeb3e74bf55859ac48539
accepted_h_implementation: e72e726b7f52c1975d862980543cd3f217ee6aa8
provider: openai_compat
model: qwen3.6-35b-a3b
live_readiness: NOT_AUTHORIZED
live_execution: NOT_AUTHORIZED
provider_model_calls_during_design: 0
endpoint_calls_during_design: 0
```

## Decision Boundary

This record prepares one later Gate-B authorization for a single repaired-
baseline confirmation. It does not authorize credentialed readiness, endpoint
observations, model generation, or campaign creation.

The executable checkpoint is the already-reviewed provider-free result commit
`661a7eeeabcfa4e6364aeb3e74bf55859ac48539`. A later authorization-record
commit may be a descendant on this design branch, but it must not replace or
rewrite that executable checkpoint. The live runner must use a clean worktree
exactly at the executable checkpoint while consuming the later authorization
record as external or non-versioned campaign custody.

The proposed later record identifiers are:

```yaml
authorization_id: WELLPLOT-D5-5I-LIVE-RUN-AUTH-001
campaign_id: d5-5i-qwen-live-001
artifact_root: workspace/evaluations/d5-5i/qwen-live-001
```

Those identifiers are reserved for the subsequent explicit Gate-B authority;
this design does not consume them or create campaign state.

## Frozen Contract

The later authorization record must bind these values without substitution:

```yaml
implementation_checkpoint: 661a7eeeabcfa4e6364aeb3e74bf55859ac48539
provider: openai_compat
model: qwen3.6-35b-a3b
structured_output_contract: json_schema
openai_sdk_version: 2.34.0
sdk_max_retries: 2
request_timeout_seconds: 900
scientist_turn_concurrency: 1
logical_generation_call_ceiling: 45
physical_generation_attempt_ceiling: 135
identity_endpoint_attempt_ceiling: 2
fallback: NONE
model_substitution: FORBIDDEN
experiment_level_replay: FORBIDDEN
selective_rerun: FORBIDDEN
```

The project configuration fingerprint is frozen as:

```yaml
project_config_fingerprint_sha256: b1d794a5ede8d4855717d34b3a02993f19b473ad120ff4fa51a06322a08a5bc3
```

The accepted H implementation, D5 single-engine production attestation, case
and gold identities, source identities, and `uv.lock` identity must be copied
from the executable checkpoint and recorded in the later authorization. They
must not be recomputed from a different checkout or silently refreshed.

The exact Qwen endpoint identity, runtime-default fingerprint, chat-template
fingerprint, minimum context size, and `thinking_off: true` evidence must be
reused verbatim from the sealed `d5-5-qwen-inspectable-002` run. They are not
inferred by this design and may not be regenerated, normalized, weakened, or
replaced. If the sealed values cannot be recovered exactly, the later run
stops before readiness.

## Scientific Population

The later campaign uses the existing frozen nine-turn population, unchanged
and in order:

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

The three frozen local source assets and their identities remain those in the
accepted D5-5I design. They must be present and verified in the execution
checkout before any credentialed observation. Missing or mismatched assets
terminate preflight as `LOCAL_ASSET_NOT_PROVISIONED_IN_THIS_CHECKOUT`.

Historical campaigns, requests, gold, fixtures, and evidence are immutable and
must not be reused as the new campaign namespace.

## Readiness Sequence

After static custody and local-asset checks pass, the later live authority
permits exactly these two credential-bearing identity observations, in order:

```text
1. GET /v1/models
2. GET /props
```

Both requests use the existing WellPlot credential path. They are identity
endpoint calls, not generation calls. The exact frozen Qwen identity is
compared only after both observations return. There is no readiness retry,
replay, fallback, or alternate endpoint.

The separate identity-attempt ceiling is `2`:

- a request rejected before it is issued consumes no identity attempt;
- once either GET is issued, including HTTP, authentication, or transport
  failure, it consumes one identity attempt;
- `/v1/models` failure terminates with one identity attempt;
- `/props` failure terminates with two identity attempts;
- a successful pair still requires exact identity/configuration comparison
  before any generation request.

Any static, asset, identity, endpoint, model, runtime-default, structured-
output, or thinking-mode mismatch stops before model calls.

## Generation Accounting

The generation budget is independent of readiness accounting:

- one planner, report-worker, section-worker, or existing authorized
  correction invocation consumes one logical generation call;
- an SDK retry of the same logical invocation consumes no additional logical
  call;
- every actually issued `/chat/completions` HTTP attempt consumes one physical
  attempt, including failed and retried attempts;
- with `sdk_max_retries = 2`, one logical call consumes at most three physical
  attempts;
- a request rejected before provider delegation consumes neither a logical
  call nor a physical attempt;
- logical call `46` and physical attempt `136` are rejected before delegation.

The `/v1/models` and `/props` observations consume neither generation budget.
No experiment-level retry, semantic replay, selective rerun, model
substitution, prompt change, or manual replacement is allowed.

## Custody And Terminal Rules

The later campaign must reuse the accepted D5-5I wire-level custody path and
the existing canonical execution path:

```text
shared composition root
  -> SemanticPlanner
  -> canonical workers
  -> deterministic lowering/reconciliation
  -> execution
  -> persistence/reload/render
  -> deterministic grading
```

For every physical attempt, custody must preserve the case/turn and logical
call identity, generation role, exact request/response hashes, structured
boundary, canonical and semantic validation, host transforms, correction
scope, resulting mutation, persistence/reload/render evidence, grader result,
and first divergence. Credentials, headers, and raw payloads remain subject
to the accepted redaction policy.

Once fresh campaign custody reaches `STARTED`, it is irreversible. A terminal
result must be one of:

```text
PASS
FAIL / RESIDUAL_SEMANTIC
FAIL / CONTRACT_OR_INPUT
INCONCLUSIVE / PROVIDER
INCONCLUSIVE / HARNESS
```

Every non-PASS result must identify the earliest evidence-supported first
divergence. A live failure does not automatically authorize another campaign.

## Decision Record

**Decision:** Prepare one Gate-B record for a repaired-baseline Qwen
confirmation, with a separate identity-endpoint budget and immutable
executable checkpoint.

**Project scope:** Confirm the accepted D5-5H baseline on the frozen D4
population without reopening architecture, prompt, schema, model selection,
or historical experiments.

**Established practice:** Treat build/configuration identity, readiness checks,
generation attempts, and scientific observations as separately auditable
resources; bind one-shot experiments to immutable inputs before execution.

**WellPlot adaptation:** The existing D5 custody and single-engine path are
reused, while `/v1/models` and `/props` receive their own bounded attempt
counter because they are identity observations rather than generations.

**Options considered:**

1. Reuse the prior D4 authorization boundary without a separate identity
   budget. Rejected because readiness failures would be ambiguously accounted.
2. Create a new live harness or provider path. Rejected because it violates
   the single-engine and accepted-custody invariants.
3. Pin the reviewed executable checkpoint and separate readiness accounting
   in one later authorization record. Selected.

**Evidence class:** ADAPTED / EMPIRICALLY_SUPPORTED.

**Risks:** sealed runtime pins may be unavailable; local assets may be absent;
endpoint identity may drift; provider or structured-output failure may make the
result inconclusive; an authorization-record commit could be mistaken for the
executable checkpoint.

**Reversible:** YES before credentialed readiness and `STARTED`.

**Validation:** static custody and asset checks, exact two-observation
readiness, shared canonical execution, bounded custody, deterministic grading,
and post-terminal artifact verification.

**Stop/revisit condition:** any mismatch in the executable checkpoint, sealed
runtime identity, frozen assets, scientific inputs, production attestation,
identity-attempt budget, or custody contract stops before model calls.

## Authorization Boundary

```yaml
design_status: READY_FOR_INDEPENDENT_GATE_B_DESIGN_REVIEW
credentialed_readiness: NOT_AUTHORIZED
endpoint_calls: 0
provider_model_calls: 0
live_campaign: NOT_AUTHORIZED
production_promotion: NOT_AUTHORIZED
D5-5G_replay: NOT_AUTHORIZED
D5-5J: NOT_AUTHORIZED
```
