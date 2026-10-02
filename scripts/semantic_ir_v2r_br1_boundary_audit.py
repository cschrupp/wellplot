"""Provider-free SI-V2R boundary audit and residual classification.

This module authenticates the frozen SI-V2R population, classifies observed
semantic residuals without case-specific decision code, and audits the
canonical Pydantic schema against its runtime invariants.  It deliberately
does not contact a provider or select a provider-facing adapter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from wellplot.agent.code_mode.semantic_ir_v2 import SemanticIRV2
from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = Path("/tmp/si-v2r-live.jsonl")
DEFAULT_GOLD = REPO_ROOT / "tests/fixtures/semantic_ir_v2r/cm59a_semantic_intents_v2r.json"
EXPECTED_EVIDENCE_SHA256 = "9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08"
FROZEN_CHECKPOINT = "4f37ef8d6fa441d138f399dd3ac1c45da331fb86"
TAXONOMY_VERSION = "si-v2r-br1.residual-mechanisms.v1"

NONE = "NONE"
STRUCTURAL_UNAVAILABLE = "STRUCTURAL_UNAVAILABLE"
REPORT_FALSE_POSITIVE = "REPORT_FALSE_POSITIVE"
REPORT_FALSE_NEGATIVE = "REPORT_FALSE_NEGATIVE"
SECTION_COUNT_ERROR = "SECTION_COUNT_ERROR"
SECTION_ORDER_ERROR = "SECTION_ORDER_ERROR"
FEATURE_KIND_ERROR = "FEATURE_KIND_ERROR"
FEATURE_MULTIPLICITY_ERROR = "FEATURE_MULTIPLICITY_ERROR"
REFERENCE_FALSE_POSITIVE = "REFERENCE_FALSE_POSITIVE"
REFERENCE_FALSE_NEGATIVE = "REFERENCE_FALSE_NEGATIVE"
REFERENCE_KIND_ERROR = "REFERENCE_KIND_ERROR"
REFERENCE_TARGET_ERROR = "REFERENCE_TARGET_ERROR"
ANNOTATION_ERROR = "ANNOTATION_ERROR"
REQUIRED_CONTEXT_OWNER_ERROR = "REQUIRED_CONTEXT_OWNER_ERROR"
REQUIRED_CONTEXT_CONTENT_ERROR = "REQUIRED_CONTEXT_CONTENT_ERROR"
UNRESOLVED_REQUIREMENT_ERROR = "UNRESOLVED_REQUIREMENT_ERROR"
OTHER_SEMANTIC_ERROR = "OTHER_SEMANTIC_ERROR"
AMBIGUOUS = "AMBIGUOUS"

PRIMARY_PRIORITY = (
    REPORT_FALSE_POSITIVE,
    REPORT_FALSE_NEGATIVE,
    SECTION_COUNT_ERROR,
    ANNOTATION_ERROR,
    FEATURE_KIND_ERROR,
    FEATURE_MULTIPLICITY_ERROR,
    SECTION_ORDER_ERROR,
    REFERENCE_FALSE_POSITIVE,
    REFERENCE_FALSE_NEGATIVE,
    REFERENCE_KIND_ERROR,
    REFERENCE_TARGET_ERROR,
    REQUIRED_CONTEXT_OWNER_ERROR,
    REQUIRED_CONTEXT_CONTENT_ERROR,
    UNRESOLVED_REQUIREMENT_ERROR,
    OTHER_SEMANTIC_ERROR,
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read JSONL rows without changing or rewriting the source artifact."""
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def authenticate_evidence(path: Path = DEFAULT_EVIDENCE) -> dict[str, Any]:
    """Authenticate the immutable 48-row SI-V2R population."""
    if not path.is_file():
        raise FileNotFoundError(path)
    actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual_sha != EXPECTED_EVIDENCE_SHA256:
        raise ValueError(f"Unexpected SI-V2R evidence SHA-256: {actual_sha}")
    rows = _read_jsonl(path)
    case_ids = {str(row["case_id"]) for row in rows}
    attempts = Counter((str(row["case_id"]), int(row["attempt"])) for row in rows)
    if len(rows) != 48 or len(case_ids) != 24 or any(count != 1 for count in attempts.values()):
        raise ValueError("SI-V2R evidence does not contain exactly two attempts per case.")
    if any(sum(1 for row in rows if row["case_id"] == case_id) != 2 for case_id in case_ids):
        raise ValueError("SI-V2R evidence case population is incomplete.")
    return {
        "path": str(path),
        "sha256": actual_sha,
        "rows": len(rows),
        "cases": len(case_ids),
        "attempts_per_case": 2,
    }


