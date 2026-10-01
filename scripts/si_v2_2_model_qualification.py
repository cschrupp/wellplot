"""Provider-facing, provider-neutral Semantic IR v2 qualification harness.

The default command is provider-free. Live execution is available only behind
the explicit authorization flag and is intentionally separate from finalization.
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
from wellplot.agent.code_mode.semantic_ir_v2 import (  # noqa: E402
    SemanticFeatureV2,
    SemanticIRV2,
)
from wellplot.agent.code_mode.semantic_ir_v2_compiler import (  # noqa: E402
    SemanticIRV2CompilationError,
    compile_semantic_ir_v2,
)
from wellplot.agent.code_mode.semantic_ir_v2_registry import (  # noqa: E402
    create_builtin_semantic_lowering_registry,
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

BASELINE_SHA = "d461d756c45c63b9f59d1cdc532d031244dc14af"
EXPERIMENT_VERSION = "SI-V2.2"
FROZEN_MODEL = "qwen3.6-35b-a3b"
PLANNER_TEMPERATURE = 0.0
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
GOLD_PATH = REPO_ROOT / "tests/fixtures/semantic_ir_v2/cm59a_semantic_intents.json"
OUTPUT_PATH = Path("/tmp/si-v2-2-live.jsonl")
ENDPOINT_PRE_PATH = Path("/tmp/si-v2-2-endpoint-pre.json")
ENDPOINT_POST_PATH = Path("/tmp/si-v2-2-endpoint-post.json")
SUMMARY_PATH = Path("/tmp/si-v2-2-summary.json")
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

SEMANTIC_SYSTEM_PROMPT = """You are the WellPlot semantic-intent specialist.

Interpret the user's request and return exactly one object conforming to the
SemanticIRV2 structured schema. Work only at the semantic level.

- Create report intent only when report work is requested.
- Create one semantic section for each logically distinct requested panel or
  section, preserving their order.
- Represent scalar curve meaning with curve features and image, waveform, or
  raster meaning with raster features.
- Set reference=true only when reference or depth presentation is semantically
  requested.
- Represent fills and annotations explicitly and preserve their relationships.
- Preserve source hints, existing-section hints, requirements, and constraints
  when the request provides them.
- Use unresolved_requirements when requested meaning cannot be represented
  safely.
- Never emit capability identifiers, parent relationships, renderer details,
  provider mechanics, filesystem paths, or generated host identifiers.
