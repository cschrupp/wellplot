"""Provider-free SI-V2R taxonomy and counterfactual analysis.

The script reads the authenticated SI-V2.2 JSONL as immutable evidence.  It
does not reinterpret the old model output as V2R output; it reports a bounded
offline adjudication alongside the frozen SI-V2.2 metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.cm59a_system_reevaluation import load_case_definitions

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = Path("/tmp/si-v2-2-live.jsonl")
EXPECTED_EVIDENCE_SHA256 = "1b95ebe42ed5227dd134e122c739ca6c6ec90aa72520fc745ffbb622c5527fd7"
TAXONOMY_VERSION = "si-v2r.failure-taxonomy.v1"

EXACT_V2_PASS = "EXACT_V2_PASS"
REFERENCE_REPRESENTATION_MISMATCH = "REFERENCE_REPRESENTATION_MISMATCH"
REFERENCE_OVERREACH = "REFERENCE_OVERREACH"
REPORT_SCOPE_FALSE_POSITIVE = "REPORT_SCOPE_FALSE_POSITIVE"
REPORT_SCOPE_FALSE_NEGATIVE = "REPORT_SCOPE_FALSE_NEGATIVE"
REPORT_NOTE_SECTION_DUPLICATION = "REPORT_NOTE_SECTION_DUPLICATION"
SECTION_ALLOCATION_ERROR = "SECTION_ALLOCATION_ERROR"
FEATURE_KIND_ERROR = "FEATURE_KIND_ERROR"
FEATURE_MULTIPLICITY_ERROR = "FEATURE_MULTIPLICITY_ERROR"
ANNOTATION_SCOPE_ERROR = "ANNOTATION_SCOPE_ERROR"
UNRESOLVED_REQUIREMENT_ERROR = "UNRESOLVED_REQUIREMENT_ERROR"
CAPABILITY_ORDER_ONLY_MISMATCH = "CAPABILITY_ORDER_ONLY_MISMATCH"
TRUE_OTHER_SEMANTIC_ERROR = "TRUE_OTHER_SEMANTIC_ERROR"
AMBIGUOUS = "AMBIGUOUS"


def _load_rows(path: Path) -> list[dict[str, Any]]:
    """Load and authenticate the frozen evidence without modifying it."""
    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_hash != EXPECTED_EVIDENCE_SHA256:
        raise ValueError(f"Unexpected SI-V2.2 evidence hash: {actual_hash}")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) != 48:
        raise ValueError(f"Expected 48 SI-V2.2 rows, found {len(rows)}")
    return rows


def _feature_list(projection: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten features from the one-section semantic projection."""
    return [
        feature
        for section in projection.get("sections", [])
        for feature in section.get("features", [])
    ]


def _feature_kinds(projection: dict[str, Any]) -> Counter[str]:
    """Count semantic feature kinds without using case-specific knowledge."""
    return Counter(str(feature.get("kind")) for feature in _feature_list(projection))


def _has_reference(projection: dict[str, Any]) -> bool:
    """Return whether a generated feature carries the historical reference flag."""
    return any(bool(feature.get("reference")) for feature in _feature_list(projection))


def _expected_reference(projection: dict[str, Any]) -> bool:
    """Return whether the gold projection requests reference semantics."""
    return _has_reference(projection)


