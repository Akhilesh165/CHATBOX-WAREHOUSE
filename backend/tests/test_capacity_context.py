import pytest
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    format_deterministic_answer,
    parse_range_filters,
)
from backend.app.validator import validate_sql
from backend.app.db import execute_readonly

def test_total_warehouse_capacity():
    """Rule 4: Total capacity queries (e.g. 'What is the total capacity?', 'Show total bin capacity', 'How much capacity does this warehouse have?')
    must return Total Warehouse/Bin Capacity = SUM(Total Bin Capacity) with single-line scalar formatting and no charts.
    """
    queries = [
        "What is the total capacity?",
        "Show total bin capacity.",
        "How much capacity does this warehouse have?",
        "What is the total warehouse capacity?"
    ]
    for q in queries:
        plan = deterministic_warehouse_sql_generator(q)
        assert plan["intent"] == "total_warehouse_capacity"
        assert "SUM(Volume)" in plan["sql"]
        assert "dbo.ZWMS_BIN_MASTER" in plan["sql"]
        assert plan["chart_type"] == "none"
        assert plan["output_type"] == "text"

        # Execute query against SQLite test DB
        sql = validate_sql(plan["sql"])
        rows, _ = execute_readonly(sql)
        assert len(rows) == 1
        assert "Total Capacity (FT3)" in rows[0]
        assert "Total Bins" in rows[0]
        assert rows[0]["Total Capacity (FT3)"] > 1000000

        # Verify formatting
        ans = format_deterministic_answer(q, rows)
        assert "total warehouse storage capacity" in ans.lower()
        assert "FT³" in ans
        assert "bins" in ans


def test_available_capacity_warehouse_and_plant():
    """Rule 5: Available capacity queries ('How much space is left?', 'Show available capacity', 'How much unused capacity is there?')
    must calculate Available Capacity = Total Capacity - Occupied Volume.
    """
    plan = deterministic_warehouse_sql_generator("How much space is left?")
    assert plan["intent"] == "available_capacity"
    assert "Total Available Capacity (FT3)" in plan["sql"]
    assert plan["chart_type"] == "none"
    assert plan["output_type"] == "text"

    sql = validate_sql(plan["sql"])
    rows, _ = execute_readonly(sql)
    assert len(rows) == 1
    assert rows[0]["Total Available Capacity (FT3)"] > 0
    assert rows[0]["Total Capacity (FT3)"] > rows[0]["Total Available Capacity (FT3)"]

    ans = format_deterministic_answer("How much space is left?", rows)
    assert "available storage capacity" in ans.lower()
    assert "FT³" in ans


def test_occupied_volume_queries():
    """Rule 6: Occupied volume queries ('How much space is occupied?', 'Show occupied volume')
    must return occupied volume (SUM(i.UnrestrictedQty * m.Volume)) without substituting utilization percentage.
    """
    plan = deterministic_warehouse_sql_generator("How much space is occupied?")
    assert plan["intent"] == "occupied_volume"
    assert "Total Occupied Volume (FT3)" in plan["sql"]
    assert plan["chart_type"] == "none"
    assert plan["output_type"] == "text"

    sql = validate_sql(plan["sql"])
    rows, _ = execute_readonly(sql)
    assert len(rows) == 1
    assert rows[0]["Total Occupied Volume (FT3)"] > 0
    assert rows[0]["Occupied Bins"] > 0

    ans = format_deterministic_answer("How much space is occupied?", rows)
    assert "occupied storage volume" in ans.lower()
    assert "FT³" in ans


def test_capacity_summary():
    """Rule 8: Capacity summary ('Give me a capacity summary', 'warehouse capacity summary')
    must provide Total Capacity, Occupied Volume, Available Capacity, and Capacity Utilization % by Plant.
    """
    plan = deterministic_warehouse_sql_generator("Give me a capacity summary")
    assert plan["intent"] == "capacity_summary"
    assert "PlantCap" in plan["sql"]
    assert "Available Capacity (FT3)" in plan["sql"]
    assert "Total Capacity (FT3)" in plan["sql"]
    assert "Occupied Volume (FT3)" in plan["sql"]
    assert "Capacity Utilization %" in plan["sql"]

    sql = validate_sql(plan["sql"])
    rows, _ = execute_readonly(sql)
    assert len(rows) >= 2
    for r in rows:
        assert r["Total Capacity (FT3)"] > 0
        assert r["Available Capacity (FT3)"] >= 0

    ans = format_deterministic_answer("Give me a capacity summary", rows)
    assert "Warehouse Capacity Summary" in ans
    assert "Plant 1258" in ans or "Plant 7228" in ans


def test_capacity_by_plant():
    """Rule 9: Capacity by plant ('Show capacity for Plant 1258', 'What is the storage capacity of Plant 1258?')
    must return Plant, Total Capacity, Occupied Volume, Available Capacity, and Capacity Utilization %.
    """
    plan = deterministic_warehouse_sql_generator("Show capacity for Plant 1258")
    assert plan["intent"] == "plant_capacity"
    assert plan["filters"]["plant"] == "1258"
    assert "Plant 1258" in plan["chart_title"]

    sql = validate_sql(plan["sql"])
    rows, _ = execute_readonly(sql)
    assert len(rows) == 1
    assert str(rows[0]["Plant"]) == "1258"
    assert rows[0]["Total Capacity (FT3)"] > 0
    assert rows[0]["Available Capacity (FT3)"] > 0

    ans = format_deterministic_answer("Show capacity for Plant 1258", rows)
    assert "Plant 1258" in ans
    assert "total storage capacity" in ans
    assert "available capacity remaining" in ans


