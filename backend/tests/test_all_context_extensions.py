"""Comprehensive Test Suite for Canonical Context Architecture extensions:
1. RANGE_CONTEXT (Numeric, Quantity, Percentage, Date ranges)
2. GENERAL COMPARISON CONTEXT (Inventory, Materials, Bins, Utilization, Empty Bins, Storage Locations)
3. BIN UTILIZATION CONTEXT (Simple value, Ranked table, Detail breakdown without buttons, No auto chart)
4. UNIVERSAL RANKING CONTEXT (Materials, Bins, Plants, Directions DESC/ASC, No auto chart)
5. SINGLE-LINE RESPONSE CONTEXT (Overrides: one line, single statement, just the number, suppressing tables/charts)
6. UNIVERSAL DETAIL / RESPONSE-DEPTH CONTEXT (Semantic mode, No Generate Detailed Analysis button)
7. RESPONSE-FORMAT DECISION ENGINE
8. CONVERSATION STATE PRESERVATION & ANTI-HALLUCINATION
"""
import pytest
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    format_deterministic_answer,
    optimize_response_format,
    parse_range_filters,
    is_detail_requested,
    is_single_line_requested
)
from backend.app.db import execute_readonly
from backend.app.validator import validate_query_result
from backend.app.semantic_context import WAREHOUSE_SEMANTIC_CONTEXT


# =========================================================================
# 1. RANGE CONTEXT TESTS
# =========================================================================

def test_parse_range_filters_between_units():
    rf = parse_range_filters("Show materials between 100 and 500 units")
    assert len(rf) == 1
    assert rf[0]["field"] == "UnrestrictedQty"
    assert rf[0]["operator"] == "BETWEEN"
    assert rf[0]["lower"] == 100.0
    assert rf[0]["upper"] == 500.0
    assert rf[0]["inclusive"] is True


def test_parse_range_filters_hyphen_percentage():
    rf = parse_range_filters("Bins with 10%-30% utilization")
    assert len(rf) == 1
    assert rf[0]["field"] == "BinUtilizationPct"
    assert rf[0]["operator"] == "BETWEEN"
    assert rf[0]["lower"] == 10.0
    assert rf[0]["upper"] == 30.0


def test_parse_range_filters_at_least():
    rf = parse_range_filters("materials with at least 100 units")
    assert len(rf) == 1
    assert rf[0]["field"] == "UnrestrictedQty"
    assert rf[0]["operator"] == "GTE"
    assert rf[0]["lower"] == 100.0


def test_parse_range_filters_below():
    rf = parse_range_filters("materials with below 500 units")
    assert len(rf) == 1
    assert rf[0]["field"] == "UnrestrictedQty"
    assert rf[0]["operator"] == "LT"
    assert rf[0]["upper"] == 500.0


def test_range_query_generation_and_execution():
    q = "Show materials with between 100 and 500 units in Plant 1258"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "range_query"
    assert "query_plan" in gen
    assert gen["query_plan"]["intent"] == "RANGE_QUERY"
    assert len(gen["query_plan"]["range_filters"]) == 1
    assert gen["query_plan"]["range_filters"][0]["operator"] == "BETWEEN"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) > 0
    for r in rows:
        assert 100 <= r["Total Stock Qty"] <= 500
        assert str(r["Plant"]) == "1258"

    ans = format_deterministic_answer(q, rows)
    assert "Plant 1258" in ans
    assert "between 100 and 500 units" in ans


# =========================================================================
# 2. GENERAL COMPARISON CONTEXT TESTS
# =========================================================================

def test_comparison_not_shortcut_to_bin_utilization():
    """'Compare Plant 1258 and Plant 7228' without utilization must produce multi-metric comparison."""
    q = "Compare Plant 1258 and Plant 7228"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "plant_comparison"
    plan = gen["query_plan"]
    assert plan["intent"] == "COMPARISON"
    assert plan["comparison_subject"] == "overview"
    assert len(plan["comparison_entities"]) == 2
    assert plan["group_by"] == ["Plant"]

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 2
    plants_in_result = {str(r["Plant"]) for r in rows}
    assert plants_in_result == {"1258", "7228"}

    ans = format_deterministic_answer(q, rows)
    assert ans.startswith("| Plant |")
    assert "1258" in ans and "7228" in ans


