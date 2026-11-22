# RAG V4 — Complete function-by-function reference

This file explains **every Python function and method** in the packaged `backend/rag/` modules. A leading underscore marks an internal helper, not a different security model. The purpose is practical: if a prediction or figure is wrong, use this map to identify the right module to inspect.

## Typical debugging flow

1. **Wrong question meaning:** inspect `planner.py` and `llm_planner.py`.
2. **Right metric, wrong result:** inspect `catalog.py` and `explorer.py`.
3. **Wrong source / empty operational data:** inspect `source_selection.py`.
4. **Missing procedure:** inspect `rag_documents/manifest.json` and `documents.py`.
5. **Confusing user answer:** inspect `presentation.py` and `RAGAssistant.jsx`.
6. **403 / wrong site:** inspect `app.auth` (existing app), `catalog.py`, `explorer.py`, and `documents.visible`.

## `api.py`

Main FastAPI HTTP boundary. JWT is required; orchestrates three retrieval modes and produces read-only responses. REPLACE.

- **`_database()` (line 25):** Obtains the live Atlas database already attached to FastAPI. Raises an explicit 503 if missing; no second unrestricted connection.
- **`_run_explore()` (line 33):** Converts permission/field/source errors from the calculation engine into correct HTTP codes; accepts only `ExploreIn`.
- **`_execute_plan()` (line 47):** Turns an approved Plan into an ExploreIn request and executes it against authorized records.
- **`_is_document_question()` (line 55):** Recognizes procedural how/why queries so they are routed to approved documents, not mistaken for statistics.
- **`_answer_documents()` (line 64):** Retrieves allowed document passages, optionally asks local Ollama to summarize and checks source citations.
- **`status()` (line 95):** GET /api/rag/status; indicates index visibility and selected optional features, without exposing document bodies.
- **`catalog()` (line 108):** GET /api/rag/catalog; returns metrics/dimensions available to the authenticated user.
- **`explore_data()` (line 115):** POST /api/rag/explore; safe, employee-selected query from the Data Explorer.
- **`ask()` (line 124):** POST /api/rag/ask; routes lots, analytics, documents and empty-source fallback, then returns readable results.

## `catalog.py`

Audited allowlist of datasets, metrics, dimensions and roles. Every metric has a business meaning. REFERENCE COPY; do not overwrite custom changes.

- **`class Metric` (line 14):** Metric definition (label, aggregation kind, data fields, semantics).
- **`class Dataset` (line 23):** Dataset definition (source, roles, filters, metrics, date).
- **`public_catalog()` (line 141):** Builds the dropdown catalog filtered by the employee role, without exposing unauthorized datasets.

## `planner.py`

Interpretable French question → a *plan* (not SQL or MQL). REPLACE.

- **`class Plan` (line 19):** Read-only analytical query proposal; not an executable DB command.
- **`norm()` (line 13):** Normalizes French accents/case for robust keyword matching, e.g. semées/semees.
- **`_has()` (line 31):** Checks whether a normalized question contains any of several indicative phrases.
- **`_group()` (line 35):** Detects grouping words such as par espèce, par client, par ville, par article.
- **`_filters()` (line 57):** Extracts safe, narrow filters like C25 and a named species; does not invent user-supplied filter values.
- **`maybe_plan()` (line 79):** Main transparent French parser: selects a catalog dataset, metric, grouping and filters, or returns None.

## `source_selection.py`

Explicit historical fallback mappings; avoids treating unrelated measures as equivalent. ADD.

- **`explicitly_operational()` (line 24):** Detects if a question explicitly requires current operational data so no historical fallback occurs.
- **`alternative_for_empty()` (line 33):** Constructs a permission-checked alternative historical plan only for defined, relevant metric mappings.
- **`fallback_notice()` (line 55):** Explains in French why data came from a separate source and whether its indicator differs.

## `explorer.py`

Site-scoped exact data retrieval and deterministic aggregation, with pagination and source excerpts. REPLACE.

