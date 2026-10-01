import pytest
import asyncio
from backend.app.llm import deterministic_warehouse_sql_generator, format_deterministic_answer, optimize_response_format
from backend.app.db import execute_readonly

@pytest.mark.parametrize("query,expected_thresh,expected_op", [
    ("Which bins are more than 90% full?", 90.0, ">="),
    ("which bins are > 90% full", 90.0, ">="),
    ("bins over 80% full", 80.0, ">="),
    ("bins greater than 75% capacity", 75.0, ">="),
    ("show me bins with utilization above 90%", 90.0, ">="),
    ("which bins are 90% full", 90.0, ">="),
    ("which storage locations are more than 85% occupied", 85.0, ">="),
    ("bins over 95% full in plant 1258", 95.0, ">="),
    ("bins less than 50% full", 50.0, "<="),
    ("bins below 30% utilization", 30.0, "<="),
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
    # Check that ONLY the 3 required columns are returned: Bin, Bin Capacity, Utilization %
    assert set(first.keys()) == {"Bin", "Bin Capacity", "Utilization %"}
    assert "Material" not in first
    assert "Plant" not in first
    assert "StorageLocation" not in first
    assert "Batch" not in first
    assert "Occupied Volume" not in first

    ans = format_deterministic_answer(q, rows)
    assert "more than 90% utilization" in ans
    assert "Utilization % > 90" in ans or "Utilization %" in ans

def test_bin_fullness_less_than_execution():
    q = "Which bins are less than 90% full?"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "low_utilization_bins"
    rows, _ = execute_readonly(gen["sql"])
    
    assert len(rows) > 0
    first = rows[0]
    assert set(first.keys()) == {"Bin", "Bin Capacity", "Utilization %"}
    assert "Material" not in first

    ans = format_deterministic_answer(q, rows)
    assert "less than 90% utilization" in ans
    assert "Utilization % < 90" in ans or "Utilization %" in ans
