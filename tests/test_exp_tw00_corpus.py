"""Tests for the EXP-TW-00 frozen typed-worker corpus."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.exp_tw00_corpus import load_corpus, replay_worker_projection, score_section_draft

CORPUS = Path(__file__).parents[0] / "fixtures" / "typed_worker" / "exp_tw00_cbl" / "corpus.json"


def test_corpus_replays_full_report_and_two_section_contexts_without_discovery() -> None:
    """Replay the complete report and two section worker contexts offline."""
    corpus = load_corpus(CORPUS)

    assert corpus.baseline_sha == "48fafb958b85069295f88fc249b3b9b68158c52a"
    assert corpus.fixture_version == "exp-tw-00.cbl.v1"
    assert corpus.plan.report_task is not None
    assert len(corpus.plan.section_tasks) == 2
    assert len(corpus.sections) == 2
    assert tuple(section.task_index for section in corpus.sections) == (0, 1)
    assert [source.candidate_id for section in corpus.sections for source in section.sources] == [
        "source-1",
        "source-2",
    ]
    report_task, report_context, section_tasks, section_contexts = replay_worker_projection(CORPUS)
    assert report_task is not None
    assert report_context.header_slots
    assert len(section_tasks) == len(section_contexts) == 2


def test_model_facing_projection_contains_no_paths_or_path_like_source_hints() -> None:
    """Keep canonical source paths out of the model-facing projection."""
    payload = json.loads(CORPUS.read_text(encoding="utf-8"))
    projection = payload["worker_projection"]
    serialized = json.dumps(projection, sort_keys=True)

    assert "source_path" not in serialized
    assert "canonical_path" not in serialized
    assert "CBL_Main.dlis" not in serialized
    assert "CBL_Repeat.dlis" not in serialized
    assert "workspace/data" not in serialized
    assert payload["host_only"]["source_paths"]


def test_gate_a_preserves_source_scope_and_repeated_binding_multiplicity() -> None:
    """Score selected-source validity and preserve repeated CBL bindings."""
    corpus = load_corpus(CORPUS)
    requirements = corpus.gate_a["section_requirements"]["main_pass"]
    context = corpus.sections[0]
    valid = {
        "title": "Main Pass",
        "source_candidate": "source-1",
        "tracks": requirements["tracks"],
    }
    result = score_section_draft(valid, section_context=context, requirements=requirements)
    assert result == {
        "host_reference_valid": True,
        "channel_valid": True,
        "semantic_usable": True,
    }
    assert [binding["channel"] for binding in valid["tracks"][2]["bindings"]] == ["CBL", "CBL"]

    invalid = {
        **valid,
        "source_candidate": "source-unknown",
    }
    assert (
        score_section_draft(invalid, section_context=context, requirements=requirements)[
            "host_reference_valid"
        ]
        is False
    )


def test_gate_a_rejects_wrong_selected_source_and_channel_kind() -> None:
    """Reject unknown sources and array/scalar binding mismatches."""
    corpus = load_corpus(CORPUS)
    requirements = corpus.gate_a["section_requirements"]["main_pass"]
    source = corpus.sections[0].sources[0]
    context = corpus.sections[0].model_copy(
        update={
            "sources": (
                source.model_copy(
                    update={
                        "candidate_id": "source-2",
                        "channels": tuple(
                            channel for channel in source.channels if channel.mnemonic != "CBL"
                        ),
                    }
                ),
            )
        }
    )
    invalid = {
        "title": "Main Pass",
        "source_candidate": "source-2",
        "tracks": [
            {
                "kind": "array",
                "bindings": [{"kind": "raster", "channel": "CBL"}],
            }
        ],
    }
    result = score_section_draft(invalid, section_context=context, requirements=requirements)
    assert result["host_reference_valid"] is True
    assert result["channel_valid"] is False
    assert result["semantic_usable"] is False
