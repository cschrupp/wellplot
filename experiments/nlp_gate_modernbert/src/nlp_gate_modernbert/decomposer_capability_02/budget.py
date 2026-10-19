"""Hard call-budget enforcement for Capability-02 runs (fail closed)."""

from __future__ import annotations


class BudgetExhausted(RuntimeError):
    """Raised when an adapter would exceed its authorized high-level call budget."""


class CallBudget:
    def __init__(self, *, authorized: int) -> None:
        if authorized < 0:
            raise ValueError("authorized_budget_must_be_non_negative")
        self.authorized = authorized
        self.consumed = 0

    def remaining(self) -> int:
        return self.authorized - self.consumed

    def consume(self, n: int = 1) -> None:
        if n < 1:
            raise ValueError("consume_n_must_be_positive")
        if self.consumed + n > self.authorized:
            raise BudgetExhausted(
                f"budget_exhausted:consumed={self.consumed};authorized={self.authorized}"
            )
        self.consumed += n
