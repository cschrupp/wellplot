"""Fixed positive/negative corpus for bakeoff parity (mirrors CFG-GENERATOR suite)."""

from __future__ import annotations


def _task(request_body: str, *, binds: str | None = None) -> str:
    mid = f'"produces_binds":{binds},' if binds is not None else ""
    return '{"tasks":[{' + mid + f'"request":{request_body},"task_id":"t1"' + "}]}"


def _req(*parts: str) -> str:
    return "{" + ",".join(parts) + "}"


POSITIVE: list[tuple[str, str]] = [
    ("empty_tasks", '{"tasks":[]}'),
    ("version_null", '{"tasks":[],"version":null}'),
    ("version_str", '{"tasks":[],"version":"v1"}'),
    (
        "text_only",
        _task(
            _req(
                '"query":{"kind":"curve","text":"GR"}',
                '"requested_operation":"PLACE_CURVE"',
            )
        ),
    ),
    (
        "local_ref_only",
        _task(
            _req(
                '"query":{"kind":"curve","local_ref":"bind1"}',
                '"requested_operation":"PLACE_CURVE"',
            )
        ),
    ),
    (
        "unicode_only_non_ws",
        _task(
            _req(
                '"query":{"kind":"curve","text":"\\u0047\\u0052"}',
                '"requested_operation":"PLACE_CURVE"',
            )
        ),
    ),
    ("optionals_absent", _task(_req('"requested_operation":"PLACE_CURVE"'))),
    (
        "nullable_alpha_null",
        _task(_req('"alpha":null', '"requested_operation":"PLACE_CURVE"')),
    ),
    ("produces_binds_empty", _task(_req('"requested_operation":"PLACE_CURVE"'), binds="{}")),
    (
        "produces_binds_entry",
        _task(
            _req('"requested_operation":"PLACE_CURVE"'),
            binds='{"petrophysics":"track"}',
        ),
    ),
    (
        "number_forms",
        _task(_req('"alpha":0', '"requested_operation":"PLACE_CURVE"')),
    ),
    (
        "number_frac_exp",
        _task(_req('"alpha":-0.5e+2', '"requested_operation":"PLACE_CURVE"')),
    ),
    (
        "valid_surrogate_pair_in_task_id",
        '{"tasks":[{"request":{"requested_operation":"PLACE_CURVE"},'
        '"task_id":"\\uD83D\\uDE00"}]}',
    ),
]

NEGATIVE: list[tuple[str, str]] = [
    (
        "both_text_and_ref",
        _task(
            _req(
                '"query":{"kind":"curve","text":"GR","local_ref":"x"}',
                '"requested_operation":"PLACE_CURVE"',
            )
        ),
    ),
    (
        "neither_text_nor_ref",
        _task(_req('"query":{"kind":"curve"}', '"requested_operation":"PLACE_CURVE"')),
    ),
    (
        "empty_text",
        _task(
            _req(
                '"query":{"kind":"curve","text":""}',
                '"requested_operation":"PLACE_CURVE"',
            )
        ),
    ),
    (
        "spaces_text",
        _task(
            _req(
                '"query":{"kind":"curve","text":"   "}',
                '"requested_operation":"PLACE_CURVE"',
            )
        ),
    ),
    (
        "tab_escape",
        _task(
            _req(
                '"query":{"kind":"curve","text":"\\t"}',
                '"requested_operation":"PLACE_CURVE"',
            )
        ),
    ),
    (
        "u0009",
        _task(
            _req(
                '"query":{"kind":"curve","text":"\\u0009"}',
                '"requested_operation":"PLACE_CURVE"',
            )
        ),
    ),
    (
        "reordered_closed_keys",
        _task(
            _req(
                '"requested_operation":"PLACE_CURVE"',
                '"query":{"kind":"curve","text":"GR"}',
            )
        ),
    ),
    ("extra_property", '{"tasks":[],"extra":1}'),
    (
        "wrong_bind_value",
        _task(_req('"requested_operation":"PLACE_CURVE"'), binds='{"x":"curve"}'),
    ),
    ("nan", _task(_req('"alpha":NaN', '"requested_operation":"PLACE_CURVE"'))),
    ("infinity", _task(_req('"alpha":Infinity', '"requested_operation":"PLACE_CURVE"'))),
    (
        "neg_infinity",
        _task(_req('"alpha":-Infinity', '"requested_operation":"PLACE_CURVE"')),
    ),
    ("structural_space", '{"tasks": []}'),
    ("structural_newline", '{"tasks":[\n]}'),
    (
        "lone_high_surrogate",
        '{"tasks":[{"request":{"requested_operation":"PLACE_CURVE"},'
        '"task_id":"\\uD800"}]}',
    ),
    (
        "lone_low_surrogate",
        '{"tasks":[{"request":{"requested_operation":"PLACE_CURVE"},'
        '"task_id":"\\uDC00"}]}',
    ),
]
