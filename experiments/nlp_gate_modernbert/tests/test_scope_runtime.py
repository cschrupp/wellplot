"""SCOPE-RUNTIME-01: six witness replays + mandatory Q3/Q4 negative tests."""

from __future__ import annotations

from nlp_gate_modernbert.mb02.workspace import project_workspace
from nlp_gate_modernbert.scope_runtime.contracts import (
    ScopeNormalizedProgram,
    ScopeNormalizedRequest,
    ScopeNormalizedTask,
    ScopeSemanticQuery,
)
from nlp_gate_modernbert.scope_runtime.execute import execute_program, parse_program_from_witness
from nlp_gate_modernbert.scope_runtime.replay import load_witnesses, replay_one, replay_witnesses

CASE_IDS = [
    "D5GAP-0085",
    "D5GAP-0089",
    "D5GAP-0096",
    "D5GAP-0101",
    "D5GAP-0117",
    "SEED-cm-9643c020e2e02463",
]


def _witness_by_id(case_id: str) -> dict:
    return next(w for w in load_witnesses() if w["case_id"] == case_id)


def test_witness_d5gap_0085_program_ok() -> None:
    r = replay_one(_witness_by_id("D5GAP-0085"))
    assert r["program_terminal"]["authority"] == "OK"
    assert r["frontier_calls"] == 0
    assert r["gold_used_as_runtime_decision_input"] is False
    # Scale update before fill: t2 changes narrow scale; t3 fill OK
    t2 = r["task_trace"][1]
    t3 = r["task_trace"][2]
    assert t2["mb02_authority"] == "OK"
    assert t2["effect_applied"] and "CONFIGURE" in t2["effect_applied"]
    assert t3["mb02_authority"] == "OK"


def test_witness_d5gap_0089_program_ok() -> None:
    r = replay_one(_witness_by_id("D5GAP-0089"))
    assert r["program_terminal"]["authority"] == "OK"
    before_fill = r["task_trace"][1]["workspace_before"]
    narrow = next(c for c in before_fill["curves"] if c["id"] == "curve-2")
    assert narrow["scale_min"] == 0.0 and narrow["scale_max"] == 100.0


def test_witness_d5gap_0096_local_ref_adapter() -> None:
    r = replay_one(_witness_by_id("D5GAP-0096"))
    assert r["program_terminal"]["authority"] == "OK"
    t1 = r["task_trace"][0]
    assert t1["binds_produced"].get("$track1") is not None
    projected = t1["binds_produced"]["$track1"]
    t2 = r["task_trace"][1]
    assert t2["source_local_ref"] == "$track1"
    assert t2["resolved_projected_ref"] == projected
    assert t2["mb02_adjudication_query"] == f"track {projected}"


def test_witness_d5gap_0101_program_ok() -> None:
    r = replay_one(_witness_by_id("D5GAP-0101"))
    assert r["program_terminal"]["authority"] == "OK"
    assert r["task_trace"][0]["binds_produced"].get("$track1") is not None


def test_witness_d5gap_0117_program_ok() -> None:
    r = replay_one(_witness_by_id("D5GAP-0117"))
    assert r["program_terminal"]["authority"] == "OK"
    assert len(r["task_trace"]) == 2


def test_witness_seed_program_ok() -> None:
    r = replay_one(_witness_by_id("SEED-cm-9643c020e2e02463"))
    assert r["program_terminal"]["authority"] == "OK"
    assert len(r["task_trace"]) == 5


def test_aggregate_six_of_six() -> None:
    out = replay_witnesses(write_evidence=False)
    assert out["summary"]["n_witnesses"] == 6
    assert out["summary"]["n_program_ok"] == 6
    assert out["summary"]["n_program_non_ok"] == 0
    assert out["summary"]["frontier_calls"] == 0
    assert out["summary"]["gold_decision_inputs"] == 0
    assert out["summary"]["mb02r_modified"] is False
    assert out["summary"]["historical_gold_modified"] is False


