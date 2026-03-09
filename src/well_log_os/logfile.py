from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .errors import TemplateValidationError
from .io import load_dlis, load_las
from .logfile_schema import validate_logfile_mapping
from .model import LogDocument, ScalarChannel, WellDataset
from .templates import document_from_mapping


@dataclass(slots=True, frozen=True)
class LogFileSpec:
    name: str
    data_source_path: str
    data_source_format: str
    render_backend: str
    render_output_path: str
    render_dpi: int
    document: dict[str, Any]
    auto_tracks: dict[str, Any]


def _ensure_mapping(value: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TemplateValidationError(
            f"Expected a mapping for {context}, got {type(value).__name__}."
        )
    return value


def _ensure_sequence(value: Any, *, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise TemplateValidationError(
            f"Expected a sequence for {context}, got {type(value).__name__}."
        )
    return value


def logfile_from_mapping(data: dict[str, Any]) -> LogFileSpec:
    validate_logfile_mapping(data)
    root = _ensure_mapping(data, context="logfile")
    try:
        _ = int(root["version"])
        name = str(root["name"])

        data_section = _ensure_mapping(root["data"], context="data")
        data_source_path = str(data_section["source_path"])
        data_source_format = str(data_section.get("source_format", "auto")).strip().lower()

        render_section = _ensure_mapping(root["render"], context="render")
        render_backend = str(render_section.get("backend", "matplotlib")).strip().lower()
        render_output_path = str(render_section["output_path"])
        render_dpi = int(render_section["dpi"])
        if render_dpi <= 0:
            raise TemplateValidationError("render.dpi must be positive.")

        document = deepcopy(_ensure_mapping(root["document"], context="document"))
        auto_tracks = deepcopy(_ensure_mapping(root["auto_tracks"], context="auto_tracks"))
        _validate_auto_tracks(auto_tracks)
    except (KeyError, TypeError, ValueError) as exc:
        raise TemplateValidationError("Invalid logfile configuration.") from exc

    return LogFileSpec(
        name=name,
        data_source_path=data_source_path,
        data_source_format=data_source_format,
        render_backend=render_backend,
        render_output_path=render_output_path,
        render_dpi=render_dpi,
        document=document,
        auto_tracks=auto_tracks,
    )


def load_logfile(path: str | Path) -> LogFileSpec:
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise TemplateValidationError("Log file root must be a mapping.")
    return logfile_from_mapping(payload)


def _validate_auto_tracks(auto_tracks: dict[str, Any]) -> None:
    depth_track = _ensure_mapping(auto_tracks["depth_track"], context="auto_tracks.depth_track")
    _ = str(depth_track["id"])
    _ = str(depth_track["title"])
    _ = float(depth_track["width_mm"])

    on_missing = str(auto_tracks.get("on_missing", "skip")).strip().lower()
    if on_missing not in {"skip", "error"}:
        raise TemplateValidationError("auto_tracks.on_missing must be either 'skip' or 'error'.")

    max_tracks = int(auto_tracks.get("max_tracks", 9999))
    if max_tracks <= 0:
        raise TemplateValidationError("auto_tracks.max_tracks must be positive.")

    track_items = _ensure_sequence(auto_tracks["tracks"], context="auto_tracks.tracks")
    if not track_items:
        raise TemplateValidationError("auto_tracks.tracks cannot be empty.")

    for index, item in enumerate(track_items):
        track_item = _ensure_mapping(item, context=f"auto_tracks.tracks[{index}]")
        _ = str(track_item["channel"])
        configure = _ensure_mapping(
            track_item["configure"], context=f"auto_tracks.tracks[{index}].configure"
        )
        _ = float(configure["width_mm"])
        _ = str(configure.get("title_template", "{mnemonic} [{unit}]"))
        style = _ensure_mapping(
            configure["style"], context=f"auto_tracks.tracks[{index}].configure.style"
        )
        if "color" not in style:
            raise TemplateValidationError(
                f"auto_tracks.tracks[{index}].configure.style.color is required."
            )
        _ = str(style["color"])
        if "scale" in configure:
            scale = _ensure_mapping(
                configure["scale"],
                context=f"auto_tracks.tracks[{index}].configure.scale",
            )
            if "min" in scale or "max" in scale:
                if "min" not in scale or "max" not in scale:
                    raise TemplateValidationError(
                        f"auto_tracks.tracks[{index}].configure.scale must define both min and max."
                    )
                _ = float(scale["min"])
                _ = float(scale["max"])
            if "kind" in scale:
                kind = str(scale["kind"]).strip().lower()
                if kind not in {"auto", "linear", "log"}:
                    raise TemplateValidationError(
                        "auto_tracks.tracks["
                        f"{index}"
                        "].configure.scale.kind must be auto, linear, or log."
                    )
            if "percentile_low" in scale:
                _ = float(scale["percentile_low"])
            if "percentile_high" in scale:
                _ = float(scale["percentile_high"])
            if "log_ratio_threshold" in scale:
                _ = float(scale["log_ratio_threshold"])
            if "min_positive" in scale:
                _ = float(scale["min_positive"])


def _sanitize_id(text: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in text).strip("_")


def _safe_format(template: str, values: dict[str, Any]) -> str:
    class _SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    return template.format_map(_SafeDict(values))


def _resolve_text_tokens(document: dict[str, Any], dataset: WellDataset, source_path: Path) -> None:
    tokens = {str(key): value for key, value in dataset.well_metadata.items()}
    tokens["DATASET_NAME"] = dataset.name
    tokens["SOURCE_FILENAME"] = source_path.name
    tokens["SOURCE_PATH"] = str(source_path)

    name = document.get("name")
    if isinstance(name, str):
        document["name"] = _safe_format(name, tokens)

    header = document.get("header")
    if isinstance(header, dict):
        for key in ("title", "subtitle"):
            value = header.get(key)
            if isinstance(value, str):
                header[key] = _safe_format(value, tokens)
    footer = document.get("footer")
    if isinstance(footer, dict):
        lines = footer.get("lines")
        if isinstance(lines, list):
            footer["lines"] = [
                _safe_format(str(line), tokens) if isinstance(line, str) else line for line in lines
            ]


def load_dataset_for_logfile(
    spec: LogFileSpec, *, base_dir: Path | None = None
) -> tuple[WellDataset, Path]:
    source_path = Path(spec.data_source_path)
    if not source_path.is_absolute():
        source_path = (base_dir or Path.cwd()) / source_path
    source_path = source_path.resolve()

    source_format = spec.data_source_format
    if source_format == "auto":
        source_format = source_path.suffix.lower().lstrip(".")
    if source_format == "las":
        return load_las(source_path), source_path
    if source_format == "dlis":
        return load_dlis(source_path), source_path
    raise TemplateValidationError(f"Unsupported data source format {source_format!r}.")


def _build_scale(values: np.ndarray, scale_cfg: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(scale_cfg or {})
    fixed_bounds = "min" in cfg or "max" in cfg
    if fixed_bounds:
        if "min" not in cfg or "max" not in cfg:
            raise TemplateValidationError(
                "Track scale requires both min and max when fixed bounds are used."
            )
        kind = str(cfg.get("kind", "linear")).strip().lower()
        if kind == "auto":
            kind = "linear"
        if kind not in {"linear", "log"}:
            raise TemplateValidationError("Track scale kind must be linear, log, or auto.")
        scale: dict[str, Any] = {
            "kind": kind,
            "min": float(cfg["min"]),
            "max": float(cfg["max"]),
        }
        if "reverse" in cfg:
            scale["reverse"] = bool(cfg["reverse"])
        return scale

    finite = values[np.isfinite(values)]
    if finite.size < 2:
        return {"kind": "linear", "min": 0.0, "max": 1.0}

    low = float(cfg.get("percentile_low", 2.0))
    high = float(cfg.get("percentile_high", 98.0))
    min_positive = float(cfg.get("min_positive", 1e-6))
    ratio_threshold = float(cfg.get("log_ratio_threshold", 200.0))
    if low >= high:
        raise TemplateValidationError("Track percentile_low must be lower than percentile_high.")

    lower, upper = np.nanpercentile(finite, [low, high])
    if np.isclose(lower, upper):
        pad = max(abs(lower) * 0.1, 1.0)
        lower -= pad
        upper += pad

    requested_kind = str(cfg.get("kind", "auto")).strip().lower()
    if requested_kind not in {"auto", "linear", "log"}:
        raise TemplateValidationError("Track scale kind must be auto, linear, or log.")

    scale_kind = "linear"
    if requested_kind == "log":
        scale_kind = "log"
    elif requested_kind == "auto":
        if lower > 0 and upper / max(lower, min_positive) >= ratio_threshold:
            scale_kind = "log"
    if lower > 0 and upper / max(lower, min_positive) >= ratio_threshold:
        if requested_kind != "linear":
            scale_kind = "log"
    if scale_kind == "log":
        lower = max(lower, min_positive)

    scale: dict[str, Any] = {"kind": scale_kind, "min": float(lower), "max": float(upper)}
    if "reverse" in cfg:
        scale["reverse"] = bool(cfg["reverse"])
    return scale


def _build_tracks(dataset: WellDataset, auto_tracks: dict[str, Any]) -> list[dict[str, Any]]:
    scalar_channels = [
        channel for channel in dataset.channels.values() if isinstance(channel, ScalarChannel)
    ]
    if not scalar_channels:
        raise TemplateValidationError("Dataset has no scalar channels for auto track generation.")

    depth_track = _ensure_mapping(auto_tracks["depth_track"], context="auto_tracks.depth_track")
    track_items = _ensure_sequence(auto_tracks["tracks"], context="auto_tracks.tracks")
    on_missing = str(auto_tracks.get("on_missing", "skip")).strip().lower()
    max_tracks = max(int(auto_tracks.get("max_tracks", len(track_items))), 1)
    by_upper = {channel.mnemonic.upper(): channel for channel in scalar_channels}

    tracks = [
        {
            "id": str(depth_track["id"]),
            "title": str(depth_track["title"]),
            "kind": "depth",
            "width_mm": float(depth_track["width_mm"]),
            "track_header": deepcopy(depth_track.get("track_header", {})),
        }
    ]

    added = 0
    for index, item in enumerate(track_items, start=1):
        track_item = _ensure_mapping(item, context=f"auto_tracks.tracks[{index - 1}]")
        channel_name = str(track_item["channel"])
        channel = by_upper.get(channel_name.upper())
        required = bool(track_item.get("required", False))
        if channel is None:
            if required or on_missing == "error":
                raise TemplateValidationError(
                    f"Configured channel {channel_name!r} was not found in dataset."
                )
            continue

        configure = _ensure_mapping(
            track_item["configure"],
            context=f"auto_tracks.tracks[{index - 1}].configure",
        )
        style = deepcopy(
            _ensure_mapping(
                configure["style"],
                context=f"auto_tracks.tracks[{index - 1}].configure.style",
            )
        )
        grid = deepcopy(configure.get("grid", {}))
        header = deepcopy(configure.get("track_header", {}))
        width_mm = float(configure["width_mm"])
        title_template = str(configure.get("title_template", "{mnemonic} [{unit}]"))
        configured_title = configure.get("title")

        unit = channel.value_unit or ""
        format_values = {
            "mnemonic": channel.mnemonic,
            "unit": unit,
            "description": channel.description or "",
        }
        if isinstance(configured_title, str) and configured_title.strip():
            title = _safe_format(configured_title, format_values).strip()
        else:
            title = _safe_format(title_template, format_values).strip()
        default_id = f"{_sanitize_id(channel.mnemonic) or 'curve'}_{index}"
        track_id = str(configure.get("id", default_id))

        tracks.append(
            {
                "id": track_id,
                "title": title or channel.mnemonic,
                "kind": "curve",
                "width_mm": width_mm,
                "track_header": header,
                "grid": grid,
                "x_scale": _build_scale(channel.masked_values(), configure.get("scale")),
                "elements": [
                    {
                        "kind": "curve",
                        "channel": channel.mnemonic,
                        "label": channel.mnemonic,
                        "style": style,
                    }
                ],
            }
        )
        added += 1
        if added >= max_tracks:
            break

    if added == 0:
        raise TemplateValidationError("No configured tracks were added from auto_tracks.tracks.")
    return tracks


def build_document_for_logfile(
    spec: LogFileSpec,
    dataset: WellDataset,
    *,
    source_path: Path,
) -> LogDocument:
    document = deepcopy(spec.document)
    if "name" not in document:
        document["name"] = spec.name
    _resolve_text_tokens(document, dataset, source_path)
    document["tracks"] = _build_tracks(dataset, spec.auto_tracks)
    return document_from_mapping(document)