def test_comparison_total_inventory():
    q = "Compare total inventory between Plant 1258 and Plant 7228"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "plant_comparison"
    assert gen["query_plan"]["comparison_subject"] == "total_inventory"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 2
    assert "Total Inventory Quantity" in rows[0]

    ans = format_deterministic_answer(q, rows)
    assert ans.startswith("| Plant |")
    assert "Total Inventory Quantity" in ans
    assert "1258" in ans and "7228" in ans


def test_comparison_unique_materials():
    q = "Compare materials between Plant 1258 and Plant 7228"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "plant_comparison"
    assert gen["query_plan"]["comparison_subject"] == "materials"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 2
    assert "Unique Materials Count" in rows[0]

    ans = format_deterministic_answer(q, rows)
    assert ans.startswith("| Plant |")
    assert "Unique Materials Count" in ans
    assert "1258" in ans and "7228" in ans


def test_comparison_empty_bins():
    q = "Compare empty bins between Plant 1258 and Plant 7228"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "plant_comparison"
    assert gen["query_plan"]["comparison_subject"] == "empty_bins"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 2
    assert "Empty Bins" in rows[0]

    ans = format_deterministic_answer(q, rows)
    assert ans.startswith("| Plant |")
    assert "Empty Bins" in ans
    assert "1258" in ans and "7228" in ans


def test_comparison_bin_utilization():
    q = "Compare bin utilization between Plant 1258 and Plant 7228"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "plant_comparison"
    assert gen["query_plan"]["comparison_subject"] == "bin_utilization"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 2
    assert "Bin Utilization %" in rows[0]


def test_comparison_storage_locations():
    q = "Compare storage locations between Plant 1258 and Plant 7228"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "plant_comparison"
    assert gen["query_plan"]["comparison_subject"] == "storage_locations"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 2
    assert "Storage Locations Count" in rows[0]

    ans = format_deterministic_answer(q, rows)
    assert ans.startswith("| Plant |")
    assert "Storage Locations Count" in ans
    assert "1258" in ans and "7228" in ans


# =========================================================================
# 3. UNIVERSAL RANKING CONTEXT TESTS (No Auto Chart)
# =========================================================================

def test_rank_materials_by_quantity_no_auto_chart():
    q = "Rank materials by quantity"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] in ["material_quantity_ranking", "material_stock_ranking"]
    assert gen["chart_type"] == "none"
    assert gen["output_type"] == "table"
    assert gen["query_plan"]["intent"] == "RANKING"
    assert gen["query_plan"]["rank_direction"] == "DESC"
    assert gen["query_plan"]["rank_entity"] == "Material"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) > 0
    assert "Total Stock Quantity" in rows[0]

    opt = optimize_response_format(q, rows, gen)
    assert opt["chart_type"] == "none"
    assert opt["output_type"] == "table"


def test_top_10_most_utilized_bins_no_auto_chart():
    q = "Show the top 10 most utilized bins"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["chart_type"] == "none"
    assert gen["output_type"] == "table"
    assert gen["query_plan"]["intent"] == "RANKING"
    assert gen["query_plan"]["limit"] == 10

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 10

    opt = optimize_response_format(q, rows, gen)
    assert opt["chart_type"] == "none"
    assert opt["output_type"] == "table"


def test_least_utilized_bins_ranking():
    q = "What about the least utilized bins?"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["chart_type"] == "none"
    assert gen["output_type"] == "table"
    assert gen["query_plan"]["intent"] == "RANKING"
    assert gen["query_plan"]["rank_direction"] == "ASC"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) > 0
    # Lowest utilization should be at the top
    assert float(str(rows[0]["Utilization %"]).replace("%", "")) <= float(str(rows[-1]["Utilization %"]).replace("%", ""))


# =========================================================================
# 4. SINGLE-LINE RESPONSE CONTEXT TESTS
# =========================================================================

def test_single_line_override_phrases():
    for phrase in ["in one line", "single line", "single statement", "just the number", "just the percentage", "briefly"]:
        assert is_single_line_requested(f"What is total inventory {phrase}") is True


def test_single_line_suppresses_table_and_chart():
    q = "What is total warehouse inventory in single line"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["output_type"] == "text"
    assert gen["chart_type"] == "none"

    rows = [{"Total Unrestricted Quantity": 2279723.0}]
    opt = optimize_response_format(q, rows, gen)
    assert opt["output_type"] == "text"
    assert opt["chart_type"] == "none"


