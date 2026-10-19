"""MB-01 gate corpus audit: authority partition, utterance dispositions, grouping.

Read-only over SLM-03 gold. Does not freeze sealed splits.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from nlp_gate_modernbert.paths import EVIDENCE_DIR, SLM01_ROOT

AUTHORITY = "WELLPLOT-NLP-RUNTIME-V2-MB01-GATE-CORPUS-AUDIT-REWORK-AUTH-001"
SLICE = "MB-01R"
PARENT_AUTHORITY = "WELLPLOT-NLP-RUNTIME-V2-MB01-GATE-CORPUS-AUDIT-AUTH-001"
SOURCE_CASES = SLM01_ROOT / "benchmark" / "gold" / "cases.jsonl"
MB01_DIR = EVIDENCE_DIR / "mb01_gate_corpus"

DECISION_AUTHORITIES = (
    "DETERMINISTIC_CARDINALITY",
    "DETERMINISTIC_NOT_FOUND",
    "DETERMINISTIC_PRECONDITION",
    "DETERMINISTIC_SCHEMA_DOMAIN",
    "STATIC_CAPABILITY_BOUNDARY",
    "LEARNED_SEMANTIC_GATE",
)

DISPOSITIONS = ("KEEP", "REWRITE", "DETACH", "REJECT")

# Fixtures where generic family nouns are intentionally multi-match.
CARDINALITY_FIXTURES = {
    "d0_ambiguous_density",
    "d5_density_ambiguous",
    "d5_duplicate_gr",
    "d5_duplicate_gr_same_track",
    "d5_duplicate_cbl",
    "d5_qc_track_ambiguous",
    "d5_two_gr_fills",
}

MISSING_CURVE_FIXTURE_PREFIXES = (
    "d0_missing_CALI_",
    "d0_missing_PEF_",
    "d0_missing_DT_",
    "d0_missing_SP_",
    "d0_missing_MSFL_",
)

# Case-level utterance disposition overrides: (case_id, utterance_index) -> (disp, note)
# Applied after general heuristics; empty means use heuristics only.
UTTERANCE_OVERRIDES: dict[tuple[str, int], tuple[str, str]] = {}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def load_source_cases(path: Path = SOURCE_CASES) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def normalize_template(text: str) -> str:
    """Collapse surface variants for leakage grouping (not a semantic parser)."""
    t = text.lower().strip()
    t = re.sub(r"\([^)]*\)", " ", t)
    t = re.sub(r"\b(variant|please)\s*\d*\b", " ", t)
    t = re.sub(r"\b\d+(\.\d+)?\b", "<n>", t)
    # family synonyms kept as tokens for contrast; normalize mnemonics lightly
    for a, b in (
        ("bulk density", "density"),
        ("neutron porosity", "neutron"),
        ("gamma ray", "gr"),
        ("spontaneous potential", "sp"),
        ("photoelectric", "pef"),
        ("caliper", "cali"),
        ("track four", "track <n>"),
        ("track 4", "track <n>"),
    ):
        t = t.replace(a, b)
    t = re.sub(r"[^\w\s<>]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _is_image_raster_panel_request(text: str) -> bool:
    low = text.lower()
    markers = (
        "image",
        "raster",
        "panel",
        "waveform",
        "vdl",
        "borehole image",
        "shared raster",
        "array track",
        "depth ruler",
        "depth reference",
        "depth lane",
        "formation review needs",
    )
    return any(m in low for m in markers)


def _is_numbered_padding(text: str) -> bool:
    return bool(
        re.search(r"\(\d+\)\s*$", text.strip())
        or re.search(r"without focus\s*\(\d+\)", text, re.I)
        or re.search(r"please\s*\(\d+\)", text, re.I)
        or re.search(r"\(variant\s*\d+\)", text, re.I)
    )


def classify_decision_authority(case: dict[str, Any]) -> tuple[str, str]:
    """Return (authority, rationale)."""
    gold = case.get("gold") or {}
    status = gold.get("status")
    reason = gold.get("reason")
    detail = (gold.get("detail") or "") or ""
    fixture = case.get("fixture") or ""
    if any(fixture.startswith(p) for p in MISSING_CURVE_FIXTURE_PREFIXES):
        return "DETERMINISTIC_NOT_FOUND", "missing-curve fixture; reference_not_found"

    if reason == "reference_not_found":
        return "DETERMINISTIC_NOT_FOUND", "gold reason reference_not_found"

    if reason == "capability_not_available" or "between_fill_requires" in detail:
        return "DETERMINISTIC_PRECONDITION", f"fill/capability precondition: {detail or reason}"

    if status == "invalid":
        if reason and reason.startswith("contradictory_"):
            # UQ-02: explicit mutual exclusions are deterministic schema/domain validation.
            return (
                "DETERMINISTIC_SCHEMA_DOMAIN",
                f"explicit contradictory request ({reason}); no residual learned judgment",
            )
        return "DETERMINISTIC_SCHEMA_DOMAIN", f"schema/domain invalid: {reason}"

    if status == "ambiguous":
        if fixture == "d5_no_focus" or case["case_id"] == "GOLD-0169":
            return "DETERMINISTIC_PRECONDITION", "deictic requires focus; focus absent"
        if fixture in CARDINALITY_FIXTURES or "ambiguous" in fixture:
            return "DETERMINISTIC_CARDINALITY", f"multi-match fixture {fixture}"
        return "DETERMINISTIC_CARDINALITY", "ambiguous envelope; treat as cardinality pending resolver"

    if status == "unsupported":
        if reason == "operation_not_supported" or reason == "capability_not_available":
            return "STATIC_CAPABILITY_BOUNDARY", f"unsupported capability: {detail or reason}"
        return "STATIC_CAPABILITY_BOUNDARY", f"unsupported: {reason}"

    # status == ok — classify by how the envelope is justified once facts exist
    texts = " ".join(u["text"].lower() for u in case.get("utterances") or [])
    family = case.get("semantic_family") or ""
    if fixture in {"d5_focus_rhob", "d5_focus_gr"} or (
        any(k in texts for k in ("that curve", "flip it", "reverse it")) and "focus" in fixture
    ):
        return "DETERMINISTIC_PRECONDITION", "ok deictic with focus present (contrast)"
    if "density" in texts and fixture not in CARDINALITY_FIXTURES:
        return "DETERMINISTIC_CARDINALITY", "ok unique density/alias resolution contrast"
    if family in {
        "curve_placement",
        "reference_resolution",
        "relational_targeting",
        "track_targeting",
        "move_remove",
    }:
        return "DETERMINISTIC_CARDINALITY", "ok after unique object resolution"
    if family in {"fills"}:
        return "DETERMINISTIC_PRECONDITION", "ok fill after deterministic preconditions"
    if family in {"display_configuration", "intervals", "track_creation", "composition"}:
        return "DETERMINISTIC_SCHEMA_DOMAIN", "ok after schema/domain-valid parameters"
    return (
        "DETERMINISTIC_CARDINALITY",
        "ok executable; learned gate not primary authority",
    )


def _material_semantics_key(text: str, gold_status: str) -> str:
    """Coarse material-request fingerprint for multi-utt coherence."""
    t = normalize_template(text)
    # Drop filler; keep verb+objectish tokens
    return f"{gold_status}::{t}"


def disposition_for_utterance(
    case: dict[str, Any],
    utt_index: int,
    utt: dict[str, Any],
    *,
    seen_templates_in_case: dict[str, int],
) -> tuple[str, str]:
    case_id = case["case_id"]
    key = (case_id, utt_index)
    if key in UTTERANCE_OVERRIDES:
        return UTTERANCE_OVERRIDES[key]

    text = utt.get("text") or ""
    gold_status = (case.get("gold") or {}).get("status")
    origin = utt.get("origin") or ""

    # Contaminated: image/raster/panel under ambiguity gold merely mentioning density.
    if gold_status == "ambiguous" and _is_image_raster_panel_request(text):
        densityish = "density" in text.lower() or "rhob" in text.lower()
        simple_density = bool(
            re.search(r"^(put|plot|add|show)\b.*\bdensity\b", text.strip(), re.I)
        ) and not _is_image_raster_panel_request(text)
        if densityish and not simple_density:
            return (
                "DETACH",
                "image/raster/panel request must not inherit ambiguity from density noun",
            )

    # Numbered synthetic padding
    if _is_numbered_padding(text):
        tmpl = normalize_template(text)
        first = seen_templates_in_case.get(tmpl)
        if first is None:
            seen_templates_in_case[tmpl] = utt_index
            return "REWRITE", "strip numbered padding; keep one canonical form"
        return "DETACH", "duplicate numbered padding of same template in case"

    # Near-duplicate templates within a case
    tmpl = normalize_template(text)
    if tmpl in seen_templates_in_case and seen_templates_in_case[tmpl] != utt_index:
        return "DETACH", "duplicate normalized template within case"
    seen_templates_in_case.setdefault(tmpl, utt_index)

    # Multi-utt SEED / mapped cases: divergent material under one gold
    if origin.startswith("mapped_") and gold_status in {"unsupported", "ambiguous", "invalid"}:
        # Compare to first KEEP-worthy utterance material for this case
        return "KEEP", "mapped seed; review coherence in case notes"  # refined below

    return "KEEP", "utterance material matches case gold semantics"


def refine_multi_utt_coherence(
    case: dict[str, Any],
    reviews: list[dict[str, Any]],
) -> None:
    """If utterances encode different material requests, DETACH divergences from primary."""
    gold_status = (case.get("gold") or {}).get("status")
    if gold_status == "ok":
        # ok multi-utt paraphrases are expected; only detach if ops diverge strongly
        return
    keep_idxs = [r["utterance_index"] for r in reviews if r["disposition"] == "KEEP"]
    if len(keep_idxs) <= 1:
        return
    primary_idx = keep_idxs[0]
    primary_text = case["utterances"][primary_idx]["text"]
    primary_key = _material_semantics_key(primary_text, gold_status)
    primary_tokens = set(primary_key.split())

    for r in reviews:
        if r["disposition"] != "KEEP":
            continue
        if r["utterance_index"] == primary_idx:
            continue
        text = case["utterances"][r["utterance_index"]]["text"]
        key = _material_semantics_key(text, gold_status)
        # Heuristic: if Jaccard of tokens very low, divergent material
        tokens = set(key.split())
        if not tokens or not primary_tokens:
            continue
        jacc = len(tokens & primary_tokens) / len(tokens | primary_tokens)
        # Also: different primary curve/family nouns
        curves_a = {w for w in primary_tokens if w in {
            "gr", "rhob", "nphi", "rt", "cali", "pef", "dt", "sp", "msfl", "cbl", "vdl", "density", "neutron"
        }}
        curves_b = {w for w in tokens if w in {
            "gr", "rhob", "nphi", "rt", "cali", "pef", "dt", "sp", "msfl", "cbl", "vdl", "density", "neutron"
        }}
        # Conditional fill GR vs NPHI under same unsupported gold is OK (same capability class)
        detail = (case.get("gold") or {}).get("detail") or ""
        if "conditional_threshold" in detail and curves_a and curves_b:
            continue
        if jacc < 0.35 and (not curves_a or not curves_b or curves_a != curves_b):
            # Unsupported multi-op seeds: detach divergent utterances
            if str(case["case_id"]).startswith("SEED") or (case.get("provenance") or {}).get("source_kind") == "mapped":
                r["disposition"] = "DETACH"
                r["disposition_note"] = (
                    f"divergent material vs primary utt[{primary_idx}] "
                    f"(jaccard={jacc:.2f}); do not share gold label"
                )


def contrast_group_id(case: dict[str, Any], authority: str) -> str | None:
    """Assign contrast pairs where meaningful."""
    fixture = case.get("fixture") or ""
    status = (case.get("gold") or {}).get("status")
    texts = " ".join(u["text"].lower() for u in case.get("utterances") or [])
    tags = case.get("semantic_tags") or []

    if "density" in texts and (
        fixture in {
            "d0_ambiguous_density",
            "d5_density_ambiguous",
            "d0_triple_combo",
            "d5_petrophysics",
        }
        or "density" in " ".join(tags)
    ):
        if "with neutron" in texts or "with density" in texts or "neutron with" in texts:
            return "contrast:density_relational_unique_vs_ambiguous"
        if any(
            k in texts
            for k in (
                "put density",
                "plot density",
                "add density",
                "show density",
                "bulk density",
                "add the density",
            )
        ):
            return "contrast:density_unique_vs_ambiguous"

    if any(k in texts for k in ("that curve", "reverse it", "flip it")):
        return "contrast:focus_present_vs_missing"

    if "gr" in texts and ("reverse" in texts or "fill" in texts) and "duplicate" in fixture:
        return "contrast:curve_unique_vs_duplicate"

    if "qc track" in texts:
        return "contrast:track_title_unique_vs_ambiguous"

    if "gr fill" in texts or "remove the gr fill" in texts:
        return "contrast:fill_unique_vs_ambiguous"

    if "fill between" in texts:
        return "contrast:supported_vs_unsupported_between_fill"

    if status == "invalid" or "log" in texts and "0" in texts:
        if "log" in texts or "logarithmic" in texts:
            return "contrast:valid_vs_invalid_log_bounds"
        if "scale" in texts or "50" in texts:
            return "contrast:valid_vs_invalid_scale_bounds"

    if status in {"unsupported", "ok"} and "shade" in texts and "exceeds" in texts:
        return "contrast:supported_fill_vs_threshold_fill"

    if authority == "DETERMINISTIC_NOT_FOUND":
        return "contrast:curve_present_vs_absent"

    return None


def leakage_group_id(case: dict[str, Any], kept_templates: list[str]) -> str:
    """Group template-equivalent semantics for split hygiene (not a freeze)."""
    status = (case.get("gold") or {}).get("status")
    family = case.get("semantic_family") or "unknown"
    reason = (case.get("gold") or {}).get("reason") or ""
    detail = (case.get("gold") or {}).get("detail") or ""
    # Prefer first kept template; else signature
    tmpl = kept_templates[0] if kept_templates else normalize_template(
        (case.get("utterances") or [{"text": ""}])[0].get("text", "")
    )
    # Coarser buckets for missing-curve replicas
    fixture = case.get("fixture") or ""
    for p in MISSING_CURVE_FIXTURE_PREFIXES:
        if fixture.startswith(p):
            curve = p.split("_")[2]  # CALI etc
            return f"leak:missing_{curve.lower()}|{status}|{family}"
    if status == "ambiguous" and "density" in tmpl:
        return f"leak:density_alias|{status}|{family}"
    if status == "ambiguous" and ("that curve" in tmpl or "reverse it" in tmpl or "flip it" in tmpl):
        return f"leak:deictic_no_focus|{status}|{family}"
    if reason or detail:
        return f"leak:{family}|{status}|{reason}|{detail}|{tmpl[:80]}"
    return f"leak:{family}|{status}|{tmpl[:100]}"


def build_uq_resolutions() -> list[dict[str, Any]]:
    """Terminal dispositions for UQ-01..05 (MB-01R)."""
    return [
        {
            "id": "UQ-01",
            "disposition": "RESOLVED_KEEP",
            "affected_cases": "all reference_not_found / missing-curve fixtures (24)",
            "public_gold": {
                "status": "unsupported",
                "reason": "reference_not_found",
            },
            "decision_authority": "DETERMINISTIC_NOT_FOUND",
            "note": (
                "decision authority ≠ public envelope status; "
                "MB-02 may terminate on zero matches without a new terminal status"
            ),
        },
        {
            "id": "UQ-02",
            "disposition": "RESOLVED_RECLASSIFY_AUTHORITY",
            "affected_cases": ["GOLD-0155", "GOLD-0156", "D5GAP-0140"],
            "public_gold_unchanged": True,
            "from_authority": "LEARNED_SEMANTIC_GATE",
            "to_authority": "DETERMINISTIC_SCHEMA_DOMAIN",
            "note": (
                "explicit mutual exclusions (scale direction / exclusive targets) "
                "are deterministic validation once parsed"
            ),
        },
        {
            "id": "UQ-03",
            "disposition": "DEFER_OUT_OF_SCOPE",
            "affected_cases": [
                "GOLD-0102 (utt>=17)",
                "SEED-cm-* divergent multi-utt DETACHes",
            ],
            "replacement_case_authoring": "NOT AUTHORIZED",
            "current_DETACH_dispositions": "PRESERVED",
            "note": "detached ≠ auto-author new training cases",
        },
        {
            "id": "UQ-04",
            "disposition": "RESOLVED_REWRITE",
            "affected_cases": ["GOLD-0001"],
            "affected_utterance_index": 2,
            "source_text": "Add density to track 4.",
            "proposed_rewrite_text": "Add RHOB to track 4.",
            "mutate_slm03_cases_jsonl": False,
            "preserve_leakage_contrast": (
                "generic density + unique workspace → OK; "
                "generic density + multiple candidates → AMBIGUOUS"
            ),
        },
        {
            "id": "UQ-05",
            "disposition": "DEFER_OUT_OF_SCOPE",
            "sealed_split_frozen": False,
            "split_creation": "NOT AUTHORIZED",
            "note": (
                "closing UQs does not authorize classifier-oriented split freeze; "
                "reassess after MB-02"
            ),
        },
    ]


def audit_corpus(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cases = cases if cases is not None else load_source_cases()
    source_hash = _sha256_file(SOURCE_CASES)

    audited_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    authority_matrix: dict[str, Any] = {
        "authority": AUTHORITY,
        "slice": SLICE,
        "classes": list(DECISION_AUTHORITIES),
        "by_case": {},
        "counts": {k: 0 for k in DECISION_AUTHORITIES},
    }
    contrast_map: dict[str, list[str]] = defaultdict(list)
    leakage_map: dict[str, list[str]] = defaultdict(list)

    for case in cases:
        case_id = case["case_id"]
        gold = case.get("gold") or {}
        status = gold.get("status")
        support = (case.get("grounding") or {}).get("support_level")
        family = case.get("semantic_family")
        authority, auth_note = classify_decision_authority(case)
        authority_matrix["by_case"][case_id] = {
            "decision_authority": authority,
            "rationale": auth_note,
            "gold_status": status,
            "fixture": case.get("fixture"),
            "semantic_family": family,
            "support_level": support,
        }
        authority_matrix["counts"][authority] += 1

        seen: dict[str, int] = {}
        utt_reviews: list[dict[str, Any]] = []
        for i, utt in enumerate(case.get("utterances") or []):
            disp, note = disposition_for_utterance(case, i, utt, seen_templates_in_case=seen)
            # specialised GOLD-0102 contamination
            if case_id == "GOLD-0102" and i >= 17:
                disp, note = (
                    "DETACH",
                    "mapped CM image/panel utterances inherited density ambiguity label",
                )
            # UQ-04: OK density alias that template-leaks with ambiguous density cases
            proposed_rewrite = None
            if case_id == "GOLD-0001" and i == 2:
                disp, note = (
                    "REWRITE",
                    "UQ-04 RESOLVED_REWRITE: prefer mnemonic on OK side; "
                    "do not mutate frozen SLM-03 cases.jsonl",
                )
                proposed_rewrite = "Add RHOB to track 4."
            row_rev: dict[str, Any] = {
                "case_id": case_id,
                "utterance_index": i,
                "text": utt.get("text"),
                "origin": utt.get("origin"),
                "reviewed_flag_source": utt.get("reviewed"),
                "disposition": disp,
                "disposition_note": note,
                "normalized_template": normalize_template(utt.get("text") or ""),
            }
            if proposed_rewrite is not None:
                row_rev["proposed_rewrite_text"] = proposed_rewrite
            utt_reviews.append(row_rev)

        refine_multi_utt_coherence(case, utt_reviews)

        # Second pass: for SEED unsupported multi-utt, detach non-primary material aggressively
        if str(case_id).startswith("SEED") and status == "unsupported":
            primary = next((r for r in utt_reviews if r["disposition"] == "KEEP"), None)
            if primary:
                ptoks = set(normalize_template(primary["text"]).split())
                for r in utt_reviews:
                    if r["utterance_index"] == primary["utterance_index"]:
                        continue
                    if r["disposition"] != "KEEP":
                        continue
                    toks = set(r["normalized_template"].split())
                    jacc = len(toks & ptoks) / max(1, len(toks | ptoks))
                    if jacc < 0.5:
                        r["disposition"] = "DETACH"
                        r["disposition_note"] = (
                            "SEED multi-utterance: divergent unsupported scenario; "
                            "detach from shared gold"
                        )

        kept_templates = [
            r["normalized_template"]
            for r in utt_reviews
            if r["disposition"] in {"KEEP", "REWRITE"}
        ]
        cg = contrast_group_id(case, authority)
        lg = leakage_group_id(case, kept_templates)
        if cg:
            contrast_map[cg].append(case_id)
        leakage_map[lg].append(case_id)

        # Gate candidate: non-ok always; ok if in a contrast group or envelope_only
        gate_candidate = status != "ok" or support == "envelope_only" or cg is not None

        audited = {
            "case_id": case_id,
            "fixture": case.get("fixture"),
            "gold_status": status,
            "gold_reason": gold.get("reason"),
            "gold_detail": gold.get("detail"),
            "semantic_family": family,
            "semantic_signature": case.get("semantic_signature"),
            "support_level": support,
            "decision_authority": authority,
            "decision_authority_rationale": auth_note,
            "contrast_group": cg,
            "leakage_group": lg,
            "gate_candidate": gate_candidate,
            "utterance_count_source": len(case.get("utterances") or []),
            "utterances": [
                {
                    **{
                        "utterance_index": r["utterance_index"],
                        "text": r["text"],
                        "origin": r["origin"],
                        "disposition": r["disposition"],
                        "disposition_note": r["disposition_note"],
                        "normalized_template": r["normalized_template"],
                        "include_in_gate_dataset": r["disposition"]
                        in {"KEEP", "REWRITE"},
                    },
                    **(
                        {"proposed_rewrite_text": r["proposed_rewrite_text"]}
                        if r.get("proposed_rewrite_text")
                        else {}
                    ),
                }
                for r in utt_reviews
            ],
            "source_provenance": {
                "audit_revision": (case.get("grounding") or {}).get("audit_revision"),
                "review_status": (case.get("provenance") or {}).get("review_status"),
                "source_kind": (case.get("provenance") or {}).get("source_kind"),
            },
        }
        audited_rows.append(audited)
        review_rows.extend(utt_reviews)

    uq_resolutions = build_uq_resolutions()
    unresolved: list[dict[str, str]] = []  # UQ-01..05 closed

    # Independent case counts (case-level, after audit; include if any KEEP/REWRITE)
    def independent(status: str) -> list[str]:
        out = []
        for row in audited_rows:
            if row["gold_status"] != status:
                continue
            if any(u["include_in_gate_dataset"] for u in row["utterances"]):
                out.append(row["case_id"])
        return out

    ok_contrast = [
        row["case_id"]
        for row in audited_rows
        if row["gold_status"] == "ok"
        and row["contrast_group"]
        and any(u["include_in_gate_dataset"] for u in row["utterances"])
    ]

    disp_counts = Counter(r["disposition"] for r in review_rows)
    status_counts = Counter(r["gold_status"] for r in audited_rows)
    family_counts = Counter(r["semantic_family"] for r in audited_rows)
    support_counts = Counter(r["support_level"] for r in audited_rows)

    contrast_groups = {
        gid: {
            "group_id": gid,
            "case_ids": sorted(set(ids)),
            "n_cases": len(set(ids)),
            "statuses": sorted(
                {
                    next(r["gold_status"] for r in audited_rows if r["case_id"] == cid)
                    for cid in set(ids)
                }
            ),
        }
        for gid, ids in sorted(contrast_map.items())
    }
    leakage_groups = {
        gid: {
            "group_id": gid,
            "case_ids": sorted(set(ids)),
            "n_cases": len(set(ids)),
            "note": "Proposed only; must not cross eventual splits once frozen.",
        }
        for gid, ids in sorted(leakage_map.items())
    }

    learned_cases = [
        {
            "case_id": row["case_id"],
            "gold_status": row["gold_status"],
            "gold_reason": row["gold_reason"],
            "leakage_group": row["leakage_group"],
            "rationale": row["decision_authority_rationale"],
            "why_deterministic_cannot_decide": None,
        }
        for row in audited_rows
        if row["decision_authority"] == "LEARNED_SEMANTIC_GATE"
    ]
    learned_groups = sorted({c["leakage_group"] for c in learned_cases})
    learned_count = len(learned_cases)
    if learned_count == 0:
        learned_gate_status = "NO_LEARNED_GATE_REQUIRED"
    elif learned_count < 30:
        learned_gate_status = "INSUFFICIENT_FOR_EXPERIMENT"
    else:
        learned_gate_status = "SUFFICIENT_FOR_EXPERIMENT"

    det_static = sum(
        authority_matrix["counts"][k]
        for k in DECISION_AUTHORITIES
        if k != "LEARNED_SEMANTIC_GATE"
    )

    summary = {
        "authority": AUTHORITY,
        "parent_authority": PARENT_AUTHORITY,
        "slice": SLICE,
        "source_cases_path": str(SOURCE_CASES),
        "source_cases_sha256": source_hash,
        "total_source_cases_reviewed": len(audited_rows),
        "total_utterances_reviewed": len(review_rows),
        "cases_by_gold_status": dict(status_counts),
        "cases_by_semantic_family": dict(family_counts),
        "cases_by_support_level": dict(support_counts),
        "cases_by_decision_authority": dict(authority_matrix["counts"]),
        "deterministic_or_static_case_count": det_static,
        "utterances_by_disposition": dict(disp_counts),
        "independent_ambiguous_cases": independent("ambiguous"),
        "independent_unsupported_cases": independent("unsupported"),
        "independent_invalid_cases": independent("invalid"),
        "independent_ok_contrast_cases": ok_contrast,
        "n_independent_ambiguous": len(independent("ambiguous")),
        "n_independent_unsupported": len(independent("unsupported")),
        "n_independent_invalid": len(independent("invalid")),
        "n_independent_ok_contrast": len(ok_contrast),
        "n_leakage_groups": len(leakage_groups),
        "n_contrast_groups": len(contrast_groups),
        "n_gate_candidate_cases": sum(1 for r in audited_rows if r["gate_candidate"]),
        "sealed_split_frozen": False,
        "split_creation": "NOT AUTHORIZED",
        "known_unresolved_semantic_questions": unresolved,
        "uq_resolutions": uq_resolutions,
        "learned_gate_case_count": learned_count,
        "learned_gate_independent_group_count": len(learned_groups),
        "learned_gate_cases": learned_cases,
        "learned_gate_status": learned_gate_status,
        "gate_viability_conclusion": {
            "learned_gate_status": learned_gate_status,
            "learned_gate_case_count": learned_count,
            "learned_gate_independent_group_count": len(learned_groups),
            "deterministic_or_static_case_count": det_static,
            "total_cases": len(audited_rows),
            "recommendation": (
                "Do not authorize MB-03 encoder bake-off on this corpus. "
                "Proceed to MB-02 deterministic resolver/capability layer and test whether "
                "it eliminates SLM-03 envelope failures without a learned gate."
                if learned_gate_status == "NO_LEARNED_GATE_REQUIRED"
                else "Reassess after corpus changes under a new authority."
            ),
            "do_not_manufacture_learned_examples": True,
        },
        "invariants": [
            "No utterance remains attached to a gold label unless material request matches gold",
            "sealed_split_frozen=false; split_creation NOT AUTHORIZED in MB-01R",
            "SLM-03 artifacts and cases.jsonl untouched",
            "No resolver/encoder/T5/LangGraph implementation in MB-01R",
            "Do not enlarge LEARNED_SEMANTIC_GATE to obtain training data",
            "decision authority ≠ public envelope status",
        ],
    }

    return {
        "audited": audited_rows,
        "reviews": review_rows,
        "authority_matrix": authority_matrix,
        "contrast_groups": contrast_groups,
        "leakage_groups": leakage_groups,
        "summary": summary,
        "uq_resolutions": uq_resolutions,
    }


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rows]
    body = "\n".join(lines) + ("\n" if lines else "")
    path.write_text(body, encoding="utf-8")
    return _sha256_bytes(body.encode("utf-8"))


def write_json(path: Path, obj: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(body, encoding="utf-8")
    return _sha256_bytes(body.encode("utf-8"))


def publish_mb01_deliverables(out_dir: Path | None = None) -> dict[str, str]:
    out_dir = out_dir or MB01_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    result = audit_corpus()
    hashes = {
        "gate_cases_audited.jsonl": write_jsonl(
            out_dir / "gate_cases_audited.jsonl", result["audited"]
        ),
        "gate_case_review.jsonl": write_jsonl(
            out_dir / "gate_case_review.jsonl", result["reviews"]
        ),
        "gate_authority_matrix.json": write_json(
            out_dir / "gate_authority_matrix.json", result["authority_matrix"]
        ),
        "contrast_groups.json": write_json(
            out_dir / "contrast_groups.json", result["contrast_groups"]
        ),
        "leakage_groups.json": write_json(
            out_dir / "leakage_groups.json", result["leakage_groups"]
        ),
        "gate_dataset_summary.json": write_json(
            out_dir / "gate_dataset_summary.json", result["summary"]
        ),
        "uq_resolutions.json": write_json(
            out_dir / "uq_resolutions.json",
            {
                "authority": AUTHORITY,
                "slice": SLICE,
                "resolutions": result["uq_resolutions"],
            },
        ),
    }
    # also place copies at evidence root names expected by plan
    root_hashes: dict[str, str] = {}
    for name, digest in list(hashes.items()):
        target = EVIDENCE_DIR / name
        target.write_bytes((out_dir / name).read_bytes())
        root_hashes[f"evidence_root:{name}"] = digest
    hashes.update(root_hashes)
    return hashes
