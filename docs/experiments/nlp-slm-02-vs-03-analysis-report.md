# WELL-IR NLP SLM-02 vs SLM-03 — Full Analysis Report

**Document purpose:** Exhaustive record of decisions, settings, steps, and results for SLM-02 and SLM-03 (with necessary SLM-01 / 01B / corpus-freeze context) so you can analyze regressions, improvements, and next experiments.

**Report date:** 2026-10-13  
**Experiment root:** `experiments/nlp_slm_01/`  
**Hardware used for both fine-tunes:** WSL2, NVIDIA GeForce RTX 3060 Laptop GPU (6.0 GB), Unsloth Studio Python (`~/.unsloth/studio/unsloth_studio/bin/python`, Torch 2.11.0+cu130)

---

## 0. Executive comparison (read this first)

| Dimension | SLM-02 | SLM-03 |
|---|---|---|
| Goal | QLoRA on frozen SLM-01 gold (WELL-IR **1.0**) | QLoRA on D5-grounded gold (WELL-IR **1.2-candidate**) |
| Base model | `Qwen/Qwen3-1.7B` (local ModelScope snapshot) | Same |
| Method | Unsloth QLoRA 4-bit | Same hyperparams (new seed) |
| Train rows (SFT utterances) | **284** | **237** |
| Val rows | **95** | **40** |
| Gold cases | **360** (1.0) | **300** (1.2-candidate) |
| Held-out cases | **70** | **50** (26 trainable-support / 24 future-ops) |
| Primary reported semantic score | **82.5%** executable (Q1) | **60.0%** D5-executable floor (Q1) |
| Overall held-out correct | **67.1%** | Floor **34.6%** / Full **30.0%** |
| Gate | **IR-REWORK** (`family_breadth`) | **IR-REWORK** (`family_breadth`) |
| Ambiguity family | **0/13** | **0/10** |
| Composition family | **5/13 (38%)** | Floor **3/3 (100%)** |
| Are scores A/B comparable? | **No** — different IR, gold, fixtures, splits, train filter, prompt | |

**Bottom line:** Same gate outcome. Headline semantic floor dropped (82.5% → 60%) on a **harder, D5-aligned** exam. Ambiguity remains the shared failure mode. Composition improved on a small floor sample. Not a clean regression test.

---

## 1. Lineage before SLM-02 (why Qwen3-1.7B was frozen as the FT base)

### 1.1 SLM-01 (untuned baselines)

- Untuned `Qwen/Qwen3-1.7B` Q2 held-out semantic ≈ **42.1%**.
- Gate outcome for size ladder: **MODEL-SIZE-FAIL** path opened the 01B ~3B experiment.

### 1.2 SLM-01B (~3B ladder)

Authorized to test whether larger untuned bases beat Qwen without IR rewrite.

| Arm | Runtime | Best semantic |
|---|---|---|
| A SmolLM3-3B BF16 | HF + offload | **28.1%** |
| C SmolLM3 GGUF Q4 | llama.cpp | 21.1% |
| D Phi-4-mini GGUF Q4 | llama.cpp | 21.1% |
| B Phi-4-mini BF16 | HF + offload | 15.8% (Q2 aborted) |
| Ref Qwen3-1.7B | — | **42.1%** |

**Decision:** Do **not** fine-tune 3B on this 6 GB laptop. SLM-02 QLoRA targets **Qwen3-1.7B**.

**Evidence:** `docs/experiments/nlp-slm-01b.md`, `benchmark/evidence/slm01b_*`.

---

## 2. Shared gate definition (unchanged across SLM-01 → 03)

Implemented in `eval/report.py::evaluate_gate`.

### 2.1 Checks

