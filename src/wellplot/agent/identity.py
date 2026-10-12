"""Deterministic identity allocation owned by the authoring engine."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence

_NON_SLUG_CHARACTERS = re.compile(r"[^A-Za-z0-9]+")


class IdentityError(ValueError):
    """Raised when an adopted or allocated identity violates its contract."""


def slugify_id_hint(value: str | None, *, fallback: str) -> str:
    """Create a stable advisory identity component without changing adopted IDs."""
    if value is None:
        return fallback
    if not isinstance(value, str):
        raise IdentityError("Identity hints must be strings when provided.")
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = _NON_SLUG_CHARACTERS.sub("-", ascii_text).strip("-")
    return slug or fallback


class IdAllocator:
    """Allocate collision-safe identities from explicit host reservations."""

    def __init__(
        self,
        *,
        section_ids: Sequence[str] = (),
        track_ids_by_section: Mapping[str, Sequence[str]] | None = None,
        binding_ids: Sequence[str] = (),
        leaf_ids: Sequence[str] = (),
    ) -> None:
        """Seed the allocator with identities occupied by the canonical document."""
        self._section_ids: set[str] = set()
        self._track_ids_by_section: dict[str, set[str]] = {}
        self._binding_ids: set[str] = set()
        self._leaf_ids: set[str] = set()
        for section_id in section_ids:
            self.adopt_section(section_id)
        if track_ids_by_section is not None:
            for section_id, track_ids in track_ids_by_section.items():
                for track_id in track_ids:
                    self.adopt_track(section_id, track_id)
        for binding_id in binding_ids:
            self.adopt_binding(binding_id)
        for leaf_id in leaf_ids:
            self.adopt_leaf(leaf_id)

    def allocate_section(self, id_hint: str | None = None) -> str:
        """Allocate a document-scoped section identity."""
        section_id = self._reserve_next(
            self._section_ids, slugify_id_hint(id_hint, fallback="section")
        )
        self._track_ids_by_section.setdefault(section_id, set())
        return section_id

    def adopt_section(self, section_id: str) -> str:
        """Reserve one existing section identity."""
        canonical_id = _canonical_id(section_id, "section id")
        self._section_ids.add(canonical_id)
        self._track_ids_by_section.setdefault(canonical_id, set())
        return canonical_id

    def allocate_track(self, section_id: str, id_hint: str | None = None) -> str:
        """Allocate one section-scoped track identity."""
        canonical_section_id = self._require_section(section_id)
        return self._reserve_next(
            self._track_ids_by_section[canonical_section_id],
            slugify_id_hint(id_hint, fallback="track"),
        )

    def adopt_track(self, section_id: str, track_id: str) -> str:
        """Reserve one existing local track identity."""
        canonical_section_id = self._require_section(section_id)
        canonical_track_id = _canonical_id(track_id, "track id")
        self._track_ids_by_section[canonical_section_id].add(canonical_track_id)
        return canonical_track_id

    def allocate_binding(
        self,
        section_id: str,
        track_id: str,
        *,
        channel: str | None = None,
        id_hint: str | None = None,
    ) -> str:
        """Allocate one globally unique binding identity."""
        canonical_section_id, canonical_track_id = self._require_track(section_id, track_id)
        seed = (
            _channel_identity_seed(channel)
            if channel is not None
            else slugify_id_hint(id_hint, fallback="binding")
        )
        base = ".".join(
            (
                slugify_id_hint(canonical_section_id, fallback="section"),
                slugify_id_hint(canonical_track_id, fallback="track"),
                seed,
            )
        )
        return self._reserve_next(self._binding_ids, base)

    def adopt_binding(self, binding_id: str) -> str:
        """Reserve one exact existing binding identity."""
        canonical_id = _canonical_id(binding_id, "binding id")
        self._binding_ids.add(canonical_id)
        return canonical_id

    def allocate_leaf(
        self,
        section_id: str,
        track_id: str,
        *,
        leaf_kind: str,
        id_hint: str | None = None,
    ) -> str:
        """Allocate one generic track-leaf identity."""
        canonical_section_id, canonical_track_id = self._require_track(section_id, track_id)
        base = ".".join(
            (
                slugify_id_hint(canonical_section_id, fallback="section"),
                slugify_id_hint(canonical_track_id, fallback="track"),
                slugify_id_hint(leaf_kind, fallback="leaf"),
                slugify_id_hint(id_hint, fallback="item"),
            )
        )
        return self._reserve_next(self._leaf_ids, base)

    def adopt_leaf(self, leaf_id: str) -> str:
        """Reserve one exact existing leaf identity."""
        canonical_id = _canonical_id(leaf_id, "leaf id")
        self._leaf_ids.add(canonical_id)
        return canonical_id

    def _require_section(self, section_id: str) -> str:
        canonical_id = _canonical_id(section_id, "section id")
        if canonical_id not in self._section_ids:
            raise IdentityError(f"Section identity '{canonical_id}' has not been reserved.")
        return canonical_id

    def _require_track(self, section_id: str, track_id: str) -> tuple[str, str]:
        canonical_section_id = self._require_section(section_id)
        canonical_track_id = _canonical_id(track_id, "track id")
        if canonical_track_id not in self._track_ids_by_section[canonical_section_id]:
            raise IdentityError(
                f"Track identity '{canonical_track_id}' has not been reserved in "
                f"section '{canonical_section_id}'."
            )
        return canonical_section_id, canonical_track_id

    @staticmethod
    def _reserve_next(occupied: set[str], base: str) -> str:
        candidate = base
        suffix = 2
        while candidate in occupied:
            candidate = f"{base}.{suffix}"
            suffix += 1
        occupied.add(candidate)
        return candidate


def _canonical_id(value: object, label: str) -> str:
    """Validate one exact adopted identity."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise IdentityError(f"{label.capitalize()} must be a non-empty trimmed string.")
    return value


def _channel_identity_seed(channel: object) -> str:
    """Create a stable identity seed from an exact channel mnemonic."""
    if not isinstance(channel, str):
        raise IdentityError("Binding channel identity seeds must be strings.")
    normalized = unicodedata.normalize("NFKD", channel)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    seed = _NON_SLUG_CHARACTERS.sub("-", ascii_text).strip("-")
    return seed or "binding"


__all__ = ["IdAllocator", "IdentityError", "slugify_id_hint"]