- Never invent report or section work that the request does not ask for.
- Use semantic identifiers only as local correlation handles.
"""
STRUCTURAL_RETRY_INSTRUCTION = """Return one value that conforms exactly to the
supplied SemanticIRV2 schema. Preserve the semantic interpretation of the
original request. Do not add undeclared fields or prose outside the structured
response. This is a format correction only; do not change the interpretation.
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
FROZEN_CONTROLS = {
    "model": FROZEN_MODEL,
    "temperature": PLANNER_TEMPERATURE,
    "max_output_tokens": MAX_OUTPUT_TOKENS,
    "max_tokens_parameter": MAX_TOKENS_PARAMETER,
    "timeout_seconds": TIMEOUT_SECONDS,
    "concurrency": 1,
    "mode": "reconstruct",
    "current_document_summary": {},
}
PROTECTED_ARTIFACTS = (
    "src/wellplot/agent/code_mode/semantic_ir_v2.py",
    "src/wellplot/agent/code_mode/semantic_ir_v2_compiler.py",
    "src/wellplot/agent/code_mode/semantic_ir_v2_registry.py",
    "src/wellplot/agent/code_mode/capability_safety.py",
    "src/wellplot/agent/code_mode/report_boundary_safety.py",
    "src/wellplot/agent/code_mode/section_leaf_safety.py",
    "src/wellplot/agent/code_mode/planner.py",
    "src/wellplot/agent/providers/base.py",
    "src/wellplot/agent/providers/openai_compat_v2.py",
    "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json",
    "tests/fixtures/semantic_ir_v2/cm59a_semantic_intents.json",
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
    """Read one SI-V2.1-protected artifact from the frozen baseline."""
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
    """Load exactly the frozen 24-case CM-59A request corpus."""
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if payload.get("version") != "cm59a.system-reevaluation.v1":
        raise ValueError("CM-59A request corpus version drifted.")
    if not isinstance(cases, list) or len(cases) != EXPECTED_CASE_COUNT:
        raise ValueError("SI-V2.2 requires exactly 24 request cases.")
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


def _load_gold() -> dict[str, SemanticIRV2]:
    """Load and structurally validate the grader-only semantic fixture."""
    payload = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if payload.get("version") != "si-v2.cm59a.semantic-intents.v1":
        raise ValueError("SI-V2 semantic fixture version drifted.")
    if not isinstance(cases, list) or len(cases) != EXPECTED_CASE_COUNT:
        raise ValueError("SI-V2.2 requires exactly 24 semantic gold cases.")
    result: dict[str, SemanticIRV2] = {}
    for item in cases:
        if not isinstance(item, dict) or not isinstance(item.get("case_id"), str):
            raise ValueError("Semantic gold case is malformed.")
        case_id = str(item["case_id"])
        if case_id in result:
            raise ValueError(f"Duplicate semantic gold case: {case_id!r}.")
        review_fields = {"case_id"}
        model_payload = {key: value for key, value in item.items() if key not in review_fields}
        result[case_id] = SemanticIRV2.model_validate(model_payload)
    return result


def _gold_signature(case: dict[str, object]) -> dict[str, object]:
    """Project the frozen CM-59A capability signature without provider input."""
    return {
        "report": list(case["expected_report_capabilities"]),
        "sections": [list(section) for section in case["expected_sections"]],
    }


def _feature_projection(
    feature: SemanticFeatureV2, curve_positions: dict[str, int]
) -> dict[str, object]:
    """Project one feature's semantic topology without local ID spelling."""
    if feature.kind in {"curve", "raster"}:
        return {"kind": feature.kind, "reference": feature.reference}
    if feature.kind == "fill":
        return {
            "kind": "fill",
            "target_curve_position": curve_positions.get(feature.target_semantic_id),
        }
    if feature.kind == "extension":
        return {"kind": "extension", "semantic_key": feature.semantic_key}
    return {"kind": feature.kind}


def semantic_projection(intent: SemanticIRV2) -> dict[str, object]:
    """Project hard semantic decisions while excluding free-text phrasing."""
    sections: list[dict[str, object]] = []
    for section in intent.sections:
        curve_positions = {
            feature.semantic_id: index
            for index, feature in enumerate(section.features)
            if feature.kind == "curve"
        }
        sections.append(
            {
                "kind": section.kind,
                "features": [
                    _feature_projection(feature, curve_positions) for feature in section.features
                ],
            }
        )
    return {
        "report_present": intent.report is not None,
        "section_count": len(intent.sections),
        "sections": sections,
    }


def context_projection(intent: SemanticIRV2) -> dict[str, object]:
    """Project context-preservation diagnostics separately from hard semantics."""
    return {
        "report_requirements": (
            [_normalize_text(value) for value in intent.report.requirements]
            if intent.report is not None
            else []
        ),
        "sections": [
            {
                "source_hints": [_normalize_text(value) for value in section.source_hints],
                "existing_section_hint": (
                    _normalize_text(section.existing_section_hint)
                    if section.existing_section_hint
                    else None
                ),
                "requirements": [_normalize_text(value) for value in section.requirements],
                "constraints": [_normalize_text(value) for value in section.constraints],
            }
            for section in intent.sections
        ],
        "unresolved_requirements": [
            _normalize_text(value) for value in intent.unresolved_requirements
        ],
    }


def _semantic_differences(actual: object, expected: object, path: str = "$") -> list[str]:
    """Return bounded structural paths that differ between projections."""
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


def _plan_signature(plan: SemanticPlan) -> dict[str, object]:
    """Return the canonical downstream capability signature."""
    return {
        "report": list(plan.report_task.capability_ids) if plan.report_task else [],
        "sections": [list(task.capability_ids) for task in plan.section_tasks],
    }


def _build_gold_plan(case: dict[str, object]) -> SemanticPlan:
    """Build a provider-free expected SemanticPlan signature."""
    from wellplot.agent.code_mode.planner import ReportTask, SectionTask

    return SemanticPlan(
        summary="SI-V2.2 gold plan",
        report_task=(
            ReportTask(
                goal="gold report", capability_ids=tuple(case["expected_report_capabilities"])
            )
            if case["expected_report_capabilities"]
            else None
        ),
        section_tasks=tuple(
            SectionTask(goal="gold section", capability_ids=tuple(section))
            for section in case["expected_sections"]
        ),
    )


def _semantic_prompt_payload(request: str) -> str:
    """Build the only provider user payload, without case IDs or gold data."""
    return canonical_json(
        {
            "request": request,
            "mode": "reconstruct",
            "current_document_summary": {},
        }
    )


def _call_record(
    *, call_index: int, phase: str, outcome: str, reason: str | None = None
) -> dict[str, object]:
    """Create a bounded provider-call trace record."""
    return {
        "call_index": call_index,
        "phase": phase,
        "outcome": outcome,
        "reason": reason,
    }


async def _generate_intent(
    *,
    request: str,
    provider: ModelBackendProtocol,
) -> tuple[SemanticIRV2 | None, list[dict[str, object]], bool, bool, str | None]:
    """Make one initial call and at most one generic structural retry."""
    user_prompt = _semantic_prompt_payload(request)
    traces: list[dict[str, object]] = []
    retry_used = False
    initial_success = False
    final_reason: str | None = None

    async def call(phase: str, system_prompt: str) -> SemanticIRV2 | None:
        nonlocal initial_success, final_reason
        request_model = StructuredGenerationRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_seconds=TIMEOUT_SECONDS,
            temperature=PLANNER_TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        index = len(traces)
        try:
            result = await provider.generate_structured(
                request_model,
                response_model=SemanticIRV2,
            )
            value = SemanticIRV2.model_validate(result.value)
        except StructuredResponseProviderError as error:
            reason = error.diagnostic_metadata().get("response_reason")
            final_reason = reason
            traces.append(
                _call_record(
                    call_index=index,
                    phase=phase,
                    outcome="structured_failure",
                    reason=reason,
                )
            )
            return None
        except ProviderRequestError as error:
            final_reason = error.category.value
            traces.append(
                _call_record(
                    call_index=index,
                    phase=phase,
                    outcome="provider_failure",
                    reason=error.category.value,
                )
            )
            return None
        except ValidationError:
            final_reason = "schema_validation"
            traces.append(
                _call_record(
                    call_index=index,
                    phase=phase,
                    outcome="structured_failure",
                    reason=final_reason,
                )
            )
            return None
        traces.append(_call_record(call_index=index, phase=phase, outcome="structured_success"))
        if phase == "INITIAL":
            initial_success = True
        return value

    value = await call("INITIAL", SEMANTIC_SYSTEM_PROMPT)
    if value is not None:
        return value, traces, retry_used, initial_success, final_reason
    first_trace = traces[0] if traces else {}
    if first_trace.get("outcome") != "structured_failure":
        return None, traces, retry_used, initial_success, final_reason
    retry_used = True
    value = await call(
        "STRUCTURAL_RETRY",
        SEMANTIC_SYSTEM_PROMPT + "\n\n" + STRUCTURAL_RETRY_INSTRUCTION,
    )
    return value, traces, retry_used, initial_success, final_reason


def _layer_record(result: object) -> dict[str, object]:
    """Serialize one successful CM-58 result without its transient plan."""
    return {
        "status": "REPAIRED" if result.changed else "PASSED",
        "changed": result.changed,
        "actions": [action.model_dump(mode="json") for action in result.actions],
        "evidence": result.evidence().model_dump(mode="json"),
    }


def _not_run() -> dict[str, object]:
    """Return a bounded not-run safety record."""
    return {"status": "NOT_RUN", "changed": False, "actions": [], "evidence": None}


async def run_execution(
    *,
    case: dict[str, object],
    gold_intent: SemanticIRV2,
    provider: ModelBackendProtocol,
) -> dict[str, object]:
    """Run one model attempt through L1, L2, L3, and L4 in order."""
    registry = create_builtin_registry()
    lowering_registry = create_builtin_semantic_lowering_registry()
    generated, trace, retry_used, initial_success, final_reason = await _generate_intent(
        request=str(case["request"]),
        provider=provider,
    )
    result: dict[str, object] = {
        "provider_call_count": len(trace),
        "provider_trace": trace,
        "initial_structural_success": initial_success,
        "structural_retry_used": retry_used,
        "semantic_status": "NOT_RUN",
        "semantic_projection": None,
        "expected_semantic_projection": semantic_projection(gold_intent),
        "semantic_differences": [],
        "context_projection": None,
        "expected_context_projection": context_projection(gold_intent),
        "compiler_status": "NOT_RUN",
        "compiler_error_code": None,
        "raw_compiled_signature": None,
        "expected_gold_signature": _gold_signature(case),
        "compiled_signature_match": False,
        "cm58": {"cm58_1": _not_run(), "cm58_2": _not_run(), "cm58_3": _not_run()},
        "cm58_status": "NOT_RUN",
        "cm58_actions": [],
        "final_signature": None,
        "final_system_status": "NOT_RUN",
        "infrastructure_status": None,
        "semantic_model": _safe_model_dump(generated),
    }
    if generated is None:
        reason = final_reason or "structured_failure"
        if reason in INFRASTRUCTURE_CATEGORIES:
            result["infrastructure_status"] = reason
        result["structural_status"] = "STRUCTURAL_FAIL"
        result["structural_failure_reason"] = reason
        return result

    result["structural_status"] = "STRUCTURAL_PASS"
    result["structural_failure_reason"] = None
    actual_projection = semantic_projection(generated)
    expected_projection = semantic_projection(gold_intent)
    result["semantic_projection"] = actual_projection
    result["context_projection"] = context_projection(generated)
    result["semantic_differences"] = _semantic_differences(actual_projection, expected_projection)
    semantic_pass = actual_projection == expected_projection
    result["semantic_status"] = "SEMANTIC_PASS" if semantic_pass else "SEMANTIC_FAIL"

    try:
        compiled = compile_semantic_ir_v2(
            generated,
            registry=registry,
            lowering_registry=lowering_registry,
        )
    except SemanticIRV2CompilationError as error:
        result["compiler_status"] = (
            "COMPILER_INVARIANT_FAILURE" if semantic_pass else "EXPECTED_FAIL_CLOSED"
        )
        result["compiler_error_code"] = error.code.value
        return result

    compiled_signature = _plan_signature(compiled)
    result["compiler_status"] = "COMPILE_SUCCESS"
    result["raw_compiled_signature"] = compiled_signature
    result["compiled_signature_match"] = compiled_signature == _gold_signature(case)

    final_plan = compiled
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
                request=str(case["request"]),
                plan=final_plan,
                registry=registry,
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

    actions = [
        action
        for layer in safety.values()
        if isinstance(layer, dict)
        for action in layer.get("actions", [])
    ]
    result["cm58_actions"] = actions
    if terminal_failure is not None:
        result["cm58_status"] = "SAFE_REJECTION"
        result["final_system_status"] = "SAFE_REJECTION"
        return result

    final_signature = _plan_signature(final_plan)
    result["final_signature"] = final_signature
    final_matches = final_signature == _gold_signature(case)
    changed = any(isinstance(layer, dict) and layer.get("changed") for layer in safety.values())
    result["cm58_status"] = "SAFE_REPAIR" if changed else "NO_ACTION"
    if final_matches and not semantic_pass and changed:
        result["final_system_status"] = "SAFETY_RESCUE"
    elif final_matches:
        result["final_system_status"] = "FINAL_SYSTEM_PASS"
    elif semantic_pass:
        result["final_system_status"] = "SAFETY_REGRESSION"
    else:
        result["final_system_status"] = "WRONG_FINAL_ESCAPE"
    return result


def _provenance() -> dict[str, object]:
    """Return hashes that bind each future row to the reviewed contract."""
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "si_v2_baseline_sha": BASELINE_SHA,
        "harness_sha256": artifact_sha256(Path(__file__)),
        "prompt_sha256": sha256_text(SEMANTIC_SYSTEM_PROMPT),
        "semantic_ir_schema_sha256": sha256_text(canonical_json(SemanticIRV2.model_json_schema())),
        "request_corpus_sha256": artifact_sha256(CASE_PATH),
        "gold_fixture_sha256": artifact_sha256(GOLD_PATH),
        "compiler_sha256": artifact_sha256(
            REPO_ROOT / "src/wellplot/agent/code_mode/semantic_ir_v2_compiler.py"
        ),
        "lowering_registry_sha256": artifact_sha256(
            REPO_ROOT / "src/wellplot/agent/code_mode/semantic_ir_v2_registry.py"
        ),
        "cm58_source_hashes": {
            path: artifact_sha256(REPO_ROOT / path)
            for path in PROTECTED_ARTIFACTS
            if "capability_safety.py" in path
            or "report_boundary_safety.py" in path
            or "section_leaf_safety.py" in path
        },
        "execution_controls": dict(FROZEN_CONTROLS),
        "policy_versions": dict(POLICY_VERSIONS),
        "expected_endpoint_identity_sha256": EXPECTED_ENDPOINT_IDENTITY_SHA256,
    }


