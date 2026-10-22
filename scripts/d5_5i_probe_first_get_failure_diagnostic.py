"""Diagnose the closed D5-5I probe's first identity request.

This tool has one optional network observation and no provider or generation
path. Its normal execution is intentionally separate from the closed probe.
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
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from scripts import nlp_d4_live_acceptance as d4
from scripts import nlp_d5_live_semantic_qualification as d5
from wellplot.project_config import load_project_config

SCIENTIFIC_CHECKPOINT = "fa3bfe59819d9b5e4cac9821b7770d7f4b4b3a0b"
FAILED_PROBE_TOOLING_CHECKPOINT = "fa8f1247ef6763c2fafcc024c4502aed8bd7af83"
EXPECTED_PROJECT_CONFIG_FINGERPRINT = (
    "b1d794a5ede8d4855717d34b3a02993f19b473ad120ff4fa51a06322a08a5bc3"
)
TARGET_URL = "http://192.168.2.141:8888/v1/models"
EXPECTED_CREDENTIAL_RESOLUTION = "d4.load_d4_api_key(repo_root)"
FAILED_PROBE_AUTHORIZATION_ID = "WELLPLOT-D5-5I-RUNTIME-BUILD-DRIFT-PROBE-AUTH-001"
MAX_ENDPOINT_ATTEMPTS = 1
MAX_ENDPOINT_RESPONSE_BYTES = d5.MAX_ENDPOINT_RESPONSE_BYTES
STATE_SUFFIX = ".state.json"
JOURNAL_SUFFIX = ".journal.jsonl"
TERMINAL_SUFFIX = ".terminal.json"
SUMMARY_SUFFIX = ".summary.json"
FAILED_PROBE_DIGEST_KEYS = ("state_sha256", "journal_sha256", "terminal_sha256")


class DiagnosticToolError(RuntimeError):
    """Base error for bounded first-request diagnostics."""


class DiagnosticPreflightError(DiagnosticToolError):
    """Raised when the contemporaneous zero-network preflight fails."""


class DiagnosticTransportError(DiagnosticToolError):
    """Raised for normalized transport failure without an HTTP response."""


@dataclass(frozen=True, slots=True)
class UnusableJson:
    """Represent an HTTP response whose body is not valid JSON."""

    reason: str


@dataclass(frozen=True, slots=True)
class DiagnosticHttpResponse:
    """Retain only bounded response data from the diagnostic transport."""

    payload: object
    http_status: int
    redirect_followed: bool = False


@dataclass(frozen=True, slots=True)
class DiagnosticAuthorization:
    """Explicit facts for one fresh first-request diagnostic namespace."""

    scientific_checkpoint: str
    failed_probe_tooling_checkpoint: str
    diagnostic_tooling_checkpoint: str
    authorization_id: str
    artifact_root: str
    project_config_fingerprint_sha256: str
    target_url: str
    credential_resolution: str
    failed_probe_authorization_id: str
    failed_probe_artifact_root: str
    failed_probe_custody_digests: Mapping[str, str]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> DiagnosticAuthorization:
        """Parse an explicit diagnostic authority without deriving identities."""
        required = {
            "scientific_checkpoint",
            "failed_probe_tooling_checkpoint",
            "diagnostic_tooling_checkpoint",
            "authorization_id",
            "artifact_root",
            "project_config_fingerprint_sha256",
            "target_url",
            "credential_resolution",
            "failed_probe_authorization_id",
            "failed_probe_artifact_root",
            "failed_probe_custody_digests",
        }
        missing = sorted(required - set(value))
        extra = sorted(set(value) - required)
        if missing:
            raise DiagnosticPreflightError(f"authorization fields missing: {missing!r}")
        if extra:
            raise DiagnosticPreflightError(f"unsupported authorization fields: {extra!r}")
        digests = value["failed_probe_custody_digests"]
        if not isinstance(digests, Mapping):
            raise DiagnosticPreflightError("failed-probe custody digests are not a mapping")
        if set(digests) != set(FAILED_PROBE_DIGEST_KEYS):
            raise DiagnosticPreflightError("failed-probe custody digest shape drifted")
        authorization = cls(
            scientific_checkpoint=str(value["scientific_checkpoint"]),
            failed_probe_tooling_checkpoint=str(value["failed_probe_tooling_checkpoint"]),
            diagnostic_tooling_checkpoint=str(value["diagnostic_tooling_checkpoint"]),
            authorization_id=str(value["authorization_id"]),
            artifact_root=str(value["artifact_root"]),
            project_config_fingerprint_sha256=str(value["project_config_fingerprint_sha256"]),
            target_url=str(value["target_url"]),
            credential_resolution=str(value["credential_resolution"]),
            failed_probe_authorization_id=str(value["failed_probe_authorization_id"]),
            failed_probe_artifact_root=str(value["failed_probe_artifact_root"]),
            failed_probe_custody_digests={str(k): str(v) for k, v in digests.items()},
        )
        if authorization.scientific_checkpoint != SCIENTIFIC_CHECKPOINT:
            raise DiagnosticPreflightError("scientific checkpoint drifted")
        if authorization.failed_probe_tooling_checkpoint != FAILED_PROBE_TOOLING_CHECKPOINT:
            raise DiagnosticPreflightError("failed-probe tooling checkpoint drifted")
        if (
            not authorization.diagnostic_tooling_checkpoint
            or authorization.diagnostic_tooling_checkpoint
            in {
                authorization.scientific_checkpoint,
                authorization.failed_probe_tooling_checkpoint,
            }
        ):
            raise DiagnosticPreflightError("diagnostic tooling checkpoint is not distinct")
        if authorization.target_url != TARGET_URL:
            raise DiagnosticPreflightError("diagnostic target URL drifted")
        if authorization.credential_resolution != EXPECTED_CREDENTIAL_RESOLUTION:
            raise DiagnosticPreflightError("credential resolution drifted")
        if authorization.failed_probe_authorization_id != FAILED_PROBE_AUTHORIZATION_ID:
            raise DiagnosticPreflightError("failed-probe authority drifted")
        for value_name, value_text in (
            ("authorization_id", authorization.authorization_id),
            ("artifact_root", authorization.artifact_root),
            ("failed_probe_artifact_root", authorization.failed_probe_artifact_root),
        ):
            if not value_text:
                raise DiagnosticPreflightError(f"{value_name} is empty")
        if Path(authorization.authorization_id).name != authorization.authorization_id:
            raise DiagnosticPreflightError("diagnostic authorization ID is not a leaf")
        return authorization


@dataclass(frozen=True, slots=True)
class DiagnosticEvidencePaths:
    """Files for one fresh diagnostic authority."""

    root: Path
    authorization_id: str

    @property
    def state(self) -> Path:
        """Return the mutable state artifact path."""
        return self.root / f"{self.authorization_id}{STATE_SUFFIX}"

    @property
    def journal(self) -> Path:
        """Return the append-only journal artifact path."""
        return self.root / f"{self.authorization_id}{JOURNAL_SUFFIX}"

    @property
    def terminal(self) -> Path:
        """Return the immutable terminal artifact path."""
        return self.root / f"{self.authorization_id}{TERMINAL_SUFFIX}"

    @property
    def summary(self) -> Path:
        """Return the digest summary artifact path."""
        return self.root / f"{self.authorization_id}{SUMMARY_SUFFIX}"

    def all_paths(self) -> tuple[Path, ...]:
        """Return every artifact path in custody order."""
        return self.state, self.journal, self.terminal, self.summary


def _redaction_projection(value: object) -> object:
    """Exclude one known-safe credential-loader label from secret scanning."""
    if isinstance(value, Mapping):
        return {
            key: _redaction_projection(item)
            for key, item in value.items()
            if not (key == "credential_resolution" and item == EXPECTED_CREDENTIAL_RESOLUTION)
        }
    if isinstance(value, list):
        return [_redaction_projection(item) for item in value]
    return value


def _atomic_json(path: Path, value: Mapping[str, Any], *, exclusive: bool = False) -> None:
    """Write one redacted JSON artifact atomically."""
    if not d5.evidence_is_redacted(_redaction_projection(value)):
        raise DiagnosticToolError("diagnostic evidence redaction failed")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if exclusive and path.exists():
        temporary.unlink(missing_ok=True)
        raise DiagnosticToolError(f"diagnostic artifact already exists: {path.name}")
    os.replace(temporary, path)


def _append_event(path: Path, event: Mapping[str, Any], *, exclusive: bool = False) -> None:
    """Append one bounded redacted event."""
    if not d5.evidence_is_redacted(_redaction_projection(event)):
        raise DiagnosticToolError("diagnostic journal redaction failed")
    if exclusive and path.exists():
        raise DiagnosticToolError("diagnostic journal already exists")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")


def _sha256_file(path: Path) -> str:
    """Return a file digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(repo_root: Path, *arguments: str) -> str:
    """Read one Git fact without changing a checkout."""
    return subprocess.check_output(["git", *arguments], cwd=repo_root, text=True).strip()


