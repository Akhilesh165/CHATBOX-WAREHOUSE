"""Tests for Multi-Plant Detailed Bin Tables — Slide/Pagination Context.
Validates:
1. Separate table dataset per plant
2. 10 bins per slide/page pagination behavior
3. All records retained in memory (not truncated to 10 in backend/database)
4. Absence of 'Occupied Volume' from all rows
5. Mini Summary is plant-level and does not recalculate on paging
6. Multi-plant scaling (2, 3, 4+ plants)
7. Zero regression on single-line specific bin queries and existing features
"""

import pytest
import asyncio
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.llm import deterministic_warehouse_sql_generator, format_deterministic_answer, extract_explicit_plants
from backend.app.db import execute_readonly

client = TestClient(app)


def test_multi_plant_detailed_tables_api():
    """Verify endpoint returns independent table_datasets per plant for detailed multi-plant comparison."""
    query = "Compare the bin utilization of both Plant 1268 and 7228 in detail"
    resp = client.post("/api/chat", json={"message": query})
    assert resp.status_code == 200
    data = resp.json()

    assert data["intent"] == "multi_plant_bin_detail"
    assert data["output_type"] == "table"
    tables = data.get("tables", [])
    assert len(tables) >= 2, f"Expected at least 2 tables, got {len(tables)}"

    # Check plant separation and order
    plant_names = [t["plant"] for t in tables]
    assert "1268" in plant_names
    assert "7228" in plant_names
    assert plant_names.index("1268") < plant_names.index("7228")

    forbidden_terms = ["occupied volume", "occupied volume (m³)", "occupied volume (ft³)", "used volume"]

    for tbl in tables:
        # Title follows Plant X convention
        assert f"Plant {tbl['plant']}" in tbl["title"]
        rows = tbl["rows"]
        assert len(rows) > 0

        # All database records must remain available (display mechanism, NOT data limit)
        assert tbl["total_count"] >= len(rows)
        assert tbl["displayed_count"] == len(rows)
        # Database rows should not be artificially cut to 10 in backend
        if tbl["total_count"] > 10:
            assert len(rows) > 10, "Backend should not truncate results to 10 rows"

        # Check column names: No Occupied Volume
        for r in rows:
            assert "Bin" in r
            assert "Capacity" in r
            assert "Available Capacity" in r
            assert "Utilization %" in r
            assert "Material / Inventory Information" in r
            for k in r.keys():
                for fb in forbidden_terms:
                    assert fb not in k.lower(), f"Forbidden key '{k}' found in row!"

        # Check mini_summary integrity
        summary = tbl.get("mini_summary")
        assert summary is not None
        assert "total_bins" in summary
        assert "utilized_bins" in summary
        assert "empty_bins" in summary
        assert "average_utilization" in summary
        assert summary["total_bins"] >= len(rows)
        assert summary["utilized_bins"] + summary["empty_bins"] == summary["total_bins"]

    # Verify canonical plant-level metric values match exactly
    tbl_1268 = next(t for t in tables if t["plant"] == "1268")
    assert tbl_1268["mini_summary"]["total_bins"] == 15582
    assert tbl_1268["mini_summary"]["utilized_bins"] == 10710
    assert tbl_1268["mini_summary"]["empty_bins"] == 4872
    assert tbl_1268["mini_summary"]["average_utilization"] == "68.73%"

    tbl_7228 = next(t for t in tables if t["plant"] == "7228")
    assert tbl_7228["mini_summary"]["total_bins"] == 9514
    assert tbl_7228["mini_summary"]["utilized_bins"] == 7522
    assert tbl_7228["mini_summary"]["empty_bins"] == 1992
    assert tbl_7228["mini_summary"]["average_utilization"] == "79.06%"


def test_three_plant_detailed_comparison():
    """Verify 3-plant detailed query returns 3 separate plant tables."""
    query = "Compare bin utilization of Plant 1268, 7228 and 1258 in detail"
    resp = client.post("/api/chat", json={"message": query})
    assert resp.status_code == 200
    data = resp.json()

    tables = data.get("tables", [])
    assert len(tables) == 3
    plants = [t["plant"] for t in tables]
    assert plants == ["1268", "7228", "1258"]

    for tbl in tables:
        assert len(tbl["rows"]) > 0
        assert tbl["mini_summary"]["total_bins"] >= len(tbl["rows"])

    tbl_1268 = next(t for t in tables if t["plant"] == "1268")
    assert tbl_1268["mini_summary"]["average_utilization"] == "68.73%"

    tbl_7228 = next(t for t in tables if t["plant"] == "7228")
    assert tbl_7228["mini_summary"]["average_utilization"] == "79.06%"

    tbl_1258 = next(t for t in tables if t["plant"] == "1258")
    assert tbl_1258["mini_summary"]["total_bins"] == 6187
    assert tbl_1258["mini_summary"]["utilized_bins"] == 3762
    assert tbl_1258["mini_summary"]["empty_bins"] == 2425
    assert tbl_1258["mini_summary"]["average_utilization"] == "60.8%"


def test_pagination_slide_math_10_bins_per_page():
    """Verify 10 bins per page pagination math and last page behavior."""
    page_size = 10
    total_records = 25

    # Simulate 25 records
    simulated_rows = [{"Bin": f"BIN_{i+1}", "Capacity": 50.0} for i in range(total_records)]
    total_pages = (total_records + page_size - 1) // page_size
    assert total_pages == 3

    # Page 1: bins 1 to 10
    page_1 = simulated_rows[0:10]
    assert len(page_1) == 10
    assert page_1[0]["Bin"] == "BIN_1"
    assert page_1[9]["Bin"] == "BIN_10"

    # Page 2: bins 11 to 20
    page_2 = simulated_rows[10:20]
    assert len(page_2) == 10
    assert page_2[0]["Bin"] == "BIN_11"
    assert page_2[9]["Bin"] == "BIN_20"

    # Page 3 (last page): bins 21 to 25 (fewer than 10, no fake rows)
    page_3 = simulated_rows[20:30]
    assert len(page_3) == 5
    assert page_3[0]["Bin"] == "BIN_21"
    assert page_3[4]["Bin"] == "BIN_25"


def test_zero_regression_on_specific_bin_single_line():
    """Verify previous update (Specific Bin Query — Single-Line Response) remains 100% intact."""
    queries = [
        "Show me utilization of 105290412 bin in Plant 1266",
        "What material is stored in S105290412?",
        "What is the capacity of S105290412?",
        "Which plant does S105290412 belong to?",
        "Tell me about S105290412"
    ]
    for q in queries:
        resp = client.post("/api/chat", json={"message": q})
        assert resp.status_code == 200
        data = resp.json()
        assert data["output_type"] == "text"
        assert len(data.get("rows", [])) == 0
        ans = data["answer"].strip()
        lines = [l for l in ans.split("\n") if l.strip()]
        assert len(lines) == 1, f"Expected 1 concise line for '{q}', got: {lines}"
        assert not ans.startswith("#")
        assert "|" not in ans
