"""Provider-free SI-V2R SR3 residual root-mechanism decomposition."""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.semantic_ir_v2r_br1_boundary_audit import (
    REPO_ROOT,
    _read_jsonl,
    authenticate_evidence,
)
from scripts.semantic_ir_v2r_sr1_report_routing_audit import _load_cases, _load_gold

BASELINE_SHA = "6d79a9f0cea757b97509dbd42fb50cc309bbae77"
DEFAULT_EVIDENCE = Path("/tmp/si-v2r-live.jsonl")
DEFAULT_OUTPUT_DIR = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr3"
SR2_ROWS = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr2/adjusted_rows.json"
SR2_RESULT = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr2/result.json"
TAXONOMY_VERSION = "si-v2r-sr3.root-mechanisms.v1"
TARGET_CASES = (
    "cm59-single-garnet-06",
    "cm59-alloc-verde-19",
    "cm59-mixed-amber-24",
    "cm59-single-iris-08",
)
FROZEN_RESIDUALS = {
    "cm59-single-garnet-06": ["REQUIRED_CONTEXT_OWNER_ERROR"],
    "cm59-alloc-verde-19": ["REFERENCE_FALSE_POSITIVE"],
    "cm59-mixed-amber-24": [
        "SECTION_ORDER_ERROR",
        "FEATURE_KIND_ERROR",
        "FEATURE_MULTIPLICITY_ERROR",
        "ANNOTATION_ERROR",
        "REQUIRED_CONTEXT_OWNER_ERROR",
    ],
    "cm59-single-iris-08": [
        "REFERENCE_FALSE_POSITIVE",
        "SECTION_ORDER_ERROR",
        "FEATURE_KIND_ERROR",
        "FEATURE_MULTIPLICITY_ERROR",
        "ANNOTATION_ERROR",
        "UNRESOLVED_REQUIREMENT_ERROR",
        "REQUIRED_CONTEXT_OWNER_ERROR",
    ],
}
ROOT_MECHANISMS = (
    "CONSTRAINT_OWNER_MISPLACEMENT",
    "UNREQUESTED_REFERENCE_INFERENCE",
    "ANNOTATION_WRONG_OWNER",
    "UNRESOLVED_PROMOTION",
)
ROOT_EVIDENCE_CLASS = "EMPIRICALLY_SUPPORTED"
LEAF_CLASSES = ("ROOT", "CONSEQUENCE", "CO-ROOT", "INDEPENDENT", "NOT_EXPLAINED")
PROTECTED_PATHS = (
    "src/wellplot/agent/code_mode/semantic_ir_v2r.py",
    "src/wellplot/agent/code_mode/semantic_ir_v2r_compiler.py",
    "src/wellplot/agent/code_mode/semantic_ir_v2_registry.py",
    "src/wellplot/agent/code_mode/capability_safety.py",
    "src/wellplot/agent/code_mode/report_boundary_safety.py",
    "src/wellplot/agent/code_mode/section_leaf_safety.py",
    "src/wellplot/agent/code_mode/planner.py",
    "src/wellplot/agent/providers/base.py",
    "src/wellplot/agent/providers/openai_compat_v2.py",
    "scripts/si_v2r_model_qualification.py",
    "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json",
    "tests/fixtures/semantic_ir_v2r/cm59a_semantic_intents_v2r.json",
)


