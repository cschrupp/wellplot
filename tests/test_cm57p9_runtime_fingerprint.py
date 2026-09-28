"""Provider-free tests for normalized CM-57P9 endpoint provenance."""

# Test doubles intentionally use lightweight untyped callback signatures.
# ruff: noqa: ANN001, ANN002, ANN204, D103

from __future__ import annotations

import json

import pytest
from scripts import cm57p9_runtime_fingerprint as fingerprint


def _payload(*, created: int = 1, order: tuple[str, ...] = ("qwen3.6-35b-a3b",)) -> dict:
    """Build a small OpenAI-compatible model catalog."""
    return {
        "object": "list",
        "data": [{"id": model_id, "created": created, "owned_by": "local"} for model_id in order],
    }


def _fingerprint(payload: object, *, endpoint: str = "http://host:8888/v1") -> dict:
    """Build one valid v2 fingerprint."""
    return fingerprint.build_endpoint_fingerprint_v2(
        endpoint=endpoint,
        model_api_label="qwen3.6-35b-a3b",
        models_payload=payload,
    )


def test_metadata_changes_do_not_change_normalized_identity() -> None:
    left = _fingerprint(_payload(created=1))
    right = _fingerprint(_payload(created=2))
    assert left["normalized_identity_sha256"] == right["normalized_identity_sha256"]
    assert left["raw_model_catalog_sha256"] != right["raw_model_catalog_sha256"]
    assert fingerprint.compare_endpoint_fingerprints_v2(left, right) == []


def test_model_order_and_duplicates_are_normalized() -> None:
    left = _fingerprint(_payload(order=("qwen3.6-35b-a3b", "aux")))
    right = _fingerprint(
        _payload(order=("aux", "qwen3.6-35b-a3b", "aux")),
    )
    assert left["available_model_ids"] == ["aux", "qwen3.6-35b-a3b"]
    assert right["available_model_ids"] == left["available_model_ids"]
    assert left["normalized_identity_sha256"] == right["normalized_identity_sha256"]


def test_trailing_endpoint_slash_is_normalized() -> None:
    left = _fingerprint(_payload(), endpoint="http://host:8888/v1")
    right = _fingerprint(_payload(), endpoint="http://host:8888/v1/")
    assert left["endpoint"] == right["endpoint"]
    assert left["normalized_identity_sha256"] == right["normalized_identity_sha256"]


def test_different_model_identity_changes_hash() -> None:
    left = _fingerprint(_payload())
    right = fingerprint.build_endpoint_fingerprint_v2(
        endpoint="http://host:8888/v1",
        model_api_label="aux",
        models_payload=_payload(order=("aux", "qwen3.6-35b-a3b")),
    )
    assert left["normalized_identity_sha256"] != right["normalized_identity_sha256"]
    assert fingerprint.compare_endpoint_fingerprints_v2(left, right)


@pytest.mark.parametrize("payload", [{}, {"data": []}, {"models": []}, {"data": [{}]}])
def test_invalid_model_catalogs_fail_closed(payload: object) -> None:
    with pytest.raises(ValueError):
        _fingerprint(payload)


def test_configured_model_absence_fails_closed() -> None:
    with pytest.raises(ValueError, match="absent"):
        _fingerprint(_payload(order=("other",)))


def test_v2_fingerprint_validation_requires_normalized_projection() -> None:
    value = _fingerprint(_payload())
    value["normalized_identity_sha256"] = "0" * 64
    valid, reasons = fingerprint.validate_endpoint_fingerprint_v2(value)
    assert not valid
    assert "normalized_identity_sha256_invalid" in reasons


def test_capture_uses_only_models_get_and_does_not_retain_api_key(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return json.dumps(_payload()).encode("utf-8")

    def urlopen(request: fingerprint.urllib.request.Request, *, timeout: float) -> Response:
        calls.append((request.full_url, request.get_method()))
        assert request.get_header("Authorization") == "Bearer secret"
        return Response()

    monkeypatch.setattr(fingerprint.urllib.request, "urlopen", urlopen)
    value = fingerprint.capture_endpoint_fingerprint_v2(
        endpoint="http://host:8888/v1/",
        model_api_label="qwen3.6-35b-a3b",
        api_key="secret",
    )
    assert calls == [("http://host:8888/v1/models", "GET")]
    assert "secret" not in json.dumps(value)


def test_five_stable_probes_are_stable() -> None:
    probes = [_fingerprint(_payload(created=index)) for index in range(5)]
    result = fingerprint.summarize_endpoint_probes(
        probes,
        model_api_label="qwen3.6-35b-a3b",
    )
    assert result["decision"] == "ENDPOINT_PROVENANCE_NORMALIZED_STABLE"
    assert len(result["raw_model_catalog_sha256"]) == 5


def test_changed_normalized_probe_is_unstable() -> None:
    probes = [_fingerprint(_payload()) for _ in range(4)]
    probes.append(
        fingerprint.build_endpoint_fingerprint_v2(
            endpoint="http://other:8888/v1",
            model_api_label="qwen3.6-35b-a3b",
            models_payload=_payload(),
        )
    )
    result = fingerprint.summarize_endpoint_probes(
        probes,
        model_api_label="qwen3.6-35b-a3b",
    )
    assert result["decision"] == "ENDPOINT_PROVENANCE_NORMALIZED_UNSTABLE"


def test_incomplete_probe_population_is_inconclusive() -> None:
    result = fingerprint.summarize_endpoint_probes(
        [_fingerprint(_payload())] * 4,
        model_api_label="qwen3.6-35b-a3b",
    )
    assert result["decision"] == "INCONCLUSIVE_ENDPOINT_PROVENANCE_CHECK"
    assert "incomplete_probe_set" in result["reasons"]


def test_probe_summary_is_bounded_and_deterministic() -> None:
    probes = [_fingerprint(_payload()) for _ in range(5)]
    first = fingerprint.summarize_endpoint_probes(
        probes,
        model_api_label="qwen3.6-35b-a3b",
    )
    second = fingerprint.summarize_endpoint_probes(
        probes,
        model_api_label="qwen3.6-35b-a3b",
    )
    assert first == second
    assert "Authorization" not in json.dumps(first)
