# SI-V2R-BR1 Adapter Decision

## Options

### A. Direct Canonical Schema

Retain the direct `SemanticIRV2R` provider boundary. This remains viable, but
the current evidence does not establish whether the six terminal failures
were caused by decoder compatibility or canonical runtime validation.

### B. Schema Projection

Transform only the provider-facing JSON Schema while retaining the exact
`SemanticIRV2R` serialized representation and unchanged canonical validation.
This is the preferred adapter if a pinned converter audit demonstrates a
specific unsupported or ineffective construct.

### C. Separate Wire Model

Introduce `SemanticWireV2R` only if a schema projection cannot express the
required adaptation without changing the provider representation. A wire
model would require exact round-trip preservation for all 24 gold cases and
non-benchmark domain fixtures.

### D. Weak / General JSON

Useful only as a diagnostic control. It is rejected as a promotion approach
because parse success or permissive intermediate acceptance would not be
canonical structural success.

## Decision

`SI_V2R_BR1_BOUNDARY_MECHANISM_UNRESOLVED`

No adapter is selected in BR1. The deployed converter provenance is unresolved
and the retained provider diagnostic does not distinguish JSON-Schema rejection
from Pydantic relational validation. Selecting a simpler wire model now would
be a hypothesis-driven architecture change rather than an evidence-based
boundary correction.

## Required Properties of Any Future Adapter

Any later Option B or C implementation must be pure, deterministic, isolated
from production, and non-repairing. It must preserve report presence, section
count/order, feature kind and multiplicity, semantic identities and targets,
reference meaning, requirements, constraints, source hints, existing-section
hints, and unresolved requirements. Canonical validation remains mandatory;
conversion failure remains structural failure.

## Revisit Condition

Reopen the decision only after a provider-free audit authenticates the deployed
converter/toolchain or otherwise produces a reproducible boundary incompatibility
that a schema projection can address. A later live qualification would then be
a separate authorized experiment.
