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


def morph_cost_card_from_endpoints(
    *,
    openrouter_model_id: str,
    endpoints_doc: dict[str, Any],
    preferred_tag: str = "morph/fp8",
) -> tuple[CostCard, dict[str, Any]]:
    """Select Morph endpoint (prefer morph/fp8) and build a CostCard."""
    data = endpoints_doc.get("data") or {}
    endpoints = data.get("endpoints") or []
    morph_rows = [e for e in endpoints if e.get("provider_name") == "Morph"]
    if not morph_rows:
        raise RuntimeError("live_rate_snapshot_fail:Morph_not_listed")

    preferred = next((e for e in morph_rows if e.get("tag") == preferred_tag), None)
    chosen = preferred or morph_rows[0]
    pricing = chosen.get("pricing") or {}
    if "prompt" not in pricing or "completion" not in pricing:
        raise RuntimeError("live_rate_snapshot_fail:Morph_pricing_incomplete")

    params = list(chosen.get("supported_parameters") or [])
    for required in ("reasoning", "max_tokens", "response_format", "reasoning_effort"):
        if required not in params:
            raise RuntimeError(f"live_rate_snapshot_fail:Morph_missing_param:{required}")

    rate = ProviderRate(
        provider_name="Morph",
        prompt_usd_per_1m=_usd_per_1m_from_per_token(pricing["prompt"]),
        completion_usd_per_1m=_usd_per_1m_from_per_token(pricing["completion"]),
        tag=chosen.get("tag"),
    )
    snap_utc = datetime.now(timezone.utc).isoformat()
    card = CostCard(
        openrouter_model_id=openrouter_model_id,
        pinned_provider="Morph",
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
        "pinned_provider": "Morph",
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
        "morph_endpoint_count": len(morph_rows),
        "billable_inference_calls": 0,
        "note": "Catalog/endpoints GET only; not a chat completion.",
    }
    return card, archive
