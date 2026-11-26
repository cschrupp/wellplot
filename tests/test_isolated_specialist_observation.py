"""First-response qualification through the canonical HTTP provider."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from scripts.nlp_d4_live_acceptance import CountingBackend

from wellplot.agent.code_mode.canonical_workers import CanonicalReportWorker
from wellplot.agent.code_mode.typed_section_worker import CanonicalSectionWorker
from wellplot.agent.providers.base import ProviderRequestError, StructuredGenerationRequest
from wellplot.agent.providers.openai_compat_v2 import OpenAICompatibleBackendV2
from wellplot.model.authoring import AuthoringDocumentSpec

RESEARCH = Path(__file__).resolve().parents[1] / "docs/research"


def _finding(disposition: str) -> dict[str, str]:
    return {"disposition": disposition, "explanation": "Grounded in inspected state."}


def _binding(handle: str, channel: str) -> dict[str, object]:
    return {
        "action": "add_binding",
        "target": {"handle": handle},
        "binding": {"semantic_id": "new-curve", "channel": channel},
    }


def test_first_response_boundaries() -> None:
    """Exercise both workers without calling production compilation."""

    async def run() -> None:
        panel = json.loads((RESEARCH / "WELLPLOT_V2_SPECIALIST_PANEL.json").read_bytes())
        assert [case["id"] for case in panel] == [f"W{i:02d}" for i in range(1, 9)]
        decisions = [
            {"title": "Winter Survey", "subtitle": "Station 12"},
            {"detail_fields": [{"slot_id": "operator-detail", "value": "Northstar"}]},
            _finding("already_satisfied"),
            _binding("acoustics", "SLOW"),
            {
                "action": "add_track",
                "track": {
                    "semantic_id": "pressure-track",
                    "kind": "normal",
                    "title": "Pressure",
                    "bindings": [{"semantic_id": "press", "channel": "PRESS"}],
                },
            },
            _finding("unavailable"),
            _finding("clarification"),
            _binding("bounds", "UPPER"),
        ]
        actual = []
        for case, decision in zip(panel, decisions, strict=True):
            role = case["role"]
            prompt = (RESEARCH / f"WELLPLOT_V2_SPECIALIST_{role.upper()}.md").read_text()
            document = AuthoringDocumentSpec.model_validate(case["document"])
            user = json.dumps(
                {
                    "dialogue": [],
                    "workflow": {"pending": [], "verified_results": []},
                    **case,
                    "document": document.model_dump(mode="json"),
                }
            )
            content = {"decision": decision, "rationale": "Synthetic first response."}
            if case["id"] == "W08":
                content["pending_objective"] = "Blue between-curve fill after verified co-location."

            def respond(
                request: httpx.Request,
                case_id: str = case["id"],
                prompt: str = prompt,
                user: str = user,
                content: dict[str, object] = content,
            ) -> httpx.Response:
                body = json.loads(request.content)
                actual.append(case_id)
                assert body["messages"] == [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user},
                ]
                assert body["response_format"]["json_schema"]["schema"]["properties"]["decision"]
                assert "required_action" not in user
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {"message": {"content": json.dumps(content)}, "finish_reason": "stop"}
                        ]
                    },
                )

            async with httpx.AsyncClient(
                transport=httpx.MockTransport(respond), trust_env=False
            ) as http:

                async def create(**arguments: object) -> object:
                    response = await http.post(
                        "http://example.invalid/v1/chat/completions", json=arguments
                    )
                    return response.json()

                client = SimpleNamespace(
                    chat=SimpleNamespace(completions=SimpleNamespace(create=create))
                )
                counted = CountingBackend(
                    delegate=OpenAICompatibleBackendV2(
                        model="mock", client=client, structured_output="json_schema"
                    ),
                    max_calls=1,
                    specialist_observation=True,
                )
                worker_type = CanonicalReportWorker if role == "report" else CanonicalSectionWorker
                worker = worker_type(counted)
                request = StructuredGenerationRequest(prompt, user, 10, 0, 4096)
                result = await worker.observe_first_response(request)
                assert result.value.rationale == content["rationale"]
                assert len(counted.calls) == 1
                content.clear()
                invalid_backend = CountingBackend(
                    delegate=counted.delegate, max_calls=1, specialist_observation=True
                )
                with pytest.raises(ProviderRequestError):
                    await worker_type(invalid_backend).observe_first_response(request)
        assert actual == [case["id"] for case in panel for _ in range(2)]

    asyncio.run(asyncio.wait_for(run(), timeout=10))
