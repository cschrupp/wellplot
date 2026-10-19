"""Four-path adapter registry for C02-02 qualification."""

from __future__ import annotations

from nlp_gate_modernbert.decomposer_capability_02.budget import CallBudget, ExecutionBudgets
from nlp_gate_modernbert.decomposer_capability_02.contracts import (
    AdapterCapability,
    ModelPathId,
)
from nlp_gate_modernbert.decomposer_capability_02.cost_card import CostCard, load_cost_card
from nlp_gate_modernbert.decomposer_capability_02.local_qwen_adapter import LocalQwenAdapter
from nlp_gate_modernbert.decomposer_capability_02.openrouter_adapter import (
    ForbiddenLiveTransport,
    OpenRouterAdapter,
)

# C02-03 design: preferred Google AI Studio; no silent fallback.
GEMINI_PROVIDER_ORDER = ("Google AI Studio",)

# Joint smoke: freeze Morph from C02-02 DeepSeek endpoint snapshot
# (response_format + structured_outputs; no silent fallback).
DEEPSEEK_PROVIDER_ORDER = ("Morph",)

# Verified via OpenRouter public catalog GET /api/v1/models (not inference).
OPENROUTER_GEMINI_4_ARGON = "google/gemini-4-argon"
OPENROUTER_DEEPSEEK_V41_FLASH_1017 = "deepseek/deepseek-v4.1-flash-1017"

HF_QWEN3_4B_INSTRUCT_2507 = "Qwen/Qwen3-4B-Instruct-2507"
HF_QWEN3_4B_THINKING_2507 = "Qwen/Qwen3-4B-Thinking-2507"


CAPABILITIES: dict[ModelPathId, AdapterCapability] = {
    ModelPathId.GEMINI_4_ARGON: AdapterCapability(
        model_path=ModelPathId.GEMINI_4_ARGON,
        transport="openrouter_openai_compatible",
        openrouter_model_id=OPENROUTER_GEMINI_4_ARGON,
        hf_model_id=None,
        structured_output_mode="response_format.json_object_plus_freeze_candidate",
        reasoning_handling="optional_include_reasoning_field_and_tag_strip; grade_final_answer_only",
        hard_xgrammar_mask=False,
        notes=(
            "Not identical to Pilot Run 1 XGrammar hard mask",
            "Providers: Google AI Studio, Google Vertex (see endpoints snapshot)",
        ),
    ),
    ModelPathId.DEEPSEEK_V41_FLASH_1017: AdapterCapability(
        model_path=ModelPathId.DEEPSEEK_V41_FLASH_1017,
        transport="openrouter_openai_compatible",
        openrouter_model_id=OPENROUTER_DEEPSEEK_V41_FLASH_1017,
        hf_model_id=None,
        structured_output_mode="response_format.json_object_plus_freeze_candidate",
        reasoning_handling="optional_reasoning_field_and_tag_strip; grade_final_answer_only",
        hard_xgrammar_mask=False,
        notes=(
            "Budget-capability reference; not the frontier ceiling",
            "Provider pricing varies; see endpoints snapshot",
            "JSON-schema enforcement may vary by provider",
        ),
    ),
    ModelPathId.QWEN3_4B_INSTRUCT_2507: AdapterCapability(
        model_path=ModelPathId.QWEN3_4B_INSTRUCT_2507,
        transport="local_hf_transformers_contract",
        openrouter_model_id=None,
        hf_model_id=HF_QWEN3_4B_INSTRUCT_2507,
        structured_output_mode="prompted_json_plus_optional_future_constraint_adapter",
        reasoning_handling="thinking_disabled",
        hard_xgrammar_mask=False,
        notes=(
            "Non-thinking Instruct-2507 variant",
            "Local weights not loaded in C02-02; checkpoint presence deferred",
            "Tokenizer-specific XGrammar adapter requires separate future validation",
        ),
    ),
    ModelPathId.QWEN3_4B_THINKING_2507: AdapterCapability(
        model_path=ModelPathId.QWEN3_4B_THINKING_2507,
        transport="local_hf_transformers_contract",
        openrouter_model_id=None,
        hf_model_id=HF_QWEN3_4B_THINKING_2507,
        structured_output_mode="prompted_json_plus_optional_future_constraint_adapter",
        reasoning_handling="thinking_enabled_final_answer_only_for_grading",
        hard_xgrammar_mask=False,
        notes=(
            "Thinking-only 2507 variant; not a prompt mode of Instruct",
            "Local weights not loaded in C02-02; checkpoint presence deferred",
        ),
    ),
}


