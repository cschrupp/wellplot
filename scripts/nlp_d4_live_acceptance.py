"""Provider-free D4 live-acceptance harness and future-live interlocks.

The default command path performs only deterministic preflight checks.  Live
execution is deliberately isolated behind an explicit caller-owned backend so
that D4A tests cannot accidentally construct a real provider.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import os
import subprocess
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from wellplot.agent.providers.base import (
    ModelBackendProtocol,
    ProgramGenerationRequest,
    ProgramGenerationResult,
    ProviderFailureCategory,
    ProviderMetrics,
    ProviderRequestError,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.io import load_dlis, load_las
from wellplot.model.authoring import AuthoringDocumentSpec

EXPERIMENT_VERSION = "WELLPLOT-NLP-D4A"
PRODUCTION_BASELINE = "2c8e851fcd8b315e5d1861652a97984202db7488"
AUTHORIZED_DESIGN_CHECKPOINT = "8618c3ef2207236ad50d5fc576cf1c96badbfb95"
EXPECTED_PROVIDER = "openai"
EXPECTED_MODEL = "gpt-5.4"
EXPECTED_OPENAI_VERSION = "2.34.0"
EXPECTED_SDK_MAX_RETRIES = 2
MAX_LOGICAL_CALLS = 45
SOURCE_RELATIVE = Path("workspace/data/30-23a-3 8117_d.las")
SOURCE_SIZE = 5_987_785
SOURCE_SHA256 = "7e6c69c65713dc33303362ab91b767eb06371fd24a31856add8650e6d3bee1a9"
SOURCE_REQUIRED_CHANNELS = frozenset({"GR", "CALI", "ILD", "ILM", "MSFL", "NPHI"})
SOURCE_FORBIDDEN_CHANNELS = frozenset({"RT"})
CASES_PATH = Path("tests/fixtures/nlp_d4_live_cases.json")
GOLD_PATH = Path("tests/fixtures/nlp_d4_live_gold.json")
HARNESS_SOURCE_PATH = Path("scripts/nlp_d4_live_acceptance.py")
UV_LOCK_PATH = Path("uv.lock")
STATE_RELATIVE = Path("workspace/evaluations/d4-live-acceptance/d4-live-v1.state.json")
JOURNAL_RELATIVE = Path("workspace/evaluations/d4-live-acceptance/d4-live-v1.jsonl")
FROZEN_CASES_SHA256 = "f710581831b29dcd7ab321dd91afc5dd2b4e40b729161f969f8802f3f7a84298"
FROZEN_GOLD_SHA256 = "795f9280d201ee91365b1575737fa26ca782b65699debf32cf21e020faaf33e2"
FROZEN_UV_LOCK_SHA256 = "0076359f8f68da82efa5e800d61ef38032fad72742340f51b78b6d8e969ff1b6"
PRODUCTION_COMPONENT_PATHS = (
    "src/wellplot/agent/code_mode/planner.py",
    "src/wellplot/agent/code_mode/workflow.py",
    "src/wellplot/agent/code_mode/capability_safety.py",
    "src/wellplot/agent/code_mode/report_boundary_safety.py",
    "src/wellplot/agent/code_mode/section_leaf_safety.py",
    "src/wellplot/agent/code_mode/enrichment.py",
    "src/wellplot/agent/code_mode/report_worker.py",
    "src/wellplot/agent/code_mode/program_worker.py",
    "src/wellplot/agent/code_mode/repair.py",
    "src/wellplot/agent/providers/base.py",
    "src/wellplot/agent/providers/openai.py",
    "src/wellplot/agent/providers/openai_v2.py",
    "src/wellplot/agent/providers/openai_program_v2.py",
    "src/wellplot/agent/direct_notebook.py",
    "src/wellplot/authoring.py",
    "src/wellplot/authoring_reconciler.py",
    "src/wellplot/authoring_executor.py",
    "src/wellplot/authoring_service.py",
    "src/wellplot/agent/operation_executor.py",
    "scripts/verify_cbl_packet.py",
    "scripts/verify_las_revision.py",
)
FROZEN_PRODUCTION_COMPONENT_SHA256 = {
    "src/wellplot/agent/code_mode/planner.py": (
        "1e2858b4663996ccacaf1c42979fc62fe988ba7501d6ec63e00911e6cdc86740"
    ),
    "src/wellplot/agent/code_mode/workflow.py": (
        "1a142cb614409fbeb55ebf77b91714ef8a6be83634f153eac25bf104d8b871da"
    ),
    "src/wellplot/agent/code_mode/capability_safety.py": (
        "09eaa16eb3b540c785573233092f7650569158a03ce9747d7b4501302a5e8be7"
    ),
    "src/wellplot/agent/code_mode/report_boundary_safety.py": (
        "86c05471dcbb0f71035ea8eca7eca59cae4f9f9c8665d59d7fe39befe022107f"
    ),
    "src/wellplot/agent/code_mode/section_leaf_safety.py": (
        "8d7890b9c18e4ffcf8a87f474439ce6da0f07338126ea4052201239b8936347d"
    ),
    "src/wellplot/agent/code_mode/enrichment.py": (
        "78cfec5e1f704dcd4218ff5047b0d29282ea154ed668b5244f5c6a40d709dd0b"
    ),
    "src/wellplot/agent/code_mode/report_worker.py": (
        "2048c9c7b0c4a63377daee6911a3b249b503d886c5981d144997d3d0534f463a"
    ),
    "src/wellplot/agent/code_mode/program_worker.py": (
        "52fe50ba7a18af0f9efd30d76068572f831076d35682e909692f64de488b3f86"
    ),
    "src/wellplot/agent/code_mode/repair.py": (
        "c1470b491c442b5e743a0421a49046cccf8e3f12635293c40b44ff0864a53804"
    ),
    "src/wellplot/agent/providers/base.py": (
        "4c14afc1e6e53faef1ef99266059b7b88b6c4dec4bfb5a4768ca5b36efc3f049"
    ),
    "src/wellplot/agent/providers/openai.py": (
        "0e49f227ee03f761f3a215f013feb1ab40c542b28ac10e428159065c9ab29a91"
    ),
    "src/wellplot/agent/providers/openai_v2.py": (
        "a3548b5d373767abe614c0600194b9558b1057e1caa07b17df948956cc5c0759"
    ),
    "src/wellplot/agent/providers/openai_program_v2.py": (
        "e68b4bb63da930b4eb5c399741bfd486a4a8563d405a505d5aafefb86c6bc062"
    ),
    "src/wellplot/agent/direct_notebook.py": (
        "6a4915ee395a599cf5fc74df151bc8ea025990b5b3fdf003cf9fe8b3624a44cc"
    ),
    "src/wellplot/authoring.py": (
        "0c6c0d04c6d71fcc07c7fa6d130c1ff9e026fbd7ae8dc1bb463d50d009caa99b"
    ),
    "src/wellplot/authoring_reconciler.py": (
        "1c599c6c6e3945816fd7114b5b35631267f85fd77ff75a7bced87a38fb891034"
    ),
    "src/wellplot/authoring_executor.py": (
        "f1218bbddf706751e6cbb019017ed9efbae60d9909b1c08660dbc9edda0eb28b"
    ),
    "src/wellplot/authoring_service.py": (
        "458d2c1c54e7013c3c66bd2196830849148f68364f217df1b95b276a776da954"
    ),
    "src/wellplot/agent/operation_executor.py": (
        "b52ab3eaae90a23092d584687caf5a53a742ff4c263bee763eee97e342b878ee"
    ),
    "scripts/verify_cbl_packet.py": (
        "528a0ed80d6eb43ddf74188fcc10038e25a696b5f6fd792eaeddd5bc96516613"
    ),
    "scripts/verify_las_revision.py": (
        "abf9f513a3f0b35c03d70f8bc429204a2cc6929cd459452e223ee7785492c004"
    ),
}
SECRET_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "authorization_headers",
        "credentials",
        "environment_dump",
        "raw_provider_response",
        "raw_generated_program",
        "raw_structured_payload",
        "hidden_reasoning",
    }
)
SECRET_MARKERS = ("bearer ", "api_key", "openai_api_key", "authorization:")


class PreflightError(RuntimeError):
    """Raised when D4 cannot safely establish its frozen contract."""


class CallCapExceeded(RuntimeError):
    """Raised before delegating logical generation call 46."""


@dataclass(frozen=True, slots=True)
class FrozenAuthorization:
    """External D4B authorization facts that must not be self-derived."""

    accepted_checkpoint: str
    harness_source_sha256: str
    cases_fixture_sha256: str
    gold_fixture_sha256: str
    uv_lock_sha256: str
    production_component_sha256: Mapping[str, str]
    source_sha256: Mapping[str, str]
    provider: str = EXPECTED_PROVIDER
    model: str = EXPECTED_MODEL
    openai_version: str = EXPECTED_OPENAI_VERSION
    sdk_max_retries: int = EXPECTED_SDK_MAX_RETRIES

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> FrozenAuthorization:
        """Build authorization facts while rejecting missing identity fields."""
        required = {
            "accepted_checkpoint",
            "harness_source_sha256",
            "cases_fixture_sha256",
            "gold_fixture_sha256",
            "uv_lock_sha256",
            "production_component_sha256",
            "source_sha256",
        }
        missing = required - set(value)
        if missing:
            raise PreflightError(f"authorization is missing fields: {sorted(missing)!r}")
        return cls(
            accepted_checkpoint=str(value["accepted_checkpoint"]),
            harness_source_sha256=str(value["harness_source_sha256"]),
            cases_fixture_sha256=str(value["cases_fixture_sha256"]),
            gold_fixture_sha256=str(value["gold_fixture_sha256"]),
            uv_lock_sha256=str(value["uv_lock_sha256"]),
            production_component_sha256=dict(value["production_component_sha256"]),
            source_sha256=dict(value["source_sha256"]),
            provider=str(value.get("provider", EXPECTED_PROVIDER)),
            model=str(value.get("model", EXPECTED_MODEL)),
            openai_version=str(value.get("openai_version", EXPECTED_OPENAI_VERSION)),
            sdk_max_retries=int(value.get("sdk_max_retries", EXPECTED_SDK_MAX_RETRIES)),
        )


@dataclass(frozen=True, slots=True)
class SourcePreflight:
    """Bounded source facts retained by the D4A result record."""

    relative_path: str
    size: int
    sha256: str
    channel_inventory: tuple[str, ...]
    required_channels_present: bool
    forbidden_channels_absent: bool


@dataclass(frozen=True, slots=True)
class LogicalCall:
    """Redacted observation at the WellPlot backend boundary."""

    index: int
    operation: str
    provider: str
    model: str
    temperature: float | None
    max_output_tokens: int | None
    outcome: str
    category: str | None
    metrics: dict[str, int | float | None]


@dataclass
class CountingBackend:
    """Count logical generation calls without adding retries or payload capture."""

    delegate: ModelBackendProtocol
    provider: str = EXPECTED_PROVIDER
    model: str = EXPECTED_MODEL
    max_calls: int = MAX_LOGICAL_CALLS
    call_started: Callable[[dict[str, Any]], None] | None = None
    calls: list[LogicalCall] = field(default_factory=list)

    def _before(self, operation: str, request: object) -> int:
        if len(self.calls) >= self.max_calls:
            raise CallCapExceeded(
                f"logical generation call {self.max_calls + 1} rejected before delegation"
            )
        index = len(self.calls) + 1
        temperature = getattr(request, "temperature", None)
        max_output_tokens = getattr(request, "max_output_tokens", None)
        if operation not in {"structured", "program"}:
            raise ValueError(f"unsupported operation: {operation}")
        if operation == "structured":
            if temperature != 0.0 or max_output_tokens is not None:
                raise PreflightError("planner request controls drifted")
        elif temperature is not None or max_output_tokens is not None:
            raise PreflightError("worker request controls drifted")
        if self.call_started is not None:
            self.call_started(
                {
                    "event": "logical_call_started",
                    "index": index,
                    "operation": operation,
                    "provider": self.provider,
                    "model": self.model,
                    "temperature": temperature,
                    "max_output_tokens": max_output_tokens,
                }
            )
        return index

    def _record(
        self,
        *,
        index: int,
        operation: str,
        request: object,
        outcome: str,
        category: str | None,
        metrics: ProviderMetrics | None,
    ) -> None:
        self.calls.append(
            LogicalCall(
                index=index,
                operation=operation,
                provider=self.provider,
                model=self.model,
                temperature=getattr(request, "temperature", None),
                max_output_tokens=getattr(request, "max_output_tokens", None),
                outcome=outcome,
                category=category,
                metrics={} if metrics is None else metrics.public_metadata(),
            )
        )

    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
        *,
        response_model: type[Any],
    ) -> StructuredGenerationResult[Any]:
        """Delegate one structured call and record only bounded metadata."""
        index = self._before("structured", request)
        try:
            result = await self.delegate.generate_structured(
                request,
                response_model=response_model,
            )
        except ProviderRequestError as error:
            self._record(
                index=index,
                operation="structured",
                request=request,
                outcome="failure",
                category=error.category.value,
                metrics=None,
            )
            raise
        except Exception:
            self._record(
                index=index,
                operation="structured",
                request=request,
                outcome="failure",
                category=ProviderFailureCategory.INVALID_RESPONSE.value,
                metrics=None,
            )
            raise
        self._record(
            index=index,
            operation="structured",
            request=request,
            outcome="success",
            category=None,
            metrics=result.metrics,
        )
        return result

    async def generate_program(
        self,
        request: ProgramGenerationRequest,
    ) -> ProgramGenerationResult:
        """Delegate one program call and retain no generated source text."""
        index = self._before("program", request)
        try:
            result = await self.delegate.generate_program(request)
        except ProviderRequestError as error:
            self._record(
                index=index,
                operation="program",
                request=request,
                outcome="failure",
                category=error.category.value,
                metrics=None,
            )
            raise
        except Exception:
            self._record(
                index=index,
                operation="program",
                request=request,
                outcome="failure",
                category=ProviderFailureCategory.INVALID_RESPONSE.value,
                metrics=None,
            )
            raise
        self._record(
            index=index,
            operation="program",
            request=request,
            outcome="success",
            category=None,
            metrics=result.metrics,
        )
        return result


def canonical_json(value: object) -> str:
    """Serialize one evidence value deterministically."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    """Return one SHA-256 digest."""
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    """Hash normalized UTF-8 request text."""
    normalized = "\n".join(line.rstrip() for line in value.replace("\r\n", "\n").splitlines())
    return sha256_bytes(normalized.strip().encode("utf-8"))


def sha256_file(path: Path) -> str:
    """Hash one file without retaining its contents."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_ACCEPTED_D1_D3_REQUESTS = (
    "Change the Gamma Ray curve scale to a linear scale from 10 to 100.",
    'Change the report title to "Gamma Ray Quality Control Review".',
    'In the Main Log section, add a new normal track titled "Caliper QC" at the end, '
    '28 mm wide, and plot the CALI curve on it labeled "Caliper QC" with a linear scale '
    "from 6 to 12.",
    "In the Main Log section, on the GR track, fill from the Gamma Ray curve to its "
    "lower scale limit using light gray (#d9d9d9) at 25% opacity.",
    'In the Main Log section, add a normal track titled "Neutron" and plot NPHI '
    "from missing.las on it.",
    "In the Main Log section, change the Gamma Ray curve scale to 10–100.",
    'In the Main Log section, add a normal track titled "Neutron", 28 mm wide, '
    'and plot NPHI from fixture.las on it labeled "Neutron" with a linear scale '
    "from 0 to 45.",
)