def _verify_siv21_unchanged() -> None:
    """Prove SI-V2.1 and production safety artifacts remain byte-identical."""
    for relative_path in PROTECTED_ARTIFACTS:
        path = REPO_ROOT / relative_path
        if path.read_bytes() != _baseline_blob(relative_path):
            raise RuntimeError(f"SI-V2.1 protected artifact drifted: {relative_path}")


def _validate_gold_compilation(cases: tuple[dict[str, object], ...]) -> dict[str, object]:
    """Validate all gold intents and their existing CM-59A signatures provider-free."""
    gold = _load_gold()
    case_ids = {str(case["case_id"]) for case in cases}
    if set(gold) != case_ids:
        raise ValueError("Semantic gold IDs do not match the frozen request corpus.")
    registry = create_builtin_registry()
    lowering = create_builtin_semantic_lowering_registry()
    mismatches: list[str] = []
    for case in cases:
        plan = compile_semantic_ir_v2(
            gold[str(case["case_id"])], registry=registry, lowering_registry=lowering
        )
        if _plan_signature(plan) != _gold_signature(case):
            mismatches.append(str(case["case_id"]))
    if mismatches:
        raise ValueError(f"Gold signature mismatch: {mismatches!r}.")
    return {
        "case_count": len(gold),
        "exact_signature_matches": len(gold),
        "gold_fixture_sha256": artifact_sha256(GOLD_PATH),
    }


