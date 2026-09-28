"""CM-57P9A endpoint-session inference reproducibility characterization.

The default command is provider-free. Live execution and finalization are
separate, explicitly gated operations so a partial population can never be
silently resumed.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import cm57p5_fresh_holdout as p5  # noqa: E402
from scripts import cm57p7_fresh_promotion as p7  # noqa: E402
from scripts import cm57p8_prompt_factor_localization as p8  # noqa: E402
from scripts import cm57p9_runtime_fingerprint as fingerprint  # noqa: E402
from wellplot.agent.code_mode.planner import (  # noqa: E402
    _PLANNER_SYSTEM_PROMPT,
    PlannerSemanticFailure,
    SemanticPlan,
    SemanticPlanner,
)
from wellplot.agent.providers.base import (  # noqa: E402
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry  # noqa: E402

MANIFEST_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm57p9a_repro_cases.json"
P7_CASE_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm57p7_fresh_promotion.json"
P7_SCRIPT_PATH = REPO_ROOT / "scripts/cm57p7_fresh_promotion.py"
P7_SUMMARY_PATH = REPO_ROOT / "docs/evaluations/agent-code-mode/CM-57P7-live-summary.json"
P8_SCRIPT_PATH = REPO_ROOT / "scripts/cm57p8_prompt_factor_localization.py"
P8_SUMMARY_PATH = REPO_ROOT / "docs/evaluations/agent-code-mode/CM-57P8-live-summary.json"
OUTPUT_PATH = Path("/tmp/cm57p9a-endpoint-session-qwen.jsonl")

BASELINE_SHA = "e8f19141e6dd349d44ddd9cb97305a856216a6fa"
EXPERIMENT_VERSION = "CM-57P9A"
MANIFEST_VERSION = "cm57p9a.same-process-repro.v1"
FROZEN_MODEL = "qwen3.6-35b-a3b"
PLANNER_TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 16384
MAX_TOKENS_PARAMETER = "max_tokens"
TIMEOUT_SECONDS = 900.0
ATTEMPTS = 8
ARMS: tuple[str, ...] = ("P", "RC")
Arm = Literal["P", "RC"]
CASE_IDS: tuple[str, ...] = (
    "p7-dossier-gamma-17",
    "p7-separated-curves-13",
    "p7-temperature-image-pair-12",
    "p7-reference-density-image-10",
    "p7-depth-conductivity-06",
    "p7-lone-porosity-05",
)

EXPECTED_P7_CORPUS_SHA256 = "4aebee0d2734cb272c6ae002aec277e58427dd5dce44e38e5fdf1a14a4dccd12"
EXPECTED_P7_RAW_SHA256 = "b4cb75aaf6a5ffe8c7f88c6e730d32247d973ea974269132a76b814633ff4d2f"
EXPECTED_P7_SUMMARY_SHA256 = "c10e909384a6a1d75f11d74979a3804a6f13b8505e56de5a638af3a29032300c"
EXPECTED_P7_SCRIPT_SHA256 = "52809176e6fbe75cf30cf419af15943e7c98e0ccfbf7646a85bdd445b0d6f0a8"
EXPECTED_P8_RAW_SHA256 = "0c9bb86c11a229ea387c2e597a374af80cfa9af4204f1da2054865cff6f8b451"
EXPECTED_P8_SUMMARY_SHA256 = "0df78b4e299bb6add03488f1dd7c9084a268abf0c8b991c8800ea0d42d065abe"
EXPECTED_P8_SCRIPT_SHA256 = "40c58f643f4c4c70bbaf474a98019a12f8a370be8574fb13a0a26c0efce3a777"
EXPECTED_PLANNER_SOURCE_SHA256 = "0189b290ef4f76bdd776fe2612c454809ff77725379def7d8c5a98d9ae165413"
EXPECTED_PROVIDER_BASE_SHA256 = "4c14afc1e6e53faef1ef99266059b7b88b6c4dec4bfb5a4768ca5b36efc3f049"
EXPECTED_OPENAI_COMPAT_SHA256 = "1409f83cdc6e8ed376f3d1d59102acde06b3e272ce15035adec6cd830723c653"
EXPECTED_CAPABILITY_CATALOG_SHA256 = (
    "2290d9656bf69cea130e97c39da4c572449a0bbb3bcd6aff61463f25b2702cac"
)
EXPECTED_BASE_PROMPT_SHA256 = "5e7a0732af01e4b1f16b3ccf019c005ea2e9ba5c0e93e94870a56a261e2bca18"
EXPECTED_RC_PROMPT_SHA256 = "e1710cb516a96c47ec1d0593752e83aacc1bb4502c3026b2b6a9a676c90e4d34"
EXPECTED_SCHEMA_SHA256 = "3a331166ccc570a74056dea7770d04b16f8fa32dc3641d6c37de6c26cf81d9e3"
EXPECTED_SOURCE_SUMMARY_SHA256 = "ec6147a1b5e1ac6374e34ae3d66d11275542c6b340337cb26d3ae1d06240532e"
EXPECTED_MANIFEST_SHA256 = "0d2a4b2d7e6db23034779e18e885b9cf663905dbd8885c54dd473374c69d231e"
CHECKPOINT_RE = __import__("re").compile(r"^[0-9a-f]{40}$")

FIXED_SOURCE_SUMMARY = p5.FIXED_SOURCE_SUMMARY
FIXED_EXECUTION_CONTROLS = {
    "model": FROZEN_MODEL,
    "planner_temperature": PLANNER_TEMPERATURE,
    "max_output_tokens": MAX_OUTPUT_TOKENS,
    "max_tokens_parameter": MAX_TOKENS_PARAMETER,
    "timeout_seconds": TIMEOUT_SECONDS,
}


def canonical_json(value: object) -> str:
    """Serialize JSON-shaped values deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(value: bytes) -> str:
    """Hash exact bytes."""
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    """Hash exact UTF-8 text."""
    return sha256_bytes(value.encode("utf-8"))


