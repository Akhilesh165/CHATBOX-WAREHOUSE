import pytest
import asyncio
from backend.app.llm import deterministic_warehouse_sql_generator, format_deterministic_answer, optimize_response_format
from backend.app.db import execute_readonly

@pytest.mark.parametrize("query,expected_thresh,expected_op", [
    ("Which bins are more than 90% full?", 90.0, ">"),
    ("which bins are > 90% full", 90.0, ">"),
    ("bins over 80% full", 80.0, ">"),
    ("bins greater than 75% capacity", 75.0, ">"),
    ("show me bins with utilization above 90%", 90.0, ">"),
    ("which bins are 90% full", 90.0, ">"),
    ("which storage locations are more than 85% occupied", 85.0, ">"),
    ("bins over 95% full in plant 1258", 95.0, ">"),
    ("bins less than 50% full", 50.0, "<"),
    ("bins below 30% utilization", 30.0, "<"),
    ("bins at least 80% full", 80.0, ">="),
    ("bins at most 25% full", 25.0, "<="),
])
def test_bin_fullness_threshold_generator(query, expected_thresh, expected_op):
    gen = deterministic_warehouse_sql_generator(query)
    assert gen["intent"] in ["high_utilization_bins", "low_utilization_bins"]
    assert gen["output_type"] == "table"
    assert gen["chart_type"] == "none"
    assert "Bin Capacity" in gen["sql"]
    assert "Utilization %" in gen["sql"]
    assert str(int(expected_thresh)) in gen["sql"]
    assert expected_op in gen["sql"]

def test_bin_fullness_more_than_execution():
    q = "Which bins are more than 90% full?"
    gen = deterministic_warehouse_sql_generator(q)
    rows, _ = execute_readonly(gen["sql"])
    
    assert len(rows) > 0
    first = rows[0]
    # Check that required columns are returned: Bin, Plant, Bin Capacity, Occupied Volume, Utilization %
    assert set(first.keys()) == {"Bin", "Plant", "Bin Capacity", "Occupied Volume", "Utilization %"}
    assert "Material" not in first
    assert "StorageLocation" not in first
    assert "Batch" not in first

    ans = format_deterministic_answer(q, rows)
    assert "utilization" in ans.lower()
    assert "> 90" in ans or "90%" in ans

def test_bin_fullness_less_than_execution():
    q = "Which bins are less than 90% full?"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "low_utilization_bins"
    rows, _ = execute_readonly(gen["sql"])
    
    assert len(rows) > 0
    first = rows[0]
    assert set(first.keys()) == {"Bin", "Plant", "Bin Capacity", "Occupied Volume", "Utilization %"}
    assert "Material" not in first

    ans = format_deterministic_answer(q, rows)
    assert "utilization" in ans.lower()
    assert "< 90" in ans or "90%" in ans

# ==============================================================================
# PART C — Regression tests
# ==============================================================================

def test_regression_1_show_bins_above_80_plant_7228_and_1268():
    """Show bins above 80% utilization in Plant 7228 and 1268:
    SQL contains IN ('7228', '1268'), operator is > 80 (not >=), result has a Plant column, answer names both plants.
    """
    q = "Show bins above 80% utilization in Plant 7228 and 1268"
    gen = deterministic_warehouse_sql_generator(q)
    assert "IN ('7228', '1268')" in gen["sql"]
    assert "> 80" in gen["sql"]
    assert ">= 80" not in gen["sql"]
    
    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) > 0
    assert "Plant" in rows[0]
    assert set(rows[0].keys()) == {"Bin", "Plant", "Bin Capacity", "Occupied Volume", "Utilization %"}

    ans = format_deterministic_answer(q, rows)
    assert "7228" in ans
    assert "1268" in ans
    assert "> 80%" in ans

def test_regression_2_show_bins_above_80_plants_1258_1266_7228():
    """Show bins above 80% in plants 1258, 1266 and 7228:
    IN with all three plants.
    """
    q = "Show bins above 80% in plants 1258, 1266 and 7228"
    gen = deterministic_warehouse_sql_generator(q)
    assert "IN ('1258', '1266', '7228')" in gen["sql"]
    assert "> 80" in gen["sql"]

def test_regression_3_show_bins_above_80_plant_1258_or_7228():
    """Show bins above 80% in Plant 1258 or Plant 7228:
    IN ('1258','7228').
    """
    q = "Show bins above 80% in Plant 1258 or Plant 7228"
    gen = deterministic_warehouse_sql_generator(q)
    assert "IN ('1258', '7228')" in gen["sql"]
    assert "> 80" in gen["sql"]

def test_regression_4_show_bins_above_80_plant_7228():
    """Show bins above 80% in Plant 7228:
    still = '7228' (no regression).
    """
    q = "Show bins above 80% in Plant 7228"
    gen = deterministic_warehouse_sql_generator(q)
    assert "Plant = '7228'" in gen["sql"]
    assert "> 80" in gen["sql"]

def test_regression_5_show_bins_at_least_80_plant_7228_and_1268():
    """Show bins at least 80% utilization in Plant 7228 and 1268:
    operator >= 80.
    """
    q = "Show bins at least 80% utilization in Plant 7228 and 1268"
    gen = deterministic_warehouse_sql_generator(q)
    assert "IN ('7228', '1268')" in gen["sql"]
    assert ">= 80" in gen["sql"]

def test_regression_6_how_many_bins_above_80_plant_7228_and_1268():
    """How many bins are above 80% in Plant 7228 and 1268?
    count query over both plants with per-plant split.
    """
    q = "How many bins are above 80% in Plant 7228 and 1268?"
    gen = deterministic_warehouse_sql_generator(q)
    assert "Threshold Bins Count" in gen["sql"]
    assert "IN ('7228', '1268')" in gen["sql"]
    assert "GROUP BY Plant" in gen["sql"]

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) > 0
    ans = format_deterministic_answer(q, rows)
    assert "7228" in ans
    assert "1268" in ans
    assert "> 80%" in ans
    # Check that per-plant split is present
    assert "7228:" in ans or "1268:" in ans

def test_regression_7_bins_above_80_in_2026():
    """Bins above 80% in 2026:
    no plant filter (year is not a plant).
    """
    q = "Bins above 80% in 2026"
    gen = deterministic_warehouse_sql_generator(q)
    assert "b.Plant = '" not in gen["sql"]
    assert "b.Plant IN" not in gen["sql"]
    assert "2026" not in gen["sql"]
    assert "> 80" in gen["sql"]

def test_regression_8_show_bins_below_20_plant_7228_and_1268():
    """Show bins below 20% utilization in Plant 7228 and 1268:
    operator < 20, ASC order.
    """
    q = "Show bins below 20% utilization in Plant 7228 and 1268"
    gen = deterministic_warehouse_sql_generator(q)
    assert "IN ('7228', '1268')" in gen["sql"]
    assert "< 20" in gen["sql"]
    assert "ASC" in gen["sql"]