def build_mocked_openrouter_adapter(
    model_path: ModelPathId,
    *,
    budget: CallBudget,
    transport,
) -> OpenRouterAdapter:
    cap = CAPABILITIES[model_path]
    assert cap.openrouter_model_id is not None
    return OpenRouterAdapter(
        model_path=model_path,
        openrouter_model_id=cap.openrouter_model_id,
        budget=budget,
        transport=transport,
        include_reasoning=False,
    )


def build_mocked_local_adapter(
    model_path: ModelPathId,
    *,
    budget: CallBudget,
    generate_fn,
) -> LocalQwenAdapter:
    cap = CAPABILITIES[model_path]
    assert cap.hf_model_id is not None
    return LocalQwenAdapter(
        model_path=model_path,
        hf_model_id=cap.hf_model_id,
        budget=budget,
        generate_fn=generate_fn,
        thinking_enabled=(model_path == ModelPathId.QWEN3_4B_THINKING_2507),
    )


def default_live_forbidden_openrouter(
    model_path: ModelPathId,
    *,
    budget: CallBudget,
) -> OpenRouterAdapter:
    return build_mocked_openrouter_adapter(
        model_path, budget=budget, transport=ForbiddenLiveTransport()
    )


def build_gemini_ceiling_prep_adapter(
    *,
    budgets: ExecutionBudgets,
    transport,
    cost_card: CostCard | None = None,
    provider_order: tuple[str, ...] = GEMINI_PROVIDER_ORDER,
) -> OpenRouterAdapter:
    """Pinned Gemini adapter for execution preparation / future authorized runs."""
    card = cost_card or load_cost_card(
        openrouter_model_id=OPENROUTER_GEMINI_4_ARGON,
        pinned_provider=provider_order[0],
    )
    return OpenRouterAdapter(
        model_path=ModelPathId.GEMINI_4_ARGON,
        openrouter_model_id=OPENROUTER_GEMINI_4_ARGON,
        budgets=budgets,
        transport=transport,
        include_reasoning=False,
        provider_order=list(provider_order),
        allow_fallbacks=False,
        require_provider_pin=True,
        max_transport_attempts_per_logical_call=2,
        cost_card=card,
    )


def build_deepseek_budget_adapter(
    *,
    budgets: ExecutionBudgets,
    transport,
    cost_card: CostCard | None = None,
    provider_order: tuple[str, ...] = DEEPSEEK_PROVIDER_ORDER,
) -> OpenRouterAdapter:
    """Pinned DeepSeek V4.1 Flash adapter (budget reference)."""
    card = cost_card or load_cost_card(
        openrouter_model_id=OPENROUTER_DEEPSEEK_V41_FLASH_1017,
        pinned_provider=provider_order[0],
    )
    return OpenRouterAdapter(
        model_path=ModelPathId.DEEPSEEK_V41_FLASH_1017,
        openrouter_model_id=OPENROUTER_DEEPSEEK_V41_FLASH_1017,
        budgets=budgets,
        transport=transport,
        include_reasoning=False,
        provider_order=list(provider_order),
        allow_fallbacks=False,
        require_provider_pin=True,
        max_transport_attempts_per_logical_call=2,
        cost_card=card,
    )
