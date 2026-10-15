"""Derive all deterministic facts from NormalizedRequest + ProjectedWorkspace."""

from __future__ import annotations

from nlp_gate_modernbert.mb02.capability import assess_capability
from nlp_gate_modernbert.mb02.contracts import (
    DerivedFacts,
    NormalizedRequest,
    ProjectedWorkspace,
    ReferenceMatch,
)
from nlp_gate_modernbert.mb02.resolve import (
    match_curves,
    match_deictic_curve,
    match_fills,
    match_tracks,
)
from nlp_gate_modernbert.mb02.schema_domain import assess_schema_domain


def _curve_by_id(ws: ProjectedWorkspace, cid: str):
    for c in ws.curves:
        if c.id == cid or c.channel == cid or c.handle == cid:
            return c
    return None


def derive_facts(req: NormalizedRequest, ws: ProjectedWorkspace) -> DerivedFacts:
    facts = DerivedFacts()

    invalid, schema_reason = assess_schema_domain(req)
    facts.schema_invalid = invalid
    facts.schema_reason = schema_reason

    supported, cap_reason, cap_detail = assess_capability(req)
    facts.capability_supported = supported
    facts.capability_reason = cap_reason
    facts.capability_detail = cap_detail

    matches: list[ReferenceMatch] = []

    if req.deictic_reference:
        m = match_deictic_curve(ws)
        matches.append(m)
        if m.candidate_count == 0:
            facts.precondition_failures.append("MISSING_DEICTIC_FOCUS")
            facts.precondition_details["MISSING_DEICTIC_FOCUS"] = "focus_absent"
    else:
        if req.query and req.query.kind == "curve" and req.query.text:
            matches.append(match_curves(ws, req.query.text))
        if req.secondary_query and req.secondary_query.kind == "curve" and req.secondary_query.text:
            matches.append(match_curves(ws, req.secondary_query.text))
        if req.target and req.target.kind == "track" and req.target.text:
            matches.append(match_tracks(ws, req.target.text))
        if req.target and req.target.kind == "curve" and req.target.text:
            # relational "with density" — density is a curve target reference
            matches.append(match_curves(ws, req.target.text))
        if req.query and req.query.kind == "fill" and req.query.text:
            matches.append(match_fills(ws, req.query.text))
        if req.query and req.query.kind == "track" and req.query.text:
            matches.append(match_tracks(ws, req.query.text))

    # Fill between preconditions
    if (
        req.requested_operation == "DEFINE_FILL"
        and req.fill
        and req.fill.mode == "BETWEEN"
        and req.fill.primary_query
        and req.fill.predicate
        and req.fill.predicate.secondary_query
    ):
        a = match_curves(ws, req.fill.primary_query)
        b = match_curves(ws, req.fill.predicate.secondary_query)
        matches.extend([a, b])
        if a.candidate_count == 1 and b.candidate_count == 1:
            ca = _curve_by_id(ws, a.candidate_ids[0])
            cb = _curve_by_id(ws, b.candidate_ids[0])
            if ca and cb:
                cross = (
                    ca.track_ref is not None
                    and cb.track_ref is not None
                    and ca.track_ref != cb.track_ref
                )
                same_scale = (
                    ca.scale_kind == cb.scale_kind
                    and ca.scale_min == cb.scale_min
                    and ca.scale_max == cb.scale_max
                    and ca.scale_reverse == cb.scale_reverse
                )
                # Fail-closed only when request asserts the incompatible setup
                # (silent cross-track may still be gold-ok; explicit phrase → unsupported).
                if req.fill.asserts_cross_track and cross:
                    facts.precondition_failures.append("FILL_CROSS_TRACK")
                    facts.precondition_details["FILL_CROSS_TRACK"] = (
                        "between_fill_requires_same_track"
                    )
                if req.fill.asserts_scale_mismatch and not same_scale:
                    facts.precondition_failures.append("FILL_SCALE_INCOMPATIBLE")
                    facts.precondition_details["FILL_SCALE_INCOMPATIBLE"] = (
                        "between_fill_requires_matching_effective_scales"
                    )

    facts.reference_matches = matches
    place_onto_track = (
        req.requested_operation == "PLACE_CURVE"
        and req.target is not None
        and req.target.kind == "track"
    )
    for m in matches:
        if m.candidate_count == 0:
            if req.deictic_reference and m.query == "that curve":
                continue
            # Place onto a named track: curve may be a new catalog bind; track
            # cardinality/precondition owns the terminal when the track is present.
            if place_onto_track and m.field == "curve":
                continue
            facts.not_found_fields.append(m.field)
        elif m.candidate_count > 1:
            facts.ambiguous_fields.append(m.field)

    return facts