def artifact_sha256(path: Path) -> str:
    """Hash one repository artifact."""
    return sha256_bytes(path.read_bytes())


def _git_output(*arguments: str) -> bytes:
    """Return exact output from a repository-local Git command."""
    return subprocess.check_output(["git", *arguments], cwd=REPO_ROOT, stderr=subprocess.STDOUT)


def current_checkout_sha() -> str:
    """Return the current checkout SHA."""
    return _git_output("rev-parse", "HEAD").decode().strip()


def composed_prompt(arm: Arm) -> str:
    """Return the exact production or frozen RC prompt."""
    return _PLANNER_SYSTEM_PROMPT if arm == "P" else p8.p4.composed_prompt("RC")


PROMPT_SHA256 = {arm: sha256_text(composed_prompt(arm)) for arm in ARMS}


def _gold_sha(case: dict[str, object]) -> str:
    """Hash frozen P7 gold fields without copying them into the manifest."""
    return p8._gold_sha(case)


def _schema_sha256() -> str:
    """Return the production SemanticPlan schema hash."""
    return p8._schema_sha256()


def load_manifest() -> tuple[dict[str, object], ...]:
    """Resolve six hash-only manifest entries against frozen P7 requests."""
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if payload.get("version") != MANIFEST_VERSION:
        raise ValueError("Unexpected CM-57P9A manifest version.")
    if payload.get("p7_corpus_sha256") != EXPECTED_P7_CORPUS_SHA256:
        raise ValueError("CM-57P9A P7 corpus hash drifted.")
    if payload.get("p7_raw_sha256") != EXPECTED_P7_RAW_SHA256:
        raise ValueError("CM-57P9A P7 raw hash drifted.")
    if payload.get("p8_raw_sha256") != EXPECTED_P8_RAW_SHA256:
        raise ValueError("CM-57P9A P8 raw hash drifted.")
    entries = payload.get("cases")
    if not isinstance(entries, list) or len(entries) != len(CASE_IDS):
        raise ValueError("CM-57P9A requires exactly six cases.")
    if [entry.get("case_id") for entry in entries] != list(CASE_IDS):
        raise ValueError("CM-57P9A case order drifted.")
    p7_cases = {str(case["case_id"]): case for case in p7.load_case_definitions(P7_CASE_PATH)}
    resolved: list[dict[str, object]] = []
    for entry in entries:
        case_id = str(entry["case_id"])
        case = p7_cases.get(case_id)
        if case is None or "request" in entry:
            raise ValueError(f"Invalid CM-57P9A manifest case: {case_id!r}.")
        if entry.get("request_sha256") != sha256_text(str(case["request"])):
            raise ValueError(f"Request hash drift for {case_id!r}.")
        if entry.get("gold_sha256") != _gold_sha(case):
            raise ValueError(f"Gold hash drift for {case_id!r}.")
        for anchor_name in ("p7_historical", "p8_historical"):
            anchors = entry.get(anchor_name)
            if not isinstance(anchors, dict) or set(anchors) != {"0", "1"}:
                raise ValueError(f"Missing {anchor_name} for {case_id!r}.")
            for attempt in ("0", "1"):
                if not isinstance(anchors[attempt], dict) or set(anchors[attempt]) != set(ARMS):
                    raise ValueError(f"Invalid {anchor_name} for {case_id!r}.")
        resolved.append(
            {
                **case,
                "role": entry["role"],
                "p7_historical": entry["p7_historical"],
                "p8_historical": entry["p8_historical"],
            }
        )
    return tuple(resolved)


def _frozen_provenance() -> dict[str, object]:
    """Return immutable provenance for each future evidence row."""
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "design_baseline_sha": BASELINE_SHA,
        "manifest_sha256": artifact_sha256(MANIFEST_PATH),
        "p7_corpus_sha256": EXPECTED_P7_CORPUS_SHA256,
        "p7_raw_sha256": EXPECTED_P7_RAW_SHA256,
        "p8_raw_sha256": EXPECTED_P8_RAW_SHA256,
        "P_prompt_sha256": PROMPT_SHA256["P"],
        "RC_prompt_sha256": PROMPT_SHA256["RC"],
        "response_schema_sha256": _schema_sha256(),
        "source_summary_sha256": sha256_text(canonical_json(FIXED_SOURCE_SUMMARY)),
        "execution_controls": dict(FIXED_EXECUTION_CONTROLS),
    }


def _field(value: object, name: str) -> object:
    """Read one SDK field from an object or mapping."""
    return value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)


def _usage(value: object, name: str) -> int | None:
    """Read one non-negative usage counter."""
    item = _field(value, name)
    return item if isinstance(item, int) and not isinstance(item, bool) and item >= 0 else None


@dataclass
class ResponseObserver:
    """Capture safe response metadata while returning provider responses unchanged."""

    events: list[dict[str, object]]

    def _response_event(self, response: object, latency_ms: float) -> dict[str, object]:
        choices = _field(response, "choices")
        choice = choices[0] if isinstance(choices, (list, tuple)) and choices else None
        message = _field(choice, "message")
        content = _field(message, "content")
        usage = _field(response, "usage")
        return {
            "response_observed": True,
            "raw_assistant_content_sha256": sha256_text(content)
            if isinstance(content, str)
            else None,
            "finish_reason": _field(choice, "finish_reason"),
            "prompt_tokens": _usage(usage, "prompt_tokens"),
            "completion_tokens": _usage(usage, "completion_tokens"),
            "total_tokens": _usage(usage, "total_tokens"),
            "latency_ms": latency_ms,
        }

    def record_transport_failure(self, latency_ms: float) -> None:
        """Record a failed transport without retaining exception text."""
        self.events.append(
            {
                "response_observed": False,
                "raw_assistant_content_sha256": None,
                "finish_reason": None,
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "latency_ms": latency_ms,
            }
        )


