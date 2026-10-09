"""Provider-free D4 live-acceptance harness and future-live interlocks.

The default command path performs only deterministic preflight checks. Live
execution is isolated behind an explicit D4B authorization record and the
campaign-owned execution adapter, so D4A tests cannot construct a provider.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import importlib.metadata
import inspect
import json
import os
import subprocess
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from wellplot.agent.direct_notebook import DirectNotebookSession
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
INCONCLUSIVE_DECISION = "WELLPLOT_NLP_D4_LIVE_ACCEPTANCE_INCONCLUSIVE"
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
FROZEN_GOLD_SHA256 = "99ba5fc73dfd95d67c8a909cb75325a84ff1bbccc724fa524d7850f306d02968"
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


@dataclass(slots=True)
class LogicalCallLedger:
    """Reserve unique logical-call identities before any provider delegation."""

    max_calls: int = MAX_LOGICAL_CALLS
    started_calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def reserve(self) -> int:
        """Atomically reserve the next call index or reject it before delegation."""
        with self._lock:
            next_index = self.started_calls + 1
            if next_index > self.max_calls:
                raise CallCapExceeded(
                    f"logical generation call {next_index} rejected before delegation"
                )
            self.started_calls = next_index
            return next_index


@dataclass
class CountingBackend:
    """Count logical generation calls without adding retries or payload capture."""

    delegate: ModelBackendProtocol
    provider: str = EXPECTED_PROVIDER
    model: str = EXPECTED_MODEL
    max_calls: int = MAX_LOGICAL_CALLS
    call_started: Callable[[dict[str, Any]], None] | None = None
    call_completed: Callable[[dict[str, Any]], None] | None = None
    prompt_guard: Callable[[str], None] | None = None
    calls: list[LogicalCall] = field(default_factory=list)
    ledger: LogicalCallLedger | None = None

    def __post_init__(self) -> None:
        """Give standalone wrappers a ledger while allowing campaign sharing."""
        if self.ledger is None:
            self.ledger = LogicalCallLedger(max_calls=self.max_calls)
        elif self.ledger.max_calls != self.max_calls:
            raise ValueError("counting backend and logical-call ledger caps must match")

    def _before(self, operation: str, request: object) -> int:
        temperature = getattr(request, "temperature", None)
        max_output_tokens = getattr(request, "max_output_tokens", None)
        if operation not in {"structured", "program"}:
            raise ValueError(f"unsupported operation: {operation}")
        if operation == "structured":
            if temperature != 0.0 or max_output_tokens is not None:
                raise PreflightError("planner request controls drifted")
        elif temperature is not None or max_output_tokens is not None:
            raise PreflightError("worker request controls drifted")
        if self.prompt_guard is not None:
            prompt = getattr(request, "user_prompt", None)
            if not isinstance(prompt, str):
                raise PreflightError("generation request has no user prompt")
            self.prompt_guard(prompt)
        assert self.ledger is not None
        index = self.ledger.reserve()
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
        call = LogicalCall(
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
        self.calls.append(call)
        if self.call_completed is not None:
            self.call_completed(
                {
                    "event": "logical_call_completed",
                    "index": call.index,
                    "operation": call.operation,
                    "provider": call.provider,
                    "model": call.model,
                    "temperature": call.temperature,
                    "max_output_tokens": call.max_output_tokens,
                    "outcome": call.outcome,
                    "failure_category": call.category,
                    **call.metrics,
                }
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


@dataclass(frozen=True, slots=True)
class CampaignCallSource:
    """Expose one shared bounded call ledger for all graph backends."""

    backends: tuple[CountingBackend, ...]
    calls: list[LogicalCall]
    ledger: LogicalCallLedger | None = None

    def __post_init__(self) -> None:
        """Require all campaign wrappers to use one start-time ledger."""
        if self.ledger is None:
            if self.backends:
                ledger = self.backends[0].ledger
                assert ledger is not None
            else:
                ledger = LogicalCallLedger()
            object.__setattr__(self, "ledger", ledger)
        assert self.ledger is not None
        if any(backend.ledger is not self.ledger for backend in self.backends):
            raise ValueError("campaign backends must share one logical-call ledger")

    def bind_call_started(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Bind durable custody to every ModelBackendProtocol boundary."""
        for backend in self.backends:
            backend.call_started = callback

    def bind_call_completed(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Bind durable completion evidence to every backend boundary."""
        for backend in self.backends:
            backend.call_completed = callback

    @property
    def logical_call_count(self) -> int:
        """Return the reserved logical-call count from the shared ledger."""
        assert self.ledger is not None
        return self.ledger.started_calls

    def calls_since(self, cursor: int) -> list[LogicalCall]:
        """Return bounded observations since one turn-local cursor."""
        return sorted(
            (call for call in self.calls if call.index > cursor),
            key=lambda call: call.index,
        )


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
        if event.get("index") != next_count:
            raise PreflightError("logical-call ledger index drifted from campaign custody")
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

    def record_call_completed(self, event: Mapping[str, Any]) -> None:
        """Persist bounded post-delegation call evidence without payloads."""
        self.journal.append(
            {
                "experiment_version": EXPERIMENT_VERSION,
                "campaign_id": self.state["campaign_id"],
                **dict(event),
            }
        )

    def append_turn(self, row: Mapping[str, Any]) -> None:
        """Append one bounded turn row after validating its required identity."""
        required = {
            "experiment_version",
            "campaign_id",
            "production_baseline",
            "live_harness_checkpoint",
            "case_id",
            "turn_id",
            "execution_index",
            "request_sha256",
            "starting_artifact_sha256",
            "ending_artifact_sha256",
            "render_sha256",
            "provider",
            "model",
            "result_status",
            "outcome",
            "apply_status",
            "diagnostics",
            "worker_metrics",
            "token_usage",
            "logical_generation_calls",
            "structured_logical_calls",
            "program_logical_calls",
            "worker_repair_count",
            "turn_duration_seconds",
            "render_duration_seconds",
            "sdk_max_retries",
            "physical_http_attempt_upper_bound",
            "verifier_requirements",
            "diff_status",
            "grader_status",
        }
        missing = required - set(row)
        if missing:
            raise PreflightError(f"turn evidence is missing fields: {sorted(missing)!r}")
        self.journal.append(dict(row))


def _bounded_diagnostics(value: object) -> list[dict[str, object]]:
    """Keep bounded diagnostic facts transiently for outcome classification."""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    result: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        result.append(
            {
                key: item[key]
                for key in (
                    "stage",
                    "code",
                    "message",
                    "severity",
                    "retryable",
                    "worker_kind",
                    "plan_order",
                )
                if key in item
            }
        )
    return result


def _journal_diagnostics(value: object) -> list[dict[str, object]]:
    """Project diagnostics to stable journal fields without free-form messages."""
    fields = ("stage", "code", "severity", "retryable", "worker_kind", "plan_order")
    return [
        {key: item[key] for key in fields if key in item} for item in _bounded_diagnostics(value)
    ]


def _artifact_sha256(actual: Mapping[str, Any], *, path_key: str, hash_key: str) -> str | None:
    """Use a supplied artifact hash or hash a local artifact without journaling its path."""
    supplied = actual.get(hash_key)
    if supplied is not None:
        return str(supplied)
    path = actual.get(path_key)
    if path is None:
        return None
    artifact = Path(str(path))
    return sha256_file(artifact) if artifact.is_file() else None


def _worker_metrics(actual: Mapping[str, Any]) -> dict[str, int | float]:
    """Project bounded worker and usage metrics from one turn."""
    value = actual.get("worker_metrics", {})
    if not isinstance(value, Mapping):
        return {}
    allowed = {
        "worker_count",
        "successful_workers",
        "failed_workers",
        "program_calls",
        "program_repairs",
        "total_calls",
        "total_repairs",
        "input_tokens",
        "output_tokens",
        "total_tokens",
    }
    return {
        str(key): item
        for key, item in value.items()
        if key in allowed and isinstance(item, (int, float)) and not isinstance(item, bool)
    }


def _token_usage(calls: Sequence[LogicalCall]) -> dict[str, int | float | None]:
    """Aggregate bounded provider usage for one turn without raw payloads."""
    fields = ("input_tokens", "output_tokens", "total_tokens", "latency_ms")
    usage: dict[str, int | float | None] = {}
    for field_name in fields:
        values = [call.metrics.get(field_name) for call in calls]
        if any(value is None for value in values):
            usage[field_name] = None
        else:
            usage[field_name] = sum(value for value in values if value is not None)
    return usage


def _add_session_evidence(actual: dict[str, Any], result: object) -> None:
    """Project bounded notebook-session evidence into one turn observation."""
    report_facts = getattr(result, "report_facts", {})
    compilation = report_facts.get("compilation", {}) if isinstance(report_facts, Mapping) else {}
    if not isinstance(compilation, Mapping):
        compilation = {}
    diagnostics = _bounded_diagnostics(compilation.get("diagnostics", []))
    metrics = compilation.get("metrics", {})
    if not isinstance(metrics, Mapping):
        metrics = {}
    actual["diagnostics"] = diagnostics
    actual["worker_metrics"] = _worker_metrics({"worker_metrics": metrics})
    actual["worker_repair_count"] = int(metrics.get("total_repairs", 0) or 0)
    actual["apply_status"] = report_facts.get("apply_status")
    actual["intent_applied"] = getattr(result, "submitted_intent", None) is not None
    actual["changed"] = bool(report_facts.get("changed", False))
    actual["diagnostic_code"] = diagnostics[0].get("code") if diagnostics else None


def _document_channels(document: Mapping[str, Any]) -> list[str]:
    """Return persisted binding channels from one canonical document."""
    channels: list[str] = []
    for section in document.get("sections", []):
        if not isinstance(section, Mapping):
            continue
        for track in section.get("tracks", []):
            if not isinstance(track, Mapping):
                continue
            for binding in track.get("bindings", []):
                if isinstance(binding, Mapping) and binding.get("channel") is not None:
                    channels.append(str(binding["channel"]))
    return channels


def _observed_failure_facts(
    actual: Mapping[str, Any],
    before: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive failure facts from persisted artifacts and bounded diagnostics."""
    after = actual.get("canonical_after")
    if not isinstance(after, Mapping):
        after = {}
    before_channels = _document_channels(before)
    after_channels = _document_channels(after)
    created_channels = [channel for channel in after_channels if channel not in before_channels]
    diagnostic_code = actual.get("diagnostic_code")
    diagnostics = actual.get("diagnostics", [])
    byte_identity = (
        actual.get("pre_bytes_sha256") is not None
        and actual.get("post_bytes_sha256") is not None
        and actual.get("pre_bytes_sha256") == actual.get("post_bytes_sha256")
    )
    canonical_identity = before == after
    no_intent = actual.get("intent_applied") is not True
    no_persisted_substitution = not created_channels
    diagnostic_text = " ".join(
        f"{item.get('code', '')} {item.get('message', '')}"
        for item in diagnostics
        if isinstance(item, Mapping)
    ).casefold()
    observed_safe_diagnostic = False
    for item in diagnostics:
        if not isinstance(item, Mapping):
            continue
        code = str(item.get("code", ""))
        message = str(item.get("message", "")).casefold()
        if code in {"enrichment.section_hint_ambiguous", "enrichment.source_missing"}:
            observed_safe_diagnostic = True
            break
        if (
            code == "program.dry_run_error"
            and "channel_missing" in message
            and "no source channel matches 'rt'" in message
        ):
            observed_safe_diagnostic = True
            break
    return {
        "changed": not (byte_identity and canonical_identity),
        "diagnostic_code": diagnostic_code,
        "intent_applied": actual.get("intent_applied") is True,
        "created_channels": created_channels,
        "fallback_used": bool("fallback" in diagnostic_text),
        "substituted_channel": bool(created_channels),
        "prohibited_object_present": bool(created_channels),
        "observed_safe_rejection": (
            byte_identity
            and canonical_identity
            and no_intent
            and no_persisted_substitution
            and observed_safe_diagnostic
        ),
    }


def _grade_has_unintended_mutation(grade: Mapping[str, Any]) -> bool:
    """Identify mutation evidence that must outrank ordinary semantic failure."""
    mutation_errors = {
        "canonical_change_outside_allowed_paths",
        "failure_mutated_artifact",
        "failure_bytes_changed",
        "failure_canonical_state_changed",
        "prohibited_channel_substitution",
        "prohibited_path_mutation",
    }
    return any(error in mutation_errors for error in grade.get("errors", []))


def _observed_outcome(
    actual: Mapping[str, Any],
    case: Mapping[str, Any],
    before: Mapping[str, Any],
    grade: Mapping[str, Any] | None = None,
) -> str:
    """Classify one turn after deterministic grading, never from the gold outcome."""
    grade_status = grade.get("status", "PASS") if isinstance(grade, Mapping) else "PASS"
    if actual.get("infrastructure_failure"):
        return "INFRASTRUCTURE_INCONCLUSIVE"
    if actual.get("unintended_mutation") or (
        isinstance(grade, Mapping) and _grade_has_unintended_mutation(grade)
    ):
        return "UNINTENDED_MUTATION"
    if actual.get("persisted") is True and actual.get("rendered") is True:
        if grade_status != "PASS":
            return "UNDETECTED_INCORRECT_OUTPUT"
        if (
            case.get("workflow") == "LAS-REVISE"
            and len(before.get("sections", [])) > 1
            and "only to" in str(case.get("request", "")).casefold()
        ):
            return "CORRECT_AFTER_CLARIFICATION"
        return "DIRECT_CORRECT"
    if actual.get("observed_safe_rejection") is True:
        return "SAFE_ACTIONABLE_FAILURE"
    return "DETECTED_INCORRECT_OUTPUT"


def _campaign_turn_row(
    *,
    state: Mapping[str, Any],
    case: Mapping[str, Any],
    actual: Mapping[str, Any],
    grade: Mapping[str, Any],
    duration_seconds: float,
    observed_calls: Sequence[LogicalCall] = (),
) -> dict[str, Any]:
    """Build the complete bounded JSONL schema for one campaign turn."""
    logical_calls = len(observed_calls)
    structured_calls = sum(call.operation == "structured" for call in observed_calls)
    program_calls = sum(call.operation == "program" for call in observed_calls)
    verifier_requirements = grade.get("verifier_requirements", [])
    if not isinstance(verifier_requirements, list):
        verifier_requirements = []
    render_sha256 = _artifact_sha256(actual, path_key="render_path", hash_key="render_sha256")
    starting_artifact_sha256 = _artifact_sha256(
        actual,
        path_key="starting_artifact_path",
        hash_key="starting_artifact_sha256",
    ) or _artifact_sha256(actual, path_key="before_path", hash_key="before_sha256")
    ending_artifact_sha256 = _artifact_sha256(
        actual,
        path_key="ending_artifact_path",
        hash_key="ending_artifact_sha256",
    ) or _artifact_sha256(actual, path_key="after_path", hash_key="after_sha256")
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "campaign_id": state["campaign_id"],
        "production_baseline": PRODUCTION_BASELINE,
        "live_harness_checkpoint": state["live_harness_checkpoint"],
        "case_id": case["case_id"],
        "turn_id": case["turn_id"],
        "execution_index": case["execution_index"],
        "request_sha256": case["request_sha256"],
        "starting_artifact_sha256": starting_artifact_sha256,
        "ending_artifact_sha256": ending_artifact_sha256,
        "render_sha256": render_sha256,
        "provider": str(actual.get("provider", EXPECTED_PROVIDER)),
        "model": str(actual.get("model", EXPECTED_MODEL)),
        "result_status": str(actual.get("result_status", "COMPLETED")),
        "apply_status": str(
            actual.get(
                "apply_status",
                "persisted" if actual.get("persisted") is True else "rejected",
            )
        ),
        "outcome": actual.get("outcome"),
        "diagnostics": _journal_diagnostics(actual.get("diagnostics", [])),
        "worker_metrics": _worker_metrics(actual),
        "token_usage": _token_usage(observed_calls),
        "logical_generation_calls": logical_calls,
        "structured_logical_calls": structured_calls,
        "program_logical_calls": program_calls,
        "worker_repair_count": int(actual.get("worker_repair_count", 0)),
        "turn_duration_seconds": round(duration_seconds, 6),
        "render_duration_seconds": round(float(actual.get("render_duration_seconds", 0.0)), 6),
        "sdk_max_retries": EXPECTED_SDK_MAX_RETRIES,
        "physical_http_attempt_upper_bound": logical_calls * (EXPECTED_SDK_MAX_RETRIES + 1),
        "verifier_requirements": verifier_requirements,
        "diff_status": str(grade.get("diff_status", "NOT_CHECKABLE")),
        "grader_status": grade["status"],
        "grader_errors": [str(error) for error in grade.get("errors", [])],
        "infrastructure_failure": bool(actual.get("infrastructure_failure", False)),
        "configuration_drift": bool(actual.get("configuration_drift", False)),
        "logical_call_cap_exceeded": bool(actual.get("logical_call_cap_exceeded", False)),
        "detected_incorrect_output": actual.get("outcome") == "DETECTED_INCORRECT_OUTPUT",
        "undetected_incorrect_output": bool(actual.get("undetected_incorrect_output", False)),
        "unintended_mutation": bool(actual.get("unintended_mutation", False)),
    }


