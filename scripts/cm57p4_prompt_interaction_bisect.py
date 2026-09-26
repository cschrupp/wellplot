"""CM-57P4 planner prompt interaction and ordering micro-bisect.

The default command performs provider-free pre-live checks. The live path is
separately gated because this experiment changes only planner prompt composition.
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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import cm57p2_planner_shadow as p2  # noqa: E402
from wellplot.agent.code_mode.planner import (  # noqa: E402
    _PLANNER_SYSTEM_PROMPT,
    PlannerSemanticFailure,
    ReportTask,
    SectionTask,
    SemanticPlan,
    SemanticPlanner,
)  # noqa: E402
from wellplot.agent.providers.base import (  # noqa: E402
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)  # noqa: E402
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry  # noqa: E402

CASE_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm57c_shadow_cases.json"
HISTORICAL_SUMMARY_PATH = REPO_ROOT / "docs/evaluations/agent-code-mode/CM-57P2-live-summary.json"
OUTPUT_PATH = Path("/tmp/cm57p4-prompt-interaction-qwen.jsonl")

BASELINE_SHA = "ad870d94b62e297585c29867debd40f556489f05"
EXPERIMENT_VERSION = "CM-57P4"
FROZEN_MODEL = "qwen3.6-35b-a3b"
PLANNER_TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 16384
MAX_TOKENS_PARAMETER = "max_tokens"
TIMEOUT_SECONDS = 900.0
ATTEMPTS = 2
ARMS: tuple[str, ...] = ("R", "WR", "RW", "RC")
Arm = Literal["R", "WR", "RW", "RC"]

EXPECTED_PROMPT_SHA256 = "5e7a0732af01e4b1f16b3ccf019c005ea2e9ba5c0e93e94870a56a261e2bca18"
EXPECTED_PLANNER_SOURCE_SHA256 = "0189b290ef4f76bdd776fe2612c454809ff77725379def7d8c5a98d9ae165413"
EXPECTED_CATALOG_SHA256 = "b1b9c85db961cb8b97f1c8b6f914a6a75f5bf57cf49ca4413c64d35311b80d37"
EXPECTED_CORPUS_SHA256 = "3acac04abbe8d20902bc1785d71cf3b8b0a9d7caf623ea79ed2eca8617842181"
EXPECTED_P2_SUMMARY_SHA256 = "0aa20622e319117a1920f2a9809404fc00f087582c6c90786a159229c7b5e6fe"
EXPECTED_P2_RAW_SHA256 = "33361e0ec2020b2215793fac87df52547a86d542fd6ed886def77871a5e79d38"
EXPECTED_P3_SCRIPT_SHA256 = "ac416284aed961f3abebf33f329445bf9118c12c0e3638dfb5c514ca656e9000"
EXPECTED_P3_SUMMARY_SHA256 = "1d22cbfbf34072c9566effc141fe3b88fa0972ed27c71f0d2d53cdff903e59ed"
EXPECTED_P3_CHECKPOINT = "2e4f26f94670b8fa43cd7bea1246cb414c87bc41"
EXPECTED_P3_RAW_SHA256 = "84dd0a9b9a9b6288f7442211cc72b427512db39128d8b976c12e378888aca1a0"
EXPECTED_SOURCE_MATRIX_SHA256 = "7be957d4bd3361457206bbce689c612727cec5c4a3d4cbf392c4dcca52203d8b"
CHECKPOINT_RE = re.compile(r"^[0-9a-f]{40}$")

WORK_UNIT_INSTRUCTION = """Work-unit boundary:

A SectionTask represents one independently compilable logical section, not one
capability. Capabilities describing that section's container, tracks, and
bindings belong together in that same SectionTask.

Do not create separate SectionTasks merely because capabilities have different
categories or structural levels.

Create multiple SectionTasks only when the user's request actually describes
multiple independently compilable logical sections."""

REPORT_BOUNDARY_INSTRUCTION = """Report-task boundary:

Use report_task only for genuinely report-wide work explicitly requested by the
user.

If the request consists only of creating, modifying, or describing one or more
plot/log sections, report_task must be null.

Do not create an empty, placeholder, summary-only, or bookkeeping report_task
for section-local work."""

SECTION_COMPOSITION_INSTRUCTION = """SectionTask composition:

A SectionTask represents one independently compilable logical section.

When one requested section contains multiple tracks, including tracks of
different kinds, keep those tracks in the same SectionTask and include the
complete capability type set needed for the section container, every requested
track, and every requested binding.

Create another SectionTask only for another independently compilable section."""


def canonical_json(value: object) -> str:
    """Serialize JSON-shaped evidence deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    """Hash exact UTF-8 text bytes."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def artifact_sha256(path: Path) -> str:
    """Hash one repository artifact by exact bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def composed_prompt(arm: Arm) -> str:
    """Compose one P4 factor prompt while preserving the production base."""
    suffixes = {
        "R": (REPORT_BOUNDARY_INSTRUCTION,),
        "WR": (WORK_UNIT_INSTRUCTION, REPORT_BOUNDARY_INSTRUCTION),
        "RW": (REPORT_BOUNDARY_INSTRUCTION, WORK_UNIT_INSTRUCTION),
        "RC": (REPORT_BOUNDARY_INSTRUCTION, SECTION_COMPOSITION_INSTRUCTION),
    }[arm]
    return _PLANNER_SYSTEM_PROMPT + "".join(f"\n{suffix}" for suffix in suffixes)


