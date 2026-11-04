"""Deterministic host-side enrichment for Code Mode semantic plans."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...authoring_context import AuthoringChannelCandidate
from ...file_revision import file_revision_token
from ...model.authoring import AuthoringDocumentSpec
from ...model.intent import AuthoringDocumentIntent
from ..inspection import (
    AuthoringInspectionFacade,
    ChannelInspectionSummary,
    HeaderSlotInspectionSummary,
)
from .obligations import ObligationKind
from .planner import CompilationMode, SectionTask, SemanticPlan

SourceFormat = Literal["las", "dlis"]
MAX_SERIALIZED_INSPECTION_CONTEXT_BYTES = 1_048_576


class _EnrichmentModel(BaseModel):
    """Shared strict immutable configuration for transient enrichment context."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class ChannelContext(_EnrichmentModel):
    """Semantic channel metadata without samples or parser objects."""

    mnemonic: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    unit: str | None = Field(default=None, min_length=1)
    shape: tuple[int, ...] = ()
    description: str = ""
    aliases: tuple[str, ...] = ()
    physical_identity: dict[str, object] = Field(default_factory=dict)
    addressability: Literal["ADDRESSABLE", "UNADDRESSABLE", "UNKNOWN"] = "ADDRESSABLE"
    frame_indexes: tuple[int, ...] = ()
    sample_availability: Literal["NOT_CHECKED"] = "NOT_CHECKED"


class SourceCandidate(_EnrichmentModel):
    """One host-approved source candidate available for deterministic selection."""

    candidate_id: str = Field(min_length=1)
    root_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    labels: tuple[str, ...] = ()
    trusted_format: SourceFormat | None = None
    inspection_state: Literal["inspected", "not_inspected", "unavailable"] = "not_inspected"
    channels: tuple[ChannelContext, ...] = ()
    expected_revision_token: str | None = None

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Reject blank candidate labels."""
        if any(not value.strip() for value in values):
            raise ValueError("Source candidate labels cannot contain blank items.")
        return values


class SourceMetadata(_EnrichmentModel):
    """One bounded JSON-safe well metadata value."""

    key: str = Field(min_length=1)
    value: str = Field(min_length=1)


class LoadedSource(_EnrichmentModel):
    """Bounded loader output accepted by the enrichment boundary."""

    dataset_name: str = ""
    well_metadata: tuple[SourceMetadata, ...] = ()
    channels: tuple[ChannelContext, ...] = ()


class SourceContext(_EnrichmentModel):
    """One normalized, inspected source attached to a semantic task."""

    candidate_id: str = Field(min_length=1)
    handle: str = Field(default="source-1", min_length=1)
    labels: tuple[str, ...] = ()
    canonical_path: str | None = None
    source_format: SourceFormat | None = None
    inspection_state: Literal["inspected", "not_inspected", "unavailable"] = "inspected"
    revision_token: str | None = None
    dataset_name: str = ""
    well_metadata: tuple[SourceMetadata, ...] = ()
    channels: tuple[ChannelContext, ...] = ()


class ExistingCurveContext(_EnrichmentModel):
    """One exact existing curve identity available to a revision worker."""

    track_id: str = Field(min_length=1)
    track_title: str = Field(min_length=1)
    track_kind: str = Field(min_length=1)
    binding_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    label: str | None = Field(default=None, min_length=1)
    scale_kind: str | None = Field(default=None, min_length=1)
    scale_minimum: float | None = None
    scale_maximum: float | None = None
    reverse: bool | None = None


class ResolvedSectionContext(_EnrichmentModel):
    """Canonical read-only context for one semantic section task."""

    task_index: int = Field(ge=0)
    section_id: str | None = Field(default=None, min_length=1)
    section_handle: str | None = Field(default=None, min_length=1)
    snapshot_id: str | None = Field(default=None, min_length=1)
    sources: tuple[SourceContext, ...] = ()
    channels: tuple[ChannelInspectionSummary, ...] = ()
    existing_curves: tuple[ExistingCurveContext, ...] = ()


class ReportContext(_EnrichmentModel):
    """Read-only report inventory exposed to a future worker."""

    snapshot_id: str | None = None
    header_slots: tuple[HeaderSlotInspectionSummary, ...] = ()
    general_slot_ids: tuple[str, ...] = ()
    service_title_slot_ids: tuple[str, ...] = ()
    detail_slot_ids: tuple[str, ...] = ()


class SnapshotSource(_EnrichmentModel):
    """Opaque source identity and explicit inspection state in one snapshot."""

    handle: str = Field(min_length=1)
    inspection_state: Literal["inspected", "not_inspected", "unavailable"]
    revision_token: str | None = None


class DocumentInspectionSnapshot(_EnrichmentModel):
    """Versioned host-owned identity shared by all tasks in one graph run."""

    version: Literal["wellplot.document-inspection.v1"] = "wellplot.document-inspection.v1"
    snapshot_id: str = Field(min_length=1)
    document_revision: str = Field(min_length=1)
    sources: tuple[SnapshotSource, ...] = ()


class EnrichmentWarning(_EnrichmentModel):
    """Safe non-fatal evidence produced during deterministic enrichment."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class EnrichedSemanticContext(_EnrichmentModel):
    """Transient worker context preserving the original semantic plan."""

    plan: SemanticPlan
    sections: tuple[ResolvedSectionContext, ...]
    report: ReportContext
    snapshot: DocumentInspectionSnapshot | None = None
    snapshot_bytes: int = Field(default=0, ge=0)
    warnings: tuple[EnrichmentWarning, ...] = ()


