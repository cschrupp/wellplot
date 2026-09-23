"""Deterministic CM-56R8R corrected-evaluation tests."""

from __future__ import annotations

import json

import pytest
from scripts.cm56_typed_section_shadow import case_corpus_sha256, load_case_definitions
from scripts.cm56r8r_semantic_contract_correction import (
    _SCALE_DEFAULTS,
    BASELINE_SHA,
    CASE_CORPUS_SHA256,
    EVALUATION_CONTRACT_VERSION,
    EVALUATOR_VERSION,
    MAX_OUTPUT_TOKENS,
    PLANNER_TEMPERATURE,
    REPRESENTATION_CASES,
    RESPONSE_SCHEMA_SHA256,
    TIMEOUT_SECONDS,
    WORKER_TEMPERATURE,
    build_contract_system_prompt,
    build_contract_worker_input,
    corrected_expected_for_case,
    evaluate_semantic_draft_r8r,
    load_evaluation_contract,
    load_semantic_contracts,
    normalize_sample_axis,
    normalize_scale,
    semantic_contract_only_differs,
)

from wellplot.agent.code_mode.section_semantics import (
    ArrayTrackSemanticDraft,
    CurveBindingSemanticDraft,
    NormalTrackSemanticDraft,
    RasterBindingSemanticDraft,
    SectionSemanticDraft,
    SemanticSampleAxis,
    SemanticScale,
)


def _curve_draft(*, scale: SemanticScale | None) -> SectionSemanticDraft:
    """Build a synthetic scalar draft for leaf-level evaluator tests."""
    return SectionSemanticDraft(
        title="Calibration",
        source_candidate="source-1",
        tracks=(
            NormalTrackSemanticDraft(
                semantic_id="calibration",
                kind="normal",
                title="Calibration",
                bindings=(
                    CurveBindingSemanticDraft(
                        semantic_id="calx",
                        channel="CALX",
                        scale=scale,
                    ),
                ),
            ),
        ),
    )


def _curve_expected(scale: dict[str, object]) -> dict[str, object]:
    """Build a synthetic expected scalar semantic projection."""
    return {
        "title": "Calibration",
        "source_candidate": "source-1",
        "tracks": [
            {
                "kind": "normal",
                "title": "Calibration",
                "bindings": [{"kind": "curve", "channel": "CALX", "scale": scale}],
            }
        ],
    }


def _mapping_targets(artifact: dict[str, object], capability_id: str) -> list[dict[str, object]]:
    """Return machine-readable mapping targets for one capability."""
    contract = next(
        contract for contract in artifact["contracts"] if contract["capability_id"] == capability_id
    )
    return [mapping["targets"] for mapping in contract["mappings"]]


def test_scale_defaults_are_normalized_symmetrically() -> None:
    """Expected partial scales compare equal to generated semantic defaults."""
    expected = _curve_expected({"minimum": 0, "maximum": 150})
    actual = _curve_draft(scale=SemanticScale(minimum=0, maximum=150, kind="linear", reverse=False))
    evaluation = evaluate_semantic_draft_r8r(actual, expected=expected)
    assert evaluation.accepted
    assert evaluation.leaf_statuses["tracks[0].bindings[0].scale.kind"] == "PASS"
    assert evaluation.leaf_statuses["tracks[0].bindings[0].scale.reverse"] == "PASS"
    assert normalize_scale({"minimum": 0, "maximum": 150}) == normalize_scale(
        {"kind": "linear", "minimum": 0, "maximum": 150, "reverse": False}
    )
    assert _SCALE_DEFAULTS == {"kind": "linear", "reverse": False}


@pytest.mark.parametrize(
    ("expected_scale", "actual_scale", "failed_leaf"),
    [
        (
            {"minimum": 0, "maximum": 150},
            {"minimum": 0, "maximum": 100},
            "tracks[0].bindings[0].scale.maximum",
        ),
        (
            {"kind": "log", "minimum": 1, "maximum": 100},
            {"kind": "linear", "minimum": 1, "maximum": 100},
            "tracks[0].bindings[0].scale.kind",
        ),
        (
            {"minimum": 200, "maximum": 0, "reverse": True},
            {"minimum": 200, "maximum": 0, "reverse": False},
            "tracks[0].bindings[0].scale.reverse",
        ),
    ],
)
def test_scale_semantic_errors_remain_rejections(
    expected_scale: dict[str, object],
    actual_scale: dict[str, object],
    failed_leaf: str,
) -> None:
    """Normalization removes only default noise, never scientific differences."""
    evaluation = evaluate_semantic_draft_r8r(
        _curve_draft(scale=SemanticScale.model_validate(actual_scale)),
        expected=_curve_expected(expected_scale),
    )
    assert not evaluation.accepted
    assert evaluation.leaf_statuses[failed_leaf] == "WRONG_VALUE"


