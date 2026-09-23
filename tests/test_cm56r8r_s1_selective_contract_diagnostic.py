"""Deterministic CM-56R8R-S1 pre-live harness tests."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest
from scripts.cm56r8r_s1_selective_contract_diagnostic import (
    ATTEMPTS,
    BASELINE_SHA,
    CASE_CORPUS_SHA256,
    EVALUATION_CONTRACT_SHA256,
    EVALUATOR_SHA256,
    EXPERIMENT_VERSION,
    FROZEN_MODEL,
    REPRESENTATION_CASES,
    RESPONSE_SCHEMA_SHA256,
    _mapping_targets,
    aggregate_s1_rows,
    build_pre_live_metadata,
    build_selective_system_prompt,
    build_selective_worker_input,
    ensure_empty_evidence_path,
    load_selective_contracts,
    selective_contract_only_differs,
    validate_frozen_execution_controls,
    validate_selective_contract_artifact,
)
from scripts.cm56r8r_semantic_contract_correction import (
    AUTHORITATIVE_REQUEST_SYSTEM_PROMPT,
)


def test_selective_contract_has_only_authorized_mappings() -> None:
    """Only raster profile and sample-axis targets are documented."""
    artifact, _ = load_selective_contracts()
    assert _mapping_targets(artifact) == [
        "binding.profile",
        "binding.sample_axis.unit",
        "binding.sample_axis.source_origin",
        "binding.sample_axis.source_step",
        "binding.sample_axis.tick_count",
    ]
    serialized = json.dumps(artifact, sort_keys=True)
    for phrase in ("0 to 150", "200 to 0", "0 to 200", "200 to 1200", "-25 to 75", "10 to 90"):
        assert phrase not in serialized


def test_selective_contract_keeps_track_and_sample_axis_distinction() -> None:
    """The distinction is present as contract metadata, not scale mappings."""
    artifact, _ = load_selective_contracts()
    contract = artifact["contracts"][0]
    distinctions = " ".join(contract["distinctions"])
    assert "track.x_scale" in distinctions
    assert "binding.sample_axis" in distinctions
    assert "Do not copy track.x_scale" in distinctions


def test_selective_contract_rejects_forbidden_mapping_targets() -> None:
    """Structural target inspection fails closed for any scale mapping."""
    artifact, _ = load_selective_contracts()
    altered = json.loads(json.dumps(artifact))
    altered["contracts"][0]["mappings"][0]["targets"] = {"binding.scale.minimum": "A"}
    with pytest.raises(ValueError, match="Forbidden"):
        validate_selective_contract_artifact(altered)


def test_a_and_s_payloads_differ_only_by_selective_contract_field() -> None:
    """S adds one structured field and receives no A output or evaluator data."""
    authoritative = json.dumps(
        {"authoritative_request": "Use the supplied source.", "worker_input": {"x": 1}},
        sort_keys=True,
        separators=(",", ":"),
    )
    artifact, _ = load_selective_contracts()
    selective = build_selective_worker_input(
        authoritative,
        contracts=artifact["contracts"],
    )
    assert selective_contract_only_differs(authoritative, selective)
    assert "expected_semantic_projection" not in selective
    assert "generated_semantic_projection" not in selective


def test_s_prompt_is_a_prompt_plus_only_bounded_instruction() -> None:
    """Prompt isolation keeps the intervention limited to selective contracts."""
    prompt = build_selective_system_prompt()
    assert prompt.startswith(AUTHORITATIVE_REQUEST_SYSTEM_PROMPT)
    assert "selective_semantic_contracts" in prompt
    for forbidden in ("reverse_scale", "R8R", "minimum/maximum problem", "expected answers"):
        assert forbidden not in prompt


def test_pre_live_metadata_freezes_provenance_and_expected_families() -> None:
    """Metadata is derived from frozen artifacts without provider execution."""
    metadata = build_pre_live_metadata()
    assert metadata["experiment_version"] == EXPERIMENT_VERSION
    assert metadata["authorized_checkpoint"] == BASELINE_SHA
    assert metadata["provider_calls"] == 0
    assert metadata["production_changes"] == 0
    assert metadata["corpus_sha256"] == CASE_CORPUS_SHA256
    assert metadata["response_schema_sha256"] == RESPONSE_SCHEMA_SHA256
    assert metadata["evaluation_contract_sha256"] == EVALUATION_CONTRACT_SHA256
    assert metadata["evaluator_source_sha256"] == EVALUATOR_SHA256
    assert set(metadata["expected_family_inventory"]) == set(REPRESENTATION_CASES)


def test_frozen_controls_and_cli_attempt_path() -> None:
    """The CLI has no mutable attempt option and uses the frozen value."""
    from scripts.cm56r8r_s1_selective_contract_diagnostic import _parser

    args = _parser().parse_args(
        [
            "--model",
            FROZEN_MODEL,
            "--base-url",
            "http://example.invalid/v1",
        ]
    )
    validate_frozen_execution_controls(args)
    assert not hasattr(args, "attempts")
    assert ATTEMPTS == 3


def test_wrong_frozen_model_is_rejected() -> None:
    """A control mismatch fails before provider construction."""
    with pytest.raises(ValueError, match="frozen controls rejected"):
        validate_frozen_execution_controls(Namespace(model="wrong-model"))


@pytest.mark.parametrize(
    ("field", "value"),
    [("attempts", 4), ("timeout", 60.0), ("max_output_tokens", 1024)],
)
def test_mutable_control_overrides_are_rejected(field: str, value: object) -> None:
    """Injected control overrides cannot change the future live matrix."""
    with pytest.raises(ValueError, match="frozen controls rejected"):
        validate_frozen_execution_controls(Namespace(model=FROZEN_MODEL, **{field: value}))


def test_non_empty_evidence_file_is_rejected(tmp_path: Path) -> None:
    """A future run cannot append to an existing S1 population."""
    output = tmp_path / "evidence.jsonl"
    output.write_text("existing\n")
    with pytest.raises(FileExistsError):
        ensure_empty_evidence_path(output)


def _variant(statuses: dict[str, str], *, accepted: bool) -> dict[str, object]:
    """Build one bounded synthetic eligible arm for decision tests."""
    return {
        "structured_valid": True,
        "context_valid": True,
        "compiler_valid": True,
        "semantic_accepted": accepted,
        "leaf_statuses": statuses,
    }


def _population(
    *,
    a_statuses: dict[str, str],
    s_statuses: dict[str, str],
    s_extras: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    """Build the complete five-case x three-attempt synthetic population."""
    rows: list[dict[str, object]] = []
    for case_id in REPRESENTATION_CASES:
        for attempt_index in range(ATTEMPTS):
            current_s = {**s_statuses, **(s_extras or {})}
            rows.append(
                {
                    "case_id": case_id,
                    "attempt_index": attempt_index,
                    "input_sufficiency": {"sufficient": True},
                    "selective_contract_only_diff": True,
                    "a": _variant(
                        a_statuses,
                        accepted=all(v == "PASS" for v in a_statuses.values()),
                    ),
                    "s": _variant(
                        current_s,
                        accepted=all(v == "PASS" for v in current_s.values()),
                    ),
                }
            )
    return rows


_SCALE_PASS = {
    "tracks[0].x_scale.minimum": "PASS",
    "tracks[0].x_scale.maximum": "PASS",
    "tracks[0].bindings[0].scale.minimum": "PASS",
    "tracks[0].bindings[0].scale.maximum": "PASS",
}
_TARGET_FAIL = {
    "tracks[0].bindings[0].profile": "WRONG_VALUE",
    "tracks[0].bindings[0].sample_axis.tick_count": "MISSING",
}


def test_full_recovery_decision() -> None:
    """Exact full-recovery conditions produce the full classification."""
    target_pass = {
        "tracks[0].bindings[0].profile": "PASS",
        "tracks[0].bindings[0].sample_axis.tick_count": "PASS",
    }
    result = aggregate_s1_rows(
        _population(
            a_statuses={**_SCALE_PASS, **_TARGET_FAIL},
            s_statuses={**_SCALE_PASS, **target_pass},
        )
    )
    assert result["decision"] == "SELECTIVE_CONTRACT_FULL_RECOVERY"


def test_scale_regression_dominates_recovery() -> None:
    """Any A-pass/S-fail scale leaf dominates target recoveries."""
    s_statuses = {**_SCALE_PASS, "tracks[0].bindings[0].scale.minimum": "WRONG_VALUE"}
    result = aggregate_s1_rows(
        _population(a_statuses={**_SCALE_PASS, **_TARGET_FAIL}, s_statuses=s_statuses)
    )
    assert result["decision"] == "SELECTIVE_CONTRACT_REGRESSION"


def test_partial_recovery_decision() -> None:
    """Some target recovery with a remaining target failure is partial."""
    s_statuses = {
        **_SCALE_PASS,
        "tracks[0].bindings[0].profile": "PASS",
        "tracks[0].bindings[0].sample_axis.tick_count": "MISSING",
    }
    result = aggregate_s1_rows(
        _population(a_statuses={**_SCALE_PASS, **_TARGET_FAIL}, s_statuses=s_statuses)
    )
    assert result["decision"] == "SELECTIVE_CONTRACT_PARTIAL_RECOVERY"


def test_no_benefit_decision() -> None:
    """No target recovery and no scale regression produces no benefit."""
    result = aggregate_s1_rows(_population(a_statuses=_SCALE_PASS, s_statuses=_SCALE_PASS))
    assert result["decision"] == "SELECTIVE_CONTRACT_NO_BENEFIT"


def test_incomplete_population_is_inconclusive() -> None:
    """Incomplete rows cannot produce a selective-contract decision."""
    result = aggregate_s1_rows([])
    assert result["decision"] == "INCONCLUSIVE_SELECTIVE_CONTRACT"
