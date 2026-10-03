# SI-V2R-SR2 Historical Regrade

## Authority

- Baseline: `e97ae4d53ed82c724a014d7fc5b52598f9ca201d`
- Raw population: `/tmp/si-v2r-live.jsonl`
- Raw SHA-256: `9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08`
- Provider, endpoint, and worker/program calls: `0`

SR2 is a provider-free derived regrade. It does not rewrite the immutable LQ0
decision or score, does not alter CM-58, and does not infer a counterfactual
model output.

The ownership contract under review is deliberately narrow:

```text
report presence  -> deterministic CM-58.2 ownership
report content   -> model ownership when report scope is admissible
```

Model report-routing overreach remains a diagnostic fact. A section-only false
positive is a system-level report-scope success only when unchanged CM-58.2
classifies the request as section-only and removes the report task safely.

Structural failures remain `NOT_EVALUABLE`; no intended output is reconstructed.
Every non-report semantic dimension retains its frozen meaning.
