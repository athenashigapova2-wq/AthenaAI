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