class EnrichmentErrorCode(StrEnum):
    """Stable deterministic failure categories for enrichment."""

    SOURCE_MISSING = "source_missing"
    SOURCE_OUTSIDE_ROOT = "source_outside_root"
    SOURCE_FORMAT_UNKNOWN = "source_format_unknown"
    SOURCE_FORMAT_CONFLICT = "source_format_conflict"
    SOURCE_AMBIGUOUS = "source_ambiguous"
    SOURCE_LOAD_FAILED = "source_load_failed"
    SOURCE_INSPECTION_BUSY = "source_inspection_busy"
    SOURCE_INSPECTION_INCOMPLETE = "source_inspection_incomplete"
    SECTION_HINT_UNRESOLVED = "section_hint_unresolved"
    SECTION_HINT_AMBIGUOUS = "section_hint_ambiguous"
    SECTION_TARGET_DUPLICATE = "section_target_duplicate"
    SECTION_TARGET_CARDINALITY_AMBIGUOUS = "section_target_cardinality_ambiguous"
    SCOPE_BINDING_MISMATCH = "scope_binding_mismatch"
    SNAPSHOT_STALE = "snapshot_stale"
    INSPECTION_CONTEXT_LIMIT = "inspection_context_limit"


class SemanticEnrichmentError(ValueError):
    """Safe typed error for one deterministic enrichment failure."""

    def __init__(
        self,
        code: EnrichmentErrorCode,
        message: str,
        *,
        task_index: int | None = None,
        candidate_id: str | None = None,
        candidates: tuple[str, ...] = (),
    ) -> None:
        """Create an error without retaining raw paths or parser exceptions."""
        self.code = code
        self.task_index = task_index
        self.candidate_id = candidate_id
        self.candidates = candidates
        super().__init__(message)


class SourceLoaderProtocol(Protocol):
    """Host-supplied loader for one already-normalized source file."""

    def load(self, path: Path, source_format: SourceFormat) -> LoadedSource:
        """Load bounded metadata and channel projections from one source."""


