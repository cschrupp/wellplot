"""Forensic analysis of CM-56R8R binding-scale regressions.

This module reads only the frozen R8R evidence and repository artifacts.  It
does not import provider or worker runtime code and never performs inference.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

BASELINE_SHA = "518fc68512c0a405a20761140736f786b906114e"
RAW_EVIDENCE_PATH = Path("/tmp/cm56r8r-live-qwen.jsonl")
RAW_EVIDENCE_SHA256 = "bf1274b987c948e68c36f4f0de6a945860fce6baf97e32f335943bfbb3c16aca"
EVALUATOR_SHA256 = "4bddc22e5a8267cd36e96624884eba8c8578fdd229c7d71c0bd7986bcab12e49"
SEMANTIC_CONTRACT_SHA256 = "1f1ec51c7122b28a87e707051ee7c9203cb13e5b4c0aadf773228fdbfad61eb0"
EVALUATION_CONTRACT_SHA256 = "3e6c3c36d967acb60e6bb7cda13db95d76ed7a754eb92c4bcf5688d76b0da4da"
CORPUS_SHA256 = "4ebae0b37defbdf38bcb743f3332ed930b5d260bffc283473405cafdb4ea327e"
RESPONSE_SCHEMA_SHA256 = "93f1b7d26f1196a1105b733bc13a8de784da19f44eaaa990989d59abaf9fa2d4"
SEMANTIC_CONTRACT_PATH = Path("docs/evaluations/agent-code-mode/CM-56R8R-semantic-contracts.json")
CASE_FIXTURE_PATH = Path("tests/fixtures/typed_worker/cm56_shadow_cases.json")
EXPECTED_CASES = {
    "scalar_linear",
    "reverse_scale",
    "generic_raster",
    "waveform",
    "vdl_sample_axis",
}

MINMAX_NAME_CONFLICT_SIGNATURE = "MINMAX_NAME_CONFLICT_SIGNATURE"
CONTRACT_EXAMPLE_ANCHORING_SIGNATURE = "CONTRACT_EXAMPLE_ANCHORING_SIGNATURE"
TRACK_SCALE_COPY_SIGNATURE = "TRACK_SCALE_COPY_SIGNATURE"
CROSS_CASE_VALUE_SIGNATURE = "CROSS_CASE_VALUE_SIGNATURE"
OTHER_CONTRACT_INDUCED_ENDPOINT_CHANGE = "OTHER_CONTRACT_INDUCED_ENDPOINT_CHANGE"
MIXED_ENDPOINT_REGRESSION = "MIXED_ENDPOINT_REGRESSION"
NO_ENDPOINT_REGRESSION_REPRODUCED = "NO_ENDPOINT_REGRESSION_REPRODUCED"
INCONCLUSIVE_FORENSIC_EVIDENCE = "INCONCLUSIVE_FORENSIC_EVIDENCE"

_NUMBER_TOKEN = r"[-+]?(?:\d+\.\d+|\d+|\.\d+)"
_NUMBER_RE = re.compile(rf"(?<![A-Za-z0-9_]){_NUMBER_TOKEN}(?![A-Za-z0-9_])")
_RANGE_RE = re.compile(
    rf"(?:from|x scale)\s+({_NUMBER_TOKEN})\s+to\s+({_NUMBER_TOKEN})",
    re.IGNORECASE,
)


class EvidenceIntegrityError(ValueError):
    """Raised when frozen forensic evidence does not match its contract."""


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest of one artifact."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _number(value: object) -> float | int:
    """Normalize JSON numeric values for stable comparisons and output."""
    number = float(value)
    return int(number) if number.is_integer() else number


def _pair(scale: dict[str, Any] | None) -> tuple[float | int, float | int] | None:
    """Return ordered scale endpoints from a projection scale."""
    if not scale or "minimum" not in scale or "maximum" not in scale:
        return None
    return (_number(scale["minimum"]), _number(scale["maximum"]))


def _first_binding(projection: dict[str, Any]) -> dict[str, Any]:
    """Return the first binding in a one-track scalar projection."""
    return projection["tracks"][0]["bindings"][0]


def _scale_fields(projection: dict[str, Any]) -> dict[str, Any]:
    """Return bounded scalar-scale fields from one generated projection."""
    scale = _first_binding(projection).get("scale") or {}
    return {
        "kind": scale.get("kind"),
        "minimum": scale.get("minimum"),
        "maximum": scale.get("maximum"),
        "reverse": scale.get("reverse"),
    }


def _expected_scale_fields(projection: dict[str, Any]) -> dict[str, Any]:
    """Return the corresponding fields from an expected projection."""
    scale = _first_binding(projection).get("scale") or {}
    return {
        "kind": scale.get("kind", "linear"),
        "minimum": scale.get("minimum"),
        "maximum": scale.get("maximum"),
        "reverse": scale.get("reverse", False),
    }


def _read_rows(path: Path = RAW_EVIDENCE_PATH) -> list[dict[str, Any]]:
    """Read and integrity-check the frozen R8R JSONL evidence."""
    if not path.exists():
        raise EvidenceIntegrityError(f"Evidence file does not exist: {path}")
    digest = _sha256(path)
    if digest != RAW_EVIDENCE_SHA256:
        raise EvidenceIntegrityError(f"Unexpected evidence SHA-256: {digest}")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if len(rows) != 15:
        raise EvidenceIntegrityError(f"Expected 15 rows, found {len(rows)}")
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["case_id"]] += 1
        if row.get("evaluator_source_sha256") not in (None, EVALUATOR_SHA256):
            raise EvidenceIntegrityError("Unexpected evaluator digest in row")
        for key, expected in (
            ("case_corpus_sha256", CORPUS_SHA256),
            ("response_schema_sha256", RESPONSE_SCHEMA_SHA256),
            ("semantic_contract_sha256", SEMANTIC_CONTRACT_SHA256),
            ("evaluation_contract_sha256", EVALUATION_CONTRACT_SHA256),
        ):
            if row.get(key) != expected:
                raise EvidenceIntegrityError(f"Unexpected {key} in row")
    if set(counts) != EXPECTED_CASES or set(counts.values()) != {3}:
        raise EvidenceIntegrityError(f"Unexpected case population: {dict(counts)}")
    return rows


def _load_cases(path: Path = CASE_FIXTURE_PATH) -> dict[str, dict[str, Any]]:
    """Load frozen request and expected-section metadata by case ID."""
    payload = json.loads(path.read_text())
    return {case["case_id"]: case for case in payload["cases"]}


def extract_contract_numeric_literals(
    artifact: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Extract numeric literals and explicit range pairs from contract examples."""
    literals: list[str] = []
    ranges: list[dict[str, Any]] = []
    for contract in artifact["contracts"]:
        for example in contract.get("examples", []):
            for match in _NUMBER_RE.findall(example):
                if match not in literals:
                    literals.append(match)
            for match in _RANGE_RE.finditer(example):
                pair = [_number(match.group(1)), _number(match.group(2))]
                ranges.append({"example": example, "pair": pair})
    return literals, ranges


