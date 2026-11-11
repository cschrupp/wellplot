"""Provider-free D5-4 live semantic qualification harness.

This module owns only the D5-4 orchestration and evidence boundary. It reuses
the accepted D4 cases, custody helpers, deterministic graders, and canonical
Direct Notebook adapter; it never creates a provider or performs network I/O
unless a future, separately authorized live runner supplies those operations.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import errno
import hashlib
import importlib.metadata
import inspect
import json
import os
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from scripts import d5_5_final_population as final_population
from scripts import nlp_d4_live_acceptance as d4
from scripts.d5_5_c02_contract_grader import grade_c02_artifact
from wellplot.agent.code_mode.facade import CodeModeCompileResult
from wellplot.agent.code_mode.obligations import (
    RequestCompilationResult,
    compile_request_contract,
)
from wellplot.agent.providers.base import (
    ProviderFailureCategory,
    ProviderRequestError,
    StructuredGenerationRequest,
)
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
MAX_PLANNER_LOGICAL_CALLS = 2
MAX_REPORT_WORKER_LOGICAL_CALLS = 2
MAX_SECTION_WORKER_LOGICAL_CALLS = 4
ROLE_LOGICAL_CALL_LIMITS = {
    "planner": MAX_PLANNER_LOGICAL_CALLS,
    "report_worker": MAX_REPORT_WORKER_LOGICAL_CALLS,
    "section_worker": MAX_SECTION_WORKER_LOGICAL_CALLS,
}
SMOKE_ROLE = "smoke"
SMOKE_TURN_ID = "D5-5J-SMOKE"
SMOKE_BINDING_KIND = "binding_compile"
SMOKE_BINDING_TURN_ID = "D5-5J-BINDING-SMOKE-002"
SMOKE_PLANNER_KIND = "planner_only"
SMOKE_PLANNER_TURN_ID = "A10-SEM-02-PLANNER-SMOKE"
SMOKE_SYSTEM_PROMPT = "Return the smoke readiness object using the supplied JSON Schema."
SMOKE_USER_PROMPT = "Return exactly one JSON object with status READY and no other fields."
SMOKE_MAX_LOGICAL_CALLS = 1
SMOKE_MAX_PHYSICAL_ATTEMPTS = 3
SMOKE_BINDING_ROLE_LIMITS = {"planner": 2, "section_worker": 2, "report_worker": 0}
SMOKE_BINDING_MAX_LOGICAL_CALLS = 4
SMOKE_BINDING_MAX_PHYSICAL_ATTEMPTS_PER_CALL = 3
SMOKE_PLANNER_ROLE_LIMITS = {"planner": MAX_PLANNER_LOGICAL_CALLS}
SMOKE_PLANNER_MAX_RETRIES = 0
# The production planner permits one invalid-response correction after the initial call.
SMOKE_PLANNER_MAX_PHYSICAL_ATTEMPTS = MAX_PLANNER_LOGICAL_CALLS
SMOKE_PLANNER_MAX_PHYSICAL_ATTEMPTS_PER_REQUEST = 1
A10_SEM_01_ROOT = "workspace/evaluations/a10-sem-01-20261110"
A10_SEM_01_BENCHMARK = f"{A10_SEM_01_ROOT}/benchmark.json"
A10_SEM_01_SOURCE_INVENTORY = f"{A10_SEM_01_ROOT}/source-inventory.json"
A10_SEM_02_SMOKE_CASE_ID = "B01"
A10_SEM_02_SMOKE_SOURCE_KEY = "approved_las"
A10_SEM_02_SMOKE_SOURCE_PATH = "workspace/data/30-23a-3 8117_d.las"
A10_SEM_02_SMOKE_SOURCE_SHA256 = "7e6c69c65713dc33303362ab91b767eb06371fd24a31856add8650e6d3bee1a9"
A10_SEM_02_SOURCE_PATH_BY_KEY = {
    "approved_las": A10_SEM_02_SMOKE_SOURCE_PATH,
    "cbl_repeat_dlis": "workspace/data/CBL_Repeat.dlis",
    "cbl_main_dlis": "workspace/data/CBL_Main.dlis",
}
A10_SEM_02_EXPECTED_WORKTREE_PORCELAIN = (
    " M examples/notebooks/user/agent_cbl_log_example_from_prompt.ipynb\n"
    " M examples/notebooks/user/agent_las_step_by_step.ipynb\n"
    "?? examples/families/FamiliesList.json\n"
    "?? examples/families/FamilyAssignment.json\n"
)
SMOKE_BINDING_REQUEST = (
    "In the Main Log section, add two normal tracks while preserving the existing tracks.\n"
    "Track Bond Index: normal, width 34 mm.\n"
    "Track Gamma Ray: normal, width 26 mm.\n"
    "On Bond Index: BI -> Bond Index, linear 0..1, #111111, width 0.8.\n"
    "On Gamma Ray: GR_STGC -> Gamma Ray, linear 0..150, #16a34a, width 0.8."
)
SMOKE_BINDING_REQUEST_SHA256 = "b60330264cf1037fec80a533bd0a7b96fdee70aa52101693a8da5c962b9914e7"
MAX_ENDPOINT_RESPONSE_BYTES = 1_048_576
MAX_SECTION_ACTION_EVIDENCE_BYTES = 65_536
MAX_PLANNER_DIAGNOSTIC_RECORD_BYTES = 1_048_576
MAX_PLANNER_DIAGNOSTIC_FILE_BYTES = 6 * MAX_PLANNER_DIAGNOSTIC_RECORD_BYTES
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


class _PlannerOnlyWireCaptured(Exception):
    """Stop after the production planner's schema-validated wire DTO is captured."""


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


class SmokeReadyResponse(BaseModel):
    """Minimal structured response used only by the canonical smoke mode."""

    status: Literal["READY"]


def _smoke_schema_sha256() -> str:
    """Hash the exact Pydantic schema sent by the smoke request."""
    return _sha256_json(SmokeReadyResponse.model_json_schema())


SMOKE_SCHEMA_SHA256 = "1559e2f0e9da487297424da1fd94d65c877ce4c0a26b21658daed90c4f5680f6"


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
    section_action_capture_mode: Literal["off", "diagnostics", "validated_dto"] = "off"
    planner_smoke_mode: str = ""
    planner_smoke_case_id: str = ""
    planner_smoke_request_sha256: str = ""
    planner_smoke_benchmark_sha256: str = ""
    planner_smoke_source_inventory_sha256: str = ""
    planner_smoke_source_sha256: str = ""
    planner_smoke_harness_sha256: str = ""
    planner_smoke_wire_schema_sha256: str = ""
    planner_smoke_sdk_max_retries: int | None = None
    expected_worktree_porcelain: str = ""

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
        capture_mode = value.get("section_action_capture_mode", "off")
        if not isinstance(capture_mode, str) or capture_mode not in {
            "off",
            "diagnostics",
            "validated_dto",
        }:
            raise D5StaticPreflightError("invalid section action capture mode")
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
            section_action_capture_mode=capture_mode,
            planner_smoke_mode=str(value.get("planner_smoke_mode", "")),
            planner_smoke_case_id=str(value.get("planner_smoke_case_id", "")),
            planner_smoke_request_sha256=str(value.get("planner_smoke_request_sha256", "")),
            planner_smoke_benchmark_sha256=str(value.get("planner_smoke_benchmark_sha256", "")),
            planner_smoke_source_inventory_sha256=str(
                value.get("planner_smoke_source_inventory_sha256", "")
            ),
            planner_smoke_source_sha256=str(value.get("planner_smoke_source_sha256", "")),
            planner_smoke_harness_sha256=str(value.get("planner_smoke_harness_sha256", "")),
            planner_smoke_wire_schema_sha256=str(value.get("planner_smoke_wire_schema_sha256", "")),
            planner_smoke_sdk_max_retries=value.get("planner_smoke_sdk_max_retries"),
            expected_worktree_porcelain=str(value.get("expected_worktree_porcelain", "")),
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


def _git_porcelain_raw(repo_root: Path) -> str:
    """Return Git porcelain exactly, including status columns and final newline."""
    return subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo_root,
        text=True,
    )


def _require_exact_planner_worktree(repo_root: Path, expected: str) -> None:
    """Accept only the frozen, reviewed unrelated worktree entries for A10 smoke."""
    if expected != A10_SEM_02_EXPECTED_WORKTREE_PORCELAIN:
        raise D5StaticPreflightError("planner smoke worktree allowlist is not the reviewed state")
    if _git_porcelain_raw(repo_root) != expected:
        raise D5StaticPreflightError("planner smoke worktree differs from the exact allowlist")


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


def _default_smoke_static_checks(
    repo_root: Path,
    authorization: D5Authorization,
    artifact_paths: EvidencePaths,
    *,
    expected_worktree_porcelain: str | None = None,
    expected_schema_sha256: str = SMOKE_SCHEMA_SHA256,
    mode: str = "canonical_live_smoke",
) -> dict[str, Any]:
    """Validate smoke custody without loading scientific cases or sources."""
    current = _git(repo_root, "rev-parse", "HEAD")
    if current != authorization.implementation_checkpoint:
        raise D5StaticPreflightError("implementation checkpoint mismatch")
    if expected_worktree_porcelain is None:
        if _git(repo_root, "status", "--porcelain"):
            raise D5StaticPreflightError("working tree is not clean")
    else:
        _require_exact_planner_worktree(repo_root, expected_worktree_porcelain)
    project_config = load_project_config(repo_root)
    _validate_project_config(project_config)
    if authorization.project_config_fingerprint_sha256 != project_config.fingerprint_sha256:
        raise D5StaticPreflightError("project configuration fingerprint mismatch")
    if authorization.provider != EXPECTED_PROVIDER or authorization.model != EXPECTED_MODEL:
        raise D5StaticPreflightError("provider/model contract drifted")
    if not isinstance(authorization.section_action_capture_mode, str) or (
        authorization.section_action_capture_mode not in {"off", "diagnostics", "validated_dto"}
    ):
        raise D5StaticPreflightError("invalid section action capture mode")
    if authorization.sdk_version != EXPECTED_OPENAI_VERSION:
        raise D5StaticPreflightError("OpenAI package contract drifted")
    if authorization.sdk_max_retries != EXPECTED_SDK_MAX_RETRIES:
        raise D5StaticPreflightError("SDK retry contract drifted")
    version, retries = _inspect_openai_sdk()
    if authorization.structured_output_contract != EXPECTED_STRUCTURED_OUTPUT:
        raise D5StaticPreflightError("structured-output contract drifted")
    if not authorization.thinking_off:
        raise D5StaticPreflightError("thinking-off request contract is absent")
    if authorization.thinking_control_options_sha256 != THINKING_CONTROL_OPTIONS_SHA256:
        raise D5StaticPreflightError("thinking-off request control digest drifted")
    _validated_thinking_control_options(authorization.thinking_control_options)
    if artifact_paths.campaign_id != authorization.campaign_id:
        raise D5StaticPreflightError("smoke path is not bound to authorization")
    if not authorization.authorization_id or not authorization.campaign_id:
        raise D5StaticPreflightError("authorization/campaign identity is missing")
    if expected_schema_sha256 != (
        SMOKE_SCHEMA_SHA256 if mode == "canonical_live_smoke" else _planner_wire_schema_sha256()
    ):
        raise D5StaticPreflightError("smoke schema fingerprint drifted")
    for path in artifact_paths.all_paths():
        if path.exists():
            raise D5StaticPreflightError(f"fresh smoke artifact path already exists: {path.name}")
    attestation = _run_static_attestation(repo_root)
    return {
        "status": "PASS",
        "mode": mode,
        "current_checkout": current,
        "project_config_fingerprint_sha256": project_config.fingerprint_sha256,
        "provider": authorization.provider,
        "model": authorization.model,
        "sdk_version": version,
        "sdk_max_retries": retries,
        "structured_output_contract": authorization.structured_output_contract,
        "thinking_control_mechanism": THINKING_CONTROL_MECHANISM,
        "thinking_control_options_sha256": THINKING_CONTROL_OPTIONS_SHA256,
        "smoke_schema_sha256": expected_schema_sha256,
        "scientific_population_loaded": False,
        "scientific_campaign_started": False,
        "d5_attestation": attestation,
    }


def _planner_wire_schema_sha256() -> str:
    """Hash the production planner's actual structured wire schema."""
    from wellplot.agent.code_mode.planner import _PlannerWirePlan

    return _sha256_json(_PlannerWirePlan.model_json_schema())


def _planner_generation_purpose(logical_index: int) -> str:
    """Classify the bounded initial or native correction generation request."""
    if logical_index == 1:
        return "INITIAL_GENERATION"
    if logical_index == 2:
        return "STRUCTURED_OUTPUT_CORRECTION"
    raise D5HarnessError("planner generation exceeded its production correction policy")


