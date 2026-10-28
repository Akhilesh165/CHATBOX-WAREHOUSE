import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    extract_specific_bins,
    format_deterministic_answer
)
from backend.app.db import execute_readonly

@pytest.fixture
def anyio_backend():
    return "asyncio"

# 1. TEST SPECIFIC BIN EXTRACTION (ALL USER PROMPT PHRASINGS)
def test_specific_bin_extraction():
    test_cases = [
        ("Tell me about bin S105290412", ["S105290412"]),
        ("Show me information about S105290412", ["S105290412"]),
        ("What is in S105290412?", ["S105290412"]),
        ("Show me utilization of S105290412", ["S105290412"]),
        ("What is the utilization of S105290412?", ["S105290412"]),
        ("Show me utilization of 105290412 bin in Plant 1266", ["S105290412"]),
        ("What material is stored in S105290412?", ["S105290412"]),
        ("Which plant does S105290412 belong to?", ["S105290412"]),
        ("Give me details of bin S105290412", ["S105290412"]),
        ("What is the capacity of S105290412?", ["S105290412"]),
        ("How much inventory is in S105290412?", ["S105290412"]),
        ("Tell me the status of S105290412", ["S105290412"]),
        ("S105290412", ["S105290412"]),
        ("information about 105290412", ["S105290412"]),
        ("details for bin 105290412", ["S105290412"]),
        ("the S105290412 bin", ["S105290412"]),
        ("S105290412's utilization", ["S105290412"]),
        ("Show me available capacity of S105290412", ["S105290412"]),
        ("What is the utilization of bin NONEXISTENT123?", ["NONEXISTENT123"]),
    ]
    for q, expected in test_cases:
        res = extract_specific_bins(q)
        assert res == expected, f"Failed extraction for: '{q}'. Got {res}, expected {expected}"

# 2. DO NOT TRIGGER SPECIFIC BIN FOR MULTI-BIN, RANKING, OR MULTI-PLANT
def test_specific_bin_does_not_break_other_intents():
    multi_bin = extract_specific_bins("Show me utilization of S105290412 and S105290413")
    assert len(multi_bin) == 2

    ranking = extract_specific_bins("Show me the top 10 utilized bins")
    assert len(ranking) == 0

    multi_plant = extract_specific_bins("compare the bin utilization of plant 1268 and 1266 in detail")
    assert len(multi_plant) == 0

    single_plant = extract_specific_bins("Show me bin utilization of Plant 1266 in detail")
    assert len(single_plant) == 0

# 3. UNIT TEST DETERMINISTIC SQL GENERATOR FOR SPECIFIC BIN
def test_sql_generator_specific_bin():
    plan = deterministic_warehouse_sql_generator("Show me utilization of 105290412 bin in Plant 1266")
    assert plan.get("is_single_specific_bin") is True
    assert plan.get("output_type") == "text"
    assert "S105290412" in plan["sql"] or "105290412" in plan["sql"]
    assert "Plant = '1266'" in plan["sql"]

