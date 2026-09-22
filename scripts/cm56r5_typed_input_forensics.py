"""CM-56R5 typed-input representation and planner forensics."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from scripts.cm56_post_r4_typed_shadow import production_source_summary
from scripts.cm56_typed_section_shadow import (
    _case_request,
    _document,
    _provider_category,
    audit_input_sufficiency,
    build_fixture_enricher,
    build_source_candidates,
    case_corpus_sha256,
    evaluate_semantic_draft,
    load_case_definitions,
)
from scripts.cm56r2_planner_diagnostic import safe_plan_projection
from wellplot.agent.code_mode.enrichment import (
    ResolvedSectionContext,
    SemanticEnrichmentError,
)
from wellplot.agent.code_mode.planner import SectionTask, SemanticPlanner
from wellplot.agent.code_mode.section_semantics import (
    SectionSemanticDraft,
    SectionSemanticValidationError,
    validate_section_semantics,
)
from wellplot.agent.code_mode.semantic_section_compiler import (
    SectionSemanticCompilationError,
    compile_section_semantics,
)
from wellplot.agent.code_mode.typed_section_worker import (
    RESPONSE_SCHEMA_SHA256,
    TYPED_SECTION_SYSTEM_PROMPT,
    build_typed_section_input,
    response_schema_sha256,
    serialize_typed_section_input,
)
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProviderRequestError,
    StructuredGenerationRequest,
)
from wellplot.authoring_program.inspection import AuthoringInspectionFacade
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry

EXPERIMENT_VERSION = "CM-56R5.v1"
PLANNER_TEMPERATURE = 0.0
WORKER_TEMPERATURE = 1.0
MAX_OUTPUT_TOKENS = 16384
TIMEOUT_SECONDS = 900.0
REPRESENTATION_CASES = (
    "scalar_linear",
    "reverse_scale",
    "generic_raster",
    "waveform",
    "cbl_continuity",
    "vdl_sample_axis",
)
PRIMARY_CASES = frozenset(
    {
        "scalar_linear",
        "reverse_scale",
        "generic_raster",
        "waveform",
        "cbl_continuity",
    }
)
REPEATED_CHANNEL_CASE = "repeated_channel"
REPEATED_CHANNEL_ATTEMPTS = 10

_NUMBER = r"[-+]?\d+(?:\.\d+)?"
_RANGE_RE = re.compile(rf"({_NUMBER})\s*(?:to|[-–])\s*({_NUMBER})", re.IGNORECASE)


class _DiagnosticModel(BaseModel):
    """Strict immutable model for evaluation-only diagnostic input."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ExplicitScale(_DiagnosticModel):
    """A scale field explicitly recovered from task prose."""

    kind: str | None = Field(default=None, min_length=1)
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool | None = None


class ExplicitSampleAxis(_DiagnosticModel):
    """Sample-axis fields explicitly preserved by the planner task."""

    unit: str | None = Field(default=None, min_length=1)
    source_origin: float | None = None
    source_step: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    tick_count: int | None = Field(default=None, ge=2)


class ExplicitBinding(_DiagnosticModel):
    """One provider-visible binding with only sourced semantic fields."""

    local_semantic_id: str = Field(min_length=1)
    kind: Literal["curve", "raster"]
    channel: str = Field(min_length=1)
    scale: ExplicitScale | None = None
    profile: str | None = Field(default=None, min_length=1)
    sample_axis: ExplicitSampleAxis | None = None


class ExplicitTrack(_DiagnosticModel):
    """One provider-visible track with partial facts allowed."""

    local_semantic_id: str = Field(min_length=1)
    kind: Literal["normal", "reference", "array"]
    title: str | None = Field(default=None, min_length=1)
    x_scale: ExplicitScale | None = None
    bindings: tuple[ExplicitBinding, ...] = ()


class ExplicitSemanticBlock(_DiagnosticModel):
    """A diagnostic A-plus block built from the frozen task/context only."""

    title: str | None = Field(default=None, min_length=1)
    source_candidate: str | None = Field(default=None, min_length=1)
    tracks: tuple[ExplicitTrack, ...] = ()


class ProvenanceRecord(_DiagnosticModel):
    """One auditable link from an explicit field to task/context evidence."""

    output_path: str = Field(min_length=1)
    provider_path: str = Field(min_length=1)
    evidence_path: str = Field(min_length=1)
    evidence_class: Literal["task", "context", "diagnostic_local_identity"]
    evidence_sha256: str = Field(min_length=64, max_length=64)


