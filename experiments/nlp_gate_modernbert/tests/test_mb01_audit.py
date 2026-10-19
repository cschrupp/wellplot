"""MB-01 / MB-01R gate corpus audit invariants."""

from __future__ import annotations

from nlp_gate_modernbert.mb01_audit import (
    AUTHORITY,
    DECISION_AUTHORITIES,
    DISPOSITIONS,
    MB01_DIR,
    SOURCE_CASES,
    SLICE,
    audit_corpus,
    publish_mb01_deliverables,
)
from nlp_gate_modernbert.paths import EVIDENCE_DIR
from nlp_gate_modernbert.provenance import load_json, sha256_file


REQUIRED = (
    "gate_cases_audited.jsonl",
    "gate_case_review.jsonl",
    "gate_authority_matrix.json",
    "contrast_groups.json",
    "leakage_groups.json",
    "gate_dataset_summary.json",
)


def test_audit_covers_all_source_cases() -> None:
    result = audit_corpus()
    source_n = sum(1 for _ in SOURCE_CASES.open(encoding="utf-8") if _.strip())
    assert len(result["audited"]) == source_n == 300
    assert result["summary"]["total_utterances_reviewed"] == len(result["reviews"])
    assert result["summary"]["sealed_split_frozen"] is False
    assert result["summary"]["split_creation"] == "NOT AUTHORIZED"


def test_every_case_has_allowed_authority() -> None:
    result = audit_corpus()
    for row in result["audited"]:
        assert row["decision_authority"] in DECISION_AUTHORITIES
        assert row["leakage_group"]
        assert row["gold_status"] in {"ok", "ambiguous", "unsupported", "invalid"}


def test_every_utterance_has_disposition() -> None:
    result = audit_corpus()
    for r in result["reviews"]:
        assert r["disposition"] in DISPOSITIONS


def test_gold0102_image_utterances_detached() -> None:
    result = audit_corpus()
    rows = [r for r in result["reviews"] if r["case_id"] == "GOLD-0102"]
    detached = [r for r in rows if r["disposition"] == "DETACH"]
    assert len(detached) >= 9
    assert any("image" in (r["text"] or "").lower() for r in detached)


def test_uq02_contradictory_reclassified_deterministic() -> None:
    result = audit_corpus()
    for cid in ("GOLD-0155", "GOLD-0156", "D5GAP-0140"):
        row = next(r for r in result["audited"] if r["case_id"] == cid)
        assert row["decision_authority"] == "DETERMINISTIC_SCHEMA_DOMAIN"
        assert row["gold_status"] == "invalid"


def test_learned_gate_is_empty_after_uq02() -> None:
    result = audit_corpus()
    assert result["summary"]["learned_gate_case_count"] == 0
    assert result["summary"]["learned_gate_independent_group_count"] == 0
    assert result["summary"]["learned_gate_status"] == "NO_LEARNED_GATE_REQUIRED"
    assert result["summary"]["deterministic_or_static_case_count"] == 300
    assert result["summary"]["cases_by_decision_authority"]["LEARNED_SEMANTIC_GATE"] == 0


def test_uq_resolutions_closed() -> None:
    result = audit_corpus()
    assert result["summary"]["known_unresolved_semantic_questions"] == []
    ids = {u["id"] for u in result["uq_resolutions"]}
    assert ids == {"UQ-01", "UQ-02", "UQ-03", "UQ-04", "UQ-05"}
    by_id = {u["id"]: u for u in result["uq_resolutions"]}
    assert by_id["UQ-01"]["disposition"] == "RESOLVED_KEEP"
    assert by_id["UQ-02"]["disposition"] == "RESOLVED_RECLASSIFY_AUTHORITY"
    assert by_id["UQ-03"]["disposition"] == "DEFER_OUT_OF_SCOPE"
    assert by_id["UQ-04"]["disposition"] == "RESOLVED_REWRITE"
    assert by_id["UQ-05"]["disposition"] == "DEFER_OUT_OF_SCOPE"


def test_uq04_proposed_rewrite_recorded() -> None:
    result = audit_corpus()
    row = next(r for r in result["audited"] if r["case_id"] == "GOLD-0001")
    utt2 = row["utterances"][2]
    assert utt2["disposition"] == "REWRITE"
    assert utt2["proposed_rewrite_text"] == "Add RHOB to track 4."


def test_publish_writes_six_deliverables() -> None:
    hashes = publish_mb01_deliverables()
    for name in REQUIRED:
        path = MB01_DIR / name
        assert path.is_file(), name
        assert (EVIDENCE_DIR / name).is_file(), name
        assert name in hashes
    summary = load_json(EVIDENCE_DIR / "gate_dataset_summary.json")
    assert summary["authority"] == AUTHORITY
    assert summary["slice"] == SLICE
    assert summary["sealed_split_frozen"] is False
    assert summary["learned_gate_status"] == "NO_LEARNED_GATE_REQUIRED"
    assert (EVIDENCE_DIR / "uq_resolutions.json").is_file()


def test_slm03_adapter_still_pinned() -> None:
    prov = load_json(EVIDENCE_DIR / "mb00_provenance.json")
    from nlp_gate_modernbert.paths import SLM03_ADAPTER

    expected = prov["pinned_sha256"]["slm03_adapter_model"]
    actual = sha256_file(SLM03_ADAPTER / "adapter_model.safetensors")
    assert actual == expected


def test_source_gold_hash_unchanged() -> None:
    prov = load_json(EVIDENCE_DIR / "mb00_provenance.json")
    expected = prov["pinned_sha256"]["gold_cases_jsonl"]
    actual = sha256_file(SOURCE_CASES)
    assert actual == expected
