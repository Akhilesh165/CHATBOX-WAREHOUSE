"""
Centralized Semantic Regression Test Suite for Warehouse AI Chatbot.
=====================================================================
Covers:
1. Intent & Entity classification with business-subject priority.
2. Separation of response modifiers (detail/summary/graph) from business intent.
3. Pre-execution Query-Plan Validation & sanitization.
4. Post-execution Response Validation & mismatch re-routing.
5. Conversation context preservation for elliptical follow-ups.
6. Ambiguity detection and clarification questions.
7. Centralized minimum required verification test suite.
"""

import pytest
from backend.app.query_planner import (
    build_structured_query_plan,
    validate_and_sanitize_query_plan,
    validate_response_match,
    detect_ambiguity,
    is_explicit_inventory_intent,
    is_explicit_bin_utilization_intent,
)
from backend.app.llm import deterministic_warehouse_sql_generator


# -----------------------------------------------------------------------------
# 1. CORE INTENT PRIORITY (SUBJECT FIRST) TESTS
# -----------------------------------------------------------------------------

def test_inventory_subject_priority():
    """Explicit inventory requests must be classified as INVENTORY regardless of modifiers."""
    queries = [
        "Show detailed inventory for Plant 7228",
        "Give me inventory details for Plant 1258",
        "Show inventory in detail for Plant 7228",
        "Give me a detailed inventory report for Plant 1268",
        "Show all inventory details for Plant 7228",
        "Explain the inventory of Plant 7228 in detail",
        "What materials are in Plant 7228? Show details",
        "Show detailed material inventory for Plant 7228",
        "Show stock for Plant 1258",
        "Give me total material quantity in Plant 7228",
        "List available materials in Plant 7228",
        "Show inventory breakdown by plant",
        "What is the total warehouse inventory?",
    ]
    for q in queries:
        plan = build_structured_query_plan(q)
        assert plan["intent"] == "INVENTORY", f"Failed for '{q}', got intent {plan['intent']}"
        assert is_explicit_inventory_intent(q) is True, f"Failed explicit inventory check for '{q}'"


def test_bin_utilization_subject_priority():
    """Explicit bin utilization requests must be classified as BIN_UTILIZATION."""
    queries = [
        "Show detailed bin utilization for Plant 7228",
        "Show bin utilization for Plant 7228",
        "Give me bin utilization details for Plant 1258",
        "Explain bin utilization for Plant 7228 in detail",
        "What is the utilization of bins in Plant 1268?",
        "Show bin capacity utilization in Plant 7228",
        "How full are the bins in Plant 1258?",
        "Most utilized bins in Plant 7228",
        "Least utilized bins in Plant 1268",
    ]
    for q in queries:
        plan = build_structured_query_plan(q)
        assert plan["intent"] == "BIN_UTILIZATION", f"Failed for '{q}', got intent {plan['intent']}"
        assert is_explicit_bin_utilization_intent(q) is True, f"Failed explicit bin util check for '{q}'"


# -----------------------------------------------------------------------------
# 2. SEPARATION OF RESPONSE MODIFIERS FROM BUSINESS INTENT
# -----------------------------------------------------------------------------

def test_response_modifiers_isolation():
    """Detail, summary, and visualization words modify mode only and never change intent."""
    # Inventory + detail => INVENTORY (detail_mode = True)
    p1 = build_structured_query_plan("Show detailed inventory for Plant 7228")
    assert p1["intent"] == "INVENTORY"
    assert p1["detail_mode"] is True
    assert p1["visualization_mode"] is False

    # Bin utilization + detail => BIN_UTILIZATION (detail_mode = True)
    p2 = build_structured_query_plan("Show detailed bin utilization for Plant 7228")
    assert p2["intent"] == "BIN_UTILIZATION"
    assert p2["detail_mode"] is True
    assert p2["visualization_mode"] is False

    # Inventory + graph => INVENTORY (visualization_mode = True)
    p3 = build_structured_query_plan("Show inventory for Plant 7228 as a graph")
    assert p3["intent"] == "INVENTORY"
    assert p3["visualization_mode"] is True

    # Bin utilization + graph => BIN_UTILIZATION (visualization_mode = True)
    p4 = build_structured_query_plan("Show bin utilization for Plant 7228 as a chart")
    assert p4["intent"] == "BIN_UTILIZATION"
    assert p4["visualization_mode"] is True


# -----------------------------------------------------------------------------
# 3. RANKING & COMPARISON INTENT TESTS
# -----------------------------------------------------------------------------

