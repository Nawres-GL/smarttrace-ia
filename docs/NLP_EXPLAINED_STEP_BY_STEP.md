# SmartTrace NLP: Understand the page, the files and their functions

**Based on the Phase 6 backend + V4 hybrid inference + the latest provided Human Review UI.** If your local project has newer customizations, use this as the conceptual reference, not proof that your exact code is identical.

## 1. What problem NLP solves

A production employee normally types the operation into many fields. Example:

> « Nous avons transféré 230 plants du lot RO-54321/25 de la chambre 1 vers la serre 5. »

The NLP assistant *proposes* a form:

- Intent (`TRANSFERT`) -> SmartTrace action `transfer`.
- Entities: QUANTITY=230; LOT=RO-54321/25; ORIGIN=chambre 1; DESTINATION=serre 5.
- Validated field candidates: quantity=230, origin=CHAMBRE-01, destination=SERRE-05.
- Resolves the real **authorized** operational MongoDB lot separately (if it exists).
- Opens an editable form. It does **not** submit/commit an operation.

Two CamemBERT models are used: a **sequence classifier** for the overall intent (12 labels including HORS_SUJET), and a **token classifier** for entity spans (BIO tagging, 24 entity types in the training setup). Both were fine-tuned on synthetic domain examples. They do not know stock balances, whether a warehouse exists, or whether a named employee is authorized.

## 2. How to read the NLP page

**01 · Votre description** (`frontend/src/AssistantNLP.jsx`): input the French text, choose an example, and click `Analyser la description`. This sends `POST /api/nlp/interpret` with a Bearer JWT and the text. No stock/event write occurs.

**02 · Proposition structurée**: shows predicted action, cited lot, recognized fields, missing required fields, and warnings. `Score indicatif` is a model output; it is NOT a calibrated probability that the operation is true or valid.

**Diagnostic CamemBERT**: optional developer-facing scores, alternative intents and raw NER entities. It is **not** a model's private reasoning or explanation of its thought process. The raw entity scores can be low even when a deterministic parser finds the same field safely.

**Opération à ouvrir**: the employee may select a permitted form, even if dates or a valid lot are missing. If changing operation type, the proposed fields are cleared to avoid cross-operation prefill.

**Ouvrir le formulaire**: calls the `onApply` callback in `App.jsx`, which navigates to `OperationalWorkspace.jsx` with a **draft**. The employee selects a real operational lot and completes all required fields before pressing `Valider l'opération`. Only that final operation endpoint can update MongoDB, after role/site/stock validation.

**Hard stops**: negative statements, questions, and requests containing multiple different operations require reformulation. This is not because the AI can't be corrected; it's because those texts shouldn't be handed to an executable agricultural action by guesswork.

## 3. Complete request flow, with file/folder locations

```text
frontend/src/AssistantNLP.jsx         React text form + diagnostics
      | POST /api/nlp/interpret
      v
backend/nlp/api.py                  User JWT, allowed actions, visible MongoDB lots
      |
      v
backend/nlp/service.py              Hybrid combination + field validation
      +--> backend/nlp/rules.py       French lexical parser
      +--> backend/nlp/transformer.py Two local CamemBERT models
      +--> backend/nlp/safety_guard.py Review flags
      |
      v
React draft callback (App.jsx) -> frontend/src/OperationalWorkspace.jsx
      |
      v
backend/app/operations.py            Business rules + MongoDB event + Fabric outbox
```

## 4. Function-by-function NLP backend reference

### `backend/nlp/rules.py` — deterministic baseline

| Function | Responsibility and why |
|---|---|
| `ascii_lower(text)` | Converts case and accents to a consistent form to match French terms robustly. |
| `classify(text)` | Looks for action cues, returns an intent or an ambiguous/unknown result. It's a **heuristic**, not a trained probability. |
| `_date(text)` | Parses dates/relative expressions; keeps date interpretation out of the Transformer. |
| `_locations(text)` | Detects text patterns for origins/destinations/locations. |
| `_lot(text)` | Finds a potential lot reference; it does **not** prove that a lot exists in MongoDB. |
| `_number_after(...)` | Helper to associate numeric spans with nearby keywords. |
| `_qty(text)` | Finds a candidate quantity; must later be checked by operational constraints. |
| `_temperature(text)` | Extracts a temperature value from matching French text. |
| `_humidity(text)` | Extracts humidity values, not temperature. |
| `extract(text)` | Main deterministic parser. Builds base draft containing action, fields, missing fields, and warnings. |

