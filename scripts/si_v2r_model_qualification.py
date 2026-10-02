"""Provider-facing SI-V2R qualification harness.

The default and ``--prelive`` paths are provider-free.  Live execution is
available only behind the explicit ``--live`` lifecycle and a reviewed
checkpoint.  SI-V2R semantics are graded directly; the historical SI-V2.2
runner and grader are not used for generated output.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import cm57p9_runtime_fingerprint as fingerprint  # noqa: E402
from wellplot.agent.code_mode.capability_safety import (  # noqa: E402
    REFERENCE_POLICY_VERSION,
    CapabilitySafetyFailure,
    enforce_capability_safety,
)
from wellplot.agent.code_mode.planner import SemanticPlan  # noqa: E402
from wellplot.agent.code_mode.report_boundary_safety import (  # noqa: E402
    REPORT_BOUNDARY_POLICY_VERSION,
    ReportBoundarySafetyFailure,
    enforce_report_boundary_safety,
)
from wellplot.agent.code_mode.section_leaf_safety import (  # noqa: E402
    SECTION_LEAF_POLICY_VERSION,
    SectionLeafSafetyFailure,
    enforce_section_leaf_safety,
)
from wellplot.agent.code_mode.semantic_ir_v2_registry import (  # noqa: E402
    create_builtin_semantic_lowering_registry,
)
from wellplot.agent.code_mode.semantic_ir_v2r import (  # noqa: E402
    AnnotationSemanticIntentV2R,
    CurveSemanticIntentV2R,
    FillSemanticIntentV2R,
    RasterSemanticIntentV2R,
    SemanticFeatureV2R,
    SemanticIRV2R,
)
from wellplot.agent.code_mode.semantic_ir_v2r_compiler import (  # noqa: E402
    CompiledSemanticPlanV2R,
    SemanticIRV2RCompilationError,
    compile_semantic_ir_v2r,
)
from wellplot.agent.providers.base import (  # noqa: E402
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderRequestError,
    StructuredGenerationRequest,
)
from wellplot.agent.providers.response_diagnostics import (  # noqa: E402
    StructuredResponseProviderError,
)
from wellplot.capabilities import create_builtin_registry  # noqa: E402

BASELINE_SHA = "d896a7e9a634bffe15c6f39ed156dc52c17b2bed"
EXPERIMENT_VERSION = "SI-V2R-LQ0"
FROZEN_MODEL = "qwen3.6-35b-a3b"
TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 16384
MAX_TOKENS_PARAMETER = "max_tokens"
TIMEOUT_SECONDS = 900.0
ATTEMPTS = 2
EXPECTED_CASE_COUNT = 24
EXPECTED_ROW_COUNT = EXPECTED_CASE_COUNT * ATTEMPTS
EXPECTED_ENDPOINT_IDENTITY_SHA256 = (
    "23afb5ebf67063154bcf02ada6d25b2c929250b14c6a4cad06e8649d087bc980"
)
FAMILIES = (
    "REPORT_ONLY",
    "SINGLE_SECTION",
    "REFERENCE_REQUIRED",
    "MULTITRACK_SINGLE_SECTION",
    "MULTI_SECTION_ALLOCATION",
    "MIXED_REPORT_SECTION",
)
NAMED_ANCHORS = ("fig", "linden", "kestrel", "xenon")
CASE_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json"
GOLD_PATH = REPO_ROOT / "tests/fixtures/semantic_ir_v2r/cm59a_semantic_intents_v2r.json"
OUTPUT_PATH = Path("/tmp/si-v2r-live.jsonl")
ENDPOINT_PRE_PATH = Path("/tmp/si-v2r-endpoint-pre.json")
ENDPOINT_POST_PATH = Path("/tmp/si-v2r-endpoint-post.json")
SUMMARY_PATH = Path("/tmp/si-v2r-summary.json")
CHECKPOINT_RE = re.compile(r"^[0-9a-f]{40}$")
INFRASTRUCTURE_CATEGORIES = {
    ProviderFailureCategory.CONFIGURATION.value,
    ProviderFailureCategory.AUTHENTICATION.value,
    ProviderFailureCategory.TIMEOUT.value,
    ProviderFailureCategory.RATE_LIMIT.value,
    ProviderFailureCategory.TRANSPORT.value,
}
POLICY_VERSIONS = {
    "cm58_1": REFERENCE_POLICY_VERSION,
    "cm58_2": REPORT_BOUNDARY_POLICY_VERSION,
    "cm58_3": SECTION_LEAF_POLICY_VERSION,
}

V2R_SYSTEM_PROMPT = """You are the WellPlot semantic-intent specialist.

Interpret the user's request at planner-semantic level and return exactly one
SemanticIRV2R object.

- Create report_work only for requested report, document, packet, or brief work.
- A panel, view, display, log plot, curve, image, waveform, or track does not
  by itself imply report_work.
- Report notes, remarks, dispositions, packet metadata, titles, headings,
  preparer information, and similar document-wide content belong in report_work.
- A section annotation is a visible marker inside the log or panel domain;
  report text is not a section annotation.
- Create one ordered section for each logically distinct requested panel or
  section.
- Represent scalar data as curve features and images, waveforms, and raster-like
  data as raster features.
- For a separate depth lane, depth ruler, depth marker column, or reference
  column beside data, use reference_intent.kind=companion_depth_lane. Do not
  model that companion lane as another feature.
- Use reference_intent.kind=reference_track only when a specific data feature is
  assigned to the reference track; target_semantic_id must identify that feature.
- Use no reference_intent when no reference or depth meaning is requested.
- Represent fills and visible section annotations explicitly.
- Preserve source hints, existing-section hints, requirements, constraints, and
  unresolved requirements when materially present.
- Never emit capability IDs, parent chains, worker track IDs, renderer details,
  filesystem paths, provider mechanics, or report SDK operations.
- Never invent report work, section work, reference semantics, annotations, or
  data features. Use semantic identifiers only as local correlation handles.
"""
STRUCTURAL_RETRY_PROMPT = """Return exactly one object conforming to the
SemanticIRV2R schema. Preserve the interpretation of the original request. Do
not add prose or undeclared fields. This is format/schema correction only; do
not change the semantic interpretation.
"""
FORBIDDEN_PROMPT_TERMS = (
    "report.standard",
    "section.log_plot",
    "track.normal",
    "track.reference",
    "track.array",
    "binding.curve",
    "binding.raster",
    "fill.curve",
    "track.annotation",
    "annotation.typed",
)
PROTECTED_ARTIFACTS = (
    "src/wellplot/agent/code_mode/semantic_ir_v2r.py",
    "src/wellplot/agent/code_mode/semantic_ir_v2r_compiler.py",
    "src/wellplot/agent/code_mode/semantic_ir_v2_registry.py",
    "src/wellplot/agent/code_mode/capability_safety.py",
    "src/wellplot/agent/code_mode/report_boundary_safety.py",
    "src/wellplot/agent/code_mode/section_leaf_safety.py",
    "src/wellplot/agent/code_mode/planner.py",
    "src/wellplot/agent/providers/base.py",
    "src/wellplot/agent/providers/openai_compat_v2.py",
    "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json",
    "tests/fixtures/semantic_ir_v2r/cm59a_semantic_intents_v2r.json",
)


def canonical_json(value: object) -> str:
    """Serialize JSON-shaped evidence deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    """Hash exact UTF-8 text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def artifact_sha256(path: Path) -> str:
    """Hash one repository artifact by exact bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_output(*arguments: str) -> bytes:
    """Return exact output from a repository-local Git command."""
    return subprocess.check_output(["git", *arguments], cwd=REPO_ROOT, stderr=subprocess.STDOUT)