@dataclass(frozen=True, slots=True)
class SemanticEnricher:
    """Resolve explicit host candidates into immutable worker context."""

    loader: SourceLoaderProtocol
    allowed_roots: Mapping[str, str | Path]
    max_context_bytes: int = MAX_SERIALIZED_INSPECTION_CONTEXT_BYTES

    def __post_init__(self) -> None:
        """Reject a disabled or nonsensical serialized-context budget."""
        if not 1 <= self.max_context_bytes <= MAX_SERIALIZED_INSPECTION_CONTEXT_BYTES:
            raise ValueError("The inspection context byte limit is outside its allowed range.")

    def enrich(
        self,
        *,
        plan: SemanticPlan,
        request: str | None = None,
        document: AuthoringDocumentSpec,
        source_candidates: Sequence[SourceCandidate],
        mode: CompilationMode = "reconstruct",
        expected_document_revision: str | None = None,
    ) -> EnrichedSemanticContext:
        """Enrich one plan without changing it or mutating the document."""
        document_revision = AuthoringInspectionFacade(document).document_revision()
        if (
            expected_document_revision is not None
            and expected_document_revision != document_revision
        ):
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SNAPSHOT_STALE,
                "The document changed between planning and source inspection.",
            )
        target_obligations = tuple(
            item for item in plan.obligations if item.kind is ObligationKind.TARGET_REFERENCE
        )
        if len(target_obligations) == 1 and len(plan.section_tasks) > 1:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SECTION_TARGET_CARDINALITY_AMBIGUOUS,
                "One request target cannot authorize multiple section tasks.",
            )
        resolved_section_ids: list[str | None] = []
        warnings: list[EnrichmentWarning] = []
        for task_index, task in enumerate(plan.section_tasks):
            try:
                resolved_section_ids.append(
                    _resolved_section_id(task, document, task_index=task_index)
                )
            except SemanticEnrichmentError as error:
                if (
                    mode == "reconstruct"
                    and error.code is EnrichmentErrorCode.SECTION_HINT_UNRESOLVED
                ):
                    resolved_section_ids.append(None)
                    warnings.append(
                        EnrichmentWarning(
                            code="section_hint_unresolved_downgraded",
                            message=(
                                "An advisory existing-section hint was not resolved; "
                                "compiling as a new section."
                            ),
                        )
                    )
                    continue
                raise
        _validate_unique_section_targets(resolved_section_ids)
        for task, section_id in zip(plan.section_tasks, resolved_section_ids, strict=True):
            scope_id = task.scope_id
            if scope_id is None:
                raise SemanticEnrichmentError(
                    EnrichmentErrorCode.SCOPE_BINDING_MISMATCH,
                    "Section task has no host-bound request scope.",
                )
            if scope_id.startswith("existing:") and section_id is None:
                raise SemanticEnrichmentError(
                    EnrichmentErrorCode.SCOPE_BINDING_MISMATCH,
                    "Request-declared existing section did not resolve in host context.",
                )
            if scope_id.startswith("new:") and section_id is not None:
                raise SemanticEnrichmentError(
                    EnrichmentErrorCode.SCOPE_BINDING_MISMATCH,
                    "New-section task unexpectedly resolved to an existing section.",
                )
        roots = _normalize_roots(self.allowed_roots)
        candidates = _normalize_candidates(source_candidates, roots)
        loaded_cache: dict[tuple[Path, SourceFormat], LoadedSource] = {}
        resolved_sources: dict[int, tuple[SourceContext, ...]] = {}

        for task_index, task in enumerate(plan.section_tasks):
            selected = (
                _select_sources(task, candidates, task_index=task_index)
                if _task_requires_source_inspection(task)
                else ()
            )
            resolved_sources[task_index] = tuple(
                self._load_source(
                    candidate,
                    loaded_cache=loaded_cache,
                    task_index=task_index,
                )
                for candidate in selected
            )

        available_channels: dict[str, list[AuthoringChannelCandidate]] = {}
        for task_index, sources in resolved_sources.items():
            section_id = resolved_section_ids[task_index]
            if section_id is None:
                continue
            available_channels[section_id] = [
                _channel_candidate(channel, source_path=source.canonical_path)
                for source in sources
                for channel in source.channels
            ]
        inspection = AuthoringInspectionFacade(
            document,
            available_channels=available_channels,
        )
        sources_by_handle = {
            source.handle: source for sources in resolved_sources.values() for source in sources
        }
        snapshot_sources = tuple(
            SnapshotSource(
                handle=source.handle,
                inspection_state=source.inspection_state,
                revision_token=source.revision_token,
            )
            for source in sorted(sources_by_handle.values(), key=lambda item: item.handle)
        )
        snapshot_payload = {
            "version": "wellplot.document-inspection.v1",
            "document_revision": document_revision,
            "sources": [item.model_dump(mode="json") for item in snapshot_sources],
        }
        snapshot_id = hashlib.sha256(
            json.dumps(snapshot_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        snapshot = DocumentInspectionSnapshot(
            snapshot_id=snapshot_id,
            document_revision=document_revision,
            sources=snapshot_sources,
        )
        sections = tuple(
            self._section_context(
                task,
                task_index=task_index,
                section_id=resolved_section_ids[task_index],
                inspection=inspection,
                document=document,
                sources=resolved_sources[task_index],
                snapshot_id=snapshot_id,
            )
            for task_index, task in enumerate(plan.section_tasks)
        )
        context = EnrichedSemanticContext(
            plan=plan,
            sections=sections,
            report=ReportContext(
                snapshot_id=snapshot_id,
                header_slots=_report_header_slots(document, inspection.header_slots()),
                general_slot_ids=_general_slot_ids(document),
                service_title_slot_ids=_service_title_slot_ids(document),
                detail_slot_ids=_detail_slot_ids(document),
            ),
            snapshot=snapshot,
            warnings=tuple(warnings),
        )
        serialized_size = len(
            json.dumps(
                context.model_dump(mode="json", exclude={"snapshot_bytes"}),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if serialized_size > self.max_context_bytes:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.INSPECTION_CONTEXT_LIMIT,
                "The inspected worker context exceeds its configured size limit.",
            )
        return context.model_copy(update={"snapshot_bytes": serialized_size})

    def validate_snapshot(
        self,
        context: EnrichedSemanticContext,
        document: AuthoringDocumentSpec,
    ) -> None:
        """Fail closed when captured document or source revisions have changed."""
        validate_enriched_snapshot(context, document)

    def _load_source(
        self,
        candidate: _NormalizedCandidate,
        *,
        loaded_cache: dict[tuple[Path, SourceFormat], LoadedSource],
        task_index: int,
    ) -> SourceContext:
        """Load one canonical candidate at most once per enrichment call."""
        if candidate.path is None:
            return SourceContext(
                candidate_id=candidate.candidate_id,
                handle=candidate.handle,
                labels=candidate.labels,
                source_format=candidate.source_format,
                inspection_state="unavailable",
            )
        if not candidate.path.is_file() or not os.access(candidate.path, os.R_OK):
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_MISSING,
                "The selected source is not a readable regular file.",
                task_index=task_index,
                candidate_id=candidate.candidate_id,
            )
        if candidate.source_format is None:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_FORMAT_UNKNOWN,
                "The selected source format is not deterministically known.",
                task_index=task_index,
                candidate_id=candidate.candidate_id,
            )
        try:
            revision_before = file_revision_token(candidate.path)
        except OSError as exc:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_MISSING,
                "The selected source changed before inspection.",
                task_index=task_index,
                candidate_id=candidate.candidate_id,
            ) from exc
        if (
            candidate.expected_revision_token is not None
            and revision_before != candidate.expected_revision_token
        ):
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SNAPSHOT_STALE,
                "A source changed after request context was captured.",
                task_index=task_index,
                candidate_id=candidate.candidate_id,
            )
        cache_key = (candidate.path, candidate.source_format)
        if cache_key not in loaded_cache:
            try:
                loaded_cache[cache_key] = self.loader.load(
                    candidate.path,
                    candidate.source_format,
                )
            except Exception as exc:
                inspection_code = getattr(exc, "code", None)
                if inspection_code == "inspection_busy":
                    code = EnrichmentErrorCode.SOURCE_INSPECTION_BUSY
                elif isinstance(inspection_code, str):
                    code = EnrichmentErrorCode.SOURCE_INSPECTION_INCOMPLETE
                else:
                    code = EnrichmentErrorCode.SOURCE_LOAD_FAILED
                raise SemanticEnrichmentError(
                    code,
                    "The selected source could not be inspected.",
                    task_index=task_index,
                    candidate_id=candidate.candidate_id,
                ) from exc
        loaded = loaded_cache[cache_key]
        try:
            revision_after = file_revision_token(candidate.path)
        except OSError as exc:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SNAPSHOT_STALE,
                "The selected source became unavailable during inspection.",
                task_index=task_index,
                candidate_id=candidate.candidate_id,
            ) from exc
        if revision_before != revision_after:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SNAPSHOT_STALE,
                "A source changed while it was being inspected.",
                task_index=task_index,
                candidate_id=candidate.candidate_id,
            )
        return SourceContext(
            candidate_id=candidate.candidate_id,
            handle=candidate.handle,
            labels=candidate.labels,
            canonical_path=str(candidate.path),
            source_format=candidate.source_format,
            inspection_state="inspected",
            revision_token=revision_after,
            dataset_name=loaded.dataset_name,
            well_metadata=loaded.well_metadata,
            channels=loaded.channels,
        )

    @staticmethod
    def _section_context(
        task: SectionTask,
        *,
        task_index: int,
        section_id: str | None,
        inspection: AuthoringInspectionFacade,
        document: AuthoringDocumentSpec,
        sources: tuple[SourceContext, ...],
        snapshot_id: str,
    ) -> ResolvedSectionContext:
        """Project canonical section and channels through the inspection facade."""
        if section_id is None:
            channels = tuple(
                ChannelInspectionSummary(
                    mnemonic=channel.mnemonic,
                    kind=channel.kind,
                    unit=channel.unit,
                    shape=channel.shape,
                )
                for source in sources
                for channel in source.channels
            )
        else:
            channels = inspection.channels(section_id)
        return ResolvedSectionContext(
            task_index=task_index,
            section_id=section_id,
            section_handle=(None if section_id is None else inspection.section_handle(section_id)),
            snapshot_id=snapshot_id,
            sources=sources,
            channels=channels,
            existing_curves=_existing_curves(document, section_id),
        )


