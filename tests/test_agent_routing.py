"""Focused tests for the CM-53 public engine selector."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import anyio
import pytest

from wellplot.agent.core import AuthoringSession, run_authoring_request
from wellplot.agent.notebook import create_project_session
from wellplot.agent.routing import (
    create_authoring_session,
    normalize_authoring_engine,
)


def test_engine_selector_accepts_only_canonical_values() -> None:
    """Accept only the canonical engine selector value."""
    assert normalize_authoring_engine("v2") == "v2"
    for invalid in ("v1", "legacy", "code_mode", "auto", "default", "v3", "", None):
        with pytest.raises(ValueError, match="exactly 'v2'"):
            normalize_authoring_engine(invalid)  # type: ignore[arg-type]


def test_project_session_routes_only_to_the_canonical_engine() -> None:
    """Route notebook construction through the sole canonical engine."""
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        v2_session = object()
        with mock.patch(
            "wellplot.agent.notebook.create_authoring_session",
            return_value=v2_session,
        ) as factory:
            session, _ = create_project_session(
                server_root=root,
                project_dir="workspace/demo",
                provider="openai",
                model="demo-model",
            )

        assert session.authoring_session is v2_session
        assert session.engine == "v2"
        assert factory.call_args.kwargs["engine"] == "v2"

        with pytest.raises(ValueError, match="exactly 'v2'"):
            create_project_session(
                server_root=root,
                project_dir="workspace/legacy",
                provider="openai",
                model="demo-model",
                engine="v1",  # type: ignore[arg-type]
            )


def test_v1_selector_cannot_construct_a_legacy_session() -> None:
    """Reject the retired v1 selector before any session construction."""
    with pytest.raises(ValueError, match="exactly 'v2'"):
        create_authoring_session(
            engine="v1",
            provider="openai",
            model="demo-model",
            server_root=None,
            api_key=None,
            base_url=None,
            timeout=None,
        )


def test_default_v2_failure_never_falls_back_to_v1() -> None:
    """Keep a v2 failure bounded instead of silently retrying through v1."""

    class FailingV2Session:
        async def run(self, **_: object) -> object:
            raise RuntimeError("v2 provider failed")

    with (
        mock.patch(
            "wellplot.agent.direct_notebook.create_direct_notebook_session",
            return_value=FailingV2Session(),
        ),
        mock.patch.object(
            AuthoringSession,
            "from_local_mcp",
            side_effect=AssertionError("v1 fallback must not be attempted"),
        ),
        pytest.raises(RuntimeError, match="v2 provider failed"),
    ):
        anyio.run(
            partial(
                run_authoring_request,
                goal="Build a draft.",
                output_logfile="draft.log.yaml",
                example_id="starter",
                provider="openai",
                model="demo-model",
            )
        )


def test_v2_helper_preserves_max_rounds_without_creating_extra_attempts() -> None:
    """Pass the compatibility budget once without adding v2 attempts."""

    class RecordingV2Session:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def run(self, **kwargs: object) -> object:
            self.calls.append(kwargs)
            return object()

    selected = RecordingV2Session()
    with mock.patch(
        "wellplot.agent.direct_notebook.create_direct_notebook_session",
        return_value=selected,
    ):
        result = anyio.run(
            partial(
                run_authoring_request,
                goal="Build a bounded draft.",
                output_logfile="draft.log.yaml",
                example_id="starter",
                provider="openai",
                model="demo-model",
                max_rounds=100,
            )
        )

    assert result is not None
    assert len(selected.calls) == 1
    assert selected.calls[0]["max_rounds"] == 100
