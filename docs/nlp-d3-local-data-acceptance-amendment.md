# D3 Local External-Data Acceptance Amendment

## Status

`AUTHORIZED / USER-DIRECTED GOVERNANCE AMENDMENT`

Authorization:

```text
WELLPLOT-NLP-D3-DATA-SCOPE-AMEND-002
```

Supersedes only the D3 requirements that real CBL DLIS data be committed, redistributed, provisioned through Git LFS, or made mandatory in clean CI.

It does **not** alter the accepted D3 scientific, architectural, SDK, worker-grounding, one-shot public-path, rendering, or CBL-verifier contracts.

Parent accepted D3 design:

```text
10a0a54509f6f785194fbbe7b039f2aeb5fd1bdf
```

Implementation branch:

```text
delivery/nlp-d3-cbl-construction
```

D4 remains unauthorized.

---

# 1. Governance Decision

D3 is a local external-data integration acceptance.

The real DLIS files remain outside Git and remain ignored by repository source control.

Canonical local inputs:

```text
workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis
workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis
```

Frozen observed identities:

```text
CBL_Main.dlis
size    = 111573216
sha256  = 3ceb9100fd654d710155672a50a9e0f24ce9705db6ef8e424140f29bd02131f7

CBL_Repeat.dlis
size    = 3294924
sha256  = a4a2e91b495172079fc47bc2e9c936f0ab60c9845bbed8e65bf56555a5e82640
```

Both files have already been confirmed to:

```text
parse through wellplot.io.dlis.load_dlis
contain all D3 required scalar channels
contain raster channel VDL
```

No redistribution-rights decision is required because D3 does not redistribute the files.

---

# 2. Explicitly Removed Requirements

The following are no longer D3 requirements:

```text
committing CBL_Main.dlis
committing CBL_Repeat.dlis
Git LFS
.gitattributes changes
fixture redistribution analysis
fixture license/provenance approval for republication
tests/fixtures/agentic_cbl/data/*
clean-clone availability of the real DLIS
CI download/provisioning of the real DLIS
CI changes solely to fetch the real DLIS
CI changes solely to install dlisio for D3
network download during tests
```

Do not add any of these unless separately authorized later.

---

# 3. CI / Local Acceptance Split

D3 now has two evidence classes.

## A. Repository-safe deterministic regressions

These remain ordinary committed tests and must run without the external DLIS files:

```text
SDK grid bridge
raster colorbar bridge
raster sample-axis bridge
existing-track worker projection
sibling-track isolation
grounded target-track enforcement
worker SDK-reference changes
planner/worker structural regressions that do not require real source bytes
```

These belong in normal repository validation and CI.

## B. External-data D3 integrated acceptance

The full one-shot CBL construction test uses the two local gitignored DLIS files.

It is the authoritative D3 integrated acceptance for:

```text
real DLIS loading
real channel grounding
DirectNotebookSession.run()
report + two section workers
merged canonical intent
persistence
real rendering
CBL-01 through CBL-09
```

This acceptance is expected to run locally in the authorized implementation environment.

It is not required to run in a clean checkout lacking the external files.

---

# 4. Integrated Test Missing-Data Behavior

`tests/test_nlp_d3_cbl_construction.py` may be committed.

It must resolve the two canonical local paths relative to repository root.

## Both files absent

If both external files are absent:

```text
SKIP
```

with a precise message equivalent to:

```text
D3 external-data integration skipped: local CBL DLIS fixtures are not present.
```

This is an environment skip, not D3 acceptance.

## Exactly one file present

If one file exists and the other does not:

```text
FAIL
```

Do not silently skip a partially configured D3 environment.

## Both files present

Then the test is mandatory and must:

1. verify exact byte size;
2. verify exact SHA-256;
3. parse both through the real existing DLIS loader;
4. verify required channel inventory;
5. execute the complete D3 one-shot acceptance.

Any hash, parse, channel, render, persistence, worker, or CBL-verifier failure is a real D3 failure.

Do not skip after the files are detected.

---

# 5. Frozen Local Data Identity

Required main file:

```text
workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis
111573216 bytes
3ceb9100fd654d710155672a50a9e0f24ce9705db6ef8e424140f29bd02131f7
```

Required repeat file:

```text
workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis
3294924 bytes
a4a2e91b495172079fc47bc2e9c936f0ab60c9845bbed8e65bf56555a5e82640
```

The integration test may copy those bytes into its temporary project using stable staged basenames:

```text
CBL_Main.dlis
CBL_Repeat.dlis
```

The copied bytes must have identical hashes.

No alternate DLIS source is authorized for D3 without another amendment.

---

# 6. Required Real Channel Contract

When both files are present, each must be inspected through the real source path and expose:

```text
ECGR_STGC
TT
TENS
MTEM
STIT
TDSP
VSEC
CBL
VDL
```

Required kinds:

```text
ECGR_STGC scalar
TT        scalar
TENS      scalar
MTEM      scalar
STIT      scalar
TDSP      scalar
VSEC      scalar
CBL       scalar
VDL       array
```

No fake source inventory is permitted in the integrated D3 test.

---

# 7. Updated Authorized File Boundary

Authorized production files remain:

```text
src/wellplot/authoring_program/intent_builder.py
src/wellplot/agent/code_mode/program_worker.py
```

Authorized lower-level tests:

```text
tests/test_authoring_program_intent_builder.py
tests/test_authoring_program_interpreter.py
tests/test_code_mode_program_worker.py
```

Authorized integrated acceptance and evidence:

```text
tests/test_nlp_d3_cbl_construction.py
docs/nlp-d3-cbl-construction-result.md
```

This amendment document is itself authorized governance evidence:

```text
docs/nlp-d3-local-data-acceptance-amendment.md
```

Not authorized:

```text
.gitattributes
.github/workflows/ci.yml
committed .dlis files
tests/fixtures/agentic_cbl/data/*
production files outside the two listed above
existing D1-D2E acceptance-test modifications
scripts/verify_cbl_packet.py
renderer changes
planner/enrichment/report-worker changes
D4 work
```

---

# 8. One-Shot D3 Contract Remains Unchanged

The integrated local acceptance still requires exactly one:

```python
result = await DirectNotebookSession.run(
    goal=D3_REQUEST,
    output_logfile=output_logfile,
    source_logfile_path=scaffold_logfile,
)
```

No follow-up `revise()`.

No post-run YAML repair.

No direct authoring-service repair.

No fake source loader.

No fake renderer.

Expected graph:

```text
planner calls       = 1
report workers      = 1
section workers     = 2
worker_count        = 3
successful_workers  = 3
failed_workers      = 0
expected repairs    = 0
```

All previously accepted D3 semantic-chain, worker-grounding, VDL, persistence, render, and verifier requirements remain in force.

---

# 9. Result Document Requirements

`docs/nlp-d3-cbl-construction-result.md` must clearly distinguish:

## Local external-data integrated evidence

Record:

```text
data mode:
LOCAL_EXTERNAL_GITIGNORED

main local path:
workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis

main size:
111573216

main SHA-256:
3ceb9100fd654d710155672a50a9e0f24ce9705db6ef8e424140f29bd02131f7

repeat local path:
workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis

repeat size:
3294924

repeat SHA-256:
a4a2e91b495172079fc47bc2e9c936f0ab60c9845bbed8e65bf56555a5e82640

files committed:
NO

source parsing:
PASS

required channels:
PASS
```

Then record the actual one-shot D3 evidence and CBL-01…CBL-09 result.

## Repository/full-suite evidence

If the full repository suite sees the two local files, D3 may run there.

If the environment lacks both files, the D3 integrated test's explicit external-data skip must be counted and classified as:

```text
expected external-data environment skip
```

Do not count such a skip as independent D3 acceptance.

The authoritative D3 acceptance remains the explicit local run that used the frozen real files.

---

# 10. Revised Validation Interpretation

A valid final D3 handoff may therefore contain both:

```text
Local D3 integrated acceptance:
PASS
CBL-01 through CBL-09 PASS
real render PASS
```

and:

```text
Clean/other environment full suite:
D3 integrated test SKIPPED
reason: external gitignored CBL data absent
```

This is not a contradiction.

Lower-level D3 regressions must not depend on the external data and must continue to run normally.

---

# 11. STOP Conditions

STOP if:

```text
both expected local files are not available in the authorized local run

only one local file is present

file size differs

SHA-256 differs

real DLIS parsing fails

required channel/kind is missing

implementation requires committed data

implementation requires Git LFS

implementation requires CI workflow changes

implementation requires another production file

planner/enrichment/report-worker/reconciler/renderer change becomes necessary

one-shot run cannot achieve CBL-01 through CBL-09

real rendering fails

post-run manual repair becomes necessary

provider/model call becomes necessary

D4 work becomes necessary
```

Do not broaden scope automatically.

---

# 12. Governance Decision

```text
WELLPLOT-NLP-D3-DATA-SCOPE-AMEND-002 — AUTHORIZED
```

The previous requirement to redistribute/version the real DLIS files is superseded.

The real CBL files remain:

```text
local
gitignored
uncommitted
identified by fixed size + SHA-256
```

D3 implementation may proceed locally under:

```text
WELLPLOT-NLP-D3-AUTH-001
+
WELLPLOT-NLP-D3-DATA-SCOPE-AMEND-002
```

D4 remains unauthorized.