def _expected_pairs_by_case(cases: dict[str, dict[str, Any]]) -> dict[str, list[list[Any]]]:
    """Collect expected binding-scale pairs from all frozen cases."""
    pairs: dict[str, list[list[Any]]] = {}
    for case_id, case in cases.items():
        case_pairs: list[list[Any]] = []
        for section in case["expected_sections"]:
            for track in section["tracks"]:
                for binding in track["bindings"]:
                    pair = _pair(binding.get("scale"))
                    if pair is not None:
                        case_pairs.append(list(pair))
        pairs[case_id] = case_pairs
    return pairs


def classify_endpoint_regression(
    *,
    expected: dict[str, Any],
    generated_a: dict[str, Any],
    generated_b: dict[str, Any],
    contract_pairs: list[tuple[float | int, float | int]] = (),
    contract_literals: list[float | int] = (),
    other_case_pairs: dict[str, list[tuple[float | int, float | int]]] | None = None,
) -> dict[str, Any]:
    """Classify one endpoint regression using only semantic relationships."""
    expected_pair = _pair(expected)
    a_pair = _pair(generated_a)
    b_pair = _pair(generated_b)
    if expected_pair is None or a_pair is None or b_pair is None:
        return {
            "signatures": [INCONCLUSIVE_FORENSIC_EVIDENCE],
            "primary_signature": INCONCLUSIVE_FORENSIC_EVIDENCE,
        }

    expected_list = list(expected_pair)
    b_list = list(b_pair)
    relationships = {
        "b_matches_expected": b_pair == expected_pair,
        "b_matches_a": b_pair == a_pair,
        "b_is_exact_swap": b_pair == (expected_pair[1], expected_pair[0]),
        "b_has_same_unordered_endpoints": sorted(b_pair) == sorted(expected_pair),
        "b_is_sorted_ascending": b_pair == tuple(sorted(expected_pair)),
        "b_is_sorted_descending": b_pair == tuple(sorted(expected_pair, reverse=True)),
        "a_matches_expected": a_pair == expected_pair,
        "b_kind_matches_expected": generated_b.get("kind") == expected.get("kind", "linear"),
        "b_reverse_matches_expected": generated_b.get("reverse", False)
        == expected.get("reverse", False),
    }
    if relationships["b_matches_expected"]:
        return {
            "signatures": [NO_ENDPOINT_REGRESSION_REPRODUCED],
            "primary_signature": NO_ENDPOINT_REGRESSION_REPRODUCED,
            "relationships": relationships,
            "evidence": {},
        }
    signatures: list[str] = []
    evidence: dict[str, Any] = {}

    if (
        relationships["a_matches_expected"]
        and relationships["b_is_exact_swap"]
        and relationships["b_kind_matches_expected"]
        and relationships["b_reverse_matches_expected"]
    ):
        signatures.append(MINMAX_NAME_CONFLICT_SIGNATURE)
        evidence["minmax_name_conflict"] = {
            "expected_pair": expected_list,
            "b_pair": b_list,
            "expected_descending": expected_pair[0] > expected_pair[1],
            "b_ascending": b_pair[0] < b_pair[1],
        }

    if b_pair in contract_pairs and b_pair != expected_pair:
        signatures.append(CONTRACT_EXAMPLE_ANCHORING_SIGNATURE)
        evidence["contract_example_match"] = list(b_pair)
    contract_value_matches = {
        field: value
        for field, value in (
            ("minimum", b_pair[0]),
            ("maximum", b_pair[1]),
        )
        if value in contract_literals
    }
    if contract_value_matches:
        evidence["contract_individual_value_matches"] = contract_value_matches

    b_track_pair = _pair(generated_b.get("track_x_scale"))
    if b_track_pair is not None and b_track_pair == b_pair and b_pair != expected_pair:
        signatures.append(TRACK_SCALE_COPY_SIGNATURE)
        evidence["track_scale_copy"] = list(b_pair)

    sample_values = generated_b.get("sample_axis_values", [])
    sample_pairs = {
        tuple(values)
        for values in sample_values
        if isinstance(values, (list, tuple)) and len(values) == 2
    }
    if b_pair in sample_pairs and b_pair != expected_pair:
        signatures.append("SAMPLE_AXIS_COPY_SIGNATURE")
        evidence["sample_axis_copy"] = list(b_pair)
    sample_value_matches = {
        field: value
        for field, value in generated_b.get("sample_axis_fields", {}).items()
        if value in b_pair
    }
    if sample_value_matches:
        evidence["sample_axis_individual_value_matches"] = sample_value_matches

    cross_case_matches: dict[str, list[list[Any]]] = {}
    for case_id, pairs in (other_case_pairs or {}).items():
        matches = [list(pair) for pair in pairs if pair == b_pair and pair != expected_pair]
        if matches:
            cross_case_matches[case_id] = matches
    if cross_case_matches:
        signatures.append(CROSS_CASE_VALUE_SIGNATURE)
        evidence["cross_case_matches"] = cross_case_matches

    if not signatures:
        signatures.append(OTHER_CONTRACT_INDUCED_ENDPOINT_CHANGE)

    return {
        "signatures": signatures,
        "primary_signature": signatures[0],
        "relationships": relationships,
        "evidence": evidence,
    }


