# SmartTrace consolidation — installation, paths and verification

## Before copying anything

**Back up your actual current project.** The available source snapshots are Phase 5 / Phase 6 Human Review + Phase 7 RAG connection. Your local `App.jsx` may contain additional newer changes. Always prefer the minimal patch to blindly replacing a file.

Windows project root (from your terminal log):

`C:\Users\LEGION\Desktop\TERMINAL\Final Year 1st Sem\Ongoing mini projects for discovery\royal-plants-smarttrace-phase3`

## Files to add/replace

| Kit file | Copy to local project | Action |
|---|---|---|
| `backend/app/history.py` | `backend/app/history.py` | MERGE/REPLACE if local version matches Phase 5/6; adds filtered `overview` and article/variety option fix. |
| `frontend/src/LotHistoryFilters.jsx` | `frontend/src/LotHistoryFilters.jsx` | **ADD** new cascading selector. |
| `frontend/src/lot-history-filters.css` | `frontend/src/lot-history-filters.css` | **ADD** selector styling and optional baseline panel styling. |
| `frontend/src/App.jsx` | `frontend/src/App.jsx` | **MERGE**. Full reference provided but keep local NLP/RAG/custom routes. |
| `frontend/src/OperationalWorkspace.jsx` | `frontend/src/OperationalWorkspace.jsx` | **MERGE**. Only folds admin historical activation inside a details panel. |
| `patches/CHANGES_TO_MERGE.patch` | no destination required | Unified source diff for history, App, OperationalWorkspace. |
| `tests/test_history_filters_offline.py` | `tests/test_history_filters_offline.py` | **ADD** portable mock tests. |
| `blockchain/chaincode/main_test.go` | `blockchain/chaincode/main_test.go` | **ADD** optional offline Go unit tests. |
| `blockchain/gateway/main_test.go` | `blockchain/gateway/main_test.go` | **ADD** optional offline Go unit tests. |
| `scripts/fabric_preflight.sh` | `scripts/fabric_preflight.sh` | **ADD** read-only Docker/Fabric preflight. |
| `docs/*.md` | optional project docs | Learning guides (NLP, RAG, blockchain, filters). |

The kit does not alter your original Excel workbooks, MongoDB records, `.env`, CamemBERT models, `backend/rag` source, or real Blockchain ledger.

## API prerequisites

In `backend/app/main.py`, keep historical routes admin-only and existing NLP/RAG routers registered. Example check:

```python
app.include_router(historical_router, dependencies=[Depends(require_role('admin'))])
# plus your existing app.include_router(nlp_router) and app.include_router(rag_router)
```

**Do not add the historical router twice.** The backend already has `/api/historique/lots` and `/api/historique/filters`.

## Development commands

From project root in **PowerShell**:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

In a new **PowerShell** terminal:

```powershell
cd frontend
npm run dev
```

The new browser code calls:

```text
GET /api/historique/filters?campaign=C25&species=TOMATE
GET /api/historique/lots?campaign=C25&species=TOMATE&article=...&search=...&limit=24&offset=0
GET /api/historique/overview?campaign=C25&species=TOMATE&article=...
```

With an authenticated admin, verify these first at `http://127.0.0.1:8000/docs`. Filters are intended for admins because the underlying historic Excel records cannot be reliably scoped to live operating sites.

## Local offline tests (run without Atlas/Excel)

```powershell
cd "C:\Users\LEGION\Desktop\TERMINAL\Final Year 1st Sem\Ongoing mini projects for discovery\royal-plants-smarttrace-phase3"
.\backend\.venv\Scripts\python.exe tests\test_history_filters_offline.py
```

Expected: 6 passed. This does not replace live tests.

For Fabric, see `docs/BLOCKCHAIN_TERMINAL_CHECKLIST.md`. Go tests can run before Docker works; real deployment cannot.
