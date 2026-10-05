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

def test_conversation_1_full_flow():
    # Turn 1: Show me the top 10 most utilized bins.
    turn1_q = "Show me the top 10 most utilized bins."
    res1 = deterministic_warehouse_sql_generator(turn1_q)
    assert res1["intent"] == "top_utilized_bins"
    assert "DESC" in res1["sql"]
    assert "TOP 10" in res1["sql"]
    assert "Occupied Volume" in res1["sql"]
    assert "Capacity" in res1["sql"]
    assert "Utilization" in res1["sql"]

    # Turn 2: What about the least utilized ones?
    history1 = [
        {"role": "user", "content": turn1_q},
        {"role": "assistant", "content": "Top 10 Most Utilized Bins"}
    ]
    turn2_q = "What about the least utilized ones?"
    res2 = deterministic_warehouse_sql_generator(turn2_q, history=history1)
    assert res2["intent"] == "least_utilized_bins"
    assert "ASC" in res2["sql"]
    assert "TOP 10" in res2["sql"]

    # Turn 3: Only for Plant 1258.
    history2 = history1 + [
        {"role": "user", "content": turn2_q},
        {"role": "assistant", "content": "10 Least Utilized Bins"}
    ]
    turn3_q = "Only for Plant 1258."
    res3 = deterministic_warehouse_sql_generator(turn3_q, history=history2)
    assert res3["intent"] == "least_utilized_bins"
    assert "ASC" in res3["sql"]
    assert "1258" in res3["sql"]
    assert res3["filters"].get("plant") == "1258"

    # Turn 4: Show me the top 5 instead.
    history3 = history2 + [
        {"role": "user", "content": turn3_q},
        {"role": "assistant", "content": "10 Least Utilized Bins — Plant 1258"}
    ]
    turn4_q = "Show me the top 5 instead."
    res4 = deterministic_warehouse_sql_generator(turn4_q, history=history3)
    assert res4["intent"] == "top_utilized_bins"
    assert "DESC" in res4["sql"]
    assert "TOP 5" in res4["sql"]
    assert "1258" in res4["sql"]
    assert res4["filters"].get("plant") == "1258"

def test_conversation_2_empty_bins_flow():
    # Turn 1: Show me empty bins.
    turn1_q = "Show me empty bins."
    res1 = deterministic_warehouse_sql_generator(turn1_q)
    assert res1["intent"] == "putaway_bins"
    assert res1["output_type"] == "table"
    assert "Storage Location" in res1["sql"]
    assert "Status" in res1["sql"]

    # Turn 2: Only in Plant 1258.
    history1 = [
        {"role": "user", "content": turn1_q},
        {"role": "assistant", "content": "Empty Bins Available for Put-away"}
    ]
    turn2_q = "Only in Plant 1258."
    res2 = deterministic_warehouse_sql_generator(turn2_q, history=history1)
    assert res2["intent"] == "putaway_bins"
    assert res2["output_type"] == "table"
    assert "1258" in res2["sql"]

    # Turn 3: How many are there?
    history2 = history1 + [
        {"role": "user", "content": turn2_q},
        {"role": "assistant", "content": "Empty Bins — Plant 1258"}
    ]
    turn3_q = "How many are there?"
    res3 = deterministic_warehouse_sql_generator(turn3_q, history=history2)
    assert res3["intent"] == "empty_bins_count"
    assert res3["output_type"] == "kpi"
    assert "COUNT(DISTINCT" in res3["sql"]
    assert "1258" in res3["sql"]


