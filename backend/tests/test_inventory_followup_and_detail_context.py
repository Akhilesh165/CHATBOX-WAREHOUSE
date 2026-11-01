"""Tests for PERMANENT INVENTORY FOLLOW-UP & DETAILED INVENTORY ENHANCEMENT CONTEXT.

Covers:
Part A - Conversational Follow-Up Context:
- Test Case 1: Top / Lowest Materials (4 turns)
- Test Case 2: Plant Inventory Comparison (4 turns)
- Test Case 3: Highest / Lowest Material (3 turns)
- Test Case 4: Multi-Plant Summary & Drilldown (3 turns)

Part B - Rich Detailed Inventory Responses:
- Single-Plant Detailed Inventory (Overview KPIs, Distribution, Top 5, Observations, Data Table)
- Multi-Plant Detailed Inventory Comparison (Side-by-side Comparative Table, Insights)
- Strict Non-Regression on Normal Inventory Queries
"""

import pytest
from backend.app.llm import (
    extract_and_update_conversation_state,
    deterministic_warehouse_sql_generator,
    format_deterministic_answer,
    optimize_response_format,
)
from backend.app.db import execute_readonly


def test_followup_case_1_top_lowest_materials():
    """Follow-up Test Case 1: Top / Lowest Materials across multi-turn dialog."""
    h = []
    # Turn 1: Show the top 10 materials by quantity.
    q1 = "Show the top 10 materials by quantity."
    r1 = deterministic_warehouse_sql_generator(q1, h)
    assert r1.get("intent") == "material_quantity_ranking"
    assert "10" in r1["sql"]
    assert "DESC" in r1["sql"]
    h.append({"role": "user", "content": q1})
    h.append({"role": "assistant", "content": "Here are the top 10 materials by quantity."})

    # Turn 2: What about the lowest ones?
    q2 = "What about the lowest ones?"
    r2 = deterministic_warehouse_sql_generator(q2, h)
    assert r2.get("intent") == "material_quantity_ranking"
    assert "ASC" in r2["sql"]
    h.append({"role": "user", "content": q2})
    h.append({"role": "assistant", "content": "Here are the lowest 10 materials by quantity."})

    # Turn 3: Only for Plant 1258.
    q3 = "Only for Plant 1258."
    r3 = deterministic_warehouse_sql_generator(q3, h)
    assert r3.get("intent") == "material_quantity_ranking"
    assert "1258" in r3["sql"]
    assert "ASC" in r3["sql"]
    h.append({"role": "user", "content": q3})
    h.append({"role": "assistant", "content": "Here are the lowest 10 materials for Plant 1258."})

    # Turn 4: Show top 5 instead.
    q4 = "Show top 5 instead."
    r4 = deterministic_warehouse_sql_generator(q4, h)
    assert r4.get("intent") == "material_quantity_ranking"
    assert "5" in r4["sql"]
    assert "1258" in r4["sql"]
    assert "DESC" in r4["sql"]


def test_followup_case_2_plant_inventory_comparison():
    """Follow-up Test Case 2: Plant Inventory Comparison and scope reset."""
    h = []
    # Turn 1: Show inventory for Plant 1258.
    q1 = "Show inventory for Plant 1258."
    r1 = deterministic_warehouse_sql_generator(q1, h)
    assert "1258" in r1["sql"]
    h.append({"role": "user", "content": q1})
    h.append({"role": "assistant", "content": "Plant 1258 holds 495,404 units."})

    # Turn 2: What about Plant 7228?
    q2 = "What about Plant 7228?"
    r2 = deterministic_warehouse_sql_generator(q2, h)
    assert "7228" in r2["sql"]
    h.append({"role": "user", "content": q2})
    h.append({"role": "assistant", "content": "Plant 7228 holds 1,837,768 units."})

    # Turn 3: Compare them.
    q3 = "Compare them."
    r3 = deterministic_warehouse_sql_generator(q3, h)
    assert "1258" in r3["sql"] and "7228" in r3["sql"]
    h.append({"role": "user", "content": q3})
    h.append({"role": "assistant", "content": "Comparison between Plant 1258 and Plant 7228."})

    # Turn 4: Show me the top 10 materials.
    # Scope MUST reset to ALL plants (not filtered to 1258 or 7228).
    q4 = "Show me the top 10 materials."
    r4 = deterministic_warehouse_sql_generator(q4, h)
    assert r4.get("intent") == "material_quantity_ranking"
    assert "1258" not in r4["sql"]
    assert "7228" not in r4["sql"]
    assert "DESC" in r4["sql"]


def test_followup_case_3_highest_lowest_material():
    """Follow-up Test Case 3: Highest / Lowest Material extreme queries."""
    h = []
    # Turn 1: Which material has the highest quantity?
    q1 = "Which material has the highest quantity?"
    r1 = deterministic_warehouse_sql_generator(q1, h)
    assert r1.get("intent") == "material_max_quantity"
    assert "DESC" in r1["sql"]
    h.append({"role": "user", "content": q1})
    h.append({"role": "assistant", "content": "Material BV430100002 has the highest quantity."})

    # Turn 2: What about the lowest?
    q2 = "What about the lowest?"
    r2 = deterministic_warehouse_sql_generator(q2, h)
    assert r2.get("intent") == "material_min_quantity"
    assert "ASC" in r2["sql"]
    h.append({"role": "user", "content": q2})
    h.append({"role": "assistant", "content": "Material XYZ has the lowest quantity."})

    # Turn 3: Only in Plant 7228.
    q3 = "Only in Plant 7228."
    r3 = deterministic_warehouse_sql_generator(q3, h)
    assert r3.get("intent") == "material_min_quantity"
    assert "7228" in r3["sql"]
    assert "ASC" in r3["sql"]


