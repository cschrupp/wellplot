# WellPlot NLP Runtime V2 — Codex Execution Plan

**Status:** Authoritative Codex implementation sequence (**Amendment R1**)  
**Derived from:** Runtime V2 architecture roadmap  
**Execution rule:** Only the currently authorized slice may be implemented. Every slice ends in a hard STOP for independent review.

## Amendment R1 — Encoder Bake-Off

**MB-03 is now a three-arm RoBERTa-base / ModernBERT-base / UltraBERT-150M experiment.**  
**MB-03 remains blocked until MB-01 and MB-02 are independently accepted.**  

Where Appendix A / older docs still name ModernBERT as the sole initial gate model, **this R1 execution sequence takes precedence**.

### Immediate experimental priority

1. **Three-arm encoder gate bake-off** — RoBERTa-base vs ModernBERT-base vs UltraBERT-150M — while keeping SLM-03/Qwen unchanged as the compiler.
2. **Training block:** MB-03 remains explicitly **BLOCKED** until MB-01 and MB-02 are independently accepted.
3. **T5 translator** only if/after the encoder bake-off and selected-encoder + SLM-03 integration are reviewed.
4. **LangGraph** deferred until resolver/gate/translator contracts are independently accepted.
5. **SLM-04** remains a controlled monolithic comparison path; not the first next implementation.

---

## 0. Codex operating contract

Codex SHALL:

1. Work on one slice only at a time.
2. Use the exact authorized starting SHA/branch supplied for that slice.
3. Make no production-path changes unless the slice explicitly authorizes them.
4. Preserve the current SLM-03 adapter and evidence as immutable comparison artifacts.
5. Preserve WELL-IR 1.2-candidate unless a separate IR-rework authority is issued.
6. Never train on sealed held-out cases.
7. Never infer missing semantic rules from benchmark examples when the real WellPlot code can answer them deterministically.
8. Record exact changed files, tests, commands, candidate SHA, remote SHA, and working-tree state.
9. STOP after publishing the slice handoff. Do not continue automatically into the next slice.
10. Treat any scope ambiguity as a STOP condition, not permission to broaden implementation.

### Forbidden cross-slice work

Without separate authorization, Codex SHALL NOT:

- implement T5 while working on the encoder bake-off;
- implement LangGraph while working on the encoder bake-off or T5;
- retrain Qwen while working on Runtime V2;
- alter canonical WellPlot renderer/lowerer behavior to improve ML scores;
- merge experimental runtime code into production;
- change gate labels or WELL-IR semantics during a training run;
- derive training examples from sealed held-out failures.

---

## 1. Revised experiment order

```
CURRENT FROZEN REFERENCE
SLM-03 / Qwen3-1.7B compiler
        │
        ▼
MB-00  Preserve evidence + establish experiment authority
        │
        ▼
MB-01  Gate corpus audit + deterministic/learned boundary
        │
        ▼
MB-02  Minimal deterministic resolver/fact projector
        │
        ▼
MB-03  3-arm encoder bake-off
       RoBERTa-base / ModernBERT-base / UltraBERT-150M
        │
        ▼
MB-04  Sealed encoder evaluation + winner selection
        │
        ▼
DECISION GATE A
   ├─ FAIL → data/gate rework or SLM-04 path
   └─ PASS + SELECT ENCODER
        │
        ▼
MB-05  Selected encoder + existing SLM-03 integration experiment
        │
        ▼
DECISION GATE B
   ├─ architecture not beneficial → keep monolithic path
   └─ beneficial
        │
        ▼
T5-00 … T5-02 → DECISION GATE C
        │
        ▼
RV2-01 … RV2-04 → shadow / dogfood / promotion
```

---

## 2. MB-00 — Evidence preservation and experiment bootstrap

*(Unchanged intent.)* Create a clean encoder-gate experiment boundary without changing SLM-03.

Deliverables under `experiments/nlp_gate_modernbert/` (name retained for continuity; covers all encoder arms).

**HARD STOP:** Do not proceed to MB-01 without explicit acceptance.

