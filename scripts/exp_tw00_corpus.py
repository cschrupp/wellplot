"""Capture and replay the EXP-TW-00 typed-worker corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from wellplot.agent.code_mode.enrichment import (
    ReportContext,
    ResolvedSectionContext,
    SourceContext,
)
from wellplot.agent.code_mode.planner import ReportTask, SectionTask, SemanticPlan
from wellplot.authoring import load_authoring_document
from wellplot.authoring_program.inspection import AuthoringInspectionFacade
from wellplot.model.authoring import AuthoringDocumentSpec

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "agentic_cbl"
DEFAULT_CORPUS_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "typed_worker" / "exp_tw00_cbl" / "corpus.json"
)
BASELINE_SHA = "48fafb958b85069295f88fc249b3b9b68158c52a"
FIXTURE_VERSION = "exp-tw-00.cbl.v1"


@dataclass(frozen=True, slots=True)
class FrozenWorkerCorpus:
    """Replayed host and worker context for the typed-worker experiment."""

    baseline_sha: str
    fixture_version: str
    starter_document: AuthoringDocumentSpec
    plan: SemanticPlan
    report_context: ReportContext
    sections: tuple[ResolvedSectionContext, ...]
    gate_a: Mapping[str, object]


def load_corpus(path: str | Path = DEFAULT_CORPUS_PATH) -> FrozenWorkerCorpus:
    """Deserialize one explicit corpus without invoking discovery or enrichment."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    host = _mapping(payload, "host_only")
    worker = _mapping(payload, "worker_projection")
    expected_worker_hash = str(payload.get("worker_projection_sha256", ""))
    if _sha256_json(worker) != expected_worker_hash:
        raise ValueError("EXP-TW-00 worker projection hash does not match the corpus.")
    raw_fixture = {
        "host_only": host,
        "worker_projection": worker,
        "gate_a": payload.get("gate_a", {}),
    }
    if _sha256_json(raw_fixture) != payload.get("fixture_sha256"):
        raise ValueError("EXP-TW-00 fixture hash does not match the corpus.")

    starter_document = AuthoringDocumentSpec.model_validate(host["starter_document"])
    plan = SemanticPlan.model_validate(worker["semantic_plan"])
    report_context = ReportContext.model_validate(worker["report_context"])
    source_paths = {str(key): str(value) for key, value in _mapping(host, "source_paths").items()}
    sections = tuple(
        _replay_section_context(item, source_paths)
        for item in _sequence(worker, "section_contexts")
    )
    if len(sections) != len(plan.section_tasks):
        raise ValueError("EXP-TW-00 section task/context counts do not match.")
    return FrozenWorkerCorpus(
        baseline_sha=str(payload["baseline_sha"]),
        fixture_version=str(payload["fixture_version"]),
        starter_document=starter_document,
        plan=plan,
        report_context=report_context,
        sections=sections,
        gate_a=_mapping(payload, "gate_a"),
    )


def replay_worker_projection(
    path: str | Path = DEFAULT_CORPUS_PATH,
) -> tuple[ReportTask, ReportContext, tuple[SectionTask, ...], tuple[ResolvedSectionContext, ...]]:
    """Return the exact bounded worker inputs from the frozen corpus."""
    corpus = load_corpus(path)
    return (
        corpus.plan.report_task,
        corpus.report_context,
        corpus.plan.section_tasks,
        corpus.sections,
    )


