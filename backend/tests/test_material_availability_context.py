import pytest
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    format_deterministic_answer,
    optimize_response_format,
    is_material_availability_intent,
    extract_and_update_conversation_state,
)
from backend.app.db import execute_readonly


def test_material_availability_intent_detection():
    # Positive signals
    assert is_material_availability_intent("Which materials are available in Plant 7228?")
    assert is_material_availability_intent("What materials are in Plant 7228?")
    assert is_material_availability_intent("Show materials in Plant 7228.")
    assert is_material_availability_intent("List materials available in Plant 7228.")
    assert is_material_availability_intent("Which materials does Plant 7228 have?")
    assert is_material_availability_intent("What items are available in Plant 7228?")
    assert is_material_availability_intent("Show me all materials stored in Plant 7228.")
    assert is_material_availability_intent("Which inventory materials are present in Plant 7228?")
    assert is_material_availability_intent("Which materials are available?")
    assert is_material_availability_intent("Show all available materials.")
    assert is_material_availability_intent("List all warehouse materials.")
    assert is_material_availability_intent("Which materials are available in Plant 1258 and 7228?")
    assert is_material_availability_intent("Which materials are available in Plant 7228 with quantity above 1000?")
    assert is_material_availability_intent("Which materials are availble in Plant 7228?")
    assert is_material_availability_intent("What matirials are in Plant 7228?")

    # Negative signals (Boundaries)
    assert not is_material_availability_intent("How many materials are in Plant 7228?")
    assert not is_material_availability_intent("How many materials are available in Plant 7228?")
    assert not is_material_availability_intent("Give me inventory summary for Plant 7228.")
    assert not is_material_availability_intent("Show inventory summary for Plant 7228.")
    assert not is_material_availability_intent("What is the total inventory of Plant 7228?")
    assert not is_material_availability_intent("Which material has the highest quantity?")
    assert not is_material_availability_intent("Which bin holds the lowest utilization?")


def test_single_plant_material_listing():
    q = "Which materials are available in Plant 7228?"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "material_availability"
    
    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 974
    
    opt = optimize_response_format(q, rows, gen)
    assert opt["output_type"] == "table"
    
    ans = format_deterministic_answer(q, rows)
    assert "### 📦 Materials Available in Plant 7228" in ans
    assert "974" in ans


def test_multi_plant_material_listing():
    q = "Which materials are available in Plant 1258 and 7228?"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "material_availability"
    
    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 2427
    
    plants_in_results = {str(r.get("Plant")) for r in rows}
    assert "1258" in plants_in_results
    assert "7228" in plants_in_results
    
    ans = format_deterministic_answer(q, rows)
    assert "Plant 1258" in ans and "Plant 7228" in ans


def test_all_plant_material_listing():
    q = "Show all available materials."
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "material_availability"
    
    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 5718
    
    ans = format_deterministic_answer(q, rows)
    assert "Available Warehouse Materials" in ans
    assert "5,718" in ans


def test_filtered_material_listing():
    q = "Which materials are available in Plant 7228 with quantity above 1000?"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "material_availability"
    
    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 362
    assert all(r["Total Stock Qty"] > 1000 for r in rows)
    
    ans = format_deterministic_answer(q, rows)
    assert "362" in ans
    assert "above 1,000" in ans


def test_strict_boundaries_preserved():
    # 1. Count
    q_count = "How many materials are available in Plant 7228?"
    gen_c = deterministic_warehouse_sql_generator(q_count)
    assert gen_c["intent"] == "unique_materials_count"
    rows_c, _ = execute_readonly(gen_c["sql"])
    ans_c = format_deterministic_answer(q_count, rows_c)
    assert "974" in ans_c
    assert "unique materials" in ans_c

    # 2. Inventory summary
    q_sum = "Give me inventory summary for Plant 7228."
    gen_s = deterministic_warehouse_sql_generator(q_sum)
    assert gen_s["intent"] == "inventory_summary"
    rows_s, _ = execute_readonly(gen_s["sql"])
    opt_s = optimize_response_format(q_sum, rows_s, gen_s)
    assert opt_s["output_type"] == "kpi"

    # 3. Highest quantity
    q_high = "Which material has the highest quantity?"
    gen_h = deterministic_warehouse_sql_generator(q_high)
    assert gen_h["intent"] == "material_max_quantity"


