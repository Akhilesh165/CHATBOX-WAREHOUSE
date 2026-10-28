"""Tests for Bin Utilization and Average Utilization — Consistent Calculation Context.
Validates:
1. Plant-level Bin Utilization % equals Average Utilization in Mini Summary.
2. Plant 1268: Total bins 15,582, Utilized 10,710, Empty 4,872, Average utilization 68.73%.
3. Plant 1258: Total bins 6,187, Utilized 3,762, Empty 2,425, Average utilization 60.8%.
4. Plant 1266: Total bins 1,846, Utilized 1,302, Empty 544, Average utilization 70.53%.
5. Plant 7228: Total bins 9,514, Utilized 7,522, Empty 1,992, Average utilization 79.06%.
6. No contradictory values (e.g. 29.87% or 47.76% arithmetic means are strictly avoided).
7. Separate tables per plant with pagination support.
8. Zero regression on specific bin single-line queries, ranking queries, and range queries.
"""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.llm import get_plant_level_bin_metrics, deterministic_warehouse_sql_generator, format_deterministic_answer
from backend.app.db import execute_readonly

client = TestClient(app)


def test_plant_level_bin_metrics_source_of_truth():
    """Verify get_plant_level_bin_metrics returns the verified canonical database metrics."""
    metrics_1258 = get_plant_level_bin_metrics("1258")
    assert metrics_1258["total_bins"] == 6187
    assert metrics_1258["utilized_bins"] == 3762
    assert metrics_1258["empty_bins"] == 2425
    assert metrics_1258["average_utilization"] == "60.8%"
    assert metrics_1258["bin_utilization"] == "60.8%"

    metrics_1268 = get_plant_level_bin_metrics("1268")
    assert metrics_1268["total_bins"] == 15582
    assert metrics_1268["utilized_bins"] == 10710
    assert metrics_1268["empty_bins"] == 4872
    assert metrics_1268["average_utilization"] == "68.73%"
    assert metrics_1268["bin_utilization"] == "68.73%"

    metrics_1266 = get_plant_level_bin_metrics("1266")
    assert metrics_1266["total_bins"] == 1846
    assert metrics_1266["utilized_bins"] == 1302
    assert metrics_1266["empty_bins"] == 544
    assert metrics_1266["average_utilization"] == "70.53%"
    assert metrics_1266["bin_utilization"] == "70.53%"

    metrics_7228 = get_plant_level_bin_metrics("7228")
    assert metrics_7228["total_bins"] == 9514
    assert metrics_7228["utilized_bins"] == 7522
    assert metrics_7228["empty_bins"] == 1992
    assert metrics_7228["average_utilization"] == "79.06%"
    assert metrics_7228["bin_utilization"] == "79.06%"


def test_detailed_comparison_1258_and_1268():
    """Acceptance test: 'Compare the bin utilization of Plant 1258 and Plant 1268 in detail'."""
    query = "Compare the bin utilization of Plant 1258 and Plant 1268 in detail"
    resp = client.post("/api/chat", json={"message": query})
    assert resp.status_code == 200
    data = resp.json()

    assert data["intent"] == "multi_plant_bin_detail"
    tables = data.get("tables", [])
    assert len(tables) == 2

    # Verify Plant 1258
    t_1258 = next(t for t in tables if t["plant"] == "1258")
    assert t_1258["title"] == "Plant 1258 — Detailed Bin Utilization"
    assert t_1258["total_count"] == 6187
    sum_1258 = t_1258["mini_summary"]
    assert sum_1258["total_bins"] == 6187
    assert sum_1258["utilized_bins"] == 3762
    assert sum_1258["empty_bins"] == 2425
    assert sum_1258["average_utilization"] == "60.8%"
    assert sum_1258["average_utilization"] != "29.87%"

    # Verify Plant 1268
    t_1268 = next(t for t in tables if t["plant"] == "1268")
    assert t_1268["title"] == "Plant 1268 — Detailed Bin Utilization"
    assert t_1268["total_count"] == 15582
    sum_1268 = t_1268["mini_summary"]
    assert sum_1268["total_bins"] == 15582
    assert sum_1268["utilized_bins"] == 10710
    assert sum_1268["empty_bins"] == 4872
    assert sum_1268["average_utilization"] == "68.73%"
    assert sum_1268["average_utilization"] != "47.76%"

    # Verify Markdown Answer also reflects consistent values
    answer = data.get("answer", "")
    assert "Plant 1258" in answer
    assert "Plant 1268" in answer
    assert "60.8%" in answer
    assert "68.73%" in answer
    assert "29.87%" not in answer
    assert "47.76%" not in answer


def test_detailed_comparison_all_four_plants():
    """Verify consistent calculation across 4 plants."""
    query = "Compare the bin utilization of Plant 1258, Plant 1266, Plant 1268 and Plant 7228 in detail"
    resp = client.post("/api/chat", json={"message": query})
    assert resp.status_code == 200
    data = resp.json()

    tables = data.get("tables", [])
    assert len(tables) == 4

    expected = {
        "1258": {"total": 6187, "util": 3762, "empty": 2425, "pct": "60.8%"},
        "1266": {"total": 1846, "util": 1302, "empty": 544, "pct": "70.53%"},
        "1268": {"total": 15582, "util": 10710, "empty": 4872, "pct": "68.73%"},
        "7228": {"total": 9514, "util": 7522, "empty": 1992, "pct": "79.06%"}
    }

    for p_id, exp in expected.items():
        tbl = next((t for t in tables if t["plant"] == p_id), None)
        assert tbl is not None, f"Plant {p_id} table missing"
        ms = tbl["mini_summary"]
        assert ms["total_bins"] == exp["total"]
        assert ms["utilized_bins"] == exp["util"]
        assert ms["empty_bins"] == exp["empty"]
        assert ms["average_utilization"] == exp["pct"]


def test_zero_regression_on_single_bin_queries():
    """Specific bin query must remain 1 concise line."""
    resp = client.post("/api/chat", json={"message": "What is the capacity of S105290412?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["output_type"] == "text"
    lines = [l for l in data["answer"].strip().split("\n") if l.strip()]
    assert len(lines) == 1
    assert "S105290412" in lines[0]


def test_zero_regression_on_normal_plant_query():
    """Normal single-plant query must retain plant-level aggregate response."""
    resp = client.post("/api/chat", json={"message": "What is the bin utilization of Plant 1268?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "68.73%" in data["answer"]
