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
