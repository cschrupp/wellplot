"""Provider-free A09 metadata inspection and containment regressions."""

from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

import lasio
import pytest

from wellplot.agent.code_mode import source_inspection_child
from wellplot.agent.code_mode import source_loader as source_loader_module
from wellplot.agent.code_mode.source_loader import (
    CHILD_ADDRESS_SPACE_BYTES,
    DLIS_CPU_SECONDS,
    DLIS_WALL_SECONDS,
    LAS_CPU_SECONDS,
    LAS_WALL_SECONDS,
    MAX_CHILD_OUTPUT_BYTES,
    LogfileSourceLoader,
    SourceInspectionError,
    _collect_child_stdout,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DLIS_FIXTURE = REPO_ROOT / "tests/fixtures/a09_d2_metadata/multifile_repeated_mnemonics.dlis"
DLIS_FIXTURE_SHA256 = "b98beba2bc6fedb70794da63d68dd09ac94abe02191fbfb53e6acd2eb85c08b9"


def _write_small_las(path: Path) -> None:
    las = lasio.LASFile()
    las.append_curve("DEPT", [100.0, 101.0], unit="m")
    las.append_curve("GR", [50.0, 51.0], unit="gAPI")
    las.write(str(path), version=2.0)


def test_las_metadata_inspection_does_not_depend_on_numeric_tail(tmp_path: Path) -> None:
    """Metadata extraction stops at the data marker and exposes no samples."""
    source = tmp_path / "source.las"
    _write_small_las(source)
    first = LogfileSourceLoader(runtime_root=tmp_path).load(source, "las")
    with source.open("ab") as stream:
        stream.write(b"0 1\n" * 250_000)
    second = LogfileSourceLoader(runtime_root=tmp_path).load(source, "las")

    assert [channel.mnemonic for channel in first.channels] == ["DEPT", "GR"]
    assert [channel.mnemonic for channel in second.channels] == ["DEPT", "GR"]
    assert all(channel.addressability == "ADDRESSABLE" for channel in second.channels)
    assert all(channel.sample_availability == "NOT_CHECKED" for channel in second.channels)
    assert all(channel.shape == () for channel in second.channels)
    assert all(channel.description == "" and channel.aliases == () for channel in second.channels)
    assert first.well_metadata == second.well_metadata == ()


def test_incomplete_las_header_fails_closed(tmp_path: Path) -> None:
    """A file without a complete data-section marker is not an empty inventory."""
    source = tmp_path / "incomplete.las"
    source.write_text("~V\nVERS. 2.0\n~C\nDEPT.M\n", encoding="ascii")

    with pytest.raises(SourceInspectionError):
        LogfileSourceLoader(runtime_root=tmp_path).load(source, "las")


def test_dlis_repeated_physical_identities_are_not_renderer_addressable() -> None:
    """Metadata retains logical/frame/copy identity without sample loading."""
    digest = hashlib.sha256(DLIS_FIXTURE.read_bytes()).hexdigest()
    assert digest == DLIS_FIXTURE_SHA256

    source = LogfileSourceLoader(runtime_root=REPO_ROOT).load(DLIS_FIXTURE, "dlis")

    assert len(source.channels) == 6
    assert all(channel.addressability == "UNADDRESSABLE" for channel in source.channels)
    depths = [channel for channel in source.channels if channel.mnemonic == "DEPTH"]
    assert len({channel.physical_identity["logical_file_index"] for channel in depths}) == 2
    assert {channel.physical_identity["copy_number"] for channel in depths[:2]} == {0, 1}
    assert {channel.frame_indexes for channel in depths[:2]} == {(0,), (1,)}
    assert all(channel.sample_availability == "NOT_CHECKED" for channel in source.channels)
    assert all(channel.description == "" and channel.aliases == () for channel in source.channels)


def test_parser_lock_is_exclusive_and_released_after_close(tmp_path: Path) -> None:
    """Separate lock opens contend, and capacity becomes available after release."""
    loader = LogfileSourceLoader(runtime_root=tmp_path)
    held_fd = loader._acquire_host_lock()
    try:
        with pytest.raises(SourceInspectionError) as caught:
            loader._acquire_host_lock()
        assert caught.value.code == "inspection_busy"
    finally:
        os.close(held_fd)

    released_fd = loader._acquire_host_lock()
    os.close(released_fd)


def test_parser_lock_coordinates_independent_processes(tmp_path: Path) -> None:
    """Independent WellPlot processes share one nonblocking parser lock."""
    loader = LogfileSourceLoader(runtime_root=tmp_path)
    held_fd = loader._acquire_host_lock()
    lock_path = tmp_path / "workspace" / ".wellplot-inspection" / "parser.lock"
    child_code = "\n".join(
        (
            "import fcntl, os, sys",
            "fd = os.open(sys.argv[1], os.O_RDWR)",
            "try:",
            "    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)",
            "except BlockingIOError:",
            "    sys.exit(17)",
            "fcntl.flock(fd, fcntl.LOCK_UN)",
            "os.close(fd)",
        )
    )
    try:
        blocked = subprocess.run(
            [sys.executable, "-c", child_code, str(lock_path)],
            check=False,
            timeout=3,
        )
        assert blocked.returncode == 17
    finally:
        os.close(held_fd)

    available = subprocess.run(
        [sys.executable, "-c", child_code, str(lock_path)],
        check=False,
        timeout=3,
    )
    assert available.returncode == 0


def test_inherited_parser_lock_survives_supervisor_descriptor_close(tmp_path: Path) -> None:
    """A child-held descriptor prevents a second process from entering early."""
    loader = LogfileSourceLoader(runtime_root=tmp_path)
    held_fd = loader._acquire_host_lock()
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(1.0)"],
        pass_fds=(held_fd,),
        start_new_session=True,
    )
    os.close(held_fd)
    try:
        with pytest.raises(SourceInspectionError) as caught:
            loader._acquire_host_lock()
        assert caught.value.code == "inspection_busy"
    finally:
        child.wait(timeout=3)

    released_fd = loader._acquire_host_lock()
    os.close(released_fd)


