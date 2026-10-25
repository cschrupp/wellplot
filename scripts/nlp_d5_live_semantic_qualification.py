"""Provider-free D5-4 live semantic qualification harness.

This module owns only the D5-4 orchestration and evidence boundary. It reuses
the accepted D4 cases, custody helpers, deterministic graders, and canonical
Direct Notebook adapter; it never creates a provider or performs network I/O
unless a future, separately authorized live runner supplies those operations.
"""

from __future__ import annotations

import argparse
import asyncio
import errno
import hashlib
import importlib.metadata
import inspect
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from scripts import nlp_d4_live_acceptance as d4
from wellplot.project_config import ProjectConfig, load_project_config

D5_EXPERIMENT_VERSION = "WELLPLOT-NLP-D5-5I"
D5_DESIGN_CHECKPOINT = "1658c1593330620501baa4a551b965fa209cc95b"
D5_ENGINE_CHECKPOINT = "51fd23fe18ca77c067b0cdf702f88a57ba4c457d"
D5I_ACCEPTED_H_IMPLEMENTATION_CHECKPOINT = "e72e726b7f52c1975d862980543cd3f217ee6aa8"
EXPECTED_PROVIDER = "openai_compat"
EXPECTED_MODEL = "qwen3.6-35b-a3b"
EXPECTED_OPENAI_VERSION = "2.34.0"
EXPECTED_SDK_MAX_RETRIES = 2
EXPECTED_TIMEOUT_SECONDS = 900.0
EXPECTED_CONCURRENCY = 1
EXPECTED_STRUCTURED_OUTPUT = "json_schema"
MAX_LOGICAL_CALLS = 45
MAX_PHYSICAL_ATTEMPTS = 135
MAX_ROLE_LOGICAL_CALLS = 2
ROLE_LOGICAL_CALL_LIMITS = {
    "planner": MAX_ROLE_LOGICAL_CALLS,
    "report_worker": MAX_ROLE_LOGICAL_CALLS,
    "section_worker": MAX_ROLE_LOGICAL_CALLS,
}
MAX_ENDPOINT_RESPONSE_BYTES = 1_048_576
THINKING_CONTROL_MECHANISM = "chat_template_kwargs.enable_thinking"
THINKING_CONTROL_OPTIONS_SHA256 = "220b99e47feb82851cab428f86b8fe977ae7c605400d421a91e99d4a35ec9c26"
FROZEN_TURN_IDS = (
    "D4-C01:C01",
    "D4-L01:T1",
    "D4-L01:T2",
    "D4-L01:T3",
    "D4-L01:T4",
    "D4-L02:T1",
    "D4-L02:T2",
    "D4-L03:C01",
    "D4-L04:C01",
)
FROZEN_SOURCE_SHA256 = {
    d4.SOURCE_RELATIVE.as_posix(): d4.SOURCE_SHA256,
    "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis": (
        "3ceb9100fd654d710155672a50a9e0f24ce9705db6ef8e424140f29bd02131f7"
    ),
    "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis": (
        "a4a2e91b495172079fc47bc2e9c936f0ab60c9845bbed8e65bf56555a5e82640"
    ),
}
DECODER_POLICY = {
    "planner": {"temperature": 0.0, "max_output_tokens": None},
    "report_worker": {"temperature": None, "max_output_tokens": None},
    "section_worker": {"temperature": None, "max_output_tokens": None},
    "all_roles": {
        "top_p": "ABSENT",
        "top_k": "ABSENT",
        "seed": "ABSENT",
        "max_tokens": "ABSENT",
        "max_completion_tokens": "ABSENT",
        "model_substitution": "FORBIDDEN",
    },
}
STATE_SUFFIX = ".state.json"
JOURNAL_SUFFIX = ".journal.jsonl"
TERMINAL_SUFFIX = ".terminal.json"
SUMMARY_SUFFIX = ".summary.json"
EVIDENCE_SUFFIX = ".evidence.jsonl"
MODEL_IO_SUFFIX = ".model-io.jsonl"

D5I_SCIENTIFIC_TERMINALS = frozenset(
    {
        "PASS",
        "FAIL / RESIDUAL_SEMANTIC",
        "FAIL / CONTRACT_OR_INPUT",
        "INCONCLUSIVE / PROVIDER",
        "INCONCLUSIVE / HARNESS",
    }
)
D5I_FIRST_DIVERGENCES = frozenset(
    {
        "NONE",
        "PROVIDER_OR_STRUCTURED",
        "PLANNER_STRUCTURAL",
        "SEMANTIC",
        "TARGET_GROUNDING",
        "SOURCE_CHANNEL_GROUNDING",
        "CAPABILITY",
        "CORRECTION_PRESERVATION",
        "HOST_EXECUTION",
        "PERSISTENCE_RELOAD_RENDER",
        "DETERMINISTIC_GRADING",
        "HARNESS",
    }
)
D5I_DIMENSIONS = (
    "provider_structured",
    "planner_structural",
    "semantic",
    "target_grounding",
    "source_channel_grounding",
    "capability",
    "correction_preservation",
    "safe_negative",
    "mutation",
    "persistence_reload_render",
    "deterministic_grading",
)

SECRET_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "authorization_headers",
        "credentials",
        "environment_dump",
        "raw_provider_response",
        "raw_props_response",
        "raw_models_response",
        "raw_generated_program",
        "raw_structured_payload",
        "raw_prompt",
        "prompt_text",
        "hidden_reasoning",
        "absolute_model_path",
    }
)
SECRET_MARKERS = (
    "bearer ",
    "api_key",
    "openai_api_key",
    "authorization:",
    "sk-proj-",
)


class D5HarnessError(RuntimeError):
    """Base error for bounded D5-4 harness failures."""


class D5StaticPreflightError(D5HarnessError):
    """Raised before readiness when static custody is invalid."""


class D5ReadinessError(D5HarnessError):
    """Raised when the two-observation operational readiness contract fails."""

    def __init__(
        self,
        reason: str,
        endpoint_calls: int = 0,
        *,
        http_status: int | None = None,
        mismatched_fields: Sequence[str] = (),
    ) -> None:
        """Retain a bounded reason and truthful endpoint call count."""
        super().__init__(reason)
        self.reason = reason
        self.endpoint_calls = endpoint_calls
        self.http_status = http_status
        self.mismatched_fields = tuple(sorted(set(mismatched_fields)))


class D5CallCapExceeded(D5HarnessError):
    """Raised before logical call 46 is delegated."""


class D5StructuredOutputRejected(D5HarnessError):
    """Raised when the first measured endpoint rejects frozen response_format."""


class D5TransportFailure(D5HarnessError):
    """Raised for a post-STARTED transport or runtime failure."""


class D5ProductionFailure(D5HarnessError):
    """Raised when deterministic WellPlot execution fails."""


class D5ProcessInterruption(D5HarnessError):
    """Represent an interruption after STARTED without exposing process details."""


def _thinking_control_options() -> dict[str, object]:
    """Return the one frozen request-level thinking control."""
    return {"chat_template_kwargs": {"enable_thinking": False}}


TERMINAL_DECISIONS = frozenset({"PASS", "FAIL", "INCONCLUSIVE", "ARCHITECTURAL_ESCALATION"})


@dataclass(frozen=True, slots=True)
class D5Authorization:
    """External facts required to qualify one exact harness checkout."""

    implementation_checkpoint: str
    authorization_id: str = ""
    campaign_id: str = ""
    project_config_fingerprint_sha256: str = ""
    accepted_d5_engine_checkpoint: str = D5_ENGINE_CHECKPOINT
    accepted_d5_design_checkpoint: str = D5_DESIGN_CHECKPOINT
    accepted_h_implementation_checkpoint: str = D5I_ACCEPTED_H_IMPLEMENTATION_CHECKPOINT
    provider: str = EXPECTED_PROVIDER
    model: str = EXPECTED_MODEL
    endpoint_identity: Mapping[str, Any] = field(default_factory=dict)
    source_sha256: Mapping[str, str] = field(default_factory=lambda: dict(FROZEN_SOURCE_SHA256))
    cases_sha256: str = d4.FROZEN_CASES_SHA256
    gold_sha256: str = d4.FROZEN_GOLD_SHA256
    uv_lock_sha256: str = d4.FROZEN_UV_LOCK_SHA256
    production_component_sha256: Mapping[str, str] = field(
        default_factory=lambda: dict(d4.FROZEN_PRODUCTION_COMPONENT_SHA256)
    )
    minimum_context_size: int = 0
    runtime_defaults_sha256: str = ""
    thinking_off: bool = True
    thinking_control_options: Mapping[str, object] = field(
        default_factory=_thinking_control_options
    )
    thinking_control_options_sha256: str = THINKING_CONTROL_OPTIONS_SHA256
    structured_output_contract: str = "json_schema"
    sdk_version: str = EXPECTED_OPENAI_VERSION
    sdk_max_retries: int = EXPECTED_SDK_MAX_RETRIES
    artifact_root: str = "workspace/evaluations/d5-4-live-qualification"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> D5Authorization:
        """Parse required authorization facts without deriving them locally."""
        required = {
            "implementation_checkpoint",
            "authorization_id",
            "campaign_id",
            "project_config_fingerprint_sha256",
        }
        missing = required - set(value)
        if missing:
            raise D5StaticPreflightError(f"authorization is missing: {sorted(missing)!r}")
        control_fields = {
            "thinking_off",
            "thinking_control_options",
            "thinking_control_options_sha256",
        }
        missing_control = control_fields - set(value)
        if missing_control:
            raise D5StaticPreflightError(
                f"authorization is missing thinking control: {sorted(missing_control)!r}"
            )
        if value["thinking_off"] is not True:
            raise D5StaticPreflightError("thinking_off must be the literal boolean true")
        options = value["thinking_control_options"]
        if not isinstance(options, Mapping) or dict(options) != _thinking_control_options():
            raise D5StaticPreflightError("thinking-off request control drifted")
        digest = value["thinking_control_options_sha256"]
        if digest != THINKING_CONTROL_OPTIONS_SHA256:
            raise D5StaticPreflightError("thinking-off request control digest drifted")
        return cls(
            implementation_checkpoint=str(value["implementation_checkpoint"]),
            authorization_id=str(value["authorization_id"]),
            campaign_id=str(value["campaign_id"]),
            project_config_fingerprint_sha256=str(value["project_config_fingerprint_sha256"]),
            accepted_d5_engine_checkpoint=str(
                value.get("accepted_d5_engine_checkpoint", D5_ENGINE_CHECKPOINT)
            ),
            accepted_d5_design_checkpoint=str(
                value.get("accepted_d5_design_checkpoint", D5_DESIGN_CHECKPOINT)
            ),
            accepted_h_implementation_checkpoint=str(
                value.get(
                    "accepted_h_implementation_checkpoint",
                    D5I_ACCEPTED_H_IMPLEMENTATION_CHECKPOINT,
                )
            ),
            provider=str(value.get("provider", EXPECTED_PROVIDER)),
            model=str(value.get("model", EXPECTED_MODEL)),
            endpoint_identity=dict(value.get("endpoint_identity", {})),
            source_sha256=dict(value.get("source_sha256", FROZEN_SOURCE_SHA256)),
            cases_sha256=str(value.get("cases_sha256", d4.FROZEN_CASES_SHA256)),
            gold_sha256=str(value.get("gold_sha256", d4.FROZEN_GOLD_SHA256)),
            uv_lock_sha256=str(value.get("uv_lock_sha256", d4.FROZEN_UV_LOCK_SHA256)),
            production_component_sha256=dict(
                value.get(
                    "production_component_sha256",
                    d4.FROZEN_PRODUCTION_COMPONENT_SHA256,
                )
            ),
            minimum_context_size=int(value.get("minimum_context_size", 0)),
            runtime_defaults_sha256=str(value.get("runtime_defaults_sha256", "")),
            thinking_off=value["thinking_off"],
            thinking_control_options=dict(options),
            thinking_control_options_sha256=digest,
            structured_output_contract=str(value.get("structured_output_contract", "json_schema")),
            sdk_version=str(value.get("sdk_version", EXPECTED_OPENAI_VERSION)),
            sdk_max_retries=int(value.get("sdk_max_retries", EXPECTED_SDK_MAX_RETRIES)),
            artifact_root=str(
                value.get("artifact_root", "workspace/evaluations/d5-4-live-qualification")
            ),
        )


def _authorized_artifact_root(repo_root: Path, authorization: D5Authorization) -> Path:
    """Resolve the one artifact namespace allowed by external authorization."""
    configured = Path(authorization.artifact_root).expanduser()
    return (configured if configured.is_absolute() else repo_root / configured).resolve()