Important constants: `ACTION` maps model intent labels to SmartTrace actions (`TRANSFERT -> transfer`). `REQUIRED` lists mandatory fields by action (e.g. transfer quantity, origin, destination). Changing form requirements must be coordinated with `backend/app/operations.py`.

### `backend/nlp/transformer.py` — trained CamemBERT inference

| Function | Responsibility and why |
|---|---|
| `_folder(...)` or `load_models()` (depending on your installed version) | Resolves saved model directories and loads intent and NER pipelines lazily. |
| `predict(text)` | Returns ranked intent scores and labeled entity spans. It **does not** query stock or write to MongoDB. |

Model directories: `backend/models/nlp-intent/` and `backend/models/nlp-entities/`. The names in `.env` must point to the correct exported model folders; `NLP_DEVICE=-1` runs on CPU.

### `backend/nlp/safety_guard.py` — conservative language review

| Function | Responsibility and why |
|---|---|
| `normalize(text)` | Makes negation and operation-word matching less sensitive to French accents. |
| `assess_instruction(text)` | Flags negative, interrogative and mixed-operation sentences; returns reasons for manual reformulation, never a stock decision. |

### `backend/nlp/service.py` — hybrid orchestration

| Function | Responsibility and why |
|---|---|
| `_threshold(key, default)` | Reads experimental model score limits from the environment; clips invalid values. |
| `_identifier(text)` | Trims sentence-final punctuation from structured identifier candidates; raw NER offsets stay unchanged. |
| `_location(text)` | Translates recognized location *formats* such as `serre 5` into normalized codes; a real site/location must still be checked. |
| `_quantity(value)` | Parses French thousands separators and rejects unsuitable values. |
| `_fill_from_ner(draft,item)` | Copies only accepted entity candidates into **missing** draft fields; doesn't overwrite stronger deterministic extraction. Handles labels such as LOT, QUANTITY, PRODUCT, SUPPLIER, DELIVERY_NOTE, ROOTSTOCK_LOT and quality descriptions. |
| `_structured_identifier_fallback(draft,text)` | Recovers explicit `BL-...` delivery note codes when a token classifier mislabels them. |
| `parse_draft(text)` | The central service: starts with rules, adds guard flags, runs CamemBERT if configured, reports disagreements and fills validated fields. No MongoDB writes. |

`NLP_MIN_INTENT_SCORE=0.45` / `NLP_MIN_ENTITY_SCORE=0.45` are experimental suggestion thresholds. They should not determine whether the **employee can edit** a form. The backend still decides whether an operation may be saved.

### `backend/nlp/api.py` — security and handoff

| Function/class | Responsibility and why |
|---|---|
| `InterpretRequest` | Pydantic input schema, max text length and optional context lot ID. |
| `lot_number(value)` | Extracts a five-digit number for *candidate* historical linkage, not proof of identity. |
| `interpret(body,request,user)` | Requires login; checks role's allowed actions; calls `parse_draft`; queries visible MongoDB lots by exact reference or controlled five-digit historical hint; distinguishes `can_open_editor`, `needs_manual_completion`, and hard review flags. |

**Security boundary**: a user cannot gain access to a lot by merely including its number in their French sentence. `siteCode` constraints and the user's role are enforced on lookup and again on eventual submission.

## 5. Function-by-function React walkthrough

- `AssistantNLP({token,onApply})`: React component owning description text, loading state, proposed draft and selected operation.
- `display(value)`: formats a typed field value for readable cards.
- `interpret(event)`: handles `Analyser`, POSTs authenticated text, catches errors, stores results and defaults to a role-allowed action.
- Inline description `onChange`: updates text and clears stale previous prediction.
- Example button handlers: set an example description without submitting anything.
- Action selector `onChange`: allows choosing only a role-allowed action.
- `onApply(...)`: **provided by App.jsx**, strips prefill when operation has changed and navigates to the permitted editor.
- In `App.jsx`, `applyNlpDraft(...)`: stores a one-time proposed draft and picks Production/Quality/Delivery page.
- In `OperationalWorkspace.jsx`, `submitAction(...)`: actually calls operational FastAPI API after human confirmation. *This is the real transaction boundary.*

## 6. Testing and interpretation

Test one positive example of each of the 11 agricultural actions, plus `HORS_SUJET`, question, negation and multi-operation diagnostics. Record: intent accuracy, strict exact-span F1, complete draft accuracy, schema-valid fields, and the percentage of human edits made to each field. **An employee's correction rate** is a better practical measure of usefulness than raw softmax scores alone.

Keep real employee data private. Synthetic training accuracy cannot prove real-world reliability; pilot the assistant with permission-scoped observations and explicit employee confirmation.
