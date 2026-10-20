# D5-5 Comparative Inspection Report

**Authority:** `WELLPLOT-D5-5-COMPARATIVE-INSPECTION-REPORT-AUTH-001`  
**Checkpoint:** `492fe008d6fd84626b87a753270c3dc553809e2d`  
**Scope:** read-only comparison of sealed Qwen and DeepSeek campaigns.  
**Provider/model calls during inspection:** 0

## Executive Comparison

| Turn | Intent | Qwen | DeepSeek | Expected | Main divergence |
|---|---|---:|---:|---|---|
| `D4-C01:C01` | Complete supported CBL/VDL reconstruction | **FAIL** | **FAIL** | DIRECT_CORRECT | CBL verifier and persistence/render evidence incomplete |
| `D4-L01:T1` | Rename this report "Formation Integrity Review". Do not alter the plotted sections. | **FAIL** | **PASS** | DIRECT_CORRECT | title remained unchanged; persistence/render not proven / PASS |
| `D4-L01:T2` | In Main Log, set the Gamma Ray curve to a linear 5–125 scale. Leave its label and styling unchanged. | **PASS** | **PASS** | DIRECT_CORRECT | PASS / PASS |
| `D4-L01:T3` | Append a 30 mm normal track named "Resistivity QC" to Main Log. Plot ILD on it as "Resistivity QC" with a logarithmic 0.2–2000 scale. | **FAIL** | **FAIL** | DIRECT_CORRECT | track and binding requirements failed / track/binding requirements passed; requested scale kind/min/max failed |
| `D4-L01:T4` | On Main Log's GR track, fill from the Gamma Ray curve to its lower scale boundary with #f2e8a0 at 20% opacity; preserve everything else. | **PASS** | **PASS** | DIRECT_CORRECT | PASS / PASS |
| `D4-L02:T1` | In Main Log, change the Gamma Ray curve to a linear 20–110 scale. | **PASS** | **FAIL** | SAFE_ACTIONABLE_FAILURE | PASS / artifact mutated; intent/persistence/render flags became true; no actionable diagnostic |
| `D4-L02:T2` | Apply that 20–110 linear Gamma Ray scale change only to Main Log – Upper. | **PASS** | **FAIL** | CORRECT_AFTER_CLARIFICATION | PASS / before/after preservation and required 20-110 contract failed; earliest divergence is inherited from T1 mutation |
| `D4-L03:C01` | In Main Log, add a 24 mm normal track titled "Neutron QC" and plot NPHI from missing_neutron.las on it with a linear 0–45 scale. | **PASS** | **PASS** | SAFE_ACTIONABLE_FAILURE | PASS / PASS |
| `D4-L04:C01` | In Main Log, add a 24 mm normal track titled "Resistivity Alias QC" and plot RT from "30-23a-3 8117_d.las" on it with a logarithmic 0.2–2000 scale. | **PASS** | **PASS** | SAFE_ACTIONABLE_FAILURE | PASS / PASS |


## Evidence Boundary

The sealed campaign evidence preserves verifier rows, digests, outcomes, diagnostics, artifact hashes, timing, and call counts. It does **not** preserve raw structured model responses or the exact model-facing system/user prompt pair. Therefore:

- Qwen exact/persisted model answers available: **0/9**.
- DeepSeek exact/persisted model answers available: **0/9**.
- Exact model-facing prompts available or deterministically proven reconstructed: **0/9**.
- No model answer is reconstructed from verifier errors.
- The exact frozen user requests below come from `tests/fixtures/nlp_d4_live_cases.json`.
- Exact frozen verifier contracts are included under each turn.

Evidence artifact digests:

- Qwen evidence: `0bcd3c80c6af4c3f4f806541d6708aeea73e99cc00a37111246f7d2a795c03ac`; journal: `8bfd089cd8c378e240eaf567d62b7d41143d082fc0a2a51d36bec66e560cff99`.
- DeepSeek evidence: `85d3394fc1b562ad0df68864b8c4f095198e593b5511c4a2f0f999ef44740aae`; journal: `2cc4bcddd060afaba6bcd7cffd7998c472904f6516d8f1941f45bbc85e032b19`.

## D4-C01:C01

**Workflow:** `CBL-CONSTRUCT`  
**Expected outcome:** `DIRECT_CORRECT`

### 1. User Request

```text
Using CBL_Main.dlis as the main-pass data and CBL_Repeat.dlis as the repeat-pass
data, finish the supported cased-hole CBL/VDL report in the existing scaffold.
Keep the existing section identities main_pass and repeat_pass and limit the
report to the heading, remarks, those two strip sections, and the tail.

Use these service titles, in order: "Cement Bond Log", "Variable Density Log",
and "Gamma Ray - CCL".

Set the report metadata to:
Company University of Utah; well FORGE 16B (78)-32; field Utah Forge; county
Beaver; state Utah; section NWSW 32; township 26; range 9; footage
972' FSL & 523' FWL; latitude 38.501242; longitude -112.882661; logging date
08-May-2023; KB 5445.50 ft; GL 5415.00 ft; DF 5445.00 ft; drilling and log
datum Kelly Bushing; top interval 25.00 ft; bottom interval 4845.00 ft; fluid
Fresh Water; run ONE; driller depth 4980.00 ft; logged depth TD Not Tag;
density 8.4 lbm/gal; maximum temperature 177.2 degF; logged by
D. May / D. Jones; witnessed by Leroy Swearingen.

Include three remarks:
1. Supported Reconstruction Scope — reconstruct only the supported heading,
remarks, main pass, repeat pass, and tail; do not invent unsupported well
diagrams, calibration reports, or vendor parameter tables.
2. Data Sources — use the staged DLIS files for the main and repeat passes.
3. Public Data and IP Notice — keep the WellPlot reproduction boundary explicit
and do not recreate vendor disclaimer artwork.

For each pass, use four tracks from left to right:
combo = normal 50 mm; depth = reference 10 mm; cbl = normal 44 mm;
vdl = array 48 mm.

On combo:
ECGR_STGC → "Gamma Ray (ECGR_STGC) QTGC-B", linear 0..150,
#16a34a, width 0.8.
TT → "Transit Time for CBL (TT) QSLT-B", linear 200..400 reversed,
#2142ff, width 0.75.
TENS → "Cable Tension (TENS)", linear 5000..0, #111111 dashed,
width 0.65.
MTEM → "Mud Temperature (MTEM) LEH-MT", linear 100..500,
#111111, width 0.9.

On depth:
STIT → "Stuck Tool Indicator, Total (STIT)", linear 0..50,
#111111, width 0.65.
TDSP → "Cable Drag", linear 0..50, #92400e dotted, width 0.65.
VSEC → "Tool_Tot. Drag", linear 0..50, #1d4ed8 dashed, width 0.65.

On cbl, plot CBL twice with two different binding identities. Both labels are
"CBL Amplitude (CBL) QSLT-B". The first is linear 0..100, #111111, width 0.75.
The second is linear 0..10, #2563eb dashed, width 0.65.

On vdl, plot VDL as a raster labelled
"VDL VariableDensity (VDL) QSLT-B". Use a linear track scale 200..1200,
profile vdl, gray_r, colorbar enabled with label Amplitude in the header, and
sample axis enabled in us from 200 to 1200 with 7 ticks, source origin 40 and
step 10. Hide both vertical main and secondary grid lines.

Use only channels actually present in the staged sources, preserve the full
labels above, and keep the result restrained and readable.
```

