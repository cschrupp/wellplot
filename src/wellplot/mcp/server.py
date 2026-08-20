###############################################################################
#
# Copyright (C) 2026 Carlos Schrupp
# SPDX-License-Identifier: Apache-2.0
#
###############################################################################

"""FastMCP registration for the stable wellplot authoring surface."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from ..errors import DependencyUnavailableError
from . import service
from .stable import register_stable_tools

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP, Image


def _load_mcp_runtime() -> tuple[type[FastMCP], type[Image], type[object]]:
    try:
        from mcp.server.fastmcp import FastMCP, Image
        from mcp.types import ToolAnnotations
    except ModuleNotFoundError as exc:
        raise DependencyUnavailableError(
            "wellplot MCP support requires the optional `mcp` dependency. "
            "Install `wellplot[mcp]` to use `wellplot-mcp`."
        ) from exc
    return FastMCP, Image, ToolAnnotations


def _register_resources(mcp: FastMCP) -> None:
    """Register discovery resources; resources are not model mutation tools."""

    @mcp.resource("wellplot://schema/logfile.json", mime_type="application/json")
    def logfile_schema_resource() -> str:
        return service.schema_resource().text

    @mcp.resource("wellplot://examples/production/index.json", mime_type="application/json")
    def production_examples_manifest_resource() -> str:
        return service.production_example_manifest_resource().text

    @mcp.resource(
        "wellplot://examples/production/{example_id}/README.md", mime_type="text/markdown"
    )
    def production_example_readme_resource(example_id: str) -> str:
        return service.production_example_resource(example_id, "README.md").text

    @mcp.resource(
        "wellplot://examples/production/{example_id}/base.template.yaml", mime_type="text/yaml"
    )
    def production_example_template_resource(example_id: str) -> str:
        return service.production_example_resource(example_id, "base.template.yaml").text

    @mcp.resource(
        "wellplot://examples/production/{example_id}/full_reconstruction.log.yaml",
        mime_type="text/yaml",
    )
    def production_example_logfile_resource(example_id: str) -> str:
        return service.production_example_resource(example_id, "full_reconstruction.log.yaml").text

    @mcp.resource(
        "wellplot://examples/production/{example_id}/data-notes.md", mime_type="text/markdown"
    )
    def production_example_notes_resource(example_id: str) -> str:
        return service.production_example_resource(example_id, "data-notes.md").text

    @mcp.resource("wellplot://authoring/schema/patch.json", mime_type="application/json")
    def authoring_patch_schema_resource() -> str:
        return service.authoring_patch_schema_resource().text

    @mcp.resource("wellplot://authoring/schema/canonical.json", mime_type="application/json")
    def authoring_canonical_schema_resource() -> str:
        return service.authoring_canonical_schema_resource().text

    @mcp.resource("wellplot://authoring/schema/operations.json", mime_type="application/json")
    def authoring_operations_schema_resource() -> str:
        return service.authoring_operations_schema_resource().text

    @mcp.resource("wellplot://authoring/catalog/hierarchy.json", mime_type="application/json")
    def authoring_hierarchy_resource() -> str:
        return service.authoring_hierarchy_resource().text

    @mcp.resource("wellplot://authoring/catalog/track-kinds.json", mime_type="application/json")
    def authoring_track_kinds_resource() -> str:
        return service.authoring_track_kinds_resource().text

    @mcp.resource("wellplot://authoring/catalog/fill-kinds.json", mime_type="application/json")
    def authoring_fill_kinds_resource() -> str:
        return service.authoring_fill_kinds_resource().text

    @mcp.resource(
        "wellplot://authoring/catalog/track-archetypes.json", mime_type="application/json"
    )
    def authoring_track_archetypes_resource() -> str:
        return service.authoring_track_archetypes_resource().text

    @mcp.resource(
        "wellplot://authoring/catalog/header-archetypes.json", mime_type="application/json"
    )
    def authoring_header_archetypes_resource() -> str:
        return service.authoring_header_archetypes_resource().text

    @mcp.resource(
        "wellplot://authoring/catalog/packet-blueprints.json", mime_type="application/json"
    )
    def authoring_packet_blueprints_resource() -> str:
        return service.authoring_packet_blueprints_resource().text

    @mcp.resource("wellplot://authoring/catalog/style-presets.json", mime_type="application/json")
    def authoring_style_presets_resource() -> str:
        return service.authoring_style_presets_resource().text

    @mcp.resource("wellplot://authoring/catalog/header-fields.json", mime_type="application/json")
    def authoring_header_fields_resource() -> str:
        return service.authoring_header_fields_resource().text

    @mcp.resource(
        "wellplot://authoring/catalog/header-key-aliases.json", mime_type="application/json"
    )
    def authoring_header_key_aliases_resource() -> str:
        return service.authoring_header_key_aliases_resource().text

    @mcp.resource("wellplot://authoring/catalog/channel-aliases.json", mime_type="application/json")
    def authoring_channel_aliases_resource() -> str:
        return service.authoring_channel_aliases_resource().text


def _register_prompts(mcp: FastMCP) -> None:
    """Register workflow prompts without embedding provider behavior in tools."""

    @mcp.prompt()
    def review_logfile(logfile_path: str) -> str:
        return service.review_logfile_prompt(logfile_path)

    @mcp.prompt()
    def preview_logfile(logfile_path: str, focus: str | None = None) -> str:
        return service.preview_logfile_prompt(logfile_path, focus)

    @mcp.prompt()
    def start_from_example(example_id: str, goal: str) -> str:
        return service.start_from_example_prompt(example_id, goal)

    @mcp.prompt()
    def author_plot_from_request(
        goal: str,
        logfile_path: str | None = None,
        example_id: str | None = None,
    ) -> str:
        return service.author_plot_from_request_prompt(
            goal,
            logfile_path=logfile_path,
            example_id=example_id,
        )

    @mcp.prompt()
    def revise_plot_from_feedback(logfile_path: str, feedback: str) -> str:
        return service.revise_plot_from_feedback_prompt(logfile_path, feedback)

    @mcp.prompt()
    def ingest_header_text(
        logfile_path: str,
        source_text: str,
        source_description: str | None = None,
    ) -> str:
        return service.ingest_header_text_prompt(
            logfile_path,
            source_text,
            source_description=source_description,
        )


def create_mcp_server(root: str | Path | None = None) -> FastMCP:
    """Create the stable 16-responsibility wellplot MCP server."""
    FastMCP, Image, ToolAnnotations = _load_mcp_runtime()
    server_root = service.resolve_server_root(root)
    mcp = FastMCP(
        "wellplot",
        instructions=(
            "wellplot MCP server with a stable, deterministic authoring contract for "
            f"logfiles under the fixed server root {server_root}."
        ),
    )

    register_stable_tools(
        mcp,
        root=server_root,
        image_factory=lambda data: Image(data=data, format="png"),
        annotation_factory=lambda values: ToolAnnotations(**dict(values)),
    )
    _register_resources(mcp)
    _register_prompts(mcp)
    return mcp


def main() -> int:
    """Run the wellplot MCP server over stdio."""
    try:
        server = create_mcp_server()
        from .stdio import run_stdio

        run_stdio(server)
    except DependencyUnavailableError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