**Status:** Implemented; see `experiments/nlp_gate_modernbert/evidence/mb00_handoff.md`.

---

## 3. MB-01 — Gate corpus audit and authority partition

Construct clean OK / AMBIGUOUS / UNSUPPORTED / INVALID data; separate deterministic facts from learned judgment.

Decision sources: `DETERMINISTIC_CARDINALITY` | `DETERMINISTIC_NOT_FOUND` | `DETERMINISTIC_PRECONDITION` | `DETERMINISTIC_SCHEMA_DOMAIN` | `STATIC_CAPABILITY_BOUNDARY` | `LEARNED_SEMANTIC_GATE`

Dispositions: KEEP / REWRITE / DETACH / REJECT + contrast groups + leakage groups (no leakage across development / validation / sealed_test).

**HARD STOP:** No encoder training yet.

---

## 4. MB-02 — Minimal deterministic resolver / fact projector

Prevent encoders from learning facts deterministic code can prove. If facts establish a terminal envelope, the encoder SHALL NOT be called.

**HARD STOP:** No classifier training until accepted.

---

## 5. MB-03 — Three-arm encoder bake-off

### Authority status

**BLOCKED** until **BOTH** MB-01 and MB-02 are independently accepted.

Before any training command, MB-03 authority SHALL pin:

- accepted MB-01 candidate SHA
- accepted MB-02 candidate SHA
- gate dataset hash
- development / validation / sealed-test split hashes
- fact-projector schema/hash
- label schema
- training-code SHA

Absence of either prerequisite = hard STOP.

### Goal

Controlled comparison of residual learned envelope-gating — not three independently tuned research programs.

### Arms (exactly three; no larger model)

| Arm | Model |
|---|---|
| A | `RoBERTa-base` |
| B | `ModernBERT-base` |
| C | `UltraBERT-150M` (`dmis-lab/UltraBERT-150M`) |

### Experimental fairness

Same audited cases, leakage groups, splits, labels, normalized fields, fact projector, metrics, seed set, model-selection policy, and hyperparameter-search **budget**. Architecture-specific tokenizers/optimizer defaults may differ; no arm gets extra tuning because it is weaker mid-run.

Recommended minimum: **3 fixed seeds per arm**; report mean / std / bootstrap CI when compute permits.

### Input

Normalized request + compact deterministic facts. **Do not** dump the full WellPlot document merely because UltraBERT supports 32K.

### Labels

Exactly: `OK` | `AMBIGUOUS` | `UNSUPPORTED` | `INVALID`

### UltraBERT execution safety

Because UltraBERT may require custom loading code, Codex SHALL:

- pin exact model repository revision/commit;
- record fetched model/config/code hashes where available;
- **review custom Python loading code before execution**;
- avoid unpinned `trust_remote_code=True`;
- record whether custom code execution was required.

A moving `main` revision is not acceptable provenance.

### Training requirements

- grouped split by `leakage_group`;
- class distribution reported;
- weighted loss or balanced sampling permitted;
- false-OK ambiguity = high severity;
- thresholds on validation only;
- model revisions pinned; seed set fixed before comparative eval;
- no sealed-test tuning;
- no arm may see another arm’s sealed-test results before its own checkpoint selection is frozen.

### Validation metrics (every arm × seed)

macro-F1; per-class P/R/F1; OK precision; ambiguous/unsupported/invalid recall; false-OK ambiguous/unsupported; ECE/Brier; stability; train time; peak VRAM; inference latency.

### Model-selection policy

Select each arm’s candidate on **validation only**. Cross-arm winner is **not** selected in MB-03.

### Deliverables

`encoder_bakeoff_manifest.json`; `roberta/` / `modernbert/` / `ultrabert/` run manifests + candidates; `validation_comparison.json`; `training_resource_report.json`

### HARD STOP

Training completion does **not** authorize sealed-test evaluation.  
**STOP FOR INDEPENDENT MB-03 REVIEW.**

---

## 6. MB-04 — Sealed three-arm encoder evaluation

### Goal