# 4. UNIT TEST FORMAT DETERMINISTIC ANSWER (SINGLE-LINE STYLES)
def test_single_line_styles():
    rows = [{
        "Bin": "S105290412",
        "Plant": 1266,
        "Storage Location": "STRD",
        "Capacity": 48.89,
        "Unit": "FT³",
        "Occupied Volume": 28.32,
        "Available Capacity": 20.57,
        "Utilization %": "57.93%",
        "Total Qty": 96.0,
        "UOM": "EA",
        "Material Count": 1,
        "Material Info": "BKE15LSSB28 (96.0 EA)"
    }]

    # Utilization with plant
    ans1 = format_deterministic_answer("Show me utilization of 105290412 bin in Plant 1266", rows)
    assert ans1 == "Bin 105290412 in Plant 1266 has 57.93% utilization."
    assert "\n" not in ans1
    assert "Occupied Volume" not in ans1

    # Utilization without plant
    ans2 = format_deterministic_answer("What is the utilization of S105290412?", rows)
    assert ans2 == "Bin S105290412 has 57.93% utilization."
    assert "\n" not in ans2
    assert "Occupied Volume" not in ans2

    # Material
    ans3 = format_deterministic_answer("What material is stored in S105290412?", rows)
    assert "contains BKE15LSSB28 (96.0 EA)" in ans3
    assert "\n" not in ans3

    # Capacity
    ans4 = format_deterministic_answer("What is the capacity of S105290412?", rows)
    assert ans4 == "Bin S105290412 has a capacity of 48.89 FT³."
    assert "\n" not in ans4

    # Available capacity
    ans5 = format_deterministic_answer("Show me available capacity of S105290412", rows)
    assert ans5 == "Bin S105290412 has 20.57 FT³ available capacity."
    assert "\n" not in ans5

    # Plant lookup
    ans6 = format_deterministic_answer("Which plant does S105290412 belong to?", rows)
    assert ans6 == "Bin S105290412 belongs to Plant 1266."
    assert "\n" not in ans6

    # Details (Concise 1 line, NO table)
    ans7 = format_deterministic_answer("Give me details of bin S105290412", rows)
    assert "Bin S105290412 is in Plant 1266, has 48.89 FT³ capacity, 20.57 FT³ available capacity, and 57.93% utilization." == ans7
    assert "\n" not in ans7

    # Occupied Volume explicitly asked
    ans8 = format_deterministic_answer("What is the occupied volume of bin S105290412?", rows)
    assert ans8 == "Bin S105290412 has 28.32 FT³ occupied volume."
    assert "\n" not in ans8

# 5. TEST NONEXISTENT SPECIFIC BIN
def test_nonexistent_bin():
    ans = format_deterministic_answer("What is the utilization of bin NONEXISTENT123?", [])
    assert ans == "No matching warehouse records were found for your query in the database."
    assert "\n" not in ans

# 6. INTEGRATION END-TO-END TEST VIA API
@pytest.mark.anyio
async def test_api_specific_bin_queries():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Example 1: Utilization with plant
        res1 = await client.post("/api/chat", json={
            "message": "Show me utilization of 105290412 bin in Plant 1266"
        })
        assert res1.status_code == 200
        d1 = res1.json()
        assert d1["output_type"] == "text"
        assert d1["rows"] == []
        assert d1["chart"]["type"] == "none"
        assert "57.93%" in d1["answer"]
        assert len(d1["answer"].splitlines()) == 1
        assert "Occupied Volume" not in d1["answer"]

        # Example 2: What material is stored
        res2 = await client.post("/api/chat", json={
            "message": "What material is stored in S105290412?"
        })
        assert res2.status_code == 200
        d2 = res2.json()
        assert d2["output_type"] == "text"
        assert d2["rows"] == []
        assert "BKE15LSSB28" in d2["answer"]
        assert len(d2["answer"].splitlines()) == 1

        # Example 3: Details (Must be 1 line, NO table, NO chart)
        res3 = await client.post("/api/chat", json={
            "message": "Give me details of bin S105290412"
        })
        assert res3.status_code == 200
        d3 = res3.json()
        assert d3["output_type"] == "text"
        assert d3["rows"] == []
        assert "capacity" in d3["answer"].lower()
        assert "utilization" in d3["answer"].lower()
        assert len(d3["answer"].splitlines()) == 1

        # Example 4: Nonexistent bin
        res4 = await client.post("/api/chat", json={
            "message": "What is the utilization of bin NONEXISTENT123?"
        })
        assert res4.status_code == 200
        d4 = res4.json()
        assert d4["output_type"] == "text"
        assert d4["rows"] == []
        assert d4["answer"] == "No matching warehouse records were found for your query in the database."

        # Example 5: Explicit graph request exception
        res5 = await client.post("/api/chat", json={
            "message": "Show utilization of S105290412 with a graph"
        })
        assert res5.status_code == 200
        d5 = res5.json()
        assert d5["chart"]["type"] in ["bar", "pie", "line"]