def test_empty_bins_capacity():
    """Rule 10 & 40: Capacity in empty bins ('How much capacity is available in empty bins?')
    must compute SUM(Total Bin Capacity) for empty bins where Occupied Volume is 0.
    """
    plan = deterministic_warehouse_sql_generator("How much capacity is available in empty bins?")
    assert plan["intent"] == "empty_bins_capacity"
    assert "Empty Bins Available Capacity (FT3)" in plan["sql"]

    sql = validate_sql(plan["sql"])
    rows, _ = execute_readonly(sql)
    assert len(rows) == 1
    assert rows[0]["Empty Bins Count"] > 0
    assert rows[0]["Empty Bins Available Capacity (FT3)"] > 0

    ans = format_deterministic_answer("How much capacity is available in empty bins?", rows)
    assert "empty bins" in ans
    assert "available storage capacity" in ans


def test_single_bin_capacity_lookup():
    """Rule 12: Single bin capacity lookup ('What is the capacity of bin NRJP2124D2?')
    must return Bin, Plant, Storage Location, Total Capacity, Occupied Volume, and Available Capacity.
    """
    plan = deterministic_warehouse_sql_generator("What is the capacity of bin NRJP2124D2?")
    assert plan["intent"] == "single_bin_capacity"
    assert plan["filters"]["bin"] == "NRJP2124D2"

    sql = validate_sql(plan["sql"])
    rows, _ = execute_readonly(sql)
    if rows:
        assert rows[0]["Bin"].startswith("NRJP2124D2")
        assert "Total Capacity (FT3)" in rows[0]
        assert "Available Capacity (FT3)" in rows[0]
        ans = format_deterministic_answer("What is the capacity of bin NRJP2124D2?", rows)
        assert "NRJP2124D2" in ans
        assert "total capacity" in ans


def test_capacity_comparison_between_plants():
    """Rule 11: Capacity comparison ('Compare capacity between Plant 1258 and Plant 7228', 'Which plant has more available capacity?')
    must present side-by-side capacity figures and state which plant has more available capacity.
    """
    plan = deterministic_warehouse_sql_generator("Compare capacity between Plant 1258 and Plant 7228")
    assert plan["intent"] == "plant_comparison"
    assert "Total Capacity (FT3)" in plan["sql"] or "Total Capacity Volume (FT3)" in plan["sql"]

    sql = validate_sql(plan["sql"])
    rows, _ = execute_readonly(sql)
    assert len(rows) == 2

    ans = format_deterministic_answer("Compare capacity between Plant 1258 and Plant 7228", rows)
    assert "Capacity Comparison" in ans or "Capacity" in ans
    assert "Plant 1258" in ans
    assert "Plant 7228" in ans


def test_capacity_range_filtering():
    """Rule 42: Capacity ranges:
    - Total Capacity: 'Bins between 400 and 600 FT3 total capacity'
    - Available Capacity: 'Bins with 100 to 300 FT3 free space'
    """
    # 1. Total capacity range
    plan_tot = deterministic_warehouse_sql_generator("Show bins with total capacity between 400 and 600 FT3")
    assert plan_tot["intent"] == "range_query"
    assert plan_tot["query_plan"]["field"] == "TotalCapacity"
    assert "BETWEEN 400" in plan_tot["sql"] or "BETWEEN 400.0" in plan_tot["sql"]

    sql_tot = validate_sql(plan_tot["sql"])
    rows_tot, _ = execute_readonly(sql_tot)
    for r in rows_tot:
        assert 400 <= r["Total Capacity (FT3)"] <= 600

    # 2. Available capacity range
    plan_avail = deterministic_warehouse_sql_generator("Show bins with available capacity between 100 and 300 FT3")
    assert plan_avail["intent"] == "range_query"
    assert plan_avail["query_plan"]["field"] == "AvailableCapacity"

    sql_avail = validate_sql(plan_avail["sql"])
    rows_avail, _ = execute_readonly(sql_avail)
    for r in rows_avail:
        assert 100 <= r["Available Capacity (FT3)"] <= 300


def test_capacity_referential_followup():
    """Rule 44: Referential follow-ups ('how much total occupied volume do they have?')
    referencing previously queried bins.
    """
    history = [
        {"role": "user", "content": "Show top 5 most utilized bins"},
        {"role": "assistant", "content": "Top 5 Most Utilized Bins..."}
    ]
    followup_q = "how much total occupied volume do they have?"
    plan = deterministic_warehouse_sql_generator(followup_q, history=history)
    assert plan["intent"] == "referential_bins_capacity"
    assert "PriorBins" in plan["sql"]

    sql = validate_sql(plan["sql"])
    rows, _ = execute_readonly(sql)
    assert len(rows) == 1
    assert rows[0]["Referenced Bins Count"] == 5
    assert rows[0]["Total Capacity (FT3)"] > 0
    assert rows[0]["Total Occupied Volume (FT3)"] > 0

    ans = format_deterministic_answer(followup_q, rows)
    assert "5 referenced bins" in ans
    assert "total capacity" in ans
    assert "occupied" in ans