def test_ranking_entities():
    """Correctly distinguishes material ranking vs bin ranking vs plant ranking."""
    # Material ranking
    p_mat = build_structured_query_plan("Which material has the highest quantity in Plant 7228?")
    assert p_mat["entity"] == "MATERIAL"
    assert p_mat["operation"] == "RANKING"
    assert p_mat["ranking_direction"] == "DESC"

    p_mat_low = build_structured_query_plan("Which material has the lowest quantity in Plant 7228?")
    assert p_mat_low["entity"] == "MATERIAL"
    assert p_mat_low["operation"] == "RANKING"
    assert p_mat_low["ranking_direction"] == "ASC"

    # Bin ranking
    p_bin = build_structured_query_plan("Which bin has the highest utilization in Plant 7228?")
    assert p_bin["entity"] == "BIN"
    assert p_bin["operation"] == "RANKING"
    assert p_bin["ranking_direction"] == "DESC"
    assert p_bin["metric"] == "BIN_UTILIZATION"

    p_bin_low = build_structured_query_plan("Which bin has the lowest utilization in Plant 7228?")
    assert p_bin_low["entity"] == "BIN"
    assert p_bin_low["operation"] == "RANKING"
    assert p_bin_low["ranking_direction"] == "ASC"
    assert p_bin_low["metric"] == "BIN_UTILIZATION"


def test_comparison_metrics():
    """Correctly separates Inventory Comparison vs Bin Utilization Comparison."""
    # Inventory comparison
    p_inv_comp = build_structured_query_plan("Compare inventory of Plant 7228 and 1258")
    assert p_inv_comp["comparison_mode"] is True
    assert p_inv_comp["metric"] == "INVENTORY_COMPARISON"
    assert set(p_inv_comp["plants"]) == {"7228", "1258"}

    # Bin utilization comparison
    p_bin_comp = build_structured_query_plan("Compare bin utilization of Plant 7228 and 1258")
    assert p_bin_comp["comparison_mode"] is True
    assert p_bin_comp["metric"] == "BIN_UTILIZATION_COMPARISON"
    assert set(p_bin_comp["plants"]) == {"7228", "1258"}


# -----------------------------------------------------------------------------
# 4. PRE-EXECUTION & POST-EXECUTION VALIDATION
# -----------------------------------------------------------------------------

def test_query_plan_pre_execution_validation():
    """If planner mistakenly assigned BIN_UTILIZATION to an explicit inventory query, validator auto-corrects."""
    bad_plan = {
        "intent": "BIN_UTILIZATION",
        "entity": "BIN",
        "metric": "BIN_UTILIZATION",
        "operation": "DETAILED_REPORT",
        "detail_mode": True,
        "plants": ["7228"],
        "filters": {"plants": ["7228"]}
    }
    corrected, warnings = validate_and_sanitize_query_plan(bad_plan, "Show detailed inventory for Plant 7228")
    assert corrected["intent"] == "INVENTORY"
    assert corrected["metric"] == "INVENTORY_DETAIL"
    assert len(warnings) > 0


def test_response_post_execution_validation():
    """If returned data contains only bin utilization when inventory was requested, detects mismatch."""
    plan = {"intent": "INVENTORY", "detail_mode": True}
    bin_util_rows = [{"Bin Location": "B01", "Bin Utilization %": "85.2%", "Capacity": 50.0}]
    ans = "## Plant 7228 Detailed Bin Utilization\n..."
    
    is_valid, msg, action = validate_response_match(plan, bin_util_rows, ans)
    assert is_valid is False
    assert action == "reroute_to_inventory"


def test_no_occupied_volume_in_bin_utilization():
    """Bin utilization responses must never show 'Occupied Volume' (Rule 8)."""
    plan = {"intent": "BIN_UTILIZATION"}
    forbidden_rows = [{"Bin Location": "B01", "Occupied Volume": 35.0, "Bin Utilization %": "85%"}]
    is_valid, msg, action = validate_response_match(plan, forbidden_rows, "Utilization is 85%")
    assert is_valid is False
    assert action == "sanitize_columns"


# -----------------------------------------------------------------------------
# 5. CONVERSATION CONTEXT PRESERVATION (MULTI-TURN FOLLOW-UPS)
# -----------------------------------------------------------------------------

def test_followup_ranking_reversal():
    """Turn 1: 'Show top 10 materials' -> Turn 2: 'What about the lowest ones?'"""
    history = [
        {"role": "user", "content": "Show top 10 materials by quantity"},
        {"role": "assistant", "content": "Here are the top 10 materials..."}
    ]
    p_turn2 = build_structured_query_plan("What about the lowest ones?", history=history)
    assert p_turn2["entity"] == "MATERIAL"
    assert p_turn2["operation"] == "RANKING"
    assert p_turn2["ranking_direction"] == "ASC"
    assert p_turn2["limit"] == 10


