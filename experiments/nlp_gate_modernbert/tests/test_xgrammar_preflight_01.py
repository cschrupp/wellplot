"""DECOMPOSER-PILOT-CONSTRAINT-XGRAMMAR-PREFLIGHT-01 / 01R tests."""

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
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.fail_closed import (
    run_fail_closed_suite,
)
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.identity import (
    verify_identities,
)
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.manifest_q6 import (
    REQUIRED_MODEL_FIELDS,
    validate_q6_run_manifest,
)
from nlp_gate_modernbert.decomposer_pilot.xgrammar_preflight.run_preflight import (
    AutoDownloadForbiddenError,
    AutoModelForbiddenError,
    ForwardForbiddenError,
    GenerateForbiddenError,
    run_xgrammar_preflight,
)
from nlp_gate_modernbert.paths import EVIDENCE_DIR


def test_p1_identities_preserve_full_model_fields():
    identity = verify_identities()
    assert identity["pass"] is True
    model = identity["model_provenance"]
    for field in REQUIRED_MODEL_FIELDS:
        assert field in model and model[field] is not None, field
    assert model["model_id"] == "Qwen/Qwen3-1.7B"
    assert model["adapters"] == "NONE"
    assert model["auto_download"] is False
    assert model["fallback_model"] == "NONE"


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


def test_six_case_hashes_clean():
    identity = verify_identities()
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(
        identity["model_provenance"]["snapshot_path"], local_files_only=True
    )
    out = freeze_six_case_hashes(tok)
    assert out["pass"] is True
    assert [c["case_id"] for c in out["cases"]] == list(C.INVOCATION_ORDER)
    assert out["contamination_failures"] == []
    for c in out["cases"]:
        assert "utterance" not in c
        assert "workspace_json" not in c
        assert c["case_id_in_model_input"] is False


def test_p7_fail_closed_adversarial_suite():
    identity = verify_identities()
    well = identity["grammar_bytes"].decode("utf-8")
    snap = identity["model_provenance"]["snapshot_path"]
    suite = run_fail_closed_suite(well_text=well, snapshot_path=snap)
    assert suite["pass"] is True, suite
    names = {c["name"] for c in suite["cases"]}
    assert "grammar_hash_mismatch" in names
    assert "missing_tokenizer_artifact" in names
    assert "native_grammar_sha_mismatch" in names
    assert "adapter_blocked_token" in names
    assert "contamination_detection" in names
    for c in suite["cases"]:
        assert c["zero_model_preserved"] is True
        assert c["pass"] is True


def test_p8_guards_block_concrete_qwen3_load_call_generate_download():
    report = run_xgrammar_preflight(evidence_dir=EVIDENCE_DIR)
    assert report["result"] == "PASS"
    assert report["slice"].endswith("01R2")
    assert report["model_calls"] == 0
    assert report["model_weights_loaded"] is False
    assert report["model_forward_calls"] == 0
    assert report["model_generate_calls"] == 0

    # Explicit P8 prevention evidence (not name-only)
    ge = report["p8_guard_evidence"]
    assert ge["pass"] is True
    assert ge["direct_concrete_model_load_blocked"] is True
    assert ge["subclass_model_invocation_blocked"] is True
    assert ge["generate_blocked"] is True
    assert ge["non_local_tokenizer_config_blocked"] is True

    # P2 field-level completeness
    assert report["p2_validation"]["pass"] is True
    for field in REQUIRED_MODEL_FIELDS:
        assert field in report["p2_validation"]["required_model_fields"]

    from transformers.generation import GenerationMixin
    from transformers import AutoTokenizer, Qwen3ForCausalLM
    import transformers

    with pytest.raises(GenerateForbiddenError):
        GenerationMixin.generate(object())

    with pytest.raises(AutoModelForbiddenError):
        transformers.AutoModelForCausalLM.from_pretrained("x")

    # Concrete pilot class — not Auto* factory
    with pytest.raises(AutoModelForbiddenError):
        Qwen3ForCausalLM.from_pretrained("Qwen/Qwen3-1.7B", local_files_only=True)

    # Subclass __call__ (bypasses overridden forward)
    stub = object.__new__(Qwen3ForCausalLM)
    with pytest.raises(ForwardForbiddenError):
        stub()

    with pytest.raises(AutoDownloadForbiddenError):
        AutoTokenizer.from_pretrained(
            report["identity"]["model_provenance"]["snapshot_path"],
            local_files_only=False,
        )


def test_p2_manifest_rejects_incomplete_model():
    incomplete = {
        "MODEL": {"snapshot_path": "/tmp"},
        "CONSTRAINT": {
            "backend": "xgrammar",
            "backend_version": C.REQUIRED_XGRAMMAR,
            "well_ebnf1_sha256": C.WELL_EBNF1_SHA256,
            "xgrammar_native_grammar_sha256": C.XGRAMMAR_NATIVE_GRAMMAR_SHA256,
        },
        "PROMPT": {"regime": "zero-shot", "system_prompt_sha256": "x", "user_template_sha256": "y"},
        "WORKSPACE_SERIALIZATION": {"implementation_sha256": "z"},
        "INFERENCE": {
            "temperature": 0,
            "do_sample": False,
            "thinking_enabled": False,
            "max_new_tokens": 1024,
            "seed": 20261016,
            "inference_config_sha256": "q",
        },
    }
    out = validate_q6_run_manifest(incomplete)
    assert out["pass"] is False
    assert any(e.startswith("model_missing:") for e in out["errors"])


def test_evidence_artifacts_exist():
    for name in (
        "decomposer_pilot_constraint_xgrammar_preflight_01_run_manifest.json",
        "decomposer_pilot_constraint_xgrammar_preflight_01_parity.json",
        "decomposer_pilot_constraint_xgrammar_preflight_01_adapter.json",
        "decomposer_pilot_constraint_xgrammar_preflight_01_case_hashes.json",
        "decomposer_pilot_constraint_xgrammar_preflight_01_fail_closed.json",
        "decomposer_pilot_constraint_xgrammar_preflight_01.json",
        "decomposer_pilot_constraint_xgrammar_preflight_01.md",
    ):
        assert (EVIDENCE_DIR / name).is_file(), name


def test_hf_processor_replay_in_adapter_evidence():
    import json

    adapter = json.loads(
        (
            EVIDENCE_DIR
            / "decomposer_pilot_constraint_xgrammar_preflight_01_adapter.json"
        ).read_text()
    )
    hf = adapter["hf_logits_processor"]
    assert hf["pass"] is True
    assert hf["progressive_valid_sequence"] is True
    assert hf["completed"] is True
    assert hf["stop_allowed"] is True
    assert hf["dual_replay_identical"] is True
    assert hf["generate_invoked"] is False