@dataclass(frozen=True, slots=True)
class _NormalizedCandidate:
    """Internal canonical candidate retained only during one enrichment call."""

    candidate_id: str
    handle: str
    path: Path | None
    source_format: SourceFormat | None
    inspection_state: Literal["inspected", "not_inspected", "unavailable"]
    labels: tuple[str, ...]
    expected_revision_token: str | None = None


def _existing_curves(
    document: AuthoringDocumentSpec,
    section_id: str | None,
) -> tuple[ExistingCurveContext, ...]:
    """Project exact curve identities from the selected current section."""
    if section_id is None:
        return ()
    for section in document.sections:
        if section.id != section_id:
            continue
        curves: list[ExistingCurveContext] = []
        for track in section.tracks:
            for binding in getattr(track, "bindings", ()):
                if getattr(binding, "kind", None) != "curve":
                    continue
                scale = getattr(binding, "scale", None)
                curves.append(
                    ExistingCurveContext(
                        track_id=track.id,
                        track_title=track.title,
                        track_kind=track.kind,
                        binding_id=binding.binding_id,
                        channel=binding.channel,
                        label=getattr(binding, "label", None),
                        scale_kind=None if scale is None else scale.kind.value,
                        scale_minimum=None if scale is None else scale.minimum,
                        scale_maximum=None if scale is None else scale.maximum,
                        reverse=None if scale is None else scale.reverse,
                    )
                )
        return tuple(curves)
    return ()


