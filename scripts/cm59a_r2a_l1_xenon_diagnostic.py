"""CM-59A-R2A-L1 Xenon structured-response diagnostic.

The default command performs only provider-free validation. Live execution is
available only behind an exact-checkout authorization flag and is limited to
two sequential planner attempts for the frozen Xenon case.
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
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import cm57p5_fresh_holdout as p5  # noqa: E402
from scripts import cm57p6_report_invariant_bisect as p6  # noqa: E402
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
from wellplot.agent.providers.response_diagnostics import (  # noqa: E402
    ProviderResponseFailureReason,
    StructuredResponseProviderError,
)
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry  # noqa: E402

EXPERIMENT_VERSION = "CM-59A-R2A-L1"
CONTRACT_VERSION = "cm59a.r2a.l1.xenon-diagnostic.v1"
PRODUCTION_ANCHOR_SHA = "866037452f6c1944297d62270756b4e3a5322125"
CASE_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json"
OUTPUT_PATH = Path("/tmp/cm59a-r2a-l1-xenon-diagnostic.jsonl")
ENDPOINT_PRE_PATH = Path("/tmp/cm59a-r2a-l1-endpoint-pre.json")
ENDPOINT_POST_PATH = Path("/tmp/cm59a-r2a-l1-endpoint-post.json")
SUMMARY_PATH = Path("/tmp/cm59a-r2a-l1-summary.json")
CORPUS_SHA256 = "b6a605158e667e5250df99a53cb4ba521473f8146fad2022aed2dff77d5f551b"
TARGET_CASE_ID = "cm59-mixed-xenon-21"
TARGET_REQUEST_SHA256 = "c0f175abcb01eb875126d2bd3a2a8a6cd2efcf2207494419ce27edc82d8802c5"
TARGET_FAMILY = "MIXED_REPORT_SECTION"
TARGET_REPORT = ["report.standard"]
TARGET_SECTIONS = [["section.log_plot", "track.array", "binding.raster"]]
TARGET_UNRESOLVED = 0
FROZEN_MODEL = "qwen3.6-35b-a3b"
PLANNER_TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 16384
MAX_TOKENS_PARAMETER = "max_tokens"
TIMEOUT_SECONDS = 900.0
ATTEMPTS = 2
EXPECTED_PROMPT_SHA256 = "5e7a0732af01e4b1f16b3ccf019c005ea2e9ba5c0e93e94870a56a261e2bca18"
EXPECTED_SCHEMA_SHA256 = "3a331166ccc570a74056dea7770d04b16f8fa32dc3641d6c37de6c26cf81d9e3"
EXPECTED_SOURCE_SUMMARY_SHA256 = "ec6147a1b5e1ac6374e34ae3d66d11275542c6b340337cb26d3ae1d06240532e"
REASONS = tuple(reason.value for reason in ProviderResponseFailureReason)
ALLOWED_CALL_KINDS = {"INITIAL", "INVALID_RESPONSE_RETRY", "SEMANTIC_CORRECTION"}
ALLOWED_OUTCOMES = {"structured_success", "provider_failure", "structured_output_failure"}
INFRASTRUCTURE_CATEGORIES = {
    ProviderFailureCategory.CONFIGURATION.value,
    ProviderFailureCategory.AUTHENTICATION.value,
    ProviderFailureCategory.TIMEOUT.value,
    ProviderFailureCategory.RATE_LIMIT.value,
    ProviderFailureCategory.TRANSPORT.value,
}
CHECKPOINT_RE = re.compile(r"^[0-9a-f]{40}$")
PROTECTED_ARTIFACTS = (
    "src/wellplot/agent/code_mode/planner.py",
    "src/wellplot/agent/providers/base.py",
    "src/wellplot/agent/providers/openai_compat_v2.py",
    "src/wellplot/agent/providers/response_diagnostics.py",
    "src/wellplot/capabilities/builtins.py",
    "scripts/cm57p5_fresh_holdout.py",
    "scripts/cm57p9_runtime_fingerprint.py",
    "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json",
)
FROZEN_CONTROLS = {
    "model": FROZEN_MODEL,
    "planner_temperature": PLANNER_TEMPERATURE,
    "max_output_tokens": MAX_OUTPUT_TOKENS,
    "max_tokens_parameter": MAX_TOKENS_PARAMETER,
    "timeout_seconds": TIMEOUT_SECONDS,
    "concurrency": 1,
    "mode": "reconstruct",
}


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
    """Return the current full checkout SHA."""
    return _git_output("rev-parse", "HEAD").decode().strip()


def _anchor_blob(relative_path: str) -> bytes:
    """Read one protected artifact from the accepted production anchor."""
    return _git_output("show", f"{PRODUCTION_ANCHOR_SHA}:{relative_path}")


def _schema_sha256() -> str:
    """Hash the production SemanticPlan response schema."""
    return p6.schema_sha256(SemanticPlan)


def _source_summary() -> dict[str, object]:
    """Return the established bounded production source summary."""
    return p5.FIXED_SOURCE_SUMMARY


def _source_summary_sha256() -> str:
    """Hash the established source summary."""
    return sha256_text(canonical_json(_source_summary()))


def _production_source_hashes() -> dict[str, str]:
    """Return hashes for production artifacts used by the diagnostic."""
    return {path: artifact_sha256(REPO_ROOT / path) for path in PROTECTED_ARTIFACTS}


def _load_target_case() -> dict[str, object]:
    """Load the one Xenon case from the authoritative CM-59A corpus."""
    if artifact_sha256(CASE_PATH) != CORPUS_SHA256:
        raise RuntimeError("CM-59A corpus drifted.")
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    if payload.get("version") != "cm59a.system-reevaluation.v1":
        raise RuntimeError("Unexpected CM-59A corpus version.")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise RuntimeError("CM-59A corpus cases are malformed.")
    matches = [
        case for case in cases if isinstance(case, dict) and case.get("case_id") == TARGET_CASE_ID
    ]
    if len(matches) != 1:
        raise RuntimeError("Xenon target case is missing or duplicated.")
    case = matches[0]
    if (
        sha256_text(str(case.get("request"))) != TARGET_REQUEST_SHA256
        or case.get("family") != TARGET_FAMILY
        or case.get("residual_class") is not None
        or case.get("expected_report_capabilities") != TARGET_REPORT
        or case.get("expected_sections") != TARGET_SECTIONS
        or case.get("expected_unresolved_count") != TARGET_UNRESOLVED
    ):
        raise RuntimeError("Xenon target case semantics drifted.")
    registry = create_builtin_registry()
    p5._validate_report_gold(TARGET_REPORT, registry, TARGET_CASE_ID)
    for section in TARGET_SECTIONS:
        p5._validate_section_gold(section, registry, TARGET_CASE_ID)
    return case


def _verify_production_anchor() -> None:
    """Require all protected production bytes to match the accepted anchor."""
    for relative_path in PROTECTED_ARTIFACTS:
        path = REPO_ROOT / relative_path
        if not path.is_file() or path.read_bytes() != _anchor_blob(relative_path):
            raise RuntimeError(f"L1 production artifact drifted: {relative_path}")


def _verify_static_contract() -> dict[str, object]:
    """Run all provider-free contract checks needed before live authorization."""
    case = _load_target_case()
    _verify_production_anchor()
    prompt_sha = sha256_text(_PLANNER_SYSTEM_PROMPT)
    schema_sha = _schema_sha256()
    source_sha = _source_summary_sha256()
    if prompt_sha != EXPECTED_PROMPT_SHA256:
        raise RuntimeError("L1 planner prompt drifted.")
    if schema_sha != EXPECTED_SCHEMA_SHA256:
        raise RuntimeError("L1 SemanticPlan schema drifted.")
    if source_sha != EXPECTED_SOURCE_SUMMARY_SHA256:
        raise RuntimeError("L1 source summary drifted.")
    if (
        set(REASONS)
        != {
            "unusable_choice",
            "missing_message",
            "non_assistant_message",
            "incomplete_output",
            "unexpected_finish_reason",
            "tool_call",
            "missing_content",
            "invalid_json",
            "schema_validation",
        }
        or len(REASONS) != 9
    ):
        raise RuntimeError("L1 response reason taxonomy drifted.")
    return {
        "target_case": case,
        "corpus_sha256": CORPUS_SHA256,
        "prompt_sha256": prompt_sha,
        "response_schema_sha256": schema_sha,
        "source_summary_sha256": source_sha,
        "production_source_hashes": _production_source_hashes(),
    }


def frozen_provenance() -> dict[str, object]:
    """Return provenance bound to each future evidence row."""
    return {
        "diagnostic_version": EXPERIMENT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "production_anchor_sha": PRODUCTION_ANCHOR_SHA,
        "harness_sha256": artifact_sha256(Path(__file__)),
        "corpus_sha256": CORPUS_SHA256,
        "prompt_sha256": EXPECTED_PROMPT_SHA256,
        "response_schema_sha256": EXPECTED_SCHEMA_SHA256,
        "source_summary_sha256": EXPECTED_SOURCE_SUMMARY_SHA256,
        "production_source_hashes": _production_source_hashes(),
        "execution_controls": dict(FROZEN_CONTROLS),
    }


def _plan_projection(plan: SemanticPlan | None) -> dict[str, object] | None:
    """Project a plan without retaining provider-generated prose."""
    return p5._plan_projection(plan) if plan is not None else None


def _raw_facts(
    plan: SemanticPlan | None,
    case: dict[str, object],
    registry: CapabilityRegistry,
) -> dict[str, object] | None:
    """Project bounded semantic facts for a returned plan."""
    return p5._facts(plan, case, registry) if plan is not None else None


def _classify_provider_error(error: ProviderRequestError) -> tuple[str, str | None]:
    """Classify a provider error without parsing any error text."""
    category = error.category.value
    if category in INFRASTRUCTURE_CATEGORIES:
        return "INFRA_FAILURE", None
    if category == ProviderFailureCategory.INVALID_RESPONSE.value:
        if isinstance(error, StructuredResponseProviderError):
            return "TERMINAL_INVALID_RESPONSE", error.response_reason.value
        return "DIAGNOSTIC_GAP", None
    return "OTHER_PLANNER_TERMINAL", None


@dataclass
class RecordingBackend(ModelBackendProtocol):
    """Record only bounded planner-call facts."""

    delegate: ModelBackendProtocol
    calls: list[dict[str, object]]
    program_calls: int = 0

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Record one production planner call without retaining its response."""
        if not self.calls:
            call_kind = "INITIAL"
        elif "Correction context:" in request.user_prompt:
            call_kind = "SEMANTIC_CORRECTION"
        else:
            call_kind = "INVALID_RESPONSE_RETRY"
        record: dict[str, object] = {
            "call_kind": call_kind,
            "response_reason": None,
        }
        try:
            result = await self.delegate.generate_structured(request, response_model=response_model)
        except ProviderRequestError as error:
            record["provider_category"] = error.category.value
            record["outcome"] = (
                "structured_output_failure"
                if error.category is ProviderFailureCategory.INVALID_RESPONSE
                else "provider_failure"
            )
            if isinstance(error, StructuredResponseProviderError):
                record["response_reason"] = error.response_reason.value
            self.calls.append(record)
            raise
        except ValidationError:
            record.update(
                {
                    "provider_category": ProviderFailureCategory.INVALID_RESPONSE.value,
                    "outcome": "structured_output_failure",
                }
            )
            self.calls.append(record)
            raise
        record["provider_category"] = None
        record["outcome"] = "structured_success"
        record["metrics"] = result.metrics.public_metadata()
        if not isinstance(result.value, SemanticPlan):
            raise TypeError("L1 planner returned an unexpected response model.")
        record["plan"] = _plan_projection(result.value)
        self.calls.append(record)
        return result

    async def generate_program(self, request: object) -> object:
        """Reject accidental worker/program execution."""
        self.program_calls += 1
        raise AssertionError(f"L1 must not call program generation: {request!r}")