| Check key | Pass condition |
|---|---|
| `ir_frozen` | IR frozen for the experiment |
| `gold_frozen` | Gold frozen |
| `split_frozen` | Splits frozen / sealed held-out |
| `lowerer_100` | Lowerer pass rate ≥ 1.0 |
| `baselines_complete` | Eval arms complete |
| `taxonomy_complete` | Failure taxonomy present |
| `semantic_floor_50` | Executable semantic correctness ≥ **0.50** |
| `family_breadth` | Per-family heuristic (see below) |
| `learnable_ge_70` | Learnable share of confirmed semantic failures ≥ 0.70 |
| `ir_limit_lt_15` | IR-limitation share of all failures < 0.15 |
| `no_leakage` | Held-out not used in training |
| `non_goals` | Non-goals preserved |

### 2.2 Decision outcomes

- `PASS` — all checks true  
- `MODEL-SIZE-FAIL` — semantic floor fails while infra/freeze checks hold  
- `IR-REWORK` — breadth / IR / lowerer / other non-size failures (including `family_breadth` false)

### 2.3 Family breadth heuristic (as coded)

For families present in the scored set: fail if `correct < 5` **and** `rate < 0.25`.  
SLM-03 applies this on the **D5-executable floor** family stats (not future-ops-only rows).

Ambiguity at **0%** with n≥5 trips this check → **IR-REWORK** for both SLM-02 and SLM-03.

---

## 3. SLM-02 — full record

### 3.1 Authorization / purpose

- **Doc:** `docs/experiments/nlp-slm-02.md`
- **Purpose:** QLoRA fine-tune Qwen3-1.7B on frozen SLM-01 development SFT; sealed held-out retest with SLM-01 gate.
- **Non-goals:** No IR rewrite; no held-out training.

### 3.2 Corpus & freeze (inputs)

| Item | Value |
|---|---|
| WELL-IR | **1.0** |
| Gold | `benchmark/gold/cases.jsonl` (then); archived now at `benchmark/archive/slm01_well_ir_1_0/gold/cases.jsonl` |
| Cases | **360** |
| Utterances (corpus meta) | **467** |
| Schema | `benchmark/schema/well_ir_v1.json` (archived copy under `archive/slm01_well_ir_1_0/schema/`) |
| Corpus SHA256 | `4a2c68ba839f7a8faf57fa4faf13680564d6e73f36bc4415238351ca57bd2d2c` |

**Family mix (360):**

| Family | n |
|---|---|
| composition | 71 |
| ambiguity_unsupported | 63 |
| relational_targeting | 60 |
| fills | 55 |
| curve_placement | 47 |
| intervals | 45 |
| display_configuration | 19 |

**Splits (1.0):**

| Split | n |
|---|---|
| development | 219 |
| validation | 71 |
| held_out | 70 |

### 3.3 SFT export

- Script: `scaffold/qlora/export_training_data.py` (then: all cases in split; no support-level filter)
- Train: `artifacts/exports/dev_sft.jsonl` → **284** rows (utterance-expanded)
- Val: `artifacts/exports/val_sft.jsonl` → **95** rows
- Row fields: `case_id`, `split`, `utterance`, `workspace`, `d0`, `output` (gold envelope)
- Fixtures: classic `{d0, workspace}` JSON under `benchmark/fixtures/d0_*.json`

### 3.4 Prompt / packaging

- `SYSTEM_PROMPT` from `runners/common.py` (WELL-IR **1.0** wording at train time)
- User payload via `assemble_user_payload(utterance, workspace, d0)` JSON with:
  - `utterance`
  - `workspace`
  - `document_state_summary` (tracks / curve refs / fills / interval)
  - `well_ir_version`
- Chat template: Qwen3 with `enable_thinking=False`
- Training rows: **single-turn** (system + user + assistant gold); **no few-shot in SFT**
- Eval arms: **Q1** (zero-shot) and **Q2** (few-shot exemplars)

### 3.5 Training settings

