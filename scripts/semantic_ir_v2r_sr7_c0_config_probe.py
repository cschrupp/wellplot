"""Freeze SR7 serving configurations with bounded structured-output probes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import httpx

from scripts.si_v2r_model_qualification import (
    STRUCTURAL_RETRY_PROMPT,
    V2R_SYSTEM_PROMPT,
)
from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R

BASELINE_SHA = "fef690452c00dcaea6fa41df0e0af779269372ba"
DEFAULT_OUTPUT_DIR = Path("tests/fixtures/semantic_ir_v2r_sr7_c0")
A_BASE_URL = "http://192.168.2.140:8888/v1"
B_BASE_URL = "https://integrate.api.nvidia.com/v1"
A_REQUESTED_MODEL = "qwen3.6-35b-a3b"
B_REQUESTED_MODEL = "nvidia/nemotron-3-super-120b-a12b"
TEMPERATURE_A = 0.0
TEMPERATURE_B = 1.0
TOP_P_B = 0.95
MAX_OUTPUT_TOKENS = 16384
TIMEOUT_SECONDS = 900.0
PROBE_TIMEOUT_SECONDS = 900.0
GOLD_SHA256 = "eb4803c1b0265f72e2b7f3f97176afe585698473f108d60768e792e4ecfca0a5"
V2R_SCHEMA_SHA256 = "d84cdef165ba6d060addd3ed73b018a1f10a3e70ef4a674b5d1a06352c0d58d8"
SYSTEM_PROMPT_SHA256 = "5ebdd3da9bc3cdf78442a97ba0a2ef9fc1c0d5e8b1ca641f18a30fe1b0cb50e3"
RETRY_PROMPT_SHA256 = "27c6a43c7f611a79401914b6732dbcec946493bba51058c1eb1d1245f47990f0"
HISTORICAL_A_ENDPOINT_SHA256 = "23afb5ebf67063154bcf02ada6d25b2c929250b14c6a4cad06e8649d087bc980"
NVIDIA_REASONING_DOC = (
    "https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-super-120b-a12b-infer"
)
SECRET_MARKERS = (
    "Bearer",
    "NVIDIA_API_KEY",
    "OPENROUTER_API_KEY",
    "sk-",
    "nvapi-",
)


def canonical_json(value: object) -> str:
    """Serialize JSON-shaped values deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    """Hash exact UTF-8 text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    """Hash exact bytes."""
    return hashlib.sha256(value).hexdigest()


def _schema_hash() -> str:
    return sha256_text(canonical_json(SemanticIRV2R.model_json_schema()))


def _artifact_hash(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _git_output(repo_root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=repo_root, stderr=subprocess.STDOUT)


def _api_key(environment: str, key_file: str | None) -> str:
    value = os.getenv(environment, "").strip()
    if not value and key_file:
        value = Path(key_file).read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"Credential unavailable for {environment}")
    return value


def _safe_error(error: Exception) -> dict[str, object]:
    """Return an error category without retaining provider response text."""
    if isinstance(error, httpx.HTTPStatusError):
        return {
            "category": "http_error",
            "status_code": error.response.status_code,
        }
    if isinstance(error, httpx.TimeoutException):
        return {"category": "timeout"}
    if isinstance(error, httpx.TransportError):
        return {"category": "transport"}
    if isinstance(error, json.JSONDecodeError):
        return {"category": "invalid_json"}
    return {"category": type(error).__name__}


def _request_json(
    method: str,
    url: str,
    *,
    api_key: str,
    payload: dict[str, object] | None = None,
    timeout_seconds: float = 30.0,
) -> tuple[int, dict[str, object] | None, dict[str, object] | None, float]:
    """Make one bounded JSON request and discard response bodies on failure."""
    started = perf_counter()
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.request(
                method,
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            status_code = response.status_code
            response.raise_for_status()
            parsed = response.json()
            if not isinstance(parsed, dict):
                raise ValueError("response was not a JSON object")
            return status_code, parsed, None, (perf_counter() - started) * 1000
    except Exception as error:  # noqa: BLE001 - sanitized evidence boundary
        status = getattr(error, "response", None)
        status_code = status.status_code if status is not None else 0
        return status_code, None, _safe_error(error), (perf_counter() - started) * 1000


def _catalog_identity(
    base_url: str,
    *,
    api_key: str,
    requested_model: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Read one model catalog and return normalized identity plus probe evidence."""
    status, body, error, latency = _request_json(
        "GET",
        f"{base_url.rstrip('/')}/models",
        api_key=api_key,
        timeout_seconds=30.0,
    )
    if body is None:
        identity = {
            "endpoint": base_url.rstrip("/"),
            "requested_model": requested_model,
            "observed_model_identifier": "UNAVAILABLE",
            "available_model_ids": [],
            "model_catalog_sha256": "UNAVAILABLE",
        }
        return identity, {
            "operation": "GET /v1/models",
            "status_code": status,
            "latency_ms": round(latency, 3),
            "request_fingerprint_sha256": sha256_text(
                canonical_json({"method": "GET", "path": "/v1/models"})
            ),
            "normalized_identity_sha256": sha256_text(canonical_json(identity)),
            "observed_model_identifier": "UNAVAILABLE",
            "available_model_count": 0,
            "error": error,
        }
    data = body.get("data")
    model_ids = (
        sorted(
            str(item.get("id"))
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        )
        if isinstance(data, list)
        else []
    )
    observed = (
        requested_model
        if requested_model in model_ids
        else (model_ids[0] if model_ids else "UNAVAILABLE")
    )
    normalized = {
        "endpoint": base_url.rstrip("/"),
        "requested_model": requested_model,
        "observed_model_identifier": observed,
        "available_model_ids": model_ids,
        "model_catalog_sha256": (
            sha256_text(canonical_json(model_ids)) if model_ids else "UNAVAILABLE"
        ),
    }
    evidence = {
        "operation": "GET /v1/models",
        "status_code": status,
        "latency_ms": round(latency, 3),
        "request_fingerprint_sha256": sha256_text(
            canonical_json({"method": "GET", "path": "/v1/models"})
        ),
        "normalized_identity_sha256": sha256_text(canonical_json(normalized)),
        "observed_model_identifier": observed,
        "available_model_count": len(model_ids),
        "error": error,
    }
    return normalized, evidence


