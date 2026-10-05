"""Unit & Integration Tests for Data Quality Checks and Missing Physical Dimensions."""

import pytest
from backend.app.llm import deterministic_warehouse_sql_generator, format_deterministic_answer, optimize_response_format
from backend.app.db import execute_readonly

def test_data_quality_missing_dimensions_intent():
    questions = [
        "Which materials have missing physical dimensions?",
        "Check data quality for material volume",
        "List materials with incomplete dimensions",
        "Find materials missing length, width, or height",
        "Show materials with no physical dimensions",
        "Cross-dataset validation for material volume and dimensions"
    ]
    for q in questions:
        gen = deterministic_warehouse_sql_generator(q)
        assert gen["intent"] == "data_quality_check"
        assert gen["metric"] == "missing_dimensions"
        assert gen["output_type"] == "table"
        assert gen["chart_type"] == "none"
        assert "ZWMS_INVENTORY" in gen["sql"]
        assert "ZWMS_MATERIAL_MASTER" in gen["sql"]
        assert "Quality Issue" in gen["sql"]
        assert "Missing Volume Master Record" in gen["sql"]
        assert "Length" in gen["sql"]
        assert "Width" in gen["sql"]
        assert "Height" in gen["sql"]

def test_data_quality_execution_and_formatting():
    gen = deterministic_warehouse_sql_generator("Which materials have missing physical dimensions?")
    rows, elapsed = execute_readonly(gen["sql"])
    
    # Verify execution succeeds
    assert isinstance(rows, list)
    assert elapsed >= 0
    
    if rows:
        first = rows[0]
        assert "Material" in first
        assert "Quality Issue" in first
        assert "Total Stock Qty" in first
        assert "Occupied Bins" in first
        
        # Test formatting
        answer = format_deterministic_answer("Which materials have missing physical dimensions?", rows)
        assert "Data Quality Exception" in answer or "missing or incomplete physical dimensions" in answer
        assert "Data Table" in answer
        
        # Test response optimization
        opt = optimize_response_format("Which materials have missing physical dimensions?", rows, gen)
        assert opt["output_type"] == "table"
        assert opt["chart_type"] == "none"
        assert opt["intent"] == "data_quality_check"
        assert opt["metric"] == "missing_dimensions"

def test_materials_missing_from_volume_master_dq001():
    """Test Rule DQ-001: Materials in Inventory but missing from Volume Master."""
    questions = [
        "Find materials in inventory but missing from the volume master",
        "Which materials exist in Inventory Master but not Material Volume Master?",
        "Materials missing from volume master",
        "Inventory materials without volume master record",
        "Find materials in inventory not present in material volume master"
    ]
    for q in questions:
        gen = deterministic_warehouse_sql_generator(q)
        assert gen["intent"] == "materials_missing_from_volume_master"
        assert gen["output_type"] == "table"
        assert "ZWMS_INVENTORY" in gen["sql"]
        assert "ZWMS_MATERIAL_MASTER" in gen["sql"]
        assert "v.MaterialCode IS NULL" in gen["sql"]
        assert "Storage Location" in gen["sql"]
        assert "Inventory Qty" in gen["sql"]

        plan = gen.get("query_plan", {})
        assert plan.get("intent") == "MATERIALS_MISSING_FROM_VOLUME_MASTER"
        assert plan.get("task_type") == "CROSS_TABLE_VALIDATION"
        assert plan.get("entity") == "MATERIAL"
        assert plan.get("condition") == "NO_MATCHING_VOLUME_MASTER_RECORD"

    # Execution check
    rows, elapsed = execute_readonly(gen["sql"])
    assert isinstance(rows, list)
    if rows:
        first = rows[0]
        assert "Material" in first
        assert "Storage Location" in first
        assert "Inventory Qty" in first
        answer = format_deterministic_answer("Find materials in inventory but missing from the volume master", rows)
        assert "Materials Missing from Volume Master" in answer
        assert "MaterialVolumeMaster" in answer or "Volume Master" in answer