def test_invalid_plant():
    q = "Which materials are available in Plant 1001?"
    gen = deterministic_warehouse_sql_generator(q)
    rows, _ = execute_readonly(gen["sql"])
    ans = format_deterministic_answer(q, rows)
    assert "No matching warehouse records were found" in ans


def test_followup_conversation_context():
    hist = [
        {"role": "user", "content": "Which materials are available in Plant 7228?"},
        {"role": "assistant", "content": "Found 974 available materials in Plant 7228."}
    ]
    followup_q = "What about Plant 1258?"
    gen = deterministic_warehouse_sql_generator(followup_q, history=hist)
    assert gen["intent"] == "material_availability"
    
    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 1453
    
    ans = format_deterministic_answer(followup_q, rows)
    assert "Plant 1258" in ans
    assert "1,453" in ans


def test_reverse_availability_queries():
    # 1. In which plants is material BCH20DBB21 available?
    q1 = "In which plants is material BCH20DBB21 available?"
    gen1 = deterministic_warehouse_sql_generator(q1)
    assert gen1["intent"] == "material_plants_lookup"
    rows1, _ = execute_readonly(gen1["sql"])
    assert len(rows1) == 4
    ans1 = format_deterministic_answer(q1, rows1)
    assert "BCH20DBB21" in ans1
    assert "Plant 1258" in ans1 and "Plant 7228" in ans1

    # 2. Which plants contain material BCH20DBB21?
    q2 = "Which plants contain material BCH20DBB21?"
    gen2 = deterministic_warehouse_sql_generator(q2)
    assert gen2["intent"] == "material_plants_lookup"

    # 3. Where is material BCH20DBB21 stored?
    q3 = "Where is material BCH20DBB21 stored?"
    gen3 = deterministic_warehouse_sql_generator(q3)
    assert gen3["intent"] == "material_plants_lookup"

    # 4. Is material BCH20DBB21 available in Plant 7228?
    q4 = "Is material BCH20DBB21 available in Plant 7228?"
    gen4 = deterministic_warehouse_sql_generator(q4)
    assert gen4["intent"] == "material_plants_lookup"
    rows4, _ = execute_readonly(gen4["sql"])
    assert len(rows4) == 1
    ans4 = format_deterministic_answer(q4, rows4)
    assert "Yes" in ans4
    assert "Plant 7228" in ans4


def test_common_materials_queries():
    q = "Which materials are common in Plant 1258 and 7228?"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "common_materials"
    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 436
    ans = format_deterministic_answer(q, rows)
    assert "436" in ans
    assert "Common Materials" in ans or "common materials" in ans.lower()


def test_unique_and_difference_materials_queries():
    # 1. Which materials exist only in Plant 1258?
    q1 = "Which materials exist only in Plant 1258?"
    gen1 = deterministic_warehouse_sql_generator(q1)
    assert gen1["intent"] == "unique_materials"
    rows1, _ = execute_readonly(gen1["sql"])
    ans1 = format_deterministic_answer(q1, rows1)
    assert "Plant 1258" in ans1
    assert "exclusive" in ans1 or "Unique" in ans1

    # 2. Which materials are present in Plant 1258 but not Plant 7228?
    q2 = "Which materials are present in Plant 1258 but not Plant 7228?"
    gen2 = deterministic_warehouse_sql_generator(q2)
    assert gen2["intent"] == "unique_materials"
    rows2, _ = execute_readonly(gen2["sql"])
    assert len(rows2) == 1017
    ans2 = format_deterministic_answer(q2, rows2)
    assert "1,017" in ans2
    assert "Plant 1258" in ans2 and "Plant 7228" in ans2

    # 3. Which materials are missing from Plant 7228 compared with Plant 1258?
    q3 = "Which materials are missing from Plant 7228 compared with Plant 1258?"
    gen3 = deterministic_warehouse_sql_generator(q3)
    assert gen3["intent"] == "unique_materials"
    rows3, _ = execute_readonly(gen3["sql"])
    assert len(rows3) == 1017


def test_names_only_modifier():
    q = "Only show material names in Plant 1268"
    gen = deterministic_warehouse_sql_generator(q)
    rows, _ = execute_readonly(gen["sql"])
    ans = format_deterministic_answer(q, rows)
    # ans should be comma-separated material codes without markdown headers
    assert "###" not in ans
    assert "," in ans
    first_mat = rows[0]["Material"]
    assert first_mat in ans
