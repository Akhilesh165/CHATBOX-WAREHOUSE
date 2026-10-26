import pytest
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    format_deterministic_answer,
    optimize_response_format,
    is_comparison_intent,
    is_comparison_explanation_requested,
    is_comparison_detail_requested,
)
from backend.app.db import execute_readonly


def test_first_response_to_comparison_is_table_only():
    """Rule 1 & 3: Initial comparison response must directly start with a proper comparison table.

    No narrative summary before, no conclusion, no comparison summary paragraph.
    """
    q = "Compare the bin utilization of Plant 1268 and Plant 1266"
    gen = deterministic_warehouse_sql_generator(q)
    rows, _ = execute_readonly(gen["sql"])
    ans = format_deterministic_answer(q, rows)

    # 1. Must directly start with Markdown comparison table
    assert ans.startswith("| Plant |"), f"Expected table header at start, got:\n{ans[:100]}"
    assert "| Occupied Bins | Empty Bins | Total Bins | Bin Utilization % |" in ans

    # 2. Rows contain plants and exact values
    assert "1268" in ans and "68.73%" in ans
    assert "1266" in ans and "70.53%" in ans

    # 3. No narrative summary, conclusion, or summary paragraph before/after
    assert "### 🏭" not in ans
    assert "Comparison Breakdown" not in ans
    assert "Comparison Summary" not in ans
    assert "Conclusion:" not in ans
    assert "💡" not in ans

    # 4. No unrequested volume information (Rule 15)
    assert "Occupied Volume" not in ans
    assert "Total Capacity" not in ans
    assert "Available Capacity" not in ans
    assert "Volume Utilization" not in ans
    assert "FT³" not in ans


def test_inventory_comparison_table_only():
    """Rule 2 & 6: Inventory quantity comparison produces table only."""
    q = "Compare total inventory between Plant 1258 and Plant 7228"
    gen = deterministic_warehouse_sql_generator(q)
    rows, _ = execute_readonly(gen["sql"])
    ans = format_deterministic_answer(q, rows)

    assert ans.startswith("| Plant |")
    assert "Total Inventory Quantity" in ans
    assert "1258" in ans and "498,504" in ans
    assert "7228" in ans and "1,933,031" in ans
    assert "Conclusion:" not in ans


def test_capacity_comparison_table_only():
    """Rule 2 & 6: Capacity comparison produces relevant capacity table only."""
    q = "Compare capacity between Plant 1258 and Plant 7228"
    gen = deterministic_warehouse_sql_generator(q)
    rows, _ = execute_readonly(gen["sql"])
    ans = format_deterministic_answer(q, rows)

    assert ans.startswith("| Plant |")
    assert "Capacity" in ans
    assert "1258" in ans and "7228" in ans
    assert "Conclusion:" not in ans


def test_empty_bins_comparison_table_only():
    """Rule 2 & 6: Empty bins comparison produces empty bins table only."""
    q = "Compare empty bins between Plant 1258 and Plant 7228"
    gen = deterministic_warehouse_sql_generator(q)
    rows, _ = execute_readonly(gen["sql"])
    ans = format_deterministic_answer(q, rows)

    assert ans.startswith("| Plant |")
    assert "Empty Bins" in ans
    assert "1258" in ans and "2,425" in ans
    assert "7228" in ans and "1,992" in ans


def test_summary_only_when_user_requests_it():
    """Rule 4 & 5: When user asks for explanation/summary of comparison table,

    response format is:
    ### Comparison Table
    ...
    ### Summary
    ...
    """
    mock_rows = [
        {"Plant": "7228", "Occupied Bins": 7522, "Empty Bins": 1992, "Total Bins": 9514, "Bin Utilization %": "79.06%"},
        {"Plant": "1268", "Occupied Bins": 10710, "Empty Bins": 4872, "Total Bins": 15582, "Bin Utilization %": "68.73%"}
    ]

    for trigger in [
        "Explain this table",
        "Explain the comparison",
        "What does this mean?",
        "Give me a summary",
        "Summarize the above",
        "Which one is better?",
        "Explain the result",
        "What can you conclude?",
        "Give me the comparison summary",
        "Tell me what this table means",
        "Explain it."
    ]:
        ans = format_deterministic_answer(trigger, mock_rows)
        assert ans.startswith("### Comparison Table"), f"Failed header for trigger: {trigger}"
        assert "### Summary" in ans, f"Failed summary header for trigger: {trigger}"
        assert "| Plant |" in ans
        assert "7228" in ans and "1268" in ans
        assert "higher bin utilization" in ans or "percentage points" in ans or "Plant 7228" in ans