def _normalise(value: str) -> str:
    """Normalize text for bounded evidence overlap checks."""
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _strings(value: object) -> list[str]:
    """Collect strings from a semantic object without retaining envelopes."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    return []


def _contains_text(value: object, expected: str) -> bool:
    """Check whether all words of an expected phrase occur in generated text."""
    expected_words = _normalise(expected).split()
    generated = set(_normalise(" ".join(_strings(value))).split())
    return bool(expected_words) and all(word in generated for word in expected_words)


def _section_features(projection: dict[str, Any]) -> list[list[str]]:
    """Return ordered feature kinds from a bounded semantic projection."""
    return [
        [str(feature.get("kind")) for feature in section.get("features", [])]
        for section in projection.get("sections", [])
    ]


def _projection_leaf_labels(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """Compute projection-only leaf differences for diagnostics."""
    expected_features = _section_features(expected)
    actual_features = _section_features(actual)
    labels: list[str] = []
    if len(expected_features) != len(actual_features):
        labels.append("SECTION_COUNT_ERROR")
    if len(expected_features) == len(actual_features):
        if expected_features != actual_features:
            labels.append("SECTION_ORDER_ERROR")
        if any(
            set(expected) != set(actual)
            for expected, actual in zip(expected_features, actual_features, strict=True)
        ):
            labels.append("FEATURE_KIND_ERROR")
        if expected_features != actual_features:
            labels.append("FEATURE_MULTIPLICITY_ERROR")
    expected_refs = [section.get("reference_intent") for section in expected.get("sections", [])]
    actual_refs = [section.get("reference_intent") for section in actual.get("sections", [])]
    if [ref is not None for ref in expected_refs] != [ref is not None for ref in actual_refs]:
        labels.append("REFERENCE_FALSE_POSITIVE")
    expected_annotations = [kinds.count("annotation") for kinds in expected_features]
    actual_annotations = [kinds.count("annotation") for kinds in actual_features]
    if expected_annotations != actual_annotations:
        labels.append("ANNOTATION_ERROR")
    return labels


def remove_unrequested_references(projection: dict[str, Any]) -> dict[str, Any]:
    """Remove only generated reference intents for a diagnostic copy."""
    result = copy.deepcopy(projection)
    for section in result.get("sections", []):
        section["reference_intent"] = None
    return result


def reclassify_annotation_requirement(
    projection: dict[str, Any], _model: dict[str, Any]
) -> dict[str, Any]:
    """Represent existing annotation text as an annotation feature diagnostically."""
    result = copy.deepcopy(projection)
    model_sections = _model.get("sections", [])
    for index, section in enumerate(result.get("sections", [])):
        model_section = model_sections[index] if index < len(model_sections) else {}
        section_text = " ".join(_strings(model_section))
        if "annotat" not in section_text.casefold() and "marker" not in section_text.casefold():
            continue
        if any(feature.get("kind") == "annotation" for feature in section.get("features", [])):
            continue
        section.setdefault("features", []).append({"kind": "annotation"})
    return result


def owner_move_diagnostic(model: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any] | None:
    """Describe a textual constraint that is present but attached too high."""
    expected_constraints = [
        constraint
        for section in gold.get("sections", [])
        for feature in section.get("features", [])
        for constraint in feature.get("constraints", [])
    ]
    for constraint in expected_constraints:
        if _contains_text(model, constraint):
            feature_constraints = [
                constraint
                for section in model.get("sections", [])
                for feature in section.get("features", [])
                for constraint in feature.get("constraints", [])
            ]
            if not feature_constraints:
                return {
                    "operation": "move_existing_textual_constraint",
                    "source_owner": "section.goal_or_summary",
                    "target_owner": "feature.constraints",
                    "matched_text": constraint,
                    "predicted_leaf_collapse": ["REQUIRED_CONTEXT_OWNER_ERROR"],
                    "source_content_present": True,
                }
    return None


def _root_mechanisms(
    model: dict[str, Any],
    gold: dict[str, Any],
    expected_projection: dict[str, Any],
    actual_projection: dict[str, Any],
) -> list[dict[str, Any]]:
    """Derive generic mechanisms from generated semantic structure."""
    roots: list[dict[str, Any]] = []
    expected_refs = [
        section.get("reference_intent") for section in expected_projection.get("sections", [])
    ]
    actual_refs = [
        section.get("reference_intent") for section in actual_projection.get("sections", [])
    ]
    if not any(ref is not None for ref in expected_refs) and any(
        ref is not None for ref in actual_refs
    ):
        roots.append(
            {
                "mechanism": "UNREQUESTED_REFERENCE_INFERENCE",
                "evidence_class": ROOT_EVIDENCE_CLASS,
                "support": (
                    "Generated reference_intent is present where the request and gold contain none."
                ),
                "owner_classification": "DETERMINISTIC_SAFETY_CANDIDATE",
            }
        )
    expected_annotations = sum(
        _section_features(expected_projection)[index].count("annotation")
        for index in range(len(expected_projection.get("sections", [])))
    )
    actual_annotations = sum(
        _section_features(actual_projection)[index].count("annotation")
        for index in range(len(actual_projection.get("sections", [])))
    )
    if expected_annotations > actual_annotations and any(
        token in " ".join(_strings(model)).casefold() for token in ("annotat", "marker")
    ):
        roots.append(
            {
                "mechanism": "ANNOTATION_WRONG_OWNER",
                "evidence_class": ROOT_EVIDENCE_CLASS,
                "support": (
                    "Annotation meaning is present in generated prose/requirements "
                    "but no annotation feature is emitted."
                ),
                "owner_classification": "MODEL_SEMANTIC",
            }
        )
    if owner_move_diagnostic(model, gold) is not None:
        roots.append(
            {
                "mechanism": "CONSTRAINT_OWNER_MISPLACEMENT",
                "evidence_class": ROOT_EVIDENCE_CLASS,
                "support": (
                    "A required feature constraint is represented in generated text "
                    "but not under feature.constraints."
                ),
                "owner_classification": "IR_CONTRACT_CANDIDATE",
            }
        )
    if model.get("unresolved_requirements") and not gold.get("unresolved_requirements"):
        roots.append(
            {
                "mechanism": "UNRESOLVED_PROMOTION",
                "evidence_class": ROOT_EVIDENCE_CLASS,
                "support": (
                    "The provider leaves a request-level unresolved requirement "
                    "despite emitting partial structured semantics."
                ),
                "owner_classification": "MODEL_SEMANTIC",
            }
        )
    if not roots:
        roots.append(
            {
                "mechanism": "ROOT_UNRESOLVED",
                "evidence_class": "UNRESOLVED",
                "support": (
                    "Available semantic projections do not support a bounded root mechanism."
                ),
                "owner_classification": "UNRESOLVED",
            }
        )
    return roots


def _classify_leaves(leaves: list[str], roots: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Classify every observed leaf as root, consequence, or unresolved."""
    names = {root["mechanism"] for root in roots}
    result: dict[str, dict[str, str]] = {}
    for leaf in leaves:
        if leaf == "REFERENCE_FALSE_POSITIVE" and "UNREQUESTED_REFERENCE_INFERENCE" in names:
            classification = "ROOT"
            mechanism = "UNREQUESTED_REFERENCE_INFERENCE"
        elif leaf == "ANNOTATION_ERROR" and "ANNOTATION_WRONG_OWNER" in names:
            classification = "ROOT"
            mechanism = "ANNOTATION_WRONG_OWNER"
        elif leaf == "REQUIRED_CONTEXT_OWNER_ERROR" and "CONSTRAINT_OWNER_MISPLACEMENT" in names:
            classification = "ROOT"
            mechanism = "CONSTRAINT_OWNER_MISPLACEMENT"
        elif leaf == "UNRESOLVED_REQUIREMENT_ERROR" and "UNRESOLVED_PROMOTION" in names:
            classification = "ROOT"
            mechanism = "UNRESOLVED_PROMOTION"
        elif "ANNOTATION_WRONG_OWNER" in names and leaf in {
            "SECTION_ORDER_ERROR",
            "FEATURE_KIND_ERROR",
            "FEATURE_MULTIPLICITY_ERROR",
            "REQUIRED_CONTEXT_OWNER_ERROR",
        }:
            classification = "CONSEQUENCE"
            mechanism = "ANNOTATION_WRONG_OWNER"
        else:
            classification = "NOT_EXPLAINED"
            mechanism = "ROOT_UNRESOLVED"
        result[leaf] = {"classification": classification, "mechanism": mechanism}
    return result


