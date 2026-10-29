"""Test Suite for HIGHEST_BIN_UTILIZATION Semantic Intent Context.

Verifies:
1. Intent classification: All semantic variations of BIN + HIGHEST/MAX/MOST + UTILIZATION map to 'HIGHEST_BIN_UTILIZATION'.
2. Typo normalization ('utliztion', 'utilzation', 'utiliztion', 'utilisation', 'utilised', etc.).
3. SQL generation: Queries actual warehouse/bin data, TOP 1, sorted by utilization % descending.
4. Correct bin data: Returns the maximum utilization bin (BLINKIT at 671.1% across warehouse, or plant-scoped).
5. Output format: Single concise text by default, without returning generic plant-level responses or multi-bin lists.
6. Negative cases: Does NOT hijack multi-item rankings (e.g. 'top 10 bins'), plant-level extremes ('which plant has highest bin utilization'), or detailed comparisons.
"""

import pytest
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    is_highest_bin_utilization_intent,
    format_deterministic_answer,
    optimize_response_format,
    normalize_query_typos
)
from backend.app.db import execute_readonly


EQUIVALENT_QUERIES = [
    "Which bin is holding the highest bin utilization?",
    "Highest utilization bin",
    "Which bin has highest utilization?",
    "Which bin has the highest utilization?",
    "Show me the highest utilized bin",
    "Which is the most utilized bin?",
    "Find the bin with maximum utilization",
    "Which bin has maximum utilization?",
    "Show the bin with the highest bin utilization",
    "What is the highest utilized bin?",
    "Which bin is utilized the most?",
    "Bin with the highest utilization percentage",
    "Highest utilization % bin",
    "Which bin has the highest utilization %?",
]

TYPO_QUERIES = [
    "highest utliztion bin",
    "which bin has highest utliztion",
    "which bin has highest utilzation",
    "which bin has highest utiliztion",
    "which bin has highest utilisation",
    "show me the most utilised bin",
    "which bin is holding the highest bin utliztion",
]


@pytest.mark.parametrize("q", EQUIVALENT_QUERIES)
def test_equivalent_queries_intent_and_sql(q):
    assert is_highest_bin_utilization_intent(q) is True, f"Failed helper check: {q}"
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "HIGHEST_BIN_UTILIZATION"
    assert "TOP 1" in res.get("sql", "")
    assert "ORDER BY SUM(i.UnrestrictedQty" in res.get("sql", "")
    assert "DESC" in res.get("sql", "")
    assert res.get("output_type") == "text"


@pytest.mark.parametrize("q", TYPO_QUERIES)
def test_typo_queries_intent_and_sql(q):
    assert is_highest_bin_utilization_intent(q) is True, f"Failed typo check: {q}"
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "HIGHEST_BIN_UTILIZATION"
    assert "TOP 1" in res.get("sql", "")
    assert res.get("output_type") == "text"


def test_plant_scoped_highest_bin_utilization():
    q = "Which bin has the highest utilization in plant 1266?"
    assert is_highest_bin_utilization_intent(q) is True
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "HIGHEST_BIN_UTILIZATION"
    assert "b.Plant = '1266'" in res.get("sql", "")
    
    rows, _ = execute_readonly(res["sql"])
    assert len(rows) == 1
    assert rows[0]["Bin"] == "S105310111"
    assert "152.4%" in str(rows[0]["Utilization %"])


def test_db_execution_and_answer_formatting():
    q = "Which bin is holding the highest bin utilization?"
    res = deterministic_warehouse_sql_generator(q)
    rows, _ = execute_readonly(res["sql"])
    assert len(rows) == 1
    assert rows[0]["Bin"] == "BLINKIT"
    assert "671.1%" in str(rows[0]["Utilization %"])
    
    ans = format_deterministic_answer(q, rows)
    assert "BLINKIT" in ans
    assert "671.1%" in ans
    assert "highest utilization" in ans.lower()
    
    # Test response optimization
    opt = optimize_response_format(q, rows, res)
    assert opt.get("intent") == "HIGHEST_BIN_UTILIZATION"
    assert opt.get("output_type") == "text"


def test_explicit_table_request():
    q = "Show me the highest utilization bin in a table"
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("intent") == "HIGHEST_BIN_UTILIZATION"
    assert res.get("output_type") == "table"
    rows, _ = execute_readonly(res["sql"])
    ans = format_deterministic_answer(q, rows)
    assert "| Bin | Plant |" in ans
    assert "BLINKIT" in ans


def test_negative_cases_not_hijacked():
    # 1. Multi-item ranking (should NOT be HIGHEST_BIN_UTILIZATION)
    q1 = "Top 10 most utilized bins"
    assert is_highest_bin_utilization_intent(q1) is False
    res1 = deterministic_warehouse_sql_generator(q1)
    assert res1.get("intent") != "HIGHEST_BIN_UTILIZATION"
    assert "TOP 10" in res1.get("sql", "")

    # 2. Plant-level extreme (asking which plant, NOT which bin)
    q2 = "Which plant has the highest bin utilization?"
    assert is_highest_bin_utilization_intent(q2) is False
    res2 = deterministic_warehouse_sql_generator(q2)
    assert res2.get("intent") == "highest_bin_utilization"  # Plant-level intent
    assert "b.Plant" in res2.get("sql", "")

    # 3. Multi-plant detailed comparison
    q3 = "Compare the bin utilization of both Plant 1268 and 7228 in detail"
    assert is_highest_bin_utilization_intent(q3) is False
    res3 = deterministic_warehouse_sql_generator(q3)
    assert res3.get("intent") == "multi_plant_bin_detail"
