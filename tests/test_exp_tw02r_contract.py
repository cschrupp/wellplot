"""Focused EXP-TW-02R corrective contract tests."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from scripts.exp_tw00_corpus import load_corpus
from scripts.exp_tw02r_contract import (
    DraftCompilationError,
    compile_golden_drafts,
    compile_section_draft,
    execute_compiled_section,
    load_golden_drafts,
    provider_section_input,
    validate_gate_a,
)

from wellplot.agent.code_mode.enrichment import ResolvedSectionContext


def _context_for(section_key: str) -> ResolvedSectionContext:
    """Return the frozen context selected by its opaque candidate ID."""
    corpus = load_corpus()
    candidate_id = "source-1" if section_key == "main_pass" else "source-2"
    return next(
        context
        for context in corpus.sections
        if any(source.candidate_id == candidate_id for source in context.sources)
    )


def test_provider_projection_is_path_free_and_matches_worker_boundary() -> None:
    """Host canonical paths never cross the provider-facing projection."""
    context = _context_for("main_pass")
    payload = provider_section_input(context).model_dump_json()

    assert "CBL_Main.dlis" not in payload
    assert "canonical_path" not in payload
    assert "source_format" not in payload
    assert {source.candidate_id for source in provider_section_input(context).sources} == {
        "source-1"
    }


def test_corrected_golden_drafts_compile_and_execute_privately() -> None:
    """Both corrected sections pass Gate A, reconciliation, and private execution."""
    compiled = compile_golden_drafts()

    assert set(compiled) == {"main_pass", "repeat_pass"}
    for section_key, result in compiled.items():
        execution = execute_compiled_section(result, _context_for(section_key))
        assert execution.success is True
        assert result.intent.sections is not None
        assert result.intent.sections[0].data_source is not None


def test_compilation_is_deterministic_and_preserves_semantic_views() -> None:
    """Repeated CBL views, order, scales, and VDL semantics survive compilation."""
    first = compile_golden_drafts()["main_pass"]
    second = compile_golden_drafts()["main_pass"]

    assert first.normalized_projection == second.normalized_projection
    tracks = first.normalized_projection["tracks"]
    assert [track["role"] for track in tracks] == ["combo", "depth", "cbl", "vdl"]
    cbl_bindings = tracks[2]["bindings"]
    assert [binding["semantic_id"] for binding in cbl_bindings] == [
        "cbl_0_100",
        "cbl_0_10",
    ]
    assert [binding["scale"]["maximum"] for binding in cbl_bindings] == [100, 10]
    assert tracks[3]["bindings"][0]["kind"] == "raster"
    assert tracks[3]["bindings"][0]["profile"] == "vdl"


def test_gate_a_rejects_wrong_title_and_binding_semantics() -> None:
    """Gate A validates worker-owned titles and repeated-view distinctions."""
    drafts = load_golden_drafts()
    draft = drafts["main_pass"]
    renamed = draft.model_copy(update={"title": "Anything"})
    gate = validate_gate_a(
        renamed,
        section_key="main_pass",
        section_context=_context_for("main_pass"),
    )
    assert gate["titles_valid"] is False
    assert gate["semantic_usable"] is False

    reordered = draft.model_copy(
        update={
            "tracks": (
                draft.tracks[0],
                draft.tracks[1],
                draft.tracks[2].model_copy(
                    update={"bindings": tuple(reversed(draft.tracks[2].bindings))}
                ),
                draft.tracks[3],
            )
        }
    )
    assert (
        validate_gate_a(
            reordered,
            section_key="main_pass",
            section_context=_context_for("main_pass"),
        )["semantic_usable"]
        is False
    )

    wrong_scale = draft.model_copy(
        update={
            "tracks": (
                draft.tracks[0].model_copy(
                    update={
                        "bindings": (
                            draft.tracks[0]
                            .bindings[0]
                            .model_copy(
                                update={
                                    "scale": draft.tracks[0]
                                    .bindings[0]
                                    .scale.model_copy(update={"maximum": 999})
                                }
                            ),
                            *draft.tracks[0].bindings[1:],
                        )
                    }
                ),
                *draft.tracks[1:],
            )
        }
    )
    assert (
        validate_gate_a(
            wrong_scale,
            section_key="main_pass",
            section_context=_context_for("main_pass"),
        )["semantic_usable"]
        is False
    )


def test_gate_a_is_source_scoped_when_two_candidates_coexist() -> None:
    """A channel in source A cannot satisfy a draft selecting source B."""
    corpus = load_corpus()
    first_source = corpus.sections[0].sources[0]
    second_source = first_source.model_copy(
        update={
            "candidate_id": "source-2",
            "canonical_path": "workspace/data/other.dlis",
            "channels": tuple(
                channel for channel in first_source.channels if channel.mnemonic != "CBL"
            ),
        }
    )
    context = corpus.sections[0].model_copy(update={"sources": (first_source, second_source)})
    draft = load_golden_drafts()["main_pass"].model_copy(update={"source_candidate": "source-2"})

    gate = validate_gate_a(draft, section_key="main_pass", section_context=context)
    assert gate["host_reference_valid"] is True
    assert gate["channel_valid"] is False
    assert gate["semantic_usable"] is False


def test_compiler_revalidates_corrupted_existing_model_instances() -> None:
    """model_copy(update=...) corruption cannot bypass structural validation."""
    draft = load_golden_drafts()["main_pass"]
    corrupted_track = draft.tracks[0].model_copy(update={"kind": "annotation"})
    corrupted = draft.model_copy(update={"tracks": (corrupted_track, *draft.tracks[1:])})

    with pytest.raises(ValidationError):
        compile_section_draft(
            corrupted,
            section_key="main_pass",
            section_context=_context_for("main_pass"),
        )


def test_gate_a_rejects_wrong_source_channel_kind_before_compilation() -> None:
    """Valid structure with a raster/scalar mismatch fails at Gate A."""
    draft = load_golden_drafts()["main_pass"]
    cbl = draft.tracks[2]
    invalid = draft.model_copy(
        update={
            "tracks": (
                draft.tracks[0],
                draft.tracks[1],
                cbl.model_copy(
                    update={
                        "bindings": (
                            cbl.bindings[0].model_copy(update={"channel": "VDL"}),
                            cbl.bindings[1],
                        )
                    }
                ),
                draft.tracks[3],
            )
        }
    )

    with pytest.raises(DraftCompilationError, match="corrected Gate A"):
        compile_section_draft(
            invalid,
            section_key="main_pass",
            section_context=_context_for("main_pass"),
        )


def test_review_projection_is_path_free_and_contains_no_provider_concepts() -> None:
    """The review projection contains semantics, not host/compiler/provider data."""
    projection = compile_golden_drafts()["repeat_pass"].normalized_projection
    serialized = json.dumps(projection, sort_keys=True)

    assert "CBL_Repeat.dlis" not in serialized
    assert "canonical_path" not in serialized
    assert "binding_id" not in serialized
    assert "provider" not in serialized.lower()
    assert projection["source_candidate"] == "source-2"


def test_valid_corrected_contract_is_total_for_canonical_intent() -> None:
    """Every Gate-A-valid corrected value has an explicit host completion path."""
    for result in compile_golden_drafts().values():
        assert result.intent.sections is not None
        section = result.intent.sections[0]
        assert section.tracks is not None
        assert all(track.width_mm is not None for track in section.tracks)
        assert all(track.bindings for track in section.tracks)
