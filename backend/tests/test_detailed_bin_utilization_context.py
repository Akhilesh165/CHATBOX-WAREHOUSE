import pytest
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    format_deterministic_answer,
    is_bin_level_detail_intent,
    extract_and_update_conversation_state
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
    assert "## Plant 1268 — Bin Utilization" in ans
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
    assert "## Plant 1268 — Bin Utilization" in ans
    assert "## Plant 1266 — Bin Utilization" in ans

    # Verify order: Plant 1268 section comes first, then Plant 1266
    p1268_idx = ans.index("## Plant 1268 — Bin Utilization")
    p1266_idx = ans.index("## Plant 1266 — Bin Utilization")
    assert p1268_idx < p1266_idx

    # Verify both sections have their own table headers
    sections = ans.split("## Plant ")
    # sections[0] is empty prefix, sections[1] is 1268, sections[2] is 1266
    assert len(sections) == 3
    for s in sections[1:]:
        assert "| Bin | Capacity | Available Capacity | Utilization % | Material / Inventory Information |" in s


def test_section_6_dynamic_three_plant_comparison():
    """Verify dynamic support for 3 plants with 3 separate tables."""
    q = "Compare detailed top 5 bins of Plant 1268, Plant 1266 and Plant 7228"
    plan = deterministic_warehouse_sql_generator(q)
    assert plan["intent"] == "multi_plant_bin_detail"

    rows, _ = execute_readonly(plan["sql"])
    assert len(rows) == 15
    ans = format_deterministic_answer(q, rows)
    assert "## Plant 1268 — Bin Utilization" in ans
    assert "## Plant 1266 — Bin Utilization" in ans
    assert "## Plant 7228 — Bin Utilization" in ans


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
    assert "## Plant 1268 — Bin Utilization" not in normal_ans  # not bin-level table

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
    assert "## Plant 1266 — Bin Utilization" in t2_ans
    history.append({"role": "user", "content": t2_q})
    history.append({"role": "assistant", "content": t2_ans})

    # Turn 3: Follow-up on Plant 7228
    t3_q = "What about Plant 7228?"
    t3_plan = deterministic_warehouse_sql_generator(t3_q, history=history)
    assert t3_plan["intent"] == "plant_bin_level_detail"
    assert t3_plan["filters"]["plant"] == "7228"
    t3_rows, _ = execute_readonly(t3_plan["sql"], max_rows=10)
    t3_ans = format_deterministic_answer(t3_q, t3_rows)
    assert "## Plant 7228 — Bin Utilization" in t3_ans
    history.append({"role": "user", "content": t3_q})
    history.append({"role": "assistant", "content": t3_ans})

    # Turn 4: "Compare those two"
    t4_q = "Compare those two"
    t4_plan = deterministic_warehouse_sql_generator(t4_q, history=history)
    assert t4_plan["intent"] == "multi_plant_bin_detail"
    assert t4_plan["filters"]["plants"] == ["1266", "7228"]
    t4_rows = t2_rows + t3_rows
    t4_ans = format_deterministic_answer(t4_q, t4_rows)
    assert "## Plant 1266 — Bin Utilization" in t4_ans
    assert "## Plant 7228 — Bin Utilization" in t4_ans


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
