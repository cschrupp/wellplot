###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Verified final rendering and read-only visual QA for graph execution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from ...authoring_context import AuthoringChannelAlias, AuthoringChannelInput
from ...model.authoring import AuthoringDocumentSpec
from ...model.intent import AuthoringDocumentIntent
from .models import VisualCorrection
from .verifier import DocumentIntentVerificationResult, verify_document_intent

MAX_VISUAL_REPAIR_CYCLES = 2


@dataclass(frozen=True)
class FinalRenderArtifact:
    """Immutable render output supplied to the visual-review boundary."""

    backend: str
    page_count: int
    page_images: tuple[bytes, ...] = ()
    output_path: str | None = None

    def __post_init__(self) -> None:
        """Reject artifacts that cannot be reviewed or delivered."""
        object.__setattr__(self, "page_images", tuple(self.page_images))
        if not self.backend.strip():
            raise ValueError("Render artifact backend must be non-empty.")
        if self.page_count < 1:
            raise ValueError("Render artifact page_count must be at least one.")
        if not all(isinstance(image, bytes) for image in self.page_images):
            raise ValueError("Render artifact page_images must contain only bytes.")
        if not self.page_images and not self.output_path:
            raise ValueError("Render artifact requires page images or an output path.")


class CanonicalDocumentRenderer(Protocol):
    """Render the exact in-memory canonical document supplied by the graph."""

    def render(self, document: AuthoringDocumentSpec) -> FinalRenderArtifact:
        """Render one canonical document without mutating it."""


class VisualReviewResult(BaseModel):
    """Structured visual-review output that cannot mutate canonical state."""

    model_config = ConfigDict(extra="forbid")

    corrections: list[VisualCorrection] = Field(default_factory=list)


@dataclass(frozen=True)
class VisualReviewRequest:
    """Immutable context provided to a vision-capable visual reviewer."""

    request: str
    document: AuthoringDocumentSpec
    intent: AuthoringDocumentIntent
    artifact: FinalRenderArtifact


class VisualReviewer(Protocol):
    """Return structured visual corrections for one final render artifact."""

    async def review(self, request: VisualReviewRequest) -> VisualReviewResult:
        """Review the rendered artifact without changing canonical authoring state."""


@dataclass(frozen=True)
class DocumentFinalizationResult:
    """Evidence from semantic verification, final rendering, and visual QA."""

    document: AuthoringDocumentSpec
    verification: DocumentIntentVerificationResult
    artifact: FinalRenderArtifact | None = None
    corrections: tuple[VisualCorrection, ...] = ()
    errors: tuple[str, ...] = ()
    max_repair_cycles: int = MAX_VISUAL_REPAIR_CYCLES

    @property
    def success(self) -> bool:
        """Return whether semantic verification and final rendering succeeded."""
        return self.verification.success and self.artifact is not None and not self.errors

    @property
    def needs_repair(self) -> bool:
        """Return whether visual QA found corrections for a later typed repair stage."""
        return bool(self.corrections)

    @property
    def ready_for_delivery(self) -> bool:
        """Return whether the verified render needs no visual repair."""
        return self.success and not self.needs_repair


async def finalize_document_intent(
    document: AuthoringDocumentSpec,
    intent: AuthoringDocumentIntent,
    *,
    renderer: CanonicalDocumentRenderer,
    request: str = "",
    reviewer: VisualReviewer | None = None,
    scaffold: AuthoringDocumentSpec | None = None,
    defaults: Mapping[str, Any] | None = None,
    available_channels: Mapping[str, Sequence[AuthoringChannelInput]] | None = None,
    channel_aliases: Sequence[AuthoringChannelAlias | Mapping[str, Any]] = (),
    header_aliases: Mapping[str, Sequence[str]] | None = None,
    max_repair_cycles: int = MAX_VISUAL_REPAIR_CYCLES,
) -> DocumentFinalizationResult:
    """Verify, render, and visually review one canonical document.

    Rendering occurs only after deterministic semantic verification passes. A
    reviewer may return typed correction requests, but this boundary neither
    mutates the document nor executes repairs. Later graph stages must route
    corrections through the owning typed capability compiler.
    """
    if not 1 <= max_repair_cycles <= MAX_VISUAL_REPAIR_CYCLES:
        raise ValueError(f"max_repair_cycles must be between one and {MAX_VISUAL_REPAIR_CYCLES}.")

    verification = verify_document_intent(
        document,
        intent,
        scaffold=scaffold,
        defaults=defaults,
        available_channels=available_channels,
        channel_aliases=channel_aliases,
        header_aliases=header_aliases,
    )
    if not verification.success:
        return DocumentFinalizationResult(
            document=document,
            verification=verification,
            errors=tuple(issue.message for issue in verification.issues),
            max_repair_cycles=max_repair_cycles,
        )

    try:
        artifact = renderer.render(document.model_copy(deep=True))
    except Exception as exc:
        return DocumentFinalizationResult(
            document=document,
            verification=verification,
            errors=(f"Final rendering failed: {exc}",),
            max_repair_cycles=max_repair_cycles,
        )

    corrections: tuple[VisualCorrection, ...] = ()
    if reviewer is not None:
        try:
            review = await reviewer.review(
                VisualReviewRequest(
                    request=request,
                    document=document.model_copy(deep=True),
                    intent=intent.model_copy(deep=True),
                    artifact=artifact,
                )
            )
        except Exception as exc:
            return DocumentFinalizationResult(
                document=document,
                verification=verification,
                artifact=artifact,
                errors=(f"Visual review failed: {exc}",),
                max_repair_cycles=max_repair_cycles,
            )
        corrections = tuple(review.corrections)

    return DocumentFinalizationResult(
        document=document,
        verification=verification,
        artifact=artifact,
        corrections=corrections,
        max_repair_cycles=max_repair_cycles,
    )


__all__ = [
    "CanonicalDocumentRenderer",
    "DocumentFinalizationResult",
    "FinalRenderArtifact",
    "MAX_VISUAL_REPAIR_CYCLES",
    "VisualReviewRequest",
    "VisualReviewResult",
    "VisualReviewer",
    "finalize_document_intent",
]
