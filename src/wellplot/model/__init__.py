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

"""Public model types for datasets, channels, and log documents."""

from .authoring import (
    AnnotationArrowSpec as AuthoringAnnotationArrowSpec,
)
from .authoring import (
    AnnotationGlyphSpec as AuthoringAnnotationGlyphSpec,
)
from .authoring import (
    AnnotationIntervalSpec as AuthoringAnnotationIntervalSpec,
)
from .authoring import (
    AnnotationMarkerSpec as AuthoringAnnotationMarkerSpec,
)
from .authoring import (
    AnnotationTextSpec as AuthoringAnnotationTextSpec,
)
from .authoring import (
    AnnotationTrackSpec as AuthoringAnnotationTrackSpec,
)
from .authoring import (
    ArrayTrackSpec as AuthoringArrayTrackSpec,
)
from .authoring import (
    AuthoringCurveFillKind,
    AuthoringDataSource,
    AuthoringDepthSpec,
    AuthoringDocumentSpec,
    AuthoringGridDisplayMode,
    AuthoringGridPatch,
    AuthoringGridScaleKind,
    AuthoringGridSpacingMode,
    AuthoringGridSpec,
    AuthoringPageSpec,
    AuthoringRasterNormalizationKind,
    AuthoringRasterProfileKind,
    AuthoringReferenceAxisKind,
    AuthoringReferenceOverlayMode,
    AuthoringReferenceOverlaySpec,
    AuthoringReferenceTickSide,
    AuthoringRemarkSpec,
    AuthoringScale,
    AuthoringScaleKind,
    AuthoringSectionSpec,
    AuthoringStyle,
    AuthoringTrackHeaderObjectKind,
    AuthoringTrackHeaderObjectSpec,
    AuthoringTrackHeaderPatch,
    AuthoringTrackHeaderSpec,
    authoring_json_schema,
)
from .authoring import (
    CurveBindingSpec as AuthoringCurveBindingSpec,
)
from .authoring import (
    CurveFillSpec as AuthoringCurveFillSpec,
)
from .authoring import (
    NormalTrackSpec as AuthoringNormalTrackSpec,
)
from .authoring import (
    RasterBindingSpec as AuthoringRasterBindingSpec,
)
from .authoring import (
    ReferenceTrackSpec as AuthoringReferenceTrackSpec,
)
from .channels import ArrayChannel, BaseChannel, RasterChannel, ScalarChannel
from .dataset import WellDataset
from .document import (
    AnnotationArrowSpec,
    AnnotationGlyphSpec,
    AnnotationIntervalSpec,
    AnnotationLabelMode,
    AnnotationMarkerSpec,
    AnnotationTextSpec,
    CurveCalloutSpec,
    CurveElement,
    CurveFillBaselineSpec,
    CurveFillCrossoverSpec,
    CurveFillKind,
    CurveFillSpec,
    CurveHeaderDisplaySpec,
    CurveValueLabelsSpec,
    DepthAxisSpec,
    FooterSpec,
    GridDisplayMode,
    GridScaleKind,
    GridSpacingMode,
    GridSpec,
    HeaderField,
    HeaderSpec,
    LogDocument,
    MarkerSpec,
    NumberFormatKind,
    PageSpec,
    RasterColorbarPosition,
    RasterElement,
    RasterNormalizationKind,
    RasterProfileKind,
    RasterWaveformSpec,
    ReferenceAxisKind,
    ReferenceCurveOverlayMode,
    ReferenceCurveOverlaySpec,
    ReferenceCurveTickSide,
    ReferenceEventSpec,
    ReferenceTrackSpec,
    ReportBlockSpec,
    ReportDetailCellSpec,
    ReportDetailColumnSpec,
    ReportDetailKind,
    ReportDetailRowSpec,
    ReportDetailSpec,
    ReportFieldSpec,
    ReportServiceTitleSpec,
    ReportValueSpec,
    ScaleKind,
    ScaleSpec,
    StyleSpec,
    TrackHeaderObjectKind,
    TrackHeaderObjectSpec,
    TrackHeaderSpec,
    TrackKind,
    TrackSpec,
    ZoneSpec,
)

