# MB-00 Handoff — STOP FOR INDEPENDENT REVIEW

```
SLICE: MB-00
AUTHORITY: WELLPLOT-NLP-RUNTIME-V2-MB00-BOOTSTRAP-AUTH-001
REPOSITORY: /home/user/projects/wellplot
BRANCH: exp/wellplot-nlp-slm-01
STARTING SHA: 225977d80e945923d7c883f0c829d90dd16aa75f
CANDIDATE SHA: (working tree; not committed — see WORKING TREE)
REMOTE SHA: (no upstream tracking verified at handoff)

CHANGED FILES (this slice):
- docs/experiments/nlp-runtime-v2.md
- docs/experiments/nlp-runtime-v2-codex-execution-plan.md
- docs/experiments/nlp-runtime-v2-architecture.md
- experiments/nlp_gate_modernbert/README.md
- experiments/nlp_gate_modernbert/pyproject.toml
- experiments/nlp_gate_modernbert/.gitignore
- experiments/nlp_gate_modernbert/artifacts/.gitkeep
- experiments/nlp_gate_modernbert/src/nlp_gate_modernbert/__init__.py
- experiments/nlp_gate_modernbert/src/nlp_gate_modernbert/paths.py
- experiments/nlp_gate_modernbert/src/nlp_gate_modernbert/provenance.py
- experiments/nlp_gate_modernbert/tests/test_mb00_bootstrap.py
- experiments/nlp_gate_modernbert/evidence/mb00_provenance.json
- experiments/nlp_gate_modernbert/evidence/mb00_handoff.md

IMPLEMENTED:
- Saved Runtime V2 Codex execution plan + architecture appendix under docs/experiments/
- Created isolated experiments/nlp_gate_modernbert/ package boundary
- Pinned SLM-03 / corpus / schema / split / Qwen base / tokenizer / evidence SHA-256 hashes
- Recorded environment (Unsloth Studio Python/Torch/Transformers + GPU identity)
- Bootstrap tests for layout, imports, writable artifacts, hash invariants

NOT IMPLEMENTED:
- MB-01 gate corpus audit
- MB-02 deterministic resolver/fact projector
- MB-03 ModernBERT training
- MB-04/MB-05 evaluation/integration
- T5 / LangGraph / SLM-04
- Any production-path (src/wellplot) changes
- Any modification of SLM-03 adapter or evidence files

TESTS:
- command: cd experiments/nlp_gate_modernbert && PYTHONPATH=src \
    ../nlp_slm_01/.venv/bin/python -m pytest tests -q
  result: 6 passed

STATIC CHECKS:
- SLM-03 pinned hashes re-verified OK at handoff
- No torch/transformers/langgraph/t5 runtime deps in pyproject (MB-00)

MODEL/PROVIDER CALLS:
- count: 0

ARTIFACTS:
- experiments/nlp_gate_modernbert/evidence/mb00_provenance.json
- experiments/nlp_gate_modernbert/evidence/mb00_handoff.md

INVARIANTS VERIFIED:
- SLM-03 adapter_model.safetensors hash unchanged
- SLM-03 evidence JSON hashes unchanged
- Gold / schema / split hashes unchanged
- Experiment does not import into production

KNOWN LIMITATIONS:
- Working tree not committed; candidate SHA is starting SHA + uncommitted MB-00/docs changes
- Default system python lacks pytest; tests used experiments/nlp_slm_01/.venv
- Remote upstream SHA not confirmed (branch may be local-only)

WORKING TREE: dirty (docs/experiments + experiments/nlp_gate_modernbert + pre-existing untracked experiments/nlp_slm_01)
REMOTE MATCH: unknown / not verified
STATUS: STOP FOR INDEPENDENT REVIEW
```

Do **not** authorize MB-01 until this handoff is accepted.