| Setting | Value |
|---|---|
| Script | `scripts/train_slm02_unsloth.py` |
| Runtime | Unsloth Studio Python (CUDA) |
| Base path | `artifacts/modelscope_cache/models/Qwen--Qwen3-1.7B/snapshots/master` |
| Method | `unsloth_qlora_4bit` |
| `load_in_4bit` | True |
| `max_seq_length` | 2048 |
| LoRA `r` | 16 |
| LoRA `alpha` | 32 |
| LoRA `dropout` | 0.05 |
| Target modules | q/k/v/o_proj, gate/up/down_proj |
| Gradient checkpointing | `"unsloth"` |
| Batch size | 1 |
| Grad accumulation | 8 (effective batch 8) |
| Epochs | **3.0** |
| LR | **2e-4** |
| Optim | `adamw_8bit` |
| Precision | bf16=True, fp16=False |
| Warmup | `warmup_ratio=0.05` |
| Packing | False |
| Save / eval | per epoch; `load_best_model_at_end` on `eval_loss` |
| Seed | **20261011** |
| Adapter out | `artifacts/adapters/slm02_qwenv17_qlora/` |
| Train meta | `.../slm02_train_meta.json` |

### 3.6 Evaluation protocol (SLM-02)

- Script: `scripts/run_slm02_heldout.py`
- Load base 4-bit + PEFT adapter; `FastLanguageModel.for_inference`
- Prompt arms: **Q1, Q2**
- Decode: `do_sample=False`, `max_new_tokens=512`
- Scoring: schema parse → `normalized_equal` OR `execution_equivalent` → `correct`
- Gate semantic metric: **executable** subset (`gold_status == "ok"`)

### 3.7 SLM-02 results

#### Headline

| Metric | Q1 | Q2 |
|---|---|---|
| n held-out | 70 | 70 |
| Executable semantic | **82.56%** (47/57) | **0%** |
| Overall correct | **67.14%** (47/70) | 0% |
| Schema validity | 98.57% | (broken) |
| False-ok on ambiguous | **5** | — |
| Envelope macro-F1 | 0.222 | — |
| Δ vs untuned Qwen Q2 (42.1%) | **+40.4 pts** | — |

**Q2 failure cause:** few-shot prompts exceeded context (truncation at 4096 in that run path) → 0% usable.

#### Q1 family rates

| Family | Correct | n | Rate |
|---|---|---|---|
| curve_placement | 9 | 9 | **1.00** |
| fills | 10 | 10 | **1.00** |
| intervals | 9 | 9 | **1.00** |
| relational_targeting | 11 | 12 | **0.92** |
| display_configuration | 3 | 4 | **0.75** |
| composition | 5 | 13 | **0.38** |
| ambiguity_unsupported | 0 | 13 | **0.00** |

#### Envelope confusion (Q1, gold → pred counts)

From `slm02_model_metrics.json`:

- gold `ok` → pred `ok` 56, `invalid` 1  
- gold `ambiguous` → pred `ok` **5** (all false-ok)  
- gold `unsupported` → pred `ok` **6**  
- gold `invalid` → pred `ok` **2**

#### Failure taxonomy (Q1)

| Label | count |
|---|---|
| envelope_misuse | 13 |
| composition | 8 |
| syntax_or_schema | 1 |
| other | 1 |

- Learnable share of confirmed: **1.0**  
- IR-limitation share: **0.0**

#### Gate

```json
{
  "decision": "IR-REWORK",
  "checks": {
    "semantic_floor_50": true,
    "family_breadth": false,
    "learnable_ge_70": true,
    "ir_limit_lt_15": true
  }
}
```

**Interpretation:** Model learned executable ok-programs well; **did not learn fail-closed ambiguity/unsupported**. Composition under-learned relative to placement/fills.

### 3.8 Evidence paths (SLM-02)

- `benchmark/evidence/slm02_final_summary.json`
- `benchmark/evidence/slm02_gate_decision.json`
- `benchmark/evidence/slm02_model_metrics.json`
- `benchmark/evidence/slm02_family_metrics.json`
- `benchmark/evidence/slm02_failure_taxonomy.json`
- `artifacts/adapters/slm02_qwenv17_qlora/`
- `artifacts/runs/slm02_*` (if retained)

---

## 4. Interlude — post–SLM-02 corpus work (decisions that shaped SLM-03)

After SLM-02 `IR-REWORK`, work shifted from “bigger model” to **data / IR grounding**.

### 4.1 Diagnosis that drove the next phase

