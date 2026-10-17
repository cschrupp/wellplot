"""Derive-all-facts then select terminal by frozen precedence."""

from __future__ import annotations

from nlp_gate_modernbert.mb02.contracts import (
    Authority,
    DerivedFacts,
    NormalizedRequest,
    ProjectedWorkspace,
    PublicEnvelope,
    ResolverDecision,
)
from nlp_gate_modernbert.mb02.envelope import map_public_envelope
from nlp_gate_modernbert.mb02.facts import derive_facts

# Q5 precedence (first applicable terminal wins after all facts derived)
_PRECEDENCE: list[Authority] = [
    "DETERMINISTIC_SCHEMA_DOMAIN",
    "STATIC_CAPABILITY_BOUNDARY",
    "DETERMINISTIC_NOT_FOUND",
    "DETERMINISTIC_CARDINALITY",
    "DETERMINISTIC_PRECONDITION",
    "OK",
]


def _applicable_terminals(facts: DerivedFacts) -> list[tuple[Authority, str | None]]:
    out: list[tuple[Authority, str | None]] = []
    if facts.schema_invalid:
        out.append(("DETERMINISTIC_SCHEMA_DOMAIN", facts.schema_reason))
    if not facts.capability_supported:
        out.append(("STATIC_CAPABILITY_BOUNDARY", facts.capability_reason))
    if facts.not_found_fields:
        # Deictic missing focus is PRECONDITION, not NOT_FOUND
        if "MISSING_DEICTIC_FOCUS" not in facts.precondition_failures:
            out.append(("DETERMINISTIC_NOT_FOUND", "reference_not_found"))
    if facts.ambiguous_fields:
        out.append(("DETERMINISTIC_CARDINALITY", "multiple_matches"))
    if facts.precondition_failures:
        # pick first subtype for selected subtype label
        out.append(("DETERMINISTIC_PRECONDITION", facts.precondition_failures[0]))
    if not out:
        out.append(("OK", None))
    return out


def adjudicate(req: NormalizedRequest, ws: ProjectedWorkspace) -> ResolverDecision:
    facts = derive_facts(req, ws)
    applicable = _applicable_terminals(facts)
    # Select by precedence among applicable
    selected: Authority = "OK"
    subtype: str | None = None
    for auth in _PRECEDENCE:
        for a, sub in applicable:
            if a == auth:
                selected = a
                subtype = sub
                break
        else:
            continue
        break

    suppressed = [a for a, _ in applicable if a != selected and a != "OK"]
    public = map_public_envelope(selected, subtype, facts, req)

    provenance = [
        "adjudicate:derive_all_then_precedence",
        "schema_domain:reuse_ScaleSpec" if facts.schema_invalid else "schema_domain:pass",
        "capability:static_registry",
        "resolve:experiment_matcher",
    ]
    if any(p.startswith("FILL_") for p in facts.precondition_failures):
        provenance.append("precondition:adapted_renderer_fill_axis_semantics")

    return ResolverDecision(
        authority=selected,
        subtype=subtype,
        outcome=public.status,
        reason=public.reason,
        facts=facts,
        suppressed_terminal_facts=suppressed,
        public_envelope=public,
        rule_provenance=provenance,
    )