Request SHA256: `5ef3a1e528b2e539dcd895ec09767547151a7706eff911a99cc050c61d7d8f3c`

### 2. What WellPlot Sent to the Model

**EXACT MODEL-FACING PROMPT NOT PRESERVED.** No admissible system/user prompt pair is present in the sealed artifacts, and this report does not approximate one.

Qwen:
```text
source artifact: workspace/evaluations/d5-5/qwen/d5-5-qwen-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 0bcd3c80c6af4c3f4f806541d6708aeea73e99cc00a37111246f7d2a795c03ac
```

DeepSeek:
```text
source artifact: workspace/evaluations/d5-5/deepseek/d5-5-deepseek-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 85d3394fc1b562ad0df68864b8c4f095198e593b5511c4a2f0f999ef44740aae
```

### 3. Qwen Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 4. DeepSeek Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 5. Expected Answer

Complete the supported CBL/VDL report from the two staged DLIS inputs, preserving the named sections and using the requested metadata, remarks, tracks, bindings, scales, styles, and VDL raster settings.

<details>
<summary>Exact frozen verifier contract</summary>

```text
{
  "kind": "cbl",
  "required_verifier_requirements": [
    "CBL-01",
    "CBL-02",
    "CBL-03",
    "CBL-04",
    "CBL-05",
    "CBL-06",
    "CBL-07",
    "CBL-08",
    "CBL-09"
  ]
}
```
</details>

### 6. Difference

| Field | Expected | Qwen | DeepSeek |
|---|---|---|---|
| Semantic result | full CBL report and all nine CBL requirements | CBL-01/02/04/05/06/08/09 failed; persistence/render not proven | CBL-01/02/04/05/06/08 failed; CBL-03/07/09 passed |
| Earliest admissible divergence | Frozen contract | No raw answer is preserved. The first admissible evidence is verifier divergence: the CBL contract fails after the model-mediated construction; no infrastructure failure is recorded. | No raw answer is preserved. The first admissible evidence is verifier divergence: the CBL contract fails after the model-mediated construction; no infrastructure failure is recorded. |

### 7. Deterministic Verifier Outcome

- **Qwen: FAIL**; diagnostics: verifier requirement failed: CBL-01; verifier requirement failed: CBL-02; verifier requirement failed: CBL-04; verifier requirement failed: CBL-05; verifier requirement failed: CBL-06; verifier requirement failed: CBL-08; verifier requirement failed: CBL-09; cbl_persistence_not_proven; cbl_render_not_proven; cbl_rendered_wrong_artifact; cbl_verifier_failed
- **DeepSeek: FAIL**; diagnostics: verifier requirement failed: CBL-01; verifier requirement failed: CBL-02; verifier requirement failed: CBL-04; verifier requirement failed: CBL-05; verifier requirement failed: CBL-06; verifier requirement failed: CBL-08; cbl_verifier_failed
- Persistence/render status is reported separately in the evidence row; it is not treated as the first semantic divergence.

<details>
<summary>Sealed verifier metadata</summary>

Qwen: `{
  "turn_id": "D4-C01:C01",
  "outcome": "FAIL",
  "grader_status": "FAIL",
  "logical_generation_calls": 4,
  "physical_attempts": 4,
  "persisted": false,
  "rendered": false,
  "starting_artifact_sha256": "ef659a71042a06039afddc142d8d6ebb46f30f8d1f40c1c130b60c74778905a1",
  "ending_artifact_sha256": "f1f8f6d1279a910dc06b0efefe889812f5e54ec46549a9844996e9e0c152c6e5",
  "render_sha256": null,
  "verifier_requirements": [
    {
      "id": "CBL-01",
      "status": "FAIL"
    },
    {
      "id": "CBL-02",
      "status": "FAIL"
    },
    {
      "id": "CBL-03",
      "status": "PASS"
    },
    {
      "id": "CBL-04",
      "status": "FAIL"
    },
    {
      "id": "CBL-05",
      "status": "FAIL"
    },
    {
      "id": "CBL-06",
      "status": "FAIL"
    },
    {
      "id": "CBL-07",
      "status": "PASS"
    },
    {
      "id": "CBL-08",
      "status": "FAIL"
    },
    {
      "id": "CBL-09",
      "status": "FAIL"
    }
  ]
}`

DeepSeek: `{
  "turn_id": "D4-C01:C01",
  "outcome": "FAIL",
  "grader_status": "FAIL",
  "logical_generation_calls": 5,
  "physical_attempts": 5,
  "persisted": true,
  "rendered": true,
  "starting_artifact_sha256": "ef659a71042a06039afddc142d8d6ebb46f30f8d1f40c1c130b60c74778905a1",
  "ending_artifact_sha256": "e112cba88afca2e8ac6b92f336b2183fcdf029156d29d220a03d5094b0e5c9d8",
  "render_sha256": "71be559c50cf0234eda2b1e0a3511047fbb34447dd3722ab20cd9267e8449d11",
  "verifier_requirements": [
    {
      "id": "CBL-01",
      "status": "FAIL"
    },
    {
      "id": "CBL-02",
      "status": "FAIL"
    },
    {
      "id": "CBL-03",
      "status": "PASS"
    },
    {
      "id": "CBL-04",
      "status": "FAIL"
    },
    {
      "id": "CBL-05",
      "status": "FAIL"
    },
    {
      "id": "CBL-06",
      "status": "FAIL"
    },
    {
      "id": "CBL-07",
      "status": "PASS"
    },
    {
      "id": "CBL-08",
      "status": "FAIL"
    },
    {
      "id": "CBL-09",
      "status": "PASS"
    }
  ]
}`

</details>

## D4-L01:T1

**Workflow:** `LAS-REVISE`  
**Expected outcome:** `DIRECT_CORRECT`

### 1. User Request

```text
Rename this report "Formation Integrity Review". Do not alter the plotted sections.
```

Request SHA256: `0ffe99d4e0131f2649370730e913cd5147f73dccff24ed0f2d1ce928b2f41a34`

### 2. What WellPlot Sent to the Model

**EXACT MODEL-FACING PROMPT NOT PRESERVED.** No admissible system/user prompt pair is present in the sealed artifacts, and this report does not approximate one.

Qwen:
```text
source artifact: workspace/evaluations/d5-5/qwen/d5-5-qwen-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 0bcd3c80c6af4c3f4f806541d6708aeea73e99cc00a37111246f7d2a795c03ac
```

DeepSeek:
```text
source artifact: workspace/evaluations/d5-5/deepseek/d5-5-deepseek-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 85d3394fc1b562ad0df68864b8c4f095198e593b5511c4a2f0f999ef44740aae
```

### 3. Qwen Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 4. DeepSeek Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 5. Expected Answer

Rename the report to "Formation Integrity Review"; make no plotted-section changes.

<details>
<summary>Exact frozen verifier contract</summary>

