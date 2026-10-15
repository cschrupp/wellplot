# MB-02 Handoff — STOP FOR INDEPENDENT REVIEW

```
SLICE: MB-02
AUTHORITY: WELLPLOT-NLP-RUNTIME-V2-MB02-DETERMINISTIC-RESOLVER-FACT-PROJECTOR-AUTH-001
REPOSITORY: /home/user/projects/wellplot
BRANCH: exp/wellplot-nlp-slm-01
STARTING SHA: 9d2bd840eeef361917776e4a9a6bf1713a446606
CANDIDATE SHA: 85da5283985cea55543d4b2775359e6af2bdd4cb
REMOTE SHA: origin/main @ 225977d (local branch ahead; not pushed)

CLAIM:
MB-02 validates NormalizedRequest + ProjectedWorkspace → derived facts →
deterministic envelope only. It provides no evidence for raw natural-language →
NormalizedRequest.

IMPLEMENTED:
- contracts (NormalizedRequest / ProjectedWorkspace / DerivedFacts / ResolverDecision)
- workspace projection (fixture_loader + D5 focus.curve_handle fix)
- experiment-side curve/track/fill/deictic matchers
- schema/domain checks reusing production ScaleSpec
- static capability registry (WELL-IR 1.2-candidate surface)
- fill precondition facts (adapted renderer same-track/scale semantics; assertion-gated)
- derive-all-facts + Q5 precedence adjudicator + Q6 public envelope mapping
- uniform mb02_normalized_requests.jsonl (300) without gold during generation
- 300-case replay harness + provenance accounting
- representative unit tests

NOT IMPLEMENTED:
- English → NormalizedRequest parser/model
- MB-03 encoder bake-off
- sealed split freeze
- T5 / LangGraph / SLM-04 / WELL-IR / production mutation

NORMALIZATION:
- 300 / 300 schema-valid, source-reviewed
- RULE_BUILDER: 291
- MANUAL_NORMALIZATION: 9
- gold available during generation: NO
- frontier/model calls: 0

REPLAY (canonical normalized inputs):
- public status match: 279 / 300 (0.930)
- non-ok authority match vs MB-01R: 66 / 67
- authority classes accounted: SCHEMA/CARDINALITY/PRECONDITION/NOT_FOUND/CAPABILITY = all present
- duplicated production rules: 0 preferred (ScaleSpec reused; fill-axis adapted; matchers experimental)

AUTHORITY COVERAGE (MB-01R class → cases accounted):
- DETERMINISTIC_SCHEMA_DOMAIN     129/129
- DETERMINISTIC_CARDINALITY        66/66
- DETERMINISTIC_PRECONDITION       64/64
- DETERMINISTIC_NOT_FOUND          24/24
- STATIC_CAPABILITY_BOUNDARY       17/17

RULE PROVENANCE BUCKETS:
- reused_canonical (ScaleSpec): present on schema failures
- adapted_canonical (fill axis): present on asserted fill preconditions
- experimental_only (matchers/registry/adjudicator): all cases

LEARNED GATE REQUIRED: NO
learned_gate_status: NO_LEARNED_GATE_REQUIRED

UNRESOLVED DETERMINISTIC CASES (21):
Mostly complex D5GAP multi-clause / split-fill / dual-instance fill utterances
where NormalizedRequest builders are incomplete, plus D5GAP-0125 (neutron absent
on density-ambiguous fixture while density is multi-match; NOT_FOUND dominates
CARDINALITY under frozen precedence). See mb02_replay_mismatches.json.

TESTS:
- command: cd experiments/nlp_gate_modernbert && \
    PYTHONPATH=src:../nlp_slm_01:../../src ../nlp_slm_01/.venv/bin/python -m pytest tests -q
  result: 30 passed

ARTIFACTS:
- evidence/mb02_normalized_requests.jsonl
- evidence/mb02_normalization_manifest.json
- evidence/mb02_replay_summary.json
- evidence/mb02_replay_results.jsonl
- evidence/mb02_replay_mismatches.json
- evidence/mb02/ (copies)

WORKING TREE: clean after handoff SHA stamp commit
STATUS: STOP FOR INDEPENDENT MB-02 REVIEW
```

MB-03 remains **BLOCKED** / **NOT JUSTIFIED** on current evidence.
T5/LangGraph/SLM-04 remain **NOT AUTHORIZED**.
