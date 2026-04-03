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

from __future__ import annotations

from pathlib import Path

from well_log_os import (
    LogBuilder,
    build_documents,
    create_dataset,
    save_document,
    save_report,
)


def build_dataset():
    dataset = create_dataset("serialize-demo")
    dataset.add_curve(
        mnemonic="GR",
        values=[70.0, 75.0, 82.0],
        index=[8200.0, 8210.0, 8220.0],
        index_unit="ft",
        value_unit="gAPI",
    )
    return dataset


def build_report(dataset):
    builder = LogBuilder(name="Serialize Demo")
    builder.set_render(backend="matplotlib", output_path="serialize_demo.pdf", dpi=120)
    builder.set_page(size="A4", orientation="portrait", header_height_mm=0, footer_height_mm=0)
    builder.set_depth_axis(unit="ft", scale=240, major_step=10, minor_step=2)
    builder.set_depth_range(8200, 8220)
    section = builder.add_section(
        "main",
        dataset=dataset,
        title="Main",
        source_path="workspace/data/demo.las",
        source_format="las",
    )
    section.add_track(
        id="depth",
        title="",
        kind="reference",
        width_mm=16,
        reference={"axis": "depth", "define_layout": True, "unit": "ft"},
    )
    section.add_track(id="combo", title="", kind="normal", width_mm=30)
    section.add_curve(
        channel="GR",
        track_id="combo",
        label="Gamma Ray",
        scale={"kind": "linear", "min": 0, "max": 150},
    )
    return builder.build()


def main() -> None:
    dataset = build_dataset()
    report = build_report(dataset)
    documents = build_documents(report)

    report_yaml_path = Path("workspace/renders/api_serialize_report.yaml")
    document_yaml_path = Path("workspace/renders/api_serialize_document.yaml")

    save_report(report, report_yaml_path)
    save_document(documents[0], document_yaml_path)

    print("Saved report YAML:", report_yaml_path)
    print("Saved document YAML:", document_yaml_path)


if __name__ == "__main__":
    main()
