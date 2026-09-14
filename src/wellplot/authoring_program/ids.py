###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
###############################################################################

"""Deterministic reservation-based identities for future Authoring Program SDKs."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence

from .errors import ProgramNameError, ProgramTypeError

_NON_SLUG_CHARACTERS = re.compile(r"[^A-Za-z0-9]+")


def slugify_id_hint(value: str | None, *, fallback: str) -> str:
    """Return a locale-independent advisory identity component.

    The function lowercases ASCII-normalized text, replaces every punctuation
    or whitespace run with one hyphen, and uses the fixed fallback when no
    alphanumeric content survives. It does not alter adopted canonical IDs.
    """
    if value is None:
        return fallback
    if not isinstance(value, str):
        raise ProgramTypeError("Identity hints must be strings when provided.")
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = _NON_SLUG_CHARACTERS.sub("-", ascii_text).strip("-")
    return slug or fallback


class IdAllocator:
    """Allocate canonical identities from explicit reservation sets only."""

    def __init__(
        self,
        *,
        section_ids: Sequence[str] = (),
        track_ids_by_section: Mapping[str, Sequence[str]] | None = None,
        binding_ids: Sequence[str] = (),
        leaf_ids: Sequence[str] = (),
    ) -> None:
        """Seed the allocator with canonical identities already occupied by a draft."""
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
        """Allocate one document-scoped section identity from a slugged hint."""
        return self._reserve_next(self._section_ids, slugify_id_hint(id_hint, fallback="section"))

    def adopt_section(self, section_id: str) -> str:
        """Reserve one existing section identity without allocating a replacement."""
        canonical_id = _canonical_id(section_id, "section id")
        self._section_ids.add(canonical_id)
        self._track_ids_by_section.setdefault(canonical_id, set())
        return canonical_id

    def allocate_track(self, section_id: str, id_hint: str | None = None) -> str:
        """Allocate one section-scoped track identity from a slugged hint."""
        canonical_section_id = self._require_section(section_id)
        occupied = self._track_ids_by_section[canonical_section_id]
        return self._reserve_next(occupied, slugify_id_hint(id_hint, fallback="track"))

    def adopt_track(self, section_id: str, track_id: str) -> str:
        """Reserve one existing local track identity without allocating a replacement."""
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
        """Allocate one globally unique binding ID using channel before advisory hint."""
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
        """Reserve one exact existing global binding identity idempotently."""
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
        """Allocate one generic globally unique track-leaf identity.

        Fill and annotation naming is deliberately structural only in CM-13.
        Later intent/capability slices own their semantic identity conventions.
        """
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
        """Reserve one exact existing generic track-leaf identity idempotently."""
        canonical_id = _canonical_id(leaf_id, "leaf id")
        self._leaf_ids.add(canonical_id)
        return canonical_id

    def section_is_reserved(self, section_id: str) -> bool:
        """Return whether one exact section identity is already occupied."""
        return section_id in self._section_ids

    def track_is_reserved(self, section_id: str, track_id: str) -> bool:
        """Return whether one exact local track identity is already occupied."""
        return track_id in self._track_ids_by_section.get(section_id, set())

    def binding_is_reserved(self, binding_id: str) -> bool:
        """Return whether one exact binding identity is already occupied globally."""
        return binding_id in self._binding_ids

    def leaf_is_reserved(self, leaf_id: str) -> bool:
        """Return whether one exact generic leaf identity is already occupied globally."""
        return leaf_id in self._leaf_ids

    def _require_section(self, section_id: str) -> str:
        """Require that a parent section is already explicitly reserved."""
        canonical_section_id = _canonical_id(section_id, "section id")
        if canonical_section_id not in self._section_ids:
            raise ProgramNameError(
                f"Section identity '{canonical_section_id}' has not been reserved."
            )
        return canonical_section_id

    def _require_track(self, section_id: str, track_id: str) -> tuple[str, str]:
        """Require that a parent section and local track are already reserved."""
        canonical_section_id = self._require_section(section_id)
        canonical_track_id = _canonical_id(track_id, "track id")
        if canonical_track_id not in self._track_ids_by_section[canonical_section_id]:
            raise ProgramNameError(
                "Track identity "
                f"'{canonical_track_id}' has not been reserved in section "
                f"'{canonical_section_id}'."
            )
        return canonical_section_id, canonical_track_id

    @staticmethod
    def _reserve_next(occupied: set[str], base: str) -> str:
        """Reserve the base ID or its first free numeric suffix deterministically."""
        candidate = base
        suffix = 2
        while candidate in occupied:
            candidate = f"{base}.{suffix}"
            suffix += 1
        occupied.add(candidate)
        return candidate


def _canonical_id(value: object, label: str) -> str:
    """Validate one exact adopted identity without normalizing or renaming it."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProgramTypeError(f"{label.capitalize()} must be a non-empty trimmed string.")
    return value


def _channel_identity_seed(channel: object) -> str:
    """Normalize a source channel without discarding its canonical case."""
    if not isinstance(channel, str):
        raise ProgramTypeError("Binding channel identity seeds must be strings.")
    normalized = unicodedata.normalize("NFKD", channel)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    seed = _NON_SLUG_CHARACTERS.sub("-", ascii_text).strip("-")
    return seed or "binding"


__all__ = ["IdAllocator", "slugify_id_hint"]
