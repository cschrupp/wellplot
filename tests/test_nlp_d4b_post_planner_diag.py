"""Provider-free reproduction of the D4 CBL post-planner path."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts import nlp_d4_live_acceptance as d4
from tests._mcp_fixtures import REPO_ROOT
from tests.test_nlp_d4r1_integrated_acceptance import _D4R1Backend

from wellplot.agent.code_mode.section_leaf_safety import project_section_leaf_request


class _RecordingNotebookSession:
    """Retain only the bounded public result for local stage diagnosis."""

    def __init__(self, delegate: object) -> None:
        self.delegate = delegate
        self.result: object | None = None

    @property
    def provider(self) -> str:
        return self.delegate.provider

    @property
    def model(self) -> str:
        return self.delegate.model

    async def run(self, **kwargs: object) -> object:
        self.result = await self.delegate.run(**kwargs)
        return self.result

    async def render_logfile_to_file(self, **kwargs: object) -> object:
        return await self.delegate.render_logfile_to_file(**kwargs)


def test_d4_cbl_post_planner_path_reproduces_provider_free() -> None:
    """Exercise the exact CBL adapter path without a provider or campaign state."""
    case = next(item for item in d4.load_cases(REPO_ROOT) if item["turn_id"] == "D4-C01:C01")
    expected = next(
        item for item in d4.load_gold(REPO_ROOT)["cases"] if item["turn_id"] == "D4-C01:C01"
    )
    backend = _D4R1Backend()
    backend.prepare(str(case["request"]))

    with TemporaryDirectory(dir=REPO_ROOT) as temporary:
        artifact_root = Path(temporary)
        production_session = d4.build_notebook_session(
            backend=backend,
            provider="deterministic",
            model="d4-post-planner-diagnostic",
            server_root=REPO_ROOT,
            credential_source="diagnostic",
            timeout=10.0,
        )
        session = _RecordingNotebookSession(production_session)
        adapter = d4.D4CampaignAdapter(
            repo_root=REPO_ROOT,
            artifact_root=artifact_root,
            session=session,
            call_source=d4.CampaignCallSource(backends=(), calls=[]),
        )

        try:
            actual = asyncio.run(adapter.execute_turn(case, expected))
        except Exception as error:
            raise AssertionError(
                f"Stage A failed after {backend.last_stage}: {type(error).__name__}"
            ) from error

    assert len(backend.structured_requests) == 4
    report_facts = getattr(session.result, "report_facts", None)
    if backend.program_calls != 0:
        raise AssertionError(
            f"program_calls={backend.program_calls}; report_facts={report_facts!r}"
        )
    assert actual["persisted"] is True


def test_frozen_cbl_request_projects_scalar_curve_intent() -> None:
    """The mixed CBL/VDL request must not enter the raster-only ambiguity guard."""
    case = next(item for item in d4.load_cases(REPO_ROOT) if item["turn_id"] == "D4-C01:C01")
    evidence = project_section_leaf_request(str(case["request"]))
    assert evidence.curve_explicit is True
    assert evidence.raster_explicit is True
