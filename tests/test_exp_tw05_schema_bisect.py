"""Focused EXP-TW-05 schema compatibility characterization tests."""

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
from scripts.exp_tw02r_contract import SectionDraft, load_golden_drafts
from scripts.exp_tw03_provider import AttemptConfig, AttemptOutcome
from scripts.exp_tw05_schema_bisect import (
    BASELINE_SHA,
    DEFAULT_SYSTEM_PROMPT,
    SchemaVariant,
    SectionDraftS1,
    SectionDraftS2,
    SectionDraftS3,
    SectionDraftS4,
    ladder_schema_artifact,
    response_model_for,
    run_schema_attempt,
    run_schema_ladder,
    schema_diff_summary,
    schema_sha256,
    schema_variant_specs,
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
    """Minimal backend fake that records the exact request boundary."""

    result_factory: object | None = None
    error: Exception | None = None
    calls: list[tuple[StructuredGenerationRequest, type[object]]] = field(default_factory=list)

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[object],
    ) -> object:
        """Record one call and return its configured value or error."""
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


def _golden_for_model(section_role: str, response_model: type[object]) -> object:
    """Validate a frozen golden through the requested ladder model."""
    return response_model.model_validate(_golden_payload(section_role))  # type: ignore[attr-defined]


def test_s0_and_s5_are_the_historical_and_strengthened_controls() -> None:
    """S0 reuses history exactly and S5 reuses the existing strengthened model."""
    assert response_model_for(SchemaVariant.S0) is SectionDraft
    assert response_model_for(SchemaVariant.S5).__name__ == "SectionDraftS"
    assert BASELINE_SHA == "91c4151"


@pytest.mark.parametrize("section_role", ["main_pass", "repeat_pass"])
def test_all_ladder_variants_preserve_frozen_golden_semantics(section_role: str) -> None:
    """Every ladder step can represent both unchanged frozen semantic outputs."""
    payload = _golden_payload(section_role)
    for spec in schema_variant_specs():
        validated = spec.response_model.model_validate(payload)
        assert validated.model_dump(mode="json") == payload


def test_schema_hashes_and_adjacent_diffs_are_deterministic() -> None:
    """Schema fingerprints are stable and each intended transition is visible."""
    first = [schema_sha256(spec.response_model) for spec in schema_variant_specs()]
    second = [schema_sha256(spec.response_model) for spec in schema_variant_specs()]
    assert first == second
    assert len(set(first)) == len(first)

    diffs = [
        schema_diff_summary(previous.response_model, current.response_model)
        for previous, current in zip(
            schema_variant_specs(), schema_variant_specs()[1:], strict=False
        )
    ]
    assert all(
        diff["added_paths"] or diff["removed_paths"] or diff["changed_paths"] for diff in diffs
    )
    assert any("discriminator" in path for path in diffs[0]["added_paths"])
    assert any(path.endswith(".required.3") for path in diffs[3]["added_paths"])


def test_schema_artifact_is_json_serializable_and_contains_adjacent_diffs() -> None:
    """The review artifact contains all six schemas and five structural diffs."""
    artifact = ladder_schema_artifact()
    assert [item["schema_variant"] for item in artifact["variants"]] == [
        "S0",
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
    ]
    assert len(artifact["adjacent_diffs"]) == 5
    json.dumps(artifact, sort_keys=True)


def test_s1_accepts_normal_raster_and_array_curve_before_binding_restrictions() -> None:
    """S1 changes only track discrimination, leaving binding families permissive."""
    normal_raster = _golden_payload("main_pass")
    normal_raster["tracks"][0]["bindings"][0] = {
        "kind": "raster",
        "semantic_id": "synthetic-raster",
        "channel": "SYNTHETIC",
        "profile": "vdl",
        "sample_axis": {
            "unit": "us",
            "minimum": 0,
            "maximum": 1,
            "tick_count": 2,
            "source_origin": 0,
            "source_step": 1,
        },
    }
    array_curve = _golden_payload("main_pass")
    array_curve["tracks"][3]["x_scale"] = None
    array_curve["tracks"][3]["bindings"][0] = {
        "kind": "curve",
        "semantic_id": "synthetic-curve",
        "channel": "SYNTHETIC",
        "scale": {"minimum": 0, "maximum": 1},
    }
    assert isinstance(SectionDraftS1.model_validate(normal_raster), SectionDraftS1)
    assert isinstance(SectionDraftS1.model_validate(array_curve), SectionDraftS1)
    with pytest.raises(ValidationError):
        SectionDraftS2.model_validate(normal_raster)
    with pytest.raises(ValidationError):
        SectionDraftS3.model_validate(array_curve)


def test_s2_still_allows_array_curve_until_s3() -> None:
    """S2 leaves array binding families unchanged until S3."""
    payload = _golden_payload("main_pass")
    payload["tracks"][3]["x_scale"] = None
    payload["tracks"][3]["bindings"][0] = {
        "kind": "curve",
        "semantic_id": "synthetic-curve",
        "channel": "SYNTHETIC",
        "scale": {"minimum": 0, "maximum": 1},
    }
    assert SectionDraftS2.model_validate(payload).tracks[3].kind == "array"
    with pytest.raises(ValidationError):
        SectionDraftS3.model_validate(payload)


