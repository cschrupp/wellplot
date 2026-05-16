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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

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
    "inspect_data_source",
    "check_channel_availability",
    "inspect_header_archetypes",
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


@dataclass(frozen=True)
class AuthoringRequest:
    """High-level natural-language authoring request."""

    goal: str
    output_logfile: str
    example_id: str | None = None
    source_logfile_path: str | None = None
    max_rounds: int = 12

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
            user_report=_build_user_report(
                request_text=goal,
                validation=validation_payload,
                draft_summary=draft_summary_payload,
                change_summary=change_summary_payload,
                tool_trace=provider_result.tool_trace,
                report_facts=getattr(provider_result, "report_facts", {}),
            ),
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
            )
        )

    async def revise(
        self,
        *,
        feedback: str,
        logfile_path: str | Path,
        max_rounds: int = 12,
    ) -> AuthoringResult:
        """Revise one existing draft logfile through the provider-backed agent loop."""
        return await self.revise_request(
            RevisionRequest(
                feedback=feedback,
                logfile_path=_relative_logfile_path(self.runtime.server_root, logfile_path),
                max_rounds=max_rounds,
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
