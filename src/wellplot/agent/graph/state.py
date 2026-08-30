###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""LangGraph state definitions for natural-language reconstruction."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, NotRequired

from typing_extensions import TypedDict

from .models import CompilationMode


class ReconstructionState(TypedDict, total=False):
    """JSON-serializable graph state.

    Parallel workers append to ``compiled_artifacts`` and ``diagnostics`` using
    reducers. Shared mutable canonical Wellplot objects are deliberately not
    placed in worker state.
    """

    request: str
    mode: CompilationMode
    current_document: dict[str, Any]
    source_manifest: dict[str, Any]
    plan: dict[str, Any]
    compiled_artifacts: Annotated[list[dict[str, Any]], operator.add]
    merged_intent: dict[str, Any]
    validation: dict[str, Any]
    preview_path: str
    diagnostics: Annotated[list[dict[str, Any]], operator.add]
    repair_attempt: int


class CompilationWorkerState(TypedDict, total=False):
    """Read-only context supplied to one dynamically dispatched compiler worker."""

    request: str
    mode: CompilationMode
    current_document: dict[str, Any]
    source_manifest: dict[str, Any]
    work_unit: Literal["report", "section"]
    plan: NotRequired[dict[str, Any]]
    section_plan: NotRequired[dict[str, Any]]
    compiled_artifacts: Annotated[list[dict[str, Any]], operator.add]