def accepted_d1_d3_request_hashes(repo_root: Path) -> frozenset[str]:
    """Return exact accepted D1-D3 request identities for the unseen guard."""
    requests = list(_ACCEPTED_D1_D3_REQUESTS)
    d3_path = repo_root / "tests/fixtures/agentic_cbl/frozen_prompt.txt"
    if d3_path.is_file():
        d3_request = d3_path.read_text(encoding="utf-8")
        for source_name in (
            "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis",
            "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis",
        ):
            d3_request = d3_request.replace(source_name, Path(source_name).name)
        requests.append(d3_request)
    return frozenset(sha256_text(request) for request in requests)


def assert_unseen_requests(repo_root: Path, cases: Sequence[Mapping[str, Any]]) -> None:
    """Reject any D4 request that reuses an accepted D1-D3 request exactly."""
    accepted = accepted_d1_d3_request_hashes(repo_root)
    reused = [case.get("turn_id") for case in cases if case.get("request_sha256") in accepted]
    if reused:
        raise PreflightError(f"D4 reuses accepted D1-D3 requests: {reused!r}")


def assert_provider_prompt_excludes_gold(prompt: str, gold: Mapping[str, Any]) -> None:
    """Reject evaluator gold leakage into a future provider prompt."""
    serialized_gold = canonical_json(gold)
    if serialized_gold in prompt:
        raise PreflightError("provider prompt contains the serialized D4 gold object")
    if "D4 LAS Acceptance Seed" in prompt or '"expected_outcome"' in prompt:
        raise PreflightError("provider prompt contains D4 evaluator metadata")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PreflightError(f"expected JSON object: {path}")
    return value


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True).strip()


