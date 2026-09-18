"""Corrective EXP-TW-02R semantic contract and host completion experiment."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from scripts.exp_tw00_corpus import (
    DEFAULT_CORPUS_PATH,
    load_corpus,
    score_section_draft,
)
from wellplot.agent.code_mode.enrichment import ResolvedSectionContext
from wellplot.authoring_context import AuthoringChannelCandidate
from wellplot.authoring_executor import AuthoringExecutionResult, execute_authoring_plan
from wellplot.authoring_reconciler import reconcile_authoring
from wellplot.authoring_service import AuthoringService
from wellplot.model.authoring import (
    AuthoringDataSource,
    AuthoringDocumentSpec,
    AuthoringRasterColorbarSpec,
    AuthoringRasterSampleAxisSpec,
    AuthoringScale,
)
from wellplot.model.intent import (
    AuthoringCurveBindingIntent,
    AuthoringDocumentIntent,
    AuthoringGridIntent,
    AuthoringRasterBindingIntent,
    AuthoringSectionIntent,
    AuthoringStyleIntent,
    AuthoringTrackIntent,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "typed_worker" / "exp_tw02r_cbl" / "golden_drafts.json"
)


class _SemanticModel(BaseModel):
    """Strict immutable worker-facing semantic model."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class ScaleDraft(_SemanticModel):
    """Worker-owned scalar or raster axis scale."""

    kind: Literal["linear"] = "linear"
    minimum: float
    maximum: float
    reverse: bool = False


class SampleAxisDraft(_SemanticModel):
    """Worker-owned VDL sample-axis semantics."""

    unit: str = Field(min_length=1)
    minimum: float
    maximum: float
    tick_count: int = Field(ge=2)
    source_origin: float
    source_step: float


class CurveBindingDraft(_SemanticModel):
    """One ordered scalar view, including identity for repeated channels."""

    kind: Literal["curve"] = "curve"
    semantic_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    scale: ScaleDraft


class RasterBindingDraft(_SemanticModel):
    """One ordered array view and its scientific display semantics."""

    kind: Literal["raster"] = "raster"
    semantic_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    profile: Literal["vdl"] = "vdl"
    sample_axis: SampleAxisDraft


class TrackDraft(_SemanticModel):
    """One ordered semantic track; width and styling are host-completed."""

    role: Literal["combo", "depth", "cbl", "vdl"]
    kind: Literal["normal", "reference", "array"]
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft | RasterBindingDraft, ...] = Field(min_length=1)


class SectionDraft(_SemanticModel):
    """Corrected semantic intent sufficient for the frozen CBL artifact."""

    title: str = Field(min_length=1)
    source_candidate: str = Field(min_length=1)
    tracks: tuple[TrackDraft, ...] = Field(min_length=1)


class WorkerChannelInput(_SemanticModel):
    """Provider-safe channel facts matching the production worker projection."""

    mnemonic: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    unit: str | None = Field(default=None, min_length=1)


class WorkerSourceInput(_SemanticModel):
    """Provider-safe source handle with no path or host identity."""

    candidate_id: str = Field(min_length=1)
    channels: tuple[WorkerChannelInput, ...] = ()


class WorkerSectionInput(_SemanticModel):
    """Provider-safe projection of one resolved section context."""

    target: Literal["new", "existing"]
    sources: tuple[WorkerSourceInput, ...] = ()


@dataclass(frozen=True, slots=True)
class CompiledSectionDraft:
    """Completed canonical intent and a path-free review projection."""

    intent: AuthoringDocumentIntent
    normalized_projection: dict[str, object]


class DraftCompilationError(ValueError):
    """Stable corrective experiment failure."""

    def __init__(self, code: str, message: str) -> None:
        """Store a deterministic diagnostic code."""
        self.code = code
        super().__init__(message)


