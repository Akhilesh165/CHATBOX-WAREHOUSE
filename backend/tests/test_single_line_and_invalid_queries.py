import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    is_unsupported_nonexistent_query,
    extract_invalid_plant_specified,
    is_single_line_requested,
    is_number_only_requested,
    extract_only_number,
    format_deterministic_answer
)

@pytest.fixture
def anyio_backend():
    return "asyncio"

# 1. TEST NONEXISTENT & INVALID QUERY DETECTION (UNIT)
def test_nonexistent_and_invalid_detection():
    # Negative / Nonexistent queries
    assert is_unsupported_nonexistent_query("find bins that do not exist") is True
    assert is_unsupported_nonexistent_query("show bins that don't exist") is True
    assert is_unsupported_nonexistent_query("find nonexistent bins") is True
    assert is_unsupported_nonexistent_query("list bins that are not present in the database") is True
    assert is_unsupported_nonexistent_query("show utilization for an invalid plant") is True
    assert is_unsupported_nonexistent_query("details of a nonexistent bin") is True

    # Valid queries that should NOT trigger nonexistent detection
    assert is_unsupported_nonexistent_query("inventory items missing from volume master") is False
    assert is_unsupported_nonexistent_query("materials missing from volume master") is False
    assert is_unsupported_nonexistent_query("show completely empty bins") is False
    assert is_unsupported_nonexistent_query("how many empty bins in plant 1268") is False

    # Invalid Plant detection
    assert extract_invalid_plant_specified("show utilization for plant 9999") == "9999"
    assert extract_invalid_plant_specified("bins in plant abcd") == "ABCD"
    assert extract_invalid_plant_specified("plant 0000 capacity") == "0000"
    assert extract_invalid_plant_specified("show utilization for an invalid plant") == "invalid"
    
    # Valid plants should not trigger invalid plant
    assert extract_invalid_plant_specified("bins in plant 1258") is None
    assert extract_invalid_plant_specified("bins in plant 1266") is None
    assert extract_invalid_plant_specified("bins in plant 1268") is None
    assert extract_invalid_plant_specified("bins in plant 7228") is None


# 2. TEST SQL GENERATOR FOR NONEXISTENT & INVALID QUERIES
def test_sql_generator_nonexistent_queries():
    plan1 = deterministic_warehouse_sql_generator("Find bins that do not exist")
    assert plan1["intent"] == "no_matching_records"
    assert plan1.get("is_invalid_query") is True

    plan2 = deterministic_warehouse_sql_generator("Show bins that don't exist")
    assert plan2["intent"] == "no_matching_records"
    assert plan2.get("is_invalid_query") is True

    plan3 = deterministic_warehouse_sql_generator("Show utilization for an invalid plant")
    assert plan3["intent"] == "no_matching_records"
    assert plan3.get("is_invalid_query") is True

    plan4 = deterministic_warehouse_sql_generator("Show utilization for Plant 9999")
    assert "9999" in plan4["sql"]

    # Specific nonexistent bin lookup should target that specific bin, NOT list all bins
    plan5 = deterministic_warehouse_sql_generator("Find bin XYZ999")
    assert "XYZ999" in plan5["sql"]
    assert "find_bins_list" != plan5["intent"]

    plan6 = deterministic_warehouse_sql_generator("What material is stored in bin INVALID123?")
    assert "INVALID123" in plan6["sql"]
    assert "find_bins_list" != plan6["intent"]


# 3. TEST SINGLE-LINE & NUMBER-ONLY INTENT DETECTION
def test_single_line_and_number_only_detection():
    # Single-line triggers
    assert is_single_line_requested("give me the bin utilization in one line.") is True
    assert is_single_line_requested("tell me the total inventory in one line.") is True
    assert is_single_line_requested("give me the answer in a single line") is True
    assert is_single_line_requested("give me the result without explanation") is True
    assert is_single_line_requested("give me a one-line summary") is True
    assert is_single_line_requested("answer briefly") is True
    assert is_single_line_requested("just tell me") is True

    # Number-only triggers
    assert is_number_only_requested("give me only the number.") is True
    assert is_number_only_requested("just the number") is True
    assert is_number_only_requested("only the percentage") is True
    assert is_number_only_requested("just tell me the count") is True
    assert is_number_only_requested("give me only the count") is True

    # Scalar number extraction
    assert extract_only_number("Overall warehouse bin utilization is 77.4%.") == "77.4%"
    assert extract_only_number("Total inventory quantity is 4,464,910 units.") == "4,464,910"
    assert extract_only_number("There are 9,591 empty bins in the warehouse.") == "9,591"


