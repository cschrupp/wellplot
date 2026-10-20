"""Render sealed D5 model-I/O custody as a human-readable HTML report."""

# The embedded HTML/CSS template intentionally contains long presentation lines.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import html
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from scripts import nlp_d4_live_acceptance as d4


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read one append-only JSONL artifact without contacting a provider."""
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _pretty(value: object) -> str:
    """Format one bounded structure for a preformatted HTML block."""
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def _message_content(response: object) -> object:
    """Project assistant content from one raw response envelope."""
    if not isinstance(response, dict):
        return None
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    return message.get("content") if isinstance(message, dict) else None


def _request_parts(request: object) -> tuple[object, object, object, object]:
    """Extract display-only prompt/schema/control projections from a request body."""
    if not isinstance(request, dict):
        return None, None, None, None
    messages = request.get("messages")
    system = user = None
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            if message.get("role") == "system":
                system = message.get("content")
            elif message.get("role") == "user":
                user = message.get("content")
    controls = {
        key: value for key, value in request.items() if key not in {"messages", "response_format"}
    }
    return system, user, request.get("response_format"), controls


def _block(title: str, value: object) -> str:
    """Return one escaped preformatted inspection block."""
    return f"<h5>{html.escape(title)}</h5><pre>{html.escape(_pretty(value))}</pre>"


def render_report(repo_root: Path, campaign_dir: Path, output: Path) -> None:
    """Render one sealed campaign using only local custody and frozen fixtures."""
    state_path = next(campaign_dir.glob("*.state.json"), None)
    evidence_path = next(campaign_dir.glob("*.evidence.jsonl"), None)
    model_io_path = next(campaign_dir.glob("*.model-io.jsonl"), None)
    if state_path is None or evidence_path is None:
        raise ValueError("campaign state/evidence artifacts are incomplete")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    evidence = {row["turn_id"]: row for row in _read_jsonl(evidence_path)}
    model_io = _read_jsonl(model_io_path) if model_io_path else []
    requests: dict[tuple[str, int, int], dict[str, Any]] = {}
    responses: dict[tuple[str, int, int], dict[str, Any]] = {}
    results: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in model_io:
        if row.get("event") == "logical_call_result":
            results[str(row.get("turn_id"))].append(row)
        elif row.get("event") == "physical_request":
            key = (
                str(row.get("turn_id")),
                int(row.get("logical_call_index", 0)),
                int(row.get("physical_attempt", 0)),
            )
            requests[key] = row
        elif row.get("event") == "physical_response":
            key = (
                str(row.get("turn_id")),
                int(row.get("logical_call_index", 0)),
                int(row.get("physical_attempt", 0)),
            )
            responses[key] = row
    calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for key in sorted(set(requests) | set(responses)):
        merged = dict(requests.get(key, {}))
        merged.update(responses.get(key, {}))
        calls[key[0]].append(merged)
    cases = d4.load_cases(repo_root)
    gold = {row["turn_id"]: row for row in d4.load_gold(repo_root)["cases"]}
    sections: list[str] = []
    toc: list[str] = []
    for case in cases:
        turn_id = str(case["turn_id"])
        anchor = turn_id.replace(":", "-")
        toc.append(f'<a href="#{html.escape(anchor)}">{html.escape(turn_id)}</a>')
        evidence_row = evidence.get(turn_id, {})
        timeline: list[str] = []
        for call in calls.get(turn_id, []):
            request = call.get("request_json")
            system, user, schema, controls = _request_parts(request)
            response = call.get("response_json")
            timeline.append(
                "<article class='call-card'>"
                f"<h4>Logical call #{html.escape(str(call.get('logical_call_index')))} "
                f"- {html.escape(str(call.get('role')))}</h4>"
                f"<p>Physical attempt: {html.escape(str(call.get('physical_attempt')))}; "
                f"model: {html.escape(str(call.get('model')))}</p>"
                f"{_block('SYSTEM PROMPT', system)}"
                f"{_block('USER PROMPT', user)}"
                f"{_block('RESPONSE JSON SCHEMA', schema)}"
                f"{_block('REQUEST CONTROLS', controls)}"
                f"{_block('RAW ASSISTANT MESSAGE', _message_content(response))}"
                f"<details><summary>Raw provider response body</summary>{_block('RESPONSE', response)}</details>"
                f"<p class='digest'>Request SHA256: <code>{html.escape(str(call.get('request_sha256')))}</code><br>"
                f"Response SHA256: <code>{html.escape(str(call.get('response_sha256')))}</code></p>"
                "</article>"
            )
        result_html = "".join(
            _block("CANONICAL ENGINE RESULT", row) for row in results.get(turn_id, [])
        )
        if not timeline:
            timeline = ["<p class='missing'>MODEL-I/O NOT PRESERVED FOR THIS CAMPAIGN.</p>"]
        sections.append(
            f"<article class='turn' id='{html.escape(anchor)}'>"
            f"<h2>{html.escape(turn_id)}</h2>"
            f"<h3>1. User request</h3><pre>{html.escape(str(case['request']))}</pre>"
            f"<h3>2. Expected behavior</h3><p>{html.escape(str(case['expected_outcome']))}</p>"
            f"<details><summary>Exact frozen verifier contract</summary>{_block('GOLD', gold[turn_id]['contract'])}</details>"
            f"<h3>3. Model-call timeline</h3>{''.join(timeline)}"
            f"<h3>4. Final WellPlot result</h3>{_block('SEALED EVIDENCE', evidence_row)}"
            f"{result_html}"
            "</article>"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>D5-5 Inspectable Model I/O - {html.escape(str(state.get("campaign_id")))}</title>
<style>
:root{{--ink:#182230;--muted:#5d6878;--line:#d9e0e8;--panel:#f5f7fa;--accent:#174ea6}}
*{{box-sizing:border-box}} body{{margin:0;color:var(--ink);font:15px/1.5 Georgia,serif}}
header{{padding:36px max(24px,calc((100vw - 1180px)/2));background:linear-gradient(120deg,#eef5ff,#fff7ed);border-bottom:1px solid var(--line)}}
main{{max-width:1180px;margin:auto;padding:26px 24px 70px;display:grid;grid-template-columns:210px 1fr;gap:28px}}
nav{{position:sticky;top:16px;align-self:start;padding:14px;background:var(--panel);border:1px solid var(--line);border-radius:10px}}
nav a{{display:block;color:var(--accent);text-decoration:none;margin:5px 0;font-size:13px}}
.turn{{border:1px solid var(--line);border-radius:12px;padding:22px;margin:24px 0;box-shadow:0 3px 15px #1822300c}}
.call-card{{border-left:4px solid #4783d1;background:#f7fbff;padding:16px;margin:14px 0}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#111827;color:#eef2f7;padding:13px;border-radius:8px;font:12px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace}}
summary{{cursor:pointer;font-weight:700}} details{{margin:12px 0;padding:9px 12px;background:var(--panel);border-radius:8px}}
.digest{{color:var(--muted);font-size:12px}} .missing{{color:#a33;font-weight:700}}
@media(max-width:820px){{main{{display:block}}nav{{position:static;margin-bottom:22px}}}}
</style></head><body>
<header><h1>D5-5 Inspectable Model I/O</h1><p>Campaign: <code>{html.escape(str(state.get("campaign_id")))}</code><br>
Decision: <strong>{html.escape(str(state.get("decision")))}</strong><br>
This report reads sealed custody only. Provider/model calls during inspection: <strong>0</strong>.</p></header>
<main><nav><strong>Contents</strong>{"".join(toc)}</nav><section>
{"".join(sections)}
<section><h2>Evidence limitations</h2><p>The report omits request headers, credentials, and reasoning fields. Historical campaigns without a model-I/O artifact remain valid but cannot display raw prompts or responses.</p></section>
</section></main></body></html>"""
    output.write_text(document, encoding="utf-8")


def main() -> int:
    """Render one local sealed campaign without contacting a provider."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render_report(args.repo_root, args.campaign_dir, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
