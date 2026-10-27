import pytest
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    format_deterministic_answer,
    is_bin_level_detail_intent,
    extract_and_update_conversation_state,
    optimize_response_format
)
from backend.app.db import execute_readonly


def test_section_2_all_twelve_detail_intent_phrasings():
    """Verify semantic intent detection across all 12 phrasings from Section 2."""
    twelve_examples = [
        "Detail bin utilization of Plant 1268",
        "Show bin utilization of Plant 1268 in detail",
        "Give me detailed bin utilization for Plant 1268",
        "Explain bin utilization of Plant 1268",
        "Give me a summary of bin utilization for Plant 1268",
        "Show complete bin utilization of Plant 1268",
        "Break down bin utilization of Plant 1268",
        "Give me full details of Plant 1268 bins",
        "Show all bins of Plant 1268 with utilization",
        "Detailed analysis of bins in Plant 1268",
        "Explain all bins of Plant 1268",
        "Give complete bin-wise utilization for Plant 1268"
    ]

    for q in twelve_examples:
        assert is_bin_level_detail_intent(q), f"Failed intent recognition for: {q}"
        plan = deterministic_warehouse_sql_generator(q)
        assert plan["intent"] == "plant_bin_level_detail", f"Failed intent mapping for: {q}"
        assert plan["filters"]["plant"] == "1268"
        assert plan["output_type"] == "table"


def test_section_3_and_4_single_plant_detail_table():
    """Verify single-plant detail generates individual bins with canonical columns."""
    q = "Detail bin utilization of Plant 1268"
    plan = deterministic_warehouse_sql_generator(q)
    rows, _ = execute_readonly(plan["sql"], max_rows=50)
    assert len(rows) > 1, "Must return individual bins, not a single plant aggregate"

    ans = format_deterministic_answer(q, rows)
    assert ("## Plant 1268 — Detailed Bin Utilization" in ans or "## Plant 1268 — Bin Utilization" in ans)
    assert "| Bin | Capacity | Available Capacity | Utilization % | Material / Inventory Information |" in ans
    # Assert individual bins are present
    assert rows[0]["Bin"] in ans


def test_section_5_occupied_volume_global_exclusion():
    """Verify 'Occupied Volume' is strictly excluded from all user-facing bin utilization tables."""
    queries = [
        "Detail bin utilization of Plant 1268",
        "Compare detailed bin utilization of Plant 1268 and Plant 1266",
        "Give detailed top 5 bins of Plant 1268"
    ]
    for q in queries:
        plan = deterministic_warehouse_sql_generator(q)
        rows, _ = execute_readonly(plan["sql"], max_rows=20)
        ans = format_deterministic_answer(q, rows)
        assert "Occupied Volume" not in ans, f"'Occupied Volume' found in response for: {q}"
        assert "Occupied Volume (m³)" not in ans
        assert "Occupied Volume (FT³)" not in ans
        assert "Used Volume" not in ans


def test_section_6_7_14_multi_plant_detailed_comparison_separate_tables():
    """Verify detailed multi-plant comparisons produce separate tables per plant."""
    q = "Compare detailed top 5 bins of Plant 1268 and Plant 1266"
    plan = deterministic_warehouse_sql_generator(q)
    assert plan["intent"] == "multi_plant_bin_detail"
    assert plan["filters"]["plants"] == ["1268", "1266"]

    rows, _ = execute_readonly(plan["sql"])
    assert len(rows) == 10

    ans = format_deterministic_answer(q, rows)
    assert ("## Plant 1268 — Detailed Bin Utilization" in ans or "## Plant 1268 — Bin Utilization" in ans)
    assert ("## Plant 1266 — Detailed Bin Utilization" in ans or "## Plant 1266 — Bin Utilization" in ans)

    # Verify order: Plant 1268 section comes first, then Plant 1266
    p1268_idx = ans.index("Plant 1268")
    p1266_idx = ans.index("Plant 1266")
    assert p1268_idx < p1266_idx

    # Verify both sections have their own table headers
    sections = ans.split("## Plant ")
    # sections[0] is empty prefix, sections[1] is 1268, sections[2] is 1266 (with optional summary at end)
    assert len(sections) >= 3
    for s in sections[1:3]:
        assert "| Bin | Capacity | Available Capacity | Utilization % | Material / Inventory Information |" in s


