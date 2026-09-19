"""Focused EXP-TW-06 native Pydantic union-form compatibility tests."""

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
from scripts.exp_tw06_union_bisect import (
    BASELINE_SHA,
    DEFAULT_SYSTEM_PROMPT,
    ArrayTrackU,
    NormalTrackU,
    ReferenceTrackU,
    SectionDraftU1,
    SectionDraftU2,
    SectionDraftU3,
    UnionVariant,
    normalized_track_schema,
    response_model_for,
    run_union_attempt,
    run_union_ladder,
    run_union_section_attempts,
    schema_diff_summary,
    u2_u3_branch_equivalence,
    union_schema_artifact,
    union_variant_specs,
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


def test_u0_is_historical_and_u4_reuses_exact_tw05_s1() -> None:
    """The endpoints are the frozen historical and TW-05 controls."""
    assert response_model_for(UnionVariant.U0) is SectionDraft
    assert response_model_for(UnionVariant.U4).__name__ == "SectionDraftS1"
    assert BASELINE_SHA == "2e317e1"


@pytest.mark.parametrize("section_role", ["main_pass", "repeat_pass"])
def test_all_union_variants_preserve_golden_semantics(section_role: str) -> None:
    """Every U variant represents both frozen semantic outputs unchanged."""
    payload = _golden_payload(section_role)
    for spec in union_variant_specs():
        validated = spec.response_model.model_validate(payload)
        assert validated.model_dump(mode="json") == payload


def test_u1_is_one_track_model_without_discriminator() -> None:
    """U1 changes only the field-level kind annotation."""
    schema = SectionDraftU1.model_json_schema()
    assert "discriminator" not in json.dumps(schema, sort_keys=True)
    assert set(schema["$defs"]["TrackDraftU1"]["required"]) >= {
        "role",
        "kind",
        "title",
        "bindings",
    }
    kind_schema = schema["$defs"]["TrackDraftU1"]["properties"]["kind"]
    assert len(kind_schema["anyOf"]) == 3
    assert {branch["const"] for branch in kind_schema["anyOf"]} == {
        "normal",
        "reference",
        "array",
    }


def test_u1_relationship_to_u0_is_detected_from_native_schema() -> None:
    """The harness records whether native Pydantic makes U1 separating."""
    equivalent = normalized_track_schema(SectionDraft) == normalized_track_schema(SectionDraftU1)
    assert equivalent is False
    diff = schema_diff_summary(SectionDraft, SectionDraftU1)
    assert diff["track_schema_equivalent"] is False


def test_u2_is_plain_union_with_required_branch_literals_and_mixed_bindings() -> None:
    """U2 adds branch models without a discriminator or kind defaults."""
    schema = SectionDraftU2.model_json_schema()
    serialized = json.dumps(schema, sort_keys=True)
    assert "discriminator" not in serialized
    assert "anyOf" in serialized
    for branch, value in (
        (NormalTrackU, "normal"),
        (ReferenceTrackU, "reference"),
        (ArrayTrackU, "array"),
    ):
        branch_schema = schema["$defs"][branch.__name__]
        assert "kind" in branch_schema["required"]
        assert "default" not in branch_schema["properties"]["kind"]
        assert branch_schema["properties"]["kind"]["const"] == value

    payload = _golden_payload("main_pass")
    for index, track in enumerate(payload["tracks"]):
        track["bindings"][0] = {
            "kind": "curve" if index == 3 else "raster",
            "semantic_id": f"synthetic-{index}",
            "channel": "SYNTHETIC",
            **(
                {"scale": {"minimum": 0, "maximum": 1}}
                if index == 3
                else {
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
            ),
        }
    assert SectionDraftU2.model_validate(payload)


def test_u1_and_u2_require_kind_without_defaults() -> None:
    """Both intermediate representations reject an omitted kind."""
    payload = _golden_payload("main_pass")
    payload["tracks"][0].pop("kind")
    with pytest.raises(ValidationError):
        SectionDraftU1.model_validate(payload)
    with pytest.raises(ValidationError):
        SectionDraftU2.model_validate(payload)


def test_u3_reuses_u2_branches_and_adds_only_standard_discriminator_wrapper() -> None:
    """U2/U3 branch definitions match while their union wrappers differ."""
    assert u2_u3_branch_equivalence() == {
        "NormalTrackU": True,
        "ReferenceTrackU": True,
        "ArrayTrackU": True,
    }
    u2_schema = SectionDraftU2.model_json_schema()
    u3_schema = SectionDraftU3.model_json_schema()
    assert "discriminator" not in json.dumps(u2_schema, sort_keys=True)
    assert "discriminator" in json.dumps(u3_schema, sort_keys=True)
    assert schema_diff_summary(SectionDraftU2, SectionDraftU3)["track_schema_equivalent"] is False


def test_schema_artifact_is_deterministic_and_reviewable() -> None:
    """The artifact contains native schemas, hashes, diffs, and branch proof."""
    first = union_schema_artifact()
    second = union_schema_artifact()
    assert first == second
    assert [item["schema_variant"] for item in first["variants"]] == [
        "U0",
        "U1",
        "U2",
        "U3",
        "U4",
    ]
    assert len(first["adjacent_diffs"]) == 4
    assert first["u2_u3_branch_equivalence"] == {
        "NormalTrackU": True,
        "ReferenceTrackU": True,
        "ArrayTrackU": True,
    }
    json.dumps(first, sort_keys=True)


def test_provider_input_and_prompt_are_identical_for_every_variant() -> None:
    """Only the response model changes at the provider boundary."""
    bundle, context, requirements = _fixture_inputs("main_pass")
    expected_prompt = serialize_provider_input(bundle)
    requests: list[StructuredGenerationRequest] = []

    def factory(response_model: type[object]) -> object:
        return response_model.model_validate(_golden_payload("main_pass"))  # type: ignore[attr-defined]

    for spec in union_variant_specs():
        backend = _FakeBackend(result_factory=factory)
        evidence = _run(
            run_union_attempt(
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
        requests.append(request)
        assert request.user_prompt == expected_prompt
        assert request.system_prompt == DEFAULT_SYSTEM_PROMPT
        assert response_model is spec.response_model
        assert "canonical_path" not in request.user_prompt
    assert {request.user_prompt for request in requests} == {expected_prompt}
    assert {request.system_prompt for request in requests} == {DEFAULT_SYSTEM_PROMPT}


def test_provider_failure_is_terminal_without_retry() -> None:
    """Typed provider failures remain one-call terminal outcomes."""
    bundle, context, requirements = _fixture_inputs("repeat_pass")
    backend = _FakeBackend(
        error=ProviderRequestError(ProviderFailureCategory.TIMEOUT, "safe timeout")
    )
    evidence = _run(
        run_union_attempt(
            "repeat_pass",
            UnionVariant.U2,
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


def test_section_attempts_flush_each_completed_attempt() -> None:
    """The sink receives each result before the next request is constructed."""
    bundle, context, requirements = _fixture_inputs("main_pass")
    backends: list[_FakeBackend] = []
    flushed: list[tuple[int, int]] = []

    def factory() -> _FakeBackend:
        backend = _FakeBackend(
            result_factory=lambda model: model.model_validate(_golden_payload("main_pass"))
        )
        backends.append(backend)
        return backend

    def sink(attempt: object) -> None:
        flushed.append((len(backends), attempt.attempt_index))  # type: ignore[attr-defined]

    summary = _run(
        run_union_section_attempts(
            "main_pass",
            UnionVariant.U0,
            factory,
            provider_id="fake",
            model_id="test-model",
            config=AttemptConfig(timeout_seconds=30),
            attempt_count=2,
            bundle=bundle,
            section_context=context,
            gate_requirements=requirements,
            attempt_sink=sink,
        )
    )
    assert summary.total_attempts == 2
    assert flushed == [(1, 1), (2, 2)]
    assert all(len(backend.calls) == 1 for backend in backends)


def test_ladder_stops_after_u0_control_failure(tmp_path: Path) -> None:
    """A failed historical control prevents causal interpretation downstream."""
    backends: list[_FakeBackend] = []

    def factory() -> _FakeBackend:
        backend = _FakeBackend(
            error=ProviderRequestError(ProviderFailureCategory.INVALID_RESPONSE, "invalid")
        )
        backends.append(backend)
        return backend

    summaries = _run(
        run_union_ladder(
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
    assert summaries[0].schema_variant is UnionVariant.U0
    assert len(backends) == 2
    assert all(len(backend.calls) == 1 for backend in backends)


def test_ladder_can_stage_u0_without_downstream_calls(tmp_path: Path) -> None:
    """The control stage can be persisted before spending downstream calls."""
    backends: list[_FakeBackend] = []

    def factory() -> _FakeBackend:
        backend = _FakeBackend(
            result_factory=lambda model: model.model_validate(
                _golden_payload("main_pass" if len(backends) == 0 else "repeat_pass")
            )
        )
        backends.append(backend)
        return backend

    summaries = _run(
        run_union_ladder(
            factory,
            provider_id="fake",
            model_id="test-model",
            config=AttemptConfig(timeout_seconds=30),
            attempt_count=1,
            through_variant=UnionVariant.U0,
            output_jsonl=tmp_path / "attempts.jsonl",
            schema_output=tmp_path / "schemas.json",
        )
    )
    assert [summary.schema_variant for summary in summaries] == [UnionVariant.U0]
    assert len(backends) == 2


def test_u2_and_u3_do_not_add_role_kind_policy() -> None:
    """The micro-bisect does not add benchmark-specific role/kind semantics."""
    payload = _golden_payload("main_pass")
    payload["tracks"][0]["role"] = "vdl"
    payload["tracks"][0]["kind"] = "array"
    assert SectionDraftU2.model_validate(payload)
    assert SectionDraftU3.model_validate(payload)
