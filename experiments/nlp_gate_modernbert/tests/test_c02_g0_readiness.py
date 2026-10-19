"""G0 readiness decision structure and non-authorization invariants."""

from __future__ import annotations

import json

from nlp_gate_modernbert.paths import EVIDENCE_DIR

G0 = EVIDENCE_DIR / "decomposer_capability_02" / "g0"


def test_g0_two_readiness_levels_and_no_inference() -> None:
    d = json.loads((G0 / "readiness_decision.json").read_text())
    assert d["slice"] == "G0"
    assert d["readiness_levels"]["phase0_technical_readiness"]["status"] == "READY"
    assert d["readiness_levels"]["live_scientific_execution_readiness"]["status"] == "NOT_ESTABLISHED"
    assert d["gate_disposition"]["authorize_inference"] is False
    assert d["gate_disposition"]["authorize_C02_03_execution"] is False
    assert d["gate_disposition"]["authorize_preparation_of_next_experimental_design"] is True
    assert d["model_calls"] == 0
    assert d["openrouter_calls"] == 0
    ids = {x["id"] for x in d["assessments"]["comparability_limitations"]["items"]}
    assert "decoding_parity" in ids
    assert "provider_routing_unpinning" in ids
