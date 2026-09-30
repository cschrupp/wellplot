"""CM-59A-R2C-A bounded schema-validation-shape diagnostic.

The default command is provider-free. Live execution is guarded behind an
explicit checkpoint and is intentionally limited to the two E2 failure cases.
Only sanitized Pydantic validation shape is retained; response content and
validation messages never enter evidence.
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
from pathlib import Path

from pydantic import BaseModel, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import cm57p9_runtime_fingerprint as fingerprint  # noqa: E402
from scripts import cm59a_system_reevaluation as historical  # noqa: E402
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
    MAX_SCHEMA_VALIDATION_ISSUES,
    MAX_SCHEMA_VALIDATION_LOCATION_DEPTH,
    ProviderResponseFailureReason,
    ProviderSchemaValidationShape,
    StructuredResponseProviderError,
)
from wellplot.capabilities import create_builtin_registry  # noqa: E402

BASELINE_SHA = "17540f98c9c035ae07385b28c71bd11dccff323b"
EXPERIMENT_VERSION = "CM-59A-R2C-A"
DIAGNOSTIC_CONTRACT_VERSION = "cm59a.r2c.a.schema-validation-shape.v1"
CASE_PATH = REPO_ROOT / "tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json"
OUTPUT_PATH = Path("/tmp/cm59a-r2c-a-schema-shape.jsonl")
ENDPOINT_PRE_PATH = Path("/tmp/cm59a-r2c-a-endpoint-pre.json")
ENDPOINT_POST_PATH = Path("/tmp/cm59a-r2c-a-endpoint-post.json")
SUMMARY_PATH = Path("/tmp/cm59a-r2c-a-summary.json")
FROZEN_MODEL = "qwen3.6-35b-a3b"
PLANNER_TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 16384
MAX_TOKENS_PARAMETER = "max_tokens"
TIMEOUT_SECONDS = 900.0
ATTEMPTS = 2
EXPECTED_CORPUS_SHA256 = "b6a605158e667e5250df99a53cb4ba521473f8146fad2022aed2dff77d5f551b"
EXPECTED_PROMPT_SHA256 = "5e7a0732af01e4b1f16b3ccf019c005ea2e9ba5c0e93e94870a56a261e2bca18"
EXPECTED_SCHEMA_SHA256 = "3a331166ccc570a74056dea7770d04b16f8fa32dc3641d6c37de6c26cf81d9e3"
EXPECTED_SOURCE_SUMMARY_SHA256 = "ec6147a1b5e1ac6374e34ae3d66d11275542c6b340337cb26d3ae1d06240532e"
EXPECTED_ENDPOINT_IDENTITY = "23afb5ebf67063154bcf02ada6d25b2c929250b14c6a4cad06e8649d087bc980"
EXPECTED_REQUEST_HASHES = {
    "cm59-report-kestrel-04": "8400815f448d35955497cbe9c7cb661a56431ec410e3c14b591e5d72435fa12b",
    "cm59-mixed-xenon-21": "c0f175abcb01eb875126d2bd3a2a8a6cd2efcf2207494419ce27edc82d8802c5",
}
TARGET_CASES = ("cm59-report-kestrel-04", "cm59-mixed-xenon-21")
CALL_KINDS = {"INITIAL", "INVALID_RESPONSE_RETRY", "SCHEMA_CORRECTION", "SEMANTIC_CORRECTION"}
RESPONSE_REASONS = {reason.value for reason in ProviderResponseFailureReason}
INFRASTRUCTURE_CATEGORIES = {
    ProviderFailureCategory.CONFIGURATION.value,
    ProviderFailureCategory.AUTHENTICATION.value,
    ProviderFailureCategory.TIMEOUT.value,
    ProviderFailureCategory.RATE_LIMIT.value,
    ProviderFailureCategory.TRANSPORT.value,
}
FROZEN_EXECUTION_CONTROLS = {
    "model": FROZEN_MODEL,
    "planner_temperature": PLANNER_TEMPERATURE,
    "max_output_tokens": MAX_OUTPUT_TOKENS,
    "max_tokens_parameter": MAX_TOKENS_PARAMETER,
    "timeout_seconds": TIMEOUT_SECONDS,
    "concurrency": 1,
    "mode": "reconstruct",
    "current_document_summary": {},
}
INSTRUMENTED_ARTIFACTS = {
    "src/wellplot/agent/providers/openai_compat_v2.py",
    "src/wellplot/agent/providers/response_diagnostics.py",
}
PROTECTED_ARTIFACTS = (
    "src/wellplot/agent/code_mode/planner.py",
    "src/wellplot/agent/code_mode/capability_safety.py",
    "src/wellplot/agent/code_mode/report_boundary_safety.py",
    "src/wellplot/agent/code_mode/section_leaf_safety.py",
    "src/wellplot/agent/code_mode/workflow.py",
    "src/wellplot/capabilities/builtins.py",
    "src/wellplot/agent/providers/base.py",
    "scripts/cm57p9_runtime_fingerprint.py",
)
CHECKPOINT_RE = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_LOCATION_SEGMENTS = {"$root", "*", "<unknown_field>", "<unknown_segment>", "<truncated>"}
ERROR_TYPE_PATTERN = re.compile(r"^[a-z0-9_.-]{1,64}$")


def _declared_schema_fields(schema: object) -> frozenset[str]:
    """Collect every JSON Schema property name exposed by the response model."""
    fields: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict):
                fields.update(key for key in properties if isinstance(key, str))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    return frozenset(fields)


DECLARED_SCHEMA_FIELDS = _declared_schema_fields(SemanticPlan.model_json_schema())


def canonical_json(value: object) -> str:
    """Serialize JSON-shaped evidence deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    """Hash exact UTF-8 text bytes."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def artifact_sha256(path: Path) -> str:
    """Hash one local artifact by exact bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_output(*arguments: str) -> bytes:
    """Return exact output from a repository-local Git command."""
    return subprocess.check_output(["git", *arguments], cwd=REPO_ROOT, stderr=subprocess.STDOUT)


