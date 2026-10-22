"""Establish D5-5I runtime pins with exactly two metadata observations.

This tool is intentionally separate from the live qualification harness. It
reuses the accepted readiness projections, but has no provider construction or
``/chat/completions`` path. A future, separately authorized invocation may
perform one ``/v1/models`` GET followed by one ``/props`` GET.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts import nlp_d4_live_acceptance as d4
from scripts import nlp_d5_live_semantic_qualification as d5
from wellplot.project_config import load_project_config

TARGET_EXECUTABLE_CHECKPOINT = "fa3bfe59819d9b5e4cac9821b7770d7f4b4b3a0b"
TARGET_SERVER_ORIGIN = "http://192.168.2.141:8888"
TARGET_OPENAI_COMPAT_BASE_URL = f"{TARGET_SERVER_ORIGIN}/v1"
EXPECTED_MODEL = "qwen3.6-35b-a3b"
EXPECTED_STRUCTURED_OUTPUT = "json_schema"
MAX_METADATA_ATTEMPTS = 2
MAX_ENDPOINT_RESPONSE_BYTES = d5.MAX_ENDPOINT_RESPONSE_BYTES

CONTINUITY_FIELDS = (
    "model_catalog",
    "model_path_basename",
    "model_path_fingerprint_sha256",
    "build_info",
    "context_size",
    "total_slots",
    "chat_template_sha256",
)

STATE_SUFFIX = ".state.json"
JOURNAL_SUFFIX = ".journal.jsonl"
TERMINAL_SUFFIX = ".terminal.json"
SUMMARY_SUFFIX = ".summary.json"


class MetadataToolError(RuntimeError):
    """Base error for bounded metadata-tool failures."""


class MetadataStaticPreflightError(MetadataToolError):
    """Raised before any metadata request when custody is invalid."""


class MetadataEndpointError(MetadataToolError):
    """Represent a bounded endpoint failure without retaining a response."""

    def __init__(self, reason: str, *, http_status: int | None = None) -> None:
        """Retain only the bounded failure category and HTTP status."""
        super().__init__(reason)
        self.reason = reason
        self.http_status = http_status


@dataclass(frozen=True, slots=True)
class MetadataAuthorization:
    """Facts needed to establish one fresh runtime-pin evidence namespace."""

    implementation_checkpoint: str
    authorization_id: str
    project_config_fingerprint_sha256: str
    artifact_root: str
    historical_continuity: Mapping[str, Any]
    target_server_origin: str = TARGET_SERVER_ORIGIN
    target_openai_compat_base_url: str = TARGET_OPENAI_COMPAT_BASE_URL
    model: str = EXPECTED_MODEL

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> MetadataAuthorization:
        """Parse explicit metadata authority without deriving its identity."""
        required = {
            "implementation_checkpoint",
            "authorization_id",
            "project_config_fingerprint_sha256",
            "artifact_root",
            "historical_continuity",
        }
        missing = sorted(required - set(value))
        if missing:
            raise MetadataStaticPreflightError(f"metadata authorization is missing: {missing!r}")
        continuity = value["historical_continuity"]
        if not isinstance(continuity, Mapping):
            raise MetadataStaticPreflightError("historical continuity is not a mapping")
        missing_continuity = sorted(set(CONTINUITY_FIELDS) - set(continuity))
        if missing_continuity:
            raise MetadataStaticPreflightError(
                f"historical continuity is missing: {missing_continuity!r}"
            )
        authorization = cls(
            implementation_checkpoint=str(value["implementation_checkpoint"]),
            authorization_id=str(value["authorization_id"]),
            project_config_fingerprint_sha256=str(value["project_config_fingerprint_sha256"]),
            artifact_root=str(value["artifact_root"]),
            historical_continuity=dict(continuity),
            target_server_origin=str(value.get("target_server_origin", TARGET_SERVER_ORIGIN)),
            target_openai_compat_base_url=str(
                value.get("target_openai_compat_base_url", TARGET_OPENAI_COMPAT_BASE_URL)
            ),
            model=str(value.get("model", EXPECTED_MODEL)),
        )
        if authorization.implementation_checkpoint != TARGET_EXECUTABLE_CHECKPOINT:
            raise MetadataStaticPreflightError("metadata executable checkpoint drifted")
        if authorization.target_server_origin != TARGET_SERVER_ORIGIN:
            raise MetadataStaticPreflightError("metadata server origin drifted")
        if authorization.target_openai_compat_base_url != TARGET_OPENAI_COMPAT_BASE_URL:
            raise MetadataStaticPreflightError("metadata OpenAI-compatible base URL drifted")
        if authorization.model != EXPECTED_MODEL:
            raise MetadataStaticPreflightError("metadata model identity drifted")
        if not authorization.authorization_id or not authorization.artifact_root:
            raise MetadataStaticPreflightError("metadata custody identity is missing")
        if Path(authorization.authorization_id).name != authorization.authorization_id:
            raise MetadataStaticPreflightError("metadata authorization ID is not a leaf")
        return authorization


@dataclass(frozen=True, slots=True)
class MetadataEvidencePaths:
    """Collision-sensitive files for one metadata-only authority."""

    root: Path
    authorization_id: str

    @property
    def state(self) -> Path:
        """Return durable consumption state."""
        return self.root / f"{self.authorization_id}{STATE_SUFFIX}"

    @property
    def journal(self) -> Path:
        """Return append-only bounded event custody."""
        return self.root / f"{self.authorization_id}{JOURNAL_SUFFIX}"

    @property
    def terminal(self) -> Path:
        """Return the immutable terminal result."""
        return self.root / f"{self.authorization_id}{TERMINAL_SUFFIX}"

    @property
    def summary(self) -> Path:
        """Return terminal digest summary."""
        return self.root / f"{self.authorization_id}{SUMMARY_SUFFIX}"

    def all_paths(self) -> tuple[Path, ...]:
        """Return all files that must be absent in a fresh namespace."""
        return self.state, self.journal, self.terminal, self.summary


def _atomic_json(path: Path, value: Mapping[str, Any], *, exclusive: bool = False) -> None:
    """Write one JSON artifact atomically without exposing secrets."""
    if not d5.evidence_is_redacted(value):
        raise MetadataToolError("metadata evidence redaction failed")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if exclusive and path.exists():
        temporary.unlink(missing_ok=True)
        raise MetadataToolError(f"metadata artifact already exists: {path.name}")
    os.replace(temporary, path)


def _append_event(path: Path, event: Mapping[str, Any], *, exclusive: bool = False) -> None:
    """Append one redacted metadata event."""
    if not d5.evidence_is_redacted(event):
        raise MetadataToolError("metadata journal redaction failed")
    if exclusive and path.exists():
        raise MetadataToolError("metadata journal already exists")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")


def _sha256_file(path: Path) -> str:
    """Hash one sealed metadata artifact."""
    return d5._sha256_file(path)


def _git(repo_root: Path, *arguments: str) -> str:
    """Read one Git fact without changing the checkout."""
    return subprocess.check_output(["git", *arguments], cwd=repo_root, text=True).strip()


def _artifact_root(repo_root: Path, authorization: MetadataAuthorization) -> Path:
    """Resolve the authority's fresh evidence namespace."""
    configured = Path(authorization.artifact_root).expanduser()
    return (configured if configured.is_absolute() else repo_root / configured).resolve()


