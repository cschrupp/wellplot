###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Typed request compilation contracts for the provider-facing agent layer."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..model.intent import AuthoringDocumentIntent


class AuthoringRequestItem(BaseModel):
    """One deterministic request item that must be accounted for by the provider."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    item_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class AuthoringRequestManifest(BaseModel):
    """Compact, stable request inventory used for intent coverage validation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    items: list[AuthoringRequestItem] = Field(min_length=1)


AuthoringCoverageStatus = Literal[
    "mapped",
    "preserved",
    "unsupported",
    "inconsistent",
]


class AuthoringIntentCoverage(BaseModel):
    """Provider claim linking one request item to typed intent paths."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_item_id: str = Field(min_length=1)
    status: AuthoringCoverageStatus
    intent_paths: list[str] = Field(default_factory=list)
    reason: str | None = Field(default=None, min_length=1)


class AuthoringIntentSubmission(BaseModel):
    """One typed desired state plus coverage for the request manifest."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    intent: AuthoringDocumentIntent
    coverage: list[AuthoringIntentCoverage] = Field(min_length=1)


def _strip_bullet(line: str) -> str:
    """Remove one common bullet or numbered-list prefix."""
    return re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", line).strip()


def _is_bullet(line: str) -> bool:
    """Return whether one line starts a list item."""
    return bool(re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", line))


def build_request_manifest(text: str) -> AuthoringRequestManifest:
    """Split a natural-language request into stable, reviewable request items."""
    items: list[str] = []
    current: str | None = None
    paragraph: list[str] = []

    def flush_current() -> None:
        nonlocal current
        if current:
            items.append(current.strip())
        current = None

    def flush_paragraph() -> None:
        if paragraph:
            items.append(" ".join(paragraph).strip())
            paragraph.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_current()
            flush_paragraph()
            continue
        if _is_bullet(raw_line):
            flush_paragraph()
            flush_current()
            current = _strip_bullet(raw_line)
            continue
        if current is not None:
            current = f"{current} {line}".strip()
            continue
        if line.endswith(":"):
            flush_paragraph()
            paragraph.append(line)
            continue
        paragraph.append(line)

    flush_current()
    flush_paragraph()
    normalized_items = [item for item in items if item]
    if not normalized_items and text.strip():
        normalized_items = [text.strip()]
    return AuthoringRequestManifest(
        items=[
            AuthoringRequestItem(item_id=f"request-{index:03d}", text=item)
            for index, item in enumerate(normalized_items, start=1)
        ]
    )


def validate_intent_coverage(
    manifest: AuthoringRequestManifest,
    coverage: Iterable[AuthoringIntentCoverage],
) -> list[str]:
    """Return deterministic errors for incomplete or contradictory coverage."""
    entries = list(coverage)
    expected_ids = {item.item_id for item in manifest.items}
    seen_ids: set[str] = set()
    errors: list[str] = []
    for entry in entries:
        if entry.request_item_id in seen_ids:
            errors.append(f"Duplicate coverage for {entry.request_item_id!r}.")
        seen_ids.add(entry.request_item_id)
        if entry.request_item_id not in expected_ids:
            errors.append(f"Coverage references unknown request item {entry.request_item_id!r}.")
        if entry.status in {"mapped", "preserved"} and not entry.intent_paths:
            errors.append(
                f"Coverage for {entry.request_item_id!r} needs at least one intent path."
            )
        if entry.status in {"unsupported", "inconsistent"} and not entry.reason:
            errors.append(
                f"Coverage for {entry.request_item_id!r} needs a reason for status "
                f"{entry.status!r}."
            )
    missing_ids = sorted(expected_ids - seen_ids)
    errors.extend(f"Missing coverage for request item {item_id!r}." for item_id in missing_ids)
    return errors


__all__ = [
    "AuthoringCoverageStatus",
    "AuthoringIntentCoverage",
    "AuthoringIntentSubmission",
    "AuthoringRequestItem",
    "AuthoringRequestManifest",
    "build_request_manifest",
    "validate_intent_coverage",
]