class _ObservedCompletions:
    def __init__(self, delegate: object, observer: ResponseObserver) -> None:
        self._delegate = delegate
        self._observer = observer

    async def create(self, **arguments: object) -> object:
        """Forward exact arguments and observe only safe response metadata."""
        import time

        started = time.perf_counter()
        try:
            response = await self._delegate.create(**arguments)
        except Exception:
            self._observer.record_transport_failure((time.perf_counter() - started) * 1000)
            raise
        self._observer.events.append(
            self._observer._response_event(response, (time.perf_counter() - started) * 1000)
        )
        return response


class _ObservedChat:
    def __init__(self, delegate: object, observer: ResponseObserver) -> None:
        completions = delegate.completions
        self.completions = _ObservedCompletions(completions, observer)


class ObservedClient:
    """Minimal AsyncOpenAI proxy preserving the production client interface."""

    def __init__(self, delegate: object, observer: ResponseObserver) -> None:
        """Wrap the production client without changing its request surface."""
        self.chat = _ObservedChat(delegate.chat, observer)


@dataclass
class PromptBackend(ModelBackendProtocol):
    """Substitute only the frozen P or RC system prompt."""

    delegate: ModelBackendProtocol
    arm: Arm

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Forward all request fields unchanged except the system prompt."""
        if request.system_prompt != _PLANNER_SYSTEM_PROMPT:
            raise RuntimeError("CM-57P9A received an unexpected planner prompt.")
        return await self.delegate.generate_structured(
            replace(request, system_prompt=composed_prompt(self.arm)),
            response_model=response_model,
        )

    async def generate_program(self, request: object) -> object:
        """Reject accidental worker execution."""
        raise AssertionError("CM-57P9A must not invoke program generation.")


@dataclass
class RecordingBackend(ModelBackendProtocol):
    """Record bounded provider-call and plan metadata around production calls."""

    delegate: ModelBackendProtocol
    observer: ResponseObserver
    calls: list[dict[str, object]]
    plans: list[SemanticPlan]
    program_calls: int = 0

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Record one call without retaining provider payloads."""
        call_kind = (
            "INITIAL"
            if not self.calls
            else (
                "SEMANTIC_CORRECTION"
                if "Correction context:" in request.user_prompt
                else "INVALID_RESPONSE_RETRY"
            )
        )
        event_index = len(self.observer.events)
        record: dict[str, object] = {"call_kind": call_kind}
        try:
            result = await self.delegate.generate_structured(request, response_model=response_model)
        except ProviderRequestError as error:
            record.update(
                {"outcome": "provider_failure", "provider_category": error.category.value}
            )
            if len(self.observer.events) > event_index:
                record.update(self.observer.events[event_index])
            self.calls.append(record)
            raise
        except ValidationError:
            record["outcome"] = "structured_output_failure"
            if len(self.observer.events) > event_index:
                record.update(self.observer.events[event_index])
            self.calls.append(record)
            raise
        record["outcome"] = "structured_success"
        record["metrics"] = result.metrics.public_metadata()
        if len(self.observer.events) > event_index:
            record.update(self.observer.events[event_index])
        if isinstance(result.value, SemanticPlan):
            self.plans.append(result.value)
            record["plan"] = p7.p5._plan_projection(result.value)
        self.calls.append(record)
        return result

    async def generate_program(self, request: object) -> object:
        """Fail closed if planner execution reaches a worker."""
        self.program_calls += 1
        raise AssertionError("CM-57P9A must stop before worker execution.")


def _provider_classification(error: ProviderRequestError) -> str:
    """Classify only invalid structured output as a planner schema outcome."""
    if error.category in {
        ProviderFailureCategory.INVALID_RESPONSE,
        ProviderFailureCategory.VALIDATION,
    }:
        return "PLANNER_SCHEMA_FAILURE"
    return "PROVIDER_INFRA_FAILURE"


def _plan_facts(
    plan: SemanticPlan | None,
    case: dict[str, object],
    registry: CapabilityRegistry,
) -> dict[str, object] | None:
    """Use the established bounded planner fact projection."""
    return p8._plan_facts(plan, case, registry) if plan is not None else None


def _planner_facts_hash(
    facts: dict[str, object] | None,
    final_classification: str | None,
    *,
    final_plan_available: bool,
) -> str:
    """Hash structural planner facts, including stable terminal outcomes."""
    fact_keys = (
        "report_task_present",
        "report_capability_ids",
        "section_capability_signatures",
        "section_task_count",
        "unresolved_requirements_count",
        "parent_closure_valid",
        "duplicate_capability_type",
    )
    selected = {key: facts.get(key) if isinstance(facts, dict) else None for key in fact_keys}
    selected["final_plan_available"] = final_plan_available
    selected["final_classification"] = final_classification
    return sha256_text(canonical_json(selected))


def _call_path_hash(calls: list[dict[str, object]]) -> str:
    """Hash the complete ordered call trace, including response hashes."""
    path = [
        {
            key: call.get(key)
            for key in (
                "call_kind",
                "outcome",
                "provider_category",
                "raw_assistant_content_sha256",
            )
        }
        for call in calls
    ]
    return sha256_text(canonical_json(path))


def _call_path_structure_hash(calls: list[dict[str, object]]) -> str:
    """Hash call structure without treating provider text as path variation."""
    path = [
        {key: call.get(key) for key in ("call_kind", "outcome", "provider_category")}
        for call in calls
    ]
    return sha256_text(canonical_json(path))


def _initial_structured_success(calls: list[dict[str, object]]) -> bool:
    """Report whether the INITIAL planner call returned a structured plan."""
    initial = next(
        (call for call in calls if call.get("call_kind") == "INITIAL"),
        None,
    )
    return bool(initial and initial.get("outcome") == "structured_success")