def _static_preflight(
    repo_root: Path,
    authorization: MetadataAuthorization,
    paths: MetadataEvidencePaths,
    *,
    static_checker: Callable[[Path, MetadataAuthorization, MetadataEvidencePaths], dict[str, Any]]
    | None = None,
) -> dict[str, Any]:
    """Verify checkout/configuration/custody before loading a credential."""
    if static_checker is not None:
        return static_checker(repo_root, authorization, paths)
    if _git(repo_root, "rev-parse", "HEAD") != authorization.implementation_checkpoint:
        raise MetadataStaticPreflightError("implementation checkpoint mismatch")
    if _git(repo_root, "status", "--porcelain"):
        raise MetadataStaticPreflightError("working tree is not clean")
    project_config = load_project_config(repo_root)
    d5._validate_project_config(project_config)
    if project_config.fingerprint_sha256 != authorization.project_config_fingerprint_sha256:
        raise MetadataStaticPreflightError("project configuration fingerprint mismatch")
    if project_config.server_origin != authorization.target_server_origin:
        raise MetadataStaticPreflightError("configured server origin mismatch")
    if project_config.openai_compat_base_url != authorization.target_openai_compat_base_url:
        raise MetadataStaticPreflightError("configured OpenAI-compatible base URL mismatch")
    if project_config.provider.model != authorization.model:
        raise MetadataStaticPreflightError("configured model mismatch")
    if project_config.runtime.structured_output != EXPECTED_STRUCTURED_OUTPUT:
        raise MetadataStaticPreflightError("structured-output contract drifted")
    if paths.root.exists() or any(path.exists() for path in paths.all_paths()):
        raise MetadataStaticPreflightError("metadata evidence namespace is not fresh")
    attestation = d5._run_static_attestation(repo_root)
    return {
        "status": "PASS",
        "implementation_checkpoint": authorization.implementation_checkpoint,
        "project_config_fingerprint_sha256": project_config.fingerprint_sha256,
        "server_origin": project_config.server_origin,
        "openai_compat_base_url": project_config.openai_compat_base_url,
        "model": project_config.provider.model,
        "structured_output_contract": EXPECTED_STRUCTURED_OUTPUT,
        "single_engine_attestation": attestation,
    }