def current_checkout_sha() -> str:
    """Return the current checkout SHA."""
    return _git_output("rev-parse", "HEAD").decode().strip()


def _baseline_blob(relative_path: str) -> bytes:
    """Read one protected artifact from the accepted V2R baseline."""
    return _git_output("show", f"{BASELINE_SHA}:{relative_path}")


def _normalize_text(value: str) -> str:
    """Normalize free text for bounded context diagnostics."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in normalized
    )
    return " ".join(normalized.split())


def _safe_model_dump(value: BaseModel | None) -> dict[str, object] | None:
    """Return a JSON-safe model projection or no value."""
    return value.model_dump(mode="json") if value is not None else None


def _load_requests() -> tuple[dict[str, object], ...]:
    """Load exactly the frozen 24-case request corpus."""
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if payload.get("version") != "cm59a.system-reevaluation.v1":
        raise ValueError("CM-59A request corpus version drifted.")
    if not isinstance(cases, list) or len(cases) != EXPECTED_CASE_COUNT:
        raise ValueError("SI-V2R requires exactly 24 request cases.")
    required = {
        "case_id",
        "family",
        "residual_class",
        "request",
        "expected_report_capabilities",
        "expected_sections",
        "expected_unresolved_count",
    }
    seen: set[str] = set()
    validated: list[dict[str, object]] = []
    for case in cases:
        if not isinstance(case, dict) or set(case) != required:
            raise ValueError("CM-59A request corpus fields drifted.")
        case_id = case["case_id"]
        family = case["family"]
        request = case["request"]
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError("CM-59A case IDs must be unique non-empty strings.")
        if family not in FAMILIES:
            raise ValueError(f"Unknown CM-59A family: {family!r}.")
        if not isinstance(request, str) or not request.strip() or "/" in request:
            raise ValueError(f"Unsafe request text for {case_id!r}.")
        if case["expected_unresolved_count"] != 0:
            raise ValueError("CM-59A requires zero unresolved gold requirements.")
        seen.add(case_id)
        validated.append(case)
    if Counter(str(case["family"]) for case in validated) != Counter(dict.fromkeys(FAMILIES, 4)):
        raise ValueError("CM-59A family distribution drifted.")
    return tuple(validated)


def _load_gold() -> dict[str, SemanticIRV2R]:
    """Load and structurally validate the grader-only V2R gold fixture."""
    payload = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if payload.get("version") != "si-v2r.cm59a.semantic-intents.v1":
        raise ValueError("SI-V2R semantic fixture version drifted.")
    if not isinstance(cases, list) or len(cases) != EXPECTED_CASE_COUNT:
        raise ValueError("SI-V2R requires exactly 24 semantic gold cases.")
    result: dict[str, SemanticIRV2R] = {}
    for item in cases:
        if not isinstance(item, dict) or not isinstance(item.get("case_id"), str):
            raise ValueError("V2R semantic gold case is malformed.")
        case_id = str(item["case_id"])
        if case_id in result:
            raise ValueError(f"Duplicate V2R semantic gold case: {case_id!r}.")
        result[case_id] = SemanticIRV2R.model_validate(
            {key: value for key, value in item.items() if key != "case_id"}
        )
    return result


def _feature_projection(
    feature: SemanticFeatureV2R, positions: dict[str, int]
) -> dict[str, object]:
    """Project one feature while removing arbitrary semantic ID spelling."""
    if isinstance(feature, (CurveSemanticIntentV2R, RasterSemanticIntentV2R)):
        return {"kind": feature.kind}
    if isinstance(feature, FillSemanticIntentV2R):
        return {
            "kind": "fill",
            "target_feature_position": positions.get(feature.target_semantic_id),
        }
    if isinstance(feature, AnnotationSemanticIntentV2R):
        return {"kind": "annotation"}
    return {"kind": feature.kind, "semantic_key": feature.semantic_key}


def semantic_projection(intent: SemanticIRV2R) -> dict[str, object]:
    """Project V2R hard semantic decisions without local ID spelling."""
    sections: list[dict[str, object]] = []
    for section in intent.sections:
        positions = {feature.semantic_id: index for index, feature in enumerate(section.features)}
        reference = None
        if section.reference_intent is not None:
            reference = {"kind": section.reference_intent.kind}
            if section.reference_intent.kind == "reference_track":
                reference["target_feature_position"] = positions.get(
                    section.reference_intent.target_semantic_id
                )
        sections.append(
            {
                "kind": section.kind,
                "features": [
                    _feature_projection(feature, positions) for feature in section.features
                ],
                "reference_intent": reference,
            }
        )
    return {
        "report_work_present": intent.report_work is not None,
        "section_count": len(intent.sections),
        "sections": sections,
    }


def context_projection(intent: SemanticIRV2R) -> dict[str, object]:
    """Project report, section, and feature context separately from semantics."""
    report = None
    if intent.report_work is not None:
        report = {
            "goal": _normalize_text(intent.report_work.goal),
            "requirements": [_normalize_text(value) for value in intent.report_work.requirements],
            "constraints": [_normalize_text(value) for value in intent.report_work.constraints],
        }
    return {
        "report_work": report,
        "sections": [
            {
                "goal": _normalize_text(section.goal),
                "source_hints": [_normalize_text(value) for value in section.source_hints],
                "existing_section_hint": (
                    _normalize_text(section.existing_section_hint)
                    if section.existing_section_hint
                    else None
                ),
                "requirements": [_normalize_text(value) for value in section.requirements],
                "constraints": [_normalize_text(value) for value in section.constraints],
                "feature_context": [
                    {
                        "requirements": [_normalize_text(value) for value in feature.requirements],
                        "constraints": [_normalize_text(value) for value in feature.constraints],
                    }
                    for feature in section.features
                ],
            }
            for section in intent.sections
        ],
        "unresolved_requirements": [
            _normalize_text(value) for value in intent.unresolved_requirements
        ],
    }


def _contains_required_context(required: str, generated_values: list[str]) -> bool:
    """Check a normalized required phrase within one owned semantic scope."""
    return any(required in value for value in generated_values)


def _required_context_preservation(
    generated: SemanticIRV2R, gold: SemanticIRV2R
) -> tuple[bool, list[str]]:
    """Verify non-empty gold context remains in its original semantic owner."""
    misses: list[str] = []
    if gold.report_work is not None:
        if generated.report_work is None:
            if any(_normalize_text(value) for value in gold.report_work.requirements):
                misses.append("report_work.requirements")
            if any(_normalize_text(value) for value in gold.report_work.constraints):
                misses.append("report_work.constraints")
        else:
            generated_report = [
                _normalize_text(generated.report_work.goal),
                *(_normalize_text(value) for value in generated.report_work.requirements),
                *(_normalize_text(value) for value in generated.report_work.constraints),
            ]
            for field_name, values in (
                ("requirements", gold.report_work.requirements),
                ("constraints", gold.report_work.constraints),
            ):
                for index, value in enumerate(values):
                    normalized = _normalize_text(value)
                    if normalized and not _contains_required_context(normalized, generated_report):
                        misses.append(f"report_work.{field_name}[{index}]")

    for section_index, gold_section in enumerate(gold.sections):
        if section_index >= len(generated.sections):
            misses.append(f"sections[{section_index}]")
            continue
        generated_section = generated.sections[section_index]
        generated_section_values = [
            _normalize_text(generated_section.goal),
            *(_normalize_text(value) for value in generated_section.requirements),
            *(_normalize_text(value) for value in generated_section.constraints),
        ]
        for field_name, values in (
            ("requirements", gold_section.requirements),
            ("constraints", gold_section.constraints),
        ):
            for index, value in enumerate(values):
                normalized = _normalize_text(value)
                if normalized and not _contains_required_context(
                    normalized, generated_section_values
                ):
                    misses.append(f"sections[{section_index}].{field_name}[{index}]")
        for feature_index, gold_feature in enumerate(gold_section.features):
            if feature_index >= len(generated_section.features):
                misses.append(f"sections[{section_index}].features[{feature_index}]")
                continue
            generated_feature = generated_section.features[feature_index]
            generated_feature_values = [
                _normalize_text(value) for value in generated_feature.requirements
            ] + [_normalize_text(value) for value in generated_feature.constraints]
            for field_name, values in (
                ("requirements", gold_feature.requirements),
                ("constraints", gold_feature.constraints),
            ):
                for index, value in enumerate(values):
                    normalized = _normalize_text(value)
                    if normalized and not _contains_required_context(
                        normalized, generated_feature_values
                    ):
                        misses.append(
                            f"sections[{section_index}].features[{feature_index}]"
                            f".{field_name}[{index}]"
                        )
    return not misses, misses[:32]


def _reference_projection(intent: SemanticIRV2R) -> list[dict[str, object] | None]:
    """Return one section-aligned reference projection."""
    result: list[dict[str, object] | None] = []
    for section in intent.sections:
        reference = section.reference_intent
        if reference is None:
            result.append(None)
            continue
        projected: dict[str, object] = {"kind": reference.kind}
        if reference.kind == "reference_track":
            positions = {
                feature.semantic_id: index for index, feature in enumerate(section.features)
            }
            projected["target_feature_position"] = positions.get(reference.target_semantic_id)
        result.append(projected)
    return result


def _plan_signature(plan: SemanticPlan) -> dict[str, object]:
    """Return the exact downstream capability signature."""
    return {
        "report": list(plan.report_task.capability_ids) if plan.report_task else [],
        "sections": [list(task.capability_ids) for task in plan.section_tasks],
    }


def _type_signature(plan: SemanticPlan) -> dict[str, object] | None:
    """Return capability types, or ``None`` when duplicates make it invalid."""
    report_ids = list(plan.report_task.capability_ids) if plan.report_task else []
    section_ids = [list(task.capability_ids) for task in plan.section_tasks]
    if len(report_ids) != len(set(report_ids)) or any(
        len(ids) != len(set(ids)) for ids in section_ids
    ):
        return None
    return {
        "report": sorted(report_ids),
        "sections": [sorted(ids) for ids in section_ids],
    }


def _gold_signature(case: dict[str, object]) -> dict[str, object]:
    """Project the frozen CM-59A capability signature."""
    return {
        "report": list(case["expected_report_capabilities"]),
        "sections": [list(section) for section in case["expected_sections"]],
    }


def _gold_type_signature(case: dict[str, object]) -> dict[str, object] | None:
    """Project the frozen CM-59A type-equivalent signature."""
    report = list(case["expected_report_capabilities"])
    sections = [list(section) for section in case["expected_sections"]]
    if len(report) != len(set(report)) or any(len(ids) != len(set(ids)) for ids in sections):
        return None
    return {"report": sorted(report), "sections": [sorted(ids) for ids in sections]}


def _capability_type_equivalent(plan: SemanticPlan, expected: dict[str, object] | None) -> bool:
    """Compare capability types without erasing duplicate-capability errors."""
    actual = _type_signature(plan)
    return expected is not None and actual is not None and actual == expected


def _semantic_differences(actual: object, expected: object, path: str = "$") -> list[str]:
    """Return bounded projection paths that differ."""
    if type(actual) is not type(expected):
        return [path]
    if isinstance(actual, dict):
        differences: list[str] = []
        for key in sorted(set(actual) | set(expected)):
            if key not in actual or key not in expected:
                differences.append(f"{path}.{key}")
            else:
                differences.extend(
                    _semantic_differences(actual[key], expected[key], f"{path}.{key}")
                )
        return differences[:32]
    if isinstance(actual, list):
        differences = []
        for index in range(max(len(actual), len(expected))):
            if index >= len(actual) or index >= len(expected):
                differences.append(f"{path}[{index}]")
            else:
                differences.extend(
                    _semantic_differences(actual[index], expected[index], f"{path}[{index}]")
                )
        return differences[:32]
    return [] if actual == expected else [path]


def _semantic_prompt_payload(request: str) -> str:
    """Build the only provider user payload without case or gold data."""
    return canonical_json(
        {"request": request, "mode": "reconstruct", "current_document_summary": {}}
    )


def _call_record(
    index: int, phase: str, outcome: str, reason: str | None = None
) -> dict[str, object]:
    """Create a bounded provider-call trace record."""
    return {"call_index": index, "phase": phase, "outcome": outcome, "reason": reason}


async def _generate_intent(
    *, request: str, provider: ModelBackendProtocol
) -> tuple[SemanticIRV2R | None, list[dict[str, object]], bool, bool, str | None]:
    """Make one initial call and at most one generic structural retry."""
    traces: list[dict[str, object]] = []
    retry_used = False
    initial_success = False
    final_reason: str | None = None
    user_prompt = _semantic_prompt_payload(request)

    async def call(phase: str, system_prompt: str) -> SemanticIRV2R | None:
        nonlocal initial_success, final_reason
        request_model = StructuredGenerationRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_seconds=TIMEOUT_SECONDS,
            temperature=TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        try:
            result = await provider.generate_structured(
                request_model,
                response_model=SemanticIRV2R,
            )
            value = SemanticIRV2R.model_validate(result.value)
        except StructuredResponseProviderError as error:
            final_reason = str(
                error.diagnostic_metadata().get("response_reason") or "structured_failure"
            )
            traces.append(_call_record(len(traces), phase, "structured_failure", final_reason))
            return None
        except ProviderRequestError as error:
            final_reason = error.category.value
            traces.append(_call_record(len(traces), phase, "provider_failure", final_reason))
            return None
        except ValidationError:
            final_reason = "schema_validation"
            traces.append(_call_record(len(traces), phase, "structured_failure", final_reason))
            return None
        traces.append(_call_record(len(traces), phase, "structured_success"))
        if phase == "INITIAL":
            initial_success = True
        return value

    value = await call("INITIAL", V2R_SYSTEM_PROMPT)
    if value is not None:
        return value, traces, retry_used, initial_success, final_reason
    if not traces or traces[0].get("outcome") != "structured_failure":
        return None, traces, retry_used, initial_success, final_reason
    retry_used = True
    value = await call("STRUCTURAL_RETRY", V2R_SYSTEM_PROMPT + "\n\n" + STRUCTURAL_RETRY_PROMPT)
    return value, traces, retry_used, initial_success, final_reason


def _not_run() -> dict[str, object]:
    """Return a bounded not-run safety record."""
    return {"status": "NOT_RUN", "changed": False, "actions": [], "evidence": None}


def _layer_record(result: object) -> dict[str, object]:
    """Serialize one successful CM58 result without its transient plan."""
    return {
        "status": "SAFE_REPAIR" if result.changed else "NO_ACTION",
        "changed": result.changed,
        "actions": [action.model_dump(mode="json") for action in result.actions],
        "evidence": result.evidence().model_dump(mode="json"),
    }


async def run_execution(
    *, case: dict[str, object], gold_intent: SemanticIRV2R, provider: ModelBackendProtocol
) -> dict[str, object]:
    """Run one result through direct V2R grading, lowering, and CM58."""
    registry = create_builtin_registry()
    lowering_registry = create_builtin_semantic_lowering_registry()
    generated, trace, retry_used, initial_success, final_reason = await _generate_intent(
        request=str(case["request"]), provider=provider
    )
    expected_projection = semantic_projection(gold_intent)
    result: dict[str, object] = {
        "provider_call_count": len(trace),
        "provider_trace": trace,
        "initial_structural_success": initial_success,
        "structural_retry_used": retry_used,
        "structural_status": "STRUCTURAL_FAIL",
        "structural_failure_reason": final_reason,
        "semantic_status": "NOT_RUN",
        "semantic_projection": None,
        "expected_semantic_projection": expected_projection,
        "semantic_topology_match": False,
        "required_context_preserved": False,
        "required_context_misses": [],
        "semantic_differences": [],
        "context_projection": None,
        "expected_context_projection": context_projection(gold_intent),
        "compiler_status": "NOT_RUN",
        "compiler_error_code": None,
        "compiled_reference_projection": None,
        "expected_reference_projection": _reference_projection(gold_intent),
        "reference_preservation_status": "NOT_RUN",
        "raw_compiled_signature": None,
        "expected_gold_signature": _gold_signature(case),
        "exact_compiled_signature_match": False,
        "capability_type_compiled_match": False,
        "cm58": {"cm58_1": _not_run(), "cm58_2": _not_run(), "cm58_3": _not_run()},
        "cm58_status": "NOT_RUN",
        "cm58_actions": [],
        "final_signature": None,
        "exact_final_signature_match": False,
        "capability_type_final_match": False,
        "reference_metadata_consistency": None,
        "final_capability_status": "NOT_RUN",
        "final_v2r_system_status": "NOT_RUN",
        "infrastructure_status": None,
        "semantic_model": _safe_model_dump(generated),
    }
    if generated is None:
        if final_reason in INFRASTRUCTURE_CATEGORIES:
            result["infrastructure_status"] = final_reason
        return result

    result["structural_status"] = "STRUCTURAL_PASS"
    result["structural_failure_reason"] = None
    actual_projection = semantic_projection(generated)
    result["semantic_projection"] = actual_projection
    result["context_projection"] = context_projection(generated)
    result["semantic_differences"] = _semantic_differences(actual_projection, expected_projection)
    topology_match = actual_projection == expected_projection
    required_context_preserved, required_context_misses = _required_context_preservation(
        generated, gold_intent
    )
    result["semantic_topology_match"] = topology_match
    result["required_context_preserved"] = required_context_preserved
    result["required_context_misses"] = required_context_misses
    semantic_pass = topology_match and required_context_preserved
    result["semantic_status"] = "SEMANTIC_PASS" if semantic_pass else "SEMANTIC_FAIL"

    try:
        compiled = compile_semantic_ir_v2r(
            generated, registry=registry, lowering_registry=lowering_registry
        )
    except SemanticIRV2RCompilationError as error:
        result["compiler_status"] = (
            "COMPILER_INVARIANT_FAILURE" if semantic_pass else "EXPECTED_FAIL_CLOSED"
        )
        result["compiler_error_code"] = error.code.value
        return result

    if not isinstance(compiled, CompiledSemanticPlanV2R):
        result["compiler_status"] = "COMPILER_INVARIANT_FAILURE"
        result["compiler_error_code"] = "compiled_result_type"
        return result
    generated_reference = _reference_projection(generated)
    compiled_reference = [
        None if value is None else value.model_dump(mode="json")
        for value in compiled.reference_intents
    ]
    # Convert target IDs in the preserved wrapper to feature positions for comparison.
    compiled_reference = _reference_projection_from_compiled(generated, compiled)
    reference_preserved = compiled_reference == generated_reference
    result["compiled_reference_projection"] = compiled_reference
    result["reference_preservation_status"] = "PASS" if reference_preserved else "FAIL"
    result["compiler_status"] = (
        "COMPILE_SUCCESS" if reference_preserved else "COMPILER_SEMANTIC_PRESERVATION_FAILURE"
    )
    result["raw_compiled_signature"] = _plan_signature(compiled.semantic_plan)
    result["exact_compiled_signature_match"] = result["raw_compiled_signature"] == _gold_signature(
        case
    )
    result["capability_type_compiled_match"] = _capability_type_equivalent(
        compiled.semantic_plan, _gold_type_signature(case)
    )
    if not reference_preserved:
        return result

    final_plan = compiled.semantic_plan
    safety = result["cm58"]
    terminal_failure: str | None = None
    for key, function, failure_type in (
        ("cm58_1", enforce_capability_safety, CapabilitySafetyFailure),
        ("cm58_2", enforce_report_boundary_safety, ReportBoundarySafetyFailure),
        ("cm58_3", enforce_section_leaf_safety, SectionLeafSafetyFailure),
    ):
        if terminal_failure is not None:
            break
        try:
            layer_result = function(
                request=str(case["request"]), plan=final_plan, registry=registry
            )
        except failure_type as error:
            safety[key] = {
                "status": "FAILED",
                "changed": False,
                "actions": [],
                "evidence": None,
                "failure_code": error.code,
            }
            terminal_failure = error.code
        else:
            safety[key] = _layer_record(layer_result)
            final_plan = layer_result.safe_plan

    result["cm58_actions"] = [
        action
        for layer in safety.values()
        if isinstance(layer, dict)
        for action in layer["actions"]
    ]
    if terminal_failure is not None:
        result["cm58_status"] = "SAFE_REJECTION"
        result["final_v2r_system_status"] = "SAFE_REJECTION"
        return result

    result["final_signature"] = _plan_signature(final_plan)
    result["exact_final_signature_match"] = result["final_signature"] == _gold_signature(case)
    result["capability_type_final_match"] = _capability_type_equivalent(
        final_plan, _gold_type_signature(case)
    )
    result["final_capability_status"] = (
        "FINAL_CAPABILITY_PASS"
        if result["capability_type_final_match"]
        else "FINAL_CAPABILITY_FAIL"
    )
    result["reference_metadata_consistency"] = _reference_metadata_consistent(compiled, final_plan)
    changed = any(isinstance(layer, dict) and layer.get("changed") for layer in safety.values())
    result["cm58_status"] = "SAFE_REPAIR" if changed else "NO_ACTION"
    if result["reference_metadata_consistency"] is False:
        result["final_v2r_system_status"] = "REFERENCE_METADATA_CONFLICT"
    elif result["capability_type_final_match"] and not changed:
        result["final_v2r_system_status"] = "FINAL_V2R_SYSTEM_PASS"
    elif result["capability_type_final_match"] and changed:
        result["final_v2r_system_status"] = (
            "SAFETY_RESCUE" if not semantic_pass else "FINAL_V2R_SYSTEM_PASS"
        )
    elif semantic_pass:
        result["final_v2r_system_status"] = "SAFETY_REGRESSION"
    else:
        result["final_v2r_system_status"] = "WRONG_FINAL_ESCAPE"
    return result


def _reference_projection_from_compiled(
    generated: SemanticIRV2R, compiled: CompiledSemanticPlanV2R
) -> list[dict[str, object] | None]:
    """Project preserved wrapper metadata using generated feature positions."""
    result: list[dict[str, object] | None] = []
    for section, reference in zip(generated.sections, compiled.reference_intents, strict=True):
        if reference is None:
            result.append(None)
            continue
        value: dict[str, object] = {"kind": reference.kind}
        if reference.kind == "reference_track":
            positions = {
                feature.semantic_id: index for index, feature in enumerate(section.features)
            }
            value["target_feature_position"] = positions.get(reference.target_semantic_id)
        result.append(value)
    return result


def _reference_metadata_consistent(
    compiled: CompiledSemanticPlanV2R, final_plan: SemanticPlan
) -> bool:
    """Detect CM58 outcomes that contradict preserved V2R reference meaning."""
    for reference, task in zip(compiled.reference_intents, final_plan.section_tasks, strict=True):
        has_reference_capability = "track.reference" in task.capability_ids
        if reference is None and has_reference_capability:
            return False
        if reference is not None and not has_reference_capability:
            return False
    return True


def _provenance() -> dict[str, object]:
    """Return hashes binding future rows to the reviewed contract."""
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "accepted_baseline_sha": BASELINE_SHA,
        "harness_sha256": artifact_sha256(Path(__file__)),
        "prompt_sha256": sha256_text(V2R_SYSTEM_PROMPT),
        "structural_retry_prompt_sha256": sha256_text(STRUCTURAL_RETRY_PROMPT),
        "semantic_ir_v2r_schema_sha256": sha256_text(
            canonical_json(SemanticIRV2R.model_json_schema())
        ),
        "request_corpus_sha256": artifact_sha256(CASE_PATH),
        "gold_fixture_sha256": artifact_sha256(GOLD_PATH),
        "semantic_ir_v2r_sha256": artifact_sha256(
            REPO_ROOT / "src/wellplot/agent/code_mode/semantic_ir_v2r.py"
        ),
        "compiler_sha256": artifact_sha256(
            REPO_ROOT / "src/wellplot/agent/code_mode/semantic_ir_v2r_compiler.py"
        ),
        "lowering_registry_sha256": artifact_sha256(
            REPO_ROOT / "src/wellplot/agent/code_mode/semantic_ir_v2_registry.py"
        ),
        "cm58_source_hashes": {
            path: artifact_sha256(REPO_ROOT / path)
            for path in PROTECTED_ARTIFACTS
            if path.endswith(
                ("capability_safety.py", "report_boundary_safety.py", "section_leaf_safety.py")
            )
        },
        "execution_controls": {
            "model": FROZEN_MODEL,
            "temperature": TEMPERATURE,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_tokens_parameter": MAX_TOKENS_PARAMETER,
            "timeout_seconds": TIMEOUT_SECONDS,
            "concurrency": 1,
            "mode": "reconstruct",
            "current_document_summary": {},
        },
        "policy_versions": dict(POLICY_VERSIONS),
        "expected_endpoint_identity_sha256": EXPECTED_ENDPOINT_IDENTITY_SHA256,
    }


def _verify_protected_artifacts() -> None:
    """Prove production and accepted V2R core artifacts are unchanged."""
    for relative_path in PROTECTED_ARTIFACTS:
        path = REPO_ROOT / relative_path
        if path.read_bytes() != _baseline_blob(relative_path):
            raise RuntimeError(f"Protected artifact drifted: {relative_path}")


def _validate_gold_compilation(cases: tuple[dict[str, object], ...]) -> dict[str, object]:
    """Validate all V2R gold intents, lowering, and reference preservation."""
    gold = _load_gold()
    case_ids = {str(case["case_id"]) for case in cases}
    if set(gold) != case_ids:
        raise ValueError("V2R gold IDs do not match the frozen request corpus.")
    registry = create_builtin_registry()
    lowering = create_builtin_semantic_lowering_registry()
    topology_mismatches: list[str] = []
    reference_mismatches: list[str] = []
    for case in cases:
        case_id = str(case["case_id"])
        compiled = compile_semantic_ir_v2r(
            gold[case_id], registry=registry, lowering_registry=lowering
        )
        if not _capability_type_equivalent(compiled.semantic_plan, _gold_type_signature(case)):
            topology_mismatches.append(case_id)
        if _reference_projection_from_compiled(gold[case_id], compiled) != _reference_projection(
            gold[case_id]
        ):
            reference_mismatches.append(case_id)
    if topology_mismatches or reference_mismatches:
        raise ValueError(
            f"V2R gold validation failed: topology={topology_mismatches!r}, "
            f"reference={reference_mismatches!r}."
        )
    return {
        "case_count": len(gold),
        "compiled": len(gold),
        "capability_type_matches": len(gold),
        "reference_preservation": len(gold),
        "gold_fixture_sha256": artifact_sha256(GOLD_PATH),
    }


def verify_frozen_contract() -> dict[str, object]:
    """Run all local corpus, gold, schema, leakage, and immutability checks."""
    _verify_protected_artifacts()
    cases = _load_requests()
    gold_result = _validate_gold_compilation(cases)
    schema = SemanticIRV2R.model_json_schema()
    if not schema:
        raise ValueError("SemanticIRV2R schema is empty.")
    prompt_text = V2R_SYSTEM_PROMPT + STRUCTURAL_RETRY_PROMPT
    if any(term in prompt_text for term in FORBIDDEN_PROMPT_TERMS):
        raise ValueError("V2R prompt leaks capability topology.")
    if any(str(case["case_id"]) in prompt_text for case in cases):
        raise ValueError("V2R prompt leaks a qualification case ID.")
    for case in cases:
        for capability_id in case["expected_report_capabilities"]:
            if capability_id in prompt_text:
                raise ValueError("V2R prompt leaks expected capability data.")
        for section in case["expected_sections"]:
            for capability_id in section:
                if capability_id in prompt_text:
                    raise ValueError("V2R prompt leaks expected capability data.")
    return {
        "cases": len(cases),
        "families": dict(Counter(str(case["family"]) for case in cases)),
        "gold": gold_result,
        "provenance": _provenance(),
        "provider_calls": 0,
        "endpoint_calls": 0,
        "worker_program_calls": 0,
    }


def prelive_report() -> dict[str, object]:
    """Return the provider-free LQ0 readiness report."""
    contract = verify_frozen_contract()
    return {
        "status": "PRELIVE_READY",
        "experiment_version": EXPERIMENT_VERSION,
        "baseline_sha": BASELINE_SHA,
        "current_checkout_sha": current_checkout_sha(),
        "live_inference": "NOT_STARTED",
        "provider_calls": 0,
        "endpoint_calls": 0,
        "worker_program_calls": 0,
        "future_population": {
            "rows": EXPECTED_ROW_COUNT,
            "cases": EXPECTED_CASE_COUNT,
            "attempts_per_case": ATTEMPTS,
            "provider_calls_max": EXPECTED_ROW_COUNT * 2,
            "semantic_retry_calls": 0,
        },
        "acceptance": {
            "terminal_structural_failures": 0,
            "stable_semantic_passes_minimum": 22,
            "reference_family_stable_passes": "4/4",
            "compiler_invariant_failures": 0,
            "safety_regressions": 0,
            "wrong_final_escapes": 0,
            "reference_metadata_conflicts": 0,
        },
        **contract,
    }


def _api_key(args: argparse.Namespace) -> str:
    """Resolve the API key without retaining or serializing it."""
    value = os.getenv(args.api_key_env, "").strip()
    if not value and args.api_key_file:
        path = Path(args.api_key_file)
        if not path.is_absolute():
            path = REPO_ROOT / path
        value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError("No SI-V2R API key configured.")
    return value


def _provider_configuration(args: argparse.Namespace) -> ModelBackendProtocol:
    """Construct the provider only after PRE identity validation."""
    from openai import AsyncOpenAI

    from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2

    return OpenAICompatibleBackendV2(
        model=FROZEN_MODEL,
        client=AsyncOpenAI(api_key=_api_key(args), base_url=args.base_url, timeout=TIMEOUT_SECONDS),
        structured_output="json_schema",
        max_tokens_parameter=MAX_TOKENS_PARAMETER,
    )


def _ensure_empty(path: Path) -> None:
    """Reject non-empty live artifacts before endpoint access."""
    if path.exists() and path.stat().st_size:
        raise RuntimeError(f"SI-V2R artifact is non-empty: {path}")


def _verify_live_checkout(checkpoint: str) -> None:
    """Require the exact reviewed live checkpoint and frozen contract."""
    if CHECKPOINT_RE.fullmatch(checkpoint) is None or current_checkout_sha() != checkpoint:
        raise RuntimeError("SI-V2R checkout does not match the authorized checkpoint.")
    verify_frozen_contract()


def _validate_expected_endpoint_fingerprint(value: dict[str, object], *, label: str) -> None:
    """Require a valid fingerprint for the frozen endpoint identity."""
    valid, reasons = fingerprint.validate_endpoint_fingerprint_v2(value)
    if not valid:
        raise RuntimeError(f"{label} endpoint fingerprint is invalid: {', '.join(reasons)}")
    if value.get("normalized_identity_sha256") != EXPECTED_ENDPOINT_IDENTITY_SHA256:
        raise RuntimeError(f"{label} endpoint identity does not match the frozen endpoint.")


async def _run_live(args: argparse.Namespace, checkpoint: str) -> None:
    """Run the complete sequential population exactly once."""
    _verify_live_checkout(checkpoint)
    paths = tuple(
        Path(value)
        for value in (
            args.evidence_path,
            args.endpoint_fingerprint_pre,
            args.endpoint_fingerprint_post,
            args.summary_path,
        )
    )
    for path in paths:
        _ensure_empty(path)
    cases = _load_requests()
    gold = _load_gold()
    pre = fingerprint.capture_endpoint_fingerprint_v2(
        endpoint=args.base_url,
        model_api_label=FROZEN_MODEL,
        api_key=_api_key(args),
        timeout_seconds=20.0,
    )
    pre_text = canonical_json(pre)
    Path(args.endpoint_fingerprint_pre).write_text(pre_text + "\n", encoding="utf-8")
    _validate_expected_endpoint_fingerprint(pre, label="PRE")
    pre_sha = sha256_text(pre_text)
    try:
        provider = _provider_configuration(args)
        with Path(args.evidence_path).open("w", encoding="utf-8") as handle:
            for case in cases:
                for attempt in range(ATTEMPTS):
                    result = await run_execution(
                        case=case, gold_intent=gold[str(case["case_id"])], provider=provider
                    )
                    row = {
                        **_provenance(),
                        "authorized_checkpoint": checkpoint,
                        "endpoint_pre_identity": pre.get("normalized_identity_sha256"),
                        "endpoint_pre_fingerprint_sha256": pre_sha,
                        "case_id": case["case_id"],
                        "family": case["family"],
                        "attempt": attempt,
                        "request_sha256": sha256_text(str(case["request"])),
                        "provider": result,
                        "worker_program_calls": 0,
                    }
                    handle.write(canonical_json(row) + "\n")
                    handle.flush()
                    if result.get("infrastructure_status") is not None:
                        return
    finally:
        post = fingerprint.capture_endpoint_fingerprint_v2(
            endpoint=args.base_url,
            model_api_label=FROZEN_MODEL,
            api_key=_api_key(args),
            timeout_seconds=20.0,
        )
        Path(args.endpoint_fingerprint_post).write_text(
            canonical_json(post) + "\n", encoding="utf-8"
        )


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    """Load bounded evidence rows."""
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("SI-V2R evidence rows must be objects.")
        rows.append(value)
    return rows


def _load_fingerprint(path: Path) -> dict[str, object]:
    """Load one endpoint fingerprint without network access."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Endpoint fingerprint must be an object.")
    return value


