"""CM-57P7 fresh promotion-quality planner evaluation.

The default command is provider-free.  Live execution is available only
behind the explicit authorization flags and is intentionally not part of the
pre-live implementation checkpoint.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import cm57p5_fresh_holdout as p5  # noqa: E402
from scripts import cm57p6_report_invariant_bisect as p6  # noqa: E402
from wellplot.agent.code_mode.planner import (  # noqa: E402
    _PLANNER_SYSTEM_PROMPT,
    PlannerSemanticFailure,
    SemanticPlan,
    SemanticPlanner,
)
from wellplot.agent.providers.base import (  # noqa: E402
    ModelBackendProtocol,
    StructuredGenerationRequest,
)
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry  # noqa: E402

CASE_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm57p7_fresh_promotion.json"
P5_SCRIPT_PATH = REPO_ROOT / "scripts/cm57p5_fresh_holdout.py"
P5_SUMMARY_PATH = REPO_ROOT / "docs/evaluations/agent-code-mode/CM-57P5-live-summary.json"
P6_SCRIPT_PATH = REPO_ROOT / "scripts/cm57p6_report_invariant_bisect.py"
P6_SUMMARY_PATH = REPO_ROOT / "docs/evaluations/agent-code-mode/CM-57P6-live-summary.json"
P6_MANIFEST_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm57p6_report_invariant_cases.json"
OUTPUT_PATH = Path("/tmp/cm57p7-fresh-promotion-qwen.jsonl")

BASELINE_SHA = "19e971740de9214a47b56afee4891ca82e8e32b5"
EXPERIMENT_VERSION = "CM-57P7"
CORPUS_VERSION = "cm57p7.fresh-promotion.v1"
FROZEN_MODEL = "qwen3.6-35b-a3b"
PLANNER_TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 16384
MAX_TOKENS_PARAMETER = "max_tokens"
TIMEOUT_SECONDS = 900.0
ATTEMPTS = 2
ARMS: tuple[str, ...] = ("P", "RC", "RCV", "RCS")
Arm = Literal["P", "RC", "RCV", "RCS"]
FAMILIES: tuple[str, ...] = (
    "REPORT_ONLY",
    "SINGLE_SECTION",
    "HETEROGENEOUS_SECTION",
    "MULTI_SECTION",
    "MIXED_REPORT_SECTION",
    "CAPABILITY_MULTIPLICITY",
)

EXPECTED_CORPUS_SHA256 = "4aebee0d2734cb272c6ae002aec277e58427dd5dce44e38e5fdf1a14a4dccd12"
EXPECTED_P5_SCRIPT_SHA256 = "3170c970d2ad4298f87c09cb106237d015356e4a5854095e3f889ba139bc600e"
EXPECTED_P5_SUMMARY_SHA256 = "16bda565e0687b6d7e9d3e9c2b6e053111355fb85ee97bfc6f34ffffbac0810d"
EXPECTED_P6_SCRIPT_SHA256 = "701380c0e21c71acadd4f1db1167d75ac24937f799693e1062a7b98785873768"
EXPECTED_P6_SUMMARY_SHA256 = "28d8a235192b7d7743b98c5138ea2e00aff0e144a2cd7982a72945620a802a55"
EXPECTED_P6_MANIFEST_SHA256 = "123af939d720cc7b7480445d9d421773b91c85b2615d8103e0d943ece1b4d10f"
EXPECTED_PLANNER_SOURCE_SHA256 = "0189b290ef4f76bdd776fe2612c454809ff77725379def7d8c5a98d9ae165413"
EXPECTED_PROVIDER_BASE_SHA256 = "4c14afc1e6e53faef1ef99266059b7b88b6c4dec4bfb5a4768ca5b36efc3f049"
EXPECTED_CATALOG_SHA256 = "b1b9c85db961cb8b97f1c8b6f914a6a75f5bf57cf49ca4413c64d35311b80d37"
EXPECTED_BASE_PROMPT_SHA256 = "5e7a0732af01e4b1f16b3ccf019c005ea2e9ba5c0e93e94870a56a261e2bca18"
EXPECTED_RC_PROMPT_SHA256 = "e1710cb516a96c47ec1d0593752e83aacc1bb4502c3026b2b6a9a676c90e4d34"
EXPECTED_SOURCE_SUMMARY_SHA256 = "ec6147a1b5e1ac6374e34ae3d66d11275542c6b340337cb26d3ae1d06240532e"
EXPECTED_PRODUCTION_SCHEMA_SHA256 = (
    "3a331166ccc570a74056dea7770d04b16f8fa32dc3641d6c37de6c26cf81d9e3"
)
EXPECTED_NONEMPTY_SCHEMA_SHA256 = "404357b174380f169c651147d988a02e8c6057bce451d18e295e85c3849af936"
CHECKPOINT_RE = re.compile(r"^[0-9a-f]{40}$")
PATH_RE = re.compile(r"(?<!\w)(?:[A-Za-z]:[\\/]|/)[^\s,;]+")

FIXED_EXECUTION_CONTROLS = {
    "model": FROZEN_MODEL,
    "planner_temperature": PLANNER_TEMPERATURE,
    "max_output_tokens": MAX_OUTPUT_TOKENS,
    "max_tokens_parameter": MAX_TOKENS_PARAMETER,
    "timeout_seconds": TIMEOUT_SECONDS,
}

FORBIDDEN_REQUEST_TERMS = (
    "SectionTask",
    "ReportTask",
    "SemanticPlan",
    "capability_ids",
    "expected_sections",
    "expected_report_capabilities",
    "minItems",
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
FIELD_KEYS = (
    "report_presence_correct",
    "report_capabilities_exact",
    "section_count_correct",
    "section_multiset_exact",
    "parent_closure_valid",
    "unresolved_correct",
    "no_duplicate_capability_type",
)


def canonical_json(value: object) -> str:
    """Serialize JSON-shaped values deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    """Hash exact UTF-8 text bytes."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def artifact_sha256(path: Path) -> str:
    """Hash one artifact by exact bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_output(*arguments: str) -> bytes:
    """Return output from a repository-local Git command."""
    import subprocess

    return subprocess.check_output(["git", *arguments], cwd=REPO_ROOT, stderr=subprocess.STDOUT)


