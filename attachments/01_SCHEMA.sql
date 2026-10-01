-- ============================================================================
-- 01_SCHEMA.sql - Warehouse Inventory Database Tables (DDL)
-- ============================================================================

USE WarehouseDB;
GO

-- 1. ZWMS_INVENTORY Table (Source: "Bin Invrntory.xlsx" [Sheet1])
IF OBJECT_ID('dbo.ZWMS_INVENTORY', 'U') IS NOT NULL
    DROP TABLE dbo.ZWMS_INVENTORY;
GO

CREATE TABLE dbo.ZWMS_INVENTORY (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    FileName NVARCHAR(255) NULL,
    Material NVARCHAR(100) NOT NULL,
    Plant NVARCHAR(50) NOT NULL,
    StorageLocation NVARCHAR(50) NOT NULL,
    Batch NVARCHAR(100) NULL,
    MaterialDescription NVARCHAR(500) NULL,
    UnrestrictedQty DECIMAL(18, 3) NOT NULL DEFAULT 0,
    UnrestrictedQty2 DECIMAL(18, 3) NULL DEFAULT 0,
    BaseUnitOfMeasure NVARCHAR(50) NULL,
    Mrp DECIMAL(18, 2) NULL,
    FullyVestedOn DATETIME NULL,
    ChangedAt DATETIME NULL,
    BinNo NVARCHAR(100) NOT NULL,
    INSERT_BY NVARCHAR(100) NULL,
    INSERT_TIMESTAMP DATETIME NULL,
    UPDATE_BY NVARCHAR(100) NULL,
    UPDATE_TIMESTAMP DATETIME NULL
);
GO

-- 2. ZWMS_BIN_MASTER Table (Source: "WMS Bins Data.xlsx" [Bin Master])
IF OBJECT_ID('dbo.ZWMS_BIN_MASTER', 'U') IS NOT NULL
    DROP TABLE dbo.ZWMS_BIN_MASTER;
GO

CREATE TABLE dbo.ZWMS_BIN_MASTER (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    Plant NVARCHAR(50) NOT NULL,
    BinLocation NVARCHAR(100) NOT NULL,
    MainCriterion NVARCHAR(100) NULL,
    StorageLocation NVARCHAR(50) NOT NULL,
    PalletType NVARCHAR(100) NULL,
    Box NVARCHAR(100) NULL,
    Owner NVARCHAR(100) NULL,
    Volume DECIMAL(18, 4) NULL,
    VolumeUnit NVARCHAR(50) NULL,
    Length DECIMAL(18, 4) NULL,
    Width DECIMAL(18, 4) NULL,
    Height DECIMAL(18, 4) NULL,
    CreatedDate DATETIME NULL,
    CreatedBy NVARCHAR(100) NULL
);
GO

-- 3. ZWMS_MATERIAL_MASTER Table (Source: "WMS Bins Data.xlsx" [Material Master])
IF OBJECT_ID('dbo.ZWMS_MATERIAL_MASTER', 'U') IS NOT NULL
    DROP TABLE dbo.ZWMS_MATERIAL_MASTER;
GO

CREATE TABLE dbo.ZWMS_MATERIAL_MASTER (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    MaterialCode NVARCHAR(100) NOT NULL,
    MaterialDescription NVARCHAR(500) NULL,
    Volume DECIMAL(18, 4) NULL,
    VUom NVARCHAR(50) NULL,
    GrossWeight DECIMAL(18, 4) NULL,
    Division NVARCHAR(100) NULL,
    DivisionDescription NVARCHAR(255) NULL,
    Kslot NVARCHAR(100) NULL,
    BinUom NVARCHAR(50) NULL,
    InsertBY NVARCHAR(100) NULL,
    CreatedDateTime DATETIME NULL,
    NetWeight DECIMAL(18, 4) NULL,
    EanNo NVARCHAR(100) NULL,
    Hierarchy NVARCHAR(255) NULL,
    MaterialGroup NVARCHAR(100) NULL,
    CaseLot DECIMAL(18, 2) NULL,
    Length DECIMAL(18, 4) NULL,
    Width DECIMAL(18, 4) NULL,
    Height DECIMAL(18, 4) NULL,
    CartoonGrossWeight DECIMAL(18, 4) NULL,
    CartoonVolume DECIMAL(18, 4) NULL,
    UpdatedDateTime DATETIME NULL
);
GO