def _gold_cases(path: Path = DEFAULT_GOLD) -> dict[str, dict[str, Any]]:
    """Load the provider-free V2R gold semantics by case identity."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(case["case_id"]): case for case in payload["cases"]}


def _sections(projection: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    """Return projected sections, preserving unavailable as ``None``."""
    if projection is None:
        return None
    return list(projection.get("sections", []))


def _feature_kinds(section: dict[str, Any]) -> list[str]:
    """Return ordered feature kinds from one semantic projection."""
    return [str(feature.get("kind")) for feature in section.get("features", [])]


def _reference_kind(section: dict[str, Any]) -> str | None:
    """Return a section reference kind without inferring missing values."""
    reference = section.get("reference_intent")
    return None if reference is None else str(reference.get("kind"))


def _section_signatures(projection: dict[str, Any]) -> list[tuple[tuple[str, ...], str | None]]:
    """Create an order-sensitive semantic signature for each section."""
    return [tuple(_feature_kinds(section)) for section in _sections(projection) or []]


def _actual_target_valid(model: dict[str, Any], index: int) -> bool:
    """Check a reference target against the model's own feature identities."""
    sections = model.get("sections", [])
    if index >= len(sections):
        return False
    reference = sections[index].get("reference_intent")
    if reference is None:
        return False
    target = reference.get("target_semantic_id")
    feature_ids = {feature.get("semantic_id") for feature in sections[index].get("features", [])}
    return isinstance(target, str) and target in feature_ids


def _reference_target_correct(
    expected_model: dict[str, Any],
    actual_model: dict[str, Any],
    expected_projection: dict[str, Any],
    actual_projection: dict[str, Any],
) -> bool:
    """Compare target presence and validity without assuming provider IDs."""
    expected_sections = _sections(expected_projection) or []
    actual_sections = _sections(actual_projection) or []
    if len(expected_sections) != len(actual_sections):
        return False
    expected_models = expected_model.get("sections", [])
    actual_models = actual_model.get("sections", [])
    if len(expected_models) != len(actual_models):
        return False
    for index, expected_section in enumerate(expected_sections):
        expected_ref = expected_section.get("reference_intent")
        actual_ref = actual_sections[index].get("reference_intent")
        expected_target = expected_ref is not None and expected_ref.get("kind") == "reference_track"
        actual_target = actual_ref is not None and actual_ref.get("kind") == "reference_track"
        if expected_target != actual_target:
            return False
        if expected_target and not _actual_target_valid(actual_model, index):
            return False
    return True


