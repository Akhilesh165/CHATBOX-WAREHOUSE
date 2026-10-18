import pytest
from backend.app.models import ChatRequest
from backend.app.main import chat_endpoint
from backend.app.llm import deterministic_warehouse_sql_generator

@pytest.mark.asyncio
async def test_compare_bins_two_plants_two_tables():
    q = "Compare the bins over 80% utilization in Plant 1268 and 1258."
    req = ChatRequest(message=q)
    res = await chat_endpoint(req)

    assert len(res.tables) == 2, f"Expected 2 tables, got {len(res.tables)}"
    
    t1 = res.tables[0]
    t2 = res.tables[1]
    
    assert t1.plant == "1268"
    assert "Plant 1268" in t1.title
    assert t1.count == 3806
    assert len(t1.rows) == 3806
    
    assert t2.plant == "1258"
    assert "Plant 1258" in t2.title
    assert t2.count == 97
    assert len(t2.rows) == 97

    # Check identical columns in both tables
    expected_cols = {"Bin", "Plant", "Bin Capacity", "Occupied Volume", "Utilization %"}
    assert set(t1.rows[0].keys()) == expected_cols
    assert set(t2.rows[0].keys()) == expected_cols

    # Total row count
    assert res.meta.rowCount == 3906 or res.meta.rowCount == 3903

@pytest.mark.asyncio
async def test_compare_bins_three_plants_three_tables():
    q = "Compare bins above 80% utilization in Plant 1258, 1268, and 7228"
    req = ChatRequest(message=q)
    res = await chat_endpoint(req)

    assert len(res.tables) == 3, f"Expected 3 tables, got {len(res.tables)}"
    assert res.tables[0].plant == "1258"
    assert res.tables[1].plant == "1268"
    assert res.tables[2].plant == "7228"

@pytest.mark.asyncio
async def test_compare_bins_empty_table_for_unmatched_plant():
    q = "Compare the bins over 300% utilization in Plant 1268 and 1258."
    req = ChatRequest(message=q)
    res = await chat_endpoint(req)

    assert len(res.tables) == 2
    t1 = res.tables[0] # 1268
    t2 = res.tables[1] # 1258
    assert t1.count > 0
    assert t2.count == 0
    assert t2.empty_message is not None
    assert "No bins found" in t2.empty_message

@pytest.mark.asyncio
async def test_single_plant_threshold_remains_single_table():
    q = "Show bins above 80% utilization in Plant 1258"
    req = ChatRequest(message=q)
    res = await chat_endpoint(req)

    assert len(res.tables) == 0  # Single plant does not use multi-table comparison
    assert len(res.rows) == 97