```text
{
  "kind": "las",
  "required_verifier_requirements": [
    "LAS-01",
    "LAS-02",
    "LAS-07",
    "LAS-09"
  ],
  "before_assertions": [
    {
      "path": "/title",
      "operator": "equals",
      "value": "Original Well Log Report"
    }
  ],
  "after_assertions": [
    {
      "path": "/title",
      "operator": "equals",
      "value": "Formation Integrity Review"
    }
  ],
  "required_changes": {
    "LAS-02": {
      "before": [
        {
          "path": "/title",
          "operator": "equals",
          "value": "Original Well Log Report"
        }
      ],
      "after": [
        {
          "path": "/title",
          "operator": "equals",
          "value": "Formation Integrity Review"
        }
      ]
    }
  },
  "required_change_paths": [
    "/title"
  ],
  "allowed_change_paths": [
    "/title",
    "/extensions/compatibility/legacy_document/header/title"
  ]
}
```
</details>

### 6. Difference

| Field | Expected | Qwen | DeepSeek |
|---|---|---|---|
| Semantic result | title changed; sections preserved | title remained unchanged; persistence/render not proven | PASS |
| Earliest admissible divergence | Frozen contract | Qwen: title change is absent in the graded after-state. DeepSeek: no semantic divergence is recorded. | Qwen: title change is absent in the graded after-state. DeepSeek: no semantic divergence is recorded. |

### 7. Deterministic Verifier Outcome

- **Qwen: FAIL**; diagnostics: verifier requirement failed: LAS-02; verifier requirement failed: LAS-09; after_assertion_failed: /title; required_scientific_change_missing; persistence_not_proven; render_not_proven; verifier_failed
- **DeepSeek: PASS**; diagnostics: none
- Persistence/render status is reported separately in the evidence row; it is not treated as the first semantic divergence.

<details>
<summary>Sealed verifier metadata</summary>

Qwen: `{
  "turn_id": "D4-L01:T1",
  "outcome": "FAIL",
  "grader_status": "FAIL",
  "logical_generation_calls": 3,
  "physical_attempts": 3,
  "persisted": false,
  "rendered": false,
  "starting_artifact_sha256": "fb20891eba8b072cd86c815970213a3a72623e08de9c9181a6be323b080a2c93",
  "ending_artifact_sha256": "fb20891eba8b072cd86c815970213a3a72623e08de9c9181a6be323b080a2c93",
  "render_sha256": null,
  "verifier_requirements": [
    {
      "id": "LAS-01",
      "status": "PASS"
    },
    {
      "id": "LAS-02",
      "status": "FAIL"
    },
    {
      "id": "LAS-03",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-04",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-05",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-06",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-07",
      "status": "PASS"
    },
    {
      "id": "LAS-08",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-09",
      "status": "FAIL"
    }
  ]
}`

DeepSeek: `{
  "turn_id": "D4-L01:T1",
  "outcome": "PASS",
  "grader_status": "PASS",
  "logical_generation_calls": 2,
  "physical_attempts": 2,
  "persisted": true,
  "rendered": true,
  "starting_artifact_sha256": "fb20891eba8b072cd86c815970213a3a72623e08de9c9181a6be323b080a2c93",
  "ending_artifact_sha256": "f92bdf2a0b5df8a87d4a02d2dd252e657fde872767181f44a1564edb9910af02",
  "render_sha256": "0993cc5b79af445021272fad7499ac9cbb7d5e7e4b5bc9d2dd5d98b3eb9436ba",
  "verifier_requirements": [
    {
      "id": "LAS-01",
      "status": "PASS"
    },
    {
      "id": "LAS-02",
      "status": "PASS"
    },
    {
      "id": "LAS-03",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-04",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-05",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-06",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-07",
      "status": "PASS"
    },
    {
      "id": "LAS-08",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-09",
      "status": "PASS"
    }
  ]
}`

</details>

## D4-L01:T2

**Workflow:** `LAS-REVISE`  
**Expected outcome:** `DIRECT_CORRECT`

### 1. User Request

```text
In Main Log, set the Gamma Ray curve to a linear 5–125 scale. Leave its label and styling unchanged.
```

Request SHA256: `866ff67469139034c2062f1c668283c5532d0fc69fd711ed8e55e6c71d12d5f8`

### 2. What WellPlot Sent to the Model

**EXACT MODEL-FACING PROMPT NOT PRESERVED.** No admissible system/user prompt pair is present in the sealed artifacts, and this report does not approximate one.

Qwen:
```text
source artifact: workspace/evaluations/d5-5/qwen/d5-5-qwen-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 0bcd3c80c6af4c3f4f806541d6708aeea73e99cc00a37111246f7d2a795c03ac
```

DeepSeek:
```text
source artifact: workspace/evaluations/d5-5/deepseek/d5-5-deepseek-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 85d3394fc1b562ad0df68864b8c4f095198e593b5511c4a2f0f999ef44740aae
```

### 3. Qwen Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 4. DeepSeek Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 5. Expected Answer

Set Main Log Gamma Ray to linear 5-125 while preserving label and styling.

<details>
<summary>Exact frozen verifier contract</summary>

```text
{
  "kind": "las",
  "required_verifier_requirements": [
    "LAS-01",
    "LAS-05",
    "LAS-07",
    "LAS-09"
  ],
  "before_assertions": [
    {
      "path": "/sections/0/tracks/1/bindings/0/scale/kind",
      "operator": "equals",
      "value": "linear"
    },
    {
      "path": "/sections/0/tracks/1/bindings/0/scale/minimum",
      "operator": "equals",
      "value": 0
    }
  ],
  "after_assertions": [
    {
      "path": "/sections/0/tracks/1/bindings/0/scale/kind",
      "operator": "equals",
      "value": "linear"
    },
    {
      "path": "/sections/0/tracks/1/bindings/0/scale/minimum",
      "operator": "equals",
      "value": 5
    },
    {
      "path": "/sections/0/tracks/1/bindings/0/scale/maximum",
      "operator": "equals",
      "value": 125
    }
  ],
  "required_changes": {
    "LAS-05": {
      "before": [
        {
          "path": "/sections/0/tracks/1/bindings/0/scale/kind",
          "operator": "equals",
          "value": "linear"
        },
        {
          "path": "/sections/0/tracks/1/bindings/0/scale/minimum",
          "operator": "equals",
          "value": 0
        }
      ],
      "after": [
        {
          "path": "/sections/0/tracks/1/bindings/0/scale/kind",
          "operator": "equals",
          "value": "linear"
        },
        {
          "path": "/sections/0/tracks/1/bindings/0/scale/minimum",
          "operator": "equals",
          "value": 5
        },
        {
          "path": "/sections/0/tracks/1/bindings/0/scale/maximum",
          "operator": "equals",
          "value": 125
        }
      ]
    }
  },
  "required_change_paths": [
    "/sections/0/tracks/1/bindings/0/scale"
  ],
  "allowed_change_paths": [
    "/sections/0/tracks/1/bindings/0/scale",
    "/extensions/compatibility/legacy_document/bindings/channels/0/scale",
    "/sections/0/tracks/1/bindings/0/extensions/compatibility/legacy_binding/scale"
  ]
}
```
</details>

### 6. Difference

| Field | Expected | Qwen | DeepSeek |
|---|---|---|---|
| Semantic result | linear 5-125 scale | PASS | PASS |
| Earliest admissible divergence | Frozen contract | Both lanes reach the requested scale and pass the deterministic contract. | Both lanes reach the requested scale and pass the deterministic contract. |

### 7. Deterministic Verifier Outcome

- **Qwen: PASS**; diagnostics: none
- **DeepSeek: PASS**; diagnostics: none
- Persistence/render status is reported separately in the evidence row; it is not treated as the first semantic divergence.

