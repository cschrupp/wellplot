"""Freeze the provider-free SI-V2R SR7 paired-comparison contract.

This module intentionally has no provider execution path.  It authenticates the
accepted inputs, generates the future execution/evidence contracts, and grades
only synthetic or caller-supplied semantic objects.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.si_v2r_model_qualification import (
    STRUCTURAL_RETRY_PROMPT,
    V2R_SYSTEM_PROMPT,
    _required_context_preservation,
    context_projection,
    semantic_projection,
)
from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R

BASELINE_SHA = "9c0dfd2fa0a060195199f21655ccdffd2cc68c9c"
DEFAULT_OUTPUT_DIR = Path("tests/fixtures/semantic_ir_v2r_sr7_p0")
CORPUS_PATH = Path("tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json")
GOLD_PATH = Path("tests/fixtures/semantic_ir_v2r/cm59a_semantic_intents_v2r.json")
C0_DIR = Path("tests/fixtures/semantic_ir_v2r_sr7_c0")
C1_RESULT = Path("tests/fixtures/semantic_ir_v2r_sr7_c1/result.json")

CONFIGURATION_A_FINGERPRINT = "154513f15bba419aae7ce87c8a0e26a601f45829281e385c599d597fc810711a"
CONFIGURATION_B_FINGERPRINT = "a473cc25db1415373b81d7775c263170d7c6388fa45caa5572b11308e8b7d980"
SCHEMA_SHA256 = "d84cdef165ba6d060addd3ed73b018a1f10a3e70ef4a674b5d1a06352c0d58d8"
SYSTEM_PROMPT_SHA256 = "5ebdd3da9bc3cdf78442a97ba0a2ef9fc1c0d5e8b1ca641f18a30fe1b0cb50e3"
RETRY_PROMPT_SHA256 = "27c6a43c7f611a79401914b6732dbcec946493bba51058c1eb1d1245f47990f0"
GOLD_SHA256 = "eb4803c1b0265f72e2b7f3f97176afe585698473f108d60768e792e4ecfca0a5"
CORPUS_SHA256 = "b6a605158e667e5250df99a53cb4ba521473f8146fad2022aed2dff77d5f551b"

DIMENSIONS = (
    "REPORT_PRESENCE",
    "REPORT_CONTENT",
    "SECTION_STRUCTURE",
    "SECTION_ALLOCATION",
    "SECTION_ORDER",
    "FEATURE_KIND",
    "FEATURE_MULTIPLICITY",
    "REQUIRED_CONTEXT",
    "REFERENCE_PRESENCE",
    "REFERENCE_KIND",
    "REFERENCE_TARGET",
    "ANNOTATION",
    "CONSTRAINT_SCOPE",
    "UNRESOLVED_REQUIREMENT",
)
MODEL_ROLES = (
    "PRIMARY_MODEL_OBLIGATION",
    "RAW_MODEL_DIAGNOSTIC",
    "MASKED_UNRESOLVED_CONTRACT",
    "NOT_APPLICABLE",
)
SYSTEM_ROLES = (
    "SYSTEM_CREDIT_ELIGIBLE",
    "SYSTEM_OBSERVED_ONLY",
    "SYSTEM_CREDIT_BLOCKED",
    "SYSTEM_NOT_APPLICABLE",
)
SEMANTIC_STATUSES = (
    "CORRECT",
    "INCORRECT",
    "MASKED",
    "NOT_APPLICABLE",
    "NOT_EVALUABLE_STRUCTURAL",
    "NOT_EVALUABLE_INFRA",
)
RELATIONS = ("A_BETTER", "B_BETTER", "UNCHANGED", "NOT_COMPARABLE")


def canonical_json(value: object) -> str:
    """Serialize JSON-shaped values deterministically."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    """Hash UTF-8 text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    """Hash bytes."""
    return hashlib.sha256(value).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True).strip()


def _assert_lineage(repo_root: Path) -> None:
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASELINE_SHA, "HEAD"],
        cwd=repo_root,
        check=False,
    ).returncode:
        raise RuntimeError(f"checkout does not descend from P0 baseline {BASELINE_SHA}")


def _assert_frozen_inputs(repo_root: Path) -> None:
    schema_hash = sha256_text(canonical_json(SemanticIRV2R.model_json_schema()))
    if schema_hash != SCHEMA_SHA256:
        raise RuntimeError(f"V2R schema drift: {schema_hash}")
    if sha256_text(V2R_SYSTEM_PROMPT) != SYSTEM_PROMPT_SHA256:
        raise RuntimeError("V2R system prompt drift")
    if sha256_text(STRUCTURAL_RETRY_PROMPT) != RETRY_PROMPT_SHA256:
        raise RuntimeError("structural retry prompt drift")
    if sha256_bytes((repo_root / CORPUS_PATH).read_bytes()) != CORPUS_SHA256:
        raise RuntimeError("CM59A request corpus drift")
    if sha256_bytes((repo_root / GOLD_PATH).read_bytes()) != GOLD_SHA256:
        raise RuntimeError("V2R gold drift")
    c1 = _load_json(repo_root / C1_RESULT)
    if c1["decision"] != "SI_V2R_SR7_C1_B_FREEZE_ALLOWED":
        raise RuntimeError("C1 did not authorize the B freeze")
    if c1["configuration_b_fingerprint_sha256"] != CONFIGURATION_B_FINGERPRINT:
        raise RuntimeError("C1 B fingerprint drift")
    if c1["cm59a_requests_sent"] != 0 or c1["worker_program_calls"] != 0:
        raise RuntimeError("C1 contains prohibited execution activity")
    for name, expected in (
        ("configuration_a.json", CONFIGURATION_A_FINGERPRINT),
        ("configuration_b.json", CONFIGURATION_B_FINGERPRINT),
    ):
        record = _load_json(repo_root / C0_DIR / name)
        if record["configuration_fingerprint_sha256"] != expected:
            raise RuntimeError(f"C0 fingerprint drift: {name}")
        if record["gold_sha256"] != GOLD_SHA256:
            raise RuntimeError(f"C0 gold binding drift: {name}")


