"""Shared worker result contract for the canonical semantic graph."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ...model.intent import AuthoringDocumentIntent
from ..semantic_runtime import SemanticDiagnostic, SemanticMetrics, SemanticStageEvidence
from .enrichment import ReportContext, ResolvedSectionContext
from .obligations import ObligationState, OwnerKind, RequestObligation
from .planner import (
    MAX_SEMANTIC_OPERATIONS,
    OperationCondition,
    ReportTask,
    SectionTask,
    SemanticOperation,
)


class SectionWorkContractError(ValueError):
    """Deterministic failure while projecting authoritative section work."""

    def __init__(
        self, code: str, message: str, *, details: dict[str, object] | None = None
    ) -> None:
        """Initialize the stable diagnostic code and safe message."""
        self.code = code
        self.details = details
        super().__init__(message)


def _handle_mismatch_details(
    classification: str,
    expected: list[str],
    actual: list[str],
    *,
    owners: dict[str, str] | None = None,
) -> dict[str, object]:
    """Bound untrusted handle evidence to counts and stable digests."""

    def digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()

    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    limit = 32
    result: dict[str, object] = {
        "stage": "section_work_contract",
        "classification": classification,
        "expected_count": len(expected),
        "actual_count": len(actual),
        "missing_count": len(missing),
        "unexpected_count": len(unexpected),
        "missing_handle_sha256": [digest(item) for item in missing[:limit]],
        "unexpected_handle_sha256": [digest(item) for item in unexpected[:limit]],
        "handles_truncated": len(missing) > limit or len(unexpected) > limit,
    }
    if owners is None:
        result["binding_validation"] = "NOT_EVALUATED"
    else:
        result["expected_ownership_sha256"] = [
            {"binding": digest(handle), "track": digest(owners[handle])}
            for handle in sorted(owners)[:limit]
        ]
        result["ownership_truncated"] = len(owners) > limit
    return result


class SectionWorkTarget(BaseModel):
    """Provider-safe target for one section-local task."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["existing_section", "new_section"]
    title: str | None = None
    handle: str | None = None


class SectionWorkScale(BaseModel):
    """Explicit scale values that are authoritative for one action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool | None = None


class SectionWorkTrack(BaseModel):
    """One required request-local track identity and its explicit semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    handle: str = Field(min_length=1)
    title: str | None = None
    kind: str | None = None
    width_mm: float | None = None
    scale: SectionWorkScale | None = None
    vertical_main_visible: bool | None = None
    vertical_secondary_visible: bool | None = None


class SectionWorkBinding(BaseModel):
    """One required request-local binding identity and explicit semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    handle: str = Field(min_length=1)
    track_handle: str = Field(min_length=1)
    kind: Literal["curve", "raster"] = "curve"
    channel: str | None = None
    label: str | None = None
    scale: SectionWorkScale | None = None
    color: str | None = None
    line_width: float | None = None
    line_style: str | None = None
    alpha: float | None = None
    raster_profile: str | None = None
    raster_colormap: str | None = None
    colorbar_enabled: bool | None = None
    colorbar_label: str | None = None
    colorbar_position: str | None = None
    sample_axis_enabled: bool | None = None
    sample_axis_unit: str | None = None
    sample_axis_minimum: float | None = None
    sample_axis_maximum: float | None = None
    sample_axis_tick_count: int | None = None
    sample_axis_source_origin: float | None = None
    sample_axis_source_step: float | None = None


class SectionWorkChannel(BaseModel):
    """Safe source channel facts available to the section serializer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mnemonic: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    unit: str | None = None


class SectionWorkSource(BaseModel):
    """Opaque request-local source handle and its bounded channel inventory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    handle: str = Field(min_length=1)
    name: str = Field(min_length=1)
    format: str | None = None
    inspection_state: Literal["inspected", "not_inspected", "unavailable"] = "inspected"
    channels: tuple[SectionWorkChannel, ...] = ()


class SectionWorkContract(BaseModel):
    """Deterministic, provider-neutral instructions for one section task."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["wellplot.section-work.v1"] = "wellplot.section-work.v1"
    snapshot_id: str | None = None
    target: SectionWorkTarget
    required_action: Literal[
        "reconstruct", "add_track", "add_tracks", "update_curve_scale", "add_fill"
    ]
    required_tracks: tuple[SectionWorkTrack, ...] = ()
    required_bindings: tuple[SectionWorkBinding, ...] = ()
    source_handle: str | None = None
    target_handle: str | None = None
    required_scale: SectionWorkScale | None = None
    required_fill: dict[str, str | float | bool | None] | None = None
    source_facts: tuple[SectionWorkSource, ...] = ()
    preservation_rules: tuple[str, ...] = ()


class WorkerOperationContractEntry(BaseModel):
    """One planner operation grounded into its section-local host contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str = Field(min_length=1)
    operation_ref: str = Field(min_length=1)
    operation_type: Literal["ADD_TRACK"]
    scope_ref: str = Field(min_length=1)
    target_handle: str | None = None
    parent_operation_id: str | None = None
    condition_predicate: str | None = None
    condition_result: Literal[
        "UNCONDITIONAL",
        "CONDITION_TRUE",
        "CONDITION_FALSE",
        "SOURCE_NOT_INSPECTED",
        "SOURCE_UNAVAILABLE",
    ] = "UNCONDITIONAL"
    condition_evidence: str | None = None
    condition_channel_clue: str | None = None
    requirement_ids: tuple[str, ...] = ()


class SectionOperationContract(BaseModel):
    """Exact host-owned operation inventory for one immutable section snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["wellplot.section-operation-contract.v1"] = (
        "wellplot.section-operation-contract.v1"
    )
    request_sha256: str
    scope_ref: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    operations: tuple[WorkerOperationContractEntry, ...]
    omitted_operations: tuple[WorkerOperationContractEntry, ...] = ()
    operation_schema_sha256: str
    ordering_constraints: tuple[tuple[str, str, str], ...] = ()