- Ambiguity_unsupported **0/13** (false `ok`) → breadth fail.
- Composition weak (38%).
- CM / TW / D4 historical corpora exist but are **not** drop-in WELL-IR SFT (report/CBL/VDL constructs; invented paraphrases).

### 4.2 CM/TW/D4 mine → map → candidate pass (parked, not merged)

**Authorized decisions (interview sequence):**

1. Mine CM/TW/D4 as **candidates only** (no auto-merge into gold/SFT).
2. Priority families: **ambiguity_unsupported** + **composition**.
3. Volume aim: ~80–120 development / ~20–30 validation new rows.
4. After first mine under-shot volume (68 admits): accept **controlled composition paraphrases** (~40–60) rather than forcing invented-mnemonic rejects.

**Implementation:** `scripts/mine_cm_tw_d4_to_well_ir.py`

**Final candidate summary** (`artifacts/exports/cm_tw_d4_mapped_summary.json`):

| Metric | Value |
|---|---|
| Total mapped rows | 184 |
| Admit | **118** |
| Reject | 66 |
| Ambiguity admits | 54 |
| Composition admits | 60 (incl. 50 `para`) |
| Sources | cm 57 · para 50 · d4 10 · tw 1 |
| Split hints | development 97 · validation 21 |

**Later disposition (SLM-03 freeze decision):** leave `cm_tw_d4_mapped_candidates.jsonl` **parked**; do **not** merge into 1.0 gold. Superseded by D5-grounded 300.

### 4.3 D5-grounded 300 corpus (authoritative replacement)

**External deliverable:**  
`artifacts/exports/wellplot_slm01_d5_grounded_300_r1.zip`

**ZIP contents:**

| File | Role |
|---|---|
| `wellplot_slm01_d5_grounded_300_r1.jsonl` | Full 300-case gold |
| `wellplot_slm01_d5_gap_cases_148_r1.jsonl` | 148 new gap cases |
| `well_ir_1_2_candidate.schema.json` | IR schema |
| `wellplot_slm01_d5_fixture_manifest_r1.json` | 16 D5 fixtures |
| `wellplot_slm01_d5_coverage_matrix_r1.json` | Coverage / support stats |
| `wellplot_slm01_d5_300_review.md` | Human audit narrative |

**Grounding baseline:**

- Branch: `d5/single-engine-convergence`
- Commit: `560ec48d2b2809ed2feb55467da15195f527ec44`
- WELL-IR: **1.2-candidate**
- D5 semantic-action union (production): `reconstruct | update_curve_scale | add_track | add_fill`

**Corpus structure:**

| Status | n |
|---|---|
| ok | 233 |
| unsupported | 43 |
| invalid | 14 |
| ambiguous | 10 |
| **Total** | **300** |

**Support levels (critical for train filter):**

| Level | Meaning | n |
|---|---|---|
| `d5_current` | Directly foldable to current D5 semantic actions | 77 |
| `d5_context_lowerable` | Needs deterministic merge with current state | 20 |
| `authoring_supported` | Canonical AuthoringDocumentIntent, not yet one of four D5 actions | 106 |
| `resolver_extension` | Needs WELL-IR relation/move resolver | 30 |
| `envelope_only` | Ambiguity / unsupported / invalid envelopes | 67 |

**Unique by `(fixture, canonical gold)`** — paraphrase duplicates do not count as new semantic targets.

**1.2 schema additions called out in audit:**

- Request-local `curve-N` / fill handles (duplicate CBL instances)
- `between_instances` fills
- `width_mm` on `create_track`
- `append` / `before` / `after` track placement
- Nested `scale` / `style` patches on `configure_curve_display`
- `set_interval` uses `base` (alias of bottom); units include cm (core registry m/ft/in/cm/mm)

**Caveat recorded:** original 152 fixtures’ manifests unavailable → marked `contract_audited_original_fixture_manifest_unavailable`; 148 new cases state-validated against 16-fixture manifest.

---

## 5. SLM-03 freeze — decisions (interview tree, all agreed)

These were locked **one decision at a time** before any install/train:

