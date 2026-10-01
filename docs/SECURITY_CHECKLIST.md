# Production Security Checklist

| # | Security Control | Implementation Mechanism | Status |
|---|---|---|:---:|
| 1 | **Database Least Privilege** | Read-only SQL Server user (`wms_chatbot_readonly`) with explicit `GRANT SELECT` only on approved tables/views and `DENY` on all DDL/DML. | Verified |
| 2 | **No Credential Exposure** | Database connection strings and LLM API keys are isolated in backend environment variables and NEVER passed to LLM prompts. | Verified |
| 3 | **SQLGlot AST Validation** | Abstract Syntax Tree validation enforces strictly single `SELECT` or `WITH` queries and blocks `Insert`, `Update`, `Delete`, `Drop`, `Alter`, `Exec`, `Truncate`, and `Merge`. | Verified |
| 4 | **Table Allowlisting** | Only `dbo.ZWMS_INVENTORY`, `dbo.ZWMS_BIN_MASTER`, `dbo.ZWMS_MATERIAL_MASTER`, and `dbo.vw_WMS_InventoryEnriched` can be accessed. Access to system tables (`sys.*`, `INFORMATION_SCHEMA.*`) or unknown tables is immediately blocked. | Verified |
| 5 | **Comment & Stacked Query Blocking** | SQL comments (`--`, `/* */`) and semicolon-separated multiple statements are rejected before execution. | Verified |
| 6 | **Output Redaction for Non-Admins** | Raw SQL queries are hidden from end users in API responses unless `is_admin=true` or `DEBUG=True` is explicitly authorized. | Verified |
| 7 | **Execution Timeout** | Queries have strict server-side connection and query execution timeouts (default 30 seconds) to prevent Denial of Service (DoS). | Verified |
| 8 | **Max Result Row Cap** | Output row count is bounded at 1,000 rows max to avoid memory exhaustion. | Verified |
| 9 | **Input Sanitization** | JSON payload validation via Pydantic models with type checking and length boundaries. | Verified |
| 10 | **Audit & Latency Logging** | Requests, execution durations, intent classifications, and user feedback are logged without logging secrets or credentials. | Verified |