def build_notebook_session(
    *,
    backend: ModelBackendProtocol,
    provider: str,
    model: str,
    server_root: Path,
    credential_source: str | None,
    timeout: float,
) -> DirectNotebookSession:
    """Compose the unchanged production notebook graph around one backend."""
    from wellplot.agent.code_mode.enrichment import SemanticEnricher
    from wellplot.agent.code_mode.facade import CodeModeCompileFacade
    from wellplot.agent.code_mode.planner import SemanticPlanner
    from wellplot.agent.code_mode.program_worker import ProgramSectionCompiler
    from wellplot.agent.code_mode.report_worker import ReportProgramCompiler
    from wellplot.agent.code_mode.source_loader import LogfileSourceLoader
    from wellplot.agent.code_mode.workflow import CodeModeGraphDependencies
    from wellplot.agent.session import AgentSession, AgentSessionConfig
    from wellplot.capabilities import create_builtin_registry

    registry = create_builtin_registry()
    dependencies = CodeModeGraphDependencies(
        planner=SemanticPlanner(backend=backend, registry=registry),
        enricher=SemanticEnricher(
            loader=LogfileSourceLoader(),
            allowed_roots={"server": server_root},
        ),
        report_compiler=ReportProgramCompiler(backend=backend, registry=registry),
        section_compiler=ProgramSectionCompiler(backend=backend, registry=registry),
    )
    return DirectNotebookSession(
        session=AgentSession(
            compiler=CodeModeCompileFacade(dependencies),
            config=AgentSessionConfig(timeout_seconds=timeout),
        ),
        provider=provider,
        model=model,
        credential_source=credential_source,
        server_root=server_root,
    )


