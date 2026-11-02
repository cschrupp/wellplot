"""Security and lifecycle regressions for graph execution traces."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from wellplot.agent.execution_trace import AgentRunTrace, read_agent_trace


def test_stage_trace_does_not_persist_arbitrary_exception_text(tmp_path: Path) -> None:
    """Unexpected messages may contain secrets or local paths and are omitted."""
    trace = AgentRunTrace(path=tmp_path / "run.jsonl", run_id="test-run")
    secret = "sk-private-token-0123456789"
    private_path = "/home/user/private/source.dlis"

    with pytest.raises(RuntimeError, match="private"), trace.stage("inspection"):
        raise RuntimeError(f"{secret} failed while reading {private_path}")

    terminal = read_agent_trace(trace.path)[-1]
    serialized = terminal.model_dump_json()
    assert terminal.status == "failed"
    assert terminal.details == {
        "exception_type": "RuntimeError",
        "exception_module": "builtins",
    }
    assert secret not in serialized
    assert private_path not in serialized


def test_stage_trace_records_cancellation_and_propagates_it(tmp_path: Path) -> None:
    """Cancellation is observable without converting it into a worker failure."""
    trace = AgentRunTrace(path=tmp_path / "run.jsonl", run_id="test-run")

    async def cancel_stage() -> None:
        with trace.stage("section_worker"):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cancel_stage())

    terminal = read_agent_trace(trace.path)[-1]
    assert terminal.event == "stage_finished"
    assert terminal.stage == "section_worker"
    assert terminal.status == "cancelled"
    assert terminal.details == {"termination_kind": "cancelled"}
