# Debugging audit and verification notes

## Scope inspected

This audit is based on the uploaded `CHATBOX-WAREHOUSE-main` project, including the FastAPI backend, deterministic semantic query resolver, SQL validation/result validation layers, prompts, tests, SQLite database, and the supplied Warehouse Chatbot Master Context.

## Findings and changes made

1. **Total warehouse inventory could be vulnerable to scope drift.** The SQL generation path tries the deterministic resolver first, but falls back to an LLM for generic `inventory_summary` intent. A broad total-inventory question must be an all-warehouse aggregate unless the current question explicitly names a plant or asks for a breakdown. Added a guard in `backend/app/llm.py` for explicit global total-inventory wording; it returns a single aggregate query with no plant filter, `GROUP BY`, `TOP`, or `LIMIT`.
2. **Hardcoded plant validation in answer formatting was brittle.** `format_deterministic_answer` previously used a fixed list of plant IDs (and even special-cased year-like values), which can become stale as the database changes. It now checks the returned `Plant` column when available and does not infer that a zero-valued aggregate means no records.
3. **Local SQLite selection depended on the process working directory.** `backend/app/db.py` now resolves `warehouse.db` relative to the project directory, so starting the backend from another working directory does not accidentally skip the included development database.
4. **Result row cap was silent.** `backend/app/main.py` now adds a warning when the configured row cap is reached, making it clear that a list may be incomplete instead of presenting a capped result as complete.
5. **Master context was not available as a named project documentation file.** Added `docs/WAREHOUSE_CHATBOT_MASTER_CONTEXT.md` using the user's supplied context text.
6. **Generated TypeScript cache was unnecessary project noise.** Removed `frontend/tsconfig.tsbuildinfo` and added it to `.gitignore`. Source files, database, Excel source data, dependencies, and tests were retained.

## Database facts verified from the included `warehouse.db`

Direct SQLite queries returned:

- `ZWMS_INVENTORY`: 35,419 rows
- `ZWMS_BIN_MASTER`: 33,129 rows
- `ZWMS_MATERIAL_MASTER`: 27,829 rows
- Inventory rows by plant:
  - Plant 1258: 5,517 rows; `SUM(UnrestrictedQty)` = 498,504
  - Plant 1266: 2,295 rows; `SUM(UnrestrictedQty)` = 206,471
  - Plant 1268: 18,229 rows; `SUM(UnrestrictedQty)` = 1,826,904
  - Plant 7228: 9,378 rows; `SUM(UnrestrictedQty)` = 1,933,031
- All-warehouse `SUM(UnrestrictedQty)` = **4,464,910** in the included database.

These values are from the uploaded SQLite database and are not hardcoded into chatbot responses. They can differ if the database is refreshed.

## Regression coverage added

`backend/tests/test_total_warehouse_inventory_scope.py` checks that:

- “Total warehouse inventory” resolves to an all-warehouse `SUM(UnrestrictedQty)` query.
- The generated query does not add a plant filter, group by plant, or arbitrary `TOP`/`LIMIT`.
- An explicitly requested Plant 1258 remains scoped to Plant 1258.
- A valid aggregate whose value is zero is not automatically converted into a “no matching records” response.

## Verification limitations

- Python syntax compilation and direct SQLite data checks can be run in this environment.
- The full pytest suite could not be collected here because the execution environment lacks required project dependencies, especially `sqlglot` (and the initial test invocation also lacked the expected project import path). Package installation was attempted but network access was unavailable.
- Therefore, the new pytest tests are added but **not claimed as passing** here. Run `pip install -r backend/requirements.txt` in your project environment, then run `python -m pytest backend/tests -q` from the project root.
- The included SQLite database was queried directly; live SQL Server connectivity and frontend/browser behavior were not available for end-to-end verification.

## Known cleanup decisions

- `database/02_views.sql` and `database/03_views.sql` are duplicates, but both are retained because the existing deployment documentation explicitly references `03_views.sql`. Removing it without updating deployment scripts could break setup instructions.
- The Excel workbooks and `warehouse.db` are retained because they are the supplied source data and local database, not disposable build artifacts.
