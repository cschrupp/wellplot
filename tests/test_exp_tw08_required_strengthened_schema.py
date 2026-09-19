"""Focused EXP-TW-08 required-tag remediation-validation tests."""

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
from scripts.exp_tw03s_schema import SectionDraftS
from scripts.exp_tw08_required_strengthened_schema import (
    DEFAULT_SYSTEM_PROMPT,
    R1,
    RemediationVariant,
    compiler_projection_equivalence,
    golden_equivalence,
    remediation_variant_specs,
    response_model_for,
    run_remediation_attempt,
    run_remediation_section_attempts,
    run_remediation_stage,
    schema_artifact,
    schema_comparison,
    schema_sha256,
    structural_invariant_audit,
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
    """Minimal backend fake that records the provider boundary."""

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
    """Return a mutable JSON-shaped copy of one frozen strengthened draft."""
    return copy.deepcopy(load_golden_drafts()[section_role].model_dump(mode="json"))


def _golden_factory(section_role: str) -> object:
    """Build a fake result factory for one frozen section."""
    payload = _golden_payload(section_role)

    def factory(response_model: type[object]) -> object:
        return response_model.model_validate(payload)  # type: ignore[attr-defined]

    return factory


def _track(kind: str, binding: dict[str, object], *, role: str = "combo") -> dict[str, object]:
    """Build a minimal semantic track payload for structural tests."""
    payload: dict[str, object] = {
        "role": role,
        "kind": kind,
        "title": "Track",
        "bindings": [binding],
    }
    if kind == "array":
        payload["x_scale"] = {"minimum": 0, "maximum": 1}
    return payload


def _section(track: dict[str, object]) -> dict[str, object]:
    """Build a minimal section around one track."""
    return {
        "title": "Section",
        "source_candidate": "source-1",
        "tracks": [track],
    }


def _curve() -> dict[str, object]:
    """Build one minimal scalar binding."""
    return {
        "kind": "curve",
        "semantic_id": "curve",
        "channel": "CURVE",
        "scale": {"minimum": 0, "maximum": 1},
    }


def _raster() -> dict[str, object]:
    """Build one minimal raster binding."""
    return {
        "kind": "raster",
        "semantic_id": "raster",
        "channel": "ARRAY",
        "profile": "vdl",
        "sample_axis": {
            "unit": "samples",
            "minimum": 0,
            "maximum": 1,
            "tick_count": 2,
            "source_origin": 0,
            "source_step": 1,
        },
    }


def test_r0_reuses_frozen_section_draft_s_and_r1_is_distinct() -> None:
    """R0 is unchanged while R1 is a separate native Pydantic type."""
    specs = remediation_variant_specs()
    assert specs[0].response_model is SectionDraftS
    assert specs[1].response_model is R1.response_model
    assert specs[1].response_model is not SectionDraftS
    assert specs[1].response_model.__name__ == "SectionDraftS"
    assert R1.normal_track.__name__ == "NormalTrackDraftS"
    assert R1.reference_track.__name__ == "ReferenceTrackDraftS"
    assert R1.array_track.__name__ == "ArrayTrackDraftS"


def test_schema_diff_is_limited_to_required_track_tags() -> None:
    """R0/R1 native schemas differ only in the three tag fields."""
    comparison = schema_comparison()
    assert comparison["branch_names_identical"] is True
    assert comparison["branch_count_identical"] is True
    assert comparison["one_of_identical"] is True
    assert comparison["ref_targets_identical"] is True
    assert comparison["discriminator_property_identical"] is True
    assert comparison["discriminator_mapping_identical"] is True
    assert comparison["non_tag_schema_identical"] is True
    for branch in comparison["branches"].values():  # type: ignore[union-attr]
        assert branch["r0_kind_default"] in {"normal", "reference", "array"}
        assert branch["r1_kind_has_default"] is False
        assert branch["r0_kind_required"] is False
        assert branch["r1_kind_required"] is True
        assert branch["required_removed_from_r0"] == []
        assert branch["required_added_to_r1"] == ["kind"]
        assert branch["non_kind_fields_equivalent"] is True


def test_r1_preserves_all_strengthened_structural_invariants() -> None:
    """Every TW-03S structural guarantee is exercised on R1."""
    assert structural_invariant_audit() == {
        "normal_curve_only": True,
        "reference_curve_only": True,
        "array_raster_with_x_scale": True,
        "normal_rejects_raster": True,
        "reference_rejects_raster": True,
        "array_rejects_curve": True,
        "array_requires_x_scale": True,
        "role_domain_rejects_unknown": True,
        "role_kind_not_coupled": True,
    }


@pytest.mark.parametrize(
    ("kind", "binding"),
    [("normal", _raster()), ("reference", _raster()), ("array", _curve())],
)
def test_r1_rejects_incompatible_binding_shapes(
    kind: str,
    binding: dict[str, object],
) -> None:
    """R1 rejects each impossible curve/raster track combination."""
    with pytest.raises(ValidationError):
        response_model_for(RemediationVariant.R1).model_validate(_section(_track(kind, binding)))


def test_r1_requires_array_x_scale_and_historical_roles() -> None:
    """R1 keeps required array axes and the historical role domain."""
    array_without_scale = _track("array", _raster(), role="vdl")
    array_without_scale["x_scale"] = None
    with pytest.raises(ValidationError):
        response_model_for(RemediationVariant.R1).model_validate(_section(array_without_scale))

    with pytest.raises(ValidationError):
        response_model_for(RemediationVariant.R1).model_validate(
            _section(_track("normal", _curve(), role="anything"))
        )
    assert response_model_for(RemediationVariant.R1).model_validate(
        _section(_track("normal", _curve(), role="vdl"))
    )


def test_r0_and_r1_full_union_omission_behavior_is_recorded() -> None:
    """The artifact records actual top-level union behavior for omitted tags."""
    artifact = schema_artifact()
    assert artifact["r0_full_union_omitted_kind"] is False
    assert artifact["r1_full_union_omitted_kind"] is False


def test_goldens_have_identical_semantics_and_gate_a_results() -> None:
    """Both R1 goldens preserve values and corrected Gate-A success."""
    results = golden_equivalence()
    assert set(results) == {"main_pass", "repeat_pass"}
    for result in results.values():  # type: ignore[union-attr]
        assert result["r0_dump_equals_r1"] is True
        assert result["r1_dump_equals_golden"] is True
        assert result["gate_equal"] is True
        assert result["r1_gate"]["semantic_usable"] is True


def test_unchanged_compiler_consumes_equivalent_r0_r1_mappings() -> None:
    """The existing TW-02R compiler sees identical semantic projections."""
    assert compiler_projection_equivalence() == {"main_pass": True, "repeat_pass": True}


def test_schema_hashes_and_artifact_are_deterministic() -> None:
    """Native schema hashes and the full review artifact are stable."""
    assert schema_sha256(response_model_for(RemediationVariant.R0)) == schema_sha256(
        response_model_for(RemediationVariant.R0)
    )
    assert schema_sha256(response_model_for(RemediationVariant.R1)) == schema_sha256(
        response_model_for(RemediationVariant.R1)
    )
    first = schema_artifact()
    assert first == schema_artifact()
    json.dumps(first, sort_keys=True)


def test_provider_payload_prompt_and_settings_are_identical() -> None:
    """R0/R1 change only the requested response model."""
    bundle, context, requirements = _fixture_inputs("main_pass")
    expected_payload = serialize_provider_input(bundle)
    requests: list[StructuredGenerationRequest] = []

    for variant in RemediationVariant:
        backend = _FakeBackend(result_factory=_golden_factory("main_pass"))
        evidence = _run(
            run_remediation_attempt(
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
        assert evidence.outcome is AttemptOutcome.SUCCESS
        assert len(backend.calls) == 1
        request, response_model = backend.calls[0]
        requests.append(request)
        assert request.user_prompt == expected_payload
        assert request.system_prompt == DEFAULT_SYSTEM_PROMPT
        assert response_model is response_model_for(variant)
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
        run_remediation_attempt(
            "repeat_pass",
            RemediationVariant.R1,
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
            run_remediation_attempt(
                "main_pass",
                RemediationVariant.R0,
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
        run_remediation_section_attempts(
            "main_pass",
            RemediationVariant.R0,
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


def test_stage_writes_flushed_records_and_schema_artifact(tmp_path: Path) -> None:
    """A staged run persists attempts before advancing sections."""
    backends: list[_FakeBackend] = []

    def factory() -> _FakeBackend:
        role = "main_pass" if len(backends) == 0 else "repeat_pass"
        backend = _FakeBackend(result_factory=_golden_factory(role))
        backends.append(backend)
        return backend

    output_path = tmp_path / "attempts.jsonl"
    schema_path = tmp_path / "schema.json"
    summary = _run(
        run_remediation_stage(
            RemediationVariant.R0,
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
    assert json.loads(schema_path.read_text()) == schema_artifact()
