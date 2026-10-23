import pytest
from backend.app.llm import extract_and_update_conversation_state, deterministic_warehouse_sql_generator, format_deterministic_answer
from backend.app.db import execute_readonly

def test_combined_top_and_least_bins():
    hist = [
        {"role": "user", "content": "compare plant 1258 and 1266"},
        {"role": "assistant", "content": "Plant comparison result"}
    ]
    q = "List the top 10 most utilized bins and the top 10 least utilized bins."
    st = extract_and_update_conversation_state(q, hist)
    assert st.get("topic") == "top_and_bottom_bins"
    assert st.get("plants") == []
    assert st.get("filters") == {}

    res = deterministic_warehouse_sql_generator(q, hist)
    qp = res.get("query_plan", {})
    assert qp.get("intent") == "COMBINED_RANKING"
    assert qp.get("number_of_rankings") == 2
    assert len(qp.get("rankings", [])) == 2
    assert qp["rankings"][0]["direction"] == "DESC"
    assert qp["rankings"][1]["direction"] == "ASC"

    rows, _ = execute_readonly(res["sql"])
    assert len(rows) == 20
    top_rows = [r for r in rows if "Most" in str(r.get("Ranking Group", ""))]
    bottom_rows = [r for r in rows if "Least" in str(r.get("Ranking Group", ""))]
    assert len(top_rows) == 10
    assert len(bottom_rows) == 10
    assert top_rows[0]["Rank"] == 1
    assert bottom_rows[0]["Rank"] == 1

    ans = format_deterministic_answer(q, rows)
    assert "Top 10 Most Utilized Bins" in ans
    assert "Top 10 Least Utilized Bins" in ans
    assert "Plant 1258 vs Plant 1266" not in ans

def test_combined_top_5_and_bottom_5():
    q = "Show the top 5 and bottom 5 bins by utilization."
    res = deterministic_warehouse_sql_generator(q)
    rows, _ = execute_readonly(res["sql"])
    assert len(rows) == 10
    ans = format_deterministic_answer(q, rows)
    assert "Top 5 Most Utilized Bins" in ans
    assert "Top 5 Least Utilized Bins" in ans

def test_combined_10_most_and_10_least():
    q = "Give me the 10 most utilized and 10 least utilized bins."
    res = deterministic_warehouse_sql_generator(q)
    rows, _ = execute_readonly(res["sql"])
    assert len(rows) == 20
    ans = format_deterministic_answer(q, rows)
    assert "Top 10 Most Utilized Bins" in ans
    assert "Top 10 Least Utilized Bins" in ans

def test_single_top_10_utilized():
    hist = [{"role": "user", "content": "compare plant 1258 and 1266"}]
    q = "Show the top 10 most utilized bins."
    st = extract_and_update_conversation_state(q, hist)
    assert st.get("topic") == "top_utilized_bins"
    assert st.get("plants") == []
    res = deterministic_warehouse_sql_generator(q, hist)
    assert res.get("query_plan", {}).get("intent") == "RANKING"
    assert res.get("query_plan", {}).get("rank_direction") == "DESC"
    rows, _ = execute_readonly(res["sql"])
    assert len(rows) == 10

def test_single_least_utilized():
    hist = [{"role": "user", "content": "compare plant 1258 and 1266"}]
    q = "Show the least utilized bins."
    st = extract_and_update_conversation_state(q, hist)
    assert st.get("topic") == "least_utilized_bins"
    assert st.get("plants") == []
    res = deterministic_warehouse_sql_generator(q, hist)
    assert res.get("query_plan", {}).get("intent") == "RANKING"
    assert res.get("query_plan", {}).get("rank_direction") == "ASC"
    rows, _ = execute_readonly(res["sql"])
    assert len(rows) == 10

def test_plant_filter_bins():
    q = "Show top 10 utilized bins in Plant 1258."
    st = extract_and_update_conversation_state(q)
    assert st.get("filters", {}).get("plant") == "1258"
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("query_plan", {}).get("rank_direction") == "DESC"
    rows, _ = execute_readonly(res["sql"])
    assert all(str(r["Plant"]) == "1258" for r in rows)

def test_plant_comparison():
    q = "Compare Plant 1258 and Plant 7228 for bin utilization."
    st = extract_and_update_conversation_state(q)
    assert st.get("topic") == "plant_comparison"
    assert set(st.get("plants", [])) == {"1258", "7228"}
    res = deterministic_warehouse_sql_generator(q)
    assert res.get("query_plan", {}).get("intent") == "COMPARISON"
    rows, _ = execute_readonly(res["sql"])
    assert len(rows) == 2

def test_compare_bins_of_plants():
    q = "Compare the top 10 utilized bins of Plant 1258 and Plant 7228."
    res = deterministic_warehouse_sql_generator(q)
    rows, _ = execute_readonly(res["sql"])
    ans = format_deterministic_answer(q, rows)
    assert "Plant 1258" in ans and "Plant 7228" in ans