| # | Decision | Agreed choice |
|---|---|---|
| 1 | Gold role of D5 300 | **Replace** `cases.jsonl` (not parallel with 1.0; no mix 1.0+1.2) |
| 2 | SFT support filter | Train **only** `d5_current` + `d5_context_lowerable` + `envelope_only` (~164 cases). Hold out `authoring_supported` + `resolver_extension` from SFT |
| 3 | Splits | Stratified rebuild of all 300 ≈ **70/15/15** by `(semantic_family, support_level)`; seed `20251013`; held-out keeps **all** support levels |
| 4 | Schema | Sole experiment schema = **1.2-candidate**; archive 1.0 |
| 5 | Fixtures | Keep `d0_*`; install 16 `d5_*` manifests **as authored** (semantic manifest shape) |
| 6 | Train timing | Freeze-only first; train only after explicit authorize |
| 7 | Archive / park | Move 1.0 gold/splits/schema → `benchmark/archive/slm01_well_ir_1_0/`; park CM candidates; write freeze notes |

### 5.1 Freeze install execution

- Installer: `scripts/freeze_slm03_d5_corpus.py`
- Summary: `artifacts/exports/slm03_freeze_summary.json`
- Gold SHA256: `172e70825d51bf3cb68ea3798ff87f20da21e7365d14ff0efd383b69d9013a11`
- ZIP SHA256: `7c446fd3fb9d78d0eefa35e75c507d1fa5a321b6e0136cc7f9322333944b38ec`

**Splits realized:**

| Split | Cases | Of which trainable support |
|---|---|---|
| development | **204** | 113 |
| validation | **46** | 25 |
| held_out | **50** | 26 |

**SFT export after filter:**

| Export | Rows (utterances) |
|---|---|
| `dev_sft.jsonl` | **237** |
| `val_sft.jsonl` | **40** |

Export script updated to:

1. Skip non-trainable support levels  
2. Load fixtures via `benchmark/fixture_loader.py` (projects D5 manifests → `d0`/`workspace` for prompts)

**Held-out mix (for interpreting dual scores):**

| Support level | n in held-out |
|---|---|
| authoring_supported | 18 |
| d5_current | 12 |
| envelope_only | 11 |
| resolver_extension | 6 |
| d5_context_lowerable | 3 |

| Gold status | n |
|---|---|
| ok | 39 |
| unsupported | 8 |
| ambiguous | 2 |
| invalid | 1 |

### 5.2 Docs written at freeze

- `benchmark/FREEZE.md` (active freeze boundary)
- `docs/experiments/nlp-slm-03-freeze.md`
- Provenance copies under `benchmark/gold/`: coverage matrix, review md, fixture manifest

---

## 6. SLM-03 — train authorization decisions

Agreed before run:

| # | Decision | Choice |
|---|---|---|
| 1 | Base | Same **Qwen3-1.7B** Unsloth QLoRA; new adapter `slm03_qwenv17_qlora` |
| 2 | Hyperparams | Match SLM-02 (3 ep, 2e-4, 2048, r16/α32/drop 0.05, batch 1×accum 8, bf16); seed **20251013** |
| 3 | Prompt | Light **1.2** refresh (handles, `between_instances`, `width_mm`, append/before/after); still no few-shot in train |
| 4 | Eval | **Q1 only** (no Q2); dual scores: (a) D5-executable floor (b) full held-out breadth |

### 6.1 Prompt delta (SLM-03)

File: `runners/common.py`  
Version constant: `well_ir/version.py` → `WELL_IR_VERSION = "1.2-candidate"`

Added guidance (summary):

- Prefer request-local `curve-N` / fill handles when present  
- `define_fill` may use `between_instances` with matching scales  
- `create_track` may include `width_mm` and append|before|after  
- Outside-scope language updated from “WELL-IR v1” to version-templated 1.2-candidate

### 6.2 Pydantic / loader updates required for 1.2 eval

Gold shapes diverged from 1.0 models (114/300 initially failed parse). Updated:

