"""Post-freeze evaluation orchestration. Oracle access requires FrozenCandidate."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.nl_program_eval.cases import CASE_REGISTRY
from nlp_gate_modernbert.nl_program_eval.compare import CompareResult, compare_programs
from nlp_gate_modernbert.nl_program_eval.freeze import (
    FreezeFailure,
    FrozenCandidate,
    freeze_candidate,
    require_frozen,
)
from nlp_gate_modernbert.nl_program_eval.input import build_decomposer_input
from nlp_gate_modernbert.nl_program_eval.oracle import load_oracle_program


@dataclass
class EvaluationResult:
    case_id: str
    schema_valid: bool
    freeze_status: str
    candidate_digest: str | None
    canonicalization_version: str | None
    oracle_access_before_freeze: bool
    oracle_access_enabled_after_freeze: bool | None
    runtime_gate: dict[str, Any] = field(default_factory=dict)
    q3_comparison: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)
    failure_labels: list[str] = field(default_factory=list)
    semantically_equivalent: bool | None = None
    freeze_detail: str | None = None
    decomposer_input_keys: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_raw_candidate(
    case_id: str,
    raw_candidate: dict[str, Any] | str | bytes,
) -> EvaluationResult:
    """Freeze then evaluate. Oracle material is unreachable before FrozenCandidate."""
    d_in = build_decomposer_input(case_id)
    payload = d_in.to_payload()

    frozen = freeze_candidate(raw_candidate)
    if isinstance(frozen, FreezeFailure):
        return EvaluationResult(
            case_id=case_id,
            schema_valid=False,
            freeze_status=frozen.failure,
            candidate_digest=None,
            canonicalization_version=None,
            oracle_access_before_freeze=False,
            oracle_access_enabled_after_freeze=False,
            failure_labels=[frozen.failure],
            semantically_equivalent=False,
            freeze_detail=frozen.detail,
            decomposer_input_keys=sorted(payload.keys()),
        )

    return evaluate_frozen(frozen, case_id=case_id, decomposer_input_keys=sorted(payload.keys()))


def evaluate_frozen(
    frozen: FrozenCandidate,
    *,
    case_id: str,
    decomposer_input_keys: list[str] | None = None,
) -> EvaluationResult:
    require_frozen(frozen)
    case = CASE_REGISTRY[case_id]
    initial = build_decomposer_input(case_id).projected_workspace
    # Oracle load is capability-locked: FrozenCandidate is a required argument.
    oracle = load_oracle_program(frozen, case.oracle_witness_id)

    cmp: CompareResult = compare_programs(frozen, oracle, initial, case)

    return EvaluationResult(
        case_id=case_id,
        schema_valid=True,
        freeze_status="FROZEN",
        candidate_digest=frozen.sha256,
        canonicalization_version=frozen.canonicalization_version,
        oracle_access_before_freeze=False,
        oracle_access_enabled_after_freeze=frozen.oracle_access_enabled,
        runtime_gate={
            "candidate_terminal": cmp.candidate_terminal,
            "oracle_terminal": cmp.oracle_terminal,
            "terminals_match": cmp.candidate_terminal == cmp.oracle_terminal
            or (
                cmp.candidate_terminal.get("authority") == cmp.oracle_terminal.get("authority")
                and cmp.candidate_terminal.get("status") == cmp.oracle_terminal.get("status")
            ),
        },
        q3_comparison={
            "coverage": cmp.coverage,
            "alignment": cmp.alignment,
            "benign_redundant_task_ids": cmp.benign_redundant_task_ids,
            "observed_out_of_scope": cmp.observed_out_of_scope,
        },
        diagnostics=list(cmp.diagnostics),
        failure_labels=list(cmp.failure_labels),
        semantically_equivalent=cmp.semantically_equivalent,
        decomposer_input_keys=decomposer_input_keys or ["utterance", "projected_workspace"],
    )


def load_candidate_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
