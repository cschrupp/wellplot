"""Provider-free D5-4 live semantic qualification harness.

This module owns only the D5-4 orchestration and evidence boundary. It reuses
the accepted D4 cases, custody helpers, deterministic graders, and canonical
Direct Notebook adapter; it never creates a provider or performs network I/O
unless a future, separately authorized live runner supplies those operations.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts import nlp_d4_live_acceptance as d4

D5_EXPERIMENT_VERSION = "WELLPLOT-NLP-D5-4"
D5_DESIGN_CHECKPOINT = "1658c1593330620501baa4a551b965fa209cc95b"
D5_ENGINE_CHECKPOINT = "51fd23fe18ca77c067b0cdf702f88a57ba4c457d"
EXPECTED_PROVIDER = "openai_compat"
EXPECTED_MODEL = "qwen3.6-35b-a3b"
SERVER_ORIGIN = "http://192.168.2.140:8888"
OPENAI_COMPAT_BASE_URL = f"{SERVER_ORIGIN}/v1"
MODEL_CATALOG_URL = f"{OPENAI_COMPAT_BASE_URL}/models"
PROPS_URL = f"{SERVER_ORIGIN}/props"
EXPECTED_OPENAI_VERSION = "2.34.0"
EXPECTED_SDK_MAX_RETRIES = 2
MAX_LOGICAL_CALLS = 45
MAX_PHYSICAL_ATTEMPTS = 135
CONCURRENCY = 1
GENERATION_TIMEOUT_SECONDS = 900.0
MAX_ENDPOINT_RESPONSE_BYTES = 1_048_576
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

    def __init__(self, reason: str, endpoint_calls: int = 0) -> None:
        """Retain a bounded reason and truthful endpoint call count."""
        super().__init__(reason)
        self.reason = reason
        self.endpoint_calls = endpoint_calls


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


TERMINAL_DECISIONS = frozenset({"PASS", "FAIL", "INCONCLUSIVE", "ARCHITECTURAL_ESCALATION"})


@dataclass(frozen=True, slots=True)
class D5Authorization:
    """External facts required to qualify one exact harness checkout."""

    implementation_checkpoint: str
    accepted_d5_engine_checkpoint: str = D5_ENGINE_CHECKPOINT
    accepted_d5_design_checkpoint: str = D5_DESIGN_CHECKPOINT
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
    structured_output_contract: str = "json_schema"
    sdk_version: str = EXPECTED_OPENAI_VERSION
    sdk_max_retries: int = EXPECTED_SDK_MAX_RETRIES

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> D5Authorization:
        """Parse required authorization facts without deriving them locally."""
        if "implementation_checkpoint" not in value:
            raise D5StaticPreflightError("implementation checkpoint is missing")
        return cls(
            implementation_checkpoint=str(value["implementation_checkpoint"]),
            accepted_d5_engine_checkpoint=str(
                value.get("accepted_d5_engine_checkpoint", D5_ENGINE_CHECKPOINT)
            ),
            accepted_d5_design_checkpoint=str(
                value.get("accepted_d5_design_checkpoint", D5_DESIGN_CHECKPOINT)
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
            thinking_off=bool(value.get("thinking_off", True)),
            structured_output_contract=str(value.get("structured_output_contract", "json_schema")),
            sdk_version=str(value.get("sdk_version", EXPECTED_OPENAI_VERSION)),
            sdk_max_retries=int(value.get("sdk_max_retries", EXPECTED_SDK_MAX_RETRIES)),
        )


@dataclass(frozen=True, slots=True)
class D5ReadinessProjection:
    """Sanitized runtime identity and declared structured-output contract."""

    model_catalog: tuple[str, ...]
    model_path_basename: str
    model_path_fingerprint_sha256: str
    context_size: int
    build_info: str
    total_slots: int
    chat_template: str
    chat_template_caps: tuple[str, ...]
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
            "chat_template": self.chat_template,
            "chat_template_caps": list(self.chat_template_caps),
            "runtime_defaults_sha256": self.runtime_defaults_sha256,
            "thinking_off": self.thinking_off,
            "structured_output_contract": self.structured_output_contract,
            "gguf_byte_identity": self.gguf_byte_identity,
        }


def _sha256_json(value: object) -> str:
    """Hash a deterministic JSON projection."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    if authorization.accepted_d5_engine_checkpoint != D5_ENGINE_CHECKPOINT:
        raise D5StaticPreflightError("accepted D5 engine checkpoint drifted")
    if authorization.accepted_d5_design_checkpoint != D5_DESIGN_CHECKPOINT:
        raise D5StaticPreflightError("accepted D5 design checkpoint drifted")
    if authorization.provider != EXPECTED_PROVIDER or authorization.model != EXPECTED_MODEL:
        raise D5StaticPreflightError("provider/model contract drifted")
    if authorization.sdk_version != EXPECTED_OPENAI_VERSION:
        raise D5StaticPreflightError("OpenAI package contract drifted")
    if authorization.sdk_max_retries != EXPECTED_SDK_MAX_RETRIES:
        raise D5StaticPreflightError("SDK retry contract drifted")
    if authorization.structured_output_contract != "json_schema":
        raise D5StaticPreflightError("structured-output contract drifted")
    if not authorization.thinking_off:
        raise D5StaticPreflightError("thinking-off readiness precondition is absent")
    if not authorization.endpoint_identity:
        raise D5StaticPreflightError("authorized endpoint identity is missing")
    if not authorization.runtime_defaults_sha256:
        raise D5StaticPreflightError("authorized runtime-default fingerprint is missing")
    if authorization.minimum_context_size <= 0:
        raise D5StaticPreflightError("authorized minimum context size is missing")
    for path in (
        artifact_paths.state,
        artifact_paths.journal,
        artifact_paths.terminal,
        artifact_paths.summary,
        artifact_paths.evidence,
    ):
        if path.exists():
            raise D5StaticPreflightError(f"fresh artifact path already exists: {path.name}")

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

    try:
        version = importlib.metadata.version("openai")
        from openai import AsyncOpenAI

        retries = inspect.signature(AsyncOpenAI).parameters["max_retries"].default
    except (ImportError, KeyError, TypeError, ValueError, importlib.metadata.PackageNotFoundError):
        raise D5StaticPreflightError("OpenAI SDK retry contract cannot be inspected") from None
    if version != EXPECTED_OPENAI_VERSION or retries != EXPECTED_SDK_MAX_RETRIES:
        raise D5StaticPreflightError("OpenAI SDK version/retry contract drifted")

    static_attestation = _run_static_attestation(repo_root)
    return {
        "status": "PASS",
        "current_checkout": current,
        "accepted_d5_engine_checkpoint": D5_ENGINE_CHECKPOINT,
        "accepted_d5_design_checkpoint": D5_DESIGN_CHECKPOINT,
        "openai_version": version,
        "sdk_max_retries": retries,
        "logical_call_ceiling": MAX_LOGICAL_CALLS,
        "physical_attempt_upper_bound": MAX_PHYSICAL_ATTEMPTS,
        "concurrency": CONCURRENCY,
        "generation_timeout_seconds": GENERATION_TIMEOUT_SECONDS,
        "fallback": "NONE",
        "model_substitution": "FORBIDDEN",
        "d5_attestation": static_attestation,
    }


