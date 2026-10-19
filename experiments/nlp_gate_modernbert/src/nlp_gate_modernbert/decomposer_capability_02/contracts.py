"""Shared semantic input / normalized output contracts for Capability-02 adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ModelPathId(str, Enum):
    GEMINI_4_ARGON = "gemini-4-argon"
    DEEPSEEK_V41_FLASH_1017 = "deepseek-v4.1-flash-1017"
    QWEN3_4B_INSTRUCT_2507 = "qwen3-4b-instruct-2507"
    QWEN3_4B_THINKING_2507 = "qwen3-4b-thinking-2507"


@dataclass(frozen=True)
class SemanticDecomposerRequest:
    """Model-facing semantic input shared by all adapters (case_id harness-only)."""

    utterance: str
    projected_workspace_json: str
    case_id: str | None = None  # never sent to the model by adapters

    def model_facing_messages(self, *, system_prompt: str, user_template: str) -> list[dict[str, str]]:
        user = user_template.format(
            utterance=self.utterance,
            workspace_json=self.projected_workspace_json,
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user},
        ]

    def model_facing_payload(self) -> dict[str, str]:
        return {
            "utterance": self.utterance,
            "projected_workspace": self.projected_workspace_json,
        }


@dataclass
class NormalizedGeneration:
    """Transport-agnostic generation result before freeze_candidate()."""

    model_path: ModelPathId
    raw_text: str
    final_answer_text: str
    reasoning_text: str | None
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    reasoning_tokens: int | None
    total_tokens: int | None
    provider: str | None = None
    openrouter_model_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.final_answer_text.strip())


@dataclass(frozen=True)
class AdapterCapability:
    model_path: ModelPathId
    transport: str
    openrouter_model_id: str | None
    hf_model_id: str | None
    structured_output_mode: str
    reasoning_handling: str
    hard_xgrammar_mask: bool
    notes: tuple[str, ...] = ()