async def run_arm(
    case: dict[str, object],
    *,
    arm: Arm,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
    observer: ResponseObserver,
) -> dict[str, object]:
    """Run one production planner execution for one P/RC arm."""
    calls: list[dict[str, object]] = []
    plans: list[SemanticPlan] = []
    recorder = RecordingBackend(
        delegate=PromptBackend(delegate=delegate, arm=arm),
        observer=observer,
        calls=calls,
        plans=plans,
    )
    planner = SemanticPlanner(backend=recorder, registry=registry)
    final_plan: SemanticPlan | None = None
    error_type: str | None = None
    error_code: str | None = None
    final_classification: str | None = None
    infra = False
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
        final_classification = _provider_classification(error)
        infra = final_classification == "PROVIDER_INFRA_FAILURE"
    except PlannerSemanticFailure as error:
        error_type = "PlannerSemanticFailure"
        error_code = error.code
        final_classification = "PLANNER_SEMANTIC_FAILURE"
    except ValidationError:
        error_type = "ValidationError"
        final_classification = "PLANNER_SCHEMA_FAILURE"
    if final_plan is not None:
        facts = _plan_facts(final_plan, case, registry)
        final_classification = p5.classify_facts(facts or {})
    else:
        facts = None
    if final_classification is None:
        raise AssertionError("CM-57P9A arm ended without a terminal classification.")
    initial_structured_success = _initial_structured_success(calls)
    return {
        "arm": arm,
        "prompt_sha256": PROMPT_SHA256[arm],
        "response_schema_sha256": _schema_sha256(),
        "planner_call_count": len(calls),
        "program_call_count": recorder.program_calls,
        "call_trace": calls,
        "initial_structured_success": initial_structured_success,
        "initial_plan_available": initial_structured_success,
        "final_plan_available": final_plan is not None,
        "final_planner_success": final_plan is not None,
        "final_classification": final_classification,
        "final_error_type": error_type,
        "final_error_code": error_code,
        "provider_infrastructure_failure": infra,
        "invalid_response_retry_used": any(
            call.get("call_kind") == "INVALID_RESPONSE_RETRY" for call in calls
        ),
        "semantic_correction_used": any(
            call.get("call_kind") == "SEMANTIC_CORRECTION" for call in calls
        ),
        "semantic_plan_sha256": (
            sha256_text(canonical_json(final_plan.model_dump(mode="json")))
            if final_plan is not None
            else None
        ),
        "planner_facts_sha256": _planner_facts_hash(
            facts,
            final_classification,
            final_plan_available=final_plan is not None,
        ),
        "call_path_sha256": _call_path_hash(calls),
        "call_path_structure_sha256": _call_path_structure_hash(calls),
        "plan_projection": p7.p5._plan_projection(final_plan) if final_plan is not None else None,
        "reference": p8._reference_projection(facts, case),
        "final_facts": facts,
    }


async def run_row(
    case: dict[str, object],
    *,
    repetition_index: int,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
    observer: ResponseObserver,
    runtime_fingerprint_sha256: str,
    authorized_checkpoint: str,
) -> dict[str, object]:
    """Run P then RC sequentially for one case/repetition."""
    arms = {}
    for arm in ARMS:
        arms[arm] = await run_arm(
            case,
            arm=arm,
            delegate=delegate,
            registry=registry,
            observer=observer,
        )
    return {
        **_frozen_provenance(),
        "authorized_checkpoint": authorized_checkpoint,
        "runtime_fingerprint_sha256": runtime_fingerprint_sha256,
        "case_id": case["case_id"],
        "role": case["role"],
        "repetition_index": repetition_index,
        "request_sha256": sha256_text(str(case["request"])),
        "gold_sha256": _gold_sha(case),
        "arms": arms,
    }


def _arm(row: dict[str, object], arm: str) -> dict[str, object]:
    """Return one bounded arm result."""
    arms = row.get("arms")
    value = arms.get(arm) if isinstance(arms, dict) else None
    return value if isinstance(value, dict) else {}


def population_integrity(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    runtime_fingerprint_sha256: str | None = None,
    expected_checkpoint: str | None = None,
) -> tuple[bool, list[str]]:
    """Fail closed on population, provenance, and worker-call drift."""
    reasons: list[str] = []
    expected_pairs = len(cases) * ATTEMPTS
    if len(rows) != expected_pairs:
        reasons.append("wrong_row_count")
    expected_ids = {str(case["case_id"]) for case in cases}
    pairs = [(str(row.get("case_id")), row.get("repetition_index")) for row in rows]
    if len(set(pairs)) != len(pairs):
        reasons.append("duplicate_case_repetition")
    if {case_id for case_id, _ in pairs} != expected_ids:
        reasons.append("case_set_mismatch")
    by_case: dict[str, set[object]] = {}
    for case_id, repetition in pairs:
        by_case.setdefault(case_id, set()).add(repetition)
    if any(values != set(range(ATTEMPTS)) for values in by_case.values()):
        reasons.append("repetition_index_mismatch")
    if any(not isinstance(row.get("arms"), dict) or set(row["arms"]) != set(ARMS) for row in rows):
        reasons.append("arm_set_mismatch")
    case_map = {str(case["case_id"]): case for case in cases}
    expected_provenance = _frozen_provenance()
    for row in rows:
        case = case_map.get(str(row.get("case_id")))
        if case is None:
            continue
        for key, expected in expected_provenance.items():
            if row.get(key) != expected:
                reasons.append(f"{key}_mismatch")
        if (
            runtime_fingerprint_sha256 is not None
            and row.get("runtime_fingerprint_sha256") != runtime_fingerprint_sha256
        ):
            reasons.append("runtime_fingerprint_mismatch")
        if (
            expected_checkpoint is not None
            and row.get("authorized_checkpoint") != expected_checkpoint
        ):
            reasons.append("authorized_checkpoint_mismatch")
        if row.get("request_sha256") != sha256_text(str(case["request"])):
            reasons.append("request_hash_mismatch")
        if row.get("gold_sha256") != _gold_sha(case):
            reasons.append("gold_hash_mismatch")
        for arm in ARMS:
            result = _arm(row, arm)
            if result.get("prompt_sha256") != PROMPT_SHA256[arm]:
                reasons.append(f"{arm}_prompt_mismatch")
            if result.get("response_schema_sha256") != EXPECTED_SCHEMA_SHA256:
                reasons.append(f"{arm}_schema_mismatch")
            if int(result.get("program_call_count", 0)) != 0:
                reasons.append("worker_program_call")
            if result.get("provider_infrastructure_failure"):
                reasons.append("provider_infrastructure_failure")
    return not reasons, sorted(set(reasons))


