"""Deterministic host-side enrichment for Code Mode semantic plans."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...authoring_context import AuthoringChannelCandidate
from ...authoring_program.inspection import (
    AuthoringInspectionFacade,
    ChannelInspectionSummary,
    HeaderSlotInspectionSummary,
)
from ...model.authoring import AuthoringDocumentSpec
from .planner import SectionTask, SemanticPlan

SourceFormat = Literal["las", "dlis"]


class _EnrichmentModel(BaseModel):
    """Shared strict immutable configuration for transient enrichment context."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class SourceCandidate(_EnrichmentModel):
    """One host-approved source candidate available for deterministic selection."""

    candidate_id: str = Field(min_length=1)
    root_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    labels: tuple[str, ...] = ()
    trusted_format: SourceFormat | None = None

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


class ChannelContext(_EnrichmentModel):
    """Semantic channel metadata without samples or parser objects."""

    mnemonic: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    unit: str | None = Field(default=None, min_length=1)
    shape: tuple[int, ...] = ()
    description: str = ""
    aliases: tuple[str, ...] = ()


class LoadedSource(_EnrichmentModel):
    """Bounded loader output accepted by the enrichment boundary."""

    dataset_name: str = ""
    well_metadata: tuple[SourceMetadata, ...] = ()
    channels: tuple[ChannelContext, ...] = ()


class SourceContext(_EnrichmentModel):
    """One normalized, inspected source attached to a semantic task."""

    candidate_id: str = Field(min_length=1)
    canonical_path: str = Field(min_length=1)
    source_format: SourceFormat
    dataset_name: str = ""
    well_metadata: tuple[SourceMetadata, ...] = ()
    channels: tuple[ChannelContext, ...] = ()


class ResolvedSectionContext(_EnrichmentModel):
    """Canonical read-only context for one semantic section task."""

    task_index: int = Field(ge=0)
    section_id: str | None = Field(default=None, min_length=1)
    sources: tuple[SourceContext, ...] = ()
    channels: tuple[ChannelInspectionSummary, ...] = ()


class ReportContext(_EnrichmentModel):
    """Read-only report inventory exposed to a future worker."""

    header_slots: tuple[HeaderSlotInspectionSummary, ...] = ()


class EnrichedSemanticContext(_EnrichmentModel):
    """Transient worker context preserving the original semantic plan."""

    plan: SemanticPlan
    sections: tuple[ResolvedSectionContext, ...]
    report: ReportContext


class EnrichmentErrorCode(StrEnum):
    """Stable deterministic failure categories for enrichment."""

    SOURCE_MISSING = "source_missing"
    SOURCE_OUTSIDE_ROOT = "source_outside_root"
    SOURCE_FORMAT_UNKNOWN = "source_format_unknown"
    SOURCE_FORMAT_CONFLICT = "source_format_conflict"
    SOURCE_AMBIGUOUS = "source_ambiguous"
    SOURCE_LOAD_FAILED = "source_load_failed"
    SECTION_HINT_UNRESOLVED = "section_hint_unresolved"
    SECTION_HINT_AMBIGUOUS = "section_hint_ambiguous"


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

    def enrich(
        self,
        *,
        plan: SemanticPlan,
        document: AuthoringDocumentSpec,
        source_candidates: Sequence[SourceCandidate],
    ) -> EnrichedSemanticContext:
        """Enrich one plan without changing it or mutating the document."""
        roots = _normalize_roots(self.allowed_roots)
        candidates = _normalize_candidates(source_candidates, roots)
        loaded_cache: dict[tuple[Path, SourceFormat], LoadedSource] = {}
        resolved_sources: dict[int, tuple[SourceContext, ...]] = {}

        for task_index, task in enumerate(plan.section_tasks):
            selected = _select_sources(task, candidates, task_index=task_index)
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
            section_id = _resolved_section_id(plan.section_tasks[task_index], document)
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
        sections = tuple(
            self._section_context(
                task,
                task_index=task_index,
                document=document,
                inspection=inspection,
                sources=resolved_sources[task_index],
            )
            for task_index, task in enumerate(plan.section_tasks)
        )
        return EnrichedSemanticContext(
            plan=plan,
            sections=sections,
            report=ReportContext(header_slots=inspection.header_slots()),
        )

    def _load_source(
        self,
        candidate: _NormalizedCandidate,
        *,
        loaded_cache: dict[tuple[Path, SourceFormat], LoadedSource],
        task_index: int,
    ) -> SourceContext:
        """Load one canonical candidate at most once per enrichment call."""
        cache_key = (candidate.path, candidate.source_format)
        if cache_key not in loaded_cache:
            try:
                loaded_cache[cache_key] = self.loader.load(
                    candidate.path,
                    candidate.source_format,
                )
            except Exception as exc:
                raise SemanticEnrichmentError(
                    EnrichmentErrorCode.SOURCE_LOAD_FAILED,
                    "The selected source could not be inspected.",
                    task_index=task_index,
                    candidate_id=candidate.candidate_id,
                ) from exc
        loaded = loaded_cache[cache_key]
        return SourceContext(
            candidate_id=candidate.candidate_id,
            canonical_path=str(candidate.path),
            source_format=candidate.source_format,
            dataset_name=loaded.dataset_name,
            well_metadata=loaded.well_metadata,
            channels=loaded.channels,
        )

    @staticmethod
    def _section_context(
        task: SectionTask,
        *,
        task_index: int,
        document: AuthoringDocumentSpec,
        inspection: AuthoringInspectionFacade,
        sources: tuple[SourceContext, ...],
    ) -> ResolvedSectionContext:
        """Project canonical section and channels through the inspection facade."""
        section_id = _resolved_section_id(task, document, task_index=task_index)
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
            sources=sources,
            channels=channels,
        )


@dataclass(frozen=True, slots=True)
class _NormalizedCandidate:
    """Internal canonical candidate retained only during one enrichment call."""

    candidate_id: str
    path: Path
    source_format: SourceFormat
    labels: tuple[str, ...]


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
        try:
            canonical_path = path.resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_MISSING,
                "The explicit source candidate does not exist.",
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
        if not canonical_path.is_file() or not os.access(canonical_path, os.R_OK):
            raise SemanticEnrichmentError(
                EnrichmentErrorCode.SOURCE_MISSING,
                "The explicit source candidate is not a readable regular file.",
                candidate_id=candidate.candidate_id,
            )
        source_format = _source_format(candidate, canonical_path)
        normalized.append(
            _NormalizedCandidate(
                candidate_id=candidate.candidate_id,
                path=canonical_path,
                source_format=source_format,
                labels=tuple(candidate.labels),
            )
        )
    return tuple(sorted(normalized, key=lambda item: item.candidate_id.casefold()))


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
    for value in (
        candidate.candidate_id,
        candidate.path.name,
        candidate.path.stem,
        *candidate.labels,
    ):
        normalized = _normalize_lexical(value)
        if normalized:
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
    )


__all__ = [
    "ChannelContext",
    "EnrichedSemanticContext",
    "EnrichmentErrorCode",
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
]
