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

"""Public host-side agent exports for LLM-driven wellplot authoring."""

from .execution_trace import AgentTraceEvent, read_agent_trace
from .notebook import (
    AgenticMcpClient,
    ProjectPaths,
    ProjectSession,
    ProjectStarter,
    create_agentic_mcp_client,
    create_project_session,
    display_agentic_result,
    display_authoring_result,
    display_phase_previews,
    relative_path,
)
from .results import AuthoringResult, AuthoringRunState, AuthoringUserReport
from .session import (
    AgentDiagnostic,
    AgentDiagnosticSeverity,
    AgentMetrics,
    AgentSession,
    AgentSessionConfig,
    AgentSessionResult,
    AgentSourceConfig,
    AgentWorkerEvidence,
    AgentWorkerMetrics,
)
from .tool_contract import (
    StableToolProfile,
    stable_tool_budget,
    stable_tool_profile,
)

__all__ = [
    "AuthoringResult",
    "AuthoringRunState",
    "AuthoringUserReport",
    "AgentTraceEvent",
    "AgenticMcpClient",
    "AgentDiagnostic",
    "AgentDiagnosticSeverity",
    "AgentMetrics",
    "AgentSession",
    "AgentSessionConfig",
    "AgentSessionResult",
    "AgentSourceConfig",
    "AgentWorkerMetrics",
    "AgentWorkerEvidence",
    "ProjectPaths",
    "ProjectSession",
    "ProjectStarter",
    "create_agentic_mcp_client",
    "create_project_session",
    "display_authoring_result",
    "display_agentic_result",
    "display_phase_previews",
    "relative_path",
    "read_agent_trace",
    "StableToolProfile",
    "stable_tool_budget",
    "stable_tool_profile",
]


_LEGACY_COMPATIBILITY_EXPORTS = frozenset(
    {
        "AuthoringPlanPhase",
        "AuthoringPlanResult",
        "AuthoringRequest",
        "AuthoringToolCall",
        "BranchOperationGroup",
        "DirectBranchCompilationResult",
        "ExecutedAuthoringPhase",
        "RevisionRequest",
        "build_branch_operation_groups",
        "compile_direct_branch_operations",
        "revise_authoring_request",
        "run_authoring_request",
    }
)


def __getattr__(name: str) -> object:
    """Load historical core exports only for explicit compatibility callers."""
    if name not in _LEGACY_COMPATIBILITY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if name in {
        "BranchOperationGroup",
        "DirectBranchCompilationResult",
        "build_branch_operation_groups",
        "compile_direct_branch_operations",
    }:
        from . import branch_compiler

        return getattr(branch_compiler, name)
    from . import core

    return getattr(core, name)
