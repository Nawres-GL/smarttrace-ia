# RAG question-routing development checks

`routing_questions.jsonl` contains 27 **hand-written development examples**, not an unbiased real-user test dataset.

Run from `backend`:

```powershell
.\.venv\Scripts\python.exe rag_eval/check_routing.py
```

Use this to catch a **regression in how French questions map to the allowlisted dataset, metric, group and filters**. It does not test retrieval correctness or answer faithfulness. For a proper evaluation, maintain a separate blind question collection written by Royal Plants employees and compare numerical results with original records.