def _artifact_root(repo_root: Path, configured_value: str) -> Path:
    """Resolve a relative evidence path beneath the target checkout."""
    configured = Path(configured_value).expanduser()
    return (configured if configured.is_absolute() else repo_root / configured).resolve()


def _load_json(path: Path) -> Mapping[str, Any]:
    """Read bounded JSON custody data."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise DiagnosticPreflightError(f"custody artifact is not an object: {path.name}")
    return value


def _verify_failed_probe_join(
    repo_root: Path, authorization: DiagnosticAuthorization
) -> dict[str, str]:
    """Verify the closed probe custody and its exact digest binding."""
    root = _artifact_root(repo_root, authorization.failed_probe_artifact_root)
    paths = DiagnosticEvidencePaths(root, authorization.failed_probe_authorization_id)
    if not all(path.is_file() for path in paths.all_paths()):
        raise DiagnosticPreflightError("failed-probe custody artifacts are incomplete")
    digests = {
        key: _sha256_file(getattr(paths, key.removesuffix("_sha256")))
        for key in FAILED_PROBE_DIGEST_KEYS
    }
    if digests != dict(authorization.failed_probe_custody_digests):
        raise DiagnosticPreflightError("failed-probe custody digest join failed")
    summary = _load_json(paths.summary)
    if any(summary.get(key) != value for key, value in digests.items()):
        raise DiagnosticPreflightError("failed-probe summary digest join failed")
    state = _load_json(paths.state)
    terminal = _load_json(paths.terminal)
    if (
        state.get("authorization_id") != authorization.failed_probe_authorization_id
        or terminal.get("authorization_id") != authorization.failed_probe_authorization_id
        or summary.get("authorization_id") != authorization.failed_probe_authorization_id
        or state.get("status") != "TERMINAL"
        or state.get("consumed") is not True
        or state.get("endpoint_attempts") != 1
        or terminal.get("outcome") != "AUTHENTICATION_OR_TRANSPORT_FAILURE"
        or terminal.get("reason") != "FIRST_IDENTITY_GET_FAILED"
        or terminal.get("endpoint_attempts") != 1
        or terminal.get("provider_calls") != 0
        or terminal.get("model_calls") != 0
    ):
        raise DiagnosticPreflightError("failed-probe terminal contract drifted")
    events = [
        json.loads(line)
        for line in paths.journal.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    issued = [event for event in events if event.get("event") == "probe_endpoint_issued"]
    if len(issued) != 1 or issued[0] != {
        "event": "probe_endpoint_issued",
        "method": "GET",
        "endpoint": "/v1/models",
        "attempt": 1,
    }:
        raise DiagnosticPreflightError("failed-probe request sequence drifted")
    return digests


def _validate_namespace_fresh(paths: DiagnosticEvidencePaths) -> None:
    """Reject any existing diagnostic namespace before custody creation."""
    if paths.root.exists() or any(path.exists() for path in paths.all_paths()):
        raise DiagnosticPreflightError("diagnostic evidence namespace is not fresh")


def _static_preflight(
    repo_root: Path,
    failed_probe_tooling_root: Path,
    diagnostic_tooling_root: Path,
    authorization: DiagnosticAuthorization,
    paths: DiagnosticEvidencePaths,
    *,
    static_checker: Callable[[Path, Path, Path, DiagnosticAuthorization], Mapping[str, Any]]
    | None = None,
) -> dict[str, Any]:
    """Repeat all Stage-1 checks without network activity."""
    if static_checker is not None:
        return dict(
            static_checker(
                repo_root,
                failed_probe_tooling_root,
                diagnostic_tooling_root,
                authorization,
            )
        )
    roots = {
        "scientific": repo_root.resolve(),
        "failed_probe_tooling": failed_probe_tooling_root.resolve(),
        "diagnostic_tooling": diagnostic_tooling_root.resolve(),
    }
    if len(roots.values()) != len(set(roots.values())):
        raise DiagnosticPreflightError("worktrees are not distinct")
    for root in roots.values():
        if _git(root, "status", "--porcelain"):
            raise DiagnosticPreflightError("a required worktree is not clean")
    if _git(repo_root, "rev-parse", "HEAD") != authorization.scientific_checkpoint:
        raise DiagnosticPreflightError("scientific checkpoint mismatch")
    if (
        _git(failed_probe_tooling_root, "rev-parse", "HEAD")
        != authorization.failed_probe_tooling_checkpoint
    ):
        raise DiagnosticPreflightError("failed-probe tooling checkpoint mismatch")
    if (
        _git(diagnostic_tooling_root, "rev-parse", "HEAD")
        != authorization.diagnostic_tooling_checkpoint
    ):
        raise DiagnosticPreflightError("diagnostic tooling checkpoint mismatch")
    project_config = load_project_config(repo_root)
    d5._validate_project_config(project_config)
    if project_config.fingerprint_sha256 != authorization.project_config_fingerprint_sha256:
        raise DiagnosticPreflightError("project configuration fingerprint mismatch")
    if project_config.model_catalog_url != authorization.target_url:
        raise DiagnosticPreflightError("exact model-catalog URL mismatch")
    parsed = urlsplit(authorization.target_url)
    if parsed.query or parsed.fragment or parsed.path != "/v1/models":
        raise DiagnosticPreflightError("target URL construction mismatch")
    if authorization.credential_resolution != EXPECTED_CREDENTIAL_RESOLUTION:
        raise DiagnosticPreflightError("credential resolution mismatch")
    _verify_failed_probe_join(repo_root, authorization)
    return {
        "status": "PASS",
        "scientific_checkpoint": authorization.scientific_checkpoint,
        "failed_probe_tooling_checkpoint": authorization.failed_probe_tooling_checkpoint,
        "diagnostic_tooling_checkpoint": authorization.diagnostic_tooling_checkpoint,
        "project_config_fingerprint_sha256": project_config.project_config_fingerprint_sha256
        if hasattr(project_config, "project_config_fingerprint_sha256")
        else project_config.fingerprint_sha256,
        "target_url": authorization.target_url,
        "failed_probe_authorization_id": authorization.failed_probe_authorization_id,
    }


class DiagnosticCustody:
    """Durable one-shot custody for one optional network request."""

    def __init__(
        self, paths: DiagnosticEvidencePaths, authorization: DiagnosticAuthorization
    ) -> None:
        """Initialize custody for one explicit diagnostic authority."""
        self.paths = paths
        self.authorization = authorization

    @classmethod
    def create(
        cls, paths: DiagnosticEvidencePaths, authorization: DiagnosticAuthorization
    ) -> DiagnosticCustody:
        """Create fresh custody before preflight and credential resolution."""
        _validate_namespace_fresh(paths)
        paths.root.mkdir(parents=True)
        _atomic_json(
            paths.state,
            {
                "authorization_id": authorization.authorization_id,
                "scientific_checkpoint": authorization.scientific_checkpoint,
                "failed_probe_tooling_checkpoint": authorization.failed_probe_tooling_checkpoint,
                "diagnostic_tooling_checkpoint": authorization.diagnostic_tooling_checkpoint,
                "target_url": authorization.target_url,
                "credential_resolution": authorization.credential_resolution,
                "status": "READY",
                "consumed": False,
                "endpoint_attempts": 0,
                "provider_calls": 0,
                "model_calls": 0,
            },
            exclusive=True,
        )
        _append_event(paths.journal, {"event": "diagnostic_namespace_created"}, exclusive=True)
        return cls(paths, authorization)

    def _state(self) -> dict[str, Any]:
        return dict(_load_json(self.paths.state))

    def preflight_passed(self, facts: Mapping[str, Any]) -> None:
        """Record the immediate zero-network preflight result."""
        updated = self._state()
        updated["static_preflight"] = facts.get("status")
        _atomic_json(self.paths.state, updated)
        _append_event(self.paths.journal, {"event": "diagnostic_preflight_passed"})

    def issue(self) -> int:
        """Consume authority immediately before the only network request."""
        state = self._state()
        if state.get("status") == "TERMINAL":
            raise DiagnosticToolError("diagnostic authority is terminal")
        if int(state.get("endpoint_attempts", 0)) >= MAX_ENDPOINT_ATTEMPTS:
            raise DiagnosticToolError("second diagnostic request rejected")
        updated = dict(state)
        updated.update({"status": "OBSERVING", "consumed": True, "endpoint_attempts": 1})
        _atomic_json(self.paths.state, updated)
        _append_event(
            self.paths.journal,
            {
                "event": "diagnostic_endpoint_issued",
                "method": "GET",
                "endpoint": "/v1/models",
                "attempt": 1,
            },
        )
        return 1

    def seal(self, terminal: Mapping[str, Any]) -> dict[str, Any]:
        """Seal one immutable terminal and digest summary."""
        if self.paths.terminal.exists() or self.paths.summary.exists():
            raise DiagnosticToolError("diagnostic terminal already exists")
        state = self._state()
        record = {
            **dict(terminal),
            "authorization_id": self.authorization.authorization_id,
            "scientific_checkpoint": self.authorization.scientific_checkpoint,
            "failed_probe_tooling_checkpoint": self.authorization.failed_probe_tooling_checkpoint,
            "diagnostic_tooling_checkpoint": self.authorization.diagnostic_tooling_checkpoint,
            "target_url": self.authorization.target_url,
            "credential_resolution": self.authorization.credential_resolution,
            "auth001_replayed": False,
            "provider_calls": 0,
            "model_calls": 0,
        }
        _atomic_json(self.paths.terminal, record, exclusive=True)
        _append_event(
            self.paths.journal,
            {
                "event": "diagnostic_terminal_sealed",
                "classification": record.get("classification"),
                "endpoint_attempts": state.get("endpoint_attempts", 0),
            },
        )
        final_state = dict(state)
        final_state.update(
            {
                "status": "TERMINAL",
                "outcome": record.get("classification"),
                "reason": record.get("reason"),
            }
        )
        _atomic_json(self.paths.state, final_state)
        summary = {
            "authorization_id": self.authorization.authorization_id,
            "target_url": self.authorization.target_url,
            "classification": record.get("classification"),
            "endpoint_attempts": final_state.get("endpoint_attempts", 0),
            "consumed": final_state.get("consumed", False),
            "auth001_replayed": False,
            "provider_calls": 0,
            "model_calls": 0,
            "state_sha256": _sha256_file(self.paths.state),
            "journal_sha256": _sha256_file(self.paths.journal),
            "terminal_sha256": _sha256_file(self.paths.terminal),
        }
        _atomic_json(self.paths.summary, summary, exclusive=True)
        return record


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Disable urllib redirect following at the handler layer."""

    def redirect_request(
        self,
        request: object,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        """Reject every redirect without issuing a follow-up request."""
        del request, fp, code, msg, headers, newurl


def _default_endpoint_request(url: str, api_key: str) -> DiagnosticHttpResponse:
    """Issue exactly one request with no redirect or retry behavior."""
    parsed = urlsplit(url)
    if url != TARGET_URL or parsed.query or parsed.fragment:
        raise DiagnosticPreflightError("diagnostic endpoint URL drifted")
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=20.0) as response:
            raw = response.read(MAX_ENDPOINT_RESPONSE_BYTES + 1)
            status = int(response.status)
    except urllib.error.HTTPError as error:
        if error.code in {301, 302, 303, 307, 308}:
            return DiagnosticHttpResponse(
                payload=None, http_status=error.code, redirect_followed=False
            )
        if error.code in {401, 403}:
            return DiagnosticHttpResponse(
                payload=None, http_status=error.code, redirect_followed=False
            )
        return DiagnosticHttpResponse(payload=None, http_status=error.code, redirect_followed=False)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        raise DiagnosticTransportError("tcp_unreachable") from None
    if len(raw) > MAX_ENDPOINT_RESPONSE_BYTES:
        return DiagnosticHttpResponse(
            payload=UnusableJson("response_too_large"),
            http_status=status,
            redirect_followed=False,
        )
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        payload = UnusableJson("invalid_json")
    return DiagnosticHttpResponse(payload=payload, http_status=status, redirect_followed=False)


