import pytest
from backend.app.llm import deterministic_warehouse_sql_generator, format_deterministic_answer, optimize_response_format
from backend.app.db import execute_readonly

def test_top_and_bottom_bins_combined_query():
    q = "List the top 10 most utilized bins and the top 10 least utilized bins."
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "top_and_bottom_bins"
    assert gen["output_type"] == "table"
    assert "Top 10 Most Utilized" in gen["sql"]
    assert "Bottom 10 Least Utilized" in gen["sql"]

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 20
    assert "Ranking Group" in rows[0]
    assert "Bin" in rows[0]
    assert "Bin Capacity" in rows[0]
    assert "Utilization %" in rows[0]

    ans = format_deterministic_answer(q, rows)
    assert "Top 10 Most Utilized Bins" in ans
    assert "Bottom 10 Least Utilized Bins" in ans

    opt = optimize_response_format(q, rows, gen)
    assert opt["output_type"] == "table"

def test_top_n_most_utilized_bins_query():
    q = "top 10 most utilized bins"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "top_utilized_bins"
    assert gen["output_type"] == "table"
    assert "DESC" in gen["sql"]

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 10
    assert "Bin" in rows[0]
    assert "Bin Capacity" in rows[0]
    assert "Utilization %" in rows[0]

def test_bottom_n_least_utilized_bins_query():
    q = "bottom 10 least utilized bins"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "least_utilized_bins"
    assert gen["output_type"] == "table"
    assert "ASC" in gen["sql"]

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 10
    assert "Bin" in rows[0]
    assert "Bin Capacity" in rows[0]
    assert "Utilization %" in rows[0]