- `well_ir/selectors.py` — `handle` promotion; track `ref` may be str id/title  
- `well_ir/targets.py` — `AppendTarget`; relations before/after  
- `well_ir/operations.py` — fill `kind`/`mode`, nested scale/style, `base`↔`bottom`, `width_mm`/`title`, baseline `{value:…}`  
- `lowerer/context.py` — extra=ignore; array tracks; channel/handle fields  
- Result after fix: **300/300** parse OK

### 6.3 Training settings (SLM-03)

| Setting | Value |
|---|---|
| Script | `scripts/train_slm03_unsloth.py` |
| Runtime | Same Unsloth Studio CUDA Python |
| Base | Same Qwen3-1.7B snapshot |
| Train / val | 237 / 40 |
| Epochs / LR / seq / LoRA | **Identical to SLM-02** except seed |
| Seed | **20251013** |
| Steps | 90 total (3 epochs × ceil(237/8)) |
| Train loss (final) | **0.3765** |
| Eval loss (final) | **2.049** |
| Train runtime | ~968 s (~16 min) |
| Adapter | `artifacts/adapters/slm03_qwenv17_qlora/` |
| Meta | `slm03_train_meta.json` |

### 6.4 Evaluation protocol (SLM-03)

- Script: `scripts/run_slm03_heldout.py`
- Prompt arm: **Q1 only**
- Dual scoring scopes:
  - **D5-executable floor:** support ∈ {`d5_current`,`d5_context_lowerable`,`envelope_only`} — **n=26**
  - **Full held-out breadth:** all 50  
  - **Future-ops probe:** authoring + resolver — **n=24** (informational)
- Gate uses **floor** executable semantic + floor family breadth
- Evidence prefix: `slm03_*`

### 6.5 SLM-03 results

#### Headline dual scores

| Scope | n | Executable semantic | Overall correct | Schema validity | False-ok ambiguous |
|---|---|---|---|---|---|
| D5-executable floor | 26 | **60.0%** (9/15 exec) | 34.6% | 92.3% | 2 |
| Full held-out | 50 | (see metrics file) | **30.0%** | — | — |
| Future-ops probe | 24 | — | **25.0%** | — | — |

#### Floor family rates (gate scope)

| Family | Correct | n | Rate |
|---|---|---|---|
| composition | 3 | 3 | **1.00** |
| display_configuration | 2 | 4 | **0.50** |
| track_creation | 1 | 2 | **0.50** |
| fills | 3 | 7 | **0.43** |
| ambiguity_unsupported | 0 | 10 | **0.00** |

Note: floor held-out did **not** contain curve_placement / intervals / relational rows in this stratified draw (those families exist in corpus but landed elsewhere or as non-trainable).

#### Floor envelope confusion (gold → pred)

- `ok` → `ok` 15  
- `ambiguous` → `ok` **2**  
- `unsupported` → `ok` **6**, `invalid` 2  
- `invalid` → `ok` **1**

#### Floor failure taxonomy

| Label | count |
|---|---|
| envelope_misuse | 9 |
| other | 6 |
| syntax_or_schema | 2 |

#### Gate

```json
{
  "decision": "IR-REWORK",
  "checks": {
    "semantic_floor_50": true,
    "family_breadth": false,
    "learnable_ge_70": true,
    "ir_limit_lt_15": true
  }
}
```

Same structure as SLM-02: floor ≥50% passes; ambiguity 0% fails breadth.

### 6.6 Evidence paths (SLM-03)

- `docs/experiments/nlp-slm-03.md`
- `docs/experiments/nlp-slm-03-freeze.md`
- `benchmark/FREEZE.md`
- `benchmark/evidence/slm03_final_summary.json`
- `benchmark/evidence/slm03_gate_decision.json`
- `benchmark/evidence/slm03_model_metrics.json`
- `benchmark/evidence/slm03_family_metrics.json`
- `benchmark/evidence/slm03_failure_taxonomy.json`
- `artifacts/runs/slm03_train.log`
- `artifacts/runs/slm03_heldout.log`
- `artifacts/runs/slm03_heldout_Q1.jsonl`
- `artifacts/adapters/slm03_qwenv17_qlora/`