class ReportOperationContractEntry(BaseModel):
    """One report operation mapped to an existing report-owned output target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_ref: str = Field(min_length=1)
    field: str = Field(min_length=1)
    target: str = Field(min_length=1)
    value: str | float | int | bool | None = None
    requirement_id: str | None = None
    order_index: int | None = Field(default=None, ge=1)


class ReportOperationContract(BaseModel):
    """Host-owned binding from report planner refs to obligation-backed slots."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal["wellplot.report-operation-contract.v1"] = (
        "wellplot.report-operation-contract.v1"
    )
    request_sha256: str
    scope_ref: Literal["report"] = "report"
    snapshot_id: str = Field(min_length=1)
    entries: tuple[ReportOperationContractEntry, ...]
    ordering_constraints: tuple[tuple[str, str, str], ...] = ()


# The planner and worker schema share this finite batch bound. It caps a
# provider response to a size already representable by one bounded section
# task; it is not a claim of compatibility for arbitrary providers.
MAX_SECTION_SEMANTIC_OPERATIONS = MAX_SEMANTIC_OPERATIONS


_BINDING_FIELDS = {
    "channel",
    "label",
    "scale_kind",
    "scale_minimum",
    "scale_maximum",
    "scale_reverse",
    "color",
    "line_width",
    "line_style",
    "alpha",
    "raster_profile",
    "raster_colormap",
    "colorbar_enabled",
    "colorbar_label",
    "colorbar_position",
    "sample_axis_enabled",
    "sample_axis_unit",
    "sample_axis_minimum",
    "sample_axis_maximum",
    "sample_axis_tick_count",
    "sample_axis_source_origin",
    "sample_axis_source_step",
}


def _work_handle(value: str) -> str:
    """Create the canonical exact-normalized request-local semantic handle."""
    return "_".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _unique_value(items: list[RequestObligation], field: str) -> object | None:
    values = [item.value for item in items if item.field == field]
    if not values:
        return None
    normalized = {str(value).casefold() if isinstance(value, str) else value for value in values}
    if len(normalized) != 1:
        raise SectionWorkContractError(
            "section_work_contract_conflict", "Conflicting section work values were compiled."
        )
    return values[0]


def _scale_from_items(
    items: list[RequestObligation], *, prefix: str = "scale_"
) -> SectionWorkScale | None:
    fields = {
        "kind": prefix + "kind",
        "minimum": prefix + "minimum",
        "maximum": prefix + "maximum",
        "reverse": prefix + "reverse",
    }
    values = {key: _unique_value(items, source) for key, source in fields.items()}
    if not any(value is not None for value in values.values()):
        return None
    return SectionWorkScale(**values)


def _track_handle_from_slot(slot_key: str | None, fallback_owner: str) -> str:
    """Project an obligation slot to its request-local track handle."""
    if slot_key and ".binding." in slot_key:
        return _work_handle(slot_key.split(".binding.", 1)[0])
    return _work_handle(fallback_owner)


def _source_handle(
    requested_source: object | None,
    section_context: ResolvedSectionContext,
) -> str | None:
    """Resolve a requested source to one opaque handle without exposing its ID."""
    if not section_context.sources:
        raise SectionWorkContractError(
            "section_work_source_missing", "No inspected source is available for this task."
        )
    if requested_source is None:
        return "source-1" if len(section_context.sources) == 1 else None
    requested_name = re.split(r"[/\\]", str(requested_source))[-1]
    wanted = _work_handle(requested_name)
    matches = [
        index
        for index, source in enumerate(section_context.sources)
        if wanted
        in {
            _work_handle(_source_name(source)),
            *(_work_handle(label) for label in source.labels),
        }
    ]
    if len(matches) != 1:
        code = "section_work_source_missing" if not matches else "section_work_source_ambiguous"
        raise SectionWorkContractError(code, "The requested source is not uniquely inspected.")
    source = section_context.sources[matches[0]]
    if source.inspection_state != "inspected":
        raise SectionWorkContractError(
            "section_work_source_unavailable",
            "The requested source does not have an inspected channel inventory.",
        )
    return source.handle


def _source_index(source_handle: str, section_context: ResolvedSectionContext) -> int:
    """Decode one already-resolved opaque source handle."""
    matches = [
        index
        for index, source in enumerate(section_context.sources)
        if source.handle == source_handle
    ]
    if len(matches) != 1:
        raise SectionWorkContractError(
            "section_work_source_missing", "The requested source handle is invalid."
        )
    return matches[0]


def _channel_kind(
    channel: object,
    section_context: ResolvedSectionContext,
    *,
    selected_source_index: int | None,
) -> str | None:
    """Resolve channel kind only from the selected or inventory-consistent sources."""
    if channel is None:
        return None
    mnemonic = str(channel).casefold()
    if selected_source_index is not None:
        if selected_source_index >= len(section_context.sources):
            raise SectionWorkContractError(
                "section_work_source_missing", "The selected source is not inspected."
            )
        matches = [
            item.kind
            for item in section_context.sources[selected_source_index].channels
            if item.mnemonic.casefold() == mnemonic
        ]
        return matches[0] if len(matches) == 1 else None

    if not section_context.sources:
        return None
    source_kinds: list[str] = []
    for source in section_context.sources:
        matches = [item.kind for item in source.channels if item.mnemonic.casefold() == mnemonic]
        if len(matches) != 1:
            raise SectionWorkContractError(
                "section_work_source_ambiguous",
                "Candidate source inventories disagree for a required channel.",
            )
        source_kinds.append(matches[0])
    if len(set(source_kinds)) != 1:
        raise SectionWorkContractError(
            "section_work_source_ambiguous",
            "Candidate source inventories disagree for a required channel.",
        )
    return source_kinds[0]


def _source_name(source: object) -> str:
    """Project a basename only; never expose a canonical source path."""
    labels = tuple(getattr(source, "labels", ()))
    canonical_path = getattr(source, "canonical_path", None)
    fallback = (
        Path(canonical_path).name if canonical_path else getattr(source, "candidate_id", "source")
    )
    raw = labels[0] if labels else str(fallback)
    name = re.split(r"[/\\]", raw)[-1].strip()
    return name or "source"


