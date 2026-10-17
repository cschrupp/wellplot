"""Oracle material access — capability-locked to FrozenCandidate (Q2)."""

from __future__ import annotations

from typing import Any

from nlp_gate_modernbert.nl_program_eval.freeze import FrozenCandidate, require_frozen
from nlp_gate_modernbert.paths import EVIDENCE_DIR
from nlp_gate_modernbert.scope_runtime.contracts import ScopeNormalizedProgram
from nlp_gate_modernbert.scope_runtime.execute import parse_program_from_witness
from nlp_gate_modernbert.scope_runtime.replay import load_witnesses

WITNESS_PATH = EVIDENCE_DIR / "scope_contract_design_01.json"


def load_oracle_program(
    frozen: FrozenCandidate,
    case_id: str,
    *,
    witness_path: Any = None,
) -> ScopeNormalizedProgram:
    """Load oracle NormalizedProgram for ``case_id``.

    Requires a verified ``FrozenCandidate``. There is no public case_id-only path.
    """
    require_frozen(frozen)
    path = witness_path or WITNESS_PATH
    witnesses = {w["case_id"]: w for w in load_witnesses(path)}
    if case_id not in witnesses:
        raise RuntimeError(f"unknown_oracle_witness:{case_id}")
    raw = witnesses[case_id]["normalized_program"]
    return parse_program_from_witness(raw)
