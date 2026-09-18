"""Tests for the schema-only EXP-TW-01 typed semantic draft."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from scripts.exp_tw00_corpus import load_corpus, score_section_draft
from scripts.exp_tw01_schema import (
    RasterBindingDraft,
    SectionDraft,
    load_golden_drafts,
    score_golden_drafts,
)

CORPUS = Path(__file__).parent / "fixtures" / "typed_worker" / "exp_tw00_cbl" / "corpus.json"
GOLDENS = (
    Path(__file__).parent / "fixtures" / "typed_worker" / "exp_tw01_cbl" / "golden_drafts.json"
)


def test_golden_drafts_validate_and_pass_exp_tw00_gate_a() -> None:
    """Validate both manually authored drafts through the frozen Gate A scorer."""
    drafts = load_golden_drafts(GOLDENS)

    assert set(drafts) == {"main_pass", "repeat_pass"}
    assert score_golden_drafts(corpus_path=CORPUS, drafts_path=GOLDENS) == {
        "main_pass": {
            "host_reference_valid": True,
            "channel_valid": True,
            "semantic_usable": True,
        },
        "repeat_pass": {
            "host_reference_valid": True,
            "channel_valid": True,
            "semantic_usable": True,
        },
    }


def test_draft_json_round_trip_is_deterministic_and_preserves_order_and_multiplicity() -> None:
    """Preserve semantic ordering and the repeated CBL binding on round-trip."""
    draft = load_golden_drafts(GOLDENS)["main_pass"]
    encoded = draft.model_dump_json()
    round_tripped = SectionDraft.model_validate_json(encoded)

    assert round_tripped == draft
    assert [track.kind for track in round_tripped.tracks] == [
        "normal",
        "reference",
        "normal",
        "array",
    ]
    cbl_bindings = round_tripped.tracks[2].bindings
    assert [binding.channel for binding in cbl_bindings] == ["CBL", "CBL"]
    assert json.dumps(round_tripped.model_dump(mode="json"), separators=(",", ":")) == json.dumps(
        draft.model_dump(mode="json"), separators=(",", ":")
    )


@pytest.mark.parametrize(
    ("variant", "expected"),
    [
        ("missing_source", "host_reference_valid"),
        ("missing_channel", "channel_valid"),
        ("wrong_binding_shape", "channel_valid"),
        ("collapsed_cbl", "semantic_usable"),
        ("reordered_tracks", "semantic_usable"),
    ],
)
def test_malformed_drafts_fail_gate_a_for_the_intended_reason(
    variant: str,
    expected: str,
) -> None:
    """Reject each required semantic defect at the deterministic Gate A boundary."""
    corpus = load_corpus(CORPUS)
    draft = load_golden_drafts(GOLDENS)["main_pass"]
    malformed = _malformed_variant(draft, variant)
    result = score_section_draft(
        malformed.model_dump(mode="json"),
        section_context=corpus.sections[0],
        requirements=corpus.gate_a["section_requirements"]["main_pass"],
    )

    assert result[expected] is False
    assert result["semantic_usable"] is False


def test_schema_rejects_implementation_fields_and_does_not_advertise_them() -> None:
    """Keep host, renderer, and provider mechanics out of the worker schema."""
    with pytest.raises(ValidationError):
        SectionDraft.model_validate(
            {
                "title": "CBL",
                "source_candidate": "source-1",
                "tracks": [],
                "source_path": "/secret/CBL.dlis",
                "provider": "openai_compat",
            }
        )

    schema_text = json.dumps(SectionDraft.model_json_schema(), sort_keys=True).lower()
    serialized = GOLDENS.read_text(encoding="utf-8").lower()
    for prohibited in (
        "source_path",
        "canonical_path",
        "matplotlib",
        "renderer",
        "provider",
        "prompt",
        "retry",
        "repair",
        "width_mm",
        "height_mm",
        "line_style",
        "color",
        "layout",
        "coordinate",
    ):
        assert prohibited not in schema_text
        assert prohibited not in serialized


def _malformed_variant(draft: SectionDraft, variant: str) -> SectionDraft:
    """Create one deterministic invalid semantic variant for Gate A tests."""
    if variant == "missing_source":
        return draft.model_copy(update={"source_candidate": "source-missing"})
    if variant == "missing_channel":
        combo = draft.tracks[0].model_copy(
            update={
                "bindings": (
                    draft.tracks[0].bindings[0].model_copy(update={"channel": "MISSING"}),
                    *draft.tracks[0].bindings[1:],
                )
            }
        )
        return draft.model_copy(update={"tracks": (combo, *draft.tracks[1:])})
    if variant == "wrong_binding_shape":
        vdl = draft.tracks[3].model_copy(
            update={
                "bindings": (RasterBindingDraft(channel="CBL"),),
            }
        )
        return draft.model_copy(update={"tracks": (*draft.tracks[:3], vdl)})
    if variant == "collapsed_cbl":
        cbl = draft.tracks[2].model_copy(update={"bindings": draft.tracks[2].bindings[:1]})
        return draft.model_copy(update={"tracks": (*draft.tracks[:2], cbl, draft.tracks[3])})
    if variant == "reordered_tracks":
        return draft.model_copy(
            update={"tracks": (draft.tracks[1], draft.tracks[0], *draft.tracks[2:])}
        )
    raise AssertionError(f"Unknown malformed draft variant: {variant}")
