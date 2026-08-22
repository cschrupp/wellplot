"""Acceptance tests for the compact stable-MCP provider loop."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from wellplot.agent.core import (
    STABLE_MCP_TOOL_NAMES,
    AuthoringRequest,
    AuthoringSession,
    AuthoringToolCall,
    FunctionToolDefinition,
    ProviderRunResult,
    _catalog_fallback_section_id,
    _catalog_fallback_tool_arguments,
    _normalize_scale_payload,
    _normalize_stable_tool_arguments,
    _resolve_requested_source_path,
    _resolved_authoring_value,
    _stable_postcondition_errors,
    _stable_scope_tool_names,
)
from wellplot.agent.stable_fallback import (
    build_catalog_fallback_plan,
    catalog_channel_candidates,
    fallback_plan_satisfied,
)
from wellplot.agent.tool_contract import stable_tool_profile
from wellplot.authoring import authoring_document_to_yaml
from wellplot.model.authoring import (
    AuthoringDocumentSpec,
    AuthoringHeaderFieldSpec,
    AuthoringHeaderSpec,
    AuthoringReportValueSpec,
    AuthoringSectionSpec,
    NormalTrackSpec,
)


def test_stable_postcondition_value_unwraps_typed_report_values() -> None:
    """Compare the literal value inside nested report slot models."""
    wrapped = SimpleNamespace(value=SimpleNamespace(value="Open Hole Quicklook"))

    assert _resolved_authoring_value(wrapped) == "Open Hole Quicklook"


def test_resolves_declared_source_basename(tmp_path: Path) -> None:
    """Resolve a shortened provider path from an unambiguous declared source."""
    source = tmp_path / "workspace" / "packet" / "CBL_Repeat.dlis"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")

    request = """
    Data Sources:
    - main: workspace/packet/CBL_Main.dlis
    - repeat: workspace/packet/CBL_Repeat.dlis
    """

    assert _resolve_requested_source_path(
        "CBL_Repeat.dlis",
        request_text=request,
        server_root=tmp_path,
    ) == "workspace/packet/CBL_Repeat.dlis"

    assert _resolve_requested_source_path(
        str(tmp_path / "CBL_Repeat.dlis"),
        request_text=request,
        server_root=tmp_path,
    ) == "workspace/packet/CBL_Repeat.dlis"


def test_preserves_ambiguous_source_basename(tmp_path: Path) -> None:
    """Do not guess when the same basename is declared more than once."""
    request = """
    Data Sources:
    - first: one/CBL.dlis
    - second: two/CBL.dlis
    """

    assert _resolve_requested_source_path(
        "CBL.dlis",
        request_text=request,
        server_root=tmp_path,
    ) == "CBL.dlis"


def test_stable_argument_normalizer_does_not_invent_payload_shapes() -> None:
    """Contract-invalid provider payloads remain invalid instead of being repaired by the host."""
    flat_remark = {
        "operation": "add",
        "title": "Notes",
        "lines": ["A note"],
    }
    assert _normalize_stable_tool_arguments("edit_remarks", flat_remark) == flat_remark

    nested_raster = {
        "operation": "update",
        "style": {
            "colormap": "gray_r",
            "colorbar": {"enabled": True, "label": "Amplitude"},
        },
    }
    assert _normalize_stable_tool_arguments("edit_raster_binding", nested_raster) == nested_raster


def test_stable_scale_arguments_use_canonical_bounds() -> None:
    """Normalize provider scale vocabulary before typed validation."""
    assert _normalize_scale_payload(
        {"kind": "linear", "domain": [-80, 20], "unit": "mV"}
    ) == {
        "kind": "linear",
        "minimum": -80,
        "maximum": 20,
    }


def test_catalog_source_inspection_uses_source_path_only() -> None:
    """Do not append a logfile target to source inspection requests."""
    assert _catalog_fallback_tool_arguments(
        "inspect_source",
        {"source_path": "workspace/input.las", "source_format": "las"},
        "workspace/draft.log.yaml",
    ) == {"source_path": "workspace/input.las", "source_format": "las"}
    assert _catalog_fallback_tool_arguments(
        "inspect_authoring",
        {"object_kind": "track"},
        "workspace/draft.log.yaml",
    ) == {
        "object_kind": "track",
        "logfile_path": "workspace/draft.log.yaml",
    }
    assert _catalog_fallback_tool_arguments(
        "inspect_source",
        {
            "source_path": "workspace/input.las",
            "logfile_path": "workspace/draft.log.yaml",
        },
        "workspace/draft.log.yaml",
    ) == {"source_path": "workspace/input.las"}


def test_stable_source_inspection_drops_conflicting_logfile_target() -> None:
    """Keep source inspection mutually exclusive when providers copy context."""
    assert _normalize_stable_tool_arguments(
        "inspect_source",
        {
            "source_path": "workspace/input.dlis",
            "logfile_path": "workspace/draft.log.yaml",
            "section_id": "repeat",
        },
    ) == {"source_path": "workspace/input.dlis"}


def test_catalog_fallback_does_not_implicitly_target_packet_sections() -> None:
    """Single-section recovery must not guess which section a packet means."""
    document = SimpleNamespace(
        sections=[SimpleNamespace(id="main_pass"), SimpleNamespace(id="repeat_pass")]
    )

    assert (
        _catalog_fallback_section_id(
            "Keep the section ids `main_pass` and `repeat_pass`.",
            document,
        )
        is None
    )
    assert (
        _catalog_fallback_section_id(
            "Add a resistivity track to section id `repeat_pass`.",
            document,
        )
        == "repeat_pass"
    )


def test_stable_scope_does_not_treat_header_depth_labels_as_page_settings() -> None:
    """Header labels such as ``Depth Driller`` must not widen the report scope."""
    scope = _stable_scope_tool_names(
        """
        Header Values:
        - Depth Driller: 4980 ft
        - Schlumberger Depth: TD not tagged
        """
    )

    assert scope == {"edit_header"}


def test_stable_scope_keeps_explicit_page_and_depth_axis_settings() -> None:
    """Narrower scope matching still exposes genuine document-settings requests."""
    scope = _stable_scope_tool_names(
        "Set the page orientation to landscape and the depth axis scale to 200."
    )

    assert scope == {"edit_report_settings"}


def test_stable_arguments_normalize_scale_and_style_aliases() -> None:
    """Normalize common provider aliases without weakening canonical validation."""
    normalized = _normalize_stable_tool_arguments(
        "edit_curve_binding",
        {
            "operation": "update",
            "scale": {"type": "logarithmic", "min": 0.2, "max": 2000},
            "style": {"stroke": "black", "stroke_width": 1.5, "dash": "--"},
        },
    )

    assert normalized["scale"] == {
        "kind": "logarithmic",
        "minimum": 0.2,
        "maximum": 2000,
    }
    assert normalized["style"] == {
        "color": "black",
        "line_width": 1.5,
        "line_style": "--",
    }


def test_catalog_fallback_plans_generic_resistivity_track() -> None:
    """Resolve a stalled resistivity request from catalogs and source channels."""
    goal = """
        Add one resistivity track after the depth track.
        Use a logarithmic scale from 0.2 to 2000 ohm.m.
        Bind the deep, medium, and shallow resistivity curves that are available.
    """
    document = {
        "sections": [
            {
                "id": "main",
                "tracks": [
                    {"id": "gr_sp", "title": "GR/SP", "kind": "normal", "bindings": []},
                    {"id": "depth", "title": "Depth", "kind": "reference", "bindings": []},
                ],
            }
        ]
    }

    assert "ILD" in catalog_channel_candidates(goal)
    plan = build_catalog_fallback_plan(
        goal,
        section_id="main",
        document=document,
        available_channels=["ILD", "ILM", "MSFL"],
    )

    assert plan is not None
    assert plan.family_id == "resistivity_log"
    assert plan.preset_id == "triple_combo_resistivity"
    assert plan.expected_channels == ("MSFL", "ILM", "ILD")
    assert plan.expected_scale == {"kind": "log", "min": 0.2, "max": 2000.0}
    assert [operation.tool_name for operation in plan.operations].count("edit_curve_binding") == 3
    assert plan.operations[-1].arguments["operation"] == "move"


def test_catalog_fallback_parses_scale_to_wording() -> None:
    """Honor the common ``change the scale to A to B`` request form."""
    plan = build_catalog_fallback_plan(
        """
        Change the Resistivity track scale to 0.2 to 20, along with all the curves scales
        in that track.
        """,
        section_id="main",
        document={
            "sections": [
                {
                    "id": "main",
                    "tracks": [
                        {
                            "id": "resistivity",
                            "title": "Resistivity",
                            "x_scale": {"kind": "log", "min": 0.2, "max": 2000.0},
                        }
                    ],
                }
            ]
        },
        available_channels=["ILD"],
    )

    assert plan is not None
    assert plan.expected_scale == {"kind": "log", "min": 0.2, "max": 20.0}
    set_scales = next(
        operation
        for operation in plan.operations
        if operation.tool_name == "edit_track"
        and operation.arguments.get("operation") == "set_scales"
    )
    assert set_scales.arguments["x_scale"] == plan.expected_scale
    assert set_scales.arguments["curve_scale"] == plan.expected_scale


def test_catalog_fallback_track_scale_does_not_rewrite_existing_curve_scales() -> None:
    """A track-axis request must leave existing curve scales independent."""
    plan = build_catalog_fallback_plan(
        "Change the Resistivity track scale to 0.2 to 20.",
        section_id="main",
        document={
            "sections": [
                {
                    "id": "main",
                    "tracks": [
                        {
                            "id": "resistivity",
                            "title": "Resistivity",
                            "x_scale": {"kind": "log", "min": 0.2, "max": 2000.0},
                            "bindings": [
                                {
                                    "channel": "ILD",
                                    "scale": {"kind": "log", "min": 0.2, "max": 2000.0},
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        available_channels=["ILD"],
    )

    assert plan is not None
    assert plan.expected_scale == {"kind": "log", "min": 0.2, "max": 20.0}
    assert [operation.tool_name for operation in plan.operations] == ["edit_track"]
    assert plan.operations[0].arguments["operation"] == "update"
    assert plan.operations[0].arguments["patch"] == {"x_scale": plan.expected_scale}


def test_catalog_fallback_curve_scale_request_leaves_track_axis_unchanged() -> None:
    """A curve-scale request must not change the shared track axis."""
    plan = build_catalog_fallback_plan(
        "Change all curves scales in the Resistivity track to 0.2 to 20.",
        section_id="main",
        document={
            "sections": [
                {
                    "id": "main",
                    "tracks": [
                        {
                            "id": "resistivity",
                            "title": "Resistivity",
                            "x_scale": {"kind": "log", "min": 0.2, "max": 2000.0},
                            "bindings": [
                                {
                                    "channel": "ILD",
                                    "binding_id": "resistivity.ild",
                                    "scale": {"kind": "log", "min": 0.2, "max": 2000.0},
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        available_channels=["ILD"],
    )

    assert plan is not None
    assert plan.expected_scale is None
    binding_operations = [
        operation for operation in plan.operations if operation.tool_name == "edit_curve_binding"
    ]
    assert len(binding_operations) == 1
    assert set(binding_operations[0].arguments["patch"]) == {"scale"}
    assert binding_operations[0].arguments["patch"]["scale"] == {
        "kind": "log",
        "min": 0.2,
        "max": 20.0,
    }


def test_catalog_fallback_does_not_guess_unknown_track_family() -> None:
    """Do not invent a family when no asset-backed catalog entry matches."""
    plan = build_catalog_fallback_plan(
        "Add one imaginary track and bind any available curves.",
        section_id="main",
        document={"sections": [{"id": "main", "tracks": []}]},
        available_channels=["GR"],
    )

    assert plan is None


def test_open_world_track_plan_uses_request_name_and_available_channels() -> None:
    """Build an arbitrary narrow track without borrowing another family preset."""
    goal = """
        Add one narrow QC track after the porosity track.
        Bind supporting curves such as CALI, PEF, and DRHO only when they are available.
        Keep the track readable and lighter-weight than the main interpretation tracks.
    """
    document = {
        "sections": [
            {
                "id": "main",
                "tracks": [
                    {"id": "gr_sp", "title": "GR/SP"},
                    {"id": "depth", "title": "Depth"},
                    {"id": "porosity", "title": "Porosity Overlay"},
                ],
            }
        ]
    }

    assert catalog_channel_candidates(goal) == ()
    plan = build_catalog_fallback_plan(
        goal,
        section_id="main",
        document=document,
        available_channels=["CALI", "PEF", "DRHO", "RHOB", "NPHI"],
    )

    assert plan is not None
    assert plan.family_id is None
    assert plan.preset_id is None
    assert plan.track_id == "qc"
    assert plan.expected_channels == ("CALI", "PEF", "DRHO")
    add_track = next(
        operation
        for operation in plan.operations
        if operation.tool_name == "edit_track" and operation.arguments.get("operation") == "add"
    )
    assert add_track.arguments["title"] == "QC"
    assert add_track.arguments["kind"] == "normal"
    assert add_track.arguments["width_mm"] == 14.0
    binding_tool = "edit_curve_binding"
    binding_operations = [
        operation for operation in plan.operations if operation.tool_name == binding_tool
    ]
    assert [operation.arguments["channel"] for operation in binding_operations] == [
        "CALI",
        "PEF",
        "DRHO",
    ]
    assert [operation.arguments["style"] for operation in binding_operations] == [
        {"line_width": 0.8}
    ] * len(binding_operations)
    move_track = next(
        operation
        for operation in plan.operations
        if operation.tool_name == "edit_track" and operation.arguments.get("operation") == "move"
    )
    assert move_track.arguments["new_index"] == 4
    assert not any(operation.tool_name == "edit_fill" for operation in plan.operations)


def test_catalog_fallback_plans_porosity_overlay_and_crossover_fill() -> None:
    """Keep both porosity families when the request asks for an overlay."""
    goal = """
        Add one porosity track after the resistivity track.
        If RHOB and NPHI are available, overlay them in the same track.
        Reverse the neutron scale so crossover reads naturally.
        Add a crossover fill only when both RHOB and NPHI are present.
        Prefer the between_instances pattern against the RHOB overlay.
    """
    plan = build_catalog_fallback_plan(
        goal,
        section_id="main",
        document={"sections": [{"id": "main", "tracks": []}]},
        available_channels=["RHOB", "NPHI"],
    )

    assert plan is not None
    assert plan.expected_channels == ("RHOB", "NPHI")
    assert plan.expected_fill is not None
    assert plan.expected_fill["kind"] == "between_instances"
    fill_operations = [
        operation for operation in plan.operations if operation.tool_name == "edit_fill"
    ]
    assert len(fill_operations) == 1
    assert fill_operations[0].arguments["other_binding_id"] == "porosity.bulk_density.rhob"
    assert fill_operations[0].arguments["binding_id"] == "porosity.neutron_porosity.nphi"


def test_catalog_fallback_reconciles_existing_gr_sp_overview() -> None:
    """Use the same generic catalog path for an explicitly named existing track."""
    goal = """
        Revise the existing `gr_sp` overview track before the depth track.
        If both GR and SP are available, bind both to this track.
        Use -80 to 20 as the SP scale.
        Use 0 to 150 as the GR scale.
        Use a readable green gamma-ray curve and conventional linear scaling.
    """
    document = {
        "sections": [
            {
                "id": "main",
                "tracks": [
                    {
                        "id": "gr_sp",
                        "title": "GR/SP",
                        "kind": "normal",
                        "bindings": [
                            {
                                "channel": "GR",
                                "binding_id": "main.gr_sp.GR.1",
                                "label": "GR",
                            }
                        ],
                    },
                    {"id": "depth", "title": "Depth", "kind": "reference"},
                ],
            }
        ]
    }

    assert catalog_channel_candidates(goal) == ("GR", "SGR", "CGR", "SP")
    plan = build_catalog_fallback_plan(
        goal,
        section_id="main",
        document=document,
        available_channels=["GR", "SP"],
    )

    assert plan is not None
    assert plan.track_id == "gr_sp"
    assert plan.family_id is None
    assert plan.preset_id == "gr_sp_overview"
    assert plan.expected_channels == ("GR", "SP")
    assert plan.expected_binding_scales == {
        "GR": {"kind": "linear", "min": 0.0, "max": 150.0},
        "SP": {"kind": "linear", "min": -80.0, "max": 20.0},
    }
    assert plan.expected_binding_labels == {
        "GR": "Gamma Ray (GR)",
        "SP": "Spontaneous Potential (SP)",
    }
    track_adds = [
        operation
        for operation in plan.operations
        if operation.tool_name == "edit_track" and operation.arguments.get("operation") == "add"
    ]
    assert track_adds == []
    binding_operations = [
        operation for operation in plan.operations if operation.tool_name == "edit_curve_binding"
    ]
    assert [operation.arguments["operation"] for operation in binding_operations] == [
        "update",
        "add",
    ]


@pytest.mark.parametrize(
    ("value_min", "value_max", "expected_scale"),
    [
        (-0.02, 0.48, {"kind": "linear", "min": 0.45, "max": -0.15}),
        (-1.2208, 70.6439, {"kind": "linear", "min": 45.0, "max": -15.0}),
    ],
)
def test_catalog_fallback_selects_porosity_scale_from_source_range(
    value_min: float,
    value_max: float,
    expected_scale: dict[str, object],
) -> None:
    """Select asset-declared fractional or percentage scales from source evidence."""
    plan = build_catalog_fallback_plan(
        "Add one porosity track and overlay RHOB and NPHI with crossover fill.",
        section_id="main",
        document={"sections": [{"id": "main", "tracks": []}]},
        available_channels=["RHOB", "NPHI"],
        channel_summaries={
            "RHOB": {"value_min": 1.1, "value_max": 3.0},
            "NPHI": {"value_min": value_min, "value_max": value_max},
        },
    )

    assert plan is not None
    assert plan.expected_binding_scales["NPHI"] == expected_scale
    assert plan.expected_binding_labels == {
        "RHOB": "Density (RHOB)",
        "NPHI": "Neutron (NPHI)",
    }


def test_catalog_fallback_explicit_channel_scale_overrides_source_variant() -> None:
    """Keep a user-provided channel scale authoritative over catalog selection."""
    plan = build_catalog_fallback_plan(
        """
        Add one porosity track and overlay RHOB and NPHI.
        Use 0.5 to -0.1 as the NPHI scale.
        """,
        section_id="main",
        document={"sections": [{"id": "main", "tracks": []}]},
        available_channels=["RHOB", "NPHI"],
        channel_summaries={
            "NPHI": {"value_min": -1.2208, "value_max": 70.6439},
        },
    )

    assert plan is not None
    assert plan.expected_binding_scales["NPHI"] == {
        "kind": "linear",
        "min": 0.5,
        "max": -0.1,
    }


def test_catalog_fallback_upgrades_legacy_default_label() -> None:
    """Migrate an old semantic-only default without treating it as user text."""
    document = {
        "sections": [
            {
                "id": "main",
                "tracks": [
                    {
                        "id": "porosity",
                        "title": "Porosity Overlay",
                        "kind": "normal",
                        "bindings": [
                            {
                                "channel": "RHOB",
                                "binding_id": "porosity.rhob",
                                "label": "Density",
                            }
                        ],
                    }
                ],
            }
        ]
    }

    plan = build_catalog_fallback_plan(
        "Update the existing porosity track and overlay RHOB and NPHI.",
        section_id="main",
        document=document,
        available_channels=["RHOB", "NPHI"],
    )

    assert plan is not None
    rhob_update = next(
        operation
        for operation in plan.operations
        if operation.tool_name == "edit_curve_binding"
        and operation.arguments.get("channel") == "RHOB"
    )
    assert rhob_update.arguments["patch"]["label"] == "Density (RHOB)"


def test_catalog_fallback_preserves_existing_custom_label() -> None:
    """Catalog recovery must not replace an explicit persisted curve label."""
    document = {
        "sections": [
            {
                "id": "main",
                "tracks": [
                    {
                        "id": "porosity",
                        "title": "Porosity Overlay",
                        "kind": "normal",
                        "bindings": [
                            {
                                "channel": "RHOB",
                                "binding_id": "porosity.rhob",
                                "label": "Bulk density from corrected borehole",
                            }
                        ],
                    }
                ],
            }
        ]
    }

    plan = build_catalog_fallback_plan(
        "Update the existing porosity track and overlay RHOB and NPHI.",
        section_id="main",
        document=document,
        available_channels=["RHOB", "NPHI"],
    )

    assert plan is not None
    assert plan.expected_binding_labels["RHOB"] == "Bulk density from corrected borehole"
    rhob_update = next(
        operation
        for operation in plan.operations
        if operation.tool_name == "edit_curve_binding"
        and operation.arguments.get("channel") == "RHOB"
    )
    assert "label" not in rhob_update.arguments["patch"]


def test_catalog_fallback_porosity_postcondition_requires_fill() -> None:
    """A porosity overlay is incomplete until its requested fill is persisted."""
    goal = "Add one porosity track and overlay RHOB and NPHI with crossover fill."
    plan = build_catalog_fallback_plan(
        goal,
        section_id="main",
        document={"sections": [{"id": "main", "tracks": []}]},
        available_channels=["RHOB", "NPHI"],
    )

    assert plan is not None
    base_track = {
        "id": plan.track_id,
        "bindings": [
            {
                "channel": "RHOB",
                "binding_id": "porosity.bulk_density.rhob",
                "label": plan.expected_binding_labels["RHOB"],
                "scale": plan.expected_binding_scales["RHOB"],
            },
            {
                "channel": "NPHI",
                "binding_id": "porosity.neutron_porosity.nphi",
                "label": plan.expected_binding_labels["NPHI"],
                "scale": plan.expected_binding_scales["NPHI"],
            },
        ],
        "fills": [],
    }
    assert not fallback_plan_satisfied(plan, {"sections": [{"id": "main", "tracks": [base_track]}]})
    base_track["fills"] = [plan.expected_fill]
    assert fallback_plan_satisfied(plan, {"sections": [{"id": "main", "tracks": [base_track]}]})


def test_catalog_fallback_postcondition_checks_track_and_curve_scales() -> None:
    """Verify the fallback contract against the canonical document shape."""
    goal = "Add one resistivity track with a logarithmic scale from 0.2 to 2000."
    plan = build_catalog_fallback_plan(
        goal,
        section_id="main",
        document={"sections": [{"id": "main", "tracks": []}]},
        available_channels=["ILD"],
    )

    assert plan is not None
    document = {
        "sections": [
            {
                "id": "main",
                "tracks": [
                    {
                        "id": plan.track_id,
                        "x_scale": {"kind": "log", "minimum": 0.2, "maximum": 2000.0},
                        "bindings": [
                            {
                                "channel": "ILD",
                                "label": plan.expected_binding_labels["ILD"],
                                "scale": {
                                    "kind": "log",
                                    "minimum": 0.2,
                                    "maximum": 2000.0,
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }

    assert fallback_plan_satisfied(plan, document)


def test_stable_remarks_postcondition_accepts_string_lines(tmp_path: Path) -> None:
    """A valid remarks block may be serialized as a list of lines."""
    baseline = StableSession._document()
    current = StableSession._document()
    current.remarks = [
        {
            "title": "Notes",
            "lines": ["Built from a user-supplied LAS file."],
        }
    ]
    draft_path = tmp_path / "remarks.log.yaml"
    authoring_document_to_yaml(current, draft_path)

    assert (
        _stable_postcondition_errors(
            "Add one concise remarks block.",
            baseline,
            root=tmp_path,
            draft_logfile="remarks.log.yaml",
        )
        == []
    )


class StableBackend:
    """Provider double that performs one stable mutation through the loop."""

    provider = "stable-test"
    model = "stable-test-model"
    credential_source = "test"
    supports_desired_state = True
    supports_direct_operations = True

    def __init__(self, *, subtitle: str = "Stable loop test") -> None:
        """Initialize provider-call captures."""
        self.tool_names: list[str] = []
        self.max_rounds: int | None = None
        self.mutation_payload: dict[str, object] | None = None
        self.subtitle = subtitle

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[FunctionToolDefinition],
        tool_caller: object,
        max_rounds: int,
    ) -> ProviderRunResult:
        """Replay one stable section mutation."""
        del instructions, initial_user_message
        self.tool_names = [tool.name for tool in tool_definitions]
        self.max_rounds = max_rounds
        assert callable(tool_caller)
        self.mutation_payload = await tool_caller(
            "edit_section",
            {
                "operation": "update",
                "section_id": "main",
                "subtitle": self.subtitle,
            },
        )
        return ProviderRunResult(
            final_text="Applied one stable section edit.",
            tool_trace=(
                AuthoringToolCall(
                    round=1,
                    name="edit_section",
                    arguments={
                        "operation": "update",
                        "section_id": "main",
                        "subtitle": self.subtitle,
                    },
                ),
            ),
        )


class ReportInspectBackend(StableBackend):
    """Provider double that uses the legacy report inspection vocabulary."""

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[FunctionToolDefinition],
        tool_caller: object,
        max_rounds: int,
    ) -> ProviderRunResult:
        """Ask for report inspection and verify the host normalizes it."""
        del instructions, initial_user_message, tool_definitions, max_rounds
        assert callable(tool_caller)
        self.report_payload = await tool_caller(
            "inspect_authoring",
            {"object_kind": "report", "detail": "full"},
        )
        return ProviderRunResult(final_text="Inspected the report.", tool_trace=())


class FailingStableBackend(StableBackend):
    """Provider double that mutates once and then fails before verification."""

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[FunctionToolDefinition],
        tool_caller: object,
        max_rounds: int,
    ) -> ProviderRunResult:
        """Persist a mutation and raise to exercise request rollback."""
        await super().run_authoring(
            instructions=instructions,
            initial_user_message=initial_user_message,
            tool_definitions=tool_definitions,
            tool_caller=tool_caller,
            max_rounds=max_rounds,
        )
        raise RuntimeError("provider test failure")


class StalledStableBackend(StableBackend):
    """Provider double that repeats a failing inspection until stopped."""

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[FunctionToolDefinition],
        tool_caller: object,
        max_rounds: int,
    ) -> ProviderRunResult:
        """Replay repeated invalid inspections to exercise the circuit breaker."""
        del instructions, initial_user_message, tool_definitions, max_rounds
        assert callable(tool_caller)
        for _ in range(5):
            payload = await tool_caller(
                "inspect_source",
                {"source_path": "missing-source.las"},
            )
            if payload.get("_agent_control") is not None:
                break
        return ProviderRunResult(
            final_text="The feedback loop stopped the stalled inspection.",
            tool_trace=(),
        )


class ReadOnlyStalledBackend(StableBackend):
    """Provider double that repeatedly inspects without attempting a mutation."""

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[FunctionToolDefinition],
        tool_caller: object,
        max_rounds: int,
    ) -> ProviderRunResult:
        """Capture steering feedback after successful but unproductive inspections."""
        del instructions, initial_user_message, tool_definitions, max_rounds
        assert callable(tool_caller)
        self.feedback_messages: list[str] = []
        for _ in range(6):
            payload = await tool_caller(
                "inspect_authoring",
                {"object_kind": "section", "detail": "full"},
            )
            feedback = payload.get("agent_feedback", {})
            if isinstance(feedback, dict):
                self.feedback_messages.append(str(feedback.get("message", "")))
            if payload.get("_agent_control") is not None:
                break
        return ProviderRunResult(
            final_text="The feedback loop stopped the unproductive inspection.",
            tool_trace=(),
        )


class ExploratoryStableBackend(StableBackend):
    """Provider double that performs distinct reads before a valid mutation."""

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[FunctionToolDefinition],
        tool_caller: object,
        max_rounds: int,
    ) -> ProviderRunResult:
        """Prove that new inspections are not treated as stalled progress."""
        del instructions, initial_user_message, tool_definitions, max_rounds
        assert callable(tool_caller)
        for object_kind in ("section", "track", "page", "remark", "header_slot"):
            payload = await tool_caller(
                "inspect_authoring",
                {"object_kind": object_kind, "detail": "summary"},
            )
            assert payload.get("_agent_control") is None
        mutation = await tool_caller(
            "edit_section",
            {
                "operation": "update",
                "section_id": "main",
                "subtitle": "Stable loop test",
            },
        )
        assert mutation.get("_agent_control", {}).get("status") in {None, "completed"}
        return ProviderRunResult(
            final_text="Inspected distinct state and then applied the requested edit.",
            tool_trace=(),
        )


class StableSession:
    """Stateful MCP double exposing only the stable tool profile."""

    def __init__(self, root: Path) -> None:
        """Initialize the stable MCP session double."""
        self.root = root
        self.calls: list[tuple[str, dict[str, object]]] = []

    @staticmethod
    def _document(*, subtitle: str | None = None) -> AuthoringDocumentSpec:
        """Build the smallest valid document used by this MCP double."""
        return AuthoringDocumentSpec(
            name="Stable loop test",
            sections=[
                AuthoringSectionSpec(
                    id="main",
                    title="Main",
                    subtitle=subtitle,
                    tracks=[
                        NormalTrackSpec(
                            id="gr_sp",
                            title="GR/SP",
                            width_mm=30.0,
                        )
                    ],
                )
            ],
        )

    def _write_document(self, path: Path, *, subtitle: str | None = None) -> None:
        """Persist a canonical document rather than a YAML fragment."""
        path.parent.mkdir(parents=True, exist_ok=True)
        authoring_document_to_yaml(self._document(subtitle=subtitle), path)

    async def list_tools(self) -> object:
        """Return the complete stable tool catalog."""
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name=profile.name,
                    description=profile.description,
                    inputSchema=profile.input_schema,
                )
                for profile in stable_tool_profile()
            ]
        )

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        """Return stable payloads and persist the tested mutation."""
        self.calls.append((name, dict(arguments)))
        if name == "create_draft":
            path = self.root / str(arguments["logfile_path"])
            self._write_document(path)
            return SimpleNamespace(structuredContent={"ok": True, "changed": True, "after": {}})
        if name == "edit_header":
            assert arguments["operation"] == "apply_values"
            assert arguments["values"]
            return SimpleNamespace(
                structuredContent={
                    "ok": True,
                    "changed": True,
                    "applied_assignments": [
                        {"input_key": key, "value": value}
                        for key, value in arguments["values"].items()
                    ],
                    "skipped_assignments": [],
                    "warnings": [],
                }
            )
        if name == "inspect_authoring":
            return SimpleNamespace(
                structuredContent={
                    "ok": True,
                    "items": [
                        {
                            "ref": {"object_id": "main"},
                            "object": {
                                "id": "main",
                                "title": "Main",
                                "subtitle": "Stable loop test",
                                "tracks": [{"id": "gr_sp", "kind": "normal"}],
                            },
                        }
                    ],
                    "warnings": [],
                    "next_steps": [],
                }
            )
        if name == "edit_section":
            assert arguments["logfile_path"] == "workspace/stable.log.yaml"
            path = self.root / str(arguments["logfile_path"])
            self._write_document(path, subtitle=str(arguments["subtitle"]))
            return SimpleNamespace(
                structuredContent={
                    "ok": True,
                    "changed": True,
                    "target": {"object_kind": "section", "object_id": "main"},
                    "before": {"subtitle": ""},
                    "after": {"subtitle": "Stable loop test"},
                    "warnings": [],
                    "next_steps": [],
                }
            )
        if name == "validate_logfile":
            return SimpleNamespace(
                structuredContent={
                    "ok": True,
                    "valid": True,
                    "errors": [],
                    "warnings": [],
                    "next_steps": [],
                }
            )
        if name == "preview_logfile":
            return SimpleNamespace(content=[SimpleNamespace(data=b"stable-preview")])
        raise AssertionError(f"Unexpected stable MCP tool call: {name}")


class HeaderStableSession(StableSession):
    """Stable MCP double that persists header assignments."""

    @staticmethod
    def _document(*, subtitle: str | None = None) -> AuthoringDocumentSpec:
        """Build a document with independently writable header slots."""
        document = StableSession._document(subtitle=subtitle)
        document.header = AuthoringHeaderSpec(
            general_fields=[
                AuthoringHeaderFieldSpec(
                    slot_id="rmf_measured_temp",
                    key="rmf_measured_temp",
                    label="RMF @ Measured Temp",
                    value=AuthoringReportValueSpec(value=""),
                )
            ]
        )
        return document

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        """Persist stable header assignments before returning MCP evidence."""
        if name != "edit_header":
            return await super().call_tool(name, arguments)
        self.calls.append((name, dict(arguments)))
        path = self.root / str(arguments["logfile_path"])
        document = self._document()
        values = arguments["values"]
        assert isinstance(values, dict)
        value = next(iter(values.values()))
        document.header.general_fields = [
            field.model_copy(update={"value": AuthoringReportValueSpec(value=value)})
            for field in document.header.general_fields
        ]
        authoring_document_to_yaml(document, path)
        return SimpleNamespace(
            structuredContent={
                "ok": True,
                "changed": True,
                "applied_assignments": [
                    {"input_key": key, "value": value} for key, value in values.items()
                ],
                "skipped_assignments": [],
                "warnings": [],
            }
        )


class StableRuntime:
    """Runtime double translating stable descriptors and image results."""

    def __init__(self, root: Path, session: StableSession) -> None:
        """Initialize the runtime double."""
        self.server_root = root
        self.session = session

    @asynccontextmanager
    async def open_session(self) -> StableSession:
        """Yield the stable session double."""
        yield self.session

    def build_tool_definitions(
        self,
        mcp_tools: list[object],
        *,
        allowed_names: set[str],
        excluded_names: set[str] | None = None,
    ) -> list[FunctionToolDefinition]:
        """Translate stable descriptors into provider function tools."""
        excluded = excluded_names or set()
        return [
            FunctionToolDefinition(
                name=str(tool.name),
                description=str(tool.description),
                parameters=dict(tool.inputSchema),
            )
            for tool in mcp_tools
            if str(tool.name) in allowed_names and str(tool.name) not in excluded
        ]

    @staticmethod
    def image_bytes(result: object) -> bytes:
        """Return fake preview bytes."""
        return bytes(result.content[0].data)

    @staticmethod
    def tool_result_payload(result: object) -> dict[str, object]:
        """Normalize one fake MCP response."""
        return {
            "is_error": bool(getattr(result, "isError", False)),
            "structured": getattr(result, "structuredContent", {}),
        }


@pytest.mark.anyio
async def test_stable_loop_uses_compact_profile_and_persisted_evidence(tmp_path: Path) -> None:
    """Route natural-language authoring through stable tools, not legacy verbs."""
    session = StableSession(tmp_path)
    backend = StableBackend()
    authoring = AuthoringSession(backend=backend, runtime=StableRuntime(tmp_path, session))

    result = await authoring.run_request(
        AuthoringRequest(
            goal="Set the main section subtitle to Stable loop test.",
            output_logfile="workspace/stable.log.yaml",
            source_logfile_path="starter.log.yaml",
            max_rounds=4,
        )
    )

    assert backend.max_rounds == 4
    assert set(backend.tool_names) == STABLE_MCP_TOOL_NAMES
    assert result.validation["valid"] is True
    assert result.change_summary["changed"] is True
    assert result.report_preview_png == b"stable-preview"
    assert result.section_preview_png == b"stable-preview"
    assert result.report_facts["stable_tool_outcomes"]
    assert result.report_facts["feedback_loop"]["status"] == "completed"
    assert backend.mutation_payload["agent_feedback"]["status"] == "completed"
    assert session.calls[1][0] == "validate_logfile"
    assert session.calls[1][1]["level"] == "structural"
    assert [name for name, _ in session.calls] == [
        "create_draft",
        "validate_logfile",
        "edit_section",
        "validate_logfile",
        "inspect_authoring",
        "preview_logfile",
        "preview_logfile",
    ]
    assert all(not name.endswith("_logfile_draft") for name, _ in session.calls)


@pytest.mark.anyio
async def test_stable_loop_applies_packet_header_before_provider_tools(tmp_path: Path) -> None:
    """Bulk packet headers bypass provider slot selection and remain single-pass."""
    session = StableSession(tmp_path)
    backend = StableBackend()
    authoring = AuthoringSession(backend=backend, runtime=StableRuntime(tmp_path, session))

    result = await authoring.run_request(
        AuthoringRequest(
            goal="""
                Reconstruct the supported packet.

                Header Values:
                LOG / SERVICE
                - Cement Bond Log
                - Variable Density Log

                COMPANY / WELL IDENTIFICATION
                - Company: University of Utah

                Set the main section subtitle to Stable loop test.
            """,
            output_logfile="workspace/packet.log.yaml",
            source_logfile_path="starter.log.yaml",
            max_rounds=4,
        )
    )

    assert result.validation["valid"] is True
    assert "edit_header" not in backend.tool_names
    assert [name for name, _ in session.calls] == [
        "create_draft",
        "edit_header",
        "validate_logfile",
        "edit_section",
        "validate_logfile",
        "inspect_authoring",
        "preview_logfile",
        "preview_logfile",
    ]
    header_call = session.calls[1][1]
    assert header_call["operation"] == "apply_values"
    assert header_call["values"] == {
        "service_title_1": "Cement Bond Log",
        "service_title_2": "Variable Density Log",
        "Company": "University of Utah",
    }


@pytest.mark.anyio
async def test_stable_run_routes_header_only_request_without_provider_loop(tmp_path: Path) -> None:
    """Persist pure header fills directly instead of exposing them to the provider loop."""
    session = HeaderStableSession(tmp_path)
    backend = StableBackend()
    authoring = AuthoringSession(backend=backend, runtime=StableRuntime(tmp_path, session))

    result = await authoring.run_request(
        AuthoringRequest(
            goal="""
                Fill the following header fields with the following values:
                - Rmf measured: 0.01 @ 25
            """,
            output_logfile="workspace/header-only.log.yaml",
            source_logfile_path="starter.log.yaml",
            max_rounds=4,
        )
    )

    assert backend.tool_names == []
    assert result.validation["valid"] is True
    assert result.change_summary["changed"] is True
    assert [name for name, _ in session.calls] == [
        "create_draft",
        "edit_header",
        "validate_logfile",
        "inspect_authoring",
        "preview_logfile",
        "preview_logfile",
    ]
    persisted_path = tmp_path / "workspace/header-only.log.yaml"
    assert "0.01 @ 25" in persisted_path.read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_stable_loop_maps_report_inspection_to_page(tmp_path: Path) -> None:
    """Keep legacy report inspection requests inside the stable object contract."""
    session = StableSession(tmp_path)
    backend = ReportInspectBackend()
    authoring = AuthoringSession(backend=backend, runtime=StableRuntime(tmp_path, session))

    await authoring.run_request(
        AuthoringRequest(
            goal="Inspect the current report.",
            output_logfile="workspace/report-inspection.log.yaml",
            source_logfile_path="starter.log.yaml",
            max_rounds=4,
        )
    )

    inspect_calls = [
        arguments
        for name, arguments in session.calls
        if name == "inspect_authoring"
    ]
    assert any(arguments["object_kind"] == "page" for arguments in inspect_calls)


@pytest.mark.anyio
async def test_stable_loop_rolls_back_provider_failure(tmp_path: Path) -> None:
    """A failed stable request cannot contaminate the next revision."""
    session = StableSession(tmp_path)
    backend = FailingStableBackend()
    authoring = AuthoringSession(backend=backend, runtime=StableRuntime(tmp_path, session))

    result = await authoring.run_request(
        AuthoringRequest(
            goal="Set the main section subtitle to Stable loop test.",
            output_logfile="workspace/stable-rollback.log.yaml",
            source_logfile_path="starter.log.yaml",
            max_rounds=4,
        )
    )

    draft_path = tmp_path / "workspace/stable-rollback.log.yaml"
    assert draft_path.read_text(encoding="utf-8") == authoring_document_to_yaml(session._document())
    assert result.change_summary["changed"] is False
    assert result.report_facts["rolled_back"] is True


@pytest.mark.anyio
async def test_stable_loop_rolls_back_unmet_request_postcondition(tmp_path: Path) -> None:
    """A persisted but incorrect mutation is not reported as successful."""
    session = StableSession(tmp_path)
    backend = StableBackend(subtitle="Unexpected value")
    authoring = AuthoringSession(backend=backend, runtime=StableRuntime(tmp_path, session))

    result = await authoring.run_request(
        AuthoringRequest(
            goal="Set the main section subtitle to Stable loop test.",
            output_logfile="workspace/stable.log.yaml",
            source_logfile_path="starter.log.yaml",
            max_rounds=4,
        )
    )

    draft_path = tmp_path / "workspace/stable.log.yaml"
    assert draft_path.read_text(encoding="utf-8") == authoring_document_to_yaml(session._document())
    assert result.change_summary["changed"] is False
    assert result.report_facts["rolled_back"] is True
    assert "subtitle" in " ".join(result.report_facts["reasons"])


@pytest.mark.anyio
async def test_stable_loop_hides_rolled_back_header_mutations(tmp_path: Path) -> None:
    """A transaction rollback cannot leave an applied header in the user summary."""
    session = HeaderStableSession(tmp_path)
    backend = FailingStableBackend()
    authoring = AuthoringSession(backend=backend, runtime=StableRuntime(tmp_path, session))

    result = await authoring.run_request(
        AuthoringRequest(
            goal="""
                Header Values:
                - Rmf measured: 0.01 @ 25

                Set the main section subtitle to Stable loop test.
            """,
            output_logfile="workspace/stable.log.yaml",
            source_logfile_path="starter.log.yaml",
            max_rounds=4,
        )
    )

    assert result.report_facts["rolled_back"] is True
    assert result.change_summary["changed"] is False
    assert result.change_summary["summary_lines"] == []
    assert result.user_report.done == ()
    assert "Deterministic header values were rolled back with the request." in result.report_facts[
        "not_done"
    ]


@pytest.mark.anyio
async def test_stable_loop_stops_repeated_tool_errors(tmp_path: Path) -> None:
    """Repeated MCP failures stop the provider before the round budget is spent."""
    session = StableSession(tmp_path)
    backend = StalledStableBackend()
    authoring = AuthoringSession(backend=backend, runtime=StableRuntime(tmp_path, session))

    result = await authoring.run_request(
        AuthoringRequest(
            goal="Inspect the current draft before making changes.",
            output_logfile="workspace/stable-stalled.log.yaml",
            source_logfile_path="starter.log.yaml",
            max_rounds=12,
        )
    )

    assert [name for name, _ in session.calls[:4]] == [
        "create_draft",
        "validate_logfile",
        "inspect_source",
        "inspect_source",
    ]
    assert result.report_facts["feedback_loop"]["status"] == "blocked"
    assert result.report_facts["feedback_loop"]["consecutive_tool_errors"] == 2
    assert result.report_facts["feedback_loop"]["repeated_error_count"] == 2
    assert result.report_facts["rolled_back"] is True


@pytest.mark.anyio
async def test_stable_loop_allows_distinct_reads_before_mutation(tmp_path: Path) -> None:
    """Distinct discovery calls may precede a mutation without tripping the breaker."""
    session = StableSession(tmp_path)
    backend = ExploratoryStableBackend()
    authoring = AuthoringSession(backend=backend, runtime=StableRuntime(tmp_path, session))

    result = await authoring.run_request(
        AuthoringRequest(
            goal="Set the main section subtitle to Stable loop test.",
            output_logfile="workspace/stable.log.yaml",
            source_logfile_path="starter.log.yaml",
            max_rounds=12,
        )
    )

    assert result.validation["valid"] is True
    assert result.change_summary["changed"] is True
    assert result.report_facts["feedback_loop"]["status"] in {
        "completed",
        "provider_finished",
    }
    assert result.report_facts["feedback_loop"]["repeated_read_only_calls"] == 0
    edit_index = next(index for index, (name, _) in enumerate(session.calls) if name == "edit_section")
    inspect_calls_before_edit = [
        name for name, _ in session.calls[:edit_index] if name == "inspect_authoring"
    ]
    assert len(inspect_calls_before_edit) == 5


@pytest.mark.anyio
async def test_stable_loop_steers_after_successful_read_only_calls(tmp_path: Path) -> None:
    """Successful inspections cannot consume the request without mutation guidance."""
    session = StableSession(tmp_path)
    backend = ReadOnlyStalledBackend()
    authoring = AuthoringSession(backend=backend, runtime=StableRuntime(tmp_path, session))

    result = await authoring.run_request(
        AuthoringRequest(
            goal="Add a resistivity track and bind the available curves.",
            output_logfile="workspace/stable-read-only.log.yaml",
            source_logfile_path="starter.log.yaml",
            max_rounds=12,
        )
    )

    assert any(
        "exact read-only call already succeeded" in message
        for message in backend.feedback_messages
    )
    assert result.report_facts["feedback_loop"]["status"] == "blocked"
    assert result.report_facts["feedback_loop"]["repeated_read_only_calls"] >= 2
