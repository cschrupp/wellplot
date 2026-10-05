"""Provider-free tests for the SI-V2R SR7-P1A execution harness."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Never

import pytest
from pydantic import BaseModel
from scripts.semantic_ir_v2r_sr7_p1_live_comparison import (
    CONFIGURATION_FINGERPRINTS,
    MAX_PHYSICAL_CALLS,
    P0_SHA,
    PreflightError,
    _configuration_contract,
    _finalize_rows,
    _load_cases,
    _load_p0_contracts,
    execute_logical_attempt,
    main,
    run_matrix,
    verify_preflight,
)

from wellplot.agent.providers.base import (
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.agent.providers.response_diagnostics import (
    ProviderResponseFailureReason,
    StructuredResponseProviderError,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
P1_FIXTURE = REPO_ROOT / "tests/fixtures/semantic_ir_v2r_sr7_p1/fake_transport_sequences.json"


def _valid_payload() -> dict[str, object]:
    return json.loads(P1_FIXTURE.read_text(encoding="utf-8"))["valid_response"]


class FakeBackend:
    """Deterministic provider substitute that never opens a network connection."""

    def __init__(self, outcomes: list[object], returned_model: str = "qwen3.6-35b-a3b") -> None:
        """Store a finite response/error sequence."""
        self.outcomes = list(outcomes)
        self.calls: list[object] = []
        self.returned_model = returned_model
        self.last_metadata: dict[str, object] = {}

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[BaseModel],
    ) -> StructuredGenerationResult[BaseModel]:
        """Return the next deterministic outcome."""
        self.calls.append(request)
        outcome = self.outcomes.pop(0)
        self.last_metadata = {
            "returned_model": self.returned_model,
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            "latency_ms": 1.0,
        }
        if isinstance(outcome, BaseException):
            raise outcome
        return StructuredGenerationResult(
            value=response_model.model_validate(outcome),
            metrics=ProviderMetrics(latency_ms=1.0),
        )

    async def generate_program(self, request: object) -> Never:
        """Fail if a production-program path is accidentally exercised."""
        raise AssertionError("program call is forbidden")


class SequenceBackend(FakeBackend):
    """Named fake backend for finite retry and matrix sequences."""


def _case_context() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    corpus, gold = _load_cases(REPO_ROOT)
    contracts = _load_p0_contracts(REPO_ROOT)
    case = dict(corpus[0])
    item = contracts["schedule"]["rows"][0]
    case.update(item)
    return case, gold[case["case_id"]], contracts["mask"]


def test_preflight_authenticates_frozen_p0_without_network(tmp_path: Path) -> None:
    """Authenticate frozen P0 inputs without constructing a provider."""
    report = verify_preflight(
        REPO_ROOT,
        authorized_checkpoint=None,
        output_path=tmp_path / "evidence.jsonl",
        journal_path=tmp_path / "journal.jsonl",
        terminal_path=tmp_path / "terminal.json",
        require_exact_checkpoint=False,
        require_clean=False,
    )
    assert report["accepted_p0_sha"] == P0_SHA
    assert report["semantic_grader_sha256"]
    assert report["configuration_fingerprints"] == CONFIGURATION_FINGERPRINTS


def test_preflight_rejects_nonempty_evidence_before_provider(tmp_path: Path) -> None:
    """Reject an existing evidence population before any provider work."""
    output = tmp_path / "evidence.jsonl"
    output.write_text("existing\n", encoding="utf-8")
    with pytest.raises(PreflightError, match="non-empty"):
        verify_preflight(
            REPO_ROOT,
            authorized_checkpoint=None,
            output_path=output,
            journal_path=tmp_path / "journal.jsonl",
            terminal_path=tmp_path / "terminal.json",
            require_exact_checkpoint=False,
            require_clean=False,
        )


def test_preflight_rejects_checkpoint_mismatch_before_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject an unauthorized checkout before networking."""
    monkeypatch.setattr(
        "scripts.semantic_ir_v2r_sr7_p1_live_comparison._git",
        lambda repo_root, *args: "0" * 40 if args == ("rev-parse", "HEAD") else "",
    )
    with pytest.raises(PreflightError, match="authorized P1 checkpoint"):
        verify_preflight(
            REPO_ROOT,
            authorized_checkpoint="1" * 40,
            output_path=tmp_path / "evidence.jsonl",
            journal_path=tmp_path / "journal.jsonl",
            terminal_path=tmp_path / "terminal.json",
            require_exact_checkpoint=True,
            require_clean=False,
        )