@dataclass(slots=True)
class MetadataCustody:
    """Durable one-shot metadata consumption and terminal evidence."""

    paths: MetadataEvidencePaths
    authorization: MetadataAuthorization

    @classmethod
    def create(
        cls,
        paths: MetadataEvidencePaths,
        authorization: MetadataAuthorization,
        static_facts: Mapping[str, Any],
    ) -> MetadataCustody:
        """Create a fresh namespace before any credential-bearing request."""
        if paths.root.exists() or any(path.exists() for path in paths.all_paths()):
            raise MetadataStaticPreflightError("metadata evidence namespace is not fresh")
        paths.root.mkdir(parents=True)
        _atomic_json(
            paths.state,
            {
                "authorization_id": authorization.authorization_id,
                "implementation_checkpoint": authorization.implementation_checkpoint,
                "status": "READY",
                "consumed": False,
                "endpoint_attempts": 0,
                "provider_calls": 0,
                "model_calls": 0,
                "static_preflight": static_facts.get("status"),
            },
            exclusive=True,
        )
        _append_event(
            paths.journal,
            {"event": "metadata_preflight_passed", "endpoint_attempts": 0},
            exclusive=True,
        )
        return cls(paths=paths, authorization=authorization)

    def _state(self) -> dict[str, Any]:
        """Read current durable state."""
        return json.loads(self.paths.state.read_text(encoding="utf-8"))

    def issue(self, endpoint: str) -> int:
        """Consume and durably record one endpoint attempt before issuance."""
        state = self._state()
        attempts = int(state.get("endpoint_attempts", 0))
        if state.get("status") == "TERMINAL":
            raise MetadataToolError("metadata authority is terminal")
        if attempts >= MAX_METADATA_ATTEMPTS:
            raise MetadataToolError("third metadata endpoint attempt rejected")
        next_attempt = attempts + 1
        updated = dict(state)
        updated.update(
            {
                "status": "OBSERVING",
                "consumed": True,
                "endpoint_attempts": next_attempt,
            }
        )
        _atomic_json(self.paths.state, updated)
        _append_event(
            self.paths.journal,
            {
                "event": "metadata_get_issued",
                "endpoint": endpoint,
                "attempt": next_attempt,
            },
        )
        return next_attempt

    def seal(self, terminal: Mapping[str, Any]) -> dict[str, Any]:
        """Write one immutable terminal record and digest summary."""
        if self.paths.terminal.exists() or self.paths.summary.exists():
            raise MetadataToolError("metadata terminal already exists")
        state = self._state()
        terminal_record = {
            "authorization_id": self.authorization.authorization_id,
            "implementation_checkpoint": self.authorization.implementation_checkpoint,
            "provider_calls": 0,
            "model_calls": 0,
            **dict(terminal),
        }
        _atomic_json(self.paths.terminal, terminal_record, exclusive=True)
        _append_event(
            self.paths.journal,
            {
                "event": "metadata_terminal_sealed",
                "outcome": terminal_record.get("outcome"),
                "endpoint_attempts": state.get("endpoint_attempts", 0),
            },
        )
        final_state = dict(state)
        final_state.update(
            {
                "status": "TERMINAL",
                "outcome": terminal_record.get("outcome"),
                "reason": terminal_record.get("reason"),
            }
        )
        _atomic_json(self.paths.state, final_state)
        summary = {
            "authorization_id": self.authorization.authorization_id,
            "outcome": terminal_record.get("outcome"),
            "endpoint_attempts": final_state.get("endpoint_attempts", 0),
            "provider_calls": 0,
            "model_calls": 0,
            "state_sha256": _sha256_file(self.paths.state),
            "journal_sha256": _sha256_file(self.paths.journal),
            "terminal_sha256": _sha256_file(self.paths.terminal),
        }
        _atomic_json(self.paths.summary, summary, exclusive=True)
        return terminal_record


