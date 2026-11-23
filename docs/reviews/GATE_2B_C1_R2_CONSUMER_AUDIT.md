# Gate 2B-C1 Revision 2 Consumer Audit

## Review State

```yaml
baseline: 640010ae48a1be075b45719843d969aec177b32b
candidate_patch_sha256: b6b6fbed377272e20a9b1749792f619296b88ff015dcccf69a379de4c5503c89
review_disposition: bounded HOST_CONTEXT dependency contract passed static independent review
complete_c1_matrix: open
request_scope_qualification: requires separately authorized request syntax
c2_implementation_authorized: false
production_activation_authorized: false
```

This audit records only the bounded C1 dependency-provenance review. It does
not accept the complete C1 matrix and does not authorize C2, production
admission, execution, publication, or live inference.

## Consumer Audit

| Boundary | Local source | Custody |
| --- | --- | --- |
| Request facts and provenance | `obligations.py:152,219,873,1461,2000` | The original model derives requirement IDs from owner kind/ref, field and original byte start. The same helper is independently called for all four dependency facts. |
| Requirement and compilation models | `obligations.py:305`; `compile_request_contract` at `1955` | Existing compiler constructs the set and result; no dependency emitted. Existing readers can validate old JSON with the default empty tuple. New JSON has an additive field; strict pre-change readers do not accept it. |
| Scope origin | `obligations.py:1852` and anonymous scope in `compile_request_contract` | Named declarations originate in text; anonymous existing-section declaration is symbolic and grounded by host context only later. The exact joint fixture contains no section wording, so only the canonical anonymous declaration is legal. REQUEST origin cannot have a positive joint case without separately authorized named-scope syntax. |
| Coverage | `obligations.py:2207` | Legacy tuple supported without dependencies. Dependency validation consumes the whole set, checking its real declaration, request and fact provenance, IDs, geometry, and exact two relation spans. An unsupported joint request without the record cannot pass by stripping it or supplying empty anchors. |
| Planner and attachment | `planner.py:491,628,651,1203,1340,1555,1633` | Host-only compilation is attached intact. Assigned task copies have scope keys rewritten; these copies are not the original validated set. No consumer treats dependencies as admission. C2 must check the full set before attachment and separately join task assignments before any dependent admission. |
| Internal graph | `workflow.py:124,130,198,236,576`; `facade.py:280` | Internal SemanticPlan JSON preserves nested compilation, but reconstructing models does not prove provenance. Provider wire and worker contracts receive no new dependency authority. |
| Downstream execution | `worker_contracts.py:641,1383,2041`; `agent/_private_apply.py` | Existing work admission and execution use task facts and specific admitted operations. Neither receives a new relationship or execution occurrence. |

Inventory paths above are under `src/wellplot/agent/code_mode` unless otherwise
indicated. The reviewed implementation changes only `obligations.py`,
`tests/test_d5_5j_obligations.py`, and the single-engine production manifest.
No runtime transport was changed.

## Limitations and Deferred Work

C2 still needs bounded joint grammar, actual compiler emission, independent
anchor coverage, and host scope transport. Named REQUEST qualification requires
original scope syntax and validation, not a fabricated declaration.

The complete C1 matrix remains open because named REQUEST-scope qualification
requires separately authorized request syntax. No C2 implementation or
production activation is authorized by this checkpoint.
