"""Frozen zero-shot system prompt + user template (DESIGN Q2 allowlist; no sealed-six)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

PROMPT_CONTRACT_VERSION = "decomposer_pilot_preflight_01.prompt.v1"

# General contract semantics only — no sealed-six derivatives, no case/fixture/oracle hints.
SYSTEM_PROMPT = """You are a WELL-IR decomposer. Translate one user request plus a projected workspace into exactly one ScopeNormalizedProgram as JSON.

Output rules:
- JSON only; no prose, markdown, explanation, confidence, or repair notes.
- Conform to the frozen ScopeNormalizedProgram schema provided by constrained decoding.
- Preserve explicit user semantics; do not invent workspace entities or unsupported operations.
- Supported operations include CREATE_TRACK, PLACE_CURVE, CONFIGURE_CURVE_DISPLAY, DEFINE_FILL, and other schema-enumerated operations.
- Use local_ref to refer to entities created earlier in the same program when later tasks must bind to them.
- Use depends_on only for genuine semantic dependency required by the utterance; do not invent ordering.

Do not include case identifiers, fixture identifiers, evaluation labels, expected task counts, or oracle-derived guidance.
"""

USER_TEMPLATE = """Utterance:
{utterance}

Projected workspace (JSON):
{workspace_json}
"""

CHAT_TEMPLATE_KWARGS = {
    "tokenize": False,
    "add_generation_prompt": True,
    "enable_thinking": False,
}

# Fixed dummy material for template smoke only (not sealed six).
DUMMY_UTTERANCE = "place the GR curve on track 1"
DUMMY_WORKSPACE = {
    "curves": [{"id": "c_gr", "handle": "GR", "aliases": ["Gamma"]}],
    "tracks": [{"ref": 1, "title": "Track1", "curves": ["c_gr"]}],
    "fills": [],
    "focus_curve_handle": None,
    "focus_track_ref": None,
    "depth_unit": "m",
    "supported_depth_units": ["m", "ft"],
}


def system_prompt_sha256() -> str:
    return hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def user_template_sha256() -> str:
    return hashlib.sha256(USER_TEMPLATE.encode("utf-8")).hexdigest()


def build_messages(*, utterance: str, workspace_json: str) -> list[dict[str, str]]:
    user = USER_TEMPLATE.format(utterance=utterance, workspace_json=workspace_json)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def render_chat_template_text(
    tokenizer: Any,
    *,
    utterance: str,
    workspace_json: str,
) -> str:
    messages = build_messages(utterance=utterance, workspace_json=workspace_json)
    return tokenizer.apply_chat_template(messages, **CHAT_TEMPLATE_KWARGS)


def prompt_contract_manifest(
    *,
    chat_template_text_sha256: str | None = None,
    input_ids_sha256: str | None = None,
    messages_sha256: str | None = None,
) -> dict[str, Any]:
    return {
        "version": PROMPT_CONTRACT_VERSION,
        "exemplars": 0,
        "regime": "zero-shot",
        "system_prompt_sha256": system_prompt_sha256(),
        "user_template_sha256": user_template_sha256(),
        "chat_template_kwargs": dict(CHAT_TEMPLATE_KWARGS),
        "thinking_disable_mechanism": "enable_thinking=False via apply_chat_template",
        "messages_encoding_sha256": messages_sha256,
        "chat_template_text_sha256": chat_template_text_sha256,
        "input_ids_sha256": input_ids_sha256,
        "dummy_smoke": {
            "utterance": DUMMY_UTTERANCE,
            "note": "fixed dummy for template smoke only; not sealed-six material",
        },
    }


def hash_messages(messages: list[dict[str, str]]) -> str:
    payload = json.dumps(messages, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
