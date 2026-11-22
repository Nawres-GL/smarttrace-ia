# SmartTrace Phase 7 — Improving RAG questions, not model accuracy

## Problem diagnosis

The first RAG version had **query-coverage gaps**:

1. `Quels lots ont un taux de perte supérieur à 30 % ?` called `_rank_losses()` in `rag/structured.py`, checking only operational `db.production_lots` and using `plantsLost / quantitySown`. It did **not** read the historical grafted-production `Perte_Totale` field.
2. `Compare les taux de germination des variétés de tomates pour C25` was not routed as a structured query. The assistant fell through to document retrieval, which naturally could not answer a numerical analysis question.
3. The original historical lot source list kept just two delivery rows. For lot 13877, there are five delivery rows, so the reference list was incomplete.
4. The document corpus contained a software guide but no quality-workflow information for the question `Quelles sont les étapes du contrôle qualité avant livraison ?`.

## Important dataset finding

Inspection of the original **Production_franc_valid-3.xlsx** identified a real column named `Taux_Germination`. The **Production_Greffee_Final_corrected-1.xlsx** contains `Perte_Totale`, `Perte_Greffage`, and `Taux_Germination_Franc`. The Phase 6 ETL function `make_production_record()` did not expose `Taux_Germination` at the top level, but it **already preserves every original cell** in `raw_cells`.

The new `historical_reported_germination()` retrieves the existing, explicit `Taux_Germination` column from `raw_cells` without modifying Excel or ETL. It aggregates values across varieties using a **weighted average with `QteSemis_Rapport`** as weight, restricted to the requested campaign and species. This is clearly identified as a **reported historical Excel field**, not an independent validation of germination in the field. Groups missing rate/weight are excluded. The source list displays row references and lots counted.

The admin-only grafting loss fallback reads **`Perte_Totale`** and does not confuse this historic value with the operational ratio `plantsLost / quantitySown`. Any values outside 0–100% are excluded from the ranking and noted.

## Installation in VS Code / PowerShell

1. Save/commit your current project state.
2. Copy/add the three files below relative to your existing `backend/` directory:

   - **REPLACE / MERGE** `rag/structured.py`
   - **ADD** `rag/analytics.py`
   - **REPLACE / MERGE** `rag/api.py`

3. Copy **ADD** `rag_documents/controle_qualite_smarttrace.md` and **MERGE** the new entry from the delivered `rag_documents/manifest.json` into your own manifest. **Do not overwrite existing document entries** you may have added.
4. For optional tests, copy `tests/test_rag_analytics_upgrade.py` and `tests/test_rag_phase7.py` if missing.
5. No changes are needed in `App.jsx`, `RAGAssistant.jsx`, `app/main.py`, `.env`, `nlp/`, or in the original `.xlsx` files. The registered `/api/rag/ask` endpoint is reused.

Run from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_rag_phase7.py tests/test_rag_analytics_upgrade.py -q
.\.venv\Scripts\python.exe -c "from rag.structured import structured_search; from rag.analytics import historical_reported_germination; print('RAG OK')"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

If your test environment lacks pytest, install it in the selected virtual environment using the existing development requirements; do not modify global Python.

## Behavior to verify (as administrator)

- **Historical loss rates:** `Quels lots ont un taux de perte supérieur à 30 % ?` → When no eligible operational result is found, RAG may now return separate historical grafting losses using Excel `Perte_Totale`; responses clearly say **historical non-certified**. If there are operational matches, those remain prioritized. Results depend on source records and campaign filters.
- **Tomato comparison:** `Compare les taux de germination des variétés de tomates pour la campagne C25.` → If available operational GERMINATION events exist, the ratio is calculated from recorded `quantite_germee / quantite_semee`. Otherwise, an admin may receive weighted historic reported `Taux_Germination`, with row citations. A normal employee is not allowed to see admin-only historical Excel values.
- **Lot history:** `Quel est l'historique complet du lot 13877 ?` → For the admin historical lookup, 1 production + 1 greffage + 5 delivery lines now yields **8 sources including the summary**, if all are present. Very large histories are explicitly truncated and marked partial.
- **Quality guide:** `Quelles sont les étapes du contrôle qualité avant livraison ?` → A relevant software-workflow document should now be retrievable. It is a *technical description of form validations*, **not** an approved Royal Plants quality/SOP document.

## Behavior to verify (ordinary employee)

- All MongoDB production/trace-events queries continue filtering by user `siteCodes`.
- Historical Excel reporting remains **administrator-only** because site/ownership cannot reliably be derived from these sources.
- Document ACLs must be satisfied before any embedding or LLM call.
- The RAG assistant remains READ-ONLY and never submits production updates.
- A lack of eligible operational records is reported as a limitation of the *operational data*, not as proof no historical losses or germination records exist.

## Why this is still a pilot

The new tests use a fake MongoDB and fake historical index. Run with your actual Atlas/Excel environment before presenting numerical conclusions. There is no general agentic database query generation, no complete historic genealogy, no Fabric certification, and no independently validated company-quality protocol. Revisit data aggregation/business definitions with Royal Plants before operational use.

**Next optional improvements:** a retrieval evaluation corpus (expected source IDs, numerical correctness, role-access rejection), historical view pagination, multi-campaign comparisons, and scalable pre-computed analytical materializations.
