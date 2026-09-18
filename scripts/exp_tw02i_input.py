"""EXP-TW-02I typed provider-input contract and provenance audit."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from scripts.exp_tw00_corpus import DEFAULT_CORPUS_PATH, load_corpus
from scripts.exp_tw02r_contract import WorkerSectionInput, provider_section_input
from wellplot.agent.code_mode.enrichment import ResolvedSectionContext

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT_PATH = REPO_ROOT / "tests" / "fixtures" / "agentic_cbl" / "compile_contract.json"
_MISSING = object()


class _InputModel(BaseModel):
    """Strict immutable base for provider-visible experiment inputs."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class ScaleRequirement(_InputModel):
    """Worker-owned linear scale semantics."""

    kind: Literal["linear"] = "linear"
    minimum: float
    maximum: float
    reverse: bool = False


class SampleAxisRequirement(_InputModel):
    """Worker-owned array sample-axis semantics."""

    unit: str = Field(min_length=1)
    minimum: float
    maximum: float
    tick_count: int = Field(ge=2)
    source_origin: float
    source_step: float


class CurveRequirement(_InputModel):
    """One ordered scalar binding requirement."""

    kind: Literal["curve"] = "curve"
    semantic_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    scale: ScaleRequirement


class RasterRequirement(_InputModel):
    """One ordered raster binding requirement."""

    kind: Literal["raster"] = "raster"
    semantic_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    profile: Literal["vdl"] = "vdl"
    sample_axis: SampleAxisRequirement


class TrackRequirement(_InputModel):
    """One ordered track requirement with worker-owned semantics only."""

    role: Literal["combo", "depth", "cbl", "vdl"]
    kind: Literal["normal", "reference", "array"]
    title: str = Field(min_length=1)
    x_scale: ScaleRequirement | None = None
    bindings: tuple[CurveRequirement | RasterRequirement, ...] = Field(min_length=1)


class TypedWorkerTaskInput(_InputModel):
    """Complete typed semantic job visible to a future provider."""

    section_role: Literal["main_pass", "repeat_pass"]
    title: str = Field(min_length=1)
    source_candidate: str = Field(min_length=1)
    tracks: tuple[TrackRequirement, ...] = Field(min_length=1)


class TypedWorkerInputBundle(_InputModel):
    """The complete path-free provider boundary for one section."""

    task: TypedWorkerTaskInput
    section: WorkerSectionInput


class SemanticProvenance(_InputModel):
    """One deterministic link from output semantic to provider input evidence."""

    output_path: str = Field(min_length=1)
    provider_path: str = Field(min_length=1)
    evidence_path: str = Field(min_length=1)


class ProvenanceAudit(_InputModel):
    """Reviewable result of the worker-owned input sufficiency audit."""

    valid: bool
    records: tuple[SemanticProvenance, ...]
    missing_output_paths: tuple[str, ...] = ()


_TRACK_SHAPE = (
    ("combo", ("ecgr", "tt", "tension", "temperature")),
    ("depth", ("stit", "tdsp", "vsec")),
    ("cbl", ("cbl_0_100", "cbl_0_10")),
    ("vdl", ("vdl",)),
)
_CHANNEL_TO_SEMANTIC_ID = {
    "ECGR_STGC": "ecgr",
    "TT": "tt",
    "TENS": "tension",
    "MTEM": "temperature",
    "STIT": "stit",
    "TDSP": "tdsp",
    "VSEC": "vsec",
    "VDL": "vdl",
}


def build_typed_worker_input(
    section_role: Literal["main_pass", "repeat_pass"],
    *,
    contract_path: str | Path = DEFAULT_CONTRACT_PATH,
    corpus_path: str | Path = DEFAULT_CORPUS_PATH,
) -> TypedWorkerInputBundle:
    """Build one complete typed input from frozen task/artifact evidence."""
    contract = json.loads(Path(contract_path).read_text(encoding="utf-8"))
    raw_plan = _section_by_key(contract["reconstruction_plan"]["sections"], section_role)
    canonical = _section_by_key(contract["merged_intent"]["sections"], section_role)
    corpus = load_corpus(corpus_path)
    context = _context_by_role(corpus.sections, section_role)
    task = _task_from_evidence(section_role, raw_plan, canonical, corpus.plan.section_tasks)
    return TypedWorkerInputBundle(task=task, section=provider_section_input(context))


