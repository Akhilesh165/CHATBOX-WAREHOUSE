import pytest
from backend.app.llm import deterministic_warehouse_sql_generator, format_deterministic_answer, optimize_response_format
from backend.app.db import execute_readonly

def test_average_inventory_per_occupied_bin():
    queries = [
        "What is the average inventory per occupied bin?",
        "avg inventory per occupied bin",
        "average stock per bin",
        "average units per occupied bin in plant 1258"
    ]
    for q in queries:
        gen = deterministic_warehouse_sql_generator(q)
        assert gen["intent"] == "avg_inventory_per_bin"
        assert gen["output_type"] == "kpi"
        assert "AvgInventoryPerOccupiedBin" in gen["sql"]
        assert "UnrestrictedQty > 0" in gen["sql"]

        rows, _ = execute_readonly(gen["sql"])
        assert len(rows) == 1
        assert "AvgInventoryPerOccupiedBin" in rows[0]
        assert rows[0]["AvgInventoryPerOccupiedBin"] > 0

        ans = format_deterministic_answer(q, rows)
        assert "average inventory per occupied bin" in ans.lower()

        opt = optimize_response_format(q, rows, gen)
        assert opt["output_type"] == "kpi"

def test_empty_bins_semantic_rule():
    q = "Which bins are empty?"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "putaway_bins"
    assert gen["output_type"] == "table"
    assert "UnrestrictedQty = 0" in gen["sql"] or "BinNo IS NULL" in gen["sql"]

def test_warehouse_utilization_semantic_rule():
    q = "What is the overall warehouse bin utilization percentage?"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "bin_utilization"
    assert "BinUtilizationPct" in gen["sql"]
    assert "VolumeUtilizationPct" in gen["sql"]

def test_top_materials_volume_consumption_semantic_rule():
    q = "Which materials are consuming the highest percentage of total bin volume?"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] in ["material_volume", "material_volume_share"]
    assert "% of Total Bin Volume" in gen["sql"] or "PctOfTotalWarehouseBinVolume" in gen["sql"]
    assert "Total Material Volume" in gen["sql"] or "ConsumedMaterialVolume" in gen["sql"]

def test_output_selection_rules():
    # 1. KPI
    q_kpi = "What is our total warehouse inventory quantity?"
    gen_kpi = deterministic_warehouse_sql_generator(q_kpi)
    assert gen_kpi["output_type"] == "kpi"

    # 2. Table for list/show
    q_table = "Show me materials of plant 1258"
    gen_table = deterministic_warehouse_sql_generator(q_table)
    assert gen_table["output_type"] == "table"

    # 3. Line chart for trend over time
    q_line = "Show warehouse trend over time for last 6 months"
    gen_line = deterministic_warehouse_sql_generator(q_line)
    assert gen_line["output_type"] == "line_chart"
    assert gen_line["chart_type"] == "line"

    # 4. Pie chart for division breakdown
    q_pie = "Show inventory distribution by material division"
    gen_pie = deterministic_warehouse_sql_generator(q_pie)
    assert gen_pie["output_type"] == "pie_chart"
    assert gen_pie["chart_type"] == "pie"
