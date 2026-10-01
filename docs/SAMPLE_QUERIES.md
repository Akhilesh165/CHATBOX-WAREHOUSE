# Sample Natural Language Queries & Expected SQL

| Category | Natural Language Question | Expected SQL Intent / Query | Chart Recommended |
|---|---|---|---|
| **Totals & Aggregate** | "What is the total unrestricted inventory in the warehouse?" | `SELECT SUM(UnrestrictedQty) AS TotalUnrestrictedQty FROM dbo.ZWMS_INVENTORY` | `none` |
| **Top-N Ranking** | "Show top 10 materials by unrestricted quantity" | `SELECT TOP 10 Material, MAX(MaterialDescription) AS Description, SUM(UnrestrictedQty) AS TotalQty FROM dbo.ZWMS_INVENTORY GROUP BY Material ORDER BY TotalQty DESC` | `bar` |
| **Location Breakdown** | "Breakdown of inventory by plant" | `SELECT Plant, SUM(UnrestrictedQty) AS TotalQty FROM dbo.ZWMS_INVENTORY GROUP BY Plant ORDER BY TotalQty DESC` | `bar` |
| **Storage Breakdown** | "Show inventory by storage location for plant 1000" | `SELECT StorageLocation, SUM(UnrestrictedQty) AS TotalQty FROM dbo.ZWMS_INVENTORY WHERE Plant = '1000' GROUP BY StorageLocation ORDER BY TotalQty DESC` | `bar` |
| **Material Lookup** | "Where is material 1000123 stored and what are the batches?" | `SELECT BinNo, StorageLocation, Plant, Batch, UnrestrictedQty FROM dbo.ZWMS_INVENTORY WHERE Material = '1000123' ORDER BY UnrestrictedQty DESC` | `none` |
| **Bin Lookup** | "What items are inside Bin A-01-01?" | `SELECT Material, MaterialDescription, Batch, UnrestrictedQty, BaseUnitOfMeasure FROM dbo.ZWMS_INVENTORY WHERE BinNo = 'A-01-01'` | `none` |
| **Bin Master Details** | "Give me the volume, pallet type, and dimensions of bin A-01-01" | `SELECT BinLocation, Plant, StorageLocation, Volume, VolumeUnit, PalletType, Length, Width, Height FROM dbo.ZWMS_BIN_MASTER WHERE BinLocation = 'A-01-01'` | `none` |
| **Material Master Specs**| "What is the gross weight and division of material 1000123?" | `SELECT MaterialCode, MaterialDescription, GrossWeight, NetWeight, Division, DivisionDescription, MaterialGroup FROM dbo.ZWMS_MATERIAL_MASTER WHERE MaterialCode = '1000123'` | `none` |
| **Comparative Analysis**| "Compare inventory between plant 1000 and plant 2000" | `SELECT Plant, COUNT(DISTINCT Material) AS MaterialCount, SUM(UnrestrictedQty) AS TotalQty FROM dbo.ZWMS_INVENTORY WHERE Plant IN ('1000', '2000') GROUP BY Plant` | `bar` |
| **Percentage Contribution** | "What percentage of total stock does each of the top 5 materials represent?" | `WITH Tot AS (SELECT SUM(UnrestrictedQty) AS GT FROM dbo.ZWMS_INVENTORY), Top5 AS (SELECT TOP 5 Material, SUM(UnrestrictedQty) AS MQty FROM dbo.ZWMS_INVENTORY GROUP BY Material ORDER BY MQty DESC) SELECT Top5.Material, Top5.MQty, CAST(Top5.MQty * 100.0 / Tot.GT AS DECIMAL(5,2)) AS Pct FROM Top5 CROSS JOIN Tot` | `pie` |
| **Time Series / Audit** | "Show recently updated inventory records" | `SELECT TOP 20 Material, MaterialDescription, BinNo, ChangedAt, UPDATE_TIMESTAMP FROM dbo.ZWMS_INVENTORY ORDER BY ChangedAt DESC` | `none` |
