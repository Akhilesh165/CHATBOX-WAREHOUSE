import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.llm import (
    extract_explicit_plants,
    extract_and_update_conversation_state,
    deterministic_warehouse_sql_generator,
)

client = TestClient(app)


def test_comparison_connectors_plant_extraction():
    test_queries = [
        ("the bin utilization of plant 1268 vs 1258 in detail", ["1268", "1258"]),
        ("compare the bin utilization of plant 1268 and 1258 in detail", ["1268", "1258"]),
        ("bin utilization of plant 1268 versus 1258 in detail", ["1268", "1258"]),
        ("bin utilization of plant 1268 against 1258 in detail", ["1268", "1258"]),
        ("bin utilization for plant 1268 vs plant 1258 in detail", ["1268", "1258"]),
        ("show plant 1268 vs plant 1258 bin utilization in detail", ["1268", "1258"]),
        ("plant 1268 vs 1258 bin utilization", ["1268", "1258"]),
        ("plant 1268 and plant 1258 bin utilization comparison", ["1268", "1258"]),
        ("how does bin utilization of plant 1268 compare with 1258", ["1268", "1258"]),
        ("bin utilization: 1268 vs 1258", ["1268", "1258"]),
        ("1268 vs 1258 bin utilization in detail", ["1268", "1258"]),
        ("1268 v/s 1258 bin utilization", ["1268", "1258"]),
        ("1268 vs. 1258 bin utilization", ["1268", "1258"]),
        ("bin utilization of plant 1268 compared with 1258 in detail", ["1268", "1258"]),
        ("bin utilization of plant 1268 relative to 1258 in detail", ["1268", "1258"]),
    ]

    for q, expected in test_queries:
        plants = extract_explicit_plants(q)
        assert sorted(plants) == sorted(expected), f"Failed for query: {q}, got: {plants}"


def test_other_metric_comparison_plant_extraction():
    metric_queries = [
        ("Plant 1268 vs Plant 1258 inventory", ["1268", "1258"]),
        ("Plant 1268 vs Plant 1258 bins", ["1268", "1258"]),
        ("Plant 1268 vs Plant 1258 materials", ["1268", "1258"]),
        ("Plant 1268 vs Plant 1258 empty bins", ["1268", "1258"]),
        ("Plant 1268 versus Plant 1258 capacity", ["1268", "1258"]),
        ("1268 against 1258 total inventory", ["1268", "1258"]),
    ]

    for q, expected in metric_queries:
        plants = extract_explicit_plants(q)
        assert sorted(plants) == sorted(expected), f"Failed for query: {q}, got: {plants}"


def test_vs_query_matches_compare_query_routing():
    q_vs = "the bin utilization of plant 1268 vs 1258 in detail"
    q_compare = "compare the bin utilization of plant 1268 and 1258 in detail"

    state_vs = extract_and_update_conversation_state(q_vs, [])
    state_comp = extract_and_update_conversation_state(q_compare, [])

    assert sorted(state_vs.get("plants", [])) == ["1258", "1268"]
    assert sorted(state_comp.get("plants", [])) == ["1258", "1268"]
    assert state_vs.get("operation") == "comparison"
    assert state_comp.get("operation") == "comparison"

    res_vs = deterministic_warehouse_sql_generator(q_vs, [])
    res_comp = deterministic_warehouse_sql_generator(q_compare, [])

    sql_vs = res_vs["sql"] if isinstance(res_vs, dict) else res_vs
    sql_comp = res_comp["sql"] if isinstance(res_comp, dict) else res_comp

    assert sql_vs is not None
    assert sql_comp is not None
    # Both must query both plants 1268 and 1258
    assert "'1268'" in sql_vs and "'1258'" in sql_vs
    assert "'1268'" in sql_comp and "'1258'" in sql_comp
    # Both should have utilization calculation
    assert "Utilization %" in sql_vs
    assert "Utilization %" in sql_comp


def test_section_14_variations_sql_generation():
    queries = [
        "the bin utilization of plant 1268 vs 1258 in detail",
        "compare the bin utilization of plant 1268 and 1258 in detail",
        "bin utilization of plant 1268 versus 1258 in detail",
        "bin utilization of plant 1268 against 1258 in detail",
        "plant 1268 vs plant 1258 bin utilization in detail",
        "show bin utilization for plant 1268 vs plant 1258 in detail",
        "1268 vs 1258 bin utilization in detail",
    ]
    for q in queries:
        res = deterministic_warehouse_sql_generator(q, [])
        sql = res["sql"] if isinstance(res, dict) else res
        assert sql is not None, f"SQL generation returned None for: {q}"
        assert "'1268'" in sql and "'1258'" in sql, f"Missing plant filtering in: {q}\nSQL: {sql}"
        assert "Utilization %" in sql or "Utilization" in sql, f"Missing utilization calculation in: {q}\nSQL: {sql}"


def test_vs_query_api_multi_plant_detailed_tables():
    q = "the bin utilization of plant 1268 vs 1258 in detail"
    resp = client.post("/api/chat", json={"message": q})
    assert resp.status_code == 200
    data = resp.json()

    assert data["intent"] == "multi_plant_bin_detail"
    assert data["output_type"] == "table"
    tables = data.get("tables", [])
    assert len(tables) == 2, f"Expected 2 tables for plants 1268 and 1258, got {len(tables)}"

    plants = [t["plant"] for t in tables]
    assert "1268" in plants
    assert "1258" in plants

    for tbl in tables:
        assert tbl["displayed_count"] > 0
        assert "Plant " in tbl["title"]
        rows = tbl["rows"]
        assert len(rows) > 0
        first_row = rows[0]
        assert "Bin" in first_row
        assert "Utilization %" in first_row


def test_non_regression_queries():
    # 1. which bin has the lowest utilization
    q_lowest = "which bin has the lowest utilization"
    res_lowest = deterministic_warehouse_sql_generator(q_lowest, [])
    sql_lowest = res_lowest["sql"] if isinstance(res_lowest, dict) else res_lowest
    assert sql_lowest is not None
    assert "ORDER BY SUM(i.UnrestrictedQty" in sql_lowest or "ORDER BY [Utilization %] ASC" in sql_lowest or "ORDER BY" in sql_lowest
    assert "TOP 1" in sql_lowest or "LIMIT 1" in sql_lowest

    # 2. which bin has the highest utilization
    q_highest = "which bin has the highest utilization"
    res_highest = deterministic_warehouse_sql_generator(q_highest, [])
    sql_highest = res_highest["sql"] if isinstance(res_highest, dict) else res_highest
    assert sql_highest is not None
    assert "DESC" in sql_highest

    # 3. what is the utilization of plant 1268
    q_plant = "what is the utilization of plant 1268"
    res_plant = deterministic_warehouse_sql_generator(q_plant, [])
    sql_plant = res_plant["sql"] if isinstance(res_plant, dict) else res_plant
    assert sql_plant is not None
    assert "'1268'" in sql_plant

    # 4. show bins in plant 1268 and plant 1258
    q_bins = "show bins in plant 1268 and plant 1258"
    res_bins = deterministic_warehouse_sql_generator(q_bins, [])
    sql_bins = res_bins["sql"] if isinstance(res_bins, dict) else res_bins
    assert sql_bins is not None
    assert "'1268'" in sql_bins and "'1258'" in sql_bins