def _task_requires_source_inspection(task: SectionTask) -> bool:
    """Inspect only when host-bound request facts need physical source evidence."""
    if task.source_hints or "section.log_plot" in task.capability_ids:
        return True
    return any(
        obligation.field in {"channel", "source"}
        for obligation in task.obligations
        if obligation.state.value not in {"FORBIDDEN", "UNRESOLVED"}
    )


def _normalize_roots(roots: Mapping[str, str | Path]) -> dict[str, Path]:
    """Resolve explicit roots and reject missing or non-directory roots."""
    if not roots:
        raise SemanticEnrichmentError(
            EnrichmentErrorCode.SOURCE_OUTSIDE_ROOT,
            "At least one allowed source root is required.",
        )
    normalized: dict[str, Path] = {}
    for root_id, raw_root in roots.items():
        if not str(root_id).strip():
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_OUTSIDE_ROOT,
                "An allowed source root has an empty identifier.",
            )
        root = Path(raw_root).expanduser()
        try:
            resolved = root.resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_MISSING,
                "An allowed source root does not exist.",
            ) from exc
        if not resolved.is_dir():
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_OUTSIDE_ROOT,
                "An allowed source root is not a directory.",
            )
        normalized[str(root_id)] = resolved
    return normalized


def _normalize_candidates(
    candidates: Sequence[SourceCandidate],
    roots: Mapping[str, Path],
) -> tuple[_NormalizedCandidate, ...]:
    """Canonicalize only explicit candidates under their declared roots."""
    normalized: list[_NormalizedCandidate] = []
    seen_ids: set[str] = set()
    for candidate in candidates:
        if candidate.candidate_id in seen_ids:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_AMBIGUOUS,
                "Source candidate identifiers must be unique.",
                candidate_id=candidate.candidate_id,
            )
        seen_ids.add(candidate.candidate_id)
        try:
            root = roots[candidate.root_id]
        except KeyError as exc:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_OUTSIDE_ROOT,
                "The source candidate references an unknown allowed root.",
                candidate_id=candidate.candidate_id,
            ) from exc

        requested = Path(candidate.path).expanduser()
        path = requested if requested.is_absolute() else root / requested
        if candidate.inspection_state == "unavailable":
            normalized.append(
                _NormalizedCandidate(
                    candidate_id=candidate.candidate_id,
                    handle="",
                    path=None,
                    source_format=_source_format_hint(candidate, path),
                    inspection_state="unavailable",
                    labels=tuple(dict.fromkeys((*candidate.labels, path.name, path.stem))),
                )
            )
            continue
        try:
            canonical_path = path.resolve(strict=False)
        except OSError as exc:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_MISSING,
                "The explicit source candidate cannot be resolved.",
                candidate_id=candidate.candidate_id,
            ) from exc
        try:
            canonical_path.relative_to(root)
        except ValueError as exc:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_OUTSIDE_ROOT,
                "The explicit source candidate resolves outside its allowed root.",
                candidate_id=candidate.candidate_id,
            ) from exc
        source_format = _source_format_hint(candidate, canonical_path)
        normalized.append(
            _NormalizedCandidate(
                candidate_id=candidate.candidate_id,
                handle="",
                path=canonical_path,
                source_format=source_format,
                inspection_state=candidate.inspection_state,
                labels=tuple(candidate.labels),
                expected_revision_token=candidate.expected_revision_token,
            )
        )
    ordered = sorted(normalized, key=lambda item: (item.candidate_id.casefold(), item.candidate_id))
    return tuple(
        _NormalizedCandidate(
            candidate_id=item.candidate_id,
            handle=f"source-{index + 1}",
            path=item.path,
            source_format=item.source_format,
            inspection_state=item.inspection_state,
            labels=item.labels,
            expected_revision_token=item.expected_revision_token,
        )
        for index, item in enumerate(ordered)
    )


def _source_format_hint(candidate: SourceCandidate, path: Path) -> SourceFormat | None:
    """Infer an unavailable candidate format without resolving its path."""
    suffix_format: SourceFormat | None = {
        ".las": "las",
        ".dlis": "dlis",
    }.get(path.suffix.casefold())
    if candidate.trusted_format is not None:
        if suffix_format is not None and candidate.trusted_format != suffix_format:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_FORMAT_CONFLICT,
                "The trusted source format conflicts with the file suffix.",
                candidate_id=candidate.candidate_id,
            )
        return candidate.trusted_format
    return suffix_format