def test_section_6_dynamic_three_plant_comparison():
    """Verify dynamic support for 3 plants with 3 separate tables."""
    q = "Compare detailed top 5 bins of Plant 1268, Plant 1266 and Plant 7228"
    plan = deterministic_warehouse_sql_generator(q)
    assert plan["intent"] == "multi_plant_bin_detail"

    rows, _ = execute_readonly(plan["sql"])
    assert len(rows) == 15
    ans = format_deterministic_answer(q, rows)
    assert ("## Plant 1268 — Detailed Bin Utilization" in ans or "## Plant 1268 — Bin Utilization" in ans)
    assert ("## Plant 1266 — Detailed Bin Utilization" in ans or "## Plant 1266 — Bin Utilization" in ans)
    assert ("## Plant 7228 — Detailed Bin Utilization" in ans or "## Plant 7228 — Bin Utilization" in ans)


def test_section_8_normal_vs_detail_query_distinction():
    """Verify normal queries remain plant aggregates and normal comparisons remain summary tables."""
    # 1. Normal single-plant query
    normal_q = "What is the bin utilization of Plant 1268?"
    normal_plan = deterministic_warehouse_sql_generator(normal_q)
    assert normal_plan["intent"] == "plant_bin_utilization_detail"
    normal_rows, _ = execute_readonly(normal_plan["sql"])
    assert len(normal_rows) == 1
    assert "68.73%" in normal_rows[0]["Bin Utilization %"]

    normal_ans = format_deterministic_answer(normal_q, normal_rows)
    assert "68.73%" in normal_ans
    assert "## Plant 1268" not in normal_ans  # not bin-level table

    # 2. Normal multi-plant comparison
    comp_q = "Compare Plant 1268 and Plant 1266"
    comp_plan = deterministic_warehouse_sql_generator(comp_q)
    assert comp_plan["intent"] != "multi_plant_bin_detail"
    comp_rows, _ = execute_readonly(comp_plan["sql"])
    assert len(comp_rows) == 2  # 2 plant rows

    comp_ans = format_deterministic_answer(comp_q, comp_rows)
    assert "| Plant | Occupied Bins | Empty Bins | Total Bins | Bin Utilization % |" in comp_ans


def test_section_10_follow_up_context_preservation():
    """Verify detailed bin utilization flow preserved across multiple elliptical turns:
    Plant 1268 -> Plant 1266 -> Plant 7228 -> Compare those two.
    """
    history = []

    # Turn 1: Initial detailed query
    t1_q = "Detail bin utilization of Plant 1268"
    t1_plan = deterministic_warehouse_sql_generator(t1_q, history=history)
    assert t1_plan["intent"] == "plant_bin_level_detail"
    assert t1_plan["filters"]["plant"] == "1268"
    t1_rows, _ = execute_readonly(t1_plan["sql"], max_rows=10)
    t1_ans = format_deterministic_answer(t1_q, t1_rows)
    history.append({"role": "user", "content": t1_q})
    history.append({"role": "assistant", "content": t1_ans})

    # Turn 2: Follow-up on Plant 1266
    t2_q = "What about Plant 1266?"
    t2_plan = deterministic_warehouse_sql_generator(t2_q, history=history)
    assert t2_plan["intent"] == "plant_bin_level_detail"
    assert t2_plan["filters"]["plant"] == "1266"
    t2_rows, _ = execute_readonly(t2_plan["sql"], max_rows=10)
    t2_ans = format_deterministic_answer(t2_q, t2_rows)
    assert ("## Plant 1266 — Detailed Bin Utilization" in t2_ans or "## Plant 1266 — Bin Utilization" in t2_ans)
    history.append({"role": "user", "content": t2_q})
    history.append({"role": "assistant", "content": t2_ans})

    # Turn 3: Follow-up on Plant 7228
    t3_q = "What about Plant 7228?"
    t3_plan = deterministic_warehouse_sql_generator(t3_q, history=history)
    assert t3_plan["intent"] == "plant_bin_level_detail"
    assert t3_plan["filters"]["plant"] == "7228"
    t3_rows, _ = execute_readonly(t3_plan["sql"], max_rows=10)
    t3_ans = format_deterministic_answer(t3_q, t3_rows)
    assert ("## Plant 7228 — Detailed Bin Utilization" in t3_ans or "## Plant 7228 — Bin Utilization" in t3_ans)
    history.append({"role": "user", "content": t3_q})
    history.append({"role": "assistant", "content": t3_ans})

    # Turn 4: "Compare those two"
    t4_q = "Compare those two"
    t4_plan = deterministic_warehouse_sql_generator(t4_q, history=history)
    assert t4_plan["intent"] == "multi_plant_bin_detail"
    assert t4_plan["filters"]["plants"] == ["1266", "7228"]
    t4_rows = t2_rows + t3_rows
    t4_ans = format_deterministic_answer(t4_q, t4_rows)
    assert ("## Plant 1266 — Detailed Bin Utilization" in t4_ans or "## Plant 1266 — Bin Utilization" in t4_ans)
    assert ("## Plant 7228 — Detailed Bin Utilization" in t4_ans or "## Plant 7228 — Bin Utilization" in t4_ans)


