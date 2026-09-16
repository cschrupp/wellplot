"""Deterministic graph-host fixture for real MCP stdio integration tests."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path

from wellplot.agent.session import (
    AgentDiagnostic,
    AgentMetrics,
    AgentSessionResult,
    AgentWorkerEvidence,
    AgentWorkerMetrics,
)
from wellplot.mcp import create_mcp_server
from wellplot.mcp.agentic import GraphAuthoringMcpOperations
from wellplot.mcp.stdio import run_stdio


class FixtureSession:
    """Emit fixed v2 session results selected by the integration-test request."""

    async def build(self, *, request: str, **_: object) -> AgentSessionResult:
        """Return a deterministic build result."""
        return self._result("reconstruct", request)

    async def revise(self, *, request: str, **_: object) -> AgentSessionResult:
        """Return a deterministic revision result."""
        return self._result("revise", request)

    @staticmethod
    def _result(mode: str, request: str) -> AgentSessionResult:
        """Construct one bounded result for the fixture request."""
        if "provider failure" in request:
            return AgentSessionResult(
                mode=mode,
                success=False,
                diagnostics=(
                    AgentDiagnostic(
                        stage="provider",
                        code="provider.transport",
                        message="The configured provider request failed.",
                    ),
                ),
                metrics=AgentMetrics(
                    worker_count=0,
                    successful_workers=0,
                    failed_workers=0,
                    total_program_chars=0,
                    total_ast_nodes=0,
                    total_statements=0,
                    total_calls=0,
                    total_repairs=0,
                    total_loop_iterations=0,
                    total_created_objects=0,
                    max_nesting_depth=0,
                ),
            )
        if "invalid" in request:
            intent: dict[str, object] = {
                "sections": [
                    {
                        "section_id": "main",
                        "tracks": [
                            {
                                "track_id": "missing",
                                "title": "Missing",
                                "kind": "normal",
                                "width_mm": 20,
                                "bindings": [
                                    {
                                        "kind": "curve",
                                        "binding_id": "main.missing.UNKNOWN.1",
                                        "channel": "UNKNOWN",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        elif mode == "revise":
            intent = {"sections": [{"section_id": "main", "subtitle": "Revised"}]}
        else:
            intent = {"title": "Graph stdio reconstruction"}
        return AgentSessionResult(
            mode=mode,
            success=True,
            intent=deepcopy(intent),
            workers=(
                AgentWorkerEvidence(
                    kind="report",
                    plan_order=0,
                    success=True,
                    metrics=AgentWorkerMetrics(
                        program_chars=1,
                        program_ast_nodes=1,
                        program_statements=1,
                        program_calls=1,
                        created_objects=1,
                    ),
                ),
            ),
            metrics=AgentMetrics(
                worker_count=1,
                successful_workers=1,
                failed_workers=0,
                total_program_chars=1,
                total_ast_nodes=1,
                total_statements=1,
                total_calls=1,
                total_repairs=0,
                total_loop_iterations=0,
                total_created_objects=1,
                max_nesting_depth=0,
            ),
        )


def main() -> None:
    """Run the deterministic graph fixture over real MCP stdio."""
    root = Path(os.environ["WELLPLOT_AGENTIC_TEST_ROOT"]).resolve()
    operations = GraphAuthoringMcpOperations.create(
        session=FixtureSession(),  # type: ignore[arg-type]
        root=root,
    )
    run_stdio(create_mcp_server(root, agentic_operations=operations))


if __name__ == "__main__":
    main()
