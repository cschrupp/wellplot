"""Open-world acceptance tests for provider-neutral authoring."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest

from wellplot.agent import AuthoringSession
from wellplot.agent.compilation import build_request_manifest
from wellplot.authoring_context import AuthoringContextSnapshot
from wellplot.authoring_executor import execute_authoring_plan
from wellplot.authoring_service import AuthoringService
from wellplot.model import AuthoringDocumentIntent, AuthoringDocumentSpec


def _minimal_document() -> AuthoringDocumentSpec:
    """Build the smallest existing report that can receive new tracks."""
    return AuthoringDocumentSpec(
        name="open-world-acceptance",
        title="Open-world acceptance",
        sections=[
            {
                "id": "main",
                "title": "Main",
                "tracks": [
                    {
                        "id": "depth",
                        "title": "Depth",
                        "kind": "reference",
                        "width_mm": 16.0,
                    }
                ],
            }
        ],
    )


def _session() -> AuthoringSession:
    """Build a provider-neutral planner for deterministic acceptance tests."""
    backend = SimpleNamespace(
        provider="fixture",
        model="fixture-model",
        credential_source="fixture",
    )
    runtime = SimpleNamespace(server_root=Path("."))
    return AuthoringSession(backend=backend, runtime=runtime)


def _plan_and_execute(
    intent: AuthoringDocumentIntent,
    available_channels: dict[str, list[object]],
) -> tuple[object, AuthoringDocumentSpec]:
    """Compile one typed intent, execute it, and return its read-back document."""
    document = _minimal_document()
    plan = _session().plan(
        text="Build the requested cross-domain well-log objects.",
        desired_state=intent,
        existing=document,
        available_channels=available_channels,
    )
    assert plan.blocked is False, plan.blocked_reasons
    assert plan.reconciliation_plan is not None

    execution = execute_authoring_plan(
        AuthoringService(document),
        plan.reconciliation_plan,
    )
    assert execution.success, execution.errors
    assert all(outcome.postcondition_verified for outcome in execution.outcomes)
    assert execution.phase_summaries
    return plan, execution.document


def _track(document: AuthoringDocumentSpec, track_id: str) -> object:
    """Return one read-back track by stable id."""
    section = next(section for section in document.sections if section.id == "main")
    return next(track for track in section.tracks if track.id == track_id)


class _ResistivityExtractionBackend:
    """Submit a natural-language resistivity request through the provider seam."""

    provider = "fixture"
    model = "fixture-model"
    credential_source = "fixture"

    def __init__(self, request_text: str) -> None:
        self.manifest = build_request_manifest(request_text)
        self.tool_names: list[str] = []

    async def run_authoring(self, **kwargs: object) -> object:
        """Submit one provider-shaped intent and complete request coverage."""
        tool_name = kwargs["tool_definitions"][0].name
        self.tool_names.append(tool_name)
        tool_caller = kwargs["tool_caller"]
        structure_ids = {item.item_id for item in self.manifest.items[:3]}
        scalar_ids = {item.item_id for item in self.manifest.items[3:]}
        if tool_name == "submit_request_inventory":
            response = await tool_caller(
                tool_name,
                {
                    "items": [
                        {
                            "request_item_id": item.item_id,
                            "status": "mapped",
                            "action": "add" if item.item_id in structure_ids else "update",
                            "object_family": (
                                "track" if item.item_id in structure_ids else "curve_binding"
                            ),
                            "target": item.text,
                        }
                        for item in self.manifest.items
                    ]
                },
            )
            assert response["accepted"] is True
            return SimpleNamespace(final_text="Inventoried request.", tool_trace=())
        if tool_name == "submit_structure_intent":
            intent = {
                "sections": [
                    {
                        "section_id": "main",
                        "tracks": [
                            {
                                "track_id": "resistivity",
                                "section_id": "main",
                                "x_scale": {
                                    "kind": "log",
                                    "minimum": 0.2,
                                    "maximum": 2000.0,
                                    "unit": "ohm.m",
                                },
                            }
                        ],
                    }
                ]
            }
            request_ids = structure_ids
        else:
            assert tool_name == "submit_scalar_intent"
            assert '"compiled_structure"' in str(kwargs["initial_user_message"])
            assert '"track_id": "resistivity"' in str(kwargs["initial_user_message"])
            intent = {
                "curve_bindings": [
                    {
                        "kind": "curve",
                        "binding_id": f"main.resistivity.{channel}.1",
                        "section_id": "main",
                        "track_id": "resistivity",
                        "channel": channel,
                    }
                    for channel in ("ILD", "ILM", "MSFL")
                ]
            }
            request_ids = scalar_ids
        response = await tool_caller(
            tool_name,
            {
                "intent": intent,
                "coverage": [
                    {
                        "request_item_id": item.item_id,
                        "status": "mapped",
                        "intent_paths": [
                            (
                                "sections[main].tracks[resistivity]"
                                if item.item_id in structure_ids
                                else "curve_bindings"
                            )
                        ],
                    }
                    for item in self.manifest.items
                    if item.item_id in request_ids
                ],
            },
        )
        assert response["accepted"] is True
        return SimpleNamespace(final_text="Submitted typed intent.", tool_trace=())


def test_provider_submission_reaches_generic_resistivity_operation_payload() -> None:
    """Verify the natural-language extraction seam before claiming notebook success."""
    request_text = """
        Revise the existing draft.

        - Add one resistivity track after the depth track.
        - Use a logarithmic scale from 0.2 to 2000 ohm.m.
        - Bind the deep, medium, and shallow resistivity curves that are available.
        - Keep the deepest resistivity curve visually strongest.
    """
    backend = _ResistivityExtractionBackend(request_text)
    session = AuthoringSession(backend=backend, runtime=SimpleNamespace(server_root=Path(".")))
    existing = _minimal_document()
    context = AuthoringContextSnapshot(draft_logfile="draft.log.yaml")

    result, intent = anyio.run(
        partial(
            session._extract_desired_state,
            request_text=request_text,
            draft_logfile="draft.log.yaml",
            existing=existing,
            context_snapshot=context,
            max_rounds=3,
        )
    )

    assert intent is not None
    assert backend.tool_names == [
        "submit_request_inventory",
        "submit_structure_intent",
        "submit_scalar_intent",
    ]
    assert result.report_facts["submitted_intent"] == intent.model_dump(
        mode="json", exclude_unset=True
    )
    plan = session.plan(
        text=request_text,
        desired_state=intent,
        existing=existing,
        available_channels={"main": ["ILD", "ILM", "MSFL"]},
    )
    assert plan.blocked is False, plan.blocked_reasons
    track_operation = next(
        operation
        for operation in plan.operation_payloads
        if operation["object_kind"] == "track" and operation["object_id"] == "resistivity"
    )
    assert track_operation["payload"]["object"]["width_mm"] == 32.0
    assert (
        plan.applied_defaults_provenance["sections[main].tracks[resistivity].width_mm"]
        == "style_preset:triple_combo_resistivity"
    )


def test_open_world_resistivity_creation_uses_generic_reconciliation() -> None:
    """Create a triple-combo resistivity track without internal form fields."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "resistivity",
                        "bindings": [
                            {
                                "kind": "curve",
                                "binding_id": "main.resistivity.ild",
                                "channel": "ILD",
                            },
                            {
                                "kind": "curve",
                                "binding_id": "main.resistivity.ilm",
                                "channel": "ILM",
                            },
                            {
                                "kind": "curve",
                                "binding_id": "main.resistivity.msfl",
                                "channel": "MSFL",
                            },
                        ],
                    }
                ],
            }
        ]
    )

    plan, document = _plan_and_execute(
        intent,
        {"main": ["ILD", "ILM", "MSFL"]},
    )

    assert (
        plan.defaults_provenance["sections[main].tracks[resistivity].x_scale"]
        == "style_preset:triple_combo_resistivity"
    )
    section = document.sections[0]
    assert [track.id for track in section.tracks] == ["depth", "resistivity"]
    resistivity = _track(document, "resistivity")
    assert resistivity.kind == "normal"
    assert resistivity.title == "Resistivity"
    assert resistivity.width_mm == 32.0
    assert resistivity.x_scale is not None
    assert resistivity.x_scale.kind == "log"
    assert (resistivity.x_scale.minimum, resistivity.x_scale.maximum) == (0.2, 2000.0)
    assert [binding.channel for binding in resistivity.bindings] == ["ILD", "ILM", "MSFL"]
    assert resistivity.bindings[0].style.line_width > resistivity.bindings[1].style.line_width
    assert resistivity.bindings[1].style.line_width > resistivity.bindings[2].style.line_width


