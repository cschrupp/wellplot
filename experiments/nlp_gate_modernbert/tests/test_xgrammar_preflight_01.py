"""DECOMPOSER-PILOT-CONSTRAINT-XGRAMMAR-PREFLIGHT-01 tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import torch

from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight import constants as C
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.adapter import (
    AdapterFailClosedError,
    PilotXGrammarHardMaskAdapter,
    compile_accepted_constraint_path,
)
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.case_hashes import (
    freeze_six_case_hashes,
)
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.identity import (
    verify_identities,
)
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.run_preflight import (
    AutoModelForbiddenError,
    GenerateForbiddenError,
    run_xgrammar_preflight,
)
from nlp_gate_modernbert.paths import EVIDENCE_DIR


def test_p1_identities_match():
    identity = verify_identities()
    assert identity["pass"] is True
    assert identity["grammar_sha256"] == C.WELL_EBNF1_SHA256


def test_adapter_synthetic_logits_and_fail_closed():
    identity = verify_identities()
    snap = identity["model_provenance"]["snapshot_path"]
    well = identity["grammar_bytes"].decode("utf-8")
    path = compile_accepted_constraint_path(well, snap)
    adapter = PilotXGrammarHardMaskAdapter(path)
    logits = torch.ones(path.vocab_size, dtype=torch.float32)
    masked = adapter.apply_synthetic_logits(logits.clone())
    assert torch.isneginf(masked).any()
    assert torch.isfinite(masked).any()

    adapter.reset()
    adapter.fill_next_token_bitmask()
    blocked = next(t for t in range(path.vocab_size) if not adapter._bit_allowed(t))
    with pytest.raises(AdapterFailClosedError):
        adapter.accept_token(blocked)


def test_six_case_hashes_clean(tmp_path: Path):
    identity = verify_identities()
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(
        identity["model_provenance"]["snapshot_path"], local_files_only=True
    )
    out = freeze_six_case_hashes(tok)
    assert out["pass"] is True
    assert [c["case_id"] for c in out["cases"]] == list(C.INVOCATION_ORDER)
    assert out["contamination_failures"] == []
    # Hashes only — no raw utterance persisted in evidence structure beyond sha
    for c in out["cases"]:
        assert "utterance" not in c
        assert "workspace_json" not in c
        assert c["case_id_in_model_input"] is False


def test_generate_and_automodel_guards():
    # Running preflight installs guards; probe them afterward via a fresh call.
    report = run_xgrammar_preflight(evidence_dir=EVIDENCE_DIR)
    assert report["model_calls"] == 0
    assert report["model_weights_loaded"] is False
    assert report["model_generate_calls"] == 0
    assert report["result"] == "PASS"
    assert all(report["gates"][g]["pass"] for g in report["gates"])

    from transformers.generation import GenerationMixin

    with pytest.raises(GenerateForbiddenError):
        GenerationMixin.generate(object())

    import transformers

    with pytest.raises(AutoModelForbiddenError):
        transformers.AutoModelForCausalLM.from_pretrained("x")


def test_evidence_artifacts_exist():
    for name in (
        "decomposer_pilot_constraint_xgrammar_preflight_01_run_manifest.json",
        "decomposer_pilot_constraint_xgrammar_preflight_01_parity.json",
        "decomposer_pilot_constraint_xgrammar_preflight_01_adapter.json",
        "decomposer_pilot_constraint_xgrammar_preflight_01_case_hashes.json",
        "decomposer_pilot_constraint_xgrammar_preflight_01.json",
        "decomposer_pilot_constraint_xgrammar_preflight_01.md",
    ):
        assert (EVIDENCE_DIR / name).is_file(), name