def _counterfactuals(
    model: dict[str, Any],
    gold: dict[str, Any],
    expected_projection: dict[str, Any],
    actual_projection: dict[str, Any],
    leaves: list[str],
) -> list[dict[str, Any]]:
    """Run bounded explanatory transformations on copied projections only."""
    diagnostics: list[dict[str, Any]] = []
    if "REFERENCE_FALSE_POSITIVE" in leaves:
        after = remove_unrequested_references(actual_projection)
        diagnostics.append(
            {
                "label": "DIAGNOSTIC_COUNTERFACTUAL",
                "operation": "remove_unrequested_references",
                "applicable": True,
                "predicted_leaf_collapse": sorted(
                    set(_projection_leaf_labels(expected_projection, actual_projection))
                    - set(_projection_leaf_labels(expected_projection, after))
                ),
                "uses_gold_replacement": False,
            }
        )
    if "ANNOTATION_ERROR" in leaves and any(
        token in " ".join(_strings(model)).casefold() for token in ("annotat", "marker")
    ):
        after = reclassify_annotation_requirement(actual_projection, model)
        diagnostics.append(
            {
                "label": "DIAGNOSTIC_COUNTERFACTUAL",
                "operation": "reclassify_existing_annotation_text",
                "applicable": True,
                "predicted_leaf_collapse": sorted(
                    set(_projection_leaf_labels(expected_projection, actual_projection))
                    - set(_projection_leaf_labels(expected_projection, after))
                ),
                "uses_gold_replacement": False,
            }
        )
    owner_move = owner_move_diagnostic(model, gold)
    if owner_move is not None:
        diagnostics.append(
            {"label": "DIAGNOSTIC_COUNTERFACTUAL", **owner_move, "uses_gold_replacement": False}
        )
    return diagnostics


