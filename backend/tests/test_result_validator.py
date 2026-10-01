"""Unit tests for the Result Validator Layer."""

import pytest
from backend.app.validator import validate_query_result
from backend.app.llm import deterministic_warehouse_sql_generator

def test_result_validator_detects_mismatched_summary():
    question = "Which inventory materials don't have dimensions?"
    
    # Generic summary columns returned improperly
    bad_rows = [{
        "TotalUniqueMaterials": 850,
        "TotalActiveBins": 2100,
        "PlantCount": 4,
        "TotalUnrestrictedQuantity": 95000.0
    }]
    
    is_valid, reason = validate_query_result(question, None, "SELECT ...", bad_rows)
    assert not is_valid
    assert "User requested: Material-level missing-dimension records" in reason
    assert "Returned: Warehouse-level inventory summary" in reason

def test_result_validator_passes_correct_records():
    question = "Which inventory materials don't have dimensions?"
    
    correct_rows = [{
        "Material": "MAT001",
        "Material Description": "Test Widget",
        "Total Stock Qty": 150.0,
        "Occupied Bins": 2,
        "Length": None,
        "Width": None,
        "Height": None,
        "Volume": None,
        "Quality Issue": "Missing Volume Master Record"
    }]
    
    is_valid, reason = validate_query_result(question, None, "SELECT ...", correct_rows)
    assert is_valid
    assert "Passed" in reason

def test_result_validator_detects_ranking_mismatch():
    question = "Top 10 most utilized bins"
    bad_rows = [{"TotalUniqueMaterials": 500, "TotalActiveBins": 100}]
    
    is_valid, reason = validate_query_result(question, None, "SELECT ...", bad_rows)
    assert not is_valid
    assert "User requested: Bin utilization ranking records" in reason

def test_query_plan_structure():
    gen = deterministic_warehouse_sql_generator("Which materials have missing physical dimensions?")
    assert "query_plan" in gen
    plan = gen["query_plan"]
    assert plan["user_intent"] == "data_quality"
    assert plan["question_type"] == "missing_data"
    assert plan["entity"] == "material"
    assert plan["analytical_task"] == "DATA QUALITY"
    assert "dbo.ZWMS_INVENTORY" in plan["tables"]
    assert "dbo.ZWMS_MATERIAL_MASTER" in plan["tables"]
    assert plan["result_type"] == "table"
