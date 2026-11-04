# A09 D1 Integrated Design Acceptance Record

**Decision date:** 2026-11-03

**Accepted design candidate:** `da23cd69792b4c75ed1da30bc0de35ca69ddcb38`

**Candidate parent:** `feefde0540a72d404f416e7992b0f4d49a779c2a`

**Review disposition:** `A09_D1_ACCEPTED`

**A09 implementation:** Not authorized

**D2 feasibility:** Open

## Decision

Accept the integrated A09-CAT/A09-SRC design at the exact candidate above.
The candidate preserves the accepted metadata-first architecture at
`daef5d171828495b2f0dfcea25ae372f0bc39af4`, adds the governed catalog/source
contract proposal, and closes review findings F15 and F16. The accepted
candidate commit and the original F14 design document remain immutable; this
record documents the accepted relationship and amendment rather than editing
either historical artifact.

### Accepted F14 amendment

The following narrow semantic amendment is accepted for future implementation
design:

- An unambiguously selected physical channel retains exact-identity
  precedence, including an explicitly qualified `GR` channel.
- A bare `GR` request that could mean either the physical mnemonic or the
  Gamma Ray family requires clarification; neither interpretation wins by
  hidden precedence.
- Family-level `ABSENT` requires a complete scoped inventory and a separately
  reviewed, explicitly exhaustive mapping for that source/frame scope. A
  nonexhaustive catalog miss remains `UNKNOWN`/`UNCLASSIFIED`.

No other accepted F14 behavior is changed by this amendment.

### Findings closed

- **F15:** Request-language-to-family rules and family-to-physical-channel
  rules are separate typed contracts. One deterministic host resolver runs
  the stages in order; neither rule establishes physical inventory presence
  or renderer addressability.
- **F16:** The accepted historical semantics and the narrow amendment are
  explicitly distinguished. The original accepted design is not rewritten.
- **Catalog custody:** A semantic resolution carries the exact
  `catalog_content_sha256` and immutable `catalog_release_ref`; the digest is
  recomputed at resolution and before publication. The digest excludes its
  own field.

## Knowledge Delta

### Accepted design knowledge

- Catalog request-term interpretation is distinct from physical-channel
  classification; both are host-owned and independently provenance-reviewed.
- Physical resolution, semantic classification, renderer addressability, and
  sample availability remain separate evidence dimensions.
- Unknown vendor channels remain eligible for explicit physical selection;
  unknown taxonomy does not make physical data unsupported.
- Catalog/file order, mnemonic sorting, and pattern length cannot silently
  resolve collisions.
- A nonexhaustive semantic catalog cannot establish family-level absence.
- Source and catalog identities are pinned to resolution evidence and
  revalidated before canonical publication.
- The supplied family JSON remains reference/collision material only; no rule,
  unit conversion, or presentation preset is approved by D1.

### Preserved architecture and no-change findings

- The existing canonical planner/worker, authoring context, reconciliation,
  executor/service, YAML persistence, and renderer remain the only authoring
  path.
- LAS/DLIS metadata inspection stays behind the existing source-loader and
  inspection boundaries; existing scientific sample loaders are not changed.
- Renderer addressability remains a separate fail-closed gate. Metadata
  uniqueness alone never authorizes binding.
- The A08 whole-message publication boundary remains: unresolved or stale
  evidence cannot partially publish an instruction.
- No production code, provider path, semantic engine, baseline, or scientific
  population is changed by this acceptance record.

### Open questions and next gate

D2 remains open for supported LAS metadata correctness and resource budgets;
valid synthetic RP66 fixtures and DLIS process containment/measurements; exact
Qwen/llama.cpp tokenizer, template, and structured-output accounting; and
catalog provenance, licensing, unit governance, reviewed mappings, and
presentation preset governance. No numeric budgets or production rules are
selected.

The active baseline is intentionally not promoted by this record. A09
implementation and A10 integration qualification remain unauthorized. Any
implementation authority requires a separate D2 closure and review/approval.

## Activity Accounting

```text
production source changes = 0
provider calls = 0
model calls = 0
endpoint calls = 0
scientific turns = 0
C02 exposure = 0
active baseline changes = 0
```
