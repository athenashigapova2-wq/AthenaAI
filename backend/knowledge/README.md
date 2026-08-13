# Athena RAG v1 — ingestion contract

## Safety gate

`source_manifest.json` is a candidate registry, not permission to scrape. Every source starts with
`rights_status=review_required`, `verification_status=pending`, and `ingestion_enabled=false`.
Before ingestion, verify the current URL, publisher, edition/update date, licence/reuse terms,
robots policy, and whether full-text storage is permitted. Store links and metadata only until then.

## Separate corpora

| Selection | Domains | Unit of ingestion |
|---|---|---|
| Nutrition guidance | nutrition, safety | One official guideline chapter or fact sheet per document |
| Activity guidance | workout, recovery, safety | One guideline chapter/section per document |
| Sleep and recovery | recovery, safety | One first-party article per document |
| Product knowledge | product | Athena-authored help article per document |

Structured `food_nutrients` data remains outside this corpus. It is queried as a deterministic tool,
not copied into prose chunks.

## Pipeline

```text
candidate source
→ rights + freshness review
→ approved/enabled source
→ fetch immutable document snapshot
→ normalize text without changing claims
→ SHA-256 document hash
→ heading-aware chunks
→ token counts + chunk hashes
→ multilingual-e5-base passage embeddings (768d)
→ staged DataFrames
→ PostgreSQL upsert
→ retrieval eval before activation
```

Recommended initial chunks are 350–550 tokens with 50–80 token overlap. Preserve heading paths,
lists, warning boxes, publication dates, canonical URLs, and page/section locators in metadata.
Never join claims from different documents into one chunk.

## DataFrame boundary

The ingestion implementation must produce three frames defined in `app/rag/dataframes.py`:

1. `sources_frame` — governance and rights metadata.
2. `documents_frame` — one normalized official page/publication with SHA-256 hash.
3. `chunks_frame` — ordered citation-ready text units before embedding/upsert.

The Pydantic models in `app/rag/contracts.py` validate rows before they enter a DataFrame. A batch
containing documents is rejected unless its source is both rights-approved and ingestion-enabled.

## Running ingestion

Apply migrations through `0014_rag_ingestion_upsert.sql`, then prepare a UTF-8 JSON bundle with
`source` and `documents` (see `ingestion_bundle.example.json`). The loader normalizes whitespace,
computes SHA-256 hashes, and creates 450-token-estimate chunks with 70-token overlap when `chunks`
is omitted.

Validate without loading the embedding model or writing to Supabase:

```bash
python backend/scripts/ingest_knowledge.py \
  backend/knowledge/ingestion_bundle.example.json --dry-run
```

Ingest an approved bundle:

```bash
python backend/scripts/ingest_knowledge.py path/to/approved-bundle.json
```

Both the bundle and the existing `knowledge_sources` database row must be `approved` and enabled.
An unknown source is registered as `review_required` and disabled, then ingestion stops. Approval
therefore remains a separate operator action and cannot be smuggled in through the content bundle.
Each document and all its chunks are replaced in one PostgreSQL transaction. Identical document
hashes, chunk hashes, and embedding model names return `unchanged`; use `--force` to rebuild them.

At runtime LangGraph executes `router -> retriever -> specialist`. The retriever searches only
approved/enabled sources, applies the routed domain filter and similarity threshold, and injects
canonical citation metadata as an untrusted system context. Retrieval failure is fail-open for chat:
the specialist continues without RAG context and the backend logs the retrieval error.

## First verification slice

The first document candidate is the NIH ODS health-professional fact sheet on exercise and athletic
performance supplements (`document_candidates.json`). Verification is deliberately split in two:

1. `verify_knowledge_source.py` collects HTTP status, final official host, content type, update
   headers and SHA-256 without storing page content.
2. A human reviews the current page, robots policy, copyright/reuse notice and update date. Only
   then may the manifest be changed to `rights_status=approved` and `ingestion_enabled=true`.

```bash
python backend/scripts/verify_knowledge_source.py nih-ods-exercise-athletic-performance-hp
```

Passing the network identity check does **not** approve ingestion rights.

NIH ODS returned HTTP 403 during the first network check, so it remains disabled. The next candidate
is the WHO physical activity guideline publication page:

```bash
python backend/scripts/verify_knowledge_source.py who-physical-activity-guidelines-2020 --write-report
```

An HTML `200` verifies only the WHO landing page. Before parsing, record and separately verify the
exact PDF URL (including an allowed `iris.who.int` redirect), publication date and licence notice.
The evidence report lists official PDF/bitstream links discovered in the landing-page HTML and
license-related marker words. These are review hints, not an automatic legal approval.

The verified landing page exposed one official `iris.who.int` bitstream. It is tracked as a separate
document candidate so the PDF bytes receive their own status, content type and SHA-256 evidence:

```bash
python backend/scripts/verify_knowledge_source.py who-physical-activity-guidelines-2020-pdf --write-report
```

Do not infer the exact licence from landing-page marker words. Read the licence statement inside the
PDF and record whether commercial use, adaptations, attribution and share-alike obligations apply.

The PDF licence inspector reads only the first five and last three pages, records the PDF hash and a
short licence notice, and does not persist the PDF itself:

```bash
python backend/scripts/inspect_pdf_license.py who-physical-activity-guidelines-2020-pdf --write-report
```

If automated download is blocked, download the exact verified bitstream manually and pass
`--pdf-file path/to/file.pdf`. A detected licence still remains `review_required` until its
commercial-use and attribution obligations are accepted for Athena's intended distribution.
