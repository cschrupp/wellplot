"""CM-56 deterministic tests for the typed section shadow worker."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from wellplot.agent.code_mode.enrichment import (
    ChannelContext,
    ResolvedSectionContext,
    SourceContext,
)
from wellplot.agent.code_mode.planner import SectionTask
from wellplot.agent.code_mode.section_semantics import (
    CurveBindingSemanticDraft,
    NormalTrackSemanticDraft,
    SectionSemanticDraft,
)
from wellplot.agent.code_mode.typed_section_worker import (
    RESPONSE_SCHEMA_SHA256,
    TYPED_SECTION_SYSTEM_PROMPT,
    TypedSectionCompiler,
    TypedSectionRepresentabilityError,
    TypedSectionWorkerError,
    TypedSectionWorkerErrorCode,
    build_typed_section_input,
    response_schema_sha256,
    serialize_typed_section_input,
)
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec


@dataclass
class _Backend(ModelBackendProtocol):
    """Small backend double that records exactly one typed request."""

    value: object
    calls: list[tuple[StructuredGenerationRequest, type[BaseModel]]]

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Return the configured value and record the response model."""
        self.calls.append((request, response_model))
        if isinstance(self.value, BaseException):
            raise self.value
        return StructuredGenerationResult(
            value=self.value,
            metrics=ProviderMetrics(input_tokens=1, output_tokens=2, total_tokens=3),
        )

    async def generate_program(self, request: object) -> object:
        """Fail because the typed worker must not use plain programs."""
        raise AssertionError("CM-56 typed worker unexpectedly requested a program.")


def _task(*, capabilities: tuple[str, ...] | None = None) -> SectionTask:
    """Build one generic reconstruction task."""
    return SectionTask(
        goal="Create a Gamma Ray section from /secret/well/main.las.",
        capability_ids=capabilities or ("section.log_plot", "track.normal", "binding.curve"),
        source_hints=("main",),
        requirements=("Use the GR channel.",),
    )


def _context() -> ResolvedSectionContext:
    """Build a new-section context with one scalar channel."""
    return ResolvedSectionContext(
        task_index=0,
        sources=(
            SourceContext(
                candidate_id="source-1",
                canonical_path="/secret/well/main.las",
                source_format="las",
                channels=(
                    ChannelContext(
                        mnemonic="GR",
                        kind="scalar",
                        description="/secret/well/main.las gamma ray",
                        aliases=("gamma ray", "/secret/alias"),
                    ),
                ),
            ),
        ),
    )


def _draft() -> SectionSemanticDraft:
    """Build one provider-valid typed draft."""
    return SectionSemanticDraft(
        title="Gamma Ray",
        source_candidate="source-1",
        tracks=(
            NormalTrackSemanticDraft(
                semantic_id="gamma-track",
                kind="normal",
                title="Gamma Ray",
                bindings=(
                    CurveBindingSemanticDraft(
                        semantic_id="gamma",
                        channel="GR",
                    ),
                ),
            ),
        ),
    )


def _document() -> AuthoringDocumentSpec:
    """Build a valid seed document for host identity allocation."""
    return AuthoringDocumentSpec(
        name="cm56",
        sections=[
            {
                "id": "existing",
                "title": "Existing",
                "tracks": [
                    {
                        "id": "existing-track",
                        "title": "Existing",
                        "kind": "normal",
                        "width_mm": 20,
                    }
                ],
            }
        ],
    )


def test_response_schema_digest_is_frozen_and_track_tags_are_required() -> None:
    """CM-55's static response schema is the CM-56 input/output contract."""
    assert response_schema_sha256() == RESPONSE_SCHEMA_SHA256
    schema = _draft().model_json_schema()
    branches = schema["$defs"]
    assert all(
        "kind" in branch.get("required", ())
        for branch in branches.values()
        if "Track" in branch.get("title", "")
    )


def test_provider_input_is_deterministic_and_path_free() -> None:
    """Only redacted task/context semantics cross the provider boundary."""
    value = build_typed_section_input(
        _task(),
        section_context=_context(),
        registry=create_builtin_registry(),
    )
    first = serialize_typed_section_input(value)
    second = serialize_typed_section_input(value)
    assert first == second
    assert "/secret/" not in first
    assert "canonical_path" not in first
    assert "main.las" not in first
    assert "[redacted-path]" in first
    assert json.loads(first)["sources"][0]["channels"][0]["recognition_aliases"] == [
        "gamma ray",
        "[redacted-path]",
    ]


def test_compile_uses_one_structured_call_and_returns_host_intent() -> None:
    """The shadow worker performs one call and then deterministic host work."""
    backend = _Backend(value=_draft(), calls=[])
    result = asyncio.run(
        TypedSectionCompiler(
            backend=backend,
            registry=create_builtin_registry(),
        ).compile(
            task=_task(),
            section_context=_context(),
            document=_document(),
            section_id_hint="cm56-section",
            timeout_seconds=30,
        )
    )
    assert len(backend.calls) == 1
    request, response_model = backend.calls[0]
    assert response_model is SectionSemanticDraft
    assert request.user_prompt == serialize_typed_section_input(
        build_typed_section_input(
            _task(),
            section_context=_context(),
            registry=create_builtin_registry(),
        )
    )
    assert result.draft == _draft()
    assert result.intent_fragment.sections[0].data_source.source_path == "/secret/well/main.las"
    assert result.response_schema_sha256 == RESPONSE_SCHEMA_SHA256
    assert result.system_prompt_sha256
    assert TYPED_SECTION_SYSTEM_PROMPT


def test_revision_is_rejected_before_provider_call() -> None:
    """The initial typed worker is reconstruct-only and host-preflighted."""
    backend = _Backend(value=_draft(), calls=[])
    context = _context().model_copy(update={"section_id": "existing"})
    with pytest.raises(TypedSectionWorkerError) as error:
        asyncio.run(
            TypedSectionCompiler(
                backend=backend,
                registry=create_builtin_registry(),
            ).compile(
                task=_task(),
                section_context=context,
                document=_document(),
                section_id_hint="cm56-section",
                timeout_seconds=30,
                mode="revise",
            )
        )
    assert error.value.code is TypedSectionWorkerErrorCode.REVISION_UNSUPPORTED
    assert not backend.calls


def test_unsupported_capability_is_rejected_before_provider_call() -> None:
    """Representability gaps do not become provider or semantic failures."""
    backend = _Backend(value=_draft(), calls=[])
    with pytest.raises(TypedSectionRepresentabilityError):
        asyncio.run(
            TypedSectionCompiler(
                backend=backend,
                registry=create_builtin_registry(),
            ).compile(
                task=_task(capabilities=("section.log_plot", "fill.curve")),
                section_context=_context(),
                document=_document(),
                section_id_hint="cm56-section",
                timeout_seconds=30,
            )
        )
    assert not backend.calls


def test_provider_error_is_not_retried_or_normalized() -> None:
    """Provider-neutral failures remain terminal in the shadow slice."""
    error = ProviderRequestError("transport", "provider unavailable")
    backend = _Backend(value=error, calls=[])
    with pytest.raises(ProviderRequestError):
        asyncio.run(
            TypedSectionCompiler(
                backend=backend,
                registry=create_builtin_registry(),
            ).compile(
                task=_task(),
                section_context=_context(),
                document=_document(),
                section_id_hint="cm56-section",
                timeout_seconds=30,
            )
        )
    assert len(backend.calls) == 1
