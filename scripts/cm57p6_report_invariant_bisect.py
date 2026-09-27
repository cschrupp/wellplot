"""CM-57P6 non-empty report work-unit invariant bisect.

The default command performs provider-free validation only. Live execution is
available solely behind the explicit authorization flags and is not part of
this implementation slice.
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
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, create_model

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import cm57p5_fresh_holdout as p5  # noqa: E402
from wellplot.agent.code_mode.planner import (  # noqa: E402
    _PLANNER_SYSTEM_PROMPT,
    PlannerSemanticError,
    PlannerSemanticFailure,
    ReportTask,
    SectionTask,
    SemanticPlan,
    SemanticPlanner,
    _correction_request,
    _planning_catalog,
    _planning_request,
    _safe_source_summary,
    validate_semantic_plan,
)
from wellplot.agent.providers.base import (  # noqa: E402
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry  # noqa: E402

CASE_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm57p5_fresh_holdout.json"
MANIFEST_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm57p6_report_invariant_cases.json"
P5_SCRIPT_PATH = REPO_ROOT / "scripts/cm57p5_fresh_holdout.py"
P5_SUMMARY_PATH = REPO_ROOT / "docs/evaluations/agent-code-mode/CM-57P5-live-summary.json"
OUTPUT_PATH = Path("/tmp/cm57p6-report-invariant-qwen.jsonl")

BASELINE_SHA = "f33f3bba228d10bbdb08818653fba83b051b18a9"
P5_CHECKPOINT = "aea88a0611804b88bf1694448283cd5818977c55"
P5_RAW_PATH = Path("/tmp/cm57p5-fresh-holdout-qwen.jsonl")
EXPERIMENT_VERSION = "CM-57P6"
MANIFEST_VERSION = "cm57p6.report-invariant.v1"
FROZEN_MODEL = "qwen3.6-35b-a3b"
PLANNER_TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 16384
MAX_TOKENS_PARAMETER = "max_tokens"
TIMEOUT_SECONDS = 900.0
ATTEMPTS = 2
ARMS: tuple[str, ...] = ("RC", "RCV", "RCS")
Arm = Literal["RC", "RCV", "RCS"]

ROLE_TARGET = "TARGET_EMPTY_REPORT"
ROLE_REPORT_CONTROL = "REPORT_PASS_CONTROL"
ROLE_SECTION_SENTINEL = "SECTION_SENTINEL"
ROLES = (ROLE_TARGET, ROLE_REPORT_CONTROL, ROLE_SECTION_SENTINEL)

TARGET_CASES = (
    "p5-report-header-01",
    "p5-report-settings-04",
    "p5-mixed-two-panels-19",
)
REPORT_CONTROL_CASES = (
    "p5-report-page-02",
    "p5-report-remarks-03",
    "p5-mixed-summary-17",
    "p5-mixed-image-18",
    "p5-mixed-combined-20",
)
SECTION_SENTINEL_CASES = (
    "p5-single-curve-05",
    "p5-heterogeneous-overlay-09",
    "p5-multi-curve-image-14",
    "p5-multiplicity-independent-24",
)

EXPECTED_P5_SUMMARY_SHA256 = "16bda565e0687b6d7e9d3e9c2b6e053111355fb85ee97bfc6f34ffffbac0810d"
EXPECTED_P5_RAW_SHA256 = "b9ce5e164d98ff18586d01ee561d83e43da023afca2f63b95de0170f8fb97cb2"
EXPECTED_P5_CORPUS_SHA256 = "29e85998481ce9bcc6eab9ecb7959d470cefbf3a84e5273309c6004aacae334d"
EXPECTED_P5_SCRIPT_SHA256 = "3170c970d2ad4298f87c09cb106237d015356e4a5854095e3f889ba139bc600e"
EXPECTED_PLANNER_SOURCE_SHA256 = "0189b290ef4f76bdd776fe2612c454809ff77725379def7d8c5a98d9ae165413"
EXPECTED_CATALOG_SHA256 = "b1b9c85db961cb8b97f1c8b6f914a6a75f5bf57cf49ca4413c64d35311b80d37"
EXPECTED_BASE_PROMPT_SHA256 = "5e7a0732af01e4b1f16b3ccf019c005ea2e9ba5c0e93e94870a56a261e2bca18"
EXPECTED_RC_PROMPT_SHA256 = "e1710cb516a96c47ec1d0593752e83aacc1bb4502c3026b2b6a9a676c90e4d34"
EXPECTED_SOURCE_SUMMARY_SHA256 = "ec6147a1b5e1ac6374e34ae3d66d11275542c6b340337cb26d3ae1d06240532e"
EXPECTED_MANIFEST_SHA256 = "123af939d720cc7b7480445d9d421773b91c85b2615d8103e0d943ece1b4d10f"
EXPECTED_PRODUCTION_SCHEMA_SHA256 = (
    "3a331166ccc570a74056dea7770d04b16f8fa32dc3641d6c37de6c26cf81d9e3"
)
EXPECTED_NONEMPTY_SCHEMA_SHA256 = "404357b174380f169c651147d988a02e8c6057bce451d18e295e85c3849af936"
CHECKPOINT_RE = re.compile(r"^[0-9a-f]{40}$")

FIXED_EXECUTION_CONTROLS = {
    "model": FROZEN_MODEL,
    "planner_temperature": PLANNER_TEMPERATURE,
    "max_output_tokens": MAX_OUTPUT_TOKENS,
    "max_tokens_parameter": MAX_TOKENS_PARAMETER,
    "timeout_seconds": TIMEOUT_SECONDS,
}

NonEmptyReportTask = create_model(
    "ReportTask",
    __base__=ReportTask,
    capability_ids=(tuple[str, ...], Field(min_length=1)),
)
NonEmptyReportTask.__doc__ = ReportTask.__doc__
NonEmptyReportSemanticPlan = create_model(
    "SemanticPlan",
    __base__=SemanticPlan,
    report_task=(NonEmptyReportTask | None, None),
)
NonEmptyReportSemanticPlan.__doc__ = SemanticPlan.__doc__


def canonical_json(value: object) -> str:
    """Serialize JSON-shaped evidence deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    """Hash exact UTF-8 text bytes."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def artifact_sha256(path: Path) -> str:
    """Hash one artifact by exact bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_output(*arguments: str) -> bytes:
    """Return exact output from a repository-local Git command."""
    return subprocess.check_output(["git", *arguments], cwd=REPO_ROOT, stderr=subprocess.STDOUT)


def current_checkout_sha() -> str:
    """Return the current checkout's full commit SHA."""
    return _git_output("rev-parse", "HEAD").decode().strip()


def production_schema() -> dict[str, object]:
    """Return the production planner response schema."""
    return SemanticPlan.model_json_schema()


def nonempty_report_schema() -> dict[str, object]:
    """Return the experimental non-empty-report response schema."""
    return NonEmptyReportSemanticPlan.model_json_schema()


def schema_sha256(response_model: type[BaseModel]) -> str:
    """Hash one canonical response schema."""
    return sha256_text(canonical_json(response_model.model_json_schema()))