def load_cases(repo_root: Path) -> list[dict[str, Any]]:
    """Load and authenticate the exact ordered nine-turn population."""
    payload = _load_json(repo_root / CASES_PATH)
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 9:
        raise PreflightError("D4 requires exactly nine frozen turns")
    expected_order = [
        "D4-C01:C01",
        "D4-L01:T1",
        "D4-L01:T2",
        "D4-L01:T3",
        "D4-L01:T4",
        "D4-L02:T1",
        "D4-L02:T2",
        "D4-L03:C01",
        "D4-L04:C01",
    ]
    actual_order = [str(item.get("turn_id")) for item in cases]
    if actual_order != expected_order:
        raise PreflightError(f"D4 execution order drifted: {actual_order!r}")
    for item in cases:
        request = item.get("request")
        if not isinstance(request, str) or sha256_text(request) != item.get("request_sha256"):
            raise PreflightError(f"request identity mismatch: {item.get('turn_id')}")
    assert_unseen_requests(repo_root, cases)
    return cases


def load_gold(repo_root: Path) -> dict[str, Any]:
    """Load gold expectations and validate the canonical LAS seed."""
    payload = _load_json(repo_root / GOLD_PATH)
    seed = payload.get("canonical_las_seed")
    if not isinstance(seed, dict):
        raise PreflightError("canonical LAS seed is missing")
    try:
        AuthoringDocumentSpec.model_validate(seed)
    except ValidationError as error:
        raise PreflightError("canonical LAS seed does not validate") from error
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 9:
        raise PreflightError("gold must cover all nine turns")
    return payload