def _catalog_shape(payload: object) -> str:
    """Classify only the bounded model-catalog JSON shape."""
    if not isinstance(payload, Mapping):
        return "unusable"
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return "unusable"
    if any(not isinstance(item, Mapping) or not isinstance(item.get("id"), str) for item in data):
        return "unusable"
    return "model_catalog_observable"


def _classify_response(response: DiagnosticHttpResponse) -> dict[str, Any]:
    """Map one exact endpoint response to the frozen taxonomy."""
    base = {
        "network_request_issued": True,
        "http_status": response.http_status,
        "redirect_followed": False,
        "endpoint_attempts": 1,
        "provider_calls": 0,
        "model_calls": 0,
    }
    if response.http_status in {401, 403}:
        return {"classification": "HTTP_REACHABLE_AUTH_FAILURE", **base}
    if response.http_status != 200:
        return {"classification": "HTTP_REACHABLE_OTHER_FAILURE", **base}
    if isinstance(response.payload, UnusableJson):
        return {
            "classification": "HTTP_REACHABLE_OTHER_FAILURE",
            "response_shape": response.payload.reason,
            **base,
        }
    shape = _catalog_shape(response.payload)
    if shape != "model_catalog_observable":
        return {
            "classification": "HTTP_REACHABLE_OTHER_FAILURE",
            "response_shape": shape,
            **base,
        }
    return {
        "classification": "ENDPOINT_REACHABLE",
        "response_shape": shape,
        **base,
    }


