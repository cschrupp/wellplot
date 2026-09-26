"""CM-57P2 planner-only shadow evaluation harness.

The harness exercises the production :class:`SemanticPlanner` boundary and
stops before enrichment, typed workers, compilation, persistence, or routing.
The default command performs only deterministic pre-live checks.  Provider
construction is available only behind the explicit future live authorization
flags.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from scripts.cm56_post_r4_typed_shadow import production_source_summary
from wellplot.agent.code_mode.planner import (
    PlannerSemanticFailure,
    SemanticPlan,
    SemanticPlanner,
    _planning_catalog,
)
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry

REPO_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm57c_shadow_cases.json"
HISTORICAL_SUMMARY_PATH = REPO_ROOT / "docs/evaluations/agent-code-mode/CM-57C-live-summary.json"
OUTPUT_PATH = Path("/tmp/cm57p2-planner-qwen.jsonl")

BASELINE_SHA = "474f6b014457e06e561db6e72ba3d6faa0605b8e"
EXPERIMENT_VERSION = "CM-57P2"
CORPUS_VERSION = "cm57c.shadow.v1"
FROZEN_MODEL = "qwen3.6-35b-a3b"
PLANNER_TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 16384
MAX_TOKENS_PARAMETER = "max_tokens"
TIMEOUT_SECONDS = 900.0
ATTEMPTS = 2

EXPECTED_PROMPT_SHA256 = "5e7a0732af01e4b1f16b3ccf019c005ea2e9ba5c0e93e94870a56a261e2bca18"
EXPECTED_PLANNER_SOURCE_SHA256 = "0189b290ef4f76bdd776fe2612c454809ff77725379def7d8c5a98d9ae165413"
EXPECTED_CATALOG_SHA256 = "b1b9c85db961cb8b97f1c8b6f914a6a75f5bf57cf49ca4413c64d35311b80d37"
EXPECTED_CORPUS_SHA256 = "3acac04abbe8d20902bc1785d71cf3b8b0a9d7caf623ea79ed2eca8617842181"
EXPECTED_HISTORICAL_SUMMARY_SHA256 = (
    "97636abb8826d5039e2dd3878ce828126e9f6f6dbcb077d82aa9d45e673cdedf"
)
EXPECTED_HISTORICAL_RAW_SHA256 = "57df9720bc2eb7b05fcb815de84062815382b13c84f5878da8c948e08e41cba8"
EXPECTED_SOURCE_MATRIX_SHA256 = "7be957d4bd3361457206bbce689c612727cec5c4a3d4cbf392c4dcca52203d8b"

CHECKPOINT_RE = re.compile(r"^[0-9a-f]{40}$")
PATH_RE = re.compile(r"(?<!\w)(?:[A-Za-z]:[\\/]|/)[^\s,;]+")
GUARDED_FILES = (
    "scripts/cm57p2_planner_shadow.py",
    "scripts/cm57c_shadow_generalization.py",
    "scripts/cm56_post_r4_typed_shadow.py",
    "scripts/cm56_typed_section_shadow.py",
    "src/wellplot/agent/code_mode/planner.py",
    "src/wellplot/capabilities/base.py",
    "src/wellplot/capabilities/registry.py",
    "src/wellplot/capabilities/builtins.py",
    "tests/fixtures/typed_worker/cm57c_shadow_cases.json",
    str(HISTORICAL_SUMMARY_PATH.relative_to(REPO_ROOT)),
)
GUARDED_DIRECTORIES = ("tests/fixtures/typed_worker/cm56_sources",)


def canonical_json(value: object) -> str:
    """Serialize JSON-shaped evidence deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(value: bytes) -> str:
    """Return the SHA-256 digest of exact bytes."""
    return hashlib.sha256(value).hexdigest()


def artifact_sha256(path: Path) -> str:
    """Hash one repository artifact by exact bytes."""
    return sha256_bytes(path.read_bytes())


def validate_authorized_checkpoint(value: object) -> str:
    """Require a complete lowercase Git checkpoint for future live use."""
    if not isinstance(value, str) or CHECKPOINT_RE.fullmatch(value) is None:
        raise ValueError("CM-57P2 requires a full lowercase 40-character checkpoint SHA.")
    return value


def _git_output(*arguments: str) -> bytes:
    """Return exact output from a repository-local Git command."""
    return subprocess.check_output(["git", *arguments], cwd=REPO_ROOT, stderr=subprocess.STDOUT)


def current_checkout_sha() -> str:
    """Return the current checkout's full commit SHA."""
    return _git_output("rev-parse", "HEAD").decode().strip()