@dataclass(frozen=True, slots=True)
class D5ReadinessProjection:
    """Sanitized runtime identity and declared structured-output contract."""

    model_catalog: tuple[str, ...]
    model_path_basename: str
    model_path_fingerprint_sha256: str
    context_size: int
    build_info: str
    total_slots: int
    chat_template_sha256: str
    runtime_defaults_sha256: str
    thinking_off: bool
    structured_output_contract: str
    gguf_byte_identity: str = "NOT_AVAILABLE"

    def as_dict(self) -> dict[str, Any]:
        """Return the only runtime fields allowed into evidence."""
        return {
            "model_catalog": list(self.model_catalog),
            "model_path_basename": self.model_path_basename,
            "model_path_fingerprint_sha256": self.model_path_fingerprint_sha256,
            "context_size": self.context_size,
            "build_info": self.build_info,
            "total_slots": self.total_slots,
            "chat_template_sha256": self.chat_template_sha256,
            "runtime_defaults_sha256": self.runtime_defaults_sha256,
            "thinking_off": self.thinking_off,
            "structured_output_contract": self.structured_output_contract,
            "gguf_byte_identity": self.gguf_byte_identity,
        }


class D5ReadinessProjectionProtocol(Protocol):
    """Sanitized readiness projection accepted by shared campaign custody."""

    def as_dict(self) -> dict[str, Any]:
        """Return redacted readiness evidence."""
        ...


def _sha256_json(value: object) -> str:
    """Hash a deterministic JSON projection."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validated_thinking_control_options(
    request_options: Mapping[str, object] | None,
) -> dict[str, object]:
    """Require the exact frozen request control and return an isolated copy."""
    if request_options is None:
        raise D5StaticPreflightError("thinking-off request control is missing")
    expected = _thinking_control_options()
    candidate = dict(request_options)
    if candidate != expected or _sha256_json(candidate) != THINKING_CONTROL_OPTIONS_SHA256:
        raise D5StaticPreflightError("thinking-off request control drifted")
    return json.loads(json.dumps(expected, sort_keys=True, separators=(",", ":")))


def _git(repo_root: Path, *args: str) -> str:
    """Run one read-only Git query in the target checkout."""
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True).strip()


def _sha256_file(path: Path) -> str:
    """Hash one local file without retaining its contents."""
    return d4.sha256_file(path)


def _assert_hash(path: Path, expected: str, label: str) -> None:
    """Require one immutable custody hash."""
    if not path.is_file() or _sha256_file(path) != expected:
        raise D5StaticPreflightError(f"{label} custody drifted")


def _validate_project_config(project_config: ProjectConfig) -> None:
    """Require the checked-in config to match the frozen D5 runtime contract."""
    if project_config.provider.name != EXPECTED_PROVIDER:
        raise D5StaticPreflightError("project provider contract drifted")
    if project_config.provider.model != EXPECTED_MODEL:
        raise D5StaticPreflightError("project model contract drifted")
    if project_config.provider.timeout_seconds != EXPECTED_TIMEOUT_SECONDS:
        raise D5StaticPreflightError("project timeout contract drifted")
    if project_config.provider.max_retries != EXPECTED_SDK_MAX_RETRIES:
        raise D5StaticPreflightError("project retry contract drifted")
    if project_config.runtime.concurrency != EXPECTED_CONCURRENCY:
        raise D5StaticPreflightError("project concurrency contract drifted")
    if project_config.runtime.structured_output != EXPECTED_STRUCTURED_OUTPUT:
        raise D5StaticPreflightError("project structured-output contract drifted")


def _run_static_attestation(repo_root: Path) -> dict[str, Any]:
    """Run the accepted D5 attestation and reachability checks without network."""
    environment = {**os.environ, "PYTHONPATH": str(repo_root / "src")}
    checks = (
        [
            "scripts/d5_single_engine_attestation.py",
            "--repo-root",
            str(repo_root),
            "--check",
        ],
        [
            "scripts/check_d5_single_engine_reachability.py",
            "--repo-root",
            str(repo_root),
        ],
    )
    results: list[dict[str, Any]] = []
    for command in checks:
        completed = subprocess.run(
            [sys.executable, os.fspath(repo_root / command[0]), *command[1:]],
            cwd=repo_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise D5StaticPreflightError(f"static D5 check failed: {command[0]}")
        results.append({"command": command[0], "status": "PASS"})
    return {"status": "PASS", "checks": results}


def _inspect_openai_sdk() -> tuple[str, int]:
    """Inspect the installed SDK version and constructor retry default."""
    try:
        version = importlib.metadata.version("openai")
        from openai import AsyncOpenAI

        retries = inspect.signature(AsyncOpenAI).parameters["max_retries"].default
    except (ImportError, KeyError, TypeError, ValueError, importlib.metadata.PackageNotFoundError):
        raise D5StaticPreflightError("OpenAI SDK retry contract cannot be inspected") from None
    if version != EXPECTED_OPENAI_VERSION or retries != EXPECTED_SDK_MAX_RETRIES:
        raise D5StaticPreflightError("OpenAI SDK version/retry contract drifted")
    return version, retries


def _default_static_checks(
    repo_root: Path,
    authorization: D5Authorization,
    artifact_paths: EvidencePaths,
) -> dict[str, Any]:
    """Execute fail-closed repository, source, dependency, and path checks."""
    current = _git(repo_root, "rev-parse", "HEAD")
    if current != authorization.implementation_checkpoint:
        raise D5StaticPreflightError("implementation checkpoint mismatch")
    if _git(repo_root, "status", "--porcelain"):
        raise D5StaticPreflightError("working tree is not clean")
    project_config = load_project_config(repo_root)
    _validate_project_config(project_config)
    if (
        not authorization.project_config_fingerprint_sha256
        or authorization.project_config_fingerprint_sha256 != project_config.fingerprint_sha256
    ):
        raise D5StaticPreflightError("project configuration fingerprint mismatch")
    if authorization.accepted_d5_engine_checkpoint != D5_ENGINE_CHECKPOINT:
        raise D5StaticPreflightError("accepted D5 engine checkpoint drifted")
    if authorization.accepted_d5_design_checkpoint != D5_DESIGN_CHECKPOINT:
        raise D5StaticPreflightError("accepted D5 design checkpoint drifted")
    if (
        authorization.accepted_h_implementation_checkpoint
        != D5I_ACCEPTED_H_IMPLEMENTATION_CHECKPOINT
    ):
        raise D5StaticPreflightError("accepted H implementation checkpoint drifted")
    if (
        subprocess.run(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                D5I_ACCEPTED_H_IMPLEMENTATION_CHECKPOINT,
                current,
            ],
            cwd=repo_root,
            check=False,
        ).returncode
        != 0
    ):
        raise D5StaticPreflightError("accepted H implementation is not an ancestor")
    if authorization.provider != EXPECTED_PROVIDER or authorization.model != EXPECTED_MODEL:
        raise D5StaticPreflightError("provider/model contract drifted")
    if authorization.sdk_version != EXPECTED_OPENAI_VERSION:
        raise D5StaticPreflightError("OpenAI package contract drifted")
    if authorization.sdk_max_retries != EXPECTED_SDK_MAX_RETRIES:
        raise D5StaticPreflightError("SDK retry contract drifted")
    if authorization.structured_output_contract != "json_schema":
        raise D5StaticPreflightError("structured-output contract drifted")
    if not authorization.thinking_off:
        raise D5StaticPreflightError("thinking-off request contract is absent")
    if authorization.thinking_control_options_sha256 != THINKING_CONTROL_OPTIONS_SHA256:
        raise D5StaticPreflightError("thinking-off request control digest drifted")
    _validated_thinking_control_options(authorization.thinking_control_options)
    if not authorization.endpoint_identity:
        raise D5StaticPreflightError("authorized endpoint identity is missing")
    if not authorization.runtime_defaults_sha256:
        raise D5StaticPreflightError("authorized runtime-default fingerprint is missing")
    if authorization.minimum_context_size <= 0:
        raise D5StaticPreflightError("authorized minimum context size is missing")
    if not authorization.authorization_id or not authorization.campaign_id:
        raise D5StaticPreflightError("authorization/campaign identity is missing")
    if artifact_paths.campaign_id != authorization.campaign_id:
        raise D5StaticPreflightError("campaign path is not bound to authorization")
    for path in (
        artifact_paths.state,
        artifact_paths.journal,
        artifact_paths.terminal,
        artifact_paths.summary,
        artifact_paths.evidence,
    ):
        if path.exists():
            raise D5StaticPreflightError(f"fresh artifact path already exists: {path.name}")

    for relative in authorization.source_sha256:
        if not (repo_root / relative).is_file():
            raise D5StaticPreflightError("LOCAL_ASSET_NOT_PROVISIONED_IN_THIS_CHECKOUT")
    _assert_hash(repo_root / d4.CASES_PATH, authorization.cases_sha256, "case fixture")
    _assert_hash(repo_root / d4.GOLD_PATH, authorization.gold_sha256, "gold fixture")
    _assert_hash(repo_root / d4.UV_LOCK_PATH, authorization.uv_lock_sha256, "uv.lock")
    for relative, digest in authorization.source_sha256.items():
        _assert_hash(repo_root / relative, digest, relative)
    try:
        las = d4.preflight_las_source(repo_root)
        dlis = d4.preflight_dlis_sources(repo_root)
    except d4.PreflightError as error:
        raise D5StaticPreflightError("frozen source parse/custody failed") from error
    observed_sources = {
        las.relative_path: las.sha256,
        **{item["relative_path"]: item["sha256"] for item in dlis},
    }
    if observed_sources != dict(authorization.source_sha256):
        raise D5StaticPreflightError("source custody manifest drifted")
    current_manifest = d4.production_component_hashes(repo_root)
    if current_manifest != dict(authorization.production_component_sha256):
        raise D5StaticPreflightError("production component attestation drifted")

    version, retries = _inspect_openai_sdk()

    static_attestation = _run_static_attestation(repo_root)
    return {
        "status": "PASS",
        "current_checkout": current,
        "accepted_d5_engine_checkpoint": D5_ENGINE_CHECKPOINT,
        "accepted_d5_design_checkpoint": D5_DESIGN_CHECKPOINT,
        "accepted_h_implementation_checkpoint": D5I_ACCEPTED_H_IMPLEMENTATION_CHECKPOINT,
        "openai_version": version,
        "sdk_max_retries": retries,
        "logical_call_ceiling": MAX_LOGICAL_CALLS,
        "physical_attempt_upper_bound": MAX_PHYSICAL_ATTEMPTS,
        "concurrency": project_config.runtime.concurrency,
        "generation_timeout_seconds": project_config.provider.timeout_seconds,
        "project_config_fingerprint_sha256": project_config.fingerprint_sha256,
        "server_origin": project_config.server_origin,
        "model_catalog_url": project_config.model_catalog_url,
        "props_url": project_config.props_url,
        "thinking_control_mechanism": THINKING_CONTROL_MECHANISM,
        "thinking_control_options_sha256": THINKING_CONTROL_OPTIONS_SHA256,
        "fallback": "NONE",
        "model_substitution": "FORBIDDEN",
        "d5_attestation": static_attestation,
    }


@dataclass(frozen=True, slots=True)
class EvidencePaths:
    """Fresh custody namespace for one D5-4 campaign."""

    root: Path
    campaign_id: str

    @property
    def state(self) -> Path:
        """Return the campaign state path."""
        return self.root / f"{self.campaign_id}{STATE_SUFFIX}"

    @property
    def journal(self) -> Path:
        """Return the append-only campaign journal path."""
        return self.root / f"{self.campaign_id}{JOURNAL_SUFFIX}"

    @property
    def terminal(self) -> Path:
        """Return the immutable terminal artifact path."""
        return self.root / f"{self.campaign_id}{TERMINAL_SUFFIX}"

    @property
    def summary(self) -> Path:
        """Return the bounded campaign summary path."""
        return self.root / f"{self.campaign_id}{SUMMARY_SUFFIX}"

    @property
    def evidence(self) -> Path:
        """Return the redacted per-turn evidence path."""
        return self.root / f"{self.campaign_id}{EVIDENCE_SUFFIX}"

    @property
    def model_io(self) -> Path:
        """Return the optional exact model-I/O custody path."""
        return self.root / f"{self.campaign_id}{MODEL_IO_SUFFIX}"

    def all_paths(self) -> tuple[Path, ...]:
        """Return all collision-sensitive paths in deterministic order."""
        return (
            self.state,
            self.journal,
            self.terminal,
            self.summary,
            self.evidence,
            self.model_io,
        )


def ensure_fresh_namespace(paths: EvidencePaths) -> None:
    """Reject any collision before readiness or campaign creation."""
    if any(path.exists() for path in paths.all_paths()):
        raise D5StaticPreflightError("campaign artifact collision")
    paths.root.mkdir(parents=True, exist_ok=True)


def _atomic_json(path: Path, value: Mapping[str, Any], *, exclusive: bool = False) -> None:
    """Write one bounded JSON artifact atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if exclusive and path.exists():
        temporary.unlink(missing_ok=True)
        raise D5HarnessError(f"artifact already exists: {path.name}")
    os.replace(temporary, path)