def _existing_curve_handle(
    owner: str,
    context: ResolvedSectionContext,
) -> str:
    """Resolve one existing curve by exact normalized title/label/channel identity."""
    identity = _work_handle(owner)
    matches = [
        index
        for index, curve in enumerate(context.existing_curves)
        if identity
        in {
            _work_handle(curve.track_title),
            _work_handle(curve.label or ""),
            _work_handle(curve.channel),
        }
    ]
    if len(matches) != 1:
        code = "section_work_target_missing" if not matches else "section_work_target_ambiguous"
        raise SectionWorkContractError(code, "Existing curve target is not uniquely grounded.")
    return f"curve-{matches[0] + 1}"


def build_section_work_contract(
    task: SectionTask,
    section_context: ResolvedSectionContext,
) -> SectionWorkContract:
    """Project task obligations and host context into one deterministic contract."""
    obligations = tuple(task.obligations)
    invalid = [item for item in obligations if item.state is not ObligationState.SET]
    if invalid:
        raise SectionWorkContractError(
            "section_work_contract_unresolved",
            "Section work contract requires resolved explicit obligations.",
        )

    track_owner_names = tuple(
        dict.fromkeys(
            item.owner_ref
            for item in obligations
            if item.owner_kind in {OwnerKind.TRACK, OwnerKind.ARRAY_TRACK}
        )
    )
    handles: dict[str, str] = {}
    for owner in track_owner_names:
        handle = _work_handle(owner)
        previous = handles.get(handle)
        if not handle or previous is not None and previous != owner:
            raise SectionWorkContractError(
                "section_work_handle_collision",
                "Distinct request objects share one normalized semantic handle.",
            )
        handles[handle] = owner
    owner_order = sorted(
        track_owner_names,
        key=lambda owner: min(
            (item.start_byte for item in obligations if item.owner_ref == owner),
            default=0,
        ),
    )
    source_obligation = next(
        (item for item in obligations if item.owner_kind is OwnerKind.SOURCE),
        None,
    )
    selected_source_handle = (
        _source_handle(source_obligation.value, section_context)
        if source_obligation is not None
        else "source-1"
        if len(section_context.sources) == 1
        else None
    )
    selected_source_index = (
        _source_index(selected_source_handle, section_context)
        if selected_source_handle is not None
        else (0 if len(section_context.sources) == 1 else None)
    )
    work_tracks: list[SectionWorkTrack] = []
    work_bindings: list[SectionWorkBinding] = []
    for owner in owner_order:
        handle = _work_handle(owner)
        owned_tracks = [item for item in obligations if item.owner_ref == owner]
        track_kind = _unique_value(owned_tracks, "kind")
        if track_kind is None:
            track_kind = (
                "array"
                if any(item.owner_kind is OwnerKind.ARRAY_TRACK for item in owned_tracks)
                else None
            )
        if track_kind not in {"normal", "reference", "array"}:
            raise SectionWorkContractError(
                "section_work_track_kind_missing",
                "A required track kind is not determined by compiled obligations.",
            )
        explicit_title = _unique_value(owned_tracks, "title")
        track = SectionWorkTrack(
            handle=handle,
            title=str(explicit_title) if explicit_title is not None else None,
            kind=track_kind,
            width_mm=_unique_value(owned_tracks, "width_mm"),
            scale=_scale_from_items(owned_tracks, prefix="track_scale_"),
            vertical_main_visible=_unique_value(owned_tracks, "vertical_main_visible"),
            vertical_secondary_visible=_unique_value(owned_tracks, "vertical_secondary_visible"),
        )
        work_tracks.append(track)

        binding_facts = [
            item
            for item in obligations
            if item.owner_kind is OwnerKind.BINDING
            and _track_handle_from_slot(item.slot_key, item.owner_ref) == handle
        ]
        slot_facts_by_key: dict[str, list[RequestObligation]] = {}
        for fact in binding_facts:
            if fact.slot_key is not None:
                slot_facts_by_key.setdefault(fact.slot_key, []).append(fact)
        unscoped = [fact for fact in binding_facts if fact.slot_key is None]
        if unscoped:
            channel_facts = [fact for fact in unscoped if fact.field == "channel"]
            if len(channel_facts) > 1:
                raise SectionWorkContractError(
                    "section_work_binding_ambiguous",
                    "Repeated channels require explicit ordered binding slots.",
                )
            if not slot_facts_by_key:
                owner_groups = {_work_handle(fact.owner_ref) for fact in unscoped}
                if len(owner_groups) > 1:
                    raise SectionWorkContractError(
                        "section_work_binding_ambiguous",
                        "Unslotted binding obligations do not identify one local binding.",
                    )
                slot_facts_by_key[f"{handle}.binding.1"] = unscoped
            elif channel_facts and len(unscoped) == 1:
                for slot_facts in slot_facts_by_key.values():
                    slot_facts.extend(channel_facts)
            elif len(slot_facts_by_key) == 1:
                next(iter(slot_facts_by_key.values())).extend(unscoped)
            else:
                raise SectionWorkContractError(
                    "section_work_binding_ambiguous",
                    "Unslotted obligations cannot be assigned across multiple bindings.",
                )
        slots = tuple(
            sorted(
                slot_facts_by_key,
                key=lambda slot: (
                    int(slot.rsplit(".binding.", 1)[-1])
                    if slot.rsplit(".binding.", 1)[-1].isdigit()
                    else 0,
                    slot,
                ),
            )
        )
        for index, slot in enumerate(slots, start=1):
            slot_facts = slot_facts_by_key[slot]
            values = {field: _unique_value(slot_facts, field) for field in _BINDING_FIELDS}
            channel = values.pop("channel")
            channel_kind = _channel_kind(
                channel,
                section_context,
                selected_source_index=selected_source_index,
            )
            if channel is None or channel_kind is None:
                raise SectionWorkContractError(
                    "section_work_channel_missing",
                    "A required binding channel is not present in inspected sources.",
                )
            scale = SectionWorkScale(
                kind=values.pop("scale_kind"),
                minimum=values.pop("scale_minimum"),
                maximum=values.pop("scale_maximum"),
                reverse=values.pop("scale_reverse"),
            )
            if not any(value is not None for value in scale.model_dump().values()):
                scale = None
            work_bindings.append(
                SectionWorkBinding(
                    handle=f"{handle}.binding.{index}",
                    track_handle=handle,
                    kind="raster" if channel_kind == "array" else "curve",
                    channel=channel,
                    label=values.pop("label"),
                    scale=scale,
                    color=values.pop("color"),
                    line_width=values.pop("line_width"),
                    line_style=values.pop("line_style"),
                    alpha=values.pop("alpha"),
                    raster_profile=values.pop("raster_profile"),
                    raster_colormap=values.pop("raster_colormap"),
                    colorbar_enabled=values.pop("colorbar_enabled"),
                    colorbar_label=values.pop("colorbar_label"),
                    colorbar_position=values.pop("colorbar_position"),
                    sample_axis_enabled=values.pop("sample_axis_enabled"),
                    sample_axis_unit=values.pop("sample_axis_unit"),
                    sample_axis_minimum=values.pop("sample_axis_minimum"),
                    sample_axis_maximum=values.pop("sample_axis_maximum"),
                    sample_axis_tick_count=values.pop("sample_axis_tick_count"),
                    sample_axis_source_origin=values.pop("sample_axis_source_origin"),
                    sample_axis_source_step=values.pop("sample_axis_source_step"),
                )
            )
        if not slots:
            raise SectionWorkContractError(
                "section_work_binding_missing",
                "A required track has no compiled binding slot.",
            )

    fill_facts = [item for item in obligations if item.owner_kind is OwnerKind.FILL]
    scale_only = bool(obligations) and all(
        (
            item.owner_kind is OwnerKind.BINDING
            and item.field in {"scale_kind", "scale_minimum", "scale_maximum", "scale_reverse"}
        )
        or (item.owner_kind is OwnerKind.SECTION and item.field == "target")
        for item in obligations
    )
    if fill_facts:
        required_action: Literal[
            "reconstruct", "add_track", "add_tracks", "update_curve_scale", "add_fill"
        ] = "add_fill"
    elif scale_only and section_context.section_id is not None:
        required_action = "update_curve_scale"
    elif section_context.section_id is not None and len(work_tracks) == 1:
        required_action = "add_track"
    elif section_context.section_id is not None and len(work_tracks) > 1:
        required_action = "add_tracks"
    elif work_tracks:
        required_action = "reconstruct"
    else:
        raise SectionWorkContractError(
            "section_work_action_ambiguous", "Section task shape does not select one safe action."
        )

    target_obligation = next(
        (
            item
            for item in obligations
            if item.owner_kind is OwnerKind.SECTION and item.field == "target"
        ),
        None,
    )
    target_title = (
        str(target_obligation.value)
        if target_obligation is not None
        else task.existing_section_hint
    )
    target = SectionWorkTarget(
        kind="existing_section" if section_context.section_id is not None else "new_section",
        title=target_title,
        handle=section_context.section_handle,
    )
    target_handle = None
    required_scale = None
    required_fill = None
    if required_action == "update_curve_scale":
        scale_fields = {"scale_kind", "scale_minimum", "scale_maximum", "scale_reverse"}
        owner_names = tuple(
            dict.fromkeys(
                item.owner_ref
                for item in obligations
                if item.owner_kind is OwnerKind.BINDING and item.field in scale_fields
            )
        )
        if len(owner_names) != 1:
            raise SectionWorkContractError(
                "section_work_target_ambiguous", "Scale update must identify one existing curve."
            )
        target_handle = _existing_curve_handle(owner_names[0], section_context)
        required_scale = _scale_from_items(list(obligations))
        if (
            required_scale is None
            or required_scale.minimum is None
            or required_scale.maximum is None
        ):
            raise SectionWorkContractError(
                "section_work_scale_incomplete", "Scale update lacks explicit numeric bounds."
            )
    elif required_action == "add_fill":
        target_obligation = next(
            (
                item
                for item in obligations
                if item.owner_kind is OwnerKind.BINDING and item.field == "target"
            ),
            None,
        )
        if target_obligation is None:
            if len(section_context.existing_curves) != 1:
                raise SectionWorkContractError(
                    "section_work_target_ambiguous",
                    "Fill target is not uniquely grounded by the existing context.",
                )
            target_handle = "curve-1"
        else:
            target_handle = _existing_curve_handle(str(target_obligation.value), section_context)
        required_fill = {
            item.field: item.value for item in fill_facts if item.field in {"color", "alpha"}
        }

    source_handle = (
        selected_source_handle
        if required_action in {"reconstruct", "add_track", "add_tracks"}
        else None
    )

    sources = tuple(
        SectionWorkSource(
            handle=source.handle,
            name=_source_name(source),
            format=source.source_format,
            inspection_state=source.inspection_state,
            channels=tuple(
                SectionWorkChannel(mnemonic=channel.mnemonic, kind=channel.kind, unit=channel.unit)
                for channel in source.channels
            ),
        )
        for index, source in enumerate(section_context.sources)
    )
    preservation_rules = (
        ("preserve_existing_section_identity", "preserve_unrequested_existing_tracks")
        if section_context.section_id is not None
        else ()
    )
    return SectionWorkContract(
        snapshot_id=section_context.snapshot_id,
        target=target,
        required_action=required_action,
        required_tracks=tuple(work_tracks),
        required_bindings=tuple(work_bindings),
        source_handle=source_handle,
        target_handle=target_handle,
        required_scale=required_scale,
        required_fill=required_fill,
        source_facts=sources,
        preservation_rules=preservation_rules,
    )