<details>
<summary>Sealed verifier metadata</summary>

Qwen: `{
  "turn_id": "D4-L01:T2",
  "outcome": "PASS",
  "grader_status": "PASS",
  "logical_generation_calls": 2,
  "physical_attempts": 2,
  "persisted": true,
  "rendered": true,
  "starting_artifact_sha256": "fb20891eba8b072cd86c815970213a3a72623e08de9c9181a6be323b080a2c93",
  "ending_artifact_sha256": "c2ecd653f7ad33d5caf37fd7898703e362f7adb41ed4b856c99838ba8d9acace",
  "render_sha256": "346213b6a6012058a1f098745fc0025c4d69bf0949f775fa1a81c06ba73f744e",
  "verifier_requirements": [
    {
      "id": "LAS-01",
      "status": "PASS"
    },
    {
      "id": "LAS-02",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-03",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-04",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-05",
      "status": "PASS"
    },
    {
      "id": "LAS-06",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-07",
      "status": "PASS"
    },
    {
      "id": "LAS-08",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-09",
      "status": "PASS"
    }
  ]
}`

DeepSeek: `{
  "turn_id": "D4-L01:T2",
  "outcome": "PASS",
  "grader_status": "PASS",
  "logical_generation_calls": 2,
  "physical_attempts": 2,
  "persisted": true,
  "rendered": true,
  "starting_artifact_sha256": "f92bdf2a0b5df8a87d4a02d2dd252e657fde872767181f44a1564edb9910af02",
  "ending_artifact_sha256": "1af501b982b1d5fc29d30242783c268a41626c2c6e3fd0a0fc45ac85a9ab9f2c",
  "render_sha256": "b204b82016790ce58419a4c768dd99dd96cc922a29abdf60db28a09ee7715d6d",
  "verifier_requirements": [
    {
      "id": "LAS-01",
      "status": "PASS"
    },
    {
      "id": "LAS-02",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-03",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-04",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-05",
      "status": "PASS"
    },
    {
      "id": "LAS-06",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-07",
      "status": "PASS"
    },
    {
      "id": "LAS-08",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-09",
      "status": "PASS"
    }
  ]
}`

</details>

## D4-L01:T3

**Workflow:** `LAS-REVISE`  
**Expected outcome:** `DIRECT_CORRECT`

### 1. User Request

```text
Append a 30 mm normal track named "Resistivity QC" to Main Log. Plot ILD on it as "Resistivity QC" with a logarithmic 0.2–2000 scale.
```

Request SHA256: `49405cb494cc3cead9cc015c99ef6e0e048583d716be3421930c39d995b95136`

### 2. What WellPlot Sent to the Model

**EXACT MODEL-FACING PROMPT NOT PRESERVED.** No admissible system/user prompt pair is present in the sealed artifacts, and this report does not approximate one.

Qwen:
```text
source artifact: workspace/evaluations/d5-5/qwen/d5-5-qwen-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 0bcd3c80c6af4c3f4f806541d6708aeea73e99cc00a37111246f7d2a795c03ac
```

DeepSeek:
```text
source artifact: workspace/evaluations/d5-5/deepseek/d5-5-deepseek-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 85d3394fc1b562ad0df68864b8c4f095198e593b5511c4a2f0f999ef44740aae
```

### 3. Qwen Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 4. DeepSeek Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 5. Expected Answer

Append a 30 mm normal "Resistivity QC" track to Main Log; bind ILD with the requested label and logarithmic 0.2-2000 scale.

<details>
<summary>Exact frozen verifier contract</summary>

```text
{
  "kind": "las",
  "required_verifier_requirements": [
    "LAS-01",
    "LAS-03",
    "LAS-07",
    "LAS-09"
  ],
  "before_assertions": [
    {
      "path": "/sections/0/tracks",
      "operator": "length_at_least",
      "value": 3
    }
  ],
  "after_assertions": [
    {
      "path": "/sections/0/tracks/3/title",
      "operator": "equals",
      "value": "Resistivity QC"
    },
    {
      "path": "/sections/0/tracks/3/kind",
      "operator": "equals",
      "value": "normal"
    },
    {
      "path": "/sections/0/tracks/3/width_mm",
      "operator": "equals",
      "value": 30
    },
    {
      "path": "/sections/0/tracks/3/bindings/0/label",
      "operator": "equals",
      "value": "Resistivity QC"
    },
    {
      "path": "/sections/0/tracks/3/bindings/0/channel",
      "operator": "equals",
      "value": "ILD"
    },
    {
      "path": "/sections/0/tracks/3/bindings/0/scale/kind",
      "operator": "equals",
      "value": "log"
    },
    {
      "path": "/sections/0/tracks/3/bindings/0/scale/minimum",
      "operator": "equals",
      "value": 0.2
    },
    {
      "path": "/sections/0/tracks/3/bindings/0/scale/maximum",
      "operator": "equals",
      "value": 2000
    }
  ],
  "required_changes": {
    "LAS-03": {
      "before": [
        {
          "path": "/sections/0/tracks",
          "operator": "length_at_least",
          "value": 3
        }
      ],
      "after": [
        {
          "path": "/sections/0/tracks/3/title",
          "operator": "equals",
          "value": "Resistivity QC"
        },
        {
          "path": "/sections/0/tracks/3/kind",
          "operator": "equals",
          "value": "normal"
        },
        {
          "path": "/sections/0/tracks/3/width_mm",
          "operator": "equals",
          "value": 30
        },
        {
          "path": "/sections/0/tracks/3/bindings/0/label",
          "operator": "equals",
          "value": "Resistivity QC"
        },
        {
          "path": "/sections/0/tracks/3/bindings/0/channel",
          "operator": "equals",
          "value": "ILD"
        },
        {
          "path": "/sections/0/tracks/3/bindings/0/scale/kind",
          "operator": "equals",
          "value": "log"
        },
        {
          "path": "/sections/0/tracks/3/bindings/0/scale/minimum",
          "operator": "equals",
          "value": 0.2
        },
        {
          "path": "/sections/0/tracks/3/bindings/0/scale/maximum",
          "operator": "equals",
          "value": 2000
        }
      ]
    }
  },
  "required_change_paths": [
    "/sections/0/tracks/3"
  ],
  "allowed_change_paths": [
    "/sections/0/tracks/3",
    "/extensions/compatibility/legacy_document/bindings/channels/2",
    "/extensions/compatibility/legacy_document/layout/log_sections/0/tracks/3"
  ]
}
```
</details>

### 6. Difference

| Field | Expected | Qwen | DeepSeek |
|---|---|---|---|
| Semantic result | new normal 30 mm track, ILD binding, log 0.2-2000 | track and binding requirements failed | track/binding requirements passed; requested scale kind/min/max failed |
| Earliest admissible divergence | Frozen contract | Qwen: the new track/binding semantic object is absent or incomplete. DeepSeek: the track/binding exists, but its scale kind/minimum/maximum do not match. | Qwen: the new track/binding semantic object is absent or incomplete. DeepSeek: the track/binding exists, but its scale kind/minimum/maximum do not match. |

### 7. Deterministic Verifier Outcome