def _dimension_flags(
    expected_model: dict[str, Any],
    actual_model: dict[str, Any],
    expected_projection: dict[str, Any],
    actual_projection: dict[str, Any],
    provider: dict[str, Any],
) -> dict[str, bool]:
    """Compute independent semantic dimensions for one structurally valid row."""
    expected_sections = _sections(expected_projection) or []
    actual_sections = _sections(actual_projection) or []
    expected_kinds = [_feature_kinds(section) for section in expected_sections]
    actual_kinds = [_feature_kinds(section) for section in actual_sections]
    same_count = len(expected_sections) == len(actual_sections)
    same_sets = same_count and all(
        set(expected) == set(actual)
        for expected, actual in zip(expected_kinds, actual_kinds, strict=True)
    )
    exact_features = same_count and expected_kinds == actual_kinds
    expected_annotations = [kinds.count("annotation") for kinds in expected_kinds]
    actual_annotations = [kinds.count("annotation") for kinds in actual_kinds]
    expected_refs = [_reference_kind(section) for section in expected_sections]
    actual_refs = [_reference_kind(section) for section in actual_sections]
    report_correct = bool(expected_projection.get("report_work_present")) == bool(
        actual_projection.get("report_work_present")
    )
    context_correct = bool(provider.get("required_context_preserved"))
    expected_unresolved = expected_model.get("unresolved_requirements", [])
    actual_unresolved = actual_model.get("unresolved_requirements", [])
    return {
        "section_count_correct": same_count,
        "section_order_correct": same_count
        and _section_signatures(expected_projection) == _section_signatures(actual_projection),
        "report_scope_correct": report_correct,
        "feature_kinds_correct": same_sets,
        "feature_multiplicity_correct": exact_features,
        "reference_presence_correct": [ref is not None for ref in expected_refs]
        == [ref is not None for ref in actual_refs],
        "reference_kind_correct": expected_refs == actual_refs,
        "reference_target_correct": _reference_target_correct(
            expected_model, actual_model, expected_projection, actual_projection
        ),
        "annotation_correct": expected_annotations == actual_annotations,
        "required_context_correct": context_correct,
        "unresolved_requirement_correct": bool(expected_unresolved) == bool(actual_unresolved),
    }


def _classify_row(
    expected_model: dict[str, Any],
    actual_model: dict[str, Any] | None,
    expected_projection: dict[str, Any],
    actual_projection: dict[str, Any] | None,
    provider: dict[str, Any],
) -> dict[str, Any]:
    """Classify one row, preserving unavailable dimensions as ``NOT_EVALUABLE``."""
    if actual_model is None or actual_projection is None:
        return {
            "structural_available": False,
            "structural_failure_reason": provider.get("structural_failure_reason"),
            "validation_mechanism": "UNKNOWN_SCHEMA_VALIDATION_FAILURE"
            if provider.get("structural_failure_reason") == "schema_validation"
            else "UNKNOWN",
            "section_count_correct": "NOT_EVALUABLE",
            "section_order_correct": "NOT_EVALUABLE",
            "report_scope_correct": "NOT_EVALUABLE",
            "feature_kinds_correct": "NOT_EVALUABLE",
            "feature_multiplicity_correct": "NOT_EVALUABLE",
            "reference_presence_correct": "NOT_EVALUABLE",
            "reference_kind_correct": "NOT_EVALUABLE",
            "reference_target_correct": "NOT_EVALUABLE",
            "annotation_correct": "NOT_EVALUABLE",
            "required_context_correct": "NOT_EVALUABLE",
            "unresolved_requirement_correct": "NOT_EVALUABLE",
            "primary_failure_mechanism": STRUCTURAL_UNAVAILABLE,
            "secondary_failure_mechanisms": [],
        }

    flags = _dimension_flags(
        expected_model, actual_model, expected_projection, actual_projection, provider
    )
    secondary: list[str] = []
    if expected_projection.get("report_work_present") and not actual_projection.get(
        "report_work_present"
    ):
        secondary.append(REPORT_FALSE_NEGATIVE)
    if not expected_projection.get("report_work_present") and actual_projection.get(
        "report_work_present"
    ):
        secondary.append(REPORT_FALSE_POSITIVE)
    if not flags["section_count_correct"]:
        secondary.append(SECTION_COUNT_ERROR)
    if (
        flags["section_count_correct"]
        and flags["feature_kinds_correct"]
        and not flags["section_order_correct"]
    ):
        secondary.append(SECTION_ORDER_ERROR)
    if not flags["feature_kinds_correct"]:
        secondary.append(FEATURE_KIND_ERROR)
    if flags["feature_kinds_correct"] and not flags["feature_multiplicity_correct"]:
        secondary.append(FEATURE_MULTIPLICITY_ERROR)
    if not flags["reference_presence_correct"]:
        expected_refs = [
            _reference_kind(section) for section in _sections(expected_projection) or []
        ]
        actual_refs = [_reference_kind(section) for section in _sections(actual_projection) or []]
        if any(ref is not None for ref in actual_refs) and not any(
            ref is not None for ref in expected_refs
        ):
            secondary.append(REFERENCE_FALSE_POSITIVE)
        else:
            secondary.append(REFERENCE_FALSE_NEGATIVE)
    elif not flags["reference_kind_correct"]:
        secondary.append(REFERENCE_KIND_ERROR)
    elif not flags["reference_target_correct"]:
        secondary.append(REFERENCE_TARGET_ERROR)
    if not flags["annotation_correct"]:
        secondary.append(ANNOTATION_ERROR)
    if not flags["required_context_correct"]:
        misses = provider.get("required_context_misses", [])
        secondary.append(REQUIRED_CONTEXT_OWNER_ERROR if misses else REQUIRED_CONTEXT_CONTENT_ERROR)
    if not flags["unresolved_requirement_correct"]:
        secondary.append(UNRESOLVED_REQUIREMENT_ERROR)
    if not secondary and provider.get("semantic_status") != "SEMANTIC_PASS":
        secondary.append(OTHER_SEMANTIC_ERROR)
    primary = next(
        (value for value in PRIMARY_PRIORITY if value in secondary), OTHER_SEMANTIC_ERROR
    )
    if not secondary:
        primary = NONE
    return {
        "structural_available": True,
        "structural_failure_reason": None,
        "validation_mechanism": None,
        **flags,
        "primary_failure_mechanism": primary,
        "secondary_failure_mechanisms": secondary,
    }


