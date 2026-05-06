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

"""Drive local wellplot MCP authoring through the public agent API."""

from __future__ import annotations

import json
import os
from pathlib import Path

from wellplot.agent import AuthoringResult, run_authoring_request

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
DEFAULT_EXAMPLE_ID = "forge16b_porosity_example"
DEFAULT_OUTPUT_LOGFILE = Path("workspace/mcp_demo/openai_forge16b_recreated.log.yaml")
DEFAULT_GOAL = (
    "Recreate the forge16b porosity example as a simplified interpretation packet. "
    "Keep one GR/SP track, one depth track, one resistivity track, and one porosity "
    "overlay track with RHOB and NPHI. Shorten the remarks to one concise block and "
    "simplify the heading."
)


def repo_root() -> Path:
    """Return the repository root that contains the example checkout."""
    return Path(__file__).resolve().parents[1]


def repo_relative(path: str | Path) -> str:
    """Return one path relative to the repository root."""
    raw = Path(path)
    if raw.is_absolute():
        return raw.resolve().relative_to(repo_root()).as_posix()
    return raw.as_posix()


async def run_openai_authoring(
    *,
    goal: str = DEFAULT_GOAL,
    example_id: str = DEFAULT_EXAMPLE_ID,
    output_logfile: str | Path = DEFAULT_OUTPUT_LOGFILE,
    model: str = DEFAULT_MODEL,
    max_rounds: int = 12,
) -> AuthoringResult:
    """Run one natural-language authoring pass through the public agent API."""
    # Keep provider credentials outside the script body. The agent layer loads
    # OPENAI_API_KEY or local ignored secret files rooted at repo_root().
    return await run_authoring_request(
        goal=goal,
        example_id=example_id,
        output_logfile=output_logfile,
        provider="openai",
        model=model,
        server_root=repo_root(),
        max_rounds=max_rounds,
    )


async def _run_demo() -> None:
    result = await run_openai_authoring()
    preview_paths = {
        name: repo_relative(path) for name, path in result.write_preview_artifacts().items()
    }
    summary = {
        "provider": result.provider,
        "model": result.model,
        "token_source": result.credential_source,
        "draft_logfile": result.draft_logfile,
        "preview_paths": preview_paths,
        "tool_trace": [
            {
                "round": item.round,
                "name": item.name,
                "arguments": item.arguments,
            }
            for item in result.tool_trace
        ],
        "validation": result.validation,
        "summary_lines": result.change_summary.get("summary_lines", []),
        "final_text": result.final_text,
    }
    print(json.dumps(summary, indent=2))


def main() -> None:
    """Run the natural-language MCP authoring demo as a normal Python script."""
    import anyio

    anyio.run(_run_demo)


if __name__ == "__main__":
    main()
