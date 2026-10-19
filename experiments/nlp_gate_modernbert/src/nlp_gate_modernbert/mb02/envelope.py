"""Authority + subtype → frozen public WELL-IR envelope mapping (Q6)."""

from __future__ import annotations

from nlp_gate_modernbert.mb02.contracts import (
    Authority,
    DerivedFacts,
    NormalizedRequest,
    PublicEnvelope,
)


def map_public_envelope(
    authority: Authority,
    subtype: str | None,
    facts: DerivedFacts,
    req: NormalizedRequest,
) -> PublicEnvelope:
    if authority == "DETERMINISTIC_SCHEMA_DOMAIN":
        return PublicEnvelope(
            status="invalid",
            reason=facts.schema_reason or subtype,
            detail=None,
        )

    if authority == "STATIC_CAPABILITY_BOUNDARY":
        return PublicEnvelope(
            status="unsupported",
            reason=facts.capability_reason or "operation_not_supported",
            detail=facts.capability_detail,
        )

    if authority == "DETERMINISTIC_NOT_FOUND":
        return PublicEnvelope(
            status="unsupported",
            reason="reference_not_found",
            detail=None,
        )

    if authority == "DETERMINISTIC_CARDINALITY":
        ambs = []
        for m in facts.reference_matches:
            if m.candidate_count > 1:
                ambs.append(
                    {
                        "field": m.field,
                        "candidates": m.candidate_ids,
                        "query": m.query,
                    }
                )
        return PublicEnvelope(status="ambiguous", reason=None, ambiguities=ambs)

    if authority == "DETERMINISTIC_PRECONDITION":
        # Typed subtype → existing public mapping
        if subtype == "MISSING_DEICTIC_FOCUS" or "MISSING_DEICTIC_FOCUS" in facts.precondition_failures:
            return PublicEnvelope(status="ambiguous", reason=None, ambiguities=[])
        if "FILL_CROSS_TRACK" in facts.precondition_failures:
            return PublicEnvelope(
                status="unsupported",
                reason="capability_not_available",
                detail=facts.precondition_details.get(
                    "FILL_CROSS_TRACK", "between_fill_requires_same_track"
                ),
            )
        if "FILL_SCALE_INCOMPATIBLE" in facts.precondition_failures:
            return PublicEnvelope(
                status="unsupported",
                reason="capability_not_available",
                detail=facts.precondition_details.get(
                    "FILL_SCALE_INCOMPATIBLE",
                    "between_fill_requires_matching_effective_scales",
                ),
            )
        return PublicEnvelope(
            status="unsupported",
            reason="capability_not_available",
            detail=facts.precondition_details.get(
                subtype or "", "execution_precondition_failed"
            ),
        )

    return PublicEnvelope(status="ok")