def current_checkout_sha() -> str:
    """Return the current checkout SHA."""
    return _git_output("rev-parse", "HEAD").decode().strip()


def _baseline_blob(relative_path: str) -> bytes:
    """Read one protected artifact from the E2 result checkpoint."""
    return _git_output("show", f"{BASELINE_SHA}:{relative_path}")


def load_target_cases(path: Path = CASE_PATH) -> tuple[dict[str, object], ...]:
    """Load only the two frozen E2 failure cases."""
    if artifact_sha256(path) != EXPECTED_CORPUS_SHA256:
        raise RuntimeError("CM-59A-R2C-A corpus hash drifted.")
    cases = historical.load_case_definitions(path)
    by_id = {str(case["case_id"]): case for case in cases}
    if set(by_id) & set(TARGET_CASES) != set(TARGET_CASES):
        raise RuntimeError("CM-59A-R2C-A target case set drifted.")
    selected = tuple(by_id[case_id] for case_id in TARGET_CASES)
    for case in selected:
        case_id = str(case["case_id"])
        if sha256_text(str(case["request"])) != EXPECTED_REQUEST_HASHES[case_id]:
            raise RuntimeError(f"Request hash drifted for {case_id}.")
    return selected


def _schema_sha256() -> str:
    """Hash the frozen SemanticPlan response schema."""
    return historical._schema_sha256()


def _source_summary() -> dict[str, object]:
    """Return the frozen bounded source summary."""
    return historical._source_summary()


def _source_summary_sha256() -> str:
    """Hash the canonical source summary."""
    return sha256_text(canonical_json(_source_summary()))


def _production_source_hashes() -> dict[str, str]:
    """Hash protected and instrumented runtime files separately."""
    return {
        relative_path: artifact_sha256(REPO_ROOT / relative_path)
        for relative_path in (*PROTECTED_ARTIFACTS, *sorted(INSTRUMENTED_ARTIFACTS))
    }


def frozen_provenance() -> dict[str, object]:
    """Return exact provenance placed on every future evidence row."""
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "diagnostic_contract_version": DIAGNOSTIC_CONTRACT_VERSION,
        "behavior_baseline_sha": BASELINE_SHA,
        "corpus_sha256": artifact_sha256(CASE_PATH),
        "harness_sha256": artifact_sha256(Path(__file__)),
        "P_prompt_sha256": sha256_text(_PLANNER_SYSTEM_PROMPT),
        "response_schema_sha256": _schema_sha256(),
        "source_summary_sha256": _source_summary_sha256(),
        "production_source_hashes": _production_source_hashes(),
        "execution_controls": dict(FROZEN_EXECUTION_CONTROLS),
    }


def verify_frozen_contract() -> dict[str, object]:
    """Verify the provider-free corpus and all frozen planner contracts."""
    cases = load_target_cases()
    for relative_path in PROTECTED_ARTIFACTS:
        if (REPO_ROOT / relative_path).read_bytes() != _baseline_blob(relative_path):
            raise RuntimeError(f"Protected production artifact drifted: {relative_path}")
    if sha256_text(_PLANNER_SYSTEM_PROMPT) != EXPECTED_PROMPT_SHA256:
        raise RuntimeError("Planner prompt drifted.")
    if _schema_sha256() != EXPECTED_SCHEMA_SHA256:
        raise RuntimeError("SemanticPlan schema drifted.")
    if _source_summary_sha256() != EXPECTED_SOURCE_SUMMARY_SHA256:
        raise RuntimeError("Source summary drifted.")
    if len(cases) != 2:
        raise RuntimeError("Target population size drifted.")
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "diagnostic_contract_version": DIAGNOSTIC_CONTRACT_VERSION,
        "behavior_baseline_sha": BASELINE_SHA,
        "corpus_sha256": artifact_sha256(CASE_PATH),
        "harness_sha256": artifact_sha256(Path(__file__)),
        "P_prompt_sha256": sha256_text(_PLANNER_SYSTEM_PROMPT),
        "response_schema_sha256": _schema_sha256(),
        "source_summary_sha256": _source_summary_sha256(),
        "production_source_hashes": _production_source_hashes(),
        "execution_controls": dict(FROZEN_EXECUTION_CONTROLS),
    }


def _shape_json(shape: ProviderSchemaValidationShape | None) -> dict[str, object] | None:
    """Serialize one typed shape without exposing non-JSON objects."""
    return None if shape is None else shape.to_json()


