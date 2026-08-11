"""Tests for deterministic authoring-context resolution."""

from __future__ import annotations

from wellplot.authoring_context import (
    AuthoringChannelAlias,
    AuthoringChannelCandidate,
    AuthoringContextIssue,
    AuthoringResolutionSource,
    build_authoring_context_snapshot,
    resolve_authoring_context,
)
from wellplot.model.authoring import (
    ArrayTrackSpec,
    AuthoringDocumentSpec,
    AuthoringHeaderFieldSpec,
    AuthoringHeaderSpec,
    AuthoringReportValueSpec,
    AuthoringStyle,
    CurveBindingSpec,
    NormalTrackSpec,
)
from wellplot.model.intent import (
    AuthoringCurveBindingIntent,
    AuthoringDocumentIntent,
    AuthoringHeaderFieldIntent,
    AuthoringSectionIntent,
    AuthoringTrackIntent,
)


def _document(*, width_mm: float = 40, track_kind: str = "normal") -> AuthoringDocumentSpec:
    """Build a small canonical document with stable header and binding IDs."""
    track = (
        ArrayTrackSpec(id="vdl", title="VDL", width_mm=width_mm)
        if track_kind == "array"
        else NormalTrackSpec(
            id="cbl",
            title="CBL",
            width_mm=width_mm,
            bindings=[
                CurveBindingSpec(
                    binding_id="cbl-1",
                    channel="CBL",
                    style=AuthoringStyle(color="black", line_width=1.2),
                )
            ],
        )
    )
    return AuthoringDocumentSpec(
        name="context-test",
        output={"dpi": 120},
        header=AuthoringHeaderSpec(
            general_fields=[
                AuthoringHeaderFieldSpec(
                    slot_id="general.well",
                    key="well",
                    label="Well",
                    value=AuthoringReportValueSpec(value="Existing-1"),
                )
            ]
        ),
        sections=[
            {
                "id": "main",
                "title": "Main",
                "tracks": [track],
            }
        ],
    )


def test_precedence_is_explicit_then_existing_then_defaults_then_scaffold() -> None:
    """Select fallback values without allowing defaults to overwrite existing state."""
    scaffold = _document(width_mm=55)
    intent = AuthoringDocumentIntent(
        output={"dpi": 240},
        sections=[
            {
                "section_id": "main",
                "tracks": [{"track_id": "cbl", "kind": "normal"}],
            }
        ],
    )
    result = resolve_authoring_context(
        intent,
        existing=_document(width_mm=40),
        scaffold=scaffold,
        defaults={"sections[main].tracks[cbl].width_mm": 30},
    )

    assert result.ready is True
    assert result.resolved_values["output.dpi"] == 240
    assert result.resolved_values["sections[main].tracks[cbl].width_mm"] == 40
    assert result.resolved_values["sections[main].tracks[cbl].kind"] == "normal"
    assert any(
        item.path == "sections[main].tracks[cbl].width_mm"
        and item.source == AuthoringResolutionSource.PRESERVED
        for item in result.decisions
    )


def test_defaults_win_over_scaffold_when_existing_state_is_absent() -> None:
    """Use a family/default value before a starter scaffold value."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [{"track_id": "cbl", "kind": "normal"}],
            }
        ]
    )
    result = resolve_authoring_context(
        intent,
        scaffold=_document(width_mm=55),
        defaults={"sections[main].tracks[cbl].width_mm": 30},
    )

    assert result.ready is True
    assert result.resolved_values["sections[main].tracks[cbl].width_mm"] == 30
    assert any(
        item.path == "sections[main].tracks[cbl].width_mm"
        and item.source == AuthoringResolutionSource.DEFAULT
        for item in result.decisions
    )


def test_nested_parent_scope_does_not_replace_child_identity() -> None:
    """Resolve defaults by local child ids when providers repeat parent scope."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "section_id": "main",
                        "track_id": "resistivity",
                        "bindings": [
                            {
                                "kind": "curve",
                                "section_id": "main",
                                "track_id": "resistivity",
                                "binding_id": "ild-1",
                                "channel": "ILD",
                            }
                        ],
                    }
                ],
            }
        ]
    )
    result = resolve_authoring_context(
        intent,
        defaults={
            "sections[main].tracks[resistivity].width_mm": 32.0,
            "sections[main].tracks[resistivity].bindings[ild-1].style": {
                "color": "black",
                "line_width": 1.3,
            },
        },
        available_channels={"main": ["ILD"]},
    )

    assert result.ready is True
    assert result.resolved_values[
        "sections[main].tracks[resistivity].width_mm"
    ] == 32.0
    assert result.resolved_values[
        "sections[main].tracks[resistivity].bindings[ild-1].style"
    ]["color"] == "black"
    assert not any("tracks[main]" in path for path in result.resolved_values)


