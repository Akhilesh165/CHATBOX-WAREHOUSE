"""Automated Test Suite for the 21 Recommended Questions from the Warehouse BI Implementation Guide.
Verifies:
1. Semantic understanding & concept mapping
2. Context retention across follow-ups
3. Correct analytical task classification and query plan
4. Canonical formulas & join keys
5. Output format selection (KPI, Table, Chart)
6. Anti-hallucination / qualification
"""

import pytest
from backend.app.llm import deterministic_warehouse_sql_generator, format_deterministic_answer, optimize_response_format

def test_q1_how_full_is_the_warehouse_right_now():
    """Q1: 'How full is the warehouse right now?' -> Warehouse/Bin Utilization KPI/Comparison"""
    res = deterministic_warehouse_sql_generator("How full is the warehouse right now?")
    assert "dbo.ZWMS_BIN_MASTER" in res["sql"]
    assert "BinUtilizationPct" in res["sql"] or "VolumeUtilizationPct" in res["sql"] or "SUM(b.Volume)" in res["sql"]
    assert res["intent"] == "bin_utilization"

def test_q2_percentage_of_storage_capacity_used():
    """Q2: 'What percentage of our storage capacity are we using?' -> Utilization percentage"""
    res = deterministic_warehouse_sql_generator("What percentage of our storage capacity are we using?")
    assert "dbo.ZWMS_BIN_MASTER" in res["sql"]
    assert "BinUtilizationPct" in res["sql"] or "VolumeUtilizationPct" in res["sql"]

def test_q3_show_the_10_fullest_bins():
    """Q3: 'Show the 10 fullest bins.' -> Ranking of most utilized bins (TOP 10 DESC)"""
    res = deterministic_warehouse_sql_generator("Show the 10 fullest bins.")
    assert "TOP 10" in res["sql"]
    assert "DESC" in res["sql"]
    assert "dbo.ZWMS_BIN_MASTER" in res["sql"]
    assert res["intent"] == "top_utilized_bins"

def test_q4_which_bins_are_using_the_least_space():
    """Q4: 'Which bins are using the least space?' -> Least utilized bins (ASC)"""
    res = deterministic_warehouse_sql_generator("Which bins are using the least space?")
    assert "ASC" in res["sql"]
    assert "dbo.ZWMS_BIN_MASTER" in res["sql"]
    assert res["intent"] == "least_utilized_bins"

def test_q5_to_q7_multi_turn_bin_utilization_flow():
    """Q5-Q7: Follow-up chain:
    Q5: What about the least utilized ones?
    Q6: Only for Plant 1258.
    Q7: Show me the top 5 instead.
    """
    history = [
        {"role": "user", "content": "Show me the top 10 most utilized bins."},
        {"role": "assistant", "content": "Here are the top 10 most utilized bins."}
    ]
    
    # Q5: Turn 2
    res_q5 = deterministic_warehouse_sql_generator("What about the least utilized ones?", history=history)
    assert "ASC" in res_q5["sql"]
    assert "TOP 10" in res_q5["sql"]
    assert res_q5["intent"] == "least_utilized_bins"

    # Q6: Turn 3
    history.extend([
        {"role": "user", "content": "What about the least utilized ones?"},
        {"role": "assistant", "content": "Here are the least utilized bins."}
    ])
    res_q6 = deterministic_warehouse_sql_generator("Only for Plant 1258.", history=history)
    assert "1258" in res_q6["sql"]
    assert "ASC" in res_q6["sql"]
    assert "TOP 10" in res_q6["sql"]

    # Q7: Turn 4
    history.extend([
        {"role": "user", "content": "Only for Plant 1258."},
        {"role": "assistant", "content": "Here are the least utilized bins for Plant 1258."}
    ])
    res_q7 = deterministic_warehouse_sql_generator("Show me the top 5 instead.", history=history)
    assert "1258" in res_q7["sql"]
    assert "DESC" in res_q7["sql"]
    assert "TOP 5" in res_q7["sql"]
    assert res_q7["intent"] == "top_utilized_bins"

def test_q8_to_q10_empty_bins_flow():
    """Q8-Q10: Follow-up chain:
    Q8: Show me empty bins.
    Q9: Only in Plant 1258.
    Q10: How many are there?
    """
    # Q8
    res_q8 = deterministic_warehouse_sql_generator("Show me empty bins.")
    assert "dbo.ZWMS_BIN_MASTER" in res_q8["sql"]
    assert "(i.BinNo IS NULL OR i.UnrestrictedQty = 0)" in res_q8["sql"]
    assert res_q8["output_type"] == "table"

    # Q9
    history = [
        {"role": "user", "content": "Show me empty bins."},
        {"role": "assistant", "content": "Here are empty bins."}
    ]
    res_q9 = deterministic_warehouse_sql_generator("Only in Plant 1258.", history=history)
    assert "1258" in res_q9["sql"]
    assert "(i.BinNo IS NULL OR i.UnrestrictedQty = 0)" in res_q9["sql"]

    # Q10
    history.extend([
        {"role": "user", "content": "Only in Plant 1258."},
        {"role": "assistant", "content": "Here are empty bins in Plant 1258."}
    ])
    res_q10 = deterministic_warehouse_sql_generator("How many are there?", history=history)
    assert "1258" in res_q10["sql"]
    assert "COUNT(DISTINCT" in res_q10["sql"]
    assert res_q10["output_type"] == "kpi"