def test_all_production_scale_kinds_normalize() -> None:
    """Linear, logarithmic, and tangential scales remain supported."""
    for kind in ("linear", "log", "tangential"):
        value = {"kind": kind, "minimum": 1, "maximum": 10}
        assert normalize_scale(value)["kind"] == kind


def test_scale_units_are_preserved() -> None:
    """Explicit scale units are semantic leaves, not discarded metadata."""
    normalized = normalize_scale({"minimum": 1, "maximum": 10, "unit": "synthetic-unit"})
    assert normalized["unit"] == "synthetic-unit"


def test_track_x_scale_uses_the_same_symmetric_normalization() -> None:
    """Array-track x-scale defaults receive the same comparison treatment."""
    draft = SectionSemanticDraft(
        title="Array View",
        source_candidate="source-1",
        tracks=(
            ArrayTrackSemanticDraft(
                semantic_id="array",
                kind="array",
                title="Array View",
                x_scale=SemanticScale(minimum=10, maximum=90),
                bindings=(
                    RasterBindingSemanticDraft(
                        semantic_id="array-q",
                        channel="ARRAY_Q",
                        profile="generic",
                    ),
                ),
            ),
        ),
    )
    expected = {
        "title": "Array View",
        "source_candidate": "source-1",
        "tracks": [
            {
                "kind": "array",
                "title": "Array View",
                "x_scale": {"minimum": 10, "maximum": 90},
                "bindings": [{"kind": "raster", "channel": "ARRAY_Q", "profile": "generic"}],
            }
        ],
    }
    evaluation = evaluate_semantic_draft_r8r(draft, expected=expected)
    assert evaluation.accepted
    assert evaluation.leaf_statuses["tracks[0].x_scale.kind"] == "PASS"


def test_sample_axis_normalization_preserves_explicit_leaves() -> None:
    """Sample-axis values are normalized without injecting compiler defaults."""
    normalized = normalize_sample_axis(
        {
            "unit": "ms",
            "source_origin": 12,
            "source_step": 2,
            "tick_count": 5,
        }
    )
    assert normalized == {
        "unit": "ms",
        "source_origin": 12.0,
        "source_step": 2.0,
        "tick_count": 5,
    }


def test_sample_axis_leaf_statuses_distinguish_missing_wrong_and_extra() -> None:
    """Sample-axis leaves are independently auditable."""
    expected = {
        "title": "Array View",
        "source_candidate": "source-1",
        "tracks": [
            {
                "kind": "array",
                "title": "Array View",
                "x_scale": {"minimum": 10, "maximum": 90},
                "bindings": [
                    {
                        "kind": "raster",
                        "channel": "ARRAY_Q",
                        "profile": "waveform",
                        "sample_axis": {
                            "unit": "ms",
                            "source_origin": 12,
                            "source_step": 2,
                            "tick_count": 5,
                        },
                    }
                ],
            }
        ],
    }
    actual = SectionSemanticDraft(
        title="Array View",
        source_candidate="source-1",
        tracks=(
            ArrayTrackSemanticDraft(
                semantic_id="array",
                kind="array",
                title="Array View",
                x_scale=SemanticScale(minimum=10, maximum=90),
                bindings=(
                    RasterBindingSemanticDraft(
                        semantic_id="array-q",
                        channel="ARRAY_Q",
                        profile="generic",
                        sample_axis=SemanticSampleAxis(
                            unit="ms",
                            source_origin=12,
                            source_step=3,
                            tick_count=5,
                            minimum=1,
                            maximum=2,
                        ),
                    ),
                ),
            ),
        ),
    )
    evaluation = evaluate_semantic_draft_r8r(actual, expected=expected)
    source_step_status = evaluation.leaf_statuses["tracks[0].bindings[0].sample_axis.source_step"]
    assert source_step_status == "WRONG_VALUE"
    assert "tracks[0].bindings[0].sample_axis.minimum" in evaluation.unrequested_semantics
    assert "tracks[0].bindings[0].sample_axis.maximum" in evaluation.unrequested_semantics


def test_vdl_overlay_removes_only_unsupported_sample_axis_bounds() -> None:
    """The declarative VDL policy keeps x-scale and explicit axis facts distinct."""
    evaluation_contract, _ = load_evaluation_contract()
    case = next(case for case in load_case_definitions() if case["case_id"] == "vdl_sample_axis")
    expected = corrected_expected_for_case(case, evaluation_contract)
    track = expected["tracks"][0]
    assert track["x_scale"] == {"minimum": 200, "maximum": 1200}
    assert track["bindings"][0]["sample_axis"] == {
        "unit": "us",
        "source_origin": 40,
        "source_step": 10,
        "tick_count": 7,
    }


