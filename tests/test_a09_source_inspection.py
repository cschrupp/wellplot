"""Provider-free A09 metadata inspection and containment regressions."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

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
from wellplot.io.las import _DEPTH_MNEMONICS

REPO_ROOT = Path(__file__).resolve().parents[1]
DLIS_FIXTURE = REPO_ROOT / "tests/fixtures/a09_d2_metadata/multifile_repeated_mnemonics.dlis"
DLIS_FIXTURE_SHA256 = "b98beba2bc6fedb70794da63d68dd09ac94abe02191fbfb53e6acd2eb85c08b9"
CBL_REPEAT_DLIS = (
    REPO_ROOT / "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis"
)
CBL_REPEAT_DLIS_SHA256 = "a4a2e91b495172079fc47bc2e9c936f0ab60c9845bbed8e65bf56555a5e82640"
CBL_REPEAT_METADATA_SHA256 = "b17fc03542ea815c00da2e063086aee1c97122188a372211d425178733ea887d"
CBL_REPEAT_UNAFFECTED_CLASSIFICATIONS_SHA256 = (
    "faba5cc6cbc14ad90f3ba1ddbc8c43f66b861e4be7ceadfeff50a7ee072cbea6"
)
SHELL_LAS = REPO_ROOT / "workspace/data/30-23a-3 8117_d.las"
SHELL_LAS_CHANNELS = (
    "DEPTH",
    "CAL",
    "CALI",
    "CGR",
    "DRHO",
    "DT",
    "DTL",
    "GR",
    "GRD",
    "ILD",
    "ILM",
    "MSFL",
    "NPHI",
    "PEF",
    "POTA.",
    "RHOB",
    "SFLU",
    "SP",
    "THOR",
    "URAN",
)


def _write_small_las(path: Path) -> None:
    las = lasio.LASFile()
    las.append_curve("DEPT", [100.0, 101.0], unit="m")
    las.append_curve("GR", [50.0, 51.0], unit="gAPI")
    las.write(str(path), version=2.0)


def _write_las_with_later_depth_alias(path: Path) -> None:
    """Write a LAS where a later MD curve may be consumed as the index."""
    las = lasio.LASFile()
    las.append_curve("DEPTH", [100.0, 101.0], unit="m")
    las.append_curve("MD", [100.0, 101.0], unit="m")
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
    assert [channel.addressability for channel in first.channels] == [
        "UNADDRESSABLE",
        "ADDRESSABLE",
    ]
    assert [channel.addressability for channel in second.channels] == [
        "UNADDRESSABLE",
        "ADDRESSABLE",
    ]
    assert all(channel.sample_availability == "NOT_CHECKED" for channel in second.channels)
    assert all(channel.shape == () for channel in second.channels)
    assert all(channel.description == "" and channel.aliases == () for channel in second.channels)
    assert first.well_metadata == second.well_metadata == ()


def test_later_depth_mnemonic_addressability_is_unknown_without_sample_inspection(
    tmp_path: Path,
) -> None:
    """A later depth alias is not presumed addressable from its header alone."""
    source_path = tmp_path / "later-depth-alias.las"
    _write_las_with_later_depth_alias(source_path)

    source = LogfileSourceLoader(runtime_root=tmp_path).load(source_path, "las")

    assert [channel.mnemonic for channel in source.channels] == ["DEPTH", "MD", "GR"]
    assert [channel.physical_identity["curve_index"] for channel in source.channels] == [0, 1, 2]
    assert [channel.addressability for channel in source.channels] == [
        "UNADDRESSABLE",
        "UNKNOWN",
        "ADDRESSABLE",
    ]
    assert all(channel.sample_availability == "NOT_CHECKED" for channel in source.channels)
    assert all(channel.shape == () for channel in source.channels)


def test_las_depth_index_contract_matches_scientific_loader() -> None:
    """Metadata inspection and the canonical loader share depth-index names."""
    assert source_inspection_child._LAS_DEPTH_INDEX_MNEMONICS == _DEPTH_MNEMONICS


@pytest.mark.skipif(not SHELL_LAS.is_file(), reason="canonical Shell LAS asset unavailable")
def test_shell_las_projection_preserves_channels_and_marks_depth_index_unaddressable() -> None:
    """Project the real Shell LAS header without loading numerical samples."""
    source = LogfileSourceLoader(runtime_root=REPO_ROOT).load(SHELL_LAS, "las")

    assert [channel.mnemonic for channel in source.channels] == list(SHELL_LAS_CHANNELS)
    assert source.channels[0].physical_identity == {"format": "LAS", "curve_index": 0}
    assert source.channels[0].mnemonic == "DEPTH"
    assert source.channels[0].addressability == "UNADDRESSABLE"
    assert source.channels[14].mnemonic == "POTA."
    assert source.channels[14].source_token == "POTA.."
    assert source.channels[14].unit is None
    assert all(channel.sample_availability == "NOT_CHECKED" for channel in source.channels)
    assert all(channel.shape == () for channel in source.channels)
    assert [channel.physical_identity["curve_index"] for channel in source.channels] == list(
        range(20)
    )


def test_other_double_period_record_does_not_receive_pota_request_name(tmp_path: Path) -> None:
    """The legacy request spelling is assigned only to exact POTA source syntax."""
    source_path = tmp_path / "other-double-period.las"
    source_path.write_text(
        "~Version Information Section\n"
        "VERS. 2.0\n"
        "~Well Information Section\n"
        "STRT.m 100\nSTOP.m 101\nSTEP.m 1\nNULL. -999.25\n"
        "~Curve Information Section\n"
        "DEPT.m : Depth\n"
        "OTHER.. : Other channel with an unspecified unit\n"
        "~ASCII Log Data Section\n",
        encoding="ascii",
    )

    source = LogfileSourceLoader(runtime_root=tmp_path).load(source_path, "las")

    assert [channel.mnemonic for channel in source.channels] == ["DEPT", "OTHER."]
    assert source.channels[1].source_token == "OTHER.."


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


def test_dlis_depth_and_frame_index_addressability_is_metadata_conservative(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Frame indexes and sample-dependent scalar depths are not presumed bindable."""
    from dlisio import dlis

    def channel(name: str, copy_number: int, dimension: tuple[int, ...] = ()) -> SimpleNamespace:
        return SimpleNamespace(
            name=name,
            units="ft",
            dimension=dimension,
            origin=7,
            copynumber=copy_number,
            type="CHANNEL",
        )

    channels = [
        channel("TDEP", 2),
        channel("DEPTH", 0),
        channel("MD", 0),
        channel("DEPT", 0, (2,)),
        channel("FRAMENO", 0),
        channel("GR", 0),
    ]

    def reject_sample_access() -> None:
        raise AssertionError("metadata inspection must not read frame samples")

    frame = SimpleNamespace(index="TDEP", channels=channels, curves=reject_sample_access)
    logical_file = SimpleNamespace(channels=channels, frames=[frame])
    monkeypatch.setattr(dlis, "load", lambda *_args, **_kwargs: [logical_file])

    projection = source_inspection_child._inspect_dlis(tmp_path / "metadata-only.dlis")
    channels_by_name = {item["mnemonic"]: item for item in projection["channels"]}

    assert projection["complete"] is True
    assert channels_by_name["TDEP"]["addressability"] == "UNADDRESSABLE"
    assert channels_by_name["FRAMENO"]["addressability"] == "UNADDRESSABLE"
    assert channels_by_name["DEPTH"]["addressability"] == "UNKNOWN"
    assert channels_by_name["MD"]["addressability"] == "UNKNOWN"
    assert channels_by_name["DEPT"]["kind"] == "array"
    assert channels_by_name["DEPT"]["addressability"] == "ADDRESSABLE"
    assert channels_by_name["GR"]["addressability"] == "ADDRESSABLE"
    assert channels_by_name["TDEP"]["physical_identity"] == {
        "format": "DLIS",
        "logical_file_index": 0,
        "name": "TDEP",
        "origin": 7,
        "copy_number": 2,
        "object_type": "CHANNEL",
        "frame_indexes": (0,),
    }
    source_loader_module._InspectionProjection.model_validate_json(json.dumps(projection))


