import pytest
from backend.app.validator import validate_sql

def test_valid_select_queries():
    # Standard SELECT
    q1 = "SELECT TOP 10 Material, SUM(UnrestrictedQty) FROM dbo.ZWMS_INVENTORY GROUP BY Material"
    assert "SELECT" in validate_sql(q1)

    # SELECT with View
    q2 = "SELECT Material, BinNo, Division FROM dbo.vw_WMS_InventoryEnriched WHERE Plant = '1000'"
    assert "vw_WMS_InventoryEnriched" in validate_sql(q2)

    # JOIN between allowed tables
    q3 = """
    SELECT i.Material, i.UnrestrictedQty, b.Volume
    FROM dbo.ZWMS_INVENTORY i
    JOIN dbo.ZWMS_BIN_MASTER b ON i.BinNo = b.BinLocation
    """
    assert "ZWMS_INVENTORY" in validate_sql(q3)

    # CTE query
    q4 = """
    WITH TopStock AS (
        SELECT Material, SUM(UnrestrictedQty) AS Total
        FROM dbo.ZWMS_INVENTORY
        GROUP BY Material
    )
    SELECT * FROM TopStock
    """
    assert "WITH" in validate_sql(q4)

def test_blocks_dml_write_operations():
    with pytest.raises(ValueError, match="is forbidden|is prohibited|Invalid statement"):
        validate_sql("DELETE FROM dbo.ZWMS_INVENTORY WHERE Id = 1")

    with pytest.raises(ValueError, match="is forbidden|is prohibited|Invalid statement"):
        validate_sql("UPDATE dbo.ZWMS_INVENTORY SET UnrestrictedQty = 100")

    with pytest.raises(ValueError, match="is forbidden|is prohibited|Invalid statement"):
        validate_sql("INSERT INTO dbo.ZWMS_INVENTORY (Material) VALUES ('TEST')")

def test_blocks_ddl_and_administrative_commands():
    with pytest.raises(ValueError):
        validate_sql("DROP TABLE dbo.ZWMS_INVENTORY")

    with pytest.raises(ValueError):
        validate_sql("ALTER TABLE dbo.ZWMS_INVENTORY ADD column_test INT")

    with pytest.raises(ValueError):
        validate_sql("TRUNCATE TABLE dbo.ZWMS_INVENTORY")

    with pytest.raises(ValueError):
        validate_sql("EXEC sp_who2")

def test_blocks_unauthorized_tables():
    with pytest.raises(ValueError, match="Unauthorized table reference"):
        validate_sql("SELECT * FROM sys.users")

    with pytest.raises(ValueError, match="Unauthorized table reference"):
        validate_sql("SELECT * FROM SecretFinancials")

def test_blocks_multiple_statements_and_injection():
    # Semicolon stacked queries
    with pytest.raises(ValueError, match="Multiple SQL statements"):
        validate_sql("SELECT TOP 5 * FROM dbo.ZWMS_INVENTORY; SELECT TOP 5 * FROM dbo.ZWMS_BIN_MASTER")

    # SQL Comments
    with pytest.raises(ValueError, match="SQL comments"):
        validate_sql("SELECT * FROM dbo.ZWMS_INVENTORY -- trailing comment")

    with pytest.raises(ValueError, match="SQL comments"):
        validate_sql("SELECT * /* inline comment */ FROM dbo.ZWMS_INVENTORY")

def test_markdown_code_block_stripping():
    wrapped = "```sql\nSELECT TOP 5 Material FROM dbo.ZWMS_INVENTORY\n```"
    cleaned = validate_sql(wrapped)
    assert cleaned.startswith("SELECT")
    assert "```" not in cleaned
