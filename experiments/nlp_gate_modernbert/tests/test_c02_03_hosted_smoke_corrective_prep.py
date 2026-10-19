"""Offline corrective prep: cost dual fields + Gemini schema classification."""

from __future__ import annotations

import json

from nlp_gate_modernbert.decomposer_capability_02.cost_accounting import dual_cost_record
from nlp_gate_modernbert.decomposer_capability_02.cost_card import load_cost_card
from nlp_gate_modernbert.decomposer_capability_02.registry import (
    GEMINI_PROVIDER_ORDER,
    OPENROUTER_GEMINI_4_ARGON,
)
from nlp_gate_modernbert.nl_program_eval.evaluate import evaluate_raw_candidate
from nlp_gate_modernbert.nl_program_eval.freeze import FreezeFailure, freeze_candidate
from nlp_gate_modernbert.paths import EVIDENCE_DIR

SMOKE = EVIDENCE_DIR / "decomposer_capability_02" / "c02_03_joint_hosted_smoke"
PREP = EVIDENCE_DIR / "decomposer_capability_02" / "c02_03_hosted_smoke_corrective_prep"


def test_gemini_archived_response_is_schema_invalid_not_semantic_compare() -> None:
    fa = (SMOKE / "gemini" / "final_answer.json").read_text(encoding="utf-8")
    frozen = freeze_candidate(fa.encode("utf-8"))
    assert isinstance(frozen, FreezeFailure)
    assert frozen.failure == "DECOMPOSITION_SCHEMA_INVALID"
    ev = evaluate_raw_candidate("D5GAP-0085", fa)
    assert ev.schema_valid is False
    assert ev.freeze_status == "DECOMPOSITION_SCHEMA_INVALID"
    # Field is false, but must not be treated as completed semantic Layer-1.
    assert ev.semantically_equivalent is False
    cls = json.loads((PREP / "gemini_schema_classification.json").read_text())
    assert cls["reached_freeze"] is False
    assert "completed Layer-1" in cls["interpretation"] or "completed Layer-1" in cls["interpretation"].replace(
        "Layer 1", "Layer-1"
    )


def test_dual_cost_uses_provider_reported_as_observed() -> None:
    g = json.loads((SMOKE / "gemini" / "generation_summary.json").read_text())
    card = load_cost_card(
        openrouter_model_id=OPENROUTER_GEMINI_4_ARGON,
        pinned_provider=GEMINI_PROVIDER_ORDER[0],
    )
    rec = dual_cost_record(
        cost_card=card,
        prompt_tokens=g["prompt_tokens"],
        completion_tokens=g["completion_tokens"],
        raw_usage=g["raw_usage"],
    )
    assert rec["provider_reported_usd"] == g["raw_usage"]["cost"]
    assert abs(rec["reported_over_estimate_ratio"] - 2.0) < 1e-9


def test_deepseek_corrective_config_pins_4096_and_keeps_original_immutable() -> None:
    cfg = json.loads((PREP / "deepseek_corrective_config.json").read_text())
    assert cfg["proposed_request_overrides"]["max_tokens"] == 4096
    assert cfg["proposed_request_overrides"]["reasoning"]["effort"] == "low"
    assert cfg["original_smoke_observation"] == "RETAINED_IMMUTABLE"
    assert cfg["additional_api_calls_authorized_by_this_prep"] == 0
    readiness = json.loads((PREP / "corrective_readiness.json").read_text())
    assert readiness["live_inference_calls"] == 0
    assert readiness["corrective_deepseek_smoke_authorized"] is False