def preflight_las_source(repo_root: Path) -> SourcePreflight:
    """Authenticate and parse the immutable real LAS source."""
    path = repo_root / SOURCE_RELATIVE
    if not path.is_file():
        raise PreflightError(f"frozen LAS source is missing: {SOURCE_RELATIVE}")
    size = path.stat().st_size
    digest = sha256_file(path)
    if size != SOURCE_SIZE or digest != SOURCE_SHA256:
        raise PreflightError("frozen LAS source size or SHA-256 drifted")
    try:
        dataset = load_las(path)
    except Exception as error:
        raise PreflightError("frozen LAS source cannot be parsed") from error
    channels = tuple(sorted(str(name) for name in dataset.channels))
    inventory = set(channels)
    if not SOURCE_REQUIRED_CHANNELS.issubset(inventory):
        raise PreflightError("frozen LAS source is missing a required channel")
    if SOURCE_FORBIDDEN_CHANNELS.intersection(inventory):
        raise PreflightError("frozen LAS source contains forbidden RT channel")
    return SourcePreflight(
        relative_path=SOURCE_RELATIVE.as_posix(),
        size=size,
        sha256=digest,
        channel_inventory=channels,
        required_channels_present=True,
        forbidden_channels_absent=True,
    )


def preflight_dlis_sources(repo_root: Path) -> list[dict[str, Any]]:
    """Authenticate the two accepted D3 DLIS sources without retaining data."""
    expected = {
        Path("workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis"): (
            111_573_216,
            "3ceb9100fd654d710155672a50a9e0f24ce9705db6ef8e424140f29bd02131f7",
        ),
        Path("workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis"): (
            3_294_924,
            "a4a2e91b495172079fc47bc2e9c936f0ab60c9845bbed8e65bf56555a5e82640",
        ),
    }
    result = []
    for relative, (size, digest) in expected.items():
        path = repo_root / relative
        if not path.is_file() or path.stat().st_size != size or sha256_file(path) != digest:
            raise PreflightError(f"frozen DLIS source drifted: {relative}")
        try:
            dataset = load_dlis(path)
        except Exception as error:
            raise PreflightError(f"frozen DLIS source cannot be parsed: {relative}") from error
        result.append(
            {
                "relative_path": relative.as_posix(),
                "size": size,
                "sha256": digest,
                "channel_count": len(dataset.channels),
            }
        )
    return result


