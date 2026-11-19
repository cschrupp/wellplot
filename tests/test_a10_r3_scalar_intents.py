"""Exercise compact A10 intents through the canonical provider-free graph."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError

from wellplot.agent.code_mode.canonical_workers import CanonicalReportWorker
from wellplot.agent.code_mode.enrichment import (
    ChannelContext,
    LoadedSource,
    SemanticEnricher,
    SourceCandidate,
    bind_semantic_publication_sources,
    reconciliation_channels,
    validate_enriched_snapshot,
)
from wellplot.agent.code_mode.facade import CodeModeCompileFacade, CodeModeCompileResult
from wellplot.agent.code_mode.planner import (
    PlannerAbstention,
    SemanticPlanner,
    _PlannerWirePlan,
)
from wellplot.agent.code_mode.typed_section_worker import CanonicalSectionWorker
from wellplot.agent.code_mode.workflow import CodeModeGraphDependencies
from wellplot.agent.providers.base import (
    ProviderMetrics,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from wellplot.authoring_reconciler import AuthoringReconciliationPlan, reconcile_authoring
from wellplot.capabilities import create_builtin_registry
from wellplot.model.authoring import AuthoringDocumentSpec
from wellplot.semantic_catalog import (
    EMPTY_SEMANTIC_CHANNEL_CATALOG,
    load_deployed_catalog_release,
)


@dataclass
class _Backend:
    responses: list[dict[str, object]]
    calls: list[str] = field(default_factory=list)

    async def generate_structured(
        self, request: StructuredGenerationRequest, *, response_model: type[BaseModel]
    ) -> StructuredGenerationResult:
        self.calls.append(response_model.__name__)
        return StructuredGenerationResult(
            value=response_model.model_validate(self.responses.pop(0)), metrics=ProviderMetrics()
        )


class _Loader:
    def load(self, path: Path, format_hint: str) -> LoadedSource:
        return LoadedSource(
            channels=tuple(
                ChannelContext(
                    mnemonic=name,
                    kind="scalar",
                    unit=unit,
                    physical_identity={"format": "LAS", "curve_index": index},
                )
                for index, (name, unit) in enumerate(
                    (("GR", "gAPI"), ("CBL", "mV"), ("ILD", "ohm.m"), ("NPHI", "%")), start=7
                )
            ),
        )


def _wire(
    action: str,
    channel: str,
    *,
    kind: str = "physical",
    hint: str | None = None,
    scale: dict[str, object] | None = None,
    target: str | None = None,
    sources: tuple[str, ...] = (),
) -> dict[str, object]:
    scalar = {"action": action, "channel_clue": channel, "channel_kind": kind}
    if scale is not None:
        scalar["scale"] = scale
    if target is not None:
        scalar["target_clue"] = target
    return {
        "version": "wellplot.semantic-plan.v2",
        "summary": "Apply the requested edit.",
        "section_tasks": [
            {
                "goal": "Apply the requested edit.",
                "existing_section_hint": hint,
                "source_hints": sources,
                "scalar_intent": scalar,
            }
        ],
    }


def _document(*, ambiguous: bool = False) -> AuthoringDocumentSpec:
    sections = [
        {
            "id": name.lower(),
            "title": name,
            "tracks": [{"id": "main-track", "title": "Main", "kind": "normal", "width_mm": 30}],
        }
        for name in (("Main", "Repeat") if ambiguous else ("Main",))
    ]
    return AuthoringDocumentSpec(name="Synthetic R3", sections=sections)


def _compile(
    tmp_path: Path,
    request: str,
    responses: list[dict[str, object]],
    document: AuthoringDocumentSpec,
    *,
    second_source: bool = False,
    approved_catalog_source: bool = False,
) -> tuple[CodeModeCompileResult, list[str]]:
    path = tmp_path / "synthetic.las"
    if not approved_catalog_source:
        path.touch()
    else:
        path = Path("workspace/data/30-23a-3 8117_d.las").resolve()
    sources = [
        SourceCandidate(
            candidate_id="metadata", root_id="test", path=str(path), trusted_format="las"
        )
    ]
    if second_source:
        other = tmp_path / "other.las"
        other.touch()
        sources.append(
            SourceCandidate(
                candidate_id="other", root_id="test", path=str(other), trusted_format="las"
            )
        )
    backend = _Backend(responses)
    facade = CodeModeCompileFacade(
        CodeModeGraphDependencies(
            planner=SemanticPlanner(backend=backend, registry=create_builtin_registry()),
            enricher=SemanticEnricher(loader=_Loader(), allowed_roots={"test": path.parent}),
            report_compiler=CanonicalReportWorker(backend=backend),
            section_compiler=CanonicalSectionWorker(backend=backend),
        )
    )
    result = asyncio.run(
        facade.compile(
            request=request,
            mode="revise",
            document=document,
            source_candidates=sources,
            timeout_seconds=1,
        )
    )
    return result, backend.calls


def _read_only_reconcile(
    result: CodeModeCompileResult, document: AuthoringDocumentSpec
) -> AuthoringReconciliationPlan:
    assert result.inspection_context is not None and result.merged_intent is not None
    validate_enriched_snapshot(result.inspection_context, document)
    contract = result.semantic_publication_contract
    catalog = EMPTY_SEMANTIC_CHANNEL_CATALOG
    if contract is not None:
        release = load_deployed_catalog_release()
        catalog = release.catalog
        contract = bind_semantic_publication_sources(contract, result.inspection_context)
        contract = contract.model_copy(update={"trusted_release": release})
    return reconcile_authoring(
        result.merged_intent,
        existing=document,
        available_channels=reconciliation_channels(result.inspection_context, result.merged_intent),
        semantic_catalog=catalog,
        semantic_publication_contract=contract,
    )


def test_compact_physical_curve_uses_host_target(tmp_path: Path) -> None:
    """The planner neither declares an existing track nor selects an implicit section."""
    document = _document()
    before = document.model_dump()
    result, calls = _compile(
        tmp_path,
        "Plot physical GR.",
        [
            _wire("plot_curve", "GR", hint="Incorrect hint"),
            {
                "action": "add_binding",
                "target": {"handle": "track-1"},
                "binding": {"semantic_id": "request.binding.1", "channel": "GR"},
            },
        ],
        document,
    )
    assert result.success, result.diagnostics
    assert result.inspection_context.plan.section_tasks[0].existing_section_hint is None
    assert result.merged_intent.curve_bindings[0].track_id == "main-track"
    assert _read_only_reconcile(result, document).ready
    assert len(calls) == 2
    assert document.model_dump() == before


def test_compact_curve_preserves_explicit_section_track_and_source(tmp_path: Path) -> None:
    """An explicit request can identify one section and source in a larger context."""
    document = _document(ambiguous=True)
    result, calls = _compile(
        tmp_path,
        "In Main section, plot GR from synthetic.las on the Main track.",
        [
            _wire("plot_curve", "GR", hint="Main", target="Main", sources=("synthetic.las",)),
            {
                "action": "add_binding",
                "target": {"handle": "track-1"},
                "binding": {"semantic_id": "request.binding.1", "channel": "GR"},
            },
        ],
        document,
        second_source=True,
    )
    assert result.success, result.diagnostics
    section = result.inspection_context.sections[0]
    assert section.section_id == "main"
    assert [source.candidate_id for source in section.sources] == ["metadata"]
    assert _read_only_reconcile(result, document).ready
    assert len(calls) == 2


def test_compact_semantic_curve_reaches_trusted_catalog_resolution(tmp_path: Path) -> None:
    """The request keeps its semantic spelling until the existing authoring resolver."""
    if not Path("workspace/data/30-23a-3 8117_d.las").is_file():
        pytest.skip("The hash-bound catalog qualification fixture is local only.")
    document = _document()
    result, calls = _compile(
        tmp_path,
        "Plot Gamma Ray.",
        [
            _wire("plot_curve", "Gamma Ray", kind="semantic"),
            {
                "action": "add_binding",
                "target": {"handle": "track-1"},
                "binding": {"semantic_id": "request.binding.1", "channel": "Gamma Ray"},
            },
        ],
        document,
        approved_catalog_source=True,
    )
    assert result.success, result.diagnostics
    assert result.merged_intent.curve_bindings[0].channel == "Gamma Ray"
    assert result.semantic_publication_contract is not None
    disposition = _read_only_reconcile(result, document)
    assert disposition.ready, disposition.issues
    assert len(disposition.semantic_resolutions) == 1
    assert disposition.semantic_resolutions[0].physical_mnemonic == "GR"
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("request_text", "channel", "scale"),
    [
        (
            "Add a CBL track and set its scale to linear 0\u20131 mV.",
            "CBL",
            {"kind": "linear", "minimum": 0, "maximum": 1, "unit": "mV"},
        ),
        ("Add an exact physical GR track.", "GR", None),
    ],
)
def test_compact_track_lowers_once_with_exact_presentation(
    tmp_path: Path, request_text: str, channel: str, scale: dict[str, object] | None
) -> None:
    """A single host track operation preserves one binding and the explicit scale."""
    track = {
        "semantic_id": channel.lower(),
        "kind": "normal",
        "title": channel,
        "bindings": [
            {"kind": "curve", "channel": channel, "semantic_id": f"{channel.lower()}.binding.1"}
        ],
    }
    if scale:
        track["x_scale"] = scale
    document = _document()
    result, calls = _compile(
        tmp_path,
        request_text,
        [_wire("add_track", channel, scale=scale), {"action": "add_track", "track": track}],
        document,
    )
    assert result.success, result.diagnostics
    task = result.inspection_context.plan.section_tasks[0]
    assert [(op.verb, op.object_kind) for op in task.operations] == [("CREATE", "track")]
    tracks = result.merged_intent.sections[0].tracks
    assert len(tracks) == 1
    assert [binding.channel for binding in tracks[0].bindings] == [channel]
    if scale:
        assert tracks[0].x_scale.model_dump(exclude_defaults=True) == {
            key: value for key, value in scale.items() if key != "kind"
        }
        assert tracks[0].x_scale.kind == "linear"
    else:
        assert tracks[0].x_scale is None
    disposition = _read_only_reconcile(result, document)
    assert disposition.ready, disposition.issues
    assert tracks[0].width_mm == 28
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("request_text", "clue", "kind"),
    [
        ("Plot deep resistivity.", "deep resistivity", "semantic"),
        ("Show neutron porosity.", "NPHI", "physical"),
        ("Plot resistivity.", "ILD", "physical"),
        ("Plot physical GR.", "CGR", "physical"),
    ],
)
def test_unapproved_terms_and_substitutions_cannot_dispatch(
    tmp_path: Path, request_text: str, clue: str, kind: str
) -> None:
    """Wire-valid intent is not permission for a source or channel guess."""
    result, calls = _compile(
        tmp_path, request_text, [_wire("plot_curve", clue, kind=kind)], _document()
    )
    assert not result.success and result.merged_intent is None
    assert not result.workers
    assert result.diagnostics[0].code == "planner.scalar_intent_not_authorized"
    assert result.diagnostics[0].failure_owner == "host_safety"
    assert calls == ["_PlannerWirePlan"]


@pytest.mark.parametrize("second_source", [False, True])
def test_model_hint_cannot_resolve_implicit_context_ambiguity(
    tmp_path: Path, second_source: bool
) -> None:
    """A partial intent cannot dispatch on ambiguous section or source context."""
    result, calls = _compile(
        tmp_path,
        "Plot physical GR.",
        [_wire("plot_curve", "GR", hint="Main")],
        _document(ambiguous=not second_source),
        second_source=second_source,
    )
    assert not result.success and result.merged_intent is None
    assert not result.workers
    assert "ambiguous" in result.diagnostics[0].code
    assert calls == ["_PlannerWirePlan"]


@pytest.mark.parametrize(
    "scale", [None, {"kind": "linear", "minimum": 0, "maximum": 1, "unit": "V"}]
)
def test_missing_or_changed_scale_stops_before_worker(
    tmp_path: Path, scale: dict[str, object] | None
) -> None:
    """Do not repair model omissions or reinterpret requested measurement units."""
    result, calls = _compile(
        tmp_path,
        "Add a CBL track and set its scale to linear 0\u20131 mV.",
        [_wire("add_track", "CBL", scale=scale)],
        _document(),
    )
    assert not result.success and result.merged_intent is None
    assert result.diagnostics[0].code == "planner.scalar_intent_not_authorized"
    assert calls == ["_PlannerWirePlan"]


def test_typed_abstention_cannot_turn_into_work(tmp_path: Path) -> None:
    """The unresolved mixed request remains an explicit no-work outcome."""
    payload = {
        "version": "wellplot.semantic-plan.v2",
        "summary": "Report title and unresolved curve requested.",
        "abstention": {"reason": "ambiguous", "unresolved": ["Which resistivity curve?"]},
    }
    schema = Draft202012Validator(_PlannerWirePlan.model_json_schema())
    schema.validate(payload)
    invalid = {**_wire("plot_curve", "GR"), "abstention": payload["abstention"]}
    assert not schema.is_valid(invalid)
    with pytest.raises(ValidationError, match="cannot contain executable work"):
        _PlannerWirePlan.model_validate(invalid)
    backend = _Backend([payload])
    planner = SemanticPlanner(backend=backend, registry=create_builtin_registry())
    with pytest.raises(PlannerAbstention) as caught:
        asyncio.run(
            planner.plan(
                request="Set the report title to 'Log' and plot resistivity.",
                mode="revise",
                timeout_seconds=1,
            )
        )
    assert caught.value.abstention.unresolved == ("Which resistivity curve?",)

    result, calls = _compile(
        tmp_path, "Set the report title to 'Log' and plot resistivity.", [payload], _document()
    )
    assert not result.success and result.merged_intent is None and not result.workers
    assert result.diagnostics[0].code == "planner.model_abstention"
    assert calls == ["_PlannerWirePlan"]
