###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Transactional execution and verification for graph-compiled reconstructions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from ...authoring_context import AuthoringChannelAlias, AuthoringChannelInput
from ...authoring_service import AuthoringService
from ...model.authoring import AuthoringDocumentSpec
from .executor import DirectIntentExecutionResult, execute_document_intent
from .reconstruction import (
    ReconstructionCompilationResult,
    compile_document_reconstruction,
)
from .source_context import available_channels_from_source_manifest
from .verifier import DocumentIntentVerificationResult, verify_document_intent


@dataclass(frozen=True)
class ReconstructionExecutionResult:
    """Evidence from one graph-compiled reconstruction transaction.

    If final semantic verification fails after otherwise successful execution,
    ``rolled_back`` is true and ``document`` is the restored starting snapshot.
    The direct execution evidence remains available for diagnosis.
    """

    reconstruction: ReconstructionCompilationResult
    execution: DirectIntentExecutionResult
    document: AuthoringDocumentSpec
    verification: DocumentIntentVerificationResult | None = None
    errors: tuple[str, ...] = ()
    rolled_back: bool = False

    @property
    def success(self) -> bool:
        """Return whether reconstruction executed and semantically verified."""
        return bool(
            self.execution.success
            and self.verification is not None
            and self.verification.success
            and not self.errors
            and not self.rolled_back
        )


async def execute_document_reconstruction(
    graph: CompiledStateGraph,
    service: AuthoringService,
    *,
    request: str,
    source_manifest: Mapping[str, Any] | None = None,
    logfile_path: str | None = None,
    scaffold: AuthoringDocumentSpec | None = None,
    defaults: Mapping[str, Any] | None = None,
    available_channels: Mapping[str, Sequence[AuthoringChannelInput]] | None = None,
    channel_aliases: Sequence[AuthoringChannelAlias | Mapping[str, Any]] = (),
    header_aliases: Mapping[str, Sequence[str]] | None = None,
) -> ReconstructionExecutionResult:
    """Compile, execute, verify, and atomically publish one reconstruction.

    Compilation reads a defensive service snapshot. The direct executor owns
    typed mutation and operation-level transactionality. This facade adds the
    final semantic postcondition: a verification failure restores the pre-run
    canonical document.
    """
    before = service.document
    reconstruction = await compile_document_reconstruction(
        graph,
        request=request,
        current_document=before,
        source_manifest=source_manifest,
        logfile_path=logfile_path,
    )
    effective_channels = dict(available_channels or {})
    effective_channels.update(
        available_channels_from_source_manifest(reconstruction.source_manifest)
    )
    execution = execute_document_intent(
        service,
        reconstruction.intent,
        scaffold=scaffold,
        defaults=defaults,
        available_channels=effective_channels,
        channel_aliases=channel_aliases,
        header_aliases=header_aliases,
    )
    if not execution.success:
        return ReconstructionExecutionResult(
            reconstruction=reconstruction,
            execution=execution,
            document=service.document,
            errors=execution.errors,
        )

    verification = verify_document_intent(
        service.document,
        reconstruction.intent,
        scaffold=scaffold,
        defaults=defaults,
        available_channels=effective_channels,
        channel_aliases=channel_aliases,
        header_aliases=header_aliases,
    )
    if verification.success:
        return ReconstructionExecutionResult(
            reconstruction=reconstruction,
            execution=execution,
            document=service.document,
            verification=verification,
        )

    service.replace_document(before)
    return ReconstructionExecutionResult(
        reconstruction=reconstruction,
        execution=execution,
        document=service.document,
        verification=verification,
        errors=tuple(issue.message for issue in verification.issues),
        rolled_back=True,
    )


__all__ = ["ReconstructionExecutionResult", "execute_document_reconstruction"]
