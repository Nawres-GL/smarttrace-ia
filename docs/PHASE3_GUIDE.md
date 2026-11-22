# SmartTrace — Phase 3: corrections, Excel greffage, 8 étapes

This document explains **what was added or changed after Phase 1** (read-only two-workbook viewer), through Phase 2 and this revision. Application UI remains French. Source workbooks are NEVER modified.

## 1. Data architecture and limits

Three **historical** Excel files, in `data/` (all optional to users of the live operational forms, first two required for historic view):

| File | Purpose | Linking field |
|---|---|---|
| `Production_franc_valid-3.xlsx` | Production summary, lot, seed batch, variety, sowing and quantity totals | `LOT` → `13766` from `RO-13766/25` |
| `LivraisonC25_Clean-walid.xlsx` | Customers, note number, dated delivery lines/returns | `N° Lot` → `13766` |
| `Production_Greffee_Final_corrected-1.xlsx` | Historical grafted production, greenhouse, variety, grafting yield and losses | `Lot_Production` / `LOT` → `13877` from `GRO-G13877/` |

The only JOIN rule is a **standalone five-digit number**. We do **not** filter out lot-number links merely because articles, varieties or quantities differ. The frontend shows all source lines, including duplicates and multiple delivery transactions. A five-digit match is a **candidate linkage**, not proof of parent/child lot genealogy. Real genealogy arises only from new, validated grafting operations. The original Excel files are not overwritten, backfilled or edited.

All fresh activity is stored in MongoDB Atlas. Each newly validated operation writes the updated lot, append-only trace event and Fabric outbox marker in one MongoDB transaction. The outbox is not a Fabric transaction. Old Excel rows are explicitly **not Blockchain-certified**.

Optional future hosting: `HISTORY_MODE=atlas` after separately importing read-only historical *copies* (see CLI below); the Excel files remain unchanged. No automatic source synchronisation is implied. Customer data is admin-only for the historical API until multi-site ownership can be mapped safely.

## 2. Corrected login, step by step

**The real cause of your 422:** FastAPI/Pydantic's `EmailStr` refused `admin@example.test`, because `.test` is a reserved domain. It rejected the input before checking the password.

- `backend/app/auth.py`: `LoginBody.email` uses a deliberate syntax validator for internal account IDs and accepts `.test` as a local identifier. It normalizes case and whitespace. Other user-registration emails use the same rule. For production, use real organizational emails and verified identity management.
- `backend/app/main.py`: 422 responses include **field names and helpful messages**, not submitted passwords/secrets; DB errors no longer disclose connection details.
- `frontend/src/App.jsx`: displays precise error information from the API.
- `backend/app/bootstrap_admin.py`: inserts a new administrator if missing. **It intentionally doesn't update an existing user's password.**
- `backend/app/admin_tools.py`: if an admin already exists, you can explicitly rotate its password using a new temporary `ADMIN_PASSWORD` in `.env` and `python -m app.admin_tools --reset-admin-password --confirm`.

**Important:** Every secret previously pasted in chat (database password, JWT secret, administrator password) must be changed. Never commit `.env`. `backend/.env.example` includes placeholders only.

## 3. All eight stages and corresponding APIs

Every operation is authenticated, linked to an operator and site, carries a timestamped event and pending Blockchain proof, and is validated by FastAPI. Roles: `production`, `qualite`, `logistique`, `admin`.

| Stage | Route | Captured fields | Validation highlights |
|---|---|---|---|
| 1 Réception des semences | `POST /api/seed-lots` | supplier, variety, supplier lot, quantity, reception date, site | unique supplier lot, quantity > 0, site access |
| 2 Semis | `POST /api/lots` | sowing date, operator from JWT, seed lot, quantity, tray type, tray count, tray capacity, substrate | seed capacity, no sowing before reception, no sowing beyond tray capacity, no future sowing |
| 3 Germination | `POST /api/operations/lots/{id}/germination` | start/end/observation dates, duration hours, temperature, humidity, germinated quantity | only once, germinated ≤ sown, chronological dates, duration consistent with dates, temperatures/humidity within limits |
| 4 Production | `POST /api/operations/lots/{id}/transfer`, `/treatment`, `/loss` | origin/destination, greenhouse/chamber, quantities, treatment/product/dose/date, losses and reasons | no moving more than unreserved stock, quality reinspection after transfer/intervention/loss, no same-location transfer |
| 5 Greffage | `POST /api/operations/lots/{id}/graft` | scion lot, rootstock lot and variety, graft date, quantity used/successful/lost, site/location | distinct parents, both stocks exist, quantities ≤ available, no premature date, creates child lot with genealogy |
| 6 Contrôle qualité | `POST /api/operations/lots/{id}/quality` | inspector JWT, inspection date, sanitary condition, homogeneity, inspected and commercial quantities | approve only if `SAIN` + `HOMOGENE`; approved ≤ inspected ≤ in-stock, cannot change with reservations |
| 7 Préparation des commandes | `POST /api/operations/lots/{id}/preparation` | client, order reference, site/location, reserved quantity, trays, pallets | quality release mandatory, available stock and commercial quantity checked, duplicate client/order rejected |
| 8 Livraison | `POST /api/operations/lots/{id}/delivery` | date, transporter, vehicle, note, delivered quantity, customer recipient, explicit receipt confirmation | preparation mandatory, not more than remaining reservation, sufficient stock, quality conforming, receipt confirmed |

