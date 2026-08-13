###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""End-to-end acceptance coverage for natural-language intent compilation."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest
import yaml

from wellplot import authoring_document_to_render
from wellplot.agent import AuthoringRequest, AuthoringSession
from wellplot.agent.compilation import build_request_manifest
from wellplot.authoring import (
    authoring_document_from_mapping,
    authoring_document_to_logfile_mapping,
    authoring_document_to_yaml,
    load_authoring_document,
)
from wellplot.mcp import service as mcp_service
from wellplot.model import AuthoringDocumentSpec

_SOURCE_PATH = "sources/main.las"
_FAMILY_SCOPES = {
    "report": "report",
    "header": "report",
    "page": "report",
    "output": "report",
    "depth": "report",
    "remarks": "report",
    "section": "structure",
    "track": "structure",
    "curve_binding": "scalar",
    "fill": "scalar",
    "raster_binding": "raster",
    "annotation": "annotation",
}


def _document(*, with_header: bool = False) -> AuthoringDocumentSpec:
    """Build the reusable existing report used by compiler acceptance cases."""
    document = AuthoringDocumentSpec(
        name="compiler-acceptance",
        title="Compiler acceptance",
        sections=[
            {
                "id": "main",
                "title": "Main",
                "data_source": {
                    "source_path": _SOURCE_PATH,
                    "source_format": "las",
                },
                "tracks": [
                    {
                        "id": "gr_sp",
                        "title": "GR/SP",
                        "kind": "normal",
                        "width_mm": 28.0,
                        "bindings": [
                            {
                                "kind": "curve",
                                "binding_id": "main.gr_sp.gr.1",
                                "channel": "GR",
                                "label": "Gamma Ray",
                            }
                        ],
                    },
                    {
                        "id": "depth",
                        "title": "Depth",
                        "kind": "reference",
                        "width_mm": 16.0,
                    },
                ],
            }
        ],
    )
    if with_header:
        document.header = {
            "title": "Acceptance header",
            "general_fields": [
                {
                    "slot_id": "general.well",
                    "key": "well",
                    "label": "Well",
                    "aliases": ["well name"],
                }
            ],
        }
    return document


def _channels(*, ambiguous_sp: bool = False) -> list[dict[str, object]]:
    """Return inspected scalar and raster source channels for the fixture."""
    channels: list[dict[str, object]] = [
        {"mnemonic": "GR", "kind": "scalar", "value_unit": "gAPI"},
        {"mnemonic": "ILD", "kind": "scalar", "value_unit": "ohm.m"},
        {"mnemonic": "ILM", "kind": "scalar", "value_unit": "ohm.m"},
        {"mnemonic": "MSFL", "kind": "scalar", "value_unit": "ohm.m"},
        {"mnemonic": "SENSOR_X", "kind": "scalar", "value_unit": "arb"},
        {
            "mnemonic": "WAVE_X",
            "kind": "array",
            "value_unit": "mV",
            "value_shape": [10, 16],
        },
    ]
    if ambiguous_sp:
        channels.extend(
            [
                {"mnemonic": "SP_A", "kind": "scalar", "aliases": ["SP"]},
                {"mnemonic": "SP_B", "kind": "scalar", "aliases": ["SP"]},
            ]
        )
    else:
        channels.append({"mnemonic": "SP", "kind": "scalar", "value_unit": "mV"})
    return channels


class _AcceptanceRuntime:
    """Stateful MCP runtime double that persists canonical documents to disk."""

    def __init__(
        self,
        root: Path,
        *,
        document: AuthoringDocumentSpec,
        channels: list[dict[str, object]],
    ) -> None:
        self.server_root = root
        self.document = document
        self.channels = channels
        self.session: _AcceptanceMcpSession | None = None

    @asynccontextmanager
    async def open_session(self) -> object:
        """Yield a stateful fake MCP session for one authoring request."""
        self.session = _AcceptanceMcpSession(self)
        yield self.session

    @staticmethod
    def build_tool_definitions(**_: object) -> list[object]:
        """Return no tools because compiler stages own their definitions."""
        return []

    @staticmethod
    def prompt_text(_: object) -> str:
        """Return an unused prompt value for the desired-state route."""
        return ""

    @staticmethod
    def image_bytes(result: object) -> bytes:
        """Extract deterministic preview bytes from the local MCP double."""
        return bytes(result.content[0].data)

    @staticmethod
    def tool_result_payload(result: object) -> dict[str, object]:
        """Normalize fake MCP structured content for the agent core."""
        return {"structured": getattr(result, "structuredContent", {})}