def test_followup_case_4_multi_plant_summary_drilldown():
    """Follow-up Test Case 4: Multi-plant summary, candidate ranking, and drilldown."""
    h = []
    # Turn 1: Show inventory summary for Plant 1258, 1268 and 7228.
    q1 = "Show inventory summary for Plant 1258, 1268 and 7228."
    r1 = deterministic_warehouse_sql_generator(q1, h)
    assert all(p in r1["sql"] for p in ["1258", "1268", "7228"])
    h.append({"role": "user", "content": q1})
    h.append({
        "role": "assistant",
        "content": "Plant 1268 has 888,290 units, Plant 7228 has 1,837,768 units, Plant 1258 has 495,404 units."
    })

    # Turn 2: Which one has the highest inventory?
    q2 = "Which one has the highest inventory?"
    r2 = deterministic_warehouse_sql_generator(q2, h)
    # Must only rank candidate plants [1258, 1268, 7228]
    assert all(p in r2["sql"] for p in ["1258", "1268", "7228"])
    assert "DESC" in r2["sql"]
    h.append({"role": "user", "content": q2})
    h.append({
        "role": "assistant",
        "content": "Plant 7228 has the highest total inventory quantity with 1,837,768 units."
    })

    # Turn 3: Show the top materials from that plant.
    q3 = "Show the top materials from that plant."
    r3 = deterministic_warehouse_sql_generator(q3, h)
    assert r3.get("intent") == "material_quantity_ranking"
    assert "7228" in r3["sql"]
    assert "DESC" in r3["sql"]


def test_detailed_single_plant_inventory():
    """Part B: Single-plant detailed inventory report query and rich formatting."""
    queries = [
        "Show inventory details for Plant 1258",
        "Give me detailed inventory for Plant 7228",
        "plant 1268 inventory in detail",
    ]
    for q in queries:
        res = deterministic_warehouse_sql_generator(q)
        assert res.get("intent") == "plant_inventory_detail"
        rows, _ = execute_readonly(res["sql"])
        assert len(rows) > 0
        assert "Plant Total Bins" in rows[0]
        assert "Plant Occupied Bins" in rows[0]
        assert "Plant Total Records" in rows[0]

        ans = format_deterministic_answer(q, rows)
        assert "Detailed Inventory Report" in ans
        assert "Key Inventory & Storage Metrics" in ans
        assert "Total Stock Quantity" in ans
        assert "Occupied Bins" in ans
        assert "Empty Bins" in ans
        assert "Inventory Distribution Highlights" in ans
        assert "Top 5 Materials" in ans

        opt = optimize_response_format(q, rows, res)
        assert opt.get("output_type") == "table"


def test_detailed_multi_plant_inventory_comparison():
    """Part B: Multi-plant detailed inventory comparison query and rich formatting."""
    queries = [
        "Give me a detailed inventory comparison of Plant 1258 and 7228",
        "Compare Plant 1268 vs 1258 inventory in detail",
    ]
    for q in queries:
        res = deterministic_warehouse_sql_generator(q)
        assert res.get("intent") == "multi_plant_inventory_detail"
        rows, _ = execute_readonly(res["sql"])
        assert len(rows) == 2
        assert "Avg Qty per Material" in rows[0]
        assert "Empty Bins" in rows[0]
        assert "Total Bins" in rows[0]

        ans = format_deterministic_answer(q, rows)
        assert "Detailed Inventory Comparison" in ans
        assert "Comparative Plant KPIs" in ans
        assert "Key Comparative Insights & Observations" in ans
        assert "Inventory Volume Leader" in ans

        opt = optimize_response_format(q, rows, res)
        assert opt.get("output_type") == "table"


def test_strict_non_regression_normal_inventory_queries():
    """Part C: Strict non-regression - normal inventory queries remain concise."""
    # 1. Normal single plant inventory remains summary (not full detailed report)
    q1 = "Show inventory for Plant 1258."
    r1 = deterministic_warehouse_sql_generator(q1)
    assert r1.get("intent") != "plant_inventory_detail"
    rows1, _ = execute_readonly(r1["sql"])
    ans1 = format_deterministic_answer(q1, rows1)
    assert "Detailed Inventory Report" not in ans1

    # 2. Total inventory quantity scalar remains text scalar
    q2 = "How much inventory does plant 1258 have?"
    r2 = deterministic_warehouse_sql_generator(q2)
    assert r2.get("intent") == "total_inventory_quantity"
    rows2, _ = execute_readonly(r2["sql"])
    opt2 = optimize_response_format(q2, rows2, r2)
    assert opt2.get("output_type") == "text"
