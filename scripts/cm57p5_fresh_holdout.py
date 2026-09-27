"""CM-57P5 fresh holdout planner-contract generalization experiment.

The default command performs only provider-free validation. Live execution is
available only behind the explicit authorization flags and is intentionally
limited to planner decomposition evidence.
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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import cm57p2_planner_shadow as p2  # noqa: E402
from scripts import cm57p4_prompt_interaction_bisect as p4  # noqa: E402
from wellplot.agent.code_mode.planner import (  # noqa: E402
    _PLANNER_SYSTEM_PROMPT,
    PlannerSemanticFailure,
    ReportTask,
    SectionTask,
    SemanticPlan,
    SemanticPlanner,
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
P4_SCRIPT_PATH = REPO_ROOT / "scripts/cm57p4_prompt_interaction_bisect.py"
P4_SUMMARY_PATH = REPO_ROOT / "docs/evaluations/agent-code-mode/CM-57P4-live-summary.json"
OUTPUT_PATH = Path("/tmp/cm57p5-fresh-holdout-qwen.jsonl")

BASELINE_SHA = "c39068ccab1b470c7a325649d59f4e9a42114f52"
PREVIOUS_BASELINE_SHA = "f7ffdf1382c0a4f57ee05b11b5cc3af2943d5b4f"
EXPERIMENT_VERSION = "CM-57P5"
CORPUS_VERSION = "cm57p5.holdout.v1"
FROZEN_MODEL = "qwen3.6-35b-a3b"
PLANNER_TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 16384
MAX_TOKENS_PARAMETER = "max_tokens"
TIMEOUT_SECONDS = 900.0
ATTEMPTS = 2
ARMS: tuple[str, ...] = ("P", "RC")
FAMILIES: tuple[str, ...] = (
    "REPORT_ONLY",
    "SINGLE_SECTION",
    "HETEROGENEOUS_SECTION",
    "MULTI_SECTION",
    "MIXED_REPORT_SECTION",
    "CAPABILITY_MULTIPLICITY",
)
Arm = Literal["P", "RC"]

EXPECTED_HOLDOUT_SHA256 = "29e85998481ce9bcc6eab9ecb7959d470cefbf3a84e5273309c6004aacae334d"
EXPECTED_P4_SCRIPT_SHA256 = "fe7684ff610a14151784cd4272b65ba45e91b56c54b3eda2230e4fff6d2a9693"
EXPECTED_P4_SUMMARY_SHA256 = "571c1c98d4043ad174fe8000f2affc5dec93ec1d90a5fffa100d2cc98d51ae0d"
EXPECTED_P4_RAW_SHA256 = "84984fe9903e43396633c87682eb341342f8ac406d296d29dfb47b32b02cd001"
EXPECTED_P4_CHECKPOINT = "c44f163ef605f8d892bf6d114c6a6a3258756ca5"
EXPECTED_PLANNER_SOURCE_SHA256 = "0189b290ef4f76bdd776fe2612c454809ff77725379def7d8c5a98d9ae165413"
EXPECTED_CATALOG_SHA256 = "b1b9c85db961cb8b97f1c8b6f914a6a75f5bf57cf49ca4413c64d35311b80d37"
EXPECTED_BASE_PROMPT_SHA256 = "5e7a0732af01e4b1f16b3ccf019c005ea2e9ba5c0e93e94870a56a261e2bca18"
EXPECTED_R_INSTRUCTION_SHA256 = "12fd2c40e407cb7d5d0e21effd66493e20e99468e3a97b89ac0186b40648c5b5"
EXPECTED_C_INSTRUCTION_SHA256 = "b69c47063b6da13e4f5857609708efe0becc901b989a1a65c503dd277cdc8205"
EXPECTED_RC_PROMPT_SHA256 = "e1710cb516a96c47ec1d0593752e83aacc1bb4502c3026b2b6a9a676c90e4d34"
EXPECTED_SOURCE_SUMMARY_SHA256 = "ec6147a1b5e1ac6374e34ae3d66d11275542c6b340337cb26d3ae1d06240532e"
CHECKPOINT_RE = re.compile(r"^[0-9a-f]{40}$")
PATH_RE = re.compile(r"(?<!\w)(?:[A-Za-z]:[\\/]|/)[^\s,;]+")

REPORT_BOUNDARY_INSTRUCTION = p4.REPORT_BOUNDARY_INSTRUCTION
SECTION_COMPOSITION_INSTRUCTION = p4.SECTION_COMPOSITION_INSTRUCTION
RC_PROMPT = (
    _PLANNER_SYSTEM_PROMPT
    + "\n"
    + REPORT_BOUNDARY_INSTRUCTION
    + "\n"
    + SECTION_COMPOSITION_INSTRUCTION
)

FIXED_SOURCE_SUMMARY: dict[str, object] = {
    "version": "cm56r3.source-summary.v1",
    "sources": [
        {
            "labels": ["combined pack", "combined"],
            "channels": [],
        }
    ],
}

FROZEN_EXECUTION_CONTROLS = {
    "model": FROZEN_MODEL,
    "planner_temperature": PLANNER_TEMPERATURE,
    "max_output_tokens": MAX_OUTPUT_TOKENS,
    "max_tokens_parameter": MAX_TOKENS_PARAMETER,
    "timeout_seconds": TIMEOUT_SECONDS,
}

FORBIDDEN_REQUEST_TERMS = (
    "SectionTask",
    "ReportTask",
    "capability_ids",
    "expected_sections",
    "expected_report_capabilities",
)
CAPABILITY_IDS = (
    "report.standard",
    "section.log_plot",
    "track.normal",
    "track.reference",
    "track.array",
    "binding.curve",
    "binding.raster",
)


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


def _fixed_source_summary_sha() -> str:
    """Return the frozen hash for the one production-safe source summary."""
    return sha256_text(canonical_json(FIXED_SOURCE_SUMMARY))


def composed_prompt(arm: Arm) -> str:
    """Return the exact production or frozen RC planner prompt."""
    if arm == "P":
        return _PLANNER_SYSTEM_PROMPT
    return RC_PROMPT


def frozen_population_provenance() -> dict[str, object]:
    """Return exact provenance values placed on every future live row."""
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "design_baseline_sha": BASELINE_SHA,
        "harness_sha256": artifact_sha256(Path(__file__)),
        "corpus_sha256": artifact_sha256(CASE_PATH),
        "planner_source_sha256": artifact_sha256(
            REPO_ROOT / "src/wellplot/agent/code_mode/planner.py"
        ),
        "catalog_sha256": _catalog_sha256(),
        "base_prompt_sha256": sha256_text(_PLANNER_SYSTEM_PROMPT),
        "report_instruction_sha256": sha256_text(REPORT_BOUNDARY_INSTRUCTION),
        "section_composition_instruction_sha256": sha256_text(SECTION_COMPOSITION_INSTRUCTION),
        "RC_prompt_sha256": sha256_text(RC_PROMPT),
        "source_summary_sha256": _fixed_source_summary_sha(),
        "execution_controls": dict(FROZEN_EXECUTION_CONTROLS),
    }


def _catalog_sha256() -> str:
    """Hash the production planner catalogue projection."""
    return sha256_text(canonical_json(_planning_catalog()))


def _planning_catalog() -> tuple[dict[str, object], ...]:
    """Return the current production planning catalogue."""
    return p2._planning_catalog(create_builtin_registry())


def _registry_ids(registry: CapabilityRegistry) -> set[str]:
    """Return canonical IDs from a registry without widening its API."""
    return {spec.capability_id for spec in registry}


def _parent_closure_ids(capability_ids: list[str], registry: CapabilityRegistry) -> bool:
    """Check selected parent closure without adding or repairing IDs."""
    selected = set(capability_ids)
    try:
        specs = [registry.get(value) for value in capability_ids]
    except KeyError:
        return False
    return all(
        not spec.allowed_parents or selected.intersection(spec.allowed_parents) for spec in specs
    )


def _cm57c_request_hashes() -> set[str]:
    """Return request hashes from the frozen CM-57C corpus."""
    path = REPO_ROOT / "tests/fixtures/typed_worker/cm57c_shadow_cases.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {sha256_text(str(case["request"])) for case in payload["cases"]}


def load_case_definitions(path: Path = CASE_PATH) -> tuple[dict[str, object], ...]:
    """Load and validate the immutable 24-case holdout corpus."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != CORPUS_VERSION:
        raise ValueError("Unexpected CM-57P5 holdout version.")
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 24:
        raise ValueError("CM-57P5 requires exactly 24 holdout cases.")
    registry = create_builtin_registry()
    case_ids: set[str] = set()
    request_hashes: set[str] = set()
    family_counts: Counter[str] = Counter()
    historical_request_hashes = _cm57c_request_hashes()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("CM-57P5 cases must be objects.")
        case_id = case.get("case_id")
        family = case.get("family")
        request = case.get("request")
        report = case.get("expected_report_capabilities")
        sections = case.get("expected_sections")
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            raise ValueError("CM-57P5 case IDs must be unique non-empty strings.")
        if family not in FAMILIES:
            raise ValueError(f"Unknown CM-57P5 family: {family!r}.")
        if not isinstance(request, str) or not request.strip() or PATH_RE.search(request):
            raise ValueError(f"Case {case_id!r} has unsafe request text.")
        if any(term in request for term in (*CAPABILITY_IDS, *FORBIDDEN_REQUEST_TERMS)):
            raise ValueError(f"Case {case_id!r} leaks planner/evaluator vocabulary.")
        request_hash = sha256_text(request)
        if request_hash in request_hashes or request_hash in historical_request_hashes:
            raise ValueError(f"Case {case_id!r} reuses a request.")
        if not isinstance(report, list) or not all(isinstance(value, str) for value in report):
            raise ValueError(f"Case {case_id!r} has invalid report gold.")
        if not isinstance(sections, list) or not all(isinstance(value, list) for value in sections):
            raise ValueError(f"Case {case_id!r} has invalid section gold.")
        if case.get("expected_unresolved_count") != 0:
            raise ValueError("CM-57P5 only permits zero unresolved requirements.")
        _validate_report_gold(report, registry, case_id)
        for section in sections:
            _validate_section_gold(section, registry, case_id)
        case_ids.add(case_id)
        request_hashes.add(request_hash)
        family_counts[str(family)] += 1
    if set(family_counts) != set(FAMILIES) or any(
        family_counts[family] != 4 for family in FAMILIES
    ):
        raise ValueError(f"CM-57P5 family distribution is invalid: {family_counts!r}.")
    return tuple(cases)