def _props_identity(base_url: str, *, api_key: str) -> dict[str, object]:
    """Read bounded llama.cpp metadata when the endpoint exposes it."""
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3].rstrip("/")
    status, body, error, _ = _request_json(
        "GET", f"{root}/props", api_key=api_key, timeout_seconds=30.0
    )
    if body is None:
        return {"status_code": status, "error": error, "backend": "UNRESOLVED"}
    selected = {
        key: body[key]
        for key in ("build_number", "version", "commit")
        if key in body and isinstance(body[key], (str, int, bool, type(None)))
    }
    return {"status_code": status, "backend": "llama.cpp", "props": selected}


def _schema_request(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema_name: str,
    schema: dict[str, object],
    temperature: float,
    top_p: float | None,
    reasoning_effort: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema, "strict": True},
        },
    }
    if top_p is not None:
        payload["top_p"] = top_p
    if reasoning_effort is not None:
        payload["reasoning_effort"] = reasoning_effort
    return payload


def _response_result(
    body: dict[str, object],
    *,
    model: str,
    schema_validator: Callable[[object], bool] | None,
) -> dict[str, object]:
    """Validate a successful completion without retaining response content."""
    choices = body.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        return {"api_success": True, "valid_json": False, "validation": "NO_SINGLE_CHOICE"}
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        return {"api_success": True, "valid_json": False, "validation": "NO_MESSAGE"}
    content = message.get("content")
    finish_reason = choice.get("finish_reason")
    reasoning_fields = [
        key
        for key in ("reasoning_content", "reasoning", "reasoning_tokens")
        if key in message or key in body
    ]
    result: dict[str, object] = {
        "api_success": True,
        "returned_model_identifier": body.get("model", model),
        "finish_reason": finish_reason,
        "single_assistant_choice": message.get("role") == "assistant",
        "reasoning_fields_present": reasoning_fields,
        "usage": body.get("usage") if isinstance(body.get("usage"), dict) else None,
    }
    if not isinstance(content, str):
        result.update({"valid_json": False, "validation": "MISSING_CONTENT"})
        return result
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        result.update({"valid_json": False, "validation": "INVALID_JSON"})
        return result
    result["valid_json"] = True
    if schema_validator is None:
        result["schema_validation"] = "SKIPPED"
        result["validation"] = "PASS"
        return result
    try:
        valid = schema_validator(parsed)
    except Exception:  # noqa: BLE001 - bounded validation result
        valid = False
    if not valid:
        result["schema_validation"] = "FAIL"
        result["validation"] = "SCHEMA_VALIDATION"
        return result
    result["schema_validation"] = "PASS"
    result["validation"] = "PASS"
    return result


