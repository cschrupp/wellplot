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

"""Compile explicit Code Mode SDK calls into canonical authoring intent.

This module accumulates only validated :class:`AuthoringDocumentIntent`
fragments.  It does not inspect source data, simulate a document, reconcile,
persist, render, or call an application service.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar, cast

from pydantic import BaseModel, ValidationError

from ..model.authoring import (
    AnnotationSpec,
    AnnotationTextSpec,
    AuthoringCurveFillBaselineSpec,
    AuthoringCurveFillCrossoverSpec,
    AuthoringDataSource,
    AuthoringRasterColorbarSpec,
    AuthoringRasterSampleAxisSpec,
    AuthoringScale,
)
from ..model.intent import (
    AuthoringAnnotationIntent,
    AuthoringCurveBindingIntent,
    AuthoringDepthIntent,
    AuthoringDocumentIntent,
    AuthoringFillIntent,
    AuthoringHeaderFieldIntent,
    AuthoringOutputIntent,
    AuthoringPageIntent,
    AuthoringRasterBindingIntent,
    AuthoringRemarkIntent,
    AuthoringReportValueIntent,
    AuthoringSectionIntent,
    AuthoringServiceTitleIntent,
    AuthoringStyleIntent,
    AuthoringTailIntent,
    AuthoringTrackIntent,
)
from .builders import (
    AnnotationHandle,
    BindingHandle,
    FillHandle,
    HandleBuilder,
    ReportHandle,
    SectionHandle,
    SourceHandle,
    TrackHandle,
)
from .errors import ProgramNameError, ProgramPolicyError, ProgramTypeError
from .runtime import (
    HandleMethodRegistry,
    RootMethodRegistry,
    RuntimeEnvironment,
    RuntimeHandle,
    RuntimeValue,
)

_Model = TypeVar("_Model", bound=BaseModel)
_Handle = TypeVar("_Handle", bound=RuntimeHandle)
_TRACK_KINDS = frozenset({"normal", "reference", "array", "annotation"})
_FILL_KINDS = frozenset(
    {
        "between_curves",
        "between_instances",
        "to_lower_limit",
        "to_upper_limit",
        "baseline_split",
    }
)
_BETWEEN_FILL_KINDS = frozenset({"between_curves", "between_instances"})


class IntentBuilder:
    """Accumulate explicit SDK calls into one fresh canonical intent result.

    The builder owns desired-state fragments, not an ``AuthoringDocumentSpec``
    or a mutable clone of a report.  CM-13 remains the sole authority for
    canonical identifiers and typed-handle ownership.
    """

    def __init__(self, *, handles: HandleBuilder | None = None) -> None:
        """Create one isolated compiler with a CM-13 identity context."""
        self._handles = handles or HandleBuilder()
        self._sources: dict[str, tuple[SourceHandle, AuthoringDataSource]] = {}
        self._section_target_id: str | None = None
        self._report: ReportHandle | None = None
        self._report_fields: dict[str, str] = {}
        self._header_fields: dict[str, AuthoringHeaderFieldIntent] = {}
        self._service_titles: dict[str, AuthoringServiceTitleIntent] = {}
        self._detail_fields: dict[str, AuthoringHeaderFieldIntent] = {}
        self._remarks: dict[str, AuthoringRemarkIntent] = {}
        self._page: AuthoringPageIntent | None = None
        self._depth: AuthoringDepthIntent | None = None
        self._output: AuthoringOutputIntent | None = None
        self._tail: AuthoringTailIntent | None = None
        self._sections: dict[str, AuthoringSectionIntent] = {}
        self._section_order: list[str] = []
        self._tracks: dict[str, TrackHandle] = {}
        self._track_locations: dict[str, tuple[str, int]] = {}
        self._bindings: dict[str, BindingHandle] = {}
        self._fills: dict[str, FillHandle] = {}
        self._annotations: dict[str, AnnotationHandle] = {}

    @property
    def handles(self) -> HandleBuilder:
        """Expose the CM-13 identity authority used by this builder."""
        return self._handles

    def report(
        self,
        *,
        title: str | None = None,
        subtitle: str | None = None,
    ) -> ReportHandle:
        """Start one report-wide desired-state fragment.

        Report-wide settings are added through explicit builder methods below;
        fluent report-receiver syntax remains intentionally deferred.
        """
        if self._report is not None:
            raise ProgramPolicyError("A program may create only one report intent.")

        fields = _non_null_fields(title=title, subtitle=subtitle)
        _validated(AuthoringDocumentIntent, fields, "Report desired state")
        self._report = self._handles.create_report()
        self._report_fields = fields
        return self._report

    def register_source(
        self,
        candidate_id: str,
        data_source: AuthoringDataSource,
    ) -> SourceHandle:
        """Register one host-bounded source without exposing its path to programs."""
        source = _validated(
            AuthoringDataSource,
            data_source.model_dump(mode="python"),
            "Source association",
        )
        handle = self._handles.create_source(candidate_id)
        existing = self._sources.get(handle.candidate_id)
        if existing is not None and existing[1] != source:
            raise ProgramPolicyError(
                f"Source candidate '{handle.candidate_id}' has conflicting metadata."
            )
        self._sources[handle.candidate_id] = (handle, source)
        return handle

    def source(self, candidate_id: str) -> SourceHandle:
        """Return one exact host-registered source candidate handle."""
        handle_and_source = self._sources.get(candidate_id)
        if handle_and_source is None:
            raise ProgramNameError(f"Unknown source candidate '{candidate_id}'.")
        return handle_and_source[0]

    def register_section_target(self, section_id: str) -> None:
        """Bind one host-resolved section identity for target-section calls."""
        if self._section_target_id is not None:
            raise ProgramPolicyError("An intent builder can own only one section target.")
        if not isinstance(section_id, str) or not section_id.strip():
            raise ProgramTypeError("A section target requires a non-empty section ID.")
        self._section_target_id = section_id.strip()

    def set_header_field(
        self,
        report: ReportHandle,
        *,
        key: str,
        value: AuthoringReportValueIntent,
        label: str | None = None,
    ) -> None:
        """Set one semantic general-header field for the owned report."""
        self._require_report(report)
        field = _validated(
            AuthoringHeaderFieldIntent,
            _non_null_fields(slot_id=key, key=key, value=value, label=label),
            "Header field desired state",
        )
        self._header_fields[key] = field

    def set_service_title(
        self,
        report: ReportHandle,
        *,
        slot_id: str,
        value: AuthoringReportValueIntent,
        font_size: float | None = None,
        auto_adjust: bool | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
        alignment: str | None = None,
    ) -> None:
        """Set one stable service-title slot for the owned report."""
        self._require_report(report)
        title = _validated(
            AuthoringServiceTitleIntent,
            _non_null_fields(
                slot_id=slot_id,
                value=value,
                font_size=font_size,
                auto_adjust=auto_adjust,
                bold=bold,
                italic=italic,
                alignment=alignment,
            ),
            "Service title desired state",
        )
        self._service_titles[slot_id] = title

    def set_detail_field(
        self,
        report: ReportHandle,
        *,
        key: str,
        value: AuthoringReportValueIntent,
        label: str | None = None,
    ) -> None:
        """Set one semantic detail-header field for the owned report."""
        self._require_report(report)
        field = _validated(
            AuthoringHeaderFieldIntent,
            _non_null_fields(slot_id=key, key=key, value=value, label=label),
            "Detail field desired state",
        )
        self._detail_fields[key] = field

    def add_remark(
        self,
        report: ReportHandle,
        *,
        remark_id: str,
        title: str | None = None,
        text: str | None = None,
        lines: list[str] | None = None,
        alignment: str | None = None,
        font_size: float | None = None,
        title_font_size: float | None = None,
        border: bool | None = None,
    ) -> None:
        """Add one identified report remark without replacing another remark."""
        self._require_report(report)
        if remark_id in self._remarks:
            raise ProgramNameError(f"Remark id '{remark_id}' is already owned by this builder.")
        remark = _validated(
            AuthoringRemarkIntent,
            _non_null_fields(
                remark_id=remark_id,
                title=title,
                text=text,
                lines=lines,
                alignment=alignment,
                font_size=font_size,
                title_font_size=title_font_size,
                border=border,
            ),
            "Remark desired state",
        )
        self._remarks[remark_id] = remark

    def update_page(self, report: ReportHandle, *, page: AuthoringPageIntent) -> None:
        """Set one explicit canonical page patch for the owned report."""
        self._require_report(report)
        self._page = _copy_intent(page, AuthoringPageIntent, "Page desired state")

    def update_depth(self, report: ReportHandle, *, depth: AuthoringDepthIntent) -> None:
        """Set one explicit canonical depth patch for the owned report."""
        self._require_report(report)
        self._depth = _copy_intent(depth, AuthoringDepthIntent, "Depth desired state")

    def update_output(self, report: ReportHandle, *, output: AuthoringOutputIntent) -> None:
        """Set one explicit canonical output patch for the owned report."""
        self._require_report(report)
        self._output = _copy_intent(output, AuthoringOutputIntent, "Output desired state")

    def update_tail(self, report: ReportHandle, *, enabled: bool | None = None) -> None:
        """Set minimal report-tail enablement for the owned report."""
        self._require_report(report)
        self._tail = _validated(
            AuthoringTailIntent,
            _non_null_fields(enabled=enabled),
            "Tail desired state",
        )

    def add_section(
        self,
        report: ReportHandle,
        *,
        id_hint: str | None = None,
        title: str,
        subtitle: str | None = None,
        depth_minimum: float | None = None,
        depth_maximum: float | None = None,
        source: SourceHandle | None = None,
    ) -> SectionHandle:
        """Create one titled section with an optional explicit depth range."""
        owned_report = self._require_report(report)
        depth_range = _optional_pair(
            depth_minimum,
            depth_maximum,
            label="Section depth range",
        )
        data_source = self._source_data(source) if source is not None else None
        section = self._handles.create_section(owned_report, id_hint)
        self._handles.validate_section_parent(owned_report, section)
        fragment = _validated(
            AuthoringSectionIntent,
            _non_null_fields(
                section_id=section.section_id,
                title=title,
                subtitle=subtitle,
                depth_range=depth_range,
                data_source=data_source,
            ),
            "Section desired state",
        )
        self._sections[section.token] = fragment
        self._section_order.append(section.token)
        return section

    def select_section(self, report: ReportHandle, *, section_id: str) -> SectionHandle:
        """Adopt one host-resolved section identity without searching a document."""
        owned_report = self._require_report(report)
        section = self._handles.adopt_section(owned_report, section_id)
        self._handles.validate_section_parent(owned_report, section)
        if section.token not in self._sections:
            self._sections[section.token] = AuthoringSectionIntent(section_id=section.section_id)
            self._section_order.append(section.token)
        return section

    def update_section(
        self,
        section: SectionHandle,
        *,
        title: str | None = None,
        subtitle: str | None = None,
        depth_minimum: float | None = None,
        depth_maximum: float | None = None,
    ) -> None:
        """Apply one sparse update to an adopted section without changing identity."""
        owned_section = self._require_section(section)
        depth_range = _optional_pair(
            depth_minimum,
            depth_maximum,
            label="Section depth range",
        )
        patch = _validated(
            AuthoringSectionIntent,
            _non_null_fields(
                section_id=owned_section.section_id,
                title=title,
                subtitle=subtitle,
                depth_range=depth_range,
            ),
            "Section desired state",
        )
        if not patch.supplied_fields().difference({"section_id"}):
            raise ProgramPolicyError("Section update requires at least one mutable field.")
        self._sections[owned_section.token] = _merge_intent(
            self._sections[owned_section.token],
            patch,
            AuthoringSectionIntent,
            "Section desired state",
        )

    def add_track(
        self,
        section: SectionHandle,
        *,
        id_hint: str | None = None,
        kind: str,
        title: str,
        width_mm: float,
        scale_minimum: float | None = None,
        scale_maximum: float | None = None,
        scale_kind: str = "linear",
        reverse: bool = False,
    ) -> TrackHandle:
        """Create one typed track with a narrow optional horizontal scale."""
        owned_section = self._require_section(section)
        if kind not in _TRACK_KINDS:
            raise ProgramTypeError(f"Unsupported track kind '{kind}'.")
        scale = _optional_scale(
            scale_minimum,
            scale_maximum,
            kind=scale_kind,
            reverse=reverse,
            label="Track scale",
        )
        track = self._handles.create_track(owned_section, id_hint)
        self._handles.validate_track_parent(owned_section, track)
        fragment = _validated(
            AuthoringTrackIntent,
            _non_null_fields(
                track_id=track.track_id,
                section_id=track.section_id,
                kind=kind,
                title=title,
                width_mm=width_mm,
                x_scale=scale,
            ),
            "Track desired state",
        )
        section_fragment = self._sections[owned_section.token]
        tracks = list(section_fragment.tracks or [])
        tracks.append(fragment)
        self._sections[owned_section.token] = _replace_section_tracks(section_fragment, tracks)
        self._tracks[track.token] = track
        self._track_locations[track.token] = (owned_section.token, len(tracks) - 1)
        return track

    def select_track(self, section: SectionHandle, *, track_id: str) -> TrackHandle:
        """Adopt one host-resolved track identity under one selected section."""
        owned_section = self._require_section(section)
        track = self._handles.adopt_track(owned_section, track_id)
        self._handles.validate_track_parent(owned_section, track)
        if track.token not in self._tracks:
            section_fragment = self._sections[owned_section.token]
            tracks = list(section_fragment.tracks or [])
            tracks.append(
                AuthoringTrackIntent(
                    track_id=track.track_id,
                    section_id=track.section_id,
                )
            )
            self._sections[owned_section.token] = _replace_section_tracks(
                section_fragment,
                tracks,
            )
            self._tracks[track.token] = track
            self._track_locations[track.token] = (owned_section.token, len(tracks) - 1)
        return track

    def update_track(
        self,
        track: TrackHandle,
        *,
        kind: str | None = None,
        title: str | None = None,
        width_mm: float | None = None,
        scale_minimum: float | None = None,
        scale_maximum: float | None = None,
        scale_kind: str = "linear",
        reverse: bool = False,
    ) -> None:
        """Apply one sparse update without moving or renaming an adopted track."""
        owned_track = self._require_track(track)
        if kind is not None and kind not in _TRACK_KINDS:
            raise ProgramTypeError(f"Unsupported track kind '{kind}'.")
        scale = _optional_scale(
            scale_minimum,
            scale_maximum,
            kind=scale_kind,
            reverse=reverse,
            label="Track scale",
        )
        patch = _validated(
            AuthoringTrackIntent,
            _non_null_fields(
                track_id=owned_track.track_id,
                section_id=owned_track.section_id,
                kind=kind,
                title=title,
                width_mm=width_mm,
                x_scale=scale,
            ),
            "Track desired state",
        )
        if not patch.supplied_fields().difference({"track_id", "section_id"}):
            raise ProgramPolicyError("Track update requires at least one mutable field.")
        section, tracks, index = self._track_state(owned_track)
        tracks[index] = _merge_intent(
            tracks[index],
            patch,
            AuthoringTrackIntent,
            "Track desired state",
        )
        self._sections[section] = _replace_section_tracks(self._sections[section], tracks)

    def add_curve(
        self,
        track: TrackHandle,
        *,
        channel: str,
        id_hint: str | None = None,
        label: str | None = None,
        scale_minimum: float | None = None,
        scale_maximum: float | None = None,
        scale_kind: str = "linear",
        reverse: bool = False,
        scale_unit: str | None = None,
        color: str | None = None,
        line_style: str | None = None,
        line_width: float | None = None,
    ) -> BindingHandle:
        """Add one scalar curve binding with explicit scale and line options."""
        owned_track = self._require_track(track)
        binding = self._handles.create_binding(owned_track, channel=channel, id_hint=id_hint)
        self._handles.validate_leaf_parent(owned_track, binding)
        fragment = _validated(
            AuthoringCurveBindingIntent,
            _non_null_fields(
                kind="curve",
                binding_id=binding.binding_id,
                section_id=owned_track.section_id,
                track_id=owned_track.track_id,
                channel=channel,
                label=label,
                scale=_optional_scale(
                    scale_minimum,
                    scale_maximum,
                    kind=scale_kind,
                    reverse=reverse,
                    unit=scale_unit,
                    label="Curve scale",
                ),
                style=_optional_style(
                    color=color,
                    line_style=line_style,
                    line_width=line_width,
                ),
            ),
            "Curve binding desired state",
        )
        self._append_track_binding(owned_track, fragment)
        self._bindings[binding.token] = binding
        return binding

    def add_raster(
        self,
        track: TrackHandle,
        *,
        channel: str,
        id_hint: str | None = None,
        label: str | None = None,
        profile: str | None = None,
        normalization: str | None = None,
        color_minimum: float | None = None,
        color_maximum: float | None = None,
        colormap: str | None = None,
        alpha: float | None = None,
        colorbar: AuthoringRasterColorbarSpec | None = None,
        sample_axis: AuthoringRasterSampleAxisSpec | None = None,
    ) -> BindingHandle:
        """Add one raster binding with explicit display and amplitude options."""
        owned_track = self._require_track(track)
        color_limits = _optional_pair(
            color_minimum,
            color_maximum,
            label="Raster color limits",
        )
        binding = self._handles.create_binding(owned_track, channel=channel, id_hint=id_hint)
        self._handles.validate_leaf_parent(owned_track, binding)
        fragment = _validated(
            AuthoringRasterBindingIntent,
            _non_null_fields(
                kind="raster",
                binding_id=binding.binding_id,
                section_id=owned_track.section_id,
                track_id=owned_track.track_id,
                channel=channel,
                label=label,
                profile=profile,
                normalization=normalization,
                color_limits=color_limits,
                colorbar=colorbar,
                sample_axis=sample_axis,
                style=_optional_style(colormap=colormap, alpha=alpha),
            ),
            "Raster binding desired state",
        )
        self._append_track_binding(owned_track, fragment)
        self._bindings[binding.token] = binding
        return binding

    def select_curve(self, track: TrackHandle, *, binding_id: str) -> BindingHandle:
        """Adopt one host-resolved scalar binding identity under a track."""
        return self._select_binding(track, binding_id=binding_id, kind="curve")

    def select_raster(self, track: TrackHandle, *, binding_id: str) -> BindingHandle:
        """Adopt one host-resolved raster binding identity under a track."""
        return self._select_binding(track, binding_id=binding_id, kind="raster")

    def update_curve(
        self,
        track: TrackHandle,
        binding: BindingHandle,
        *,
        channel: str | None = None,
        label: str | None = None,
        scale_minimum: float | None = None,
        scale_maximum: float | None = None,
        scale_kind: str = "linear",
        reverse: bool = False,
        scale_unit: str | None = None,
        color: str | None = None,
        line_style: str | None = None,
        line_width: float | None = None,
    ) -> None:
        """Apply a sparse update to one adopted curve binding."""
        owned_track = self._require_track(track)
        owned_binding = self._require_binding(owned_track, binding)
        patch = _validated(
            AuthoringCurveBindingIntent,
            _non_null_fields(
                kind="curve",
                binding_id=owned_binding.binding_id,
                section_id=owned_track.section_id,
                track_id=owned_track.track_id,
                channel=channel,
                label=label,
                scale=_optional_scale(
                    scale_minimum,
                    scale_maximum,
                    kind=scale_kind,
                    reverse=reverse,
                    unit=scale_unit,
                    label="Curve scale",
                ),
                style=_optional_style(
                    color=color,
                    line_style=line_style,
                    line_width=line_width,
                ),
            ),
            "Curve binding desired state",
        )
        self._merge_track_binding(owned_track, patch)

    def update_raster(
        self,
        track: TrackHandle,
        binding: BindingHandle,
        *,
        channel: str | None = None,
        label: str | None = None,
        profile: str | None = None,
        normalization: str | None = None,
        color_minimum: float | None = None,
        color_maximum: float | None = None,
        colormap: str | None = None,
        alpha: float | None = None,
        colorbar: AuthoringRasterColorbarSpec | None = None,
        sample_axis: AuthoringRasterSampleAxisSpec | None = None,
    ) -> None:
        """Apply a sparse update to one adopted raster binding."""
        owned_track = self._require_track(track)
        owned_binding = self._require_binding(owned_track, binding)
        patch = _validated(
            AuthoringRasterBindingIntent,
            _non_null_fields(
                kind="raster",
                binding_id=owned_binding.binding_id,
                section_id=owned_track.section_id,
                track_id=owned_track.track_id,
                channel=channel,
                label=label,
                profile=profile,
                normalization=normalization,
                color_limits=_optional_pair(
                    color_minimum,
                    color_maximum,
                    label="Raster color limits",
                ),
                colorbar=colorbar,
                sample_axis=sample_axis,
                style=_optional_style(colormap=colormap, alpha=alpha),
            ),
            "Raster binding desired state",
        )
        self._merge_track_binding(owned_track, patch)

    def add_fill(
        self,
        track: TrackHandle,
        *,
        kind: str,
        binding: BindingHandle,
        other_binding: BindingHandle | None = None,
        id_hint: str | None = None,
        label: str | None = None,
        color: str | None = None,
        alpha: float | None = None,
        baseline: AuthoringCurveFillBaselineSpec | None = None,
        crossover: AuthoringCurveFillCrossoverSpec | None = None,
    ) -> FillHandle:
        """Add one explicit curve-fill relation between bindings on one track."""
        owned_track = self._require_track(track)
        if kind not in _FILL_KINDS:
            raise ProgramTypeError(f"Unsupported fill kind '{kind}'.")
        owned_binding = self._require_binding(owned_track, binding)
        owned_other_binding = None
        if other_binding is not None:
            owned_other_binding = self._require_binding(owned_track, other_binding)
        if kind in _BETWEEN_FILL_KINDS and owned_other_binding is None:
            raise ProgramTypeError(f"Fill kind '{kind}' requires other_binding.")
        if kind not in _BETWEEN_FILL_KINDS and owned_other_binding is not None:
            raise ProgramTypeError(f"Fill kind '{kind}' does not accept other_binding.")

        fill = self._handles.create_fill(owned_track, id_hint)
        self._handles.validate_leaf_parent(owned_track, fill)
        fragment = _validated(
            AuthoringFillIntent,
            _non_null_fields(
                fill_id=fill.fill_id,
                section_id=owned_track.section_id,
                track_id=owned_track.track_id,
                kind=kind,
                binding_id=owned_binding.binding_id,
                other_binding_id=(
                    owned_other_binding.binding_id if owned_other_binding is not None else None
                ),
                label=label,
                color=color,
                alpha=alpha,
                baseline=baseline,
                crossover=crossover,
            ),
            "Fill desired state",
        )
        self._append_track_fill(owned_track, fragment)
        self._fills[fill.token] = fill
        return fill

    def reference_binding(self, track: TrackHandle, *, binding_id: str) -> BindingHandle:
        """Adopt a binding identity for a relation without emitting a binding patch."""
        owned_track = self._require_track(track)
        binding = self._handles.adopt_binding(owned_track, binding_id)
        self._handles.validate_leaf_parent(owned_track, binding)
        self._bindings[binding.token] = binding
        return binding

    def select_fill(self, track: TrackHandle, *, fill_id: str) -> FillHandle:
        """Adopt one host-resolved fill identity under a normal track."""
        owned_track = self._require_track(track)
        fill = self._handles.adopt_fill(owned_track, fill_id)
        self._handles.validate_leaf_parent(owned_track, fill)
        if fill.token not in self._fills:
            self._append_track_fill(
                owned_track,
                AuthoringFillIntent(
                    fill_id=fill.fill_id,
                    section_id=owned_track.section_id,
                    track_id=owned_track.track_id,
                ),
            )
            self._fills[fill.token] = fill
        return fill

    def update_fill(
        self,
        track: TrackHandle,
        fill: FillHandle,
        *,
        kind: str | None = None,
        binding: BindingHandle | None = None,
        other_binding: BindingHandle | None = None,
        label: str | None = None,
        color: str | None = None,
        alpha: float | None = None,
        baseline: AuthoringCurveFillBaselineSpec | None = None,
        crossover: AuthoringCurveFillCrossoverSpec | None = None,
    ) -> None:
        """Apply an outer sparse fill update with atomic nested replacements."""
        owned_track = self._require_track(track)
        owned_fill = self._require_fill(owned_track, fill)
        owned_binding = self._require_binding(owned_track, binding) if binding is not None else None
        owned_other_binding = (
            self._require_binding(owned_track, other_binding) if other_binding is not None else None
        )
        patch = _validated(
            AuthoringFillIntent,
            _non_null_fields(
                fill_id=owned_fill.fill_id,
                section_id=owned_track.section_id,
                track_id=owned_track.track_id,
                kind=kind,
                binding_id=(owned_binding.binding_id if owned_binding is not None else None),
                other_binding_id=(
                    owned_other_binding.binding_id if owned_other_binding is not None else None
                ),
                label=label,
                color=color,
                alpha=alpha,
                baseline=baseline,
                crossover=crossover,
            ),
            "Fill desired state",
        )
        self._merge_track_fill(owned_track, patch)

    def add_annotation(
        self,
        track: TrackHandle,
        *,
        text: str,
        depth: float,
        id_hint: str | None = None,
        color: str | None = None,
        font_size: float | None = None,
    ) -> AnnotationHandle:
        """Add one narrow text annotation anchored at a depth value."""
        annotation_spec = _validated(
            AnnotationTextSpec,
            _non_null_fields(
                kind="text",
                annotation_id=id_hint or "annotation",
                text=text,
                depth=depth,
                color=color,
                font_size=font_size,
            ),
            "Text annotation desired state",
        )
        return self.add_typed_annotation(track, annotation=annotation_spec, id_hint=id_hint)

    def add_typed_annotation(
        self,
        track: TrackHandle,
        *,
        annotation: AnnotationSpec,
        id_hint: str | None = None,
    ) -> AnnotationHandle:
        """Add one complete typed annotation with a host-owned identity."""
        owned_track = self._require_track(track)
        typed_annotation = _replace_annotation_id(annotation, "pending")
        created = self._handles.create_annotation(owned_track, id_hint)
        self._handles.validate_leaf_parent(owned_track, created)
        typed_annotation = _replace_annotation_id(typed_annotation, created.annotation_id)
        fragment = _validated(
            AuthoringAnnotationIntent,
            {
                "annotation_id": created.annotation_id,
                "section_id": owned_track.section_id,
                "track_id": owned_track.track_id,
                "annotation": typed_annotation,
            },
            "Annotation desired state",
        )
        self._append_track_annotation(owned_track, fragment)
        self._annotations[created.token] = created
        return created

    def select_annotation(self, track: TrackHandle, *, annotation_id: str) -> AnnotationHandle:
        """Adopt one host-resolved annotation identity under an annotation track."""
        owned_track = self._require_track(track)
        annotation = self._handles.adopt_annotation(owned_track, annotation_id)
        self._handles.validate_leaf_parent(owned_track, annotation)
        if annotation.token not in self._annotations:
            self._append_track_annotation(
                owned_track,
                AuthoringAnnotationIntent(
                    annotation_id=annotation.annotation_id,
                    section_id=owned_track.section_id,
                    track_id=owned_track.track_id,
                ),
            )
            self._annotations[annotation.token] = annotation
        return annotation

    def update_typed_annotation(
        self,
        track: TrackHandle,
        annotation: AnnotationHandle,
        *,
        payload: AnnotationSpec,
    ) -> None:
        """Replace one adopted annotation payload without changing its identity."""
        owned_track = self._require_track(track)
        owned_annotation = self._require_annotation(owned_track, annotation)
        typed_payload = _replace_annotation_id(payload, owned_annotation.annotation_id)
        patch = _validated(
            AuthoringAnnotationIntent,
            {
                "annotation_id": owned_annotation.annotation_id,
                "section_id": owned_track.section_id,
                "track_id": owned_track.track_id,
                "annotation": typed_payload,
            },
            "Annotation desired state",
        )
        self._merge_track_annotation(owned_track, patch)

    def intent(self) -> AuthoringDocumentIntent:
        """Return a fresh validated canonical intent in deterministic call order."""
        fields: dict[str, object] = dict(self._report_fields)
        header_fields = _report_header_fields(
            self._header_fields,
            self._service_titles,
            self._detail_fields,
        )
        if header_fields:
            fields["header"] = header_fields
        if self._remarks:
            fields["remarks"] = list(self._remarks.values())
        if self._page is not None:
            fields["page"] = self._page
        if self._depth is not None:
            fields["depth"] = self._depth
        if self._output is not None:
            fields["output"] = self._output
        if self._tail is not None:
            fields["tail"] = self._tail
        if self._section_order:
            fields["sections"] = [
                self._sections[token].model_dump(exclude_unset=True)
                for token in self._section_order
            ]
        return _validated(AuthoringDocumentIntent, fields, "Compiled program intent")

    def runtime_environment(self) -> RuntimeEnvironment:
        """Return the explicit CM-12 registry for this builder's narrow SDK."""
        return RuntimeEnvironment(
            root_methods=RootMethodRegistry(
                methods={
                    "report": self._runtime_report,
                    "source": self._runtime_source,
                    "header_field": self._runtime_header_field,
                    "service_title": self._runtime_service_title,
                    "detail_field": self._runtime_detail_field,
                    "remark": self._runtime_remark,
                    "page": self._runtime_page,
                    "depth": self._runtime_depth,
                    "output": self._runtime_output,
                    "tail": self._runtime_tail,
                    "section": self._runtime_section,
                    "target_section": self._runtime_target_section,
                    "update_section": self._runtime_update_section,
                    "track": self._runtime_track,
                    "curve": self._runtime_curve,
                    "raster": self._runtime_raster,
                    "fill": self._runtime_fill,
                    "annotation": self._runtime_annotation,
                }
            ),
            handle_methods=HandleMethodRegistry(methods={}),
        )

    def _require_report(self, report: ReportHandle) -> ReportHandle:
        """Require the builder's one issued report handle before child creation."""
        owned_report = self._handles.validate_report(report)
        if owned_report != self._report:
            raise ProgramNameError("Report handle is not owned by this intent builder.")
        return owned_report

    def _require_source(self, source: SourceHandle) -> SourceHandle:
        """Require one source handle issued by this builder."""
        owned_source = self._handles.validate_source(source)
        if owned_source.candidate_id not in self._sources:
            raise ProgramNameError(
                f"Source candidate '{owned_source.candidate_id}' is not registered."
            )
        return owned_source

    def _source_data(self, source: SourceHandle) -> AuthoringDataSource:
        """Resolve an owned opaque source handle to private canonical metadata."""
        owned_source = self._require_source(source)
        return self._sources[owned_source.candidate_id][1]

    def _require_section(self, section: SectionHandle) -> SectionHandle:
        """Require an issued section that already has an accumulated fragment."""
        owned_section = self._handles.validate_section(section)
        if owned_section.token not in self._sections:
            raise ProgramNameError("Section handle is not owned by this intent builder.")
        return owned_section

    def _require_track(self, track: TrackHandle) -> TrackHandle:
        """Require an issued track that already has an accumulated fragment."""
        owned_track = self._handles.validate_track(track)
        if owned_track.token not in self._tracks:
            raise ProgramNameError("Track handle is not owned by this intent builder.")
        return owned_track

    def _require_binding(self, track: TrackHandle, binding: BindingHandle) -> BindingHandle:
        """Require one accumulated binding under the exact supplied parent track."""
        owned_binding = self._handles.validate_binding(binding)
        self._handles.validate_leaf_parent(track, owned_binding)
        if owned_binding.token not in self._bindings:
            raise ProgramNameError("Binding handle is not owned by this intent builder.")
        return owned_binding

    def _require_fill(self, track: TrackHandle, fill: FillHandle) -> FillHandle:
        """Require one accumulated fill under the exact supplied parent track."""
        owned_fill = self._handles.validate_fill(fill)
        self._handles.validate_leaf_parent(track, owned_fill)
        if owned_fill.token not in self._fills:
            raise ProgramNameError("Fill handle is not owned by this intent builder.")
        return owned_fill

    def _require_annotation(
        self,
        track: TrackHandle,
        annotation: AnnotationHandle,
    ) -> AnnotationHandle:
        """Require one accumulated annotation under the exact supplied parent track."""
        owned_annotation = self._handles.validate_annotation(annotation)
        self._handles.validate_leaf_parent(track, owned_annotation)
        if owned_annotation.token not in self._annotations:
            raise ProgramNameError("Annotation handle is not owned by this intent builder.")
        return owned_annotation

    def _append_track_binding(
        self,
        track: TrackHandle,
        binding: AuthoringCurveBindingIntent | AuthoringRasterBindingIntent,
    ) -> None:
        """Append one canonical binding fragment without mutating a document model."""
        section, tracks, index = self._track_state(track)
        current = tracks[index]
        bindings = list(current.bindings or [])
        bindings.append(binding)
        tracks[index] = _replace_track_field(current, "bindings", bindings)
        self._sections[section] = _replace_section_tracks(self._sections[section], tracks)

    def _select_binding(
        self,
        track: TrackHandle,
        *,
        binding_id: str,
        kind: str,
    ) -> BindingHandle:
        """Adopt one exact binding identity with a typed partial fragment."""
        owned_track = self._require_track(track)
        binding = self._handles.adopt_binding(owned_track, binding_id)
        self._handles.validate_leaf_parent(owned_track, binding)
        if binding.token not in self._bindings:
            model_type = (
                AuthoringCurveBindingIntent if kind == "curve" else AuthoringRasterBindingIntent
            )
            fragment = _validated(
                model_type,
                _non_null_fields(
                    kind=kind,
                    binding_id=binding.binding_id,
                    section_id=owned_track.section_id,
                    track_id=owned_track.track_id,
                ),
                "Binding desired state",
            )
            self._append_track_binding(owned_track, fragment)
            self._bindings[binding.token] = binding
        return binding

    def _merge_track_binding(
        self,
        track: TrackHandle,
        patch: AuthoringCurveBindingIntent | AuthoringRasterBindingIntent,
    ) -> None:
        """Merge one binding patch into the exact binding identity on a track."""
        section, tracks, index = self._track_state(track)
        current = tracks[index]
        bindings = list(current.bindings or [])
        for binding_index, existing in enumerate(bindings):
            if existing.binding_id != patch.binding_id:
                continue
            if existing.kind != patch.kind:
                raise ProgramPolicyError(
                    f"Binding '{patch.binding_id}' kind does not match the selected capability."
                )
            bindings[binding_index] = _merge_intent(
                existing,
                patch,
                type(existing),
                "Binding desired state",
            )
            tracks[index] = _replace_track_field(current, "bindings", bindings)
            self._sections[section] = _replace_section_tracks(self._sections[section], tracks)
            return
        raise ProgramNameError(f"Binding '{patch.binding_id}' is not owned by the selected track.")

    def _append_track_fill(self, track: TrackHandle, fill: AuthoringFillIntent) -> None:
        """Append one canonical fill fragment without applying it to a report."""
        section, tracks, index = self._track_state(track)
        current = tracks[index]
        fills = list(current.fills or [])
        fills.append(fill)
        tracks[index] = _replace_track_field(current, "fills", fills)
        self._sections[section] = _replace_section_tracks(self._sections[section], tracks)

    def _merge_track_fill(self, track: TrackHandle, patch: AuthoringFillIntent) -> None:
        """Merge one sparse outer fill patch with atomic nested field replacement."""
        section, tracks, index = self._track_state(track)
        current = tracks[index]
        fills = list(current.fills or [])
        for fill_index, existing in enumerate(fills):
            if existing.fill_id != patch.fill_id:
                continue
            fills[fill_index] = _merge_intent(
                existing,
                patch,
                AuthoringFillIntent,
                "Fill desired state",
            )
            tracks[index] = _replace_track_field(current, "fills", fills)
            self._sections[section] = _replace_section_tracks(self._sections[section], tracks)
            return
        raise ProgramNameError(f"Fill '{patch.fill_id}' is not owned by the selected track.")

    def _append_track_annotation(
        self,
        track: TrackHandle,
        annotation: AuthoringAnnotationIntent,
    ) -> None:
        """Append one canonical annotation fragment without applying it to a report."""
        section, tracks, index = self._track_state(track)
        current = tracks[index]
        annotations = list(current.annotations or [])
        annotations.append(annotation)
        tracks[index] = _replace_track_field(current, "annotations", annotations)
        self._sections[section] = _replace_section_tracks(self._sections[section], tracks)

    def _merge_track_annotation(
        self,
        track: TrackHandle,
        patch: AuthoringAnnotationIntent,
    ) -> None:
        """Replace one complete typed annotation payload at a stable identity."""
        section, tracks, index = self._track_state(track)
        current = tracks[index]
        annotations = list(current.annotations or [])
        for annotation_index, existing in enumerate(annotations):
            if existing.annotation_id != patch.annotation_id:
                continue
            annotations[annotation_index] = patch
            tracks[index] = _replace_track_field(current, "annotations", annotations)
            self._sections[section] = _replace_section_tracks(self._sections[section], tracks)
            return
        raise ProgramNameError(
            f"Annotation '{patch.annotation_id}' is not owned by the selected track."
        )

    def _track_state(
        self,
        track: TrackHandle,
    ) -> tuple[str, list[AuthoringTrackIntent], int]:
        """Return a copied parent-track collection for one validated track handle."""
        section, index = self._track_locations[track.token]
        tracks = list(self._sections[section].tracks or [])
        return section, tracks, index

    def _runtime_report(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch the root report SDK call through the explicit registry."""
        _require_no_args(args, "wp.report")
        values = _runtime_kwargs(kwargs, "wp.report", {"title", "subtitle"})
        return self.report(
            title=_optional_runtime_text(values, "title"),
            subtitle=_optional_runtime_text(values, "subtitle"),
        )

    def _runtime_header_field(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch one primitive-valued semantic header field."""
        report = _runtime_handle_arg(args, "wp.header_field", ReportHandle)
        values = _runtime_kwargs(
            kwargs,
            "wp.header_field",
            {"key", "value", "unit", "label"},
        )
        return self._set_runtime_header_field(report, values, detail=False)

    def _runtime_service_title(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch one primitive-valued service-title slot."""
        report = _runtime_handle_arg(args, "wp.service_title", ReportHandle)
        values = _runtime_kwargs(
            kwargs,
            "wp.service_title",
            {
                "slot_id",
                "value",
                "unit",
                "font_size",
                "auto_adjust",
                "bold",
                "italic",
                "alignment",
            },
        )
        self.set_service_title(
            report,
            slot_id=_required_runtime_text(values, "slot_id", "wp.service_title"),
            value=_runtime_report_value(values, "wp.service_title"),
            font_size=_optional_runtime_number(values, "font_size"),
            auto_adjust=_optional_runtime_bool_or_none(values, "auto_adjust"),
            bold=_optional_runtime_bool_or_none(values, "bold"),
            italic=_optional_runtime_bool_or_none(values, "italic"),
            alignment=_optional_runtime_text(values, "alignment"),
        )
        return None

    def _runtime_detail_field(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch one primitive-valued detail-header field."""
        report = _runtime_handle_arg(args, "wp.detail_field", ReportHandle)
        values = _runtime_kwargs(
            kwargs,
            "wp.detail_field",
            {"key", "value", "unit", "label"},
        )
        return self._set_runtime_header_field(report, values, detail=True)

    def _set_runtime_header_field(
        self,
        report: ReportHandle,
        values: Mapping[str, RuntimeValue],
        *,
        detail: bool,
    ) -> RuntimeValue:
        """Set one header/detail field after converting primitive values."""
        name = "wp.detail_field" if detail else "wp.header_field"
        key = _required_runtime_text(values, "key", name)
        value = _runtime_report_value(values, name)
        setter = self.set_detail_field if detail else self.set_header_field
        setter(
            report,
            key=key,
            value=value,
            label=_optional_runtime_text(values, "label"),
        )
        return None

    def _runtime_remark(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch one primitive-valued report remark."""
        report = _runtime_handle_arg(args, "wp.remark", ReportHandle)
        values = _runtime_kwargs(
            kwargs,
            "wp.remark",
            {
                "remark_id",
                "title",
                "text",
                "alignment",
                "font_size",
                "title_font_size",
                "border",
            },
        )
        self.add_remark(
            report,
            remark_id=_required_runtime_text(values, "remark_id", "wp.remark"),
            title=_optional_runtime_text(values, "title"),
            text=_required_runtime_text(values, "text", "wp.remark"),
            alignment=_optional_runtime_text(values, "alignment"),
            font_size=_optional_runtime_number(values, "font_size"),
            title_font_size=_optional_runtime_number(values, "title_font_size"),
            border=_optional_runtime_bool_or_none(values, "border"),
        )
        return None

    def _runtime_page(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch primitive page settings into one canonical page patch."""
        report = _runtime_handle_arg(args, "wp.page", ReportHandle)
        values = _runtime_kwargs(
            kwargs,
            "wp.page",
            {"size", "width_mm", "height_mm", "orientation", "continuous"},
        )
        page = _validated(
            AuthoringPageIntent,
            _non_null_fields(
                size=_optional_runtime_text(values, "size"),
                width_mm=_optional_runtime_number(values, "width_mm"),
                height_mm=_optional_runtime_number(values, "height_mm"),
                orientation=_optional_runtime_text(values, "orientation"),
                continuous=_optional_runtime_bool_or_none(values, "continuous"),
            ),
            "Page desired state",
        )
        self.update_page(report, page=page)
        return None

    def _runtime_depth(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch primitive depth settings into one canonical depth patch."""
        report = _runtime_handle_arg(args, "wp.depth", ReportHandle)
        values = _runtime_kwargs(kwargs, "wp.depth", {"unit", "scale"})
        depth = _validated(
            AuthoringDepthIntent,
            _non_null_fields(
                unit=_optional_runtime_text(values, "unit"),
                scale=_optional_runtime_scalar(values, "scale", "wp.depth"),
            ),
            "Depth desired state",
        )
        self.update_depth(report, depth=depth)
        return None

    def _runtime_output(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch primitive output settings without filesystem access."""
        report = _runtime_handle_arg(args, "wp.output", ReportHandle)
        values = _runtime_kwargs(
            kwargs,
            "wp.output",
            {"backend", "output_path", "dpi"},
        )
        output = _validated(
            AuthoringOutputIntent,
            _non_null_fields(
                backend=_optional_runtime_text(values, "backend"),
                output_path=_optional_runtime_text(values, "output_path"),
                dpi=_optional_runtime_integer(values, "dpi", "wp.output"),
            ),
            "Output desired state",
        )
        self.update_output(report, output=output)
        return None

    def _runtime_tail(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch minimal report-tail enablement."""
        report = _runtime_handle_arg(args, "wp.tail", ReportHandle)
        values = _runtime_kwargs(kwargs, "wp.tail", {"enabled"})
        self.update_tail(
            report,
            enabled=_required_runtime_bool(values, "enabled", "wp.tail"),
        )
        return None

    def _runtime_source(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Resolve one exact host-registered source candidate."""
        if len(args) > 1:
            raise ProgramTypeError("wp.source accepts at most one positional candidate ID.")
        if args and "candidate_id" in kwargs:
            raise ProgramTypeError("wp.source cannot mix positional and keyword candidate IDs.")
        values = _runtime_kwargs(kwargs, "wp.source", {"candidate_id"})
        if args:
            candidate_id = args[0]
            if not isinstance(candidate_id, str) or not candidate_id:
                raise ProgramTypeError("wp.source candidate ID must be a non-empty string.")
        else:
            candidate_id = _required_runtime_text(values, "candidate_id", "wp.source")
        return self.source(candidate_id)

    def _runtime_section(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch one root section SDK call with an explicit report operand."""
        report = _runtime_handle_arg(args, "wp.section", ReportHandle)
        values = _runtime_kwargs(
            kwargs,
            "wp.section",
            {
                "id_hint",
                "title",
                "subtitle",
                "depth_minimum",
                "depth_maximum",
                "source",
            },
        )
        source = None
        if "source" in values:
            source = _runtime_handle(values["source"], "wp.section", SourceHandle)
        return self.add_section(
            report,
            id_hint=_optional_runtime_text(values, "id_hint"),
            title=_required_runtime_text(values, "title", "wp.section"),
            subtitle=_optional_runtime_text(values, "subtitle"),
            depth_minimum=_optional_runtime_number(values, "depth_minimum"),
            depth_maximum=_optional_runtime_number(values, "depth_maximum"),
            source=source,
        )

    def _runtime_target_section(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Adopt the one opaque section identity registered by the host."""
        report = _runtime_handle_arg(args, "wp.target_section", ReportHandle)
        _runtime_kwargs(kwargs, "wp.target_section", set())
        if self._section_target_id is None:
            raise ProgramPolicyError("No host-selected section target is available.")
        return self.select_section(report, section_id=self._section_target_id)

    def _runtime_update_section(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Apply a sparse update to one section handle selected by the host."""
        section = _runtime_handle_arg(args, "wp.update_section", SectionHandle)
        values = _runtime_kwargs(
            kwargs,
            "wp.update_section",
            {"title", "subtitle", "depth_minimum", "depth_maximum"},
        )
        self.update_section(
            section,
            title=_optional_runtime_text(values, "title"),
            subtitle=_optional_runtime_text(values, "subtitle"),
            depth_minimum=_optional_runtime_number(values, "depth_minimum"),
            depth_maximum=_optional_runtime_number(values, "depth_maximum"),
        )
        return None

    def _runtime_track(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch one root track SDK call with an explicit section operand."""
        section = _runtime_handle_arg(args, "wp.track", SectionHandle)
        values = _runtime_kwargs(
            kwargs,
            "wp.track",
            {
                "id_hint",
                "kind",
                "title",
                "width_mm",
                "scale_minimum",
                "scale_maximum",
                "scale_kind",
                "reverse",
            },
        )
        return self.add_track(
            section,
            id_hint=_optional_runtime_text(values, "id_hint"),
            kind=_required_runtime_text(values, "kind", "wp.track"),
            title=_required_runtime_text(values, "title", "wp.track"),
            width_mm=_required_runtime_number(values, "width_mm", "wp.track"),
            scale_minimum=_optional_runtime_number(values, "scale_minimum"),
            scale_maximum=_optional_runtime_number(values, "scale_maximum"),
            scale_kind=_optional_runtime_text(values, "scale_kind") or "linear",
            reverse=_optional_runtime_bool(values, "reverse", default=False),
        )

    def _runtime_curve(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch one root scalar-binding SDK call with a track operand."""
        track = _runtime_handle_arg(args, "wp.curve", TrackHandle)
        values = _runtime_kwargs(
            kwargs,
            "wp.curve",
            {
                "channel",
                "id_hint",
                "label",
                "scale_minimum",
                "scale_maximum",
                "scale_kind",
                "reverse",
                "color",
                "line_style",
                "line_width",
            },
        )
        return self.add_curve(
            track,
            channel=_required_runtime_text(values, "channel", "wp.curve"),
            id_hint=_optional_runtime_text(values, "id_hint"),
            label=_optional_runtime_text(values, "label"),
            scale_minimum=_optional_runtime_number(values, "scale_minimum"),
            scale_maximum=_optional_runtime_number(values, "scale_maximum"),
            scale_kind=_optional_runtime_text(values, "scale_kind") or "linear",
            reverse=_optional_runtime_bool(values, "reverse", default=False),
            color=_optional_runtime_text(values, "color"),
            line_style=_optional_runtime_text(values, "line_style"),
            line_width=_optional_runtime_number(values, "line_width"),
        )

    def _runtime_raster(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch one root raster-binding SDK call with a track operand."""
        track = _runtime_handle_arg(args, "wp.raster", TrackHandle)
        values = _runtime_kwargs(
            kwargs,
            "wp.raster",
            {
                "channel",
                "id_hint",
                "label",
                "profile",
                "normalization",
                "color_minimum",
                "color_maximum",
                "colormap",
                "alpha",
            },
        )
        return self.add_raster(
            track,
            channel=_required_runtime_text(values, "channel", "wp.raster"),
            id_hint=_optional_runtime_text(values, "id_hint"),
            label=_optional_runtime_text(values, "label"),
            profile=_optional_runtime_text(values, "profile"),
            normalization=_optional_runtime_text(values, "normalization"),
            color_minimum=_optional_runtime_number(values, "color_minimum"),
            color_maximum=_optional_runtime_number(values, "color_maximum"),
            colormap=_optional_runtime_text(values, "colormap"),
            alpha=_optional_runtime_number(values, "alpha"),
        )

    def _runtime_fill(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch one root fill SDK call with explicit track and binding operands."""
        if len(args) not in {2, 3}:
            raise ProgramTypeError("wp.fill requires track, binding, and optional other_binding.")
        track = _runtime_handle(args[0], "wp.fill", TrackHandle)
        binding = _runtime_handle(args[1], "wp.fill", BindingHandle)
        other_binding = (
            _runtime_handle(args[2], "wp.fill", BindingHandle) if len(args) == 3 else None
        )
        values = _runtime_kwargs(
            kwargs,
            "wp.fill",
            {"kind", "id_hint", "label", "color", "alpha"},
        )
        return self.add_fill(
            track,
            kind=_required_runtime_text(values, "kind", "wp.fill"),
            binding=binding,
            other_binding=other_binding,
            id_hint=_optional_runtime_text(values, "id_hint"),
            label=_optional_runtime_text(values, "label"),
            color=_optional_runtime_text(values, "color"),
            alpha=_optional_runtime_number(values, "alpha"),
        )

    def _runtime_annotation(
        self,
        args: tuple[RuntimeValue, ...],
        kwargs: Mapping[str, RuntimeValue],
    ) -> RuntimeValue:
        """Dispatch one root text-annotation SDK call with a track operand."""
        track = _runtime_handle_arg(args, "wp.annotation", TrackHandle)
        values = _runtime_kwargs(
            kwargs,
            "wp.annotation",
            {"text", "depth", "id_hint", "color", "font_size"},
        )
        return self.add_annotation(
            track,
            text=_required_runtime_text(values, "text", "wp.annotation"),
            depth=_required_runtime_number(values, "depth", "wp.annotation"),
            id_hint=_optional_runtime_text(values, "id_hint"),
            color=_optional_runtime_text(values, "color"),
            font_size=_optional_runtime_number(values, "font_size"),
        )


def _non_null_fields(**values: object) -> dict[str, object]:
    """Return explicit SDK values while treating ``None`` as omitted input."""
    return {name: value for name, value in values.items() if value is not None}


def _copy_intent(
    value: BaseModel,
    model_type: type[_Model],
    label: str,
) -> _Model:
    """Copy one canonical partial intent while preserving omitted fields."""
    if not isinstance(value, model_type):
        raise ProgramTypeError(f"{label} is invalid.")
    return _validated(model_type, value.model_dump(exclude_unset=True), label)


def _merge_intent(
    current: BaseModel,
    patch: BaseModel,
    model_type: type[_Model],
    label: str,
) -> _Model:
    """Merge supplied patch fields while preserving omitted canonical state."""
    fields = current.model_dump(exclude_unset=True)
    fields.update(patch.model_dump(exclude_unset=True))
    return _validated(model_type, fields, label)


def _report_header_fields(
    general_fields: Mapping[str, AuthoringHeaderFieldIntent],
    service_titles: Mapping[str, AuthoringServiceTitleIntent],
    detail_fields: Mapping[str, AuthoringHeaderFieldIntent],
) -> dict[str, object]:
    """Return only the explicitly accumulated header collections."""
    return _non_null_fields(
        general_fields=list(general_fields.values()) or None,
        service_titles=list(service_titles.values()) or None,
        detail_fields=list(detail_fields.values()) or None,
    )


def _validated(
    model_type: type[_Model],
    values: Mapping[str, object],
    label: str,
) -> _Model:
    """Build a canonical model while keeping validation failures program-typed."""
    try:
        return model_type.model_validate(dict(values))
    except ValidationError:
        raise ProgramTypeError(f"{label} is invalid.") from None


def _optional_pair(
    minimum: float | None,
    maximum: float | None,
    *,
    label: str,
) -> tuple[float, float] | None:
    """Return an omitted-or-complete numeric pair without inferred values."""
    if minimum is None and maximum is None:
        return None
    if minimum is None or maximum is None:
        raise ProgramTypeError(f"{label} requires both minimum and maximum.")
    return minimum, maximum


def _optional_scale(
    minimum: float | None,
    maximum: float | None,
    *,
    kind: str,
    reverse: bool,
    unit: str | None = None,
    label: str,
) -> AuthoringScale | None:
    """Return one canonical scale only when both explicit bounds were supplied."""
    bounds = _optional_pair(minimum, maximum, label=label)
    if bounds is None:
        return None
    return _validated(
        AuthoringScale,
        {
            "kind": kind,
            "minimum": bounds[0],
            "maximum": bounds[1],
            "reverse": reverse,
            "unit": unit,
        },
        label,
    )


def _optional_style(
    *,
    color: str | None = None,
    line_style: str | None = None,
    line_width: float | None = None,
    colormap: str | None = None,
    alpha: float | None = None,
) -> AuthoringStyleIntent | None:
    """Return a narrow canonical style patch only for explicit SDK options."""
    fields = _non_null_fields(
        color=color,
        line_style=line_style,
        line_width=line_width,
        colormap=colormap,
        alpha=alpha,
    )
    if not fields:
        return None
    return _validated(AuthoringStyleIntent, fields, "Style desired state")


def _replace_annotation_id(annotation: AnnotationSpec, annotation_id: str) -> AnnotationSpec:
    """Return a revalidated typed annotation with the host-owned identity."""
    fields = annotation.model_dump(mode="python")
    fields["annotation_id"] = annotation_id
    return cast(AnnotationSpec, _validated(type(annotation), fields, "Annotation desired state"))


def _replace_section_tracks(
    section: AuthoringSectionIntent,
    tracks: list[AuthoringTrackIntent],
) -> AuthoringSectionIntent:
    """Return one revalidated section fragment with the supplied track order."""
    fields = section.model_dump(exclude_unset=True)
    fields["tracks"] = tracks
    return _validated(AuthoringSectionIntent, fields, "Section desired state")


def _replace_track_field(
    track: AuthoringTrackIntent,
    field: str,
    value: object,
) -> AuthoringTrackIntent:
    """Return one revalidated track fragment with one child collection replaced."""
    fields = track.model_dump(exclude_unset=True)
    fields[field] = value
    return _validated(AuthoringTrackIntent, fields, "Track desired state")


def _require_no_args(args: tuple[RuntimeValue, ...], name: str) -> None:
    """Reject positional values where a root SDK call only accepts keywords."""
    if args:
        raise ProgramTypeError(f"{name} does not accept positional arguments.")


def _runtime_kwargs(
    kwargs: Mapping[str, RuntimeValue],
    name: str,
    allowed: set[str],
) -> dict[str, RuntimeValue]:
    """Copy and validate the narrow keyword set for one root SDK method."""
    unexpected = sorted(set(kwargs).difference(allowed))
    if unexpected:
        raise ProgramTypeError(f"{name} does not accept keyword '{unexpected[0]}'.")
    return dict(kwargs)


def _runtime_handle_arg(
    args: tuple[RuntimeValue, ...],
    name: str,
    handle_type: type[_Handle],
) -> _Handle:
    """Return the one required typed-handle positional operand for a root call."""
    if len(args) != 1:
        raise ProgramTypeError(f"{name} requires exactly one positional handle.")
    return _runtime_handle(args[0], name, handle_type)


def _runtime_handle(
    value: RuntimeValue,
    name: str,
    handle_type: type[_Handle],
) -> _Handle:
    """Require one specific CM-13 typed handle from the restricted runtime."""
    if not isinstance(value, handle_type):
        raise ProgramTypeError(f"{name} received an incompatible handle.")
    return value


def _required_runtime_text(
    values: Mapping[str, RuntimeValue],
    key: str,
    name: str,
) -> str:
    """Return one required non-empty SDK string without implicit coercion."""
    value = _optional_runtime_text(values, key)
    if value is None:
        raise ProgramTypeError(f"{name} requires keyword '{key}'.")
    return value


def _optional_runtime_text(values: Mapping[str, RuntimeValue], key: str) -> str | None:
    """Return one optional explicit string, rejecting nulls and host coercion."""
    if key not in values:
        return None
    value = values[key]
    if not isinstance(value, str):
        raise ProgramTypeError(f"Keyword '{key}' must be a string.")
    return value


def _runtime_report_value(
    values: Mapping[str, RuntimeValue],
    name: str,
) -> AuthoringReportValueIntent:
    """Build one report value from primitive program keywords."""
    return _validated(
        AuthoringReportValueIntent,
        _non_null_fields(
            value=_required_runtime_text(values, "value", name),
            unit=_optional_runtime_text(values, "unit"),
        ),
        f"{name} value",
    )


def _required_runtime_number(
    values: Mapping[str, RuntimeValue],
    key: str,
    name: str,
) -> float:
    """Return one required numeric SDK value without accepting booleans."""
    value = _optional_runtime_number(values, key)
    if value is None:
        raise ProgramTypeError(f"{name} requires keyword '{key}'.")
    return value


def _optional_runtime_number(values: Mapping[str, RuntimeValue], key: str) -> float | None:
    """Return one optional explicit numeric SDK value without coercion."""
    if key not in values:
        return None
    value = values[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProgramTypeError(f"Keyword '{key}' must be a number.")
    return float(value)


def _optional_runtime_scalar(
    values: Mapping[str, RuntimeValue],
    key: str,
    name: str,
) -> str | float | None:
    """Return a depth scale string or number without coercion."""
    if key not in values:
        return None
    value = values[key]
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ProgramTypeError(f"{name} keyword '{key}' must be a string or number.")
    return float(value) if isinstance(value, (int, float)) else value


def _optional_runtime_integer(
    values: Mapping[str, RuntimeValue],
    key: str,
    name: str,
) -> int | None:
    """Return one integer SDK value without accepting booleans or coercion."""
    if key not in values:
        return None
    value = values[key]
    if type(value) is not int:
        raise ProgramTypeError(f"{name} keyword '{key}' must be an integer.")
    return value


def _optional_runtime_bool(
    values: Mapping[str, RuntimeValue],
    key: str,
    *,
    default: bool,
) -> bool:
    """Return one optional explicit boolean SDK value without coercion."""
    if key not in values:
        return default
    value = values[key]
    if type(value) is not bool:
        raise ProgramTypeError(f"Keyword '{key}' must be a boolean.")
    return cast(bool, value)


def _optional_runtime_bool_or_none(
    values: Mapping[str, RuntimeValue],
    key: str,
) -> bool | None:
    """Return an omitted-or-explicit boolean without coercion."""
    if key not in values:
        return None
    value = values[key]
    if type(value) is not bool:
        raise ProgramTypeError(f"Keyword '{key}' must be a boolean.")
    return cast(bool, value)


def _required_runtime_bool(
    values: Mapping[str, RuntimeValue],
    key: str,
    name: str,
) -> bool:
    """Return one required boolean SDK value without coercion."""
    value = _optional_runtime_bool_or_none(values, key)
    if value is None:
        raise ProgramTypeError(f"{name} requires keyword '{key}'.")
    return value


__all__ = ["IntentBuilder"]