def build_section_operation_contract(
    task: SectionTask,
    section_context: ResolvedSectionContext,
) -> SectionOperationContract:
    """Ground the planner inventory against request facts and one snapshot."""
    if not section_context.snapshot_id:
        raise SectionWorkContractError(
            "section_operation_snapshot_missing", "Operation contract requires a bound snapshot."
        )
    if not task.scope_ref:
        raise SectionWorkContractError(
            "section_operation_scope_missing", "Operation contract requires a declared scope."
        )
    if not task.operations:
        raise SectionWorkContractError(
            "section_operation_inventory_missing", "Section task has no semantic operations."
        )
    if len(task.operations) > MAX_SECTION_SEMANTIC_OPERATIONS:
        raise SectionWorkContractError(
            "section_operation_budget_exceeded",
            "Section operation inventory exceeds the bounded contract limit.",
        )
    if len({item.local_ref for item in task.operations}) != len(task.operations):
        raise SectionWorkContractError(
            "section_operation_duplicate_ref",
            "Section operation refs must be unique.",
        )

    obligations = tuple(task.obligations)
    if any(item.state is not ObligationState.SET for item in obligations):
        raise SectionWorkContractError(
            "section_operation_requirements_unresolved",
            "Operation contract requires resolved explicit request facts.",
        )
    request_hashes = {item.request_sha256 for item in obligations}
    if len(request_hashes) != 1:
        raise SectionWorkContractError(
            "section_operation_request_identity_invalid",
            "Section requirements do not share one authoritative request identity.",
        )
    request_sha256 = next(iter(request_hashes))
    track_owners = tuple(
        dict.fromkeys(
            item.owner_ref
            for item in obligations
            if item.owner_kind in {OwnerKind.TRACK, OwnerKind.ARRAY_TRACK}
        )
    )

    def field_matches(left: object, right: object) -> bool:
        if isinstance(left, str) and isinstance(right, str):
            return left.casefold().strip() == right.casefold().strip()
        return left == right

    def track_owner(operation: SemanticOperation) -> str | None:
        candidates = {
            _work_handle(value)
            for value in (operation.semantic_ref, operation.target_clue)
            if value
        }
        exact = [owner for owner in track_owners if _work_handle(owner) in candidates]
        if len(exact) == 1:
            return exact[0]
        title_values = [item.value for item in operation.field_values if item.field == "title"]
        if len(title_values) == 1:
            titled = [
                owner
                for owner in track_owners
                if any(
                    item.owner_ref == owner
                    and item.field == "title"
                    and field_matches(item.value, title_values[0])
                    for item in obligations
                )
            ]
            if len(titled) == 1:
                return titled[0]
        return None

    operation_ids = {
        item.local_ref: hashlib.sha256(f"{task.scope_ref}:{item.local_ref}".encode()).hexdigest()[
            :24
        ]
        for item in task.operations
    }
    semantic_operation_ids = {
        item.semantic_ref: operation_ids[item.local_ref]
        for item in task.operations
        if item.semantic_ref is not None
    }
    track_owner_by_semantic_ref = {
        item.semantic_ref: track_owner(item)
        for item in task.operations
        if item.object_kind == "track" and item.semantic_ref is not None
    }
    entries: list[WorkerOperationContractEntry] = []
    omitted_entries: list[WorkerOperationContractEntry] = []
    assigned_track_owners: set[str] = set()
    source_obligation = next(
        (item for item in obligations if item.owner_kind is OwnerKind.SOURCE), None
    )
    selected_source = (
        _source_handle(source_obligation.value, section_context)
        if source_obligation is not None
        else None
    )
    for operation in task.operations:
        if operation.scope_ref != task.scope_ref:
            raise SectionWorkContractError(
                "section_operation_scope_mismatch",
                "Operation inventory crosses its declared section scope.",
            )

        owner: str | None = None
        if operation.object_kind in {"track", "binding"}:
            owner = (
                track_owner_by_semantic_ref.get(operation.parent_ref)
                if operation.object_kind == "binding" and operation.parent_ref is not None
                else track_owner(operation)
            )
            if operation.object_kind == "track":
                if owner is None:
                    raise SectionWorkContractError(
                        "section_operation_target_unresolved",
                        "Track operation does not resolve to one request-owned track.",
                    )
                if owner in assigned_track_owners:
                    raise SectionWorkContractError(
                        "section_operation_duplicate_target",
                        "Multiple operations target the same request-owned track.",
                    )
                assigned_track_owners.add(owner)

        operation_type = _section_operation_type(operation)
        facts = [
            item
            for item in obligations
            if owner is not None
            and item.owner_ref == owner
            and item.owner_kind in {OwnerKind.TRACK, OwnerKind.ARRAY_TRACK, OwnerKind.BINDING}
        ]
        for proposal in operation.field_values:
            matching_facts = [item for item in facts if item.field == proposal.field]
            if (
                not matching_facts
                or proposal.state != "SET"
                or not any(field_matches(item.value, proposal.value) for item in matching_facts)
            ):
                raise SectionWorkContractError(
                    "section_operation_field_mismatch",
                    "Planner operation fields conflict with request-authoritative facts.",
                )

        if (
            operation.condition is not None
            and selected_source is not None
            and operation.condition.evidence_kind == "inspected_source"
            and operation.condition.evidence_ref != selected_source
        ):
            raise SectionWorkContractError(
                "section_operation_condition_source_mismatch",
                "Conditional evidence does not belong to the selected request source.",
            )
        condition_result, condition_evidence = _evaluate_operation_condition(
            operation.condition, section_context
        )
        entry = WorkerOperationContractEntry(
            operation_id=operation_ids[operation.local_ref],
            operation_ref=operation.local_ref,
            operation_type=operation_type,
            scope_ref=task.scope_ref,
            target_handle=_work_handle(owner) if owner is not None else None,
            parent_operation_id=(
                semantic_operation_ids.get(operation.parent_ref)
                if operation.parent_ref is not None
                else None
            ),
            condition_predicate=(
                operation.condition.predicate if operation.condition is not None else None
            ),
            condition_result=condition_result,
            condition_evidence=condition_evidence,
            condition_channel_clue=(
                operation.condition.channel_clue if operation.condition is not None else None
            ),
            requirement_ids=tuple(
                dict.fromkeys(item.requirement_id for item in facts if item.requirement_id)
            ),
        )
        (omitted_entries if condition_result == "CONDITION_FALSE" else entries).append(entry)

    required_track_owners = set(track_owners)
    if assigned_track_owners != required_track_owners:
        raise SectionWorkContractError(
            "section_operation_coverage_incomplete",
            "Operation inventory does not cover every request-owned track exactly once.",
        )
    ordering: list[tuple[str, str, str]] = []
    for item in task.operations:
        if item.anchor_ref is None:
            continue
        anchor_operation_id = semantic_operation_ids.get(item.anchor_ref)
        if anchor_operation_id is None:
            raise SectionWorkContractError(
                "section_operation_order_unresolved",
                "Ordering constraint references an unknown operation.",
            )
        ordering.append((operation_ids[item.local_ref], item.relation or "", anchor_operation_id))
    schema_bytes = json.dumps(
        WorkerOperationContractEntry.model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return SectionOperationContract(
        request_sha256=request_sha256,
        scope_ref=task.scope_ref,
        snapshot_id=section_context.snapshot_id,
        operations=tuple(entries),
        omitted_operations=tuple(omitted_entries),
        operation_schema_sha256=hashlib.sha256(schema_bytes).hexdigest(),
        ordering_constraints=tuple(ordering),
    )


def build_report_operation_contract(
    task: ReportTask,
    report_context: ReportContext,
) -> ReportOperationContract:
    """Bind report operation refs to obligation-backed report slots or fields."""
    if not report_context.snapshot_id:
        raise SectionWorkContractError(
            "report_operation_snapshot_missing", "Report contract requires a bound snapshot."
        )
    if not task.operations:
        raise SectionWorkContractError(
            "report_operation_inventory_missing", "Report task has no semantic operations."
        )

    obligations = tuple(
        item
        for item in task.obligations
        if item.owner_kind is OwnerKind.REPORT and item.state is ObligationState.SET
    )
    request_hashes = {item.request_sha256 for item in obligations}
    if len(request_hashes) != 1:
        raise SectionWorkContractError(
            "report_operation_request_identity_invalid",
            "Report obligations do not share one authoritative request identity.",
        )
    request_sha256 = next(iter(request_hashes))

    def normalized(value: object) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value).casefold())

    def target_for(item: RequestObligation) -> str:
        if item.field == "metadata":
            key = normalized(item.owner_ref)
            matches = [
                slot
                for slot in report_context.header_slots
                if key
                in {
                    normalized(slot.key),
                    normalized(slot.label),
                }
            ]
            if len(matches) != 1:
                raise SectionWorkContractError(
                    "report_operation_slot_ambiguous",
                    "Report metadata does not resolve to exactly one inspected slot.",
                )
            slot = matches[0]
            if slot.slot_id in report_context.general_slot_ids:
                return f"general.{slot.slot_id}"
            if slot.slot_id in report_context.detail_slot_ids:
                return f"detail.{slot.slot_id}"
            raise SectionWorkContractError(
                "report_operation_slot_unsupported",
                "Report metadata resolved outside an authorized slot group.",
            )
        if item.field == "service_title":
            if not item.slot_key or item.slot_key not in {
                f"service_title.{index}"
                for index in range(1, len(report_context.service_title_slot_ids) + 1)
            }:
                raise SectionWorkContractError(
                    "report_operation_slot_missing",
                    "Service-title requirement lacks an inspected output slot.",
                )
            index = int(item.slot_key.rsplit(".", maxsplit=1)[-1]) - 1
            return f"service_title.{report_context.service_title_slot_ids[index]}"
        if item.field == "remark":
            if not item.slot_key or not item.slot_key.startswith("remark."):
                raise SectionWorkContractError(
                    "report_operation_slot_missing",
                    "Remark requirement lacks a request-local ordered slot.",
                )
            return item.slot_key
        return f"report.{item.field}"

    entries: list[ReportOperationContractEntry] = []
    used_requirements: set[str] = set()
    seen_refs: set[str] = set()
    for operation in task.operations:
        if operation.local_ref in seen_refs:
            raise SectionWorkContractError(
                "report_operation_duplicate_ref", "Report operation refs must be unique."
            )
        seen_refs.add(operation.local_ref)
        if operation.object_kind not in {"report_field", "service_title", "remark"}:
            raise SectionWorkContractError(
                "report_operation_unsupported",
                "Report task contains an operation outside report-owned object kinds.",
            )
        if not operation.field_values:
            raise SectionWorkContractError(
                "report_operation_fields_missing",
                "Report operation has no inspected postcondition to verify.",
            )
        for proposed in operation.field_values:
            candidates = [
                item
                for item in obligations
                if item.requirement_id not in used_requirements
                and item.field == proposed.field
                and item.value == proposed.value
            ]
            clues = {
                normalized(value)
                for value in (operation.semantic_ref, operation.target_clue)
                if value
            }
            if len(candidates) > 1 and clues:
                candidates = [
                    item
                    for item in candidates
                    if normalized(item.owner_ref) in clues or normalized(item.slot_key) in clues
                ]
            if len(candidates) != 1:
                raise SectionWorkContractError(
                    "report_operation_fact_unresolved",
                    "Report operation does not resolve to exactly one request obligation.",
                )
            fact = candidates[0]
            allowed_fields = {
                "report_field": {
                    "title",
                    "subtitle",
                    "metadata",
                    "tail_enabled",
                    "depth_presentation_allowed",
                    "page_presentation_allowed",
                    "remark",
                    "service_title",
                },
                "service_title": {"service_title"},
                "remark": {"remark"},
            }[operation.object_kind]
            if fact.field not in allowed_fields:
                raise SectionWorkContractError(
                    "report_operation_field_kind_mismatch",
                    "Report operation kind does not own the requested field.",
                )
            used_requirements.add(fact.requirement_id)
            entries.append(
                ReportOperationContractEntry(
                    operation_ref=operation.local_ref,
                    field=fact.field,
                    target=target_for(fact),
                    value=fact.value,
                    requirement_id=fact.requirement_id,
                    order_index=(
                        int(fact.slot_key.rsplit(".", maxsplit=1)[-1])
                        if fact.field in {"service_title", "remark"} and fact.slot_key
                        else None
                    ),
                )
            )

    expected_requirements = {item.requirement_id for item in obligations}
    if used_requirements != expected_requirements:
        raise SectionWorkContractError(
            "report_operation_coverage_incomplete",
            "Report operations do not cover every request-owned report obligation exactly.",
        )

    known_refs = {item.local_ref for item in task.operations}
    ordering: list[tuple[str, str, str]] = []
    for constraint in task.presentation_constraints:
        if (
            constraint.scope_ref != "report"
            or constraint.item_ref not in known_refs
            or constraint.anchor_ref not in known_refs
        ):
            raise SectionWorkContractError(
                "report_operation_order_unresolved",
                "Report presentation order references an unknown operation or scope.",
            )
        ordering.append((constraint.item_ref, constraint.relation, constraint.anchor_ref))
    return ReportOperationContract(
        request_sha256=request_sha256,
        snapshot_id=report_context.snapshot_id,
        entries=tuple(entries),
        ordering_constraints=tuple(ordering),
    )


