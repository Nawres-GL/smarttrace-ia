# Learn RAG, LLMs and NLP by building SmartTrace

## 1. Begin with the problem, not the model

A useful assistant must interpret employee language, access the correct authorized data, compute the requested quantities **accurately**, and explain the answer with evidence. A fluent chatbot may still be wrong if it retrieves the wrong table or substitutes an event count for a rate.

SmartTrace has **two different AI tasks**:

- **CamemBERT, Phase 6:** classification + NER on an operation description. Input: `Nous avons déplacé 200 plants du lot ...`. Output: `TRANSFERT`, `LOT`, `QUANTITY`, `ORIGIN`, `DESTINATION`. The employee edits a draft; **never auto-submits**.
- **Hybrid RAG, Phase 7:** question answering from facts already stored in MongoDB, historical Excel and documents. Input: `Quel est le taux moyen de greffage par article ?`. Output: statistics computed from the relevant authorized records, with cited sources. **Read only**.

A Transformer alone doesn't know your private production database, and you should not fine-tune it to memorize changing customer records. RAG addresses that problem by retrieving evidence *at query time*.

## 2. What Retrieval-Augmented Generation means

**Retrieval** = selecting relevant evidence. In SmartTrace that includes: (1) exact MongoDB records, (2) read-only Excel historical observations, (3) approved document chunks.

**Augmented** = giving that evidence to a language model or a deterministic formatter. The answer is constrained by the available evidence and query scope.

**Generation** = producing a natural-language explanation. It can be done by a local LLM such as Ollama or with an audited deterministic template. A model isn't required for totals; Python is more reliable for that.

```
Question
  |
  v
Auth/JWT + role/site checks
  |
  v
Router / planner -> query PLAN (dataset, metric, grouping, filters)
  |
  +--> structured query: MongoDB / Excel ETL -> exact calculation -> result rows
  |
  +--> document query: manifest -> ACL filter -> chunks -> lexical / embeddings
  |
  v
Answer formatter, source labels, limitations -> React table + expandable evidence
```

**Hybrid RAG** means selecting tools based on the type of evidence. Searching text chunks to answer `How does quality control work?` is sensible. Searching embeddings to compute `average grafting rate` is not. For statistics, query structured records and calculate.

## 3. A real end-to-end example: delivery counts by client

**Question:** `Combien de livraisons par client ?`

1. React `RAGAssistant.jsx` sends the question to `POST /api/rag/ask` with the user's Bearer JWT.
2. FastAPI `api.ask()` authenticates the user and obtains the configured Atlas database.
3. `planner.maybe_plan()` proposes `operational_deliveries`, metric `records`, group `client`.
4. `explorer.explore()` checks catalog permissions and queries only the authorized sites.
5. If there are no operational deliveries and the user is admin, `source_selection.alternative_for_empty()` offers `historical_deliveries` with `delivery_notes`: the count of **distinct delivery note numbers**, not the number of Excel lines. These measures differ in provenance, so the response identifies its historical source.
6. The engine groups allowed rows by `client`, counts distinct valid BL numbers and preserves representative source-row IDs. It does not mutate Excel or MongoDB.
7. `presentation.present_explore()` prepares an ordinary answer and a table.
8. React `AnswerView()` shows a heading such as **« Livraisons historiques par client »**, a table, and collapsed sections for warnings/source details.

**Why this is better:** One BL may contain several Excel lines. Simply counting spreadsheet rows can overstate actual delivery-note counts. Each metric must have a business definition before it's offered to a user.

**Why don't we show raw `dataset`, `group_by`, `event_type` by default?** Those are implementation details. They remain in the collapsible technical section so developers can debug errors, while employees see the requested result.

## 4. A second example: grafting rate versus event count

**Question:** `Quel est le taux moyen de greffage par article ?`

Old error: the routing keyword `greffage` selected `trace_events` and `records`, returning a *count of events*.

Correct approach: the question requests a **percentage**, so V4 selects `historical_grafting`, metric `grafting_rate`, grouping `article` (admin only). The value is the mean of valid **recorded Excel percentage values**, as defined in the catalog. It's not automatically a plant-weighted rate; it is not proof of a Blockchain transaction, and no real-world agronomic explanation is inferred from the percentages alone.

The V4 planner refuses unsupported group-by fields. A request `grafting rate by city from active records` will not silently return a total number of events in place of the requested percentage.

## 5. A third example: what an embeddings-based document search does

**Question:** `Comment fonctionne le contrôle qualité avant livraison ?`

1. `api._is_document_question()` prioritizes explanatory/quality-procedure language.
2. `documents.load_chunks()` reads only `.md` files explicitly listed in `backend/rag_documents/manifest.json`.
3. `documents.visible()` filters by **the authenticated user's role and site before ranking**. Filtering *after* ranking could expose forbidden snippets or bias results.
4. `documents.lexical_rank()` calculates keyword-based relevance for allowed chunks.
5. If embeddings are enabled, `documents.search_documents()` also converts the question and chunks to multilingual vectors and combines semantic similarity with lexical ranking. It falls back to lexical search when the model is unavailable.
6. `llm.synthesize()` can optionally provide a fluent, cited answer via a LOCAL Ollama service. If disabled or untrustworthy, the assistant displays relevant document excerpts with attribution.

