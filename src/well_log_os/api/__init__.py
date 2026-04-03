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

from .builder import LogBuilder, ProgrammaticLogSpec, SectionBuilder
from .dataset import DatasetBuilder, create_dataset
from .render import (
    build_documents,
    render_png_bytes,
    render_report,
    render_section,
    render_section_png,
    render_svg_bytes,
    render_track,
    render_track_png,
    render_window,
    render_window_png,
)
from .serialize import (
    document_from_dict,
    document_from_yaml,
    document_to_dict,
    document_to_yaml,
    load_document_yaml,
    load_report,
    report_from_dict,
    report_from_yaml,
    report_to_dict,
    report_to_yaml,
    save_document,
    save_report,
)

__all__ = [
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
    "report_from_dict",
    "report_from_yaml",
    "report_to_dict",
    "report_to_yaml",
    "save_document",
    "save_report",
    "render_png_bytes",
    "render_report",
    "render_section",
    "render_section_png",
    "render_svg_bytes",
    "render_track",
    "render_track_png",
    "render_window",
    "render_window_png",
]