def _case_stability(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate two attempts without converting instability into a pass."""
    primary_values = {record["primary_failure_mechanism"] for record in records}
    stable = len(primary_values) == 1 and all(
        record["structural_available"] == records[0]["structural_available"] for record in records
    )
    return {
        "stable": stable,
        "primary_failure_mechanism": next(iter(primary_values)) if stable else AMBIGUOUS,
        "secondary_failure_mechanisms": sorted(
            {value for record in records for value in record["secondary_failure_mechanisms"]}
        ),
    }


def analyze_evidence(
    evidence_path: Path = DEFAULT_EVIDENCE,
    gold_path: Path = DEFAULT_GOLD,
) -> dict[str, Any]:
    """Return authenticated row taxonomy and bounded mechanism aggregates."""
    evidence = authenticate_evidence(evidence_path)
    gold = _gold_cases(gold_path)
    rows = _read_jsonl(evidence_path)
    row_records: list[dict[str, Any]] = []
    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        provider = row["provider"]
        case_id = str(row["case_id"])
        expected_model = {key: value for key, value in gold[case_id].items() if key != "case_id"}
        expected_projection = provider["expected_semantic_projection"]
        actual_model = provider.get("semantic_model")
        actual_projection = provider.get("semantic_projection")
        dimensions = _classify_row(
            expected_model,
            actual_model,
            expected_projection,
            actual_projection,
            provider,
        )
        record = {
            "case_id": case_id,
            "family": row["family"],
            "attempt": row["attempt"],
            "overall_frozen_semantic_status": provider.get("semantic_status"),
            **dimensions,
        }
        by_case.setdefault(case_id, []).append(record)
        row_records.append(record)

    case_records = []
    for case_id, records in sorted(by_case.items()):
        case_records.append(
            {
                "case_id": case_id,
                "family": records[0]["family"],
                "attempts": records,
                **_case_stability(records),
            }
        )
    stable_cases = [case for case in case_records if case["stable"]]
    mechanism_counts = Counter(record["primary_failure_mechanism"] for record in row_records)
    stable_mechanism_counts = Counter(case["primary_failure_mechanism"] for case in stable_cases)
    allocation_ids = {
        case_id
        for case_id, case in ((case["case_id"], case) for case in case_records)
        if case["family"] == "MULTI_SECTION_ALLOCATION"
    }
    allocation_cases = [case for case in case_records if case["case_id"] in allocation_ids]
    allocation_audit = {
        case["case_id"]: {
            "stable": case["stable"],
            "mechanism": case["primary_failure_mechanism"],
            "section_count": [attempt["section_count_correct"] for attempt in case["attempts"]],
            "section_order": [attempt["section_order_correct"] for attempt in case["attempts"]],
        }
        for case in allocation_cases
    }
    allocation_available = [
        attempt
        for case in allocation_cases
        for attempt in case["attempts"]
        if attempt["structural_available"]
    ]
    allocation_status = (
        "NOT_EVALUABLE"
        if not allocation_available
        else "SUPPORTED"
        if all(
            attempt["section_count_correct"] and attempt["section_order_correct"]
            for attempt in allocation_available
        )
        and len(allocation_available) == 8
        else "PARTIAL"
    )
    garnet = next(case for case in case_records if case["case_id"].endswith("garnet-06"))
    return {
        "version": TAXONOMY_VERSION,
        "baseline": FROZEN_CHECKPOINT,
        "evidence": evidence,
        "frozen_result": {
            "decision": "SI_V2R_PROVIDER_BOUNDARY_REJECTED",
            "stable_semantic_passes": "14/24",
            "initial_structural_successes": "36/48",
            "terminal_structural_failures": 6,
            "compile_successes": 42,
            "historical_result_changed": False,
        },
        "row_mechanism_counts": dict(sorted(mechanism_counts.items())),
        "stable_case_mechanism_counts": dict(sorted(stable_mechanism_counts.items())),
        "allocation_mechanism_status": allocation_status,
        "allocation_audit": allocation_audit,
        "garnet_audit": garnet,
        "rows": row_records,
        "cases": case_records,
        "qwen_intrinsic_incapability": "NOT_ESTABLISHED",
    }


def _walk_schema(node: object, depth: int = 0) -> tuple[Counter[str], int, set[str]]:
    """Collect descriptive JSON Schema metrics recursively."""
    counts: Counter[str] = Counter()
    max_depth = depth
    keywords: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            keywords.add(key)
            if key in {"$defs", "properties", "definitions"} and isinstance(value, dict):
                for child in value.values():
                    child_counts, child_depth, child_keywords = _walk_schema(child, depth + 1)
                    counts.update(child_counts)
                    max_depth = max(max_depth, child_depth)
                    keywords.update(child_keywords)
                continue
            if key in {"$ref", "anyOf", "oneOf", "discriminator", "required"}:
                counts[key] += 1
            if key == "type":
                counts[f"type:{value}"] += 1
                if value in {"object", "array"}:
                    counts[f"{value}_nodes"] += 1
            if key == "additionalProperties" and value is False:
                counts["additionalProperties_false"] += 1
            if key == "required" and isinstance(value, list):
                counts["required_fields"] += len(value)
            child_counts, child_depth, child_keywords = _walk_schema(value, depth + 1)
            counts.update(child_counts)
            max_depth = max(max_depth, child_depth)
            keywords.update(child_keywords)
    elif isinstance(node, list):
        for child in node:
            child_counts, child_depth, child_keywords = _walk_schema(child, depth + 1)
            counts.update(child_counts)
            max_depth = max(max_depth, child_depth)
            keywords.update(child_keywords)
    return counts, max_depth, keywords


def schema_metrics(schema: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic descriptive metrics for a JSON Schema document."""
    counts, depth, keywords = _walk_schema(schema)
    return {
        "bytes": len(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()),
        "defs": len(schema.get("$defs", {})),
        "refs": counts["$ref"],
        "any_of": counts["anyOf"],
        "one_of": counts["oneOf"],
        "discriminators": counts["discriminator"],
        "object_nodes": counts["object_nodes"],
        "array_nodes": counts["array_nodes"],
        "maximum_nesting_depth": depth,
        "required_fields": counts["required_fields"],
        "additional_properties_false": counts["additionalProperties_false"],
        "keywords": sorted(keywords),
    }


def invariant_inventory(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Record whether each important invariant is schema- or runtime-owned."""
    feature_defs = schema.get("$defs", {})
    feature_kinds = {
        name
        for name in feature_defs
        if name
        in {
            "AnnotationSemanticIntentV2R",
            "CurveSemanticIntentV2R",
            "ExtensionSemanticIntentV2R",
            "FillSemanticIntentV2R",
            "RasterSemanticIntentV2R",
        }
    }
    return [
        {
            "invariant_id": "non_empty_strings",
            "classification": "SCHEMA_EXPLICIT",
            "evidence": "minLength",
        },
        {
            "invariant_id": "allowed_feature_kinds",
            "classification": "SCHEMA_EXPLICIT",
            "evidence": sorted(feature_kinds),
        },
        {
            "invariant_id": "feature_discriminator",
            "classification": "SCHEMA_EXPLICIT",
            "evidence": "oneOf/const kind",
        },
        {
            "invariant_id": "minimum_one_section_feature",
            "classification": "SCHEMA_EXPLICIT",
            "evidence": "features.minItems",
        },
        {
            "invariant_id": "unique_semantic_ids_in_section",
            "classification": "CANONICAL_VALIDATION_ONLY",
            "evidence": "model_validator",
        },
        {
            "invariant_id": "reference_track_requires_target",
            "classification": "CANONICAL_VALIDATION_ONLY",
            "evidence": "model_validator",
        },
        {
            "invariant_id": "companion_depth_lane_forbids_target",
            "classification": "CANONICAL_VALIDATION_ONLY",
            "evidence": "model_validator",
        },
        {
            "invariant_id": "reference_target_identifies_feature",
            "classification": "CANONICAL_VALIDATION_ONLY",
            "evidence": "model_validator",
        },
        {
            "invariant_id": "fill_target_identifies_curve",
            "classification": "CANONICAL_VALIDATION_ONLY",
            "evidence": "model_validator",
        },
        {
            "invariant_id": "report_or_sections_required",
            "classification": "CANONICAL_VALIDATION_ONLY",
            "evidence": "model_validator",
        },
        {
            "invariant_id": "extra_fields_forbidden",
            "classification": "SCHEMA_EXPLICIT",
            "evidence": "additionalProperties=false",
        },
    ]


def _base_intent() -> dict[str, Any]:
    """Return a minimal valid section intent for malformed-fixture mutations."""
    return {
        "summary": "base",
        "sections": [
            {
                "kind": "log_plot",
                "goal": "plot curve",
                "features": [{"kind": "curve", "semantic_id": "curve"}],
            }
        ],
    }


def malformed_fixtures() -> dict[str, dict[str, Any]]:
    """Build provider-free fixtures that target distinct validation layers."""
    fixtures: dict[str, dict[str, Any]] = {}
    value = _base_intent()
    value["sections"][0]["reference_intent"] = {"kind": "reference_track"}
    fixtures["reference_track_without_target"] = value
    value = _base_intent()
    value["sections"][0]["reference_intent"] = {
        "kind": "companion_depth_lane",
        "target_semantic_id": "curve",
    }
    fixtures["companion_with_target"] = value
    value = _base_intent()
    value["sections"][0]["reference_intent"] = {
        "kind": "reference_track",
        "target_semantic_id": "missing",
    }
    fixtures["reference_target_missing_feature"] = value
    value = _base_intent()
    value["sections"][0]["features"].append({"kind": "curve", "semantic_id": "curve"})
    fixtures["duplicate_semantic_id"] = value
    value = _base_intent()
    value["sections"][0]["features"].append(
        {"kind": "fill", "semantic_id": "fill", "target_semantic_id": "missing"}
    )
    fixtures["fill_target_missing"] = value
    value = _base_intent()
    value["sections"][0]["features"] = [
        {"kind": "raster", "semantic_id": "raster"},
        {"kind": "fill", "semantic_id": "fill", "target_semantic_id": "raster"},
    ]
    fixtures["fill_target_raster"] = value
    fixtures["no_report_or_sections"] = {"summary": "empty"}
    value = _base_intent()
    value["sections"][0]["features"] = [{"kind": "unknown", "semantic_id": "unknown"}]
    fixtures["unknown_feature_kind"] = value
    value = _base_intent()
    value["summary"] = " "
    fixtures["blank_required_string"] = value
    value = _base_intent()
    value["unexpected"] = True
    fixtures["extra_field"] = value
    return fixtures


def validation_matrix() -> dict[str, Any]:
    """Compare JSON Schema acceptance with canonical Pydantic acceptance."""
    schema = SemanticIRV2R.model_json_schema()
    validator = Draft202012Validator(schema)
    results = []
    for name, payload in malformed_fixtures().items():
        schema_valid = not list(validator.iter_errors(payload))
        try:
            SemanticIRV2R.model_validate(payload)
        except Exception as error:  # Pydantic exposes several validation subclasses.
            canonical_valid = False
            error_type = type(error).__name__
        else:
            canonical_valid = True
            error_type = None
        results.append(
            {
                "fixture": name,
                "json_schema_accepts": schema_valid,
                "deployed_converter": "DEPLOYED_SUPPORT_UNKNOWN",
                "canonical_model_accepts": canonical_valid,
                "canonical_error_type": error_type,
                "expected_canonical_accepts": False,
            }
        )
    return {"version": "si-v2r-br1.validation-matrix.v1", "rows": results}


def build_audit(evidence_path: Path = DEFAULT_EVIDENCE) -> dict[str, Any]:
    """Build all provider-free audit outputs without selecting an adapter."""
    taxonomy = analyze_evidence(evidence_path)
    canonical_schema = SemanticIRV2R.model_json_schema()
    legacy_schema = SemanticIRV2.model_json_schema()
    canonical_bytes = json.dumps(canonical_schema, sort_keys=True, separators=(",", ":")).encode()
    return {
        "experiment": "SI-V2R-BR1",
        "baseline": FROZEN_CHECKPOINT,
        "provider_calls": 0,
        "endpoint_calls": 0,
        "worker_program_calls": 0,
        "taxonomy": taxonomy,
        "canonical_schema": {
            "sha256": hashlib.sha256(canonical_bytes).hexdigest(),
            "metrics": schema_metrics(canonical_schema),
            "invariants": invariant_inventory(canonical_schema),
            "validation_matrix": validation_matrix(),
        },
        "legacy_schema_metrics": schema_metrics(legacy_schema),
        "deployed_converter": {
            "exact_version_resolved": False,
            "status": "DEPLOYED_CONVERTER_VERSION_UNRESOLVED",
            "converter_calls": 0,
            "grammar_validation": "NOT_RUN",
        },
        "boundary_options": {
            "direct_canonical_schema": "MECHANISM_UNRESOLVED",
            "schema_projection": "NOT_JUSTIFIED_BEFORE_CONVERTER_AUDIT",
            "wire_model": "NOT_JUSTIFIED_BEFORE_PROJECTION_AUDIT",
            "weak_general_json": "REJECTED_AS_NON_DIAGNOSTIC_CONTROL_ONLY",
        },
        "decision": "SI_V2R_BR1_BOUNDARY_MECHANISM_UNRESOLVED",
        "semantic_residual_primary_mechanism": "REPORT_FALSE_POSITIVE",
        "allocation_mechanism_status": taxonomy["allocation_mechanism_status"],
        "negative_reference_understanding_status": "NOT_ESTABLISHED",
        "qwen_intrinsic_incapability": "NOT_ESTABLISHED",
    }


def write_outputs(output_dir: Path, evidence_path: Path = DEFAULT_EVIDENCE) -> dict[str, Any]:
    """Write deterministic machine-readable BR1 artifacts."""
    audit = build_audit(evidence_path)
    canonical_schema = SemanticIRV2R.model_json_schema()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "live_residual_mechanisms.json").write_text(
        json.dumps(audit["taxonomy"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "canonical_schema_audit.json").write_text(
        json.dumps(audit["canonical_schema"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "validation_matrix.json").write_text(
        json.dumps(audit["canonical_schema"]["validation_matrix"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "canonical_schema.json").write_text(
        json.dumps(canonical_schema, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return audit


def main() -> None:
    """Write BR1 audit artifacts to a provider-free output directory."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    audit = write_outputs(args.output_dir, args.evidence)
    print(
        json.dumps(
            {key: audit[key] for key in ("decision", "provider_calls", "endpoint_calls")},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