def load_case_definitions(path: Path = CASE_PATH) -> tuple[dict[str, object], ...]:
    """Load and validate the frozen CM-57C corpus without changing it."""
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if artifact.get("version") != CORPUS_VERSION:
        raise ValueError("Unexpected CM-57C corpus version.")
    cases = artifact.get("cases")
    if not isinstance(cases, list) or len(cases) != 16:
        raise ValueError("CM-57P2 requires exactly 16 frozen cases.")
    case_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("CM-57C corpus cases must be objects.")
        case_id = case.get("case_id")
        expected = case.get("expected_capabilities")
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            raise ValueError("CM-57C corpus case IDs must be unique non-empty strings.")
        if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
            raise ValueError(f"Case {case_id!r} has invalid expected capabilities.")
        case_ids.add(case_id)
    return tuple(cases)


def _historical_summary() -> tuple[dict[str, object], str, dict[str, tuple[str, ...]]]:
    """Validate the frozen CM-57C summary and return historical outcomes."""
    summary_sha = artifact_sha256(HISTORICAL_SUMMARY_PATH)
    if summary_sha != EXPECTED_HISTORICAL_SUMMARY_SHA256:
        raise RuntimeError("CM-57C historical summary bytes drifted.")
    summary = json.loads(HISTORICAL_SUMMARY_PATH.read_text(encoding="utf-8"))
    raw = summary.get("raw_evidence", {})
    population = summary.get("population", {})
    provider = summary.get("provider", {})
    if raw.get("sha256") != EXPECTED_HISTORICAL_RAW_SHA256 or raw.get("rows") != 32:
        raise RuntimeError("CM-57C historical raw evidence guard failed.")
    if population.get("expected_rows") != 32 or population.get("actual_rows") != 32:
        raise RuntimeError("CM-57C historical population guard failed.")
    if provider.get("planner_provider_calls") != 43:
        raise RuntimeError("CM-57C historical planner-call guard failed.")
    if provider.get("provider_infrastructure_failures") != 0:
        raise RuntimeError("CM-57C historical provider-infrastructure guard failed.")
    if summary.get("pipeline_counts", {}).get("PLANNER_FAILURE") != 21:
        raise RuntimeError("CM-57C historical planner-failure guard failed.")
    case_results = summary.get("case_results")
    if not isinstance(case_results, dict) or len(case_results) != 16:
        raise RuntimeError("CM-57C historical case-result guard failed.")
    historical: dict[str, tuple[str, ...]] = {}
    for case_id, result in case_results.items():
        pipeline = result.get("pipeline") if isinstance(result, dict) else None
        if not isinstance(pipeline, list) or len(pipeline) != 2:
            raise RuntimeError(f"Historical attempts for {case_id!r} are invalid.")
        historical[case_id] = tuple(str(value) for value in pipeline)
    return summary, summary_sha, historical


def _source_matrix(cases: tuple[dict[str, object], ...]) -> tuple[list[dict[str, object]], str]:
    """Build and hash the exact production path-free source-summary matrix."""
    matrix = [production_source_summary(case) for case in cases]
    serialized = canonical_json(matrix)
    if PATH_RE.search(serialized) or "candidate_id" in serialized:
        raise RuntimeError("Production source summary leaked host identity or a path.")
    return matrix, sha256_bytes(serialized.encode("utf-8"))


def verify_frozen_contract() -> dict[str, object]:
    """Verify every frozen semantic input before any future provider construction."""
    cases = load_case_definitions()
    _, historical_summary_sha, _ = _historical_summary()
    _, source_summary_sha = _source_matrix(cases)
    registry = create_builtin_registry()
    from wellplot.agent.code_mode.planner import _PLANNER_SYSTEM_PROMPT

    prompt_sha = sha256_bytes(_PLANNER_SYSTEM_PROMPT.encode("utf-8"))
    planner_sha = artifact_sha256(REPO_ROOT / "src/wellplot/agent/code_mode/planner.py")
    catalog_sha = sha256_bytes(canonical_json(_planning_catalog(registry)).encode("utf-8"))
    if prompt_sha != EXPECTED_PROMPT_SHA256:
        raise RuntimeError("CM-57P1 planner prompt drifted.")
    if planner_sha != EXPECTED_PLANNER_SOURCE_SHA256:
        raise RuntimeError("CM-57P1 planner source drifted.")
    if catalog_sha != EXPECTED_CATALOG_SHA256:
        raise RuntimeError("CM-57P1 planner catalog projection drifted.")
    if artifact_sha256(CASE_PATH) != EXPECTED_CORPUS_SHA256:
        raise RuntimeError("CM-57C corpus drifted.")
    if historical_summary_sha != EXPECTED_HISTORICAL_SUMMARY_SHA256:
        raise RuntimeError("CM-57C historical summary drifted.")
    if source_summary_sha != EXPECTED_SOURCE_MATRIX_SHA256:
        raise RuntimeError("CM-57P2 source-summary matrix drifted.")
    return {
        "cases": len(cases),
        "corpus_sha256": EXPECTED_CORPUS_SHA256,
        "historical_summary_sha256": EXPECTED_HISTORICAL_SUMMARY_SHA256,
        "source_summary_matrix_sha256": EXPECTED_SOURCE_MATRIX_SHA256,
        "planner_prompt_sha256": EXPECTED_PROMPT_SHA256,
        "planner_source_sha256": EXPECTED_PLANNER_SOURCE_SHA256,
        "planner_catalog_sha256": EXPECTED_CATALOG_SHA256,
    }


