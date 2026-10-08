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
import subprocess
import uuid
from collections.abc import Callable, Sequence
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
STATE_RELATIVE = Path("workspace/evaluations/d4-live-acceptance/d4-live-v1.state.json")
JOURNAL_RELATIVE = Path("workspace/evaluations/d4-live-acceptance/d4-live-v1.jsonl")
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
    return {
        "baseline": PRODUCTION_BASELINE,
        "current": _git(repo_root, "rev-parse", "HEAD"),
        "changed_files": [],
    }


def assert_campaign_paths_absent(state_path: Path, journal_path: Path) -> None:
    """Reject any existing state or journal, including zero-length files."""
    if state_path.exists() or journal_path.exists():
        raise PreflightError("D4 campaign artifacts already exist; resume is forbidden")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


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
        "live_harness_checkpoint": provenance["current_checkout"],
        "status": "STARTED",
        "logical_generation_calls": 0,
    }
    _atomic_json(state_path, state)
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


def grade_turn(actual: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    """Grade bounded synthetic turn evidence without provider material."""
    outcome = actual.get("outcome")
    expected_outcome = expected.get("expected_outcome")
    errors: list[str] = []
    if outcome != expected_outcome:
        errors.append("outcome_mismatch")
    if expected_outcome == "SAFE_ACTIONABLE_FAILURE":
        if actual.get("changed") is not False:
            errors.append("failure_mutated_artifact")
        if actual.get("pre_bytes_sha256") != actual.get("post_bytes_sha256"):
            errors.append("failure_bytes_changed")
        if not actual.get("diagnostic_code"):
            errors.append("missing_actionable_diagnostic")
    if expected_outcome == "DIRECT_CORRECT" and actual.get("verifier_status") != "PASS":
        errors.append("verifier_failed")
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


def provider_free_preflight(repo_root: Path) -> dict[str, Any]:
    """Run all D4A checks without credentials, endpoint access, or provider creation."""
    if _git(repo_root, "status", "--porcelain"):
        raise PreflightError("working tree must be clean for provider-free preflight")
    current = _git(repo_root, "rev-parse", "HEAD")
    cases = load_cases(repo_root)
    gold = load_gold(repo_root)
    las = preflight_las_source(repo_root)
    dlis = preflight_dlis_sources(repo_root)
    sdk = inspect_openai_retry_policy()
    production = verify_production_identity(repo_root)
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "current_checkout": current,
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
    args = parser.parse_args()
    if not args.provider_free_preflight:
        parser.error("D4A only supports --provider-free-preflight; D4B is not authorized")
    try:
        print(
            json.dumps(
                provider_free_preflight(args.repo_root.resolve()),
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