- **Qwen: FAIL**; diagnostics: verifier requirement failed: LAS-03; verifier requirement failed: LAS-09; after_assertion_failed: /sections/0/tracks/3/title; after_assertion_failed: /sections/0/tracks/3/kind; after_assertion_failed: /sections/0/tracks/3/width_mm; after_assertion_failed: /sections/0/tracks/3/bindings/0/label; after_assertion_failed: /sections/0/tracks/3/bindings/0/channel; after_assertion_failed: /sections/0/tracks/3/bindings/0/scale/kind; after_assertion_failed: /sections/0/tracks/3/bindings/0/scale/minimum; after_assertion_failed: /sections/0/tracks/3/bindings/0/scale/maximum; required_scientific_change_missing; persistence_not_proven; render_not_proven; verifier_failed
- **DeepSeek: FAIL**; diagnostics: verifier requirement failed: LAS-03; after_assertion_failed: /sections/0/tracks/3/bindings/0/scale/kind; after_assertion_failed: /sections/0/tracks/3/bindings/0/scale/minimum; after_assertion_failed: /sections/0/tracks/3/bindings/0/scale/maximum; verifier_failed
- Persistence/render status is reported separately in the evidence row; it is not treated as the first semantic divergence.

<details>
<summary>Sealed verifier metadata</summary>

Qwen: `{
  "turn_id": "D4-L01:T3",
  "outcome": "FAIL",
  "grader_status": "FAIL",
  "logical_generation_calls": 2,
  "physical_attempts": 2,
  "persisted": false,
  "rendered": false,
  "starting_artifact_sha256": "c2ecd653f7ad33d5caf37fd7898703e362f7adb41ed4b856c99838ba8d9acace",
  "ending_artifact_sha256": "c2ecd653f7ad33d5caf37fd7898703e362f7adb41ed4b856c99838ba8d9acace",
  "render_sha256": null,
  "verifier_requirements": [
    {
      "id": "LAS-01",
      "status": "PASS"
    },
    {
      "id": "LAS-02",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-03",
      "status": "FAIL"
    },
    {
      "id": "LAS-04",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-05",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-06",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-07",
      "status": "PASS"
    },
    {
      "id": "LAS-08",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-09",
      "status": "FAIL"
    }
  ]
}`

DeepSeek: `{
  "turn_id": "D4-L01:T3",
  "outcome": "FAIL",
  "grader_status": "FAIL",
  "logical_generation_calls": 2,
  "physical_attempts": 2,
  "persisted": true,
  "rendered": true,
  "starting_artifact_sha256": "1af501b982b1d5fc29d30242783c268a41626c2c6e3fd0a0fc45ac85a9ab9f2c",
  "ending_artifact_sha256": "f4b3c65a5f667ef6178145ad0394dfd42fff206ae5abe33df06a7b5250c5aa14",
  "render_sha256": "e4714860323ca4b250ed5d4811f9fae656a11854e2d3812b3fab8eda7d514233",
  "verifier_requirements": [
    {
      "id": "LAS-01",
      "status": "PASS"
    },
    {
      "id": "LAS-02",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-03",
      "status": "FAIL"
    },
    {
      "id": "LAS-04",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-05",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-06",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-07",
      "status": "PASS"
    },
    {
      "id": "LAS-08",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-09",
      "status": "PASS"
    }
  ]
}`

</details>

## D4-L01:T4

**Workflow:** `LAS-REVISE`  
**Expected outcome:** `DIRECT_CORRECT`

### 1. User Request

```text
On Main Log's GR track, fill from the Gamma Ray curve to its lower scale boundary with #f2e8a0 at 20% opacity; preserve everything else.
```

Request SHA256: `0819dd6cb0964cc61752c96682aa4fa2b8924c6a47bb57e7897bd0b5ec52557b`

### 2. What WellPlot Sent to the Model

**EXACT MODEL-FACING PROMPT NOT PRESERVED.** No admissible system/user prompt pair is present in the sealed artifacts, and this report does not approximate one.

Qwen:
```text
source artifact: workspace/evaluations/d5-5/qwen/d5-5-qwen-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 0bcd3c80c6af4c3f4f806541d6708aeea73e99cc00a37111246f7d2a795c03ac
```

DeepSeek:
```text
source artifact: workspace/evaluations/d5-5/deepseek/d5-5-deepseek-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 85d3394fc1b562ad0df68864b8c4f095198e593b5511c4a2f0f999ef44740aae
```

### 3. Qwen Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 4. DeepSeek Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 5. Expected Answer

Add the specified lower-limit fill on Main Log GR and preserve all other state.

<details>
<summary>Exact frozen verifier contract</summary>

```text
{
  "kind": "las",
  "required_verifier_requirements": [
    "LAS-01",
    "LAS-06",
    "LAS-07",
    "LAS-09"
  ],
  "before_assertions": [
    {
      "path": "/sections/0/tracks/1/fills",
      "operator": "length_at_least",
      "value": 0
    }
  ],
  "after_assertions": [
    {
      "path": "/sections/0/tracks/1/fills/0/kind",
      "operator": "equals",
      "value": "to_lower_limit"
    },
    {
      "path": "/sections/0/tracks/1/fills/0/binding_id",
      "operator": "equals",
      "value": "main.gr.GR.1"
    },
    {
      "path": "/sections/0/tracks/1/fills/0/color",
      "operator": "equals",
      "value": "#f2e8a0"
    },
    {
      "path": "/sections/0/tracks/1/fills/0/alpha",
      "operator": "equals",
      "value": 0.2
    }
  ],
  "required_changes": {
    "LAS-06": {
      "before": [
        {
          "path": "/sections/0/tracks/1/fills",
          "operator": "length_at_least",
          "value": 0
        }
      ],
      "after": [
        {
          "path": "/sections/0/tracks/1/fills/0/kind",
          "operator": "equals",
          "value": "to_lower_limit"
        },
        {
          "path": "/sections/0/tracks/1/fills/0/binding_id",
          "operator": "equals",
          "value": "main.gr.GR.1"
        },
        {
          "path": "/sections/0/tracks/1/fills/0/color",
          "operator": "equals",
          "value": "#f2e8a0"
        },
        {
          "path": "/sections/0/tracks/1/fills/0/alpha",
          "operator": "equals",
          "value": 0.2
        }
      ]
    }
  },
  "required_change_paths": [
    "/sections/0/tracks/1/fills/0"
  ],
  "allowed_change_paths": [
    "/sections/0/tracks/1/fills/0",
    "/extensions/compatibility/legacy_document/bindings/channels/0/fill",
    "/sections/0/tracks/1/bindings/0/extensions/compatibility/legacy_binding/fill"
  ]
}
```
</details>

### 6. Difference

| Field | Expected | Qwen | DeepSeek |
|---|---|---|---|
| Semantic result | fill main.gr.GR.1, #f2e8a0, alpha 0.2 | PASS | PASS |
| Earliest admissible divergence | Frozen contract | Both lanes reach the requested fill contract and pass. | Both lanes reach the requested fill contract and pass. |

### 7. Deterministic Verifier Outcome

- **Qwen: PASS**; diagnostics: none
- **DeepSeek: PASS**; diagnostics: none
- Persistence/render status is reported separately in the evidence row; it is not treated as the first semantic divergence.

<details>
<summary>Sealed verifier metadata</summary>

