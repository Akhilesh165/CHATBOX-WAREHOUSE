-- ============================================================================
-- Seed & Verification Sample Queries
-- Standard operational inventory questions and their canonical SQL Server queries
-- ============================================================================

USE WarehouseDB;
GO

-- 1. Total unrestricted inventory across the entire warehouse
SELECT 
    COUNT(DISTINCT Material) AS TotalUniqueMaterials,
    COUNT(DISTINCT BinNo) AS TotalActiveBins,
    SUM(UnrestrictedQty) AS TotalUnrestrictedQuantity
FROM dbo.ZWMS_INVENTORY;

-- 2. Top 20 materials by unrestricted quantity
SELECT TOP 20
    Material,
    MAX(MaterialDescription) AS MaterialDescription,
    SUM(UnrestrictedQty) AS TotalQuantity,
    MAX(BaseUnitOfMeasure) AS UOM
FROM dbo.ZWMS_INVENTORY
GROUP BY Material
ORDER BY TotalQuantity DESC;

-- 3. Inventory breakdown by Plant
SELECT 
    Plant,
    COUNT(DISTINCT Material) AS MaterialCount,
    COUNT(DISTINCT BinNo) AS BinCount,
    SUM(UnrestrictedQty) AS TotalQuantity
FROM dbo.ZWMS_INVENTORY
GROUP BY Plant
ORDER BY TotalQuantity DESC;

-- 4. Inventory breakdown by Storage Location
SELECT 
    StorageLocation,
    Plant,
    COUNT(DISTINCT Material) AS MaterialCount,
    SUM(UnrestrictedQty) AS TotalQuantity
FROM dbo.ZWMS_INVENTORY
GROUP BY StorageLocation, Plant
ORDER BY TotalQuantity DESC;

-- 5. Bins for a specific material with plant & batch details
-- Example parameterized check
SELECT 
    BinNo,
    Plant,
    StorageLocation,
    Batch,
    UnrestrictedQty,
    BaseUnitOfMeasure,
    ChangedAt
FROM dbo.ZWMS_INVENTORY
WHERE Material = '1000123' -- replace with target material code
ORDER BY UnrestrictedQty DESC;

-- 6. Bin Details joined with Bin Master
SELECT 
    i.BinNo,
    i.Plant,
    i.StorageLocation,
    COUNT(DISTINCT i.Material) AS MaterialCount,
    SUM(i.UnrestrictedQty) AS CurrentQuantity,
    b.Volume AS BinVolume,
    b.VolumeUnit,
    b.PalletType,
    b.Box
FROM dbo.ZWMS_INVENTORY i
LEFT JOIN dbo.ZWMS_BIN_MASTER b
    ON i.BinNo = b.BinLocation 
    AND i.Plant = b.Plant 
    AND i.StorageLocation = b.StorageLocation
WHERE i.BinNo = 'A-01-01' -- replace with target bin
GROUP BY i.BinNo, i.Plant, i.StorageLocation, b.Volume, b.VolumeUnit, b.PalletType, b.Box;

-- 7. Material master details with inventory sum
SELECT 
    m.MaterialCode,
    m.MaterialDescription,
    m.MaterialGroup,
    m.Division,
    m.DivisionDescription,
    m.GrossWeight,
    m.NetWeight,
    m.Volume,
    m.VUom,
    COALESCE(SUM(i.UnrestrictedQty), 0) AS CurrentStock
FROM dbo.ZWMS_MATERIAL_MASTER m
LEFT JOIN dbo.ZWMS_INVENTORY i
    ON m.MaterialCode = i.Material
WHERE m.MaterialCode = '1000123' -- replace with target material code
GROUP BY m.MaterialCode, m.MaterialDescription, m.MaterialGroup, m.Division, m.DivisionDescription, m.GrossWeight, m.NetWeight, m.Volume, m.VUom;

-- 8. Plant Comparison: Plant 1000 vs Plant 2000
SELECT 
    Plant,
    COUNT(DISTINCT Material) AS DistinctMaterials,
    COUNT(DISTINCT BinNo) AS DistinctBins,
    SUM(UnrestrictedQty) AS TotalQuantity,
    AVG(UnrestrictedQty) AS AvgQuantityPerRecord
FROM dbo.ZWMS_INVENTORY
WHERE Plant IN ('1000', '2000')
GROUP BY Plant;

-- 9. Latest Changed Inventory Records
SELECT TOP 15
    Material,
    MaterialDescription,
    Plant,
    StorageLocation,
    BinNo,
    Batch,
    UnrestrictedQty,
    ChangedAt
FROM dbo.ZWMS_INVENTORY
ORDER BY ChangedAt DESC;

-- 10. Percentage contribution of Top 10 Materials
WITH TotalStock AS (
    SELECT SUM(UnrestrictedQty) AS GrandTotal FROM dbo.ZWMS_INVENTORY
),
MaterialAgg AS (
    SELECT TOP 10
        Material,
        MAX(MaterialDescription) AS MaterialDescription,
        SUM(UnrestrictedQty) AS MaterialTotal
    FROM dbo.ZWMS_INVENTORY
    GROUP BY Material
    ORDER BY MaterialTotal DESC
)
SELECT 
    m.Material,
    m.MaterialDescription,
    m.MaterialTotal,
    CAST(m.MaterialTotal * 100.0 / NULLIF(t.GrandTotal, 0) AS DECIMAL(5, 2)) AS PercentageOfTotal
FROM MaterialAgg m
CROSS JOIN TotalStock t;
