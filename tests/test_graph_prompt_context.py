"""Tests for graph-provider prompt context serialization."""

from __future__ import annotations

import json

from wellplot.agent.graph.prompt_context import compact_prompt_json


def test_compact_prompt_json_preserves_values_without_pretty_printing() -> None:
    """Context remains JSON-equivalent while avoiding indentation overhead."""
    context = {
        "request": "Build a log.",
        "sections": [
            {"section_id": "main", "tracks": ["depth", "resistivity"]},
            {"section_id": "repeat", "tracks": []},
        ],
        "metadata": {"source": "input.dlis", "enabled": True, "count": 2},
    }

    compact = compact_prompt_json(context)

    assert json.loads(compact) == context
    assert compact == json.dumps(context, default=str, separators=(",", ":"))
    assert len(compact) < len(json.dumps(context, default=str, indent=2))
