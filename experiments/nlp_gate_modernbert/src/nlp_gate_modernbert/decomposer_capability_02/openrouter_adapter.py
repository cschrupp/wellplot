"""OpenRouter chat adapter — transport injectable; live HTTP not used in C02-02."""

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
    usage_from_openrouter,
)
from nlp_gate_modernbert.decomposer_pilot import prompt_contract

Transport = Callable[[dict[str, Any]], dict[str, Any]]


class OpenRouterAdapter:
    """Builds OpenAI-compatible chat requests and normalizes responses."""

    def __init__(
        self,
        *,
        model_path: ModelPathId,
        openrouter_model_id: str,
        budget: CallBudget,
        transport: Transport,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        request_json_object: bool = True,
        include_reasoning: bool = False,
    ) -> None:
        self.model_path = model_path
        self.openrouter_model_id = openrouter_model_id
        self.budget = budget
        self.transport = transport
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.request_json_object = request_json_object
        self.include_reasoning = include_reasoning

    def build_request(self, req: SemanticDecomposerRequest) -> dict[str, Any]:
        messages = req.model_facing_messages(
            system_prompt=prompt_contract.SYSTEM_PROMPT,
            user_template=prompt_contract.USER_TEMPLATE,
        )
        # case_id must never appear in request messages content as harness metadata injection
        body: dict[str, Any] = {
            "model": self.openrouter_model_id,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.request_json_object:
            body["response_format"] = {"type": "json_object"}
        if self.include_reasoning:
            body["include_reasoning"] = True
        return body

    def generate(self, req: SemanticDecomposerRequest) -> NormalizedGeneration:
        self.budget.consume(1)
        body = self.build_request(req)
        try:
            payload = self.transport(body)
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
                openrouter_model_id=self.openrouter_model_id,
                error=f"transport_error:{type(exc).__name__}:{exc}",
            )

        if payload.get("error"):
            err = payload["error"]
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
                openrouter_model_id=self.openrouter_model_id,
                provider=(payload.get("provider") if isinstance(payload.get("provider"), str) else None),
                error=f"provider_error:{err}",
                metadata={"raw_error": err},
            )

        choices = payload.get("choices") or []
        if not choices:
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
                openrouter_model_id=self.openrouter_model_id,
                error="empty_choices",
            )

        message = choices[0].get("message") or {}
        raw_text = message.get("content") or ""
        reasoning_field = message.get("reasoning")
        cleaned, tagged_reasoning = strip_reasoning_blocks(raw_text)
        reasoning = reasoning_field if isinstance(reasoning_field, str) else tagged_reasoning
        try:
            final = extract_json_object_text(cleaned)
        except Exception as exc:  # noqa: BLE001
            return NormalizedGeneration(
                model_path=self.model_path,
                raw_text=raw_text,
                final_answer_text="",
                reasoning_text=reasoning,
                finish_reason=choices[0].get("finish_reason"),
                prompt_tokens=None,
                completion_tokens=None,
                reasoning_tokens=None,
                total_tokens=None,
                openrouter_model_id=self.openrouter_model_id,
                provider=payload.get("provider"),
                error=f"parse_error:{type(exc).__name__}:{exc}",
                metadata={"usage": payload.get("usage")},
            )

        usage = usage_from_openrouter(payload)
        return NormalizedGeneration(
            model_path=self.model_path,
            raw_text=raw_text,
            final_answer_text=final,
            reasoning_text=reasoning,
            finish_reason=choices[0].get("finish_reason"),
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            reasoning_tokens=usage["reasoning_tokens"],
            total_tokens=usage["total_tokens"],
            openrouter_model_id=payload.get("model") or self.openrouter_model_id,
            provider=payload.get("provider"),
            metadata={
                "id": payload.get("id"),
                "usage": payload.get("usage"),
                "requested_model": self.openrouter_model_id,
            },
        )


class ForbiddenLiveTransport:
    """Default transport — refuses live network; C02-02 uses mocks only."""

    def __call__(self, body: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("live_openrouter_transport_forbidden_in_c02_02")
