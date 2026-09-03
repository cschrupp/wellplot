###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Safe, per-run JSONL tracing for graph-backed agentic authoring."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

TRACE_VERSION = 1
_MAX_PAYLOAD_CHARACTERS = 64_000
_MAX_RESPONSE_EXCERPT_CHARACTERS = 16_384
_RESPONSE_EXCERPT_HEAD_CHARACTERS = 12_288
_SENSITIVE_KEY_PARTS = ("api_key", "authorization", "password", "secret", "token")
_SENSITIVE_TOKEN_PATTERN = re.compile(r"(?i)\b(?:sk|nvapi|hf|ghp)[-_][A-Za-z0-9_-]{8,}\b")


class AgentTraceEvent(BaseModel):
    """One safe, durable event emitted during a graph-authoring run."""

    model_config = ConfigDict(extra="forbid")

    trace_version: int = TRACE_VERSION
    run_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    timestamp: str = Field(min_length=1)
    event: str = Field(min_length=1)
    status: str = Field(min_length=1)
    stage: str | None = None
    target_id: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    details: dict[str, Any] = Field(default_factory=dict)
    payload: Any | None = None


@dataclass(frozen=True)
class _StageContext:
    """Current graph stage carried safely across asynchronous provider calls."""

    trace: AgentRunTrace
    stage: str
    target_id: str | None


_ACTIVE_TRACE: ContextVar[AgentRunTrace | None] = ContextVar(
    "wellplot_active_agent_trace",
    default=None,
)
_ACTIVE_STAGE: ContextVar[_StageContext | None] = ContextVar(
    "wellplot_active_agent_trace_stage",
    default=None,
)


def _sanitize_text(value: str) -> str:
    """Redact common credential forms while retaining useful diagnostics."""
    normalized = _SENSITIVE_TOKEN_PATTERN.sub("[REDACTED]", value)
    return re.sub(r"(?i)\bbearer\s+\S+", "Bearer [REDACTED]", normalized)


