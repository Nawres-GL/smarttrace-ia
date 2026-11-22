# Historical Excel linking (read-only)

The app links `Production_franc_valid-3.xlsx` and `LivraisonC25_Clean-walid.xlsx` **solely using the five-digit lot number**.

- Production field: `LOT`, e.g. `RO-13766/25` → `13766`.
- Delivery field: `N° Lot`, e.g. `13766` → `13766`.
- Article, year, quantity and client **do not form part of the join key**. Article mismatches become warnings, not rejected matches.
- All lines (including partial deliveries, returns, repeated records and distinct full lot references with the same five-digit code) are retained; no arbitrary reduction to one delivery record.
- Both original Excel files remain intact and read-only.
- `Date Effet` is a date on a delivery document; do not call it confirmed physical delivery time.
- Historical data are source snapshots, not Blockchain-certified events.

Run FastAPI with `HISTORY_MODE=excel` for direct local read-only access. No MongoDB is required for this part.

Optional commands from `backend/`:

```
python -m etl.cli analyze --production ../data/Production_franc_valid-3.xlsx --delivery ../data/LivraisonC25_Clean-walid.xlsx --out etl_output
python -m etl.cli import --production ../data/Production_franc_valid-3.xlsx --delivery ../data/LivraisonC25_Clean-walid.xlsx --out etl_output --confirm-import
```

`analyze` generates separate preview outputs in `etl_output/` (not Excel edits). `import` additionally creates historical source-snapshot records in a development-only MongoDB Atlas DB. Never set `HISTORY_MODE=atlas` until the source rows are imported. No Blockchain validation is performed during import.
