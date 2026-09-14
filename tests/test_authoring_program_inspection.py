"""Bounded read-only inspection tests for CM-16."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from wellplot.authoring_context import AuthoringChannelCandidate
from wellplot.authoring_program.errors import ProgramNameError
from wellplot.authoring_program.inspection import AuthoringInspectionFacade
from wellplot.model.authoring import AuthoringDocumentSpec


def _document() -> AuthoringDocumentSpec:
    """Build two sections with local track IDs and ordered header slots."""
    return AuthoringDocumentSpec(
        name="inspection-test",
        title="Inspection",
        subtitle="Bounded",
        header={
            "general_fields": [{"slot_id": "well", "key": "well", "label": "Well Name"}],
            "service_titles": [{"slot_id": "service"}],
        },
        sections=[
            {
                "id": "main",
                "title": "Main Pass",
                "tracks": [
                    {
                        "id": "combo",
                        "title": "Combo",
                        "kind": "normal",
                        "width_mm": 40,
                        "bindings": [
                            {
                                "binding_id": "main.combo.GR",
                                "channel": "GR",
                            }
                        ],
                    }
                ],
            },
            {
                "id": "repeat",
                "title": "Repeat Pass",
                "tracks": [
                    {
                        "id": "combo",
                        "title": "Repeat Combo",
                        "kind": "normal",
                        "width_mm": 20,
                        "bindings": [
                            {
                                "binding_id": "repeat.combo.CBL",
                                "channel": "CBL",
                            }
                        ],
                    }
                ],
            },
        ],
    )


def _channels() -> dict[str, list[dict[str, object]]]:
    """Return deliberately unsorted section-scoped semantic channel facts."""
    return {
        "main": [
            {"mnemonic": "GR", "kind": "scalar", "unit": "gAPI", "value_shape": []},
            {"mnemonic": "VDL", "kind": "array", "unit": "mV", "value_shape": [64]},
        ],
        "repeat": [{"mnemonic": "CBL", "kind": "scalar", "unit": "mV", "value_shape": []}],
    }


def test_document_and_sections_are_bounded_and_canonically_ordered() -> None:
    """Document summaries contain no nested tracks or canonical internals."""
    inspection = AuthoringInspectionFacade(_document(), available_channels=_channels())

    assert inspection.document_summary().model_dump(mode="json") == {
        "name": "inspection-test",
        "title": "Inspection",
        "subtitle": "Bounded",
        "section_ids": ["main", "repeat"],
    }
    assert [section.section_id for section in inspection.sections()] == ["main", "repeat"]
    assert set(inspection.document_summary().model_dump()) == {
        "name",
        "title",
        "subtitle",
        "section_ids",
    }
    assert "tracks" not in inspection.document_summary().model_dump()


def test_tracks_and_bindings_are_section_scoped_and_deterministic() -> None:
    """Local track IDs remain independently addressable by section."""
    inspection = AuthoringInspectionFacade(_document())

    assert inspection.tracks("main")[0].model_dump(mode="json") == {
        "track_id": "combo",
        "title": "Combo",
        "kind": "normal",
        "width_mm": 40.0,
        "binding_ids": ["main.combo.GR"],
    }
    assert inspection.bindings("repeat", "combo")[0].model_dump(mode="json") == {
        "binding_id": "repeat.combo.CBL",
        "kind": "curve",
        "channel": "CBL",
    }


def test_header_slots_expose_identity_without_current_values() -> None:
    """Header inventory is a fixed slot projection, not a full header dump."""
    inspection = AuthoringInspectionFacade(_document())

    assert [slot.model_dump(mode="json") for slot in inspection.header_slots()] == [
        {"slot_id": "well", "key": "well", "label": "Well Name"},
        {"slot_id": "service", "key": None, "label": None},
    ]


def test_channels_are_explicit_section_scoped_sorted_and_semantic_only() -> None:
    """Channel output contains stable metadata but no source or sample values."""
    inspection = AuthoringInspectionFacade(_document(), available_channels=_channels())

    assert [channel.model_dump(mode="json") for channel in inspection.channels("main")] == [
        {"mnemonic": "GR", "kind": "scalar", "unit": "gAPI", "shape": []},
        {"mnemonic": "VDL", "kind": "array", "unit": "mV", "shape": [64]},
    ]
    assert set(inspection.channels("main")[0].model_dump()) == {
        "mnemonic",
        "kind",
        "unit",
        "shape",
    }


def test_facade_does_not_mutate_inputs_or_return_mutable_projection_state() -> None:
    """Deep-copy and frozen projections preserve both caller and facade state."""
    document = _document()
    channels = _channels()
    document_before = document.model_dump_json()
    channels_before = repr(channels)
    inspection = AuthoringInspectionFacade(document, available_channels=channels)

    sections = inspection.sections()
    source_channels = inspection.channels("main")
    with pytest.raises((TypeError, AttributeError, ValueError)):
        sections[0].title = "changed"
    with pytest.raises((TypeError, AttributeError, ValueError)):
        source_channels[0].shape += (2,)

    assert document.model_dump_json() == document_before
    assert repr(channels) == channels_before
    assert inspection.sections()[0].title == "Main Pass"


def test_unknown_scopes_use_program_name_error_and_track_lookup_is_not_global() -> None:
    """Unknown section/track selectors are stable errors and never ambiguous."""
    inspection = AuthoringInspectionFacade(_document())

    with pytest.raises(ProgramNameError, match="Section 'missing'"):
        inspection.tracks("missing")
    with pytest.raises(ProgramNameError, match="Track 'missing'"):
        inspection.bindings("main", "missing")
    with pytest.raises(ProgramNameError, match="section 'repeat'"):
        inspection.bindings("repeat", "missing")
    with pytest.raises(ProgramNameError, match="Section 'missing'"):
        inspection.channels("missing")


def test_channel_context_requires_explicit_section_key() -> None:
    """Global or inferred source channel context is never invented."""
    inspection = AuthoringInspectionFacade(
        _document(),
        available_channels={"other": [AuthoringChannelCandidate(mnemonic="GR")]},
    )

    assert inspection.channels("main") == ()


def test_inspection_surface_has_no_full_document_or_arbitrary_query_escape_hatch() -> None:
    """Only the fixed read-only projection methods are public facade methods."""
    public_names = {name for name in dir(AuthoringInspectionFacade) if not name.startswith("_")}
    assert public_names == {
        "bindings",
        "channels",
        "document_summary",
        "header_slots",
        "sections",
        "tracks",
    }
    assert not any(
        name in public_names
        for name in {"document", "raw_document", "spec", "payload", "dump", "query"}
    )


def test_inspection_module_has_no_edge_or_filesystem_imports() -> None:
    """The host-side context facade remains below agent and edge layers."""
    module_path = Path(__file__).parents[1] / "src/wellplot/authoring_program/inspection.py"
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
        "wellplot.provider",
        "wellplot.render",
        "pathlib",
        "os",
        "yaml",
    )
    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imported_modules
        for prefix in forbidden_prefixes
    )