def test_s3_keeps_array_x_scale_optional_but_s4_requires_it() -> None:
    """S4 introduces only the required array x scale."""
    payload = _golden_payload("main_pass")
    payload["tracks"][3].pop("x_scale")
    assert SectionDraftS3.model_validate(payload).tracks[3].kind == "array"
    with pytest.raises(ValidationError):
        SectionDraftS4.model_validate(payload)


@pytest.mark.parametrize("variant", list(SchemaVariant))
def test_historical_track_roles_remain_the_only_allowed_role_domain(
    variant: SchemaVariant,
) -> None:
    """The ladder never loosens the historical role vocabulary."""
    payload = _golden_payload("main_pass")
    payload["tracks"][0]["role"] = "anything"
    with pytest.raises(ValidationError):
        response_model_for(variant).model_validate(payload)


def test_every_variant_uses_identical_provider_input_and_one_call() -> None:
    """Schema changes do not alter the sole user payload or add calls."""
    bundle, context, requirements = _fixture_inputs("main_pass")
    expected_prompt = serialize_provider_input(bundle)
    backends: list[_FakeBackend] = []

    def factory(response_model: type[object]) -> object:
        return response_model.model_validate(_golden_payload("main_pass"))  # type: ignore[attr-defined]

    for spec in schema_variant_specs():
        backend = _FakeBackend(result_factory=factory)
        backends.append(backend)
        evidence = _run(
            run_schema_attempt(
                "main_pass",
                spec.variant,
                backend,
                provider_id="fake",
                model_id="test-model",
                config=AttemptConfig(timeout_seconds=30),
                bundle=bundle,
                section_context=context,
                gate_requirements=requirements,
            )
        )
        assert evidence.outcome is AttemptOutcome.SUCCESS
        assert len(backend.calls) == 1
        request, response_model = backend.calls[0]
        assert request.user_prompt == expected_prompt
        assert request.system_prompt == DEFAULT_SYSTEM_PROMPT
        assert response_model is spec.response_model
    assert {backend.calls[0][0].user_prompt for backend in backends} == {expected_prompt}


def test_provider_failure_is_terminal_without_retry() -> None:
    """Typed provider failures remain one-call terminal outcomes."""
    bundle, context, requirements = _fixture_inputs("repeat_pass")
    backend = _FakeBackend(
        error=ProviderRequestError(ProviderFailureCategory.TIMEOUT, "safe timeout")
    )
    evidence = _run(
        run_schema_attempt(
            "repeat_pass",
            SchemaVariant.S3,
            backend,
            provider_id="fake",
            model_id="test-model",
            config=AttemptConfig(timeout_seconds=30),
            bundle=bundle,
            section_context=context,
            gate_requirements=requirements,
        )
    )
    assert evidence.outcome is AttemptOutcome.PROVIDER_FAILURE
    assert len(backend.calls) == 1


def test_ladder_stops_after_s0_control_failure(tmp_path: Path) -> None:
    """A failed historical control prevents causal interpretation of later steps."""
    backends: list[_FakeBackend] = []

    def factory() -> _FakeBackend:
        backend = _FakeBackend(
            error=ProviderRequestError(ProviderFailureCategory.INVALID_RESPONSE, "invalid")
        )
        backends.append(backend)
        return backend

    summaries = _run(
        run_schema_ladder(
            factory,
            provider_id="fake",
            model_id="test-model",
            config=AttemptConfig(timeout_seconds=30),
            attempt_count=1,
            output_jsonl=tmp_path / "attempts.jsonl",
            schema_output=tmp_path / "schemas.json",
        )
    )
    assert len(summaries) == 1
    assert summaries[0].schema_variant is SchemaVariant.S0
    assert len(backends) == 2
    assert all(len(backend.calls) == 1 for backend in backends)
    records = tmp_path.joinpath("attempts.jsonl").read_text(encoding="utf-8").splitlines()
    assert sum('"record_type": "attempt"' in line for line in records) == 2


def test_ladder_can_stop_after_a_successful_s0_control(tmp_path: Path) -> None:
    """The staged runner can measure S0 without spending downstream calls."""
    backends: list[_FakeBackend] = []

    def factory() -> _FakeBackend:
        backend = _FakeBackend(
            result_factory=lambda model: model.model_validate(  # type: ignore[attr-defined]
                _golden_payload("main_pass" if len(backends) == 0 else "repeat_pass")
            )
        )
        backends.append(backend)
        return backend

    summaries = _run(
        run_schema_ladder(
            factory,
            provider_id="fake",
            model_id="test-model",
            config=AttemptConfig(timeout_seconds=30),
            attempt_count=1,
            through_variant=SchemaVariant.S0,
            output_jsonl=tmp_path / "attempts.jsonl",
            schema_output=tmp_path / "schemas.json",
        )
    )
    assert [summary.schema_variant for summary in summaries] == [SchemaVariant.S0]
    assert len(backends) == 2
