"""Probe exact successor-template control behavior without model inference.

The future authorized execution is fixed to two successor-identity GETs and
two ``/apply-template`` POSTs. This module has no provider construction or
chat-completions path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from scripts import d5_5i_runtime_pin_establishment as pin
from scripts import nlp_d4_live_acceptance as d4
from scripts import nlp_d5_live_semantic_qualification as d5
from wellplot.project_config import load_project_config

TARGET_EXECUTABLE_CHECKPOINT = "fa3bfe59819d9b5e4cac9821b7770d7f4b4b3a0b"
PROJECTION_BASELINE_CHECKPOINT = "aeb2ad07e9e4430efe60098a58629201f19cbaee"
TARGET_SERVER_ORIGIN = "http://192.168.2.141:8888"
TARGET_OPENAI_COMPAT_BASE_URL = f"{TARGET_SERVER_ORIGIN}/v1"
EXPECTED_MODEL = "qwen3.6-35b-a3b"
EXPECTED_CREDENTIAL_RESOLUTION = "d4.load_d4_api_key(repo_root)"
HISTORICAL_AUTHORIZATION_ID = "WELLPLOT-D5-5I-RUNTIME-PIN-ESTABLISHMENT-AUTH-001"
MAX_ENDPOINT_ATTEMPTS = 4
MAX_ENDPOINT_RESPONSE_BYTES = d5.MAX_ENDPOINT_RESPONSE_BYTES

SUCCESSOR_FIELDS = (
    "model_catalog",
    "model_path_basename",
    "model_path_fingerprint_sha256",
    "build_info",
    "context_size",
    "total_slots",
    "chat_template_sha256",
    "runtime_defaults_sha256",
)
REQUIRED_CUSTODY_DIGESTS = ("state_sha256", "journal_sha256", "terminal_sha256")
PROBE_STATE_SUFFIX = ".state.json"
PROBE_JOURNAL_SUFFIX = ".journal.jsonl"
PROBE_TERMINAL_SUFFIX = ".terminal.json"
PROBE_SUMMARY_SUFFIX = ".summary.json"

PROBE_MESSAGES = (
    {"role": "system", "content": "You are a template-formatting probe."},
    {"role": "user", "content": "State the word READY."},
)
FALSE_REQUEST_OPTIONS = {"chat_template_kwargs": {"enable_thinking": False}}
TRUE_REQUEST_OPTIONS = {"chat_template_kwargs": {"enable_thinking": True}}
FALSE_REQUEST_BODY = {
    **FALSE_REQUEST_OPTIONS,
    "messages": list(PROBE_MESSAGES),
    "model": EXPECTED_MODEL,
}
TRUE_REQUEST_BODY = {
    **TRUE_REQUEST_OPTIONS,
    "messages": list(PROBE_MESSAGES),
    "model": EXPECTED_MODEL,
}
FALSE_REQUEST_BODY_SHA256 = "e4711fcaad9b74d2c50cdf8d0d56df4959958366b574682c8b4b3f74f999f259"
TRUE_REQUEST_BODY_SHA256 = "a9cb9e9ee04db246c5eb1f4b5b92fd888074688d14bf62a1ba9b792e802f859c"


class ProbeToolError(RuntimeError):
    """Base error for bounded successor-runtime probe failures."""


class ProbeStaticPreflightError(ProbeToolError):
    """Raised before endpoint issuance when the probe is not admissible."""


class ProbeEndpointError(ProbeToolError):
    """Represent a bounded endpoint failure without retaining a response."""

    def __init__(self, reason: str, *, http_status: int | None = None) -> None:
        """Retain only the failure category and optional HTTP status."""
        super().__init__(reason)
        self.reason = reason
        self.http_status = http_status


@dataclass(frozen=True, slots=True)
class ProbeUnusableJson:
    """Represent an HTTP-successful response whose body is not JSON."""

    reason: str = "invalid_json"


@dataclass(frozen=True, slots=True)
class ProbeEndpointResponse:
    """Retain bounded HTTP status separately from the parsed response."""

    payload: object
    http_status: int | None


@dataclass(frozen=True, slots=True)
class ProbeAuthorization:
    """Facts needed to run one fresh successor-runtime probe namespace."""

    scientific_executable_checkpoint: str
    projection_baseline_checkpoint: str
    probe_tooling_checkpoint: str
    authorization_id: str
    project_config_fingerprint_sha256: str
    artifact_root: str
    historical_pin_artifact_root: str
    historical_pin_authorization_id: str
    historical_pin_custody_digests: Mapping[str, str]
    successor_identity: Mapping[str, Any]
    target_server_origin: str
    target_openai_compat_base_url: str
    model: str
    credential_resolution: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ProbeAuthorization:
        """Parse explicit probe authority without deriving identity values."""
        required = {
            "scientific_executable_checkpoint",
            "projection_baseline_checkpoint",
            "probe_tooling_checkpoint",
            "authorization_id",
            "project_config_fingerprint_sha256",
            "artifact_root",
            "historical_pin_artifact_root",
            "historical_pin_authorization_id",
            "historical_pin_custody_digests",
            "successor_identity",
            "target_server_origin",
            "target_openai_compat_base_url",
            "model",
            "credential_resolution",
        }
        missing = sorted(required - set(value))
        if missing:
            raise ProbeStaticPreflightError(f"probe authorization is missing: {missing!r}")
        digests = value["historical_pin_custody_digests"]
        identity = value["successor_identity"]
        if not isinstance(digests, Mapping):
            raise ProbeStaticPreflightError("historical pin custody digests are not a mapping")
        if not isinstance(identity, Mapping):
            raise ProbeStaticPreflightError("successor identity is not a mapping")
        missing_digests = sorted(set(REQUIRED_CUSTODY_DIGESTS) - set(digests))
        missing_identity = sorted(set(SUCCESSOR_FIELDS) - set(identity))
        unsupported_identity = sorted(set(identity) - set(SUCCESSOR_FIELDS))
        if missing_digests:
            raise ProbeStaticPreflightError(
                f"historical pin custody digests are missing: {missing_digests!r}"
            )
        if missing_identity:
            raise ProbeStaticPreflightError(f"successor identity is missing: {missing_identity!r}")
        if unsupported_identity:
            raise ProbeStaticPreflightError(
                f"successor identity has unsupported fields: {unsupported_identity!r}"
            )
        authorization = cls(
            scientific_executable_checkpoint=str(value["scientific_executable_checkpoint"]),
            projection_baseline_checkpoint=str(value["projection_baseline_checkpoint"]),
            probe_tooling_checkpoint=str(value["probe_tooling_checkpoint"]),
            authorization_id=str(value["authorization_id"]),
            project_config_fingerprint_sha256=str(value["project_config_fingerprint_sha256"]),
            artifact_root=str(value["artifact_root"]),
            historical_pin_artifact_root=str(value["historical_pin_artifact_root"]),
            historical_pin_authorization_id=str(value["historical_pin_authorization_id"]),
            historical_pin_custody_digests={str(k): str(v) for k, v in digests.items()},
            successor_identity=dict(identity),
            target_server_origin=str(value["target_server_origin"]),
            target_openai_compat_base_url=str(value["target_openai_compat_base_url"]),
            model=str(value["model"]),
            credential_resolution=str(value["credential_resolution"]),
        )
        if authorization.scientific_executable_checkpoint != TARGET_EXECUTABLE_CHECKPOINT:
            raise ProbeStaticPreflightError("probe executable checkpoint drifted")
        if authorization.projection_baseline_checkpoint != PROJECTION_BASELINE_CHECKPOINT:
            raise ProbeStaticPreflightError("projection baseline checkpoint drifted")
        if not authorization.probe_tooling_checkpoint:
            raise ProbeStaticPreflightError("probe tooling checkpoint is missing")
        if authorization.probe_tooling_checkpoint == PROJECTION_BASELINE_CHECKPOINT:
            raise ProbeStaticPreflightError("probe tooling checkpoint is not distinct")
        if authorization.target_server_origin != TARGET_SERVER_ORIGIN:
            raise ProbeStaticPreflightError("probe server origin drifted")
        if authorization.target_openai_compat_base_url != TARGET_OPENAI_COMPAT_BASE_URL:
            raise ProbeStaticPreflightError("probe OpenAI-compatible base URL drifted")
        if authorization.model != EXPECTED_MODEL:
            raise ProbeStaticPreflightError("probe model identity drifted")
        if authorization.credential_resolution != EXPECTED_CREDENTIAL_RESOLUTION:
            raise ProbeStaticPreflightError("probe credential resolution drifted")
        if authorization.historical_pin_authorization_id != HISTORICAL_AUTHORIZATION_ID:
            raise ProbeStaticPreflightError("historical pin authorization drifted")
        for identity_field in SUCCESSOR_FIELDS:
            if not authorization.successor_identity[identity_field]:
                raise ProbeStaticPreflightError(
                    f"successor identity field is empty: {identity_field}"
                )
        if not authorization.authorization_id or not authorization.artifact_root:
            raise ProbeStaticPreflightError("probe custody identity is missing")
        if Path(authorization.authorization_id).name != authorization.authorization_id:
            raise ProbeStaticPreflightError("probe authorization ID is not a leaf")
        return authorization


@dataclass(frozen=True, slots=True)
class ProbeEvidencePaths:
    """Collision-sensitive files for one probe authority."""

    root: Path
    authorization_id: str

    @property
    def state(self) -> Path:
        """Return durable consumption state."""
        return self.root / f"{self.authorization_id}{PROBE_STATE_SUFFIX}"

    @property
    def journal(self) -> Path:
        """Return append-only event custody."""
        return self.root / f"{self.authorization_id}{PROBE_JOURNAL_SUFFIX}"

    @property
    def terminal(self) -> Path:
        """Return immutable terminal result."""
        return self.root / f"{self.authorization_id}{PROBE_TERMINAL_SUFFIX}"

    @property
    def summary(self) -> Path:
        """Return terminal digest summary."""
        return self.root / f"{self.authorization_id}{PROBE_SUMMARY_SUFFIX}"

    def all_paths(self) -> tuple[Path, ...]:
        """Return all files that must be absent in a fresh namespace."""
        return self.state, self.journal, self.terminal, self.summary


def _atomic_json(path: Path, value: Mapping[str, Any], *, exclusive: bool = False) -> None:
    """Write one redacted JSON artifact atomically."""
    if not d5.evidence_is_redacted(value):
        raise ProbeToolError("probe evidence redaction failed")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if exclusive and path.exists():
        temporary.unlink(missing_ok=True)
        raise ProbeToolError(f"probe artifact already exists: {path.name}")
    os.replace(temporary, path)


def _append_event(path: Path, event: Mapping[str, Any], *, exclusive: bool = False) -> None:
    """Append one redacted probe event."""
    if not d5.evidence_is_redacted(event):
        raise ProbeToolError("probe journal redaction failed")
    if exclusive and path.exists():
        raise ProbeToolError("probe journal already exists")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")


def _sha256_file(path: Path) -> str:
    """Hash one sealed probe artifact."""
    return d5._sha256_file(path)


def _git(repo_root: Path, *arguments: str) -> str:
    """Read one Git fact without changing the checkout."""
    return subprocess.check_output(["git", *arguments], cwd=repo_root, text=True).strip()


def _artifact_root(repo_root: Path, configured_value: str) -> Path:
    """Resolve one authority namespace relative to the target checkout."""
    configured = Path(configured_value).expanduser()
    return (configured if configured.is_absolute() else repo_root / configured).resolve()


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    """Serialize one request using the frozen probe canonicalization."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _request_body(enable_thinking: bool) -> bytes:
    """Return the exact frozen false/true request body."""
    body = FALSE_REQUEST_BODY if not enable_thinking else TRUE_REQUEST_BODY
    encoded = _canonical_json(body)
    expected = FALSE_REQUEST_BODY_SHA256 if not enable_thinking else TRUE_REQUEST_BODY_SHA256
    if hashlib.sha256(encoded).hexdigest() != expected:
        raise ProbeStaticPreflightError("frozen probe request body digest drifted")
    return encoded