def _planner_smoke_case(
    repo_root: Path,
    authorization: D5Authorization,
    *,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Resolve one authority-pinned case from the immutable SEM-01 inputs."""
    required_digests = {
        "benchmark": authorization.planner_smoke_benchmark_sha256,
        "source inventory": authorization.planner_smoke_source_inventory_sha256,
        "source": authorization.planner_smoke_source_sha256,
        "harness": authorization.planner_smoke_harness_sha256,
        "wire schema": authorization.planner_smoke_wire_schema_sha256,
        "request": authorization.planner_smoke_request_sha256,
    }
    if authorization.planner_smoke_mode != SMOKE_PLANNER_KIND:
        raise D5StaticPreflightError("planner-only smoke mode is not authorized")
    selected_case_id = authorization.planner_smoke_case_id if case_id is None else case_id
    if not selected_case_id or selected_case_id != authorization.planner_smoke_case_id:
        raise D5StaticPreflightError("selected planner case does not match its authority")
    if type(authorization.planner_smoke_sdk_max_retries) is not int or (
        authorization.planner_smoke_sdk_max_retries != SMOKE_PLANNER_MAX_RETRIES
    ):
        raise D5StaticPreflightError("planner smoke authority must pin zero SDK retries")
    if any(not re.fullmatch(r"[0-9a-f]{64}", digest) for digest in required_digests.values()):
        raise D5StaticPreflightError("planner smoke authority is missing a pinned digest")
    if authorization.expected_worktree_porcelain != A10_SEM_02_EXPECTED_WORKTREE_PORCELAIN:
        raise D5StaticPreflightError("planner smoke worktree authority is not the reviewed state")

    benchmark_path = repo_root / A10_SEM_01_BENCHMARK
    inventory_path = repo_root / A10_SEM_01_SOURCE_INVENTORY
    _assert_hash(benchmark_path, authorization.planner_smoke_benchmark_sha256, "benchmark")
    _assert_hash(
        inventory_path,
        authorization.planner_smoke_source_inventory_sha256,
        "source inventory",
    )
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    cases = benchmark.get("cases")
    if not isinstance(cases, list):
        raise D5StaticPreflightError("frozen benchmark case set is invalid")
    matches = [
        case for case in cases if isinstance(case, Mapping) and case.get("id") == selected_case_id
    ]
    if len(matches) != 1:
        raise D5StaticPreflightError("frozen planner case is missing or not unique")
    case = dict(matches[0])
    request = case.get("request")
    source_key = case.get("source")
    if not isinstance(source_key, str):
        raise D5StaticPreflightError("frozen planner case has no source reference")
    relative_source_path = A10_SEM_02_SOURCE_PATH_BY_KEY.get(source_key)
    if relative_source_path is None:
        raise D5StaticPreflightError("frozen planner case names an unknown source")
    if (
        not isinstance(request, str)
        or not request.strip()
        or hashlib.sha256(request.encode("utf-8")).hexdigest()
        != authorization.planner_smoke_request_sha256
    ):
        raise D5StaticPreflightError("frozen planner case request differs from authority")

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    sources = inventory.get("sources")
    if not isinstance(sources, list):
        raise D5StaticPreflightError("frozen source inventory is invalid")
    source_rows = [
        source
        for source in sources
        if isinstance(source, Mapping) and source.get("path") == relative_source_path
    ]
    if len(source_rows) != 1:
        raise D5StaticPreflightError("frozen planner source is missing or not unique")
    source_row = source_rows[0]
    source_sha256 = source_row.get("sha256")
    source_format = source_row.get("format")
    if (
        not isinstance(source_sha256, str)
        or source_sha256 != authorization.planner_smoke_source_sha256
        or source_format not in {"LAS", "DLIS"}
    ):
        raise D5StaticPreflightError("planner source identity differs from authority")
    source_path = (repo_root / relative_source_path).resolve()
    if not source_path.is_relative_to(repo_root.resolve()):
        raise D5StaticPreflightError("frozen planner source escapes the repository")
    _assert_hash(source_path, authorization.planner_smoke_source_sha256, "source")
    _assert_hash(Path(__file__).resolve(), authorization.planner_smoke_harness_sha256, "harness")
    if _planner_wire_schema_sha256() != authorization.planner_smoke_wire_schema_sha256:
        raise D5StaticPreflightError("production planner wire schema differs from authority")
    return {
        "case_id": selected_case_id,
        "request": request,
        "request_sha256": authorization.planner_smoke_request_sha256,
        "source_key": source_key,
        "source_path": relative_source_path,
        "source_format": source_format.lower(),
        "source_sha256": authorization.planner_smoke_source_sha256,
        "benchmark_sha256": authorization.planner_smoke_benchmark_sha256,
        "source_inventory_sha256": authorization.planner_smoke_source_inventory_sha256,
        "wire_schema_sha256": authorization.planner_smoke_wire_schema_sha256,
        "sdk_max_retries": authorization.planner_smoke_sdk_max_retries,
        "physical_attempt_limit": SMOKE_PLANNER_MAX_PHYSICAL_ATTEMPTS,
    }


def _default_planner_smoke_static_checks(
    repo_root: Path,
    authorization: D5Authorization,
    artifact_paths: EvidencePaths,
    *,
    case_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate the exact A10 smoke authority before readiness or provider setup."""
    canonical_root = Path("/home/user/projects/well_log_os").resolve()
    if Path.cwd().resolve() != canonical_root or repo_root.resolve() != canonical_root:
        raise D5StaticPreflightError("planner smoke is not running in the canonical checkout")
    if Path(_git(repo_root, "rev-parse", "--show-toplevel")).resolve() != canonical_root:
        raise D5StaticPreflightError("planner smoke Git top-level is not canonical")
    if authorization.planner_smoke_mode != SMOKE_PLANNER_KIND:
        raise D5StaticPreflightError("planner-only smoke mode is not authorized")
    if authorization.expected_worktree_porcelain != A10_SEM_02_EXPECTED_WORKTREE_PORCELAIN:
        raise D5StaticPreflightError("planner smoke worktree allowlist is not the reviewed state")
    case = _planner_smoke_case(repo_root, authorization, case_id=case_id)
    static = _default_smoke_static_checks(
        repo_root,
        authorization,
        artifact_paths,
        expected_worktree_porcelain=authorization.expected_worktree_porcelain,
        expected_schema_sha256=authorization.planner_smoke_wire_schema_sha256,
        mode="canonical_planner_only_smoke",
    )
    static.update(
        {
            "planner_entrypoint": "wellplot.agent.code_mode.planner.SemanticPlanner.plan",
            "planner_smoke_case_id": case["case_id"],
            "planner_smoke_request_sha256": case["request_sha256"],
            "planner_smoke_benchmark_sha256": case["benchmark_sha256"],
            "planner_smoke_source_inventory_sha256": case["source_inventory_sha256"],
            "planner_smoke_source_sha256": case["source_sha256"],
            "planner_smoke_harness_sha256": authorization.planner_smoke_harness_sha256,
            "planner_smoke_wire_schema_sha256": case["wire_schema_sha256"],
            "planner_smoke_sdk_max_retries": case["sdk_max_retries"],
            "planner_smoke_physical_attempt_limit": case["physical_attempt_limit"],
            "expected_worktree_porcelain_sha256": hashlib.sha256(
                authorization.expected_worktree_porcelain.encode("utf-8")
            ).hexdigest(),
        }
    )
    return static, case


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

    @property
    def compile_result(self) -> Path:
        """Return the safe host-facing compile result for binding smoke."""
        return self.root / f"{self.campaign_id}.compile-result.json"

    @property
    def planner_wire(self) -> Path:
        """Return validated planner wire DTOs, one per line."""
        return self.root / f"{self.campaign_id}.planner-wire-response.jsonl"

    @property
    def planner_wire_diagnostics(self) -> Path:
        """Return private raw planner request/response diagnostics."""
        return self.root / f"{self.campaign_id}.planner-wire-diagnostics.jsonl"

    @property
    def request_compilation(self) -> Path:
        """Return the deterministic host request compilation projection."""
        return self.root / f"{self.campaign_id}.request-compilation.json"

    @property
    def planner_context(self) -> Path:
        """Return the sanitized planner context needed for provider-free replay."""
        return self.root / f"{self.campaign_id}.planner-context.json"

    @property
    def section_actions(self) -> Path:
        """Return validated section-worker action DTOs captured for diagnosis."""
        return self.root / f"{self.campaign_id}.section-actions.jsonl"

    @property
    def validated_section_dtos(self) -> Path:
        """Return the private, independently expirable DTO directory."""
        return self.root / f"{self.campaign_id}.validated-section-dtos"

    @property
    def dto_deletion_receipt(self) -> Path:
        """Return the separate authorization receipt for expired DTO deletion."""
        return self.root / f"{self.campaign_id}.dto-deletion.json"

    @property
    def stage_trace(self) -> Path:
        """Return pre-dispatch and planner stage transitions, one per line."""
        return self.root / f"{self.campaign_id}.stage-trace.jsonl"

    @property
    def binding_request(self) -> Path:
        """Return the exact non-scientific binding-smoke request record."""
        return self.root / f"{self.campaign_id}.binding-request.json"

    @property
    def binding_request_compilation(self) -> Path:
        """Return provider-free compilation evidence for the binding request."""
        return self.root / f"{self.campaign_id}.binding-request-compilation.json"

    def all_paths(self) -> tuple[Path, ...]:
        """Return all collision-sensitive paths in deterministic order."""
        return (
            self.state,
            self.journal,
            self.terminal,
            self.summary,
            self.evidence,
            self.model_io,
            self.compile_result,
            self.planner_wire,
            self.planner_wire_diagnostics,
            self.request_compilation,
            self.planner_context,
            self.section_actions,
            self.validated_section_dtos,
            self.dto_deletion_receipt,
            self.stage_trace,
            self.binding_request,
            self.binding_request_compilation,
        )


@dataclass(slots=True)
class D5SmokeCallLedger:
    """Bound smoke calls and physical attempts under the canonical call roles."""

    mode: Literal["structured_ready", "binding_compile", "planner_only"] = "structured_ready"
    max_logical_calls: int = SMOKE_MAX_LOGICAL_CALLS
    max_physical_attempts: int = SMOKE_MAX_PHYSICAL_ATTEMPTS
    logical_calls: int = 0
    physical_attempts: int = 0
    calls_by_role: dict[str, int] = field(default_factory=dict)
    roles_by_index: dict[int, str] = field(default_factory=dict)
    attempts_by_index: dict[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Set the logical-call ceiling for the selected smoke mode."""
        if self.mode in {SMOKE_BINDING_KIND, SMOKE_PLANNER_KIND}:
            self.max_logical_calls = (
                SMOKE_PLANNER_ROLE_LIMITS["planner"]
                if self.mode == SMOKE_PLANNER_KIND
                else SMOKE_BINDING_MAX_LOGICAL_CALLS
            )
        elif self.mode != "structured_ready":
            raise D5HarnessError("unknown smoke accounting mode")

    def reserve(self) -> int:
        """Reserve the READY smoke call before provider delegation."""
        if self.mode != "structured_ready":
            raise D5HarnessError("binding smoke calls require canonical role events")
        next_index = self.logical_calls + 1
        if next_index > self.max_logical_calls:
            raise D5CallCapExceeded("smoke logical call 2 rejected before delegation")
        self.logical_calls = next_index
        self.roles_by_index[next_index] = SMOKE_ROLE
        self.calls_by_role[SMOKE_ROLE] = 1
        self.attempts_by_index[next_index] = 0
        return next_index

    def record_canonical_call_started(self, index: int, role: str) -> None:
        """Admit a canonical planner/worker call before provider delegation."""
        if self.mode not in {SMOKE_BINDING_KIND, SMOKE_PLANNER_KIND}:
            raise D5HarnessError("canonical role events require binding-smoke mode")
        if index != self.logical_calls + 1:
            raise D5HarnessError("binding smoke logical identity is not sequential")
        role_limits = (
            SMOKE_PLANNER_ROLE_LIMITS
            if self.mode == SMOKE_PLANNER_KIND
            else SMOKE_BINDING_ROLE_LIMITS
        )
        if role not in role_limits:
            raise D5CallCapExceeded("binding smoke generation role is not authorized")
        if self.logical_calls >= self.max_logical_calls:
            if self.mode == SMOKE_PLANNER_KIND:
                raise D5CallCapExceeded(
                    "planner-only correction budget exhausted before provider delegation"
                )
            raise D5CallCapExceeded("binding smoke logical call 5 rejected before delegation")
        role_count = self.calls_by_role.get(role, 0)
        if role_count >= role_limits[role]:
            raise D5CallCapExceeded(f"binding smoke {role} call limit rejected before delegation")
        self.logical_calls = index
        self.roles_by_index[index] = role
        self.calls_by_role[role] = role_count + 1
        self.attempts_by_index[index] = 0

    def validate_call_event(self, index: int, role: str | None) -> None:
        """Reject lifecycle events that do not match an admitted call identity."""
        if self.roles_by_index.get(index) != role:
            raise D5HarnessError("binding smoke lifecycle event identity mismatch")

    def physical_attempt(self, logical_index: int) -> int:
        """Count an SDK attempt under the mode-specific per-call ceiling."""
        role = self.roles_by_index.get(logical_index)
        if role is None:
            raise D5HarnessError("smoke physical attempt references unknown call")
        next_attempt = self.attempts_by_index[logical_index] + 1
        if self.mode == SMOKE_PLANNER_KIND:
            limit = SMOKE_PLANNER_MAX_PHYSICAL_ATTEMPTS_PER_REQUEST
        elif self.mode == SMOKE_BINDING_KIND:
            limit = SMOKE_BINDING_MAX_PHYSICAL_ATTEMPTS_PER_CALL
        else:
            limit = self.max_physical_attempts
        if next_attempt > limit:
            if self.mode == SMOKE_PLANNER_KIND:
                raise D5CallCapExceeded("planner-only smoke forbids transport retries")
            raise D5CallCapExceeded("smoke physical attempt 4 rejected before delegation")
        self.attempts_by_index[logical_index] = next_attempt
        self.physical_attempts = next_attempt
        if self.mode in {SMOKE_BINDING_KIND, SMOKE_PLANNER_KIND}:
            self.physical_attempts = sum(self.attempts_by_index.values())
        return next_attempt


@dataclass(slots=True)
class D5SmokeCustody:
    """Persist one non-scientific smoke result without scientific STARTED state."""

    paths: EvidencePaths
    authorization: D5Authorization
    state: dict[str, Any]
    ledger: D5SmokeCallLedger = field(default_factory=D5SmokeCallLedger)
    terminal_written: bool = False

    @classmethod
    def start(
        cls,
        paths: EvidencePaths,
        *,
        authorization: D5Authorization,
        static_preflight: Mapping[str, Any],
        readiness: D5ReadinessProjectionProtocol,
        endpoint_calls: int,
        smoke_kind: str = "structured_ready",
        source_asset_identities: Sequence[Mapping[str, Any]] = (),
        binding_input_preflighted: bool = False,
    ) -> D5SmokeCustody:
        """Create smoke custody only after static checks and readiness pass."""
        if authorization.section_action_capture_mode != "off":
            _prepare_private_campaign_root(paths.root)
        ensure_fresh_namespace(
            paths,
            existing_allowed=(
                (paths.binding_request, paths.binding_request_compilation)
                if binding_input_preflighted
                else ()
            ),
        )
        safe_asset_identities = _sanitize_source_asset_identities(source_asset_identities)
        ledger_mode = (
            smoke_kind
            if smoke_kind in {SMOKE_BINDING_KIND, SMOKE_PLANNER_KIND}
            else "structured_ready"
        )
        custody_mode = (
            "canonical_planner_only_smoke"
            if smoke_kind == SMOKE_PLANNER_KIND
            else "canonical_live_smoke"
        )
        ledger = D5SmokeCallLedger(mode=ledger_mode)
        state = {
            "experiment_version": D5_EXPERIMENT_VERSION,
            "mode": custody_mode,
            "smoke_kind": smoke_kind,
            "campaign_id": paths.campaign_id,
            "authorization_id": authorization.authorization_id,
            "status": "SMOKE_STARTED",
            "provider": authorization.provider,
            "model": authorization.model,
            "endpoint_calls": endpoint_calls,
            "identity_endpoint_calls": endpoint_calls,
            "logical_generation_calls": 0,
            "physical_generation_attempts": 0,
            "provider_calls": 0,
            "model_calls": 0,
            "scientific_population_loaded": False,
            "scientific_campaign_started": False,
            "readiness": readiness.as_dict(),
            "static_preflight": dict(static_preflight),
            "source_asset_identities": safe_asset_identities,
        }
        if ledger.mode in {SMOKE_BINDING_KIND, SMOKE_PLANNER_KIND}:
            state["logical_calls_by_role"] = {}
            if authorization.section_action_capture_mode != "off":
                state["section_action_capture_mode"] = authorization.section_action_capture_mode
                state["validated_dto_retention_days"] = 30
        if ledger.mode == SMOKE_PLANNER_KIND:
            state.update(
                {
                    "logical_planner_invocations": 0,
                    "initial_generation_requests": 0,
                    "correction_generation_requests": 0,
                    "initial_physical_generation_requests": 0,
                    "correction_physical_generation_requests": 0,
                    "transport_retries": 0,
                    "correction_path_entered": False,
                    "first_pass_schema_valid": None,
                    "eventual_schema_valid": False,
                    "correction_success": False,
                    "final_structured_output_status": "NOT_REACHED",
                    "planner_wire_diagnostic_capture_status": "READY",
                    "planner_wire_diagnostic_records": 0,
                }
            )
        if not evidence_is_redacted(state):
            raise D5HarnessError("smoke state redaction failure")
        _atomic_json(paths.state, state, exclusive=True)
        _append_jsonl(
            paths.journal,
            {
                "event": "smoke_started",
                "mode": custody_mode,
                "campaign_id": paths.campaign_id,
                "authorization_id": authorization.authorization_id,
                "status": "SMOKE_STARTED",
            },
            exclusive=True,
        )
        paths.model_io.touch(exist_ok=False)
        if ledger.mode == SMOKE_PLANNER_KIND:
            _write_private_exclusive(paths.planner_wire_diagnostics, b"")
        return cls(
            paths=paths,
            authorization=authorization,
            state=state,
            ledger=ledger,
        )

    @classmethod
    def pre_smoke_failure(
        cls,
        paths: EvidencePaths,
        *,
        authorization: D5Authorization,
        static_preflight: Mapping[str, Any],
        endpoint_calls: int,
        reason: str,
        binding_input_preflighted: bool = False,
        smoke_kind: str | None = None,
    ) -> D5SmokeCustody:
        """Create durable pre-smoke evidence without asserting smoke started."""
        if authorization.section_action_capture_mode != "off":
            _prepare_private_campaign_root(paths.root)
        ensure_fresh_namespace(
            paths,
            existing_allowed=(
                (paths.binding_request, paths.binding_request_compilation)
                if binding_input_preflighted
                else ()
            ),
        )
        state = {
            "experiment_version": D5_EXPERIMENT_VERSION,
            "mode": (
                "canonical_planner_only_smoke"
                if smoke_kind == SMOKE_PLANNER_KIND
                else "canonical_live_smoke"
            ),
            "campaign_id": paths.campaign_id,
            "authorization_id": authorization.authorization_id,
            "status": "SMOKE_NOT_STARTED",
            "provider": authorization.provider,
            "model": authorization.model,
            "endpoint_calls": endpoint_calls,
            "identity_endpoint_calls": endpoint_calls,
            "logical_generation_calls": 0,
            "physical_generation_attempts": 0,
            "provider_calls": 0,
            "model_calls": 0,
            "scientific_population_loaded": False,
            "scientific_campaign_started": False,
            "readiness": None,
            "static_preflight": dict(static_preflight),
            "reason": reason,
        }
        if smoke_kind is not None:
            state["smoke_kind"] = smoke_kind
        if not evidence_is_redacted(state):
            raise D5HarnessError("smoke state redaction failure")
        _atomic_json(paths.state, state, exclusive=True)
        _append_jsonl(
            paths.journal,
            {
                "event": "smoke_not_started",
                "mode": state["mode"],
                "campaign_id": paths.campaign_id,
                "authorization_id": authorization.authorization_id,
                "status": "SMOKE_NOT_STARTED",
                "endpoint_calls": endpoint_calls,
                "reason": reason,
            },
            exclusive=True,
        )
        paths.model_io.touch(exist_ok=False)
        return cls(paths=paths, authorization=authorization, state=state)

    def record_binding_request(self, request: str) -> None:
        """Persist the exact safe engineering request before compiling it."""
        request_hash = hashlib.sha256(request.encode("utf-8")).hexdigest()
        request_record = {
            "smoke_kind": SMOKE_BINDING_KIND,
            "request_sha256": request_hash,
            "request": request,
        }
        if not evidence_is_redacted(request_record):
            raise D5HarnessError("binding-smoke input redaction failure")
        _atomic_json(self.paths.binding_request, request_record, exclusive=True)

    def record_binding_request_compilation(
        self,
        compilation: RequestCompilationResult,
    ) -> None:
        """Persist the deterministic provider-free request compilation result."""
        compilation_record = compilation.model_dump(mode="json")
        if not evidence_is_redacted(compilation_record):
            raise D5HarnessError("binding-smoke compilation redaction failure")
        _atomic_json(
            self.paths.binding_request_compilation,
            compilation_record,
            exclusive=True,
        )

    def record_unexpected_host_exception(
        self,
        error: BaseException,
        *,
        last_completed_stage: str,
        event_name: str = "BINDING_SMOKE_HOST_EXCEPTION",
    ) -> None:
        """Record bounded exception location without locals or traceback text."""
        traceback = error.__traceback__
        last_frame = None
        while traceback is not None:
            last_frame = traceback.tb_frame
            line_number = traceback.tb_lineno
            traceback = traceback.tb_next
        if last_frame is None:
            location = {
                "source_file_basename": None,
                "function": None,
                "line_number": None,
            }
        else:
            location = {
                "source_file_basename": Path(last_frame.f_code.co_filename).name,
                "function": last_frame.f_code.co_name,
                "line_number": line_number,
            }
        self.record_planner_observability(
            {
                "event": event_name,
                "exception_type": type(error).__name__,
                "exception_module": type(error).__module__,
                **location,
                "last_completed_stage": last_completed_stage,
            }
        )

    def record_section_action(self, event: Mapping[str, Any]) -> None:
        """Persist one bounded, schema-validated worker action DTO."""
        mode = self.authorization.section_action_capture_mode
        if mode != "off":
            self._record_section_action_observation(event, mode=mode)
            return
        action = event.get("action")
        if not isinstance(action, Mapping):
            raise D5HarnessError("validated section action is not an object")
        row = {
            "event": "SECTION_ACTION_VALIDATED",
            "attempt": event.get("attempt"),
            "response_schema": "SectionSemanticActionResponse",
        }
        encoded = json.dumps(row, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_SECTION_ACTION_EVIDENCE_BYTES:
            raise D5HarnessError("validated section action evidence exceeds its bound")
        if not evidence_is_redacted(row):
            raise D5HarnessError("validated section action redaction failure")
        with self.paths.section_actions.open("a", encoding="utf-8") as handle:
            handle.write(encoded + "\n")

    def _record_section_action_observation(self, event: Mapping[str, Any], *, mode: str) -> None:
        """Retain opt-in metadata and, when authorized, one complete screened DTO."""
        name = event.get("event")
        created_dto: Path | None = None
        if name in {
            "SECTION_ACTION_SCHEMA_VALIDATED",
            "SECTION_ACTION_CONTRACT_RESULT",
            "SECTION_ACTION_VALIDATED",
        }:
            allowed = {
                "event",
                "event_version",
                "worker_role",
                "task_index",
                "attempt",
                "logical_call_index",
                "response_schema",
                "dto_sha256",
                "dto_size_bytes",
                "snapshot_id",
                "request_sha256",
                "work_contract_sha256",
                "operation_contract_sha256",
                "validation_result_sha256",
                "capture_state",
                "contract_outcome",
                "diagnostic_code",
                "mismatch",
            }
            row = {key: value for key, value in event.items() if key in allowed}
            index = row.get("logical_call_index")
            if (
                not isinstance(index, int)
                or isinstance(index, bool)
                or self.ledger.roles_by_index.get(index) != "section_worker"
            ):
                raise D5HarnessError("section observation call identity mismatch")
            if row.get("worker_role") != "section_worker" or row.get("attempt") not in {1, 2}:
                raise D5HarnessError("section observation identity is invalid")
            if (
                not isinstance(row.get("task_index"), int)
                or isinstance(row["task_index"], bool)
                or row["task_index"] < 0
            ):
                raise D5HarnessError("section observation task identity is invalid")
            if row.get("event_version") != "wellplot.section-action-observation.v1":
                raise D5HarnessError("section observation version is invalid")
            if row.get("response_schema") not in {
                "ReconstructSectionAction",
                "AddTrackAction",
                "AddTracksAction",
                "UpdateCurveScaleAction",
                "AddFillAction",
            }:
                raise D5HarnessError("section observation schema is invalid")
            if not isinstance(row.get("dto_size_bytes"), int) or row["dto_size_bytes"] < 0:
                raise D5HarnessError("section observation size is invalid")
            if not isinstance(row.get("dto_sha256"), str) or not re.fullmatch(
                r"[0-9a-f]{64}", row["dto_sha256"]
            ):
                raise D5HarnessError("section observation digest is invalid")
            for field_name in (
                "request_sha256",
                "work_contract_sha256",
                "operation_contract_sha256",
                "validation_result_sha256",
            ):
                digest = row.get(field_name)
                if digest is not None and (
                    not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                ):
                    raise D5HarnessError("section evidence digest is invalid")
            if row.get("snapshot_id") is not None and not isinstance(row["snapshot_id"], str):
                raise D5HarnessError("section snapshot identity is invalid")
            if name == "SECTION_ACTION_SCHEMA_VALIDATED":
                expected_state = "complete" if mode == "validated_dto" else "metadata_only"
                if (
                    row.get("capture_state") != expected_state
                    or row.get("contract_outcome") != "NOT_EVALUATED"
                ):
                    raise D5HarnessError("section observation capture state is invalid")
                if mode == "diagnostics" and "action" in event:
                    raise D5HarnessError("diagnostics-only capture cannot retain a DTO")
            if name == "SECTION_ACTION_SCHEMA_VALIDATED" and mode == "validated_dto":
                action = event.get("action")
                if not isinstance(action, Mapping):
                    raise D5HarnessError("complete validated action is unavailable")
                encoded = json.dumps(
                    action, sort_keys=True, separators=(",", ":"), ensure_ascii=True
                ).encode("utf-8")
                if hashlib.sha256(encoded).hexdigest() != row["dto_sha256"] or len(
                    encoded
                ) != row.get("dto_size_bytes"):
                    raise D5HarnessError("validated action digest mismatch")
                directory = self.paths.validated_section_dtos
                filename = f"task-{row['task_index']}-call-{index}-attempt-{row['attempt']}.json"
                destination = directory / filename
                now = _utc_now()
                complete_metadata = {
                    "authorization_id": self.authorization.authorization_id,
                    "campaign_id": self.paths.campaign_id,
                    "dto_path": destination.relative_to(self.paths.root).as_posix(),
                    "captured_at_utc": now.isoformat(),
                    "retention_until_utc": (now + timedelta(days=30)).isoformat(),
                    "retention_days": 30,
                }
                full_size = len(
                    json.dumps(
                        {**row, **complete_metadata, "action": action},
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=True,
                    ).encode("utf-8")
                )
                reason = None
                if full_size > MAX_SECTION_ACTION_EVIDENCE_BYTES:
                    reason = "DTO_OVERSIZE"
                elif not _safe_validated_action(action):
                    reason = "DTO_SCREENING_REJECTED"
                if reason is not None:
                    row["capture_state"] = "INCOMPLETE"
                    row["capture_failure"] = reason
                    self._append_section_observation(row)
                    raise D5HarnessError("validated action capture rejected")
                directory.mkdir(mode=0o700, exist_ok=True)
                _require_private_directory(directory)
                _write_private_exclusive(destination, encoded)
                created_dto = destination
                row.update(complete_metadata)
        else:
            raise D5HarnessError("unknown section observation event")
        try:
            self._append_section_observation(row)
        except Exception:
            if created_dto is not None:
                created_dto.unlink()
            raise

    def _append_section_observation(self, row: Mapping[str, Any]) -> None:
        """Append bounded observation metadata without persisting model-controlled text."""
        bounded = dict(row)
        bounded.update(
            {
                "authorization_id": self.authorization.authorization_id,
                "campaign_id": self.paths.campaign_id,
            }
        )
        encoded = json.dumps(
            bounded, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        if len(encoded) > MAX_SECTION_ACTION_EVIDENCE_BYTES or not _safe_validated_action(bounded):
            raise D5HarnessError("section observation metadata rejected")
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.paths.section_actions, flags, 0o600)
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid()
            ):
                raise D5HarnessError("section observation file is not private")
            with os.fdopen(fd, "ab", closefd=False) as handle:
                handle.write(encoded + b"\n")
        finally:
            os.close(fd)

    def record_readiness(self, readiness: D5ReadinessProjectionProtocol) -> None:
        """Persist the bounded readiness projection before generation."""
        self.state["readiness"] = readiness.as_dict()
        _atomic_json(self.paths.state, self.state)

    def record_model_io(self, row: Mapping[str, Any]) -> None:
        """Persist observer output under the smoke namespace."""
        bounded = dict(row)
        bounded.update(
            {
                "campaign_id": self.paths.campaign_id,
                "authorization_id": self.authorization.authorization_id,
                "turn_id": SMOKE_TURN_ID,
            }
        )
        if not evidence_is_redacted(bounded):
            raise D5HarnessError("smoke model-I/O redaction failure")
        with self.paths.model_io.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(bounded, sort_keys=True, separators=(",", ":")) + "\n")

    def record_planner_wire_diagnostic(self, row: Mapping[str, Any]) -> None:
        """Persist exact planner wire evidence in a private bounded artifact."""
        if self.state.get("smoke_kind") != SMOKE_PLANNER_KIND:
            raise D5HarnessError("planner wire diagnostics require planner smoke custody")
        encoded = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
        record = encoded + b"\n"
        if len(record) > MAX_PLANNER_DIAGNOSTIC_RECORD_BYTES:
            self._fail_planner_wire_diagnostics("RECORD_LIMIT_EXCEEDED")
            raise D5HarnessError("planner wire diagnostic record limit exceeded")
        flags = os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.paths.planner_wire_diagnostics, flags)
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid()
            ):
                self._fail_planner_wire_diagnostics("PRIVATE_FILE_CHECK_FAILED")
                raise D5HarnessError("planner wire diagnostic file is not private")
            if info.st_size + len(record) > MAX_PLANNER_DIAGNOSTIC_FILE_BYTES:
                self._fail_planner_wire_diagnostics("FILE_LIMIT_EXCEEDED")
                raise D5HarnessError("planner wire diagnostic file limit exceeded")
            with os.fdopen(fd, "ab", closefd=False) as handle:
                handle.write(record)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            os.close(fd)
        self.state["planner_wire_diagnostic_records"] = (
            int(self.state.get("planner_wire_diagnostic_records", 0)) + 1
        )
        _atomic_json(self.paths.state, self.state)

    def _fail_planner_wire_diagnostics(self, reason: str) -> None:
        self.state["planner_wire_diagnostic_capture_status"] = "INCOMPLETE"
        self.state["planner_wire_diagnostic_failure"] = reason
        _atomic_json(self.paths.state, self.state)

    def record_bounded_model_io(self, row: Mapping[str, Any]) -> None:
        """Persist request/response hashes and metadata without raw payloads."""
        allowed = {
            "event",
            "turn_id",
            "logical_call_index",
            "role",
            "model",
            "physical_attempt",
            "request_sha256",
            "response_sha256",
            "http_status",
            "engine_outcome",
            "failure_category",
            "response_reason",
            "validation_shape",
            "termination_kind",
            "exception_type",
            "exception_module",
        }
        bounded = {key: row[key] for key in allowed if key in row}
        smoke_kind = self.state.get("smoke_kind")
        if smoke_kind == SMOKE_PLANNER_KIND:
            logical_index = bounded.get("logical_call_index")
            if isinstance(logical_index, int) and not isinstance(logical_index, bool):
                bounded["generation_purpose"] = _planner_generation_purpose(logical_index)
        turn_id = (
            SMOKE_PLANNER_TURN_ID
            if smoke_kind == SMOKE_PLANNER_KIND
            else SMOKE_BINDING_TURN_ID
            if smoke_kind == SMOKE_BINDING_KIND
            else SMOKE_TURN_ID
        )
        bounded.update(
            {
                "campaign_id": self.paths.campaign_id,
                "authorization_id": self.authorization.authorization_id,
                "turn_id": turn_id,
            }
        )
        if not evidence_is_redacted(bounded):
            raise D5HarnessError("smoke model-I/O redaction failure")
        with self.paths.model_io.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(bounded, sort_keys=True, separators=(",", ":")) + "\n")

    def record_planner_observability(self, event: Mapping[str, Any]) -> None:
        """Route opt-in canonical planner events to bounded, replayable artifacts."""
        name = event.get("event")
        if name == "PLANNER_GENERATION_PASS":
            row = {
                "attempt": event.get("attempt"),
                "response_schema": event.get("response_schema"),
                "validated_response": event.get("validated_response"),
            }
            if not evidence_is_redacted(row):
                raise D5HarnessError("planner wire response redaction failure")
            with self.paths.planner_wire.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            return
        if name == "REQUEST_COMPILATION_PASS":
            payload = {"result": event.get("result")}
            if not evidence_is_redacted(payload):
                raise D5HarnessError("request compilation redaction failure")
            _atomic_json(self.paths.request_compilation, payload, exclusive=True)
            return
        if name == "PLANNER_CONTEXT":
            payload = _sanitize_planner_context(event.get("context"))
            payload["source_asset_identities"] = self.state.get("source_asset_identities", [])
            if not evidence_is_redacted(payload):
                raise D5HarnessError("planner context redaction failure")
            _atomic_json(self.paths.planner_context, payload, exclusive=True)
            return
        bounded = dict(event)
        if not evidence_is_redacted(bounded):
            raise D5HarnessError("planner stage trace redaction failure")
        with self.paths.stage_trace.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(bounded, sort_keys=True, separators=(",", ":")) + "\n")

    def record_compile_result(self, result: object) -> None:
        """Persist public compile diagnostics even when the graph dispatched no workers."""
        diagnostics = [item.model_dump(mode="json") for item in getattr(result, "diagnostics", ())]
        workers = [item.model_dump(mode="json") for item in getattr(result, "workers", ())]
        metrics = getattr(result, "metrics", None)
        payload = {
            "success": bool(getattr(result, "success", False)),
            "diagnostics": diagnostics,
            "workers": workers,
            "metrics": None if metrics is None else metrics.model_dump(mode="json"),
            "obligations": [
                item.model_dump(mode="json") for item in getattr(result, "obligations", ())
            ],
            "merged_intent_present": getattr(result, "merged_intent", None) is not None,
        }
        if not evidence_is_redacted(payload):
            raise D5HarnessError("compile result redaction failure")
        _atomic_json(self.paths.compile_result, payload, exclusive=True)

    def record_attempt(self, logical_index: int) -> None:
        """Persist one physical attempt after the observer accepts it."""
        attempt = self.ledger.physical_attempt(logical_index)
        binding_event = self.ledger.mode in {SMOKE_BINDING_KIND, SMOKE_PLANNER_KIND}
        row = {
            "event": "smoke_physical_attempt",
            "campaign_id": self.paths.campaign_id,
            "authorization_id": self.authorization.authorization_id,
            "logical_call_index": logical_index,
            "physical_attempt": attempt,
        }
        if binding_event:
            row["generation_role"] = self.ledger.roles_by_index[logical_index]
            self.state["physical_generation_attempts"] = self.ledger.physical_attempts
            if self.ledger.mode == SMOKE_PLANNER_KIND:
                purpose = _planner_generation_purpose(logical_index)
                row["generation_purpose"] = purpose
                counter = (
                    "initial_physical_generation_requests"
                    if logical_index == 1
                    else "correction_physical_generation_requests"
                )
                self.state[counter] = int(self.state.get(counter, 0)) + 1
                if attempt > 1:
                    self.state["transport_retries"] = (
                        int(self.state.get("transport_retries", 0)) + 1
                    )
            _atomic_json(self.paths.state, self.state)
        _append_jsonl(
            self.paths.journal,
            row,
        )

    def record_binding_call_started(self, event: Mapping[str, Any]) -> None:
        """Record a canonical logical index and role before provider delegation."""
        smoke_kind = self.state.get("smoke_kind")
        if smoke_kind not in {SMOKE_BINDING_KIND, SMOKE_PLANNER_KIND}:
            raise D5HarnessError("canonical smoke callback used outside role-accounted mode")
        index = int(event["index"])
        role = str(event.get("generation_role", ""))
        self.ledger.record_canonical_call_started(index, role)
        self.state["logical_generation_calls"] = self.ledger.logical_calls
        self.state["logical_calls_by_role"] = dict(self.ledger.calls_by_role)
        generation_purpose = None
        if self.ledger.mode == SMOKE_PLANNER_KIND:
            generation_purpose = _planner_generation_purpose(index)
            counter = (
                "initial_generation_requests" if index == 1 else "correction_generation_requests"
            )
            self.state[counter] = int(self.state.get(counter, 0)) + 1
        _atomic_json(self.paths.state, self.state)
        row = {
            "event": "logical_call_started",
            "mode": smoke_kind,
            "campaign_id": self.paths.campaign_id,
            "authorization_id": self.authorization.authorization_id,
            "logical_call_index": index,
            "generation_role": role,
            "provider": event.get("provider"),
            "model": event.get("model"),
        }
        if generation_purpose is not None:
            row["generation_purpose"] = generation_purpose
        _append_jsonl(self.paths.journal, row)

    def record_binding_call_completed(self, event: Mapping[str, Any]) -> None:
        """Record bounded completion metadata for one admitted canonical call."""
        index = int(event.get("index", 0))
        role = str(event.get("generation_role", ""))
        self.ledger.validate_call_event(index, role)
        _append_jsonl(
            self.paths.journal,
            {
                "event": "logical_call_completed",
                "mode": self.state["smoke_kind"],
                "campaign_id": self.paths.campaign_id,
                "authorization_id": self.authorization.authorization_id,
                "logical_call_index": index,
                "generation_role": role,
                **(
                    {"generation_purpose": _planner_generation_purpose(index)}
                    if self.ledger.mode == SMOKE_PLANNER_KIND
                    else {}
                ),
                "outcome": event.get("outcome"),
                "failure_category": event.get("failure_category"),
            },
        )

    def record_binding_call_aborted(self, event: Mapping[str, Any]) -> None:
        """Record bounded termination metadata for one admitted canonical call."""
        index = int(event.get("index", 0))
        role = str(event.get("generation_role", ""))
        self.ledger.validate_call_event(index, role)
        _append_jsonl(
            self.paths.journal,
            {
                "event": "logical_call_aborted",
                "mode": self.state["smoke_kind"],
                "campaign_id": self.paths.campaign_id,
                "authorization_id": self.authorization.authorization_id,
                "logical_call_index": index,
                "generation_role": role,
                **(
                    {"generation_purpose": _planner_generation_purpose(index)}
                    if self.ledger.mode == SMOKE_PLANNER_KIND
                    else {}
                ),
                "termination_kind": event.get("termination_kind"),
                "exception_type": event.get("exception_type"),
                "exception_module": event.get("exception_module"),
            },
        )

    def bind_binding_smoke_observability(self, adapter: object) -> None:
        """Bind canonical lifecycle callbacks to role-accounted smoke custody."""
        smoke_kind = self.state.get("smoke_kind")
        if smoke_kind not in {SMOKE_BINDING_KIND, SMOKE_PLANNER_KIND}:
            raise D5HarnessError("role-accounted smoke wiring requires canonical smoke custody")
        binders = {
            "bind_call_started": self.record_binding_call_started,
            "bind_call_completed": self.record_binding_call_completed,
            "bind_call_aborted": self.record_binding_call_aborted,
            "bind_physical_attempt": self.record_attempt,
            "bind_model_io": self.record_bounded_model_io,
        }
        for name, callback in binders.items():
            binder = getattr(adapter, name, None)
            if not callable(binder):
                raise D5HarnessError("canonical binding-smoke observer is unavailable")
            binder(callback)
        if smoke_kind == SMOKE_PLANNER_KIND:
            planner_binder = getattr(adapter, "bind_planner_diagnostic", None)
            if not callable(planner_binder):
                raise D5HarnessError("canonical planner diagnostic observer is unavailable")
            planner_binder(self.record_planner_wire_diagnostic)
        set_active_turn = getattr(adapter, "set_active_turn", None)
        if not callable(set_active_turn):
            raise D5HarnessError("canonical binding-smoke observer is unavailable")
        turn_id = (
            SMOKE_PLANNER_TURN_ID if smoke_kind == SMOKE_PLANNER_KIND else SMOKE_BINDING_TURN_ID
        )
        set_active_turn(turn_id)

    def finish(self, outcome: str, *, reason: str | None = None) -> dict[str, Any]:
        """Seal one bounded smoke terminal and its digest summary."""
        allowed = {
            "SMOKE_PASS",
            "SMOKE_ENVIRONMENT_BLOCKED",
            "SMOKE_NOT_READY",
            "SMOKE_PROVIDER_INCONCLUSIVE",
            "SMOKE_HARNESS_FAIL",
            "SMOKE_CONTRACT_FAIL",
        }
        if outcome not in allowed or self.terminal_written or self.paths.terminal.exists():
            raise D5HarnessError("invalid or duplicate smoke terminal")
        dto_paths: list[Path] = []
        if (
            self.paths.validated_section_dtos.is_symlink()
            or self.paths.validated_section_dtos.exists()
        ):
            if self.authorization.section_action_capture_mode != "validated_dto":
                raise D5HarnessError("validated DTO capture was not authorized")
            _require_private_directory(self.paths.validated_section_dtos)
            dto_paths = sorted(self.paths.validated_section_dtos.iterdir())
        for path in dto_paths:
            info = path.lstat()
            if (
                not re.fullmatch(r"task-\d+-call-\d+-attempt-[12]\.json", path.name)
                or path.is_symlink()
                or not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid()
            ):
                raise D5HarnessError("validated DTO file is not private")
        if dto_paths and not self.paths.section_actions.is_file():
            raise D5HarnessError("validated DTO metadata is unavailable")
        if (
            self.authorization.section_action_capture_mode == "validated_dto"
            and self.paths.section_actions.is_file()
        ):
            captured: dict[str, str] = {}
            for line in self.paths.section_actions.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if (
                    row.get("event") == "SECTION_ACTION_SCHEMA_VALIDATED"
                    and row.get("capture_state") == "complete"
                ):
                    relative = str(row.get("dto_path", ""))
                    if relative in captured:
                        raise D5HarnessError("duplicate validated DTO metadata")
                    captured[relative] = str(row.get("dto_sha256", ""))
            actual = {path.relative_to(self.paths.root).as_posix(): path for path in dto_paths}
            if set(actual) != set(captured):
                raise D5HarnessError("validated DTO custody set does not match metadata")
            if any(_sha256_file(path) != captured[relative] for relative, path in actual.items()):
                raise D5HarnessError("validated DTO custody digest mismatch")
        state = json.loads(self.paths.state.read_text(encoding="utf-8"))
        endpoint_calls = int(state.get("endpoint_calls", 0))
        state.update(
            {
                "status": "SMOKE_TERMINAL",
                "outcome": outcome,
                "reason": reason,
                "logical_generation_calls": self.ledger.logical_calls,
                "physical_generation_attempts": self.ledger.physical_attempts,
                "provider_calls": self.ledger.logical_calls,
                "model_calls": self.ledger.logical_calls,
            }
        )
        if self.ledger.mode in {SMOKE_BINDING_KIND, SMOKE_PLANNER_KIND}:
            state["logical_calls_by_role"] = dict(self.ledger.calls_by_role)
        if self.ledger.mode == SMOKE_PLANNER_KIND:
            reliability_fields = (
                "logical_planner_invocations",
                "initial_generation_requests",
                "correction_generation_requests",
                "initial_physical_generation_requests",
                "correction_physical_generation_requests",
                "transport_retries",
                "correction_path_entered",
                "first_pass_schema_valid",
                "eventual_schema_valid",
                "correction_success",
                "final_structured_output_status",
            )
            terminal_fields = {
                field_name: state.get(field_name) for field_name in reliability_fields
            }
            state.update(terminal_fields)
        _atomic_json(self.paths.state, state)
        journal_terminal = {
            "event": "smoke_terminal",
            "campaign_id": self.paths.campaign_id,
            "authorization_id": self.authorization.authorization_id,
            "outcome": outcome,
            "reason": reason,
            "logical_generation_calls": self.ledger.logical_calls,
            "physical_generation_attempts": self.ledger.physical_attempts,
        }
        if self.ledger.mode in {SMOKE_BINDING_KIND, SMOKE_PLANNER_KIND}:
            journal_terminal["logical_calls_by_role"] = dict(self.ledger.calls_by_role)
        _append_jsonl(self.paths.journal, journal_terminal)
        terminal = {
            "experiment_version": D5_EXPERIMENT_VERSION,
            "mode": state["mode"],
            "campaign_id": self.paths.campaign_id,
            "authorization_id": self.authorization.authorization_id,
            "outcome": outcome,
            "reason": reason,
            "logical_generation_calls": self.ledger.logical_calls,
            "physical_generation_attempts": self.ledger.physical_attempts,
            "endpoint_calls": endpoint_calls,
            "identity_endpoint_calls": endpoint_calls,
            "provider_calls": self.ledger.logical_calls,
            "model_calls": self.ledger.logical_calls,
            "scientific_population_loaded": False,
            "scientific_campaign_started": False,
            "state_sha256": _sha256_file(self.paths.state),
            "journal_sha256": _sha256_file(self.paths.journal),
            "model_io_sha256": _sha256_file(self.paths.model_io),
            "observability_artifacts": {
                path.relative_to(self.paths.root).as_posix(): _sha256_file(path)
                for path in (
                    self.paths.compile_result,
                    self.paths.planner_wire,
                    self.paths.planner_wire_diagnostics,
                    self.paths.request_compilation,
                    self.paths.planner_context,
                    self.paths.section_actions,
                    self.paths.stage_trace,
                    self.paths.binding_request,
                    self.paths.binding_request_compilation,
                    *dto_paths,
                )
                if path.is_file()
            },
        }
        if self.ledger.mode in {SMOKE_BINDING_KIND, SMOKE_PLANNER_KIND}:
            terminal["logical_calls_by_role"] = dict(self.ledger.calls_by_role)
        if self.ledger.mode == SMOKE_PLANNER_KIND:
            terminal.update(terminal_fields)
        _atomic_json(self.paths.terminal, terminal, exclusive=True)
        summary = dict(terminal)
        summary["terminal_sha256"] = _sha256_file(self.paths.terminal)
        _atomic_json(self.paths.summary, summary, exclusive=True)
        self.terminal_written = True
        return terminal


def ensure_fresh_namespace(
    paths: EvidencePaths,
    *,
    existing_allowed: Sequence[Path] = (),
) -> None:
    """Reject any collision before readiness or campaign creation."""
    allowed = set(existing_allowed)
    if any(path.exists() for path in paths.all_paths() if path not in allowed):
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


def _safe_validated_action(value: object) -> bool:
    """Best-effort secret and absolute-path screening of untrusted DTO strings."""
    if isinstance(value, Mapping):
        return all(
            str(key).casefold() not in {item.casefold() for item in SECRET_KEYS}
            and _safe_validated_action(str(key))
            and _safe_validated_action(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return all(_safe_validated_action(item) for item in value)
    if isinstance(value, str):
        if not evidence_is_redacted(value):
            return False
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            return False
        if re.search(
            r"(?i)\b(?:sk-[a-z0-9_-]{12,}|akia[a-z0-9]{16})\b|-----begin [^-]*private key-----",
            value,
        ):
            return False
        return (
            re.search(r"(?<![A-Za-z0-9])/(?!/)|(?<![A-Za-z0-9])[A-Za-z]:[\\/]|\\\\", value) is None
        )
    return value is None or isinstance(value, (bool, int, float))


def _utc_now() -> datetime:
    """Return the current UTC time for the local retention boundary."""
    return datetime.now(UTC)


def _require_private_directory(path: Path) -> None:
    """Require an owned real directory that is inaccessible to group and others."""
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o700
        or info.st_uid != os.geteuid()
    ):
        raise D5HarnessError("validated DTO directory is not private")


def _prepare_private_campaign_root(root: Path) -> None:
    """Require private campaign files and a process umask that keeps new files private."""
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    _require_private_directory(root)
    try:
        status = Path("/proc/self/status").read_text(encoding="utf-8")
        umask_line = next(line for line in status.splitlines() if line.startswith("Umask:"))
        current_umask = int(umask_line.split()[1], 8)
    except (OSError, StopIteration, ValueError, IndexError):
        raise D5HarnessError("private campaign umask cannot be verified") from None
    if current_umask & 0o077 != 0o077:
        raise D5HarnessError("private campaign requires umask 077")
    for child in root.iterdir():
        info = child.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid()
        ):
            raise D5HarnessError("pre-existing campaign entry is not a private file")


def _validate_section_capture_location(repo_root: Path, root: Path) -> None:
    """Keep opt-in section custody under the ignored local evaluation workspace."""
    repository = repo_root.resolve()
    workspace = (repository / "workspace/evaluations").resolve()
    destination = root.resolve()
    if destination == workspace or not destination.is_relative_to(workspace):
        raise D5StaticPreflightError("section capture must be under workspace/evaluations")
    probe = (destination / "validated-dto-probe.json").relative_to(repository)
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", "--", str(probe)],
        cwd=repository,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if ignored.returncode != 0:
        raise D5StaticPreflightError("section capture is not Git-ignored")


def _write_private_exclusive(path: Path, data: bytes) -> None:
    """Create a private DTO atomically without following an existing path."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise D5HarnessError("validated DTO file is not private")
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        os.unlink(path)
        raise
    finally:
        os.close(fd)


def verify_smoke_observability(paths: EvidencePaths) -> dict[str, object]:
    """Verify sealed smoke evidence, allowing only recorded DTO retention deletions."""
    terminal = json.loads(paths.terminal.read_text(encoding="utf-8"))
    summary = json.loads(paths.summary.read_text(encoding="utf-8"))
    terminal_sha = _sha256_file(paths.terminal)
    if summary.get("terminal_sha256") != terminal_sha:
        raise D5HarnessError("smoke terminal digest mismatch")
    for path, digest_field in (
        (paths.state, "state_sha256"),
        (paths.journal, "journal_sha256"),
        (paths.model_io, "model_io_sha256"),
    ):
        if _sha256_file(path) != terminal.get(digest_field):
            raise D5HarnessError("smoke custody digest mismatch")
    deleted: dict[str, str] = {}
    if paths.dto_deletion_receipt.is_symlink() or paths.dto_deletion_receipt.exists():
        receipt_info = paths.dto_deletion_receipt.lstat()
        if (
            not stat.S_ISREG(receipt_info.st_mode)
            or stat.S_IMODE(receipt_info.st_mode) != 0o600
            or receipt_info.st_uid != os.geteuid()
        ):
            raise D5HarnessError("DTO deletion receipt is not private")
        receipt = json.loads(paths.dto_deletion_receipt.read_text(encoding="utf-8"))
        if (
            receipt.get("terminal_sha256") != terminal_sha
            or receipt.get("campaign_id") != paths.campaign_id
            or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,128}", str(receipt.get("deletion_authorization_id", ""))
            )
        ):
            raise D5HarnessError("DTO deletion receipt is invalid")
        deleted = dict(receipt.get("authorized_files", {}))
    artifacts = terminal.get("observability_artifacts", {})
    if deleted:
        if artifacts.get(paths.section_actions.name) != _sha256_file(paths.section_actions):
            raise D5HarnessError("DTO metadata digest mismatch")
        try:
            authorized_at = datetime.fromisoformat(str(receipt.get("authorized_at_utc", "")))
        except ValueError:
            raise D5HarnessError("DTO deletion receipt time is invalid") from None
        if authorized_at.tzinfo is None:
            raise D5HarnessError("DTO deletion receipt time is invalid")
        rows = [
            json.loads(line)
            for line in paths.section_actions.read_text(encoding="utf-8").splitlines()
        ]
        captured = {
            row.get("dto_path"): row
            for row in rows
            if row.get("event") == "SECTION_ACTION_SCHEMA_VALIDATED"
            and row.get("capture_state") == "complete"
        }
        for name, digest in deleted.items():
            row = captured.get(name)
            if row is None or row.get("dto_sha256") != digest:
                raise D5HarnessError("DTO deletion receipt lacks matching capture metadata")
            try:
                expiry = datetime.fromisoformat(str(row.get("retention_until_utc", "")))
            except ValueError:
                raise D5HarnessError("DTO retention time is invalid") from None
            if expiry.tzinfo is None or authorized_at < expiry:
                raise D5HarnessError("DTO deletion receipt predates retention expiry")
    missing_dtos = 0
    if paths.validated_section_dtos.is_symlink() or paths.validated_section_dtos.exists():
        _require_private_directory(paths.validated_section_dtos)
        for path in paths.validated_section_dtos.iterdir():
            relative = path.relative_to(paths.root).as_posix()
            if relative not in artifacts or path.is_symlink():
                raise D5HarnessError("unsealed validated DTO entry")
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                raise D5HarnessError("validated DTO file is not private")
    for relative, expected in artifacts.items():
        path = paths.root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(paths.root.resolve()):
            raise D5HarnessError("smoke evidence path is unsafe")
        if path.is_file():
            if _sha256_file(path) != expected:
                raise D5HarnessError("smoke observation digest mismatch")
        elif (
            relative.startswith(paths.validated_section_dtos.name + "/")
            and deleted.get(relative) == expected
        ):
            missing_dtos += 1
        else:
            raise D5HarnessError("smoke observation is missing")
    if any(artifacts.get(name) != digest for name, digest in deleted.items()):
        raise D5HarnessError("DTO deletion receipt does not match the terminal")
    state = json.loads(paths.state.read_text(encoding="utf-8"))
    if state.get("section_action_capture_mode") in {"diagnostics", "validated_dto"}:
        _require_private_directory(paths.root)
        for path in paths.root.rglob("*"):
            info = path.lstat()
            if path.is_symlink() or info.st_uid != os.geteuid():
                raise D5HarnessError("private campaign entry is unsafe")
            expected_mode = 0o700 if stat.S_ISDIR(info.st_mode) else 0o600
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise D5HarnessError("private campaign entry is unsafe")
            if stat.S_IMODE(info.st_mode) != expected_mode:
                raise D5HarnessError("private campaign entry permissions drifted")
    if state.get("section_action_capture_mode") in {"diagnostics", "validated_dto"}:
        starts = {
            row.get("logical_call_index"): row.get("generation_role")
            for row in (
                json.loads(line) for line in paths.journal.read_text(encoding="utf-8").splitlines()
            )
            if row.get("event") == "logical_call_started"
        }
        observed: dict[tuple[object, ...], str | None] = {}
        observation_bindings: dict[tuple[object, ...], dict[str, object]] = {}
        metadata_dtos: set[str] = set()
        if paths.section_actions.exists():
            for line in paths.section_actions.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if (
                    row.get("campaign_id") != paths.campaign_id
                    or row.get("authorization_id") != terminal.get("authorization_id")
                    or row.get("worker_role") != "section_worker"
                    or starts.get(row.get("logical_call_index")) != "section_worker"
                ):
                    raise D5HarnessError("section observation identity mismatch")
                key = tuple(
                    row.get(name)
                    for name in ("task_index", "attempt", "logical_call_index", "dto_sha256")
                )
                if row.get("event") == "SECTION_ACTION_SCHEMA_VALIDATED":
                    if key in observed:
                        raise D5HarnessError("duplicate section observation")
                    observed[key] = None
                    observation_bindings[key] = {
                        name: row.get(name)
                        for name in (
                            "snapshot_id",
                            "request_sha256",
                            "work_contract_sha256",
                            "operation_contract_sha256",
                        )
                    }
                    if row.get("capture_state") == "complete" and artifacts.get(
                        row.get("dto_path")
                    ) != row.get("dto_sha256"):
                        raise D5HarnessError("validated DTO digest is not sealed")
                    if row.get("capture_state") == "complete":
                        expected_path = (
                            f"{paths.validated_section_dtos.name}/task-{row['task_index']}"
                            f"-call-{row['logical_call_index']}-attempt-{row['attempt']}.json"
                        )
                        if row.get("dto_path") != expected_path:
                            raise D5HarnessError("validated DTO path is uncorrelated")
                        metadata_dtos.add(expected_path)
                        try:
                            captured_at = datetime.fromisoformat(
                                str(row.get("captured_at_utc", ""))
                            )
                            expiry = datetime.fromisoformat(str(row.get("retention_until_utc", "")))
                        except ValueError:
                            raise D5HarnessError(
                                "validated DTO retention metadata is invalid"
                            ) from None
                        if (
                            captured_at.tzinfo is None
                            or expiry.tzinfo is None
                            or row.get("retention_days") != 30
                            or expiry - captured_at != timedelta(days=30)
                        ):
                            raise D5HarnessError("validated DTO retention metadata is invalid")
                elif row.get("event") == "SECTION_ACTION_CONTRACT_RESULT":
                    if key not in observed or observed[key] is not None:
                        raise D5HarnessError("section contract result is uncorrelated")
                    if any(
                        row.get(field) != value
                        for field, value in observation_bindings[key].items()
                    ):
                        raise D5HarnessError("section contract evidence binding changed")
                    outcome = row.get("contract_outcome")
                    if outcome not in {"PASS", "FAIL"}:
                        raise D5HarnessError("section contract outcome is invalid")
                    if not isinstance(row.get("validation_result_sha256"), str) or not re.fullmatch(
                        r"[0-9a-f]{64}", row["validation_result_sha256"]
                    ):
                        raise D5HarnessError("section validation result digest is invalid")
                    validation_result = {
                        name: row.get(name)
                        for name in ("contract_outcome", "diagnostic_code", "mismatch")
                    }
                    if row["validation_result_sha256"] != _sha256_json(validation_result):
                        raise D5HarnessError("section validation result digest mismatch")
                    observed[key] = outcome
                elif row.get("event") == "SECTION_ACTION_VALIDATED":
                    if observed.get(key) != "PASS":
                        raise D5HarnessError("accepted section action lacks a passing contract")
                else:
                    raise D5HarnessError("unknown section observation")
        sealed_dtos = {
            name for name in artifacts if name.startswith(paths.validated_section_dtos.name + "/")
        }
        if sealed_dtos != metadata_dtos:
            raise D5HarnessError("sealed DTO set does not match observation metadata")
        if (
            any(outcome is None for outcome in observed.values())
            and terminal.get("reason") != "section_action_evidence_integrity"
        ):
            raise D5HarnessError("section observation lacks a contract outcome")
    return {"terminal_sha256": terminal_sha, "authorized_deleted_dtos": missing_dtos}


