"""C02-03 design invariants: Gemini ceiling protocol frozen; zero inference."""

from __future__ import annotations

import json

from nlp_gate_modernbert.decomposer_pilot import prompt_contract
from nlp_gate_modernbert.decomposer_pilot.pilot_01.constants import INVOCATION_ORDER
from nlp_gate_modernbert.decomposer_capability_02.registry import OPENROUTER_GEMINI_4_ARGON
from nlp_gate_modernbert.paths import EVIDENCE_DIR

C02_03 = EVIDENCE_DIR / "decomposer_capability_02" / "c02_03"
G0 = EVIDENCE_DIR / "decomposer_capability_02" / "g0"


def test_c02_03_design_freezes_six_case_gemini_protocol_without_inference() -> None:
    d = json.loads((C02_03 / "design.json").read_text())
    assert d["slice"] == "C02-03"
    assert d["model_calls"] == 0
    assert d["openrouter_calls"] == 0
    assert d["code_execution_authorized"] is False
    assert d["model"]["openrouter_model_id"] == OPENROUTER_GEMINI_4_ARGON
    assert d["cases"]["invocation_order"] == list(INVOCATION_ORDER)
    assert d["prompt_preservation"]["system_prompt_sha256"] == prompt_contract.system_prompt_sha256()
    assert d["prompt_preservation"]["user_template_sha256"] == prompt_contract.user_template_sha256()
    assert d["decoding_regime"]["c02_03_gemini"]["hard_xgrammar_mask"] is False
    assert d["decoding_regime"]["c02_03_gemini"]["equivalence_to_pilot"] == "NOT_CLAIMED"
    assert d["retry_policy"]["semantic_retries"] == 0
    assert d["token_cost_accounting"]["charge_attempted_calls_on_parse_or_freeze_failure"] is True
    assert d["model"]["provider_pin_policy"]["required"] is True
    blocker_ids = {b["id"] for b in d["unresolved_execution_blockers"]}
    assert "B1_EXECUTION_AUTHORITY" in blocker_ids
    assert "B2_PROVIDER_PIN_IMPLEMENTATION" in blocker_ids
    assert "live_gemini_inference" in d["explicit_non_authorizations"]


def test_g0_closed_and_phase0_closed() -> None:
    acc = json.loads((G0 / "independent_review_acceptance.json").read_text())
    assert acc["status"] == "CLOSED"
    assert acc["phase0_status"] == "CLOSED"
    assert acc["accepted_tip"] == "2db64aa96549e96161ff8cb2e7df2f03c885be55"