_TRACK_POLICY = {
    "combo": {"width_mm": 50.0},
    "depth": {"width_mm": 10.0},
    "cbl": {"width_mm": 44.0},
    "vdl": {"width_mm": 48.0},
}
_CURVE_PRESENTATION = {
    "ecgr": ("Gamma Ray (ECGR_STGC) QTGC-B", "#16a34a", "-", 0.8),
    "tt": ("Transit Time for CBL (TT) QSLT-B", "#2142ff", "-", 0.75),
    "tension": ("Cable Tension (TENS)", "#111111", "--", 0.65),
    "temperature": ("Mud Temperature (MTEM) LEH-MT", "#111111", "-", 0.9),
    "stit": ("Stuck Tool Indicator, Total (STIT)", "#111111", "-", 0.65),
    "tdsp": ("Cable Drag", "#92400e", ":", 0.65),
    "vsec": ("Tool_Tot. Drag", "#1d4ed8", "--", 0.65),
    "cbl_0_100": ("CBL Amplitude (CBL) QSLT-B", "#111111", "-", 0.75),
    "cbl_0_10": ("CBL Amplitude (CBL) QSLT-B", "#2563eb", "--", 0.65),
}
_EXPECTED_CHANNELS = {
    "ecgr": "ECGR_STGC",
    "tt": "TT",
    "tension": "TENS",
    "temperature": "MTEM",
    "stit": "STIT",
    "tdsp": "TDSP",
    "vsec": "VSEC",
    "cbl_0_100": "CBL",
    "cbl_0_10": "CBL",
    "vdl": "VDL",
}
_EXPECTED_CURVE_SCALES = {
    "ecgr": ScaleDraft(minimum=0, maximum=150),
    "tt": ScaleDraft(minimum=200, maximum=400, reverse=True),
    "tension": ScaleDraft(minimum=5000, maximum=0),
    "temperature": ScaleDraft(minimum=100, maximum=500),
    "stit": ScaleDraft(minimum=0, maximum=50),
    "tdsp": ScaleDraft(minimum=0, maximum=50),
    "vsec": ScaleDraft(minimum=0, maximum=50),
    "cbl_0_100": ScaleDraft(minimum=0, maximum=100),
    "cbl_0_10": ScaleDraft(minimum=0, maximum=10),
}
_EXPECTED_VDL_SAMPLE_AXIS = SampleAxisDraft(
    unit="us",
    minimum=200,
    maximum=1200,
    tick_count=7,
    source_origin=40,
    source_step=10,
)
_EXPECTED = {
    "main_pass": {
        "source_candidate": "source-1",
        "title": "Main Pass",
        "tracks": (
            ("combo", "normal", "Combo", ("ecgr", "tt", "tension", "temperature")),
            ("depth", "reference", "Depth", ("stit", "tdsp", "vsec")),
            ("cbl", "normal", "CBL Amplitude", ("cbl_0_100", "cbl_0_10")),
            ("vdl", "array", "VDL", ("vdl",)),
        ),
    },
    "repeat_pass": {
        "source_candidate": "source-2",
        "title": "Repeat Pass",
        "tracks": (
            ("combo", "normal", "Combo", ("ecgr", "tt", "tension", "temperature")),
            ("depth", "reference", "Depth", ("stit", "tdsp", "vsec")),
            ("cbl", "normal", "CBL Amplitude", ("cbl_0_100", "cbl_0_10")),
            ("vdl", "array", "VDL", ("vdl",)),
        ),
    },
}


