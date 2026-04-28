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

"""Smoke-test an installed wheel via the public package surface."""

from __future__ import annotations

import importlib.util
import os
import sys
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

os.environ.setdefault("MPLBACKEND", "Agg")

from wellplot import (  # noqa: E402
    DatasetBuilder,
    LogBuilder,
    ProgrammaticLogSpec,
    __version__,
    build_documents,
    render_png_bytes,
    render_report,
    report_from_yaml,
    report_to_yaml,
)


def _build_smoke_report() -> ProgrammaticLogSpec:
    depth_ft = np.linspace(1000.0, 1020.0, 21)
    gamma = 75.0 + 12.0 * np.sin((depth_ft - depth_ft.min()) / 4.0)

    dataset = (
        DatasetBuilder(
            name="smoke-main",
            well_metadata={"WELL": "Smoke Test"},
            provenance={"source": "installed-wheel"},
        )
        .add_curve(
            mnemonic="GR",
            values=gamma,
            index=depth_ft,
            index_unit="ft",
            value_unit="gAPI",
            description="Installed wheel gamma-ray smoke curve",
        )
        .build()
    )

    builder = LogBuilder(name="Installed wheel smoke test")
    builder.set_render(backend="matplotlib", output_path="smoke.pdf", dpi=120)
    builder.set_page(
        size="A4",
        orientation="portrait",
        header_height_mm=0,
        footer_height_mm=0,
        track_header_height_mm=12,
        track_gap_mm=0,
    )
    builder.set_depth_axis(unit="ft", scale=240, major_step=10, minor_step=2)
    builder.set_depth_range(1000.0, 1020.0)
    section = builder.add_section(
        "main",
        dataset=dataset,
        title="Main",
        source_name="smoke.memory",
    )
    section.add_track(
        id="depth",
        title="",
        kind="reference",
        width_mm=16,
        reference={"axis": "depth", "define_layout": True, "unit": "ft"},
    )
    section.add_track(
        id="curve",
        title="",
        kind="normal",
        width_mm=36,
    )
    section.add_curve(
        channel="GR",
        track_id="curve",
        label="Gamma Ray",
        scale={"kind": "linear", "min": 0, "max": 150},
        style={"color": "#15803d", "line_width": 0.8},
    )
    return builder.build()


def main() -> int:
    """Run the installed-wheel smoke test and exit with status code zero on success."""
    report = _build_smoke_report()
    documents = build_documents(report)
    if len(documents) != 1:
        raise RuntimeError(f"Expected 1 rendered document, received {len(documents)}.")

    yaml_text = report_to_yaml(report)
    if not isinstance(yaml_text, str) or "log_sections:" not in yaml_text:
        raise RuntimeError("Failed to serialize the report to YAML text.")

    loaded_spec = report_from_yaml(StringIO(yaml_text))
    if loaded_spec.render_backend != "matplotlib":
        raise RuntimeError("Serialized report did not preserve the matplotlib backend.")

    with TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / "installed-wheel-smoke.pdf"
        result = render_report(report, output_path=pdf_path)
        if result.output_path != pdf_path:
            raise RuntimeError("Renderer did not return the expected PDF output path.")
        if not pdf_path.exists() or pdf_path.stat().st_size <= 0:
            raise RuntimeError("Installed wheel smoke render did not produce a non-empty PDF.")

        png_bytes = render_png_bytes(report, dpi=96)
        if not png_bytes:
            raise RuntimeError("Installed wheel smoke render did not produce PNG bytes.")

    if importlib.util.find_spec("mcp") is not None:
        import anyio
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        from wellplot.mcp import create_mcp_server
        from wellplot.mcp.service import production_example_manifest, schema_resource

        server = create_mcp_server()
        if not hasattr(server, "run"):
            raise RuntimeError("wellplot MCP server did not expose a runnable server instance.")

        schema_payload = schema_resource().text
        if '"$schema"' not in schema_payload:
            raise RuntimeError("wellplot MCP schema resource did not contain JSON schema text.")

        example_ids = [item["id"] for item in production_example_manifest()["examples"]]
        if example_ids != ["cbl_log_example", "forge16b_porosity_example"]:
            raise RuntimeError(
                "wellplot MCP example manifest did not expose the expected examples."
            )

        server_command = Path(sys.executable).resolve().with_name("wellplot-mcp")
        if not server_command.exists():
            candidate = server_command.with_suffix(".exe")
            if candidate.exists():
                server_command = candidate
            else:
                raise RuntimeError("Installed wheel smoke test could not locate wellplot-mcp.")

        async def _exercise_stdio_server() -> None:
            server_params = StdioServerParameters(
                command=str(server_command),
                cwd=str(Path.cwd()),
            )
            async with stdio_client(server_params) as streams, ClientSession(*streams) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_names = [tool.name for tool in tools.tools]
                required_tools = {
                    "validate_logfile",
                    "preview_section_png",
                    "preview_track_png",
                    "preview_window_png",
                    "export_example_bundle",
                    "validate_logfile_text",
                    "format_logfile_text",
                    "save_logfile_text",
                }
                if not required_tools.issubset(tool_names):
                    raise RuntimeError(
                        "Installed wheel MCP server did not expose the expected tool set."
                    )
                validation = await session.call_tool(
                    "validate_logfile",
                    {"logfile_path": "examples/cbl_main.log.yaml"},
                )
                if validation.structuredContent.get("valid") is not True:
                    raise RuntimeError("Installed wheel MCP validate_logfile call did not succeed.")

        anyio.run(_exercise_stdio_server)

    print(f"Installed wheel smoke test passed for wellplot {__version__}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