def _call_kind(request: StructuredGenerationRequest, calls: list[dict[str, object]]) -> str:
    """Classify one planner request using the frozen production prompts."""
    if not calls:
        return "INITIAL"
    if "Schema correction context:" in request.user_prompt:
        return "SCHEMA_CORRECTION"
    if "Correction context:" in request.user_prompt:
        return "SEMANTIC_CORRECTION"
    return "INVALID_RESPONSE_RETRY"


class RecordingBackend(ModelBackendProtocol):
    """Record bounded planner diagnostics and reject worker calls."""

    def __init__(self, delegate: ModelBackendProtocol) -> None:
        """Store one provider delegate and start an empty bounded trace."""
        self.delegate = delegate
        self.calls: list[dict[str, object]] = []
        self.program_calls = 0

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Delegate at most two structured calls and retain only safe facts."""
        if len(self.calls) >= 2:
            raise RuntimeError("CM-59A-R2C-A provider call budget exceeded.")
        call_kind = _call_kind(request, self.calls)
        record: dict[str, object] = {
            "call_index": len(self.calls),
            "call_kind": call_kind,
        }
        try:
            result = await self.delegate.generate_structured(
                request,
                response_model=response_model,
            )
        except StructuredResponseProviderError as error:
            record.update(
                {
                    "outcome": "provider_failure",
                    "provider_category": error.category.value,
                    "response_reason": error.response_reason.value,
                    "validation_shape": _shape_json(error.validation_shape),
                }
            )
            self.calls.append(record)
            raise
        except ProviderRequestError as error:
            record.update(
                {
                    "outcome": "provider_failure",
                    "provider_category": error.category.value,
                    "response_reason": None,
                    "validation_shape": None,
                }
            )
            self.calls.append(record)
            raise
        except ValidationError:
            record.update(
                {
                    "outcome": "structured_output_failure",
                    "provider_category": None,
                    "response_reason": None,
                    "validation_shape": None,
                }
            )
            self.calls.append(record)
            raise
        record.update(
            {
                "outcome": "structured_success",
                "provider_category": None,
                "response_reason": None,
                "validation_shape": None,
                "metrics": result.metrics.public_metadata(),
            }
        )
        if isinstance(result.value, SemanticPlan):
            record["plan"] = historical._plan_projection(result.value)
        self.calls.append(record)
        return result

    async def generate_program(self, request: object) -> object:
        """Reject accidental downstream worker/program execution."""
        self.program_calls += 1
        raise AssertionError(f"R2C-A must not call program generation: {request!r}")


async def run_execution(
    case: dict[str, object],
    *,
    delegate: ModelBackendProtocol,
    registry: object,
) -> dict[str, object]:
    """Run one production planner execution without safety or worker stages."""
    backend = RecordingBackend(delegate)
    planner = SemanticPlanner(backend=backend, registry=registry)  # type: ignore[arg-type]
    plan: SemanticPlan | None = None
    error_type: str | None = None
    error_code: str | None = None
    infrastructure_failure = False
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
        error_type = "ProviderRequestError"
        error_code = error.category.value
        infrastructure_failure = error.category.value in INFRASTRUCTURE_CATEGORIES
    except PlannerSemanticFailure as error:
        error_type = "PlannerSemanticFailure"
        error_code = error.code
    except ValidationError:
        error_type = "ValidationError"
        error_code = "structured_output_validation"
    return {
        "provider_calls": len(backend.calls),
        "program_calls": backend.program_calls,
        "call_trace": backend.calls,
        "initial_plan_available": bool(
            backend.calls
            and backend.calls[0].get("call_kind") == "INITIAL"
            and backend.calls[0].get("outcome") == "structured_success"
        ),
        "final_plan_available": plan is not None,
        "final_plan_projection": historical._plan_projection(plan),
        "final_error_type": error_type,
        "final_error_code": error_code,
        "provider_infrastructure_failure": infrastructure_failure,
    }


def _row(
    case: dict[str, object],
    *,
    attempt_index: int,
    result: dict[str, object],
    authorized_checkpoint: str,
    endpoint_pre_sha256: str,
) -> dict[str, object]:
    """Build one redacted evidence row."""
    return {
        **frozen_provenance(),
        "authorized_harness_checkpoint": authorized_checkpoint,
        "endpoint_pre_fingerprint_sha256": endpoint_pre_sha256,
        "case_id": case["case_id"],
        "attempt_index": attempt_index,
        "request_sha256": sha256_text(str(case["request"])),
        "planner": result,
        "program_calls": result["program_calls"],
    }


def _shape_signature(shape: object) -> tuple[object, ...] | None:
    """Convert a serialized shape into a deterministic comparable tuple."""
    if not isinstance(shape, dict):
        return None
    issues = shape.get("issues")
    if not isinstance(issues, list):
        return None
    normalized: list[tuple[str, tuple[str, ...]]] = []
    for issue in issues:
        if not isinstance(issue, dict) or not isinstance(issue.get("location"), list):
            return None
        normalized.append(
            (str(issue.get("error_type")), tuple(str(segment) for segment in issue["location"]))
        )
    return (
        int(shape.get("issue_count", -1)),
        tuple(normalized),
        bool(shape.get("truncated")),
    )


def validation_signature(row: dict[str, object]) -> tuple[tuple[object, ...], ...]:
    """Return all ordered schema-validation observations for one attempt."""
    trace = row.get("planner", {}).get("call_trace", [])
    if not isinstance(trace, list):
        return ()
    observations: list[tuple[object, ...]] = []
    for call in trace:
        if not isinstance(call, dict):
            continue
        if call.get("response_reason") == ProviderResponseFailureReason.SCHEMA_VALIDATION.value:
            observations.append(
                (call.get("call_kind"), _shape_signature(call.get("validation_shape")))
            )
    return tuple(observations)


def _shape_counts(rows: list[dict[str, object]]) -> tuple[Counter[str], Counter[str]]:
    """Count bounded issue types and locations without reading raw values."""
    types: Counter[str] = Counter()
    locations: Counter[str] = Counter()
    for row in rows:
        trace = row.get("planner", {}).get("call_trace", [])
        if not isinstance(trace, list):
            continue
        for call in trace:
            if not isinstance(call, dict) or call.get("response_reason") != "schema_validation":
                continue
            shape = call.get("validation_shape")
            if not isinstance(shape, dict) or not isinstance(shape.get("issues"), list):
                continue
            for issue in shape["issues"]:
                if isinstance(issue, dict):
                    types[str(issue.get("error_type"))] += 1
                    locations[canonical_json(issue.get("location"))] += 1
    return types, locations


def _shape_integrity_reasons(call: dict[str, object]) -> list[str]:
    """Validate one retained shape and enforce no-shape rules."""
    reason = call.get("response_reason")
    shape = call.get("validation_shape")
    if reason != ProviderResponseFailureReason.SCHEMA_VALIDATION.value:
        return ["non_schema_validation_shape"] if shape is not None else []
    if shape is None:
        return []
    if not isinstance(shape, dict):
        return ["validation_shape_malformed"]
    if set(shape) != {"issue_count", "issues", "truncated"}:
        return ["validation_shape_fields_invalid"]
    issues = shape.get("issues")
    issue_count = shape.get("issue_count")
    if not isinstance(issue_count, int) or isinstance(issue_count, bool) or issue_count < 0:
        return ["validation_issue_count_invalid"]
    if not isinstance(issues, list) or len(issues) > MAX_SCHEMA_VALIDATION_ISSUES:
        return ["validation_issue_bound_invalid"]
    truncated = shape.get("truncated")
    if not isinstance(truncated, bool):
        return ["validation_shape_count_invalid"]
    if not truncated and issue_count != len(issues):
        return ["validation_shape_count_invalid"]
    if truncated and (issue_count <= len(issues) or len(issues) != MAX_SCHEMA_VALIDATION_ISSUES):
        return ["validation_shape_count_invalid"]
    reasons: list[str] = []
    for issue in issues:
        if not isinstance(issue, dict) or set(issue) != {"error_type", "location"}:
            reasons.append("validation_issue_fields_invalid")
            continue
        error_type = issue["error_type"]
        if not isinstance(error_type, str) or (
            not ERROR_TYPE_PATTERN.fullmatch(error_type) and error_type != "<unknown_error_type>"
        ):
            reasons.append("validation_issue_type_invalid")
        location = issue["location"]
        if (
            not isinstance(location, list)
            or not location
            or len(location) > MAX_SCHEMA_VALIDATION_LOCATION_DEPTH
            or any(
                not isinstance(segment, str)
                or (
                    segment not in DECLARED_SCHEMA_FIELDS
                    and segment not in ALLOWED_LOCATION_SEGMENTS
                )
                for segment in location
            )
        ):
            reasons.append("validation_location_invalid")
        elif "<truncated>" in location and (
            location[-1] != "<truncated>" or len(location) != MAX_SCHEMA_VALIDATION_LOCATION_DEPTH
        ):
            reasons.append("validation_location_truncation_invalid")
    return sorted(set(reasons))


def _call_trace_reasons(planner: dict[str, object]) -> list[str]:
    """Validate one bounded production planner call trace."""
    trace = planner.get("call_trace")
    if not isinstance(trace, list) or len(trace) not in {1, 2}:
        return ["call_trace_invalid"]
    if planner.get("provider_calls") != len(trace):
        return ["provider_call_count_mismatch"]
    reasons: list[str] = []
    first = trace[0]
    if not isinstance(first, dict) or first.get("call_kind") != "INITIAL":
        reasons.append("initial_call_invalid")
        return reasons
    for expected_index, call in enumerate(trace):
        if not isinstance(call, dict) or call.get("call_kind") not in CALL_KINDS:
            reasons.append("call_kind_invalid")
            continue
        if call.get("call_index") != expected_index:
            reasons.append("call_index_invalid")
        response_reason = call.get("response_reason")
        if response_reason not in {None, *RESPONSE_REASONS}:
            reasons.append("response_reason_invalid")
        reasons.extend(_shape_integrity_reasons(call))
    if len(trace) == 2:
        second = trace[1]
        if not isinstance(second, dict):
            return sorted(set(reasons + ["second_call_invalid"]))
        first_reason = first.get("response_reason")
        second_kind = second.get("call_kind")
        if second_kind == "SCHEMA_CORRECTION" and not (
            first.get("outcome") == "provider_failure"
            and first.get("provider_category") == ProviderFailureCategory.INVALID_RESPONSE.value
            and first_reason == ProviderResponseFailureReason.SCHEMA_VALIDATION.value
        ):
            reasons.append("schema_correction_trigger_invalid")
        if second_kind == "INVALID_RESPONSE_RETRY":
            if first_reason == ProviderResponseFailureReason.SCHEMA_VALIDATION.value:
                reasons.append("schema_used_generic_retry")
            if not (
                first.get("outcome") == "provider_failure"
                and first.get("provider_category") == ProviderFailureCategory.INVALID_RESPONSE.value
                and first_reason != ProviderResponseFailureReason.SCHEMA_VALIDATION.value
            ):
                reasons.append("invalid_response_retry_trigger_invalid")
        if second_kind == "SEMANTIC_CORRECTION" and first.get("outcome") != "structured_success":
            reasons.append("semantic_correction_trigger_invalid")
        if second_kind not in {
            "SCHEMA_CORRECTION",
            "INVALID_RESPONSE_RETRY",
            "SEMANTIC_CORRECTION",
        }:
            reasons.append("second_call_invalid")
    elif first.get("response_reason") == ProviderResponseFailureReason.SCHEMA_VALIDATION.value:
        reasons.append("schema_correction_missing")
    return sorted(set(reasons))


def population_integrity(
    rows: list[dict[str, object]],
    *,
    expected_checkpoint: str | None = None,
    pre_fingerprint: dict[str, object] | None = None,
) -> tuple[bool, list[str]]:
    """Fail closed on population, provenance, call-path, and redaction drift."""
    reasons: set[str] = set()
    expected = set(TARGET_CASES)
    pairs = {(str(row.get("case_id")), row.get("attempt_index")) for row in rows}
    if len(rows) != 4:
        reasons.add("wrong_row_count")
    if len(pairs) != len(rows):
        reasons.add("duplicate_case_attempt")
    if {case_id for case_id, _ in pairs} != expected:
        reasons.add("case_set_mismatch")
    for case_id in expected:
        attempts = {row.get("attempt_index") for row in rows if row.get("case_id") == case_id}
        if attempts != {0, 1}:
            reasons.add("attempt_index_mismatch")
    checkpoints = {row.get("authorized_harness_checkpoint") for row in rows}
    if expected_checkpoint is not None and checkpoints != {expected_checkpoint}:
        reasons.add("checkpoint_mismatch")
    if pre_fingerprint is None:
        reasons.add("pre_fingerprint_missing")
    else:
        pre_hash = sha256_text(canonical_json(pre_fingerprint))
        if any(row.get("endpoint_pre_fingerprint_sha256") != pre_hash for row in rows):
            reasons.add("pre_fingerprint_mismatch")
    expected_cases = {str(case["case_id"]): case for case in load_target_cases()}
    expected_provenance = frozen_provenance()
    for row in rows:
        case_id = str(row.get("case_id"))
        case = expected_cases.get(case_id)
        if case is None:
            continue
        for key, value in expected_provenance.items():
            if row.get(key) != value:
                reasons.add(f"{key}_mismatch")
        if row.get("request_sha256") != sha256_text(str(case["request"])):
            reasons.add("request_hash_mismatch")
        planner = row.get("planner")
        if not isinstance(planner, dict):
            reasons.add("planner_missing")
            continue
        if int(row.get("program_calls", -1)) != 0 or int(planner.get("program_calls", -1)) != 0:
            reasons.add("worker_program_call")
        reasons.update(_call_trace_reasons(planner))
    return not reasons, sorted(reasons)


def _endpoint_status(
    pre: dict[str, object] | None,
    post: dict[str, object] | None,
) -> tuple[bool, list[str]]:
    """Require valid, equal PRE/POST endpoint identities matching the freeze."""
    if pre is None or post is None:
        return False, ["endpoint_fingerprint_missing"]
    pre_valid, pre_reasons = fingerprint.validate_endpoint_fingerprint_v2(pre)
    post_valid, post_reasons = fingerprint.validate_endpoint_fingerprint_v2(post)
    reasons = [f"pre_{reason}" for reason in pre_reasons]
    reasons.extend(f"post_{reason}" for reason in post_reasons)
    reasons.extend(
        f"endpoint_{reason}" for reason in fingerprint.compare_endpoint_fingerprints_v2(pre, post)
    )
    if pre.get("normalized_identity_sha256") != EXPECTED_ENDPOINT_IDENTITY:
        reasons.append("pre_expected_identity_mismatch")
    if post.get("normalized_identity_sha256") != EXPECTED_ENDPOINT_IDENTITY:
        reasons.append("post_expected_identity_mismatch")
    return pre_valid and post_valid and not reasons, sorted(set(reasons))


def _rows_by_case(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    """Group rows by target case without changing their evidence order."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("case_id")), []).append(row)
    return grouped


