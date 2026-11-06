# Knowledge (PR-014)

Tenant documents (care and installation guides, terms, policies) that staff and the sales
assistant can search. Part 1 is the backend; the screens follow in part 2.

## Module and permissions

The `knowledge` module has no requirements. It is off until a platform admin enables it.

| Permission         | Roles                | Allows                               |
| ------------------ | -------------------- | ------------------------------------ |
| `knowledge.read`   | member, admin, owner | List, read and search documents      |
| `knowledge.manage` | admin, owner         | Upload, replace and delete documents |

## Upload

`POST /v1/w/{slug}/knowledge/documents` with JSON `{title, filename, content_base64}`.

- **Formats**, decided by the file name: PDF, `.txt` and `.md`/`.markdown`. Word files are not
  supported yet.
- **Limits:** 5 MB, 100 PDF pages, 200,000 characters of text.
- **Refused with `422` and a reason:** bad base64, an unsupported format, a file that is not
  really a PDF, an unreadable or password-protected PDF, non-UTF-8 text, or no text at all
  (scanned PDFs need text recognition, which is not supported).
- **Only the text is kept.** The original file is not stored. To update a document, upload the
  new file over it.
- **Duplicates:** the same file (by SHA-256) twice in one workspace is a `409` whose detail
  `ref` names the existing document. Another workspace may hold the same file.

Processing happens inside the request, in this order, so a failure stores nothing:

1. Extract the text with `pypdf` (nothing in the PDF is executed or followed) and clean it:
   Unicode normalised, control characters and extra whitespace removed.
2. Split each page into passages of about 3,200 characters (~800 tokens), overlapping by about
   400, breaking at paragraphs, then sentences, then words. A passage never spans two pages,
   so every citation names one page.
3. Embed every passage through the AI gateway (below). A provider failure is a `503`, and a
   used-up budget is a `429`.
4. Store the document and its chunks in one transaction, and audit
   `knowledge.document.added` with ids and counts only, never text or file names.

`PUT /documents/{id}/file` replaces the file and optionally the title. It bumps `version` and
swaps every chunk in one transaction, so search sees the old version or the new one, never a
mix. The same file again changes nothing. `DELETE /documents/{id}` removes the document and
its chunks.

## Search

`POST /v1/w/{slug}/knowledge/search` with `{query, limit}` (at most 10) returns
`{hits, mode, abstained}`. Each hit has the chunk and document ids, the document title, the
page (PDFs only), the passage, a score and `matched_by`.

- **Keyword:** PostgreSQL full-text search (`english` configuration, `websearch_to_tsquery`,
  GIN index), ranked by `ts_rank_cd`.
- **Semantic:** cosine distance on the passage embeddings (pgvector HNSW index). A semantic-only
  match needs a cosine similarity of at least 0.35.
- The two rankings are merged by reciprocal-rank fusion (k = 60).
- **Abstains** (`hits: []`, `abstained: true`) when nothing clears the bar. It never returns
  weak matches to fill the list.
- **Keyword fallback:** if the query cannot be embedded (AI unavailable, provider failure or
  budget used up), search runs on keywords alone and answers `mode: "keyword"`.
- Every query filters by the bound tenant explicitly, and row-level security gated by the
  `knowledge` module applies too.

## Embeddings

The embedding model is its own workload, `knowledge_embedding`, and never falls back to the
chat model. `AIGateway.embed()` reserves budget, meters and finalises a usage event exactly like
a chat call, with bounded retries for transient errors. Every vector must have 1,536
dimensions, or the call counts as invalid output and nothing is stored.

| Setting (env)                 | Value for OpenAI                                                                                  |
| ----------------------------- | ------------------------------------------------------------------------------------------------- |
| `ONYX_API_AI_WORKLOAD_MODELS` | add `"knowledge_embedding": "openai:text-embedding-3-small"`                                      |
| `ONYX_API_AI_MODEL_PRICES`    | add `"openai:text-embedding-3-small": {"input_usd_per_mtok": "0.02", "output_usd_per_mtok": "0"}` |

Locally and in tests, an unset workload uses a deterministic fake (hashed words). Deployed
environments refuse the fake: without the setting, uploads answer `503` and search uses
keywords only.

## The assistant

With `knowledge` enabled, the assistant also gets `search_knowledge(query)`, which returns up
to 4 passages of at most 1,500 characters, each with a `source_id`.

- **Untrusted text:** passages are shop documents, never instructions. Angle brackets are
  neutralised, and the instructions say so.
- **Citations:** the model lists the passages it relied on in `sources_used`. A source that no
  search returned in that run sends the run to staff (`unknown_source`).
- **No evidence:** when nothing is found, the tool says so, and the model must say a colleague
  will confirm.
- **Run records** list the returned chunk ids and the search mode, never passage text.

## Data (migration `0017`)

- **`knowledge_documents`:** title, file name, format, size, SHA-256 (unique per tenant),
  version, page, character and chunk counts, embedding model, and who created and updated it.
- **`knowledge_chunks`:** ordinal, page, text (at most 8,000 characters), a `tsvector` written
  with the text, and a `vector(1536)` embedding. A composite same-tenant foreign key to the
  document, `ON DELETE CASCADE`.
- Both tables have tenant RLS gated by `knowledge`.
- **Grants:** `onyx_app` may read, insert and delete both, and update document metadata.
  Chunks are never updated. `onyx_worker` has no grants.

## Rollback

Revert the PR. Migration `0017` downgrades by dropping both tables and the module; the `vector`
extension (since `0001`) stays. Deployed databases use a forward fix or a backup restore.

## Tests

- `tests/modules/knowledge/test_extract.py`: PDF pages, blank and scanned PDFs, refused files,
  cleaning, chunk bounds, overlap and page boundaries, determinism, and the fake embeddings.
- `tests/api/test_knowledge.py`, against a real database:
  - upload, metering and audit without text;
  - PDF page citations, duplicates, replace and delete;
  - abstention on an unrelated question;
  - embedding outage (nothing stored, keyword fallback), wrong vector size, and no budget;
  - bad uploads refused before any embedding;
  - member and owner roles, the module gate, and two-tenant isolation through the API and RLS;
  - the assistant citing found passages, an invented citation escalated, and no document tool
    without the module.
