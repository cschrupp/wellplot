"""Live OpenRouter HTTP transport — authorized slices only; never log the API key."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from nlp_gate_modernbert.decomposer_capability_02.api_key import load_api_key

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


class LiveOpenRouterTransport:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 180.0,
        http_referer: str = "https://github.com/cschrupp/wellplot",
        x_title: str = "WellPlot-DECOMPOSER-CAPABILITY-02",
    ) -> None:
        self._api_key = api_key if api_key is not None else load_api_key()
        self.timeout_seconds = timeout_seconds
        self.http_referer = http_referer
        self.x_title = x_title

    def __call__(self, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            OPENROUTER_CHAT_URL,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": self.http_referer,
                "X-Title": self.x_title,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
                payload = json.loads(raw)
                if isinstance(payload, dict) and "provider" not in payload:
                    # Some responses put provider only in headers; keep body as-is.
                    pass
                return payload
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            # Encode status for retry eligibility markers used by the adapter.
            raise RuntimeError(f"HTTP_{exc.code}:{detail[:500]}") from None
        except TimeoutError as exc:
            raise RuntimeError(f"timeout:{exc}") from None
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"transport_error:{type(exc).__name__}:{exc}") from None


def redact_request_for_archive(body: dict[str, Any]) -> dict[str, Any]:
    """Archive-safe copy of the request body (no Authorization header exists here)."""
    return json.loads(json.dumps(body))