def _continuity_mismatches(
    observed: Mapping[str, Any], expected: Mapping[str, Any]
) -> tuple[str, ...]:
    """Compare projected values without retaining unbounded endpoint data."""
    mismatches = []
    for field in expected:
        expected_value = expected[field]
        observed_value = observed[field]
        if isinstance(observed_value, tuple):
            observed_value = list(observed_value)
        if observed_value != expected_value:
            mismatches.append(field)
    return tuple(mismatches)


def _endpoint_failure(error: BaseException) -> tuple[str, int | None]:
    """Classify endpoint failure without exposing exception details."""
    if isinstance(error, d5.D5ReadinessError):
        if error.http_status in {401, 403} or error.reason == "endpoint_authentication_failed":
            return "AUTHENTICATION_FAILURE", error.http_status
        if error.reason == "endpoint_identity_mismatch":
            return "MISMATCH", error.http_status
        return "TRANSPORT_FAILURE", error.http_status
    if isinstance(error, MetadataEndpointError):
        if error.http_status in {401, 403} or error.reason == "endpoint_authentication_failed":
            return "AUTHENTICATION_FAILURE", error.http_status
        if error.reason == "endpoint_identity_mismatch":
            return "MISMATCH", error.http_status
        return "TRANSPORT_FAILURE", error.http_status
    return "TRANSPORT_FAILURE", None


def _terminal_for_endpoint_failure(
    outcome: str,
    reason: str,
    attempts: int,
    http_status: int | None,
) -> dict[str, Any]:
    """Build bounded endpoint failure evidence."""
    result: dict[str, Any] = {
        "outcome": outcome,
        "reason": reason,
        "endpoint_attempts": attempts,
        "generation_calls": 0,
    }
    if http_status is not None:
        result["http_status"] = http_status
    return result


def _default_endpoint_get(url: str, api_key: str) -> object:
    """Perform one bounded credential-bearing metadata GET only."""
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20.0) as response:
            if response.geturl() != url:
                raise MetadataEndpointError("endpoint_identity_mismatch")
            body = response.read(MAX_ENDPOINT_RESPONSE_BYTES + 1)
    except MetadataEndpointError:
        raise
    except urllib.error.HTTPError as error:
        reason = (
            "endpoint_authentication_failed" if error.code in {401, 403} else "endpoint_http_error"
        )
        raise MetadataEndpointError(reason, http_status=error.code) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
        del error
        raise MetadataEndpointError("endpoint_transport_error") from None
    if len(body) > MAX_ENDPOINT_RESPONSE_BYTES:
        raise MetadataEndpointError("endpoint_identity_mismatch")
    try:
        return json.loads(body)
    except (TypeError, ValueError):
        raise MetadataEndpointError("endpoint_identity_mismatch") from None


