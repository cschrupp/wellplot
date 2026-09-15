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

"""Typed identity and ownership handles without document-construction behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import uuid4

from .errors import ProgramNameError, ProgramPolicyError, ProgramTypeError
from .ids import IdAllocator
from .runtime import RuntimeHandle, _register_runtime_handle_type


@dataclass(frozen=True, slots=True)
class ReportHandle(RuntimeHandle):
    """Identity-only root handle issued by one :class:`HandleBuilder`."""

    builder_id: str
    report_id: str

    def __post_init__(self) -> None:
        """Validate the fixed typed-handle identity contract."""
        RuntimeHandle.__post_init__(self)
        _validate_handle_fields(self.builder_id, self.report_id)
        if self.kind != "report":
            raise ValueError("Report handles must use kind 'report'.")


@dataclass(frozen=True, slots=True)
class SourceHandle(RuntimeHandle):
    """Opaque host-registered source candidate handle."""

    builder_id: str
    candidate_id: str

    def __post_init__(self) -> None:
        """Validate source identity without carrying filesystem metadata."""
        RuntimeHandle.__post_init__(self)
        _validate_handle_fields(self.builder_id, self.candidate_id)
        if self.kind != "source":
            raise ValueError("Source handles must use kind 'source'.")


@dataclass(frozen=True, slots=True)
class SectionHandle(RuntimeHandle):
    """Identity-only section handle with its report parent token."""

    builder_id: str
    report_token: str
    section_id: str

    def __post_init__(self) -> None:
        """Validate the fixed typed-handle identity contract."""
        RuntimeHandle.__post_init__(self)
        _validate_handle_fields(self.builder_id, self.report_token, self.section_id)
        if self.kind != "section":
            raise ValueError("Section handles must use kind 'section'.")


@dataclass(frozen=True, slots=True)
class TrackHandle(RuntimeHandle):
    """Identity-only track handle with its section ownership path."""

    builder_id: str
    section_token: str
    section_id: str
    track_id: str

    def __post_init__(self) -> None:
        """Validate the fixed typed-handle identity contract."""
        RuntimeHandle.__post_init__(self)
        _validate_handle_fields(self.builder_id, self.section_token, self.section_id, self.track_id)
        if self.kind != "track":
            raise ValueError("Track handles must use kind 'track'.")


@dataclass(frozen=True, slots=True)
class BindingHandle(RuntimeHandle):
    """Identity-only binding handle with its track ownership path."""

    builder_id: str
    track_token: str
    section_id: str
    track_id: str
    binding_id: str

    def __post_init__(self) -> None:
        """Validate the fixed typed-handle identity contract."""
        RuntimeHandle.__post_init__(self)
        _validate_handle_fields(
            self.builder_id,
            self.track_token,
            self.section_id,
            self.track_id,
            self.binding_id,
        )
        if self.kind != "binding":
            raise ValueError("Binding handles must use kind 'binding'.")


@dataclass(frozen=True, slots=True)
class FillHandle(RuntimeHandle):
    """Identity-only fill handle with its track ownership path."""

    builder_id: str
    track_token: str
    section_id: str
    track_id: str
    fill_id: str

    def __post_init__(self) -> None:
        """Validate the fixed typed-handle identity contract."""
        RuntimeHandle.__post_init__(self)
        _validate_handle_fields(
            self.builder_id,
            self.track_token,
            self.section_id,
            self.track_id,
            self.fill_id,
        )
        if self.kind != "fill":
            raise ValueError("Fill handles must use kind 'fill'.")


@dataclass(frozen=True, slots=True)
class AnnotationHandle(RuntimeHandle):
    """Identity-only annotation handle with its track ownership path."""

    builder_id: str
    track_token: str
    section_id: str
    track_id: str
    annotation_id: str

    def __post_init__(self) -> None:
        """Validate the fixed typed-handle identity contract."""
        RuntimeHandle.__post_init__(self)
        _validate_handle_fields(
            self.builder_id,
            self.track_token,
            self.section_id,
            self.track_id,
            self.annotation_id,
        )
        if self.kind != "annotation":
            raise ValueError("Annotation handles must use kind 'annotation'.")


for _handle_type in (
    ReportHandle,
    SourceHandle,
    SectionHandle,
    TrackHandle,
    BindingHandle,
    FillHandle,
    AnnotationHandle,
):
    _register_runtime_handle_type(_handle_type)


class HandleBuilder:
    """Issue, adopt, and validate typed identities without authoring state."""

    def __init__(
        self,
        *,
        allocator: IdAllocator | None = None,
        builder_id: str | None = None,
    ) -> None:
        """Create one isolated identity context with opaque handle provenance."""
        self._allocator = allocator or IdAllocator()
        self._builder_id = _builder_identity(builder_id)
        self._issued: dict[str, RuntimeHandle] = {}

    @property
    def allocator(self) -> IdAllocator:
        """Expose the owned allocator for deterministic reservation inspection."""
        return self._allocator

    @property
    def builder_id(self) -> str:
        """Return the opaque provenance value attached to handles from this builder."""
        return self._builder_id

    def create_report(self, report_id: str = "report") -> ReportHandle:
        """Issue one report identity without creating document content."""
        canonical_report_id = _identity_text(report_id, "report id")
        return self._issue_report(canonical_report_id)

    def adopt_report(self, report_id: str = "report") -> ReportHandle:
        """Return the equivalent report identity without allocating a replacement."""
        return self.create_report(report_id)

    def create_source(self, candidate_id: str) -> SourceHandle:
        """Issue one opaque handle for a host-registered source candidate."""
        canonical_candidate_id = _identity_text(candidate_id, "source candidate id")
        token = self._token("source", canonical_candidate_id)
        return self._issue(
            SourceHandle(
                token=token,
                kind="source",
                builder_id=self._builder_id,
                candidate_id=canonical_candidate_id,
            )
        )

    def create_section(self, report: ReportHandle, id_hint: str | None = None) -> SectionHandle:
        """Allocate and issue one document-scoped section identity."""
        owned_report = self._require_handle(report, ReportHandle)
        section_id = self._allocator.allocate_section(id_hint)
        return self._issue_section(owned_report, section_id)

    def adopt_section(self, report: ReportHandle, section_id: str) -> SectionHandle:
        """Adopt one exact existing section identity idempotently."""
        owned_report = self._require_handle(report, ReportHandle)
        canonical_section_id = self._allocator.adopt_section(section_id)
        return self._issue_section(owned_report, canonical_section_id)

    def create_track(self, section: SectionHandle, id_hint: str | None = None) -> TrackHandle:
        """Allocate and issue one section-scoped local track identity."""
        owned_section = self._require_handle(section, SectionHandle)
        track_id = self._allocator.allocate_track(owned_section.section_id, id_hint)
        return self._issue_track(owned_section, track_id)

    def adopt_track(self, section: SectionHandle, track_id: str) -> TrackHandle:
        """Adopt one exact existing local track identity idempotently."""
        owned_section = self._require_handle(section, SectionHandle)
        canonical_track_id = self._allocator.adopt_track(owned_section.section_id, track_id)
        return self._issue_track(owned_section, canonical_track_id)

    def create_binding(
        self,
        track: TrackHandle,
        *,
        channel: str | None = None,
        id_hint: str | None = None,
    ) -> BindingHandle:
        """Allocate one globally unique binding identity from channel or advisory hint."""
        owned_track = self._require_handle(track, TrackHandle)
        binding_id = self._allocator.allocate_binding(
            owned_track.section_id,
            owned_track.track_id,
            channel=channel,
            id_hint=id_hint,
        )
        return self._issue_binding(owned_track, binding_id)

    def adopt_binding(self, track: TrackHandle, binding_id: str) -> BindingHandle:
        """Adopt one exact existing binding identity idempotently."""
        owned_track = self._require_handle(track, TrackHandle)
        canonical_binding_id = self._allocator.adopt_binding(binding_id)
        return self._issue_binding(owned_track, canonical_binding_id)

    def create_fill(self, track: TrackHandle, id_hint: str | None = None) -> FillHandle:
        """Allocate one generic fill identity without fill-domain semantics."""
        owned_track = self._require_handle(track, TrackHandle)
        fill_id = self._allocator.allocate_leaf(
            owned_track.section_id,
            owned_track.track_id,
            leaf_kind="fill",
            id_hint=id_hint,
        )
        return self._issue_fill(owned_track, fill_id)

    def adopt_fill(self, track: TrackHandle, fill_id: str) -> FillHandle:
        """Adopt one exact existing fill identity idempotently."""
        owned_track = self._require_handle(track, TrackHandle)
        canonical_fill_id = self._allocator.adopt_leaf(fill_id)
        return self._issue_fill(owned_track, canonical_fill_id)

    def create_annotation(
        self,
        track: TrackHandle,
        id_hint: str | None = None,
    ) -> AnnotationHandle:
        """Allocate one generic annotation identity without annotation semantics."""
        owned_track = self._require_handle(track, TrackHandle)
        annotation_id = self._allocator.allocate_leaf(
            owned_track.section_id,
            owned_track.track_id,
            leaf_kind="annotation",
            id_hint=id_hint,
        )
        return self._issue_annotation(owned_track, annotation_id)

    def adopt_annotation(self, track: TrackHandle, annotation_id: str) -> AnnotationHandle:
        """Adopt one exact existing annotation identity idempotently."""
        owned_track = self._require_handle(track, TrackHandle)
        canonical_annotation_id = self._allocator.adopt_leaf(annotation_id)
        return self._issue_annotation(owned_track, canonical_annotation_id)

    def validate_section_parent(self, report: ReportHandle, section: SectionHandle) -> None:
        """Require that one issued section belongs to the supplied report handle."""
        owned_report = self._require_handle(report, ReportHandle)
        owned_section = self._require_handle(section, SectionHandle)
        if owned_section.report_token != owned_report.token:
            raise ProgramPolicyError("Section handle does not belong to the supplied report.")

    def validate_report(self, report: ReportHandle) -> ReportHandle:
        """Return one issued report handle after provenance validation."""
        return cast(ReportHandle, self._require_handle(report, ReportHandle))

    def validate_source(self, source: SourceHandle) -> SourceHandle:
        """Return one issued source handle after provenance validation."""
        return cast(SourceHandle, self._require_handle(source, SourceHandle))

    def validate_section(self, section: SectionHandle) -> SectionHandle:
        """Return one issued section handle after provenance validation."""
        return cast(SectionHandle, self._require_handle(section, SectionHandle))

    def validate_track(self, track: TrackHandle) -> TrackHandle:
        """Return one issued track handle after provenance validation."""
        return cast(TrackHandle, self._require_handle(track, TrackHandle))

    def validate_binding(self, binding: BindingHandle) -> BindingHandle:
        """Return one issued binding handle after provenance validation."""
        return cast(BindingHandle, self._require_handle(binding, BindingHandle))

    def validate_fill(self, fill: FillHandle) -> FillHandle:
        """Return one issued fill handle after provenance validation."""
        return cast(FillHandle, self._require_handle(fill, FillHandle))

    def validate_annotation(self, annotation: AnnotationHandle) -> AnnotationHandle:
        """Return one issued annotation handle after provenance validation."""
        return cast(AnnotationHandle, self._require_handle(annotation, AnnotationHandle))

    def validate_track_parent(self, section: SectionHandle, track: TrackHandle) -> None:
        """Require that one issued track belongs to the supplied section handle."""
        owned_section = self._require_handle(section, SectionHandle)
        owned_track = self._require_handle(track, TrackHandle)
        if owned_track.section_token != owned_section.token:
            raise ProgramPolicyError("Track handle does not belong to the supplied section.")

    def validate_leaf_parent(
        self,
        track: TrackHandle,
        leaf: BindingHandle | FillHandle | AnnotationHandle,
    ) -> None:
        """Require that one issued leaf handle belongs to the supplied track handle."""
        owned_track = self._require_handle(track, TrackHandle)
        owned_leaf = self._require_handle(leaf, (BindingHandle, FillHandle, AnnotationHandle))
        if owned_leaf.track_token != owned_track.token:
            raise ProgramPolicyError("Leaf handle does not belong to the supplied track.")

    def _issue_report(self, report_id: str) -> ReportHandle:
        """Return one idempotently issued report handle for an exact identity."""
        token = self._token("report", report_id)
        return self._issue(
            ReportHandle(
                token=token,
                kind="report",
                builder_id=self._builder_id,
                report_id=report_id,
            )
        )

    def _issue_section(self, report: ReportHandle, section_id: str) -> SectionHandle:
        """Return one idempotently issued section handle for an exact identity."""
        token = self._token("section", report.report_id, section_id)
        return self._issue(
            SectionHandle(
                token=token,
                kind="section",
                builder_id=self._builder_id,
                report_token=report.token,
                section_id=section_id,
            )
        )

    def _issue_track(self, section: SectionHandle, track_id: str) -> TrackHandle:
        """Return one idempotently issued track handle for an exact local identity."""
        token = self._token("track", section.section_id, track_id)
        return self._issue(
            TrackHandle(
                token=token,
                kind="track",
                builder_id=self._builder_id,
                section_token=section.token,
                section_id=section.section_id,
                track_id=track_id,
            )
        )

    def _issue_binding(self, track: TrackHandle, binding_id: str) -> BindingHandle:
        """Return one idempotently issued binding handle for an exact identity."""
        token = self._token("binding", binding_id)
        return self._issue(
            BindingHandle(
                token=token,
                kind="binding",
                builder_id=self._builder_id,
                track_token=track.token,
                section_id=track.section_id,
                track_id=track.track_id,
                binding_id=binding_id,
            )
        )

    def _issue_fill(self, track: TrackHandle, fill_id: str) -> FillHandle:
        """Return one idempotently issued fill handle for an exact identity."""
        token = self._token("fill", fill_id)
        return self._issue(
            FillHandle(
                token=token,
                kind="fill",
                builder_id=self._builder_id,
                track_token=track.token,
                section_id=track.section_id,
                track_id=track.track_id,
                fill_id=fill_id,
            )
        )

    def _issue_annotation(self, track: TrackHandle, annotation_id: str) -> AnnotationHandle:
        """Return one idempotently issued annotation handle for an exact identity."""
        token = self._token("annotation", annotation_id)
        return self._issue(
            AnnotationHandle(
                token=token,
                kind="annotation",
                builder_id=self._builder_id,
                track_token=track.token,
                section_id=track.section_id,
                track_id=track.track_id,
                annotation_id=annotation_id,
            )
        )

    def _issue(self, handle: RuntimeHandle) -> RuntimeHandle:
        """Register one handle or return the equivalent idempotent issued value."""
        existing = self._issued.get(handle.token)
        if existing is None:
            self._issued[handle.token] = handle
            return handle
        if existing != handle:
            raise ProgramPolicyError("Issued handle token conflicts with another identity.")
        return existing

    def _require_handle(
        self,
        handle: object,
        expected: type[RuntimeHandle] | tuple[type[RuntimeHandle], ...],
    ) -> RuntimeHandle:
        """Validate runtime type, typed class, provenance, and issued identity order."""
        if not isinstance(handle, RuntimeHandle):
            raise ProgramTypeError("Expected a runtime handle.")
        if not isinstance(handle, expected):
            raise ProgramTypeError("Handle has an incompatible typed identity.")
        issued_handle_types = (
            ReportHandle,
            SourceHandle,
            SectionHandle,
            TrackHandle,
            BindingHandle,
            FillHandle,
            AnnotationHandle,
        )
        if not isinstance(handle, issued_handle_types):
            raise ProgramTypeError("Handle type is not issued by the identity builder.")
        if handle.builder_id != self._builder_id:
            raise ProgramNameError("Handle belongs to a different identity builder.")
        existing = self._issued.get(handle.token)
        if existing is None:
            raise ProgramNameError("Handle identity is not issued or reserved by this builder.")
        if existing != handle:
            raise ProgramPolicyError("Handle token conflicts with its issued identity.")
        return handle

    def _token(self, kind: str, *identity: str) -> str:
        """Build one opaque per-builder token from a typed ownership path."""
        return ":".join((self._builder_id, kind, *identity))


def _validate_handle_fields(*values: str) -> None:
    """Require immutable handle metadata to be non-empty public strings."""
    for value in values:
        if not isinstance(value, str) or not value or value.startswith("_"):
            raise ValueError("Handle metadata must use non-empty public strings.")


def _identity_text(value: object, label: str) -> str:
    """Validate one builder root identity without changing its canonical text."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProgramTypeError(f"{label.capitalize()} must be a non-empty trimmed string.")
    return value


def _builder_identity(builder_id: str | None) -> str:
    """Return an opaque runtime provenance token independent from canonical IDs."""
    if builder_id is None:
        return f"builder-{uuid4().hex}"
    return _identity_text(builder_id, "builder id")


__all__ = [
    "AnnotationHandle",
    "BindingHandle",
    "FillHandle",
    "HandleBuilder",
    "ReportHandle",
    "SourceHandle",
    "SectionHandle",
    "TrackHandle",
]
