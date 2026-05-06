###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
###############################################################################

"""OpenAI provider adapter for the public wellplot authoring API."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from wellplot.errors import DependencyUnavailableError

from ..core import AuthoringToolCall, FunctionToolDefinition, ProviderRunResult, ToolCaller


def load_openai_api_key(
    *,
    server_root: str | Path,
    api_key: str | None = None,
) -> tuple[str, str]:
    """Load one OpenAI API key from explicit input or local ignored sources."""
    if api_key is not None and api_key.strip():
        return api_key.strip(), "explicit api_key argument"

    env_key = os.getenv("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key, "environment variable OPENAI_API_KEY"

    root = Path(server_root).resolve()
    env_paths = (root / ".env.local", root / ".env")
    for env_path in env_paths:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() != "OPENAI_API_KEY" or not value.strip():
                continue
            token = value.strip().strip('"').strip("'")
            if token:
                return token, str(env_path.relative_to(root))

    text_paths = (
        root / "OPENAI_API_KEY.txt",
        root / "openai_api_key.txt",
    )
    for text_path in text_paths:
        if not text_path.exists():
            continue
        token = text_path.read_text(encoding="utf-8").strip()
        if token:
            return token, str(text_path.relative_to(root))

    raise RuntimeError(
        "Set OPENAI_API_KEY, pass api_key=..., or create one of .env.local, .env, "
        "OPENAI_API_KEY.txt, or openai_api_key.txt under the configured server root."
    )


def _load_openai_client(api_key: str) -> object:
    """Import and construct the optional OpenAI client lazily."""
    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:
        raise DependencyUnavailableError(
            "Install `wellplot[agent]` or add the `openai` package to use the "
            "OpenAI authoring session."
        ) from exc
    return OpenAI(api_key=api_key)


@dataclass(frozen=True)
class OpenAIAuthoringBackend:
    """Thin OpenAI Responses API adapter for the public authoring session."""

    model: str
    client: object
    credential_source: str | None = None
    provider: str = field(default="openai", init=False)

    @classmethod
    def from_local_configuration(
        cls,
        *,
        model: str,
        server_root: str | Path,
        api_key: str | None = None,
    ) -> OpenAIAuthoringBackend:
        """Build one backend from explicit args plus local ignored key sources."""
        token, token_source = load_openai_api_key(server_root=server_root, api_key=api_key)
        return cls(
            model=model,
            client=_load_openai_client(token),
            credential_source=token_source,
        )

    async def run_authoring(
        self,
        *,
        instructions: str,
        initial_user_message: str,
        tool_definitions: list[FunctionToolDefinition],
        tool_caller: ToolCaller,
        max_rounds: int,
    ) -> ProviderRunResult:
        """Run one OpenAI Responses API loop and replay tool calls through MCP."""
        response = None
        final_text = ""
        pending_input: list[dict[str, object]] = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": initial_user_message,
                    }
                ],
            }
        ]
        tool_trace: list[AuthoringToolCall] = []
        function_tools = [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in tool_definitions
        ]
        if not function_tools:
            raise RuntimeError("No function tools were provided to the OpenAI backend.")

        for round_index in range(1, max_rounds + 1):
            request_kwargs: dict[str, object] = {
                "model": self.model,
                "tools": function_tools,
            }
            if response is None:
                request_kwargs["instructions"] = instructions
                request_kwargs["input"] = pending_input
            else:
                request_kwargs["previous_response_id"] = getattr(response, "id", None)
                request_kwargs["input"] = pending_input
            response = self.client.responses.create(**request_kwargs)
            output = getattr(response, "output", [])
            function_calls = [
                item for item in output if getattr(item, "type", None) == "function_call"
            ]
            if not function_calls:
                response_text = getattr(response, "output_text", "")
                final_text = response_text if isinstance(response_text, str) else ""
                break

            pending_input = []
            for call in function_calls:
                arguments = json.loads(getattr(call, "arguments", "") or "{}")
                if not isinstance(arguments, dict):
                    raise RuntimeError("Expected tool-call arguments to decode into a mapping.")
                tool_trace.append(
                    AuthoringToolCall(
                        round=round_index,
                        name=getattr(call, "name", ""),
                        arguments=arguments,
                    )
                )
                tool_payload = await tool_caller(getattr(call, "name", ""), arguments)
                pending_input.append(
                    {
                        "type": "function_call_output",
                        "call_id": getattr(call, "call_id", ""),
                        "output": json.dumps(tool_payload),
                    }
                )
        else:
            raise RuntimeError(f"The OpenAI authoring loop exceeded {max_rounds} rounds.")

        if response is not None and not final_text.strip():
            summary_response = self.client.responses.create(
                model=self.model,
                previous_response_id=getattr(response, "id", None),
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Summarize the applied draft changes in three concise "
                                    "bullet points without calling more tools."
                                ),
                            }
                        ],
                    }
                ],
            )
            summary_text = getattr(summary_response, "output_text", "")
            final_text = summary_text if isinstance(summary_text, str) else ""

        return ProviderRunResult(
            final_text=final_text,
            tool_trace=tuple(tool_trace),
        )