- **`class InvalidExplore` (line 25):** Invalid requested dataset/metric/filters/units exception.
- **`class ForbiddenExplore` (line 29):** Unauthorized dataset or site exception.
- **`class Bucket` (line 260):** Accumulator for one aggregation group.
- **`_norm()` (line 33):** Normalizes comparison strings so accents/case do not cause avoidable filter mismatches.
- **`_number()` (line 38):** Safely parses numeric Excel/MongoDB values and rejects NaN, infinity and invalid percentages.
- **`_printed()` (line 53):** Formats a computed number as readable French numeric text and percentages.
- **`_str()` (line 61):** Converts optional raw field to trimmed string, preserving blankness.
- **`_month()` (line 65):** Extracts YYYY-MM only from recognized date/date-like values for time filtering.
- **`_extract()` (line 72):** Retrieves a dimension field through the catalog rather than arbitrary user-specified DB paths.
- **`_enrich_historical()` (line 81):** Adds derived metadata such as campaign/declared germination rate to copies of raw Excel rows.
- **`_historical_records()` (line 90):** Traverses existing read-only Excel ETL indexes and annotates campaign without modifying workbook files.
- **`_germination_records()` (line 107):** Links validated GERMINATION events to authorized SEMIS lots by real lot ID plus matching site, not five-digit guesses.
- **`_mongo_records()` (line 148):** Fetches operational projections with site restrictions enforced in MongoDB before rows are loaded.
- **`_check_inputs()` (line 198):** Rejects unknown datasets/fields/operators, forbidden roles, invalid filters, limits and sort options.
- **`_filter()` (line 220):** Matches only catalog-defined filter dimensions; includes special pending-quality and five-digit historical matching rules.
- **`_metric_value()` (line 249):** Reads a metric value, including calculated pending quantity = max(reserved-delivered,0).
- **`Bucket.__post_init__()` (line 269):** Initializes per-group sets and evidence lists.
- **`Bucket.add()` (line 275):** Adds one eligible record to its group, tracking valid/invalid rows, values, denominators and provenance.
- **`Bucket.result()` (line 317):** Finalizes count/distinct/sum/mean/weighted percentage according to the metric business definition.
- **`_source_ref()` (line 331):** Builds a source-row identifier for Excel or a MongoDB document ID for traceability.
- **`explore()` (line 337):** Main calculation engine: permission check → retrieve → filter → aggregate → rank/page → evidence and structured rows.

## `presentation.py`

Transforms numeric results into concise French answers and tables. ADD.

- **`_scoped_label()` (line 6):** Translates internal filter names to user-friendly French labels without exposing raw schema codes.
- **`present_explore()` (line 15):** Adds readable summary, table, provenance and honest no-data/partial status without changing computed values.
- **`present_document()` (line 71):** Packages a document-based answer and citations into the same response envelope as analytics.

## `documents.py`

Document index and permission filtering, lexical retrieval, optional embeddings and status diagnostics. REPLACE.

- **`class Chunk` (line 25):** A document passage with role/site ACL and source information.
- **`text_tokens()` (line 34):** Normalizes and tokenizes French/English text for lexical comparison.
- **`_split()` (line 40):** Splits approved Markdown text into overlapping chunks to preserve local context.
- **`load_chunks()` (line 62):** Reads only manifest-approved Markdown files, validating paths, role lists, site lists and size caps.
- **`visible()` (line 97):** Checks a chunk’s allowed roles and sites BEFORE any lexical or vector retrieval.
- **`_model()` (line 106):** Lazy-loads the optional multilingual SentenceTransformer on CPU (cached).
- **`lexical_rank()` (line 117):** Scores token overlap with extra weight on document titles, excluding common French stopwords.
- **`_cached_vectors()` (line 141):** Caches embeddings of an already ACL-filtered chunk tuple.
- **`search_documents()` (line 146):** Retrieves visible chunks lexically or using combined embedding+keyword scores; falls back safely.
- **`document_status()` (line 177):** Checks whether documents and manifest are installed and visible; exposes counts/hints, not secret text.

## `llm_planner.py`

Optional local LLM producing strictly validated JSON plans, not executable DB code. ADD.

- **`allowed_catalog_summary()` (line 16):** Sends ONLY role-authorized field/metric names to the local language-model planner.
- **`validate_plan()` (line 23):** Rejects unknown dataset/metric/group, unauthorized roles, operator objects and invalid filter values.
- **`propose_plan()` (line 57):** Calls local Ollama for JSON only when enabled, validates result and returns a safe plan or None.

## `llm.py`

Optional local Ollama synthesis for document excerpts only. REFERENCE COPY.

- **`synthesize()` (line 21):** Optional local LLM uses approved evidence snippets to explain documentary questions; no remote URLs or writes.

## `schemas.py`

Pydantic definitions of accepted request bodies. REFERENCE COPY.

- **`class QuestionIn` (line 5):** Pydantic validation of a bounded French question.
- **`class ExploreIn` (line 9):** Pydantic validation of dataset/metric/filter/order/limit input.

## `structured.py`

Previous exact lot lookup and focused operational queries. REFERENCE COPY.