async def run_attempt(
    case: dict[str, object],
    *,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
    attempt_index: int,
) -> dict[str, object]:
    """Run one unchanged production planner execution."""
    calls: list[dict[str, object]] = []
    backend = RecordingBackend(delegate=delegate, calls=calls)
    planner = SemanticPlanner(backend=backend, registry=registry)
    plan: SemanticPlan | None = None
    attempt_classification = "PLANNER_SUCCESS"
    final_provider_category: str | None = None
    final_response_reason: str | None = None
    terminal_signature: str | None = None
    try:
        plan = await planner.plan(
            request=str(case["request"]),
            mode="reconstruct",
            current_document_summary={},
            source_summary=_source_summary(),
            timeout_seconds=TIMEOUT_SECONDS,
            temperature=PLANNER_TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
    except ProviderRequestError as error:
        attempt_classification, final_response_reason = _classify_provider_error(error)
        final_provider_category = error.category.value
        terminal_signature = final_response_reason or final_provider_category
    except PlannerSemanticFailure as error:
        attempt_classification = "OTHER_PLANNER_TERMINAL"
        terminal_signature = error.code
    except ValidationError:
        attempt_classification = "DIAGNOSTIC_GAP"
        final_provider_category = ProviderFailureCategory.INVALID_RESPONSE.value
        terminal_signature = "missing_response_reason"

    facts = _raw_facts(plan, case, registry)
    return {
        "attempt_index": attempt_index,
        "planner_call_count": len(calls),
        "invalid_response_retry_used": any(
            call["call_kind"] == "INVALID_RESPONSE_RETRY" for call in calls
        ),
        "semantic_correction_used": any(
            call["call_kind"] == "SEMANTIC_CORRECTION" for call in calls
        ),
        "final_plan_available": plan is not None,
        "final_provider_category": final_provider_category,
        "final_response_reason": final_response_reason,
        "provider_infrastructure_failure": any(
            call.get("provider_category") in INFRASTRUCTURE_CATEGORIES for call in calls
        ),
        "raw_plan_projection": _plan_projection(plan),
        "raw_work_unit_facts": facts,
        "raw_contract_ok": plan is not None and p5.final_contract_ok(facts or {}),
        "attempt_classification": attempt_classification,
        "terminal_signature": terminal_signature,
        "call_trace": calls,
        "program_calls": backend.program_calls,
    }


async def run_row(
    case: dict[str, object],
    *,
    attempt_index: int,
    delegate: ModelBackendProtocol,
    registry: CapabilityRegistry,
    authorized_checkpoint: str,
    pre_fingerprint_sha256: str,
) -> dict[str, object]:
    """Run one diagnostic attempt and bind it to frozen provenance."""
    result = await run_attempt(
        case,
        delegate=delegate,
        registry=registry,
        attempt_index=attempt_index,
    )
    return {
        **frozen_provenance(),
        "authorized_harness_checkpoint": authorized_checkpoint,
        "pre_endpoint_fingerprint_sha256": pre_fingerprint_sha256,
        "case_id": case["case_id"],
        "request_sha256": sha256_text(str(case["request"])),
        "attempt_index": attempt_index,
        "attempt": result,
    }


def classify_attempts(attempts: list[dict[str, object]]) -> str:
    """Classify the two attempts without applying a pass/fail threshold."""
    if len(attempts) != ATTEMPTS:
        return "INCONCLUSIVE_DIAGNOSTIC"
    classes = [str(attempt.get("attempt_classification")) for attempt in attempts]
    if any(value == "INFRA_FAILURE" for value in classes):
        return "INCONCLUSIVE_DIAGNOSTIC"
    if any(value == "DIAGNOSTIC_GAP" for value in classes):
        return "DIAGNOSTIC_INSTRUMENTATION_GAP"
    if classes == ["TERMINAL_INVALID_RESPONSE", "TERMINAL_INVALID_RESPONSE"]:
        reasons = [attempt.get("final_response_reason") for attempt in attempts]
        if all(isinstance(reason, str) and reason for reason in reasons):
            if reasons[0] == reasons[1]:
                return "STABLE_INVALID_RESPONSE_REASON"
            return "VARIABLE_INVALID_RESPONSE_REASON"
        return "DIAGNOSTIC_INSTRUMENTATION_GAP"
    if classes == ["PLANNER_SUCCESS", "PLANNER_SUCCESS"]:
        return "HISTORICAL_FAILURE_NOT_REPRODUCED"
    if classes[0] == classes[1] == "OTHER_PLANNER_TERMINAL":
        signatures = [attempt.get("terminal_signature") for attempt in attempts]
        if signatures[0] == signatures[1]:
            return "OTHER_STABLE_PLANNER_TERMINAL"
    return "MIXED_DIAGNOSTIC_OUTCOME"


def population_integrity(
    rows: list[dict[str, object]],
    *,
    expected_checkpoint: str | None = None,
    pre_fingerprint: dict[str, object] | None = None,
) -> tuple[bool, list[str]]:
    """Fail closed on the two-row population and all bounded provenance."""
    reasons: set[str] = set()
    if len(rows) != ATTEMPTS:
        reasons.add("wrong_row_count")
    if {row.get("case_id") for row in rows} != {TARGET_CASE_ID}:
        reasons.add("case_id_mismatch")
    if {row.get("attempt_index") for row in rows} != set(range(ATTEMPTS)):
        reasons.add("attempt_index_mismatch")
    if len({(row.get("case_id"), row.get("attempt_index")) for row in rows}) != len(rows):
        reasons.add("duplicate_attempt")
    if expected_checkpoint is not None and any(
        row.get("authorized_harness_checkpoint") != expected_checkpoint for row in rows
    ):
        reasons.add("checkpoint_mismatch")
    expected_pre = (
        sha256_text(canonical_json(pre_fingerprint)) if pre_fingerprint is not None else None
    )
    if expected_pre is None or any(
        row.get("pre_endpoint_fingerprint_sha256") != expected_pre for row in rows
    ):
        reasons.add("pre_fingerprint_mismatch")
    expected_provenance = frozen_provenance()
    for row in rows:
        for key, value in expected_provenance.items():
            if row.get(key) != value:
                reasons.add(f"{key}_mismatch")
        if row.get("request_sha256") != TARGET_REQUEST_SHA256:
            reasons.add("request_hash_mismatch")
        attempt = row.get("attempt")
        if not isinstance(attempt, dict):
            reasons.add("attempt_missing")
            continue
        if int(attempt.get("program_calls", -1)) != 0:
            reasons.add("program_calls")
        call_trace = attempt.get("call_trace")
        if not isinstance(call_trace, list) or not 1 <= len(call_trace) <= 2:
            reasons.add("provider_call_count")
            continue
        if int(attempt.get("planner_call_count", -1)) != len(call_trace):
            reasons.add("call_trace_mismatch")
        for call in call_trace:
            if not isinstance(call, dict) or call.get("call_kind") not in ALLOWED_CALL_KINDS:
                reasons.add("call_kind_invalid")
                continue
            if call.get("outcome") not in ALLOWED_OUTCOMES:
                reasons.add("call_outcome_invalid")
            category = call.get("provider_category")
            reason = call.get("response_reason")
            if category == ProviderFailureCategory.INVALID_RESPONSE.value and reason not in REASONS:
                reasons.add("invalid_response_reason_missing")
            if reason is not None and reason not in REASONS:
                reasons.add("response_reason_invalid")
    return not reasons, sorted(reasons)


def _endpoint_status(
    pre: dict[str, object] | None,
    post: dict[str, object] | None,
) -> tuple[bool, list[str]]:
    """Validate and compare normalized endpoint identity."""
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


def _rows_by_attempt(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return rows in deterministic attempt order."""
    return sorted(rows, key=lambda row: int(row.get("attempt_index", -1)))


def summarize_population(
    rows: list[dict[str, object]],
    *,
    pre_fingerprint: dict[str, object] | None,
    post_fingerprint: dict[str, object] | None,
    expected_checkpoint: str | None = None,
    evidence_bytes: bytes | None = None,
) -> dict[str, object]:
    """Finalize the diagnostic without provider or endpoint access."""
    population_ok, population_reasons = population_integrity(
        rows,
        expected_checkpoint=expected_checkpoint,
        pre_fingerprint=pre_fingerprint,
    )
    endpoint_equal, endpoint_reasons = _endpoint_status(pre_fingerprint, post_fingerprint)
    attempts = _rows_by_attempt(rows)
    decision = "INCONCLUSIVE_DIAGNOSTIC"
    case_decision: str | None = None
    stable_reason: str | None = None
    if population_ok and endpoint_equal:
        attempt_values = [row["attempt"] for row in attempts]
        case_decision = classify_attempts(attempt_values)
        decision = case_decision
        if decision == "STABLE_INVALID_RESPONSE_REASON":
            stable_reason = str(attempt_values[0]["final_response_reason"])
        if decision == "INCONCLUSIVE_DIAGNOSTIC":
            decision = "INCONCLUSIVE_DIAGNOSTIC"
    return {
        "diagnostic_version": EXPERIMENT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "production_anchor_sha": PRODUCTION_ANCHOR_SHA,
        "authorized_harness_checkpoint": expected_checkpoint,
        "case_id": TARGET_CASE_ID,
        "request_sha256": TARGET_REQUEST_SHA256,
        "row_count": len(rows),
        "provider_call_count": sum(
            int(row.get("attempt", {}).get("planner_call_count", 0))
            for row in rows
            if isinstance(row.get("attempt"), dict)
        ),
        "worker_program_call_count": sum(
            int(row.get("attempt", {}).get("program_calls", 0))
            for row in rows
            if isinstance(row.get("attempt"), dict)
        ),
        "attempt_outcomes": [
            row.get("attempt", {}).get("attempt_classification")
            for row in attempts
            if isinstance(row.get("attempt"), dict)
        ],
        "response_reasons": [
            row.get("attempt", {}).get("final_response_reason")
            for row in attempts
            if isinstance(row.get("attempt"), dict)
        ],
        "stable_response_reason": stable_reason,
        "pre_normalized_identity": (
            pre_fingerprint.get("normalized_identity_sha256") if pre_fingerprint else None
        ),
        "post_normalized_identity": (
            post_fingerprint.get("normalized_identity_sha256") if post_fingerprint else None
        ),
        "endpoint_identity_equal": endpoint_equal,
        "infrastructure_failures": sum(
            int(row.get("attempt", {}).get("provider_infrastructure_failure", False))
            for row in rows
            if isinstance(row.get("attempt"), dict)
        ),
        "population_integrity": population_ok,
        "population_integrity_reasons": population_reasons,
        "endpoint_integrity_reasons": endpoint_reasons,
        "case_decision": case_decision,
        "decision": decision,
        "raw_evidence_sha256": (
            hashlib.sha256(evidence_bytes).hexdigest() if evidence_bytes is not None else None
        ),
    }


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    """Load bounded JSONL evidence without contacting a provider."""
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("L1 evidence rows must be objects.")
        rows.append(value)
    return rows


def _load_json_object(path: Path) -> dict[str, object]:
    """Load one bounded JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("L1 fingerprint must be an object.")
    return value


def prelive_report() -> dict[str, object]:
    """Return the provider-free L1 pre-live report."""
    contract = _verify_static_contract()
    return {
        "status": "PRELIVE_READY",
        "diagnostic_version": EXPERIMENT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "production_anchor_sha": PRODUCTION_ANCHOR_SHA,
        "target_case": TARGET_CASE_ID,
        "attempts": ATTEMPTS,
        "future_planner_executions": ATTEMPTS,
        "future_inference_calls_min": ATTEMPTS,
        "future_inference_calls_max": ATTEMPTS * 2,
        "worker_program_calls": 0,
        "provider_calls": 0,
        "endpoint_calls": 0,
        "production_delta": 0,
        "corpus_valid": True,
        "prompt_valid": True,
        "schema_valid": True,
        "source_summary_valid": True,
        "raw_provider_retention": 0,
        "resume": "FORBIDDEN",
        "artifact_paths": {
            "evidence": str(OUTPUT_PATH),
            "endpoint_pre": str(ENDPOINT_PRE_PATH),
            "endpoint_post": str(ENDPOINT_POST_PATH),
            "summary": str(SUMMARY_PATH),
        },
        "future_live": "NOT_AUTHORIZED",
        **{key: value for key, value in contract.items() if key != "target_case"},
    }


def _verify_reviewed_checkout(checkpoint: str) -> None:
    """Require exact L1 checkout and unchanged protected production bytes."""
    if CHECKPOINT_RE.fullmatch(checkpoint) is None or current_checkout_sha() != checkpoint:
        raise RuntimeError("L1 checkout does not match the authorized checkpoint.")
    _verify_production_anchor()
    for relative_path in (
        "scripts/cm59a_r2a_l1_xenon_diagnostic.py",
        "tests/test_cm59a_r2a_l1_xenon_diagnostic.py",
        str(CASE_PATH.relative_to(REPO_ROOT)),
    ):
        path = REPO_ROOT / relative_path
        if not path.is_file() or path.read_bytes() != _git_output(
            "show", f"{checkpoint}:{relative_path}"
        ):
            raise RuntimeError(f"L1 guarded artifact drifted: {relative_path}")


def _ensure_empty(path: Path) -> None:
    """Reject non-empty artifacts without deleting or resuming them."""
    if path.exists() and path.stat().st_size:
        raise RuntimeError(f"L1 artifact path is non-empty: {path}")


def _api_key(args: argparse.Namespace) -> str:
    """Resolve an API key without retaining it in evidence."""
    value = os.getenv(args.api_key_env, "").strip()
    if args.api_key_file:
        path = Path(args.api_key_file)
        if not path.is_absolute():
            path = REPO_ROOT / path
        value = value or path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError("No L1 API key configured.")
    return value


def _provider_configuration(args: argparse.Namespace) -> ModelBackendProtocol:
    """Construct the provider only after all live guards and PRE capture."""
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


async def _run_live(args: argparse.Namespace, checkpoint: str) -> None:
    """Run exactly two sequential planner-only attempts."""
    _verify_reviewed_checkout(checkpoint)
    _verify_static_contract()
    paths = (
        Path(args.evidence_path),
        Path(args.endpoint_fingerprint_pre),
        Path(args.endpoint_fingerprint_post),
        Path(args.summary_path),
    )
    for path in paths:
        _ensure_empty(path)
    case = _load_target_case()
    pre = fingerprint.capture_endpoint_fingerprint_v2(
        endpoint=args.base_url,
        model_api_label=FROZEN_MODEL,
        api_key=_api_key(args),
        timeout_seconds=20.0,
    )
    pre_bytes = canonical_json(pre) + "\n"
    Path(args.endpoint_fingerprint_pre).write_text(pre_bytes, encoding="utf-8")
    pre_sha = sha256_text(canonical_json(pre))
    provider = _provider_configuration(args)
    registry = create_builtin_registry()
    with Path(args.evidence_path).open("w", encoding="utf-8") as handle:
        for attempt_index in range(ATTEMPTS):
            row = await run_row(
                case,
                attempt_index=attempt_index,
                delegate=provider,
                registry=registry,
                authorized_checkpoint=checkpoint,
                pre_fingerprint_sha256=pre_sha,
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


def finalize(
    *,
    evidence_path: Path,
    pre_path: Path,
    post_path: Path,
    authorized_checkpoint: str,
) -> dict[str, object]:
    """Finalize preserved evidence without provider or endpoint access."""
    _verify_reviewed_checkout(authorized_checkpoint)
    _verify_static_contract()
    evidence_bytes = evidence_path.read_bytes()
    rows = _load_jsonl(evidence_path)
    pre = _load_json_object(pre_path)
    post = _load_json_object(post_path)
    return summarize_population(
        rows,
        pre_fingerprint=pre,
        post_fingerprint=post,
        expected_checkpoint=authorized_checkpoint,
        evidence_bytes=evidence_bytes,
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
    """Run provider-free audit, authorized live execution, or finalization."""
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
