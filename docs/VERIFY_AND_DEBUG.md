# Verify, evaluate and debug SmartTrace RAG V4

## Quick smoke test

From `backend/` in VS Code PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_rag_advanced_v3.py tests/test_rag_v4.py tests/test_rag_v4_api.py -q
.\.venv\Scripts\python.exe rag_eval/check_v4_routing.py
```

The supplied kit passed **49 mock/offline tests** and **30 development routing cases** when packaged. Your project may have additional custom code or database differences; treat those as separate integration tests.

## First questions to ask as an administrator

1. `Combien de livraisons par client ?` — expect operational data if present; otherwise labeled Excel history and distinct BL counts, not spreadsheet row counts.
2. `Combien de plants ont été semés par espèce ?` — if operational lots are empty, admin historical fallback. Display the actual metric **Graines semées** rather than pretending it's a count of living plants.
3. `Quel est le taux moyen de greffage par article ?` — expect historical percentage, not event count.
4. `Quelle quantité a été livrée par client ou par ville ?` — expect two separate views and no mixing of incompatible units.
5. `Quels lots ont un ratio de perte supérieur à 30 % ?` — operational ratio, or a **clearly labeled non-equivalent historical** loss percentage if no operational data.
6. `Compare les taux de germination des variétés de tomates pour C25.` — production Excel `Taux_Germination` with declared meaning/weighting, not inferred germination from all other quantities.
7. `Comment fonctionne le contrôle qualité avant livraison ?` — application guide, with explicit **NON OFFICIEL** status.
8. `Quel est l'historique du lot 13877 ?` — exact lookup; the 5-digit link is only a candidate cross-source association.

## Inspect endpoint availability

Login to FastAPI Swagger at `http://127.0.0.1:8000/docs` (the RAG routes require a valid JWT). Verify `GET /api/rag/status`:

```json
{
  "ready": true,
  "read_only": true,
  "documents": {
    "ready": true,
    "visible_documents": 2,
    "visible_passages": 6,
    "hint": "Index documentaire accessible."
  }
}
```

The numbers above are **illustrative**; installed document counts may differ. If `visible_documents=0`, check `backend/rag_documents/manifest.json` and its listed Markdown files **before** changing embeddings or prompts.

## Common symptoms and fixes

| Symptom | Meaning | Check |
|---|---|---|
| `404 /api/rag/ask` | Router not registered | Ensure exactly one `app.include_router(rag_router)` in `backend/app/main.py` |
| `401` | Missing/expired JWT | Log in again |
| `403` | Dataset not allowed for role/site | Use catalog for this user; Excel remains admin-only |
| `503` MongoDB | DB client unavailable | Atlas connection and application startup |
| `503` Excel | Source paths/config missing | Historical files under the correct `data/` directory |
| No operational records | Empty authorized collection / filters | Check MongoDB documents, permissions, siteCodes, campaign; do not automatically assert a global zero |
| No document evidence | Document absent/blocked/low similarity | Inspect `/api/rag/status`, manifest, file, roles/sites, retrieval thresholds |
| Missing `sentence_transformers` | Optional embeddings dependency not installed in FastAPI interpreter | Set `RAG_USE_EMBEDDINGS=0` or install in `.venv` |
| Ollama unavailable | Optional local service not running | Leave `RAG_USE_OLLAMA=0` and `RAG_USE_LLM_PLANNER=0` until it works |
| 10 of 137 groups | Paginated preview | Click **Modifier cette analyse dans l'explorateur**, choose more rows/pagination; it is not the entire result |
| Weird source metrics | Query interpretation may be wrong | Inspect technical details; correct dataset/metric/group in Explorer |

## Evaluation methodology

1. Gather 50–100 **new**, representative French questions with consent and without unnecessary customer/personally identifying details.
2. Annotate expected route, dataset, metric, grouping, filters, accessible sources, unit, expected numerical answer and source references.
3. Hold this set out of prompt selection and keyword tuning. Repeatedly editing prompts to score on it turns the test into a development set.
4. Score **plan accuracy**, **numerical accuracy**, **retrieval coverage**, **faithfulness**, **source correctness**, **permission isolation**, **unsupported-question refusal** and latency separately.
5. Compare deterministic-only vs local-LLM planner vs semantic retrieval on the same examples.
6. Measure multi-turn follow-ups independently; the current V4 prototype does not implement conversation-state query refinement.

## Known limitations (do not hide in a resume/demo)

- No guarantee of understanding **every** French, Arabic or Tunisian-dialect question.
- No unbounded database queries; large scans are capped and must report partial coverage.
- No general-purpose safe SQL/MQL generation, because the prototype only allows catalog-defined fields and metrics.
- No automatic conversion of mixed historical delivery units into plants.
- No claim that matching five-digit historical codes prove the same physical plants.
- Source samples show some contributing rows, not a complete independent audit of every aggregated value.
- Document-based answers depend on approved manifest content; absent SOPs cannot be guessed.
- Optional LLM plan might be wrong despite passing field validation, so source and query corrections remain available to the employee.
- No live Fabric verification yet; never mark an event as Blockchain-verified solely because an answer is returned.
