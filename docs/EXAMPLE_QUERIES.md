# Example Warehouse Inventory Queries

## 1. Totals and Summaries
- **Question:** "What is the total unrestricted inventory in the warehouse?"
  - **SQL:** `SELECT SUM(UnrestrictedQty) AS TotalUnrestrictedQty FROM dbo.ZWMS_INVENTORY`
  - **Chart:** `none`

## 2. Top-N Rankings
- **Question:** "Show top 10 materials by unrestricted quantity"
  - **SQL:** `SELECT TOP 10 Material, MAX(MaterialDescription) AS Description, SUM(UnrestrictedQty) AS TotalQty FROM dbo.ZWMS_INVENTORY GROUP BY Material ORDER BY TotalQty DESC`
  - **Chart:** `bar` (X: `Material`, Y: `TotalQty`)

## 3. Location & Storage Breakdown
- **Question:** "Show inventory breakdown by plant"
  - **SQL:** `SELECT Plant, SUM(UnrestrictedQty) AS TotalQty FROM dbo.ZWMS_INVENTORY GROUP BY Plant ORDER BY TotalQty DESC`
  - **Chart:** `bar` (X: `Plant`, Y: `TotalQty`)

- **Question:** "Show inventory by storage location for plant 1000"
  - **SQL:** `SELECT StorageLocation, SUM(UnrestrictedQty) AS TotalQty FROM dbo.ZWMS_INVENTORY WHERE Plant = '1000' GROUP BY StorageLocation ORDER BY TotalQty DESC`
  - **Chart:** `bar` (X: `StorageLocation`, Y: `TotalQty`)

## 4. Material & Bin Specific Lookups
- **Question:** "Where is material 1000123 stored and what are the batches?"
  - **SQL:** `SELECT BinNo, StorageLocation, Plant, Batch, UnrestrictedQty FROM dbo.ZWMS_INVENTORY WHERE Material = '1000123' ORDER BY UnrestrictedQty DESC`
  - **Chart:** `none`

- **Question:** "What items are inside Bin A-01-01?"
  - **SQL:** `SELECT Material, MaterialDescription, Batch, UnrestrictedQty, BaseUnitOfMeasure FROM dbo.ZWMS_INVENTORY WHERE BinNo = 'A-01-01'`
  - **Chart:** `none`

## 5. Master Data Enriched Inquiries
- **Question:** "Give me the volume, pallet type, and dimensions of bin A-01-01"
  - **SQL:** `SELECT BinLocation, Plant, StorageLocation, Volume, VolumeUnit, PalletType, Length, Width, Height FROM dbo.ZWMS_BIN_MASTER WHERE BinLocation = 'A-01-01'`
  - **Chart:** `none`

- **Question:** "What is the gross weight and division of material 1000123?"
  - **SQL:** `SELECT MaterialCode, MaterialDescription, GrossWeight, NetWeight, Division, DivisionDescription, MaterialGroup FROM dbo.ZWMS_MATERIAL_MASTER WHERE MaterialCode = '1000123'`
  - **Chart:** `none`

## 6. Comparison & Percentage
- **Question:** "Compare inventory between plant 1000 and plant 2000"
  - **SQL:** `SELECT Plant, COUNT(DISTINCT Material) AS MaterialCount, SUM(UnrestrictedQty) AS TotalQty FROM dbo.ZWMS_INVENTORY WHERE Plant IN ('1000', '2000') GROUP BY Plant`
  - **Chart:** `bar` (X: `Plant`, Y: `TotalQty`)
