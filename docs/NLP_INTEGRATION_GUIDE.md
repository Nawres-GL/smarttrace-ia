# SmartTrace Phase 6 — Integrating CamemBERT exports

## Scope
The existing Phase 6 project already contains `/api/nlp/interpret`, `AssistantNLP.jsx`, and the form-prefill link. Replace only the files in this kit. No new MongoDB collections are necessary, and no Fabric server is required. This does not change the Excel workbooks or audit workflow.

### Files to replace
- `backend/nlp/transformer.py`: lazy local loading of exported CamemBERT models; top-3 classifier labels and raw NER spans.
- `backend/nlp/service.py`: hybrid parsing. Low-scored neural outputs never override known rule-parsed values. High-scored entities are format-validated before prefilling.
- `frontend/src/AssistantNLP.jsx`: optional explanation panel showing actual scores and NER spans.
- `frontend/src/assistant-nlp.css`: diagnostics styling.

### Files to add
- `backend/nlp/check_models.py`: safe model smoke test using local files.
- `backend/tests/test_nlp_hybrid.py`: no-download tests of uncertain and contradictory predictions.

## Model folders
Unzip Colab export and copy the **folders** (not the outer ZIP) into:

```
backend/
  models/
    nlp-intent/
      config.json
      model.safetensors
      tokenizer files...
    nlp-entities/
      config.json
      model.safetensors
      tokenizer files...
```

`model.safetensors` can be `pytorch_model.bin` for older exports. Keep any `special_tokens_map.json`, `tokenizer.json`, `tokenizer_config.json`, and SentencePiece model files. Paths above assume commands run from `backend/`.

## Private backend/.env
```
NLP_MODE=hybrid
NLP_INTENT_MODEL_DIR=models/nlp-intent
NLP_ENTITY_MODEL_DIR=models/nlp-entities
NLP_DEVICE=-1
NLP_MIN_INTENT_SCORE=0.80
NLP_MIN_ENTITY_SCORE=0.85
```
`NLP_DEVICE=-1` uses CPU; use `0` only when the FastAPI interpreter has CUDA-enabled PyTorch and a compatible NVIDIA GPU. These thresholds are initial conservative heuristics, **not calibrated probabilities**.

## Windows PowerShell commands
```
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-nlp-models.txt
.\.venv\Scripts\python.exe -m nlp.check_models
.\.venv\Scripts\python.exe -m pytest tests/test_nlp_hybrid.py -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```
Install the optional model packages only if they are not already installed. Models are loaded on the first interpret request and cached; first inference can be slower. Run `check_models` first to surface path or dependency errors; do not commit the model binaries if they are confidential or large. The model-check command reads `.env` from backend.

React can be started as before (`npm run dev` from `frontend/`). Open **Assistant NLP** and submit one French description. The assistant asks `/api/nlp/interpret`; when it resolves an active authorized lot and the role is allowed, **Ouvrir le formulaire prérempli** passes a draft into `OperationalWorkspace.jsx`. That form still requires manual validation through the ordinary FastAPI production endpoint. The NLP route never creates an audit event.

## What the low scores mean
Current user's example: classifier `TRANSFERT` score ~0.42, NER scores ~0.05–0.35, split `chambre` / `1`. These are **not sufficiently reliable for autonomous extraction**. The rule-based parser correctly handles straightforward numeric facility references while the model is being improved. Read actual `evaluation_report.json` for per-task synthetic metrics; also evaluate on real employee language. Never describe synthetic F1 as real-world F1.

## Improving the trained model
- Inspect the NER confusion/annotation for `LOCATION`, `ORIGIN`, and `DESTINATION` and add more unambiguous, manually reviewed examples. Sentence-level role assignment is challenging, especially with "de"/"vers" order changes.
- Add omission, negation, colloquial wording, alternate location formats, mixed operations, and real-world anonymized expressions to the evaluation corpus.
- Re-train and compare entity-level F1, per-intent F1 and complete-draft accuracy. Increasing epochs alone is not a quality guarantee.
- Check errors on unknown lots, named facilities, two lots, and numbers representing dates or percentages. Employees always confirm before a stock-changing operation.

**Security:** The private `.env`, JWT secret, MongoDB URI, company workbooks, raw employee text, and model training credentials are not included in this kit.
