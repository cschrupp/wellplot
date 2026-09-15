"""Run the six-live-run CM-43 section A/B experiment."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wellplot.agent.graph.provider_adapter import ExistingProviderStructuredAdapter
from wellplot.agent.providers._openai_responses import load_openai_client
from wellplot.agent.providers.openai_compat import OpenAICompatibleAuthoringBackend
from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2

try:
    from scripts.cbl_section_ab import (
        CBLExperimentCase,
        LegacyBackendRecorder,
        evaluate_gate,
        run_ab,
        write_jsonl,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from cbl_section_ab import (  # type: ignore[no-redef]
        CBLExperimentCase,
        LegacyBackendRecorder,
        evaluate_gate,
        run_ab,
        write_jsonl,
    )


@dataclass(frozen=True, slots=True)
class _GenerationSettings:
    """Provider settings shared by both live engine factories."""

    base_url: str
    api_key: str
    temperature: float | None
    top_p: float | None
    max_output_tokens: int | None
    max_tokens_parameter: str
    timeout_seconds: float


class _ConfiguredCompletions:
    """Inject identical generation settings into legacy Chat requests."""

    def __init__(self, delegate: object, settings: _GenerationSettings) -> None:
        self._delegate = delegate
        self._settings = settings
        self.calls = 0

    def create(self, **arguments: object) -> object:
        """Forward a request while filling only explicitly configured settings."""
        self.calls += 1
        if self._settings.temperature is not None:
            arguments.setdefault("temperature", self._settings.temperature)
        if self._settings.top_p is not None:
            arguments.setdefault("top_p", self._settings.top_p)
        if self._settings.max_output_tokens is not None:
            arguments.setdefault(
                self._settings.max_tokens_parameter,
                self._settings.max_output_tokens,
            )
        return self._delegate.create(**arguments)  # type: ignore[attr-defined]


class _ConfiguredChat:
    """Proxy the Chat Completions namespace used by the legacy adapter."""

    def __init__(self, delegate: object, settings: _GenerationSettings) -> None:
        self.completions = _ConfiguredCompletions(
            delegate.__getattribute__("completions"),
            settings,
        )


class _ConfiguredClient:
    """Proxy a provider client without retaining or exposing credentials."""

    def __init__(self, delegate: object, settings: _GenerationSettings) -> None:
        self.chat = _ConfiguredChat(delegate.__getattribute__("chat"), settings)

    @property
    def provider_generation_calls(self) -> int:
        """Expose the Chat request count to the v1 recorder."""
        return self.chat.completions.calls


def _load_api_key(root: Path, *, key_file: str | None, key_env: str) -> str:
    """Load one explicit local key without printing it or accepting empty values."""
    environment_value = os.getenv(key_env, "").strip()
    if environment_value:
        return environment_value
    if key_file:
        path = Path(key_file)
        if not path.is_absolute():
            path = root / path
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    source = f"{key_env} or {key_file!r}" if key_file else key_env
    raise RuntimeError(f"No API key found in {source}.")


def _factory_pair(
    *,
    root: Path,
    settings: _GenerationSettings,
    model: str,
) -> tuple[Any, Any]:
    """Build case-aware factories over one provider configuration."""

    def v1_factory(case: CBLExperimentCase) -> ExistingProviderStructuredAdapter:
        """Create a fresh legacy structured adapter for one frozen case."""
        del case
        raw_client = load_openai_client(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
        )
        client = _ConfiguredClient(raw_client, settings)
        backend = OpenAICompatibleAuthoringBackend(
            model=model,
            client=client,
            base_url=settings.base_url,
            credential_source="explicit live-evaluation configuration",
        )
        return ExistingProviderStructuredAdapter(LegacyBackendRecorder(backend))

    def v2_factory(case: CBLExperimentCase) -> OpenAICompatibleBackendV2:
        """Create a fresh v2 program adapter for one frozen case."""
        del case
        raw_client = load_openai_client(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
        )
        return OpenAICompatibleBackendV2(
            model=model,
            client=_ConfiguredClient(raw_client, settings),
            max_tokens_parameter=settings.max_tokens_parameter,  # type: ignore[arg-type]
        )

    return v1_factory, v2_factory


def _parser() -> argparse.ArgumentParser:
    """Build the explicit live-run command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--provider", default="openai_compat")
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key-file")
    parser.add_argument("--api-key-env", default="OPENAI_COMPAT_API_KEY")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--top-p", type=float, default=None)
    parser.add_argument("--max-output-tokens", type=int, default=None)
    parser.add_argument(
        "--max-tokens-parameter",
        choices=("max_completion_tokens", "max_tokens"),
        default="max_completion_tokens",
    )
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/evaluations/agent-code-mode/CM-43-live-runs.jsonl"),
    )
    return parser


async def _run(arguments: argparse.Namespace) -> dict[str, object]:
    """Run both engines three times and persist redacted evidence."""
    root = arguments.repo_root.resolve()
    if arguments.timeout <= 0:
        raise ValueError("--timeout must be greater than zero.")
    api_key = _load_api_key(
        root,
        key_file=arguments.api_key_file,
        key_env=arguments.api_key_env,
    )
    case = CBLExperimentCase.load(
        fixture_root=root / "tests" / "fixtures" / "agentic_cbl",
        provider=arguments.provider,
        model=arguments.model,
        temperature=arguments.temperature,
        top_p=arguments.top_p,
        max_output_tokens=arguments.max_output_tokens,
        timeout_seconds=arguments.timeout,
        run_count=3,
    )
    settings = _GenerationSettings(
        base_url=arguments.base_url,
        api_key=api_key,
        temperature=arguments.temperature,
        top_p=arguments.top_p,
        max_output_tokens=arguments.max_output_tokens,
        max_tokens_parameter=arguments.max_tokens_parameter,
        timeout_seconds=arguments.timeout,
    )
    v1_factory, v2_factory = _factory_pair(
        root=root,
        settings=settings,
        model=arguments.model,
    )
    rows = await run_ab(
        case,
        v1_model_factory=v1_factory,
        v2_backend_factory=v2_factory,
        live=True,
    )
    output = arguments.output
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(output, rows)
    return {
        "output": str(output),
        "row_count": len(rows),
        "experiment_fingerprint": case.experiment_fingerprint,
        "gate": evaluate_gate(rows),
    }


def main() -> int:
    """Run CM-43 and print only non-secret summary evidence."""
    arguments = _parser().parse_args()
    result = asyncio.run(_run(arguments))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