def _section_operation_type(operation: SemanticOperation) -> Literal["ADD_TRACK"]:
    """Accept only the additive operation currently consumed by this worker."""
    if operation.verb != "CREATE" or operation.object_kind != "track":
        raise SectionWorkContractError(
            "section_operation_unsupported",
            "The current section operation contract supports only track additions.",
        )
    return "ADD_TRACK"


def _evaluate_operation_condition(
    condition: OperationCondition | None,
    context: ResolvedSectionContext,
) -> tuple[str, str | None]:
    """Evaluate only conditions supported by the immutable inspected snapshot."""
    if condition is None:
        return "UNCONDITIONAL", None
    if condition.predicate in {"source_channel_available", "source_channel_absent"}:
        source = next(
            (item for item in context.sources if item.handle == condition.evidence_ref),
            None,
        )
        if source is None:
            raise SectionWorkContractError(
                "section_operation_condition_unresolved",
                "Conditional source handle is not present in the inspected snapshot.",
            )
        if source.inspection_state == "unavailable":
            raise SectionWorkContractError(
                "section_operation_condition_unresolved",
                "Conditional source inventory is unavailable.",
            )
        if source.inspection_state != "inspected":
            raise SectionWorkContractError(
                "section_operation_condition_unresolved",
                "Conditional source inventory has not been inspected.",
            )
        matches = [
            channel
            for channel in source.channels
            if channel.mnemonic.casefold() == (condition.channel_clue or "").casefold()
        ]
        if len(matches) > 1:
            raise SectionWorkContractError(
                "section_operation_condition_ambiguous",
                "The inspected source has ambiguous channel identity for the condition.",
            )
        found = bool(matches)
        expected_found = condition.predicate == "source_channel_available"
        if found == expected_found:
            return "CONDITION_TRUE", source.handle
        return "CONDITION_FALSE", source.handle
    raise SectionWorkContractError(
        "section_operation_condition_unresolved",
        "The operation condition cannot be resolved from the inspected snapshot.",
    )


