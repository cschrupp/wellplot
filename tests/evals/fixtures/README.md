# Agent Evaluation Fixtures

The task catalog resolves each fixture below this directory:

```text
tests/evals/fixtures/agent_tasks/<fixture-id>/
  starter.log.yaml       # required for run tasks
  draft.log.yaml         # required for revise tasks
  baseline.log.yaml      # required for deterministic isolation grading
  <source files referenced by the YAML>
```

Source logs and DLIS files may be locally supplied and must not be committed
when redistribution is not permitted. The evaluator reports missing artifacts
as `not_run`; it never substitutes a notebook workspace draft or claims a
provider pass without a canonical baseline.