def test_followup_plant_filter_refinement():
    """Turn 1: 'Show top 10 materials' -> Turn 2: 'What about the lowest ones?' -> Turn 3: 'Only Plant 1258'"""
    history = [
        {"role": "user", "content": "Show top 10 materials by quantity"},
        {"role": "assistant", "content": "Here are the top 10 materials..."},
        {"role": "user", "content": "What about the lowest ones?"},
        {"role": "assistant", "content": "Here are the lowest materials..."}
    ]
    p_turn3 = build_structured_query_plan("Only Plant 1258", history=history)
    assert p_turn3["entity"] == "MATERIAL"
    assert p_turn3["operation"] == "RANKING"
    assert p_turn3["ranking_direction"] == "ASC"
    assert p_turn3["limit"] == 10
    assert p_turn3["plants"] == ["1258"]


def test_followup_plant_switch():
    """Turn 1: 'Show inventory for Plant 7228' -> Turn 2: 'What about Plant 1258?'"""
    history = [
        {"role": "user", "content": "Show inventory for Plant 7228"},
        {"role": "assistant", "content": "Plant 7228 inventory summary..."}
    ]
    p_turn2 = build_structured_query_plan("What about Plant 1258?", history=history)
    assert p_turn2["intent"] == "INVENTORY"
    assert p_turn2["plants"] == ["1258"]


# -----------------------------------------------------------------------------
# 6. AMBIGUITY DETECTION TESTS (REQUIREMENT 7)
# -----------------------------------------------------------------------------

def test_ambiguity_detection_and_clarification():
    """Genuinely ambiguous queries ask for clarification instead of guessing."""
    ambiguous_queries = [
        "Show warehouse details for Plant 7228",
        "Show details for Plant 7228",
        "Give me details for Plant 1258",
        "Warehouse report for Plant 7228",
    ]
    for q in ambiguous_queries:
        plan = build_structured_query_plan(q)
        assert plan["intent"] == "CLARIFICATION", f"Expected CLARIFICATION for '{q}', got {plan['intent']}"
        assert plan["ambiguity_detected"] is True
        assert plan["clarification_question"] is not None
        assert "Plant" in plan["clarification_question"]

    # Clear queries must NOT trigger ambiguity
    clear_queries = [
        "Show detailed inventory for Plant 7228",
        "Show detailed bin utilization for Plant 7228",
        "Show available capacity for Plant 7228",
        "List empty bins in Plant 7228",
    ]
    for q in clear_queries:
        plan = build_structured_query_plan(q)
        assert plan["intent"] != "CLARIFICATION", f"Expected clear intent for '{q}', got CLARIFICATION"
        assert plan["ambiguity_detected"] is False


# -----------------------------------------------------------------------------
# 7. DETERMINISTIC SQL GENERATOR HARMONIZATION
# -----------------------------------------------------------------------------

def test_deterministic_generator_intent_routing():
    """Deterministic generator produces exact matching SQL and intent metadata."""
    # 1. Show detailed inventory for Plant 7228
    res1 = deterministic_warehouse_sql_generator("Show detailed inventory for Plant 7228")
    assert res1["intent"] == "plant_inventory_detail"
    assert "PlantSummary" in res1["sql"]
    assert "Total Stock Quantity" in res1["sql"]

    # 2. Show detailed bin utilization for Plant 7228
    res2 = deterministic_warehouse_sql_generator("Show detailed bin utilization for Plant 7228")
    assert res2["intent"] in ["plant_bin_level_detail", "plant_bin_utilization_detailed_analysis"]
    assert "dbo.ZWMS_BIN_MASTER" in res2["sql"]

    # 3. Material ranking
    res3 = deterministic_warehouse_sql_generator("Which material has the highest quantity in Plant 7228?")
    assert res3["intent"] == "material_max_quantity"
    assert "UnrestrictedQty" in res3["sql"]

    # 4. Bin ranking
    res4 = deterministic_warehouse_sql_generator("Which bin has the highest utilization in Plant 7228?")
    assert res4["intent"] == "HIGHEST_BIN_UTILIZATION"

    # 5. Compare inventory
    res5 = deterministic_warehouse_sql_generator("Compare inventory of Plant 7228 and 1258")
    assert res5["intent"] == "plant_comparison"
    assert res5["metric"] == "total_inventory_comparison"

    # 6. Compare bin utilization
    res6 = deterministic_warehouse_sql_generator("Compare bin utilization of Plant 7228 and 1258")
    assert res6["intent"] == "plant_comparison"
    assert res6["metric"] == "bin_utilization_comparison"