def delete_expired_validated_dtos(
    paths: EvidencePaths,
    *,
    deletion_authorization_id: str,
) -> dict[str, object]:
    """Delete expired private DTOs only under an explicit local authorization."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", deletion_authorization_id):
        raise D5HarnessError("DTO deletion authorization is invalid")
    if paths.dto_deletion_receipt.exists():
        raise D5HarnessError("DTO deletion was already authorized")
    verification = verify_smoke_observability(paths)
    terminal = json.loads(paths.terminal.read_text(encoding="utf-8"))
    current = _utc_now()
    if current.tzinfo is None:
        raise D5HarnessError("DTO deletion time must include a timezone")
    files: dict[str, str] = {}
    for line in paths.section_actions.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if (
            row.get("event") != "SECTION_ACTION_SCHEMA_VALIDATED"
            or row.get("capture_state") != "complete"
        ):
            continue
        relative = str(row.get("dto_path", ""))
        if not relative.startswith(paths.validated_section_dtos.name + "/"):
            raise D5HarnessError("DTO retention path is invalid")
        try:
            expiry = datetime.fromisoformat(str(row.get("retention_until_utc", "")))
        except ValueError:
            raise D5HarnessError("DTO retention time is invalid") from None
        if expiry.tzinfo is None or current < expiry:
            raise D5HarnessError("DTO retention period has not expired")
        digest = terminal.get("observability_artifacts", {}).get(relative)
        if digest != row.get("dto_sha256"):
            raise D5HarnessError("DTO retention digest mismatch")
        files[relative] = digest
    if not files:
        raise D5HarnessError("no retained DTOs are eligible for deletion")
    receipt = {
        "campaign_id": paths.campaign_id,
        "deletion_authorization_id": deletion_authorization_id,
        "terminal_sha256": verification["terminal_sha256"],
        "authorized_at_utc": current.isoformat(),
        "authorized_files": files,
    }
    if not evidence_is_redacted(receipt):
        raise D5HarnessError("DTO deletion receipt failed screening")
    _write_private_exclusive(
        paths.dto_deletion_receipt,
        (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    )
    for relative in files:
        (paths.root / relative).unlink()
    return receipt


def _sanitize_planner_context(value: object) -> dict[str, Any]:
    """Retain replay context while reducing filesystem paths to safe relative labels."""
    if not isinstance(value, Mapping):
        raise D5HarnessError("planner context is not a mapping")

    path_keys = {"path", "source_path", "canonical_path", "absolute_path"}

    def sanitize(item: object, *, key: str | None = None) -> object:
        if isinstance(item, Mapping):
            return {str(name): sanitize(child, key=str(name)) for name, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [sanitize(child) for child in item]
        if isinstance(item, str) and key in path_keys and Path(item).is_absolute():
            return Path(item).name
        return item

    safe = sanitize(value)
    if not isinstance(safe, dict):
        raise D5HarnessError("planner context projection failed")
    return safe


def _sanitize_source_asset_identities(
    identities: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Retain bounded source identity fields without absolute filesystem paths."""
    allowed = {"asset_id", "relative_path", "path_basename", "format", "size_bytes", "sha256"}
    result: list[dict[str, Any]] = []
    for identity in identities:
        bounded = {key: value for key, value in identity.items() if key in allowed}
        if "relative_path" in bounded and Path(str(bounded["relative_path"])).is_absolute():
            raise D5HarnessError("source asset identity contains an absolute path")
        if not evidence_is_redacted(bounded):
            raise D5HarnessError("source asset identity redaction failure")
        result.append(bounded)
    return result


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
    _failure_candidates: list[dict[str, Any]] = field(default_factory=list)
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

    def record_call_aborted(self, event: Mapping[str, Any]) -> None:
        """Persist bounded termination evidence without inventing completion."""
        self._failure_candidates.append(
            {
                "failure_kind": (
                    "cancellation"
                    if event.get("termination_kind") == "cancelled"
                    else "logical_abort"
                ),
                "index": event.get("index"),
                "role": event.get("generation_role"),
                "exception_type": event.get("exception_type"),
                "exception_module": event.get("exception_module"),
                "termination_kind": event.get("termination_kind"),
            }
        )
        _append_jsonl(
            self.paths.journal,
            {
                "event": "logical_call_aborted",
                "experiment_version": D5_EXPERIMENT_VERSION,
                "campaign_id": self.campaign_id,
                "authorization_id": self.authorization_id,
                "index": event.get("index"),
                "generation_role": event.get("generation_role"),
                "provider": event.get("provider"),
                "model": event.get("model"),
                "termination_kind": event.get("termination_kind"),
                "exception_type": event.get("exception_type"),
                "exception_module": event.get("exception_module"),
                "status_code": event.get("status_code"),
                "timeout": event.get("timeout"),
                "primary_or_secondary": "PROVISIONAL",
            },
        )

    def record_worker_diagnostic(self, event: Mapping[str, Any]) -> None:
        """Persist bounded canonical worker exception evidence."""
        self._failure_candidates.append(
            {
                "failure_kind": "worker_exception",
                "index": None,
                "role": event.get("worker_kind"),
                "plan_order": event.get("plan_order"),
                "exception_type": event.get("exception_type"),
                "exception_module": event.get("exception_module"),
            }
        )
        _append_jsonl(
            self.paths.journal,
            {
                "event": "worker_exception",
                "experiment_version": D5_EXPERIMENT_VERSION,
                "campaign_id": self.campaign_id,
                "authorization_id": self.authorization_id,
                "worker_kind": event.get("worker_kind"),
                "plan_order": event.get("plan_order"),
                "stage": event.get("stage"),
                "exception_type": event.get("exception_type"),
                "exception_module": event.get("exception_module"),
                "provider_call_in_flight": event.get("provider_call_in_flight"),
                "provider_call_state": event.get("provider_call_state"),
                "primary_or_secondary": "PROVISIONAL",
            },
        )

    def record_campaign_exception(
        self,
        error: BaseException,
        *,
        active_turn: str | None,
        completed_worker_outcomes: Sequence[Mapping[str, Any]],
    ) -> None:
        """Persist top-level exception context before terminal classification."""
        self._failure_candidates.append(
            {
                "failure_kind": "campaign_exception",
                "index": self._active_logical_index,
                "role": None,
                "exception_type": type(error).__name__,
                "exception_module": type(error).__module__,
            }
        )
        started = [call for call in self.ledger.calls if call.get("outcome") != "reserved"]
        completed = [call for call in started if call.get("outcome") in {"completed", "failed"}]
        outstanding = [
            {
                "index": call.get("logical_call_index"),
                "role": call.get("role"),
            }
            for call in self.ledger.calls
            if call.get("outcome") == "reserved"
        ]
        outcomes = []
        for outcome in completed_worker_outcomes:
            outcomes.append(
                {
                    "turn_id": outcome.get("turn_id"),
                    "grader_status": outcome.get("grader_status"),
                    "attribution": outcome.get("attribution"),
                    "first_divergence": outcome.get("first_divergence"),
                }
            )
        _append_jsonl(
            self.paths.journal,
            {
                "event": "campaign_exception",
                "experiment_version": D5_EXPERIMENT_VERSION,
                "campaign_id": self.campaign_id,
                "authorization_id": self.authorization_id,
                "exception_type": type(error).__name__,
                "exception_module": type(error).__module__,
                "active_turn": active_turn,
                "last_started_logical_call": (
                    self.ledger.calls[-1].get("logical_call_index") if self.ledger.calls else None
                ),
                "last_completed_logical_call": (
                    completed[-1].get("logical_call_index") if completed else None
                ),
                "outstanding_logical_calls": outstanding,
                "completed_worker_outcomes": outcomes,
                "primary_or_secondary": "PROVISIONAL",
            },
        )

    def _record_failure_adjudication(self) -> None:
        """Seal order-independent primary/secondary ownership for candidates."""
        if not self._failure_candidates:
            return
        candidates = list(enumerate(self._failure_candidates))
        primary_index, primary = min(
            candidates,
            key=lambda item: (
                item[1].get("failure_kind") == "cancellation",
                item[0],
            ),
        )
        secondary = [candidate for index, candidate in candidates if index != primary_index]
        _append_jsonl(
            self.paths.journal,
            {
                "event": "failure_adjudication",
                "experiment_version": D5_EXPERIMENT_VERSION,
                "campaign_id": self.campaign_id,
                "authorization_id": self.authorization_id,
                "primary": primary,
                "secondary": secondary,
                "rule": "non_cancellation_precedes_cancellation",
            },
        )

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
        self._record_failure_adjudication()
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
        self.planner_diagnostic_callback: Callable[[dict[str, Any]], None] | None = None
        self.worker_diagnostic_callback: Callable[[dict[str, Any]], None] | None = None
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
        logical_context = d4.current_logical_call_context()
        if logical_context is None:
            if self.active_logical_index is None:
                raise D5HarnessError("generation attempt has no active logical call")
            logical_context = {
                "index": self.active_logical_index,
                "generation_role": self.active_role,
                "model": self.active_model,
            }
        if self.callback is None:
            raise D5HarnessError("generation attempt has no active logical call")
        logical_index = int(logical_context["index"])
        role = logical_context.get("generation_role")
        model = logical_context.get("model")
        attempt = self._attempts.get(logical_index, 0) + 1
        body = bytes(getattr(request, "content", b""))
        self._pending_responses[id(request)] = {
            "event": "physical_request",
            "turn_id": self.active_turn_id,
            "logical_call_index": logical_index,
            "role": role,
            "model": model,
            "physical_attempt": attempt,
            "request_sha256": hashlib.sha256(body).hexdigest(),
            "request_body_base64": base64.b64encode(body).decode("ascii"),
            "request_body": body.decode("utf-8", errors="replace"),
            "request_json": _json_body(body),
        }
        if self.planner_diagnostic_callback is not None:
            self.planner_diagnostic_callback(
                {
                    "event": "physical_request",
                    "generation_purpose": _planner_generation_purpose(logical_index),
                    "logical_call_index": logical_index,
                    "physical_attempt": attempt,
                    "request_sha256": hashlib.sha256(body).hexdigest(),
                    "request_body_base64": base64.b64encode(body).decode("ascii"),
                    "request_json": _json_body(body),
                }
            )
        self.callback(logical_index)
        self._attempts[logical_index] = attempt
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
            if key not in {"event", "request_body", "request_body_base64", "request_json"}
        }
        response_row.update(
            {
                "event": "physical_response",
                "http_status": getattr(response, "status_code", None),
                "response_sha256": hashlib.sha256(body).hexdigest(),
                "response_body_base64": base64.b64encode(body).decode("ascii"),
                "response_body": body.decode("utf-8", errors="replace"),
                "response_json": _json_body(body),
            }
        )
        if self.planner_diagnostic_callback is not None:
            response_json = _json_body(body)
            assistant_content = None
            if isinstance(response_json, Mapping):
                choices = response_json.get("choices")
                if isinstance(choices, list) and choices:
                    first_choice = choices[0]
                    if isinstance(first_choice, Mapping):
                        message = first_choice.get("message")
                        if isinstance(message, Mapping):
                            assistant_content = message.get("content")
            self.planner_diagnostic_callback(
                {
                    "event": "physical_response",
                    "generation_purpose": _planner_generation_purpose(
                        int(response_row["logical_call_index"])
                    ),
                    "logical_call_index": response_row["logical_call_index"],
                    "physical_attempt": response_row["physical_attempt"],
                    "http_status": response_row["http_status"],
                    "response_sha256": response_row["response_sha256"],
                    "response_body_base64": base64.b64encode(body).decode("ascii"),
                    "assistant_content": assistant_content,
                }
            )
        if self.model_io_callback is not None:
            self.model_io_callback(response_row)

    def logical_call_aborted(self, event: Mapping[str, Any]) -> None:
        """Close unresolved physical requests without fabricating responses."""
        logical_index = int(event["index"])
        pending_keys = [
            request_id
            for request_id, row in self._pending_responses.items()
            if row.get("logical_call_index") == logical_index
        ]
        for request_id in pending_keys:
            pending = self._pending_responses.pop(request_id)
            if self.model_io_callback is not None:
                self.model_io_callback(
                    {
                        "event": "physical_termination",
                        "turn_id": self.active_turn_id,
                        "logical_call_index": logical_index,
                        "role": pending.get("role"),
                        "model": pending.get("model"),
                        "physical_attempt": pending.get("physical_attempt"),
                        "request_sha256": pending.get("request_sha256"),
                        "termination_kind": event.get("termination_kind"),
                        "exception_type": event.get("exception_type"),
                        "exception_module": event.get("exception_module"),
                        "status_code": event.get("status_code"),
                        "timeout": event.get("timeout"),
                    }
                )
        if self.model_io_callback is not None:
            self.model_io_callback(
                {
                    "event": "logical_call_aborted",
                    "logical_call_index": logical_index,
                    "role": event.get("generation_role"),
                    "model": event.get("model"),
                    "termination_kind": event.get("termination_kind"),
                    "exception_type": event.get("exception_type"),
                    "exception_module": event.get("exception_module"),
                    "status_code": event.get("status_code"),
                    "timeout": event.get("timeout"),
                }
            )

    def set_active_turn(self, turn_id: str) -> None:
        """Set the current frozen turn without entering the provider body."""
        self.active_turn_id = str(turn_id)

    def bind_model_io(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Bind append-only model-I/O custody."""
        self.model_io_callback = callback

    def bind_planner_diagnostic(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Bind private planner-only raw request/response custody."""
        self.planner_diagnostic_callback = callback

    def bind_worker_diagnostic(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Bind canonical graph exception diagnostics to campaign custody."""
        self.worker_diagnostic_callback = callback

    def capture_worker_diagnostic(self, event: Mapping[str, Any]) -> None:
        """Forward bounded worker diagnostics without changing graph behavior."""
        if self.worker_diagnostic_callback is not None:
            self.worker_diagnostic_callback(dict(event))

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
            row = {
                "event": "logical_call_result",
                "logical_call_index": event.get("index"),
                "role": event.get("generation_role"),
                "model": event.get("model"),
                "engine_outcome": event.get("outcome"),
                "failure_category": event.get("failure_category"),
                "response_reason": response_reason,
                "validation_shape": validation_shape,
            }
            if self.planner_diagnostic_callback is not None:
                self.planner_diagnostic_callback(
                    {
                        **row,
                        "generation_purpose": _planner_generation_purpose(
                            int(event.get("index", 0))
                        ),
                    }
                )
            self.model_io_callback(row)


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

    def bind_call_aborted(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Forward logical aborts while closing unresolved transport observations."""

        def wrapped(event: dict[str, Any]) -> None:
            self.observer.logical_call_aborted(event)
            callback(event)

        self.inner.bind_call_aborted(wrapped)

    def bind_worker_diagnostic(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Bind canonical compile-worker exception evidence."""
        self.observer.bind_worker_diagnostic(callback)

    def bind_physical_attempt(self, callback: Callable[[int], None]) -> None:
        """Bind the D5 ledger to each observed SDK transport attempt."""
        self.observer.callback = callback

    def set_active_turn(self, turn_id: str) -> None:
        """Bind model-I/O records to the current campaign turn."""
        self.observer.set_active_turn(turn_id)

    def bind_model_io(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Bind exact transport body capture to campaign custody."""
        self.observer.bind_model_io(callback)

    def bind_planner_diagnostic(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Bind private raw planner wire capture to smoke custody."""
        self.observer.bind_planner_diagnostic(callback)

    async def execute_smoke(self, custody: D5SmokeCustody) -> SmokeReadyResponse:
        """Issue one smoke call through the adapter's existing provider backend."""
        backend = self.inner.session.session.compiler.dependencies.planner.backend
        delegate = getattr(backend, "delegate", None)
        if delegate is None or not callable(getattr(delegate, "generate_structured", None)):
            raise D5HarnessError("canonical provider backend is unavailable")
        logical_index = custody.ledger.reserve()
        self.set_active_turn(SMOKE_TURN_ID)
        self.observer.logical_call_started(
            {
                "index": logical_index,
                "generation_role": SMOKE_ROLE,
                "model": getattr(delegate, "model", ""),
            }
        )
        request = StructuredGenerationRequest(
            system_prompt=SMOKE_SYSTEM_PROMPT,
            user_prompt=SMOKE_USER_PROMPT,
            timeout_seconds=EXPECTED_TIMEOUT_SECONDS,
            temperature=0.0,
        )
        try:
            result = await delegate.generate_structured(
                request,
                response_model=SmokeReadyResponse,
            )
        except ProviderRequestError as error:
            self.observer.logical_call_completed(
                {
                    "index": logical_index,
                    "generation_role": SMOKE_ROLE,
                    "model": getattr(delegate, "model", ""),
                    "outcome": "failure",
                    "failure_category": error.category.value,
                    "response_reason": getattr(error, "response_reason", None),
                    "validation_shape": getattr(error, "validation_shape", None),
                }
            )
            raise
        except Exception:
            self.observer.logical_call_completed(
                {
                    "index": logical_index,
                    "generation_role": SMOKE_ROLE,
                    "model": getattr(delegate, "model", ""),
                    "outcome": "failure",
                    "failure_category": "invalid_response",
                }
            )
            raise
        self.observer.logical_call_completed(
            {
                "index": logical_index,
                "generation_role": SMOKE_ROLE,
                "model": getattr(delegate, "model", ""),
                "outcome": "success",
            }
        )
        if result.value.status != "READY":
            raise D5HarnessError("smoke response did not establish READY")
        return result.value

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
    max_retries_override: int | None = None,
    trace_callback: Callable[[Mapping[str, Any]], None] | None = None,
    compile_result_callback: Callable[[Any], None] | None = None,
    section_action_callback: Callable[[Mapping[str, object]], None] | None = None,
    section_action_capture_mode: Literal["off", "diagnostics", "validated_dto"] = "off",
) -> _ObservedLiveAdapter:
    """Build the canonical adapter with optional harness-scoped retry control."""
    import httpx
    from openai import AsyncOpenAI

    from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2

    _validate_project_config(project_config)
    if section_action_capture_mode not in {"off", "diagnostics", "validated_dto"}:
        raise D5StaticPreflightError("invalid section action capture mode")
    if section_action_capture_mode != "off" and section_action_callback is None:
        raise D5StaticPreflightError("section action observer is required")
    if require_thinking_control:
        request_options = _validated_thinking_control_options(request_options)
    max_retries = project_config.provider.max_retries
    if max_retries_override is not None:
        if type(max_retries_override) is not int or max_retries_override < 0:
            raise D5StaticPreflightError("max retries override must be a non-negative integer")
        max_retries = max_retries_override
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
        max_retries=max_retries,
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
        capture_logical_identity=section_action_capture_mode != "off",
    )
    session = d4.build_notebook_session(
        backend=counted,
        provider=resolved_provider,
        model=resolved_model,
        server_root=repo_root,
        credential_source="configured",
        timeout=project_config.provider.timeout_seconds,
        diagnostic_callback=observer.capture_worker_diagnostic,
        trace_callback=trace_callback,
        compile_result_callback=compile_result_callback,
        section_action_callback=section_action_callback,
        section_action_capture_mode=section_action_capture_mode,
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
    turn_ids: Sequence[str] | None = None,
    mode: str = "scientific",
    population: str = "d4",
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
        population=population,
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
    runner_kwargs: dict[str, Any] = {"turn_ids": turn_ids, "mode": mode}
    if population != "d4":
        runner_kwargs["population"] = population
    return asyncio.run(runner.run(readiness.adapter, **runner_kwargs))


async def _run_smoke_and_close(
    adapter: _ObservedLiveAdapter,
    custody: D5SmokeCustody,
) -> SmokeReadyResponse:
    """Run one smoke generation and close the existing async client."""
    try:
        return await adapter.execute_smoke(custody)
    finally:
        client = adapter.inner.session.session.compiler.dependencies.planner.backend.delegate.client
        close = getattr(client, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result


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
    """Run one non-scientific structured generation through the canonical adapter."""
    if authorization.section_action_capture_mode != "off":
        raise D5StaticPreflightError("section action capture requires binding-smoke mode")
    if artifact_root.resolve() != _authorized_artifact_root(repo_root, authorization):
        raise D5StaticPreflightError("artifact root is not authorized")
    project_config = load_project_config(repo_root)
    _validate_project_config(project_config)
    if authorization.project_config_fingerprint_sha256 != project_config.fingerprint_sha256:
        raise D5StaticPreflightError("project configuration fingerprint mismatch")
    paths = EvidencePaths(artifact_root, authorization.campaign_id)
    static = (static_checker or _default_smoke_static_checks)(repo_root, authorization, paths)
    if static.get("status") != "PASS":
        raise D5StaticPreflightError("smoke static preflight failed")
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
    try:
        readiness = prepare_readiness(
            authorization=authorization,
            project_config=project_config,
            api_key_loader=load_key,
            endpoint_get=endpoint_get,
            static_preflight=static,
            provider_factory=lambda token: build_provider(repo_root, artifact_root, token),
        )
    except D5ReadinessError as error:
        custody = D5SmokeCustody.pre_smoke_failure(
            paths,
            authorization=authorization,
            static_preflight=static,
            endpoint_calls=error.endpoint_calls,
            reason=error.reason,
        )
        terminal = custody.finish("SMOKE_NOT_READY", reason=error.reason)
        return {
            "status": "SMOKE_NOT_READY",
            "terminal": terminal,
            "readiness": _readiness_failure_result(error),
            "provider_calls": 0,
            "model_calls": 0,
        }
    if not isinstance(readiness.adapter, _ObservedLiveAdapter):
        custody = D5SmokeCustody.pre_smoke_failure(
            paths,
            authorization=authorization,
            static_preflight=static,
            endpoint_calls=len(readiness.endpoint_calls),
            reason="canonical_adapter_unavailable",
        )
        terminal = custody.finish("SMOKE_HARNESS_FAIL", reason="canonical adapter unavailable")
        return {"status": "SMOKE_HARNESS_FAIL", "terminal": terminal}
    custody = D5SmokeCustody.start(
        paths,
        authorization=authorization,
        static_preflight=static,
        readiness=readiness.projection,
        endpoint_calls=len(readiness.endpoint_calls),
    )
    custody.record_readiness(readiness.projection)
    readiness.adapter.bind_model_io(custody.record_model_io)
    readiness.adapter.bind_physical_attempt(custody.record_attempt)
    try:
        asyncio.run(_run_smoke_and_close(readiness.adapter, custody))
    except ProviderRequestError as error:
        terminal = custody.finish("SMOKE_PROVIDER_INCONCLUSIVE", reason=error.category.value)
        return {
            "status": "SMOKE_PROVIDER_INCONCLUSIVE",
            "terminal": terminal,
            "readiness": readiness.projection.as_dict(),
        }
    except D5CallCapExceeded as error:
        terminal = custody.finish("SMOKE_CONTRACT_FAIL", reason=str(error))
        return {"status": "SMOKE_CONTRACT_FAIL", "terminal": terminal}
    except D5HarnessError as error:
        terminal = custody.finish("SMOKE_HARNESS_FAIL", reason=str(error))
        return {"status": "SMOKE_HARNESS_FAIL", "terminal": terminal}
    except Exception:
        terminal = custody.finish("SMOKE_HARNESS_FAIL", reason="unclassified_failure")
        return {"status": "SMOKE_HARNESS_FAIL", "terminal": terminal}
    terminal = custody.finish("SMOKE_PASS")
    return {
        "status": "SMOKE_PASS",
        "terminal": terminal,
        "readiness": readiness.projection.as_dict(),
    }


def _binding_smoke_contract_issue(
    request: str,
    compilation: RequestCompilationResult,
) -> str | None:
    """Require the one frozen, structurally useful binding-smoke request."""
    if compilation.status.value != "EXTRACTION_COMPLETE":
        return f"request_compilation_{compilation.status.value.casefold()}"
    request_hash = hashlib.sha256(request.encode("utf-8")).hexdigest()
    if request_hash != SMOKE_BINDING_REQUEST_SHA256:
        return "binding_smoke_request_identity_mismatch"

    requirements = compilation.requirements.requirements
    if len(compilation.requirements.scopes.scopes) != 1:
        return "binding_smoke_scope_shape_invalid"
    track_fields: dict[str, set[str]] = {}
    binding_channels: dict[str, set[str]] = {}
    for requirement in requirements:
        if requirement.state.value != "SET":
            return "binding_smoke_requirement_not_explicit"
        if requirement.owner_kind.value == "track":
            track_fields.setdefault(requirement.owner_ref, set()).add(requirement.field)
        elif requirement.owner_kind.value == "binding" and requirement.field == "channel":
            binding_channels.setdefault(requirement.owner_ref, set()).add(str(requirement.value))
        elif requirement.owner_kind.value == "report":
            return "binding_smoke_unexpected_report_requirement"

    if len(track_fields) != 2 or any(
        not {"kind", "title", "width_mm"}.issubset(fields) for fields in track_fields.values()
    ):
        return "binding_smoke_track_shape_invalid"
    expected_track_refs = {"bond_index", "gamma_ray"}
    if set(binding_channels) != expected_track_refs or any(
        len(channels) != 1 for channels in binding_channels.values()
    ):
        return "binding_smoke_binding_shape_invalid"
    if {next(iter(values)) for values in binding_channels.values()} != {"BI", "GR_STGC"}:
        return "binding_smoke_channel_membership_invalid"
    return None


def _binding_smoke_asset_identities(context: object, repo_root: Path) -> list[dict[str, Any]]:
    """Return bounded identities for the local inputs declared by the demo."""
    candidates = getattr(context, "source_candidates", ())
    identities: list[dict[str, Any]] = []
    for candidate in candidates:
        path = Path(candidate.path).resolve()
        try:
            relative_path = path.relative_to(repo_root.resolve()).as_posix()
        except ValueError as error:
            raise D5HarnessError("binding-smoke source escapes repository root") from error
        if not path.is_file():
            raise D5HarnessError("binding-smoke source asset is unavailable")
        identities.append(
            {
                "asset_id": str(candidate.candidate_id),
                "relative_path": relative_path,
                "path_basename": path.name,
                "format": candidate.trusted_format or path.suffix.lstrip("."),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    if not identities:
        raise D5HarnessError("binding-smoke has no declared source asset")
    return identities


async def _close_binding_smoke_adapter(adapter: object) -> None:
    """Close the canonical OpenAI client without entering notebook projection."""
    try:
        client = adapter.inner.session.session.compiler.dependencies.planner.backend.delegate.client
    except AttributeError as error:
        raise D5HarnessError("canonical binding-smoke client is unavailable") from error
    close = getattr(client, "close", None)
    if not callable(close):
        raise D5HarnessError("canonical binding-smoke client cannot be closed")
    result = close()
    if inspect.isawaitable(result):
        await result


async def _run_binding_smoke_and_close(
    adapter: object,
    *,
    request: str,
    document: object,
    sources: Sequence[object],
) -> tuple[object | None, BaseException | None, BaseException | None]:
    """Run compilation and close the async client before the same loop exits."""
    from wellplot.agent.session import AgentSession

    result: object | None = None
    execution_error: BaseException | None = None
    cleanup_error: BaseException | None = None
    try:
        agent_session = adapter.inner.session.session
        if not isinstance(agent_session, AgentSession):
            raise D5HarnessError("canonical Code Mode session is unavailable")
        result = await agent_session.revise(
            request=request,
            document=document,
            sources=sources,
        )
    except BaseException as error:
        execution_error = error
    try:
        await _close_binding_smoke_adapter(adapter)
    except BaseException as error:
        cleanup_error = error
    return result, execution_error, cleanup_error


def _build_planner_smoke_inputs(
    repo_root: Path,
    case: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the same bounded document/source summaries consumed by plan_node."""
    from wellplot.agent.code_mode.source_loader import LogfileSourceLoader
    from wellplot.agent.code_mode.workflow import _planner_source_summary
    from wellplot.agent.inspection import AuthoringInspectionFacade
    from wellplot.agent.session import AgentSourceConfig
    from wellplot.file_revision import file_revision_token
    from wellplot.model.authoring import AuthoringDocumentSpec

    source_path = repo_root / str(case["source_path"])
    source_sha_before = _sha256_file(source_path)
    revision_before = file_revision_token(source_path)
    loaded = LogfileSourceLoader(runtime_root=repo_root).load(
        source_path,
        str(case["source_format"]),
    )
    source_sha_after = _sha256_file(source_path)
    revision_after = file_revision_token(source_path)
    if (
        source_sha_before != case["source_sha256"]
        or source_sha_after != source_sha_before
        or revision_after != revision_before
    ):
        raise D5HarnessError("planner smoke source changed during metadata inspection")

    source = AgentSourceConfig(
        candidate_id=str(case["source_key"]),
        root_id="server",
        path=str(source_path),
        labels=(str(case["source_key"]),),
        trusted_format=str(case["source_format"]),
        inspection_state="inspected",
        channels=loaded.channels,
        expected_revision_token=revision_after,
    )
    document = AuthoringDocumentSpec.model_validate(
        {
            "name": "A10 planner smoke context",
            "sections": [
                {
                    "id": "main-log",
                    "title": "Main Log",
                    "tracks": [
                        {
                            "id": "main-track",
                            "title": "Main Log",
                            "kind": "normal",
                            "width_mm": 30.0,
                        }
                    ],
                }
            ],
        }
    )
    from wellplot.agent.code_mode.enrichment import SourceCandidate

    source_candidate = SourceCandidate.model_validate(source._internal().model_dump(mode="json"))
    source_summary = _planner_source_summary({"source_candidates": [source_candidate]})
    document_summary = AuthoringInspectionFacade(document).planner_summary()
    return {
        "document": document,
        "document_summary": document_summary,
        "source_summary": source_summary,
        "source_path": source_path,
        "source_sha256_before": source_sha_before,
        "source_sha256_after_inspection": source_sha_after,
        "source_revision_before": revision_before,
        "source_revision_after_inspection": revision_after,
        "source_channel_count": len(loaded.channels),
        "numeric_sample_apis_invoked": False,
        "source_asset_identity": {
            "asset_id": str(case["source_key"]),
            "relative_path": str(case["source_path"]),
            "path_basename": source_path.name,
            "format": str(case["source_format"]),
            "size_bytes": source_path.stat().st_size,
            "sha256": source_sha_before,
        },
    }


async def _run_planner_only_and_close(
    adapter: object,
    *,
    request: str,
    document_summary: Mapping[str, Any],
    source_summary: Mapping[str, Any],
) -> tuple[object | None, BaseException | None, BaseException | None]:
    """Call only the canonical planner entrypoint, then close its canonical client."""
    from wellplot.agent.code_mode.planner import SemanticPlanner

    result: object | None = None
    execution_error: BaseException | None = None
    cleanup_error: BaseException | None = None
    try:
        session = adapter.inner.session.session
        planner = session.compiler.dependencies.planner
        if not isinstance(planner, SemanticPlanner):
            raise D5HarnessError("canonical semantic planner is unavailable")
        config = session.config
        result = await planner.plan(
            request=request,
            mode="revise",
            current_document_summary=document_summary,
            source_summary=source_summary,
            timeout_seconds=config.timeout_seconds,
            temperature=config.planner_temperature,
            max_output_tokens=config.max_output_tokens,
        )
    except BaseException as error:
        execution_error = error
    try:
        await _close_binding_smoke_adapter(adapter)
    except BaseException as error:
        cleanup_error = error
    return result, execution_error, cleanup_error


def _planner_smoke_downstream_events(
    trace_events: Sequence[Mapping[str, Any]],
    calls_by_role: Mapping[str, int],
) -> list[str]:
    """Return any observed graph/worker stage beyond the planner-only boundary."""
    forbidden_prefixes = (
        "CAPABILITY_SAFETY_",
        "ENRICHMENT_",
        "REPORT_BOUNDARY_",
        "SECTION_LEAF_",
        "REPORT_WORKER_",
        "SECTION_WORKER_",
        "RECONCILIATION_",
        "EXECUTION_",
        "PERSISTENCE_",
        "RENDER_",
        "PREVIEW_",
    )
    events = [
        str(event.get("event", ""))
        for event in trace_events
        if str(event.get("event", "")).startswith(forbidden_prefixes)
    ]
    if calls_by_role.get("report_worker", 0):
        events.append("REPORT_WORKER_CALL")
    if calls_by_role.get("section_worker", 0):
        events.append("SECTION_WORKER_CALL")
    return events


def _planner_output_reliability(
    trace_events: Sequence[Mapping[str, Any]],
    ledger: D5SmokeCallLedger,
) -> dict[str, Any]:
    """Separate one planner invocation from its initial/correction requests."""
    named_events = [str(event.get("event", "")) for event in trace_events]
    attempts = {
        attempt
        for event in trace_events
        if event.get("event") == "PLANNER_GENERATION_ENTER"
        and (attempt := event.get("attempt")) in {1, 2}
    }
    successful_attempts = {
        attempt
        for event in trace_events
        if event.get("event") == "PLANNER_GENERATION_PASS"
        and (attempt := event.get("attempt")) in {1, 2}
    }
    failed_events = [
        event for event in trace_events if event.get("event") == "PLANNER_GENERATION_FAIL"
    ]
    initial_failure = next(
        (event for event in failed_events if event.get("attempt") == 1),
        None,
    )
    initial_schema_valid: bool | None = None
    if 1 in successful_attempts:
        initial_schema_valid = True
    elif initial_failure is not None and initial_failure.get("category") == "invalid_response":
        initial_schema_valid = False

    initial_calls = int(1 in ledger.roles_by_index)
    correction_calls = int(2 in ledger.roles_by_index)
    initial_physical = ledger.attempts_by_index.get(1, 0)
    correction_physical = ledger.attempts_by_index.get(2, 0)
    transport_retries = sum(
        max(attempt_count - 1, 0) for attempt_count in ledger.attempts_by_index.values()
    )
    eventual_schema_valid = bool(successful_attempts)
    correction_entered = 2 in attempts
    correction_success = 2 in successful_attempts

    if 1 in successful_attempts:
        final_status = "VALID_FIRST_PASS"
    elif correction_success:
        final_status = "VALID_AFTER_CORRECTION"
    elif correction_entered and correction_calls == 0:
        final_status = "CORRECTION_BLOCKED_BEFORE_PROVIDER"
    elif correction_calls and any(event.get("attempt") == 2 for event in failed_events):
        final_status = "INVALID_AFTER_CORRECTION"
    elif any("REQUEST" in event for event in named_events) and not attempts:
        final_status = "PLANNER_FAILURE_BEFORE_GENERATION"
    elif any(event.get("category") != "invalid_response" for event in failed_events):
        final_status = "TRANSPORT_OR_PROVIDER_FAILURE"
    else:
        final_status = "NOT_REACHED"

    return {
        "logical_planner_invocations": int("REQUEST_COMPILATION_ENTER" in named_events),
        "initial_generation_requests": initial_calls,
        "correction_generation_requests": correction_calls,
        "initial_physical_generation_requests": initial_physical,
        "correction_physical_generation_requests": correction_physical,
        "transport_retries": transport_retries,
        "correction_path_entered": correction_entered,
        "first_pass_schema_valid": initial_schema_valid,
        "eventual_schema_valid": eventual_schema_valid,
        "correction_success": correction_success,
        "final_structured_output_status": final_status,
    }


def execute_live_planner_smoke(
    *,
    repo_root: Path,
    authorization: D5Authorization,
    artifact_root: Path,
    endpoint_get: Callable[[str, str], object] = _credential_bearing_json_get,
    api_key_loader: Callable[[], str] | None = None,
    static_checker: Callable[[Path, D5Authorization, EvidencePaths], dict[str, Any]] | None = None,
    provider_factory: Callable[..., object] | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Run one frozen benchmark case through the canonical planner-only boundary."""
    if artifact_root.resolve() != _authorized_artifact_root(repo_root, authorization):
        raise D5StaticPreflightError("artifact root is not authorized")
    project_config = load_project_config(repo_root)
    _validate_project_config(project_config)
    if authorization.project_config_fingerprint_sha256 != project_config.fingerprint_sha256:
        raise D5StaticPreflightError("project configuration fingerprint mismatch")
    paths = EvidencePaths(artifact_root, authorization.campaign_id)
    if static_checker is None:
        static, case = _default_planner_smoke_static_checks(
            repo_root,
            authorization,
            paths,
            case_id=case_id,
        )
    else:
        case = _planner_smoke_case(repo_root, authorization, case_id=case_id)
        _require_exact_planner_worktree(repo_root, authorization.expected_worktree_porcelain)
        static = static_checker(repo_root, authorization, paths)
    try:
        context = _build_planner_smoke_inputs(repo_root, case)
    except Exception as error:
        custody = D5SmokeCustody.pre_smoke_failure(
            paths,
            authorization=authorization,
            static_preflight=static,
            endpoint_calls=0,
            reason="planner_context_setup_failed",
            smoke_kind=SMOKE_PLANNER_KIND,
        )
        custody.record_unexpected_host_exception(error, last_completed_stage="STATIC_PREFLIGHT")
        terminal = custody.finish("SMOKE_HARNESS_FAIL", reason="planner_context_setup_failed")
        return {"status": "SMOKE_HARNESS_FAIL", "terminal": terminal}

    trace_events: list[Mapping[str, Any]] = []
    custody_ref: dict[str, D5SmokeCustody] = {}

    def on_trace(event: Mapping[str, Any]) -> None:
        trace_events.append(dict(event))
        custody = custody_ref.get("custody")
        if custody is not None:
            custody.record_planner_observability(event)
        if event.get("event") == "PLANNER_GENERATION_PASS":
            # Stop at the schema-validated wire DTO, before planner post-processing.
            raise _PlannerOnlyWireCaptured

    load_key = api_key_loader or (lambda: d4.load_d4_api_key(repo_root))

    def build_provider(token: str) -> object:
        if provider_factory is not None:
            return provider_factory(
                repo_root,
                artifact_root,
                token,
                max_retries_override=authorization.planner_smoke_sdk_max_retries,
                trace_callback=on_trace,
            )
        return create_live_adapter(
            repo_root=repo_root,
            artifact_root=artifact_root,
            api_key=token,
            project_config=project_config,
            request_options=authorization.thinking_control_options,
            require_thinking_control=True,
            max_retries_override=authorization.planner_smoke_sdk_max_retries,
            trace_callback=on_trace,
        )

    try:
        readiness = prepare_readiness(
            authorization=authorization,
            project_config=project_config,
            api_key_loader=load_key,
            endpoint_get=endpoint_get,
            static_preflight=static,
            provider_factory=build_provider,
        )
    except D5ReadinessError as error:
        custody = D5SmokeCustody.pre_smoke_failure(
            paths,
            authorization=authorization,
            static_preflight=static,
            endpoint_calls=error.endpoint_calls,
            reason=error.reason,
            smoke_kind=SMOKE_PLANNER_KIND,
        )
        terminal = custody.finish("SMOKE_NOT_READY", reason=error.reason)
        return {
            "status": "SMOKE_NOT_READY",
            "terminal": terminal,
            "readiness": _readiness_failure_result(error),
            "provider_calls": 0,
            "model_calls": 0,
        }

    adapter = readiness.adapter
    if not isinstance(adapter, _ObservedLiveAdapter):
        custody = D5SmokeCustody.pre_smoke_failure(
            paths,
            authorization=authorization,
            static_preflight=static,
            endpoint_calls=len(readiness.endpoint_calls),
            reason="canonical_adapter_unavailable",
            smoke_kind=SMOKE_PLANNER_KIND,
        )
        terminal = custody.finish("SMOKE_HARNESS_FAIL", reason="canonical_adapter_unavailable")
        return {"status": "SMOKE_HARNESS_FAIL", "terminal": terminal}

    custody = D5SmokeCustody.start(
        paths,
        authorization=authorization,
        static_preflight=static,
        readiness=readiness.projection,
        endpoint_calls=len(readiness.endpoint_calls),
        smoke_kind=SMOKE_PLANNER_KIND,
        source_asset_identities=(context["source_asset_identity"],),
    )
    custody_ref["custody"] = custody
    custody.state.update(
        {
            "planner_smoke_case_id": case["case_id"],
            "planner_smoke_request_sha256": case["request_sha256"],
            "planner_entrypoint": "wellplot.agent.code_mode.planner.SemanticPlanner.plan",
            "planner_result_status": "NOT_REACHED",
            "planner_result_schema_valid": False,
            "numeric_sample_apis_invoked": context["numeric_sample_apis_invoked"],
            "source_sha256_before": context["source_sha256_before"],
            "source_sha256_after_inspection": context["source_sha256_after_inspection"],
            "source_revision_before": context["source_revision_before"],
            "source_revision_after_inspection": context["source_revision_after_inspection"],
            "source_channel_count": context["source_channel_count"],
            "downstream_stage_calls": {
                "report_worker": 0,
                "section_worker": 0,
                "reconciliation": 0,
                "execution": 0,
                "persistence": 0,
                "render": 0,
                "preview": 0,
            },
        }
    )
    _atomic_json(paths.state, custody.state)
    custody.bind_binding_smoke_observability(adapter)
    for event in trace_events:
        custody.record_planner_observability(event)

    result, execution_error, cleanup_error = asyncio.run(
        _run_planner_only_and_close(
            adapter,
            request=case["request"],
            document_summary=context["document_summary"],
            source_summary=context["source_summary"],
        )
    )
    reliability = _planner_output_reliability(trace_events, custody.ledger)
    custody.state.update(reliability)
    _atomic_json(paths.state, custody.state)
    if cleanup_error is not None:
        custody.record_unexpected_host_exception(
            cleanup_error,
            last_completed_stage="CLIENT_CLOSE",
            event_name="PLANNER_SMOKE_CLEANUP_EXCEPTION",
        )
    wire_capture = next(
        (event for event in trace_events if event.get("event") == "PLANNER_GENERATION_PASS"),
        None,
    )
    if isinstance(execution_error, _PlannerOnlyWireCaptured):
        execution_error = None
    if execution_error is not None:
        custody.record_unexpected_host_exception(
            execution_error,
            last_completed_stage="PLANNER",
            event_name="PLANNER_SMOKE_EXCEPTION",
        )
        outcome = (
            "SMOKE_CONTRACT_FAIL"
            if isinstance(execution_error, ProviderRequestError)
            and execution_error.category is ProviderFailureCategory.INVALID_RESPONSE
            else "SMOKE_PROVIDER_INCONCLUSIVE"
            if isinstance(execution_error, ProviderRequestError)
            else "SMOKE_CONTRACT_FAIL"
        )
        terminal = custody.finish(outcome, reason=type(execution_error).__name__)
        return {"status": outcome, "terminal": terminal}
    if cleanup_error is not None:
        terminal = custody.finish("SMOKE_HARNESS_FAIL", reason="client_cleanup_failed")
        return {"status": "SMOKE_HARNESS_FAIL", "terminal": terminal}

    from wellplot.agent.code_mode.planner import _PlannerWirePlan

    wire_response = None if wire_capture is None else wire_capture.get("validated_response")
    if (
        result is not None
        or not isinstance(wire_response, Mapping)
        or wire_capture.get("response_schema") != "_PlannerWirePlan"
    ):
        terminal = custody.finish("SMOKE_CONTRACT_FAIL", reason="planner_wire_capture_invalid")
        return {"status": "SMOKE_CONTRACT_FAIL", "terminal": terminal}
    try:
        _PlannerWirePlan.model_validate(wire_response)
    except Exception:
        terminal = custody.finish("SMOKE_CONTRACT_FAIL", reason="planner_wire_schema_invalid")
        return {"status": "SMOKE_CONTRACT_FAIL", "terminal": terminal}
    downstream_events = _planner_smoke_downstream_events(trace_events, custody.ledger.calls_by_role)
    source_path = context["source_path"]
    source_sha_after = _sha256_file(source_path)
    from wellplot.file_revision import file_revision_token

    source_revision_after = file_revision_token(source_path)
    worktree_unchanged = _git_porcelain_raw(repo_root) == authorization.expected_worktree_porcelain
    source_unchanged = (
        source_sha_after == context["source_sha256_before"]
        and source_revision_after == context["source_revision_before"]
    )
    custody.record_planner_observability(
        {
            "event": "PLANNER_RESULT_CAPTURED",
            "response_schema": "_PlannerWirePlan",
            "schema_valid": True,
            "validated_response": wire_response,
        }
    )
    custody.state.update(
        {
            "planner_result_status": "SCHEMA_VALIDATED_WIRE_CAPTURED",
            "planner_result_schema_valid": True,
            "source_sha256_after_planner": source_sha_after,
            "source_revision_after_planner": source_revision_after,
            "worktree_allowlist_unchanged": worktree_unchanged,
            "downstream_stage_events": downstream_events,
            "downstream_stage_calls": {
                "report_worker": custody.ledger.calls_by_role.get("report_worker", 0),
                "section_worker": custody.ledger.calls_by_role.get("section_worker", 0),
                "reconciliation": 0,
                "execution": 0,
                "persistence": 0,
                "render": 0,
                "preview": 0,
            },
        }
    )
    _atomic_json(paths.state, custody.state)
    if not worktree_unchanged or not source_unchanged or downstream_events:
        terminal = custody.finish("SMOKE_CONTRACT_FAIL", reason="planner_smoke_boundary_failed")
        return {"status": "SMOKE_CONTRACT_FAIL", "terminal": terminal}
    terminal = custody.finish("SMOKE_PASS")
    return {
        "status": "SMOKE_PASS",
        "terminal": terminal,
        "readiness": readiness.projection.as_dict(),
    }


def execute_live_binding_smoke(
    *,
    repo_root: Path,
    authorization: D5Authorization,
    artifact_root: Path,
    logfile_path: Path,
    request: str = SMOKE_BINDING_REQUEST,
    endpoint_get: Callable[[str, str], object] = _credential_bearing_json_get,
    api_key_loader: Callable[[], str] | None = None,
    static_checker: Callable[[Path, D5Authorization, EvidencePaths], dict[str, Any]] | None = None,
    provider_factory: Callable[..., object] | None = None,
) -> dict[str, Any]:
    """Run the fixed engineering binding request through the canonical compile facade."""
    if artifact_root.resolve() != _authorized_artifact_root(repo_root, authorization):
        raise D5StaticPreflightError("artifact root is not authorized")
    project_config = load_project_config(repo_root)
    _validate_project_config(project_config)
    if authorization.project_config_fingerprint_sha256 != project_config.fingerprint_sha256:
        raise D5StaticPreflightError("project configuration fingerprint mismatch")
    paths = EvidencePaths(artifact_root, authorization.campaign_id)
    static = (static_checker or _default_smoke_static_checks)(repo_root, authorization, paths)
    if static.get("status") != "PASS":
        raise D5StaticPreflightError("smoke static preflight failed")
    if authorization.section_action_capture_mode != "off":
        _validate_section_capture_location(repo_root, paths.root)
        _prepare_private_campaign_root(paths.root)
    ensure_fresh_namespace(paths)

    input_custody = D5SmokeCustody(paths, authorization, state={})
    input_custody.record_binding_request(request)
    try:
        compilation = compile_request_contract(request)
    except Exception as error:
        custody = D5SmokeCustody.pre_smoke_failure(
            paths,
            authorization=authorization,
            static_preflight=static,
            endpoint_calls=0,
            reason="request_compilation_exception",
            binding_input_preflighted=True,
            smoke_kind=SMOKE_BINDING_KIND,
        )
        custody.record_unexpected_host_exception(
            error,
            last_completed_stage="REQUEST_COMPILATION_ENTER",
        )
        custody.finish("SMOKE_HARNESS_FAIL", reason="unexpected_host_exception")
        raise
    input_custody.record_binding_request_compilation(compilation)
    contract_issue = _binding_smoke_contract_issue(request, compilation)
    if contract_issue is not None:
        custody = D5SmokeCustody.pre_smoke_failure(
            paths,
            authorization=authorization,
            static_preflight=static,
            endpoint_calls=0,
            reason=contract_issue,
            binding_input_preflighted=True,
            smoke_kind=SMOKE_BINDING_KIND,
        )
        terminal = custody.finish("SMOKE_CONTRACT_FAIL", reason=contract_issue)
        return {"status": "SMOKE_CONTRACT_FAIL", "terminal": terminal}

    try:
        resolved_logfile = logfile_path.resolve()
        resolved_logfile.relative_to(repo_root.resolve())
        from wellplot.agent.direct_notebook import _load_document_context

        document_context = _load_document_context(resolved_logfile, root=repo_root)
        asset_identities = _binding_smoke_asset_identities(document_context, repo_root)
    except Exception as error:
        custody = D5SmokeCustody.pre_smoke_failure(
            paths,
            authorization=authorization,
            static_preflight=static,
            endpoint_calls=0,
            reason="binding_smoke_input_unavailable",
            binding_input_preflighted=True,
            smoke_kind=SMOKE_BINDING_KIND,
        )
        custody.record_unexpected_host_exception(
            error,
            last_completed_stage="REQUEST_COMPILATION_PASS",
        )
        custody.finish("SMOKE_HARNESS_FAIL", reason="binding_smoke_input_unavailable")
        raise

    trace_events: list[Mapping[str, Any]] = []
    section_action_events: list[Mapping[str, Any]] = []
    compile_results: list[Any] = []
    custody_ref: dict[str, D5SmokeCustody] = {}
    last_completed_stage = "READINESS"

    def on_trace(event: Mapping[str, Any]) -> None:
        nonlocal last_completed_stage
        trace_events.append(dict(event))
        name = str(event.get("event", ""))
        if name.endswith("_PASS") or name.endswith("_COMPLETED"):
            last_completed_stage = name
        active_custody = custody_ref.get("custody")
        if active_custody is not None:
            active_custody.record_planner_observability(event)

    def on_compile_result(result: CodeModeCompileResult) -> None:
        compile_results.append(result)
        active_custody = custody_ref.get("custody")
        if active_custody is not None:
            active_custody.record_compile_result(result)

    def on_section_action(event: Mapping[str, object]) -> None:
        active_custody = custody_ref.get("custody")
        if authorization.section_action_capture_mode == "off":
            section_action_events.append(dict(event))
        elif active_custody is None:
            raise D5HarnessError("section action custody is not active")
        if active_custody is not None:
            active_custody.record_section_action(event)

    load_key = api_key_loader or (lambda: d4.load_d4_api_key(repo_root))

    def build_provider(token: str) -> object:
        if provider_factory is not None:
            extra = (
                {"section_action_capture_mode": authorization.section_action_capture_mode}
                if authorization.section_action_capture_mode != "off"
                else {}
            )
            return provider_factory(
                repo_root,
                artifact_root,
                token,
                trace_callback=on_trace,
                compile_result_callback=on_compile_result,
                section_action_callback=on_section_action,
                **extra,
            )
        return create_live_adapter(
            repo_root=repo_root,
            artifact_root=artifact_root,
            api_key=token,
            project_config=project_config,
            request_options=authorization.thinking_control_options,
            require_thinking_control=True,
            trace_callback=on_trace,
            compile_result_callback=on_compile_result,
            section_action_callback=on_section_action,
            section_action_capture_mode=authorization.section_action_capture_mode,
        )

    try:
        readiness = prepare_readiness(
            authorization=authorization,
            project_config=project_config,
            api_key_loader=load_key,
            endpoint_get=endpoint_get,
            static_preflight=static,
            provider_factory=build_provider,
        )
    except D5ReadinessError as error:
        custody = D5SmokeCustody.pre_smoke_failure(
            paths,
            authorization=authorization,
            static_preflight=static,
            endpoint_calls=error.endpoint_calls,
            reason=error.reason,
            binding_input_preflighted=True,
            smoke_kind=SMOKE_BINDING_KIND,
        )
        terminal = custody.finish("SMOKE_NOT_READY", reason=error.reason)
        return {
            "status": "SMOKE_NOT_READY",
            "terminal": terminal,
            "readiness": _readiness_failure_result(error),
            "provider_calls": 0,
            "model_calls": 0,
        }

    adapter = readiness.adapter
    if not isinstance(adapter, _ObservedLiveAdapter):
        custody = D5SmokeCustody.pre_smoke_failure(
            paths,
            authorization=authorization,
            static_preflight=static,
            endpoint_calls=len(readiness.endpoint_calls),
            reason="canonical_adapter_unavailable",
            binding_input_preflighted=True,
            smoke_kind=SMOKE_BINDING_KIND,
        )
        terminal = custody.finish("SMOKE_HARNESS_FAIL", reason="canonical_adapter_unavailable")
        return {"status": "SMOKE_HARNESS_FAIL", "terminal": terminal}

    if authorization.section_action_capture_mode != "off":
        try:
            dependencies = adapter.inner.session.session.compiler.dependencies
            configured_mode = dependencies.section_compiler.action_capture_mode
            correlation_enabled = dependencies.planner.backend.capture_logical_identity
        except AttributeError:
            configured_mode = None
            correlation_enabled = False
        if configured_mode != authorization.section_action_capture_mode or not correlation_enabled:
            custody = D5SmokeCustody.pre_smoke_failure(
                paths,
                authorization=authorization,
                static_preflight=static,
                endpoint_calls=len(readiness.endpoint_calls),
                reason="section_action_capture_unavailable",
                binding_input_preflighted=True,
                smoke_kind=SMOKE_BINDING_KIND,
            )
            terminal = custody.finish(
                "SMOKE_NOT_READY", reason="section_action_capture_unavailable"
            )
            return {"status": "SMOKE_NOT_READY", "terminal": terminal}

    custody = D5SmokeCustody.start(
        paths,
        authorization=authorization,
        static_preflight=static,
        readiness=readiness.projection,
        endpoint_calls=len(readiness.endpoint_calls),
        smoke_kind=SMOKE_BINDING_KIND,
        source_asset_identities=asset_identities,
        binding_input_preflighted=True,
    )
    custody_ref["custody"] = custody
    custody.bind_binding_smoke_observability(adapter)
    for event in trace_events:
        custody.record_planner_observability(event)
    for result in compile_results:
        custody.record_compile_result(result)
    for event in section_action_events:
        custody.record_section_action(event)

    try:
        result, execution_error, cleanup_error = asyncio.run(
            _run_binding_smoke_and_close(
                adapter,
                request=request,
                document=document_context.document,
                sources=document_context.source_candidates,
            )
        )
    except BaseException as error:
        execution_error = error
        cleanup_error = None
        result = None

    if cleanup_error is not None:
        custody.record_unexpected_host_exception(
            cleanup_error,
            last_completed_stage="CLIENT_CLOSE",
            event_name="BINDING_SMOKE_CLEANUP_EXCEPTION",
        )

    if isinstance(execution_error, asyncio.CancelledError):
        raise execution_error
    if isinstance(execution_error, D5CallCapExceeded):
        terminal = custody.finish("SMOKE_CONTRACT_FAIL", reason="binding_call_cap_exceeded")
        return {"status": "SMOKE_CONTRACT_FAIL", "terminal": terminal}
    if execution_error is not None:
        custody.record_unexpected_host_exception(
            execution_error,
            last_completed_stage=last_completed_stage,
        )
        custody.finish("SMOKE_HARNESS_FAIL", reason="unexpected_host_exception")
        raise execution_error

    if not compile_results:
        terminal = custody.finish("SMOKE_HARNESS_FAIL", reason="compile_result_not_observed")
        return {"status": "SMOKE_HARNESS_FAIL", "terminal": terminal}
    compile_result = compile_results[-1]
    if not result.success or not compile_result.success:
        if any(item.code == "worker_evidence_integrity_failure" for item in result.diagnostics):
            terminal = custody.finish(
                "SMOKE_HARNESS_FAIL", reason="section_action_evidence_integrity"
            )
            return {"status": "SMOKE_HARNESS_FAIL", "terminal": terminal}
        provider_failure = any(item.stage == "provider" for item in result.diagnostics)
        outcome = "SMOKE_PROVIDER_INCONCLUSIVE" if provider_failure else "SMOKE_CONTRACT_FAIL"
        reason = "provider_compile_failure" if provider_failure else "canonical_compile_rejected"
        terminal = custody.finish(outcome, reason=reason)
        return {"status": outcome, "terminal": terminal}
    section_workers = [worker for worker in result.workers if worker.kind == "section"]
    successful_lowering = bool(section_workers) and all(
        worker.success and worker.stage_evidence.semantic_lowering == "PASS"
        for worker in section_workers
    )
    if not successful_lowering or any(worker.kind == "report" for worker in result.workers):
        terminal = custody.finish("SMOKE_CONTRACT_FAIL", reason="binding_compile_stage_missing")
        return {"status": "SMOKE_CONTRACT_FAIL", "terminal": terminal}
    terminal = custody.finish("SMOKE_PASS")
    return {
        "status": "SMOKE_PASS",
        "terminal": terminal,
        "readiness": readiness.projection.as_dict(),
    }


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
    if _is_correction_scope_violation(actual):
        return None
    if actual.get("observed_safe_rejection") is True and grade.get("status") == "PASS":
        return None
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


_STRUCTURED_OUTPUT_FAILURE_CATEGORIES = frozenset(
    {"configuration", "provider_rejected", "invalid_response"}
)
_PROVIDER_RUNTIME_FAILURE_CATEGORIES = frozenset(
    {"transport", "timeout", "rate_limit", "authentication"}
)


def _classify_logical_call_failure(
    calls: Sequence[Mapping[str, Any]],
) -> tuple[str, str] | None:
    """Classify the latest unrecovered logical-call failure."""
    if not calls or calls[-1].get("outcome") in {"completed", "success"}:
        return None
    category = calls[-1].get("failure_category")
    if category in _STRUCTURED_OUTPUT_FAILURE_CATEGORIES:
        return "PROVIDER_BOUNDARY / STRUCTURED_OUTPUT", str(category)
    if category in _PROVIDER_RUNTIME_FAILURE_CATEGORIES:
        return "PROVIDER_OR_TRANSPORT_RUNTIME", str(category)
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
    if _is_correction_scope_violation(actual):
        return "CORRECTION_PRESERVATION"
    if actual.get("observed_safe_rejection") is True and grade.get("status") == "PASS":
        return "NONE"
    declared = actual.get("first_divergence")
    if isinstance(declared, str) and declared in D5I_FIRST_DIVERGENCES:
        return declared
    if actual.get("harness_failure") is True:
        return "HARNESS"
    if actual.get("normalization_status") == "FAIL":
        return "HOST_EXECUTION"
    if actual.get("lowering_status") == "FAIL":
        return "HOST_EXECUTION"
    if str(actual.get("apply_status")) in {
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


def _is_correction_scope_violation(actual: Mapping[str, Any]) -> bool:
    """Recognize a bounded rejected correction without calling it host failure."""
    return (
        actual.get("worker_diagnostic_code") == "worker_correction_scope_violation"
        and actual.get("normalization_status") == "PASS"
        and actual.get("worker_obligation_status") == "FAIL"
        and actual.get("lowering_status") == "NOT_REACHED"
        and actual.get("apply_status") == "compile_failed"
    )


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
    population_size: int,
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
    if decision == "PASS" and len(rows) == population_size:
        return "PASS"
    if any(row.get("scientific_terminal") == "FAIL / CONTRACT_OR_INPUT" for row in rows):
        return "FAIL / CONTRACT_OR_INPUT"
    return "FAIL / RESIDUAL_SEMANTIC"


def _grade_turn(actual: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    """Dispatch the final held-out contract without changing D4 grading."""
    if expected.get("grader") == "d5_c02_contract":
        return grade_c02_artifact(actual, expected["contract"])
    return d4.grade_turn(actual, expected)


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
        turn_ids: Sequence[str] | None = None,
        mode: str = "scientific",
        population: str = "d4",
    ) -> dict[str, Any]:
        """Run selected frozen turns through the shared canonical adapter."""
        if self._started or self._finished:
            raise D5HarnessError("campaign cannot be resumed or invoked twice")
        if mode not in {"smoke", "scientific"}:
            raise D5HarnessError("unknown campaign mode")
        if population == "d4":
            cases = d4.load_cases(self.repo_root)
            gold_cases = {item["turn_id"]: item for item in d4.load_gold(self.repo_root)["cases"]}
            population_ids = FROZEN_TURN_IDS
        elif population == "final":
            cases, gold_payload = final_population.load_final_population(self.repo_root)
            gold_cases = {item["turn_id"]: item for item in gold_payload["cases"]}
            population_ids = final_population.FINAL_TURN_IDS
        else:
            raise D5StaticPreflightError("unknown population")
        selected_ids = tuple(str(turn_id) for turn_id in (turn_ids or population_ids))
        if not selected_ids or len(set(selected_ids)) != len(selected_ids):
            raise D5StaticPreflightError("selected turn population is invalid")
        if any(turn_id not in population_ids for turn_id in selected_ids):
            raise D5StaticPreflightError("selected turn is outside the frozen population")
        if selected_ids != tuple(turn_id for turn_id in population_ids if turn_id in selected_ids):
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
            if callable(getattr(adapter, "bind_call_aborted", None)):
                adapter.bind_call_aborted(custody.record_call_aborted)
            if callable(getattr(adapter, "bind_physical_attempt", None)):
                adapter.bind_physical_attempt(custody.record_physical_attempt)
            if callable(getattr(adapter, "bind_model_io", None)):
                adapter.bind_model_io(custody.record_model_io)
            if callable(getattr(adapter, "bind_worker_diagnostic", None)):
                adapter.bind_worker_diagnostic(custody.record_worker_diagnostic)
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
                expected = gold_cases[case["turn_id"]]
                cursor = int(getattr(adapter, "logical_call_count", 0))
                physical_cursor = custody.ledger.physical_attempts
                started = time.perf_counter()
                actual = await execute_turn(case, expected)
                observed_failure = _classify_logical_call_failure(custody.ledger.calls[cursor:])
                grade = (
                    {"status": "INCONCLUSIVE", "errors": [], "verifier_requirements": []}
                    if observed_failure is not None
                    else _grade_turn(dict(actual), expected)
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
                decision, attribution = (
                    "INCONCLUSIVE",
                    next(
                        row["failure_category"]
                        for row in rows
                        if row.get("failure_category") in _HOST_FAILURE_CATEGORIES
                    ),
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
            custody.record_campaign_exception(
                error,
                active_turn=custody._active_turn_id,
                completed_worker_outcomes=rows,
            )
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
                population_size=len(selected_ids),
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
    population: str = "d4",
) -> dict[str, Any]:
    """Run static D5-4 checks without credentials, endpoints, or providers."""
    project_config = load_project_config(repo_root)
    _validate_project_config(project_config)
    if authorization.project_config_fingerprint_sha256 != project_config.fingerprint_sha256:
        raise D5StaticPreflightError("project configuration fingerprint mismatch")
    if population == "final":
        final_population.load_final_population(repo_root)
    elif population != "d4":
        raise D5StaticPreflightError("unknown population")
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
        "population": {
            "turns": len(FROZEN_TURN_IDS)
            if population == "d4"
            else len(final_population.FINAL_TURN_IDS),
            "turn_ids": list(
                FROZEN_TURN_IDS if population == "d4" else final_population.FINAL_TURN_IDS
            ),
        },
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
    modes.add_argument("--execute-planner-smoke", action="store_true")
    modes.add_argument("--execute-live", action="store_true")
    parser.add_argument("--population", choices=("d4", "final"), default="d4")
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--authorization-json", type=Path, required=True)
    parser.add_argument(
        "--planner-case-id",
        help="select a case pinned by the planner-only authorization",
    )
    args = parser.parse_args()
    if args.planner_case_id is not None and not args.execute_planner_smoke:
        parser.error("--planner-case-id requires --execute-planner-smoke")
    repo_root = args.repo_root.resolve()
    authorization = _load_authorization(args.authorization_json.resolve())
    artifact_root = (
        args.artifact_root.resolve()
        if args.artifact_root is not None
        else (repo_root / authorization.artifact_root).resolve()
    )
    paths = EvidencePaths(artifact_root, authorization.campaign_id)
    if args.provider_free_preflight:
        result = provider_free_preflight(
            repo_root,
            authorization,
            paths,
            population=args.population,
        )
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
    elif args.execute_planner_smoke:
        result = execute_live_planner_smoke(
            repo_root=repo_root,
            authorization=authorization,
            artifact_root=artifact_root,
            case_id=args.planner_case_id,
        )
    else:
        try:
            result = execute_live_campaign(
                repo_root=repo_root,
                authorization=authorization,
                artifact_root=artifact_root,
                population=args.population,
            )
        except D5ReadinessError as error:
            print(json.dumps(_readiness_failure_result(error), indent=2, sort_keys=True))
            return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