@dataclass(frozen=True, slots=True)
class EvidencePaths:
    """Fresh five-file custody namespace for one D5-4 campaign."""

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

    def all_paths(self) -> tuple[Path, ...]:
        """Return all collision-sensitive paths in deterministic order."""
        return (self.state, self.journal, self.terminal, self.summary, self.evidence)


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

    def reserve(self, role: str) -> int:
        """Reserve a role-tagged logical call before provider delegation."""
        if role not in {"planner", "report_worker", "section_worker"}:
            raise D5HarnessError("unknown generation role")
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
        return next_index

    def physical_attempt(self, logical_index: int) -> None:
        """Record one SDK-level attempt without reserving a new logical call."""
        if logical_index < 1 or logical_index > self.logical_calls:
            raise D5HarnessError("physical attempt references unknown logical call")
        if self.physical_attempts >= self.max_physical_attempts:
            raise D5CallCapExceeded("physical attempt ceiling exceeded")
        self.physical_attempts += 1
        row = self.calls[logical_index - 1]
        row["physical_attempt_count"] += 1

    def complete(self, logical_index: int, outcome: str) -> None:
        """Close one logical call with bounded outcome metadata."""
        if outcome not in {"completed", "failed", "rejected"}:
            raise D5HarnessError("unknown logical-call outcome")
        self.calls[logical_index - 1]["outcome"] = outcome

    def record_d4_event(self, event: Mapping[str, Any]) -> None:
        """Attach D4 CountingBackend events to this D5 ledger."""
        event_name = event.get("event")
        index = int(event.get("index", 0))
        role = str(event.get("generation_role", ""))
        if event_name == "logical_call_started":
            expected = self.reserve(role)
            if expected != index:
                raise D5HarnessError("D4/D5 logical call index drift")
            self.physical_attempt(index)
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
    _terminal_written: bool = False

    @classmethod
    def start(
        cls,
        paths: EvidencePaths,
        *,
        provenance: Mapping[str, Any],
        readiness: D5ReadinessProjection,
    ) -> D5CampaignCustody:
        """Create STARTED custody only after successful readiness."""
        ensure_fresh_namespace(paths)
        state = {
            "experiment_version": D5_EXPERIMENT_VERSION,
            "campaign_id": paths.campaign_id,
            "status": "STARTED",
            "readiness_status": "LIVE_READY",
            "provider": EXPECTED_PROVIDER,
            "model": EXPECTED_MODEL,
            "logical_generation_calls": 0,
            "physical_generation_attempts": 0,
            "identity_endpoint_calls": 2,
            "endpoint_identity": readiness.as_dict(),
            "provenance": dict(provenance),
        }
        if not evidence_is_redacted(state):
            raise D5HarnessError("state redaction failure")
        _atomic_json(paths.state, state, exclusive=True)
        _append_jsonl(
            paths.journal,
            {
                "event": "campaign_started",
                "experiment_version": D5_EXPERIMENT_VERSION,
                "campaign_id": paths.campaign_id,
                "status": "STARTED",
            },
            exclusive=True,
        )
        return cls(
            paths=paths,
            campaign_id=paths.campaign_id,
            state=state,
            ledger=D5LogicalCallLedger(),
        )

    def record_call_started(self, event: Mapping[str, Any]) -> None:
        """Persist one role-aware logical call before delegation."""
        self.ledger.record_d4_event(event)
        self.state["logical_generation_calls"] = self.ledger.logical_calls
        self.state["physical_generation_attempts"] = self.ledger.physical_attempts
        _atomic_json(self.paths.state, self.state)
        bounded = {
            "event": "logical_call_started",
            "experiment_version": D5_EXPERIMENT_VERSION,
            "campaign_id": self.campaign_id,
            "index": event.get("index"),
            "generation_role": event.get("generation_role"),
            "provider": event.get("provider"),
            "model": event.get("model"),
        }
        _append_jsonl(self.paths.journal, bounded)

    def record_call_completed(self, event: Mapping[str, Any]) -> None:
        """Persist bounded completion metadata without payload material."""
        bounded = {
            "event": "logical_call_completed",
            "experiment_version": D5_EXPERIMENT_VERSION,
            "campaign_id": self.campaign_id,
            "index": event.get("index"),
            "generation_role": event.get("generation_role"),
            "provider": event.get("provider"),
            "model": event.get("model"),
            "outcome": event.get("outcome"),
            "failure_category": event.get("failure_category"),
        }
        _append_jsonl(self.paths.journal, bounded)

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
    ) -> dict[str, Any]:
        """Write exactly one terminal artifact and close the campaign."""
        if decision not in TERMINAL_DECISIONS:
            raise D5HarnessError("unknown terminal decision")
        if self._terminal_written or self.paths.terminal.exists():
            raise D5HarnessError("terminal artifact already written")
        _append_jsonl(
            self.paths.journal,
            {
                "event": "campaign_terminal",
                "experiment_version": D5_EXPERIMENT_VERSION,
                "campaign_id": self.campaign_id,
                "decision": decision,
                "attribution": attribution,
                "completed_turns": len(rows),
            },
        )
        evidence_digest = (
            _sha256_file(self.paths.evidence) if self.paths.evidence.exists() else None
        )
        journal_digest = _sha256_file(self.paths.journal)
        state_digest = _sha256_file(self.paths.state)
        terminal = {
            "experiment_version": D5_EXPERIMENT_VERSION,
            "campaign_id": self.campaign_id,
            "decision": decision,
            "attribution": attribution,
            "completed_turns": len(rows),
            "logical_generation_calls": self.ledger.logical_calls,
            "physical_generation_attempts": self.ledger.physical_attempts,
            "state_snapshot_sha256": state_digest,
            "journal_sha256": journal_digest,
            "evidence_sha256": evidence_digest,
        }
        _atomic_json(self.paths.terminal, terminal, exclusive=True)
        summary = {
            "experiment_version": D5_EXPERIMENT_VERSION,
            "campaign_id": self.campaign_id,
            "decision": decision,
            "attribution": attribution,
            "completed_turns": len(rows),
            "logical_generation_calls": self.ledger.logical_calls,
            "physical_generation_attempts": self.ledger.physical_attempts,
            "terminal_sha256": _sha256_file(self.paths.terminal),
        }
        _atomic_json(self.paths.summary, summary, exclusive=True)
        self.state.update(
            {
                "status": "TERMINAL",
                "decision": decision,
                "attribution": attribution,
                "completed_turns": len(rows),
                "terminal_sha256": _sha256_file(self.paths.terminal),
            }
        )
        _atomic_json(self.paths.state, self.state)
        self._terminal_written = True
        return terminal