def test_negative_failed_task_no_effect_no_bind() -> None:
    """Failed task → fail-fast, no effect, no bind, later task not adjudicated."""
    # CREATE_TRACK OK, then CONFIGURE with contradictory directions → schema-domain;
    # third task must not run; failed task must not mutate scale.
    from nlp_gate_modernbert.mb02.contracts import ScaleBounds

    program = ScopeNormalizedProgram(
        version="test",
        tasks=[
            ScopeNormalizedTask(
                task_id="t1",
                depends_on=[],
                produces_binds={"$track1": "track"},
                request=ScopeNormalizedRequest(
                    requested_operation="CREATE_TRACK",
                    track_title="Temp",
                ),
            ),
            ScopeNormalizedTask(
                task_id="t2",
                depends_on=["t1"],
                produces_binds={},
                request=ScopeNormalizedRequest(
                    requested_operation="CONFIGURE_CURVE_DISPLAY",
                    query=ScopeSemanticQuery(kind="curve", text="GR"),
                    scale_direction_claims=["increasing", "decreasing"],
                    scale_bounds=ScaleBounds(kind="linear", minimum=0.0, maximum=50.0),
                ),
            ),
            ScopeNormalizedTask(
                task_id="t3",
                depends_on=["t2"],
                produces_binds={},
                request=ScopeNormalizedRequest(
                    requested_operation="PLACE_CURVE",
                    query=ScopeSemanticQuery(kind="curve", text="RT"),
                    target=ScopeSemanticQuery(kind="track", local_ref="$track1"),
                ),
            ),
        ],
    )
    ws = project_workspace("d0_base")
    before_tracks = len(ws.tracks)
    gr_before = next(c for c in ws.curves if c.channel == "GR")
    gr_scale_before = (gr_before.scale_min, gr_before.scale_max, gr_before.scale_reverse)
    result = execute_program(program, ws, case_id="NEG-fail")
    assert result.program_terminal["authority"] == "DETERMINISTIC_SCHEMA_DOMAIN"
    assert result.program_terminal.get("failed_task_id") == "t2"
    assert len(result.task_trace) == 2  # t3 not adjudicated
    t1, t2 = result.task_trace
    assert t1.mb02_authority == "OK"
    assert t1.binds_produced.get("$track1") is not None
    assert t2.mb02_authority == "DETERMINISTIC_SCHEMA_DOMAIN"
    assert t2.effect_applied is None
    assert t2.binds_produced == {}
    assert t2.workspace_after == t2.workspace_before
    # GR scale unchanged despite failed configure payload
    gr_after = next(c for c in t2.workspace_after["curves"] if c["channel"] == "GR")
    assert (gr_after["scale_min"], gr_after["scale_max"], gr_after["scale_reverse"]) == gr_scale_before
    assert len(t1.workspace_after["tracks"]) == before_tracks + 1


def test_negative_illegal_local_ref_schema_domain() -> None:
    """Unresolved local_ref → DETERMINISTIC_SCHEMA_DOMAIN; zero task execution."""
    program = ScopeNormalizedProgram(
        version="test",
        tasks=[
            ScopeNormalizedTask(
                task_id="t1",
                depends_on=[],
                produces_binds={},
                request=ScopeNormalizedRequest(
                    requested_operation="PLACE_CURVE",
                    query=ScopeSemanticQuery(kind="curve", text="GR"),
                    target=ScopeSemanticQuery(kind="track", local_ref="$missing"),
                ),
            ),
        ],
    )
    ws = project_workspace("d0_base")
    result = execute_program(program, ws, case_id="NEG-bind")
    assert result.structural_valid is False
    assert result.program_terminal["authority"] == "DETERMINISTIC_SCHEMA_DOMAIN"
    assert result.task_trace == []


def test_local_ref_plus_text_schema_domain() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ScopeSemanticQuery(kind="track", text="track 1", local_ref="$track1")


def test_adapter_track_n_form() -> None:
    w = _witness_by_id("D5GAP-0101")
    program = parse_program_from_witness(w["normalized_program"])
    ws = project_workspace(w["initial_workspace_facts"]["fixture_id"])
    result = execute_program(program, ws)
    t2 = result.task_trace[1]
    n = t2.resolved_projected_ref
    assert t2.mb02_adjudication_query == f"track {n}"
    assert t2.source_local_ref == "$track1"
