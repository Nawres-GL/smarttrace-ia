# Install Phase 7 V4 in your existing SmartTrace project

Use your current application; **do not replace the project with an old Phase 6/7 archive.**

## 0. Backup first

Open the project root in VS Code (the folder containing `backend/` and `frontend/`). Commit existing work or copy your existing `backend/rag/` and `frontend/src/RAGAssistant.jsx` to a backup directory. Never share, overwrite or commit `backend/.env` or MongoDB credentials.

## 1. Exact file destinations

The paths on the **left are inside this ZIP**; the paths on the **right are inside your existing local SmartTrace project**.

| Kit file | Destination | Action | Why |
|---|---|---|---|
| `backend/rag/api.py` | `backend/rag/api.py` | **REPLACE / MERGE** | Query orchestration, fallback, optional planner, human-readable API response |
| `backend/rag/planner.py` | `backend/rag/planner.py` | **REPLACE / MERGE** | Correct intent→dataset/metric, grouping, filters |
| `backend/rag/explorer.py` | `backend/rag/explorer.py` | **REPLACE / MERGE** | Retains safe calculations and now returns structured tables |
| `backend/rag/documents.py` | `backend/rag/documents.py` | **REPLACE / MERGE** | Existing lexical/embedding retrieval plus document diagnostics |
| `backend/rag/source_selection.py` | `backend/rag/source_selection.py` | **ADD** | Explicit admin-only historical fallback policy |
| `backend/rag/presentation.py` | `backend/rag/presentation.py` | **ADD** | Short French summaries, numerical result tables, provenance |
| `backend/rag/llm_planner.py` | `backend/rag/llm_planner.py` | **ADD** | Optional local Ollama JSON planner constrained to catalog |
| `frontend/src/RAGAssistant.jsx` | `frontend/src/RAGAssistant.jsx` | **REPLACE / MERGE** | Readable answers, tables, separate panels, collapsed evidence |
| `frontend/src/rag-assistant.css` | `frontend/src/rag-assistant.css` | **REPLACE / MERGE** | Styles table, evidence and main answer |
| `backend/tests/test_rag_v4.py` | `backend/tests/test_rag_v4.py` | **ADD** | Unit checks for routing, ACLs, output |
| `backend/tests/test_rag_v4_api.py` | `backend/tests/test_rag_v4_api.py` | **ADD** | Mock end-to-end orchestration checks |
| `backend/rag_eval/check_v4_routing.py` | `backend/rag_eval/check_v4_routing.py` | **ADD** | Run your French routing regression |
| `backend/rag_eval/v4_regression_questions.jsonl` | `backend/rag_eval/v4_regression_questions.jsonl` | **ADD** | Diagnostic question list |

**Keep existing files unchanged:**

- `backend/rag/catalog.py` (audited data dictionary)
- `backend/rag/structured.py` (exact lot and guarded MongoDB queries)
- `backend/rag/analytics.py` (existing specialized history/GERMINATION helpers)
- `backend/rag/llm.py` (optional local document synthesis)
- `backend/rag/schemas.py` (Pydantic request schema)
- `backend/rag/__init__.py`
- `backend/app/main.py` (if it already contains `app.include_router(rag_router)`)
- `frontend/src/App.jsx` (RAG page already connected in the previous patch)
- Your NLP and Blockchain modules; your Excel workbooks under `backend/data/`.

Reference copies of unchanged modules are provided in the ZIP so that you can inspect them while studying; use replacements above only unless your local code is older.

## 2. Confirm documents are present

The earlier failed quality-control answer strongly suggests the deployed `rag_documents` folder or `manifest.json` entry may be missing/incorrect. Check:

```text
backend/rag_documents/
  manifest.json
  controle_qualite_smarttrace.md
  smarttrace_guide_technique.md
```

The manifest must list `controle_qualite_smarttrace.md` with allowed roles. Keep the file explicitly labeled **application guide, not official Royal Plants quality SOP**.

If you already have more approved documents, **merge manifest entries**, rather than replacing the manifest wholesale. Do not index confidential staff/customer information without a permission review.

## 3. Suggested initial `.env` in `backend/.env`

```env
RAG_USE_EMBEDDINGS=0
RAG_USE_OLLAMA=0
RAG_USE_LLM_PLANNER=0
```

All three are optional. Start in deterministic mode to verify that calculation and retrieval work independently of the LLM.

After basic tests, if you want semantic document retrieval:

```env
RAG_USE_EMBEDDINGS=1
RAG_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

The `sentence-transformers` dependency/model should be installed in the **same Python environment that starts FastAPI**. For local LLM experimentation, install Ollama separately and use a model you have actually downloaded:

```env
RAG_USE_OLLAMA=1
RAG_USE_LLM_PLANNER=1
RAG_OLLAMA_URL=http://127.0.0.1:11434
RAG_OLLAMA_MODEL=qwen2.5:3b
```

**The Ollama planner is optional.** The JSON result is validated; it cannot access off-catalog fields, expand historical access or execute arbitrary MongoDB commands. Never point `RAG_OLLAMA_URL` at an external service containing unapproved confidential data.

## 4. Python / VS Code commands

From **PowerShell**, inside `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_rag_advanced_v3.py tests/test_rag_v4.py tests/test_rag_v4_api.py -q
.\.venv\Scripts\python.exe rag_eval/check_v4_routing.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

If `test_rag_advanced_v3.py` isn't installed in your local backend, you can copy it from the ZIP's `backend/tests/` (it is a self-contained mock test file), or omit it from that command. `pytest` must be installed in your virtual environment.

Open a second terminal inside `frontend/`:

```powershell
npm run dev
```

`frontend/src/App.jsx` should **already** import `RAGAssistant` and render it for `page === 'rag'` from the previous integration. If not, add those two lines and the sidebar route; do not replace a newer `App.jsx` wholesale.

## 5. Check API and documents

In your browser open `http://127.0.0.1:8000/docs`. Confirm these authenticated routes:

- `GET /api/rag/status` — includes `documents.ready`, `documents.visible_documents`, `documents.visible_passages`.
- `GET /api/rag/catalog` — authorized fields/datasets for the current account.
- `POST /api/rag/ask` — natural-language question.
- `POST /api/rag/explore` — user-selected safe calculation.

Check `documents.visible_documents >= 2` when logged in with a role allowed by the sample manifest. If 0, inspect the folder, manifest and source permissions; do not tune embeddings first.

## 6. Verify with real data, not just tests

1. As admin: ask *“Combien de livraisons par client ?”*. If operational deliveries are empty but authorized historical Excel has rows, expect a **historical** table explicitly labeled as such.
2. As admin: ask *“Quel est le taux moyen de greffage par article ?”*. Expect a percentage, **not an event count**.
3. As admin: ask *“Quelle quantité a été livrée par client ou par ville ?”*. Expect two separate tables, and historical units kept separate.
4. Ask about the quality workflow. Confirm the indexed application guide is returned and **not misrepresented as an approved agronomic SOP**.
5. As a production-only user, verify that historical Excel cannot be queried via the Explorer or natural language.
6. Check an unavailable measure and verify the answer explicitly says the source doesn't support it.

## 7. Rollback

Restore your backed-up seven changed files, restart FastAPI and React. This upgrade changes **no MongoDB schema, Excel file, CamemBERT weights or Fabric contract**.