def _validate_v2r(value: object) -> bool:
    try:
        SemanticIRV2R.model_validate(value)
    except Exception:  # noqa: BLE001 - bounded provider validation
        return False
    return True


def _validate_trivial_probe(value: object) -> bool:
    return isinstance(value, dict) and value == {"ok": True}


def _run_structured_probe(
    *,
    label: str,
    base_url: str,
    api_key: str,
    payload: dict[str, object],
    schema_validator: Callable[[object], bool] | None,
) -> dict[str, object]:
    """Run exactly one structured probe with sanitized evidence."""
    request_fingerprint = sha256_text(canonical_json(payload))
    status, body, error, latency = _request_json(
        "POST",
        f"{base_url.rstrip('/')}/chat/completions",
        api_key=api_key,
        payload=payload,
        timeout_seconds=PROBE_TIMEOUT_SECONDS,
    )
    result: dict[str, object] = {
        "label": label,
        "operation": "POST /v1/chat/completions",
        "request_fingerprint_sha256": request_fingerprint,
        "response_status_code": status,
        "latency_ms": round(latency, 3),
        "provider_attempts": 1,
        "error": error,
    }
    if body is not None:
        result.update(
            _response_result(
                body,
                model=str(payload["model"]),
                schema_validator=schema_validator,
            )
        )
        result["response_fingerprint_sha256"] = sha256_text(
            canonical_json(
                {
                    "model": body.get("model"),
                    "finish_reason": (
                        body.get("choices", [{}])[0].get("finish_reason")
                        if isinstance(body.get("choices"), list)
                        and body.get("choices")
                        and isinstance(body["choices"][0], dict)
                        else None
                    ),
                    "usage": body.get("usage"),
                }
            )
        )
    else:
        result.update({"api_success": False, "validation": "NOT_EVALUABLE"})
    return result


def _synthetic_payload() -> str:
    return canonical_json(
        {
            "request": (
                "Represent one synthetic scalar curve called probe_curve in one log-plot section."
            ),
            "mode": "reconstruct",
            "current_document_summary": {},
        }
    )