- **`normal()` (line 12):** Standardizes textual queries for focused exact lookups.
- **`site_scope()` (line 17):** Builds a site filter for operations; no unrestricted cross-site search for employees.
- **`code_from_question()` (line 23):** Recognizes a lot identifier explicitly present in a question.
- **`campaign_from_question()` (line 30):** Finds a campaign such as C25 from user text.
- **`numbers_5()` (line 35):** Extracts an isolated five-digit historical lot code; not a physical genealogy proof.
- **`evidence()` (line 40):** Creates a consistently formatted source reference and excerpt.
- **`value()` (line 44):** Formats a field from a row, with a missing-value placeholder.
- **`lot_record()` (line 49):** Summarizes the key fields of one active operational lot.
- **`_active_lots()` (line 59):** Looks up real MongoDB lots under role/site restrictions, with their direct attached events.
- **`historical_lot()` (line 102):** Admin-only historical lot lookup combining production, grafting and delivery by shared five-digit key.
- **`_rank_losses()` (line 140):** Earlier specialized operational losses lookup and ranking (reference implementation).
- **`_quality_waiting()` (line 186):** Earlier specialized quality-state lookup (reference implementation).
- **`_total_lots()` (line 204):** Earlier specialized authorized MongoDB lot count.
- **`_pending_preparations()` (line 217):** Earlier specialized reservations/delivery-balance search.
- **`structured_search()` (line 245):** Orchestrates exact lot and special-case lookups with evidence, permissions and warnings.

## `analytics.py`

Previous purpose-built historical/operational analytics helpers. REFERENCE COPY.

- **`_positive_number()` (line 20):** Validates nonnegative finite numeric input for specialized calculations.
- **`_species_requested()` (line 28):** Detects the explicitly supported crop filter in prior specialized code.
- **`_matches_species()` (line 33):** Checks species name against requested crop.
- **`operational_germination()` (line 39):** Calculates recorded germinated/sown from valid, authorized GERMINATION events.
- **`_reported_germination_rate()` (line 116):** Reads explicit `Taux_Germination` stored in Excel ETL raw_cells; does not infer it from net plants.
- **`historical_reported_germination()` (line 137):** Admin-only aggregation of declared historical germination percentages.
- **`historical_grafting_losses()` (line 201):** Admin-only lookup of historical grafting `Perte_Totale`, not operational loss ratio.

## `__init__.py`

Marks `rag` as an importable Python package. REFERENCE COPY.

- No executable functions; package/module definitions only.

## React frontend: `frontend/src/RAGAssistant.jsx`

- **`DataTable({table})`:** Displays metric results as a readable HTML table, with labels, formatted values and number of contributing rows; does not recalculate values.
- **`AnswerView({entry})`:** Shows the short answer, group tables, provenance and collapsible warnings, source excerpts and technical query details. Technical JSON is hidden by default.
- **`RAGAssistant({token})`:** Owns the UI state for the chat and Data Explorer, and passes the JWT to authenticated API calls.
- **`useEffect` for catalog:** Fetches `/api/rag/catalog` so only allowed datasets populate the Explorer controls.
- **`useEffect` for selection:** Keeps metric/group/filter selections valid when dataset changes.
- **`request(path,payload,visibleQuestion,isExplore)`:** Sends a POST with Bearer token, handles loading/cancellation/error, and appends the answer to the conversation.
- **`ask(event)`:** Submits the typed French question to `/api/rag/ask`.
- **`explore(event,offset)`:** Converts explicit Explorer controls into an `/api/rag/explore` request, without generating SQL/MQL.
- **`loadMore()`:** Loads the next page for an explicit Explorer query.
- **`changeFilter(index,key,value)`:** Updates one filter row without affecting other filters.
- **`Modifier cette analyse dans l'explorateur` button:** Opens the previously interpreted dataset/metric/filters as editable controls; human correction is central to the design.

## Why there are both `analytics.py` and `explorer.py`

`analytics.py` is the earlier focused, purpose-built query path; `explorer.py` provides a general catalog-based engine. Keep existing analytics source files in place for compatibility, but new metric calculations should normally be implemented once in the catalog and Explorer, with tests proving equivalence. Do not create two different formulas under the same label.

## Security invariants

All roads to data must go through permission checks. `rag.api` obtains the authenticated user. `explorer._check_inputs()` verifies roles/fields; `_mongo_records()` restricts by site before loading; historical Excel datasets are admin-only; `documents.visible()` filters document snippets before ranking. LLM planner output is always revalidated, and a model may not execute commands, persist operations or fabricate Blockchain certification.