def _classify_row(expected: dict[str, Any], actual: dict[str, Any]) -> tuple[str, list[str]]:
    """Classify one old V2 output using generic semantic differences."""
    if actual == expected:
        return EXACT_V2_PASS, []

    secondary: list[str] = []
    expected_sections = expected.get("sections", [])
    actual_sections = actual.get("sections", [])
    expected_report = bool(expected.get("report_present"))
    actual_report = bool(actual.get("report_present"))

    if expected_report and not actual_report:
        secondary.append(REPORT_SCOPE_FALSE_NEGATIVE)
    if not expected_report and actual_report:
        secondary.append(REPORT_SCOPE_FALSE_POSITIVE)

    if expected_report and any(
        feature.get("kind") == "annotation" for feature in _feature_list(actual)
    ):
        secondary.append(REPORT_NOTE_SECTION_DUPLICATION)

    if len(expected_sections) != len(actual_sections):
        secondary.append(SECTION_ALLOCATION_ERROR)

    expected_features = _feature_kinds(expected)
    actual_features = _feature_kinds(actual)
    if expected_features != actual_features:
        if set(expected_features) != set(actual_features):
            secondary.append(FEATURE_KIND_ERROR)
        else:
            secondary.append(FEATURE_MULTIPLICITY_ERROR)

    if _expected_reference(expected):
        if _has_reference(actual) and set(expected_features).issubset(actual_features):
            if len(_feature_list(actual)) >= len(_feature_list(expected)):
                secondary.append(REFERENCE_REPRESENTATION_MISMATCH)
        elif not _has_reference(actual):
            secondary.append(TRUE_OTHER_SEMANTIC_ERROR)
    elif _has_reference(actual):
        secondary.append(REFERENCE_OVERREACH)

    if "annotation" in expected_features and "annotation" not in actual_features:
        secondary.append(ANNOTATION_SCOPE_ERROR)

    if not secondary:
        secondary.append(TRUE_OTHER_SEMANTIC_ERROR)

    priority = (
        REPORT_NOTE_SECTION_DUPLICATION,
        REPORT_SCOPE_FALSE_NEGATIVE,
        REPORT_SCOPE_FALSE_POSITIVE,
        REFERENCE_REPRESENTATION_MISMATCH,
        REFERENCE_OVERREACH,
        SECTION_ALLOCATION_ERROR,
        FEATURE_KIND_ERROR,
        FEATURE_MULTIPLICITY_ERROR,
        ANNOTATION_SCOPE_ERROR,
        TRUE_OTHER_SEMANTIC_ERROR,
    )
    return next(category for category in priority if category in secondary), secondary


def capability_type_equivalent(
    actual: dict[str, Any] | None,
    expected: dict[str, Any],
) -> bool:
    """Compare capability type sets while preserving section order and multiplicity."""
    if actual is None:
        return False
    actual_report = list(actual.get("report", []))
    expected_report = list(expected.get("report", []))
    if len(actual_report) != len(set(actual_report)) or len(expected_report) != len(
        set(expected_report)
    ):
        return False
    if set(actual_report) != set(expected_report):
        return False
    actual_sections = [list(section) for section in actual.get("sections", [])]
    expected_sections = [list(section) for section in expected.get("sections", [])]
    if len(actual_sections) != len(expected_sections):
        return False
    for actual_section, expected_section in zip(actual_sections, expected_sections, strict=True):
        if len(actual_section) != len(set(actual_section)):
            return False
        if len(expected_section) != len(set(expected_section)):
            return False
        if set(actual_section) != set(expected_section):
            return False
    return True


def _expected_signature(case: dict[str, Any]) -> dict[str, Any]:
    """Project the existing CM-59A gold into the comparator shape."""
    return {
        "report": list(case["expected_report_capabilities"]),
        "sections": [list(section) for section in case["expected_sections"]],
    }


def _adjudication(category: str) -> str:
    """Classify old output without claiming it was generated under V2R."""
    if category == EXACT_V2_PASS:
        return "V2_EXACT_PASS"
    if category == REFERENCE_REPRESENTATION_MISMATCH:
        return "V2R_CONTRACT_EQUIVALENT"
    if category == AMBIGUOUS:
        return "AMBIGUOUS_UNDER_V2R"
    return "TRUE_MODEL_SEMANTIC_ERROR"