def _validate_report_gold(
    report: list[object], registry: CapabilityRegistry, case_id: object
) -> None:
    """Validate one report work-unit gold set."""
    if len(report) != len(set(report)):
        raise ValueError(f"Case {case_id!r} repeats a report capability type.")
    for capability_id in report:
        spec = registry.get(capability_id)
        if spec.category != "report":
            raise ValueError(f"Case {case_id!r} has a non-report capability in report gold.")


def _validate_section_gold(
    section: list[object], registry: CapabilityRegistry, case_id: object
) -> None:
    """Validate one independently compilable section signature."""
    if "section.log_plot" not in section:
        raise ValueError(f"Case {case_id!r} section gold lacks its section capability.")
    if len(section) != len(set(section)):
        raise ValueError(f"Case {case_id!r} repeats a section capability type.")
    if any(value == "report.standard" for value in section):
        raise ValueError(f"Case {case_id!r} places report work in a section.")
    if not _parent_closure_ids([str(value) for value in section], registry):
        raise ValueError(f"Case {case_id!r} violates capability parent closure.")


def _section_signatures(section_tasks: tuple[SectionTask, ...]) -> list[tuple[str, ...]]:
    """Project section tasks into order-independent canonical signatures."""
    return [tuple(sorted(task.capability_ids)) for task in section_tasks]


def _expected_section_signatures(case: dict[str, object]) -> Counter[tuple[str, ...]]:
    """Build the expected section multiset for one holdout case."""
    return Counter(
        tuple(sorted(str(value) for value in section)) for section in case["expected_sections"]
    )


