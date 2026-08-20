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
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field, replace
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
    resolve_authoring_context,
)
from ..authoring_defaults import (
    form_default_catalog,
    generic_authoring_defaults,
    style_preset_catalog,
    track_archetype_catalog,
)
from ..authoring_executor import (
    AuthoringExecutionResult,
    AuthoringExecutionStatus,
    AuthoringOperationOutcome,
    AuthoringPhaseCheckpoint,
)
from ..authoring_reconciler import (
    AuthoringOperationPhase,
    AuthoringReconciliationPlan,
    reconcile_authoring,
)
from ..authoring_service import (
    AuthoringService,
    authoring_hierarchy_catalog,
    authoring_operation_json_schema,
)
from ..mcp.packet_blueprints import packet_blueprint_spec
from ..model.authoring import AuthoringDocumentSpec
from ..model.intent import AuthoringDocumentIntent
from .compilation import (
    AuthoringCompilationScope,
    AuthoringIntentCoverage,
    AuthoringRequestInventory,
    AuthoringRequestInventoryItem,
    AuthoringRequestManifest,
    AuthoringRequestWorkUnit,
    build_deterministic_narrow_inventory,
    build_request_manifest,
    build_request_work_units,
    compilation_scope_for_object_family,
    group_request_inventory,
    merge_scoped_intents,
    operation_request_object_kind,
    scoped_submission_model,
    validate_intent_coverage,
    validate_reconciliation_fulfillment,
    validate_request_inventory,
    validate_scoped_intent_semantics,
)
from .operation_executor import (
    TypedOperationExecutionStatus,
    TypedSubmissionExecutionResult,
    execute_typed_submissions,
)
from .reconciliation_bridge import compile_reconciliation_plan
from .stable_fallback import (
    build_catalog_fallback_plan,
    catalog_channel_candidates,
    fallback_plan_satisfied,
    is_track_request,
)
from .tool_contract import stable_tool_profile

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

STABLE_MCP_TOOL_NAMES = frozenset(item.name for item in stable_tool_profile())
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


class ProviderAdapterError(RuntimeError):
    """Normalized provider-adapter failure with a stable diagnostic status."""

    def __init__(
        self,
        status: str,
        message: str,
        *,
        tool_trace: Sequence[AuthoringToolCall] = (),
        final_text: str = "",
        report_facts: Mapping[str, object] | None = None,
    ) -> None:
        """Initialize one adapter failure with a machine-readable status."""
        super().__init__(message)
        self.status = status
        self.tool_trace = tuple(tool_trace)
        self.final_text = final_text
        self.report_facts = dict(report_facts or {})


def _sanitize_provider_text(value: object, *, limit: int = 500) -> str | None:
    """Return a short provider message with common credential forms redacted."""
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = " ".join(value.split())
    normalized = re.sub(
        r"(?i)\b(?:sk|nvapi|hf|ghp)[-_][A-Za-z0-9_-]{8,}\b",
        "[REDACTED]",
        normalized,
    )
    normalized = re.sub(r"(?i)\bbearer\s+\S+", "Bearer [REDACTED]", normalized)
    if len(normalized) > limit:
        return normalized[: limit - 3].rstrip() + "..."
    return normalized


def _provider_exception_status(exc: BaseException) -> str:
    """Classify one provider failure for the extraction report."""
    if isinstance(exc, ProviderAdapterError):
        return exc.status
    if isinstance(exc, json.JSONDecodeError):
        return "invalid_json"
    message = str(exc).lower()
    if "exceeded" in message and "round" in message:
        return "round_budget_exhausted"
    if any(token in message for token in ("connection", "transport", "closed")):
        return "transport_failure"
    return "provider_error"


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
    warnings: tuple[str, ...] = ()
    run_state: AuthoringRunState = field(default_factory=AuthoringRunState)
    defaults_provenance: dict[str, str] = field(default_factory=dict)
    applied_defaults_provenance: dict[str, str] = field(default_factory=dict)
    resolved_values: dict[str, object] = field(default_factory=dict)
    resolution_decisions: tuple[dict[str, object], ...] = ()
    operation_payloads: tuple[dict[str, object], ...] = ()
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
    needs_clarification: tuple[dict[str, object], ...] = ()
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
                (
                    "Needs clarification",
                    tuple(_clarification_summary_text(item) for item in self.needs_clarification),
                ),
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
    needs_clarification: tuple[dict[str, object], ...] = ()
    request_coverage: tuple[dict[str, object], ...] = ()
    operation_outcomes: tuple[dict[str, object], ...] = ()
    defaults_provenance: dict[str, str] = field(default_factory=dict)
    submitted_intent: dict[str, object] | None = None
    report_facts: dict[str, object] = field(default_factory=dict)

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
    supports_desired_state: bool
    supports_direct_operations: bool

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[FunctionToolDefinition],
        tool_caller: ToolCaller,
        max_rounds: int,
        required_tool_name: str | None = None,
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


def _quoted_request_value(text: str, label_pattern: str) -> str | None:
    """Extract a quoted or simple unquoted value after a natural-language label."""
    match = re.search(
        rf"{label_pattern}\s*(?:to|=)\s*"
        rf"(?:[`\"'](?P<quoted>[^`\"']+)[`\"']|(?P<bare>[^\n.;]+?))"
        rf"(?=[.;\n]|$)",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    value = match.group("quoted") or match.group("bare")
    return value.strip() if value else None


def _request_identifier(text: str, label_pattern: str) -> str | None:
    """Extract one identifier written after a natural-language label."""
    quoted = re.search(
        rf"{label_pattern}\s*(?:[:=]|is|to)?\s*[`\"'](?P<value>[^`\"']+)[`\"']",
        text,
        re.IGNORECASE,
    )
    if quoted is not None:
        return quoted.group("value").strip()
    bare = re.search(
        rf"{label_pattern}\s*(?:[:=]|is|to)\s*(?P<value>[A-Za-z][\w.-]*)",
        text,
        re.IGNORECASE,
    )
    return bare.group("value").strip() if bare is not None else None


def _resolved_authoring_value(value: object) -> object:
    """Unwrap nested typed report values for deterministic comparisons."""
    current = value
    for _ in range(3):
        nested = getattr(current, "value", None)
        if nested is None or nested is current:
            break
        current = nested
    return current


def _stable_scope_tool_names(goal: str) -> set[str] | None:
    """Return mutation tools named by a request, when the scope is explicit."""
    families = {
        "edit_header": r"\b(?:header|service\s+title)\b",
        "edit_report_settings": (
            r"\b(?:report\s+title|subtitle|page|output|depth|orientation|layout|settings?)\b"
        ),
        "edit_remarks": r"\b(?:remarks?|notes?)\b",
        "edit_section": r"\bsections?\b",
        "edit_track": r"\btracks?\b",
        "edit_curve_binding": r"\b(?:curves?|bindings?)\b",
        "edit_raster_binding": r"\b(?:arrays?|rasters?)\b",
        "edit_fill": r"\bfills?\b",
        "edit_annotation": r"\bannotations?\b",
    }
    mentioned = {tool for tool, pattern in families.items() if re.search(pattern, goal, re.I)}
    if not mentioned:
        return None
    negative_remarks = re.search(
        r"\b(?:do\s+not|don't|without)\s+(?:add|create|insert)\b[^.\n]*\bremarks?\b",
        goal,
        re.IGNORECASE,
    )
    if negative_remarks:
        mentioned.discard("edit_remarks")
    if "edit_section" in mentioned:
        mentioned.add("replicate_section_structure")
    return mentioned


def _catalog_fallback_section_id(
    goal: str,
    document: AuthoringDocumentSpec,
) -> str | None:
    """Resolve a single section for catalog recovery, never a packet implicitly."""
    if re.search(r"\b(?:sections\s+ids?|section\s+ids)\b", goal, re.IGNORECASE):
        return None
    match = re.search(
        r"\bsection(?:\s+id)?\s+[`\"']?([A-Za-z][\w.-]*)",
        goal,
        re.IGNORECASE,
    )
    if match is not None:
        requested = match.group(1)
        if any(section.id == requested for section in document.sections):
            return requested
        return None
    return document.sections[0].id if len(document.sections) == 1 else None


def _stable_postcondition_errors(
    goal: str,
    baseline: AuthoringDocumentSpec,
    *,
    root: Path,
    draft_logfile: str,
) -> list[str]:
    """Check explicit request clauses against baseline-relative canonical state."""
    current_path = root / draft_logfile
    current = load_authoring_document(current_path, allowed_root=root)
    errors: list[str] = []

    section_id = _request_identifier(goal, r"section\s+id")
    expected_subtitle = _quoted_request_value(goal, r"section\s+subtitle")
    if expected_subtitle is not None:
        if section_id is None:
            section_match = re.search(
                r"\b([A-Za-z][\w.-]*)\s+section\s+subtitle\b",
                goal,
                re.IGNORECASE,
            )
            candidate = section_match.group(1) if section_match else None
            section_id = candidate if candidate not in {"the", "a", "an"} else None
        if section_id is None and len(current.sections) == 1:
            section = current.sections[0]
        else:
            section = next(
                (item for item in current.sections if item.id == section_id),
                None,
            )
        if section is None:
            errors.append(f"Requested section {section_id!r} was not found.")
        elif section.subtitle != expected_subtitle:
            errors.append(f"Section {section.id!r} subtitle was not set to {expected_subtitle!r}.")

    expected_service_title = _quoted_request_value(goal, r"(?:first\s+)?service\s+title")
    if expected_service_title is not None:
        if current.header is None:
            errors.append("The request asked for a service title, but the header is missing.")
        else:
            titles = [
                _resolved_authoring_value(slot.value) for slot in current.header.service_titles
            ]
            if not titles or titles[0] != expected_service_title:
                errors.append(f"First service title was not set to {expected_service_title!r}.")

    baseline_payload = baseline.model_dump(mode="json")
    current_payload = current.model_dump(mode="json")
    if re.search(
        r"\b(?:do\s+not|don't|without)\s+(?:add|create|insert)\b[^.\n]*\bremarks?\b",
        goal,
        re.IGNORECASE,
    ) and baseline_payload.get("remarks") != current_payload.get("remarks"):
        errors.append("The request prohibited remarks changes, but remarks were mutated.")

    if re.search(r"\bdo\s+not\s+add\s+any\s+additional\s+tracks?\b", goal, re.I):
        baseline_tracks = [track.id for section in baseline.sections for track in section.tracks]
        current_tracks = [track.id for section in current.sections for track in section.tracks]
        if baseline_tracks != current_tracks:
            errors.append("The request prohibited additional tracks, but track structure changed.")

    if re.search(r"\badd\s+(?:one|a|an)\b[^.\n]*\b(?:remarks?|notes?)\b", goal, re.I):
        baseline_remarks = baseline_payload.get("remarks") or []
        current_remarks = current_payload.get("remarks") or []
        if len(current_remarks) != len(baseline_remarks) + 1:
            errors.append(
                "The request asked for one new remarks block, but the persisted count "
                f"changed from {len(baseline_remarks)} to {len(current_remarks)}."
            )
        if any(not _has_persisted_remark_content(item) for item in current_remarks):
            errors.append(
                "Every persisted remarks block must have non-empty text or string lines."
            )
    return errors


def _has_persisted_remark_content(item: object) -> bool:
    """Return whether a serialized remark contains text or non-empty string lines."""
    if not isinstance(item, dict):
        return False
    text = item.get("text")
    if isinstance(text, str) and text.strip():
        return True
    lines = item.get("lines")
    return isinstance(lines, list) and bool(lines) and all(
        isinstance(line, str) and line.strip() for line in lines
    )


def _normalize_stable_tool_arguments(
    name: str,
    arguments: Mapping[str, object],
) -> dict[str, object]:
    """Normalize recoverable provider argument shapes before MCP dispatch."""
    normalized = dict(arguments)
    if name == "inspect_source":
        if normalized.get("source_path") is not None:
            # Source inspection and draft inspection are mutually exclusive.
            # Providers often copy the draft context into every tool call.
            normalized.pop("logfile_path", None)
        return normalized
    if name == "edit_report_settings":
        return _normalize_report_settings_arguments(normalized)
    if name == "edit_raster_binding":
        return _normalize_raster_binding_arguments(normalized)
    if name != "edit_remarks" or normalized.get("operation") != "add":
        if name in {"edit_curve_binding", "edit_track"}:
            scale_keys = ("scale", "x_scale", "curve_scale")
            for key in scale_keys:
                if key in normalized:
                    normalized[key] = _normalize_scale_payload(normalized[key])
            channel_scales = normalized.get("channel_scales")
            if isinstance(channel_scales, Mapping):
                normalized["channel_scales"] = {
                    str(channel): _normalize_scale_payload(scale)
                    for channel, scale in channel_scales.items()
                }
            patch = normalized.get("patch")
            if isinstance(patch, Mapping):
                normalized_patch = dict(patch)
                for key in scale_keys:
                    if key in normalized_patch:
                        normalized_patch[key] = _normalize_scale_payload(normalized_patch[key])
                if isinstance(normalized_patch.get("style"), Mapping):
                    normalized_patch["style"] = _normalize_style_payload(
                        normalized_patch["style"]
                    )
                normalized["patch"] = normalized_patch
            if isinstance(normalized.get("style"), Mapping):
                normalized["style"] = _normalize_style_payload(normalized["style"])
        return normalized
    remark_fields = (
        "remark_id",
        "title",
        "text",
        "lines",
        "alignment",
        "font_size",
        "title_font_size",
        "border",
    )
    nested_remark = normalized.get("remark")
    if isinstance(nested_remark, Mapping):
        remark = dict(nested_remark)
    else:
        remark = {
            field: normalized[field]
            for field in remark_fields
            if field in normalized
        }
    if remark:
        lines = remark.get("lines")
        if isinstance(lines, str):
            try:
                decoded_lines = json.loads(lines)
            except json.JSONDecodeError:
                decoded_lines = [lines]
            remark["lines"] = (
                decoded_lines if isinstance(decoded_lines, list) else [lines]
            )
        normalized["remark"] = remark
        for field in remark_fields:
            normalized.pop(field, None)
    return normalized


_RASTER_BINDING_FIELDS = {
    "label",
    "profile",
    "normalization",
    "waveform_normalization",
    "clip_percentiles",
    "interpolation",
    "show_raster",
    "alpha",
    "raster_alpha",
    "color_limits",
    "colorbar",
    "sample_axis",
    "waveform",
}


def _normalize_raster_binding_arguments(
    arguments: Mapping[str, object],
) -> dict[str, object]:
    """Normalize provider raster patches into the stable binding contract."""
    normalized = dict(arguments)
    patch_value = normalized.get("patch")
    patch = dict(patch_value) if isinstance(patch_value, Mapping) else {}
    if isinstance(normalized.get("style"), Mapping):
        patch.setdefault("style", normalized["style"])

    for raster_field in _RASTER_BINDING_FIELDS:
        if raster_field in normalized:
            patch.setdefault(raster_field, normalized[raster_field])

    style = patch.get("style")
    if isinstance(style, Mapping):
        style_patch = dict(style)
        # Some providers treat a raster binding as one undifferentiated style
        # object. Move presentation controls to their typed patch fields.
        for raster_field in _RASTER_BINDING_FIELDS:
            if raster_field in style_patch:
                patch.setdefault(raster_field, style_patch.pop(raster_field))
        patch["style"] = _normalize_style_payload(style_patch)

    color_limits = patch.get("color_limits")
    if color_limits is None or color_limits == []:
        patch.pop("color_limits", None)
    elif isinstance(color_limits, Mapping):
        minimum = color_limits.get("minimum", color_limits.get("min"))
        maximum = color_limits.get("maximum", color_limits.get("max"))
        if minimum is not None and maximum is not None:
            patch["color_limits"] = [minimum, maximum]

    # Optional object fields with null values are not valid for the generated
    # MCP input schema. Absence preserves the current persisted value.
    for raster_field in _RASTER_BINDING_FIELDS:
        if patch.get(raster_field) is None:
            patch.pop(raster_field, None)

    normalized["patch"] = patch
    for raster_field in _RASTER_BINDING_FIELDS:
        normalized.pop(raster_field, None)
    normalized.update(patch)
    return normalized


def _normalize_report_settings_arguments(arguments: Mapping[str, object]) -> dict[str, object]:
    """Map generic provider settings verbs to the typed settings operations."""
    normalized = dict(arguments)
    operation = str(normalized.get("operation", "")).strip().lower()
    if operation not in {"update", "set"}:
        return normalized

    patch = normalized.pop("patch", None)
    if isinstance(patch, Mapping):
        for key, value in patch.items():
            normalized.setdefault(str(key), value)

    if "style_patch" in normalized:
        normalized["operation"] = "set_matplotlib_style"
        return normalized

    page_fields = {
        "size",
        "width_mm",
        "height_mm",
        "orientation",
        "continuous",
        "bottom_track_header_enabled",
        "margin_left_mm",
        "margin_right_mm",
        "margin_top_mm",
        "margin_bottom_mm",
        "header_height_mm",
        "track_header_height_mm",
        "footer_height_mm",
        "track_gap_mm",
    }
    depth_fields = {"unit", "scale", "major_step", "minor_step"}
    output_fields = {"backend", "output_path", "dpi", "continuous_strip_page_height_mm"}
    section_fields = {"title", "subtitle", "depth_range"}

    def move_fields(container: str, fields: set[str]) -> None:
        current = normalized.get(container)
        payload = dict(current) if isinstance(current, Mapping) else {}
        for field_name in fields:
            if field_name in normalized:
                payload[field_name] = normalized.pop(field_name)
        if payload:
            normalized[container] = payload

    if normalized.get("section_id") is not None and any(
        field_name in normalized for field_name in section_fields | {"page", "output"}
    ):
        normalized["operation"] = "set_section_view"
        move_fields("page", page_fields)
        move_fields("output", output_fields)
        return normalized
    if "page" in normalized or any(field_name in normalized for field_name in page_fields):
        normalized["operation"] = "set_page"
        move_fields("page", page_fields)
        return normalized
    if "output" in normalized or any(field_name in normalized for field_name in output_fields):
        normalized["operation"] = "set_output"
        move_fields("output", output_fields)
        return normalized
    if "depth" in normalized or any(field_name in normalized for field_name in depth_fields):
        normalized["operation"] = "set_depth"
        move_fields("depth", depth_fields)
        return normalized

    normalized["operation"] = "set_report"
    move_fields("patch", {"title", "subtitle"})
    return normalized


def _normalize_scale_payload(value: object) -> object:
    """Map common provider scale aliases to the canonical scale shape."""
    if not isinstance(value, Mapping):
        return value
    normalized = dict(value)
    # Units belong to the source/header metadata; the legacy scale schema only
    # accepts the transform, bounds, and reverse flag.
    normalized.pop("unit", None)
    domain = normalized.pop("domain", None)
    if isinstance(domain, (list, tuple)) and len(domain) == 2:
        normalized.setdefault("minimum", domain[0])
        normalized.setdefault("maximum", domain[1])
    if "min" in normalized:
        normalized.setdefault("minimum", normalized.pop("min"))
    if "max" in normalized:
        normalized.setdefault("maximum", normalized.pop("max"))
    if "type" in normalized and "kind" not in normalized:
        normalized["kind"] = normalized.pop("type")
    if "logarithmic" in normalized and "kind" not in normalized:
        logarithmic = normalized.pop("logarithmic")
        if logarithmic:
            normalized["kind"] = "log"
    return normalized


def _normalize_style_payload(value: Mapping[str, object]) -> dict[str, object]:
    """Map common drawing-library style aliases to canonical curve fields."""
    normalized = dict(value)
    aliases = {
        "stroke": "color",
        "stroke_color": "color",
        "stroke_width": "line_width",
        "linewidth": "line_width",
        "linestyle": "line_style",
        "dash": "line_style",
    }
    for alias, canonical in aliases.items():
        if alias in normalized:
            normalized.setdefault(canonical, normalized[alias])
            normalized.pop(alias, None)
    return normalized


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


def _clarification_entries(value: object) -> tuple[dict[str, object], ...]:
    """Normalize structured clarification entries from deterministic tool output."""
    if not isinstance(value, list):
        return ()
    return tuple(dict(entry) for entry in value if isinstance(entry, dict))


def _clarification_summary_text(entry: dict[str, object]) -> str:
    """Return the concise user-facing text for one clarification entry."""
    question = entry.get("clarification_question")
    if isinstance(question, str) and question.strip():
        return question.strip()
    input_key = str(entry.get("input_key", "the requested value")).strip()
    labels = entry.get("candidate_labels")
    if isinstance(labels, list):
        visible_labels = [str(label).strip() for label in labels if str(label).strip()]
        if visible_labels:
            return f"Choose a header field for `{input_key}`: " + " or ".join(visible_labels) + "."
    return f"Choose the header field for `{input_key}`."


def _header_clarification_entries(payload: object) -> list[dict[str, object]]:
    """Extract user-facing header conflicts from one preview payload."""
    if not isinstance(payload, dict):
        return []
    conflicts = payload.get("conflicting_values")
    if not isinstance(conflicts, list):
        return []
    entries: list[dict[str, object]] = []
    for conflict in conflicts:
        if not isinstance(conflict, dict):
            continue
        question = conflict.get("clarification_question")
        if not isinstance(question, str) or not question.strip():
            continue
        entries.append(
            {
                "input_key": conflict.get("input_key"),
                "input_value": deepcopy(conflict.get("input_value")),
                "clarification_question": question.strip(),
                "overwrite_policy": payload.get("overwrite_policy", "replace"),
                "candidate_labels": deepcopy(conflict.get("candidate_labels", [])),
                "candidate_targets": deepcopy(conflict.get("candidate_targets", [])),
            }
        )
    return entries


def _clarification_selector_tokens(value: object) -> set[str]:
    """Normalize conversational clarification wording into meaningful tokens."""
    text = str(value).casefold()
    for delimiter in "_-.@/():,`'\"":
        text = text.replace(delimiter, " ")
    ignored = {
        "as",
        "choose",
        "field",
        "for",
        "from",
        "header",
        "i",
        "it",
        "mean",
        "one",
        "please",
        "select",
        "the",
        "this",
        "that",
        "to",
        "use",
        "value",
        "with",
    }
    tokens = set(text.split()) - ignored
    return {"temp" if token == "temperature" else token for token in tokens}


def _select_pending_header_target(
    text: str,
    pending_entries: Sequence[dict[str, object]],
) -> tuple[dict[str, object], dict[str, object]] | None:
    """Select one pending header target from a natural clarification response."""
    request_tokens = _clarification_selector_tokens(text)
    if not request_tokens:
        return None

    matches: list[tuple[int, dict[str, object], dict[str, object]]] = []
    for entry in pending_entries:
        candidate_labels = entry.get("candidate_labels")
        candidate_targets = entry.get("candidate_targets")
        if not isinstance(candidate_targets, list):
            continue
        labels = candidate_labels if isinstance(candidate_labels, list) else []
        for index, target in enumerate(candidate_targets):
            if not isinstance(target, dict):
                continue
            terms: list[object] = [target.get("display_label"), target.get("target_key")]
            if index < len(labels):
                terms.append(labels[index])
            candidate_tokens: set[str] = set()
            for term in terms:
                candidate_tokens.update(_clarification_selector_tokens(term))
            if request_tokens.issubset(candidate_tokens):
                matches.append((len(request_tokens), entry, target))

    if not matches:
        return None
    highest_score = max(score for score, _entry, _target in matches)
    best_matches = [(entry, target) for score, entry, target in matches if score == highest_score]
    if len(best_matches) != 1:
        return None
    return best_matches[0]


def _header_clarification_target_key(target: dict[str, object]) -> str | None:
    """Return a scoped mapping key for one selected clarification target."""
    target_key = str(target.get("target_key", "")).strip()
    if not target_key:
        return None
    target_kind = str(target.get("target_kind", "")).strip().lower()
    if target_kind == "detail_field":
        return f"detail.{target_key}"
    if target_kind == "general_field":
        return f"general_field.{target_key}"
    if target_kind == "provider":
        return "provider"
    if target_kind == "service_title":
        return target_key
    return target_key


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
    for key in ("display_label", "target_key", "request_key", "channel", "track_id"):
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

    if not bool(report_facts.get("authoritative_completed")):
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

    if not done and tool_trace and not bool(report_facts.get("authoritative_completed")):
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
        needs_clarification=_clarification_entries(report_facts.get("needs_clarification")),
        next_help=_dedupe_text_items(next_help),
    )


