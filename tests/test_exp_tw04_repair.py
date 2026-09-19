"""Focused EXP-TW-04 single semantic-repair tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from scripts.exp_tw00_corpus import load_corpus
from scripts.exp_tw02i_input import build_typed_worker_input, serialize_provider_input
from scripts.exp_tw03_provider import AttemptConfig
from scripts.exp_tw03s_schema import strengthen_golden_drafts
from scripts.exp_tw04_repair import (
    RepairTask,
    SemanticMismatch,
    build_repair_task,
    run_logical_attempt,
    semantic_mismatches,
    serialize_repair_task,
)

from wellplot.agent.providers.base import (
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)


@dataclass
class _FakeBackend:
    """Minimal backend fake recording every structured request."""

    responses: list[object] = field(default_factory=list)
    calls: list[tuple[StructuredGenerationRequest, type[object]]] = field(default_factory=list)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[object],
    ) -> object:
        """Return the next configured response."""
        self.calls.append((request, response_model))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _inputs(section_role: str) -> tuple[object, object, object]:
    """Build the frozen bundle, Gate-A context, and requirements."""
    corpus = load_corpus()
    candidate_id = "source-1" if section_role == "main_pass" else "source-2"
    context = next(
        section
        for section in corpus.sections
        if any(source.candidate_id == candidate_id for source in section.sources)
    )
    return (
        build_typed_worker_input(section_role),
        context,
        corpus.gate_a["section_requirements"][section_role],
    )


def _result(draft: object) -> StructuredGenerationResult:
    """Build one measured fake provider result."""
    return StructuredGenerationResult(
        value=draft,
        metrics=ProviderMetrics(
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            latency_ms=40,
        ),
    )


def _run(coroutine: object) -> object:
    """Run one async experiment case without a pytest async plugin."""
    return asyncio.run(coroutine)


def test_semantic_diff_uses_typed_input_not_golden_or_gate_state() -> None:
    """Mismatch expectations remain available without corpus/evaluator access."""
    import scripts.exp_tw04_repair as repair_module

    bundle, _context, _requirements = _inputs("main_pass")
    golden = strengthen_golden_drafts()["main_pass"]
    wrong = golden.model_copy(update={"title": "Wrong title"})

    assert "load_golden_drafts" not in repair_module.__dict__
    assert "validate_gate_a" not in repair_module.__dict__

    mismatches = semantic_mismatches(bundle, wrong)

    assert mismatches == (
        SemanticMismatch(
            output_path="SectionDraft.title",
            provider_input_path="task.title",
            issue="value_mismatch",
            observed="Wrong title",
            expected=bundle.task.title,
        ),
    )

    changed_bundle = bundle.model_copy(
        update={
            "task": bundle.task.model_copy(update={"title": "Changed typed task"}),
        }
    )
    changed = semantic_mismatches(changed_bundle, wrong)
    assert changed[0].expected == "Changed typed task"


def test_repair_task_is_path_free_and_deterministically_serialized() -> None:
    """Repair payload contains only typed input, prior draft, and mismatches."""
    bundle, _context, _requirements = _inputs("repeat_pass")
    draft = strengthen_golden_drafts()["repeat_pass"]
    task = build_repair_task(bundle, draft.model_copy(update={"title": "Wrong"}))
    serialized = serialize_repair_task(task)

    assert isinstance(task, RepairTask)
    assert "canonical_path" not in serialized
    assert "source_path" not in serialized
    assert "provider_id" not in serialized
    assert serialized == serialize_repair_task(task)


def test_first_success_makes_one_call_and_no_repair() -> None:
    """A first-attempt Gate-A success is terminal."""
    bundle, context, requirements = _inputs("main_pass")
    golden = strengthen_golden_drafts()["main_pass"]
    backend = _FakeBackend(responses=[_result(golden)])

    evidence = _run(
        run_logical_attempt(
            "main_pass",
            backend,
            provider_id="fake",
            model_id="test-model",
            config=AttemptConfig(timeout_seconds=30),
            bundle=bundle,
            section_context=context,
            gate_requirements=requirements,
        )
    )

    assert evidence.first_outcome.value == "success"
    assert evidence.repair_eligible is False
    assert evidence.repair_attempt is None
    assert evidence.final_outcome.value == "success"
    assert len(backend.calls) == 1
    assert backend.calls[0][1].__name__ == "SectionDraftS"
    assert backend.calls[0][0].user_prompt == serialize_provider_input(bundle)


def test_semantic_failure_makes_exactly_one_repair_call() -> None:
    """One structurally valid Gate-A failure gets one targeted repair only."""
    bundle, context, requirements = _inputs("main_pass")
    golden = strengthen_golden_drafts()["main_pass"]
    first = golden.model_copy(update={"title": "Wrong title"})
    backend = _FakeBackend(responses=[_result(first), _result(golden)])

    evidence = _run(
        run_logical_attempt(
            "main_pass",
            backend,
            provider_id="fake",
            model_id="test-model",
            config=AttemptConfig(timeout_seconds=30),
            bundle=bundle,
            section_context=context,
            gate_requirements=requirements,
        )
    )

    assert evidence.first_outcome.value == "gate_a_failure"
    assert evidence.repair_eligible is True
    assert evidence.repair_attempt is not None
    assert evidence.repair_attempt.outcome.value == "success"
    assert evidence.final_outcome.value == "success"
    assert len(backend.calls) == 2
    assert all(call[1].__name__ == "SectionDraftS" for call in backend.calls)
    assert evidence.repair_diagnostics[0].provider_input_path == "task.title"
    assert "Wrong title" in backend.calls[1][0].user_prompt
    assert "Main Pass" in backend.calls[1][0].user_prompt


def test_repair_failure_does_not_start_a_third_call() -> None:
    """A semantically wrong repair result is terminal."""
    bundle, context, requirements = _inputs("repeat_pass")
    golden = strengthen_golden_drafts()["repeat_pass"]
    first = golden.model_copy(update={"title": "Wrong first"})
    second = golden.model_copy(update={"title": "Wrong repair"})
    backend = _FakeBackend(responses=[_result(first), _result(second)])

    evidence = _run(
        run_logical_attempt(
            "repeat_pass",
            backend,
            provider_id="fake",
            model_id="test-model",
            config=AttemptConfig(timeout_seconds=30),
            bundle=bundle,
            section_context=context,
            gate_requirements=requirements,
        )
    )

    assert evidence.final_outcome.value == "gate_a_failure"
    assert len(backend.calls) == 2


@pytest.mark.parametrize(
    "error",
    [
        ProviderRequestError(ProviderFailureCategory.TIMEOUT, "safe timeout"),
        ProviderRequestError(ProviderFailureCategory.TRANSPORT, "safe transport"),
        ProviderRequestError(ProviderFailureCategory.INVALID_RESPONSE, "safe invalid"),
    ],
)
def test_provider_or_structured_failure_is_terminal_without_repair(
    error: Exception,
) -> None:
    """Provider and structured failures do not enter semantic repair."""
    bundle, context, requirements = _inputs("main_pass")
    backend = _FakeBackend(responses=[error])

    async def run() -> object:
        try:
            return await run_logical_attempt(
                "main_pass",
                backend,
                provider_id="fake",
                model_id="test-model",
                config=AttemptConfig(timeout_seconds=30),
                bundle=bundle,
                section_context=context,
                gate_requirements=requirements,
            )
        except Exception:
            raise

    evidence = _run(run())

    assert evidence.repair_eligible is False
    assert evidence.repair_attempt is None
    assert len(backend.calls) == 1
    if error.category is ProviderFailureCategory.INVALID_RESPONSE:
        assert evidence.first_outcome.value == "structured_output_failure"
    else:
        assert evidence.first_outcome.value == "provider_failure"


def test_unvalidated_structured_result_is_terminal_without_repair() -> None:
    """A completed call without SectionDraftS does not enter semantic repair."""
    bundle, context, requirements = _inputs("main_pass")
    backend = _FakeBackend(
        responses=[
            StructuredGenerationResult(
                value=SimpleNamespace(not_a_section_draft=True),
                metrics=ProviderMetrics(latency_ms=5),
            )
        ]
    )

    evidence = _run(
        run_logical_attempt(
            "main_pass",
            backend,
            provider_id="fake",
            model_id="test-model",
            config=AttemptConfig(timeout_seconds=30),
            bundle=bundle,
            section_context=context,
            gate_requirements=requirements,
        )
    )

    assert evidence.first_outcome.value == "structured_output_failure"
    assert evidence.repair_eligible is False
    assert len(backend.calls) == 1


def test_unexpected_backend_validation_error_propagates() -> None:
    """Unexpected implementation errors remain visible instead of being repaired."""
    bundle, context, requirements = _inputs("main_pass")
    backend = _FakeBackend(
        responses=[
            ValidationError.from_exception_data(
                "BackendModel",
                [{"type": "string_type", "loc": ("field",), "input": 1}],
            )
        ]
    )

    with pytest.raises(ValidationError):
        _run(
            run_logical_attempt(
                "main_pass",
                backend,
                provider_id="fake",
                model_id="test-model",
                config=AttemptConfig(timeout_seconds=30),
                bundle=bundle,
                section_context=context,
                gate_requirements=requirements,
            )
        )
    assert len(backend.calls) == 1


def test_summary_separates_first_repair_and_final_counts() -> None:
    """Summary metrics expose repair conversion and bounded call counts."""
    bundle, context, requirements = _inputs("main_pass")
    golden = strengthen_golden_drafts()["main_pass"]
    first = golden.model_copy(update={"title": "Wrong title"})
    backend = _FakeBackend(responses=[_result(first), _result(golden)])

    evidence = _run(
        run_logical_attempt(
            "main_pass",
            backend,
            provider_id="fake",
            model_id="test-model",
            config=AttemptConfig(timeout_seconds=30),
            bundle=bundle,
            section_context=context,
            gate_requirements=requirements,
        )
    )
    from scripts.exp_tw04_repair import summarize_attempts

    summary = summarize_attempts("main_pass", (evidence,))

    assert summary.logical_attempts == 1
    assert summary.first_gate_a_success_count == 0
    assert summary.repair_eligible_count == 1
    assert summary.repair_calls == 1
    assert summary.repair_gate_a_success_count == 1
    assert summary.repair_conversion_count == 1
    assert summary.final_success_count == 1
    assert summary.total_tokens_total == 60
    assert summary.total_latency_ms == 80
