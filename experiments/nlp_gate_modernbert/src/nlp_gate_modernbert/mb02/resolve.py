"""Experiment-side cardinality / alias matching over ProjectedWorkspace."""

from __future__ import annotations

import re

from nlp_gate_modernbert.mb02.contracts import ProjectedWorkspace, ReferenceMatch


def _norm(text: str) -> str:
    t = text.lower().replace("-", " ")
    t = re.sub(r"\btrack\s+(\d+)\b", r"track \1", t)
    return " ".join(t.split())


def match_curves(workspace: ProjectedWorkspace, query: str) -> ReferenceMatch:
    """Match curve query to workspace entries.

    Duplicate placed instances (same channel, distinct handles) each count.
    Unplaced catalog-only entries count by channel id once.
    """
    q = _norm(query)
    hits: list[str] = []
    for c in workspace.curves:
        ids = {_norm(c.id)}
        if c.channel:
            ids.add(_norm(c.channel))
        if c.handle:
            ids.add(_norm(c.handle))
        aliases = set(c.aliases) | ids
        if c.label:
            aliases.add(_norm(c.label))
        # handle "curve-3" / "curve 3"
        if c.handle:
            aliases.add(_norm(c.handle.replace("-", " ")))
        if c.id.startswith("curve"):
            aliases.add(_norm(c.id.replace("-", " ")))
        # multi-word query: all tokens present in alias/label blob
        blob = " ".join(sorted(aliases))
        token_hit = q in aliases or q == _norm(c.id)
        if not token_hit and " " in q:
            toks = q.split()
            token_hit = all(t in blob for t in toks)
        if token_hit:
            # Distinct instance id: prefer handle when present (duplicate channels)
            label = c.handle or c.id
            if label not in hits:
                hits.append(label)
    return ReferenceMatch(
        field="curve",
        query=query,
        candidate_ids=hits,
        candidate_count=len(hits),
    )


def match_tracks(workspace: ProjectedWorkspace, query: str) -> ReferenceMatch:
    q = _norm(query)
    hits: list[str] = []
    tracks = list(workspace.tracks)
    # ordinals
    if q in {"first track", "first"} and tracks:
        hits.append(str(sorted(tracks, key=lambda t: t.ref)[0].ref))
        return ReferenceMatch(field="track", query=query, candidate_ids=hits, candidate_count=1)
    if q in {"last track", "last"} and tracks:
        hits.append(str(sorted(tracks, key=lambda t: t.ref)[-1].ref))
        return ReferenceMatch(field="track", query=query, candidate_ids=hits, candidate_count=1)
    if q in {"third track", "third"} and len(tracks) >= 3:
        hits.append(str(sorted(tracks, key=lambda t: t.ref)[2].ref))
        return ReferenceMatch(field="track", query=query, candidate_ids=hits, candidate_count=1)

    m = re.search(r"(?:track\s*)?(\d+)$", q)
    if m and (q.startswith("track") or q.isdigit()):
        ref = int(m.group(1))
        for t in tracks:
            if t.ref == ref:
                hits.append(str(t.ref))
        return ReferenceMatch(
            field="track", query=query, candidate_ids=hits, candidate_count=len(hits)
        )
    # strip trailing "track" for title match: "gamma ray track"
    q_title = re.sub(r"\btrack\b", " ", q).strip()
    q_title = " ".join(q_title.split())
    for t in tracks:
        title = _norm(t.title or "")
        tid = _norm(t.id or "")
        if not title and not tid:
            continue
        if (
            q == tid
            or q == title
            or q_title == title
            or (q and q in title.split())
            or (q and q in title)
            or (q_title and q_title in title)
            or (title and title in q)
        ):
            hits.append(str(t.ref))
    seen: set[str] = set()
    uniq: list[str] = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            uniq.append(h)
    return ReferenceMatch(
        field="track", query=query, candidate_ids=uniq, candidate_count=len(uniq)
    )


def match_fills(workspace: ProjectedWorkspace, query: str) -> ReferenceMatch:
    q = _norm(query)
    hits: list[str] = []
    for f in workspace.fills:
        curve = _norm(f.curve or "")
        ref = _norm(f.ref)
        if q in {ref, curve} or (q and (q in curve or curve in q)):
            hits.append(f.ref)
        # "gr fill" style
        if "fill" in q and curve and curve in q:
            if f.ref not in hits:
                hits.append(f.ref)
    return ReferenceMatch(
        field="fill", query=query, candidate_ids=hits, candidate_count=len(hits)
    )


def match_deictic_curve(workspace: ProjectedWorkspace) -> ReferenceMatch:
    if workspace.focus_curve_handle:
        return ReferenceMatch(
            field="curve",
            query="that curve",
            candidate_ids=[workspace.focus_curve_handle],
            candidate_count=1,
        )
    return ReferenceMatch(
        field="curve",
        query="that curve",
        candidate_ids=[],
        candidate_count=0,
    )