def _append_jsonl(path: Path, value: Mapping[str, Any], *, exclusive: bool = False) -> None:
    """Append one redacted event, refusing a pre-existing journal when requested."""
    if not evidence_is_redacted(value):
        raise D5HarnessError("redaction failure before evidence append")
    if exclusive and path.exists():
        raise D5HarnessError("journal already exists")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def evidence_is_redacted(value: object) -> bool:
    """Reject secrets, raw provider material, prompts, paths, and dump fields."""
    if isinstance(value, Mapping):
        return all(
            str(key) not in SECRET_KEYS and evidence_is_redacted(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return all(evidence_is_redacted(item) for item in value)
    if isinstance(value, str):
        lowered = value.casefold()
        return not any(marker in lowered for marker in SECRET_MARKERS)
    return True


@dataclass(slots=True)
class D5LogicalCallLedger:
    """Reserve logical calls before delegation and track physical attempts."""

    max_logical_calls: int = MAX_LOGICAL_CALLS
    max_physical_attempts: int = MAX_PHYSICAL_ATTEMPTS
    logical_calls: int = 0
    physical_attempts: int = 0
    calls: list[dict[str, Any]] = field(default_factory=list)
    active_turn_id: str | None = None
    turn_role_counts: dict[str, int] = field(default_factory=dict)

    def begin_turn(self, turn_id: str) -> None:
        """Reset per-turn role accounting at the frozen turn boundary."""
        self.active_turn_id = str(turn_id)
        self.turn_role_counts = {}

    def reserve(self, role: str) -> int:
        """Reserve a role-tagged logical call before provider delegation."""
        if role not in {"planner", "report_worker", "section_worker"}:
            raise D5HarnessError("unknown generation role")
        if self.active_turn_id is not None:
            used = self.turn_role_counts.get(role, 0)
            limit = ROLE_LOGICAL_CALL_LIMITS[role]
            if used >= limit:
                raise D5CallCapExceeded(
                    f"{role} logical call limit {limit} exceeded for turn {self.active_turn_id}"
                )
        next_index = self.logical_calls + 1
        if next_index > self.max_logical_calls:
            raise D5CallCapExceeded("logical call 46 rejected before provider delegation")
        self.logical_calls = next_index
        self.calls.append(
            {
                "logical_call_index": next_index,
                "role": role,
                "physical_attempt_count": 0,
                "outcome": "reserved",
            }
        )
        if self.active_turn_id is not None:
            self.turn_role_counts[role] = self.turn_role_counts.get(role, 0) + 1
        return next_index

    def physical_attempt(self, logical_index: int) -> None:
        """Record one SDK-level attempt without reserving a new logical call."""
        if logical_index < 1 or logical_index > self.logical_calls:
            raise D5HarnessError("physical attempt references unknown logical call")
        next_attempt = self.physical_attempts + 1
        if next_attempt > self.max_physical_attempts:
            raise D5CallCapExceeded(
                f"physical attempt {next_attempt} rejected before provider delegation"
            )
        self.physical_attempts += 1
        row = self.calls[logical_index - 1]
        row["physical_attempt_count"] += 1

    def complete(self, logical_index: int, outcome: str) -> None:
        """Close one logical call with bounded outcome metadata."""
        outcome = {"success": "completed", "failure": "failed"}.get(outcome, outcome)
        if outcome not in {"completed", "failed", "rejected"}:
            raise D5HarnessError("unknown logical-call outcome")
        self.calls[logical_index - 1]["outcome"] = outcome

    def annotate_completion(
        self,
        logical_index: int,
        *,
        failure_category: str | None = None,
        metrics: Mapping[str, Any] | None = None,
    ) -> None:
        """Retain bounded completion metrics without provider payloads."""
        row = self.calls[logical_index - 1]
        if failure_category is not None:
            row["failure_category"] = str(failure_category)
        if metrics:
            row["metrics"] = {
                key: value
                for key, value in metrics.items()
                if key in {"latency_ms", "input_tokens", "output_tokens", "total_tokens"}
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            }

    def record_d4_event(self, event: Mapping[str, Any]) -> None:
        """Attach D4 CountingBackend events to this D5 ledger."""
        event_name = event.get("event")
        index = int(event.get("index", 0))
        role = str(event.get("generation_role", ""))
        if event_name == "logical_call_started":
            expected = self.reserve(role)
            if expected != index:
                raise D5HarnessError("D4/D5 logical call index drift")
        elif event_name == "logical_call_completed":
            self.complete(index, str(event.get("outcome", "failed")))


def _safe_hash(value: object) -> str | None:
    """Return a local artifact hash without retaining its path in evidence."""
    if isinstance(value, Path) and value.is_file():
        return _sha256_file(value)
    if isinstance(value, str):
        path = Path(value)
        if path.is_file():
            return _sha256_file(path)
    return None


@dataclass(slots=True)
class D5CampaignCustody:
    """Durable one-shot campaign state, journal, evidence, and terminal record."""

    paths: EvidencePaths
    campaign_id: str
    state: dict[str, Any]
    ledger: D5LogicalCallLedger
    authorization_id: str
    mode: str = "scientific"
    live: bool = False
    endpoint_call_count: int = 2
    started: bool = False
    legacy_eager: bool = False
    require_physical_observer: bool = False
    _active_logical_index: int | None = None
    _active_turn_id: str | None = None
    _terminal_written: bool = False

    @classmethod
    def prepare(
        cls,
        paths: EvidencePaths,
        *,
        authorization: D5Authorization,
        provenance: Mapping[str, Any],
        readiness: D5ReadinessProjectionProtocol,
        live: bool = False,
        endpoint_call_count: int = 2,
        mode: str = "scientific",
    ) -> D5CampaignCustody:
        """Prepare custody without consuming it before the first generation."""
        ensure_fresh_namespace(paths)
        if paths.campaign_id != authorization.campaign_id:
            raise D5HarnessError("campaign path does not match authorization")
        if mode not in {"smoke", "scientific"}:
            raise D5HarnessError("unknown campaign mode")
        state = {
            "experiment_version": D5_EXPERIMENT_VERSION,
            "mode": mode,
            "campaign_id": paths.campaign_id,
            "authorization_id": authorization.authorization_id,
            "status": "NOT_STARTED",
            "readiness_status": "LIVE_READY",
            "provider": authorization.provider,
            "model": authorization.model,
            "logical_generation_calls": 0,
            "physical_generation_attempts": 0,
            "identity_endpoint_calls": endpoint_call_count,
            "endpoint_calls": endpoint_call_count if live else 0,
            "provider_calls": 0,
            "model_calls": 0,
            "live_execution": live,
            "endpoint_identity": readiness.as_dict(),
            "provenance": dict(provenance),
            "started": False,
            "campaign_consumed": False,
        }
        if not evidence_is_redacted(state):
            raise D5HarnessError("state redaction failure")
        return cls(
            paths=paths,
            campaign_id=paths.campaign_id,
            state=state,
            ledger=D5LogicalCallLedger(),
            authorization_id=authorization.authorization_id,
            mode=mode,
            live=live,
            endpoint_call_count=endpoint_call_count,
        )

    # Preserve the existing custody construction name while keeping activation lazy.
    @classmethod
    def start(
        cls,
        paths: EvidencePaths,
        *,
        authorization: D5Authorization,
        provenance: Mapping[str, Any],
        readiness: D5ReadinessProjectionProtocol,
        live: bool = False,
        endpoint_call_count: int = 2,
        mode: str = "scientific",
    ) -> D5CampaignCustody:
        """Retain the historical constructor for legacy custody tests only."""
        custody = cls.prepare(
            paths,
            authorization=authorization,
            provenance=provenance,
            readiness=readiness,
            live=live,
            endpoint_call_count=endpoint_call_count,
            mode=mode,
        )
        custody.paths.model_io.touch(exist_ok=False)
        custody.legacy_eager = True
        return custody

    def _activate(self) -> None:
        """Consume custody immediately before the first provider delegation."""
        if self.started:
            return
        self.state.update(
            {
                "status": "STARTED",
                "started": True,
                "campaign_consumed": True,
            }
        )
        _atomic_json(self.paths.state, self.state, exclusive=True)
        _append_jsonl(
            self.paths.journal,
            {
                "event": "campaign_started",
                "mode": self.mode,
                "experiment_version": D5_EXPERIMENT_VERSION,
                "campaign_id": self.campaign_id,
                "authorization_id": self.authorization_id,
                "status": "STARTED",
            },
            exclusive=True,
        )
        self.paths.model_io.touch(exist_ok=True)
        self.started = True

    def record_call_started(self, event: Mapping[str, Any]) -> None:
        """Persist one role-aware logical call before delegation."""
        self._activate()
        self.ledger.record_d4_event(event)
        self._active_logical_index = int(event["index"])
        self.state["logical_generation_calls"] = self.ledger.logical_calls
        self.state["physical_generation_attempts"] = self.ledger.physical_attempts
        _atomic_json(self.paths.state, self.state)
        bounded = {
            "event": "logical_call_started",
            "experiment_version": D5_EXPERIMENT_VERSION,
            "campaign_id": self.campaign_id,
            "authorization_id": self.authorization_id,
            "index": event.get("index"),
            "generation_role": event.get("generation_role"),
            "provider": event.get("provider"),
            "model": event.get("model"),
        }
        _append_jsonl(self.paths.journal, bounded)

    def record_call_completed(self, event: Mapping[str, Any]) -> None:
        """Persist bounded completion metadata without payload material."""
        index = int(event.get("index", 0))
        call = self.ledger.calls[index - 1]
        if call["physical_attempt_count"] == 0:
            if self.require_physical_observer:
                raise D5HarnessError("physical attempt was not observed")
            self.ledger.physical_attempt(index)
        self.ledger.complete(index, str(event.get("outcome", "failed")))
        self.ledger.annotate_completion(
            index,
            failure_category=event.get("failure_category"),
            metrics=event,
        )
        self.state["logical_generation_calls"] = self.ledger.logical_calls
        self.state["physical_generation_attempts"] = self.ledger.physical_attempts
        _atomic_json(self.paths.state, self.state)
        bounded = {
            "event": "logical_call_completed",
            "experiment_version": D5_EXPERIMENT_VERSION,
            "campaign_id": self.campaign_id,
            "authorization_id": self.authorization_id,
            "index": index,
            "generation_role": event.get("generation_role"),
            "provider": event.get("provider"),
            "model": event.get("model"),
            "outcome": event.get("outcome"),
            "failure_category": event.get("failure_category"),
            "physical_attempt_count": call["physical_attempt_count"],
            "latency_ms": event.get("latency_ms"),
            "input_tokens": event.get("input_tokens"),
            "output_tokens": event.get("output_tokens"),
            "total_tokens": event.get("total_tokens"),
        }
        _append_jsonl(self.paths.journal, bounded)

    def record_physical_attempt(self, index: int | None = None) -> None:
        """Record one observed SDK/HTTP attempt for the active logical call."""
        logical_index = index if index is not None else self._active_logical_index
        if logical_index is None:
            raise D5HarnessError("physical attempt has no active logical call")
        self.ledger.physical_attempt(logical_index)
        _append_jsonl(
            self.paths.journal,
            {
                "event": "physical_attempt",
                "experiment_version": D5_EXPERIMENT_VERSION,
                "campaign_id": self.campaign_id,
                "authorization_id": self.authorization_id,
                "index": logical_index,
                "physical_attempt_count": self.ledger.calls[logical_index - 1][
                    "physical_attempt_count"
                ],
            },
        )

    def begin_turn(self, turn_id: str) -> None:
        """Bind subsequent model-I/O observations to the active frozen turn."""
        self._active_turn_id = str(turn_id)
        self.ledger.begin_turn(turn_id)

    def append_model_io(self, row: Mapping[str, Any]) -> None:
        """Append exact request/response bodies without headers or credentials."""
        forbidden = {"headers", "request_headers", "response_headers", "authorization"}
        if forbidden.intersection(row) or _contains_forbidden_key(row, forbidden):
            raise D5HarnessError("model-I/O custody cannot contain headers")
        if row.get("campaign_id") != self.campaign_id:
            raise D5HarnessError("model-I/O campaign identity mismatch")
        with self.paths.model_io.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(row), sort_keys=True, separators=(",", ":")) + "\n")

    def record_model_io(self, row: Mapping[str, Any]) -> None:
        """Append one observer event with the current turn and custody identity."""
        if self._active_turn_id is None:
            raise D5HarnessError("model-I/O observation has no active turn")
        bounded = dict(row)
        bounded.update(
            {
                "campaign_id": self.campaign_id,
                "authorization_id": self.authorization_id,
                "turn_id": self._active_turn_id,
            }
        )
        self.append_model_io(bounded)

    def record_logical_model_result(self, event: Mapping[str, Any]) -> None:
        """Persist canonical parse/validation outcome after backend consumption."""
        if self._active_turn_id is None:
            raise D5HarnessError("logical model result has no active turn")
        self.record_model_io(
            {
                "event": "logical_call_result",
                "logical_call_index": event.get("index"),
                "role": event.get("generation_role"),
                "model": event.get("model"),
                "engine_outcome": event.get("outcome"),
                "failure_category": event.get("failure_category"),
                "response_reason": event.get("response_reason"),
                "validation_shape": event.get("validation_shape"),
                "json_parse": (
                    "PASS" if event.get("outcome") == "success" else event.get("response_reason")
                ),
                "response_model_validation": (
                    "PASS"
                    if event.get("outcome") == "success"
                    else (
                        "FAIL"
                        if event.get("response_reason") == "schema_validation"
                        else "NOT_ESTABLISHED"
                    )
                ),
            }
        )

    def append_turn(self, row: Mapping[str, Any]) -> None:
        """Append one redacted bounded turn result."""
        if not evidence_is_redacted(row):
            raise D5HarnessError("turn evidence failed redaction")
        _append_jsonl(self.paths.evidence, dict(row))

    def finish(
        self,
        decision: str,
        *,
        attribution: str,
        rows: Sequence[Mapping[str, Any]],
        scientific_terminal: str | None = None,
        first_divergence: str = "NONE",
    ) -> dict[str, Any]:
        """Write exactly one terminal artifact and close the campaign."""
        if decision not in TERMINAL_DECISIONS:
            raise D5HarnessError("unknown terminal decision")
        if scientific_terminal is not None and scientific_terminal not in D5I_SCIENTIFIC_TERMINALS:
            raise D5HarnessError("unknown scientific terminal")
        if first_divergence not in D5I_FIRST_DIVERGENCES:
            raise D5HarnessError("unknown first divergence")
        if self._terminal_written or self.paths.terminal.exists():
            raise D5HarnessError("terminal artifact already written")
        if not self.started and not self.legacy_eager:
            raise D5HarnessError("cannot seal custody before first logical call")
        if not self.started:
            self.state.update(
                {
                    "status": "TERMINAL",
                    "decision": decision,
                    "attribution": attribution,
                    "scientific_terminal": scientific_terminal,
                    "first_divergence": first_divergence,
                    "completed_turns": len(rows),
                    "started": False,
                    "campaign_consumed": False,
                }
            )
            _atomic_json(self.paths.state, self.state, exclusive=True)
            self.paths.evidence.touch()
            self.paths.model_io.touch()
        _append_jsonl(
            self.paths.journal,
            {
                "event": "campaign_terminal",
                "mode": self.mode,
                "experiment_version": D5_EXPERIMENT_VERSION,
                "campaign_id": self.campaign_id,
                "authorization_id": self.authorization_id,
                "decision": decision,
                "attribution": attribution,
                "scientific_terminal": scientific_terminal,
                "first_divergence": first_divergence,
                "completed_turns": len(rows),
            },
        )
        self.state.update(
            {
                "status": "TERMINAL",
                "decision": decision,
                "attribution": attribution,
                "scientific_terminal": scientific_terminal,
                "first_divergence": first_divergence,
                "completed_turns": len(rows),
                "logical_generation_calls": self.ledger.logical_calls,
                "physical_generation_attempts": self.ledger.physical_attempts,
                "endpoint_calls": self.endpoint_call_count if self.live else 0,
                "provider_calls": self.ledger.logical_calls if self.live else 0,
                "model_calls": self.ledger.logical_calls if self.live else 0,
                "mode": self.mode,
                "started": self.started,
                "campaign_consumed": self.started,
            }
        )
        _atomic_json(self.paths.state, self.state)
        if not self.paths.evidence.exists():
            self.paths.evidence.touch()
        evidence_digest = (
            _sha256_file(self.paths.evidence) if self.paths.evidence.exists() else None
        )
        journal_digest = _sha256_file(self.paths.journal)
        state_digest = _sha256_file(self.paths.state)
        model_io_digest = (
            _sha256_file(self.paths.model_io) if self.paths.model_io.exists() else None
        )
        terminal = {
            "experiment_version": D5_EXPERIMENT_VERSION,
            "mode": self.mode,
            "campaign_id": self.campaign_id,
            "authorization_id": self.authorization_id,
            "decision": decision,
            "attribution": attribution,
            "scientific_terminal": scientific_terminal,
            "first_divergence": first_divergence,
            "completed_turns": len(rows),
            "logical_generation_calls": self.ledger.logical_calls,
            "physical_generation_attempts": self.ledger.physical_attempts,
            "endpoint_calls": self.endpoint_call_count if self.live else 0,
            "provider_calls": self.ledger.logical_calls if self.live else 0,
            "model_calls": self.ledger.logical_calls if self.live else 0,
            "started": self.started,
            "campaign_consumed": self.started,
            "state_snapshot_sha256": state_digest,
            "journal_sha256": journal_digest,
            "evidence_sha256": evidence_digest,
        }
        if model_io_digest is not None:
            terminal["model_io_sha256"] = model_io_digest
        _atomic_json(self.paths.terminal, terminal, exclusive=True)
        summary = {
            "experiment_version": D5_EXPERIMENT_VERSION,
            "mode": self.mode,
            "campaign_id": self.campaign_id,
            "authorization_id": self.authorization_id,
            "decision": decision,
            "attribution": attribution,
            "scientific_terminal": scientific_terminal,
            "first_divergence": first_divergence,
            "completed_turns": len(rows),
            "logical_generation_calls": self.ledger.logical_calls,
            "physical_generation_attempts": self.ledger.physical_attempts,
            "endpoint_calls": self.endpoint_call_count if self.live else 0,
            "provider_calls": self.ledger.logical_calls if self.live else 0,
            "model_calls": self.ledger.logical_calls if self.live else 0,
            "terminal_sha256": _sha256_file(self.paths.terminal),
        }
        if model_io_digest is not None:
            summary["model_io_sha256"] = model_io_digest
        _atomic_json(self.paths.summary, summary, exclusive=True)
        self._terminal_written = True
        return terminal


