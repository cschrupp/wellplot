# S3 Canonical Round-Trip and Mutation Invariants

## Scope

Slice S3 closes remediation issue I03 from the MCP remediation playbook. A
draft accepted by `create_logfile_draft` must be immediately editable through
the same canonical state space used by every later mutation.

## Canonical Persistence Pipeline

Both creation modes and all mutation services now persist through this common
pipeline:

```text
input mapping
  -> rebase paths when creating a draft
  -> normalize between_instances fill references
  -> AuthoringService canonical model
  -> canonical structural validation
  -> canonical document projection
  -> normalize resulting binding ids and fill references
  -> logfile schema and render validation
  -> serialize and write
  -> reload saved YAML
  -> canonical structural validation
  -> render validation
```

The saved file, rather than the pre-write object, is returned to callers.
This prevents creation from accepting a document that its first unrelated edit
would reject.

## Forge Fill Regression

The Forge density-neutron packet contains a local porosity relationship:

```text
NPHI / nphi_overlay
fill.kind = between_instances
fill.other_element_id = rhob_overlay
```

Canonical serialization deduplicates repeated binding ids across sections by
adding a numeric suffix, such as `rhob_overlay.2`. The fill normalizer now
resolves an unambiguous numeric-suffixed local id within the same section and
track. It does not match across sections or tracks and retains the existing
channel-based shorthand path for new fills.

## Coverage

`tests/test_mcp_service.py` now verifies:

- both packaged examples create, serialize, reload, and validate canonically;
- source-logfile cloning also performs the same canonical round trip;
- CBL/VDL mutations cover header, report settings, remarks, section, track,
  curve binding, raster binding, and annotation families using fresh drafts;
- Forge mutations cover header, report settings, remarks, section, track,
  curve binding, annotation, and its applicable fill family;
- the Forge `between_instances` relation survives an unrelated remarks edit;
- repeating the same remarks replacement produces an identical canonical hash.

The broad mutation-family checks mock render validation only so the test
measures the S3 structural invariant without making every structural mutation
pay for DLIS rendering. Creation and the dedicated Forge regression still run
the real render validation. Slice S4 owns separating structural, source, and
render validation in production behavior.

## Evidence

Focused checks passed after implementation:

```text
pytest -q tests/test_mcp_service.py -k packaged_mutation_families_remain_canonical
# 1 passed, 9 subtests passed

pytest -q tests/test_mcp_service.py -k forge_common_mutation_families_remain_canonical
# 1 passed

pytest -q tests/test_mcp_service.py -k 'packaged_examples_create_and_round_trip_canonically or forge_between_instances_fill_survives_unrelated_remarks_mutation'
# 2 passed, 2 subtests passed
```

## Follow-up

S4 must preserve this canonical reload barrier while moving source and render
checks out of structural-only mutations.