def _sanitize_value(value: object, *, key: str | None = None) -> object:
    """Return JSON-safe trace content without credentials or arbitrary objects."""
    if key is not None and any(part in key.lower() for part in _SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(item_key): _sanitize_value(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list | tuple):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    return _sanitize_text(repr(value))


def _bounded_payload(value: object) -> object:
    """Bound one trace payload while preserving a stable content fingerprint."""
    sanitized = _sanitize_value(value)
    encoded = json.dumps(sanitized, sort_keys=True, ensure_ascii=True, default=str)
    if len(encoded) <= _MAX_PAYLOAD_CHARACTERS:
        return sanitized
    return {
        "truncated": True,
        "original_characters": len(encoded),
        "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "excerpt": encoded[:_MAX_PAYLOAD_CHARACTERS],
    }


def assistant_response_trace_payload(response_text: str) -> dict[str, object]:
    """Return a redacted, bounded response record suitable for a JSONL trace.

    The trace intentionally does not store prompts. A provider can nevertheless
    return unstructured prose instead of its required tool call, so preserving a
    bounded response excerpt is necessary to diagnose that behavior. The record
    keeps both ends of verbose responses and a digest of the complete redacted
    content without allowing one provider response to grow the trace unbounded.
    """
    sanitized = _sanitize_text(response_text)
    digest = hashlib.sha256(sanitized.encode("utf-8")).hexdigest()
    if len(sanitized) <= _MAX_RESPONSE_EXCERPT_CHARACTERS:
        excerpt = sanitized
        truncated = False
    else:
        tail_characters = _MAX_RESPONSE_EXCERPT_CHARACTERS - _RESPONSE_EXCERPT_HEAD_CHARACTERS
        excerpt = (
            f"{sanitized[:_RESPONSE_EXCERPT_HEAD_CHARACTERS]}"
            "\n\n[... assistant response excerpt truncated ...]\n\n"
            f"{sanitized[-tail_characters:]}"
        )
        truncated = True
    return {
        "original_characters": len(response_text),
        "sha256": digest,
        "truncated": truncated,
        "excerpt": excerpt,
    }


class AgentRunTrace:
    """Append safe, ordered events to one graph-authoring JSONL sidecar."""

    def __init__(self, *, path: Path, run_id: str) -> None:
        """Initialize one trace writer bound to a unique JSONL path."""
        self.path = path
        self.run_id = run_id
        self._sequence = 0
        self._lock = threading.Lock()

    @classmethod
    def create(cls, *, logfile_path: str | Path, mode: str) -> AgentRunTrace:
        """Create one unique trace beside the target draft and record its start."""
        logfile = Path(logfile_path).resolve()
        run_id = uuid.uuid4().hex
        trace_path = (
            logfile.parent / ".wellplot" / "agentic-runs" / f"{logfile.stem}-{run_id}.jsonl"
        )
        trace = cls(path=trace_path, run_id=run_id)
        trace.record(
            "run_started",
            status="started",
            details={"mode": mode, "logfile": str(logfile)},
        )
        return trace

    @property
    def event_count(self) -> int:
        """Return the number of events durably written for this run."""
        return self._sequence

    def record(
        self,
        event: str,
        *,
        status: str = "info",
        stage: str | None = None,
        target_id: str | None = None,
        duration_ms: int | None = None,
        details: Mapping[str, Any] | None = None,
        payload: object | None = None,
    ) -> AgentTraceEvent:
        """Append and flush one event so stalled runs remain inspectable."""
        stage_context = _ACTIVE_STAGE.get()
        if stage is None and stage_context is not None and stage_context.trace is self:
            stage = stage_context.stage
            target_id = target_id if target_id is not None else stage_context.target_id
        with self._lock:
            self._sequence += 1
            event_model = AgentTraceEvent(
                run_id=self.run_id,
                sequence=self._sequence,
                timestamp=datetime.now(UTC).isoformat(),
                event=event,
                status=status,
                stage=stage,
                target_id=target_id,
                duration_ms=duration_ms,
                details=_bounded_payload(dict(details or {})),
                payload=_bounded_payload(payload) if payload is not None else None,
            )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(event_model.model_dump_json() + "\n")
                handle.flush()
        return event_model

    @contextmanager
    def stage(self, stage: str, *, target_id: str | None = None) -> Iterator[None]:
        """Record one graph stage and carry its identity into provider calls."""
        started = perf_counter()
        token = _ACTIVE_STAGE.set(_StageContext(self, stage, target_id))
        self.record("stage_started", status="started", stage=stage, target_id=target_id)
        try:
            yield
        except Exception as exc:
            status = str(getattr(exc, "status", "failed"))
            self.record(
                "stage_finished",
                status=status,
                stage=stage,
                target_id=target_id,
                duration_ms=round((perf_counter() - started) * 1000),
                details={"error": str(exc)},
            )
            raise
        else:
            self.record(
                "stage_finished",
                status="succeeded",
                stage=stage,
                target_id=target_id,
                duration_ms=round((perf_counter() - started) * 1000),
            )
        finally:
            _ACTIVE_STAGE.reset(token)


@contextmanager
def bind_agent_trace(trace: AgentRunTrace) -> Iterator[AgentRunTrace]:
    """Bind one run trace to the active graph task and its child provider calls."""
    token = _ACTIVE_TRACE.set(trace)
    try:
        yield trace
    finally:
        _ACTIVE_TRACE.reset(token)


def current_agent_trace() -> AgentRunTrace | None:
    """Return the per-run trace bound to the current asynchronous task, if any."""
    return _ACTIVE_TRACE.get()


def read_agent_trace(path: str | Path) -> list[AgentTraceEvent]:
    """Read one JSONL trace for notebook inspection and deterministic tests."""
    trace_path = Path(path)
    return [
        AgentTraceEvent.model_validate_json(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


__all__ = [
    "AgentRunTrace",
    "AgentTraceEvent",
    "assistant_response_trace_payload",
    "bind_agent_trace",
    "current_agent_trace",
    "read_agent_trace",
]