def _source_format(candidate: SourceCandidate, path: Path) -> SourceFormat:
    """Infer a known format and reject trusted metadata conflicts."""
    suffix = path.suffix.casefold()
    suffix_format: SourceFormat | None = {
        ".las": "las",
        ".dlis": "dlis",
    }.get(suffix)
    trusted_format = candidate.trusted_format
    if trusted_format is not None and suffix_format is not None and trusted_format != suffix_format:
        raise SemanticEnrichmentError(
            EnrichmentErrorCode.SOURCE_FORMAT_CONFLICT,
            "The trusted source format conflicts with the file suffix.",
            candidate_id=candidate.candidate_id,
        )
    if trusted_format is not None:
        return trusted_format
    if suffix_format is None:
        raise SemanticEnrichmentError(
            EnrichmentErrorCode.SOURCE_FORMAT_UNKNOWN,
            "The source format is not deterministically known.",
            candidate_id=candidate.candidate_id,
        )
    return suffix_format


def _select_sources(
    task: SectionTask,
    candidates: Sequence[_NormalizedCandidate],
    *,
    task_index: int,
) -> tuple[_NormalizedCandidate, ...]:
    """Select only bounded candidates using conservative lexical matching."""
    if not task.source_hints:
        if len(candidates) == 1:
            return (candidates[0],)
        if len(candidates) > 1:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_AMBIGUOUS,
                "Multiple explicit source candidates require a source hint.",
                task_index=task_index,
                candidates=tuple(candidate.candidate_id for candidate in candidates),
            )
        return ()
    selected: dict[str, _NormalizedCandidate] = {}
    for hint in task.source_hints:
        normalized_hint = _normalize_lexical(hint)
        matches = tuple(
            candidate
            for candidate in candidates
            if any(
                _lexical_contains(normalized_hint, label) for label in _candidate_labels(candidate)
            )
        )
        if not matches:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_MISSING,
                "A source hint did not match an explicit host candidate.",
                task_index=task_index,
            )
        if len(matches) > 1:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_AMBIGUOUS,
                "A source hint matched multiple explicit host candidates.",
                task_index=task_index,
                candidates=tuple(item.candidate_id for item in matches),
            )
        selected[matches[0].candidate_id] = matches[0]
    return tuple(sorted(selected.values(), key=lambda item: item.candidate_id.casefold()))


def _candidate_labels(candidate: _NormalizedCandidate) -> tuple[str, ...]:
    """Return only host-supplied labels and canonical filename labels."""
    labels: list[str] = []
    path_labels = () if candidate.path is None else (candidate.path.name, candidate.path.stem)
    for value in (candidate.candidate_id, *path_labels):
        normalized = _normalize_lexical(value)
        if normalized:
            labels.append(normalized)
    format_label = _normalize_lexical(candidate.source_format)
    for raw_label in candidate.labels:
        normalized = _normalize_lexical(raw_label)
        if normalized and normalized != format_label:
            labels.append(normalized)
    return tuple(labels)


def _lexical_contains(hint: str, label: str) -> bool:
    """Match exact or whole-phrase containment without fuzzy scoring."""
    return hint == label or label in hint or hint in label


def _normalize_lexical(value: object) -> str:
    """Normalize only case and repeated whitespace for lexical matching."""
    if value is None:
        return ""
    return " ".join(str(value).casefold().strip().split())


def _resolved_section_id(
    task: SectionTask,
    document: AuthoringDocumentSpec,
    *,
    task_index: int | None = None,
) -> str | None:
    """Resolve an advisory hint by exact title, subtitle, then containment."""
    if task.existing_section_hint is None:
        return None
    hint = _normalize_lexical(task.existing_section_hint)
    sections = tuple(document.sections)
    for field_name in ("title", "subtitle"):
        exact = tuple(
            section
            for section in sections
            if _normalize_lexical(getattr(section, field_name, "")) == hint
        )
        if exact:
            return _unique_section_id(exact, task_index=task_index)
    contained = tuple(
        section
        for section in sections
        if any(
            hint in _normalize_lexical(getattr(section, field_name, ""))
            or _normalize_lexical(getattr(section, field_name, "")) in hint
            for field_name in ("title", "subtitle")
        )
    )
    if contained:
        return _unique_section_id(contained, task_index=task_index)
    raise SemanticEnrichmentError(
        EnrichmentErrorCode.SECTION_HINT_UNRESOLVED,
        "The existing-section hint did not match an inspected section.",
        task_index=task_index,
    )