class ExplicitSemanticAudit(_DiagnosticModel):
    """Executable audit result for every field added by Variant B."""

    valid: bool
    records: tuple[ProvenanceRecord, ...]
    missing_output_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PairInput:
    """Paired A/B payloads derived from one task/context."""

    task: SectionTask
    section_context: ResolvedSectionContext
    variant_a: str
    variant_b: str
    explicit_block: ExplicitSemanticBlock
    audit: ExplicitSemanticAudit


def build_pair_input(
    task: SectionTask,
    *,
    section_context: ResolvedSectionContext,
    registry: CapabilityRegistry,
    task_context_case: Mapping[str, object] | None = None,
) -> PairInput:
    """Build exact production A and diagnostic A-plus-B payloads."""
    del task_context_case
    typed_input = build_typed_section_input(
        task,
        section_context=section_context,
        registry=registry,
    )
    variant_a = serialize_typed_section_input(typed_input)
    block, records = build_explicit_semantics(task, section_context=section_context)
    audit = audit_explicit_semantics(block, records, task=task, section_context=section_context)
    if not audit.valid:
        raise ValueError(
            "CM-56R5 explicit semantic input lacks allowed provenance: "
            + ", ".join(audit.missing_output_paths)
        )
    payload = json.loads(variant_a)
    payload["explicit_semantics"] = block.model_dump(mode="json", exclude_none=True)
    variant_b = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return PairInput(task, section_context, variant_a, variant_b, block, audit)


def build_explicit_semantics(
    task: SectionTask,
    *,
    section_context: ResolvedSectionContext,
) -> tuple[ExplicitSemanticBlock, tuple[ProvenanceRecord, ...]]:
    """Extract explicit worker facts from task/context without expected gold."""
    task_text = _task_text(task)
    lower_text = task_text.lower()
    sources = tuple(section_context.sources)
    source = sources[0] if len(sources) == 1 else _source_from_task(task, sources)
    records: list[ProvenanceRecord] = []
    title, title_evidence = _section_title(task, source, task_text)
    if title is not None:
        records.append(
            _record(
                "explicit_semantics.title",
                "title",
                title,
                "task" if title_evidence == "task" else "context",
                task_text,
            )
        )
    source_candidate = source.candidate_id if source is not None else None
    if source_candidate is not None:
        records.append(
            _record(
                "explicit_semantics.source_candidate",
                "source_candidate",
                source_candidate,
                "context",
                source_candidate,
            )
        )

    tracks: list[ExplicitTrack] = []
    for track_index, kind in enumerate(_track_kinds(task)):
        track_title, track_title_source = _track_title(
            kind,
            task_text,
            source,
            occurrence_index=_occurrence_index(_track_kinds(task), track_index, kind),
        )
        track_id = f"diagnostic-track-{track_index}"
        track_records = [
            _record(
                f"explicit_semantics.tracks[{track_index}].local_semantic_id",
                f"tracks[{track_index}].local_semantic_id",
                track_id,
                "diagnostic_local_identity",
                "",
            )
        ]
        track_records.append(
            _record(
                f"explicit_semantics.tracks[{track_index}].kind",
                f"tracks[{track_index}].kind",
                kind,
                "task",
                task_text,
            )
        )
        if track_title is not None:
            track_records.append(
                _record(
                    f"explicit_semantics.tracks[{track_index}].title",
                    f"tracks[{track_index}].title",
                    track_title,
                    "task" if track_title_source == "task" else "context",
                    task_text,
                )
            )
        bindings = _bindings_for_track(
            kind,
            source=source,
            task_text=task_text,
            lower_text=lower_text,
            track_index=track_index,
            records=track_records,
            track_title=track_title,
        )
        x_scale = _x_scale(
            kind,
            task_text=task_text,
            lower_text=lower_text,
            track_index=track_index,
            records=track_records,
        )
        tracks.append(
            ExplicitTrack(
                local_semantic_id=track_id,
                kind=kind,
                title=track_title,
                x_scale=x_scale,
                bindings=tuple(bindings),
            )
        )
        records.extend(track_records)
    return ExplicitSemanticBlock(
        title=title, source_candidate=source_candidate, tracks=tuple(tracks)
    ), tuple(records)


def audit_explicit_semantics(
    block: ExplicitSemanticBlock,
    records: Sequence[ProvenanceRecord],
    *,
    task: SectionTask,
    section_context: ResolvedSectionContext,
) -> ExplicitSemanticAudit:
    """Verify every B field against its declared task/context provenance."""
    raw = block.model_dump(mode="json", exclude_none=True)
    context_values = {source.candidate_id for source in section_context.sources}
    context_values.update(
        channel.mnemonic for source in section_context.sources for channel in source.channels
    )
    context_values.update(
        channel.kind for source in section_context.sources for channel in source.channels
    )
    task_text = _task_text(task).lower()
    missing: list[str] = []
    for record in records:
        value = _value_at_path(raw, record.provider_path)
        if value is None:
            missing.append(record.output_path)
            continue
        if record.evidence_class == "diagnostic_local_identity":
            valid = bool(value)
        elif record.evidence_class == "context":
            valid = str(value) in context_values
        else:
            valid = _value_in_task_text(value, task_text)
        if not valid:
            missing.append(record.output_path)
    return ExplicitSemanticAudit(
        valid=not missing,
        records=tuple(records),
        missing_output_paths=tuple(missing),
    )


