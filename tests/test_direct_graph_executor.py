"""Tests for direct execution of graph-compiled authoring intent."""

from __future__ import annotations

import json
from pathlib import Path
from shutil import copyfile

from wellplot.agent.graph import execute_document_intent
from wellplot.authoring import load_authoring_document
from wellplot.authoring_service import AuthoringService
from wellplot.model.authoring import AuthoringDocumentSpec
from wellplot.model.intent import AuthoringDocumentIntent

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "agentic_cbl"


def _service() -> AuthoringService:
    """Build a minimal document for generic execution tests."""
    return AuthoringService(
        AuthoringDocumentSpec(
            name="direct-executor-test",
            title="Original",
            sections=[
                {
                    "id": "main",
                    "title": "Main",
                    "tracks": [
                        {
                            "id": "depth",
                            "title": "Depth",
                            "kind": "reference",
                            "width_mm": 20,
                        }
                    ],
                }
            ],
        )
    )


def _cased_hole_service(tmp_path: Path) -> AuthoringService:
    """Load the tracked cased-hole scaffold without mutable workspace inputs."""
    for filename in ("base.template.yaml", "cased_hole_starter.log.yaml"):
        copyfile(_FIXTURE_DIR / filename, tmp_path / filename)
    return AuthoringService(load_authoring_document(tmp_path / "cased_hole_starter.log.yaml"))


def test_direct_executor_applies_generic_intent_atomically() -> None:
    """Apply report, track, and binding intent without MCP or a provider."""
    service = _service()
    intent = AuthoringDocumentIntent.model_validate(
        {
            "title": "Revised",
            "sections": [
                {
                    "section_id": "main",
                    "tracks": [
                        {
                            "track_id": "curves",
                            "title": "Curves",
                            "kind": "normal",
                            "width_mm": 30,
                            "bindings": [
                                {
                                    "kind": "curve",
                                    "binding_id": "main.curves.GR.1",
                                    "channel": "GR",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )

    result = execute_document_intent(
        service,
        intent,
        available_channels={"main": [{"mnemonic": "GR", "kind": "scalar"}]},
    )

    assert result.success is True, result.errors
    assert result.reconciliation_plan is not None
    assert result.compilation is not None
    assert result.execution is not None
    assert result.execution.success is True
    assert service.document.title == "Revised"
    curves = service.document.sections[0].tracks[1]
    assert curves.id == "curves"
    assert curves.bindings[0].channel == "GR"


def test_direct_executor_leaves_service_unchanged_when_resolution_is_blocked() -> None:
    """Block before reconciliation when a source channel cannot be verified."""
    service = _service()
    before = service.document.model_dump(mode="json")
    intent = AuthoringDocumentIntent.model_validate(
        {
            "title": "Must not persist",
            "sections": [
                {
                    "section_id": "main",
                    "tracks": [
                        {
                            "track_id": "curves",
                            "title": "Curves",
                            "kind": "normal",
                            "width_mm": 30,
                            "bindings": [
                                {
                                    "kind": "curve",
                                    "binding_id": "main.curves.SP.1",
                                    "channel": "SP",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )

    result = execute_document_intent(
        service,
        intent,
        available_channels={"main": [{"mnemonic": "GR", "kind": "scalar"}]},
    )

    assert result.success is False
    assert result.reconciliation_plan is None
    assert result.execution is None
    assert "SP" in " ".join(result.errors)
    assert service.document.model_dump(mode="json") == before


def test_direct_executor_applies_frozen_cbl_intent_to_tracked_scaffold(tmp_path: Path) -> None:
    """Apply the frozen graph output with explicit, deterministic context data."""
    contract = json.loads((_FIXTURE_DIR / "compile_contract.json").read_text(encoding="utf-8"))
    intent = AuthoringDocumentIntent.model_validate(contract["merged_intent"])
    service = _cased_hole_service(tmp_path)
    source_manifest = contract["source_manifest"]

    result = execute_document_intent(
        service,
        intent,
        available_channels={
            section_id: source["channels"] for section_id, source in source_manifest.items()
        },
        header_aliases=contract["execution_context"]["header_aliases"],
    )

    assert result.success is True, result.errors
    assert result.execution is not None
    assert result.execution.success is True
    assert len(result.reconciliation_plan.operations) == 63
    assert [section.id for section in service.document.sections] == ["main_pass", "repeat_pass"]
    for section in service.document.sections:
        assert [track.id for track in section.tracks] == ["combo", "depth", "cbl", "vdl"]
        tracks = {track.id: track for track in section.tracks}
        assert len(tracks["combo"].bindings) == 4
        assert len(tracks["depth"].bindings) == 3
        assert len(tracks["cbl"].bindings) == 2
        assert len(tracks["vdl"].bindings) == 1
        assert tracks["vdl"].bindings[0].kind == "raster"
    assert [title.value.value for title in service.document.header.service_titles] == [
        "Cement Bond Log",
        "Variable Density Log",
        "Gamma Ray - CCL",
    ]
    general_values = {
        field.key: field.value.value for field in service.document.header.general_fields
    }
    assert general_values["company"] == "University of Utah"
    assert general_values["well"] == "FORGE 16B (78)-32"
    assert general_values["country"] == "Utah"
    assert general_values["section"] == "NWSW 32"
    remarks = {remark.title: remark for remark in service.document.remarks}
    assert (
        "Reconstruct only the supported subset"
        in remarks["Supported Reconstruction Scope"].lines[0]
    )
    assert "staged DLIS files" in remarks["Data Sources"].lines[0]