PROMPT_SHA256 = {arm: sha256_text(composed_prompt(arm)) for arm in ARMS}


@dataclass
class PromptArmBackend(ModelBackendProtocol):
    """Substitute only the planner system prompt at the provider boundary."""

    delegate: ModelBackendProtocol
    arm: Arm
    forwarded_requests: list[StructuredGenerationRequest]

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Forward a request after checking and replacing only its system prompt."""
        if request.system_prompt != _PLANNER_SYSTEM_PROMPT:
            raise RuntimeError("CM-57P4 received unexpected production planner prompt.")
        forwarded = replace(request, system_prompt=composed_prompt(self.arm))
        self.forwarded_requests.append(forwarded)
        return await self.delegate.generate_structured(forwarded, response_model=response_model)

    async def generate_program(self, request: object) -> object:
        """Reject accidental downstream worker execution."""
        raise AssertionError(f"CM-57P4 must not call program generation: {request!r}")


@dataclass
class _RecordingBackend(ModelBackendProtocol):
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
        """Record call kind and bounded plan shape, then return the provider result."""
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
            record["plan"] = p2._plan_projection(result.value)
        record["metrics"] = result.metrics.public_metadata()
        self.calls.append(record)
        return result

    async def generate_program(self, request: object) -> object:
        """Fail if the planner experiment reaches a worker."""
        self.program_calls += 1
        raise AssertionError(f"CM-57P4 must not call program generation: {request!r}")


def _facts(
    plan: SemanticPlan,
    expected_capabilities: list[str],
    registry: CapabilityRegistry,
) -> dict[str, object]:
    """Project planner output into work-unit and report-boundary facts."""
    section_capabilities = [list(task.capability_ids) for task in plan.section_tasks]
    flattened = [capability for task in section_capabilities for capability in task]
    expected = set(expected_capabilities)
    actual = set(flattened)
    counts = Counter(flattened)
    union_exact = actual == expected
    parent_closure = p2._parent_closure(plan, registry)
    return {
        "report_task_present": plan.report_task is not None,
        "report_capability_ids": (
            list(plan.report_task.capability_ids) if plan.report_task is not None else []
        ),
        "report_capability_count": (
            len(plan.report_task.capability_ids) if plan.report_task is not None else 0
        ),
        "empty_report_task": plan.report_task is not None and not plan.report_task.capability_ids,
        "section_task_count": len(plan.section_tasks),
        "section_count_ok": len(plan.section_tasks) == 1,
        "section_capability_ids": section_capabilities,
        "section_capability_union": sorted(actual),
        "union_missing_capabilities": sorted(expected - actual),
        "union_unexpected_capabilities": sorted(actual - expected),
        "union_exact_expected": union_exact,
        "actual_capability_ids": flattened,
        "duplicate_capabilities": sorted(
            capability for capability, count in counts.items() if count > 1
        ),
        "within_task_duplicates": [
            sorted(capability for capability, count in Counter(task).items() if count > 1)
            for task in section_capabilities
        ],
        "single_task_closure_omission": len(plan.section_tasks) == 1 and bool(expected - actual),
        "work_unit_fragmentation": len(plan.section_tasks) > 1 and union_exact,
        "fragmentation_with_gap": len(plan.section_tasks) > 1 and not union_exact,
        "capability_types_repeated_across_section_tasks": sorted(
            capability for capability, count in Counter(flattened).items() if count > 1
        ),
        "unresolved_requirements_count": len(plan.unresolved_requirements),
        "unresolved_present": bool(plan.unresolved_requirements),
        "wrong_capability_selection": bool(actual - expected),
        "parent_closure_valid": parent_closure,
    }


def final_contract_ok(facts: dict[str, object]) -> bool:
    """Apply the exact one-section planner contract."""
    return bool(
        not facts["report_task_present"]
        and facts["section_count_ok"]
        and not facts["unresolved_present"]
        and not facts["duplicate_capabilities"]
        and facts["union_exact_expected"]
        and facts["parent_closure_valid"]
    )


def _classify(facts: dict[str, object]) -> str:
    """Classify a completed plan using the existing P2 contract vocabulary."""
    if not facts["section_count_ok"]:
        return "WORK_UNIT_COUNT_MISMATCH"
    if facts["wrong_capability_selection"]:
        return "WRONG_CAPABILITY_SELECTION"
    if facts["union_missing_capabilities"]:
        return "CAPABILITY_CLOSURE_OMISSION"
    if facts["duplicate_capabilities"]:
        return "CAPABILITY_DUPLICATION"
    if facts["report_task_present"] and facts["unresolved_present"]:
        return "REPORT_AND_UNRESOLVED"
    if facts["report_task_present"]:
        return "UNEXPECTED_REPORT_TASK"
    if facts["unresolved_present"]:
        return "UNRESOLVED_REQUIREMENTS"
    if not facts["parent_closure_valid"]:
        return "PLANNER_SEMANTIC_FAILURE"
    return "PLANNER_CONTRACT_OK"


def _provider_classification(error: ProviderRequestError) -> str:
    """Map provider categories to bounded planner evidence classes."""
    if error.category in {
        ProviderFailureCategory.INVALID_RESPONSE,
        ProviderFailureCategory.VALIDATION,
    }:
        return "PLANNER_SCHEMA_FAILURE"
    return "PROVIDER_INFRA_FAILURE"


async def run_arm(
    case: dict[str, object],
    *,
    arm: Arm,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
    attempt_index: int,
    shared_input: dict[str, object],
) -> dict[str, object]:
    """Run one production SemanticPlanner under one prompt factor."""
    calls: list[dict[str, object]] = []
    prompt_backend = PromptArmBackend(delegate=delegate, arm=arm, forwarded_requests=[])
    backend = _RecordingBackend(delegate=prompt_backend, calls=calls, plans=[])
    planner = SemanticPlanner(backend=backend, registry=registry)
    expected = [str(value) for value in case["expected_capabilities"]]
    final_plan: SemanticPlan | None = None
    provider_error: ProviderRequestError | None = None
    semantic_failure: PlannerSemanticFailure | None = None
    schema_failure = False
    try:
        final_plan = await planner.plan(
            request=str(case["request"]),
            mode="reconstruct",
            source_summary=shared_input["source_summary"],
            timeout_seconds=TIMEOUT_SECONDS,
            temperature=PLANNER_TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
    except ProviderRequestError as error:
        provider_error = error
    except PlannerSemanticFailure as error:
        semantic_failure = error
    except ValidationError:
        schema_failure = True
    initial_plan = next(
        (plan for call_kind, plan in backend.plans if call_kind == "INITIAL"),
        None,
    )
    result: dict[str, object] = {
        "arm": arm,
        "prompt_sha256": PROMPT_SHA256[arm],
        "planner_call_count": len(calls),
        "program_call_count": backend.program_calls,
        "call_trace": calls,
        "provider_failure_categories": [
            str(call["provider_category"])
            for call in calls
            if call.get("outcome") == "provider_failure"
        ],
        "semantic_correction_used": any(
            call.get("call_kind") == "SEMANTIC_CORRECTION" for call in calls
        ),
        "invalid_response_retry_used": any(
            call.get("call_kind") == "INVALID_RESPONSE_RETRY" for call in calls
        ),
        "initial_plan_available": initial_plan is not None,
        "initial_facts": (
            _facts(initial_plan, expected, registry) if initial_plan is not None else None
        ),
        "provider_infrastructure_failure": False,
    }
    if provider_error is not None:
        result.update(
            {
                "final_planner_success": False,
                "final_classification": _provider_classification(provider_error),
                "provider_infrastructure_failure": _provider_classification(provider_error)
                == "PROVIDER_INFRA_FAILURE",
                "final_error_type": "ProviderRequestError",
                "final_error_code": provider_error.category.value,
                "final_facts": None,
            }
        )
    elif semantic_failure is not None:
        result.update(
            {
                "final_planner_success": False,
                "final_classification": "PLANNER_SEMANTIC_FAILURE",
                "final_error_type": "PlannerSemanticFailure",
                "final_error_code": semantic_failure.code,
                "final_facts": None,
            }
        )
    elif schema_failure:
        result.update(
            {
                "final_planner_success": False,
                "final_classification": "PLANNER_SCHEMA_FAILURE",
                "final_error_type": "ValidationError",
                "final_error_code": None,
                "final_facts": None,
            }
        )
    elif final_plan is not None:
        final_facts = _facts(final_plan, expected, registry)
        result.update(
            {
                "final_planner_success": True,
                "final_classification": _classify(final_facts),
                "final_error_type": None,
                "final_error_code": None,
                "final_facts": final_facts,
                "final_plan": p2._plan_projection(final_plan),
            }
        )
    else:
        raise AssertionError("Planner arm ended without a terminal result.")
    final_facts = result.get("final_facts") or {}
    result["work_unit_fragmentation"] = bool(final_facts.get("work_unit_fragmentation"))
    result["fragmentation_with_gap"] = bool(final_facts.get("fragmentation_with_gap"))
    result["single_task_closure_omission"] = bool(final_facts.get("single_task_closure_omission"))
    result["report_task_present"] = bool(final_facts.get("report_task_present"))
    result["final_contract_ok"] = result.get("final_classification") == "PLANNER_CONTRACT_OK"
    return result


async def run_shared_row(
    case: dict[str, object],
    *,
    attempt_index: int,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
    authorized_checkpoint: str | None = None,
) -> dict[str, object]:
    """Run all four arms against one shared planner/enrichment-independent input."""
    source_summary = p2.production_source_summary(case)
    shared_input = {
        "request": str(case["request"]),
        "mode": "reconstruct",
        "source_summary": source_summary,
    }
    row: dict[str, object] = {
        "experiment_version": EXPERIMENT_VERSION,
        "design_baseline_sha": BASELINE_SHA,
        "authorized_checkpoint": authorized_checkpoint,
        "harness_sha256": artifact_sha256(Path(__file__)),
        "corpus_sha256": EXPECTED_CORPUS_SHA256,
        "planner_source_sha256": EXPECTED_PLANNER_SOURCE_SHA256,
        "base_prompt_sha256": EXPECTED_PROMPT_SHA256,
        "catalog_sha256": EXPECTED_CATALOG_SHA256,
        "p2_historical_summary_sha256": EXPECTED_P2_SUMMARY_SHA256,
        "p2_historical_raw_sha256": EXPECTED_P2_RAW_SHA256,
        "work_unit_instruction_sha256": sha256_text(WORK_UNIT_INSTRUCTION),
        "report_instruction_sha256": sha256_text(REPORT_BOUNDARY_INSTRUCTION),
        "section_composition_instruction_sha256": sha256_text(SECTION_COMPOSITION_INSTRUCTION),
        "R_prompt_sha256": PROMPT_SHA256["R"],
        "WR_prompt_sha256": PROMPT_SHA256["WR"],
        "RW_prompt_sha256": PROMPT_SHA256["RW"],
        "RC_prompt_sha256": PROMPT_SHA256["RC"],
        "execution_controls": {
            "model": FROZEN_MODEL,
            "planner_temperature": PLANNER_TEMPERATURE,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_tokens_parameter": MAX_TOKENS_PARAMETER,
            "timeout_seconds": TIMEOUT_SECONDS,
        },
        "case_id": case["case_id"],
        "attempt_index": attempt_index,
        "request_sha256": sha256_text(shared_input["request"]),
        "source_summary_sha256": sha256_text(canonical_json(source_summary)),
        "expected_capability_ids": list(case["expected_capabilities"]),
        "arms": {},
    }
    for arm in ARMS:
        row["arms"][arm] = await run_arm(
            case,
            arm=arm,  # type: ignore[arg-type]
            delegate=delegate,
            registry=registry,
            attempt_index=attempt_index,
            shared_input=shared_input,
        )
    return row


def _arm(row: dict[str, object], arm: str) -> dict[str, object]:
    """Return one arm result from a shared evidence row."""
    arms = row.get("arms")
    if not isinstance(arms, dict):
        return {}
    result = arms.get(arm)
    return result if isinstance(result, dict) else {}


def _final_fact(
    arm_result: dict[str, object],
    key: str,
    default: object = False,
) -> object:
    """Read one final semantic fact without manufacturing facts for failures."""
    facts = arm_result.get("final_facts")
    if not isinstance(facts, dict):
        return default
    return facts.get(key, default)


def _phase_fact(
    arm_result: dict[str, object],
    phase: Literal["initial", "final"],
    key: str,
    default: object = False,
) -> object:
    """Read one initial or final semantic fact safely."""
    facts = arm_result.get("initial_facts") if phase == "initial" else arm_result.get("final_facts")
    if not isinstance(facts, dict):
        return default
    return facts.get(key, default)


def _phase_contract_ok(arm_result: dict[str, object], phase: Literal["initial", "final"]) -> bool:
    """Determine contract success for a structurally available plan phase."""
    facts = arm_result.get(f"{phase}_facts")
    if not isinstance(facts, dict):
        return False
    try:
        return final_contract_ok(facts)
    except KeyError:
        return False


def _pair_table(rows: list[dict[str, object]], left: str, right: str, key: str) -> dict[str, int]:
    """Count exact paired boolean transitions for one diagnostic metric."""
    counts = Counter()
    for row in rows:
        left_value = bool(_arm(row, left).get(key))
        right_value = bool(_arm(row, right).get(key))
        counts[(left_value, right_value)] += 1
    return {
        "both_true": counts[(True, True)],
        "left_true_only": counts[(True, False)],
        "right_true_only": counts[(False, True)],
        "both_false": counts[(False, False)],
    }


def _semantic_pair_table(
    rows: list[dict[str, object]],
    left: str,
    right: str,
    key: str,
    *,
    true_true: str,
    true_false: str,
    false_true: str,
    false_false: str,
) -> dict[str, int]:
    """Count semantic transitions only when both final fact dictionaries exist."""
    counts = Counter()
    for row in rows:
        left_facts = _arm(row, left).get("final_facts")
        right_facts = _arm(row, right).get("final_facts")
        if not isinstance(left_facts, dict) or not isinstance(right_facts, dict):
            counts["UNAVAILABLE"] += 1
            continue
        counts[(bool(left_facts.get(key)), bool(right_facts.get(key)))] += 1
    return {
        true_true: counts[(True, True)],
        true_false: counts[(True, False)],
        false_true: counts[(False, True)],
        false_false: counts[(False, False)],
        "UNAVAILABLE": counts["UNAVAILABLE"],
    }


def _full_contract_pair_table(table: dict[str, int]) -> dict[str, int]:
    """Rename full-contract boolean buckets without an availability bucket."""
    return {
        "BOTH_PASS": table["both_true"],
        "LEFT_ONLY_PASS": table["left_true_only"],
        "RIGHT_ONLY_PASS": table["right_true_only"],
        "BOTH_FAIL": table["both_false"],
    }


def factor_tables(rows: list[dict[str, object]]) -> dict[str, object]:
    """Build the required paired factor tables."""
    pairs = {
        "R_to_WR": ("R", "WR"),
        "WR_to_RW": ("WR", "RW"),
        "R_to_RW": ("R", "RW"),
        "R_to_RC": ("R", "RC"),
        "RW_to_RC": ("RW", "RC"),
        "WR_to_RC": ("WR", "RC"),
    }
    tables: dict[str, object] = {}
    for pair_name, (left, right) in pairs.items():
        raw = {"final_contract_ok": _pair_table(rows, left, right, "final_contract_ok")}
        tables[pair_name] = {
            "neutral": {"final_contract_ok": raw["final_contract_ok"]},
            "full_contract": _full_contract_pair_table(raw["final_contract_ok"]),
            "fragmentation": _semantic_pair_table(
                rows,
                left,
                right,
                "work_unit_fragmentation",
                true_true="FRAGMENTED_TO_FRAGMENTED",
                true_false="FRAGMENTED_TO_CORRECT",
                false_true="CORRECT_TO_FRAGMENTED",
                false_false="CORRECT_TO_CORRECT",
            ),
            "report_task": _semantic_pair_table(
                rows,
                left,
                right,
                "report_task_present",
                true_true="REPORT_PRESENT_TO_PRESENT",
                true_false="REPORT_PRESENT_TO_ABSENT",
                false_true="ABSENT_TO_PRESENT",
                false_false="ABSENT_TO_ABSENT",
            ),
        }
    return tables


def population_integrity(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    expected_checkpoint: str | None = None,
) -> tuple[bool, list[str]]:
    """Validate exact shared-row, arm, case, and checkpoint population shape."""
    expected_ids = {str(case["case_id"]) for case in cases}
    reasons: list[str] = []
    if len(rows) != len(cases) * ATTEMPTS:
        reasons.append("wrong_row_count")
    pairs = [(str(row.get("case_id")), row.get("attempt_index")) for row in rows]
    if len(set(pairs)) != len(pairs):
        reasons.append("duplicate_case_attempt")
    if {pair[0] for pair in pairs} != expected_ids:
        reasons.append("case_set_mismatch")
    by_case: dict[str, set[object]] = {}
    for case_id, attempt in pairs:
        by_case.setdefault(case_id, set()).add(attempt)
    if any(indexes != set(range(ATTEMPTS)) for indexes in by_case.values()):
        reasons.append("attempt_index_mismatch")
    if any(not isinstance(row.get("arms"), dict) or set(row["arms"]) != set(ARMS) for row in rows):
        reasons.append("arm_set_mismatch")
    checkpoints = {row.get("authorized_checkpoint") for row in rows}
    if None in checkpoints or len(checkpoints) != 1:
        reasons.append("authorized_checkpoint_missing_or_mixed")
    elif expected_checkpoint is not None and checkpoints != {expected_checkpoint}:
        reasons.append("authorized_checkpoint_mismatch")
    return not reasons, reasons


def _count_arm(rows: list[dict[str, object]], arm: str, key: str) -> int:
    """Count one boolean arm metric."""
    return sum(bool(_arm(row, arm).get(key)) for row in rows)


def _phase_metrics(
    rows: list[dict[str, object]],
    arm: str,
    phase: Literal["initial", "final"],
) -> dict[str, int]:
    """Aggregate semantic facts for one planner phase, excluding terminal failures."""
    available = [
        _arm(row, arm) for row in rows if isinstance(_arm(row, arm).get(f"{phase}_facts"), dict)
    ]
    prefix = f"{phase}_"
    return {
        f"{prefix}plan_available": sum(
            bool(_arm(row, arm).get(f"{phase}_plan_available")) for row in rows
        )
        if phase == "initial"
        else sum(bool(_arm(row, arm).get("final_planner_success")) for row in rows),
        f"{prefix}contract_passes": sum(_phase_contract_ok(_arm(row, arm), phase) for row in rows),
        f"{prefix}section_count_failures": sum(
            not bool(_phase_fact(result, phase, "section_count_ok")) for result in available
        ),
        f"{prefix}work_unit_fragmentation": sum(
            bool(_phase_fact(result, phase, "work_unit_fragmentation")) for result in available
        ),
        f"{prefix}fragmentation_with_gap": sum(
            bool(_phase_fact(result, phase, "fragmentation_with_gap")) for result in available
        ),
        f"{prefix}single_task_closure_omission": sum(
            bool(_phase_fact(result, phase, "single_task_closure_omission")) for result in available
        ),
        f"{prefix}report_task_present": sum(
            bool(_phase_fact(result, phase, "report_task_present")) for result in available
        ),
        f"{prefix}empty_report_task": sum(
            bool(_phase_fact(result, phase, "empty_report_task")) for result in available
        ),
        f"{prefix}nonempty_report_task": sum(
            bool(_phase_fact(result, phase, "report_task_present"))
            and not bool(_phase_fact(result, phase, "empty_report_task"))
            for result in available
        ),
        f"{prefix}union_exact_expected": sum(
            bool(_phase_fact(result, phase, "union_exact_expected")) for result in available
        ),
        f"{prefix}wrong_selection": sum(
            bool(_phase_fact(result, phase, "wrong_capability_selection")) for result in available
        ),
        f"{prefix}duplicates": sum(
            bool(_phase_fact(result, phase, "duplicate_capabilities")) for result in available
        ),
        f"{prefix}parent_closure_failures": sum(
            not bool(_phase_fact(result, phase, "parent_closure_valid")) for result in available
        ),
        f"{prefix}unresolved_requirements": sum(
            bool(_phase_fact(result, phase, "unresolved_present")) for result in available
        ),
    }


def _terminal_metrics(rows: list[dict[str, object]], arm: str) -> dict[str, int]:
    """Aggregate terminal planner outcomes without treating them as semantic facts."""
    results = [_arm(row, arm) for row in rows]
    return {
        "final_planner_success": sum(
            bool(result.get("final_planner_success")) for result in results
        ),
        "planner_semantic_failures": sum(
            result.get("final_classification") == "PLANNER_SEMANTIC_FAILURE" for result in results
        ),
        "planner_schema_failures": sum(
            result.get("final_classification") == "PLANNER_SCHEMA_FAILURE" for result in results
        ),
        "provider_infrastructure_failures": sum(
            bool(result.get("provider_infrastructure_failure")) for result in results
        ),
    }


def _correction_metrics(rows: list[dict[str, object]], arm: str) -> dict[str, int]:
    """Aggregate bounded correction and retry outcomes for one arm."""
    results = [_arm(row, arm) for row in rows]
    used = [bool(result.get("semantic_correction_used")) for result in results]
    return {
        "semantic_corrections": sum(used),
        "semantic_correction_recoveries": sum(
            used[index] and bool(results[index].get("final_contract_ok"))
            for index in range(len(results))
        ),
        "semantic_correction_failures": sum(
            used[index] and not bool(results[index].get("final_contract_ok"))
            for index in range(len(results))
        ),
        "invalid_response_retries": sum(
            bool(result.get("invalid_response_retry_used")) for result in results
        ),
        "rows_without_semantic_correction": sum(not item for item in used),
    }


def _new_wrong_selection(rows: list[dict[str, object]], arm: str) -> bool:
    """Return whether a candidate introduces wrong selection absent from WR."""
    return any(
        bool(_final_fact(_arm(row, arm), "wrong_capability_selection"))
        and not bool(_final_fact(_arm(row, "WR"), "wrong_capability_selection"))
        for row in rows
    )


def decision(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    expected_checkpoint: str | None = None,
) -> str:
    """Apply the frozen CM-57P4 candidate decision precedence."""
    complete, _ = population_integrity(rows, cases, expected_checkpoint=expected_checkpoint)
    if not complete:
        return "INCONCLUSIVE_PROMPT_INTERACTION_BISECT"
    if any(_arm(row, arm).get("provider_infrastructure_failure") for row in rows for arm in ARMS):
        return "INCONCLUSIVE_PROMPT_INTERACTION_BISECT"
    wr_passes = _count_arm(rows, "WR", "final_contract_ok")
    candidate_passes = {arm: _count_arm(rows, arm, "final_contract_ok") for arm in ("RW", "RC")}
    candidate_wrong = {arm: _new_wrong_selection(rows, arm) for arm in ("RW", "RC")}
    if all(candidate_passes[arm] < wr_passes for arm in candidate_passes):
        return "PROMPT_INTERACTION_REGRESSION"
    if all(candidate_wrong.values()):
        return "PROMPT_INTERACTION_REGRESSION"
    safe_candidates = [
        passes for arm, passes in candidate_passes.items() if not candidate_wrong[arm]
    ]
    if not safe_candidates:
        return "PROMPT_INTERACTION_REGRESSION"
    best = max(safe_candidates)
    if best == len(rows):
        return "PROMPT_INTERACTION_FULL_RECOVERY"
    if best > wr_passes:
        return "PROMPT_INTERACTION_PARTIAL_RECOVERY"
    return "PROMPT_INTERACTION_NO_RECOVERY"


def repeatability(rows: list[dict[str, object]]) -> dict[str, object]:
    """Compare final contract projections across the two attempts per case."""
    by_case: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_case.setdefault(str(row["case_id"]), []).append(row)
    stable: dict[str, list[str]] = {arm: [] for arm in ARMS}
    unstable: dict[str, list[str]] = {arm: [] for arm in ARMS}
    unavailable: dict[str, list[str]] = {arm: [] for arm in ARMS}
    for case_id, case_rows in sorted(by_case.items()):
        for arm in ARMS:
            values = [_arm(row, arm).get("final_facts") for row in case_rows]
            if len(values) != ATTEMPTS or any(value is None for value in values):
                unavailable[arm].append(case_id)
            elif values[0] == values[1]:
                stable[arm].append(case_id)
            else:
                unstable[arm].append(case_id)
    return {"stable_cases": stable, "unstable_cases": unstable, "unavailable_cases": unavailable}


def sentinel_rows(rows: list[dict[str, object]]) -> dict[str, object]:
    """Return bounded diagnostics for the authorized historical sentinel cases."""
    wanted = {
        "mixed_curve_raster_section",
        "generic_profile_paraphrase",
        "waveform_profile_paraphrase",
        "independent_sample_bounds",
    }
    output: dict[str, object] = {}
    for row in rows:
        case_id = str(row.get("case_id"))
        if case_id not in wanted or row.get("attempt_index") not in {0, 1}:
            continue
        output[f"{case_id}/attempt_{row['attempt_index']}"] = {
            arm: {
                "initial_section_task_count": (
                    _arm(row, arm).get("initial_facts", {}).get("section_task_count")
                    if isinstance(_arm(row, arm).get("initial_facts"), dict)
                    else None
                ),
                "initial_capability_ids": (
                    _arm(row, arm).get("initial_facts", {}).get("section_capability_ids")
                    if isinstance(_arm(row, arm).get("initial_facts"), dict)
                    else None
                ),
                "initial_missing_capabilities": (
                    _arm(row, arm).get("initial_facts", {}).get("union_missing_capabilities")
                    if isinstance(_arm(row, arm).get("initial_facts"), dict)
                    else None
                ),
                "correction_used": bool(_arm(row, arm).get("semantic_correction_used")),
                "final_section_task_count": (
                    _arm(row, arm).get("final_facts", {}).get("section_task_count")
                    if isinstance(_arm(row, arm).get("final_facts"), dict)
                    else None
                ),
                "final_capability_ids": (
                    _arm(row, arm).get("final_facts", {}).get("section_capability_ids")
                    if isinstance(_arm(row, arm).get("final_facts"), dict)
                    else None
                ),
                "final_missing_capabilities": (
                    _arm(row, arm).get("final_facts", {}).get("union_missing_capabilities")
                    if isinstance(_arm(row, arm).get("final_facts"), dict)
                    else None
                ),
                "final_contract_ok": bool(_arm(row, arm).get("final_contract_ok")),
            }
            for arm in ARMS
        }
    return output


def summarize_population(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    authorized_checkpoint: str | None = None,
) -> dict[str, object]:
    """Build bounded aggregate evidence for a completed four-arm population."""
    complete, reasons = population_integrity(rows, cases, expected_checkpoint=authorized_checkpoint)
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
        "arm_metrics": {
            arm: {
                **_phase_metrics(rows, arm, "initial"),
                **_phase_metrics(rows, arm, "final"),
                **_terminal_metrics(rows, arm),
                **_correction_metrics(rows, arm),
                "provider_calls": sum(
                    int(_arm(row, arm).get("planner_call_count", 0)) for row in rows
                ),
            }
            for arm in ARMS
        },
        "factor_tables": factor_tables(rows),
        "repeatability": repeatability(rows),
        "sentinels": sentinel_rows(rows),
        "controls": {
            "model": FROZEN_MODEL,
            "planner_temperature": PLANNER_TEMPERATURE,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_tokens_parameter": MAX_TOKENS_PARAMETER,
            "timeout_seconds": TIMEOUT_SECONDS,
        },
    }


def verify_frozen_contract() -> dict[str, object]:
    """Verify P2, corpus, planner, catalog, and prompt anchors before live use."""
    contract = p2.verify_frozen_contract()
    p2_summary_sha = artifact_sha256(HISTORICAL_SUMMARY_PATH)
    if p2_summary_sha != EXPECTED_P2_SUMMARY_SHA256:
        raise RuntimeError("CM-57P2 live summary bytes drifted.")
    p2_summary = json.loads(HISTORICAL_SUMMARY_PATH.read_text(encoding="utf-8"))
    if p2_summary.get("decision") != "PLANNER_CONTRACT_REGRESSION":
        raise RuntimeError("CM-57P2 live decision anchor drifted.")
    raw_evidence = p2_summary.get("raw_evidence", {})
    if raw_evidence.get("sha256") != EXPECTED_P2_RAW_SHA256 or raw_evidence.get("rows") != 32:
        raise RuntimeError("CM-57P2 raw evidence anchor drifted.")
    p3_script = REPO_ROOT / "scripts/cm57p3_work_unit_bisect.py"
    if artifact_sha256(p3_script) != EXPECTED_P3_SCRIPT_SHA256:
        raise RuntimeError("CM-57P4 P3 harness anchor drifted.")
    p3_summary_path = REPO_ROOT / "docs/evaluations/agent-code-mode/CM-57P3-live-summary.json"
    if artifact_sha256(p3_summary_path) != EXPECTED_P3_SUMMARY_SHA256:
        raise RuntimeError("CM-57P4 P3 summary anchor drifted.")
    p3_summary = json.loads(p3_summary_path.read_text(encoding="utf-8"))
    live_evidence = p3_summary.get("live_evidence", {})
    if (
        p3_summary.get("decision") != "PROMPT_CONTRACT_PARTIAL_RECOVERY"
        or live_evidence.get("authorized_checkpoint") != EXPECTED_P3_CHECKPOINT
        or live_evidence.get("raw_rows") != 32
        or live_evidence.get("raw_sha256") != EXPECTED_P3_RAW_SHA256
    ):
        raise RuntimeError("CM-57P4 live evidence anchor drifted.")
    if artifact_sha256(CASE_PATH) != EXPECTED_CORPUS_SHA256:
        raise RuntimeError("CM-57P4 corpus drifted.")
    if sha256_text(_PLANNER_SYSTEM_PROMPT) != EXPECTED_PROMPT_SHA256:
        raise RuntimeError("CM-57P4 base planner prompt drifted.")
    expected = {
        "W": sha256_text(WORK_UNIT_INSTRUCTION),
        "R": sha256_text(REPORT_BOUNDARY_INSTRUCTION),
        "C": sha256_text(SECTION_COMPOSITION_INSTRUCTION),
    }
    return {
        **contract,
        "experiment_version": EXPERIMENT_VERSION,
        "base_prompt_sha256": EXPECTED_PROMPT_SHA256,
        "work_unit_instruction_sha256": expected["W"],
        "report_instruction_sha256": expected["R"],
        "section_composition_instruction_sha256": expected["C"],
        "prompt_sha256": dict(PROMPT_SHA256),
        "p2_summary_sha256": p2_summary_sha,
        "p3_summary_sha256": EXPECTED_P3_SUMMARY_SHA256,
    }


def _self_test_classification(cases: tuple[dict[str, object], ...]) -> None:
    """Exercise provider-free P4 classification, pairing, and decision branches."""
    case = cases[0]
    registry = create_builtin_registry()
    expected = list(case["expected_capabilities"])
    exact = SemanticPlan(
        summary="one section",
        section_tasks=(SectionTask(goal="section", capability_ids=tuple(expected)),),
    )
    fragmented = SemanticPlan(
        summary="split section",
        section_tasks=tuple(
            SectionTask(goal="part", capability_ids=(capability,)) for capability in expected
        ),
    )
    report = SemanticPlan(
        summary="polluted",
        report_task=ReportTask(goal="placeholder"),
        section_tasks=(SectionTask(goal="section", capability_ids=tuple(expected)),),
    )
    assert final_contract_ok(_facts(exact, expected, registry))
    assert _facts(fragmented, expected, registry)["work_unit_fragmentation"]
    assert _facts(report, expected, registry)["report_task_present"]
    rows: list[dict[str, object]] = []
    for case_item in cases:
        for attempt in range(ATTEMPTS):
            rows.append(
                {
                    "case_id": case_item["case_id"],
                    "attempt_index": attempt,
                    "authorized_checkpoint": BASELINE_SHA,
                    "arms": {
                        arm: {
                            "final_contract_ok": True,
                            "provider_infrastructure_failure": False,
                            "work_unit_fragmentation": False,
                            "report_task_present": False,
                            "final_facts": {"wrong_capability_selection": False},
                        }
                        for arm in ARMS
                    },
                }
            )
    assert (
        decision(rows, cases, expected_checkpoint=BASELINE_SHA)
        == "PROMPT_INTERACTION_FULL_RECOVERY"
    )
    rows[0]["arms"]["RW"]["final_contract_ok"] = False
    rows[1]["arms"]["RC"]["final_contract_ok"] = False
    rows[2]["arms"]["WR"]["final_contract_ok"] = False
    rows[3]["arms"]["WR"]["final_contract_ok"] = False
    assert (
        decision(rows, cases, expected_checkpoint=BASELINE_SHA)
        == "PROMPT_INTERACTION_PARTIAL_RECOVERY"
    )
    for row in rows:
        row["arms"]["RW"]["final_contract_ok"] = False
        row["arms"]["RC"]["final_contract_ok"] = False
    assert (
        decision(rows, cases, expected_checkpoint=BASELINE_SHA) == "PROMPT_INTERACTION_REGRESSION"
    )


def prelive_report() -> dict[str, object]:
    """Run all provider-free guards and describe the future matrix."""
    contract = verify_frozen_contract()
    cases = p2.load_case_definitions(CASE_PATH)
    _self_test_classification(cases)
    return {
        "status": "PRELIVE_READY",
        "experiment_version": EXPERIMENT_VERSION,
        "baseline_sha": BASELINE_SHA,
        "provider_calls": 0,
        "worker_calls": 0,
        "production_changes": 0,
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
            "shared_rows": len(cases) * ATTEMPTS,
            "planner_executions": len(cases) * ATTEMPTS * len(ARMS),
            "provider_calls_min": len(cases) * ATTEMPTS * len(ARMS),
            "provider_calls_max": len(cases) * ATTEMPTS * len(ARMS) * 2,
        },
        "arms": list(ARMS),
        "decision_self_tests": "PASS",
        "live_inference": "NOT_STARTED",
    }


def _git_output(*arguments: str) -> bytes:
    """Return exact output from a repository-local Git command."""
    return subprocess.check_output(["git", *arguments], cwd=REPO_ROOT, stderr=subprocess.STDOUT)


def current_checkout_sha() -> str:
    """Return the current checkout's full commit SHA."""
    return _git_output("rev-parse", "HEAD").decode().strip()