def _plan_projection(plan: SemanticPlan) -> dict[str, object]:
    """Project only bounded planner shape evidence, never semantic prose."""
    return {
        "report_task_present": plan.report_task is not None,
        "report_capability_ids": (
            list(plan.report_task.capability_ids) if plan.report_task is not None else []
        ),
        "section_count": len(plan.section_tasks),
        "sections": [
            {
                "capability_ids": list(task.capability_ids),
                "source_hint_count": len(task.source_hints),
            }
            for task in plan.section_tasks
        ],
        "unresolved_count": len(plan.unresolved_requirements),
    }


def _parent_closure(plan: SemanticPlan, registry: CapabilityRegistry) -> bool:
    """Check selected parent closure without injecting or repairing IDs."""
    tasks: list[Any] = list(plan.section_tasks)
    if plan.report_task is not None:
        tasks.append(plan.report_task)
    for task in tasks:
        selected = set(task.capability_ids)
        try:
            specs = [registry.get(capability_id) for capability_id in task.capability_ids]
        except KeyError:
            return False
        for spec in specs:
            parents = tuple(spec.allowed_parents)
            if parents and not selected.intersection(parents):
                return False
    return True


def _contract_facts(
    plan: SemanticPlan,
    expected_capabilities: list[str],
    registry: CapabilityRegistry,
) -> dict[str, object]:
    """Return bounded comparison facts for one planner result."""
    section_capabilities = [
        capability_id for task in plan.section_tasks for capability_id in task.capability_ids
    ]
    expected_set = set(expected_capabilities)
    actual_set = set(section_capabilities)
    counts = Counter(section_capabilities)
    return {
        "report_task_present": plan.report_task is not None,
        "section_count": len(plan.section_tasks),
        "section_count_ok": len(plan.section_tasks) == 1,
        "unresolved_count": len(plan.unresolved_requirements),
        "unresolved_present": bool(plan.unresolved_requirements),
        "actual_capability_ids": section_capabilities,
        "actual_unique_capability_ids": sorted(actual_set),
        "missing_capabilities": sorted(expected_set - actual_set),
        "unexpected_capabilities": sorted(actual_set - expected_set),
        "duplicate_capabilities": sorted(
            capability_id for capability_id, count in counts.items() if count > 1
        ),
        "exact_unique_match": actual_set == expected_set
        and all(count == 1 for count in counts.values()),
        "parent_closure_valid": _parent_closure(plan, registry),
    }


def _initial_classification(facts: dict[str, object]) -> str:
    """Classify the first plan while preserving independent diagnostic flags."""
    gaps: list[str] = []
    if not facts["section_count_ok"]:
        gaps.append("work_unit")
    if facts["unexpected_capabilities"]:
        gaps.append("wrong_selection")
    if facts["missing_capabilities"]:
        gaps.append("omission")
    if facts["duplicate_capabilities"]:
        gaps.append("duplication")
    if not facts["parent_closure_valid"]:
        gaps.append("parent_closure")
    if facts["report_task_present"]:
        gaps.append("report")
    if facts["unresolved_present"]:
        gaps.append("unresolved")
    if len(gaps) > 1:
        return "INITIAL_MULTIPLE_CONTRACT_GAPS"
    if not gaps:
        return "INITIAL_CONTRACT_OK"
    return {
        "work_unit": "INITIAL_WORK_UNIT_MISMATCH",
        "wrong_selection": "INITIAL_WRONG_CAPABILITY_SELECTION",
        "omission": "INITIAL_CAPABILITY_CLOSURE_OMISSION",
        "duplication": "INITIAL_CAPABILITY_DUPLICATION",
        "parent_closure": "INITIAL_PARENT_CLOSURE_FAILURE",
        "report": "INITIAL_UNEXPECTED_REPORT_TASK",
        "unresolved": "INITIAL_UNRESOLVED_REQUIREMENTS",
    }[gaps[0]]


def _final_classification(facts: dict[str, object]) -> str:
    """Apply the frozen final planner-contract precedence."""
    if not facts["section_count_ok"]:
        return "WORK_UNIT_COUNT_MISMATCH"
    if facts["unexpected_capabilities"]:
        return "WRONG_CAPABILITY_SELECTION"
    if facts["missing_capabilities"]:
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


