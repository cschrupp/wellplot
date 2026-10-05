"""Execute the frozen SI-V2R SR7 A/B comparison after explicit authorization.

The default path is provider-free.  Network access is available only with
``--execute-live`` and an exact authorized checkout.  The runner stages every
completed logical attempt before producing the canonical evidence population.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, NoReturn

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError

from scripts.semantic_ir_v2r_sr7_p0_comparison_contract import (
    classify_future_comparison,
    derive_comparison,
    grade_semantics,
    system_dimension_outcomes,
    validate_evidence_rows,
    validate_runtime_attestation,
)
from scripts.si_v2r_model_qualification import (
    STRUCTURAL_RETRY_PROMPT,
    V2R_SYSTEM_PROMPT,
    run_execution,
)
from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.agent.providers.response_diagnostics import (
    ProviderResponseFailureReason,
    StructuredResponseProviderError,
)

P0_SHA = "8f30a33c9bcf5fbbce179996a6ea6b0f9a9da78f"
EXPERIMENT_VERSION = "SI-V2R-SR7-P1"
P0_DIR = Path("tests/fixtures/semantic_ir_v2r_sr7_p0")
P0_SCRIPT = Path("scripts/semantic_ir_v2r_sr7_p0_comparison_contract.py")
CORPUS_PATH = Path("tests/fixtures/typed_worker/cm59a_system_reevaluation_cases.json")
GOLD_PATH = Path("tests/fixtures/semantic_ir_v2r/cm59a_semantic_intents_v2r.json")
SCHEMA_PATH = Path("src/wellplot/agent/code_mode/semantic_ir_v2r.py")
DEFAULT_OUTPUT = Path("/tmp/si-v2r-sr7-p1-live.jsonl")
DEFAULT_JOURNAL = Path("/tmp/si-v2r-sr7-p1-live.journal.jsonl")
DEFAULT_TERMINAL = Path("/tmp/si-v2r-sr7-p1-live.terminal.json")
DEFAULT_SUMMARY = Path("/tmp/si-v2r-sr7-p1-live-summary.json")
MAX_INFRASTRUCTURE_RETRIES = 1
MAX_STRUCTURAL_RETRIES = 1
MAX_PHYSICAL_CALLS = 3
SECRET_MARKERS = ("authorization", "bearer", "api_key", "nvapi-", "openrouter_api_key")
INFRASTRUCTURE_CATEGORIES = {
    ProviderFailureCategory.CONFIGURATION.value,
    ProviderFailureCategory.AUTHENTICATION.value,
    ProviderFailureCategory.TIMEOUT.value,
    ProviderFailureCategory.RATE_LIMIT.value,
    ProviderFailureCategory.TRANSPORT.value,
}
TRANSIENT_CATEGORIES = {
    ProviderFailureCategory.TIMEOUT.value,
    ProviderFailureCategory.RATE_LIMIT.value,
    ProviderFailureCategory.TRANSPORT.value,
}

FROZEN_HASHES = {
    "configurations.json": "31cc00912d9b77ec4a9d1d42645d6c189d593cffb1bd83dcc7228f54d59bff7e",
    "runtime_attestation_contract.json": (
        "c955d53ec80a8c20e476ab8e941aa716da266b68a5b14023f2c132c539181d96"
    ),
    "case_dimension_mask.json": "b17cd676baea56547c25dfd91c22957601346f4963ee0284302f35538e2314f7",
    "comparison_contract.json": "6a8d0d5b73e10a2299c504c61428526119bcf70c114440b73a2e07f73a033349",
    "execution_schedule.json": "17781e18a482848b6be9bd1bf960534a4cffeec2537883a5427723871861d665",
    "evidence_schema.json": "912a90c1363c28dac6319e075dfd1a54e3bb2ff237468626663c21af3fd5e587",
    "semantic_dimension_contract.json": (
        "aa0e62f2af2751fa0f3e2f4d8785a4410c0302fa379f1e245bed9550a5e2d9a9"
    ),
}
V2R_SCHEMA_SHA256 = "d84cdef165ba6d060addd3ed73b018a1f10a3e70ef4a674b5d1a06352c0d58d8"
SYSTEM_PROMPT_SHA256 = "5ebdd3da9bc3cdf78442a97ba0a2ef9fc1c0d5e8b1ca641f18a30fe1b0cb50e3"
RETRY_PROMPT_SHA256 = "27c6a43c7f611a79401914b6732dbcec946493bba51058c1eb1d1245f47990f0"
GOLD_SHA256 = "eb4803c1b0265f72e2b7f3f97176afe585698473f108d60768e792e4ecfca0a5"
CORPUS_SHA256 = "b6a605158e667e5250df99a53cb4ba521473f8146fad2022aed2dff77d5f551b"
SEMANTIC_GRADER_SHA256 = "b8bdad56daa189d2e990d4e03de5976685345954d515876e719992e727c9c7ef"
CONFIGURATION_FINGERPRINTS = {
    "A": "154513f15bba419aae7ce87c8a0e26a601f45829281e385c599d597fc810711a",
    "B": "a473cc25db1415373b81d7775c263170d7c6388fa45caa5572b11308e8b7d980",
}


class PreflightError(RuntimeError):
    """Raised when the live interlock must prevent provider construction."""


class StudyAbort(RuntimeError):
    """Raised for a terminal, evidence-bearing study stop."""

    def __init__(self, decision: str, reason: str) -> None:
        """Store a terminal decision without retaining provider content."""
        super().__init__(reason)
        self.decision = decision
        self.reason = reason


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: object) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PreflightError(f"expected JSON object: {path}")
    return value


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True).strip()


def _artifact_hash(repo_root: Path, relative: Path) -> str:
    return _sha256_bytes((repo_root / relative).read_bytes())


def _p0_artifact_hash(repo_root: Path, name: str) -> str:
    return _sha256_json(_load_json(repo_root / P0_DIR / name))


def _assert_empty(path: Path) -> None:
    if path.exists() and path.stat().st_size:
        raise PreflightError(f"live artifact is non-empty: {path}")


def _configuration_contract(repo_root: Path) -> dict[str, dict[str, Any]]:
    payload = _load_json(repo_root / P0_DIR / "configurations.json")
    return {item["configuration_id"]: item for item in payload["configurations"]}


def _expected_runtime(configuration: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "configuration_id": configuration["configuration_id"],
        "base_url": configuration["base_url"],
        "requested_model": configuration["requested_model"],
        "returned_model": configuration["requested_model"],
        "temperature": configuration["temperature"],
        "max_tokens": configuration["max_tokens"],
        "timeout_seconds": configuration["timeout_seconds"],
        "structured_output_type": "json_schema",
        "strict": configuration["strict"],
        "schema_sha256": V2R_SCHEMA_SHA256,
        "system_prompt_sha256": SYSTEM_PROMPT_SHA256,
        "retry_prompt_sha256": RETRY_PROMPT_SHA256,
        "case_corpus_sha256": CORPUS_SHA256,
        "comparison_concurrency": 1,
    }
    if configuration["configuration_id"] == "B":
        expected.update(
            {
                "top_p": configuration["top_p"],
                "reasoning_effort": configuration["reasoning_effort"],
            }
        )
    return expected


def verify_preflight(
    repo_root: Path,
    *,
    authorized_checkpoint: str | None,
    output_path: Path,
    journal_path: Path,
    terminal_path: Path,
    require_exact_checkpoint: bool,
    require_clean: bool = True,
) -> dict[str, Any]:
    """Verify all P0 hashes and live interlocks without constructing a provider."""
    head = _git(repo_root, "rev-parse", "HEAD")
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", P0_SHA, "HEAD"],
        cwd=repo_root,
        check=False,
    ).returncode:
        raise PreflightError("checkout does not descend from accepted P0")
    if require_exact_checkpoint and head != authorized_checkpoint:
        raise PreflightError("checkout does not match the authorized P1 checkpoint")
    if require_clean and _git(repo_root, "status", "--porcelain"):
        raise PreflightError("working tree is not clean")
    if authorized_checkpoint and len(authorized_checkpoint) != 40:
        raise PreflightError("authorized checkpoint must be a full SHA")
    for path in (output_path, journal_path, terminal_path):
        _assert_empty(path)

    for name, expected in FROZEN_HASHES.items():
        actual = _p0_artifact_hash(repo_root, name)
        if actual != expected:
            raise PreflightError(f"frozen P0 artifact drift: {name}")
    schema_hash = _sha256_json(SemanticIRV2R.model_json_schema())
    if schema_hash != V2R_SCHEMA_SHA256:
        raise PreflightError("V2R schema drift")
    from scripts.si_v2r_model_qualification import STRUCTURAL_RETRY_PROMPT, V2R_SYSTEM_PROMPT

    if _sha256_bytes(V2R_SYSTEM_PROMPT.encode("utf-8")) != SYSTEM_PROMPT_SHA256:
        raise PreflightError("V2R system prompt drift")
    if _sha256_bytes(STRUCTURAL_RETRY_PROMPT.encode("utf-8")) != RETRY_PROMPT_SHA256:
        raise PreflightError("structural retry prompt drift")
    if _artifact_hash(repo_root, CORPUS_PATH) != CORPUS_SHA256:
        raise PreflightError("request corpus drift")
    if _artifact_hash(repo_root, GOLD_PATH) != GOLD_SHA256:
        raise PreflightError("gold drift")
    if _artifact_hash(repo_root, P0_SCRIPT) != SEMANTIC_GRADER_SHA256:
        raise PreflightError("semantic grader source drift")
    configurations = _configuration_contract(repo_root)
    for configuration_id, expected_fingerprint in CONFIGURATION_FINGERPRINTS.items():
        if configurations[configuration_id]["fingerprint"] != expected_fingerprint:
            raise PreflightError(f"configuration fingerprint drift: {configuration_id}")
    return {
        "accepted_p0_sha": P0_SHA,
        "current_checkout_sha": head,
        "configuration_contract_sha256": FROZEN_HASHES["configurations.json"],
        "runtime_attestation_contract_sha256": FROZEN_HASHES["runtime_attestation_contract.json"],
        "case_dimension_mask_sha256": FROZEN_HASHES["case_dimension_mask.json"],
        "comparison_contract_sha256": FROZEN_HASHES["comparison_contract.json"],
        "execution_schedule_sha256": FROZEN_HASHES["execution_schedule.json"],
        "evidence_schema_sha256": FROZEN_HASHES["evidence_schema.json"],
        "semantic_dimension_contract_sha256": FROZEN_HASHES["semantic_dimension_contract.json"],
        "semantic_grader_sha256": SEMANTIC_GRADER_SHA256,
        "v2r_schema_sha256": V2R_SCHEMA_SHA256,
        "system_prompt_sha256": SYSTEM_PROMPT_SHA256,
        "retry_prompt_sha256": RETRY_PROMPT_SHA256,
        "gold_sha256": GOLD_SHA256,
        "corpus_sha256": CORPUS_SHA256,
        "configuration_fingerprints": dict(CONFIGURATION_FINGERPRINTS),
    }


def _load_cases(repo_root: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    corpus = _load_json(repo_root / CORPUS_PATH)["cases"]
    gold = _load_json(repo_root / GOLD_PATH)["cases"]
    if len(corpus) != 24 or len(gold) != 24:
        raise PreflightError("P1 requires the frozen 24-case corpus")
    return corpus, {case["case_id"]: case for case in gold}


def _load_p0_contracts(repo_root: Path) -> dict[str, Any]:
    return {
        "mask": _load_json(repo_root / P0_DIR / "case_dimension_mask.json"),
        "schedule": _load_json(repo_root / P0_DIR / "execution_schedule.json"),
        "comparison": _load_json(repo_root / P0_DIR / "comparison_contract.json"),
        "evidence": _load_json(repo_root / P0_DIR / "evidence_schema.json"),
    }


def _request_payload(request: str) -> str:
    return _canonical_json(
        {"request": request, "mode": "reconstruct", "current_document_summary": {}}
    )


@dataclass(frozen=True, slots=True)
class _CallObservation:
    phase: str
    outcome: str
    value: SemanticIRV2R | None
    reason: str | None
    category: str | None
    metadata: dict[str, Any]


def _safe_provider_failure(error: ProviderRequestError) -> _CallObservation:
    return _CallObservation(
        phase="",
        outcome="provider_failure",
        value=None,
        reason=error.category.value,
        category=error.category.value,
        metadata={"status_code": error.status_code},
    )


def _backend_metadata(backend: ModelBackendProtocol) -> dict[str, Any]:
    """Copy bounded transport metadata even when provider validation fails."""
    metadata = getattr(backend, "last_metadata", {})
    return dict(metadata) if isinstance(metadata, dict) else {}


def _parse_and_validate_content(
    content: str,
    response_model: type[SemanticIRV2R],
    metadata: dict[str, Any],
) -> SemanticIRV2R:
    """Apply JSON parsing, JSON Schema, and canonical validation in order."""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        metadata.update(
            {
                "valid_json": False,
                "json_schema_status": None,
                "pydantic_status": None,
            }
        )
        raise StructuredResponseProviderError(
            "provider returned invalid structured JSON",
            response_reason=ProviderResponseFailureReason.INVALID_JSON,
        ) from None

    try:
        Draft202012Validator(response_model.model_json_schema()).validate(parsed)
    except JsonSchemaValidationError:
        metadata.update(
            {
                "valid_json": True,
                "json_schema_status": "FAIL",
                "pydantic_status": None,
            }
        )
        raise StructuredResponseProviderError(
            "provider returned JSON that does not satisfy the response schema",
            response_reason=ProviderResponseFailureReason.SCHEMA_VALIDATION,
        ) from None

    metadata.update({"valid_json": True, "json_schema_status": "PASS"})
    try:
        value = response_model.model_validate(parsed)
    except ValidationError:
        metadata["pydantic_status"] = "FAIL"
        raise StructuredResponseProviderError(
            "provider returned JSON that failed canonical validation",
            response_reason=ProviderResponseFailureReason.SCHEMA_VALIDATION,
        ) from None
    metadata["pydantic_status"] = "PASS"
    return value


async def _call_backend(
    backend: ModelBackendProtocol,
    request: StructuredGenerationRequest,
    *,
    phase: str,
) -> _CallObservation:
    try:
        result = await backend.generate_structured(request, response_model=SemanticIRV2R)
    except StructuredResponseProviderError as error:
        metadata = _backend_metadata(backend)
        metadata.update(error.diagnostic_metadata())
        return _CallObservation(
            phase=phase,
            outcome="structured_failure",
            value=None,
            reason=str(metadata.get("response_reason") or "structured_failure"),
            category=ProviderFailureCategory.INVALID_RESPONSE.value,
            metadata=metadata,
        )
    except ProviderRequestError as error:
        observed = _safe_provider_failure(error)
        return _CallObservation(
            phase=phase,
            outcome=observed.outcome,
            value=None,
            reason=observed.reason,
            category=observed.category,
            metadata=observed.metadata,
        )
    except ValidationError:
        metadata = _backend_metadata(backend)
        metadata.update(
            {
                "valid_json": True,
                "json_schema_status": "PASS",
                "pydantic_status": "FAIL",
            }
        )
        return _CallObservation(
            phase=phase,
            outcome="structured_failure",
            value=None,
            reason="schema_validation",
            category=ProviderFailureCategory.INVALID_RESPONSE.value,
            metadata=metadata,
        )
    metadata = _backend_metadata(backend)
    metadata.update({"valid_json": True, "json_schema_status": "PASS", "pydantic_status": "PASS"})
    return _CallObservation(
        phase=phase,
        outcome="structured_success",
        value=result.value,
        reason=None,
        category=None,
        metadata=dict(metadata) if isinstance(metadata, dict) else {},
    )


def _call_projection(call: _CallObservation | None) -> dict[str, Any]:
    if call is None:
        return {
            "transport_status": None,
            "finish_reason": None,
            "valid_json": None,
            "json_schema_status": None,
            "pydantic_status": None,
            "usage": None,
            "latency_ms": None,
        }
    success = call.outcome == "structured_success"
    structured_failure = call.outcome == "structured_failure"
    return {
        "transport_status": "PASS" if success or structured_failure else call.category,
        "finish_reason": call.metadata.get("finish_reason"),
        "valid_json": (
            call.metadata.get("valid_json") if structured_failure else True if success else None
        ),
        "json_schema_status": (
            call.metadata.get("json_schema_status")
            if structured_failure
            else "PASS"
            if success
            else None
        ),
        "pydantic_status": (
            call.metadata.get("pydantic_status")
            if structured_failure
            else "PASS"
            if success
            else None
        ),
        "usage": call.metadata.get("usage"),
        "latency_ms": call.metadata.get("latency_ms"),
    }


def _trace_record(call: _CallObservation) -> dict[str, Any]:
    return {
        "phase": call.phase,
        "outcome": call.outcome,
        "reason": call.reason,
        "category": call.category,
        "returned_model": call.metadata.get("returned_model"),
    }


async def execute_logical_attempt(
    *,
    case: dict[str, Any],
    gold: dict[str, Any],
    configuration: dict[str, Any],
    mask: dict[str, Any],
    backend: ModelBackendProtocol,
    provenance: dict[str, Any],
    execution_order_index: int,
) -> dict[str, Any]:
    """Execute one scheduled attempt with bounded infrastructure/structural retries."""
    observations: list[_CallObservation] = []
    infrastructure_retries = 0
    structural_retries = 0
    phase = "INITIAL"
    system_prompt = V2R_SYSTEM_PROMPT
    request_text = str(case["request"])
    while len(observations) < MAX_PHYSICAL_CALLS:
        request = StructuredGenerationRequest(
            system_prompt=system_prompt,
            user_prompt=_request_payload(request_text),
            timeout_seconds=float(configuration["timeout_seconds"]),
            temperature=float(configuration["temperature"]),
            max_output_tokens=int(configuration["max_tokens"]),
        )
        call = await _call_backend(backend, request, phase=phase)
        observations.append(call)
        returned_model = call.metadata.get("returned_model")
        configuration_drift = returned_model not in (None, configuration["requested_model"])
        if configuration_drift:
            break
        if call.outcome == "structured_success":
            break
        if (
            call.category in TRANSIENT_CATEGORIES
            and infrastructure_retries < MAX_INFRASTRUCTURE_RETRIES
        ):
            infrastructure_retries += 1
            continue
        if call.outcome == "structured_failure" and structural_retries < MAX_STRUCTURAL_RETRIES:
            structural_retries += 1
            phase = "STRUCTURAL_RETRY"
            system_prompt = V2R_SYSTEM_PROMPT + "\n\n" + STRUCTURAL_RETRY_PROMPT
            continue
        break

    final_call = observations[-1]
    generated = final_call.value if final_call.outcome == "structured_success" else None
    final_deterministic: dict[str, Any]
    if generated is None:
        final_deterministic = {
            "semantic_dimension_results": grade_semantics(case, gold, None, mask),
            "system_dimension_results": system_dimension_outcomes(
                mask, grade_semantics(case, gold, None, mask)
            ),
            "compiler_status": "NOT_RUN",
            "compiler_error_code": None,
            "compiler_failure_category": None,
            "safety_actions": [],
            "cm58_actions": [],
            "semantic_model": None,
            "cm58": {},
        }
    else:
        from scripts.si_v2r_model_qualification import _safe_model_dump

        class _ReplayBackend:
            last_metadata: dict[str, Any] = {}

            async def generate_structured(
                self, request: object, *, response_model: type[SemanticIRV2R]
            ) -> StructuredGenerationResult[SemanticIRV2R]:
                del request, response_model
                return StructuredGenerationResult(
                    value=generated,
                    metrics=ProviderMetrics(),
                )

            async def generate_program(self, request: object) -> NoReturn:
                raise AssertionError("program generation is not part of P1")

        deterministic = await run_execution(
            case=case,
            gold_intent=SemanticIRV2R.model_validate(
                {key: value for key, value in gold.items() if key != "case_id"}
            ),
            provider=_ReplayBackend(),
        )
        semantic_results = grade_semantics(
            case,
            gold,
            _safe_model_dump(generated),
            mask,
        )
        final_deterministic = {
            **deterministic,
            "semantic_dimension_results": semantic_results,
            "system_dimension_results": system_dimension_outcomes(mask, semantic_results),
        }

    initial = observations[0] if observations else None
    retry = observations[-1] if len(observations) > 1 else None
    runtime = {
        "configuration_id": configuration["configuration_id"],
        "base_url": configuration["base_url"],
        "requested_model": configuration["requested_model"],
        "returned_model": final_call.metadata.get("returned_model"),
        "temperature": configuration["temperature"],
        "max_tokens": configuration["max_tokens"],
        "timeout_seconds": configuration["timeout_seconds"],
        "structured_output_type": "json_schema",
        "strict": configuration["strict"],
        "schema_sha256": V2R_SCHEMA_SHA256,
        "system_prompt_sha256": SYSTEM_PROMPT_SHA256,
        "retry_prompt_sha256": RETRY_PROMPT_SHA256,
        "case_corpus_sha256": CORPUS_SHA256,
        "comparison_concurrency": 1,
    }
    if configuration["configuration_id"] == "B":
        runtime.update(
            {"top_p": configuration["top_p"], "reasoning_effort": configuration["reasoning_effort"]}
        )
    expected_runtime = _expected_runtime(configuration)
    runtime_status = validate_runtime_attestation(runtime, expected_runtime)
    configuration_drift = (
        runtime_status != "OK" and final_call.category not in INFRASTRUCTURE_CATEGORIES
    )
    row = {
        "experiment_version": EXPERIMENT_VERSION,
        "comparison_contract_sha256": provenance["comparison_contract_sha256"],
        "semantic_dimension_contract_sha256": provenance["semantic_dimension_contract_sha256"],
        "semantic_grader_sha256": provenance["semantic_grader_sha256"],
        "configuration_id": configuration["configuration_id"],
        "configuration_fingerprint": configuration["fingerprint"],
        "case_id": case["case_id"],
        "family": case["family"],
        "case_index": case["case_index"],
        "attempt_index": case["attempt_index"],
        "execution_order_index": execution_order_index,
        "request_sha256": _sha256_bytes(request_text.encode("utf-8")),
        "system_prompt_sha256": SYSTEM_PROMPT_SHA256,
        "retry_prompt_sha256": RETRY_PROMPT_SHA256,
        "schema_sha256": V2R_SCHEMA_SHA256,
        "gold_sha256": GOLD_SHA256,
        "mask_sha256": provenance["case_dimension_mask_sha256"],
        "runtime_material_attestation": runtime,
        "runtime_attestation_status": runtime_status,
        "provider_call_count": len(observations),
        "infrastructure_retry_count": infrastructure_retries,
        "structural_retry_count": structural_retries,
        "initial_transport_status": _call_projection(initial)["transport_status"],
        "initial_finish_reason": _call_projection(initial)["finish_reason"],
        "initial_valid_json": _call_projection(initial)["valid_json"],
        "initial_json_schema_status": _call_projection(initial)["json_schema_status"],
        "initial_pydantic_status": _call_projection(initial)["pydantic_status"],
        "initial_usage": _call_projection(initial)["usage"],
        "initial_latency_ms": _call_projection(initial)["latency_ms"],
        "retry_transport_status": _call_projection(retry)["transport_status"],
        "retry_finish_reason": _call_projection(retry)["finish_reason"],
        "retry_valid_json": _call_projection(retry)["valid_json"],
        "retry_json_schema_status": _call_projection(retry)["json_schema_status"],
        "retry_pydantic_status": _call_projection(retry)["pydantic_status"],
        "final_canonical_status": "PASS" if generated is not None else "FAIL",
        "model_semantics": final_deterministic["semantic_model"],
        "semantic_dimension_results": final_deterministic["semantic_dimension_results"],
        "compiler_status": final_deterministic["compiler_status"],
        "compiler_failure_category": final_deterministic["compiler_error_code"],
        "safety_actions": final_deterministic["cm58_actions"],
        "system_dimension_results": final_deterministic["system_dimension_results"],
        "terminal_row_status": "CONFIGURATION_DRIFT" if configuration_drift else "COMPLETE",
        "provider_trace": [_trace_record(observation) for observation in observations],
    }
    if final_call.category in INFRASTRUCTURE_CATEGORIES and generated is None:
        row["terminal_row_status"] = "INFRASTRUCTURE_FAILURE"
    return row


def _required_field_errors(
    rows: list[dict[str, Any]], evidence_schema: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    required = set(evidence_schema["required_fields"])

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {
                    "credentials",
                    "authorization_headers",
                    "reasoning_text",
                    "environment_dump",
                }:
                    errors.append(f"FORBIDDEN_FIELD:{key}")
                if isinstance(item, (dict, list)):
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for index, row in enumerate(rows):
        missing = sorted(required - row.keys())
        errors.extend(f"ROW_{index}_MISSING:{field}" for field in missing)
        text = json.dumps(row, sort_keys=True).lower()
        errors.extend(f"ROW_{index}_SECRET:{marker}" for marker in SECRET_MARKERS if marker in text)
        walk(row)
    return sorted(set(errors))


def _finalize_rows(
    repo_root: Path,
    rows: list[dict[str, Any]],
    provenance: dict[str, Any],
    contracts: dict[str, Any],
) -> dict[str, Any]:
    errors = _required_field_errors(rows, contracts["evidence"])
    errors.extend(
        validate_evidence_rows(
            rows,
            contracts["schedule"],
            expected_mask_sha256=provenance["case_dimension_mask_sha256"],
            expected_contract_sha256=provenance["comparison_contract_sha256"],
            expected_semantic_dimension_contract_sha256=provenance[
                "semantic_dimension_contract_sha256"
            ],
            expected_semantic_grader_sha256=provenance["semantic_grader_sha256"],
        )
    )
    if errors:
        return {
            "decision": "INCONCLUSIVE_EVIDENCE",
            "evidence_invalid": True,
            "integrity_errors": sorted(set(errors)),
            "rows": len(rows),
        }
    for row in rows:
        expected = _configuration_contract(repo_root)[row["configuration_id"]]
        if (
            validate_runtime_attestation(
                row["runtime_material_attestation"], _expected_runtime(expected)
            )
            != "OK"
        ):
            errors.append("RUNTIME_ATTESTATION")
        if row["provider_call_count"] > MAX_PHYSICAL_CALLS:
            errors.append("PHYSICAL_CALL_LIMIT")
        if row["configuration_fingerprint"] != expected["fingerprint"]:
            errors.append("CONFIGURATION_FINGERPRINT")
    if errors:
        return {
            "decision": "INCONCLUSIVE_EVIDENCE",
            "evidence_invalid": True,
            "integrity_errors": sorted(set(errors)),
            "rows": len(rows),
        }
    comparison = derive_comparison(rows, contracts["mask"])
    primary_dimensions = {
        (mask_row["case_id"], mask_row["dimension"])
        for mask_row in contracts["mask"]["rows"]
        if mask_row["model_role"] == "PRIMARY_MODEL_OBLIGATION"
    }

    def accuracy(configuration_id: str) -> float:
        statuses = [
            result["status"]
            for row in rows
            if row["configuration_id"] == configuration_id
            for dimension, result in row["semantic_dimension_results"].items()
            if (row["case_id"], dimension) in primary_dimensions
            if result["status"] in {"CORRECT", "INCORRECT"}
        ]
        return sum(status == "CORRECT" for status in statuses) / len(statuses) if statuses else 0.0

    a_case_wins = sum(
        value["relation"] == "A_BETTER" for value in comparison["case_relations"].values()
    )
    b_case_wins = sum(
        value["relation"] == "B_BETTER" for value in comparison["case_relations"].values()
    )
    summary = {
        "infrastructure_failure": False,
        "configuration_drift": False,
        "evidence_invalid": False,
        "structural_materially_contradicts": False,
        "a_case_wins": a_case_wins,
        "b_case_wins": b_case_wins,
        "a_dimension_accuracy": accuracy("A"),
        "b_dimension_accuracy": accuracy("B"),
        "a_terminal_structural_failures": sum(
            row["configuration_id"] == "A" and row["final_canonical_status"] != "PASS"
            for row in rows
        ),
        "b_terminal_structural_failures": sum(
            row["configuration_id"] == "B" and row["final_canonical_status"] != "PASS"
            for row in rows
        ),
    }
    return {
        "decision": classify_future_comparison(summary),
        "population_integrity": "PASS",
        "rows": len(rows),
        "summary": summary,
        "comparison": comparison,
        "provenance": provenance,
    }


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict) and value.get("record_type") != "terminal_run":
                rows.append(value)
    return rows


async def run_matrix(
    *,
    repo_root: Path,
    backends: dict[str, ModelBackendProtocol],
    output_path: Path,
    journal_path: Path,
    terminal_path: Path,
    require_clean: bool = True,
) -> dict[str, Any]:
    """Run a complete matrix with injected backends; network is caller-controlled."""
    contracts = _load_p0_contracts(repo_root)
    provenance = verify_preflight(
        repo_root,
        authorized_checkpoint=None,
        output_path=output_path,
        journal_path=journal_path,
        terminal_path=terminal_path,
        require_exact_checkpoint=False,
        require_clean=require_clean,
    )
    corpus, gold = _load_cases(repo_root)
    cases_by_id = {case["case_id"]: case for case in corpus}
    for item in contracts["schedule"]["rows"]:
        case = dict(cases_by_id[item["case_id"]])
        case.update(item)
        row = await execute_logical_attempt(
            case=case,
            gold=gold[item["case_id"]],
            configuration=_configuration_contract(repo_root)[item["configuration_id"]],
            mask=contracts["mask"],
            backend=backends[item["configuration_id"]],
            provenance=provenance,
            execution_order_index=item["execution_order_index"],
        )
        _append_jsonl(journal_path, row)
        if row["terminal_row_status"] in {"CONFIGURATION_DRIFT", "INFRASTRUCTURE_FAILURE"}:
            decision = (
                "INCONCLUSIVE_CONFIGURATION_DRIFT"
                if row["terminal_row_status"] == "CONFIGURATION_DRIFT"
                else "INCONCLUSIVE_INFRASTRUCTURE"
            )
            terminal = {
                "record_type": "terminal_run",
                "decision": decision,
                "completed_rows": len(_read_jsonl(journal_path)),
                "reason": row["terminal_row_status"],
            }
            terminal_path.write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n")
            return terminal
    rows = _read_jsonl(journal_path)
    finalized = _finalize_rows(repo_root, rows, provenance, contracts)
    if finalized.get("decision") == "INCONCLUSIVE_EVIDENCE":
        terminal_path.write_text(json.dumps(finalized, indent=2, sort_keys=True) + "\n")
        return finalized
    output_path.write_text(
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return finalized


class _HttpxStructuredBackend:
    """Evaluation-only frozen OpenAI-compatible transport."""

    def __init__(self, configuration: dict[str, Any], api_key: str) -> None:
        self.configuration = configuration
        self.api_key = api_key
        self.last_metadata: dict[str, Any] = {}

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[SemanticIRV2R],
    ) -> StructuredGenerationResult[SemanticIRV2R]:
        import httpx

        self.last_metadata = {}
        payload: dict[str, Any] = {
            "model": self.configuration["requested_model"],
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "SemanticIRV2R",
                    "schema": response_model.model_json_schema(),
                    "strict": True,
                },
            },
        }
        if self.configuration["top_p"] is not None:
            payload["top_p"] = self.configuration["top_p"]
        if self.configuration["reasoning_effort"] is not None:
            payload["reasoning_effort"] = self.configuration["reasoning_effort"]
        started = perf_counter()
        try:
            async with httpx.AsyncClient(timeout=request.timeout_seconds) as client:
                response = await client.post(
                    f"{self.configuration['base_url'].rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
        except httpx.TimeoutException:
            raise ProviderRequestError(
                ProviderFailureCategory.TIMEOUT, "provider timeout"
            ) from None
        except httpx.TransportError:
            raise ProviderRequestError(
                ProviderFailureCategory.TRANSPORT, "provider transport failure"
            ) from None
        latency_ms = (perf_counter() - started) * 1000
        if response.status_code >= 400:
            category = (
                ProviderFailureCategory.AUTHENTICATION
                if response.status_code in {401, 403}
                else ProviderFailureCategory.RATE_LIMIT
                if response.status_code == 429
                else ProviderFailureCategory.TIMEOUT
                if response.status_code in {408, 504}
                else ProviderFailureCategory.TRANSPORT
                if response.status_code >= 500
                else ProviderFailureCategory.PROVIDER_REJECTED
            )
            raise ProviderRequestError(
                category,
                "provider returned an HTTP error",
                status_code=response.status_code,
            )
        try:
            body = response.json()
        except ValueError:
            raise StructuredResponseProviderError(
                "provider returned invalid structured JSON",
                response_reason=ProviderResponseFailureReason.INVALID_JSON,
            ) from None
        choices = body.get("choices") if isinstance(body, dict) else None
        message = (
            choices[0].get("message")
            if isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict)
            else None
        )
        finish_reason = (
            choices[0].get("finish_reason")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict)
            else None
        )
        self.last_metadata = {
            "returned_model": body.get("model") if isinstance(body, dict) else None,
            "finish_reason": finish_reason,
            "usage": body.get("usage") if isinstance(body, dict) else None,
            "latency_ms": round(latency_ms, 3),
        }
        if not isinstance(message, dict) or message.get("role") not in {None, "assistant"}:
            raise StructuredResponseProviderError(
                "provider returned an unusable assistant message",
                response_reason=ProviderResponseFailureReason.MISSING_MESSAGE,
            )
        if finish_reason not in {None, "stop"}:
            raise StructuredResponseProviderError(
                "provider returned incomplete output",
                response_reason=ProviderResponseFailureReason.UNEXPECTED_FINISH_REASON,
            )
        content = message.get("content")
        if not isinstance(content, str):
            raise StructuredResponseProviderError(
                "provider returned no structured content",
                response_reason=ProviderResponseFailureReason.MISSING_CONTENT,
            )
        value = _parse_and_validate_content(content, response_model, self.last_metadata)
        return StructuredGenerationResult(
            value=value,
            metrics=ProviderMetrics(
                latency_ms=round(latency_ms, 3),
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
            ),
        )

    async def generate_program(self, request: object) -> NoReturn:
        raise AssertionError("program generation is not part of SI-V2R SR7 P1")


def _read_api_key(environment: str, path_value: str | None) -> str:
    value = os.getenv(environment, "").strip()
    if not value and path_value:
        value = Path(path_value).read_text(encoding="utf-8").strip()
    if not value:
        raise PreflightError(f"credential unavailable for {environment}")
    return value


async def run_live(args: argparse.Namespace, repo_root: Path) -> dict[str, Any]:
    """Run the exact authorized matrix after all non-network guards pass."""
    if not args.execute_live:
        raise PreflightError("live execution requires --execute-live")
    provenance = verify_preflight(
        repo_root,
        authorized_checkpoint=args.authorized_checkpoint,
        output_path=args.output,
        journal_path=args.journal,
        terminal_path=args.terminal,
        require_exact_checkpoint=True,
    )
    configs = _configuration_contract(repo_root)
    a_backend = _HttpxStructuredBackend(
        configs["A"], _read_api_key(args.a_api_key_env, args.a_api_key_file)
    )
    b_backend = _HttpxStructuredBackend(
        configs["B"], _read_api_key(args.b_api_key_env, args.b_api_key_file)
    )
    result = await run_matrix(
        repo_root=repo_root,
        backends={"A": a_backend, "B": b_backend},
        output_path=args.output,
        journal_path=args.journal,
        terminal_path=args.terminal,
    )
    if result.get("decision") not in {
        "INCONCLUSIVE_INFRASTRUCTURE",
        "INCONCLUSIVE_CONFIGURATION_DRIFT",
    }:
        args.summary.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    del provenance
    return result


def main() -> None:
    """Run provider-free preflight or the explicitly authorized live matrix."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--authorized-checkpoint")
    parser.add_argument("--a-api-key-env", default="LLAMA_CPP_API_KEY")
    parser.add_argument("--b-api-key-env", default="NVIDIA_API_KEY")
    parser.add_argument("--a-api-key-file")
    parser.add_argument("--b-api-key-file")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL)
    parser.add_argument("--terminal", type=Path, default=DEFAULT_TERMINAL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    repo_root = Path.cwd()
    if not args.execute_live:
        report = verify_preflight(
            repo_root,
            authorized_checkpoint=None,
            output_path=args.output,
            journal_path=args.journal,
            terminal_path=args.terminal,
            require_exact_checkpoint=False,
        )
        print(json.dumps({"status": "PRELIVE_PROVIDER_FREE", **report}, sort_keys=True))
        return
    result = asyncio.run(run_live(args, repo_root))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