def _repetition_outcome(result: dict[str, object]) -> tuple[object, ...]:
    """Return the outcome fields frozen for stability comparison."""
    return (
        result.get("final_plan_available"),
        result.get("final_classification"),
        result.get("planner_call_count"),
        result.get("invalid_response_retry_used"),
        result.get("semantic_correction_used"),
    )


def _provider_signature(result: dict[str, object]) -> tuple[object, ...]:
    """Return raw response hashes and path identity for one repetition."""
    return (
        tuple(call.get("raw_assistant_content_sha256") for call in result.get("call_trace", [])),
        result.get("call_path_sha256"),
    )


def _stats(values: list[object]) -> dict[str, object]:
    """Summarize numeric provider metadata without inventing unavailable values."""
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    if not numeric:
        return {"min": None, "max": None, "mean": None, "median": None, "unique_values": []}
    unique = sorted(set(numeric))
    return {
        "min": min(numeric),
        "max": max(numeric),
        "mean": statistics.mean(numeric),
        "median": statistics.median(numeric),
        "unique_values": unique,
    }


def _historical_matches(result: dict[str, object], historical: dict[str, object]) -> bool:
    """Compare one bounded result against one historical anchor."""
    facts = result.get("final_facts")
    bounded = {
        "final_planner_success": result.get("final_planner_success"),
        "final_classification": result.get("final_classification"),
        "report_task_present": facts.get("report_task_present")
        if isinstance(facts, dict)
        else None,
        "report_capability_ids": facts.get("report_capability_ids")
        if isinstance(facts, dict)
        else None,
        "section_capability_signatures": facts.get("section_capability_signatures")
        if isinstance(facts, dict)
        else None,
        "final_contract_ok": p5.final_contract_ok(facts) if isinstance(facts, dict) else False,
        "provider_failure_category": result.get("final_error_code"),
        "provider_calls": result.get("planner_call_count"),
        "call_kinds": [call.get("call_kind") for call in result.get("call_trace", [])],
    }
    return bounded == historical


