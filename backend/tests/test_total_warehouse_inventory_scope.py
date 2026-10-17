"""Regression tests for warehouse-wide inventory scope and result completeness."""

import asyncio
import re

from backend.app.llm import generate_sql


def test_total_warehouse_inventory_is_unscoped_aggregate():
    generated = asyncio.run(generate_sql("Total warehouse inventory", history=[]))
    sql = generated["sql"].lower()

    assert "sum(unrestrictedqty)" in sql
    assert "from dbo.zwms_inventory" in sql
    assert "where plant" not in sql
    assert "group by plant" not in sql
    assert "top " not in sql
    assert not re.search(r"\\blimit\\s+\\d+", sql)
    assert generated["query_plan"]["scope"] == "ALL_WAREHOUSE"
    assert generated["query_plan"]["plant"] is None
    assert generated["filters"] == {}
    assert generated["output_type"] == "text"


def test_explicit_plant_scope_is_not_overridden_as_global():
    generated = asyncio.run(generate_sql("Total warehouse inventory for Plant 1258", history=[]))
    sql = generated["sql"].lower()

    assert "where plant = '1258'" in sql
    assert generated["filters"].get("plant") == "1258"



def test_zero_aggregate_is_not_treated_as_no_matching_records():
    from backend.app.llm import format_deterministic_answer

    answer = format_deterministic_answer("Total inventory for Plant 1258", [{
        "total_inventory": 0,
        "Total Unrestricted Quantity": 0,
        "TotalUniqueMaterials": 0,
        "TotalActiveBins": 0,
        "PlantCount": 1,
    }])

    assert answer != "No matching warehouse records were found for your query in the database."
