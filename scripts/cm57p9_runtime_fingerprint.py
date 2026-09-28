"""Provider-free llama.cpp runtime fingerprinting for CM-57P9A.

The helper records bounded identity and launch metadata only. It never calls
the inference endpoint, reads the environment wholesale, or modifies a
running server.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

FINGERPRINT_VERSION = "cm57p9.runtime-fingerprint.v1"
UNKNOWN = None
_FLAG_ALIASES = {
    "context_size": ("--ctx-size", "-c"),
    "batch_size": ("--batch-size", "-b"),
    "ubatch_size": ("--ubatch-size", "-ub"),
    "parallel_slots": ("--parallel", "-np"),
    "threads": ("--threads", "-t"),
    "threads_batch": ("--threads-batch", "-tb"),
    "n_gpu_layers": ("--n-gpu-layers", "-ngl"),
    "flash_attention": ("--flash-attn", "-fa"),
    "main_gpu": ("--main-gpu",),
    "tensor_split": ("--tensor-split",),
    "seed_if_configured": ("--seed",),
}
_REQUIRED_KEYS = (
    "fingerprint_version",
    "endpoint",
    "model_api_label",
    "model_file_name",
    "model_sha256",
    "model_file_bytes",
    "llama_binary_name",
    "llama_binary_sha256",
    "llama_version",
    "llama_build_commit_if_available",
    "server_process_id",
    "server_process_start_time",
    "context_size",
    "batch_size",
    "ubatch_size",
    "parallel_slots",
    "continuous_batching",
    "threads",
    "threads_batch",
    "n_gpu_layers",
    "flash_attention",
    "main_gpu",
    "tensor_split",
    "seed_if_configured",
    "gpu_name",
    "gpu_driver_version",
    "cuda_runtime_or_build_version_if_available",
    "launch_arguments_sha256",
)


def _canonical_json(value: object) -> str:
    """Serialize fingerprint values deterministically."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_file(path: Path) -> str | None:
    """Hash one file, returning unavailable for missing/unreadable inputs."""
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except (OSError, ValueError):
        return UNKNOWN


def _file_size(path: Path) -> int | None:
    """Return one file size without retaining its path."""
    try:
        return path.stat().st_size
    except OSError:
        return UNKNOWN


