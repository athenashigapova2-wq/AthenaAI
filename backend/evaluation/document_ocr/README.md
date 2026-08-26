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

## Paired local vs AWS benchmark

The benchmark renders the same synthetic source pixels for both variants,
runs `local_tesseract` and AWS Textract `DetectDocumentText`, then passes both
OCR outputs through the same canonical LLM `normalize_entities` stage:

```powershell
$env:DOCUMENT_OCR_BENCHMARK_ENABLED = "true"
$env:DOCUMENT_OCR_AWS_ENABLED = "true"
$env:AWS_PROFILE = "your-read-only-benchmark-profile"
$env:DOCUMENT_OCR_AWS_REGION = "us-west-2"

python backend/scripts/run_ocr_backend_benchmark.py `
  --output-json $env:TEMP/ocr-backend-benchmark.json `
  --output-markdown $env:TEMP/ocr-backend-benchmark.md
```

On Windows, the reproducible path is the backend image, because it already
contains Tesseract, RU/EN language packs and the benchmark dataset. Mount a
read-only AWS profile and a report directory instead of copying credentials into
the image:

```powershell
docker compose build api
docker compose run --rm `
  -e DOCUMENT_OCR_BENCHMARK_ENABLED=true `
  -e DOCUMENT_OCR_AWS_ENABLED=true `
  -e DOCUMENT_OCR_AWS_REGION=us-west-2 `
  -e AWS_PROFILE=your-read-only-benchmark-profile `
  -v "${env:USERPROFILE}\.aws:/home/athena/.aws:ro" `
  -v "${env:TEMP}:/reports" `
  api python scripts/run_ocr_backend_benchmark.py `
    --output-json /reports/ocr-backend-benchmark.json `
    --output-markdown /reports/ocr-backend-benchmark.md
```

The report contains OCR character accuracy, final field precision/recall/F1,
OCR/LLM/end-to-end p50/p95, provider API cost and explicit cost coverage. Local
OCR has no per-page API fee, but its CPU, memory and operations are intentionally
not called “free”. The Textract price is a configurable dated snapshot via
`DOCUMENT_OCR_AWS_PRICE_PER_PAGE_USD`; verify it against the
[official AWS pricing page](https://aws.amazon.com/textract/pricing/) for the
selected region before a decision.

The experiment is paired rather than user-assigned: every backend receives the
same cases. Choose AWS only when its quality/reliability gain justifies data
transfer, vendor dependency and per-page fees. Choose local when quality is
within the accepted margin and privacy, offline operation or predictable
infrastructure matters more. A synthetic winner is only a candidate; the final
decision requires an approved anonymized production-like corpus.

Language slices are mandatory. AWS currently documents Textract text detection
for English, French, German, Italian, Portuguese and Spanish, not Russian. The
adapter therefore marks Russian cases as `UnsupportedOCRLanguageError` without
sending them to AWS; their missed fields remain visible in recall. A mixed
aggregate must never be used to claim Textract support for Russian receipts.

For the runtime endpoint, `DOCUMENT_OCR_BACKEND=tesseract` remains the default.
Setting it to `aws_textract` also requires `DOCUMENT_OCR_AWS_ENABLED=true`; do
not enable that globally for Russian uploads. The current upload contract
allowlists `ru` and `en`, matching the installed Tesseract language packs.

Predictions use `[{"id": "...", "document": {...}}]`. The report computes
micro and per-field precision/recall/F1. Release gates should be set separately
for critical fields (`total`, `currency`, `issue_date`, supplier identity) and
line items; a high aggregate score must not hide a weak total or currency field.