def test_header_alias_resolves_to_existing_stable_slot() -> None:
    """Resolve visible header labels without inventing a new slot."""
    intent = AuthoringDocumentIntent(
        header={
            "general_fields": [
                AuthoringHeaderFieldIntent(
                    slot_id="Well",
                    value={"value": "FORGE-1"},
                )
            ]
        }
    )
    result = resolve_authoring_context(intent, existing=_document())

    assert result.ready is True
    assert result.resolved_intent.header is not None
    assert result.resolved_intent.header.general_fields[0].slot_id == "general.well"
    assert result.resolved_values["header.general_fields[general.well].value.value"] == "FORGE-1"


def test_channel_alias_resolves_and_preserves_explicit_curve_style() -> None:
    """Resolve a semantic channel alias while retaining explicit presentation values."""
    intent = AuthoringDocumentIntent(
        sections=[
            AuthoringSectionIntent(
                section_id="main",
                tracks=[
                    AuthoringTrackIntent(
                        track_id="cbl",
                        bindings=[
                            AuthoringCurveBindingIntent(
                                kind="curve",
                                binding_id="cbl-2",
                                channel="cement bond",
                                style={"color": "blue", "line_style": "--"},
                            )
                        ],
                    )
                ],
            )
        ]
    )
    result = resolve_authoring_context(
        intent,
        existing=_document(),
        available_channels={
            "main": [AuthoringChannelCandidate(mnemonic="CBL", kind="scalar")]
        },
        channel_aliases=[
            AuthoringChannelAlias(
                id="cement_bond",
                label="Cement Bond",
                aliases=["cbl"],
                mnemonics=["CBL"],
            )
        ],
    )

    assert result.ready is True
    binding = result.resolved_intent.sections[0].tracks[0].bindings[0]
    assert isinstance(binding, AuthoringCurveBindingIntent)
    assert binding.channel == "CBL"
    assert result.resolved_values[
        "sections[main].tracks[cbl].bindings[cbl-2].style.color"
    ] == "blue"


def test_nested_and_root_binding_references_are_coalesced() -> None:
    """Treat two scoped representations of one binding as one logical object."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "resistivity",
                        "kind": "normal",
                        "bindings": [
                            {
                                "kind": "curve",
                                "binding_id": "ild-1",
                                "channel": "ILD",
                            }
                        ],
                    }
                ],
            }
        ],
        curve_bindings=[
            {
                "kind": "curve",
                "binding_id": "ild-1",
                "section_id": "main",
                "track_id": "resistivity",
                "style": {"color": "black", "line_width": 1.1},
            }
        ],
    )

    result = resolve_authoring_context(
        intent,
        available_channels={"main": [{"mnemonic": "ILD", "kind": "scalar"}]},
    )

    assert result.ready is True
    assert result.resolved_intent.curve_bindings == []
    binding = result.resolved_intent.sections[0].tracks[0].bindings[0]
    assert isinstance(binding, AuthoringCurveBindingIntent)
    assert binding.channel == "ILD"
    assert binding.style is not None
    assert binding.style.color == "black"


def test_conflicting_nested_and_root_binding_references_block() -> None:
    """Do not silently choose between conflicting alternate declarations."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "resistivity",
                        "kind": "normal",
                        "bindings": [
                            {
                                "kind": "curve",
                                "binding_id": "ild-1",
                                "channel": "ILD",
                                "style": {"color": "black"},
                            }
                        ],
                    }
                ],
            }
        ],
        curve_bindings=[
            {
                "kind": "curve",
                "binding_id": "ild-1",
                "section_id": "main",
                "track_id": "resistivity",
                "style": {"color": "blue"},
            }
        ],
    )

    result = resolve_authoring_context(
        intent,
        available_channels={"main": [{"mnemonic": "ILD", "kind": "scalar"}]},
    )

    assert result.ready is False
    assert "duplicate_binding_definition" in {issue.code for issue in result.issues}


