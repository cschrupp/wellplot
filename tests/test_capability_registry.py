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


def _leaf_compiler(_: BaseModel) -> AuthoringDocumentIntent:
    raise RuntimeError("Leaf-only test capability")


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
