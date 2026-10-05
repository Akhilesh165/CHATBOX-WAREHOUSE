import pytest
from backend.app.llm import deterministic_warehouse_sql_generator, format_deterministic_answer

def test_conversation_flow_top_then_least_utilized_bins():
    history = [
        {"role": "user", "content": "Show me the top 10 most utilized bins."},
        {"role": "assistant", "content": "Found top 10 utilized bins."}
    ]
    
    follow_up_questions = [
        "What about the least utilized ones?",
        "What about least utilized ones?",
        "And the least utilized ones?",
        "What about the lowest ones?",
        "Show least utilized ones",
        "And what about the bottom 10?",
        "What about the least utilized?"
    ]
    
    for q in follow_up_questions:
        res = deterministic_warehouse_sql_generator(q, history=history)
        assert res["intent"] == "least_utilized_bins", f"Failed for follow-up query: {q}"
        assert "ASC" in res["sql"], f"Expected ASC ordering in SQL for: {q}"
        assert res["output_type"] == "table"

def test_standalone_anaphoric_queries():
    res1 = deterministic_warehouse_sql_generator("What about the least utilized ones?")
    assert res1["intent"] == "least_utilized_bins"
    assert "ASC" in res1["sql"]

    res2 = deterministic_warehouse_sql_generator("What about the most utilized ones?")
    assert res2["intent"] == "top_utilized_bins"
    assert "DESC" in res2["sql"]

    res3 = deterministic_warehouse_sql_generator("Show least utilized ones")
    assert res3["intent"] == "least_utilized_bins"

def test_conversation_flow_data_quality_plant_filter():
    history = [
        {"role": "user", "content": "Which inventory materials don't have dimensions?"},
        {"role": "assistant", "content": "Found materials with missing dimensions."}
    ]
    res = deterministic_warehouse_sql_generator("What about in plant 1258?", history=history)
    assert res["intent"] == "data_quality_check"
    assert "1258" in res["sql"]

def test_conversation_flow_empty_bins_plant_filter():
    history = [
        {"role": "user", "content": "Show me empty bins for put-away"},
        {"role": "assistant", "content": "Found empty bins."}
    ]
    res = deterministic_warehouse_sql_generator("What about plant 7228?", history=history)
    assert res["intent"] == "putaway_bins"
    assert "7228" in res["sql"]

def test_conversation_flow_multi_turn_filter_and_limit_inheritance():
    # Turn 1: Top 10 Bins
    # Turn 2: What about the least utilized ones?
    # Turn 3: Only for Plant 1258.
    # Turn 4: Top 5 instead
    history_turn_2 = [
        {"role": "user", "content": "Show me the top 10 most utilized bins."},
        {"role": "assistant", "content": "Found top 10 most utilized bins."},
        {"role": "user", "content": "What about the least utilized ones?"},
        {"role": "assistant", "content": "Found bottom 10 least utilized bins."}
    ]
    res_turn_3 = deterministic_warehouse_sql_generator("Only for Plant 1258.", history=history_turn_2)
    assert res_turn_3["intent"] == "least_utilized_bins"
    assert "1258" in res_turn_3["sql"]
    assert "ASC" in res_turn_3["sql"]

    history_turn_3 = history_turn_2 + [
        {"role": "user", "content": "Only for Plant 1258."},
        {"role": "assistant", "content": "Found bottom 10 least utilized bins in Plant 1258."}
    ]
    res_turn_4 = deterministic_warehouse_sql_generator("Top 5 instead", history=history_turn_3)
    assert res_turn_4["intent"] == "least_utilized_bins"
    assert "TOP 5" in res_turn_4["sql"]

