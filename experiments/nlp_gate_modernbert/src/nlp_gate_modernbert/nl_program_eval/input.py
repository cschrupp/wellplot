"""DecomposerInput boundary: utterance + ProjectedWorkspace only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nlp_gate_modernbert.mb02.contracts import ProjectedWorkspace
from nlp_gate_modernbert.mb02.workspace import project_workspace
from nlp_gate_modernbert.nl_program_eval.cases import CASE_REGISTRY, CaseRecord


@dataclass(frozen=True)
class DecomposerInput:
    """Payload a decomposer may see. No case_id / fixture_id / oracle fields."""

    utterance: str
    projected_workspace: ProjectedWorkspace

    def to_payload(self) -> dict[str, Any]:
        return {
            "utterance": self.utterance,
            "projected_workspace": self.projected_workspace.model_dump(mode="json"),
        }


FORBIDDEN_DECOMPOSER_KEYS = frozenset(
    {
        "case_id",
        "fixture_id",
        "oracle_witness_id",
        "expected_terminal",
        "gold",
        "normalized_program",
        "coverage_checklist",
        "evaluation_spec",
        "candidate_fixture_role",
        "expected_evaluation",
        "scenario",
    }
)


def build_decomposer_input(case_id: str) -> DecomposerInput:
    rec = CASE_REGISTRY[case_id]
    ws = project_workspace(rec.fixture_id)
    return DecomposerInput(utterance=rec.utterance, projected_workspace=ws)


def assert_decomposer_payload_clean(payload: dict[str, Any]) -> None:
    bad = FORBIDDEN_DECOMPOSER_KEYS.intersection(payload)
    if bad:
        raise RuntimeError(f"decomposer_payload_forbidden_keys:{sorted(bad)}")


def case_record(case_id: str) -> CaseRecord:
    return CASE_REGISTRY[case_id]