Qwen: `{
  "turn_id": "D4-L01:T4",
  "outcome": "PASS",
  "grader_status": "PASS",
  "logical_generation_calls": 2,
  "physical_attempts": 2,
  "persisted": true,
  "rendered": true,
  "starting_artifact_sha256": "c2ecd653f7ad33d5caf37fd7898703e362f7adb41ed4b856c99838ba8d9acace",
  "ending_artifact_sha256": "d1cf707d1d471d4167b9c4c293ca0b77e3a64ffbd6fdc5f500eafdf886e9f9d4",
  "render_sha256": "3eb5d630aec2fc1080a75529099085ff28fce4fa4050deb8f7df231f73a8987d",
  "verifier_requirements": [
    {
      "id": "LAS-01",
      "status": "PASS"
    },
    {
      "id": "LAS-02",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-03",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-04",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-05",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-06",
      "status": "PASS"
    },
    {
      "id": "LAS-07",
      "status": "PASS"
    },
    {
      "id": "LAS-08",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-09",
      "status": "PASS"
    }
  ]
}`

DeepSeek: `{
  "turn_id": "D4-L01:T4",
  "outcome": "PASS",
  "grader_status": "PASS",
  "logical_generation_calls": 2,
  "physical_attempts": 2,
  "persisted": true,
  "rendered": true,
  "starting_artifact_sha256": "f4b3c65a5f667ef6178145ad0394dfd42fff206ae5abe33df06a7b5250c5aa14",
  "ending_artifact_sha256": "f294403cd02117f6ef9cbfa6d1400238b770b8f9b18e5a070710da4d24e6bdb6",
  "render_sha256": "603b2007d1fc03cee06889b973e5287bf98f2a35dc450b8ceebf9eec9fa930d4",
  "verifier_requirements": [
    {
      "id": "LAS-01",
      "status": "PASS"
    },
    {
      "id": "LAS-02",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-03",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-04",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-05",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-06",
      "status": "PASS"
    },
    {
      "id": "LAS-07",
      "status": "PASS"
    },
    {
      "id": "LAS-08",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-09",
      "status": "PASS"
    }
  ]
}`

</details>

## D4-L02:T1

**Workflow:** `LAS-REVISE`  
**Expected outcome:** `SAFE_ACTIONABLE_FAILURE`

### 1. User Request

```text
In Main Log, change the Gamma Ray curve to a linear 20–110 scale.
```

Request SHA256: `6bc23defbb254104f567c7a3c2caf33b77ad06f6d0dd124c3dc9b796f3fda541`

### 2. What WellPlot Sent to the Model

**EXACT MODEL-FACING PROMPT NOT PRESERVED.** No admissible system/user prompt pair is present in the sealed artifacts, and this report does not approximate one.

Qwen:
```text
source artifact: workspace/evaluations/d5-5/qwen/d5-5-qwen-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 0bcd3c80c6af4c3f4f806541d6708aeea73e99cc00a37111246f7d2a795c03ac
```

DeepSeek:
```text
source artifact: workspace/evaluations/d5-5/deepseek/d5-5-deepseek-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 85d3394fc1b562ad0df68864b8c4f095198e593b5511c4a2f0f999ef44740aae
```

### 3. Qwen Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 4. DeepSeek Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 5. Expected Answer

Reject the underspecified 20-110 Gamma Ray request safely: no intent, mutation, persistence, or render.

<details>
<summary>Exact frozen verifier contract</summary>

```text
{
  "kind": "safety",
  "required_false_flags": [
    "intent_applied",
    "persisted",
    "rendered"
  ],
  "prohibited_paths": [
    "/sections",
    "/title",
    "/remarks"
  ]
}
```
</details>

### 6. Difference

| Field | Expected | Qwen | DeepSeek |
|---|---|---|---|
| Semantic result | safe actionable rejection with unchanged artifact | PASS | artifact mutated; intent/persistence/render flags became true; no actionable diagnostic |
| Earliest admissible divergence | Frozen contract | DeepSeek: the safety boundary is crossed first: the artifact bytes/canonical state changed and intent was applied; the missing diagnostic is secondary. Qwen remains a safe rejection. | DeepSeek: the safety boundary is crossed first: the artifact bytes/canonical state changed and intent was applied; the missing diagnostic is secondary. Qwen remains a safe rejection. |

### 7. Deterministic Verifier Outcome

- **Qwen: PASS**; diagnostics: none
- **DeepSeek: FAIL**; diagnostics: failure_mutated_artifact; failure_bytes_changed; missing_actionable_diagnostic; failure_canonical_state_changed; failure_applied_intent; failure_flag_not_false: intent_applied; failure_flag_not_false: persisted; failure_flag_not_false: rendered
- Persistence/render status is reported separately in the evidence row; it is not treated as the first semantic divergence.

<details>
<summary>Sealed verifier metadata</summary>

Qwen: `{
  "turn_id": "D4-L02:T1",
  "outcome": "PASS",
  "grader_status": "PASS",
  "logical_generation_calls": 2,
  "physical_attempts": 2,
  "persisted": false,
  "rendered": false,
  "starting_artifact_sha256": "35a3e93efbae52ba3e6fd3afb3b78b2f3315af4ba53906f9d62d8d4ae9a342e5",
  "ending_artifact_sha256": "35a3e93efbae52ba3e6fd3afb3b78b2f3315af4ba53906f9d62d8d4ae9a342e5",
  "render_sha256": null,
  "verifier_requirements": []
}`

DeepSeek: `{
  "turn_id": "D4-L02:T1",
  "outcome": "FAIL",
  "grader_status": "FAIL",
  "logical_generation_calls": 3,
  "physical_attempts": 3,
  "persisted": true,
  "rendered": true,
  "starting_artifact_sha256": "35a3e93efbae52ba3e6fd3afb3b78b2f3315af4ba53906f9d62d8d4ae9a342e5",
  "ending_artifact_sha256": "6e88e1dc0032b569ff8e136cf7c6cf6b27b98cc2057f9c88af27b28a51c666e5",
  "render_sha256": "3f4dde78fca06160bf54b9bd8e96309e5936ae47f3cd5e2d67805258d409a9cc",
  "verifier_requirements": []
}`

</details>

## D4-L02:T2

**Workflow:** `LAS-REVISE`  
**Expected outcome:** `CORRECT_AFTER_CLARIFICATION`

### 1. User Request

```text
Apply that 20–110 linear Gamma Ray scale change only to Main Log – Upper.
```

Request SHA256: `eee91c864757d6a4d8f23d906928964318868c8063f5e61e3afba4c794ee32c9`

### 2. What WellPlot Sent to the Model

**EXACT MODEL-FACING PROMPT NOT PRESERVED.** No admissible system/user prompt pair is present in the sealed artifacts, and this report does not approximate one.

Qwen:
```text
source artifact: workspace/evaluations/d5-5/qwen/d5-5-qwen-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 0bcd3c80c6af4c3f4f806541d6708aeea73e99cc00a37111246f7d2a795c03ac
```

DeepSeek:
```text
source artifact: workspace/evaluations/d5-5/deepseek/d5-5-deepseek-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 85d3394fc1b562ad0df68864b8c4f095198e593b5511c4a2f0f999ef44740aae
```

### 3. Qwen Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 4. DeepSeek Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 5. Expected Answer

Apply 20-110 only to Main Log - Upper; preserve the other section at its existing 0-100 scale.

<details>
<summary>Exact frozen verifier contract</summary>