def _bindings_for_track(
    kind: str,
    *,
    source: object | None,
    task_text: str,
    lower_text: str,
    track_index: int,
    records: list[ProvenanceRecord],
    track_title: str | None,
) -> list[ExplicitBinding]:
    """Project channel facts and only locally recoverable binding semantics."""
    if source is None:
        return []
    bindings: list[ExplicitBinding] = []
    channels = tuple(getattr(source, "channels", ()))
    scoped_text = _track_scope_text(task_text, track_title)
    scoped_lower_text = scoped_text.lower()
    for channel in channels:
        mnemonic = str(channel.mnemonic)
        positions = [
            match.start() for match in re.finditer(re.escape(mnemonic), scoped_text, re.IGNORECASE)
        ]
        if not positions:
            continue
        binding_kind = "raster" if kind == "array" else "curve"
        repeat_count = _repeat_count(mnemonic, scoped_lower_text)
        positions = positions[:repeat_count]
        ranges = _ranges_for_channel(scoped_text, mnemonic, repeat_count)
        for binding_index, _position in enumerate(positions):
            local_id = f"diagnostic-binding-{track_index}-{binding_index}"
            prefix = f"explicit_semantics.tracks[{track_index}].bindings[{binding_index}]"
            records.append(
                _record(
                    f"{prefix}.local_semantic_id",
                    f"tracks[{track_index}].bindings[{binding_index}].local_semantic_id",
                    local_id,
                    "diagnostic_local_identity",
                    "",
                )
            )
            records.append(
                _record(
                    f"{prefix}.kind",
                    f"tracks[{track_index}].bindings[{binding_index}].kind",
                    binding_kind,
                    "task",
                    task_text,
                )
            )
            records.append(
                _record(
                    f"{prefix}.channel",
                    f"tracks[{track_index}].bindings[{binding_index}].channel",
                    mnemonic,
                    "context",
                    mnemonic,
                )
            )
            scale = _scale_for_range(
                ranges[binding_index] if binding_index < len(ranges) else None,
                task_text=task_text,
                lower_text=_binding_window(scoped_text, mnemonic, positions, binding_index),
                prefix=prefix,
                records=records,
            )
            profile = _profile_for_text(lower_text) if binding_kind == "raster" else None
            if profile is not None:
                records.append(
                    _record(
                        f"{prefix}.profile",
                        f"tracks[{track_index}].bindings[{binding_index}].profile",
                        profile,
                        "task",
                        task_text,
                    )
                )
            sample_axis = (
                _sample_axis(
                    task_text,
                    lower_text,
                    prefix=prefix,
                    records=records,
                )
                if binding_kind == "raster"
                else None
            )
            bindings.append(
                ExplicitBinding(
                    local_semantic_id=local_id,
                    kind=binding_kind,
                    channel=mnemonic,
                    scale=scale,
                    profile=profile,
                    sample_axis=sample_axis,
                )
            )
    return bindings


def _scale_for_range(
    pair: tuple[float, float] | None,
    *,
    task_text: str,
    lower_text: str,
    prefix: str,
    records: list[ProvenanceRecord],
) -> ExplicitScale | None:
    """Create a scale only when both bounds are present in task prose."""
    if pair is None:
        return None
    kind = None
    for candidate in ("log", "tangential", "linear"):
        if candidate in lower_text:
            kind = candidate
            break
    reverse = True if "reverse" in lower_text or "reversed" in lower_text else None
    scale = ExplicitScale(kind=kind, minimum=pair[0], maximum=pair[1], reverse=reverse)
    records.extend(
        [
            _record(
                f"{prefix}.scale.minimum", f"{prefix}.scale.minimum", pair[0], "task", task_text
            ),
            _record(
                f"{prefix}.scale.maximum", f"{prefix}.scale.maximum", pair[1], "task", task_text
            ),
        ]
    )
    if kind is not None:
        records.append(
            _record(f"{prefix}.scale.kind", f"{prefix}.scale.kind", kind, "task", task_text)
        )
    if reverse is not None:
        records.append(
            _record(f"{prefix}.scale.reverse", f"{prefix}.scale.reverse", True, "task", task_text)
        )
    return scale