def test_section_12_explicit_limits_vs_no_limits():
    """Verify explicit limits (top 10) are honored, while queries without limits don't have TOP clauses."""
    # With limit
    plan_lim = deterministic_warehouse_sql_generator("Give detailed top 10 bins of Plant 1268")
    assert "TOP 10" in plan_lim["sql"] or "LIMIT 10" in plan_lim["sql"]
    rows_lim, _ = execute_readonly(plan_lim["sql"])
    assert len(rows_lim) == 10

    # Without limit
    plan_no_lim = deterministic_warehouse_sql_generator("Detail bin utilization of Plant 1268")
    assert "TOP" not in plan_no_lim["sql"]


# =========================================================================
# NEW SPECIFICATION TESTS (Sections 1-23 of DETAILED MULTI-PLANT CONTEXT)
# =========================================================================

def test_section_1_and_22_both_plants_detail_and_structured_summary():
    """Verify 'Show me bin utilization of both Plant 7228 and 1258 in detail':
    - Extracts both plants [7228, 1258]
    - Separate table for Plant 7228
    - Separate table for Plant 1258
    - Structured ## Summary with ### Plant 7228 and ### Plant 1258
    - No Occupied Volume
    - Exactly one section per plant (no duplicate sections)
    """
    q = "Show me bin utilization of both Plant 7228 and 1258 in detail"
    plan = deterministic_warehouse_sql_generator(q)
    assert plan["intent"] == "multi_plant_bin_detail"
    assert plan["filters"]["plants"] == ["7228", "1258"]
    assert plan["chart_type"] == "none"  # Rule 20: No auto graph!

    mock_rows = [
        {"Bin": "NRJP2513C1", "Plant": "7228", "Capacity": 50.0, "Available Capacity": -66.54, "Utilization %": "233.1%", "Material / Inventory Information": "3 materials (200 units)"},
        {"Bin": "NRJP1308G2", "Plant": "7228", "Capacity": 50.0, "Available Capacity": -65.30, "Utilization %": "230.6%", "Material / Inventory Information": "2 materials (672 units)"},
        {"Bin": "BOR11L2P17", "Plant": "1258", "Capacity": 80.0, "Available Capacity": 12.50, "Utilization %": "84.4%", "Material / Inventory Information": "1 material (500 units)"},
        {"Bin": "BOR11L2P18", "Plant": "1258", "Capacity": 80.0, "Available Capacity": 80.00, "Utilization %": "0.0%", "Material / Inventory Information": "Empty"},
    ]
    ans = format_deterministic_answer(q, mock_rows)

    # 1. Separate tables
    assert "## Plant 7228 — Detailed Bin Utilization" in ans
    assert "## Plant 1258 — Detailed Bin Utilization" in ans
    assert ans.count("## Plant 7228 — Detailed Bin Utilization") == 1
    assert ans.count("## Plant 1258 — Detailed Bin Utilization") == 1

    # 2. Plant 7228 bins in Plant 7228 section only
    sec_7228 = ans.split("## Plant 1258")[0]
    assert "NRJP2513C1" in sec_7228
    assert "BOR11L2P17" not in sec_7228
    assert "### Mini Summary" in sec_7228

    # 3. Plant 1258 bins in Plant 1258 section only
    sec_1258 = ans.split("## Plant 1258")[1]
    assert "BOR11L2P17" in sec_1258
    assert "NRJP2513C1" not in sec_1258
    assert "### Mini Summary" in sec_1258

    # 4. Structured mini summary separated per plant immediately after each table
    assert ans.count("### Mini Summary") == 2
    assert "- Total bins:" in ans
    assert "- Utilized bins:" in ans
    assert "- Empty bins:" in ans
    assert "- Average utilization:" in ans

    # 5. Global exclusion of Occupied Volume
    assert "Occupied Volume" not in ans
    assert "Used Volume" not in ans


