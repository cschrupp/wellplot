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

"""Notebook-facing helpers for the public wellplot agent API."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

import yaml

from .core import AuthoringResult, AuthoringSession


@dataclass(frozen=True)
class ProjectPaths:
    """Canonical filesystem paths for one user-managed authoring project."""

    server_root: Path
    project_dir: Path

    @classmethod
    def under_root(
        cls,
        server_root: str | Path,
        project_dir: str | Path,
    ) -> ProjectPaths:
        """Resolve one project directory under the configured MCP server root."""
        resolved_root = Path(server_root).resolve()
        raw_project_dir = Path(project_dir)
        resolved_project_dir = (
            raw_project_dir if raw_project_dir.is_absolute() else (resolved_root / raw_project_dir)
        ).resolve()
        try:
            resolved_project_dir.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError("project_dir must resolve inside the configured server_root.") from exc
        return cls(server_root=resolved_root, project_dir=resolved_project_dir)

    def path(self, *parts: str | Path) -> Path:
        """Return one absolute project path under the configured project directory."""
        target = self.project_dir
        for part in parts:
            raw_part = Path(part)
            if raw_part.is_absolute():
                raise ValueError("project path parts must be relative, not absolute.")
            target = target / raw_part
        resolved_target = target.resolve()
        try:
            resolved_target.relative_to(self.project_dir)
        except ValueError as exc:
            raise ValueError(
                "project path parts must resolve inside the project directory."
            ) from exc
        return resolved_target


@dataclass(frozen=True)
class ProjectStarter:
    """Generated starter files for one project-scoped authoring workflow."""

    kind: str
    template_path: Path
    logfile_path: Path
    render_output_path: Path
    data_file: Path
    template_yaml: str
    logfile_yaml: str

    def display_yaml(self, *, return_objects: bool = False) -> tuple[object, object] | None:
        """Display the generated template and logfile YAML in notebook-friendly form."""
        try:
            from IPython.display import Code, display
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Install `wellplot[notebook]` or add IPython to use notebook display helpers."
            ) from exc

        template_code = Code(self.template_yaml, language="yaml")
        logfile_code = Code(self.logfile_yaml, language="yaml")
        display(template_code)
        display(logfile_code)
        if return_objects:
            return template_code, logfile_code
        return None


@dataclass
class ProjectSession:
    """Notebook-facing project wrapper around one public authoring session."""

    authoring_session: AuthoringSession
    paths: ProjectPaths
    run_max_rounds: int = 12
    revise_max_rounds: int = 12
    draft_logfile: str | Path | None = None
    render_output_path: str | Path | None = None

    def __getattr__(self, name: str) -> object:
        """Delegate core authoring methods and properties to the wrapped session."""
        return getattr(self.authoring_session, name)

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize one notebook-authored multi-line prompt string."""
        return dedent(text).strip()

    def _resolve_server_file(
        self,
        path: str | Path,
        *,
        field_name: str,
    ) -> Path:
        """Resolve one file path and require it to live under the configured server root."""
        raw_path = Path(path).expanduser()
        absolute_path = (
            raw_path if raw_path.is_absolute() else (self.paths.server_root / raw_path)
        ).resolve()
        try:
            absolute_path.relative_to(self.paths.server_root)
        except ValueError as exc:
            raise ValueError(
                f"{field_name} must resolve inside the configured server_root. "
                f"Stage it under the project directory first if needed."
            ) from exc
        return absolute_path

    def _resolve_project_file(
        self,
        path: str | Path,
        *,
        field_name: str,
    ) -> Path:
        """Resolve one file path and require it to live under the project directory."""
        raw_path = Path(path).expanduser()
        if raw_path.is_absolute():
            absolute_path = raw_path.resolve()
        else:
            project_relative_root = self.paths.project_dir.relative_to(self.paths.server_root)
            try:
                raw_path.relative_to(project_relative_root)
            except ValueError:
                absolute_path = (self.paths.project_dir / raw_path).resolve()
            else:
                absolute_path = (self.paths.server_root / raw_path).resolve()
        try:
            absolute_path.relative_to(self.paths.project_dir)
        except ValueError as exc:
            raise ValueError(
                f"{field_name} must resolve inside the configured project_dir."
            ) from exc
        return absolute_path

    @staticmethod
    def _yaml_text(mapping: dict[str, object]) -> str:
        """Render one mapping to stable YAML text for starter file generation."""
        return yaml.safe_dump(mapping, sort_keys=False).strip() + "\n"

    @staticmethod
    def _infer_source_format(data_file: Path) -> str:
        """Infer one supported source format from the file extension."""
        suffix = data_file.suffix.lower()
        if suffix == ".las":
            return "las"
        if suffix == ".dlis":
            return "dlis"
        raise ValueError(
            "Unable to infer source_format from data_file. "
            "Supported extensions: .las, .dlis"
        )

    @staticmethod
    def _open_hole_quicklook_template_mapping() -> dict[str, object]:
        """Return the shipped starter template preset for one open-hole quicklook packet."""
        return {
            "render": {
                "backend": "matplotlib",
                "dpi": 144,
                "continuous_strip_page_height_mm": 297,
                "matplotlib": {
                    "style": {
                        "report": {
                            "summary_label_fontsize": 8.0,
                            "summary_value_fontsize": 10.5,
                            "provider_fontsize": 16.0,
                            "service_fontsize": 8.0,
                            "tail_service_fontsize": 8.0,
                            "field_label_fontsize": 7.0,
                            "field_value_fontsize": 7.8,
                            "detail_header_fontsize": 9.0,
                            "detail_label_fontsize": 6.4,
                            "detail_value_fontsize": 6.4,
                            "tail_frame_y": 0.74,
                            "tail_frame_height": 0.22,
                        },
                        "section_title": {
                            "background_color": "#0d3fb3",
                            "border_mode": "box",
                            "border_color": "#0d3fb3",
                            "border_linewidth": 0.8,
                            "padding_left": 0.03,
                            "padding_right": 0.03,
                            "title_align": "center",
                            "subtitle_align": "center",
                            "title_fontsize": 11.0,
                            "subtitle_fontsize": 6.6,
                            "title_color": "#ffffff",
                            "subtitle_color": "#eaf0ff",
                            "title_y": 0.68,
                            "subtitle_y": 0.22,
                        },
                        "track_header": {
                            "background_color": "#eef2f8",
                        },
                        "track": {
                            "x_tick_labelsize": 6.0,
                        },
                        "grid": {
                            "depth_major_linewidth": 0.65,
                        },
                    }
                },
            },
            "document": {
                "page": {
                    "size": "A4",
                    "orientation": "portrait",
                    "continuous": False,
                    "bottom_track_header_enabled": True,
                    "margin_left_mm": 0,
                    "margin_right_mm": 8,
                    "margin_top_mm": 0,
                    "margin_bottom_mm": 0,
                    "track_gap_mm": 0,
                    "header_height_mm": 0,
                    "track_header_height_mm": 30,
                    "footer_height_mm": 0,
                },
                "depth": {
                    "unit": "ft",
                    "scale": 240,
                    "major_step": 10,
                    "minor_step": 2,
                },
                "layout": {
                    "heading": {
                        "enabled": True,
                        "provider_name": "Company",
                        "general_fields": [
                            {"key": "company", "label": "Company", "source_key": "COMP"},
                            {"key": "well", "label": "Well", "source_key": "WELL"},
                            {"key": "field", "label": "Field", "source_key": "FLD"},
                            {
                                "key": "service_company",
                                "label": "Service Company",
                                "source_key": "SRVC",
                            },
                        ],
                        "service_titles": [
                            {
                                "value": "Open Hole Quicklook",
                                "alignment": "center",
                                "bold": True,
                            }
                        ],
                        "detail": {
                            "kind": "open_hole",
                            "title": "Open Hole Metadata",
                            "rows": [
                                {
                                    "label": "Date",
                                    "values": [
                                        {"source_key": "DATE"},
                                        "",
                                    ],
                                },
                                {
                                    "label_cells": ["UWI", "Province"],
                                    "columns": [
                                        {"cells": [{"source_key": "UWI"}]},
                                        {"cells": [{"source_key": "PROV"}]},
                                    ],
                                },
                            ],
                        },
                    },
                    "remarks": [
                        {
                            "title": "Public Data and IP Notice",
                            "lines": [
                                (
                                    "This example uses publicly available or "
                                    "repository-provided demonstration data intended "
                                    "for educational use."
                                ),
                                (
                                    "Rendered layouts are independent reproductions "
                                    "generated by wellplot, not vendor-authored "
                                    "originals or official service-company deliverables."
                                ),
                                (
                                    "Original trademarks and service names remain the "
                                    "property of their respective owners."
                                ),
                                (
                                    "Confirm data provenance and redistribution rights "
                                    "before reusing outputs outside this repository."
                                ),
                            ],
                            "alignment": "left",
                        }
                    ],
                    "log_sections": [],
                    "tail": {"enabled": True},
                },
                "bindings": {
                    "on_missing": "skip",
                    "channels": [],
                },
            },
        }

    @staticmethod
    def _starter_tracks(
        seed_tracks: tuple[str, ...],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        """Return starter tracks and bindings for one supported preset selection."""
        supported_tracks: dict[str, dict[str, object]] = {
            "gr_sp": {
                "id": "gr_sp",
                "title": "GR/SP",
                "kind": "normal",
                "width_mm": 32,
                "position": 1,
            },
            "depth": {
                "id": "depth",
                "title": "Depth",
                "kind": "reference",
                "width_mm": 18,
                "position": 2,
                "reference": {
                    "axis": "depth",
                    "define_layout": True,
                    "unit": "ft",
                    "scale_ratio": 240,
                    "major_step": 100,
                    "secondary_grid": {
                        "display": True,
                        "line_count": 4,
                    },
                },
            },
        }
        unknown_tracks = [name for name in seed_tracks if name not in supported_tracks]
        if unknown_tracks:
            raise ValueError(
                f"Unsupported seed_tracks for the shipped starter preset: {unknown_tracks}"
            )
        tracks = [supported_tracks[name] for name in seed_tracks]
        bindings: list[dict[str, object]] = []
        if "gr_sp" in seed_tracks:
            bindings.append(
                {
                    "channel": "GR",
                    "track_id": "gr_sp",
                    "kind": "curve",
                    "label": "GR",
                    "style": {"color": "#2e7d32"},
                }
            )
        return tracks, bindings

    def configure_rounds(
        self,
        *,
        run_max_rounds: int | None = None,
        revise_max_rounds: int | None = None,
    ) -> ProjectSession:
        """Update the default round budgets for later run/revise calls."""
        if run_max_rounds is not None:
            self.run_max_rounds = run_max_rounds
        if revise_max_rounds is not None:
            self.revise_max_rounds = revise_max_rounds
        return self

    def configure_paths(
        self,
        *,
        draft_logfile: str | Path | None = None,
        render_output_path: str | Path | None = None,
    ) -> ProjectSession:
        """Update the default draft/render paths for later notebook calls."""
        if draft_logfile is not None:
            self.draft_logfile = draft_logfile
        if render_output_path is not None:
            self.render_output_path = render_output_path
        return self

    def _require_default_path(
        self,
        path: str | Path | None,
        *,
        field_name: str,
    ) -> str | Path:
        """Return one configured default path or raise a clear notebook-facing error."""
        if path is None:
            raise ValueError(
                f"No default {field_name} is configured on this session. "
                f"Call session.configure_paths({field_name}=...) or pass {field_name}=..."
            )
        return path

    async def run(
        self,
        *,
        goal: str,
        output_logfile: str | Path | None = None,
        example_id: str | None = None,
        source_logfile_path: str | Path | None = None,
        max_rounds: int | None = None,
    ) -> AuthoringResult:
        """Run one project-scoped authoring request with normalized prompt text."""
        resolved_output = self._require_default_path(
            self.draft_logfile if output_logfile is None else output_logfile,
            field_name="draft_logfile",
        )
        return await self.authoring_session.run(
            goal=self._normalize_text(goal),
            output_logfile=resolved_output,
            example_id=example_id,
            source_logfile_path=source_logfile_path,
            max_rounds=self.run_max_rounds if max_rounds is None else max_rounds,
        )

    async def revise(
        self,
        *,
        feedback: str,
        logfile_path: str | Path | None = None,
        max_rounds: int | None = None,
    ) -> AuthoringResult:
        """Revise one draft with normalized feedback and default round budgets."""
        resolved_logfile = self._require_default_path(
            self.draft_logfile if logfile_path is None else logfile_path,
            field_name="draft_logfile",
        )
        return await self.authoring_session.revise(
            feedback=self._normalize_text(feedback),
            logfile_path=resolved_logfile,
            max_rounds=self.revise_max_rounds if max_rounds is None else max_rounds,
        )

    async def render_logfile_to_file(
        self,
        *,
        logfile_path: str | Path | None = None,
        output_path: str | Path | None = None,
        overwrite: bool = False,
    ) -> dict[str, object]:
        """Render one draft with optional default logfile and output-path settings."""
        resolved_logfile = self._require_default_path(
            self.draft_logfile if logfile_path is None else logfile_path,
            field_name="draft_logfile",
        )
        resolved_output = self._require_default_path(
            self.render_output_path if output_path is None else output_path,
            field_name="render_output_path",
        )
        return await self.authoring_session.render_logfile_to_file(
            logfile_path=resolved_logfile,
            output_path=resolved_output,
            overwrite=overwrite,
        )

    def add_data_file(
        self,
        source_path: str | Path,
        *,
        destination_name: str | Path | None = None,
        overwrite: bool = False,
        keep_existing: bool = False,
    ) -> Path:
        """Copy one file into the project directory and return the staged path."""
        raw_source = Path(source_path).expanduser()
        absolute_source = (
            raw_source if raw_source.is_absolute() else (self.paths.server_root / raw_source)
        ).resolve()
        if not absolute_source.exists():
            raise FileNotFoundError(f"Data file does not exist: {absolute_source}")
        if not absolute_source.is_file():
            raise ValueError(f"Data file must be a file path: {absolute_source}")

        if destination_name is None:
            destination_path = self.paths.path(absolute_source.name)
        else:
            raw_destination = Path(destination_name)
            if raw_destination.is_absolute():
                raise ValueError(
                    "destination_name must be one relative file name, not an absolute path."
                )
            destination_path = self.paths.path(raw_destination)

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_destination = destination_path.resolve()
        if resolved_destination == absolute_source:
            return resolved_destination
        if resolved_destination.exists() and keep_existing and not overwrite:
            return resolved_destination
        if resolved_destination.exists() and not overwrite:
            raise FileExistsError(
                f"Project data file already exists: {resolved_destination}. "
                "Pass overwrite=True to replace it."
            )
        shutil.copyfile(absolute_source, resolved_destination)
        return resolved_destination

    def create_starter(
        self,
        *,
        kind: str,
        data_file: str | Path,
        title: str,
        subtitle: str,
        depth_range: tuple[float, float] | None = None,
        template_path: str | Path = "base.template.yaml",
        starter_logfile: str | Path = "starter.log.yaml",
        render_output_path: str | Path | None = None,
        source_format: str | None = None,
        section_id: str = "main",
        starter_name: str = "Project Starter",
        seed_tracks: tuple[str, ...] = ("gr_sp", "depth"),
        overwrite: bool = True,
    ) -> ProjectStarter:
        """Create one starter template/logfile pair from one shipped preset."""
        if kind != "open_hole_quicklook":
            raise ValueError("Supported starter kinds: 'open_hole_quicklook'.")

        resolved_data_file = self._resolve_server_file(data_file, field_name="data_file")
        if not resolved_data_file.exists():
            raise FileNotFoundError(f"Starter data file does not exist: {resolved_data_file}")

        resolved_template_path = self._resolve_project_file(
            template_path,
            field_name="template_path",
        )
        resolved_logfile_path = self._resolve_project_file(
            starter_logfile,
            field_name="starter_logfile",
        )
        render_output_target = (
            "report.pdf"
            if render_output_path is None and self.render_output_path is None
            else (self.render_output_path if render_output_path is None else render_output_path)
        )
        resolved_render_output_path = self._resolve_project_file(
            render_output_target,
            field_name="render_output_path",
        )
        if resolved_template_path.exists() and not overwrite:
            raise FileExistsError(
                f"Starter template already exists: {resolved_template_path}. "
                "Pass overwrite=True to replace it."
            )
        if resolved_logfile_path.exists() and not overwrite:
            raise FileExistsError(
                f"Starter logfile already exists: {resolved_logfile_path}. "
                "Pass overwrite=True to replace it."
            )

        relative_source_path = Path(
            os.path.relpath(resolved_data_file, start=self.paths.project_dir)
        ).as_posix()
        relative_template_path = Path(
            os.path.relpath(resolved_template_path, start=resolved_logfile_path.parent)
        ).as_posix()
        relative_render_output = Path(
            os.path.relpath(resolved_render_output_path, start=resolved_logfile_path.parent)
        ).as_posix()
        resolved_source_format = (
            self._infer_source_format(resolved_data_file)
            if source_format is None
            else str(source_format).strip().lower()
        )

        tracks, bindings = self._starter_tracks(seed_tracks)
        section_mapping: dict[str, object] = {
            "id": section_id,
            "title": title,
            "subtitle": subtitle,
            "data": {
                "source_path": relative_source_path,
                "source_format": resolved_source_format,
            },
            "tracks": tracks,
        }
        if depth_range is not None:
            section_mapping["depth_range"] = [depth_range[0], depth_range[1]]

        template_mapping = self._open_hole_quicklook_template_mapping()
        starter_mapping = {
            "template": {"path": relative_template_path},
            "version": 1,
            "name": starter_name,
            "render": {"output_path": relative_render_output},
            "document": {
                "layout": {
                    "log_sections": [section_mapping],
                },
                "bindings": {
                    "on_missing": "skip",
                    "channels": bindings,
                },
            },
        }

        template_yaml = self._yaml_text(template_mapping)
        logfile_yaml = self._yaml_text(starter_mapping)
        resolved_template_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_logfile_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_template_path.write_text(template_yaml, encoding="utf-8")
        resolved_logfile_path.write_text(logfile_yaml, encoding="utf-8")
        return ProjectStarter(
            kind=kind,
            template_path=resolved_template_path,
            logfile_path=resolved_logfile_path,
            render_output_path=resolved_render_output_path,
            data_file=resolved_data_file,
            template_yaml=template_yaml,
            logfile_yaml=logfile_yaml,
        )


def create_project_session(
    *,
    server_root: str | Path,
    project_dir: str | Path,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    run_max_rounds: int = 12,
    revise_max_rounds: int = 12,
) -> tuple[ProjectSession, ProjectPaths]:
    """Create one notebook-ready authoring session scoped to a project directory."""
    project_paths = ProjectPaths.under_root(server_root=server_root, project_dir=project_dir)
    project_paths.project_dir.mkdir(parents=True, exist_ok=True)
    resolved_model = model or os.getenv("OPENAI_MODEL", "gpt-5.4")
    authoring_session = AuthoringSession.from_local_mcp(
        provider=provider,
        model=resolved_model,
        server_root=project_paths.server_root,
        api_key=api_key,
        base_url=base_url,
    )
    return (
        ProjectSession(
            authoring_session=authoring_session,
            paths=project_paths,
            run_max_rounds=run_max_rounds,
            revise_max_rounds=revise_max_rounds,
        ),
        project_paths,
    )


def relative_path(path: str | Path, *, root: str | Path) -> str:
    """Return one path rendered relative to a configured root when possible."""
    resolved_root = Path(root).resolve()
    raw_path = Path(path)
    absolute_path = raw_path if raw_path.is_absolute() else (resolved_root / raw_path)
    resolved_path = absolute_path.resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return str(resolved_path)


def display_authoring_result(
    title: str,
    result: AuthoringResult,
    *,
    preview: str = "section",
    return_image: bool = False,
) -> object | None:
    """Print one compact authoring summary and display one preview image."""
    try:
        from IPython.display import Image, display
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Install `wellplot[notebook]` or add IPython to use notebook display helpers."
        ) from exc

    print(title)
    print("Draft:", result.draft_logfile)
    print("Tool trace:", [item.name for item in result.tool_trace])
    for line in result.summary_lines:
        print(" -", line)
    image = Image(data=result.preview_bytes(preview))
    display(image)
    if return_image:
        return image
    return None
