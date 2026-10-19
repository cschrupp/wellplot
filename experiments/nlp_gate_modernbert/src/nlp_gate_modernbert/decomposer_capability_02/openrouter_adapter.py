"""OpenRouter chat adapter — transport injectable; live HTTP forbidden without exec auth."""

from __future__ import annotations

from typing import Any, Callable

from nlp_gate_modernbert.decomposer_capability_02.budget import (
    BudgetExhausted,
    CallBudget,
    ExecutionBudgets,
)
from nlp_gate_modernbert.decomposer_capability_02.contracts import (
    ModelPathId,
    NormalizedGeneration,
    SemanticDecomposerRequest,
)
from nlp_gate_modernbert.decomposer_capability_02.cost_card import CostCard
from nlp_gate_modernbert.decomposer_capability_02.normalize import (
    extract_json_object_text,
    strip_reasoning_blocks,
    usage_from_openrouter,
)
from nlp_gate_modernbert.decomposer_pilot import prompt_contract

Transport = Callable[[dict[str, Any]], dict[str, Any]]

# HTTP / transport classes eligible for one retry (design C02-03).
TRANSPORT_RETRY_MARKERS = (
    "timeout",
    "connection_reset",
    "HTTP_408",
    "HTTP_429",
    "HTTP_500",
    "HTTP_502",
    "HTTP_503",
    "HTTP_504",
    "Status408",
    "Status429",
    "Status500",
    "Status502",
    "Status503",
    "Status504",
)


class ProviderMismatch(RuntimeError):
    """Response provider not in the request allowlist — fail closed, no silent fallback."""


