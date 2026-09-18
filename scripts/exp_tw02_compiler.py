"""Deterministic EXP-TW-02 compiler for typed section drafts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from scripts.exp_tw00_corpus import DEFAULT_CORPUS_PATH, load_corpus, score_section_draft
from scripts.exp_tw01_schema import DEFAULT_GOLDEN_PATH, SectionDraft, load_golden_drafts
from wellplot.agent.code_mode.enrichment import ResolvedSectionContext, SourceContext
from wellplot.model.authoring import AuthoringDataSource
from wellplot.model.intent import (
    AuthoringCurveBindingIntent,
    AuthoringDocumentIntent,
    AuthoringRasterBindingIntent,
    AuthoringSectionIntent,
    AuthoringTrackIntent,
)


@dataclass(frozen=True, slots=True)
class CompiledSectionDraft:
    """Canonical downstream intent plus a path-free review projection."""

    intent: AuthoringDocumentIntent
    normalized_projection: dict[str, object]


class DraftCompilationError(ValueError):
    """Deterministic failure while compiling an already validated draft."""

    def __init__(self, code: str, message: str) -> None:
        """Store a stable experimental compiler diagnostic."""
        self.code = code
        super().__init__(message)


def compile_section_draft(
    draft: SectionDraft | Mapping[str, object],
    *,
    section_context: ResolvedSectionContext,
    requirements: Mapping[str, object],
) -> CompiledSectionDraft:
    """Validate, Gate-A-check, and compile one semantic section draft."""
    validated = SectionDraft.model_validate(draft)
    gate = score_section_draft(
        validated.model_dump(mode="json"),
        section_context=section_context,
        requirements=requirements,
    )
    if gate != {
        "host_reference_valid": True,
        "channel_valid": True,
        "semantic_usable": True,
    }:
        raise DraftCompilationError(
            "gate_a_invalid",
            "SectionDraft failed EXP-TW-00 Gate A semantic validation.",
        )

    source = _selected_source(validated.source_candidate, section_context)
    if source is None:
        raise DraftCompilationError(
            "source_unrepresentable",
            "Validated SectionDraft source cannot be represented in the host context.",
        )
    if source.source_format not in {"las", "dlis"} or not source.canonical_path.strip():
        raise DraftCompilationError(
            "source_unrepresentable",
            "Selected source metadata cannot be represented by AuthoringDataSource.",
        )

    section_id = f"exp-tw02-section-{section_context.task_index}"
    tracks: list[AuthoringTrackIntent] = []
    for track_index, track in enumerate(validated.tracks):
        track_id = f"{section_id}.track-{track_index}"
        bindings = []
        for binding_index, binding in enumerate(track.bindings):
            binding_id = f"{track_id}.binding-{binding_index}"
            binding_fields = {
                "kind": binding.kind,
                "binding_id": binding_id,
                "section_id": section_id,
                "track_id": track_id,
                "channel": binding.channel,
            }
            if binding.kind == "curve":
                bindings.append(AuthoringCurveBindingIntent(**binding_fields))
            elif binding.kind == "raster":
                bindings.append(AuthoringRasterBindingIntent(**binding_fields))
            else:  # pragma: no cover - discriminated schema prevents this branch
                raise DraftCompilationError(
                    "binding_unrepresentable",
                    f"Binding kind {binding.kind!r} is not supported downstream.",
                )
        tracks.append(
            AuthoringTrackIntent(
                track_id=track_id,
                section_id=section_id,
                title=track.title,
                kind=track.kind,
                bindings=bindings,
            )
        )

    section_fields: dict[str, object] = {
        "section_id": section_id,
        "title": validated.title,
        "data_source": AuthoringDataSource(
            source_path=source.canonical_path,
            source_format=source.source_format,
        ),
        "tracks": tracks,
    }
    if validated.subtitle is not None:
        section_fields["subtitle"] = validated.subtitle
    section = AuthoringSectionIntent(**section_fields)
    intent = AuthoringDocumentIntent(sections=[section])
    return CompiledSectionDraft(
        intent=intent,
        normalized_projection=_normalized_projection(validated),
    )


def compile_golden_drafts(
    *,
    corpus_path: str | Path = DEFAULT_CORPUS_PATH,
    drafts_path: str | Path = DEFAULT_GOLDEN_PATH,
) -> dict[str, CompiledSectionDraft]:
    """Compile both frozen drafts through the enforced validation boundary."""
    corpus = load_corpus(corpus_path)
    drafts = load_golden_drafts(drafts_path)
    return {
        section_id: compile_section_draft(
            drafts[section_id],
            section_context=corpus.sections[index],
            requirements=corpus.gate_a["section_requirements"][section_id],
        )
        for index, section_id in enumerate(("main_pass", "repeat_pass"))
    }


def _selected_source(
    candidate_id: str,
    context: ResolvedSectionContext,
) -> SourceContext | None:
    """Return the one host source selected by the validated draft."""
    return next(
        (source for source in context.sources if source.candidate_id == candidate_id),
        None,
    )


def _normalized_projection(draft: SectionDraft) -> dict[str, object]:
    """Return stable semantic output without compiler-owned identity or paths."""
    return draft.model_dump(mode="json")


__all__ = [
    "CompiledSectionDraft",
    "DraftCompilationError",
    "compile_golden_drafts",
    "compile_section_draft",
]
