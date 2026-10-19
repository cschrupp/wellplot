"""Live OpenRouter endpoints rate snapshot (catalog GET; not inference)."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from typing import Any

from nlp_gate_modernbert.decomposer_capability_02.cost_card import CostCard, ProviderRate

OPENROUTER_ENDPOINTS_URL = (
    "https://openrouter.ai/api/v1/models/{model_id}/endpoints"
)


def fetch_endpoints_document(openrouter_model_id: str, *, timeout_seconds: float = 60.0) -> dict[str, Any]:
    url = OPENROUTER_ENDPOINTS_URL.format(model_id=openrouter_model_id)
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _usd_per_1m_from_per_token(raw: str | float | int) -> float:
    return float(raw) * 1_000_000.0


def provider_cost_card_from_endpoints(
    *,
    openrouter_model_id: str,
    endpoints_doc: dict[str, Any],
    pinned_provider: str,
    preferred_tag: str | None = None,
    required_parameters: tuple[str, ...] = ("max_tokens", "response_format"),
) -> tuple[CostCard, dict[str, Any]]:
    """Select a pinned provider endpoint and build a CostCard from live endpoints."""
    data = endpoints_doc.get("data") or {}
    endpoints = data.get("endpoints") or []
    rows = [e for e in endpoints if e.get("provider_name") == pinned_provider]
    if not rows:
        raise RuntimeError(f"live_rate_snapshot_fail:{pinned_provider}_not_listed")

    chosen = None
    if preferred_tag is not None:
        chosen = next((e for e in rows if e.get("tag") == preferred_tag), None)
    if chosen is None:
        chosen = rows[0]
    pricing = chosen.get("pricing") or {}
    if "prompt" not in pricing or "completion" not in pricing:
        raise RuntimeError(f"live_rate_snapshot_fail:{pinned_provider}_pricing_incomplete")

    params = list(chosen.get("supported_parameters") or [])
    for required in required_parameters:
        if required not in params:
            raise RuntimeError(
                f"live_rate_snapshot_fail:{pinned_provider}_missing_param:{required}"
            )

    rate = ProviderRate(
        provider_name=pinned_provider,
        prompt_usd_per_1m=_usd_per_1m_from_per_token(pricing["prompt"]),
        completion_usd_per_1m=_usd_per_1m_from_per_token(pricing["completion"]),
        tag=chosen.get("tag"),
    )
    snap_utc = datetime.now(timezone.utc).isoformat()
    card = CostCard(
        openrouter_model_id=openrouter_model_id,
        pinned_provider=pinned_provider,
        rate=rate,
        source_path=f"live_openrouter_endpoints:{openrouter_model_id}",
        snapshot_utc=snap_utc,
        catalog_prompt_usd_per_1m=None,
        catalog_completion_usd_per_1m=None,
    )
    archive = {
        "snapshot_kind": "live_openrouter_endpoints_preflight",
        "snapshot_utc": snap_utc,
        "openrouter_model_id": openrouter_model_id,
        "pinned_provider": pinned_provider,
        "preferred_tag": preferred_tag,
        "selected_endpoint": {
            "provider_name": chosen.get("provider_name"),
            "tag": chosen.get("tag"),
            "quantization": chosen.get("quantization"),
            "pricing": pricing,
            "prompt_usd_per_1m_tokens": rate.prompt_usd_per_1m,
            "completion_usd_per_1m_tokens": rate.completion_usd_per_1m,
            "supported_parameters": params,
            "max_completion_tokens": chosen.get("max_completion_tokens"),
        },
        "provider_endpoint_count": len(rows),
        "billable_inference_calls": 0,
        "note": "Catalog/endpoints GET only; not a chat completion.",
    }
    return card, archive


def morph_cost_card_from_endpoints(
    *,
    openrouter_model_id: str,
    endpoints_doc: dict[str, Any],
    preferred_tag: str = "morph/fp8",
) -> tuple[CostCard, dict[str, Any]]:
    """Select Morph endpoint (prefer morph/fp8) and build a CostCard."""
    return provider_cost_card_from_endpoints(
        openrouter_model_id=openrouter_model_id,
        endpoints_doc=endpoints_doc,
        pinned_provider="Morph",
        preferred_tag=preferred_tag,
        required_parameters=("reasoning", "max_tokens", "response_format", "reasoning_effort"),
    )


def google_ai_studio_cost_card_from_endpoints(
    *,
    openrouter_model_id: str,
    endpoints_doc: dict[str, Any],
    preferred_tag: str = "google-ai-studio/flex",
) -> tuple[CostCard, dict[str, Any]]:
    """Select Google AI Studio endpoint (prefer flex tag) and build a CostCard."""
    return provider_cost_card_from_endpoints(
        openrouter_model_id=openrouter_model_id,
        endpoints_doc=endpoints_doc,
        pinned_provider="Google AI Studio",
        preferred_tag=preferred_tag,
        required_parameters=("max_tokens", "response_format"),
    )