def current_checkout_sha() -> str:
    """Return the current checkout commit SHA."""
    return _git_output("rev-parse", "HEAD").decode().strip()


def _normalized_request(request: str) -> str:
    """Normalize request text for cross-corpus freshness checks."""
    return " ".join(request.casefold().split())


def _fixed_source_summary_sha() -> str:
    """Return the frozen production-safe source-summary hash."""
    return sha256_text(p5.canonical_json(p5.FIXED_SOURCE_SUMMARY))


def _prompt_sha256(arm: Arm) -> str:
    """Return the exact system prompt hash for one arm."""
    return sha256_text(p5.RC_PROMPT if arm != "P" else _PLANNER_SYSTEM_PROMPT)


def _schema_sha256(arm: Arm) -> str:
    """Return the response schema hash used by one arm."""
    model = p6.NonEmptyReportSemanticPlan if arm == "RCS" else SemanticPlan
    return p6.schema_sha256(model)


def _registry_ids(registry: CapabilityRegistry) -> set[str]:
    """Return canonical capability IDs without widening the registry API."""
    return {spec.capability_id for spec in registry}


def load_case_definitions(path: Path = CASE_PATH) -> tuple[dict[str, object], ...]:
    """Load and validate the fresh 24-case promotion corpus."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != CORPUS_VERSION:
        raise ValueError("Unexpected CM-57P7 corpus version.")
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 24:
        raise ValueError("CM-57P7 requires exactly 24 cases.")
    registry = create_builtin_registry()
    previous = p5.load_case_definitions()
    previous_ids = {str(case["case_id"]) for case in previous}
    previous_requests = {_normalized_request(str(case["request"])) for case in previous}
    previous_hashes = p5._cm57c_request_hashes()
    seen_ids: set[str] = set()
    seen_requests: set[str] = set()
    family_counts: Counter[str] = Counter()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("CM-57P7 cases must be objects.")
        case_id = case.get("case_id")
        family = case.get("family")
        request = case.get("request")
        report = case.get("expected_report_capabilities")
        sections = case.get("expected_sections")
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError("CM-57P7 case IDs must be unique non-empty strings.")
        if case_id in previous_ids:
            raise ValueError("CM-57P7 case IDs must be new relative to P5/P6.")
        if family not in FAMILIES:
            raise ValueError(f"Unknown CM-57P7 family: {family!r}.")
        if not isinstance(request, str) or not request.strip() or PATH_RE.search(request):
            raise ValueError(f"Case {case_id!r} has unsafe request text.")
        normalized = _normalized_request(request)
        if normalized in seen_requests or normalized in previous_requests:
            raise ValueError(f"Case {case_id!r} reuses normalized request text.")
        if any(term.casefold() in request.casefold() for term in FORBIDDEN_REQUEST_TERMS):
            raise ValueError(f"Case {case_id!r} leaks planner vocabulary.")
        if any(value.casefold() in request.casefold() for value in CAPABILITY_IDS):
            raise ValueError(f"Case {case_id!r} leaks capability IDs.")
        if p5.sha256_text(request) in previous_hashes:
            raise ValueError(f"Case {case_id!r} reuses a historical request hash.")
        if not isinstance(report, list) or not all(isinstance(value, str) for value in report):
            raise ValueError(f"Case {case_id!r} has invalid report gold.")
        if not isinstance(sections, list) or not all(isinstance(value, list) for value in sections):
            raise ValueError(f"Case {case_id!r} has invalid section gold.")
        if case.get("expected_unresolved_count") != 0:
            raise ValueError("CM-57P7 permits only zero unresolved requirements.")
        p5._validate_report_gold(report, registry, case_id)
        for section in sections:
            p5._validate_section_gold(section, registry, case_id)
        seen_ids.add(case_id)
        seen_requests.add(normalized)
        family_counts[str(family)] += 1
    if family_counts != Counter(dict.fromkeys(FAMILIES, 4)):
        raise ValueError(f"CM-57P7 family distribution is invalid: {family_counts!r}.")
    return tuple(cases)


def frozen_provenance() -> dict[str, object]:
    """Return exact provenance fields for future live rows."""
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "design_baseline_sha": BASELINE_SHA,
        "harness_sha256": artifact_sha256(Path(__file__)),
        "corpus_sha256": artifact_sha256(CASE_PATH),
        "p5_harness_sha256": EXPECTED_P5_SCRIPT_SHA256,
        "p5_summary_sha256": EXPECTED_P5_SUMMARY_SHA256,
        "p6_harness_sha256": EXPECTED_P6_SCRIPT_SHA256,
        "p6_summary_sha256": EXPECTED_P6_SUMMARY_SHA256,
        "p6_manifest_sha256": EXPECTED_P6_MANIFEST_SHA256,
        "planner_source_sha256": EXPECTED_PLANNER_SOURCE_SHA256,
        "provider_base_sha256": EXPECTED_PROVIDER_BASE_SHA256,
        "catalog_sha256": EXPECTED_CATALOG_SHA256,
        "base_prompt_sha256": EXPECTED_BASE_PROMPT_SHA256,
        "RC_prompt_sha256": EXPECTED_RC_PROMPT_SHA256,
        "production_schema_sha256": p6.schema_sha256(SemanticPlan),
        "nonempty_schema_sha256": p6.schema_sha256(p6.NonEmptyReportSemanticPlan),
        "source_summary_sha256": _fixed_source_summary_sha(),
        "execution_controls": dict(FIXED_EXECUTION_CONTROLS),
    }


def _plan_facts(
    plan: SemanticPlan | None,
    case: dict[str, object],
    registry: CapabilityRegistry,
) -> dict[str, object] | None:
    """Project final planner facts through the accepted P5 evaluator."""
    return p5._facts(plan, case, registry) if plan is not None else None


def _arm_result(row: dict[str, object], arm: str) -> dict[str, object]:
    """Return one bounded arm result."""
    arms = row.get("arms")
    value = arms.get(arm) if isinstance(arms, dict) else None
    return value if isinstance(value, dict) else {}


def _facts(row: dict[str, object], arm: str) -> dict[str, object] | None:
    """Return final semantic facts when available."""
    value = _arm_result(row, arm).get("final_work_unit_facts")
    return value if isinstance(value, dict) else None


async def run_arm(
    case: dict[str, object],
    *,
    arm: Arm,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
) -> dict[str, object]:
    """Run one production or candidate planner arm with no worker path."""
    calls: list[dict[str, object]] = []
    plans: list[tuple[str, SemanticPlan]] = []
    forwarded_requests: list[StructuredGenerationRequest] = []
    forwarded_models: list[type[BaseModel]] = []
    recorder = p6.RecordingBackend(
        delegate=delegate,
        response_schema_sha256=_schema_sha256(arm),
        calls=calls,
        plans=plans,
    )
    if arm == "P":
        planner = SemanticPlanner(backend=recorder, registry=registry)
    elif arm == "RCV":
        prompt_backend = p6.PromptBackend(
            delegate=recorder,
            forwarded_requests=forwarded_requests,
            forwarded_response_models=forwarded_models,
        )
        planner = p6.InvariantSemanticPlanner(backend=prompt_backend, registry=registry)
    else:
        if arm == "RCS":
            prompt_backend = p6.SchemaPromptBackend(
                delegate=recorder,
                forwarded_requests=forwarded_requests,
                forwarded_response_models=forwarded_models,
            )
        else:
            prompt_backend = p6.PromptBackend(
                delegate=recorder,
                forwarded_requests=forwarded_requests,
                forwarded_response_models=forwarded_models,
            )
        planner = SemanticPlanner(backend=prompt_backend, registry=registry)
    final_plan: SemanticPlan | None = None
    error_type: str | None = None
    error_code: str | None = None
    final_classification: str | None = None
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
    except p6.ProviderRequestError as error:
        error_type = "ProviderRequestError"
        error_code = error.category.value
        final_classification = p6._provider_classification(error)
    except PlannerSemanticFailure as error:
        error_type = "PlannerSemanticFailure"
        error_code = error.code
        final_classification = "PLANNER_SEMANTIC_FAILURE"
    except ValidationError:
        error_type = "ValidationError"
        final_classification = "PLANNER_SCHEMA_FAILURE"
    initial_plan = next((plan for kind, plan in plans if kind == "INITIAL"), None)
    initial_facts = _plan_facts(initial_plan, case, registry)
    final_facts = _plan_facts(final_plan, case, registry)
    if final_plan is not None:
        final_classification = p5.classify_facts(final_facts or {})
    if final_classification is None:
        raise AssertionError("CM-57P7 arm ended without a terminal result.")
    return {
        "arm": arm,
        "prompt_sha256": _prompt_sha256(arm),
        "response_schema_sha256": _schema_sha256(arm),
        "provider_calls": len(calls),
        "program_calls": recorder.program_calls,
        "call_trace": calls,
        "initial_plan_available": initial_plan is not None,
        "initial_work_unit_facts": initial_facts,
        "invalid_response_retry_used": any(
            call.get("call_kind") == "INVALID_RESPONSE_RETRY" for call in calls
        ),
        "semantic_correction_used": any(
            call.get("call_kind") == "SEMANTIC_CORRECTION" for call in calls
        ),
        "final_planner_success": final_plan is not None,
        "final_error_type": error_type,
        "final_error_code": error_code,
        "final_work_unit_facts": final_facts,
        "final_classification": final_classification,
        "final_contract_ok": final_plan is not None and p5.final_contract_ok(final_facts or {}),
        "provider_infrastructure_failure": final_classification == "PROVIDER_INFRA_FAILURE",
        "final_plan": p5._plan_projection(final_plan) if final_plan is not None else None,
    }


async def run_shared_row(
    case: dict[str, object],
    *,
    attempt_index: int,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
    authorized_checkpoint: str | None,
) -> dict[str, object]:
    """Run all four arms for one shared request and context."""
    return {
        **frozen_provenance(),
        "authorized_checkpoint": authorized_checkpoint,
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


def _arm_metrics(rows: list[dict[str, object]], arm: str) -> dict[str, int]:
    """Aggregate bounded metrics for one arm."""
    results = [_arm_result(row, arm) for row in rows]
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
        "invalid_response_retries": sum(
            bool(result.get("invalid_response_retry_used")) for result in results
        ),
        "terminal_failures": sum(
            not bool(result.get("final_planner_success")) for result in results
        ),
        "infrastructure_failures": sum(
            bool(result.get("provider_infrastructure_failure")) for result in results
        ),
        "program_calls": sum(int(result.get("program_calls", 0)) for result in results),
    }


def _full_contract_table(rows: list[dict[str, object]], left: str, right: str) -> dict[str, int]:
    """Count paired final contract outcomes."""
    counts = Counter()
    for row in rows:
        left_pass = bool(_arm_result(row, left).get("final_contract_ok"))
        right_pass = bool(_arm_result(row, right).get("final_contract_ok"))
        counts[(left_pass, right_pass)] += 1
    return {
        "BOTH_PASS": counts[(True, True)],
        "P_ONLY_PASS": counts[(True, False)],
        "CANDIDATE_ONLY_PASS": counts[(False, True)],
        "BOTH_FAIL": counts[(False, False)],
    }


def _field_transition(
    rows: list[dict[str, object]], left: str, right: str, field: str
) -> dict[str, int]:
    """Count availability-aware field transitions."""
    counts = Counter()
    for row in rows:
        left_facts = _facts(row, left)
        right_facts = _facts(row, right)
        if left_facts is None or right_facts is None:
            counts["UNAVAILABLE"] += 1
        else:
            left_value = _field_correct(left_facts, field)
            right_value = _field_correct(right_facts, field)
            counts[(left_value, right_value)] += 1
    return {
        "CORRECT_TO_CORRECT": counts[(True, True)],
        "CORRECT_TO_WRONG": counts[(True, False)],
        "WRONG_TO_CORRECT": counts[(False, True)],
        "WRONG_TO_WRONG": counts[(False, False)],
        "UNAVAILABLE": counts["UNAVAILABLE"],
    }


def _field_correct(facts: dict[str, object], field: str) -> bool:
    """Return the correctness value for one P5 semantic fact."""
    if field == "no_duplicate_capability_type":
        return not bool(facts.get("duplicate_capability_type"))
    return bool(facts.get(field))


def _repeatability(rows: list[dict[str, object]], arm: str) -> dict[str, int]:
    """Count stable, unstable, and unavailable case pairs."""
    stable = unstable = unavailable = 0
    for case_id in {str(row["case_id"]) for row in rows}:
        pair = sorted(
            (row for row in rows if str(row["case_id"]) == case_id),
            key=lambda row: int(row["attempt_index"]),
        )
        values = [
            (_arm_result(row, arm).get("final_contract_ok"), _facts(row, arm)) for row in pair
        ]
        if len(values) != ATTEMPTS or any(facts is None for _, facts in values):
            unavailable += 1
        elif values[0] == values[1]:
            stable += 1
        else:
            unstable += 1
    return {"stable": stable, "unstable": unstable, "unavailable": unavailable}


def population_integrity(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    expected_checkpoint: str | None = None,
) -> tuple[bool, list[str]]:
    """Fail closed on population, provenance, arm, and execution drift."""
    reasons: set[str] = set()
    if len(rows) != len(cases) * ATTEMPTS:
        reasons.add("wrong_row_count")
    expected_ids = {str(case["case_id"]) for case in cases}
    pairs = [(str(row.get("case_id")), row.get("attempt_index")) for row in rows]
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
    expected = {str(case["case_id"]): case for case in cases}
    provenance = frozen_provenance()
    provenance_fields = tuple(provenance) + ("execution_controls",)
    for row in rows:
        case = expected.get(str(row.get("case_id")))
        if case is None:
            continue
        arms = row.get("arms")
        if not isinstance(arms, dict) or set(arms) != set(ARMS):
            reasons.add("arm_set_mismatch")
        if row.get("family") != case["family"]:
            reasons.add("family_mismatch")
        for field in provenance_fields:
            if row.get(field) != provenance[field]:
                reasons.add(f"{field}_mismatch")
        if row.get("request_sha256") != sha256_text(str(case["request"])):
            reasons.add("request_hash_mismatch")
        if row.get("expected_report_capabilities") != case["expected_report_capabilities"]:
            reasons.add("report_gold_mismatch")
        if row.get("expected_sections") != case["expected_sections"]:
            reasons.add("section_gold_mismatch")
        if row.get("expected_unresolved_count") != case["expected_unresolved_count"]:
            reasons.add("unresolved_gold_mismatch")
        for arm in ARMS:
            result = _arm_result(row, arm)
            if result.get("prompt_sha256") != _prompt_sha256(arm):
                reasons.add(f"{arm}_prompt_mismatch")
            if result.get("response_schema_sha256") != _schema_sha256(arm):
                reasons.add(f"{arm}_schema_mismatch")
            if int(result.get("program_calls", 0)) != 0:
                reasons.add("worker_program_call")
    return not reasons, sorted(reasons)


def _activation_cases(
    rows: list[dict[str, object]], cases: tuple[dict[str, object], ...]
) -> tuple[set[str], list[str]]:
    """Find two stable RC empty-report activations across required families."""
    by_id = {str(case["case_id"]): case for case in cases}
    activated: set[str] = set()
    for case_id, case in by_id.items():
        if case["family"] not in {"REPORT_ONLY", "MIXED_REPORT_SECTION"}:
            continue
        pair = [row for row in rows if str(row.get("case_id")) == case_id]
        if len(pair) != ATTEMPTS:
            continue
        if all(
            (_facts(row, "RC") or {}).get("report_task_present")
            and (_facts(row, "RC") or {}).get("report_capability_ids") == []
            and _arm_result(row, "RC").get("final_classification") == "REPORT_CAPABILITY_MISMATCH"
            for row in pair
        ):
            activated.add(case_id)
    families = {str(by_id[case_id]["family"]) for case_id in activated}
    reasons = []
    if len(activated) < 2 or not {"REPORT_ONLY", "MIXED_REPORT_SECTION"}.issubset(families):
        reasons.append("insufficient_rc_activation")
    return activated, reasons


def _candidate_viability(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    candidate: str,
    activations: set[str],
) -> dict[str, object]:
    """Evaluate one candidate against P using the frozen promotion gates."""
    report_correct = all(
        (_facts(row, candidate) or {}).get("report_presence_correct")
        and (_facts(row, candidate) or {}).get("report_capabilities_exact")
        for row in rows
    )
    activation_recovered = all(
        _activation_report_recovered(row, candidate)
        for row in rows
        if str(row.get("case_id")) in activations
    )
    full = _full_contract_table(rows, "P", candidate)
    field_tables = {field: _field_transition(rows, "P", candidate, field) for field in FIELD_KEYS}
    field_regressions = sum(table["CORRECT_TO_WRONG"] for table in field_tables.values())
    gains: set[str] = set()
    by_case = {str(case["case_id"]): case for case in cases}
    for case_id in by_case:
        pair = [row for row in rows if str(row.get("case_id")) == case_id]
        if len(pair) == ATTEMPTS and all(
            not bool(_arm_result(row, "P").get("final_contract_ok"))
            and bool(_arm_result(row, candidate).get("final_contract_ok"))
            for row in pair
        ):
            gains.add(case_id)
    gain_families = {str(by_case[case_id]["family"]) for case_id in gains}
    metrics = [_arm_result(row, candidate) for row in rows]
    no_terminal = all(bool(result.get("final_planner_success")) for result in metrics)
    no_infra = not any(bool(result.get("provider_infrastructure_failure")) for result in metrics)
    no_worker = not any(int(result.get("program_calls", 0)) for result in metrics)
    stable = _repeatability(rows, candidate)
    viable = bool(
        report_correct
        and activation_recovered
        and full["P_ONLY_PASS"] == 0
        and field_regressions == 0
        and len(gains) >= 4
        and len(gain_families) >= 2
        and no_terminal
        and no_infra
        and no_worker
        and stable == {"stable": len(cases), "unstable": 0, "unavailable": 0}
    )
    return {
        "viable": viable,
        "report_correct": report_correct,
        "activation_recovered": activation_recovered,
        "full_contract": full,
        "field_transitions": field_tables,
        "field_regressions": field_regressions,
        "stable_gains": sorted(gains),
        "stable_gain_families": sorted(gain_families),
        "no_terminal_failures": no_terminal,
        "no_infrastructure_failures": no_infra,
        "no_worker_calls": no_worker,
        "repeatability": stable,
    }


def decision(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    expected_checkpoint: str | None = None,
) -> str:
    """Apply the frozen promotion-quality decision precedence."""
    complete, _ = population_integrity(rows, cases, expected_checkpoint=expected_checkpoint)
    if not complete:
        return "INCONCLUSIVE_PROMOTION_EVALUATION"
    if any(
        bool(_arm_result(row, arm).get("provider_infrastructure_failure"))
        for row in rows
        for arm in ARMS
    ):
        return "INCONCLUSIVE_PROMOTION_EVALUATION"
    if any(
        _repeatability(rows, arm)["unstable"] or _repeatability(rows, arm)["unavailable"]
        for arm in ("P", "RC")
    ):
        return "INCONCLUSIVE_PROMOTION_EVALUATION"
    activations, activation_reasons = _activation_cases(rows, cases)
    if activation_reasons:
        return "INCONCLUSIVE_PROMOTION_EVALUATION"
    validator = _candidate_viability(rows, cases, "RCV", activations)
    schema = _candidate_viability(rows, cases, "RCS", activations)
    if validator["viable"] and schema["viable"]:
        return "PROMOTION_BOTH_VALIDATED"
    if schema["viable"]:
        return "PROMOTION_SCHEMA_ONLY_VALIDATED"
    if validator["viable"]:
        return "PROMOTION_VALIDATOR_ONLY_VALIDATED"
    return "PROMOTION_NO_CANDIDATE_VALIDATED"


def _efficiency(rows: list[dict[str, object]], left: str, right: str) -> str:
    """Compare total candidate provider calls after viability is known."""
    left_calls = sum(int(_arm_result(row, left).get("provider_calls", 0)) for row in rows)
    right_calls = sum(int(_arm_result(row, right).get("provider_calls", 0)) for row in rows)
    if left_calls < right_calls:
        return left
    if right_calls < left_calls:
        return right
    return "TIE"


def _activation_report_recovered(row: dict[str, object], arm: str) -> bool:
    """Check only the repaired report invariant for an activation row."""
    result = _arm_result(row, arm)
    facts = _facts(row, arm)
    return bool(
        result.get("final_planner_success")
        and facts
        and facts.get("report_task_present")
        and facts.get("report_capabilities_exact")
        and facts.get("report_presence_correct")
        and result.get("final_classification")
        not in {
            "REPORT_PRESENCE_MISMATCH",
            "REPORT_CAPABILITY_MISMATCH",
        }
    )


def summarize_population(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    authorized_checkpoint: str | None = None,
) -> dict[str, object]:
    """Build bounded aggregate evidence for a completed future matrix."""
    complete, reasons = population_integrity(rows, cases, expected_checkpoint=authorized_checkpoint)
    activation_cases, activation_reasons = _activation_cases(rows, cases)
    viability = {
        arm: _candidate_viability(rows, cases, arm, activation_cases) for arm in ("RCV", "RCS")
    }
    final_decision = decision(rows, cases, expected_checkpoint=authorized_checkpoint)
    efficiency = (
        _efficiency(rows, "RCV", "RCS")
        if final_decision
        in {
            "PROMOTION_BOTH_VALIDATED",
            "PROMOTION_SCHEMA_ONLY_VALIDATED",
            "PROMOTION_VALIDATOR_ONLY_VALIDATED",
        }
        else "NOT_APPLICABLE"
    )
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "decision": final_decision,
        "population": {
            "expected_rows": len(cases) * ATTEMPTS,
            "actual_rows": len(rows),
            "cases": len(cases),
            "attempts_per_case": ATTEMPTS,
            "arms_per_row": len(ARMS),
            "planner_executions": len(cases) * ATTEMPTS * len(ARMS),
            "complete": complete,
            "reasons": reasons,
        },
        "activation": {
            "case_ids": sorted(activation_cases),
            "reasons": activation_reasons,
        },
        "arm_metrics": {arm: _arm_metrics(rows, arm) for arm in ARMS},
        "viability": viability,
        "paired": {
            f"P_to_{arm}": {
                "full_contract": _full_contract_table(rows, "P", arm),
                "fields": {field: _field_transition(rows, "P", arm, field) for field in FIELD_KEYS},
            }
            for arm in ("RCV", "RCS")
        },
        "repeatability": {arm: _repeatability(rows, arm) for arm in ARMS},
        "efficiency": {"RCV_vs_RCS": efficiency},
        "controls": dict(FIXED_EXECUTION_CONTROLS),
        "provider_calls": sum(
            int(_arm_result(row, arm).get("provider_calls", 0)) for row in rows for arm in ARMS
        ),
        "worker_program_calls": sum(
            int(_arm_result(row, arm).get("program_calls", 0)) for row in rows for arm in ARMS
        ),
    }


def verify_reviewed_checkout(checkpoint: str) -> None:
    """Require live execution to use the reviewed P7 checkout and bytes."""
    if CHECKPOINT_RE.fullmatch(checkpoint) is None or current_checkout_sha() != checkpoint:
        raise RuntimeError("CM-57P7 checkout does not match the authorized checkpoint.")
    guarded = (
        "scripts/cm57p7_fresh_promotion.py",
        "tests/fixtures/typed_worker/cm57p7_fresh_promotion.json",
        "scripts/cm57p5_fresh_holdout.py",
        "scripts/cm57p6_report_invariant_bisect.py",
        "docs/evaluations/agent-code-mode/CM-57P5-live-summary.json",
        "docs/evaluations/agent-code-mode/CM-57P6-live-summary.json",
        "src/wellplot/agent/code_mode/planner.py",
        "src/wellplot/agent/providers/base.py",
        "src/wellplot/capabilities/base.py",
        "src/wellplot/capabilities/registry.py",
        "src/wellplot/capabilities/builtins.py",
    )
    for relative_path in guarded:
        if (REPO_ROOT / relative_path).read_bytes() != _git_output(
            "show", f"{checkpoint}:{relative_path}"
        ):
            raise RuntimeError(f"CM-57P7 guarded artifact drifted: {relative_path}")


def verify_frozen_contract() -> dict[str, object]:
    """Verify P5/P6 anchors and P7's provider-free corpus controls."""
    cases = load_case_definitions()
    if artifact_sha256(CASE_PATH) != EXPECTED_CORPUS_SHA256:
        raise RuntimeError("CM-57P7 corpus bytes drifted.")
    checks = (
        (P5_SCRIPT_PATH, EXPECTED_P5_SCRIPT_SHA256),
        (P5_SUMMARY_PATH, EXPECTED_P5_SUMMARY_SHA256),
        (P6_SCRIPT_PATH, EXPECTED_P6_SCRIPT_SHA256),
        (P6_SUMMARY_PATH, EXPECTED_P6_SUMMARY_SHA256),
        (P6_MANIFEST_PATH, EXPECTED_P6_MANIFEST_SHA256),
        (REPO_ROOT / "src/wellplot/agent/code_mode/planner.py", EXPECTED_PLANNER_SOURCE_SHA256),
        (REPO_ROOT / "src/wellplot/agent/providers/base.py", EXPECTED_PROVIDER_BASE_SHA256),
    )
    for path, expected in checks:
        if artifact_sha256(path) != expected:
            raise RuntimeError(f"CM-57P7 frozen artifact drifted: {path.name}")
    if p5._catalog_sha256() != EXPECTED_CATALOG_SHA256:
        raise RuntimeError("CM-57P7 planning catalogue drifted.")
    if sha256_text(_PLANNER_SYSTEM_PROMPT) != EXPECTED_BASE_PROMPT_SHA256:
        raise RuntimeError("CM-57P7 production prompt drifted.")
    if sha256_text(p5.RC_PROMPT) != EXPECTED_RC_PROMPT_SHA256:
        raise RuntimeError("CM-57P7 RC prompt drifted.")
    if _fixed_source_summary_sha() != EXPECTED_SOURCE_SUMMARY_SHA256:
        raise RuntimeError("CM-57P7 source summary drifted.")
    if p6.schema_sha256(SemanticPlan) != EXPECTED_PRODUCTION_SCHEMA_SHA256:
        raise RuntimeError("CM-57P7 production response schema drifted.")
    if p6.schema_sha256(p6.NonEmptyReportSemanticPlan) != EXPECTED_NONEMPTY_SCHEMA_SHA256:
        raise RuntimeError("CM-57P7 candidate response schema drifted.")
    return {
        "cases": len(cases),
        "corpus_sha256": EXPECTED_CORPUS_SHA256,
        "p5_script_sha256": EXPECTED_P5_SCRIPT_SHA256,
        "p6_script_sha256": EXPECTED_P6_SCRIPT_SHA256,
        "p6_summary_sha256": EXPECTED_P6_SUMMARY_SHA256,
        "provider_base_sha256": EXPECTED_PROVIDER_BASE_SHA256,
        "production_schema_sha256": EXPECTED_PRODUCTION_SCHEMA_SHA256,
        "nonempty_schema_sha256": EXPECTED_NONEMPTY_SCHEMA_SHA256,
    }


