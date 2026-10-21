import pytest
from backend.app.llm import deterministic_warehouse_sql_generator, format_deterministic_answer
from backend.app.validator import validate_sql, validate_query_result
from backend.app.db import execute_readonly


def test_query_a_almost_full_bins():
    """A: Find bins that are almost full.
    Expected: entity = BIN, metric = BIN_UTILIZATION, condition = NEAR_FULL, response_mode = TABLE.
    """
    q = "Find bins that are almost full"
    gen = deterministic_warehouse_sql_generator(q, [])
    assert gen["intent"] == "almost_full_bins"
    plan = gen.get("query_plan", {})
    assert plan.get("entity") == "BIN"
    assert plan.get("metric") == "BIN_UTILIZATION"
    assert plan.get("condition") == "NEAR_FULL"
    assert plan.get("response_mode") == "TABLE"
    assert "HAVING" in gen["sql"] and "80.0" in gen["sql"] and "100.0" in gen["sql"]

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) > 0
    # Validate result with semantic validator
    valid, reason = validate_query_result(q, plan, gen["sql"], rows)
    assert valid, f"Validation failed: {reason}"
    ans = format_deterministic_answer(q, rows)
    assert "operating near full capacity" in ans


def test_query_b_missing_volume_percentage():
    """B: Give me the percentage of inventory materials missing volume information.
    Expected: entity = MATERIAL, metric = MISSING_VOLUME_PERCENTAGE, operation = PERCENTAGE, response_mode = SUMMARY.
    """
    q = "Give me the percentage of inventory materials missing volume information"
    gen = deterministic_warehouse_sql_generator(q, [])
    assert gen["intent"] == "materials_missing_volume_percentage"
    plan = gen.get("query_plan", {})
    assert plan.get("entity") == "MATERIAL"
    assert plan.get("metric") == "MISSING_VOLUME_PERCENTAGE"
    assert plan.get("operation") == "PERCENTAGE"
    assert plan.get("response_mode") == "SUMMARY"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 1
    assert "Missing Volume Percentage" in rows[0]
    valid, reason = validate_query_result(q, plan, gen["sql"], rows)
    assert valid, f"Validation failed: {reason}"
    ans = format_deterministic_answer(q, rows)
    assert "%" in ans and "missing volume information" in ans


def test_query_c_available_capacity_by_plant():
    """C: Show available capacity by plant.
    Expected: entity = PLANT, metric = AVAILABLE_CAPACITY, group_by = PLANT, operation = AGGREGATION, response_mode = TABLE.
    """
    q = "Show available capacity by plant"
    gen = deterministic_warehouse_sql_generator(q, [])
    assert gen["intent"] == "plant_available_capacity"
    plan = gen.get("query_plan", {})
    assert plan.get("entity") == "PLANT"
    assert plan.get("metric") == "AVAILABLE_CAPACITY"
    assert plan.get("group_by") == "PLANT"
    assert plan.get("operation") == "AGGREGATION"
    assert plan.get("response_mode") == "TABLE"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 4
    for r in rows:
        assert "Plant" in r
        assert "Total Capacity (FT3)" in r
        assert "Occupied Volume (FT3)" in r
        assert "Available Capacity (FT3)" in r
    ans = format_deterministic_answer(q, rows)
    assert "operational plants" in ans


def test_query_d_plant_7228_bin_utilization_chart():
    """D: Create a chart for Plant 7228 bin utilization.
    Expected: entity = BIN, metric = BIN_UTILIZATION, filters = {plant: '7228'}, operation = ANALYZE, response_mode = GRAPH.
    Must NOT be top_utilized_bins and must NOT have >80% filter or limit 10.
    """
    q = "Create a chart for Plant 7228 bin utilization"
    gen = deterministic_warehouse_sql_generator(q, [])
    assert gen["intent"] == "plant_bin_utilization_detail"
    assert gen["chart_type"] == "bar"
    assert gen["output_type"] == "bar_chart"
    plan = gen.get("query_plan", {})
    assert plan.get("entity") == "BIN"
    assert plan.get("metric") == "BIN_UTILIZATION"
    assert plan.get("operation") == "ANALYZE"
    assert plan.get("filters", {}).get("plant") == "7228"
    assert plan.get("response_mode") == "GRAPH"
    assert "> 80" not in gen["sql"]
    assert "TOP 10" not in gen["sql"]


