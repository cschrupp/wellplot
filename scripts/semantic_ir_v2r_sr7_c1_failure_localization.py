"""Localize the bounded SI-V2R SR7-C1 full-schema probe failure."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError

from scripts.semantic_ir_v2r_sr7_c0_config_probe import (
    B_BASE_URL,
    B_REQUESTED_MODEL,
    MAX_OUTPUT_TOKENS,
    NVIDIA_REASONING_DOC,
    PROBE_TIMEOUT_SECONDS,
    STRUCTURAL_RETRY_PROMPT,
    SYSTEM_PROMPT_SHA256,
    TOP_P_B,
    V2R_SCHEMA_SHA256,
    _api_key,
    _request_json,
    _schema_request,
    _synthetic_payload,
    canonical_json,
    sha256_text,
)
from scripts.si_v2r_model_qualification import V2R_SYSTEM_PROMPT
from wellplot.agent.code_mode.semantic_ir_v2r import SemanticIRV2R

BASELINE_SHA = "adfaa102da045626a2d5e8d153fbf973ffd55068"
DEFAULT_OUTPUT_DIR = Path("tests/fixtures/semantic_ir_v2r_sr7_c1")
GOLD_SHA256 = "eb4803c1b0265f72e2b7f3f97176afe585698473f108d60768e792e4ecfca0a5"
RETRY_PROMPT_SHA256 = "27c6a43c7f611a79401914b6732dbcec946493bba51058c1eb1d1245f47990f0"
C0_B_FINGERPRINT = "a473cc25db1415373b81d7775c263170d7c6388fa45caa5572b11308e8b7d980"
SECRET_MARKERS = ("Bearer", "NVIDIA_API_KEY", "OPENROUTER_API_KEY", "sk-", "nvapi-")
ROOT_MECHANISMS = {
    "JSON_SCHEMA_EXPLICIT_VIOLATION",
    "PYDANTIC_ONLY_RELATIONAL_VIOLATION",
    "MODEL_SEMANTIC_INVALIDITY",
    "PROVIDER_CONSTRAINT_ENFORCEMENT_GAP",
    "FAILURE_CAUSE_UNRESOLVED",
}

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - exercised only without the optional tool
    Draft202012Validator = None  # type: ignore[assignment,misc]


def _git_output(repo_root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=repo_root, stderr=subprocess.STDOUT)


def _artifact_hash(repo_root: Path, relative_path: str) -> str:
    return hashlib.sha256((repo_root / relative_path).read_bytes()).hexdigest()


def _schema_hash() -> str:
    return sha256_text(canonical_json(SemanticIRV2R.model_json_schema()))


def _sanitize_usage(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(item, (int, float, bool)) or item is None:
            result[str(key)] = item
        elif isinstance(item, dict):
            nested = _sanitize_usage(item)
            if nested is not None:
                result[str(key)] = nested
    return result


def _structural_projection(value: object) -> dict[str, object]:
    """Retain bounded JSON shape without retaining generated prose."""
    paths: list[dict[str, object]] = []
    safe_value_keys = {"kind", "semantic_id", "target_semantic_id"}

    def visit(node: object, path: tuple[str, ...], key: str | None = None) -> None:
        if len(paths) >= 250:
            return
        if isinstance(node, dict):
            paths.append({"path": list(path), "json_type": "object", "keys": sorted(node)})
            for child_key, child in sorted(node.items()):
                visit(child, (*path, str(child_key)), str(child_key))
            return
        if isinstance(node, list):
            paths.append(
                {
                    "path": list(path),
                    "json_type": "array",
                    "length": len(node),
                }
            )
            for index, child in enumerate(node):
                visit(child, (*path, str(index)), key)
            return
        entry: dict[str, object] = {
            "path": list(path),
            "json_type": (
                "null"
                if node is None
                else "boolean"
                if isinstance(node, bool)
                else "number"
                if isinstance(node, (int, float))
                else "string"
            ),
        }
        if isinstance(node, str):
            entry["length"] = len(node)
            entry["sha256"] = sha256_text(node)
            if key in safe_value_keys:
                entry["value"] = node
        paths.append(entry)

    visit(value, ())
    return {"field_paths": paths, "field_path_count": len(paths)}


def _sanitize_validation_error(error: dict[str, object]) -> dict[str, object]:
    loc = error.get("loc", ())
    sanitized_loc = [item if isinstance(item, (str, int)) else str(item) for item in loc]
    ctx = error.get("ctx")
    return {
        "loc": sanitized_loc,
        "type": str(error.get("type", "unknown")),
        "msg_category": _message_category(str(error.get("msg", ""))),
        "ctx_keys": sorted(ctx) if isinstance(ctx, dict) else [],
    }


def _message_category(message: str) -> str:
    normalized = message.lower()
    known = (
        ("reference_track_target_required", "reference_track intent requires"),
        ("companion_target_forbidden", "companion_depth_lane intent cannot target"),
        ("reference_target_missing", "reference target must identify"),
        ("fill_target_missing", "fill target must reference"),
        ("feature_ids_not_unique", "feature ids must be unique"),
        ("work_required", "must contain report or section intent"),
        ("nonempty", "cannot contain blank items"),
    )
    for category, phrase in known:
        if phrase in normalized:
            return category
    return "pydantic_validation_error"


def _json_schema_errors(payload: object) -> dict[str, object]:
    if Draft202012Validator is None:
        return {"status": "UNAVAILABLE", "errors": []}
    validator = Draft202012Validator(SemanticIRV2R.model_json_schema())
    errors = []
    for error in validator.iter_errors(payload):
        errors.append(
            {
                "instance_path": [
                    item if isinstance(item, (str, int)) else str(item)
                    for item in error.absolute_path
                ],
                "schema_path": [
                    item if isinstance(item, (str, int)) else str(item)
                    for item in error.absolute_schema_path
                ],
                "keyword": str(error.validator),
                "message_category": str(error.validator),
            }
        )
    return {"status": "PASS" if not errors else "FAIL", "errors": errors}


def _pydantic_errors(payload: object) -> dict[str, object]:
    try:
        SemanticIRV2R.model_validate(payload)
    except ValidationError as error:
        errors = [_sanitize_validation_error(item) for item in error.errors(include_input=False)]
        return {"status": "FAIL", "errors": errors}
    return {"status": "PASS", "errors": []}


def _rule_inventory() -> list[dict[str, object]]:
    schema = SemanticIRV2R.model_json_schema()
    reference_schema = schema.get("$defs", {}).get("ReferenceSemanticIntentV2R", {})
    reference_required = reference_schema.get("required", [])
    return [
        {
            "rule_id": "reference_track_target_required",
            "implementation": "PYDANTIC_MODEL_VALIDATOR",
            "json_schema_explicit": (
                "YES_EXPLICIT" if "target_semantic_id" in reference_required else "NO_PYTHON_ONLY"
            ),
        },
        {
            "rule_id": "companion_target_forbidden",
            "implementation": "PYDANTIC_MODEL_VALIDATOR",
            "json_schema_explicit": "NO_PYTHON_ONLY",
        },
        {
            "rule_id": "reference_target_existing_feature",
            "implementation": "PYDANTIC_MODEL_VALIDATOR",
            "json_schema_explicit": "NO_PYTHON_ONLY",
        },
        {
            "rule_id": "fill_target_curve",
            "implementation": "PYDANTIC_MODEL_VALIDATOR",
            "json_schema_explicit": "NO_PYTHON_ONLY",
        },
        {
            "rule_id": "feature_ids_unique",
            "implementation": "PYDANTIC_MODEL_VALIDATOR",
            "json_schema_explicit": "NO_PYTHON_ONLY",
        },
        {
            "rule_id": "work_required",
            "implementation": "PYDANTIC_MODEL_VALIDATOR",
            "json_schema_explicit": "NO_PYTHON_ONLY",
        },
        {
            "rule_id": "semantic_id_nonempty",
            "implementation": "PYDANTIC_FIELD_VALIDATOR",
            "json_schema_explicit": "YES_EXPLICIT",
        },
        {
            "rule_id": "kind_enum",
            "implementation": "JSON_SCHEMA_EXPLICIT",
            "json_schema_explicit": "YES_EXPLICIT",
        },
    ]


def _failed_rule_ids(errors: Iterable[dict[str, object]]) -> list[str]:
    rule_ids = []
    for error in errors:
        category = error.get("msg_category")
        if isinstance(category, str) and category not in rule_ids:
            rule_ids.append(category)
    return rule_ids


def analyze_sanitized_evidence(evidence: dict[str, object]) -> dict[str, object]:
    """Derive C1 diagnostics from sanitized evidence without provider access."""
    transport = evidence.get("transport_status")
    json_status = evidence.get("json_parse_status")
    schema_status = evidence.get("json_schema_conformance")
    pydantic_status = evidence.get("pydantic_canonical_status")
    pydantic_errors = evidence.get("pydantic_errors", [])
    if not isinstance(pydantic_errors, list):
        pydantic_errors = []
    if transport != "PASS" or json_status != "PASS" or pydantic_status != "FAIL":
        root = "FAILURE_CAUSE_UNRESOLVED"
        freeze = "B_FREEZE_UNRESOLVED"
        decision = "SI_V2R_SR7_C1_FAILURE_CAUSE_UNRESOLVED"
    elif schema_status == "PASS":
        root = "PYDANTIC_ONLY_RELATIONAL_VIOLATION"
        freeze = "B_FREEZE_ALLOWED"
        decision = "SI_V2R_SR7_C1_B_FREEZE_ALLOWED"
    elif schema_status == "FAIL":
        root = "PROVIDER_CONSTRAINT_ENFORCEMENT_GAP"
        freeze = "B_FREEZE_FORBIDDEN"
        decision = "SI_V2R_SR7_C1_B_FREEZE_FORBIDDEN"
    else:
        root = "FAILURE_CAUSE_UNRESOLVED"
        freeze = "B_FREEZE_UNRESOLVED"
        decision = "SI_V2R_SR7_C1_FAILURE_LOCALIZED_BUT_FREEZE_UNRESOLVED"
    assert root in ROOT_MECHANISMS
    primary_path = pydantic_errors[0].get("loc", []) if pydantic_errors else []
    return {
        "decision": decision,
        "root_mechanism": root,
        "evidence_class": "EMPIRICALLY_SUPPORTED"
        if root != "FAILURE_CAUSE_UNRESOLVED"
        else "UNRESOLVED",
        "b_freeze": freeze,
        "validation_error_count": len(pydantic_errors),
        "primary_failed_path": primary_path,
        "failed_rule_ids": _failed_rule_ids(pydantic_errors),
        "transport_status": transport,
        "json_parse_status": json_status,
        "json_schema_conformance": schema_status,
        "pydantic_canonical_status": pydantic_status,
        "synthetic_semantic_status": "NOT_EVALUATED",
    }


def build_preflight(repo_root: Path, authorized_checkpoint: str) -> dict[str, object]:
    """Authenticate C0 and repository inputs before the one provider call."""
    if authorized_checkpoint != _git_output(repo_root, "rev-parse", "HEAD").decode().strip():
        raise RuntimeError("C1 checkout does not match authorized checkpoint")
    expected = {
        "v2r_schema_sha256": V2R_SCHEMA_SHA256,
        "prompt_sha256": SYSTEM_PROMPT_SHA256,
        "retry_prompt_sha256": sha256_text(STRUCTURAL_RETRY_PROMPT),
        "gold_sha256": GOLD_SHA256,
    }
    actual = {
        "v2r_schema_sha256": _schema_hash(),
        "prompt_sha256": sha256_text(V2R_SYSTEM_PROMPT),
        "retry_prompt_sha256": RETRY_PROMPT_SHA256,
        "gold_sha256": _artifact_hash(
            repo_root, "tests/fixtures/semantic_ir_v2r/cm59a_semantic_intents_v2r.json"
        ),
    }
    if actual != expected:
        raise RuntimeError("C1 frozen repository input hash mismatch")
    c0_result_path = "docs/evaluations/agent-code-mode/semantic-ir-v2/55-si-v2r-sr7-c0-result.md"
    if (
        _git_output(repo_root, "show", f"{BASELINE_SHA}:{c0_result_path}")
        != (repo_root / c0_result_path).read_bytes()
    ):
        raise RuntimeError("C0 result artifact changed")
    return {
        "baseline": BASELINE_SHA,
        "authorized_checkpoint": authorized_checkpoint,
        "frozen_inputs": actual,
        "c0_b_fingerprint": C0_B_FINGERPRINT,
        "configuration": {
            "base_url": B_BASE_URL,
            "model": B_REQUESTED_MODEL,
            "temperature": 1.0,
            "top_p": TOP_P_B,
            "reasoning_effort": "low",
            "max_tokens": MAX_OUTPUT_TOKENS,
        },
    }


def _transient(status: int, error: dict[str, object] | None) -> bool:
    if status in {429, 500, 501, 502, 503, 504}:
        return True
    return isinstance(error, dict) and error.get("category") in {"transport", "timeout"}


def _run_probe(*, api_key: str, preflight: dict[str, object]) -> dict[str, object]:
    payload = _schema_request(
        model=B_REQUESTED_MODEL,
        system_prompt=V2R_SYSTEM_PROMPT,
        user_prompt=_synthetic_payload(),
        schema_name="SemanticIRV2R",
        schema=SemanticIRV2R.model_json_schema(),
        temperature=1.0,
        top_p=TOP_P_B,
        reasoning_effort="low",
    )
    request_fingerprint = sha256_text(canonical_json(payload))
    attempts: list[dict[str, object]] = []
    body: dict[str, object] | None = None
    status = 0
    error: dict[str, object] | None = None
    for attempt in range(2):
        status, body, error, latency = _request_json(
            "POST",
            f"{B_BASE_URL}/chat/completions",
            api_key=api_key,
            payload=payload,
            timeout_seconds=PROBE_TIMEOUT_SECONDS,
        )
        attempts.append(
            {
                "attempt": attempt + 1,
                "status_code": status,
                "latency_ms": round(latency, 3),
                "error_category": error.get("category") if error else None,
            }
        )
        if body is not None or not _transient(status, error) or attempt == 1:
            break
    result: dict[str, object] = {
        "provider": "NVIDIA",
        "model": B_REQUESTED_MODEL,
        "request_fingerprint_sha256": request_fingerprint,
        "response_status_code": status,
        "transport_status": "PASS" if body is not None and status == 200 else "FAIL",
        "provider_attempts": len(attempts),
        "infrastructure_retries": max(0, len(attempts) - 1),
        "attempts": attempts,
        "preflight": preflight,
        "reasoning_control": {
            "parameter": "reasoning_effort",
            "value": "low",
            "source": NVIDIA_REASONING_DOC,
        },
    }
    if body is None:
        result.update(
            {
                "json_parse_status": "NOT_EVALUABLE",
                "json_schema_conformance": "NOT_EVALUABLE",
                "pydantic_canonical_status": "NOT_EVALUABLE",
                "pydantic_errors": [],
                "raw_content_sha256": None,
                "raw_content_length": None,
                "error_category": error.get("category") if error else "unknown",
            }
        )
        return result
    choices = body.get("choices")
    message = (
        choices[0].get("message")
        if isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict)
        else None
    )
    content = message.get("content") if isinstance(message, dict) else None
    result.update(
        {
            "returned_model_identifier": body.get("model", B_REQUESTED_MODEL),
            "finish_reason": (
                choices[0].get("finish_reason")
                if isinstance(choices, list) and choices and isinstance(choices[0], dict)
                else None
            ),
            "usage": _sanitize_usage(body.get("usage")),
            "reasoning_fields_present": sorted(
                key
                for key in ("reasoning_content", "reasoning", "reasoning_tokens")
                if (isinstance(message, dict) and key in message) or key in body
            ),
        }
    )
    if not isinstance(content, str):
        result.update(
            {
                "json_parse_status": "FAIL",
                "json_schema_conformance": "NOT_EVALUABLE",
                "pydantic_canonical_status": "NOT_EVALUABLE",
                "pydantic_errors": [],
                "raw_content_sha256": None,
                "raw_content_length": None,
            }
        )
        return result
    result["raw_content_sha256"] = sha256_text(content)
    result["raw_content_length"] = len(content)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        result.update(
            {
                "json_parse_status": "FAIL",
                "json_schema_conformance": "NOT_EVALUABLE",
                "pydantic_canonical_status": "NOT_EVALUABLE",
                "pydantic_errors": [],
            }
        )
        return result
    schema_result = _json_schema_errors(parsed)
    pydantic_result = _pydantic_errors(parsed)
    result.update(
        {
            "json_parse_status": "PASS",
            "json_schema_conformance": schema_result["status"],
            "json_schema_errors": schema_result["errors"],
            "pydantic_canonical_status": pydantic_result["status"],
            "pydantic_errors": pydantic_result["errors"],
            "structural_projection": _structural_projection(parsed),
        }
    )
    return result


def _check_secrets(value: object) -> None:
    text = json.dumps(value, sort_keys=True).lower()
    for marker in SECRET_MARKERS:
        if marker.lower() in text:
            raise RuntimeError(f"secret marker persisted in C1 artifact: {marker}")


def build_artifacts(evidence: dict[str, object], preflight: dict[str, object]) -> dict[str, object]:
    """Build all four C1 artifacts from sanitized evidence."""
    validation_errors = {
        "schema_version": "si-v2r.sr7-c1.validation-errors.v1",
        "pydantic_errors": evidence.get("pydantic_errors", []),
        "json_schema_errors": evidence.get("json_schema_errors", []),
        "validation_error_count": len(evidence.get("pydantic_errors", [])),
        "primary_failed_path": (
            evidence.get("pydantic_errors", [{}])[0].get("loc", [])
            if evidence.get("pydantic_errors")
            else []
        ),
    }
    rules = _rule_inventory()
    analysis_input = {
        "transport_status": evidence.get("transport_status"),
        "json_parse_status": evidence.get("json_parse_status"),
        "json_schema_conformance": evidence.get("json_schema_conformance"),
        "pydantic_canonical_status": evidence.get("pydantic_canonical_status"),
        "pydantic_errors": evidence.get("pydantic_errors", []),
    }
    derived = analyze_sanitized_evidence(analysis_input)
    schema_analysis = {
        "schema_version": "si-v2r.sr7-c1.schema-analysis.v1",
        "schema_sha256": V2R_SCHEMA_SHA256,
        "local_validator": "jsonschema.Draft202012Validator"
        if Draft202012Validator is not None
        else "UNAVAILABLE",
        "rules": rules,
        "failed_rule_ids": derived["failed_rule_ids"],
        "expressibility_for_observed_failure": (
            "YES_EXPLICIT"
            if evidence.get("json_schema_conformance") == "FAIL"
            else "NO_PYTHON_ONLY"
            if evidence.get("json_schema_conformance") == "PASS"
            else "UNRESOLVED"
        ),
    }
    probe_summary = {
        "schema_version": "si-v2r.sr7-c1.probe-summary.v1",
        "preflight": preflight,
        "probe": {
            key: value
            for key, value in evidence.items()
            if key
            not in {
                "structural_projection",
            }
        },
        "structural_projection": evidence.get("structural_projection"),
        "structured_calls_b": evidence.get("provider_attempts", 0),
        "infrastructure_retries": evidence.get("infrastructure_retries", 0),
        "cm59a_requests_sent": 0,
        "a_inference_calls": 0,
        "worker_program_calls": 0,
    }
    result = {
        "schema_version": "si-v2r.sr7-c1.result.v1",
        "decision": derived["decision"],
        "root_mechanism": derived["root_mechanism"],
        "evidence_class": derived["evidence_class"],
        "b_freeze": derived["b_freeze"],
        "configuration_b_fingerprint_sha256": C0_B_FINGERPRINT,
        "validation_error_count": derived["validation_error_count"],
        "primary_failed_path": derived["primary_failed_path"],
        "rule_represented_explicitly": schema_analysis["expressibility_for_observed_failure"],
        "transport_status": evidence.get("transport_status"),
        "json_parse_status": evidence.get("json_parse_status"),
        "json_schema_conformance": evidence.get("json_schema_conformance"),
        "pydantic_canonical_status": evidence.get("pydantic_canonical_status"),
        "synthetic_semantic_status": "NOT_EVALUATED",
        "structured_calls_b": evidence.get("provider_attempts", 0),
        "infrastructure_retries": evidence.get("infrastructure_retries", 0),
        "cm59a_requests_sent": 0,
        "a_inference_calls": 0,
        "worker_program_calls": 0,
        "production_changes": 0,
        "prompt_changed": False,
        "schema_changed": False,
        "gold_changed": False,
        "cm58_changed": False,
        "v2r_changed": False,
        "sr7_p0_authorized": False,
        "live_paired_comparison_authorized": False,
    }
    artifacts = {
        "validation_errors.json": validation_errors,
        "schema_rule_analysis.json": schema_analysis,
        "probe_summary.json": probe_summary,
        "result.json": result,
    }
    for artifact in artifacts.values():
        _check_secrets(artifact)
    return artifacts


def write_artifacts(artifacts: dict[str, object], output_dir: Path) -> None:
    """Write sanitized C1 artifacts and reject evidence mixing."""
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError("C1 output directory is not empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in artifacts.items():
        output_dir.joinpath(name).write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def run_live(args: argparse.Namespace, repo_root: Path) -> dict[str, object]:
    """Run the one authorized B2 probe and derive sanitized artifacts."""
    if args.authorized_checkpoint != _git_output(repo_root, "rev-parse", "HEAD").decode().strip():
        raise RuntimeError("C1 checkout does not match authorized checkpoint")
    preflight = build_preflight(repo_root, args.authorized_checkpoint)
    api_key = _api_key(args.api_key_env, args.api_key_file)
    evidence = _run_probe(api_key=api_key, preflight=preflight)
    return build_artifacts(evidence, preflight)


def main() -> None:
    """Run live C1 once or analyze a previously sanitized evidence object."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-authorized", action="store_true")
    parser.add_argument("--authorized-checkpoint", default="")
    parser.add_argument("--api-key-env", default="NVIDIA_API_KEY")
    parser.add_argument("--api-key-file", default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--analyze", type=Path, default=None)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    if args.analyze is not None:
        evidence = json.loads(args.analyze.read_text(encoding="utf-8"))
        print(json.dumps(analyze_sanitized_evidence(evidence), indent=2, sort_keys=True))
        return
    if not args.live_authorized:
        raise SystemExit("C1 requires --live-authorized; no probe was run")
    write_artifacts(run_live(args, repo_root), args.output_dir)


if __name__ == "__main__":
    main()
