"""Focused EXP-TW-02I typed-input and provenance tests."""

from __future__ import annotations

import json

import pytest
from scripts.exp_tw02i_input import (
    audit_worker_input_provenance,
    build_typed_worker_input,
    serialize_provider_input,
)


@pytest.mark.parametrize("section_role", ["main_pass", "repeat_pass"])
def test_frozen_sections_have_complete_worker_input_provenance(section_role: str) -> None:
    """Every Gate-A-scored worker-owned field has typed provider evidence."""
    bundle = build_typed_worker_input(section_role)  # type: ignore[arg-type]
    audit = audit_worker_input_provenance(bundle)

    assert audit.valid is True
    assert audit.missing_output_paths == ()
    assert len(audit.records) > 30


def test_provider_input_exposes_the_corrected_scientific_semantics() -> None:
    """Scales, repeated CBL views, and VDL semantics are explicit inputs."""
    task = build_typed_worker_input("main_pass").task

    assert task.title == "Main Pass"
    assert task.source_candidate == "source-1"
    assert [track.role for track in task.tracks] == ["combo", "depth", "cbl", "vdl"]
    assert [binding.semantic_id for binding in task.tracks[0].bindings] == [
        "ecgr",
        "tt",
        "tension",
        "temperature",
    ]
    assert task.tracks[0].bindings[0].scale.maximum == 150
    assert task.tracks[0].bindings[1].scale.reverse is True

    cbl_bindings = task.tracks[2].bindings
    assert [binding.semantic_id for binding in cbl_bindings] == [
        "cbl_0_100",
        "cbl_0_10",
    ]
    assert [binding.scale.maximum for binding in cbl_bindings] == [100, 10]

    vdl = task.tracks[3]
    assert vdl.x_scale is not None
    assert (vdl.x_scale.minimum, vdl.x_scale.maximum) == (200, 1200)
    raster = vdl.bindings[0]
    assert raster.profile == "vdl"
    assert raster.sample_axis.unit == "us"
    assert (raster.sample_axis.minimum, raster.sample_axis.maximum) == (200, 1200)
    assert raster.sample_axis.tick_count == 7
    assert (raster.sample_axis.source_origin, raster.sample_axis.source_step) == (40, 10)


def test_complete_provider_input_is_deterministic_and_path_free() -> None:
    """The future provider boundary serializes stably without host details."""
    first = serialize_provider_input(build_typed_worker_input("repeat_pass"))
    second = serialize_provider_input(build_typed_worker_input("repeat_pass"))

    assert first == second
    assert "CBL_Main.dlis" not in first
    assert "CBL_Repeat.dlis" not in first
    assert ".dlis" not in first.lower()
    assert "canonical_path" not in first
    assert "source_path" not in first
    assert "width_mm" not in first
    assert "CBL Amplitude (CBL) QSLT-B" not in first
    assert "#111111" not in first
    assert "#2563eb" not in first
    assert "gray_r" not in first
    assert "binding_id" not in first
    assert "exp-tw02" not in first
    assert "provider" not in first.lower()
    assert "retry" not in first.lower()
    assert "repair" not in first.lower()


def test_missing_worker_input_provenance_fails_at_the_reported_output_path() -> None:
    """Removing one typed input value cannot fall back to the golden output."""
    bundle = build_typed_worker_input("main_pass")
    raw = bundle.model_dump(mode="json")
    raw["task"]["tracks"][3]["bindings"][0]["sample_axis"].pop("source_step")

    audit = audit_worker_input_provenance(raw)

    assert audit.valid is False
    assert (
        "SectionDraft.tracks[vdl].bindings[vdl].sample_axis.source_step"
        in audit.missing_output_paths
    )


def test_provenance_records_are_reviewable_without_being_provider_input() -> None:
    """Audit evidence names frozen sources while the serialized bundle stays clean."""
    bundle = build_typed_worker_input("main_pass")
    audit = audit_worker_input_provenance(bundle)
    serialized_bundle = json.dumps(bundle.model_dump(mode="json"), sort_keys=True)
    serialized_audit = audit.model_dump_json()

    assert "merged_intent.sections[main_pass]" in serialized_audit
    assert "task.tracks[vdl].bindings[vdl].sample_axis.source_step" in serialized_audit
    assert "merged_intent.sections[main_pass]" not in serialized_bundle
