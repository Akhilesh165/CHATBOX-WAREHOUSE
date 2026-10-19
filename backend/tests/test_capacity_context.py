import pytest
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    format_deterministic_answer,
    parse_range_filters,
)
from backend.app.validator import validate_sql
from backend.app.db import execute_readonly
from backend.app.semantic_context import PROJECT_CAPACITY_THRESHOLDS

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


def test_compound_capacity_utilization_numerical():
    """Rule: COMPOUND CAPACITY + UTILIZATION QUERY:
    When user asks for bins with capacity < 45 FT3 and utilization > 80%:
    - Entity must be identified as Bin
    - Apply BOTH conditions to the same bin records
    - Result must show Bin, Capacity, Utilization %, and Occupied Volume
    - Must NOT return plant or warehouse level summaries
    """
    q = "bins with capacity < 45 FT3 and utilization > 80%"
    plan = deterministic_warehouse_sql_generator(q)
    assert plan["intent"] == "compound_capacity_utilization"
    assert plan["output_type"] == "table"
    assert plan["chart_type"] == "none"
    assert "BinStats" in plan["sql"]
    assert "CapacityNum <= 45" in plan["sql"]
    assert "UtilizationNum >= 80" in plan["sql"]

    sql = validate_sql(plan["sql"])
    rows, _ = execute_readonly(sql)
    assert len(rows) > 0
    first_row = rows[0]
    assert "Bin" in first_row
    assert "Capacity" in first_row
    assert "Utilization %" in first_row
    assert "Occupied Volume" in first_row

    ans = format_deterministic_answer(q, rows)
    assert "matching bins" in ans.lower()
    assert "capacity" in ans.lower()
    assert "utilization" in ans.lower()


def test_compound_capacity_clarification_qualitative():
    """Rule: COMPOUND CAPACITY + UTILIZATION QUERY:
    'Low' and 'high' must use predefined project thresholds if available.
    If no thresholds are defined, the chatbot must ask for clarification rather than inventing arbitrary thresholds.
    """
    # Ensure thresholds are undefined
    PROJECT_CAPACITY_THRESHOLDS["low_capacity_threshold"] = None
    PROJECT_CAPACITY_THRESHOLDS["high_capacity_threshold"] = None
    PROJECT_CAPACITY_THRESHOLDS["high_utilization_threshold"] = None
    PROJECT_CAPACITY_THRESHOLDS["low_utilization_threshold"] = None

    q = "low capacity but high utilization"
    plan = deterministic_warehouse_sql_generator(q)
    assert plan["intent"] == "compound_capacity_clarification"
    assert plan["output_type"] == "text"
    assert plan["chart_type"] == "none"

    ans = format_deterministic_answer(q, [{"clarification_needed": 1}])
    assert "specify the thresholds" in ans.lower()
    assert "no default thresholds" in ans.lower()


def test_compound_capacity_with_predefined_thresholds():
    """Rule: COMPOUND CAPACITY + UTILIZATION QUERY:
    When predefined thresholds are configured in PROJECT_CAPACITY_THRESHOLDS,
    qualitative queries use them directly without asking for clarification.
    """
    try:
        PROJECT_CAPACITY_THRESHOLDS["low_capacity_threshold"] = 40.0
        PROJECT_CAPACITY_THRESHOLDS["high_utilization_threshold"] = 75.0

        q = "small bins with high utilization"
        plan = deterministic_warehouse_sql_generator(q)
        assert plan["intent"] == "compound_capacity_utilization"
        assert "CapacityNum <= 40" in plan["sql"]
        assert "UtilizationNum >= 75" in plan["sql"]

        sql = validate_sql(plan["sql"])
        rows, _ = execute_readonly(sql)
        assert len(rows) > 0
        for r in rows:
            assert "Bin" in r
            assert "Capacity" in r
            assert "Utilization %" in r
    finally:
        PROJECT_CAPACITY_THRESHOLDS["low_capacity_threshold"] = None
        PROJECT_CAPACITY_THRESHOLDS["high_utilization_threshold"] = None