def _case_files(repo_root: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    corpus = _load_json(repo_root / CORPUS_PATH)["cases"]
    gold = _load_json(repo_root / GOLD_PATH)["cases"]
    if not isinstance(corpus, list) or not isinstance(gold, list):
        raise RuntimeError("frozen case artifacts are malformed")
    if len(corpus) != 24 or len(gold) != 24:
        raise RuntimeError("P0 requires exactly 24 frozen cases")
    corpus_ids = [case["case_id"] for case in corpus]
    gold_by_id = {case["case_id"]: case for case in gold}
    if len(set(corpus_ids)) != 24 or set(corpus_ids) != set(gold_by_id):
        raise RuntimeError("corpus/gold case IDs do not match exactly")
    return corpus, gold_by_id


def _has_features(gold: dict[str, Any]) -> bool:
    return any(section.get("features") for section in gold["sections"])


def _has_reference(gold: dict[str, Any]) -> bool:
    return any(section.get("reference_intent") is not None for section in gold["sections"])


def _has_annotation(gold: dict[str, Any]) -> bool:
    return any(
        feature.get("kind") == "annotation"
        for section in gold["sections"]
        for feature in section.get("features", [])
    )


def _has_context(gold: dict[str, Any]) -> bool:
    return any(
        section.get("source_hints")
        or section.get("requirements")
        or any(feature.get("requirements") for feature in section.get("features", []))
        for section in gold["sections"]
    )


def _mask_entry(
    case_id: str,
    dimension: str,
    model_role: str,
    system_role: str,
    reason: str,
) -> dict[str, str]:
    return {
        "case_id": case_id,
        "dimension": dimension,
        "model_role": model_role,
        "system_role": system_role,
        "reason": reason,
    }


def build_dimension_contract() -> dict[str, Any]:
    """Build the closed semantic-dimension ownership contract."""
    owners = {
        "REPORT_PRESENCE": "DETERMINISTIC_BOUNDARY",
        "REPORT_CONTENT": "MODEL",
        "SECTION_STRUCTURE": "MODEL",
        "SECTION_ALLOCATION": "MODEL",
        "SECTION_ORDER": "MODEL",
        "FEATURE_KIND": "MODEL",
        "FEATURE_MULTIPLICITY": "MODEL",
        "REQUIRED_CONTEXT": "MODEL",
        "REFERENCE_PRESENCE": "SHARED_EXPLICIT_BOUNDARY",
        "REFERENCE_KIND": "MODEL",
        "REFERENCE_TARGET": "MODEL",
        "ANNOTATION": "MODEL",
        "CONSTRAINT_SCOPE": "MODEL",
        "UNRESOLVED_REQUIREMENT": "MODEL",
    }
    return {
        "schema_version": "si-v2r.sr7-p0.semantic-dimension-contract.v2",
        "baseline": BASELINE_SHA,
        "dimensions": [
            {
                "dimension": dimension,
                "owner": owners[dimension],
                "meaning": "semantic obligation defined by the frozen V2R contract",
            }
            for dimension in DIMENSIONS
        ],
        "allowed_model_roles": list(MODEL_ROLES),
        "allowed_system_roles": list(SYSTEM_ROLES),
        "equivalence": {
            "identity": "semantic_ids_are_local_handles_not_semantic_values",
            "relationship_targets": "compare_target_feature_position_within_section",
            "text": "compare_normalized_owned_context_using_lq0_preservation_rules",
            "section_order": "ordered_id_invariant_semantic_and_owned_context_signatures",
            "CONSTRAINT_SCOPE": "MODEL_EXCEPT_GARNET_CASE_SPECIFIC_MASK",
        },
        "case_specific_overrides": [
            {
                "case_id": "cm59-single-garnet-06",
                "dimension": "CONSTRAINT_SCOPE",
                "owner": "UNRESOLVED_CONTRACT",
                "reason": "SR4 leaves Garnet depth-column ownership unresolved.",
            }
        ],
        "historical_outcomes_used_to_construct_mask": False,
    }


def build_case_dimension_mask(repo_root: Path) -> dict[str, Any]:
    """Build the complete case-by-dimension grading mask."""
    corpus, gold_by_id = _case_files(repo_root)
    rows: list[dict[str, str]] = []
    for case in corpus:
        case_id = case["case_id"]
        gold = gold_by_id[case_id]
        section_count = len(gold["sections"])
        report = gold.get("report_work") is not None
        has_features = _has_features(gold)
        has_reference = _has_reference(gold)
        has_context = _has_context(gold)
        has_annotation = _has_annotation(gold)
        has_constraints = any(
            section.get("constraints")
            or any(feature.get("constraints") for feature in section.get("features", []))
            for section in gold["sections"]
        )
        for dimension in DIMENSIONS:
            model_role = "NOT_APPLICABLE"
            system_role = "SYSTEM_NOT_APPLICABLE"
            reason = "no corresponding obligation in the frozen gold intent"
            if dimension == "REPORT_PRESENCE":
                model_role = "RAW_MODEL_DIAGNOSTIC"
                system_role = "SYSTEM_CREDIT_ELIGIBLE"
                reason = "presence is owned by the deterministic report boundary"
            elif dimension == "REPORT_CONTENT" and report:
                model_role = "PRIMARY_MODEL_OBLIGATION"
                system_role = "SYSTEM_CREDIT_BLOCKED"
                reason = "report content remains model-owned"
            elif dimension == "SECTION_STRUCTURE" and section_count:
                model_role = "PRIMARY_MODEL_OBLIGATION"
                system_role = "SYSTEM_CREDIT_BLOCKED"
                reason = "the request requires one or more section structures"
            elif dimension == "SECTION_ALLOCATION" and section_count > 1:
                model_role = "PRIMARY_MODEL_OBLIGATION"
                system_role = "SYSTEM_CREDIT_BLOCKED"
                reason = "multiple independent sections require allocation"
            elif dimension == "SECTION_ORDER" and section_count > 1:
                model_role = "PRIMARY_MODEL_OBLIGATION"
                system_role = "SYSTEM_CREDIT_BLOCKED"
                reason = "multiple sections have an ordered request"
            elif dimension in {"FEATURE_KIND", "FEATURE_MULTIPLICITY"} and has_features:
                model_role = "PRIMARY_MODEL_OBLIGATION"
                system_role = "SYSTEM_CREDIT_BLOCKED"
                reason = "the section contains one or more requested features"
            elif dimension == "REQUIRED_CONTEXT" and has_context:
                model_role = "PRIMARY_MODEL_OBLIGATION"
                system_role = "SYSTEM_CREDIT_BLOCKED"
                reason = "the gold intent contains explicit contextual requirements"
            elif dimension == "REFERENCE_PRESENCE":
                if has_reference:
                    model_role = "PRIMARY_MODEL_OBLIGATION"
                    system_role = "SYSTEM_CREDIT_ELIGIBLE"
                    reason = "explicit reference presence is a shared boundary obligation"
                elif section_count:
                    model_role = "RAW_MODEL_DIAGNOSTIC"
                    system_role = "SYSTEM_CREDIT_BLOCKED"
                    reason = "unspecified reference generation is diagnostic only"
            elif dimension == "REFERENCE_KIND" and has_reference:
                model_role = "PRIMARY_MODEL_OBLIGATION"
                system_role = "SYSTEM_CREDIT_BLOCKED"
                reason = "reference kind remains model-owned"
            elif dimension == "REFERENCE_TARGET" and any(
                section.get("reference_intent", {}).get("target_semantic_id")
                for section in gold["sections"]
                if section.get("reference_intent")
            ):
                model_role = "PRIMARY_MODEL_OBLIGATION"
                system_role = "SYSTEM_CREDIT_BLOCKED"
                reason = "reference target remains model-owned"
            elif dimension == "ANNOTATION" and has_annotation:
                model_role = "PRIMARY_MODEL_OBLIGATION"
                system_role = "SYSTEM_CREDIT_BLOCKED"
                reason = "annotation semantics remain model-owned"
            elif dimension == "CONSTRAINT_SCOPE" and has_constraints:
                if "garnet" in case_id:
                    model_role = "MASKED_UNRESOLVED_CONTRACT"
                    reason = "depth-column ownership/scope remains unresolved by SR4"
                else:
                    model_role = "PRIMARY_MODEL_OBLIGATION"
                    reason = "constraint scope is explicit outside the unresolved Garnet rule"
                system_role = "SYSTEM_CREDIT_BLOCKED"
            elif dimension == "UNRESOLVED_REQUIREMENT" and gold.get("unresolved_requirements"):
                model_role = "PRIMARY_MODEL_OBLIGATION"
                system_role = "SYSTEM_CREDIT_BLOCKED"
                reason = "unresolved promotion remains model-owned"
            elif dimension == "UNRESOLVED_REQUIREMENT" and "iris" in case_id:
                model_role = "PRIMARY_MODEL_OBLIGATION"
                system_role = "SYSTEM_CREDIT_BLOCKED"
                reason = "accepted Iris contract retains unresolved promotion as model-owned"
            rows.append(_mask_entry(case_id, dimension, model_role, system_role, reason))
    return {
        "schema_version": "si-v2r.sr7-p0.case-dimension-mask.v1",
        "baseline": BASELINE_SHA,
        "case_count": 24,
        "dimension_count": len(DIMENSIONS),
        "rows": rows,
    }


def build_execution_schedule(repo_root: Path) -> dict[str, Any]:
    """Build the balanced 96-row future execution schedule."""
    corpus, _ = _case_files(repo_root)
    rows: list[dict[str, Any]] = []
    order_index = 0
    for case_index, case in enumerate(corpus):
        first = ("A", "B") if case_index % 2 == 0 else ("B", "A")
        sequence = (
            (first[0], 0),
            (first[1], 0),
            (first[1], 1),
            (first[0], 1),
        )
        for configuration_id, attempt_index in sequence:
            rows.append(
                {
                    "case_id": case["case_id"],
                    "case_index": case_index,
                    "configuration_id": configuration_id,
                    "attempt_index": attempt_index,
                    "execution_order_index": order_index,
                }
            )
            order_index += 1
    return {
        "schema_version": "si-v2r.sr7-p0.execution-schedule.v1",
        "case_count": 24,
        "attempts_per_configuration": 2,
        "configuration_count": 2,
        "base_logical_call_count": 96,
        "rows": rows,
    }


def build_comparison_contract() -> dict[str, Any]:
    """Build the paired comparison and directional-decision contract."""
    return {
        "schema_version": "si-v2r.sr7-p0.comparison-contract.v1",
        "baseline": BASELINE_SHA,
        "case_relation": list(RELATIONS),
        "mixed_tradeoff_relation": "UNCHANGED",
        "mixed_tradeoff_reason": "MIXED_TRADEOFF",
        "primary_dimensions": "PRIMARY_MODEL_OBLIGATION",
        "secondary_dimensions": "PRIMARY_MODEL_OBLIGATION + RAW_MODEL_DIAGNOSTIC",
        "structural_relation_tuple": ["final_canonical_count", "initial_canonical_pass_count"],
        "system_outcomes_separate": True,
        "attempts_are_repeated_measurements": True,
        "no_arbitrary_weighting": True,
        "no_p_value_promotion_gate": True,
        "directional_rules": {
            "B_DIRECTIONALLY_BETTER": [
                "B_BETTER primary cases > A_BETTER primary cases",
                "B primary dimension accuracy > A primary dimension accuracy",
                "B terminal structural failures <= A terminal structural failures",
            ],
            "A_DIRECTIONALLY_BETTER": "symmetric",
            "NO_CLEAR_DIRECTIONAL_DIFFERENCE": "otherwise when evidence is comparable",
        },
        "study_integrity_decisions": [
            "INCONCLUSIVE_INFRASTRUCTURE",
            "INCONCLUSIVE_CONFIGURATION_DRIFT",
            "INCONCLUSIVE_EVIDENCE",
        ],
    }


def build_runtime_attestation_contract() -> dict[str, Any]:
    """Build the material runtime identity and drift contract."""
    common = {
        "configuration_id": "required",
        "base_url": "required",
        "requested_model": "required",
        "returned_model": "required",
        "temperature": "required",
        "max_tokens": "required",
        "timeout_seconds": "required",
        "structured_output_type": "required",
        "strict": "required",
        "schema_sha256": "required",
        "system_prompt_sha256": "required",
        "retry_prompt_sha256": "required",
        "case_corpus_sha256": "required",
        "comparison_concurrency": "required",
    }
    return {
        "schema_version": "si-v2r.sr7-p0.runtime-attestation.v1",
        "baseline": BASELINE_SHA,
        "material_fields": {
            "A": common,
            "B": {**common, "top_p": "required", "reasoning_effort": "required"},
        },
        "unavailable_provenance": "UNAVAILABLE_FROM_SERVING_INTERFACE",
        "unrelated_catalog_changes": "not material drift",
        "unexpected_returned_model": "stop and classify INCONCLUSIVE_CONFIGURATION_DRIFT",
        "preflight_mismatch": "abort before first semantic call",
    }


def build_evidence_schema() -> dict[str, Any]:
    """Build the bounded future live-evidence schema description."""
    required = [
        "experiment_version",
        "comparison_contract_sha256",
        "configuration_id",
        "configuration_fingerprint",
        "case_id",
        "family",
        "case_index",
        "attempt_index",
        "execution_order_index",
        "request_sha256",
        "system_prompt_sha256",
        "retry_prompt_sha256",
        "schema_sha256",
        "gold_sha256",
        "mask_sha256",
        "runtime_material_attestation",
        "provider_call_count",
        "infrastructure_retry_count",
        "structural_retry_count",
        "initial_transport_status",
        "initial_finish_reason",
        "initial_valid_json",
        "initial_json_schema_status",
        "initial_pydantic_status",
        "initial_usage",
        "initial_latency_ms",
        "retry_transport_status",
        "retry_finish_reason",
        "retry_valid_json",
        "retry_json_schema_status",
        "retry_pydantic_status",
        "final_canonical_status",
        "model_semantics",
        "semantic_dimension_results",
        "compiler_status",
        "compiler_failure_category",
        "safety_actions",
        "system_dimension_results",
        "terminal_row_status",
    ]
    return {
        "schema_version": "si-v2r.sr7-p0.evidence-schema.v1",
        "baseline": BASELINE_SHA,
        "required_fields": required,
        "forbidden_fields": [
            "credentials",
            "authorization_headers",
            "reasoning_text",
            "environment_dump",
        ],
        "canonical_v2r_retained": True,
        "provider_metadata_allowed": [
            "returned_model",
            "finish_reason",
            "usage",
            "latency",
            "reasoning_token_count",
            "http_category",
        ],
        "attempt_row_count": 96,
        "retry_limits": {"infrastructure": 1, "structural": 1},
    }


def _report_content_equivalent(generated: SemanticIRV2R, gold: SemanticIRV2R) -> bool:
    """Compare report-owned requirements without requiring wording identity."""
    generated_report = context_projection(generated)["report_work"]
    gold_report = context_projection(gold)["report_work"]
    if (generated_report is None) != (gold_report is None):
        return False
    if gold_report is None:
        return True
    generated_values = [
        generated_report["goal"],
        *generated_report["requirements"],
        *generated_report["constraints"],
    ]
    for field_name in ("requirements", "constraints"):
        for required in gold_report[field_name]:
            if required and not any(required in value for value in generated_values):
                return False
    return True


def _section_order_projection(intent: SemanticIRV2R) -> list[dict[str, object]]:
    """Build ordered section signatures without using local semantic IDs."""
    hard_sections = semantic_projection(intent)["sections"]
    context_sections = context_projection(intent)["sections"]
    return [
        {"semantic": hard_section, "context": context_section}
        for hard_section, context_section in zip(hard_sections, context_sections, strict=True)
    ]


def _owned_context_equivalent(generated: SemanticIRV2R, gold: SemanticIRV2R) -> bool:
    """Apply LQ0 preservation plus normalized section-owned source context."""
    preserved, _ = _required_context_preservation(generated, gold)
    if not preserved:
        return False
    generated_sections = context_projection(generated)["sections"]
    gold_sections = context_projection(gold)["sections"]
    if len(generated_sections) != len(gold_sections):
        return False
    for generated_section, gold_section in zip(generated_sections, gold_sections, strict=True):
        for required in gold_section["source_hints"]:
            if required and not any(
                required in value for value in generated_section["source_hints"]
            ):
                return False
        required_hint = gold_section["existing_section_hint"]
        generated_hint = generated_section["existing_section_hint"]
        if required_hint and (generated_hint is None or required_hint not in generated_hint):
            return False
    return True


def _annotation_projection(intent: SemanticIRV2R) -> list[list[dict[str, object]]]:
    """Project annotation meaning and owned context while omitting annotation IDs."""
    hard_sections = semantic_projection(intent)["sections"]
    context_sections = context_projection(intent)["sections"]
    result: list[list[dict[str, object]]] = []
    for hard_section, context_section in zip(hard_sections, context_sections, strict=True):
        annotations = []
        for feature, feature_context in zip(
            hard_section["features"], context_section["feature_context"], strict=True
        ):
            if feature["kind"] == "annotation":
                annotations.append(feature_context)
        result.append(annotations)
    return result


def _constraint_projection(intent: SemanticIRV2R) -> list[dict[str, object]]:
    """Project constraint ownership with normalized text and stable positions."""
    return [
        {
            "section": section["constraints"],
            "features": [feature["constraints"] for feature in section["feature_context"]],
        }
        for section in context_projection(intent)["sections"]
    ]


def _unresolved_projection(intent: SemanticIRV2R) -> list[str]:
    """Normalize unresolved requirements without preserving spelling noise."""
    return context_projection(intent)["unresolved_requirements"]


def _dimension_equivalent(generated: SemanticIRV2R, gold: SemanticIRV2R, dimension: str) -> bool:
    """Evaluate one dimension using accepted semantic, ownership, and text rules."""
    generated_hard = semantic_projection(generated)
    gold_hard = semantic_projection(gold)
    if dimension == "REPORT_PRESENCE":
        return generated_hard["report_work_present"] == gold_hard["report_work_present"]
    if dimension == "REPORT_CONTENT":
        return _report_content_equivalent(generated, gold)
    if dimension == "SECTION_STRUCTURE":
        return [section["kind"] for section in generated_hard["sections"]] == [
            section["kind"] for section in gold_hard["sections"]
        ]
    if dimension == "SECTION_ALLOCATION":
        return generated_hard["section_count"] == gold_hard["section_count"]
    if dimension == "SECTION_ORDER":
        return _section_order_projection(generated) == _section_order_projection(gold)
    if dimension == "FEATURE_KIND":
        return [
            [feature["kind"] for feature in section["features"]]
            for section in generated_hard["sections"]
        ] == [
            [feature["kind"] for feature in section["features"]]
            for section in gold_hard["sections"]
        ]
    if dimension == "FEATURE_MULTIPLICITY":
        return [len(section["features"]) for section in generated_hard["sections"]] == [
            len(section["features"]) for section in gold_hard["sections"]
        ]
    if dimension == "REQUIRED_CONTEXT":
        return _owned_context_equivalent(generated, gold)
    if dimension == "REFERENCE_PRESENCE":
        return [
            section["reference_intent"] is not None for section in generated_hard["sections"]
        ] == [section["reference_intent"] is not None for section in gold_hard["sections"]]
    if dimension == "REFERENCE_KIND":
        return [
            None if section["reference_intent"] is None else section["reference_intent"]["kind"]
            for section in generated_hard["sections"]
        ] == [
            None if section["reference_intent"] is None else section["reference_intent"]["kind"]
            for section in gold_hard["sections"]
        ]
    if dimension == "REFERENCE_TARGET":
        return [
            None
            if section["reference_intent"] is None
            else section["reference_intent"].get("target_feature_position")
            for section in generated_hard["sections"]
        ] == [
            None
            if section["reference_intent"] is None
            else section["reference_intent"].get("target_feature_position")
            for section in gold_hard["sections"]
        ]
    if dimension == "ANNOTATION":
        return _annotation_projection(generated) == _annotation_projection(gold)
    if dimension == "CONSTRAINT_SCOPE":
        return _constraint_projection(generated) == _constraint_projection(gold)
    if dimension == "UNRESOLVED_REQUIREMENT":
        return _unresolved_projection(generated) == _unresolved_projection(gold)
    raise KeyError(dimension)


def _semantic_model(value: dict[str, Any]) -> SemanticIRV2R:
    """Validate a fixture or provider object without its external case label."""
    return SemanticIRV2R.model_validate(
        {key: item for key, item in value.items() if key != "case_id"}
    )


def grade_semantics(
    request_case: dict[str, Any],
    frozen_gold: dict[str, Any],
    generated_v2r: dict[str, Any] | None,
    case_dimension_mask: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Grade one generated object using only frozen input and mask data."""
    del request_case
    rows = [row for row in case_dimension_mask["rows"] if row["case_id"] == frozen_gold["case_id"]]
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        dimension = row["dimension"]
        if row["model_role"] == "NOT_APPLICABLE":
            result[dimension] = {"status": "NOT_APPLICABLE", "model_role": row["model_role"]}
            continue
        if row["model_role"] == "MASKED_UNRESOLVED_CONTRACT":
            result[dimension] = {"status": "MASKED", "model_role": row["model_role"]}
            continue
        if generated_v2r is None:
            result[dimension] = {
                "status": "NOT_EVALUABLE_STRUCTURAL",
                "model_role": row["model_role"],
            }
            continue
        expected_model = _semantic_model(frozen_gold)
        actual_model = _semantic_model(generated_v2r)
        result[dimension] = {
            "status": (
                "CORRECT"
                if _dimension_equivalent(actual_model, expected_model, dimension)
                else "INCORRECT"
            ),
            "model_role": row["model_role"],
        }
    return result


def _pair_relation(a_correct: int, b_correct: int, matched: int) -> str:
    if matched == 0:
        return "NOT_COMPARABLE"
    if a_correct > b_correct:
        return "A_BETTER"
    if b_correct > a_correct:
        return "B_BETTER"
    return "UNCHANGED"


def _dimension_relations(
    rows: list[dict[str, Any]], mask: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    semantic_rows = [row for row in rows if "configuration_id" in row]
    by_key = {
        (row["configuration_id"], row["case_id"], row["attempt_index"]): row
        for row in semantic_rows
    }
    result: dict[str, dict[str, Any]] = {}
    for case_id in sorted({row["case_id"] for row in semantic_rows}):
        case_mask_dimensions = tuple(
            row["dimension"] for row in mask["rows"] if row["case_id"] == case_id
        )
        for dimension in case_mask_dimensions:
            mask_row = next(
                row
                for row in mask["rows"]
                if row["case_id"] == case_id and row["dimension"] == dimension
            )
            if mask_row["model_role"] not in {"PRIMARY_MODEL_OBLIGATION", "RAW_MODEL_DIAGNOSTIC"}:
                result[f"{case_id}:{dimension}"] = {
                    "case_id": case_id,
                    "dimension": dimension,
                    "relation": "NOT_COMPARABLE",
                    "matched_evaluable_attempts": 0,
                    "a_correct": 0,
                    "b_correct": 0,
                }
                continue
            matched = a_correct = b_correct = 0
            for attempt in (0, 1):
                left = by_key.get(("A", case_id, attempt))
                right = by_key.get(("B", case_id, attempt))
                if not left or not right:
                    continue
                a_status = left["semantic_dimension_results"][dimension]["status"]
                b_status = right["semantic_dimension_results"][dimension]["status"]
                if a_status not in {"CORRECT", "INCORRECT"} or b_status not in {
                    "CORRECT",
                    "INCORRECT",
                }:
                    continue
                matched += 1
                a_correct += a_status == "CORRECT"
                b_correct += b_status == "CORRECT"
            result[f"{case_id}:{dimension}"] = {
                "case_id": case_id,
                "dimension": dimension,
                "relation": _pair_relation(a_correct, b_correct, matched),
                "matched_evaluable_attempts": matched,
                "a_correct": a_correct,
                "b_correct": b_correct,
            }
    return result


def derive_comparison(rows: list[dict[str, Any]], mask: dict[str, Any]) -> dict[str, Any]:
    """Derive paired relations without weights or model/provider calls."""
    dimensions = _dimension_relations(rows, mask)
    case_relations: dict[str, dict[str, Any]] = {}
    semantic_rows = [row for row in rows if "configuration_id" in row]
    for case_id in sorted({row["case_id"] for row in semantic_rows}):
        primary = [
            value["relation"]
            for key, value in dimensions.items()
            if key.startswith(f"{case_id}:")
            and next(
                row
                for row in mask["rows"]
                if row["case_id"] == case_id and row["dimension"] == value["dimension"]
            )["model_role"]
            == "PRIMARY_MODEL_OBLIGATION"
            and value["relation"] != "NOT_COMPARABLE"
        ]
        if not primary:
            relation = "NOT_COMPARABLE"
            reason = None
        elif "A_BETTER" in primary and "B_BETTER" not in primary:
            relation, reason = "A_BETTER", None
        elif "B_BETTER" in primary and "A_BETTER" not in primary:
            relation, reason = "B_BETTER", None
        else:
            relation = "UNCHANGED"
            reason = "MIXED_TRADEOFF" if "A_BETTER" in primary or "B_BETTER" in primary else "EQUAL"
        case_relations[case_id] = {"relation": relation, "unchanged_reason": reason}
    return {"dimension_relations": dimensions, "case_relations": case_relations}


def system_dimension_outcomes(
    mask: dict[str, Any],
    semantic_dimension_results: dict[str, dict[str, Any]],
    credited_interventions: set[str] | None = None,
) -> dict[str, str]:
    """Project model results into separate contract-credited system outcomes."""
    credited_interventions = credited_interventions or set()
    output: dict[str, str] = {}
    for row in mask["rows"]:
        dimension = row["dimension"]
        if dimension in output:
            continue
        model_status = semantic_dimension_results.get(dimension, {}).get("status")
        if row["model_role"] == "NOT_APPLICABLE":
            output[dimension] = "SYSTEM_NOT_APPLICABLE"
        elif model_status in {"NOT_EVALUABLE_STRUCTURAL", "NOT_EVALUABLE_INFRA"}:
            output[dimension] = "SYSTEM_NOT_EVALUABLE"
        elif model_status == "CORRECT" or (
            dimension in credited_interventions and row["system_role"] == "SYSTEM_CREDIT_ELIGIBLE"
        ):
            output[dimension] = "SYSTEM_CORRECT"
        elif row["system_role"] == "SYSTEM_CREDIT_BLOCKED":
            output[dimension] = "SYSTEM_BLOCKED"
        else:
            output[dimension] = "SYSTEM_INCORRECT"
    return output


def structural_relation(a_rows: list[dict[str, Any]], b_rows: list[dict[str, Any]]) -> str:
    """Compare structural reliability using the frozen lexicographic tuple."""

    def score(rows: list[dict[str, Any]]) -> tuple[int, int]:
        return (
            sum(row.get("final_canonical_status") == "PASS" for row in rows),
            sum(row.get("initial_canonical_status") == "PASS" for row in rows),
        )

    a_score = score(a_rows)
    b_score = score(b_rows)
    if a_score > b_score:
        return "A_BETTER"
    if b_score > a_score:
        return "B_BETTER"
    return "UNCHANGED"


def validate_runtime_attestation(actual: dict[str, Any], expected: dict[str, Any]) -> str:
    """Return a fail-closed runtime-attestation status."""
    material_fields = (
        "configuration_id",
        "base_url",
        "requested_model",
        "returned_model",
        "temperature",
        "max_tokens",
        "timeout_seconds",
        "structured_output_type",
        "strict",
        "schema_sha256",
        "system_prompt_sha256",
        "retry_prompt_sha256",
        "case_corpus_sha256",
        "comparison_concurrency",
    )
    for field in material_fields:
        if field not in actual or field not in expected or actual[field] != expected[field]:
            return "INCONCLUSIVE_CONFIGURATION_DRIFT"
    for field in ("top_p", "reasoning_effort"):
        if field in expected and actual.get(field) != expected[field]:
            return "INCONCLUSIVE_CONFIGURATION_DRIFT"
    return "OK"


def validate_evidence_rows(
    rows: list[dict[str, Any]],
    schedule: dict[str, Any],
    *,
    expected_mask_sha256: str,
    expected_contract_sha256: str,
) -> list[str]:
    """Return integrity errors for a future 96-row evidence population."""
    errors: list[str] = []
    expected_keys = {
        (
            item["configuration_id"],
            item["case_id"],
            item["attempt_index"],
        )
        for item in schedule["rows"]
    }
    actual_keys = {
        (
            row.get("configuration_id"),
            row.get("case_id"),
            row.get("attempt_index"),
        )
        for row in rows
    }
    if len(rows) != len(expected_keys):
        errors.append("ROW_COUNT")
    if len(actual_keys) != len(rows):
        errors.append("DUPLICATE_LOGICAL_ATTEMPT")
    if actual_keys != expected_keys:
        errors.append("SCHEDULE_POPULATION_MISMATCH")
    for row in rows:
        if row.get("mask_sha256") != expected_mask_sha256:
            errors.append("MASK_HASH")
        if row.get("comparison_contract_sha256") != expected_contract_sha256:
            errors.append("CONTRACT_HASH")
        if row.get("infrastructure_retry_count", 0) > 1:
            errors.append("INFRASTRUCTURE_RETRY_LIMIT")
        if row.get("structural_retry_count", 0) > 1:
            errors.append("STRUCTURAL_RETRY_LIMIT")
    return sorted(set(errors))


def classify_future_comparison(summary: dict[str, Any]) -> str:
    """Apply the frozen study-level directional rules to derived metrics."""
    if summary.get("infrastructure_failure"):
        return "INCONCLUSIVE_INFRASTRUCTURE"
    if summary.get("configuration_drift"):
        return "INCONCLUSIVE_CONFIGURATION_DRIFT"
    if summary.get("evidence_invalid"):
        return "INCONCLUSIVE_EVIDENCE"
    if summary.get("structural_materially_contradicts"):
        return "NO_CLEAR_DIRECTIONAL_DIFFERENCE"
    if (
        summary.get("b_case_wins", 0) > summary.get("a_case_wins", 0)
        and summary.get("b_dimension_accuracy", 0) > summary.get("a_dimension_accuracy", 0)
        and summary.get("b_terminal_structural_failures", 0)
        <= summary.get("a_terminal_structural_failures", 0)
    ):
        return "CONFIGURATION_B_DIRECTIONALLY_BETTER"
    if (
        summary.get("a_case_wins", 0) > summary.get("b_case_wins", 0)
        and summary.get("a_dimension_accuracy", 0) > summary.get("b_dimension_accuracy", 0)
        and summary.get("a_terminal_structural_failures", 0)
        <= summary.get("b_terminal_structural_failures", 0)
    ):
        return "CONFIGURATION_A_DIRECTIONALLY_BETTER"
    return "NO_CLEAR_DIRECTIONAL_DIFFERENCE"


def _synthetic_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case_id, a_status, b_status in (
        ("a-better", "CORRECT", "INCORRECT"),
        ("b-better", "INCORRECT", "CORRECT"),
        ("equal", "CORRECT", "CORRECT"),
        ("mixed", "CORRECT", "INCORRECT"),
        ("not-comparable", "NOT_EVALUABLE_STRUCTURAL", "CORRECT"),
    ):
        for configuration_id, status in (("A", a_status), ("B", b_status)):
            for attempt in (0, 1):
                rows.append(
                    {
                        "configuration_id": configuration_id,
                        "case_id": case_id,
                        "attempt_index": attempt,
                        "semantic_dimension_results": {
                            "REPORT_CONTENT": {
                                "status": status,
                                "model_role": "PRIMARY_MODEL_OBLIGATION",
                            },
                            **(
                                {
                                    "ANNOTATION": {
                                        "status": (
                                            "INCORRECT" if configuration_id == "A" else "CORRECT"
                                        ),
                                        "model_role": "PRIMARY_MODEL_OBLIGATION",
                                    }
                                }
                                if case_id == "mixed"
                                else {}
                            ),
                        },
                        "initial_canonical_status": "PASS" if status == "CORRECT" else "FAIL",
                        "final_canonical_status": "PASS"
                        if status != "NOT_EVALUABLE_STRUCTURAL"
                        else "FAIL",
                    }
                )
    # Add the system-credit and infrastructure branches as explicit evidence examples.
    rows.extend(
        [
            {
                "branch": "system_credit_blocked",
                "model_status": "INCORRECT",
                "system_status": "SYSTEM_BLOCKED",
            },
            {"branch": "infrastructure_non_evaluable", "status": "NOT_EVALUABLE_INFRA"},
            {"branch": "configuration_drift", "decision": "INCONCLUSIVE_CONFIGURATION_DRIFT"},
            {"branch": "masked_dimension", "status": "MASKED"},
            {"branch": "structural_terminal", "status": "NOT_EVALUABLE_STRUCTURAL"},
        ]
    )
    return rows


def build_synthetic_fixture() -> dict[str, Any]:
    """Build a provider-free fixture covering comparison decision branches."""
    return {
        "schema_version": "si-v2r.sr7-p0.synthetic-paired-fixture.v1",
        "provider_calls": 0,
        "rows": _synthetic_rows(),
        "expected_branches": {
            "a-better": "A_BETTER",
            "b-better": "B_BETTER",
            "equal": "UNCHANGED",
            "mixed": "UNCHANGED",
            "not-comparable": "NOT_COMPARABLE",
        },
    }


def _synthetic_mask() -> dict[str, Any]:
    rows = [
        {
            "case_id": case_id,
            "dimension": "REPORT_CONTENT",
            "model_role": "PRIMARY_MODEL_OBLIGATION",
        }
        for case_id in ("a-better", "b-better", "equal", "mixed", "not-comparable")
    ]
    rows.append(
        {
            "case_id": "mixed",
            "dimension": "ANNOTATION",
            "model_role": "PRIMARY_MODEL_OBLIGATION",
        }
    )
    return {"rows": rows}


def _validate_synthetic_fixture(fixture: dict[str, Any]) -> None:
    rows = [row for row in fixture["rows"] if "configuration_id" in row]
    comparison = derive_comparison(rows, _synthetic_mask())
    for case_id, expected in fixture["expected_branches"].items():
        assert comparison["case_relations"][case_id]["relation"] == expected
    assert fixture["provider_calls"] == 0


def _configuration_contract(repo_root: Path) -> dict[str, Any]:
    a = _load_json(repo_root / C0_DIR / "configuration_a.json")
    b = _load_json(repo_root / C0_DIR / "configuration_b.json")
    return {
        "schema_version": "si-v2r.sr7-p0.configuration-contract.v1",
        "baseline": BASELINE_SHA,
        "configurations": [
            {
                "configuration_id": "A",
                "role": "CURRENT_BASELINE",
                "fingerprint": CONFIGURATION_A_FINGERPRINT,
                "provider": a["provider"],
                "base_url": a["base_url"],
                "requested_model": a["requested_model"],
                "temperature": 0.0,
                "top_p": None,
                "reasoning_effort": None,
                "max_tokens": 16384,
                "timeout_seconds": 900,
                "concurrency": 1,
                "structured_output": "response_format=json_schema",
                "strict": True,
                "artifact_provenance": "UNAVAILABLE_FROM_SERVING_INTERFACE",
            },
            {
                "configuration_id": "B",
                "role": "CANDIDATE",
                "fingerprint": CONFIGURATION_B_FINGERPRINT,
                "provider": "NVIDIA",
                "base_url": b["base_url"],
                "requested_model": b["requested_model"],
                "temperature": 1.0,
                "top_p": 0.95,
                "reasoning_effort": "low",
                "max_tokens": 16384,
                "timeout_seconds": 900,
                "concurrency": 1,
                "structured_output": "response_format=json_schema",
                "strict": True,
                "artifact_provenance": "UNAVAILABLE_FROM_HOSTED_PROVIDER",
            },
        ],
        "comparison_claim": "model-plus-serving configuration comparison",
        "not_claimed": ["model-only causal superiority", "production readiness", "generalization"],
    }


def _prelive_result(
    configs: dict[str, Any],
    dimensions: dict[str, Any],
    mask: dict[str, Any],
    comparison: dict[str, Any],
    runtime: dict[str, Any],
    schedule: dict[str, Any],
    evidence: dict[str, Any],
    synthetic: dict[str, Any],
) -> dict[str, Any]:
    contract_hashes = {
        "configuration_contract_sha256": sha256_text(canonical_json(configs)),
        "runtime_attestation_contract_sha256": sha256_text(canonical_json(runtime)),
        "semantic_dimension_contract_sha256": sha256_text(canonical_json(dimensions)),
        "case_dimension_mask_sha256": sha256_text(canonical_json(mask)),
        "comparison_contract_sha256": sha256_text(canonical_json(comparison)),
        "execution_schedule_sha256": sha256_text(canonical_json(schedule)),
        "evidence_schema_sha256": sha256_text(canonical_json(evidence)),
    }
    return {
        "schema_version": "si-v2r.sr7-p0.prelive-result.v2",
        "baseline": BASELINE_SHA,
        "decision": "SI_V2R_SR7_P0_REWORK_REQUIRED",
        "configuration_a_fingerprint": CONFIGURATION_A_FINGERPRINT,
        "configuration_b_fingerprint": CONFIGURATION_B_FINGERPRINT,
        "case_count": 24,
        "dimension_count": len(DIMENSIONS),
        "case_dimension_row_count": len(mask["rows"]),
        "base_logical_call_count": 96,
        "provider_calls": 0,
        "endpoint_calls": 0,
        "worker_program_calls": 0,
        "production_changes": 0,
        "prompt_changed": False,
        "schema_changed": False,
        "gold_changed": False,
        "cm58_changed": False,
        "v2r_changed": False,
        "adr_cm57": "UNCHANGED",
        "garnet_whole_case_excluded": False,
        "verde_reference_overreach_role": "RAW_MODEL_DIAGNOSTIC",
        "verde_reference_removal_model_credit": False,
        "verde_reference_removal_system_credit": "BLOCKED",
        "amber_annotation_role": "PRIMARY_MODEL_OBLIGATION",
        "iris_annotation_role": "PRIMARY_MODEL_OBLIGATION",
        "iris_unresolved_requirement_role": "PRIMARY_MODEL_OBLIGATION",
        "synthetic_fixture_provider_calls": synthetic["provider_calls"],
        "artifact_hashes": contract_hashes,
    }


def build_artifacts(repo_root: Path) -> dict[str, Any]:
    """Build every committed P0 artifact without provider or endpoint access."""
    _assert_lineage(repo_root)
    _assert_frozen_inputs(repo_root)
    configs = _configuration_contract(repo_root)
    dimensions = build_dimension_contract()
    mask = build_case_dimension_mask(repo_root)
    comparison = build_comparison_contract()
    runtime = build_runtime_attestation_contract()
    schedule = build_execution_schedule(repo_root)
    evidence = build_evidence_schema()
    synthetic = build_synthetic_fixture()
    _validate_synthetic_fixture(synthetic)
    result = _prelive_result(
        configs, dimensions, mask, comparison, runtime, schedule, evidence, synthetic
    )
    return {
        "configurations.json": configs,
        "semantic_dimension_contract.json": dimensions,
        "case_dimension_mask.json": mask,
        "comparison_contract.json": comparison,
        "runtime_attestation_contract.json": runtime,
        "execution_schedule.json": schedule,
        "evidence_schema.json": evidence,
        "synthetic_pair_fixture.json": synthetic,
        "prelive_result.json": result,
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check_artifacts(repo_root: Path, output_dir: Path) -> None:
    """Fail if committed P0 artifacts differ from deterministic generation."""
    artifacts = build_artifacts(repo_root)
    for name, expected in artifacts.items():
        path = output_dir / name
        if not path.is_file() or json.loads(path.read_text(encoding="utf-8")) != expected:
            raise RuntimeError(f"P0 artifact drifted or missing: {path}")


def write_artifacts(repo_root: Path, output_dir: Path) -> None:
    """Write deterministic P0 artifacts to the new fixture directory."""
    artifacts = build_artifacts(repo_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in artifacts.items():
        _write_json(output_dir / name, value)


def main() -> None:
    """Run provider-free P0 generation or verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write new P0 fixtures")
    parser.add_argument("--check", action="store_true", help="check committed P0 fixtures")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if args.write == args.check:
        parser.error("choose exactly one of --write or --check")
    output_dir = args.repo_root / DEFAULT_OUTPUT_DIR
    if args.write:
        write_artifacts(args.repo_root, output_dir)
    else:
        check_artifacts(args.repo_root, output_dir)


if __name__ == "__main__":
    main()
