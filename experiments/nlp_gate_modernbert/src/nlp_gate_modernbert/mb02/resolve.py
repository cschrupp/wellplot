"""Experiment-side cardinality / alias matching over ProjectedWorkspace."""

from __future__ import annotations

import re

from nlp_gate_modernbert.mb02.contracts import ProjectedWorkspace, ReferenceMatch


def _norm(text: str) -> str:
    t = text.lower().replace("-", " ")
    t = re.sub(r"\btrack\s+(\d+)\b", r"track \1", t)
    return " ".join(t.split())


def _curve_alias_blob(c) -> set[str]:
    ids = {_norm(c.id)}
    if c.channel:
        ids.add(_norm(c.channel))
    if c.handle:
        ids.add(_norm(c.handle))
        ids.add(_norm(c.handle.replace("-", " ")))
    aliases = set(c.aliases) | ids
    if c.label:
        aliases.add(_norm(c.label))
    if c.id.startswith("curve"):
        aliases.add(_norm(c.id.replace("-", " ")))
    return aliases


def _curve_token_hit(q: str, aliases: set[str], curve_id: str) -> bool:
    if q in aliases or q == _norm(curve_id):
        return True
    if " " in q:
        blob = " ".join(sorted(aliases))
        toks = q.split()
        return all(t in blob for t in toks)
    return False


def match_curves(workspace: ProjectedWorkspace, query: str) -> ReferenceMatch:
    """Match curve query to workspace entries.

    Duplicate placed instances (same channel, distinct handles) each count.
    Unplaced catalog-only entries count by channel id once.
    Ordinals (first/second) and view qualifiers (wide/narrow) select instances.
    """
    q = _norm(query)
    q = re.sub(r"\s+views?$", "", q).strip()

    # Ordinal instance: "first CBL", "second GR instance"
    ord_m = re.match(r"^(first|second|third|1st|2nd|3rd)\s+(.+)$", q)
    if ord_m:
        ord_word = ord_m.group(1)
        rest = re.sub(r"\s+instances?$", "", ord_m.group(2)).strip()
        rest = re.sub(r"\s+views?$", "", rest).strip()
        idx = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2}[ord_word]
        ranked: list[str] = []
        for c in workspace.curves:
            aliases = _curve_alias_blob(c)
            if _curve_token_hit(rest, aliases, c.id):
                label = c.handle or c.id
                if label not in ranked:
                    ranked.append(label)
        hits = [ranked[idx]] if len(ranked) > idx else []
        return ReferenceMatch(
            field="curve", query=query, candidate_ids=hits, candidate_count=len(hits)
        )

    # Qualifier + mnemonic: "narrow CBL", "wide CBL", "narrow CBL view"
    qual_m = re.match(r"^(wide|narrow)\s+(.+)$", q)
    if qual_m:
        qual = qual_m.group(1)
        rest = re.sub(r"\s+views?$", "", qual_m.group(2)).strip()
        hits: list[str] = []
        for c in workspace.curves:
            aliases = _curve_alias_blob(c)
            if qual in aliases and _curve_token_hit(rest, aliases, c.id):
                label = c.handle or c.id
                if label not in hits:
                    hits.append(label)
        return ReferenceMatch(
            field="curve", query=query, candidate_ids=hits, candidate_count=len(hits)
        )

    hits = []
    for c in workspace.curves:
        aliases = _curve_alias_blob(c)
        if _curve_token_hit(q, aliases, c.id):
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
    """Match fill by ref, curve channel/handle, and optional kind (upper/lower)."""
    q = _norm(query)
    want_lower = "lower" in q
    want_upper = "upper" in q
    hits: list[str] = []

    def _fill_curve_names(f) -> set[str]:
        names: set[str] = set()
        raw = _norm(f.curve or "")
        if raw:
            names.add(raw)
            names.add(raw.replace("-", " "))
        for c in workspace.curves:
            label = c.handle or c.id
            if raw and raw in {_norm(c.id), _norm(c.handle or ""), _norm(c.channel or "")}:
                names |= _curve_alias_blob(c)
                if c.channel:
                    names.add(_norm(c.channel))
            elif label and raw == _norm(label):
                names |= _curve_alias_blob(c)
        return names

    def _kind_ok(f) -> bool:
        mode = _norm(f.mode or "")
        if want_lower and "lower" not in mode:
            return False
        if want_upper and "upper" not in mode:
            return False
        return True

    for f in workspace.fills:
        if not _kind_ok(f):
            continue
        curve_names = _fill_curve_names(f)
        ref = _norm(f.ref)
        # strip filler words from query for curve token check
        q_core = re.sub(r"\b(fill|the|exactly|upper|lower|limit|to)\b", " ", q)
        q_core = " ".join(q_core.split())
        hit = False
        if q in {ref} or ref in q:
            hit = True
        elif curve_names and any(n and (n in q or n == q_core) for n in curve_names):
            hit = True
        elif q_core and any(n == q_core or q_core in n for n in curve_names):
            hit = True
        if hit and f.ref not in hits:
            hits.append(f.ref)

    # If kind filter yielded nothing but query named a curve uniquely without kind,
    # fall back only when neither upper nor lower was requested.
    if not hits and not want_lower and not want_upper:
        for f in workspace.fills:
            curve_names = _fill_curve_names(f)
            if any(n and n in q for n in curve_names):
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
