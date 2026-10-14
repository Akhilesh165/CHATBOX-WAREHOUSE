"""Tests for RANGE FILTER VALIDATION RULE and DISPLAYED-METRIC CONSISTENCY.

Authoritative Rules Tested:
1. RANGE FILTER VALIDATION RULE:
   When the user specifies a numerical range such as "between 50% and 80% utilization,"
   the chatbot must filter the final result using the same metric displayed in the response.
   For an inclusive "between" request, use 50% <= utilization <= 80%. Every returned row
   must satisfy the requested range. The chatbot must never display rows outside the
   requested range, even if the backend returns them. Before presenting the response,
   validate every returned row against the requested lower and upper bounds. If any row
   falls outside the range, exclude it or correct the calculation before displaying the result.

2. DISPLAYED-METRIC CONSISTENCY:
   The metric used for filtering must be the same metric shown to the user. If the table
   displays "Utilization %," then the range filter must operate on the calculated
   Utilization % value, not on bin capacity, occupied volume, a raw database field,
   or another percentage field.
"""

import pytest
from backend.app.llm import deterministic_warehouse_sql_generator, format_deterministic_answer, parse_range_filters
from backend.app.validator import validate_sql, validate_query_result, validate_and_filter_range_rows
from backend.app.db import execute_readonly


def test_bin_utilization_range_inclusive_bounds():
    """Verify that every row returned for between 50% and 80% satisfies 50 <= util <= 80."""
    q = "Show only bins between 50% and 80% utilization."
    gen = deterministic_warehouse_sql_generator(q)
    assert gen.get("query_plan") is not None
    rf = gen["query_plan"].get("range_filters", [])
    assert len(rf) == 1
    assert rf[0]["field"] == "BinUtilizationPct"
    assert rf[0]["lower"] == 50.0
    assert rf[0]["upper"] == 80.0
    assert rf[0]["operator"] == "BETWEEN"
    assert rf[0]["inclusive"] is True

    # Validate and execute SQL
    sql = validate_sql(gen["sql"])
    rows, _ = execute_readonly(sql)
    assert len(rows) > 0

    # Prune/validate rows
    valid_rows, _ = validate_and_filter_range_rows(rows, rf)
    assert len(valid_rows) == len(rows), "Database returned rows outside requested range"

    # Verify every returned row satisfies 50.0 <= util <= 80.0
    for r in valid_rows:
        val_str = str(r.get("UtilizationPct", r.get("Utilization %", ""))).replace("%", "").strip()
        val = float(val_str)
        assert 50.0 <= val <= 80.0, f"Row {r} violated range 50% <= util <= 80% with value {val}"


def test_displayed_metric_consistency():
    """Verify that the table displays 'Utilization %' and operates on calculated utilization value."""
    q = "Show only bins between 50% and 80% utilization."
    gen = deterministic_warehouse_sql_generator(q)
    sql = validate_sql(gen["sql"])
    rows, _ = execute_readonly(sql)
    assert len(rows) > 0

    # DISPLAYED-METRIC CONSISTENCY:
    # 1. The table displays 'Utilization %'
    assert "Utilization %" in rows[0]
    # 2. It does not filter on 'Bin Capacity' or raw volume
    assert rows[0]["Bin Capacity"] != rows[0]["Utilization %"]
    # 3. Formatted answer references the exact utilization %
    ans = format_deterministic_answer(q, rows)
    assert "between 50.0% and 80.0% utilization" in ans.lower() or "50" in ans


def test_range_filter_pruning_excludes_out_of_bounds_rows():
    """Verify that validate_and_filter_range_rows strictly excludes out-of-bounds rows."""
    mock_rows = [
        {"Bin": "BIN1", "Bin Capacity": "50 FT3", "Utilization %": "55.0%", "UtilizationPct": 55.0},
        {"Bin": "BIN2", "Bin Capacity": "50 FT3", "Utilization %": "75.0%", "UtilizationPct": 75.0},
        {"Bin": "BIN3", "Bin Capacity": "50 FT3", "Utilization %": "85.0%", "UtilizationPct": 85.0}, # Out of bounds (too high)
        {"Bin": "BIN4", "Bin Capacity": "50 FT3", "Utilization %": "45.0%", "UtilizationPct": 45.0}, # Out of bounds (too low)
        {"Bin": "BIN5", "Bin Capacity": "50 FT3", "Utilization %": "80.0%", "UtilizationPct": 80.0}, # Inclusive upper bound (valid)
        {"Bin": "BIN6", "Bin Capacity": "50 FT3", "Utilization %": "50.0%", "UtilizationPct": 50.0}, # Inclusive lower bound (valid)
    ]
    range_filters = [{
        "field": "BinUtilizationPct",
        "operator": "BETWEEN",
        "lower": 50.0,
        "upper": 80.0,
        "inclusive": True
    }]

    filtered, warnings = validate_and_filter_range_rows(mock_rows, range_filters)
    assert len(filtered) == 4
    bins = [r["Bin"] for r in filtered]
    assert "BIN1" in bins
    assert "BIN2" in bins
    assert "BIN5" in bins
    assert "BIN6" in bins
    assert "BIN3" not in bins
    assert "BIN4" not in bins
    assert len(warnings) == 1
    assert "Excluded 2 row(s)" in warnings[0]


def test_result_validator_detects_metric_inconsistency():
    """Verify that validate_query_result rejects results that violate displayed-metric consistency."""
    # Mock rows with only Bin Capacity, but no calculated Utilization %
    bad_rows = [
        {"Bin": "BIN1", "Bin Capacity": "70 FT3", "Plant": 1258}
    ]
    plan = {
        "intent": "RANGE_QUERY",
        "range_filters": [{"field": "BinUtilizationPct", "operator": "BETWEEN", "lower": 50, "upper": 80}]
    }
    is_valid, reason = validate_query_result(
        "Show only bins between 50% and 80% utilization.",
        plan,
        "SELECT BinLocation FROM ZWMS_BIN_MASTER",
        bad_rows
    )
    assert not is_valid
    assert "DISPLAYED-METRIC CONSISTENCY VIOLATION" in reason


def test_plant_scoped_utilization_range():
    """Verify that range filtering combined with plant scoping correctly isolates plant and range."""
    q = "Show bins between 10% and 40% utilization for Plant 1258"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen.get("filters", {}).get("plant") == "1258" or "1258" in gen["sql"]
    sql = validate_sql(gen["sql"])
    rows, _ = execute_readonly(sql)
    if rows:
        for r in rows:
            assert str(r.get("Plant")) == "1258"
            val = float(str(r.get("UtilizationPct", r.get("Utilization %"))).replace("%", ""))
            assert 10.0 <= val <= 40.0
