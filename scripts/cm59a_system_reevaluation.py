"""CM-59A provider-free system reevaluation gate.

The default command validates the fresh corpus and future live contract only.
Live inference is deliberately withheld behind explicit authorization flags.
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
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import cm57p5_fresh_holdout as p5  # noqa: E402
from scripts import cm57p6_report_invariant_bisect as p6  # noqa: E402
from scripts import cm57p9_runtime_fingerprint as fingerprint  # noqa: E402
from wellplot.agent.code_mode.capability_safety import (  # noqa: E402
    REFERENCE_POLICY_VERSION,
    CapabilitySafetyFailure,
    CapabilitySafetyResult,
    enforce_capability_safety,
)
from wellplot.agent.code_mode.planner import (  # noqa: E402
    _PLANNER_SYSTEM_PROMPT,
    PlannerSemanticFailure,
    SemanticPlan,
    SemanticPlanner,
)
from wellplot.agent.code_mode.report_boundary_safety import (  # noqa: E402
    REPORT_BOUNDARY_POLICY_VERSION,
    ReportBoundarySafetyFailure,
    ReportBoundarySafetyResult,
    enforce_report_boundary_safety,
)
from wellplot.agent.code_mode.section_leaf_safety import (  # noqa: E402
    SECTION_LEAF_POLICY_VERSION,
    SectionLeafSafetyFailure,
    SectionLeafSafetyResult,
    enforce_section_leaf_safety,
)
from wellplot.agent.providers.base import (  # noqa: E402
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry  # noqa: E402

BASELINE_SHA = "d8a49996125b48a7fd1c8385059ddaae97978069"
CASE_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json"
OUTPUT_PATH = Path("/tmp/cm59a-system-reevaluation-qwen.jsonl")
ENDPOINT_PRE_PATH = Path("/tmp/cm59a-endpoint-pre.json")
ENDPOINT_POST_PATH = Path("/tmp/cm59a-endpoint-post.json")
SUMMARY_PATH = Path("/tmp/cm59a-system-reevaluation-summary.json")
EXPERIMENT_VERSION = "CM-59A"
CORPUS_VERSION = "cm59a.system-reevaluation.v1"
FROZEN_MODEL = "qwen3.6-35b-a3b"
PLANNER_TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 16384
MAX_TOKENS_PARAMETER = "max_tokens"
TIMEOUT_SECONDS = 900.0
ATTEMPTS = 2
FAMILIES = (
    "REPORT_ONLY",
    "SINGLE_SECTION",
    "REFERENCE_REQUIRED",
    "MULTITRACK_SINGLE_SECTION",
    "MULTI_SECTION_ALLOCATION",
    "MIXED_REPORT_SECTION",
)
RESIDUAL_CLASSES = {None, "LICHEN_CLASS", "MARINER_CLASS"}
INFRASTRUCTURE_CATEGORIES = {
    ProviderFailureCategory.CONFIGURATION.value,
    ProviderFailureCategory.AUTHENTICATION.value,
    ProviderFailureCategory.TIMEOUT.value,
    ProviderFailureCategory.RATE_LIMIT.value,
    ProviderFailureCategory.TRANSPORT.value,
}
CHECKPOINT_RE = re.compile(r"^[0-9a-f]{40}$")
PATH_RE = re.compile(r"(?<!\w)(?:[A-Za-z]:[\\/]|/)[^\s,;]+")
CAPABILITY_IDS = (
    "report.standard",
    "section.log_plot",
    "track.normal",
    "track.reference",
    "track.array",
    "binding.curve",
    "binding.raster",
    "track.annotation",
    "annotation.typed",
)
FORBIDDEN_REQUEST_TERMS = (
    "SemanticPlan",
    "ReportTask",
    "SectionTask",
    "capability_ids",
    "expected_sections",
    "expected_report_capabilities",
)
FROZEN_EXECUTION_CONTROLS = {
    "model": FROZEN_MODEL,
    "planner_temperature": PLANNER_TEMPERATURE,
    "max_output_tokens": MAX_OUTPUT_TOKENS,
    "max_tokens_parameter": MAX_TOKENS_PARAMETER,
    "timeout_seconds": TIMEOUT_SECONDS,
    "concurrency": 1,
    "mode": "reconstruct",
}
POLICY_VERSIONS = {
    "capability_safety": REFERENCE_POLICY_VERSION,
    "report_boundary_safety": REPORT_BOUNDARY_POLICY_VERSION,
    "section_leaf_safety": SECTION_LEAF_POLICY_VERSION,
}
SAFETY_LAYER_KEYS = ("cm58_1", "cm58_2", "cm58_3")
PRODUCTION_ARTIFACTS = (
    "src/wellplot/agent/code_mode/planner.py",
    "src/wellplot/agent/code_mode/capability_safety.py",
    "src/wellplot/agent/code_mode/report_boundary_safety.py",
    "src/wellplot/agent/code_mode/section_leaf_safety.py",
    "src/wellplot/agent/code_mode/workflow.py",
    "src/wellplot/capabilities/builtins.py",
    "src/wellplot/agent/providers/base.py",
    "src/wellplot/agent/providers/openai_compat_v2.py",
    "scripts/cm57p9_runtime_fingerprint.py",
)


def canonical_json(value: object) -> str:
    """Serialize JSON-shaped values deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    """Hash exact UTF-8 text bytes."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def artifact_sha256(path: Path) -> str:
    """Hash one repository artifact."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_output(*arguments: str) -> bytes:
    """Return exact output from a repository-local Git command."""
    return subprocess.check_output(["git", *arguments], cwd=REPO_ROOT, stderr=subprocess.STDOUT)


def current_checkout_sha() -> str:
    """Return the current checkout SHA."""
    return _git_output("rev-parse", "HEAD").decode().strip()


def _baseline_blob(relative_path: str) -> bytes:
    """Read one protected production artifact from the accepted baseline."""
    return _git_output("show", f"{BASELINE_SHA}:{relative_path}")


def _normalized_request(request: str) -> str:
    """Normalize request text for cross-corpus freshness checks."""
    normalized = unicodedata.normalize("NFKC", request).casefold()
    normalized = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in normalized
    )
    return " ".join(normalized.split())


