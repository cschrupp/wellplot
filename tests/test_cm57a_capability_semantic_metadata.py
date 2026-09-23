"""CM-57A tests for host-side capability semantic metadata authority."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError, asdict

import pytest
from pydantic import BaseModel

from wellplot.capabilities import (
    CapabilityRegistry,
    CapabilitySemanticMapping,
    CapabilitySemanticMetadata,
    CapabilitySpec,
    create_builtin_registry,
)
from wellplot.model.intent import AuthoringDocumentIntent


class _Artifact(BaseModel):
    """Synthetic artifact for declaration-only capability tests."""

    value: str = "value"


def _compiler(_: BaseModel) -> AuthoringDocumentIntent:
    return AuthoringDocumentIntent.model_validate({})


def _mapping(
    *,
    concept: str = "profile",
    patterns: tuple[str, ...] = ("raster",),
    targets: tuple[tuple[str, str], ...] = (("binding.profile", "generic"),),
) -> CapabilitySemanticMapping:
    return CapabilitySemanticMapping(
        concept=concept,
        language_patterns=patterns,
        targets=targets,
    )


def _metadata(*mappings: CapabilitySemanticMapping) -> CapabilitySemanticMetadata:
    return CapabilitySemanticMetadata(purpose="Host semantic guidance.", mappings=mappings)


def test_public_metadata_types_are_immutable() -> None:
    """Metadata declarations expose no mutable semantic containers."""
    mapping = _mapping()
    metadata = _metadata(mapping)

    with pytest.raises(FrozenInstanceError):
        metadata.purpose = "changed"
    with pytest.raises(FrozenInstanceError):
        mapping.concept = "changed"
    with pytest.raises(FrozenInstanceError):
        metadata.mappings += (mapping,)

    for factory in (
        lambda: CapabilitySemanticMapping(
            concept="x", language_patterns=["x"], targets=(("binding.x", "x"),)
        ),
        lambda: CapabilitySemanticMapping(
            concept="x", language_patterns=("x",), targets=[["binding.x", "x"]]
        ),
        lambda: CapabilitySemanticMetadata(purpose="x", mappings=[mapping]),
        lambda: CapabilitySemanticMetadata(purpose="x", distinctions=["x"]),
    ):
        with pytest.raises(TypeError):
            factory()


@pytest.mark.parametrize(
    "factory",
    (
        lambda: CapabilitySemanticMetadata(purpose=" "),
        lambda: _mapping(concept=" "),
        lambda: _mapping(patterns=(" ",)),
        lambda: _mapping(targets=((" ", "cue"),)),
        lambda: _mapping(targets=(("binding.profile", " "),)),
        lambda: CapabilitySemanticMetadata(purpose="x", distinctions=(" ",)),
    ),
)
def test_blank_metadata_values_are_rejected(factory: Callable[[], object]) -> None:
    """Blank declaration text cannot become provider-facing guidance later."""
    with pytest.raises(ValueError):
        factory()


@pytest.mark.parametrize(
    "target_path",
    (
        "binding..profile",
        ".binding.profile",
        "binding.profile.",
        "binding[0].profile",
        "binding/profile",
    ),
)
def test_target_paths_require_bounded_dotted_identifiers(target_path: str) -> None:
    """Metadata validates generic paths without coupling to typed-worker models."""
    with pytest.raises(ValueError, match="target path"):
        _mapping(targets=((target_path, "cue"),))

    assert (
        _mapping(targets=(("binding.sample_axis.tick_count", "cue"),)).targets[0][0]
        == "binding.sample_axis.tick_count"
    )


def test_duplicate_concepts_patterns_and_targets_are_rejected() -> None:
    """Ambiguous declarations fail while distinct mappings may share a target path."""
    with pytest.raises(ValueError, match="concept"):
        _metadata(_mapping(), _mapping(concept=" PROFILE ", patterns=("other",)))
    with pytest.raises(ValueError, match="language pattern"):
        _metadata(_mapping(), _mapping(concept="other", patterns=(" RASTER ",)))
    with pytest.raises(ValueError, match="target path"):
        _mapping(
            targets=(
                ("binding.profile", "generic"),
                ("binding.profile", "waveform"),
            )
        )

    metadata = _metadata(
        _mapping(),
        _mapping(
            concept="waveform profile",
            patterns=("waveform raster",),
            targets=(("binding.profile", "waveform"),),
        ),
    )
    assert len(metadata.mappings) == 2


def test_metadata_count_bounds_are_deterministic() -> None:
    """The declaration surface remains bounded without imposing semantic limits."""
    mappings = tuple(
        _mapping(
            concept=f"concept-{index}",
            patterns=(f"pattern-{index}",),
            targets=(("binding.profile", f"value-{index}"),),
        )
        for index in range(8)
    )
    assert len(_metadata(*mappings).mappings) == 8
    with pytest.raises(ValueError, match="at most 8 mappings"):
        _metadata(
            *mappings,
            _mapping(
                concept="concept-8",
                patterns=("pattern-8",),
                targets=(("binding.profile", "value-8"),),
            ),
        )

    patterns = tuple(f"pattern-{index}" for index in range(8))
    assert len(_mapping(patterns=patterns).language_patterns) == 8
    with pytest.raises(ValueError, match="at most 8 language patterns"):
        _mapping(patterns=patterns + ("pattern-8",))

    assert (
        len(CapabilitySemanticMetadata(purpose="x", distinctions=("a", "b", "c", "d")).distinctions)
        == 4
    )
    with pytest.raises(ValueError, match="at most 4 distinctions"):
        CapabilitySemanticMetadata(purpose="x", distinctions=("a", "b", "c", "d", "e"))


def test_capability_spec_remains_backward_compatible_without_metadata() -> None:
    """Capability authors that omit metadata retain the existing contract."""
    spec = CapabilitySpec(
        capability_id="track.synthetic",
        category="track",
        description="Synthetic track.",
        artifact_model=_Artifact,
        compiler=_compiler,
    )

    assert spec.semantic_metadata is None
    assert spec.planning_descriptor()["id"] == "track.synthetic"


def test_builtin_raster_is_the_only_initial_metadata_owner() -> None:
    """The first production metadata declaration belongs only to binding.raster."""
    capabilities = create_builtin_registry()
    owners = tuple(
        spec.capability_id for spec in capabilities if spec.semantic_metadata is not None
    )

    assert owners == ("binding.raster",)
    raster = capabilities.get("binding.raster")
    assert raster.semantic_metadata is capabilities.get("raster").semantic_metadata


def test_builtin_raster_metadata_has_exact_generic_targets() -> None:
    """Raster metadata contains only the approved profile and sample-axis targets."""
    metadata = create_builtin_registry().get("binding.raster").semantic_metadata
    assert metadata is not None
    assert len(metadata.mappings) == 7
    assert len(metadata.distinctions) == 3

    target_paths = [path for mapping in metadata.mappings for path, _ in mapping.targets]
    assert set(target_paths) == {
        "binding.profile",
        "binding.sample_axis.unit",
        "binding.sample_axis.source_origin",
        "binding.sample_axis.source_step",
        "binding.sample_axis.tick_count",
    }
    assert all(not path.startswith("binding.scale") for path in target_paths)
    assert not any(path.startswith("track.x_scale.") for path in target_paths)

    serialized = json.dumps(asdict(metadata), sort_keys=True).casefold()
    for forbidden in (
        "cm-56",
        "r8r",
        "s1",
        "reverse_scale",
        "scalar_linear",
        "gate-a",
        "0 to 150",
        "200 to 0",
        "0 to 200",
        "200 to 1200",
        "-25 to 75",
        "10 to 90",
    ):
        assert forbidden not in serialized

    assert any("track.x_scale" in distinction for distinction in metadata.distinctions)
    assert any("sample_axis" in distinction for distinction in metadata.distinctions)


def test_existing_descriptor_surfaces_do_not_expose_semantic_metadata() -> None:
    """CM-57A keeps planner and existing worker descriptors byte-compatible in shape."""
    spec = create_builtin_registry().get("binding.raster")
    planning = spec.planning_descriptor()
    worker = spec.worker_descriptor()
    code_mode = spec.code_mode_worker_descriptor()

    assert set(planning) == {
        "id",
        "category",
        "description",
        "aliases",
        "allowed_parents",
        "source_kinds",
        "planning_hints",
        "schema_version",
    }
    assert set(worker) == set(planning) | {"artifact_schema"}
    assert set(code_mode) == {
        "id",
        "category",
        "description",
        "aliases",
        "allowed_parents",
        "source_kinds",
        "worker_hints",
        "examples",
        "arguments_schema",
    }
    for descriptor in (planning, worker, code_mode):
        assert "semantic_metadata" not in descriptor
        assert "semantic_contracts" not in descriptor


def test_registry_keeps_existing_capability_object_as_metadata_authority() -> None:
    """Registry lookup exposes the declaration without a second metadata catalog."""
    registry = CapabilityRegistry(create_builtin_registry())
    canonical = registry.get("binding.raster")
    alias = registry.get("raster")

    assert canonical is alias
    assert canonical.semantic_metadata is not None