@dataclass
class RecordingBackend(ModelBackendProtocol):
    """Record bounded planner-call evidence around the actual provider."""

    delegate: ModelBackendProtocol
    calls: list[dict[str, object]]
    plans: list[SemanticPlan]
    program_calls: int = 0

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Delegate one structured request and retain no raw provider payload."""
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
            record.update({"outcome": "structured_output_failure"})
            self.calls.append(record)
            raise
        record["outcome"] = "structured_success"
        if isinstance(result.value, SemanticPlan):
            self.plans.append(result.value)
            record["plan"] = _plan_projection(result.value)
        record["metrics"] = result.metrics.public_metadata()
        self.calls.append(record)
        return result

    async def generate_program(self, request: object) -> object:
        """Fail if the planner shadow accidentally reaches a worker."""
        self.program_calls += 1
        raise AssertionError("CM-57P2 must not call program generation.")


def _provider_classification(error: ProviderRequestError) -> str:
    """Map provider categories to bounded planner evidence classes."""
    if error.category in {
        ProviderFailureCategory.INVALID_RESPONSE,
        ProviderFailureCategory.VALIDATION,
    }:
        return "PLANNER_SCHEMA_FAILURE"
    return "PROVIDER_INFRA_FAILURE"


async def run_planner_attempt(
    case: dict[str, object],
    *,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
    attempt_index: int,
    historical_status: str,
) -> dict[str, object]:
    """Run the production planner once and stop at its terminal boundary."""
    calls: list[dict[str, object]] = []
    backend = RecordingBackend(delegate=delegate, calls=calls, plans=[])
    planner = SemanticPlanner(backend=backend, registry=registry)
    expected = [str(value) for value in case["expected_capabilities"]]
    row: dict[str, object] = {
        "experiment_version": EXPERIMENT_VERSION,
        "authorized_baseline": BASELINE_SHA,
        "corpus_sha256": EXPECTED_CORPUS_SHA256,
        "historical_summary_sha256": EXPECTED_HISTORICAL_SUMMARY_SHA256,
        "source_summary_matrix_sha256": EXPECTED_SOURCE_MATRIX_SHA256,
        "planner_prompt_sha256": EXPECTED_PROMPT_SHA256,
        "planner_source_sha256": EXPECTED_PLANNER_SOURCE_SHA256,
        "planner_catalog_sha256": EXPECTED_CATALOG_SHA256,
        "execution_controls": {
            "model": FROZEN_MODEL,
            "planner_temperature": PLANNER_TEMPERATURE,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "max_tokens_parameter": MAX_TOKENS_PARAMETER,
            "timeout_seconds": TIMEOUT_SECONDS,
        },
        "case_id": case["case_id"],
        "attempt_index": attempt_index,
        "historical_pipeline": historical_status,
        "expected_capability_ids": expected,
    }
    initial_plan: SemanticPlan | None = None
    final_plan: SemanticPlan | None = None
    semantic_failure: PlannerSemanticFailure | None = None
    provider_error: ProviderRequestError | None = None
    schema_failure = False
    try:
        final_plan = await planner.plan(
            request=str(case["request"]),
            mode="reconstruct",
            source_summary=production_source_summary(case),
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
    if backend.plans:
        initial_plan = backend.plans[0]
    row["planner_call_count"] = len(calls)
    row["call_trace"] = calls
    row["program_call_count"] = backend.program_calls
    row["provider_failure_categories"] = [
        str(call["provider_category"])
        for call in calls
        if call.get("outcome") == "provider_failure"
    ]
    if provider_error is not None:
        row["final_planner_success"] = False
        row["final_classification"] = _provider_classification(provider_error)
        row["provider_infrastructure_failure"] = row["final_classification"] == (
            "PROVIDER_INFRA_FAILURE"
        )
        row["semantic_failure_code"] = None
    elif semantic_failure is not None:
        row["final_planner_success"] = False
        row["final_classification"] = "PLANNER_SEMANTIC_FAILURE"
        row["provider_infrastructure_failure"] = False
        row["semantic_failure_code"] = semantic_failure.code
    elif schema_failure:
        row["final_planner_success"] = False
        row["final_classification"] = "PLANNER_SCHEMA_FAILURE"
        row["provider_infrastructure_failure"] = False
        row["semantic_failure_code"] = None
    elif final_plan is not None:
        facts = _contract_facts(final_plan, expected, registry)
        row.update(
            {
                "final_planner_success": facts["exact_unique_match"]
                and facts["section_count_ok"]
                and not facts["report_task_present"]
                and not facts["unresolved_present"]
                and facts["parent_closure_valid"],
                "final_classification": _final_classification(facts),
                "final_facts": facts,
                "final_plan": _plan_projection(final_plan),
                "provider_infrastructure_failure": False,
                "semantic_failure_code": None,
            }
        )
    else:
        raise AssertionError("Planner attempt ended without a terminal result.")
    final_ok = row["final_classification"] == "PLANNER_CONTRACT_OK"
    row["historical_recovered"] = historical_status != "SUCCESS" and final_ok
    row["historical_success_regression"] = historical_status == "SUCCESS" and not final_ok
    row["initial_classification"] = None
    row["initial_plan"] = None
    row["initial_facts"] = None
    if initial_plan is not None:
        initial_facts = _contract_facts(initial_plan, expected, registry)
        row["initial_classification"] = _initial_classification(initial_facts)
        row["initial_plan"] = _plan_projection(initial_plan)
        row["initial_facts"] = initial_facts
    return row


def population_integrity(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    expected_checkpoint: str | None = None,
) -> tuple[bool, list[str]]:
    """Validate the exact future population shape and checkpoint provenance."""
    expected_ids = {str(case["case_id"]) for case in cases}
    reasons: list[str] = []
    if len(rows) != len(cases) * ATTEMPTS:
        reasons.append("wrong_row_count")
    pairs = [(str(row.get("case_id")), row.get("attempt_index")) for row in rows]
    if len(set(pairs)) != len(pairs):
        reasons.append("duplicate_case_attempt")
    if {pair[0] for pair in pairs} != expected_ids:
        reasons.append("case_set_mismatch")
    attempts_by_case: dict[str, set[object]] = {}
    for case_id, attempt_index in pairs:
        attempts_by_case.setdefault(case_id, set()).add(attempt_index)
    expected_attempts = set(range(ATTEMPTS))
    if any(indexes != expected_attempts for indexes in attempts_by_case.values()):
        reasons.append("attempt_index_mismatch")
    checkpoints = {row.get("authorized_checkpoint") for row in rows}
    if (
        None in checkpoints
        or not checkpoints
        or not all(isinstance(checkpoint, str) for checkpoint in checkpoints)
    ):
        reasons.append("authorized_checkpoint_missing")
    elif len(checkpoints) != 1:
        reasons.append("mixed_authorized_checkpoint")
    elif expected_checkpoint is not None and checkpoints != {expected_checkpoint}:
        reasons.append("authorized_checkpoint_mismatch")
    return not reasons, reasons


def planner_decision(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    expected_checkpoint: str | None = None,
) -> str:
    """Apply the frozen CM-57P2 decision precedence."""
    complete, _ = population_integrity(
        rows,
        cases,
        expected_checkpoint=expected_checkpoint,
    )
    if not complete:
        return "INCONCLUSIVE_PLANNER_EVALUATION"
    if any(row.get("provider_infrastructure_failure") for row in rows):
        return "INCONCLUSIVE_PLANNER_EVALUATION"
    transitions = transition_matrix(rows)
    historical_recovered = sum(bool(row.get("historical_recovered")) for row in rows)
    historical_regressions = sum(bool(row.get("historical_success_regression")) for row in rows)
    if (
        transitions["FAIL_TO_PASS"] != historical_recovered
        or transitions["PASS_TO_FAIL"] != historical_regressions
    ):
        return "INCONCLUSIVE_PLANNER_EVALUATION"
    if any(row.get("historical_success_regression") for row in rows):
        return "PLANNER_CONTRACT_REGRESSION"
    if any(row.get("final_classification") == "WRONG_CAPABILITY_SELECTION" for row in rows):
        return "PLANNER_CONTRACT_REGRESSION"
    successes = sum(row.get("final_classification") == "PLANNER_CONTRACT_OK" for row in rows)
    if successes == len(rows):
        return "PLANNER_CONTRACT_VALIDATED"
    if successes > 11:
        return "PLANNER_CONTRACT_IMPROVED_BUT_INCOMPLETE"
    return "PLANNER_CONTRACT_NOT_IMPROVED"


def repeatability(rows: list[dict[str, object]]) -> dict[str, object]:
    """Compare final bounded contract projections for the two attempts."""
    by_case: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_case.setdefault(str(row["case_id"]), []).append(row)
    stable: list[str] = []
    unstable: list[str] = []
    unavailable: list[str] = []
    for case_id, case_rows in sorted(by_case.items()):
        projections = [row.get("final_facts") for row in case_rows]
        if any(projection is None for projection in projections):
            unavailable.append(case_id)
        elif projections[0] == projections[1]:
            stable.append(case_id)
        else:
            unstable.append(case_id)
    return {"stable_cases": stable, "unstable_cases": unstable, "unavailable_cases": unavailable}


def transition_matrix(rows: list[dict[str, object]]) -> dict[str, int]:
    """Count historical planner PASS/FAIL to final contract PASS/FAIL paths."""
    transitions = Counter(
        (
            "PASS" if row.get("historical_pipeline") == "SUCCESS" else "FAIL",
            "PASS" if row.get("final_classification") == "PLANNER_CONTRACT_OK" else "FAIL",
        )
        for row in rows
    )
    return {
        "PASS_TO_PASS": transitions[("PASS", "PASS")],
        "PASS_TO_FAIL": transitions[("PASS", "FAIL")],
        "FAIL_TO_PASS": transitions[("FAIL", "PASS")],
        "FAIL_TO_FAIL": transitions[("FAIL", "FAIL")],
    }


def _initial_metric_counts(rows: list[dict[str, object]]) -> dict[str, int]:
    """Count independent initial planner-contract facts."""
    facts = [row.get("initial_facts") or {} for row in rows]
    return {
        "initial_closure_omissions": sum(bool(item.get("missing_capabilities")) for item in facts),
        "initial_duplicates": sum(bool(item.get("duplicate_capabilities")) for item in facts),
        "initial_parent_closure_failures": sum(
            not bool(item.get("parent_closure_valid", True)) for item in facts
        ),
        "initial_wrong_selections": sum(
            bool(item.get("unexpected_capabilities")) for item in facts
        ),
        "initial_unexpected_report_tasks": sum(
            bool(item.get("report_task_present")) for item in facts
        ),
        "initial_unresolved_requirements": sum(
            bool(item.get("unresolved_present")) for item in facts
        ),
    }


def _final_metric_counts(rows: list[dict[str, object]]) -> dict[str, int]:
    """Count independent final planner-contract facts."""
    facts = [row.get("final_facts") or {} for row in rows]
    return {
        "final_closure_omissions": sum(bool(item.get("missing_capabilities")) for item in facts),
        "final_duplicates": sum(bool(item.get("duplicate_capabilities")) for item in facts),
        "final_parent_closure_failures": sum(
            not bool(item.get("parent_closure_valid", True)) for item in facts if item
        ),
        "final_wrong_selections": sum(bool(item.get("unexpected_capabilities")) for item in facts),
        "final_unexpected_report_tasks": sum(
            bool(item.get("report_task_present")) for item in facts
        ),
        "final_unresolved_requirements": sum(
            bool(item.get("unresolved_present")) for item in facts
        ),
        "final_report_and_unresolved": sum(
            bool(item.get("report_task_present")) and bool(item.get("unresolved_present"))
            for item in facts
        ),
    }


def summarize_population(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    authorized_checkpoint: str | None = None,
) -> dict[str, object]:
    """Build bounded aggregate evidence for a completed future population."""
    complete, reasons = population_integrity(
        rows,
        cases,
        expected_checkpoint=authorized_checkpoint,
    )
    classifications = Counter(str(row.get("final_classification")) for row in rows)
    initial = Counter(str(row.get("initial_classification")) for row in rows)
    transitions = transition_matrix(rows)
    initial_metrics = _initial_metric_counts(rows)
    final_metrics = _final_metric_counts(rows)
    historical_recovered = sum(bool(row.get("historical_recovered")) for row in rows)
    historical_regressions = sum(bool(row.get("historical_success_regression")) for row in rows)
    transition_consistent = (
        transitions["FAIL_TO_PASS"] == historical_recovered
        and transitions["PASS_TO_FAIL"] == historical_regressions
    )
    if not transition_consistent:
        complete = False
        reasons.append("historical_transition_mismatch")
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "population": {
            "expected_rows": len(cases) * ATTEMPTS,
            "actual_rows": len(rows),
            "cases": len(cases),
            "attempts_per_case": ATTEMPTS,
            "complete": complete,
            "reasons": reasons,
        },
        "decision": planner_decision(
            rows,
            cases,
            expected_checkpoint=authorized_checkpoint,
        ),
        "final_classifications": dict(sorted(classifications.items())),
        "initial_classifications": dict(sorted(initial.items())),
        "historical_transitions": transitions,
        "historical_transition_total": sum(transitions.values()),
        "historical_transition_consistent": transition_consistent,
        "initial_contract_metrics": initial_metrics,
        "final_contract_metrics": final_metrics,
        "final_gate_counts": {
            "UNEXPECTED_REPORT_TASK": classifications.get("UNEXPECTED_REPORT_TASK", 0),
            "UNRESOLVED_REQUIREMENTS": classifications.get("UNRESOLVED_REQUIREMENTS", 0),
            "REPORT_AND_UNRESOLVED": classifications.get("REPORT_AND_UNRESOLVED", 0),
        },
        "metrics": {
            "planner_calls": sum(int(row.get("planner_call_count", 0)) for row in rows),
            "initial_ok": sum(
                row.get("initial_classification") == "INITIAL_CONTRACT_OK" for row in rows
            ),
            "initial_fail": sum(
                row.get("initial_classification") not in {None, "INITIAL_CONTRACT_OK"}
                for row in rows
            ),
            "invalid_response_retries": sum(
                any(
                    call.get("call_kind") == "INVALID_RESPONSE_RETRY"
                    for call in row.get("call_trace", ())
                )
                for row in rows
            ),
            "semantic_corrections_invoked": sum(
                any(
                    call.get("call_kind") == "SEMANTIC_CORRECTION"
                    for call in row.get("call_trace", ())
                )
                for row in rows
            ),
            "semantic_correction_recovered": sum(
                any(
                    call.get("call_kind") == "SEMANTIC_CORRECTION"
                    for call in row.get("call_trace", ())
                )
                and row.get("final_classification") == "PLANNER_CONTRACT_OK"
                for row in rows
            ),
            "semantic_correction_failed": sum(
                any(
                    call.get("call_kind") == "SEMANTIC_CORRECTION"
                    for call in row.get("call_trace", ())
                )
                and row.get("final_classification") != "PLANNER_CONTRACT_OK"
                for row in rows
            ),
            "initial_duplicates": sum(
                bool((row.get("initial_facts") or {}).get("duplicate_capabilities")) for row in rows
            ),
            "final_duplicates": sum(
                bool((row.get("final_facts") or {}).get("duplicate_capabilities")) for row in rows
            ),
            "parent_closure_failures": sum(
                not bool((row.get("final_facts") or {}).get("parent_closure_valid", True))
                for row in rows
            ),
            "closure_omissions": sum(
                row.get("final_classification") == "CAPABILITY_CLOSURE_OMISSION" for row in rows
            ),
            "final_ok": sum(
                row.get("final_classification") == "PLANNER_CONTRACT_OK" for row in rows
            ),
            "historical_recovered": historical_recovered,
            "historical_success_regressions": historical_regressions,
            "rows_no_correction": sum(
                not any(
                    call.get("call_kind") == "SEMANTIC_CORRECTION"
                    for call in row.get("call_trace", ())
                )
                for row in rows
            ),
        },
        "repeatability": repeatability(rows),
    }


def _self_test_decisions(cases: tuple[dict[str, object], ...]) -> None:
    """Exercise decision precedence without provider calls."""
    base = [
        {
            "case_id": case["case_id"],
            "attempt_index": attempt,
            "authorized_checkpoint": BASELINE_SHA,
            "historical_pipeline": "PLANNER_FAILURE",
            "final_classification": "PLANNER_CONTRACT_OK",
            "provider_infrastructure_failure": False,
            "historical_success_regression": False,
            "historical_recovered": True,
        }
        for case in cases
        for attempt in range(ATTEMPTS)
    ]
    assert planner_decision(base, cases, expected_checkpoint=BASELINE_SHA) == (
        "PLANNER_CONTRACT_VALIDATED"
    )
    regression = [dict(row) for row in base]
    regression[0]["final_classification"] = "WRONG_CAPABILITY_SELECTION"
    regression[0]["historical_recovered"] = False
    assert planner_decision(regression, cases, expected_checkpoint=BASELINE_SHA) == (
        "PLANNER_CONTRACT_REGRESSION"
    )
    incomplete = [dict(row) for row in base]
    for row in incomplete[:20]:
        row["final_classification"] = "PLANNER_SEMANTIC_FAILURE"
        row["historical_recovered"] = False
    assert planner_decision(incomplete, cases, expected_checkpoint=BASELINE_SHA) == (
        "PLANNER_CONTRACT_IMPROVED_BUT_INCOMPLETE"
    )
    not_improved = [dict(row) for row in base]
    for row in not_improved[:21]:
        row["final_classification"] = "PLANNER_SEMANTIC_FAILURE"
        row["historical_recovered"] = False
    for row in not_improved[21:]:
        row["final_classification"] = "PLANNER_CONTRACT_OK"
    assert planner_decision(not_improved, cases, expected_checkpoint=BASELINE_SHA) == (
        "PLANNER_CONTRACT_NOT_IMPROVED"
    )
    invalid = base[:-1]
    assert planner_decision(invalid, cases, expected_checkpoint=BASELINE_SHA) == (
        "INCONCLUSIVE_PLANNER_EVALUATION"
    )


def prelive_report() -> dict[str, object]:
    """Run all provider-free guards and return the future-run contract."""
    contract = verify_frozen_contract()
    cases = load_case_definitions()
    _self_test_decisions(cases)
    return {
        "status": "PRELIVE_READY",
        "experiment_version": EXPERIMENT_VERSION,
        "baseline_sha": BASELINE_SHA,
        "provider_calls": 0,
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
        "future_population": {"cases": len(cases), "rows": len(cases) * ATTEMPTS},
        "decision_self_tests": "PASS",
        "live_inference": "NOT_STARTED",
    }


def _guarded_paths_at_commit(checkpoint: str) -> tuple[str, ...]:
    """Return tracked files and source fixtures covered by live guards."""
    paths = list(GUARDED_FILES)
    for directory in GUARDED_DIRECTORIES:
        output = _git_output("ls-tree", "-r", "--name-only", checkpoint, "--", directory)
        paths.extend(line for line in output.decode().splitlines() if line)
    return tuple(sorted(set(paths)))


def verify_reviewed_checkout(checkpoint: str) -> None:
    """Reject future live execution if reviewed artifacts drifted."""
    checkpoint = validate_authorized_checkpoint(checkpoint)
    if current_checkout_sha() != checkpoint:
        raise RuntimeError("CM-57P2 checkout does not match the authorized checkpoint.")
    guarded_paths = _guarded_paths_at_commit(checkpoint)
    for relative_path in guarded_paths:
        path = REPO_ROOT / relative_path
        if not path.is_file() or path.read_bytes() != _git_output(
            "show", f"{checkpoint}:{relative_path}"
        ):
            raise RuntimeError(f"CM-57P2 guarded artifact drifted: {relative_path}")
    for directory in GUARDED_DIRECTORIES:
        root = REPO_ROOT / directory
        current = tuple(
            sorted(str(path.relative_to(REPO_ROOT)) for path in root.rglob("*") if path.is_file())
        )
        expected = tuple(path for path in guarded_paths if path.startswith(f"{directory}/"))
        if current != expected:
            raise RuntimeError(f"CM-57P2 guarded directory drifted: {directory}")


def _provider_configuration(args: argparse.Namespace) -> ModelBackendProtocol:
    """Construct the frozen provider only after all live guards pass."""
    from openai import AsyncOpenAI

    from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2

    api_key = os.getenv(args.api_key_env, "").strip()
    if args.api_key_file:
        key_path = Path(args.api_key_file)
        if not key_path.is_absolute():
            key_path = REPO_ROOT / key_path
        api_key = api_key or key_path.read_text(encoding="utf-8").strip()
    if not api_key:
        raise RuntimeError("No CM-57P2 API key configured.")
    return OpenAICompatibleBackendV2(
        model=FROZEN_MODEL,
        client=AsyncOpenAI(api_key=api_key, base_url=args.base_url, timeout=TIMEOUT_SECONDS),
        structured_output="json_schema",
        max_tokens_parameter=MAX_TOKENS_PARAMETER,
    )


async def _run_live(args: argparse.Namespace, checkpoint: str) -> None:
    """Run the future 32-row planner-only population incrementally."""
    checkpoint = validate_authorized_checkpoint(checkpoint)
    if OUTPUT_PATH.exists() and OUTPUT_PATH.stat().st_size:
        raise RuntimeError(f"Refusing to append to non-empty evidence path {OUTPUT_PATH}.")
    verify_reviewed_checkout(checkpoint)
    verify_frozen_contract()
    cases = load_case_definitions()
    _, source_hash = _source_matrix(cases)
    if source_hash != EXPECTED_SOURCE_MATRIX_SHA256:
        raise RuntimeError("CM-57P2 source-summary matrix drifted before live execution.")
    _, _, historical = _historical_summary()
    registry = create_builtin_registry()
    backend = _provider_configuration(args)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    with OUTPUT_PATH.open("a", encoding="utf-8") as handle:
        for case in cases:
            case_id = str(case["case_id"])
            for attempt_index in range(ATTEMPTS):
                row = await run_planner_attempt(
                    case,
                    delegate=backend,
                    registry=registry,
                    attempt_index=attempt_index,
                    historical_status=historical[case_id][attempt_index],
                )
                row["authorized_checkpoint"] = checkpoint
                rows.append(row)
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
                handle.flush()
    print(
        json.dumps(
            summarize_population(rows, cases, authorized_checkpoint=checkpoint),
            indent=2,
            sort_keys=True,
        )
    )


def _parser() -> argparse.ArgumentParser:
    """Build the provider-free default and explicitly gated live CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-authorized", action="store_true")
    parser.add_argument("--authorized-checkpoint")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="LLAMA_CPP_API_KEY")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run pre-live guards by default or the separately authorized live path."""
    args = _parser().parse_args(argv)
    if not args.live_authorized:
        print(json.dumps(prelive_report(), indent=2, sort_keys=True))
        return 0
    if not args.authorized_checkpoint or not args.base_url:
        raise SystemExit("Live CM-57P2 requires --authorized-checkpoint and --base-url.")
    checkpoint = validate_authorized_checkpoint(args.authorized_checkpoint)
    asyncio.run(_run_live(args, checkpoint))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
