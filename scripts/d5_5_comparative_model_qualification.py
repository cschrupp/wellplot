"""Provider-free D5-5 comparative qualification boundary.

This module defines two lane configurations for the existing provider boundary
without adding a provider, semantic engine, or model-specific authoring path.
Live execution is intentionally outside this D5-5B slice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts import nlp_d4_live_acceptance as d4
from wellplot.agent.composition import create_provider_backend
from wellplot.agent.providers._v2_client import load_api_key
from wellplot.project_config import ProjectConfig, load_project_config

D5_5_AUTHORITY = "WELLPLOT-D5-5-COMPARATIVE-QUALIFICATION-DESIGN-AUTH-001"
D5_5_BASELINE = "63aa1f9e0fecbfd15abefa20ab57e8e3d366a6a2"
D5_5_EXPERIMENT = "d5-5-post-hardening-compare-001"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
LUNA_MODEL = "openai/gpt-6-luna"
MAX_LOGICAL_CALLS = 45
MAX_PHYSICAL_ATTEMPTS = 135
GENERATION_TIMEOUT_SECONDS = 900.0
CONCURRENCY = 1
CANONICAL_ENGINE_ENTRYPOINT = "wellplot.agent.composition:create_canonical_compile_facade"
HISTORICAL_CAMPAIGN = "d5-4-live-qwen-001"


@dataclass(frozen=True, slots=True)
class ComparativeLane:
    """Provider configuration that varies without changing semantic routing."""

    lane_id: str
    model: str
    base_url: str
    readiness: str
    campaign_id: str
    artifact_root: str
    credential_env_names: tuple[str, ...]
    credential_file_names: tuple[str, ...]
    canonical_engine: str = CANONICAL_ENGINE_ENTRYPOINT
    provider: str = "openai_compat"

    def provider_arguments(self, repo_root: Path, api_key: str | None = None) -> dict[str, object]:
        """Return arguments for the existing provider factory only."""
        return {
            "provider": self.provider,
            "model": self.model,
            "server_root": repo_root,
            "api_key": api_key,
            "base_url": self.base_url,
            "timeout": GENERATION_TIMEOUT_SECONDS,
        }


def lane_configurations(project_config: ProjectConfig) -> tuple[ComparativeLane, ...]:
    """Build the two approved lanes from existing runtime configuration."""
    return (
        ComparativeLane(
            lane_id="qwen",
            model="qwen3.6-35b-a3b",
            base_url=project_config.openai_compat_base_url,
            readiness="llama_cpp",
            campaign_id="d5-5-qwen-001",
            artifact_root="workspace/evaluations/d5-5/qwen",
            credential_env_names=("OPENAI_COMPAT_API_KEY", "OPENAI_API_KEY"),
            credential_file_names=(
                "LLAMA_CPP_API_KEY.txt",
                "OPENAI_COMPAT_API_KEY.txt",
                "openai_compat_api_key.txt",
            ),
        ),
        ComparativeLane(
            lane_id="luna",
            model=LUNA_MODEL,
            base_url=OPENROUTER_BASE_URL,
            readiness="openai_compat",
            campaign_id="d5-5-luna-001",
            artifact_root="workspace/evaluations/d5-5/luna",
            credential_env_names=("OPENROUTER_API_KEY", "OPENAI_API_KEY"),
            credential_file_names=("OPENROUTER_API_KEY.txt", "OPENAI_API_KEY.txt"),
        ),
    )


def validate_lane_configurations(
    lanes: tuple[ComparativeLane, ...],
) -> dict[str, object]:
    """Fail closed if lane identity or custody namespaces can collide."""
    if tuple(lane.lane_id for lane in lanes) != ("qwen", "luna"):
        raise ValueError("D5-5 requires exactly the ordered Qwen and Luna lanes")
    if len({lane.campaign_id for lane in lanes}) != len(lanes):
        raise ValueError("comparative campaign IDs must be distinct")
    if len({lane.artifact_root for lane in lanes}) != len(lanes):
        raise ValueError("comparative artifact roots must be distinct")
    if any(lane.campaign_id == HISTORICAL_CAMPAIGN for lane in lanes):
        raise ValueError("historical D4 campaign cannot be reused")
    if any(lane.canonical_engine != CANONICAL_ENGINE_ENTRYPOINT for lane in lanes):
        raise ValueError("all lanes must use the canonical composition root")
    if any(lane.provider != "openai_compat" for lane in lanes):
        raise ValueError("D5-5 lanes must use the existing OpenAI-compatible boundary")
    if any(lane.readiness not in {"llama_cpp", "openai_compat"} for lane in lanes):
        raise ValueError("unsupported provider-specific readiness contract")
    return {
        "lane_ids": [lane.lane_id for lane in lanes],
        "campaign_ids": [lane.campaign_id for lane in lanes],
        "artifact_roots": [lane.artifact_root for lane in lanes],
        "canonical_engine": CANONICAL_ENGINE_ENTRYPOINT,
        "logical_call_ceiling_per_lane": MAX_LOGICAL_CALLS,
        "physical_attempt_ceiling_per_lane": MAX_PHYSICAL_ATTEMPTS,
        "concurrency": CONCURRENCY,
        "generation_timeout_seconds": GENERATION_TIMEOUT_SECONDS,
        "provider_calls": 0,
        "model_calls": 0,
    }


def load_lane_api_key(repo_root: Path, lane: ComparativeLane) -> str:
    """Load a lane credential through existing provider-v2 conventions."""
    return load_api_key(
        server_root=repo_root,
        api_key=None,
        env_var_names=lane.credential_env_names,
        env_file_keys=lane.credential_env_names,
        text_file_names=lane.credential_file_names,
        missing_message=f"{lane.lane_id} credential is not configured",
    )


def create_lane_provider_backend(
    *,
    repo_root: Path,
    lane: ComparativeLane,
    api_key: str,
) -> object:
    """Delegate both lanes to the existing provider-v2 factory."""
    return create_provider_backend(**lane.provider_arguments(repo_root, api_key))  # type: ignore[arg-type]


def _sha256_file(path: Path) -> str:
    """Hash one custody file without retaining its contents."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(repo_root: Path, *arguments: str) -> str:
    """Read one Git fact from the isolated qualification checkout."""
    return subprocess.check_output(["git", *arguments], cwd=repo_root, text=True).strip()


