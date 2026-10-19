"""Provider-free D5-5 dual-lane qualification tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from scripts import d5_5_comparative_model_qualification as d5_5
from scripts import nlp_d4_live_acceptance as d4
from tests.test_d5_provider_free_parity_acceptance import (
    _assert_frozen_las_contract,
    _assert_reloaded,
    _d4_case,
    _d4_gold,
    _new_direct_harness,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_revision_with_count(
    root: Path,
    source: Path,
    *,
    case_id: str,
    turn_id: str,
) -> tuple[Path, bytes, bytes, dict[str, object], dict[str, object], object, int]:
    """Run one isolated revision while retaining the fixture call count."""
    harness = _new_direct_harness(root, source)
    path = harness.adapter._base_for(case_id)
    before_bytes = path.read_bytes()
    before_document = d4.load_logfile_document(path)
    result = asyncio.run(
        harness.adapter.session.revise(
            feedback=_d4_case(turn_id)["request"],
            logfile_path=path,
        )
    )
    after_bytes = path.read_bytes()
    after_document = d4.load_logfile_document(path)
    return (
        path,
        before_bytes,
        after_bytes,
        before_document,
        after_document,
        result,
        harness.adapter.logical_call_count,
    )


def _run_exact_nine_turn_rehearsal(root: Path) -> dict[str, object]:
    """Run the frozen D4 nine-turn route through the canonical deterministic path."""
    source = REPO_ROOT / d4.SOURCE_RELATIVE
    logical_calls = 0

    cbl_harness = _new_direct_harness(root / "cbl", source)
    cbl_case = _d4_case("D4-C01:C01")
    cbl_gold = _d4_gold("D4-C01:C01")
    cbl_actual = asyncio.run(cbl_harness.adapter.execute_turn(cbl_case, cbl_gold))
    cbl_grade = d4.grade_turn(cbl_actual, cbl_gold)
    assert cbl_grade["status"] == "PASS", cbl_grade
    assert {item["status"] for item in cbl_grade["verifier_requirements"]} == {"PASS"}
    assert d4.sha256_file(cbl_actual["starting_artifact_path"]) != d4.sha256_file(
        cbl_actual["ending_artifact_path"]
    )
    assert Path(cbl_actual["ending_artifact_path"]).is_file()
    assert Path(cbl_actual["render_path"]).stat().st_size > 0
    logical_calls += cbl_harness.adapter.logical_call_count

    cumulative = _new_direct_harness(root / "cumulative", source)
    current = cumulative.adapter._base_for("D4-L01")
    for turn_id in ("D4-L01:T1", "D4-L01:T2", "D4-L01:T3", "D4-L01:T4"):
        before = d4.load_logfile_document(current)
        result = asyncio.run(
            cumulative.adapter.session.revise(
                feedback=_d4_case(turn_id)["request"],
                logfile_path=current,
            )
        )
        assert result.report_facts["success"] is True, result.report_facts
        after = d4.load_logfile_document(current)
        _assert_frozen_las_contract(turn_id, before, after)
        _assert_reloaded(current, after)
    logical_calls += cumulative.adapter.logical_call_count

    for case_id, turn_id in (
        ("D4-L02", "D4-L02:T1"),
        ("D4-L02", "D4-L02:T2"),
        ("D4-L03", "D4-L03:C01"),
        ("D4-L04", "D4-L04:C01"),
    ):
        path, before, after, before_document, after_document, result, calls = (
            _run_revision_with_count(
                root / turn_id.replace(":", "-"),
                source,
                case_id=case_id,
                turn_id=turn_id,
            )
        )
        if turn_id in {"D4-L02:T1", "D4-L03:C01", "D4-L04:C01"}:
            assert before == after
            assert result.report_facts["success"] is False
            diagnostics = result.report_facts["compilation"]["diagnostics"]
            codes = {item["code"] for item in diagnostics}
            expected = {
                "D4-L02:T1": "enrichment.section_hint_ambiguous",
                "D4-L03:C01": "enrichment.source_missing",
                "D4-L04:C01": "channel_missing",
            }[turn_id]
            assert expected in codes or "typed.channel_missing" in codes
        else:
            assert result.report_facts["success"] is True
            _assert_frozen_las_contract(turn_id, before_document, after_document)
            _assert_reloaded(path, after_document)
        logical_calls += calls

    assert logical_calls == 18
    return {
        "turns": 9,
        "logical_calls": logical_calls,
        "physical_attempts": logical_calls,
        "provider_calls": 0,
        "endpoint_calls": 0,
        "model_calls": 0,
        "decision": "PASS",
    }


def test_lane_descriptors_share_engine_and_have_independent_custody() -> None:
    """Qwen and Luna vary only at provider configuration and artifact identity."""
    config = d5_5.load_project_config(REPO_ROOT)
    lanes = d5_5.lane_configurations(config)
    facts = d5_5.validate_lane_configurations(lanes)
    assert facts["canonical_engine"] == d5_5.CANONICAL_ENGINE_ENTRYPOINT
    assert [lane.model for lane in lanes] == ["qwen3.6-35b-a3b", "openai/gpt-6-luna"]
    assert lanes[0].base_url == config.openai_compat_base_url
    assert lanes[1].base_url == "https://openrouter.ai/api/v1"
    assert lanes[0].campaign_id != lanes[1].campaign_id
    assert lanes[0].artifact_root != lanes[1].artifact_root
    assert d5_5.HISTORICAL_CAMPAIGN not in facts["campaign_ids"]


def test_provider_factory_arguments_are_lane_local_and_share_boundary() -> None:
    """Both future live lanes delegate to the same existing provider factory."""
    config = d5_5.load_project_config(REPO_ROOT)
    lanes = d5_5.lane_configurations(config)
    arguments = [lane.provider_arguments(REPO_ROOT, "redacted-token") for lane in lanes]
    assert [item["provider"] for item in arguments] == ["openai_compat", "openai_compat"]
    assert [item["model"] for item in arguments] == [
        "qwen3.6-35b-a3b",
        "openai/gpt-6-luna",
    ]
    assert arguments[0]["base_url"] != arguments[1]["base_url"]
    assert all(item["timeout"] == 900.0 for item in arguments)


def test_provider_free_contract_rebinds_to_current_checkpoint_without_calls() -> None:
    """Static D5-5 custody checks preserve the exact nine-turn identities."""
    result = d5_5.verify_provider_free_contract(
        REPO_ROOT,
        implementation_checkpoint=d5_5._git(REPO_ROOT, "rev-parse", "HEAD"),
        run_attestation=True,
    )
    assert result["accepted_baseline"] == d5_5.D5_5_BASELINE
    assert result["population"]["turns"] == 9
    assert result["single_engine_attestation"] == "PASS"
    assert result["provider_calls"] == result["model_calls"] == 0


@pytest.mark.parametrize("lane_id", ["qwen", "luna"])
def test_each_lane_rehearses_the_exact_nine_turn_population(lane_id: str) -> None:
    """Each lane gets an independent 9/9 provider-free canonical rehearsal."""
    config = d5_5.load_project_config(REPO_ROOT)
    lane = next(item for item in d5_5.lane_configurations(config) if item.lane_id == lane_id)
    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        result = _run_exact_nine_turn_rehearsal(Path(temporary) / lane.lane_id)
    assert result == {
        "turns": 9,
        "logical_calls": 18,
        "physical_attempts": 18,
        "provider_calls": 0,
        "endpoint_calls": 0,
        "model_calls": 0,
        "decision": "PASS",
    }


def test_lane_artifact_roots_cannot_collide(tmp_path: Path) -> None:
    """The comparison namespace is lane-specific and historical evidence is untouched."""
    config = d5_5.load_project_config(REPO_ROOT)
    lanes = d5_5.lane_configurations(config)
    roots = [tmp_path / lane.artifact_root for lane in lanes]
    for root in roots:
        root.mkdir(parents=True)
        (root / f"{d5_5.D5_5_EXPERIMENT}.marker").write_text("fresh", encoding="utf-8")
    assert roots[0] != roots[1]
    assert not (tmp_path / d5_5.HISTORICAL_CAMPAIGN).exists()