def analyze_evidence(evidence_path: Path = DEFAULT_EVIDENCE) -> dict[str, Any]:
    """Build taxonomy, corrected equivalence metrics, and offline adjudication."""
    rows = _load_rows(evidence_path)
    cases = {str(case["case_id"]): case for case in load_case_definitions()}
    by_case: dict[str, list[dict[str, Any]]] = {}
    row_records: list[dict[str, Any]] = []
    equivalence_counts = Counter()
    for row in rows:
        provider = row["provider"]
        case_id = str(row["case_id"])
        expected = provider["expected_semantic_projection"]
        actual = provider["semantic_projection"]
        category, secondary = _classify_row(expected, actual)
        gold_signature = _expected_signature(cases[case_id])
        final_signature = provider.get("final_signature")
        exact_final = final_signature == gold_signature
        type_final = capability_type_equivalent(final_signature, gold_signature)
        if exact_final:
            equivalence_counts["exact_order_final_matches"] += 1
        elif type_final:
            equivalence_counts["capability_type_equivalent_final_outcomes"] += 1
            equivalence_counts["order_only_final_mismatches"] += 1
        elif final_signature is not None:
            equivalence_counts["true_final_capability_mismatches"] += 1
        record = {
            "case_id": case_id,
            "family": row["family"],
            "attempt": row["attempt"],
            "semantic_status": provider["semantic_status"],
            "primary_failure_class": category,
            "secondary_failure_classes": secondary,
            "final_exact_order_match": exact_final,
            "final_capability_type_equivalent": type_final,
            "cm58_status": provider.get("cm58_status"),
            "cm58_effect": provider.get("cm58_actions", []),
            "architecture_implication": _implication(category),
            "offline_v2r_adjudication": _adjudication(category),
        }
        by_case.setdefault(case_id, []).append(record)
        row_records.append(record)

    taxonomy_cases: list[dict[str, Any]] = []
    for case_id, case_rows in by_case.items():
        primary_values = {str(record["primary_failure_class"]) for record in case_rows}
        stable = (
            len(primary_values) == 1
            and len(
                {
                    json.dumps(record["final_exact_order_match"], sort_keys=True)
                    for record in case_rows
                }
            )
            == 1
        )
        primary = next(iter(primary_values)) if stable else AMBIGUOUS
        taxonomy_cases.append(
            {
                "case_id": case_id,
                "family": case_rows[0]["family"],
                "attempts": case_rows,
                "stable": stable,
                "primary_failure_class": primary,
                "secondary_failure_classes": sorted(
                    {value for record in case_rows for value in record["secondary_failure_classes"]}
                ),
            }
        )

    category_counts = Counter(record["primary_failure_class"] for record in row_records)
    stable_counts = Counter(
        case["primary_failure_class"] for case in taxonomy_cases if case["stable"]
    )
    adjudication_counts = Counter(record["offline_v2r_adjudication"] for record in row_records)
    return {
        "version": TAXONOMY_VERSION,
        "evidence": {
            "path": str(evidence_path),
            "sha256": EXPECTED_EVIDENCE_SHA256,
            "rows": len(rows),
            "cases": len(taxonomy_cases),
        },
        "frozen_si_v2_2": {
            "stable_semantic_passes": "8/24",
            "historical_result_changed": False,
        },
        "row_category_counts": dict(sorted(category_counts.items())),
        "stable_case_category_counts": dict(sorted(stable_counts.items())),
        "offline_adjudication_counts": dict(sorted(adjudication_counts.items())),
        "capability_equivalence": dict(sorted(equivalence_counts.items())),
        "rows": row_records,
        "cases": sorted(taxonomy_cases, key=lambda item: str(item["case_id"])),
    }


def _implication(category: str) -> str:
    """Attach a generic architecture implication to a taxonomy class."""
    return {
        REFERENCE_REPRESENTATION_MISMATCH: "Reference meaning needs section-level ownership.",
        REFERENCE_OVERREACH: "Reference intent must remain explicit and fail closed when absent.",
        REPORT_SCOPE_FALSE_POSITIVE: "Report work must not be inferred from section prose.",
        REPORT_SCOPE_FALSE_NEGATIVE: "Mixed requests need an explicit coarse report-work branch.",
        REPORT_NOTE_SECTION_DUPLICATION: (
            "Report note and section annotation require separate ownership."
        ),
        SECTION_ALLOCATION_ERROR: "Section count and order are planner semantics.",
        FEATURE_KIND_ERROR: "Curve/raster meaning remains a first-class planner decision.",
        FEATURE_MULTIPLICITY_ERROR: "Feature multiplicity must survive lowering.",
        ANNOTATION_SCOPE_ERROR: "Section annotations must remain distinct from report remarks.",
        TRUE_OTHER_SEMANTIC_ERROR: "No V2R contract rescue is justified by this evidence.",
        EXACT_V2_PASS: "Current semantic encoding is sufficient for this row.",
    }.get(category, "The evidence is insufficient for a bounded reconciliation.")


def main() -> None:
    """Write a deterministic machine-readable taxonomy artifact."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(analyze_evidence(args.evidence), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
