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

"""Generate walkthrough notebooks for the repository example set."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import re
import subprocess
from copy import deepcopy
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"
NOTEBOOKS_ROOT = EXAMPLES_DIR / "notebooks"
DEVELOPER_NOTEBOOKS_DIR = NOTEBOOKS_ROOT / "developer"
USER_NOTEBOOKS_DIR = NOTEBOOKS_ROOT / "user"
USER_ASSETS_DIR = USER_NOTEBOOKS_DIR / "assets"
USER_COMPUTED_NUMPY_DIR = USER_NOTEBOOKS_DIR / "computed_numpy"
USER_COMPUTED_PANDAS_DIR = USER_NOTEBOOKS_DIR / "computed_pandas"

KERNEL_METADATA = {
    "kernelspec": {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    },
    "language_info": {
        "name": "python",
        "version": "3.12",
    },
}


@dataclass(frozen=True)
class PythonRecipe:
    """Notebook recipe metadata for one Python example script."""

    source: str
    title: str
    summary: str
    learning_goals: tuple[str, ...]
    prerequisites: tuple[str, ...]
    code_cells: tuple[str, ...]
    adaptation_tips: tuple[str, ...]
    install_command: str | None = None
    display_source: bool = True
    self_contained: bool = False


@dataclass(frozen=True)
class PreviewImageSpec:
    """Preview image metadata for one curated user notebook."""

    asset_name: str
    title: str
    summary: str
    page_number: int


@dataclass(frozen=True)
class UserProductionRecipe:
    """Curated notebook metadata for end-user production examples."""

    package_name: str
    title: str
    subtitle: str
    target_user: str
    why_this_example: str
    data_highlights: tuple[str, ...]
    what_to_look_for: tuple[str, ...]
    first_edits: tuple[str, ...]
    keep_in_mind: tuple[str, ...]
    previews: tuple[PreviewImageSpec, ...]


@dataclass(frozen=True)
class UserNotebookPreview:
    """One rendered checkpoint preview embedded in a user tutorial notebook."""

    asset_name: str
    title: str
    summary: str
    page_index: int = 0
    section_id: str | None = None


@dataclass(frozen=True)
class UserNotebookStage:
    """One tutorial stage for a user-facing notebook."""

    slug: str
    title: str
    summary: str
    teaching_points: tuple[str, ...]
    logfile_text: str
    previews: tuple[UserNotebookPreview, ...]


@dataclass(frozen=True)
class UserNotebookTutorial:
    """Tutorial configuration for one user-facing production notebook."""

    package_name: str
    template_text: str
    template_explanation: tuple[str, ...]
    inspection_section_id: str
    inspection_channels: tuple[str, ...]
    inspection_metadata_keys: tuple[str, ...]
    stages: tuple[UserNotebookStage, ...]
    adaptation_tips: tuple[str, ...]


PYTHON_RECIPES: dict[str, PythonRecipe] = {
    "api_dataset_ingest_demo.py": PythonRecipe(
        source="api_dataset_ingest_demo.py",
        title="Dataset Ingestion API Walkthrough",
        summary=(
            "Build a synthetic dataset from dataframe-, series-, and raster-style inputs, "
            "merge the channels into one working dataset, and save a quick visual check."
        ),
        learning_goals=(
            "Create an in-memory dataset without starting from LAS or DLIS files.",
            "Add scalar curves from pandas data structures and add a 2D raster channel.",
            "Merge raw and derived channels into one validated working dataset.",
            "Save a quick PNG preview before moving on to full report layout work.",
        ),
        prerequisites=("pandas",),
        code_cells=(
            dedent(
                """
                # Import the example module so we can reuse its self-contained recipe.
                import api_dataset_ingest_demo as demo

                # Run the example end to end exactly as the repository script does.
                # This is the fastest way to confirm that the ingestion workflow is
                # healthy before you start changing curve names, units, or metadata.
                demo.main()
                """
            ).strip(),
        ),
        adaptation_tips=(
            "Replace the synthetic arrays with curves loaded from your own preprocessing step.",
            "Add more `add_curve(...)`, `add_series(...)`, or `add_raster(...)` calls as soon as the base dataset validates cleanly.",
            "Keep the quick PNG preview pattern if you want a fast QC artifact before building a full report packet.",
        ),
    ),
    "api_dataset_alignment_demo.py": PythonRecipe(
        source="api_dataset_alignment_demo.py",
        title="Dataset Alignment Walkthrough",
        summary=(
            "Start from channels sampled on different depth grids, align them to a shared "
            "index, convert depth units, and render the normalized result."
        ),
        learning_goals=(
            "Sort descending or irregular input indices into the order expected by the renderer.",
            "Reindex curves and rasters onto a shared sampling grid before layout binding.",
            "Convert depth units at the dataset stage instead of hard-coding unit changes later.",
            "Render a simple report once the channels share the same depth basis.",
        ),
        prerequisites=(),
        code_cells=(
            dedent(
                """
                # Import the example helpers so the notebook stays close to the script version.
                import api_dataset_alignment_demo as demo

                # Build the aligned dataset and inspect the normalized channels.
                dataset = demo.build_aligned_dataset()
                print("Channels:", sorted(dataset.channels))
                for mnemonic in ("GR", "CBL", "VDL_SYN"):
                    channel = dataset.get_channel(mnemonic)
                    print(
                        f"{mnemonic}: depth_unit={channel.depth_unit}, "
                        f"samples={channel.depth.size}"
                    )
                """
            ).strip(),
            dedent(
                """
                # Build the report that consumes the aligned dataset and render it to the
                # same workspace output used by the example script.
                from wellplot import render_report

                report = demo.build_report(dataset)
                output_path = WORKSPACE_RENDERS / "api_dataset_alignment_demo.pdf"
                result = render_report(report, output_path=output_path)
                print("Pages:", result.page_count)
                print("Rendered:", result.output_path)
                """
            ).strip(),
        ),
        adaptation_tips=(
            "Use `sort_index(...)` first whenever incoming data arrives in descending acquisition order.",
            "Use `reindex_to(...)` early if later calculations assume one common depth axis.",
            "Convert the dataset index unit once and keep the report layout in that same unit to avoid accidental mixed-unit plots.",
        ),
    ),
    "api_dataset_merge_demo.py": PythonRecipe(
        source="api_dataset_merge_demo.py",
        title="Dataset Merge Walkthrough",
        summary=(
            "Combine raw and processed datasets, handle mnemonic collisions safely, and "
            "inspect the merge history captured in dataset provenance."
        ),
        learning_goals=(
            "Separate raw acquisition data from derived or QC datasets before merging them.",
            "Choose an explicit collision policy instead of silently overwriting matching mnemonics.",
            "Use merge-history provenance to understand how the final working dataset was assembled.",
        ),
        prerequisites=(),
        code_cells=(
            dedent(
                """
                # Import the example module and the merge builder helper used in the script.
                import api_dataset_merge_demo as demo
                from wellplot import DatasetBuilder

                # Build the raw and processed inputs separately so you can inspect what is
                # about to be merged and decide how to handle name collisions.
                raw = demo.build_raw_dataset()
                processed = demo.build_processed_dataset()
                print("Raw channels:", sorted(raw.channels))
                print("Processed channels:", sorted(processed.channels))

                # Merge with collision='rename' so the derived GR channel remains available
                # without replacing the raw GR curve.
                merged = (
                    DatasetBuilder(name="merged")
                    .merge(raw, merge_well_metadata=True, merge_provenance=True)
                    .merge(
                        processed,
                        collision="rename",
                        rename_template="{mnemonic}_{dataset}",
                    )
                    .build()
                )

                print("Merged channels:", sorted(merged.channels))
                print("Merge history:", merged.provenance["merge_history"])
                print("Renamed channel metadata:", merged.get_channel("GR_qc").metadata)
                """
            ).strip(),
        ),
        adaptation_tips=(
            "Use `collision='rename'` when both the raw and processed versions of a mnemonic need to stay visible.",
            "Use provenance merges when downstream users need to understand where each channel came from.",
            "Promote the merged dataset to your layout layer only after the final channel names are stable.",
        ),
    ),
    "api_layout_render_demo.py": PythonRecipe(
        source="api_layout_render_demo.py",
        title="Programmatic Layout Walkthrough",
        summary=(
            "Build a report packet entirely in Python, define tracks and bindings in memory, "
            "and render the result without hand-authoring YAML."
        ),
        learning_goals=(
            "Use `LogBuilder` to define page settings, depth settings, sections, tracks, and bindings.",
            "Keep the dataset and layout steps separate so the report remains easy to adapt later.",
            "Render in-memory layouts directly from a notebook session.",
        ),
        prerequisites=(),
        code_cells=(
            dedent(
                """
                # Import the example helpers and build the synthetic dataset that feeds the
                # programmatic layout.
                import api_layout_render_demo as demo

                dataset = demo.build_dataset()
                print("Channels:", sorted(dataset.channels))
                print("Depth range:", dataset.depth_range("ft"))
                """
            ).strip(),
            dedent(
                """
                # Build the report in memory and render it without forcing an output path so
                # the first figure is available directly in the notebook.
                from wellplot import render_report

                report = demo.build_report(dataset)
                result = render_report(report)
                print("Pages:", result.page_count)
                result.artifact[0]
                """
            ).strip(),
            dedent(
                """
                # Save the same report to a PDF once the in-notebook preview looks correct.
                output_path = WORKSPACE_RENDERS / "api_layout_render_demo.pdf"
                saved = render_report(report, output_path=output_path)
                print("Rendered:", saved.output_path)
                """
            ).strip(),
        ),
        adaptation_tips=(
            "Use programmatic layout when your report design is driven by upstream Python logic or notebook calculations.",
            "Keep section IDs and track IDs stable before you start adding many curve bindings.",
            "Preview in memory first, then write the PDF only after the layout contract looks right.",
        ),
    ),
    "api_partial_render_demo.py": PythonRecipe(
        source="api_partial_render_demo.py",
        title="Partial Rendering Walkthrough",
        summary=(
            "Render one section, one subset of tracks, or one depth window from a shared "
            "report definition without cloning the full layout."
        ),
        learning_goals=(
            "Reuse one canonical report definition for section, track, and window-level previews.",
            "Generate lighter QC artifacts before spending time on full-packet tuning.",
            "Keep scoped renders aligned with the same underlying track and binding contract.",
        ),
        prerequisites=(),
        code_cells=(
            dedent(
                """
                # Reuse the base layout demo so the partial renders all start from the same
                # canonical report definition.
                import api_layout_render_demo as base_demo
                from wellplot import render_section, render_track, render_window

                dataset = base_demo.build_dataset()
                report = base_demo.build_report(dataset)
                """
            ).strip(),
            dedent(
                """
                # Render the section, one selected track, and one depth window to separate
                # workspace outputs so you can compare the scopes directly.
                section_path = WORKSPACE_RENDERS / "api_partial_section_demo.pdf"
                track_path = WORKSPACE_RENDERS / "api_partial_track_demo.pdf"
                window_path = WORKSPACE_RENDERS / "api_partial_window_demo.pdf"

                section_result = render_section(report, section_id="main", output_path=section_path)
                track_result = render_track(
                    report,
                    section_id="main",
                    track_ids=["combo"],
                    output_path=track_path,
                )
                window_result = render_window(
                    report,
                    depth_range=(8300.0, 8400.0),
                    depth_range_unit="ft",
                    output_path=window_path,
                )

                print("Section pages:", section_result.page_count)
                print("Track pages:", track_result.page_count)
                print("Window pages:", window_result.page_count)
                print("Saved:", section_path)
                print("Saved:", track_path)
                print("Saved:", window_path)
                """
            ).strip(),
        ),
        adaptation_tips=(
            "Use partial renders whenever a full multisection report is too heavy for quick visual iteration.",
            "Track-scoped renders are useful for tuning fills, callouts, and header behavior in isolation.",
            "Window-scoped renders are the fastest way to inspect a tight interval before widening the packet again.",
        ),
    ),
    "api_notebook_bytes_demo.py": PythonRecipe(
        source="api_notebook_bytes_demo.py",
        title="Notebook Byte-Render Walkthrough",
        summary=(
            "Generate in-memory PNG and SVG outputs for notebook, dashboard, or web-style "
            "workflows without saving a PDF first."
        ),
        learning_goals=(
            "Use the byte-oriented render helpers designed specifically for notebook workflows.",
            "Capture section, window, and whole-page previews as binary assets.",
            "Understand when to prefer PNG or SVG output over a saved PDF.",
        ),
        prerequisites=(),
        code_cells=(
            dedent(
                """
                # Build the shared synthetic layout used by the byte-render example.
                from IPython.display import SVG, Image, display

                import api_layout_render_demo as base_demo
                from wellplot import render_section_png, render_svg_bytes, render_window_png

                dataset = base_demo.build_dataset()
                report = base_demo.build_report(dataset)
                """
            ).strip(),
            dedent(
                """
                # Render notebook-friendly image bytes instead of writing a PDF immediately.
                section_png = render_section_png(report, section_id="main", page_index=0, dpi=140)
                window_png = render_window_png(
                    report,
                    depth_range=(8300.0, 8400.0),
                    depth_range_unit="ft",
                    page_index=0,
                    dpi=140,
                )
                report_svg = render_svg_bytes(report, page_index=0)

                display(Image(data=section_png))
                display(Image(data=window_png))
                display(SVG(report_svg.decode("utf-8")))
                """
            ).strip(),
            dedent(
                """
                # Persist the byte outputs only after you are happy with the in-notebook
                # previews.
                section_png_path = WORKSPACE_RENDERS / "api_notebook_section.png"
                window_png_path = WORKSPACE_RENDERS / "api_notebook_window.png"
                report_svg_path = WORKSPACE_RENDERS / "api_notebook_report_page.svg"

                section_png_path.write_bytes(section_png)
                window_png_path.write_bytes(window_png)
                report_svg_path.write_bytes(report_svg)

                print("Saved:", section_png_path)
                print("Saved:", window_png_path)
                print("Saved:", report_svg_path)
                """
            ).strip(),
        ),
        adaptation_tips=(
            "Prefer the byte-render helpers when your notebook needs inline previews rather than a saved file path.",
            "Use PNG for quick raster previews and SVG when you want scalable vector output.",
            "Persist the image bytes only after the preview looks right, so your workspace does not fill with throwaway artifacts.",
        ),
    ),
    "api_end_to_end_demo.py": PythonRecipe(
        source="api_end_to_end_demo.py",
        title="End-to-End API Walkthrough",
        summary=(
            "Run the full recipe: build raw and processed datasets, merge them into one "
            "working dataset, build a report, save YAML, and render both PDF and PNG outputs."
        ),
        learning_goals=(
            "Connect ingestion, processing, merge, layout, rendering, and serialization in one workflow.",
            "Keep raw and processed channels visible together inside a single working dataset.",
            "Produce both final artifacts and lighter preview artifacts from the same report definition.",
        ),
        prerequisites=("pandas",),
        code_cells=(
            dedent(
                """
                # Import the example module and build the merged working dataset used by the
                # end-to-end recipe.
                import api_end_to_end_demo as demo

                dataset = demo.build_working_dataset()
                print("Channels:", sorted(dataset.channels))
                print("Depth range:", dataset.depth_range("ft"))
                """
            ).strip(),
            dedent(
                """
                # Build the report and save a normalized YAML representation that you can
                # version-control or hand off to a YAML-first workflow later.
                from wellplot import render_report, render_window_png, save_report

                report = demo.build_report(dataset)
                report_yaml_path = WORKSPACE_RENDERS / "api_end_to_end_report.yaml"
                save_report(report, report_yaml_path)
                print("Saved report YAML:", report_yaml_path)
                """
            ).strip(),
            dedent(
                """
                # Render the full report to PDF and save one smaller PNG window for quick QC.
                pdf_path = WORKSPACE_RENDERS / "api_end_to_end_demo.pdf"
                png_path = WORKSPACE_RENDERS / "api_end_to_end_window.png"

                pdf_result = render_report(report, output_path=pdf_path)
                window_png = render_window_png(
                    report,
                    depth_range=(8360.0, 8420.0),
                    depth_range_unit="ft",
                    page_index=0,
                    dpi=140,
                )
                png_path.write_bytes(window_png)

                print("Pages:", pdf_result.page_count)
                print("Saved PDF:", pdf_path)
                print("Saved PNG:", png_path)
                """
            ).strip(),
        ),
        adaptation_tips=(
            "Keep the raw and processed datasets separate until the merge policy is settled.",
            "Save the normalized report YAML when you want a notebook-built layout to become a reusable file artifact.",
            "Use a small PNG window as a fast QC snapshot even if the final deliverable is PDF.",
        ),
    ),
    "api_serialize_demo.py": PythonRecipe(
        source="api_serialize_demo.py",
        title="Serialization Walkthrough",
        summary=(
            "Build a small report in memory, convert it into normalized YAML artifacts, "
            "and inspect the saved document and report files."
        ),
        learning_goals=(
            "Understand the difference between report-level and document-level serialization.",
            "Use YAML export as a bridge between notebook prototypes and file-based workflows.",
            "Inspect the normalized artifacts that `wellplot` persists after builder composition.",
        ),
        prerequisites=(),
        code_cells=(
            dedent(
                """
                # Import the example module and build the smallest useful report for a
                # serialization walkthrough.
                import api_serialize_demo as demo
                from wellplot import build_documents, save_document, save_report

                dataset = demo.build_dataset()
                report = demo.build_report(dataset)
                documents = build_documents(report)
                print("Document count:", len(documents))
                """
            ).strip(),
            dedent(
                """
                # Save both the report-level YAML and the first normalized document YAML so
                # you can compare the two persistence surfaces side by side.
                report_yaml_path = WORKSPACE_RENDERS / "api_serialize_report.yaml"
                document_yaml_path = WORKSPACE_RENDERS / "api_serialize_document.yaml"

                save_report(report, report_yaml_path)
                save_document(documents[0], document_yaml_path)

                print("Saved report YAML:", report_yaml_path)
                print("Saved document YAML:", document_yaml_path)
                """
            ).strip(),
            dedent(
                """
                # Read back a short slice of each file so the notebook documents what was
                # written without forcing you to leave the recipe.
                print(report_yaml_path.read_text()[:800])
                print("\\n---\\n")
                print(document_yaml_path.read_text()[:800])
                """
            ).strip(),
        ),
        adaptation_tips=(
            "Save the report YAML when you want to preserve the higher-level authoring structure.",
            "Save the document YAML when you need the normalized render-ready form for debugging or downstream tooling.",
            "Inspect a short text slice in the notebook before diffing the files in your editor.",
        ),
    ),
    "mcp_workflow_demo.py": PythonRecipe(
        source="mcp_workflow_demo.py",
        title="Experimental MCP Workflow Walkthrough",
        summary=(
            "Launch the local stdio MCP server, inspect its public contract, preview a "
            "production logfile, exercise the writable authoring tools, and walk a "
            "copied header packet through deterministic MCP ingestion without dropping "
            "down to the direct Python or YAML pipeline."
        ),
        learning_goals=(
            "Start the experimental `wellplot-mcp` surface from a notebook-friendly Python workflow.",
            "Inspect the registered tools, resources, resource templates, and prompts before using them.",
            "Use MCP tool calls to validate, inspect, and preview a production logfile at full-report, section, track, and window scopes.",
            "Round-trip a full logfile through MCP text validation, formatting, export, save, and explicit render-to-file calls.",
            "Parse copied header text, inspect exact heading slots, preview the mapping, apply it, and preview the first report page through MCP.",
        ),
        prerequisites=("mcp", "dlis"),
        code_cells=(
            dedent(
                """
                # Import the MCP helper module and inspect the default example paths it
                # uses for the walkthrough.
                import mcp_workflow_demo as demo

                print("Demo logfile:", demo.DEFAULT_LOGFILE)
                print("Header-ingestion logfile:", demo.DEFAULT_HEADER_LOGFILE)
                print("Demo base dir:", demo.DEFAULT_BASE_DIR)
                print("Demo output root:", demo.DEFAULT_OUTPUT_ROOT)
                """
            ).strip(),
            dedent(
                """
                # Ask the MCP server what it exposes before calling the workflow tools.
                contract = await demo.collect_server_contract()

                print("Tools:")
                for name in contract["tools"]:
                    print(" -", name)

                print("\\nResources:")
                for uri in contract["resources"]:
                    print(" -", uri)

                print("\\nResource templates:")
                for uri_template in contract["resource_templates"]:
                    print(" -", uri_template)

                print("\\nPrompts:")
                for name in contract["prompts"]:
                    print(" -", name)

                print("\\nPackaged production examples:")
                for example in contract["example_manifest"]["examples"]:
                    print(f" - {example['id']}: {example['title']}")

                print("\\nreview_logfile prompt preview:\\n")
                print(contract["review_prompt"])
                """
            ).strip(),
            dedent(
                """
                # Validate, inspect, and preview the production logfile through MCP only.
                from IPython.display import Image, display

                review = await demo.run_review_flow()

                print("Validation:")
                print(review["validation"])
                print("\\nSelected section:", review["selected_section_id"])
                print("Selected tracks:", review["selected_track_ids"])
                print("Window depth range:", review["window_depth_range"])
                print("\\nResolved section ids:", review["inspection"]["section_ids"])

                display(Image(data=review["section_preview_png"]))
                display(Image(data=review["track_preview_png"]))
                display(Image(data=review["window_preview_png"]))
                """
            ).strip(),
            dedent(
                """
                # Exercise the writable MCP tools against the same production example.
                from IPython.display import Code, display

                authoring = await demo.run_authoring_flow()

                print("Text validation:")
                print(authoring["text_validation"])
                print("\\nExported files:")
                for path in authoring["export"]["written_files"]:
                    print(" -", path)
                print("\\nSaved logfile:", authoring["save"]["output_path"])
                print("Rendered logfile:", authoring["rendered_logfile"])
                print("Rendered PDF:", authoring["render"]["output_path"])

                preview_yaml = "\\n".join(authoring["formatted_yaml"].splitlines()[:80])
                display(Code(preview_yaml, language="yaml"))
                """
            ).strip(),
            dedent(
                """
                # Clone a draft, parse copied header text, preview the mapping, apply it,
                # and preview the first report page through MCP only.
                import json
                from IPython.display import Image, Code, display

                header_demo = await demo.run_header_ingestion_flow()

                print("Header draft:", header_demo["draft_logfile"])
                print("Mapped values:")
                print(header_demo["mapped_values"])

                print("\\nParsed pairs:")
                for pair in header_demo["parsed"]["pairs"]:
                    print(f" - {pair['key']}: {pair['value']}")

                print("\\nPrompt excerpt:\\n")
                print("\\n".join(header_demo["ingest_prompt"].splitlines()[:14]))

                print("\\nReport-page style presets:")
                for preset in header_demo["style_presets"]["presets"]:
                    print(f" - {preset['id']}: {preset['label']}")

                print("\\nPreview warnings:", header_demo["preview"]["warnings"])
                print("Applied assignments:", len(header_demo["apply"]["applied_assignments"]))

                predicted_patch = json.dumps(
                    header_demo["preview"]["predicted_heading_patch"],
                    indent=2,
                )
                display(Code(predicted_patch, language="json"))
                display(Image(data=header_demo["page_preview_png"]))
                """
            ).strip(),
        ),
        adaptation_tips=(
            "Keep the server root pointed at a narrow working directory when you move from a repo demo to a real job directory.",
            "Use `inspect_logfile(...)` first and then drive the narrow preview tools with the returned section and track ids.",
            "Treat `format_logfile_text(...)` and `save_logfile_text(...)` as normalization steps, not as comment-preserving editors.",
            "Use explicit keys like `general_field.company`, `detail.date`, or `service_title_1` when copied header text could map to multiple slots.",
        ),
    ),
    "mcp_natural_language_demo.py": PythonRecipe(
        source="mcp_natural_language_demo.py",
        title="Natural-Language MCP Authoring With OpenAI",
        summary=(
            "Use the public `wellplot.agent` API to drive local `wellplot-mcp` "
            "authoring from natural-language instructions and recreate a production "
            "example variant without embedding provider or MCP glue in the notebook."
        ),
        learning_goals=(
            "Create one public `AuthoringSession` backed by local stdio MCP and the OpenAI adapter.",
            "Run one natural-language authoring request against a packaged production example.",
            "Inspect the tool trace, structural change summary, and rendered previews from the returned `AuthoringResult`.",
            "Persist the in-memory preview PNGs next to the generated draft logfile through the result helper.",
        ),
        prerequisites=("agent", "las", "notebook"),
        install_command='pip install "wellplot[agent,las,notebook]"',
        display_source=True,
        code_cells=(
            dedent(
                """
                # Import the public authoring API from the installed package.
                import os
                from pathlib import Path
                from wellplot.agent import AuthoringSession

                DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
                DEFAULT_EXAMPLE_ID = "forge16b_porosity_example"
                DEFAULT_OUTPUT_LOGFILE = Path("workspace/mcp_demo/openai_forge16b_recreated.log.yaml")
                """
            ).strip(),
            dedent(
                """
                # Edit these values before rerunning the notebook on a different target.
                GOAL = (
                    "Recreate the forge16b porosity example as a simplified interpretation "
                    "packet. Keep one GR/SP track, one depth track, one resistivity track, "
                    "and one porosity overlay track with RHOB and NPHI. Shorten the remarks "
                    "to one concise block and simplify the heading."
                )
                EXAMPLE_ID = DEFAULT_EXAMPLE_ID
                MODEL = DEFAULT_MODEL
                OUTPUT_LOGFILE = DEFAULT_OUTPUT_LOGFILE

                print("Model:", MODEL)
                print("Seed example:", EXAMPLE_ID)
                print("Draft output:", OUTPUT_LOGFILE)
                print("Server root:", REPO_ROOT)

                session = AuthoringSession.from_local_mcp(
                    provider="openai",
                    model=MODEL,
                    server_root=REPO_ROOT,
                )
                """
            ).strip(),
            dedent(
                """
                # Run the natural-language authoring loop through the public API.
                from IPython.display import Code, Image, Markdown, display

                authoring = await session.run(
                    goal=GOAL,
                    example_id=EXAMPLE_ID,
                    output_logfile=OUTPUT_LOGFILE,
                )

                preview_paths = authoring.write_preview_artifacts()

                print("Provider:", authoring.provider)
                print("Model:", authoring.model)
                print("Token source:", authoring.credential_source)
                print("Draft logfile:", authoring.draft_logfile)
                print("Preview files:")
                for name, path in preview_paths.items():
                    print(f" - {name}: {path.relative_to(REPO_ROOT)}")

                print("\\nValidation:", authoring.validation)
                print("\\nModel summary:\\n")
                display(Markdown(authoring.final_text or "_No final text returned._"))

                print("\\nTool trace:")
                for item in authoring.tool_trace:
                    print(f" - round {item.round}: {item.name}({item.arguments})")

                print("\\nChange summary:")
                for line in authoring.change_summary.get("summary_lines", []):
                    print(" -", line)

                print("\\nFirst section ids:", authoring.inspect_summary["section_ids"])
                display(Image(data=authoring.report_preview_png))
                display(Image(data=authoring.section_preview_png))

                preview_yaml = "\\n".join(authoring.draft_text.splitlines()[:120])
                display(Code(preview_yaml, language="yaml"))
                """
            ).strip(),
        ),
        adaptation_tips=(
            "Keep secrets in `OPENAI_API_KEY`, `.env.local`, `.env`, `OPENAI_API_KEY.txt`, or `openai_api_key.txt`; those paths stay local and should not be committed.",
            "Start from `forge16b_porosity_example` or another LAS-backed production packet first so the natural-language loop stays fast and reproducible.",
            "Treat the OpenAI model as the planner and `wellplot-mcp` as the deterministic executor; if the result is close but not right, rerun with a tighter goal or follow up with `revise_plot_from_feedback(...)` through the MCP prompt layer.",
        ),
    ),
    "real_data_demo.py": PythonRecipe(
        source="real_data_demo.py",
        title="Real-Data CLI Wrapper Walkthrough",
        summary=(
            "Use the simplest possible script wrapper around `render_from_logfile(...)` to "
            "render a file-based example from Python instead of the shell."
        ),
        learning_goals=(
            "See the minimal Python entry point required to drive a file-based render.",
            "Point the wrapper at a different YAML config without changing the renderer internals.",
            "Reuse the same render pipeline from both notebooks and CLI-style scripts.",
        ),
        prerequisites=("las",),
        code_cells=(
            dedent(
                """
                # Import the high-level file-based renderer and point it at the same example
                # YAML used by the script default.
                from wellplot import render_from_logfile

                logfile_path = EXAMPLES_DIR / "cbl_main.log.yaml"
                result = render_from_logfile(logfile_path)
                print("Rendered:", result.output_path)
                """
            ).strip(),
        ),
        adaptation_tips=(
            "Use this wrapper pattern when a notebook or service already knows the YAML path it wants to render.",
            "Switch the `logfile_path` first before you touch any renderer internals.",
            "Keep CLI-style wrappers thin so the YAML examples remain the source of truth.",
        ),
    ),
    "synthetic_demo.py": PythonRecipe(
        source="synthetic_demo.py",
        title="Legacy Synthetic Triple-Combo Walkthrough",
        summary=(
            "Render the legacy triple-combo document example using a synthetic in-memory "
            "dataset and the lower-level `MatplotlibRenderer` directly."
        ),
        learning_goals=(
            "Understand the older document-plus-dataset render flow that predates the newer logfile pipeline.",
            "Build a synthetic dataset without any external LAS or DLIS dependency.",
            "Render a legacy document definition directly through the renderer backend.",
        ),
        prerequisites=(),
        code_cells=(
            dedent(
                """
                # Import the legacy example helpers and build the synthetic dataset that feeds
                # the triple-combo document.
                import synthetic_demo as demo
                from wellplot import load_document
                from wellplot.renderers import MatplotlibRenderer

                document = load_document(EXAMPLES_DIR / "triple_combo.yaml")
                dataset = demo.build_dataset()
                print("Channels:", sorted(dataset.channels))
                """
            ).strip(),
            dedent(
                """
                # Render the legacy document directly through the backend so you can see the
                # lower-level flow that newer logfile examples now wrap for you.
                renderer = MatplotlibRenderer()
                output_path = WORKSPACE_RENDERS / "synthetic_triple_combo.pdf"
                result = renderer.render(document, dataset, output_path=output_path)
                print("Pages:", result.page_count)
                print("Rendered:", result.output_path)
                """
            ).strip(),
        ),
        adaptation_tips=(
            "Use this pattern when you are studying the older document model or maintaining legacy examples.",
            "Prefer the newer logfile or builder flows for new end-user recipes unless you specifically need the lower-level renderer contract.",
            "Keep synthetic datasets handy for layout experiments that should not depend on external data files.",
        ),
    ),
    "cbl_vdl_array_mvp_demo.py": PythonRecipe(
        source="cbl_vdl_array_mvp_demo.py",
        title="Synthetic CBL/VDL YAML Walkthrough",
        summary=(
            "Pair a synthetic in-memory dataset with a log YAML file and render it through "
            "the logfile document builder instead of the higher-level data-loading pipeline."
        ),
        learning_goals=(
            "See how a YAML-defined layout can be driven by a synthetic dataset instead of a file-backed one.",
            "Understand the bridge from `load_logfile(...)` to `build_documents_for_logfile(...)`.",
            "Render a YAML-defined array track without depending on external DLIS files.",
        ),
        prerequisites=(),
        code_cells=(
            dedent(
                """
                # Import the legacy YAML demo helpers and load the corresponding log-file
                # specification.
                import cbl_vdl_array_mvp_demo as demo
                from wellplot.logfile import build_documents_for_logfile, load_logfile
                from wellplot.renderers import MatplotlibRenderer

                logfile_path = EXAMPLES_DIR / "cbl_vdl_array_mvp.log.yaml"
                spec = load_logfile(logfile_path)
                dataset = demo.build_synthetic_dataset()
                documents = build_documents_for_logfile(
                    spec,
                    dataset,
                    source_path=Path("synthetic_cbl_vdl.dlis"),
                )
                print("Document count:", len(documents))
                """
            ).strip(),
            dedent(
                """
                # Render the YAML-defined documents using the same backend configuration read
                # from the log-file specification.
                renderer_kwargs = {"dpi": spec.render_dpi}
                if spec.render_continuous_strip_page_height_mm is not None:
                    renderer_kwargs["continuous_strip_page_height_mm"] = (
                        spec.render_continuous_strip_page_height_mm
                    )
                style = spec.render_matplotlib.get("style")
                if style is not None:
                    renderer_kwargs["style"] = style

                renderer = MatplotlibRenderer(**renderer_kwargs)
                output_path = demo.resolve_output(logfile_path, spec.render_output_path)
                result = renderer.render_documents(documents, dataset, output_path=output_path)
                print("Pages:", result.page_count)
                print("Rendered:", result.output_path)
                """
            ).strip(),
        ),
        adaptation_tips=(
            "Use this bridge when you want a stable YAML layout but your data source is synthetic or preprocessed in memory.",
            "Keep the synthetic `source_path` explicit so downstream metadata stays understandable.",
            "Once the synthetic dataset stabilizes, switch to the higher-level pipeline only if you also want file-backed loading.",
        ),
    ),
}


USER_PRODUCTION_RECIPES: dict[str, UserProductionRecipe] = {
    "cbl_log_example": UserProductionRecipe(
        package_name="cbl_log_example",
        title="CBL/VDL Packet User Walkthrough",
        subtitle=(
            "Build a CBL/VDL interpretation packet from DLIS data one stage at a time, "
            "starting with a reusable template and finishing with the repeat pass."
        ),
        target_user=(
            "A geologist, petrophysicist, or subsurface engineer who wants a concrete example "
            "of how `wellplot` reconstructs a CBL/VDL packet from public or repository-backed "
            "DLIS data."
        ),
        why_this_example=(
            "This is the best starting point if you care about packet-style cement evaluation "
            "output rather than isolated renderer features. It includes the heading, remarks, "
            "main-pass strip, repeat-pass strip, and tail pages."
        ),
        data_highlights=(
            "Source DLIS files: `workspace/data/CBL_Main.dlis` and `workspace/data/CBL_Repeat.dlis`.",
            "Reference packet for visual comparison: `workspace/renders/CBL_log_example.Pdf`.",
            "Key curves shown in the strips: `ECGR_STGC`, `TT`, `TENS`, `MTEM`, `CBL`, `VDL`, `STIT`, `TDSP`, and `VSEC`.",
        ),
        what_to_look_for=(
            "The opening page establishes the report context and remarks before the strip sections start.",
            "The main-pass strip combines a reference overview, dual-scale CBL, and VDL texture in one packet section.",
            "The repeat-pass strip lets you compare the second pass without rebuilding the packet structure.",
        ),
        first_edits=(
            "Change the DLIS source file paths first if you are adapting the example to another job.",
            "Update the remarks text before you start changing track geometry or styling.",
            "Adjust section depth ranges only after you confirm the packet renders cleanly with the new data.",
        ),
        keep_in_mind=(
            "This packet is a new `wellplot` rendering, not an original vendor deliverable.",
            "Unsupported vendor-only content such as calibration tables and disclaimer pages is intentionally omitted.",
            "If you need the raw YAML and binding details, use the developer notebook for this same example.",
        ),
        previews=(
            PreviewImageSpec(
                asset_name="cbl_log_example_opening_page.png",
                title="Opening packet page",
                summary="Shows the report heading and remarks context before the strip sections.",
                page_number=1,
            ),
            PreviewImageSpec(
                asset_name="cbl_log_example_main_pass.png",
                title="Main-pass strip preview",
                summary="Shows the first strip section with the reference overview, dual-scale CBL, and VDL raster.",
                page_number=2,
            ),
        ),
    ),
    "forge16b_porosity_example": UserProductionRecipe(
        package_name="forge16b_porosity_example",
        title="Open-Hole Porosity Packet User Walkthrough",
        subtitle=(
            "Build an open-hole porosity packet from a public LAS file one stage at a time, "
            "from reusable template to gas-crossover fill and the final two-window packet."
        ),
        target_user=(
            "A geologist or petrophysicist who wants to adapt a compact open-hole interpretation "
            "packet without having to learn the `wellplot` YAML layout structure first."
        ),
        why_this_example=(
            "This example keeps a production-ready report template and swaps in the public "
            "`30-23a-3 8117_d.las` file. It is the clearest starting point for a LAS-backed "
            "open-hole packet with header metadata, remarks, and two review windows."
        ),
        data_highlights=(
            "Source LAS file: `workspace/data/30-23a-3 8117_d.las`.",
            "The heading is populated directly from the LAS well header rather than hard-coded placeholders.",
            "The strip sections focus on `GR`, `SP`, `ILD`, `ILM`, `MSFL`, `NPHI`, `RHOB`, `PEF`, and `DRHO`.",
        ),
        what_to_look_for=(
            "The opening page shows how the retained template uses the LAS header metadata and production remarks.",
            "The upper review window is the quickest place to confirm the resistivity and porosity tracks are behaving correctly.",
            "The porosity track highlights density-neutron crossover as gas-fill interpretation space rather than a density-baseline fill.",
        ),
        first_edits=(
            "Change the LAS file path first if you want to point the packet at another well.",
            "Update the upper and lower depth windows before you tune track styling or curve scales.",
            "Refresh the remarks text so the packet reflects your production context rather than the shipped example wording.",
        ),
        keep_in_mind=(
            "This is a reproducible open-hole packet example, not a certified vendor-issued log packet.",
            "The packet keeps the public-data and IP boundary explicit; preserve that language if you publish derivatives.",
            "If you need the raw YAML and template internals, use the developer notebook for this same example.",
        ),
        previews=(
            PreviewImageSpec(
                asset_name="forge16b_porosity_example_opening_page.png",
                title="Opening packet page",
                summary="Shows the retained report template, header metadata, and remarks blocks.",
                page_number=1,
            ),
            PreviewImageSpec(
                asset_name="forge16b_porosity_example_upper_review.png",
                title="Upper open-hole review",
                summary="Shows the GR/SP, resistivity, and density-neutron interpretation view with gas crossover fill.",
                page_number=2,
            ),
        ),
    ),
}


def markdown_cell(text: str) -> dict[str, object]:
    """Return a notebook markdown cell."""
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": _as_lines(text),
    }


def code_cell(
    text: str,
    *,
    outputs: list[dict[str, object]] | None = None,
    execution_count: int | None = None,
) -> dict[str, object]:
    """Return a notebook code cell."""
    return {
        "cell_type": "code",
        "execution_count": execution_count,
        "metadata": {},
        "outputs": [] if outputs is None else outputs,
        "source": _as_lines(text),
    }


def stream_output(text: str) -> dict[str, object]:
    """Return a stdout stream output for one code cell."""
    return {
        "name": "stdout",
        "output_type": "stream",
        "text": _as_lines(text),
    }


def display_data_output(
    data: dict[str, object],
    *,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return a display_data output payload."""
    return {
        "data": data,
        "metadata": {} if metadata is None else metadata,
        "output_type": "display_data",
    }