def serialize_provider_input(bundle: TypedWorkerInputBundle) -> str:
    """Serialize the complete provider input with stable JSON ordering."""
    return json.dumps(bundle.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def audit_worker_input_provenance(
    bundle: TypedWorkerInputBundle | Mapping[str, object],
) -> ProvenanceAudit:
    """Verify every corrected output semantic has explicit typed input evidence."""
    raw = bundle.model_dump(mode="json") if isinstance(bundle, TypedWorkerInputBundle) else bundle
    task = raw.get("task", {}) if isinstance(raw, Mapping) else {}
    values = _provider_values(task if isinstance(task, Mapping) else {})
    records = _provenance_records(task if isinstance(task, Mapping) else {})
    missing = tuple(
        record.output_path
        for record in records
        if values.get(record.provider_path, _MISSING) is _MISSING
    )
    return ProvenanceAudit(
        valid=not missing,
        records=tuple(records),
        missing_output_paths=missing,
    )


def _task_from_evidence(
    section_role: str,
    raw_plan: Mapping[str, object],
    canonical: Mapping[str, object],
    section_tasks: tuple[object, ...],
) -> TypedWorkerTaskInput:
    """Project semantic values from the frozen plan and canonical artifact."""
    canonical_tracks = {str(track["track_id"]): track for track in canonical["tracks"]}
    plan_components = raw_plan["components"]
    tracks: list[TrackRequirement] = []
    for component in plan_components:
        capability_id = str(component["capability_id"])
        if not capability_id.startswith("track."):
            continue
        role = str(component["values"]["track_id"])
        canonical_track = canonical_tracks[role]
        bindings = _binding_requirements(
            role,
            component,
            plan_components,
            canonical_track,
        )
        tracks.append(
            TrackRequirement(
                role=role,
                kind=capability_id.removeprefix("track."),
                title=str(canonical_track["title"]),
                x_scale=(
                    ScaleRequirement.model_validate(canonical_track["x_scale"])
                    if "x_scale" in canonical_track
                    else None
                ),
                bindings=tuple(bindings),
            )
        )
    task_index = next(
        index
        for index, task in enumerate(section_tasks)
        if task.source_hints
        and task.source_hints[0] == f"source-{1 if section_role == 'main_pass' else 2}"
    )
    source_candidate = str(section_tasks[task_index].source_hints[0])
    return TypedWorkerTaskInput(
        section_role=section_role,
        title=str(canonical["title"]),
        source_candidate=source_candidate,
        tracks=tuple(tracks),
    )


def _binding_requirements(
    role: str,
    track_component: Mapping[str, object],
    components: list[Mapping[str, object]],
    canonical_track: Mapping[str, object],
) -> list[CurveRequirement | RasterRequirement]:
    """Join plan channel facts to canonical scientific display semantics."""
    children = [
        component
        for component in components
        if component.get("parent_component_id") == track_component.get("component_id")
    ]
    canonical_bindings = canonical_track["bindings"]
    result: list[CurveRequirement | RasterRequirement] = []
    for index, component in enumerate(children):
        channel = str(component["values"]["channel"])
        canonical_binding = canonical_bindings[index]
        semantic_id = _semantic_id(component, channel)
        if role == "vdl":
            sample_axis = canonical_binding["sample_axis"]
            result.append(
                RasterRequirement(
                    semantic_id=semantic_id,
                    channel=channel,
                    profile=str(canonical_binding["profile"]),
                    sample_axis=SampleAxisRequirement(
                        unit=str(sample_axis["unit"]),
                        minimum=float(sample_axis["minimum"]),
                        maximum=float(sample_axis["maximum"]),
                        tick_count=int(sample_axis["tick_count"]),
                        source_origin=float(sample_axis["source_origin"]),
                        source_step=float(sample_axis["source_step"]),
                    ),
                )
            )
        else:
            result.append(
                CurveRequirement(
                    semantic_id=semantic_id,
                    channel=channel,
                    scale=ScaleRequirement.model_validate(canonical_binding["scale"]),
                )
            )
    return result


def _semantic_id(component: Mapping[str, object], channel: str) -> str:
    """Derive a semantic binding identity from frozen task evidence."""
    goal = str(component["goal"]).lower()
    if channel == "CBL":
        if "0 to 100" in goal:
            return "cbl_0_100"
        if "0 to 10" in goal:
            return "cbl_0_10"
        raise ValueError("Frozen CBL binding goal has no distinguishable view.")
    try:
        return _CHANNEL_TO_SEMANTIC_ID[channel]
    except KeyError as exc:
        raise ValueError(f"Frozen channel {channel!r} has no semantic identity.") from exc


def _provenance_records(task: Mapping[str, object]) -> list[SemanticProvenance]:
    """Return deterministic provenance records for the corrected output shape."""
    section_role = str(task.get("section_role", "section"))
    records = [
        SemanticProvenance(
            output_path="SectionDraft.title",
            provider_path="task.title",
            evidence_path=f"merged_intent.sections[{section_role}].title",
        ),
        SemanticProvenance(
            output_path="SectionDraft.source_candidate",
            provider_path="task.source_candidate",
            evidence_path=f"semantic_plan.section_tasks[{section_role}].source_hints[0]",
        ),
    ]
    for role, binding_ids in _TRACK_SHAPE:
        prefix = f"tracks[{role}]"
        records.extend(
            [
                SemanticProvenance(
                    output_path=f"SectionDraft.{prefix}.role",
                    provider_path=f"task.{prefix}.role",
                    evidence_path=f"reconstruction_plan.sections[{section_role}].components[{role}].values.track_id",
                ),
                SemanticProvenance(
                    output_path=f"SectionDraft.{prefix}.kind",
                    provider_path=f"task.{prefix}.kind",
                    evidence_path=f"reconstruction_plan.sections[{section_role}].components[{role}].capability_id",
                ),
                SemanticProvenance(
                    output_path=f"SectionDraft.{prefix}.title",
                    provider_path=f"task.{prefix}.title",
                    evidence_path=f"merged_intent.sections[{section_role}].tracks[{role}].title",
                ),
            ]
        )
        if role == "vdl":
            records.extend(
                SemanticProvenance(
                    output_path=f"SectionDraft.{prefix}.x_scale.{field}",
                    provider_path=f"task.{prefix}.x_scale.{field}",
                    evidence_path=f"merged_intent.sections[{section_role}].tracks[vdl].x_scale.{field}",
                )
                for field in ("kind", "minimum", "maximum", "reverse")
            )
        for semantic_id in binding_ids:
            binding_prefix = f"{prefix}.bindings[{semantic_id}]"
            records.extend(
                [
                    SemanticProvenance(
                        output_path=f"SectionDraft.{binding_prefix}.semantic_id",
                        provider_path=f"task.{binding_prefix}.semantic_id",
                        evidence_path=f"reconstruction_plan.sections[{section_role}].components[{semantic_id}].goal",
                    ),
                    SemanticProvenance(
                        output_path=f"SectionDraft.{binding_prefix}.channel",
                        provider_path=f"task.{binding_prefix}.channel",
                        evidence_path=f"reconstruction_plan.sections[{section_role}].components[{semantic_id}].values.channel",
                    ),
                ]
            )
            if semantic_id == "vdl":
                records.extend(
                    SemanticProvenance(
                        output_path=f"SectionDraft.{binding_prefix}.sample_axis.{field}",
                        provider_path=f"task.{binding_prefix}.sample_axis.{field}",
                        evidence_path=f"merged_intent.sections[{section_role}].tracks[vdl].bindings[vdl].sample_axis.{field}",
                    )
                    for field in (
                        "unit",
                        "minimum",
                        "maximum",
                        "tick_count",
                        "source_origin",
                        "source_step",
                    )
                )
                records.append(
                    SemanticProvenance(
                        output_path=f"SectionDraft.{binding_prefix}.profile",
                        provider_path=f"task.{binding_prefix}.profile",
                        evidence_path=f"merged_intent.sections[{section_role}].tracks[vdl].bindings[vdl].profile",
                    )
                )
            else:
                records.extend(
                    SemanticProvenance(
                        output_path=f"SectionDraft.{binding_prefix}.scale.{field}",
                        provider_path=f"task.{binding_prefix}.scale.{field}",
                        evidence_path=f"merged_intent.sections[{section_role}].tracks[{role}].bindings[{semantic_id}].scale.{field}",
                    )
                    for field in ("kind", "minimum", "maximum", "reverse")
                )
    return records


def _provider_values(task: Mapping[str, object]) -> dict[str, object]:
    """Index provider-visible task values by stable audit paths."""
    values: dict[str, object] = {}
    if "title" in task:
        values["task.title"] = task["title"]
    if "source_candidate" in task:
        values["task.source_candidate"] = task["source_candidate"]
    tracks = task.get("tracks", ())
    if not isinstance(tracks, list):
        return values
    for track in tracks:
        if not isinstance(track, Mapping) or not isinstance(track.get("role"), str):
            continue
        role = track["role"]
        for field in ("role", "kind", "title", "x_scale"):
            if field in track and track[field] is not None:
                if field == "x_scale" and isinstance(track[field], Mapping):
                    for scale_field in ("kind", "minimum", "maximum", "reverse"):
                        if scale_field in track[field]:
                            values[f"task.tracks[{role}].x_scale.{scale_field}"] = track[field][
                                scale_field
                            ]
                else:
                    values[f"task.tracks[{role}].{field}"] = track[field]
        bindings = track.get("bindings", ())
        if not isinstance(bindings, list):
            continue
        for binding in bindings:
            if not isinstance(binding, Mapping) or not isinstance(binding.get("semantic_id"), str):
                continue
            semantic_id = binding["semantic_id"]
            prefix = f"task.tracks[{role}].bindings[{semantic_id}]"
            for field in ("semantic_id", "channel", "profile"):
                if field in binding:
                    values[f"{prefix}.{field}"] = binding[field]
            for nested_name in ("scale", "sample_axis"):
                nested = binding.get(nested_name)
                if isinstance(nested, Mapping):
                    for field, value in nested.items():
                        values[f"{prefix}.{nested_name}.{field}"] = value
    return values


def _section_by_key(
    sections: list[Mapping[str, object]], section_role: str
) -> Mapping[str, object]:
    """Find one frozen section by its semantic benchmark role."""
    for section in sections:
        if section.get("section_id") == section_role:
            return section
    raise ValueError(f"Frozen contract has no section {section_role!r}.")


def _context_by_role(
    sections: tuple[ResolvedSectionContext, ...],
    section_role: str,
) -> ResolvedSectionContext:
    """Find a corpus context by its opaque frozen candidate identity."""
    candidate_id = "source-1" if section_role == "main_pass" else "source-2"
    for section in sections:
        if any(source.candidate_id == candidate_id for source in section.sources):
            return section
    raise ValueError(f"Frozen corpus has no context for {section_role!r}.")


__all__ = [
    "CurveRequirement",
    "ProvenanceAudit",
    "RasterRequirement",
    "SampleAxisRequirement",
    "ScaleRequirement",
    "SemanticProvenance",
    "TrackRequirement",
    "TypedWorkerInputBundle",
    "TypedWorkerTaskInput",
    "audit_worker_input_provenance",
    "build_typed_worker_input",
    "serialize_provider_input",
]
