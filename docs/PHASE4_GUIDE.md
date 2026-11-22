# Royal Plants SmartTrace — Phase 4

**Interface language:** French. **Technical notes:** English. **Scope:** Campaigns, taxonomy-first lot explorer, staff accounts, site administration, and contextual user help. This builds on Phase 3; it does not implement Fabric consensus, NLP or offline sync.

## 1. What changed (and what did not)

The original **three Excel files are never modified**. Historical production, grafted production and deliveries remain joined **only by the shared five-digit lot number**. Other columns are used only to display attributes, filter the catalogue or signal inconsistencies; they are **not join conditions**.

| File | New or changed | Why |
|---|---|---|
| `backend/app/campaigns.py` | **NEW** | Pure date → campaign conversion; provenance rules and campaign boundaries |
| `backend/app/history.py` | UPDATED | Adds `/filters`, campaign/species/article/lot filters and stable hierarchical categorization; resolves capitalization differences using the production source first |
| `backend/app/auth.py` | UPDATED | Staff creation with one-time temporary password, forced change, listing, role/site/active status updates, logout-on-password-change tokens |
| `backend/app/main.py` | UPDATED | Separate species/article/variety for new seed lots, campaign from sowing date, MongoDB staff-access audit index, PATCH in CORS |
| `backend/app/operations.py` | UPDATED | Operational lot projection includes species/article/campaign; grafts and returns inherit taxonomy, operational list supports limit/offset |
| `frontend/src/HistoricalRegistry.jsx` | **NEW** | Visible unfiltered lots, campaign → species → article/variety → lot, grouped lot cards and paging |
| `frontend/src/EmployeeAdmin.jsx` | **NEW** | Admin creates employee accounts/sites, assigns role and site permissions, views/disables accounts |
| `frontend/src/AccountPassword.jsx` | **NEW** | Employees change provisional passwords at first login; existing users change personal passwords |
| `frontend/src/PageGuide.jsx` | **NEW** | “Why this page exists / how to use it” on each page |
| `frontend/src/phase4.css` | **NEW** | Professional, responsive card layout and guides; existing CSS 3D seedling scene preserved |
| `frontend/src/App.jsx` | UPDATED | Integrates new pages and role-based navigation; replaces former flat historical lot table |
| `frontend/src/OperationalWorkspace.jsx` | UPDATED | Groups operational lots by species/article/campaign, adds distinct seed fields, operation-specific instructions, read-only behavior for nonwriters |
| `backend/tests/test_campaigns.py` | **NEW** | Boundary, provenance, conflicting dates, normalization and filtering regression tests |
| `docs/PHASE4_GUIDE.md` | **NEW** | This manual |
| `README.md` | UPDATED | Phase 4 quick-start and documentation entry |

No `.env` with real passwords is bundled, and the original `.env.example` remains a safe template.

## 2. Campagne: business meaning

Royal Plants defines a campaign from **October 1 of the previous calendar year through September 30 of the named year**, both inclusive.

| Date | Campaign |
|---|---|
| 2024-09-30 | C24 |
| 2024-10-01 | **C25** |
| 2025-04-29 | **C25** |
| 2025-09-30 | **C25** |
| 2025-10-01 | **C26** |

`campaign_for_date()` in `campaigns.py` performs that calculation; `campaign_bounds()` describes a chosen campaign. The literal `RO-xxxxx/25` **does not determine** the agricultural campaign.

For a historical *lot*, the date source is chosen in order:
1. **production sowing date** (`Date semis`), preferred;
2. production germination exit date (`Date Sortie`) if sowing is unavailable;
3. grafted-production **validation date** (`Validé Le`) if no franc-production date exists (this is not asserted to be the physical grafting date);
4. delivery-document date (`Date Effet`) for delivery-only lots (this is not asserted to be proof of physical customer receipt).

If date evidence at the same priority points to more than one campaign, the result is **indeterminate** rather than arbitrary. The response includes `campaign_source` for transparency. A lot's production campaign can differ from the campaign of a **later delivery**; the delivery itself retains its original date and campaign field. This Phase 4 explorer classifies a **lot by its best available production date**; it is not a delivery-period report.

For newly created lots, the campaign comes from the sowing date. A grafted child inherits its source lot's campaign. Existing operational records without a usable date may show `Campagne ?` rather than receiving invented dates.

## 3. Pages: why they exist and how employees use them