def _population_reasons(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    pre: dict[str, object],
    post: dict[str, object],
    checkpoint: str,
) -> list[str]:
    """Return fail-closed integrity reasons for finalization."""
    reasons: list[str] = []
    valid_pre, pre_reasons = fingerprint.validate_endpoint_fingerprint_v2(pre)
    valid_post, post_reasons = fingerprint.validate_endpoint_fingerprint_v2(post)
    reasons.extend(f"pre_{reason}" for reason in pre_reasons)
    reasons.extend(f"post_{reason}" for reason in post_reasons)
    reasons.extend(fingerprint.compare_endpoint_fingerprints_v2(pre, post))
    if pre.get("normalized_identity_sha256") != EXPECTED_ENDPOINT_IDENTITY_SHA256:
        reasons.append("pre_expected_endpoint_identity")
    if post.get("normalized_identity_sha256") != EXPECTED_ENDPOINT_IDENTITY_SHA256:
        reasons.append("post_expected_endpoint_identity")
    expected_keys = [
        (str(case["case_id"]), attempt) for case in cases for attempt in range(ATTEMPTS)
    ]
    actual_keys = [(str(row.get("case_id")), row.get("attempt")) for row in rows]
    infrastructure_terminal = any(
        isinstance(row.get("provider"), dict)
        and row["provider"].get("infrastructure_status") is not None
        for row in rows
    )
    if infrastructure_terminal:
        if actual_keys != expected_keys[: len(actual_keys)]:
            reasons.append("partial_case_order_or_attempt_population")
    elif len(rows) != EXPECTED_ROW_COUNT or actual_keys != expected_keys:
        reasons.append("case_order_or_attempt_population")
    expected_provenance = _provenance()
    pre_sha = sha256_text(canonical_json(pre))
    for row in rows:
        if row.get("authorized_checkpoint") != checkpoint:
            reasons.append("checkpoint_binding")
        if row.get("endpoint_pre_fingerprint_sha256") != pre_sha:
            reasons.append("pre_fingerprint_binding")
        for key, value in expected_provenance.items():
            if row.get(key) != value:
                reasons.append(f"provenance_{key}")
        if row.get("worker_program_calls") != 0:
            reasons.append("worker_program_calls")
        provider = row.get("provider")
        if not isinstance(provider, dict) or int(provider.get("provider_call_count", 0)) > 2:
            reasons.append("provider_call_budget")
    if not valid_pre or not valid_post:
        reasons.append("endpoint_fingerprint_invalid")
    return sorted(set(reasons))