def _normalized_schema(schema: dict[str, object]) -> dict[str, object]:
    """Remove only the authorized report capability constraint difference."""
    normalized = json.loads(canonical_json(schema))
    report_task = normalized["$defs"]["ReportTask"]
    capability_ids = report_task["properties"]["capability_ids"]
    capability_ids.pop("default", None)
    capability_ids.pop("minItems", None)
    report_task["required"] = [
        value for value in report_task["required"] if value != "capability_ids"
    ]
    return normalized


def schema_diff_isolated() -> bool:
    """Require the experimental schema to differ only at the frozen field."""
    production = production_schema()
    experimental = nonempty_report_schema()
    if _normalized_schema(production) != _normalized_schema(experimental):
        return False
    production_field = production["$defs"]["ReportTask"]["properties"]["capability_ids"]
    experimental_field = experimental["$defs"]["ReportTask"]["properties"]["capability_ids"]
    if production_field.get("default") != [] or "minItems" in production_field:
        return False
    if "default" in experimental_field or experimental_field.get("minItems") != 1:
        return False
    production_required = production["$defs"]["ReportTask"]["required"]
    experimental_required = experimental["$defs"]["ReportTask"]["required"]
    return "capability_ids" not in production_required and "capability_ids" in experimental_required


def _load_p5_cases() -> tuple[dict[str, object], ...]:
    """Load the frozen P5 corpus through its original validator."""
    return p5.load_case_definitions(CASE_PATH)


def load_manifest() -> tuple[dict[str, object], ...]:
    """Load and validate the twelve-case diagnostic manifest."""
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if payload.get("version") != MANIFEST_VERSION:
        raise ValueError("Unexpected CM-57P6 manifest version.")
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 12:
        raise ValueError("CM-57P6 requires exactly twelve manifest cases.")
    p5_cases = {str(case["case_id"]): case for case in _load_p5_cases()}
    seen: set[str] = set()
    role_counts: Counter[str] = Counter()
    for entry in cases:
        if set(entry) != {"case_id", "role", "historical_rc_status"}:
            raise ValueError("CM-57P6 manifest fields drifted.")
        case_id = entry["case_id"]
        role = entry["role"]
        status = entry["historical_rc_status"]
        if not isinstance(case_id, str) or case_id not in p5_cases or case_id in seen:
            raise ValueError("CM-57P6 manifest case IDs are invalid or duplicated.")
        if role not in ROLES or not isinstance(status, dict):
            raise ValueError("CM-57P6 manifest role/status is invalid.")
        seen.add(case_id)
        role_counts[str(role)] += 1
    if role_counts != Counter(
        {
            ROLE_TARGET: 3,
            ROLE_REPORT_CONTROL: 5,
            ROLE_SECTION_SENTINEL: 4,
        }
    ):
        raise ValueError(f"CM-57P6 role distribution is invalid: {role_counts!r}.")
    if tuple(entry["case_id"] for entry in cases[:3]) != TARGET_CASES:
        raise ValueError("CM-57P6 target order drifted.")
    return tuple(cases)


def _manifest_by_id() -> dict[str, dict[str, object]]:
    """Index manifest entries by their frozen case ID."""
    return {str(entry["case_id"]): entry for entry in load_manifest()}


def _case_by_id() -> dict[str, dict[str, object]]:
    """Index frozen P5 cases by case ID."""
    return {str(case["case_id"]): case for case in _load_p5_cases()}


def _fixed_source_summary_sha() -> str:
    """Return the frozen P5 source-summary hash from the actual object."""
    return sha256_text(p5.canonical_json(p5.FIXED_SOURCE_SUMMARY))


def _catalog_sha256() -> str:
    """Return the production planner catalogue hash."""
    return p5._catalog_sha256()


def _response_schema_for_arm(arm: Arm) -> type[BaseModel]:
    """Return the schema used at the provider boundary for one arm."""
    return NonEmptyReportSemanticPlan if arm == "RCS" else SemanticPlan


def _prompt_sha256() -> str:
    """Return the exact shared RC prompt hash."""
    return sha256_text(p5.RC_PROMPT)


def frozen_provenance() -> dict[str, object]:
    """Return provenance fields written to every future row."""
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "design_baseline_sha": BASELINE_SHA,
        "harness_sha256": artifact_sha256(Path(__file__)),
        "manifest_sha256": artifact_sha256(MANIFEST_PATH),
        "p5_summary_sha256": EXPECTED_P5_SUMMARY_SHA256,
        "p5_raw_sha256": EXPECTED_P5_RAW_SHA256,
        "p5_corpus_sha256": EXPECTED_P5_CORPUS_SHA256,
        "p5_script_sha256": EXPECTED_P5_SCRIPT_SHA256,
        "planner_source_sha256": EXPECTED_PLANNER_SOURCE_SHA256,
        "catalog_sha256": EXPECTED_CATALOG_SHA256,
        "base_prompt_sha256": EXPECTED_BASE_PROMPT_SHA256,
        "RC_prompt_sha256": EXPECTED_RC_PROMPT_SHA256,
        "production_schema_sha256": schema_sha256(SemanticPlan),
        "nonempty_report_schema_sha256": schema_sha256(NonEmptyReportSemanticPlan),
        "source_summary_sha256": _fixed_source_summary_sha(),
        "execution_controls": dict(FIXED_EXECUTION_CONTROLS),
    }


def validate_semantic_plan_nonempty_report(
    plan: SemanticPlan, registry: CapabilityRegistry
) -> SemanticPlan:
    """Apply production validation plus the experimental report invariant."""
    validated = validate_semantic_plan(plan, registry)
    if validated.report_task is not None and not validated.report_task.capability_ids:
        raise PlannerSemanticError(
            "empty_report_capabilities",
            "A present ReportTask must select at least one registered report capability.",
        )
    return validated


