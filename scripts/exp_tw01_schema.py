"""Experimental EXP-TW-01 semantic section draft schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from scripts.exp_tw00_corpus import DEFAULT_CORPUS_PATH, load_corpus, score_section_draft

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "typed_worker" / "exp_tw01_cbl" / "golden_drafts.json"
)


class _DraftModel(BaseModel):
    """Strict immutable base for the experimental semantic response."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class CurveBindingDraft(_DraftModel):
    """One scalar channel decision for an ordered semantic track."""

    kind: Literal["curve"] = "curve"
    channel: str = Field(min_length=1)


class RasterBindingDraft(_DraftModel):
    """One array channel decision for an ordered semantic track."""

    kind: Literal["raster"] = "raster"
    channel: str = Field(min_length=1)


BindingDraft: TypeAlias = Annotated[
    CurveBindingDraft | RasterBindingDraft,
    Field(discriminator="kind"),
]


class TrackDraft(_DraftModel):
    """One ordered semantic track and its typed channel decisions."""

    kind: Literal["normal", "reference", "array"]
    title: str = Field(min_length=1)
    bindings: tuple[BindingDraft, ...] = Field(min_length=1)


class SectionDraft(_DraftModel):
    """Minimum typed semantic representation for the frozen CBL sections."""

    title: str = Field(min_length=1)
    subtitle: str | None = Field(default=None, min_length=1)
    source_candidate: str = Field(min_length=1)
    tracks: tuple[TrackDraft, ...] = Field(min_length=1)


def load_golden_drafts(
    path: str | Path = DEFAULT_GOLDEN_PATH,
) -> dict[str, SectionDraft]:
    """Load the manually authored drafts for both frozen CBL sections."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("EXP-TW-01 golden drafts must be a JSON object.")
    drafts = {
        section_id: SectionDraft.model_validate(value) for section_id, value in payload.items()
    }
    expected = {"main_pass", "repeat_pass"}
    if set(drafts) != expected:
        raise ValueError(f"EXP-TW-01 golden drafts must contain {sorted(expected)!r}.")
    return drafts


def score_golden_drafts(
    *,
    corpus_path: str | Path = DEFAULT_CORPUS_PATH,
    drafts_path: str | Path = DEFAULT_GOLDEN_PATH,
) -> dict[str, dict[str, object]]:
    """Score both golden drafts through the EXP-TW-00 Gate A machinery."""
    corpus = load_corpus(corpus_path)
    drafts = load_golden_drafts(drafts_path)
    return {
        section_id: score_section_draft(
            draft.model_dump(mode="json"),
            section_context=corpus.sections[index],
            requirements=corpus.gate_a["section_requirements"][section_id],
        )
        for index, section_id in enumerate(("main_pass", "repeat_pass"))
        for draft in (drafts[section_id],)
    }


__all__ = [
    "BindingDraft",
    "CurveBindingDraft",
    "RasterBindingDraft",
    "SectionDraft",
    "TrackDraft",
    "load_golden_drafts",
    "score_golden_drafts",
]
