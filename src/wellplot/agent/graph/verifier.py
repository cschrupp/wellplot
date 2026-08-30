###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""Read-only semantic verification for compiled authoring intents."""

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
from ...authoring_reconciler import (
    AuthoringOperation,
    AuthoringReconciliationPlan,
    reconcile_authoring,
)
from ...model.authoring import AuthoringDocumentSpec
from ...model.intent import AuthoringDocumentIntent


@dataclass(frozen=True)
class IntentVerificationIssue:
    """One canonical postcondition that is unmet or cannot be resolved."""

    path: str
    code: str
    message: str
    operation: AuthoringOperation | None = None


@dataclass(frozen=True)
class DocumentIntentVerificationResult:
    """Read-only evidence that a canonical document satisfies one intent."""

    document: AuthoringDocumentSpec
    resolution: AuthoringContextResolution
    reconciliation_plan: AuthoringReconciliationPlan | None = None
    issues: tuple[IntentVerificationIssue, ...] = ()

    @property
    def success(self) -> bool:
        """Return whether every requested canonical postcondition is satisfied."""
        return not self.issues


def _operation_issue(operation: AuthoringOperation) -> IntentVerificationIssue:
    """Describe one reconciliation operation as an unmet postcondition."""
    scope = ".".join(
        part for part in (operation.section_id, operation.track_id, operation.object_id) if part
    )
    path = scope or operation.object_id
    return IntentVerificationIssue(
        path=path,
        code="postcondition_unmet",
        message=(
            f"{operation.reason} Canonical state still requires "
            f"{operation.action.value} of {operation.object_kind.value} "
            f"{operation.object_id!r}."
        ),
        operation=operation,
    )


def verify_document_intent(
    document: AuthoringDocumentSpec,
    intent: AuthoringDocumentIntent,
    *,
    scaffold: AuthoringDocumentSpec | None = None,
    defaults: Mapping[str, Any] | None = None,
    available_channels: Mapping[str, Sequence[AuthoringChannelInput]] | None = None,
    channel_aliases: Sequence[AuthoringChannelAlias | Mapping[str, Any]] = (),
    header_aliases: Mapping[str, Sequence[str]] | None = None,
) -> DocumentIntentVerificationResult:
    """Verify that ``document`` already satisfies ``intent`` without mutation.

    Context resolution and reconciliation are the canonical source of semantic
    comparison rules. A document passes only when contextual resolution is
    ready and reconciliation proposes no remaining operations.
    """
    resolution = resolve_authoring_context(
        intent,
        existing=document,
        scaffold=scaffold,
        defaults=defaults,
        available_channels=available_channels,
        channel_aliases=channel_aliases,
        header_aliases=header_aliases,
    )
    if not resolution.ready:
        return DocumentIntentVerificationResult(
            document=document,
            resolution=resolution,
            issues=tuple(
                IntentVerificationIssue(
                    path=issue.path,
                    code=issue.code,
                    message=issue.message,
                )
                for issue in resolution.issues
            ),
        )

    reconciliation_plan = reconcile_authoring(resolution, existing=document)
    if not reconciliation_plan.ready:
        return DocumentIntentVerificationResult(
            document=document,
            resolution=resolution,
            reconciliation_plan=reconciliation_plan,
            issues=tuple(
                IntentVerificationIssue(
                    path=issue.path,
                    code=issue.code,
                    message=issue.message,
                )
                for issue in reconciliation_plan.issues
            ),
        )

    return DocumentIntentVerificationResult(
        document=document,
        resolution=resolution,
        reconciliation_plan=reconciliation_plan,
        issues=tuple(_operation_issue(operation) for operation in reconciliation_plan.operations),
    )


__all__ = [
    "DocumentIntentVerificationResult",
    "IntentVerificationIssue",
    "verify_document_intent",
]
