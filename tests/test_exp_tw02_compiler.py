"""Tests for the deterministic EXP-TW-02 section compiler."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from scripts.exp_tw00_corpus import load_corpus
from scripts.exp_tw01_schema import load_golden_drafts
from scripts.exp_tw02_compiler import (
    DraftCompilationError,
    compile_golden_drafts,
    compile_section_draft,
)

CORPUS = Path(__file__).parent / "fixtures" / "typed_worker" / "exp_tw00_cbl" / "corpus.json"
GOLDENS = (
    Path(__file__).parent / "fixtures" / "typed_worker" / "exp_tw01_cbl" / "golden_drafts.json"
)


def test_both_golden_drafts_compile_to_canonical_intent() -> None:
    """Compile both frozen sections after structural and Gate A validation."""
    compiled = compile_golden_drafts(corpus_path=CORPUS, drafts_path=GOLDENS)

    assert set(compiled) == {"main_pass", "repeat_pass"}
    for section_id, result in compiled.items():
        section = result.intent.sections[0]
        assert section.title == f"{section_id.replace('_', ' ').title()} CBL/VDL"
        assert result.normalized_projection["source_candidate"] == (
            "source-1" if section_id == "main_pass" else "source-2"
        )
        assert section.data_source is not None
        assert section.data_source.source_path.endswith(
            "CBL_Main.dlis" if section_id == "main_pass" else "CBL_Repeat.dlis"
        )


def test_compilation_is_deterministic_and_preserves_semantic_order() -> None:
    """Repeated compilation produces identical intent and review projections."""
    corpus = load_corpus(CORPUS)
    draft = load_golden_drafts(GOLDENS)["main_pass"]
    requirements = corpus.gate_a["section_requirements"]["main_pass"]

    first = compile_section_draft(
        draft,
        section_context=corpus.sections[0],
        requirements=requirements,
    )
    second = compile_section_draft(
        draft,
        section_context=corpus.sections[0],
        requirements=requirements,
    )

    assert first.intent.model_dump(mode="json") == second.intent.model_dump(mode="json")
    assert first.normalized_projection == second.normalized_projection
    section = first.intent.sections[0]
    assert [track.title for track in section.tracks or []] == [
        "Combo",
        "Depth",
        "CBL",
        "VDL",
    ]
    cbl_bindings = (section.tracks or [])[2].bindings
    assert [binding.channel for binding in cbl_bindings or []] == ["CBL", "CBL"]
    assert [
        (binding.kind, binding.channel) for binding in (section.tracks or [])[3].bindings or []
    ] == [("raster", "VDL")]


def test_gate_a_invalid_draft_is_rejected_before_compiler_output() -> None:
    """Reject semantic invalidity before constructing any canonical intent."""
    corpus = load_corpus(CORPUS)
    draft = load_golden_drafts(GOLDENS)["main_pass"].model_copy(
        update={"source_candidate": "source-missing"}
    )

    with pytest.raises(DraftCompilationError, match="Gate A") as error:
        compile_section_draft(
            draft,
            section_context=corpus.sections[0],
            requirements=corpus.gate_a["section_requirements"]["main_pass"],
        )
    assert error.value.code == "gate_a_invalid"


def test_structurally_invalid_or_unrepresentable_values_fail_explicitly() -> None:
    """Reject unsupported semantic values instead of normalizing or repairing them."""
    corpus = load_corpus(CORPUS)
    raw = load_golden_drafts(GOLDENS)["main_pass"].model_dump(mode="json")
    raw["tracks"][0]["kind"] = "annotation"
    with pytest.raises(ValidationError):
        compile_section_draft(
            raw,
            section_context=corpus.sections[0],
            requirements=corpus.gate_a["section_requirements"]["main_pass"],
        )

    source = corpus.sections[0].sources[0].model_copy(update={"source_format": "unsupported"})
    unrepresentable_context = corpus.sections[0].model_copy(update={"sources": (source,)})
    with pytest.raises(DraftCompilationError, match="AuthoringDataSource") as error:
        compile_section_draft(
            load_golden_drafts(GOLDENS)["main_pass"],
            section_context=unrepresentable_context,
            requirements=corpus.gate_a["section_requirements"]["main_pass"],
        )
    assert error.value.code == "source_unrepresentable"


def test_review_projection_contains_semantics_without_provider_or_path_fields() -> None:
    """Keep compiler review output path-free and provider-neutral."""
    compiled = compile_golden_drafts(corpus_path=CORPUS, drafts_path=GOLDENS)
    serialized = json.dumps(
        {section_id: result.normalized_projection for section_id, result in compiled.items()},
        sort_keys=True,
    ).lower()

    assert "source-1" in serialized
    assert "source-2" in serialized
    assert "cbl_main.dlis" not in serialized
    assert "cbl_repeat.dlis" not in serialized
    for prohibited in ("provider", "prompt", "retry", "repair", "matplotlib", "renderer"):
        assert prohibited not in serialized
