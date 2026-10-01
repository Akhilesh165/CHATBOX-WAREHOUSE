# Single Prompt for an AI Coding Builder

Build a production-ready warehouse inventory AI chatbot.

## Data rules
- Inventory source is `Bin Invrntory.xlsx` only.
- From `WMS Bins Data.xlsx`, use only `Bin Master` and `Material Master`.
- Ignore `WMS Bins Data.xlsx` -> `Inventory` entirely.
- SQL Server is the source of truth after import.

## Stack
Use Next.js/React + TypeScript for frontend and Python FastAPI for backend. Use SQLAlchemy/pyodbc for SQL Server, SQLGlot for SQL validation, Pydantic for API models, pandas/openpyxl for import, and Recharts or Apache ECharts for charts. Reuse established third-party libraries rather than implementing parsers, chart engines, or DB drivers from scratch.

## Required architecture
User -> frontend -> FastAPI -> query normalization/intent/context -> LLM SQL generation -> SQLGlot validation -> read-only SQL Server -> result validator -> answer generator -> chart metadata -> frontend.

## AI requirements
The LLM must:
- understand natural language and common typos
- use only the provided schema
- generate exactly one read-only SELECT/WITH statement
- understand follow-up questions from conversation history
- never invent data
- return structured SQL + chart metadata

## SQL security
Use a read-only DB user. Validate SQL with SQLGlot AST. Allow only approved tables/views and columns. Block INSERT/UPDATE/DELETE/MERGE/DROP/ALTER/TRUNCATE/EXEC/CREATE/GRANT/REVOKE, comments, multiple statements, and unauthorized tables. Add query timeouts and row limits.

## Tables
Create:
- dbo.ZWMS_INVENTORY
- dbo.ZWMS_BIN_MASTER
- dbo.ZWMS_MATERIAL_MASTER
Optional semantic view: dbo.vw_WMS_InventoryEnriched.

## Chart behavior
Return a bar chart for category comparisons/top-N, a line chart for time series, a pie chart for small distributions, and no chart for simple scalar/look-up questions. Chart data must come directly from SQL results.

## UX
Create a polished warehouse chat UI with message history, loading state, markdown answer rendering, result tables, charts, copy answer, optional admin-only SQL view, error state, feedback, and responsive layout.

## Reliability
If SQL generation fails, retry once with the validation error. If execution fails, do not fabricate an answer. Show a friendly error and log technical details server-side.

## Deliverables
Generate:
1. frontend
2. backend
3. database SQL scripts
4. Excel import script
5. environment configuration
6. prompts
7. tests
8. API documentation
9. deployment instructions
10. seed/sample queries
11. security checklist
12. performance checklist

Do not hard-code answers for a small set of questions. The system must dynamically translate new inventory questions into SQL using the schema.