def _x_scale(
    kind: str,
    *,
    task_text: str,
    lower_text: str,
    track_index: int,
    records: list[ProvenanceRecord],
) -> ExplicitScale | None:
    """Extract array x-scale facts without consulting expected output."""
    if kind != "array":
        return None
    match = re.search(
        rf"x\s*[- ]?scale\s*(?:of|from)?\s*({_NUMBER})\s*to\s*({_NUMBER})", lower_text
    )
    if match is None:
        return None
    pair = (float(match.group(1)), float(match.group(2)))
    prefix = f"explicit_semantics.tracks[{track_index}].x_scale"
    records.extend(
        [
            _record(
                f"{prefix}.minimum",
                f"tracks[{track_index}].x_scale.minimum",
                pair[0],
                "task",
                task_text,
            ),
            _record(
                f"{prefix}.maximum",
                f"tracks[{track_index}].x_scale.maximum",
                pair[1],
                "task",
                task_text,
            ),
        ]
    )
    return ExplicitScale(minimum=pair[0], maximum=pair[1])


def _sample_axis(
    task_text: str,
    lower_text: str,
    *,
    prefix: str,
    records: list[ProvenanceRecord],
) -> ExplicitSampleAxis | None:
    """Extract only axis facts that survived into task text."""
    unit_match = re.search(r"sample\s+unit\s+([a-zA-Z]+)", lower_text)
    origin_match = re.search(rf"source\s+origin\s+({_NUMBER})", lower_text)
    step_match = re.search(rf"source\s+step\s+({_NUMBER})", lower_text)
    ticks_match = re.search(r"([0-9]+)\s+ticks", lower_text)
    axis_values = [unit_match, origin_match, step_match, ticks_match]
    if not any(axis_values):
        return None
    unit = unit_match.group(1) if unit_match else None
    origin = float(origin_match.group(1)) if origin_match else None
    step = float(step_match.group(1)) if step_match else None
    tick_count = int(ticks_match.group(1)) if ticks_match else None
    if unit is not None:
        records.append(
            _record(
                f"{prefix}.sample_axis.unit", f"{prefix}.sample_axis.unit", unit, "task", task_text
            )
        )
    if origin is not None:
        records.append(
            _record(
                f"{prefix}.sample_axis.source_origin",
                f"{prefix}.sample_axis.source_origin",
                origin,
                "task",
                task_text,
            )
        )
    if step is not None:
        records.append(
            _record(
                f"{prefix}.sample_axis.source_step",
                f"{prefix}.sample_axis.source_step",
                step,
                "task",
                task_text,
            )
        )
    if tick_count is not None:
        records.append(
            _record(
                f"{prefix}.sample_axis.tick_count",
                f"{prefix}.sample_axis.tick_count",
                tick_count,
                "task",
                task_text,
            )
        )
    return ExplicitSampleAxis(
        unit=unit, source_origin=origin, source_step=step, tick_count=tick_count
    )


def _profile_for_text(lower_text: str) -> str | None:
    """Select a raster profile only from explicit task wording."""
    if "vdl" in lower_text:
        return "vdl"
    if "waveform" in lower_text:
        return "waveform"
    if "generic raster" in lower_text or "image" in lower_text:
        return "generic"
    return None


def _ranges_for_channel(text: str, channel: str, count: int) -> list[tuple[float, float]]:
    """Find nearby ordered numeric ranges for one channel occurrence."""
    matches = list(re.finditer(re.escape(channel), text, re.IGNORECASE))
    if not matches:
        return []
    window = text[matches[0].start() : matches[0].start() + 180]
    return [(float(match.group(1)), float(match.group(2))) for match in _RANGE_RE.finditer(window)][
        :count
    ]


def _binding_window(text: str, channel: str, positions: Sequence[int], index: int) -> str:
    """Limit scale-kind inference to the prose for one binding occurrence."""
    position = positions[index]
    later_positions = [value for value in positions if value > position]
    end = later_positions[0] if later_positions else min(len(text), position + 180)
    return text[position:end].lower()


def _track_scope_text(text: str, title: str | None) -> str:
    """Keep channel extraction within an explicitly named track's prose."""
    if title is None:
        return text
    lowered = title.lower()
    markers = {
        "combo": (r"on\s+combo", r"(?:on\s+depth|track\s+titled\s+(?:cbl|vdl)|vdl)"),
        "depth": (r"(?:on\s+depth|depth\s+track)", r"(?:cbl|vdl)"),
        "cbl": (r"cbl", r"vdl"),
        "vdl": (r"vdl", r"$^"),
    }
    marker = next((value for key, value in markers.items() if key in lowered), None)
    if marker is None:
        return text
    start_match = re.search(marker[0], text, re.IGNORECASE)
    if start_match is None:
        return text
    end_match = re.search(marker[1], text[start_match.end() :], re.IGNORECASE)
    end = start_match.end() + end_match.start() if end_match else len(text)
    return text[start_match.start() : end]


