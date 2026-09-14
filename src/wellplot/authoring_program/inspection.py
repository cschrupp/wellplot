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

"""Bounded, read-only context projections for Code Mode workers.

The facade accepts only an explicit canonical document and explicit channel
context. It exposes fixed projections rather than arbitrary paths, filters, or
document serialization. Source discovery and file inspection remain outside
the authoring-program layer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy

from pydantic import BaseModel, ConfigDict, Field

from ..authoring_context import AuthoringChannelCandidate, AuthoringChannelInput
from ..model.authoring import AuthoringDocumentSpec, AuthoringSectionSpec, TrackSpec
from .errors import ProgramNameError


class _InspectionModel(BaseModel):
    """Strict immutable base for bounded inspection projections."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class DocumentInspectionSummary(_InspectionModel):
    """Small report summary without nested canonical document content."""

    name: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)
    subtitle: str | None = Field(default=None, min_length=1)
    section_ids: tuple[str, ...] = ()


class SectionInspectionSummary(_InspectionModel):
    """One section summary in canonical document order."""

    section_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    subtitle: str | None = Field(default=None, min_length=1)
    depth_range: tuple[float, float] | None = None
    track_ids: tuple[str, ...] = ()
    track_kinds: tuple[str, ...] = ()


class TrackInspectionSummary(_InspectionModel):
    """One track summary scoped to its selected section."""

    track_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    width_mm: float = Field(gt=0)
    binding_ids: tuple[str, ...] = ()


class BindingInspectionSummary(_InspectionModel):
    """One binding summary scoped to its selected section and track."""

    binding_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    channel: str = Field(min_length=1)


class HeaderSlotInspectionSummary(_InspectionModel):
    """Semantic header-slot identity without current value or layout internals."""

    slot_id: str = Field(min_length=1)
    key: str | None = Field(default=None, min_length=1)
    label: str | None = Field(default=None, min_length=1)


class ChannelInspectionSummary(_InspectionModel):
    """Compact source-channel metadata supplied by the caller."""

    mnemonic: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    unit: str | None = Field(default=None, min_length=1)
    shape: tuple[int, ...] = ()


