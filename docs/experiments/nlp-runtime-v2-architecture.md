# WellPlot NLP Runtime V2 — Architecture Roadmap (Appendix A)

**Status:** Long-range design reference  
**Precedence:** The [Codex execution plan](nlp-runtime-v2-codex-execution-plan.md) takes precedence for implementation order. This document preserves the broader architecture.

**Project:** WellPlot natural-language authoring / semantic compiler  
**Primary orchestration candidate:** LangGraph (deferred until model contracts accepted)  
**Initial frontier planner:** Luna-class frontier model  
**Initial local gate:** ModernBERT-base  
**Initial local translator:** FLAN-T5-base / T5-family  
**Existing reference compiler:** Qwen3-1.7B / SLM-03  
**Semantic target:** WELL-IR 1.2-candidate  
**D5 baseline:** `d5/single-engine-convergence` @ `560ec48d2b2809ed2feb55467da15195f527ec44`

> **Amendment R1 precedence:** The Codex execution plan now runs a **3-arm encoder bake-off** (RoBERTa-base / ModernBERT-base / UltraBERT-150M). Sections below that still say “ModernBERT” as the sole initial gate model are historical; **R1 wins**.


---

## 1. Executive decision

Stop treating one small generative model as planner + decomposer + ambiguity/capability classifier + symbol resolver + semantic translator + program generator simultaneously.

Recommended Runtime V2:

```
Human request
    → Frontier semantic planner (Luna initially)
    → Typed task graph
    → Deterministic context/resolver
         ├── deterministic terminal when facts suffice
         └── else ModernBERT semantic gate
                ├── non-OK → envelope / clarification
                └── OK → T5 translator (task → one WELL-IR op)
                         → schema/semantic validator
                         → ordered WELL-IR program
                         → deterministic lowerer
                         → canonical WellPlot authoring/execution
```

LangGraph orchestrates after contracts exist; it does not define semantic truth.

---

## 2. Why this architecture is justified

1. Qwen3-1.7B can learn executable WELL-IR strongly after QLoRA (SLM-02/03).
2. Dominant failure is fail-closed behavior (ambiguity/unsupported emitted as ok).
3. WELL-IR 1.2 is more faithful and structurally demanding.
4. Many decisions are objectively deterministic (alias cardinality, existence, focus, scale compatibility, units, fill preconditions).
5. Small SFT corpora let monolothic decoders memorize ops faster than safe boundaries.
6. The system increasingly resembles a typed compiler pipeline.

**Practical implication:** Models for language interpretation/translation; deterministic code for facts, identity, validation, and execution.

---

## 3. Architectural principles

### 3.1 Deterministic code owns facts

Models must not decide facts computable from project state (existence, alias counts, focus, same-track, scale match, unit support, log bounds).

### 3.2 Models express semantics, not canonical identities

No inventing `main.track.17` etc. Request-local handles / semantic queries only. Canonical IDs are host-owned.

### 3.3 Final ok means resolved and executable

Executable `status: ok` programs contain only uniquely resolved references.

### 3.4 No silent semantic dropping

Every material imperative in an ok request must appear in the program, or the runtime must unsupported/clarify/explicitly split under a designed contract.

### 3.5 Bounded retries only

T5 → validate; optional one frontier recovery → validate; else terminal diagnostic. No open-ended agent loops.

### 3.6 Frameworks do not own semantics

LangGraph is control plane only.

---

## 4. Relationship to SLM-04

| Track | Question |
|---|---|
| SLM-04 | Can Qwen become a better monolithic compiler after corpus/loss repairs? |
| Runtime V2 | Can modular decomposition beat a monolithic compiler on safety/speed/interpretability? |

SLM-03 remains frozen evidence. Neither becomes production without separate authority.

---

## 5. Proposed repository structure

```
experiments/nlp_runtime_v2/   # later; ModernBERT gate starts in nlp_gate_modernbert/
  contracts/ planner/ resolver/ gate/ translator/
  orchestration/ validation/ datasets/ eval/ artifacts/
```

**One-way import:** experiment → `src/wellplot` only. Deleting the experiment must leave WellPlot unchanged.

Current active bootstrap: `experiments/nlp_gate_modernbert/` (MB-00+).

---

## 6. Core contracts (freeze before model work)

### 6.1 TaskGraph / SemanticTask

Typed tasks aligned to WELL-IR ops: SET_INTERVAL, CREATE_TRACK, PLACE_CURVE, MOVE_CURVE, REMOVE_CURVE, CONFIGURE_CURVE_DISPLAY, DEFINE_FILL, REMOVE_FILL.

Planner may decompose/order/parameterize; must not decide canonical IDs, alias resolution, existence, fill compatibility, units, or execution status.

### 6.2 SemanticQuery

Internal queries may be richer than executable selectors (family/mnemonic/deictic). Belongs to resolver boundary.

### 6.3 ResolverResult

`resolved` (exactly one) | `ambiguous` (>1) | `not_found` (0) | `invalid`. No model may override cardinality.

### 6.4 GateDecision

Labels: ok | ambiguous | unsupported | invalid + probabilities/confidence/reason_class. No free-form reasoning as execution dependency.

### 6.5 TranslatorInput

Normalized narrow task + resolved target → one WELL-IR operation.

---

## 7–8. LangGraph state and nodes

Deferred until Decision Gate C. See Codex plan §11. Nodes include prepare_context, plan_request, resolve_task, classify_semantic_gate, translate_task, validate_*, clarification interrupt, bounded recovery, finalize_*.

Deterministic edges preferred: if resolver finds two matches, do not ask ModernBERT whether the request is ambiguous.

---

## 9. Broader slice map (reference)

Original RV2-00…RV2-13 numbering in the long roadmap is **superseded for Codex order** by MB-00…MB-05 → T5 → RV2-01…. Keep this appendix for contract/detail depth when those slices are authorized.

Critical path summary after Gate C:

TaskGraph → Frontier planner → LangGraph skeleton → Full integration → Fallback → E2E eval → Shadow → Promotion.

---

## 10. Data governance

- Provenance fields on training examples.
- No held-out contamination after sealing.
- Development/validation failures reusable; sealed final evidence is not.

---

## 11. Proposed research gates (not yet frozen production SLAs)

| Component | Suggested target |
|---|---|
| Resolver | 100% deterministic contract suite |
| ModernBERT | amb/unsup recall ≥0.80; invalid ≥0.70; OK precision ≥0.90; false-OK amb ≤0.10 |
| T5 | schema ≥99%; semantic/exec op ≥85% |
| E2E core | schema ≥99%; exec semantic ≥80%; fail-closed recalls as above; no core family <60%; lowerer 100% |

---

## 12. Final architecture target

Models interpret. Deterministic code resolves, validates, owns identity, and executes.