---

## 7. Side-by-side settings matrix

| Setting | SLM-02 | SLM-03 |
|---|---|---|
| Base | Qwen3-1.7B | Qwen3-1.7B |
| QLoRA | 4-bit, r16, α32, drop 0.05 | Same |
| Epochs / LR / seq | 3 / 2e-4 / 2048 | Same |
| Eff. batch | 8 | 8 |
| Seed | 20261011 | 20251013 |
| WELL-IR | 1.0 | 1.2-candidate |
| Gold cases | 360 | 300 |
| Train filter | All split cases | 3 support levels only |
| SFT train/val rows | 284 / 95 | 237 / 40 |
| Held-out | 70 | 50 |
| Fixtures | d0+workspace | d0 + D5 manifests (projected) |
| Prompt | 1.0 compiler prompt | 1.2 + handles / between_instances / width_mm |
| Eval arms | Q1 + Q2 | Q1 only |
| Gate semantic scope | All held-out executable | Floor support levels only |
| Adapter path | `slm02_qwenv17_qlora` | `slm03_qwenv17_qlora` |

---

## 8. What improved vs what worsened (analytic, not gate math)

### 8.1 Not directly comparable

Different IR version, gold uniqueness rule, fixture semantics, train exclusion of 106+30 future-ops cases, smaller held-out, different family occupancy in the floor slice.

### 8.2 Same failure mode (high confidence)

| Signal | SLM-02 | SLM-03 |
|---|---|---|
| Ambiguity rate | 0/13 | 0/10 |
| False-ok on ambiguous | 5 | 2 (floor; smaller ambiguous n) |
| Unsupported often predicted `ok` | yes (6) | yes (6 on floor) |
| Gate | IR-REWORK | IR-REWORK |

**Conclusion:** Fine-tuning on ok-heavy SFT without strong fail-closed pressure does not teach envelope discipline. SLM-03 included `envelope_only` in the trainable set, but floor ambiguity remains 0%.

### 8.3 Apparent improvements

- **Composition** on floor: 38% → 100% (n=3 only — treat as weak evidence).
- **Corpus quality / product alignment:** support_level tags prevent training “authoring as if D5-current”.
- **IR fidelity:** 1.2 handles, between_instances, renderer-aware fill preconditions documented in gold.
- **Eval honesty:** dual scores separate “what D5 can run today” from “future resolver/authoring”.

### 8.4 Apparent regressions

- Executable semantic floor: **82.5% → 60%**.
- Fills: **100% → 43%** (1.2 fill `kind`, instance fills, scale gates harder).
- Display: **75% → 50%** (nested scale/style).
- Full held-out overall **30%** (includes 24 untrained future-ops rows by design).
- Schema validity floor **92%** vs SLM-02 **98.6%** (stricter / newer shapes).

### 8.5 Confounders to weight in any improvement proposal

1. **Train set smaller and filtered** (237 vs 284 utterances; excluded authoring/resolver).  
2. **Floor executable n=15** vs SLM-02 executable n=57 — high variance.  
3. **Family coverage in floor held-out is sparse** (no placement/intervals/relational in the 26).  
4. **Prompt changed** at the same time as corpus — entangled ablation.  
5. **Equalization metric missing:** no re-eval of SLM-02 adapter on 1.2 gold (and vice versa).

---

## 9. Artifact & reproducibility checklist

### 9.1 Reproduce SLM-02 train

```bash
cd experiments/nlp_slm_01
# Requires archived 1.0 gold/splits restored OR use archive paths manually
~/.unsloth/studio/unsloth_studio/bin/python scripts/train_slm02_unsloth.py
```

### 9.2 Reproduce SLM-03 freeze + train + eval

```bash
cd experiments/nlp_slm_01
export PYTHONPATH=.
python3 scripts/freeze_slm03_d5_corpus.py
python3 scaffold/qlora/export_training_data.py --split development --out artifacts/exports/dev_sft.jsonl
python3 scaffold/qlora/export_training_data.py --split validation --out artifacts/exports/val_sft.jsonl
~/.unsloth/studio/unsloth_studio/bin/python scripts/train_slm03_unsloth.py
~/.unsloth/studio/unsloth_studio/bin/python scripts/run_slm03_heldout.py
```

