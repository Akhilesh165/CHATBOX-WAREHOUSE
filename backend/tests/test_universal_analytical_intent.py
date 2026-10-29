"""Test Suite for Universal Analytical Intent Normalization.

Verifies:
1. HIGHEST / MAX: Bin utilization, Material quantity, Plant inventory, Bin capacity (preserving metric).
2. LOWEST / MIN: Bin utilization, Material quantity, Plant inventory, Bin capacity.
3. AVERAGE: Average bin utilization (Warehouse: 70.32%, Plant 1268: 68.73%), returns clean text statement.
4. TOTAL / SUM: Total inventory quantity (SUM of UnrestrictedQty) with sum/combined/altogether.
5. COUNT: Empty bins, total bins, unique materials.
6. TOP / BOTTOM permutations: Word order variations, preserving metric & explicit N >= 2.
7. FOLLOW-UP Polarity Flips: Flips between MAX and MIN while retaining entity, metric, and filters.
8. TYPO NORMALIZATION: Tolerance across analytical queries.
"""

import pytest
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    is_highest_bin_utilization_intent,
    is_lowest_bin_utilization_intent,
    is_bin_capacity_extreme_intent,
    is_average_bin_utilization_intent,
    extract_and_update_conversation_state,
    format_deterministic_answer,
    optimize_response_format,
    normalize_query_typos
)
from backend.app.db import execute_readonly


# ==========================================
# 1. HIGHEST / MAX INTENT
# ==========================================

@pytest.mark.parametrize("q", [
    "Which bin is holding the highest bin utilization?",
    "Which bin has the highest utilization?",
    "Show me the highest utilized bin",
    "Which is the most utilized bin?",
    "Find the bin with maximum utilization",
    "Which bin is utilized the most?",
    "Bin with the highest utilization percentage",
])
def test_highest_bin_utilization_intent(q):
    assert is_highest_bin_utilization_intent(q) is True
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "HIGHEST_BIN_UTILIZATION"
    assert "TOP 1" in res.get("sql", "")
    assert "DESC" in res.get("sql", "")
    assert res.get("output_type") == "text"


def test_highest_bin_utilization_execution():
    res = deterministic_warehouse_sql_generator("Which bin has the highest utilization?")
    rows, _ = execute_readonly(res["sql"])
    assert len(rows) == 1
    assert rows[0]["Bin"] == "BLINKIT"
    assert "671.1%" in str(rows[0]["Utilization %"])
    
    ans = format_deterministic_answer("Which bin has the highest utilization?", rows)
    assert "BLINKIT" in ans
    assert "671.1%" in ans


def test_highest_material_quantity():
    q = "Which material has the highest quantity?"
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "material_max_quantity"
    assert "TOP 1" in res.get("sql", "")
    assert "DESC" in res.get("sql", "")


def test_highest_plant_inventory():
    q = "Which plant has the highest inventory?"
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "plant_inventory_ranking"
    assert res.get("output_type") == "text"
    assert "DESC" in res.get("sql", "")


def test_highest_bin_capacity_metric_preserved():
    # Metric preservation: Must return Volume (FT3), NOT utilization!
    q = "Which bin has the highest capacity?"
    assert is_bin_capacity_extreme_intent(q) == "MAX"
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "HIGHEST_BIN_CAPACITY"
    assert "b.Volume DESC" in res.get("sql", "")
    assert res.get("output_type") == "text"

    rows, _ = execute_readonly(res["sql"])
    assert len(rows) == 1
    assert rows[0]["Bin"] == "NRKP0107A1"
    assert rows[0]["Plant"] == 1258
    assert rows[0]["Capacity"] == 80.0

    ans = format_deterministic_answer(q, rows)
    assert "NRKP0107A1" in ans
    assert "80.0 FT3" in ans or "80" in ans


# ==========================================
# 2. LOWEST / MIN INTENT
# ==========================================