def _read_cmdline(pid: int) -> list[str] | None:
    """Read one process command line without retaining it in the result."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return UNKNOWN
    return [item.decode("utf-8", errors="replace") for item in raw.split(b"\0") if item]


def _process_start_time(pid: int) -> int | None:
    """Return Linux process start ticks as a stable same-process identity."""
    try:
        stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return UNKNOWN
    closing = stat_text.rfind(")")
    if closing < 0:
        return UNKNOWN
    fields = stat_text[closing + 2 :].split()
    try:
        return int(fields[19])
    except (IndexError, ValueError):
        return UNKNOWN


def _flag_value(arguments: list[str] | None, names: tuple[str, ...]) -> str | None:
    """Return one bounded command-line flag value."""
    if not arguments:
        return UNKNOWN
    for index, argument in enumerate(arguments):
        for name in names:
            if argument == name and index + 1 < len(arguments):
                return arguments[index + 1]
            if argument.startswith(name + "="):
                return argument.split("=", 1)[1]
    return UNKNOWN


def _runtime_settings(arguments: list[str] | None) -> dict[str, object]:
    """Project known llama-server settings without exposing command arguments."""
    settings: dict[str, object] = {}
    for field_name, names in _FLAG_ALIASES.items():
        settings[field_name] = _flag_value(arguments, names)
    settings["continuous_batching"] = (
        "--cont-batching" in arguments if arguments is not None else UNKNOWN
    )
    return settings


def _safe_version(binary: Path) -> tuple[str | None, str | None]:
    """Read a bounded version line and optional build commit from llama-server."""
    try:
        completed = subprocess.run(
            [str(binary), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN, UNKNOWN
    output = (completed.stdout or completed.stderr).strip()
    first_line = output.splitlines()[0][:256] if output else None
    commit = None
    if output:
        match = re.search(r"(?:commit|build)[^0-9a-f]*([0-9a-f]{7,40})", output, re.I)
        commit = match.group(1) if match else None
    return first_line, commit


def _gpu_metadata() -> dict[str, str | None]:
    """Read bounded NVIDIA identity metadata when the utility is available."""
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return {"gpu_name": UNKNOWN, "gpu_driver_version": UNKNOWN}
    line = next((item.strip() for item in completed.stdout.splitlines() if item.strip()), "")
    if not line:
        return {"gpu_name": UNKNOWN, "gpu_driver_version": UNKNOWN}
    name, _, driver = line.partition(",")
    return {"gpu_name": name.strip() or UNKNOWN, "gpu_driver_version": driver.strip() or UNKNOWN}


def build_fingerprint(
    *,
    server_pid: int,
    llama_binary: Path,
    model_file: Path,
    endpoint: str,
    model_api_label: str,
) -> dict[str, object]:
    """Build one provider-free fingerprint from supplied host paths."""
    arguments = _read_cmdline(server_pid)
    version, build_commit = _safe_version(llama_binary)
    gpu = _gpu_metadata()
    settings = _runtime_settings(arguments)
    fingerprint: dict[str, object] = {
        "fingerprint_version": FINGERPRINT_VERSION,
        "captured_at": datetime.now(UTC).isoformat(),
        "endpoint": endpoint,
        "model_api_label": model_api_label,
        "model_file_name": model_file.name,
        "model_sha256": _sha256_file(model_file),
        "model_file_bytes": _file_size(model_file),
        "llama_binary_name": llama_binary.name,
        "llama_binary_sha256": _sha256_file(llama_binary),
        "llama_version": version,
        "llama_build_commit_if_available": build_commit,
        "server_process_id": server_pid,
        "server_process_start_time": _process_start_time(server_pid),
        **settings,
        **gpu,
        "cuda_runtime_or_build_version_if_available": None,
        "launch_arguments_sha256": (
            hashlib.sha256(_canonical_json(arguments).encode("utf-8")).hexdigest()
            if arguments is not None
            else UNKNOWN
        ),
    }
    return fingerprint


def validate_fingerprint(value: object) -> tuple[bool, list[str]]:
    """Validate the explicit fingerprint shape and required keys."""
    if not isinstance(value, dict):
        return False, ["fingerprint_not_object"]
    reasons = [f"missing_{key}" for key in _REQUIRED_KEYS if key not in value]
    if value.get("fingerprint_version") != FINGERPRINT_VERSION:
        reasons.append("fingerprint_version_mismatch")
    endpoint = value.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.strip():
        reasons.append("endpoint_invalid")
    process_id = value.get("server_process_id")
    if process_id is not None and (isinstance(process_id, bool) or not isinstance(process_id, int)):
        reasons.append("process_id_invalid")
    return not reasons, sorted(set(reasons))


def compare_fingerprints(pre: dict[str, object], post: dict[str, object]) -> list[str]:
    """Return changed identity/runtime fields, excluding capture time."""
    keys = tuple(key for key in _REQUIRED_KEYS if key != "fingerprint_version")
    return [key for key in keys if pre.get(key) != post.get(key)]


def _parser() -> argparse.ArgumentParser:
    """Build the metadata-only CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--llama-binary", type=Path, required=True)
    parser.add_argument("--model-file", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model-api-label", default="qwen3.6-35b-a3b")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Capture one fingerprint without contacting the inference endpoint."""
    args = _parser().parse_args(argv)
    payload = build_fingerprint(
        server_pid=args.server_pid,
        llama_binary=args.llama_binary,
        model_file=args.model_file,
        endpoint=args.endpoint,
        model_api_label=args.model_api_label,
    )
    valid, reasons = validate_fingerprint(payload)
    if not valid:
        raise SystemExit(f"Invalid runtime fingerprint: {', '.join(reasons)}")
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