def _project_model_catalog(payload: object, expected_model: str) -> tuple[str, ...]:
    """Project exactly one model ID without retaining the response body."""
    if not isinstance(payload, Mapping) or not isinstance(payload.get("data"), list):
        raise D5ReadinessError("endpoint_identity_mismatch", 1)
    identifiers = tuple(
        str(item.get("id", "")).strip() for item in payload["data"] if isinstance(item, Mapping)
    )
    if identifiers != (expected_model,):
        raise D5ReadinessError("endpoint_identity_mismatch", 1)
    return identifiers


def _project_props(payload: object, expected_contract: str) -> dict[str, Any]:
    """Sanitize llama.cpp runtime properties and fingerprint defaults."""
    if not isinstance(payload, Mapping):
        raise D5ReadinessError("endpoint_identity_mismatch", 2)
    path = payload.get("model_path")
    generation = payload.get("default_generation_settings")
    build_info = payload.get("build_info")
    slots = payload.get("total_slots")
    chat_template = payload.get("chat_template")
    chat_caps = payload.get("chat_template_caps", [])
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
        or not isinstance(chat_caps, list)
        or not all(isinstance(item, str) for item in chat_caps)
    ):
        raise D5ReadinessError("endpoint_identity_mismatch", 2)
    if expected_contract != "json_schema":
        raise D5ReadinessError("endpoint_identity_mismatch", 2)
    if "json_schema" not in chat_caps:
        raise D5ReadinessError("structured_output_contract_mismatch", 2)
    normalized_path = path.strip()
    basename = Path(normalized_path).name
    runtime_defaults = dict(generation)
    return {
        "model_path_basename": basename,
        "model_path_fingerprint_sha256": d4.sha256_text(normalized_path),
        "context_size": generation["n_ctx"],
        "build_info": build_info.strip(),
        "total_slots": slots,
        "chat_template": chat_template.strip(),
        "chat_template_caps": tuple(sorted(chat_caps)),
        "runtime_defaults_sha256": _sha256_json(runtime_defaults),
        "thinking_off": payload.get("thinking_off") is True,
        "structured_output_contract": expected_contract,
        "gguf_byte_identity": str(payload.get("gguf_byte_identity", "NOT_AVAILABLE")),
    }