def test_contract_mappings_have_exact_target_paths() -> None:
    """Contract completeness is structural rather than substring-based."""
    artifact, _ = load_semantic_contracts()
    curve_targets = _mapping_targets(artifact, "binding.curve")
    assert {
        "binding.scale.kind",
        "binding.scale.minimum",
        "binding.scale.maximum",
    } <= set().union(*(targets.keys() for targets in curve_targets))
    assert {"binding.scale.reverse": True} in curve_targets
    array_targets = _mapping_targets(artifact, "track.array")
    assert {
        "track.x_scale.kind",
        "track.x_scale.minimum",
        "track.x_scale.maximum",
    } <= set().union(*(targets.keys() for targets in array_targets))
    raster_targets = _mapping_targets(artifact, "binding.raster")
    required_raster = {
        "binding.profile",
        "binding.sample_axis.unit",
        "binding.sample_axis.source_origin",
        "binding.sample_axis.source_step",
        "binding.sample_axis.tick_count",
    }
    assert required_raster <= set().union(*(targets.keys() for targets in raster_targets))


def test_contract_has_no_sample_axis_typo_or_benchmark_leakage() -> None:
    """Corrected contracts remain generic and path-free."""
    artifact, _ = load_semantic_contracts()
    serialized = json.dumps(artifact, sort_keys=True)
    forbidden = (
        "source_axis",
        "scalar_linear",
        "reverse_scale",
        "generic_raster",
        "vdl_sample_axis",
        "cbl_continuity",
        "main-source",
        "repeat-source",
        "Gamma Ray",
        "CBL Amplitude",
        "200 to 1200",
        "0 to 150",
        "0 to 100",
        "5000",
        "canonical_path",
    )
    assert all(value not in serialized for value in forbidden)
    assert "/home/" not in serialized
    assert "/tmp/" not in serialized


def test_a_b_isolation_excludes_gold_and_expected_projection() -> None:
    """B adds only contracts; expected semantics never enter either payload."""
    artifact, _ = load_semantic_contracts()
    base = json.dumps(
        {
            "section_task": {
                "goal": "Create synthetic CALX.",
                "capability_ids": ["section.log_plot", "track.normal", "binding.curve"],
            },
            "sources": [
                {
                    "candidate_id": "source-1",
                    "channels": [{"mnemonic": "CALX", "kind": "scalar"}],
                }
            ],
            "authoritative_original_request": "Create CALX with a linear scale from -25 to 75.",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    contracts = [
        contract
        for contract in artifact["contracts"]
        if contract["capability_id"] in {"track.normal", "binding.curve"}
    ]
    variant_b = build_contract_worker_input(base, contracts=contracts)
    assert semantic_contract_only_differs(base, variant_b)
    assert "Hidden Benchmark Title" not in base
    assert "Hidden Benchmark Title" not in variant_b
    assert "expected_sections" not in base
    assert "expected_sections" not in variant_b


def test_prompt_is_bounded_and_uses_corrected_contract_instruction() -> None:
    """The prompt adds no gold or evaluator output."""
    prompt = build_contract_system_prompt()
    assert "source_axis" not in prompt
    assert "expected_sections" not in prompt
    assert "never copy example values" in prompt


def test_vdl_overlay_is_not_in_provider_contract() -> None:
    """Evaluation-only gold policy is separate from the provider contract."""
    artifact, _ = load_semantic_contracts()
    serialized = json.dumps(artifact, sort_keys=True)
    assert "explicit_request_only" not in serialized
    assert "remove_expected_paths" not in serialized


def test_frozen_case_and_schema_controls_remain_unchanged() -> None:
    """R8R uses the frozen CM-56 corpus and CM-55 response schema."""
    assert BASELINE_SHA == "17da03e"
    assert case_corpus_sha256() == CASE_CORPUS_SHA256
    assert RESPONSE_SCHEMA_SHA256 == (
        "93f1b7d26f1196a1105b733bc13a8de784da19f44eaaa990989d59abaf9fa2d4"
    )
    assert EVALUATION_CONTRACT_VERSION == "cm56r8r.semantic-evaluation.v1"
    assert EVALUATOR_VERSION == "cm56r8r.corrected-evaluator.v1"
    assert PLANNER_TEMPERATURE == 0.0
    assert WORKER_TEMPERATURE == 0.0
    assert MAX_OUTPUT_TOKENS == 16384
    assert TIMEOUT_SECONDS == 900.0
    assert REPRESENTATION_CASES == (
        "scalar_linear",
        "reverse_scale",
        "generic_raster",
        "waveform",
        "vdl_sample_axis",
    )