def load_golden_drafts(path: str | Path = DEFAULT_GOLDEN_PATH) -> dict[str, SectionDraft]:
    """Load corrected manually authored golden drafts."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("EXP-TW-02R golden drafts must be a JSON object.")
    drafts = {key: SectionDraft.model_validate(value) for key, value in payload.items()}
    if set(drafts) != set(_EXPECTED):
        raise ValueError(f"EXP-TW-02R golden drafts must contain {sorted(_EXPECTED)!r}.")
    return drafts


def provider_section_input(section_context: ResolvedSectionContext) -> WorkerSectionInput:
    """Project host context into the exact path-free worker input boundary."""
    return WorkerSectionInput(
        target="existing" if section_context.section_id else "new",
        sources=tuple(
            WorkerSourceInput(
                candidate_id=source.candidate_id,
                channels=tuple(
                    WorkerChannelInput(
                        mnemonic=channel.mnemonic,
                        kind=channel.kind,
                        aliases=tuple(channel.aliases),
                        unit=channel.unit,
                    )
                    for channel in source.channels
                ),
            )
            for source in section_context.sources
        ),
    )


def _revalidate(draft: SectionDraft | Mapping[str, object]) -> SectionDraft:
    """Revalidate mappings and existing model instances from serialized data."""
    raw = draft.model_dump(mode="json") if isinstance(draft, SectionDraft) else draft
    return SectionDraft.model_validate(raw)


def validate_gate_a(
    draft: SectionDraft | Mapping[str, object],
    *,
    section_key: str,
    section_context: ResolvedSectionContext,
    requirements: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Run original Gate A plus exact corrected semantic checks."""
    validated = _revalidate(draft)
    base = score_section_draft(
        validated.model_dump(mode="json"),
        section_context=section_context,
        requirements=requirements or {"tracks": _base_track_requirements(section_key)},
    )
    expected = _EXPECTED[section_key]
    selected = next(
        (
            source
            for source in section_context.sources
            if source.candidate_id == validated.source_candidate
        ),
        None,
    )
    channels = {channel.mnemonic: channel for channel in selected.channels} if selected else {}
    source_selection_valid = validated.source_candidate == expected["source_candidate"]
    titles_valid = validated.title == expected["title"]
    semantics_valid = len(validated.tracks) == len(expected["tracks"])
    if semantics_valid:
        for draft_track, (role, kind, title, binding_ids) in zip(
            validated.tracks, expected["tracks"], strict=True
        ):
            if (
                draft_track.role != role
                or draft_track.kind != kind
                or draft_track.title != title
                or tuple(binding.semantic_id for binding in draft_track.bindings) != binding_ids
            ):
                semantics_valid = False
                break
            expected_bindings = binding_ids
            for binding, semantic_id in zip(draft_track.bindings, expected_bindings, strict=True):
                if binding.channel != _EXPECTED_CHANNELS[semantic_id]:
                    semantics_valid = False
                if semantic_id == "vdl" and (
                    binding.kind != "raster"
                    or binding.profile != "vdl"
                    or binding.sample_axis != _EXPECTED_VDL_SAMPLE_AXIS
                ):
                    semantics_valid = False
                if semantic_id != "vdl" and (
                    binding.kind != "curve"
                    or binding.channel not in channels
                    or binding.scale != _EXPECTED_CURVE_SCALES[semantic_id]
                ):
                    semantics_valid = False
                if binding.kind == "curve":
                    channel_info = channels.get(binding.channel)
                    if channel_info is None or channel_info.kind != "scalar":
                        semantics_valid = False
            if role == "vdl" and draft_track.x_scale != ScaleDraft(minimum=200, maximum=1200):
                semantics_valid = False
            if role != "vdl" and draft_track.x_scale is not None:
                semantics_valid = False
    return {
        **base,
        "source_selection_valid": source_selection_valid,
        "titles_valid": titles_valid,
        "semantic_fields_valid": semantics_valid,
        "semantic_usable": all(
            bool(base.get(key)) for key in ("host_reference_valid", "channel_valid")
        )
        and source_selection_valid
        and titles_valid
        and semantics_valid,
    }