def _authoring_execution_from_typed(
    plan: AuthoringPlanResult,
    result: TypedSubmissionExecutionResult,
) -> AuthoringExecutionResult:
    """Adapt typed branch execution to the established agent phase contract."""
    operation_by_id = {
        str(operation["operation_id"]): operation
        for operation in plan.operation_payloads
        if isinstance(operation.get("operation_id"), str)
    }
    outcomes: list[AuthoringOperationOutcome] = []
    for outcome in result.outcomes:
        operation = operation_by_id.get(outcome.operation_id)
        if operation is None:
            continue
        status = (
            AuthoringExecutionStatus.COMPLETED
            if outcome.status
            in {
                TypedOperationExecutionStatus.COMPLETED,
                TypedOperationExecutionStatus.SKIPPED,
            }
            else AuthoringExecutionStatus.BLOCKED
        )
        outcomes.append(
            AuthoringOperationOutcome(
                operation_id=outcome.operation_id,
                phase=AuthoringOperationPhase(operation["phase"]),
                action=operation["action"],
                object_kind=operation["object_kind"],
                object_id=outcome.verification.target.object_id
                if outcome.verification.target is not None
                else str(operation["object_id"]),
                status=status,
                postcondition_verified=outcome.postcondition_verified,
                message=outcome.message,
                error=outcome.error,
            )
        )
    checkpoints = tuple(
        AuthoringPhaseCheckpoint(
            phase=checkpoint.phase,
            status=(
                AuthoringExecutionStatus.COMPLETED
                if checkpoint.status
                in {
                    TypedOperationExecutionStatus.COMPLETED,
                    TypedOperationExecutionStatus.SKIPPED,
                }
                else AuthoringExecutionStatus.BLOCKED
            ),
            operation_ids=checkpoint.operation_ids,
            applied_count=checkpoint.applied_count,
            document=checkpoint.document,
        )
        for checkpoint in result.phase_summaries
    )
    return AuthoringExecutionResult(
        success=result.success,
        stopped=result.stopped,
        document=result.document,
        outcomes=tuple(outcomes),
        phase_summaries=checkpoints,
        errors=result.errors,
        warnings=result.warnings,
    )


def _typed_operation_completion_lines(
    *,
    plan: AuthoringPlanResult,
    execution: AuthoringExecutionResult,
) -> list[str]:
    """Describe only typed operations that passed deterministic postconditions."""
    operation_by_id = {
        str(operation["operation_id"]): operation
        for operation in plan.operation_payloads
        if isinstance(operation.get("operation_id"), str)
    }
    action_labels = {
        "create": "Created",
        "update": "Updated",
        "remove": "Removed",
        "move": "Moved",
    }
    completed: list[str] = []
    for outcome in execution.outcomes:
        if (
            outcome.status != AuthoringExecutionStatus.COMPLETED
            or not outcome.postcondition_verified
        ):
            continue
        operation = operation_by_id.get(outcome.operation_id, {})
        action = action_labels.get(outcome.action.value, outcome.action.value.title())
        object_kind = outcome.object_kind.value.replace("_", " ")
        object_id = outcome.object_id
        line = f"{action} {object_kind}"
        if object_id != outcome.object_kind.value:
            line += f" `{object_id}`"
        section_id = operation.get("section_id")
        track_id = operation.get("track_id")
        if isinstance(section_id, str) and section_id:
            line += f" in section `{section_id}`"
        if isinstance(track_id, str) and track_id:
            line += f", track `{track_id}`"
        completed.append(f"{line}.")

    if not completed and execution.success:
        completed.append(
            "No typed changes were required; the requested state was already satisfied."
        )
    return list(_dedupe_text_items(completed))


def _typed_plan_next_help(plan: AuthoringPlanResult) -> tuple[str, ...]:
    """Return domain-language help for a blocked typed desired-state plan."""
    issue_codes = {
        issue.code
        for issue in (plan.reconciliation_plan.issues if plan.reconciliation_plan else ())
    }
    help_items: list[str] = []
    if "track_create_incomplete" in issue_codes:
        help_items.append(
            "Describe the missing track details in plain language, such as its display "
            "name, approximate width, and whether it is a normal, depth/reference, "
            "array, or annotation track. Track form is separate from its X-scale."
        )
    if any("Ambiguous defaults for track" in warning for warning in plan.warnings):
        help_items.append(
            "Choose the intended presentation convention or provide explicit colors, "
            "labels, and scales; the object can be built generically without guessing "
            "between conventions."
        )
    if any("Unmatched source channel" in warning for warning in plan.warnings):
        help_items.append(
            "The unmatched source channel was retained as requested; provide an explicit "
            "presentation only if its family-specific styling matters."
        )
    if not help_items:
        help_items.append(
            "I can inspect the current draft and source context to identify the smallest "
            "user-facing clarification needed."
        )
    return tuple(help_items)


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
    value = value.rstrip(".;").rstrip()
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
        if isinstance(lines_raw, list):
            lines = tuple(
                str(line).strip() for line in lines_raw if isinstance(line, str) and line.strip()
            )
        else:
            lines = ()
        if not lines:
            text = entry.get("text")
            lines = (text.strip(),) if isinstance(text, str) and text.strip() else ()
        if not title or not lines:
            continue
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


def _catalog_fallback_tool_arguments(
    name: str,
    arguments: Mapping[str, object],
    draft_logfile: str,
) -> dict[str, object]:
    """Add the draft target without creating a dual-source inspection request."""
    call_arguments = dict(arguments)
    if name == "inspect_source" and call_arguments.get("source_path") is not None:
        call_arguments.pop("logfile_path", None)
    else:
        call_arguments.setdefault("logfile_path", draft_logfile)
    return call_arguments