def markdown_output(text: str) -> dict[str, object]:
    """Return a markdown display output."""
    return display_data_output({"text/markdown": text})


def png_output(png_bytes: bytes) -> dict[str, object]:
    """Return a PNG display output."""
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return display_data_output({"image/png": encoded})


def _as_lines(text: str) -> list[str]:
    """Return notebook cell source lines with trailing newlines preserved."""
    normalized = dedent(text).strip("\n")
    return [] if not normalized else [f"{line}\n" for line in normalized.splitlines()]


def _write_if_changed(path: Path, content: str) -> bool:
    """Write text content only when the file contents changed."""
    if path.exists() and path.read_text() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return True


def _write_bytes_if_changed(path: Path, content: bytes) -> bool:
    """Write binary content only when the file contents changed."""
    if path.exists() and path.read_bytes() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return True


def _yaml_text(mapping: dict[str, object]) -> str:
    """Return a stable YAML string for notebook tutorial snippets."""
    return yaml.safe_dump(mapping, sort_keys=False).strip()


def _python_identifier(value: str) -> str:
    """Return a Python-friendly identifier derived from a slug."""
    return re.sub(r"[^0-9a-zA-Z_]+", "_", value).strip("_")


def _repo_setup_code() -> str:
    """Return the common notebook setup code used in generated recipes."""
    return dedent(
        """
        import sys
        from pathlib import Path

        try:
            import wellplot
        except ImportError as exc:
            raise RuntimeError(
                "Install the published 'wellplot' package in the active "
                "environment before running this notebook."
            ) from exc

        # Walk upward from the current working directory until we find the
        # repository checkout that holds the example sources and sample data.
        cwd = Path.cwd().resolve()
        REPO_ROOT = next((path for path in (cwd, *cwd.parents) if (path / "examples").exists()), None)
        if REPO_ROOT is None:
            raise RuntimeError(
                "Run this notebook from a checkout of the wellplot repository "
                "so the example files and sample data are available."
            )

        EXAMPLES_DIR = REPO_ROOT / "examples"
        WORKSPACE_DIR = REPO_ROOT / "workspace"
        WORKSPACE_RENDERS = WORKSPACE_DIR / "renders"
        WORKSPACE_RENDERS.mkdir(parents=True, exist_ok=True)

        examples_path = str(EXAMPLES_DIR)
        if examples_path not in sys.path:
            sys.path.insert(0, examples_path)

        print("wellplot version:", wellplot.__version__)
        print("Examples root:", EXAMPLES_DIR)
        print("Render output:", WORKSPACE_RENDERS)
        """
    ).strip()