def compile_section_draft(
    draft: SectionDraft | Mapping[str, object],
    *,
    section_key: str,
    section_context: ResolvedSectionContext,
    requirements: Mapping[str, object] | None = None,
) -> CompiledSectionDraft:
    """Revalidate, Gate-A-check, complete host policy, and compile one section."""
    validated = _revalidate(draft)
    gate = validate_gate_a(
        validated,
        section_key=section_key,
        section_context=section_context,
        requirements=requirements,
    )
    if not gate["semantic_usable"]:
        raise DraftCompilationError("gate_a_invalid", "SectionDraft failed corrected Gate A.")

    source = next(
        source
        for source in section_context.sources
        if source.candidate_id == validated.source_candidate
    )
    section_id = f"exp-tw02r-{section_key}"
    tracks: list[AuthoringTrackIntent] = []
    projection_tracks: list[dict[str, object]] = []
    for _track_index, track in enumerate(validated.tracks):
        track_id = f"{section_id}.track-{track.role}"
        track_kwargs: dict[str, object] = {
            "track_id": track_id,
            "section_id": section_id,
            "title": track.title,
            "kind": track.kind,
            "width_mm": _TRACK_POLICY[track.role]["width_mm"],
            "bindings": [],
        }
        if track.x_scale is not None:
            track_kwargs["x_scale"] = AuthoringScale(**track.x_scale.model_dump())
        if track.role == "vdl":
            track_kwargs["grid"] = AuthoringGridIntent(
                vertical_main_visible=False,
                vertical_secondary_visible=False,
            )
        bindings: list[AuthoringCurveBindingIntent | AuthoringRasterBindingIntent] = []
        projection_bindings: list[dict[str, object]] = []
        for _binding_index, binding in enumerate(track.bindings):
            binding_id = f"{track_id}.binding-{binding.semantic_id}"
            if binding.kind == "curve":
                label, color, line_style, line_width = _CURVE_PRESENTATION[binding.semantic_id]
                bindings.append(
                    AuthoringCurveBindingIntent(
                        kind="curve",
                        binding_id=binding_id,
                        section_id=section_id,
                        track_id=track_id,
                        channel=binding.channel,
                        label=label,
                        scale=AuthoringScale(**binding.scale.model_dump()),
                        style=AuthoringStyleIntent(
                            color=color,
                            line_style=line_style,
                            line_width=line_width,
                        ),
                    )
                )
                projection_bindings.append(
                    {
                        "semantic_id": binding.semantic_id,
                        "kind": "curve",
                        "channel": binding.channel,
                        "scale": binding.scale.model_dump(mode="json"),
                    }
                )
            else:
                bindings.append(
                    AuthoringRasterBindingIntent(
                        kind="raster",
                        binding_id=binding_id,
                        section_id=section_id,
                        track_id=track_id,
                        channel=binding.channel,
                        label="VDL VariableDensity (VDL) QSLT-B",
                        profile="vdl",
                        style=AuthoringStyleIntent(colormap="gray_r"),
                        colorbar=AuthoringRasterColorbarSpec(
                            enabled=True,
                            label="Amplitude",
                            position="header",
                        ),
                        sample_axis=AuthoringRasterSampleAxisSpec(
                            **binding.sample_axis.model_dump()
                        ),
                    )
                )
                projection_bindings.append(
                    {
                        "semantic_id": binding.semantic_id,
                        "kind": "raster",
                        "channel": binding.channel,
                        "profile": binding.profile,
                        "sample_axis": binding.sample_axis.model_dump(mode="json"),
                    }
                )
        track_kwargs["bindings"] = bindings
        tracks.append(AuthoringTrackIntent(**track_kwargs))
        projection_tracks.append(
            {
                "role": track.role,
                "kind": track.kind,
                "title": track.title,
                "width_mm": _TRACK_POLICY[track.role]["width_mm"],
                "x_scale": track.x_scale.model_dump(mode="json") if track.x_scale else None,
                "bindings": projection_bindings,
            }
        )
    intent = AuthoringDocumentIntent(
        sections=[
            AuthoringSectionIntent(
                section_id=section_id,
                title=validated.title,
                data_source=AuthoringDataSource(
                    source_path=source.canonical_path,
                    source_format=source.source_format,
                ),
                tracks=tracks,
            )
        ]
    )
    return CompiledSectionDraft(
        intent=intent,
        normalized_projection={
            "section_key": section_key,
            "title": validated.title,
            "source_candidate": validated.source_candidate,
            "tracks": projection_tracks,
        },
    )


def compile_golden_drafts(
    *,
    corpus_path: str | Path = DEFAULT_CORPUS_PATH,
    drafts_path: str | Path = DEFAULT_GOLDEN_PATH,
) -> dict[str, CompiledSectionDraft]:
    """Compile both corrected golden drafts using stable source-based joins."""
    corpus = load_corpus(corpus_path)
    drafts = load_golden_drafts(drafts_path)
    contexts = _contexts_by_section_key(corpus.sections)
    return {
        section_key: compile_section_draft(
            drafts[section_key],
            section_key=section_key,
            section_context=contexts[section_key],
            requirements=corpus.gate_a["section_requirements"][section_key],
        )
        for section_key in ("main_pass", "repeat_pass")
    }


