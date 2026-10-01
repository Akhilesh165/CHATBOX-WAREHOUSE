# Project Manifest

## Data Mapping
- Inventory: `Bin Invrntory.xlsx` / `Sheet1` -> `dbo.ZWMS_INVENTORY` (35,419 rows, 18 columns)
- Bins: `WMS Bins Data.xlsx` / `Bin Master` -> `dbo.ZWMS_BIN_MASTER` (33,129 rows, 15 columns)
- Materials: `WMS Bins Data.xlsx` / `Material Master` -> `dbo.ZWMS_MATERIAL_MASTER` (27,829 rows, 23 columns)
- Ignored: `WMS Bins Data.xlsx` / `Inventory` (36,529 rows - intentionally ignored)

## Source Columns Specification
### 1. Inventory (`dbo.ZWMS_INVENTORY`):
- `Id`, `FileName`, `Material`, `Plant`, `StorageLocation`, `Batch`, `MaterialDescription`, `UnrestrictedQty`, `UnrestrictedQty2`, `BaseUnitOfMeasure`, `Mrp`, `FullyVestedOn`, `ChangedAt`, `BinNo`, `INSERT_BY`, `INSERT_TIMESTAMP`, `UPDATE_BY`, `UPDATE_TIMESTAMP`

### 2. Bin Master (`dbo.ZWMS_BIN_MASTER`):
- `Id`, `Plant`, `BinLocation`, `MainCriterion`, `StorageLocation`, `PalletType`, `Box`, `Owner`, `Volume`, `VolumeUnit`, `Length`, `Width`, `Height`, `CreatedDate`, `CreatedBy`

### 3. Material Master (`dbo.ZWMS_MATERIAL_MASTER`):
- `Id`, `MaterialCode`, `MaterialDescription`, `Volume`, `VUom`, `GrossWeight`, `Division`, `DivisionDescription`, `Kslot`, `BinUom`, `InsertBY`, `CreatedDateTime`, `NetWeight`, `EanNo`, `Hierarchy`, `MaterialGroup`, `CaseLot`, `Length`, `Width`, `Height`, `CartoonGrossWeight`, `CartoonVolume`, `UpdatedDateTime`

## Stack
- Frontend: Next.js + React + TypeScript + Recharts + Tailwind CSS + Lucide Icons
- Backend: Python + FastAPI + SQLGlot AST validator + SQLAlchemy + pyodbc
- DB: SQL Server (with read-only least privilege user)
- Import: pandas + openpyxl
