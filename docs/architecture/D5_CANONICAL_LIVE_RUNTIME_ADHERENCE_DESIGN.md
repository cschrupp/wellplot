# D5 Canonical Live Runtime Adherence — Design 001

```yaml
authority: WELLPLOT-D5-CANONICAL-LIVE-RUNTIME-ADHERENCE-DESIGN-001
status: DESIGN_CANDIDATE
base_checkpoint: f752db35a75f8015c13ff99dc5b8d63c1deaa6f7
provider_calls: 0
model_calls: 0
endpoint_calls: 0
scientific_population_changes: 0
```

## 1. Purpose

Prevent a disposable clone or worktree from silently becoming the runtime root
for WellPlot live qualification.

This is an operational-adherence correction. It does not redesign the semantic
engine, provider path, project configuration, scientific population, grader,
or D5 campaign semantics.

The failure class being corrected is root conflation:

```text
checkout root
    == code identity root

but was also being treated as

credential root
    + local scientific-asset root
    + durable evidence root
```

That convention is valid for the established persistent WellPlot checkout, but
unsafe when an agent substitutes a disposable checkout such as `/tmp/...`.

## 2. Existing authority reused unchanged

This design reuses and does not reopen:

1. `config/wellplot.yaml` as the canonical non-secret provider/runtime
   configuration.
2. `src/wellplot/project_config.py` as its strict typed loader.
3. K-01 in `docs/agent-code-mode-current-baseline.md`: one canonical semantic
   engine.
4. `docs/architecture/D5_SINGLE_ENGINE_PRODUCTION_MANIFEST.json`.
5. The shared composition root and canonical
   planner/worker/lowering/reconciliation/execution path.
6. The D5 live harness and its existing credential loader.
7. The existing repository-relative local scientific assets.
8. The existing repository-relative `workspace/evaluations/...` evidence
   layout.
9. D5-FINAL-10, its frozen population, C02 holdout status, graders, call
   ceilings, and accepted checkpoints.
10. The Live Execution Pre-START Gate in `AGENTS.md` and
    `docs/project-decision-protocol.md`.

No new semantic or scientific authority is created by this design.

## 3. Established machine-local runtime

For the current WellPlot host, the persistent live runtime is:

```text
canonical checkout:
    /home/user/projects/well_log_os

canonical project config:
    /home/user/projects/well_log_os/config/wellplot.yaml

canonical OpenAI-compatible credential file:
    /home/user/projects/well_log_os/LLAMA_CPP_API_KEY.txt

canonical durable evaluation namespace:
    /home/user/projects/well_log_os/workspace/evaluations/...
```

The credential value remains secret and must never be printed, committed, or
copied into evidence.

The configured endpoint remains owned by `config/wellplot.yaml`; this design
does not restate the endpoint as a second runtime configuration source.

## 4. Decision

### D-01 — Live execution uses the canonical persistent checkout

Any WellPlot operation that performs credential-bearing endpoint activity,
provider-backed smoke execution, scientific execution, benchmark execution, or
evidence-bearing campaign custody must use:

```text
/home/user/projects/well_log_os
```

as its repository/execution root on the current host.

A live run must not be launched from `/tmp`, another disposable worktree, an
ephemeral clone, or a scratch copy of the repository.

### D-02 — Temporary worktrees remain implementation-only

A temporary or secondary worktree may be used when there is a genuine
simultaneous-checkout need for implementation, diff inspection, or independent
code review.

Such a worktree must not:

- perform provider-backed live qualification;
- consume a live smoke or scientific authority;
- hold campaign custody as the durable source of record;
- become the source of machine-local credentials;
- receive copied credential files to make live execution work;
- become the canonical local scientific-asset store.

### D-03 — Existing configuration remains the only non-secret runtime config

Do not add another YAML, JSON, environment-derived endpoint configuration,
provider configuration layer, or evaluation-specific model configuration.

`config/wellplot.yaml` remains authoritative for provider name, model,
server origin, timeout, retries, concurrency, and structured-output mode.

Experiment code may freeze/assert those values but may not become a parallel
configuration authority.

### D-04 — Existing single engine remains the only semantic engine

No fallback engine, evaluation engine, model-specific compiler, provider-
specific semantic path, or shadow authoring path may be introduced by this
correction.

The live harness must continue to reach the accepted canonical production
composition path.

### D-05 — Do not split checkout_root/runtime_root in this correction

