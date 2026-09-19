"""Focused EXP-TW-07 required-versus-defaulted tag tests."""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pydantic import ValidationError
from scripts.exp_tw00_corpus import load_corpus
from scripts.exp_tw02i_input import build_typed_worker_input, serialize_provider_input
from scripts.exp_tw02r_contract import load_golden_drafts
from scripts.exp_tw03_provider import AttemptConfig, AttemptOutcome
from scripts.exp_tw07_discriminator_default_bisect import (
    DEFAULT_SYSTEM_PROMPT,
    DefaultVariant,
    build_model_set,
    d1_accepts_omitted_kind,
    provider_input_sha256,
    response_model_for,
    run_default_attempt,
    run_default_section_attempts,
    run_default_stage,
    schema_artifact,
    schema_comparison,
    schema_sha256,
    system_prompt_sha256,
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
    """Minimal backend fake that records each exact provider boundary."""

    result_factory: object | None = None
    error: Exception | None = None
    calls: list[tuple[StructuredGenerationRequest, type[object]]] = field(default_factory=list)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[object],
    ) -> object:
        """Record one request and return its configured value or error."""
        self.calls.append((request, response_model))
        if self.error is not None:
            raise self.error
        value = self.result_factory(response_model)  # type: ignore[operator]
        return StructuredGenerationResult(
            value=value,
            metrics=ProviderMetrics(total_tokens=11, latency_ms=2.5),
        )


def _run(coroutine: object) -> object:
    """Run one async experiment operation in the synchronous test suite."""
    return asyncio.run(coroutine)


def _fixture_inputs(section_role: str) -> tuple[object, object, object]:
    """Build the frozen provider bundle, context, and Gate-A requirements."""
    corpus = load_corpus()
    candidate_id = "source-1" if section_role == "main_pass" else "source-2"
    context = next(
        section
        for section in corpus.sections
        if any(source.candidate_id == candidate_id for source in section.sources)
    )
    return (
        build_typed_worker_input(section_role),  # type: ignore[arg-type]
        context,
        corpus.gate_a["section_requirements"][section_role],
    )


def _golden_payload(section_role: str) -> dict[str, object]:
    """Return a mutable JSON-shaped copy of one frozen golden draft."""
    return copy.deepcopy(load_golden_drafts()[section_role].model_dump(mode="json"))


def _golden_factory(section_role: str) -> object:
    """Build a fake result factory for one frozen section."""
    payload = _golden_payload(section_role)

    def factory(response_model: type[object]) -> object:
        return response_model.model_validate(payload)  # type: ignore[attr-defined]

    return factory


def test_d0_and_d1_share_native_names_and_factory_shape() -> None:
    """Both variants use one model factory and identical model names."""
    d0 = build_model_set(default_discriminator=False)
    d1 = build_model_set(default_discriminator=True)
    assert d0.response_model is not d1.response_model
    assert d0.response_model.__name__ == d1.response_model.__name__ == "SectionDraftTag"
    assert d0.normal_track.__name__ == d1.normal_track.__name__ == "NormalTrackTag"
    assert d0.reference_track.__name__ == d1.reference_track.__name__ == "ReferenceTrackTag"
    assert d0.array_track.__name__ == d1.array_track.__name__ == "ArrayTrackTag"


def test_schema_comparison_has_only_defaulted_discriminator_differences() -> None:
    """The native schema audit identifies no unrelated D0/D1 changes."""
    comparison = schema_comparison()
    assert comparison["branch_names_identical"] is True
    assert comparison["branch_count_identical"] is True
    assert comparison["tracks_one_of_identical"] is True
    assert comparison["discriminator_property_name_identical"] is True
    assert comparison["discriminator_mapping_identical"] is True
    assert comparison["non_kind_schema_identical"] is True
    for branch in comparison["branches"].values():  # type: ignore[union-attr]
        assert branch["d0_kind_has_default"] is False
        assert branch["d0_kind_required"] is True
        assert branch["d1_kind_required"] is False
        assert branch["required_removed_from_d0"] == ["kind"]
        assert branch["required_added_to_d1"] == []
        assert branch["non_kind_fields_equivalent"] is True

    raw_diff = comparison["raw_diff"]
    assert len(raw_diff["added_paths"]) == 3  # type: ignore[index]
    assert all(path.endswith("properties.kind.default") for path in raw_diff["added_paths"])  # type: ignore[index]
    assert len(raw_diff["removed_paths"]) == 3  # type: ignore[index]


@pytest.mark.parametrize("section_role", ["main_pass", "repeat_pass"])
def test_both_native_variants_round_trip_both_golden_sections(section_role: str) -> None:
    """Explicit discriminator tags survive both native model variants."""
    payload = _golden_payload(section_role)
    for variant in DefaultVariant:
        model = response_model_for(variant)
        value = model.model_validate(payload)
        assert value.model_dump(mode="json") == payload


def test_d0_requires_kind_and_d1_native_omission_behavior_is_recorded() -> None:
    """The experiment records, rather than assumes, D1 omission behavior."""
    payload = _golden_payload("main_pass")
    payload["tracks"][0].pop("kind")  # type: ignore[index]
    with pytest.raises(ValidationError):
        response_model_for(DefaultVariant.D0).model_validate(payload)
    d1_accepts = d1_accepts_omitted_kind()
    if d1_accepts:
        branch = build_model_set(default_discriminator=True).normal_track
        value = branch.model_validate(payload["tracks"][0])
        assert value.kind == "normal"
    else:
        with pytest.raises(ValidationError):
            response_model_for(DefaultVariant.D1).model_validate(payload)


