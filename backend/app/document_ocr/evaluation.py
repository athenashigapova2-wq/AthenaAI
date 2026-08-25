"""Field-level exact-match evaluation for OCR/entity extraction datasets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class FieldMetrics:
    true_positive: int
    false_positive: int
    false_negative: int

    @property
    def precision(self) -> float:
        denominator = self.true_positive + self.false_positive
        return self.true_positive / denominator if denominator else 1.0

    @property
    def recall(self) -> float:
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else 1.0

    @property
    def f1(self) -> float:
        denominator = self.precision + self.recall
        return 2 * self.precision * self.recall / denominator if denominator else 0.0


def evaluate_fields(predicted: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    predicted_fields = flatten_fields(predicted)
    expected_fields = flatten_fields(expected)
    names = sorted(set(predicted_fields) | set(expected_fields))
    per_field: dict[str, FieldMetrics] = {}
    totals = [0, 0, 0]
    for name in names:
        prediction = predicted_fields.get(name)
        target = expected_fields.get(name)
        matched = prediction is not None and target is not None and _equal(prediction, target)
        tp = int(matched)
        fp = int(prediction is not None and not matched)
        fn = int(target is not None and not matched)
        per_field[name] = FieldMetrics(tp, fp, fn)
        totals[0] += tp
        totals[1] += fp
        totals[2] += fn
    micro = FieldMetrics(*totals)
    return {
        "micro": _serialize(micro),
        "per_field": {name: _serialize(metrics) for name, metrics in per_field.items()},
    }


def evaluate_dataset_fields(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
) -> dict[str, Any]:
    """Aggregate the same semantic field across cases and line-item indices."""
    counts: dict[str, list[int]] = {}
    totals = [0, 0, 0]
    for predicted, expected in pairs:
        left = flatten_fields(predicted)
        right = flatten_fields(expected)
        for path in set(left) | set(right):
            field = re.sub(r"\.\d+(?=\.|$)", "[]", path)
            prediction = left.get(path)
            target = right.get(path)
            matched = prediction is not None and target is not None and _equal(
                prediction, target
            )
            current = counts.setdefault(field, [0, 0, 0])
            increments = (
                int(matched),
                int(prediction is not None and not matched),
                int(target is not None and not matched),
            )
            for index, increment in enumerate(increments):
                current[index] += increment
                totals[index] += increment
    return {
        "micro": _serialize(FieldMetrics(*totals)),
        "per_field": {
            field: _serialize(FieldMetrics(*values)) for field, values in sorted(counts.items())
        },
    }


def flatten_fields(value: Any, prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "field_confidence":
                continue
            path = f"{prefix}.{key}" if prefix else key
            flattened.update(flatten_fields(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            path = f"{prefix}.{index}" if prefix else str(index)
            flattened.update(flatten_fields(child, path))
    elif value is not None:
        flattened[prefix] = value
    return flattened


def _equal(left: Any, right: Any) -> bool:
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except InvalidOperation:
        def normalize(item: Any) -> str:
            return re.sub(r"\s+", " ", str(item).strip().casefold())

        return normalize(left) == normalize(right)


def _serialize(metrics: FieldMetrics) -> dict[str, float | int]:
    return {
        "true_positive": metrics.true_positive,
        "false_positive": metrics.false_positive,
        "false_negative": metrics.false_negative,
        "precision": round(metrics.precision, 4),
        "recall": round(metrics.recall, 4),
        "f1": round(metrics.f1, 4),
    }
