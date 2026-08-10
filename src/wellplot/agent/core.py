###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
###############################################################################

"""Public host-side agent API for LLM-driven wellplot authoring."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from ..authoring import (
    authoring_document_from_mapping,
    authoring_document_to_yaml,
    load_authoring_document,
)
from ..authoring_context import (
    AuthoringChannelInput,
    AuthoringContextIssue,
    AuthoringContextSnapshot,
    build_authoring_context_snapshot,
)
from ..authoring_defaults import generic_authoring_defaults
from ..authoring_executor import (
    AuthoringExecutionResult,
    AuthoringExecutionStatus,
    execute_authoring_plan,
)
from ..authoring_reconciler import (
    AuthoringOperationPhase,
    AuthoringReconciliationPlan,
    reconcile_authoring,
)
from ..authoring_service import AuthoringService
from ..mcp.packet_blueprints import packet_blueprint_spec
from ..model.authoring import AuthoringDocumentSpec
from ..model.intent import AuthoringDocumentIntent
from .compilation import (
    AuthoringIntentSubmission,
    build_request_manifest,
    validate_intent_coverage,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from contextlib import AbstractAsyncContextManager

DEFAULT_ALLOWED_MCP_TOOLS = (
    "create_logfile_draft",
    "summarize_logfile_draft",
    "set_section_data_source",
    "set_depth_axis",
    "set_matplotlib_style",
    "validate_logfile",
    "inspect_logfile",
    "inspect_authoring_objects",
    "inspect_data_source",
    "check_channel_availability",
    "inspect_header_archetypes",
    "inspect_packet_blueprints",
    "replicate_section_structure",
    "update_section",
    "set_page_layout",
    "set_section_view",
    "apply_header_archetype",
    "inspect_heading_slots",
    "parse_key_value_text",
    "preview_header_mapping",
    "apply_header_values",
    "inspect_style_presets",
    "apply_style_preset",
    "inspect_authoring_vocab",
    "add_track",
    "update_track",
    "add_annotation_object",
    "update_annotation_object",
    "remove_annotation_object",
    "inspect_track_bindings",
    "set_track_scales",
    "remove_track",
    "bind_curve",
    "add_curve_fill",
    "bind_raster",
    "update_curve_binding",
    "update_raster_binding",
    "remove_curve_binding",
    "remove_raster_binding",
    "move_track",
    "set_heading_content",
    "set_remarks_content",
    "summarize_logfile_changes",
)

_PHASE_READ_ONLY_TOOLS = frozenset(
    {
        "summarize_logfile_draft",
        "inspect_logfile",
        "inspect_authoring_objects",
        "inspect_data_source",
        "check_channel_availability",
        "inspect_header_archetypes",
        "inspect_packet_blueprints",
        "inspect_heading_slots",
        "inspect_style_presets",
        "inspect_authoring_vocab",
        "inspect_track_bindings",
    }
)

_PHASE_TOOL_FAMILY_NAMES = {
    "sections": frozenset(
        {
            "set_section_data_source",
            "replicate_section_structure",
            "update_section",
        }
    ),
    "tracks": frozenset(
        {
            "add_track",
            "update_track",
            "remove_track",
            "move_track",
            "set_depth_axis",
        }
    ),
    "layout": frozenset({"set_page_layout", "set_section_view", "set_depth_axis"}),
    "bindings": frozenset(
        {
            "bind_curve",
            "bind_raster",
            "update_curve_binding",
            "update_raster_binding",
            "remove_curve_binding",
            "remove_raster_binding",
            "clear_track_bindings",
        }
    ),
    "fills": frozenset({"add_curve_fill", "remove_curve_fill"}),
    "scale": frozenset({"set_track_scales", "update_curve_binding", "update_raster_binding"}),
    "styles": frozenset(
        {
            "set_matplotlib_style",
            "apply_style_preset",
            "update_track",
            "update_curve_binding",
            "update_raster_binding",
        }
    ),
    "presets": frozenset({"inspect_style_presets", "apply_style_preset"}),
    "heading": frozenset(
        {
            "parse_key_value_text",
            "preview_header_mapping",
            "apply_header_values",
            "set_heading_content",
        }
    ),
    "remarks": frozenset({"set_remarks_content"}),
    "annotations": frozenset(
        {
            "add_annotation_object",
            "update_annotation_object",
            "remove_annotation_object",
        }
    ),
}


def _phase_allowed_tool_names(phase: AuthoringPlanPhase) -> set[str]:
    """Return the MCP tools allowed during one authoring phase."""
    names = set(_PHASE_READ_ONLY_TOOLS)
    for family in phase.tool_families:
        names.update(_PHASE_TOOL_FAMILY_NAMES.get(family, ()))
    return names


def _tool_payload_error_text(payload: dict[str, object]) -> str | None:
    """Extract one provider-facing MCP error from a normalized tool payload."""
    if not bool(payload.get("is_error")):
        return None
    error = payload.get("error")
    if isinstance(error, str) and error.strip():
        return error.strip()
    messages: list[str] = []
    content = payload.get("content", [])
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                messages.append(text.strip())
    return "\n".join(messages) if messages else "MCP returned an error result."


@dataclass(frozen=True)
class AuthoringRequest:
    """High-level natural-language authoring request."""

    goal: str
    output_logfile: str
    example_id: str | None = None
    source_logfile_path: str | None = None
    max_rounds: int = 12
    desired_state: AuthoringDocumentIntent | Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        """Require exactly one draft seed for the initial authoring pass."""
        if (self.example_id is None) == (self.source_logfile_path is None):
            raise ValueError(
                "Provide exactly one of example_id or source_logfile_path "
                "when creating an AuthoringRequest."
            )


@dataclass(frozen=True)
class RevisionRequest:
    """High-level natural-language revision request for one existing draft."""

    feedback: str
    logfile_path: str
    max_rounds: int = 12
    desired_state: AuthoringDocumentIntent | Mapping[str, object] | None = None


@dataclass(frozen=True)
class AuthoringToolCall:
    """One provider-issued tool call replayed through wellplot MCP."""

    round: int
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class FunctionToolDefinition:
    """Generic function-tool definition passed to one provider adapter."""

    name: str
    description: str
    parameters: dict[str, object]


@dataclass(frozen=True)
class ProviderRunResult:
    """Normalized provider loop result returned to the orchestration core."""

    final_text: str
    tool_trace: tuple[AuthoringToolCall, ...]
    report_facts: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthoringPlanPhase:
    """One planned authoring phase for a structured packet or draft workflow."""

    id: str
    kind: str
    summary: str
    instructions: str
    tool_families: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    success_checks: tuple[str, ...] = ()
    success_check_specs: tuple[dict[str, object], ...] = ()
    max_rounds: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthoringRunState:
    """Structured per-run state captured during one authoring workflow."""

    objectives: tuple[str, ...] = ()
    completed_objectives: tuple[str, ...] = ()
    blocked_objectives: tuple[str, ...] = ()
    discovered_sections: tuple[str, ...] = ()
    discovered_tracks_by_section: dict[str, tuple[str, ...]] = field(default_factory=dict)
    discovered_binding_ids_by_track: dict[str, tuple[str, ...]] = field(default_factory=dict)
    available_channels_by_section: dict[str, tuple[str, ...]] = field(default_factory=dict)
    last_verification: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthoringPlanResult:
    """Structured planning output for one authoring request."""

    mode: str
    packet_blueprint_id: str | None
    phases: tuple[AuthoringPlanPhase, ...]
    blocked: bool
    blocked_reasons: tuple[str, ...] = ()
    run_state: AuthoringRunState = field(default_factory=AuthoringRunState)
    desired_state: AuthoringDocumentIntent | None = None
    reconciliation_plan: AuthoringReconciliationPlan | None = None


@dataclass(frozen=True)
class ExecutedAuthoringPhase:
    """Recorded execution outcome for one planned authoring phase."""

    id: str
    kind: str
    summary: str
    status: str
    tool_trace: tuple[AuthoringToolCall, ...]
    verification: dict[str, object]
    blocked_reasons: tuple[str, ...] = ()
    preview_kind: str | None = None
    preview_target: str | None = None
    preview_png: bytes | None = field(default=None, repr=False)

    def preview_bytes(self) -> bytes | None:
        """Return the optional captured phase preview bytes."""
        return self.preview_png


@dataclass(frozen=True)
class AuthoringUserReport:
    """Concise deterministic operator report for one authoring run."""

    done: tuple[str, ...] = ()
    could_not_do: tuple[str, ...] = ()
    why_not: tuple[str, ...] = ()
    warnings_or_errors: tuple[str, ...] = ()
    request_inconsistencies: tuple[str, ...] = ()
    next_help: tuple[str, ...] = ()

    def sections(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """Return the non-empty report sections in display order."""
        return tuple(
            (label, items)
            for label, items in (
                ("Done", self.done),
                ("Could not do", self.could_not_do),
                ("Why not", self.why_not),
                ("Warnings/errors", self.warnings_or_errors),
                ("Request inconsistencies", self.request_inconsistencies),
                ("Next help", self.next_help),
            )
            if items
        )

    def to_text(self) -> str:
        """Render the operator report as concise plain text."""
        lines: list[str] = []
        for label, items in self.sections():
            lines.append(f"{label}:")
            lines.extend(f"- {item}" for item in items)
        return "\n".join(lines)


@dataclass(frozen=True)
class AuthoringResult:
    """Final result for one authoring request."""

    provider: str
    model: str
    credential_source: str | None
    request_kind: str
    example_id: str | None
    source_logfile_path: str | None
    goal: str
    draft_logfile: str
    server_root: Path
    tool_trace: tuple[AuthoringToolCall, ...]
    final_text: str
    validation: dict[str, object]
    draft_summary: dict[str, object]
    inspect_summary: dict[str, object]
    change_summary: dict[str, object]
    draft_text: str
    report_preview_png: bytes = field(repr=False)
    section_preview_png: bytes = field(repr=False)
    plan: AuthoringPlanResult | None = None
    phase_summaries: tuple[ExecutedAuthoringPhase, ...] = ()
    run_state: AuthoringRunState = field(default_factory=AuthoringRunState)
    user_report: AuthoringUserReport = field(default_factory=AuthoringUserReport)

    @property
    def draft_path(self) -> Path:
        """Return the absolute path to the generated draft logfile."""
        return self.server_root / self.draft_logfile

    @property
    def summary_lines(self) -> tuple[str, ...]:
        """Return the normalized change-summary lines for notebook/UI display."""
        lines = self.change_summary.get("summary_lines", [])
        if not isinstance(lines, list):
            return ()
        normalized: list[str] = []
        for line in lines:
            if isinstance(line, str) and line.strip():
                normalized.append(line)
        return tuple(normalized)

    def preview_bytes(self, kind: str = "section") -> bytes:
        """Return one preview payload by logical kind."""
        normalized_kind = str(kind).strip().lower()
        if normalized_kind == "section":
            return self.section_preview_png
        if normalized_kind == "report":
            return self.report_preview_png
        raise ValueError("preview kind must be either 'section' or 'report'.")

    @property
    def user_report_text(self) -> str:
        """Return the concise operator report as plain text."""
        return self.user_report.to_text()

    def write_preview_artifacts(
        self,
        *,
        output_dir: str | Path | None = None,
    ) -> dict[str, Path]:
        """Persist the in-memory preview PNGs and return their paths."""
        if output_dir is None:
            target_dir = self.draft_path.parent
        else:
            raw_target_dir = Path(output_dir)
            target_dir = (
                raw_target_dir
                if raw_target_dir.is_absolute()
                else self.server_root / raw_target_dir
            )
        target_dir.mkdir(parents=True, exist_ok=True)
        stem = self.draft_path.stem.removesuffix(".log")
        report_preview = target_dir / f"{stem}_report_preview.png"
        section_preview = target_dir / f"{stem}_section_preview.png"
        report_preview.write_bytes(self.report_preview_png)
        section_preview.write_bytes(self.section_preview_png)
        return {
            "report_preview": report_preview,
            "section_preview": section_preview,
        }


class McpSessionProtocol(Protocol):
    """Minimal MCP client session surface needed by the agent layer."""

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        """Call one MCP tool."""

    async def get_prompt(self, name: str, arguments: dict[str, object]) -> object:
        """Request one MCP prompt."""

    async def list_tools(self) -> object:
        """List registered MCP tools."""


class McpRuntimeProtocol(Protocol):
    """Transport/runtime adapter for local MCP access."""

    server_root: Path

    def open_session(self) -> AbstractAsyncContextManager[McpSessionProtocol]:
        """Open one MCP client session."""

    def build_tool_definitions(
        self,
        mcp_tools: Iterable[object],
        *,
        allowed_names: set[str],
        excluded_names: set[str] | None = None,
    ) -> list[FunctionToolDefinition]:
        """Convert raw MCP tool descriptors into generic function tools."""

    def prompt_text(self, result: object) -> str:
        """Extract the first text prompt from one MCP prompt response."""

    def image_bytes(self, result: object) -> bytes:
        """Extract raw bytes from one MCP image response."""

    def tool_result_payload(self, result: object) -> dict[str, object]:
        """Normalize one MCP tool result for provider tool-loop replay."""


ToolCaller = Callable[[str, dict[str, object]], Awaitable[dict[str, object]]]


class ProviderBackendProtocol(Protocol):
    """Provider adapter used by the public authoring session."""

    provider: str
    model: str
    credential_source: str | None

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[FunctionToolDefinition],
        tool_caller: ToolCaller,
        max_rounds: int,
    ) -> ProviderRunResult:
        """Run one authoring loop and replay provider tool calls."""


@dataclass(frozen=True)
class _HeaderFillIntent:
    """Deterministic header-value assignment extracted from one request."""

    values: tuple[tuple[str, str], ...]
    overwrite_policy: str = "replace"

    def as_mapping(self) -> dict[str, str]:
        """Return the extracted key/value pairs as one ordered mapping."""
        return dict(self.values)


@dataclass(frozen=True)
class _MatplotlibStyleIntent:
    """Deterministic report-wide Matplotlib style patch extracted from one request."""

    style_patch: dict[str, object]


@dataclass(frozen=True)
class _TypedPhasePreview:
    """Preview captured from one staged typed checkpoint document."""

    kind: str | None = None
    target: str | None = None
    png: bytes | None = None
    error: str | None = None


def _relative_logfile_path(root: Path, output_logfile: str | Path) -> str:
    """Return one logfile path relative to the configured server root."""
    raw = Path(output_logfile)
    if raw.is_absolute():
        return raw.resolve().relative_to(root).as_posix()
    return raw.as_posix()


def _structured_content(result: object) -> dict[str, object]:
    """Return one MCP structured content payload as a plain dict."""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return dict(structured)
    if structured is None:
        return {}
    raise RuntimeError("Expected MCP structured content to be a mapping.")


def _mcp_error_text(result: object) -> str | None:
    """Return one human-readable MCP tool error message when present."""
    if not bool(getattr(result, "isError", False)):
        return None
    messages: list[str] = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if isinstance(text, str) and text.strip():
            messages.append(text.strip())
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and structured:
        messages.append(json.dumps(structured, indent=2))
    if messages:
        return "\n".join(messages)
    return "MCP returned an error result with no text payload."


def _require_mcp_success(result: object, *, action: str) -> None:
    """Raise one actionable exception when an MCP tool result is marked as an error."""
    error_text = _mcp_error_text(result)
    if error_text is None:
        return
    raise RuntimeError(f"{action} failed:\n{error_text}")


def _existing_draft_path(
    *,
    server_root: Path,
    requested_relative_path: str,
    create_result: dict[str, object],
) -> Path:
    """Resolve one created draft path and require that the file now exists."""
    requested_path = server_root / requested_relative_path
    candidates = [requested_path]
    returned_output_path = create_result.get("output_path")
    if isinstance(returned_output_path, str) and returned_output_path.strip():
        raw_returned_path = Path(returned_output_path)
        returned_path = (
            raw_returned_path.resolve()
            if raw_returned_path.is_absolute()
            else (server_root / raw_returned_path).resolve()
        )
        if returned_path not in candidates:
            candidates.insert(0, returned_path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    searched = ", ".join(str(candidate) for candidate in candidates)
    raise RuntimeError(
        "create_logfile_draft reported success but no draft file was written. "
        f"Checked: {searched}. This usually means the notebook kernel and the "
        "launched `wellplot-mcp` server are not resolving the same wellplot checkout."
    )


def _trim_bullet_prefix(line: str) -> str:
    """Remove one leading list/bullet prefix from a freeform request line."""
    return re.sub(r"^\s*(?:[-*+]\s*|\d+\.\s*)", "", line).strip()


def _normalize_request_token(value: object) -> str:
    """Normalize one request token for track/channel comparisons."""
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _dedupe_text_items(items: list[str]) -> tuple[str, ...]:
    """Return one de-duplicated ordered string tuple."""
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


def _extract_section_context(
    draft_summary: dict[str, object],
) -> tuple[set[str], set[str], set[str]]:
    """Return bound channels, available channels, and track ids from one draft summary."""
    bound_channels: set[str] = set()
    available_channels: set[str] = set()
    track_ids: set[str] = set()
    sections = draft_summary.get("sections", [])
    if not isinstance(sections, list):
        return bound_channels, available_channels, track_ids
    for section in sections:
        if not isinstance(section, dict):
            continue
        for track_id in section.get("track_ids", []):
            if isinstance(track_id, str) and track_id.strip():
                track_ids.add(track_id.strip().lower())
        for channel in section.get("available_channels", []):
            if isinstance(channel, str) and channel.strip():
                available_channels.add(channel.strip().upper())
        bindings_by_track = section.get("bindings_by_track", {})
        if not isinstance(bindings_by_track, dict):
            continue
        for bindings in bindings_by_track.values():
            if not isinstance(bindings, list):
                continue
            for binding in bindings:
                if not isinstance(binding, dict):
                    continue
                channel = binding.get("channel")
                if isinstance(channel, str) and channel.strip():
                    bound_channels.add(channel.strip().upper())
    return bound_channels, available_channels, track_ids


def _request_curve_targets(text: str) -> list[str]:
    """Return explicitly referenced existing curve/channel targets from one request."""
    targets: list[str] = []
    pattern = re.compile(
        r"(?i)\b(?:change|update|set|remove|clear)\b.*?\b([A-Z][A-Z0-9_]{1,12})\b\s+"
        r"(?:curve|channel)\b"
    )
    for raw_line in text.splitlines():
        line = _trim_bullet_prefix(raw_line)
        if not line:
            continue
        match = pattern.search(line)
        if match is None:
            continue
        targets.append(match.group(1).strip().upper())
    return targets


def _request_track_targets(text: str) -> list[str]:
    """Return explicitly referenced existing track targets from one request."""
    targets: list[str] = []
    pattern = re.compile(
        r"(?i)\b(?:change|update|set|remove|clear)\b.*?(?:the\s+)?"
        r"([a-z][a-z0-9 _/-]{0,32}?)\s+track\b"
    )
    for raw_line in text.splitlines():
        line = _trim_bullet_prefix(raw_line)
        if not line:
            continue
        match = pattern.search(line)
        if match is None:
            continue
        target = match.group(1).strip().lower()
        if target:
            targets.append(target)
    return targets


def _assignment_label(entry: object) -> str | None:
    """Return one best-effort human label for a structured assignment entry."""
    if not isinstance(entry, dict):
        return None
    for key in ("target_key", "display_label", "request_key", "channel", "track_id"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _summarize_request_inconsistencies(
    *,
    request_text: str,
    draft_summary: dict[str, object],
) -> tuple[str, ...]:
    """Return concise request inconsistencies provable from the current draft context."""
    bound_channels, available_channels, track_ids = _extract_section_context(draft_summary)
    issues: list[str] = []

    for channel in _request_curve_targets(request_text):
        if channel in bound_channels:
            continue
        if channel in available_channels:
            issues.append(
                f"Requested curve `{channel}` is available in the source data but is not "
                "currently bound in the draft."
            )
            continue
        issues.append(
            f"Requested curve `{channel}` is not available in the current draft or source data."
        )

    normalized_track_ids = {_normalize_request_token(track_id) for track_id in track_ids}
    for track_name in _request_track_targets(request_text):
        normalized_name = _normalize_request_token(track_name)
        if not normalized_name:
            continue
        if normalized_name in normalized_track_ids:
            continue
        issues.append(f"Requested track `{track_name}` does not exist in the current draft.")

    return _dedupe_text_items(issues)


def _build_user_report(
    *,
    request_text: str,
    validation: dict[str, object],
    draft_summary: dict[str, object],
    change_summary: dict[str, object],
    tool_trace: tuple[AuthoringToolCall, ...],
    report_facts: dict[str, object],
) -> AuthoringUserReport:
    """Build one concise deterministic operator report from execution facts."""
    done: list[str] = []
    could_not_do: list[str] = []
    why_not: list[str] = []
    warnings_or_errors: list[str] = []
    next_help: list[str] = []

    summary_lines = change_summary.get("summary_lines", [])
    if isinstance(summary_lines, list):
        for line in summary_lines:
            if isinstance(line, str) and line.strip():
                done.append(line.strip())

    for entry in report_facts.get("completed", []):
        if isinstance(entry, str) and entry.strip():
            done.append(entry.strip())

    for entry in report_facts.get("not_done", []):
        if isinstance(entry, str) and entry.strip():
            could_not_do.append(entry.strip())

    for entry in report_facts.get("reasons", []):
        if isinstance(entry, str) and entry.strip():
            why_not.append(entry.strip())

    for entry in report_facts.get("warnings", []):
        if isinstance(entry, str) and entry.strip():
            warnings_or_errors.append(entry.strip())

    for entry in report_facts.get("next_help", []):
        if isinstance(entry, str) and entry.strip():
            next_help.append(entry.strip())

    for entry in report_facts.get("request_inconsistencies", []):
        if isinstance(entry, str) and entry.strip():
            could_not_do.append(entry.strip())
            why_not.append("The request was explicitly marked unsupported or inconsistent.")

    if validation.get("valid") is False:
        message = validation.get("message")
        if isinstance(message, str) and message.strip():
            warnings_or_errors.append(message.strip())
        else:
            warnings_or_errors.append("The resulting draft did not validate cleanly.")

    inconsistencies = _summarize_request_inconsistencies(
        request_text=request_text,
        draft_summary=draft_summary,
    )
    if inconsistencies:
        could_not_do.extend(inconsistencies)
        why_not.append(
            "Some requested edits referenced tracks or curves the current draft cannot verify."
        )
        next_help.append(
            "I can inspect the current draft to show valid track ids, bound curves, "
            "and available channels."
        )

    if not done and tool_trace:
        done.append(
            "Executed deterministic tools: "
            + ", ".join(item.name for item in tool_trace[:3])
            + ("." if len(tool_trace) <= 3 else ", ...")
        )

    if could_not_do and not why_not:
        why_not.append("The draft or source context did not support every requested edit.")

    if not next_help:
        if could_not_do:
            next_help.append(
                "I can inspect the draft context and suggest the smallest valid follow-up edit."
            )
        else:
            next_help.append("I can help with the next draft revision or render the final PDF.")

    return AuthoringUserReport(
        done=_dedupe_text_items(done),
        could_not_do=_dedupe_text_items(could_not_do),
        why_not=_dedupe_text_items(why_not),
        warnings_or_errors=_dedupe_text_items(warnings_or_errors),
        request_inconsistencies=inconsistencies,
        next_help=_dedupe_text_items(next_help),
    )


def _header_fill_overwrite_policy(text: str) -> str:
    """Infer the safest overwrite policy for one deterministic header-fill request."""
    lowered = text.lower()
    fill_empty_markers = (
        "fill empty",
        "only if empty",
        "leave existing",
        "preserve existing",
        "if blank",
    )
    if any(marker in lowered for marker in fill_empty_markers):
        return "fill_empty"
    return "replace"


def _parse_inline_header_assignment(line: str) -> tuple[str, str] | None:
    """Parse one explicit header assignment from a natural-language line."""
    inline_match = re.match(
        r"(?is)^(?:please\s+)?(?:fill|set|update|populate|apply)\s+"
        r"(?:the\s+)?(?:header|heading)\s+(?P<key>.+?)\s+"
        r"(?:(?:field|value)\s+)?(?:as|to)\s+(?P<value>.+)$",
        line,
    )
    if inline_match is None:
        return None
    key = inline_match.group("key").strip().removesuffix(":")
    value = inline_match.group("value").strip()
    if not key or not value:
        return None
    if key.lower().endswith(" value"):
        key = key[:-6].strip()
    if key.lower().endswith(" field"):
        key = key[:-6].strip()
    return key, value


def _is_header_intro_line(line: str) -> bool:
    """Return whether one line is framing text for a header-ingestion block."""
    return bool(
        re.match(
            r"(?is)^(?:please\s+)?(?:fill|set|update|populate|apply|use)\s+"
            r"(?:the\s+following\s+)?(?:header|heading)(?:\s+(?:fields?|values?))?"
            r"(?:\s+with(?:\s+the\s+following\s+values?)?)?[:.]?$",
            line,
        )
        or re.match(
            r"(?is)^use\s+the\s+following\s+values\s+to\s+complete\s+the\s+relevant\s+"
            r"(?:header|heading)\s+fields[:.]?$",
            line,
        )
        or re.match(r"(?is)^revise\s+the\s+existing\s+draft[.:]?$", line)
    )


def _is_header_category_line(line: str) -> bool:
    """Return whether one line is a category heading inside copied header text."""
    if ":" in line or "=" in line:
        return False
    if len(line) > 80:
        return False
    return bool(re.match(r"^[A-Z0-9 /()&'.,+-]+$", line))


def _is_service_title_category_line(line: str) -> bool:
    """Return whether one copied header category introduces one service-title block."""
    normalized = re.sub(r"[^a-z0-9]+", "", line.lower())
    return normalized in {"logservice", "services", "service"}


def _looks_like_non_header_edit_instruction(line: str) -> bool:
    """Return whether one line asks for broader non-header authoring edits."""
    lowered = line.lower()
    action_verbs = (
        "add",
        "remove",
        "change",
        "update",
        "set",
        "make",
        "move",
        "bind",
        "clear",
        "replace",
        "render",
        "preview",
    )
    scope_markers = (
        "track",
        "curve",
        "raster",
        "annotation",
        "remarks",
        "remark",
        "page ",
        "layout",
        "pdf",
        "render",
        "preview",
        "depth range",
        "output path",
    )
    return any(verb in lowered for verb in action_verbs) and any(
        marker in lowered for marker in scope_markers
    )


def _extract_header_fill_intent(text: str) -> _HeaderFillIntent | None:
    """Return one deterministic header-fill intent when the request is narrowly scoped."""
    lowered = text.lower()
    if "header" not in lowered and "heading" not in lowered:
        return None

    values: list[tuple[str, str]] = []
    in_service_title_block = False
    next_service_title_index = 1
    for raw_line in text.splitlines():
        line = _trim_bullet_prefix(raw_line)
        if not line:
            continue
        if _is_header_intro_line(line):
            continue
        if _is_header_category_line(line):
            in_service_title_block = _is_service_title_category_line(line)
            continue
        if in_service_title_block and ":" not in line and "=" not in line:
            values.append((f"service_title_{next_service_title_index}", line))
            next_service_title_index += 1
            continue
        parsed = _parse_inline_header_assignment(line)
        if parsed is not None:
            values.append(parsed)
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key and value:
                values.append((key, value))
                continue
        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key and value:
                values.append((key, value))
                continue
        if _is_header_category_line(line):
            continue
        if _looks_like_non_header_edit_instruction(line):
            return None
    if not values:
        return None
    return _HeaderFillIntent(
        values=tuple(values),
        overwrite_policy=_header_fill_overwrite_policy(text),
    )


def _merge_optional_mapping(
    original: dict[str, object],
    patch: dict[str, object],
) -> dict[str, object]:
    """Deep-merge one nested mapping patch without mutating either input."""
    merged = dict(original)
    for key, value in patch.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _merge_optional_mapping(existing, value)
            continue
        merged[key] = value
    return merged


def _merge_omitted_defaults(
    existing: dict[str, object],
    defaults: dict[str, object],
) -> dict[str, object]:
    """Return only default fields absent from existing state, recursively."""
    missing: dict[str, object] = {}
    for key, value in defaults.items():
        if key not in existing:
            missing[key] = deepcopy(value)
            continue
        current = existing[key]
        if isinstance(current, dict) and isinstance(value, dict):
            nested = _merge_omitted_defaults(current, value)
            if nested:
                missing[key] = nested
    return missing


def _grid_style_patch_for_line(line: str) -> dict[str, object] | None:
    """Return one deterministic report-grid style patch for a natural-language line."""
    lowered = line.lower()
    if "grid" not in lowered:
        return None

    grid_patch: dict[str, object] = {}
    if any(token in lowered for token in ("darker", "darken", "stronger", "more visible")):
        grid_patch.update(
            {
                "depth_major_color": "#555555",
                "depth_minor_color": "#9a9a9a",
                "depth_major_linewidth": 0.8,
                "depth_minor_linewidth": 0.45,
                "x_major_linewidth": 0.8,
                "x_minor_linewidth": 0.45,
            }
        )
    elif any(token in lowered for token in ("lighter", "lighten", "fainter", "less visible")):
        grid_patch.update(
            {
                "depth_major_color": "#c0c7d2",
                "depth_minor_color": "#dde3ea",
                "depth_major_linewidth": 0.5,
                "depth_minor_linewidth": 0.28,
                "x_major_linewidth": 0.5,
                "x_minor_linewidth": 0.28,
            }
        )

    if any(token in lowered for token in ("thicker", "heavier", "bolder")):
        grid_patch.update(
            {
                "depth_major_linewidth": 0.9,
                "depth_minor_linewidth": 0.5,
                "x_major_linewidth": 0.9,
                "x_minor_linewidth": 0.5,
            }
        )
    elif any(token in lowered for token in ("thinner", "finer")):
        grid_patch.update(
            {
                "depth_major_linewidth": 0.45,
                "depth_minor_linewidth": 0.24,
                "x_major_linewidth": 0.45,
                "x_minor_linewidth": 0.24,
            }
        )

    if not grid_patch:
        return None
    return {"grid": grid_patch}


def _extract_matplotlib_style_intent(text: str) -> tuple[_MatplotlibStyleIntent | None, str]:
    """Extract one deterministic report-style patch and return the remaining request text."""
    style_patch: dict[str, object] = {}
    remaining_lines: list[str] = []
    for raw_line in text.splitlines():
        line = _trim_bullet_prefix(raw_line)
        if not line:
            remaining_lines.append(raw_line)
            continue
        line_patch = _grid_style_patch_for_line(line)
        if line_patch is None:
            remaining_lines.append(raw_line)
            continue
        style_patch = _merge_optional_mapping(style_patch, line_patch)

    remaining_text = "\n".join(remaining_lines).strip()
    if not style_patch:
        return None, text
    return _MatplotlibStyleIntent(style_patch=style_patch), remaining_text


def _extract_named_block(text: str, *, headings: tuple[str, ...]) -> list[str]:
    """Return the indented/body lines that belong to one named prompt block."""
    normalized_headings = {
        re.sub(r"[^a-z0-9]+", "", heading.lower()): heading for heading in headings
    }
    block_lines: list[str] = []
    capturing = False
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        normalized = re.sub(r"[^a-z0-9]+", "", stripped.lower())
        if normalized in normalized_headings:
            capturing = True
            continue
        if capturing and stripped.endswith(":") and not stripped.startswith("-"):
            break
        if capturing:
            block_lines.append(raw_line)
    return block_lines


def _parse_source_slot_mapping(text: str) -> dict[str, str]:
    """Parse one simple packet data-source block into named source slots."""
    values: dict[str, str] = {}
    for raw_line in _extract_named_block(
        text, headings=("data sources:", "source data:", "sources:")
    ):
        line = _trim_bullet_prefix(raw_line)
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        slot = key.strip().lower()
        source_path = value.strip()
        if slot and source_path:
            values[slot] = source_path
    return values


def _request_source_paths(text: str, source_slots: Mapping[str, str]) -> dict[str, str]:
    """Find source paths in a request that are not in its named source block."""
    paths: dict[str, str] = dict(source_slots)
    pattern = re.compile(r"[^\s`'\"(),;]+\.(?:las|dlis)\b", re.IGNORECASE)
    for source_path in pattern.findall(text):
        normalized = source_path.strip()
        if not normalized:
            continue
        if normalized not in paths.values():
            paths[f"source_{len(paths) + 1}"] = normalized
    return paths


def _source_format_for_path(source_path: str) -> str:
    """Infer a safe inspection format from a source filename."""
    suffix = Path(source_path).suffix.lower()
    if suffix == ".las":
        return "las"
    if suffix == ".dlis":
        return "dlis"
    return "auto"


def _extract_packet_header_fill_intent(text: str) -> _HeaderFillIntent | None:
    """Extract one packet header-value block without mixing in broader packet prose."""
    block_lines = _extract_named_block(
        text,
        headings=("header values:", "header:", "header fields:"),
    )
    block_text = "\n".join(block_lines).strip()
    if not block_text:
        return _extract_header_fill_intent(text)
    return _extract_header_fill_intent(f"Header Values:\n{block_text}")


def _extract_packet_remarks(text: str) -> list[dict[str, object]]:
    """Extract one deterministic remarks payload from a structured prompt block."""
    block_lines = _extract_named_block(text, headings=("remarks:", "notes:"))
    remarks: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    current_lines: list[str] = []
    for raw_line in block_lines:
        line = raw_line.strip()
        if not line:
            continue
        trimmed = _trim_bullet_prefix(raw_line)
        if trimmed.lower().startswith("title:"):
            if current is not None and current_lines:
                current["lines"] = list(current_lines)
                remarks.append(current)
            current = {"title": trimmed.split(":", 1)[1].strip(), "alignment": "left"}
            current_lines = []
            continue
        if current is None:
            current = {"title": "Notes", "alignment": "left"}
        current_lines.append(trimmed)
    if current is not None and current_lines:
        current["lines"] = list(current_lines)
        remarks.append(current)
    return remarks


def _normalize_remarks_payload(
    remarks: object,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return one normalized comparable remarks representation."""
    if not isinstance(remarks, list):
        return ()
    normalized: list[tuple[str, tuple[str, ...]]] = []
    for entry in remarks:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title", "")).strip()
        lines_raw = entry.get("lines", [])
        if not title or not isinstance(lines_raw, list):
            continue
        lines = tuple(
            str(line).strip() for line in lines_raw if isinstance(line, str) and line.strip()
        )
        normalized.append((title, lines))
    return tuple(normalized)