1. Can an encoder gate beat the current Qwen fail-closed path?  
2. Which of RoBERTa / ModernBERT / UltraBERT becomes the MB-05 encoder?

### Preconditions

MB-03 accepted; all three candidates frozen; validation thresholds frozen; sealed-test hash unchanged from MB-01.

### Compare (same sealed gate test)

A. deterministic resolver only  
B. SLM-03 envelope behavior  
C–E. each encoder after deterministic resolver  
F–G. optional frontier / Jev (cannot change winner policy after sealed open)

### Continuation gate (proposed)

- ambiguous recall ≥ 0.80  
- unsupported recall ≥ 0.80  
- invalid recall ≥ 0.70  
- OK precision ≥ 0.90  
- false-OK ambiguous ≤ 0.10  

### Winner-selection (lexicographic; safety first)

1. must satisfy continuation gate  
2. minimize false-OK ambiguous  
3. minimize false-OK unsupported  
4. maximize ambiguous recall  
5. maximize unsupported recall  
6. maximize envelope macro-F1  
7. maximize OK precision  
8. prefer calibration/stability  
9. if tied → prefer lower engineering/runtime risk  

Do **not** pick by generic benchmark reputation alone.

### Decision Gate A

- `PASS + SELECT ENCODER` → record exactly one of `ROBERTA_BASE` | `MODERNBERT_BASE` | `ULTRABERT_150M`  
- `DATA-REWORK` | `MODEL-FAIL` | `ARCHITECTURE-FAIL`

### HARD STOP

No T5 yet. **STOP FOR INDEPENDENT MB-04 REVIEW AND HUMAN ENCODER SELECTION ACCEPTANCE.**

---

## 7. MB-05 — Selected encoder + existing SLM-03 integration

```
request → fact projector → deterministic terminal?
                         ├─ yes → final envelope
                         └─ no → selected encoder
                                  ├─ non-OK → final envelope
                                  └─ OK → unchanged SLM-03/Qwen → validator/lowerer
```

Encoder **gates** only; does not generate WELL-IR; does not override deterministic cardinality; does not allocate canonical IDs.

### Decision Gate B

If fail-closed improves without unacceptable executable degradation → proceed to T5-00.  
Else stop — do not build T5 merely because it is next.

### HARD STOP — STOP FOR INDEPENDENT MB-05 REVIEW.

---

## 8–10. T5 track (after Gate B only)

T5-00 operation-level derivation → T5-01 FLAN-T5-small smoke → T5-02 FLAN-T5-base → **Decision Gate C**.  
No LangGraph until Gate C accepted.

---

## 11. TaskGraph / planner / LangGraph

Only after Decision Gate C. See [nlp-runtime-v2-architecture.md](nlp-runtime-v2-architecture.md).

---

## 12. Where SLM-04 fits

Controlled comparison if encoder gate fails, or stronger monolithic baseline is needed. Not justified merely because SLM-03 was imperfect.

---

## 13. Frontier-model role

Corpus reviewer; contrast-case author; T5 alignment reviewer; failure analyst (dev/val only).

---

## 14. Codex handoff template

Unchanged (SLICE / AUTHORITY / SHAs / CHANGED FILES / IMPLEMENTED / NOT IMPLEMENTED / TESTS / ARTIFACTS / INVARIANTS / STATUS: STOP…).

---

## 15. Immediate Codex instruction

1. **MB-00 only** (bootstrap) — identity `WELLPLOT-NLP-RUNTIME-V2-MB00-BOOTSTRAP-AUTH-001`  
2. After MB-00 acceptance → `WELLPLOT-NLP-RUNTIME-V2-MB01-GATE-CORPUS-AUDIT-AUTH-001`  
3. First **training** authority is **MB-03**, issued only after **both** MB-01 and MB-02 are accepted; MB-03 then authorizes **only** the three-arm bake-off.

---

## Appendix A

Long-range architecture roadmap (still names ModernBERT alone in places):  
[nlp-runtime-v2-architecture.md](nlp-runtime-v2-architecture.md)  

**R1 takes precedence** for encoder selection and slice order.