def _unique_section_id(
    sections: Sequence[object],
    *,
    task_index: int | None,
) -> str:
    """Return one section ID or a stable ambiguity error."""
    section_ids = tuple(str(section.id) for section in sections)
    if len(section_ids) > 1:
        raise SemanticEnrichmentError(
            EnrichmentErrorCode.SECTION_HINT_AMBIGUOUS,
            "The existing-section hint matched multiple inspected sections.",
            task_index=task_index,
            candidates=section_ids,
        )
    return section_ids[0]


def _validate_unique_section_targets(section_ids: Sequence[str | None]) -> None:
    """Reject multiple semantic tasks targeting one canonical section."""
    first_by_id: dict[str, int] = {}
    for task_index, section_id in enumerate(section_ids):
        if section_id is None:
            continue
        first_index = first_by_id.get(section_id)
        if first_index is not None:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SECTION_TARGET_DUPLICATE,
                "Multiple section tasks resolve to the same existing section target.",
                task_index=task_index,
                candidates=(str(first_index), str(task_index)),
            )
        first_by_id[section_id] = task_index


def _channel_candidate(channel: ChannelContext, *, source_path: str) -> AuthoringChannelCandidate:
    """Adapt bounded source metadata to the canonical inspection facade input."""
    return AuthoringChannelCandidate(
        mnemonic=channel.mnemonic,
        kind=channel.kind,
        unit=channel.unit,
        description=channel.description,
        aliases=list(channel.aliases),
        value_shape=list(channel.shape),
        source_path=source_path,
        physical_identity=channel.physical_identity,
        addressability=channel.addressability,
    )


def reconciliation_channels(
    context: EnrichedSemanticContext,
    intent: AuthoringDocumentIntent,
) -> dict[str, tuple[AuthoringChannelCandidate, ...]]:
    """Project the exact inspected channels for canonical reconciliation."""
    available: dict[str, tuple[AuthoringChannelCandidate, ...]] = {}
    sections = intent.sections if isinstance(intent.sections, list) else []
    for section_context in context.sections:
        target_ids: set[str] = set()
        if section_context.section_id is not None:
            target_ids.add(section_context.section_id)
        source_paths = {
            _normalized_source_path(source.canonical_path)
            for source in section_context.sources
            if source.canonical_path is not None
        }
        for section in sections:
            data_source = getattr(section, "data_source", None)
            requested_path = getattr(data_source, "source_path", None)
            if (
                requested_path is not None
                and _normalized_source_path(requested_path) in source_paths
            ):
                target_ids.add(section.section_id)
        if not target_ids:
            continue
        channels = tuple(
            _channel_candidate(channel, source_path=source.canonical_path)
            for source in section_context.sources
            if source.canonical_path is not None
            for channel in source.channels
        )
        for section_id in target_ids:
            previous = available.get(section_id)
            if previous is not None and previous != channels:
                raise SemanticEnrichmentError(
                    EnrichmentErrorCode.SOURCE_AMBIGUOUS,
                    "Multiple inspected source projections target one section.",
                )
            available[section_id] = channels
    return available


def intent_requires_channel_context(intent: AuthoringDocumentIntent) -> bool:
    """Return whether canonical reconciliation needs inspected channel facts."""
    for section in intent.sections if isinstance(intent.sections, list) else ():
        for track in section.tracks if isinstance(section.tracks, list) else ():
            if getattr(track, "bindings", None):
                return True
    return bool(intent.curve_bindings or intent.raster_bindings)


def _normalized_source_path(value: str) -> str:
    """Normalize only host-side source identity for projection joins."""
    return str(Path(value).expanduser().resolve(strict=False))