Additional routes: quarantine `return`, administrative non-destructive `correction` note, admin-approved `activate-history`, QR, audit/integrity, and lot lists. `correction` is **a note**; it does not reverse or recompute stock (financial-grade corrections still need a separate approval/reversal workflow).

## 4. Common failure cases now explicitly handled

- **401**: bearer token missing/invalid; **403**: wrong role, wrong site or another user's replay key.
- **404**: missing production/seed lot or historical code.
- **409**: duplicate supplier lot, duplicate activation, reused idempotency key or duplicate order, concurrent revision conflict.
- **422**: malformed request fields; negative/zero quantities; invalid dates or environment measurements; missing rootstock or impossible grafting; transfer from/to same place; shipping blocked lots; customer receipt not confirmed; losses exceeding available stock; delivery before sowing; returning items before delivery; nonconforming sanitary/homogeneity with approval.
- **503**: Atlas unavailable or configured source workbook unavailable.

These cover important cases, **not literally every possible failure**. Production rollout requires more tests with Royal Plants, explicit cancellation/reversal workflows, secure deployment, independent backups and monitoring.

## 5. UI changes

- `frontend/src/App.jsx`: fixes login error display, adds historical grafting records, count, a third source card and a new grafting column in the registry.
- `frontend/src/OperationalWorkspace.jsx`: corresponding French form fields for trays/substrate, germination dates/duration, intervention type/product/dose, grafting date, sanitary/homogeneity inspection, and customer receipt.
- `frontend/src/style.css`: refined responsive stats/source layout while preserving the existing green/forest visual identity and animated CSS **3D seedling tray**. No Three.js dependency is needed for the pilot.

## 6. Run locally (Windows PowerShell)

1. Extract this updated ZIP into **a new folder**, so you can revert to your old phase2 project if needed. Copy the three **unchanged** `.xlsx` files into `data/`. No data files or `.env` are inside the ZIP.
2. Make `backend/.env` from `backend/.env.example`. Configure your NEW rotated private MongoDB password, JWT secret, admin email and admin password. The URI must be plain text: `mongodb+srv://...mongodb.net/` — **no** backslash before `.` or `:`. Likewise, use `FRONTEND_PUBLIC_URL=http://127.0.0.1:5173`, not a Markdown link.
3. In `backend`: `py -m venv .venv`, `./.venv/Scripts/python.exe -m pip install -r requirements.txt` (PowerShell format below), then `./.venv/Scripts/python.exe -m app.bootstrap_admin` (only if the admin does not exist).
4. If the existing account has a different password than your updated `.env`: `./.venv/Scripts/python.exe -m app.admin_tools --reset-admin-password --confirm` (explicit change only).
5. Remove `ADMIN_PASSWORD` from `.env` after bootstrap/reset. Start backend: `./.venv/Scripts/python.exe -m uvicorn app.main:app --reload`. Navigate to `http://127.0.0.1:8000/docs`.
6. In `frontend`: `npm install` then `npm run dev` and open `http://127.0.0.1:5173`.

**Recommended commands with Windows separators**:

```powershell
# terminal 1 (from backend/)
Copy-Item .env.example .env   # first run only; don't overwrite an existing .env
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.bootstrap_admin
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload

# terminal 2 (from frontend/)
npm install
npm run dev
```

To test POST login in Swagger, open `/docs` and submit **JSON**:

```json
{"email":"admin@example.test","password":"<your private password>"}
```

After successful bootstrap, do not confuse a **JWT** access token with your password. 401 on protected historical routes without a bearer token is expected. 422 on a malformed login body shows `errors[]` with which field failed. 401 with a correctly formatted body typically means no such account or incorrect password.

## 7. Optional three-file historical import for future deployment

From `backend/`, after preview and explicit review:

```powershell
.\.venv\Scripts\python.exe -m etl.cli analyze --production "..\data\Production_franc_valid-3.xlsx" --delivery "..\data\LivraisonC25_Clean-walid.xlsx" --grafting "..\data\Production_Greffee_Final_corrected-1.xlsx" --out etl_output

# Only if you intentionally want read-only copies in Atlas:
.\.venv\Scripts\python.exe -m etl.cli import --production "..\data\Production_franc_valid-3.xlsx" --delivery "..\data\LivraisonC25_Clean-walid.xlsx" --grafting "..\data\Production_Greffee_Final_corrected-1.xlsx" --out etl_output --confirm-import
```

Set `HISTORY_MODE=atlas` only after historical collections are populated. Re-imports upsert by source-file fingerprint and row; differing file versions are separate snapshots and may need version filtering in future. **This import never modifies original Excel files and never creates fake Blockchain certificates.**

## 8. Verification status and remaining commitments

Verified without private services: real three-file matching and example lot `13877`, local API authentication logic (200/401/422 test), Python compilation, synthetic grafting tests, React JSX parsing. Not yet verified: actual Atlas transaction workflow, npm/Vite full production build (package registry unavailable), rootstock and quality end-to-end operational tests on a live Atlas cluster, production deployment.

**Still planned**: Hyperledger Fabric live chaincode and confirmation worker, event receipt verification, NLP extraction of French descriptions with human confirmation, RAG with scoped retrieval and citations, full offline sync, robust multi-site organization and hardening. None of these are falsely represented as implemented today.
