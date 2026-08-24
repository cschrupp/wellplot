"""Opt-in, redacted telemetry for stable MCP tool dispatch."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

TELEMETRY_PATH_ENV = "WELLPLOT_MCP_TELEMETRY_PATH"


def new_request_id() -> str:
    """Return a correlation id for one stable MCP dispatch."""
    return uuid.uuid4().hex


def dispatch_started() -> float:
    """Capture a monotonic start timestamp for one dispatch."""
    return time.perf_counter()


def _json_default(value: object) -> object:
    """Represent non-JSON values safely while measuring payload size."""
    if isinstance(value, bytes):
        return {"binary_bytes": len(value)}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    if is_dataclass(value):
        return asdict(value)
    return f"<{type(value).__name__}>"


def _serialized_size(value: object) -> int | None:
    """Return serialized payload bytes without retaining the payload itself."""
    try:
        encoded = json.dumps(
            value,
            default=_json_default,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return len(encoded)


def _argument_hash(arguments: object) -> str | None:
    """Return a stable hash of arguments without writing their values."""
    try:
        encoded = json.dumps(
            arguments,
            default=_json_default,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(encoded).hexdigest()


def _draft_revision(arguments: object, root: str | Path) -> str | None:
    """Return a content revision for a logfile argument, when available."""
    if not isinstance(arguments, dict):
        return None
    logfile_value = arguments.get("logfile_path")
    if not isinstance(logfile_value, str) or not logfile_value:
        return None
    root_path = Path(root).resolve()
    candidate = Path(logfile_value).expanduser()
    candidate = (
        (root_path / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    )
    try:
        candidate.relative_to(root_path)
        if not candidate.is_file():
            return None
        return hashlib.sha256(candidate.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return None


def _telemetry_path(root: str | Path) -> Path | None:
    """Resolve the opt-in telemetry destination under the server root only."""
    configured = os.getenv(TELEMETRY_PATH_ENV)
    if not configured:
        return None
    root_path = Path(root).resolve()
    candidate = Path(configured)
    if not candidate.is_absolute():
        candidate = root_path / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root_path)
    except (OSError, ValueError):
        return None
    return resolved


def emit_dispatch_event(
    *,
    root: str | Path,
    request_id: str,
    tool_name: str,
    arguments: object,
    started_at: float,
    result: object | None = None,
    error: Exception | None = None,
) -> None:
    """Append one metadata-only stable-dispatch event when telemetry is enabled.

    Telemetry failures must never affect tool execution. Payload values are used
    only to calculate byte sizes and are never written to the event file.
    """
    try:
        path = _telemetry_path(root)
        if path is None:
            return
        changed = result.get("changed") if isinstance(result, dict) else None
        result_revision = result.get("revision") if isinstance(result, dict) else None
        draft_revision = (
            result_revision
            if isinstance(result_revision, str)
            else _draft_revision(arguments, root)
        )
        argument_mapping = arguments if isinstance(arguments, dict) else {}
        event: dict[str, Any] = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "request_id": request_id,
            "tool_name": tool_name,
            "argument_bytes": _serialized_size(arguments),
            "result_bytes": _serialized_size(result) if error is None else None,
            "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 3),
            "outcome": "error" if error is not None else "success",
            "changed": changed if isinstance(changed, bool) else None,
            "exception_type": type(error).__name__ if error is not None else None,
            "argument_sha256": _argument_hash(arguments),
            "draft_revision": draft_revision,
            "operation": argument_mapping.get("operation"),
            "object_kind": argument_mapping.get("object_kind"),
            "section_id": argument_mapping.get("section_id"),
            "track_id": argument_mapping.get("track_id"),
            "binding_id": argument_mapping.get("binding_id"),
            "detail": argument_mapping.get("detail"),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
    except Exception:  # noqa: BLE001 - observability must never alter tool behavior.
        return