The supplied quality guide describes **the software's validation workflow**, not a Royal Plants-approved phytosanitary or agricultural SOP. That status must remain visible.

### Vocabulary

- **Chunk:** short portion of a document. Splitting a 30-page procedure into chunks helps retrieve the relevant section.
- **Embedding:** numeric vector representing a text's meaning; semantically similar texts tend to have related vectors.
- **Lexical search:** relevance from actual overlapping words, e.g. `contrôle`, `qualité`, `livraison`.
- **Semantic search:** relevance from embeddings, useful for paraphrases such as `inspection sanitaire avant expédition` versus `contrôle qualité avant livraison`.
- **Hybrid retrieval:** combines both, rather than relying on one signal exclusively.
- **Reranker:** a later (optional) model that reorders retrieved candidates; not part of the current default kit. Add only after a documented retrieval benchmark.
- **Grounding:** restricting answers to authorized, actually retrieved material.
- **Hallucination:** a plausible but unsupported statement or calculation.
- **ACL:** access-control list; document and dataset permissions.
- **Provenance:** where a number came from, including source type and source-row references.

## 6. How the optional LLM planner helps with unfamiliar questions

Without an LLM, `planner.py` understands curated French patterns and entities. That is predictable but can't cover arbitrary paraphrases.

The new `llm_planner.py` can convert an unfamiliar question into JSON **only if you explicitly enable it**. The prompt contains a catalog of authorized datasets/metrics/filters. The result is validated using `validate_plan()` and then passed through the same checked `explorer.explore()` path. The LLM never generates or executes MongoDB aggregation pipelines, never receives unrelated customer records for routing, and cannot override the user's role/site rules.

```
Employee question
  -> deterministic planner, if recognized
  -> else (optional): local Ollama JSON planner
  -> validate JSON against CATALOG and user role
  -> execute safe read-only calculation
  -> evidence + French explanation
```

**What this does not guarantee:** The model may still choose the wrong *allowed* metric or misunderstand the requested time period. Always show the selected source and let employees open the Data Explorer to correct the query. A schema-valid answer is not automatically a semantically correct answer.

## 7. Source selection and access control

The system distinguishes:

- **MongoDB operational lots:** actual authorized records; lot references, sites, quantities, events, quality and delivery state.
- **Excel C25 history:** historical production/greffage/delivery observations, **admin-only**; the five-digit lot-code association does not prove genealogy or create physical stock.
- **Internal docs:** only files in the approved manifest, with explicit roles/sites and document status.
- **Hyperledger Fabric:** not operational yet; no historical record is described as on-chain verified until an actual proof exists.

A fallback is **not** a merge. For example, operational `plantsLost / quantitySown` isn't equal to historical `Perte_Totale`. V4 may show the related historical measure when the operational one is empty, but explicitly says it is **different**.

## 8. Why exact statistics must stay deterministic

LLMs can produce arithmetic errors, especially when handling many rows or mixed units. The calculation engine has hard rules:

- Allowed datasets, fields, metrics and groupings defined in `catalog.py`.
- Read-only MongoDB projections and site restrictions before loading rows.
- No arithmetic across incompatible units such as tray counts versus individual plants.
- Missing/invalid percentages rejected, and ignored count reported.
- Weighted mean only where the metric definition explicitly specifies its denominator.
- Caps trigger **PARTIAL** notices rather than claims of total coverage.
- Sample source identifiers are displayed; they help trace results but do **not** by themselves prove every aggregate row was independently audited. A complete audit/export is a later extension.

## 9. How to measure RAG quality

Do not optimize only on whether the app returns a fluent paragraph. Evaluate at least four independent layers:

| Layer | Example acceptance check |
|---|---|
| Intent/plan | `taux moyen de greffage par article` -> `historical_grafting/grafting_rate/article` |
| Retrieval | All required authorized records or document passages found within the allowed scan |
| Computation | Correct average, correct units, unique BL counts vs row counts, no invalid value silently included |
| Answer & grounding | User-readable result, correct source/campaign, no fabricated fact, meaningful limitations |

Also test users with multiple sites, no sites, non-admin access, empty databases, new paraphrases, missing docs, optional LLM offline, and incomplete scans.

The kit's 47 tests and 30 routing examples are **development regressions**. They are not real-world field accuracy figures. A strong PFE/resume project should include a separate unseen evaluation set written from actual, permission-appropriate employee questions and a scored error analysis.

## 10. Suggested future research directions

When the V4 integration is stable against live company data, you could explore:

1. An **LLM planner benchmark** against the deterministic planner using held-out French questions and exact plan correctness.
2. Better document chunking by heading and metadata; optionally dense/lexical rank fusion and reranking.
3. Conversation memory for follow-up questions like `Et pour la variété Roma ?`, but **keep all state within the user's authorized scope** and never reuse another user's retrieved sources.
4. Time-aware analytics using explicit period definitions and validated date fields.
5. Separate answer evaluation for factual correctness, citation support, retrieval relevance, safety and latency.
6. Fine-grained lot/entity linking only with verified identifiers; never infer historical genealogy from the shared five-digit code alone.

A precise resume description could be:

> Built a permission-aware Hybrid RAG assistant for agricultural production traceability using FastAPI, MongoDB, read-only Excel history, multilingual document retrieval and optional local LLM-based query planning. Implemented audited analytics, evidence-linked answers, site-level access controls, regression tests and a React data-exploration interface.
