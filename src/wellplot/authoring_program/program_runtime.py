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

"""Private semantic dry-run execution for canonical Authoring Program intent.

``ProgramRuntime`` deliberately reuses the canonical reconciliation and
execution stack. It mutates only a private service created from a deep copy of
the caller's document and never persists, renders, inspects sources, or loads
project state.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from typing import Any

from ..authoring_context import AuthoringChannelAlias, AuthoringChannelInput
from ..authoring_executor import AuthoringExecutionResult, execute_authoring_plan
from ..authoring_reconciler import AuthoringReconciliationPlan, reconcile_authoring
from ..authoring_service import AuthoringService
from ..model.authoring import AuthoringDocumentSpec
from ..model.intent import AuthoringDocumentIntent
from .errors import ProgramDryRunError, ProgramTypeError
from .models import (
    AuthoringProgram,
    ProgramArtifact,
    ProgramDiagnostic,
    ProgramExecutionResult,
    ProgramMetrics,
)


class ProgramRuntime:
    """Run canonical desired state privately against explicit caller context."""

    def __init__(
        self,
        document: AuthoringDocumentSpec,
        *,
        scaffold: AuthoringDocumentSpec | None = None,
        defaults: Mapping[str, Any] | None = None,
        available_channels: Mapping[str, Sequence[AuthoringChannelInput]] | None = None,
        channel_aliases: Sequence[AuthoringChannelAlias | Mapping[str, Any]] = (),
        header_aliases: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        """Capture defensive copies of the explicit deterministic dry-run inputs."""
        if not isinstance(document, AuthoringDocumentSpec):
            raise TypeError("ProgramRuntime document must be an AuthoringDocumentSpec.")
        if scaffold is not None and not isinstance(scaffold, AuthoringDocumentSpec):
            raise TypeError("ProgramRuntime scaffold must be an AuthoringDocumentSpec.")

        self._document = _clone_document(document)
        self._scaffold = _clone_document(scaffold) if scaffold is not None else None
        self._defaults = deepcopy(dict(defaults)) if defaults is not None else None
        self._available_channels = (
            deepcopy(dict(available_channels)) if available_channels is not None else None
        )
        self._channel_aliases = tuple(deepcopy(list(channel_aliases)))
        self._header_aliases = (
            deepcopy(dict(header_aliases)) if header_aliases is not None else None
        )

    def dry_run(
        self,
        program: AuthoringProgram,
        intent: AuthoringDocumentIntent,
        *,
        metrics: ProgramMetrics | None = None,
    ) -> ProgramExecutionResult:
        """Privately reconcile, execute, and validate one canonical intent.

        ``intent`` is authoritative input from CM-14. This method does not
        parse or interpret ``program`` again; it retains the program only as
        evidence on the returned execution result.
        """
        if not isinstance(program, AuthoringProgram):
            raise ProgramTypeError("Dry-run program must be an AuthoringProgram.")
        if not isinstance(intent, AuthoringDocumentIntent):
            raise ProgramTypeError("Dry-run intent must be an AuthoringDocumentIntent.")
        if metrics is not None and not isinstance(metrics, ProgramMetrics):
            raise ProgramTypeError("Dry-run metrics must be ProgramMetrics when provided.")

        result_metrics = metrics or ProgramMetrics()
        try:
            service = AuthoringService(_clone_document(self._document))
            plan = reconcile_authoring(
                intent,
                existing=service.document,
                scaffold=_clone_document(self._scaffold) if self._scaffold is not None else None,
                defaults=deepcopy(self._defaults),
                available_channels=deepcopy(self._available_channels),
                channel_aliases=deepcopy(self._channel_aliases),
                header_aliases=deepcopy(self._header_aliases),
            )
        except Exception:  # noqa: BLE001 - preserve a compact model-facing boundary
            return _failed_result(
                program,
                result_metrics,
                ["Private authoring dry run could not prepare canonical execution."],
            )

        if not plan.ready:
            return _failed_result(
                program,
                result_metrics,
                _plan_messages(plan),
            )

        try:
            execution = execute_authoring_plan(service, plan)
        except Exception:  # noqa: BLE001 - never expose implementation exceptions to the program
            return _failed_result(
                program,
                result_metrics,
                ["Private authoring dry run could not execute the canonical plan."],
            )

        if not execution.success:
            return _failed_result(
                program,
                result_metrics,
                _execution_messages(execution),
            )

        validation = service.validate()
        if not validation.valid:
            return _failed_result(
                program,
                result_metrics,
                ["Private authoring dry run produced an invalid canonical document."],
            )

        return ProgramExecutionResult(
            program=program,
            success=True,
            artifact=ProgramArtifact(intent_fragment=intent),
            metrics=result_metrics,
        )


def _clone_document(document: AuthoringDocumentSpec) -> AuthoringDocumentSpec:
    """Return one deep canonical clone without using a service as a copier."""
    return AuthoringDocumentSpec.model_validate(deepcopy(document).model_dump(mode="python"))


def _plan_messages(plan: AuthoringReconciliationPlan) -> list[str]:
    """Convert ordered canonical reconciliation issues into compact dry-run text."""
    return _unique_messages(f"{issue.code}: {issue.message}" for issue in plan.issues) or [
        "Private authoring dry run rejected the canonical intent."
    ]


def _execution_messages(execution: AuthoringExecutionResult) -> list[str]:
    """Convert deterministic execution outcomes without exposing Python exception detail."""
    outcome_messages = [
        f"Canonical execution could not apply {outcome.object_kind.value} '{outcome.object_id}'."
        for outcome in execution.outcomes
        if outcome.error is not None
    ]
    if outcome_messages:
        return _unique_messages(outcome_messages)
    return ["Private authoring dry run could not apply the canonical intent."]


def _unique_messages(messages: Iterable[str]) -> list[str]:
    """Return non-empty diagnostic messages in deterministic first-seen order."""
    unique: list[str] = []
    seen: set[str] = set()
    for message in messages:
        if not isinstance(message, str):
            continue
        compact = message.strip()
        if not compact or compact in seen:
            continue
        seen.add(compact)
        unique.append(compact)
    return unique


def _failed_result(
    program: AuthoringProgram,
    metrics: ProgramMetrics,
    messages: Sequence[str],
) -> ProgramExecutionResult:
    """Build an artifact-free, all-or-nothing semantic dry-run result."""
    diagnostics: tuple[ProgramDiagnostic, ...] = tuple(
        ProgramDryRunError(
            message,
            remediation_hint=(
                "Revise the intent using the supplied current document and execution context."
            ),
        ).to_diagnostic()
        for message in _unique_messages(messages)
    )
    if not diagnostics:
        diagnostics = (
            ProgramDryRunError(
                "Private authoring dry run rejected the canonical intent."
            ).to_diagnostic(),
        )
    return ProgramExecutionResult(
        program=program,
        success=False,
        diagnostics=diagnostics,
        metrics=metrics,
    )


__all__ = ["ProgramRuntime"]
