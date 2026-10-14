import pytest
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    format_deterministic_answer,
    optimize_response_format,
    extract_and_update_conversation_state
)
from backend.app.db import execute_readonly


LIVE_USER_QUESTIONS = [
    "fetch the bin utlization of plant 1268",
    "compare the bin utilization of plant 1268 and 1258",
    "compare the bin utilization of plant 1268 and 1258 with graph",
    "Top 5 plants by occupied volume",
    "fetch the bin utilization of 7229 plant",
    "Rank all plants by total occupied volume.",
    "Which plant has the highest occupied volume",
    "Which plant has the lowest  occupied volume",
    "how many bins available in plant 7228",
    "how many bins available in plant 7228 with graph",
    "Give me a plant-wise ranking based on occupied volume.",
    "total warehouse bins",
    "What is the difference between Plant 1258 utilization and overall warehouse utilization?",
    "Are there bins with zero capacity but non-zero occupied volume?",
    "Rank Plant 7228 bins by utilization from lowest to highest.",
    "Show only bins between 50% and 80% utilization.",
    "What rank is Plant 1258 by occupied volume?",
    "Why is Plant 1268 ranked #1 by occupied volume?",
    "Rank bins by available capacity",
    "Show the top 10 most utilized bins",
    "Show materials in Plant 1258",
    "Is bin NRJP2124D2 occupied?"
]


@pytest.mark.parametrize("question", LIVE_USER_QUESTIONS)
def test_live_user_queries_end_to_end(question):
    """Test that all real user queries generate valid SQL, execute cleanly, and produce grounded answers."""
    gen = deterministic_warehouse_sql_generator(question)
    assert gen is not None, f"Generator returned None for '{question}'"
    assert "sql" in gen, f"No SQL produced for '{question}'"
    assert len(gen["sql"].strip()) > 0

    # Execute SQL on local database
    rows, elapsed_ms = execute_readonly(gen["sql"])
    assert isinstance(rows, list), f"Query execution failed for '{question}'"

    # Answer formatting
    ans = format_deterministic_answer(question, rows)
    assert ans is not None
    assert len(ans.strip()) > 0

    # Optimize format
    opt = optimize_response_format(question, rows, gen)
    assert opt is not None
    assert "output_type" in opt
    assert "chart_type" in opt


def test_followup_chain_debugging():
    """Debug multi-turn elliptical conversational flows."""
    # Turn 1: Top 10 most utilized bins
    q1 = "Show the top 10 most utilized bins"
    g1 = deterministic_warehouse_sql_generator(q1)
    r1, _ = execute_readonly(g1["sql"])
    assert len(r1) == 10

    hist = [
        {"role": "user", "content": q1},
        {"role": "assistant", "content": format_deterministic_answer(q1, r1)}
    ]

    # Turn 2: What about the least utilized ones?
    q2 = "What about the least utilized ones?"
    g2 = deterministic_warehouse_sql_generator(q2, history=hist)
    assert g2["query_plan"]["rank_direction"] == "ASC"
    r2, _ = execute_readonly(g2["sql"])
    assert len(r2) > 0

    hist.extend([
        {"role": "user", "content": q2},
        {"role": "assistant", "content": format_deterministic_answer(q2, r2)}
    ])

    # Turn 3: Only for Plant 1258
    q3 = "Only for Plant 1258"
    g3 = deterministic_warehouse_sql_generator(q3, history=hist)
    assert "1258" in g3["sql"]
    r3, _ = execute_readonly(g3["sql"])
    assert len(r3) > 0
    for row in r3:
        if "Plant" in row:
            assert str(row["Plant"]) == "1258"

    hist.extend([
        {"role": "user", "content": q3},
        {"role": "assistant", "content": format_deterministic_answer(q3, r3)}
    ])

    # Turn 4: Show 5 instead
    q4 = "Show 5 instead"
    g4 = deterministic_warehouse_sql_generator(q4, history=hist)
    assert "TOP 5" in g4["sql"] or "limit 5" in str(g4.get("query_plan", {})).lower()
    r4, _ = execute_readonly(g4["sql"])
    assert len(r4) == 5
