"""CM-57IB deterministic pre-live input-boundary harness tests."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest
from scripts.cm57_input_boundary_experiment import (
    ARM_ORDER,
    ATTEMPTS,
    CASE_CORPUS_SHA256,
    DESIGN_BASELINE_SHA,
    EVALUATION_CONTRACT_SHA256,
    EVALUATOR_SHA256,
    EXPERIMENT_VERSION,
    FROZEN_MODEL,
    OUTPUT_PATH,
    REPRESENTATION_CASES,
    REQUEST_FIELD,
    RESPONSE_SCHEMA_SHA256,
    SEMANTIC_FIELD,
    TYPED_SECTION_SYSTEM_PROMPT,
    _canonical_json,
    _sha256,
    aggregate_rows,
    arm_isolation_flags,
    build_arm_inputs,
    build_arm_prompts,
    build_evidence_row,
    build_pre_live_metadata,
    ensure_empty_evidence_path,
    harness_source_sha256,
    select_production_semantic_metadata,
    semantic_metadata_projection_sha256,
    validate_authorized_checkpoint,
    validate_frozen_artifacts,
    validate_frozen_execution_controls,
    validate_production_metadata,
)

from wellplot.capabilities import create_builtin_registry


def _contract() -> tuple[dict[str, object], ...]:
    return select_production_semantic_metadata(("binding.raster",), create_builtin_registry())


def _inputs(*, contracts: tuple[dict[str, object], ...] | None = None) -> dict[str, str]:
    return build_arm_inputs(
        _canonical_json({"section_task": {"capability_ids": ["binding.raster"]}}),
        request=("Create a raster from /secret/input.dlis and preserve C:\\secret\\input.dlis."),
        contracts=_contract() if contracts is None else contracts,
    )


def _arm(statuses: dict[str, str]) -> dict[str, object]:
    return {
        "provider_call_completed": True,
        "structured_valid": True,
        "context_valid": True,
        "compiler_valid": True,
        "semantic_accepted": all(status == "PASS" for status in statuses.values()),
        "leaf_statuses": statuses,
    }


def _population(
    *,
    p: dict[str, str],
    r: dict[str, str] | None = None,
    s: dict[str, str] | None = None,
    rs: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    """Build a complete synthetic five-case by three-attempt population."""
    statuses = {"P": p, "R": r or p, "S": s or p, "RS": rs or p}
    rows: list[dict[str, object]] = []
    for case_id in REPRESENTATION_CASES:
        for attempt_index in range(ATTEMPTS):
            rows.append(
                {
                    "case_id": case_id,
                    "attempt_index": attempt_index,
                    "input_sufficiency": {"all_arms_sufficient": True},
                    "variant_flags": {
                        "request_only_diff": True,
                        "semantic_only_diff": True,
                        "future_contract_only_diff": True,
                    },
                    "arms": {arm: _arm(statuses[arm]) for arm in ARM_ORDER},
                }
            )
    return rows


_SCALE_PASS = {
    "tracks[0].x_scale.minimum": "PASS",
    "tracks[0].bindings[0].scale.minimum": "PASS",
}
_TARGET_FAIL = {
    "tracks[0].bindings[0].profile": "MISSING",
    "tracks[0].bindings[0].sample_axis.tick_count": "MISSING",
}
_TARGET_PASS = {
    "tracks[0].bindings[0].profile": "PASS",
    "tracks[0].bindings[0].sample_axis.tick_count": "PASS",
}


def test_production_projection_is_authoritative_and_exact() -> None:
    """S/RS source metadata comes from CapabilitySpec, not historical JSON."""
    registry = create_builtin_registry()
    audit = validate_production_metadata(registry)
    projection = audit["projection"]

    assert audit["metadata_source"] == "CapabilitySpec.semantic_metadata"
    assert audit["target_paths"] == [
        "binding.profile",
        "binding.sample_axis.source_origin",
        "binding.sample_axis.source_step",
        "binding.sample_axis.tick_count",
        "binding.sample_axis.unit",
    ]
    assert semantic_metadata_projection_sha256(projection) == audit["projection_sha256"]
    assert (
        "CM-56R8R-S1-selective-semantic-contracts.json"
        not in Path("scripts/cm57_input_boundary_experiment.py").read_text()
    )


def test_metadata_selection_preserves_task_order_and_deduplicates() -> None:
    """Capability selection is canonical, task-ordered, and non-fuzzy."""
    selected = select_production_semantic_metadata(
        ("track.normal", "raster", "binding.raster", "binding.raster"),
        create_builtin_registry(),
    )
    assert [item["capability_id"] for item in selected] == ["binding.raster"]


def test_arm_inputs_are_exact_factorial_compositions_and_redact_paths() -> None:
    """P/R/S/RS differ only by their authorized fields."""
    inputs = _inputs()
    flags = arm_isolation_flags(inputs)

    assert all(
        flags[name] is True
        for name in (
            "request_only_diff",
            "semantic_only_diff",
            "future_contract_only_diff",
            "rs_without_request_equals_s",
            "rs_without_semantic_equals_r",
        )
    )
    assert REQUEST_FIELD not in json.loads(inputs["P"])
    assert SEMANTIC_FIELD not in json.loads(inputs["R"])
    assert REQUEST_FIELD not in json.loads(inputs["S"])
    assert REQUEST_FIELD in json.loads(inputs["RS"])
    assert SEMANTIC_FIELD in json.loads(inputs["RS"])
    assert "/secret/input.dlis" not in inputs["R"]
    assert "C:\\secret\\input.dlis" not in inputs["R"]
    assert "[redacted-path]" in inputs["R"]
    assert inputs["P"] == _canonical_json(json.loads(inputs["P"]))


def test_scalar_control_collapses_metadata_arms_without_forcing_empty_contracts() -> None:
    """When no capability owns metadata, S=P and RS=R structurally."""
    base = _canonical_json({"section_task": {"capability_ids": ["track.normal"]}})
    inputs = build_arm_inputs(base, request="Create a scalar track.", contracts=())
    flags = arm_isolation_flags(inputs)
    prompts = build_arm_prompts(semantic_applicable=False)

    assert inputs["P"] == inputs["S"]
    assert inputs["R"] == inputs["RS"]
    assert flags["P_equals_S"] is True
    assert flags["R_equals_RS"] is True
    assert SEMANTIC_FIELD not in inputs["S"]
    assert prompts["S"] == TYPED_SECTION_SYSTEM_PROMPT
    assert prompts["RS"].endswith(
        "authoritative request, but do not invent semantics absent from it."
    )


def test_prompt_composition_is_exact_and_ordered() -> None:
    """RS is the composition of the two isolated prompt interventions."""
    prompts = build_arm_prompts(semantic_applicable=True)

    assert prompts["P"] == TYPED_SECTION_SYSTEM_PROMPT
    assert prompts["R"].startswith(prompts["P"])
    assert prompts["S"].startswith(prompts["P"])
    assert prompts["RS"].startswith(prompts["R"])
    assert prompts["RS"].endswith(prompts["S"][len(prompts["P"]) :])
    assert len({_sha256(value) for value in prompts.values()}) == 4


def test_pre_live_metadata_freezes_all_provenance_without_provider_calls() -> None:
    """The default harness path is deterministic and provider-free."""
    metadata = build_pre_live_metadata()

    assert metadata["experiment_version"] == EXPERIMENT_VERSION
    assert metadata["design_baseline_sha"] == DESIGN_BASELINE_SHA
    assert metadata["provider_calls"] == 0
    assert metadata["production_changes"] == 0
    assert metadata["cases"] == list(REPRESENTATION_CASES)
    assert metadata["attempts_per_case"] == 3
    assert metadata["future_worker_calls"] == 60
    assert metadata["request_field"] == REQUEST_FIELD
    assert metadata["semantic_field"] == SEMANTIC_FIELD
    assert metadata["artifacts"]["case_corpus_sha256"] == CASE_CORPUS_SHA256
    assert metadata["artifacts"]["response_schema_sha256"] == RESPONSE_SCHEMA_SHA256
    assert metadata["artifacts"]["evaluation_contract_sha256"] == EVALUATION_CONTRACT_SHA256
    assert metadata["artifacts"]["evaluator_source_sha256"] == EVALUATOR_SHA256


def test_checkpoint_controls_and_nonempty_evidence_fail_closed(tmp_path: Path) -> None:
    """Future provider construction is gated by exact provenance and controls."""
    for value in (None, "short", "g" * 40, "A" * 40):
        with pytest.raises(ValueError):
            validate_authorized_checkpoint(value)
    with pytest.raises(ValueError):
        validate_frozen_execution_controls(Namespace(model="wrong"))
    with pytest.raises(ValueError):
        validate_frozen_execution_controls(Namespace(model=FROZEN_MODEL, attempts=4))

    evidence = tmp_path / "evidence.jsonl"
    evidence.write_text("existing\n")
    with pytest.raises(FileExistsError):
        ensure_empty_evidence_path(evidence)
    assert OUTPUT_PATH.name == "cm57ib-live-qwen.jsonl"


def test_hash_and_artifact_guards_are_deterministic() -> None:
    """Frozen artifacts and exact harness bytes are checked before future live use."""
    registry = create_builtin_registry()
    assert validate_frozen_artifacts(registry)["production_metadata_projection_sha256"]
    assert len(harness_source_sha256()) == 64
    assert harness_source_sha256() == harness_source_sha256()


def test_complete_row_contains_bounded_provenance_only() -> None:
    """A future row can be serialized without retaining raw requests or payloads."""
    registry = create_builtin_registry()
    artifact_metadata = validate_frozen_artifacts(registry)
    inputs = _inputs()
    prompts = build_arm_prompts(semantic_applicable=True)
    flags = arm_isolation_flags(inputs)
    result = _arm({**_SCALE_PASS, **_TARGET_PASS})
    row = build_evidence_row(
        case_id="scalar_linear",
        attempt_index=0,
        model=FROZEN_MODEL,
        authorized_checkpoint="a" * 40,
        artifact_metadata=artifact_metadata,
        request="Use /secret/request.txt.",
        selected_capability_ids=("binding.raster",),
        selected_source_ids=("raster-source",),
        inputs=inputs,
        prompts=prompts,
        input_sufficiency={"all_arms_sufficient": True},
        flags=flags,
        arms=dict.fromkeys(ARM_ORDER, result),
        elapsed_ms=1.0,
    )
    serialized = json.dumps(row, sort_keys=True)
    assert "/secret/request.txt" not in serialized
    assert "provider_response" not in serialized
    assert row["arm_order"] == list(ARM_ORDER)
    assert row["metadata_source"] == "CapabilitySpec.semantic_metadata"


def test_full_future_contract_validation_decision() -> None:
    """A complete RS target recovery with no scale regression validates the future input."""
    result = aggregate_rows(
        _population(
            p={**_SCALE_PASS, **_TARGET_FAIL},
            s={**_SCALE_PASS, **_TARGET_PASS},
            rs={**_SCALE_PASS, **_TARGET_PASS},
        )
    )
    assert result["decision"] == "FUTURE_TYPED_INPUT_VALIDATED"


def test_scale_regression_dominates_future_contract_decision() -> None:
    """Protected generic scale regressions dominate target recovery."""
    rs = {**_SCALE_PASS, **_TARGET_PASS}
    rs["tracks[0].bindings[0].scale.minimum"] = "WRONG_VALUE"
    result = aggregate_rows(
        _population(
            p={**_SCALE_PASS, **_TARGET_FAIL},
            r={**_SCALE_PASS, **_TARGET_FAIL},
            s={**_SCALE_PASS, **_TARGET_PASS},
            rs=rs,
        )
    )
    assert result["decision"] == "FUTURE_TYPED_INPUT_REGRESSION"
    assert result["protected_scale_regressions"] > 0


def test_partial_and_incomplete_future_contract_decisions() -> None:
    """Remaining target failures are partial; missing rows are inconclusive."""
    partial = aggregate_rows(
        _population(
            p={**_SCALE_PASS, **_TARGET_FAIL},
            rs={
                **_SCALE_PASS,
                "tracks[0].bindings[0].profile": "PASS",
                "tracks[0].bindings[0].sample_axis.tick_count": "MISSING",
            },
        )
    )
    assert partial["decision"] == "FUTURE_TYPED_INPUT_PARTIAL"
    assert aggregate_rows([])["decision"] == "INCONCLUSIVE_INPUT_BOUNDARY"


def test_request_and_metadata_contribution_classifications_are_separate() -> None:
    """Factor classifications use their own direct comparisons."""
    result = aggregate_rows(
        _population(
            p={**_SCALE_PASS, **_TARGET_FAIL},
            r={**_SCALE_PASS, **_TARGET_PASS},
            s={**_SCALE_PASS, **_TARGET_PASS},
            rs={**_SCALE_PASS, **_TARGET_PASS},
        )
    )
    assert result["request_contribution"] == "REQUEST_CONTRIBUTES"
    assert result["metadata_contribution"] == "METADATA_CONTRIBUTES"
