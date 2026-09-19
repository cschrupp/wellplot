"""EXP-TW-03S strengthened experimental SectionDraft schema."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from scripts.exp_tw00_corpus import FrozenWorkerCorpus, load_corpus
from scripts.exp_tw02r_contract import (
    CurveBindingDraft,
    RasterBindingDraft,
    ScaleDraft,
    SectionDraft,
    load_golden_drafts,
    validate_gate_a,
)
from scripts.exp_tw03_provider import FirstAttemptEvidence
from wellplot.agent.code_mode.enrichment import ResolvedSectionContext

BASELINE_SHA = "151efd0"
EXPERIMENT_VERSION = "exp-tw-03s.structural-schema.v1"
TrackRole = Literal["combo", "depth", "cbl", "vdl"]


class _StrengthenedModel(BaseModel):
    """Strict immutable model base for the strengthened experiment."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class NormalTrackDraftS(_StrengthenedModel):
    """Normal track whose ordered bindings are all scalar curves."""

    role: TrackRole
    kind: Literal["normal"] = "normal"
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft, ...] = Field(min_length=1)


class ReferenceTrackDraftS(_StrengthenedModel):
    """Reference track whose ordered bindings are all scalar curves."""

    role: TrackRole
    kind: Literal["reference"] = "reference"
    title: str = Field(min_length=1)
    x_scale: ScaleDraft | None = None
    bindings: tuple[CurveBindingDraft, ...] = Field(min_length=1)


class ArrayTrackDraftS(_StrengthenedModel):
    """Array track whose bindings are rasters and which has an x scale."""

    role: TrackRole
    kind: Literal["array"] = "array"
    title: str = Field(min_length=1)
    x_scale: ScaleDraft
    bindings: tuple[RasterBindingDraft, ...] = Field(min_length=1)


TrackDraftS = Annotated[
    NormalTrackDraftS | ReferenceTrackDraftS | ArrayTrackDraftS,
    Field(discriminator="kind"),
]


class SectionDraftS(_StrengthenedModel):
    """Strengthened semantic section intent with structural track invariants."""

    title: str = Field(min_length=1)
    source_candidate: str = Field(min_length=1)
    tracks: tuple[TrackDraftS, ...] = Field(min_length=1)


class ReplayCount(_StrengthenedModel):
    """One redacted deterministic replay count."""

    key: str = Field(min_length=1)
    count: int = Field(ge=0)


class ReplaySummary(_StrengthenedModel):
    """Aggregate TW-03 replay result for one provider and section."""

    experiment_version: str = EXPERIMENT_VERSION
    baseline_sha: str = BASELINE_SHA
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    section_role: Literal["main_pass", "repeat_pass"]
    historical_attempts: int = Field(ge=1)
    historical_structurally_valid_count: int = Field(ge=0)
    historical_gate_a_valid_count: int = Field(ge=0)
    strengthened_structurally_valid_count: int = Field(ge=0)
    structural_rejection_count: int = Field(ge=0)
    gate_a_valid_count_after_strengthening: int = Field(ge=0)
    historical_structural_failure_count: int = Field(ge=0)
    structural_error_path_counts: tuple[ReplayCount, ...] = ()
    prior_gate_a_failures_rejected_structurally: int = Field(ge=0)
    prior_gate_a_failures_remaining_structurally_valid: int = Field(ge=0)


class ReplayContractError(ValueError):
    """Raised when read-only replay evidence violates its expected contract."""


def strengthen_draft(
    draft: SectionDraft | Mapping[str, object],
) -> SectionDraftS:
    """Revalidate a historical draft through a serialized mapping boundary."""
    if isinstance(draft, SectionDraft):
        payload = draft.model_dump(mode="json")
    elif isinstance(draft, Mapping):
        payload = dict(draft)
    else:
        raise TypeError("TW-03S accepts a historical SectionDraft or mapping.")
    return SectionDraftS.model_validate(payload)


def strengthen_golden_drafts() -> dict[str, SectionDraftS]:
    """Revalidate both frozen TW-02R goldens without changing their values."""
    return {
        section_key: strengthen_draft(draft) for section_key, draft in load_golden_drafts().items()
    }


def replay_evidence_file(path: str | Path) -> tuple[ReplaySummary, ...]:
    """Replay one TW-03 JSONL file without provider calls or output mutation."""
    attempts = _load_attempts(path)
    if not attempts:
        raise ValueError(f"No TW-03 attempt records found in {path!s}.")

    grouped: dict[str, list[FirstAttemptEvidence]] = {}
    for attempt in attempts:
        grouped.setdefault(attempt.section_role, []).append(attempt)
    return tuple(
        _replay_attempts(role_attempts)
        for role_attempts in (grouped[role] for role in sorted(grouped))
    )