def _classify_group(
    rows: list[dict[str, object]], case: dict[str, object], arm: Arm
) -> dict[str, object]:
    """Classify one case/arm across eight sequential repetitions."""
    results = [_arm(row, arm) for row in sorted(rows, key=lambda row: row["repetition_index"])]
    provider_signatures = [_provider_signature(result) for result in results]
    plan_hashes = [result.get("semantic_plan_sha256") for result in results]
    facts_hashes = [result.get("planner_facts_sha256") for result in results]
    outcomes = [_repetition_outcome(result) for result in results]
    call_paths = [result.get("call_path_structure_sha256") for result in results]
    provider_exact = len(set(provider_signatures)) == 1
    plan_stable = len(set(plan_hashes)) == 1
    facts_stable = len(set(facts_hashes)) == 1 and facts_hashes[0] is not None
    outcome_stable = len(set(outcomes)) == 1
    call_path_stable = len(set(call_paths)) == 1
    if not facts_stable or not outcome_stable or not call_path_stable:
        classification = "NOT_REPRODUCIBLE"
    elif plan_stable and provider_exact:
        classification = "EXACT_REPRODUCIBLE"
    elif plan_stable:
        classification = "PLAN_REPRODUCIBLE_WITH_TEXT_VARIATION"
    else:
        classification = "CONTRACT_REPRODUCIBLE_WITH_SEMANTIC_TEXT_VARIATION"
    p7_flags = [
        any(_historical_matches(result, case["p7_historical"][str(index)][arm]) for index in (0, 1))
        for result in results
    ]
    p8_flags = [
        any(_historical_matches(result, case["p8_historical"][str(index)][arm]) for index in (0, 1))
        for result in results
    ]
    p7_matches = sum(p7_flags)
    p8_matches = sum(p8_flags)
    calls = [call for result in results for call in result.get("call_trace", [])]
    token_stats = {
        field: _stats([call.get(field) for call in calls])
        for field in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    latency_stats = _stats([call.get("latency_ms") for call in calls])
    return {
        "case_id": case["case_id"],
        "arm": arm,
        "classification": classification,
        "levels": {
            "provider": "EXACT_PROVIDER_STABLE" if provider_exact else "PROVIDER_TEXT_VARIANT",
            "semantic_plan": (
                "SEMANTIC_PLAN_STABLE"
                if plan_stable and plan_hashes[0] is not None
                else "SEMANTIC_PLAN_ABSENT_STABLE"
                if plan_stable
                else "SEMANTIC_PLAN_VARIANT"
            ),
            "contract_facts": "CONTRACT_FACTS_STABLE" if facts_stable else "CONTRACT_FACTS_VARIANT",
            "outcome": "OUTCOME_STABLE" if outcome_stable else "OUTCOME_VARIANT",
        },
        "repeat_count": len(results),
        "p7_match_count": p7_matches,
        "p8_match_count": p8_matches,
        "historical_state_counts": {
            "P7_match": p7_matches,
            "P8_match": p8_matches,
            "other": sum(not p7 and not p8 for p7, p8 in zip(p7_flags, p8_flags, strict=True)),
        },
        "token_usage": token_stats,
        "latency_ms": latency_stats,
        "prompt_token_accounting_variant": len(
            {
                call.get("prompt_tokens")
                for result in results
                for call in result.get("call_trace", [])
                if call.get("call_kind") == "INITIAL"
            }
        )
        > 1,
    }


def _special_diagnostics(rows: list[dict[str, object]]) -> dict[str, object]:
    """Summarize the three P9A diagnostic targets."""

    def facts_for(row: dict[str, object], arm: Arm) -> dict[str, object]:
        facts = _arm(row, arm).get("final_facts")
        return facts if isinstance(facts, dict) else {}

    output: dict[str, object] = {}
    reference_case = "p7-dossier-gamma-17"
    output[reference_case] = {
        arm: {
            "present": sum(
                bool(facts_for(row, arm).get("section_capability_signatures"))
                and any(
                    "track.reference" in section
                    for section in facts_for(row, arm).get("section_capability_signatures", [])
                )
                for row in rows
                if row["case_id"] == reference_case
            ),
            "absent": sum(
                _arm(row, arm).get("final_plan_available") is True
                and not any(
                    "track.reference" in section
                    for section in facts_for(row, arm).get("section_capability_signatures", [])
                )
                for row in rows
                if row["case_id"] == reference_case
            ),
        }
        for arm in ARMS
    }
    for case_id in ("p7-separated-curves-13", "p7-temperature-image-pair-12"):
        output[case_id] = {
            arm: {
                "initial_structured_success": sum(
                    bool(_arm(row, arm).get("initial_structured_success"))
                    for row in rows
                    if row["case_id"] == case_id
                ),
                "invalid_response_retry": sum(
                    bool(_arm(row, arm).get("invalid_response_retry_used"))
                    for row in rows
                    if row["case_id"] == case_id
                ),
                "terminal_schema_failure": sum(
                    _arm(row, arm).get("final_classification") == "PLANNER_SCHEMA_FAILURE"
                    for row in rows
                    if row["case_id"] == case_id
                ),
                "final_plan_available": sum(
                    bool(_arm(row, arm).get("final_plan_available"))
                    for row in rows
                    if row["case_id"] == case_id
                ),
            }
            for arm in ARMS
        }
    control = "p7-reference-density-image-10"
    output[control] = {
        arm: {
            "required_reference_omissions": sum(
                _arm(row, arm).get("final_facts") is not None
                and _arm(row, arm).get("reference", {}).get("missing_required_reference") is True
                for row in rows
                if row["case_id"] == control
            )
        }
        for arm in ARMS
    }
    return output


def _decision(
    complete: bool,
    reasons: list[str],
    groups: list[dict[str, object]],
    *,
    fingerprint_mismatches: list[str] | None = None,
) -> str:
    """Apply endpoint-session reproducibility precedence."""
    if (
        not complete
        or fingerprint_mismatches
        or any(group["classification"] == "INCONCLUSIVE" for group in groups)
    ):
        return "INCONCLUSIVE_REPRODUCIBILITY_EVALUATION"
    classifications = {str(group["classification"]) for group in groups}
    if "NOT_REPRODUCIBLE" in classifications:
        return "ENDPOINT_SESSION_NOT_REPRODUCIBLE"
    if "CONTRACT_REPRODUCIBLE_WITH_SEMANTIC_TEXT_VARIATION" in classifications:
        return "ENDPOINT_SESSION_CONTRACT_REPRODUCIBLE"
    if "PLAN_REPRODUCIBLE_WITH_TEXT_VARIATION" in classifications:
        return "ENDPOINT_SESSION_PLAN_REPRODUCIBLE"
    return "ENDPOINT_SESSION_EXACT_REPRODUCIBLE"


def summarize_population(
    rows: list[dict[str, object]],
    cases: tuple[dict[str, object], ...],
    *,
    pre_fingerprint: dict[str, object] | None = None,
    post_fingerprint: dict[str, object] | None = None,
    authorized_checkpoint: str | None = None,
) -> dict[str, object]:
    """Build a provider-free reproducibility summary."""
    pre_valid, pre_reasons = fingerprint.validate_endpoint_fingerprint(pre_fingerprint)
    post_valid, post_reasons = fingerprint.validate_endpoint_fingerprint(post_fingerprint)
    fingerprint_mismatches = (
        fingerprint.compare_endpoint_fingerprints(pre_fingerprint, post_fingerprint)
        if pre_valid and post_valid
        else [*pre_reasons, *post_reasons]
    )
    pre_sha = sha256_text(canonical_json(pre_fingerprint)) if pre_fingerprint else None
    complete, reasons = population_integrity(
        rows,
        cases,
        runtime_fingerprint_sha256=pre_sha,
        expected_checkpoint=authorized_checkpoint,
    )
    groups = [
        _classify_group([row for row in rows if row.get("case_id") == case["case_id"]], case, arm)
        for case in cases
        for arm in ARMS
    ]
    decision = _decision(complete, reasons, groups, fingerprint_mismatches=fingerprint_mismatches)
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "decision": decision,
        "population": {
            "expected_rows": len(cases) * ATTEMPTS,
            "actual_rows": len(rows),
            "cases": len(cases),
            "repetitions_per_case_arm": ATTEMPTS,
            "planner_executions": len(cases) * ATTEMPTS * len(ARMS),
            "complete": complete,
            "reasons": reasons,
        },
        "groups": groups,
        "special_diagnostics": _special_diagnostics(rows),
        "runtime_fingerprint": {
            "scope": "ENDPOINT_MODEL",
            "pre_sha256": sha256_text(canonical_json(pre_fingerprint)) if pre_fingerprint else None,
            "post_sha256": sha256_text(canonical_json(post_fingerprint))
            if post_fingerprint
            else None,
            "mismatches": fingerprint_mismatches,
        },
        "provider_calls_total": sum(
            int(_arm(row, arm).get("planner_call_count", 0)) for row in rows for arm in ARMS
        ),
        "worker_program_calls": sum(
            int(_arm(row, arm).get("program_call_count", 0)) for row in rows for arm in ARMS
        ),
        "controls": dict(FIXED_EXECUTION_CONTROLS),
        "prompt_hashes": dict(PROMPT_SHA256),
        "response_schema_sha256": EXPECTED_SCHEMA_SHA256,
        "provenance_scope": "ENDPOINT_MODEL",
        "production_adoption": "NOT_AUTHORIZED",
        "CM57D": "BLOCKED",
    }


