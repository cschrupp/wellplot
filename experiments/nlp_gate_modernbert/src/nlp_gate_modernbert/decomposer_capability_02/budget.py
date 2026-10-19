"""Separate logical-call, transport-attempt, and cost budgets (fail closed)."""

from __future__ import annotations

from dataclasses import dataclass


class BudgetExhausted(RuntimeError):
    """Raised when a budget would be exceeded."""


class CallBudget:
    """Backward-compatible single counter (logical high-level calls)."""

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


@dataclass
class ExecutionBudgets:
    """Three independent counters for Gemini ceiling execution prep/run."""

    logical_calls: CallBudget
    transport_attempts: CallBudget
    estimated_usd: float
    estimated_usd_cap: float

    @classmethod
    def for_six_case_ceiling(
        cls,
        *,
        logical_authorized: int = 6,
        transport_authorized: int = 12,
        estimated_usd_cap: float = 5.0,
    ) -> ExecutionBudgets:
        return cls(
            logical_calls=CallBudget(authorized=logical_authorized),
            transport_attempts=CallBudget(authorized=transport_authorized),
            estimated_usd=0.0,
            estimated_usd_cap=estimated_usd_cap,
        )

    def charge_usd(self, amount: float) -> None:
        if amount < 0:
            raise ValueError("usd_charge_must_be_non_negative")
        if self.estimated_usd + amount > self.estimated_usd_cap + 1e-12:
            raise BudgetExhausted(
                f"cost_budget_exhausted:estimated={self.estimated_usd};"
                f"charge={amount};cap={self.estimated_usd_cap}"
            )
        self.estimated_usd += amount