def validate_section_action_contract(
    action: object,
    contract: SectionWorkContract,
    operation_contract: SectionOperationContract | None = None,
) -> None:
    """Reject provider output that violates the deterministic work contract."""
    if getattr(action, "action", None) != contract.required_action:
        raise SectionWorkContractError(
            "worker_contract_action_mismatch", "Section response used an unauthorized action."
        )
    if contract.required_action == "reconstruct":
        section = action.section
        if contract.target.title is not None and section.title != contract.target.title:
            raise SectionWorkContractError(
                "worker_contract_target_mismatch", "Section response changed the required target."
            )
        allowed_sources = {source.handle for source in contract.source_facts}
        if section.source_candidate not in allowed_sources or (
            contract.source_handle is not None
            and section.source_candidate != contract.source_handle
        ):
            raise SectionWorkContractError(
                "worker_contract_source_mismatch",
                "Section response selected an unknown source handle.",
            )
        tracks = tuple(section.tracks)
    elif contract.required_action == "add_track":
        tracks = (action.track,)
    elif contract.required_action == "add_tracks":
        patches = tuple(action.operations)
        tracks = tuple(item.track for item in patches)
        if operation_contract is None:
            raise SectionWorkContractError(
                "worker_operation_contract_missing",
                "Sparse track batches require an authoritative operation contract.",
            )
        if (
            not operation_contract.operations
            or operation_contract.snapshot_id != contract.snapshot_id
            or any(
                item.scope_ref != operation_contract.scope_ref
                for item in operation_contract.operations
            )
        ):
            raise SectionWorkContractError(
                "worker_operation_contract_identity_mismatch",
                "Operation contract is empty or not bound to the work snapshot.",
            )
        if any(
            item.operation_type != "ADD_TRACK"
            for item in (*operation_contract.operations, *operation_contract.omitted_operations)
        ):
            raise SectionWorkContractError(
                "worker_operation_combination_unsupported",
                "The response shape cannot cover every operation in this section task.",
            )
        if {item.operation_ref for item in operation_contract.operations}.intersection(
            item.operation_ref for item in operation_contract.omitted_operations
        ):
            raise SectionWorkContractError(
                "worker_operation_set_mismatch",
                "An operation cannot be both admitted and conditionally omitted.",
            )
        expected_by_ref = {item.operation_ref: item for item in operation_contract.operations}
        actual_refs = tuple(item.operation_ref for item in patches)
        expected_refs = tuple(item.operation_ref for item in operation_contract.operations)
        if len(actual_refs) != len(set(actual_refs)) or set(actual_refs) != set(expected_refs):
            raise SectionWorkContractError(
                "worker_operation_set_mismatch",
                "Track patch operation refs differ from the authorized operation set.",
            )
        if any(
            patch.track.semantic_id != expected_by_ref[patch.operation_ref].target_handle
            for patch in patches
        ):
            raise SectionWorkContractError(
                "worker_operation_target_mismatch",
                "A track patch is assigned to the wrong authorized operation.",
            )
        if actual_refs != expected_refs:
            raise SectionWorkContractError(
                "worker_operation_order_mismatch",
                "Track patches do not preserve the authorized operation order.",
            )
    elif contract.required_action == "update_curve_scale":
        if action.target.handle != contract.target_handle or not _scale_matches(
            action.scale, contract.required_scale
        ):
            raise SectionWorkContractError(
                "worker_contract_incomplete",
                "Scale update does not match its required target and scale.",
            )
        return
    else:
        if action.target.handle != contract.target_handle:
            raise SectionWorkContractError(
                "worker_contract_target_mismatch", "Fill response changed the required target."
            )
        if action.fill.target_binding != contract.target_handle:
            raise SectionWorkContractError(
                "worker_contract_target_mismatch", "Fill binding target differs from the contract."
            )
        for field, expected_value in (contract.required_fill or {}).items():
            actual_value = getattr(action.fill, field, None)
            if actual_value != expected_value:
                raise SectionWorkContractError(
                    "worker_contract_fill_mismatch", "Fill semantics differ from the work contract."
                )
        return

    expected_tracks = {track.handle: track for track in contract.required_tracks}
    actual_handles = [track.semantic_id for track in tracks]
    if len(actual_handles) != len(expected_tracks) or set(actual_handles) != set(expected_tracks):
        raise SectionWorkContractError(
            "worker_contract_incomplete",
            "Section response omitted or added required tracks.",
            details=_handle_mismatch_details(
                "TRACK_HANDLE_SET_MISMATCH", list(expected_tracks), actual_handles
            ),
        )
    expected_bindings = {binding.handle: binding for binding in contract.required_bindings}
    actual_bindings: dict[str, tuple[str, object]] = {}
    for track in tracks:
        expected_track = expected_tracks.get(track.semantic_id)
        if expected_track is None:
            continue
        if (
            track.kind != expected_track.kind
            or (expected_track.title is not None and track.title != expected_track.title)
            or (expected_track.width_mm is not None and track.width_mm != expected_track.width_mm)
        ):
            raise SectionWorkContractError(
                "worker_contract_track_mismatch", "Track identity or required fields differ."
            )
        if expected_track.scale is not None and not _scale_matches(
            track.x_scale, expected_track.scale
        ):
            raise SectionWorkContractError(
                "worker_contract_track_mismatch", "Track scale differs from the work contract."
            )
        if (
            expected_track.vertical_main_visible is not None
            and getattr(getattr(track, "grid", None), "vertical_main_visible", None)
            != expected_track.vertical_main_visible
        ):
            raise SectionWorkContractError(
                "worker_contract_track_mismatch", "Track grid differs from the work contract."
            )
        if (
            expected_track.vertical_secondary_visible is not None
            and getattr(getattr(track, "grid", None), "vertical_secondary_visible", None)
            != expected_track.vertical_secondary_visible
        ):
            raise SectionWorkContractError(
                "worker_contract_track_mismatch", "Track grid differs from the work contract."
            )
        for binding in track.bindings:
            if binding.semantic_id in actual_bindings:
                raise SectionWorkContractError(
                    "worker_contract_duplicate_handle",
                    "Section response duplicated a binding handle.",
                )
            actual_bindings[binding.semantic_id] = (track.semantic_id, binding)
    if set(actual_bindings) != set(expected_bindings):
        raise SectionWorkContractError(
            "worker_contract_incomplete",
            "Section response omitted or added required bindings.",
            details=_handle_mismatch_details(
                "BINDING_HANDLE_SET_MISMATCH",
                list(expected_bindings),
                list(actual_bindings),
                owners={
                    handle: binding.track_handle for handle, binding in expected_bindings.items()
                },
            ),
        )
    for handle, expected in expected_bindings.items():
        track_handle, actual = actual_bindings[handle]
        if track_handle != expected.track_handle:
            raise SectionWorkContractError(
                "worker_contract_binding_owner_mismatch",
                "Binding handle was attached to another track.",
            )
        if actual.kind != expected.kind:
            raise SectionWorkContractError(
                "worker_contract_binding_mismatch", "Binding kind differs from the work contract."
            )
        for field in _BINDING_FIELDS:
            expected_value = _expected_binding_value(expected, field)
            if expected_value is None:
                continue
            actual_value = _actual_binding_value(actual, field)
            if actual_value != expected_value:
                raise SectionWorkContractError(
                    "worker_contract_binding_mismatch",
                    "Binding semantics differ from the work contract.",
                )