@dataclass
class D4CampaignAdapter:
    """Own the complete nine-turn execution adapter for D4B and rehearsal."""

    repo_root: Path
    artifact_root: Path
    session: Any
    call_source: CampaignCallSource
    source_path: Path | None = None
    cbl_artifact_path: Path | None = None
    provider_backed: bool = False
    _current_by_case: dict[str, Path] = field(default_factory=dict)

    def bind_call_started(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Bind the campaign's durable custody to all backend calls."""
        self.call_source.bind_call_started(callback)

    def bind_call_completed(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Bind durable completion evidence to all backend calls."""
        self.call_source.bind_call_completed(callback)

    @property
    def logical_call_count(self) -> int:
        """Expose the authoritative observed-call cursor."""
        return self.call_source.logical_call_count

    def calls_since(self, cursor: int) -> list[LogicalCall]:
        """Return calls observed after one turn began."""
        return self.call_source.calls_since(cursor)

    @property
    def provider_calls(self) -> int:
        """Report provider-bound calls without relabeling them as HTTP attempts."""
        if not self.provider_backed:
            return 0
        return self.call_source.logical_call_count

    @property
    def endpoint_calls(self) -> int | None:
        """Return zero for rehearsal or unavailable for uninstrumented HTTP."""
        return 0 if not self.provider_backed else None

    @property
    def model_calls(self) -> int | None:
        """Return zero for rehearsal or unavailable for remote model execution."""
        return 0 if not self.provider_backed else None

    def _write_document(self, path: Path, payload: Mapping[str, Any]) -> None:
        """Persist one canonical document through the existing logfile mapping."""
        from wellplot.authoring import authoring_document_to_logfile_mapping

        document = AuthoringDocumentSpec.model_validate(payload)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(
                authoring_document_to_logfile_mapping(document),
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def _base_for(self, case_id: str) -> Path:
        """Create one independent frozen starting artifact per D4 case."""
        if case_id in self._current_by_case:
            return self._current_by_case[case_id]
        payload = copy.deepcopy(load_gold(self.repo_root)["canonical_las_seed"])
        case_root = self.artifact_root / "cases" / case_id
        case_root.mkdir(parents=True, exist_ok=True)
        source_path = self.source_path or self.repo_root / SOURCE_RELATIVE
        staged_source = case_root / source_path.name
        if not staged_source.exists():
            staged_source.symlink_to(source_path)
        payload["sections"][0]["data_source"]["source_path"] = source_path.name
        if case_id == "D4-L02":
            lower = copy.deepcopy(payload["sections"][0])
            payload["sections"][0]["id"] = "main-upper"
            payload["sections"][0]["title"] = "Main Log – Upper"
            lower["id"] = "main-lower"
            lower["title"] = "Main Log – Lower"
            for track in lower["tracks"]:
                for binding in track.get("bindings", []):
                    binding["binding_id"] = str(binding["binding_id"]).replace(
                        "main.", "main-lower."
                    )
            payload["sections"][0]["depth_range"] = [8400.0, 9300.0]
            lower["depth_range"] = [9300.0, 10200.0]
            payload["sections"] = [payload["sections"][0], lower]
        path = case_root / f"{case_id}.log.yaml"
        self._write_document(path, payload)
        self._write_document(path, load_logfile_document(path))
        self._current_by_case[case_id] = path
        return path

    def _write_cbl_scaffold(self, path: Path) -> None:
        """Create the D3-minimum CBL scaffold for a future live construction."""
        template_path = self.repo_root / "tests/fixtures/agentic_cbl/base.template.yaml"
        mapping = yaml.safe_load(template_path.read_text(encoding="utf-8"))
        case_root = path.parent
        main = self.repo_root / (
            "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Main.dlis"
        )
        repeat = self.repo_root / (
            "workspace/tutorials/agent_cbl_log_example_from_prompt/CBL_Repeat.dlis"
        )
        mapping["version"] = 1
        mapping["name"] = "D4 CBL scaffold"
        mapping["render"]["output_path"] = "d4-cbl-render.pdf"
        mapping["document"]["layout"]["remarks"] = []
        mapping["document"]["layout"]["log_sections"] = [
            {
                "id": "main_pass",
                "title": "Main Pass",
                "subtitle": "CBL/VDL packet main pass",
                "data": {
                    "source_path": os.path.relpath(main, case_root).replace(os.sep, "/"),
                    "source_format": "dlis",
                },
                "tracks": [{"id": "combo", "title": "Combo", "kind": "normal", "width_mm": 50}],
            },
            {
                "id": "repeat_pass",
                "title": "Repeat Pass",
                "subtitle": "CBL/VDL packet repeat pass",
                "data": {
                    "source_path": os.path.relpath(repeat, case_root).replace(os.sep, "/"),
                    "source_format": "dlis",
                },
                "tracks": [{"id": "combo", "title": "Combo", "kind": "normal", "width_mm": 50}],
            },
        ]
        mapping["document"]["bindings"]["channels"] = []
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")

    async def execute_turn(
        self,
        case: Mapping[str, Any],
        expected: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Execute one frozen turn through the real notebook-facing adapter."""
        turn_id = str(case["turn_id"])
        case_id = str(case["case_id"])
        turn_root = self.artifact_root / "turns" / turn_id.replace(":", "-")
        turn_root.mkdir(parents=True, exist_ok=True)

        if case["workflow"] == "CBL-CONSTRUCT":
            if self.cbl_artifact_path is not None:
                artifact = self.cbl_artifact_path
                render_path = turn_root / "cbl-render.pdf"
                render_path.write_bytes(b"prebuilt deterministic CBL render")
                return {
                    "outcome": None,
                    "before_path": artifact,
                    "after_path": artifact,
                    "starting_artifact_path": artifact,
                    "ending_artifact_path": artifact,
                    "canonical_before": {},
                    "canonical_after": {},
                    "artifact_path": artifact,
                    "rendered_artifact_path": artifact,
                    "render_path": render_path,
                    "persisted": True,
                    "rendered": True,
                    "execution_evidence": {
                        "accepted": True,
                        "persisted": True,
                        "rendered": True,
                    },
                    "provider": self.session.provider,
                    "model": self.session.model,
                }
            scaffold = turn_root / "cbl-scaffold.log.yaml"
            self._write_cbl_scaffold(scaffold)
            result = await self.session.run(
                goal=str(case["request"]),
                output_logfile=turn_root / "generated-cbl.log.yaml",
                source_logfile_path=scaffold,
            )
            artifact = turn_root / "generated-cbl.log.yaml"
            report_facts = getattr(result, "report_facts", {})
            succeeded = bool(report_facts.get("success"))
            actual: dict[str, Any] = {
                "outcome": None,
                "before_path": scaffold,
                "after_path": artifact,
                "starting_artifact_path": scaffold,
                "ending_artifact_path": artifact,
                "canonical_before": {},
                "canonical_after": {},
                "artifact_path": artifact,
                "rendered_artifact_path": None,
                "persisted": succeeded,
                "rendered": False,
                "provider": self.session.provider,
                "model": self.session.model,
                "execution_evidence": {
                    "accepted": succeeded,
                    "persisted": succeeded,
                    "rendered": False,
                },
            }
            _add_session_evidence(actual, result)
            if succeeded:
                render_path = turn_root / "cbl-render.pdf"
                render_started = time.perf_counter()
                rendered = await self.session.render_logfile_to_file(
                    logfile_path=artifact,
                    output_path=render_path,
                    overwrite=True,
                )
                actual["render_path"] = render_path
                actual["rendered_artifact_path"] = artifact
                actual["rendered"] = bool(rendered and render_path.is_file())
                actual["render_duration_seconds"] = time.perf_counter() - render_started
                actual["execution_evidence"]["rendered"] = actual["rendered"]
            return actual

        current = self._base_for(case_id)
        before = turn_root / "before.log.yaml"
        after = turn_root / "after.log.yaml"
        before.write_bytes(current.read_bytes())
        staged_turn_source = turn_root / (self.source_path or self.repo_root / SOURCE_RELATIVE).name
        if not staged_turn_source.exists():
            staged_turn_source.symlink_to(self.source_path or self.repo_root / SOURCE_RELATIVE)
        before_payload = load_logfile_document(before)
        result = await self.session.revise(
            feedback=str(case["request"]),
            logfile_path=current,
        )
        after.write_bytes(current.read_bytes())

        report_facts = getattr(result, "report_facts", {})
        succeeded = bool(report_facts.get("success"))
        actual: dict[str, Any] = {
            "outcome": None,
            "before_path": before,
            "after_path": after,
            "starting_artifact_path": before,
            "ending_artifact_path": after,
            "canonical_before": before_payload,
            "canonical_after": load_logfile_document(after),
            "persisted": succeeded,
            "rendered": False,
            "provider": self.session.provider,
            "model": self.session.model,
            "execution_evidence": {
                "accepted": succeeded,
                "persisted": succeeded,
                "rendered": False,
            },
        }
        actual["pre_bytes_sha256"] = sha256_file(before)
        actual["post_bytes_sha256"] = sha256_file(after)
        _add_session_evidence(actual, result)
        if succeeded:
            render_path = turn_root / "render.pdf"
            render_started = time.perf_counter()
            rendered = await self.session.render_logfile_to_file(
                logfile_path=after,
                output_path=render_path,
                overwrite=True,
            )
            actual["render_path"] = render_path
            actual["rendered"] = bool(rendered and render_path.is_file())
            actual["render_duration_seconds"] = time.perf_counter() - render_started
            actual["execution_evidence"]["rendered"] = actual["rendered"]
        else:
            actual.update(_observed_failure_facts(actual, before_payload))
        return actual


def load_logfile_document(path: Path) -> dict[str, Any]:
    """Project one logfile into the canonical JSON shape used by the grader."""
    from wellplot.authoring import load_authoring_document

    return load_authoring_document(path).model_dump(mode="json")


def create_live_campaign_adapter(
    *,
    repo_root: Path,
    artifact_root: Path,
    api_key: str | None,
    base_url: str | None,
    timeout: float,
    prompt_guard: Callable[[str], None] | None = None,
) -> D4CampaignAdapter:
    """Create the explicit D4B provider-backed adapter without fallback paths."""
    from wellplot.agent.direct_notebook import _provider_backend

    backend, credential_source = _provider_backend(
        provider=EXPECTED_PROVIDER,
        model=EXPECTED_MODEL,
        root=repo_root,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
    )
    calls: list[LogicalCall] = []
    ledger = LogicalCallLedger()
    counted = CountingBackend(
        delegate=backend,
        provider=EXPECTED_PROVIDER,
        model=EXPECTED_MODEL,
        calls=calls,
        ledger=ledger,
        prompt_guard=prompt_guard,
    )
    session = build_notebook_session(
        backend=counted,
        provider=EXPECTED_PROVIDER,
        model=EXPECTED_MODEL,
        server_root=repo_root,
        credential_source=credential_source,
        timeout=timeout,
    )
    return D4CampaignAdapter(
        repo_root=repo_root,
        artifact_root=artifact_root,
        session=session,
        call_source=CampaignCallSource(backends=(counted,), calls=calls, ledger=ledger),
        provider_backed=True,
    )


async def run_campaign(
    *,
    repo_root: Path,
    state_path: Path,
    journal_path: Path,
    preflight: Callable[[], dict[str, Any]],
    execution_factory: Callable[[], D4CampaignAdapter],
) -> dict[str, Any]:
    """Execute the frozen nine-turn campaign through the harness adapter."""
    cases = load_cases(repo_root)
    gold_cases = {item["turn_id"]: item for item in load_gold(repo_root)["cases"]}
    state, execution_context = start_campaign(
        state_path=state_path,
        journal_path=journal_path,
        preflight=preflight,
        execution_factory=execution_factory,
    )
    custody = CampaignCustody(
        state_path=state_path,
        journal=CampaignJournal(journal_path),
        state=state,
    )
    bind_call_started = getattr(execution_context, "bind_call_started", None)
    if callable(bind_call_started):
        bind_call_started(custody.record_call_started)
    bind_call_completed = getattr(execution_context, "bind_call_completed", None)
    if callable(bind_call_completed):
        bind_call_completed(custody.record_call_completed)
    rows: list[dict[str, Any]] = []
    try:
        for case in cases:
            expected = gold_cases[case["turn_id"]]
            started = time.perf_counter()
            call_cursor = execution_context.logical_call_count
            actual = dict(await execution_context.execute_turn(case, expected))
            observed_calls = execution_context.calls_since(call_cursor)
            duration = time.perf_counter() - started
            grade = grade_turn(actual, expected)
            actual["unintended_mutation"] = _grade_has_unintended_mutation(grade)
            actual["outcome"] = _observed_outcome(
                actual,
                case,
                actual.get("canonical_before", {}),
                grade,
            )
            actual["undetected_incorrect_output"] = (
                actual["outcome"] == "UNDETECTED_INCORRECT_OUTPUT"
            )
            actual["unintended_mutation"] = actual["outcome"] == "UNINTENDED_MUTATION"
            row = _campaign_turn_row(
                state=state,
                case=case,
                actual=actual,
                grade=grade,
                duration_seconds=duration,
                observed_calls=observed_calls,
            )
            custody.append_turn(row)
            rows.append(row)
            if row["infrastructure_failure"] or row["configuration_drift"]:
                break
        decision = derive_terminal_decision(rows)
        state["status"] = "COMPLETED" if decision != INCONCLUSIVE_DECISION else "INCONCLUSIVE"
        state["decision"] = decision
        state["completed_turns"] = len(rows)
        _atomic_json(state_path, state)
        custody.journal.append(
            {
                "event": "campaign_terminal",
                "experiment_version": EXPERIMENT_VERSION,
                "campaign_id": state["campaign_id"],
                "status": state["status"],
                "decision": decision,
                "completed_turns": len(rows),
                "logical_generation_calls": state["logical_generation_calls"],
            }
        )
        return {
            "decision": decision,
            "status": state["status"],
            "completed_turns": len(rows),
            "rows": rows,
            "logical_generation_calls": int(state["logical_generation_calls"]),
            "provider_calls": int(getattr(execution_context, "provider_calls", 0)),
            "endpoint_calls": getattr(execution_context, "endpoint_calls", None),
            "model_calls": getattr(execution_context, "model_calls", None),
        }
    except Exception as error:
        state["status"] = "INCONCLUSIVE"
        state["decision"] = INCONCLUSIVE_DECISION
        state["infrastructure_failure"] = True
        state["failure_type"] = type(error).__name__
        state["completed_turns"] = len(rows)
        _atomic_json(state_path, state)
        custody.journal.append(
            {
                "event": "campaign_terminal",
                "experiment_version": EXPERIMENT_VERSION,
                "campaign_id": state["campaign_id"],
                "status": "INCONCLUSIVE",
                "decision": INCONCLUSIVE_DECISION,
                "completed_turns": len(rows),
                "failure_type": type(error).__name__,
            }
        )
        return {
            "decision": INCONCLUSIVE_DECISION,
            "status": "INCONCLUSIVE",
            "completed_turns": len(rows),
            "rows": rows,
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
    finally:
        custody.journal.close()


def start_campaign(
    *,
    state_path: Path,
    journal_path: Path,
    preflight: Callable[[], dict[str, Any]],
    execution_factory: Callable[[], D4CampaignAdapter],
) -> tuple[dict[str, Any], D4CampaignAdapter]:
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
    return state, execution_factory()


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
    if operator == "length_at_least":
        return isinstance(actual, (list, tuple, dict, str)) and len(actual) >= int(expected)
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
    verifier = actual.get("verifier")
    if isinstance(verifier, Mapping):
        return dict(verifier)
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
    errors: list[str] = []
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
    if contract.get("kind") == "cbl":
        if actual.get("persisted") is not True:
            errors.append("cbl_persistence_not_proven")
        if actual.get("rendered") is not True:
            errors.append("cbl_render_not_proven")
        if actual.get("rendered_artifact_path") != actual.get("artifact_path"):
            errors.append("cbl_rendered_wrong_artifact")
        verifier_status = verifier.get("status", verifier.get("acceptance_status"))
        if actual.get("verifier_status", verifier_status) not in {"PASS", "accepted"}:
            errors.append("cbl_verifier_failed")
    elif contract.get("kind") == "safety":
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
        if actual.get("verifier_status", verifier_status) not in {
            "PASS",
            "accepted",
            "NOT_CHECKABLE",
        }:
            errors.append("verifier_failed")
    for flag in contract.get("required_true_flags", []):
        if actual.get(flag) is not True:
            errors.append(f"required_flag_not_true: {flag}")
    return {
        "turn_id": expected["turn_id"],
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "verifier_status": verifier.get("status", verifier.get("acceptance_status")),
        "verifier_requirements": [
            {"id": item.get("id"), "status": item.get("status")}
            for item in verifier.get("requirements", [])
            if isinstance(item, Mapping)
        ],
        "diff_status": "FAIL" if any("canonical_change" in error for error in errors) else "PASS",
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
        row.get("outcome")
        in {
            "DETECTED_INCORRECT_OUTPUT",
            "UNDETECTED_INCORRECT_OUTPUT",
            "UNINTENDED_MUTATION",
        }
        for row in rows
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
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--authorization-json", type=Path)
    args = parser.parse_args()
    if args.provider_free_preflight and args.execute_live:
        parser.error("choose exactly one of --provider-free-preflight or --execute-live")
    if not args.provider_free_preflight and not args.execute_live:
        parser.error("D4A requires --provider-free-preflight; D4B requires --execute-live")
    if args.authorization_json is None:
        parser.error("--authorization-json is required for frozen-contract attestation")
    try:
        raw_authorization = _load_json(args.authorization_json.resolve())
        if args.execute_live and raw_authorization.get("live_authorized") is not True:
            raise PreflightError("D4B requires live_authorized: true in the authorization record")
        authorization = FrozenAuthorization.from_mapping(raw_authorization)
        repo_root = args.repo_root.resolve()
        if args.provider_free_preflight:
            output = provider_free_preflight(repo_root, authorization)
        else:
            state_path = repo_root / STATE_RELATIVE
            journal_path = repo_root / JOURNAL_RELATIVE
            artifact_root = state_path.parent / "artifacts"
            output = asyncio.run(
                run_campaign(
                    repo_root=repo_root,
                    state_path=state_path,
                    journal_path=journal_path,
                    preflight=lambda: provider_free_preflight(repo_root, authorization),
                    execution_factory=lambda: create_live_campaign_adapter(
                        repo_root=repo_root,
                        artifact_root=artifact_root,
                        api_key=None,
                        base_url=None,
                        timeout=120.0,
                    ),
                )
            )
        print(json.dumps(output, indent=2, sort_keys=True))
    except PreflightError as error:
        status = "D4B_BLOCKED" if args.execute_live else "D4A_BLOCKED"
        print(json.dumps({"status": status, "reason": str(error)}, indent=2))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