def test_section_5_three_plant_detailed_bin_utilization():
    """Verify 'Give detailed bin utilization of Plant 7228, Plant 1258 and Plant 1268'."""
    q = "Give detailed bin utilization of Plant 7228, Plant 1258 and Plant 1268"
    plan = deterministic_warehouse_sql_generator(q)
    assert plan["intent"] == "multi_plant_bin_detail"
    assert plan["filters"]["plants"] == ["7228", "1258", "1268"]

    mock_rows = [
        {"Bin": "B_7228", "Plant": "7228", "Capacity": 50.0, "Available Capacity": 10.0, "Utilization %": "80.0%", "Material / Inventory Information": "Empty"},
        {"Bin": "B_1258", "Plant": "1258", "Capacity": 80.0, "Available Capacity": 20.0, "Utilization %": "75.0%", "Material / Inventory Information": "Empty"},
        {"Bin": "B_1268", "Plant": "1268", "Capacity": 60.0, "Available Capacity": 30.0, "Utilization %": "50.0%", "Material / Inventory Information": "Empty"},
    ]
    ans = format_deterministic_answer(q, mock_rows)

    assert "## Plant 7228 — Detailed Bin Utilization" in ans
    assert "## Plant 1258 — Detailed Bin Utilization" in ans
    assert "## Plant 1268 — Detailed Bin Utilization" in ans

    assert ans.count("### Mini Summary") == 3


def test_section_8_no_unsolicited_rank_column():
    """Verify that detailed queries without explicit ranking intent do NOT include a Rank column."""
    queries = [
        "Show detailed bin utilization of Plant 7228",
        "Show me bin utilization of both Plant 7228 and 1258 in detail"
    ]
    for q in queries:
        plan = deterministic_warehouse_sql_generator(q)
        mock_rows = [
            {"Bin": "B01", "Plant": "7228", "Capacity": 50.0, "Available Capacity": 10.0, "Utilization %": "80.0%", "Material / Inventory Information": "Empty"}
        ]
        ans = format_deterministic_answer(q, mock_rows)
        assert "| Rank |" not in ans, f"Unsolicited Rank column found for: {q}"


def test_section_15_16_19_20_graph_rules_and_axes():
    """Verify graph generation rules:
    - No auto-generated graph for detailed queries without graph keywords.
    - Graph generated when explicitly requested with X=Bin (NOT Plant) and Y=Utilization %.
    """
    # 1. Detail without graph -> chart_type = 'none'
    q_no_graph = "Show me bin utilization of both Plant 7228 and 1258 in detail"
    plan_no_graph = deterministic_warehouse_sql_generator(q_no_graph)
    assert plan_no_graph["chart_type"] == "none"

    rows = [
        {"Bin": "NRJP2513C1", "Plant": "7228", "Capacity": 50.0, "Available Capacity": -66.54, "Utilization %": "233.1%", "Material / Inventory Information": "3 materials"},
        {"Bin": "BOR11L2P17", "Plant": "1258", "Capacity": 80.0, "Available Capacity": 12.50, "Utilization %": "84.4%", "Material / Inventory Information": "1 material"},
    ]
    opt_no_graph = optimize_response_format(q_no_graph, rows, plan_no_graph)
    assert opt_no_graph["chart_type"] == "none"

    # 2. Detail with graph -> chart_type = 'bar', X=Bin, Y=Utilization %
    q_graph = "Show detailed bin utilization of Plant 7228 and Plant 1258 with graph"
    plan_graph = deterministic_warehouse_sql_generator(q_graph)
    assert plan_graph["chart_type"] == "bar"
    assert plan_graph["chart_x"] == "Bin"
    assert plan_graph["chart_y"] == "Utilization %"

    opt_graph = optimize_response_format(q_graph, rows, plan_graph)
    assert opt_graph["chart_type"] == "bar"
    assert opt_graph["chart_x"] == "Bin"
    assert opt_graph["chart_y"] == "Utilization %"


