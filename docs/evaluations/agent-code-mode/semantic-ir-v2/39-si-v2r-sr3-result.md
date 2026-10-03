# SI-V2R-SR3 Result

```yaml
decision: SI_V2R_SR3_ROOT_MECHANISMS_RESOLVED
baseline: 6d79a9f0cea757b97509dbd42fb50cc309bbae77
raw_evidence_sha256: 9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08
target_cases: 4/4
target_attempts: 8/8
frozen_semantic_pass: 28/48
ownership_adjusted_semantic_pass: 34/48
frozen_stable_pass: 14/24
ownership_adjusted_stable_pass: 17/24
remaining_adjusted_failures: 8 attempts / 4 stable cases
dominant_root: TIED:ANNOTATION_WRONG_OWNER,UNREQUESTED_REFERENCE_INFERENCE
dominant_root_cases: 2/4 each
root_stability: ROOT_STABLE for all four cases
unexplained_leaves: 0
provider_inference_calls: 0
endpoint_calls: 0
worker_program_calls: 0
production_behavior_changed: false
adr_cm57: UNCHANGED
```

SR3 resolves the diagnostic decomposition, not the semantic failures. The
remaining cases are explained by four generic mechanisms, with two tied
two-case mechanisms and two narrower mechanisms. The result is
`ROOT_MECHANISMS_RESOLVED` because all major leaf clusters are explained,
attempt stability is understood, and the next ownership questions are bounded.

The conclusion is `EMPIRICALLY_SUPPORTED`, not proven neural causality.
CM58.1 already acts on unrequested references, while annotation ownership,
constraint ownership, and unresolved-promotion handling remain separate design
questions. SR3 does not choose among deterministic safety, IR-contract, prompt,
or model changes.

The frozen LQ0 decision remains `SI_V2R_PROVIDER_BOUNDARY_REJECTED`, and SR2
remains `SI_V2R_SR2_REPORT_PRESENCE_RESOLVED`. No model qualification,
provider qualification, production readiness, prompt change, or live
inference follows from SR3.

## Next bounded step

Authorize one provider-free ownership/contract decision slice that compares
the existing CM58.1 reference action and the V2R annotation/constraint owners
against the four SR3 mechanisms. It should decide which distinctions are
already deterministic-owned and which remain model-owned before any fresh
qualification or production implementation.