def inspect_openai_retry_policy() -> dict[str, Any]:
    """Inspect package/version/signature without constructing a client."""
    version = importlib.metadata.version("openai")
    try:
        from openai import AsyncOpenAI

        default = inspect.signature(AsyncOpenAI).parameters["max_retries"].default
    except (ImportError, KeyError, TypeError, ValueError) as error:
        raise PreflightError("unable to inspect OpenAI max_retries") from error
    if version != EXPECTED_OPENAI_VERSION or default != EXPECTED_SDK_MAX_RETRIES:
        raise PreflightError(
            f"OpenAI retry contract drifted: version={version!r}, max_retries={default!r}"
        )
    return {
        "package": "openai",
        "version": version,
        "max_retries": default,
        "physical_http_attempt_upper_bound": MAX_LOGICAL_CALLS * (1 + default),
    }


def verify_production_identity(repo_root: Path) -> dict[str, Any]:
    """Prove D4A did not change the accepted D3 production tree."""
    changed = _git(
        repo_root,
        "diff",
        "--name-only",
        f"{PRODUCTION_BASELINE}..HEAD",
        "--",
        "src/wellplot",
    ).splitlines()
    if changed:
        raise PreflightError(f"production source changed: {changed}")
    component_hashes = production_component_hashes(repo_root)
    if component_hashes != FROZEN_PRODUCTION_COMPONENT_SHA256:
        raise PreflightError("authorized production component hashes drifted")
    return {
        "baseline": PRODUCTION_BASELINE,
        "current": _git(repo_root, "rev-parse", "HEAD"),
        "changed_files": [],
        "component_sha256": component_hashes,
    }


def production_component_hashes(repo_root: Path) -> dict[str, str]:
    """Hash every production/verifier component frozen by the D4 design."""
    result: dict[str, str] = {}
    for relative in PRODUCTION_COMPONENT_PATHS:
        path = repo_root / relative
        if not path.is_file():
            raise PreflightError(f"authorized component is missing: {relative}")
        result[relative] = sha256_file(path)
    return result


def verify_frozen_contract(
    repo_root: Path,
    authorization: FrozenAuthorization,
) -> dict[str, Any]:
    """Authenticate external D4B custody facts before state or credentials."""
    current = _git(repo_root, "rev-parse", "HEAD")
    if current != authorization.accepted_checkpoint:
        raise PreflightError("checkout does not match the independently accepted D4A checkpoint")
    if _git(repo_root, "status", "--porcelain"):
        raise PreflightError("working tree is not clean")
    if authorization.provider != EXPECTED_PROVIDER or authorization.model != EXPECTED_MODEL:
        raise PreflightError("provider/model configuration drifted")
    if authorization.openai_version != EXPECTED_OPENAI_VERSION:
        raise PreflightError("authorized OpenAI version drifted")
    if authorization.sdk_max_retries != EXPECTED_SDK_MAX_RETRIES:
        raise PreflightError("authorized SDK retry setting drifted")
    if authorization.cases_fixture_sha256 != FROZEN_CASES_SHA256:
        raise PreflightError("authorized cases fixture hash is not the frozen hash")
    if authorization.gold_fixture_sha256 != FROZEN_GOLD_SHA256:
        raise PreflightError("authorized gold fixture hash is not the frozen hash")
    if authorization.uv_lock_sha256 != FROZEN_UV_LOCK_SHA256:
        raise PreflightError("authorized uv.lock hash is not the frozen hash")
    if authorization.production_component_sha256 != FROZEN_PRODUCTION_COMPONENT_SHA256:
        raise PreflightError("authorized production component manifest drifted")
    paths = (repo_root / STATE_RELATIVE, repo_root / JOURNAL_RELATIVE)
    if any(path.exists() for path in paths):
        raise PreflightError("campaign state or journal already exists")
    observed = {
        "accepted_checkpoint": current,
        "harness_source_sha256": sha256_file(repo_root / HARNESS_SOURCE_PATH),
        "cases_fixture_sha256": sha256_file(repo_root / CASES_PATH),
        "gold_fixture_sha256": sha256_file(repo_root / GOLD_PATH),
        "uv_lock_sha256": sha256_file(repo_root / UV_LOCK_PATH),
        "production_component_sha256": production_component_hashes(repo_root),
    }
    for field_name in (
        "harness_source_sha256",
        "cases_fixture_sha256",
        "gold_fixture_sha256",
        "uv_lock_sha256",
        "production_component_sha256",
    ):
        if observed[field_name] != getattr(authorization, field_name):
            raise PreflightError(f"frozen artifact mismatch: {field_name}")
    return observed


def assert_campaign_paths_absent(state_path: Path, journal_path: Path) -> None:
    """Reject any existing state or journal, including zero-length files."""
    if state_path.exists() or journal_path.exists():
        raise PreflightError("D4 campaign artifacts already exist; resume is forbidden")


