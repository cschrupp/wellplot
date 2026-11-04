"""Host-owned metadata-only source inspection for Code Mode enrichment."""

from __future__ import annotations

import fcntl
import json
import os
import selectors
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .enrichment import (
    ChannelContext,
    LoadedSource,
    SourceFormat,
    SourceLoaderProtocol,
    SourceMetadata,
)

MAX_CHILD_OUTPUT_BYTES = 1_048_576
MAX_METADATA_OBJECTS = 5_001
MAX_LAS_LINE_BYTES = 2 * 1_048_576
MAX_LAS_PREFIX_BYTES = 16 * 1_048_576
LAS_CPU_SECONDS = 10
LAS_WALL_SECONDS = 15
DLIS_CPU_SECONDS = 90
DLIS_WALL_SECONDS = 120
CHILD_ADDRESS_SPACE_BYTES = 1_073_741_824


class _ChannelProjection(BaseModel):
    """Strict metadata-only physical-channel projection from the parser child."""

    model_config = ConfigDict(extra="forbid", strict=True)

    mnemonic: str = Field(min_length=1, max_length=256)
    unit: str | None = Field(default=None, max_length=256)
    kind: Literal["scalar", "array"]
    physical_identity: dict[str, str | int | tuple[int, ...]]
    addressability: Literal["ADDRESSABLE", "UNADDRESSABLE", "UNKNOWN"]
    frame_indexes: tuple[int, ...] = ()


class _InspectionProjection(BaseModel):
    """Complete bounded child response, with an explicit terminal marker."""

    model_config = ConfigDict(extra="forbid", strict=True)

    complete: Literal[True]
    dataset_name: str = Field(max_length=512)
    well_metadata: dict[str, str]
    channels: tuple[_ChannelProjection, ...] = Field(max_length=MAX_METADATA_OBJECTS)


class SourceInspectionError(RuntimeError):
    """Safe inspection failure with no parser text or source path retained."""

    def __init__(self, code: str) -> None:
        """Create a safe error containing only its stable failure code."""
        self.code = code
        super().__init__(code)


class LogfileSourceLoader(SourceLoaderProtocol):
    """Inspect LAS/DLIS metadata behind the canonical source-loader boundary."""

    def __init__(self, runtime_root: str | Path | None = None) -> None:
        """Bind the shared parser lock to the canonical runtime root."""
        self.runtime_root = Path(runtime_root or Path.cwd()).expanduser().resolve()

    def load(self, path: Path, source_format: SourceFormat) -> LoadedSource:
        """Return complete metadata without invoking numerical-data loaders."""
        source = path.resolve(strict=True)
        lock_fd = self._acquire_host_lock()
        try:
            response = self._run_child(source, source_format, lock_fd)
        finally:
            os.close(lock_fd)

        try:
            projection = _InspectionProjection.model_validate_json(response)
        except (ValidationError, ValueError) as exc:
            raise SourceInspectionError("inspection_projection_invalid") from exc
        if not projection.channels:
            raise SourceInspectionError("inspection_inventory_incomplete")
        if len(projection.channels) > MAX_METADATA_OBJECTS:
            raise SourceInspectionError("inspection_metadata_limit")

        return LoadedSource(
            dataset_name=projection.dataset_name or source.stem,
            well_metadata=tuple(
                SourceMetadata(key=key, value=value)
                for key, value in sorted(projection.well_metadata.items())
                if key.strip() and value.strip()
            ),
            channels=tuple(
                ChannelContext(
                    mnemonic=channel.mnemonic,
                    kind=channel.kind,
                    unit=channel.unit,
                    physical_identity=channel.physical_identity,
                    addressability=channel.addressability,
                    frame_indexes=channel.frame_indexes,
                    # Source-authored descriptions and aliases are untrusted.
                    description="",
                    aliases=(),
                )
                for channel in projection.channels
            ),
        )

    def _acquire_host_lock(self) -> int:
        lock_directory = self.runtime_root / "workspace" / ".wellplot-inspection"
        try:
            lock_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(lock_directory, 0o700)
            lock_path = lock_directory / "parser.lock"
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            os.fchmod(fd, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                os.close(fd)
                raise SourceInspectionError("inspection_busy") from exc
            return fd
        except SourceInspectionError:
            raise
        except OSError as exc:
            raise SourceInspectionError("inspection_lock_unavailable") from exc

    def _run_child(self, path: Path, source_format: SourceFormat, lock_fd: int) -> bytes:
        cpu_seconds, wall_seconds = _limits_for(source_format)
        command = [
            sys.executable,
            str(Path(__file__).with_name("source_inspection_child.py")),
            source_format,
            str(path),
            str(cpu_seconds),
            str(wall_seconds),
            str(CHILD_ADDRESS_SPACE_BYTES),
        ]
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True,
                pass_fds=(lock_fd,),
                start_new_session=True,
            )
        except OSError as exc:
            raise SourceInspectionError("inspection_child_start_failed") from exc

        try:
            stdout = _collect_child_stdout(
                process,
                wall_seconds=wall_seconds,
                output_limit=MAX_CHILD_OUTPUT_BYTES,
            )
            returncode = process.wait(timeout=1)
            if returncode != 0:
                if returncode == -getattr(signal, "SIGXCPU", -1):
                    raise SourceInspectionError("inspection_cpu_limit")
                raise SourceInspectionError("inspection_child_failed")
            # Parser stderr is counted against the cap but never retained.
            return _extract_child_json(bytes(stdout))
        except BaseException:
            if process.poll() is None:
                _terminate_process_group(process)
            raise
        finally:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()


def _collect_child_stdout(
    process: subprocess.Popen[bytes],
    *,
    wall_seconds: float,
    output_limit: int,
) -> bytes:
    """Drain both pipes incrementally while retaining only bounded stdout."""
    selector = selectors.DefaultSelector()
    assert process.stdout is not None
    assert process.stderr is not None
    for stream in (process.stdout, process.stderr):
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ)
    stdout = bytearray()
    total_output = 0
    deadline = time.monotonic() + wall_seconds
    try:
        while selector.get_map() or process.poll() is None:
            if time.monotonic() >= deadline:
                _terminate_process_group(process)
                raise SourceInspectionError("inspection_wall_limit")
            for key, _events in selector.select(timeout=0.05):
                remaining = output_limit - total_output
                chunk = os.read(key.fd, min(65_536, remaining + 1))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                total_output += len(chunk)
                if total_output > output_limit:
                    _terminate_process_group(process)
                    raise SourceInspectionError("inspection_output_limit")
                if key.fileobj is process.stdout:
                    stdout.extend(chunk)
        return bytes(stdout)
    except BaseException:
        if process.poll() is None:
            _terminate_process_group(process)
        raise
    finally:
        selector.close()


def _limits_for(source_format: SourceFormat) -> tuple[int, int]:
    if source_format == "las":
        return LAS_CPU_SECONDS, LAS_WALL_SECONDS
    return DLIS_CPU_SECONDS, DLIS_WALL_SECONDS


def _extract_child_json(output: bytes) -> bytes:
    """Reject any unexpected framing rather than parsing an ambiguous stream."""
    try:
        payload = json.loads(output)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceInspectionError("inspection_projection_invalid") from exc
    if not isinstance(payload, dict) or payload.get("complete") is not True:
        raise SourceInspectionError("inspection_inventory_incomplete")
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    """Kill and reap the direct parser child and any descendants."""
    if process.poll() is None:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


__all__ = ["LogfileSourceLoader", "SourceInspectionError"]