@pytest.mark.parametrize("q", [
    "Which bin has the lowest utilization?",
    "Which is the least utilized bin?",
    "Find the bin with minimum utilization",
    "Which bin has minimum utilization?",
    "Show the bin with the lowest bin utilization",
    "What is the lowest utilized bin?",
    "Which bin is utilized the least?",
    "Bin with the lowest utilization percentage",
])
def test_lowest_bin_utilization_intent(q):
    assert is_lowest_bin_utilization_intent(q) is True
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "LOWEST_BIN_UTILIZATION"
    assert "TOP 1" in res.get("sql", "")
    assert "ASC" in res.get("sql", "")
    assert res.get("output_type") == "text"


def test_lowest_bin_utilization_plant_scoped_execution():
    q = "Which bin has the lowest utilization in Plant 1268?"
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "LOWEST_BIN_UTILIZATION"
    assert "b.Plant = '1268'" in res.get("sql", "")
    rows, _ = execute_readonly(res["sql"])
    assert len(rows) == 1
    assert rows[0]["Bin"] == "BOR11L2P17"
    assert "0.0%" in str(rows[0]["Utilization %"])

    ans = format_deterministic_answer(q, rows)
    assert "BOR11L2P17" in ans
    assert "0.0%" in ans


def test_lowest_material_quantity():
    q = "Which material has the lowest quantity?"
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "material_min_quantity"
    assert "TOP 1" in res.get("sql", "")
    assert "ASC" in res.get("sql", "")


def test_lowest_plant_inventory():
    q = "Which plant has the lowest inventory?"
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "plant_inventory_ranking"
    assert res.get("output_type") == "text"
    assert "ASC" in res.get("sql", "")


def test_lowest_bin_capacity():
    q = "Which bin has the lowest capacity?"
    assert is_bin_capacity_extreme_intent(q) == "MIN"
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "LOWEST_BIN_CAPACITY"
    assert "b.Volume ASC" in res.get("sql", "")
    assert res.get("output_type") == "text"


# ==========================================
# 3. AVERAGE INTENT
# ==========================================

def test_average_bin_utilization_warehouse():
    q = "What is the average bin utilization?"
    assert is_average_bin_utilization_intent(q) is True
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "AVERAGE_BIN_UTILIZATION"
    assert res.get("output_type") == "text"
    assert res.get("chart_type") == "none"

    rows, _ = execute_readonly(res["sql"])
    assert len(rows) == 1
    assert rows[0]["Average Bin Utilization %"] == 70.32 or rows[0]["Average Utilization"] == "70.32%"
    assert rows[0]["Total Bins"] == 33129
    assert rows[0]["Occupied Bins"] == 23296

    ans = format_deterministic_answer(q, rows)
    assert "70.32%" in ans
    assert "33,129" in ans


def test_average_bin_utilization_plant_1268():
    q = "What is the average bin utilization in Plant 1268?"
    assert is_average_bin_utilization_intent(q) is True
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "AVERAGE_BIN_UTILIZATION"
    assert "b.Plant = '1268'" in res.get("sql", "")

    rows, _ = execute_readonly(res["sql"])
    assert len(rows) == 1
    assert rows[0]["Average Bin Utilization %"] == 68.73 or rows[0]["Average Utilization"] == "68.73%"
    assert rows[0]["Total Bins"] == 15582
    assert rows[0]["Occupied Bins"] == 10710

    ans = format_deterministic_answer(q, rows)
    assert "68.73%" in ans
    assert "15,582" in ans


# ==========================================
# 4. TOTAL / SUM INTENT
# ==========================================

@pytest.mark.parametrize("q", [
    "What is the total inventory quantity?",
    "What is the sum of inventory in the warehouse?",
    "Total stock quantity",
    "Combined inventory quantity",
    "What is the overall inventory quantity altogether?",
])
def test_total_inventory_quantity_intent(q):
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "total_inventory_quantity"
    assert "SUM(UnrestrictedQty)" in res.get("sql", "")


# ==========================================
# 5. COUNT INTENT
# ==========================================

@pytest.mark.parametrize("q", [
    "Number of empty bins?",
    "Count empty bins",
    "How many empty bins are there?",
    "Total count of empty bins",
])
def test_count_empty_bins(q):
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "empty_bins_count"
    assert "Empty Bins Count" in res.get("sql", "")