def score_section_draft(
    draft: Mapping[str, object],
    *,
    section_context: ResolvedSectionContext,
    requirements: Mapping[str, object],
) -> dict[str, object]:
    """Score a future JSON draft against frozen host and semantic requirements."""
    source_id = draft.get("source_candidate")
    sources = {source.candidate_id: source for source in section_context.sources}
    selected_source = sources.get(source_id) if isinstance(source_id, str) else None
    host_reference_valid = selected_source is not None
    channel_index = (
        {channel.mnemonic: channel for channel in selected_source.channels}
        if selected_source is not None
        else {}
    )
    channel_valid = True
    binding_shapes: list[dict[str, object]] = []
    tracks = draft.get("tracks")
    if not isinstance(tracks, list):
        tracks = []
        channel_valid = False
    for track in tracks:
        if not isinstance(track, Mapping):
            channel_valid = False
            continue
        bindings = track.get("bindings")
        if not isinstance(bindings, list):
            channel_valid = False
            continue
        track_bindings: list[dict[str, object]] = []
        for binding in bindings:
            if not isinstance(binding, Mapping):
                channel_valid = False
                continue
            channel = binding.get("channel")
            kind = binding.get("kind")
            channel_info = channel_index.get(channel) if isinstance(channel, str) else None
            if (
                channel_info is None
                or (kind == "curve" and channel_info.kind != "scalar")
                or (kind == "raster" and channel_info.kind != "array")
            ):
                channel_valid = False
            track_bindings.append({"kind": kind, "channel": channel})
        binding_shapes.append(
            {
                "kind": track.get("kind"),
                "bindings": track_bindings,
            }
        )
    expected_tracks = requirements.get("tracks", ())
    semantic_usable = (
        isinstance(draft.get("title"), str)
        and bool(draft["title"].strip())
        and binding_shapes == list(expected_tracks)
        and host_reference_valid
        and channel_valid
    )
    return {
        "host_reference_valid": host_reference_valid,
        "channel_valid": channel_valid,
        "semantic_usable": semantic_usable,
    }


