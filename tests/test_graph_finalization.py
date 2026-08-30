"""Tests for verified final rendering and read-only visual QA."""

from __future__ import annotations

from functools import partial

import anyio

from wellplot.agent.graph import (
    FinalRenderArtifact,
    VisualReviewRequest,
    VisualReviewResult,
    finalize_document_intent,
)
from wellplot.model.authoring import AuthoringDocumentSpec
from wellplot.model.intent import AuthoringDocumentIntent


class _Renderer:
    """Record in-memory render calls without writing a file."""

    def __init__(self, *, mutate_document: bool = False) -> None:
        self.documents: list[AuthoringDocumentSpec] = []
        self.mutate_document = mutate_document

    def render(self, document: AuthoringDocumentSpec) -> FinalRenderArtifact:
        self.documents.append(document)
        if self.mutate_document:
            document.title = "Mutated by renderer"
        return FinalRenderArtifact(backend="test", page_count=1, page_images=(b"png",))


class _Reviewer:
    """Return deterministic structured corrections for finalization tests."""

    def __init__(
        self,
        corrections: list[dict[str, object]] | None = None,
        *,
        mutate_document: bool = False,
    ) -> None:
        self.requests: list[VisualReviewRequest] = []
        self.corrections = corrections or []
        self.mutate_document = mutate_document

    async def review(self, request: VisualReviewRequest) -> VisualReviewResult:
        self.requests.append(request)
        if self.mutate_document:
            request.document.title = "Mutated by reviewer"
            request.intent.title = "Mutated intent"
        return VisualReviewResult(corrections=self.corrections)


def _document(*, title: str = "Revised") -> AuthoringDocumentSpec:
    """Build a minimal canonical document for finalization tests."""
    return AuthoringDocumentSpec(
        name="finalization-test",
        title=title,
        sections=[
            {
                "id": "main",
                "title": "Main",
                "tracks": [
                    {
                        "id": "depth",
                        "title": "Depth",
                        "kind": "reference",
                        "width_mm": 20,
                    }
                ],
            }
        ],
    )


def _intent() -> AuthoringDocumentIntent:
    """Return the desired state satisfied by the default document."""
    return AuthoringDocumentIntent(title="Revised")


def test_final_render_artifact_freezes_page_images() -> None:
    """A renderer cannot leak a mutable page-image collection to visual QA."""
    artifact = FinalRenderArtifact(backend="test", page_count=1, page_images=[b"png"])

    assert artifact.page_images == (b"png",)
    assert isinstance(artifact.page_images, tuple)


def test_finalization_renders_only_after_semantic_verification() -> None:
    """A verified document reaches one final renderer call."""
    document = _document()
    renderer = _Renderer()

    result = anyio.run(
        partial(
            finalize_document_intent,
            document,
            _intent(),
            renderer=renderer,
            request="Render the final document.",
        )
    )

    assert result.success is True
    assert result.ready_for_delivery is True
    assert result.artifact is not None
    assert len(renderer.documents) == 1
    assert renderer.documents[0].model_dump(mode="json") == document.model_dump(mode="json")


def test_finalization_blocks_render_when_semantic_postconditions_fail() -> None:
    """A damaged document never reaches rendering or visual review."""
    document = _document(title="Original")
    renderer = _Renderer()
    reviewer = _Reviewer()

    result = anyio.run(
        partial(
            finalize_document_intent,
            document,
            _intent(),
            renderer=renderer,
            reviewer=reviewer,
        )
    )

    assert result.success is False
    assert result.artifact is None
    assert result.errors
    assert renderer.documents == []
    assert reviewer.requests == []


def test_finalization_returns_corrections_without_mutating_document() -> None:
    """Visual QA can request a typed repair but cannot apply it directly."""
    document = _document()
    before = document.model_dump(mode="json")
    renderer = _Renderer()
    reviewer = _Reviewer(
        corrections=[
            {
                "target_id": "main.depth",
                "capability_id": "track_layout",
                "issue": "Depth labels collide.",
                "requested_change": {"width_mm": 24},
            }
        ]
    )

    result = anyio.run(
        partial(
            finalize_document_intent,
            document,
            _intent(),
            renderer=renderer,
            reviewer=reviewer,
            request="Check depth-label spacing.",
            max_repair_cycles=2,
        )
    )

    assert result.success is True
    assert result.needs_repair is True
    assert result.ready_for_delivery is False
    assert result.max_repair_cycles == 2
    assert len(result.corrections) == 1
    assert reviewer.requests[0].request == "Check depth-label spacing."
    assert document.model_dump(mode="json") == before


def test_finalization_isolates_canonical_state_from_adapters() -> None:
    """Injected adapters cannot mutate the caller's canonical document or intent."""
    document = _document()
    intent = _intent()
    document_before = document.model_dump(mode="json")
    intent_before = intent.model_dump(mode="json")

    result = anyio.run(
        partial(
            finalize_document_intent,
            document,
            intent,
            renderer=_Renderer(mutate_document=True),
            reviewer=_Reviewer(mutate_document=True),
        )
    )

    assert result.success is True
    assert document.model_dump(mode="json") == document_before
    assert intent.model_dump(mode="json") == intent_before