class OpenRouterAdapter:
    """Builds OpenAI-compatible chat requests and normalizes responses."""

    def __init__(
        self,
        *,
        model_path: ModelPathId,
        openrouter_model_id: str,
        budget: CallBudget | None = None,
        budgets: ExecutionBudgets | None = None,
        transport: Transport,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        request_json_object: bool = True,
        include_reasoning: bool = False,
        reasoning: dict[str, Any] | None = None,
        provider_order: list[str] | None = None,
        allow_fallbacks: bool = False,
        max_transport_attempts_per_logical_call: int = 2,
        cost_card: CostCard | None = None,
        require_provider_pin: bool = False,
    ) -> None:
        if budgets is None and budget is None:
            raise ValueError("budget_or_budgets_required")
        self.model_path = model_path
        self.openrouter_model_id = openrouter_model_id
        self.budget = budget
        self.budgets = budgets
        self.transport = transport
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.request_json_object = request_json_object
        self.include_reasoning = include_reasoning
        self.reasoning = dict(reasoning) if reasoning is not None else None
        self.provider_order = list(provider_order or [])
        self.allow_fallbacks = allow_fallbacks
        self.max_transport_attempts_per_logical_call = max_transport_attempts_per_logical_call
        self.cost_card = cost_card
        self.require_provider_pin = require_provider_pin
        if self.require_provider_pin and not self.provider_order:
            raise ValueError("provider_order_required_when_pinning")
        if self.allow_fallbacks:
            raise ValueError("silent_provider_fallback_forbidden")

    def build_request(self, req: SemanticDecomposerRequest) -> dict[str, Any]:
        messages = req.model_facing_messages(
            system_prompt=prompt_contract.SYSTEM_PROMPT,
            user_template=prompt_contract.USER_TEMPLATE,
        )
        body: dict[str, Any] = {
            "model": self.openrouter_model_id,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "include_reasoning": bool(self.include_reasoning),
        }
        if self.request_json_object:
            body["response_format"] = {"type": "json_object"}
        if self.reasoning is not None:
            body["reasoning"] = dict(self.reasoning)
        if self.provider_order:
            body["provider"] = {
                "order": list(self.provider_order),
                "allow_fallbacks": False,
                "require_parameters": True,
            }
        return body

    def _consume_logical(self) -> None:
        if self.budgets is not None:
            self.budgets.logical_calls.consume(1)
        elif self.budget is not None:
            self.budget.consume(1)

    def _consume_transport(self) -> None:
        if self.budgets is not None:
            self.budgets.transport_attempts.consume(1)
        # Legacy CallBudget path: transport attempts share the same counter only when
        # ExecutionBudgets are not provided (prep tests should use ExecutionBudgets).

    def _charge_usage(self, usage: dict[str, int | None]) -> float:
        if self.cost_card is None or self.budgets is None:
            return 0.0
        usd = self.cost_card.estimate_usd(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
        self.budgets.charge_usd(usd)
        return usd

    def _usage_fields(self, payload: dict[str, Any] | None) -> dict[str, int | None]:
        if not payload:
            return {
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "reasoning_tokens": None,
            }
        return usage_from_openrouter(payload)

    def _check_provider(self, observed: str | None) -> None:
        if not self.provider_order:
            return
        if observed is None:
            raise ProviderMismatch("missing_response_provider")
        if observed not in self.provider_order:
            raise ProviderMismatch(
                f"provider_mismatch:observed={observed};allowed={self.provider_order}"
            )

    def _eligible_transport_retry(self, error_text: str) -> bool:
        return any(marker.lower() in error_text.lower() for marker in TRANSPORT_RETRY_MARKERS)

    def _normalize_payload(
        self, payload: dict[str, Any], *, transport_attempts: int
    ) -> NormalizedGeneration:
        base_meta: dict[str, Any] = {
            "requested_model": self.openrouter_model_id,
            "requested_provider_order": list(self.provider_order),
            "transport_attempts": transport_attempts,
            "raw_usage": (payload or {}).get("usage"),
        }

        if payload.get("error"):
            usage = self._usage_fields(payload)
            usd = self._charge_usage(usage)
            return NormalizedGeneration(
                model_path=self.model_path,
                raw_text="",
                final_answer_text="",
                reasoning_text=None,
                finish_reason=None,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                reasoning_tokens=usage["reasoning_tokens"],
                total_tokens=usage["total_tokens"],
                openrouter_model_id=self.openrouter_model_id,
                provider=(payload.get("provider") if isinstance(payload.get("provider"), str) else None),
                error=f"provider_error:{payload['error']}",
                metadata={**base_meta, "raw_error": payload["error"], "estimated_usd": usd},
            )

        choices = payload.get("choices") or []
        if not choices:
            usage = self._usage_fields(payload)
            usd = self._charge_usage(usage)
            return NormalizedGeneration(
                model_path=self.model_path,
                raw_text="",
                final_answer_text="",
                reasoning_text=None,
                finish_reason=None,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                reasoning_tokens=usage["reasoning_tokens"],
                total_tokens=usage["total_tokens"],
                openrouter_model_id=self.openrouter_model_id,
                provider=payload.get("provider"),
                error="empty_choices",
                metadata={**base_meta, "estimated_usd": usd},
            )

        observed_provider = payload.get("provider")
        try:
            self._check_provider(observed_provider if isinstance(observed_provider, str) else None)
        except ProviderMismatch as exc:
            usage = self._usage_fields(payload)
            usd = self._charge_usage(usage)
            return NormalizedGeneration(
                model_path=self.model_path,
                raw_text="",
                final_answer_text="",
                reasoning_text=None,
                finish_reason=None,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                reasoning_tokens=usage["reasoning_tokens"],
                total_tokens=usage["total_tokens"],
                openrouter_model_id=payload.get("model") or self.openrouter_model_id,
                provider=observed_provider if isinstance(observed_provider, str) else None,
                error=f"provider_mismatch:{exc}",
                metadata={**base_meta, "estimated_usd": usd},
            )

        message = choices[0].get("message") or {}
        raw_text = message.get("content") or ""
        reasoning_field = message.get("reasoning")
        cleaned, tagged_reasoning = strip_reasoning_blocks(raw_text)
        reasoning = reasoning_field if isinstance(reasoning_field, str) else tagged_reasoning
        usage = self._usage_fields(payload)
        usd = self._charge_usage(usage)

        try:
            final = extract_json_object_text(cleaned)
        except Exception as exc:  # noqa: BLE001
            return NormalizedGeneration(
                model_path=self.model_path,
                raw_text=raw_text,
                final_answer_text="",
                reasoning_text=reasoning,
                finish_reason=choices[0].get("finish_reason"),
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                reasoning_tokens=usage["reasoning_tokens"],
                total_tokens=usage["total_tokens"],
                openrouter_model_id=payload.get("model") or self.openrouter_model_id,
                provider=observed_provider if isinstance(observed_provider, str) else None,
                error=f"parse_error:{type(exc).__name__}:{exc}",
                metadata={**base_meta, "estimated_usd": usd},
            )

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
            provider=observed_provider if isinstance(observed_provider, str) else None,
            metadata={
                **base_meta,
                "id": payload.get("id"),
                "usage": payload.get("usage"),
                "estimated_usd": usd,
            },
        )

    def generate(self, req: SemanticDecomposerRequest) -> NormalizedGeneration:
        self._consume_logical()
        body = self.build_request(req)
        attempts = 0
        last_transport_error: str | None = None

        while attempts < self.max_transport_attempts_per_logical_call:
            attempts += 1
            self._consume_transport()
            try:
                payload = self.transport(body)
            except Exception as exc:  # noqa: BLE001
                last_transport_error = f"transport_error:{type(exc).__name__}:{exc}"
                if (
                    attempts < self.max_transport_attempts_per_logical_call
                    and self._eligible_transport_retry(last_transport_error)
                ):
                    continue
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
                    error=last_transport_error,
                    metadata={
                        "requested_provider_order": list(self.provider_order),
                        "transport_attempts": attempts,
                        "raw_usage": None,
                    },
                )

            # Non-exception provider HTTP-style errors may be encoded in payload.
            if payload.get("error") and self._eligible_transport_retry(
                f"provider_error:{payload.get('error')}"
            ):
                last_transport_error = f"provider_error:{payload.get('error')}"
                if attempts < self.max_transport_attempts_per_logical_call:
                    continue

            return self._normalize_payload(payload, transport_attempts=attempts)

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
            error=last_transport_error or "transport_retry_exhausted",
            metadata={
                "requested_provider_order": list(self.provider_order),
                "transport_attempts": attempts,
                "raw_usage": None,
            },
        )


class ForbiddenLiveTransport:
    """Default transport — refuses live network until a separate execution authority."""

    def __call__(self, body: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("live_openrouter_transport_forbidden_without_execution_authority")
