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
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples"
NOTEBOOKS_DIR = EXAMPLES_DIR / "notebooks"

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
        prerequisites=("uv sync --extra pandas",),
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
        prerequisites=("uv sync --extra pandas",),
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
        prerequisites=("uv sync --extra las",),
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


def markdown_cell(text: str) -> dict[str, object]:
    """Return a notebook markdown cell."""
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": _as_lines(text),
    }


def code_cell(text: str) -> dict[str, object]:
    """Return a notebook code cell."""
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": _as_lines(text),
    }


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


def _repo_setup_code() -> str:
    """Return the common repository path setup code used in notebooks."""
    return dedent(
        """
        import sys
        from pathlib import Path

        # Walk upward from the current working directory until we find the
        # repository root. This keeps the notebook runnable whether Jupyter was
        # launched from the repo root or from examples/notebooks.
        cwd = Path.cwd().resolve()
        REPO_ROOT = next(
            path for path in (cwd, *cwd.parents)
            if (path / "examples").exists() and (path / "src").exists()
        )

        EXAMPLES_DIR = REPO_ROOT / "examples"
        SRC_DIR = REPO_ROOT / "src"
        WORKSPACE_DIR = REPO_ROOT / "workspace"
        WORKSPACE_RENDERS = WORKSPACE_DIR / "renders"
        WORKSPACE_RENDERS.mkdir(parents=True, exist_ok=True)

        for candidate in (SRC_DIR, EXAMPLES_DIR):
            candidate_text = str(candidate)
            if candidate_text not in sys.path:
                sys.path.insert(0, candidate_text)
        """
    ).strip()


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
    """Infer prerequisite installation steps from YAML source metadata."""
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
                extras.add("uv sync --extra dlis")
            if source_format == "las" or source_path.endswith(".las"):
                extras.add("uv sync --extra las")
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
        common.append(
            "Compare scale conventions before you standardize one for your own packet."
        )
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


def _production_intro_markdown(package_name: str, title: str, prerequisites: tuple[str, ...]) -> str:
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
            "Release follow-up:",
            "",
            "- these notebooks currently bootstrap the local repository paths so they run",
            "  directly from a source checkout",
            "- after the published package workflow is in place, update them to prefer",
            "  installed-package imports and published-example usage first",
        ]
    )


def _python_intro_markdown(recipe: PythonRecipe) -> str:
    """Return the intro markdown for one Python example notebook."""
    goals = "\n".join(f"- {goal}" for goal in recipe.learning_goals)
    prereq_block = _prerequisites_markdown(recipe.prerequisites)
    return _join_markdown_lines(
        [
            f"# {recipe.title}",
            "",
            "This generated notebook is the recipe companion for",
            f"`examples/{recipe.source}`.",
            "",
            recipe.summary,
            "",
            "What you will practice in this walkthrough:",
            "",
            goals,
            "",
            prereq_block,
            "",
            "Release follow-up:",
            "",
            "- this notebook currently adds the local `src/` and `examples/` paths so it",
            "  can run from a source checkout",
            "- after publishing, switch the recipe toward installed-package-first imports",
            "  and validate it against the published distribution",
        ]
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
            "Release follow-up:",
            "",
            "- this notebook currently validates and renders the YAML from the repository",
            "  checkout",
            "- after publishing, add an installed-package-first version of the recipe and",
            "  confirm the same example still works against the published distribution",
        ]
    )


def _prerequisites_markdown(steps: tuple[str, ...]) -> str:
    """Return a prerequisite markdown block."""
    if not steps:
        return _join_markdown_lines(
            [
                "Prerequisites:",
                "",
                "- the repository dependencies installed in the active environment",
            ]
        )
    joined = "\n".join(f"- `{step}`" for step in steps)
    return _join_markdown_lines(["Prerequisites:", "", joined])


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

        - the repository dependencies installed in the active environment

        Release follow-up:

        - this notebook currently relies on the source checkout and local path
          bootstrapping
        - after publishing, keep a published-package version of the recipe for
          users who are not working inside the repository
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
        code_cell(_source_display_code(recipe.source, "python")),
    ]
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


