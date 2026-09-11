"""Frozen compile-only CBL reconstruction evaluation for LG-1 through LG-4."""

###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pydantic import BaseModel

pytest.importorskip("langgraph")

from wellplot.agent.graph import (
    ReconstructionGraphDependencies,
    ReconstructionPlanner,
    ReportCompiler,
    SectionCompiler,
    build_compile_graph,
)
from wellplot.authoring import load_authoring_document
from wellplot.capabilities import create_builtin_registry
from wellplot.model.intent import AuthoringDocumentIntent

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "agentic_cbl"


@dataclass
class _FixtureStructuredModel:
    """Return frozen structured results without invoking a provider or MCP."""

    contract: dict[str, object]
    tool_calls: list[str] = field(default_factory=list)
    mcp_call_count: int = 0
    correction_count: int = 0

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
        """Return the frozen planner or compiler output for its exact target."""
        del instructions, tool_description, max_rounds
        self.tool_calls.append(tool_name)
        artifacts = self.contract["artifacts"]
        if tool_name == "submit_reconstruction_plan":
            payload = self.contract["reconstruction_plan"]
        elif tool_name == "submit_report_artifact":
            payload = artifacts["report"]
        elif "Compile section 'main_pass'." in user_message:
            payload = artifacts["sections"]["main_pass"]
        elif "Compile section 'repeat_pass'." in user_message:
            payload = artifacts["sections"]["repeat_pass"]
        else:
            raise AssertionError(f"Unexpected compiler target: {tool_name!r}")
        result = response_model.model_validate(payload)
        if response_validator is not None:
            response_validator(result)
        return result


def test_cbl_compile_graph_matches_frozen_semantic_contract() -> None:
    """The graph compiles the CBL request without persistence, MCP, or repair."""
    prompt = (_FIXTURE_DIR / "frozen_prompt.txt").read_text(encoding="utf-8")
    contract = json.loads((_FIXTURE_DIR / "compile_contract.json").read_text(encoding="utf-8"))

    result, model = asyncio.run(_compile_frozen_cbl(prompt=prompt, contract=contract))

    assert hashlib.sha256(prompt.encode("utf-8")).hexdigest() == contract["prompt_sha256"]
    assert result["plan"] == contract["reconstruction_plan"]
    assert result["merged_intent"] == contract["merged_intent"]
    assert model.tool_calls == [
        "submit_reconstruction_plan",
        "submit_report_artifact",
        "submit_section_artifact",
        "submit_section_artifact",
    ]
    assert len(model.tool_calls) == contract["model_call_count"] == 4
    assert model.correction_count == contract["correction_count"] == 0
    assert model.mcp_call_count == 0

    intent = AuthoringDocumentIntent.model_validate(result["merged_intent"])
    sections = intent.sections or []
    assert [section.section_id for section in sections] == ["main_pass", "repeat_pass"]
    assert set(contract["capability_ids"]) >= {
        "report.standard",
        "section.log_plot",
        "track.normal",
        "track.reference",
        "track.array",
        "binding.curve",
        "binding.raster",
    }

    for section in sections:
        tracks = section.tracks or []
        assert [track.track_id for track in tracks] == ["combo", "depth", "cbl", "vdl"]
        assert [track.kind for track in tracks] == ["normal", "reference", "normal", "array"]
        by_track = {track.track_id: track for track in tracks}
        assert len(by_track["combo"].bindings or []) == 4
        assert len(by_track["depth"].bindings or []) == 3
        assert len(by_track["cbl"].bindings or []) == 2
        assert {
            binding.channel
            for binding in by_track["cbl"].bindings or []
            if getattr(binding, "kind", None) == "curve"
        } == {"CBL"}
        assert [binding.channel for binding in by_track["vdl"].bindings or []] == ["VDL"]


async def _compile_frozen_cbl(
    *,
    prompt: str,
    contract: dict[str, object],
) -> tuple[dict[str, object], _FixtureStructuredModel]:
    """Run only the compile graph with deterministic fixture responses."""
    registry = create_builtin_registry()
    model = _FixtureStructuredModel(contract=contract)
    graph = build_compile_graph(
        ReconstructionGraphDependencies(
            planner=ReconstructionPlanner(model=model, registry=registry),
            report_compiler=ReportCompiler(model=model, registry=registry),
            section_compiler=SectionCompiler(model=model, registry=registry),
            registry=registry,
        )
    )
    result = await graph.ainvoke(
        {
            "request": prompt,
            "current_document": load_authoring_document(
                _FIXTURE_DIR / "cased_hole_starter.log.yaml"
            ).model_dump(mode="json"),
            "source_manifest": contract["source_manifest"],
            "compiled_artifacts": [],
            "diagnostics": [],
            "repair_attempt": 0,
        }
    )
    return result, model
