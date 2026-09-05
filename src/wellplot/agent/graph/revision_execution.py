###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Transactional execution and verification for graph-compiled revisions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from ...authoring_context import AuthoringChannelAlias, AuthoringChannelInput
from ...authoring_service import AuthoringService
from ...model.authoring import AuthoringDocumentSpec
from .executor import DirectIntentExecutionResult, execute_document_intent
from .revision import RevisionCompilationResult, compile_document_revision
from .source_context import available_channels_from_source_manifest
from .verifier import DocumentIntentVerificationResult, verify_document_intent


@dataclass(frozen=True)
class RevisionExecutionResult:
    """Evidence from one graph-compiled revision transaction.

    If final semantic verification fails after otherwise successful execution,
    ``rolled_back`` is true and ``document`` is the restored pre-revision
    snapshot. The direct execution evidence remains available for diagnosis.
    """

    revision: RevisionCompilationResult
    execution: DirectIntentExecutionResult
    document: AuthoringDocumentSpec
    verification: DocumentIntentVerificationResult | None = None
    errors: tuple[str, ...] = ()
    rolled_back: bool = False

    @property
    def success(self) -> bool:
        """Return whether the revision executed and semantically verified."""
        return bool(
            self.execution.success
            and self.verification is not None
            and self.verification.success
            and not self.errors
            and not self.rolled_back
        )


async def execute_document_revision(
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
) -> RevisionExecutionResult:
    """Compile, execute, verify, and atomically publish one document revision.

    Compilation reads a defensive service snapshot. The existing direct
    executor remains responsible for typed mutation and operation-level
    transactionality. This facade adds the final semantic postcondition: a
    verification failure restores the pre-revision canonical document.
    """
    before = service.document
    revision = await compile_document_revision(
        graph,
        request=request,
        current_document=before,
        source_manifest=source_manifest,
        logfile_path=logfile_path,
    )
    effective_channels = dict(available_channels or {})
    effective_channels.update(available_channels_from_source_manifest(revision.source_manifest))
    execution = execute_document_intent(
        service,
        revision.intent,
        scaffold=scaffold,
        defaults=defaults,
        available_channels=effective_channels,
        channel_aliases=channel_aliases,
        header_aliases=header_aliases,
    )
    if not execution.success:
        return RevisionExecutionResult(
            revision=revision,
            execution=execution,
            document=service.document,
            errors=execution.errors,
        )

    verification = verify_document_intent(
        service.document,
        revision.intent,
        scaffold=scaffold,
        defaults=defaults,
        available_channels=effective_channels,
        channel_aliases=channel_aliases,
        header_aliases=header_aliases,
    )
    if verification.success:
        return RevisionExecutionResult(
            revision=revision,
            execution=execution,
            document=service.document,
            verification=verification,
        )

    service.replace_document(before)
    return RevisionExecutionResult(
        revision=revision,
        execution=execution,
        document=service.document,
        verification=verification,
        errors=tuple(issue.message for issue in verification.issues),
        rolled_back=True,
    )


__all__ = ["RevisionExecutionResult", "execute_document_revision"]
