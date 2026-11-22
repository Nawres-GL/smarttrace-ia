# Royal Plants SmartTrace — Phase 7 V4: Evidence-first Hybrid RAG

**Goal:** make questions more useful and answers more legible, without pretending that an LLM has unlimited access to the business or that historical Excel is certified by Fabric.

## Start here

1. [`docs/INSTALLATION_STEP_BY_STEP.md`](docs/INSTALLATION_STEP_BY_STEP.md) — exact project folders, which files to add/replace, commands.
2. [`docs/LEARN_RAG_FROM_ZERO.md`](docs/LEARN_RAG_FROM_ZERO.md) — detailed conceptual lesson with complete examples.
3. [`docs/FUNCTION_BY_FUNCTION_REFERENCE.md`](docs/FUNCTION_BY_FUNCTION_REFERENCE.md) — every function in every backend module, plus React component logic.
4. [`docs/VERIFY_AND_DEBUG.md`](docs/VERIFY_AND_DEBUG.md) — demo questions, API checks, evaluation, troubleshooting.

## Changed in V4

- **More accurate question interpretation:** grafting rates are no longer mistaken for event counts; city questions aren't answered with a global total; `client OU ville` produces two separate views.
- **Historical fallback for authorized admins:** if relevant operational data is empty, try a comparable historical metric **in a different source**, with an explicit notice. Loss ratios use a *related but different* historical metric and clearly warn against direct equivalence.
- **User-friendly French answers:** a concise answer, a readable result table, source provenance, collapsible source evidence and diagnostic details. No raw JSON in the normal view.
- **Approved documents:** a `/api/rag/status` indicator shows whether the manifest and documents are installed and accessible.
- **Optional local JSON planner:** unfamiliar statistical questions can be converted to strictly validated catalog selections through Ollama (`RAG_USE_LLM_PLANNER=1`); raw DB queries are never generated.
- **Read-only architecture preserved:** live MongoDB scoped by site and role, admin-only Excel, no chatbot-triggered database writes.

## Verifications performed in the kit

- 49 offline tests for existing functionality, new routing and permissions, API orchestration using mock collections.
- 30/30 purpose-built French routing regression examples. **These are development tests, not a blind benchmark.**
- JSX syntax transpilation check successful.
- **Not tested here:** your live Windows MongoDB Atlas, local React installation, real employee role profiles, Ollama model, or a production Fabric ledger.

## Directories

```text
backend/
  rag/
    api.py, catalog.py, planner.py, source_selection.py,
    explorer.py, presentation.py, structured.py, analytics.py,
    documents.py, llm.py, llm_planner.py, schemas.py, __init__.py
  rag_documents/
    manifest.json, controle_qualite_smarttrace.md,
    smarttrace_guide_technique.md
  rag_eval/
    check_v4_routing.py, v4_regression_questions.jsonl,
    check_routing.py, routing_questions.jsonl
  tests/
    test_rag_v4.py, test_rag_v4_api.py, test_rag_advanced_v3.py
frontend/
  src/
    RAGAssistant.jsx, rag-assistant.css
```

**The ZIP does not replace your `App.jsx`, `OperationalWorkspace.jsx`, CamemBERT or Fabric files.**
