# D5-F Post-Hoc Classification Note

This note records an evaluator interpretation found after the immutable
Authority F run. It does not modify, replace, or reclassify any Authority F
custody artifact.

## Recorded Run

- Authority: `WELLPLOT-D5-FINAL-10-QWEN-LIVE-AUTH-20261027-F`
- Campaign: `d5-final-10-qwen-live-20261027-f`
- Checkpoint: `bb05e888f5926488ccbc39181d28460bc0ff2ae2`
- Recorded terminal: `INCONCLUSIVE / HARNESS`
- Completed turns: `1`
- C02 exposure: `0`

The sealed first-turn evidence contains valid provider responses followed by
the bounded worker diagnostic `worker_correction_scope_violation`. The section
worker correctly rejected a correction that changed collection cardinality:

```text
normalization = PASS
worker_obligation = FAIL
semantic_lowering = NOT_REACHED
```

## Evaluator Finding

The evaluator treated `apply_status = compile_failed` as
`HOST_SEMANTIC_APPLICATION` before considering the worker diagnostic. That was
an evaluator classification defect. The production worker did not fail as a
host exception; it correctly rejected an unauthorized model correction.

The corrected interpretation of `D4-C01:C01` is:

```text
failure = model semantic correction-preservation failure
first_divergence = CORRECTION_PRESERVATION
scientific_terminal = FAIL / RESIDUAL_SEMANTIC
infrastructure_failure = false
```

Authority F remains immutable, consumed, and closed. This note is explanatory
only; it does not alter its terminal, custody hashes, or campaign namespace.