def test_comparison_plus_detail():
    """Rule 10: Comparison + Detail returns Comparison Table -> Detailed comparison."""
    mock_rows = [
        {"Plant": "7228", "Occupied Bins": 7522, "Empty Bins": 1992, "Total Bins": 9514, "Bin Utilization %": "79.06%"},
        {"Plant": "1268", "Occupied Bins": 10710, "Empty Bins": 4872, "Total Bins": 15582, "Bin Utilization %": "68.73%"}
    ]
    q = "Compare the bin utilization of Plant 1268 and Plant 7228 in detail"
    ans = format_deterministic_answer(q, mock_rows)

    assert ans.startswith("### Comparison Table")
    assert "### Detailed Comparison" in ans
    assert "| Plant |" in ans
    assert "- **Plant 7228**" in ans and "79.06%" in ans
    assert "- **Plant 1268**" in ans and "68.73%" in ans


def test_comparison_plus_single_line():
    """Rule 12: Comparison + Single Line overrides table with crisp single statement."""
    mock_rows = [
        {"Plant": "7228", "Occupied Bins": 7522, "Empty Bins": 1992, "Total Bins": 9514, "Bin Utilization %": "79.06%"},
        {"Plant": "1268", "Occupied Bins": 10710, "Empty Bins": 4872, "Total Bins": 15582, "Bin Utilization %": "68.73%"}
    ]
    q = "Compare Plant 7228 and Plant 1268 and give me only the answer"
    ans = format_deterministic_answer(q, mock_rows)

    # Must be single line statement, no Markdown table
    assert "|" not in ans
    assert "Plant 7228" in ans and "Plant 1268" in ans
    assert "higher bin utilization" in ans


def test_comparison_plus_graph():
    """Rule 11: Comparison + Graph returns Comparison Table + Bar Chart."""
    q = "Compare Plant 1268 and Plant 7228 with a graph"
    gen = deterministic_warehouse_sql_generator(q)
    rows, _ = execute_readonly(gen["sql"])
    ans = format_deterministic_answer(q, rows)

    # Table is prioritized
    assert ans.startswith("| Plant |")

    # Chart format
    opt = optimize_response_format(q, rows, gen)
    assert opt["chart_type"] == "bar"
    assert opt["output_type"] == "bar_chart"


def test_non_comparison_queries_remain_unchanged():
    """Rule 9: Non-comparison queries must remain completely unchanged."""
    # 1. Single plant bin utilization
    q1 = "Show bin utilization for Plant 7228"
    gen1 = deterministic_warehouse_sql_generator(q1)
    rows1, _ = execute_readonly(gen1["sql"])
    ans1 = format_deterministic_answer(q1, rows1)
    assert "Plant 7228: **79.06%** Bin Utilization" in ans1
    assert not ans1.startswith("| Plant |")

    # 2. All plants bin utilization
    q2 = "Show the bin utilization of all plants"
    gen2 = deterministic_warehouse_sql_generator(q2)
    rows2, _ = execute_readonly(gen2["sql"])
    ans2 = format_deterministic_answer(q2, rows2)
    assert "Plant 7228" in ans2 and "79.06%" in ans2
    assert "Plant 1268" in ans2 and "68.73%" in ans2

    # 3. Ranking plants by bin utilization
    q3 = "Rank plants by bin utilization"
    gen3 = deterministic_warehouse_sql_generator(q3)
    rows3, _ = execute_readonly(gen3["sql"])
    ans3 = format_deterministic_answer(q3, rows3)
    assert "Plant 7228" in ans3 and "79.06%" in ans3
    assert "#1" in ans3 or "Rank 1" in ans3

    # 4. Range query
    q4 = "Show materials with between 100 and 500 units in Plant 1258"
    gen4 = deterministic_warehouse_sql_generator(q4)
    rows4, _ = execute_readonly(gen4["sql"])
    ans4 = format_deterministic_answer(q4, rows4)
    assert "between 100 and 500 units" in ans4 or "Plant 1258" in ans4
