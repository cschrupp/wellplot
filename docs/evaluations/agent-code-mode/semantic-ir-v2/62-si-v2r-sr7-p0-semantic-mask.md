# SR7-P0 Semantic Dimension Mask

The closed dimension vocabulary is:

`REPORT_PRESENCE`, `REPORT_CONTENT`, `SECTION_STRUCTURE`,
`SECTION_ALLOCATION`, `SECTION_ORDER`, `FEATURE_KIND`,
`FEATURE_MULTIPLICITY`, `REQUIRED_CONTEXT`, `REFERENCE_PRESENCE`,
`REFERENCE_KIND`, `REFERENCE_TARGET`, `ANNOTATION`, `CONSTRAINT_SCOPE`, and
`UNRESOLVED_REQUIREMENT`.

The committed mask contains exactly 336 entries: every frozen case paired with
every dimension. Each entry independently declares model-score role and
system-credit role. No entry is selected from historical model outcomes or
candidate behavior.

## Mandatory Exceptions

- Garnet is not excluded. Only `CONSTRAINT_SCOPE` is
  `MASKED_UNRESOLVED_CONTRACT`; no later output can unmask it.
- Verde `REFERENCE_PRESENCE` is `RAW_MODEL_DIAGNOSTIC`, while deterministic
  reference removal remains `SYSTEM_CREDIT_BLOCKED` and is never model credit.
- Amber `ANNOTATION` is `PRIMARY_MODEL_OBLIGATION`.
- Iris `ANNOTATION` and `UNRESOLVED_REQUIREMENT` are
  `PRIMARY_MODEL_OBLIGATION`.
- Report presence is a deterministic-boundary obligation and report content is
  model-owned.

The mask is immutable after P0. Its SHA-256 is recorded in
`case_dimension_mask.json` and the pre-live result.