def _plan_projection(plan: SemanticPlan) -> dict[str, object]:
    """Project bounded work-unit facts without retaining semantic prose."""
    return {
        "report_task_present": plan.report_task is not None,
        "report_capability_ids": (
            list(plan.report_task.capability_ids) if plan.report_task is not None else []
        ),
        "section_capability_signatures": [
            list(signature) for signature in _section_signatures(plan.section_tasks)
        ],
        "unresolved_requirements_count": len(plan.unresolved_requirements),
    }


def _facts(
    plan: SemanticPlan,
    case: dict[str, object],
    registry: CapabilityRegistry,
) -> dict[str, object]:
    """Project final plan facts against report and section multisets."""
    expected_report = tuple(sorted(str(value) for value in case["expected_report_capabilities"]))
    actual_report = (
        tuple(sorted(plan.report_task.capability_ids)) if plan.report_task is not None else ()
    )
    actual_sections = _section_signatures(plan.section_tasks)
    expected_sections = _expected_section_signatures(case)
    actual_counter = Counter(actual_sections)
    duplicate_types = [
        sorted(
            capability for capability, count in Counter(task.capability_ids).items() if count > 1
        )
        for task in plan.section_tasks
    ]
    duplicate_types = [items for items in duplicate_types if items]
    closure = all(
        _parent_closure_ids(list(task.capability_ids), registry) for task in plan.section_tasks
    )
    if plan.report_task is not None:
        closure = closure and _parent_closure_ids(list(plan.report_task.capability_ids), registry)
    report_presence_correct = (plan.report_task is not None) == bool(expected_report)
    report_capabilities_exact = actual_report == expected_report
    section_count_correct = len(actual_sections) == sum(expected_sections.values())
    section_multiset_exact = actual_counter == expected_sections
    unresolved_correct = len(plan.unresolved_requirements) == int(case["expected_unresolved_count"])
    return {
        "report_task_present": plan.report_task is not None,
        "report_capability_ids": list(actual_report),
        "section_task_count": len(actual_sections),
        "section_capability_signatures": [list(signature) for signature in actual_sections],
        "report_presence_correct": report_presence_correct,
        "report_capabilities_exact": report_capabilities_exact,
        "section_count_correct": section_count_correct,
        "section_multiset_exact": section_multiset_exact,
        "missing_section_signatures": [
            list(signature)
            for signature, count in (expected_sections - actual_counter).items()
            for _ in range(count)
        ],
        "extra_section_signatures": [
            list(signature)
            for signature, count in (actual_counter - expected_sections).items()
            for _ in range(count)
        ],
        "within_task_duplicates": duplicate_types,
        "duplicate_capability_type": bool(duplicate_types),
        "parent_closure_valid": closure,
        "unresolved_requirements_count": len(plan.unresolved_requirements),
        "unresolved_correct": unresolved_correct,
    }


def final_contract_ok(facts: dict[str, object]) -> bool:
    """Return whether all frozen P5 decomposition conditions pass."""
    return bool(
        facts["report_presence_correct"]
        and facts["report_capabilities_exact"]
        and facts["section_count_correct"]
        and facts["section_multiset_exact"]
        and not facts["duplicate_capability_type"]
        and facts["parent_closure_valid"]
        and facts["unresolved_correct"]
    )


def classify_facts(facts: dict[str, object]) -> str:
    """Apply the frozen final P5 classification precedence."""
    if not facts["report_presence_correct"]:
        return "REPORT_PRESENCE_MISMATCH"
    if not facts["report_capabilities_exact"]:
        return "REPORT_CAPABILITY_MISMATCH"
    if not facts["section_count_correct"]:
        return "SECTION_COUNT_MISMATCH"
    if not facts["section_multiset_exact"]:
        return "SECTION_WORK_UNIT_MISMATCH"
    if facts["duplicate_capability_type"]:
        return "DUPLICATE_CAPABILITY_TYPE"
    if not facts["parent_closure_valid"]:
        return "PARENT_CLOSURE_FAILURE"
    if not facts["unresolved_correct"]:
        return "UNRESOLVED_REQUIREMENTS"
    return "PLANNER_CONTRACT_OK"


@dataclass
class PromptArmBackend(ModelBackendProtocol):
    """Substitute only RC's system prompt at the provider boundary."""

    delegate: ModelBackendProtocol
    arm: Arm
    forwarded_requests: list[StructuredGenerationRequest]
    forwarded_response_models: list[type[BaseModel]] = field(default_factory=list)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Forward P unchanged or replace only RC's system prompt."""
        if request.system_prompt != _PLANNER_SYSTEM_PROMPT:
            raise RuntimeError("CM-57P5 received an unexpected production prompt.")
        forwarded = request if self.arm == "P" else replace(request, system_prompt=RC_PROMPT)
        self.forwarded_requests.append(forwarded)
        self.forwarded_response_models.append(response_model)
        return await self.delegate.generate_structured(forwarded, response_model=response_model)

    async def generate_program(self, request: object) -> object:
        """Reject accidental worker/program execution."""
        raise AssertionError(f"CM-57P5 must not call program generation: {request!r}")


@dataclass
class RecordingBackend(ModelBackendProtocol):
    """Record bounded planner-call facts without retaining provider payloads."""

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
        """Record call outcome and bounded plan shape."""
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
                {"outcome": "provider_failure", "provider_category": error.category.value}
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
        """Fail if the planner experiment reaches a worker."""
        self.program_calls += 1
        raise AssertionError(f"CM-57P5 must not call program generation: {request!r}")