def test_q11_where_can_i_put_new_inventory():
    """Q11: 'Where can I put new inventory right now?' -> Available/Empty put-away bins"""
    res = deterministic_warehouse_sql_generator("Where can I put new inventory right now?")
    assert "(i.BinNo IS NULL OR i.UnrestrictedQty = 0)" in res["sql"]
    assert res["intent"] == "putaway_bins"
    assert res["output_type"] == "table"

def test_q12_which_inventory_materials_dont_have_dimensions():
    """Q12: 'Which inventory materials don't have dimensions?' -> Data Quality / Exception Table"""
    res = deterministic_warehouse_sql_generator("Which inventory materials don't have dimensions?")
    assert "dbo.ZWMS_INVENTORY" in res["sql"]
    assert "dbo.ZWMS_MATERIAL_MASTER" in res["sql"]
    assert "m.MaterialCode IS NULL" in res["sql"] or "m.Length IS NULL" in res["sql"]
    assert res["intent"] == "data_quality_check"
    assert res["output_type"] == "table"

def test_q13_find_products_without_physical_size_information():
    """Q13: 'Find products without physical size information.' -> Maps to Data Quality / Missing Dimensions"""
    res = deterministic_warehouse_sql_generator("Find products without physical size information.")
    assert "dbo.ZWMS_INVENTORY" in res["sql"]
    assert "dbo.ZWMS_MATERIAL_MASTER" in res["sql"]
    assert res["intent"] == "data_quality_check"

def test_q14_materials_in_inventory_not_in_material_volume_master():
    """Q14: 'Which materials exist in Inventory Master but not Material Volume Master?' -> Rule DQ-001"""
    res = deterministic_warehouse_sql_generator("Which materials exist in Inventory Master but not Material Volume Master?")
    assert "dbo.ZWMS_INVENTORY" in res["sql"]
    assert "dbo.ZWMS_MATERIAL_MASTER" in res["sql"]
    assert res["intent"] in ["materials_missing_from_volume_master", "data_quality_check"]

def test_q15_which_inventory_materials_have_incomplete_dimensions():
    """Q15: 'Which inventory materials have incomplete dimensions?'"""
    res = deterministic_warehouse_sql_generator("Which inventory materials have incomplete dimensions?")
    assert "dbo.ZWMS_INVENTORY" in res["sql"]
    assert "dbo.ZWMS_MATERIAL_MASTER" in res["sql"]
    assert res["intent"] == "data_quality_check"

def test_q16_show_materials_in_plant_1258():
    """Q16: 'Show materials in Plant 1258.' -> Plant material filter table"""
    res = deterministic_warehouse_sql_generator("Show materials in Plant 1258.")
    assert "Plant = '1258'" in res["sql"]
    assert "dbo.ZWMS_INVENTORY" in res["sql"]
    assert res["output_type"] == "table"

def test_q17_which_bins_in_plant_1258_are_empty():
    """Q17: 'Which bins in Plant 1258 are empty?' -> Empty bins scoped to Plant 1258"""
    res = deterministic_warehouse_sql_generator("Which bins in Plant 1258 are empty?")
    assert "1258" in res["sql"]
    assert "(i.BinNo IS NULL OR i.UnrestrictedQty = 0)" in res["sql"]
    assert res["intent"] == "putaway_bins"

def test_q18_compare_inventory_across_storage_locations():
    """Q18: 'Compare inventory across storage locations.' -> Comparison by storage location"""
    res = deterministic_warehouse_sql_generator("Compare inventory across storage locations.")
    assert "StorageLocation" in res["sql"]
    assert "GROUP BY StorageLocation" in res["sql"] or "GROUP BY" in res["sql"]
    assert res["output_type"] in ["bar_chart", "table"]

def test_q19_show_warehouse_utilization_over_time():
    """Q19: 'Show warehouse utilization over time.' -> Trend line chart"""
    res = deterministic_warehouse_sql_generator("Show warehouse utilization over time.")
    assert "FullyVestedOn" in res["sql"] or "Month" in res["sql"] or "STRFTIME" in res["sql"]
    assert res["output_type"] == "line_chart"

def test_q20_are_we_running_out_of_storage_space():
    """Q20: 'Are we running out of storage space?' -> Warehouse bin utilization overview"""
    res = deterministic_warehouse_sql_generator("Are we running out of storage space?")
    assert "dbo.ZWMS_BIN_MASTER" in res["sql"]
    assert "BinUtilizationPct" in res["sql"] or "VolumeUtilizationPct" in res["sql"] or "SUM(b.Volume)" in res["sql"]