def test_entity_preservation_find_bins():
    """Rule: ENTITY PRESERVATION RULE:
    If the user asks 'Find bins…', the final result must be at bin level.
    Do not replace the requested bin-level result with Plant Breakdown,
    Warehouse Summary, aggregate statistics, or unrelated charts.
    """
    q = "Find bins in Plant 1258"
    plan = deterministic_warehouse_sql_generator(q)
    assert plan["intent"] == "find_bins_list"
    assert plan["output_type"] == "table"
    assert plan["chart_type"] == "none"
    assert plan["filters"]["plant"] == "1258"

    sql = validate_sql(plan["sql"])
    rows, _ = execute_readonly(sql)
    assert len(rows) > 0
    # Every row must be an individual bin in plant 1258
    for r in rows:
        assert "Bin" in r
        assert str(r.get("Plant")) == "1258"
        assert "Capacity" in r
        assert "Utilization %" in r

    ans = format_deterministic_answer(q, rows)
    assert "bins in plant 1258" in ans.lower()
    assert "individual bin level" in ans.lower()


def test_bin_capacity_range_query_semantics():
    """Targeted Test: BIN + CAPACITY + RANGE queries must resolve strictly to:
    entity = BIN, metric = BIN_CAPACITY, operation = FILTER, operator = BETWEEN / GT / LT,
    response_mode = TABLE. Must never be misclassified as bin utilization or inventory quantity.
    """
    # 1. Target query: Between 1000 and 5000
    q1 = "Find bins with capacity between 1000 and 5000"
    plan1 = deterministic_warehouse_sql_generator(q1)
    assert plan1["intent"] == "range_query"
    assert plan1["metric"] == "BIN_CAPACITY"
    assert plan1["output_type"] == "table"
    qp1 = plan1["query_plan"]
    assert qp1["entity"] == "BIN"
    assert qp1["metric"] == "BIN_CAPACITY"
    assert qp1["operation"] == "FILTER"
    assert qp1["operator"] == "BETWEEN"
    assert qp1["lower_bound"] == 1000.0
    assert qp1["upper_bound"] == 5000.0
    assert qp1["response_mode"] == "TABLE"

    # Natural-language forms
    for q_var in [
        "Show bins with capacity from 1000 to 5000",
        "List bins having capacity between 1000 and 5000",
        "Which bins have capacity in the range 1000-5000?",
        "Find storage bins with capacity from 1000 to 5000",
        "Show bins whose capacity is between 1000 and 5000",
        "Find bins with capacity >= 1000 and <= 5000",
        "Show bins with capacity greater than or equal to 1000 and less than or equal to 5000",
        "List bins between 1000 and 5000 capacity",
    ]:
        p = deterministic_warehouse_sql_generator(q_var)
        assert p["query_plan"]["entity"] == "BIN", f"Failed entity for {q_var}"
        assert p["query_plan"]["metric"] == "BIN_CAPACITY", f"Failed metric for {q_var}"
        assert p["query_plan"]["operator"] == "BETWEEN", f"Failed operator for {q_var}"
        assert p["query_plan"]["lower_bound"] == 1000.0
        assert p["query_plan"]["upper_bound"] == 5000.0

    # Single-sided capacity queries
    p_above = deterministic_warehouse_sql_generator("Find bins with capacity above 1000")
    assert p_above["query_plan"]["entity"] == "BIN"
    assert p_above["query_plan"]["metric"] == "BIN_CAPACITY"
    assert p_above["query_plan"]["operator"] == "GT"
    assert p_above["query_plan"]["lower_bound"] == 1000.0

    p_below = deterministic_warehouse_sql_generator("Find bins with capacity below 5000")
    assert p_below["query_plan"]["entity"] == "BIN"
    assert p_below["query_plan"]["metric"] == "BIN_CAPACITY"
    assert p_below["query_plan"]["operator"] == "LT"
    assert p_below["query_plan"]["upper_bound"] == 5000.0

    # DB Execution and Answer formatting for 0 rows
    rows1, _ = execute_readonly(plan1["sql"])
    assert len(rows1) == 0
    ans1 = format_deterministic_answer(q1, rows1)
    assert "No bins found with configured capacity" in ans1
    assert "between 1,000 and 5,000 FT³" in ans1