def run_diagnostic(
    *,
    repo_root: Path,
    failed_probe_tooling_root: Path,
    diagnostic_tooling_root: Path,
    authorization: DiagnosticAuthorization,
    endpoint_request: Callable[[str, str], DiagnosticHttpResponse],
    api_key_loader: Callable[[], str],
    static_checker: Callable[[Path, Path, Path, DiagnosticAuthorization], Mapping[str, Any]]
    | None = None,
) -> dict[str, Any]:
    """Run the zero-or-one-request diagnostic state machine."""
    paths = DiagnosticEvidencePaths(
        _artifact_root(repo_root, authorization.artifact_root),
        authorization.authorization_id,
    )
    custody = DiagnosticCustody.create(paths, authorization)
    try:
        facts = _static_preflight(
            repo_root,
            failed_probe_tooling_root,
            diagnostic_tooling_root,
            authorization,
            paths,
            static_checker=static_checker,
        )
    except DiagnosticPreflightError as error:
        return custody.seal(
            {
                "classification": "LOCAL_PRECONDITION",
                "reason": str(error),
                "network_request_issued": False,
                "http_status": "NOT_REACHED",
                "redirect_followed": False,
                "endpoint_attempts": 0,
                "authority_consumed": False,
            }
        )
    custody.preflight_passed(facts)
    try:
        api_key = api_key_loader()
    except Exception:
        return custody.seal(
            {
                "classification": "LOCAL_PRECONDITION",
                "reason": "CREDENTIAL_UNAVAILABLE",
                "network_request_issued": False,
                "http_status": "NOT_REACHED",
                "redirect_followed": False,
                "endpoint_attempts": 0,
                "authority_consumed": False,
            }
        )
    if not isinstance(api_key, str) or not api_key.strip():
        return custody.seal(
            {
                "classification": "LOCAL_PRECONDITION",
                "reason": "CREDENTIAL_UNAVAILABLE",
                "network_request_issued": False,
                "http_status": "NOT_REACHED",
                "endpoint_attempts": 0,
                "authority_consumed": False,
            }
        )
    custody.issue()
    try:
        response = endpoint_request(TARGET_URL, api_key)
    except DiagnosticTransportError:
        return custody.seal(
            {
                "classification": "TCP_UNREACHABLE",
                "reason": "NORMALIZED_TRANSPORT_FAILURE",
                "network_request_issued": True,
                "http_status": "NOT_RECEIVED",
                "redirect_followed": False,
                "endpoint_attempts": 1,
                "authority_consumed": True,
            }
        )
    result = _classify_response(response)
    result["authority_consumed"] = True
    return custody.seal(result)