def test_final_acceptance_tests_1_through_5():
    """Verify all 5 Final Acceptance Tests from the Multi-Plant Bin Utilization specification:
    Test 1 — Detailed two-plant query ('Show me bin utilization of both Plant 7228 and 1258 in detail')
    Test 2 — Summary two-plant query ('Summary of the bin utilization of both Plant 1268 and 1258')
    Test 3 — Explicit graph ('Show me bin utilization of Plant 7228 and 1258 with a graph')
    Test 4 — Three plants ('Show me detailed bin utilization for Plant 7228, 1258 and 1268')
    Test 5 — Existing functionality (single plant, ranking, detail)
    """
    # Test 1: Detailed two-plant query
    q1 = "Show me bin utilization of both Plant 7228 and 1258 in detail"
    p1 = deterministic_warehouse_sql_generator(q1)
    assert p1["intent"] == "multi_plant_bin_detail"
    assert p1["filters"]["plants"] == ["7228", "1258"]
    assert p1.get("chart_type") == "none"
    r1, _ = execute_readonly(p1["sql"], max_rows=10)
    a1 = format_deterministic_answer(q1, r1)
    assert "Plant 7228" in a1 and "Plant 1258" in a1
    assert "Occupied Volume" not in a1

    # Test 2: Summary two-plant query
    q2 = "Summary of the bin utilization of both Plant 1268 and 1258"
    p2 = deterministic_warehouse_sql_generator(q2)
    assert p2["intent"] == "plant_comparison"
    assert p2["filters"]["plants"] == ["1268", "1258"]
    r2, _ = execute_readonly(p2["sql"])
    assert len(r2) == 2
    assert str(r2[0]["Plant"]) == "1268"
    assert str(r2[1]["Plant"]) == "1258"
    a2 = format_deterministic_answer(q2, r2)
    assert "| Plant | Occupied Bins | Empty Bins | Total Bins | Bin Utilization % |" in a2
    assert "68.73%" in a2 and "60.80%" in a2
    assert a2.count("Plant 1268") <= 1
    assert a2.count("Plant 1258") <= 1

    # Test 3: Explicit graph
    q3 = "Show me bin utilization of Plant 7228 and 1258 with a graph"
    p3 = deterministic_warehouse_sql_generator(q3)
    assert p3["intent"] == "plant_comparison"
    r3, _ = execute_readonly(p3["sql"])
    opt3 = optimize_response_format(q3, r3, p3)
    assert opt3.get("chart_type") == "bar"

    # Test 4: Three plants
    q4 = "Show me detailed bin utilization for Plant 7228, 1258 and 1268"
    p4 = deterministic_warehouse_sql_generator(q4)
    assert p4["intent"] == "multi_plant_bin_detail"
    assert p4["filters"]["plants"] == ["7228", "1258", "1268"]

    # Test 5: Existing functionality
    p5_1 = deterministic_warehouse_sql_generator("Detail bin utilization of Plant 1268")
    assert p5_1["intent"] == "plant_bin_level_detail"
    p5_2 = deterministic_warehouse_sql_generator("Give me a summary of bin utilization for Plant 1268")
    assert p5_2["intent"] == "plant_bin_level_detail"
    p5_3 = deterministic_warehouse_sql_generator("What is the bin utilization of Plant 1268?")
    assert p5_3["intent"] == "plant_bin_utilization_detail"
    p5_4 = deterministic_warehouse_sql_generator("Top 5 bins by utilization in Plant 1268")
    assert p5_4["intent"] == "top_utilized_bins"


def test_multi_plant_detailed_comparison_separate_table_and_mini_summary():
    """Verify Section 1-16: MULTI-PLANT DETAILED COMPARISON — SEPARATE TABLE + MINI SUMMARY:
    'Compare the bin utilization of Plant 1268 and Plant 1266 in detail'
    - Intent: multi_plant_bin_detail
    - Separate table per plant (Plant 1268 first, then Plant 1266)
    - Mini summary immediately AFTER each plant's table
    - Correct fields: Total bins, Utilized bins, Empty bins, Average utilization
    - No Occupied Volume
    - No auto graph
    """
    q = "Compare the bin utilization of Plant 1268 and Plant 1266 in detail"
    plan = deterministic_warehouse_sql_generator(q)
    assert plan["intent"] == "multi_plant_bin_detail"
    assert plan["filters"]["plants"] == ["1268", "1266"]
    assert plan.get("chart_type") == "none"

    mock_rows = [
        {"Bin": "B1268_01", "Plant": "1268", "Capacity": 50.0, "Available Capacity": 10.0, "Utilization %": "80.0%", "Material / Inventory Information": "MatA (10 units)"},
        {"Bin": "B1266_01", "Plant": "1266", "Capacity": 60.0, "Available Capacity": 20.0, "Utilization %": "66.7%", "Material / Inventory Information": "Empty"}
    ]
    ans = format_deterministic_answer(q, mock_rows)

    # 1. Check sections exist in order
    assert "Plant 1268" in ans
    assert "Plant 1266" in ans
    idx_1268 = ans.index("Plant 1268")
    idx_1266 = ans.index("Plant 1266")
    assert idx_1268 < idx_1266

    # 2. Check each plant has its table and immediately following Mini Summary
    sections = ans.split("\n\n---\n\n")
    assert len(sections) == 2
    for s in sections:
        assert "| Bin | Capacity | Available Capacity | Utilization % | Material / Inventory Information |" in s
        assert "### Mini Summary" in s
        assert "- Total bins:" in s
        assert "- Utilized bins:" in s
        assert "- Empty bins:" in s
        assert "- Average utilization:" in s

    # 3. Check Occupied Volume excluded
    assert "Occupied Volume" not in ans
    assert "Used Volume" not in ans