def verify_reviewed_checkout(checkpoint: str) -> None:
    """Require exact reviewed bytes before provider construction."""
    if CHECKPOINT_RE.fullmatch(checkpoint) is None or current_checkout_sha() != checkpoint:
        raise RuntimeError("CM-57P9A checkout does not match the authorized checkpoint.")
    guarded = (
        "scripts/cm57p9a_inference_reproducibility.py",
        "scripts/cm57p9_runtime_fingerprint.py",
        "tests/fixtures/typed_worker/cm57p9a_repro_cases.json",
        "scripts/cm57p8_prompt_factor_localization.py",
        "docs/evaluations/agent-code-mode/CM-57P8-live-summary.json",
        "scripts/cm57p7_fresh_promotion.py",
        "tests/fixtures/typed_worker/cm57p7_fresh_promotion.json",
        "src/wellplot/agent/code_mode/planner.py",
        "src/wellplot/agent/providers/base.py",
        "src/wellplot/agent/providers/openai_compat_v2.py",
        "src/wellplot/capabilities/builtins.py",
    )
    for relative_path in guarded:
        path = REPO_ROOT / relative_path
        if path.read_bytes() != _git_output("show", f"{checkpoint}:{relative_path}"):
            raise RuntimeError(f"CM-57P9A guarded artifact drifted: {relative_path}")


def verify_frozen_contract() -> dict[str, object]:
    """Verify all P7/P8 and production artifacts without provider construction."""
    cases = load_manifest()
    checks = {
        MANIFEST_PATH: EXPECTED_MANIFEST_SHA256,
        P7_CASE_PATH: EXPECTED_P7_CORPUS_SHA256,
        P7_SCRIPT_PATH: EXPECTED_P7_SCRIPT_SHA256,
        P7_SUMMARY_PATH: EXPECTED_P7_SUMMARY_SHA256,
        P8_SCRIPT_PATH: EXPECTED_P8_SCRIPT_SHA256,
        P8_SUMMARY_PATH: EXPECTED_P8_SUMMARY_SHA256,
        REPO_ROOT / "src/wellplot/agent/code_mode/planner.py": EXPECTED_PLANNER_SOURCE_SHA256,
        REPO_ROOT / "src/wellplot/agent/providers/base.py": EXPECTED_PROVIDER_BASE_SHA256,
        REPO_ROOT
        / "src/wellplot/agent/providers/openai_compat_v2.py": EXPECTED_OPENAI_COMPAT_SHA256,
        REPO_ROOT / "src/wellplot/capabilities/builtins.py": EXPECTED_CAPABILITY_CATALOG_SHA256,
    }
    for path, expected in checks.items():
        if artifact_sha256(path) != expected:
            raise RuntimeError(f"CM-57P9A frozen artifact drifted: {path}")
    if _schema_sha256() != EXPECTED_SCHEMA_SHA256:
        raise RuntimeError("CM-57P9A response schema drifted.")
    if sha256_text(_PLANNER_SYSTEM_PROMPT) != EXPECTED_BASE_PROMPT_SHA256:
        raise RuntimeError("CM-57P9A production prompt drifted.")
    if PROMPT_SHA256["RC"] != EXPECTED_RC_PROMPT_SHA256:
        raise RuntimeError("CM-57P9A RC prompt drifted.")
    if sha256_text(canonical_json(FIXED_SOURCE_SUMMARY)) != EXPECTED_SOURCE_SUMMARY_SHA256:
        raise RuntimeError("CM-57P9A source summary drifted.")
    return {
        "p9a_manifest_sha256": artifact_sha256(MANIFEST_PATH),
        "p7_corpus_sha256": EXPECTED_P7_CORPUS_SHA256,
        "p7_summary_sha256": EXPECTED_P7_SUMMARY_SHA256,
        "p7_raw_sha256": EXPECTED_P7_RAW_SHA256,
        "p8_summary_sha256": EXPECTED_P8_SUMMARY_SHA256,
        "p8_raw_sha256": EXPECTED_P8_RAW_SHA256,
        "p9a_harness_sha256": artifact_sha256(Path(__file__)),
        "p_prompt_sha256": PROMPT_SHA256["P"],
        "rc_prompt_sha256": PROMPT_SHA256["RC"],
        "response_schema_sha256": EXPECTED_SCHEMA_SHA256,
        "provider_base_sha256": EXPECTED_PROVIDER_BASE_SHA256,
        "openai_compat_provider_sha256": EXPECTED_OPENAI_COMPAT_SHA256,
        "capability_catalog_sha256": EXPECTED_CAPABILITY_CATALOG_SHA256,
        "source_summary_sha256": EXPECTED_SOURCE_SUMMARY_SHA256,
        "selected_cases": len(cases),
    }


def _load_fingerprint(path: Path) -> dict[str, object]:
    """Load and validate one endpoint/model fingerprint."""
    value = json.loads(path.read_text(encoding="utf-8"))
    valid, reasons = fingerprint.validate_endpoint_fingerprint(value)
    if not valid:
        raise RuntimeError(f"Invalid runtime fingerprint: {', '.join(reasons)}")
    return value


