###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Direct, transactional execution for compiled reconstruction intents."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ...authoring_context import (
    AuthoringChannelAlias,
    AuthoringChannelInput,
    AuthoringContextResolution,
    resolve_authoring_context,
)
from ...authoring_reconciler import AuthoringReconciliationPlan, reconcile_authoring
from ...authoring_service import AuthoringService
from ...model.authoring import AuthoringDocumentSpec
from ...model.intent import AuthoringDocumentIntent
from ..operation_executor import TypedSubmissionExecutionResult, execute_typed_submissions
from ..reconciliation_bridge import TypedReconciliationCompilation, compile_reconciliation_plan


@dataclass(frozen=True)
class DirectIntentExecutionResult:
    """Evidence returned by one direct compiled-intent execution attempt.

    Resolution, reconciliation, and typed execution remain independently
    inspectable. A blocked result never mutates the supplied service.
    """

    document: AuthoringDocumentSpec
    resolution: AuthoringContextResolution
    reconciliation_plan: AuthoringReconciliationPlan | None = None
    compilation: TypedReconciliationCompilation | None = None
    execution: TypedSubmissionExecutionResult | None = None
    errors: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        """Return whether the intent was reconciled and committed successfully."""
        return bool(self.execution is not None and self.execution.success)


def execute_document_intent(
    service: AuthoringService,
    intent: AuthoringDocumentIntent,
    *,
    scaffold: AuthoringDocumentSpec | None = None,
    defaults: Mapping[str, Any] | None = None,
    available_channels: Mapping[str, Sequence[AuthoringChannelInput]] | None = None,
    channel_aliases: Sequence[AuthoringChannelAlias | Mapping[str, Any]] = (),
    header_aliases: Mapping[str, Sequence[str]] | None = None,
) -> DirectIntentExecutionResult:
    """Apply one compiled intent through the canonical authoring services.

    This is the internal graph execution boundary. It deliberately has no MCP,
    provider, file, or rendering dependency. The supplied ``AuthoringService``
    changes only when every compiled typed operation succeeds.
    """
    resolution = resolve_authoring_context(
        intent,
        existing=service.document,
        scaffold=scaffold,
        defaults=defaults,
        available_channels=available_channels,
        channel_aliases=channel_aliases,
        header_aliases=header_aliases,
    )
    if not resolution.ready:
        return DirectIntentExecutionResult(
            document=service.document,
            resolution=resolution,
            errors=tuple(issue.message for issue in resolution.issues),
        )

    reconciliation_plan = reconcile_authoring(
        resolution,
        existing=service.document,
    )
    if not reconciliation_plan.ready:
        return DirectIntentExecutionResult(
            document=service.document,
            resolution=resolution,
            reconciliation_plan=reconciliation_plan,
            errors=tuple(issue.message for issue in reconciliation_plan.issues),
        )

    try:
        compilation = compile_reconciliation_plan(
            reconciliation_plan,
            service=service,
        )
    except ValueError as exc:
        return DirectIntentExecutionResult(
            document=service.document,
            resolution=resolution,
            reconciliation_plan=reconciliation_plan,
            errors=(str(exc),),
        )

    execution = execute_typed_submissions(
        service,
        submissions=compilation.submissions,
        work_units=compilation.work_units,
        defaults_provenance_by_operation=compilation.defaults_provenance_by_operation,
    )
    return DirectIntentExecutionResult(
        document=service.document,
        resolution=resolution,
        reconciliation_plan=reconciliation_plan,
        compilation=compilation,
        execution=execution,
        errors=execution.errors,
    )


__all__ = ["DirectIntentExecutionResult", "execute_document_intent"]
