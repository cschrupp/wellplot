"""Envelope classification metrics."""

from __future__ import annotations

from collections import Counter
from typing import Iterable


STATUSES = ("ok", "ambiguous", "unsupported", "invalid")


def confusion_matrix(
    y_true: Iterable[str], y_pred: Iterable[str]
) -> dict[str, dict[str, int]]:
    matrix = {t: {p: 0 for p in STATUSES} for t in STATUSES}
    for t, p in zip(y_true, y_pred, strict=True):
        t_key = t if t in matrix else "invalid"
        p_key = p if p in matrix[t_key] else "invalid"
        matrix[t_key][p_key] += 1
    return matrix


def macro_f1(matrix: dict[str, dict[str, int]]) -> float:
    scores = []
    for label in STATUSES:
        tp = matrix[label][label]
        fp = sum(matrix[o][label] for o in STATUSES if o != label)
        fn = sum(matrix[label][o] for o in STATUSES if o != label)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        scores.append(f1)
    return sum(scores) / len(scores) if scores else 0.0


def false_ok_on_ambiguous(y_true: Iterable[str], y_pred: Iterable[str]) -> int:
    return sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == "ambiguous" and p == "ok")