def _configuration_record(
    *,
    configuration_id: str,
    role: str,
    provider: str,
    base_url: str,
    requested_model: str,
    identity: dict[str, object],
    props: dict[str, object],
    structured_output_status: str,
    full_schema_status: str,
    reasoning_mode: str,
    reasoning_control: dict[str, object] | str,
    temperature: float,
    top_p: float | None,
    probes: list[dict[str, object]],
) -> dict[str, object]:
    backend = props.get("backend", "UNRESOLVED")
    model_artifact_sha256 = (
        "UNAVAILABLE_FROM_SERVING_INTERFACE"
        if provider == "openai_compat"
        else "UNAVAILABLE_FROM_HOSTED_PROVIDER"
    )
    record: dict[str, object] = {
        "configuration_id": configuration_id,
        "role": role,
        "provider": provider,
        "protocol": "openai_compatible_chat_completions",
        "base_url": base_url,
        "requested_model": requested_model,
        "observed_model_identifier": identity.get("observed_model_identifier", "UNAVAILABLE"),
        "model_artifact_sha256": model_artifact_sha256,
        "server_backend": backend,
        "server_metadata": props.get("props", {}),
        "server_version_build": props.get("props", {}).get("version", "UNAVAILABLE")
        if isinstance(props.get("props"), dict)
        else "UNAVAILABLE",
        "endpoint_identity": identity,
        "endpoint_identity_sha256": sha256_text(canonical_json(identity)),
        "historical_lq0_endpoint_identity_sha256": HISTORICAL_A_ENDPOINT_SHA256,
        "historical_identity_match": (
            identity.get("normalized_identity_sha256") == HISTORICAL_A_ENDPOINT_SHA256
            if configuration_id == "A"
            else None
        ),
        "chat_operation": "chat.completions.create",
        "structured_output": "response_format=json_schema",
        "strict_json_schema": True,
        "schema_converter": "UNRESOLVED",
        "parser": "WellPlot local json.loads + Pydantic model_validate",
        "temperature": temperature,
        "top_p": top_p,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "max_tokens_parameter": "max_tokens",
        "timeout_seconds": TIMEOUT_SECONDS,
        "comparison_concurrency": 1,
        "reasoning_mode": reasoning_mode,
        "reasoning_control": reasoning_control,
        "prompt_sha256": SYSTEM_PROMPT_SHA256,
        "retry_prompt_sha256": RETRY_PROMPT_SHA256,
        "v2r_schema_sha256": V2R_SCHEMA_SHA256,
        "gold_sha256": GOLD_SHA256,
        "structured_output_status": structured_output_status,
        "full_v2r_schema_status": full_schema_status,
        "probe_count": len(probes),
        "probe_result_fingerprints": [probe.get("response_fingerprint_sha256") for probe in probes],
        "artifact_identity_status": (
            "UNAVAILABLE" if "UNAVAILABLE" in model_artifact_sha256 else "OBSERVED_ONLY"
        ),
        "backend_identity_status": "OBSERVED_ONLY" if backend == "llama.cpp" else "UNRESOLVED",
        "structured_output_identity_status": (
            "FROZEN"
            if structured_output_status == "PASS"
            else "UNRESOLVED"
            if structured_output_status == "UNRESOLVED"
            else "INCOMPATIBLE"
        ),
        "decoding_parameter_status": (
            "FROZEN"
            if top_p is not None and temperature is not None
            else "REQUESTED_TEMPERATURE_ONLY_SERVER_DEFAULTS_UNRESOLVED"
        ),
        "reasoning_control_status": (
            "FROZEN" if reasoning_mode.startswith("EXPLICIT") else "UNRESOLVED"
        ),
        "probes": probes,
    }
    basis = dict(record)
    basis.pop("configuration_fingerprint_sha256", None)
    record["configuration_fingerprint_sha256"] = sha256_text(canonical_json(basis))
    return record


def _result(
    *,
    a: dict[str, object],
    b: dict[str, object],
    probe_summary: dict[str, object],
) -> dict[str, object]:
    a_frozen = a["structured_output_status"] == "PASS" and a["full_v2r_schema_status"] == "PASS"
    b_frozen = (
        b["structured_output_status"] == "PASS"
        and b["full_v2r_schema_status"] == "PASS"
        and b["reasoning_control_status"] == "FROZEN"
        and b["decoding_parameter_status"] == "FROZEN"
    )
    b_incompatible = any(
        _probe_is_schema_incompatible(probe)
        for probe in b.get("probes", [])
        if isinstance(probe, dict)
    )
    if b_incompatible:
        decision = "SI_V2R_SR7_C0_CANDIDATE_SCHEMA_INCOMPATIBLE"
    elif not a_frozen or not b_frozen:
        decision = "SI_V2R_SR7_C0_CONFIGURATION_UNRESOLVED"
    else:
        decision = "SI_V2R_SR7_C0_CONFIGURATIONS_FROZEN"
    return {
        "schema_version": "si-v2r.sr7-c0.result.v1",
        "decision": decision,
        "baseline": BASELINE_SHA,
        "configuration_a_fingerprint_sha256": a["configuration_fingerprint_sha256"],
        "configuration_b_fingerprint_sha256": b["configuration_fingerprint_sha256"],
        "a_frozen": a_frozen,
        "b_frozen": b_frozen,
        "structured_calls_a": probe_summary["structured_calls_a"],
        "structured_calls_b": probe_summary["structured_calls_b"],
        "infrastructure_retries": 0,
        "cm59a_requests_sent": 0,
        "provider_inference_used_for_model_evaluation": 0,
        "production_changes": 0,
        "prompt_changed": False,
        "schema_changed": False,
        "gold_changed": False,
        "cm58_changed": False,
        "v2r_changed": False,
        "adr_cm57": "UNCHANGED",
        "sr7_p0_authorized": False,
        "live_paired_comparison_authorized": False,
    }