@pytest.mark.parametrize("q", [
    "Count the bins",
    "Count bins",
    "Number of bins?",
    "How many bins in total?",
])
def test_count_total_bins(q):
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "total_bins_count"
    assert "Total Bins Count" in res.get("sql", "")


@pytest.mark.parametrize("q", [
    "Count materials",
    "How many materials?",
    "Number of unique materials",
    "How many distinct materials do we have?",
])
def test_count_unique_materials(q):
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "unique_materials_count"
    assert "Material" in res.get("sql", "")


# ==========================================
# 6. TOP / BOTTOM / RANKING PERMUTATIONS
# ==========================================

@pytest.mark.parametrize("q,expected_intent,expected_limit", [
    ("Top 10 most utilized bins", "top_utilized_bins", 10),
    ("10 highest utilized bins", "top_utilized_bins", 10),
    ("Most utilized 10 bins", "top_utilized_bins", 10),
    ("10 bins with highest utilization", "top_utilized_bins", 10),
    ("Bottom 10 bins", "least_utilized_bins", 10),
    ("10 least utilized bins", "least_utilized_bins", 10),
    ("Least utilized 10 bins", "least_utilized_bins", 10),
    ("10 bins with lowest utilization", "least_utilized_bins", 10),
])
def test_ranking_permutations(q, expected_intent, expected_limit):
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == expected_intent
    assert f"TOP {expected_limit}" in res.get("sql", "")
    assert res.get("output_type") in ["table", "bar_chart"]


# ==========================================
# 7. FOLLOW-UP CONTEXT & POLARITY FLIPS
# ==========================================

def test_followup_highest_to_lowest_bin_polarity():
    # Initial question
    q1 = "Which bin has the highest utilization in Plant 7228?"
    state = extract_and_update_conversation_state(q1, history=[])
    assert state.get("topic") == "HIGHEST_BIN_UTILIZATION"
    assert state.get("filters", {}).get("plant") == "7228"

    # Follow-up: "What about the lowest?"
    history = [
        {"role": "user", "content": q1},
        {"role": "assistant", "content": "The bin with the highest utilization in Plant 7228 is `NRJP1309G2`."}
    ]
    q2 = "What about the lowest?"
    state2 = extract_and_update_conversation_state(q2, history=history)
    assert state2.get("topic") == "LOWEST_BIN_UTILIZATION"
    assert state2.get("ranking") == "lowest"
    assert state2.get("limit") == 1
    assert state2.get("filters", {}).get("plant") == "7228"

    res = deterministic_warehouse_sql_generator(q2, history=history)
    assert res.get("intent") == "LOWEST_BIN_UTILIZATION"
    assert "b.Plant = '7228'" in res.get("sql", "")
    assert "ASC" in res.get("sql", "")


def test_followup_highest_to_lowest_capacity_polarity():
    # Initial question
    q1 = "Which bin has the highest capacity?"
    state = extract_and_update_conversation_state(q1, history=[])
    assert state.get("topic") == "HIGHEST_BIN_CAPACITY"

    # Follow-up: "What about the lowest?"
    history = [
        {"role": "user", "content": q1},
        {"role": "assistant", "content": "The bin with highest capacity is `NRKP0107A1`."}
    ]
    q2 = "What about the lowest?"
    state2 = extract_and_update_conversation_state(q2, history=history)
    assert state2.get("topic") == "LOWEST_BIN_CAPACITY"
    assert state2.get("ranking") == "lowest"

    res = deterministic_warehouse_sql_generator(q2, history=history)
    assert res.get("intent") == "LOWEST_BIN_CAPACITY"
    assert "b.Volume ASC" in res.get("sql", "")


# ==========================================
# 8. TYPO NORMALIZATION
# ==========================================

@pytest.mark.parametrize("raw,normalized_substr", [
    ("which bin has the higest utilzation", "highest"),
    ("which bin has lowes utliztion", "lowest"),
    ("avrage bin utiliztion", "average"),
    ("total invetor quanity", "quantity"),
    ("count materails", "materials"),
    ("bin with highest capcity", "capacity"),
])
def test_typo_normalization(raw, normalized_substr):
    norm = normalize_query_typos(raw)
    assert normalized_substr in norm.lower()