def _validate_frozen_request_body(enable_thinking: bool, body: bytes) -> None:
    """Reject any request body other than the frozen canonical body."""
    if body != _request_body(enable_thinking):
        raise ProbeStaticPreflightError("probe request body mutation detected")


def _validate_route(method: str, url: str, project_config: object) -> None:
    """Allow only the two identity GETs and the two template POSTs."""
    expected = {
        ("GET", project_config.model_catalog_url): "/v1/models",
        ("GET", project_config.props_url): "/props",
        ("POST", f"{TARGET_SERVER_ORIGIN}/apply-template"): "/apply-template",
    }
    if (method, url) not in expected:
        raise ProbeStaticPreflightError(f"forbidden probe endpoint: {method} {url}")
    parsed = urlsplit(url)
    if parsed.query or parsed.fragment:
        raise ProbeStaticPreflightError("probe endpoint URL has query or fragment")


def _default_endpoint_request(
    method: str,
    url: str,
    api_key: str,
    body: bytes | None,
    project_config: object,
) -> object:
    """Issue one bounded request on the allowlisted non-generative routes."""
    _validate_route(method, url, project_config)
    headers = {"Authorization": f"Bearer {api_key}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20.0) as response:
            if response.geturl() != url:
                raise ProbeEndpointError("endpoint_identity_mismatch")
            raw = response.read(MAX_ENDPOINT_RESPONSE_BYTES + 1)
    except ProbeEndpointError:
        raise
    except urllib.error.HTTPError as error:
        reason = (
            "endpoint_authentication_failed" if error.code in {401, 403} else "endpoint_http_error"
        )
        raise ProbeEndpointError(reason, http_status=error.code) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        raise ProbeEndpointError("endpoint_transport_error") from None
    if len(raw) > MAX_ENDPOINT_RESPONSE_BYTES:
        raise ProbeEndpointError("endpoint_response_too_large")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        payload = ProbeUnusableJson()
    return ProbeEndpointResponse(payload=payload, http_status=response.status)


def _verify_historical_pin_join(
    repo_root: Path, authorization: ProbeAuthorization
) -> tuple[dict[str, str], dict[str, Any]]:
    """Verify AUTH-001 custody and bind its sealed successor observation."""
    root = _artifact_root(repo_root, authorization.historical_pin_artifact_root)
    paths = pin.MetadataEvidencePaths(root, authorization.historical_pin_authorization_id)
    digests = pin.verify_metadata_custody(paths)
    if digests != dict(authorization.historical_pin_custody_digests):
        raise ProbeStaticPreflightError("historical pin custody digest join failed")
    terminal = json.loads(paths.terminal.read_text(encoding="utf-8"))
    if terminal.get("outcome") != "MISMATCH":
        raise ProbeStaticPreflightError("historical pin terminal outcome drifted")
    if terminal.get("reason") != "HISTORICAL_IDENTITY_MISMATCH":
        raise ProbeStaticPreflightError("historical pin terminal reason drifted")
    if terminal.get("mismatched_fields") != ["build_info"]:
        raise ProbeStaticPreflightError("historical pin mismatch scope drifted")
    observed = terminal.get("observed_empirical_pins")
    if not isinstance(observed, Mapping):
        raise ProbeStaticPreflightError("historical pin successor observation is missing")
    if set(observed) != set(SUCCESSOR_FIELDS):
        raise ProbeStaticPreflightError("historical pin successor observation shape drifted")
    if dict(observed) != dict(authorization.successor_identity):
        raise ProbeStaticPreflightError("successor identity is not joined to AUTH-001")
    return digests, dict(observed)


def _validate_frozen_contract() -> None:
    """Fail closed if the frozen request or route contract changes."""
    _request_body(False)
    _request_body(True)
    if "/chat/completions" in json.dumps((FALSE_REQUEST_BODY, TRUE_REQUEST_BODY)):
        raise ProbeStaticPreflightError("generation route entered frozen probe body")


def _static_preflight(
    repo_root: Path,
    tooling_root: Path,
    authorization: ProbeAuthorization,
    paths: ProbeEvidencePaths,
    *,
    static_checker: Callable[[Path, ProbeAuthorization, ProbeEvidencePaths], dict[str, Any]]
    | None = None,
) -> dict[str, Any]:
    """Verify identities, custody join, and fresh namespace before credentials."""
    _validate_frozen_contract()
    if static_checker is not None:
        facts = static_checker(repo_root, authorization, paths)
    else:
        if _git(repo_root, "rev-parse", "HEAD") != authorization.scientific_executable_checkpoint:
            raise ProbeStaticPreflightError("implementation checkpoint mismatch")
        if _git(tooling_root, "rev-parse", "HEAD") != authorization.probe_tooling_checkpoint:
            raise ProbeStaticPreflightError("tooling checkpoint mismatch")
        if repo_root.resolve() == tooling_root.resolve():
            raise ProbeStaticPreflightError("target and tooling worktrees must be distinct")
        if _git(repo_root, "status", "--porcelain"):
            raise ProbeStaticPreflightError("target working tree is not clean")
        if _git(tooling_root, "status", "--porcelain"):
            raise ProbeStaticPreflightError("tooling working tree is not clean")
        project_config = load_project_config(repo_root)
        d5._validate_project_config(project_config)
        if project_config.fingerprint_sha256 != authorization.project_config_fingerprint_sha256:
            raise ProbeStaticPreflightError("project configuration fingerprint mismatch")
        if project_config.server_origin != authorization.target_server_origin:
            raise ProbeStaticPreflightError("configured server origin mismatch")
        if project_config.openai_compat_base_url != authorization.target_openai_compat_base_url:
            raise ProbeStaticPreflightError("configured OpenAI-compatible base URL mismatch")
        if project_config.provider.model != authorization.model:
            raise ProbeStaticPreflightError("configured model mismatch")
        if authorization.credential_resolution != EXPECTED_CREDENTIAL_RESOLUTION:
            raise ProbeStaticPreflightError("probe credential resolution drifted")
        historical_digests, historical_successor_identity = _verify_historical_pin_join(
            repo_root, authorization
        )
        attestation = d5._run_static_attestation(repo_root)
        facts = {
            "status": "PASS",
            "scientific_executable_checkpoint": authorization.scientific_executable_checkpoint,
            "projection_baseline_checkpoint": authorization.projection_baseline_checkpoint,
            "probe_tooling_checkpoint": authorization.probe_tooling_checkpoint,
            "project_config_fingerprint_sha256": project_config.fingerprint_sha256,
            "successor_identity": dict(authorization.successor_identity),
            "historical_pin_successor_identity": historical_successor_identity,
            "historical_pin_custody_digests": historical_digests,
            "single_engine_attestation": attestation,
        }
    if paths.root.exists() or any(path.exists() for path in paths.all_paths()):
        raise ProbeStaticPreflightError("probe evidence namespace is not fresh")
    return facts


@dataclass(slots=True)
class ProbeCustody:
    """Durable one-shot custody for the four-request probe."""

    paths: ProbeEvidencePaths
    authorization: ProbeAuthorization

    @classmethod
    def create(
        cls,
        paths: ProbeEvidencePaths,
        authorization: ProbeAuthorization,
        static_facts: Mapping[str, Any],
    ) -> ProbeCustody:
        """Create fresh custody before the first issued endpoint request."""
        if paths.root.exists() or any(path.exists() for path in paths.all_paths()):
            raise ProbeStaticPreflightError("probe evidence namespace is not fresh")
        paths.root.mkdir(parents=True)
        _atomic_json(
            paths.state,
            {
                "authorization_id": authorization.authorization_id,
                "scientific_executable_checkpoint": authorization.scientific_executable_checkpoint,
                "projection_baseline_checkpoint": authorization.projection_baseline_checkpoint,
                "probe_tooling_checkpoint": authorization.probe_tooling_checkpoint,
                "status": "READY",
                "consumed": False,
                "endpoint_attempts": 0,
                "provider_calls": 0,
                "model_calls": 0,
                "static_preflight": static_facts.get("status"),
            },
            exclusive=True,
        )
        _append_event(paths.journal, {"event": "probe_preflight_passed"}, exclusive=True)
        return cls(paths=paths, authorization=authorization)

    def _state(self) -> dict[str, Any]:
        """Read current durable state."""
        return json.loads(self.paths.state.read_text(encoding="utf-8"))

    def issue(self, method: str, endpoint: str) -> int:
        """Record one endpoint attempt before transport, with no fifth attempt."""
        state = self._state()
        attempts = int(state.get("endpoint_attempts", 0))
        if state.get("status") == "TERMINAL":
            raise ProbeToolError("probe authority is terminal")
        if attempts >= MAX_ENDPOINT_ATTEMPTS:
            raise ProbeToolError("fifth endpoint attempt rejected")
        next_attempt = attempts + 1
        updated = dict(state)
        updated.update({"status": "OBSERVING", "consumed": True, "endpoint_attempts": next_attempt})
        _atomic_json(self.paths.state, updated)
        _append_event(
            self.paths.journal,
            {
                "event": "probe_endpoint_issued",
                "method": method,
                "endpoint": endpoint,
                "attempt": next_attempt,
            },
        )
        return next_attempt

    def seal(self, terminal: Mapping[str, Any]) -> dict[str, Any]:
        """Write one immutable terminal result and digest summary."""
        if self.paths.terminal.exists() or self.paths.summary.exists():
            raise ProbeToolError("probe terminal already exists")
        state = self._state()
        record = {
            "authorization_id": self.authorization.authorization_id,
            "scientific_executable_checkpoint": self.authorization.scientific_executable_checkpoint,
            "projection_baseline_checkpoint": self.authorization.projection_baseline_checkpoint,
            "probe_tooling_checkpoint": self.authorization.probe_tooling_checkpoint,
            "provider_calls": 0,
            "model_calls": 0,
            **dict(terminal),
        }
        _atomic_json(self.paths.terminal, record, exclusive=True)
        _append_event(
            self.paths.journal,
            {
                "event": "probe_terminal_sealed",
                "outcome": record.get("outcome"),
                "endpoint_attempts": state.get("endpoint_attempts", 0),
            },
        )
        final_state = dict(state)
        final_state.update(
            {"status": "TERMINAL", "outcome": record.get("outcome"), "reason": record.get("reason")}
        )
        _atomic_json(self.paths.state, final_state)
        summary = {
            "authorization_id": self.authorization.authorization_id,
            "outcome": record.get("outcome"),
            "endpoint_attempts": final_state.get("endpoint_attempts", 0),
            "provider_calls": 0,
            "model_calls": 0,
            "state_sha256": _sha256_file(self.paths.state),
            "journal_sha256": _sha256_file(self.paths.journal),
            "terminal_sha256": _sha256_file(self.paths.terminal),
        }
        _atomic_json(self.paths.summary, summary, exclusive=True)
        return record


def _endpoint_failure(error: BaseException) -> tuple[str, int | None]:
    """Classify endpoint failure without retaining response content."""
    if isinstance(error, ProbeEndpointError):
        if error.http_status in {401, 403} or error.reason == "endpoint_authentication_failed":
            return "AUTHENTICATION_OR_TRANSPORT_FAILURE", error.http_status
        return "AUTHENTICATION_OR_TRANSPORT_FAILURE", error.http_status
    return "AUTHENTICATION_OR_TRANSPORT_FAILURE", None


def _endpoint_terminal(reason: str, attempts: int, status: int | None = None) -> dict[str, Any]:
    """Build bounded endpoint-failure evidence."""
    result: dict[str, Any] = {
        "outcome": "AUTHENTICATION_OR_TRANSPORT_FAILURE",
        "reason": reason,
        "endpoint_attempts": attempts,
        "generation_calls": 0,
    }
    if status is not None:
        result["http_status"] = status
    return result


def _project_successor_identity(catalog_payload: object, props_payload: object) -> dict[str, Any]:
    """Project the exact eight successor fields using accepted D5 semantics."""
    catalog = d5._project_model_catalog(catalog_payload, "")
    props = d5._project_props(props_payload, "json_schema")
    return {
        "model_catalog": list(catalog),
        **{field: props[field] for field in SUCCESSOR_FIELDS if field != "model_catalog"},
    }


def _identity_mismatches(
    observed: Mapping[str, Any], expected: Mapping[str, Any]
) -> tuple[str, ...]:
    """Return exact successor identity differences in frozen field order."""
    return tuple(field for field in SUCCESSOR_FIELDS if observed.get(field) != expected.get(field))


def _prompt_projection(payload: object) -> dict[str, Any]:
    """Retain only the bounded prompt shape, length, and hash."""
    if not isinstance(payload, Mapping) or not isinstance(payload.get("prompt"), str):
        raise ProbeToolError("apply-template response lacks a string prompt")
    prompt = payload["prompt"]
    encoded = prompt.encode("utf-8")
    return {
        "response_shape": "object_with_string_prompt",
        "prompt_length": len(prompt),
        "prompt_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _response_payload(response: object) -> object:
    """Unwrap the bounded transport result used by the real HTTP helper."""
    if isinstance(response, ProbeEndpointResponse):
        return response.payload
    return response


def _response_status(response: object) -> int | None:
    """Return an HTTP status when the transport exposes one."""
    if isinstance(response, ProbeEndpointResponse):
        return response.http_status
    return None


def _utc_observation_timestamp(clock: Callable[[], datetime] | None) -> str:
    """Return an injected or current UTC timestamp in bounded ISO form."""
    observed_at = (clock or (lambda: datetime.now(UTC)))()
    if observed_at.tzinfo is None:
        raise ProbeToolError("observation clock must provide timezone-aware UTC time")
    return observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")


def establish_successor_compatibility(
    *,
    repo_root: Path,
    tooling_root: Path,
    authorization: ProbeAuthorization,
    endpoint_request: Callable[[str, str, str, bytes | None], object],
    api_key_loader: Callable[[], str],
    static_checker: Callable[[Path, ProbeAuthorization, ProbeEvidencePaths], dict[str, Any]]
    | None = None,
    observation_clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Run the bounded GET, GET, POST(false), POST(true) probe sequence."""
    root = _artifact_root(repo_root, authorization.artifact_root)
    paths = ProbeEvidencePaths(root, authorization.authorization_id)
    static = _static_preflight(
        repo_root,
        tooling_root,
        authorization,
        paths,
        static_checker=static_checker,
    )
    try:
        token = api_key_loader()
    except Exception:
        raise ProbeToolError("CREDENTIAL_UNAVAILABLE before endpoint issuance") from None
    if not isinstance(token, str) or not token.strip():
        raise ProbeToolError("CREDENTIAL_UNAVAILABLE before endpoint issuance")
    custody = ProbeCustody.create(paths, authorization, static)
    project_config = load_project_config(repo_root)

    first_attempt = custody.issue("GET", "/v1/models")
    try:
        catalog_response = endpoint_request("GET", project_config.model_catalog_url, token, None)
        catalog_payload = _response_payload(catalog_response)
    except Exception as error:
        outcome, status = _endpoint_failure(error)
        return custody.seal(_endpoint_terminal("FIRST_IDENTITY_GET_FAILED", first_attempt, status))

    catalog_projection_error = False
    try:
        d5._project_model_catalog(catalog_payload, "")
    except (d5.D5ReadinessError, TypeError, ValueError):
        catalog_projection_error = True

    second_attempt = custody.issue("GET", "/props")
    try:
        props_response = endpoint_request("GET", project_config.props_url, token, None)
        props_payload = _response_payload(props_response)
    except Exception as error:
        outcome, status = _endpoint_failure(error)
        return custody.seal(
            _endpoint_terminal("SECOND_IDENTITY_GET_FAILED", second_attempt, status)
        )

    if catalog_projection_error:
        return custody.seal(
            {
                "outcome": "INCOMPLETE_SUCCESSOR_IDENTITY",
                "reason": "MODEL_CATALOG_UNAVAILABLE",
                "endpoint_attempts": second_attempt,
                "generation_calls": 0,
            }
        )
    try:
        observed_identity = _project_successor_identity(catalog_payload, props_payload)
    except (d5.D5ReadinessError, TypeError, ValueError):
        return custody.seal(
            {
                "outcome": "INCOMPLETE_SUCCESSOR_IDENTITY",
                "reason": "EXTENDED_RUNTIME_IDENTITY_UNAVAILABLE",
                "endpoint_attempts": second_attempt,
                "generation_calls": 0,
            }
        )
    mismatches = _identity_mismatches(observed_identity, authorization.successor_identity)
    identity_observation = {
        "contemporaneous_successor_identity": observed_identity,
        "successor_identity_observed_at_utc": _utc_observation_timestamp(observation_clock),
        "successor_identity_comparison": "EXACT_MATCH" if not mismatches else "MISMATCH",
    }
    if mismatches:
        return custody.seal(
            {
                "outcome": "SUCCESSOR_IDENTITY_DRIFT",
                "reason": "SUCCESSOR_IDENTITY_DRIFT",
                "mismatched_fields": list(mismatches),
                "endpoint_attempts": second_attempt,
                "generation_calls": 0,
                **identity_observation,
            }
        )

    false_body = _request_body(False)
    _validate_frozen_request_body(False, false_body)
    false_attempt = custody.issue("POST", "/apply-template")
    try:
        false_response = endpoint_request(
            "POST", f"{TARGET_SERVER_ORIGIN}/apply-template", token, false_body
        )
        false_projection = _prompt_projection(_response_payload(false_response))
    except Exception:
        return custody.seal(
            {
                "outcome": "COMPATIBILITY_UNESTABLISHED",
                "reason": "FALSE_ARM_FAILED",
                "endpoint_attempts": false_attempt,
                "generation_calls": 0,
                "false_request_body_sha256": FALSE_REQUEST_BODY_SHA256,
                "false_response_shape": "NOT_OBSERVED",
                **identity_observation,
            }
        )

    true_body = _request_body(True)
    _validate_frozen_request_body(True, true_body)
    true_attempt = custody.issue("POST", "/apply-template")
    try:
        true_response = endpoint_request(
            "POST", f"{TARGET_SERVER_ORIGIN}/apply-template", token, true_body
        )
        true_projection = _prompt_projection(_response_payload(true_response))
    except Exception:
        return custody.seal(
            {
                "outcome": "COMPATIBILITY_UNESTABLISHED",
                "reason": "TRUE_ARM_FAILED",
                "endpoint_attempts": true_attempt,
                "generation_calls": 0,
                "false_request_body_sha256": FALSE_REQUEST_BODY_SHA256,
                "true_request_body_sha256": TRUE_REQUEST_BODY_SHA256,
                "false_response_shape": "OBSERVED",
                "true_response_shape": "NOT_OBSERVED",
                **identity_observation,
            }
        )

    terminal = {
        "endpoint_attempts": true_attempt,
        "generation_calls": 0,
        "false_request_body_sha256": FALSE_REQUEST_BODY_SHA256,
        "true_request_body_sha256": TRUE_REQUEST_BODY_SHA256,
        "false_http_status": _response_status(false_response),
        "true_http_status": _response_status(true_response),
        "false_response_shape": false_projection["response_shape"],
        "true_response_shape": true_projection["response_shape"],
        "false_prompt_length": false_projection["prompt_length"],
        "false_prompt_sha256": false_projection["prompt_sha256"],
        "true_prompt_length": true_projection["prompt_length"],
        "true_prompt_sha256": true_projection["prompt_sha256"],
        **identity_observation,
    }
    if false_projection["prompt_sha256"] == true_projection["prompt_sha256"]:
        return custody.seal(
            {
                "outcome": "CONTROL_NOT_OBSERVED",
                "reason": "IDENTICAL_PROMPT_PROJECTIONS",
                **terminal,
            }
        )
    return custody.seal(
        {
            "outcome": "CONTROL_EFFECT_OBSERVED",
            "reason": "CONTROL_SENSITIVE_TEMPLATE_OUTPUT",
            "thinking_off_semantics": "NOT_ESTABLISHED_BY_THIS_PROBE",
            **terminal,
        }
    )


def verify_probe_custody(paths: ProbeEvidencePaths) -> dict[str, str]:
    """Verify terminal custody and digest joins without mutating evidence."""
    required = (paths.state, paths.journal, paths.terminal, paths.summary)
    if not all(path.is_file() for path in required):
        raise ProbeToolError("probe custody artifact set is incomplete")
    state = json.loads(paths.state.read_text(encoding="utf-8"))
    terminal = json.loads(paths.terminal.read_text(encoding="utf-8"))
    summary = json.loads(paths.summary.read_text(encoding="utf-8"))
    if state.get("status") != "TERMINAL":
        raise ProbeToolError("probe state is not terminal")
    if not all(d5.evidence_is_redacted(item) for item in (state, terminal, summary)):
        raise ProbeToolError("probe custody redaction failed")
    if any(
        item.get("authorization_id") != paths.authorization_id
        for item in (state, terminal, summary)
    ):
        raise ProbeToolError("probe authorization join failed")
    digests = {
        "state_sha256": _sha256_file(paths.state),
        "journal_sha256": _sha256_file(paths.journal),
        "terminal_sha256": _sha256_file(paths.terminal),
    }
    if any(summary.get(key) != value for key, value in digests.items()):
        raise ProbeToolError("probe custody digest mismatch")
    return digests


def _load_authorization(path: Path) -> ProbeAuthorization:
    """Load explicit probe authority without printing its contents."""
    return ProbeAuthorization.from_mapping(json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    """Run the explicitly supplied non-generative successor-runtime probe."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--tooling-repo-root", type=Path, required=True)
    parser.add_argument("--authorization-json", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = establish_successor_compatibility(
            repo_root=args.repo_root.resolve(),
            tooling_root=args.tooling_repo_root.resolve(),
            authorization=_load_authorization(args.authorization_json.resolve()),
            endpoint_request=lambda method, url, token, body: _default_endpoint_request(
                method,
                url,
                token,
                body,
                load_project_config(args.repo_root.resolve()),
            ),
            api_key_loader=lambda: d4.load_d4_api_key(args.repo_root.resolve()),
        )
    except ProbeToolError as error:
        print(json.dumps({"status": "NOT_RUN", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
