"""Provider-free D5-5 comparative qualification boundary.

This module defines two lane configurations for the existing provider boundary
without adding a provider, semantic engine, or model-specific authoring path.
Live execution is intentionally outside this D5-5B slice.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from scripts import nlp_d4_live_acceptance as d4
from scripts import nlp_d5_live_semantic_qualification as d5
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


@dataclass(frozen=True, slots=True)
class OpenAICompatibleReadinessProjection:
    """Sanitized readiness facts for an OpenAI-compatible non-llama lane."""

    model_catalog: tuple[str, ...]
    requested_model: str
    base_url: str
    structured_output_contract: str
    context_budget: str

    def as_dict(self) -> dict[str, object]:
        """Return only provider-appropriate, non-credential readiness facts."""
        return {
            "model_catalog": list(self.model_catalog),
            "requested_model": self.requested_model,
            "base_url": self.base_url,
            "structured_output_contract": self.structured_output_contract,
            "context_budget": self.context_budget,
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


def prepare_openai_compatible_readiness(
    *,
    lane: ComparativeLane,
    authorization: d5.D5Authorization,
    api_key_loader: Callable[[], str],
    endpoint_get: Callable[[str, str], object],
    static_preflight: Mapping[str, Any],
    provider_factory: Callable[[str], object] | None = None,
) -> d5.D5OperationalReadiness:
    """Qualify an OpenAI-compatible lane without llama.cpp-specific probes."""
    if static_preflight.get("status") != "PASS":
        raise d5.D5ReadinessError("static_preflight_failed", 0)
    token = api_key_loader()
    if not isinstance(token, str) or not token.strip():
        raise d5.D5ReadinessError("credential_unavailable", 0)
    models_url = f"{lane.base_url.rstrip('/')}/models"
    try:
        payload = endpoint_get(models_url, token)
        if not isinstance(payload, Mapping):
            raise d5.D5ReadinessError("endpoint_identity_mismatch", 1)
        data = payload.get("data")
        if not isinstance(data, list):
            raise d5.D5ReadinessError("endpoint_identity_mismatch", 1)
        model_ids = tuple(
            str(item.get("id"))
            for item in data
            if isinstance(item, Mapping) and isinstance(item.get("id"), str)
        )
        if authorization.model not in model_ids:
            raise d5.D5ReadinessError(
                "endpoint_identity_mismatch",
                1,
                mismatched_fields=("model_catalog",),
            )
    except d5.D5ReadinessError:
        raise
    except Exception:
        raise d5.D5ReadinessError("endpoint_unreachable", 1) from None
    adapter = None
    if provider_factory is not None:
        try:
            adapter = provider_factory(token)
        except Exception:
            raise d5.D5ReadinessError("provider_construction_failed", 1) from None
    return d5.D5OperationalReadiness(
        projection=OpenAICompatibleReadinessProjection(
            model_catalog=model_ids,
            requested_model=authorization.model,
            base_url=lane.base_url,
            structured_output_contract=authorization.structured_output_contract,
            context_budget=(
                str(authorization.minimum_context_size)
                if authorization.minimum_context_size
                else "provider_declared"
            ),
        ),
        endpoint_calls=("/models",),
        adapter=adapter,
        live=provider_factory is not None,
    )


def prepare_lane_readiness(
    *,
    lane: ComparativeLane,
    authorization: d5.D5Authorization,
    project_config: ProjectConfig,
    api_key_loader: Callable[[], str],
    endpoint_get: Callable[[str, str], object],
    static_preflight: Mapping[str, Any],
    provider_factory: Callable[[str], object] | None = None,
) -> d5.D5OperationalReadiness:
    """Dispatch only the approved lane-specific readiness contract."""
    if lane.readiness == "llama_cpp":
        return d5.prepare_readiness(
            authorization=authorization,
            project_config=project_config,
            api_key_loader=api_key_loader,
            endpoint_get=endpoint_get,
            static_preflight=static_preflight,
            provider_factory=provider_factory,
        )
    if lane.readiness == "openai_compat":
        return prepare_openai_compatible_readiness(
            lane=lane,
            authorization=authorization,
            api_key_loader=api_key_loader,
            endpoint_get=endpoint_get,
            static_preflight=static_preflight,
            provider_factory=provider_factory,
        )
    raise d5.D5ReadinessError("unsupported_readiness_contract", 0)


def create_lane_live_adapter(
    *,
    repo_root: Path,
    artifact_root: Path,
    api_key: str,
    lane: ComparativeLane,
    project_config: ProjectConfig,
    http_client_factory: Callable[[Callable[[object], Any]], object] | None = None,
) -> object:
    """Construct the existing D5-4 live adapter with lane-local endpoint/model."""
    return d5.create_live_adapter(
        repo_root=repo_root,
        artifact_root=artifact_root,
        api_key=api_key,
        project_config=project_config,
        http_client_factory=http_client_factory,
        base_url=lane.base_url,
        model=lane.model,
        provider_name=lane.provider,
    )


def _provider_free_authorization(
    *,
    repo_root: Path,
    lane: ComparativeLane,
    artifact_root: Path,
    implementation_checkpoint: str,
) -> d5.D5Authorization:
    """Build synthetic custody facts for an in-memory readiness rehearsal."""
    common = {
        "implementation_checkpoint": implementation_checkpoint,
        "authorization_id": f"d5-5-provider-free-{lane.lane_id}",
        "campaign_id": lane.campaign_id,
        "project_config_fingerprint_sha256": load_project_config(repo_root).fingerprint_sha256,
        "provider": lane.provider,
        "model": lane.model,
        "artifact_root": str(artifact_root),
    }
    if lane.readiness == "openai_compat":
        return d5.D5Authorization(**common)
    props = {
        "model_path": "/provider-free/qwen3.6-35b-a3b.gguf",
        "default_generation_settings": {"n_ctx": 32768, "temperature": 0.0, "top_p": 1.0},
        "build_info": "provider-free D5-5 boundary fixture",
        "total_slots": 1,
        "chat_template": "qwen3",
        "gguf_byte_identity": "NOT_AVAILABLE",
    }
    defaults = props["default_generation_settings"]
    assert isinstance(defaults, dict)
    return d5.D5Authorization(
        **common,
        endpoint_identity={
            "model_catalog": [lane.model],
            "model_path_basename": "qwen3.6-35b-a3b.gguf",
            "model_path_fingerprint_sha256": d4.sha256_text(props["model_path"]),
            "context_size": 32768,
            "build_info": props["build_info"],
            "total_slots": 1,
            "chat_template_sha256": d4.sha256_text("qwen3"),
            "runtime_defaults_sha256": d5._sha256_json(defaults),
            "structured_output_contract": "json_schema",
            "gguf_byte_identity": "NOT_AVAILABLE",
        },
        minimum_context_size=16384,
        runtime_defaults_sha256=d5._sha256_json(defaults),
    )


class _ProviderFreeBoundaryAdapter:
    """Enter shared STARTED custody without delegating to a provider."""

    observes_physical_attempts = False

    def __init__(self, lane: ComparativeLane) -> None:
        self.lane = lane
        self.logical_call_count = 0
        self._started: Callable[[dict[str, Any]], None] | None = None

    def bind_call_started(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Capture the shared runner's first logical boundary."""
        self._started = callback

    async def execute_turn(
        self,
        case: Mapping[str, Any],
        expected: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Stop before delegation after proving lane-specific custody."""
        del case, expected
        self.logical_call_count = 1
        if self._started is None:
            raise d5.D5HarnessError("shared runner did not bind logical custody")
        self._started(
            {
                "event": "logical_call_started",
                "index": 1,
                "generation_role": "planner",
                "provider": self.lane.provider,
                "model": self.lane.model,
            }
        )
        raise d5.D5TransportFailure("provider-free boundary probe")


def verify_executable_lane_boundary(
    repo_root: Path,
    *,
    implementation_checkpoint: str,
) -> dict[str, object]:
    """Exercise both lane readiness and shared STARTED custody without I/O."""
    import httpx

    config = load_project_config(repo_root)
    lanes = lane_configurations(config)
    facts: list[dict[str, object]] = []
    with TemporaryDirectory(dir=repo_root) as temporary:
        root = Path(temporary)
        for lane in lanes:
            artifact_root = root / lane.lane_id
            authorization = _provider_free_authorization(
                repo_root=repo_root,
                lane=lane,
                artifact_root=artifact_root,
                implementation_checkpoint=implementation_checkpoint,
            )
            endpoint_calls: list[str] = []

            def endpoint_get(
                url: str,
                token: str,
                *,
                lane: ComparativeLane = lane,
                endpoint_calls: list[str] = endpoint_calls,
            ) -> object:
                assert token == "provider-free-token"
                endpoint_calls.append(url)
                if lane.readiness == "llama_cpp":
                    if url == config.model_catalog_url:
                        return {"data": [{"id": lane.model}]}
                    return {
                        "model_path": "/provider-free/qwen3.6-35b-a3b.gguf",
                        "default_generation_settings": {
                            "n_ctx": 32768,
                            "temperature": 0.0,
                            "top_p": 1.0,
                        },
                        "build_info": "provider-free D5-5 boundary fixture",
                        "total_slots": 1,
                        "chat_template": "qwen3",
                        "gguf_byte_identity": "NOT_AVAILABLE",
                    }
                return {"data": [{"id": lane.model}]}

            readiness = prepare_lane_readiness(
                lane=lane,
                authorization=authorization,
                project_config=config,
                api_key_loader=lambda: "provider-free-token",
                endpoint_get=endpoint_get,
                static_preflight={"status": "PASS"},
            )
            expected_endpoint_calls = (
                [config.model_catalog_url, config.props_url]
                if lane.readiness == "llama_cpp"
                else [f"{lane.base_url}/models"]
            )
            if endpoint_calls != expected_endpoint_calls:
                raise d5.D5HarnessError(f"{lane.lane_id} readiness call sequence drifted")
            if lane.readiness == "openai_compat" and config.props_url in endpoint_calls:
                raise d5.D5HarnessError("OpenAI-compatible readiness called /props")

            # Construction is exercised through the existing provider factory and
            # existing D5-4 live adapter; neither operation sends a request.
            create_lane_provider_backend(
                repo_root=repo_root,
                lane=lane,
                api_key="provider-free-token",
            )
            clients: list[httpx.AsyncClient] = []

            def client_factory(
                observer: Callable[[object], Any],
                *,
                clients: list[httpx.AsyncClient] = clients,
            ) -> httpx.AsyncClient:
                client = httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda request: httpx.Response(500, request=request)
                    ),
                    event_hooks={"request": [observer]},
                )
                clients.append(client)
                return client

            live_adapter = create_lane_live_adapter(
                repo_root=repo_root,
                artifact_root=artifact_root,
                api_key="provider-free-token",
                lane=lane,
                project_config=config,
                http_client_factory=client_factory,
            )
            runner = d5.D5CampaignRunner(
                repo_root=repo_root,
                authorization=authorization,
                paths=d5.EvidencePaths(artifact_root, lane.campaign_id),
                readiness=readiness,
                provenance={
                    "implementation_checkpoint": implementation_checkpoint,
                    "lane_id": lane.lane_id,
                },
            )
            result = asyncio.run(runner.run(_ProviderFreeBoundaryAdapter(lane)))
            for client in clients:
                asyncio.run(client.aclose())
            if result["decision"] != "INCONCLUSIVE" or result["completed_turns"] != 0:
                raise d5.D5HarnessError(f"{lane.lane_id} did not fail closed before delegation")
            facts.append(
                {
                    "lane_id": lane.lane_id,
                    "readiness": lane.readiness,
                    "endpoint_calls": endpoint_calls,
                    "provider_backend": "existing_factory",
                    "live_adapter": type(live_adapter).__name__,
                    "shared_runner": type(runner).__name__,
                    "decision": result["decision"],
                    "provider_calls": 0,
                    "model_calls": 0,
                }
            )
    return {"lanes": facts, "provider_calls": 0, "model_calls": 0}


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
    """Run provider-free D5-5B contract and executable-boundary checks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--implementation-checkpoint", required=True)
    args = parser.parse_args()
    result = verify_provider_free_contract(
        args.repo_root.resolve(),
        implementation_checkpoint=args.implementation_checkpoint,
    )
    result["executable_lane_boundary"] = verify_executable_lane_boundary(
        args.repo_root.resolve(),
        implementation_checkpoint=args.implementation_checkpoint,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
