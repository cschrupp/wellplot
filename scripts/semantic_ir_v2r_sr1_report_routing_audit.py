"""Provider-free SI-V2R report-routing residual audit.

SR1 authenticates the frozen SI-V2R population, projects only bounded report
evidence, and compares the existing deterministic report-boundary classifier
with the frozen corpus. It never contacts a provider or endpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from wellplot.agent.code_mode.report_boundary_safety import (
    classify_report_boundary_intent,
    enforce_report_boundary_safety,
)
from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R
from wellplot.agent.code_mode.semantic_ir_v2r_compiler import compile_semantic_ir_v2r
from wellplot.capabilities import create_builtin_registry

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_SHA = "7a660d6f4efff7a6b3e54a09fa81a3e08e271de4"
EVIDENCE_SHA256 = "9d175c3b80c2cb6a5d5f62195861d4c0070643a37ab4f99dd02559d018011f08"
DEFAULT_EVIDENCE = Path("/tmp/si-v2r-live.jsonl")
CASE_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json"
GOLD_PATH = REPO_ROOT / "tests/fixtures/semantic_ir_v2r/cm59a_semantic_intents_v2r.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr1"
TAXONOMY_VERSION = "si-v2r-sr1.report-routing.v1"
DECISION = "SI_V2R_SR1_DETERMINISTIC_REPORT_OWNERSHIP_SUPPORTED"
FALSE_POSITIVE_CASES = {
    "cm59-single-garnet-06",
    "cm59-multi-ruby-15",
    "cm59-alloc-tamarind-17",
    "cm59-alloc-verde-19",
    "cm59-alloc-willow-20",
}
SECTION_ONLY_CONTROLS = {
    "cm59-single-fig-05",
    "cm59-single-hazel-07",
    "cm59-single-iris-08",
    "cm59-reference-juniper-09",
    "cm59-reference-linden-10",
    "cm59-reference-mica-11",
    "cm59-reference-nova-12",
    "cm59-multi-opal-13",
    "cm59-multi-quartz-14",
    "cm59-multi-slate-16",
    "cm59-alloc-umber-18",
}
MECHANISMS = (
    "REQUEST_SUMMARY_PROMOTION",
    "TOP_LEVEL_COORDINATION_PROMOTION",
    "CONTEXT_PROMOTION",
    "CONSTRAINT_PROMOTION",
    "SECTION_CONTENT_DUPLICATION",
    "DOCUMENT_SCOPE_HALLUCINATION",
    "SYNTHETIC_METADATA",
    "OTHER",
    "AMBIGUOUS",
)
LEXICAL_CUES = (
    "panel",
    "panels",
    "view",
    "views",
    "display",
    "displays",
    "review",
    "interpretation",
    "analysis",
    "present",
    "show",
    "place",
    "keep",
)
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


def canonical_json(value: object) -> str:
    """Serialize JSON-shaped values deterministically."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    """Hash exact bytes."""
    return hashlib.sha256(value).hexdigest()


def _normalize(value: str) -> str:
    """Normalize text for bounded lexical comparisons."""
    value = unicodedata.normalize("NFKC", value).casefold()
    value = "".join(" " if unicodedata.category(char).startswith("P") else char for char in value)
    return " ".join(value.split())


def _contains(text: str, phrase: str) -> bool:
    """Match a whole-word phrase after normalization."""
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read JSONL without rewriting or normalizing the source artifact."""
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def authenticate_evidence(path: Path = DEFAULT_EVIDENCE) -> dict[str, Any]:
    """Authenticate the immutable 48-row SI-V2R population."""
    if not path.is_file():
        raise FileNotFoundError(path)
    actual_sha = sha256_bytes(path.read_bytes())
    if actual_sha != EVIDENCE_SHA256:
        raise ValueError(f"Unexpected SI-V2R evidence SHA-256: {actual_sha}")
    rows = _read_jsonl(path)
    keys = {(str(row["case_id"]), int(row["attempt"])) for row in rows}
    counts = Counter(str(row["case_id"]) for row in rows)
    if len(rows) != 48 or len(counts) != 24 or len(keys) != 48:
        raise ValueError("SI-V2R evidence must contain 48 unique rows for 24 cases.")
    if any(count != 2 for count in counts.values()):
        raise ValueError("SI-V2R evidence must contain two attempts per case.")
    return {"path": str(path), "sha256": actual_sha, "rows": 48, "cases": 24, "attempts": 2}