def _case_signature_status(case_rows: list[dict[str, object]]) -> str:
    """Classify one target's two bounded attempts."""
    signatures = [validation_signature(row) for row in case_rows]
    if len(signatures) != 2:
        return "UNAVAILABLE"
    if signatures[0] != signatures[1]:
        return "VARIABLE_VALIDATION_SIGNATURE"
    if signatures[0]:
        return "STABLE_VALIDATION_SIGNATURE"
    return "NO_SCHEMA_VALIDATION"


def _planner_execution_succeeded(row: dict[str, object]) -> bool:
    """Return whether one integrity-checked planner execution truly succeeded."""
    planner = row.get("planner")
    return (
        isinstance(planner, dict)
        and planner.get("final_plan_available") is True
        and planner.get("final_error_type") is None
        and planner.get("provider_infrastructure_failure") is False
    )


def _has_instrumentation_gap(rows: list[dict[str, object]]) -> tuple[int, int]:
    """Count missing and truncated schema shapes in decision-bearing calls."""
    gaps = truncated = 0
    for row in rows:
        trace = row.get("planner", {}).get("call_trace", [])
        if not isinstance(trace, list):
            continue
        for call in trace:
            if not isinstance(call, dict) or call.get("response_reason") != "schema_validation":
                continue
            shape = call.get("validation_shape")
            if shape is None:
                gaps += 1
            elif isinstance(shape, dict) and shape.get("truncated") is True:
                truncated += 1
    return gaps, truncated


