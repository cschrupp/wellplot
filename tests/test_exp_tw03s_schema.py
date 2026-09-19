"""Focused EXP-TW-03S strengthened-schema tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from scripts.exp_tw02r_contract import (
    CurveBindingDraft,
    ScaleDraft,
    SectionDraft,
    load_golden_drafts,
)
from scripts.exp_tw03_provider import (
    AttemptConfig,
    AttemptOutcome,
    FirstAttemptEvidence,
    GateAEvidence,
)
from scripts.exp_tw03s_schema import (
    ArrayTrackDraftS,
    NormalTrackDraftS,
    ReferenceTrackDraftS,
    SectionDraftS,
    replay_evidence_file,
    strengthen_draft,
    strengthen_golden_drafts,
)


def _golden_payload(section_key: str = "main_pass") -> dict[str, object]:
    """Return one historical golden as a serialized mapping."""
    return load_golden_drafts()[section_key].model_dump(mode="json")


def _curve_binding() -> dict[str, object]:
    """Return a minimal semantic curve binding."""
    return {
        "semantic_id": "arbitrary-curve",
        "channel": "ARBITRARY",
        "scale": {"minimum": -10, "maximum": 10, "reverse": True},
    }


def _raster_binding() -> dict[str, object]:
    """Return a minimal semantic raster binding."""
    return {
        "semantic_id": "arbitrary-raster",
        "channel": "ARRAY_CHANNEL",
        "profile": "vdl",
        "sample_axis": {
            "unit": "samples",
            "minimum": -1,
            "maximum": 1,
            "tick_count": 2,
            "source_origin": 0,
            "source_step": 1,
        },
    }


def _track_payload(
    kind: str,
    binding: dict[str, object],
    *,
    role: str = "combo",
) -> dict[str, object]:
    """Return a structurally isolated track payload."""
    payload: dict[str, object] = {
        "role": role,
        "kind": kind,
        "title": "Arbitrary title",
        "bindings": [binding],
    }
    if kind == "array":
        payload["x_scale"] = {"minimum": -2, "maximum": 3, "reverse": True}
    return payload


def _section_with_track(track: dict[str, object]) -> dict[str, object]:
    """Return a semantically arbitrary section around one track."""
    return {
        "title": "Not a frozen title",
        "source_candidate": "not-a-frozen-source",
        "tracks": [track],
    }


def test_frozen_goldens_validate_unchanged_under_strengthened_schema() -> None:
    """Both corrected frozen outputs remain representable without mutation."""
    historical = load_golden_drafts()
    strengthened = strengthen_golden_drafts()

    assert set(strengthened) == {"main_pass", "repeat_pass"}
    for section_key, draft in strengthened.items():
        assert draft.model_dump(mode="json") == historical[section_key].model_dump(mode="json")


def test_normal_reference_and_array_track_contracts_validate() -> None:
    """Each strengthened track variant accepts only its intended binding family."""
    normal = NormalTrackDraftS.model_validate(_track_payload("normal", _curve_binding()))
    reference = ReferenceTrackDraftS.model_validate(_track_payload("reference", _curve_binding()))
    array = ArrayTrackDraftS.model_validate(_track_payload("array", _raster_binding()))

    assert normal.kind == "normal"
    assert reference.kind == "reference"
    assert array.kind == "array"
    assert array.x_scale is not None


@pytest.mark.parametrize(
    ("kind", "binding", "error_fragment"),
    [
        ("normal", _raster_binding(), "normal"),
        ("reference", _raster_binding(), "reference"),
        ("array", _curve_binding(), "array"),
    ],
)
def test_incompatible_track_binding_kinds_are_structural_errors(
    kind: str,
    binding: dict[str, object],
    error_fragment: str,
) -> None:
    """Impossible track/binding combinations fail before Gate A."""
    with pytest.raises(ValidationError) as caught:
        SectionDraftS.model_validate(_section_with_track(_track_payload(kind, binding)))

    assert any(error_fragment in str(error["loc"]) for error in caught.value.errors())


def test_array_track_requires_explicit_x_scale() -> None:
    """Array-track x-scale omission is structural, not a semantic repair case."""
    payload = _track_payload("array", _raster_binding())
    del payload["x_scale"]

    with pytest.raises(ValidationError) as caught:
        SectionDraftS.model_validate(_section_with_track(payload))

    assert any(error["loc"][-1] == "x_scale" for error in caught.value.errors())


def test_strengthening_rejects_without_transforming_invalid_historical_draft() -> None:
    """A historical-style impossible shape is rejected, never repaired."""
    payload = _golden_payload()
    vdl_track = payload["tracks"][-1]
    assert isinstance(vdl_track, dict)
    vdl_track["bindings"][0]["kind"] = "curve"

    with pytest.raises(ValidationError):
        strengthen_draft(payload)

    assert vdl_track["bindings"][0]["kind"] == "curve"


@pytest.mark.parametrize(
    "change",
    [
        {"title": "Any other section"},
        {"source_candidate": "opaque-host-handle"},
        {"tracks": []},
    ],
)
def test_benchmark_semantics_are_not_structural_invariants(
    change: dict[str, object],
) -> None:
    """Title/source/track presence remain Gate-A concerns when structurally valid."""
    payload = _golden_payload()
    if "tracks" in change:
        payload["tracks"] = [_track_payload("normal", _curve_binding())]
    else:
        payload.update(change)

    strengthened = strengthen_draft(payload)
    assert strengthened.model_dump(mode="json")[next(iter(change))] == (
        payload[next(iter(change))]
        if next(iter(change)) != "tracks"
        else strengthened.model_dump(mode="json")["tracks"]
    )


def test_scale_and_reversal_values_are_preserved_without_benchmark_literals() -> None:
    """Arbitrary numeric scale values and reversals remain provider-owned semantics."""
    payload = _section_with_track(_track_payload("normal", _curve_binding()))
    strengthened = SectionDraftS.model_validate(payload)

    assert strengthened.tracks[0].bindings[0].scale.minimum == -10
    assert strengthened.tracks[0].bindings[0].scale.maximum == 10
    assert strengthened.tracks[0].bindings[0].scale.reverse is True


def test_historical_and_strengthened_schemas_share_track_role_domain() -> None:
    """The strengthening preserves historical role values without coupling them to kind."""
    payload = _section_with_track(_track_payload("normal", _curve_binding(), role="anything"))

    with pytest.raises(ValidationError):
        SectionDraft.model_validate(payload)
    with pytest.raises(ValidationError):
        SectionDraftS.model_validate(payload)


def test_semantic_track_order_remains_representable() -> None:
    """Track ordering is task semantics and remains outside schema validation."""
    payload = _golden_payload()
    payload["tracks"] = list(reversed(payload["tracks"]))

    strengthened = strengthen_draft(payload)

    assert [track["role"] for track in strengthened.model_dump(mode="json")["tracks"]] == [
        "vdl",
        "cbl",
        "depth",
        "combo",
    ]


def test_schema_has_no_host_or_provider_concepts() -> None:
    """The strengthened worker schema remains semantic and path-free."""
    schema_text = json.dumps(SectionDraftS.model_json_schema(), sort_keys=True).lower()

    for prohibited in (
        "canonical_path",
        "source_path",
        "matplotlib",
        "renderer",
        "provider",
        "binding_id",
        "layout",
    ):
        assert prohibited not in schema_text


def test_historical_schema_and_strengthened_schema_are_distinct() -> None:
    """TW-03 history remains available rather than being silently replaced."""
    historical = load_golden_drafts()["main_pass"]
    strengthened = strengthen_draft(historical)

    assert type(strengthened) is SectionDraftS
    assert type(strengthened) is not type(historical)


def test_replay_rejects_impossible_shapes_without_increasing_gate_a(
    tmp_path: Path,
) -> None:
    """Replay moves an impossible shape to structural failure without repair."""
    valid = load_golden_drafts()["main_pass"]
    vdl_track = valid.tracks[-1]
    invalid_vdl = vdl_track.model_copy(
        update={
            "bindings": (
                CurveBindingDraft(
                    semantic_id="vdl",
                    channel="VDL",
                    scale=ScaleDraft(minimum=200, maximum=1200),
                ),
            )
        }
    )
    invalid = valid.model_copy(update={"tracks": (*valid.tracks[:-1], invalid_vdl)})

    def evidence(
        attempt_index: int,
        draft: object,
        outcome: AttemptOutcome,
        semantic_usable: bool,
    ) -> dict[str, object]:
        """Build one redacted synthetic TW-03 attempt row."""
        row = FirstAttemptEvidence(
            section_role="main_pass",
            attempt_index=attempt_index,
            provider_id="fake",
            model_id="fake-model",
            provider_input_sha256="0" * 64,
            response_schema_sha256="1" * 64,
            request=AttemptConfig(timeout_seconds=30),
            outcome=outcome,
            draft=draft,
            gate_a=GateAEvidence(
                host_reference_valid=True,
                channel_valid=True,
                semantic_usable=semantic_usable,
                source_selection_valid=True,
                titles_valid=semantic_usable,
                semantic_fields_valid=semantic_usable,
            ),
        )
        return {"record_type": "attempt", **row.model_dump(mode="json")}

    evidence_path = tmp_path / "tw03.jsonl"
    evidence_path.write_text(
        "\n".join(
            json.dumps(row, sort_keys=True)
            for row in (
                evidence(1, valid, AttemptOutcome.SUCCESS, True),
                evidence(2, invalid, AttemptOutcome.GATE_A_FAILURE, False),
            )
        )
        + "\n",
        encoding="utf-8",
    )

    (summary,) = replay_evidence_file(evidence_path)

    assert summary.historical_attempts == 2
    assert summary.historical_gate_a_valid_count == 1
    assert summary.strengthened_structurally_valid_count == 1
    assert summary.structural_rejection_count == 1
    assert summary.gate_a_valid_count_after_strengthening == 1
    assert summary.prior_gate_a_failures_rejected_structurally == 1
    assert summary.prior_gate_a_failures_remaining_structurally_valid == 0