def validate_readiness_projection(
    observed: Mapping[str, Any],
    authorization: D5Authorization,
) -> D5ReadinessProjection:
    """Require exact authorized runtime identity and server thinking precondition."""
    required = {
        "model_catalog",
        "model_path_basename",
        "model_path_fingerprint_sha256",
        "context_size",
        "build_info",
        "total_slots",
        "chat_template",
        "chat_template_caps",
        "runtime_defaults_sha256",
        "thinking_off",
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
    if observed["thinking_off"] is not True or authorization.thinking_off is not True:
        raise D5ReadinessError("thinking_off_not_established", 2)
    if observed["structured_output_contract"] != authorization.structured_output_contract:
        raise D5ReadinessError("structured_output_contract_mismatch", 2)
    expected = dict(authorization.endpoint_identity)
    for key, value in expected.items():
        observed_value = observed.get(key)
        if isinstance(observed_value, tuple) and isinstance(value, list):
            observed_value = list(observed_value)
        if observed_value != value:
            raise D5ReadinessError("endpoint_identity_mismatch", 2)
    return D5ReadinessProjection(**dict(observed))


@dataclass(frozen=True, slots=True)
class D5OperationalReadiness:
    """Successful two-GET readiness result with no generation probe."""

    projection: D5ReadinessProjection
    endpoint_calls: tuple[str, str]
    provider_calls: int = 0
    model_calls: int = 0


def prepare_readiness(
    *,
    authorization: D5Authorization,
    api_key_loader: Callable[[], str],
    endpoint_get: Callable[[str, str], object],
    static_preflight: Mapping[str, Any],
) -> D5OperationalReadiness:
    """Perform exactly two injectable identity observations after static checks."""
    if static_preflight.get("status") != "PASS":
        raise D5ReadinessError("static_preflight_failed", 0)
    token = api_key_loader()
    if not isinstance(token, str) or not token.strip():
        raise D5ReadinessError("credential_unavailable", 0)
    calls: list[str] = []

    def get(url: str) -> object:
        calls.append(url)
        return endpoint_get(url, token)

    try:
        catalog = _project_model_catalog(get(MODEL_CATALOG_URL), authorization.model)
        props = _project_props(get(PROPS_URL), authorization.structured_output_contract)
        observed = {"model_catalog": catalog, **props}
        projection = validate_readiness_projection(observed, authorization)
    except D5ReadinessError:
        raise
    except Exception:
        raise D5ReadinessError("endpoint_unreachable", len(calls)) from None
    if tuple(calls) != (MODEL_CATALOG_URL, PROPS_URL):
        raise D5ReadinessError("endpoint_order_mismatch", len(calls))
    return D5OperationalReadiness(projection=projection, endpoint_calls=("/v1/models", "/props"))


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
) -> dict[str, Any]:
    """Project one D4 actual/grade pair into redacted D5 evidence."""
    verifier = grade.get("verifier_requirements", [])
    return {
        "experiment_version": D5_EXPERIMENT_VERSION,
        "case_id": case.get("case_id"),
        "turn_id": case["turn_id"],
        "execution_index": execution_index,
        "request_sha256": case.get("request_sha256"),
        "result_status": grade.get("status"),
        "outcome": "PASS" if grade.get("status") == "PASS" else "FAIL",
        "grader_status": grade.get("status"),
        "diagnostics": list(grade.get("errors", [])),
        "verifier_requirements": verifier,
        "starting_artifact_sha256": _safe_hash(actual.get("starting_artifact_path")),
        "ending_artifact_sha256": _safe_hash(actual.get("ending_artifact_path")),
        "render_sha256": _safe_hash(actual.get("render_path")),
        "persisted": actual.get("persisted") is True,
        "rendered": actual.get("rendered") is True,
        "logical_generation_calls": call_count,
        "physical_attempts": call_count,
        "provider": EXPECTED_PROVIDER,
        "model": EXPECTED_MODEL,
    }


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

    async def run(self, adapter: object) -> dict[str, Any]:
        """Run the immutable nine-turn order through the supplied adapter."""
        if self._started or self._finished:
            raise D5HarnessError("campaign cannot be resumed or invoked twice")
        self._started = True
        custody = D5CampaignCustody.start(
            self.paths,
            provenance=self.provenance,
            readiness=self.readiness.projection,
        )
        rows: list[dict[str, Any]] = []
        try:
            if callable(getattr(adapter, "bind_call_started", None)):
                adapter.bind_call_started(custody.record_call_started)
            if callable(getattr(adapter, "bind_call_completed", None)):
                adapter.bind_call_completed(custody.record_call_completed)
            cases = d4.load_cases(self.repo_root)
            gold = {item["turn_id"]: item for item in d4.load_gold(self.repo_root)["cases"]}
            if tuple(item["turn_id"] for item in cases) != FROZEN_TURN_IDS:
                raise D5StaticPreflightError("D5 population order drifted")
            execute_turn = getattr(adapter, "execute_turn", None)
            if not callable(execute_turn):
                raise D5ProductionFailure("adapter has no canonical execute_turn")
            for execution_index, case in enumerate(cases, start=1):
                expected = gold[case["turn_id"]]
                cursor = int(getattr(adapter, "logical_call_count", 0))
                started = time.perf_counter()
                actual = await execute_turn(case, expected)
                grade = d4.grade_turn(dict(actual), expected)
                calls = int(getattr(adapter, "logical_call_count", 0)) - cursor
                row = _bounded_turn_row(
                    case,
                    expected,
                    actual,
                    grade,
                    execution_index=execution_index,
                    call_count=calls,
                )
                row["duration_seconds"] = round(time.perf_counter() - started, 6)
                custody.append_turn(row)
                rows.append(row)
            if len(rows) != 9:
                decision, attribution = "INCONCLUSIVE", "POPULATION_INCOMPLETE"
            elif all(row["grader_status"] == "PASS" for row in rows):
                decision, attribution = "PASS", "DETERMINISTIC_GRADING"
            else:
                decision, attribution = "FAIL", "SEMANTIC_CONTRACT"
        except Exception as error:
            decision, attribution = _classify_exception(error)
        terminal = custody.finish(decision, attribution=attribution, rows=rows)
        self._finished = True
        return {
            "decision": decision,
            "attribution": attribution,
            "completed_turns": len(rows),
            "rows": rows,
            "terminal": terminal,
            "logical_generation_calls": custody.ledger.logical_calls,
            "physical_generation_attempts": custody.ledger.physical_attempts,
            "provider_calls": 0,
            "endpoint_calls": 0,
            "model_calls": 0,
        }