def establish_runtime_pins(
    *,
    repo_root: Path,
    authorization: MetadataAuthorization,
    endpoint_get: Callable[[str, str], object] = _default_endpoint_get,
    api_key_loader: Callable[[], str] | None = None,
    static_checker: Callable[[Path, MetadataAuthorization, MetadataEvidencePaths], dict[str, Any]]
    | None = None,
) -> dict[str, Any]:
    """Run the one-shot two-GET metadata qualification."""
    root = _artifact_root(repo_root, authorization)
    paths = MetadataEvidencePaths(root, authorization.authorization_id)
    static = _static_preflight(
        repo_root,
        authorization,
        paths,
        static_checker=static_checker,
    )
    custody = MetadataCustody.create(paths, authorization, static)
    load_key = api_key_loader or (lambda: d4.load_d4_api_key(repo_root))
    try:
        token = load_key()
    except Exception:
        return custody.seal(
            {
                "outcome": "AUTHENTICATION_FAILURE",
                "reason": "CREDENTIAL_UNAVAILABLE",
                "endpoint_attempts": 0,
            }
        )
    if not isinstance(token, str) or not token.strip():
        return custody.seal(
            {
                "outcome": "AUTHENTICATION_FAILURE",
                "reason": "CREDENTIAL_UNAVAILABLE",
                "endpoint_attempts": 0,
            }
        )

    try:
        first_attempt = custody.issue("/v1/models")
        catalog_payload = endpoint_get(
            load_project_config(repo_root).model_catalog_url,
            token,
        )
    except Exception as error:
        outcome, status = _endpoint_failure(error)
        return custody.seal(
            _terminal_for_endpoint_failure(outcome, "FIRST_GET_FAILED", first_attempt, status)
        )
    try:
        model_catalog = d5._project_model_catalog(catalog_payload, "")
    except d5.D5ReadinessError:
        return custody.seal(
            {
                "outcome": "INCOMPLETE_PROPS",
                "reason": "MODEL_CATALOG_UNAVAILABLE",
                "endpoint_attempts": first_attempt,
                "generation_calls": 0,
            }
        )
    observed_catalog = {"model_catalog": model_catalog}
    catalog_mismatches = _continuity_mismatches(
        observed_catalog,
        {"model_catalog": authorization.historical_continuity["model_catalog"]},
    )
    if model_catalog != (authorization.model,) or catalog_mismatches:
        return custody.seal(
            {
                "outcome": "MISMATCH",
                "reason": "HISTORICAL_IDENTITY_MISMATCH",
                "mismatched_fields": ["model_catalog"],
                "observed_model_catalog": list(model_catalog),
                "endpoint_attempts": first_attempt,
                "generation_calls": 0,
            }
        )

    try:
        second_attempt = custody.issue("/props")
        props_payload = endpoint_get(load_project_config(repo_root).props_url, token)
    except Exception as error:
        outcome, status = _endpoint_failure(error)
        return custody.seal(
            _terminal_for_endpoint_failure(outcome, "SECOND_GET_FAILED", second_attempt, status)
        )
    try:
        props = d5._project_props(props_payload, EXPECTED_STRUCTURED_OUTPUT)
    except d5.D5ReadinessError:
        return custody.seal(
            {
                "outcome": "INCOMPLETE_PROPS",
                "reason": "EXTENDED_RUNTIME_IDENTITY_UNAVAILABLE",
                "endpoint_attempts": second_attempt,
                "generation_calls": 0,
            }
        )
    observed = {"model_catalog": model_catalog, **props}
    mismatches = _continuity_mismatches(observed, authorization.historical_continuity)
    if mismatches:
        return custody.seal(
            {
                "outcome": "MISMATCH",
                "reason": "HISTORICAL_IDENTITY_MISMATCH",
                "mismatched_fields": list(mismatches),
                "observed_runtime_identity": observed,
                "endpoint_attempts": second_attempt,
                "generation_calls": 0,
            }
        )
    return custody.seal(
        {
            "outcome": "SUCCESS",
            "reason": "RUNTIME_PINS_ESTABLISHED",
            "historical_overlap": "EXACT_MATCH",
            "extended_pins": observed,
            "thinking_off": "STATIC_REQUEST_CONTRACT",
            "compatibility_review": "REQUIRED_BEFORE_GATE_B",
            "endpoint_attempts": second_attempt,
            "generation_calls": 0,
        }
    )


def verify_metadata_custody(paths: MetadataEvidencePaths) -> dict[str, str]:
    """Verify terminal state, redaction, and digest joins without mutation."""
    required = (paths.state, paths.journal, paths.terminal, paths.summary)
    if not all(path.is_file() for path in required):
        raise MetadataToolError("metadata custody artifact set is incomplete")
    state = json.loads(paths.state.read_text(encoding="utf-8"))
    terminal = json.loads(paths.terminal.read_text(encoding="utf-8"))
    summary = json.loads(paths.summary.read_text(encoding="utf-8"))
    if state.get("status") != "TERMINAL":
        raise MetadataToolError("metadata state is not terminal")
    if not all(d5.evidence_is_redacted(item) for item in (state, terminal, summary)):
        raise MetadataToolError("metadata custody redaction failed")
    if state.get("authorization_id") != paths.authorization_id:
        raise MetadataToolError("metadata state authorization mismatch")
    if terminal.get("authorization_id") != paths.authorization_id:
        raise MetadataToolError("metadata terminal authorization mismatch")
    if summary.get("authorization_id") != paths.authorization_id:
        raise MetadataToolError("metadata summary authorization mismatch")
    digests = {
        "state_sha256": _sha256_file(paths.state),
        "journal_sha256": _sha256_file(paths.journal),
        "terminal_sha256": _sha256_file(paths.terminal),
    }
    if any(summary.get(key) != value for key, value in digests.items()):
        raise MetadataToolError("metadata custody digest mismatch")
    return digests


def _load_authorization(path: Path) -> MetadataAuthorization:
    """Load a metadata authority without printing its contents."""
    return MetadataAuthorization.from_mapping(json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    """Run the explicitly supplied metadata-only authority."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--authorization-json", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = establish_runtime_pins(
            repo_root=args.repo_root.resolve(),
            authorization=_load_authorization(args.authorization_json.resolve()),
        )
    except MetadataToolError as error:
        print(json.dumps({"status": "NOT_RUN", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
