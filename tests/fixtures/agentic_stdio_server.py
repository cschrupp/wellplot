"""Deterministic graph-host fixture for real MCP stdio integration tests."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path

from wellplot.mcp import create_mcp_server
from wellplot.mcp.agentic import GraphAuthoringMcpOperations
from wellplot.mcp.stdio import run_stdio


class FixtureGraph:
    """Emit fixed graph artifacts selected by the integration-test request."""

    async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
        """Return a valid graph result for one deterministic test request."""
        mode = str(state["mode"])
        request = str(state["request"])
        section = {
            "section_id": "main",
            "capability_id": "section.log_plot",
            "goal": "Update the main section.",
        }
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
        return {
            "plan": {"summary": f"{mode} main section.", "sections": [section]},
            "merged_intent": deepcopy(intent),
        }


def main() -> None:
    """Run the deterministic graph fixture over real MCP stdio."""
    root = Path(os.environ["WELLPLOT_AGENTIC_TEST_ROOT"]).resolve()
    operations = GraphAuthoringMcpOperations.create(graph=FixtureGraph(), root=root)
    run_stdio(create_mcp_server(root, agentic_operations=operations))


if __name__ == "__main__":
    main()