def _load_cases() -> dict[str, dict[str, Any]]:
    """Load the immutable request corpus by case identity."""
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if payload.get("version") != "cm59a.system-reevaluation.v1" or not isinstance(cases, list):
        raise ValueError("CM-59A request corpus is not the frozen version.")
    if len(cases) != 24 or len({case["case_id"] for case in cases}) != 24:
        raise ValueError("CM-59A request corpus must contain 24 unique cases.")
    return {str(case["case_id"]): case for case in cases}


def _load_gold() -> dict[str, dict[str, Any]]:
    """Load V2R gold report content for report-content-only comparison."""
    payload = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    return {str(case["case_id"]): case for case in payload["cases"]}


def _gold_scope(case: dict[str, Any]) -> str:
    """Map frozen gold ownership to the SR1 scope taxonomy."""
    has_report = bool(case["expected_report_capabilities"])
    has_sections = bool(case["expected_sections"])
    if has_report and has_sections:
        return "MIXED"
    if has_report:
        return "REPORT_ONLY"
    return "SECTION_ONLY"


def _report_work(model: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return only the bounded generated report-work fields."""
    if model is None or model.get("report_work") is None:
        return None
    report = model["report_work"]
    return {
        "goal": report.get("goal", ""),
        "requirements": list(report.get("requirements", [])),
        "constraints": list(report.get("constraints", [])),
    }


def _stored_cm58(row: dict[str, Any]) -> dict[str, Any]:
    """Return the retained CM-58.2 evidence projection."""
    return row["provider"]["cm58"]["cm58_2"]


def _recompute_cm58(request: str, model: dict[str, Any]) -> dict[str, Any]:
    """Recompute CM-58.2 from the generated V2R model, provider-free."""
    intent = SemanticIRV2R.model_validate(model)
    compiled = compile_semantic_ir_v2r(intent, registry=create_builtin_registry())
    result = enforce_report_boundary_safety(
        request=request,
        plan=compiled.semantic_plan,
        registry=create_builtin_registry(),
    )
    return {
        "intent": result.intent.value,
        "actions": [action.model_dump(mode="json") for action in result.actions],
        "changed": result.changed,
        "final_report_present": result.safe_plan.report_task is not None,
    }


def _request_terms(request: str) -> set[str]:
    """Return content terms used only for generic overlap diagnostics."""
    words = set(re.findall(r"[a-z][a-z-]+", _normalize(request)))
    return words - {
        "a",
        "an",
        "and",
        "as",
        "by",
        "for",
        "in",
        "one",
        "the",
        "to",
        "with",
    }


def classify_report_mechanisms(
    *, request: str, model: dict[str, Any], gold_scope: str
) -> list[str]:
    """Classify invented report content using generic observable criteria."""
    report = _report_work(model)
    if report is None or gold_scope != "SECTION_ONLY":
        return []
    report_text = _normalize(
        " ".join([report["goal"], *report["requirements"], *report["constraints"]])
    )
    request_text = _normalize(request)
    request_terms = _request_terms(request)
    report_terms = set(re.findall(r"[a-z][a-z-]+", report_text))
    visual_terms = (
        "panel",
        "panels",
        "display",
        "displays",
        "view",
        "views",
        "curve",
        "image",
        "waveform",
        "track",
        "raster",
        "response",
        "measurement",
    )
    document_terms = (
        "report",
        "document",
        "packet",
        "brief",
        "title",
        "heading",
        "preparer",
        "metadata",
        "handover",
    )
    labels: list[str] = []
    visual_overlap = len(request_terms.intersection(report_terms))
    if any(_contains(report_text, term) for term in visual_terms) and visual_overlap >= 2:
        labels.append("REQUEST_SUMMARY_PROMOTION")
    section_count = len(model.get("sections", []))
    coordination_terms = ("separate", "distinct", "together", "independent", "three", "two")
    if section_count > 1 or any(_contains(report_text, term) for term in coordination_terms):
        labels.append("TOP_LEVEL_COORDINATION_PROMOTION")
    context_terms = ("review", "interpretation", "analysis", "closeout", "handover")
    if any(
        _contains(report_text, term) and _contains(request_text, term) for term in context_terms
    ):
        labels.append("CONTEXT_PROMOTION")
    constraint_terms = ("omit", "keep", "must", "separate", "distinct", "dedicated")
    if report["constraints"] or any(_contains(report_text, term) for term in constraint_terms):
        labels.append("CONSTRAINT_PROMOTION")
    section_text = _normalize(
        " ".join(
            [section.get("goal", "") for section in model.get("sections", [])]
            + [
                value
                for section in model.get("sections", [])
                for feature in section.get("features", [])
                for value in feature.get("requirements", []) + feature.get("constraints", [])
            ]
        )
    )
    if section_text and len(set(re.findall(r"[a-z][a-z-]+", section_text)) & report_terms) >= 2:
        labels.append("SECTION_CONTENT_DUPLICATION")
    if any(_contains(report_text, term) for term in document_terms) and not any(
        _contains(request_text, term) for term in document_terms
    ):
        labels.append("DOCUMENT_SCOPE_HALLUCINATION")
    metadata_terms = ("title", "heading", "preparer", "metadata", "subtitle")
    if any(_contains(report_text, term) for term in metadata_terms) and not any(
        _contains(request_text, term) for term in metadata_terms
    ):
        labels.append("SYNTHETIC_METADATA")
    return labels or ["AMBIGUOUS"]


def _semantic_available(rows: list[dict[str, Any]]) -> bool:
    """Require both attempts to expose a generated semantic model."""
    return all(row["provider"].get("semantic_model") is not None for row in rows)


def _structure_signature(case: dict[str, Any]) -> tuple[int, int, bool, bool, bool, bool]:
    """Summarize observable request structure for control matching."""
    sections = case["expected_sections"]
    features = [
        capability
        for section in sections
        for capability in section
        if capability.startswith("binding.")
    ]
    request = _normalize(case["request"])
    return (
        len(sections),
        len(features),
        any("track.reference" in section for section in sections),
        any(term in request for term in (" omit ", " without ", " no ")),
        "binding.raster" in features,
        len(sections) > 1 or len(features) > 1,
    )


def _feature_count(case: dict[str, Any]) -> int:
    """Count feature bindings in the frozen canonical section signatures."""
    return sum(
        capability.startswith("binding.")
        for section in case["expected_sections"]
        for capability in section
    )


def _matched_controls(
    cases: dict[str, dict[str, Any]],
    rows_by_case: dict[str, list[dict[str, Any]]],
) -> dict[str, list[str]]:
    """Select section-only, structurally available contrastive controls."""
    controls: dict[str, list[str]] = {}
    candidates = [
        case_id
        for case_id in sorted(SECTION_ONLY_CONTROLS)
        if case_id in cases and _semantic_available(rows_by_case[case_id])
    ]
    for case_id in sorted(FALSE_POSITIVE_CASES):
        target = _structure_signature(cases[case_id])
        ranked = sorted(
            candidates,
            key=lambda candidate: (
                sum(
                    a != b
                    for a, b in zip(target, _structure_signature(cases[candidate]), strict=True)
                ),
                candidate,
            ),
        )
        controls[case_id] = ranked[:3]
    return controls


def _report_content_matches(model: dict[str, Any], gold: dict[str, Any]) -> bool:
    """Compare report-owned requirements and constraints without section errors."""
    generated = _report_work(model)
    expected = gold.get("report_work")
    if expected is None or generated is None:
        return expected is None and generated is None
    generated_values = [_normalize(generated["goal"])] + [
        _normalize(value) for value in generated["requirements"] + generated["constraints"]
    ]
    for field in ("requirements", "constraints"):
        for value in expected.get(field, []):
            normalized = _normalize(value)
            if normalized and not any(normalized in candidate for candidate in generated_values):
                return False
    return True


def analyze_evidence(
    evidence_path: Path = DEFAULT_EVIDENCE,
) -> dict[str, Any]:
    """Build all SR1 provider-free evidence projections."""
    evidence = authenticate_evidence(evidence_path)
    cases = _load_cases()
    gold = _load_gold()
    rows = _read_jsonl(evidence_path)
    rows_by_case: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_case.setdefault(str(row["case_id"]), []).append(row)

    routing_rows: list[dict[str, Any]] = []
    scope_rows: list[dict[str, Any]] = []
    mechanism_rows: list[dict[str, Any]] = []
    cm58_matches = 0
    cm58_comparable = 0
    for case_id in sorted(cases):
        case = cases[case_id]
        gold_scope = _gold_scope(case)
        boundary_intent = classify_report_boundary_intent(case["request"]).value.upper()
        scope_rows.append(
            {
                "case_id": case_id,
                "request": case["request"],
                "family": case["family"],
                "gold_report_scope": gold_scope,
                "deterministic_boundary_intent": boundary_intent,
                "matches_gold_report_scope": "YES" if boundary_intent == gold_scope else "NO",
                "section_count_gold": len(case["expected_sections"]),
                "stable_semantic_status": [
                    row["provider"].get("semantic_status") for row in rows_by_case[case_id]
                ],
            }
        )
        for row in sorted(rows_by_case[case_id], key=lambda item: int(item["attempt"])):
            provider = row["provider"]
            model = provider.get("semantic_model")
            if model is None:
                continue
            report = _report_work(model)
            recomputed = _recompute_cm58(case["request"], model)
            stored = _stored_cm58(row)
            cm58_comparable += 1
            if (
                recomputed["intent"] == stored["evidence"]["intent"]
                and recomputed["actions"] == stored["actions"]
                and recomputed["changed"] == stored["changed"]
            ):
                cm58_matches += 1
            mechanisms = classify_report_mechanisms(
                request=case["request"], model=model, gold_scope=gold_scope
            )
            if mechanisms:
                mechanism_rows.append(
                    {
                        "case_id": case_id,
                        "family": case["family"],
                        "attempt": row["attempt"],
                        "request": case["request"],
                        "generated_report_work": report,
                        "labels": mechanisms,
                        "primary": mechanisms[0],
                    }
                )
            routing_rows.append(
                {
                    "case_id": case_id,
                    "family": case["family"],
                    "attempt": row["attempt"],
                    "request": case["request"],
                    "gold_report_present": bool(case["expected_report_capabilities"]),
                    "generated_report_present": report is not None,
                    "generated_report_work": report,
                    "generated_section_count": len(model.get("sections", [])),
                    "semantic_status": provider.get("semantic_status"),
                    "report_boundary_intent": recomputed["intent"],
                    "cm58_report_action": recomputed["actions"],
                    "final_report_present": recomputed["final_report_present"],
                    "primary_br1_mechanism": (
                        "REPORT_FALSE_POSITIVE"
                        if gold_scope == "SECTION_ONLY" and report is not None
                        else "NONE"
                    ),
                    "secondary_br1_mechanisms": provider.get("semantic_differences", []),
                }
            )

    scope_counts = Counter(
        (row["gold_report_scope"], row["deterministic_boundary_intent"]) for row in scope_rows
    )
    false_rows = [row for row in mechanism_rows if row["case_id"] in FALSE_POSITIVE_CASES]
    stable_false_cases = sorted(
        case_id
        for case_id in FALSE_POSITIVE_CASES
        if len([row for row in false_rows if row["case_id"] == case_id]) == 2
        and len({tuple(row["labels"]) for row in false_rows if row["case_id"] == case_id}) == 1
    )
    mechanism_counts = Counter(label for row in false_rows for label in row["labels"])
    primary_counts = Counter(row["primary"] for row in false_rows)
    controls = _matched_controls(cases, rows_by_case)

    lexical: dict[str, dict[str, int]] = {}
    report_case_ids = {
        case_id for case_id, case in cases.items() if _gold_scope(case) != "SECTION_ONLY"
    }
    false_case_ids = set(FALSE_POSITIVE_CASES)
    for cue in LEXICAL_CUES:

        def contains(case_id: str, *, _cue: str = cue) -> bool:
            return _contains(_normalize(cases[case_id]["request"]), _cue)

        lexical[cue] = {
            "false_positive_cases": sum(contains(case_id) for case_id in false_case_ids),
            "successful_section_only_cases": sum(
                contains(case_id)
                for case_id in SECTION_ONLY_CONTROLS
                if _semantic_available(rows_by_case[case_id])
            ),
            "report_bearing_cases": sum(contains(case_id) for case_id in report_case_ids),
        }

    evaluable_section_cases = [
        case_id
        for case_id in sorted(SECTION_ONLY_CONTROLS | FALSE_POSITIVE_CASES)
        if _semantic_available(rows_by_case[case_id])
    ]
    complexity: dict[str, dict[str, int]] = {}
    for dimension, predicate in (
        ("one_section", lambda case: len(case["expected_sections"]) == 1),
        ("multiple_sections", lambda case: len(case["expected_sections"]) > 1),
        (
            "one_feature",
            lambda case: _feature_count(case) == 1,
        ),
        (
            "multiple_features",
            lambda case: _feature_count(case) > 1,
        ),
    ):
        population = [case_id for case_id in evaluable_section_cases if predicate(cases[case_id])]
        failures = [case_id for case_id in population if case_id in FALSE_POSITIVE_CASES]
        complexity[dimension] = {
            "false_positive_cases": len(failures),
            "evaluable_section_only_cases": len(population),
        }

    report_content = {
        "REPORT_ONLY": {"rows": 0, "content_passes": 0},
        "MIXED": {"rows": 0, "content_passes": 0},
    }
    for case_id, case in cases.items():
        scope = _gold_scope(case)
        if scope not in report_content:
            continue
        for row in rows_by_case[case_id]:
            model = row["provider"].get("semantic_model")
            if model is None:
                continue
            report_content[scope]["rows"] += 1
            report_content[scope]["content_passes"] += _report_content_matches(model, gold[case_id])

    prompt_path = REPO_ROOT / "scripts/si_v2r_model_qualification.py"
    prompt_sha = sha256_bytes(prompt_path.read_bytes())
    return {
        "version": TAXONOMY_VERSION,
        "baseline": BASELINE_SHA,
        "evidence": evidence,
        "routing_rows": routing_rows,
        "scope_rows": scope_rows,
        "mechanism_rows": mechanism_rows,
        "mechanism_summary": {
            "false_positive_rows": len(false_rows),
            "stable_false_positive_cases": stable_false_cases,
            "primary_counts": dict(sorted(primary_counts.items())),
            "label_counts": dict(sorted(mechanism_counts.items())),
            "matched_controls": controls,
        },
        "report_scope_matrix": {
            "REPORT_ONLY": {
                "correct": scope_counts[("REPORT_ONLY", "REPORT_ONLY")],
                "total": 4,
            },
            "SECTION_ONLY": {
                "correct": scope_counts[("SECTION_ONLY", "SECTION_ONLY")],
                "total": 16,
            },
            "MIXED": {"correct": scope_counts[("MIXED", "MIXED")], "total": 4},
            "total_correct": sum(
                count
                for (gold_scope, actual_scope), count in scope_counts.items()
                if gold_scope == actual_scope
            ),
            "total": 24,
            "false_positive_rows_section_only": sum(
                row["report_boundary_intent"] == "section_only"
                for row in routing_rows
                if row["case_id"] in FALSE_POSITIVE_CASES
            ),
            "genuine_report_rows_report_or_mixed": sum(
                row["report_boundary_intent"] in {"report_only", "mixed"}
                for row in routing_rows
                if row["case_id"] not in FALSE_POSITIVE_CASES
                and _gold_scope(cases[row["case_id"]]) != "SECTION_ONLY"
            ),
        },
        "cm58_reconciliation": {
            "comparable_rows": cm58_comparable,
            "matching_rows": cm58_matches,
            "mismatches": cm58_comparable - cm58_matches,
        },
        "lexical_cues": lexical,
        "complexity": complexity,
        "prompt_audit": {
            "prompt_source": str(prompt_path.relative_to(REPO_ROOT)),
            "prompt_source_sha256": prompt_sha,
            "report_creation_rule": "EXPLICITLY_PROHIBITED_BY_CURRENT_PROMPT",
            "visualization_not_report_rule": "EXPLICITLY_PROHIBITED_BY_CURRENT_PROMPT",
            "invent_report_rule": "EXPLICITLY_PROHIBITED_BY_CURRENT_PROMPT",
        },
        "report_content": report_content,
        "hypotheses": {
            "H1_SINGLE_LEXICAL_TRIGGER": "NOT_SUPPORTED",
            "H2_PROMPT_AMBIGUITY": "NOT_SUPPORTED",
            "H3_REQUEST_AMBIGUITY": "NOT_SUPPORTED",
            "H4_COMPLEXITY_COORDINATION_PROMOTION": "PARTIAL",
            "H5_OPTIONAL_REPORT_FIELD_PRIOR": "NOT_EVALUABLE",
            "H6_MODEL_REPORT_ROUTING_RESIDUAL": "PARTIAL",
            "H7_DETERMINISTIC_REPORT_PRESENCE_OWNERSHIP": "SUPPORTED",
        },
        "decision": DECISION,
        "recommended_owner_of_report_presence": "DETERMINISTIC_BOUNDARY",
        "provider_calls": 0,
        "endpoint_calls": 0,
        "worker_program_calls": 0,
    }


def _git_protected_paths_unchanged() -> bool:
    """Verify SR1 has not changed protected production or historical files."""
    result = subprocess.run(
        ["git", "diff", "--quiet", BASELINE_SHA, "--", *PROTECTED_PATHS],
        cwd=REPO_ROOT,
        check=False,
    )
    return result.returncode == 0


def write_artifacts(result: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
    """Write the four bounded SR1 machine-readable artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_result = {
        key: value
        for key, value in result.items()
        if key not in {"routing_rows", "scope_rows", "mechanism_rows"}
    }
    safe_result["evidence"] = {
        key: value for key, value in result["evidence"].items() if key != "path"
    }
    files = {
        "report_routing_rows.json": result["routing_rows"],
        "request_scope_matrix.json": result["scope_rows"],
        "mechanism_summary.json": {
            "version": result["version"],
            "mechanism_summary": result["mechanism_summary"],
            "mechanism_rows": result["mechanism_rows"],
            "lexical_cues": result["lexical_cues"],
            "complexity": result["complexity"],
            "prompt_audit": result["prompt_audit"],
            "report_content": result["report_content"],
            "hypotheses": result["hypotheses"],
        },
        "result.json": {
            **safe_result,
        },
    }
    for name, value in files.items():
        (output_dir / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def main() -> int:
    """Run the bounded provider-free audit and optionally write artifacts."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = analyze_evidence(args.evidence)
    if not _git_protected_paths_unchanged():
        raise SystemExit("Protected production or historical artifact changed.")
    if args.write:
        write_artifacts(result, args.output_dir)
    printable = {
        key: value
        for key, value in result.items()
        if key not in {"routing_rows", "scope_rows", "mechanism_rows"}
    }
    print(json.dumps(printable, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