def test_open_world_creates_unknown_scalar_array_annotation_and_cbl_objects() -> None:
    """Use one generic typed path for uncatalogued and canonical content families."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "custom_sensor",
                        "bindings": [
                            {
                                "kind": "curve",
                                "binding_id": "main.custom_sensor.sensor",
                                "channel": "SENSOR_X",
                                "label": "Custom Sensor",
                                "style": {"color": "#005f73", "line_width": 1.4},
                            }
                        ],
                    },
                    {
                        "track_id": "waveform",
                        "bindings": [
                            {
                                "kind": "raster",
                                "binding_id": "main.waveform.vdl",
                                "channel": "VDL",
                            }
                        ],
                    },
                    {
                        "track_id": "markers",
                        "annotations": [
                            {
                                "annotation_id": "main.markers.zone-a",
                                "annotation": {
                                    "kind": "marker",
                                    "annotation_id": "main.markers.zone-a",
                                    "depth": 1750.0,
                                    "shape": "diamond",
                                    "color": "#b91c1c",
                                    "label": "Zone A",
                                },
                            }
                        ],
                    },
                    {
                        "track_id": "cbl",
                        "title": "CBL Amplitude",
                        "kind": "normal",
                        "width_mm": 36.0,
                        "bindings": [
                            {
                                "kind": "curve",
                                "binding_id": "main.cbl.1",
                                "channel": "CBL",
                                "scale": {"minimum": 0.0, "maximum": 100.0, "unit": "mV"},
                                "style": {"color": "black", "line_width": 0.75},
                            },
                            {
                                "kind": "curve",
                                "binding_id": "main.cbl.2",
                                "channel": "CBL",
                                "scale": {"minimum": 0.0, "maximum": 10.0, "unit": "mV"},
                                "style": {
                                    "color": "blue",
                                    "line_style": "--",
                                    "line_width": 0.65,
                                },
                            },
                        ],
                    },
                    {
                        "track_id": "vdl",
                        "bindings": [
                            {
                                "kind": "raster",
                                "binding_id": "main.vdl.raster",
                                "channel": "VDL",
                            }
                        ],
                    },
                ],
            }
        ]
    )

    plan, document = _plan_and_execute(
        intent,
        {"main": ["SENSOR_X", "CBL", {"mnemonic": "VDL", "kind": "array"}]},
    )

    assert any("Unmatched source channel(s)" in warning for warning in plan.warnings)
    custom_sensor = _track(document, "custom_sensor")
    assert (custom_sensor.kind, custom_sensor.width_mm) == ("normal", 28.0)
    assert custom_sensor.bindings[0].style.color == "#005f73"
    waveform = _track(document, "waveform")
    assert (waveform.kind, waveform.width_mm) == ("array", 28.0)
    assert waveform.bindings[0].profile.value == "vdl"
    markers = _track(document, "markers")
    assert (markers.kind, markers.width_mm) == ("annotation", 28.0)
    assert markers.annotations[0].label == "Zone A"
    cbl = _track(document, "cbl")
    assert [binding.channel for binding in cbl.bindings] == ["CBL", "CBL"]
    assert [binding.binding_id for binding in cbl.bindings] == ["main.cbl.1", "main.cbl.2"]
    assert cbl.bindings[1].style.line_style == "--"
    vdl = _track(document, "vdl")
    assert vdl.kind == "array"
    assert vdl.bindings[0].profile.value == "vdl"


def test_open_world_rejects_missing_incompatible_and_ambiguous_requests() -> None:
    """Keep unsupported source/content and ambiguous form choices fail-closed."""
    cases = [
        (
            AuthoringDocumentIntent(
                sections=[
                    {
                        "section_id": "main",
                        "tracks": [
                            {
                                "track_id": "missing",
                                "bindings": [
                                    {
                                        "kind": "curve",
                                        "binding_id": "main.missing.curve",
                                        "channel": "NOT_AVAILABLE",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            ),
            {"main": []},
            "channel_missing",
        ),
        (
            AuthoringDocumentIntent(
                sections=[
                    {
                        "section_id": "main",
                        "tracks": [
                            {
                                "track_id": "scalar",
                                "kind": "normal",
                                "title": "Scalar",
                                "width_mm": 28.0,
                                "bindings": [
                                    {
                                        "kind": "raster",
                                        "binding_id": "main.scalar.raster",
                                        "channel": "VDL",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            ),
            {"main": [{"mnemonic": "VDL", "kind": "array"}]},
            "content_track_incompatible",
        ),
        (
            AuthoringDocumentIntent(
                sections=[
                    {
                        "section_id": "main",
                        "tracks": [
                            {
                                "track_id": "cbl",
                                "bindings": [
                                    {
                                        "kind": "curve",
                                        "binding_id": "main.cbl.curve",
                                        "channel": "CBL",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            ),
            {"main": ["CBL"]},
            "track_create_incomplete",
        ),
    ]

    for intent, available_channels, issue_code in cases:
        plan = _session().plan(
            text="Build the requested object.",
            desired_state=intent,
            existing=_minimal_document(),
            available_channels=available_channels,
        )
        assert plan.blocked is True
        assert plan.reconciliation_plan is not None
        assert any(issue.code == issue_code for issue in plan.reconciliation_plan.issues)


@pytest.mark.parametrize("track_id", ["custom_sensor", "waveform", "markers"])
def test_open_world_generic_form_provenance_is_explicit(track_id: str) -> None:
    """Expose generic form provenance for non-family tracks."""
    children: dict[str, object] = {
        "custom_sensor": {
            "bindings": [{"kind": "curve", "binding_id": "sensor", "channel": "SENSOR_X"}]
        },
        "waveform": {"bindings": [{"kind": "raster", "binding_id": "wave", "channel": "WAVE_X"}]},
        "markers": {
            "annotations": [
                {
                    "annotation_id": "marker",
                    "annotation": {
                        "kind": "marker",
                        "annotation_id": "marker",
                        "depth": 100.0,
                    },
                }
            ]
        },
    }
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [{"track_id": track_id, **children[track_id]}],
            }
        ]
    )
    channels = {"main": ["SENSOR_X", {"mnemonic": "WAVE_X", "kind": "array"}]}

    plan = _session().plan(
        text="Build a generic track.",
        desired_state=intent,
        existing=_minimal_document(),
        available_channels=channels,
    )

    assert plan.blocked is False
    expected_form = (
        "array" if track_id == "waveform" else "annotation" if track_id == "markers" else "normal"
    )
    assert (
        plan.defaults_provenance[f"sections[main].tracks[{track_id}].kind"]
        == f"generic_form:{expected_form}"
    )
