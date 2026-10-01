-- ============================================================================
-- SQL Server Security & Permissions Script
-- Creates dedicated Read-Only user for the AI Chatbot application
-- Enforces Principle of Least Privilege: SELECT only on approved tables/views
-- ============================================================================

USE WarehouseDB;
GO

-- 1. Create SQL Login if not exists
IF NOT EXISTS (SELECT * FROM sys.server_principals WHERE name = 'wms_chatbot_readonly')
BEGIN
    CREATE LOGIN wms_chatbot_readonly WITH PASSWORD = 'ChangeThisStrongPassword123!', CHECK_POLICY = ON;
END
GO

-- 2. Create Database User
IF NOT EXISTS (SELECT * FROM sys.database_principals WHERE name = 'wms_chatbot_readonly')
BEGIN
    CREATE USER wms_chatbot_readonly FOR LOGIN wms_chatbot_readonly;
END
GO

-- 3. Grant Explicit SELECT-only permissions on approved tables and views
GRANT SELECT ON dbo.ZWMS_INVENTORY TO wms_chatbot_readonly;
GRANT SELECT ON dbo.ZWMS_BIN_MASTER TO wms_chatbot_readonly;
GRANT SELECT ON dbo.ZWMS_MATERIAL_MASTER TO wms_chatbot_readonly;
GRANT SELECT ON dbo.vw_WMS_InventoryEnriched TO wms_chatbot_readonly;
GO

-- 4. Explicitly DENY all DDL and DML operations
DENY INSERT, UPDATE, DELETE, ALTER, DROP, EXECUTE TO wms_chatbot_readonly;
GO