def decision(
    rows: list[dict[str, object]],
    *,
    expected_checkpoint: str | None = None,
    pre_fingerprint: dict[str, object] | None = None,
    post_fingerprint: dict[str, object] | None = None,
) -> str:
    """Apply the frozen R2C-A decision precedence."""
    population_ok, _ = population_integrity(
        rows,
        expected_checkpoint=expected_checkpoint,
        pre_fingerprint=pre_fingerprint,
    )
    endpoint_ok, _ = _endpoint_status(pre_fingerprint, post_fingerprint)
    if not population_ok or not endpoint_ok:
        return "INCONCLUSIVE_DIAGNOSTIC"
    if any(row.get("planner", {}).get("provider_infrastructure_failure") for row in rows):
        return "INCONCLUSIVE_DIAGNOSTIC"
    gaps, truncated = _has_instrumentation_gap(rows)
    if gaps or truncated:
        return "DIAGNOSTIC_INSTRUMENTATION_GAP"
    signatures = [validation_signature(row) for row in rows]
    if not any(signatures):
        if all(_planner_execution_succeeded(row) for row in rows):
            return "FAILURES_NOT_REPRODUCED"
        return "MIXED_DIAGNOSTIC_OUTCOME"
    grouped = _rows_by_case(rows)
    statuses = [_case_signature_status(grouped.get(case_id, [])) for case_id in TARGET_CASES]
    if "VARIABLE_VALIDATION_SIGNATURE" in statuses:
        return "VARIABLE_VALIDATION_SIGNATURE"
    if statuses == ["STABLE_VALIDATION_SIGNATURE", "STABLE_VALIDATION_SIGNATURE"]:
        first = validation_signature(grouped[TARGET_CASES[0]][0])
        second = validation_signature(grouped[TARGET_CASES[1]][0])
        if first == second:
            return "STABLE_SHARED_VALIDATION_SIGNATURE"
        return "STABLE_DISTINCT_VALIDATION_SIGNATURES"
    if statuses == ["NO_SCHEMA_VALIDATION", "NO_SCHEMA_VALIDATION"]:
        if all(_planner_execution_succeeded(row) for row in rows):
            return "FAILURES_NOT_REPRODUCED"
        return "MIXED_DIAGNOSTIC_OUTCOME"
    return "MIXED_DIAGNOSTIC_OUTCOME"


