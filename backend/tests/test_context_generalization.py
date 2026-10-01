"""Comprehensive tests verifying Context-Based Semantic Understanding across varied paraphrasing."""

import pytest
from backend.app.llm import deterministic_warehouse_sql_generator, format_deterministic_answer, optimize_response_format
from backend.app.db import execute_readonly

def test_material_volume_share_paraphrased():
    variations = [
        "Which materials are consuming the highest percentage of our total bin volume?",
        "Which products take up the highest proportion of bin cubic capacity?",
        "Show me the SKUs with the largest volume footprint across the warehouse",
        "Which items occupy the biggest share of storage space in the facility?",
        "Top 10 goods by percentage of total warehouse volume",
        "Which SKUs take up the most room in the warehouse bins?"
    ]
    for q in variations:
        gen = deterministic_warehouse_sql_generator(q)
        assert gen["intent"] == "material_volume_share", f"Failed for question: {q}"
        assert gen["output_type"] == "bar_chart"
        assert gen["chart_type"] == "bar"
        assert "Rank" in gen["sql"]
        assert "% of Total Bin Volume" in gen["sql"]
        assert "Total Material Volume" in gen["sql"]

def test_data_quality_missing_dimensions_paraphrased():
    variations = [
        "Which inventory materials don't have dimensions?",
        "Which items are missing their physical measurements?",
        "Are there any stock items without length and width populated in the master?",
        "List SKUs where dimension data is absent",
        "Data quality exception check for material size and cubic volume",
        "Find materials lacking length, width or height attributes"
    ]
    for q in variations:
        gen = deterministic_warehouse_sql_generator(q)
        assert gen["intent"] == "data_quality_check", f"Failed for question: {q}"
        assert gen["metric"] == "missing_dimensions"
        assert gen["output_type"] == "table"
        assert "Quality Issue" in gen["sql"]
        assert "Missing Volume Master Record" in gen["sql"]

def test_putaway_available_bins_paraphrased():
    variations = [
        "Where can I place incoming stock right now without displacing existing inventory?",
        "Where can we store new products right now without moving anything?",
        "Show me completely vacant storage positions",
        "Which locations have a balance of zero and can accept incoming freight?",
        "List empty bins ready for put-away"
    ]
    for q in variations:
        gen = deterministic_warehouse_sql_generator(q)
        assert gen["intent"] == "putaway_bins", f"Failed for question: {q}"
        assert gen["output_type"] == "table"
        assert "UnrestrictedQty = 0" in gen["sql"] or "i.BinNo IS NULL" in gen["sql"]

def test_average_inventory_per_bin_paraphrased():
    variations = [
        "What is the average inventory per occupied bin?",
        "What is the mean quantity held per active bin?",
        "On average how many stock units are stored inside each occupied location?",
        "Average units per bin across the warehouse"
    ]
    for q in variations:
        gen = deterministic_warehouse_sql_generator(q)
        assert gen["intent"] == "avg_inventory_per_bin", f"Failed for question: {q}"
        assert gen["output_type"] == "kpi"
        assert "AvgInventoryPerOccupiedBin" in gen["sql"]

def test_bin_rankings_paraphrased():
    variations_both = [
        "List the top 10 most utilized bins and the top 10 least utilized bins.",
        "Find the 10 fullest bins and the 10 emptiest bins in our storage network",
        "Highest 10 and lowest 10 locations by capacity usage"
    ]
    for q in variations_both:
        gen = deterministic_warehouse_sql_generator(q)
        assert gen["intent"] == "top_and_bottom_bins", f"Failed for question: {q}"
        assert "TopBins" in gen["sql"]
        assert "BottomBins" in gen["sql"]
        assert "Ranking Group" in gen["sql"]