def _fsync_directory(path: Path) -> None:
    """Persist a directory entry after creating or replacing an evidence file."""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, payload: dict[str, Any], *, exclusive: bool = False) -> None:
    """Write JSON durably, optionally refusing an existing target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(
        temporary,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )
    try:
        encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive:
            try:
                os.link(temporary, path)
            except FileExistsError as error:
                raise PreflightError(f"evidence target already exists: {path}") from error
            finally:
                temporary.unlink(missing_ok=True)
        else:
            os.replace(temporary, path)
        _fsync_directory(path.parent)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


@dataclass
class CampaignJournal:
    """Exclusive, fsync-backed JSONL writer for one campaign."""

    path: Path
    _descriptor: int | None = field(default=None, init=False, repr=False)

    def _open(self) -> None:
        if self._descriptor is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._descriptor = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_APPEND | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as error:
            raise PreflightError("campaign journal already exists; resume is forbidden") from error
        _fsync_directory(self.path.parent)

    def append(self, event: Mapping[str, Any]) -> None:
        """Append one redacted event and force it to durable storage."""
        if not evidence_is_redacted(event):
            raise PreflightError("journal event contains secret or raw generation material")
        self._open()
        assert self._descriptor is not None
        data = (canonical_json(dict(event)) + "\n").encode("utf-8")
        offset = 0
        while offset < len(data):
            offset += os.write(self._descriptor, data[offset:])
        os.fsync(self._descriptor)

    def close(self) -> None:
        """Close the descriptor without changing the journal contents."""
        if self._descriptor is not None:
            os.close(self._descriptor)
            self._descriptor = None


@dataclass
class CampaignCustody:
    """Persist monotonic logical-call evidence and bounded turn rows."""

    state_path: Path
    journal: CampaignJournal
    state: dict[str, Any]

    def record_call_started(self, event: Mapping[str, Any]) -> None:
        """Durably count an attempted logical call before provider delegation."""
        next_count = int(self.state.get("logical_generation_calls", 0)) + 1
        if next_count > MAX_LOGICAL_CALLS:
            raise CallCapExceeded("logical generation call exceeds the frozen campaign cap")
        self.state["logical_generation_calls"] = next_count
        _atomic_json(self.state_path, self.state)
        self.journal.append(
            {
                "experiment_version": EXPERIMENT_VERSION,
                "campaign_id": self.state["campaign_id"],
                "logical_generation_calls": next_count,
                **dict(event),
            }
        )

    def append_turn(self, row: Mapping[str, Any]) -> None:
        """Append one bounded turn row after validating its required identity."""
        required = {
            "experiment_version",
            "campaign_id",
            "turn_id",
            "execution_index",
            "request_sha256",
            "result_status",
            "outcome",
        }
        missing = required - set(row)
        if missing:
            raise PreflightError(f"turn evidence is missing fields: {sorted(missing)!r}")
        self.journal.append(dict(row))


def start_campaign(
    *,
    state_path: Path,
    journal_path: Path,
    preflight: Callable[[], dict[str, Any]],
    credential_factory: Callable[[], object],
) -> tuple[dict[str, Any], object]:
    """Create durable STARTED state before accessing credentials/provider code."""
    assert_campaign_paths_absent(state_path, journal_path)
    provenance = preflight()
    campaign_id = f"d4-live-v1-{uuid.uuid4().hex}"
    state = {
        "experiment_version": EXPERIMENT_VERSION,
        "campaign_id": campaign_id,
        "production_baseline": PRODUCTION_BASELINE,
        "live_harness_checkpoint": provenance.get(
            "accepted_checkpoint", provenance["current_checkout"]
        ),
        "status": "STARTED",
        "logical_generation_calls": 0,
    }
    for key in (
        "harness_source_sha256",
        "cases_fixture_sha256",
        "gold_fixture_sha256",
        "uv_lock_sha256",
        "production_component_sha256",
    ):
        if key in provenance:
            state[key] = provenance[key]
    _atomic_json(state_path, state, exclusive=True)
    return state, credential_factory()


def evidence_is_redacted(value: object) -> bool:
    """Return false when evidence contains forbidden fields or secret markers."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in SECRET_KEYS or not evidence_is_redacted(item):
                return False
        return True
    if isinstance(value, list):
        return all(evidence_is_redacted(item) for item in value)
    if isinstance(value, str):
        lowered = value.casefold()
        return not any(marker in lowered for marker in SECRET_MARKERS)
    return True