def _api_key(args: argparse.Namespace) -> str:
    """Resolve the configured API key without exposing it in evidence."""
    api_key = os.getenv(args.api_key_env, "").strip()
    if args.api_key_file:
        path = Path(args.api_key_file)
        if not path.is_absolute():
            path = REPO_ROOT / path
        api_key = api_key or path.read_text(encoding="utf-8").strip()
    if not api_key:
        raise RuntimeError("No CM-57P9A API key configured.")
    return api_key


def _provider_configuration(
    args: argparse.Namespace,
    observer: ResponseObserver,
    *,
    api_key: str,
) -> ModelBackendProtocol:
    """Construct production provider only after all live guards pass."""
    from openai import AsyncOpenAI  # noqa: I001

    from wellplot.agent.providers.openai_compat_v2 import (  # noqa: I001
        OpenAICompatibleBackendV2,
    )

    client = AsyncOpenAI(api_key=api_key, base_url=args.base_url, timeout=TIMEOUT_SECONDS)
    return OpenAICompatibleBackendV2(
        model=FROZEN_MODEL,
        client=ObservedClient(client, observer),
        structured_output="json_schema",
        max_tokens_parameter=MAX_TOKENS_PARAMETER,
    )


async def _run_live(args: argparse.Namespace, checkpoint: str) -> None:
    """Run the exact 96-execution matrix with endpoint-level provenance."""
    if OUTPUT_PATH.exists() and OUTPUT_PATH.stat().st_size:
        raise RuntimeError(f"Refusing to append to non-empty evidence path {OUTPUT_PATH}.")
    verify_reviewed_checkout(checkpoint)
    contract = verify_frozen_contract()
    api_key = _api_key(args)
    pre = fingerprint.capture_endpoint_fingerprint(
        endpoint=args.base_url,
        model_api_label=FROZEN_MODEL,
        api_key=api_key,
    )
    pre_path = Path(args.runtime_fingerprint_pre)
    pre_path.write_text(json.dumps(pre, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    cases = load_manifest()
    registry = create_builtin_registry()
    observer = ResponseObserver(events=[])
    backend = _provider_configuration(args, observer, api_key=api_key)
    runtime_sha = sha256_text(canonical_json(pre))
    rows: list[dict[str, object]] = []
    with OUTPUT_PATH.open("a", encoding="utf-8") as handle:
        for case in cases:
            for repetition_index in range(ATTEMPTS):
                row = await run_row(
                    case,
                    repetition_index=repetition_index,
                    delegate=backend,
                    registry=registry,
                    observer=observer,
                    runtime_fingerprint_sha256=runtime_sha,
                    authorized_checkpoint=checkpoint,
                )
                rows.append(row)
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
                handle.flush()
    post = fingerprint.capture_endpoint_fingerprint(
        endpoint=args.base_url,
        model_api_label=FROZEN_MODEL,
        api_key=api_key,
    )
    post_path = Path(args.runtime_fingerprint_post)
    post_path.write_text(json.dumps(post, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "MATRIX_COMPLETE", **contract}, indent=2, sort_keys=True))


def finalize(
    *,
    checkpoint: str,
    evidence_path: Path,
    pre_path: Path,
    post_path: Path,
) -> dict[str, object]:
    """Finalize existing evidence without constructing a provider."""
    verify_reviewed_checkout(checkpoint)
    verify_frozen_contract()
    pre = _load_fingerprint(pre_path)
    post = _load_fingerprint(post_path)
    cases = load_manifest()
    rows = [
        json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines() if line
    ]
    return summarize_population(
        rows,
        cases,
        pre_fingerprint=pre,
        post_fingerprint=post,
        authorized_checkpoint=checkpoint,
    )


def prelive_report() -> dict[str, object]:
    """Run provider-free validation and describe the future population."""
    contract = verify_frozen_contract()
    return {
        "status": "PRELIVE_READY",
        "experiment": EXPERIMENT_VERSION,
        "provider_calls": 0,
        "worker_program_calls": 0,
        "production_changes": 0,
        "live_inference": "NOT_STARTED",
        "provenance_scope": "ENDPOINT_MODEL",
        "production_adoption": "NOT_AUTHORIZED",
        "CM57D": "BLOCKED",
        "cases": len(CASE_IDS),
        "arms": list(ARMS),
        "repetitions": ATTEMPTS,
        "planner_executions": len(CASE_IDS) * len(ARMS) * ATTEMPTS,
        "provider_calls_min": len(CASE_IDS) * len(ARMS) * ATTEMPTS,
        "provider_calls_max": len(CASE_IDS) * len(ARMS) * ATTEMPTS * 2,
        **contract,
    }


def _parser() -> argparse.ArgumentParser:
    """Build provider-free, live, and finalization CLI modes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-authorized", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--authorized-checkpoint")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="LLAMA_CPP_API_KEY")
    parser.add_argument(
        "--runtime-fingerprint-pre",
        default="/tmp/cm57p9a-endpoint-pre.json",
    )
    parser.add_argument(
        "--runtime-fingerprint-post",
        default="/tmp/cm57p9a-endpoint-post.json",
    )
    parser.add_argument("--evidence", default=str(OUTPUT_PATH))
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run provider-free validation unless an explicit future mode is selected."""
    args = _parser().parse_args(argv)
    if args.finalize:
        if not args.authorized_checkpoint:
            raise SystemExit("CM-57P9A finalization requires an authorized checkpoint.")
        print(
            json.dumps(
                finalize(
                    checkpoint=args.authorized_checkpoint,
                    evidence_path=Path(args.evidence),
                    pre_path=Path(args.runtime_fingerprint_pre),
                    post_path=Path(args.runtime_fingerprint_post),
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not args.live_authorized:
        print(json.dumps(prelive_report(), indent=2, sort_keys=True))
        return 0
    required = (args.authorized_checkpoint, args.base_url)
    if not all(required):
        raise SystemExit("CM-57P9A live mode requires checkpoint and base URL.")
    asyncio.run(_run_live(args, args.authorized_checkpoint))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