@dataclass
class AuthoringSession:
    """High-level authoring session bound to one provider and local MCP runtime."""

    backend: ProviderBackendProtocol
    runtime: McpRuntimeProtocol
    allowed_tool_names: tuple[str, ...] = DEFAULT_ALLOWED_MCP_TOOLS
    _pending_header_clarifications: dict[str, tuple[dict[str, object], ...]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    @classmethod
    def from_local_mcp(
        cls,
        *,
        provider: str,
        model: str,
        server_root: str | Path | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
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
                timeout=timeout,
            )
        elif provider == "openai_compat":
            if base_url is None or not base_url.strip():
                raise ValueError("provider='openai_compat' requires a non-empty base_url.")
            backend = OpenAICompatibleAuthoringBackend.from_local_configuration(
                model=model,
                server_root=runtime.server_root,
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
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
        report_facts = getattr(provider_result, "report_facts", {})
        needs_clarification = _clarification_entries(
            report_facts.get("needs_clarification") if isinstance(report_facts, dict) else None
        )
        request_coverage = (
            tuple(
                dict(item)
                for item in report_facts.get("request_coverage", [])
                if isinstance(item, dict)
            )
            if isinstance(report_facts, dict)
            else ()
        )
        submitted_intent = (
            dict(report_facts["submitted_intent"])
            if isinstance(report_facts, dict)
            and isinstance(report_facts.get("submitted_intent"), dict)
            else None
        )
        operation_outcomes = (
            tuple(
                dict(item)
                for item in report_facts.get("operation_outcomes", [])
                if isinstance(item, dict)
            )
            if isinstance(report_facts, dict)
            else ()
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
            needs_clarification=needs_clarification,
            request_coverage=request_coverage,
            operation_outcomes=operation_outcomes,
            defaults_provenance=({} if plan is None else dict(plan.defaults_provenance)),
            submitted_intent=submitted_intent,
            report_facts=dict(getattr(provider_result, "report_facts", {})),
            user_report=_build_user_report(
                request_text=goal,
                validation=validation_payload,
                draft_summary=draft_summary_payload,
                change_summary=change_summary_payload,
                tool_trace=provider_result.tool_trace,
                report_facts=getattr(provider_result, "report_facts", {}),
            ),
        )

    @staticmethod
    async def _stable_tool_catalog(session: McpSessionProtocol) -> list[object] | None:
        try:
            result = await session.list_tools()
        except AssertionError:
            return None
        tools = list(getattr(result, "tools", []) or [])
        names = {
            str(getattr(tool, "name", "")).strip()
            for tool in tools
            if str(getattr(tool, "name", "")).strip()
        }
        required = {"create_draft", "inspect_authoring", "validate_logfile", "preview_logfile"}
        if not required.issubset(names):
            return None
        return tools

    async def _finalize_stable_result(
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
        stable_tool_outcomes: list[dict[str, object]],
        stable_tool_errors: list[str],
    ) -> AuthoringResult:
        output_path = self.runtime.server_root / draft_logfile
        if not output_path.exists():
            raise RuntimeError("The stable MCP loop finished without the expected draft logfile.")

        report_facts = dict(provider_result.report_facts)
        warnings = [*report_facts.get("warnings", []), *stable_tool_errors]
        report_facts["stable_tool_outcomes"] = stable_tool_outcomes
        if warnings:
            report_facts["warnings"] = warnings

        validation_result = await session.call_tool(
            "validate_logfile",
            {"logfile_path": draft_logfile},
        )
        _require_mcp_success(validation_result, action="validate_logfile")
        validation_payload = _structured_content(validation_result)
        inspect_result = await session.call_tool(
            "inspect_authoring",
            {
                "logfile_path": draft_logfile,
                "object_kind": "section",
                "detail": "full",
            },
        )
        _require_mcp_success(inspect_result, action="inspect_authoring")
        inspect_payload = _structured_content(inspect_result)
        items = inspect_payload.get("items", [])
        items = items if isinstance(items, list) else []
        section_ids = [
            str(item.get("ref", {}).get("object_id", "")).strip()
            for item in items
            if isinstance(item, Mapping)
            and isinstance(item.get("ref"), Mapping)
            and str(item.get("ref", {}).get("object_id", "")).strip()
        ]
        sections = [
            {
                "id": section_id,
                "track_ids": [
                    str(track.get("id", "")).strip()
                    for track in item.get("object", {}).get("tracks", [])
                    if isinstance(track, Mapping) and str(track.get("id", "")).strip()
                ],
            }
            for item, section_id in zip(items, section_ids, strict=True)
            if isinstance(item, Mapping) and isinstance(item.get("object"), Mapping)
        ]
        if not section_ids:
            warnings.append("Stable inspection returned no report sections.")

        current_draft_text = output_path.read_text(encoding="utf-8")
        changed = current_draft_text != baseline_draft_text
        summary_lines: list[str] = []
        for outcome in stable_tool_outcomes:
            payload = outcome.get("payload")
            if not isinstance(payload, Mapping):
                continue
            structured = payload.get("structured")
            if not isinstance(structured, Mapping) or structured.get("changed") is not True:
                continue
            summary_lines.append(
                f"Applied stable MCP tool `{outcome.get('name', 'unknown')}` to the draft."
            )
        if changed and not summary_lines:
            summary_lines.append("Persisted stable MCP authoring changes to the draft.")
        change_summary_payload = {
            "changed": changed,
            "summary_lines": summary_lines,
        }
        draft_summary_payload = {
            "section_ids": section_ids,
            "sections": sections,
        }
        inspect_summary_payload = {
            "object_kind": "section",
            "section_ids": section_ids,
            "sections": sections,
        }

        report_preview_result = await session.call_tool(
            "preview_logfile",
            {"logfile_path": draft_logfile, "page": 0},
        )
        _require_mcp_success(report_preview_result, action="preview_logfile")
        section_preview_result = await session.call_tool(
            "preview_logfile",
            {
                "logfile_path": draft_logfile,
                "section_id": section_ids[0] if section_ids else None,
                "page": 0,
            },
        )
        _require_mcp_success(section_preview_result, action="preview_logfile")
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
            inspect_summary=inspect_summary_payload,
            change_summary=change_summary_payload,
            draft_text=current_draft_text,
            report_preview_png=self.runtime.image_bytes(report_preview_result),
            section_preview_png=self.runtime.image_bytes(section_preview_result),
            report_facts=report_facts,
            user_report=_build_user_report(
                request_text=goal,
                validation=validation_payload,
                draft_summary=draft_summary_payload,
                change_summary=change_summary_payload,
                tool_trace=provider_result.tool_trace,
                report_facts=report_facts,
            ),
        )

    async def _execute_catalog_fallback(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        goal: str,
        stable_tool_outcomes: list[dict[str, object]],
        stable_tool_errors: list[str],
    ) -> tuple[bool, str]:
        """Execute one catalog or open-world track plan after provider stagnation."""
        candidates = catalog_channel_candidates(goal)
        if not candidates and not is_track_request(goal):
            return False, "No catalog or generic track request was found."

        async def call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
            """Call and record one deterministic fallback tool operation."""
            call_arguments = _catalog_fallback_tool_arguments(
                name,
                arguments,
                draft_logfile,
            )
            try:
                result = await session.call_tool(name, call_arguments)
                payload = self.runtime.tool_result_payload(result)
            except Exception as exc:  # noqa: BLE001 - report fallback diagnostics
                payload = {
                    "is_error": True,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            stable_tool_outcomes.append(
                {
                    "name": name,
                    "arguments": call_arguments,
                    "payload": payload,
                    "source": "catalog_fallback",
                }
            )
            if payload.get("is_error") is True:
                stable_tool_errors.append(
                    f"{name} failed: {payload.get('error', 'MCP returned an error result.')}"
                )
            return payload

        current = load_authoring_document(
            self.runtime.server_root / draft_logfile,
            allowed_root=self.runtime.server_root,
        )
        section_id = _catalog_fallback_section_id(goal, current)
        if section_id is None:
            return False, "Catalog fallback requires one resolvable target section."
        section = next(item for item in current.sections if item.id == section_id)
        source_arguments: dict[str, object] = {"include_metadata": False}
        if candidates:
            source_arguments["channels"] = list(candidates)
        if section.data_source is not None:
            source_path = Path(section.data_source.source_path)
            if not source_path.is_absolute():
                source_path = Path(draft_logfile).parent / source_path
            source_arguments.update(
                {
                    "source_path": source_path.as_posix(),
                    "source_format": section.data_source.source_format,
                }
            )
        source_payload = await call_tool(
            "inspect_source",
            source_arguments,
        )
        if source_payload.get("is_error") is True:
            return False, "Catalog fallback could not inspect source-channel availability."

        available: list[str] = []
        channel_summaries: dict[str, Mapping[str, object]] = {}
        structured = source_payload.get("structured")
        if isinstance(structured, Mapping):
            for key in ("available_channels", "found_channels"):
                top_level = structured.get(key)
                if isinstance(top_level, list):
                    available.extend(str(channel) for channel in top_level)
            items = structured.get("items", [])
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, Mapping):
                        continue
                    summaries = item.get("channels")
                    if isinstance(summaries, list):
                        for summary in summaries:
                            if not isinstance(summary, Mapping):
                                continue
                            mnemonic = summary.get("mnemonic")
                            if isinstance(mnemonic, str) and mnemonic.strip():
                                channel_summaries[mnemonic.upper()] = summary
                                available.append(mnemonic)
                    found = item.get("found_channels")
                    if isinstance(found, list):
                        available.extend(str(channel) for channel in found)
                    resolutions = item.get("resolutions", [])
                    if isinstance(resolutions, list):
                        for resolution in resolutions:
                            if not isinstance(resolution, Mapping):
                                continue
                            matched = resolution.get("matched_channels")
                            if isinstance(matched, list):
                                available.extend(str(channel) for channel in matched)

        plan = build_catalog_fallback_plan(
            goal,
            section_id=section_id,
            document=current.model_dump(mode="json"),
            available_channels=available,
            channel_summaries=channel_summaries,
        )
        if plan is None:
            return False, "The request did not resolve to a catalog or generic track plan."
        if fallback_plan_satisfied(plan, current.model_dump(mode="json")):
            return (
                True,
                f"Catalog request is already satisfied by `{plan.track_id}`; "
                "no recovery mutation was needed.",
            )

        for operation in plan.operations:
            payload = await call_tool(operation.tool_name, operation.arguments)
            if payload.get("is_error") is True:
                return False, f"Catalog fallback stopped at {operation.tool_name}."

        validation_payload = await call_tool("validate_logfile", {})
        if validation_payload.get("is_error") is True or not bool(
            (validation_payload.get("structured") or {}).get("valid", True)
        ):
            return False, "Catalog fallback mutations did not produce a valid logfile."

        inspection_payload = await call_tool(
            "inspect_authoring",
            {
                "object_kind": "track",
                "section_id": plan.section_id,
                "track_id": plan.track_id,
                "detail": "full",
            },
        )
        if inspection_payload.get("is_error") is True:
            return False, "Catalog fallback could not read back the created track."
        saved = load_authoring_document(
            self.runtime.server_root / draft_logfile,
            allowed_root=self.runtime.server_root,
        )
        if not fallback_plan_satisfied(plan, saved.model_dump(mode="json")):
            return False, "Catalog fallback postconditions did not match the persisted document."

        details = [
            f"Created or reconciled `{plan.track_id}` from catalog family "
            f"`{plan.family_id or plan.preset_id or 'generic'}`.",
        ]
        if plan.expected_channels:
            details.append(f"Bound available channels: {', '.join(plan.expected_channels)}.")
        if plan.skipped_channels:
            details.append(
                "Skipped unavailable catalog channels: "
                + ", ".join(plan.skipped_channels)
                + "."
            )
        return True, " ".join(details)

    async def _run_stable_mcp_loop(
        self,
        *,
        session: McpSessionProtocol,
        mcp_tools: list[object],
        draft_logfile: str,
        request_kind: str,
        goal: str,
        example_id: str | None,
        source_logfile_path: str | None,
        baseline_draft_text: str | None,
        max_rounds: int,
    ) -> AuthoringResult:
        if baseline_draft_text is None:
            create_arguments: dict[str, object] = {
                "operation": "create" if example_id is not None else "clone",
                "logfile_path": draft_logfile,
                "overwrite": True,
            }
            if example_id is not None:
                create_arguments["kind"] = example_id
            elif source_logfile_path is not None:
                create_arguments["source_logfile_path"] = source_logfile_path
            create_result = await session.call_tool("create_draft", create_arguments)
            _require_mcp_success(create_result, action="create_draft")
            output_path = self.runtime.server_root / draft_logfile
            if not output_path.exists():
                raise RuntimeError("create_draft returned without creating the requested draft.")
            baseline_draft_text = output_path.read_text(encoding="utf-8")

        baseline_document = load_authoring_document(
            self.runtime.server_root / draft_logfile,
            allowed_root=self.runtime.server_root,
        )
        preflight_header_result: ProviderRunResult | None = None
        preflight_header_outcome: dict[str, object] | None = None
        packet_header_intent = _extract_packet_header_fill_intent(goal)
        if packet_header_intent is not None and packet_header_intent.values:
            (
                preflight_header_result,
                preflight_header_outcome,
            ) = await self._execute_stable_header_fill(
                session=session,
                draft_logfile=draft_logfile,
                intent=packet_header_intent,
            )
        preflight_result = await session.call_tool(
            "inspect_authoring",
            {
                "logfile_path": draft_logfile,
                "object_kind": "section",
                "detail": "full",
            },
        )
        _require_mcp_success(preflight_result, action="inspect_authoring")
        tool_definitions = self.runtime.build_tool_definitions(
            mcp_tools,
            allowed_names=set(STABLE_MCP_TOOL_NAMES),
            excluded_names=(
                {"edit_header"}
                if preflight_header_result is not None
                else set()
            ),
        )
        allowed_names = {tool.name for tool in tool_definitions}
        stable_tool_outcomes: list[dict[str, object]] = []
        if preflight_header_outcome is not None:
            stable_tool_outcomes.append(preflight_header_outcome)
        stable_tool_errors: list[str] = []
        scope_tools = _stable_scope_tool_names(goal)
        mutation_counts: Counter[str] = Counter()
        controller_status: str | None = None
        controller_message = ""
        consecutive_tool_errors = 0
        repeated_error_count = 0
        last_error_signature: tuple[str, str] | None = None
        no_progress_calls = 0
        catalog_fallback_attempted = False
        singular_remarks_request = bool(
            re.search(r"\badd\s+(?:one|a|an)\b[^.\n]*\b(?:remarks?|notes?)\b", goal, re.I)
        )
        has_checkable_postconditions = bool(
            _quoted_request_value(goal, r"section\s+subtitle")
            or _quoted_request_value(goal, r"(?:first\s+)?service\s+title")
            or singular_remarks_request
            or re.search(
                r"\bdo\s+not\s+add\s+any\s+additional\s+tracks?\b",
                goal,
                re.IGNORECASE,
            )
        )
        mutation_names = {
            "edit_header",
            "edit_report_settings",
            "edit_remarks",
            "edit_section",
            "replicate_section_structure",
            "edit_track",
            "edit_curve_binding",
            "edit_raster_binding",
            "edit_fill",
            "edit_annotation",
        }

        def rejected_tool_payload(message: str) -> dict[str, object]:
            """Record one host-rejected call and apply the same circuit breaker."""
            nonlocal controller_message
            nonlocal controller_status
            nonlocal consecutive_tool_errors
            nonlocal last_error_signature
            nonlocal repeated_error_count

            stable_tool_errors.append(message)
            consecutive_tool_errors += 1
            error_signature = ("host", message)
            if error_signature == last_error_signature:
                repeated_error_count += 1
            else:
                repeated_error_count = 1
                last_error_signature = error_signature
            if consecutive_tool_errors >= 3 or repeated_error_count >= 2:
                controller_status = "blocked"
                controller_message = (
                    "The feedback loop stopped after repeated rejected tool calls. "
                    f"Last rejection: {message}"
                )
            feedback = {
                "status": controller_status or "continue",
                "message": controller_message
                or "Correct the tool arguments and continue with the requested scope.",
            }
            payload: dict[str, object] = {
                "is_error": True,
                "error": message,
                "agent_feedback": feedback,
            }
            if controller_status == "blocked":
                payload["_agent_control"] = {
                    "action": "stop",
                    "status": "blocked",
                    "message": controller_message,
                }
            return payload

        def resolve_numeric_header_alias(arguments: dict[str, object]) -> None:
            """Resolve model-friendly numeric indexes to stable header slot IDs."""
            operation = str(arguments.get("operation") or "")
            if operation not in {"set_slot", "clear_slot", "set_service_title"}:
                return
            field_name = "service_title" if operation == "set_service_title" else "slot_id"
            raw_value = arguments.get(field_name)
            if raw_value is None:
                return
            index_text = str(raw_value).strip()
            if not index_text.isdigit():
                return
            try:
                current = load_authoring_document(
                    self.runtime.server_root / draft_logfile,
                    allowed_root=self.runtime.server_root,
                )
            except Exception:
                return
            header = current.header
            if header is None:
                return
            if field_name == "service_title":
                slots = list(header.service_titles)
            else:
                slots = list(header.general_fields)
                if header.detail is not None:
                    for row in header.detail.rows:
                        slots.extend(row.values)
                        for column in row.columns:
                            slots.extend(column.cells)
            index = int(index_text)
            if 0 <= index < len(slots):
                arguments[field_name] = str(slots[index].slot_id)

        async def tool_caller(name: str, arguments: dict[str, object]) -> dict[str, object]:
            nonlocal controller_message
            nonlocal controller_status
            nonlocal consecutive_tool_errors
            nonlocal last_error_signature
            nonlocal no_progress_calls
            nonlocal repeated_error_count
            nonlocal catalog_fallback_attempted

            if controller_status in {"blocked", "completed"}:
                return {
                    "ok": controller_status == "completed",
                    "agent_feedback": {
                        "status": controller_status,
                        "message": controller_message,
                    },
                    "_agent_control": {
                        "action": "stop",
                        "status": controller_status,
                        "message": controller_message,
                    },
                }
            call_arguments = _normalize_stable_tool_arguments(name, arguments)
            section_scoped_tools = {
                "edit_report_settings",
                "edit_section",
                "edit_track",
                "edit_curve_binding",
                "edit_raster_binding",
                "edit_fill",
                "edit_annotation",
            }
            if (
                name in section_scoped_tools
                and call_arguments.get("section_id") is None
                and len(baseline_document.sections) == 1
            ):
                call_arguments["section_id"] = baseline_document.sections[0].id
            if name not in allowed_names:
                message = f"Tool `{name}` is not in the stable MCP profile."
                return rejected_tool_payload(message)
            if scope_tools is not None and name in mutation_names and name not in scope_tools:
                message = f"Tool `{name}` is outside the explicit request scope."
                return rejected_tool_payload(message)
            if singular_remarks_request and name == "edit_remarks" and mutation_counts[name] >= 1:
                message = "The request allows one new remarks block; do not add another."
                return rejected_tool_payload(message)
            if name == "inspect_authoring":
                object_kind_aliases = {
                    "header": "header_slot",
                    "curve": "curve_binding",
                    "raster": "raster_binding",
                    "remarks": "remark",
                    "report": "page",
                }
                object_kind = str(call_arguments.get("object_kind") or "section").lower()
                call_arguments["object_kind"] = object_kind_aliases.get(
                    object_kind,
                    object_kind,
                )
            if name == "inspect_source":
                source_format = call_arguments.get("source_format")
                if source_format is None or str(source_format).lower() == "none":
                    call_arguments["source_format"] = "auto"
                source_path = call_arguments.get("source_path")
                if source_path is not None:
                    candidate = Path(str(source_path)).expanduser()
                    if not candidate.is_absolute():
                        candidate = self.runtime.server_root / candidate
                    if not candidate.exists():
                        call_arguments.pop("source_path", None)
            if name == "edit_header":
                resolve_numeric_header_alias(call_arguments)
            if name not in {"create_draft", "inspect_vocab"} and not (
                name == "inspect_source" and call_arguments.get("source_path") is not None
            ):
                call_arguments.setdefault("logfile_path", draft_logfile)
            try:
                result = await session.call_tool(name, call_arguments)
                payload = self.runtime.tool_result_payload(result)
            except Exception as exc:
                payload = {
                    "is_error": True,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            stable_tool_outcomes.append(
                {
                    "name": name,
                    "arguments": call_arguments,
                    "payload": payload,
                }
            )
            repeated_read_only_call = name not in mutation_names and any(
                previous.get("name") == name
                and previous.get("arguments") == call_arguments
                for previous in stable_tool_outcomes[:-1]
            )
            if payload.get("is_error") is True:
                stable_tool_errors.append(
                    f"{name} failed: {payload.get('error', 'MCP returned an error result.')}"
                )
            structured = payload.get("structured")
            if (
                isinstance(structured, Mapping)
                and structured.get("changed") is True
                and name in mutation_names
            ):
                mutation_counts[name] += 1
                no_progress_calls = 0
            else:
                no_progress_calls += 1

            if payload.get("is_error") is True:
                consecutive_tool_errors += 1
                error_signature = (name, str(payload.get("error", "")))
                if error_signature == last_error_signature:
                    repeated_error_count += 1
                else:
                    repeated_error_count = 1
                    last_error_signature = error_signature
            else:
                consecutive_tool_errors = 0
                repeated_error_count = 0
                last_error_signature = None

            feedback: dict[str, object] = {
                "status": "continue",
                "message": (
                    "Continue only if the next tool call makes measurable progress. "
                    "Use the current persisted state and returned before/after evidence."
                ),
            }
            if payload.get("is_error") is True and name == "edit_track":
                error_text = str(payload.get("error", ""))
                operation = str(call_arguments.get("operation") or "").strip().lower()
                if operation == "update" and "Unknown track_ids" in error_text:
                    feedback["message"] = (
                        "The requested track does not exist. For a requested new track, "
                        "call edit_track with operation='add', use track_id as the new id, "
                        "and provide title, kind, and width_mm. The add operation appends "
                        "the track; use operation='move' afterward if placement matters. "
                        "Do not retry update for this missing track."
                    )
                elif "section_id" in error_text:
                    feedback["message"] = (
                        "This operation targets a section. Provide section_id explicitly; "
                        "only a single-section draft can infer it automatically."
                    )
            if payload.get("is_error") is True and name == "edit_section":
                operation = str(call_arguments.get("operation") or "").strip().lower()
                if operation == "add":
                    feedback["message"] = (
                        "A section add requires a complete section object with a non-empty "
                        "tracks list. If the requested section should copy an existing "
                        "section, call replicate_section_structure with the source and "
                        "target section ids, then edit the copied tracks and bindings."
                    )
            if payload.get("is_error") is True and name == "edit_report_settings":
                feedback["message"] = (
                    "Use one typed settings operation: set_report for report title/subtitle, "
                    "set_page for page settings, set_output for output settings, set_depth "
                    "for the depth axis, set_section_view for section title/subtitle/window, "
                    "or set_matplotlib_style for report-wide drawing style."
                )
            if repeated_read_only_call and payload.get("is_error") is not True:
                feedback["message"] = (
                    "This identical read-only inspection already succeeded. Do not repeat it. "
                    "Use its returned state and call the relevant edit_* mutation now; "
                    "preserve any values not requested by the user."
                )
            requested_mutations = (
                sorted(scope_tools & mutation_names) if scope_tools is not None else []
            )
            has_persisted_mutation = any(
                outcome.get("name") in mutation_names
                and isinstance(outcome.get("payload"), Mapping)
                and isinstance(outcome["payload"].get("structured"), Mapping)
                and outcome["payload"]["structured"].get("changed") is True
                for outcome in stable_tool_outcomes
            )
            if (
                payload.get("is_error") is not True
                and no_progress_calls >= 3
                and requested_mutations
                and not has_persisted_mutation
                and not catalog_fallback_attempted
            ):
                feedback["message"] = (
                    "Several read-only inspections have succeeded without a persisted mutation. "
                    "Stop repeating inspection tools and execute the requested mutation now. "
                    f"Requested mutation families: {', '.join(requested_mutations)}. "
                    "For a new track, use edit_track with operation='add', then use "
                    "operation='move' if placement was requested; bind curves only after "
                    "the target track exists."
                )
                if _catalog_fallback_section_id(goal, baseline_document) is None:
                    feedback["message"] = (
                        str(feedback["message"])
                        + " This request spans multiple sections or has no resolvable target; "
                        "do not use single-section catalog recovery."
                    )
                else:
                    catalog_fallback_attempted = True
                    fallback_succeeded, fallback_message = (
                        await self._execute_catalog_fallback(
                            session=session,
                            draft_logfile=draft_logfile,
                            goal=goal,
                            stable_tool_outcomes=stable_tool_outcomes,
                            stable_tool_errors=stable_tool_errors,
                        )
                    )
                    if fallback_succeeded:
                        controller_status = "completed"
                        controller_message = fallback_message
                        no_progress_calls = 0
                    else:
                        feedback["message"] = (
                            str(feedback["message"])
                            + " Catalog recovery was not applied: "
                            + fallback_message
                        )
            remaining: list[str] | None = None
            if payload.get("is_error") is not True and has_checkable_postconditions:
                try:
                    remaining = _stable_postcondition_errors(
                        goal,
                        baseline_document,
                        root=self.runtime.server_root,
                        draft_logfile=draft_logfile,
                    )
                except Exception as exc:  # noqa: BLE001 - return feedback to the provider
                    remaining = [f"Postcondition inspection failed: {type(exc).__name__}: {exc}"]
                feedback["remaining_postconditions"] = remaining
            if payload.get("is_error") is True and (
                consecutive_tool_errors >= 3 or repeated_error_count >= 2
            ):
                controller_status = "blocked"
                controller_message = (
                    "The feedback loop stopped after repeated MCP tool errors. "
                    f"Last failure: {payload.get('error', 'unknown MCP error')}"
                )
            elif no_progress_calls >= 6:
                controller_status = "blocked"
                controller_message = (
                    "The feedback loop stopped after six tool calls without a persisted "
                    "mutation. Inspect the reported state and retry with a smaller request."
                )
            elif (
                isinstance(structured, Mapping)
                and structured.get("changed") is True
                and has_checkable_postconditions
            ):
                if remaining is not None and not remaining:
                    controller_status = "completed"
                    controller_message = (
                        "All explicit request postconditions are persisted and verified. "
                        "Stop calling tools and report the completed work."
                    )

            if controller_status in {"blocked", "completed"}:
                feedback = {
                    "status": controller_status,
                    "message": controller_message,
                }
                payload["_agent_control"] = {
                    "action": "stop",
                    "status": controller_status,
                    "message": controller_message,
                }
            payload["agent_feedback"] = feedback
            return payload

        instructions = (
            "You are the wellplot authoring agent. Use only the supplied stable MCP tools. "
            "The draft has already been created at the supplied logfile path. Inspect the "
            "current canonical objects or source before editing. Preserve unspecified values "
            "and objects. After every mutation, use its returned before/after evidence; if a "
            "tool reports an error, correct the arguments instead of claiming success. "
            "For a new section copied from an existing section, use "
            "replicate_section_structure; do not synthesize an incomplete section object. "
            "Finish only after validation and a concise report of completed and blocked work."
        )
        try:
            provider_result = await self.backend.run_authoring(
                instructions=instructions,
                initial_user_message=(f"Draft: {draft_logfile}\n\nRequest:\n{goal}"),
                tool_definitions=tool_definitions,
                tool_caller=tool_caller,
                max_rounds=max_rounds,
            )
        except ProviderAdapterError as exc:
            report_facts = dict(exc.report_facts)
            report_facts.setdefault("warnings", []).append(f"Provider error: {exc}")
            provider_result = ProviderRunResult(
                final_text=exc.final_text,
                tool_trace=exc.tool_trace,
                report_facts=report_facts,
            )
        except Exception as exc:
            provider_result = ProviderRunResult(
                final_text="",
                tool_trace=(),
                report_facts={
                    "warnings": [f"Provider error: {type(exc).__name__}: {exc}"],
                    "reasons": ["The stable provider loop stopped before completion."],
                },
            )
        report_facts = dict(provider_result.report_facts)
        if preflight_header_result is not None:
            preflight_facts = dict(preflight_header_result.report_facts)
            for key in ("completed", "not_done", "reasons", "warnings"):
                preflight_values = preflight_facts.get(key, [])
                current_values = report_facts.get(key, [])
                if isinstance(preflight_values, list):
                    if not isinstance(current_values, list):
                        current_values = []
                    report_facts[key] = preflight_values + current_values
            report_facts["deterministic_header_preflight"] = True
            provider_result = replace(
                provider_result,
                tool_trace=preflight_header_result.tool_trace + provider_result.tool_trace,
                report_facts=report_facts,
            )
        report_facts = dict(provider_result.report_facts)

        def mark_header_preflight_rolled_back(facts: dict[str, object]) -> None:
            """Keep the report truthful when the full request is rolled back."""
            if preflight_header_result is None:
                return
            completed = facts.get("completed", [])
            if isinstance(completed, list):
                facts["completed"] = [
                    item
                    for item in completed
                    if item != "Applied the qualified header value through stable `edit_header`."
                ]
            not_done = facts.get("not_done", [])
            if not isinstance(not_done, list):
                not_done = []
            not_done.append("Deterministic header values were rolled back with the request.")
            facts["not_done"] = not_done

        warnings = report_facts.get("warnings", [])
        provider_failed = isinstance(warnings, list) and any(
            isinstance(item, str) and item.startswith("Provider error:") for item in warnings
        )
        if (
            not provider_failed
            and not catalog_fallback_attempted
            and _catalog_fallback_section_id(goal, baseline_document) is not None
            and (catalog_channel_candidates(goal) or is_track_request(goal))
        ):
            catalog_fallback_attempted = True
            fallback_succeeded, fallback_message = await self._execute_catalog_fallback(
                session=session,
                draft_logfile=draft_logfile,
                goal=goal,
                stable_tool_outcomes=stable_tool_outcomes,
                stable_tool_errors=stable_tool_errors,
            )
            report_facts = dict(provider_result.report_facts)
            report_facts["catalog_recovery"] = fallback_message
            if fallback_succeeded:
                controller_status = "completed"
                controller_message = fallback_message
                completed = report_facts.get("completed", [])
                if not isinstance(completed, list):
                    completed = []
                completed.append(fallback_message)
                report_facts["completed"] = completed
            else:
                controller_status = "blocked"
                controller_message = fallback_message
                not_done = report_facts.get("not_done", [])
                if not isinstance(not_done, list):
                    not_done = []
                not_done.append("Reconcile the catalog-defined track request deterministically.")
                report_facts["not_done"] = not_done
                reasons = report_facts.get("reasons", [])
                if not isinstance(reasons, list):
                    reasons = []
                reasons.append(fallback_message)
                report_facts["reasons"] = reasons
            provider_result = replace(provider_result, report_facts=report_facts)
        report_facts["feedback_loop"] = {
            "status": controller_status or "provider_finished",
            "consecutive_tool_errors": consecutive_tool_errors,
            "repeated_error_count": repeated_error_count,
            "no_progress_calls": no_progress_calls,
        }
        provider_result = replace(provider_result, report_facts=report_facts)
        controller_blocked = controller_status == "blocked"
        if provider_failed or controller_blocked:
            output_path = self.runtime.server_root / draft_logfile
            output_path.write_text(baseline_draft_text, encoding="utf-8")
            report_facts["rolled_back"] = True
            mark_header_preflight_rolled_back(report_facts)
            not_done = report_facts.get("not_done", [])
            if not isinstance(not_done, list):
                not_done = []
            not_done.append("Persist stable MCP authoring changes.")
            report_facts["not_done"] = not_done
            reasons = report_facts.get("reasons", [])
            if not isinstance(reasons, list):
                reasons = []
            reasons.append(
                controller_message
                if controller_blocked
                else "The provider failed before the request could be verified."
            )
            report_facts["reasons"] = reasons
            provider_result = replace(provider_result, report_facts=report_facts)
        if not provider_failed:
            try:
                scope_errors = _stable_postcondition_errors(
                    goal,
                    baseline_document,
                    root=self.runtime.server_root,
                    draft_logfile=draft_logfile,
                )
            except Exception as exc:  # noqa: BLE001 - report verification failures
                scope_errors = [
                    f"Stable request postcondition inspection failed: {type(exc).__name__}: {exc}"
                ]
            if scope_errors:
                output_path = self.runtime.server_root / draft_logfile
                output_path.write_text(baseline_draft_text, encoding="utf-8")
                report_facts = dict(provider_result.report_facts)
                report_facts["rolled_back"] = True
                mark_header_preflight_rolled_back(report_facts)
                not_done = report_facts.get("not_done", [])
                if not isinstance(not_done, list):
                    not_done = []
                not_done.append(
                    "Persist stable MCP authoring changes after postcondition verification."
                )
                report_facts["not_done"] = not_done
                report_facts["reasons"] = scope_errors
                provider_result = replace(provider_result, report_facts=report_facts)
        try:
            return await self._finalize_stable_result(
                session=session,
                draft_logfile=draft_logfile,
                request_kind=request_kind,
                goal=goal,
                example_id=example_id,
                source_logfile_path=source_logfile_path,
                baseline_draft_text=baseline_draft_text,
                provider_result=provider_result,
                stable_tool_outcomes=stable_tool_outcomes,
                stable_tool_errors=stable_tool_errors,
            )
        except Exception:
            output_path = self.runtime.server_root / draft_logfile
            if output_path.exists():
                output_path.write_text(baseline_draft_text, encoding="utf-8")
            raise

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
        resolution = resolve_authoring_context(
            intent,
            existing=existing,
            defaults=defaults_resolution.defaults,
            available_channels=available_channels,
        )
        reconciliation_plan = reconcile_authoring(resolution, existing=existing)
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
        operation_payloads = tuple(
            {
                "operation_id": operation.operation_id,
                "phase": operation.phase.value,
                "action": operation.action.value,
                "object_kind": operation.object_kind.value,
                "object_id": operation.object_id,
                "section_id": operation.section_id,
                "track_id": operation.track_id,
                "payload": operation.payload,
            }
            for operation in reconciliation_plan.operations
        )
        resolution_decisions = tuple(
            decision.model_dump(mode="json") for decision in resolution.decisions
        )
        applied_defaults_provenance = {
            decision.path: defaults_resolution.provenance[decision.path]
            for decision in resolution.decisions
            if decision.source.value == "default"
            and decision.path in defaults_resolution.provenance
        }
        return AuthoringPlanResult(
            mode="desired_state",
            packet_blueprint_id=None,
            phases=tuple(phases),
            blocked=not reconciliation_plan.ready,
            blocked_reasons=tuple(issue.message for issue in reconciliation_plan.issues),
            warnings=tuple(reconciliation_plan.warnings),
            run_state=AuthoringRunState(
                objectives=tuple(phase.summary for phase in phases),
            ),
            defaults_provenance={
                **defaults_resolution.matched_families,
                **defaults_resolution.provenance,
            },
            applied_defaults_provenance=applied_defaults_provenance,
            resolved_values=dict(resolution.resolved_values),
            resolution_decisions=resolution_decisions,
            operation_payloads=operation_payloads,
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
        preview_payload = _structured_content(preview_result)
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
                clarification_question = entry.get("clarification_question")
                if isinstance(clarification_question, str) and clarification_question.strip():
                    input_key = str(entry.get("input_key", "requested header value")).strip()
                    not_done.append(
                        f"Did not apply the value for `{input_key}`; clarification is required."
                    )
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
                "needs_clarification": _header_clarification_entries(preview_payload),
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

    def _remember_header_clarifications(
        self,
        draft_logfile: str,
        result: AuthoringResult,
    ) -> None:
        """Store or clear pending header choices for one in-memory draft session."""
        if result.needs_clarification:
            self._pending_header_clarifications[draft_logfile] = result.needs_clarification
        else:
            self._pending_header_clarifications.pop(draft_logfile, None)

    async def _continue_header_clarification(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        request_kind: str,
        feedback: str,
        baseline_draft_text: str,
        stable_tools_available: bool = False,
    ) -> AuthoringResult | None:
        """Apply a recognized clarification choice after revalidating its target."""
        pending = self._pending_header_clarifications.get(draft_logfile, ())
        selection = _select_pending_header_target(feedback, pending)
        if selection is None:
            return None
        clarification, target = selection
        selection_key = _header_clarification_target_key(target)
        original_value = clarification.get("input_value")
        if selection_key is None or original_value is None:
            return None
        overwrite_policy = str(clarification.get("overwrite_policy", "replace"))
        if overwrite_policy not in {"fill_empty", "replace", "merge_lists"}:
            overwrite_policy = "replace"

        intent = _HeaderFillIntent(
            values=((selection_key, str(original_value)),),
            overwrite_policy=overwrite_policy,
        )
        if stable_tools_available:
            return await self._run_stable_header_fill(
                session=session,
                draft_logfile=draft_logfile,
                request_kind=request_kind,
                goal=feedback,
                example_id=None,
                source_logfile_path=None,
                baseline_draft_text=baseline_draft_text,
                intent=intent,
            )

        inspect_result = await session.call_tool(
            "inspect_heading_slots",
            {"logfile_path": draft_logfile},
        )
        _require_mcp_success(inspect_result, action="inspect_heading_slots")
        preview_result = await session.call_tool(
            "preview_header_mapping",
            {
                "logfile_path": draft_logfile,
                "values": {selection_key: str(original_value)},
                "overwrite_policy": "replace",
            },
        )
        _require_mcp_success(preview_result, action="preview_header_mapping")
        preview_payload = _structured_content(preview_result)
        resolved_assignments = preview_payload.get("resolved_assignments", [])
        target_key = str(target.get("target_key", "")).strip()
        target_label = str(target.get("display_label", "")).strip()
        target_is_present = (
            any(
                isinstance(assignment, dict)
                and (
                    str(assignment.get("target_key", "")).strip() == target_key
                    or str(assignment.get("display_label", "")).strip() == target_label
                )
                for assignment in resolved_assignments
            )
            if isinstance(resolved_assignments, list)
            else False
        )
        if not target_is_present:
            clarification_entry = dict(clarification)
            reason = (
                f"The selected header field `{target_label or target_key}` is no longer "
                "available in the current draft."
            )
            provider_result = ProviderRunResult(
                final_text="Header clarification was blocked during current-draft revalidation.",
                tool_trace=(
                    AuthoringToolCall(
                        round=1,
                        name="inspect_heading_slots",
                        arguments={"logfile_path": draft_logfile},
                    ),
                    AuthoringToolCall(
                        round=1,
                        name="preview_header_mapping",
                        arguments={
                            "logfile_path": draft_logfile,
                            "values": {selection_key: str(original_value)},
                            "overwrite_policy": "replace",
                        },
                    ),
                ),
                report_facts={
                    "not_done": ["Apply the selected header value."],
                    "reasons": [reason],
                    "needs_clarification": [clarification_entry],
                    "next_help": [
                        "I can inspect the current heading slots and ask for a new choice."
                    ],
                },
            )
            return await self._finalize_result(
                session=session,
                draft_logfile=draft_logfile,
                request_kind=request_kind,
                goal=feedback,
                example_id=None,
                source_logfile_path=None,
                baseline_draft_text=baseline_draft_text,
                provider_result=provider_result,
            )

        intent = _HeaderFillIntent(
            values=((selection_key, str(original_value)),),
            overwrite_policy=overwrite_policy,
        )
        result = await self._run_deterministic_header_fill(
            session=session,
            draft_logfile=draft_logfile,
            request_kind=request_kind,
            goal=feedback,
            example_id=None,
            source_logfile_path=None,
            baseline_draft_text=baseline_draft_text,
            intent=intent,
        )
        object.__setattr__(
            result,
            "tool_trace",
            (
                AuthoringToolCall(
                    round=1,
                    name="inspect_heading_slots",
                    arguments={"logfile_path": draft_logfile},
                ),
                AuthoringToolCall(
                    round=1,
                    name="preview_header_mapping",
                    arguments={
                        "logfile_path": draft_logfile,
                        "values": {selection_key: str(original_value)},
                        "overwrite_policy": "replace",
                    },
                ),
            )
            + result.tool_trace,
        )
        return result

    async def _apply_deterministic_matplotlib_style(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        intent: _MatplotlibStyleIntent,
        tool_name: str = "set_matplotlib_style",
    ) -> AuthoringToolCall:
        """Apply one deterministic report-wide Matplotlib style patch."""
        if tool_name == "edit_report_settings":
            arguments = {
                "logfile_path": draft_logfile,
                "operation": "set_matplotlib_style",
                "style_patch": intent.style_patch,
            }
        else:
            arguments = {
                "logfile_path": draft_logfile,
                "style_patch": intent.style_patch,
            }
        result = await session.call_tool(
            tool_name,
            arguments,
        )
        _require_mcp_success(result, action=tool_name)
        return AuthoringToolCall(
            round=1,
            name=tool_name,
            arguments=arguments,
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

    async def _run_stable_header_fill(
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
        """Apply a narrow header request through the stable MCP projection."""
        provider_result, stable_tool_outcome = await self._execute_stable_header_fill(
            session=session,
            draft_logfile=draft_logfile,
            intent=intent,
        )
        return await self._finalize_stable_result(
            session=session,
            draft_logfile=draft_logfile,
            request_kind=request_kind,
            goal=goal,
            example_id=example_id,
            source_logfile_path=source_logfile_path,
            baseline_draft_text=baseline_draft_text,
            provider_result=provider_result,
            stable_tool_outcomes=[stable_tool_outcome],
            stable_tool_errors=[],
        )

    async def _execute_stable_header_fill(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        intent: _HeaderFillIntent,
    ) -> tuple[ProviderRunResult, dict[str, object]]:
        """Apply stable header values without finalizing the surrounding request."""
        arguments = {
            "logfile_path": draft_logfile,
            "operation": "apply_values",
            "values": intent.as_mapping(),
            "overwrite_policy": intent.overwrite_policy,
        }
        result = await session.call_tool("edit_header", arguments)
        _require_mcp_success(result, action="edit_header")
        payload = self.runtime.tool_result_payload(result)
        structured = payload.get("structured")
        if not isinstance(structured, Mapping):
            structured = {}

        skipped = structured.get("skipped_assignments", [])
        conflicts = [
            {
                "input_key": entry.get("input_key"),
                "input_value": entry.get("input_value"),
                "clarification_question": entry.get("clarification_question"),
                "candidate_labels": entry.get("candidate_labels", []),
                "candidate_targets": entry.get("candidate_targets", []),
            }
            for entry in skipped
            if isinstance(entry, Mapping)
            and entry.get("status") == "conflict"
            and entry.get("clarification_question")
        ] if isinstance(skipped, list) else []
        applied = structured.get("applied_assignments", [])
        applied_count = len(applied) if isinstance(applied, list) else 0
        completed = (
            ["Applied the qualified header value through stable `edit_header`."]
            if applied_count
            else []
        )
        not_done = (
            [
                f"Did not apply `{entry.get('input_key', 'the requested header value')}`; "
                "clarification is required."
                for entry in conflicts
            ]
            + [
                f"Did not apply `{entry.get('input_key', 'the requested header value')}`."
                for entry in skipped
                if isinstance(entry, Mapping)
                and entry.get("status") not in {"conflict", "unchanged"}
            ]
            if isinstance(skipped, list)
            else []
        )
        provider_result = ProviderRunResult(
            final_text=(
                "Applied deterministic stable header assignment"
                f" ({applied_count} applied, "
                f"{len(skipped) if isinstance(skipped, list) else 0} skipped)."
            ),
            tool_trace=(
                AuthoringToolCall(
                    round=1,
                    name="edit_header",
                    arguments=arguments,
                ),
            ),
            report_facts={
                "completed": completed,
                "not_done": not_done,
                "reasons": [
                    str(entry.get("reason"))
                    for entry in skipped
                    if (
                        isinstance(entry, Mapping)
                        and entry.get("status") != "unchanged"
                        and entry.get("reason")
                    )
                ] if isinstance(skipped, list) else [],
                "warnings": list(structured.get("warnings", []))
                if isinstance(structured.get("warnings"), list)
                else [],
                "needs_clarification": _header_clarification_entries(
                    {
                        "overwrite_policy": intent.overwrite_policy,
                        "conflicting_values": conflicts,
                    }
                ),
            },
        )
        return provider_result, {
            "name": "edit_header",
            "arguments": arguments,
            "payload": payload,
        }

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

    async def _extract_request_inventory(
        self,
        *,
        request_text: str,
        draft_logfile: str,
        existing: AuthoringDocumentSpec,
        context_snapshot: AuthoringContextSnapshot,
        max_rounds: int,
    ) -> tuple[
        ProviderRunResult,
        AuthoringRequestManifest,
        AuthoringRequestInventory | None,
    ]:
        """Classify a request before direct branch-operation compilation."""
        request_manifest = build_request_manifest(request_text)
        inventory = build_deterministic_narrow_inventory(request_manifest)
        if inventory is not None:
            return (
                ProviderRunResult(
                    final_text="Classified one deterministic narrow report request.",
                    tool_trace=(),
                    report_facts={
                        "request_manifest": request_manifest.model_dump(mode="json"),
                        "request_inventory": inventory.model_dump(mode="json"),
                        "extraction": {
                            "status": "deterministic",
                            "inventory_attempts": 0,
                            "validation_failures": [],
                            "inventory_failures": [],
                            "tool_calls_emitted": False,
                        },
                    },
                ),
                request_manifest,
                inventory,
            )

        inventory = None
        attempts = 0
        validation_errors: list[str] = []
        inventory_errors: list[list[str]] = []

        async def submit_inventory(
            name: str,
            arguments: dict[str, object],
        ) -> dict[str, object]:
            """Validate one complete request inventory without mutating the draft."""
            nonlocal attempts, inventory
            if name != "submit_request_inventory":
                return {
                    "is_error": True,
                    "error": "Only submit_request_inventory is available at this stage.",
                }
            attempts += 1
            if attempts > 2:
                return {
                    "is_error": True,
                    "error": "Only one initial inventory and one correction are allowed.",
                }
            try:
                candidate = AuthoringRequestInventory.model_validate(arguments)
            except Exception as exc:  # Pydantic provides actionable schema details.
                validation_errors.append(
                    _sanitize_provider_text(str(exc), limit=800) or type(exc).__name__
                )
                return {
                    "is_error": True,
                    "error": f"Invalid request inventory: {exc}",
                }
            errors = validate_request_inventory(request_manifest, candidate.items)
            if errors:
                inventory_errors.append(list(errors))
                return {
                    "is_error": True,
                    "error": "Request inventory is incomplete or invalid:\n- "
                    + "\n- ".join(errors),
                }
            inventory = candidate
            return {
                "accepted": True,
                "message": "Request inventory validated for direct branch compilation.",
            }

        context = {
            "request": request_text,
            "request_manifest": request_manifest.model_dump(mode="json"),
            "current_document": existing.model_dump(mode="json"),
            "authoring_context": context_snapshot.model_dump(mode="json"),
        }
        tool = FunctionToolDefinition(
            name="submit_request_inventory",
            description=(
                "Classify every request clause once by canonical object family and action, "
                "copy explicit values, and preserve natural-language targets."
            ),
            parameters=AuthoringRequestInventory.model_json_schema(),
        )
        provider_result: ProviderRunResult
        try:
            raw_result = await self.backend.run_authoring(
                instructions=(
                    "You are the request-inventory stage of wellplot. Do not emit YAML, a "
                    "full-document desired state, or mutation calls. Classify every request "
                    "item exactly once. Use canonical object families, copy explicit values "
                    "without applying defaults, keep negative instructions in "
                    "preserve_constraints, and use unsupported or inconsistent only with a "
                    "concise reason."
                ),
                initial_user_message=(
                    "Submit the compact request inventory. Every request item must appear "
                    "exactly once. The typed inventory schema is supplied as the tool "
                    "schema.\n\nContext:\n" + json.dumps(context, indent=2, default=str)
                ),
                tool_definitions=[tool],
                tool_caller=submit_inventory,
                max_rounds=min(max_rounds, 3),
                required_tool_name="submit_request_inventory",
            )
            provider_result = ProviderRunResult(
                final_text=str(getattr(raw_result, "final_text", "")),
                tool_trace=tuple(getattr(raw_result, "tool_trace", ()) or ()),
                report_facts=dict(getattr(raw_result, "report_facts", {}) or {}),
            )
        except Exception as exc:
            status = _provider_exception_status(exc)
            message = _sanitize_provider_text(str(exc), limit=800) or type(exc).__name__
            provider_result = ProviderRunResult(
                final_text=str(getattr(exc, "final_text", "") or ""),
                tool_trace=tuple(getattr(exc, "tool_trace", ()) or ()),
                report_facts={
                    "provider_error": message,
                    "provider_failure_status": status,
                    "provider_failure_stage": "inventory",
                },
            )

        report_facts = dict(provider_result.report_facts)
        extraction_status = "submitted" if inventory is not None else "invalid"
        if inventory is None:
            error_status = report_facts.get("provider_failure_status")
            extraction_status = str(error_status or "submission_rejected")
        report_facts.update(
            {
                "request_manifest": request_manifest.model_dump(mode="json"),
                "request_inventory": (
                    None if inventory is None else inventory.model_dump(mode="json")
                ),
                "extraction": {
                    "status": extraction_status,
                    "inventory_attempts": attempts,
                    "validation_failures": validation_errors,
                    "inventory_failures": inventory_errors,
                    "tool_calls_emitted": bool(provider_result.tool_trace),
                },
            }
        )
        return (
            ProviderRunResult(
                final_text=provider_result.final_text,
                tool_trace=provider_result.tool_trace,
                report_facts=report_facts,
            ),
            request_manifest,
            inventory,
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
        """Compile one request through inventory and scoped typed submissions."""
        request_manifest = build_request_manifest(request_text)
        inventory: AuthoringRequestInventory | None = None
        inventory_attempts = 0
        scoped_attempts: dict[str, int] = {}
        validation_failures: list[str] = []
        coverage_failures: list[list[str]] = []
        inventory_failures: list[list[str]] = []
        merge_failures: list[str] = []
        failed_stages: list[str] = []
        stage_results: list[tuple[str, ProviderRunResult]] = []
        stage_messages: dict[str, int] = {}
        stage_schema_chars: dict[str, int] = {}
        scoped_submissions: dict[str, dict[str, object]] = {}
        request_work_units: tuple[AuthoringRequestWorkUnit, ...] = ()
        fragments: list[object] = []
        coverage: list[AuthoringIntentCoverage] = []
        provider_failure_status: str | None = None
        provider_stage_failures: list[dict[str, object]] = []
        corrected_failures: list[dict[str, object]] = []

        def normalize_result(result: object) -> ProviderRunResult:
            """Normalize lightweight test doubles and provider adapter results."""
            return ProviderRunResult(
                final_text=str(getattr(result, "final_text", "")),
                tool_trace=tuple(getattr(result, "tool_trace", ())),
                report_facts=dict(getattr(result, "report_facts", {})),
            )

        def provider_failure_result(stage: str, exc: BaseException) -> ProviderRunResult:
            """Normalize one failed provider stage while retaining partial evidence."""
            failure_facts = dict(getattr(exc, "report_facts", {}) or {})
            status = _provider_exception_status(exc)
            message = _sanitize_provider_text(str(exc), limit=800) or type(exc).__name__
            failure_facts["provider_error"] = message
            failure_facts["provider_failure_status"] = status
            failure_facts["provider_failure_stage"] = stage
            provider_stage_failures.append(
                {
                    "stage": stage,
                    "status": status,
                    "message": message,
                }
            )
            return ProviderRunResult(
                final_text=str(getattr(exc, "final_text", "") or ""),
                tool_trace=tuple(getattr(exc, "tool_trace", ()) or ()),
                report_facts=failure_facts,
            )

        async def submit_inventory(
            name: str,
            arguments: dict[str, object],
        ) -> dict[str, object]:
            """Validate a compact inventory without mutating the draft."""
            nonlocal inventory, inventory_attempts
            if name != "submit_request_inventory":
                return {
                    "is_error": True,
                    "error": (
                        "Only submit_request_inventory is available in request inventory mode."
                    ),
                }
            inventory_attempts += 1
            if inventory_attempts > 2:
                return {
                    "is_error": True,
                    "error": (
                        "Only one initial submission and one correction submission are "
                        "allowed for the request inventory."
                    ),
                }
            try:
                candidate = AuthoringRequestInventory.model_validate(arguments)
            except Exception as exc:  # Pydantic gives provider-actionable details.
                validation_failures.append(
                    _sanitize_provider_text(str(exc), limit=800) or type(exc).__name__
                )
                return {
                    "is_error": True,
                    "error": (
                        f"Invalid AuthoringRequestInventory: {exc}. Include exactly one "
                        "inventory item for every request item."
                    ),
                }
            errors = validate_request_inventory(
                request_manifest,
                candidate.items,
            )
            if errors:
                inventory_failures.append(list(errors))
                return {
                    "is_error": True,
                    "error": (
                        "Request inventory is incomplete or invalid. Submit one correction "
                        "with one item per request item:\n- " + "\n- ".join(errors)
                    ),
                }
            inventory = candidate
            if inventory_failures:
                corrected_failures.extend(
                    {"stage": "inventory", "errors": errors} for errors in inventory_failures
                )
                inventory_failures.clear()
            return {
                "accepted": True,
                "message": (
                    "Request inventory validated. Related canonical object families will "
                    "now be compiled through scoped typed contracts."
                ),
            }

        inventory_context = {
            "request": request_text,
            "request_manifest": request_manifest.model_dump(mode="json"),
        }
        inventory_instructions = (
            "You are the request-inventory stage of wellplot authoring. Do not emit a "
            "desired state and do not call mutation tools. Classify every request item "
            "exactly once by canonical object family and requested "
            "action. Keep the original clause as the request item context; preserve human "
            "target and natural parent descriptions when stable ids are unknown. Copy "
            "explicit values without applying defaults. Put negative instructions in "
            "preserve_constraints and ordering requirements in dependencies. Use "
            "unsupported or inconsistent only with a concise reason."
        )
        inventory_schema = AuthoringRequestInventory.model_json_schema()
        inventory_schema_chars = len(
            json.dumps(inventory_schema, separators=(",", ":"), default=str)
        )
        inventory_message = (
            "Submit the compact request inventory. Do not describe MCP calls or construct "
            "the final document. Every request item must appear exactly once.\n\n"
            f"Context:\n{json.dumps(inventory_context, indent=2, default=str)}\n\n"
            "The inventory schema is supplied as the function schema; do not repeat it."
        )
        inventory_tool = FunctionToolDefinition(
            name="submit_request_inventory",
            description=(
                "Submit one compact classification and value inventory for every request item."
            ),
            parameters=inventory_schema,
        )
        stage_messages["inventory"] = len(inventory_message)
        stage_schema_chars["inventory"] = inventory_schema_chars
        try:
            raw_result = await self.backend.run_authoring(
                instructions=inventory_instructions,
                initial_user_message=inventory_message,
                tool_definitions=[inventory_tool],
                tool_caller=submit_inventory,
                max_rounds=min(max_rounds, 3),
                required_tool_name="submit_request_inventory",
            )
            stage_results.append(("inventory", normalize_result(raw_result)))
        except Exception as exc:
            provider_failure_status = _provider_exception_status(exc)
            failed_stages.append("inventory")
            stage_results.append(("inventory", provider_failure_result("inventory", exc)))

        def compact_document(scope: AuthoringCompilationScope) -> dict[str, object]:
            """Return only current objects relevant to one compilation scope."""
            payload = existing.model_dump(mode="json")
            if scope == "report":
                keys = (
                    "title",
                    "subtitle",
                    "output",
                    "page",
                    "depth",
                    "header",
                    "tail",
                    "remarks",
                )
                return {key: payload[key] for key in keys if key in payload}

            sections = payload.get("sections", [])
            if not isinstance(sections, list):
                return {"sections": []}
            compact_sections: list[dict[str, object]] = []
            for section in sections:
                if not isinstance(section, dict):
                    continue
                compact_section = {
                    key: deepcopy(section[key])
                    for key in (
                        "id",
                        "title",
                        "subtitle",
                        "depth_range",
                        "data_source",
                    )
                    if key in section
                }
                compact_tracks: list[dict[str, object]] = []
                tracks = section.get("tracks", [])
                if not isinstance(tracks, list):
                    tracks = []
                for track in tracks:
                    if not isinstance(track, dict):
                        continue
                    compact_track = {
                        key: deepcopy(track[key])
                        for key in (
                            "id",
                            "title",
                            "kind",
                            "width_mm",
                            "x_scale",
                            "grid",
                            "track_header",
                        )
                        if key in track
                    }
                    if scope == "scalar":
                        bindings = track.get("bindings", [])
                        compact_track["bindings"] = [
                            deepcopy(binding)
                            for binding in bindings
                            if isinstance(binding, dict) and binding.get("kind", "curve") == "curve"
                        ]
                        compact_track["fills"] = deepcopy(track.get("fills", []))
                    elif scope == "raster":
                        bindings = track.get("bindings", [])
                        compact_track["bindings"] = [
                            deepcopy(binding)
                            for binding in bindings
                            if isinstance(binding, dict) and binding.get("kind") == "raster"
                        ]
                    elif scope == "annotation":
                        compact_track["annotations"] = deepcopy(track.get("annotations", []))
                    compact_tracks.append(compact_track)
                compact_section["tracks"] = compact_tracks
                compact_sections.append(compact_section)
            return {"sections": compact_sections}

        if inventory is not None:
            request_work_units = build_request_work_units(request_manifest, inventory)
            grouped = group_request_inventory(inventory)
            manifest_by_id = {item.item_id: item for item in request_manifest.items}
            context_payload = context_snapshot.model_dump(mode="json")
            for scope, inventory_items in grouped.items():
                item_ids = {item.request_item_id for item in inventory_items}
                scoped_work_units = [
                    unit.model_dump(mode="json")
                    for unit in request_work_units
                    if unit.request_item_id in item_ids
                ]
                scoped_manifest = AuthoringRequestManifest(
                    items=[
                        manifest_by_id[item_id] for item_id in manifest_by_id if item_id in item_ids
                    ]
                )
                submission_model = scoped_submission_model(scope)
                tool_name = f"submit_{scope}_intent"
                scoped_attempts[scope] = 0
                accepted_submission: object | None = None

                async def submit_scoped_intent(
                    name: str,
                    arguments: dict[str, object],
                    *,
                    expected_name: str = tool_name,
                    model: type = submission_model,
                    manifest: AuthoringRequestManifest = scoped_manifest,
                    stage: str = scope,
                    scoped_inventory: tuple[AuthoringRequestInventoryItem, ...] = tuple(
                        inventory_items
                    ),
                ) -> dict[str, object]:
                    """Validate one scoped typed fragment without mutation."""
                    nonlocal accepted_submission
                    if name != expected_name:
                        return {
                            "is_error": True,
                            "error": f"Only {expected_name} is available in this stage.",
                        }
                    scoped_attempts[stage] += 1
                    if scoped_attempts[stage] > 2:
                        return {
                            "is_error": True,
                            "error": (
                                "Only one initial submission and one correction submission "
                                f"are allowed for the {stage} scope."
                            ),
                        }
                    try:
                        candidate = model.model_validate(arguments)
                    except Exception as exc:
                        validation_failures.append(
                            f"{stage}: "
                            + (_sanitize_provider_text(str(exc), limit=800) or type(exc).__name__)
                        )
                        return {
                            "is_error": True,
                            "error": (
                                f"Invalid {model.__name__}: {exc}. Include only the "
                                f"canonical fields accepted by the {stage} contract."
                            ),
                        }
                    errors = validate_intent_coverage(manifest, candidate.coverage)
                    errors.extend(
                        validate_scoped_intent_semantics(
                            scoped_inventory,
                            candidate.intent,
                            candidate.coverage,
                        )
                    )
                    if errors:
                        coverage_failures.append([f"{stage}: {error}" for error in errors])
                        return {
                            "is_error": True,
                            "error": (
                                f"{stage.title()} request coverage is invalid. Submit one "
                                "correction:\n- " + "\n- ".join(errors)
                            ),
                        }
                    accepted_submission = candidate
                    return {
                        "accepted": True,
                        "message": (
                            f"{stage.title()} intent validated. It will be merged and "
                            "canonically validated before planning."
                        ),
                    }

                scoped_context: dict[str, object] = {
                    "draft_logfile": draft_logfile,
                    "request_items": scoped_manifest.model_dump(mode="json"),
                    "request_inventory": {
                        "items": [item.model_dump(mode="json") for item in inventory_items]
                    },
                    "work_units": scoped_work_units,
                    "current_objects": compact_document(scope),
                    "context_issues": context_payload.get("issues", []),
                }
                if scope == "report":
                    scoped_context["header_slots"] = context_payload.get("header_slots", {})
                else:
                    scoped_context["section_context"] = context_payload.get("sections", [])
                if scope in {"scalar", "raster", "annotation"}:
                    structure_submission = scoped_submissions.get("structure")
                    if structure_submission is not None:
                        scoped_context["compiled_structure"] = structure_submission["intent"]
                scoped_instructions = (
                    "You are one scoped desired-state compiler for wellplot authoring. "
                    f"Compile only the {scope} request items through the supplied typed "
                    "contract. Do not call mutation tools and do not include unrelated "
                    "branches. Use the supplied work units to preserve each original "
                    "clause and its natural parent; do not merge clauses from different "
                    "parents into one invented object. Omit preserved fields, use explicit "
                    "clear/remove "
                    "objects when requested, and retain every explicit label, ordering, "
                    "scale, grid, color, line style, width, and raster value exactly. "
                    "Use stable proposed ids and parent ids consistently; deterministic "
                    "context resolution will apply defaults and verify source channels."
                )
                scoped_message = (
                    f"Submit the {scope} typed fragment and coverage for only these "
                    "request items. The schema is supplied as the function schema.\n\n"
                    f"Context:\n{json.dumps(scoped_context, indent=2, default=str)}"
                )
                scoped_schema = submission_model.model_json_schema()
                stage_messages[scope] = len(scoped_message)
                stage_schema_chars[scope] = len(
                    json.dumps(scoped_schema, separators=(",", ":"), default=str)
                )
                scoped_tool = FunctionToolDefinition(
                    name=tool_name,
                    description=(
                        f"Submit the validated partial {scope} desired state and coverage "
                        "for this scope's request items."
                    ),
                    parameters=scoped_schema,
                )
                try:
                    raw_result = await self.backend.run_authoring(
                        instructions=scoped_instructions,
                        initial_user_message=scoped_message,
                        tool_definitions=[scoped_tool],
                        tool_caller=submit_scoped_intent,
                        max_rounds=min(max_rounds, 3),
                        required_tool_name=tool_name,
                    )
                    stage_results.append((scope, normalize_result(raw_result)))
                except Exception as exc:
                    if provider_failure_status is None:
                        provider_failure_status = _provider_exception_status(exc)
                    if scope not in failed_stages:
                        failed_stages.append(scope)
                    stage_results.append((scope, provider_failure_result(scope, exc)))
                if accepted_submission is None:
                    if scope not in failed_stages:
                        failed_stages.append(scope)
                    continue
                corrected_scope_errors = [
                    list(errors)
                    for errors in coverage_failures
                    if any(error.startswith(f"{scope}: ") for error in errors)
                ]
                if corrected_scope_errors:
                    corrected_failures.extend(
                        {"stage": scope, "errors": errors} for errors in corrected_scope_errors
                    )
                    coverage_failures[:] = [
                        errors
                        for errors in coverage_failures
                        if not any(error.startswith(f"{scope}: ") for error in errors)
                    ]
                fragment = accepted_submission.intent
                fragments.append(fragment)
                coverage.extend(accepted_submission.coverage)
                scoped_submissions[scope] = {
                    "intent": fragment.model_dump(mode="json", exclude_unset=True),
                    "coverage": [
                        entry.model_dump(mode="json") for entry in accepted_submission.coverage
                    ],
                }

            for item in inventory.items:
                if item.status not in {"unsupported", "inconsistent"}:
                    continue
                coverage.append(
                    AuthoringIntentCoverage(
                        unit_id=f"unit-{item.request_item_id}",
                        status=item.status,
                        reason=item.reason,
                    )
                )

        submitted: AuthoringDocumentIntent | None = None
        if inventory is not None and not failed_stages:
            final_coverage_errors = validate_intent_coverage(
                request_manifest,
                coverage,
            )
            if final_coverage_errors:
                coverage_failures.append(final_coverage_errors)
            else:
                try:
                    submitted = merge_scoped_intents(fragments)
                except Exception as exc:
                    merge_failures.append(
                        _sanitize_provider_text(str(exc), limit=800) or type(exc).__name__
                    )

        combined_trace = tuple(call for _, result in stage_results for call in result.tool_trace)
        failed_stage_set = set(failed_stages)
        if failed_stage_set:
            final_text = next(
                (
                    result.final_text
                    for stage, result in reversed(stage_results)
                    if stage in failed_stage_set
                ),
                "",
            )
        else:
            final_text = next(
                (
                    result.final_text
                    for _, result in reversed(stage_results)
                    if result.final_text.strip()
                ),
                "",
            )
        report_facts: dict[str, object] = {}
        provider_stages: list[dict[str, object]] = []
        for stage, result in stage_results:
            if result.report_facts:
                provider_stages.append({"stage": stage, **result.report_facts})
                for key, value in result.report_facts.items():
                    report_facts.setdefault(key, value)
        if failed_stage_set:
            for stage, result in reversed(stage_results):
                if stage in failed_stage_set:
                    report_facts.update(result.report_facts)
                    break
        if provider_stages:
            report_facts["provider_stages"] = provider_stages
        if provider_stage_failures:
            report_facts["provider_stage_failures"] = provider_stage_failures
        if corrected_failures:
            report_facts["corrected_failures"] = corrected_failures
        report_facts["request_manifest"] = request_manifest.model_dump(mode="json")
        if inventory is not None:
            report_facts["request_inventory"] = inventory.model_dump(mode="json")
            report_facts["request_work_units"] = [
                {
                    key: value
                    for key, value in unit.model_dump(mode="json").items()
                    if key != "phase" or value is not None
                }
                for unit in request_work_units
            ]
        report_facts["provider_contract"] = {
            "tool_name": "submit_request_inventory",
            "tool_names": [
                "submit_request_inventory",
                *[f"submit_{scope}_intent" for scope in stage_schema_chars if scope != "inventory"],
            ],
            "message_chars": sum(stage_messages.values()),
            "stage_message_chars": stage_messages,
            "tool_schema_chars": max(stage_schema_chars.values(), default=0),
            "stage_tool_schema_chars": stage_schema_chars,
            "request_inventory_schema_chars": inventory_schema_chars,
            "full_intent_schema_chars": len(
                json.dumps(
                    AuthoringDocumentIntent.model_json_schema(),
                    separators=(",", ":"),
                    default=str,
                )
            ),
            "schema_repeated_in_message": False,
        }
        if scoped_submissions:
            report_facts["scoped_submissions"] = scoped_submissions
        if submitted is not None:
            report_facts["submitted_intent"] = submitted.model_dump(
                mode="json",
                exclude_unset=True,
            )
            report_facts["request_coverage"] = [entry.model_dump(mode="json") for entry in coverage]
            report_facts["request_inconsistencies"] = [
                f"{entry.unit_id}: {entry.reason}"
                for entry in coverage
                if entry.status in {"unsupported", "inconsistent"} and entry.reason
            ]
        elif coverage_failures or inventory_failures or merge_failures or provider_stage_failures:
            reasons = [
                error for failure in (*inventory_failures, *coverage_failures) for error in failure
            ]
            reasons.extend(merge_failures)
            reasons.extend(
                f"Provider {failure['stage']} stage failed ({failure['status']}): "
                f"{failure['message']}"
                for failure in provider_stage_failures
            )
            report_facts["reasons"] = list(report_facts.get("reasons", [])) + [
                "Desired-state compilation failed: " + "; ".join(reasons)
            ]
        if submitted is not None:
            extraction_status = "submitted"
        elif provider_failure_status:
            extraction_status = provider_failure_status
        elif merge_failures:
            extraction_status = "merge_failed"
        elif inventory_failures:
            extraction_status = "inventory_coverage_failed"
        elif coverage_failures:
            extraction_status = "coverage_failed"
        elif validation_failures:
            extraction_status = "schema_validation_failed"
        elif combined_trace:
            extraction_status = "submission_rejected"
        else:
            extraction_status = "no_tool_call"
        extraction_facts: dict[str, object] = {
            "status": extraction_status,
            "submission_attempts": inventory_attempts + sum(scoped_attempts.values()),
            "inventory_attempts": inventory_attempts,
            "scoped_attempts": scoped_attempts,
            "tool_calls_emitted": bool(combined_trace),
            "validation_failures": validation_failures,
            "inventory_failures": inventory_failures,
            "coverage_failures": coverage_failures,
            "merge_failures": merge_failures,
            "failed_stages": failed_stages,
            "provider_stage_failures": provider_stage_failures,
            "corrected_failures": corrected_failures,
        }
        provider_text = _sanitize_provider_text(final_text)
        if provider_text is not None and submitted is None:
            extraction_facts["provider_text"] = provider_text
        report_facts["extraction"] = extraction_facts
        return (
            ProviderRunResult(
                final_text=final_text,
                tool_trace=combined_trace,
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

    async def _unsupported_provider_result(
        self,
        *,
        session: McpSessionProtocol,
        draft_logfile: str,
        request_kind: str,
        goal: str,
        example_id: str | None,
        source_logfile_path: str | None,
        baseline_draft_text: str,
        preflight_tool_trace: tuple[AuthoringToolCall, ...] = (),
    ) -> AuthoringResult:
        """Finalize a request when the provider cannot submit typed authoring data."""
        provider_name = str(self.backend.provider).strip() or "unknown"
        reason = (
            f"Provider `{provider_name}` does not support typed authoring extraction. "
            "The legacy provider-to-MCP mutation loop is disabled."
        )
        provider_result = ProviderRunResult(
            final_text="Natural-language authoring was blocked before mutation.",
            tool_trace=preflight_tool_trace,
            report_facts={
                "authoritative_completed": False,
                "extraction": {
                    "status": "unsupported_provider",
                    "tool_calls_emitted": False,
                },
                "not_done": ["Extract and apply the typed desired state for this request."],
                "reasons": [reason],
                "next_help": [
                    "Use a provider with typed authoring support or pass desired_state directly."
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
        request_coverage = tuple(
            dict(item)
            for item in report_facts.get("request_coverage", [])
            if isinstance(item, dict)
        )
        needs_clarification = _clarification_entries(report_facts.get("needs_clarification"))
        submitted_intent = (
            dict(report_facts["submitted_intent"])
            if isinstance(report_facts.get("submitted_intent"), dict)
            else None
        )
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
            needs_clarification=needs_clarification,
            request_coverage=request_coverage,
            defaults_provenance=({} if plan is None else dict(plan.defaults_provenance)),
            submitted_intent=submitted_intent,
            report_facts=report_facts,
            user_report=_build_user_report(
                request_text=goal,
                validation={"valid": False, "message": reason},
                draft_summary={},
                change_summary={"summary_lines": []},
                tool_trace=provider_result.tool_trace,
                report_facts=report_facts,
            ),
        )

    @staticmethod
    def _direct_operation_phase(object_family: str) -> AuthoringOperationPhase:
        """Return deterministic execution order for one canonical object family."""
        if object_family in {
            "report",
            "header",
            "header_slot",
            "service_title",
            "page",
            "output",
            "depth",
            "remarks",
            "tail",
        }:
            return AuthoringOperationPhase.REPORT
        if object_family == "section":
            return AuthoringOperationPhase.SECTIONS
        if object_family == "track":
            return AuthoringOperationPhase.TRACKS
        if object_family in {"curve_binding", "raster_binding"}:
            return AuthoringOperationPhase.BINDINGS
        if object_family == "annotation":
            return AuthoringOperationPhase.CONTENT
        return AuthoringOperationPhase.PRESENTATION

    @staticmethod
    def _plan_from_direct_submissions(
        *,
        submissions: Sequence[object],
        work_units: Sequence[AuthoringRequestWorkUnit],
        blocked_reasons: Sequence[str] = (),
    ) -> AuthoringPlanResult:
        """Build the public plan contract from accepted branch operations."""
        unit_by_id = {unit.unit_id: unit for unit in work_units}
        operation_payloads: list[dict[str, object]] = []
        operations_by_phase: dict[AuthoringOperationPhase, list[str]] = {}
        for submission in submissions:
            for operation in getattr(submission, "operations", ()):
                unit = unit_by_id.get(operation.work_unit_id)
                phase = (
                    unit.phase
                    if unit is not None and unit.phase is not None
                    else AuthoringOperationPhase.PRESENTATION
                )
                request = operation.request
                object_kind = operation_request_object_kind(request)
                payload = request.model_dump(mode="json")
                target = getattr(request, "target", None)
                object_id = getattr(target, "object_id", None) if target is not None else None
                if object_id is None:
                    object_payload = payload.get(object_kind)
                    if isinstance(object_payload, Mapping):
                        object_id = (
                            object_payload.get("id")
                            or object_payload.get("binding_id")
                            or object_payload.get("fill_id")
                            or object_payload.get("annotation_id")
                            or object_payload.get("remark_id")
                        )
                object_id = str(object_id or operation.operation_id)
                operation_payloads.append(
                    {
                        "operation_id": operation.operation_id,
                        "phase": phase.value,
                        "action": operation.action,
                        "object_kind": object_kind,
                        "object_id": object_id,
                        "section_id": getattr(request, "section_id", None),
                        "track_id": getattr(request, "track_id", None),
                        "payload": payload,
                    }
                )
                operations_by_phase.setdefault(phase, []).append(operation.operation_id)

        phases: list[AuthoringPlanPhase] = []
        for phase in AuthoringOperationPhase:
            operation_ids = operations_by_phase.get(phase, [])
            if not operation_ids:
                continue
            phases.append(
                AuthoringPlanPhase(
                    id=f"direct-{phase.value}",
                    kind=f"direct_operations_{phase.value}",
                    summary=f"Apply and verify direct {phase.value} operations.",
                    instructions=(
                        "Execute the branch-compiled operations atomically and verify every "
                        "canonical read-after-write postcondition."
                    ),
                    tool_families=("typed_authoring",),
                    success_checks=("all direct operations read back successfully",),
                    success_check_specs=(
                        {"kind": "typed_postconditions", "operation_ids": operation_ids},
                    ),
                    metadata={"operation_ids": operation_ids},
                )
            )
        return AuthoringPlanResult(
            mode="direct_operations",
            packet_blueprint_id=None,
            phases=tuple(phases),
            blocked=bool(blocked_reasons),
            blocked_reasons=tuple(blocked_reasons),
            run_state=AuthoringRunState(
                objectives=tuple(phase.summary for phase in phases),
            ),
            operation_payloads=tuple(operation_payloads),
        )

    async def _run_direct_operation_workflow(
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
    ) -> AuthoringResult:
        """Compile natural language into branch operations, then execute atomically."""
        from .branch_compiler import build_branch_operation_groups, compile_direct_branch_operations

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
        provider_result, request_manifest, inventory = await self._extract_request_inventory(
            request_text=request_text,
            draft_logfile=draft_logfile,
            existing=existing,
            context_snapshot=context_snapshot,
            max_rounds=max_rounds,
        )
        if inventory is None:
            report_facts = dict(provider_result.report_facts)
            extraction = report_facts.get("extraction", {})
            status = extraction.get("status") if isinstance(extraction, dict) else None
            reason = (
                "The provider connection failed before request inventory completed."
                if status == "transport_failure"
                else "The provider did not produce a valid request inventory."
            )
            report_facts["not_done"] = ["Classify the request into canonical work units."]
            report_facts["reasons"] = [reason]
            report_facts["next_help"] = [
                "Retry with a provider/model that supports the typed inventory tool contract."
            ]
            return await self._finalize_result(
                session=session,
                draft_logfile=draft_logfile,
                request_kind=request_kind,
                goal=request_text,
                example_id=example_id,
                source_logfile_path=source_logfile_path,
                baseline_draft_text=baseline_draft_text,
                provider_result=ProviderRunResult(
                    final_text="Direct operation planning was blocked before mutation.",
                    tool_trace=provider_result.tool_trace,
                    report_facts=report_facts,
                ),
            )

        all_work_units = build_request_work_units(request_manifest, inventory)
        actionable_work_units = tuple(
            unit
            for unit in all_work_units
            if unit.status not in {"unsupported", "inconsistent"}
            and compilation_scope_for_object_family(unit.object_family) is not None
        )
        phased_work_units = tuple(
            unit.model_copy(update={"phase": self._direct_operation_phase(unit.object_family)})
            for unit in actionable_work_units
        )
        source_channels = {
            section.section_id: [
                candidate.model_dump(mode="json") for candidate in section.available_channels
            ]
            for section in context_snapshot.sections
        }
        parent_snapshots: dict[str, object] = {}
        for section in existing.sections:
            section_payload = section.model_dump(mode="json")
            parent_snapshots[f"{section.id} section"] = section_payload
            for track in section.tracks:
                parent_snapshots[f"{track.id} track"] = track.model_dump(mode="json")
        context = {
            "current_document": existing.model_dump(mode="json"),
            "parent_snapshots": parent_snapshots,
            "source_channels": source_channels,
            "canonical_operations": authoring_operation_json_schema(),
            "canonical_hierarchy": authoring_hierarchy_catalog(),
            "applicable_defaults": {
                "form_defaults": form_default_catalog(),
                "track_archetypes": track_archetype_catalog(),
                "style_presets": style_preset_catalog(),
            },
        }
        groups = build_branch_operation_groups(phased_work_units, context=context)
        skipped_work_units = tuple(unit for unit in all_work_units if unit not in phased_work_units)
        skipped_request_items = [
            {
                "request_item_id": unit.request_item_id,
                "clause": unit.clause_text,
                "status": unit.status,
                "reason": unit.reason
                or "No direct operation branch is available for this object family.",
            }
            for unit in skipped_work_units
        ]
        compilation = await compile_direct_branch_operations(
            self.backend,
            groups,
            max_rounds=max_rounds,
        )
        plan = self._plan_from_direct_submissions(
            submissions=compilation.submissions,
            work_units=phased_work_units,
            blocked_reasons=compilation.blocked_reasons,
        )
        report_facts = {
            **provider_result.report_facts,
            "request_work_units": [unit.model_dump(mode="json") for unit in all_work_units],
            "request_coverage": [
                {
                    "request_item_id": unit.request_item_id,
                    "unit_id": unit.unit_id,
                    "status": unit.status,
                    "object_family": unit.object_family,
                    "natural_parent": unit.natural_parent,
                }
                for unit in all_work_units
            ],
            "direct_compilation": compilation.provider_facts,
            "correction_errors": list(compilation.correction_errors),
            "request_inconsistency_details": skipped_request_items,
            "request_inconsistencies": [
                f"Request item `{item['request_item_id']}` was skipped: {item['reason']}."
                for item in skipped_request_items
            ],
        }
        if not compilation.success:
            report_facts.update(
                {
                    "not_done": [phase.summary for phase in plan.phases]
                    or ["Compile direct branch operations."],
                    "reasons": list(compilation.blocked_reasons),
                    "next_help": [
                        "Inspect the blocked branch diagnostic and retry with the missing "
                        "parent, target, or explicit value clarified."
                    ],
                }
            )
            return await self._finalize_result(
                session=session,
                draft_logfile=draft_logfile,
                request_kind=request_kind,
                goal=request_text,
                example_id=example_id,
                source_logfile_path=source_logfile_path,
                baseline_draft_text=baseline_draft_text,
                provider_result=ProviderRunResult(
                    final_text="Direct branch-operation compilation was blocked before mutation.",
                    tool_trace=provider_result.tool_trace + compilation.tool_trace,
                    report_facts=report_facts,
                ),
                plan=plan,
            )

        service = AuthoringService(existing)
        try:
            typed_execution = execute_typed_submissions(
                service,
                compilation.submissions,
                phased_work_units,
            )
            execution = _authoring_execution_from_typed(plan, typed_execution)
        except Exception as exc:  # noqa: BLE001 - deterministic boundary report
            execution = AuthoringExecutionResult(
                success=False,
                stopped=True,
                document=existing,
                errors=(f"Direct operation execution failed: {type(exc).__name__}: {exc}",),
            )
            typed_execution = None
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
        completed_phases = [
            phase.summary for phase in phase_summaries if phase.status == "completed"
        ]
        blocked_phases = [phase.summary for phase in phase_summaries if phase.status != "completed"]
        if skipped_request_items:
            blocked_phases.extend(
                f"Skipped request item `{item['request_item_id']}`: {item['reason']}."
                for item in skipped_request_items
            )
        reasons = list(execution.errors)
        if save_error:
            reasons.append(f"Canonical direct-operation save failed: {save_error}")
        warnings = list(phase_preview_warnings)
        report_facts.update(
            {
                "authoritative_completed": True,
                "completed": _typed_operation_completion_lines(plan=plan, execution=execution),
                "not_done": blocked_phases,
                "reasons": reasons,
                "warnings": warnings,
                "operation_payloads": list(plan.operation_payloads),
                "operation_outcomes": [
                    outcome.model_dump(mode="json")
                    for outcome in (
                        typed_execution.outcomes
                        if typed_execution is not None
                        else execution.outcomes
                    )
                ],
                "next_help": (
                    [
                        "Inspect the blocked operation and correct its object identity or "
                        "source-channel reference before retrying."
                    ]
                    if reasons or skipped_request_items
                    else ["Continue with another typed revision or request a final render."]
                ),
            }
        )
        provider_result = ProviderRunResult(
            final_text=(
                "Direct branch operations executed and persisted."
                if execution.success and save_error is None
                else "Direct branch-operation execution was blocked."
            ),
            tool_trace=provider_result.tool_trace + compilation.tool_trace,
            report_facts=report_facts,
        )
        run_state = self._run_state_from_summary(
            draft_summary=summary,
            objectives=plan.run_state.objectives,
            completed_objectives=tuple(completed_phases),
            blocked_objectives=tuple(blocked_phases),
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
            report_facts = dict(provider_result.report_facts)
            extraction_facts = report_facts.get("extraction", {})
            extraction_status = (
                extraction_facts.get("status") if isinstance(extraction_facts, dict) else None
            )
            if extraction_status == "no_tool_call":
                extraction_reason = (
                    "The provider returned without submitting the typed authoring request."
                )
                extraction_next_help = (
                    "Retry with a provider/model that supports the typed authoring submission "
                    "contract."
                )
            elif extraction_status == "round_budget_exhausted":
                extraction_reason = "The provider exhausted its extraction round budget."
                extraction_next_help = (
                    "Retry with a larger provider context or a model that can complete the "
                    "typed authoring submission."
                )
            elif extraction_status == "transport_failure":
                extraction_reason = (
                    "The provider connection failed before typed authoring completed."
                )
                extraction_next_help = "Retry after verifying the provider endpoint and timeout."
            elif extraction_status == "invalid_json":
                extraction_reason = "The provider emitted malformed typed-submission arguments."
                extraction_next_help = (
                    "Retry with a provider that supports structured tool arguments."
                )
            elif extraction_status in {"schema_validation_failed", "submission_rejected"}:
                extraction_reason = (
                    "The provider submitted typed data that failed canonical validation."
                )
                extraction_next_help = (
                    "Inspect the reported validation details, then retry with a compatible "
                    "provider/model."
                )
            elif extraction_status == "coverage_failed":
                extraction_reason = "The provider did not account for every request item."
                extraction_next_help = (
                    "Retry with a provider that can return complete request coverage."
                )
            elif extraction_status == "merge_failed":
                extraction_reason = (
                    "The provider submission could not be merged into one canonical desired state."
                )
                extraction_next_help = (
                    "Retry after correcting the reported canonical field or identity conflict."
                )
            else:
                extraction_reason = "Typed authoring extraction did not produce a valid submission."
                extraction_next_help = (
                    "Retry with a provider/model that supports the typed authoring submission "
                    "contract."
                )
            report_facts["not_done"] = ["Extract a typed desired state from the request."]
            existing_reasons = report_facts.get("reasons")
            reasons = list(existing_reasons) if isinstance(existing_reasons, list) else []
            if extraction_reason not in reasons:
                reasons.append(extraction_reason)
            report_facts["reasons"] = reasons
            report_facts["next_help"] = [extraction_next_help]
            provider_error = report_facts.get("provider_error")
            if isinstance(provider_error, str) and provider_error.strip():
                report_facts["warnings"] = [f"Provider error: {provider_error}"]
            if isinstance(extraction_facts, dict):
                provider_text = extraction_facts.get("provider_text")
                if isinstance(provider_text, str) and provider_text.strip():
                    warnings = report_facts.get("warnings")
                    if not isinstance(warnings, list):
                        warnings = []
                        report_facts["warnings"] = warnings
                    warnings.append(f"Provider response: {provider_text}")
            provider_result = ProviderRunResult(
                final_text="Desired-state extraction did not produce a valid submission.",
                tool_trace=provider_result.tool_trace,
                report_facts=report_facts,
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
                    **provider_result.report_facts,
                    "not_done": [phase.summary for phase in plan.phases]
                    or ["Resolve and reconcile the typed desired state."],
                    "reasons": list(reasons),
                    "warnings": list(plan.warnings),
                    "next_help": list(_typed_plan_next_help(plan)),
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

        inventory_payload = provider_result.report_facts.get("request_inventory")
        if isinstance(inventory_payload, dict):
            try:
                request_inventory = AuthoringRequestInventory.model_validate(inventory_payload)
            except Exception as exc:
                fulfillment_errors = [
                    "The accepted request inventory could not be revalidated before "
                    f"execution: {type(exc).__name__}: {exc}"
                ]
            else:
                fulfillment_errors = validate_reconciliation_fulfillment(
                    request_inventory.items,
                    plan.operation_payloads,
                )
            if fulfillment_errors:
                blocked_plan = replace(
                    plan,
                    blocked=True,
                    blocked_reasons=tuple(fulfillment_errors),
                )
                provider_result = ProviderRunResult(
                    final_text="Typed desired-state plan was blocked before mutation.",
                    tool_trace=provider_result.tool_trace,
                    report_facts={
                        **provider_result.report_facts,
                        "not_done": ["Apply typed operations that fulfill every mapped request."],
                        "reasons": fulfillment_errors,
                        "warnings": list(blocked_plan.warnings),
                        "next_help": [
                            "Correct the typed intent so its planned operations match the "
                            "requested action and object family."
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
                    plan=blocked_plan,
                )

        service = AuthoringService(existing)
        typed_execution: TypedSubmissionExecutionResult | None = None
        try:
            compilation = compile_reconciliation_plan(
                plan.reconciliation_plan,
                service=service,
                defaults_provenance=plan.applied_defaults_provenance,
            )
            typed_execution = execute_typed_submissions(
                service,
                compilation.submissions,
                compilation.work_units,
                defaults_provenance_by_operation=compilation.defaults_provenance_by_operation,
            )
            execution = _authoring_execution_from_typed(plan, typed_execution)
        except Exception as exc:  # noqa: BLE001 - deterministic boundary report
            execution = AuthoringExecutionResult(
                success=False,
                stopped=True,
                document=existing,
                errors=(f"Typed reconciliation compilation failed: {type(exc).__name__}: {exc}",),
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

        completed_phases = [
            phase.summary for phase in phase_summaries if phase.status == "completed"
        ]
        blocked_phases = [phase.summary for phase in phase_summaries if phase.status != "completed"]
        completed_operations = _typed_operation_completion_lines(
            plan=plan,
            execution=execution,
        )
        reasons = list(execution.errors)
        if save_error:
            reasons.append(f"Canonical desired-state save failed: {save_error}")
        if not execution.success and not reasons:
            reasons.append("The deterministic executor stopped before all postconditions passed.")
        warnings = list(plan.warnings) + list(execution.warnings) + list(phase_preview_warnings)
        provider_result = ProviderRunResult(
            final_text=(
                "Typed desired state executed and persisted."
                if execution.success and save_error is None
                else "Typed desired-state execution was blocked."
            ),
            tool_trace=provider_result.tool_trace,
            report_facts={
                **provider_result.report_facts,
                "authoritative_completed": True,
                "completed": completed_operations,
                "not_done": blocked_phases,
                "reasons": reasons,
                "warnings": warnings,
                "applied_defaults_provenance": plan.applied_defaults_provenance,
                "resolved_values": plan.resolved_values,
                "resolution_decisions": list(plan.resolution_decisions),
                "operation_payloads": list(plan.operation_payloads),
                "operation_outcomes": [
                    outcome.model_dump(mode="json")
                    for outcome in (
                        typed_execution.outcomes
                        if typed_execution is not None
                        else execution.outcomes
                    )
                ],
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
            completed_objectives=tuple(completed_phases),
            blocked_objectives=tuple(blocked_phases),
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
        # A new authoring run overwrites the draft and must not inherit choices
        # from an earlier clarification conversation.
        self._pending_header_clarifications.pop(relative_output_logfile, None)
        relative_source_logfile = (
            None
            if request.source_logfile_path is None
            else _relative_logfile_path(self.runtime.server_root, request.source_logfile_path)
        )

        async with self.runtime.open_session() as session:
            if request.desired_state is None:
                stable_tools = await self._stable_tool_catalog(session)
                if stable_tools is not None:
                    return await self._run_stable_mcp_loop(
                        session=session,
                        mcp_tools=stable_tools,
                        draft_logfile=relative_output_logfile,
                        request_kind="author",
                        goal=request.goal,
                        example_id=request.example_id,
                        source_logfile_path=relative_source_logfile,
                        baseline_draft_text=None,
                        max_rounds=request.max_rounds,
                    )
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
                self._remember_header_clarifications(relative_output_logfile, result)
                if preflight_tool_trace:
                    object.__setattr__(
                        result,
                        "tool_trace",
                        preflight_tool_trace + result.tool_trace,
                    )
                return result

            if request.desired_state is not None:
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
            if bool(getattr(self.backend, "supports_direct_operations", False)):
                return await self._run_direct_operation_workflow(
                    session=session,
                    draft_logfile=relative_output_logfile,
                    request_kind="author",
                    request_text=effective_goal,
                    example_id=request.example_id,
                    source_logfile_path=relative_source_logfile,
                    baseline_draft_text=baseline_draft_text,
                    max_rounds=request.max_rounds,
                )
            if bool(getattr(self.backend, "supports_scoped_intent_compatibility", False)):
                return await self._run_desired_state_workflow(
                    session=session,
                    draft_logfile=relative_output_logfile,
                    request_kind="author",
                    request_text=effective_goal,
                    example_id=request.example_id,
                    source_logfile_path=relative_source_logfile,
                    baseline_draft_text=baseline_draft_text,
                    max_rounds=request.max_rounds,
                    desired_state=None,
                )
            return await self._unsupported_provider_result(
                session=session,
                draft_logfile=relative_output_logfile,
                request_kind="author",
                goal=request.goal,
                example_id=request.example_id,
                source_logfile_path=relative_source_logfile,
                baseline_draft_text=baseline_draft_text,
                preflight_tool_trace=preflight_tool_trace,
            )

    async def revise_request(self, request: RevisionRequest) -> AuthoringResult:
        """Run one revision request against an existing draft logfile."""
        relative_logfile = _relative_logfile_path(self.runtime.server_root, request.logfile_path)
        output_path = self.runtime.server_root / relative_logfile
        if not output_path.exists():
            raise FileNotFoundError(f"Draft logfile does not exist: {output_path}")

        async with self.runtime.open_session() as session:
            baseline_draft_text = output_path.read_text(encoding="utf-8")
            original_draft_text = baseline_draft_text
            stable_tools = await self._stable_tool_catalog(session)

            preflight_tool_trace: tuple[AuthoringToolCall, ...] = ()
            style_intent, remaining_feedback = _extract_matplotlib_style_intent(
                request.feedback
            )
            effective_feedback = remaining_feedback if remaining_feedback else request.feedback
            if style_intent is not None:
                style_tool_name = "set_matplotlib_style"
                if stable_tools is not None:
                    available_tool_names = {
                        str(getattr(tool, "name", "")) for tool in stable_tools
                    }
                    if "set_matplotlib_style" not in available_tool_names:
                        style_tool_name = (
                            "edit_report_settings"
                            if "edit_report_settings" in available_tool_names
                            else ""
                        )
                if not style_tool_name:
                    effective_feedback = request.feedback
                else:
                    style_tool_call = await self._apply_deterministic_matplotlib_style(
                        session=session,
                        draft_logfile=relative_logfile,
                        intent=style_intent,
                        tool_name=style_tool_name,
                    )
                    preflight_tool_trace = (style_tool_call,)
                    baseline_draft_text = output_path.read_text(encoding="utf-8")
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
                            baseline_draft_text=original_draft_text,
                            provider_result=provider_result,
                        )

            # Narrow header fills must use the deterministic label resolver. If
            # they enter the provider loop first, a model can select a similar
            # visible row even when the requested qualifier is unambiguous.
            continuation = await self._continue_header_clarification(
                session=session,
                draft_logfile=relative_logfile,
                request_kind="revise",
                feedback=effective_feedback,
                baseline_draft_text=baseline_draft_text,
                stable_tools_available=stable_tools is not None,
            )
            if continuation is not None:
                self._remember_header_clarifications(relative_logfile, continuation)
                return continuation

            deterministic_header_fill = _extract_header_fill_intent(effective_feedback)
            if deterministic_header_fill is not None:
                if stable_tools is not None:
                    result = await self._run_stable_header_fill(
                        session=session,
                        draft_logfile=relative_logfile,
                        request_kind="revise",
                        goal=request.feedback,
                        example_id=None,
                        source_logfile_path=None,
                        baseline_draft_text=baseline_draft_text,
                        intent=deterministic_header_fill,
                    )
                else:
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
                self._remember_header_clarifications(relative_logfile, result)
                return result

            if stable_tools is not None:
                result = await self._run_stable_mcp_loop(
                    session=session,
                    mcp_tools=stable_tools,
                    draft_logfile=relative_logfile,
                    request_kind="revise",
                    goal=effective_feedback,
                    example_id=None,
                    source_logfile_path=None,
                    baseline_draft_text=baseline_draft_text,
                    max_rounds=request.max_rounds,
                )
                if preflight_tool_trace:
                    object.__setattr__(
                        result,
                        "tool_trace",
                        preflight_tool_trace + result.tool_trace,
                    )
                return result

            continuation = await self._continue_header_clarification(
                session=session,
                draft_logfile=relative_logfile,
                request_kind="revise",
                feedback=effective_feedback,
                baseline_draft_text=baseline_draft_text,
                stable_tools_available=False,
            )
            if continuation is not None:
                self._remember_header_clarifications(relative_logfile, continuation)
                if preflight_tool_trace:
                    object.__setattr__(
                        continuation,
                        "tool_trace",
                        preflight_tool_trace + continuation.tool_trace,
                    )
                return continuation

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
                self._remember_header_clarifications(relative_logfile, result)
                if preflight_tool_trace:
                    object.__setattr__(
                        result,
                        "tool_trace",
                        preflight_tool_trace + result.tool_trace,
                    )
                return result

            if request.desired_state is not None:
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
            if bool(getattr(self.backend, "supports_direct_operations", False)):
                return await self._run_direct_operation_workflow(
                    session=session,
                    draft_logfile=relative_logfile,
                    request_kind="revise",
                    request_text=effective_feedback,
                    example_id=None,
                    source_logfile_path=None,
                    baseline_draft_text=baseline_draft_text,
                    max_rounds=request.max_rounds,
                )
            if bool(getattr(self.backend, "supports_scoped_intent_compatibility", False)):
                return await self._run_desired_state_workflow(
                    session=session,
                    draft_logfile=relative_logfile,
                    request_kind="revise",
                    request_text=effective_feedback,
                    example_id=None,
                    source_logfile_path=None,
                    baseline_draft_text=baseline_draft_text,
                    max_rounds=request.max_rounds,
                    desired_state=None,
                )
            return await self._unsupported_provider_result(
                session=session,
                draft_logfile=relative_logfile,
                request_kind="revise",
                goal=request.feedback,
                example_id=None,
                source_logfile_path=None,
                baseline_draft_text=baseline_draft_text,
                preflight_tool_trace=preflight_tool_trace,
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
                "render_logfile",
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
            _require_mcp_success(result, action="render_logfile")
        payload = _structured_content(result)
        if "output_path" not in payload and "artifact" in payload:
            payload["output_path"] = payload["artifact"]
        return payload

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
    timeout: float | None = None,
    max_rounds: int = 12,
) -> AuthoringResult:
    """Run one high-level authoring request against local stdio MCP."""
    session = AuthoringSession.from_local_mcp(
        provider=provider,
        model=model,
        server_root=server_root,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
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
    timeout: float | None = None,
    max_rounds: int = 12,
) -> AuthoringResult:
    """Revise one existing draft logfile against local stdio MCP."""
    session = AuthoringSession.from_local_mcp(
        provider=provider,
        model=model,
        server_root=server_root,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
    )
    return await session.revise(
        feedback=feedback,
        logfile_path=logfile_path,
        max_rounds=max_rounds,
    )
