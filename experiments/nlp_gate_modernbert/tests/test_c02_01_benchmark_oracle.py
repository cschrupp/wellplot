"""C02-01: immutable six-case benchmark, taxonomy, partitions, deterministic evaluators."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from nlp_gate_modernbert.decomposer_pilot.pilot_01.constants import INVOCATION_ORDER
from nlp_gate_modernbert.nl_program_eval.compare import FAILURE_LABELS
from nlp_gate_modernbert.nl_program_eval.evaluate import evaluate_raw_candidate
from nlp_gate_modernbert.nl_program_eval.freeze import FreezeFailure, freeze_candidate
from nlp_gate_modernbert.paths import EVIDENCE_DIR
from nlp_gate_modernbert.scope_runtime.replay import load_witnesses

DC02 = EVIDENCE_DIR / "decomposer_capability_02"
C02_01 = DC02 / "c02_01"


def _oracle_clean(case_id: str) -> dict:
    w = next(x for x in load_witnesses() if x["case_id"] == case_id)
    tasks = []
    for t in w["normalized_program"]["tasks"]:
        tasks.append(
            {
                "task_id": t["task_id"],
                "depends_on": list(t.get("depends_on") or []),
                "produces_binds": dict(t.get("produces_binds") or {}),
                "request": deepcopy(t["request"]),
            }
        )
    return {"version": w["normalized_program"].get("version"), "tasks": tasks}


def test_oracle_self_equivalent_all_six() -> None:
    for case_id in INVOCATION_ORDER:
        ev = evaluate_raw_candidate(case_id, _oracle_clean(case_id))
        assert ev.freeze_status == "FROZEN"
        assert ev.semantically_equivalent is True
        assert ev.failure_labels == []


def test_empty_program_not_equivalent() -> None:
    ev = evaluate_raw_candidate("D5GAP-0096", {"version": None, "tasks": []})
    assert ev.semantically_equivalent is False
    assert ev.failure_labels  # at least one semantic failure


def test_schema_invalid_is_structural() -> None:
    raw = _oracle_clean("D5GAP-0101")
    raw["unexpected_field"] = True
    frozen = freeze_candidate(raw)
    assert isinstance(frozen, FreezeFailure)
    assert frozen.failure == "DECOMPOSITION_SCHEMA_INVALID"


def test_failure_taxonomy_preserves_harness_labels() -> None:
    tax = json.loads((C02_01 / "failure_taxonomy.json").read_text())
    assert tax["semantic_failure_labels"] == list(FAILURE_LABELS)
    structural = {x["label"] for x in tax["structural_failure_labels"]}
    assert "DECOMPOSITION_DECODE_FAILURE" in structural
    assert "DECOMPOSITION_SCHEMA_INVALID" in structural


def test_benchmark_manifest_matches_invocation_order_and_c02_00() -> None:
    bench = json.loads((C02_01 / "benchmark_manifest.json").read_text())
    assert bench["invocation_order"] == list(INVOCATION_ORDER)
    assert bench["gold_cases_unchanged_by_deepseek_amendment"] is True
    c00 = json.loads(
        (DC02 / "c02_00" / "recovered_pilot_manifest.json").read_text()
    )
    c00_by = {c["case_id"]: c for c in c00["recovered_cases"]}
    for case in bench["cases"]:
        assert case["decomposer_input_sha256"] == c00_by[case["case_id"]][
            "decomposer_input_sha256"
        ]
        assert case["oracle_self_equivalent"] is True
        ref = json.loads((C02_01 / "oracle_refs" / f"{case['case_id']}.json").read_text())
        assert ref["cleaned_program_sha256"] == case["oracle_cleaned_program_sha256"]


def test_partition_design_has_frozen_pilot_and_empty_future_sets() -> None:
    splits = json.loads((C02_01 / "split_manifest.json").read_text())
    assert splits["dataset_expansion"] == "NOT_AUTHORIZED_IN_C02_01"
    hist = splits["partitions"]["historical_pilot_six"]
    assert hist["case_ids"] == list(INVOCATION_ORDER)
    for name in ("development_diagnostic", "training_corpus", "validation", "sealed_final"):
        assert splits["partitions"][name]["case_ids"] == []


def test_model_inventory_includes_deepseek_without_authorizing_calls() -> None:
    inv = json.loads((DC02 / "model_inventory.json").read_text())
    assert inv["amendment"] == "WP-DC02-MODEL-INVENTORY-AMEND-001"
    deepseek = next(m for m in inv["models"] if m["id"] == "deepseek-v4.1-flash-1017")
    assert deepseek["openrouter_model_id"] == "deepseek/deepseek-v4.1-flash-1017"
    assert deepseek["role"] == "budget_capability_reference"
    assert deepseek["training_eligible"] is False
    assert "any_model_calls" in inv["does_not_authorize"]


def test_metrics_reproducibility_marks_rendered_hash_deferred() -> None:
    metrics = json.loads((C02_01 / "metrics_reproducibility.json").read_text())
    deferred_names = {d["metric"] for d in metrics["deferred"]}
    assert "rendered_model_input_sha256_live_reverification" in deferred_names
    assert "gemini_openrouter_endpoint_identity" in deferred_names
    repro = {r["metric"] for r in metrics["reproducible_now"]}
    assert "oracle_self_semantic_equivalence" in repro
