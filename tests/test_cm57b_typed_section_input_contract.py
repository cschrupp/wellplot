"""CM-57B deterministic tests for the production typed-worker input boundary."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, replace

import pytest
from pydantic import BaseModel, ValidationError

from wellplot.agent.code_mode.enrichment import (
    ChannelContext,
    ResolvedSectionContext,
    SourceContext,
)
from wellplot.agent.code_mode.planner import SectionTask
from wellplot.agent.code_mode.section_semantics import (
    ArrayTrackSemanticDraft,
    RasterBindingSemanticDraft,
    SectionSemanticDraft,
    SemanticScale,
)
from wellplot.agent.code_mode.typed_section_worker import (
    RESPONSE_SCHEMA_SHA256,
    TYPED_SECTION_SEMANTIC_TARGET_PATHS,
    TYPED_SECTION_SYSTEM_PROMPT,
    TypedSectionCompiler,
    TypedSectionWorkerError,
    TypedSectionWorkerErrorCode,
    build_typed_section_input,
    build_typed_section_provider_input,
    build_typed_section_system_prompt,
    response_schema_sha256,
    serialize_typed_section_input,
    serialize_typed_section_provider_input,
)
from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.capabilities import CapabilityRegistry, create_builtin_registry
from wellplot.capabilities.base import CapabilitySemanticMapping, CapabilitySemanticMetadata
from wellplot.model.authoring import AuthoringDocumentSpec

REQUEST = "Create a VDL raster from /secret/well/main.dlis and C:\\secret\\main.dlis"


@dataclass
class _Backend(ModelBackendProtocol):
    """Backend double that records provider calls without making network requests."""

    value: object
    calls: list[tuple[StructuredGenerationRequest, type[BaseModel]]]

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Return the configured draft and retain the request for assertions."""
        self.calls.append((request, response_model))
        return StructuredGenerationResult(
            value=self.value,
            metrics=ProviderMetrics(input_tokens=1, output_tokens=2, total_tokens=3),
        )

    async def generate_program(self, request: object) -> object:
        """Reject the legacy program path in this typed-worker test."""
        raise AssertionError("CM-57B unexpectedly requested a generated program.")


def _registry() -> CapabilityRegistry:
    """Return the built-in registry for one isolated test."""
    return create_builtin_registry()


def _task(*, raster: bool = False, capabilities: tuple[str, ...] | None = None) -> SectionTask:
    """Build a task with either the scalar or raster typed capability set."""
    selected = capabilities or (
        (
            "section.log_plot",
            "track.array",
            "binding.raster",
        )
        if raster
        else (
            "section.log_plot",
            "track.normal",
            "binding.curve",
        )
    )
    return SectionTask(
        goal="Create the requested typed section.",
        capability_ids=selected,
        source_hints=("main",),
        requirements=("Preserve the explicitly requested semantics.",),
    )


def _context(*, raster: bool = False) -> ResolvedSectionContext:
    """Build a bounded context containing scalar and optional array channels."""
    channels = [
        ChannelContext(
            mnemonic="GR",
            kind="scalar",
            description="Gamma ray",
            aliases=("gamma ray", "/secret/alias"),
        )
    ]
    if raster:
        channels.append(
            ChannelContext(
                mnemonic="VDL",
                kind="array",
                description="Variable density log",
                aliases=("waveform",),
            )
        )
    return ResolvedSectionContext(
        task_index=0,
        sources=(
            SourceContext(
                candidate_id="source-1",
                canonical_path="/secret/well/main.dlis",
                source_format="dlis",
                channels=tuple(channels),
            ),
        ),
    )