```text
{
  "kind": "las",
  "required_verifier_requirements": [
    "LAS-01",
    "LAS-05",
    "LAS-07",
    "LAS-09"
  ],
  "before_assertions": [
    {
      "path": "/sections/1/tracks/1/bindings/0/scale/kind",
      "operator": "equals",
      "value": "linear"
    },
    {
      "path": "/sections/1/tracks/1/bindings/0/scale/minimum",
      "operator": "equals",
      "value": 0
    }
  ],
  "after_assertions": [
    {
      "path": "/sections/0/tracks/1/bindings/0/scale/kind",
      "operator": "equals",
      "value": "linear"
    },
    {
      "path": "/sections/0/tracks/1/bindings/0/scale/minimum",
      "operator": "equals",
      "value": 20
    },
    {
      "path": "/sections/0/tracks/1/bindings/0/scale/maximum",
      "operator": "equals",
      "value": 110
    },
    {
      "path": "/sections/1/tracks/1/bindings/0/scale/kind",
      "operator": "equals",
      "value": "linear"
    },
    {
      "path": "/sections/1/tracks/1/bindings/0/scale/minimum",
      "operator": "equals",
      "value": 0
    },
    {
      "path": "/sections/1/tracks/1/bindings/0/scale/maximum",
      "operator": "equals",
      "value": 100
    }
  ],
  "required_changes": {
    "LAS-05": {
      "before": [
        {
          "path": "/sections/1/tracks/1/bindings/0/scale/kind",
          "operator": "equals",
          "value": "linear"
        },
        {
          "path": "/sections/1/tracks/1/bindings/0/scale/minimum",
          "operator": "equals",
          "value": 0
        }
      ],
      "after": [
        {
          "path": "/sections/0/tracks/1/bindings/0/scale/kind",
          "operator": "equals",
          "value": "linear"
        },
        {
          "path": "/sections/0/tracks/1/bindings/0/scale/minimum",
          "operator": "equals",
          "value": 20
        },
        {
          "path": "/sections/0/tracks/1/bindings/0/scale/maximum",
          "operator": "equals",
          "value": 110
        },
        {
          "path": "/sections/1/tracks/1/bindings/0/scale/kind",
          "operator": "equals",
          "value": "linear"
        },
        {
          "path": "/sections/1/tracks/1/bindings/0/scale/minimum",
          "operator": "equals",
          "value": 0
        },
        {
          "path": "/sections/1/tracks/1/bindings/0/scale/maximum",
          "operator": "equals",
          "value": 100
        }
      ]
    }
  },
  "required_change_paths": [
    "/sections/0/tracks/1/bindings/0/scale"
  ],
  "allowed_change_paths": [
    "/sections/0/tracks/1/bindings/0/scale",
    "/extensions/compatibility/legacy_document/bindings/channels/0/scale",
    "/sections/0/tracks/1/bindings/0/extensions/compatibility/legacy_binding/scale",
    "/extensions/compatibility/legacy_document/layout/log_sections/0/tracks/1",
    "/sections/0/tracks/1/extensions/compatibility/legacy_track"
  ]
}
```
</details>

### 6. Difference

| Field | Expected | Qwen | DeepSeek |
|---|---|---|---|
| Semantic result | only Upper changes to 20-110; other section remains 0-100 | PASS | before/after preservation and required 20-110 contract failed; earliest divergence is inherited from T1 mutation |
| Earliest admissible divergence | Frozen contract | DeepSeek: this turn begins from the state mutated by T1, so the required before-state and preserved Upper section no longer match. Qwen passes. | DeepSeek: this turn begins from the state mutated by T1, so the required before-state and preserved Upper section no longer match. Qwen passes. |

### 7. Deterministic Verifier Outcome

- **Qwen: PASS**; diagnostics: none
- **DeepSeek: FAIL**; diagnostics: verifier requirement failed: LAS-01; verifier requirement failed: LAS-05; before_assertion_failed: /sections/1/tracks/1/bindings/0/scale/minimum; after_assertion_failed: /sections/1/tracks/1/bindings/0/scale/minimum; after_assertion_failed: /sections/1/tracks/1/bindings/0/scale/maximum; required_scientific_change_missing; verifier_failed
- Persistence/render status is reported separately in the evidence row; it is not treated as the first semantic divergence.

<details>
<summary>Sealed verifier metadata</summary>

Qwen: `{
  "turn_id": "D4-L02:T2",
  "outcome": "PASS",
  "grader_status": "PASS",
  "logical_generation_calls": 2,
  "physical_attempts": 2,
  "persisted": true,
  "rendered": true,
  "starting_artifact_sha256": "35a3e93efbae52ba3e6fd3afb3b78b2f3315af4ba53906f9d62d8d4ae9a342e5",
  "ending_artifact_sha256": "587c3b44a798a45d8f38f75c3542787efc79186c21890230f7c7fe0c87103818",
  "render_sha256": "35fd16348b9eb7a57890f02d6e1ba2021aaf76672ae923ef6013ca0aae72c51d",
  "verifier_requirements": [
    {
      "id": "LAS-01",
      "status": "PASS"
    },
    {
      "id": "LAS-02",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-03",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-04",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-05",
      "status": "PASS"
    },
    {
      "id": "LAS-06",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-07",
      "status": "PASS"
    },
    {
      "id": "LAS-08",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-09",
      "status": "PASS"
    }
  ]
}`

DeepSeek: `{
  "turn_id": "D4-L02:T2",
  "outcome": "FAIL",
  "grader_status": "FAIL",
  "logical_generation_calls": 2,
  "physical_attempts": 2,
  "persisted": true,
  "rendered": true,
  "starting_artifact_sha256": "6e88e1dc0032b569ff8e136cf7c6cf6b27b98cc2057f9c88af27b28a51c666e5",
  "ending_artifact_sha256": "6e88e1dc0032b569ff8e136cf7c6cf6b27b98cc2057f9c88af27b28a51c666e5",
  "render_sha256": "e9da1c69cdc836603087ae7ad9775dfbdf30efd5d68e1ca98fc5122c3e4f82f9",
  "verifier_requirements": [
    {
      "id": "LAS-01",
      "status": "FAIL"
    },
    {
      "id": "LAS-02",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-03",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-04",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-05",
      "status": "FAIL"
    },
    {
      "id": "LAS-06",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-07",
      "status": "PASS"
    },
    {
      "id": "LAS-08",
      "status": "NOT_CHECKABLE"
    },
    {
      "id": "LAS-09",
      "status": "PASS"
    }
  ]
}`

</details>

## D4-L03:C01

**Workflow:** `LAS-REVISE`  
**Expected outcome:** `SAFE_ACTIONABLE_FAILURE`

### 1. User Request

```text
In Main Log, add a 24 mm normal track titled "Neutron QC" and plot NPHI from missing_neutron.las on it with a linear 0–45 scale.
```

Request SHA256: `ee73de7b557d7f624125cb2c469ce0df1d27c9a6a6c0a21545f28bee98d3d237`

### 2. What WellPlot Sent to the Model

**EXACT MODEL-FACING PROMPT NOT PRESERVED.** No admissible system/user prompt pair is present in the sealed artifacts, and this report does not approximate one.

Qwen:
```text
source artifact: workspace/evaluations/d5-5/qwen/d5-5-qwen-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 0bcd3c80c6af4c3f4f806541d6708aeea73e99cc00a37111246f7d2a795c03ac
```

