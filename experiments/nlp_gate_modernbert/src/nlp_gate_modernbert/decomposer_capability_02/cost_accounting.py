"""Dual cost fields: pre-run estimate vs OpenRouter-reported usage cost."""

from __future__ import annotations

from typing import Any

from nlp_gate_modernbert.decomposer_capability_02.cost_card import CostCard


def provider_reported_usd(raw_usage: dict[str, Any] | None) -> float | None:
    if not raw_usage:
        return None
    cost = raw_usage.get("cost")
    if cost is None:
        return None
    return float(cost)


def dual_cost_record(
    *,
    cost_card: CostCard,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    raw_usage: dict[str, Any] | None,
) -> dict[str, Any]:
    estimated = cost_card.estimate_usd(
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
    )
    reported = provider_reported_usd(raw_usage)
    ratio = None
    if estimated and reported is not None and estimated > 0:
        ratio = reported / estimated
    return {
        "estimated_usd_from_pre_run_cost_card": estimated,
        "provider_reported_usd": reported,
        "cost_card_rates_usd_per_1m": {
            "prompt": cost_card.rate.prompt_usd_per_1m,
            "completion": cost_card.rate.completion_usd_per_1m,
            "provider": cost_card.pinned_provider,
            "tag": cost_card.rate.tag,
        },
        "reported_over_estimate_ratio": ratio,
        "accounting_rule": (
            "Use provider_reported_usd as the observed charge for cost-effectiveness. "
            "Retain estimated_usd_from_pre_run_cost_card for comparison only. "
            "Do not overwrite historical smoke rows."
        ),
    }