class AuthoringInspectionFacade:
    """Expose fixed immutable projections of explicit authoring context.

    Document-derived projections preserve canonical order. External channel
    candidates are normalized by the caller-provided section key and returned
    in lexical ``(mnemonic, kind, unit)`` order. No source path or source
    object is inferred or exposed.
    """

    def __init__(
        self,
        document: AuthoringDocumentSpec,
        *,
        available_channels: Mapping[str, Sequence[AuthoringChannelInput]] | None = None,
    ) -> None:
        """Capture defensive copies of the document and scoped channel facts."""
        if not isinstance(document, AuthoringDocumentSpec):
            raise TypeError("Inspection document must be an AuthoringDocumentSpec.")
        self._document = _clone_document(document)
        self._available_channels = _normalize_channels(available_channels)

    def document_summary(self) -> DocumentInspectionSummary:
        """Return report identity and section IDs without nested document data."""
        return DocumentInspectionSummary(
            name=self._document.name,
            title=self._document.title,
            subtitle=self._document.subtitle,
            section_ids=tuple(section.id for section in self._document.sections),
        )

    def sections(self) -> tuple[SectionInspectionSummary, ...]:
        """Return section summaries in canonical document order."""
        return tuple(
            SectionInspectionSummary(
                section_id=section.id,
                title=section.title,
                subtitle=section.subtitle,
                depth_range=section.depth_range,
                track_ids=tuple(track.id for track in section.tracks),
                track_kinds=tuple(track.kind for track in section.tracks),
            )
            for section in self._document.sections
        )

    def tracks(self, section_id: str) -> tuple[TrackInspectionSummary, ...]:
        """Return tracks in one explicitly selected section."""
        section = self._section(section_id)
        return tuple(
            TrackInspectionSummary(
                track_id=track.id,
                title=track.title,
                kind=track.kind,
                width_mm=track.width_mm,
                binding_ids=tuple(binding.binding_id for binding in getattr(track, "bindings", ())),
            )
            for track in section.tracks
        )

    def bindings(
        self,
        section_id: str,
        track_id: str,
    ) -> tuple[BindingInspectionSummary, ...]:
        """Return bindings for a section-scoped track selection."""
        track = self._track(section_id, track_id)
        return tuple(
            BindingInspectionSummary(
                binding_id=binding.binding_id,
                kind=binding.kind,
                channel=binding.channel,
            )
            for binding in getattr(track, "bindings", ())
        )

    def header_slots(self) -> tuple[HeaderSlotInspectionSummary, ...]:
        """Return stable header slot identities in canonical header order."""
        header = self._document.header
        if header is None:
            return ()

        slots: list[HeaderSlotInspectionSummary] = [
            HeaderSlotInspectionSummary(
                slot_id=field.slot_id,
                key=field.key,
                label=field.label,
            )
            for field in header.general_fields
        ]
        slots.extend(
            HeaderSlotInspectionSummary(slot_id=title.slot_id) for title in header.service_titles
        )
        if header.detail is not None:
            for row in header.detail.rows:
                if row.values:
                    slots.extend(
                        HeaderSlotInspectionSummary(
                            slot_id=cell.slot_id,
                            key=row.key,
                            label=row.label,
                        )
                        for cell in row.values
                    )
                    continue
                for column_index, column in enumerate(row.columns):
                    key = row.keys[column_index] if column_index < len(row.keys) else None
                    label = (
                        row.label_cells[column_index]
                        if column_index < len(row.label_cells)
                        else None
                    )
                    slots.extend(
                        HeaderSlotInspectionSummary(
                            slot_id=cell.slot_id,
                            key=key,
                            label=label,
                        )
                        for cell in column.cells
                    )
        return tuple(slots)

    def channels(self, section_id: str) -> tuple[ChannelInspectionSummary, ...]:
        """Return only explicit source-channel metadata for one section key."""
        self._section(section_id)
        candidates = self._available_channels.get(section_id, ())
        ordered = sorted(
            candidates,
            key=lambda candidate: (
                candidate.mnemonic.casefold(),
                candidate.kind.casefold(),
                (candidate.unit or "").casefold(),
            ),
        )
        return tuple(
            ChannelInspectionSummary(
                mnemonic=candidate.mnemonic,
                kind=candidate.kind,
                unit=candidate.unit,
                shape=tuple(candidate.value_shape),
            )
            for candidate in ordered
        )

    def _section(self, section_id: str) -> AuthoringSectionSpec:
        """Resolve a section through the fixed section-scoped API."""
        for section in self._document.sections:
            if section.id == section_id:
                return section
        raise ProgramNameError(f"Section '{section_id}' is not available.")

    def _track(self, section_id: str, track_id: str) -> TrackSpec:
        """Resolve a track only within its explicitly selected section."""
        section = self._section(section_id)
        for track in section.tracks:
            if track.id == track_id:
                return track
        raise ProgramNameError(f"Track '{track_id}' is not available in section '{section_id}'.")


def _clone_document(document: AuthoringDocumentSpec) -> AuthoringDocumentSpec:
    """Return a detached canonical document copy for read-only projections."""
    return AuthoringDocumentSpec.model_validate(deepcopy(document).model_dump(mode="python"))


def _normalize_channels(
    available_channels: Mapping[str, Sequence[AuthoringChannelInput]] | None,
) -> dict[str, tuple[AuthoringChannelCandidate, ...]]:
    """Normalize explicit section-scoped channel facts without discovering data."""
    if available_channels is None:
        return {}
    normalized: dict[str, tuple[AuthoringChannelCandidate, ...]] = {}
    for section_id, values in available_channels.items():
        normalized[str(section_id)] = tuple(
            value
            if isinstance(value, AuthoringChannelCandidate)
            else AuthoringChannelCandidate.model_validate(value)
            if isinstance(value, Mapping)
            else AuthoringChannelCandidate(mnemonic=value)
            for value in deepcopy(tuple(values))
        )
    return normalized


__all__ = [
    "AuthoringInspectionFacade",
    "BindingInspectionSummary",
    "ChannelInspectionSummary",
    "DocumentInspectionSummary",
    "HeaderSlotInspectionSummary",
    "SectionInspectionSummary",
    "TrackInspectionSummary",
]