async def run_arm(
    case: dict[str, object],
    *,
    arm: Arm,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
) -> dict[str, object]:
    """Run the real production planner for one P or RC arm."""
    calls: list[dict[str, object]] = []
    plans: list[tuple[str, SemanticPlan]] = []
    planner_backend: ModelBackendProtocol = delegate
    if arm == "RC":
        planner_backend = PromptArmBackend(
            delegate=delegate,
            arm=arm,
            forwarded_requests=[],
        )
    backend = RecordingBackend(delegate=planner_backend, calls=calls, plans=plans)
    planner = SemanticPlanner(backend=backend, registry=registry)
    final_plan: SemanticPlan | None = None
    terminal_classification: str | None = None
    error_type: str | None = None
    error_code: str | None = None
    try:
        final_plan = await planner.plan(
            request=str(case["request"]),
            mode="reconstruct",
            current_document_summary={},
            source_summary=FIXED_SOURCE_SUMMARY,
            timeout_seconds=TIMEOUT_SECONDS,
            temperature=PLANNER_TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
    except ProviderRequestError as error:
        error_type = "ProviderRequestError"
        error_code = error.category.value
        terminal_classification = (
            "PLANNER_SCHEMA_FAILURE"
            if error.category
            in {ProviderFailureCategory.INVALID_RESPONSE, ProviderFailureCategory.VALIDATION}
            else "PROVIDER_INFRA_FAILURE"
        )
    except PlannerSemanticFailure as error:
        error_type = "PlannerSemanticFailure"
        error_code = error.code
        terminal_classification = "PLANNER_SEMANTIC_FAILURE"
    except ValidationError:
        error_type = "ValidationError"
        terminal_classification = "PLANNER_SCHEMA_FAILURE"
    initial_plan = next((plan for kind, plan in plans if kind == "INITIAL"), None)
    initial_facts = _facts(initial_plan, case, registry) if initial_plan is not None else None
    final_facts = _facts(final_plan, case, registry) if final_plan is not None else None
    final_classification = terminal_classification or classify_facts(final_facts or {})
    return {
        "arm": arm,
        "prompt_sha256": sha256_text(composed_prompt(arm)),
        "provider_calls": len(calls),
        "program_calls": backend.program_calls,
        "call_trace": calls,
        "initial_plan_available": initial_plan is not None,
        "initial_work_unit_facts": initial_facts,
        "semantic_correction_used": any(
            call.get("call_kind") == "SEMANTIC_CORRECTION" for call in calls
        ),
        "invalid_response_retry_used": any(
            call.get("call_kind") == "INVALID_RESPONSE_RETRY" for call in calls
        ),
        "final_planner_success": final_plan is not None,
        "final_error_type": error_type,
        "final_error_code": error_code,
        "final_work_unit_facts": final_facts,
        "final_classification": final_classification,
        "final_contract_ok": final_plan is not None and final_contract_ok(final_facts or {}),
        "provider_infrastructure_failure": terminal_classification == "PROVIDER_INFRA_FAILURE",
        "final_plan": _plan_projection(final_plan) if final_plan is not None else None,
    }


async def run_shared_row(
    case: dict[str, object],
    *,
    attempt_index: int,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
    authorized_checkpoint: str | None,
) -> dict[str, object]:
    """Run P and RC against one shared request/context pair."""
    provenance = frozen_population_provenance()
    return {
        **provenance,
        "authorized_checkpoint": authorized_checkpoint,
        "p4_summary_sha256": EXPECTED_P4_SUMMARY_SHA256,
        "p4_raw_sha256": EXPECTED_P4_RAW_SHA256,
        "source_summary_sha256": _fixed_source_summary_sha(),
        "case_id": case["case_id"],
        "family": case["family"],
        "attempt_index": attempt_index,
        "request_sha256": sha256_text(str(case["request"])),
        "expected_report_capabilities": list(case["expected_report_capabilities"]),
        "expected_sections": [list(section) for section in case["expected_sections"]],
        "expected_unresolved_count": case["expected_unresolved_count"],
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
    result = arms.get(arm) if isinstance(arms, dict) else None
    return result if isinstance(result, dict) else {}


def _final_facts(row: dict[str, object], arm: str) -> dict[str, object] | None:
    """Return final facts only when the planner completed semantically."""
    facts = _arm(row, arm).get("final_work_unit_facts")
    return facts if isinstance(facts, dict) else None


def _full_contract_table(rows: list[dict[str, object]]) -> dict[str, int]:
    """Count the four complete-population P-to-RC transitions."""
    counts = Counter(
        (
            bool(_arm(row, "P").get("final_contract_ok")),
            bool(_arm(row, "RC").get("final_contract_ok")),
        )
        for row in rows
    )
    return {
        "BOTH_PASS": counts[(True, True)],
        "P_ONLY_PASS": counts[(True, False)],
        "RC_ONLY_PASS": counts[(False, True)],
        "BOTH_FAIL": counts[(False, False)],
    }


def _semantic_pair_table(rows: list[dict[str, object]], key: str) -> dict[str, int]:
    """Count availability-aware P-to-RC transitions for one fact."""
    counts = Counter()
    for row in rows:
        left = _final_facts(row, "P")
        right = _final_facts(row, "RC")
        if left is None or right is None:
            counts["UNAVAILABLE"] += 1
        else:
            counts[(bool(left.get(key)), bool(right.get(key)))] += 1
    return {
        "CORRECT_TO_CORRECT": counts[(True, True)],
        "CORRECT_TO_WRONG": counts[(True, False)],
        "WRONG_TO_CORRECT": counts[(False, True)],
        "WRONG_TO_WRONG": counts[(False, False)],
        "UNAVAILABLE": counts["UNAVAILABLE"],
    }


def _family_rows(rows: list[dict[str, object]], family: str) -> list[dict[str, object]]:
    """Return rows for one holdout family."""
    return [row for row in rows if row.get("family") == family]


def _arm_metrics(rows: list[dict[str, object]], arm: str) -> dict[str, int]:
    """Aggregate initial/final contract and correction metrics for one arm."""
    results = [_arm(row, arm) for row in rows]
    return {
        "initial_passes": sum(
            isinstance(result.get("initial_work_unit_facts"), dict)
            and final_contract_ok(result["initial_work_unit_facts"])
            for result in results
        ),
        "final_passes": sum(bool(result.get("final_contract_ok")) for result in results),
        "corrections": sum(bool(result.get("semantic_correction_used")) for result in results),
        "correction_recoveries": sum(
            bool(result.get("semantic_correction_used")) and bool(result.get("final_contract_ok"))
            for result in results
        ),
        "correction_failures": sum(
            bool(result.get("semantic_correction_used"))
            and not bool(result.get("final_contract_ok"))
            for result in results
        ),
        "rows_without_correction": sum(
            not bool(result.get("semantic_correction_used")) for result in results
        ),
        "terminal_failures": sum(
            not bool(result.get("final_planner_success")) for result in results
        ),
        "provider_infrastructure_failures": sum(
            bool(result.get("provider_infrastructure_failure")) for result in results
        ),
        "provider_calls": sum(int(result.get("provider_calls", 0)) for result in results),
        "program_calls": sum(int(result.get("program_calls", 0)) for result in results),
    }


def repeatability(rows: list[dict[str, object]]) -> dict[str, dict[str, list[str]]]:
    """Compare final bounded facts across the two attempts per case."""
    output = {arm: {"stable": [], "unstable": [], "unavailable": []} for arm in ARMS}
    for case_id in sorted({str(row["case_id"]) for row in rows}):
        case_rows = sorted(
            (row for row in rows if str(row["case_id"]) == case_id),
            key=lambda row: int(row["attempt_index"]),
        )
        for arm in ARMS:
            values = [_final_facts(row, arm) for row in case_rows]
            if len(values) != ATTEMPTS or any(value is None for value in values):
                output[arm]["unavailable"].append(case_id)
            elif values[0] == values[1]:
                output[arm]["stable"].append(case_id)
            else:
                output[arm]["unstable"].append(case_id)
    return output


def _new_wrong_selection(rows: list[dict[str, object]]) -> bool:
    """Detect an RC wrong work-unit selection where P was correct."""
    return any(
        bool(_arm(row, "P").get("final_contract_ok"))
        and not bool(_arm(row, "RC").get("final_contract_ok"))
        for row in rows
    )


def population_integrity(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    expected_checkpoint: str | None = None,
) -> tuple[bool, list[str]]:
    """Validate exact row shape, holdout provenance, and frozen controls."""
    reasons: list[str] = []
    expected_ids = {str(case["case_id"]) for case in cases}
    if len(rows) != len(cases) * ATTEMPTS:
        reasons.append("wrong_row_count")
    pairs = [(str(row.get("case_id")), row.get("attempt_index")) for row in rows]
    if len(set(pairs)) != len(pairs):
        reasons.append("duplicate_case_attempt")
    if {case_id for case_id, _ in pairs} != expected_ids:
        reasons.append("case_set_mismatch")
    by_case: dict[str, set[object]] = {}
    for case_id, attempt in pairs:
        by_case.setdefault(case_id, set()).add(attempt)
    if any(attempts != set(range(ATTEMPTS)) for attempts in by_case.values()):
        reasons.append("attempt_index_mismatch")
    checkpoints = {row.get("authorized_checkpoint") for row in rows}
    if None in checkpoints or len(checkpoints) != 1:
        reasons.append("checkpoint_missing_or_mixed")
    elif expected_checkpoint is not None and checkpoints != {expected_checkpoint}:
        reasons.append("checkpoint_mismatch")
    expected_by_id = {str(case["case_id"]): case for case in cases}
    expected_provenance = frozen_population_provenance()
    for row in rows:
        case = expected_by_id.get(str(row.get("case_id")))
        if case is None:
            continue
        if not isinstance(row.get("arms"), dict) or set(row["arms"]) != set(ARMS):
            reasons.append("arm_set_mismatch")
        if row.get("family") != case["family"]:
            reasons.append("family_mismatch")
        if row.get("experiment_version") != EXPERIMENT_VERSION:
            reasons.append("experiment_version_mismatch")
        if row.get("design_baseline_sha") != BASELINE_SHA:
            reasons.append("baseline_mismatch")
        for provenance_field in (
            "harness_sha256",
            "corpus_sha256",
            "planner_source_sha256",
            "catalog_sha256",
            "base_prompt_sha256",
            "report_instruction_sha256",
            "section_composition_instruction_sha256",
            "RC_prompt_sha256",
            "source_summary_sha256",
        ):
            if row.get(provenance_field) != expected_provenance[provenance_field]:
                reasons.append(f"{provenance_field}_mismatch")
        if row.get("execution_controls") != expected_provenance["execution_controls"]:
            reasons.append("execution_controls_mismatch")
        for arm in ARMS:
            if _arm(row, arm).get("prompt_sha256") != sha256_text(composed_prompt(arm)):
                reasons.append(f"{arm}_prompt_mismatch")
        if row.get("p4_summary_sha256") != EXPECTED_P4_SUMMARY_SHA256:
            reasons.append("p4_summary_mismatch")
        if row.get("p4_raw_sha256") != EXPECTED_P4_RAW_SHA256:
            reasons.append("p4_raw_mismatch")
        if row.get("request_sha256") != sha256_text(str(case["request"])):
            reasons.append("request_hash_mismatch")
        if row.get("expected_report_capabilities") != case["expected_report_capabilities"]:
            reasons.append("report_gold_mismatch")
        if row.get("expected_sections") != case["expected_sections"]:
            reasons.append("section_gold_mismatch")
        if row.get("expected_unresolved_count") != case["expected_unresolved_count"]:
            reasons.append("unresolved_gold_mismatch")
    return not reasons, sorted(set(reasons))


def decision(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    expected_checkpoint: str | None = None,
) -> str:
    """Apply the frozen promotion-quality holdout decision precedence."""
    complete, _ = population_integrity(rows, cases, expected_checkpoint=expected_checkpoint)
    if not complete:
        return "INCONCLUSIVE_HOLDOUT_EVALUATION"
    if any(
        bool(_arm(row, arm).get("provider_infrastructure_failure")) for row in rows for arm in ARMS
    ):
        return "INCONCLUSIVE_HOLDOUT_EVALUATION"
    p_passes = sum(bool(_arm(row, "P").get("final_contract_ok")) for row in rows)
    rc_passes = sum(bool(_arm(row, "RC").get("final_contract_ok")) for row in rows)
    p_only = sum(
        bool(_arm(row, "P").get("final_contract_ok"))
        and not bool(_arm(row, "RC").get("final_contract_ok"))
        for row in rows
    )
    if p_only:
        return "HOLDOUT_GENERALIZATION_REGRESSION"
    if rc_passes == len(rows):
        return "HOLDOUT_GENERALIZATION_VALIDATED"
    if rc_passes > p_passes:
        return "HOLDOUT_GENERALIZATION_PARTIAL"
    return "HOLDOUT_GENERALIZATION_NO_GAIN"


def summarize_population(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    authorized_checkpoint: str | None = None,
) -> dict[str, object]:
    """Build bounded aggregate evidence for the future live population."""
    complete, reasons = population_integrity(rows, cases, expected_checkpoint=authorized_checkpoint)
    family_metrics = {
        family: {arm: _arm_metrics(_family_rows(rows, family), arm) for arm in ARMS}
        for family in FAMILIES
    }
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "population": {
            "expected_rows": len(cases) * ATTEMPTS,
            "actual_rows": len(rows),
            "cases": len(cases),
            "attempts_per_case": ATTEMPTS,
            "arms_per_row": len(ARMS),
            "complete": complete,
            "reasons": reasons,
        },
        "decision": decision(rows, cases, expected_checkpoint=authorized_checkpoint),
        "arm_metrics": {arm: _arm_metrics(rows, arm) for arm in ARMS},
        "family_metrics": family_metrics,
        "paired": {
            "overall": _full_contract_table(rows),
            "by_family": {
                family: {
                    "full_contract": _full_contract_table(_family_rows(rows, family)),
                    "report_presence": _semantic_pair_table(
                        _family_rows(rows, family), "report_presence_correct"
                    ),
                    "section_count": _semantic_pair_table(
                        _family_rows(rows, family), "section_count_correct"
                    ),
                    "section_work_units": _semantic_pair_table(
                        _family_rows(rows, family), "section_multiset_exact"
                    ),
                    "report_capabilities": _semantic_pair_table(
                        _family_rows(rows, family), "report_capabilities_exact"
                    ),
                }
                for family in FAMILIES
            },
            "report_presence": _semantic_pair_table(rows, "report_presence_correct"),
            "section_count": _semantic_pair_table(rows, "section_count_correct"),
            "section_work_units": _semantic_pair_table(rows, "section_multiset_exact"),
            "report_capabilities": _semantic_pair_table(rows, "report_capabilities_exact"),
        },
        "repeatability": repeatability(rows),
        "controls": {
            "model": FROZEN_MODEL,
            "planner_temperature": PLANNER_TEMPERATURE,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_tokens_parameter": MAX_TOKENS_PARAMETER,
            "timeout_seconds": TIMEOUT_SECONDS,
        },
    }


def verify_reviewed_checkout(checkpoint: str) -> None:
    """Require the future live checkout and guarded bytes to match review."""
    if CHECKPOINT_RE.fullmatch(checkpoint) is None:
        raise ValueError("CM-57P5 requires a full lowercase checkpoint SHA.")
    if current_checkout_sha() != checkpoint:
        raise RuntimeError("CM-57P5 checkout does not match its authorized checkpoint.")
    guarded = (
        "scripts/cm57p5_fresh_holdout.py",
        "tests/fixtures/typed_worker/cm57p5_fresh_holdout.json",
        "scripts/cm57p4_prompt_interaction_bisect.py",
        "docs/evaluations/agent-code-mode/CM-57P4-live-summary.json",
        "src/wellplot/agent/code_mode/planner.py",
        "src/wellplot/capabilities/base.py",
        "src/wellplot/capabilities/registry.py",
        "src/wellplot/capabilities/builtins.py",
        "tests/fixtures/typed_worker/cm57c_shadow_cases.json",
    )
    for relative_path in guarded:
        path = REPO_ROOT / relative_path
        if path.read_bytes() != _git_output("show", f"{checkpoint}:{relative_path}"):
            raise RuntimeError(f"CM-57P5 guarded artifact drifted: {relative_path}")


def verify_frozen_contract() -> dict[str, object]:
    """Verify P4, production, corpus, and prompt anchors before live use."""
    cases = load_case_definitions()
    if artifact_sha256(CASE_PATH) != EXPECTED_HOLDOUT_SHA256:
        raise RuntimeError("CM-57P5 holdout corpus bytes drifted.")
    if _fixed_source_summary_sha() != EXPECTED_SOURCE_SUMMARY_SHA256:
        raise RuntimeError("CM-57P5 source summary bytes drifted.")
    actual_controls = {
        "model": FROZEN_MODEL,
        "planner_temperature": PLANNER_TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "max_tokens_parameter": MAX_TOKENS_PARAMETER,
        "timeout_seconds": TIMEOUT_SECONDS,
    }
    if actual_controls != FROZEN_EXECUTION_CONTROLS:
        raise RuntimeError("CM-57P5 execution controls drifted.")
    if artifact_sha256(P4_SCRIPT_PATH) != EXPECTED_P4_SCRIPT_SHA256:
        raise RuntimeError("CM-57P4 harness bytes drifted.")
    if artifact_sha256(P4_SUMMARY_PATH) != EXPECTED_P4_SUMMARY_SHA256:
        raise RuntimeError("CM-57P4 summary bytes drifted.")
    p4_summary = json.loads(P4_SUMMARY_PATH.read_text(encoding="utf-8"))
    live = p4_summary.get("live_evidence", {})
    if (
        p4_summary.get("decision") != "INCONCLUSIVE_PROMPT_INTERACTION_BISECT"
        or live.get("authorized_checkpoint") != EXPECTED_P4_CHECKPOINT
        or live.get("raw_rows") != 32
        or live.get("raw_sha256") != EXPECTED_P4_RAW_SHA256
        or live.get("provider_calls") != 156
        or live.get("worker_program_calls") != 0
    ):
        raise RuntimeError("CM-57P4 evidence anchor drifted.")
    planner_path = REPO_ROOT / "src/wellplot/agent/code_mode/planner.py"
    if artifact_sha256(planner_path) != EXPECTED_PLANNER_SOURCE_SHA256:
        raise RuntimeError("Production planner bytes drifted.")
    if _catalog_sha256() != EXPECTED_CATALOG_SHA256:
        raise RuntimeError("Production planning catalogue drifted.")
    if sha256_text(_PLANNER_SYSTEM_PROMPT) != EXPECTED_BASE_PROMPT_SHA256:
        raise RuntimeError("Production planner prompt drifted.")
    if sha256_text(REPORT_BOUNDARY_INSTRUCTION) != EXPECTED_R_INSTRUCTION_SHA256:
        raise RuntimeError("R instruction drifted.")
    if sha256_text(SECTION_COMPOSITION_INSTRUCTION) != EXPECTED_C_INSTRUCTION_SHA256:
        raise RuntimeError("C instruction drifted.")
    if sha256_text(RC_PROMPT) != EXPECTED_RC_PROMPT_SHA256:
        raise RuntimeError("RC prompt drifted.")
    if len(cases) != 24:
        raise RuntimeError("CM-57P5 holdout case count drifted.")
    return {
        "cases": len(cases),
        "holdout_sha256": EXPECTED_HOLDOUT_SHA256,
        "source_summary_sha256": EXPECTED_SOURCE_SUMMARY_SHA256,
        "p4_summary_sha256": EXPECTED_P4_SUMMARY_SHA256,
        "p4_raw_sha256": EXPECTED_P4_RAW_SHA256,
        "base_prompt_sha256": EXPECTED_BASE_PROMPT_SHA256,
        "report_instruction_sha256": EXPECTED_R_INSTRUCTION_SHA256,
        "section_composition_instruction_sha256": EXPECTED_C_INSTRUCTION_SHA256,
        "RC_prompt_sha256": EXPECTED_RC_PROMPT_SHA256,
    }


class _DeterministicBackend(ModelBackendProtocol):
    """Provider-free backend used only for prompt-isolation self-tests."""

    def __init__(self, *, invalid_first: bool = False) -> None:
        self.invalid_first = invalid_first
        self.calls: list[StructuredGenerationRequest] = []
        self.response_models: list[type[BaseModel]] = []

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        self.calls.append(request)
        self.response_models.append(response_model)
        invalid = self.invalid_first and len(self.calls) == 1
        capability_ids = (
            ("unknown.capability",)
            if invalid
            else (
                "section.log_plot",
                "track.normal",
                "binding.curve",
            )
        )
        plan = SemanticPlan(
            summary="deterministic self-test",
            section_tasks=(SectionTask(goal="one test panel", capability_ids=capability_ids),),
        )
        return StructuredGenerationResult(value=plan, metrics=ProviderMetrics())

    async def generate_program(self, request: object) -> object:
        raise AssertionError(f"CM-57P5 self-test reached program generation: {request!r}")


async def _production_path_equivalence_self_test(case: dict[str, object]) -> None:
    """Prove the actual P path and RC differ only by RC's system prompt."""
    registry = create_builtin_registry()
    planner_kwargs = {
        "request": str(case["request"]),
        "mode": "reconstruct",
        "current_document_summary": {},
        "source_summary": FIXED_SOURCE_SUMMARY,
        "timeout_seconds": TIMEOUT_SECONDS,
        "temperature": PLANNER_TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
    }

    direct_backend = _DeterministicBackend(invalid_first=True)
    direct_planner = SemanticPlanner(backend=direct_backend, registry=registry)
    try:
        await direct_planner.plan(**planner_kwargs)
    except PlannerSemanticFailure as error:
        raise AssertionError("Direct production correction self-test failed.") from error

    p_backend = _DeterministicBackend(invalid_first=True)
    p_result = await run_arm(case, arm="P", delegate=p_backend, registry=registry)
    assert p_result["final_planner_success"]
    assert p_backend.calls == direct_backend.calls
    assert p_backend.response_models == [SemanticPlan, SemanticPlan]
    assert direct_backend.response_models == [SemanticPlan, SemanticPlan]
    assert all(request.system_prompt == _PLANNER_SYSTEM_PROMPT for request in p_backend.calls)

    rc_backend = _DeterministicBackend(invalid_first=True)
    rc_result = await run_arm(case, arm="RC", delegate=rc_backend, registry=registry)
    assert rc_result["final_planner_success"]
    assert rc_backend.response_models == [SemanticPlan, SemanticPlan]
    for production, candidate in zip(p_backend.calls, rc_backend.calls, strict=True):
        assert production.user_prompt == candidate.user_prompt
        assert production.timeout_seconds == candidate.timeout_seconds
        assert production.temperature == candidate.temperature
        assert production.max_output_tokens == candidate.max_output_tokens
        assert production.system_prompt == _PLANNER_SYSTEM_PROMPT
        assert candidate.system_prompt == RC_PROMPT


def _self_test_evaluator(cases: tuple[dict[str, object], ...]) -> None:
    """Exercise multiset, report, multiplicity, and decision rules without a provider."""
    registry = create_builtin_registry()
    assert len(cases) == 24
    assert _expected_section_signatures(cases[12]) == Counter(
        {("binding.curve", "section.log_plot", "track.normal"): 2}
    )
    plan = SemanticPlan(
        summary="two independent panels",
        section_tasks=(
            SectionTask(
                goal="image panel",
                capability_ids=("section.log_plot", "track.array", "binding.raster"),
            ),
            SectionTask(
                goal="curve panel",
                capability_ids=("binding.curve", "track.normal", "section.log_plot"),
            ),
        ),
    )
    facts = _facts(plan, cases[13], registry)
    assert facts["section_multiset_exact"]
    assert final_contract_ok(facts)
    report_case = cases[18]
    report_plan = SemanticPlan(
        summary="mixed",
        report_task=ReportTask(goal="report", capability_ids=("report.standard",)),
        section_tasks=(
            SectionTask(
                goal="curve",
                capability_ids=("section.log_plot", "track.normal", "binding.curve"),
            ),
            SectionTask(
                goal="image",
                capability_ids=("section.log_plot", "track.array", "binding.raster"),
            ),
        ),
    )
    report_facts = _facts(report_plan, report_case, registry)
    assert final_contract_ok(report_facts)
    duplicate_plan = SemanticPlan(
        summary="duplicate type",
        section_tasks=(
            SectionTask(
                goal="bad panel",
                capability_ids=(
                    "section.log_plot",
                    "track.normal",
                    "binding.curve",
                    "binding.curve",
                ),
            ),
        ),
    )
    duplicate_facts = _facts(duplicate_plan, cases[20], registry)
    assert duplicate_facts["duplicate_capability_type"]
    rows = _synthetic_rows(cases)
    assert (
        decision(rows, cases, expected_checkpoint=BASELINE_SHA)
        == "HOLDOUT_GENERALIZATION_VALIDATED"
    )
    rows[0]["arms"]["RC"]["final_contract_ok"] = False
    assert (
        decision(rows, cases, expected_checkpoint=BASELINE_SHA)
        == "HOLDOUT_GENERALIZATION_REGRESSION"
    )
    rows[0]["arms"]["RC"]["final_contract_ok"] = True
    rows[0]["arms"]["P"]["final_contract_ok"] = False
    rows[1]["arms"]["P"]["final_contract_ok"] = False
    rows[1]["arms"]["RC"]["final_contract_ok"] = False
    assert (
        decision(rows, cases, expected_checkpoint=BASELINE_SHA) == "HOLDOUT_GENERALIZATION_PARTIAL"
    )
    rows[0]["arms"]["P"]["final_contract_ok"] = True
    for row in rows:
        row["arms"]["P"]["final_contract_ok"] = False
        row["arms"]["RC"]["final_contract_ok"] = False
    assert (
        decision(rows, cases, expected_checkpoint=BASELINE_SHA) == "HOLDOUT_GENERALIZATION_NO_GAIN"
    )
    rows[0]["arms"]["RC"]["provider_infrastructure_failure"] = True
    assert (
        decision(rows, cases, expected_checkpoint=BASELINE_SHA) == "INCONCLUSIVE_HOLDOUT_EVALUATION"
    )


def _synthetic_rows(cases: tuple[dict[str, object], ...]) -> list[dict[str, object]]:
    """Build a complete all-pass population for provider-free decision tests."""
    provenance = frozen_population_provenance()
    rows: list[dict[str, object]] = []
    for case in cases:
        for attempt in range(ATTEMPTS):
            rows.append(
                {
                    **provenance,
                    "authorized_checkpoint": BASELINE_SHA,
                    "p4_summary_sha256": EXPECTED_P4_SUMMARY_SHA256,
                    "p4_raw_sha256": EXPECTED_P4_RAW_SHA256,
                    "case_id": case["case_id"],
                    "family": case["family"],
                    "attempt_index": attempt,
                    "request_sha256": sha256_text(str(case["request"])),
                    "expected_report_capabilities": list(case["expected_report_capabilities"]),
                    "expected_sections": [list(section) for section in case["expected_sections"]],
                    "expected_unresolved_count": 0,
                    "arms": {
                        arm: {
                            "prompt_sha256": sha256_text(composed_prompt(arm)),
                            "final_contract_ok": True,
                            "final_planner_success": True,
                            "provider_infrastructure_failure": False,
                            "program_calls": 0,
                        }
                        for arm in ARMS
                    },
                }
            )
    return rows


def prelive_report() -> dict[str, object]:
    """Run all provider-free P5 guards and describe the future matrix."""
    contract = verify_frozen_contract()
    cases = load_case_definitions()
    _self_test_evaluator(cases)
    asyncio.run(_production_path_equivalence_self_test(cases[4]))
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
        **contract,
        "future_controls": {
            "model": FROZEN_MODEL,
            "planner_temperature": PLANNER_TEMPERATURE,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_tokens_parameter": MAX_TOKENS_PARAMETER,
            "timeout_seconds": TIMEOUT_SECONDS,
            "attempts": ATTEMPTS,
        },
        "future_population": {
            "cases": len(cases),
            "families": len(FAMILIES),
            "cases_per_family": 4,
            "shared_rows": len(cases) * ATTEMPTS,
            "planner_executions": len(cases) * ATTEMPTS * len(ARMS),
            "provider_calls_min": len(cases) * ATTEMPTS * len(ARMS),
            "provider_calls_max": len(cases) * ATTEMPTS * len(ARMS) * 2,
        },
        "arms": list(ARMS),
        "P_production_equivalence": "PASS",
        "RC_system_prompt_isolation": "PASS",
        "work_unit_multiset_evaluator": "PASS",
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
        raise RuntimeError("No CM-57P5 API key configured.")
    return OpenAICompatibleBackendV2(
        model=FROZEN_MODEL,
        client=AsyncOpenAI(api_key=api_key, base_url=args.base_url, timeout=TIMEOUT_SECONDS),
        structured_output="json_schema",
        max_tokens_parameter=MAX_TOKENS_PARAMETER,
    )


async def _run_live(args: argparse.Namespace, checkpoint: str) -> None:
    """Run all 48 shared rows once and flush each completed row."""
    if OUTPUT_PATH.exists() and OUTPUT_PATH.stat().st_size:
        raise RuntimeError(f"Refusing to append to non-empty evidence path {OUTPUT_PATH}.")
    verify_reviewed_checkout(checkpoint)
    verify_frozen_contract()
    cases = load_case_definitions()
    registry = create_builtin_registry()
    backend = _provider_configuration(args)
    rows: list[dict[str, object]] = []
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("a", encoding="utf-8") as handle:
        for case in cases:
            for attempt_index in range(ATTEMPTS):
                row = await run_shared_row(
                    case,
                    attempt_index=attempt_index,
                    delegate=backend,
                    registry=registry,
                    authorized_checkpoint=checkpoint,
                )
                rows.append(row)
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
                handle.flush()
    print(json.dumps(summarize_population(rows, cases, authorized_checkpoint=checkpoint), indent=2))


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
        raise SystemExit("Live CM-57P5 requires --authorized-checkpoint and --base-url.")
    asyncio.run(_run_live(args, args.authorized_checkpoint))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