def test_provider_payload_and_prompt_are_identical_for_d0_and_d1() -> None:
    """Only the response model changes at the provider boundary."""
    bundle, context, requirements = _fixture_inputs("main_pass")
    expected_payload = serialize_provider_input(bundle)
    requests: list[StructuredGenerationRequest] = []
    backends: list[_FakeBackend] = []

    for variant in DefaultVariant:
        backend = _FakeBackend(result_factory=_golden_factory("main_pass"))
        backends.append(backend)
        evidence = _run(
            run_default_attempt(
                "main_pass",
                variant,
                backend,
                provider_id="fake",
                model_id="test-model",
                config=AttemptConfig(timeout_seconds=30),
                attempt_index=1,
                bundle=bundle,
                section_context=context,
                gate_requirements=requirements,
            )
        )
        assert evidence.outcome in {AttemptOutcome.SUCCESS, AttemptOutcome.GATE_A_FAILURE}
        assert evidence.normalized_output is not None
        assert len(backend.calls) == 1
        request, response_model = backend.calls[0]
        requests.append(request)
        assert request.user_prompt == expected_payload
        assert request.system_prompt == DEFAULT_SYSTEM_PROMPT
        assert response_model is response_model_for(variant)
        assert "canonical_path" not in request.user_prompt
        assert evidence.provider_input_sha256 == provider_input_sha256(bundle)
        assert evidence.system_prompt_sha256 == system_prompt_sha256()

    assert {request.user_prompt for request in requests} == {expected_payload}
    assert {request.system_prompt for request in requests} == {DEFAULT_SYSTEM_PROMPT}


def test_provider_failure_is_terminal_without_retry() -> None:
    """Typed provider failures remain one-call terminal outcomes."""
    bundle, context, requirements = _fixture_inputs("repeat_pass")
    backend = _FakeBackend(
        error=ProviderRequestError(ProviderFailureCategory.TIMEOUT, "safe timeout")
    )
    evidence = _run(
        run_default_attempt(
            "repeat_pass",
            DefaultVariant.D0,
            backend,
            provider_id="fake",
            model_id="test-model",
            config=AttemptConfig(timeout_seconds=30),
            attempt_index=1,
            bundle=bundle,
            section_context=context,
            gate_requirements=requirements,
        )
    )
    assert evidence.outcome is AttemptOutcome.PROVIDER_FAILURE
    assert len(backend.calls) == 1


def test_unexpected_backend_exception_propagates() -> None:
    """Unexpected implementation failures are not experiment outcomes."""
    bundle, context, requirements = _fixture_inputs("main_pass")
    backend = _FakeBackend(error=RuntimeError("programming defect"))
    with pytest.raises(RuntimeError, match="programming defect"):
        _run(
            run_default_attempt(
                "main_pass",
                DefaultVariant.D0,
                backend,
                provider_id="fake",
                model_id="test-model",
                config=AttemptConfig(timeout_seconds=30),
                attempt_index=1,
                bundle=bundle,
                section_context=context,
                gate_requirements=requirements,
            )
        )
    assert len(backend.calls) == 1


def test_section_attempts_flush_each_completed_attempt() -> None:
    """The sink receives each result before the next request is made."""
    backends: list[_FakeBackend] = []
    flushed: list[tuple[int, int]] = []

    def factory() -> _FakeBackend:
        backend = _FakeBackend(result_factory=_golden_factory("main_pass"))
        backends.append(backend)
        return backend

    def sink(attempt: object) -> None:
        flushed.append((len(backends), attempt.attempt_index))  # type: ignore[attr-defined]

    summary = _run(
        run_default_section_attempts(
            "main_pass",
            DefaultVariant.D0,
            factory,
            provider_id="fake",
            model_id="test-model",
            config=AttemptConfig(timeout_seconds=30),
            attempt_count=2,
            attempt_sink=sink,
        )
    )
    assert summary.total_attempts == 2
    assert flushed == [(1, 1), (2, 2)]
    assert all(len(backend.calls) == 1 for backend in backends)


def test_stage_writes_deterministic_schema_and_flushed_records(tmp_path: Path) -> None:
    """A staged run writes schema evidence and each completed record."""
    backends: list[_FakeBackend] = []

    def factory() -> _FakeBackend:
        role = "main_pass" if len(backends) == 0 else "repeat_pass"
        backend = _FakeBackend(result_factory=_golden_factory(role))
        backends.append(backend)
        return backend

    output_path = tmp_path / "attempts.jsonl"
    schema_path = tmp_path / "schema.json"
    summary = _run(
        run_default_stage(
            DefaultVariant.D0,
            factory,
            provider_id="fake",
            model_id="test-model",
            config=AttemptConfig(timeout_seconds=30),
            attempt_count=1,
            output_jsonl=output_path,
            schema_output=schema_path,
        )
    )
    records = [json.loads(line) for line in output_path.read_text().splitlines()]
    assert [record["record_type"] for record in records] == [
        "attempt",
        "section_summary",
        "attempt",
        "section_summary",
        "variant_summary",
    ]
    assert summary.total_attempts == 2
    assert len(backends) == 2
    first_schema = json.loads(schema_path.read_text())
    assert first_schema == schema_artifact()
    json.dumps(first_schema, sort_keys=True)


def test_schema_hashes_and_artifact_are_deterministic() -> None:
    """Native schema hashes and review artifact are stable across calls."""
    assert schema_sha256(response_model_for(DefaultVariant.D0)) == schema_sha256(
        response_model_for(DefaultVariant.D0)
    )
    assert schema_sha256(response_model_for(DefaultVariant.D1)) == schema_sha256(
        response_model_for(DefaultVariant.D1)
    )
    assert schema_artifact() == schema_artifact()