class _AcceptanceMcpSession:
    """Implement the deterministic MCP calls used by desired-state workflows."""

    def __init__(self, runtime: _AcceptanceRuntime) -> None:
        self.runtime = runtime
        self.tool_calls: list[tuple[str, dict[str, object]]] = []

    async def get_prompt(self, _: str, __: dict[str, object]) -> object:
        """Reject legacy provider prompt routing in compiler acceptance tests."""
        raise AssertionError("compiler acceptance used the legacy provider prompt")

    async def list_tools(self) -> object:
        """Reject legacy tool discovery in compiler acceptance tests."""
        raise AssertionError("compiler acceptance listed legacy provider tools")

    def _path(self, value: object) -> Path:
        return self.runtime.server_root / str(value)

    def _loaded(self, logfile_path: object) -> AuthoringDocumentSpec:
        return load_authoring_document(
            self._path(logfile_path),
            allowed_root=self.runtime.server_root,
        )

    def _summary(self, logfile_path: object) -> dict[str, object]:
        document = self._loaded(logfile_path)
        return {
            "has_heading": document.header is not None,
            "has_remarks": bool(document.remarks),
            "section_ids": [section.id for section in document.sections],
            "sections": [
                {
                    "id": section.id,
                    "title": section.title,
                    "track_ids": [track.id for track in section.tracks],
                    "track_kinds": [track.kind for track in section.tracks],
                    "source_path": _SOURCE_PATH,
                    "source_format": "las",
                }
                for section in document.sections
            ],
        }

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        """Persist documents and route header tools to their real service functions."""
        self.tool_calls.append((name, dict(arguments)))
        logfile_path = arguments.get("logfile_path", "")
        if name == "create_logfile_draft":
            output_path = self._path(arguments["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            source_path = output_path.parent / _SOURCE_PATH
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text(
                """~Version Information
 VERS.                  2.0 : CWLS log ASCII Standard
 WRAP.                  NO  : One line per depth step
~Well Information
 STRT.FT                 0.0 : Start depth
 STOP.FT                10.0 : Stop depth
 STEP.FT                 1.0 : Step
 NULL.                -999.25 : Null value
~Curve Information
 DEPT.FT                      : Depth
 GR.API                       : Gamma Ray
~ASCII
 0.0 50.0
 1.0 51.0
 2.0 52.0
 3.0 53.0
 4.0 54.0
 5.0 55.0
 6.0 56.0
 7.0 57.0
 8.0 58.0
 9.0 59.0
 10.0 60.0
""",
                encoding="utf-8",
            )
            output_path.write_text(
                yaml.safe_dump(
                    authoring_document_to_logfile_mapping(self.runtime.document),
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            return SimpleNamespace(
                structuredContent={
                    "output_path": str(output_path),
                    "section_ids": [section.id for section in self.runtime.document.sections],
                }
            )
        if name == "save_authoring_document":
            output_path = self._path(arguments["output_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            document = authoring_document_from_mapping(arguments["document"])
            output_path.write_text(authoring_document_to_yaml(document) or "", encoding="utf-8")
            return SimpleNamespace(structuredContent={"output_path": str(output_path)})
        if name == "summarize_logfile_draft":
            return SimpleNamespace(structuredContent=self._summary(logfile_path))
        if name == "inspect_logfile":
            return SimpleNamespace(structuredContent=self._summary(logfile_path))
        if name == "inspect_data_source":
            return SimpleNamespace(
                structuredContent={
                    "source_path": _SOURCE_PATH,
                    "source_format_detected": "las",
                    "dataset_name": "Acceptance source",
                    "index": {"depth_unit": "ft", "sample_count": 10},
                    "channels": self.runtime.channels,
                    "metadata_keys": [],
                    "warnings": [],
                }
            )
        if name == "inspect_heading_slots":
            return SimpleNamespace(
                structuredContent=asdict(
                    mcp_service.inspect_heading_slots(
                        logfile_path=str(self._path(logfile_path)),
                        root=self.runtime.server_root,
                    )
                )
            )
        if name == "parse_key_value_text":
            return SimpleNamespace(
                structuredContent=asdict(
                    mcp_service.parse_key_value_text(
                        str(arguments["source_text"]),
                        format_hint=str(arguments.get("format_hint", "auto")),
                    )
                )
            )
        if name == "preview_header_mapping":
            return SimpleNamespace(
                structuredContent=asdict(
                    mcp_service.preview_header_mapping(
                        str(self._path(logfile_path)),
                        values=dict(arguments["values"]),
                        overwrite_policy=str(arguments.get("overwrite_policy", "fill_empty")),
                        root=self.runtime.server_root,
                    )
                )
            )
        if name == "apply_header_values":
            return SimpleNamespace(
                structuredContent=asdict(
                    mcp_service.apply_header_values(
                        str(self._path(logfile_path)),
                        values=dict(arguments["values"]),
                        overwrite_policy=str(arguments.get("overwrite_policy", "fill_empty")),
                        root=self.runtime.server_root,
                    )
                )
            )
        if name == "validate_logfile":
            return SimpleNamespace(structuredContent={"valid": True})
        if name == "summarize_logfile_changes":
            return SimpleNamespace(structuredContent={"summary_lines": ["Updated draft."]})
        if name in {"preview_logfile_png", "preview_section_png"}:
            return SimpleNamespace(content=[SimpleNamespace(data=b"preview")])
        raise AssertionError(f"Unexpected MCP tool: {name}")


class _RecordedCompilerBackend:
    """Recorded provider compiler submissions for one natural-language request."""

    provider = "fixture"
    model = "fixture-model"
    credential_source = "fixture"
    supports_desired_state = True

    def __init__(
        self,
        *,
        request_text: str,
        inventory: list[tuple[str, str]],
        fragments: dict[str, dict[str, object]],
    ) -> None:
        self.manifest = build_request_manifest(request_text)
        if len(inventory) != len(self.manifest.items):
            raise ValueError("Recorded inventory must cover every request item.")
        self.inventory = inventory
        self.fragments = fragments
        self.tool_names: list[str] = []

    async def run_authoring(self, **kwargs: object) -> object:
        """Submit exact recorded inventory and scoped canonical fragments."""
        tool_name = str(kwargs["required_tool_name"])
        tool = kwargs["tool_definitions"][0]
        assert tool.name == tool_name
        self.tool_names.append(tool_name)
        tool_caller = kwargs["tool_caller"]
        if tool_name == "submit_request_inventory":
            response = await tool_caller(
                tool_name,
                {
                    "items": [
                        {
                            "request_item_id": item.item_id,
                            "status": "preserved" if action == "preserve" else "mapped",
                            "action": action,
                            "object_family": family,
                            "target": item.text,
                        }
                        for item, (family, action) in zip(
                            self.manifest.items,
                            self.inventory,
                            strict=True,
                        )
                    ]
                },
            )
            assert response["accepted"] is True
            return SimpleNamespace(final_text="Inventoried request.", tool_trace=())

        scope = tool_name.removeprefix("submit_").removesuffix("_intent")
        fragment = self.fragments.get(scope, {})
        scope_items = [
            (item, action)
            for item, (family, action) in zip(
                self.manifest.items,
                self.inventory,
                strict=True,
            )
            if _FAMILY_SCOPES[family] == scope
        ]
        response = await tool_caller(
            tool_name,
            {
                "intent": fragment,
                "coverage": [
                    {
                        "unit_id": f"unit-{item.item_id}",
                        "status": "preserved" if action == "preserve" else "mapped",
                    }
                    for item, action in scope_items
                ],
            },
        )
        assert response["accepted"] is True
        return SimpleNamespace(final_text=f"Submitted {scope} intent.", tool_trace=())


def _run(
    tmp_path: Path,
    *,
    goal: str,
    inventory: list[tuple[str, str]],
    fragments: dict[str, dict[str, object]],
    channels: list[dict[str, object]] | None = None,
    document: AuthoringDocumentSpec | None = None,
) -> tuple[object, _AcceptanceRuntime, _RecordedCompilerBackend]:
    """Run one recorded natural-language compilation through canonical persistence."""
    backend = _RecordedCompilerBackend(
        request_text=goal,
        inventory=inventory,
        fragments=fragments,
    )
    runtime = _AcceptanceRuntime(
        tmp_path,
        document=document or _document(),
        channels=channels or _channels(),
    )
    result = anyio.run(
        AuthoringSession(backend=backend, runtime=runtime).run_request,
        AuthoringRequest(
            goal=goal,
            output_logfile="workspace/compiler.log.yaml",
            example_id="compiler-acceptance",
        ),
    )
    return result, runtime, backend


def _saved(runtime: _AcceptanceRuntime) -> AuthoringDocumentSpec:
    """Read the final document through the public canonical YAML loader."""
    return load_authoring_document(
        runtime.server_root / "workspace/compiler.log.yaml",
        allowed_root=runtime.server_root,
    )


def _track(document: AuthoringDocumentSpec, track_id: str) -> object:
    """Return one track from the single acceptance section."""
    return next(track for track in document.sections[0].tracks if track.id == track_id)


def _assert_successful_readback(result: object, runtime: _AcceptanceRuntime) -> None:
    """Assert persistence and render conversion rather than tool-call activity."""
    assert result.plan is not None
    assert result.plan.blocked is False, result.plan.blocked_reasons
    assert result.phase_summaries
    assert all(phase.status == "completed" for phase in result.phase_summaries)
    assert result.validation["valid"] is True
    assert any(
        name == "save_authoring_document"
        and arguments["output_path"] == "workspace/compiler.log.yaml"
        for name, arguments in runtime.session.tool_calls
    )
    assert authoring_document_to_render(_saved(runtime))


def test_compiler_adds_sp_with_explicit_scale_and_style(tmp_path: Path) -> None:
    """Compile an SP request into one existing GR/SP track and persist its style."""
    goal = """
        Revise the existing draft.

        - Add SP to the existing GR/SP track with a scale from -80 to 20 mV.
        - Render SP as a blue dashed line with width 1.25.
    """
    result, runtime, backend = _run(
        tmp_path,
        goal=goal,
        inventory=[
            ("report", "preserve"),
            ("curve_binding", "add"),
            ("curve_binding", "update"),
        ],
        fragments={
            "scalar": {
                "curve_bindings": [
                    {
                        "kind": "curve",
                        "binding_id": "main.gr_sp.sp.1",
                        "section_id": "main",
                        "track_id": "gr_sp",
                        "channel": "SP",
                        "label": "Spontaneous Potential",
                        "scale": {"minimum": -80.0, "maximum": 20.0, "unit": "mV"},
                        "style": {
                            "color": "blue",
                            "line_style": "--",
                            "line_width": 1.25,
                        },
                    }
                ]
            }
        },
    )

    _assert_successful_readback(result, runtime)
    assert backend.tool_names == [
        "submit_request_inventory",
        "submit_report_intent",
        "submit_scalar_intent",
    ]
    binding = next(
        binding for binding in _track(_saved(runtime), "gr_sp").bindings if binding.channel == "SP"
    )
    assert binding.scale.minimum == -80.0
    assert binding.scale.maximum == 20.0
    assert binding.style.color == "blue"
    assert binding.style.line_style == "--"
    assert binding.style.line_width == 1.25


def test_compiler_creates_resistivity_after_depth_with_log_grid(tmp_path: Path) -> None:
    """Compile a generic triple-combo resistivity request through full persistence."""
    goal = """
        Revise the existing draft.

        - Add one resistivity track after the depth track.
        - Use a logarithmic scale from 0.2 to 2000 ohm.m with logarithmic divisions.
        - Bind the deep, medium, and shallow resistivity curves that are available.
        - Keep the deepest resistivity curve visually strongest.
    """
    scale = {"kind": "log", "minimum": 0.2, "maximum": 2000.0, "unit": "ohm.m"}
    result, runtime, _ = _run(
        tmp_path,
        goal=goal,
        inventory=[
            ("report", "preserve"),
            ("track", "add"),
            ("track", "update"),
            ("curve_binding", "add"),
            ("curve_binding", "update"),
        ],
        fragments={
            "structure": {
                "sections": [
                    {
                        "section_id": "main",
                        "tracks": [
                            {
                                "track_id": "resistivity",
                                "section_id": "main",
                                "title": "Resistivity",
                                "kind": "normal",
                                "width_mm": 32.0,
                                "x_scale": scale,
                                "grid": {
                                    "vertical_main_scale": "logarithmic",
                                    "vertical_main_spacing_mode": "scale",
                                    "vertical_secondary_scale": "logarithmic",
                                    "vertical_secondary_spacing_mode": "scale",
                                },
                            }
                        ],
                    }
                ]
            },
            "scalar": {
                "curve_bindings": [
                    {
                        "kind": "curve",
                        "binding_id": f"main.resistivity.{channel}.1",
                        "section_id": "main",
                        "track_id": "resistivity",
                        "channel": channel,
                        "scale": scale,
                        "style": style,
                    }
                    for channel, style in (
                        ("ILD", {"color": "black", "line_width": 1.4}),
                        ("ILM", {"color": "green", "line_width": 1.0}),
                        ("MSFL", {"color": "red", "line_width": 0.8}),
                    )
                ]
            },
        },
    )

    _assert_successful_readback(result, runtime)
    document = _saved(runtime)
    assert [track.id for track in document.sections[0].tracks] == ["gr_sp", "depth", "resistivity"]
    track = _track(document, "resistivity")
    assert track.x_scale.kind == "log"
    assert (track.x_scale.minimum, track.x_scale.maximum, track.x_scale.unit) == (
        0.2,
        2000.0,
        "ohm.m",
    )
    assert track.grid.vertical_main_scale == "logarithmic"
    bindings = {binding.channel: binding for binding in track.bindings}
    assert set(bindings) == {"ILD", "ILM", "MSFL"}
    assert bindings["ILD"].style.line_width > bindings["ILM"].style.line_width
    assert bindings["ILD"].style.line_width > bindings["MSFL"].style.line_width


def test_compiler_creates_uncatalogued_scalar_track(tmp_path: Path) -> None:
    """Allow inspected scalar channels that have no curated family default."""
    goal = """
        Revise the existing draft.

        - Add a normal Custom Sensor track after depth.
        - Bind the available SENSOR_X curve to that track.
    """
    result, runtime, _ = _run(
        tmp_path,
        goal=goal,
        inventory=[("report", "preserve"), ("track", "add"), ("curve_binding", "add")],
        fragments={
            "structure": {
                "sections": [
                    {
                        "section_id": "main",
                        "tracks": [
                            {
                                "track_id": "custom_sensor",
                                "section_id": "main",
                                "title": "Custom Sensor",
                                "kind": "normal",
                                "width_mm": 28.0,
                            }
                        ],
                    }
                ]
            },
            "scalar": {
                "curve_bindings": [
                    {
                        "kind": "curve",
                        "binding_id": "main.custom_sensor.sensor_x.1",
                        "section_id": "main",
                        "track_id": "custom_sensor",
                        "channel": "SENSOR_X",
                    }
                ]
            },
        },
    )

    _assert_successful_readback(result, runtime)
    track = _track(_saved(runtime), "custom_sensor")
    assert track.kind == "normal"
    assert track.bindings[0].channel == "SENSOR_X"


def test_compiler_creates_array_track_and_binds_raster(tmp_path: Path) -> None:
    """Compile an array request without requiring a packet-specific scaffold."""
    goal = """
        Revise the existing draft.

        - Add an Array Waveform track after depth.
        - Bind the available WAVE_X array channel as a gray raster.
    """
    result, runtime, _ = _run(
        tmp_path,
        goal=goal,
        inventory=[("report", "preserve"), ("track", "add"), ("raster_binding", "add")],
        fragments={
            "structure": {
                "sections": [
                    {
                        "section_id": "main",
                        "tracks": [
                            {
                                "track_id": "waveform",
                                "section_id": "main",
                                "title": "Array Waveform",
                                "kind": "array",
                                "width_mm": 40.0,
                            }
                        ],
                    }
                ]
            },
            "raster": {
                "raster_bindings": [
                    {
                        "kind": "raster",
                        "binding_id": "main.waveform.wave_x.1",
                        "section_id": "main",
                        "track_id": "waveform",
                        "channel": "WAVE_X",
                        "label": "Waveform",
                        "style": {"colormap": "gray"},
                    }
                ]
            },
        },
    )

    _assert_successful_readback(result, runtime)
    track = _track(_saved(runtime), "waveform")
    assert track.kind == "array"
    assert track.bindings[0].channel == "WAVE_X"
    assert track.bindings[0].style.colormap == "gray"


def test_compiler_explicit_style_overrides_existing_family_default(tmp_path: Path) -> None:
    """Keep requested style fields instead of replacing them with family defaults."""
    goal = """
        Revise the existing draft.

        - Change the GR curve to dark green dotted with line width 1.4.
    """
    result, runtime, _ = _run(
        tmp_path,
        goal=goal,
        inventory=[("report", "preserve"), ("curve_binding", "update")],
        fragments={
            "scalar": {
                "curve_bindings": [
                    {
                        "kind": "curve",
                        "binding_id": "main.gr_sp.gr.1",
                        "section_id": "main",
                        "track_id": "gr_sp",
                        "channel": "GR",
                        "style": {
                            "color": "#14532d",
                            "line_style": ":",
                            "line_width": 1.4,
                        },
                    }
                ]
            }
        },
    )

    _assert_successful_readback(result, runtime)
    binding = _track(_saved(runtime), "gr_sp").bindings[0]
    assert binding.style.color == "#14532d"
    assert binding.style.line_style == ":"
    assert binding.style.line_width == 1.4


def test_header_language_path_persists_matching_slot_without_provider(tmp_path: Path) -> None:
    """Keep narrow header language on the deterministic mapping route."""
    runtime = _AcceptanceRuntime(
        tmp_path,
        document=_document(with_header=True),
        channels=_channels(),
    )
    backend = SimpleNamespace(
        provider="fixture",
        model="fixture-model",
        credential_source="fixture",
        supports_desired_state=True,
    )
    result = anyio.run(
        AuthoringSession(backend=backend, runtime=runtime).run_request,
        AuthoringRequest(
            goal="""
                Fill the following header fields with the following values:
                - Well: Acceptance-42
            """,
            output_logfile="workspace/compiler.log.yaml",
            example_id="compiler-acceptance",
        ),
    )

    assert result.plan is None
    assert [name for name, _ in runtime.session.tool_calls][:5] == [
        "create_logfile_draft",
        "inspect_heading_slots",
        "parse_key_value_text",
        "preview_header_mapping",
        "apply_header_values",
    ]
    assert _saved(runtime).header.general_fields[0].value.value == "Acceptance-42"


@pytest.mark.parametrize(
    ("channel", "channels", "expected_reason"),
    [
        ("NOT_AVAILABLE", _channels(), "No source channel matches 'NOT_AVAILABLE'."),
        ("SP", _channels(ambiguous_sp=True), "Multiple source channels match 'SP'."),
    ],
    ids=["missing-channel", "ambiguous-channel"],
)
def test_compiler_blocks_unresolved_channel_before_mutation(
    tmp_path: Path,
    channel: str,
    channels: list[dict[str, object]],
    expected_reason: str,
) -> None:
    """Stop at deterministic context resolution and leave the canonical draft intact."""
    goal = f"""
        Revise the existing draft.

        - Add {channel} to the GR/SP track.
    """
    result, runtime, backend = _run(
        tmp_path,
        goal=goal,
        inventory=[("report", "preserve"), ("curve_binding", "add")],
        channels=channels,
        fragments={
            "scalar": {
                "curve_bindings": [
                    {
                        "kind": "curve",
                        "binding_id": f"main.gr_sp.{channel.lower()}.1",
                        "section_id": "main",
                        "track_id": "gr_sp",
                        "channel": channel,
                    }
                ]
            }
        },
    )

    assert backend.tool_names == [
        "submit_request_inventory",
        "submit_report_intent",
        "submit_scalar_intent",
    ]
    assert result.plan is not None
    assert result.plan.blocked is True
    assert expected_reason in result.plan.blocked_reasons
    assert result.report_facts["extraction"]["status"] == "submitted"
    assert not any(name == "save_authoring_document" for name, _ in runtime.session.tool_calls)
    assert [binding.channel for binding in _track(_saved(runtime), "gr_sp").bindings] == ["GR"]
