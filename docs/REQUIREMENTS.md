# Complete Functional & Technical Requirements

## 1. Goal
Build a warehouse inventory AI chatbot that lets an employee/customer ask natural-language questions about inventory, bins, materials, plants, storage locations, batches, quantities, and related master data. The answer must be grounded in SQL data.

## 2. Data source contract
### Inventory source
`Bin Invrntory.xlsx` / `Sheet1` is authoritative for inventory rows.
Columns: Id, FileName, Material, Plant, StorageLocation, Batch, MaterialDescription, UnrestrictedQty, UnrestrictedQty2, BaseUnitOfMeasure, Mrp, FullyVestedOn, ChangedAt, BinNo, INSERT_BY, INSERT_TIMESTAMP, UPDATE_BY, UPDATE_TIMESTAMP.

### Bin source
`WMS Bins Data.xlsx` / `Bin Master` only.
Columns: Id, Plant, BinLocation, MainCriterion, StorageLocation, PalletType, Box, Owner, Volume, VolumeUnit, Length, Width, Height, CreatedDate, CreatedBy.

### Material source
`WMS Bins Data.xlsx` / `Material Master` only.
Columns: Id, MaterialCode, MaterialDescription, Volume, VUom, GrossWeight, Division, DivisionDescription, Kslot, BinUom, InsertBY, CreatedDateTime, NetWeight, EanNo, Hierarchy, MaterialGroup, CaseLot, Length, Width, Height, CartoonGrossWeight, CartoonVolume, UpdatedDateTime.

The `Inventory` sheet inside the second workbook MUST NOT be imported or used as a source of truth.

## 3. User capabilities
The chatbot must understand:
- totals and counts
- top/bottom N
- material lookup
- material description lookup
- quantity by material/bin/plant/storage location/batch
- available/unrestricted/blocked/quality concepts if corresponding columns exist
- stock percentages and distributions
- comparisons between locations/plants/materials
- bin details and bin occupancy/volume where the available fields support it
- material dimensions/weight/master-data attributes
- date-based queries using FullyVestedOn/ChangedAt where meaningful
- follow-up questions that refer to the previous result
- common spelling mistakes and informal phrasing

## 4. Natural-language examples
- What is the total inventory?
- Show top 20 materials by unrestricted quantity.
- Which material has the highest stock?
- Show inventory by plant.
- Show inventory by storage location.
- How much of material ABC is in each bin?
- Show all bins for material ABC.
- Give me the details of bin A01.
- What is the material group of material ABC?
- Compare inventory between plant 1000 and 2000.
- Show the percentage contribution of the top 10 materials.
- Show the latest changed inventory records.
- What is the volume and weight of material ABC?

## 5. Query understanding
Pipeline:
1. normalize typo/informal language
2. identify entities and filters
3. resolve follow-up references from conversation context
4. classify query intent
5. select tables/columns
6. generate SQL
7. validate SQL
8. execute SQL
9. validate/format result
10. decide chart type
11. generate grounded answer

## 6. LLM rules
- LLM is not the source of truth.
- SQL Server is the source of truth.
- Never let the LLM access credentials.
- Never execute arbitrary model output without validation.
- The model must use only the supplied schema.
- The model must return structured output for SQL and chart metadata.
- Temperature should be 0 or low for SQL generation.

## 7. SQL safety
Mandatory controls:
- read-only DB account
- SQLGlot AST validation
- table allowlist
- column/schema allowlist
- one statement only
- block DDL/DML/procedures/comments
- max result rows
- query timeout
- server-side connection timeout
- audit logging
- never log secrets

## 8. Answer correctness
Every answer must be generated from the returned SQL rows. If SQL returns no rows, do not hallucinate. If SQL generation or execution fails, show a useful retry/error message and log the technical error server-side.

## 9. Charts
Chart only when the question is analytical or comparative and the result has suitable dimensions/measures.
- bar: top N, comparisons, category quantities
- line: trends over time
- pie: small category distribution where appropriate
- table: detailed row-level results
Do not chart a single scalar answer unless it improves comprehension.

## 10. Frontend requirements
- clean warehouse dashboard/chat UI
- chat history
- user question and assistant answer bubbles
- streaming/loading indicator if supported
- result table with pagination
- chart area
- copy answer / copy SQL controls, subject to security policy
- feedback buttons
- error state
- empty state
- responsive desktop/mobile layout
- optional export CSV
- optional SQL visibility for admin/debug users only

## 11. API requirements
POST `/api/chat` accepts `{message, conversation_id}` and returns `{answer, sql, rows, chart, warnings, execution_ms}`.
GET `/health` returns service status.
Production additions: authentication, rate limits, request IDs, structured logs, metrics.

## 12. Performance requirements
- DB connection pooling
- indexes on Material, BinNo, Plant/StorageLocation
- avoid SELECT * in generated SQL
- cap result rows
- cache schema metadata
- optional short-lived query-result cache for repeated read-only queries
- parallel chart formatting only after query result is available
- track LLM latency and SQL latency separately

## 13. Reliability
If SQL generation fails: retry once with a stricter prompt containing the validation error. If validation fails twice: ask the model for a corrected SQL query or return a clear message. If database fails: do not fabricate an answer.

## 14. Observability
Log: request ID, user ID if authorized, normalized intent, generated SQL hash, query duration, row count, LLM duration, error category. Do not log API keys, DB passwords, or sensitive user data.

## 15. Acceptance criteria
A build is accepted when:
- inventory comes only from first workbook
- Bin Master and Material Master come only from second workbook
- duplicate second-workbook Inventory is ignored
- natural-language questions produce valid SQL
- invalid SQL is rejected
- answers match SQL results
- charts use the same SQL result data
- follow-up questions preserve context
- typos are handled reasonably
- no hallucinated quantities are returned
- database credentials are never sent to the LLM
- common failure modes return user-friendly messages
