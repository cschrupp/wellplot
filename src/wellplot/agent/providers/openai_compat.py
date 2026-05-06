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

"""OpenAI-compatible provider adapter for the public wellplot authoring API."""

from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse

from ..core import FunctionToolDefinition, ProviderRunResult, ToolCaller
from ._openai_responses import (
    load_api_key_from_sources,
    load_openai_client,
    run_responses_authoring_loop,
)


def _is_loopback_base_url(base_url: str) -> bool:
    """Return whether the configured base URL targets only the local machine."""
    hostname = urlparse(base_url).hostname
    if hostname is None:
        return False
    if hostname == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


def load_openai_compatible_api_key(
    *,
    server_root: str | Path,
    base_url: str,
    api_key: str | None = None,
) -> tuple[str, str]:
    """Load one OpenAI-compatible API key from explicit input or local sources."""
    try:
        return load_api_key_from_sources(
            server_root=server_root,
            api_key=api_key,
            env_var_names=("OPENAI_COMPAT_API_KEY", "OPENAI_API_KEY"),
            env_file_keys=("OPENAI_COMPAT_API_KEY", "OPENAI_API_KEY"),
            text_file_names=(
                "OPENAI_COMPAT_API_KEY.txt",
                "openai_compat_api_key.txt",
                "OPENAI_API_KEY.txt",
                "openai_api_key.txt",
            ),
            missing_message=(
                "Pass api_key=..., set OPENAI_COMPAT_API_KEY or OPENAI_API_KEY, or create "
                "one of OPENAI_COMPAT_API_KEY.txt, openai_compat_api_key.txt, "
                "OPENAI_API_KEY.txt, or openai_api_key.txt under the configured server "
                "root."
            ),
        )
    except RuntimeError:
        if _is_loopback_base_url(base_url):
            return (
                "wellplot-local-openai-compat",
                "implicit placeholder api_key for loopback openai_compat base_url",
            )
        raise RuntimeError(
            "Pass api_key=..., set OPENAI_COMPAT_API_KEY or OPENAI_API_KEY, or create "
            "one of OPENAI_COMPAT_API_KEY.txt, openai_compat_api_key.txt, "
            "OPENAI_API_KEY.txt, or openai_api_key.txt under the configured server "
            "root. Loopback endpoints such as http://localhost:11434/v1 can omit a "
            "real key and will receive an automatic placeholder token."
        ) from None


@dataclass(frozen=True)
class OpenAICompatibleAuthoringBackend:
    """Thin OpenAI-compatible Responses API adapter for the public session."""

    model: str
    client: object
    base_url: str
    credential_source: str | None = None
    provider: str = field(default="openai_compat", init=False)

    @classmethod
    def from_local_configuration(
        cls,
        *,
        model: str,
        server_root: str | Path,
        base_url: str,
        api_key: str | None = None,
    ) -> OpenAICompatibleAuthoringBackend:
        """Build one backend from explicit args plus local ignored key sources."""
        normalized_base_url = base_url.strip()
        if not normalized_base_url:
            raise ValueError("OpenAI-compatible authoring requires a non-empty base_url.")
        token, token_source = load_openai_compatible_api_key(
            server_root=server_root,
            base_url=normalized_base_url,
            api_key=api_key,
        )
        return cls(
            model=model,
            client=load_openai_client(api_key=token, base_url=normalized_base_url),
            base_url=normalized_base_url,
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
        """Run one OpenAI-compatible Responses loop through the shared adapter."""
        return await run_responses_authoring_loop(
            client=self.client,
            model=self.model,
            provider_label="OpenAI-compatible",
            instructions=instructions,
            initial_user_message=initial_user_message,
            tool_definitions=tool_definitions,
            tool_caller=tool_caller,
            max_rounds=max_rounds,
        )