def execute_compiled_section(
    compiled: CompiledSectionDraft,
    context: ResolvedSectionContext,
) -> AuthoringExecutionResult:
    """Reconcile and privately execute one completed new-section intent."""
    section_id = compiled.intent.sections[0].section_id
    channels = selected_execution_channels(compiled, context)
    document = AuthoringDocumentSpec(
        name="exp-tw02r",
        title="EXP-TW-02R",
        sections=[
            {
                "id": "seed",
                "title": "Seed",
                "tracks": [
                    {
                        "id": "seed-track",
                        "title": "Seed",
                        "kind": "normal",
                        "width_mm": 1,
                    }
                ],
            }
        ],
    )
    plan = reconcile_authoring(
        compiled.intent,
        existing=document,
        available_channels={section_id: channels},
    )
    if not plan.ready:
        raise DraftCompilationError(
            "reconciliation_unready",
            "; ".join(issue.code for issue in plan.issues),
        )
    result = execute_authoring_plan(AuthoringService(document), plan)
    if not result.success:
        raise DraftCompilationError("execution_failed", "Private execution rejected the intent.")
    return result


def selected_execution_channels(
    compiled: CompiledSectionDraft,
    context: ResolvedSectionContext,
) -> list[AuthoringChannelCandidate]:
    """Return channels from only the source selected by the compiled draft."""
    candidate_id = compiled.normalized_projection.get("source_candidate")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise DraftCompilationError(
            "execution_source_missing",
            "Compiled review projection does not contain a valid source candidate.",
        )

    selected_source = next(
        (source for source in context.sources if source.candidate_id == candidate_id),
        None,
    )
    if selected_source is None:
        raise DraftCompilationError(
            "execution_source_missing",
            "Private execution context does not contain the compiled source candidate.",
        )

    return [
        AuthoringChannelCandidate(
            mnemonic=channel.mnemonic,
            kind=channel.kind,
        )
        for channel in selected_source.channels
    ]


def _base_track_requirements(section_key: str) -> list[dict[str, object]]:
    """Build the original Gate A shape without duplicating channel inventories."""
    return [
        {
            "kind": kind,
            "bindings": [
                {
                    "kind": "raster" if role == "vdl" else "curve",
                    "channel": {
                        "ecgr": "ECGR_STGC",
                        "tt": "TT",
                        "tension": "TENS",
                        "temperature": "MTEM",
                        "stit": "STIT",
                        "tdsp": "TDSP",
                        "vsec": "VSEC",
                        "cbl_0_100": "CBL",
                        "cbl_0_10": "CBL",
                        "vdl": "VDL",
                    }[binding_id],
                }
                for binding_id in binding_ids
            ],
        }
        for role, kind, _title, binding_ids in _EXPECTED[section_key]["tracks"]
    ]


def _contexts_by_section_key(
    sections: tuple[ResolvedSectionContext, ...],
) -> dict[str, ResolvedSectionContext]:
    """Join replay contexts by their frozen source candidate identity."""
    result: dict[str, ResolvedSectionContext] = {}
    for section in sections:
        candidate_ids = {source.candidate_id for source in section.sources}
        for section_key, expected in _EXPECTED.items():
            if expected["source_candidate"] in candidate_ids:
                result[section_key] = section
    if set(result) != set(_EXPECTED):
        raise ValueError("EXP-TW-02R contexts cannot be joined by frozen candidates.")
    return result


__all__ = [
    "CompiledSectionDraft",
    "CurveBindingDraft",
    "DraftCompilationError",
    "RasterBindingDraft",
    "SampleAxisDraft",
    "ScaleDraft",
    "SectionDraft",
    "TrackDraft",
    "WorkerChannelInput",
    "WorkerSectionInput",
    "WorkerSourceInput",
    "compile_golden_drafts",
    "compile_section_draft",
    "execute_compiled_section",
    "load_golden_drafts",
    "provider_section_input",
    "selected_execution_channels",
    "validate_gate_a",
]