def capture_corpus(
    *,
    source_root: Path = DEFAULT_SOURCE_FIXTURE,
    output_path: Path = DEFAULT_CORPUS_PATH,
) -> None:
    """Capture the explicit CBL plan, starter document, and worker projections."""
    contract = json.loads((source_root / "compile_contract.json").read_text(encoding="utf-8"))
    starter_path = source_root / "cased_hole_starter.log.yaml"
    starter_document = load_authoring_document(starter_path)
    raw_plan = _mapping(contract, "reconstruction_plan")
    sections = _sequence(raw_plan, "sections")

    candidate_ids = {
        str(section["section_id"]): f"source-{index}"
        for index, section in enumerate(sections, start=1)
    }
    report_task = ReportTask(
        goal=str(raw_plan["report_goal"]),
        capability_ids=(str(raw_plan["report_capability_id"]),),
        requirements=tuple(
            f"service_title: {value}"
            for value in _mapping(raw_plan, "report_values").get("service_titles", ())
        ),
    )
    section_tasks = tuple(
        _section_task(section, candidate_id=candidate_ids[str(section["section_id"])])
        for section in sections
    )
    plan = SemanticPlan(
        summary=str(raw_plan["summary"]),
        report_task=report_task,
        section_tasks=section_tasks,
        unresolved_requirements=tuple(
            str(item) for item in raw_plan.get("unresolved_requirements", ())
        ),
    )
    inspection = AuthoringInspectionFacade(starter_document)
    report_context = ReportContext(header_slots=inspection.header_slots())
    source_manifest = _mapping(contract, "source_manifest")
    worker_sections = tuple(
        _section_projection(
            section,
            candidate_id=candidate_ids[str(section["section_id"])],
            source_manifest=source_manifest,
        )
        for section in sections
    )
    worker_projection = {
        "semantic_plan": plan.model_dump(mode="json"),
        "report_context": report_context.model_dump(mode="json"),
        "section_contexts": worker_sections,
    }
    host_only = {
        "source_paths": {
            candidate_ids[str(section["section_id"])]: str(
                _mapping(section, "data_source")["source_path"]
            )
            for section in sections
        },
        "starter_document": starter_document.model_dump(mode="json"),
    }
    gate_a = {
        "provider_attempts": 10,
        "thresholds": {
            "schema_valid_minimum": 9,
            "host_reference_valid_all_validated": True,
            "channel_valid_all_validated": True,
            "semantic_usable_minimum": 8,
        },
        "section_requirements": {
            str(section["section_id"]): _gate_requirements(section) for section in sections
        },
        "validity_rules": [
            "A selected channel must belong to the selected source candidate.",
            "curve bindings require selected-source scalar channels.",
            "raster bindings require selected-source array channels.",
            "Repeated bindings are counted with multiplicity.",
        ],
    }
    payload = {
        "baseline_sha": BASELINE_SHA,
        "fixture_version": FIXTURE_VERSION,
        "capture_provenance": {
            "source_fixture": "tests/fixtures/agentic_cbl/compile_contract.json",
            "starter_fixture": "tests/fixtures/agentic_cbl/cased_hole_starter.log.yaml",
            "capture_mode": "explicit fixture capture; no planner, provider, or discovery",
        },
        "host_only": host_only,
        "worker_projection": worker_projection,
        "worker_projection_sha256": _sha256_json(worker_projection),
        "gate_a": gate_a,
    }
    payload["fixture_sha256"] = _sha256_json(
        {
            "host_only": host_only,
            "worker_projection": worker_projection,
            "gate_a": gate_a,
        }
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _section_task(section: Mapping[str, object], *, candidate_id: str) -> SectionTask:
    """Project one captured section into the planner's semantic task model."""
    components = _sequence(section, "components")
    capability_ids = {str(section["capability_id"])}
    requirements: list[str] = []
    for component in components:
        capability_id = str(component["capability_id"])
        capability_ids.add(capability_id)
        values = _mapping(component, "values")
        requirement = str(component["goal"])
        if capability_id.startswith("track."):
            requirement += f" Track kind: {capability_id.removeprefix('track.')}"
        elif capability_id.startswith("binding."):
            channel = values.get("channel")
            if isinstance(channel, str):
                requirement += f" Use exact source channel '{channel}'."
        requirements.append(requirement)
    return SectionTask(
        goal=str(section["goal"]),
        capability_ids=tuple(sorted(capability_ids)),
        source_hints=(candidate_id,),
        requirements=tuple(requirements),
        constraints=tuple(str(value) for value in section.get("constraints", ())),
    )


def _section_projection(
    section: Mapping[str, object],
    *,
    candidate_id: str,
    source_manifest: Mapping[str, object],
) -> dict[str, object]:
    """Build one path-free section context projection."""
    section_id = str(section["section_id"])
    raw_source = _mapping(source_manifest, section_id)
    channels = tuple(
        {
            "mnemonic": str(channel["mnemonic"]),
            "kind": str(channel.get("kind", "scalar")),
            "aliases": list(channel.get("aliases", ())),
            "unit": channel.get("unit"),
            "shape": list(channel.get("shape", ())),
        }
        for channel in _sequence(raw_source, "channels")
    )
    return {
        "task_index": list(source_manifest).index(section_id),
        "section_id": None,
        "sources": [
            {
                "candidate_id": candidate_id,
                "source_format": str(raw_source["source_format"]),
                "dataset_name": f"frozen-cbl-{section_id}",
                "channels": list(channels),
            }
        ],
        "channels": [],
    }


def _gate_requirements(section: Mapping[str, object]) -> dict[str, object]:
    """Capture exact track and binding multiplicity from one section plan."""
    components = _sequence(section, "components")
    tracks: list[dict[str, object]] = []
    for component in components:
        capability_id = str(component["capability_id"])
        if not capability_id.startswith("track."):
            continue
        bindings = [
            {
                "kind": "raster" if str(child["capability_id"]) == "binding.raster" else "curve",
                "channel": _mapping(child, "values").get("channel"),
            }
            for child in components
            if child.get("parent_component_id") == component.get("component_id")
        ]
        tracks.append(
            {
                "kind": capability_id.removeprefix("track."),
                "bindings": bindings,
            }
        )
    return {"tracks": tracks, "source_association_required": True}


def _replay_section_context(
    raw: object,
    source_paths: Mapping[str, str],
) -> ResolvedSectionContext:
    """Reconstruct a section context, injecting paths only into host models."""
    value = _mapping_value(raw)
    sources: list[SourceContext] = []
    for source in _sequence(value, "sources"):
        source_value = dict(source)
        candidate_id = str(source_value["candidate_id"])
        source_value["canonical_path"] = source_paths[candidate_id]
        sources.append(SourceContext.model_validate(source_value))
    return ResolvedSectionContext.model_validate({**value, "sources": sources})


def _mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    """Read one required JSON object."""
    item = value.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"Expected object at {key!r}.")
    return item


def _mapping_value(value: object) -> dict[str, object]:
    """Validate one JSON object value."""
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object.")
    return value


def _sequence(value: Mapping[str, object], key: str) -> list[dict[str, object]]:
    """Read one required JSON object sequence."""
    item = value.get(key)
    if not isinstance(item, list):
        raise ValueError(f"Expected list at {key!r}.")
    if not all(isinstance(entry, dict) for entry in item):
        raise ValueError(f"Expected object entries at {key!r}.")
    return item


def _sha256_json(value: object) -> str:
    """Hash canonical JSON for stable fixture integrity checks."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    """Capture the repository-local EXP-TW-00 corpus."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_CORPUS_PATH)
    args = parser.parse_args()
    capture_corpus(output_path=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