@dataclass(frozen=True, slots=True)
class InvariantSemanticPlanner:
    """Mirror SemanticPlanner while adding one validator-only invariant."""

    backend: ModelBackendProtocol
    registry: CapabilityRegistry

    async def plan(
        self,
        *,
        request: str,
        mode: Literal["reconstruct", "revise"],
        current_document_summary: Mapping[str, object] | None = None,
        source_summary: Mapping[str, object] | None = None,
        timeout_seconds: float,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> SemanticPlan:
        """Make the production two-call flow with the new validator only."""
        if not isinstance(request, str) or not request.strip():
            raise ValueError("Planning request must be a non-empty string.")
        context = {
            "request": request,
            "mode": mode,
            "current_document_summary": dict(current_document_summary or {}),
            "source_summary": _safe_source_summary(source_summary),
            "capabilities": _planning_catalog(self.registry),
        }
        invalid_response_retry_used = False
        try:
            generated = await self.backend.generate_structured(
                _planning_request(
                    context=context,
                    timeout_seconds=timeout_seconds,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
                response_model=SemanticPlan,
            )
        except ProviderRequestError as error:
            if error.category is not ProviderFailureCategory.INVALID_RESPONSE:
                raise
            invalid_response_retry_used = True
            generated = await self.backend.generate_structured(
                _planning_request(
                    context=context,
                    timeout_seconds=timeout_seconds,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
                response_model=SemanticPlan,
            )
        plan = SemanticPlan.model_validate(generated.value)
        try:
            return validate_semantic_plan_nonempty_report(plan, self.registry)
        except PlannerSemanticError as first_error:
            if invalid_response_retry_used:
                raise PlannerSemanticFailure(
                    first_error.code,
                    "Planner returned a semantically invalid plan after one correction.",
                ) from first_error
            corrected = await self.backend.generate_structured(
                _correction_request(
                    mode=mode,
                    request=request,
                    source_summary=source_summary,
                    previous_plan=plan,
                    diagnostic=first_error,
                    registry=self.registry,
                    timeout_seconds=timeout_seconds,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
                response_model=SemanticPlan,
            )
            corrected_plan = SemanticPlan.model_validate(corrected.value)
            try:
                return validate_semantic_plan_nonempty_report(corrected_plan, self.registry)
            except PlannerSemanticError as second_error:
                raise PlannerSemanticFailure(
                    second_error.code,
                    "Planner returned a semantically invalid plan after one correction.",
                ) from second_error


@dataclass
class PromptBackend(ModelBackendProtocol):
    """Replace only the production system prompt with the frozen RC prompt."""

    delegate: ModelBackendProtocol
    forwarded_requests: list[StructuredGenerationRequest]
    forwarded_response_models: list[type[BaseModel]]

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Forward the exact request with only RC system-prompt substitution."""
        if request.system_prompt != _PLANNER_SYSTEM_PROMPT:
            raise RuntimeError("CM-57P6 received unexpected production planner prompt.")
        forwarded = replace(request, system_prompt=p5.RC_PROMPT)
        self.forwarded_requests.append(forwarded)
        self.forwarded_response_models.append(response_model)
        return await self.delegate.generate_structured(forwarded, response_model=response_model)

    async def generate_program(self, request: object) -> object:
        """Reject accidental worker/program execution."""
        raise AssertionError(f"CM-57P6 must not call program generation: {request!r}")


@dataclass
class SchemaPromptBackend(PromptBackend):
    """Apply RC prompt substitution and RCS response-model substitution."""

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Convert only successful experimental responses back to production."""
        if response_model is not SemanticPlan:
            raise RuntimeError("CM-57P6 RCS expected the production SemanticPlan request.")
        if request.system_prompt != _PLANNER_SYSTEM_PROMPT:
            raise RuntimeError("CM-57P6 received unexpected production planner prompt.")
        forwarded = replace(request, system_prompt=p5.RC_PROMPT)
        self.forwarded_requests.append(forwarded)
        self.forwarded_response_models.append(NonEmptyReportSemanticPlan)
        result = await self.delegate.generate_structured(
            forwarded,
            response_model=NonEmptyReportSemanticPlan,
        )
        converted = SemanticPlan.model_validate(result.value.model_dump())
        return StructuredGenerationResult(value=converted, metrics=result.metrics)


@dataclass
class RecordingBackend(ModelBackendProtocol):
    """Record bounded calls and outcomes without retaining provider prose."""

    delegate: ModelBackendProtocol
    response_schema_sha256: str
    calls: list[dict[str, object]]
    plans: list[tuple[str, SemanticPlan]]
    program_calls: int = 0

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Record call kind, schema, outcome, and bounded plan facts."""
        if not self.calls:
            call_kind = "INITIAL"
        elif "Correction context:" in request.user_prompt:
            call_kind = "SEMANTIC_CORRECTION"
        else:
            call_kind = "INVALID_RESPONSE_RETRY"
        record: dict[str, object] = {
            "call_kind": call_kind,
            "response_schema_sha256": self.response_schema_sha256,
        }
        if call_kind == "SEMANTIC_CORRECTION":
            record["diagnostic_code"] = (
                "empty_report_capabilities"
                if "empty_report_capabilities" in request.user_prompt
                else "other"
            )
        try:
            result = await self.delegate.generate_structured(
                request,
                response_model=response_model,
            )
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
            record["plan"] = p5._plan_projection(result.value)
        record["metrics"] = result.metrics.public_metadata()
        self.calls.append(record)
        return result

    async def generate_program(self, request: object) -> object:
        """Fail if the planner diagnostic reaches a worker."""
        self.program_calls += 1
        raise AssertionError(f"CM-57P6 must not call program generation: {request!r}")


def _provider_classification(error: ProviderRequestError) -> str:
    """Map provider categories to bounded evidence classes."""
    if error.category in {
        ProviderFailureCategory.INVALID_RESPONSE,
        ProviderFailureCategory.VALIDATION,
    }:
        return "PLANNER_SCHEMA_FAILURE"
    return "PROVIDER_INFRA_FAILURE"


def _run_planner_for_arm(
    arm: Arm,
    backend: RecordingBackend,
    registry: CapabilityRegistry,
) -> SemanticPlanner | InvariantSemanticPlanner:
    """Construct one arm's planner while keeping production flow isolated."""
    if arm == "RCV":
        return InvariantSemanticPlanner(backend=backend, registry=registry)
    return SemanticPlanner(backend=backend, registry=registry)


async def run_arm(
    case: dict[str, object],
    *,
    arm: Arm,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
) -> dict[str, object]:
    """Run one RC, RCV, or RCS planner arm."""
    calls: list[dict[str, object]] = []
    plans: list[tuple[str, SemanticPlan]] = []
    forwarded_requests: list[StructuredGenerationRequest] = []
    forwarded_response_models: list[type[BaseModel]] = []
    if arm == "RCS":
        prompt_backend: ModelBackendProtocol = SchemaPromptBackend(
            delegate=delegate,
            forwarded_requests=forwarded_requests,
            forwarded_response_models=forwarded_response_models,
        )
    else:
        prompt_backend = PromptBackend(
            delegate=delegate,
            forwarded_requests=forwarded_requests,
            forwarded_response_models=forwarded_response_models,
        )
    recorder = RecordingBackend(
        delegate=prompt_backend,
        response_schema_sha256=schema_sha256(_response_schema_for_arm(arm)),
        calls=calls,
        plans=plans,
    )
    planner = _run_planner_for_arm(arm, recorder, registry)
    final_plan: SemanticPlan | None = None
    error_type: str | None = None
    error_code: str | None = None
    final_classification: str | None = None
    provider_infrastructure_failure = False
    try:
        final_plan = await planner.plan(
            request=str(case["request"]),
            mode="reconstruct",
            current_document_summary={},
            source_summary=p5.FIXED_SOURCE_SUMMARY,
            timeout_seconds=TIMEOUT_SECONDS,
            temperature=PLANNER_TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
    except ProviderRequestError as error:
        error_type = "ProviderRequestError"
        error_code = error.category.value
        final_classification = _provider_classification(error)
        provider_infrastructure_failure = final_classification == "PROVIDER_INFRA_FAILURE"
    except PlannerSemanticFailure as error:
        error_type = "PlannerSemanticFailure"
        error_code = error.code
        final_classification = "PLANNER_SEMANTIC_FAILURE"
    except ValidationError:
        error_type = "ValidationError"
        final_classification = "PLANNER_SCHEMA_FAILURE"
    initial_plan = next((plan for kind, plan in plans if kind == "INITIAL"), None)
    initial_facts = p5._facts(initial_plan, case, registry) if initial_plan else None
    final_facts = p5._facts(final_plan, case, registry) if final_plan else None
    if final_plan is not None:
        final_classification = p5.classify_facts(final_facts or {})
    if final_classification is None:
        raise AssertionError("CM-57P6 planner arm ended without a terminal result.")
    return {
        "arm": arm,
        "prompt_sha256": _prompt_sha256(),
        "provider_calls": len(calls),
        "program_calls": recorder.program_calls,
        "response_schema_sha256": schema_sha256(_response_schema_for_arm(arm)),
        "call_trace": calls,
        "initial_plan_available": initial_plan is not None,
        "initial_work_unit_facts": initial_facts,
        "invalid_response_retry_used": any(
            call.get("call_kind") == "INVALID_RESPONSE_RETRY" for call in calls
        ),
        "semantic_correction_used": any(
            call.get("call_kind") == "SEMANTIC_CORRECTION" for call in calls
        ),
        "new_invariant_diagnostic_used": sum(
            call.get("diagnostic_code") == "empty_report_capabilities" for call in calls
        ),
        "schema_validation_failures": sum(
            call.get("outcome") == "structured_output_failure"
            or (
                call.get("outcome") == "provider_failure"
                and call.get("provider_category")
                in {
                    ProviderFailureCategory.INVALID_RESPONSE.value,
                    ProviderFailureCategory.VALIDATION.value,
                }
            )
            for call in calls
        ),
        "terminal_schema_failure": final_classification == "PLANNER_SCHEMA_FAILURE",
        "final_planner_success": final_plan is not None,
        "final_error_type": error_type,
        "final_error_code": error_code,
        "final_work_unit_facts": final_facts,
        "final_classification": final_classification,
        "final_contract_ok": final_plan is not None and p5.final_contract_ok(final_facts or {}),
        "provider_infrastructure_failure": provider_infrastructure_failure,
        "final_plan": p5._plan_projection(final_plan) if final_plan else None,
    }


def _historical_status(entry: dict[str, object]) -> dict[str, object]:
    """Return the bounded manifest status projection."""
    status = entry["historical_rc_status"]
    return status if isinstance(status, dict) else {}


def _rc_matches_historical_status(
    row: dict[str, object], historical_status: dict[str, object]
) -> bool:
    """Require contemporaneous RC to reproduce its manifest baseline state."""
    rc_arm = _arm(row, "RC")
    facts = _facts(row, "RC")
    if facts is None or not rc_arm.get("final_planner_success"):
        return False
    if rc_arm.get("final_classification") != historical_status.get("final_classification"):
        return False
    if facts.get("report_task_present") != historical_status.get("report_task_present"):
        return False
    if facts.get("report_capability_ids") != historical_status.get("report_capability_ids"):
        return False
    return not (
        historical_status.get("final_classification") == "PLANNER_CONTRACT_OK"
        and not rc_arm.get("final_contract_ok")
    )


async def run_shared_row(
    case: dict[str, object],
    entry: dict[str, object],
    *,
    attempt_index: int,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
    authorized_checkpoint: str | None,
) -> dict[str, object]:
    """Run RC, RCV, and RCS against one shared request/context."""
    role = str(entry["role"])
    return {
        **frozen_provenance(),
        "authorized_checkpoint": authorized_checkpoint,
        "case_id": case["case_id"],
        "role": role,
        "attempt_index": attempt_index,
        "request_sha256": sha256_text(str(case["request"])),
        "historical_rc_status": _historical_status(entry),
        "arms": {
            arm: await run_arm(
                case,
                arm=arm,  # type: ignore[arg-type]
                delegate=delegate,
                registry=registry,
            )
            for arm in ARMS
        },
    }


def _arm(row: dict[str, object], arm: str) -> dict[str, object]:
    """Return one bounded arm result."""
    arms = row.get("arms")
    value = arms.get(arm) if isinstance(arms, dict) else None
    return value if isinstance(value, dict) else {}


def _facts(row: dict[str, object], arm: str) -> dict[str, object] | None:
    """Return final facts only when an arm completed semantically."""
    facts = _arm(row, arm).get("final_work_unit_facts")
    return facts if isinstance(facts, dict) else None


def _candidate_recovered(row: dict[str, object], arm: str) -> bool:
    """Return whether a target row recovered its exact P5 contract."""
    facts = _facts(row, arm)
    return bool(
        _arm(row, arm).get("final_planner_success")
        and facts
        and _arm(row, arm).get("final_contract_ok")
        and facts.get("report_task_present")
        and facts.get("report_capability_ids") == ["report.standard"]
    )


def _is_available(row: dict[str, object], arm: str) -> bool:
    """Return whether final semantic facts are available for an arm."""
    return _facts(row, arm) is not None


def _transition_table(
    rows: list[dict[str, object]], left: str, right: str, field: str
) -> dict[str, int]:
    """Compare one semantic fact with terminal outcomes kept unavailable."""
    counts = Counter(
        {
            "CORRECT_TO_CORRECT": 0,
            "CORRECT_TO_WRONG": 0,
            "WRONG_TO_CORRECT": 0,
            "WRONG_TO_WRONG": 0,
            "UNAVAILABLE": 0,
        }
    )
    for row in rows:
        left_facts = _facts(row, left)
        right_facts = _facts(row, right)
        if left_facts is None or right_facts is None:
            counts["UNAVAILABLE"] += 1
            continue
        left_correct = bool(left_facts.get(field))
        right_correct = bool(right_facts.get(field))
        counts[
            ("CORRECT" if left_correct else "WRONG")
            + "_TO_"
            + ("CORRECT" if right_correct else "WRONG")
        ] += 1
    return dict(counts)


def _full_contract_table(rows: list[dict[str, object]], left: str, right: str) -> dict[str, int]:
    """Count paired final contract outcomes."""
    counts = Counter({"BOTH_PASS": 0, "LEFT_ONLY_PASS": 0, "RIGHT_ONLY_PASS": 0, "BOTH_FAIL": 0})
    for row in rows:
        left_pass = bool(_arm(row, left).get("final_contract_ok"))
        right_pass = bool(_arm(row, right).get("final_contract_ok"))
        if left_pass and right_pass:
            counts["BOTH_PASS"] += 1
        elif left_pass:
            counts["LEFT_ONLY_PASS"] += 1
        elif right_pass:
            counts["RIGHT_ONLY_PASS"] += 1
        else:
            counts["BOTH_FAIL"] += 1
    return dict(counts)


def _arm_metrics(rows: list[dict[str, object]], arm: str) -> dict[str, int]:
    """Aggregate bounded provider and planner metrics."""
    results = [_arm(row, arm) for row in rows]
    return {
        "planner_executions": len(results),
        "provider_calls": sum(int(result.get("provider_calls", 0)) for result in results),
        "initial_passes": sum(
            bool(result.get("initial_work_unit_facts"))
            and p5.final_contract_ok(result["initial_work_unit_facts"])
            for result in results
        ),
        "final_passes": sum(bool(result.get("final_contract_ok")) for result in results),
        "semantic_corrections": sum(
            bool(result.get("semantic_correction_used")) for result in results
        ),
        "new_invariant_diagnostics": sum(
            int(result.get("new_invariant_diagnostic_used", 0)) for result in results
        ),
        "invalid_response_retries": sum(
            bool(result.get("invalid_response_retry_used")) for result in results
        ),
        "schema_validation_failures": sum(
            int(result.get("schema_validation_failures", 0)) for result in results
        ),
        "terminal_failures": sum(
            not bool(result.get("final_planner_success")) for result in results
        ),
        "infrastructure_failures": sum(
            bool(result.get("provider_infrastructure_failure")) for result in results
        ),
        "program_calls": sum(int(result.get("program_calls", 0)) for result in results),
    }


def _repeatability(rows: list[dict[str, object]]) -> dict[str, dict[str, int]]:
    """Count stable, unstable, and unavailable case pairs per arm."""
    output: dict[str, dict[str, int]] = {}
    for arm in ARMS:
        stable = unstable = unavailable = 0
        for case_id in {str(row["case_id"]) for row in rows}:
            case_rows = sorted(
                (row for row in rows if str(row["case_id"]) == case_id),
                key=lambda row: int(row["attempt_index"]),
            )
            facts = [_facts(row, arm) for row in case_rows]
            if len(facts) != ATTEMPTS or any(fact is None for fact in facts):
                unavailable += 1
            elif facts[0] == facts[1]:
                stable += 1
            else:
                unstable += 1
        output[arm] = {"stable": stable, "unstable": unstable, "unavailable": unavailable}
    return output


def _target_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return the six target rows."""
    return [row for row in rows if row.get("role") == ROLE_TARGET]


def _control_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return the ten report-pass control rows."""
    return [row for row in rows if row.get("role") == ROLE_REPORT_CONTROL]


def _target_pair_table(rows: list[dict[str, object]], candidate: str) -> dict[str, int]:
    """Classify target baseline and candidate transitions."""
    counts = Counter(
        {
            "EMPTY_FAIL_TO_PASS": 0,
            "EMPTY_FAIL_TO_EMPTY_FAIL": 0,
            "EMPTY_FAIL_TO_OTHER_FAIL": 0,
            "UNEXPECTED_BASELINE_STATE": 0,
        }
    )
    for row in rows:
        rc_facts = _facts(row, "RC")
        rc_empty = bool(
            rc_facts
            and rc_facts.get("report_task_present")
            and rc_facts.get("report_capability_ids") == []
            and _arm(row, "RC").get("final_classification") == "REPORT_CAPABILITY_MISMATCH"
        )
        if not rc_empty:
            counts["UNEXPECTED_BASELINE_STATE"] += 1
        elif _candidate_recovered(row, candidate):
            counts["EMPTY_FAIL_TO_PASS"] += 1
        elif (
            _facts(row, candidate) is not None
            and _facts(row, candidate).get("report_task_present")
            and _facts(row, candidate).get("report_capability_ids") == []
        ):
            counts["EMPTY_FAIL_TO_EMPTY_FAIL"] += 1
        else:
            counts["EMPTY_FAIL_TO_OTHER_FAIL"] += 1
    return dict(counts)


def _control_regressions(rows: list[dict[str, object]], candidate: str) -> int:
    """Count RC-pass rows lost by one candidate."""
    return sum(
        bool(_arm(row, "RC").get("final_contract_ok"))
        and not bool(_arm(row, candidate).get("final_contract_ok"))
        for row in rows
    )


def _target_recoveries(rows: list[dict[str, object]], candidate: str) -> int:
    """Count recovered target rows."""
    return sum(_candidate_recovered(row, candidate) for row in rows)


def _candidate_viable(rows: list[dict[str, object]], candidate: str) -> bool:
    """Apply the frozen full-viability rule to one candidate."""
    target_rows = _target_rows(rows)
    result_rows = [_arm(row, candidate) for row in rows]
    schema_collapse = candidate == "RCS" and all(
        result.get("schema_validation_failures", 0) > 0 and not result.get("final_planner_success")
        for result in result_rows
    )
    return bool(
        _target_recoveries(target_rows, candidate) == 6
        and sum(
            bool(
                _facts(row, candidate)
                and _facts(row, candidate).get("report_task_present")
                and _facts(row, candidate).get("report_capability_ids") == []
            )
            for row in target_rows
        )
        == 0
        and _control_regressions(rows, candidate) == 0
        and not any(result.get("provider_infrastructure_failure") for result in result_rows)
        and not any(not result.get("final_planner_success") for result in result_rows)
        and not schema_collapse
    )


def decision(rows: list[dict[str, object]], *, expected_checkpoint: str | None = None) -> str:
    """Apply the frozen P6 decision precedence."""
    complete, reasons = population_integrity(rows, expected_checkpoint=expected_checkpoint)
    if not complete or any(
        bool(_arm(row, arm).get("provider_infrastructure_failure")) for row in rows for arm in ARMS
    ):
        return "INCONCLUSIVE_REPORT_INVARIANT_BISECT"
    if "target_baseline_not_reproduced" in reasons:
        return "INCONCLUSIVE_REPORT_INVARIANT_BISECT"
    rcv_viable = _candidate_viable(rows, "RCV")
    rcs_viable = _candidate_viable(rows, "RCS")
    if rcv_viable and rcs_viable:
        return "REPORT_INVARIANT_BOTH_VALIDATED"
    if rcs_viable:
        return "REPORT_INVARIANT_SCHEMA_VALIDATED"
    if rcv_viable:
        return "REPORT_INVARIANT_VALIDATOR_VALIDATED"
    recoveries = max(
        _target_recoveries(_target_rows(rows), "RCV"), _target_recoveries(_target_rows(rows), "RCS")
    )
    if (
        recoveries
        and recoveries < 6
        and all(_control_regressions(rows, arm) == 0 for arm in ("RCV", "RCS"))
    ):
        return "REPORT_INVARIANT_PARTIAL_RECOVERY"
    if recoveries == 0 and all(_control_regressions(rows, arm) == 0 for arm in ("RCV", "RCS")):
        return "REPORT_INVARIANT_NO_RECOVERY"
    return "REPORT_INVARIANT_REGRESSION"


def population_integrity(
    rows: list[dict[str, object]], *, expected_checkpoint: str | None = None
) -> tuple[bool, list[str]]:
    """Validate exact P6 row shape, anchors, and target reproduction."""
    reasons: list[str] = []
    manifest = load_manifest()
    expected_ids = {str(entry["case_id"]) for entry in manifest}
    if len(rows) != 24:
        reasons.append("wrong_row_count")
    pairs = [(str(row.get("case_id")), row.get("attempt_index")) for row in rows]
    if len(set(pairs)) != len(pairs):
        reasons.append("duplicate_case_attempt")
    if {case_id for case_id, _ in pairs} != expected_ids:
        reasons.append("case_set_mismatch")
    if any(attempts != {0, 1} for attempts in _attempts_by_case(pairs).values()):
        reasons.append("attempt_index_mismatch")
    checkpoints = {row.get("authorized_checkpoint") for row in rows}
    if len(checkpoints) != 1 or None in checkpoints:
        reasons.append("checkpoint_missing_or_mixed")
    elif expected_checkpoint is not None and checkpoints != {expected_checkpoint}:
        reasons.append("checkpoint_mismatch")
    expected_provenance = frozen_provenance()
    expected_by_id = {str(entry["case_id"]): entry for entry in manifest}
    for row in rows:
        case_id = str(row.get("case_id"))
        entry = expected_by_id.get(case_id)
        if entry is None:
            continue
        if (
            row.get("role") != entry["role"]
            or row.get("historical_rc_status") != entry["historical_rc_status"]
        ):
            reasons.append("manifest_status_mismatch")
        if not isinstance(row.get("arms"), dict) or set(row["arms"]) != set(ARMS):
            reasons.append("arm_set_mismatch")
        for field_name in (
            "experiment_version",
            "design_baseline_sha",
            "harness_sha256",
            "manifest_sha256",
            "p5_summary_sha256",
            "p5_raw_sha256",
            "p5_corpus_sha256",
            "p5_script_sha256",
            "planner_source_sha256",
            "catalog_sha256",
            "base_prompt_sha256",
            "RC_prompt_sha256",
            "source_summary_sha256",
        ):
            if row.get(field_name) != expected_provenance[field_name]:
                reasons.append(f"{field_name}_mismatch")
        for field_name in ("production_schema_sha256", "nonempty_report_schema_sha256"):
            if row.get(field_name) != expected_provenance[field_name]:
                reasons.append(f"{field_name}_mismatch")
        if row.get("execution_controls") != expected_provenance["execution_controls"]:
            reasons.append("execution_controls_mismatch")
        if row.get("request_sha256") != sha256_text(str(_case_by_id()[case_id]["request"])):
            reasons.append("request_hash_mismatch")
        for arm in ARMS:
            if _arm(row, arm).get("prompt_sha256") != EXPECTED_RC_PROMPT_SHA256:
                reasons.append(f"{arm}_prompt_mismatch")
            if (
                _arm(row, arm).get("response_schema_sha256")
                != expected_provenance[
                    "production_schema_sha256" if arm != "RCS" else "nonempty_report_schema_sha256"
                ]
            ):
                reasons.append(f"{arm}_schema_mismatch")
        if not _rc_matches_historical_status(row, entry["historical_rc_status"]):
            reasons.append("rc_baseline_not_reproduced")
    target_rows = [row for row in rows if row.get("role") == ROLE_TARGET]
    for row in target_rows:
        rc_facts = _facts(row, "RC")
        if not (
            _arm(row, "RC").get("final_planner_success")
            and rc_facts
            and rc_facts.get("report_task_present")
            and rc_facts.get("report_capability_ids") == []
            and _arm(row, "RC").get("final_classification") == "REPORT_CAPABILITY_MISMATCH"
            and not _arm(row, "RC").get("semantic_correction_used")
        ):
            reasons.append("target_baseline_not_reproduced")
    return not reasons, sorted(set(reasons))


def _attempts_by_case(pairs: list[tuple[str, object]]) -> dict[str, set[object]]:
    """Group attempt indices by case ID."""
    grouped: dict[str, set[object]] = {}
    for case_id, attempt in pairs:
        grouped.setdefault(case_id, set()).add(attempt)
    return grouped


def summarize_population(
    rows: list[dict[str, object]], *, authorized_checkpoint: str
) -> dict[str, object]:
    """Build bounded P6 aggregate evidence."""
    manifest = load_manifest()
    complete, reasons = population_integrity(rows, expected_checkpoint=authorized_checkpoint)
    cases = _case_by_id()
    target_rows = _target_rows(rows)
    report_rows = _control_rows(rows)
    sentinel_rows = [row for row in rows if row.get("role") == ROLE_SECTION_SENTINEL]
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "authorized_checkpoint": authorized_checkpoint,
        "population": {
            "expected_rows": 24,
            "actual_rows": len(rows),
            "cases": len(manifest),
            "attempts_per_case": ATTEMPTS,
            "arms_per_row": len(ARMS),
            "complete": complete,
            "reasons": reasons,
        },
        "decision": decision(rows, expected_checkpoint=authorized_checkpoint),
        "arm_metrics": {arm: _arm_metrics(rows, arm) for arm in ARMS},
        "target_metrics": {
            arm: {
                "initial_passes": sum(
                    bool(_arm(row, arm).get("initial_work_unit_facts"))
                    and p5.final_contract_ok(_arm(row, arm)["initial_work_unit_facts"])
                    for row in target_rows
                ),
                "final_passes": sum(
                    bool(_arm(row, arm).get("final_contract_ok")) for row in target_rows
                ),
                "empty_report_final": sum(
                    bool((_facts(row, arm) or {}).get("report_task_present"))
                    and (_facts(row, arm) or {}).get("report_capability_ids") == []
                    for row in target_rows
                ),
                "recoveries": _target_recoveries(target_rows, arm),
                "provider_calls": sum(
                    int(_arm(row, arm).get("provider_calls", 0)) for row in target_rows
                ),
            }
            for arm in ARMS
        },
        "report_control_metrics": {
            arm: {
                "final_passes": sum(
                    bool(_arm(row, arm).get("final_contract_ok")) for row in report_rows
                ),
                "rc_to_candidate_regressions": _control_regressions(report_rows, arm)
                if arm != "RC"
                else 0,
            }
            for arm in ARMS
        },
        "section_sentinel_metrics": {
            str(row["case_id"]): {arm: _arm(row, arm).get("final_classification") for arm in ARMS}
            for row in sentinel_rows
        },
        "pair_tables": {
            "RC_to_RCV": _full_contract_table(rows, "RC", "RCV"),
            "RC_to_RCS": _full_contract_table(rows, "RC", "RCS"),
            "RCV_to_RCS": _full_contract_table(rows, "RCV", "RCS"),
            "RC_to_RCV_report_capabilities": _transition_table(
                rows, "RC", "RCV", "report_capabilities_exact"
            ),
            "RC_to_RCS_report_capabilities": _transition_table(
                rows, "RC", "RCS", "report_capabilities_exact"
            ),
        },
        "target_pair_tables": {
            "RC_to_RCV": _target_pair_table(target_rows, "RCV"),
            "RC_to_RCS": _target_pair_table(target_rows, "RCS"),
        },
        "repeatability": _repeatability(rows),
        "control_regressions": {
            "RC_to_RCV": _control_regressions(rows, "RCV"),
            "RC_to_RCS": _control_regressions(rows, "RCS"),
        },
        "schema_hashes": {
            "production": schema_sha256(SemanticPlan),
            "nonempty_report": schema_sha256(NonEmptyReportSemanticPlan),
        },
        "controls": dict(FIXED_EXECUTION_CONTROLS),
        "case_count_by_role": dict(Counter(str(entry["role"]) for entry in manifest)),
        "unused_case_ids": sorted(set(cases) - {str(entry["case_id"]) for entry in manifest}),
    }


def verify_reviewed_checkout(checkpoint: str) -> None:
    """Require the future live checkout and guarded bytes to match review."""
    if CHECKPOINT_RE.fullmatch(checkpoint) is None:
        raise ValueError("CM-57P6 requires a full lowercase checkpoint SHA.")
    if current_checkout_sha() != checkpoint:
        raise RuntimeError("CM-57P6 checkout does not match its authorized checkpoint.")
    guarded = (
        "scripts/cm57p6_report_invariant_bisect.py",
        "tests/fixtures/typed_worker/cm57p6_report_invariant_cases.json",
        "scripts/cm57p5_fresh_holdout.py",
        "tests/fixtures/typed_worker/cm57p5_fresh_holdout.json",
        "docs/evaluations/agent-code-mode/CM-57P5-live-summary.json",
        "src/wellplot/agent/code_mode/planner.py",
        "src/wellplot/agent/providers/base.py",
        "src/wellplot/capabilities/base.py",
        "src/wellplot/capabilities/registry.py",
        "src/wellplot/capabilities/builtins.py",
    )
    for relative_path in guarded:
        path = REPO_ROOT / relative_path
        if path.read_bytes() != _git_output("show", f"{checkpoint}:{relative_path}"):
            raise RuntimeError(f"CM-57P6 guarded artifact drifted: {relative_path}")


def verify_frozen_contract() -> dict[str, object]:
    """Verify all P5/P6 anchors before provider construction."""
    manifest = load_manifest()
    if artifact_sha256(CASE_PATH) != EXPECTED_P5_CORPUS_SHA256:
        raise RuntimeError("CM-57P5 corpus bytes drifted.")
    if artifact_sha256(P5_SCRIPT_PATH) != EXPECTED_P5_SCRIPT_SHA256:
        raise RuntimeError("CM-57P5 harness bytes drifted.")
    if artifact_sha256(P5_SUMMARY_PATH) != EXPECTED_P5_SUMMARY_SHA256:
        raise RuntimeError("CM-57P5 summary bytes drifted.")
    if not P5_RAW_PATH.exists() or artifact_sha256(P5_RAW_PATH) != EXPECTED_P5_RAW_SHA256:
        raise RuntimeError("CM-57P5 raw evidence bytes drifted or are unavailable.")
    p5_summary = json.loads(P5_SUMMARY_PATH.read_text(encoding="utf-8"))
    if (
        p5_summary.get("decision") != "HOLDOUT_GENERALIZATION_REGRESSION"
        or p5_summary.get("authorized_checkpoint") != P5_CHECKPOINT
        or p5_summary.get("raw_evidence", {}).get("sha256") != EXPECTED_P5_RAW_SHA256
        or p5_summary.get("raw_evidence", {}).get("rows") != 48
    ):
        raise RuntimeError("CM-57P5 live evidence anchor drifted.")
    if _fixed_source_summary_sha() != EXPECTED_SOURCE_SUMMARY_SHA256:
        raise RuntimeError("CM-57P5 source summary drifted.")
    if sha256_text(_PLANNER_SYSTEM_PROMPT) != EXPECTED_BASE_PROMPT_SHA256:
        raise RuntimeError("Production planner prompt drifted.")
    if _prompt_sha256() != EXPECTED_RC_PROMPT_SHA256:
        raise RuntimeError("RC prompt drifted.")
    if artifact_sha256(MANIFEST_PATH) != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("CM-57P6 manifest bytes drifted.")
    if artifact_sha256(CASE_PATH) != p5.EXPECTED_HOLDOUT_SHA256:
        raise RuntimeError("P5 holdout anchor differs from its own frozen hash.")
    if (
        artifact_sha256(REPO_ROOT / "src/wellplot/agent/code_mode/planner.py")
        != EXPECTED_PLANNER_SOURCE_SHA256
    ):
        raise RuntimeError("Production planner bytes drifted.")
    if _catalog_sha256() != EXPECTED_CATALOG_SHA256:
        raise RuntimeError("Production capability catalogue drifted.")
    actual_controls = {
        "model": FROZEN_MODEL,
        "planner_temperature": PLANNER_TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "max_tokens_parameter": MAX_TOKENS_PARAMETER,
        "timeout_seconds": TIMEOUT_SECONDS,
    }
    if actual_controls != FIXED_EXECUTION_CONTROLS:
        raise RuntimeError("CM-57P6 execution controls drifted.")
    if not schema_diff_isolated():
        raise RuntimeError("CM-57P6 response-schema isolation drifted.")
    if schema_sha256(SemanticPlan) != EXPECTED_PRODUCTION_SCHEMA_SHA256:
        raise RuntimeError("Production response-schema hash drifted.")
    if schema_sha256(NonEmptyReportSemanticPlan) != EXPECTED_NONEMPTY_SCHEMA_SHA256:
        raise RuntimeError("Experimental response-schema hash drifted.")
    return {
        "manifest_cases": len(manifest),
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "p5_summary_sha256": EXPECTED_P5_SUMMARY_SHA256,
        "p5_raw_sha256": EXPECTED_P5_RAW_SHA256,
        "production_schema_sha256": EXPECTED_PRODUCTION_SCHEMA_SHA256,
        "nonempty_report_schema_sha256": EXPECTED_NONEMPTY_SCHEMA_SHA256,
        "source_summary_sha256": EXPECTED_SOURCE_SUMMARY_SHA256,
    }


class DeterministicBackend(ModelBackendProtocol):
    """Provider-free backend for P6 invariant and isolation tests."""

    def __init__(self, responses: list[SemanticPlan | dict[str, object]]) -> None:
        """Store the finite sequence of provider-free responses."""
        self.responses = list(responses)
        self.requests: list[StructuredGenerationRequest] = []
        self.response_models: list[type[BaseModel]] = []

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Return the next configured response through the requested schema."""
        self.requests.append(request)
        self.response_models.append(response_model)
        value = self.responses.pop(0)
        if isinstance(value, BaseModel):
            value = value.model_dump()
        return StructuredGenerationResult(
            value=response_model.model_validate(value),
            metrics=ProviderMetrics(),
        )

    async def generate_program(self, request: object) -> object:
        """Reject accidental worker execution."""
        raise AssertionError(f"CM-57P6 must not call program generation: {request!r}")


def _empty_report_plan() -> SemanticPlan:
    """Build the historical invalid report work unit."""
    return SemanticPlan(
        summary="empty report",
        report_task=ReportTask(goal="report", capability_ids=()),
    )


def _valid_report_plan() -> SemanticPlan:
    """Build the corrected report work unit."""
    return SemanticPlan(
        summary="report",
        report_task=ReportTask(goal="report", capability_ids=("report.standard",)),
    )


def _valid_section_plan() -> SemanticPlan:
    """Build a valid section-only plan."""
    return SemanticPlan(
        summary="section",
        section_tasks=(
            SectionTask(
                goal="one section",
                capability_ids=("section.log_plot", "track.normal", "binding.curve"),
            ),
        ),
    )


def _run_provider_free_self_tests() -> None:
    """Exercise the invariant, schema, and exact-control boundaries."""
    registry = create_builtin_registry()
    assert schema_diff_isolated()
    SemanticPlan.model_validate({"summary": "empty", "report_task": {"goal": "report"}})
    with _expect_validation_error():
        NonEmptyReportSemanticPlan.model_validate(
            {"summary": "empty", "report_task": {"goal": "report", "capability_ids": []}}
        )
    assert NonEmptyReportSemanticPlan.model_validate(_valid_section_plan().model_dump())
    assert NonEmptyReportSemanticPlan.model_validate(
        {
            "summary": "report",
            "report_task": {"goal": "report", "capability_ids": ["report.standard"]},
        }
    )

    assert validate_semantic_plan_nonempty_report(_valid_section_plan(), registry)
    assert validate_semantic_plan_nonempty_report(_valid_report_plan(), registry)
    with _expect_planner_error("empty_report_capabilities"):
        validate_semantic_plan_nonempty_report(_empty_report_plan(), registry)

    backend = DeterministicBackend([_empty_report_plan(), _valid_report_plan()])
    planner = InvariantSemanticPlanner(backend=backend, registry=registry)
    asyncio.run(
        planner.plan(
            request="Prepare a report.",
            mode="reconstruct",
            source_summary=p5.FIXED_SOURCE_SUMMARY,
            timeout_seconds=TIMEOUT_SECONDS,
            temperature=PLANNER_TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
    )
    assert len(backend.requests) == 2
    assert backend.response_models == [SemanticPlan, SemanticPlan]
    assert "empty_report_capabilities" in backend.requests[1].user_prompt

    failure_backend = DeterministicBackend([_empty_report_plan(), _empty_report_plan()])
    failure_planner = InvariantSemanticPlanner(backend=failure_backend, registry=registry)
    with _expect_planner_failure("empty_report_capabilities"):
        asyncio.run(
            failure_planner.plan(
                request="Prepare a report.",
                mode="reconstruct",
                timeout_seconds=TIMEOUT_SECONDS,
                temperature=PLANNER_TEMPERATURE,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )
        )
    assert len(failure_backend.requests) == 2

    for plan in (_valid_section_plan(), _valid_report_plan()):
        control_backend = DeterministicBackend([plan])
        candidate_backend = DeterministicBackend([plan])
        control = PromptBackend(control_backend, [], [])
        candidate = PromptBackend(candidate_backend, [], [])
        asyncio.run(
            SemanticPlanner(backend=control, registry=registry).plan(
                request="same", mode="reconstruct", timeout_seconds=1.0
            )
        )
        asyncio.run(
            InvariantSemanticPlanner(backend=candidate, registry=registry).plan(
                request="same", mode="reconstruct", timeout_seconds=1.0
            )
        )
        assert control_backend.requests == candidate_backend.requests
        assert control_backend.response_models == candidate_backend.response_models

    schema_backend = DeterministicBackend([_valid_report_plan()])
    schema_wrapper = SchemaPromptBackend(schema_backend, [], [])
    result = asyncio.run(
        SemanticPlanner(backend=schema_wrapper, registry=registry).plan(
            request="same", mode="reconstruct", timeout_seconds=1.0
        )
    )
    assert result == _valid_report_plan()
    assert schema_backend.response_models == [NonEmptyReportSemanticPlan]


class _expect_validation_error:
    """Tiny provider-free context manager for schema tests."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        return exc_type is ValidationError


class _expect_planner_error:
    """Tiny provider-free context manager for semantic invariant tests."""

    def __init__(self, code: str) -> None:
        self.code = code

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        return isinstance(exc_value, PlannerSemanticError) and exc_value.code == self.code


class _expect_planner_failure:
    """Tiny provider-free context manager for bounded failure tests."""

    def __init__(self, code: str) -> None:
        self.code = code

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        return isinstance(exc_value, PlannerSemanticFailure) and exc_value.code == self.code


def prelive_report() -> dict[str, object]:
    """Run all provider-free P6 checks and describe the future matrix."""
    contract = verify_frozen_contract()
    _run_provider_free_self_tests()
    manifest = load_manifest()
    return {
        "status": "PRELIVE_READY",
        "experiment_version": EXPERIMENT_VERSION,
        "baseline_sha": BASELINE_SHA,
        "provider_calls": 0,
        "worker_program_calls": 0,
        "production_changes": 0,
        "live_inference": "NOT_STARTED",
        "production_adoption": "NOT_AUTHORIZED",
        "CM57D": "BLOCKED",
        "arms": list(ARMS),
        "manifest_cases": len(manifest),
        "target_cases": len(TARGET_CASES),
        "report_pass_controls": len(REPORT_CONTROL_CASES),
        "section_sentinels": len(SECTION_SENTINEL_CASES),
        "attempts": ATTEMPTS,
        "shared_rows": 24,
        "planner_executions": 72,
        "provider_calls_min": 72,
        "provider_calls_max": 144,
        "RC_exact_control_isolation": "PASS",
        "RCV_production_equivalence": "PASS",
        "RCS_conversion": "PASS",
        "schema_diff_isolated": "PASS",
        "schema_hashes": {
            "production": schema_sha256(SemanticPlan),
            "nonempty_report": schema_sha256(NonEmptyReportSemanticPlan),
        },
        **contract,
        "live_evidence": "NOT_STARTED",
    }


def _provider_configuration(args: argparse.Namespace) -> ModelBackendProtocol:
    """Construct the provider only after every live guard passes."""
    from openai import AsyncOpenAI

    from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2

    api_key = os.getenv(args.api_key_env, "").strip()
    if args.api_key_file:
        key_path = Path(args.api_key_file)
        if not key_path.is_absolute():
            key_path = REPO_ROOT / key_path
        api_key = api_key or key_path.read_text(encoding="utf-8").strip()
    if not api_key:
        raise RuntimeError("No CM-57P6 API key configured.")
    return OpenAICompatibleBackendV2(
        model=FROZEN_MODEL,
        client=AsyncOpenAI(api_key=api_key, base_url=args.base_url, timeout=TIMEOUT_SECONDS),
        structured_output="json_schema",
        max_tokens_parameter=MAX_TOKENS_PARAMETER,
    )


async def _run_live(args: argparse.Namespace, checkpoint: str) -> None:
    """Run all 24 shared rows once and flush each complete row."""
    if OUTPUT_PATH.exists() and OUTPUT_PATH.stat().st_size:
        raise RuntimeError(f"Refusing to append to non-empty evidence path {OUTPUT_PATH}.")
    verify_reviewed_checkout(checkpoint)
    verify_frozen_contract()
    manifest = load_manifest()
    cases = _case_by_id()
    registry = create_builtin_registry()
    backend = _provider_configuration(args)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("a", encoding="utf-8") as handle:
        for entry in manifest:
            case = cases[str(entry["case_id"])]
            for attempt_index in range(ATTEMPTS):
                row = await run_shared_row(
                    case,
                    entry,
                    attempt_index=attempt_index,
                    delegate=backend,
                    registry=registry,
                    authorized_checkpoint=checkpoint,
                )
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
                handle.flush()
    rows = [json.loads(line) for line in OUTPUT_PATH.read_text(encoding="utf-8").splitlines()]
    print(json.dumps(summarize_population(rows, authorized_checkpoint=checkpoint), indent=2))


def _parser() -> argparse.ArgumentParser:
    """Build provider-free default and explicitly gated live CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-authorized", action="store_true")
    parser.add_argument("--authorized-checkpoint")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="LLAMA_CPP_API_KEY")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run provider-free checks unless explicit live authorization is supplied."""
    args = _parser().parse_args(argv)
    if not args.live_authorized:
        print(json.dumps(prelive_report(), indent=2, sort_keys=True))
        return 0
    if not args.authorized_checkpoint or not args.base_url:
        raise SystemExit("Live CM-57P6 requires --authorized-checkpoint and --base-url.")
    asyncio.run(_run_live(args, args.authorized_checkpoint))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