def _row_forensics(
    row: dict[str, Any],
    *,
    request: str,
    contract_pairs: list[tuple[float | int, float | int]],
    contract_literals: list[float | int],
    other_case_pairs: dict[str, list[tuple[float | int, float | int]]],
) -> dict[str, Any]:
    """Build a bounded scalar row projection and endpoint analysis."""
    expected = _expected_scale_fields(row["a"]["expected_semantic_projection"])
    generated_a = _scale_fields(row["a"]["generated_semantic_projection"])
    generated_b = _scale_fields(row["b"]["generated_semantic_projection"])
    b_projection = row["b"]["generated_semantic_projection"]
    b_track = b_projection["tracks"][0]
    b_binding = b_track["bindings"][0]
    sample_axis = b_binding.get("sample_axis") or {}
    analysis = classify_endpoint_regression(
        expected=expected,
        generated_a=generated_a,
        generated_b={
            **generated_b,
            "track_x_scale": b_track.get("x_scale"),
            "sample_axis_values": [[sample_axis.get("minimum"), sample_axis.get("maximum")]]
            if sample_axis.get("minimum") is not None and sample_axis.get("maximum") is not None
            else [],
            "sample_axis_fields": sample_axis,
        },
        contract_pairs=contract_pairs,
        contract_literals=contract_literals,
        other_case_pairs=other_case_pairs,
    )
    return {
        "case_id": row["case_id"],
        "attempt_index": row["attempt_index"],
        "request_scale_phrase": request,
        "expected": expected,
        "a_generated": generated_a,
        "b_generated": generated_b,
        "a_leaf_statuses": row["a"]["leaf_statuses"],
        "b_leaf_statuses": row["b"]["leaf_statuses"],
        "endpoint_analysis": analysis,
    }