def _previous_corpus_entries() -> tuple[dict[str, object], ...]:
    """Load earlier decision-bearing requests without invoking providers."""
    paths = (
        REPO_ROOT / "tests/fixtures/typed_worker/cm57p5_fresh_holdout.json",
        REPO_ROOT / "tests/fixtures/typed_worker/cm57p7_fresh_promotion.json",
        REPO_ROOT / "tests/fixtures/typed_worker/cm57p10_final_promotion_cases.json",
    )
    entries: list[dict[str, object]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries.extend(payload["cases"])
    return tuple(entries)


def _schema_sha256() -> str:
    """Hash the production SemanticPlan response schema canonically."""
    return p6.schema_sha256(SemanticPlan)


def _source_summary() -> dict[str, object]:
    """Return the established bounded production source summary."""
    return p5.FIXED_SOURCE_SUMMARY


def _source_summary_sha256() -> str:
    """Hash the established source summary."""
    return sha256_text(canonical_json(_source_summary()))


def _production_source_hashes() -> dict[str, str]:
    """Return exact hashes for production artifacts protected by the gate."""
    return {path: artifact_sha256(REPO_ROOT / path) for path in PRODUCTION_ARTIFACTS}


def _verify_production_matches_baseline() -> None:
    """Prove CM-59A preparation did not alter production source bytes."""
    for relative_path in PRODUCTION_ARTIFACTS:
        if (REPO_ROOT / relative_path).read_bytes() != _baseline_blob(relative_path):
            raise RuntimeError(f"CM-59A production artifact drifted: {relative_path}")


def load_case_definitions(
    path: Path = CASE_PATH,
) -> tuple[dict[str, object], ...]:
    """Load and validate the immutable 24-case CM-59A corpus."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != CORPUS_VERSION:
        raise ValueError("Unexpected CM-59A corpus version.")
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 24:
        raise ValueError("CM-59A requires exactly 24 cases.")
    registry = create_builtin_registry()
    previous = _previous_corpus_entries()
    previous_ids = {str(case["case_id"]) for case in previous}
    previous_hashes = {sha256_text(str(case["request"])) for case in previous}
    previous_normalized = {_normalized_request(str(case["request"])) for case in previous}
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    seen_normalized: set[str] = set()
    family_counts: Counter[str] = Counter()
    residual_counts: Counter[str | None] = Counter()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("CM-59A cases must be objects.")
        expected_keys = {
            "case_id",
            "family",
            "residual_class",
            "request",
            "expected_report_capabilities",
            "expected_sections",
            "expected_unresolved_count",
        }
        if set(case) != expected_keys:
            raise ValueError("CM-59A case fields drifted.")
        case_id = case["case_id"]
        family = case["family"]
        residual_class = case["residual_class"]
        request = case["request"]
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError("CM-59A case IDs must be unique non-empty strings.")
        if case_id in previous_ids:
            raise ValueError(f"CM-59A case ID is not fresh: {case_id!r}.")
        if family not in FAMILIES:
            raise ValueError(f"Unknown CM-59A family: {family!r}.")
        if residual_class not in RESIDUAL_CLASSES:
            raise ValueError(f"Invalid CM-59A residual class: {residual_class!r}.")
        if not isinstance(request, str) or not request.strip() or PATH_RE.search(request):
            raise ValueError(f"Case {case_id!r} has unsafe request text.")
        lowered = request.casefold()
        if any(term.casefold() in lowered for term in FORBIDDEN_REQUEST_TERMS):
            raise ValueError(f"Case {case_id!r} leaks planner vocabulary.")
        if any(capability.casefold() in lowered for capability in CAPABILITY_IDS):
            raise ValueError(f"Case {case_id!r} leaks capability IDs.")
        request_hash = sha256_text(request)
        normalized = _normalized_request(request)
        if request_hash in seen_hashes or request_hash in previous_hashes:
            raise ValueError(f"Case {case_id!r} reuses a historical request hash.")
        if normalized in seen_normalized or normalized in previous_normalized:
            raise ValueError(f"Case {case_id!r} reuses normalized request text.")
        report = case["expected_report_capabilities"]
        sections = case["expected_sections"]
        if not isinstance(report, list) or not all(isinstance(value, str) for value in report):
            raise ValueError(f"Case {case_id!r} has invalid report gold.")
        if not isinstance(sections, list) or not all(isinstance(value, list) for value in sections):
            raise ValueError(f"Case {case_id!r} has invalid section gold.")
        if case["expected_unresolved_count"] != 0:
            raise ValueError("CM-59A requires zero unresolved requirements.")
        p5._validate_report_gold(report, registry, case_id)
        for section in sections:
            p5._validate_section_gold(section, registry, case_id)
        seen_ids.add(case_id)
        seen_hashes.add(request_hash)
        seen_normalized.add(normalized)
        family_counts[str(family)] += 1
        residual_counts[residual_class] += 1
    if family_counts != Counter(dict.fromkeys(FAMILIES, 4)):
        raise ValueError(f"CM-59A family distribution is invalid: {family_counts!r}.")
    if residual_counts["LICHEN_CLASS"] != 2 or residual_counts["MARINER_CLASS"] != 2:
        raise ValueError(f"CM-59A residual distribution is invalid: {residual_counts!r}.")
    if residual_counts[None] != 20:
        raise ValueError("CM-59A requires exactly 20 non-residual cases.")
    return tuple(cases)


def frozen_provenance() -> dict[str, object]:
    """Return exact provenance values bound to every future evidence row."""
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "design_baseline_sha": BASELINE_SHA,
        "harness_sha256": artifact_sha256(Path(__file__)),
        "corpus_sha256": artifact_sha256(CASE_PATH),
        "production_source_hashes": _production_source_hashes(),
        "P_prompt_sha256": sha256_text(_PLANNER_SYSTEM_PROMPT),
        "response_schema_sha256": _schema_sha256(),
        "source_summary_sha256": _source_summary_sha256(),
        "policy_versions": dict(POLICY_VERSIONS),
        "execution_controls": dict(FROZEN_EXECUTION_CONTROLS),
    }


def _plan_projection(plan: SemanticPlan | None) -> dict[str, object] | None:
    """Project a plan without retaining provider-generated prose."""
    return p5._plan_projection(plan) if plan is not None else None


def _facts(
    plan: SemanticPlan | None,
    case: dict[str, object],
    registry: CapabilityRegistry,
) -> dict[str, object] | None:
    """Score one transient plan through the established P-series evaluator."""
    return p5._facts(plan, case, registry) if plan is not None else None


@dataclass
class RecordingBackend(ModelBackendProtocol):
    """Capture bounded planner-call facts without retaining provider responses."""

    delegate: ModelBackendProtocol
    calls: list[dict[str, object]]
    plans: list[tuple[str, SemanticPlan]]
    program_calls: int = 0

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Record call classification and safe plan shape."""
        if not self.calls:
            call_kind = "INITIAL"
        elif "Correction context:" in request.user_prompt:
            call_kind = "SEMANTIC_CORRECTION"
        else:
            call_kind = "INVALID_RESPONSE_RETRY"
        record: dict[str, object] = {"call_kind": call_kind}
        try:
            result = await self.delegate.generate_structured(request, response_model=response_model)
        except ProviderRequestError as error:
            record.update(
                {
                    "outcome": "provider_failure",
                    "provider_category": error.category.value,
                }
            )
            self.calls.append(record)
            raise
        except ValidationError:
            record["outcome"] = "structured_output_failure"
            self.calls.append(record)
            raise
        record["outcome"] = "structured_success"
        if isinstance(result.value, SemanticPlan):
            self.plans.append((call_kind, result.value))
            record["plan"] = _plan_projection(result.value)
        record["metrics"] = result.metrics.public_metadata()
        self.calls.append(record)
        return result

    async def generate_program(self, request: object) -> object:
        """Reject accidental worker/program execution."""
        self.program_calls += 1
        raise AssertionError(f"CM-59A must not call program generation: {request!r}")


def _infra_failure(category: str | None) -> bool:
    """Return whether one provider category invalidates the population."""
    return category in INFRASTRUCTURE_CATEGORIES


def _layer_evidence(
    result: CapabilitySafetyResult | ReportBoundarySafetyResult | SectionLeafSafetyResult,
) -> dict[str, object]:
    """Serialize one accepted safety-layer result without its safe plan."""
    return {
        "status": "REPAIRED" if result.changed else "PASSED",
        "changed": result.changed,
        "evidence": result.evidence().model_dump(mode="json"),
        "failure_code": None,
    }


def _not_run_layer() -> dict[str, object]:
    """Return bounded evidence for a safety layer skipped after failure."""
    return {"status": "NOT_RUN", "changed": False, "evidence": None, "failure_code": None}


async def run_execution(
    case: dict[str, object],
    *,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
) -> dict[str, object]:
    """Run one production planner execution and all three safety layers."""
    calls: list[dict[str, object]] = []
    plans: list[tuple[str, SemanticPlan]] = []
    backend = RecordingBackend(delegate=delegate, calls=calls, plans=plans)
    planner = SemanticPlanner(backend=backend, registry=registry)
    planner_error_type: str | None = None
    planner_error_code: str | None = None
    planner_classification: str | None = None
    planner_infra = False
    raw_plan: SemanticPlan | None = None
    try:
        raw_plan = await planner.plan(
            request=str(case["request"]),
            mode="reconstruct",
            current_document_summary={},
            source_summary=_source_summary(),
            timeout_seconds=TIMEOUT_SECONDS,
            temperature=PLANNER_TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
    except ProviderRequestError as error:
        planner_error_type = "ProviderRequestError"
        planner_error_code = error.category.value
        planner_infra = _infra_failure(planner_error_code)
        planner_classification = "INFRA_FAILURE" if planner_infra else "PLANNER_FAILURE"
    except PlannerSemanticFailure as error:
        planner_error_type = "PlannerSemanticFailure"
        planner_error_code = error.code
        planner_classification = "PLANNER_FAILURE"
    except ValidationError:
        planner_error_type = "ValidationError"
        planner_error_code = "structured_output_validation"
        planner_classification = "PLANNER_FAILURE"

    raw_facts = _facts(raw_plan, case, registry)
    if raw_plan is not None:
        raw_classification = p5.classify_facts(raw_facts or {})
    else:
        raw_classification = planner_classification

    safety: dict[str, object] = {
        "cm58_1": _not_run_layer(),
        "cm58_2": _not_run_layer(),
        "cm58_3": _not_run_layer(),
    }
    final_plan = raw_plan
    terminal_stage: str | None = None
    terminal_failure_code: str | None = None
    if raw_plan is not None:
        try:
            first = enforce_capability_safety(
                request=str(case["request"]), plan=final_plan, registry=registry
            )
            safety["cm58_1"] = _layer_evidence(first)
            final_plan = first.safe_plan
        except CapabilitySafetyFailure as error:
            safety["cm58_1"] = {
                "status": "FAILED",
                "changed": False,
                "evidence": None,
                "failure_code": error.code,
            }
            terminal_stage = "capability_safety"
            terminal_failure_code = error.code
        if terminal_stage is None:
            try:
                second = enforce_report_boundary_safety(
                    request=str(case["request"]), plan=final_plan, registry=registry
                )
                safety["cm58_2"] = _layer_evidence(second)
                final_plan = second.safe_plan
            except ReportBoundarySafetyFailure as error:
                safety["cm58_2"] = {
                    "status": "FAILED",
                    "changed": False,
                    "evidence": None,
                    "failure_code": error.code,
                }
                terminal_stage = "report_boundary_safety"
                terminal_failure_code = error.code
        if terminal_stage is None:
            try:
                third = enforce_section_leaf_safety(
                    request=str(case["request"]), plan=final_plan, registry=registry
                )
                safety["cm58_3"] = _layer_evidence(third)
                final_plan = third.safe_plan
            except SectionLeafSafetyFailure as error:
                safety["cm58_3"] = {
                    "status": "FAILED",
                    "changed": False,
                    "evidence": None,
                    "failure_code": error.code,
                }
                terminal_stage = "section_leaf_safety"
                terminal_failure_code = error.code
    if raw_plan is None:
        final_plan = None
        terminal_stage = "planner"
        terminal_failure_code = planner_error_code
    elif terminal_stage is None:
        terminal_stage = None
        terminal_failure_code = None

    final_facts = _facts(final_plan, case, registry) if terminal_stage is None else None
    final_contract = final_plan is not None and p5.final_contract_ok(final_facts or {})
    final_classification = (
        p5.classify_facts(final_facts or {})
        if final_plan is not None
        else ("SAFE_REJECTION" if terminal_stage != "planner" else planner_classification)
    )
    safety_actions = sum(
        len((layer.get("evidence") or {}).get("actions", []))
        for layer in safety.values()
        if isinstance(layer, dict)
    )
    return {
        "provider_calls": len(calls),
        "program_calls": backend.program_calls,
        "call_trace": calls,
        "response_schema_sha256": _schema_sha256(),
        "initial_plan_available": any(kind == "INITIAL" for kind, _ in plans),
        "invalid_response_retry_used": any(
            call.get("call_kind") == "INVALID_RESPONSE_RETRY" for call in calls
        ),
        "semantic_correction_used": any(
            call.get("call_kind") == "SEMANTIC_CORRECTION" for call in calls
        ),
        "final_planner_success": raw_plan is not None,
        "final_error_type": planner_error_type,
        "final_error_code": planner_error_code,
        "provider_infrastructure_failure": planner_infra,
        "raw_plan_projection": _plan_projection(raw_plan),
        "raw_work_unit_facts": raw_facts,
        "raw_classification": raw_classification,
        "raw_contract_ok": raw_plan is not None and p5.final_contract_ok(raw_facts or {}),
        "safety": safety,
        "final_plan_projection": _plan_projection(final_plan),
        "final_work_unit_facts": final_facts,
        "final_classification": final_classification,
        "final_contract_ok": final_contract,
        "final_plan_available": final_plan is not None and terminal_stage is None,
        "terminal_stage": terminal_stage,
        "terminal_failure_code": terminal_failure_code,
        "safety_action_count": safety_actions,
    }


async def run_row(
    case: dict[str, object],
    *,
    attempt_index: int,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
    authorized_checkpoint: str,
    endpoint_pre_fingerprint_sha256: str,
) -> dict[str, object]:
    """Run one case/attempt and bind it to the frozen input provenance."""
    provenance = frozen_provenance()
    result = await run_execution(case, delegate=delegate, registry=registry)
    return {
        **provenance,
        "authorized_checkpoint": authorized_checkpoint,
        "endpoint_pre_fingerprint_sha256": endpoint_pre_fingerprint_sha256,
        "case_id": case["case_id"],
        "family": case["family"],
        "residual_class": case["residual_class"],
        "attempt_index": attempt_index,
        "request_sha256": sha256_text(str(case["request"])),
        "expected_report_capabilities": list(case["expected_report_capabilities"]),
        "expected_sections": [list(section) for section in case["expected_sections"]],
        "expected_unresolved_count": case["expected_unresolved_count"],
        "planner": {key: value for key, value in result.items() if key != "safety"},
        "safety": result["safety"],
        "final_system": {
            "final_plan_available": result["final_plan_available"],
            "final_plan_projection": result["final_plan_projection"],
            "final_work_unit_facts": result["final_work_unit_facts"],
            "final_classification": result["final_classification"],
            "final_contract_ok": result["final_contract_ok"],
            "terminal_stage": result["terminal_stage"],
            "terminal_failure_code": result["terminal_failure_code"],
        },
        "program_calls": result["program_calls"],
    }


def _row_planner(row: dict[str, object]) -> dict[str, object]:
    """Return one bounded planner result."""
    value = row.get("planner")
    return value if isinstance(value, dict) else {}


def _row_final(row: dict[str, object]) -> dict[str, object]:
    """Return one bounded final system result."""
    value = row.get("final_system")
    return value if isinstance(value, dict) else {}


def _final_signature(row: dict[str, object]) -> tuple[object, ...]:
    """Return the required final repeatability signature."""
    final = _row_final(row)
    planner = _row_planner(row)
    return (
        bool(final.get("final_contract_ok")),
        canonical_json(final.get("final_work_unit_facts")),
        bool(final.get("final_plan_available")),
        final.get("terminal_stage"),
        final.get("terminal_failure_code"),
        bool(planner.get("final_planner_success")),
        bool(planner.get("provider_infrastructure_failure")),
    )


def _raw_signature(row: dict[str, object]) -> tuple[object, ...]:
    """Return a bounded raw planner repeatability signature."""
    planner = _row_planner(row)
    return (
        bool(planner.get("raw_contract_ok")),
        canonical_json(planner.get("raw_work_unit_facts")),
        planner.get("raw_classification"),
        planner.get("final_error_code"),
    )


def case_statuses(
    rows: list[dict[str, object]], cases: tuple[dict[str, object], ...]
) -> dict[str, str]:
    """Classify each case from its two final system attempts."""
    statuses: dict[str, str] = {}
    for case in cases:
        case_id = str(case["case_id"])
        attempts = sorted(
            (row for row in rows if row.get("case_id") == case_id),
            key=lambda row: int(row.get("attempt_index", -1)),
        )
        if len(attempts) != ATTEMPTS:
            statuses[case_id] = "UNAVAILABLE"
            continue
        if _final_signature(attempts[0]) != _final_signature(attempts[1]):
            statuses[case_id] = "UNSTABLE"
            continue
        first_final = _row_final(attempts[0])
        planner = _row_planner(attempts[0])
        if bool(planner.get("provider_infrastructure_failure")):
            statuses[case_id] = "UNAVAILABLE"
        elif bool(first_final.get("final_contract_ok")):
            statuses[case_id] = "STABLE_PASS"
        elif not bool(first_final.get("final_plan_available")):
            if first_final.get("terminal_stage") == "planner":
                statuses[case_id] = "STABLE_PLANNER_FAIL"
            else:
                statuses[case_id] = "STABLE_SAFE_REJECT"
        else:
            statuses[case_id] = "STABLE_WRONG_ESCAPE"
    return statuses


def _final_facts(row: dict[str, object]) -> dict[str, object] | None:
    """Return final scored facts when a final plan exists."""
    value = _row_final(row).get("final_work_unit_facts")
    return value if isinstance(value, dict) else None


def population_integrity(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    expected_checkpoint: str | None = None,
    pre_fingerprint: dict[str, object] | None = None,
) -> tuple[bool, list[str]]:
    """Fail closed on rows, provenance, controls, and worker isolation."""
    reasons: set[str] = set()
    expected_ids = {str(case["case_id"]) for case in cases}
    pairs = [(str(row.get("case_id")), row.get("attempt_index")) for row in rows]
    if len(rows) != len(cases) * ATTEMPTS:
        reasons.add("wrong_row_count")
    if len(set(pairs)) != len(pairs):
        reasons.add("duplicate_case_attempt")
    if {case_id for case_id, _ in pairs} != expected_ids:
        reasons.add("case_set_mismatch")
    by_case: dict[str, set[object]] = {}
    for case_id, attempt in pairs:
        by_case.setdefault(case_id, set()).add(attempt)
    if any(attempts != set(range(ATTEMPTS)) for attempts in by_case.values()):
        reasons.add("attempt_index_mismatch")
    checkpoints = {row.get("authorized_checkpoint") for row in rows}
    if None in checkpoints or len(checkpoints) != 1:
        reasons.add("checkpoint_missing_or_mixed")
    elif expected_checkpoint is not None and checkpoints != {expected_checkpoint}:
        reasons.add("checkpoint_mismatch")
    if pre_fingerprint is None:
        reasons.add("pre_fingerprint_missing")
    else:
        expected_pre = sha256_text(canonical_json(pre_fingerprint))
        if any(row.get("endpoint_pre_fingerprint_sha256") != expected_pre for row in rows):
            reasons.add("pre_fingerprint_mismatch")
    expected_cases = {str(case["case_id"]): case for case in cases}
    provenance = frozen_provenance()
    for row in rows:
        case = expected_cases.get(str(row.get("case_id")))
        if case is None:
            continue
        for provenance_field, value in provenance.items():
            if row.get(provenance_field) != value:
                reasons.add(f"{provenance_field}_mismatch")
        if row.get("family") != case["family"]:
            reasons.add("family_mismatch")
        if row.get("residual_class") != case["residual_class"]:
            reasons.add("residual_class_mismatch")
        if row.get("request_sha256") != sha256_text(str(case["request"])):
            reasons.add("request_hash_mismatch")
        for field in (
            "expected_report_capabilities",
            "expected_sections",
            "expected_unresolved_count",
        ):
            if row.get(field) != case[field]:
                reasons.add(f"{field}_mismatch")
        planner = _row_planner(row)
        if planner.get("response_schema_sha256") != _schema_sha256():
            reasons.add("planner_schema_mismatch")
        if int(row.get("program_calls", 0)) != 0 or int(planner.get("program_calls", 0)) != 0:
            reasons.add("worker_program_call")
        if int(planner.get("provider_calls", -1)) != len(planner.get("call_trace", [])):
            reasons.add("provider_call_trace_mismatch")
        if set(row.get("safety", {})) != set(SAFETY_LAYER_KEYS):
            reasons.add("safety_layer_set_mismatch")
    return not reasons, sorted(reasons)


def _endpoint_status(
    pre: dict[str, object] | None,
    post: dict[str, object] | None,
) -> tuple[bool, list[str]]:
    """Validate and compare normalized PRE/POST endpoint identity."""
    if pre is None or post is None:
        return False, ["endpoint_fingerprint_missing"]
    pre_valid, pre_reasons = fingerprint.validate_endpoint_fingerprint_v2(pre)
    post_valid, post_reasons = fingerprint.validate_endpoint_fingerprint_v2(post)
    reasons = [f"pre_{reason}" for reason in pre_reasons]
    reasons.extend(f"post_{reason}" for reason in post_reasons)
    reasons.extend(
        f"endpoint_{reason}" for reason in fingerprint.compare_endpoint_fingerprints_v2(pre, post)
    )
    return pre_valid and post_valid and not reasons, sorted(set(reasons))


def _reference_safety(
    rows: list[dict[str, object]], cases: tuple[dict[str, object], ...]
) -> dict[str, int]:
    """Count reference presence violations against final system gold."""
    by_id = {str(case["case_id"]): case for case in cases}
    unexpected = missing = 0
    for row in rows:
        facts = _final_facts(row)
        case = by_id.get(str(row.get("case_id")))
        if facts is None or case is None:
            continue
        required = any("track.reference" in section for section in case["expected_sections"])
        present = any(
            "track.reference" in signature
            for signature in facts.get("section_capability_signatures", [])
        )
        if required and not present:
            missing += 1
        if not required and present:
            unexpected += 1
    return {"unexpected_reference": unexpected, "missing_required_reference": missing}


def _structural_safety(rows: list[dict[str, object]]) -> dict[str, int]:
    """Count final parent-closure and duplicate-capability violations."""
    parent = duplicate = 0
    for row in rows:
        facts = _final_facts(row)
        if facts is None:
            continue
        parent += not bool(facts.get("parent_closure_valid"))
        duplicate += bool(facts.get("duplicate_capability_type"))
    return {"parent_closure_invalid": parent, "duplicate_capability_type": duplicate}


def _transition_counts(rows: list[dict[str, object]]) -> dict[str, int]:
    """Count raw-to-final safety transitions."""
    counts: Counter[str] = Counter()
    for row in rows:
        planner = _row_planner(row)
        final = _row_final(row)
        if bool(planner.get("provider_infrastructure_failure")):
            counts["INFRA_FAILURE"] += 1
        elif not bool(planner.get("final_planner_success")):
            counts["PLANNER_FAILURE"] += 1
        elif bool(planner.get("raw_contract_ok")) and bool(final.get("final_contract_ok")):
            counts["RAW_PASS_TO_FINAL_PASS"] += 1
        elif bool(planner.get("raw_contract_ok")):
            counts["RAW_PASS_TO_REGRESSION"] += 1
        elif bool(final.get("final_contract_ok")):
            counts["RAW_FAIL_TO_FINAL_PASS"] += 1
        elif not bool(final.get("final_plan_available")):
            counts["RAW_FAIL_TO_SAFE_REJECTION"] += 1
        else:
            counts["RAW_FAIL_TO_WRONG_FINAL_PLAN"] += 1
    return dict(counts)


def decision(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    expected_checkpoint: str | None = None,
    pre_fingerprint: dict[str, object] | None = None,
    post_fingerprint: dict[str, object] | None = None,
) -> str:
    """Apply the frozen CM-59A acceptance and inconclusive rules."""
    complete, _ = population_integrity(
        rows,
        cases,
        expected_checkpoint=expected_checkpoint,
        pre_fingerprint=pre_fingerprint,
    )
    endpoint_ok, _ = _endpoint_status(pre_fingerprint, post_fingerprint)
    if not complete or not endpoint_ok:
        return "INCONCLUSIVE_SYSTEM_REEVALUATION"
    if any(bool(_row_planner(row).get("provider_infrastructure_failure")) for row in rows):
        return "INCONCLUSIVE_SYSTEM_REEVALUATION"
    statuses = case_statuses(rows, cases)
    if any(status in {"UNAVAILABLE", "UNSTABLE"} for status in statuses.values()):
        return "SYSTEM_REEVALUATION_REJECTED"
    stable_passes = sum(status == "STABLE_PASS" for status in statuses.values())
    family_passes = {
        family: sum(
            statuses[str(case["case_id"])] == "STABLE_PASS"
            for case in cases
            if case["family"] == family
        )
        for family in FAMILIES
    }
    residual_passes = {
        residual: sum(
            statuses[str(case["case_id"])] == "STABLE_PASS"
            for case in cases
            if case["residual_class"] == residual
        )
        for residual in ("LICHEN_CLASS", "MARINER_CLASS")
    }
    planner_terminal_failures = sum(
        not bool(_row_planner(row).get("final_planner_success")) for row in rows
    )
    wrong_escapes = sum(status == "STABLE_WRONG_ESCAPE" for status in statuses.values())
    safety_regressions = sum(
        bool(_row_planner(row).get("raw_contract_ok"))
        and not bool(_row_final(row).get("final_contract_ok"))
        for row in rows
    )
    unnecessary_actions = sum(
        bool(_row_planner(row).get("raw_contract_ok"))
        and int(_row_planner(row).get("safety_action_count", 0)) > 0
        for row in rows
    )
    reference = _reference_safety(rows, cases)
    structural = _structural_safety(rows)
    if (
        stable_passes < 22
        or any(value < 3 for value in family_passes.values())
        or residual_passes["LICHEN_CLASS"] != 2
        or residual_passes["MARINER_CLASS"] != 2
        or planner_terminal_failures
        or wrong_escapes
        or safety_regressions
        or unnecessary_actions
        or reference["unexpected_reference"]
        or reference["missing_required_reference"]
        or structural["parent_closure_invalid"]
        or structural["duplicate_capability_type"]
    ):
        return "SYSTEM_REEVALUATION_REJECTED"
    return "SYSTEM_REEVALUATION_ACCEPTED"


def summarize_population(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    authorized_checkpoint: str | None = None,
    pre_fingerprint: dict[str, object] | None = None,
    post_fingerprint: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build bounded final evidence without provider responses or prose."""
    complete, reasons = population_integrity(
        rows,
        cases,
        expected_checkpoint=authorized_checkpoint,
        pre_fingerprint=pre_fingerprint,
    )
    statuses = case_statuses(rows, cases)
    endpoint_ok, endpoint_reasons = _endpoint_status(pre_fingerprint, post_fingerprint)
    final_decision = decision(
        rows,
        cases,
        expected_checkpoint=authorized_checkpoint,
        pre_fingerprint=pre_fingerprint,
        post_fingerprint=post_fingerprint,
    )
    family_passes = {
        family: sum(
            statuses[str(case["case_id"])] == "STABLE_PASS"
            for case in cases
            if case["family"] == family
        )
        for family in FAMILIES
    }
    residual_passes = {
        residual: sum(
            statuses[str(case["case_id"])] == "STABLE_PASS"
            for case in cases
            if case["residual_class"] == residual
        )
        for residual in ("LICHEN_CLASS", "MARINER_CLASS")
    }
    raw_signatures: dict[str, list[tuple[object, ...]]] = {}
    for case in cases:
        case_rows = sorted(
            (row for row in rows if row.get("case_id") == case["case_id"]),
            key=lambda row: int(row.get("attempt_index", -1)),
        )
        raw_signatures[str(case["case_id"])] = [_raw_signature(row) for row in case_rows]
    raw_repeatability = {
        "stable_cases": sum(
            len(signatures) == 2 and signatures[0] == signatures[1]
            for signatures in raw_signatures.values()
        ),
        "unstable_cases": sum(
            len(signatures) == 2 and signatures[0] != signatures[1]
            for signatures in raw_signatures.values()
        ),
    }
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "authorized_checkpoint": authorized_checkpoint,
        "decision": final_decision,
        "population": {
            "expected_rows": len(cases) * ATTEMPTS,
            "actual_rows": len(rows),
            "cases": len(cases),
            "attempts_per_case": ATTEMPTS,
            "planner_executions": len(rows),
            "provider_calls": sum(int(_row_planner(row).get("provider_calls", 0)) for row in rows),
            "program_worker_calls": sum(int(row.get("program_calls", 0)) for row in rows),
            "complete": complete,
            "integrity_reasons": reasons,
        },
        "case_statuses": statuses,
        "family_stable_passes": family_passes,
        "residual_stable_passes": residual_passes,
        "raw_repeatability": raw_repeatability,
        "raw_to_final_transitions": _transition_counts(rows),
        "planner_metrics": {
            "successful_executions": sum(
                bool(_row_planner(row).get("final_planner_success")) for row in rows
            ),
            "invalid_response_retries": sum(
                bool(_row_planner(row).get("invalid_response_retry_used")) for row in rows
            ),
            "semantic_corrections": sum(
                bool(_row_planner(row).get("semantic_correction_used")) for row in rows
            ),
            "terminal_planner_failures": sum(
                not bool(_row_planner(row).get("final_planner_success")) for row in rows
            ),
            "provider_infrastructure_failures": sum(
                bool(_row_planner(row).get("provider_infrastructure_failure")) for row in rows
            ),
        },
        "safety_actions": {
            "reference_removals": _action_count(rows, "remove_reference"),
            "reference_replacements": _action_count(rows, "replace_reference_with_normal"),
            "report_standard_additions": _action_count(rows, "add_report_standard"),
            "unrequested_report_removals": _action_count(rows, "remove_report_task"),
            "raster_only_curve_removals": _action_count(rows, "remove_raster_only_curve_binding"),
            "report_note_annotation_removals": _action_count(
                rows, "remove_report_note_annotation_leakage"
            ),
            "section_leaf_failures": _layer_failure_count(rows, "cm58_3"),
        },
        "reference_safety": _reference_safety(rows, cases),
        "structural_safety": _structural_safety(rows),
        "safety_regressions": sum(
            bool(_row_planner(row).get("raw_contract_ok"))
            and not bool(_row_final(row).get("final_contract_ok"))
            for row in rows
        ),
        "unnecessary_safety_actions_on_raw_pass": sum(
            bool(_row_planner(row).get("raw_contract_ok"))
            and int(_row_planner(row).get("safety_action_count", 0)) > 0
            for row in rows
        ),
        "wrong_final_plan_escapes": sum(
            status == "STABLE_WRONG_ESCAPE" for status in statuses.values()
        ),
        "endpoint_provenance": {
            "valid_and_equal": endpoint_ok,
            "reasons": endpoint_reasons,
            "pre_normalized_identity_sha256": (
                pre_fingerprint.get("normalized_identity_sha256") if pre_fingerprint else None
            ),
            "post_normalized_identity_sha256": (
                post_fingerprint.get("normalized_identity_sha256") if post_fingerprint else None
            ),
        },
        "provenance": frozen_provenance(),
        "acceptance_thresholds": {
            "stable_passes_minimum": 22,
            "family_stable_passes_minimum": 3,
            "lichen_stable_passes": 2,
            "mariner_stable_passes": 2,
            "wrong_final_plan_escapes_maximum": 0,
            "safety_regressions_maximum": 0,
            "unstable_cases_maximum": 0,
            "planner_terminal_failures_maximum": 0,
        },
        "production_adoption": "NOT_AUTHORIZED",
        "CM-57D": "BLOCKED",
    }


def _action_count(rows: list[dict[str, object]], action_kind: str) -> int:
    """Count one action kind across bounded safety evidence."""
    count = 0
    for row in rows:
        safety = row.get("safety")
        if not isinstance(safety, dict):
            continue
        for layer in safety.values():
            if not isinstance(layer, dict):
                continue
            evidence = layer.get("evidence")
            actions = evidence.get("actions", []) if isinstance(evidence, dict) else []
            count += sum(action.get("kind") == action_kind for action in actions)
    return count


def _layer_failure_count(rows: list[dict[str, object]], layer_name: str) -> int:
    """Count deterministic failures from one safety layer."""
    return sum(
        isinstance(row.get("safety"), dict)
        and isinstance(row["safety"].get(layer_name), dict)
        and row["safety"][layer_name].get("status") == "FAILED"
        for row in rows
    )


def _historical_plan_diagnostic(
    *,
    request: str,
    plan: SemanticPlan | None,
    expected: dict[str, object],
    registry: CapabilityRegistry,
) -> dict[str, object]:
    """Run a provider-free historical residual shape through CM-58."""
    if plan is None:
        return {"status": "NO_PLAN_ANCHOR", "final_plan_available": False}
    current = plan
    failures: list[str] = []
    actions: list[str] = []
    for name, function in (
        ("capability_safety", enforce_capability_safety),
        ("report_boundary_safety", enforce_report_boundary_safety),
        ("section_leaf_safety", enforce_section_leaf_safety),
    ):
        try:
            result = function(request=request, plan=current, registry=registry)
        except (
            CapabilitySafetyFailure,
            ReportBoundarySafetyFailure,
            SectionLeafSafetyFailure,
        ) as error:
            failures.append(f"{name}.{error.code}")
            break
        current = result.safe_plan
        actions.extend(action.kind.value for action in result.actions)
    facts = p5._facts(current, expected, registry) if not failures else None
    return {
        "status": "PASS" if facts is not None and p5.final_contract_ok(facts) else "MISMATCH",
        "final_plan_available": not failures,
        "failure_codes": failures,
        "actions": actions,
        "final_work_unit_facts": facts,
    }


def historical_anchor_diagnostics() -> dict[str, object]:
    """Verify old Lichen and Mariner shapes remain diagnostic-only anchors."""
    registry = create_builtin_registry()
    lichen_expected = {
        "expected_report_capabilities": [],
        "expected_sections": [
            ["section.log_plot", "track.normal", "binding.curve"],
            ["section.log_plot", "track.reference", "track.normal", "binding.curve"],
            ["section.log_plot", "track.array", "binding.raster"],
        ],
        "expected_unresolved_count": 0,
    }
    lichen_p = SemanticPlan(
        summary="historical anchor",
        report_task=p5.ReportTask(goal="report", capability_ids=()),
        section_tasks=(
            p5.SectionTask(
                goal="ordinary",
                capability_ids=("section.log_plot", "track.normal", "binding.curve"),
            ),
            p5.SectionTask(
                goal="reference",
                capability_ids=(
                    "section.log_plot",
                    "track.reference",
                    "track.normal",
                    "binding.curve",
                ),
            ),
            p5.SectionTask(
                goal="image", capability_ids=("section.log_plot", "track.array", "binding.raster")
            ),
        ),
    )
    lichen_rc = lichen_p.model_copy(
        update={
            "report_task": None,
            "section_tasks": (
                p5.SectionTask(
                    goal="ordinary",
                    capability_ids=("section.log_plot", "track.normal", "binding.curve"),
                ),
                p5.SectionTask(
                    goal="reference",
                    capability_ids=("section.log_plot", "track.reference", "binding.curve"),
                ),
                p5.SectionTask(
                    goal="image",
                    capability_ids=("section.log_plot", "track.array", "binding.raster"),
                ),
            ),
        }
    )
    mariner_expected = {
        "expected_report_capabilities": ["report.standard"],
        "expected_sections": [],
        "expected_unresolved_count": 0,
    }
    mariner_p = SemanticPlan(
        summary="historical anchor",
        report_task=p5.ReportTask(goal="report", capability_ids=()),
    )
    return {
        "historical_lichen_p_shape": _historical_plan_diagnostic(
            request=(
                "Arrange three analysis panels: a scalar measurement, a depth reference "
                "with its scalar measurement, and an image."
            ),
            plan=lichen_p,
            expected=lichen_expected,
            registry=registry,
        ),
        "historical_lichen_rc_shape": _historical_plan_diagnostic(
            request="Arrange three analysis panels including a depth-indexed scalar measurement.",
            plan=lichen_rc,
            expected=lichen_expected,
            registry=registry,
        ),
        "historical_mariner_p_shape": _historical_plan_diagnostic(
            request="Prepare a completion summary and report note.",
            plan=mariner_p,
            expected=mariner_expected,
            registry=registry,
        ),
        "historical_mariner_rc": {"status": "NO_PLAN_ANCHOR", "final_plan_available": False},
        "decision_bearing": False,
    }


def verify_frozen_contract() -> dict[str, object]:
    """Run all provider-free pre-live artifact and corpus checks."""
    cases = load_case_definitions()
    _verify_production_matches_baseline()
    prompt_sha = sha256_text(_PLANNER_SYSTEM_PROMPT)
    schema_sha = _schema_sha256()
    source_sha = _source_summary_sha256()
    if prompt_sha != p5.EXPECTED_BASE_PROMPT_SHA256:
        raise RuntimeError("CM-59A production planner prompt drifted.")
    if schema_sha != "3a331166ccc570a74056dea7770d04b16f8fa32dc3641d6c37de6c26cf81d9e3":
        raise RuntimeError("CM-59A SemanticPlan schema drifted.")
    if source_sha != "ec6147a1b5e1ac6374e34ae3d66d11275542c6b340337cb26d3ae1d06240532e":
        raise RuntimeError("CM-59A source summary drifted.")
    if p5._catalog_sha256() != "b1b9c85db961cb8b97f1c8b6f914a6a75f5bf57cf49ca4413c64d35311b80d37":
        raise RuntimeError("CM-59A capability catalogue drifted.")
    if POLICY_VERSIONS != {
        "capability_safety": "cm58.reference-admissibility.v1",
        "report_boundary_safety": "cm58.report-boundary.v1",
        "section_leaf_safety": "cm58.section-leaf-admissibility.v1",
    }:
        raise RuntimeError("CM-59A safety policy version drifted.")
    return {
        "case_count": len(cases),
        "family_counts": dict(Counter(str(case["family"]) for case in cases)),
        "residual_counts": dict(Counter(str(case["residual_class"]) for case in cases)),
        "corpus_sha256": artifact_sha256(CASE_PATH),
        "harness_sha256": artifact_sha256(Path(__file__)),
        "P_prompt_sha256": prompt_sha,
        "response_schema_sha256": schema_sha,
        "source_summary_sha256": source_sha,
        "production_source_hashes": _production_source_hashes(),
        "policy_versions": dict(POLICY_VERSIONS),
    }


def prelive_report() -> dict[str, object]:
    """Return the provider-free CM-59A audit report."""
    contract = verify_frozen_contract()
    cases = load_case_definitions()
    return {
        "status": "PRELIVE_READY",
        "experiment_version": EXPERIMENT_VERSION,
        "design_baseline_sha": BASELINE_SHA,
        "current_checkout_sha": current_checkout_sha(),
        "live_inference": "NOT_AUTHORIZED",
        "provider_calls": 0,
        "endpoint_calls": 0,
        "program_worker_calls": 0,
        "production_source_changes": 0,
        "production_adoption": "NOT_AUTHORIZED",
        "CM-58.4": "NOT_AUTHORIZED",
        "P11": "NOT_AUTHORIZED",
        "CM-57D": "BLOCKED",
        "future_controls": {**FROZEN_EXECUTION_CONTROLS, "attempts": ATTEMPTS},
        "future_population": {
            "cases": len(cases),
            "families": len(FAMILIES),
            "planner_executions": len(cases) * ATTEMPTS,
            "provider_calls_min": len(cases) * ATTEMPTS,
            "provider_calls_max": len(cases) * ATTEMPTS * 3,
            "future_populations_remaining": 1,
        },
        "freshness": "PASS",
        "historical_anchor_diagnostics": historical_anchor_diagnostics(),
        "acceptance_thresholds": {
            "stable_passes_minimum": 22,
            "family_stable_passes_minimum": 3,
            "lichen_stable_passes": 2,
            "mariner_stable_passes": 2,
            "wrong_final_plan_escapes_maximum": 0,
            "safety_regressions_maximum": 0,
            "unstable_cases_maximum": 0,
            "planner_terminal_failures_maximum": 0,
        },
        "output_paths": {
            "evidence": str(OUTPUT_PATH),
            "endpoint_pre": str(ENDPOINT_PRE_PATH),
            "endpoint_post": str(ENDPOINT_POST_PATH),
            "summary": str(SUMMARY_PATH),
        },
        **contract,
    }


def verify_reviewed_checkout(checkpoint: str) -> None:
    """Require the exact implementation checkpoint before live execution."""
    if CHECKPOINT_RE.fullmatch(checkpoint) is None or current_checkout_sha() != checkpoint:
        raise RuntimeError("CM-59A checkout does not match the authorized checkpoint.")
    for relative_path in (
        "scripts/cm59a_system_reevaluation.py",
        "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json",
        "tests/test_cm59a_system_reevaluation.py",
        "docs/evaluations/agent-code-mode/CM-59A-development-memory.md",
        *PRODUCTION_ARTIFACTS,
    ):
        path = REPO_ROOT / relative_path
        if not path.exists() or path.read_bytes() != _git_output(
            "show", f"{checkpoint}:{relative_path}"
        ):
            raise RuntimeError(f"CM-59A guarded artifact drifted: {relative_path}")


def _api_key(args: argparse.Namespace) -> str:
    """Resolve the configured API key without retaining it in evidence."""
    value = os.getenv(args.api_key_env, "").strip()
    if args.api_key_file:
        path = Path(args.api_key_file)
        if not path.is_absolute():
            path = REPO_ROOT / path
        value = value or path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError("No CM-59A API key configured.")
    return value


def _provider_configuration(args: argparse.Namespace) -> ModelBackendProtocol:
    """Construct the provider only after all live guards pass."""
    from openai import AsyncOpenAI  # noqa: I001
    from wellplot.agent.providers.openai_compat_v2 import (  # noqa: I001
        OpenAICompatibleBackendV2,
    )

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


def _ensure_empty_evidence(path: Path) -> None:
    """Reject append/resume behavior before provider construction."""
    if path.exists() and path.stat().st_size:
        raise RuntimeError(f"CM-59A evidence path is non-empty: {path}")


def _ensure_fresh_live_artifacts(paths: tuple[Path, ...]) -> None:
    """Reject any previously populated live artifact before endpoint access."""
    for path in paths:
        _ensure_empty_evidence(path)


async def _run_live(args: argparse.Namespace, checkpoint: str) -> None:
    """Run the one authorized sequential planner-only population."""
    verify_reviewed_checkout(checkpoint)
    verify_frozen_contract()
    output = Path(args.evidence_path)
    _ensure_fresh_live_artifacts(
        (
            output,
            Path(args.endpoint_fingerprint_pre),
            Path(args.endpoint_fingerprint_post),
            Path(args.summary_path),
        )
    )
    cases = load_case_definitions()
    pre = fingerprint.capture_endpoint_fingerprint_v2(
        endpoint=args.base_url,
        model_api_label=FROZEN_MODEL,
        api_key=_api_key(args),
        timeout_seconds=20.0,
    )
    pre_path = Path(args.endpoint_fingerprint_pre)
    pre_path.write_text(canonical_json(pre) + "\n", encoding="utf-8")
    pre_sha = sha256_text(canonical_json(pre))
    provider = _provider_configuration(args)
    registry = create_builtin_registry()
    with output.open("w", encoding="utf-8") as handle:
        for case in cases:
            for attempt_index in range(ATTEMPTS):
                row = await run_row(
                    case,
                    attempt_index=attempt_index,
                    delegate=provider,
                    registry=registry,
                    authorized_checkpoint=checkpoint,
                    endpoint_pre_fingerprint_sha256=pre_sha,
                )
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
    """Load one complete JSONL evidence population."""
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("CM-59A evidence rows must be JSON objects.")
        rows.append(value)
    return rows


def _load_fingerprint(path: Path) -> dict[str, object]:
    """Load one endpoint fingerprint without network access."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Endpoint fingerprint must be a JSON object.")
    return value


def finalize(
    *,
    evidence_path: Path,
    pre_path: Path,
    post_path: Path,
    authorized_checkpoint: str,
) -> dict[str, object]:
    """Finalize evidence without constructing a provider or calling a network."""
    verify_reviewed_checkout(authorized_checkpoint)
    verify_frozen_contract()
    cases = load_case_definitions()
    rows = _load_jsonl(evidence_path)
    pre = _load_fingerprint(pre_path)
    post = _load_fingerprint(post_path)
    return summarize_population(
        rows,
        cases,
        authorized_checkpoint=authorized_checkpoint,
        pre_fingerprint=pre,
        post_fingerprint=post,
    )


def _parser() -> argparse.ArgumentParser:
    """Build the guarded command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-authorized", action="store_true")
    parser.add_argument("--finalize", action="store_true")
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
    """Run provider-free audit, explicitly authorized live execution, or finalization."""
    args = _parser().parse_args(argv)
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
    if args.live_authorized:
        if not args.authorized_checkpoint or not args.base_url:
            raise SystemExit("--live-authorized requires --authorized-checkpoint and --base-url")
        asyncio.run(_run_live(args, args.authorized_checkpoint))
        return 0
    if args.authorized_checkpoint or args.base_url:
        raise SystemExit("Live arguments require --live-authorized or --finalize")
    print(json.dumps(prelive_report(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
