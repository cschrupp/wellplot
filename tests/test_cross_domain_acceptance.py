"""Cross-domain acceptance fixtures for the canonical authoring contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from wellplot import authoring_document_to_render
from wellplot.authoring_context import resolve_authoring_context
from wellplot.authoring_executor import execute_authoring_plan
from wellplot.authoring_reconciler import reconcile_authoring
from wellplot.authoring_service import AuthoringService
from wellplot.model import (
    AuthoringAnnotationMarkerShape,
    AuthoringAnnotationMarkerSpec,
    AuthoringAnnotationTrackSpec,
    AuthoringArrayTrackSpec,
    AuthoringCurveBindingSpec,
    AuthoringCurveFillCrossoverSpec,
    AuthoringCurveFillKind,
    AuthoringCurveFillSpec,
    AuthoringDocumentIntent,
    AuthoringDocumentSpec,
    AuthoringGridScaleKind,
    AuthoringGridSpacingMode,
    AuthoringGridSpec,
    AuthoringHeaderDetailRowSpec,
    AuthoringHeaderDetailSpec,
    AuthoringHeaderFieldSpec,
    AuthoringHeaderSpec,
    AuthoringNormalTrackSpec,
    AuthoringRasterBindingSpec,
    AuthoringRasterProfileKind,
    AuthoringReferenceTrackSpec,
    AuthoringReportValueSpec,
    AuthoringScale,
    AuthoringScaleKind,
    AuthoringStyle,
)


def _binding_id(section_id: str, name: str) -> str:
    """Give repeated section content globally stable binding identities."""
    return f"{section_id}.{name}"


def _curve(
    section_id: str,
    name: str,
    channel: str,
    *,
    label: str | None = None,
    scale: AuthoringScale | None = None,
    style: AuthoringStyle | None = None,
) -> AuthoringCurveBindingSpec:
    """Build one explicit scalar binding for an acceptance fixture."""
    return AuthoringCurveBindingSpec(
        binding_id=_binding_id(section_id, name),
        channel=channel,
        label=label,
        scale=scale,
        style=style or AuthoringStyle(),
    )


def _section(section_id: str) -> dict[str, object]:
    """Build a generic section containing the supported content families."""
    resistivity_scale = AuthoringScale(
        kind=AuthoringScaleKind.LOG,
        minimum=0.2,
        maximum=2000.0,
        unit="ohm.m",
    )
    porosity_bindings = [
        _curve(
            section_id,
            "rhob",
            "RHOB",
            label="Bulk Density",
            scale=AuthoringScale(minimum=1.95, maximum=2.95, unit="g/cc"),
            style=AuthoringStyle(color="#c2410c", line_width=1.3),
        ),
        _curve(
            section_id,
            "nphi",
            "NPHI",
            label="Neutron Porosity",
            scale=AuthoringScale(
                minimum=0.45,
                maximum=-0.15,
                unit="pu",
                reverse=True,
            ),
            style=AuthoringStyle(color="#1d4ed8", line_width=1.1),
        ),
    ]
    return {
        "id": section_id,
        "title": section_id.replace("_", " ").title(),
        "depth_range": (1000.0, 2500.0),
        "tracks": [
            AuthoringReferenceTrackSpec(
                id="depth",
                title="Depth",
                width_mm=16.0,
                unit="ft",
                bindings=[_curve(section_id, "depth-marker", "DEPT")],
            ),
            AuthoringNormalTrackSpec(
                id="combo",
                title="GR/SP",
                width_mm=28.0,
                bindings=[
                    _curve(
                        section_id,
                        "gr",
                        "GR",
                        scale=AuthoringScale(minimum=0.0, maximum=150.0, unit="gAPI"),
                        style=AuthoringStyle(color="#15803d", line_width=1.1),
                    ),
                    _curve(
                        section_id,
                        "sp",
                        "SP",
                        scale=AuthoringScale(minimum=-80.0, maximum=20.0, unit="mV"),
                        style=AuthoringStyle(color="#2563eb", line_style="--"),
                    ),
                ],
            ),
            AuthoringNormalTrackSpec(
                id="resistivity",
                title="Resistivity",
                width_mm=32.0,
                x_scale=resistivity_scale,
                grid=AuthoringGridSpec(
                    vertical_main_scale=AuthoringGridScaleKind.LOGARITHMIC,
                    vertical_main_spacing_mode=AuthoringGridSpacingMode.SCALE,
                    vertical_secondary_scale=AuthoringGridScaleKind.LOGARITHMIC,
                    vertical_secondary_spacing_mode=AuthoringGridSpacingMode.SCALE,
                ),
                bindings=[
                    _curve(
                        section_id,
                        "rdeep",
                        "RDEEP",
                        scale=resistivity_scale,
                        style=AuthoringStyle(color="#111827", line_width=1.3),
                    ),
                    _curve(
                        section_id,
                        "rmedium",
                        "RMED",
                        scale=resistivity_scale,
                        style=AuthoringStyle(color="#16a34a", line_width=1.0),
                    ),
                    _curve(
                        section_id,
                        "rshallow",
                        "RSH",
                        scale=resistivity_scale,
                        style=AuthoringStyle(color="#dc2626", line_style=":", line_width=0.9),
                    ),
                ],
            ),
            AuthoringNormalTrackSpec(
                id="porosity",
                title="Porosity",
                width_mm=32.0,
                bindings=porosity_bindings,
                fills=[
                    AuthoringCurveFillSpec(
                        fill_id=_binding_id(section_id, "gas-crossover"),
                        kind=AuthoringCurveFillKind.BETWEEN_INSTANCES,
                        binding_id=_binding_id(section_id, "nphi"),
                        other_binding_id=_binding_id(section_id, "rhob"),
                        label="Gas Crossover",
                        color="#d1d5db",
                        alpha=0.18,
                        crossover=AuthoringCurveFillCrossoverSpec(
                            enabled=True,
                            left_color="#bfdbfe",
                            right_color="#fed7aa",
                            alpha=0.28,
                        ),
                    )
                ],
            ),
            AuthoringNormalTrackSpec(
                id="caliper",
                title="Caliper",
                width_mm=28.0,
                bindings=[
                    _curve(
                        section_id,
                        "cali-1",
                        "CALI",
                        label="CALI (left)",
                        scale=AuthoringScale(minimum=6.0, maximum=16.0, unit="in"),
                        style=AuthoringStyle(color="#8b5e3c"),
                    ),
                    _curve(
                        section_id,
                        "cali-2",
                        "CALI",
                        label="CALI (mirrored)",
                        scale=AuthoringScale(minimum=16.0, maximum=6.0, unit="in"),
                        style=AuthoringStyle(color="#a16207", line_style="--"),
                    ),
                ],
                fills=[
                    AuthoringCurveFillSpec(
                        fill_id=_binding_id(section_id, "caliper-fill"),
                        kind=AuthoringCurveFillKind.BETWEEN_INSTANCES,
                        binding_id=_binding_id(section_id, "cali-1"),
                        other_binding_id=_binding_id(section_id, "cali-2"),
                        color="#c4a484",
                        alpha=0.2,
                    )
                ],
            ),
            AuthoringNormalTrackSpec(
                id="cbl",
                title="CBL",
                width_mm=36.0,
                bindings=[
                    _curve(
                        section_id,
                        "cbl-1",
                        "CBL",
                        label="CBL Amplitude (0-100)",
                        scale=AuthoringScale(minimum=0.0, maximum=100.0, unit="mV"),
                        style=AuthoringStyle(color="black", line_width=0.75),
                    ),
                    _curve(
                        section_id,
                        "cbl-2",
                        "CBL",
                        label="CBL Amplitude (0-10)",
                        scale=AuthoringScale(minimum=0.0, maximum=10.0, unit="mV"),
                        style=AuthoringStyle(color="blue", line_style="--", line_width=0.65),
                    ),
                ],
            ),
            AuthoringArrayTrackSpec(
                id="vdl",
                title="VDL",
                width_mm=40.0,
                bindings=[
                    AuthoringRasterBindingSpec(
                        binding_id=_binding_id(section_id, "vdl"),
                        channel="VDL",
                        label="Variable Density Log",
                        profile=AuthoringRasterProfileKind.VDL,
                        style=AuthoringStyle(colormap="gray_r"),
                    )
                ],
            ),
            AuthoringAnnotationTrackSpec(
                id="interpretation",
                title="Interpretation",
                width_mm=24.0,
                annotations=[
                    AuthoringAnnotationMarkerSpec(
                        annotation_id=_binding_id(section_id, "marker-1"),
                        depth=1525.0,
                        shape=AuthoringAnnotationMarkerShape.DIAMOND,
                        color="#7c3aed",
                        label="Zone A",
                    )
                ],
            ),
        ],
    }


def _document(section_ids: list[str]) -> AuthoringDocumentSpec:
    """Build a report fixture for one, standard, or arbitrary section layouts."""
    return AuthoringDocumentSpec(
        name="cross-domain-acceptance",
        title="Cross-domain acceptance",
        subtitle="Canonical authoring fixture",
        header=AuthoringHeaderSpec(
            provider_name="Acceptance Lab",
            title="Cross-domain report",
            general_fields=[
                AuthoringHeaderFieldSpec(
                    slot_id="general.well",
                    key="well",
                    label="Well",
                    value=AuthoringReportValueSpec(value="ACCEPTANCE-1", provenance="user"),
                )
            ],
            detail=AuthoringHeaderDetailSpec(
                kind="open_hole",
                title="Open Hole Metadata",
                rows=[
                    AuthoringHeaderDetailRowSpec(
                        row_id="location",
                        label="Location",
                        values=[
                            {
                                "slot_id": "detail.location",
                                "value": {"value": "Test Basin", "provenance": "source"},
                            }
                        ],
                    )
                ],
            ),
        ),
        remarks=[{"remark_id": "notes", "title": "Notes", "text": "Acceptance fixture."}],
        sections=[_section(section_id) for section_id in section_ids],
    )


@pytest.mark.parametrize(
    "section_ids",
    [
        ["single"],
        ["main_pass", "repeat_pass"],
        ["main", "repeat", "interpretation", "quality_control"],
    ],
    ids=["one-section", "main-repeat", "arbitrary-multi-section"],
)
def test_cross_domain_fixture_supports_report_cardinalities(section_ids: list[str]) -> None:
    """Compose the same generic object families across supported report shapes."""
    document = _document(section_ids)
    rendered = authoring_document_to_render(document)

    assert [section.id for section in document.sections] == section_ids
    assert [track.kind for track in document.sections[0].tracks] == [
        "reference",
        "normal",
        "normal",
        "normal",
        "normal",
        "normal",
        "array",
        "annotation",
    ]
    assert (
        document.sections[0].tracks[2].grid.vertical_main_scale
        == AuthoringGridScaleKind.LOGARITHMIC
    )
    assert len(document.sections[0].tracks[5].bindings) == 2
    assert document.sections[0].tracks[5].bindings[0].channel == "CBL"
    assert document.sections[0].tracks[5].bindings[1].channel == "CBL"
    assert rendered.tracks[6].elements[0].profile.value == "vdl"


def test_cross_domain_fixture_preserves_explicit_presentation_over_defaults() -> None:
    """Explicit scales, grid behavior, colors, and line styles win over defaults."""
    document = _document(["main_pass"])
    binding_id = _binding_id("main_pass", "rdeep")
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main_pass",
                "tracks": [
                    {
                        "track_id": "resistivity",
                        "x_scale": {
                            "kind": "log",
                            "minimum": 0.5,
                            "maximum": 500.0,
                            "unit": "ohm.m",
                        },
                        "grid": {
                            "vertical_main_scale": "logarithmic",
                            "vertical_main_spacing_mode": "scale",
                        },
                        "bindings": [
                            {
                                "kind": "curve",
                                "binding_id": binding_id,
                                "scale": {
                                    "kind": "log",
                                    "minimum": 0.5,
                                    "maximum": 500.0,
                                    "unit": "ohm.m",
                                },
                                "style": {
                                    "color": "#00a6a6",
                                    "line_style": "--",
                                    "line_width": 1.7,
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    )
    resolution = resolve_authoring_context(
        intent,
        existing=document,
        defaults={
            "sections[main_pass].tracks[resistivity].x_scale": {
                "kind": "log",
                "minimum": 0.2,
                "maximum": 2000.0,
            },
            f"sections[main_pass].tracks[resistivity].bindings[{binding_id}].style.color": "black",
        },
        available_channels={"main_pass": ["RDEEP", "RMED", "RSH"]},
    )

    assert resolution.ready is True
    resolved_track = resolution.resolved_intent.sections[0].tracks[0]
    assert resolved_track.x_scale.minimum == 0.5
    assert resolved_track.x_scale.maximum == 500.0
    resolved_binding = resolved_track.bindings[0]
    assert resolved_binding.style.color == "#00a6a6"
    assert resolved_binding.style.line_style == "--"

    plan = reconcile_authoring(
        resolution.resolved_intent,
        existing=document,
        available_channels={"main_pass": ["RDEEP", "RMED", "RSH"]},
    )
    assert plan.ready is True
    binding_operation = next(
        operation for operation in plan.operations if operation.object_id == binding_id
    )
    assert binding_operation.payload["patch"]["style"]["color"] == "#00a6a6"
    assert binding_operation.payload["patch"]["style"]["line_style"] == "--"

    execution = execute_authoring_plan(AuthoringService(document), plan)
    assert execution.success is True
    assert all(outcome.postcondition_verified for outcome in execution.outcomes)


def test_cross_domain_resolution_blocks_missing_channels_and_incompatible_content() -> None:
    """Reject unsupported source/content combinations before any mutation is planned."""
    document = _document(["main_pass"])
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main_pass",
                "tracks": [
                    {
                        "track_id": "vdl",
                        "kind": "normal",
                        "bindings": [
                            {
                                "kind": "raster",
                                "binding_id": "main_pass.missing-array",
                                "channel": "MISSING_ARRAY",
                            }
                        ],
                    }
                ],
            }
        ]
    )
    resolution = resolve_authoring_context(
        intent,
        existing=document,
        available_channels={"main_pass": ["CBL", "VDL"]},
    )

    assert resolution.ready is False
    assert {issue.code for issue in resolution.issues} >= {
        "channel_missing",
        "content_track_incompatible",
    }
    with pytest.raises(ValidationError):
        AuthoringDocumentIntent.model_validate({"unsupported_request_field": True})


def test_agent_notebook_gates_are_credential_free_and_structurally_present() -> None:
    """Keep the published walkthrough and CBL stress fixture discoverable without execution."""
    repository_root = Path(__file__).parents[1]
    notebook_paths = {
        "las": repository_root / "examples/notebooks/user/agent_las_step_by_step.ipynb",
        "cbl": repository_root / "examples/notebooks/user/agent_cbl_log_example_from_prompt.ipynb",
    }

    for path in notebook_paths.values():
        payload = json.loads(path.read_text(encoding="utf-8"))
        source = "\n".join(
            "".join(cell.get("source", []))
            for cell in payload.get("cells", [])
            if cell.get("cell_type") in {"markdown", "code"}
        )
        assert "wellplot.agent" in source
        assert "display_authoring_result" in source
        assert "session.run" in source

    las_source = "\n".join(
        "".join(cell.get("source", []))
        for cell in json.loads(notebook_paths["las"].read_text(encoding="utf-8")).get("cells", [])
    )
    assert "create_project_session" in las_source
    assert "bootstrap_starter" in las_source
