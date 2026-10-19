"""Provider cost-card snapshot from frozen C02-02 evidence (no billable inference)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nlp_gate_modernbert.paths import EVIDENCE_DIR

DEFAULT_SNAPSHOT = (
    EVIDENCE_DIR
    / "decomposer_capability_02"
    / "c02_02"
    / "provider_price_routing_snapshot.json"
)


@dataclass(frozen=True)
class ProviderRate:
    provider_name: str
    prompt_usd_per_1m: float
    completion_usd_per_1m: float
    tag: str | None = None


@dataclass(frozen=True)
class CostCard:
    openrouter_model_id: str
    pinned_provider: str
    rate: ProviderRate
    source_path: str
    snapshot_utc: str
    catalog_prompt_usd_per_1m: float | None
    catalog_completion_usd_per_1m: float | None

    def estimate_usd(
        self, *, prompt_tokens: int | None, completion_tokens: int | None
    ) -> float:
        p = float(prompt_tokens or 0)
        c = float(completion_tokens or 0)
        return (p * self.rate.prompt_usd_per_1m + c * self.rate.completion_usd_per_1m) / 1_000_000.0

    def to_json(self) -> dict[str, Any]:
        return {
            "openrouter_model_id": self.openrouter_model_id,
            "pinned_provider": self.pinned_provider,
            "rate": {
                "provider_name": self.rate.provider_name,
                "prompt_usd_per_1m": self.rate.prompt_usd_per_1m,
                "completion_usd_per_1m": self.rate.completion_usd_per_1m,
                "tag": self.rate.tag,
            },
            "source_path": self.source_path,
            "snapshot_utc": self.snapshot_utc,
            "catalog_prompt_usd_per_1m": self.catalog_prompt_usd_per_1m,
            "catalog_completion_usd_per_1m": self.catalog_completion_usd_per_1m,
            "billable_inference_calls": 0,
        }


def load_cost_card(
    *,
    openrouter_model_id: str,
    pinned_provider: str,
    snapshot_path: Path | None = None,
    model_section_key: str | None = None,
) -> CostCard:
    path = snapshot_path or DEFAULT_SNAPSHOT
    doc = json.loads(path.read_text(encoding="utf-8"))
    if model_section_key is None:
        if openrouter_model_id == "google/gemini-4-argon":
            model_section_key = "gemini_4_argon"
        elif openrouter_model_id == "deepseek/deepseek-v4.1-flash-1017":
            model_section_key = "deepseek_v4_1_flash_1017"
        else:
            raise KeyError(f"unknown_model_for_cost_card:{openrouter_model_id}")
    section = doc[model_section_key]
    providers = section.get("providers") or []
    match = next(
        (p for p in providers if p.get("provider_name") == pinned_provider),
        None,
    )
    if match is None:
        raise KeyError(
            f"provider_not_in_snapshot:{pinned_provider}:model={openrouter_model_id}"
        )
    catalog = section.get("catalog_pricing_usd_per_1m") or {}
    rate = ProviderRate(
        provider_name=pinned_provider,
        prompt_usd_per_1m=float(match["prompt_usd_per_1m_tokens"]),
        completion_usd_per_1m=float(match["completion_usd_per_1m_tokens"]),
        tag=match.get("tag"),
    )
    return CostCard(
        openrouter_model_id=openrouter_model_id,
        pinned_provider=pinned_provider,
        rate=rate,
        source_path=str(path),
        snapshot_utc=datetime.now(timezone.utc).isoformat(),
        catalog_prompt_usd_per_1m=catalog.get("prompt"),
        catalog_completion_usd_per_1m=catalog.get("completion"),
    )