async def _self_test_arms(case: dict[str, object]) -> None:
    """Exercise all arm wrappers without constructing a provider."""
    registry = create_builtin_registry()
    for arm in ARMS:
        backend = p5._DeterministicBackend(invalid_first=True)
        result = await run_arm(case, arm=arm, delegate=backend, registry=registry)  # type: ignore[arg-type]
        assert result["final_planner_success"]
        assert result["program_calls"] == 0
        assert result["response_schema_sha256"] == _schema_sha256(arm)
        assert len(backend.calls) == 2
    production = p5._DeterministicBackend(invalid_first=True)
    candidate = p5._DeterministicBackend(invalid_first=True)
    await run_arm(case, arm="P", delegate=production, registry=registry)  # type: ignore[arg-type]
    await run_arm(case, arm="RC", delegate=candidate, registry=registry)  # type: ignore[arg-type]
    for left, right in zip(production.calls, candidate.calls, strict=True):
        assert left.user_prompt == right.user_prompt
        assert left.system_prompt == _PLANNER_SYSTEM_PROMPT
        assert right.system_prompt == p5.RC_PROMPT


def _prelive_self_tests(cases: tuple[dict[str, object], ...]) -> None:
    """Run deterministic evaluator and arm-isolation checks."""
    assert len(cases) == 24
    registry = create_builtin_registry()
    for case in cases:
        for section in case["expected_sections"]:
            p5._validate_section_gold(section, registry, case["case_id"])
    asyncio.run(_self_test_arms(cases[4]))