@pytest.mark.skipif(not CBL_REPEAT_DLIS.is_file(), reason="canonical CBL DLIS asset unavailable")
def test_cbl_repeat_depth_addressability_preserves_metadata_and_other_classes() -> None:
    """The real CBL projection changes only sample-dependent depth addressability."""
    assert hashlib.sha256(CBL_REPEAT_DLIS.read_bytes()).hexdigest() == CBL_REPEAT_DLIS_SHA256

    source = LogfileSourceLoader(runtime_root=REPO_ROOT).load(CBL_REPEAT_DLIS, "dlis")
    channels = [
        {
            "mnemonic": channel.mnemonic,
            "unit": channel.unit,
            "kind": channel.kind,
            "physical_identity": channel.physical_identity,
            "frame_indexes": channel.frame_indexes,
            "sample_availability": channel.sample_availability,
        }
        for channel in source.channels
    ]
    metadata_digest = hashlib.sha256(
        json.dumps(channels, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    depth_channels = [
        channel
        for channel in source.channels
        if channel.mnemonic.upper() in {"DEPT", "DEPTH", "MD", "TDEP"}
    ]
    unaffected = [
        {
            "mnemonic": channel.mnemonic,
            "physical_identity": channel.physical_identity,
            "addressability": channel.addressability,
        }
        for channel in source.channels
        if channel.mnemonic.upper() not in {"DEPT", "DEPTH", "MD", "TDEP"}
    ]
    unaffected_digest = hashlib.sha256(
        json.dumps(unaffected, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()

    assert len(source.channels) == 79
    assert metadata_digest == CBL_REPEAT_METADATA_SHA256
    assert Counter(channel.addressability for channel in source.channels) == {
        "ADDRESSABLE": 67,
        "UNADDRESSABLE": 10,
        "UNKNOWN": 2,
    }
    assert len([channel for channel in depth_channels if channel.mnemonic == "TDEP"]) == 4
    assert all(
        channel.addressability == "UNADDRESSABLE"
        for channel in depth_channels
        if channel.mnemonic == "TDEP"
    )
    assert {
        channel.mnemonic: channel.addressability
        for channel in depth_channels
        if channel.mnemonic in {"DEPTH", "MD"}
    } == {"DEPTH": "UNKNOWN", "MD": "UNKNOWN"}
    assert unaffected_digest == CBL_REPEAT_UNAFFECTED_CLASSIFICATIONS_SHA256
    assert all(channel.sample_availability == "NOT_CHECKED" for channel in source.channels)


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