def test_single_statement_highest_plant_bin_utilization():
    q = "Which plant has the highest bin utilization in one line"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["output_type"] == "text"
    assert gen["chart_type"] == "none"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 1
    ans = format_deterministic_answer(q, rows)
    assert "\n" not in ans
    assert "Plant 7228" in ans


# =========================================================================
# 5. UNIVERSAL DETAIL / RESPONSE DEPTH CONTEXT TESTS
# =========================================================================

def test_detail_requested_detection():
    assert is_detail_requested("explain bin utilization for Plant 7228 in detail") is True
    assert is_detail_requested("deep dive into plant 7228") is True
    assert is_detail_requested("break it down for plant 1258") is True
    assert is_detail_requested("what is bin utilization for Plant 7228") is False


def test_detail_activates_breakdown_without_button():
    q = "explain bin utilization for Plant 7228 in detail"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "plant_bin_utilization_detailed_analysis"
    assert gen["chart_type"] == "bar"
    assert "follow_up_action" not in gen

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) > 0
    assert "Storage Location" in rows[0]
    assert "Bin Utilization %" in rows[0] or "UtilizationPct" in rows[0]

    is_valid, reason = validate_query_result(q, gen.get("query_plan"), gen["sql"], rows)
    assert is_valid is True
    assert "follow_up_action" not in gen


# =========================================================================
# 6. CONVERSATION STATE PRESERVATION TESTS
# =========================================================================

def test_conversational_flow_preserves_state():
    """Flow:
    1. Show the top 10 most utilized bins
    2. What about the least utilized ones?
    3. Only for Plant 1258
    4. Show 5 instead
    """
    # Turn 1
    q1 = "Show the top 10 most utilized bins"
    g1 = deterministic_warehouse_sql_generator(q1)
    assert g1["query_plan"]["rank_direction"] == "DESC"
    assert g1["query_plan"]["limit"] == 10

    # Turn 2: least utilized
    h1 = [
        {"role": "user", "content": q1},
        {"role": "assistant", "content": "Top 10 Most Utilized Bins"}
    ]
    q2 = "What about the least utilized ones?"
    g2 = deterministic_warehouse_sql_generator(q2, history=h1)
    assert g2["query_plan"]["rank_direction"] == "ASC"
    assert g2["query_plan"]["limit"] == 10

    # Turn 3: Only for Plant 1258
    h2 = h1 + [
        {"role": "user", "content": q2},
        {"role": "assistant", "content": "Least Utilized Bins"}
    ]
    q3 = "Only for Plant 1258"
    g3 = deterministic_warehouse_sql_generator(q3, history=h2)
    assert g3["filters"].get("plant") == "1258"
    assert "1258" in g3["sql"]

    # Turn 4: Show 5 instead
    h3 = h2 + [
        {"role": "user", "content": q3},
        {"role": "assistant", "content": "Least Utilized Bins for Plant 1258"}
    ]
    q4 = "Show 5 instead"
    g4 = deterministic_warehouse_sql_generator(q4, history=h3)
    assert g4["query_plan"]["limit"] == 5
    assert g4["filters"].get("plant") == "1258"
    assert "1258" in g4["sql"]

    rows4, _ = execute_readonly(g4["sql"])
    assert len(rows4) == 5
    for r in rows4:
        assert str(r.get("Plant", "1258")) == "1258"


# =========================================================================
# 7. ANTI-HALLUCINATION DYNAMIC COUNTS TEST
# =========================================================================

def test_no_hardcoded_plant_counts_in_answer():
    """Verify that format_deterministic_answer reports the true row count, not a hardcoded count."""
    mock_rows = [
        {"Material": "MAT01", "Description": "Item 1", "Qty": 10, "UOM": "EA", "Storage Location": "SL1", "Bin": "B1", "Plant": "1258"},
        {"Material": "MAT02", "Description": "Item 2", "Qty": 20, "UOM": "EA", "Storage Location": "SL2", "Bin": "B2", "Plant": "1258"},
    ]
    ans = format_deterministic_answer("Show materials in Plant 1258", mock_rows)
    assert "**2 inventory records**" in ans
    assert "5,517" not in ans
