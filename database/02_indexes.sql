-- ============================================================================
-- Performance Indexes for Warehouse Database
-- Optimized for inventory aggregates, joins, searches, and plant/storage filtering
-- ============================================================================

USE WarehouseDB;
GO

-- 1. Indexes on ZWMS_INVENTORY
CREATE NONCLUSTERED INDEX IX_ZWMS_INVENTORY_Material
    ON dbo.ZWMS_INVENTORY (Material)
    INCLUDE (Plant, StorageLocation, UnrestrictedQty, BinNo, Batch);
GO

CREATE NONCLUSTERED INDEX IX_ZWMS_INVENTORY_BinNo
    ON dbo.ZWMS_INVENTORY (BinNo)
    INCLUDE (Material, Plant, StorageLocation, UnrestrictedQty);
GO

CREATE NONCLUSTERED INDEX IX_ZWMS_INVENTORY_Plant_StorageLocation
    ON dbo.ZWMS_INVENTORY (Plant, StorageLocation)
    INCLUDE (Material, UnrestrictedQty, BinNo);
GO

CREATE NONCLUSTERED INDEX IX_ZWMS_INVENTORY_MaterialDescription
    ON dbo.ZWMS_INVENTORY (MaterialDescription);
GO

CREATE NONCLUSTERED INDEX IX_ZWMS_INVENTORY_ChangedAt
    ON dbo.ZWMS_INVENTORY (ChangedAt DESC)
    INCLUDE (Material, Plant, StorageLocation, UnrestrictedQty);
GO

-- 2. Indexes on ZWMS_BIN_MASTER
CREATE NONCLUSTERED INDEX IX_ZWMS_BIN_MASTER_BinLocation
    ON dbo.ZWMS_BIN_MASTER (BinLocation)
    INCLUDE (Plant, StorageLocation, Volume, PalletType, Box);
GO

CREATE NONCLUSTERED INDEX IX_ZWMS_BIN_MASTER_Plant_StorageLocation
    ON dbo.ZWMS_BIN_MASTER (Plant, StorageLocation)
    INCLUDE (BinLocation, Volume, PalletType);
GO

-- 3. Indexes on ZWMS_MATERIAL_MASTER
CREATE NONCLUSTERED INDEX IX_ZWMS_MATERIAL_MASTER_MaterialCode
    ON dbo.ZWMS_MATERIAL_MASTER (MaterialCode)
    INCLUDE (MaterialDescription, MaterialGroup, Division, GrossWeight, NetWeight, Volume);
GO

CREATE NONCLUSTERED INDEX IX_ZWMS_MATERIAL_MASTER_MaterialGroup
    ON dbo.ZWMS_MATERIAL_MASTER (MaterialGroup)
    INCLUDE (MaterialCode, Division);
GO

CREATE NONCLUSTERED INDEX IX_ZWMS_MATERIAL_MASTER_Division
    ON dbo.ZWMS_MATERIAL_MASTER (Division)
    INCLUDE (MaterialCode, MaterialDescription);
GO
