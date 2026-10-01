"""Unit and integration tests for Material Volume Share query and response format."""

import pytest
from backend.app.llm import deterministic_warehouse_sql_generator, format_deterministic_answer, optimize_response_format
from backend.app.db import execute_readonly

def test_material_volume_share_generation():
    questions = [
        "Which materials are consuming the highest percentage of our total bin volume?",
        "Top 10 materials by share of total bin volume",
        "Which materials occupy the most volume in the warehouse?",
        "Top materials consuming warehouse bin volume"
    ]
    for q in questions:
        gen = deterministic_warehouse_sql_generator(q)
        assert gen["intent"] == "material_volume_share"
        assert gen["metric"] == "bin_volume_consumption"
        assert gen["output_type"] == "bar_chart"
        assert gen["chart_type"] == "bar"
        assert gen["chart_x"] == "Material"
        assert "Rank" in gen["sql"]
        assert "Total Material Volume" in gen["sql"]
        assert "% of Total Bin Volume" in gen["sql"]

def test_material_volume_share_execution_and_format():
    gen = deterministic_warehouse_sql_generator("Which materials are consuming the highest percentage of our total bin volume?")
    rows, elapsed = execute_readonly(gen["sql"])
    
    assert isinstance(rows, list)
    assert len(rows) > 0
    first = rows[0]
    
    # Assert exact required columns from image
    assert "Rank" in first
    assert "Material" in first
    assert "Material Description" in first
    assert "Total Quantity" in first
    assert "Total Material Volume" in first
    assert "% of Total Bin Volume" in first
    
    # Assert top leader is BKE15LSSB28
    assert first["Material"] == "BKE15LSSB28"
    assert "RIO 1 5L KETTLE" in first["Material Description"]
    
    # Test answer format
    answer = format_deterministic_answer("Which materials are consuming the highest percentage of our total bin volume?", rows)
    assert "Top 10 Materials by Share of Total Bin Volume" in answer
    assert "The following materials consume the highest percentage of the warehouse's total bin volume" in answer
    assert "BKE15LSSB28" in answer
    
    # Test optimize format
    opt = optimize_response_format("Which materials are consuming the highest percentage of our total bin volume?", rows, gen)
    assert opt["output_type"] == "bar_chart"
    assert opt["chart_type"] == "bar"
    assert opt["chart_x"] == "Material"