def _authoring_bootstrap_message(
    *,
    goal: str,
    seed_label: str,
    logfile_path: str,
    seed_result: dict[str, object],
    sections: list[dict[str, object]],
    heading_patch_keys: list[object],
    curve_binding_patch_keys: list[object],
) -> str:
    """Return the initial user message passed into the provider loop."""
    bootstrap_context = {
        "draft_logfile": logfile_path,
        "seed_label": seed_label,
        "seed_result": seed_result,
        "sections": sections,
        "heading_patch_keys": heading_patch_keys,
        "curve_binding_patch_keys": curve_binding_patch_keys,
    }
    return (
        f"A starter draft already exists at `{logfile_path}`. It was seeded from "
        f"{seed_label}. Do not call create_logfile_draft again. Use MCP mutation "
        "tools only, and make only the changes needed to satisfy the goal.\n\n"
        "Draft context:\n"
        f"{json.dumps(bootstrap_context, indent=2)}\n\n"
        "If the goal only fills existing header values, preserve the current heading "
        "structure and prefer inspect_heading_slots(...), preview_header_mapping(...), "
        "and apply_header_values(...). Do not add remarks unless the goal explicitly "
        "asks for remarks.\n\n"
        "Use MCP tools only; do not rewrite YAML in prose.\n\n"
        f"Goal:\n{goal}"
    )


def _revision_bootstrap_message(
    *,
    feedback: str,
    logfile_path: str,
    sections: list[dict[str, object]],
    heading_patch_keys: list[object],
    curve_binding_patch_keys: list[object],
) -> str:
    """Return the initial user message for revising one existing draft."""
    revision_context = {
        "draft_logfile": logfile_path,
        "sections": sections,
        "heading_patch_keys": heading_patch_keys,
        "curve_binding_patch_keys": curve_binding_patch_keys,
    }
    return (
        f"A draft already exists at `{logfile_path}`. Do not call create_logfile_draft. "
        "Use the smallest reviewable MCP mutations that address the feedback. If the "
        "feedback only fills existing header values, preserve the current heading "
        "structure and prefer inspect_heading_slots(...), preview_header_mapping(...), "
        "and apply_header_values(...).\n\n"
        "Draft context:\n"
        f"{json.dumps(revision_context, indent=2)}\n\n"
        "Use MCP tools only; do not rewrite YAML in prose.\n\n"
        f"Feedback:\n{feedback}"
    )


def _bootstrap_sections(summary: dict[str, object]) -> list[dict[str, object]]:
    """Return compact per-section context for provider bootstrap prompts."""
    sections: list[dict[str, object]] = []
    for section in summary.get("sections", []):
        if not isinstance(section, dict):
            continue
        sections.append(
            {
                "id": section.get("id"),
                "track_ids": section.get("track_ids", []),
                "track_kinds": section.get("track_kinds", []),
                "available_channels": section.get("available_channels", []),
                "source_path": section.get("source_path"),
                "source_format": section.get("source_format"),
            }
        )
    return sections


def _request_seed_label(request: AuthoringRequest) -> str:
    """Return one human-readable seed label for bootstrap prompting."""
    if request.example_id is not None:
        return f"packaged example `{request.example_id}`"
    assert request.source_logfile_path is not None
    return f"starter logfile `{request.source_logfile_path}`"


