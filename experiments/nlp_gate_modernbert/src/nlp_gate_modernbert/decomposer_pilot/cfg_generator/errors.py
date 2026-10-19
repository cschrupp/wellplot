"""Fail-closed generator errors."""

from __future__ import annotations


class GeneratorFail(Exception):
    """Schema construct cannot be mapped exactly under the frozen CFG contract."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        msg = code if detail is None else f"{code}:{detail}"
        super().__init__(msg)