def _scientific_failures(variant: dict[str, Any]) -> list[str]:
    """Return non-title scientific leaves that did not pass."""
    return [
        path
        for path, status in variant["leaf_statuses"].items()
        if path != "title_valid" and status != "PASS"
    ]


def _scientific_extras(variant: dict[str, Any]) -> list[str]:
    """Return non-title scientific leaves marked as unrequested extras."""
    return [
        path
        for path, status in variant["leaf_statuses"].items()
        if path != "title_valid" and status == "UNREQUESTED_EXTRA"
    ]


def _per_case(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize bounded A/B outcomes for every frozen case."""
    output: dict[str, Any] = {}
    for case_id in sorted(EXPECTED_CASES):
        case_rows = [row for row in rows if row["case_id"] == case_id]
        output[case_id] = {}
        for label in ("a", "b"):
            variants = [row[label] for row in case_rows]
            failures = sorted(
                {failure for variant in variants for failure in _scientific_failures(variant)}
            )
            extras = sorted(
                {extra for variant in variants for extra in _scientific_extras(variant)}
            )
            output[case_id][label.upper()] = {
                "full_acceptance": (
                    f"{sum(v['semantic_accepted'] for v in variants)}/{len(variants)}"
                ),
                "scientific_only_pass": (
                    f"{sum(not _scientific_failures(v) for v in variants)}/{len(variants)}"
                ),
                "failed_scientific_leaves": failures,
                "extra_scientific_leaves": extras,
            }
    return output


def _scale_ir_semantics() -> dict[str, Any]:
    """Return the zero-call static audit of scale endpoint semantics."""
    return {
        "minimum_le_maximum_enforced": False,
        "descending_endpoint_pair_allowed": True,
        "compiler_preserves_order": True,
        "reverse_is_separate_field": True,
        "downstream_interpretation": (
            "Linear axis ranges use [minimum, maximum] unless reverse is true, "
            "in which case the renderer reverses the ordered pair. Tangential "
            "normalization also retains the stored endpoint order."
        ),
        "field_naming_assessment": (
            "minimum/maximum are canonical field names, but this path preserves "
            "ordered display endpoints; no rename is recommended in this slice."
        ),
        "reverse_descending_pair_coherent": True,
        "evidence_locations": [
            "src/wellplot/agent/code_mode/section_semantics.py:40-67",
            "src/wellplot/agent/code_mode/semantic_section_compiler.py:206-214",
            "src/wellplot/model/authoring.py:503-519",
            "src/wellplot/model/document.py:549-570",
            "src/wellplot/renderers/plotly.py:202-229",
            "src/wellplot/renderers/plotly.py:303-311",
        ],
        "questions": {
            "q1_minimum_le_maximum_validator": False,
            "q2_descending_pair_legal": True,
            "q3_compiler_order": "preserved exactly",
            "q4_reverse": "separate downstream axis-orientation field",
            "q5_minimum_maximum": "ordered endpoints in this semantic path, despite names",
            "q6_200_0_reverse_true": "internally coherent",
            "q7_from_to_names": "possibly more descriptive; no rename recommendation",
        },
    }


def build_forensic_summary() -> dict[str, Any]:
    """Build the bounded CM-56R8R-F1 forensic summary."""
    rows = _read_rows()
    cases = _load_cases()
    contracts = json.loads(SEMANTIC_CONTRACT_PATH.read_text())
    literals, contract_examples = extract_contract_numeric_literals(contracts)
    contract_pairs = [tuple(example["pair"]) for example in contract_examples]
    expected_pairs = _expected_pairs_by_case(cases)
    all_pairs = {
        case_id: [tuple(pair) for pair in pairs] for case_id, pairs in expected_pairs.items()
    }

    scalar_rows = [row for row in rows if row["case_id"] in {"scalar_linear", "reverse_scale"}]
    row_forensics = [
        _row_forensics(
            row,
            request=cases[row["case_id"]]["request"],
            contract_pairs=contract_pairs,
            contract_literals=[_number(literal) for literal in literals],
            other_case_pairs={
                case_id: pairs for case_id, pairs in all_pairs.items() if case_id != row["case_id"]
            },
        )
        for row in scalar_rows
    ]
    regressed_rows = [
        item
        for item in row_forensics
        if any(
            status != "PASS"
            for path, status in item["b_leaf_statuses"].items()
            if path.endswith("scale.minimum") or path.endswith("scale.maximum")
        )
        and all(
            item["a_leaf_statuses"].get(path) == "PASS"
            for path in (
                "tracks[0].bindings[0].scale.minimum",
                "tracks[0].bindings[0].scale.maximum",
            )
            if item["a_leaf_statuses"].get(path) is not None
        )
    ]
    primary_signatures = {item["endpoint_analysis"]["primary_signature"] for item in regressed_rows}
    if not regressed_rows:
        primary_signature = NO_ENDPOINT_REGRESSION_REPRODUCED
    elif len(primary_signatures) == 1:
        primary_signature = primary_signatures.pop()
    else:
        primary_signature = MIXED_ENDPOINT_REGRESSION

    return {
        "version": "cm56r8r.binding-scale-forensics.v1",
        "baseline": BASELINE_SHA,
        "raw_evidence": {
            "path": str(RAW_EVIDENCE_PATH),
            "sha256": RAW_EVIDENCE_SHA256,
            "rows": len(rows),
        },
        "provider_calls": 0,
        "production_changes": 0,
        "integrity": {
            "population": "15 rows, five cases x three attempts",
            "evaluator_source_sha256": EVALUATOR_SHA256,
            "semantic_contract_sha256": SEMANTIC_CONTRACT_SHA256,
            "evaluation_contract_sha256": EVALUATION_CONTRACT_SHA256,
            "case_corpus_sha256": CORPUS_SHA256,
            "response_schema_sha256": RESPONSE_SCHEMA_SHA256,
        },
        "scalar_rows": row_forensics,
        "regressed_rows": [
            {
                "case_id": item["case_id"],
                "attempt_index": item["attempt_index"],
                "signatures": item["endpoint_analysis"]["signatures"],
                "endpoint_analysis": item["endpoint_analysis"],
            }
            for item in regressed_rows
        ],
        "regressed_leaves": len(regressed_rows) * 2,
        "contract_numeric_literals": literals,
        "contract_example_pairs": contract_examples,
        "per_case": _per_case(rows),
        "scale_ir_semantics": _scale_ir_semantics(),
        "primary_signature": primary_signature,
        "findings": [
            "All three endpoint regressions are in reverse_scale; scalar_linear is "
            "a no-regression control.",
            "The reverse-scale B pair is the exact expected endpoint swap with kind "
            "and reverse preserved.",
            "The endpoint result is consistent with a minimum/maximum naming "
            "conflict, not proof of model reasoning.",
            "The frozen R8R decision remains SEMANTIC_CONTRACT_PARTIAL_RECOVERY.",
        ],
    }


def main() -> None:
    """Write the bounded forensic artifact."""
    output = Path("docs/evaluations/agent-code-mode/CM-56R8R-binding-scale-forensics.json")
    summary = build_forensic_summary()
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output), "primary_signature": summary["primary_signature"]}))


if __name__ == "__main__":
    main()