def verify_provider_free_contract(
    repo_root: Path,
    *,
    implementation_checkpoint: str,
    run_attestation: bool = True,
) -> dict[str, object]:
    """Verify shared D4/D5 custody and the accepted post-hardening baseline."""
    current = _git(repo_root, "rev-parse", "HEAD")
    if current != implementation_checkpoint:
        raise ValueError("implementation checkpoint does not match the checkout")
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", D5_5_BASELINE, current],
        cwd=repo_root,
        check=False,
    ).returncode:
        raise ValueError("accepted D5-5 baseline is not an ancestor of the checkout")
    cases = d4.load_cases(repo_root)
    gold = d4.load_gold(repo_root)
    if tuple(case["turn_id"] for case in cases) != d5_turn_ids():
        raise ValueError("D5-5 population order drifted")
    if len(gold["cases"]) != 9:
        raise ValueError("D5-5 gold population is not exactly nine turns")
    if d4.sha256_file(repo_root / d4.CASES_PATH) != d4.FROZEN_CASES_SHA256:
        raise ValueError("D4 cases fixture drifted")
    if d4.sha256_file(repo_root / d4.GOLD_PATH) != d4.FROZEN_GOLD_SHA256:
        raise ValueError("D4 gold fixture drifted")
    if d4.sha256_file(repo_root / d4.UV_LOCK_PATH) != d4.FROZEN_UV_LOCK_SHA256:
        raise ValueError("uv.lock drifted")
    source_hashes = {
        d4.SOURCE_RELATIVE.as_posix(): d4.SOURCE_SHA256,
        "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis": (
            "3ceb9100fd654d710155672a50a9e0f24ce9705db6ef8e424140f29bd02131f7"
        ),
        "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis": (
            "a4a2e91b495172079fc47bc2e9c936f0ab60c9845bbed8e65bf56555a5e82640"
        ),
    }
    for relative, expected in source_hashes.items():
        if _sha256_file(repo_root / relative) != expected:
            raise ValueError(f"source custody drifted: {relative}")
    config = load_project_config(repo_root)
    lanes = lane_configurations(config)
    lane_facts = validate_lane_configurations(lanes)
    if run_attestation:
        subprocess.run(
            [
                sys.executable,
                "scripts/d5_single_engine_attestation.py",
                "--repo-root",
                str(repo_root),
                "--check",
            ],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    return {
        "implementation_checkpoint": current,
        "accepted_baseline": D5_5_BASELINE,
        "population": {"turns": 9, "turn_ids": list(d5_turn_ids())},
        "cases_sha256": d4.FROZEN_CASES_SHA256,
        "gold_sha256": d4.FROZEN_GOLD_SHA256,
        "uv_lock_sha256": d4.FROZEN_UV_LOCK_SHA256,
        "lanes": [_lane_dict(lane) for lane in lanes],
        "lane_contract": lane_facts,
        "single_engine_attestation": "PASS" if run_attestation else "NOT_RUN",
        "provider_calls": 0,
        "model_calls": 0,
    }


def d5_turn_ids() -> tuple[str, ...]:
    """Return the immutable D4/D5 nine-turn order."""
    return (
        "D4-C01:C01",
        "D4-L01:T1",
        "D4-L01:T2",
        "D4-L01:T3",
        "D4-L01:T4",
        "D4-L02:T1",
        "D4-L02:T2",
        "D4-L03:C01",
        "D4-L04:C01",
    )


def _lane_dict(lane: ComparativeLane) -> dict[str, object]:
    """Project lane metadata without credentials or provider responses."""
    return {
        "lane_id": lane.lane_id,
        "provider": lane.provider,
        "model": lane.model,
        "base_url": lane.base_url,
        "readiness": lane.readiness,
        "campaign_id": lane.campaign_id,
        "artifact_root": lane.artifact_root,
        "canonical_engine": lane.canonical_engine,
    }


def main() -> int:
    """Run only the provider-free D5-5B contract checks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--implementation-checkpoint", required=True)
    args = parser.parse_args()
    result = verify_provider_free_contract(
        args.repo_root.resolve(),
        implementation_checkpoint=args.implementation_checkpoint,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
