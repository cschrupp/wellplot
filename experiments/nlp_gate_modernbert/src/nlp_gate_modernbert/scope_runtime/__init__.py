"""SCOPE-RUNTIME-01: NormalizedProgram execution over MB-02R per-task adjudicator."""

from nlp_gate_modernbert.scope_runtime.execute import execute_program
from nlp_gate_modernbert.scope_runtime.replay import replay_witnesses

__all__ = ["execute_program", "replay_witnesses"]