def _probe_is_schema_incompatible(probe: dict[str, object]) -> bool:
    """Classify an observed candidate response failure, not transport failure."""
    if probe.get("provider_attempts") != 1:
        return False
    status = probe.get("response_status_code")
    if status in (401, 403) or status in (0, None):
        return False
    error = probe.get("error")
    if isinstance(error, dict) and error.get("category") in {
        "transport",
        "timeout",
        "http_error",
    }:
        return status in (400, 422)
    # A successful HTTP response with invalid model content does not identify
    # whether the schema converter, model, or hosted decoding path failed.
    return False


def build_preflight_artifacts(repo_root: Path) -> dict[str, object]:
    """Build deterministic repository-side C0 inputs before any endpoint call."""
    gold = repo_root / "tests/fixtures/semantic_ir_v2r/cm59a_semantic_intents_v2r.json"
    return {
        "baseline": _git_output(repo_root, "rev-parse", "HEAD").decode().strip(),
        "gold_sha256": _artifact_hash(gold),
        "v2r_schema_sha256": _schema_hash(),
        "prompt_sha256": sha256_text(V2R_SYSTEM_PROMPT),
        "retry_prompt_sha256": sha256_text(STRUCTURAL_RETRY_PROMPT),
        "gold_expected_sha256": GOLD_SHA256,
        "v2r_expected_sha256": V2R_SCHEMA_SHA256,
        "prompt_expected_sha256": SYSTEM_PROMPT_SHA256,
        "retry_prompt_expected_sha256": RETRY_PROMPT_SHA256,
    }


def _check_secrets(value: object) -> None:
    text = json.dumps(value, sort_keys=True).lower()
    for marker in SECRET_MARKERS:
        if marker.lower() in text:
            raise RuntimeError(f"secret marker persisted in C0 artifact: {marker}")


def _endpoint_identity_unavailable(base_url: str, requested_model: str) -> dict[str, object]:
    return {
        "endpoint": base_url.rstrip("/"),
        "requested_model": requested_model,
        "observed_model_identifier": "UNAVAILABLE",
        "available_model_ids": [],
        "model_catalog_sha256": "UNAVAILABLE",
    }


def _empty_probe(label: str, reason: str) -> dict[str, object]:
    return {
        "label": label,
        "operation": "POST /v1/chat/completions",
        "provider_attempts": 0,
        "validation": reason,
    }


def _identity_available(identity: dict[str, object]) -> bool:
    return identity.get("observed_model_identifier") != "UNAVAILABLE"


def _unresolved_artifacts(
    *,
    preflight: dict[str, object],
    a_identity: dict[str, object],
    b_identity: dict[str, object],
    reason: str,
) -> dict[str, object]:
    """Build a provider-free unresolved result without retaining exception text."""
    a = _configuration_record(
        configuration_id="A",
        role="CURRENT_BASELINE",
        provider="openai_compat",
        base_url=A_BASE_URL,
        requested_model=A_REQUESTED_MODEL,
        identity=a_identity,
        props={"backend": "UNRESOLVED"},
        structured_output_status="UNRESOLVED",
        full_schema_status="UNRESOLVED",
        reasoning_mode="UNRESOLVED",
        reasoning_control="UNRESOLVED",
        temperature=TEMPERATURE_A,
        top_p=None,
        probes=[],
    )
    b = _configuration_record(
        configuration_id="B",
        role="CANDIDATE",
        provider="nvidia_cloud",
        base_url=B_BASE_URL,
        requested_model=B_REQUESTED_MODEL,
        identity=b_identity,
        props={"backend": "UNRESOLVED"},
        structured_output_status="UNRESOLVED",
        full_schema_status="UNRESOLVED",
        reasoning_mode="EXPLICIT_LOW",
        reasoning_control={"parameter": "reasoning_effort", "value": "low"},
        temperature=TEMPERATURE_B,
        top_p=TOP_P_B,
        probes=[],
    )
    probe_summary = {
        "schema_version": "si-v2r.sr7-c0.probe-summary.v1",
        "repository_baseline": BASELINE_SHA,
        "preflight": preflight,
        "probes": {},
        "structured_calls_a": 0,
        "structured_calls_b": 0,
        "infrastructure_retries": 0,
        "cm59a_requests_sent": 0,
        "terminal_reason": reason,
    }
    result = _result(
        a=a,
        b=b,
        probe_summary=probe_summary,
    )
    for artifact in (a, b, probe_summary, result):
        _check_secrets(artifact)
    return {
        "configuration_a.json": a,
        "configuration_b.json": b,
        "probe_summary.json": probe_summary,
        "result.json": result,
    }


