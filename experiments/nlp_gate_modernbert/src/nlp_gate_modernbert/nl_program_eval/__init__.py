"""NL-PROGRAM-EVAL-HARNESS-01: Q3 evaluator for frozen ScopeNormalizedProgram candidates."""

from nlp_gate_modernbert.nl_program_eval.evaluate import EvaluationResult, evaluate_frozen
from nlp_gate_modernbert.nl_program_eval.freeze import FreezeFailure, FrozenCandidate, freeze_candidate

__all__ = [
    "EvaluationResult",
    "FreezeFailure",
    "FrozenCandidate",
    "evaluate_frozen",
    "freeze_candidate",
]