def _replay_attempts(attempts: Sequence[FirstAttemptEvidence]) -> ReplaySummary:
    """Replay one section role from one provider/model evidence file."""
    provider_ids = {attempt.provider_id for attempt in attempts}
    model_ids = {attempt.model_id for attempt in attempts}
    if len(provider_ids) != 1 or len(model_ids) != 1:
        raise ReplayContractError("One evidence file must contain one provider/model.")

    section_role = attempts[0].section_role
    corpus = load_corpus()
    context = _context_for_role(corpus, section_role)
    requirements = corpus.gate_a["section_requirements"][section_role]
    structural_errors: list[str] = []
    strengthened_count = 0
    structural_rejections = 0
    gate_a_after = 0
    historical_gate_a_valid = 0
    prior_gate_a_failures_rejected = 0
    prior_gate_a_failures_remaining = 0

    for attempt in attempts:
        if attempt.gate_a is not None and attempt.gate_a.semantic_usable:
            historical_gate_a_valid += 1
        if attempt.draft is None:
            continue

        try:
            strengthened = strengthen_draft(attempt.draft)
        except ValidationError as error:
            structural_rejections += 1
            structural_errors.extend(_error_path(error))
            if attempt.gate_a is not None and not attempt.gate_a.semantic_usable:
                prior_gate_a_failures_rejected += 1
            continue

        strengthened_count += 1
        if strengthened.model_dump(mode="json") != attempt.draft.model_dump(mode="json"):
            raise ReplayContractError(
                "TW-03S changed semantic values during strengthened validation."
            )

        gate = validate_gate_a(
            attempt.draft,
            section_key=section_role,
            section_context=context,
            requirements=requirements,
        )
        historical_gate = bool(attempt.gate_a and attempt.gate_a.semantic_usable)
        if bool(gate["semantic_usable"]) != historical_gate:
            raise ReplayContractError("TW-03S replay changed the corrected Gate-A result.")
        if gate["semantic_usable"]:
            gate_a_after += 1
        elif attempt.gate_a is not None:
            prior_gate_a_failures_remaining += 1

    if gate_a_after > historical_gate_a_valid:
        raise ReplayContractError("TW-03S replay increased Gate-A success count.")

    return ReplaySummary(
        provider_id=next(iter(provider_ids)),
        model_id=next(iter(model_ids)),
        section_role=section_role,
        historical_attempts=len(attempts),
        historical_structurally_valid_count=sum(attempt.draft is not None for attempt in attempts),
        historical_gate_a_valid_count=historical_gate_a_valid,
        strengthened_structurally_valid_count=strengthened_count,
        structural_rejection_count=structural_rejections,
        gate_a_valid_count_after_strengthening=gate_a_after,
        historical_structural_failure_count=sum(attempt.draft is None for attempt in attempts),
        structural_error_path_counts=_counts(structural_errors),
        prior_gate_a_failures_rejected_structurally=prior_gate_a_failures_rejected,
        prior_gate_a_failures_remaining_structurally_valid=prior_gate_a_failures_remaining,
    )


def serialize_replay_results(results: Sequence[ReplaySummary]) -> str:
    """Serialize only compact deterministic replay aggregates."""
    return json.dumps(
        {
            "baseline_sha": BASELINE_SHA,
            "experiment_version": EXPERIMENT_VERSION,
            "summaries": [result.model_dump(mode="json") for result in results],
        },
        sort_keys=True,
        indent=2,
    )


def _load_attempts(path: str | Path) -> tuple[FirstAttemptEvidence, ...]:
    """Load only redacted attempt rows from one TW-03 JSONL artifact."""
    attempts: list[FirstAttemptEvidence] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if payload.get("record_type") == "attempt":
            payload = dict(payload)
            payload.pop("record_type", None)
            attempts.append(FirstAttemptEvidence.model_validate(payload))
    return tuple(attempts)


def _context_for_role(
    corpus: FrozenWorkerCorpus,
    section_role: str,
) -> ResolvedSectionContext:
    """Resolve the frozen Gate-A context by opaque source candidate."""
    candidate_id = "source-1" if section_role == "main_pass" else "source-2"
    for section in corpus.sections:
        if any(source.candidate_id == candidate_id for source in section.sources):
            return section
    raise ValueError(f"Frozen corpus has no context for {section_role!r}.")


def _error_path(error: ValidationError) -> tuple[str, ...]:
    """Return redacted error type/location fingerprints without input values."""
    return tuple(
        f"{item['type']}@{'.'.join(str(part) for part in item['loc'])}" for item in error.errors()
    )


def _counts(values: Sequence[str]) -> tuple[ReplayCount, ...]:
    """Count error fingerprints in deterministic key order."""
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return tuple(ReplayCount(key=key, count=counts[key]) for key in sorted(counts))


def _parse_args() -> argparse.Namespace:
    """Parse the two evidence inputs and optional aggregate output path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qwen-jsonl", type=Path, required=True)
    parser.add_argument("--nemotron-jsonl", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    """Replay both provider artifacts and print or write redacted aggregates."""
    args = _parse_args()
    results = tuple(
        result
        for path in (args.qwen_jsonl, args.nemotron_jsonl)
        for result in replay_evidence_file(path)
    )
    serialized = serialize_replay_results(results)
    if args.output is None:
        print(serialized)
    else:
        args.output.write_text(serialized + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()


__all__ = [
    "ArrayTrackDraftS",
    "BASELINE_SHA",
    "EXPERIMENT_VERSION",
    "NormalTrackDraftS",
    "ReferenceTrackDraftS",
    "ReplayContractError",
    "ReplaySummary",
    "SectionDraftS",
    "TrackRole",
    "TrackDraftS",
    "replay_evidence_file",
    "serialize_replay_results",
    "strengthen_draft",
    "strengthen_golden_drafts",
]