def verify_diagnostic_custody(
    repo_root: Path,
    paths: DiagnosticEvidencePaths,
    authorization: DiagnosticAuthorization,
) -> dict[str, str]:
    """Verify one sealed diagnostic and its unchanged failed-probe join."""
    required = paths.all_paths()
    if not all(path.is_file() for path in required):
        raise DiagnosticToolError("diagnostic custody is incomplete")
    state = _load_json(paths.state)
    terminal = _load_json(paths.terminal)
    journal = paths.journal.read_text(encoding="utf-8").splitlines()
    summary = _load_json(paths.summary)
    if state.get("status") != "TERMINAL":
        raise DiagnosticToolError("diagnostic custody is not terminal")
    if any(
        item.get("authorization_id") != paths.authorization_id
        for item in (state, terminal, summary)
    ):
        raise DiagnosticToolError("diagnostic authorization join failed")
    expected_terminal = {
        "authorization_id": authorization.authorization_id,
        "scientific_checkpoint": authorization.scientific_checkpoint,
        "failed_probe_tooling_checkpoint": authorization.failed_probe_tooling_checkpoint,
        "diagnostic_tooling_checkpoint": authorization.diagnostic_tooling_checkpoint,
        "target_url": authorization.target_url,
        "credential_resolution": authorization.credential_resolution,
        "auth001_replayed": False,
        "provider_calls": 0,
        "model_calls": 0,
    }
    if any(terminal.get(key) != value for key, value in expected_terminal.items()):
        raise DiagnosticToolError("diagnostic terminal authority claims drifted")
    if (
        state.get("target_url") != authorization.target_url
        or state.get("credential_resolution") != authorization.credential_resolution
        or state.get("provider_calls") != 0
        or state.get("model_calls") != 0
        or summary.get("target_url") != authorization.target_url
        or summary.get("consumed") != state.get("consumed")
        or summary.get("auth001_replayed") is not False
        or summary.get("provider_calls") != 0
        or summary.get("model_calls") != 0
    ):
        raise DiagnosticToolError("diagnostic custody claims drifted")
    events = [json.loads(line) for line in journal if line.strip()]
    issued = [event for event in events if event.get("event") == "diagnostic_endpoint_issued"]
    attempts = state.get("endpoint_attempts")
    if attempts == 0:
        if state.get("consumed") is not False or issued:
            raise DiagnosticToolError("zero-attempt diagnostic sequence drifted")
        if terminal.get("classification") != "LOCAL_PRECONDITION":
            raise DiagnosticToolError("zero-attempt diagnostic classification drifted")
    elif attempts == 1:
        if state.get("consumed") is not True or len(issued) != 1:
            raise DiagnosticToolError("one-shot diagnostic sequence drifted")
        if issued[0] != {
            "event": "diagnostic_endpoint_issued",
            "method": "GET",
            "endpoint": "/v1/models",
            "attempt": 1,
        }:
            raise DiagnosticToolError("diagnostic request tuple drifted")
        if terminal.get("classification") == "LOCAL_PRECONDITION":
            raise DiagnosticToolError("network diagnostic classification drifted")
    else:
        raise DiagnosticToolError("diagnostic endpoint attempt count drifted")
    _verify_failed_probe_join(repo_root, authorization)
    digests = {
        "state_sha256": _sha256_file(paths.state),
        "journal_sha256": _sha256_file(paths.journal),
        "terminal_sha256": _sha256_file(paths.terminal),
    }
    if any(summary.get(key) != value for key, value in digests.items()):
        raise DiagnosticToolError("diagnostic digest mismatch")
    return digests


def _load_authorization(path: Path) -> DiagnosticAuthorization:
    """Load the explicit diagnostic authority without printing it."""
    return DiagnosticAuthorization.from_mapping(json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    """Run the explicit diagnostic authority."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--failed-probe-tooling-root", type=Path, required=True)
    parser.add_argument("--diagnostic-tooling-root", type=Path, required=True)
    parser.add_argument("--authorization-json", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run_diagnostic(
            repo_root=args.repo_root.resolve(),
            failed_probe_tooling_root=args.failed_probe_tooling_root.resolve(),
            diagnostic_tooling_root=args.diagnostic_tooling_root.resolve(),
            authorization=_load_authorization(args.authorization_json.resolve()),
            endpoint_request=lambda url, token: _default_endpoint_request(url, token),
            api_key_loader=lambda: d4.load_d4_api_key(args.repo_root.resolve()),
        )
    except DiagnosticToolError as error:
        print(json.dumps({"status": "NOT_RUN", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
