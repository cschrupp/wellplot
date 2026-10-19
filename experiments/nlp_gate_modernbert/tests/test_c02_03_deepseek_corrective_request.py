"""Offline: corrective DeepSeek request pins max_tokens + reasoning.effort."""

from __future__ import annotations

from nlp_gate_modernbert.decomposer_capability_02.budget import CallBudget
from nlp_gate_modernbert.decomposer_capability_02.contracts import (
    ModelPathId,
    SemanticDecomposerRequest,
)
from nlp_gate_modernbert.decomposer_capability_02.openrouter_adapter import OpenRouterAdapter
from nlp_gate_modernbert.decomposer_capability_02.registry import (
    DEEPSEEK_PROVIDER_ORDER,
    OPENROUTER_DEEPSEEK_V41_FLASH_1017,
)


def test_corrective_request_body_pins_budget_and_reasoning() -> None:
    adapter = OpenRouterAdapter(
        model_path=ModelPathId.DEEPSEEK_V41_FLASH_1017,
        openrouter_model_id=OPENROUTER_DEEPSEEK_V41_FLASH_1017,
        budget=CallBudget(authorized=1),
        transport=lambda _body: {},
        temperature=0.0,
        max_tokens=4096,
        include_reasoning=False,
        reasoning={"effort": "low"},
        provider_order=list(DEEPSEEK_PROVIDER_ORDER),
        allow_fallbacks=False,
        require_provider_pin=True,
    )
    body = adapter.build_request(
        SemanticDecomposerRequest(
            utterance="u",
            projected_workspace_json="{}",
            case_id="D5GAP-0085",
        )
    )
    assert body["model"] == OPENROUTER_DEEPSEEK_V41_FLASH_1017
    assert body["max_tokens"] == 4096
    assert body["include_reasoning"] is False
    assert body["reasoning"] == {"effort": "low"}
    assert body["response_format"] == {"type": "json_object"}
    assert body["provider"] == {
        "order": ["Morph"],
        "allow_fallbacks": False,
        "require_parameters": True,
    }
