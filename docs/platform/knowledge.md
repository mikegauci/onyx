# Knowledge (PR-014)

Tenant documents (care and installation guides, terms, policies) that staff and the sales
assistant can search. Part 1 is the backend; part 2 adds the screens and the sources cited on
assistant runs.

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

- **Keyword:** PostgreSQL full-text search (`english` configuration, GIN index). Any word of
  the query may match, since people ask in sentences; passages matching more words rank higher
  (`ts_rank_cd`). Only letters and digits reach the query.
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

## Screens (`/w/{slug}/m/knowledge`)

- **Documents:** title, file, format, size, pages, passages, version, and who updated it and
  when. Admins and owners also get an upload form (title and file).
- **Document:** its details and passage previews with their page. Admins and owners can
  replace the file (optionally with a new title) or delete it after a confirmation.
- **Search:** the same search the assistant uses. Results show the document, page, passage and
  how it matched. An abstention says so plainly, and keyword-only results carry a notice.
- **File limits on screen:** PDF, `.txt` or `.md`, up to **4 MB**. The API takes 5 MB, but
  Vercel refuses request bodies over 4.5 MB before the server action runs. The browser checks
  the type and size first; the API checks everything again.
- Upload and replace wait up to 90 seconds, since indexing embeds every passage in the
  request. Duplicates link to the existing document. A `503` says AI is unavailable, and a
  `429` says the budget is used up.
- Search runs as a server action, so questions never appear in URLs or request logs.
- Members see everything read-only. The API enforces every permission regardless.

## Sources on assistant runs (migration `0018`)

- `assistant_runs.sources_used` keeps the chunk ids the reply cited, but only ids a search in
  that run returned (deduplicated). An invented id is never stored; it still escalates the run
  (`unknown_source`).
- Run responses (`POST` and `GET .../runs`) carry `sources`: each chunk id with its document id,
  current title and page. These are resolved per request for the bound tenant only. A deleted
  document, a disabled module or another tenant's chunk resolves to nulls, which the inbox
  assistant panel shows as "A removed document".
- The inbox assistant panel lists each run's sources, linking to the document.

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

Revert the PR. Migration `0018` drops `assistant_runs.sources_used`. Migration `0017`
downgrades by dropping both tables and the module; the `vector` extension (since `0001`)
stays. Deployed databases use a forward fix or a backup restore.

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
    without the module;
  - cited sources kept on the run, deduplicated, surviving the document's deletion as nulls,
    and another tenant's chunk never described.
- `apps/platform/src/lib/knowledge.test.ts`: file checks, display helpers, duplicate and
  outage messages.
- `apps/platform/e2e/knowledge.spec.ts`: upload, passages, search with a citation and an
  abstention, the member's read-only view, another tenant's not-found page, replace and delete,
  and a refused file.
