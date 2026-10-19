"""Local Qwen3-4B adapter contracts — qualification only; no weight load in C02-02."""

from __future__ import annotations

from typing import Any, Callable

from nlp_gate_modernbert.decomposer_capability_02.budget import CallBudget
from nlp_gate_modernbert.decomposer_capability_02.contracts import (
    ModelPathId,
    NormalizedGeneration,
    SemanticDecomposerRequest,
)
from nlp_gate_modernbert.decomposer_capability_02.normalize import (
    extract_json_object_text,
    strip_reasoning_blocks,
)
from nlp_gate_modernbert.decomposer_pilot import prompt_contract

LocalGenerateFn = Callable[[dict[str, Any]], dict[str, Any]]


class LocalQwenAdapter:
    """Shared local path using the frozen prompt contract + injectable generate fn."""

    def __init__(
        self,
        *,
        model_path: ModelPathId,
        hf_model_id: str,
        budget: CallBudget,
        generate_fn: LocalGenerateFn,
        thinking_enabled: bool,
        max_new_tokens: int = 1024,
    ) -> None:
        self.model_path = model_path
        self.hf_model_id = hf_model_id
        self.budget = budget
        self.generate_fn = generate_fn
        self.thinking_enabled = thinking_enabled
        self.max_new_tokens = max_new_tokens

    def build_local_request(self, req: SemanticDecomposerRequest) -> dict[str, Any]:
        messages = req.model_facing_messages(
            system_prompt=prompt_contract.SYSTEM_PROMPT,
            user_template=prompt_contract.USER_TEMPLATE,
        )
        return {
            "hf_model_id": self.hf_model_id,
            "messages": messages,
            "max_new_tokens": self.max_new_tokens,
            "do_sample": False,
            "temperature": 0.0,
            "enable_thinking": self.thinking_enabled,
            # Hard XGrammar mask is a separate future constraint adapter (not assumed).
            "hard_xgrammar_mask": False,
        }

    def generate(self, req: SemanticDecomposerRequest) -> NormalizedGeneration:
        self.budget.consume(1)
        body = self.build_local_request(req)
        try:
            payload = self.generate_fn(body)
        except Exception as exc:  # noqa: BLE001
            return NormalizedGeneration(
                model_path=self.model_path,
                raw_text="",
                final_answer_text="",
                reasoning_text=None,
                finish_reason=None,
                prompt_tokens=None,
                completion_tokens=None,
                reasoning_tokens=None,
                total_tokens=None,
                error=f"local_generate_error:{type(exc).__name__}:{exc}",
                metadata={"hf_model_id": self.hf_model_id},
            )

        raw_text = payload.get("text") or ""
        cleaned, reasoning = strip_reasoning_blocks(raw_text)
        if self.thinking_enabled and payload.get("reasoning_text"):
            reasoning = payload.get("reasoning_text")
        try:
            final = extract_json_object_text(cleaned)
        except Exception as exc:  # noqa: BLE001
            return NormalizedGeneration(
                model_path=self.model_path,
                raw_text=raw_text,
                final_answer_text="",
                reasoning_text=reasoning,
                finish_reason=payload.get("finish_reason"),
                prompt_tokens=payload.get("prompt_tokens"),
                completion_tokens=payload.get("completion_tokens"),
                reasoning_tokens=payload.get("reasoning_tokens"),
                total_tokens=payload.get("total_tokens"),
                error=f"parse_error:{type(exc).__name__}:{exc}",
                metadata={"hf_model_id": self.hf_model_id},
            )
        return NormalizedGeneration(
            model_path=self.model_path,
            raw_text=raw_text,
            final_answer_text=final,
            reasoning_text=reasoning,
            finish_reason=payload.get("finish_reason"),
            prompt_tokens=payload.get("prompt_tokens"),
            completion_tokens=payload.get("completion_tokens"),
            reasoning_tokens=payload.get("reasoning_tokens"),
            total_tokens=payload.get("total_tokens"),
            metadata={"hf_model_id": self.hf_model_id, "thinking_enabled": self.thinking_enabled},
        )
