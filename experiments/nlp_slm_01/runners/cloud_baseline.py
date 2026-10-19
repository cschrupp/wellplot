#!/usr/bin/env python3
"""Configurable cloud LLM → WELL-IR baseline (Baseline B)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from runners.common import SYSTEM_PROMPT, assemble_user_payload, schema_hash


def run_cloud(
    *,
    utterance: str,
    workspace: dict[str, Any],
    d0: dict[str, Any],
    model: str | None = None,
) -> dict[str, Any]:
    model_id = model or os.environ.get("SLM01_CLOUD_MODEL", "openai/gpt-4.1")
    api_key = os.environ.get("SLM01_CLOUD_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "status": "runner_unavailable",
            "detail": "Set SLM01_CLOUD_API_KEY or OPENAI_API_KEY to run Baseline B",
            "model_id": model_id,
            "schema_sha256": schema_hash(),
        }

    try:
        import httpx
    except ImportError as exc:  # pragma: no cover
        return {"status": "runner_unavailable", "detail": str(exc), "model_id": model_id}

    base_url = os.environ.get("SLM01_CLOUD_BASE_URL", "https://api.openai.com/v1")
    payload = {
        "model": model_id.split("/", 1)[-1] if model_id.startswith("openai/") else model_id,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": assemble_user_payload(utterance, workspace, d0),
            },
        ],
    }
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    text = data["choices"][0]["message"]["content"]
    return {
        "model_id": model_id,
        "schema_sha256": schema_hash(),
        "raw_text": text,
        "provider_response_id": data.get("id"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-json", type=Path, required=True)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    case = json.loads(args.case_json.read_text(encoding="utf-8"))
    print(
        json.dumps(
            run_cloud(
                utterance=case["utterance"],
                workspace=case["workspace"],
                d0=case["d0"],
                model=args.model,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
