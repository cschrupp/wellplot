"""MB-02 deterministic resolver representative tests."""

from __future__ import annotations

from nlp_gate_modernbert.mb02.adjudicate import adjudicate
from nlp_gate_modernbert.mb02.contracts import (
    FillPredicate,
    FillSpec,
    IntervalBounds,
    NormalizedRequest,
    ScaleBounds,
    SemanticQuery,
)
from nlp_gate_modernbert.mb02.workspace import project_workspace


def test_density_unique_ok() -> None:
    ws = project_workspace("d0_triple_combo")
    req = NormalizedRequest(
        requested_operation="PLACE_CURVE",
        query=SemanticQuery(kind="curve", text="RHOB"),
        target=SemanticQuery(kind="track", text="track 4"),
    )
    d = adjudicate(req, ws)
    assert d.authority == "OK"
    assert d.public_envelope.status == "ok"


def test_density_ambiguous_rhob_rhoz() -> None:
    ws = project_workspace("d0_ambiguous_density")
    req = NormalizedRequest(
        requested_operation="PLACE_CURVE",
        query=SemanticQuery(kind="curve", text="density"),
        target=SemanticQuery(kind="track", text="track 4"),
    )
    d = adjudicate(req, ws)
    assert d.authority == "DETERMINISTIC_CARDINALITY"
    assert d.public_envelope.status == "ambiguous"
    assert any(m.candidate_count >= 2 for m in d.facts.reference_matches)


def test_missing_curve_not_found() -> None:
    ws = project_workspace("d0_missing_CALI_0")
    req = NormalizedRequest(
        requested_operation="PLACE_CURVE",
        query=SemanticQuery(kind="curve", text="CALI"),
    )
    d = adjudicate(req, ws)
    assert d.authority == "DETERMINISTIC_NOT_FOUND"
    assert d.public_envelope.status == "unsupported"
    assert d.public_envelope.reason == "reference_not_found"


def test_deictic_no_focus_ambiguous() -> None:
    ws = project_workspace("d5_no_focus")
    req = NormalizedRequest(
        requested_operation="CONFIGURE_CURVE_DISPLAY",
        deictic_reference=True,
    )
    d = adjudicate(req, ws)
    assert d.authority == "DETERMINISTIC_PRECONDITION"
    assert d.subtype == "MISSING_DEICTIC_FOCUS"
    assert d.public_envelope.status == "ambiguous"


def test_deictic_with_focus_ok() -> None:
    ws = project_workspace("d5_focus_rhob")
    req = NormalizedRequest(
        requested_operation="CONFIGURE_CURVE_DISPLAY",
        deictic_reference=True,
    )
    d = adjudicate(req, ws)
    assert d.authority == "OK"
    assert d.public_envelope.status == "ok"


def test_fill_cross_track_precondition() -> None:
    ws = project_workspace("d5_petrophysics")
    req = NormalizedRequest(
        requested_operation="DEFINE_FILL",
        fill=FillSpec(
            mode="BETWEEN",
            primary_query="GR",
            predicate=FillPredicate(kind="BETWEEN_CURVES", secondary_query="NPHI"),
            asserts_cross_track=True,
        ),
    )
    d = adjudicate(req, ws)
    assert d.authority == "DETERMINISTIC_PRECONDITION"
    assert "FILL_CROSS_TRACK" in d.facts.precondition_failures
    assert d.public_envelope.status == "unsupported"
    assert d.public_envelope.reason == "capability_not_available"


def test_objective_cross_track_fill_precondition_r6() -> None:
    """R6: cross-track between-fill fails from workspace state, not utterance asserts."""
    ws = project_workspace("d0_with_rhob")
    req = NormalizedRequest(
        requested_operation="DEFINE_FILL",
        fill=FillSpec(
            mode="BETWEEN",
            primary_query="RHOB",
            predicate=FillPredicate(kind="BETWEEN_CURVES", secondary_query="neutron"),
            asserts_cross_track=False,
        ),
    )
    d = adjudicate(req, ws)
    assert d.authority == "DETERMINISTIC_PRECONDITION"
    assert "FILL_CROSS_TRACK" in d.facts.precondition_failures
    assert d.public_envelope.status == "unsupported"


def test_invalid_log_bounds_reuses_scalespec() -> None:
    ws = project_workspace("d0_triple_combo")
    req = NormalizedRequest(
        requested_operation="CONFIGURE_CURVE_DISPLAY",
        query=SemanticQuery(kind="curve", text="RT"),
        scale_bounds=ScaleBounds(kind="log", minimum=0.0, maximum=100.0),
    )
    d = adjudicate(req, ws)
    assert d.authority == "DETERMINISTIC_SCHEMA_DOMAIN"
    assert d.public_envelope.status == "invalid"
    assert d.public_envelope.reason == "invalid_log_scale_bounds"


def test_contradictory_directions() -> None:
    ws = project_workspace("d0_triple_combo")
    req = NormalizedRequest(
        requested_operation="CONFIGURE_CURVE_DISPLAY",
        query=SemanticQuery(kind="curve", text="RHOB"),
        scale_direction_claims=["increasing", "decreasing"],
    )
    d = adjudicate(req, ws)
    assert d.authority == "DETERMINISTIC_SCHEMA_DOMAIN"
    assert d.public_envelope.reason == "contradictory_scale_direction"


def test_contradictory_targets() -> None:
    ws = project_workspace("d0_triple_combo")
    req = NormalizedRequest(
        requested_operation="MOVE_CURVE",
        query=SemanticQuery(kind="curve", text="RHOB"),
        target_claims=["track_2", "track_4"],
    )
    d = adjudicate(req, ws)
    assert d.authority == "DETERMINISTIC_SCHEMA_DOMAIN"
    assert d.public_envelope.reason == "contradictory_target"


def test_threshold_fill_capability() -> None:
    ws = project_workspace("d0_triple_combo")
    req = NormalizedRequest(
        requested_operation="DEFINE_FILL",
        query=SemanticQuery(kind="curve", text="GR"),
        fill=FillSpec(
            mode="CONDITIONAL",
            primary_query="GR",
            predicate=FillPredicate(kind="ABOVE_THRESHOLD", value=75),
        ),
    )
    d = adjudicate(req, ws)
    assert d.authority == "STATIC_CAPABILITY_BOUNDARY"
    assert d.public_envelope.status == "unsupported"
    assert d.public_envelope.reason == "operation_not_supported"


def test_capability_before_not_found() -> None:
    """Unsupported request remains capability even if curve absent."""
    ws = project_workspace("d0_missing_CALI_0")
    req = NormalizedRequest(
        requested_operation="DEFINE_FILL",
        query=SemanticQuery(kind="curve", text="CALI"),
        fill=FillSpec(
            mode="CONDITIONAL",
            primary_query="CALI",
            predicate=FillPredicate(kind="ABOVE_THRESHOLD", value=10),
        ),
    )
    d = adjudicate(req, ws)
    assert d.authority == "STATIC_CAPABILITY_BOUNDARY"
    assert "DETERMINISTIC_NOT_FOUND" in d.suppressed_terminal_facts


def test_interval_order_invalid() -> None:
    ws = project_workspace("d0_triple_combo")
    req = NormalizedRequest(
        requested_operation="SET_INTERVAL",
        interval_bounds=IntervalBounds(top=3200.0, base=2500.0, unit="m"),
    )
    d = adjudicate(req, ws)
    assert d.authority == "DETERMINISTIC_SCHEMA_DOMAIN"
    assert d.public_envelope.reason == "invalid_interval_order"