def _expected_binding_value(binding: SectionWorkBinding, field: str) -> object | None:
    """Read a flat contract field from its normalized binding representation."""
    if field == "scale_kind":
        return binding.scale.kind if binding.scale is not None else None
    if field in {"scale_minimum", "scale_maximum", "scale_reverse"}:
        scale_field = {
            "scale_minimum": "minimum",
            "scale_maximum": "maximum",
            "scale_reverse": "reverse",
        }[field]
        return getattr(binding.scale, scale_field) if binding.scale is not None else None
    return getattr(binding, field, None)


def _actual_binding_value(binding: object, field: str) -> object | None:
    """Read canonical curve/raster semantics without fuzzy field substitution."""
    if field == "scale_kind":
        return getattr(getattr(binding, "scale", None), "kind", None)
    if field in {"scale_minimum", "scale_maximum", "scale_reverse"}:
        scale_field = {
            "scale_minimum": "minimum",
            "scale_maximum": "maximum",
            "scale_reverse": "reverse",
        }[field]
        return getattr(getattr(binding, "scale", None), scale_field, None)
    if field in {"color", "line_width", "line_style"}:
        return getattr(getattr(binding, "style", None), field, None)
    if field == "raster_profile":
        return getattr(binding, "profile", None)
    if field == "raster_colormap":
        return getattr(binding, "colormap", None)
    if field == "sample_axis_enabled":
        return getattr(binding, "sample_axis", None) is not None
    if field.startswith("sample_axis_"):
        axis_field = field.removeprefix("sample_axis_")
        return getattr(getattr(binding, "sample_axis", None), axis_field, None)
    return getattr(binding, field, None)


