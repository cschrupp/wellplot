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

"""Shared MCP test fixtures backed by repository-contained temporary files."""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
_BASE_LOGFILE = REPO_ROOT / "examples" / "cbl_main.log.yaml"
_BASE_LOGFILE_MAPPING = yaml.safe_load(_BASE_LOGFILE.read_text(encoding="utf-8"))
_TEMPLATE_PATH = REPO_ROOT / "templates" / "wireline_base.template.yaml"
_MINIMAL_LAS_TEXT = """~Version Information
 VERS.                  2.0:   CWLS log ASCII standard - VERSION 2.0
 WRAP.                   NO:   One line per depth step
~Well Information
 STRT.M               1000.0:   START DEPTH
 STOP.M               1020.0:   STOP DEPTH
 STEP.M                  1.0:   STEP
 NULL.               -999.25:   NULL VALUE
 COMP.               WELLPLOT:   COMPANY
 WELL.         MCP FIXTURE-01:   WELL
 FLD .               DEMO-FLD:   FIELD
~Curve Information
 DEPT.M                     :   Depth
 CBL .mV                    :   Cement bond log amplitude
 VDL .mV                    :   Variable density log scalar proxy
 GR  .gAPI                  :   Gamma ray
 CALI.in                    :   Caliper
 RT  .ohm.m                 :   Resistivity
~ASCII Log Data
1000.0  48.0  10.0  70.0  8.60  1.10
1002.0  47.5  11.0  72.0  8.55  1.20
1004.0  47.0  12.0  74.0  8.50  1.30
1006.0  46.5  13.0  76.0  8.45  1.40
1008.0  46.0  14.0  78.0  8.40  1.50
1010.0  45.5  15.0  80.0  8.35  1.60
1012.0  45.0  16.0  82.0  8.30  1.70
1014.0  44.5  17.0  84.0  8.25  1.80
1016.0  44.0  18.0  86.0  8.20  1.90
1018.0  43.5  19.0  88.0  8.15  2.00
1020.0  43.0  20.0  90.0  8.10  2.10
"""


@dataclass(frozen=True)
class McpFixturePaths:
    """Paths and text for synthetic MCP logfile fixtures."""

    fixture_dir: Path
    las_path: Path
    single_logfile: Path
    multi_logfile: Path
    single_logfile_relative: str
    multi_logfile_relative: str
    single_logfile_text: str


def create_mcp_fixture_paths(fixture_dir: Path, *, repo_root: Path = REPO_ROOT) -> McpFixturePaths:
    """Create tracked-repo-relative MCP test fixtures under one temporary directory."""
    fixture_dir.mkdir(parents=True, exist_ok=True)
    las_path = fixture_dir / "fixture.las"
    las_path.write_text(_MINIMAL_LAS_TEXT, encoding="utf-8")

    single_mapping = copy.deepcopy(_BASE_LOGFILE_MAPPING)
    single_mapping["template"] = {
        "path": Path(os.path.relpath(_TEMPLATE_PATH, start=fixture_dir)).as_posix()
    }
    single_mapping["name"] = "MCP Single Fixture"
    single_mapping["render"]["output_path"] = "./fixture-render.pdf"
    section = single_mapping["document"]["layout"]["log_sections"][0]
    section["subtitle"] = "Fixture Main"
    section["data"]["source_path"] = "./fixture.las"
    section["data"]["source_format"] = "auto"

    single_logfile = fixture_dir / "single.log.yaml"
    single_logfile.write_text(
        yaml.safe_dump(single_mapping, sort_keys=False),
        encoding="utf-8",
    )

    multi_mapping = copy.deepcopy(single_mapping)
    multi_mapping["name"] = "MCP Multi Fixture"
    multi_layout = multi_mapping["document"]["layout"]
    multi_layout["remarks"] = [
        {
            "title": "Fixture Remarks",
            "lines": ["Synthetic LAS-backed MCP multisection fixture."],
            "alignment": "left",
        }
    ]

    main_section = copy.deepcopy(section)
    main_section["id"] = "main_pass"
    main_section["title"] = "Main Pass"
    main_section["subtitle"] = "Fixture Main Pass"
    main_section["depth_range"] = [1000.0, 1020.0]

    repeat_section = copy.deepcopy(section)
    repeat_section["id"] = "repeat_pass"
    repeat_section["title"] = "Repeat Pass"
    repeat_section["subtitle"] = "Fixture Repeat Pass"
    repeat_section["depth_range"] = [1006.0, 1018.0]

    multi_layout["log_sections"] = [main_section, repeat_section]
    base_bindings = single_mapping["document"]["bindings"]["channels"]
    multi_mapping["document"]["bindings"]["channels"] = []
    for section_id in ("main_pass", "repeat_pass"):
        for binding in base_bindings:
            section_binding = copy.deepcopy(binding)
            section_binding["section"] = section_id
            multi_mapping["document"]["bindings"]["channels"].append(section_binding)

    multi_logfile = fixture_dir / "multi.log.yaml"
    multi_logfile.write_text(
        yaml.safe_dump(multi_mapping, sort_keys=False),
        encoding="utf-8",
    )

    return McpFixturePaths(
        fixture_dir=fixture_dir,
        las_path=las_path,
        single_logfile=single_logfile,
        multi_logfile=multi_logfile,
        single_logfile_relative=Path(os.path.relpath(single_logfile, start=repo_root)).as_posix(),
        multi_logfile_relative=Path(os.path.relpath(multi_logfile, start=repo_root)).as_posix(),
        single_logfile_text=single_logfile.read_text(encoding="utf-8"),
    )