### Connexion
Only previously registered employees can log in. The administrator creates their accounts through **Collaborateurs**. There is deliberately no public open sign-up. New employees receive a one-time temporary password and must replace it at first login. Credentials never belong in source code or Excel files.

### Vue générale (admin)
**Purpose:** see historical workload at a glance and enter the historical registry. **How:** review the dashboards; use *Explorer les lots* to open a fully populated, grouped catalogue. Figures refer to historical records, not the entirety of new Atlas operations.

### Registre des lots (admin)
**Purpose:** find historical evidence for a lot without touching the Excel originals.
**How:** the initial list appears without filters, grouped `Espèce → Article/Variété → lots` and paginated. Choose **Campagne** first, then **Espèce**, then **Article/Variété**, and optionally type a lot code or full reference. Click a card to inspect the lot dossier and warnings. C25 covers 2024-10-01 through 2025-09-30. Reset filters at any time.

**Data provenance:** source priority for *categorization* is production > grafted production > delivery. Capitalization differences such as `AUBERGINE` / `Aubergine` are normalized. This categorization does **not** change the lot matching rule: it remains the five-digit code only. An article mismatch still generates a warning in the lot dossier.

### Production active (roles: admin, production, others read-only)
**Purpose:** keep current production stock and trace all agricultural interventions.
**How for production staff:** (1) receive a supplier seed batch with species, article and variety; (2) sow and create the production lot; (3) register germination and initialize plant stock; (4) apply transfers, interventions, losses and optional grafting; (5) open dossier/QR to view the event timeline. New forms explain each operation's stock effect. The operational lot list is **visible immediately**, and can be filtered by campaign, species, article/variety and code, like the historical list.
**How for other staff:** select and open a lot to inspect stock/history, but no production-write forms appear. The backend independently rejects unauthorized requests.

### Reprendre un lot historique Excel (admin-only section in Production active)
**Purpose:** start live tracking of a historical Excel lot **from a physically verified balance**. **How:** enter the exact full Excel reference, five-digit code, site, counting location and quantity, verification date and justification. We never invent older transfers, deliveries or quality tests. This creates a **new** operational record with an `OUVERTURE_HISTORIQUE` event; the prior Excel source remains read-only and uncertified.

### Contrôle qualité (roles: qualite, admin)
**Purpose:** authorize saleable quantities. **How:** inspect a lot; enter health, homogeneity, approved quantity and inspector decision. Without `CONFORME`, preparation/delivery is blocked. Quality may need revalidation after relevant production interventions.

### Préparation & livraison (roles: logistique, admin)
**Purpose:** bridge production stock with customers. **How:** select conforming lot → reserve plants for customer/order (preparation) → select preparation → enter date, transporter, vehicle, note, delivered quantity and customer receipt. Preparing **reserves**, delivering **subtracts physical stock**. Returns create quarantined child lots, not automatically saleable stock.

### Données sources (admin)
**Purpose:** clarify exactly which workbook supplies each historical fact. **How:** review production franc, grafting and delivery sources. This is not an Excel editing page.

### Traçabilité & blockchain (admin)
**Purpose:** communicate the planned verification architecture. Atlas events receive local hashes and pending-outbox entries, but actual Hyperledger Fabric commits are **not** connected in Phase 4. Never label such events as Fabric-verified.

### Collaborateurs (admin)
**Purpose:** register staff, grant minimum access and maintain the list. **How:** create an employee with name, email, role and site(s); copy the temporary password **once**, deliver it securely; the employee logs in and must set a personal password. Admin can disable accounts, adjust roles and site access, and create sites such as `S02` before assignment. Never share an account across workers.

### Mon compte (all roles)
**Purpose:** self-service password change. **How:** provide current password and a new unique 12+ character password. Tokens issued before the change become invalid and the user must sign in again.

### Assistant NLP (not yet active)
**Purpose:** eventually offer guided French-text entry and RAG. Deliberately shown as **À venir**; no fake AI or Fabric confirmation is presented.

## 4. Role matrix

| Capability | admin | production | qualite | logistique | lecture |
|---|---|---|---|---|---|
| Read own site's operational lots | All sites | Yes | Yes | Yes | Yes |
| Receive seeds and sow | Yes | Yes | No | No | No |
| Germination / transfer / loss / treatment / graft | Yes | Yes | No | No | No |
| Approve quality | Yes | No | Yes | No | No |
| Prepare, deliver, process return | Yes | No | No | Yes | No |
| Read all historical Excel customer/delivery data | Yes | No* | No* | No* | No* |
| Activate historical lot at physical baseline | Yes | No | No | No | No |
| Create sites and manage staff | Yes | No | No | No | No |
| Change own password | Yes | Yes | Yes | Yes | Yes |