def _provider_call_count(rows: list[dict[str, object]]) -> int:
    """Count provider calls represented by evidence rows."""
    return sum(
        int(row["provider"].get("provider_call_count", 0))
        for row in rows
        if isinstance(row.get("provider"), dict)
    )


def _stable_case_results(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """Aggregate two attempts into stable V2R semantic outcomes."""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["case_id"])].append(row)
    results: dict[str, dict[str, object]] = {}
    for case_id, case_rows in grouped.items():
        projections = [
            canonical_json(row["provider"].get("semantic_projection")) for row in case_rows
        ]
        structural = all(
            row["provider"].get("structural_status") == "STRUCTURAL_PASS" for row in case_rows
        )
        semantic_pass = all(
            row["provider"].get("semantic_status") == "SEMANTIC_PASS" for row in case_rows
        )
        if (
            len(case_rows) == ATTEMPTS
            and structural
            and semantic_pass
            and len(set(projections)) == 1
        ):
            status = "STABLE_SEMANTIC_PASS"
        elif len(case_rows) == ATTEMPTS and structural and len(set(projections)) == 1:
            status = "STABLE_SEMANTIC_FAIL"
        else:
            status = "UNSTABLE"
        results[case_id] = {"status": status, "rows": len(case_rows)}
    return results


