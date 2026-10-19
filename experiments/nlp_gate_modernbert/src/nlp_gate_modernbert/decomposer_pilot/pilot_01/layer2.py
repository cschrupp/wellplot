"""Mechanical Layer-2 critical-mechanism veto (frozen design Q5)."""

from __future__ import annotations

from typing import Any

from nlp_gate_modernbert.decomposer_pilot.pilot_01.constants import (
    MECHANISM_ATTRIBUTION,
    PROBE_CASES,
)

_NEVER_MAPPED = frozenset(
    {
        "RUNTIME_TERMINAL_MISMATCH",
        "DECOMPOSITION_DECODE_FAILURE",
        "DECOMPOSITION_SCHEMA_INVALID",
    }
)


def attribute_mechanisms(case_id: str, failure_labels: list[str]) -> set[str]:
    """Map (case_id, labels) → mechanism classes; never-mapped labels excluded."""
    labs = {l for l in failure_labels if l not in _NEVER_MAPPED}
    hit: set[str] = set()
    for mech, spec in MECHANISM_ATTRIBUTION.items():
        if case_id not in spec["only_on_cases"]:
            continue
        if labs & spec["labels"]:
            hit.add(mech)
    return hit


def compute_layer2(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Veto A/B over frozen probe map. One failed probe per (case, mechanism)."""
    # failed_probes[mechanism] = set of case_ids that attributed to it
    failed: dict[str, set[str]] = {m: set() for m in MECHANISM_ATTRIBUTION}
    per_case: dict[str, list[str]] = {}

    for row in case_results:
        cid = row["case_id"]
        labels = list(row.get("failure_labels") or [])
        mechs = sorted(attribute_mechanisms(cid, labels))
        per_case[cid] = mechs
        for m in mechs:
            failed[m].add(cid)

    veto_a: list[str] = []
    for mech, probe_cases in PROBE_CASES.items():
        if probe_cases and probe_cases <= failed[mech]:
            veto_a.append(mech)

    veto_b: list[str] = []
    for mech, cases in failed.items():
        if len(cases) >= 2:
            veto_b.append(mech)

    return {
        "per_case_mechanisms": per_case,
        "failed_probe_cases_by_mechanism": {k: sorted(v) for k, v in failed.items()},
        "veto_a_mechanisms": sorted(veto_a),
        "veto_b_mechanisms": sorted(veto_b),
        "veto_a": bool(veto_a),
        "veto_b": bool(veto_b),
        "critical_mechanism_veto": bool(veto_a) or bool(veto_b),
    }


def mechanical_decision(
    *,
    layer0_reached_freeze: int,
    layer1_equivalent: int,
    layer2: dict[str, Any],
) -> str:
    if layer0_reached_freeze != 6:
        return "INCONCLUSIVE"
    if layer1_equivalent == 6:
        return "STRONG PASS"
    if layer1_equivalent >= 5:
        if layer2.get("critical_mechanism_veto"):
            return "STOP / REDESIGN"
        return "CONTINUE FAMILY"
    # <= 4
    return "STOP / REDESIGN"