def test_q21_specific_bin_material_lookup():
    """Q21: 'show me the material of this bin NRJP2124D2' -> Specific bin lookup without regex group attribute errors"""
    res = deterministic_warehouse_sql_generator("show me the material of this bin NRJP2124D2")
    assert "NRJP2124D2" in res["sql"]
    assert res["intent"] == "bin_lookup"
    assert res["filters"]["bin"] == "NRJP2124D2"

def test_explicit_entity_scoping_and_primary_metric_rule():
    """Verifies that entity-scoped queries explicitly identify the entity and prioritize the requested metric without warehouse-wide descriptions."""
    # 1. Plant-scoped bin utilization
    plant_rows = [
        {"Plant": "1258", "TotalBins": 100, "OccupiedBins": 75, "EmptyBins": 25, "BinUtilizationPct": 75.0, "TotalBinCapacityVolume": 1000.0, "OccupiedBinVolume": 750.0, "VolumeUtilizationPct": 75.0}
    ]
    ans1 = format_deterministic_answer("What is the bin utilization for Plant 1258?", plant_rows)
    assert "Plant 1258" in ans1
    assert "overall warehouse" not in ans1.lower()
    assert "warehouse network" not in ans1.lower()
    assert "75.0%" in ans1

    # 2. Specific Bin utilization
    bin_rows = [
        {"Bin": "B001", "Plant": "1258", "Storage Location": "S001", "Bin Capacity": "100 FT3", "Occupied Volume": "85 FT3", "Utilization %": "85.0%"}
    ]
    ans2 = format_deterministic_answer("What is the utilization of bin B001?", bin_rows)
    assert "Bin B001" in ans2
    assert "85.0%" in ans2
    assert "overall warehouse" not in ans2.lower()

    # 3. Plant-scoped Empty Bins Count
    empty_rows = [{"Empty Bins Count": 25}]
    ans3 = format_deterministic_answer("How many empty bins in Plant 1258?", empty_rows)
    assert "Plant 1258" in ans3
    assert "across the warehouse network" not in ans3.lower()

    # 4. Plant-scoped Average Inventory per Occupied Bin
    avg_rows = [{"AvgInventoryPerOccupiedBin": 45.5, "TotalQuantity": 4550.0, "OccupiedBins": 100}]
    ans4 = format_deterministic_answer("Average inventory per occupied bin in Plant 1258", avg_rows)
    assert "Plant 1258" in ans4
    assert "45.50" in ans4
    assert "across the warehouse network" not in ans4.lower()

def test_specific_bin_lookups_after_empty_bin_history():
    """Verify specific bin lookup does not inherit previous empty bins state."""
    history = [
        {"role": "user", "content": "Are there any empty bins in Plant 7228?"},
        {"role": "assistant", "content": "Found 50 empty bins in Plant 7228."}
    ]
    res = deterministic_warehouse_sql_generator("Which plant does bin NRJP2124D2 belong to?", history=history)
    assert res["intent"] == "bin_plant_lookup"
    assert "NRJP2124D2" in res["sql"]
    assert res["output_type"] == "text"

    ans = format_deterministic_answer("Which plant does bin NRJP2124D2 belong to?", [{"Plant": "7228", "StorageLocation": "B2B"}])
    assert "Bin **NRJP2124D2** belongs to **Plant 7228**" in ans

def test_plant_bin_utilization_detail_template():
    """Verify plant_bin_utilization_detail template generates summary, relevant KPIs, and detail offer."""
    res = deterministic_warehouse_sql_generator("Give me bin utilization details for plant 7228")
    assert res["intent"] == "plant_bin_utilization_detail"
    assert res["filters"]["plant"] == "7228"
    assert "follow_up_action" in res
    assert res["follow_up_action"]["action"] == "generate_detail"
    assert "relevant_kpis" in res

    rows = [{
        "Plant": "7228",
        "Total Bins": 9514,
        "Occupied Bins": 7522,
        "Empty Bins": 1992,
        "Bin Utilization %": "79.1%"
    }]
    ans = format_deterministic_answer("Give me bin utilization details for plant 7228", rows)
    assert "The bin utilization for **Plant 7228** is **79.1%**" in ans
    assert "7,522" in ans
    assert "1,992" in ans
    assert "\n" not in ans  # strictly max 2 lines / single concise statement

def test_plant_bin_utilization_expansion():
    """Verify follow-up confirmation expands into detailed storage location breakdown with bar chart."""
    history = [
        {"role": "user", "content": "Give me bin utilization details for plant 7228"},
        {"role": "assistant", "content": "The bin utilization for Plant 7228 is 79.1%."}
    ]
    res = deterministic_warehouse_sql_generator("Yes, please generate a detailed version", history=history)
    assert res["intent"] == "plant_bin_utilization_detailed_analysis"
    assert res["filters"]["plant"] == "7228"
    assert res["chart_type"] == "bar"
    assert res["chart_x"] == "Storage Location"
    assert "StorageLocation" in res["sql"]




