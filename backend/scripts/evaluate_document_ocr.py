"""Generate field-level receipt/invoice evaluation reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.document_ocr.evaluation import evaluate_dataset_fields, evaluate_fields  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=BACKEND / "evaluation" / "document_ocr" / "dataset.json",
    )
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()

    cases = {case["id"]: case for case in _read(args.dataset)}
    predictions = {case["id"]: case for case in _read(args.predictions)}
    case_reports: list[dict[str, Any]] = []
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for case_id, case in cases.items():
        prediction = predictions.get(case_id, {}).get("document", {})
        report = evaluate_fields(prediction, case["expected"])
        case_reports.append({"id": case_id, **report["micro"]})
        pairs.append((prediction, case["expected"]))
    aggregate = evaluate_dataset_fields(pairs)
    payload = {"cases": case_reports, **aggregate}
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_markdown.write_text(_markdown(payload), encoding="utf-8")


def _read(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _markdown(report: dict[str, Any]) -> str:
    micro = report["micro"]
    lines = [
        "# Document OCR field evaluation",
        "",
        f"Micro precision: **{micro['precision']:.4f}**  ",
        f"Micro recall: **{micro['recall']:.4f}**  ",
        f"Micro F1: **{micro['f1']:.4f}**",
        "",
        "| Case | Precision | Recall | F1 |",
        "|---|---:|---:|---:|",
    ]
    lines.extend(
        f"| {case['id']} | {case['precision']:.4f} | {case['recall']:.4f} | {case['f1']:.4f} |"
        for case in report["cases"]
    )
    lines.extend(
        [
            "",
            "## Per field",
            "",
            "| Field | Precision | Recall | F1 |",
            "|---|---:|---:|---:|",
        ]
    )
    lines.extend(
        f"| {field} | {metrics['precision']:.4f} | {metrics['recall']:.4f} | {metrics['f1']:.4f} |"
        for field, metrics in report["per_field"].items()
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