def test_preflight_rejects_semantic_grader_hash_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject drift in the frozen semantic grader source hash."""
    original = __import__(
        "scripts.semantic_ir_v2r_sr7_p1_live_comparison", fromlist=["_artifact_hash"]
    )._artifact_hash

    def drifted(repo_root: Path, relative: Path) -> str:
        if relative.as_posix() == "scripts/semantic_ir_v2r_sr7_p0_comparison_contract.py":
            return "0" * 64
        return original(repo_root, relative)

    monkeypatch.setattr("scripts.semantic_ir_v2r_sr7_p1_live_comparison._artifact_hash", drifted)
    with pytest.raises(PreflightError, match="semantic grader source drift"):
        verify_preflight(
            REPO_ROOT,
            authorized_checkpoint=None,
            output_path=tmp_path / "evidence.jsonl",
            journal_path=tmp_path / "journal.jsonl",
            terminal_path=tmp_path / "terminal.json",
            require_exact_checkpoint=False,
            require_clean=False,
        )


def test_preflight_rejects_configuration_fingerprint_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject a configuration fingerprint that differs from P0."""
    original = _configuration_contract(REPO_ROOT)
    changed = {key: dict(value) for key, value in original.items()}
    changed["B"]["fingerprint"] = "0" * 64
    monkeypatch.setattr(
        "scripts.semantic_ir_v2r_sr7_p1_live_comparison._configuration_contract",
        lambda repo_root: changed,
    )
    with pytest.raises(PreflightError, match="configuration fingerprint drift"):
        verify_preflight(
            REPO_ROOT,
            authorized_checkpoint=None,
            output_path=tmp_path / "evidence.jsonl",
            journal_path=tmp_path / "journal.jsonl",
            terminal_path=tmp_path / "terminal.json",
            require_exact_checkpoint=False,
            require_clean=False,
        )


