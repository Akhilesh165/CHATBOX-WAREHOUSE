-- ============================================================================
-- Semantic Views for Warehouse Database
-- Provides enriched inventory reporting with bin and material master lookups
-- ============================================================================

USE WarehouseDB;
GO

IF OBJECT_ID('dbo.vw_WMS_InventoryEnriched', 'V') IS NOT NULL
    DROP VIEW dbo.vw_WMS_InventoryEnriched;
GO

CREATE VIEW dbo.vw_WMS_InventoryEnriched
AS
SELECT 
    -- Inventory core fields
    i.Id AS InventoryId,
    i.Material,
    COALESCE(i.MaterialDescription, m.MaterialDescription) AS MaterialDescription,
    i.Plant,
    i.StorageLocation,
    i.Batch,
    i.UnrestrictedQty,
    i.UnrestrictedQty2,
    i.BaseUnitOfMeasure,
    i.Mrp,
    i.FullyVestedOn,
    i.ChangedAt,
    i.BinNo,
    
    -- Material Master enriched fields
    m.Division,
    m.DivisionDescription,
    m.MaterialGroup,
    m.GrossWeight AS MaterialGrossWeight,
    m.NetWeight AS MaterialNetWeight,
    m.Volume AS MaterialVolume,
    m.VUom AS MaterialVolumeUom,
    m.Length AS MaterialLength,
    m.Width AS MaterialWidth,
    m.Height AS MaterialHeight,
    m.CaseLot,
    m.EanNo,
    m.Hierarchy,
    
    -- Bin Master enriched fields
    b.PalletType,
    b.Box AS BinBox,
    b.Owner AS BinOwner,
    b.Volume AS BinVolume,
    b.VolumeUnit AS BinVolumeUnit,
    b.Length AS BinLength,
    b.Width AS BinWidth,
    b.Height AS BinHeight
FROM dbo.ZWMS_INVENTORY i
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m
    ON i.Material = m.MaterialCode
LEFT JOIN dbo.ZWMS_BIN_MASTER b
    ON i.BinNo = b.BinLocation 
    AND i.Plant = b.Plant 
    AND i.StorageLocation = b.StorageLocation;
GO