def _pointer_value(document: Mapping[str, Any], path: str) -> object:
    """Read a small JSON-pointer subset used by the frozen gold contracts."""
    current: object = document
    if path in {"", "/"}:
        return current
    if not path.startswith("/"):
        raise PreflightError(f"gold pointer must start with '/': {path!r}")
    for part in path[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if part not in current:
                raise KeyError(path)
            current = current[part]
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            current = current[int(part)]
        else:
            raise KeyError(path)
    return current


def _assertion_matches(document: Mapping[str, Any], assertion: Mapping[str, Any]) -> bool:
    """Evaluate one deterministic gold assertion."""
    try:
        actual = _pointer_value(document, str(assertion["path"]))
    except (KeyError, IndexError, TypeError, ValueError):
        return False
    operator = assertion.get("operator", "equals")
    expected = assertion.get("value")
    if operator == "equals":
        return actual == expected
    if operator == "contains":
        return isinstance(actual, str) and str(expected) in actual
    if operator == "exists":
        return True
    if operator == "length":
        return isinstance(actual, (list, tuple, dict, str)) and len(actual) == int(expected)
    raise PreflightError(f"unsupported D4 gold assertion operator: {operator!r}")


def _changed_paths(before: object, after: object, path: str = "") -> list[str]:
    """Return canonical paths changed between two JSON-like artifacts."""
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        paths: list[str] = []
        for key in sorted(set(before) | set(after), key=str):
            child = f"{path}/{key}" if path else f"/{key}"
            if key not in before or key not in after:
                paths.append(child)
            else:
                paths.extend(_changed_paths(before[key], after[key], child))
        return paths
    if (
        isinstance(before, Sequence)
        and isinstance(after, Sequence)
        and not isinstance(before, (str, bytes, bytearray))
        and not isinstance(after, (str, bytes, bytearray))
    ):
        paths = []
        for index in range(max(len(before), len(after))):
            child = f"{path}/{index}"
            if index >= len(before) or index >= len(after):
                paths.append(child)
            else:
                paths.extend(_changed_paths(before[index], after[index], child))
        return paths
    return [path or "/"] if before != after else []


def _run_frozen_verifier(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> dict[str, Any]:
    """Run the unchanged D4 verifier when canonical artifact paths are supplied."""
    verifier = actual.get("verifier")
    if isinstance(verifier, Mapping):
        return dict(verifier)
    before_path = actual.get("before_path")
    after_path = actual.get("after_path")
    if expected.get("grader") == "las" and before_path and after_path:
        from scripts.verify_las_revision import verify_las_revision

        before_bytes = Path(str(before_path)).read_bytes()
        after_bytes = Path(str(after_path)).read_bytes()
        verifier = verify_las_revision(
            before_path,
            after_path,
            expected["contract"],
            execution_evidence=actual.get("execution_evidence"),
        )
        if Path(str(before_path)).read_bytes() != before_bytes:
            raise PreflightError("LAS verifier mutated the before artifact")
        if Path(str(after_path)).read_bytes() != after_bytes:
            raise PreflightError("LAS verifier mutated the after artifact")
        return verifier
    cbl_path = actual.get("artifact_path")
    if expected.get("grader") == "cbl" and cbl_path:
        from scripts.verify_cbl_packet import verify_cbl_packet

        before_bytes = Path(str(cbl_path)).read_bytes()
        verifier = verify_cbl_packet(
            cbl_path,
            execution_evidence=actual.get("execution_evidence"),
        )
        if Path(str(cbl_path)).read_bytes() != before_bytes:
            raise PreflightError("CBL verifier mutated the acceptance artifact")
        return verifier
    return {}


def _grader_requirements(verifier: Mapping[str, Any], required_ids: Sequence[str]) -> list[str]:
    """Return missing or failed verifier requirements."""
    status_by_id = {
        str(item.get("id")): item.get("status")
        for item in verifier.get("requirements", [])
        if isinstance(item, Mapping)
    }
    errors = []
    for requirement_id in required_ids:
        if status_by_id.get(requirement_id) != "PASS":
            errors.append(f"verifier requirement failed: {requirement_id}")
    return errors


def grade_turn(actual: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    """Grade deterministic scientific and safety contracts without provider material."""
    outcome = actual.get("outcome")
    expected_outcome = expected.get("expected_outcome")
    errors: list[str] = []
    if outcome != expected_outcome:
        errors.append("outcome_mismatch")
    contract = expected.get("contract")
    if not isinstance(contract, Mapping):
        errors.append("missing_case_specific_contract")
        contract = {}
    verifier = _run_frozen_verifier(actual, expected)
    if contract.get("kind") in {"cbl", "las"} and not verifier:
        errors.append("missing_deterministic_verifier_result")
    errors.extend(
        _grader_requirements(
            verifier,
            contract.get("required_verifier_requirements", []),
        )
    )
    if expected_outcome == "SAFE_ACTIONABLE_FAILURE":
        if actual.get("changed") is not False:
            errors.append("failure_mutated_artifact")
        if actual.get("pre_bytes_sha256") != actual.get("post_bytes_sha256"):
            errors.append("failure_bytes_changed")
        if not actual.get("diagnostic_code"):
            errors.append("missing_actionable_diagnostic")
        if actual.get("canonical_before") != actual.get("canonical_after"):
            errors.append("failure_canonical_state_changed")
        if actual.get("intent_applied") is not False:
            errors.append("failure_applied_intent")
        for key in contract.get("required_false_flags", []):
            if actual.get(key) is not False:
                errors.append(f"failure_flag_not_false: {key}")
        forbidden_channels = set(contract.get("prohibited_channels", []))
        observed_channels = set(actual.get("created_channels", []))
        if forbidden_channels.intersection(observed_channels):
            errors.append("prohibited_channel_substitution")
        changed_prohibited = set(actual.get("prohibited_paths_changed", []))
        if changed_prohibited.intersection(set(contract.get("prohibited_paths", []))):
            errors.append("prohibited_path_mutation")
    else:
        before = actual.get("canonical_before")
        after = actual.get("canonical_after")
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            errors.append("missing_canonical_before_after")
        else:
            for assertion in contract.get("before_assertions", []):
                if not _assertion_matches(before, assertion):
                    errors.append(f"before_assertion_failed: {assertion.get('path')}")
            for assertion in contract.get("after_assertions", []):
                if not _assertion_matches(after, assertion):
                    errors.append(f"after_assertion_failed: {assertion.get('path')}")
            changed_paths = _changed_paths(before, after)
            allowed = contract.get("allowed_change_paths", [])
            if any(
                not any(
                    path == allowed_path
                    or path.startswith(str(allowed_path).rstrip("/") + "/")
                    or str(allowed_path).startswith(path.rstrip("/") + "/")
                    for allowed_path in allowed
                )
                for path in changed_paths
            ):
                errors.append("canonical_change_outside_allowed_paths")
            if not any(
                any(
                    path == required_path
                    or path.startswith(str(required_path).rstrip("/") + "/")
                    or str(required_path).startswith(path.rstrip("/") + "/")
                    for required_path in contract.get("required_change_paths", [])
                )
                for path in changed_paths
            ) and contract.get("required_change_paths"):
                errors.append("required_scientific_change_missing")
        if actual.get("persisted") is not True:
            errors.append("persistence_not_proven")
        if actual.get("rendered") is not True:
            errors.append("render_not_proven")
        verifier_status = verifier.get("status", verifier.get("acceptance_status"))
        if actual.get("verifier_status", verifier_status) not in {"PASS", "accepted"}:
            errors.append("verifier_failed")
    for flag in contract.get("required_true_flags", []):
        if actual.get(flag) is not True:
            errors.append(f"required_flag_not_true: {flag}")
    return {
        "turn_id": expected["turn_id"],
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }


def derive_terminal_decision(rows: Sequence[dict[str, Any]]) -> str:
    """Derive the frozen D4 decision from complete bounded row evidence."""
    if len(rows) != 9:
        return "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_INCONCLUSIVE"
    if any(row.get("infrastructure_failure") or row.get("configuration_drift") for row in rows):
        return "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_INCONCLUSIVE"
    if any(row.get("logical_call_cap_exceeded") for row in rows):
        return "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_INCONCLUSIVE"
    if any(row.get("grader_status") != "PASS" for row in rows):
        return "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_FAILED"
    if any(
        row.get("undetected_incorrect_output") or row.get("unintended_mutation") for row in rows
    ):
        return "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_FAILED"
    return "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_PASSED"


def provider_free_preflight(
    repo_root: Path,
    authorization: FrozenAuthorization,
) -> dict[str, Any]:
    """Run all D4A checks without credentials, endpoint access, or provider creation."""
    attestation = verify_frozen_contract(repo_root, authorization)
    current = _git(repo_root, "rev-parse", "HEAD")
    cases = load_cases(repo_root)
    gold = load_gold(repo_root)
    las = preflight_las_source(repo_root)
    dlis = preflight_dlis_sources(repo_root)
    observed_sources = {
        SOURCE_RELATIVE.as_posix(): las.sha256,
        **{item["relative_path"]: item["sha256"] for item in dlis},
    }
    if observed_sources != dict(authorization.source_sha256):
        raise PreflightError("source hash manifest drifted")
    sdk = inspect_openai_retry_policy()
    if sdk["version"] != authorization.openai_version:
        raise PreflightError("installed OpenAI package version drifted")
    if sdk["max_retries"] != authorization.sdk_max_retries:
        raise PreflightError("runtime OpenAI max_retries drifted")
    production = verify_production_identity(repo_root)
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "current_checkout": current,
        "accepted_checkpoint": authorization.accepted_checkpoint,
        **attestation,
        "authorized_design_checkpoint": AUTHORIZED_DESIGN_CHECKPOINT,
        "production": production,
        "population": {
            "cases": 5,
            "turns": len(cases),
            "concurrency": 1,
            "logical_call_ceiling": MAX_LOGICAL_CALLS,
        },
        "request_hashes": {case["turn_id"]: case["request_sha256"] for case in cases},
        "fixture_sha256": {
            "cases": sha256_file(repo_root / CASES_PATH),
            "gold": sha256_file(repo_root / GOLD_PATH),
        },
        "canonical_seed_valid": True,
        "canonical_seed_name": gold["canonical_las_seed"]["name"],
        "las_source": asdict(las),
        "dlis_sources": dlis,
        "openai_retry": sdk,
        "provider_calls": 0,
        "endpoint_calls": 0,
        "model_calls": 0,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--provider-free-preflight", action="store_true")
    parser.add_argument("--authorization-json", type=Path)
    args = parser.parse_args()
    if not args.provider_free_preflight:
        parser.error("D4A only supports --provider-free-preflight; D4B is not authorized")
    if args.authorization_json is None:
        parser.error("--authorization-json is required for frozen-contract attestation")
    try:
        authorization = FrozenAuthorization.from_mapping(
            _load_json(args.authorization_json.resolve())
        )
        print(
            json.dumps(
                provider_free_preflight(args.repo_root.resolve(), authorization),
                indent=2,
                sort_keys=True,
            )
        )
    except PreflightError as error:
        print(json.dumps({"status": "D4A_BLOCKED", "reason": str(error)}, indent=2))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