def _production_notebook(package_name: str, title: str, prerequisites: tuple[str, ...]) -> dict[str, object]:
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


def _notebook(cells: list[dict[str, object]]) -> dict[str, object]:
    """Return a complete notebook payload."""
    normalized_cells: list[dict[str, object]] = []
    for index, cell in enumerate(cells):
        source = cell.get("source", [])
        seed = source[0].strip() if isinstance(source, list) and source else f"cell-{index}"
        cell_id = hashlib.md5(
            f"{index}:{cell.get('cell_type', '')}:{seed}".encode()
        ).hexdigest()[:8]
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
    return NOTEBOOKS_DIR / notebook_name


def _production_notebook_path(package_name: str) -> Path:
    """Return the notebook path for one production package."""
    return NOTEBOOKS_DIR / f"{package_name}.ipynb"


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
    if check:
        current = path.read_text() if path.exists() else None
        if current != rendered:
            raise SystemExit(f"Notebook is out of date: {path}")
        return False
    return _write_if_changed(path, rendered)


def _grouped_notebook_list() -> dict[str, list[str]]:
    """Return grouped notebook names for the generated README."""
    grouped = {
        "Production package walkthroughs": [],
        "Programmatic API walkthroughs": [],
        "YAML and legacy walkthroughs": [],
    }
    for package_dir in _production_packages():
        grouped["Production package walkthroughs"].append(
            _production_notebook_path(package_dir.name).name
        )
    for recipe in PYTHON_RECIPES.values():
        grouped["Programmatic API walkthroughs"].append(_relative_notebook_path(recipe.source).name)
    for path in _yaml_example_paths():
        if path.name == "triple_combo.yaml" or path.suffix == ".yaml" or path.name.endswith(
            ".log.yaml"
        ):
            grouped["YAML and legacy walkthroughs"].append(_relative_notebook_path(path.name).name)
    return grouped


def _readme_text() -> str:
    """Return the generated README text for examples/notebooks."""
    sections = _grouped_notebook_list()
    parts = [
        "# Example Notebooks",
        "",
        "This directory contains generated walkthrough notebooks that mirror the repository",
        "example set. Each notebook is intended to act as a recipe for final users:",
        "",
        "- read the source example inside the notebook",
        "- understand the main moving parts",
        "- run the validation and render steps from an interactive session",
        "",
        "These files are generated by `scripts/generate_example_notebooks.py`.",
        "",
        "Current note:",
        "",
        "- the notebooks still bootstrap the local repository paths so they run from a",
        "  source checkout",
        "- after publishing, update them to prefer installed-package-first recipes and",
        "  verify them against the published distribution",
        "",
    ]
    for heading, entries in sections.items():
        parts.append(f"## {heading}")
        parts.append("")
        for entry in entries:
            parts.append(f"- `{entry}`")
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


def generate(*, check: bool = False) -> int:
    """Generate or check the walkthrough notebook set."""
    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    changes = 0

    for package_dir in _production_packages():
        title = _production_title(package_dir)
        notebook = _production_notebook(
            package_dir.name,
            title,
            _production_prerequisites(package_dir),
        )
        if _write_notebook(_production_notebook_path(package_dir.name), notebook, check=check):
            changes += 1

    for recipe in PYTHON_RECIPES.values():
        notebook = _python_notebook(recipe)
        if _write_notebook(_relative_notebook_path(recipe.source), notebook, check=check):
            changes += 1

    for path in _yaml_example_paths():
        if path.name == "triple_combo.yaml":
            notebook = _legacy_triple_combo_notebook()
        else:
            notebook = _yaml_notebook(path, _load_yaml(path))
        if _write_notebook(_relative_notebook_path(path.name), notebook, check=check):
            changes += 1

    readme_path = NOTEBOOKS_DIR / "README.md"
    readme_text = _readme_text()
    if check:
        current = readme_path.read_text() if readme_path.exists() else None
        if current != readme_text:
            raise SystemExit(f"Notebook README is out of date: {readme_path}")
    elif _write_if_changed(readme_path, readme_text):
        changes += 1

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