def test_parser_child_output_is_incrementally_capped_and_reaped() -> None:
    """The collector terminates a flooding child at the aggregate output cap."""
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('x' * 4096); sys.stderr.write('y' * 4096)",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    with pytest.raises(SourceInspectionError) as caught:
        _collect_child_stdout(process, wall_seconds=3, output_limit=1024)

    assert caught.value.code == "inspection_output_limit"
    assert process.poll() is not None
    assert MAX_CHILD_OUTPUT_BYTES == 1_048_576


def test_parser_child_wall_timeout_kills_and_reaps_process_group() -> None:
    """A stuck child is terminated within the bounded wall-time path."""
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    started = time.monotonic()
    with pytest.raises(SourceInspectionError) as caught:
        _collect_child_stdout(process, wall_seconds=0.1, output_limit=MAX_CHILD_OUTPUT_BYTES)

    assert caught.value.code == "inspection_wall_limit"
    assert process.poll() is not None
    assert time.monotonic() - started < 3


def test_parser_supervisor_cancellation_kills_and_reaps_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Supervisor cancellation propagates and does not orphan the parser child."""
    loader = LogfileSourceLoader(runtime_root=tmp_path)
    processes: list[subprocess.Popen[bytes]] = []
    original_popen = source_loader_module.subprocess.Popen

    def track_process(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    def cancel_collection(*_args: object, **_kwargs: object) -> bytes:
        raise asyncio.CancelledError

    monkeypatch.setattr(source_loader_module.subprocess, "Popen", track_process)
    monkeypatch.setattr(source_loader_module, "_collect_child_stdout", cancel_collection)
    lock_fd = loader._acquire_host_lock()
    try:
        with pytest.raises(asyncio.CancelledError):
            loader._run_child(tmp_path / "unused.las", "las", lock_fd)
    finally:
        os.close(lock_fd)

    assert len(processes) == 1
    assert processes[0].poll() is not None


def test_abnormal_parser_exit_has_bounded_failure_code(tmp_path: Path) -> None:
    """A nonzero child exit is classified without retaining parser output."""
    loader = LogfileSourceLoader(runtime_root=tmp_path)
    lock_fd = loader._acquire_host_lock()
    try:
        with pytest.raises(SourceInspectionError) as caught:
            loader._run_child(tmp_path / "unused", "invalid", lock_fd)  # type: ignore[arg-type]
    finally:
        os.close(lock_fd)

    assert caught.value.code == "inspection_child_failed"


def test_child_applies_cpu_and_address_space_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    """The parser child applies the configured OS resource limits before parsing."""
    applied: list[tuple[int, tuple[int, int]]] = []

    def record_limit(resource_id: int, limits: tuple[int, int]) -> None:
        applied.append((resource_id, limits))

    monkeypatch.setattr(source_inspection_child.resource, "setrlimit", record_limit)
    source_inspection_child._apply_resource_limits(7, CHILD_ADDRESS_SPACE_BYTES)

    assert applied == [
        (source_inspection_child.resource.RLIMIT_CPU, (7, 7)),
        (
            source_inspection_child.resource.RLIMIT_AS,
            (CHILD_ADDRESS_SPACE_BYTES, CHILD_ADDRESS_SPACE_BYTES),
        ),
    ]


def test_parser_limits_are_finite_and_format_specific() -> None:
    """The accepted provisional child limits are actually bound to each format."""
    assert (LAS_CPU_SECONDS, LAS_WALL_SECONDS) == (10, 15)
    assert (DLIS_CPU_SECONDS, DLIS_WALL_SECONDS) == (90, 120)
    assert CHILD_ADDRESS_SPACE_BYTES == 1_073_741_824
