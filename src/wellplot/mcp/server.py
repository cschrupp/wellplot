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

"""FastMCP server registration for the optional wellplot MCP surface."""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from ..errors import DependencyUnavailableError
from . import service

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP, Image


def _load_mcp_runtime() -> tuple[type[FastMCP], type[Image]]:
    try:
        from mcp.server.fastmcp import FastMCP, Image
    except ModuleNotFoundError as exc:
        raise DependencyUnavailableError(
            "wellplot MCP support requires the optional `mcp` dependency. "
            "Install `wellplot[mcp]` to use `wellplot-mcp`."
        ) from exc
    return FastMCP, Image


def create_mcp_server(root: str | Path | None = None) -> FastMCP:
    """Create and configure the wellplot FastMCP server."""
    FastMCP, Image = _load_mcp_runtime()
    server_root = service.resolve_server_root(root)
    mcp = FastMCP(
        "wellplot",
        instructions=(
            "wellplot MCP server for validating, inspecting, previewing, and rendering "
            f"logfiles under the fixed server root {server_root}."
        ),
    )

    @mcp.tool()
    def validate_logfile(logfile_path: str) -> dict[str, object]:
        """Validate a logfile path and return structured status."""
        return asdict(service.validate_logfile(logfile_path, root=server_root))

    @mcp.tool()
    def inspect_logfile(logfile_path: str) -> dict[str, object]:
        """Inspect a logfile path and return structured report metadata."""
        return asdict(service.inspect_logfile(logfile_path, root=server_root))

    @mcp.tool()
    def preview_logfile_png(
        logfile_path: str,
        page_index: int = 0,
        dpi: int = 144,
        section_id: str | None = None,
        track_ids: list[str] | None = None,
        depth_range: tuple[float, float] | None = None,
        depth_range_unit: str | None = None,
        include_report_pages: bool = True,
    ) -> object:
        """Render one logfile preview as an MCP image payload."""
        png_bytes = service.preview_logfile_png(
            logfile_path,
            page_index=page_index,
            dpi=dpi,
            section_id=section_id,
            track_ids=track_ids,
            depth_range=depth_range,
            depth_range_unit=depth_range_unit,
            include_report_pages=include_report_pages,
            root=server_root,
        )
        return Image(data=png_bytes, format="png")

    @mcp.tool()
    def preview_section_png(
        logfile_path: str,
        section_id: str,
        page_index: int = 0,
        dpi: int = 144,
    ) -> object:
        """Render one logfile section preview as an MCP image payload."""
        png_bytes = service.preview_section_png(
            logfile_path,
            section_id=section_id,
            page_index=page_index,
            dpi=dpi,
            root=server_root,
        )
        return Image(data=png_bytes, format="png")

    @mcp.tool()
    def preview_track_png(
        logfile_path: str,
        section_id: str,
        track_ids: list[str],
        page_index: int = 0,
        dpi: int = 144,
        depth_range: tuple[float, float] | None = None,
        depth_range_unit: str | None = None,
    ) -> object:
        """Render one logfile track selection preview as an MCP image payload."""
        png_bytes = service.preview_track_png(
            logfile_path,
            section_id=section_id,
            track_ids=track_ids,
            page_index=page_index,
            dpi=dpi,
            depth_range=depth_range,
            depth_range_unit=depth_range_unit,
            root=server_root,
        )
        return Image(data=png_bytes, format="png")

    @mcp.tool()
    def preview_window_png(
        logfile_path: str,
        depth_range: tuple[float, float],
        depth_range_unit: str | None = None,
        page_index: int = 0,
        dpi: int = 144,
        section_ids: list[str] | None = None,
    ) -> object:
        """Render one logfile depth-window preview as an MCP image payload."""
        png_bytes = service.preview_window_png(
            logfile_path,
            depth_range=depth_range,
            depth_range_unit=depth_range_unit,
            page_index=page_index,
            dpi=dpi,
            section_ids=section_ids,
            root=server_root,
        )
        return Image(data=png_bytes, format="png")

    @mcp.tool()
    def render_logfile_to_file(
        logfile_path: str,
        output_path: str,
        overwrite: bool = False,
    ) -> dict[str, object]:
        """Render one logfile to an explicit output path."""
        return asdict(
            service.render_logfile_to_file(
                logfile_path,
                output_path,
                overwrite=overwrite,
                root=server_root,
            )
        )

    @mcp.tool()
    def export_example_bundle(
        example_id: str,
        output_dir: str,
        overwrite: bool = False,
    ) -> dict[str, object]:
        """Export one packaged example bundle under the server root."""
        return asdict(
            service.export_example_bundle(
                example_id,
                output_dir,
                overwrite=overwrite,
                root=server_root,
            )
        )

    @mcp.tool()
    def create_logfile_draft(
        output_path: str,
        example_id: str | None = None,
        source_logfile_path: str | None = None,
        overwrite: bool = False,
    ) -> dict[str, object]:
        """Create one normalized draft logfile from an example or existing logfile."""
        return asdict(
            service.create_logfile_draft(
                output_path,
                example_id=example_id,
                source_logfile_path=source_logfile_path,
                overwrite=overwrite,
                root=server_root,
            )
        )

    @mcp.tool()
    def summarize_logfile_draft(logfile_path: str) -> dict[str, object]:
        """Summarize one draft logfile for deterministic authoring workflows."""
        return asdict(service.summarize_logfile_draft(logfile_path, root=server_root))

    @mcp.tool()
    def validate_logfile_text(
        yaml_text: str,
        base_dir: str | None = None,
    ) -> dict[str, object]:
        """Validate unsaved logfile YAML text under the server root."""
        return asdict(
            service.validate_logfile_text(
                yaml_text,
                base_dir=base_dir,
                root=server_root,
            )
        )

    @mcp.tool()
    def format_logfile_text(
        yaml_text: str,
        base_dir: str | None = None,
    ) -> dict[str, object]:
        """Normalize valid logfile YAML text through the canonical serializer."""
        return asdict(
            service.format_logfile_text(
                yaml_text,
                base_dir=base_dir,
                root=server_root,
            )
        )

    @mcp.tool()
    def save_logfile_text(
        yaml_text: str,
        output_path: str,
        overwrite: bool = False,
        base_dir: str | None = None,
    ) -> dict[str, object]:
        """Validate, normalize, and save logfile YAML text under the server root."""
        return asdict(
            service.save_logfile_text(
                yaml_text,
                output_path,
                overwrite=overwrite,
                base_dir=base_dir,
                root=server_root,
            )
        )

    @mcp.resource("wellplot://schema/logfile.json", mime_type="application/json")
    def logfile_schema_resource() -> str:
        """Return the wellplot logfile JSON schema resource."""
        return service.schema_resource().text

    @mcp.resource("wellplot://examples/production/index.json", mime_type="application/json")
    def production_examples_manifest_resource() -> str:
        """Return the curated production example manifest resource."""
        return service.production_example_manifest_resource().text

    @mcp.resource(
        "wellplot://examples/production/{example_id}/README.md",
        mime_type="text/markdown",
    )
    def production_example_readme_resource(example_id: str) -> str:
        """Return the packaged production example README resource."""
        return service.production_example_resource(example_id, "README.md").text

    @mcp.resource(
        "wellplot://examples/production/{example_id}/base.template.yaml",
        mime_type="text/yaml",
    )
    def production_example_template_resource(example_id: str) -> str:
        """Return the packaged production example base template resource."""
        return service.production_example_resource(example_id, "base.template.yaml").text

    @mcp.resource(
        "wellplot://examples/production/{example_id}/full_reconstruction.log.yaml",
        mime_type="text/yaml",
    )
    def production_example_logfile_resource(example_id: str) -> str:
        """Return the packaged production example logfile resource."""
        return service.production_example_resource(example_id, "full_reconstruction.log.yaml").text

    @mcp.resource(
        "wellplot://examples/production/{example_id}/data-notes.md",
        mime_type="text/markdown",
    )
    def production_example_notes_resource(example_id: str) -> str:
        """Return the packaged production example notes resource."""
        return service.production_example_resource(example_id, "data-notes.md").text

    @mcp.prompt()
    def review_logfile(logfile_path: str) -> str:
        """Guide a model through the logfile review workflow."""
        return service.review_logfile_prompt(logfile_path)

    @mcp.prompt()
    def preview_logfile(logfile_path: str, focus: str | None = None) -> str:
        """Guide a model through the logfile preview workflow."""
        return service.preview_logfile_prompt(logfile_path, focus)

    @mcp.prompt()
    def start_from_example(example_id: str, goal: str) -> str:
        """Guide a model through adapting one packaged example to a new goal."""
        return service.start_from_example_prompt(example_id, goal)

    return mcp


def main() -> int:
    """Run the wellplot MCP server over stdio."""
    try:
        create_mcp_server().run()
    except DependencyUnavailableError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
