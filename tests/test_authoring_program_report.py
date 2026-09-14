"""CM-21 tests for the static report.standard capability contract."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from wellplot.authoring_program.builders import HandleBuilder
from wellplot.authoring_program.errors import ProgramNameError, ProgramTypeError
from wellplot.authoring_program.intent_builder import IntentBuilder
from wellplot.capabilities.builtins import ReportArtifact, create_builtin_registry
from wellplot.capabilities.report_standard import (
    ReportStandardArgs,
    ReportStandardFieldArgs,
    ReportStandardRemarkArgs,
    ReportStandardServiceTitleArgs,
    ReportStandardValueArgs,
    compile_report_standard,
)
from wellplot.model.intent import (
    AuthoringDepthIntent,
    AuthoringOutputIntent,
    AuthoringPageIntent,
    AuthoringReportValueIntent,
)


def _value(value: str, *, unit: str | None = None) -> AuthoringReportValueIntent:
    """Build one canonical value for direct host-builder tests."""
    fields: dict[str, object] = {"value": value}
    if unit is not None:
        fields["unit"] = unit
    return AuthoringReportValueIntent.model_validate(fields)


def test_report_standard_v2_preserves_v1_and_compiles_sparse_report_intent() -> None:
    """The migrated capability retains v1 metadata and emits canonical intent."""
    spec = create_builtin_registry().get("report.standard")
    arguments = ReportStandardArgs(
        title="Open Hole Quicklook",
        subtitle="CM-21",
        header_fields=(
            ReportStandardFieldArgs(
                key="well",
                value=ReportStandardValueArgs(value="FORGE 16B"),
            ),
            ReportStandardFieldArgs(
                key="rm",
                value=ReportStandardValueArgs(value="0.005", unit="ohm.m"),
            ),
        ),
        service_titles=(
            ReportStandardServiceTitleArgs(
                slot_id="service_title_1",
                value=ReportStandardValueArgs(value="Open Hole Quicklook"),
                bold=True,
            ),
        ),
        detail_fields=(
            ReportStandardFieldArgs(
                key="detail.run_number",
                value=ReportStandardValueArgs(value="ONE"),
            ),
        ),
        remarks=(
            ReportStandardRemarkArgs(
                remark_id="scope",
                title="Scope",
                text="Supported channels only.",
            ),
        ),
        page=AuthoringPageIntent(width_mm=210, height_mm=297),
        depth=AuthoringDepthIntent(unit="ft", major_step=100, minor_step=20),
        output=AuthoringOutputIntent(backend="matplotlib", dpi=150),
    )

    intent = spec.handler(arguments)

    assert spec.supports_v2 is True
    assert spec.artifact_model is ReportArtifact
    assert spec.planning_descriptor()["id"] == "report.standard"
    assert intent.title == "Open Hole Quicklook"
    assert intent.subtitle == "CM-21"
    assert intent.header is not None
    assert intent.header.general_fields[0].slot_id == "well"
    assert intent.header.general_fields[0].key == "well"
    assert intent.header.service_titles[0].value.value == "Open Hole Quicklook"
    assert intent.header.detail_fields[0].slot_id == "detail.run_number"
    assert intent.remarks[0].text == "Supported channels only."
    assert intent.page.width_mm == 210
    assert intent.depth.major_step == 100
    assert intent.output.dpi == 150


def test_report_standard_omitted_fields_emit_no_unintended_updates() -> None:
    """An empty sparse argument object produces an empty canonical patch."""
    assert compile_report_standard(ReportStandardArgs()).model_dump(
        mode="json", exclude_none=True
    ) == {"removals": []}


def test_report_standard_arguments_are_static_and_strict() -> None:
    """Unknown fields and empty remark placeholders are rejected deterministically."""
    with pytest.raises(ValidationError):
        ReportStandardArgs(unexpected="not allowed")
    with pytest.raises(ValidationError, match="requires text or lines"):
        ReportStandardRemarkArgs(remark_id="empty")
    with pytest.raises(ValidationError, match="must not be empty"):
        ReportStandardArgs(header_fields=())


def test_report_builder_methods_enforce_report_ownership() -> None:
    """Explicit report methods retain CM-13 provenance and type checks."""
    builder = IntentBuilder(handles=HandleBuilder(builder_id="builder-a"))
    report = builder.report()
    foreign = IntentBuilder(handles=HandleBuilder(builder_id="builder-b")).report()

    with pytest.raises(ProgramNameError, match="different identity builder"):
        builder.set_header_field(foreign, key="well", value=_value("FORGE 16B"))
    with pytest.raises(ProgramTypeError, match="runtime handle"):
        builder.set_header_field("not a report", key="well", value=_value("FORGE 16B"))  # type: ignore[arg-type]

    builder.set_header_field(report, key="well", value=_value("FORGE 16B"))
    builder.add_remark(report, remark_id="scope", text="Supported only.")
    assert builder.intent().header.general_fields[0].slot_id == "well"


def test_report_standard_module_has_no_application_or_edge_imports() -> None:
    """The capability handler remains independent from services and providers."""
    module_path = Path(__file__).parents[1] / "src/wellplot/capabilities/report_standard.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)

    forbidden_prefixes = (
        "wellplot.agent",
        "wellplot.mcp",
        "wellplot.authoring_service",
        "wellplot.authoring_reconciler",
        "wellplot.authoring_executor",
        "langgraph",
        "mcp",
    )
    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imported_modules
        for prefix in forbidden_prefixes
    )