def verify_custody_artifacts(paths: EvidencePaths) -> dict[str, str]:
    """Recompute old five-file or new six-file custody without mutation."""
    required = (paths.state, paths.journal, paths.terminal, paths.summary, paths.evidence)
    if not all(path.is_file() for path in required):
        raise D5HarnessError("custody artifact set is incomplete")
    state = json.loads(paths.state.read_text(encoding="utf-8"))
    terminal = json.loads(paths.terminal.read_text(encoding="utf-8"))
    summary = json.loads(paths.summary.read_text(encoding="utf-8"))
    if not isinstance(state, Mapping) or not isinstance(terminal, Mapping):
        raise D5HarnessError("custody JSON shape is invalid")
    if not isinstance(summary, Mapping) or not evidence_is_redacted(state):
        raise D5HarnessError("custody redaction failed")
    if not evidence_is_redacted(terminal) or not evidence_is_redacted(summary):
        raise D5HarnessError("custody redaction failed")
    if state.get("status") != "TERMINAL":
        raise D5HarnessError("final state is not terminal")
    if state.get("campaign_id") != paths.campaign_id:
        raise D5HarnessError("state campaign identity mismatch")
    if terminal.get("campaign_id") != paths.campaign_id:
        raise D5HarnessError("terminal campaign identity mismatch")
    if summary.get("campaign_id") != paths.campaign_id:
        raise D5HarnessError("summary campaign identity mismatch")
    digests = {
        "state_sha256": _sha256_file(paths.state),
        "journal_sha256": _sha256_file(paths.journal),
        "evidence_sha256": _sha256_file(paths.evidence),
        "terminal_sha256": _sha256_file(paths.terminal),
    }
    if paths.model_io.exists():
        digests["model_io_sha256"] = _sha256_file(paths.model_io)
        if terminal.get("model_io_sha256") != digests["model_io_sha256"]:
            raise D5HarnessError("terminal model-I/O digest mismatch")
        if summary.get("model_io_sha256") != digests["model_io_sha256"]:
            raise D5HarnessError("summary model-I/O digest mismatch")
    if terminal.get("state_snapshot_sha256") != digests["state_sha256"]:
        raise D5HarnessError("terminal state digest mismatch")
    if terminal.get("journal_sha256") != digests["journal_sha256"]:
        raise D5HarnessError("terminal journal digest mismatch")
    if terminal.get("evidence_sha256") != digests["evidence_sha256"]:
        raise D5HarnessError("terminal evidence digest mismatch")
    if summary.get("terminal_sha256") != digests["terminal_sha256"]:
        raise D5HarnessError("summary terminal digest mismatch")
    return digests


def _project_model_catalog(payload: object, expected_model: str) -> tuple[str, ...]:
    """Project exactly one model ID without retaining the response body."""
    if not isinstance(payload, Mapping) or not isinstance(payload.get("data"), list):
        raise D5ReadinessError(
            "endpoint_identity_mismatch",
            1,
            mismatched_fields=("model_catalog",),
        )
    identifiers = tuple(
        str(item.get("id", "")).strip() for item in payload["data"] if isinstance(item, Mapping)
    )
    if expected_model and identifiers != (expected_model,):
        raise D5ReadinessError(
            "endpoint_identity_mismatch",
            1,
            mismatched_fields=("model_catalog",),
        )
    return identifiers


def _project_props(payload: object, expected_contract: str) -> dict[str, Any]:
    """Project documented llama.cpp `/props` fields without synthetic flags."""
    if not isinstance(payload, Mapping):
        raise D5ReadinessError("endpoint_identity_mismatch", 2)
    path = payload.get("model_path")
    generation = payload.get("default_generation_settings")
    build_info = payload.get("build_info")
    slots = payload.get("total_slots")
    chat_template = payload.get("chat_template")
    if (
        not isinstance(path, str)
        or not path.strip()
        or not isinstance(generation, Mapping)
        or not isinstance(generation.get("n_ctx"), int)
        or isinstance(generation.get("n_ctx"), bool)
        or generation["n_ctx"] <= 0
        or not isinstance(build_info, str)
        or not build_info.strip()
        or not isinstance(slots, int)
        or isinstance(slots, bool)
        or slots <= 0
        or not isinstance(chat_template, str)
        or not chat_template.strip()
    ):
        raise D5ReadinessError("endpoint_identity_mismatch", 2)
    if expected_contract != "json_schema":
        raise D5ReadinessError("endpoint_identity_mismatch", 2)
    normalized_path = path.strip()
    basename = Path(normalized_path).name
    runtime_defaults = dict(generation)
    return {
        "model_path_basename": basename,
        "model_path_fingerprint_sha256": d4.sha256_text(normalized_path),
        "context_size": generation["n_ctx"],
        "build_info": build_info.strip(),
        "total_slots": slots,
        "chat_template_sha256": hashlib.sha256(chat_template.encode("utf-8")).hexdigest(),
        "runtime_defaults_sha256": _sha256_json(runtime_defaults),
        "structured_output_contract": expected_contract,
        "gguf_byte_identity": str(payload.get("gguf_byte_identity", "NOT_AVAILABLE")),
    }