def verify_frozen_contract() -> dict[str, object]:
    """Run all provider-free corpus, gold, and immutability checks."""
    _verify_siv21_unchanged()
    cases = _load_requests()
    gold_result = _validate_gold_compilation(cases)
    if any(term in SEMANTIC_SYSTEM_PROMPT for term in FORBIDDEN_PROMPT_TERMS):
        raise ValueError("Semantic prompt leaks capability topology.")
    return {
        "cases": len(cases),
        "families": dict(Counter(str(case["family"]) for case in cases)),
        "gold": gold_result,
        "provenance": _provenance(),
        "provider_calls": 0,
        "endpoint_calls": 0,
    }


def prelive_report() -> dict[str, object]:
    """Return the provider-free SI-V2.2 readiness report."""
    contract = verify_frozen_contract()
    return {
        "status": "PRELIVE_READY",
        "experiment_version": EXPERIMENT_VERSION,
        "baseline_sha": BASELINE_SHA,
        "current_checkout_sha": current_checkout_sha(),
        "live_inference": "NOT_AUTHORIZED",
        "provider_calls": 0,
        "endpoint_calls": 0,
        "worker_program_calls": 0,
        "future_population": {
            "rows": EXPECTED_ROW_COUNT,
            "cases": EXPECTED_CASE_COUNT,
            "attempts_per_case": ATTEMPTS,
            "provider_calls_max": EXPECTED_ROW_COUNT * 2,
        },
        "acceptance": {
            "terminal_structural_failures": 0,
            "stable_semantic_passes_minimum": 22,
            "family_stable_passes_minimum": 3,
            "unstable_cases_maximum": 0,
            "named_anchor_passes": "2/2 each",
            "compiler_invariant_failures": 0,
            "safety_regressions": 0,
            "wrong_final_escapes": 0,
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
        raise RuntimeError("No SI-V2.2 API key configured.")
    return value


def _provider_configuration(args: argparse.Namespace) -> ModelBackendProtocol:
    """Construct the provider only after all live guards and PRE capture."""
    from openai import AsyncOpenAI

    from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2

    return OpenAICompatibleBackendV2(
        model=FROZEN_MODEL,
        client=AsyncOpenAI(
            api_key=_api_key(args),
            base_url=args.base_url,
            timeout=TIMEOUT_SECONDS,
        ),
        structured_output="json_schema",
        max_tokens_parameter=MAX_TOKENS_PARAMETER,
    )


def _ensure_empty(path: Path) -> None:
    """Reject non-empty evidence before endpoint access."""
    if path.exists() and path.stat().st_size:
        raise RuntimeError(f"SI-V2.2 artifact is non-empty: {path}")


def _verify_live_checkout(checkpoint: str) -> None:
    """Require the exact reviewed live checkpoint and frozen sources."""
    if CHECKPOINT_RE.fullmatch(checkpoint) is None or current_checkout_sha() != checkpoint:
        raise RuntimeError("SI-V2.2 checkout does not match authorized checkpoint.")
    verify_frozen_contract()


def _validate_expected_endpoint_fingerprint(
    value: dict[str, object],
    *,
    label: str,
) -> None:
    """Require a valid fingerprint for the frozen endpoint identity."""
    valid, reasons = fingerprint.validate_endpoint_fingerprint_v2(value)
    if not valid:
        reason_text = ", ".join(reasons) or "unknown"
        raise RuntimeError(f"{label} endpoint fingerprint is invalid: {reason_text}")
    if value.get("normalized_identity_sha256") != EXPECTED_ENDPOINT_IDENTITY_SHA256:
        raise RuntimeError(f"{label} endpoint identity does not match the frozen endpoint.")


async def _run_live(args: argparse.Namespace, checkpoint: str) -> None:
    """Run the complete sequential population once."""
    _verify_live_checkout(checkpoint)
    paths = (
        Path(args.evidence_path),
        Path(args.endpoint_fingerprint_pre),
        Path(args.endpoint_fingerprint_post),
        Path(args.summary_path),
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
    pre_sha = sha256_text(pre_text)
    _validate_expected_endpoint_fingerprint(pre, label="PRE")
    provider = _provider_configuration(args)
    with Path(args.evidence_path).open("w", encoding="utf-8") as handle:
        for case in cases:
            for attempt in range(ATTEMPTS):
                result = await run_execution(
                    case=case,
                    gold_intent=gold[str(case["case_id"])],
                    provider=provider,
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
    post = fingerprint.capture_endpoint_fingerprint_v2(
        endpoint=args.base_url,
        model_api_label=FROZEN_MODEL,
        api_key=_api_key(args),
        timeout_seconds=20.0,
    )
    Path(args.endpoint_fingerprint_post).write_text(canonical_json(post) + "\n", encoding="utf-8")


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    """Load complete bounded evidence rows."""
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("SI-V2.2 evidence rows must be objects.")
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
    if len(rows) != EXPECTED_ROW_COUNT:
        reasons.append("row_count")
    expected_ids = [str(case["case_id"]) for case in cases]
    actual_keys = [(str(row.get("case_id")), row.get("attempt")) for row in rows]
    expected_keys = [(case_id, attempt) for case_id in expected_ids for attempt in range(ATTEMPTS)]
    if actual_keys != expected_keys:
        reasons.append("case_order_or_attempt_population")
    expected_provenance = _provenance()
    for row in rows:
        if row.get("authorized_checkpoint") != checkpoint:
            reasons.append("checkpoint_binding")
        if row.get("endpoint_pre_fingerprint_sha256") != sha256_text(canonical_json(pre)):
            reasons.append("pre_fingerprint_binding")
        for key, value in expected_provenance.items():
            if row.get(key) != value:
                reasons.append(f"provenance_{key}")
        if row.get("worker_program_calls") != 0:
            reasons.append("worker_program_calls")
        provider = row.get("provider")
        if not isinstance(provider, dict):
            reasons.append("provider_record")
            continue
        if int(provider.get("provider_call_count", 0)) > 2:
            reasons.append("provider_call_budget")
    if not valid_pre or not valid_post:
        reasons.append("endpoint_fingerprint_invalid")
    return sorted(set(reasons))


def _provider_call_count(rows: list[dict[str, object]]) -> int:
    """Count provider calls represented by readable evidence rows."""
    total = 0
    for row in rows:
        provider = row.get("provider")
        if not isinstance(provider, dict):
            continue
        try:
            total += int(provider.get("provider_call_count", 0))
        except (TypeError, ValueError):
            continue
    return total


def _stable_case_results(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """Aggregate two attempts into stable semantic case outcomes."""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["case_id"])].append(row)
    result: dict[str, dict[str, object]] = {}
    for case_id, case_rows in grouped.items():
        semantic_passes = [
            row["provider"].get("semantic_status") == "SEMANTIC_PASS" for row in case_rows
        ]
        projections = [
            canonical_json(row["provider"].get("semantic_projection")) for row in case_rows
        ]
        structural = all(
            row["provider"].get("structural_status") == "STRUCTURAL_PASS" for row in case_rows
        )
        if len(case_rows) == ATTEMPTS and all(semantic_passes) and len(set(projections)) == 1:
            status = "STABLE_SEMANTIC_PASS"
        elif len(case_rows) == ATTEMPTS and structural and len(set(projections)) == 1:
            status = "STABLE_SEMANTIC_FAIL"
        else:
            status = "UNSTABLE"
        result[case_id] = {"status": status, "rows": len(case_rows)}
    return result


def _decision(summary: dict[str, object]) -> str:
    """Apply the frozen SI-V2.2 terminal decision hierarchy."""
    if summary["integrity_reasons"] or summary["endpoint_drift"]:
        return "SI_V2_2_INCONCLUSIVE_INFRASTRUCTURE"
    if summary["infrastructure_failures"]:
        return "SI_V2_2_INCONCLUSIVE_INFRASTRUCTURE"
    if summary["terminal_structural_failures"]:
        return "SI_V2_PROVIDER_BOUNDARY_REJECTED"
    if (
        summary["compiler_invariant_failures"]
        or summary["semantic_pass_compile_failures"]
        or summary["semantic_pass_signature_mismatches"]
    ):
        return "SI_V2_COMPILER_REJECTED"
    semantic_gate = (
        summary["unstable_cases"] == 0
        and summary["stable_semantic_passes"] >= 22
        and all(value >= 3 for value in summary["family_stable_passes"].values())
        and all(summary["named_anchor_passes"].get(anchor) == 2 for anchor in NAMED_ANCHORS)
    )
    if semantic_gate and (summary["safety_regressions"] or summary["wrong_final_escapes"]):
        return "SI_V2_SAFETY_REJECTED"
    if not semantic_gate:
        return "SI_V2_MODEL_SEMANTIC_REJECTED"
    return "SI_V2_MODEL_QUALIFIED"


def finalize(
    *,
    evidence_path: Path,
    pre_path: Path,
    post_path: Path,
    authorized_checkpoint: str,
) -> dict[str, object]:
    """Finalize evidence without constructing a provider or contacting a network."""
    _verify_live_checkout(authorized_checkpoint)
    cases = _load_requests()
    rows = _load_jsonl(evidence_path)
    pre = _load_fingerprint(pre_path)
    post = _load_fingerprint(post_path)
    reasons = _population_reasons(rows, cases, pre, post, authorized_checkpoint)
    raw_evidence_sha = artifact_sha256(evidence_path)
    if reasons:
        return {
            "experiment_version": EXPERIMENT_VERSION,
            "baseline_sha": BASELINE_SHA,
            "authorized_checkpoint": authorized_checkpoint,
            "rows": len(rows),
            "provider_calls": _provider_call_count(rows),
            "worker_program_calls": 0,
            "integrity_reasons": reasons,
            "endpoint_drift": fingerprint.compare_endpoint_fingerprints_v2(pre, post),
            "infrastructure_failures": 0,
            "decision": "SI_V2_2_INCONCLUSIVE_INFRASTRUCTURE",
            "pre_fingerprint_sha256": sha256_text(canonical_json(pre)),
            "post_fingerprint_sha256": sha256_text(canonical_json(post)),
            "raw_evidence_sha256": raw_evidence_sha,
        }
    stable = _stable_case_results(rows)
    case_map = {str(case["case_id"]): case for case in cases}
    family_passes = Counter()
    named_passes = dict.fromkeys(NAMED_ANCHORS, 0)
    for case_id, value in stable.items():
        if value["status"] == "STABLE_SEMANTIC_PASS":
            family_passes[str(case_map[case_id]["family"])] += 1
            for anchor in NAMED_ANCHORS:
                if anchor in case_id.casefold():
                    named_passes[anchor] += 1
    providers = [row["provider"] for row in rows]
    semantic_pass_rows = [row for row in providers if row.get("semantic_status") == "SEMANTIC_PASS"]
    summary: dict[str, object] = {
        "experiment_version": EXPERIMENT_VERSION,
        "baseline_sha": BASELINE_SHA,
        "authorized_checkpoint": authorized_checkpoint,
        "rows": len(rows),
        "provider_calls": _provider_call_count(rows),
        "worker_program_calls": sum(int(row.get("worker_program_calls", 0)) for row in rows),
        "integrity_reasons": reasons,
        "endpoint_drift": fingerprint.compare_endpoint_fingerprints_v2(pre, post),
        "infrastructure_failures": sum(
            1 for item in providers if item.get("infrastructure_status")
        ),
        "initial_structural_successes": sum(
            bool(item.get("initial_structural_success")) for item in providers
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
        "named_anchor_passes": named_passes,
        "semantic_pass_compile_failures": sum(
            item.get("semantic_status") == "SEMANTIC_PASS"
            and item.get("compiler_status") != "COMPILE_SUCCESS"
            for item in providers
        ),
        "semantic_pass_signature_mismatches": sum(
            item.get("semantic_status") == "SEMANTIC_PASS"
            and not item.get("compiled_signature_match")
            for item in providers
        ),
        "compiler_invariant_failures": sum(
            item.get("compiler_status") == "COMPILER_INVARIANT_FAILURE" for item in providers
        ),
        "compile_successes": sum(
            item.get("compiler_status") == "COMPILE_SUCCESS" for item in providers
        ),
        "expected_fail_closed": sum(
            item.get("compiler_status") == "EXPECTED_FAIL_CLOSED" for item in providers
        ),
        "gold_signature_matches": sum(
            bool(item.get("compiled_signature_match")) for item in providers
        ),
        "no_action": sum(item.get("cm58_status") == "NO_ACTION" for item in providers),
        "safe_repairs": sum(item.get("cm58_status") == "SAFE_REPAIR" for item in providers),
        "safety_rescues": sum(
            item.get("final_system_status") == "SAFETY_RESCUE" for item in providers
        ),
        "safe_rejections": sum(
            item.get("final_system_status") == "SAFE_REJECTION" for item in providers
        ),
        "wrong_final_escapes": sum(
            item.get("final_system_status") == "WRONG_FINAL_ESCAPE" for item in providers
        ),
        "safety_regressions": sum(
            item.get("final_system_status") == "SAFETY_REGRESSION" for item in providers
        ),
        "final_system_passes": sum(
            item.get("final_system_status") in {"FINAL_SYSTEM_PASS", "SAFETY_RESCUE"}
            for item in providers
        ),
        "semantic_pass_rows": len(semantic_pass_rows),
        "pre_fingerprint_sha256": sha256_text(canonical_json(pre)),
        "post_fingerprint_sha256": sha256_text(canonical_json(post)),
        "raw_evidence_sha256": raw_evidence_sha,
    }
    summary["decision"] = _decision(summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    """Build the explicit lifecycle command-line interface."""
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
    report = prelive_report()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