def verify_reviewed_checkout(checkpoint: str) -> None:
    """Require the future live checkout to match its reviewed checkpoint."""
    if CHECKPOINT_RE.fullmatch(checkpoint) is None:
        raise ValueError("CM-57P4 requires a full lowercase checkpoint SHA.")
    if current_checkout_sha() != checkpoint:
        raise RuntimeError("CM-57P4 checkout does not match the authorized checkpoint.")
    guarded = (
        "scripts/cm57p2_planner_shadow.py",
        "scripts/cm57p3_work_unit_bisect.py",
        "src/wellplot/agent/code_mode/planner.py",
        "src/wellplot/capabilities/base.py",
        "src/wellplot/capabilities/registry.py",
        "src/wellplot/capabilities/builtins.py",
        "tests/fixtures/typed_worker/cm57c_shadow_cases.json",
        "docs/evaluations/agent-code-mode/CM-57P2-live-summary.json",
        "docs/evaluations/agent-code-mode/CM-57P3-live-summary.json",
    )
    for relative_path in guarded:
        path = REPO_ROOT / relative_path
        if path.read_bytes() != _git_output("show", f"{checkpoint}:{relative_path}"):
            raise RuntimeError(f"CM-57P4 guarded artifact drifted: {relative_path}")


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
        raise RuntimeError("No CM-57P4 API key configured.")
    return OpenAICompatibleBackendV2(
        model=FROZEN_MODEL,
        client=AsyncOpenAI(api_key=api_key, base_url=args.base_url, timeout=TIMEOUT_SECONDS),
        structured_output="json_schema",
        max_tokens_parameter=MAX_TOKENS_PARAMETER,
    )


async def _run_live(args: argparse.Namespace, checkpoint: str) -> None:
    """Run the future 32-row matrix incrementally and stop after aggregation."""
    if OUTPUT_PATH.exists() and OUTPUT_PATH.stat().st_size:
        raise RuntimeError(f"Refusing to append to non-empty evidence path {OUTPUT_PATH}.")
    verify_reviewed_checkout(checkpoint)
    verify_frozen_contract()
    cases = p2.load_case_definitions(CASE_PATH)
    registry = create_builtin_registry()
    backend = _provider_configuration(args)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
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
    """Build the provider-free default and explicit future live path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-authorized", action="store_true")
    parser.add_argument("--authorized-checkpoint")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="LLAMA_CPP_API_KEY")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run pre-live checks unless the separately authorized live flag is set."""
    args = _parser().parse_args(argv)
    if not args.live_authorized:
        print(json.dumps(prelive_report(), indent=2, sort_keys=True))
        return 0
    if not args.authorized_checkpoint or not args.base_url:
        raise SystemExit("Live CM-57P4 requires --authorized-checkpoint and --base-url.")
    asyncio.run(_run_live(args, args.authorized_checkpoint))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