# 4. TEST AMBIGUOUS & NATURAL-LANGUAGE QUERY ROUTING
def test_ambiguous_queries_routing():
    # 1. Wasting space
    plan_waste = deterministic_warehouse_sql_generator("Which bins are wasting the most space?")
    assert plan_waste["intent"] == "wasting_space_bins"
    assert "Unused Space (FT3)" in plan_waste["sql"]

    # 2. Attention bins
    plan_att = deterministic_warehouse_sql_generator("Show me the bins that need attention")
    assert plan_att["intent"] == "bins_needing_attention"
    assert "Issue Type" in plan_att["sql"]

    # 3. Inventory sitting
    plan_sitting = deterministic_warehouse_sql_generator("Where is most of my inventory sitting?")
    assert plan_sitting["intent"] == "plant_inventory_distribution"

    # 4. Most free space
    plan_free = deterministic_warehouse_sql_generator("Where do I have the most free space?")
    assert plan_free["intent"] == "plant_available_capacity_ranking"
    assert "Available Capacity (FT3)" in plan_free["sql"]

    # 5. Biggest storage problem
    plan_prob = deterministic_warehouse_sql_generator("Which plant has the biggest storage problem?")
    assert plan_prob["intent"] == "plant_biggest_storage_problem"

    # 6. Put-away candidate bins
    plan_putaway = deterministic_warehouse_sql_generator("Where can I put away more stock?")
    assert plan_putaway["intent"] == "putaway_bins_ranking"
    assert "Available Capacity (FT3)" in plan_putaway["sql"]

    # 7. Best performing plant on utilization
    plan_best = deterministic_warehouse_sql_generator("Which plant is performing best on storage utilization?")
    assert plan_best["intent"] == "plant_best_utilization"

    # 8. Warehouse fullness
    plan_full = deterministic_warehouse_sql_generator("How full is the warehouse right now?")
    assert plan_full["intent"] in ["bin_utilization", "warehouse_utilization_summary"]

    # 9. Most stock
    plan_stock = deterministic_warehouse_sql_generator("Which plant has the most stock?")
    assert plan_stock["intent"] == "plant_inventory_ranking"


# 5. INTEGRATION END-TO-END TESTS VIA FASTAPI CHAT ENDPOINT
@pytest.mark.anyio
async def test_nonexistent_queries_api_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Nonexistent bins query MUST NEVER return 33,129 all-bins
        resp = await ac.post("/api/chat", json={"message": "Find bins that do not exist"})
        assert resp.status_code == 200
        data = resp.json()
        assert "No matching warehouse records were found" in data["answer"]
        assert len(data["rows"]) == 0
        assert len(data["tables"]) == 0
        assert data["output_type"] == "text"

        # Show bins that don't exist
        resp2 = await ac.post("/api/chat", json={"message": "Show bins that don't exist"})
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert "No matching warehouse records were found" in data2["answer"]
        assert len(data2["rows"]) == 0

        # Invalid plant query
        resp3 = await ac.post("/api/chat", json={"message": "Show utilization for an invalid plant"})
        assert resp3.status_code == 200
        data3 = resp3.json()
        assert "No matching warehouse records were found" in data3["answer"]
        assert len(data3["rows"]) == 0

        # Plant 9999
        resp4 = await ac.post("/api/chat", json={"message": "Show utilization for Plant 9999"})
        assert resp4.status_code == 200
        data4 = resp4.json()
        assert "No matching warehouse records were found" in data4["answer"]
        assert len(data4["rows"]) == 0

        # Nonexistent specific bin
        resp5 = await ac.post("/api/chat", json={"message": "Find bin XYZ999"})
        assert resp5.status_code == 200
        data5 = resp5.json()
        assert "No matching warehouse records were found" in data5["answer"]
        assert len(data5["rows"]) == 0


@pytest.mark.anyio
async def test_single_line_and_number_only_api_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Single-line response
        resp = await ac.post("/api/chat", json={"message": "Give me the bin utilization in one line."})
        assert resp.status_code == 200
        data = resp.json()
        assert data["output_type"] == "text"
        assert len(data["rows"]) == 0
        assert len(data["tables"]) == 0
        assert "\n" not in data["answer"].strip()
        assert "%" in data["answer"]

        # Number-only response
        resp2 = await ac.post("/api/chat", json={"message": "Give me only the number."})
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["output_type"] == "text"
        assert len(data2["rows"]) == 0
        assert "%" in data2["answer"] or data2["answer"].replace(".", "").replace(",", "").isdigit()

        # Count-only response
        resp3 = await ac.post("/api/chat", json={"message": "Just tell me the count of empty bins"})
        assert resp3.status_code == 200
        data3 = resp3.json()
        assert data3["output_type"] == "text"
        assert len(data3["rows"]) == 0
        assert any(c.isdigit() for c in data3["answer"])


@pytest.mark.anyio
async def test_ambiguous_queries_api_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # How full is the warehouse right now?
        resp1 = await ac.post("/api/chat", json={"message": "How full is the warehouse right now?"})
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert "%" in data1["answer"]

        # Which plant is performing best on storage utilization?
        resp2 = await ac.post("/api/chat", json={"message": "Which plant is performing best on storage utilization?"})
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert "7228" in data2["answer"]

        # Which plant has the biggest storage problem?
        resp3 = await ac.post("/api/chat", json={"message": "Which plant has the biggest storage problem?"})
        assert resp3.status_code == 200
        data3 = resp3.json()
        assert "7228" in data3["answer"]

        # Which plant has the most stock?
        resp4 = await ac.post("/api/chat", json={"message": "Which plant has the most stock?"})
        assert resp4.status_code == 200
        data4 = resp4.json()
        assert "7228" in data4["answer"]