def _document() -> AuthoringDocumentSpec:
    """Build a minimal valid host document for compiler tests."""
    return AuthoringDocumentSpec(
        name="cm57b",
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


def _raster_draft() -> SectionSemanticDraft:
    """Build one valid draft for the raster compiler path."""
    return SectionSemanticDraft(
        title="VDL",
        source_candidate="source-1",
        tracks=(
            ArrayTrackSemanticDraft(
                semantic_id="vdl-track",
                kind="array",
                title="VDL",
                x_scale=SemanticScale(minimum=0, maximum=1200),
                bindings=(
                    RasterBindingSemanticDraft(
                        semantic_id="vdl",
                        channel="VDL",
                        profile="vdl",
                    ),
                ),
            ),
        ),
    )


def _registry_with_raster_metadata(metadata: CapabilitySemanticMetadata) -> CapabilityRegistry:
    """Replace only the built-in raster metadata in a fresh test registry."""
    specs = tuple(
        replace(spec, semantic_metadata=metadata)
        if spec.capability_id == "binding.raster"
        else spec
        for spec in _registry()
    )
    return CapabilityRegistry(specs)


def _metadata(
    *, target_path: str, value_cue: str = "use the requested value"
) -> CapabilitySemanticMetadata:
    """Build metadata with one controlled target for boundary tests."""
    return CapabilitySemanticMetadata(
        purpose="Controlled CM-57B test metadata.",
        mappings=(
            CapabilitySemanticMapping(
                concept="controlled concept",
                language_patterns=("controlled",),
                targets=((target_path, value_cue),),
            ),
        ),
    )


def _compile(
    backend: _Backend,
    *,
    task: SectionTask,
    context: ResolvedSectionContext,
    registry: CapabilityRegistry,
    authoritative_request: str = REQUEST,
) -> None:
    """Run the inactive compiler through its provider-input preflight."""
    asyncio.run(
        TypedSectionCompiler(backend=backend, registry=registry).compile(
            task=task,
            section_context=context,
            document=_document(),
            section_id_hint="cm57b-section",
            authoritative_request=authoritative_request,
            timeout_seconds=30,
        )
    )


def test_historical_base_input_remains_exactly_three_fields() -> None:
    """Closed CM-56/CM-57IB diagnostics retain their original payload shape."""
    value = build_typed_section_input(
        _task(),
        section_context=_context(),
        registry=_registry(),
    )
    assert set(json.loads(serialize_typed_section_input(value))) == {
        "section_task",
        "capabilities",
        "sources",
    }


def test_scalar_provider_input_is_base_plus_redacted_request() -> None:
    """A scalar task adds only the authoritative request factor."""
    registry = _registry()
    base = json.loads(
        serialize_typed_section_input(
            build_typed_section_input(_task(), section_context=_context(), registry=registry)
        )
    )
    provider = json.loads(
        serialize_typed_section_provider_input(
            build_typed_section_provider_input(
                _task(),
                authoritative_request=REQUEST,
                section_context=_context(),
                registry=registry,
            )
        )
    )
    assert provider.pop("authoritative_request") == (
        "Create a VDL raster from [redacted-path] and [redacted-path]"
    )
    assert "semantic_contracts" not in provider
    assert provider == base


def test_raster_provider_input_projects_metadata_and_redacts_paths() -> None:
    """Raster input carries one production metadata contract without host paths."""
    provider = build_typed_section_provider_input(
        _task(raster=True),
        authoritative_request=REQUEST,
        section_context=_context(raster=True),
        registry=_registry(),
    )
    serialized = serialize_typed_section_provider_input(provider)
    payload = json.loads(serialized)
    assert payload["authoritative_request"] == (
        "Create a VDL raster from [redacted-path] and [redacted-path]"
    )
    assert [contract["capability_id"] for contract in payload["semantic_contracts"]] == [
        "binding.raster"
    ]
    assert "/secret/" not in serialized
    assert "C:\\secret\\" not in serialized
    assert "canonical_path" not in serialized
    targets = {
        target["path"]
        for contract in payload["semantic_contracts"]
        for mapping in contract["mappings"]
        for target in mapping["targets"]
    }
    assert targets == set(TYPED_SECTION_SEMANTIC_TARGET_PATHS)
    assert all(not target.startswith("binding.scale") for target in targets)
    assert all(not target.startswith("track.x_scale") for target in targets)


def test_raster_metadata_projection_matches_frozen_contract_digest() -> None:
    """The CM-57A raster projection is consumed without reinterpretation."""
    provider = build_typed_section_provider_input(
        _task(raster=True),
        authoritative_request=REQUEST,
        section_context=_context(raster=True),
        registry=_registry(),
    )
    projection = json.dumps(
        [contract.model_dump(mode="json") for contract in provider.semantic_contracts or ()],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    assert hashlib.sha256(projection.encode("utf-8")).hexdigest() == (
        "67aa2d6f579343e60f9261eb654fd62bde21605b1c8c68f080b5b74ff01c3f46"
    )


def test_metadata_selection_follows_task_order_and_deduplicates() -> None:
    """Metadata follows canonical task order and appears once per capability."""
    synthetic = _metadata(target_path="binding.profile", value_cue="controlled profile")
    specs = tuple(
        replace(spec, semantic_metadata=synthetic) if spec.capability_id == "track.array" else spec
        for spec in _registry()
    )
    registry = CapabilityRegistry(specs)
    provider = build_typed_section_provider_input(
        _task(
            raster=True,
            capabilities=(
                "track.array",
                "binding.raster",
                "track.array",
            ),
        ),
        authoritative_request=REQUEST,
        section_context=_context(raster=True),
        registry=registry,
    )
    assert [contract.capability_id for contract in provider.semantic_contracts or ()] == [
        "track.array",
        "binding.raster",
    ]


def test_unsupported_metadata_target_fails_before_provider_call() -> None:
    """The typed worker rejects semantics outside its current vocabulary."""
    backend = _Backend(value=_raster_draft(), calls=[])
    registry = _registry_with_raster_metadata(_metadata(target_path="binding.scale.minimum"))
    with pytest.raises(TypedSectionWorkerError) as error:
        _compile(
            backend,
            task=_task(raster=True),
            context=_context(raster=True),
            registry=registry,
        )
    assert error.value.code is TypedSectionWorkerErrorCode.INPUT_CONTRACT_INVALID
    assert not backend.calls


def test_oversized_metadata_fails_before_provider_call() -> None:
    """The provider metadata projection is bounded without truncation."""
    backend = _Backend(value=_raster_draft(), calls=[])
    registry = _registry_with_raster_metadata(
        _metadata(target_path="binding.profile", value_cue="x" * 9000)
    )
    with pytest.raises(TypedSectionWorkerError) as error:
        _compile(
            backend,
            task=_task(raster=True),
            context=_context(raster=True),
            registry=registry,
        )
    assert error.value.code is TypedSectionWorkerErrorCode.INPUT_CONTRACT_INVALID
    assert not backend.calls


def test_blank_authoritative_request_fails_before_provider_call() -> None:
    """The provider boundary requires the original request to be meaningful."""
    backend = _Backend(value=_raster_draft(), calls=[])
    with pytest.raises(TypedSectionWorkerError) as error:
        _compile(
            backend,
            task=_task(),
            context=_context(),
            registry=_registry(),
            authoritative_request="   ",
        )
    assert error.value.code is TypedSectionWorkerErrorCode.INPUT_CONTRACT_INVALID
    assert not backend.calls


def test_prompt_hashes_match_frozen_production_factors() -> None:
    """Prompt composition remains exactly comparable with CM-57IB."""
    assert hashlib.sha256(TYPED_SECTION_SYSTEM_PROMPT.encode()).hexdigest() == (
        "19b0e289d2fa8ea362840aa94d90ad43cdea5b2ebdc866363df1ef28a38f2d49"
    )
    assert (
        hashlib.sha256(
            build_typed_section_system_prompt(has_semantic_contracts=False).encode()
        ).hexdigest()
        == "7e519241911d3fbd61d8de4134c71ae69b98646a6b4e5a4ea61ba0a7a0318f69"
    )
    assert (
        hashlib.sha256(
            build_typed_section_system_prompt(has_semantic_contracts=True).encode()
        ).hexdigest()
        == "10ed56fc716165dca783f6d92805b7541f63b4044dcbcd4ac0207191f0771a80"
    )


def test_compiler_sends_request_and_metadata_with_one_structured_call() -> None:
    """Raster compilation uses the complete provider contract exactly once."""
    backend = _Backend(value=_raster_draft(), calls=[])
    _compile(
        backend,
        task=_task(raster=True),
        context=_context(raster=True),
        registry=_registry(),
    )
    assert len(backend.calls) == 1
    request, response_model = backend.calls[0]
    payload = json.loads(request.user_prompt)
    assert response_model is SectionSemanticDraft
    assert payload["authoritative_request"]
    assert payload["semantic_contracts"][0]["capability_id"] == "binding.raster"
    assert hashlib.sha256(request.system_prompt.encode()).hexdigest() == (
        "10ed56fc716165dca783f6d92805b7541f63b4044dcbcd4ac0207191f0771a80"
    )
    assert response_schema_sha256() == RESPONSE_SCHEMA_SHA256


def test_compiler_scalar_request_has_no_semantic_contract_or_extra_prompt() -> None:
    """Non-metadata tasks retain the request-only production factor."""
    backend = _Backend(value=None, calls=[])
    with pytest.raises(ValidationError):
        _compile(
            backend,
            task=_task(),
            context=_context(),
            registry=_registry(),
        )
    assert len(backend.calls) == 1
    request, _ = backend.calls[0]
    payload = json.loads(request.user_prompt)
    assert "authoritative_request" in payload
    assert "semantic_contracts" not in payload
    assert "Capability semantic metadata:" not in request.system_prompt
    assert hashlib.sha256(request.system_prompt.encode()).hexdigest() == (
        "7e519241911d3fbd61d8de4134c71ae69b98646a6b4e5a4ea61ba0a7a0318f69"
    )