def _decision(summary: dict[str, object]) -> str:
    """Apply the frozen LQ0 terminal decision precedence."""
    if (
        summary["integrity_reasons"]
        or summary["endpoint_drift"]
        or summary["infrastructure_failures"]
    ):
        return "SI_V2R_LIVE_INCONCLUSIVE_INFRASTRUCTURE"
    if summary["terminal_structural_failures"]:
        return "SI_V2R_PROVIDER_BOUNDARY_REJECTED"
    if (
        summary["compiler_invariant_failures"]
        or summary["compiler_reference_preservation_failures"]
        or summary["semantic_pass_compiler_failures"]
        or summary["semantic_pass_type_mismatches"]
    ):
        return "SI_V2R_COMPILER_REJECTED"
    semantic_gate = (
        summary["unstable_cases"] == 0
        and summary["stable_semantic_passes"] >= 22
        and all(value >= 3 for value in summary["family_stable_passes"].values())
        and summary["reference_family_stable_passes"] == 4
        and all(
            summary["named_anchor_attempt_passes"].get(anchor) == ATTEMPTS
            for anchor in NAMED_ANCHORS
        )
    )
    if not semantic_gate:
        return "SI_V2R_MODEL_SEMANTIC_REJECTED"
    if (
        summary["safety_regressions"]
        or summary["wrong_final_escapes"]
        or summary["reference_metadata_conflicts"]
    ):
        return "SI_V2R_SAFETY_REJECTED"
    return "SI_V2R_MODEL_QUALIFIED"