def test_missing_and_ambiguous_channels_block_resolution() -> None:
    """Do not invent a source channel when inspection is missing or ambiguous."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "cbl",
                        "kind": "normal",
                        "bindings": [
                            {"kind": "curve", "binding_id": "cbl-2", "channel": "cement bond"}
                        ],
                    }
                ],
            }
        ]
    )
    aliases = [
        {
            "id": "cement_bond",
            "label": "Cement Bond",
            "mnemonics": ["CBL", "CBLF"],
        }
    ]
    missing = resolve_authoring_context(
        intent,
        available_channels={"main": ["GR"]},
        channel_aliases=aliases,
    )
    ambiguous = resolve_authoring_context(
        intent,
        available_channels={"main": ["CBL", "CBLF"]},
        channel_aliases=aliases,
    )

    assert missing.ready is False
    assert {issue.code for issue in missing.issues} == {"channel_missing"}
    assert ambiguous.ready is False
    assert {issue.code for issue in ambiguous.issues} == {"channel_ambiguous"}


def test_compatibility_and_duplicate_identity_are_blocking() -> None:
    """Reject incompatible content and duplicate IDs while allowing duplicate channels."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "cbl",
                        "kind": "normal",
                        "bindings": [
                            {"kind": "curve", "binding_id": "same", "channel": "CBL"},
                            {"kind": "curve", "binding_id": "same", "channel": "CBL"},
                            {"kind": "raster", "binding_id": "vdl", "channel": "VDL"},
                        ],
                    }
                ],
            }
        ]
    )
    result = resolve_authoring_context(
        intent,
        available_channels={
            "main": [
                {"mnemonic": "CBL", "kind": "scalar"},
                {"mnemonic": "VDL", "kind": "array"},
            ]
        },
    )

    assert result.ready is False
    assert "duplicate_binding_id" in {issue.code for issue in result.issues}
    assert "content_track_incompatible" in {issue.code for issue in result.issues}


def test_defaulted_track_kind_is_used_for_compatibility() -> None:
    """Use a selected default track kind before validating raster ownership."""
    intent = AuthoringDocumentIntent(
        sections=[
            {
                "section_id": "main",
                "tracks": [
                    {
                        "track_id": "vdl",
                        "bindings": [
                            {"kind": "raster", "binding_id": "vdl-1", "channel": "VDL"}
                        ],
                    }
                ],
            }
        ]
    )
    result = resolve_authoring_context(
        intent,
        defaults={"sections[main].tracks[vdl].kind": "array"},
        available_channels={"main": [{"mnemonic": "VDL", "kind": "array"}]},
    )

    assert result.ready is True
    assert result.resolved_values["sections[main].tracks[vdl].kind"] == "array"


def test_context_snapshot_joins_new_sections_to_inspected_source_channels() -> None:
    """Prepare typed source and section context before desired-state extraction."""
    snapshot = build_authoring_context_snapshot(
        draft_logfile="workspace/draft.log.yaml",
        existing=_document(),
        summary={
            "sections": [
                {
                    "id": "main_pass",
                    "title": "Main",
                    "source_path": "main.las",
                    "source_format": "las",
                    "track_ids": ["cbl"],
                    "track_kinds": ["normal"],
                    "available_channels": ["CBL"],
                }
            ]
        },
        source_inspections={
            "main.las": {
                "source_path": "main.las",
                "source_format_detected": "las",
                "dataset_name": "Main",
                "index": {"depth_unit": "ft", "depth_min": 100, "depth_max": 200},
                "channels": [
                    {
                        "mnemonic": "CBL",
                        "kind": "scalar",
                        "value_unit": "mV",
                        "description": "Cement bond amplitude",
                        "value_shape": [11],
                    }
                ],
            },
            "repeat.dlis": {
                "source_path": "repeat.dlis",
                "source_format_detected": "dlis",
                "dataset_name": "Repeat",
                "index": {"depth_unit": "ft", "sample_count": 22},
                "channels": [
                    {
                        "mnemonic": "VDL",
                        "kind": "array",
                        "value_unit": "us",
                        "value_shape": [22, 64],
                    }
                ],
            },
        },
        requested_source_slots={"main": "main.las", "repeat": "repeat.dlis"},
        header_slots={"detail_slots": {"kind": "cased_hole"}},
        issues=[
            AuthoringContextIssue(
                path="sources[missing.dlis]",
                code="source_context_unavailable",
                message="Source was not found.",
            )
        ],
    )

    assert [section.section_id for section in snapshot.sections] == [
        "main_pass",
        "repeat_pass",
    ]
    main = snapshot.sections[0]
    repeat = snapshot.sections[1]
    assert main.available_channels[0].kind == "scalar"
    assert main.available_channels[0].unit == "mV"
    assert repeat.available_channels[0].mnemonic == "VDL"
    assert repeat.available_channels[0].kind == "array"
    assert repeat.source_format == "dlis"
    assert snapshot.object_inventory["sections"][0]["track_kinds"] == ["normal"]
    assert snapshot.header_slots["detail_slots"]["kind"] == "cased_hole"
    assert snapshot.issues[0].code == "source_context_unavailable"
