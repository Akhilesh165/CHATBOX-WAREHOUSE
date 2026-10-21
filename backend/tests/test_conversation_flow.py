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

def test_conversation_3_utilization_ranking_flow():
    # 141: Show the most utilized bins.
    res1 = deterministic_warehouse_sql_generator("Show the most utilized bins.", [])
    assert res1["intent"] == "top_utilized_bins"
    plan1 = res1.get("query_plan", {})
    assert plan1.get("entity") == "BIN"
    assert plan1.get("metric") == "BIN_UTILIZATION"
    assert plan1.get("ranking_direction") == "DESC"

    # 142: What about Plant 7228?
    h1 = [{"role": "user", "content": "Show the most utilized bins."}, {"role": "assistant", "content": "..."}]
    res2 = deterministic_warehouse_sql_generator("What about Plant 7228?", h1)
    assert res2["intent"] == "top_utilized_bins"
    assert res2["filters"].get("plant") == "7228"
    plan2 = res2.get("query_plan", {})
    assert plan2.get("ranking_direction") == "DESC"

    # 143: Now show the least utilized ones.
    h2 = h1 + [{"role": "user", "content": "What about Plant 7228?"}, {"role": "assistant", "content": "..."}]
    res3 = deterministic_warehouse_sql_generator("Now show the least utilized ones.", h2)
    assert res3["intent"] == "least_utilized_bins"
    assert res3["filters"].get("plant") == "7228"
    plan3 = res3.get("query_plan", {})
    assert plan3.get("ranking_direction") == "ASC"

    # 144: Show the top 10.
    h3 = h2 + [{"role": "user", "content": "Now show the least utilized ones."}, {"role": "assistant", "content": "..."}]
    res4 = deterministic_warehouse_sql_generator("Show the top 10.", h3)
    assert res4["intent"] == "top_utilized_bins"
    assert res4["filters"].get("plant") == "7228"
    plan4 = res4.get("query_plan", {})
    assert plan4.get("ranking_direction") == "DESC"
    assert plan4.get("limit") == 10

    # 145: Make it top 5.
    h4 = h3 + [{"role": "user", "content": "Show the top 10."}, {"role": "assistant", "content": "..."}]
    res5 = deterministic_warehouse_sql_generator("Make it top 5.", h4)
    assert res5["intent"] == "top_utilized_bins"
    assert res5["filters"].get("plant") == "7228"
    plan5 = res5.get("query_plan", {})
    assert plan5.get("ranking_direction") == "DESC"
    assert plan5.get("limit") == 5

def test_conversation_4_plant_comparison_and_format_modifiers():
    # 146: Show me the inventory of Plant 1258.
    res1 = deterministic_warehouse_sql_generator("Show me the inventory of Plant 1258.", [])
    assert res1["intent"] == "plant_inventory"
    assert res1["filters"].get("plant") == "1258"
    plan1 = res1.get("query_plan", {})
    assert plan1.get("entity") == "PLANT"
    assert plan1.get("metric") == "TOTAL_INVENTORY_QUANTITY"
    assert plan1.get("operation") == "AGGREGATION"

    # 147: What about Plant 7228?
    h1 = [{"role": "user", "content": "Show me the inventory of Plant 1258."}, {"role": "assistant", "content": "..."}]
    res2 = deterministic_warehouse_sql_generator("What about Plant 7228?", h1)
    assert res2["intent"] == "plant_inventory"
    assert res2["filters"].get("plant") == "7228"
    plan2 = res2.get("query_plan", {})
    assert plan2.get("entity") == "PLANT"
    assert plan2.get("metric") == "TOTAL_INVENTORY_QUANTITY"

    # 148: Compare those two.
    h2 = h1 + [{"role": "user", "content": "What about Plant 7228?"}, {"role": "assistant", "content": "..."}]
    res3 = deterministic_warehouse_sql_generator("Compare those two.", h2)
    assert res3["intent"] == "plant_comparison"
    plan3 = res3.get("query_plan", {})
    assert plan3.get("entity") == "PLANT"
    assert plan3.get("metric") == "TOTAL_INVENTORY_QUANTITY"
    assert plan3.get("operation") == "COMPARISON"
    assert set(plan3.get("plants", [])) == {"1258", "7228"}
    assert plan3.get("response_mode") == "TABLE"

    # 149: Show the detailed version.
    h3 = h2 + [{"role": "user", "content": "Compare those two."}, {"role": "assistant", "content": "..."}]
    res4 = deterministic_warehouse_sql_generator("Show the detailed version.", h3)
    assert res4["intent"] == "plant_comparison"
    plan4 = res4.get("query_plan", {})
    assert plan4.get("entity") == "PLANT"
    assert plan4.get("metric") == "TOTAL_INVENTORY_QUANTITY"
    assert plan4.get("operation") == "COMPARISON"
    assert plan4.get("response_mode") == "DETAIL"

    # 150: Give me only the count.
    h4 = h3 + [{"role": "user", "content": "Show the detailed version."}, {"role": "assistant", "content": "..."}]
    res5 = deterministic_warehouse_sql_generator("Give me only the count.", h4)
    assert res5["intent"] == "plant_comparison"
    assert res5["output_type"] == "text"
    plan5 = res5.get("query_plan", {})
    assert plan5.get("response_mode") == "COUNT"
    ans5 = format_deterministic_answer("Give me only the count.", [{"Plant": "1258", "Total Inventory Quantity": 498504}, {"Plant": "7228", "Total Inventory Quantity": 1933031}])
    assert "Total count" in ans5

    # 151: Show only the names.
    h5 = h4 + [{"role": "user", "content": "Give me only the count."}, {"role": "assistant", "content": "..."}]
    res6 = deterministic_warehouse_sql_generator("Show only the names.", h5)
    assert res6["intent"] == "plant_comparison"
    assert res6["output_type"] == "text"
    plan6 = res6.get("query_plan", {})
    assert plan6.get("response_mode") == "NAMES_ONLY"
    ans6 = format_deterministic_answer("Show only the names.", [{"Plant": "1258"}, {"Plant": "7228"}])
    assert "Plant 1258" in ans6 and "Plant 7228" in ans6

    # 152: Show only the percentage.
    h6 = h5 + [{"role": "user", "content": "Show only the names."}, {"role": "assistant", "content": "..."}]
    res7 = deterministic_warehouse_sql_generator("Show only the percentage.", h6)
    assert res7["intent"] == "plant_comparison"
    assert res7["output_type"] == "text"
    plan7 = res7.get("query_plan", {})
    assert plan7.get("response_mode") == "PERCENTAGE_ONLY"
    ans7 = format_deterministic_answer("Show only the percentage.", [{"Plant": "1258", "Total Inventory Quantity": 498504}, {"Plant": "7228", "Total Inventory Quantity": 1933031}])
    assert "%" in ans7 and "Plant 1258" in ans7 and "Plant 7228" in ans7

    # 153: Show the same thing for the other plant.
    h7 = h6 + [{"role": "user", "content": "Show only the percentage."}, {"role": "assistant", "content": "..."}]
    res8 = deterministic_warehouse_sql_generator("Show the same thing for the other plant.", h7)
    assert res8["intent"] == "plant_inventory"
    assert res8["filters"].get("plant") == "1258"
    plan8 = res8.get("query_plan", {})
    assert plan8.get("entity") == "PLANT"
    assert plan8.get("metric") == "TOTAL_INVENTORY_QUANTITY"



