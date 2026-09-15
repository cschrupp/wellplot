"""Tests for the bounded Code Mode v2 visual-correction boundary."""

from __future__ import annotations

from dataclasses import dataclass, field

import anyio
import pytest

from wellplot.agent.code_mode.enrichment import ResolvedSectionContext
from wellplot.agent.code_mode.visual_correction import (
    SectionRenderArtifact,
    SectionRenderImage,
    VisualCorrectionStopReason,
    VisualEvaluator,
    VisualRenderError,
    VisualReviewDecision,
    VisualReviewRequest,
    VisualSectionCorrection,
    VisualSectionCorrectionCoordinator,
)
from wellplot.authoring_program.models import (
    AuthoringProgram,
    ProgramArtifact,
    ProgramExecutionResult,
    ProgramMetrics,
    ProgramSource,
)
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDataSource, AuthoringDocumentSpec
from wellplot.model.intent import (
    AuthoringClearIntent,
    AuthoringDocumentIntent,
    AuthoringSectionIntent,
)


def _document() -> AuthoringDocumentSpec:
    """Build a report with one target and one unrelated section."""
    return AuthoringDocumentSpec(
        name="visual-correction-test",
        title="Report",
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
            },
            {
                "id": "other",
                "title": "Other",
                "tracks": [
                    {
                        "id": "other-track",
                        "title": "Other track",
                        "kind": "normal",
                        "width_mm": 20,
                    }
                ],
            },
        ],
    )


def _original_intent() -> AuthoringDocumentIntent:
    """Return an intent already satisfied by the fixture document."""
    return AuthoringDocumentIntent(
        title="Report",
        sections=[AuthoringSectionIntent(section_id="main", title="Main")],
    )


def _context() -> ResolvedSectionContext:
    """Return the host-selected opaque section context."""
    return ResolvedSectionContext(task_index=0, section_id="main")


def _execution_result(
    intent: AuthoringDocumentIntent,
    *,
    repairs: int = 0,
) -> ProgramExecutionResult:
    """Build successful bounded section-worker evidence."""
    return ProgramExecutionResult(
        program=AuthoringProgram(source=ProgramSource(text="report = wp.report()")),
        success=True,
        artifact=ProgramArtifact(intent_fragment=intent),
        metrics=ProgramMetrics(program_repairs=repairs),
    )


@dataclass
class _Renderer:
    """Record defensive render inputs and optionally fail on one call."""

    fail_on_call: int | None = None
    documents: list[AuthoringDocumentSpec] = field(default_factory=list)
    section_ids: list[str] = field(default_factory=list)

    def render(self, document: AuthoringDocumentSpec, *, section_id: str) -> SectionRenderArtifact:
        self.documents.append(document)
        self.section_ids.append(section_id)
        if self.fail_on_call == len(self.documents):
            raise VisualRenderError("fixture renderer failed")
        return SectionRenderArtifact(
            images=(SectionRenderImage(mime_type="image/png", data=b"png"),)
        )


@dataclass
class _Evaluator:
    """Return one deterministic review decision while recording its safe request."""

    decision: VisualReviewDecision
    requests: list[VisualReviewRequest] = field(default_factory=list)

    async def review(self, request: VisualReviewRequest) -> VisualReviewDecision:
        self.requests.append(request)
        return self.decision


@dataclass
class _SectionCompiler:
    """Return one deterministic correction-worker result."""

    result: ProgramExecutionResult
    calls: list[dict[str, object]] = field(default_factory=list)

    async def compile(self, **kwargs: object) -> ProgramExecutionResult:
        self.calls.append(kwargs)
        return self.result


def _coordinator(
    renderer: _Renderer,
    evaluator: VisualEvaluator,
    compiler: _SectionCompiler,
) -> VisualSectionCorrectionCoordinator:
    """Build the coordinator with the production builtin registry."""
    return VisualSectionCorrectionCoordinator(
        section_compiler=compiler,  # type: ignore[arg-type]
        registry=create_builtin_registry(),
        renderer=renderer,
        evaluator=evaluator,
    )


