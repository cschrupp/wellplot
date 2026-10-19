"""C02-00: recovered six-case digests must match frozen preflight + Run 1 hashes."""

from __future__ import annotations

import json
from pathlib import Path

from nlp_gate_modernbert.decomposer_pilot.pilot_01.constants import INVOCATION_ORDER
from nlp_gate_modernbert.decomposer_pilot import workspace_serialize
from nlp_gate_modernbert.nl_program_eval.input import build_decomposer_input
from nlp_gate_modernbert.paths import EVIDENCE_DIR


def _sha256_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_c02_00_six_case_inputs_match_frozen_preflight_and_run1() -> None:
    case_hashes = json.loads(
        (EVIDENCE_DIR / "decomposer_pilot_constraint_xgrammar_preflight_01_case_hashes.json").read_text()
    )
    frozen = {c["case_id"]: c for c in case_hashes["cases"]}
    results = [
        json.loads(line)
        for line in (EVIDENCE_DIR / "decomposer_pilot_01_results.jsonl").read_text().splitlines()
        if line.strip()
    ]
    by_id = {r["case_id"]: r for r in results}
    assert [r["case_id"] for r in results] == list(INVOCATION_ORDER)

    for case_id in INVOCATION_ORDER:
        di = build_decomposer_input(case_id)
        ws_json = workspace_serialize.serialize_projected_workspace(di.projected_workspace)
        di_sha = _sha256_text(
            json.dumps(
                {"utterance": di.utterance, "projected_workspace_json": ws_json},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        )
        assert di_sha == frozen[case_id]["decomposer_input_sha256"]
        assert di_sha == by_id[case_id]["input_hashes"]["decomposer_input_sha256"]


def test_c02_00_manifest_exists_and_claims_zero_model_calls() -> None:
    manifest = json.loads(
        (
            EVIDENCE_DIR
            / "decomposer_capability_02"
            / "c02_00"
            / "recovered_pilot_manifest.json"
        ).read_text()
    )
    assert manifest["slice"] == "C02-00"
    assert manifest["model_calls"] == 0
    assert manifest["openrouter_calls"] == 0
    assert manifest["synthetic_recreation"] is False
    assert len(manifest["recovered_cases"]) == 6