def provider_free_preflight(
    repo_root: Path,
    authorization: D5Authorization,
    paths: EvidencePaths,
    *,
    static_checker: Callable[[Path, D5Authorization, EvidencePaths], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run static D5-4 checks without credentials, endpoints, or providers."""
    checker = static_checker or _default_static_checks
    facts = checker(repo_root, authorization, paths)
    if facts.get("status") != "PASS":
        raise D5StaticPreflightError("provider-free static preflight failed")
    return {
        "experiment_version": D5_EXPERIMENT_VERSION,
        "status": "PASS",
        "accepted_d5_engine_checkpoint": D5_ENGINE_CHECKPOINT,
        "accepted_d5_design_checkpoint": D5_DESIGN_CHECKPOINT,
        "population": {"turns": 9, "turn_ids": list(FROZEN_TURN_IDS)},
        "logical_call_ceiling": MAX_LOGICAL_CALLS,
        "physical_attempt_upper_bound": MAX_PHYSICAL_ATTEMPTS,
        "provider_calls": 0,
        "endpoint_calls": 0,
        "model_calls": 0,
        "static": facts,
    }


def _load_authorization(path: Path) -> D5Authorization:
    """Load an external authorization record without printing its contents."""
    return D5Authorization.from_mapping(json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    """Run only the provider-free static preflight CLI path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--provider-free-preflight", action="store_true")
    parser.add_argument("--authorization-json", type=Path, required=True)
    args = parser.parse_args()
    if not args.provider_free_preflight:
        parser.error("D5-4 implementation supports provider-free preflight only")
    repo_root = args.repo_root.resolve()
    authorization = _load_authorization(args.authorization_json.resolve())
    campaign_id = f"d5-4-provider-free-{uuid.uuid4().hex}"
    paths = EvidencePaths(repo_root / "workspace/evaluations/d5-4-live-qualification", campaign_id)
    result = provider_free_preflight(repo_root, authorization, paths)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