def test_query_e_graph_of_bin_utilization():
    """E: Show me a graph of bin utilization.
    Expected: entity = BIN, metric = BIN_UTILIZATION, operation = ANALYZE, group_by = PLANT, response_mode = GRAPH.
    """
    q = "Show me a graph of bin utilization"
    gen = deterministic_warehouse_sql_generator(q, [])
    assert gen["intent"] == "bin_utilization"
    assert gen["chart_type"] == "bar"
    assert gen["output_type"] == "bar_chart"
    plan = gen.get("query_plan", {})
    assert plan.get("entity") == "BIN"
    assert plan.get("metric") == "BIN_UTILIZATION"
    assert plan.get("group_by") == "PLANT"
    assert plan.get("response_mode") == "GRAPH"


def test_query_f_visualize_bin_utilization_plant_7228():
    """F: Visualize bin utilization for Plant 7228.
    Expected: entity = BIN, metric = BIN_UTILIZATION, filters = {plant: '7228'}, operation = ANALYZE, response_mode = GRAPH.
    """
    q = "Visualize bin utilization for Plant 7228"
    gen = deterministic_warehouse_sql_generator(q, [])
    assert gen["intent"] == "plant_bin_utilization_detail"
    assert gen["chart_type"] == "bar"
    assert gen["output_type"] == "bar_chart"
    plan = gen.get("query_plan", {})
    assert plan.get("entity") == "BIN"
    assert plan.get("metric") == "BIN_UTILIZATION"
    assert plan.get("filters", {}).get("plant") == "7228"
    assert plan.get("response_mode") == "GRAPH"


def test_query_g_plot_top_10_most_utilized_bins_plant_7228():
    """G: Plot the top 10 most utilized bins in Plant 7228.
    Expected: entity = BIN, metric = BIN_UTILIZATION, operation = RANK, limit = 10, plant = 7228, response_mode = GRAPH.
    """
    q = "Plot the top 10 most utilized bins in Plant 7228"
    gen = deterministic_warehouse_sql_generator(q, [])
    assert gen["intent"] == "top_utilized_bins"
    assert gen["chart_type"] == "bar"
    assert gen["output_type"] == "bar_chart"
    plan = gen.get("query_plan", {})
    assert plan.get("intent") == "RANKING"
    assert plan.get("limit") == 10
    assert plan.get("rank_scope", {}).get("Plant") == "7228"
    assert "TOP 10" in gen["sql"]


def test_query_h_show_available_capacity_by_plant_as_graph():
    """H: Show available capacity by plant as a graph.
    Expected: entity = PLANT, metric = AVAILABLE_CAPACITY, group_by = PLANT, operation = AGGREGATION, response_mode = GRAPH.
    """
    q = "Show available capacity by plant as a graph"
    gen = deterministic_warehouse_sql_generator(q, [])
    assert gen["intent"] == "plant_available_capacity"
    assert gen["chart_type"] == "bar"
    assert gen["output_type"] == "bar_chart"
    plan = gen.get("query_plan", {})
    assert plan.get("entity") == "PLANT"
    assert plan.get("metric") == "AVAILABLE_CAPACITY"
    assert plan.get("group_by") == "PLANT"
    assert plan.get("response_mode") == "GRAPH"


def test_query_i_show_plant_wise_inventory_as_graph():
    """I: Show plant-wise inventory as a graph.
    Expected: entity = PLANT, metric = TOTAL_INVENTORY_QUANTITY, group_by = PLANT, operation = AGGREGATION, response_mode = GRAPH.
    """
    q = "Show plant-wise inventory as a graph"
    gen = deterministic_warehouse_sql_generator(q, [])
    assert gen["intent"] == "plant_inventory"
    assert gen["chart_type"] == "bar"
    assert gen["output_type"] == "bar_chart"
    plan = gen.get("query_plan", {})
    assert plan.get("entity") == "PLANT"
    assert plan.get("metric") == "TOTAL_INVENTORY_QUANTITY"
    assert plan.get("group_by") == "PLANT"
    assert plan.get("response_mode") == "GRAPH"


def test_query_j_conversational_follow_up_graph():
    """J: Turn 1: Give me detailed bin utilization for Plant 7228
          Turn 2: Show me with graph
    Expected: Context preserved (Plant 7228, bin utilization), only response_mode changes to GRAPH.
    """
    history = [
        {"role": "user", "content": "Give me detailed bin utilization for Plant 7228."},
        {"role": "assistant", "content": "Plant 7228 bin utilization is 79.1%..."}
    ]
    gen = deterministic_warehouse_sql_generator("Show me with graph", history)
    assert gen["intent"] == "plant_bin_utilization_detail"
    assert gen["chart_type"] == "bar"
    assert gen["output_type"] == "bar_chart"
    plan = gen.get("query_plan", {})
    assert plan.get("entity") == "BIN"
    assert plan.get("metric") == "BIN_UTILIZATION"
    assert plan.get("filters", {}).get("plant") == "7228"
    assert plan.get("response_mode") == "GRAPH"