def _run(
    coordinator: VisualSectionCorrectionCoordinator,
    **kwargs: object,
) -> object:
    """Run the async coordinator from synchronous pytest tests."""

    async def invoke() -> object:
        return await coordinator.correct(**kwargs)

    return anyio.run(invoke)


def _kwargs(document: AuthoringDocumentSpec | None = None) -> dict[str, object]:
    """Return stable coordinator inputs."""
    return {
        "request": "Improve the selected section heading spacing.",
        "document": document or _document(),
        "original_intent": _original_intent(),
        "section_context": _context(),
        "timeout_seconds": 5.0,
    }


def test_visual_correction_applies_one_root_change_and_preserves_everything_else() -> None:
    """A valid correction re-renders once without leaking private mutation."""
    document = _document()
    original_intent = _original_intent()
    before_document = document.model_dump(mode="json")
    before_intent = original_intent.model_dump(mode="json")
    renderer = _Renderer()
    evaluator = _Evaluator(
        VisualReviewDecision(
            correction=VisualSectionCorrection(
                capability_id="section.log_plot",
                issue="The section subtitle is missing.",
                requested_adjustment="Set the subtitle to 'Corrected'.",
            )
        )
    )
    compiler = _SectionCompiler(
        _execution_result(
            AuthoringDocumentIntent(
                sections=[AuthoringSectionIntent(section_id="main", subtitle="Corrected")]
            )
        )
    )

    result = _run(
        _coordinator(renderer, evaluator, compiler),
        **_kwargs(document),
    )

    assert result.success is True
    assert result.stop_reason is VisualCorrectionStopReason.CORRECTED
    assert result.corrected_document is not None
    assert result.corrected_document.sections[0].subtitle == "Corrected"
    assert result.metrics.render_count == 2
    assert result.metrics.review_count == 1
    assert result.metrics.correction_count == 1
    assert result.metrics.repair_count == 0
    assert len(compiler.calls) == 1
    assert document.model_dump(mode="json") == before_document
    assert original_intent.model_dump(mode="json") == before_intent
    assert renderer.section_ids == ["main", "main"]
    review_payload = evaluator.requests[0].model_dump_json()
    assert "main" not in review_payload
    assert "document" not in review_payload
    assert "output_path" not in review_payload


def test_visual_correction_stops_successfully_without_a_second_render() -> None:
    """No correction is a successful terminal state with one review."""
    renderer = _Renderer()
    evaluator = _Evaluator(VisualReviewDecision())
    compiler = _SectionCompiler(_execution_result(AuthoringDocumentIntent()))

    result = _run(
        _coordinator(renderer, evaluator, compiler),
        **_kwargs(),
    )

    assert result.success is True
    assert result.stop_reason is VisualCorrectionStopReason.NO_CORRECTION
    assert result.corrected_document is None
    assert result.metrics.render_count == 1
    assert result.metrics.review_count == 1
    assert result.metrics.correction_count == 0
    assert len(renderer.documents) == 1
    assert compiler.calls == []


def test_semantic_failure_prevents_render_and_review() -> None:
    """Visual QA cannot start when the original intent is unsatisfied."""
    renderer = _Renderer()
    evaluator = _Evaluator(VisualReviewDecision())
    compiler = _SectionCompiler(_execution_result(AuthoringDocumentIntent()))
    kwargs = _kwargs()
    kwargs["original_intent"] = AuthoringDocumentIntent(title="Wrong")

    result = _run(
        _coordinator(renderer, evaluator, compiler),
        **kwargs,
    )

    assert result.success is False
    assert result.stop_reason is VisualCorrectionStopReason.SEMANTIC_VERIFICATION_FAILED
    assert result.metrics.render_count == 0
    assert result.metrics.review_count == 0
    assert renderer.documents == []
    assert evaluator.requests == []