def _repeat_count(channel: str, lower_text: str) -> int:
    """Preserve repeated binding evidence from task prose."""
    if channel.upper() == "CBL" and ("twice" in lower_text or "two distinct" in lower_text):
        return 2
    return 1


def _track_kinds(task: SectionTask) -> tuple[Literal["normal", "reference", "array"], ...]:
    """Preserve selected track capability order."""
    result: list[Literal["normal", "reference", "array"]] = []
    for capability_id in task.capability_ids:
        prefix = "track."
        if not capability_id.startswith(prefix):
            continue
        kind = capability_id.removeprefix(prefix)
        if kind in {"normal", "reference", "array"}:
            result.append(kind)  # type: ignore[arg-type]
    return tuple(result)


def _source_from_task(task: SectionTask, sources: Sequence[object]) -> object | None:
    """Choose a context source only when one task hint matches it exactly."""
    hints = {str(value).lower() for value in task.source_hints}
    matches = [
        source
        for source in sources
        if str(getattr(source, "candidate_id", "")).lower() in hints
        or hints.intersection(str(label).lower() for label in getattr(source, "labels", ()))
    ]
    return matches[0] if len(matches) == 1 else None


def _section_title(
    task: SectionTask,
    source: object | None,
    task_text: str,
) -> tuple[str | None, str]:
    """Recover a title from task prose or an explicit source label."""
    match = re.search(r"titled\s+([^.,]+)", task_text, re.IGNORECASE)
    if match:
        return match.group(1).strip(), "task"
    for label in getattr(source, "labels", ()) if source is not None else ():
        if "pass" in str(label).lower():
            return str(label), "context"
    return None, "task"


def _track_title(
    kind: str,
    task_text: str,
    source: object | None,
    *,
    occurrence_index: int,
) -> tuple[str | None, str]:
    """Recover only literal track labels from task/context text."""
    patterns = {
        "normal": r"(?:on\s+|track\s+titled\s+)(Combo|CBL(?:\s+(?:Amplitude|Views?))?)",
        "reference": r"(?:track|on)\s+(Depth)",
        "array": r"(?:track\s+titled\s+|the\s+)(VDL|Image|Waveform)",
    }
    matches = list(re.finditer(patterns[kind], task_text, re.IGNORECASE))
    if occurrence_index < len(matches):
        return matches[occurrence_index].group(1).strip(), "task"
    generic = re.search(r"track\s+titled\s+([^.,]+)", task_text, re.IGNORECASE)
    if generic is not None and occurrence_index == 0:
        return generic.group(1).strip(), "task"
    for label in getattr(source, "labels", ()) if source is not None else ():
        if kind in str(label).lower():
            return str(label), "context"
    return None, "task"


def _occurrence_index(
    kinds: Sequence[Literal["normal", "reference", "array"]],
    index: int,
    kind: Literal["normal", "reference", "array"],
) -> int:
    """Return the zero-based occurrence of one track kind in capability order."""
    return sum(value == kind for value in kinds[:index])


def _task_text(task: SectionTask) -> str:
    """Serialize only the planner-owned task prose for diagnostic extraction."""
    values = [
        task.goal,
        *task.capability_ids,
        *task.source_hints,
        *task.requirements,
        *task.constraints,
    ]
    return " ".join(str(value) for value in values)


def _record(
    output_path: str,
    provider_path: str,
    value: object,
    evidence_class: Literal["task", "context", "diagnostic_local_identity"],
    evidence_text: str,
) -> ProvenanceRecord:
    """Create a provenance record without retaining source text."""
    evidence_path = _provenance_path(provider_path, evidence_class)
    evidence_value = str(value) if evidence_class == "diagnostic_local_identity" else evidence_text
    return ProvenanceRecord(
        output_path=output_path,
        provider_path=provider_path.removeprefix("explicit_semantics."),
        evidence_path=evidence_path,
        evidence_class=evidence_class,
        evidence_sha256=_sha256(evidence_value),
    )


def _provenance_path(
    provider_path: str,
    evidence_class: Literal["task", "context", "diagnostic_local_identity"],
) -> str:
    """Return a safe locator instead of retaining matched task/context text."""
    if evidence_class == "diagnostic_local_identity":
        return "diagnostic_local_identity"
    if evidence_class == "context":
        if provider_path == "source_candidate":
            return "context.source.candidate_id"
        if provider_path.endswith(".channel"):
            return "context.source.channel.mnemonic"
        return "context.source"
    if ".kind" in provider_path:
        return "task.capability_ids"
    if "source" in provider_path:
        return "task.source_hints"
    return "task.goal_requirements_constraints"