def _signature_json(signature: tuple[tuple[object, ...], ...]) -> list[dict[str, object]]:
    """Serialize a validation signature without Python tuple syntax."""
    return [
        {
            "call_kind": observation[0],
            "shape": {
                "issue_count": observation[1][0],
                "issues": [
                    {"error_type": item[0], "location": list(item[1])} for item in observation[1][1]
                ],
                "truncated": observation[1][2],
            },
        }
        for observation in signature
        if observation[1] is not None
    ]


def _summary_shapes(
    grouped: dict[str, list[dict[str, object]]],
    case_id: str,
    call_kind: str,
) -> list[object]:
    """Return shape projections only after population integrity has passed."""
    return [
        call["validation_shape"]
        for row in grouped.get(case_id, [])
        for call in row.get("planner", {}).get("call_trace", [])
        if isinstance(call, dict)
        and call.get("call_kind") == call_kind
        and call.get("response_reason") == ProviderResponseFailureReason.SCHEMA_VALIDATION.value
    ]


def summarize_population(
    rows: list[dict[str, object]],
    *,
    authorized_checkpoint: str | None = None,
    pre_fingerprint: dict[str, object] | None = None,
    post_fingerprint: dict[str, object] | None = None,
    raw_evidence_sha256: str | None = None,
    pre_fingerprint_file_sha256: str | None = None,
    post_fingerprint_file_sha256: str | None = None,
) -> dict[str, object]:
    """Build the bounded provider-free diagnostic summary."""
    population_ok, population_reasons = population_integrity(
        rows,
        expected_checkpoint=authorized_checkpoint,
        pre_fingerprint=pre_fingerprint,
    )
    endpoint_ok, endpoint_reasons = _endpoint_status(pre_fingerprint, post_fingerprint)
    grouped = _rows_by_case(rows)
    if population_ok:
        case_statuses = {
            case_id: _case_signature_status(grouped.get(case_id, [])) for case_id in TARGET_CASES
        }
        gaps, truncated = _has_instrumentation_gap(rows)
        type_counts, location_counts = _shape_counts(rows)
        signatures = {
            case_id: [
                _signature_json(validation_signature(row)) for row in grouped.get(case_id, [])
            ]
            for case_id in TARGET_CASES
        }
        stable_signatures = {
            case_id: signatures[case_id][0]
            if len(signatures[case_id]) == 2 and signatures[case_id][0] == signatures[case_id][1]
            else None
            for case_id in TARGET_CASES
        }
        shared_relation = None
        if all(stable_signatures[case_id] is not None for case_id in TARGET_CASES):
            shared_relation = (
                "shared"
                if stable_signatures[TARGET_CASES[0]] == stable_signatures[TARGET_CASES[1]]
                else "distinct"
            )
        shape_outputs = {
            "Kestrel_initial_validation_shapes": _summary_shapes(
                grouped, TARGET_CASES[0], "INITIAL"
            ),
            "Kestrel_correction_validation_shapes": _summary_shapes(
                grouped, TARGET_CASES[0], "SCHEMA_CORRECTION"
            ),
            "Xenon_initial_validation_shapes": _summary_shapes(grouped, TARGET_CASES[1], "INITIAL"),
            "Xenon_correction_validation_shapes": _summary_shapes(
                grouped, TARGET_CASES[1], "SCHEMA_CORRECTION"
            ),
        }
    else:
        case_statuses = dict.fromkeys(TARGET_CASES, "UNAVAILABLE")
        gaps = truncated = 0
        type_counts = Counter()
        location_counts = Counter()
        signatures = {case_id: [] for case_id in TARGET_CASES}
        stable_signatures = dict.fromkeys(TARGET_CASES)
        shared_relation = None
        shape_outputs = {
            "Kestrel_initial_validation_shapes": [],
            "Kestrel_correction_validation_shapes": [],
            "Xenon_initial_validation_shapes": [],
            "Xenon_correction_validation_shapes": [],
        }
    final_decision = decision(
        rows,
        expected_checkpoint=authorized_checkpoint,
        pre_fingerprint=pre_fingerprint,
        post_fingerprint=post_fingerprint,
    )
    provider_calls = sum(int(row.get("planner", {}).get("provider_calls", 0)) for row in rows)
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "diagnostic_contract_version": DIAGNOSTIC_CONTRACT_VERSION,
        "behavior_baseline_sha": BASELINE_SHA,
        "authorized_harness_checkpoint": authorized_checkpoint,
        "population_rows": len(rows),
        "planner_executions": len(rows),
        "provider_calls": provider_calls,
        "worker_program_calls": sum(int(row.get("program_calls", 0)) for row in rows),
        "population_integrity": population_ok,
        "population_integrity_reasons": population_reasons,
        "endpoint_integrity": endpoint_ok,
        "endpoint_integrity_reasons": endpoint_reasons,
        "case_statuses": case_statuses,
        **shape_outputs,
        "validation_signatures": signatures,
        "stable_validation_signatures": stable_signatures,
        "shared_signature_relation": shared_relation,
        "validation_issue_type_counts": dict(sorted(type_counts.items())),
        "validation_location_counts": dict(sorted(location_counts.items())),
        "diagnostic_gap_count": gaps,
        "truncated_shape_count": truncated,
        "raw_evidence_sha256": raw_evidence_sha256,
        "pre_fingerprint_file_sha256": pre_fingerprint_file_sha256,
        "post_fingerprint_file_sha256": post_fingerprint_file_sha256,
        "decision": final_decision,
    }


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    """Read bounded JSONL evidence without contacting a provider."""
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("Evidence row is not a JSON object.")
        rows.append(value)
    return rows