@pytest.mark.parametrize(
    "bad_intent",
    [
        AuthoringDocumentIntent(
            sections=[
                AuthoringSectionIntent(
                    section_id="main",
                    data_source=AuthoringDataSource(source_path="secret.las", source_format="las"),
                )
            ]
        ),
        AuthoringDocumentIntent(
            sections=[
                AuthoringSectionIntent(
                    section_id="main",
                    tracks=[{"track_id": "new-track", "title": "New", "kind": "normal"}],
                )
            ]
        ),
        AuthoringDocumentIntent(sections=AuthoringClearIntent()),
    ],
)
def test_visual_worker_output_cannot_escape_root_only_boundary(
    bad_intent: AuthoringDocumentIntent,
) -> None:
    """Child or source changes are rejected after worker execution."""
    renderer = _Renderer()
    evaluator = _Evaluator(
        VisualReviewDecision(
            correction=VisualSectionCorrection(
                capability_id="section.log_plot",
                issue="Root issue.",
                requested_adjustment="Apply the root-only correction.",
            )
        )
    )
    compiler = _SectionCompiler(_execution_result(bad_intent))

    result = _run(
        _coordinator(renderer, evaluator, compiler),
        **_kwargs(),
    )

    assert result.success is False
    assert result.stop_reason is VisualCorrectionStopReason.POSTCONDITION_FAILED
    assert result.corrected_document is None
    assert result.metrics.render_count == 1
    assert result.metrics.review_count == 1
    assert result.metrics.correction_count == 1
    assert len(renderer.documents) == 1


def test_final_render_failure_does_not_expose_corrected_document() -> None:
    """A failed final render remains atomic after private correction."""
    renderer = _Renderer(fail_on_call=2)
    evaluator = _Evaluator(
        VisualReviewDecision(
            correction=VisualSectionCorrection(
                capability_id="section.log_plot",
                issue="Root issue.",
                requested_adjustment="Set the subtitle to 'Corrected'.",
            )
        )
    )
    compiler = _SectionCompiler(
        _execution_result(
            AuthoringDocumentIntent(
                sections=[AuthoringSectionIntent(section_id="main", subtitle="Corrected")]
            )
        )
    )

    result = _run(
        _coordinator(renderer, evaluator, compiler),
        **_kwargs(),
    )

    assert result.success is False
    assert result.stop_reason is VisualCorrectionStopReason.FINAL_RENDER_FAILED
    assert result.corrected_document is None
    assert result.metrics.render_count == 2
    assert result.metrics.review_count == 1
    assert result.metrics.correction_count == 1


def test_visual_reviewer_cannot_select_an_unregistered_capability() -> None:
    """Capability identity is canonical and host-validated before application."""
    renderer = _Renderer()
    evaluator = _Evaluator(
        VisualReviewDecision(
            correction=VisualSectionCorrection(
                capability_id="track.normal",
                issue="Child issue.",
                requested_adjustment="Change a track.",
            )
        )
    )
    compiler = _SectionCompiler(_execution_result(AuthoringDocumentIntent()))

    result = _run(
        _coordinator(renderer, evaluator, compiler),
        **_kwargs(),
    )

    assert result.success is False
    assert result.stop_reason is VisualCorrectionStopReason.CORRECTION_REJECTED
    assert result.metrics.correction_count == 1
    assert compiler.calls == []


def test_invalid_visual_reviewer_payload_is_a_bounded_failure() -> None:
    """Evaluator schema violations cannot escape the visual boundary."""
    renderer = _Renderer()
    evaluator = _Evaluator(
        decision={
            "correction": {
                "target_scope": "selected_section",
                "section_id": "main",
                "capability_id": "section.log_plot",
                "issue": "Invalid target field.",
                "requested_adjustment": "Change the root.",
            }
        }  # type: ignore[arg-type]
    )
    compiler = _SectionCompiler(_execution_result(AuthoringDocumentIntent()))

    result = _run(
        _coordinator(renderer, evaluator, compiler),
        **_kwargs(),
    )

    assert result.success is False
    assert result.stop_reason is VisualCorrectionStopReason.REVIEW_FAILED
    assert result.corrected_document is None
    assert result.metrics.render_count == 1
    assert result.metrics.review_count == 1
    assert compiler.calls == []