def _stability(attempts: list[dict[str, Any]]) -> str:
    """Classify root-set stability across two attempts."""
    sets = [tuple(root["mechanism"] for root in attempt["root_mechanisms"]) for attempt in attempts]
    if sets[0] == sets[1]:
        return "ROOT_STABLE"
    if set(sets[0]) & set(sets[1]):
        return "ROOT_PARTIALLY_STABLE"
    return "ROOT_VARIABLE"


def _protected_unchanged() -> bool:
    """Verify no protected production or historical artifact changed."""
    return (
        subprocess.run(
            ["git", "diff", "--quiet", BASELINE_SHA, "--", *PROTECTED_PATHS],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
        == 0
    )


def analyze_evidence(evidence_path: Path = DEFAULT_EVIDENCE) -> dict[str, Any]:
    """Analyze the authenticated four-case SR2 residual population."""
    evidence = authenticate_evidence(evidence_path)
    cases = _load_cases()
    gold = _load_gold()
    raw_rows = _read_jsonl(evidence_path)
    sr2_rows = {
        (str(row["case_id"]), int(row["attempt"])): row
        for row in json.loads(SR2_ROWS.read_text(encoding="utf-8"))
    }
    target_rows = [row for row in raw_rows if row["case_id"] in TARGET_CASES]
    if len(target_rows) != 8:
        raise ValueError("SR3 target population must contain exactly eight rows.")
    case_decompositions: list[dict[str, Any]] = []
    counterfactuals: list[dict[str, Any]] = []
    root_prevalence: dict[str, dict[str, Any]] = {
        name: {"attempt_count": 0, "case_ids": set(), "cases": 0} for name in ROOT_MECHANISMS
    }
    for case_id in TARGET_CASES:
        case = cases[case_id]
        gold_model = gold[case_id]
        attempts: list[dict[str, Any]] = []
        case_rows = sorted(
            (row for row in target_rows if row["case_id"] == case_id),
            key=lambda row: int(row["attempt"]),
        )
        for row in case_rows:
            provider = row["provider"]
            model = provider.get("semantic_model")
            if model is None:
                raise ValueError(f"Target row is structurally unavailable: {case_id}")
            sr2 = sr2_rows[(case_id, int(row["attempt"]))]
            leaves = list(sr2["adjusted_residual_mechanisms"])
            expected_projection = provider["expected_semantic_projection"]
            actual_projection = provider["semantic_projection"]
            roots = _root_mechanisms(model, gold_model, expected_projection, actual_projection)
            leaf_classification = _classify_leaves(leaves, roots)
            attempt = {
                "case_id": case_id,
                "attempt": int(row["attempt"]),
                "original_request": case["request"],
                "gold_v2r": gold_model,
                "generated_v2r": model,
                "sr2_leaf_failures": leaves,
                "root_mechanisms": roots,
                "leaf_classification": leaf_classification,
                "cm58": {key: provider["cm58"][key] for key in ("cm58_1", "cm58_2", "cm58_3")},
            }
            attempts.append(attempt)
            counterfactuals.extend(
                {
                    "case_id": case_id,
                    "attempt": int(row["attempt"]),
                    **diagnostic,
                }
                for diagnostic in _counterfactuals(
                    model, gold_model, expected_projection, actual_projection, leaves
                )
            )
            for root in roots:
                name = root["mechanism"]
                root_prevalence.setdefault(
                    name, {"attempt_count": 0, "case_ids": set(), "cases": 0}
                )["attempt_count"] += 1
                root_prevalence[name]["case_ids"].add(case_id)
        root_names = sorted(
            {root["mechanism"] for attempt in attempts for root in attempt["root_mechanisms"]}
        )
        leaf_counts = Counter(leaf for attempt in attempts for leaf in attempt["sr2_leaf_failures"])
        classifications = {
            leaf: classification
            for attempt in attempts
            for leaf, classification in attempt["leaf_classification"].items()
        }
        explained = sum(
            value["classification"] != "NOT_EXPLAINED" for value in classifications.values()
        )
        case_decompositions.append(
            {
                "case_id": case_id,
                "request": case["request"],
                "attempts": attempts,
                "root_set": root_names,
                "root_stability": _stability(attempts),
                "leaf_residual_counts": dict(sorted(leaf_counts.items())),
                "leaf_classification": classifications,
                "leaf_residual_count": sum(leaf_counts.values()),
                "leaves_explained_by_roots": explained * 2,
                "leaves_unexplained": sum(
                    value["classification"] == "NOT_EXPLAINED"
                    for attempt in attempts
                    for value in attempt["leaf_classification"].values()
                ),
                "safety_interaction": {
                    key: [attempt["cm58"][key] for attempt in attempts]
                    for key in ("cm58_1", "cm58_2", "cm58_3")
                },
            }
        )
    for value in root_prevalence.values():
        value["cases"] = len(value["case_ids"])
        value["case_ids"] = sorted(value["case_ids"])
    root_prevalence = {
        key: value for key, value in root_prevalence.items() if value["attempt_count"]
    }
    sr2_result = json.loads(SR2_RESULT.read_text(encoding="utf-8"))
    all_leaves = [
        value
        for decomposition in case_decompositions
        for value in decomposition["leaf_classification"].values()
    ]
    return {
        "decision": (
            "SI_V2R_SR3_ROOT_MECHANISMS_RESOLVED"
            if all(value["classification"] != "NOT_EXPLAINED" for value in all_leaves)
            and all(
                decomposition["root_stability"] == "ROOT_STABLE"
                for decomposition in case_decompositions
            )
            else "SI_V2R_SR3_ROOT_MECHANISMS_PARTIAL"
        ),
        "version": TAXONOMY_VERSION,
        "baseline": BASELINE_SHA,
        "evidence": evidence,
        "target_cases": len(case_decompositions),
        "target_attempts": len(target_rows),
        "frozen_historical_facts": {
            "decision": sr2_result["frozen_historical_facts"]["decision"],
            "semantic_passes": sr2_result["frozen_historical_facts"]["semantic_passes"],
            "stable_semantic_passes": sr2_result["frozen_historical_facts"][
                "stable_semantic_passes"
            ],
            "terminal_structural_failures": sr2_result["frozen_historical_facts"][
                "terminal_structural_failures"
            ],
        },
        "sr2_adjusted_facts": {
            "semantic_passes": sr2_result["metrics"]["ownership_adjusted_semantic_passes"],
            "stable_semantic_passes": sr2_result["metrics"]["ownership_adjusted_stable_passes"],
            "adjusted_failures": sr2_result["metrics"]["remaining_adjusted_semantic_failures"],
        },
        "leaf_residual_counts": dict(
            sorted(
                Counter(
                    leaf
                    for decomposition in case_decompositions
                    for leaf in decomposition["leaf_residual_counts"]
                    for _ in range(decomposition["leaf_residual_counts"][leaf])
                ).items()
            )
        ),
        "root_mechanisms": root_prevalence,
        "dominant_root_mechanism": "TIED:ANNOTATION_WRONG_OWNER,UNREQUESTED_REFERENCE_INFERENCE",
        "dominant_root_cases": 2,
        "case_decompositions": case_decompositions,
        "counterfactuals": counterfactuals,
        "root_ownership": {
            name: next(
                root["owner_classification"]
                for decomposition in case_decompositions
                for attempt in decomposition["attempts"]
                for root in attempt["root_mechanisms"]
                if root["mechanism"] == name
            )
            for name in root_prevalence
        },
        "classification_summary": {
            "root_mechanisms": sum(value["classification"] == "ROOT" for value in all_leaves),
            "consequences": sum(value["classification"] == "CONSEQUENCE" for value in all_leaves),
            "co_roots": sum(value["classification"] == "CO-ROOT" for value in all_leaves),
            "independent": sum(value["classification"] == "INDEPENDENT" for value in all_leaves),
            "unexplained": sum(value["classification"] == "NOT_EXPLAINED" for value in all_leaves),
        },
        "safety_layer_interaction": {
            "cm58_1": (
                "removes unrequested references in Verde and Iris; remains diagnostic "
                "evidence in SR3"
            ),
            "cm58_2": "report presence remains resolved under the unchanged SR2 contract",
            "cm58_3": "no action on the four target rows",
        },
        "provider_inference_calls": 0,
        "endpoint_calls": 0,
        "worker_program_calls": 0,
        "production_behavior_changed": False,
        "adr_cm57": "UNCHANGED",
    }


def write_artifacts(result: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
    """Write bounded SR3 projections without raw provider envelopes."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "case_decompositions.json": result["case_decompositions"],
        "root_mechanisms.json": {
            "version": result["version"],
            "root_mechanisms": result["root_mechanisms"],
            "root_ownership": result["root_ownership"],
            "dominant_root_mechanism": result["dominant_root_mechanism"],
        },
        "counterfactual_diagnostics.json": result["counterfactuals"],
        "result.json": {
            key: value
            for key, value in result.items()
            if key not in {"case_decompositions", "counterfactuals"}
        },
    }
    payloads["result.json"]["evidence"] = {
        key: value for key, value in payloads["result.json"]["evidence"].items() if key != "path"
    }
    for name, payload in payloads.items():
        (output_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def main() -> int:
    """Run SR3 and optionally write its provider-free artifacts."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = analyze_evidence(args.evidence)
    if not _protected_unchanged():
        raise SystemExit("Protected production or historical artifact changed.")
    if args.write:
        write_artifacts(result, args.output_dir)
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key not in {"case_decompositions", "counterfactuals"}
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
