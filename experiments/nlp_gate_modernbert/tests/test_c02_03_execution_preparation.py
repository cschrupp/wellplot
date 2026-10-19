"""C02-03 execution preparation — mocked only; zero billable inference."""

from __future__ import annotations

import json
import os

import pytest

from nlp_gate_modernbert.decomposer_capability_02.api_key import (
    ApiKeyError,
    inspect_api_key_presence,
    load_api_key,
)
from nlp_gate_modernbert.decomposer_capability_02.budget import (
    BudgetExhausted,
    ExecutionBudgets,
)
from nlp_gate_modernbert.decomposer_capability_02.contracts import SemanticDecomposerRequest
from nlp_gate_modernbert.decomposer_capability_02.cost_card import load_cost_card
from nlp_gate_modernbert.decomposer_capability_02.registry import (
    GEMINI_PROVIDER_ORDER,
    OPENROUTER_GEMINI_4_ARGON,
    build_gemini_ceiling_prep_adapter,
)
from nlp_gate_modernbert.paths import EVIDENCE_DIR

PREP = EVIDENCE_DIR / "decomposer_capability_02" / "c02_03_execution_prep"


def _req() -> SemanticDecomposerRequest:
    return SemanticDecomposerRequest(
        utterance="x",
        projected_workspace_json="{}",
        case_id="D5GAP-0096",
    )


def test_request_includes_provider_pin_without_fallbacks() -> None:
    budgets = ExecutionBudgets.for_six_case_ceiling()
    adapter = build_gemini_ceiling_prep_adapter(
        budgets=budgets, transport=lambda body: (_ for _ in ()).throw(RuntimeError("no"))
    )
    body = adapter.build_request(_req())
    assert body["model"] == OPENROUTER_GEMINI_4_ARGON
    assert body["provider"]["order"] == list(GEMINI_PROVIDER_ORDER)
    assert body["provider"]["allow_fallbacks"] is False


def test_provider_mismatch_fails_closed_and_keeps_usage() -> None:
    budgets = ExecutionBudgets.for_six_case_ceiling()

    def transport(_body):
        return {
            "provider": "SomeOtherProvider",
            "model": OPENROUTER_GEMINI_4_ARGON,
            "choices": [{"finish_reason": "stop", "message": {"content": '{"tasks":[]}'}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14},
        }

    adapter = build_gemini_ceiling_prep_adapter(budgets=budgets, transport=transport)
    out = adapter.generate(_req())
    assert out.error and "provider_mismatch" in out.error
    assert out.prompt_tokens == 11
    assert out.completion_tokens == 3
    assert out.metadata["raw_usage"]["prompt_tokens"] == 11
    assert budgets.logical_calls.consumed == 1
    assert budgets.transport_attempts.consumed == 1
    assert budgets.estimated_usd > 0


def test_parse_failure_preserves_usage_and_charges_cost() -> None:
    budgets = ExecutionBudgets.for_six_case_ceiling()

    def transport(_body):
        return {
            "provider": "Google AI Studio",
            "choices": [{"finish_reason": "stop", "message": {"content": "NOT JSON"}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 7, "total_tokens": 27},
        }

    adapter = build_gemini_ceiling_prep_adapter(budgets=budgets, transport=transport)
    out = adapter.generate(_req())
    assert out.error and out.error.startswith("parse_error:")
    assert out.prompt_tokens == 20
    assert out.completion_tokens == 7
    assert out.metadata["raw_usage"]["total_tokens"] == 27
    assert budgets.estimated_usd > 0


def test_transport_retry_then_exhaustion_counts_attempts() -> None:
    budgets = ExecutionBudgets.for_six_case_ceiling(transport_authorized=4)
    calls = {"n": 0}

    def transport(_body):
        calls["n"] += 1
        raise TimeoutError("HTTP_503 upstream timeout")

    adapter = build_gemini_ceiling_prep_adapter(budgets=budgets, transport=transport)
    out = adapter.generate(_req())
    assert calls["n"] == 2
    assert budgets.logical_calls.consumed == 1
    assert budgets.transport_attempts.consumed == 2
    assert out.error and "TimeoutError" in out.error


def test_separate_budgets_independent() -> None:
    budgets = ExecutionBudgets.for_six_case_ceiling(
        logical_authorized=1, transport_authorized=1, estimated_usd_cap=0.0000001
    )

    def transport(_body):
        return {
            "provider": "Google AI Studio",
            "choices": [{"finish_reason": "stop", "message": {"content": '{"tasks":[]}'}}],
            "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000, "total_tokens": 2_000_000},
        }

    adapter = build_gemini_ceiling_prep_adapter(budgets=budgets, transport=transport)
    with pytest.raises(BudgetExhausted):
        adapter.generate(_req())


def test_cost_card_from_c02_02_snapshot_no_inference() -> None:
    card = load_cost_card(
        openrouter_model_id=OPENROUTER_GEMINI_4_ARGON,
        pinned_provider="Google AI Studio",
    )
    assert card.pinned_provider == "Google AI Studio"
    assert card.to_json()["billable_inference_calls"] == 0
    assert card.estimate_usd(prompt_tokens=1_000_000, completion_tokens=0) > 0


def test_api_key_presence_does_not_expose_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    absent = inspect_api_key_presence(load_dotenv=False)
    assert absent.present is False
    assert absent.to_json()["OPENROUTER_API_KEY_PRESENT"] is False
    with pytest.raises(ApiKeyError):
        load_api_key(load_dotenv=False)

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-SECRETVALUE")
    present = inspect_api_key_presence(load_dotenv=False)
    assert present.present is True
    dumped = json.dumps(present.to_json())
    assert "SECRETVALUE" not in dumped
    assert "length" not in dumped
    assert present.to_json()["OPENROUTER_API_KEY_PRESENT"] is True
    key = load_api_key(load_dotenv=False)
    assert key.startswith("sk-or-")
    del key


def test_silent_fallback_constructor_rejected() -> None:
    from nlp_gate_modernbert.decomposer_capability_02.contracts import ModelPathId
    from nlp_gate_modernbert.decomposer_capability_02.openrouter_adapter import (
        OpenRouterAdapter,
    )

    budgets = ExecutionBudgets.for_six_case_ceiling()
    with pytest.raises(ValueError, match="silent_provider_fallback_forbidden"):
        OpenRouterAdapter(
            model_path=ModelPathId.GEMINI_4_ARGON,
            openrouter_model_id=OPENROUTER_GEMINI_4_ARGON,
            budgets=budgets,
            transport=lambda b: {},
            provider_order=["Google AI Studio"],
            allow_fallbacks=True,
            require_provider_pin=True,
        )


def test_prep_readiness_report_exists() -> None:
    report = json.loads((PREP / "pre_execution_readiness.json").read_text())
    assert report["slice"] == "C02-03-EXECUTION-PREPARATION"
    assert report["live_inference_calls"] == 0
    assert report["billable_openrouter_calls"] == 0
    assert report["inference_authorized"] is False
