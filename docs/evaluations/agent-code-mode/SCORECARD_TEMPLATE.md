# Code Mode Migration Scorecard Template

Use one scorecard per committed migration slice. Record observed evidence only.

## Identity

| Field | Value |
|---|---|
| Slice | `CM-XX` |
| Commit | Full SHA |
| Baseline commit | `f03f76bda097bf93e4c640e0fc1a6b82b372bd0c` |
| Date | ISO-8601 date |
| Scope | One-sentence dominant purpose |

## Scope Guard

| Check | Status | Evidence |
|---|---|---|
| Runtime behavior changed only as authorized | `pass`, `fail`, or `not_applicable` | Diff or test reference |
| Dependencies changed only as authorized | `pass`, `fail`, or `not_applicable` | Diff reference |
| Legacy code deleted only as authorized | `pass`, `fail`, or `not_applicable` | Reachability reference |

## Structural Metrics

| Metric | Baseline | Slice value | Measurement command or source |
|---|---:|---:|---|
| Production `src/wellplot/agent` Python LOC | | | |
| Graph package Python LOC | | | |
| Dynamic worker-schema characters | | | |
| Legacy core reached by v2 path | | | |
| Generated program characters | | | |
| Program AST nodes | | | |
| Program calls | | | |
| Program repairs | | | |

Use `not_available` where a metric is not yet applicable. Do not substitute a
guessed zero.

## Deterministic Evidence

| Command | Status | Result | Notes |
|---|---|---|---|
| Targeted tests | | | |
| Full suite | | | |
| Architecture guards | | | |
| Frozen CBL compile/verify | | | |

## Live Evidence

| Case | Provider/model/configuration | Status | Trace | Canonical verifier | Render |
|---|---|---|---|---|---|
| Full CBL reconstruction | | `not_run`, `pass`, `fail`, or `not_reproducible` | | | |
| Simple section | | | | | |
| Report task | | | | | |
| Revision | | | | | |

## Decision

State `PROCEED`, `STOP`, or `HOLD`, the next authorized slice, and the precise
reason. A live provider transport failure is evidence, not permission to add a
fallback or relax a deterministic contract.
