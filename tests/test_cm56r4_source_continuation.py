"""Tests for the CM-56R4 source-only continuation wrapper."""

from __future__ import annotations

import asyncio
import json
from argparse import Namespace
from pathlib import Path

import pytest
from scripts import cm56r4_source_continuation as continuation


def _args(output_jsonl: Path) -> Namespace:
    """Build fixed-control continuation arguments for tests."""
    return Namespace(
        output_jsonl=output_jsonl,
        model="qwen3.6-35b-a3b",
        base_url="http://local.test/v1",
        api_key_file=None,
        api_key_env="LLAMA_CPP_API_KEY",
        max_output_tokens=16384,
        max_tokens_parameter="max_tokens",
        timeout=900.0,
    )


def test_continuation_selects_only_source_case_and_flushes_seven_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The wrapper imports the frozen attempt and writes seven independent rows."""
    cases = (
        {"case_id": "reverse_scale"},
        {"case_id": "source_selection"},
    )
    calls: list[tuple[str, int]] = []

    async def fake_attempt(
        case: dict[str, object], *, args: Namespace, attempt_index: int
    ) -> dict[str, object]:
        del args
        calls.append((str(case["case_id"]), attempt_index))
        return {"case_id": case["case_id"], "attempt_index": attempt_index}

    monkeypatch.setattr(continuation, "case_corpus_sha256", lambda: continuation.CASE_CORPUS_SHA256)
    monkeypatch.setattr(continuation, "load_case_definitions", lambda: cases)
    monkeypatch.setattr(continuation, "run_attempt", fake_attempt)
    output = tmp_path / "source-continuation.jsonl"

    asyncio.run(continuation.run_continuation(_args(output)))

    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert calls == [("source_selection", index) for index in range(7)]
    assert rows == [{"attempt_index": index, "case_id": "source_selection"} for index in range(7)]


def test_continuation_rejects_existing_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The continuation cannot append to another dataset."""
    output = tmp_path / "existing.jsonl"
    output.write_text("existing\n")
    monkeypatch.setattr(continuation, "case_corpus_sha256", lambda: continuation.CASE_CORPUS_SHA256)
    with pytest.raises(FileExistsError):
        asyncio.run(continuation.run_continuation(_args(output)))


def test_continuation_rejects_changed_corpus(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The continuation refuses to run against a changed frozen corpus."""
    monkeypatch.setattr(continuation, "case_corpus_sha256", lambda: "changed")
    with pytest.raises(RuntimeError, match="corpus hash changed"):
        asyncio.run(continuation.run_continuation(_args(tmp_path / "new.jsonl")))
