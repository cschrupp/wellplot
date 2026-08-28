###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Registry for modular Wellplot authoring capabilities."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from .base import CapabilityCategory, CapabilitySpec


class CapabilityRegistry:
    """Mutable-at-startup registry with deterministic discovery output.

    Registration is expected during application/plugin startup. Planning and
    compilation should treat the registry as read-only afterward.
    """

    def __init__(self, specs: Iterable[CapabilitySpec] = ()) -> None:
        """Initialize an empty registry and register any supplied capabilities."""
        self._specs: dict[str, CapabilitySpec] = {}
        self._aliases: dict[str, str] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: CapabilitySpec) -> None:
        """Register one capability while enforcing global identity and alias uniqueness."""
        capability_id = spec.capability_id.strip()
        if not capability_id:
            raise ValueError("Capability id cannot be empty.")
        if capability_id in self._specs:
            raise ValueError(f"Capability {capability_id!r} is already registered.")

        candidate_aliases = {
            capability_id.casefold(),
            *(alias.casefold() for alias in spec.aliases),
        }
        conflicts = sorted(alias for alias in candidate_aliases if alias in self._aliases)
        if conflicts:
            raise ValueError(
                f"Capability {capability_id!r} uses aliases already registered: {conflicts!r}."
            )

        self._specs[capability_id] = spec
        for alias in candidate_aliases:
            self._aliases[alias] = capability_id

    def register_many(self, specs: Iterable[CapabilitySpec]) -> None:
        """Register several capabilities in the supplied order."""
        for spec in specs:
            self.register(spec)

    def get(self, capability_id_or_alias: str) -> CapabilitySpec:
        """Return one capability resolved from its identifier or alias."""
        key = capability_id_or_alias.strip()
        canonical_id = self._aliases.get(key.casefold(), key)
        try:
            return self._specs[canonical_id]
        except KeyError as exc:
            raise KeyError(f"Unknown Wellplot capability {capability_id_or_alias!r}.") from exc

    def contains(self, capability_id_or_alias: str) -> bool:
        """Return whether an identifier or alias resolves in this registry."""
        try:
            self.get(capability_id_or_alias)
        except KeyError:
            return False
        return True

    def by_category(self, category: CapabilityCategory) -> tuple[CapabilitySpec, ...]:
        """Return deterministic capability descriptors for one semantic category."""
        return tuple(spec for _, spec in sorted(self._specs.items()) if spec.category == category)

    def planning_catalog(self) -> tuple[dict[str, object], ...]:
        """Return the compact, stable catalogue provided to the planner."""
        return tuple(
            self._specs[capability_id].planning_descriptor()
            for capability_id in sorted(self._specs)
        )

    def worker_catalog(self, capability_ids: Iterable[str]) -> tuple[dict[str, object], ...]:
        """Return rich descriptors only for capabilities relevant to one worker."""
        canonical_ids = {self.get(value).capability_id for value in capability_ids}
        return tuple(self._specs[value].worker_descriptor() for value in sorted(canonical_ids))

    def __iter__(self) -> Iterator[CapabilitySpec]:
        """Iterate registered capabilities in deterministic identifier order."""
        for capability_id in sorted(self._specs):
            yield self._specs[capability_id]

    def __len__(self) -> int:
        """Return the number of registered capabilities."""
        return len(self._specs)
