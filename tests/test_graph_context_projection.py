"""Tests for semantic prompt-context projections used by the graph planner."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from pydantic import BaseModel

from wellplot.agent.graph.context_projection import (
    planner_document_summary,
    planner_source_manifest_summary,
)
from wellplot.agent.graph.planner import ReconstructionPlanner
from wellplot.capabilities import create_builtin_registry


def _document() -> dict[str, object]:
    """Build presentation-heavy canonical state with semantic planner facts."""
    return {
        "name": "projection-test",
        "title": "Existing Cased-Hole Packet",
        "subtitle": "Current packet subtitle",
        "depth": {
            "unit": "ft",
            "scale": "1:240",
            "major_step": 10,
            "minor_step": 2,
        },
        "header": {
            "enabled": True,
            "provider_name": "Company",
            "title": "Header title",
            "subtitle": "Header subtitle",
            "tail_enabled": False,
            "service_titles": [
                {
                    "slot_id": "service_title.1",
                    "value": {"value": "Cased Hole Quicklook", "source_key": "SERVICE"},
                    "alignment": "center",
                }
            ],
            "general_fields": [
                {
                    "slot_id": "general.company",
                    "key": "company",
                    "label": "Company",
                    "value": {"value": "University of Utah"},
                    "aliases": ["Company"],
                }
            ],
            "detail": {
                "kind": "table",
                "title": "Open Hole Metadata",
                "column_titles": ["Field", "Value"],
                "rows": [{"cells": [{"value": "x" * 1_000}]}],
            },
            "extensions": {"legacy_header": "x" * 2_000},
        },
        "page": {"orientation": "landscape", "extensions": {"render": "x" * 2_000}},
        "extensions": {"legacy_document": "x" * 2_000},
        "remarks": [
            {
                "remark_id": "notice",
                "title": "Public Data Notice",
                "lines": ["x" * 1_000],
            }
        ],
        "sections": [
            {
                "id": "main_pass",
                "title": "Main Pass",
                "subtitle": "Primary acquisition",
                "depth_range": [25, 4_845],
                "data_source": {
                    "source_path": "CBL_Main.dlis",
                    "source_format": "dlis",
                },
                "extensions": {"legacy_section": "x" * 2_000},
                "tracks": [
                    {
                        "id": "combo",
                        "title": "Combo",
                        "kind": "normal",
                        "width_mm": 30,
                        "x_scale": {
                            "kind": "linear",
                            "minimum": 0,
                            "maximum": 150,
                            "reverse": False,
                            "unit": "gAPI",
                        },
                        "grid": {"major": {"color": "#000000"}},
                        "bindings": [
                            {
                                "binding_id": "main.combo.GR.1",
                                "kind": "curve",
                                "channel": "GR",
                                "label": "Gamma Ray",
                                "scale": {
                                    "kind": "linear",
                                    "minimum": 0,
                                    "maximum": 150,
                                },
                                "style": {"color": "#00ff00", "line_width": 0.8},
                                "extensions": {"legacy_binding": "x" * 2_000},
                            }
                        ],
                        "fills": [
                            {
                                "fill_id": "combo.fill.1",
                                "kind": "between_instances",
                                "binding_id": "main.combo.GR.1",
                                "other_binding_id": "main.combo.SP.1",
                                "label": "Crossover",
                                "extensions": {"legacy_fill": "x" * 1_000},
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _source_manifest() -> dict[str, object]:
    """Build source facts with large payloads excluded from planning."""
    return {
        "main_pass": {
            "source_path": "/data/CBL_Main.dlis",
            "source_format": "dlis",
            "dataset_name": "CBL Main",
            "channels": [
                {
                    "mnemonic": "VDL",
                    "kind": "array",
                    "aliases": ["Variable Density Log"],
                    "unit": "mV",
                    "description": "Variable density waveform",
                    "value_shape": [10_000, 240],
                    "source_path": "/data/CBL_Main.dlis",
                },
                {
                    "mnemonic": "CBL",
                    "kind": "scalar",
                    "aliases": ["Cement Bond Log"],
                    "unit": "mV",
                    "description": "Cement bond amplitude",
                    "value_shape": [10_000],
                    "source_path": "/data/CBL_Main.dlis",
                },
            ],
            "well_metadata": {"WELL": "x" * 2_000},
            "provenance": {"frames": ["x" * 2_000]},
        }
    }


def test_planner_projections_keep_semantic_inventory_and_drop_heavy_payloads() -> None:
    """Planner context is small without losing document or channel identities."""
    document = _document()
    source_manifest = _source_manifest()

    document_summary = planner_document_summary(document)
    source_summary = planner_source_manifest_summary(source_manifest)

    assert document_summary["title"] == "Existing Cased-Hole Packet"
    assert document_summary["header"] == {
        "enabled": True,
        "provider_name": "Company",
        "title": "Header title",
        "subtitle": "Header subtitle",
        "tail_enabled": False,
        "service_titles": [{"slot_id": "service_title.1"}],
        "general_fields": [
            {
                "slot_id": "general.company",
                "key": "company",
                "label": "Company",
                "aliases": ["Company"],
            }
        ],
        "detail": {
            "kind": "table",
            "title": "Open Hole Metadata",
            "column_titles": ["Field", "Value"],
            "row_count": 1,
            "fields": [],
        },
    }
    assert document_summary["remarks"] == [{"remark_id": "notice", "title": "Public Data Notice"}]
    assert document_summary["sections"] == [
        {
            "id": "main_pass",
            "title": "Main Pass",
            "subtitle": "Primary acquisition",
            "depth_range": [25, 4_845],
            "data_source": {
                "source_path": "CBL_Main.dlis",
                "source_format": "dlis",
            },
            "tracks": [
                {
                    "id": "combo",
                    "title": "Combo",
                    "kind": "normal",
                    "width_mm": 30,
                    "x_scale": {
                        "kind": "linear",
                        "minimum": 0,
                        "maximum": 150,
                        "reverse": False,
                        "unit": "gAPI",
                    },
                    "bindings": [
                        {
                            "binding_id": "main.combo.GR.1",
                            "kind": "curve",
                            "channel": "GR",
                            "label": "Gamma Ray",
                            "scale": {
                                "kind": "linear",
                                "minimum": 0,
                                "maximum": 150,
                            },
                        }
                    ],
                    "fills": [
                        {
                            "fill_id": "combo.fill.1",
                            "kind": "between_instances",
                            "binding_id": "main.combo.GR.1",
                            "other_binding_id": "main.combo.SP.1",
                            "label": "Crossover",
                        }
                    ],
                }
            ],
        }
    ]
    assert source_summary == {
        "main_pass": {
            "source_path": "/data/CBL_Main.dlis",
            "source_format": "dlis",
            "dataset_name": "CBL Main",
            "channels": [
                {
                    "mnemonic": "CBL",
                    "kind": "scalar",
                    "unit": "mV",
                    "description": "Cement bond amplitude",
                    "aliases": ["Cement Bond Log"],
                },
                {
                    "mnemonic": "VDL",
                    "kind": "array",
                    "unit": "mV",
                    "description": "Variable density waveform",
                    "aliases": ["Variable Density Log"],
                },
            ],
        }
    }

    raw_context = {"current_document": document, "source_manifest": source_manifest}
    projected_context = {
        "current_document": document_summary,
        "source_manifest": source_summary,
    }
    assert len(json.dumps(projected_context)) < len(json.dumps(raw_context)) / 4
    serialized_summary = json.dumps(projected_context)
    assert "legacy_document" not in serialized_summary
    assert "University of Utah" not in serialized_summary
    assert "Cased Hole Quicklook" not in serialized_summary
    assert "well_metadata" not in serialized_summary
    assert "provenance" not in serialized_summary
    assert "value_shape" not in serialized_summary


@dataclass
class _CapturingPlannerModel:
    """Capture the planner request while returning a valid semantic plan."""

    user_messages: list[str] = field(default_factory=list)

    async def generate(
        self,
        *,
        instructions: str,
        user_message: str,
        response_model: type[BaseModel],
        tool_name: str,
        tool_description: str,
        max_rounds: int = 3,
        response_validator: object | None = None,
    ) -> BaseModel:
        """Record the exact prompt context passed to the provider boundary."""
        del instructions, tool_description, max_rounds
        assert tool_name == "submit_reconstruction_plan"
        self.user_messages.append(user_message)
        plan = response_model.model_validate(
            {
                "summary": "Compile the existing main pass.",
                "sections": [
                    {
                        "section_id": "main_pass",
                        "capability_id": "section.log_plot",
                        "goal": "Compile the existing main pass.",
                        "components": [
                            {
                                "component_id": "main_pass.combo",
                                "target_id": "combo",
                                "capability_id": "track.normal",
                                "goal": "Keep the existing combo track.",
                                "parent_component_id": None,
                            }
                        ],
                    }
                ],
            }
        )
        assert callable(response_validator)
        response_validator(plan)
        return plan


def test_planner_sends_only_projected_context_to_provider() -> None:
    """The planner boundary cannot accidentally send full canonical payloads."""
    document = _document()
    source_manifest = _source_manifest()
    model = _CapturingPlannerModel()
    planner = ReconstructionPlanner(model=model, registry=create_builtin_registry())

    plan = asyncio.run(
        planner.plan(
            request="Compile the existing CBL packet.",
            current_document=document,
            source_manifest=source_manifest,
        )
    )

    context = json.loads(model.user_messages[0].split("Context:\n", maxsplit=1)[1])
    assert plan.sections[0].section_id == "main_pass"
    assert context["current_document"] == planner_document_summary(document)
    assert context["source_manifest"] == planner_source_manifest_summary(source_manifest)
    assert "legacy_document" not in model.user_messages[0]
    assert "well_metadata" not in model.user_messages[0]
