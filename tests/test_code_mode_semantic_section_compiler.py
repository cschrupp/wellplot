"""CM-55 tests for typed semantic section models and compilation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from wellplot.agent.code_mode.enrichment import (
    ChannelContext,
    ResolvedSectionContext,
    SourceContext,
)
from wellplot.agent.code_mode.section_semantics import (
    ArrayTrackSemanticDraft,
    CurveBindingSemanticDraft,
    NormalTrackSemanticDraft,
    RasterBindingSemanticDraft,
    ReferenceTrackSemanticDraft,
    SectionSemanticDraft,
    SectionSemanticErrorCode,
    SectionSemanticValidationError,
    SemanticRasterProfile,
    SemanticSampleAxis,
    SemanticScale,
    SemanticScaleKind,
    validate_section_semantics,
)
from wellplot.agent.code_mode.semantic_section_compiler import compile_section_semantics
from wellplot.model.authoring import AuthoringDocumentSpec

GOLDEN_PATH = Path("tests/fixtures/typed_worker/exp_tw02r_cbl/golden_drafts.json")


def _document() -> AuthoringDocumentSpec:
    """Build a document whose identities seed the compiler allocator."""
    return AuthoringDocumentSpec(
        name="cm-55",
        sections=[
            {
                "id": "existing",
                "title": "Existing",
                "tracks": [
                    {
                        "id": "track-existing",
                        "title": "Existing",
                        "kind": "normal",
                        "width_mm": 20,
                    }
                ],
            }
        ],
    )


def _source(
    candidate_id: str = "source-1",
    *,
    path: str = "/host/input/main.las",
    channels: tuple[ChannelContext, ...] | None = None,
) -> SourceContext:
    """Build one bounded source context with scalar and array channels."""
    return SourceContext(
        candidate_id=candidate_id,
        canonical_path=path,
        source_format="las",
        channels=channels
        or (
            ChannelContext(mnemonic="GR", kind="scalar"),
            ChannelContext(mnemonic="CBL", kind="scalar"),
            ChannelContext(mnemonic="VDL", kind="array", shape=(64,)),
        ),
    )


def _context(
    *sources: SourceContext,
    section_id: str | None = None,
) -> ResolvedSectionContext:
    """Build a new-section context unless an existing target is requested."""
    return ResolvedSectionContext(
        task_index=0,
        section_id=section_id,
        sources=sources or (_source(),),
    )


def _normal_draft(
    *,
    source_candidate: str = "source-1",
    channel: str = "GR",
    scale: SemanticScale | None = None,
    semantic_id: str = "gamma_ray",
) -> SectionSemanticDraft:
    """Build a minimal structurally valid normal section draft."""
    return SectionSemanticDraft(
        title="Gamma Ray",
        source_candidate=source_candidate,
        tracks=(
            NormalTrackSemanticDraft(
                semantic_id="normal_track",
                kind="normal",
                title="Gamma Ray",
                bindings=(
                    CurveBindingSemanticDraft(
                        semantic_id=semantic_id,
                        channel=channel,
                        scale=scale,
                    ),
                ),
            ),
        ),
    )


def _golden_drafts() -> dict[str, SectionSemanticDraft]:
    """Load the unchanged TW-02R golden semantics through production models."""
    payload = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    production_payload: dict[str, object] = {}
    for section_key, raw_section in payload.items():
        section = dict(raw_section)
        production_tracks = []
        for raw_track in section["tracks"]:
            track = dict(raw_track)
            track["semantic_id"] = track.pop("role")
            production_tracks.append(track)
        section["tracks"] = production_tracks
        production_payload[section_key] = section
    return {
        key: SectionSemanticDraft.model_validate(value) for key, value in production_payload.items()
    }


def _cbl_context(section_key: str) -> ResolvedSectionContext:
    """Build the source-scoped context required by both frozen CBL drafts."""
    channels = tuple(
        ChannelContext(mnemonic=mnemonic, kind="array" if mnemonic == "VDL" else "scalar")
        for mnemonic in (
            "ECGR_STGC",
            "TT",
            "TENS",
            "MTEM",
            "STIT",
            "TDSP",
            "VSEC",
            "CBL",
            "VDL",
        )
    )
    candidate_id = "source-1" if section_key == "main_pass" else "source-2"
    return _context(
        _source(
            candidate_id,
            path=f"/host/input/{section_key}.dlis",
            channels=channels,
        )
    )


@pytest.mark.parametrize(
    "track_type",
    [NormalTrackSemanticDraft, ReferenceTrackSemanticDraft, ArrayTrackSemanticDraft],
)
def test_track_discriminators_are_required(track_type: type[object]) -> None:
    """The schema keeps the TW-08-required track tags required."""
    schema = track_type.model_json_schema()  # type: ignore[attr-defined]
    assert "kind" in schema["required"]
    assert "default" not in schema["properties"]["kind"]


def test_structural_schema_is_strict_and_preserves_branch_shapes() -> None:
    """Strict models reject extras and cross-kind binding shapes."""
    with pytest.raises(ValidationError):
        SectionSemanticDraft.model_validate(
            {
                "title": "Gamma Ray",
                "source_candidate": "source-1",
                "unexpected": True,
                "tracks": [],
            }
        )

    with pytest.raises(ValidationError):
        SectionSemanticDraft.model_validate(
            {
                "title": "Gamma Ray",
                "source_candidate": "source-1",
                "tracks": [
                    {
                        "semantic_id": "normal",
                        "kind": "normal",
                        "title": "Normal",
                        "bindings": [
                            {
                                "kind": "raster",
                                "semantic_id": "array",
                                "channel": "VDL",
                            }
                        ],
                    }
                ],
            }
        )

    with pytest.raises(ValidationError):
        SectionSemanticDraft.model_validate(
            {
                "title": "Array",
                "source_candidate": "source-1",
                "tracks": [
                    {
                        "semantic_id": "array",
                        "kind": "array",
                        "title": "Array",
                        "bindings": [{"kind": "curve", "semantic_id": "curve", "channel": "GR"}],
                    }
                ],
            }
        )

    with pytest.raises(ValidationError):
        SectionSemanticDraft.model_validate(
            {
                "title": "Array",
                "source_candidate": "source-1",
                "tracks": [
                    {
                        "semantic_id": "array",
                        "kind": "array",
                        "title": "Array",
                        "bindings": [{"kind": "raster", "semantic_id": "raster", "channel": "VDL"}],
                    }
                ],
            }
        )


def test_array_requires_x_scale_and_ids_are_nonempty() -> None:
    """The validated core rejects missing array x-scales and empty identities."""
    with pytest.raises(ValidationError):
        SectionSemanticDraft.model_validate(
            {
                "title": "Array",
                "source_candidate": "source-1",
                "tracks": [
                    {
                        "semantic_id": "array",
                        "kind": "array",
                        "title": "Array",
                        "bindings": [{"semantic_id": "raster", "channel": "VDL"}],
                    }
                ],
            }
        )

    with pytest.raises(ValidationError):
        _normal_draft(semantic_id="")


@pytest.mark.parametrize("section_key", ["main_pass", "repeat_pass"])
def test_tw_golden_drafts_compile_through_production_models(section_key: str) -> None:
    """Both frozen TW-02R drafts pass the production validation/compiler path."""
    intent = compile_section_semantics(
        _golden_drafts()[section_key],
        section_context=_cbl_context(section_key),
        document=_document(),
    )
    section = intent.sections[0]
    assert section.title == ("Main Pass" if section_key == "main_pass" else "Repeat Pass")
    assert section.data_source is not None
    assert section.data_source.source_path.endswith(f"{section_key}.dlis")
    assert [track.title for track in section.tracks or []] == [
        "Combo",
        "Depth",
        "CBL Amplitude",
        "VDL",
    ]
    assert [binding.channel for binding in section.tracks[2].bindings or []] == ["CBL", "CBL"]
    assert section.tracks[3].bindings[0].kind == "raster"


def test_compilation_is_deterministic_and_allocates_host_ids() -> None:
    """Identical inputs produce identical sparse intent and host-owned IDs."""
    draft = _normal_draft()
    context = _context(_source())
    first = compile_section_semantics(draft, section_context=context, document=_document())
    second = compile_section_semantics(draft, section_context=context, document=_document())

    assert first == second
    section = first.sections[0]
    track = section.tracks[0]
    binding = track.bindings[0]
    assert section.section_id != draft.title
    assert track.track_id != draft.tracks[0].semantic_id
    assert binding.binding_id != draft.tracks[0].bindings[0].semantic_id


def test_repeated_channels_and_order_are_preserved_without_defaults() -> None:
    """Sparse compilation preserves order/multiplicity and omits absent semantics."""
    draft = SectionSemanticDraft(
        title="Gamma Ray",
        source_candidate="source-1",
        tracks=(
            NormalTrackSemanticDraft(
                semantic_id="normal_track",
                kind="normal",
                title="Gamma Ray",
                bindings=(
                    CurveBindingSemanticDraft(semantic_id="first", channel="CBL"),
                    CurveBindingSemanticDraft(semantic_id="second", channel="CBL"),
                ),
            ),
        ),
    )
    intent = compile_section_semantics(
        draft,
        section_context=_context(_source()),
        document=_document(),
    )
    payload = intent.model_dump(mode="json", exclude_unset=True)
    track = payload["sections"][0]["tracks"][0]
    assert [binding["channel"] for binding in track["bindings"]] == ["CBL", "CBL"]
    assert track["bindings"][0]["binding_id"] != track["bindings"][1]["binding_id"]
    assert "x_scale" not in track
    assert "scale" not in track["bindings"][0]
    assert "width_mm" not in track
    assert "style" not in track["bindings"][0]


def test_scale_profile_and_sample_axis_semantics_compile_without_renderer_policy() -> None:
    """Generalized scale/profile fields map directly without style invention."""
    draft = SectionSemanticDraft(
        title="Array",
        source_candidate="source-1",
        tracks=(
            ArrayTrackSemanticDraft(
                semantic_id="array",
                kind="array",
                title="Waveform",
                x_scale=SemanticScale(
                    kind=SemanticScaleKind.TANGENTIAL,
                    minimum=1,
                    maximum=10,
                    reverse=True,
                    unit="ms",
                ),
                bindings=(
                    RasterBindingSemanticDraft(
                        semantic_id="waveform",
                        channel="VDL",
                        profile=SemanticRasterProfile.WAVEFORM,
                        sample_axis=SemanticSampleAxis(
                            unit="us",
                            minimum=200,
                            maximum=1200,
                            tick_count=7,
                            source_origin=40,
                            source_step=10,
                        ),
                    ),
                ),
            ),
        ),
    )
    intent = compile_section_semantics(
        draft,
        section_context=_context(_source()),
        document=_document(),
    )
    track = intent.sections[0].tracks[0]
    binding = track.bindings[0]
    assert track.x_scale is not None
    assert track.x_scale.kind == SemanticScaleKind.TANGENTIAL
    assert track.x_scale.reverse is True
    assert binding.profile == SemanticRasterProfile.WAVEFORM
    assert binding.sample_axis is not None
    assert binding.sample_axis.enabled is True
    assert binding.sample_axis.tick_count == 7


@pytest.mark.parametrize(
    ("kind", "minimum", "maximum"),
    [(SemanticScaleKind.LOG, 0, 10), (SemanticScaleKind.LINEAR, 10, 10)],
)
def test_scale_validation_reuses_canonical_bound_rules(
    kind: SemanticScaleKind,
    minimum: float,
    maximum: float,
) -> None:
    """Invalid scale bounds fail before context compilation."""
    with pytest.raises(ValidationError):
        SemanticScale(kind=kind, minimum=minimum, maximum=maximum)


def test_context_validation_rejects_unknown_source_and_wrong_source_channel() -> None:
    """Source and channel truth is checked against the selected source only."""
    with pytest.raises(SectionSemanticValidationError) as missing_source:
        validate_section_semantics(
            _normal_draft(source_candidate="source-2"),
            section_context=_context(_source()),
        )
    assert missing_source.value.code is SectionSemanticErrorCode.SOURCE_CANDIDATE_MISSING

    source_one = _source("source-1", channels=(ChannelContext(mnemonic="GR", kind="scalar"),))
    source_two = _source("source-2", channels=(ChannelContext(mnemonic="CBL", kind="scalar"),))
    with pytest.raises(SectionSemanticValidationError) as missing_channel:
        validate_section_semantics(
            _normal_draft(channel="CBL"),
            section_context=_context(source_one, source_two),
        )
    assert missing_channel.value.code is SectionSemanticErrorCode.CHANNEL_MISSING


def test_context_validation_rejects_channel_kind_mismatch_and_duplicate_semantics() -> None:
    """Scalar/array truth and semantic identity uniqueness remain contextual."""
    with pytest.raises(SectionSemanticValidationError) as mismatch:
        validate_section_semantics(
            _normal_draft(channel="VDL"),
            section_context=_context(_source()),
        )
    assert mismatch.value.code is SectionSemanticErrorCode.CHANNEL_KIND_MISMATCH

    duplicate_track = SectionSemanticDraft(
        title="Duplicate",
        source_candidate="source-1",
        tracks=(
            NormalTrackSemanticDraft(
                semantic_id="same",
                kind="normal",
                title="One",
                bindings=(CurveBindingSemanticDraft(semantic_id="one", channel="GR"),),
            ),
            NormalTrackSemanticDraft(
                semantic_id="same",
                kind="normal",
                title="Two",
                bindings=(CurveBindingSemanticDraft(semantic_id="two", channel="GR"),),
            ),
        ),
    )
    with pytest.raises(SectionSemanticValidationError) as duplicate:
        validate_section_semantics(duplicate_track, section_context=_context(_source()))
    assert duplicate.value.code is SectionSemanticErrorCode.DUPLICATE_TRACK_ID

    duplicate_binding = SectionSemanticDraft(
        title="Duplicate",
        source_candidate="source-1",
        tracks=(
            NormalTrackSemanticDraft(
                semantic_id="normal",
                kind="normal",
                title="One",
                bindings=(
                    CurveBindingSemanticDraft(semantic_id="same", channel="GR"),
                    CurveBindingSemanticDraft(semantic_id="same", channel="CBL"),
                ),
            ),
        ),
    )
    with pytest.raises(SectionSemanticValidationError) as duplicate:
        validate_section_semantics(duplicate_binding, section_context=_context(_source()))
    assert duplicate.value.code is SectionSemanticErrorCode.DUPLICATE_BINDING_ID


def test_existing_section_revision_is_explicitly_deferred() -> None:
    """CM-55 does not turn new-section compilation into implicit revision."""
    with pytest.raises(SectionSemanticValidationError) as error:
        compile_section_semantics(
            _normal_draft(),
            section_context=_context(_source(), section_id="existing"),
            document=_document(),
        )
    assert error.value.code is SectionSemanticErrorCode.REVISION_UNSUPPORTED


def test_semantic_models_are_path_free() -> None:
    """Worker-facing models contain no host path or renderer/provider fields."""
    draft = _normal_draft()
    payload = draft.model_dump(mode="json")
    serialized = json.dumps(payload, sort_keys=True)
    assert "/host/input" not in serialized
    assert "canonical_path" not in serialized
    assert "matplotlib" not in serialized
    assert "provider" not in serialized
