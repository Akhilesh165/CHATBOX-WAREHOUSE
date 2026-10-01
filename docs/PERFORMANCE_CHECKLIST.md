# Production Performance Checklist

| # | Performance Optimization | Implementation Mechanism | Status |
|---|---|---|:---:|
| 1 | **Database Indexing** | Nonclustered indexes created on high-frequency join and filter columns (`Material`, `BinNo`, `Plant`, `StorageLocation`, `MaterialCode`, `BinLocation`) with covering `INCLUDE` clauses. | Verified |
| 2 | **Connection Pooling** | SQLAlchemy connection pool (`pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`, `pool_recycle=1800`) avoids connection establishment overhead. | Verified |
| 3 | **Fast Executemany / Chunking** | Excel data import utilizes chunked inserts (`chunksize=2000`) and pyodbc `fast_executemany=True` for bulk loading high volume records in seconds. | Verified |
| 4 | **No Unbounded SELECT \*** | LLM system prompt enforces explicit column projections, aggregates, and `TOP N` bounds. | Verified |
| 5 | **Row Limit Enforcer** | API truncates output results at 1,000 rows max and sends up to 50 rows for chart rendering to keep payload sizes lean and UI responsive. | Verified |
| 6 | **Async LLM Dispatches** | `httpx.AsyncClient` with non-blocking async calls for LLM SQL and answer generation. | Verified |
| 7 | **Latency Observability** | Millisecond breakdown tracking `llm_ms`, `sql_ms`, and total `execution_ms` returned in every response for performance monitoring. | Verified |
| 8 | **1-Retry Error Reflection** | Automatic 1-retry with validator feedback minimizes failed interactions and eliminates manual user retries for edge syntax issues. | Verified |
