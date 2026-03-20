from __future__ import annotations

from pathlib import Path

from well_log_os import (
    LogBuilder,
    build_documents,
    create_dataset,
    document_to_yaml,
    report_to_yaml,
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
    section = builder.add_section("main", dataset=dataset, title="Main")
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

    report_to_yaml(report, report_yaml_path)
    document_to_yaml(documents[0], document_yaml_path)

    print("Saved report YAML:", report_yaml_path)
    print("Saved document YAML:", document_yaml_path)


if __name__ == "__main__":
    main()