\* Historical source rows lack a validated mapping to `siteCode`, so cross-site customer data remains restricted to admins **until appropriate row-level permissions are designed**. The `lecture` account supports read-only **operational** lot access within assigned sites.

The application currently stores **one primary role per employee**. Future production needs may call for a multi-role system or approval workflows. That should be agreed with Royal Plants, not assumed.

## 5. Exact backend endpoints added or changed

**Historical:**
- `GET /api/historique/filters?campaign=C25&species=Aubergine` returns cascaded category options.
- `GET /api/historique/lots?campaign=C25&species=Aubergine&article=A336%20F1&search=13766&limit=24&offset=0` returns a paginated, grouped-sortable list of candidate lot codes.
- `GET /api/historique/lots/13766` remains the complete historical dossier.

**Operational:**
- `POST /api/seed-lots`: new seed lots now distinguish `species`, optional `article`, and `variety` (the form explicitly asks for all three).
- `GET /api/operations/lots?limit=500&offset=0`: paging of operational lots. Frontend loads pages up to 5,000 for this pilot; production deployment should use server-side filtering with bounded pages, not download every record.

**Staff:**
- `POST /api/auth/users` (admin only): register an employee and return a one-time provisional password.
- `GET /api/auth/users` (admin only): list staff with no password hashes.
- `PATCH /api/auth/users/{id}` (admin only): change role, site access or disabled status.
- `POST /api/auth/change-password` (logged-in user): replace password; invalidate old JWTs via `authVersion`.
- `POST /api/sites` (admin only) already existed; it is now available in the admin UI.

Existing Phase 3 endpoints, business rules, audit events and QR generation remain in place.

## 6. Setup — update your existing Phase 3 manually

1. **Stop FastAPI and Vite.** Back up your local Phase 3 code and your private `.env` (not the database credentials anywhere public).
2. Copy the changed/new files exactly to their indicated paths in the list in section 1. **Do not copy our example `.env` over your real one**, and do not put any credential in chat/Git.
3. Keep all three original Excel files unchanged under `data/`.
4. In `backend`, activate your existing `.venv` and install dependencies only if they are missing:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONPATH = '.'
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

5. In another terminal from `frontend`, run `npm install` (if not installed) and `npm run dev`. Open `http://127.0.0.1:5173`.
6. Log in as admin → **Registre des lots**. Confirm the unfiltered listing appears and campaign C25 includes dates from **01/10/2024 to 30/09/2025**. Test species Aubergine → article A336 F1 → lot 13766.
7. Open **Collaborateurs**, create a non-production `lecture` employee with site `S01`. Securely give the temporary password to the employee, test forced password change, and verify that they can **view** operational lots but **cannot write** or see historical customer data.
8. As admin create a second site, grant another user access only to it, and confirm site checks are enforced in the API.
9. Register a **new** supplier seed batch with separate species, article, variety; create a sowing lot dated 2025-10-01 and verify it appears in **C26**, not C25.

**Windows local environment:** running `.venv\Scripts\python.exe -m pytest` requires pytest installed from `requirements-dev.txt`. For quick smoke testing without pytest, verify `/api/health` and `GET /api/historique/filters` in Swagger after authentication.

## 7. Testing and limitations

- Tests include campaign boundaries, source priority, contradictory dates, species capitalization normalization, historical linking, event hashing and other existing regressions.
- Local environment: Python compilation and JSX syntax transpilation were checked. Package registry was unavailable, so **full Vite build and MongoDB-dependent integration tests were not run here**.
- The administrator onboarding and password-change features must be verified against **your own Atlas development database** before use with real employee identities.
- JWTs are in React memory and expire; Phase 4 introduces forced password reset and immediate disabled-account checks, but no MFA, login rate limiting, user invites by email or comprehensive production security operations yet.
- Legacy lots may lack species fields. The UI displays `Non renseignée` rather than creating an invented species; new lots capture the correct taxonomy from reception onward.
- Historical campaign labels may use a fallback document or validation date; the source is shown. Original Excel rows are never backfilled or silently corrected.
- Operational list loads a maximum of 5,000 records in browser memory for this pilot; move to server-driven pagination and filters for real large deployments.
- Fabric event proofs, NLP, RAG, offline sync, production backup/restore and company-wide deployment hardening remain explicit future phases.
