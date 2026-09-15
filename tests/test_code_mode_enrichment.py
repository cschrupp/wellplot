"""CM-41 tests for deterministic semantic-plan enrichment."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pydantic import ValidationError

from wellplot.agent.code_mode.enrichment import (
    ChannelContext,
    EnrichmentErrorCode,
    LoadedSource,
    SemanticEnricher,
    SemanticEnrichmentError,
    SourceCandidate,
    SourceMetadata,
)
from wellplot.agent.code_mode.planner import SectionTask, SemanticPlan
from wellplot.model.authoring import AuthoringDocumentSpec


@dataclass
class _Loader:
    """Fake source loader returning bounded semantic metadata."""

    calls: list[tuple[Path, str]] = field(default_factory=list)

    def load(self, path: Path, source_format: str) -> LoadedSource:
        """Record the canonical load and return metadata without samples."""
        self.calls.append((path, source_format))
        return LoadedSource(
            dataset_name=path.stem,
            well_metadata=(SourceMetadata(key="WELL", value="CM-41"),),
            channels=(
                ChannelContext(
                    mnemonic="GR",
                    kind="scalar",
                    unit="gAPI",
                    shape=(),
                    description="Gamma ray",
                ),
                ChannelContext(
                    mnemonic="VDL",
                    kind="array",
                    unit="mV",
                    shape=(64,),
                ),
            ),
        )


def _document(*, duplicate_titles: bool = False) -> AuthoringDocumentSpec:
    """Build a document with general, service-title, and detail slots."""
    second_title = "Main Pass" if duplicate_titles else "Repeat Pass"
    return AuthoringDocumentSpec(
        name="cm-41",
        title="CM-41",
        header={
            "general_fields": [{"slot_id": "well", "key": "well", "label": "Well Name"}],
            "service_titles": [{"slot_id": "service"}],
            "detail": {
                "kind": "open_hole",
                "rows": [
                    {
                        "row_id": "location",
                        "key": "location",
                        "label": "Location",
                        "values": [{"slot_id": "location-value"}],
                    },
                    {
                        "row_id": "elevation",
                        "keys": ["kb", "gl"],
                        "label_cells": ["KB", "GL"],
                        "columns": [
                            {"cells": [{"slot_id": "elevation-kb"}]},
                            {"cells": [{"slot_id": "elevation-gl"}]},
                        ],
                    },
                ],
            },
        },
        sections=[
            {
                "id": "main",
                "title": "Main Pass",
                "subtitle": "CBL presentation",
                "tracks": [
                    {
                        "id": "combo",
                        "title": "Combo",
                        "kind": "normal",
                        "width_mm": 20,
                    }
                ],
            },
            {
                "id": "repeat",
                "title": second_title,
                "subtitle": "Repeat presentation",
                "tracks": [
                    {
                        "id": "combo",
                        "title": "Repeat Combo",
                        "kind": "normal",
                        "width_mm": 20,
                    }
                ],
            },
        ],
    )


def _plan(
    *,
    hint: str | None = None,
    source_hints: tuple[str, ...] = (),
    duplicate_titles: bool = False,
) -> SemanticPlan:
    """Build one semantic plan for enrichment tests."""
    return SemanticPlan(
        summary="Prepare a section context.",
        section_tasks=(
            SectionTask(
                goal="Prepare the CBL section.",
                capability_ids=("section.log_plot",),
                existing_section_hint=hint,
                source_hints=source_hints,
            ),
        ),
    )


def _candidate(
    root: Path,
    *,
    name: str = "main.las",
    labels: tuple[str, ...] = ("main",),
) -> SourceCandidate:
    """Create one explicit candidate under the test root."""
    return SourceCandidate(
        candidate_id=name,
        root_id="input",
        path=name,
        labels=labels,
    )


def _enricher(root: Path, loader: _Loader | None = None) -> tuple[SemanticEnricher, _Loader]:
    """Build an enricher with one declared host root."""
    effective_loader = loader or _Loader()
    enricher = SemanticEnricher(loader=effective_loader, allowed_roots={"input": root})
    return enricher, effective_loader


@pytest.mark.parametrize(
    ("filename", "source_format"),
    (("main.las", "las"), ("repeat.dlis", "dlis")),
)
def test_explicit_sources_are_normalized_and_formats_are_inferred(
    tmp_path: Path,
    filename: str,
    source_format: str,
) -> None:
    """Known LAS/DLIS suffixes resolve under the declared root only."""
    (tmp_path / filename).write_text("source", encoding="utf-8")
    enricher, loader = _enricher(tmp_path)
    plan = _plan(source_hints=(Path(filename).stem,))
    candidate = _candidate(tmp_path, name=filename, labels=())

    result = enricher.enrich(
        plan=plan,
        document=_document(),
        source_candidates=(candidate,),
    )

    source = result.sections[0].sources[0]
    assert source.canonical_path == str((tmp_path / filename).resolve())
    assert source.source_format == source_format
    assert loader.calls == [(Path(source.canonical_path), source_format)]


def test_source_selection_is_bounded_to_explicit_candidates(tmp_path: Path) -> None:
    """A matching filename outside the candidate list is never discovered."""
    (tmp_path / "hidden.dlis").write_text("source", encoding="utf-8")
    enricher, loader = _enricher(tmp_path)

    with pytest.raises(SemanticEnrichmentError) as caught:
        enricher.enrich(
            plan=_plan(source_hints=("hidden",)),
            document=_document(),
            source_candidates=(),
        )

    assert caught.value.code is EnrichmentErrorCode.SOURCE_MISSING
    assert loader.calls == []


@pytest.mark.parametrize(
    "candidate_path",
    ("../outside.las",),
)
def test_source_traversal_is_rejected(tmp_path: Path, candidate_path: str) -> None:
    """Relative traversal cannot escape the declared host root."""
    root = tmp_path / "input"
    root.mkdir()
    (tmp_path / "outside.las").write_text("outside", encoding="utf-8")
    enricher, _ = _enricher(root)
    candidate = SourceCandidate(
        candidate_id="outside",
        root_id="input",
        path=candidate_path,
        labels=("outside",),
    )

    with pytest.raises(SemanticEnrichmentError) as caught:
        enricher.enrich(
            plan=_plan(source_hints=("outside",)),
            document=_document(),
            source_candidates=(candidate,),
        )

    assert caught.value.code is EnrichmentErrorCode.SOURCE_OUTSIDE_ROOT
    assert str(tmp_path) not in str(caught.value)


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    """A symlink resolving outside the declared root cannot be loaded."""
    root = tmp_path / "input"
    root.mkdir()
    outside = tmp_path / "outside.las"
    outside.write_text("outside", encoding="utf-8")
    link = root / "link.las"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks are unavailable in this test environment.")

    enricher, _ = _enricher(root)
    with pytest.raises(SemanticEnrichmentError) as caught:
        enricher.enrich(
            plan=_plan(source_hints=("link",)),
            document=_document(),
            source_candidates=(
                SourceCandidate(
                    candidate_id="link",
                    root_id="input",
                    path="link.las",
                ),
            ),
        )

    assert caught.value.code is EnrichmentErrorCode.SOURCE_OUTSIDE_ROOT


def test_missing_directory_and_unknown_format_fail_without_loader_call(tmp_path: Path) -> None:
    """Missing, directory, and unknown-format candidates are rejected early."""
    root = tmp_path / "input"
    root.mkdir()
    (root / "folder").mkdir()
    enricher, loader = _enricher(root)

    cases = (
        ("missing.las", EnrichmentErrorCode.SOURCE_MISSING),
        ("folder", EnrichmentErrorCode.SOURCE_MISSING),
        ("unknown.txt", EnrichmentErrorCode.SOURCE_FORMAT_UNKNOWN),
    )
    for filename, expected_code in cases:
        if filename == "unknown.txt":
            (root / filename).write_text("source", encoding="utf-8")
        with pytest.raises(SemanticEnrichmentError) as caught:
            enricher.enrich(
                plan=_plan(source_hints=(Path(filename).stem,)),
                document=_document(),
                source_candidates=(
                    SourceCandidate(
                        candidate_id=Path(filename).stem,
                        root_id="input",
                        path=filename,
                    ),
                ),
            )
        assert caught.value.code is expected_code
    assert loader.calls == []


def test_trusted_format_can_resolve_unknown_suffix_but_conflicts_are_rejected(
    tmp_path: Path,
) -> None:
    """Trusted host metadata may resolve an unknown suffix but not contradict LAS/DLIS."""
    (tmp_path / "staged.data").write_text("source", encoding="utf-8")
    enricher, loader = _enricher(tmp_path)
    result = enricher.enrich(
        plan=_plan(source_hints=("staged",)),
        document=_document(),
        source_candidates=(
            SourceCandidate(
                candidate_id="staged",
                root_id="input",
                path="staged.data",
                trusted_format="dlis",
            ),
        ),
    )
    assert result.sections[0].sources[0].source_format == "dlis"
    assert loader.calls[0][1] == "dlis"

    (tmp_path / "conflict.las").write_text("source", encoding="utf-8")
    with pytest.raises(SemanticEnrichmentError) as caught:
        enricher.enrich(
            plan=_plan(source_hints=("conflict",)),
            document=_document(),
            source_candidates=(
                SourceCandidate(
                    candidate_id="conflict",
                    root_id="input",
                    path="conflict.las",
                    trusted_format="dlis",
                ),
            ),
        )
    assert caught.value.code is EnrichmentErrorCode.SOURCE_FORMAT_CONFLICT


def test_equivalent_paths_are_loaded_once_and_channels_are_semantic_only(tmp_path: Path) -> None:
    """Canonical-path caching deduplicates equivalent candidates per call."""
    data = tmp_path / "data"
    data.mkdir()
    source = data / "same.dlis"
    source.write_text("source", encoding="utf-8")
    enricher, loader = _enricher(tmp_path)
    plan = SemanticPlan(
        summary="Prepare two source views.",
        section_tasks=(
            SectionTask(
                goal="Use both explicit source labels.",
                capability_ids=("section.log_plot",),
                source_hints=("first", "second"),
            ),
        ),
    )
    candidates = (
        SourceCandidate(
            candidate_id="first",
            root_id="input",
            path="data/same.dlis",
        ),
        SourceCandidate(
            candidate_id="second",
            root_id="input",
            path="data/../data/same.dlis",
        ),
    )

    result = enricher.enrich(plan=plan, document=_document(), source_candidates=candidates)

    assert loader.calls == [(source.resolve(), "dlis")]
    assert len(result.sections[0].sources) == 2
    assert result.sections[0].sources[0].channels[0].shape == ()
    assert result.sections[0].sources[0].channels[1].shape == (64,)
    assert "values" not in result.sections[0].sources[0].model_dump(mode="json")


def test_section_hint_resolution_is_exact_then_lexical_and_preserves_plan(tmp_path: Path) -> None:
    """Only deterministic title/subtitle matching resolves existing sections."""
    (tmp_path / "main.las").write_text("source", encoding="utf-8")
    enricher, _ = _enricher(tmp_path)
    plan = _plan(hint="  MAIN   PASS  ", source_hints=("main",))

    result = enricher.enrich(
        plan=plan,
        document=_document(),
        source_candidates=(_candidate(tmp_path),),
    )

    assert result.plan == plan
    assert result.sections[0].section_id == "main"
    assert {slot.slot_id for slot in result.report.header_slots} == {
        "well",
        "service",
        "location-value",
        "elevation-kb",
        "elevation-gl",
    }


def test_section_hint_containment_requires_one_match(tmp_path: Path) -> None:
    """Containment is allowed only when it produces one deterministic match."""
    enricher, _ = _enricher(tmp_path)
    (tmp_path / "main.las").write_text("source", encoding="utf-8")

    contained = enricher.enrich(
        plan=_plan(hint="CBL presentation"),
        document=_document(),
        source_candidates=(),
    )
    assert contained.sections[0].section_id == "main"

    with pytest.raises(SemanticEnrichmentError) as unresolved:
        enricher.enrich(
            plan=_plan(hint="Gamma ray only"),
            document=_document(),
            source_candidates=(),
        )
    assert unresolved.value.code is EnrichmentErrorCode.SECTION_HINT_UNRESOLVED

    with pytest.raises(SemanticEnrichmentError) as ambiguous:
        enricher.enrich(
            plan=_plan(hint="Main Pass", duplicate_titles=True),
            document=_document(duplicate_titles=True),
            source_candidates=(),
        )
    assert ambiguous.value.code is EnrichmentErrorCode.SECTION_HINT_AMBIGUOUS
    assert ambiguous.value.candidates == ("main", "repeat")


def test_new_section_has_no_allocated_id_and_existing_channels_use_facade(tmp_path: Path) -> None:
    """New tasks remain unresolved while existing tasks receive canonical projections."""
    (tmp_path / "main.las").write_text("source", encoding="utf-8")
    loader = _Loader()
    enricher = SemanticEnricher(loader=loader, allowed_roots={"input": tmp_path})
    plan = SemanticPlan(
        summary="Prepare existing and new work.",
        section_tasks=(
            SectionTask(
                goal="Update the existing pass.",
                capability_ids=("section.log_plot",),
                existing_section_hint="Main Pass",
                source_hints=("main",),
            ),
            SectionTask(
                goal="Prepare a new pass.",
                capability_ids=("section.log_plot",),
                source_hints=("main",),
            ),
        ),
    )

    result = enricher.enrich(
        plan=plan,
        document=_document(),
        source_candidates=(_candidate(tmp_path),),
    )

    assert result.sections[0].section_id == "main"
    assert result.sections[0].channels[0].mnemonic == "GR"
    assert result.sections[1].section_id is None


def test_duplicate_existing_section_targets_fail_before_source_loading(tmp_path: Path) -> None:
    """Two semantic tasks cannot independently mutate one host section target."""
    enricher, loader = _enricher(tmp_path)
    plan = SemanticPlan(
        summary="Duplicate revision targets.",
        section_tasks=(
            SectionTask(
                goal="Revise the main pass title.",
                capability_ids=("section.log_plot",),
                existing_section_hint="Main Pass",
            ),
            SectionTask(
                goal="Revise the main pass depth.",
                capability_ids=("section.log_plot",),
                existing_section_hint="Main Pass",
            ),
        ),
    )

    with pytest.raises(SemanticEnrichmentError) as duplicate:
        enricher.enrich(plan=plan, document=_document(), source_candidates=())

    assert duplicate.value.code is EnrichmentErrorCode.SECTION_TARGET_DUPLICATE
    assert duplicate.value.task_index == 1
    assert loader.calls == []


def test_enrichment_models_reject_extras_and_are_immutable() -> None:
    """Transient context contracts remain strict and frozen."""
    with pytest.raises(ValidationError):
        SourceCandidate(
            candidate_id="main",
            root_id="input",
            path="main.las",
            section_id="main",  # type: ignore[call-arg]
        )

    candidate = SourceCandidate(candidate_id="main", root_id="input", path="main.las")
    with pytest.raises(ValidationError):
        candidate.path = "other.las"  # type: ignore[misc]
