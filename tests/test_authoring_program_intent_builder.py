"""Compile-only tests for the CM-14 canonical intent builder."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from wellplot.authoring_program.builders import HandleBuilder
from wellplot.authoring_program.errors import ProgramNameError, ProgramPolicyError, ProgramTypeError
from wellplot.authoring_program.intent_builder import IntentBuilder
from wellplot.authoring_program.interpreter import interpret_authoring_program
from wellplot.authoring_program.models import AuthoringProgram, ProgramSource
from wellplot.model.authoring import AnnotationTextSpec, AuthoringScale
from wellplot.model.intent import (
    AuthoringAnnotationIntent,
    AuthoringCurveBindingIntent,
    AuthoringDocumentIntent,
    AuthoringFillIntent,
    AuthoringRasterBindingIntent,
    AuthoringSectionIntent,
    AuthoringStyleIntent,
    AuthoringTrackIntent,
)


def _builder(builder_id: str = "builder-a") -> IntentBuilder:
    """Create a deterministic CM-14 builder for exact intent assertions."""
    return IntentBuilder(handles=HandleBuilder(builder_id=builder_id))


def _program(source: str) -> AuthoringProgram:
    """Wrap one source string in the immutable CM-10 program contract."""
    return AuthoringProgram(source=ProgramSource(text=source, logical_name="intent-builder.wpa"))


def _expected_intent(*, include_raster_limits: bool = True) -> AuthoringDocumentIntent:
    """Return the exact canonical desired state constructed by the fixture program."""
    gr = AuthoringCurveBindingIntent(
        kind="curve",
        binding_id="main-pass.combo.GR",
        section_id="main-pass",
        track_id="combo",
        channel="GR",
        label="Gamma Ray",
        scale=AuthoringScale(minimum=0, maximum=150),
        style=AuthoringStyleIntent(color="#228b22", line_width=0.8),
    )
    sp = AuthoringCurveBindingIntent(
        kind="curve",
        binding_id="main-pass.combo.SP",
        section_id="main-pass",
        track_id="combo",
        channel="SP",
        label="Spontaneous Potential",
    )
    raster_fields: dict[str, object] = {
        "kind": "raster",
        "binding_id": "main-pass.combo.VDL",
        "section_id": "main-pass",
        "track_id": "combo",
        "channel": "VDL",
        "label": "VDL",
        "profile": "vdl",
        "normalization": "none",
        "style": AuthoringStyleIntent(colormap="seismic", alpha=0.8),
    }
    if include_raster_limits:
        raster_fields["color_limits"] = (-100, 100)
    vdl = AuthoringRasterBindingIntent(
        **raster_fields,
    )
    fill = AuthoringFillIntent(
        fill_id="main-pass.combo.fill.gas-crossover",
        section_id="main-pass",
        track_id="combo",
        kind="between_instances",
        binding_id=gr.binding_id,
        other_binding_id=sp.binding_id,
        label="Gas crossover",
        color="#ffee88",
        alpha=0.35,
    )
    annotation = AuthoringAnnotationIntent(
        annotation_id="main-pass.combo.annotation.bond",
        section_id="main-pass",
        track_id="combo",
        annotation=AnnotationTextSpec(
            annotation_id="main-pass.combo.annotation.bond",
            text="Bond evaluation",
            depth=2500,
            color="#333333",
            font_size=8,
        ),
    )
    return AuthoringDocumentIntent(
        title="CBL Quicklook",
        subtitle="Compile-only",
        sections=[
            AuthoringSectionIntent(
                section_id="main-pass",
                title="Main Pass",
                depth_range=(1000, 5000),
                tracks=[
                    AuthoringTrackIntent(
                        track_id="combo",
                        section_id="main-pass",
                        kind="normal",
                        title="Combo",
                        width_mm=32,
                        x_scale=AuthoringScale(minimum=0, maximum=100),
                        bindings=[gr, sp, vdl],
                        fills=[fill],
                        annotations=[annotation],
                    )
                ],
            )
        ],
    )


def _build_all_families(builder: IntentBuilder) -> AuthoringDocumentIntent:
    """Build all seven CM-14 construction families through direct SDK calls."""
    report = builder.report(title="CBL Quicklook", subtitle="Compile-only")
    section = builder.add_section(
        report,
        id_hint="main pass",
        title="Main Pass",
        depth_minimum=1000,
        depth_maximum=5000,
    )
    track = builder.add_track(
        section,
        id_hint="combo",
        kind="normal",
        title="Combo",
        width_mm=32,
        scale_minimum=0,
        scale_maximum=100,
    )
    gr = builder.add_curve(
        track,
        channel="GR",
        label="Gamma Ray",
        scale_minimum=0,
        scale_maximum=150,
        color="#228b22",
        line_width=0.8,
    )
    sp = builder.add_curve(track, channel="SP", label="Spontaneous Potential")
    builder.add_raster(
        track,
        channel="VDL",
        label="VDL",
        profile="vdl",
        normalization="none",
        color_minimum=-100,
        color_maximum=100,
        colormap="seismic",
        alpha=0.8,
    )
    builder.add_fill(
        track,
        kind="between_instances",
        binding=gr,
        other_binding=sp,
        id_hint="gas crossover",
        label="Gas crossover",
        color="#ffee88",
        alpha=0.35,
    )
    builder.add_annotation(
        track,
        id_hint="bond",
        text="Bond evaluation",
        depth=2500,
        color="#333333",
        font_size=8,
    )
    return builder.intent()


def test_intent_builder_accumulates_all_required_canonical_intent_families() -> None:
    """Direct typed SDK calls build the exact canonical intent and no shadow IR."""
    builder = _builder()

    assert _build_all_families(builder) == _expected_intent()

    first = builder.intent()
    second = builder.intent()
    assert first is not second
    assert first == second


def test_source_runs_through_cm11_cm12_cm13_and_cm14_into_exact_intent() -> None:
    """One restricted program proves the complete pure source-to-intent path."""
    source = (
        "report = wp.report(title='CBL Quicklook', subtitle='Compile-only')\n"
        "section = wp.section(report, id_hint='main pass', title='Main Pass', "
        "depth_minimum=1000, depth_maximum=5000)\n"
        "track = wp.track(section, id_hint='combo', kind='normal', title='Combo', "
        "width_mm=32, scale_minimum=0, scale_maximum=100)\n"
        "gr = wp.curve(track, channel='GR', label='Gamma Ray', scale_minimum=0, "
        "scale_maximum=150, color='#228b22', line_width=0.8)\n"
        "sp = wp.curve(track, channel='SP', label='Spontaneous Potential')\n"
        "wp.raster(track, channel='VDL', label='VDL', profile='vdl', "
        "normalization='none', colormap='seismic', alpha=0.8)\n"
        "wp.fill(track, gr, sp, kind='between_instances', id_hint='gas crossover', "
        "label='Gas crossover', color='#ffee88', alpha=0.35)\n"
        "wp.annotation(track, id_hint='bond', text='Bond evaluation', depth=2500, "
        "color='#333333', font_size=8)\n"
    )
    builder = _builder()

    result = interpret_authoring_program(_program(source), builder.runtime_environment())

    assert result.metrics.program_calls == 8
    assert builder.intent() == _expected_intent(include_raster_limits=False)


def test_equivalent_programs_and_builder_setup_serialize_to_identical_intent() -> None:
    """CM-14 determinism includes ordered calls and CM-13 allocated identities."""
    source = (
        "report = wp.report(title='One')\n"
        "section = wp.section(report, id_hint='main', title='Main')\n"
        "track = wp.track(section, id_hint='combo', kind='normal', title='Combo', width_mm=30)\n"
        "wp.curve(track, channel='GR')\n"
        "wp.curve(track, channel='GR')\n"
    )
    first = _builder("builder-stable")
    second = _builder("builder-stable")

    interpret_authoring_program(_program(source), first.runtime_environment())
    interpret_authoring_program(_program(source), second.runtime_environment())

    assert first.intent().model_dump_json() == second.intent().model_dump_json()
    bindings = first.intent().sections[0].tracks[0].bindings
    assert [binding.binding_id for binding in bindings] == [
        "main.combo.GR",
        "main.combo.GR.2",
    ]


def test_intent_builder_rejects_foreign_and_wrong_parent_handles_before_accumulation() -> None:
    """CM-13 ownership checks run before CM-14 accepts a desired-state fragment."""
    builder = _builder()
    report = builder.report(title="One")
    main = builder.add_section(report, id_hint="main", title="Main")
    repeat = builder.add_section(report, id_hint="repeat", title="Repeat")
    main_track = builder.add_track(main, id_hint="combo", kind="normal", title="Combo", width_mm=30)
    repeat_track = builder.add_track(
        repeat,
        id_hint="combo",
        kind="normal",
        title="Combo",
        width_mm=30,
    )
    binding = builder.add_curve(main_track, channel="GR")

    with pytest.raises(ProgramPolicyError, match="does not belong"):
        builder.add_fill(repeat_track, kind="between_instances", binding=binding)

    foreign = _builder("builder-b")
    with pytest.raises(ProgramNameError, match="different identity builder"):
        foreign.add_section(report, id_hint="foreign", title="Foreign")


def test_invalid_narrow_sdk_values_are_rejected_by_canonical_intent_validation() -> None:
    """CM-14 never accepts invalid values before they enter the accumulator."""
    builder = _builder()
    report = builder.report(title="One")
    section = builder.add_section(report, id_hint="main", title="Main")

    with pytest.raises(ProgramTypeError, match="Track desired state is invalid"):
        builder.add_track(section, id_hint="bad", kind="normal", title="Bad", width_mm=0)

    track = builder.add_track(section, id_hint="combo", kind="normal", title="Combo", width_mm=30)
    with pytest.raises(ProgramTypeError, match="Raster color limits requires both"):
        builder.add_raster(track, channel="VDL", color_minimum=-100)


def test_intent_builder_has_no_application_service_or_edge_imports() -> None:
    """Intent compilation stays independent from services, providers, MCP, and graphs."""
    module_path = Path(__file__).parents[1] / "src/wellplot/authoring_program/intent_builder.py"
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
        "langgraph",
        "mcp",
        "wellplot.authoring_service",
        "wellplot.authoring_reconciler",
        "wellplot.authoring_executor",
    )
    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imported_modules
        for prefix in forbidden_prefixes
    )
