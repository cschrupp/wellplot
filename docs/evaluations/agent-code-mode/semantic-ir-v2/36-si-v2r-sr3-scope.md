# SI-V2R-SR3 Residual Root-Mechanism Decomposition

## Authority

- Baseline: `6d79a9f0cea757b97509dbd42fb50cc309bbae77`
- Raw population: `/tmp/si-v2r-live.jsonl`
- Raw SHA-256: `9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08`
- Provider, endpoint, and worker/program calls: `0`

SR3 is a provider-free decomposition of the four stable ownership-adjusted
failures remaining after SR2. It does not alter the LQ0 or SR2 scores, change
the evaluator, or propose a production repair.

The target population is exactly:

```text
cm59-single-garnet-06
cm59-alloc-verde-19
cm59-mixed-amber-24
cm59-single-iris-08
```

The analysis compares the original request, frozen V2R gold, generated V2R,
SR2 leaf residuals, and retained CM58.1/CM58.2/CM58.3 evidence. A root
mechanism means the smallest evidence-supported interpretation mistake that
can explain correlated leaf differences. It is not a claim about internal
model causality.

The result preserves:

- LQ0 semantic score `28/48` and stable score `14/24`;
- SR2 ownership-adjusted score `34/48` and stable score `17/24`;
- six structural rows as non-evaluable;
- the historical LQ0 decision `SI_V2R_PROVIDER_BOUNDARY_REJECTED`.

No prompt, schema, compiler, registry, planner, provider, graph, worker,
CM58 policy, qualification corpus, scoring rule, or ADR was changed.
