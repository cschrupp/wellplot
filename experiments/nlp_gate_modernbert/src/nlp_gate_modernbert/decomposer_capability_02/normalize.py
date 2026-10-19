"""Parse hosted/local generations into a final JSON candidate string."""

from __future__ import annotations

import json
import re
from typing import Any


_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def strip_reasoning_blocks(text: str) -> tuple[str, str | None]:
    """Separate optional thinking/reasoning wrappers from final answer text."""
    reasoning_chunks: list[str] = []
    cleaned = text
    for tag in ("think", "thinking", "reasoning"):
        pattern = re.compile(rf"<{tag}>([\s\S]*?)</{tag}>", re.IGNORECASE)
        for match in pattern.finditer(cleaned):
            reasoning_chunks.append(match.group(1).strip())
        cleaned = pattern.sub("", cleaned)
    reasoning = "\n\n".join(reasoning_chunks) if reasoning_chunks else None
    return cleaned.strip(), reasoning


def extract_json_object_text(text: str) -> str:
    """Best-effort extraction of a single JSON object for freeze_candidate()."""
    cleaned, _ = strip_reasoning_blocks(text)
    cleaned = cleaned.strip()
    if not cleaned:
        raise ValueError("empty_generation")

    fence = _FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1).strip()

    if cleaned.startswith("{"):
        # Validate outermost object by json.loads when possible.
        try:
            obj = json.loads(cleaned)
            if isinstance(obj, dict):
                return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        except json.JSONDecodeError:
            pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no_json_object_found")
    candidate = cleaned[start : end + 1]
    obj = json.loads(candidate)
    if not isinstance(obj, dict):
        raise ValueError("json_root_not_object")
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def usage_from_openrouter(payload: dict[str, Any]) -> dict[str, int | None]:
    usage = payload.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "reasoning_tokens": details.get("reasoning_tokens"),
    }