def test_dry_run_never_constructs_a_network_backend(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify the CLI dry-run path never constructs the network backend."""
    monkeypatch.setattr(sys, "argv", ["p1", "--output", "/tmp/p1-dry-output"])
    monkeypatch.setattr(
        "scripts.semantic_ir_v2r_sr7_p1_live_comparison.verify_preflight",
        lambda *args, **kwargs: {"accepted_p0_sha": P0_SHA},
    )
    monkeypatch.setattr(
        "scripts.semantic_ir_v2r_sr7_p1_live_comparison._HttpxStructuredBackend",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network backend built")),
    )
    main()
    assert "PRELIVE_PROVIDER_FREE" in capsys.readouterr().out


def test_initial_structured_failure_recovers_with_one_structural_retry() -> None:
    """Record initial failure and bounded structural retry recovery."""
    case, gold, mask = _case_context()
    config = _configuration_contract(REPO_ROOT)["A"]
    backend = SequenceBackend(
        [
            StructuredResponseProviderError(
                "invalid", response_reason=ProviderResponseFailureReason.INVALID_JSON
            ),
            _valid_payload(),
        ]
    )
    provenance = verify_preflight(
        REPO_ROOT,
        authorized_checkpoint=None,
        output_path=Path("/tmp/p1-test-output-a"),
        journal_path=Path("/tmp/p1-test-journal-a"),
        terminal_path=Path("/tmp/p1-test-terminal-a"),
        require_exact_checkpoint=False,
        require_clean=False,
    )
    row = asyncio.run(
        execute_logical_attempt(
            case=case,
            gold=gold,
            configuration=config,
            mask=mask,
            backend=backend,
            provenance=provenance,
            execution_order_index=0,
        )
    )
    assert len(backend.calls) == 2
    assert row["structural_retry_count"] == 1
    assert row["infrastructure_retry_count"] == 0
    assert row["initial_pydantic_status"] == "FAIL"
    assert row["retry_pydantic_status"] == "PASS"
    assert row["final_canonical_status"] == "PASS"


def test_transient_failure_uses_one_infrastructure_retry() -> None:
    """Record exactly one permitted transient infrastructure retry."""
    case, gold, mask = _case_context()
    config = _configuration_contract(REPO_ROOT)["A"]
    backend = SequenceBackend(
        [
            ProviderRequestError(ProviderFailureCategory.TRANSPORT, "transient"),
            _valid_payload(),
        ]
    )
    provenance = verify_preflight(
        REPO_ROOT,
        authorized_checkpoint=None,
        output_path=Path("/tmp/p1-test-output-b"),
        journal_path=Path("/tmp/p1-test-journal-b"),
        terminal_path=Path("/tmp/p1-test-terminal-b"),
        require_exact_checkpoint=False,
        require_clean=False,
    )
    row = asyncio.run(
        execute_logical_attempt(
            case=case,
            gold=gold,
            configuration=config,
            mask=mask,
            backend=backend,
            provenance=provenance,
            execution_order_index=0,
        )
    )
    assert len(backend.calls) == 2
    assert row["infrastructure_retry_count"] == 1
    assert row["structural_retry_count"] == 0


def test_retry_limits_never_allow_a_fourth_call() -> None:
    """Stop after the three-call physical ceiling."""
    case, gold, mask = _case_context()
    config = _configuration_contract(REPO_ROOT)["A"]
    backend = SequenceBackend(
        [
            ProviderRequestError(ProviderFailureCategory.TRANSPORT, "transient"),
            StructuredResponseProviderError(
                "invalid", response_reason=ProviderResponseFailureReason.INVALID_JSON
            ),
            StructuredResponseProviderError(
                "invalid", response_reason=ProviderResponseFailureReason.INVALID_JSON
            ),
            _valid_payload(),
        ]
    )
    provenance = verify_preflight(
        REPO_ROOT,
        authorized_checkpoint=None,
        output_path=Path("/tmp/p1-test-output-c"),
        journal_path=Path("/tmp/p1-test-journal-c"),
        terminal_path=Path("/tmp/p1-test-terminal-c"),
        require_exact_checkpoint=False,
        require_clean=False,
    )
    row = asyncio.run(
        execute_logical_attempt(
            case=case,
            gold=gold,
            configuration=config,
            mask=mask,
            backend=backend,
            provenance=provenance,
            execution_order_index=0,
        )
    )
    assert len(backend.calls) == MAX_PHYSICAL_CALLS
    assert row["final_canonical_status"] == "FAIL"


def test_returned_model_drift_is_terminal() -> None:
    """Treat an unexpected returned model identity as terminal drift."""
    case, gold, mask = _case_context()
    config = _configuration_contract(REPO_ROOT)["A"]
    backend = SequenceBackend([_valid_payload()], returned_model="unexpected-model")
    provenance = verify_preflight(
        REPO_ROOT,
        authorized_checkpoint=None,
        output_path=Path("/tmp/p1-test-output-d"),
        journal_path=Path("/tmp/p1-test-journal-d"),
        terminal_path=Path("/tmp/p1-test-terminal-d"),
        require_exact_checkpoint=False,
        require_clean=False,
    )
    row = asyncio.run(
        execute_logical_attempt(
            case=case,
            gold=gold,
            configuration=config,
            mask=mask,
            backend=backend,
            provenance=provenance,
            execution_order_index=0,
        )
    )
    assert len(backend.calls) == 1
    assert row["terminal_row_status"] == "CONFIGURATION_DRIFT"


def test_run_matrix_consumes_exact_96_rows_and_writes_only_staged_journal(tmp_path: Path) -> None:
    """Consume the frozen schedule and finalize exactly 96 rows."""
    a_backend = SequenceBackend([_valid_payload()] * 48)
    b_backend = SequenceBackend(
        [_valid_payload()] * 48, returned_model="nvidia/nemotron-3-super-120b-a12b"
    )
    output = tmp_path / "evidence.jsonl"
    journal = tmp_path / "journal.jsonl"
    terminal = tmp_path / "terminal.json"
    result = asyncio.run(
        run_matrix(
            repo_root=REPO_ROOT,
            backends={"A": a_backend, "B": b_backend},
            output_path=output,
            journal_path=journal,
            terminal_path=terminal,
            require_clean=False,
        )
    )
    assert len(a_backend.calls) == 48
    assert len(b_backend.calls) == 48
    assert result["decision"] in {
        "CONFIGURATION_A_DIRECTIONALLY_BETTER",
        "CONFIGURATION_B_DIRECTIONALLY_BETTER",
        "NO_CLEAR_DIRECTIONAL_DIFFERENCE",
    }
    assert output.exists()
    assert len(output.read_text(encoding="utf-8").splitlines()) == 96
    assert not terminal.exists()


def test_schedule_preserves_even_odd_ordering() -> None:
    """Preserve the frozen A/B order for even and odd case indexes."""
    schedule = _load_p0_contracts(REPO_ROOT)["schedule"]["rows"]
    assert [row["configuration_id"] for row in schedule[:4]] == ["A", "B", "B", "A"]
    assert [row["attempt_index"] for row in schedule[:4]] == [0, 0, 1, 1]
    assert [row["configuration_id"] for row in schedule[4:8]] == ["B", "A", "A", "B"]
    assert [row["attempt_index"] for row in schedule[4:8]] == [0, 0, 1, 1]
    assert [row["execution_order_index"] for row in schedule] == list(range(96))


def test_run_matrix_preserves_partial_journal_on_infrastructure_exhaustion(tmp_path: Path) -> None:
    """Preserve partial evidence and stop on exhausted infrastructure retry."""
    backend = SequenceBackend(
        [ProviderRequestError(ProviderFailureCategory.TRANSPORT, "transient")] * 3
    )
    output = tmp_path / "evidence.jsonl"
    journal = tmp_path / "journal.jsonl"
    terminal = tmp_path / "terminal.json"
    result = asyncio.run(
        run_matrix(
            repo_root=REPO_ROOT,
            backends={"A": backend, "B": backend},
            output_path=output,
            journal_path=journal,
            terminal_path=terminal,
            require_clean=False,
        )
    )
    assert result["decision"] == "INCONCLUSIVE_INFRASTRUCTURE"
    assert journal.exists()
    assert terminal.exists()
    assert not output.exists()


def test_authentication_failure_is_infrastructure_terminal(tmp_path: Path) -> None:
    """Stop on credential failure without retrying or calling the other arm."""
    a_backend = SequenceBackend(
        [ProviderRequestError(ProviderFailureCategory.AUTHENTICATION, "credential failure")]
    )
    b_backend = SequenceBackend(
        [_valid_payload()], returned_model="nvidia/nemotron-3-super-120b-a12b"
    )
    result = asyncio.run(
        run_matrix(
            repo_root=REPO_ROOT,
            backends={"A": a_backend, "B": b_backend},
            output_path=tmp_path / "evidence.jsonl",
            journal_path=tmp_path / "journal.jsonl",
            terminal_path=tmp_path / "terminal.json",
            require_clean=False,
        )
    )
    assert result["decision"] == "INCONCLUSIVE_INFRASTRUCTURE"
    assert len(a_backend.calls) == 1
    assert len(b_backend.calls) == 0


def test_run_matrix_stops_on_configuration_drift(tmp_path: Path) -> None:
    """Stop before the next scheduled call when model identity drifts."""
    a_backend = SequenceBackend([_valid_payload()], returned_model="wrong-model")
    b_backend = SequenceBackend(
        [_valid_payload()], returned_model="nvidia/nemotron-3-super-120b-a12b"
    )
    result = asyncio.run(
        run_matrix(
            repo_root=REPO_ROOT,
            backends={"A": a_backend, "B": b_backend},
            output_path=tmp_path / "evidence.jsonl",
            journal_path=tmp_path / "journal.jsonl",
            terminal_path=tmp_path / "terminal.json",
            require_clean=False,
        )
    )
    assert result["decision"] == "INCONCLUSIVE_CONFIGURATION_DRIFT"
    assert len(a_backend.calls) == 1
    assert len(b_backend.calls) == 0


def test_completed_rows_exclude_secrets_and_hidden_reasoning(tmp_path: Path) -> None:
    """Keep credentials, headers, and hidden reasoning out of evidence."""
    a_backend = SequenceBackend([_valid_payload()] * 48)
    b_backend = SequenceBackend(
        [_valid_payload()] * 48, returned_model="nvidia/nemotron-3-super-120b-a12b"
    )
    output = tmp_path / "evidence.jsonl"
    asyncio.run(
        run_matrix(
            repo_root=REPO_ROOT,
            backends={"A": a_backend, "B": b_backend},
            output_path=output,
            journal_path=tmp_path / "journal.jsonl",
            terminal_path=tmp_path / "terminal.json",
            require_clean=False,
        )
    )
    serialized = output.read_text(encoding="utf-8").lower()
    assert "authorization_headers" not in serialized
    assert "reasoning_text" not in serialized
    assert "bearer" not in serialized
    assert "nvapi-" not in serialized
    assert len(serialized.splitlines()) == 96


def test_finalizer_rejects_missing_required_evidence_fields(tmp_path: Path) -> None:
    """Fail closed when a staged evidence row is incomplete."""
    contracts = _load_p0_contracts(REPO_ROOT)
    provenance = verify_preflight(
        REPO_ROOT,
        authorized_checkpoint=None,
        output_path=tmp_path / "output",
        journal_path=tmp_path / "journal",
        terminal_path=tmp_path / "terminal",
        require_exact_checkpoint=False,
        require_clean=False,
    )
    result = _finalize_rows(REPO_ROOT, [{}], provenance, contracts)
    assert result["decision"] == "INCONCLUSIVE_EVIDENCE"