def prelive_report() -> dict[str, object]:
    """Run provider-free P7 guards and describe the future matrix."""
    contract = verify_frozen_contract()
    cases = load_case_definitions()
    _prelive_self_tests(cases)
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
        "future_controls": {**FIXED_EXECUTION_CONTROLS, "attempts": ATTEMPTS},
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
        "P_production_path": "PASS",
        "RC_prompt_path": "PASS",
        "RCV_validator_only_path": "PASS",
        "RCS_schema_only_path": "PASS",
        "live_evidence": "NOT_STARTED",
    }


async def _run_live(args: argparse.Namespace, checkpoint: str) -> None:
    """Run the complete authorized matrix once and flush each row."""
    if OUTPUT_PATH.exists() and OUTPUT_PATH.stat().st_size:
        raise RuntimeError(f"Refusing to append to non-empty evidence path {OUTPUT_PATH}.")
    verify_reviewed_checkout(checkpoint)
    verify_frozen_contract()
    cases = load_case_definitions()
    registry = create_builtin_registry()
    backend = p5._provider_configuration(args)
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
    """Build provider-free and explicitly gated live CLI modes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-authorized", action="store_true")
    parser.add_argument("--authorized-checkpoint")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="LLAMA_CPP_API_KEY")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run provider-free validation unless explicit live flags are supplied."""
    args = _parser().parse_args(argv)
    if not args.live_authorized:
        print(json.dumps(prelive_report(), indent=2, sort_keys=True))
        return 0
    if not args.authorized_checkpoint or not args.base_url:
        raise SystemExit("Live CM-57P7 requires --authorized-checkpoint and --base-url.")
    asyncio.run(_run_live(args, args.authorized_checkpoint))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