def run_live(args: argparse.Namespace, repo_root: Path) -> dict[str, object]:
    """Run the authorized A1/B1/B2 probe sequence exactly once."""
    if args.authorized_checkpoint != BASELINE_SHA:
        raise RuntimeError("C0 checkpoint authorization mismatch")
    if _git_output(repo_root, "rev-parse", "HEAD").decode().strip() != BASELINE_SHA:
        raise RuntimeError("C0 checkout does not match authorized baseline")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise RuntimeError("C0 output directory is not empty")
    preflight = build_preflight_artifacts(repo_root)
    if preflight["gold_sha256"] != GOLD_SHA256:
        raise RuntimeError("gold artifact hash mismatch")
    if preflight["v2r_schema_sha256"] != V2R_SCHEMA_SHA256:
        raise RuntimeError("V2R schema hash mismatch")
    if preflight["prompt_sha256"] != SYSTEM_PROMPT_SHA256:
        raise RuntimeError("system prompt hash mismatch")
    if preflight["retry_prompt_sha256"] != RETRY_PROMPT_SHA256:
        raise RuntimeError("retry prompt hash mismatch")
    try:
        a_key = _api_key(args.a_api_key_env, args.a_api_key_file)
        b_key = _api_key(args.b_api_key_env, args.b_api_key_file)
    except RuntimeError:
        return _unresolved_artifacts(
            preflight=preflight,
            a_identity=_endpoint_identity_unavailable(args.a_base_url, A_REQUESTED_MODEL),
            b_identity=_endpoint_identity_unavailable(args.b_base_url, B_REQUESTED_MODEL),
            reason="CREDENTIAL_UNAVAILABLE",
        )
    a_identity, a_catalog = _catalog_identity(
        args.a_base_url, api_key=a_key, requested_model=A_REQUESTED_MODEL
    )
    b_identity, b_catalog = _catalog_identity(
        args.b_base_url, api_key=b_key, requested_model=B_REQUESTED_MODEL
    )
    if not _identity_available(a_identity) or not _identity_available(b_identity):
        return _unresolved_artifacts(
            preflight=preflight,
            a_identity=a_identity,
            b_identity=b_identity,
            reason="ENDPOINT_OR_MODEL_UNAVAILABLE",
        )
    a_props = _props_identity(args.a_base_url, api_key=a_key)
    synthetic = _synthetic_payload()
    a_probe = _run_structured_probe(
        label="A1_FULL_V2R_SCHEMA",
        base_url=args.a_base_url,
        api_key=a_key,
        payload=_schema_request(
            model=A_REQUESTED_MODEL,
            system_prompt=V2R_SYSTEM_PROMPT,
            user_prompt=synthetic,
            schema_name="SemanticIRV2R",
            schema=SemanticIRV2R.model_json_schema(),
            temperature=TEMPERATURE_A,
            top_p=None,
            reasoning_effort=None,
        ),
        schema_validator=_validate_v2r,
    )
    trivial_schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }
    b1_probe = _run_structured_probe(
        label="B1_JSON_SCHEMA_TRANSPORT",
        base_url=args.b_base_url,
        api_key=b_key,
        payload=_schema_request(
            model=B_REQUESTED_MODEL,
            system_prompt="Return exactly one JSON object.",
            user_prompt="Return ok=true.",
            schema_name="C0Probe",
            schema=trivial_schema,
            temperature=TEMPERATURE_B,
            top_p=TOP_P_B,
            reasoning_effort="low",
        ),
        schema_validator=_validate_trivial_probe,
    )
    b2_probe: dict[str, object] | None = None
    if b1_probe.get("validation") == "PASS":
        b2_probe = _run_structured_probe(
            label="B2_FULL_V2R_SCHEMA",
            base_url=args.b_base_url,
            api_key=b_key,
            payload=_schema_request(
                model=B_REQUESTED_MODEL,
                system_prompt=V2R_SYSTEM_PROMPT,
                user_prompt=synthetic,
                schema_name="SemanticIRV2R",
                schema=SemanticIRV2R.model_json_schema(),
                temperature=TEMPERATURE_B,
                top_p=TOP_P_B,
                reasoning_effort="low",
            ),
            schema_validator=_validate_v2r,
        )
    b2_probe = b2_probe or {
        "label": "B2_FULL_V2R_SCHEMA",
        "validation": "NOT_RUN_B1_FAILED",
        "provider_attempts": 0,
    }

    def probe_status(probe: dict[str, object]) -> str:
        if probe.get("validation") == "PASS":
            return "PASS"
        if _probe_is_schema_incompatible(probe):
            return "INCOMPATIBLE"
        return "UNRESOLVED"

    a_status = probe_status(a_probe)
    b1_status = probe_status(b1_probe)
    b2_status = probe_status(b2_probe) if b2_probe.get("provider_attempts") else "UNRESOLVED"
    a = _configuration_record(
        configuration_id="A",
        role="CURRENT_BASELINE",
        provider="openai_compat",
        base_url=args.a_base_url,
        requested_model=A_REQUESTED_MODEL,
        identity=a_identity,
        props=a_props,
        structured_output_status=a_status,
        full_schema_status=a_status,
        reasoning_mode="UNRESOLVED",
        reasoning_control="UNRESOLVED",
        temperature=TEMPERATURE_A,
        top_p=None,
        probes=[a_probe],
    )
    b = _configuration_record(
        configuration_id="B",
        role="CANDIDATE",
        provider="nvidia_cloud",
        base_url=args.b_base_url,
        requested_model=B_REQUESTED_MODEL,
        identity=b_identity,
        props={"backend": "NVIDIA hosted OpenAI-compatible"},
        structured_output_status=b1_status,
        full_schema_status=b2_status,
        reasoning_mode="EXPLICIT_LOW",
        reasoning_control={
            "parameter": "reasoning_effort",
            "value": "low",
            "source": NVIDIA_REASONING_DOC,
        },
        temperature=TEMPERATURE_B,
        top_p=TOP_P_B,
        probes=[b1_probe, b2_probe],
    )
    probe_summary = {
        "schema_version": "si-v2r.sr7-c0.probe-summary.v1",
        "probe_timestamp_utc": datetime.now(UTC).isoformat(),
        "repository_baseline": BASELINE_SHA,
        "preflight": preflight,
        "metadata_probes": {"A": a_catalog, "B": b_catalog},
        "probes": {"A1": a_probe, "B1": b1_probe, "B2": b2_probe},
        "structured_calls_a": int(a_probe.get("provider_attempts", 0)),
        "structured_calls_b": int(b1_probe.get("provider_attempts", 0))
        + int(b2_probe.get("provider_attempts", 0)),
        "infrastructure_retries": 0,
        "cm59a_requests_sent": 0,
    }
    result = _result(a=a, b=b, probe_summary=probe_summary)
    for artifact in (a, b, probe_summary, result):
        _check_secrets(artifact)
    return {
        "configuration_a.json": a,
        "configuration_b.json": b,
        "probe_summary.json": probe_summary,
        "result.json": result,
    }


def write_artifacts(artifacts: dict[str, object], output_dir: Path) -> None:
    """Write sanitized C0 artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in artifacts.items():
        output_dir.joinpath(name).write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def main() -> None:
    """Run the bounded C0 probes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-authorized", action="store_true")
    parser.add_argument("--authorized-checkpoint", default="")
    parser.add_argument("--a-base-url", default=A_BASE_URL)
    parser.add_argument("--b-base-url", default=B_BASE_URL)
    parser.add_argument("--a-api-key-env", default="LLAMA_CPP_API_KEY")
    parser.add_argument("--a-api-key-file", default=None)
    parser.add_argument("--b-api-key-env", default="NVIDIA_API_KEY")
    parser.add_argument("--b-api-key-file", default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    if not args.live_authorized:
        raise SystemExit("C0 requires --live-authorized; no probe was run")
    write_artifacts(run_live(args, repo_root), args.output_dir)


if __name__ == "__main__":
    main()