def _api_key(args: argparse.Namespace) -> str:
    """Resolve a provider key without retaining it in evidence."""
    value = os.getenv(args.api_key_env, "").strip()
    if args.api_key_file:
        path = Path(args.api_key_file)
        if not path.is_absolute():
            path = REPO_ROOT / path
        value = value or path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError("No R2C-A API key configured.")
    return value


def _provider_configuration(args: argparse.Namespace) -> ModelBackendProtocol:
    """Construct the provider only after all live guards pass."""
    from openai import AsyncOpenAI  # noqa: I001
    from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2  # noqa: I001

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


def verify_reviewed_checkout(checkpoint: str) -> None:
    """Require the exact diagnostic checkpoint before live execution."""
    if CHECKPOINT_RE.fullmatch(checkpoint) is None or current_checkout_sha() != checkpoint:
        raise RuntimeError("R2C-A checkout does not match the authorized checkpoint.")
    guarded = (
        "scripts/cm59a_r2c_a_schema_validation_shape_diagnostic.py",
        "tests/test_cm59a_r2c_a_schema_validation_shape_diagnostic.py",
        "docs/evaluations/agent-code-mode/CM-59A-R2C-A-development-memory.md",
        *PROTECTED_ARTIFACTS,
        *sorted(INSTRUMENTED_ARTIFACTS),
    )
    for relative_path in guarded:
        path = REPO_ROOT / relative_path
        if not path.exists() or path.read_bytes() != _git_output(
            "show", f"{checkpoint}:{relative_path}"
        ):
            raise RuntimeError(f"R2C-A guarded artifact drifted: {relative_path}")


def _ensure_empty(path: Path) -> None:
    """Reject append/resume behavior before endpoint access."""
    if path.exists() and path.stat().st_size:
        raise RuntimeError(f"R2C-A artifact path is non-empty: {path}")