DeepSeek:
```text
source artifact: workspace/evaluations/d5-5/deepseek/d5-5-deepseek-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 85d3394fc1b562ad0df68864b8c4f095198e593b5511c4a2f0f999ef44740aae
```

### 3. Qwen Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 4. DeepSeek Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 5. Expected Answer

Reject creation because missing_neutron.las is unavailable; no fallback, mutation, persistence, or render.

<details>
<summary>Exact frozen verifier contract</summary>

```text
{
  "kind": "safety",
  "required_false_flags": [
    "intent_applied",
    "persisted",
    "rendered",
    "fallback_used",
    "substituted_channel",
    "prohibited_object_present"
  ],
  "prohibited_paths": [
    "/sections/0/tracks/3",
    "/sections/0/bindings"
  ]
}
```
</details>

### 6. Difference

| Field | Expected | Qwen | DeepSeek |
|---|---|---|---|
| Semantic result | safe missing-source rejection | PASS | PASS |
| Earliest admissible divergence | Frozen contract | Both lanes produce the required safe rejection; no semantic mutation is recorded. | Both lanes produce the required safe rejection; no semantic mutation is recorded. |

### 7. Deterministic Verifier Outcome

- **Qwen: PASS**; diagnostics: none
- **DeepSeek: PASS**; diagnostics: none
- Persistence/render status is reported separately in the evidence row; it is not treated as the first semantic divergence.

<details>
<summary>Sealed verifier metadata</summary>

Qwen: `{
  "turn_id": "D4-L03:C01",
  "outcome": "PASS",
  "grader_status": "PASS",
  "logical_generation_calls": 2,
  "physical_attempts": 2,
  "persisted": false,
  "rendered": false,
  "starting_artifact_sha256": "fb20891eba8b072cd86c815970213a3a72623e08de9c9181a6be323b080a2c93",
  "ending_artifact_sha256": "fb20891eba8b072cd86c815970213a3a72623e08de9c9181a6be323b080a2c93",
  "render_sha256": null,
  "verifier_requirements": []
}`

DeepSeek: `{
  "turn_id": "D4-L03:C01",
  "outcome": "PASS",
  "grader_status": "PASS",
  "logical_generation_calls": 1,
  "physical_attempts": 1,
  "persisted": false,
  "rendered": false,
  "starting_artifact_sha256": "fb20891eba8b072cd86c815970213a3a72623e08de9c9181a6be323b080a2c93",
  "ending_artifact_sha256": "fb20891eba8b072cd86c815970213a3a72623e08de9c9181a6be323b080a2c93",
  "render_sha256": null,
  "verifier_requirements": []
}`

</details>

## D4-L04:C01

**Workflow:** `LAS-REVISE`  
**Expected outcome:** `SAFE_ACTIONABLE_FAILURE`

### 1. User Request

```text
In Main Log, add a 24 mm normal track titled "Resistivity Alias QC" and plot RT from "30-23a-3 8117_d.las" on it with a logarithmic 0.2–2000 scale.
```

Request SHA256: `bb38915973039b15a8b266b7ca2b7ad6faed2599eb8d8465d60bee662dce7ed6`

### 2. What WellPlot Sent to the Model

**EXACT MODEL-FACING PROMPT NOT PRESERVED.** No admissible system/user prompt pair is present in the sealed artifacts, and this report does not approximate one.

Qwen:
```text
source artifact: workspace/evaluations/d5-5/qwen/d5-5-qwen-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 0bcd3c80c6af4c3f4f806541d6708aeea73e99cc00a37111246f7d2a795c03ac
```

DeepSeek:
```text
source artifact: workspace/evaluations/d5-5/deepseek/d5-5-deepseek-001.evidence.jsonl
source field/path: no raw model-response field exists in the sealed evidence row
SHA256: 85d3394fc1b562ad0df68864b8c4f095198e593b5511c4a2f0f999ef44740aae
```

### 3. Qwen Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 4. DeepSeek Answer

**NOT PRESERVED.** The sealed row contains no raw structured response, parsed planner/worker object, or canonical semantic artifact. Only verifier evidence is available.

### 5. Expected Answer

Reject creation because RT is absent from the named source; no substitution with ILD/ILM/MSFL/GR/CALI and no mutation.

<details>
<summary>Exact frozen verifier contract</summary>

```text
{
  "kind": "safety",
  "required_false_flags": [
    "intent_applied",
    "persisted",
    "rendered",
    "fallback_used",
    "substituted_channel",
    "prohibited_object_present"
  ],
  "prohibited_channels": [
    "ILD",
    "ILM",
    "MSFL",
    "GR",
    "CALI"
  ],
  "prohibited_paths": [
    "/sections/0/tracks/3",
    "/sections/0/bindings"
  ]
}
```
</details>

### 6. Difference

| Field | Expected | Qwen | DeepSeek |
|---|---|---|---|
| Semantic result | safe missing-channel rejection with no substitution | PASS | PASS |
| Earliest admissible divergence | Frozen contract | Both lanes produce the required safe rejection without prohibited substitution. | Both lanes produce the required safe rejection without prohibited substitution. |

### 7. Deterministic Verifier Outcome

- **Qwen: PASS**; diagnostics: none
- **DeepSeek: PASS**; diagnostics: none
- Persistence/render status is reported separately in the evidence row; it is not treated as the first semantic divergence.

<details>
<summary>Sealed verifier metadata</summary>

Qwen: `{
  "turn_id": "D4-L04:C01",
  "outcome": "PASS",
  "grader_status": "PASS",
  "logical_generation_calls": 2,
  "physical_attempts": 2,
  "persisted": false,
  "rendered": false,
  "starting_artifact_sha256": "fb20891eba8b072cd86c815970213a3a72623e08de9c9181a6be323b080a2c93",
  "ending_artifact_sha256": "fb20891eba8b072cd86c815970213a3a72623e08de9c9181a6be323b080a2c93",
  "render_sha256": null,
  "verifier_requirements": []
}`

DeepSeek: `{
  "turn_id": "D4-L04:C01",
  "outcome": "PASS",
  "grader_status": "PASS",
  "logical_generation_calls": 2,
  "physical_attempts": 2,
  "persisted": false,
  "rendered": false,
  "starting_artifact_sha256": "fb20891eba8b072cd86c815970213a3a72623e08de9c9181a6be323b080a2c93",
  "ending_artifact_sha256": "fb20891eba8b072cd86c815970213a3a72623e08de9c9181a6be323b080a2c93",
  "render_sha256": null,
  "verifier_requirements": []
}`

</details>

## Evidence Limitations

The following cannot be inspected from the sealed artifacts:

1. Raw Qwen or DeepSeek assistant responses.
2. Exact system and user prompt bodies sent to each model.
3. Provider-internal reasoning or hidden metadata.
4. Any semantic field not represented in the persisted canonical/verifier evidence.

The report therefore distinguishes observed verifier facts from interpretation. For the two-turn DeepSeek failure chain `D4-L02:T1` -> `D4-L02:T2`, the inherited-state relationship is supported by the artifact hashes and diagnostics; the model's unpersisted response is not available.

## Inspection Result

All 9 turns are represented. The report is documentation-only; sealed campaigns were not modified, no turns were rerun, and no provider/model calls were made during inspection.




