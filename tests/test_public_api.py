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

"""Public package import-contract tests."""

from __future__ import annotations

import unittest

import wellplot
from wellplot import api
from wellplot._version import __version__ as package_version


class PublicApiTests(unittest.TestCase):
    """Lock the supported import surfaces for package consumers."""

    def test_package_version_is_single_sourced(self) -> None:
        """Expose the package version from the dedicated version module."""
        self.assertEqual(wellplot.__version__, package_version)

    def test_api_package_exports_expected_names(self) -> None:
        """Keep the public ``wellplot.api`` surface explicit and stable."""
        expected = {
            "DatasetBuilder",
            "LogBuilder",
            "ProgrammaticLogSpec",
            "SectionBuilder",
            "build_documents",
            "create_dataset",
            "document_from_dict",
            "document_from_yaml",
            "document_to_dict",
            "document_to_yaml",
            "load_document_yaml",
            "load_report",
            "render_png_bytes",
            "render_report",
            "render_section",
            "render_section_png",
            "render_svg_bytes",
            "render_track",
            "render_track_png",
            "render_window",
            "render_window_png",
            "report_from_dict",
            "report_from_yaml",
            "report_to_dict",
            "report_to_yaml",
            "save_document",
            "save_report",
        }

        self.assertEqual(set(api.__all__), expected)
        for name in expected:
            self.assertTrue(hasattr(api, name), name)

    def test_top_level_package_reexports_supported_api_surface(self) -> None:
        """Expose the documented runtime helpers from ``wellplot``."""
        expected = {
            "__version__",
            "ArrayChannel",
            "AnnotationArrowSpec",
            "AnnotationGlyphSpec",
            "AnnotationIntervalSpec",
            "AnnotationLabelMode",
            "AnnotationMarkerSpec",
            "AnnotationTextSpec",
            "CurveCalloutSpec",
            "CurveElement",
            "CurveFillBaselineSpec",
            "CurveFillCrossoverSpec",
            "CurveFillKind",
            "CurveFillSpec",
            "CurveHeaderDisplaySpec",
            "DatasetBuilder",
            "DatasetValidationError",
            "DepthAxisSpec",
            "FooterSpec",
            "GridDisplayMode",
            "GridScaleKind",
            "GridSpacingMode",
            "GridSpec",
            "HeaderField",
            "HeaderSpec",
            "LayoutEngine",
            "LogBuilder",
            "LogDocument",
            "LogFileSpec",
            "MarkerSpec",
            "PageSpec",
            "ProgrammaticLogSpec",
            "RasterChannel",
            "RasterElement",
            "ReferenceCurveOverlayMode",
            "ReferenceCurveOverlaySpec",
            "ReferenceCurveTickSide",
            "ReferenceEventSpec",
            "ReportBlockSpec",
            "ReportDetailCellSpec",
            "ReportDetailColumnSpec",
            "ReportDetailKind",
            "ReportDetailRowSpec",
            "ReportDetailSpec",
            "ReportFieldSpec",
            "ReportServiceTitleSpec",
            "ReportValueSpec",
            "ScalarChannel",
            "ScaleKind",
            "ScaleSpec",
            "SectionBuilder",
            "StyleSpec",
            "TrackHeaderObjectKind",
            "TrackHeaderObjectSpec",
            "TrackHeaderSpec",
            "TrackKind",
            "TrackSpec",
            "WellDataset",
            "ZoneSpec",
            "build_document_for_logfile",
            "build_documents",
            "build_documents_for_logfile",
            "create_dataset",
            "document_from_dict",
            "document_from_mapping",
            "document_from_yaml",
            "document_to_dict",
            "document_to_yaml",
            "get_logfile_json_schema",
            "load_dataset_for_logfile",
            "load_datasets_for_logfile",
            "load_document",
            "load_document_yaml",
            "load_logfile",
            "load_report",
            "logfile_from_mapping",
            "render_from_logfile",
            "render_png_bytes",
            "render_report",
            "render_section",
            "render_section_png",
            "render_svg_bytes",
            "render_track",
            "render_track_png",
            "render_window",
            "render_window_png",
            "report_from_dict",
            "report_from_yaml",
            "report_to_dict",
            "report_to_yaml",
            "save_document",
            "save_report",
            "validate_logfile_mapping",
        }

        self.assertEqual(set(wellplot.__all__), expected)
        for name in expected:
            self.assertTrue(hasattr(wellplot, name), name)
        for name in api.__all__:
            self.assertIs(getattr(wellplot, name), getattr(api, name), name)
