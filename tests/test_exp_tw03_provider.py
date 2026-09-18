"""Focused EXP-TW-03 first-attempt provider experiment tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from scripts.exp_tw00_corpus import load_corpus
from scripts.exp_tw02i_input import build_typed_worker_input, serialize_provider_input
from scripts.exp_tw02r_contract import SectionDraft, load_golden_drafts
from scripts.exp_tw03_provider import (
    AttemptConfig,
    AttemptOutcome,
    ExperimentSummary,
    run_first_attempt,
    run_section_attempts,
    serialize_evidence,
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
    """Minimal provider fake recording one structured call boundary."""

    result: object | None = None
    error: Exception | None = None
    calls: list[tuple[StructuredGenerationRequest, type[object]]] = field(default_factory=list)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[object],
    ) -> object:
        """Record the request and return or raise the configured first result."""
        self.calls.append((request, response_model))
        if self.error is not None:
            raise self.error
        return self.result


def _fixture_inputs(section_role: str) -> tuple[object, object, object]:
    """Build the frozen bundle, host context, and Gate-A requirements."""
    corpus = load_corpus()
    candidate_id = "source-1" if section_role == "main_pass" else "source-2"
    context = next(
        section
        for section in corpus.sections
        if any(source.candidate_id == candidate_id for source in section.sources)
    )
    bundle = build_typed_worker_input(section_role)  # type: ignore[arg-type]
    requirements = corpus.gate_a["section_requirements"][section_role]
    return bundle, context, requirements


def _result(section_role: str, *, draft: SectionDraft | None = None) -> object:
    """Create one fake structured result from the frozen golden output."""
    golden = load_golden_drafts()[section_role]
    return StructuredGenerationResult(
        value=draft or golden,
        metrics=ProviderMetrics(
            input_tokens=101,
            output_tokens=37,
            total_tokens=138,
            latency_ms=12.5,
        ),
    )


def _run(coroutine: object) -> object:
    """Run one provider experiment coroutine without an async test plugin."""
    return asyncio.run(coroutine)


def test_success_uses_exact_input_and_section_draft_response_model() -> None:
    """A valid first response is scored once with the supplied model unchanged."""
    bundle, context, requirements = _fixture_inputs("main_pass")
    backend = _FakeBackend(result=_result("main_pass"))

    evidence = _run(
        run_first_attempt(
            "main_pass",
            backend,
            provider_id="fake",
            model_id="test-model",
            config=AttemptConfig(timeout_seconds=30, temperature=1, max_output_tokens=512),
            bundle=bundle,
            section_context=context,
            gate_requirements=requirements,
        )
    )

    assert evidence.outcome is AttemptOutcome.SUCCESS
    assert evidence.draft is backend.result.value
    assert len(backend.calls) == 1
    request, response_model = backend.calls[0]
    assert response_model is SectionDraft
    assert request.user_prompt == serialize_provider_input(bundle)
    assert evidence.metrics is not None
    assert evidence.gate_a is not None and evidence.gate_a.semantic_usable is True


def test_gate_a_failure_is_preserved_without_retry() -> None:
    """A structurally valid but semantically wrong draft remains a scored failure."""
    bundle, context, requirements = _fixture_inputs("main_pass")
    invalid_draft = load_golden_drafts()["main_pass"].model_copy(
        update={"title": "Wrong section title"}
    )
    backend = _FakeBackend(result=_result("main_pass", draft=invalid_draft))

    evidence = _run(
        run_first_attempt(
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

    assert evidence.outcome is AttemptOutcome.GATE_A_FAILURE
    assert evidence.draft == invalid_draft
    assert evidence.gate_a is not None and evidence.gate_a.semantic_usable is False
    assert len(backend.calls) == 1


@pytest.mark.parametrize(
    ("category", "outcome"),
    [
        (ProviderFailureCategory.TIMEOUT, AttemptOutcome.PROVIDER_FAILURE),
        (ProviderFailureCategory.TRANSPORT, AttemptOutcome.PROVIDER_FAILURE),
        (ProviderFailureCategory.INVALID_RESPONSE, AttemptOutcome.STRUCTURED_OUTPUT_FAILURE),
        (ProviderFailureCategory.VALIDATION, AttemptOutcome.STRUCTURED_OUTPUT_FAILURE),
    ],
)
def test_provider_categories_remain_distinguishable_without_retry(
    category: ProviderFailureCategory,
    outcome: AttemptOutcome,
) -> None:
    """Typed provider categories map to stable experiment outcomes once."""
    bundle, context, requirements = _fixture_inputs("repeat_pass")
    backend = _FakeBackend(
        error=ProviderRequestError(category, "safe provider diagnostic", status_code=503)
    )

    evidence = _run(
        run_first_attempt(
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

    assert evidence.outcome is outcome
    assert evidence.provider_failure is not None
    assert evidence.provider_failure.category is category
    assert len(backend.calls) == 1


def test_unvalidated_structured_result_is_a_failure_without_repair() -> None:
    """A backend result that is not a SectionDraft is not patched or retried."""
    bundle, context, requirements = _fixture_inputs("main_pass")
    backend = _FakeBackend(
        result=StructuredGenerationResult(
            value=SimpleNamespace(not_a_section_draft=True),
            metrics=ProviderMetrics(latency_ms=5),
        )
    )

    evidence = _run(
        run_first_attempt(
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

    assert evidence.outcome is AttemptOutcome.STRUCTURED_OUTPUT_FAILURE
    assert evidence.draft is None
    assert len(backend.calls) == 1


def test_repeated_attempts_are_independent_and_aggregate_deterministically() -> None:
    """Ten attempts share no prior output or failure feedback."""
    backends: list[_FakeBackend] = []

    def backend_factory() -> _FakeBackend:
        backend = _FakeBackend(
            result=_result("repeat_pass") if not backends else None,
            error=None
            if not backends
            else ProviderRequestError(
                ProviderFailureCategory.TIMEOUT,
                "safe timeout",
            ),
        )
        backends.append(backend)
        return backend

    summary = _run(
        run_section_attempts(
            "repeat_pass",
            backend_factory,
            provider_id="fake",
            model_id="test-model",
            config=AttemptConfig(timeout_seconds=30),
            attempt_count=10,
        )
    )

    assert isinstance(summary, ExperimentSummary)
    assert summary.total_attempts == 10
    assert summary.provider_call_successes == 1
    assert summary.structurally_valid_outputs == 1
    assert summary.gate_a_valid_outputs == 1
    assert [(item.category, item.count) for item in summary.outcome_counts] == [
        ("provider_failure", 9),
        ("success", 1),
    ]
    assert all(len(backend.calls) == 1 for backend in backends)
    prompts = {backend.calls[0][0].user_prompt for backend in backends}
    assert prompts == {serialize_provider_input(build_typed_worker_input("repeat_pass"))}


def test_gate_a_receives_the_provider_object_without_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Gate-A call observes the exact typed object returned by the provider."""
    bundle, context, requirements = _fixture_inputs("main_pass")
    draft = load_golden_drafts()["main_pass"]
    backend = _FakeBackend(result=_result("main_pass", draft=draft))
    observed: list[object] = []

    def fake_gate(candidate: object, **kwargs: object) -> dict[str, bool]:
        observed.append(candidate)
        return {
            "host_reference_valid": True,
            "channel_valid": True,
            "semantic_usable": True,
            "source_selection_valid": True,
            "titles_valid": True,
            "semantic_fields_valid": True,
        }

    monkeypatch.setattr("scripts.exp_tw03_provider.validate_gate_a", fake_gate)
    evidence = _run(
        run_first_attempt(
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

    assert observed == [draft]
    assert observed[0] is draft
    assert evidence.outcome is AttemptOutcome.SUCCESS


def test_evidence_is_deterministic_and_does_not_store_paths_or_credentials() -> None:
    """Evidence contains hashes and typed output, not raw provider or host data."""
    bundle, context, requirements = _fixture_inputs("repeat_pass")
    backend = _FakeBackend(result=_result("repeat_pass"))
    evidence = _run(
        run_first_attempt(
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

    first = serialize_evidence(evidence)
    second = serialize_evidence(evidence)
    assert first == second
    assert "CBL_Main.dlis" not in first
    assert "CBL_Repeat.dlis" not in first
    assert "/home/" not in first
    assert "api_key" not in first.lower()
    assert "authorization" not in first.lower()
    assert "raw" not in first.lower()
    assert len(evidence.provider_input_sha256) == 64
    assert len(evidence.response_schema_sha256) == 64