### 9.3 Key hashes

| Artifact | SHA256 |
|---|---|
| D5 ZIP | `7c446fd3fb9d78d0eefa35e75c507d1fa5a321b6e0136cc7f9322333944b38ec` |
| Active gold `cases.jsonl` | `172e70825d51bf3cb68ea3798ff87f20da21e7365d14ff0efd383b69d9013a11` |
| Archived 1.0 corpus | `4a2c68ba839f7a8faf57fa4faf13680564d6e73f36bc4415238351ca57bd2d2c` |
| D5 commit | `560ec48d2b2809ed2feb55467da15195f527ec44` |

---

## 10. Suggested analysis angles for your improvement pass

(These are analysis prompts, not authorized next steps.)

1. **Ambiguity curriculum:** upsample `envelope_only` / hard negative mining; penalize false-ok; contrastive pairs (ambiguous vs clarified).  
2. **Ablate prompt vs corpus:** retrain SLM-03 corpus with SLM-02 prompt; or eval SLM-02 adapter zero-shot on projected 1.2 (expect schema fail).  
3. **Rebalance held-out floor:** ensure each core family has ≥5 floor cases before claiming breadth.  
4. **Fill/display 1.2 shapes:** dedicated SFT for nested `scale`/`style` and fill `kind` including `between_instances` preconditions.  
5. **Whether to train `authoring_supported`:** trade product honesty vs score; dual gate already separates this — decide if SLM should emit authoring IR early.  
6. **Merge parked CM candidates selectively** into 1.2 gold only where ops validate under 1.2 + D5 fixtures.  
7. **Q2 / longer context:** SLM-02 Q2 was broken; if few-shot desired, raise ctx and retest separately from Q1 gate.  
8. **Equal-n bootstrap:** report Wilson intervals on floor executable n=15 before treating 60% vs 82% as decisive.

---

## 11. Decision log (chronological, condensed)

1. SLM-01: Qwen3-1.7B untuned ~42% → size fail path.  
2. SLM-01B: ~3B arms all < Qwen → choose Qwen for FT.  
3. SLM-02: QLoRA on 1.0 gold → **82.5%** exec, **IR-REWORK** (ambiguity 0/13).  
4. Explore CM/TW/D4 as dictionary → candidates-only mine/map.  
5. Expand composition paraphrases → 118 admits; still not merged.  
6. Accept D5-grounded 300 + 1.2-candidate as **replacement** gold.  
7. Train filter: exclude authoring/resolver.  
8. Stratified splits; archive 1.0; park CM.  
9. Freeze-only, then authorize SLM-03 with matched hparams + 1.2 prompt + Q1 dual eval.  
10. SLM-03: **60%** floor exec, **IR-REWORK** (ambiguity 0/10).

---

## 12. Pointer index

| Topic | Path |
|---|---|
| This report | `docs/experiments/nlp-slm-02-vs-03-analysis-report.md` |
| SLM-02 auth/results | `docs/experiments/nlp-slm-02.md` |
| SLM-03 auth/results | `docs/experiments/nlp-slm-03.md` |
| SLM-03 freeze | `docs/experiments/nlp-slm-03-freeze.md` |
| Active freeze boundary | `experiments/nlp_slm_01/benchmark/FREEZE.md` |
| D5 review narrative | `experiments/nlp_slm_01/benchmark/gold/wellplot_slm01_d5_300_review.md` |
| Coverage matrix | `experiments/nlp_slm_01/benchmark/gold/wellplot_slm01_d5_coverage_matrix_r1.json` |
| Archived 1.0 | `experiments/nlp_slm_01/benchmark/archive/slm01_well_ir_1_0/` |
| Parked CM candidates | `experiments/nlp_slm_01/artifacts/exports/cm_tw_d4_mapped_candidates.jsonl` |
