"""Resource-limited metadata parser child; never loads numeric samples."""

from __future__ import annotations

import io
import json
import resource
import sys
from collections import Counter
from pathlib import Path
from typing import Any

MAX_LAS_LINE_BYTES = 2 * 1_048_576
MAX_LAS_PREFIX_BYTES = 16 * 1_048_576
MAX_METADATA_OBJECTS = 5_001
# Keep aligned with wellplot.io.las._DEPTH_MNEMONICS: the canonical loader
# consumes a depth-named first curve as LASIO's index instead of a regular curve.
_LAS_DEPTH_INDEX_MNEMONICS = {"DEPT", "DEPTH", "MD", "TDEP"}
_DLIS_DEPTH_MNEMONICS = _LAS_DEPTH_INDEX_MNEMONICS
_DLIS_NONRENDERABLE_MNEMONICS = {"FRAMENO"}


def main(arguments: list[str]) -> int:
    """Inspect one source under child-process resource limits."""
    if len(arguments) != 5:
        return 2
    source_format, raw_path, cpu_text, wall_text, address_text = arguments
    try:
        _apply_resource_limits(int(cpu_text), int(address_text))
        path = Path(raw_path)
        if source_format == "las":
            projection = _inspect_las(path)
        elif source_format == "dlis":
            projection = _inspect_dlis(path)
        else:
            return 2
        encoded = json.dumps(projection, separators=(",", ":"), ensure_ascii=True)
        sys.stdout.write(encoded)
        sys.stdout.flush()
        return 0
    except BaseException:
        # Parser text and exception messages may contain source-controlled data.
        return 3


def _apply_resource_limits(cpu_seconds: int, address_space_bytes: int) -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_AS, (address_space_bytes, address_space_bytes))


def _inspect_las(path: Path) -> dict[str, Any]:
    import lasio

    prefix = _read_las_header(path)
    try:
        header_text = prefix.decode("utf-8-sig")
    except UnicodeDecodeError:
        header_text = prefix.decode("latin-1")
    las = lasio.read(io.StringIO(header_text), ignore_data=True)
    curves = list(las.curves)
    if not curves or len(curves) > MAX_METADATA_OBJECTS:
        raise ValueError("incomplete LAS curve inventory")
    source_tokens = _las_curve_source_tokens(header_text)
    tokens_align = len(source_tokens) == len(curves)
    counts = Counter(str(curve.mnemonic).strip().casefold() for curve in curves)
    channels = []
    for index, curve in enumerate(curves):
        mnemonic = str(curve.mnemonic).strip()
        source_token = source_tokens[index] if tokens_align else None
        if not mnemonic:
            raise ValueError("blank LAS mnemonic")
        is_depth_index_curve = index == 0 and mnemonic.upper() in _LAS_DEPTH_INDEX_MNEMONICS
        has_unique_mnemonic = counts[mnemonic.casefold()] == 1
        if not has_unique_mnemonic or is_depth_index_curve:
            addressability = "UNADDRESSABLE"
        elif mnemonic.upper() in _LAS_DEPTH_INDEX_MNEMONICS:
            # The loader may omit another depth-named curve if its samples match
            # LASIO's index; metadata-only inspection cannot establish equality.
            addressability = "UNKNOWN"
        else:
            addressability = "ADDRESSABLE"
        channels.append(
            {
                "mnemonic": mnemonic,
                "source_token": source_token,
                "unit": str(curve.unit).strip() or None,
                "kind": "scalar",
                "physical_identity": {"format": "LAS", "curve_index": index},
                "addressability": addressability,
                "frame_indexes": [],
            }
        )
    return {
        "complete": True,
        "dataset_name": "",
        "well_metadata": {},
        "channels": channels,
    }


def _las_curve_source_tokens(header_text: str) -> list[str]:
    """Return bounded raw curve tokens in source order, without descriptions."""
    tokens: list[str] = []
    in_curve_section = False
    for line in header_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("~"):
            section_marker = stripped[1:2].casefold()
            in_curve_section = section_marker == "c"
            continue
        if not in_curve_section:
            continue
        token = stripped.split(maxsplit=1)[0].rstrip(":")
        if token:
            tokens.append(token)
            if len(tokens) > MAX_METADATA_OBJECTS:
                raise ValueError("LAS curve header limit")
    return tokens


