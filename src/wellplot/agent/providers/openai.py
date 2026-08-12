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

from dataclasses import dataclass, field
from pathlib import Path

from ..core import FunctionToolDefinition, ProviderRunResult, ToolCaller
from ._openai_responses import (
    load_api_key_from_sources,
    load_openai_client,
    run_responses_authoring_loop,
)


def load_openai_api_key(
    *,
    server_root: str | Path,
    api_key: str | None = None,
) -> tuple[str, str]:
    """Load one OpenAI API key from explicit input or local ignored sources."""
    return load_api_key_from_sources(
        server_root=server_root,
        api_key=api_key,
        env_var_names=("OPENAI_API_KEY",),
        env_file_keys=("OPENAI_API_KEY",),
        text_file_names=("OPENAI_API_KEY.txt", "openai_api_key.txt"),
        missing_message=(
            "Set OPENAI_API_KEY, pass api_key=..., or create one of .env.local, .env, "
            "OPENAI_API_KEY.txt, or openai_api_key.txt under the configured server root."
        ),
    )


@dataclass(frozen=True)
class OpenAIAuthoringBackend:
    """Thin OpenAI Responses API adapter for the public authoring session."""

    model: str
    client: object
    credential_source: str | None = None
    provider: str = field(default="openai", init=False)
    supports_desired_state: bool = field(default=True, init=False)

    @classmethod
    def from_local_configuration(
        cls,
        *,
        model: str,
        server_root: str | Path,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> OpenAIAuthoringBackend:
        """Build one backend from explicit args plus local ignored key sources."""
        token, token_source = load_openai_api_key(server_root=server_root, api_key=api_key)
        return cls(
            model=model,
            client=load_openai_client(api_key=token, timeout=timeout),
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
        required_tool_name: str | None = None,
    ) -> ProviderRunResult:
        """Run one OpenAI Responses API loop and replay tool calls through MCP."""
        return await run_responses_authoring_loop(
            client=self.client,
            model=self.model,
            provider_label="OpenAI",
            instructions=instructions,
            initial_user_message=initial_user_message,
            tool_definitions=tool_definitions,
            tool_caller=tool_caller,
            max_rounds=max_rounds,
            required_tool_name=required_tool_name,
        )
