import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.llm import deterministic_warehouse_sql_generator, format_deterministic_answer, extract_single_plant_safe, extract_explicit_limit
from backend.app.db import execute_readonly

client = TestClient(app)

def test_scenario_1_show_completely_empty_bins():
    """Scenario 1: 'Show completely empty bins' must report true count (9,833), never default 50."""
    gen = deterministic_warehouse_sql_generator("Show completely empty bins")
    assert "TOP 50" not in gen["sql"]
    assert gen["intent"] == "putaway_bins"
    
    rows, _ = execute_readonly(gen["sql"], max_rows=10000)
    assert len(rows) == 9833
    
    ans = format_deterministic_answer("Show completely empty bins", rows)
    assert "9,833" in ans
    assert "50 empty bins" not in ans

def test_scenario_2_how_many_completely_empty_bins():
    """Scenario 2: 'How many completely empty bins are there?' -> crisp single-line scalar count, no table."""
    response = client.post("/api/chat", json={
        "message": "How many completely empty bins are there?",
        "conversation_id": "test-scenario-2-count"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["output_type"] in ["text", "kpi", "single_value"]
    assert "9,833" in data["answer"]
    assert "across the warehouse network" in data["answer"]
    assert data["meta"]["total_count"] == 1 or data["meta"]["rowCount"] == 1

def test_scenario_3_show_all_completely_empty_bins():
    """Scenario 3: 'Show all completely empty bins' -> reports 9,833."""
    gen = deterministic_warehouse_sql_generator("Show all completely empty bins")
    assert "TOP 50" not in gen["sql"]
    rows, _ = execute_readonly(gen["sql"], max_rows=10000)
    assert len(rows) == 9833
    ans = format_deterministic_answer("Show all completely empty bins", rows)
    assert "9,833" in ans

def test_scenario_4_show_completely_empty_bins_plant_1258():
    """Scenario 4: 'Show completely empty bins in Plant 1258' -> reports 2,425."""
    gen = deterministic_warehouse_sql_generator("Show completely empty bins in Plant 1258")
    assert "TOP 50" not in gen["sql"]
    rows, _ = execute_readonly(gen["sql"], max_rows=10000)
    assert len(rows) == 2425
    ans = format_deterministic_answer("Show completely empty bins in Plant 1258", rows)
    assert "2,425" in ans
    assert "Plant 1258" in ans

def test_scenario_5_show_top_10_most_utilized_bins():
    """Scenario 5: 'Show the top 10 most utilized bins' -> returns exactly 10 rows."""
    response = client.post("/api/chat", json={
        "message": "Show the top 10 most utilized bins",
        "conversation_id": "test-scenario-5-top10"
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["rows"]) == 10
    assert data["meta"]["displayed_count"] == 10

def test_scenario_6_show_top_5_most_utilized_bins():
    """Scenario 6: 'Show the top 5 most utilized bins' -> returns exactly 5 rows."""
    response = client.post("/api/chat", json={
        "message": "Show the top 5 most utilized bins",
        "conversation_id": "test-scenario-6-top5"
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["rows"]) == 5
    assert data["meta"]["displayed_count"] == 5

def test_scenario_7_show_5_empty_bins_total_vs_displayed():
    """Scenario 7: Explicit user limit ('Show 5 empty bins') -> total_count=9833, displayed_count=5."""
    gen = deterministic_warehouse_sql_generator("Show 5 empty bins")
    assert "TOP 5" in gen["sql"]
    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 5
    assert rows[0].get("TotalMatching") == 9833
    
    ans = format_deterministic_answer("Show 5 empty bins", rows)
    assert "9,833 matching empty bins" in ans
    assert "Showing the first **5**" in ans

    # Also test via API
    response = client.post("/api/chat", json={
        "message": "Show 5 empty bins",
        "conversation_id": "test-scenario-7-bins5"
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["rows"]) == 5
    assert data["meta"]["total_count"] == 9833
    assert data["meta"]["displayed_count"] == 5
    assert data["total_count"] == 9833
    assert data["displayed_count"] == 5

def test_scenario_8_show_bins_between_50_and_80_utilization():
    """Scenario 8: Range query 'Show bins between 50% and 80% utilization' -> no false limit 50 extracted."""
    gen = deterministic_warehouse_sql_generator("Show bins between 50% and 80% utilization")
    assert "TOP 50" not in gen["sql"]
    lim = extract_explicit_limit("show bins between 50% and 80% utilization")
    assert lim is None

def test_scenario_9_rank_all_plants_by_occupied_volume():
    """Scenario 9: 'Rank all plants by total occupied volume' -> exactly 4 plants."""
    response = client.post("/api/chat", json={
        "message": "Rank all plants by total occupied volume",
        "conversation_id": "test-scenario-9-rank"
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["rows"]) == 4

def test_scenario_10_compare_plant_1258_and_7228():
    """Scenario 10: Compare Plant 1258 and Plant 7228."""
    response = client.post("/api/chat", json={
        "message": "Compare Plant 1258 and Plant 7228 for bin utilization",
        "conversation_id": "test-scenario-10-compare"
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["rows"]) == 2

def test_scenario_11_plant_safety_no_numeric_false_positives():
    """Scenario 11: Prevent false plant extraction for numbers like 1000 in 'quantity above 1000'."""
    assert extract_single_plant_safe("quantity above 1000") is None
    assert extract_single_plant_safe("materials with stock over 2500") is None
    assert extract_single_plant_safe("bins between 50% and 80% utilization") is None
    assert extract_single_plant_safe("Plant 1258") == "1258"
    assert extract_single_plant_safe("in 7228") == "7228"

def test_scenario_12_api_metadata_fields():
    """Scenario 12: Verify total_count and displayed_count are present in ChatResponse and Meta."""
    response = client.post("/api/chat", json={
        "message": "Show 10 empty bins in Plant 1258",
        "conversation_id": "test-scenario-12-meta"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 2425
    assert data["displayed_count"] == 10
    assert data["meta"]["total_count"] == 2425
    assert data["meta"]["displayed_count"] == 10
