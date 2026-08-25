import json
from pathlib import Path

from app.document_ocr.evaluation import evaluate_dataset_fields, evaluate_fields


DATASET = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "evaluation"
    / "document_ocr"
    / "dataset.json"
)


def test_document_ocr_dataset_is_diverse_and_synthetic() -> None:
    cases = json.loads(DATASET.read_text(encoding="utf-8"))
    assert len(cases) >= 4
    assert {case["language"] for case in cases} == {"ru", "en"}
    assert {case["document_kind"] for case in cases} == {"receipt", "invoice"}
    assert len({case["id"] for case in cases}) == len(cases)
    assert all("example" in case["ocr_text"].lower() or "тест" in case["ocr_text"].lower() or "пример" in case["ocr_text"].lower() or "demo" in case["ocr_text"].lower() for case in cases)


def test_field_metrics_count_wrong_value_as_false_positive_and_false_negative() -> None:
    report = evaluate_fields(
        {"currency": "USD", "total": "10.00", "extra": "value"},
        {"currency": "USD", "total": "12.00"},
    )["micro"]
    assert report == {
        "true_positive": 1,
        "false_positive": 2,
        "false_negative": 1,
        "precision": 0.3333,
        "recall": 0.5,
        "f1": 0.4,
    }


def test_field_metrics_normalize_case_spacing_and_decimals() -> None:
    report = evaluate_fields(
        {"supplier": {"name": "  Example   Store "}, "total": 10},
        {"supplier": {"name": "example store"}, "total": "10.00"},
    )["micro"]
    assert report["f1"] == 1.0


def test_dataset_metrics_aggregate_line_item_fields_across_cases() -> None:
    report = evaluate_dataset_fields(
        [
            (
                {"line_items": [{"description": "Coffee"}]},
                {"line_items": [{"description": "Coffee"}]},
            ),
            (
                {"line_items": [{"description": "Bread"}]},
                {"line_items": [{"description": "Milk"}]},
            ),
        ]
    )
    assert report["per_field"]["line_items[].description"] == {
        "true_positive": 1,
        "false_positive": 1,
        "false_negative": 1,
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
    }