def finalize(
    *, evidence_path: Path, pre_path: Path, post_path: Path, authorized_checkpoint: str
) -> dict[str, object]:
    """Finalize preserved evidence without provider or endpoint activity."""
    _verify_live_checkout(authorized_checkpoint)
    cases = _load_requests()
    rows = _load_jsonl(evidence_path)
    pre = _load_fingerprint(pre_path)
    post = _load_fingerprint(post_path)
    reasons = _population_reasons(rows, cases, pre, post, authorized_checkpoint)
    infrastructure_failures = sum(
        isinstance(row.get("provider"), dict)
        and row["provider"].get("infrastructure_status") is not None
        for row in rows
    )
    base = {
        "experiment_version": EXPERIMENT_VERSION,
        "baseline_sha": BASELINE_SHA,
        "authorized_checkpoint": authorized_checkpoint,
        "rows": len(rows),
        "rows_completed": len(rows),
        "provider_calls": _provider_call_count(rows),
        "worker_program_calls": 0,
        "integrity_reasons": reasons,
        "endpoint_drift": fingerprint.compare_endpoint_fingerprints_v2(pre, post),
        "pre_fingerprint_sha256": sha256_text(canonical_json(pre)),
        "post_fingerprint_sha256": sha256_text(canonical_json(post)),
        "raw_evidence_sha256": artifact_sha256(evidence_path),
    }
    if reasons:
        return {
            **base,
            "infrastructure_failures": infrastructure_failures,
            "decision": "SI_V2R_LIVE_INCONCLUSIVE_INFRASTRUCTURE",
        }

    providers = [row["provider"] for row in rows]
    stable = _stable_case_results(rows)
    case_map = {str(case["case_id"]): case for case in cases}
    family_passes = Counter()
    named_passes = dict.fromkeys(NAMED_ANCHORS, 0)
    named_anchor_attempt_passes = dict.fromkeys(NAMED_ANCHORS, 0)
    for case_id, value in stable.items():
        if value["status"] == "STABLE_SEMANTIC_PASS":
            family_passes[str(case_map[case_id]["family"])] += 1
            for anchor in NAMED_ANCHORS:
                if anchor in case_id.casefold():
                    named_passes[anchor] += 1
    for row in rows:
        provider = row["provider"]
        if (
            provider.get("structural_status") == "STRUCTURAL_PASS"
            and provider.get("semantic_status") == "SEMANTIC_PASS"
        ):
            case_id = str(row["case_id"])
            for anchor in NAMED_ANCHORS:
                if anchor in case_id.casefold():
                    named_anchor_attempt_passes[anchor] += 1
    summary: dict[str, object] = {
        **base,
        "infrastructure_failures": infrastructure_failures,
        "initial_structural_successes": sum(
            bool(item.get("initial_structural_success")) for item in providers
        ),
        "initial_structural_failures": sum(
            not bool(item.get("initial_structural_success")) for item in providers
        ),
        "final_structural_successes": sum(
            item.get("structural_status") == "STRUCTURAL_PASS" for item in providers
        ),
        "structural_retries": sum(bool(item.get("structural_retry_used")) for item in providers),
        "retry_recoveries": sum(
            bool(item.get("structural_retry_used"))
            and item.get("structural_status") == "STRUCTURAL_PASS"
            for item in providers
        ),
        "terminal_structural_failures": sum(
            item.get("structural_status") != "STRUCTURAL_PASS"
            and not item.get("infrastructure_status")
            for item in providers
        ),
        "semantic_passes": sum(
            item.get("semantic_status") == "SEMANTIC_PASS" for item in providers
        ),
        "semantic_failures": sum(
            item.get("semantic_status") == "SEMANTIC_FAIL" for item in providers
        ),
        "stable_case_results": stable,
        "stable_semantic_passes": sum(
            value["status"] == "STABLE_SEMANTIC_PASS" for value in stable.values()
        ),
        "stable_semantic_failures": sum(
            value["status"] == "STABLE_SEMANTIC_FAIL" for value in stable.values()
        ),
        "unstable_cases": sum(value["status"] == "UNSTABLE" for value in stable.values()),
        "family_stable_passes": {family: family_passes[family] for family in FAMILIES},
        "reference_family_stable_passes": sum(
            value["status"] == "STABLE_SEMANTIC_PASS"
            for case_id, value in stable.items()
            if case_map[case_id]["family"] == "REFERENCE_REQUIRED"
        ),
        "named_anchor_passes": named_passes,
        "named_anchor_attempt_passes": named_anchor_attempt_passes,
        "compiler_invariant_failures": sum(
            item.get("compiler_status") == "COMPILER_INVARIANT_FAILURE" for item in providers
        ),
        "compiler_reference_preservation_failures": sum(
            item.get("compiler_status") == "COMPILER_SEMANTIC_PRESERVATION_FAILURE"
            for item in providers
        ),
        "semantic_pass_compiler_failures": sum(
            item.get("semantic_status") == "SEMANTIC_PASS"
            and item.get("compiler_status") != "COMPILE_SUCCESS"
            for item in providers
        ),
        "semantic_pass_type_mismatches": sum(
            item.get("semantic_status") == "SEMANTIC_PASS"
            and not item.get("capability_type_compiled_match")
            for item in providers
        ),
        "compile_successes": sum(
            item.get("compiler_status") == "COMPILE_SUCCESS" for item in providers
        ),
        "cm58_safe_repairs": sum(item.get("cm58_status") == "SAFE_REPAIR" for item in providers),
        "safety_rescues": sum(
            item.get("final_v2r_system_status") == "SAFETY_RESCUE" for item in providers
        ),
        "safe_rejections": sum(
            item.get("final_v2r_system_status") == "SAFE_REJECTION" for item in providers
        ),
        "wrong_final_escapes": sum(
            item.get("final_v2r_system_status") == "WRONG_FINAL_ESCAPE" for item in providers
        ),
        "safety_regressions": sum(
            item.get("final_v2r_system_status") == "SAFETY_REGRESSION" for item in providers
        ),
        "reference_metadata_conflicts": sum(
            item.get("reference_metadata_consistency") is False for item in providers
        ),
        "final_capability_passes": sum(
            item.get("final_capability_status") == "FINAL_CAPABILITY_PASS" for item in providers
        ),
        "final_v2r_system_passes": sum(
            item.get("final_v2r_system_status") == "FINAL_V2R_SYSTEM_PASS" for item in providers
        ),
        "historical_si_v2_2": {
            "stable_semantic_passes": "8/24",
            "exact_order_final": "28/48",
            "capability_type_equivalent_final": "34/48",
        },
    }
    summary["decision"] = _decision(summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    """Build the explicit provider-free/live/finalize lifecycle CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    lifecycle = parser.add_mutually_exclusive_group()
    lifecycle.add_argument("--prelive", action="store_true")
    lifecycle.add_argument("--live", action="store_true")
    lifecycle.add_argument("--finalize", action="store_true")
    parser.add_argument("--authorized-checkpoint")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-env", default="LLAMA_CPP_API_KEY")
    parser.add_argument("--api-key-file", default="LLAMA_CPP_API_KEY.txt")
    parser.add_argument("--evidence-path", default=str(OUTPUT_PATH))
    parser.add_argument("--endpoint-fingerprint-pre", default=str(ENDPOINT_PRE_PATH))
    parser.add_argument("--endpoint-fingerprint-post", default=str(ENDPOINT_POST_PATH))
    parser.add_argument("--summary-path", default=str(SUMMARY_PATH))
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one explicit provider-free or authorized lifecycle stage."""
    args = _parser().parse_args(argv)
    if args.live:
        if not args.authorized_checkpoint or not args.base_url:
            raise SystemExit("--live requires --authorized-checkpoint and --base-url")
        asyncio.run(_run_live(args, args.authorized_checkpoint))
        return 0
    if args.finalize:
        if not args.authorized_checkpoint:
            raise SystemExit("--finalize requires --authorized-checkpoint")
        summary = finalize(
            evidence_path=Path(args.evidence_path),
            pre_path=Path(args.endpoint_fingerprint_pre),
            post_path=Path(args.endpoint_fingerprint_post),
            authorized_checkpoint=args.authorized_checkpoint,
        )
        Path(args.summary_path).write_text(canonical_json(summary) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    if args.authorized_checkpoint or args.base_url:
        raise SystemExit("Live arguments require --live or --finalize")
    print(json.dumps(prelive_report(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
