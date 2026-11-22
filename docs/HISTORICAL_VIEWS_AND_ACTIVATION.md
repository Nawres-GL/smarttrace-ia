# Vue générale, Registre des lots and optional historical activation

## 1. What was wrong

The backend (`backend/app/history.py`) already offered filters through `GET /api/historique/filters` and parameters on `GET /api/historique/lots`. The most recently provided `frontend/src/App.jsx` only sent `search`, `limit` and `offset`. The UI exposed a hard-coded LOT 13766 animation and "Voir l'exemple 13766", making it appear to be a preferred live lot. It was not.

## 2. What this kit changes

- Adds visible selectors to **both** Vue générale and Registre des lots: Campaign -> Species -> Article/Variety.
- Keeps free text search by lot number/reference/article/variety and reset/pagination.
- Selectors cascade: changing the campaign clears species and article; changing species clears article.
- `GET /api/historique/filters` supplies the options; `GET /api/historique/lots` supplies paginated lot cards. Search is server-side. Selection does **not** modify Excel.
- Historical Vue générale counters use the same filters through `GET /api/historique/overview`. This preserves the meaning of a filtered dashboard.
- The dropdown now offers **both** article and variety labels, even when an article exists.
- Replaces the hard-coded 13766 banner with a generic historical callout and generic matching example using `XXXXX`.
- Makes the admin-only historical activation form under **Production active** collapsible and explicitly optional.

**Scope:** These filters apply to **historical Excel lots**. They do not silently filter production *active* MongoDB lots, RAG data or NLP drafts. We can implement shared filter state across those separate domains later, once the business semantics are defined.

## 3. Important: what 'LIÉ' means

`LOT_LIE` in `app/history.py` means a candidate matching **five-digit code** exists in the production Excel and delivery Excel indexes. It does **not** mean confirmed physical genealogy between plants, grafted production, and delivery, and it is NOT Blockchain certification. The application must continue to show mismatches/warnings.

The previous `LOT 13766 • LIÉ` inside the decorative PlantScene was a fixed string—not calculated from MongoDB, not a special or privileged lot, and not chosen by the current filters. It has been replaced with neutral text.

## 4. Why keep 'Reprendre un lot historique Excel'?

The Excel workbooks contain historical records. They do **not** prove that physical plants are still in stock.

Example:
- Historical Excel `RO-13766/25` may mention production volumes, but those are historical numbers.
- An administrator physically counts 850 surviving plants at a real, authorized site/location.
- The admin chooses the known five-digit code and **exact full Excel reference**, enters the counted balance, location, verification date and traceable note.
- `POST /api/operations/activate-history` checks that reference exists in production/grafting Excel, rejects a duplicate activation, enforces admin+site, then creates a **new** operational MongoDB lot with `plantsInStock=850`.
- The event is `OUVERTURE_HISTORIQUE`, recording this verification point; previous planting/transfers/deliveries are not fabricated. The event may later be hashed and anchored to Fabric.

If the lot no longer has verified physical stock and you only need to analyze old data, **do not activate it**. Use Registre des lots or RAG instead.

Why the fields?

| Field | Reason |
|---|---|
| `Code à 5 chiffres` | Candidate key used to find matching historical rows. Not enough by itself to establish a physical lot. |
| `Référence Excel complète` | Selects the specific historical production identity (`RO-...`/`GRO-...`) to avoid ambiguous 5-digit matches. |
| `Site` | Sets the authorized operational location and access scope. |
| `Stock compté` | **Measured physical starting balance**; never copy historic Excel totals automatically. |
| `Emplacement` | Specifies the current location for later movement and loss checks. |
| `Date vérification` | When the count was checked. |
| `Justificatif du comptage` | Human accountability for the stock baseline. |
| `Activer le suivi` | Creates a new live record after validation—not a retroactive history import. |

## 5. API routes and functions

| File/function | Purpose |
|---|---|
| `backend/app/history.py:load_historical()` | Loads all three original Excel workbooks in read-only mode, or existing historical Atlas mode. |
| `history.indexes()` | Creates lookup maps keyed by the five-digit code. |
| `history.summarize()` | Builds one lot-code summary with campaign, species, articles, production/grafting/delivery row counts, mismatch warnings. |
| `history.catalogue()` | One summarized item per distinct lot code. |
| `history.filtered_catalogue()` | Applies combined campaign/species/article/text constraints before paging. |
| `history.filters()` | Returns dynamic campaign/species/article choices to React, plus unknown-campaign count. |
| `history.list_lots()` | Applies filters and returns `total/items/limit/offset`; does not load everything into the browser. |
| `history.overview()` | Calculates dashboard counters within selected filters (new optional arguments). |
| `history.detail()` | Shows source rows and warnings for one five-digit lot code. |
| `frontend/src/LotHistoryFilters.jsx:LotHistoryFilters()` | Three drop-downs; reloads options after campaign/species changes; displays fetching/errors. |
| `App.jsx:updateHistoryFilter()` | Clears lower-level selections and resets pagination. |
| `App.jsx:resetHistoryFilters()` | Restores all categories and text search. |
| `App.jsx:openLot()` | Retrieves one complete historical dossier when a registry row is clicked. |
| `OperationalWorkspace.jsx:submitLegacy()` | Sends manually verified current stock to the admin-only activation endpoint. |
| `backend/app/operations.py:activate_history()` | Authoritative stock-baseline creation; transaction and event. This kit does not modify it. |

## 6. Practical acceptance checks

1. With admin login, choose `C25` on Vue générale. Both counters and table should change. Compare `total` and `scoped_lots` conceptually; `production_rows` is *rows*, `scoped_lots` is *distinct 5-digit codes*.
2. Choose `TOMATE` (or the exact species label returned by the server); Article/Variety options must be narrowed to that species.
3. Change campaign to `C24`; species/article must reset.
4. Search by 5-digit code while filters are active. Clear all using `Tout afficher` or `Effacer les filtres`.
5. Check the same filter results on Vue générale and Registre des lots.
6. Open one historic lot and verify provenance warnings; **no Fabric proof** should appear as verified.
7. With a non-admin account, historical routes should remain forbidden; do not expose Excel history by bypassing the UI.
8. In Production active as admin, confirm the historical activation panel is collapsed by default and manual stock counting is still required.

Potential future optimization: cache `catalogue()` by source file modification time, or use materialized indexed historical collections, if filtering several thousand source rows becomes too slow. Do not optimize until profiling shows latency issues.