def _scale_matches(actual: object | None, expected: SectionWorkScale | None) -> bool:
    """Compare only fields fixed by request obligations."""
    if actual is None or expected is None:
        return False
    for field in ("kind", "minimum", "maximum", "reverse"):
        expected_value = getattr(expected, field)
        if expected_value is not None and getattr(actual, field, None) != expected_value:
            return False
    return True


@dataclass(frozen=True, slots=True)
class CanonicalWorkerResult:
    """Stable worker result consumed by the shared Code Mode graph."""

    success: bool
    intent_fragment: AuthoringDocumentIntent | None
    diagnostics: tuple[SemanticDiagnostic, ...]
    metrics: SemanticMetrics
    stage_evidence: SemanticStageEvidence = SemanticStageEvidence()


__all__ = [
    "CanonicalWorkerResult",
    "MAX_SECTION_SEMANTIC_OPERATIONS",
    "ReportOperationContract",
    "ReportOperationContractEntry",
    "SectionOperationContract",
    "SectionWorkBinding",
    "SectionWorkChannel",
    "SectionWorkContract",
    "SectionWorkContractError",
    "SectionWorkScale",
    "SectionWorkSource",
    "SectionWorkTarget",
    "SectionWorkTrack",
    "WorkerOperationContractEntry",
    "build_section_operation_contract",
    "build_report_operation_contract",
    "build_section_work_contract",
    "validate_section_action_contract",
]