@dataclass
class AuthoringSession:
    """High-level authoring session bound to one provider and local MCP runtime."""

    backend: ProviderBackendProtocol
    runtime: McpRuntimeProtocol
    allowed_tool_names: tuple[str, ...] = DEFAULT_ALLOWED_MCP_TOOLS

    @classmethod
    def from_local_mcp(
        cls,
        *,
        provider: str,
        model: str,
        server_root: str | Path | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> AuthoringSession:
        """Create one public authoring session backed by local stdio MCP."""
        from .mcp import LocalStdioMcpRuntime
        from .providers.openai import OpenAIAuthoringBackend
        from .providers.openai_compat import OpenAICompatibleAuthoringBackend

        runtime = LocalStdioMcpRuntime(server_root=server_root)
        if provider == "openai":
            backend = OpenAIAuthoringBackend.from_local_configuration(
                model=model,
                server_root=runtime.server_root,
                api_key=api_key,
            )
        elif provider == "openai_compat":
            if base_url is None or not base_url.strip():
                raise ValueError("provider='openai_compat' requires a non-empty base_url.")
            backend = OpenAICompatibleAuthoringBackend.from_local_configuration(
                model=model,
                server_root=runtime.server_root,
                api_key=api_key,
                base_url=base_url,
            )
        else:
            raise ValueError(
                "Unsupported authoring provider. Supported values: 'openai', 'openai_compat'."
            )
        return cls(backend=backend, runtime=runtime)

    async def _finalize_result(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        request_kind: str,
        goal: str,
        example_id: str | None,
        source_logfile_path: str | None,
        baseline_draft_text: str,
        provider_result: ProviderRunResult,
        plan: AuthoringPlanResult | None = None,
        phase_summaries: tuple[ExecutedAuthoringPhase, ...] = (),
        run_state: AuthoringRunState | None = None,
    ) -> AuthoringResult:
        """Collect the standard validation/summary/preview outputs for one draft."""
        output_path = self.runtime.server_root / draft_logfile
        if not output_path.exists():
            raise RuntimeError("The model finished without the expected draft logfile.")

        validation_result = await session.call_tool(
            "validate_logfile",
            {"logfile_path": draft_logfile},
        )
        _require_mcp_success(validation_result, action="validate_logfile")
        draft_summary_result = await session.call_tool(
            "summarize_logfile_draft",
            {"logfile_path": draft_logfile},
        )
        _require_mcp_success(draft_summary_result, action="summarize_logfile_draft")
        inspect_summary_result = await session.call_tool(
            "inspect_logfile",
            {"logfile_path": draft_logfile},
        )
        _require_mcp_success(inspect_summary_result, action="inspect_logfile")
        change_summary_result = await session.call_tool(
            "summarize_logfile_changes",
            {
                "logfile_path": draft_logfile,
                "previous_text": baseline_draft_text,
            },
        )
        _require_mcp_success(change_summary_result, action="summarize_logfile_changes")
        inspect_summary = _structured_content(inspect_summary_result)
        section_ids = inspect_summary.get("section_ids", [])
        if not isinstance(section_ids, list) or not section_ids:
            raise RuntimeError("Expected at least one section id after authoring.")
        first_section_id = section_ids[0]
        report_preview_result = await session.call_tool(
            "preview_logfile_png",
            {
                "logfile_path": draft_logfile,
                "page_index": 0,
                "dpi": 72,
                "include_report_pages": True,
            },
        )
        _require_mcp_success(report_preview_result, action="preview_logfile_png")
        section_preview_result = await session.call_tool(
            "preview_section_png",
            {
                "logfile_path": draft_logfile,
                "section_id": first_section_id,
                "dpi": 72,
            },
        )
        _require_mcp_success(section_preview_result, action="preview_section_png")
        validation_payload = _structured_content(validation_result)
        draft_summary_payload = _structured_content(draft_summary_result)
        change_summary_payload = _structured_content(change_summary_result)
        return AuthoringResult(
            provider=self.backend.provider,
            model=self.backend.model,
            credential_source=self.backend.credential_source,
            request_kind=request_kind,
            example_id=example_id,
            source_logfile_path=source_logfile_path,
            goal=goal,
            draft_logfile=draft_logfile,
            server_root=self.runtime.server_root,
            tool_trace=provider_result.tool_trace,
            final_text=provider_result.final_text,
            validation=validation_payload,
            draft_summary=draft_summary_payload,
            inspect_summary=inspect_summary,
            change_summary=change_summary_payload,
            draft_text=output_path.read_text(encoding="utf-8"),
            report_preview_png=self.runtime.image_bytes(report_preview_result),
            section_preview_png=self.runtime.image_bytes(section_preview_result),
            plan=plan,
            phase_summaries=phase_summaries,
            run_state=AuthoringRunState() if run_state is None else run_state,
            user_report=_build_user_report(
                request_text=goal,
                validation=validation_payload,
                draft_summary=draft_summary_payload,
                change_summary=change_summary_payload,
                tool_trace=provider_result.tool_trace,
                report_facts=getattr(provider_result, "report_facts", {}),
            ),
        )

    def plan(
        self,
        *,
        text: str,
        blueprint_id: str | None = None,
        desired_state: AuthoringDocumentIntent | Mapping[str, object] | None = None,
        existing: AuthoringDocumentSpec | None = None,
        available_channels: Mapping[str, Sequence[AuthoringChannelInput]] | None = None,
    ) -> AuthoringPlanResult:
        """Return a generic, scaffold, or typed desired-state plan.

        ``blueprint_id`` is opt-in. Normal authoring requests must not infer a
        packet blueprint from natural-language keywords. When ``desired_state``
        is supplied, the plan is resolved and reconciled against ``existing``
        without mutating it.
        """
        if desired_state is not None:
            intent = self._coerce_desired_state(desired_state)
            return self._plan_from_desired_state(
                intent,
                existing=existing,
                available_channels=available_channels,
            )
        return self._plan_from_text(text, blueprint_id=blueprint_id)

    @staticmethod
    def _coerce_desired_state(
        desired_state: AuthoringDocumentIntent | Mapping[str, object],
    ) -> AuthoringDocumentIntent:
        """Validate one provider or caller supplied desired-state payload."""
        if isinstance(desired_state, AuthoringDocumentIntent):
            return desired_state
        return AuthoringDocumentIntent.model_validate(dict(desired_state))

    def _plan_from_desired_state(
        self,
        intent: AuthoringDocumentIntent,
        *,
        existing: AuthoringDocumentSpec | None,
        available_channels: Mapping[str, Sequence[AuthoringChannelInput]] | None,
    ) -> AuthoringPlanResult:
        """Build the public plan view for one typed reconciliation plan."""
        defaults_resolution = generic_authoring_defaults(intent)
        reconciliation_plan = reconcile_authoring(
            intent,
            existing=existing,
            defaults=defaults_resolution.defaults,
            available_channels=available_channels,
        )
        reconciliation_plan.warnings.extend(defaults_resolution.warnings)
        operations_by_phase: dict[AuthoringOperationPhase, list[str]] = {}
        for operation in reconciliation_plan.operations:
            operations_by_phase.setdefault(operation.phase, []).append(operation.operation_id)

        phases: list[AuthoringPlanPhase] = []
        for phase in AuthoringOperationPhase:
            operation_ids = operations_by_phase.get(phase, [])
            if not operation_ids:
                continue
            phases.append(
                AuthoringPlanPhase(
                    id=f"desired-{phase.value}",
                    kind=f"desired_state_{phase.value}",
                    summary=f"Apply typed {phase.value} desired-state operations.",
                    instructions=(
                        "Execute the typed operations in dependency order and verify every "
                        "persisted postcondition before proceeding."
                    ),
                    tool_families=("typed_authoring",),
                    preconditions=tuple(
                        f"operation dependencies for {operation_id} are satisfied"
                        for operation_id in operation_ids
                    ),
                    success_checks=("all typed operations read back successfully",),
                    success_check_specs=(
                        {
                            "kind": "typed_postconditions",
                            "operation_ids": operation_ids,
                        },
                    ),
                    metadata={"operation_ids": operation_ids},
                )
            )
        if not phases and reconciliation_plan.ready:
            phases.append(
                AuthoringPlanPhase(
                    id="desired-noop",
                    kind="desired_state_noop",
                    summary="No authoring changes are required.",
                    instructions="Verify that the current canonical document already matches.",
                    tool_families=("typed_authoring",),
                    success_checks=("desired state is already satisfied",),
                    success_check_specs=({"kind": "typed_postconditions", "operation_ids": []},),
                )
            )
        return AuthoringPlanResult(
            mode="desired_state",
            packet_blueprint_id=None,
            phases=tuple(phases),
            blocked=not reconciliation_plan.ready,
            blocked_reasons=tuple(issue.message for issue in reconciliation_plan.issues),
            run_state=AuthoringRunState(
                objectives=tuple(phase.summary for phase in phases),
            ),
            desired_state=intent,
            reconciliation_plan=reconciliation_plan,
        )

    async def _run_deterministic_header_fill(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        request_kind: str,
        goal: str,
        example_id: str | None,
        source_logfile_path: str | None,
        baseline_draft_text: str,
        intent: _HeaderFillIntent,
    ) -> AuthoringResult:
        """Apply one narrow header-fill request without entering the provider loop."""
        inspect_heading_result = await session.call_tool(
            "inspect_heading_slots",
            {"logfile_path": draft_logfile},
        )
        _require_mcp_success(inspect_heading_result, action="inspect_heading_slots")
        inspect_payload = _structured_content(inspect_heading_result)
        if not bool(inspect_payload.get("has_heading", False)):
            raise RuntimeError(
                "Header fill routing requires an existing heading structure in the draft."
            )

        normalized_source_text = "\n".join(f"{key}: {value}" for key, value in intent.values)
        parse_result = await session.call_tool(
            "parse_key_value_text",
            {
                "source_text": normalized_source_text,
                "format_hint": "colon",
            },
        )
        _require_mcp_success(parse_result, action="parse_key_value_text")
        parse_payload = _structured_content(parse_result)
        parsed_values: dict[str, str] = {}
        for pair in parse_payload.get("pairs", []):
            if not isinstance(pair, dict):
                continue
            key = pair.get("key")
            value = pair.get("value")
            if isinstance(key, str) and key.strip() and isinstance(value, str):
                parsed_values[key.strip()] = value
        if not parsed_values:
            parsed_values = intent.as_mapping()

        preview_result = await session.call_tool(
            "preview_header_mapping",
            {
                "logfile_path": draft_logfile,
                "values": parsed_values,
                "overwrite_policy": intent.overwrite_policy,
            },
        )
        _require_mcp_success(preview_result, action="preview_header_mapping")
        apply_result = await session.call_tool(
            "apply_header_values",
            {
                "logfile_path": draft_logfile,
                "values": parsed_values,
                "overwrite_policy": intent.overwrite_policy,
            },
        )
        _require_mcp_success(apply_result, action="apply_header_values")
        apply_payload = _structured_content(apply_result)
        applied_assignments = apply_payload.get("applied_assignments", [])
        applied_count = len(applied_assignments) if isinstance(applied_assignments, list) else 0
        skipped_assignments = apply_payload.get("skipped_assignments", [])
        skipped_count = len(skipped_assignments) if isinstance(skipped_assignments, list) else 0
        completed: list[str] = []
        if isinstance(applied_assignments, list):
            for entry in applied_assignments:
                label = _assignment_label(entry)
                if label is None:
                    continue
                completed.append(f"Filled `{label}`.")
        not_done: list[str] = []
        reasons: list[str] = []
        if isinstance(skipped_assignments, list):
            for entry in skipped_assignments:
                if not isinstance(entry, dict):
                    continue
                label = _assignment_label(entry)
                if label is not None:
                    not_done.append(f"Did not apply `{label}`.")
                reason = entry.get("reason")
                if isinstance(reason, str) and reason.strip():
                    reasons.append(reason.strip())
                else:
                    status = entry.get("status")
                    if isinstance(status, str) and status.strip():
                        reasons.append(f"Status: {status.strip()}.")
        warnings: list[str] = []
        for source_payload in (parse_payload, _structured_content(preview_result), apply_payload):
            payload_warnings = source_payload.get("warnings", [])
            if isinstance(payload_warnings, list):
                warnings.extend(
                    warning.strip()
                    for warning in payload_warnings
                    if isinstance(warning, str) and warning.strip()
                )
        provider_result = ProviderRunResult(
            final_text=(
                "Applied deterministic header value assignment"
                f" ({applied_count} applied, {skipped_count} skipped)."
            ),
            tool_trace=(
                AuthoringToolCall(
                    round=1,
                    name="inspect_heading_slots",
                    arguments={"logfile_path": draft_logfile},
                ),
                AuthoringToolCall(
                    round=1,
                    name="parse_key_value_text",
                    arguments={
                        "source_text": normalized_source_text,
                        "format_hint": "colon",
                    },
                ),
                AuthoringToolCall(
                    round=1,
                    name="preview_header_mapping",
                    arguments={
                        "logfile_path": draft_logfile,
                        "values": parsed_values,
                        "overwrite_policy": intent.overwrite_policy,
                    },
                ),
                AuthoringToolCall(
                    round=1,
                    name="apply_header_values",
                    arguments={
                        "logfile_path": draft_logfile,
                        "values": parsed_values,
                        "overwrite_policy": intent.overwrite_policy,
                    },
                ),
            ),
            report_facts={
                "completed": completed,
                "not_done": not_done,
                "reasons": reasons,
                "warnings": warnings,
                "next_help": [
                    "I can inspect the remaining header slots or preview a more "
                    "explicit mapping for any skipped values."
                ]
                if skipped_count
                else [
                    "I can continue filling the remaining header slots or move on "
                    "to tracks, remarks, or rendering."
                ],
            },
        )
        return await self._finalize_result(
            session=session,
            draft_logfile=draft_logfile,
            request_kind=request_kind,
            goal=goal,
            example_id=example_id,
            source_logfile_path=source_logfile_path,
            baseline_draft_text=baseline_draft_text,
            provider_result=provider_result,
        )

    async def _apply_deterministic_matplotlib_style(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        intent: _MatplotlibStyleIntent,
    ) -> AuthoringToolCall:
        """Apply one deterministic report-wide Matplotlib style patch."""
        result = await session.call_tool(
            "set_matplotlib_style",
            {
                "logfile_path": draft_logfile,
                "style_patch": intent.style_patch,
            },
        )
        _require_mcp_success(result, action="set_matplotlib_style")
        return AuthoringToolCall(
            round=1,
            name="set_matplotlib_style",
            arguments={
                "logfile_path": draft_logfile,
                "style_patch": intent.style_patch,
            },
        )

    @staticmethod
    def _generic_plan_from_text(text: str) -> AuthoringPlanResult:
        """Build generic phases from requested object-operation families."""
        lowered = text.lower()
        phases: list[AuthoringPlanPhase] = []

        def contains(marker: str) -> bool:
            """Match a scope marker as a word or phrase, not a substring."""
            return re.search(rf"\b{re.escape(marker)}s?\b", lowered) is not None

        def add_phase(
            phase_id: str,
            kind: str,
            summary: str,
            instructions: str,
            tool_families: tuple[str, ...],
        ) -> None:
            phases.append(
                AuthoringPlanPhase(
                    id=phase_id,
                    kind=kind,
                    summary=summary,
                    instructions=instructions,
                    tool_families=tool_families,
                    success_checks=(
                        "persisted changes are detected",
                        "deterministic tool outcomes match persisted state",
                    ),
                    success_check_specs=(
                        {"kind": "changes_detected"},
                        {"kind": "tool_outcomes_match"},
                    ),
                )
            )

        if any(
            contains(marker)
            for marker in (
                "section",
                "track",
                "depth track",
                "page layout",
                "layout",
                "replicate",
                "move track",
                "remove track",
            )
        ):
            add_phase(
                "structure",
                "structure",
                "Apply requested section, track, and layout structure changes.",
                "Inspect the current section IDs first. Only add or update tracks in sections "
                "that already exist. If a requested section is missing, use "
                "replicate_section_structure from a compatible existing section after "
                "the source section has its requested structure. For multi-section "
                "requests, complete and verify the source section's tracks first, then "
                "replicate it, then apply target-specific changes. Never issue track or "
                "binding operations against a missing section or move a track before all "
                "requested tracks exist. Treat an MCP result marked is_error=true as a "
                "failed mutation and correct the arguments before continuing. Preserve "
                "existing objects unless the request explicitly changes them.",
                ("sections", "tracks", "layout"),
            )

        if any(
            contains(marker)
            for marker in (
                "bind ",
                "binding",
                "curve",
                "raster",
                "channel",
                "fill",
            )
        ):
            add_phase(
                "bindings",
                "bindings",
                "Apply requested curve, raster, and fill bindings.",
                "Inspect source-channel availability first. Use generic binding tools and "
                "report missing or ambiguous channels instead of inventing them.",
                ("inspect", "bindings", "fills"),
            )

        if any(
            contains(marker)
            for marker in (
                "annotation",
                "remark",
                "heading",
                "title",
                "subtitle",
                "note",
            )
        ):
            add_phase(
                "content",
                "content",
                "Apply requested heading, remarks, and annotation content changes.",
                "Use deterministic content and annotation tools. Keep content attached "
                "to the requested object and report unsupported fields explicitly.",
                ("heading", "remarks", "annotations"),
            )

        if any(
            contains(marker)
            for marker in (
                "scale",
                "color",
                "colour",
                "style",
                "line width",
                "line style",
                "grid",
                "logarithmic",
                "linear",
            )
        ):
            add_phase(
                "styling",
                "styling",
                "Apply requested scales, styles, and grid presentation changes.",
                "Use generic scale and style tools. Preserve explicit values and verify "
                "the persisted nested presentation fields after writing.",
                ("scale", "styles", "presets"),
            )

        if not phases:
            add_phase(
                "authoring",
                "authoring",
                "Apply the requested authoring changes.",
                "Inspect the current draft, choose the smallest deterministic object edits, "
                "and stop if the request references unsupported or missing objects.",
                ("inspect", "authoring"),
            )

        phases.append(
            AuthoringPlanPhase(
                id="verification",
                kind="verification",
                summary="Validate the persisted draft and verify a renderable preview.",
                instructions=(
                    "Validate the draft and verify that the report preview renders. "
                    "Report any remaining unsupported or inconsistent request items."
                ),
                tool_families=("inspect", "validate", "preview"),
                success_checks=("draft validates", "preview renders"),
                success_check_specs=(
                    {"kind": "validation_valid"},
                    {"kind": "preview_renderable"},
                ),
            )
        )
        return AuthoringPlanResult(
            mode="freeform",
            packet_blueprint_id=None,
            phases=tuple(phases),
            blocked=False,
            run_state=AuthoringRunState(
                objectives=tuple(phase.summary for phase in phases),
            ),
        )

    def _plan_from_text(
        self,
        text: str,
        *,
        blueprint_id: str | None = None,
    ) -> AuthoringPlanResult:
        """Build a generic plan or an explicitly selected scaffold plan.

        Packet assets are deliberately not inferred from freeform request text.
        Automatic matching made packet examples an implicit source of authoring
        authority, which could override the user's requested object structure.
        """
        normalized_blueprint_id = None if blueprint_id is None else str(blueprint_id).strip()
        if not normalized_blueprint_id:
            return self._generic_plan_from_text(text)
        blueprint = packet_blueprint_spec(normalized_blueprint_id)
        section_templates = {
            str(section.get("id", "")): dict(section)
            for section in blueprint.get("section_templates", [])
            if isinstance(section, dict)
        }
        phases: list[AuthoringPlanPhase] = []
        for raw_phase in blueprint.get("plan_phases", []):
            if not isinstance(raw_phase, dict):
                continue
            phase_kind = str(raw_phase.get("kind", "")).strip()
            metadata: dict[str, object] = {
                "blueprint_id": normalized_blueprint_id,
                "header_archetype": blueprint.get("header_archetype"),
                "unsupported_features": list(blueprint.get("unsupported_features", [])),
                "remarks_templates": deepcopy(list(blueprint.get("remarks_templates", []))),
                "raster_binding_defaults": deepcopy(
                    dict(blueprint.get("raster_binding_defaults", {}))
                ),
            }
            if phase_kind == "section_scaffold":
                primary_section = next(iter(section_templates.values()), None)
                if isinstance(primary_section, dict):
                    metadata["section_template"] = deepcopy(primary_section)
            elif phase_kind == "section_replication":
                target_template = next(
                    (
                        section
                        for section in section_templates.values()
                        if isinstance(section, dict) and section.get("replicates_from")
                    ),
                    None,
                )
                if isinstance(target_template, dict):
                    metadata["section_template"] = deepcopy(target_template)
            phases.append(
                AuthoringPlanPhase(
                    id=str(raw_phase.get("id", "")).strip(),
                    kind=phase_kind,
                    summary=str(raw_phase.get("summary", "")).strip(),
                    instructions=str(raw_phase.get("instructions", "")).strip(),
                    tool_families=tuple(
                        str(item).strip()
                        for item in raw_phase.get("tool_families", [])
                        if isinstance(item, str) and item.strip()
                    ),
                    preconditions=tuple(
                        str(item).strip()
                        for item in raw_phase.get("preconditions", [])
                        if isinstance(item, str) and item.strip()
                    ),
                    success_checks=tuple(
                        str(item).strip()
                        for item in raw_phase.get("success_checks", [])
                        if isinstance(item, str) and item.strip()
                    ),
                    success_check_specs=tuple(
                        dict(spec)
                        for spec in raw_phase.get("success_check_specs", [])
                        if isinstance(spec, dict)
                    ),
                    max_rounds=(
                        None
                        if raw_phase.get("max_rounds") is None
                        else int(raw_phase.get("max_rounds"))
                    ),
                    metadata=metadata,
                )
            )
        return AuthoringPlanResult(
            mode="scaffold",
            packet_blueprint_id=normalized_blueprint_id,
            phases=tuple(phases),
            blocked=False,
            run_state=AuthoringRunState(
                objectives=tuple(phase.summary for phase in phases),
            ),
        )

    def _run_state_from_summary(
        self,
        *,
        draft_summary: dict[str, object],
        objectives: tuple[str, ...],
        completed_objectives: tuple[str, ...],
        blocked_objectives: tuple[str, ...],
        last_verification: dict[str, object],
    ) -> AuthoringRunState:
        """Build one structured run-state snapshot from the current draft summary."""
        discovered_sections: list[str] = []
        discovered_tracks_by_section: dict[str, tuple[str, ...]] = {}
        discovered_binding_ids_by_track: dict[str, tuple[str, ...]] = {}
        available_channels_by_section: dict[str, tuple[str, ...]] = {}
        for section in draft_summary.get("sections", []):
            if not isinstance(section, dict):
                continue
            section_id = str(section.get("id", "")).strip()
            if not section_id:
                continue
            discovered_sections.append(section_id)
            track_ids = tuple(
                str(track_id).strip()
                for track_id in section.get("track_ids", [])
                if isinstance(track_id, str) and track_id.strip()
            )
            discovered_tracks_by_section[section_id] = track_ids
            available_channels_by_section[section_id] = tuple(
                str(channel).strip()
                for channel in section.get("available_channels", [])
                if isinstance(channel, str) and channel.strip()
            )
            bindings_by_track = section.get("bindings_by_track", {})
            if not isinstance(bindings_by_track, dict):
                continue
            for track_id, bindings in bindings_by_track.items():
                if not isinstance(track_id, str) or not isinstance(bindings, list):
                    continue
                binding_ids = tuple(
                    str(binding.get("id", "")).strip()
                    for binding in bindings
                    if isinstance(binding, dict) and str(binding.get("id", "")).strip()
                )
                discovered_binding_ids_by_track[f"{section_id}/{track_id}"] = binding_ids
        return AuthoringRunState(
            objectives=objectives,
            completed_objectives=completed_objectives,
            blocked_objectives=blocked_objectives,
            discovered_sections=tuple(discovered_sections),
            discovered_tracks_by_section=discovered_tracks_by_section,
            discovered_binding_ids_by_track=discovered_binding_ids_by_track,
            available_channels_by_section=available_channels_by_section,
            last_verification=deepcopy(last_verification),
        )

    @staticmethod
    def _binding_expected_subset(spec: dict[str, object]) -> dict[str, object]:
        """Return the persisted binding fields that should match one expected spec."""
        nested_expected = spec.get("expected")
        if isinstance(nested_expected, dict) and nested_expected:
            return deepcopy(nested_expected)
        subset: dict[str, object] = {}
        for key in (
            "label",
            "scale",
            "style",
            "header_display",
            "fill",
            "profile",
            "normalization",
            "waveform_normalization",
            "clip_percentiles",
            "interpolation",
            "show_raster",
            "raster_alpha",
            "color_limits",
            "colorbar",
            "sample_axis",
            "waveform",
        ):
            if key in spec:
                subset[key] = deepcopy(spec[key])
        return subset

    @staticmethod
    def _subset_matches(actual: object, expected: object) -> bool:
        """Return True when the actual value contains the expected subset exactly."""
        if isinstance(expected, dict):
            if not isinstance(actual, dict):
                return False
            for key, value in expected.items():
                if key not in actual:
                    return False
                if not AuthoringSession._subset_matches(actual[key], value):
                    return False
            return True
        if isinstance(expected, list):
            return isinstance(actual, list) and actual == expected
        return actual == expected

    @staticmethod
    def _matching_bindings_for_spec(
        bindings: list[dict[str, object]],
        spec: dict[str, object],
    ) -> list[dict[str, object]]:
        """Return bindings on one track that target the expected channel and kind."""
        expected_channel = str(spec.get("channel", "")).strip().upper()
        expected_kind = str(spec.get("kind", "")).strip().lower()
        if expected_kind == "binding_subset_matches":
            expected_kind = ""
        matches: list[dict[str, object]] = []
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            if str(binding.get("channel", "")).strip().upper() != expected_channel:
                continue
            if expected_kind and str(binding.get("kind", "")).strip().lower() != expected_kind:
                continue
            matches.append(binding)
        return matches

    @staticmethod
    def _binding_matches_expected_spec(
        bindings: list[dict[str, object]],
        spec: dict[str, object],
    ) -> tuple[bool, str | None]:
        """Return whether one track already contains a binding that matches the spec."""
        matches = AuthoringSession._matching_bindings_for_spec(bindings, spec)
        binding_id = str(spec.get("binding_id", "")).strip()
        if binding_id:
            for binding in matches:
                if str(binding.get("id", "")).strip() == binding_id:
                    expected_subset = AuthoringSession._binding_expected_subset(spec)
                    if AuthoringSession._subset_matches(binding, expected_subset):
                        return True, None
                    return False, f"binding_id={binding_id!r} does not match expected subset"
            return False, f"binding_id={binding_id!r} is missing"
        occurrence = spec.get("occurrence")
        if isinstance(occurrence, int) and occurrence >= 1:
            if len(matches) < occurrence:
                return False, f"occurrence={occurrence} is missing"
            binding = matches[occurrence - 1]
            expected_subset = AuthoringSession._binding_expected_subset(spec)
            if AuthoringSession._subset_matches(binding, expected_subset):
                return True, None
            return False, f"occurrence={occurrence} does not match expected subset"
        expected_subset = AuthoringSession._binding_expected_subset(spec)
        if not matches:
            return False, "binding is missing"
        for binding in matches:
            if AuthoringSession._subset_matches(binding, expected_subset):
                return True, None
        return False, "no binding matched the expected subset"

    @staticmethod
    def _binding_patch_matches(
        binding: dict[str, object],
        patch: dict[str, object],
    ) -> tuple[bool, str | None]:
        """Check one persisted binding against a partial update patch."""
        for key, expected in patch.items():
            if expected is None:
                if key in binding:
                    return False, f"field {key!r} was not cleared"
                continue
            actual = binding.get(key)
            if isinstance(expected, dict):
                if not isinstance(actual, dict) or not AuthoringSession._subset_matches(
                    actual,
                    expected,
                ):
                    return False, f"field {key!r} does not match the requested patch"
                continue
            if actual != expected:
                return False, f"field {key!r} does not match the requested patch"
        return True, None

    async def _verify_tool_outcomes(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        draft_summary: dict[str, object],
        tool_trace: tuple[AuthoringToolCall, ...],
        change_summary: dict[str, object] | None,
    ) -> dict[str, object]:
        """Verify persisted outcomes for deterministic mutating tool calls."""
        mutation_tools = {
            "add_curve_fill",
            "add_annotation_object",
            "add_track",
            "bind_curve",
            "bind_raster",
            "move_track",
            "remove_curve_binding",
            "remove_curve_fill",
            "remove_annotation_object",
            "remove_raster_binding",
            "remove_track",
            "replicate_section_structure",
            "set_depth_axis",
            "set_heading_content",
            "set_matplotlib_style",
            "set_page_layout",
            "set_remarks_content",
            "set_section_view",
            "set_section_data_source",
            "set_track_scales",
            "update_annotation_object",
            "update_curve_binding",
            "update_raster_binding",
            "update_section",
            "update_track",
        }
        outcomes: list[dict[str, object]] = []
        inspections: dict[tuple[str, str], dict[str, object]] = {}
        availability: dict[tuple[str, str], tuple[bool, str]] = {}
        object_inspections: dict[tuple[str, str | None, str | None], list[dict[str, object]]] = {}

        async def inspect_track(section_id: str, track_id: str) -> dict[str, object]:
            target = (section_id, track_id)
            if target not in inspections:
                try:
                    result = await session.call_tool(
                        "inspect_track_bindings",
                        {
                            "logfile_path": draft_logfile,
                            "section_id": section_id,
                            "track_id": track_id,
                        },
                    )
                    _require_mcp_success(result, action="inspect_track_bindings")
                    inspections[target] = _structured_content(result)
                except RuntimeError as exc:
                    inspections[target] = {"_verification_error": str(exc)}
            return inspections[target]

        async def check_channel(section_id: str, channel: str) -> tuple[bool, str]:
            """Confirm one binding channel against the draft's active source."""
            normalized_channel = channel.strip().upper()
            target = (section_id, normalized_channel)
            if target in availability:
                return availability[target]
            if not section_id or not normalized_channel:
                result = False, "binding channel or section is missing"
                availability[target] = result
                return result
            availability_result = await session.call_tool(
                "check_channel_availability",
                {
                    "logfile_path": draft_logfile,
                    "section_id": section_id,
                    "requested_channels": [channel],
                },
            )
            _require_mcp_success(
                availability_result,
                action="check_channel_availability",
            )
            payload = _structured_content(availability_result)
            found_channels = {
                str(value).strip().upper()
                for value in payload.get("found_channels", [])
                if str(value).strip()
            }
            resolved = False
            for resolution in payload.get("resolutions", []):
                if not isinstance(resolution, dict):
                    continue
                requested = str(resolution.get("requested_channel", "")).strip().upper()
                status = str(resolution.get("status", "")).strip().lower()
                if requested == normalized_channel and status in {"exact", "alias"}:
                    resolved = bool(resolution.get("matched_channels"))
                    break
            if normalized_channel in found_channels or resolved:
                result = True, "source channel is available"
            else:
                missing = {
                    str(value).strip().upper()
                    for value in payload.get("missing_channels", [])
                    if str(value).strip()
                }
                warnings = [
                    str(value).strip()
                    for value in payload.get("warnings", [])
                    if str(value).strip()
                ]
                detail = "source channel is missing or ambiguous"
                if normalized_channel in missing:
                    detail = "source channel is missing"
                if warnings:
                    detail += ": " + warnings[0]
                result = False, detail
            availability[target] = result
            return result

        async def inspect_objects(
            object_kind: str,
            *,
            section_id: str | None = None,
            track_id: str | None = None,
        ) -> list[dict[str, object]]:
            """Read canonical objects once for one verification scope."""
            target = (object_kind, section_id, track_id)
            if target not in object_inspections:
                arguments: dict[str, object] = {
                    "logfile_path": draft_logfile,
                    "object_kind": object_kind,
                }
                if section_id is not None:
                    arguments["section_id"] = section_id
                if track_id is not None:
                    arguments["track_id"] = track_id
                result = await session.call_tool("inspect_authoring_objects", arguments)
                _require_mcp_success(result, action="inspect_authoring_objects")
                payload = _structured_content(result)
                objects = payload.get("objects", [])
                object_inspections[target] = (
                    [item for item in objects if isinstance(item, dict)]
                    if isinstance(objects, list)
                    else []
                )
            return object_inspections[target]

        def object_value(item: dict[str, object]) -> dict[str, object]:
            """Return the canonical object portion of one inspection item."""
            value = item.get("object", {})
            return value if isinstance(value, dict) else {}

        def object_ref(item: dict[str, object]) -> dict[str, object]:
            """Return the stable reference portion of one inspection item."""
            value = item.get("ref", {})
            return value if isinstance(value, dict) else {}

        def find_object(
            objects: list[dict[str, object]],
            *,
            object_id: str | None = None,
            index: int | None = None,
        ) -> dict[str, object] | None:
            """Find one canonical object by stable id or ordered index."""
            for item in objects:
                ref = object_ref(item)
                if object_id is not None and str(ref.get("object_id", "")) == object_id:
                    return object_value(item)
                if index is not None and ref.get("index") == index:
                    return object_value(item)
            return None

        def section_summary(section_id: str) -> dict[str, object]:
            return next(
                (
                    section
                    for section in draft_summary.get("sections", [])
                    if isinstance(section, dict)
                    and str(section.get("id", "")).strip() == section_id
                ),
                {},
            )

        def record(
            call: AuthoringToolCall,
            ok: bool,
            detail: str,
        ) -> None:
            target_parts = [
                f"{key}={call.arguments[key]}"
                for key in (
                    "section_id",
                    "track_id",
                    "source_section_id",
                    "target_section_id",
                    "channel",
                    "binding_id",
                )
                if call.arguments.get(key) not in (None, "")
            ]
            outcomes.append(
                {
                    "tool": call.name,
                    "section_id": call.arguments.get("section_id"),
                    "track_id": call.arguments.get("track_id"),
                    "target": ", ".join(target_parts),
                    "ok": ok,
                    "detail": detail,
                }
            )

        changed = bool(
            change_summary
            and (change_summary.get("changed") or bool(change_summary.get("summary_lines")))
        )
        for call in tool_trace:
            if call.name not in mutation_tools:
                continue
            arguments = call.arguments
            section_id = str(arguments.get("section_id", "")).strip()
            track_id = str(arguments.get("track_id", "")).strip()

            if call.name == "set_heading_content":
                heading_changed = bool(
                    change_summary.get("heading_changed", changed) if change_summary else False
                )
                record(call, heading_changed, "heading_changed=" + str(heading_changed))
                continue
            if call.name == "set_remarks_content":
                remark_objects = await inspect_objects("remark")
                persisted_remarks = [object_value(item) for item in remark_objects]
                expected_remarks = _normalize_remarks_payload(arguments.get("remarks"))
                actual_remarks = _normalize_remarks_payload(persisted_remarks)
                remarks_match = actual_remarks == expected_remarks
                detail = (
                    f"remarks={len(actual_remarks)}"
                    if remarks_match
                    else f"remarks mismatch: expected={len(expected_remarks)}, "
                    f"actual={len(actual_remarks)}"
                )
                record(call, remarks_match, detail)
                continue
            if call.name in {
                "set_matplotlib_style",
                "set_section_data_source",
            }:
                record(call, changed, f"changed={changed}")
                continue

            if call.name == "set_depth_axis":
                depth_objects = await inspect_objects("depth")
                depth = find_object(depth_objects, object_id="depth")
                expected = {
                    key: arguments[key]
                    for key in ("unit", "scale", "major_step", "minor_step")
                    if arguments.get(key) is not None
                }
                ok = (
                    bool(expected)
                    and depth is not None
                    and self._subset_matches(
                        depth,
                        expected,
                    )
                )
                record(call, ok, "depth axis matches" if ok else "depth axis mismatch")
                continue

            if call.name == "update_section":
                section_objects = await inspect_objects("section", section_id=section_id)
                section = find_object(section_objects, object_id=section_id)
                expected = {
                    key: arguments[key]
                    for key in ("title", "subtitle", "depth_range")
                    if arguments.get(key) is not None
                }
                ok = (
                    bool(expected)
                    and section is not None
                    and self._subset_matches(
                        section,
                        expected,
                    )
                )
                record(call, ok, "section fields match" if ok else "section fields mismatch")
                continue

            if call.name == "set_page_layout":
                page_objects = await inspect_objects("page")
                page = find_object(page_objects, object_id="page")
                page_patch = arguments.get("page_patch")
                render_patch = arguments.get("render_patch")
                page_ok = (
                    isinstance(page_patch, dict)
                    and bool(page_patch)
                    and page is not None
                    and self._subset_matches(page, page_patch)
                ) or not page_patch
                render_ok = bool(render_patch) and changed if render_patch else True
                ok = page_ok and render_ok
                record(
                    call,
                    ok,
                    f"page={page_ok}, render_change={render_ok}",
                )
                continue

            if call.name == "set_section_view":
                section_objects = await inspect_objects("section", section_id=section_id)
                depth_objects = await inspect_objects("depth")
                page_objects = await inspect_objects("page")
                section = find_object(section_objects, object_id=section_id)
                depth = find_object(depth_objects, object_id="depth")
                page = find_object(page_objects, object_id="page")
                section_expected = {
                    key: arguments[key]
                    for key in ("title", "subtitle", "depth_range")
                    if arguments.get(key) is not None
                }
                depth_expected = {
                    key: arguments[key]
                    for key in ("unit", "scale", "major_step", "minor_step")
                    if arguments.get(key) is not None
                }
                page_patch = arguments.get("page_patch")
                render_patch = arguments.get("render_patch")
                section_ok = (
                    not section_expected
                    or section is not None
                    and self._subset_matches(section, section_expected)
                )
                depth_ok = (
                    not depth_expected
                    or depth is not None
                    and self._subset_matches(depth, depth_expected)
                )
                page_ok = (
                    not page_patch
                    or isinstance(page_patch, dict)
                    and page is not None
                    and self._subset_matches(page, page_patch)
                )
                render_ok = bool(render_patch) and changed if render_patch else True
                ok = section_ok and depth_ok and page_ok and render_ok
                record(
                    call,
                    ok,
                    f"section={section_ok}, depth={depth_ok}, page={page_ok}, "
                    f"render_change={render_ok}",
                )
                continue

            if call.name in {
                "add_annotation_object",
                "update_annotation_object",
                "remove_annotation_object",
            }:
                annotation_objects = await inspect_objects(
                    "annotation",
                    section_id=section_id,
                    track_id=track_id,
                )
                if call.name == "add_annotation_object":
                    annotation = arguments.get("annotation")
                    annotation_id = (
                        str(annotation.get("annotation_id", "")).strip()
                        if isinstance(annotation, dict)
                        else ""
                    )
                    persisted = find_object(annotation_objects, object_id=annotation_id)
                    ok = (
                        isinstance(annotation, dict)
                        and bool(annotation_id)
                        and persisted is not None
                        and self._subset_matches(persisted, annotation)
                    )
                    detail = "annotation matches" if ok else "annotation is missing or mismatched"
                elif call.name == "update_annotation_object":
                    persisted = find_object(
                        annotation_objects,
                        index=arguments.get("annotation_index")
                        if isinstance(arguments.get("annotation_index"), int)
                        else None,
                    )
                    patch = arguments.get("patch")
                    ok = (
                        isinstance(patch, dict)
                        and persisted is not None
                        and self._subset_matches(persisted, patch)
                    )
                    detail = "annotation patch matches" if ok else "annotation patch mismatch"
                else:
                    ok = changed
                    detail = (
                        "annotation removal changed the draft"
                        if ok
                        else "annotation removal not detected"
                    )
                record(call, ok, detail)
                continue

            if call.name in {"add_track", "remove_track", "move_track"}:
                section = section_summary(section_id)
                track_ids = section.get("track_ids", [])
                exists = isinstance(track_ids, list) and track_id in track_ids
                if call.name == "add_track":
                    expected_kind = str(arguments.get("kind", "")).strip()
                    kinds = section.get("track_kinds", [])
                    index = track_ids.index(track_id) if exists else -1
                    kind_matches = not expected_kind or (
                        isinstance(kinds, list)
                        and index >= 0
                        and index < len(kinds)
                        and str(kinds[index]).strip() == expected_kind
                    )
                    record(
                        call,
                        exists and kind_matches,
                        f"exists={exists}, kind_matches={kind_matches}",
                    )
                elif call.name == "remove_track":
                    record(call, not exists, f"exists_after_remove={exists}")
                else:
                    record(call, changed, f"changed={changed}")
                continue

            if call.name == "replicate_section_structure":
                source_section_id = str(arguments.get("source_section_id", "")).strip()
                target_section_id = str(arguments.get("target_section_id", "")).strip()
                source_exists = bool(section_summary(source_section_id))
                target_exists = bool(section_summary(target_section_id))
                ok = (
                    bool(source_section_id and target_section_id)
                    and source_exists
                    and target_exists
                )
                record(
                    call,
                    ok,
                    (
                        "replicated section exists"
                        if ok
                        else f"source_exists={source_exists}, target_exists={target_exists}"
                    ),
                )
                continue

            inspection = await inspect_track(section_id, track_id)
            bindings = inspection.get("bindings", [])
            if not isinstance(bindings, list):
                bindings = []
            track = inspection.get("track", {})
            if not isinstance(track, dict):
                track = {}
            verification_error = inspection.get("_verification_error")
            if isinstance(verification_error, str) and verification_error:
                record(call, False, verification_error)
                continue

            if call.name == "update_track":
                patch = arguments.get("patch", {})
                ok = isinstance(patch, dict) and self._subset_matches(track, patch)
                record(call, ok, "track patch matches" if ok else "track patch mismatch")
                continue

            if call.name == "set_track_scales":
                ok = True
                details: list[str] = []
                x_scale = arguments.get("x_scale")
                if isinstance(x_scale, dict):
                    ok = self._subset_matches(track.get("x_scale"), x_scale)
                    details.append(f"x_scale={ok}")
                curve_scale = arguments.get("curve_scale")
                if isinstance(curve_scale, dict):
                    curve_bindings = [
                        binding
                        for binding in bindings
                        if isinstance(binding, dict)
                        and str(binding.get("kind", "")).strip().lower() == "curve"
                    ]
                    curve_ok = bool(curve_bindings) and all(
                        self._subset_matches(binding.get("scale"), curve_scale)
                        for binding in curve_bindings
                    )
                    ok = ok and curve_ok
                    details.append(f"curve_scale={curve_ok}")
                channel_scales = arguments.get("channel_scales")
                if isinstance(channel_scales, dict):
                    for channel, expected_scale in channel_scales.items():
                        target_bindings = [
                            binding
                            for binding in bindings
                            if isinstance(binding, dict)
                            and str(binding.get("channel", "")).upper() == str(channel).upper()
                        ]
                        channel_ok = bool(target_bindings) and all(
                            isinstance(expected_scale, dict)
                            and self._subset_matches(binding.get("scale"), expected_scale)
                            for binding in target_bindings
                        )
                        ok = ok and channel_ok
                        details.append(f"{channel}={channel_ok}")
                record(call, ok, ", ".join(details) or "no scale fields supplied")
                continue

            binding_kind = "raster" if "raster" in call.name else "curve"
            channel = str(arguments.get("channel", "")).strip()
            matching = [
                binding
                for binding in bindings
                if isinstance(binding, dict)
                and str(binding.get("kind", "")).strip().lower() == binding_kind
                and str(binding.get("channel", "")).strip().upper() == channel.upper()
            ]
            binding_id = str(arguments.get("binding_id", "")).strip()
            if binding_id:
                matching = [
                    binding
                    for binding in matching
                    if str(binding.get("id", "")).strip() == binding_id
                ]

            if call.name in {
                "add_curve_fill",
                "bind_curve",
                "bind_raster",
                "update_curve_binding",
                "update_raster_binding",
            }:
                channel_available, availability_detail = await check_channel(
                    section_id,
                    channel,
                )
                if not channel_available:
                    record(call, False, availability_detail)
                    continue
            if call.name in {"remove_curve_binding", "remove_raster_binding"}:
                record(call, not matching, f"remaining_matches={len(matching)}")
                continue
            if not matching:
                record(call, False, "persisted binding is missing")
                continue
            target_binding = matching[0]
            expected: dict[str, object] = {}
            if call.name in {"bind_curve", "bind_raster"}:
                expected["channel"] = channel
                expected["kind"] = binding_kind
                for key in (
                    "label",
                    "style",
                    "scale",
                    "header_display",
                    "profile",
                    "normalization",
                    "waveform_normalization",
                    "clip_percentiles",
                    "interpolation",
                    "show_raster",
                    "raster_alpha",
                    "color_limits",
                    "colorbar",
                    "sample_axis",
                    "waveform",
                ):
                    if key in arguments and arguments[key] is not None:
                        expected[key] = arguments[key]
                if binding_id:
                    expected["binding_id"] = binding_id
                ok, detail = self._binding_matches_expected_spec(bindings, expected)
            elif call.name in {"update_curve_binding", "update_raster_binding"}:
                patch = arguments.get("patch", {})
                ok, detail = (
                    self._binding_patch_matches(target_binding, patch)
                    if isinstance(patch, dict)
                    else (False, "binding patch is not a mapping")
                )
            elif call.name == "add_curve_fill":
                fill = target_binding.get("fill")
                ok = (
                    isinstance(fill, dict)
                    and str(fill.get("kind", "")) == str(arguments.get("kind", "")).strip().lower()
                )
                detail = "fill kind matches" if ok else "persisted fill is missing or mismatched"
            elif call.name == "remove_curve_fill":
                ok = "fill" not in target_binding
                detail = "fill removed" if ok else "fill remains"
            else:
                ok = changed
                detail = f"changed={changed}"
            record(call, ok, detail or "outcome verified")

        return {
            "ok": all(bool(outcome.get("ok")) for outcome in outcomes),
            "outcomes": outcomes,
        }

    def _phase_success_state(
        self,
        *,
        phase: AuthoringPlanPhase,
        draft_summary: dict[str, object],
        validation: dict[str, object] | None = None,
        preview_renderable: bool = False,
        verification_context: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Evaluate one phase's machine-checkable success state."""
        sections = {
            str(section.get("id", "")): section
            for section in draft_summary.get("sections", [])
            if isinstance(section, dict)
        }
        context = verification_context or {}
        checks: list[dict[str, object]] = []
        for spec in phase.success_check_specs:
            kind = str(spec.get("kind", "")).strip()
            ok = False
            detail: str | None = None
            if kind == "heading_exists":
                ok = bool(draft_summary.get("has_heading", False))
            elif kind == "remarks_exists":
                ok = bool(draft_summary.get("has_remarks", False))
            elif kind == "section_exists":
                ok = str(spec.get("section_id", "")) in sections
            elif kind == "track_exists":
                section = sections.get(str(spec.get("section_id", "")), {})
                track_ids = section.get("track_ids", [])
                ok = (
                    str(spec.get("track_id", "")) in track_ids
                    if isinstance(track_ids, list)
                    else False
                )
            elif kind == "track_kind_is":
                section = sections.get(str(spec.get("section_id", "")), {})
                track_ids = section.get("track_ids", [])
                track_kinds = section.get("track_kinds", [])
                expected_track_id = str(spec.get("track_id", "")).strip()
                expected_kind = str(spec.get("track_kind", "")).strip()
                current_kind = None
                if isinstance(track_ids, list) and isinstance(track_kinds, list):
                    for track_id, track_kind in zip(track_ids, track_kinds, strict=False):
                        if str(track_id).strip() == expected_track_id:
                            current_kind = str(track_kind).strip()
                            break
                ok = current_kind == expected_kind and bool(expected_kind)
                detail = f"current_kind={current_kind!r}, expected_kind={expected_kind!r}"
            elif kind == "binding_channel_exists":
                section = sections.get(str(spec.get("section_id", "")), {})
                bindings_by_track = section.get("bindings_by_track", {})
                bindings = (
                    bindings_by_track.get(str(spec.get("track_id", "")), [])
                    if isinstance(bindings_by_track, dict)
                    else []
                )
                count = sum(
                    1
                    for binding in bindings
                    if isinstance(binding, dict)
                    and str(binding.get("channel", "")).upper()
                    == str(spec.get("channel", "")).upper()
                )
                min_count = int(spec.get("min_count", 1))
                ok = count >= min_count
                detail = f"count={count}, min_count={min_count}"
            elif kind == "binding_subset_matches":
                section = sections.get(str(spec.get("section_id", "")), {})
                bindings_by_track = section.get("bindings_by_track", {})
                bindings = (
                    bindings_by_track.get(str(spec.get("track_id", "")), [])
                    if isinstance(bindings_by_track, dict)
                    else []
                )
                if not isinstance(bindings, list):
                    bindings = []
                ok, detail = self._binding_matches_expected_spec(bindings, spec)
            elif kind == "header_values_applied":
                intent_present = bool(context.get("header_fill_intent_present", False))
                preview_payload = context.get("header_mapping_preview")
                if not intent_present:
                    ok = False
                    detail = "No deterministic header-value block was available."
                elif not isinstance(preview_payload, dict):
                    ok = False
                    detail = "No header mapping preview was captured for verification."
                else:
                    resolved_assignments = preview_payload.get("resolved_assignments", [])
                    conflicts = preview_payload.get("conflicting_values", [])
                    unmatched = preview_payload.get("unmatched_values", [])
                    matched_count = (
                        len(resolved_assignments) if isinstance(resolved_assignments, list) else 0
                    )
                    pending_count = (
                        sum(
                            1
                            for entry in resolved_assignments
                            if isinstance(entry, dict)
                            and str(entry.get("action", "")).strip().lower() != "unchanged"
                        )
                        if isinstance(resolved_assignments, list)
                        else 0
                    )
                    conflict_count = len(conflicts) if isinstance(conflicts, list) else 0
                    unmatched_count = len(unmatched) if isinstance(unmatched, list) else 0
                    ok = matched_count > 0 and pending_count == 0 and conflict_count == 0
                    detail = (
                        f"matched={matched_count}, pending={pending_count}, "
                        f"unmatched={unmatched_count}, conflicts={conflict_count}"
                    )
            elif kind == "remarks_match":
                expected_remarks = _normalize_remarks_payload(context.get("expected_remarks"))
                heading_slots = context.get("heading_slots")
                current_remarks = ()
                if isinstance(heading_slots, dict):
                    current_values = heading_slots.get("current_values", {})
                    if isinstance(current_values, dict):
                        current_remarks = _normalize_remarks_payload(
                            current_values.get("remarks", [])
                        )
                ok = bool(expected_remarks) and current_remarks == expected_remarks
                detail = (
                    f"expected={len(expected_remarks)}, current={len(current_remarks)}"
                    if expected_remarks
                    else "No deterministic remarks block was available."
                )
            elif kind == "changes_detected":
                change_summary = context.get("change_summary")
                summary_lines = (
                    change_summary.get("summary_lines", [])
                    if isinstance(change_summary, dict)
                    else []
                )
                ok = isinstance(summary_lines, list) and bool(summary_lines)
                detail = (
                    f"summary_lines={len(summary_lines)}"
                    if isinstance(summary_lines, list)
                    else "No change summary was captured."
                )
            elif kind == "tool_outcomes_match":
                outcome_state = context.get("tool_outcomes")
                outcomes = (
                    outcome_state.get("outcomes", []) if isinstance(outcome_state, dict) else []
                )
                ok = (
                    bool(
                        outcome_state
                        and outcome_state.get("ok")
                        and isinstance(outcomes, list)
                        and outcomes
                    )
                    if isinstance(outcome_state, dict)
                    else False
                )
                failed_outcomes = [
                    outcome
                    for outcome in outcomes
                    if isinstance(outcome, dict) and not bool(outcome.get("ok"))
                ]
                detail = (
                    (
                        f"outcomes={len(outcomes)}, failed={len(failed_outcomes)}: "
                        + "; ".join(
                            "{tool}[{target}]: {failure}".format(
                                tool=str(outcome.get("tool", "unknown")),
                                target=str(outcome.get("target", "")).strip() or "no target",
                                failure=str(outcome.get("detail", "verification failed")),
                            )
                            for outcome in failed_outcomes
                        )
                    )
                    if isinstance(outcomes, list)
                    else "No tool outcome verification was captured."
                )
            elif kind == "validation_valid":
                ok = bool(validation and validation.get("valid") is True)
            elif kind == "preview_renderable":
                ok = preview_renderable
            else:
                ok = False
                detail = "Unsupported success-check kind."
            checks.append(
                {
                    "kind": kind,
                    "ok": ok,
                    "spec": deepcopy(spec),
                    "detail": detail,
                }
            )
        return {
            "ok": all(bool(item.get("ok")) for item in checks) if checks else True,
            "checks": checks,
        }

    async def _phase_verification_context(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        phase: AuthoringPlanPhase,
        request_text: str,
        previous_draft_text: str | None = None,
    ) -> dict[str, object]:
        """Capture one deterministic verification context bundle for a phase."""
        check_kinds = {str(spec.get("kind", "")).strip() for spec in phase.success_check_specs}
        context: dict[str, object] = {}
        if "header_values_applied" in check_kinds:
            intent = _extract_packet_header_fill_intent(request_text)
            context["header_fill_intent_present"] = bool(intent and intent.values)
            if intent is not None and intent.values:
                preview_result = await session.call_tool(
                    "preview_header_mapping",
                    {
                        "logfile_path": draft_logfile,
                        "values": intent.as_mapping(),
                        "overwrite_policy": intent.overwrite_policy,
                    },
                )
                _require_mcp_success(preview_result, action="preview_header_mapping")
                context["header_mapping_preview"] = _structured_content(preview_result)
        if "remarks_match" in check_kinds:
            context["expected_remarks"] = _extract_packet_remarks(request_text)
        if "remarks_match" in check_kinds or "remarks_exists" in check_kinds:
            heading_slots_result = await session.call_tool(
                "inspect_heading_slots",
                {"logfile_path": draft_logfile},
            )
            _require_mcp_success(heading_slots_result, action="inspect_heading_slots")
            context["heading_slots"] = _structured_content(heading_slots_result)
        if "changes_detected" in check_kinds and previous_draft_text is not None:
            change_summary_result = await session.call_tool(
                "summarize_logfile_changes",
                {
                    "logfile_path": draft_logfile,
                    "previous_text": previous_draft_text,
                },
            )
            _require_mcp_success(
                change_summary_result,
                action="summarize_logfile_changes",
            )
            context["change_summary"] = _structured_content(change_summary_result)
        return context

    async def _capture_phase_preview(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        phase: AuthoringPlanPhase,
        draft_summary: dict[str, object],
    ) -> tuple[str | None, str | None, bytes | None]:
        """Capture one checkpoint preview for the executed phase when possible."""
        preferred_section_id = None
        section_ids = draft_summary.get("section_ids", [])
        if isinstance(section_ids, list):
            for candidate in ("main_pass", "main", "repeat_pass"):
                if candidate in section_ids:
                    preferred_section_id = candidate
                    break
            if preferred_section_id is None and section_ids:
                first_section = section_ids[0]
                preferred_section_id = first_section if isinstance(first_section, str) else None

        if phase.kind in {"header_scaffold", "header_fill", "remarks", "verification"}:
            preview_result = await session.call_tool(
                "preview_logfile_png",
                {
                    "logfile_path": draft_logfile,
                    "page_index": 0,
                    "dpi": 72,
                    "include_report_pages": True,
                },
            )
            _require_mcp_success(preview_result, action="preview_logfile_png")
            return "report", None, self.runtime.image_bytes(preview_result)

        if preferred_section_id is None:
            return None, None, None
        preview_result = await session.call_tool(
            "preview_section_png",
            {
                "logfile_path": draft_logfile,
                "section_id": preferred_section_id,
                "dpi": 72,
            },
        )
        _require_mcp_success(preview_result, action="preview_section_png")
        return "section", preferred_section_id, self.runtime.image_bytes(preview_result)

    async def _apply_packet_header_fill(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        request_text: str,
    ) -> ProviderRunResult:
        """Apply one packet header-fill phase deterministically when possible."""
        intent = _extract_packet_header_fill_intent(request_text)
        if intent is None:
            return ProviderRunResult(
                final_text="No deterministic packet header-value block was found.",
                tool_trace=(),
                report_facts={
                    "warnings": ["No explicit packet header block was found to fill."],
                },
            )
        inspect_heading_result = await session.call_tool(
            "inspect_heading_slots",
            {"logfile_path": draft_logfile},
        )
        _require_mcp_success(inspect_heading_result, action="inspect_heading_slots")
        parse_result = await session.call_tool(
            "parse_key_value_text",
            {
                "source_text": "\n".join(f"{key}: {value}" for key, value in intent.values),
                "format_hint": "colon",
            },
        )
        _require_mcp_success(parse_result, action="parse_key_value_text")
        parsed_payload = _structured_content(parse_result)
        parsed_values: dict[str, str] = {}
        for pair in parsed_payload.get("pairs", []):
            if not isinstance(pair, dict):
                continue
            key = pair.get("key")
            value = pair.get("value")
            if isinstance(key, str) and key.strip() and isinstance(value, str):
                parsed_values[key.strip()] = value
        if not parsed_values:
            parsed_values = intent.as_mapping()
        preview_result = await session.call_tool(
            "preview_header_mapping",
            {
                "logfile_path": draft_logfile,
                "values": parsed_values,
                "overwrite_policy": intent.overwrite_policy,
            },
        )
        _require_mcp_success(preview_result, action="preview_header_mapping")
        apply_result = await session.call_tool(
            "apply_header_values",
            {
                "logfile_path": draft_logfile,
                "values": parsed_values,
                "overwrite_policy": intent.overwrite_policy,
            },
        )
        _require_mcp_success(apply_result, action="apply_header_values")
        apply_payload = _structured_content(apply_result)
        return ProviderRunResult(
            final_text="Applied deterministic packet header values.",
            tool_trace=(
                AuthoringToolCall(
                    round=1,
                    name="inspect_heading_slots",
                    arguments={"logfile_path": draft_logfile},
                ),
                AuthoringToolCall(
                    round=1,
                    name="parse_key_value_text",
                    arguments={
                        "source_text": "\n".join(f"{key}: {value}" for key, value in intent.values),
                        "format_hint": "colon",
                    },
                ),
                AuthoringToolCall(
                    round=1,
                    name="preview_header_mapping",
                    arguments={
                        "logfile_path": draft_logfile,
                        "values": parsed_values,
                        "overwrite_policy": intent.overwrite_policy,
                    },
                ),
                AuthoringToolCall(
                    round=1,
                    name="apply_header_values",
                    arguments={
                        "logfile_path": draft_logfile,
                        "values": parsed_values,
                        "overwrite_policy": intent.overwrite_policy,
                    },
                ),
            ),
            report_facts={
                "completed": ["Filled matching packet header values."],
                "warnings": list(apply_payload.get("warnings", []))
                if isinstance(apply_payload.get("warnings"), list)
                else [],
            },
        )

    async def _apply_packet_remarks(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        request_text: str,
    ) -> ProviderRunResult:
        """Apply one packet remarks phase deterministically when possible."""
        remarks = _extract_packet_remarks(request_text)
        if not remarks:
            return ProviderRunResult(
                final_text="No explicit packet remarks block was found.",
                tool_trace=(),
            )
        result = await session.call_tool(
            "set_remarks_content",
            {
                "logfile_path": draft_logfile,
                "remarks": remarks,
            },
        )
        _require_mcp_success(result, action="set_remarks_content")
        return ProviderRunResult(
            final_text="Applied deterministic packet remarks block.",
            tool_trace=(
                AuthoringToolCall(
                    round=1,
                    name="set_remarks_content",
                    arguments={"logfile_path": draft_logfile, "remarks": remarks},
                ),
            ),
            report_facts={"completed": ["Updated the remarks block from the packet prompt."]},
        )

    async def _apply_packet_raster_defaults(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        blueprint: dict[str, object],
    ) -> tuple[AuthoringToolCall, ...]:
        """Replay deterministic raster defaults declared by the packet blueprint."""
        defaults = blueprint.get("raster_binding_defaults", {})
        if not isinstance(defaults, dict) or not defaults:
            return ()
        summary_result = await session.call_tool(
            "summarize_logfile_draft",
            {"logfile_path": draft_logfile},
        )
        _require_mcp_success(summary_result, action="summarize_logfile_draft")
        summary_payload = _structured_content(summary_result)
        section_templates = {
            str(section.get("id", "")): section
            for section in blueprint.get("section_templates", [])
            if isinstance(section, dict)
        }
        tool_calls: list[AuthoringToolCall] = []
        for section in summary_payload.get("sections", []):
            if not isinstance(section, dict):
                continue
            section_id = str(section.get("id", "")).strip()
            template = section_templates.get(section_id)
            if not isinstance(template, dict):
                continue
            expected_by_track = template.get("expected_bindings_by_track", {})
            if not isinstance(expected_by_track, dict):
                continue
            for track_id, patch in defaults.items():
                if not isinstance(track_id, str) or not isinstance(patch, dict):
                    continue
                expected_channels = expected_by_track.get(track_id, [])
                if not isinstance(expected_channels, list) or not expected_channels:
                    continue
                channel = str(expected_channels[0]).strip()
                if not channel:
                    continue
                inspect_result = await session.call_tool(
                    "inspect_track_bindings",
                    {
                        "logfile_path": draft_logfile,
                        "section_id": section_id,
                        "track_id": track_id,
                    },
                )
                _require_mcp_success(inspect_result, action="inspect_track_bindings")
                inspect_payload = _structured_content(inspect_result)
                bindings = inspect_payload.get("bindings", [])
                if not isinstance(bindings, list):
                    continue
                target_binding = next(
                    (
                        binding
                        for binding in bindings
                        if isinstance(binding, dict)
                        and str(binding.get("kind", "")).lower() == "raster"
                        and str(binding.get("channel", "")).upper() == channel.upper()
                    ),
                    None,
                )
                if target_binding is None:
                    continue
                default_patch = _merge_omitted_defaults(target_binding, patch)
                if not default_patch:
                    continue
                result = await session.call_tool(
                    "update_raster_binding",
                    {
                        "logfile_path": draft_logfile,
                        "section_id": section_id,
                        "track_id": track_id,
                        "channel": channel,
                        "patch": default_patch,
                    },
                )
                _require_mcp_success(result, action="update_raster_binding")
                tool_calls.append(
                    AuthoringToolCall(
                        round=1,
                        name="update_raster_binding",
                        arguments={
                            "logfile_path": draft_logfile,
                            "section_id": section_id,
                            "track_id": track_id,
                            "channel": channel,
                            "patch": default_patch,
                        },
                    )
                )
        return tuple(tool_calls)

    async def _reconcile_packet_section_template(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        section_template: dict[str, object],
    ) -> tuple[AuthoringToolCall, ...]:
        """Apply deterministic section-template repairs after scaffold edits."""
        section_id = str(section_template.get("id", "")).strip()
        if not section_id:
            return ()
        summary_result = await session.call_tool(
            "summarize_logfile_draft",
            {"logfile_path": draft_logfile},
        )
        _require_mcp_success(summary_result, action="summarize_logfile_draft")
        summary_payload = _structured_content(summary_result)
        section_payload = next(
            (
                section
                for section in summary_payload.get("sections", [])
                if isinstance(section, dict) and str(section.get("id", "")).strip() == section_id
            ),
            None,
        )
        if not isinstance(section_payload, dict):
            return ()
        current_track_ids = section_payload.get("track_ids", [])
        current_track_kinds = section_payload.get("track_kinds", [])
        if not isinstance(current_track_ids, list) or not isinstance(current_track_kinds, list):
            return ()
        current_kinds_by_track = {
            str(track_id).strip(): str(track_kind).strip()
            for track_id, track_kind in zip(current_track_ids, current_track_kinds, strict=False)
            if str(track_id).strip()
        }
        tool_calls: list[AuthoringToolCall] = []
        for track_template in section_template.get("track_templates", []):
            if not isinstance(track_template, dict):
                continue
            track_id = str(track_template.get("id", "")).strip()
            expected_kind = str(track_template.get("kind", "")).strip()
            if not track_id or not expected_kind:
                continue
            current_kind = current_kinds_by_track.get(track_id)
            if current_kind is None:
                continue
            patch: dict[str, object] = {}
            if current_kind != expected_kind:
                patch["kind"] = expected_kind
            if "width_mm" in track_template:
                patch["width_mm"] = track_template["width_mm"]
            if "x_scale" in track_template:
                patch["x_scale"] = deepcopy(track_template["x_scale"])
            if "grid" in track_template:
                patch["grid"] = deepcopy(track_template["grid"])
            if not patch:
                continue
            result = await session.call_tool(
                "update_track",
                {
                    "logfile_path": draft_logfile,
                    "section_id": section_id,
                    "track_id": track_id,
                    "patch": patch,
                },
            )
            _require_mcp_success(result, action="update_track")
            tool_calls.append(
                AuthoringToolCall(
                    round=1,
                    name="update_track",
                    arguments={
                        "logfile_path": draft_logfile,
                        "section_id": section_id,
                        "track_id": track_id,
                        "patch": patch,
                    },
                )
            )
        return tuple(tool_calls)

    @staticmethod
    def _expected_binding_specs_for_track(
        section_template: dict[str, object],
        *,
        track_id: str,
        track_kind: str,
    ) -> list[dict[str, object]]:
        """Return normalized expected binding specs for one packet track."""
        expected_specs_by_track = section_template.get("expected_binding_specs_by_track", {})
        raw_specs = (
            expected_specs_by_track.get(track_id, [])
            if isinstance(expected_specs_by_track, dict)
            else []
        )
        specs: list[dict[str, object]] = []
        if isinstance(raw_specs, list):
            for raw_spec in raw_specs:
                if not isinstance(raw_spec, dict):
                    continue
                spec = deepcopy(raw_spec)
                spec["kind"] = str(spec.get("kind", "")).strip().lower() or (
                    "raster" if track_kind == "array" else "curve"
                )
                specs.append(spec)
        if specs:
            return specs
        expected_by_track = section_template.get("expected_bindings_by_track", {})
        raw_channels = (
            expected_by_track.get(track_id, []) if isinstance(expected_by_track, dict) else []
        )
        if not isinstance(raw_channels, list):
            return []
        for occurrence, channel in enumerate(raw_channels, start=1):
            normalized_channel = str(channel).strip()
            if not normalized_channel:
                continue
            spec: dict[str, object] = {
                "channel": normalized_channel,
                "kind": "raster" if track_kind == "array" else "curve",
            }
            if occurrence > 1:
                spec["occurrence"] = occurrence
            specs.append(spec)
        return specs

    async def _bind_expected_packet_binding(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        section_id: str,
        track_id: str,
        spec: dict[str, object],
    ) -> AuthoringToolCall:
        """Create one expected packet binding deterministically."""
        channel = str(spec.get("channel", "")).strip()
        if str(spec.get("kind", "curve")).strip().lower() == "raster":
            arguments = {
                "logfile_path": draft_logfile,
                "section_id": section_id,
                "track_id": track_id,
                "channel": channel,
            }
            for key in (
                "label",
                "style",
                "profile",
                "normalization",
                "waveform_normalization",
                "clip_percentiles",
                "interpolation",
                "show_raster",
                "raster_alpha",
                "color_limits",
                "colorbar",
                "sample_axis",
                "waveform",
            ):
                if key in spec:
                    arguments[key] = deepcopy(spec[key])
            result = await session.call_tool("bind_raster", arguments)
            _require_mcp_success(result, action="bind_raster")
            return AuthoringToolCall(round=1, name="bind_raster", arguments=arguments)

        arguments = {
            "logfile_path": draft_logfile,
            "section_id": section_id,
            "track_id": track_id,
            "channel": channel,
        }
        for key in ("binding_id", "label", "style", "scale", "header_display"):
            if key in spec:
                arguments[key] = deepcopy(spec[key])
        result = await session.call_tool("bind_curve", arguments)
        _require_mcp_success(result, action="bind_curve")
        return AuthoringToolCall(round=1, name="bind_curve", arguments=arguments)

    async def _patch_expected_packet_binding(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        section_id: str,
        track_id: str,
        spec: dict[str, object],
        bindings: list[dict[str, object]],
    ) -> AuthoringToolCall | None:
        """Patch one existing packet binding until it matches the expected subset."""
        matches = self._matching_bindings_for_spec(bindings, spec)
        if not matches:
            return None
        binding_id = str(spec.get("binding_id", "")).strip()
        target_binding: dict[str, object] | None = None
        if binding_id:
            for binding in matches:
                if str(binding.get("id", "")).strip() == binding_id:
                    target_binding = binding
                    break
        else:
            occurrence = spec.get("occurrence")
            if isinstance(occurrence, int) and occurrence >= 1:
                if len(matches) >= occurrence:
                    target_binding = matches[occurrence - 1]
            else:
                target_binding = matches[0]
        if not isinstance(target_binding, dict):
            return None
        expected_subset = self._binding_expected_subset(spec)
        patch = _merge_omitted_defaults(target_binding, expected_subset)
        if not patch:
            return None
        channel = str(spec.get("channel", "")).strip()
        if str(spec.get("kind", "curve")).strip().lower() == "raster":
            arguments = {
                "logfile_path": draft_logfile,
                "section_id": section_id,
                "track_id": track_id,
                "channel": channel,
                "patch": patch,
            }
            result = await session.call_tool("update_raster_binding", arguments)
            _require_mcp_success(result, action="update_raster_binding")
            return AuthoringToolCall(round=1, name="update_raster_binding", arguments=arguments)
        arguments = {
            "logfile_path": draft_logfile,
            "section_id": section_id,
            "track_id": track_id,
            "channel": channel,
            "patch": patch,
        }
        if binding_id:
            arguments["binding_id"] = binding_id
        result = await session.call_tool("update_curve_binding", arguments)
        _require_mcp_success(result, action="update_curve_binding")
        return AuthoringToolCall(round=1, name="update_curve_binding", arguments=arguments)

    async def _complete_packet_expected_bindings(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        blueprint: dict[str, object],
    ) -> tuple[AuthoringToolCall, ...]:
        """Fill or patch expected packet bindings deterministically."""
        summary_result = await session.call_tool(
            "summarize_logfile_draft",
            {"logfile_path": draft_logfile},
        )
        _require_mcp_success(summary_result, action="summarize_logfile_draft")
        summary_payload = _structured_content(summary_result)
        sections = {
            str(section.get("id", "")).strip(): section
            for section in summary_payload.get("sections", [])
            if isinstance(section, dict)
        }
        section_templates = [
            section
            for section in blueprint.get("section_templates", [])
            if isinstance(section, dict)
        ]
        tool_calls: list[AuthoringToolCall] = []
        for section_template in section_templates:
            section_id = str(section_template.get("id", "")).strip()
            section_payload = sections.get(section_id)
            if not section_id or not isinstance(section_payload, dict):
                continue
            track_ids = section_payload.get("track_ids", [])
            track_kinds = section_payload.get("track_kinds", [])
            if not isinstance(track_ids, list) or not isinstance(track_kinds, list):
                continue
            track_kind_by_id = {
                str(track_id).strip(): str(track_kind).strip()
                for track_id, track_kind in zip(track_ids, track_kinds, strict=False)
                if str(track_id).strip()
            }
            for track_id, current_track_kind in track_kind_by_id.items():
                current_track_kind = track_kind_by_id.get(track_id)
                if current_track_kind is None:
                    continue
                expected_specs = self._expected_binding_specs_for_track(
                    section_template,
                    track_id=track_id,
                    track_kind=current_track_kind,
                )
                if not expected_specs:
                    continue
                requested_channels = list(
                    dict.fromkeys(
                        str(spec.get("channel", "")).strip()
                        for spec in expected_specs
                        if str(spec.get("channel", "")).strip()
                    )
                )
                availability_result = await session.call_tool(
                    "check_channel_availability",
                    {
                        "logfile_path": draft_logfile,
                        "section_id": section_id,
                        "requested_channels": requested_channels,
                    },
                )
                _require_mcp_success(
                    availability_result,
                    action="check_channel_availability",
                )
                availability_payload = _structured_content(availability_result)
                found_channels = {
                    str(channel).strip().upper()
                    for channel in availability_payload.get("found_channels", [])
                    if str(channel).strip()
                }
                inspect_result = await session.call_tool(
                    "inspect_track_bindings",
                    {
                        "logfile_path": draft_logfile,
                        "section_id": section_id,
                        "track_id": track_id,
                    },
                )
                _require_mcp_success(inspect_result, action="inspect_track_bindings")
                inspect_payload = _structured_content(inspect_result)
                bindings = inspect_payload.get("bindings", [])
                if not isinstance(bindings, list):
                    bindings = []
                needs_full_rebuild = len(
                    {
                        str(spec.get("channel", "")).strip().upper()
                        for spec in expected_specs
                        if str(spec.get("channel", "")).strip()
                    }
                ) < len(expected_specs)
                if needs_full_rebuild:
                    if bindings:
                        clear_arguments = {
                            "logfile_path": draft_logfile,
                            "section_id": section_id,
                            "track_id": track_id,
                        }
                        clear_result = await session.call_tool(
                            "clear_track_bindings",
                            clear_arguments,
                        )
                        _require_mcp_success(
                            clear_result,
                            action="clear_track_bindings",
                        )
                        tool_calls.append(
                            AuthoringToolCall(
                                round=1,
                                name="clear_track_bindings",
                                arguments=clear_arguments,
                            )
                        )
                    for spec in expected_specs:
                        channel_name = str(spec.get("channel", "")).strip().upper()
                        if channel_name not in found_channels:
                            continue
                        tool_calls.append(
                            await self._bind_expected_packet_binding(
                                session=session,
                                draft_logfile=draft_logfile,
                                section_id=section_id,
                                track_id=track_id,
                                spec=spec,
                            )
                        )
                    continue
                for spec in expected_specs:
                    channel_name = str(spec.get("channel", "")).strip().upper()
                    if channel_name not in found_channels:
                        continue
                    ok, _ = self._binding_matches_expected_spec(bindings, spec)
                    if ok:
                        continue
                    patch_call = await self._patch_expected_packet_binding(
                        session=session,
                        draft_logfile=draft_logfile,
                        section_id=section_id,
                        track_id=track_id,
                        spec=spec,
                        bindings=bindings,
                    )
                    if patch_call is not None:
                        tool_calls.append(patch_call)
                        continue
                    bind_call = await self._bind_expected_packet_binding(
                        session=session,
                        draft_logfile=draft_logfile,
                        section_id=section_id,
                        track_id=track_id,
                        spec=spec,
                    )
                    tool_calls.append(bind_call)
        return tuple(tool_calls)

    async def _execute_authoring_plan(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        request_text: str,
        plan: AuthoringPlanResult,
        prompt_text: str,
        tool_definitions: list[FunctionToolDefinition],
        request_max_rounds: int,
        seed_context: str | None = None,
    ) -> tuple[ProviderRunResult, tuple[ExecutedAuthoringPhase, ...], AuthoringRunState]:
        """Execute one staged authoring plan and verify each phase deterministically."""
        blueprint = (
            {}
            if plan.packet_blueprint_id is None
            else packet_blueprint_spec(plan.packet_blueprint_id)
        )
        phase_summaries: list[ExecutedAuthoringPhase] = []
        flattened_tool_trace: list[AuthoringToolCall] = []
        completed_objectives: list[str] = []
        blocked_objectives: list[str] = []
        last_verification: dict[str, object] = {}

        async def call_mcp_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
            allowed_names = _phase_allowed_tool_names(current_phase)
            if name not in allowed_names:
                payload = {
                    "is_error": True,
                    "error": (
                        f"Tool {name!r} is not available during phase "
                        f"{current_phase.id!r}; use the phase-appropriate tool family."
                    ),
                }
                phase_mutation_errors.append(f"{name}: {_tool_payload_error_text(payload)}")
                return payload
            tool_result = await session.call_tool(name, arguments)
            payload = self.runtime.tool_result_payload(tool_result)
            error_text = _tool_payload_error_text(payload)
            if error_text is not None and name not in _PHASE_READ_ONLY_TOOLS:
                phase_mutation_errors.append(f"{name}: {error_text}")
            return payload

        for phase in plan.phases:
            current_phase = phase
            phase_mutation_errors: list[str] = []
            summary_result = await session.call_tool(
                "summarize_logfile_draft",
                {"logfile_path": draft_logfile},
            )
            _require_mcp_success(summary_result, action="summarize_logfile_draft")
            current_summary = _structured_content(summary_result)
            phase_baseline_text: str | None = None
            if any(
                str(spec.get("kind", "")).strip() == "changes_detected"
                for spec in phase.success_check_specs
            ):
                draft_path = self.runtime.server_root / draft_logfile
                if draft_path.exists():
                    phase_baseline_text = draft_path.read_text(encoding="utf-8")
            before_verification_context = await self._phase_verification_context(
                session=session,
                draft_logfile=draft_logfile,
                phase=phase,
                request_text=request_text,
            )
            before_state = self._phase_success_state(
                phase=phase,
                draft_summary=current_summary,
                verification_context=before_verification_context,
            )
            if before_state["ok"]:
                preview_kind, preview_target, preview_png = await self._capture_phase_preview(
                    session=session,
                    draft_logfile=draft_logfile,
                    phase=phase,
                    draft_summary=current_summary,
                )
                phase_summaries.append(
                    ExecutedAuthoringPhase(
                        id=phase.id,
                        kind=phase.kind,
                        summary=phase.summary,
                        status="completed",
                        tool_trace=(),
                        verification=before_state,
                        preview_kind=preview_kind,
                        preview_target=preview_target,
                        preview_png=preview_png,
                    )
                )
                completed_objectives.append(phase.summary)
                last_verification = before_state
                continue

            phase_result: ProviderRunResult | None = None
            blocked_reasons: tuple[str, ...] = ()
            try:
                if phase.kind == "header_scaffold":
                    archetype_id = str(phase.metadata.get("header_archetype", "")).strip()
                    if archetype_id:
                        result = await session.call_tool(
                            "apply_header_archetype",
                            {
                                "logfile_path": draft_logfile,
                                "archetype_id": archetype_id,
                                "preserve_existing_values": True,
                            },
                        )
                        _require_mcp_success(result, action="apply_header_archetype")
                        phase_result = ProviderRunResult(
                            final_text="Applied deterministic packet header scaffold.",
                            tool_trace=(
                                AuthoringToolCall(
                                    round=1,
                                    name="apply_header_archetype",
                                    arguments={
                                        "logfile_path": draft_logfile,
                                        "archetype_id": archetype_id,
                                        "preserve_existing_values": True,
                                    },
                                ),
                            ),
                        )
                elif phase.kind == "header_fill":
                    phase_result = await self._apply_packet_header_fill(
                        session=session,
                        draft_logfile=draft_logfile,
                        request_text=request_text,
                    )
                elif phase.kind == "remarks":
                    phase_result = await self._apply_packet_remarks(
                        session=session,
                        draft_logfile=draft_logfile,
                        request_text=request_text,
                    )
                elif phase.kind == "section_replication":
                    section_template = phase.metadata.get("section_template", {})
                    source_slot_mapping = _parse_source_slot_mapping(request_text)
                    if not isinstance(section_template, dict):
                        blocked_reasons = ("No section template was available for replication.",)
                    else:
                        source_path = source_slot_mapping.get(
                            str(section_template.get("source_slot", "")).strip().lower()
                        )
                        result = await session.call_tool(
                            "replicate_section_structure",
                            {
                                "logfile_path": draft_logfile,
                                "source_section_id": str(
                                    section_template.get("replicates_from", "")
                                ).strip(),
                                "target_section_id": str(section_template.get("id", "")).strip(),
                                "source_path": source_path,
                                "title": section_template.get("title"),
                                "subtitle": section_template.get("subtitle"),
                                "include_bindings": False,
                                "overwrite": True,
                            },
                        )
                        _require_mcp_success(result, action="replicate_section_structure")
                        phase_result = ProviderRunResult(
                            final_text="Replicated the packet section scaffold.",
                            tool_trace=(
                                AuthoringToolCall(
                                    round=1,
                                    name="replicate_section_structure",
                                    arguments={
                                        "logfile_path": draft_logfile,
                                        "source_section_id": str(
                                            section_template.get("replicates_from", "")
                                        ).strip(),
                                        "target_section_id": str(
                                            section_template.get("id", "")
                                        ).strip(),
                                        "source_path": source_path,
                                        "title": section_template.get("title"),
                                        "subtitle": section_template.get("subtitle"),
                                        "include_bindings": False,
                                        "overwrite": True,
                                    },
                                ),
                            ),
                        )
                elif phase.kind == "verification":
                    phase_result = ProviderRunResult(
                        final_text="Verified the draft state.",
                        tool_trace=(),
                    )
                else:
                    phase_budget = phase.max_rounds or request_max_rounds
                    phase_message = (
                        f"Authoring phase `{phase.id}`.\n"
                        f"Phase summary: {phase.summary}\n"
                        f"Phase instructions:\n{phase.instructions}\n\n"
                        "Complete only this phase. Do not redesign already-complete "
                        "draft objects. Use MCP tools only.\n\n"
                    )
                    if seed_context:
                        phase_message += f"Seed context: {seed_context}\n\n"
                    phase_message += (
                        f"Current draft context:\n{json.dumps(current_summary, indent=2)}\n\n"
                        f"Original request:\n{request_text}"
                    )
                    phase_tool_definitions = [
                        tool
                        for tool in tool_definitions
                        if tool.name in _phase_allowed_tool_names(phase)
                    ]
                    phase_result = await self.backend.run_authoring(
                        instructions=prompt_text,
                        initial_user_message=phase_message,
                        tool_definitions=phase_tool_definitions,
                        tool_caller=call_mcp_tool,
                        max_rounds=phase_budget,
                    )
                    if phase.kind == "bindings_raster":
                        raster_defaults_trace = await self._apply_packet_raster_defaults(
                            session=session,
                            draft_logfile=draft_logfile,
                            blueprint=blueprint,
                        )
                        if raster_defaults_trace:
                            phase_result = ProviderRunResult(
                                final_text=phase_result.final_text,
                                tool_trace=phase_result.tool_trace + raster_defaults_trace,
                                report_facts=phase_result.report_facts,
                            )
            except RuntimeError as exc:
                if "exceeded" in str(exc).lower():
                    blocked_reasons = (
                        f"Phase `{phase.id}` exceeded its round budget before verification passed.",
                    )
                    phase_result = ProviderRunResult(
                        final_text=f"Phase `{phase.id}` blocked on round budget exhaustion.",
                        tool_trace=(),
                    )
                else:
                    raise

            if phase.kind == "section_scaffold":
                section_template = phase.metadata.get("section_template", {})
                if isinstance(section_template, dict):
                    reconcile_trace = await self._reconcile_packet_section_template(
                        session=session,
                        draft_logfile=draft_logfile,
                        section_template=section_template,
                    )
                    if reconcile_trace:
                        if phase_result is None:
                            phase_result = ProviderRunResult(
                                final_text="Applied deterministic section-template fixes.",
                                tool_trace=reconcile_trace,
                            )
                        else:
                            phase_result = ProviderRunResult(
                                final_text=phase_result.final_text,
                                tool_trace=phase_result.tool_trace + reconcile_trace,
                                report_facts=phase_result.report_facts,
                            )
            if phase.kind == "bindings_raster":
                completion_trace = await self._complete_packet_expected_bindings(
                    session=session,
                    draft_logfile=draft_logfile,
                    blueprint=blueprint,
                )
                if completion_trace:
                    if phase_result is None:
                        phase_result = ProviderRunResult(
                            final_text="Applied deterministic packet binding completion.",
                            tool_trace=completion_trace,
                        )
                    else:
                        phase_result = ProviderRunResult(
                            final_text=phase_result.final_text,
                            tool_trace=phase_result.tool_trace + completion_trace,
                            report_facts=phase_result.report_facts,
                        )
                raster_defaults_trace = await self._apply_packet_raster_defaults(
                    session=session,
                    draft_logfile=draft_logfile,
                    blueprint=blueprint,
                )
                if raster_defaults_trace:
                    if phase_result is None:
                        phase_result = ProviderRunResult(
                            final_text="Applied deterministic packet raster defaults.",
                            tool_trace=raster_defaults_trace,
                        )
                    else:
                        phase_result = ProviderRunResult(
                            final_text=phase_result.final_text,
                            tool_trace=phase_result.tool_trace + raster_defaults_trace,
                            report_facts=phase_result.report_facts,
                        )

            post_summary_result = await session.call_tool(
                "summarize_logfile_draft",
                {"logfile_path": draft_logfile},
            )
            _require_mcp_success(post_summary_result, action="summarize_logfile_draft")
            post_summary = _structured_content(post_summary_result)
            validation_payload: dict[str, object] | None = None
            if any(
                str(spec.get("kind", "")).strip() == "validation_valid"
                for spec in phase.success_check_specs
            ):
                validation_result = await session.call_tool(
                    "validate_logfile",
                    {"logfile_path": draft_logfile},
                )
                _require_mcp_success(validation_result, action="validate_logfile")
                validation_payload = _structured_content(validation_result)
            preview_kind, preview_target, preview_png = await self._capture_phase_preview(
                session=session,
                draft_logfile=draft_logfile,
                phase=phase,
                draft_summary=post_summary,
            )
            after_verification_context = await self._phase_verification_context(
                session=session,
                draft_logfile=draft_logfile,
                phase=phase,
                request_text=request_text,
                previous_draft_text=phase_baseline_text,
            )
            phase_tool_trace = () if phase_result is None else phase_result.tool_trace
            if any(
                str(spec.get("kind", "")).strip() == "tool_outcomes_match"
                for spec in phase.success_check_specs
            ):
                after_verification_context["tool_outcomes"] = await self._verify_tool_outcomes(
                    session=session,
                    draft_logfile=draft_logfile,
                    draft_summary=post_summary,
                    tool_trace=phase_tool_trace,
                    change_summary=after_verification_context.get("change_summary")
                    if isinstance(after_verification_context.get("change_summary"), dict)
                    else None,
                )
            after_state = self._phase_success_state(
                phase=phase,
                draft_summary=post_summary,
                validation=validation_payload,
                preview_renderable=preview_png is not None,
                verification_context=after_verification_context,
            )
            if after_state["ok"] and not phase_mutation_errors:
                blocked_reasons = ()
            elif not blocked_reasons:
                before_snapshot = json.dumps(before_state["checks"], sort_keys=True, default=str)
                after_snapshot = json.dumps(after_state["checks"], sort_keys=True, default=str)
                if before_snapshot == after_snapshot:
                    blocked_reasons = (
                        "Phase made no verifiable progress toward its success checks.",
                    )
                else:
                    blocked_reasons = tuple(
                        (
                            f"Unmet success check `{check.get('kind', '')}`: {check.get('detail')}."
                            if str(check.get("detail", "")).strip()
                            else f"Unmet success check `{check.get('kind', '')}`."
                        )
                        for check in after_state["checks"]
                        if not bool(check.get("ok"))
                    )
            if phase_mutation_errors:
                blocked_reasons = tuple(blocked_reasons) + tuple(
                    f"MCP mutation error: {error}" for error in phase_mutation_errors
                )

            status = "completed" if after_state["ok"] and not blocked_reasons else "blocked"
            tool_trace = phase_tool_trace
            phase_summary = ExecutedAuthoringPhase(
                id=phase.id,
                kind=phase.kind,
                summary=phase.summary,
                status=status,
                tool_trace=tool_trace,
                verification=after_state,
                blocked_reasons=blocked_reasons,
                preview_kind=preview_kind,
                preview_target=preview_target,
                preview_png=preview_png,
            )
            phase_summaries.append(phase_summary)
            flattened_tool_trace.extend(tool_trace)
            last_verification = after_state
            if status == "completed":
                completed_objectives.append(phase.summary)
                continue
            blocked_objectives.append(phase.summary)
            break

        run_state = self._run_state_from_summary(
            draft_summary=post_summary if "post_summary" in locals() else current_summary,
            objectives=plan.run_state.objectives,
            completed_objectives=tuple(completed_objectives),
            blocked_objectives=tuple(blocked_objectives),
            last_verification=last_verification,
        )
        report_facts = {
            "completed": [
                phase.summary for phase in phase_summaries if phase.status == "completed"
            ],
            "not_done": [phase.summary for phase in phase_summaries if phase.status == "blocked"],
            "reasons": [reason for phase in phase_summaries for reason in phase.blocked_reasons],
        }
        final_text = (
            "Authoring plan completed."
            if not blocked_objectives
            else "Authoring plan stopped on a blocked phase."
        )
        return (
            ProviderRunResult(
                final_text=final_text,
                tool_trace=tuple(flattened_tool_trace),
                report_facts=report_facts,
            ),
            tuple(phase_summaries),
            run_state,
        )

    async def _collect_authoring_context(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        request_text: str,
        existing: AuthoringDocumentSpec,
        summary: dict[str, object],
    ) -> AuthoringContextSnapshot:
        """Inspect all deterministic context needed before intent extraction."""
        issues: list[AuthoringContextIssue] = []
        heading_slots: dict[str, object] = {}
        heading_result = await session.call_tool(
            "inspect_heading_slots",
            {"logfile_path": draft_logfile},
        )
        heading_error = _mcp_error_text(heading_result)
        if heading_error is None:
            heading_slots = _structured_content(heading_result)
        else:
            issues.append(
                AuthoringContextIssue(
                    path="header",
                    code="header_context_unavailable",
                    message=heading_error,
                )
            )

        source_slots = _request_source_paths(
            request_text,
            _parse_source_slot_mapping(request_text),
        )
        source_requests: dict[str, tuple[str, str]] = {}
        for source_path in source_slots.values():
            normalized = source_path.strip()
            if not normalized:
                continue
            path_key = normalized.replace("\\", "/").removeprefix("./").lower()
            if path_key not in source_requests:
                source_requests[path_key] = (
                    normalized,
                    _source_format_for_path(normalized),
                )
        for section in summary.get("sections", []):
            if not isinstance(section, Mapping):
                continue
            source_path = str(section.get("source_path", "")).strip()
            if not source_path:
                continue
            path_key = source_path.replace("\\", "/").removeprefix("./").lower()
            if path_key not in source_requests:
                source_requests[path_key] = (
                    source_path,
                    str(section.get("source_format", "auto")).strip() or "auto",
                )

        source_inspections: dict[str, Mapping[str, object]] = {}
        for source_path, source_format in source_requests.values():
            inspection_result = await session.call_tool(
                "inspect_data_source",
                {"source_path": source_path, "source_format": source_format},
            )
            inspection_error = _mcp_error_text(inspection_result)
            if inspection_error is not None:
                issues.append(
                    AuthoringContextIssue(
                        path=f"sources[{source_path}]",
                        code="source_context_unavailable",
                        message=inspection_error,
                    )
                )
                continue
            source_inspections[source_path] = _structured_content(inspection_result)

        return build_authoring_context_snapshot(
            draft_logfile=draft_logfile,
            existing=existing,
            summary=summary,
            source_inspections=source_inspections,
            requested_source_slots=source_slots,
            header_slots=heading_slots,
            issues=issues,
        )

    async def _extract_desired_state(
        self,
        *,
        request_text: str,
        draft_logfile: str,
        existing: AuthoringDocumentSpec,
        context_snapshot: AuthoringContextSnapshot,
        max_rounds: int,
    ) -> tuple[ProviderRunResult, AuthoringDocumentIntent | None]:
        """Ask a typed-state capable provider for one validated desired state."""
        submitted: AuthoringDocumentIntent | None = None
        submission: AuthoringIntentSubmission | None = None
        submission_attempts = 0
        coverage_errors: list[str] = []
        request_manifest = build_request_manifest(request_text)

        async def submit_intent(
            name: str,
            arguments: dict[str, object],
        ) -> dict[str, object]:
            """Validate the provider submission without mutating the draft."""
            nonlocal submitted, submission, submission_attempts, coverage_errors
            if name != "submit_authoring_intent":
                return {
                    "is_error": True,
                    "error": (
                        "Only submit_authoring_intent is available in desired-state "
                        "extraction mode."
                    ),
                }
            submission_attempts += 1
            if submission_attempts > 2:
                return {
                    "is_error": True,
                    "error": (
                        "Only one initial submission and one correction submission are "
                        "allowed. Stop and report the unresolved coverage errors."
                    ),
                }
            try:
                candidate = AuthoringIntentSubmission.model_validate(arguments)
            except Exception as exc:  # Pydantic gives provider-actionable details.
                return {
                    "is_error": True,
                    "error": (
                        f"Invalid AuthoringIntentSubmission: {exc}. Include an `intent` "
                        "object and one coverage entry for every request item."
                    ),
                }
            coverage_errors = validate_intent_coverage(
                request_manifest,
                candidate.coverage,
            )
            if coverage_errors:
                return {
                    "is_error": True,
                    "error": (
                        "Request coverage is incomplete or invalid. Submit one correction "
                        "with the same intent plus corrected coverage:\n- "
                        + "\n- ".join(coverage_errors)
                    ),
                }
            submission = candidate
            submitted = candidate.intent
            return {
                "accepted": True,
                "message": (
                    "Typed desired state and request coverage validated. The deterministic "
                    "planner will now resolve references and execute it."
                ),
            }

        context = {
            "draft_logfile": draft_logfile,
            "request": request_text,
            "request_manifest": request_manifest.model_dump(mode="json"),
            "current_document": existing.model_dump(mode="json"),
            "authoring_context": context_snapshot.model_dump(mode="json"),
        }
        instructions = (
            "You are the desired-state extraction stage of wellplot authoring. "
            "Do not invent packet templates and do not call mutation tools. Read the "
            "current document and source context, then call submit_authoring_intent "
            "with only the requested changes and complete request coverage. You may "
            "submit once initially and once more only when the tool reports a coverage "
            "error. Omit fields that should be "
            "preserved. Use the explicit clear or remove intent objects when the user "
            "asks to clear or remove something. Preserve explicit labels, scales, "
            "colors, line styles, widths, and raster settings exactly. If the request "
            "references an unavailable or ambiguous channel, still describe the request; "
            "the deterministic resolver will block it and report why."
        )
        initial_message = (
            "Submit one typed desired state and coverage report for this request. Do not "
            "describe a sequence of MCP calls. The submission is validated before any "
            "mutation occurs. Every request item must have exactly one coverage entry. "
            "Use `mapped` or `preserved` with intent paths, and use `unsupported` or "
            "`inconsistent` only with a concise reason.\n\n"
            f"Context:\n{json.dumps(context, indent=2, default=str)}\n\n"
            f"AuthoringIntentSubmission schema:\n"
            f"{json.dumps(AuthoringIntentSubmission.model_json_schema(), indent=2, default=str)}"
        )
        tool_definition = FunctionToolDefinition(
            name="submit_authoring_intent",
            description=(
                "Submit one validated partial desired state and one coverage entry for "
                "every request item. Omit fields that must be preserved."
            ),
            parameters=AuthoringIntentSubmission.model_json_schema(),
        )
        provider_result = await self.backend.run_authoring(
            instructions=instructions,
            initial_user_message=initial_message,
            tool_definitions=[tool_definition],
            tool_caller=submit_intent,
            max_rounds=min(max_rounds, 3),
        )
        report_facts = dict(getattr(provider_result, "report_facts", {}))
        report_facts["request_manifest"] = request_manifest.model_dump(mode="json")
        if submission is not None:
            report_facts["request_coverage"] = [
                entry.model_dump(mode="json") for entry in submission.coverage
            ]
            report_facts["request_inconsistencies"] = [
                f"{entry.request_item_id}: {entry.reason}"
                for entry in submission.coverage
                if entry.status in {"unsupported", "inconsistent"} and entry.reason
            ]
        elif coverage_errors:
            report_facts["reasons"] = list(report_facts.get("reasons", [])) + [
                "Request coverage validation failed: " + "; ".join(coverage_errors)
            ]
        return (
            ProviderRunResult(
                final_text=provider_result.final_text,
                tool_trace=provider_result.tool_trace,
                report_facts=report_facts,
            ),
            submitted,
        )

    @staticmethod
    def _typed_save_payload(document: AuthoringDocumentSpec) -> dict[str, object]:
        """Validate and serialize one typed document before MCP persistence."""
        envelope = {
            "version": 1,
            "name": document.name,
            "document": document.model_dump(mode="json"),
        }
        validated = authoring_document_from_mapping(envelope)
        # Exercise the same canonical serializer used for persisted documents.  The
        # returned envelope keeps the MCP boundary explicit and JSON-compatible.
        authoring_document_to_yaml(validated)
        return {
            "version": 1,
            "name": validated.name,
            "document": validated.model_dump(mode="json"),
        }

    async def _save_typed_document(
        self,
        *,
        session: McpSessionProtocol,
        document: AuthoringDocumentSpec,
        output_path: str,
        attempts: int,
    ) -> tuple[str | None, bool]:
        """Persist one validated typed document with a bounded idempotent retry."""
        try:
            document_payload = self._typed_save_payload(document)
        except Exception as exc:
            return f"local typed document validation failed: {exc}", False

        last_error: str | None = None
        saw_transport_failure = False
        for _attempt in range(max(1, attempts)):
            try:
                result = await session.call_tool(
                    "save_authoring_document",
                    {
                        "document": document_payload,
                        "output_path": output_path,
                        "overwrite": True,
                        "base_dir": str(Path(output_path).parent),
                    },
                )
                payload_error = _tool_payload_error_text(self.runtime.tool_result_payload(result))
                if payload_error is None:
                    return None, saw_transport_failure
                last_error = payload_error
            except Exception as exc:
                saw_transport_failure = True
                last_error = f"{type(exc).__name__}: {exc}"

        total_attempts = max(1, attempts)
        return (
            f"save_authoring_document failed after {total_attempts} attempt(s): "
            f"{last_error or 'unknown MCP failure'}",
            saw_transport_failure,
        )

    async def _capture_typed_phase_previews(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        execution: AuthoringExecutionResult,
    ) -> tuple[dict[AuthoringOperationPhase, _TypedPhasePreview], tuple[str, ...]]:
        """Render each typed checkpoint from a temporary same-directory logfile."""
        previews: dict[AuthoringOperationPhase, _TypedPhasePreview] = {}
        warnings: list[str] = []
        draft_path = Path(draft_logfile)
        for index, checkpoint in enumerate(execution.phase_summaries):
            staged_path = draft_path.parent / (
                f".{draft_path.name}.phase-{index}-{uuid4().hex}.log.yaml"
            )
            staged_logfile = staged_path.as_posix()
            try:
                save_error, _ = await self._save_typed_document(
                    session=session,
                    document=checkpoint.document,
                    output_path=staged_logfile,
                    attempts=1,
                )
                if save_error is not None:
                    message = (
                        f"Phase `{checkpoint.phase.value}` preview staging failed: {save_error}"
                    )
                    previews[checkpoint.phase] = _TypedPhasePreview(error=message)
                    warnings.append(message)
                    continue

                if checkpoint.phase == AuthoringOperationPhase.REPORT:
                    preview_result = await session.call_tool(
                        "preview_logfile_png",
                        {
                            "logfile_path": staged_logfile,
                            "page_index": 0,
                            "dpi": 72,
                            "include_report_pages": True,
                        },
                    )
                    _require_mcp_success(preview_result, action="preview_logfile_png")
                    previews[checkpoint.phase] = _TypedPhasePreview(
                        kind="report",
                        png=self.runtime.image_bytes(preview_result),
                    )
                    continue

                if not checkpoint.document.sections:
                    raise RuntimeError("the checkpoint has no section to preview")
                section_id = checkpoint.document.sections[0].id
                preview_result = await session.call_tool(
                    "preview_section_png",
                    {
                        "logfile_path": staged_logfile,
                        "section_id": section_id,
                        "dpi": 72,
                    },
                )
                _require_mcp_success(preview_result, action="preview_section_png")
                previews[checkpoint.phase] = _TypedPhasePreview(
                    kind="section",
                    target=section_id,
                    png=self.runtime.image_bytes(preview_result),
                )
            except Exception as exc:
                message = (
                    f"Phase `{checkpoint.phase.value}` preview failed: {type(exc).__name__}: {exc}"
                )
                previews[checkpoint.phase] = _TypedPhasePreview(error=message)
                warnings.append(message)
            finally:
                staged_path.unlink(missing_ok=True)
        return previews, tuple(warnings)

    @staticmethod
    def _typed_phase_summaries(
        *,
        plan: AuthoringPlanResult,
        execution: AuthoringExecutionResult,
        phase_previews: Mapping[AuthoringOperationPhase, _TypedPhasePreview] | None = None,
    ) -> tuple[ExecutedAuthoringPhase, ...]:
        """Convert executor checkpoints into the public agent phase contract."""
        captured_previews = {} if phase_previews is None else phase_previews
        phase_by_operation_ids = {
            tuple(phase.metadata.get("operation_ids", [])): phase for phase in plan.phases
        }
        summaries: list[ExecutedAuthoringPhase] = []
        for checkpoint in execution.phase_summaries:
            operation_ids = tuple(checkpoint.operation_ids)
            plan_phase = phase_by_operation_ids.get(operation_ids)
            phase_id = (
                plan_phase.id if plan_phase is not None else f"desired-{checkpoint.phase.value}"
            )
            phase_kind = (
                plan_phase.kind
                if plan_phase is not None
                else f"desired_state_{checkpoint.phase.value}"
            )
            phase_summary = (
                plan_phase.summary
                if plan_phase is not None
                else f"Apply typed {checkpoint.phase.value} desired-state operations."
            )
            status = checkpoint.status.value
            phase_preview = captured_previews.get(checkpoint.phase, _TypedPhasePreview())
            blocked_reasons = (
                ()
                if status == AuthoringExecutionStatus.COMPLETED
                else (
                    checkpoint.preview_error
                    or f"Typed {checkpoint.phase.value} phase did not complete.",
                )
            )
            summaries.append(
                ExecutedAuthoringPhase(
                    id=phase_id,
                    kind=phase_kind,
                    summary=phase_summary,
                    status=(
                        "completed" if status == AuthoringExecutionStatus.COMPLETED else "blocked"
                    ),
                    tool_trace=(),
                    verification={
                        "ok": status == AuthoringExecutionStatus.COMPLETED,
                        "operation_ids": list(operation_ids),
                        "applied_count": checkpoint.applied_count,
                        **(
                            {"preview_error": phase_preview.error}
                            if phase_preview.error is not None
                            else {}
                        ),
                    },
                    blocked_reasons=blocked_reasons,
                    preview_kind=phase_preview.kind,
                    preview_target=phase_preview.target,
                    preview_png=phase_preview.png,
                )
            )
        return tuple(summaries)

    def _typed_transport_blocked_result(
        self,
        *,
        draft_logfile: str,
        request_kind: str,
        goal: str,
        example_id: str | None,
        source_logfile_path: str | None,
        baseline_draft_text: str,
        provider_result: ProviderRunResult,
        plan: AuthoringPlanResult | None,
        phase_summaries: tuple[ExecutedAuthoringPhase, ...],
        run_state: AuthoringRunState,
        reason: str,
    ) -> AuthoringResult:
        """Return a structured result when MCP transport prevents finalization."""
        report_facts = dict(provider_result.report_facts)
        report_facts["warnings"] = list(report_facts.get("warnings", [])) + [reason]
        report_facts["reasons"] = list(report_facts.get("reasons", [])) + [reason]
        report_facts["not_done"] = list(report_facts.get("not_done", [])) + [
            "Persist and finalize the typed desired-state document."
        ]
        report_facts["next_help"] = list(report_facts.get("next_help", [])) + [
            "Retry the request after the local MCP server connection is available."
        ]
        output_path = self.runtime.server_root / draft_logfile
        draft_text = (
            output_path.read_text(encoding="utf-8") if output_path.exists() else baseline_draft_text
        )
        return AuthoringResult(
            provider=self.backend.provider,
            model=self.backend.model,
            credential_source=self.backend.credential_source,
            request_kind=request_kind,
            example_id=example_id,
            source_logfile_path=source_logfile_path,
            goal=goal,
            draft_logfile=draft_logfile,
            server_root=self.runtime.server_root,
            tool_trace=provider_result.tool_trace,
            final_text="Typed desired-state execution was blocked by MCP transport.",
            validation={"valid": False, "message": reason},
            draft_summary={},
            inspect_summary={},
            change_summary={"summary_lines": []},
            draft_text=draft_text,
            report_preview_png=b"",
            section_preview_png=b"",
            plan=plan,
            phase_summaries=phase_summaries,
            run_state=run_state,
            user_report=_build_user_report(
                request_text=goal,
                validation={"valid": False, "message": reason},
                draft_summary={},
                change_summary={"summary_lines": []},
                tool_trace=provider_result.tool_trace,
                report_facts=report_facts,
            ),
        )

    async def _run_desired_state_workflow(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        request_kind: str,
        request_text: str,
        example_id: str | None,
        source_logfile_path: str | None,
        baseline_draft_text: str,
        max_rounds: int,
        desired_state: AuthoringDocumentIntent | Mapping[str, object] | None = None,
    ) -> AuthoringResult:
        """Resolve, reconcile, execute, and persist one desired-state workflow."""
        summary_result = await session.call_tool(
            "summarize_logfile_draft",
            {"logfile_path": draft_logfile},
        )
        _require_mcp_success(summary_result, action="summarize_logfile_draft")
        summary = _structured_content(summary_result)
        inspect_result = await session.call_tool(
            "inspect_logfile",
            {"logfile_path": draft_logfile},
        )
        _require_mcp_success(inspect_result, action="inspect_logfile")
        output_path = self.runtime.server_root / draft_logfile
        existing = load_authoring_document(output_path, allowed_root=self.runtime.server_root)
        context_snapshot = await self._collect_authoring_context(
            session=session,
            draft_logfile=draft_logfile,
            request_text=request_text,
            existing=existing,
            summary=summary,
        )
        available_channels = {
            section.section_id: [
                candidate.model_dump(mode="json") for candidate in section.available_channels
            ]
            for section in context_snapshot.sections
        }

        if desired_state is None:
            provider_result, intent = await self._extract_desired_state(
                request_text=request_text,
                draft_logfile=draft_logfile,
                existing=existing,
                context_snapshot=context_snapshot,
                max_rounds=max_rounds,
            )
        else:
            intent = self._coerce_desired_state(desired_state)
            provider_result = ProviderRunResult(
                final_text="Using caller-supplied typed desired state.",
                tool_trace=(),
                report_facts={
                    "context_issues": [
                        issue.model_dump(mode="json") for issue in context_snapshot.issues
                    ],
                },
            )

        if intent is None:
            provider_result = ProviderRunResult(
                final_text="Desired-state extraction did not produce a valid submission.",
                tool_trace=provider_result.tool_trace,
                report_facts={
                    "not_done": ["Extract a typed desired state from the request."],
                    "reasons": ["The provider did not submit a valid AuthoringDocumentIntent."],
                    "next_help": [
                        "Retry with a request that identifies the requested object fields "
                        "and values explicitly."
                    ],
                },
            )
            return await self._finalize_result(
                session=session,
                draft_logfile=draft_logfile,
                request_kind=request_kind,
                goal=request_text,
                example_id=example_id,
                source_logfile_path=source_logfile_path,
                baseline_draft_text=baseline_draft_text,
                provider_result=provider_result,
            )

        plan = self._plan_from_desired_state(
            intent,
            existing=existing,
            available_channels=available_channels,
        )
        if plan.reconciliation_plan is None or not plan.reconciliation_plan.ready:
            reasons = plan.blocked_reasons or ("Typed desired-state resolution was blocked.",)
            provider_result = ProviderRunResult(
                final_text="Desired-state planning was blocked before mutation.",
                tool_trace=provider_result.tool_trace,
                report_facts={
                    "not_done": [phase.summary for phase in plan.phases]
                    or ["Resolve and reconcile the typed desired state."],
                    "reasons": list(reasons),
                    "next_help": [
                        "Correct the blocked references or provide the missing source "
                        "channel and try again."
                    ],
                },
            )
            return await self._finalize_result(
                session=session,
                draft_logfile=draft_logfile,
                request_kind=request_kind,
                goal=request_text,
                example_id=example_id,
                source_logfile_path=source_logfile_path,
                baseline_draft_text=baseline_draft_text,
                provider_result=provider_result,
                plan=plan,
            )

        execution = execute_authoring_plan(
            AuthoringService(existing),
            plan.reconciliation_plan,
        )
        phase_previews, phase_preview_warnings = await self._capture_typed_phase_previews(
            session=session,
            draft_logfile=draft_logfile,
            execution=execution,
        )
        phase_summaries = self._typed_phase_summaries(
            plan=plan,
            execution=execution,
            phase_previews=phase_previews,
        )
        save_error: str | None = None
        save_transport_failure = False
        if execution.success:
            save_error, save_transport_failure = await self._save_typed_document(
                session=session,
                document=execution.document,
                output_path=draft_logfile,
                attempts=2,
            )

        completed = [phase.summary for phase in phase_summaries if phase.status == "completed"]
        blocked = [phase.summary for phase in phase_summaries if phase.status != "completed"]
        reasons = list(execution.errors)
        if save_error:
            reasons.append(f"Canonical desired-state save failed: {save_error}")
        if not execution.success and not reasons:
            reasons.append("The deterministic executor stopped before all postconditions passed.")
        warnings = list(execution.warnings) + list(phase_preview_warnings)
        provider_result = ProviderRunResult(
            final_text=(
                "Typed desired state executed and persisted."
                if execution.success and save_error is None
                else "Typed desired-state execution was blocked."
            ),
            tool_trace=provider_result.tool_trace,
            report_facts={
                "completed": completed,
                "not_done": blocked,
                "reasons": reasons,
                "warnings": warnings,
                "next_help": [
                    "Inspect the blocked operation and correct its object identity or "
                    "source-channel reference before retrying."
                ]
                if reasons
                else ["Continue with another typed revision or request a final render."],
            },
        )
        run_state = self._run_state_from_summary(
            draft_summary=summary,
            objectives=plan.run_state.objectives,
            completed_objectives=tuple(completed),
            blocked_objectives=tuple(blocked),
            last_verification={
                "success": execution.success and save_error is None,
                "errors": reasons,
                "phase_preview_warnings": list(phase_preview_warnings),
            },
        )
        if save_error is not None and save_transport_failure:
            return self._typed_transport_blocked_result(
                draft_logfile=draft_logfile,
                request_kind=request_kind,
                goal=request_text,
                example_id=example_id,
                source_logfile_path=source_logfile_path,
                baseline_draft_text=baseline_draft_text,
                provider_result=provider_result,
                plan=plan,
                phase_summaries=phase_summaries,
                run_state=run_state,
                reason=save_error,
            )
        try:
            return await self._finalize_result(
                session=session,
                draft_logfile=draft_logfile,
                request_kind=request_kind,
                goal=request_text,
                example_id=example_id,
                source_logfile_path=source_logfile_path,
                baseline_draft_text=baseline_draft_text,
                provider_result=provider_result,
                plan=plan,
                phase_summaries=phase_summaries,
                run_state=run_state,
            )
        except Exception as exc:
            if not save_transport_failure:
                raise
            return self._typed_transport_blocked_result(
                draft_logfile=draft_logfile,
                request_kind=request_kind,
                goal=request_text,
                example_id=example_id,
                source_logfile_path=source_logfile_path,
                baseline_draft_text=baseline_draft_text,
                provider_result=provider_result,
                plan=plan,
                phase_summaries=phase_summaries,
                run_state=run_state,
                reason=(
                    "MCP transport closed before final validation/preview: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )

    async def run_request(self, request: AuthoringRequest) -> AuthoringResult:
        """Run one authoring request from the provider-neutral request model."""
        relative_output_logfile = _relative_logfile_path(
            self.runtime.server_root, request.output_logfile
        )
        relative_source_logfile = (
            None
            if request.source_logfile_path is None
            else _relative_logfile_path(self.runtime.server_root, request.source_logfile_path)
        )

        async with self.runtime.open_session() as session:
            baseline_result = await session.call_tool(
                "create_logfile_draft",
                {
                    "output_path": relative_output_logfile,
                    "example_id": request.example_id,
                    "source_logfile_path": relative_source_logfile,
                    "overwrite": True,
                },
            )
            _require_mcp_success(baseline_result, action="create_logfile_draft")
            baseline_payload = _structured_content(baseline_result)
            output_path = _existing_draft_path(
                server_root=self.runtime.server_root,
                requested_relative_path=relative_output_logfile,
                create_result=baseline_payload,
            )
            relative_output_logfile = _relative_logfile_path(self.runtime.server_root, output_path)
            baseline_draft_text = output_path.read_text(encoding="utf-8")

            preflight_tool_trace: tuple[AuthoringToolCall, ...] = ()
            style_intent, remaining_goal = _extract_matplotlib_style_intent(request.goal)
            effective_goal = remaining_goal if remaining_goal else request.goal
            if style_intent is not None:
                style_tool_call = await self._apply_deterministic_matplotlib_style(
                    session=session,
                    draft_logfile=relative_output_logfile,
                    intent=style_intent,
                )
                preflight_tool_trace = (style_tool_call,)
                if not remaining_goal.strip():
                    provider_result = ProviderRunResult(
                        final_text="Applied deterministic Matplotlib style update.",
                        tool_trace=preflight_tool_trace,
                    )
                    return await self._finalize_result(
                        session=session,
                        draft_logfile=relative_output_logfile,
                        request_kind="author",
                        goal=request.goal,
                        example_id=request.example_id,
                        source_logfile_path=relative_source_logfile,
                        baseline_draft_text=baseline_draft_text,
                        provider_result=provider_result,
                    )

            deterministic_header_fill = _extract_header_fill_intent(effective_goal)
            if deterministic_header_fill is not None:
                result = await self._run_deterministic_header_fill(
                    session=session,
                    draft_logfile=relative_output_logfile,
                    request_kind="author",
                    goal=request.goal,
                    example_id=request.example_id,
                    source_logfile_path=relative_source_logfile,
                    baseline_draft_text=baseline_draft_text,
                    intent=deterministic_header_fill,
                )
                if preflight_tool_trace:
                    object.__setattr__(
                        result,
                        "tool_trace",
                        preflight_tool_trace + result.tool_trace,
                    )
                return result

            if request.desired_state is not None or bool(
                getattr(self.backend, "supports_desired_state", False)
            ):
                return await self._run_desired_state_workflow(
                    session=session,
                    draft_logfile=relative_output_logfile,
                    request_kind="author",
                    request_text=effective_goal,
                    example_id=request.example_id,
                    source_logfile_path=relative_source_logfile,
                    baseline_draft_text=baseline_draft_text,
                    max_rounds=request.max_rounds,
                    desired_state=request.desired_state,
                )

            authoring_plan = self._plan_from_text(effective_goal)
            if authoring_plan.phases:
                prompt_arguments: dict[str, object] = {
                    "goal": effective_goal,
                    "logfile_path": relative_output_logfile,
                }
                if request.example_id is not None:
                    prompt_arguments["example_id"] = request.example_id
                prompt_result = await session.get_prompt(
                    "author_plot_from_request",
                    prompt_arguments,
                )
                authoring_prompt = self.runtime.prompt_text(prompt_result)
                tools_result = await session.list_tools()
                tool_definitions = self.runtime.build_tool_definitions(
                    getattr(tools_result, "tools", []),
                    allowed_names=set(self.allowed_tool_names),
                    excluded_names={"create_logfile_draft"},
                )
                provider_result, phase_summaries, run_state = await self._execute_authoring_plan(
                    session=session,
                    draft_logfile=relative_output_logfile,
                    request_text=effective_goal,
                    plan=authoring_plan,
                    prompt_text=authoring_prompt,
                    tool_definitions=tool_definitions,
                    request_max_rounds=request.max_rounds,
                    seed_context=_request_seed_label(request),
                )
                if preflight_tool_trace:
                    provider_result = ProviderRunResult(
                        final_text=provider_result.final_text,
                        tool_trace=preflight_tool_trace + provider_result.tool_trace,
                        report_facts=provider_result.report_facts,
                    )
                return await self._finalize_result(
                    session=session,
                    draft_logfile=relative_output_logfile,
                    request_kind="author",
                    goal=request.goal,
                    example_id=request.example_id,
                    source_logfile_path=relative_source_logfile,
                    baseline_draft_text=baseline_draft_text,
                    provider_result=provider_result,
                    plan=authoring_plan,
                    phase_summaries=phase_summaries,
                    run_state=run_state,
                )

            bootstrap_summary_result = await session.call_tool(
                "summarize_logfile_draft",
                {"logfile_path": relative_output_logfile},
            )
            _require_mcp_success(bootstrap_summary_result, action="summarize_logfile_draft")
            bootstrap_vocab_result = await session.call_tool(
                "inspect_authoring_vocab",
                {"logfile_path": relative_output_logfile},
            )
            _require_mcp_success(bootstrap_vocab_result, action="inspect_authoring_vocab")
            prompt_arguments: dict[str, object] = {
                "goal": effective_goal,
                "logfile_path": relative_output_logfile,
            }
            if request.example_id is not None:
                prompt_arguments["example_id"] = request.example_id
            prompt_result = await session.get_prompt(
                "author_plot_from_request",
                prompt_arguments,
            )
            authoring_prompt = self.runtime.prompt_text(prompt_result)
            tools_result = await session.list_tools()
            tool_definitions = self.runtime.build_tool_definitions(
                getattr(tools_result, "tools", []),
                allowed_names=set(self.allowed_tool_names),
                excluded_names={"create_logfile_draft"},
            )
            if not tool_definitions:
                raise RuntimeError("No MCP tools were exposed to the authoring loop.")

            bootstrap_summary = _structured_content(bootstrap_summary_result)
            bootstrap_vocab = _structured_content(bootstrap_vocab_result)
            sections = _bootstrap_sections(bootstrap_summary)

            async def call_mcp_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
                tool_result = await session.call_tool(name, arguments)
                return self.runtime.tool_result_payload(tool_result)

            provider_result = await self.backend.run_authoring(
                instructions=authoring_prompt,
                initial_user_message=_authoring_bootstrap_message(
                    goal=effective_goal,
                    seed_label=_request_seed_label(request),
                    logfile_path=relative_output_logfile,
                    seed_result=_structured_content(baseline_result),
                    sections=sections,
                    heading_patch_keys=list(bootstrap_vocab.get("heading_patch_keys", [])),
                    curve_binding_patch_keys=list(
                        bootstrap_vocab.get("curve_binding_patch_keys", [])
                    ),
                ),
                tool_definitions=tool_definitions,
                tool_caller=call_mcp_tool,
                max_rounds=request.max_rounds,
            )
            if preflight_tool_trace:
                provider_result = ProviderRunResult(
                    final_text=provider_result.final_text,
                    tool_trace=preflight_tool_trace + provider_result.tool_trace,
                )
            return await self._finalize_result(
                session=session,
                draft_logfile=relative_output_logfile,
                request_kind="author",
                goal=request.goal,
                example_id=request.example_id,
                source_logfile_path=relative_source_logfile,
                baseline_draft_text=baseline_draft_text,
                provider_result=provider_result,
            )

    async def revise_request(self, request: RevisionRequest) -> AuthoringResult:
        """Run one revision request against an existing draft logfile."""
        relative_logfile = _relative_logfile_path(self.runtime.server_root, request.logfile_path)
        output_path = self.runtime.server_root / relative_logfile
        if not output_path.exists():
            raise FileNotFoundError(f"Draft logfile does not exist: {output_path}")

        async with self.runtime.open_session() as session:
            baseline_draft_text = output_path.read_text(encoding="utf-8")

            preflight_tool_trace: tuple[AuthoringToolCall, ...] = ()
            style_intent, remaining_feedback = _extract_matplotlib_style_intent(request.feedback)
            effective_feedback = remaining_feedback if remaining_feedback else request.feedback
            if style_intent is not None:
                style_tool_call = await self._apply_deterministic_matplotlib_style(
                    session=session,
                    draft_logfile=relative_logfile,
                    intent=style_intent,
                )
                preflight_tool_trace = (style_tool_call,)
                if not remaining_feedback.strip():
                    provider_result = ProviderRunResult(
                        final_text="Applied deterministic Matplotlib style update.",
                        tool_trace=preflight_tool_trace,
                    )
                    return await self._finalize_result(
                        session=session,
                        draft_logfile=relative_logfile,
                        request_kind="revise",
                        goal=request.feedback,
                        example_id=None,
                        source_logfile_path=None,
                        baseline_draft_text=baseline_draft_text,
                        provider_result=provider_result,
                    )

            deterministic_header_fill = _extract_header_fill_intent(effective_feedback)
            if deterministic_header_fill is not None:
                result = await self._run_deterministic_header_fill(
                    session=session,
                    draft_logfile=relative_logfile,
                    request_kind="revise",
                    goal=request.feedback,
                    example_id=None,
                    source_logfile_path=None,
                    baseline_draft_text=baseline_draft_text,
                    intent=deterministic_header_fill,
                )
                if preflight_tool_trace:
                    object.__setattr__(
                        result,
                        "tool_trace",
                        preflight_tool_trace + result.tool_trace,
                    )
                return result

            if request.desired_state is not None or bool(
                getattr(self.backend, "supports_desired_state", False)
            ):
                return await self._run_desired_state_workflow(
                    session=session,
                    draft_logfile=relative_logfile,
                    request_kind="revise",
                    request_text=effective_feedback,
                    example_id=None,
                    source_logfile_path=None,
                    baseline_draft_text=baseline_draft_text,
                    max_rounds=request.max_rounds,
                    desired_state=request.desired_state,
                )

            authoring_plan = self._plan_from_text(effective_feedback)
            if authoring_plan.phases:
                prompt_result = await session.get_prompt(
                    "revise_plot_from_feedback",
                    {
                        "logfile_path": relative_logfile,
                        "feedback": effective_feedback,
                    },
                )
                revision_prompt = self.runtime.prompt_text(prompt_result)
                tools_result = await session.list_tools()
                tool_definitions = self.runtime.build_tool_definitions(
                    getattr(tools_result, "tools", []),
                    allowed_names=set(self.allowed_tool_names),
                    excluded_names={"create_logfile_draft"},
                )
                provider_result, phase_summaries, run_state = await self._execute_authoring_plan(
                    session=session,
                    draft_logfile=relative_logfile,
                    request_text=effective_feedback,
                    plan=authoring_plan,
                    prompt_text=revision_prompt,
                    tool_definitions=tool_definitions,
                    request_max_rounds=request.max_rounds,
                )
                if preflight_tool_trace:
                    provider_result = ProviderRunResult(
                        final_text=provider_result.final_text,
                        tool_trace=preflight_tool_trace + provider_result.tool_trace,
                        report_facts=provider_result.report_facts,
                    )
                return await self._finalize_result(
                    session=session,
                    draft_logfile=relative_logfile,
                    request_kind="revise",
                    goal=request.feedback,
                    example_id=None,
                    source_logfile_path=None,
                    baseline_draft_text=baseline_draft_text,
                    provider_result=provider_result,
                    plan=authoring_plan,
                    phase_summaries=phase_summaries,
                    run_state=run_state,
                )
            bootstrap_summary_result = await session.call_tool(
                "summarize_logfile_draft",
                {"logfile_path": relative_logfile},
            )
            _require_mcp_success(bootstrap_summary_result, action="summarize_logfile_draft")
            bootstrap_vocab_result = await session.call_tool(
                "inspect_authoring_vocab",
                {"logfile_path": relative_logfile},
            )
            _require_mcp_success(bootstrap_vocab_result, action="inspect_authoring_vocab")
            prompt_result = await session.get_prompt(
                "revise_plot_from_feedback",
                {
                    "logfile_path": relative_logfile,
                    "feedback": effective_feedback,
                },
            )
            revision_prompt = self.runtime.prompt_text(prompt_result)
            tools_result = await session.list_tools()
            tool_definitions = self.runtime.build_tool_definitions(
                getattr(tools_result, "tools", []),
                allowed_names=set(self.allowed_tool_names),
                excluded_names={"create_logfile_draft"},
            )
            if not tool_definitions:
                raise RuntimeError("No MCP tools were exposed to the revision loop.")

            bootstrap_summary = _structured_content(bootstrap_summary_result)
            bootstrap_vocab = _structured_content(bootstrap_vocab_result)
            sections = _bootstrap_sections(bootstrap_summary)

            async def call_mcp_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
                tool_result = await session.call_tool(name, arguments)
                return self.runtime.tool_result_payload(tool_result)

            provider_result = await self.backend.run_authoring(
                instructions=revision_prompt,
                initial_user_message=_revision_bootstrap_message(
                    feedback=effective_feedback,
                    logfile_path=relative_logfile,
                    sections=sections,
                    heading_patch_keys=list(bootstrap_vocab.get("heading_patch_keys", [])),
                    curve_binding_patch_keys=list(
                        bootstrap_vocab.get("curve_binding_patch_keys", [])
                    ),
                ),
                tool_definitions=tool_definitions,
                tool_caller=call_mcp_tool,
                max_rounds=request.max_rounds,
            )
            if preflight_tool_trace:
                provider_result = ProviderRunResult(
                    final_text=provider_result.final_text,
                    tool_trace=preflight_tool_trace + provider_result.tool_trace,
                )
            return await self._finalize_result(
                session=session,
                draft_logfile=relative_logfile,
                request_kind="revise",
                goal=request.feedback,
                example_id=None,
                source_logfile_path=None,
                baseline_draft_text=baseline_draft_text,
                provider_result=provider_result,
            )

    async def run(
        self,
        *,
        goal: str,
        output_logfile: str | Path,
        example_id: str | None = None,
        source_logfile_path: str | Path | None = None,
        max_rounds: int = 12,
        desired_state: AuthoringDocumentIntent | Mapping[str, object] | None = None,
    ) -> AuthoringResult:
        """Run one authoring request with keyword arguments."""
        return await self.run_request(
            AuthoringRequest(
                goal=goal,
                output_logfile=_relative_logfile_path(self.runtime.server_root, output_logfile),
                example_id=example_id,
                source_logfile_path=(
                    None
                    if source_logfile_path is None
                    else _relative_logfile_path(self.runtime.server_root, source_logfile_path)
                ),
                max_rounds=max_rounds,
                desired_state=desired_state,
            )
        )

    async def revise(
        self,
        *,
        feedback: str,
        logfile_path: str | Path,
        max_rounds: int = 12,
        desired_state: AuthoringDocumentIntent | Mapping[str, object] | None = None,
    ) -> AuthoringResult:
        """Revise one existing draft logfile through the provider-backed agent loop."""
        return await self.revise_request(
            RevisionRequest(
                feedback=feedback,
                logfile_path=_relative_logfile_path(self.runtime.server_root, logfile_path),
                max_rounds=max_rounds,
                desired_state=desired_state,
            )
        )

    async def render_logfile_to_file(
        self,
        *,
        logfile_path: str | Path,
        output_path: str | Path,
        overwrite: bool = False,
    ) -> dict[str, object]:
        """Render one draft logfile through the local MCP server."""
        async with self.runtime.open_session() as session:
            result = await session.call_tool(
                "render_logfile_to_file",
                {
                    "logfile_path": _relative_logfile_path(
                        self.runtime.server_root,
                        logfile_path,
                    ),
                    "output_path": _relative_logfile_path(
                        self.runtime.server_root,
                        output_path,
                    ),
                    "overwrite": overwrite,
                },
            )
            _require_mcp_success(result, action="render_logfile_to_file")
        return _structured_content(result)

    async def inspect_heading_slots(
        self,
        *,
        logfile_path: str | Path,
    ) -> dict[str, object]:
        """Inspect deterministic heading slots for one draft logfile."""
        async with self.runtime.open_session() as session:
            result = await session.call_tool(
                "inspect_heading_slots",
                {
                    "logfile_path": _relative_logfile_path(
                        self.runtime.server_root,
                        logfile_path,
                    ),
                },
            )
            _require_mcp_success(result, action="inspect_heading_slots")
        return _structured_content(result)

    async def preview_header_mapping(
        self,
        *,
        logfile_path: str | Path,
        values: dict[str, object],
        overwrite_policy: str = "fill_empty",
    ) -> dict[str, object]:
        """Dry-run deterministic heading-value assignment for one draft logfile."""
        async with self.runtime.open_session() as session:
            result = await session.call_tool(
                "preview_header_mapping",
                {
                    "logfile_path": _relative_logfile_path(
                        self.runtime.server_root,
                        logfile_path,
                    ),
                    "values": values,
                    "overwrite_policy": overwrite_policy,
                },
            )
            _require_mcp_success(result, action="preview_header_mapping")
        return _structured_content(result)

    async def apply_header_values(
        self,
        *,
        logfile_path: str | Path,
        values: dict[str, object],
        overwrite_policy: str = "fill_empty",
    ) -> dict[str, object]:
        """Persist deterministic heading-value assignment for one draft logfile."""
        async with self.runtime.open_session() as session:
            result = await session.call_tool(
                "apply_header_values",
                {
                    "logfile_path": _relative_logfile_path(
                        self.runtime.server_root,
                        logfile_path,
                    ),
                    "values": values,
                    "overwrite_policy": overwrite_policy,
                },
            )
            _require_mcp_success(result, action="apply_header_values")
        return _structured_content(result)


async def run_authoring_request(
    *,
    goal: str,
    output_logfile: str | Path,
    example_id: str | None = None,
    source_logfile_path: str | Path | None = None,
    provider: str,
    model: str,
    server_root: str | Path | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    max_rounds: int = 12,
) -> AuthoringResult:
    """Run one high-level authoring request against local stdio MCP."""
    session = AuthoringSession.from_local_mcp(
        provider=provider,
        model=model,
        server_root=server_root,
        api_key=api_key,
        base_url=base_url,
    )
    return await session.run(
        goal=goal,
        output_logfile=output_logfile,
        example_id=example_id,
        source_logfile_path=source_logfile_path,
        max_rounds=max_rounds,
    )


async def revise_authoring_request(
    *,
    feedback: str,
    logfile_path: str | Path,
    provider: str,
    model: str,
    server_root: str | Path | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    max_rounds: int = 12,
) -> AuthoringResult:
    """Revise one existing draft logfile against local stdio MCP."""
    session = AuthoringSession.from_local_mcp(
        provider=provider,
        model=model,
        server_root=server_root,
        api_key=api_key,
        base_url=base_url,
    )
    return await session.revise(
        feedback=feedback,
        logfile_path=logfile_path,
        max_rounds=max_rounds,
    )