def _endpoint_is_expected(value: dict[str, object]) -> bool:
    """Validate one PRE/POST endpoint fingerprint against the freeze."""
    valid, reasons = fingerprint.validate_endpoint_fingerprint_v2(value)
    return (
        valid
        and not reasons
        and value.get("normalized_identity_sha256") == EXPECTED_ENDPOINT_IDENTITY
    )


async def _run_live(args: argparse.Namespace, checkpoint: str) -> None:
    """Run the exact four-row sequential planner-only diagnostic."""
    verify_reviewed_checkout(checkpoint)
    verify_frozen_contract()
    output = Path(args.evidence_path)
    pre_path = Path(args.endpoint_fingerprint_pre)
    post_path = Path(args.endpoint_fingerprint_post)
    summary_path = Path(args.summary_path)
    for path in (output, pre_path, post_path, summary_path):
        _ensure_empty(path)
    pre = fingerprint.capture_endpoint_fingerprint_v2(
        endpoint=args.base_url,
        model_api_label=FROZEN_MODEL,
    )
    if not _endpoint_is_expected(pre):
        raise RuntimeError("R2C-A PRE endpoint identity is not authorized.")
    pre_path.write_text(canonical_json(pre) + "\n", encoding="utf-8")
    pre_sha = sha256_text(canonical_json(pre))
    provider = _provider_configuration(args)
    registry = create_builtin_registry()
    cases = load_target_cases()
    with output.open("w", encoding="utf-8") as evidence:
        for case in cases:
            for attempt_index in range(ATTEMPTS):
                result = await run_execution(case, delegate=provider, registry=registry)
                evidence.write(
                    canonical_json(
                        _row(
                            case,
                            attempt_index=attempt_index,
                            result=result,
                            authorized_checkpoint=checkpoint,
                            endpoint_pre_sha256=pre_sha,
                        )
                    )
                    + "\n"
                )
                evidence.flush()
    post = fingerprint.capture_endpoint_fingerprint_v2(
        endpoint=args.base_url,
        model_api_label=FROZEN_MODEL,
    )
    post_path.write_text(canonical_json(post) + "\n", encoding="utf-8")


def _finalize(args: argparse.Namespace, checkpoint: str) -> dict[str, object]:
    """Finalize local evidence without endpoint or provider access."""
    verify_reviewed_checkout(checkpoint)
    verify_frozen_contract()
    evidence_path = Path(args.evidence_path)
    pre_path = Path(args.endpoint_fingerprint_pre)
    post_path = Path(args.endpoint_fingerprint_post)
    rows = _read_jsonl(evidence_path)
    pre = json.loads(pre_path.read_text(encoding="utf-8"))
    post = json.loads(post_path.read_text(encoding="utf-8"))
    raw_hash = artifact_sha256(evidence_path)
    summary = summarize_population(
        rows,
        authorized_checkpoint=checkpoint,
        pre_fingerprint=pre,
        post_fingerprint=post,
        raw_evidence_sha256=raw_hash,
        pre_fingerprint_file_sha256=artifact_sha256(pre_path),
        post_fingerprint_file_sha256=artifact_sha256(post_path),
    )
    Path(args.summary_path).write_text(canonical_json(summary) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def prelive_report() -> dict[str, object]:
    """Return the provider-free implementation audit."""
    contract = verify_frozen_contract()
    return {
        "status": "PRELIVE_READY",
        "experiment_version": EXPERIMENT_VERSION,
        "diagnostic_contract_version": DIAGNOSTIC_CONTRACT_VERSION,
        "behavior_baseline_sha": BASELINE_SHA,
        "current_checkout_sha": current_checkout_sha(),
        "live_inference": "NOT_AUTHORIZED",
        "provider_calls": 0,
        "endpoint_calls": 0,
        "worker_program_calls": 0,
        "production_source_changes": 0,
        "future_population": {
            "cases": 2,
            "attempts": 2,
            "planner_executions": 4,
            "provider_calls_min": 4,
            "provider_calls_max": 8,
        },
        "expected_normalized_endpoint_identity": EXPECTED_ENDPOINT_IDENTITY,
        **contract,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the provider-free/live guarded command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-authorized", action="store_true")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--authorized-checkpoint", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--evidence-path", default=str(OUTPUT_PATH))
    parser.add_argument("--endpoint-fingerprint-pre", default=str(ENDPOINT_PRE_PATH))
    parser.add_argument("--endpoint-fingerprint-post", default=str(ENDPOINT_POST_PATH))
    parser.add_argument("--summary-path", default=str(SUMMARY_PATH))
    parser.add_argument("--api-key-env", default="LLAMA_CPP_API_KEY")
    parser.add_argument("--api-key-file", default="LLAMA_CPP_API_KEY.txt")
    return parser


def main() -> None:
    """Run provider-free pre-live validation, live execution, or finalization."""
    args = build_parser().parse_args()
    if args.finalize:
        if not args.authorized_checkpoint:
            raise SystemExit("--finalize requires --authorized-checkpoint.")
        _finalize(args, args.authorized_checkpoint)
        return
    if args.live_authorized:
        if not args.authorized_checkpoint or not args.base_url:
            raise SystemExit("--live-authorized requires checkpoint and base URL.")
        asyncio.run(_run_live(args, args.authorized_checkpoint))
        return
    print(json.dumps(prelive_report(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