def _value_at_path(value: object, path: str) -> object | None:
    """Read a simple dotted/list-index path from a model dump."""
    current = value
    for part in path.split("."):
        match = re.match(r"([^\[]+)(?:\[(\d+)\])?$", part)
        if match is None or not isinstance(current, Mapping):
            return None
        current = current.get(match.group(1))
        if match.group(2) is not None:
            if not isinstance(current, list):
                return None
            index = int(match.group(2))
            if index >= len(current):
                return None
            current = current[index]
    return current


def _value_in_task_text(value: object, lower_text: str) -> bool:
    """Check a task-provenance value without interpreting expected output."""
    if isinstance(value, bool):
        return ("reverse" in lower_text) if value else True
    if isinstance(value, float) and value.is_integer():
        candidates = (str(int(value)), str(value))
    else:
        candidates = (str(value),)
    return any(candidate.lower() in lower_text for candidate in candidates)


def _sha256(value: str) -> str:
    """Hash deterministic UTF-8 text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: object) -> str:
    """Hash deterministic JSON-shaped evidence."""
    return _sha256(json.dumps(value, sort_keys=True, separators=(",", ":")))


async def generate_variant(
    backend: ModelBackendProtocol,
    *,
    serialized_input: str,
    section_context: ResolvedSectionContext,
    document: object,
    expected: Mapping[str, object],
    timeout_seconds: float,
) -> dict[str, object]:
    """Run the common typed generation/validation/compiler path once."""
    try:
        generated = await backend.generate_structured(
            StructuredGenerationRequest(
                system_prompt=TYPED_SECTION_SYSTEM_PROMPT,
                user_prompt=serialized_input,
                timeout_seconds=timeout_seconds,
                temperature=WORKER_TEMPERATURE,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            ),
            response_model=SectionSemanticDraft,
        )
    except ProviderRequestError as error:
        category = _provider_category(error)
        return _variant_failure(
            "structured_output_failure",
            error,
            provider_category=category,
            serialized_input=serialized_input,
        )
    try:
        draft = SectionSemanticDraft.model_validate(generated.value)
    except ValidationError as error:
        return _variant_failure(
            "structured_output_failure",
            error,
            provider_category="validation",
            serialized_input=serialized_input,
            provider_call_completed=True,
        )
    structured = {"provider_call_completed": True, "structured_valid": True}
    try:
        validate_section_semantics(draft, section_context=section_context)
    except SectionSemanticValidationError as error:
        return {
            **structured,
            "context_valid": False,
            "compiler_valid": False,
            "semantic_accepted": False,
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", None).value,
            "provider_input_sha256": _sha256(serialized_input),
            "provider_input_chars": len(serialized_input),
            "provider_metrics": generated.metrics.public_metadata(),
        }
    try:
        compile_section_semantics(
            draft,
            section_context=section_context,
            document=document,
            section_id_hint="cm56r5-diagnostic",
        )
    except SectionSemanticCompilationError as error:
        return {
            **structured,
            "context_valid": True,
            "compiler_valid": False,
            "semantic_accepted": False,
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", None),
            "provider_input_sha256": _sha256(serialized_input),
            "provider_input_chars": len(serialized_input),
            "provider_metrics": generated.metrics.public_metadata(),
        }
    evaluation = evaluate_semantic_draft(draft, expected=expected)
    return {
        **structured,
        "context_valid": True,
        "compiler_valid": True,
        "semantic_accepted": evaluation.accepted,
        "omissions": evaluation.omissions,
        "unrequested_semantics": evaluation.unrequested_semantics,
        "provider_input_sha256": _sha256(serialized_input),
        "provider_input_chars": len(serialized_input),
        "provider_metrics": generated.metrics.public_metadata(),
    }


def _variant_failure(
    classification: str,
    error: BaseException,
    *,
    provider_category: str | None,
    serialized_input: str,
    provider_call_completed: bool = False,
) -> dict[str, object]:
    """Serialize safe provider-boundary failure evidence."""
    return {
        "structured_valid": False,
        "provider_call_completed": provider_call_completed,
        "context_valid": False,
        "compiler_valid": False,
        "semantic_accepted": False,
        "classification": classification,
        "error_type": type(error).__name__,
        "error_code": getattr(error, "code", None),
        "provider_category": provider_category,
        "provider_input_sha256": _sha256(serialized_input),
        "provider_input_chars": len(serialized_input),
    }


def _select_case_section(
    case_id: str,
    plan: object,
    enriched: object,
) -> tuple[SectionTask, ResolvedSectionContext] | None:
    """Select one comparable section without reading expected output."""
    tasks = tuple(getattr(plan, "section_tasks", ()))
    contexts = tuple(getattr(enriched, "sections", ()))
    pairs = list(zip(tasks, contexts, strict=False))
    if case_id != "cbl_continuity":
        return pairs[0] if pairs else None
    for task, context in pairs:
        text = _task_text(task).lower()
        labels = " ".join(
            str(label).lower()
            for source in context.sources
            for label in getattr(source, "labels", ())
        )
        if "main" in text or "main" in labels:
            return task, context
    return None


async def run_representation_attempt(
    case: Mapping[str, object],
    *,
    backend: ModelBackendProtocol,
    planner: SemanticPlanner,
    registry: CapabilityRegistry,
    timeout_seconds: float,
    attempt_index: int,
) -> dict[str, object]:
    """Run one planner/enricher result through paired A/B provider calls."""
    document = _document()
    request = _case_request(case)
    started = time.perf_counter()
    base = {
        "experiment_version": EXPERIMENT_VERSION,
        "arm": "representation",
        "case_id": case["case_id"],
        "attempt_index": attempt_index,
        "planner_temperature": PLANNER_TEMPERATURE,
        "worker_temperature": WORKER_TEMPERATURE,
        "natural_request_sha256": _sha256(request),
        "case_corpus_sha256": case_corpus_sha256(),
        "system_prompt_sha256": _sha256(TYPED_SECTION_SYSTEM_PROMPT),
        "response_schema_sha256": response_schema_sha256(),
    }
    try:
        plan = await planner.plan(
            request=request,
            mode="reconstruct",
            current_document_summary=AuthoringInspectionFacade(document)
            .document_summary()
            .model_dump(mode="json"),
            source_summary=production_source_summary(case),
            timeout_seconds=timeout_seconds,
            temperature=PLANNER_TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        enriched = build_fixture_enricher(case).enrich(
            plan=plan,
            document=document,
            source_candidates=build_source_candidates(case),
            mode="reconstruct",
        )
    except ProviderRequestError as error:
        return {
            **base,
            "classification": "PLANNER_FAILURE",
            "error_type": type(error).__name__,
            "provider_category": _provider_category(error),
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        }
    except SemanticEnrichmentError as error:
        return {
            **base,
            "classification": "ENRICHMENT_FAILURE",
            "error_type": type(error).__name__,
            "error_code": getattr(error, "code", None).value,
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        }

    selected = _select_case_section(str(case["case_id"]), plan, enriched)
    if selected is None:
        return {
            **base,
            "classification": "PLANNER_SECTION_SELECTION_FAILURE",
            "elapsed_ms": (time.perf_counter() - started) * 1000,
        }
    task, section_context = selected
    pair = build_pair_input(task, section_context=section_context, registry=registry)
    expected_sections = list(case.get("expected_sections", ()))
    expected = expected_sections[0] if expected_sections else {}
    audit = audit_input_sufficiency(
        case,
        task=task,
        section_context=section_context,
        serialized_input=pair.variant_a,
    )
    a_result = await generate_variant(
        backend,
        serialized_input=pair.variant_a,
        section_context=section_context,
        document=document,
        expected=expected,
        timeout_seconds=timeout_seconds,
    )
    b_result = await generate_variant(
        backend,
        serialized_input=pair.variant_b,
        section_context=section_context,
        document=document,
        expected=expected,
        timeout_seconds=timeout_seconds,
    )
    return {
        **base,
        "classification": "PAIRED_TYPED_ATTEMPT",
        "task_context_sha256": _sha256(pair.variant_a),
        "production_input_sha256": _sha256(pair.variant_a),
        "production_input_chars": len(pair.variant_a),
        "explicit_input_sha256": _sha256(pair.variant_b),
        "explicit_input_chars": len(pair.variant_b),
        "explicit_diff_only": _only_explicit_block_diff(pair.variant_a, pair.variant_b),
        "explicit_semantic_audit": pair.audit.model_dump(mode="json"),
        "input_sufficiency": {
            "sufficient": audit.sufficient,
            "facts": audit.facts,
            "missing_fact_ids": audit.missing_fact_ids,
        },
        "vdl_axis_facts_in_task": _axis_facts_present(task),
        "a": a_result,
        "b": b_result,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
    }


def _only_explicit_block_diff(variant_a: str, variant_b: str) -> bool:
    """Verify B is exactly A plus one diagnostic field."""
    left = json.loads(variant_a)
    right = json.loads(variant_b)
    explicit = right.pop("explicit_semantics", None)
    return explicit is not None and left == right


def _axis_facts_present(task: SectionTask) -> dict[str, bool]:
    """Report whether planner task prose retained VDL axis facts."""
    text = _task_text(task).lower()
    return {
        "unit": bool(re.search(r"sample\s+unit\s+[a-z]+", text)),
        "source_origin": "source origin" in text,
        "source_step": "source step" in text,
        "tick_count": bool(re.search(r"\d+\s+ticks", text)),
    }


async def run_representation_matrix(args: argparse.Namespace) -> None:
    """Run the six-case A/B matrix and flush paired rows."""
    from scripts.cm56_typed_section_shadow import _provider_configuration

    backend = _provider_configuration(args)
    registry = create_builtin_registry()
    cases = [case for case in load_case_definitions() if case["case_id"] in REPRESENTATION_CASES]
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("a", encoding="utf-8") as handle:
        for case in cases:
            planner = SemanticPlanner(backend=backend, registry=registry)
            for attempt_index in range(3):
                row = await run_representation_attempt(
                    case,
                    backend=backend,
                    planner=planner,
                    registry=registry,
                    timeout_seconds=args.timeout,
                    attempt_index=attempt_index,
                )
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                handle.flush()


async def run_repeated_channel_matrix(args: argparse.Namespace) -> None:
    """Run the separate ten-attempt planner-only repeated-channel arm."""
    from scripts.cm56_typed_section_shadow import _provider_configuration

    case = next(
        case for case in load_case_definitions() if case["case_id"] == REPEATED_CHANNEL_CASE
    )
    backend = _provider_configuration(args)
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())
    request = _case_request(case)
    source_summary = production_source_summary(case)
    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("a", encoding="utf-8") as handle:
        for attempt_index in range(REPEATED_CHANNEL_ATTEMPTS):
            started = time.perf_counter()
            base = {
                "experiment_version": EXPERIMENT_VERSION,
                "arm": "repeated-channel",
                "case_id": REPEATED_CHANNEL_CASE,
                "attempt_index": attempt_index,
                "planner_temperature": PLANNER_TEMPERATURE,
                "natural_request_sha256": _sha256(request),
                "source_summary_sha256": _sha256_json(source_summary),
            }
            try:
                plan = await planner.plan(
                    request=request,
                    mode="reconstruct",
                    current_document_summary=AuthoringInspectionFacade(_document())
                    .document_summary()
                    .model_dump(mode="json"),
                    source_summary=source_summary,
                    timeout_seconds=args.timeout,
                    temperature=PLANNER_TEMPERATURE,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                )
            except ProviderRequestError as error:
                row = {
                    **base,
                    "classification": "PLANNER_FAILURE",
                    "error_type": type(error).__name__,
                    "provider_category": _provider_category(error),
                    "elapsed_ms": (time.perf_counter() - started) * 1000,
                }
            else:
                row = {
                    **base,
                    "classification": "PLANNED",
                    "plan": safe_plan_projection(plan),
                    "section_tasks": [
                        {
                            "task_index": index,
                            "goal": task.goal,
                            "capability_ids": task.capability_ids,
                            "source_hints": task.source_hints,
                            "requirements": task.requirements,
                            "constraints": task.constraints,
                            "existing_section_hint_present": task.existing_section_hint is not None,
                        }
                        for index, task in enumerate(plan.section_tasks)
                    ],
                    "elapsed_ms": (time.perf_counter() - started) * 1000,
                }
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()


def _parser() -> argparse.ArgumentParser:
    """Build the CM-56R5 diagnostic CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("representation", "repeated-channel"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="OPENAI_COMPAT_API_KEY")
    parser.add_argument("--max-output-tokens", type=int, default=MAX_OUTPUT_TOKENS)
    parser.add_argument(
        "--max-tokens-parameter",
        choices=("max_tokens", "max_completion_tokens"),
        default="max_tokens",
    )
    parser.add_argument("--timeout", type=float, default=TIMEOUT_SECONDS)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    return parser


def main() -> None:
    """Run one CM-56R5 diagnostic arm."""
    args = _parser().parse_args()
    if args.arm == "repeated-channel":
        asyncio.run(run_repeated_channel_matrix(args))
        return
    asyncio.run(run_representation_matrix(args))


__all__ = [
    "ExplicitSemanticAudit",
    "ExplicitSemanticBlock",
    "PairInput",
    "REPRESENTATION_CASES",
    "RESPONSE_SCHEMA_SHA256",
    "build_explicit_semantics",
    "build_pair_input",
    "audit_explicit_semantics",
    "run_representation_attempt",
    "run_repeated_channel_matrix",
]


if __name__ == "__main__":  # pragma: no cover
    main()