def _read_las_header(path: Path) -> bytes:
    prefix = bytearray()
    with path.open("rb") as stream:
        while len(prefix) < MAX_LAS_PREFIX_BYTES:
            line = stream.readline(MAX_LAS_LINE_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_LAS_LINE_BYTES:
                raise ValueError("LAS header line limit")
            if len(prefix) + len(line) > MAX_LAS_PREFIX_BYTES:
                raise ValueError("LAS header prefix limit")
            prefix.extend(line)
            stripped = line.lstrip()
            if len(stripped) >= 2 and stripped[:1] == b"~" and stripped[1:2].upper() == b"A":
                break
            if len(prefix) >= MAX_LAS_PREFIX_BYTES:
                raise ValueError("LAS header prefix limit")
    else_prefix = bytes(prefix)
    if not else_prefix or not _has_data_marker(else_prefix):
        raise ValueError("LAS inventory incomplete")
    return else_prefix


def _has_data_marker(prefix: bytes) -> bool:
    for line in prefix.splitlines():
        stripped = line.lstrip()
        if len(stripped) >= 2 and stripped[:1] == b"~" and stripped[1:2].upper() == b"A":
            return True
    return False


def _inspect_dlis(path: Path) -> dict[str, Any]:
    from dlisio import common, dlis

    handler = common.ErrorHandler(
        info=common.Actions.LOG_INFO,
        minor=common.Actions.RAISE,
        major=common.Actions.RAISE,
        critical=common.Actions.RAISE,
    )
    logical_files = dlis.load(str(path), error_handler=handler)
    if not logical_files:
        raise ValueError("DLIS inventory incomplete")
    object_count = len(logical_files)
    records = []
    renderer_counts: Counter[str] = Counter()
    for channel in getattr(logical_files[0], "channels", []) or []:
        renderer_counts[str(getattr(channel, "name", "")).casefold()] += 1
    for logical_index, logical_file in enumerate(logical_files):
        frames = list(getattr(logical_file, "frames", []) or [])
        channels = list(getattr(logical_file, "channels", []) or [])
        object_count += len(frames) + len(channels)
        if object_count > MAX_METADATA_OBJECTS:
            raise ValueError("DLIS metadata object limit")
        memberships: dict[int, list[int]] = {id(channel): [] for channel in channels}
        frame_index_names: dict[int, str] = {}
        for frame_index, frame in enumerate(frames):
            index_value = getattr(frame, "index", None)
            index_name = getattr(index_value, "name", index_value)
            if index_name is not None:
                frame_index_names[frame_index] = str(index_name).strip()
            for channel in getattr(frame, "channels", []) or []:
                memberships.setdefault(id(channel), []).append(frame_index)
        for channel in channels:
            mnemonic = str(getattr(channel, "name", "")).strip()
            if not mnemonic:
                raise ValueError("blank DLIS mnemonic")
            frame_indexes = tuple(memberships.get(id(channel), ()))
            kind = (
                "array"
                if any(int(value) > 1 for value in (getattr(channel, "dimension", []) or []))
                else "scalar"
            )
            renderer_addressable = (
                logical_index == 0
                and renderer_counts[mnemonic.casefold()] == 1
                and len(frame_indexes) == 1
            )
            is_frame_index = any(
                frame_index_names.get(frame_index) == mnemonic for frame_index in frame_indexes
            )
            if (
                not renderer_addressable
                or is_frame_index
                or mnemonic.upper() in _DLIS_NONRENDERABLE_MNEMONICS
            ):
                addressability = "UNADDRESSABLE"
            elif kind == "scalar" and mnemonic.upper() in _DLIS_DEPTH_MNEMONICS:
                # The renderer loader may omit a non-index depth channel when
                # its samples equal the frame index; metadata cannot decide.
                addressability = "UNKNOWN"
            else:
                addressability = "ADDRESSABLE"
            records.append(
                {
                    "mnemonic": mnemonic,
                    "unit": _optional_text(getattr(channel, "units", None)),
                    "kind": kind,
                    "physical_identity": {
                        "format": "DLIS",
                        "logical_file_index": logical_index,
                        "name": mnemonic,
                        "origin": int(getattr(channel, "origin", 0)),
                        "copy_number": int(getattr(channel, "copynumber", 0)),
                        "object_type": str(getattr(channel, "type", "CHANNEL")),
                        "frame_indexes": frame_indexes,
                    },
                    "addressability": addressability,
                    "frame_indexes": frame_indexes,
                }
            )
    if not records:
        raise ValueError("DLIS inventory incomplete")
    return {
        "complete": True,
        "dataset_name": "",
        "well_metadata": {},
        "channels": records,
    }


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text[:256] or None


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