def validate_readiness_projection(
    observed: Mapping[str, Any],
    authorization: D5Authorization,
) -> D5ReadinessProjection:
    """Require runtime identity plus the statically authorized request control."""
    required = {
        "model_catalog",
        "model_path_basename",
        "model_path_fingerprint_sha256",
        "context_size",
        "build_info",
        "total_slots",
        "chat_template_sha256",
        "runtime_defaults_sha256",
        "structured_output_contract",
    }
    if not required <= set(observed):
        raise D5ReadinessError("endpoint_identity_mismatch", 2)
    if (
        authorization.minimum_context_size
        and int(observed["context_size"]) < authorization.minimum_context_size
    ):
        raise D5ReadinessError("context_budget_insufficient", 2)
    if (
        authorization.runtime_defaults_sha256
        and observed["runtime_defaults_sha256"] != authorization.runtime_defaults_sha256
    ):
        raise D5ReadinessError("runtime_defaults_mismatch", 2)
    if observed["structured_output_contract"] != authorization.structured_output_contract:
        raise D5ReadinessError("structured_output_contract_mismatch", 2)
    expected = dict(authorization.endpoint_identity)
    if not isinstance(expected.get("chat_template_sha256"), str):
        raise D5ReadinessError("endpoint_identity_mismatch", 2)
    if authorization.thinking_control_options_sha256 != THINKING_CONTROL_OPTIONS_SHA256:
        raise D5ReadinessError("thinking_off_not_established", 2)
    try:
        _validated_thinking_control_options(authorization.thinking_control_options)
    except D5StaticPreflightError:
        raise D5ReadinessError("thinking_off_not_established", 2) from None
    mismatched_fields: list[str] = []
    for key, value in expected.items():
        observed_value = observed.get(key)
        if isinstance(observed_value, tuple) and isinstance(value, list):
            observed_value = list(observed_value)
        if observed_value != value:
            mismatched_fields.append(key)
    if mismatched_fields:
        raise D5ReadinessError(
            "endpoint_identity_mismatch",
            2,
            mismatched_fields=mismatched_fields,
        )
    if not authorization.thinking_off:
        raise D5ReadinessError("thinking_off_not_established", 2)
    return D5ReadinessProjection(**dict(observed), thinking_off=True)


@dataclass(frozen=True, slots=True)
class D5OperationalReadiness:
    """Successful two-GET readiness result with no generation probe."""

    projection: D5ReadinessProjectionProtocol
    endpoint_calls: tuple[str, ...]
    adapter: object | None = None
    live: bool = False
    provider_calls: int = 0
    model_calls: int = 0


def prepare_readiness(
    *,
    authorization: D5Authorization,
    project_config: ProjectConfig,
    api_key_loader: Callable[[], str],
    endpoint_get: Callable[[str, str], object],
    static_preflight: Mapping[str, Any],
    provider_factory: Callable[[str], object] | None = None,
) -> D5OperationalReadiness:
    """Perform exactly two injectable identity observations after static checks."""
    if static_preflight.get("status") != "PASS":
        raise D5ReadinessError("static_preflight_failed", 0)
    _validate_project_config(project_config)
    try:
        token = api_key_loader()
    except d4.ReadinessFailure as error:
        raise D5ReadinessError(error.reason_code, error.identity_endpoint_calls) from None
    if not isinstance(token, str) or not token.strip():
        raise D5ReadinessError("credential_unavailable", 0)
    calls: list[str] = []

    def get(url: str) -> object:
        calls.append(url)
        return endpoint_get(url, token)

    try:
        catalog = _project_model_catalog(get(project_config.model_catalog_url), "")
        props = _project_props(
            get(project_config.props_url), authorization.structured_output_contract
        )
        observed = {"model_catalog": catalog, **props}
        projection = validate_readiness_projection(observed, authorization)
    except D5ReadinessError as error:
        raise D5ReadinessError(
            error.reason,
            len(calls),
            http_status=error.http_status,
            mismatched_fields=error.mismatched_fields,
        ) from None
    except Exception:
        raise D5ReadinessError("endpoint_unreachable", len(calls)) from None
    if tuple(calls) != (project_config.model_catalog_url, project_config.props_url):
        raise D5ReadinessError("endpoint_order_mismatch", len(calls))
    adapter = None
    if provider_factory is not None:
        try:
            adapter = provider_factory(token)
        except D5ReadinessError:
            raise
        except Exception:
            raise D5ReadinessError("provider_construction_failed", len(calls)) from None
    return D5OperationalReadiness(
        projection=projection,
        endpoint_calls=("/v1/models", "/props"),
        adapter=adapter,
        live=provider_factory is not None,
    )