def _relative_display_path(path: Path) -> str:
    """Return one path relative to the repository root when possible."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _production_package_dir(package_name: str) -> Path:
    """Return the directory for one production example package."""
    return EXAMPLES_DIR / "production" / package_name


def _production_logfile_path(package_name: str) -> Path:
    """Return the main logfile path for one production example package."""
    return _production_package_dir(package_name) / "full_reconstruction.log.yaml"


def _configured_output_path(logfile_path: Path) -> Path:
    """Return the resolved configured output path for one logfile."""
    mapping = _load_yaml(logfile_path)
    render = mapping.get("render", {})
    if not isinstance(render, dict):
        raise TypeError(f"Expected render mapping in {logfile_path}.")
    configured = str(render.get("output_path", "")).strip()
    if not configured:
        raise ValueError(f"Missing render.output_path in {logfile_path}.")
    output_path = Path(configured)
    if not output_path.is_absolute():
        output_path = (logfile_path.parent / output_path).resolve()
    return output_path


def _ensure_output_pdf(logfile_path: Path, output_path: Path, *, check: bool) -> int:
    """Ensure the configured output PDF exists for preview extraction."""
    if output_path.exists():
        return 0
    if check:
        raise SystemExit(f"Rendered example PDF is missing: {output_path}")

    from wellplot import render_from_logfile

    render_from_logfile(logfile_path)
    if not output_path.exists():
        raise SystemExit(f"Expected rendered example PDF was not created: {output_path}")
    return 1


def _pdf_page_count(pdf_path: Path) -> int:
    """Return the page count for one rendered PDF using mutool."""
    result = subprocess.run(
        ["mutool", "info", str(pdf_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    match = re.search(r"Pages:\s+(\d+)", result.stdout)
    if match is None:
        raise ValueError(f"Could not determine page count for {pdf_path}.")
    return int(match.group(1))


def _pdf_preview_png_bytes(pdf_path: Path, *, page_number: int) -> bytes:
    """Return one PDF page preview as PNG bytes using mutool."""
    with TemporaryDirectory() as temp_dir:
        output_pattern = Path(temp_dir) / "preview-%d.png"
        subprocess.run(
            [
                "mutool",
                "draw",
                "-F",
                "png",
                "-o",
                str(output_pattern),
                str(pdf_path),
                str(page_number),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        preview_path = Path(temp_dir) / f"preview-{page_number}.png"
        return preview_path.read_bytes()


def _user_setup_code(package_name: str) -> str:
    """Return the lightweight setup cell for one user notebook."""
    output_rel = _relative_display_path(
        _configured_output_path(_production_logfile_path(package_name))
    )
    return dedent(
        f"""
        # Run this cell once so the notebook can locate the example package.
        from pathlib import Path

        try:
            import wellplot
        except ImportError as exc:
            raise RuntimeError(
                "Install the published 'wellplot' package in the active environment "
                "before running this notebook."
            ) from exc

        cwd = Path.cwd().resolve()
        REPO_ROOT = next((path for path in (cwd, *cwd.parents) if (path / "examples").exists()), None)
        if REPO_ROOT is None:
            raise RuntimeError(
                "Run this notebook from a checkout of the wellplot repository so the "
                "example files and sample data are available."
            )

        package_dir = REPO_ROOT / "examples" / "production" / "{package_name}"
        logfile_path = package_dir / "full_reconstruction.log.yaml"
        expected_output_pdf = REPO_ROOT / "{output_rel}"

        print("wellplot version:", wellplot.__version__)
        print("Example package:", package_dir.name)
        print("Logfile:", logfile_path.relative_to(REPO_ROOT))
        print("Expected PDF:", expected_output_pdf.relative_to(REPO_ROOT))
        """
    ).strip()


def _user_render_code() -> str:
    """Return the main render cell for a user notebook."""
    return dedent(
        """
        # Run the shipped example exactly as a user would: validate the logfile
        # and render the configured PDF packet.
        from wellplot import load_logfile, render_from_logfile

        spec = load_logfile(logfile_path)
        result = render_from_logfile(logfile_path)

        print("Validated:", spec.name)
        print("Pages created:", result.page_count)
        print("PDF written to:", result.output_path.relative_to(REPO_ROOT))
        """
    ).strip()


def _document_section_id(document: object) -> str:
    """Return the active layout section identifier stored in document metadata."""
    metadata = getattr(document, "metadata", None)
    if isinstance(metadata, dict):
        layout_sections = metadata.get("layout_sections")
        if isinstance(layout_sections, dict):
            active_section = layout_sections.get("active_section")
            if isinstance(active_section, dict):
                section_id = active_section.get("id")
                if isinstance(section_id, str):
                    return section_id
    return ""


def _close_figures(figures: list[object]) -> None:
    """Close one list of Matplotlib figures."""
    try:
        import matplotlib.pyplot as plt

        for figure in figures:
            plt.close(figure)
    except Exception:
        for figure in figures:
            clf = getattr(figure, "clf", None)
            if callable(clf):
                clf()


def _figures_to_png_bytes(
    figures: list[object],
    *,
    page_indexes: tuple[int, ...],
    dpi: int = 140,
) -> tuple[dict[int, bytes], int]:
    """Convert selected Matplotlib figure pages into PNG bytes."""
    page_count = len(figures)
    png_bytes: dict[int, bytes] = {}
    try:
        for page_index in page_indexes:
            if page_index < 0 or page_index >= page_count:
                raise ValueError(
                    f"Requested page_index {page_index} is out of range for {page_count} pages."
                )
            buffer = BytesIO()
            try:
                figures[page_index].savefig(buffer, format="png", dpi=dpi)
                png_bytes[page_index] = buffer.getvalue()
            finally:
                buffer.close()
    finally:
        _close_figures(figures)
    return png_bytes, page_count


def _matplotlib_result_png_bytes(
    figures: list[object],
    *,
    page_index: int = 0,
    dpi: int = 140,
) -> bytes:
    """Return PNG bytes for one rendered Matplotlib figure page."""
    if not figures:
        raise ValueError("No rendered figures were available for PNG preview generation.")
    if page_index < 0 or page_index >= len(figures):
        raise ValueError(
            f"Requested page_index {page_index} is out of range for {len(figures)} pages."
        )

    buffer = BytesIO()
    try:
        figures[page_index].savefig(buffer, format="png", dpi=dpi)
        return buffer.getvalue()
    finally:
        buffer.close()
        _close_figures(figures)


def _render_logfile_figures(
    logfile_path: Path,
    *,
    section_id: str | None = None,
) -> list[object]:
    """Render one logfile to in-memory Matplotlib figures."""
    from wellplot.logfile import (
        build_documents_for_logfile,
        load_datasets_for_logfile,
        load_logfile,
    )
    from wellplot.renderers import MatplotlibRenderer

    spec = load_logfile(logfile_path)
    datasets_by_section, source_paths_by_section = load_datasets_for_logfile(
        spec,
        base_dir=logfile_path.parent,
    )
    documents = build_documents_for_logfile(
        spec,
        datasets_by_section,
        source_path=source_paths_by_section,
    )
    default_dataset = next(iter(datasets_by_section.values()))
    document_dataset_pairs = [
        (
            document,
            datasets_by_section.get(_document_section_id(document), default_dataset),
        )
        for document in documents
    ]
    if section_id is not None:
        document_dataset_pairs = [
            pair for pair in document_dataset_pairs if _document_section_id(pair[0]) == section_id
        ]
        if not document_dataset_pairs:
            raise ValueError(f"No rendered document matched section_id={section_id!r}.")

    renderer_kwargs: dict[str, object] = {"dpi": spec.render_dpi}
    if spec.render_continuous_strip_page_height_mm is not None:
        renderer_kwargs["continuous_strip_page_height_mm"] = (
            spec.render_continuous_strip_page_height_mm
        )
    matplotlib_style = spec.render_matplotlib.get("style")
    if matplotlib_style is not None:
        renderer_kwargs["style"] = matplotlib_style

    renderer = MatplotlibRenderer(**renderer_kwargs)
    documents_only = tuple(document for document, _dataset in document_dataset_pairs)
    datasets_only = tuple(dataset for _document, dataset in document_dataset_pairs)
    result = renderer.render_documents(documents_only, datasets_only, output_path=None)
    figures = result.artifact
    if not isinstance(figures, list):
        raise TypeError("Expected in-memory Matplotlib figures for preview generation.")
    return figures


def _render_logfile_preview_png(
    logfile_path: Path,
    *,
    page_index: int = 0,
    section_id: str | None = None,
    dpi: int = 140,
) -> bytes:
    """Render one logfile preview to PNG bytes."""
    figures = _render_logfile_figures(logfile_path, section_id=section_id)
    return _matplotlib_result_png_bytes(figures, page_index=page_index, dpi=dpi)


def _load_yaml(path: Path) -> dict[str, object]:
    """Load a YAML file into a plain mapping."""
    loaded = yaml.safe_load(path.read_text())
    if not isinstance(loaded, dict):
        raise TypeError(f"Expected YAML mapping in {path}.")
    return loaded


def _load_python_docstring(path: Path) -> str:
    """Return the module docstring for a Python example file."""
    module = ast.parse(path.read_text(), filename=str(path))
    return ast.get_docstring(module) or "Walk through the example script."


def _safe_markdown(text: str) -> str:
    """Return text safe for notebook markdown blocks."""
    return text.strip().replace("\r\n", "\n")


def _join_markdown_lines(lines: list[str]) -> str:
    """Join markdown lines without accidental indentation."""
    return "\n".join(lines)


def _yaml_source_descriptions(mapping: dict[str, object]) -> tuple[str, ...]:
    """Infer optional dependency extras from YAML source metadata."""
    document = mapping.get("document", {})
    layout = document.get("layout", {})
    sections = layout.get("log_sections", [])
    extras: set[str] = set()
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            data = section.get("data", {})
            if not isinstance(data, dict):
                continue
            source_format = str(data.get("source_format", "")).strip().lower()
            source_path = str(data.get("source_path", "")).strip().lower()
            if source_format == "dlis" or source_path.endswith(".dlis"):
                extras.add("dlis")
            if source_format == "las" or source_path.endswith(".las"):
                extras.add("las")
    return tuple(sorted(extras))


def _yaml_learning_goals(source_name: str) -> tuple[str, ...]:
    """Return high-level learning goals for one YAML example."""
    lowered = source_name.lower()
    common = [
        "Inspect how the example is structured before changing any layout settings.",
        "Validate the YAML first so schema issues fail fast.",
        "Render the example using the output path already configured in the file.",
    ]
    if "annotation_track" in lowered:
        common.append(
            "Study how annotation tracks combine intervals, text, markers, arrows, and glyphs."
        )
    elif "cbl_vdl_array" in lowered:
        common.append(
            "Compare how the array-track settings change contrast, waveform overlays, and colorbars."
        )
    elif "curve_callout" in lowered:
        common.append(
            "Study how callouts and callout bands attach labels directly to curve features."
        )
    elif "fill_modes" in lowered or "crossover" in lowered:
        common.append(
            "Compare fill styles before you copy one into a production interpretation packet."
        )
    elif "reference_track" in lowered:
        common.append(
            "Study how overlays and events can live inside the layout-defining reference track."
        )
    elif "report_pages" in lowered or "cbl_job_demo" in lowered:
        common.append(
            "Inspect how heading, remarks, and tail pages are composed around the log sections."
        )
    elif "resistivity" in lowered or "scale" in lowered:
        common.append("Compare scale conventions before you standardize one for your own packet.")
    else:
        common.append(
            "Identify the sections, tracks, and bindings you would keep or replace in your own copy."
        )
    return tuple(common)


def _yaml_adaptation_tips(source_name: str) -> tuple[str, ...]:
    """Return adaptation tips for one YAML example."""
    lowered = source_name.lower()
    tips = [
        "Change one thing at a time and re-render after each edit so the visual effect stays obvious.",
        "Keep track IDs stable while you tune bindings, fills, and header behavior.",
        "Update the configured output path if you want to preserve the original example artifact.",
    ]
    if "production" in lowered:
        tips[0] = (
            "Keep the template and reconstruction files separate so packet-level layout decisions stay reusable."
        )
    return tuple(tips)


def _yaml_summary_code(relative_path: str) -> str:
    """Return the code cell that summarizes one YAML example."""
    return dedent(
        f"""
        # Resolve the example file relative to the repository root and display the
        # source directly inside the notebook so this recipe stays self-contained.
        import yaml
        from IPython.display import Code, display

        example_path = EXAMPLES_DIR / "{relative_path}"
        display(Code(example_path.read_text(), language="yaml"))

        # Load the YAML as plain data first so we can inspect its structure without
        # performing any rendering work yet.
        example_mapping = yaml.safe_load(example_path.read_text())
        document = example_mapping.get("document", {{}})
        layout = document.get("layout", {{}})
        sections = layout.get("log_sections", [])

        print("Name:", example_mapping.get("name"))
        print("Template:", example_mapping.get("template", {{}}).get("path"))
        print("Configured output:", example_mapping.get("render", {{}}).get("output_path"))
        print("Section count:", len(sections))

        for section in sections:
            data = section.get("data", {{}})
            tracks = section.get("tracks", [])
            print("\\nSection:", section.get("id"))
            print("  Title:", section.get("title"))
            print("  Source:", data.get("source_path"), f"({{data.get('source_format')}})")
            print("  Tracks:", [track.get("id") for track in tracks])
        """
    ).strip()


def _yaml_validate_render_code(relative_path: str) -> str:
    """Return the validate-and-render code cell for one YAML example."""
    return dedent(
        f"""
        # Use load_logfile(...) as the validation step. If the example is invalid,
        # this cell will raise the exact schema or template error to fix next.
        from wellplot import load_logfile, render_from_logfile

        example_path = EXAMPLES_DIR / "{relative_path}"
        spec = load_logfile(example_path)
        print("Validated:", spec.name)

        # Render to the output path already configured inside the example file.
        # Keeping the configured output path intact makes it easier to compare the
        # notebook run with the repository documentation and screenshots.
        result = render_from_logfile(example_path)
        print("Pages:", result.page_count)
        print("Rendered:", result.output_path)
        """
    ).strip()


def _production_setup_code(package_name: str) -> str:
    """Return the setup cell for one production package notebook."""
    return dedent(
        f"""
        # Resolve the production package files and display the supporting README
        # and notes before touching the renderable YAML.
        from IPython.display import Code, Markdown, display

        package_dir = EXAMPLES_DIR / "production" / "{package_name}"
        readme_path = package_dir / "README.md"
        notes_path = package_dir / "data-notes.md"
        template_path = package_dir / "base.template.yaml"
        logfile_path = package_dir / "full_reconstruction.log.yaml"

        display(Markdown(readme_path.read_text()))
        display(Markdown(notes_path.read_text()))
        display(Code(template_path.read_text(), language="yaml"))
        display(Code(logfile_path.read_text(), language="yaml"))
        """
    ).strip()


def _production_summary_code(package_name: str) -> str:
    """Return the summary cell for one production package."""
    return dedent(
        f"""
        # Summarize the production packet structure so you can see what will be
        # rendered before the render step runs.
        import yaml

        package_dir = EXAMPLES_DIR / "production" / "{package_name}"
        logfile_path = package_dir / "full_reconstruction.log.yaml"
        mapping = yaml.safe_load(logfile_path.read_text())
        layout = mapping.get("document", {{}}).get("layout", {{}})
        sections = layout.get("log_sections", [])
        remarks = layout.get("remarks", [])

        print("Packet:", mapping.get("name"))
        print("Configured output:", mapping.get("render", {{}}).get("output_path"))
        print("Remarks blocks:", [remark.get("title") for remark in remarks])
        print("Sections:", [section.get("id") for section in sections])

        for section in sections:
            tracks = [track.get("id") for track in section.get("tracks", [])]
            print("\\nSection:", section.get("id"))
            print("  Title:", section.get("title"))
            print("  Depth range:", section.get("depth_range"))
            print("  Tracks:", tracks)
        """
    ).strip()


def _production_render_code(package_name: str) -> str:
    """Return the validate-and-render cell for one production package."""
    return dedent(
        f"""
        # Validate and render the production example using the same high-level
        # file-based pipeline a final user would call from the CLI.
        from wellplot import load_logfile, render_from_logfile

        package_dir = EXAMPLES_DIR / "production" / "{package_name}"
        logfile_path = package_dir / "full_reconstruction.log.yaml"
        spec = load_logfile(logfile_path)
        print("Validated:", spec.name)

        result = render_from_logfile(logfile_path)
        print("Pages:", result.page_count)
        print("Rendered:", result.output_path)
        """
    ).strip()


def _production_intro_markdown(
    package_name: str, title: str, prerequisites: tuple[str, ...]
) -> str:
    """Return the intro markdown for one production package notebook."""
    prereq_block = _prerequisites_markdown(prerequisites)
    return _join_markdown_lines(
        [
            f"# {title}",
            "",
            "This generated notebook is the recipe companion for the production package",
            f"`examples/production/{package_name}/`.",
            "",
            "The walkthrough keeps the same progression a final user would follow:",
            "",
            "- review the package README and data notes",
            "- inspect the shared template and the reconstruction logfile",
            "- validate the configuration",
            "- render the packet through the normal pipeline",
            "",
            prereq_block,
            "",
            "Runtime model:",
            "",
            "- import `wellplot` from the active installed environment",
            "- use the repository checkout for the example files, helper modules, and sample data",
        ]
    )


def _python_intro_markdown(recipe: PythonRecipe) -> str:
    """Return the intro markdown for one Python example notebook."""
    goals = "\n".join(f"- {goal}" for goal in recipe.learning_goals)
    prereq_block = _prerequisites_markdown(
        recipe.prerequisites,
        install_command=recipe.install_command,
    )
    intro_lines = (
        [
            f"# {recipe.title}",
            "",
            "This generated notebook is the recipe companion for",
            f"`examples/{recipe.source}`.",
        ]
        if not recipe.self_contained
        else [
            f"# {recipe.title}",
            "",
            "This generated notebook is a self-contained walkthrough.",
        ]
    )
    runtime_lines = (
        [
            "- import `wellplot` from the active installed environment",
            "- use the repository checkout for the example files and sample data",
        ]
        if recipe.self_contained
        else [
            "- import `wellplot` from the active installed environment",
            "- use the repository checkout for the example files, helper modules, and sample data",
        ]
    )
    return _join_markdown_lines(
        intro_lines
        + [
            "",
            recipe.summary,
            "",
            "What you will practice in this walkthrough:",
            "",
            goals,
            "",
            prereq_block,
            "",
            "Runtime model:",
            "",
        ]
        + runtime_lines
    )


def _yaml_intro_markdown(path: Path, mapping: dict[str, object]) -> str:
    """Return the intro markdown for one YAML example notebook."""
    example_name = str(mapping.get("name", path.name)).strip()
    goals = "\n".join(f"- {goal}" for goal in _yaml_learning_goals(path.name))
    prereq_block = _prerequisites_markdown(_yaml_source_descriptions(mapping))
    return _join_markdown_lines(
        [
            f"# {example_name}",
            "",
            "This generated notebook is the recipe companion for",
            f"`examples/{path.name}`.",
            "",
            "Use it to read the example source in one place, validate it, and render",
            "it with the same file-based workflow that final users will run from the",
            "command line.",
            "",
            "What you will practice in this walkthrough:",
            "",
            goals,
            "",
            prereq_block,
            "",
            "Runtime model:",
            "",
            "- import `wellplot` from the active installed environment",
            "- use the repository checkout for the example files, helper modules, and sample data",
        ]
    )


def _install_command(extras: tuple[str, ...]) -> str:
    """Return the published-package install command for one notebook."""
    normalized = tuple(sorted({extra.strip() for extra in extras if extra.strip()} | {"notebook"}))
    joined = ",".join(normalized)
    return f'pip install "wellplot[{joined}]"'


def _prerequisites_markdown(
    steps: tuple[str, ...],
    *,
    install_command: str | None = None,
) -> str:
    """Return a prerequisite markdown block."""
    command = _install_command(steps) if install_command is None else install_command
    return _join_markdown_lines(
        [
            "Prerequisites:",
            "",
            f"- `{command}`",
            "- run the notebook from a checkout of this repository so the `examples/` files and sample data are available",
        ]
    )


def _source_display_code(relative_path: str, language: str) -> str:
    """Return a cell that displays the source example in the notebook."""
    return dedent(
        f"""
        # Display the source directly in the notebook so the recipe is easy to
        # read and copy from without opening another file.
        from IPython.display import Code, display

        source_path = EXAMPLES_DIR / "{relative_path}"
        display(Code(source_path.read_text(), language="{language}"))
        """
    ).strip()


def _adaptation_markdown(title: str, tips: tuple[str, ...]) -> str:
    """Return a final adaptation-notes markdown section."""
    bullets = "\n".join(f"- {tip}" for tip in tips)
    return _join_markdown_lines([f"## Adapt {title} Safely", "", bullets])


def _user_intro_markdown(recipe: UserProductionRecipe, prerequisites: tuple[str, ...]) -> str:
    """Return the opening markdown for one curated user notebook."""
    return _join_markdown_lines(
        [
            f"# {recipe.title}",
            "",
            recipe.subtitle,
            "",
            "## Who This Is For",
            "",
            recipe.target_user,
            "",
            "## Why Start Here",
            "",
            recipe.why_this_example,
            "",
            _prerequisites_markdown(prerequisites),
            "",
            "## What This Notebook Will Do",
            "",
            "- confirm the example package is available in your repository checkout",
            "- render the shipped PDF packet exactly as provided",
            "- show you representative preview images so you know what success looks like",
            "- point you to the first settings worth editing for your own well",
        ]
    )


def _user_summary_markdown(recipe: UserProductionRecipe, output_rel: str) -> str:
    """Return the user-facing summary markdown for one production notebook."""
    data_highlights = "\n".join(f"- {entry}" for entry in recipe.data_highlights)
    what_to_look_for = "\n".join(f"- {entry}" for entry in recipe.what_to_look_for)
    return _join_markdown_lines(
        [
            "## Example At A Glance",
            "",
            data_highlights,
            "",
            f"Expected PDF output: `{output_rel}`",
            "",
            "## What To Look For In The Result",
            "",
            what_to_look_for,
        ]
    )


def _user_first_edits_markdown(recipe: UserProductionRecipe) -> str:
    """Return the first-edits guidance for one user notebook."""
    first_edits = "\n".join(f"- {entry}" for entry in recipe.first_edits)
    return _join_markdown_lines(["## First Edits To Make For Your Own Well", "", first_edits])


def _user_keep_in_mind_markdown(recipe: UserProductionRecipe) -> str:
    """Return cautionary notes and next-step guidance for one user notebook."""
    notes = "\n".join(f"- {entry}" for entry in recipe.keep_in_mind)
    developer_notebook = f"examples/notebooks/developer/{recipe.package_name}.ipynb"
    return _join_markdown_lines(
        [
            "## Keep In Mind",
            "",
            notes,
            "",
            "If you decide you need the raw YAML, bindings, or template internals next,",
            f"open the developer notebook: `{developer_notebook}`.",
        ]
    )


def _user_preview_code(recipe: UserProductionRecipe) -> str:
    """Return the preview-display cell for one user notebook."""
    preview_lines = [
        "from IPython.display import Image, Markdown, display",
        "",
        'preview_dir = REPO_ROOT / "examples" / "notebooks" / "user" / "assets"',
        "",
    ]
    for preview in recipe.previews:
        variable = preview.asset_name.removesuffix(".png").replace("-", "_")
        preview_lines.append(f'{variable} = preview_dir / "{preview.asset_name}"')
        preview_lines.append(f'display(Markdown("### {preview.title}"))')
        preview_lines.append(f'display(Markdown("{preview.summary}"))')
        preview_lines.append(f"display(Image(filename=str({variable})))")
        preview_lines.append("")
    return "\n".join(preview_lines).strip()


def _user_preview_outputs(
    recipe: UserProductionRecipe,
    pdf_path: Path,
    *,
    check: bool,
) -> tuple[list[dict[str, object]], int]:
    """Generate or validate preview assets and return notebook outputs."""
    outputs: list[dict[str, object]] = []
    changes = 0
    for preview in recipe.previews:
        png_bytes = _pdf_preview_png_bytes(pdf_path, page_number=preview.page_number)
        asset_path = USER_ASSETS_DIR / preview.asset_name
        if check:
            current = asset_path.read_bytes() if asset_path.exists() else None
            if current != png_bytes:
                raise SystemExit(f"Notebook asset is out of date: {asset_path}")
        elif _write_bytes_if_changed(asset_path, png_bytes):
            changes += 1
        outputs.append(markdown_output(f"### {preview.title}"))
        outputs.append(markdown_output(preview.summary))
        outputs.append(png_output(png_bytes))
    return outputs, changes


def _heading_fields_by_keys(
    heading_mapping: dict[str, object],
    *,
    keys: tuple[str, ...],
) -> list[dict[str, object]]:
    """Return a filtered copy of heading general fields."""
    fields = heading_mapping.get("general_fields", [])
    if not isinstance(fields, list):
        return []
    selected: list[dict[str, object]] = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        if str(field.get("key")) in keys:
            selected.append(deepcopy(field))
    return selected


def _detail_rows_by_labels(
    heading_mapping: dict[str, object],
    *,
    labels: tuple[str, ...],
) -> list[dict[str, object]]:
    """Return a filtered copy of heading detail rows."""
    detail = heading_mapping.get("detail", {})
    if not isinstance(detail, dict):
        return []
    rows = detail.get("rows", [])
    if not isinstance(rows, list):
        return []
    selected: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = row.get("label")
        label_cells = row.get("label_cells")
        if label in labels:
            selected.append(deepcopy(row))
            continue
        if (
            isinstance(label_cells, list)
            and " / ".join(str(cell) for cell in label_cells) in labels
        ):
            selected.append(deepcopy(row))
    return selected


def _logfile_section_by_id(mapping: dict[str, object], section_id: str) -> dict[str, object]:
    """Return one deep-copied section mapping by id."""
    sections = mapping.get("document", {}).get("layout", {}).get("log_sections", [])
    if not isinstance(sections, list):
        raise KeyError(section_id)
    for section in sections:
        if isinstance(section, dict) and str(section.get("id")) == section_id:
            return deepcopy(section)
    raise KeyError(section_id)


def _section_with_tracks(
    section: dict[str, object], track_ids: tuple[str, ...]
) -> dict[str, object]:
    """Return a deep-copied section limited to the selected track ids."""
    tracks = section.get("tracks", [])
    if not isinstance(tracks, list):
        return section
    section_copy = deepcopy(section)
    section_copy["tracks"] = [
        deepcopy(track)
        for track in tracks
        if isinstance(track, dict) and str(track.get("id")) in track_ids
    ]
    return section_copy


def _bindings_subset(
    mapping: dict[str, object],
    *,
    section_id: str | None = None,
    track_ids: tuple[str, ...] | None = None,
    channels: tuple[str, ...] | None = None,
    element_ids: tuple[str, ...] | None = None,
) -> list[dict[str, object]]:
    """Return deep-copied binding mappings filtered by section, track, or channel."""
    bindings = mapping.get("document", {}).get("bindings", {}).get("channels", [])
    if not isinstance(bindings, list):
        return []
    selected: list[dict[str, object]] = []
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        if section_id is not None and str(binding.get("section")) != section_id:
            continue
        if track_ids is not None and str(binding.get("track_id")) not in track_ids:
            continue
        if channels is not None and str(binding.get("channel")) not in channels:
            continue
        if element_ids is not None and str(binding.get("id")) not in element_ids:
            continue
        selected.append(deepcopy(binding))
    return selected


def _tutorial_render_style_subset(template_mapping: dict[str, object]) -> dict[str, object]:
    """Return a compact but still production-like Matplotlib style mapping."""
    render = template_mapping.get("render", {})
    matplotlib_mapping = render.get("matplotlib", {}) if isinstance(render, dict) else {}
    style = matplotlib_mapping.get("style", {}) if isinstance(matplotlib_mapping, dict) else {}
    if not isinstance(style, dict):
        return {}
    return {
        key: deepcopy(value)
        for key, value in style.items()
        if key in {"report", "section_title", "track_header", "track", "grid"}
    }


def _porosity_tutorial_template_text() -> str:
    """Return a simplified reusable template for the porosity user notebook."""
    template_path = _production_package_dir("forge16b_porosity_example") / "base.template.yaml"
    template_mapping = _load_yaml(template_path)
    heading = template_mapping.get("document", {}).get("layout", {}).get("heading", {})
    if not isinstance(heading, dict):
        raise TypeError("Expected heading mapping in porosity template.")

    template_mapping["render"] = {
        "backend": "matplotlib",
        "output_path": "./renders/tutorial_template_placeholder.pdf",
        "dpi": 180,
        "matplotlib": {
            "style": _tutorial_render_style_subset(template_mapping),
        },
    }
    heading["general_fields"] = _heading_fields_by_keys(
        heading,
        keys=(
            "company",
            "well",
            "field",
            "location",
            "uwi",
            "logging_date",
            "scale",
        ),
    )
    detail = heading.get("detail", {})
    if isinstance(detail, dict):
        detail["rows"] = _detail_rows_by_labels(
            heading,
            labels=(
                "Project",
                "Service Company",
                "Permanent Datum",
                "Logging Measured From",
            ),
        )
    template_mapping["document"]["layout"]["remarks"] = [
        {
            "title": "Public Data and IP Notice",
            "lines": [
                "This tutorial uses publicly available or repository-provided demonstration data intended for educational use.",
                "Rendered layouts are independent reproductions generated by wellplot, not vendor-authored originals or official service-company deliverables.",
            ],
            "alignment": "left",
        }
    ]
    return _yaml_text(template_mapping)


def _porosity_user_tutorial() -> UserNotebookTutorial:
    """Return the stage plan for the porosity user notebook."""
    logfile_mapping = _load_yaml(
        _production_package_dir("forge16b_porosity_example") / "full_reconstruction.log.yaml"
    )
    for section in logfile_mapping["document"]["layout"]["log_sections"]:
        section["data"]["source_path"] = "../../data/30-23a-3 8117_d.las"

    upper_review = _logfile_section_by_id(logfile_mapping, "upper_review")

    step_1_mapping = {
        "template": {"path": "./base.template.yaml"},
        "version": 1,
        "name": "Porosity tutorial step 1 - first packet",
        "render": {"output_path": "./renders/step_1_first_packet.pdf"},
        "document": {
            "layout": {
                "remarks": [
                    {
                        "title": "What this first packet proves",
                        "lines": [
                            "The template can resolve heading fields from the LAS header.",
                            "A single section is enough to prove page geometry, depth scale, and one first curve.",
                        ],
                        "alignment": "left",
                    }
                ],
                "log_sections": [
                    _section_with_tracks(upper_review, ("gr_sp", "depth")),
                ],
            },
            "bindings": {
                "channels": _bindings_subset(
                    logfile_mapping,
                    section_id="upper_review",
                    track_ids=("gr_sp",),
                    channels=("GR",),
                )
            },
        },
    }
    step_2_mapping = {
        "template": {"path": "./base.template.yaml"},
        "version": 1,
        "name": "Porosity tutorial step 2 - add the resistivity track",
        "render": {"output_path": "./renders/step_2_add_resistivity.pdf"},
        "document": {
            "layout": {
                "remarks": [
                    {
                        "title": "Why the second step matters",
                        "lines": [
                            "Keep the same section and add more tracks only after the first packet renders cleanly.",
                            "The resistivity track shows how one source file can feed multiple curve overlays with different styles and scales.",
                        ],
                        "alignment": "left",
                    }
                ],
                "log_sections": [
                    _section_with_tracks(upper_review, ("gr_sp", "depth", "resistivity")),
                ],
            },
            "bindings": {
                "channels": _bindings_subset(
                    logfile_mapping,
                    section_id="upper_review",
                    track_ids=("gr_sp", "resistivity"),
                    channels=("GR", "SP", "ILD", "ILM", "MSFL"),
                )
            },
        },
    }
    step_3_mapping = {
        "template": {"path": "./base.template.yaml"},
        "version": 1,
        "name": "Porosity tutorial step 3 - add the porosity interpretation track",
        "render": {"output_path": "./renders/step_3_add_porosity_fill.pdf"},
        "document": {
            "layout": {
                "remarks": [
                    {
                        "title": "Why the porosity track is built last",
                        "lines": [
                            "The density-neutron track depends on two related curves plus optional QC curves.",
                            "The gas crossover fill works only after both the neutron and density bindings exist and their ids match.",
                        ],
                        "alignment": "left",
                    }
                ],
                "log_sections": [upper_review],
            },
            "bindings": {
                "channels": _bindings_subset(
                    logfile_mapping,
                    section_id="upper_review",
                )
            },
        },
    }
    step_4_mapping = deepcopy(logfile_mapping)
    step_4_mapping["template"] = {"path": "./base.template.yaml"}
    step_4_mapping["name"] = "Porosity tutorial step 4 - final two-window packet"
    step_4_mapping["render"] = {"output_path": "./renders/step_4_final_two_window_packet.pdf"}

    return UserNotebookTutorial(
        package_name="forge16b_porosity_example",
        template_text=_porosity_tutorial_template_text(),
        template_explanation=(
            "Put page size, depth scale, heading fields, default style, and tail behavior in the template because you will usually reuse those decisions across many wells.",
            "Keep the logfile for the parts that change per well or per packet: data source paths, depth windows, remarks, tracks, curve bindings, and fills.",
            "Start with a small reusable template. Add only the heading fields and style defaults you need before you copy the packet to another well.",
        ),
        inspection_section_id="upper_review",
        inspection_channels=("GR", "SP", "ILD", "ILM", "MSFL", "NPHI", "RHOB", "PEF", "DRHO"),
        inspection_metadata_keys=("COMP", "WELL", "FLD", "LOC", "UWI", "DATE"),
        stages=(
            UserNotebookStage(
                slug="step_1_first_packet",
                title="Step 1. Build the smallest useful packet",
                summary="Start with one depth window, one overview track, and one first curve so you can prove the template, heading, remarks, and depth axis all work together.",
                teaching_points=(
                    "The template supplies the heading and page defaults.",
                    "The logfile adds one section, one data source, and one first binding.",
                    "The depth track defines the vertical layout axis even though no curve is bound to it.",
                ),
                logfile_text=_yaml_text(step_1_mapping),
                previews=(
                    UserNotebookPreview(
                        asset_name="forge16b_step_1_opening_page.png",
                        title="Opening page after step 1",
                        summary="The heading resolves from LAS metadata and the remarks explain the packet scope.",
                        page_index=0,
                    ),
                    UserNotebookPreview(
                        asset_name="forge16b_step_1_first_strip.png",
                        title="First strip after step 1",
                        summary="A single GR curve is enough to confirm the depth axis, grid, and track header are behaving correctly.",
                        section_id="upper_review",
                        page_index=1,
                    ),
                ),
            ),
            UserNotebookStage(
                slug="step_2_add_resistivity",
                title="Step 2. Add the resistivity review track",
                summary="Once the first strip is stable, add the resistivity track and bind the deep, medium, and flushed-zone curves with log scaling.",
                teaching_points=(
                    "One section can host multiple tracks that share the same source file and depth range.",
                    "Each curve binding chooses its own style and scale even when several curves share the same track.",
                    "This is the right point to tune curve labels, line styles, and track widths before you add interpretation fills.",
                ),
                logfile_text=_yaml_text(step_2_mapping),
                previews=(
                    UserNotebookPreview(
                        asset_name="forge16b_step_2_resistivity_review.png",
                        title="Upper review after step 2",
                        summary="The packet now shows GR/SP plus deep, medium, and flushed-zone resistivity overlays.",
                        section_id="upper_review",
                        page_index=1,
                    ),
                ),
            ),
            UserNotebookStage(
                slug="step_3_add_porosity_fill",
                title="Step 3. Add the porosity track and gas crossover fill",
                summary="Bind neutron, density, and QC curves, then add the crossover fill so the packet starts carrying porosity interpretation value instead of only presentation structure.",
                teaching_points=(
                    "Use ids on related curve bindings when a fill needs to refer to another element.",
                    "The crossover block is what creates the two-sided gas fill in the strip and the matching header indicator.",
                    "Add QC curves such as PEF and DRHO only after the main interpretation pair is already behaving correctly.",
                ),
                logfile_text=_yaml_text(step_3_mapping),
                previews=(
                    UserNotebookPreview(
                        asset_name="forge16b_step_3_porosity_fill.png",
                        title="Upper review after step 3",
                        summary="The porosity track now combines NPHI, RHOB, PEF, DRHO, and the gas crossover fill.",
                        section_id="upper_review",
                        page_index=1,
                    ),
                ),
            ),
            UserNotebookStage(
                slug="step_4_final_two_window_packet",
                title="Step 4. Finish the packet with a second depth window",
                summary="Reuse the same template and same LAS source, but add a second section so the packet covers both the upper and lower review intervals.",
                teaching_points=(
                    "Reusing the template keeps report styling and headings consistent while the logfile adds a second interpretation window.",
                    "The public-data and IP remarks belong in the final production packet, not only in the README.",
                    "Only duplicate a section after the first one is correct; otherwise you duplicate mistakes and double the cleanup.",
                ),
                logfile_text=_yaml_text(step_4_mapping),
                previews=(
                    UserNotebookPreview(
                        asset_name="forge16b_step_4_opening_page.png",
                        title="Opening page of the final tutorial packet",
                        summary="The final packet keeps the reusable template and adds production remarks suitable for a public example.",
                        page_index=0,
                    ),
                    UserNotebookPreview(
                        asset_name="forge16b_step_4_lower_review.png",
                        title="Lower review section",
                        summary="The same LAS source is reused over a second depth window so the packet can extend deeper without changing the template.",
                        section_id="lower_review",
                        page_index=1,
                    ),
                ),
            ),
        ),
        adaptation_tips=(
            "Copy the template first if your page style and heading layout will be reused across wells.",
            "Point the logfile at your own LAS file and list only the curves that actually exist in that source.",
            "Tune one section until it looks right before you add extra windows, extra tracks, or extra fills.",
            "Keep the public-data and IP notice explicit whenever the source data is public or redistributed for demonstration purposes.",
        ),
    )


def _cbl_tutorial_template_text() -> str:
    """Return a simplified reusable template for the CBL user notebook."""
    template_path = _production_package_dir("cbl_log_example") / "base.template.yaml"
    template_mapping = _load_yaml(template_path)
    heading = template_mapping.get("document", {}).get("layout", {}).get("heading", {})
    if not isinstance(heading, dict):
        raise TypeError("Expected heading mapping in CBL template.")

    template_mapping["render"] = {
        "backend": "matplotlib",
        "output_path": "./renders/tutorial_template_placeholder.pdf",
        "dpi": 180,
        "continuous_strip_page_height_mm": 297,
        "matplotlib": {
            "style": _tutorial_render_style_subset(template_mapping),
        },
    }
    heading["general_fields"] = _heading_fields_by_keys(
        heading,
        keys=(
            "company",
            "well",
            "field",
            "location",
            "logging_date",
            "scale",
            "fluid_type",
        ),
    )
    detail = heading.get("detail", {})
    if isinstance(detail, dict):
        detail["rows"] = detail.get("rows", [])[:6]
    template_mapping["document"]["layout"]["remarks"] = [
        {
            "title": "Public Data and IP Notice",
            "lines": [
                "This tutorial uses publicly available or repository-provided demonstration data intended for educational use.",
                "Rendered layouts are independent reproductions generated by wellplot, not vendor-authored originals or official service-company deliverables.",
            ],
            "alignment": "left",
        }
    ]
    return _yaml_text(template_mapping)


def _cbl_user_tutorial() -> UserNotebookTutorial:
    """Return the stage plan for the CBL user notebook."""
    logfile_mapping = _load_yaml(
        _production_package_dir("cbl_log_example") / "full_reconstruction.log.yaml"
    )
    source_paths = {
        "main_pass": "../../data/CBL_Main.dlis",
        "repeat_pass": "../../data/CBL_Repeat.dlis",
    }
    for section in logfile_mapping["document"]["layout"]["log_sections"]:
        section["data"]["source_path"] = source_paths[str(section["id"])]
        if str(section["id"]) == "main_pass":
            section["depth_range"] = [8230, 8490]

    main_pass = _logfile_section_by_id(logfile_mapping, "main_pass")

    step_1_mapping = {
        "template": {"path": "./base.template.yaml"},
        "version": 1,
        "name": "CBL tutorial step 1 - first packet",
        "render": {"output_path": "./renders/step_1_first_packet.pdf"},
        "document": {
            "layout": {
                "remarks": [
                    {
                        "title": "What this first packet proves",
                        "lines": [
                            "The heading, remarks, and first main-pass section are all connected to the DLIS-backed packet.",
                            "You do not need every CBL feature on the first pass; prove the packet structure first.",
                        ],
                        "alignment": "left",
                    }
                ],
                "log_sections": [
                    _section_with_tracks(main_pass, ("combo", "depth")),
                ],
            },
            "bindings": {
                "channels": _bindings_subset(
                    logfile_mapping,
                    section_id="main_pass",
                    track_ids=("combo",),
                    channels=("ECGR_STGC", "TT"),
                )
            },
        },
    }
    step_2_mapping = {
        "template": {"path": "./base.template.yaml"},
        "version": 1,
        "name": "CBL tutorial step 2 - add the CBL amplitude track",
        "render": {"output_path": "./renders/step_2_add_cbl_track.pdf"},
        "document": {
            "layout": {
                "remarks": [
                    {
                        "title": "Why the dedicated CBL track matters",
                        "lines": [
                            "The same CBL channel can be bound twice so the packet shows both the broad 0 to 100 scale and the tighter 0 to 10 scale.",
                            "This is a good example of how one channel can support more than one interpretation view.",
                        ],
                        "alignment": "left",
                    }
                ],
                "log_sections": [
                    _section_with_tracks(main_pass, ("combo", "depth", "cbl")),
                ],
            },
            "bindings": {
                "channels": _bindings_subset(
                    logfile_mapping,
                    section_id="main_pass",
                    track_ids=("combo", "cbl"),
                    channels=("ECGR_STGC", "TT", "TENS", "MTEM", "CBL"),
                )
            },
        },
    }
    step_3_mapping = {
        "template": {"path": "./base.template.yaml"},
        "version": 1,
        "name": "CBL tutorial step 3 - add VDL and depth overlays",
        "render": {"output_path": "./renders/step_3_add_vdl_and_overlays.pdf"},
        "document": {
            "layout": {
                "remarks": [
                    {
                        "title": "Why this is the key CBL interpretation step",
                        "lines": [
                            "The VDL array track turns the packet from a simple curve sheet into a CBL/VDL interpretation view.",
                            "Reference overlays on the depth track keep local indicators visible without creating extra tracks.",
                        ],
                        "alignment": "left",
                    }
                ],
                "log_sections": [main_pass],
            },
            "bindings": {
                "channels": _bindings_subset(
                    logfile_mapping,
                    section_id="main_pass",
                )
            },
        },
    }
    step_4_mapping = deepcopy(logfile_mapping)
    step_4_mapping["template"] = {"path": "./base.template.yaml"}
    step_4_mapping["name"] = "CBL tutorial step 4 - final packet with repeat pass"
    step_4_mapping["render"] = {"output_path": "./renders/step_4_final_packet.pdf"}

    return UserNotebookTutorial(
        package_name="cbl_log_example",
        template_text=_cbl_tutorial_template_text(),
        template_explanation=(
            "The CBL template owns the reusable packet identity: page geometry, heading content, track-header styling, and tail behavior.",
            "The logfile owns job-specific content: DLIS source paths, which pass to plot, which tracks to show, and which channels to bind.",
            "That split matters because most real CBL work reuses one packet style across many jobs while only the logfile changes.",
        ),
        inspection_section_id="main_pass",
        inspection_channels=(
            "ECGR_STGC",
            "TT",
            "TENS",
            "MTEM",
            "CBL",
            "VDL",
            "STIT",
            "TDSP",
            "VSEC",
        ),
        inspection_metadata_keys=("COMP", "WELL", "FIELD", "WELL_ID"),
        stages=(
            UserNotebookStage(
                slug="step_1_first_packet",
                title="Step 1. Build the first main-pass packet",
                summary="Start with the heading, remarks, one main-pass section, and a small combo track so you can prove that the packet skeleton is correct before you add the heavier CBL/VDL features.",
                teaching_points=(
                    "A production packet can begin with only one pass and only a few curves.",
                    "The depth track still defines layout even before you add special overlay indicators.",
                    "This is the right stage to verify that the DLIS source path, page scale, and headings are all correct.",
                ),
                logfile_text=_yaml_text(step_1_mapping),
                previews=(
                    UserNotebookPreview(
                        asset_name="cbl_step_1_opening_page.png",
                        title="Opening page after step 1",
                        summary="The packet already has headings and remarks even though the log content is still minimal.",
                        page_index=0,
                    ),
                    UserNotebookPreview(
                        asset_name="cbl_step_1_main_pass.png",
                        title="Main-pass skeleton after step 1",
                        summary="The first strip proves the packet layout with only the combo and depth tracks.",
                        section_id="main_pass",
                        page_index=1,
                    ),
                ),
            ),
            UserNotebookStage(
                slug="step_2_add_cbl_track",
                title="Step 2. Add the dedicated CBL amplitude track",
                summary="Bind the same CBL channel twice so the packet shows both the broad and tight amplitude scales that make cement interpretation easier.",
                teaching_points=(
                    "One channel can be plotted more than once when each binding serves a different reading task.",
                    "The packet gets easier to read when the CBL amplitude leaves the crowded combo track and gets its own track.",
                    "This is also the stage where supporting combo curves such as tension and mud temperature become more useful.",
                ),
                logfile_text=_yaml_text(step_2_mapping),
                previews=(
                    UserNotebookPreview(
                        asset_name="cbl_step_2_dual_scale_cbl.png",
                        title="Main pass after step 2",
                        summary="The CBL amplitude track now carries both the wide and tight scales using two bindings to the same channel.",
                        section_id="main_pass",
                        page_index=1,
                    ),
                ),
            ),
            UserNotebookStage(
                slug="step_3_add_vdl_and_overlays",
                title="Step 3. Add the VDL array and depth overlays",
                summary="Finish the main pass by adding the VDL raster and the local indicator overlays on the depth track.",
                teaching_points=(
                    "Array tracks are configured differently from normal tracks because they plot raster data instead of scalar curves.",
                    "The sample-axis block tells wellplot how to label the VDL waveform axis in the header.",
                    "Reference overlays let you add local indicators without giving up the depth track as the packet layout axis.",
                ),
                logfile_text=_yaml_text(step_3_mapping),
                previews=(
                    UserNotebookPreview(
                        asset_name="cbl_step_3_vdl_and_overlays.png",
                        title="Main pass after step 3",
                        summary="The packet now has the VDL raster plus the stuck-tool and drag indicators on the depth track.",
                        section_id="main_pass",
                        page_index=1,
                    ),
                ),
            ),
            UserNotebookStage(
                slug="step_4_final_packet",
                title="Step 4. Add the repeat pass and finish the packet",
                summary="Reuse the same template and packet rules, then add the repeat pass so the final example covers the supported reconstruction scope.",
                teaching_points=(
                    "Repeat sections should reuse the same layout vocabulary unless the second pass truly needs a different design.",
                    "The production remarks and public-data notice belong inside the final packet so the PDF can stand on its own.",
                    "Once both passes are working, further edits should usually be curve styles, interval windows, or heading content rather than structural redesign.",
                ),
                logfile_text=_yaml_text(step_4_mapping),
                previews=(
                    UserNotebookPreview(
                        asset_name="cbl_step_4_opening_page.png",
                        title="Opening page of the final tutorial packet",
                        summary="The final packet has the production remarks and keeps the public-data / IP boundary explicit.",
                        page_index=0,
                    ),
                    UserNotebookPreview(
                        asset_name="cbl_step_4_repeat_pass.png",
                        title="Repeat-pass section",
                        summary="The repeat pass reuses the same packet structure so the second DLIS file drops into a familiar interpretation view.",
                        section_id="repeat_pass",
                        page_index=1,
                    ),
                ),
            ),
        ),
        adaptation_tips=(
            "Keep the template stable across jobs and change the logfile first when the source files or intervals change.",
            "Prove the main pass before you add the repeat pass or heavier raster content.",
            "Bind the same channel twice only when the second scale really adds interpretation value.",
            "Keep the IP boundary explicit whenever you compare your rendered packet against a reference vendor PDF.",
        ),
    )


def _user_tutorial_for_recipe(recipe: UserProductionRecipe) -> UserNotebookTutorial:
    """Return the tutorial configuration for one user-facing production package."""
    if recipe.package_name == "forge16b_porosity_example":
        return _porosity_user_tutorial()
    if recipe.package_name == "cbl_log_example":
        return _cbl_user_tutorial()
    raise KeyError(f"Unsupported user tutorial package {recipe.package_name!r}.")


def _tutorial_output_rel(package_name: str, output_name: str) -> str:
    """Return the expected render path for one tutorial stage."""
    return f"workspace/tutorials/{package_name}/renders/{output_name}"


def _user_tutorial_intro_markdown(
    recipe: UserProductionRecipe,
    tutorial: UserNotebookTutorial,
    *,
    prerequisites: tuple[str, ...],
) -> str:
    """Return the opening markdown for one rewritten user tutorial notebook."""
    return _join_markdown_lines(
        [
            f"# {recipe.title}",
            "",
            recipe.subtitle,
            "",
            "## Who This Notebook Is For",
            "",
            recipe.target_user,
            "",
            "## What You Will Learn",
            "",
            "- how to inspect the source data and confirm which channels and header fields are available",
            "- how to separate reusable template work from well-specific logfile work",
            "- how to validate YAML and template wiring with `load_logfile(...)`",
            "- how to render a packet with `render_from_logfile(...)` after each major edit",
            "- how to add headings, remarks, tracks, curve bindings, fills, and extra sections in a controlled order",
            "",
            _prerequisites_markdown(prerequisites),
            "",
            "## The Three `wellplot` Functions That Matter In This Workflow",
            "",
            "- `load_datasets_for_logfile(...)` to inspect the source file and list the channels you can actually plot",
            "- `load_logfile(...)` to validate the YAML and the template resolution before you render",
            "- `render_from_logfile(...)` to produce the packet PDF once the YAML is ready",
            "",
            "## How To Read This Notebook",
            "",
            "- each stage writes a real YAML file under `workspace/tutorials/`",
            "- each render cell validates and renders that stage exactly like a real user workflow",
            "- the inline images are visual checkpoints so you can compare your result with the expected packet state",
        ]
    )


def _user_tutorial_setup_code(package_name: str) -> str:
    """Return the setup cell for a user tutorial notebook."""
    return dedent(
        f"""
        from pathlib import Path

        try:
            import wellplot
        except ImportError as exc:
            raise RuntimeError(
                "Install the published 'wellplot' package in the active environment "
                "before running this notebook."
            ) from exc

        cwd = Path.cwd().resolve()
        REPO_ROOT = next((path for path in (cwd, *cwd.parents) if (path / "examples").exists()), None)
        if REPO_ROOT is None:
            raise RuntimeError(
                "Run this notebook from a checkout of the wellplot repository so the "
                "example files and sample data are available."
            )

        package_dir = REPO_ROOT / "examples" / "production" / "{package_name}"
        example_logfile = package_dir / "full_reconstruction.log.yaml"
        tutorial_dir = REPO_ROOT / "workspace" / "tutorials" / "{package_name}"
        render_dir = tutorial_dir / "renders"
        tutorial_dir.mkdir(parents=True, exist_ok=True)
        render_dir.mkdir(parents=True, exist_ok=True)

        print("wellplot version:", wellplot.__version__)
        print("Production example:", example_logfile.relative_to(REPO_ROOT))
        print("Tutorial workspace:", tutorial_dir.relative_to(REPO_ROOT))
        print("Render output folder:", render_dir.relative_to(REPO_ROOT))
        """
    ).strip()


def _user_data_inspection_markdown(recipe: UserProductionRecipe) -> str:
    """Return the data-inspection markdown for one user tutorial."""
    return _join_markdown_lines(
        [
            "## Inspect The Source Data Before You Design The Plot",
            "",
            "A practical workflow starts by confirming two things:",
            "",
            "- which channels are available in the source file",
            "- which metadata fields are good enough to populate the heading",
            "",
            f"Use the shipped `{recipe.package_name}` example as the inspection source, then copy the same pattern to your own well.",
        ]
    )


def _user_data_inspection_code(tutorial: UserNotebookTutorial) -> str:
    """Return the code cell that inspects the source data for one tutorial."""
    channels = ", ".join(repr(channel) for channel in tutorial.inspection_channels)
    metadata_keys = ", ".join(repr(key) for key in tutorial.inspection_metadata_keys)
    return dedent(
        f"""
        from wellplot import load_datasets_for_logfile, load_logfile

        spec = load_logfile(example_logfile)
        datasets_by_section, _source_paths = load_datasets_for_logfile(spec, base_dir=example_logfile.parent)
        dataset = datasets_by_section["{tutorial.inspection_section_id}"]

        wanted_channels = [{channels}]
        available_channels = [channel for channel in wanted_channels if channel in dataset.channels]
        print("Sections available:", ", ".join(datasets_by_section))
        print("Channels used in this tutorial:", ", ".join(available_channels))
        print("Header fields available from the source data:")
        for key in [{metadata_keys}]:
            print(f"  {{key}}: {{dataset.well_metadata.get(key)}}")
        """
    ).strip()


def _user_data_inspection_output(tutorial: UserNotebookTutorial) -> str:
    """Return the executed output for the data-inspection cell."""
    from wellplot import load_datasets_for_logfile, load_logfile

    example_logfile = _production_logfile_path(tutorial.package_name)
    spec = load_logfile(example_logfile)
    datasets_by_section, _source_paths = load_datasets_for_logfile(
        spec,
        base_dir=example_logfile.parent,
    )
    dataset = datasets_by_section[tutorial.inspection_section_id]
    available_channels = [
        channel for channel in tutorial.inspection_channels if channel in dataset.channels
    ]
    lines = [
        f"Sections available: {', '.join(datasets_by_section)}",
        f"Channels used in this tutorial: {', '.join(available_channels)}",
        "Header fields available from the source data:",
    ]
    for key in tutorial.inspection_metadata_keys:
        lines.append(f"  {key}: {dataset.well_metadata.get(key)}")
    return "\n".join(lines)


def _user_template_markdown(tutorial: UserNotebookTutorial) -> str:
    """Return the markdown that explains the reusable template."""
    bullets = "\n".join(f"- {entry}" for entry in tutorial.template_explanation)
    return _join_markdown_lines(
        [
            "## Create The Reusable Template First",
            "",
            "This file should hold the decisions that you expect to reuse for many wells.",
            "",
            bullets,
            "",
            "Write the template once, then keep the later stage files focused on data sources, sections, tracks, and bindings.",
        ]
    )


def _user_template_write_code(tutorial: UserNotebookTutorial) -> str:
    """Return the code cell that writes the reusable tutorial template."""
    return "\n".join(
        [
            'template_path = tutorial_dir / "base.template.yaml"',
            "template_text = '''",
            tutorial.template_text,
            "'''",
            "template_path.write_text(template_text)",
            "",
            'print("Wrote:", template_path.relative_to(REPO_ROOT))',
        ]
    )


def _user_stage_markdown(stage: UserNotebookStage) -> str:
    """Return the markdown that introduces one user tutorial stage."""
    bullets = "\n".join(f"- {point}" for point in stage.teaching_points)
    return _join_markdown_lines(
        [
            f"## {stage.title}",
            "",
            stage.summary,
            "",
            "What this step teaches:",
            "",
            bullets,
        ]
    )


def _user_stage_write_code(stage: UserNotebookStage) -> str:
    """Return the code cell that writes one stage logfile."""
    variable = _python_identifier(stage.slug)
    return "\n".join(
        [
            f'{variable}_logfile_path = tutorial_dir / "{stage.slug}.log.yaml"',
            f"{variable}_logfile_text = '''",
            stage.logfile_text,
            "'''",
            f"{variable}_logfile_path.write_text({variable}_logfile_text)",
            "",
            f'print("Wrote:", {variable}_logfile_path.relative_to(REPO_ROOT))',
        ]
    )


def _user_stage_render_code(stage: UserNotebookStage) -> str:
    """Return the render cell for one user tutorial stage."""
    variable = _python_identifier(stage.slug)
    return dedent(
        f"""
        from wellplot import load_logfile, render_from_logfile

        spec = load_logfile({variable}_logfile_path)
        result = render_from_logfile({variable}_logfile_path)

        print("Validated:", spec.name)
        print("Pages created:", result.page_count)
        print("PDF written to:", result.output_path.relative_to(REPO_ROOT))
        """
    ).strip()


def _render_grouped_previews(
    logfile_path: Path,
    previews: tuple[UserNotebookPreview, ...],
) -> tuple[dict[str, bytes], int]:
    """Render grouped preview PNGs and return them by asset name."""
    previews_by_section: dict[str | None, set[int]] = {}
    for preview in previews:
        previews_by_section.setdefault(preview.section_id, set()).add(preview.page_index)

    rendered_pngs: dict[tuple[str | None, int], bytes] = {}
    full_page_count = 0
    for section_id, page_indexes in previews_by_section.items():
        figures = _render_logfile_figures(logfile_path, section_id=section_id)
        png_bytes, page_count = _figures_to_png_bytes(
            figures,
            page_indexes=tuple(sorted(page_indexes)),
        )
        if section_id is None:
            full_page_count = page_count
        for page_index, image_bytes in png_bytes.items():
            rendered_pngs[(section_id, page_index)] = image_bytes

    if full_page_count == 0:
        full_figures = _render_logfile_figures(logfile_path)
        _png_bytes, full_page_count = _figures_to_png_bytes(full_figures, page_indexes=(0,))

    asset_bytes: dict[str, bytes] = {}
    for preview in previews:
        asset_bytes[preview.asset_name] = rendered_pngs[(preview.section_id, preview.page_index)]
    return asset_bytes, full_page_count


def _user_stage_outputs(
    tutorial: UserNotebookTutorial,
    stage: UserNotebookStage,
    *,
    check: bool,
) -> tuple[str, int, list[dict[str, object]], int]:
    """Render checkpoint previews and notebook outputs for one user tutorial stage."""
    tutorials_root = REPO_ROOT / "workspace" / "tutorials"
    tutorials_root.mkdir(parents=True, exist_ok=True)
    changes = 0
    with TemporaryDirectory(dir=tutorials_root) as temp_dir:
        temp_root = Path(temp_dir)
        (temp_root / "renders").mkdir(parents=True, exist_ok=True)
        (temp_root / "base.template.yaml").write_text(tutorial.template_text)
        logfile_path = temp_root / f"{stage.slug}.log.yaml"
        logfile_path.write_text(stage.logfile_text)

        from wellplot import load_logfile

        spec = load_logfile(logfile_path)
        rendered_assets, page_count = _render_grouped_previews(logfile_path, stage.previews)

    outputs: list[dict[str, object]] = []
    for preview in stage.previews:
        png_bytes = rendered_assets[preview.asset_name]
        asset_path = USER_ASSETS_DIR / preview.asset_name
        if check:
            current = asset_path.read_bytes() if asset_path.exists() else None
            if current != png_bytes:
                raise SystemExit(f"Notebook asset is out of date: {asset_path}")
        elif _write_bytes_if_changed(asset_path, png_bytes):
            changes += 1
        outputs.append(markdown_output(f"### {preview.title}"))
        outputs.append(markdown_output(preview.summary))
        outputs.append(png_output(png_bytes))

    return spec.name, page_count, outputs, changes


def _user_adaptation_markdown(
    recipe: UserProductionRecipe,
    tutorial: UserNotebookTutorial,
) -> str:
    """Return the final adaptation checklist for one rewritten user notebook."""
    bullets = "\n".join(f"- {tip}" for tip in tutorial.adaptation_tips)
    developer_notebook = f"examples/notebooks/developer/{recipe.package_name}.ipynb"
    return _join_markdown_lines(
        [
            "## How To Adapt This Tutorial To Your Own Well",
            "",
            bullets,
            "",
            "## When To Open The Developer Notebook",
            "",
            "- use the developer notebook only when you want the raw repository example internals, full source dumps, or lower-level implementation details",
            f"- developer reference notebook: `{developer_notebook}`",
        ]
    )


def _computed_series_label(series: str) -> str:
    """Return the user-facing label for one computed-channel series."""
    labels = {"numpy": "NumPy", "pandas": "pandas"}
    return labels[series]


def _computed_series_dir(series: str) -> Path:
    """Return the notebook directory for one computed-channel series."""
    if series == "numpy":
        return USER_COMPUTED_NUMPY_DIR
    if series == "pandas":
        return USER_COMPUTED_PANDAS_DIR
    raise KeyError(f"Unsupported computed notebook series {series!r}.")


def _computed_notebook_path(series: str, package_name: str) -> Path:
    """Return the generated notebook path for one computed-channel recipe."""
    suffix = f"{series}_computed"
    return _computed_series_dir(series) / f"{package_name}_{suffix}.ipynb"


def _computed_workspace_rel(series: str, package_name: str) -> str:
    """Return the relative workspace folder used by one computed-channel notebook."""
    return f"workspace/tutorials/computed_{series}/{package_name}"


def _computed_output_rel(series: str, package_name: str, filename: str) -> str:
    """Return the expected output path for one computed-channel notebook artifact."""
    return f"{_computed_workspace_rel(series, package_name)}/{filename}"


def _computed_source_section_id(package_name: str) -> str:
    """Return the source section used by one computed-channel notebook."""
    if package_name == "cbl_log_example":
        return "main_pass"
    if package_name == "forge16b_porosity_example":
        return "upper_review"
    raise KeyError(f"Unsupported computed notebook package {package_name!r}.")


def _computed_source_channels(package_name: str) -> tuple[str, ...]:
    """Return the source channels highlighted by one computed-channel notebook."""
    if package_name == "cbl_log_example":
        return ("ECGR_STGC", "CBL", "TT", "VDL")
    if package_name == "forge16b_porosity_example":
        return ("GR", "ILD", "ILM", "RHOB", "NPHI")
    raise KeyError(f"Unsupported computed notebook package {package_name!r}.")


def _clean_numeric_values(values: object) -> object:
    """Return a numeric array with common LAS/DLIS null sentinels converted to NaN."""
    import numpy as np

    data = np.asarray(values, dtype=float)
    return np.where(data <= -900.0, np.nan, data)


def _moving_average(values: object, window: int) -> object:
    """Return a simple NaN-tolerant moving average."""
    import numpy as np

    data = _clean_numeric_values(values)
    valid = np.isfinite(data)
    fill = float(np.nanmedian(data[valid])) if valid.any() else 0.0
    filled = np.where(valid, data, fill)
    kernel = np.ones(int(window), dtype=float) / float(window)
    return np.convolve(filled, kernel, mode="same")


def _computed_source_dataset(package_name: str) -> tuple[object, Path]:
    """Load the source dataset used by a computed-channel notebook."""
    from wellplot import load_logfile
    from wellplot.logfile import load_datasets_for_logfile

    logfile_path = _production_logfile_path(package_name)
    spec = load_logfile(logfile_path)
    datasets_by_section, source_paths_by_section = load_datasets_for_logfile(
        spec,
        base_dir=logfile_path.parent,
    )
    section_id = _computed_source_section_id(package_name)
    return datasets_by_section[section_id], source_paths_by_section[section_id]


def _computed_cbl_numpy_dataset(source_dataset: object) -> tuple[object, tuple[str, ...]]:
    """Build the CBL NumPy computed-channel dataset."""
    import numpy as np

    from wellplot import DatasetBuilder

    cbl = source_dataset.get_channel("CBL")
    vdl = source_dataset.get_channel("VDL")
    cbl_smooth = _moving_average(cbl.values, 41)
    bond_index = np.clip((80.0 - cbl_smooth) / 80.0, 0.0, 1.0)
    vdl_energy = np.nanmean(np.abs(np.asarray(vdl.values, dtype=float)), axis=1)
    p95 = float(np.nanpercentile(vdl_energy, 95))
    vdl_energy_norm = np.clip(vdl_energy / p95, 0.0, 1.0) if p95 else vdl_energy

    dataset = (
        DatasetBuilder(name="cbl-numpy-computed")
        .merge(source_dataset, merge_well_metadata=True, merge_provenance=True)
        .add_curve(
            mnemonic="CBL_SMOOTH_NP",
            values=cbl_smooth,
            index=cbl.depth,
            index_unit=cbl.depth_unit,
            value_unit="mV",
            source="numpy moving average",
            description="Moving-average CBL amplitude computed with NumPy.",
        )
        .add_curve(
            mnemonic="BOND_INDEX_NP",
            values=bond_index,
            index=cbl.depth,
            index_unit=cbl.depth_unit,
            value_unit="fraction",
            source="numpy expression",
            description="Simple normalized bond index from smoothed CBL amplitude.",
        )
        .add_curve(
            mnemonic="VDL_ENERGY_NP",
            values=vdl_energy_norm,
            index=vdl.depth,
            index_unit=vdl.depth_unit,
            value_unit="fraction",
            source="numpy mean absolute amplitude",
            description="Normalized VDL energy envelope computed from the raster trace.",
        )
        .build()
    )
    return dataset, ("CBL_SMOOTH_NP", "BOND_INDEX_NP", "VDL_ENERGY_NP")


def _computed_cbl_pandas_dataset(source_dataset: object) -> tuple[object, tuple[str, ...]]:
    """Build the CBL pandas computed-channel dataset."""
    import pandas as pd

    from wellplot import DatasetBuilder

    cbl = source_dataset.get_channel("CBL")
    tt = source_dataset.get_channel("TT")
    gr = source_dataset.get_channel("ECGR_STGC")
    frame = pd.DataFrame(
        {
            "CBL": cbl.values,
            "TT": tt.values,
            "GR": gr.values,
        },
        index=cbl.depth,
    )
    frame.index.name = "DEPTH_IN"
    frame = frame.mask(frame <= -900.0)
    frame["CBL_ROLLING_PD"] = frame["CBL"].rolling(41, center=True, min_periods=1).median()
    frame["BOND_INDEX_PD"] = ((80.0 - frame["CBL_ROLLING_PD"]) / 80.0).clip(0.0, 1.0)
    frame["TT_DELTA_PD"] = (
        frame["TT"]
        - frame["TT"]
        .rolling(
            41,
            center=True,
            min_periods=1,
        )
        .median()
    )

    dataset = (
        DatasetBuilder(name="cbl-pandas-computed")
        .merge(source_dataset, merge_well_metadata=True, merge_provenance=True)
        .add_dataframe(
            frame[["CBL_ROLLING_PD", "BOND_INDEX_PD", "TT_DELTA_PD"]],
            use_index=True,
            index_unit=cbl.depth_unit,
            curves={
                "CBL_ROLLING_PD": {
                    "value_unit": "mV",
                    "source": "pandas rolling median",
                    "description": "Rolling-median CBL amplitude computed with pandas.",
                },
                "BOND_INDEX_PD": {
                    "value_unit": "fraction",
                    "source": "pandas expression",
                    "description": "Simple normalized bond index from rolling CBL amplitude.",
                },
                "TT_DELTA_PD": {
                    "value_unit": "us",
                    "source": "pandas rolling median",
                    "description": "Transit-time deviation from a rolling median trend.",
                },
            },
        )
        .build()
    )
    return dataset, ("CBL_ROLLING_PD", "BOND_INDEX_PD", "TT_DELTA_PD")


def _computed_porosity_numpy_dataset(source_dataset: object) -> tuple[object, tuple[str, ...]]:
    """Build the porosity NumPy computed-channel dataset."""
    import numpy as np

    from wellplot import DatasetBuilder

    rhob_channel = source_dataset.get_channel("RHOB")
    depth = rhob_channel.depth
    depth_unit = rhob_channel.depth_unit
    rhob = _clean_numeric_values(rhob_channel.values)
    nphi = _clean_numeric_values(source_dataset.get_channel("NPHI").values)
    gr = _clean_numeric_values(source_dataset.get_channel("GR").values)
    ild = _clean_numeric_values(source_dataset.get_channel("ILD").values)
    ilm = _clean_numeric_values(source_dataset.get_channel("ILM").values)

    phid = np.clip((2.65 - rhob) / (2.65 - 1.0) * 100.0, -15.0, 60.0)
    neutron_density_separation = np.clip(nphi - phid, -30.0, 30.0)
    resistivity_ratio = np.log10(np.clip(ild, 0.2, None) / np.clip(ilm, 0.2, None))
    shale_index = np.clip((gr - 35.0) / (120.0 - 35.0), 0.0, 1.0)

    dataset = (
        DatasetBuilder(name="porosity-numpy-computed")
        .merge(source_dataset, merge_well_metadata=True, merge_provenance=True)
        .add_curve(
            mnemonic="PHID_NP",
            values=phid,
            index=depth,
            index_unit=depth_unit,
            value_unit="pu",
            source="numpy density porosity",
            description="Density porosity from RHOB using matrix/fluid density assumptions.",
        )
        .add_curve(
            mnemonic="ND_SEP_NP",
            values=neutron_density_separation,
            index=depth,
            index_unit=depth_unit,
            value_unit="pu",
            source="numpy expression",
            description="NPHI minus computed density porosity.",
        )
        .add_curve(
            mnemonic="RES_RATIO_NP",
            values=resistivity_ratio,
            index=depth,
            index_unit=depth_unit,
            value_unit="log10 ratio",
            source="numpy log ratio",
            description="Log10 deep-to-medium resistivity ratio.",
        )
        .add_curve(
            mnemonic="VSH_GR_NP",
            values=shale_index,
            index=depth,
            index_unit=depth_unit,
            value_unit="fraction",
            source="numpy linear GR index",
            description="Simple gamma-ray shale index clipped to 0-1.",
        )
        .build()
    )
    return dataset, ("PHID_NP", "ND_SEP_NP", "RES_RATIO_NP", "VSH_GR_NP")


def _computed_porosity_pandas_dataset(source_dataset: object) -> tuple[object, tuple[str, ...]]:
    """Build the porosity pandas computed-channel dataset."""
    import numpy as np
    import pandas as pd

    from wellplot import DatasetBuilder

    rhob_channel = source_dataset.get_channel("RHOB")
    depth = rhob_channel.depth
    depth_unit = rhob_channel.depth_unit
    frame = pd.DataFrame(
        {
            "GR": source_dataset.get_channel("GR").values,
            "ILD": source_dataset.get_channel("ILD").values,
            "ILM": source_dataset.get_channel("ILM").values,
            "RHOB": rhob_channel.values,
            "NPHI": source_dataset.get_channel("NPHI").values,
        },
        index=depth,
    )
    frame.index.name = "DEPTH_FT"
    frame = frame.mask(frame <= -900.0)
    frame["GR_SMOOTH_PD"] = frame["GR"].rolling(21, center=True, min_periods=1).mean()
    frame["PHID_PD"] = ((2.65 - frame["RHOB"]) / (2.65 - 1.0) * 100.0).clip(-15.0, 60.0)
    frame["ND_SEP_PD"] = (frame["NPHI"] - frame["PHID_PD"]).clip(-30.0, 30.0)
    frame["RES_RATIO_PD"] = np.log10(frame["ILD"].clip(lower=0.2) / frame["ILM"].clip(lower=0.2))
    frame["VSH_GR_PD"] = ((frame["GR_SMOOTH_PD"] - 35.0) / (120.0 - 35.0)).clip(0.0, 1.0)

    dataset = (
        DatasetBuilder(name="porosity-pandas-computed")
        .merge(source_dataset, merge_well_metadata=True, merge_provenance=True)
        .add_dataframe(
            frame[["GR_SMOOTH_PD", "PHID_PD", "ND_SEP_PD", "RES_RATIO_PD", "VSH_GR_PD"]],
            use_index=True,
            index_unit=depth_unit,
            curves={
                "GR_SMOOTH_PD": {
                    "value_unit": "gAPI",
                    "source": "pandas rolling mean",
                    "description": "Rolling-mean gamma ray for shale-index stabilization.",
                },
                "PHID_PD": {
                    "value_unit": "pu",
                    "source": "pandas density porosity",
                    "description": "Density porosity from RHOB.",
                },
                "ND_SEP_PD": {
                    "value_unit": "pu",
                    "source": "pandas expression",
                    "description": "NPHI minus computed density porosity.",
                },
                "RES_RATIO_PD": {
                    "value_unit": "log10 ratio",
                    "source": "pandas expression",
                    "description": "Log10 deep-to-medium resistivity ratio.",
                },
                "VSH_GR_PD": {
                    "value_unit": "fraction",
                    "source": "pandas expression",
                    "description": "Simple gamma-ray shale index clipped to 0-1.",
                },
            },
        )
        .build()
    )
    return dataset, ("GR_SMOOTH_PD", "PHID_PD", "ND_SEP_PD", "RES_RATIO_PD", "VSH_GR_PD")


def _computed_dataset(
    package_name: str,
    series: str,
    source_dataset: object,
) -> tuple[object, tuple[str, ...]]:
    """Build the computed dataset for one notebook."""
    if package_name == "cbl_log_example" and series == "numpy":
        return _computed_cbl_numpy_dataset(source_dataset)
    if package_name == "cbl_log_example" and series == "pandas":
        return _computed_cbl_pandas_dataset(source_dataset)
    if package_name == "forge16b_porosity_example" and series == "numpy":
        return _computed_porosity_numpy_dataset(source_dataset)
    if package_name == "forge16b_porosity_example" and series == "pandas":
        return _computed_porosity_pandas_dataset(source_dataset)
    raise KeyError(f"Unsupported computed recipe {package_name!r}/{series!r}.")


def _computed_channel_stats(dataset: object, channels: tuple[str, ...]) -> str:
    """Return deterministic summary lines for computed channels."""
    import numpy as np

    lines = ["Computed channels added:"]
    for mnemonic in channels:
        channel = dataset.get_channel(mnemonic)
        values = _clean_numeric_values(channel.values)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            lines.append(f"  {mnemonic}: no finite values")
            continue
        lines.append(
            f"  {mnemonic}: min={np.nanmin(finite):.3g}, "
            f"p50={np.nanpercentile(finite, 50):.3g}, max={np.nanmax(finite):.3g}"
        )
    return "\n".join(lines)


def _computed_report(
    package_name: str,
    series: str,
    dataset: object,
) -> object:
    """Build the programmatic report for one computed-channel notebook."""
    if package_name == "cbl_log_example":
        return _computed_cbl_report(series, dataset)
    if package_name == "forge16b_porosity_example":
        return _computed_porosity_report(series, dataset)
    raise KeyError(f"Unsupported computed notebook package {package_name!r}.")


def _computed_header_objects() -> dict[str, object]:
    """Return compact track-header objects used by computed notebooks."""
    return {
        "objects": [
            {"kind": "title", "enabled": False, "reserve_space": False},
            {"kind": "scale", "enabled": True, "line_units": 1},
            {"kind": "legend", "enabled": True, "line_units": 2},
            {"kind": "divisions", "enabled": False, "reserve_space": False},
        ]
    }


def _computed_reference_track() -> dict[str, object]:
    """Return the reference-track configuration used by computed notebooks."""
    return {
        "axis": "depth",
        "define_layout": True,
        "unit": "ft",
        "scale_ratio": 240,
        "major_step": 10,
        "secondary_grid": {"display": True, "line_count": 5},
        "header": {"display_unit": True, "display_scale": True},
    }


def _computed_base_builder(
    *,
    name: str,
    method_label: str,
    package_name: str,
    output_filename: str,
    source_dataset: object,
) -> object:
    """Return a base LogBuilder configured for computed-channel notebooks."""
    from wellplot import LogBuilder

    builder = LogBuilder(name=name)
    builder.set_render(
        backend="matplotlib",
        output_path=_computed_output_rel(
            method_label.lower(),
            package_name,
            f"renders/{output_filename}",
        ),
        dpi=150,
    )
    builder.set_page(
        size="A4",
        orientation="portrait",
        continuous=False,
        bottom_track_header_enabled=True,
        margin_left_mm=0,
        margin_right_mm=8,
        margin_top_mm=0,
        margin_bottom_mm=0,
        track_gap_mm=0,
        header_height_mm=0,
        footer_height_mm=0,
        track_header_height_mm=26,
    )
    builder.set_depth_axis(unit="ft", scale=240, major_step=10, minor_step=2)
    builder.set_heading(
        enabled=True,
        provider_name="wellplot",
        service_titles=[
            {
                "value": name,
                "alignment": "center",
                "font_size": 15,
                "bold": True,
                "auto_adjust": True,
            }
        ],
        general_fields=[
            {"key": "well", "label": "Well", "value": source_dataset.well_metadata.get("WELL", "")},
            {"key": "method", "label": "Computed With", "value": method_label},
            {"key": "workflow", "label": "Layout Source", "value": "LogBuilder + save_report"},
        ],
        tail_enabled=False,
    )
    builder.set_remarks(
        [
            {
                "title": "Computed-Channel Recipe",
                "lines": [
                    f"This notebook computes derived channels with {method_label} and attaches them to an in-memory WellDataset.",
                    "The YAML is generated from wellplot builders instead of hand-edited text.",
                    "The saved YAML captures the layout; computed channels are recreated by the notebook code.",
                ],
                "alignment": "left",
            }
        ]
    )
    builder.set_on_missing("skip")
    return builder


def _computed_cbl_report(series: str, dataset: object) -> object:
    """Build the CBL computed-channel report."""
    method_label = _computed_series_label(series)
    smooth_channel = "CBL_SMOOTH_NP" if series == "numpy" else "CBL_ROLLING_PD"
    bond_channel = "BOND_INDEX_NP" if series == "numpy" else "BOND_INDEX_PD"
    diagnostic_channel = "VDL_ENERGY_NP" if series == "numpy" else "TT_DELTA_PD"
    diagnostic_label = "VDL Energy" if series == "numpy" else "TT Delta"
    diagnostic_scale = (
        {"kind": "linear", "min": 0, "max": 1}
        if series == "numpy"
        else {"kind": "linear", "min": -50, "max": 50}
    )
    builder = _computed_base_builder(
        name=f"CBL Computed {method_label} Recipe",
        method_label=method_label,
        package_name="cbl_log_example",
        output_filename=f"cbl_{series}_computed.pdf",
        source_dataset=dataset,
    )
    builder.set_depth_range(8230, 8490)
    header = _computed_header_objects()
    section = builder.add_section(
        "main_pass",
        dataset=dataset,
        title=f"Main Pass - {method_label} Computed Channels",
        subtitle="Raw CBL, computed bond index, and VDL context",
        depth_range=(8230, 8490),
        source_name="CBL_Main.dlis + notebook computed channels",
    )
    section.add_track(
        id="gr", title="", kind="normal", width_mm=32, position=1, track_header=header
    )
    section.add_track(
        id="depth",
        title="",
        kind="reference",
        width_mm=24,
        position=2,
        reference=_computed_reference_track(),
        track_header=header,
    )
    section.add_track(
        id="cbl",
        title="",
        kind="normal",
        width_mm=42,
        position=3,
        track_header=header,
    )
    section.add_track(
        id="computed",
        title="",
        kind="normal",
        width_mm=36,
        position=4,
        track_header=header,
    )
    section.add_track(
        id="vdl",
        title="",
        kind="array",
        width_mm=48,
        position=5,
        x_scale={"kind": "linear", "min": 200, "max": 1200},
        grid={"vertical": {"main": {"visible": False}, "secondary": {"visible": False}}},
        track_header=header,
    )
    section.add_curve(
        channel="ECGR_STGC",
        track_id="gr",
        label="Gamma Ray",
        style={"color": "#15803d", "line_width": 0.75},
        scale={"kind": "linear", "min": 0, "max": 200},
    )
    section.add_curve(
        channel="CBL",
        track_id="cbl",
        label="CBL Raw",
        style={"color": "#111111", "line_width": 0.7},
        scale={"kind": "linear", "min": 0, "max": 100},
    )
    section.add_curve(
        channel=smooth_channel,
        track_id="cbl",
        label="CBL Smoothed",
        style={"color": "#1d4ed8", "line_width": 0.9, "line_style": "--"},
        scale={"kind": "linear", "min": 0, "max": 100},
        header_display={"wrap_name": True},
    )
    section.add_curve(
        channel=bond_channel,
        track_id="computed",
        label="Bond Index",
        style={"color": "#b45309", "line_width": 0.9},
        scale={"kind": "linear", "min": 0, "max": 1},
        fill={"kind": "to_lower_limit", "label": "Higher bond", "color": "#fbbf24", "alpha": 0.25},
    )
    section.add_curve(
        channel=diagnostic_channel,
        track_id="computed",
        label=diagnostic_label,
        style={"color": "#7c3aed", "line_width": 0.8, "line_style": ":"},
        scale=diagnostic_scale,
        header_display={"wrap_name": True},
    )
    section.add_raster(
        channel="VDL",
        track_id="vdl",
        label="VDL",
        profile="vdl",
        colorbar={"enabled": True, "label": "Amplitude", "position": "header"},
        sample_axis={"enabled": True, "unit": "us", "min": 200, "max": 1200, "ticks": 5},
    )
    return builder.build()


def _computed_porosity_report(series: str, dataset: object) -> object:
    """Build the porosity computed-channel report."""
    method_label = _computed_series_label(series)
    phid_channel = "PHID_NP" if series == "numpy" else "PHID_PD"
    nd_sep_channel = "ND_SEP_NP" if series == "numpy" else "ND_SEP_PD"
    res_ratio_channel = "RES_RATIO_NP" if series == "numpy" else "RES_RATIO_PD"
    vsh_channel = "VSH_GR_NP" if series == "numpy" else "VSH_GR_PD"
    gr_channel = "GR" if series == "numpy" else "GR_SMOOTH_PD"
    builder = _computed_base_builder(
        name=f"Porosity Computed {method_label} Recipe",
        method_label=method_label,
        package_name="forge16b_porosity_example",
        output_filename=f"porosity_{series}_computed.pdf",
        source_dataset=dataset,
    )
    builder.set_depth_range(8400, 9300)
    header = _computed_header_objects()
    section = builder.add_section(
        "upper_review",
        dataset=dataset,
        title=f"Upper Review - {method_label} Computed Channels",
        subtitle="Density porosity, neutron-density separation, and resistivity ratio",
        depth_range=(8400, 9300),
        source_name="30-23a-3 8117_d.las + notebook computed channels",
    )
    section.add_track(
        id="gr", title="", kind="normal", width_mm=34, position=1, track_header=header
    )
    section.add_track(
        id="depth",
        title="",
        kind="reference",
        width_mm=24,
        position=2,
        reference=_computed_reference_track(),
        track_header=header,
    )
    section.add_track(
        id="res",
        title="",
        kind="normal",
        width_mm=42,
        position=3,
        track_header=header,
    )
    section.add_track(
        id="por",
        title="",
        kind="normal",
        width_mm=48,
        position=4,
        track_header=header,
    )
    section.add_track(
        id="computed",
        title="",
        kind="normal",
        width_mm=34,
        position=5,
        track_header=header,
    )
    section.add_curve(
        channel=gr_channel,
        track_id="gr",
        label="Gamma Ray" if series == "numpy" else "GR Smooth",
        style={"color": "#16a34a", "line_width": 0.8},
        scale={"kind": "linear", "min": 0, "max": 150},
        fill={"kind": "to_lower_limit", "label": "GR Fill", "color": "#8fd19e", "alpha": 0.22},
    )
    section.add_curve(
        channel=vsh_channel,
        track_id="gr",
        label="GR Shale Index",
        style={"color": "#b45309", "line_width": 0.8, "line_style": "--"},
        scale={"kind": "linear", "min": 0, "max": 1},
        header_display={"wrap_name": True},
    )
    section.add_curve(
        channel="ILD",
        track_id="res",
        label="ILD",
        style={"color": "#111111", "line_width": 0.75},
        scale={"kind": "log", "min": 0.2, "max": 2000},
    )
    section.add_curve(
        channel="ILM",
        track_id="res",
        label="ILM",
        style={"color": "#2142ff", "line_width": 0.7, "line_style": "--"},
        scale={"kind": "log", "min": 0.2, "max": 2000},
    )
    section.add_curve(
        channel="NPHI",
        track_id="por",
        label="NPHI",
        style={"color": "#2142ff", "line_width": 0.75},
        scale={"kind": "linear", "min": -5, "max": 45, "reverse": True},
        fill={
            "kind": "between_curves",
            "other_channel": phid_channel,
            "label": "N-D Crossover",
            "crossover": {
                "enabled": True,
                "left_color": "#bfdbfe",
                "right_color": "#fbbf24",
                "alpha": 0.28,
            },
        },
    )
    section.add_curve(
        channel=phid_channel,
        track_id="por",
        label="PHID from RHOB",
        style={"color": "#111111", "line_width": 0.75},
        scale={"kind": "linear", "min": -5, "max": 45, "reverse": True},
        header_display={"wrap_name": True},
    )
    section.add_curve(
        channel=res_ratio_channel,
        track_id="computed",
        label="Log ILD/ILM",
        style={"color": "#7c3aed", "line_width": 0.8},
        scale={"kind": "linear", "min": -0.5, "max": 0.5},
        header_display={"wrap_name": True},
    )
    section.add_curve(
        channel=nd_sep_channel,
        track_id="computed",
        label="NPHI-PHID",
        style={"color": "#d97706", "line_width": 0.8, "line_style": "--"},
        scale={"kind": "linear", "min": -30, "max": 30},
        header_display={"wrap_name": True},
    )
    return builder.build()


def _computed_intro_markdown(package_name: str, series: str) -> str:
    """Return the opening markdown for one computed-channel notebook."""
    method_label = _computed_series_label(series)
    if package_name == "cbl_log_example":
        title = f"CBL/VDL Computed Channels With {method_label}"
        focus = "cement-bond interpretation curves from the CBL/VDL production example"
    else:
        title = f"Density-Neutron Computed Channels With {method_label}"
        focus = "porosity and gas-crossover curves from the open-hole production example"
    return _join_markdown_lines(
        [
            f"# {title}",
            "",
            f"This recipe uses {method_label} to compute {focus}.",
            "",
            "The important shift from the YAML-first notebooks is that the data and the layout are both created from Python:",
            "",
            "- source channels are loaded from the public example data",
            "- derived channels are computed in the notebook and attached to a working `WellDataset`",
            "- `LogBuilder` and `SectionBuilder` create tracks, bindings, fills, headings, and remarks",
            "- `save_report(...)` writes the generated YAML layout artifact",
            "- `render_report(...)` renders the in-memory report that still carries the computed channels",
            "",
            "Important limitation: the saved YAML records the layout, but it does not persist the computed channel arrays by itself. To reproduce the computed curves, rerun the notebook or export the computed dataset with a project-specific data export step.",
        ]
    )


def _computed_setup_code(package_name: str, series: str) -> str:
    """Return setup code for one computed-channel notebook."""
    section_id = _computed_source_section_id(package_name)
    return dedent(
        f"""
        from pathlib import Path

        try:
            import wellplot
        except ImportError as exc:
            raise RuntimeError(
                "Install the published 'wellplot' package in the active environment "
                "before running this notebook."
            ) from exc

        cwd = Path.cwd().resolve()
        REPO_ROOT = next((path for path in (cwd, *cwd.parents) if (path / "examples").exists()), None)
        if REPO_ROOT is None:
            raise RuntimeError(
                "Run this notebook from a checkout of the wellplot repository so the "
                "example files and sample data are available."
            )

        package_dir = REPO_ROOT / "examples" / "production" / "{package_name}"
        example_logfile = package_dir / "full_reconstruction.log.yaml"
        source_section = "{section_id}"
        tutorial_dir = REPO_ROOT / "{_computed_workspace_rel(series, package_name)}"
        render_dir = tutorial_dir / "renders"
        tutorial_dir.mkdir(parents=True, exist_ok=True)
        render_dir.mkdir(parents=True, exist_ok=True)

        print("wellplot version:", wellplot.__version__)
        print("Production example:", example_logfile.relative_to(REPO_ROOT))
        print("Source section:", source_section)
        print("Tutorial workspace:", tutorial_dir.relative_to(REPO_ROOT))
        """
    ).strip()


def _computed_setup_output(package_name: str, series: str) -> str:
    """Return deterministic setup output for one computed-channel notebook."""
    from wellplot import __version__ as wellplot_version

    return "\n".join(
        [
            f"wellplot version: {wellplot_version}",
            f"Production example: examples/production/{package_name}/full_reconstruction.log.yaml",
            f"Source section: {_computed_source_section_id(package_name)}",
            f"Tutorial workspace: {_computed_workspace_rel(series, package_name)}",
        ]
    )


def _computed_inspection_code(package_name: str) -> str:
    """Return source-data inspection code for one computed-channel notebook."""
    wanted = ", ".join(repr(channel) for channel in _computed_source_channels(package_name))
    return dedent(
        f"""
        from wellplot import load_datasets_for_logfile, load_logfile

        spec = load_logfile(example_logfile)
        datasets_by_section, source_paths_by_section = load_datasets_for_logfile(
            spec,
            base_dir=example_logfile.parent,
        )
        source_dataset = datasets_by_section[source_section]
        source_path = source_paths_by_section[source_section]

        wanted_channels = [{wanted}]
        print("Source file:", source_path.relative_to(REPO_ROOT))
        print("Dataset name:", source_dataset.name)
        print("Depth range, ft:", tuple(round(value, 2) for value in source_dataset.depth_range("ft")))
        print("Channels used here:")
        for mnemonic in wanted_channels:
            channel = source_dataset.get_channel(mnemonic)
            print(f"  {{mnemonic}}: {{type(channel).__name__}}, unit={{getattr(channel, 'value_unit', None)}}")
        """
    ).strip()


def _computed_inspection_output(package_name: str) -> str:
    """Return deterministic inspection output for one computed-channel notebook."""
    dataset, source_path = _computed_source_dataset(package_name)
    lines = [
        f"Source file: {_relative_display_path(source_path)}",
        f"Dataset name: {dataset.name}",
        f"Depth range, ft: {tuple(round(value, 2) for value in dataset.depth_range('ft'))}",
        "Channels used here:",
    ]
    for mnemonic in _computed_source_channels(package_name):
        channel = dataset.get_channel(mnemonic)
        lines.append(
            f"  {mnemonic}: {type(channel).__name__}, unit={getattr(channel, 'value_unit', None)}"
        )
    return "\n".join(lines)


def _computed_compute_code(package_name: str, series: str) -> str:
    """Return the computed-channel code cell for one notebook."""
    if package_name == "cbl_log_example" and series == "numpy":
        return _computed_cbl_numpy_code()
    if package_name == "cbl_log_example" and series == "pandas":
        return _computed_cbl_pandas_code()
    if package_name == "forge16b_porosity_example" and series == "numpy":
        return _computed_porosity_numpy_code()
    if package_name == "forge16b_porosity_example" and series == "pandas":
        return _computed_porosity_pandas_code()
    raise KeyError(f"Unsupported computed recipe {package_name!r}/{series!r}.")


def _computed_cbl_numpy_code() -> str:
    """Return CBL NumPy computation code."""
    return dedent(
        """
        import numpy as np

        from wellplot import DatasetBuilder

        def clean_curve(values: object) -> np.ndarray:
            \"\"\"Replace common LAS/DLIS null sentinels with NaN.\"\"\"
            data = np.asarray(values, dtype=float)
            return np.where(data <= -900.0, np.nan, data)

        def moving_average(values: object, window: int) -> np.ndarray:
            \"\"\"Return a simple NaN-tolerant moving average.\"\"\"
            data = clean_curve(values)
            valid = np.isfinite(data)
            fill = float(np.nanmedian(data[valid])) if valid.any() else 0.0
            filled = np.where(valid, data, fill)
            kernel = np.ones(window, dtype=float) / float(window)
            return np.convolve(filled, kernel, mode="same")

        cbl = source_dataset.get_channel("CBL")
        vdl = source_dataset.get_channel("VDL")

        cbl_smooth = moving_average(cbl.values, window=41)
        bond_index = np.clip((80.0 - cbl_smooth) / 80.0, 0.0, 1.0)
        vdl_energy = np.nanmean(np.abs(np.asarray(vdl.values, dtype=float)), axis=1)
        vdl_energy_norm = np.clip(vdl_energy / np.nanpercentile(vdl_energy, 95), 0.0, 1.0)

        working_dataset = (
            DatasetBuilder(name="cbl-numpy-computed")
            .merge(source_dataset, merge_well_metadata=True, merge_provenance=True)
            .add_curve(
                mnemonic="CBL_SMOOTH_NP",
                values=cbl_smooth,
                index=cbl.depth,
                index_unit=cbl.depth_unit,
                value_unit="mV",
                description="Moving-average CBL amplitude computed with NumPy.",
            )
            .add_curve(
                mnemonic="BOND_INDEX_NP",
                values=bond_index,
                index=cbl.depth,
                index_unit=cbl.depth_unit,
                value_unit="fraction",
                description="Simple normalized bond index from smoothed CBL amplitude.",
            )
            .add_curve(
                mnemonic="VDL_ENERGY_NP",
                values=vdl_energy_norm,
                index=vdl.depth,
                index_unit=vdl.depth_unit,
                value_unit="fraction",
                description="Normalized VDL energy envelope computed from the raster trace.",
            )
            .build()
        )

        computed_channels = ("CBL_SMOOTH_NP", "BOND_INDEX_NP", "VDL_ENERGY_NP")
        print("Working dataset:", working_dataset.name)
        print("Computed channels added:")
        for mnemonic in computed_channels:
            channel = working_dataset.get_channel(mnemonic)
            values = clean_curve(channel.values)
            print(
                f"  {mnemonic}: min={np.nanmin(values):.3g}, "
                f"p50={np.nanpercentile(values, 50):.3g}, max={np.nanmax(values):.3g}"
            )
        """
    ).strip()


def _computed_cbl_pandas_code() -> str:
    """Return CBL pandas computation code."""
    return dedent(
        """
        import pandas as pd

        from wellplot import DatasetBuilder

        cbl = source_dataset.get_channel("CBL")
        tt = source_dataset.get_channel("TT")
        gr = source_dataset.get_channel("ECGR_STGC")

        frame = pd.DataFrame(
            {
                "CBL": cbl.values,
                "TT": tt.values,
                "GR": gr.values,
            },
            index=cbl.depth,
        )
        frame.index.name = "DEPTH_IN"
        frame = frame.mask(frame <= -900.0)
        frame["CBL_ROLLING_PD"] = frame["CBL"].rolling(41, center=True, min_periods=1).median()
        frame["BOND_INDEX_PD"] = ((80.0 - frame["CBL_ROLLING_PD"]) / 80.0).clip(0.0, 1.0)
        frame["TT_DELTA_PD"] = frame["TT"] - frame["TT"].rolling(
            41,
            center=True,
            min_periods=1,
        ).median()

        working_dataset = (
            DatasetBuilder(name="cbl-pandas-computed")
            .merge(source_dataset, merge_well_metadata=True, merge_provenance=True)
            .add_dataframe(
                frame[["CBL_ROLLING_PD", "BOND_INDEX_PD", "TT_DELTA_PD"]],
                use_index=True,
                index_unit=cbl.depth_unit,
                curves={
                    "CBL_ROLLING_PD": {
                        "value_unit": "mV",
                        "description": "Rolling-median CBL amplitude computed with pandas.",
                    },
                    "BOND_INDEX_PD": {
                        "value_unit": "fraction",
                        "description": "Simple normalized bond index from rolling CBL amplitude.",
                    },
                    "TT_DELTA_PD": {
                        "value_unit": "us",
                        "description": "Transit-time deviation from a rolling median trend.",
                    },
                },
            )
            .build()
        )

        computed_channels = ("CBL_ROLLING_PD", "BOND_INDEX_PD", "TT_DELTA_PD")
        print("Working dataset:", working_dataset.name)
        print("Computed channels added:")
        for mnemonic in computed_channels:
            series = frame[mnemonic]
            print(
                f"  {mnemonic}: min={series.min():.3g}, "
                f"p50={series.quantile(0.5):.3g}, max={series.max():.3g}"
            )
        """
    ).strip()


def _computed_porosity_numpy_code() -> str:
    """Return porosity NumPy computation code."""
    return dedent(
        """
        import numpy as np

        from wellplot import DatasetBuilder

        def clean_curve(values: object) -> np.ndarray:
            \"\"\"Replace common LAS/DLIS null sentinels with NaN.\"\"\"
            data = np.asarray(values, dtype=float)
            return np.where(data <= -900.0, np.nan, data)

        rhob_channel = source_dataset.get_channel("RHOB")
        depth = rhob_channel.depth
        depth_unit = rhob_channel.depth_unit

        rhob = clean_curve(rhob_channel.values)
        nphi = clean_curve(source_dataset.get_channel("NPHI").values)
        gr = clean_curve(source_dataset.get_channel("GR").values)
        ild = clean_curve(source_dataset.get_channel("ILD").values)
        ilm = clean_curve(source_dataset.get_channel("ILM").values)

        phid = np.clip((2.65 - rhob) / (2.65 - 1.0) * 100.0, -15.0, 60.0)
        neutron_density_separation = np.clip(nphi - phid, -30.0, 30.0)
        resistivity_ratio = np.log10(np.clip(ild, 0.2, None) / np.clip(ilm, 0.2, None))
        shale_index = np.clip((gr - 35.0) / (120.0 - 35.0), 0.0, 1.0)

        working_dataset = (
            DatasetBuilder(name="porosity-numpy-computed")
            .merge(source_dataset, merge_well_metadata=True, merge_provenance=True)
            .add_curve(
                mnemonic="PHID_NP",
                values=phid,
                index=depth,
                index_unit=depth_unit,
                value_unit="pu",
                description="Density porosity from RHOB.",
            )
            .add_curve(
                mnemonic="ND_SEP_NP",
                values=neutron_density_separation,
                index=depth,
                index_unit=depth_unit,
                value_unit="pu",
                description="NPHI minus computed density porosity.",
            )
            .add_curve(
                mnemonic="RES_RATIO_NP",
                values=resistivity_ratio,
                index=depth,
                index_unit=depth_unit,
                value_unit="log10 ratio",
                description="Log10 deep-to-medium resistivity ratio.",
            )
            .add_curve(
                mnemonic="VSH_GR_NP",
                values=shale_index,
                index=depth,
                index_unit=depth_unit,
                value_unit="fraction",
                description="Simple gamma-ray shale index clipped to 0-1.",
            )
            .build()
        )

        computed_channels = ("PHID_NP", "ND_SEP_NP", "RES_RATIO_NP", "VSH_GR_NP")
        print("Working dataset:", working_dataset.name)
        print("Computed channels added:")
        for mnemonic in computed_channels:
            values = clean_curve(working_dataset.get_channel(mnemonic).values)
            print(
                f"  {mnemonic}: min={np.nanmin(values):.3g}, "
                f"p50={np.nanpercentile(values, 50):.3g}, max={np.nanmax(values):.3g}"
            )
        """
    ).strip()


def _computed_porosity_pandas_code() -> str:
    """Return porosity pandas computation code."""
    return dedent(
        """
        import numpy as np
        import pandas as pd

        from wellplot import DatasetBuilder

        rhob_channel = source_dataset.get_channel("RHOB")
        depth = rhob_channel.depth
        depth_unit = rhob_channel.depth_unit

        frame = pd.DataFrame(
            {
                "GR": source_dataset.get_channel("GR").values,
                "ILD": source_dataset.get_channel("ILD").values,
                "ILM": source_dataset.get_channel("ILM").values,
                "RHOB": rhob_channel.values,
                "NPHI": source_dataset.get_channel("NPHI").values,
            },
            index=depth,
        )
        frame.index.name = "DEPTH_FT"
        frame = frame.mask(frame <= -900.0)
        frame["GR_SMOOTH_PD"] = frame["GR"].rolling(21, center=True, min_periods=1).mean()
        frame["PHID_PD"] = ((2.65 - frame["RHOB"]) / (2.65 - 1.0) * 100.0).clip(-15.0, 60.0)
        frame["ND_SEP_PD"] = (frame["NPHI"] - frame["PHID_PD"]).clip(-30.0, 30.0)
        frame["RES_RATIO_PD"] = np.log10(frame["ILD"].clip(lower=0.2) / frame["ILM"].clip(lower=0.2))
        frame["VSH_GR_PD"] = ((frame["GR_SMOOTH_PD"] - 35.0) / (120.0 - 35.0)).clip(0.0, 1.0)

        working_dataset = (
            DatasetBuilder(name="porosity-pandas-computed")
            .merge(source_dataset, merge_well_metadata=True, merge_provenance=True)
            .add_dataframe(
                frame[["GR_SMOOTH_PD", "PHID_PD", "ND_SEP_PD", "RES_RATIO_PD", "VSH_GR_PD"]],
                use_index=True,
                index_unit=depth_unit,
                curves={
                    "GR_SMOOTH_PD": {"value_unit": "gAPI", "description": "Rolling-mean gamma ray."},
                    "PHID_PD": {"value_unit": "pu", "description": "Density porosity from RHOB."},
                    "ND_SEP_PD": {"value_unit": "pu", "description": "NPHI minus density porosity."},
                    "RES_RATIO_PD": {
                        "value_unit": "log10 ratio",
                        "description": "Log10 deep-to-medium resistivity ratio.",
                    },
                    "VSH_GR_PD": {
                        "value_unit": "fraction",
                        "description": "Simple gamma-ray shale index clipped to 0-1.",
                    },
                },
            )
            .build()
        )

        computed_channels = ("GR_SMOOTH_PD", "PHID_PD", "ND_SEP_PD", "RES_RATIO_PD", "VSH_GR_PD")
        print("Working dataset:", working_dataset.name)
        print("Computed channels added:")
        for mnemonic in computed_channels:
            series = frame[mnemonic]
            print(
                f"  {mnemonic}: min={series.min():.3g}, "
                f"p50={series.quantile(0.5):.3g}, max={series.max():.3g}"
            )
        """
    ).strip()


def _computed_report_code(package_name: str, series: str) -> str:
    """Return the programmatic report-builder code cell for one notebook."""
    if package_name == "cbl_log_example":
        return _computed_cbl_report_code(series)
    if package_name == "forge16b_porosity_example":
        return _computed_porosity_report_code(series)
    raise KeyError(f"Unsupported computed recipe {package_name!r}/{series!r}.")


def _computed_common_report_code_prelude(package_name: str, series: str) -> str:
    """Return shared report-builder setup code."""
    method_label = _computed_series_label(series)
    return dedent(
        f"""
        from IPython.display import Code, display

        from wellplot import LogBuilder, save_report

        yaml_path = tutorial_dir / "{package_name}_{series}_computed.yaml"
        pdf_path = render_dir / "{package_name}_{series}_computed.pdf"
        method_label = "{method_label}"

        header_objects = {{
            "objects": [
                {{"kind": "title", "enabled": False, "reserve_space": False}},
                {{"kind": "scale", "enabled": True, "line_units": 1}},
                {{"kind": "legend", "enabled": True, "line_units": 2}},
                {{"kind": "divisions", "enabled": False, "reserve_space": False}},
            ]
        }}
        reference_track = {{
            "axis": "depth",
            "define_layout": True,
            "unit": "ft",
            "scale_ratio": 240,
            "major_step": 10,
            "secondary_grid": {{"display": True, "line_count": 5}},
            "header": {{"display_unit": True, "display_scale": True}},
        }}
        """
    ).strip()


def _computed_cbl_report_code(series: str) -> str:
    """Return CBL report-builder code."""
    smooth_channel = "CBL_SMOOTH_NP" if series == "numpy" else "CBL_ROLLING_PD"
    bond_channel = "BOND_INDEX_NP" if series == "numpy" else "BOND_INDEX_PD"
    diagnostic_channel = "VDL_ENERGY_NP" if series == "numpy" else "TT_DELTA_PD"
    diagnostic_label = "VDL Energy" if series == "numpy" else "TT Delta"
    diagnostic_scale = (
        '{"kind": "linear", "min": 0, "max": 1}'
        if series == "numpy"
        else '{"kind": "linear", "min": -50, "max": 50}'
    )
    return "\n\n".join(
        [
            _computed_common_report_code_prelude("cbl_log_example", series),
            dedent(
                f"""
                builder = LogBuilder(name=f"CBL Computed {{method_label}} Recipe")
                builder.set_render(backend="matplotlib", output_path=str(pdf_path), dpi=150)
                builder.set_page(
                    size="A4",
                    orientation="portrait",
                    continuous=False,
                    bottom_track_header_enabled=True,
                    margin_left_mm=0,
                    margin_right_mm=8,
                    margin_top_mm=0,
                    margin_bottom_mm=0,
                    track_gap_mm=0,
                    header_height_mm=0,
                    footer_height_mm=0,
                    track_header_height_mm=26,
                )
                builder.set_depth_axis(unit="ft", scale=240, major_step=10, minor_step=2)
                builder.set_depth_range(8230, 8490)
                builder.set_heading(
                    enabled=True,
                    provider_name="wellplot",
                    service_titles=[
                        {{
                            "value": f"CBL Computed {{method_label}} Recipe",
                            "alignment": "center",
                            "font_size": 15,
                            "bold": True,
                            "auto_adjust": True,
                        }}
                    ],
                    general_fields=[
                        {{"key": "well", "label": "Well", "value": source_dataset.well_metadata.get("WELL", "")}},
                        {{"key": "method", "label": "Computed With", "value": method_label}},
                        {{"key": "workflow", "label": "Layout Source", "value": "LogBuilder + save_report"}},
                    ],
                    tail_enabled=False,
                )
                builder.set_remarks(
                    [
                        {{
                            "title": "Computed-Channel Recipe",
                            "lines": [
                                (
                                    f"This notebook computes derived channels with {{method_label}} "
                                    "and attaches them to an in-memory WellDataset."
                                ),
                                "The YAML is generated from wellplot builders instead of hand-edited text.",
                                (
                                    "The saved YAML captures the layout; computed channels are "
                                    "recreated by the notebook code."
                                ),
                            ],
                            "alignment": "left",
                        }}
                    ]
                )

                section = builder.add_section(
                    "main_pass",
                    dataset=working_dataset,
                    title=f"Main Pass - {{method_label}} Computed Channels",
                    subtitle="Raw CBL, computed bond index, and VDL context",
                    depth_range=(8230, 8490),
                    source_name="CBL_Main.dlis + notebook computed channels",
                )
                section.add_track(id="gr", title="", kind="normal", width_mm=32, position=1, track_header=header_objects)
                section.add_track(
                    id="depth",
                    title="",
                    kind="reference",
                    width_mm=24,
                    position=2,
                    reference=reference_track,
                    track_header=header_objects,
                )
                section.add_track(id="cbl", title="", kind="normal", width_mm=42, position=3, track_header=header_objects)
                section.add_track(
                    id="computed",
                    title="",
                    kind="normal",
                    width_mm=36,
                    position=4,
                    track_header=header_objects,
                )
                section.add_track(
                    id="vdl",
                    title="",
                    kind="array",
                    width_mm=48,
                    position=5,
                    x_scale={{"kind": "linear", "min": 200, "max": 1200}},
                    grid={{"vertical": {{"main": {{"visible": False}}, "secondary": {{"visible": False}}}}}},
                    track_header=header_objects,
                )

                section.add_curve(
                    channel="ECGR_STGC",
                    track_id="gr",
                    label="Gamma Ray",
                    style={{"color": "#15803d", "line_width": 0.75}},
                    scale={{"kind": "linear", "min": 0, "max": 200}},
                )
                section.add_curve(
                    channel="CBL",
                    track_id="cbl",
                    label="CBL Raw",
                    style={{"color": "#111111", "line_width": 0.7}},
                    scale={{"kind": "linear", "min": 0, "max": 100}},
                )
                section.add_curve(
                    channel="{smooth_channel}",
                    track_id="cbl",
                    label="CBL Smoothed",
                    style={{"color": "#1d4ed8", "line_width": 0.9, "line_style": "--"}},
                    scale={{"kind": "linear", "min": 0, "max": 100}},
                    header_display={{"wrap_name": True}},
                )
                section.add_curve(
                    channel="{bond_channel}",
                    track_id="computed",
                    label="Bond Index",
                    style={{"color": "#b45309", "line_width": 0.9}},
                    scale={{"kind": "linear", "min": 0, "max": 1}},
                    fill={{"kind": "to_lower_limit", "label": "Higher bond", "color": "#fbbf24", "alpha": 0.25}},
                )
                section.add_curve(
                    channel="{diagnostic_channel}",
                    track_id="computed",
                    label="{diagnostic_label}",
                    style={{"color": "#7c3aed", "line_width": 0.8, "line_style": ":"}},
                    scale={diagnostic_scale},
                    header_display={{"wrap_name": True}},
                )
                section.add_raster(
                    channel="VDL",
                    track_id="vdl",
                    label="VDL",
                    profile="vdl",
                    colorbar={{"enabled": True, "label": "Amplitude", "position": "header"}},
                    sample_axis={{"enabled": True, "unit": "us", "min": 200, "max": 1200, "ticks": 5}},
                )

                report = builder.build()
                save_report(report, yaml_path)
                print("Saved generated YAML:", yaml_path.relative_to(REPO_ROOT))
                print("Layout was created with LogBuilder and SectionBuilder.")
                print("Remember: rerun the notebook to recreate computed channel arrays.")
                display(Code(yaml_path.read_text(), language="yaml"))
                """
            ).strip(),
        ]
    )


def _computed_porosity_report_code(series: str) -> str:
    """Return porosity report-builder code."""
    phid_channel = "PHID_NP" if series == "numpy" else "PHID_PD"
    nd_sep_channel = "ND_SEP_NP" if series == "numpy" else "ND_SEP_PD"
    res_ratio_channel = "RES_RATIO_NP" if series == "numpy" else "RES_RATIO_PD"
    vsh_channel = "VSH_GR_NP" if series == "numpy" else "VSH_GR_PD"
    gr_channel = "GR" if series == "numpy" else "GR_SMOOTH_PD"
    gr_label = "Gamma Ray" if series == "numpy" else "GR Smooth"
    return "\n\n".join(
        [
            _computed_common_report_code_prelude("forge16b_porosity_example", series),
            dedent(
                f"""
                builder = LogBuilder(name=f"Porosity Computed {{method_label}} Recipe")
                builder.set_render(backend="matplotlib", output_path=str(pdf_path), dpi=150)
                builder.set_page(
                    size="A4",
                    orientation="portrait",
                    continuous=False,
                    bottom_track_header_enabled=True,
                    margin_left_mm=0,
                    margin_right_mm=8,
                    margin_top_mm=0,
                    margin_bottom_mm=0,
                    track_gap_mm=0,
                    header_height_mm=0,
                    footer_height_mm=0,
                    track_header_height_mm=26,
                )
                builder.set_depth_axis(unit="ft", scale=240, major_step=10, minor_step=2)
                builder.set_depth_range(8400, 9300)
                builder.set_heading(
                    enabled=True,
                    provider_name="wellplot",
                    service_titles=[
                        {{
                            "value": f"Porosity Computed {{method_label}} Recipe",
                            "alignment": "center",
                            "font_size": 15,
                            "bold": True,
                            "auto_adjust": True,
                        }}
                    ],
                    general_fields=[
                        {{"key": "well", "label": "Well", "value": source_dataset.well_metadata.get("WELL", "30-23a-3")}},
                        {{"key": "method", "label": "Computed With", "value": method_label}},
                        {{"key": "workflow", "label": "Layout Source", "value": "LogBuilder + save_report"}},
                    ],
                    tail_enabled=False,
                )
                builder.set_remarks(
                    [
                        {{
                            "title": "Computed-Channel Recipe",
                            "lines": [
                                (
                                    f"This notebook computes derived channels with {{method_label}} "
                                    "and attaches them to an in-memory WellDataset."
                                ),
                                "The YAML is generated from wellplot builders instead of hand-edited text.",
                                (
                                    "The saved YAML captures the layout; computed channels are "
                                    "recreated by the notebook code."
                                ),
                            ],
                            "alignment": "left",
                        }}
                    ]
                )

                section = builder.add_section(
                    "upper_review",
                    dataset=working_dataset,
                    title=f"Upper Review - {{method_label}} Computed Channels",
                    subtitle="Density porosity, neutron-density separation, and resistivity ratio",
                    depth_range=(8400, 9300),
                    source_name="30-23a-3 8117_d.las + notebook computed channels",
                )
                section.add_track(id="gr", title="", kind="normal", width_mm=34, position=1, track_header=header_objects)
                section.add_track(
                    id="depth",
                    title="",
                    kind="reference",
                    width_mm=24,
                    position=2,
                    reference=reference_track,
                    track_header=header_objects,
                )
                section.add_track(id="res", title="", kind="normal", width_mm=42, position=3, track_header=header_objects)
                section.add_track(id="por", title="", kind="normal", width_mm=48, position=4, track_header=header_objects)
                section.add_track(
                    id="computed",
                    title="",
                    kind="normal",
                    width_mm=34,
                    position=5,
                    track_header=header_objects,
                )

                section.add_curve(
                    channel="{gr_channel}",
                    track_id="gr",
                    label="{gr_label}",
                    style={{"color": "#16a34a", "line_width": 0.8}},
                    scale={{"kind": "linear", "min": 0, "max": 150}},
                    fill={{"kind": "to_lower_limit", "label": "GR Fill", "color": "#8fd19e", "alpha": 0.22}},
                )
                section.add_curve(
                    channel="{vsh_channel}",
                    track_id="gr",
                    label="GR Shale Index",
                    style={{"color": "#b45309", "line_width": 0.8, "line_style": "--"}},
                    scale={{"kind": "linear", "min": 0, "max": 1}},
                    header_display={{"wrap_name": True}},
                )
                section.add_curve(
                    channel="ILD",
                    track_id="res",
                    label="ILD",
                    style={{"color": "#111111", "line_width": 0.75}},
                    scale={{"kind": "log", "min": 0.2, "max": 2000}},
                )
                section.add_curve(
                    channel="ILM",
                    track_id="res",
                    label="ILM",
                    style={{"color": "#2142ff", "line_width": 0.7, "line_style": "--"}},
                    scale={{"kind": "log", "min": 0.2, "max": 2000}},
                )
                section.add_curve(
                    channel="NPHI",
                    track_id="por",
                    label="NPHI",
                    style={{"color": "#2142ff", "line_width": 0.75}},
                    scale={{"kind": "linear", "min": -5, "max": 45, "reverse": True}},
                    fill={{
                        "kind": "between_curves",
                        "other_channel": "{phid_channel}",
                        "label": "N-D Crossover",
                        "crossover": {{
                            "enabled": True,
                            "left_color": "#bfdbfe",
                            "right_color": "#fbbf24",
                            "alpha": 0.28,
                        }},
                    }},
                )
                section.add_curve(
                    channel="{phid_channel}",
                    track_id="por",
                    label="PHID from RHOB",
                    style={{"color": "#111111", "line_width": 0.75}},
                    scale={{"kind": "linear", "min": -5, "max": 45, "reverse": True}},
                    header_display={{"wrap_name": True}},
                )
                section.add_curve(
                    channel="{res_ratio_channel}",
                    track_id="computed",
                    label="Log ILD/ILM",
                    style={{"color": "#7c3aed", "line_width": 0.8}},
                    scale={{"kind": "linear", "min": -0.5, "max": 0.5}},
                    header_display={{"wrap_name": True}},
                )
                section.add_curve(
                    channel="{nd_sep_channel}",
                    track_id="computed",
                    label="NPHI-PHID",
                    style={{"color": "#d97706", "line_width": 0.8, "line_style": "--"}},
                    scale={{"kind": "linear", "min": -30, "max": 30}},
                    header_display={{"wrap_name": True}},
                )

                report = builder.build()
                save_report(report, yaml_path)
                print("Saved generated YAML:", yaml_path.relative_to(REPO_ROOT))
                print("Layout was created with LogBuilder and SectionBuilder.")
                print("Remember: rerun the notebook to recreate computed channel arrays.")
                display(Code(yaml_path.read_text(), language="yaml"))
                """
            ).strip(),
        ]
    )


def _computed_report_output(package_name: str, series: str) -> str:
    """Return deterministic report-build output for one computed notebook."""
    return "\n".join(
        [
            f"Saved generated YAML: {_computed_output_rel(series, package_name, f'{package_name}_{series}_computed.yaml')}",
            "Layout was created with LogBuilder and SectionBuilder.",
            "Remember: rerun the notebook to recreate computed channel arrays.",
        ]
    )


def _computed_render_code(package_name: str, series: str) -> str:
    """Return the render code cell for one computed-channel notebook."""
    return dedent(
        """
        from io import BytesIO

        import matplotlib.pyplot as plt
        from IPython.display import Image, display

        from wellplot import render_report

        preview_result = render_report(report)
        preview_page_index = min(1, preview_result.page_count - 1)

        buffer = BytesIO()
        preview_result.artifact[preview_page_index].savefig(buffer, format="png", dpi=140)
        preview_png = buffer.getvalue()
        for figure in preview_result.artifact:
            plt.close(figure)

        display(Image(data=preview_png))

        pdf_result = render_report(report, output_path=pdf_path)
        print("Pages created:", pdf_result.page_count)
        print("Preview page shown:", preview_page_index + 1)
        print("PDF written to:", pdf_result.output_path.relative_to(REPO_ROOT))
        """
    ).strip()


def _computed_render_outputs(
    package_name: str,
    series: str,
) -> tuple[str, list[dict[str, object]]]:
    """Render one computed-channel notebook preview and return output payloads."""
    from wellplot import render_report

    source_dataset, _source_path = _computed_source_dataset(package_name)
    working_dataset, _computed_channels = _computed_dataset(package_name, series, source_dataset)
    report = _computed_report(package_name, series, working_dataset)
    result = render_report(report)
    preview_page_index = min(1, result.page_count - 1)
    png_by_page, page_count = _figures_to_png_bytes(
        result.artifact,
        page_indexes=(preview_page_index,),
    )
    pdf_filename = (
        f"cbl_{series}_computed.pdf"
        if package_name == "cbl_log_example"
        else f"porosity_{series}_computed.pdf"
    )
    output = "\n".join(
        [
            f"Pages created: {page_count}",
            f"Preview page shown: {preview_page_index + 1}",
            f"PDF written to: {_computed_output_rel(series, package_name, f'renders/{pdf_filename}')}",
        ]
    )
    return output, [png_output(png_by_page[preview_page_index])]


def _computed_compute_output(package_name: str, series: str) -> str:
    """Return deterministic compute-cell output for one computed-channel notebook."""
    source_dataset, _source_path = _computed_source_dataset(package_name)
    working_dataset, computed_channels = _computed_dataset(package_name, series, source_dataset)
    return "\n".join(
        [
            f"Working dataset: {working_dataset.name}",
            _computed_channel_stats(working_dataset, computed_channels),
        ]
    )


def _computed_adaptation_markdown(package_name: str, series: str) -> str:
    """Return final adaptation notes for one computed-channel notebook."""
    method_label = _computed_series_label(series)
    if package_name == "cbl_log_example":
        example_tip = "replace the bond-index equation with your preferred cement-evaluation rule"
    else:
        example_tip = (
            "replace the matrix/fluid density constants with values appropriate for your reservoir"
        )
    return _join_markdown_lines(
        [
            "## How To Adapt This Recipe",
            "",
            f"- keep the {method_label} computation cell separate from the layout cell so petrophysical logic and plotting logic remain reviewable",
            f"- {example_tip}",
            "- add every derived channel to `working_dataset` before creating the report builder",
            "- use `LogBuilder` for repeatable YAML generation instead of copying and editing YAML by hand",
            "- remember that saved YAML does not persist in-memory computed arrays; export computed data separately if you need a standalone file-only workflow",
        ]
    )


def _computed_notebook(
    package_name: str,
    series: str,
) -> dict[str, object]:
    """Build one computed-channel user notebook."""
    compute_output = _computed_compute_output(package_name, series)
    render_output, render_preview_outputs = _computed_render_outputs(package_name, series)
    cells = [
        markdown_cell(_computed_intro_markdown(package_name, series)),
        code_cell(
            _computed_setup_code(package_name, series),
            execution_count=1,
            outputs=[stream_output(_computed_setup_output(package_name, series))],
        ),
        markdown_cell(
            "## Inspect The Source Channels\n\nStart by loading the same source data used by the production example and confirming the channels you will compute from."
        ),
        code_cell(
            _computed_inspection_code(package_name),
            execution_count=2,
            outputs=[stream_output(_computed_inspection_output(package_name))],
        ),
        markdown_cell(
            "## Compute New Channels\n\nThis cell creates derived curves and attaches them to a working dataset. In your own well, this is where your interpretation logic belongs."
        ),
        code_cell(
            _computed_compute_code(package_name, series),
            execution_count=3,
            outputs=[stream_output(compute_output)],
        ),
        markdown_cell(
            "## Create The YAML Layout With Builder Functions\n\nUse `LogBuilder` and `SectionBuilder` to create the same YAML structure that a hand-written file would contain, then save it with `save_report(...)`."
        ),
        code_cell(
            _computed_report_code(package_name, series),
            execution_count=4,
            outputs=[stream_output(_computed_report_output(package_name, series))],
        ),
        markdown_cell(
            "## Render The Computed Report\n\nRender from the in-memory report object so `wellplot` can see both the generated layout and the computed channels."
        ),
        code_cell(
            _computed_render_code(package_name, series),
            execution_count=5,
            outputs=[*render_preview_outputs, stream_output(render_output)],
        ),
        markdown_cell(_computed_adaptation_markdown(package_name, series)),
    ]
    return _notebook(cells)


def _legacy_triple_combo_notebook() -> dict[str, object]:
    """Build the notebook for the legacy triple-combo document example."""
    title = "Triple Combo Legacy Document Walkthrough"
    intro = dedent(
        """
        # Triple Combo Legacy Document Walkthrough

        This generated notebook is the recipe companion for
        `examples/triple_combo.yaml`.

        It shows the older document-plus-dataset rendering flow that predates the
        newer logfile pipeline. This is still useful when you want to study the
        lower-level document model directly or keep a synthetic layout example
        free from external LAS or DLIS dependencies.

        What you will practice in this walkthrough:

        - inspect a legacy document YAML directly
        - build a synthetic in-memory dataset
        - render the document through `MatplotlibRenderer`

        Prerequisites:

        - `pip install wellplot`
        - run the notebook from a checkout of this repository so the
          `examples/` files and sample data are available

        Runtime model:

        - import `wellplot` from the active installed environment
        - use the repository checkout for the example files, helper modules,
          and sample data
        """
    ).strip()
    cells = [
        markdown_cell(intro),
        code_cell(_repo_setup_code()),
        code_cell(_source_display_code("triple_combo.yaml", "yaml")),
        code_cell(
            dedent(
                """
                # Load the legacy document and summarize the structural parts that
                # matter before rendering.
                import yaml

                from wellplot import load_document

                document_path = EXAMPLES_DIR / "triple_combo.yaml"
                document_mapping = yaml.safe_load(document_path.read_text())
                document = load_document(document_path)

                print("Name:", document_mapping.get("name"))
                print("Track ids:", [track.get("id") for track in document_mapping.get("tracks", [])])
                print("Marker count:", len(document_mapping.get("markers", [])))
                print("Zone count:", len(document_mapping.get("zones", [])))
                """
            ).strip()
        ),
        code_cell(
            dedent(
                """
                # Reuse the synthetic dataset builder that already matches this
                # legacy document layout.
                import synthetic_demo as demo
                from wellplot.renderers import MatplotlibRenderer

                dataset = demo.build_dataset()
                renderer = MatplotlibRenderer()
                output_path = WORKSPACE_RENDERS / "synthetic_triple_combo.pdf"
                result = renderer.render(document, dataset, output_path=output_path)
                print("Pages:", result.page_count)
                print("Rendered:", result.output_path)
                """
            ).strip()
        ),
        markdown_cell(
            _adaptation_markdown(
                title,
                (
                    "Prefer the newer logfile or builder flows for new user-facing recipes unless you explicitly need the legacy document model.",
                    "Keep the synthetic dataset independent from external files when your goal is layout experimentation rather than data fidelity.",
                    "Move to a logfile-based example once you want templating, remarks, heading, and multisection packet features.",
                ),
            )
        ),
    ]
    return _notebook(cells)


def _python_notebook(recipe: PythonRecipe) -> dict[str, object]:
    """Build one Python-example walkthrough notebook."""
    cells: list[dict[str, object]] = [
        markdown_cell(_python_intro_markdown(recipe)),
        code_cell(_repo_setup_code()),
    ]
    if recipe.display_source:
        cells.append(code_cell(_source_display_code(recipe.source, "python")))
    cells.extend(code_cell(step) for step in recipe.code_cells)
    cells.append(markdown_cell(_adaptation_markdown(recipe.title, recipe.adaptation_tips)))
    return _notebook(cells)


def _yaml_notebook(path: Path, mapping: dict[str, object]) -> dict[str, object]:
    """Build one logfile-YAML walkthrough notebook."""
    title = str(mapping.get("name", path.name)).strip()
    cells = [
        markdown_cell(_yaml_intro_markdown(path, mapping)),
        code_cell(_repo_setup_code()),
        code_cell(_yaml_summary_code(path.name)),
        code_cell(_yaml_validate_render_code(path.name)),
        markdown_cell(_adaptation_markdown(title, _yaml_adaptation_tips(path.name))),
    ]
    return _notebook(cells)


def _production_notebook(
    package_name: str, title: str, prerequisites: tuple[str, ...]
) -> dict[str, object]:
    """Build one production-package walkthrough notebook."""
    cells = [
        markdown_cell(_production_intro_markdown(package_name, title, prerequisites)),
        code_cell(_repo_setup_code()),
        code_cell(_production_setup_code(package_name)),
        code_cell(_production_summary_code(package_name)),
        code_cell(_production_render_code(package_name)),
        markdown_cell(
            _adaptation_markdown(
                title,
                (
                    "Keep packet-wide styling, heading fields, and tail behavior in `base.template.yaml` so the reconstruction file stays focused on scope and bindings.",
                    "Update the data-source path, section depth windows, and remarks before you start retuning individual curves.",
                    "Preserve the public-data and IP notice when you publish derivative examples based on the same packet pattern.",
                ),
            )
        ),
    ]
    return _notebook(cells)


def _user_production_notebook(
    recipe: UserProductionRecipe,
    *,
    check: bool,
) -> tuple[dict[str, object], int]:
    """Build one rewritten user tutorial notebook and its checkpoint assets."""
    tutorial = _user_tutorial_for_recipe(recipe)
    setup_outputs = []

    from wellplot import __version__ as wellplot_version

    setup_outputs.append(
        stream_output(
            "\n".join(
                [
                    f"wellplot version: {wellplot_version}",
                    f"Production example: examples/production/{tutorial.package_name}/full_reconstruction.log.yaml",
                    f"Tutorial workspace: workspace/tutorials/{tutorial.package_name}",
                    f"Render output folder: workspace/tutorials/{tutorial.package_name}/renders",
                ]
            )
        )
    )

    cells: list[dict[str, object]] = [
        markdown_cell(
            _user_tutorial_intro_markdown(
                recipe,
                tutorial,
                prerequisites=_production_prerequisites(
                    _production_package_dir(recipe.package_name)
                ),
            )
        ),
        code_cell(
            _user_tutorial_setup_code(recipe.package_name),
            execution_count=1,
            outputs=setup_outputs,
        ),
        markdown_cell(_user_data_inspection_markdown(recipe)),
        code_cell(
            _user_data_inspection_code(tutorial),
            execution_count=2,
            outputs=[stream_output(_user_data_inspection_output(tutorial))],
        ),
        markdown_cell(_user_template_markdown(tutorial)),
        code_cell(
            _user_template_write_code(tutorial),
            execution_count=3,
            outputs=[
                stream_output(
                    f"Wrote: workspace/tutorials/{tutorial.package_name}/base.template.yaml"
                )
            ],
        ),
    ]

    execution_count = 4
    changes = 0
    for stage in tutorial.stages:
        spec_name, page_count, preview_outputs, asset_changes = _user_stage_outputs(
            tutorial,
            stage,
            check=check,
        )
        changes += asset_changes
        output_name = f"{stage.slug}.pdf"
        cells.append(markdown_cell(_user_stage_markdown(stage)))
        cells.append(
            code_cell(
                _user_stage_write_code(stage),
                execution_count=execution_count,
                outputs=[
                    stream_output(
                        f"Wrote: workspace/tutorials/{tutorial.package_name}/{stage.slug}.log.yaml"
                    )
                ],
            )
        )
        execution_count += 1
        cells.append(
            code_cell(
                _user_stage_render_code(stage),
                execution_count=execution_count,
                outputs=[
                    stream_output(
                        "\n".join(
                            [
                                f"Validated: {spec_name}",
                                f"Pages created: {page_count}",
                                f"PDF written to: {_tutorial_output_rel(tutorial.package_name, output_name)}",
                            ]
                        )
                    ),
                    *preview_outputs,
                ],
            )
        )
        execution_count += 1

    cells.append(markdown_cell(_user_adaptation_markdown(recipe, tutorial)))
    return _notebook(cells), changes


def _notebook(cells: list[dict[str, object]]) -> dict[str, object]:
    """Return a complete notebook payload."""
    normalized_cells: list[dict[str, object]] = []
    for index, cell in enumerate(cells):
        source = cell.get("source", [])
        seed = source[0].strip() if isinstance(source, list) and source else f"cell-{index}"
        cell_id = hashlib.md5(f"{index}:{cell.get('cell_type', '')}:{seed}".encode()).hexdigest()[
            :8
        ]
        normalized_cell = dict(cell)
        normalized_cell["id"] = cell_id
        normalized_cells.append(normalized_cell)
    return {
        "cells": normalized_cells,
        "metadata": KERNEL_METADATA,
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _relative_notebook_path(source: str) -> Path:
    """Return the notebook path that mirrors one source example."""
    if source.endswith(".log.yaml"):
        notebook_name = source.removesuffix(".log.yaml") + ".ipynb"
    elif source.endswith(".yaml"):
        notebook_name = source.removesuffix(".yaml") + ".ipynb"
    elif source.endswith(".py"):
        notebook_name = source.removesuffix(".py") + ".ipynb"
    else:
        raise ValueError(f"Unsupported example source {source!r}.")
    return DEVELOPER_NOTEBOOKS_DIR / notebook_name


def _production_notebook_path(package_name: str) -> Path:
    """Return the notebook path for one production package."""
    return DEVELOPER_NOTEBOOKS_DIR / f"{package_name}.ipynb"


def _user_notebook_path(package_name: str) -> Path:
    """Return the notebook path for one user-facing production package notebook."""
    return USER_NOTEBOOKS_DIR / f"{package_name}.ipynb"


def _production_title(package_dir: Path) -> str:
    """Return the title extracted from a production package README."""
    readme_path = package_dir / "README.md"
    for line in readme_path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.removeprefix("# ").strip() + " Walkthrough"
    return package_dir.name.replace("_", " ").title() + " Walkthrough"


def _production_prerequisites(package_dir: Path) -> tuple[str, ...]:
    """Return prerequisite installation steps for one production package."""
    mapping = _load_yaml(package_dir / "full_reconstruction.log.yaml")
    return _yaml_source_descriptions(mapping)


def _yaml_example_paths() -> list[Path]:
    """Return the top-level YAML example files that should get notebooks."""
    yaml_paths = set(EXAMPLES_DIR.glob("*.log.yaml"))
    yaml_paths.update(EXAMPLES_DIR.glob("*.yaml"))
    return sorted(path for path in yaml_paths if path.name != "README.md")


def _production_packages() -> list[Path]:
    """Return the production example package directories."""
    packages: list[Path] = []
    production_dir = EXAMPLES_DIR / "production"
    for package_dir in sorted(production_dir.iterdir()):
        if not package_dir.is_dir():
            continue
        if (package_dir / "full_reconstruction.log.yaml").exists():
            packages.append(package_dir)
    return packages


def _write_notebook(path: Path, notebook: dict[str, object], *, check: bool) -> bool:
    """Write or check one notebook payload."""
    rendered = json.dumps(notebook, indent=2) + "\n"
    rendered = _format_notebook_content(path, rendered)
    if check:
        current = path.read_text() if path.exists() else None
        if current != rendered:
            raise SystemExit(f"Notebook is out of date: {path}")
        return False
    return _write_if_changed(path, rendered)


def _format_notebook_content(path: Path, rendered: str) -> str:
    """Return notebook JSON normalized by Ruff's notebook formatter."""
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / path.name
        temp_path.write_text(rendered)
        subprocess.run(
            ["ruff", "format", str(temp_path)],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        return temp_path.read_text()


def _developer_grouped_notebook_list() -> dict[str, list[str]]:
    """Return grouped developer notebook names for the generated README."""
    grouped = {
        "Production package walkthroughs": [],
        "Programmatic API walkthroughs": [],
        "MCP walkthroughs": [],
        "YAML and legacy walkthroughs": [],
    }
    for package_dir in _production_packages():
        grouped["Production package walkthroughs"].append(
            _production_notebook_path(package_dir.name).name
        )
    for recipe in PYTHON_RECIPES.values():
        section = (
            "MCP walkthroughs"
            if recipe.source.startswith("mcp_")
            else "Programmatic API walkthroughs"
        )
        grouped[section].append(_relative_notebook_path(recipe.source).name)
    for path in _yaml_example_paths():
        if (
            path.name == "triple_combo.yaml"
            or path.suffix == ".yaml"
            or path.name.endswith(".log.yaml")
        ):
            grouped["YAML and legacy walkthroughs"].append(_relative_notebook_path(path.name).name)
    return grouped


def _root_readme_text() -> str:
    """Return the generated top-level README for examples/notebooks."""
    user_entries = sorted(
        _user_notebook_path(recipe.package_name).name for recipe in USER_PRODUCTION_RECIPES.values()
    )
    computed_numpy_entries = sorted(
        _computed_notebook_path("numpy", recipe.package_name).name
        for recipe in USER_PRODUCTION_RECIPES.values()
    )
    computed_pandas_entries = sorted(
        _computed_notebook_path("pandas", recipe.package_name).name
        for recipe in USER_PRODUCTION_RECIPES.values()
    )
    parts = [
        "# Example Notebooks",
        "",
        "This directory is split by audience:",
        "",
        "- `user/` contains curated, executed notebooks aimed at geologists, petrophysicists,",
        "  and other end users who want to run and adapt a production example with minimal",
        "  Python knowledge.",
        "- `developer/` contains unexecuted reference notebooks that mirror the repository",
        "  example set and expose the raw YAML, source code, and implementation details.",
        "",
        "These files are generated by `scripts/generate_example_notebooks.py`.",
        "",
        "## Start Here",
        "",
        "- begin with `examples/notebooks/user/` if you want a step-by-step packet-building tutorial with inline checkpoints",
        "- use `examples/notebooks/developer/` when you need the raw example internals",
        "",
        "## User Notebooks",
        "",
    ]
    for entry in user_entries:
        parts.append(f"- `user/{entry}`")
    for entry in computed_numpy_entries:
        parts.append(f"- `user/computed_numpy/{entry}`")
    for entry in computed_pandas_entries:
        parts.append(f"- `user/computed_pandas/{entry}`")
    parts.extend(
        [
            "",
            "## Runtime Note",
            "",
            "- the notebooks import the installed `wellplot` package from the active",
            "  environment",
            "- they still expect to run from a repository checkout so the example",
            "  files and sample data are available",
            "- for normal use, install the published package with the `notebook`",
            "  extra and any required data-source extras",
            "- contributors can still use `uv sync` from the repository root when",
            "  testing local changes",
            "",
            "## Regenerate",
            "",
            "```bash",
            "uv run python scripts/generate_example_notebooks.py",
            "```",
            "",
        ]
    )
    return "\n".join(parts)


def _developer_readme_text() -> str:
    """Return the generated developer README for examples/notebooks/developer."""
    sections = _developer_grouped_notebook_list()
    parts = [
        "# Developer Notebooks",
        "",
        "These generated notebooks mirror the repository example set and are meant",
        "for developers, advanced users, and contributors who want to inspect the",
        "raw example files, implementation details, and lower-level `wellplot` flows.",
        "",
        "They are intentionally unexecuted in git and act as reference material rather",
        "than polished end-user recipes.",
        "",
        "These files are generated by `scripts/generate_example_notebooks.py`.",
        "",
        "Runtime note:",
        "",
        "- the notebooks import the installed `wellplot` package from the active",
        "  environment",
        "- they still expect to run from a repository checkout so the example",
        "  files and sample data are available",
        "- for normal use, install the published package with the `notebook`",
        "  extra and any required data-source extras",
        "- contributors can still use `uv sync` from the repository root when",
        "  testing local changes",
        "",
    ]
    for heading, entries in sections.items():
        parts.append(f"## {heading}")
        parts.append("")
        for entry in entries:
            parts.append(f"- `{entry}`")
        if heading == "MCP walkthroughs":
            parts.extend(
                [
                    "",
                    "Runtime note for `mcp_natural_language_demo.ipynb`:",
                    "",
                    "- install `wellplot[agent,notebook,las]`",
                    "- run it from a repository checkout so the example data and YAML files resolve",
                    "- provide `OPENAI_API_KEY` through the environment or one of the local ignored",
                    "  files such as `.env.local` or `OPENAI_API_KEY.txt`",
                    "- treat it as a manual/opt-in integration notebook, not as a deterministic CI",
                    "  artifact",
                ]
            )
        parts.append("")
    parts.extend(
        [
            "## Regenerate",
            "",
            "```bash",
            "uv run python scripts/generate_example_notebooks.py",
            "```",
            "",
        ]
    )
    return "\n".join(parts)


def _user_readme_text() -> str:
    """Return the generated user README for examples/notebooks/user."""
    parts = [
        "# User Notebooks",
        "",
        "These notebooks are the curated starting point for geologists, petrophysicists,",
        "and other end users.",
        "",
        "They differ from the developer notebooks in three ways:",
        "",
        "- they teach how to build and adapt a production packet step by step instead of only reopening a shipped example",
        "- they explain the YAML workflow in domain language: inspect data, create the template, add sections, bind curves, and render",
        "- they include inline rendered checkpoints so the user can compare each stage with the expected visual result",
        "",
        "## Available Notebooks",
        "",
        "### YAML-First Production Recipes",
        "",
    ]
    for recipe in USER_PRODUCTION_RECIPES.values():
        parts.append(f"- `{_user_notebook_path(recipe.package_name).name}`")
        parts.append(f"  - {recipe.subtitle}")
    parts.extend(
        [
            "",
            "### Computed-Channel NumPy Recipes",
            "",
        ]
    )
    for recipe in USER_PRODUCTION_RECIPES.values():
        parts.append(
            f"- `computed_numpy/{_computed_notebook_path('numpy', recipe.package_name).name}`"
        )
        parts.append(
            "  - Compute derived channels with NumPy arrays, then generate layout YAML with wellplot builders."
        )
    parts.extend(
        [
            "",
            "### Computed-Channel pandas Recipes",
            "",
        ]
    )
    for recipe in USER_PRODUCTION_RECIPES.values():
        parts.append(
            f"- `computed_pandas/{_computed_notebook_path('pandas', recipe.package_name).name}`"
        )
        parts.append(
            "  - Compute derived channels with pandas tables, then generate layout YAML with wellplot builders."
        )
    parts.extend(
        [
            "",
            "## Runtime Note",
            "",
            "- install the published package with the `notebook` extra and any data-source",
            "  extras required by the example",
            "- run the notebooks from a checkout of this repository so the example files,",
            "  sample data, and preview assets are available",
            "",
            "## Regenerate",
            "",
            "```bash",
            "uv run python scripts/generate_example_notebooks.py",
            "```",
            "",
        ]
    )
    return "\n".join(parts)


def _computed_series_readme_text(series: str) -> str:
    """Return the generated README for one computed-channel notebook series."""
    method_label = _computed_series_label(series)
    parts = [
        f"# Computed-Channel {method_label} Notebooks",
        "",
        "These notebooks start from the same two production examples as the YAML-first user recipes,",
        f"but compute new interpretation channels with {method_label} before building the layout.",
        "",
        "The workflow is:",
        "",
        "- load the public example data",
        "- compute derived channels in Python",
        "- attach those channels to a `WellDataset`",
        "- use `LogBuilder` and `SectionBuilder` to create the YAML-style layout",
        "- save the generated YAML with `save_report(...)`",
        "- render from the in-memory report so computed channels are available",
        "",
        "Important: the saved YAML is a layout artifact. It does not persist the computed channel arrays by itself.",
        "",
        "## Available Notebooks",
        "",
    ]
    for recipe in USER_PRODUCTION_RECIPES.values():
        parts.append(f"- `{_computed_notebook_path(series, recipe.package_name).name}`")
    parts.extend(
        [
            "",
            "## Regenerate",
            "",
            "```bash",
            "uv run python scripts/generate_example_notebooks.py",
            "```",
            "",
        ]
    )
    return "\n".join(parts)


def _cleanup_stale_notebook_files(expected_files: set[Path], *, check: bool) -> int:
    """Remove stale generated files from the notebook tree."""
    existing_files = {path for path in NOTEBOOKS_ROOT.rglob("*") if path.is_file()}
    stale_files = sorted(existing_files - expected_files)
    if check and stale_files:
        raise SystemExit(f"Stale generated notebook file found: {stale_files[0]}")

    changes = 0
    for stale_path in stale_files:
        stale_path.unlink()
        changes += 1

    directories = sorted(
        [path for path in NOTEBOOKS_ROOT.rglob("*") if path.is_dir()],
        reverse=True,
    )
    for directory in directories:
        if directory == NOTEBOOKS_ROOT:
            continue
        if any(directory.iterdir()):
            continue
        directory.rmdir()
    return changes


def generate(*, check: bool = False) -> int:
    """Generate or check the user and developer notebook sets."""
    NOTEBOOKS_ROOT.mkdir(parents=True, exist_ok=True)
    DEVELOPER_NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    USER_NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    USER_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    USER_COMPUTED_NUMPY_DIR.mkdir(parents=True, exist_ok=True)
    USER_COMPUTED_PANDAS_DIR.mkdir(parents=True, exist_ok=True)
    changes = 0
    expected_files: set[Path] = set()

    for package_dir in _production_packages():
        title = _production_title(package_dir)
        notebook = _production_notebook(
            package_dir.name,
            title,
            _production_prerequisites(package_dir),
        )
        output_path = _production_notebook_path(package_dir.name)
        expected_files.add(output_path)
        if _write_notebook(output_path, notebook, check=check):
            changes += 1

    for recipe in PYTHON_RECIPES.values():
        notebook = _python_notebook(recipe)
        output_path = _relative_notebook_path(recipe.source)
        expected_files.add(output_path)
        if _write_notebook(output_path, notebook, check=check):
            changes += 1

    for path in _yaml_example_paths():
        if path.name == "triple_combo.yaml":
            notebook = _legacy_triple_combo_notebook()
        else:
            notebook = _yaml_notebook(path, _load_yaml(path))
        output_path = _relative_notebook_path(path.name)
        expected_files.add(output_path)
        if _write_notebook(output_path, notebook, check=check):
            changes += 1

    for recipe in USER_PRODUCTION_RECIPES.values():
        notebook, asset_changes = _user_production_notebook(recipe, check=check)
        output_path = _user_notebook_path(recipe.package_name)
        expected_files.add(output_path)
        tutorial = _user_tutorial_for_recipe(recipe)
        for stage in tutorial.stages:
            for preview in stage.previews:
                expected_files.add(USER_ASSETS_DIR / preview.asset_name)
        changes += asset_changes
        if _write_notebook(output_path, notebook, check=check):
            changes += 1

    for series in ("numpy", "pandas"):
        for recipe in USER_PRODUCTION_RECIPES.values():
            notebook = _computed_notebook(recipe.package_name, series)
            output_path = _computed_notebook_path(series, recipe.package_name)
            expected_files.add(output_path)
            if _write_notebook(output_path, notebook, check=check):
                changes += 1

    readmes = {
        NOTEBOOKS_ROOT / "README.md": _root_readme_text(),
        DEVELOPER_NOTEBOOKS_DIR / "README.md": _developer_readme_text(),
        USER_NOTEBOOKS_DIR / "README.md": _user_readme_text(),
        USER_COMPUTED_NUMPY_DIR / "README.md": _computed_series_readme_text("numpy"),
        USER_COMPUTED_PANDAS_DIR / "README.md": _computed_series_readme_text("pandas"),
    }
    for readme_path, readme_text in readmes.items():
        expected_files.add(readme_path)
        if check:
            current = readme_path.read_text() if readme_path.exists() else None
            if current != readme_text:
                raise SystemExit(f"Notebook README is out of date: {readme_path}")
        elif _write_if_changed(readme_path, readme_text):
            changes += 1

    changes += _cleanup_stale_notebook_files(expected_files, check=check)
    return changes


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for notebook generation."""
    parser = argparse.ArgumentParser(
        description="Generate walkthrough notebooks for repository examples."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail instead of writing files when generated content is out of date.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the notebook generation command."""
    args = parse_args()
    changes = generate(check=args.check)
    if args.check:
        print("Example notebooks are up to date.")
        return
    print(f"Updated {changes} notebook-related files.")


if __name__ == "__main__":
    main()