__all__ = [
    "ArrayChannel",
    "AuthoringAnnotationArrowSpec",
    "AuthoringAnnotationGlyphSpec",
    "AuthoringAnnotationIntervalSpec",
    "AuthoringAnnotationMarkerSpec",
    "AuthoringAnnotationTextSpec",
    "AuthoringAnnotationTrackSpec",
    "AuthoringArrayTrackSpec",
    "AuthoringCurveBindingSpec",
    "AuthoringCurveFillKind",
    "AuthoringCurveFillSpec",
    "AuthoringDataSource",
    "AuthoringDepthSpec",
    "AuthoringDocumentSpec",
    "AuthoringGridDisplayMode",
    "AuthoringGridPatch",
    "AuthoringGridScaleKind",
    "AuthoringGridSpacingMode",
    "AuthoringGridSpec",
    "AuthoringNormalTrackSpec",
    "AuthoringPageSpec",
    "AuthoringRasterNormalizationKind",
    "AuthoringRasterBindingSpec",
    "AuthoringRasterProfileKind",
    "AuthoringReferenceOverlayMode",
    "AuthoringReferenceOverlaySpec",
    "AuthoringReferenceTrackSpec",
    "AuthoringReferenceAxisKind",
    "AuthoringReferenceTickSide",
    "AuthoringRemarkSpec",
    "AuthoringScale",
    "AuthoringScaleKind",
    "AuthoringSectionSpec",
    "AuthoringStyle",
    "AuthoringTrackHeaderObjectKind",
    "AuthoringTrackHeaderObjectSpec",
    "AuthoringTrackHeaderPatch",
    "AuthoringTrackHeaderSpec",
    "AnnotationArrowSpec",
    "AnnotationGlyphSpec",
    "AnnotationIntervalSpec",
    "AnnotationLabelMode",
    "AnnotationMarkerSpec",
    "AnnotationTextSpec",
    "BaseChannel",
    "CurveCalloutSpec",
    "CurveHeaderDisplaySpec",
    "CurveValueLabelsSpec",
    "CurveElement",
    "CurveFillBaselineSpec",
    "CurveFillCrossoverSpec",
    "CurveFillKind",
    "CurveFillSpec",
    "DepthAxisSpec",
    "FooterSpec",
    "GridDisplayMode",
    "GridScaleKind",
    "GridSpacingMode",
    "GridSpec",
    "HeaderField",
    "HeaderSpec",
    "LogDocument",
    "MarkerSpec",
    "NumberFormatKind",
    "PageSpec",
    "RasterColorbarPosition",
    "RasterChannel",
    "RasterElement",
    "RasterNormalizationKind",
    "RasterProfileKind",
    "RasterWaveformSpec",
    "ReportBlockSpec",
    "ReportDetailCellSpec",
    "ReportDetailColumnSpec",
    "ReportDetailKind",
    "ReportDetailRowSpec",
    "ReportDetailSpec",
    "ReportFieldSpec",
    "ReportServiceTitleSpec",
    "ReportValueSpec",
    "ReferenceAxisKind",
    "ReferenceCurveOverlayMode",
    "ReferenceCurveOverlaySpec",
    "ReferenceCurveTickSide",
    "ReferenceEventSpec",
    "ReferenceTrackSpec",
    "ScaleKind",
    "ScaleSpec",
    "ScalarChannel",
    "StyleSpec",
    "TrackHeaderObjectKind",
    "TrackHeaderObjectSpec",
    "TrackHeaderSpec",
    "TrackKind",
    "TrackSpec",
    "WellDataset",
    "ZoneSpec",
    "authoring_json_schema",
]