class _PhysicalAttemptObserver:
    """Observe generation HTTP bodies while one logical call is active."""

    def __init__(self) -> None:
        self.active_logical_index: int | None = None
        self.callback: Callable[[int], None] | None = None
        self.model_io_callback: Callable[[dict[str, Any]], None] | None = None
        self.active_turn_id: str | None = None
        self.active_role: str | None = None
        self.active_model: str | None = None
        self._attempts: dict[int, int] = {}
        self._pending_responses: dict[int, dict[str, Any]] = {}

    async def __call__(self, request: object) -> None:
        """Remain compatible with existing injected request event hooks."""
        await self.on_request(request)

    async def on_request(self, request: object) -> None:
        """Count and capture only generation requests, never readiness GETs."""
        url = getattr(request, "url", None)
        path = str(getattr(url, "path", ""))
        if not path.endswith("/chat/completions"):
            return
        if self.active_logical_index is None or self.callback is None:
            raise D5HarnessError("generation attempt has no active logical call")
        logical_index = self.active_logical_index
        attempt = self._attempts.get(logical_index, 0) + 1
        self.callback(logical_index)
        self._attempts[logical_index] = attempt
        body = bytes(getattr(request, "content", b""))
        self._pending_responses[id(request)] = {
            "event": "physical_request",
            "turn_id": self.active_turn_id,
            "logical_call_index": logical_index,
            "role": self.active_role,
            "model": self.active_model,
            "physical_attempt": attempt,
            "request_sha256": hashlib.sha256(body).hexdigest(),
            "request_body": body.decode("utf-8", errors="replace"),
            "request_json": _json_body(body),
        }
        if self.model_io_callback is not None:
            self.model_io_callback(dict(self._pending_responses[id(request)]))

    async def on_response(self, response: object) -> None:
        """Capture the matching response body without headers."""
        request = getattr(response, "request", None)
        pending = self._pending_responses.pop(id(request), None)
        if pending is None:
            return
        aread = getattr(response, "aread", None)
        body = await aread() if callable(aread) else bytes(getattr(response, "content", b""))
        response_row = {
            key: value
            for key, value in pending.items()
            if key not in {"event", "request_body", "request_json"}
        }
        response_row.update(
            {
                "event": "physical_response",
                "http_status": getattr(response, "status_code", None),
                "response_sha256": hashlib.sha256(body).hexdigest(),
                "response_body": body.decode("utf-8", errors="replace"),
                "response_json": _json_body(body),
            }
        )
        if self.model_io_callback is not None:
            self.model_io_callback(response_row)

    def set_active_turn(self, turn_id: str) -> None:
        """Set the current frozen turn without entering the provider body."""
        self.active_turn_id = str(turn_id)

    def bind_model_io(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Bind append-only model-I/O custody."""
        self.model_io_callback = callback

    def logical_call_started(self, event: Mapping[str, Any]) -> None:
        """Track role and model alongside the existing logical identity."""
        self.active_logical_index = int(event["index"])
        self.active_role = str(event.get("generation_role", ""))
        self.active_model = str(event.get("model", ""))
        self._attempts[self.active_logical_index] = 0

    def logical_call_completed(self, event: Mapping[str, Any]) -> None:
        """Persist the canonical backend parse/validation result."""
        if self.model_io_callback is not None:
            response_reason = event.get("response_reason")
            if hasattr(response_reason, "value"):
                response_reason = response_reason.value
            validation_shape = event.get("validation_shape")
            to_json = getattr(validation_shape, "to_json", None)
            if callable(to_json):
                validation_shape = to_json()
            self.model_io_callback(
                {
                    "event": "logical_call_result",
                    "logical_call_index": event.get("index"),
                    "role": event.get("generation_role"),
                    "model": event.get("model"),
                    "engine_outcome": event.get("outcome"),
                    "failure_category": event.get("failure_category"),
                    "response_reason": response_reason,
                    "validation_shape": validation_shape,
                }
            )


def _json_body(body: bytes) -> object:
    """Parse a captured JSON body without changing its separately hashed bytes."""
    try:
        return json.loads(body)
    except (TypeError, ValueError):
        return None


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    """Reject header-like keys anywhere in structured model-I/O data."""
    if isinstance(value, Mapping):
        return any(
            str(key).casefold() in forbidden or _contains_forbidden_key(item, forbidden)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


class _ObservedLiveAdapter:
    """Add D5 custody hooks around the accepted D4 canonical adapter."""

    observes_physical_attempts = True

    def __init__(self, inner: object, observer: _PhysicalAttemptObserver) -> None:
        self.inner = inner
        self.observer = observer

    def bind_call_started(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Bind logical custody and select the active HTTP call."""

        def wrapped(event: dict[str, Any]) -> None:
            self.observer.logical_call_started(event)
            callback(event)

        self.inner.bind_call_started(wrapped)

    def bind_call_completed(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Forward bounded logical completion custody."""

        def wrapped(event: dict[str, Any]) -> None:
            self.observer.logical_call_completed(event)
            callback(event)

        self.inner.bind_call_completed(wrapped)

    def bind_physical_attempt(self, callback: Callable[[int], None]) -> None:
        """Bind the D5 ledger to each observed SDK transport attempt."""
        self.observer.callback = callback

    def set_active_turn(self, turn_id: str) -> None:
        """Bind model-I/O records to the current campaign turn."""
        self.observer.set_active_turn(turn_id)

    def bind_model_io(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Bind exact transport body capture to campaign custody."""
        self.observer.bind_model_io(callback)

    @property
    def logical_call_count(self) -> int:
        """Expose the canonical adapter's logical cursor."""
        return int(self.inner.logical_call_count)

    async def execute_turn(
        self,
        case: Mapping[str, Any],
        expected: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Execute through the accepted Direct Notebook adapter."""
        return await self.inner.execute_turn(case, expected)


def create_live_adapter(
    *,
    repo_root: Path,
    artifact_root: Path,
    api_key: str,
    project_config: ProjectConfig,
    http_client_factory: Callable[[Callable[[object], Any]], object] | None = None,
    base_url: str | None = None,
    model: str | None = None,
    provider_name: str | None = None,
    request_options: Mapping[str, object] | None = None,
    require_thinking_control: bool = False,
) -> _ObservedLiveAdapter:
    """Build the accepted canonical adapter with retry-visible HTTP transport."""
    import httpx
    from openai import AsyncOpenAI

    from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2

    _validate_project_config(project_config)
    if require_thinking_control:
        request_options = _validated_thinking_control_options(request_options)
    observer = _PhysicalAttemptObserver()
    http_client = (
        http_client_factory(observer)
        if http_client_factory is not None
        else httpx.AsyncClient(
            event_hooks={"request": [observer.on_request], "response": [observer.on_response]}
        )
    )
    resolved_base_url = base_url or project_config.openai_compat_base_url
    resolved_model = model or project_config.provider.model
    resolved_provider = provider_name or project_config.provider.name
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=resolved_base_url,
        timeout=project_config.provider.timeout_seconds,
        max_retries=project_config.provider.max_retries,
        http_client=http_client,
    )
    backend = OpenAICompatibleBackendV2(
        model=resolved_model,
        client=client,
        structured_output=project_config.runtime.structured_output,
        request_options=request_options,
    )
    calls: list[Any] = []
    ledger = d4.LogicalCallLedger()
    counted = d4.CountingBackend(
        delegate=backend,
        provider=resolved_provider,
        model=resolved_model,
        calls=calls,
        ledger=ledger,
    )
    session = d4.build_notebook_session(
        backend=counted,
        provider=resolved_provider,
        model=resolved_model,
        server_root=repo_root,
        credential_source="configured",
        timeout=project_config.provider.timeout_seconds,
    )
    inner = d4.D4CampaignAdapter(
        repo_root=repo_root,
        artifact_root=artifact_root,
        session=session,
        call_source=d4.CampaignCallSource(backends=(counted,), calls=calls, ledger=ledger),
        provider_backed=True,
    )
    return _ObservedLiveAdapter(inner, observer)


def _credential_bearing_json_get(url: str, api_key: str) -> object:
    """Read one bounded readiness response without retaining its raw body."""
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20.0) as response:
            if response.geturl() != url:
                raise D5ReadinessError("endpoint_identity_mismatch", 0)
            body = response.read(MAX_ENDPOINT_RESPONSE_BYTES + 1)
    except D5ReadinessError:
        raise
    except urllib.error.HTTPError as error:
        if error.code in {401, 403}:
            reason = "endpoint_authentication_failed"
        elif error.code == 404:
            reason = "endpoint_path_not_found"
        elif 500 <= error.code <= 599:
            reason = "endpoint_server_error"
        else:
            reason = "endpoint_http_error"
        raise D5ReadinessError(reason, 0, http_status=error.code) from None
    except urllib.error.URLError as error:
        cause = error.reason
        if isinstance(cause, (TimeoutError,)):
            reason = "endpoint_timeout"
        elif isinstance(cause, ConnectionRefusedError):
            reason = "endpoint_connection_refused"
        elif isinstance(cause, OSError) and cause.errno in {
            errno.ENETUNREACH,
            errno.EHOSTUNREACH,
        }:
            reason = "endpoint_network_unreachable"
        else:
            reason = "endpoint_transport_error"
        raise D5ReadinessError(reason, 0) from None
    except TimeoutError:
        raise D5ReadinessError("endpoint_timeout", 0) from None
    except ConnectionRefusedError:
        raise D5ReadinessError("endpoint_connection_refused", 0) from None
    except OSError as error:
        reason = (
            "endpoint_network_unreachable"
            if error.errno in {errno.ENETUNREACH, errno.EHOSTUNREACH}
            else "endpoint_transport_error"
        )
        raise D5ReadinessError(reason, 0) from None
    if len(body) > MAX_ENDPOINT_RESPONSE_BYTES:
        raise D5ReadinessError("endpoint_identity_mismatch", 0)
    try:
        return json.loads(body)
    except (TypeError, ValueError):
        raise D5ReadinessError("endpoint_identity_mismatch", 0) from None


def execute_live_campaign(
    *,
    repo_root: Path,
    authorization: D5Authorization,
    artifact_root: Path,
    endpoint_get: Callable[[str, str], object] = _credential_bearing_json_get,
    api_key_loader: Callable[[], str] | None = None,
    static_checker: Callable[[Path, D5Authorization, EvidencePaths], dict[str, Any]] | None = None,
    provider_factory: Callable[[Path, Path, str], object] | None = None,
    turn_ids: Sequence[str] = FROZEN_TURN_IDS,
    mode: str = "scientific",
) -> dict[str, Any]:
    """Run selected frozen turns after static/readiness interlocks."""
    if artifact_root.resolve() != _authorized_artifact_root(repo_root, authorization):
        raise D5StaticPreflightError("artifact root is not authorized")
    project_config = load_project_config(repo_root)
    _validate_project_config(project_config)
    if authorization.project_config_fingerprint_sha256 != project_config.fingerprint_sha256:
        raise D5StaticPreflightError("project configuration fingerprint mismatch")
    paths = EvidencePaths(artifact_root, authorization.campaign_id)
    static = provider_free_preflight(
        repo_root,
        authorization,
        paths,
        static_checker=static_checker,
    )
    load_key = api_key_loader or (lambda: d4.load_d4_api_key(repo_root))
    build_provider = provider_factory or (
        lambda key_root, key_artifact_root, token: create_live_adapter(
            repo_root=key_root,
            artifact_root=key_artifact_root,
            api_key=token,
            project_config=project_config,
            request_options=authorization.thinking_control_options,
            require_thinking_control=True,
        )
    )
    readiness = prepare_readiness(
        authorization=authorization,
        project_config=project_config,
        api_key_loader=load_key,
        endpoint_get=endpoint_get,
        static_preflight=static,
        provider_factory=lambda token: build_provider(repo_root, artifact_root, token),
    )
    if readiness.adapter is None:
        raise D5ReadinessError("provider_construction_failed", 2)
    runner = D5CampaignRunner(
        repo_root=repo_root,
        authorization=authorization,
        paths=paths,
        readiness=readiness,
        provenance={
            "authorization_id": authorization.authorization_id,
            "implementation_checkpoint": authorization.implementation_checkpoint,
            "accepted_d5_engine_checkpoint": authorization.accepted_d5_engine_checkpoint,
            "accepted_d5_design_checkpoint": authorization.accepted_d5_design_checkpoint,
            "accepted_h_implementation_checkpoint": (
                authorization.accepted_h_implementation_checkpoint
            ),
        },
    )
    return asyncio.run(runner.run(readiness.adapter, turn_ids=turn_ids, mode=mode))


def execute_live_smoke(
    *,
    repo_root: Path,
    authorization: D5Authorization,
    artifact_root: Path,
    endpoint_get: Callable[[str, str], object] = _credential_bearing_json_get,
    api_key_loader: Callable[[], str] | None = None,
    static_checker: Callable[[Path, D5Authorization, EvidencePaths], dict[str, Any]] | None = None,
    provider_factory: Callable[[Path, Path, str], object] | None = None,
) -> dict[str, Any]:
    """Run one frozen turn through the same canonical campaign runner."""
    try:
        result = execute_live_campaign(
            repo_root=repo_root,
            authorization=authorization,
            artifact_root=artifact_root,
            endpoint_get=endpoint_get,
            api_key_loader=api_key_loader,
            static_checker=static_checker,
            provider_factory=provider_factory,
            turn_ids=("D4-C01:C01",),
            mode="smoke",
        )
    except D5ReadinessError as error:
        return {
            "status": "SMOKE_NOT_READY",
            "readiness": _readiness_failure_result(error),
            "provider_calls": 0,
            "model_calls": 0,
        }
    result["status"] = result.pop("smoke_status")
    return result


def _turn_hash(value: object) -> str | None:
    """Hash allowed artifact values while excluding their filesystem paths."""
    if isinstance(value, Mapping):
        for key in ("ending_artifact_path", "after_path", "artifact_path", "render_path"):
            digest = _safe_hash(value.get(key))
            if digest:
                return digest
    return None


def _bounded_turn_row(
    case: Mapping[str, Any],
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    grade: Mapping[str, Any],
    *,
    execution_index: int,
    call_count: int,
    physical_attempt_count: int,
    provider: str = EXPECTED_PROVIDER,
    model: str = EXPECTED_MODEL,
    observed_failure: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Project one D4 actual/grade pair into redacted D5 evidence."""
    projected_actual = dict(actual)
    projected_actual.setdefault(
        "correction_preservation",
        _derive_correction_preservation(actual, expected),
    )
    projected_actual["contract_or_input_failure"] = _derive_contract_or_input_failure(actual)
    verifier = grade.get("verifier_requirements", [])
    status = str(grade.get("status"))
    outcome = "PASS" if status == "PASS" else "INCONCLUSIVE" if status == "INCONCLUSIVE" else "FAIL"
    first_divergence = _first_divergence(projected_actual, grade, observed_failure)
    failure_category = (
        observed_failure[1]
        if observed_failure is not None
        else classify_grade_failure(projected_actual, grade)
    )
    scientific_terminal = _turn_scientific_terminal(
        grade=grade,
        actual=projected_actual,
        observed_failure=observed_failure,
        first_divergence=first_divergence,
        failure_category=failure_category,
    )
    return {
        "experiment_version": D5_EXPERIMENT_VERSION,
        "case_id": case.get("case_id"),
        "turn_id": case["turn_id"],
        "execution_index": execution_index,
        "request_sha256": case.get("request_sha256"),
        "result_status": grade.get("status"),
        "outcome": outcome,
        "grader_status": grade.get("status"),
        "diagnostics": list(grade.get("errors", [])),
        "verifier_requirements": verifier,
        "starting_artifact_sha256": _safe_hash(projected_actual.get("starting_artifact_path")),
        "ending_artifact_sha256": _safe_hash(projected_actual.get("ending_artifact_path")),
        "render_sha256": _safe_hash(projected_actual.get("render_path")),
        "persisted": projected_actual.get("persisted") is True,
        "rendered": projected_actual.get("rendered") is True,
        "worker_status": projected_actual.get("worker_status", "NOT_ESTABLISHED"),
        "worker_diagnostic_code": projected_actual.get("worker_diagnostic_code"),
        "normalization_status": projected_actual.get("normalization_status", "NOT_ESTABLISHED"),
        "worker_obligation_status": projected_actual.get(
            "worker_obligation_status", "NOT_ESTABLISHED"
        ),
        "lowering_status": projected_actual.get("lowering_status", "NOT_ESTABLISHED"),
        "reconciliation_status": projected_actual.get("reconciliation_status"),
        "apply_status": projected_actual.get("apply_status"),
        "failure_owner": projected_actual.get("failure_owner"),
        "intent_applied": projected_actual.get("intent_applied") is True,
        "worker_stage_evidence": projected_actual.get("worker_stage_evidence", []),
        "host_stage_evidence": projected_actual.get("host_stage_evidence", {}),
        "logical_generation_calls": call_count,
        "physical_attempts": physical_attempt_count,
        "provider": provider,
        "model": model,
        "first_divergence": first_divergence,
        "scientific_terminal": scientific_terminal,
        "failure_category": failure_category,
        "evidence_dimensions": _dimension_evidence(
            case=case,
            expected=expected,
            actual=projected_actual,
            grade=grade,
            first_divergence=first_divergence,
            observed_failure=observed_failure,
        ),
        "correction_preservation": _correction_preservation_evidence(projected_actual),
        "contract_or_input_failure": projected_actual["contract_or_input_failure"],
    }


_INFRASTRUCTURE_GRADE_ERRORS = frozenset(
    {
        "persistence_not_proven",
        "render_not_proven",
        "cbl_persistence_not_proven",
        "cbl_render_not_proven",
        "cbl_rendered_wrong_artifact",
    }
)
_HOST_FAILURE_CATEGORIES = frozenset(
    {
        "HOST_NORMALIZATION",
        "HOST_SEMANTIC_APPLICATION",
        "HOST_EXECUTION",
        "PERSISTENCE",
        "RENDER",
    }
)


def classify_grade_failure(actual: Mapping[str, Any], grade: Mapping[str, Any]) -> str | None:
    """Classify the earliest observed host boundary before persistence grading."""
    if actual.get("normalization_status") == "FAIL":
        return "HOST_NORMALIZATION"
    if actual.get("lowering_status") == "FAIL":
        return "HOST_SEMANTIC_APPLICATION"
    apply_status = str(actual.get("apply_status", ""))
    if apply_status in {"compile_failed", "reconciliation_blocked", "validation_failed"}:
        return "HOST_SEMANTIC_APPLICATION"
    if apply_status in {"post_lowering_obligation_failed", "execution_failed"}:
        return "HOST_EXECUTION"
    errors = {str(error) for error in grade.get("errors", [])}
    if not errors.intersection(_INFRASTRUCTURE_GRADE_ERRORS):
        return None
    host_stage_evidence = actual.get("host_stage_evidence")
    if isinstance(host_stage_evidence, Mapping) and host_stage_evidence:
        if actual.get("persisted") is True and actual.get("rendered") is False:
            return "RENDER"
        if actual.get("persisted") is False:
            return "PERSISTENCE"
    if actual.get("apply_status") in {
        "rejected",
        "compile_failed",
        "reconciliation_blocked",
        "execution_failed",
    }:
        return None
    evidence = actual.get("execution_evidence")
    if isinstance(evidence, Mapping) and evidence.get("accepted") is True:
        return "PRODUCTION_OR_INFRASTRUCTURE"
    return None


_STRUCTURED_OUTPUT_FAILURE_CATEGORIES = frozenset({"configuration", "provider_rejected"})
_PROVIDER_RUNTIME_FAILURE_CATEGORIES = frozenset(
    {"transport", "timeout", "rate_limit", "authentication"}
)


def _classify_logical_call_failure(
    calls: Sequence[Mapping[str, Any]],
) -> tuple[str, str] | None:
    """Classify stable provider custody categories before semantic grading."""
    categories = [
        str(call.get("failure_category"))
        for call in calls
        if call.get("failure_category") is not None
    ]
    if any(category in _STRUCTURED_OUTPUT_FAILURE_CATEGORIES for category in categories):
        return "PROVIDER_BOUNDARY / STRUCTURED_OUTPUT", next(
            category for category in categories if category in _STRUCTURED_OUTPUT_FAILURE_CATEGORIES
        )
    if any(category in _PROVIDER_RUNTIME_FAILURE_CATEGORIES for category in categories):
        return "PROVIDER_OR_TRANSPORT_RUNTIME", next(
            category for category in categories if category in _PROVIDER_RUNTIME_FAILURE_CATEGORIES
        )
    return None


def _classify_exception(error: Exception) -> tuple[str, str]:
    """Map bounded post-STARTED failures without exposing exception text."""
    if isinstance(error, D5StructuredOutputRejected):
        return "INCONCLUSIVE", "PROVIDER_BOUNDARY / STRUCTURED_OUTPUT"
    if isinstance(error, (D5TransportFailure, TimeoutError, OSError)):
        return "INCONCLUSIVE", "TRANSPORT_RUNTIME"
    if isinstance(error, D5ProductionFailure):
        return "INCONCLUSIVE", "PRODUCTION_DEFECT"
    if isinstance(error, D5ProcessInterruption):
        return "INCONCLUSIVE", "PROCESS_INTERRUPTION"
    if isinstance(error, D5CallCapExceeded):
        return "INCONCLUSIVE", "CALL_CAP_EXCEEDED"
    if isinstance(error, D5HarnessError):
        return "INCONCLUSIVE", "EVIDENCE_INTEGRITY"
    return "INCONCLUSIVE", "EXECUTION_INTERNAL_ERROR"


def _first_divergence_for_exception(error: Exception) -> str:
    """Map a post-STARTED exception to the earliest bounded evidence layer."""
    if isinstance(error, (D5StructuredOutputRejected, D5TransportFailure, TimeoutError)):
        return "PROVIDER_OR_STRUCTURED"
    return "HARNESS"


def _first_divergence(
    actual: Mapping[str, Any],
    grade: Mapping[str, Any],
    observed_failure: tuple[str, str] | None,
) -> str:
    """Select the earliest evidence-supported turn divergence."""
    if observed_failure is not None:
        return "PROVIDER_OR_STRUCTURED"
    declared = actual.get("first_divergence")
    if isinstance(declared, str) and declared in D5I_FIRST_DIVERGENCES:
        return declared
    if actual.get("harness_failure") is True:
        return "HARNESS"
    if actual.get("normalization_status") == "FAIL":
        return "HOST_EXECUTION"
    if actual.get("lowering_status") == "FAIL" or str(actual.get("apply_status")) in {
        "compile_failed",
        "reconciliation_blocked",
        "validation_failed",
        "post_lowering_obligation_failed",
        "execution_failed",
    }:
        return "HOST_EXECUTION"
    errors = {str(error) for error in grade.get("errors", [])}
    if any(
        "canonical_change_outside" in error or "failure_bytes_changed" in error for error in errors
    ):
        return "CORRECTION_PRESERVATION"
    if any("persistence" in error or "render" in error for error in errors):
        return "PERSISTENCE_RELOAD_RENDER"
    if any("diagnostic" in error or "owner" in error or "mutation" in error for error in errors):
        return "HOST_EXECUTION"
    if any("capability" in error or "parent" in error for error in errors):
        return "CAPABILITY"
    if any("source" in error or "channel" in error for error in errors):
        return "SOURCE_CHANNEL_GROUNDING"
    if any("target" in error or "section" in error for error in errors):
        return "TARGET_GROUNDING"
    if any("schema" in error or "work_unit" in error for error in errors):
        return "PLANNER_STRUCTURAL"
    if errors:
        return "SEMANTIC"
    return "NONE"


def _correction_preservation_evidence(actual: Mapping[str, Any]) -> dict[str, Any]:
    """Project only bounded H correction evidence when a correction occurred."""
    raw = actual.get("correction_preservation")
    if isinstance(raw, Mapping):
        allowed = {
            "status",
            "diagnostic_code",
            "authorized_paths",
            "before_semantic_projection_sha256",
            "after_semantic_projection_sha256",
            "changed_paths",
            "unauthorized_change",
            "final_status",
        }
        return {
            str(key): value
            for key, value in raw.items()
            if str(key) in allowed and isinstance(value, (str, bool, list, tuple))
        }
    if actual.get("correction_occurred") is True:
        return {"status": "NOT_ESTABLISHED"}
    return {"status": "NOT_APPLICABLE"}


def _derive_correction_preservation(
    actual: Mapping[str, Any], expected: Mapping[str, Any]
) -> dict[str, Any]:
    """Derive G7 evidence from the canonical adapter's before/after artifacts."""
    if isinstance(actual.get("correction_preservation"), Mapping):
        return dict(actual["correction_preservation"])
    repair_count = actual.get("worker_repair_count", 0)
    if not actual.get("correction_occurred") and not (
        isinstance(repair_count, int) and repair_count > 0
    ):
        return {"status": "NOT_APPLICABLE"}
    before = actual.get("canonical_before")
    after = actual.get("canonical_after")
    contract = expected.get("contract")
    if (
        not isinstance(before, Mapping)
        or not isinstance(after, Mapping)
        or not isinstance(contract, Mapping)
    ):
        return {"status": "NOT_ESTABLISHED"}
    changed_paths = d4._changed_paths(before, after)
    allowed_paths = [str(path) for path in contract.get("allowed_change_paths", [])]
    unauthorized = any(
        not any(
            path == allowed
            or path.startswith(allowed.rstrip("/") + "/")
            or allowed.startswith(path.rstrip("/") + "/")
            for allowed in allowed_paths
        )
        for path in changed_paths
    )
    return {
        "status": "OBSERVED",
        "diagnostic_code": actual.get("diagnostic_code"),
        "authorized_paths": allowed_paths,
        "before_semantic_projection_sha256": _sha256_json(before),
        "after_semantic_projection_sha256": _sha256_json(after),
        "changed_paths": changed_paths,
        "unauthorized_change": unauthorized,
        "final_status": "REJECTED" if unauthorized else "ACCEPTED",
    }


_CONTRACT_INPUT_DIAGNOSTIC_CODES = frozenset(
    {
        "contract_violation",
        "input_contract_violation",
        "semantic_contract_incomplete",
        "missing_existing_section_hint",
        "missing_required_field",
        "source_inventory_unavailable",
        "channel_inventory_unavailable",
        "insufficient_source_inventory",
        "insufficient_channel_inventory",
    }
)


def _derive_contract_or_input_failure(actual: Mapping[str, Any]) -> bool:
    """Classify closed-contract/input contradictions from observed facts."""
    if actual.get("contract_or_input_failure") is True:
        return True
    diagnostic_codes = {
        str(item.get("code"))
        for item in actual.get("diagnostics", [])
        if isinstance(item, Mapping) and item.get("code") is not None
    }
    if diagnostic_codes.intersection(_CONTRACT_INPUT_DIAGNOSTIC_CODES):
        return True
    if str(actual.get("failure_owner", "")).casefold() in {
        "contract",
        "input",
        "inventory",
    }:
        return True
    return any(
        actual.get(field) in {"missing", "unavailable", "insufficient"}
        for field in ("inventory_state", "source_inventory_state", "channel_inventory_state")
    )


def _dimension_evidence(
    *,
    case: Mapping[str, Any],
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    grade: Mapping[str, Any],
    first_divergence: str,
    observed_failure: tuple[str, str] | None,
) -> dict[str, str]:
    """Project independent bounded states without inferring hidden model work."""
    provided = actual.get("evidence_dimensions")
    dimensions = dict.fromkeys(D5I_DIMENSIONS, "NOT_ESTABLISHED")
    if isinstance(provided, Mapping):
        for name in D5I_DIMENSIONS:
            value = provided.get(name)
            if value in {"PASS", "FAIL", "NOT_REACHED", "NOT_APPLICABLE", "NOT_ESTABLISHED"}:
                dimensions[name] = str(value)
    if observed_failure is not None:
        dimensions["provider_structured"] = (
            "FAIL"
            if observed_failure[1] in _STRUCTURED_OUTPUT_FAILURE_CATEGORIES
            else "NOT_REACHED"
        )
        for name in D5I_DIMENSIONS[1:]:
            if dimensions[name] == "NOT_ESTABLISHED":
                dimensions[name] = "NOT_REACHED"
        return dimensions

    grade_status = str(grade.get("status"))
    dimensions["provider_structured"] = "PASS"
    dimensions["planner_structural"] = "PASS"
    contract = expected.get("contract")
    contract_kind = str(contract.get("kind", "")) if isinstance(contract, Mapping) else ""
    if contract_kind == "safety":
        dimensions["semantic"] = "NOT_APPLICABLE"
        dimensions["safe_negative"] = "PASS" if grade_status == "PASS" else "FAIL"
        dimensions["mutation"] = "PASS" if actual.get("changed") is False else "FAIL"
        dimensions["target_grounding"] = "NOT_APPLICABLE"
        dimensions["source_channel_grounding"] = "NOT_APPLICABLE"
        dimensions["capability"] = "NOT_APPLICABLE"
    elif grade_status == "PASS":
        for name in ("semantic", "target_grounding", "source_channel_grounding", "capability"):
            dimensions[name] = "PASS"
    elif first_divergence in D5I_FIRST_DIVERGENCES:
        dimension_by_divergence = {
            "PLANNER_STRUCTURAL": "planner_structural",
            "SEMANTIC": "semantic",
            "TARGET_GROUNDING": "target_grounding",
            "SOURCE_CHANNEL_GROUNDING": "source_channel_grounding",
            "CAPABILITY": "capability",
            "CORRECTION_PRESERVATION": "correction_preservation",
            "HOST_EXECUTION": "mutation",
            "PERSISTENCE_RELOAD_RENDER": "persistence_reload_render",
            "DETERMINISTIC_GRADING": "deterministic_grading",
        }
        failing_dimension = dimension_by_divergence.get(first_divergence)
        if failing_dimension is not None:
            dimensions[failing_dimension] = "FAIL"

    mutation_errors = {
        "canonical_change_outside_allowed_paths",
        "failure_mutated_artifact",
        "failure_bytes_changed",
        "failure_canonical_state_changed",
        "prohibited_channel_substitution",
        "prohibited_path_mutation",
    }
    has_bad_mutation = any(error in mutation_errors for error in grade.get("errors", []))
    if has_bad_mutation:
        dimensions["mutation"] = "FAIL"
    elif grade_status == "PASS":
        dimensions["mutation"] = "PASS"
    else:
        dimensions["mutation"] = "NOT_ESTABLISHED"
    dimensions["persistence_reload_render"] = (
        "PASS"
        if actual.get("persisted") is True and actual.get("rendered") is True
        else "FAIL"
        if actual.get("persisted") is False or actual.get("rendered") is False
        else "NOT_ESTABLISHED"
    )
    dimensions["deterministic_grading"] = "PASS" if grade_status == "PASS" else "FAIL"
    return dimensions


def _turn_scientific_terminal(
    *,
    grade: Mapping[str, Any],
    actual: Mapping[str, Any],
    observed_failure: tuple[str, str] | None,
    first_divergence: str,
    failure_category: str | None = None,
) -> str:
    """Classify one turn using sealed evidence, not the expected gold outcome."""
    if observed_failure is not None:
        return "INCONCLUSIVE / PROVIDER"
    if actual.get("harness_failure") is True:
        return "INCONCLUSIVE / HARNESS"
    if failure_category in _HOST_FAILURE_CATEGORIES:
        return "INCONCLUSIVE / HARNESS"
    if grade.get("status") == "PASS":
        return "PASS"
    if actual.get("contract_or_input_failure") is True:
        return "FAIL / CONTRACT_OR_INPUT"
    if first_divergence == "HARNESS":
        return "INCONCLUSIVE / HARNESS"
    return "FAIL / RESIDUAL_SEMANTIC"


def _campaign_scientific_terminal(
    *,
    decision: str,
    attribution: str,
    rows: Sequence[Mapping[str, Any]],
    first_divergence: str,
) -> str:
    """Project legacy campaign outcomes into the D5-5I terminal taxonomy."""
    if first_divergence == "HARNESS":
        return "INCONCLUSIVE / HARNESS"
    if attribution.startswith(("PROVIDER", "TRANSPORT")):
        return "INCONCLUSIVE / PROVIDER"
    if attribution in _HOST_FAILURE_CATEGORIES:
        return "INCONCLUSIVE / HARNESS"
    if attribution in {
        "EVIDENCE_INTEGRITY",
        "EXECUTION_INTERNAL_ERROR",
        "PROCESS_INTERRUPTION",
        "CALL_CAP_EXCEEDED",
        "PRODUCTION_DEFECT",
        "POPULATION_INCOMPLETE",
    }:
        return "INCONCLUSIVE / HARNESS"
    if decision == "PASS" and len(rows) == len(FROZEN_TURN_IDS):
        return "PASS"
    if any(row.get("scientific_terminal") == "FAIL / CONTRACT_OR_INPUT" for row in rows):
        return "FAIL / CONTRACT_OR_INPUT"
    return "FAIL / RESIDUAL_SEMANTIC"


class D5CampaignRunner:
    """Execute one injected provider-free or future live campaign."""

    def __init__(
        self,
        *,
        repo_root: Path,
        authorization: D5Authorization,
        paths: EvidencePaths,
        readiness: D5OperationalReadiness,
        provenance: Mapping[str, Any],
    ) -> None:
        """Retain one exact campaign context before STARTED."""
        self.repo_root = repo_root
        self.authorization = authorization
        self.paths = paths
        self.readiness = readiness
        self.provenance = dict(provenance)
        self._started = False
        self._finished = False

    async def run(
        self,
        adapter: object,
        *,
        turn_ids: Sequence[str] = FROZEN_TURN_IDS,
        mode: str = "scientific",
    ) -> dict[str, Any]:
        """Run selected frozen turns through the shared canonical adapter."""
        if self._started or self._finished:
            raise D5HarnessError("campaign cannot be resumed or invoked twice")
        if mode not in {"smoke", "scientific"}:
            raise D5HarnessError("unknown campaign mode")
        selected_ids = tuple(str(turn_id) for turn_id in turn_ids)
        if not selected_ids or len(set(selected_ids)) != len(selected_ids):
            raise D5StaticPreflightError("selected turn population is invalid")
        if any(turn_id not in FROZEN_TURN_IDS for turn_id in selected_ids):
            raise D5StaticPreflightError("selected turn is outside the frozen population")
        if selected_ids != tuple(turn_id for turn_id in FROZEN_TURN_IDS if turn_id in selected_ids):
            raise D5StaticPreflightError("selected turn order drifted")
        if self.readiness.live and (
            self.paths.root.resolve()
            != _authorized_artifact_root(self.repo_root, self.authorization)
        ):
            raise D5StaticPreflightError("artifact root is not authorized")
        self._started = True
        custody = D5CampaignCustody.prepare(
            self.paths,
            authorization=self.authorization,
            provenance=self.provenance,
            readiness=self.readiness.projection,
            live=self.readiness.live,
            endpoint_call_count=len(self.readiness.endpoint_calls),
            mode=mode,
        )
        custody.require_physical_observer = bool(
            getattr(adapter, "observes_physical_attempts", False)
        )
        rows: list[dict[str, Any]] = []
        campaign_first_divergence = "NONE"
        try:
            if callable(getattr(adapter, "bind_call_started", None)):
                adapter.bind_call_started(custody.record_call_started)
            if callable(getattr(adapter, "bind_call_completed", None)):
                adapter.bind_call_completed(custody.record_call_completed)
            if callable(getattr(adapter, "bind_physical_attempt", None)):
                adapter.bind_physical_attempt(custody.record_physical_attempt)
            if callable(getattr(adapter, "bind_model_io", None)):
                adapter.bind_model_io(custody.record_model_io)
            cases = d4.load_cases(self.repo_root)
            gold = {item["turn_id"]: item for item in d4.load_gold(self.repo_root)["cases"]}
            if tuple(item["turn_id"] for item in cases) != FROZEN_TURN_IDS:
                raise D5StaticPreflightError("D5 population order drifted")
            selected_cases = [case for case in cases if case["turn_id"] in selected_ids]
            if tuple(case["turn_id"] for case in selected_cases) != selected_ids:
                raise D5StaticPreflightError("selected turn population drifted")
            execute_turn = getattr(adapter, "execute_turn", None)
            if not callable(execute_turn):
                raise D5ProductionFailure("adapter has no canonical execute_turn")
            for execution_index, case in enumerate(selected_cases, start=1):
                custody.begin_turn(str(case["turn_id"]))
                if callable(getattr(adapter, "set_active_turn", None)):
                    adapter.set_active_turn(str(case["turn_id"]))
                expected = gold[case["turn_id"]]
                cursor = int(getattr(adapter, "logical_call_count", 0))
                physical_cursor = custody.ledger.physical_attempts
                started = time.perf_counter()
                actual = await execute_turn(case, expected)
                observed_failure = _classify_logical_call_failure(custody.ledger.calls[cursor:])
                grade = (
                    {"status": "INCONCLUSIVE", "errors": [], "verifier_requirements": []}
                    if observed_failure is not None
                    else d4.grade_turn(dict(actual), expected)
                )
                calls = int(getattr(adapter, "logical_call_count", 0)) - cursor
                row = _bounded_turn_row(
                    case,
                    expected,
                    actual,
                    grade,
                    execution_index=execution_index,
                    call_count=calls,
                    physical_attempt_count=custody.ledger.physical_attempts - physical_cursor,
                    provider=self.authorization.provider,
                    model=self.authorization.model,
                    observed_failure=observed_failure,
                )
                row["duration_seconds"] = round(time.perf_counter() - started, 6)
                row["authorization_id"] = self.authorization.authorization_id
                row["failure_category"] = (
                    observed_failure[1]
                    if observed_failure is not None
                    else classify_grade_failure(actual, grade)
                )
                row["infrastructure_failure"] = (
                    observed_failure is not None or row["failure_category"] is not None
                )
                if observed_failure is not None:
                    row["attribution"] = observed_failure[0]
                elif row["failure_category"] in _HOST_FAILURE_CATEGORIES:
                    row["attribution"] = row["failure_category"]
                if campaign_first_divergence == "NONE":
                    campaign_first_divergence = str(row["first_divergence"])
                custody.append_turn(row)
                rows.append(row)
                if row["infrastructure_failure"]:
                    break
            provider_attributions = [
                str(row["attribution"]) for row in rows if row.get("attribution") is not None
            ]
            if provider_attributions:
                decision, attribution = "INCONCLUSIVE", provider_attributions[0]
            elif any(row.get("failure_category") in _HOST_FAILURE_CATEGORIES for row in rows):
                decision, attribution = "INCONCLUSIVE", next(
                    row["failure_category"]
                    for row in rows
                    if row.get("failure_category") in _HOST_FAILURE_CATEGORIES
                )
            elif any(row["infrastructure_failure"] for row in rows):
                decision, attribution = "INCONCLUSIVE", "PRODUCTION_OR_INFRASTRUCTURE"
            elif len(rows) != len(selected_ids):
                decision, attribution = "INCONCLUSIVE", "POPULATION_INCOMPLETE"
            elif all(row["grader_status"] == "PASS" for row in rows):
                decision, attribution = "PASS", "DETERMINISTIC_GRADING"
            else:
                decision, attribution = "FAIL", "SEMANTIC_CONTRACT"
        except Exception as error:
            observed_failure = _classify_logical_call_failure(custody.ledger.calls)
            if observed_failure is not None:
                decision, attribution = "INCONCLUSIVE", observed_failure[0]
            else:
                decision, attribution = _classify_exception(error)
            if campaign_first_divergence == "NONE":
                campaign_first_divergence = _first_divergence_for_exception(error)
        scientific_terminal = (
            _campaign_scientific_terminal(
                decision=decision,
                attribution=attribution,
                rows=rows,
                first_divergence=campaign_first_divergence,
            )
            if mode == "scientific"
            else None
        )
        if not custody.started:
            self._finished = True
            smoke_status = None
            if mode == "smoke":
                smoke_status = "SMOKE_INCONCLUSIVE"
            return {
                "mode": mode,
                "decision": decision,
                "attribution": attribution,
                "completed_turns": len(rows),
                "rows": rows,
                "terminal": None,
                "logical_generation_calls": custody.ledger.logical_calls,
                "physical_generation_attempts": custody.ledger.physical_attempts,
                "custody_digests": {},
                "provider_calls": 0,
                "endpoint_calls": len(self.readiness.endpoint_calls) if self.readiness.live else 0,
                "model_calls": 0,
                "scientific_terminal": scientific_terminal,
                "first_divergence": campaign_first_divergence,
                "started": False,
                "campaign_consumed": False,
                "smoke_status": smoke_status,
            }
        terminal = custody.finish(
            decision,
            attribution=attribution,
            rows=rows,
            scientific_terminal=scientific_terminal,
            first_divergence=campaign_first_divergence,
        )
        custody_digests = verify_custody_artifacts(self.paths)
        self._finished = True
        smoke_status = None
        if mode == "smoke":
            if decision == "PASS" and len(rows) == 1 and rows[0]["grader_status"] == "PASS":
                smoke_status = "SMOKE_PASS"
            elif (
                attribution.startswith(("PROVIDER", "TRANSPORT"))
                or attribution
                in {
                    "EVIDENCE_INTEGRITY",
                    "EXECUTION_INTERNAL_ERROR",
                    "PROCESS_INTERRUPTION",
                    "CALL_CAP_EXCEEDED",
                    "PRODUCTION_DEFECT",
                    "POPULATION_INCOMPLETE",
                }
                or attribution in _HOST_FAILURE_CATEGORIES
                or campaign_first_divergence == "HARNESS"
            ):
                smoke_status = "SMOKE_INCONCLUSIVE"
            else:
                smoke_status = "SMOKE_FAIL"
        return {
            "mode": mode,
            "decision": decision,
            "attribution": attribution,
            "completed_turns": len(rows),
            "rows": rows,
            "terminal": terminal,
            "logical_generation_calls": custody.ledger.logical_calls,
            "physical_generation_attempts": custody.ledger.physical_attempts,
            "custody_digests": custody_digests,
            "provider_calls": custody.ledger.logical_calls if self.readiness.live else 0,
            "endpoint_calls": len(self.readiness.endpoint_calls) if self.readiness.live else 0,
            "model_calls": custody.ledger.logical_calls if self.readiness.live else 0,
            "scientific_terminal": scientific_terminal,
            "first_divergence": campaign_first_divergence,
            "started": custody.started,
            "campaign_consumed": custody.started,
            "smoke_status": smoke_status,
        }


def provider_free_preflight(
    repo_root: Path,
    authorization: D5Authorization,
    paths: EvidencePaths,
    *,
    static_checker: Callable[[Path, D5Authorization, EvidencePaths], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run static D5-4 checks without credentials, endpoints, or providers."""
    project_config = load_project_config(repo_root)
    _validate_project_config(project_config)
    if authorization.project_config_fingerprint_sha256 != project_config.fingerprint_sha256:
        raise D5StaticPreflightError("project configuration fingerprint mismatch")
    checker = static_checker or _default_static_checks
    facts = checker(repo_root, authorization, paths)
    if facts.get("status") != "PASS":
        raise D5StaticPreflightError("provider-free static preflight failed")
    static_facts = dict(facts)
    static_facts.setdefault("project_config_fingerprint_sha256", project_config.fingerprint_sha256)
    return {
        "experiment_version": D5_EXPERIMENT_VERSION,
        "status": "PASS",
        "accepted_d5_engine_checkpoint": D5_ENGINE_CHECKPOINT,
        "accepted_d5_design_checkpoint": D5_DESIGN_CHECKPOINT,
        "accepted_h_implementation_checkpoint": D5I_ACCEPTED_H_IMPLEMENTATION_CHECKPOINT,
        "population": {"turns": 9, "turn_ids": list(FROZEN_TURN_IDS)},
        "logical_call_ceiling": MAX_LOGICAL_CALLS,
        "physical_attempt_upper_bound": MAX_PHYSICAL_ATTEMPTS,
        "role_logical_call_limits": dict(ROLE_LOGICAL_CALL_LIMITS),
        "scientific_terminals": sorted(D5I_SCIENTIFIC_TERMINALS),
        "first_divergences": sorted(D5I_FIRST_DIVERGENCES),
        "evidence_dimensions": list(D5I_DIMENSIONS),
        "provider_calls": 0,
        "endpoint_calls": 0,
        "model_calls": 0,
        "static": static_facts,
    }


def _load_authorization(path: Path) -> D5Authorization:
    """Load an external authorization record without printing its contents."""
    return D5Authorization.from_mapping(json.loads(path.read_text(encoding="utf-8")))


def _readiness_failure_result(error: D5ReadinessError) -> dict[str, Any]:
    """Return bounded pre-campaign failure evidence without endpoint payloads."""
    result: dict[str, Any] = {
        "experiment_version": D5_EXPERIMENT_VERSION,
        "status": "NOT_READY",
        "reason": error.reason,
        "endpoint_calls": error.endpoint_calls,
        "provider_calls": 0,
        "model_calls": 0,
        "started": False,
        "campaign_consumed": False,
    }
    if error.http_status is not None:
        result["http_status"] = error.http_status
    if error.mismatched_fields:
        result["mismatched_fields"] = list(error.mismatched_fields)
    return result


def main() -> int:
    """Run provider-free preflight, one smoke call, or one live campaign."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--provider-free-preflight", action="store_true")
    modes.add_argument("--execute-smoke", action="store_true")
    modes.add_argument("--execute-live", action="store_true")
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--authorization-json", type=Path, required=True)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    authorization = _load_authorization(args.authorization_json.resolve())
    artifact_root = (
        args.artifact_root.resolve()
        if args.artifact_root is not None
        else (repo_root / authorization.artifact_root).resolve()
    )
    paths = EvidencePaths(artifact_root, authorization.campaign_id)
    if args.provider_free_preflight:
        result = provider_free_preflight(repo_root, authorization, paths)
    elif args.execute_smoke:
        try:
            result = execute_live_smoke(
                repo_root=repo_root,
                authorization=authorization,
                artifact_root=artifact_root,
            )
        except D5ReadinessError as error:
            print(json.dumps(_readiness_failure_result(error), indent=2, sort_keys=True))
            return 2
    else:
        try:
            result = execute_live_campaign(
                repo_root=repo_root,
                authorization=authorization,
                artifact_root=artifact_root,
            )
        except D5ReadinessError as error:
            print(json.dumps(_readiness_failure_result(error), indent=2, sort_keys=True))
            return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