def validate_enriched_snapshot(
    context: EnrichedSemanticContext,
    document: AuthoringDocumentSpec,
) -> None:
    """Validate snapshot binding and recheck source revisions before use."""
    snapshot = context.snapshot
    if snapshot is None:
        raise SemanticEnrichmentError(
            EnrichmentErrorCode.SNAPSHOT_STALE,
            "Worker context is missing its required inspection snapshot.",
        )

    if any(section.snapshot_id != snapshot.snapshot_id for section in context.sections):
        raise SemanticEnrichmentError(
            EnrichmentErrorCode.SNAPSHOT_STALE,
            "Section context is not bound to the captured document snapshot.",
        )
    if context.report.snapshot_id != snapshot.snapshot_id:
        raise SemanticEnrichmentError(
            EnrichmentErrorCode.SNAPSHOT_STALE,
            "Report context is not bound to the captured document snapshot.",
        )
    if AuthoringInspectionFacade(document).document_revision() != snapshot.document_revision:
        raise SemanticEnrichmentError(
            EnrichmentErrorCode.SNAPSHOT_STALE,
            "The document no longer matches the inspected source snapshot.",
        )

    snapshot_payload = {
        "version": snapshot.version,
        "document_revision": snapshot.document_revision,
        "sources": [source.model_dump(mode="json") for source in snapshot.sources],
    }
    expected_snapshot_id = hashlib.sha256(
        json.dumps(snapshot_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if expected_snapshot_id != snapshot.snapshot_id:
        raise SemanticEnrichmentError(
            EnrichmentErrorCode.SNAPSHOT_STALE,
            "Inspection snapshot identity does not match its captured contents.",
        )

    sources_by_handle: dict[str, SourceContext] = {}
    for section in context.sections:
        for source in section.sources:
            previous = sources_by_handle.get(source.handle)
            if previous is not None and (
                previous.inspection_state != source.inspection_state
                or previous.revision_token != source.revision_token
                or previous.canonical_path != source.canonical_path
            ):
                raise SemanticEnrichmentError(
                    EnrichmentErrorCode.SNAPSHOT_STALE,
                    "Repeated source handles do not identify the same inspected source.",
                )
            sources_by_handle[source.handle] = source

    actual_source_identity = tuple(
        SnapshotSource(
            handle=source.handle,
            inspection_state=source.inspection_state,
            revision_token=source.revision_token,
        )
        for source in sorted(sources_by_handle.values(), key=lambda item: item.handle)
    )
    if actual_source_identity != snapshot.sources:
        raise SemanticEnrichmentError(
            EnrichmentErrorCode.SNAPSHOT_STALE,
            "Source context does not match its captured snapshot identity.",
        )

    for source in sources_by_handle.values():
        if source.inspection_state != "inspected":
            continue
        if source.canonical_path is None or source.revision_token is None:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SNAPSHOT_STALE,
                "An inspected source is missing its revision identity.",
            )
        try:
            current = file_revision_token(Path(source.canonical_path))
        except OSError as exc:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SNAPSHOT_STALE,
                "An inspected source is no longer available.",
            ) from exc
        if current != source.revision_token:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SNAPSHOT_STALE,
                "An inspected source changed before canonical publication.",
            )


def _general_slot_ids(document: AuthoringDocumentSpec) -> tuple[str, ...]:
    """Return the host-owned general header slot identities."""
    if document.header is None:
        return ()
    return tuple(field.slot_id for field in document.header.general_fields)


def _service_title_slot_ids(document: AuthoringDocumentSpec) -> tuple[str, ...]:
    """Return the host-owned service-title slot identities."""
    if document.header is None:
        return ()
    return tuple(title.slot_id for title in document.header.service_titles)


def _detail_slot_ids(document: AuthoringDocumentSpec) -> tuple[str, ...]:
    """Return detail-table slot identities in their canonical document order."""
    if document.header is None or document.header.detail is None:
        return ()
    slot_ids: list[str] = []
    for row in document.header.detail.rows:
        slot_ids.extend(cell.slot_id for cell in row.values)
        for column in row.columns:
            slot_ids.extend(cell.slot_id for cell in column.cells)
    return tuple(slot_ids)


def _report_header_slots(
    document: AuthoringDocumentSpec,
    inspected_slots: tuple[HeaderSlotInspectionSummary, ...],
) -> tuple[HeaderSlotInspectionSummary, ...]:
    """Attach canonical detail-row ownership to detail value cells."""
    slots = {slot.slot_id: slot for slot in inspected_slots}
    detail = document.header.detail if document.header is not None else None
    if detail is None:
        return inspected_slots

    for row in detail.rows:
        if row.values:
            for index, cell in enumerate(row.values):
                slots[cell.slot_id] = HeaderSlotInspectionSummary(
                    slot_id=cell.slot_id,
                    key=row.key if index == 0 else None,
                    label=row.label if index == 0 else None,
                )
            continue
        for column_index, column in enumerate(row.columns):
            row_key = row.keys[column_index] if column_index < len(row.keys) else row.key
            row_label = (
                row.label_cells[column_index] if column_index < len(row.label_cells) else row.label
            )
            for cell_index, cell in enumerate(column.cells):
                slots[cell.slot_id] = HeaderSlotInspectionSummary(
                    slot_id=cell.slot_id,
                    key=row_key if cell_index == 0 else None,
                    label=row_label if cell_index == 0 else None,
                )
    return tuple(slots[slot.slot_id] for slot in inspected_slots)


__all__ = [
    "ChannelContext",
    "DocumentInspectionSnapshot",
    "EnrichedSemanticContext",
    "EnrichmentWarning",
    "EnrichmentErrorCode",
    "ExistingCurveContext",
    "HeaderSlotInspectionSummary",
    "LoadedSource",
    "ReportContext",
    "ResolvedSectionContext",
    "SemanticEnricher",
    "SemanticEnrichmentError",
    "SourceCandidate",
    "SourceContext",
    "SourceFormat",
    "SourceLoaderProtocol",
    "SourceMetadata",
    "SnapshotSource",
]
