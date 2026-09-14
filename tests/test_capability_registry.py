"""Capability registry behavior and topology-independence tests."""

###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

from pydantic import BaseModel

from wellplot.capabilities import CapabilityRegistry, CapabilitySpec, create_builtin_registry
from wellplot.model.intent import AuthoringDocumentIntent


class _FutureImageTrackIntent(BaseModel):
    track_id: str
    source_channel: str


class _CodeModeArguments(BaseModel):
    """Synthetic v2 argument contract for the additive capability test."""

    label: str


def _leaf_compiler(_: BaseModel) -> AuthoringDocumentIntent:
    raise RuntimeError("Leaf-only test capability")


def _synthetic_handler(arguments: BaseModel) -> object:
    """Synthetic host handler retained outside the serialized descriptor."""
    return arguments


def test_builtin_registry_exposes_compact_planning_catalog() -> None:
    """The planner sees compact descriptors instead of every full artifact schema."""
    registry = create_builtin_registry()
    catalog = registry.planning_catalog()

    ids = {item["id"] for item in catalog}
    assert "section.log_plot" in ids
    assert "track.normal" in ids
    assert "binding.curve" in ids
    assert all("artifact_schema" not in item for item in catalog)


def test_new_capability_registers_without_graph_changes() -> None:
    """A new capability is discoverable without a domain-specific graph branch."""
    registry = create_builtin_registry()
    registry.register(
        CapabilitySpec(
            capability_id="track.image",
            category="track",
            description="Future depth-indexed image track.",
            artifact_model=_FutureImageTrackIntent,
            compiler=_leaf_compiler,
            aliases=("image track", "borehole image"),
            allowed_parents=("section.log_plot",),
        )
    )

    assert registry.get("image track").capability_id == "track.image"
    worker_catalog = registry.worker_catalog(["track.image"])
    assert worker_catalog[0]["id"] == "track.image"
    assert "artifact_schema" in worker_catalog[0]


def test_duplicate_alias_is_rejected() -> None:
    """Aliases remain globally unambiguous across capabilities."""
    registry = CapabilityRegistry()
    registry.register(
        CapabilitySpec(
            capability_id="track.first",
            category="track",
            description="First",
            artifact_model=_FutureImageTrackIntent,
            compiler=_leaf_compiler,
            aliases=("shared",),
        )
    )

    try:
        registry.register(
            CapabilitySpec(
                capability_id="track.second",
                category="track",
                description="Second",
                artifact_model=_FutureImageTrackIntent,
                compiler=_leaf_compiler,
                aliases=("shared",),
            )
        )
    except ValueError as exc:
        assert "aliases already registered" in str(exc)
    else:
        raise AssertionError("Expected duplicate alias registration to fail.")


def test_v1_capability_surface_remains_unchanged_without_v2_fields() -> None:
    """Existing declarations keep their v1 descriptors and remain v1-only."""
    spec = CapabilitySpec(
        capability_id="track.image",
        category="track",
        description="Future depth-indexed image track.",
        artifact_model=_FutureImageTrackIntent,
        compiler=_leaf_compiler,
        aliases=("image track",),
    )

    assert spec.supports_v2 is False
    assert spec.planning_descriptor() == {
        "id": "track.image",
        "category": "track",
        "description": "Future depth-indexed image track.",
        "aliases": ["image track"],
        "allowed_parents": [],
        "source_kinds": [],
        "planning_hints": [],
        "schema_version": "1",
    }
    try:
        spec.code_mode_worker_descriptor()
    except ValueError as exc:
        assert "does not declare the v2 contract" in str(exc)
    else:
        raise AssertionError("Expected v1-only capability to reject v2 descriptor access.")


def test_one_capability_can_expose_independent_v1_and_v2_contracts() -> None:
    """The synthetic plugin retains v1 compilation while declaring v2 metadata."""
    spec = CapabilitySpec(
        capability_id="track.synthetic",
        category="track",
        description="Synthetic dual-mode track.",
        artifact_model=_FutureImageTrackIntent,
        compiler=_leaf_compiler,
        arguments_model=_CodeModeArguments,
        handler=_synthetic_handler,
        worker_hints=("Use the explicit label.",),
        examples=("wp.synthetic(label='demo')",),
    )

    descriptor = spec.code_mode_worker_descriptor()
    assert spec.supports_v2 is True
    assert set(descriptor) == {
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
    assert descriptor["worker_hints"] == ["Use the explicit label."]
    assert descriptor["examples"] == ["wp.synthetic(label='demo')"]
    assert "handler" not in descriptor
    assert "compiler" not in descriptor
    assert "artifact_schema" not in descriptor
    assert descriptor == spec.code_mode_worker_descriptor()
    assert spec.compiler is _leaf_compiler


def test_v2_pair_is_required_and_aliases_are_strict() -> None:
    """Partial v2 declarations and malformed aliases fail immediately."""
    base = {
        "capability_id": "track.synthetic",
        "category": "track",
        "description": "Synthetic",
        "artifact_model": _FutureImageTrackIntent,
        "compiler": _leaf_compiler,
    }
    for partial in (
        {"arguments_model": _CodeModeArguments},
        {"handler": _synthetic_handler},
    ):
        try:
            CapabilitySpec(**base, **partial)
        except ValueError as exc:
            assert "arguments_model and handler together" in str(exc)
        else:
            raise AssertionError("Expected incomplete v2 pair to fail construction.")

    for aliases in (("",), ("track.synthetic",), ("same", "SAME")):
        try:
            CapabilitySpec(**base, aliases=aliases)
        except ValueError:
            pass
        else:
            raise AssertionError("Expected malformed or redundant aliases to fail.")


def test_v2_descriptor_is_json_stable_and_contains_no_callable() -> None:
    """Descriptor serialization is deterministic and host handlers stay private."""
    spec = CapabilitySpec(
        capability_id="track.synthetic",
        category="track",
        description="Synthetic dual-mode track.",
        artifact_model=_FutureImageTrackIntent,
        compiler=_leaf_compiler,
        arguments_model=_CodeModeArguments,
        handler=_synthetic_handler,
    )
    first = spec.code_mode_worker_descriptor()
    second = spec.code_mode_worker_descriptor()

    import json

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    def contains_callable(value: object) -> bool:
        if callable(value):
            return True
        if isinstance(value, dict):
            return any(contains_callable(item) for item in value.values())
        if isinstance(value, (list, tuple)):
            return any(contains_callable(item) for item in value)
        return False

    assert contains_callable(first) is False
