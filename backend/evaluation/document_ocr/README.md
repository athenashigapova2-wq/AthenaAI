# Receipt/invoice OCR evaluation

`dataset.json` contains synthetic OCR text and field-level gold labels. It is
safe to commit: no real receipts, names, tax identifiers or payment data are
included. Every case records its language and document kind.

Run the deterministic evaluator against predictions produced by any OCR/model
version:

```powershell
python backend/scripts/evaluate_document_ocr.py `
  --predictions path/to/predictions.json `
  --output-json $env:TEMP/document-ocr-eval.json `
  --output-markdown $env:TEMP/document-ocr-eval.md
```

To create extraction predictions with the configured live provider, opt in
explicitly (this is never run by CI):

```powershell
$env:DOCUMENT_OCR_LIVE_EVAL_ENABLED = "true"
python backend/scripts/generate_document_ocr_predictions.py `
  --output $env:TEMP/document-ocr-predictions.json
```

The committed seed dataset starts from synthetic OCR text and isolates entity
extraction quality. End-to-end OCR releases should additionally evaluate an
approved, anonymized image/PDF corpus through `/api/v1/documents/extract`; those
source documents must not be committed until privacy review is complete.

Predictions use `[{"id": "...", "document": {...}}]`. The report computes
micro and per-field precision/recall/F1. Release gates should be set separately
for critical fields (`total`, `currency`, `issue_date`, supplier identity) and
line items; a high aggregate score must not hide a weak total or currency field.