The present problem does not justify a new `runtime_root` abstraction.

For the accepted live environment, the canonical checkout already is the
persistent runtime root. The bounded correction is to stop agents from
substituting disposable roots, not to generalize the path model.

A later multi-host packaging requirement may reopen this choice through the
normal architecture process.

## 5. Mandatory pre-authority environment check

Before issuing or consuming a new live smoke or scientific campaign authority,
the executing agent must run a non-generative check from the exact shell and
checkout that would perform the live run.

It must establish, without printing secret contents:

```text
PWD_RESOLVED
    /home/user/projects/well_log_os

GIT_TOPLEVEL_RESOLVED
    /home/user/projects/well_log_os

PROJECT_CONFIG
    config/wellplot.yaml loaded successfully

CREDENTIAL_SOURCE
    /home/user/projects/well_log_os/LLAMA_CPP_API_KEY.txt
    exists = YES
    readable = YES
    secret contents = NOT PRINTED

CREDENTIAL_LOADER
    load succeeds
    secret contents = NOT PRINTED

ARTIFACT_ROOT
    resolves below /home/user/projects/well_log_os/workspace/evaluations
    disposable/temp root = NO

LOCAL_SCIENTIFIC_ASSETS
    required frozen assets available and hash-qualified

/v1/models
    authenticated HTTP success/failure only
    sanitized model identity only

/props
    authenticated HTTP success/failure only
    sanitized endpoint/runtime identity only

MODEL_CALLS
    0

C02_EXPOSURE
    0
```

Failure of any item terminates the environment check. It is operational
evidence only and must not consume a scientific campaign.

## 6. Why no harness rewrite is authorized yet

The current D5 harness already:

- loads `config/wellplot.yaml`;
- fingerprints and validates that configuration;
- uses the accepted canonical semantic engine;
- uses the existing credential loader;
- writes campaign evidence below the authorized artifact root;
- separates readiness from scientific STARTED.

The observed recurring failure is caused by launching that machinery from the
wrong root, not by absence of those mechanisms.

Therefore this design first closes the agent/runtime adherence gap. A product
code guard is authorized only if independent review demonstrates that the
operational rule cannot be enforced reliably without one.

If such a guard becomes necessary, it must be a narrow pre-live fail-closed
check. It must not create a new provider, configuration source, credential
resolver, semantic path, or campaign runner.

## 7. Explicitly forbidden rework

This slice must not:

- add `runtime_root`, `machine_root`, or an equivalent second-root
  architecture;
- add another config file;
- move endpoint/model settings out of `config/wellplot.yaml`;
- hard-code a second endpoint in a new harness;
- replace `load_d4_api_key` solely for this issue;
- copy or symlink the API key into `/tmp`;
- copy local scientific data into disposable worktrees for live execution;
- create a new live-smoke harness;
- create a new evaluation engine;
- alter D5-FINAL-10 or C02;
- perform model calls while implementing or reviewing this correction.

## 8. Candidate repository changes

The design candidate authorizes only governance/documentation changes:

1. this design record;
2. strengthening `AGENTS.md` so live/evidence-bearing operations cannot use
   disposable roots.

After independent acceptance, the Knowledge Delta may promote the invariant
into `docs/agent-code-mode-current-baseline.md` and reconcile the corresponding
checkout/worktree item in `docs/backlog.md`.

No production or harness source file is authorized in the design candidate.

## 9. Acceptance criteria

Independent review must verify all of the following:

- the design reuses `config/wellplot.yaml` rather than duplicating runtime
  configuration;
- the design preserves the one-engine invariant;
- D5-FINAL-10 and all scientific fixtures remain byte-unchanged;
- no provider/model/endpoint calls were made to create the candidate;
- the API key is not copied, printed, committed, or exposed;
- `/tmp` is explicitly forbidden for live/evidence-bearing execution;
- implementation/review worktrees remain allowed only when genuinely needed;
- canonical live evidence remains durable below the persistent checkout;
- the design does not authorize a new harness or scientific campaign.

## 10. Next step

Run an independent review of this exact design candidate and the associated
`AGENTS.md` change.

If accepted:

1. promote the invariant into the Current Active Baseline;
2. reconcile the related backlog wording;
3. perform the non-generative canonical-runtime environment check from
   `/home/user/projects/well_log_os`;
4. only after that check succeeds, decide whether a fresh smoke authority is
   appropriate.

No scientific campaign is authorized by this document.
