import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.llm import (
    extract_explicit_plants,
    extract_and_update_conversation_state,
    deterministic_warehouse_sql_generator,
)

client = TestClient(app)


class TestUniversalMultiPlantComparison:
    """Comprehensive test suite for PERMANENT UNIVERSAL MULTI-PLANT COMPARISON CONTEXT."""

    @pytest.mark.parametrize("query,expected_plants", [
        ("the bin utilization of plant 1258 and 7228 in detail", ["1258", "7228"]),
        ("the bin utilization of plant 1268 and 1258 in detail", ["1268", "1258"]),
        ("the bin utilization of plant 7228 and 1266 in detail", ["7228", "1266"]),
        ("the bin utilization of plant 1266 and 1268 in detail", ["1266", "1268"]),
        ("bin utilization of plant 1258 vs 7228 in detail", ["1258", "7228"]),
        ("bin utilization of plant 1268 versus 1266 in detail", ["1268", "1266"]),
        ("compare bin utilization of plant 7228 and 1258 in detail", ["7228", "1258"]),
        ("compare bin utilization of plant 1268 vs 1266 in detail", ["1268", "1266"]),
        ("bin utilization of plant 1258, 7228 and 1268 in detail", ["1258", "7228", "1268"]),
        ("compare bin utilization of 1258, 7228, 1268 and 1266 in detail", ["1258", "7228", "1268", "1266"]),
    ])
    def test_plant_extraction_and_order_preservation(self, query, expected_plants):
        """Rule 1, 2, 6, 7: All requested plants must be extracted in the user-specified order."""
        plants = extract_explicit_plants(query)
        assert plants == expected_plants, f"Expected {expected_plants}, got {plants} for query '{query}'"

    @pytest.mark.parametrize("query,expected_plants", [
        ("the bin utilization of plant 1258 and 7228 in detail", ["1258", "7228"]),
        ("the bin utilization of plant 7228 and 1258 in detail", ["7228", "1258"]),
        ("the bin utilization of plant 1266 and 1268 in detail", ["1266", "1268"]),
        ("bin utilization of plant 1258, 7228 and 1268 in detail", ["1258", "7228", "1268"]),
        ("compare bin utilization of 1258, 7228, 1268 and 1266 in detail", ["1258", "7228", "1268", "1266"]),
    ])
    def test_state_and_routing_multi_plant_bin_detail(self, query, expected_plants):
        """Rule 1, 4, 8: Multi-plant queries with detail wording must route to multi_plant_bin_detail without requiring 'compare'."""
        state = extract_and_update_conversation_state(query, [])
        assert state.get("topic") == "multi_plant_bin_detail"
        assert state.get("operation") == "comparison"
        assert state.get("response_mode") == "DETAIL"
        assert state.get("plants") == expected_plants

        res = deterministic_warehouse_sql_generator(query, [])
        assert isinstance(res, dict)
        assert res.get("intent") == "multi_plant_bin_detail"
        assert res.get("output_type") == "table"
        assert res.get("filters", {}).get("plants") == expected_plants

        sql = res["sql"]
        for p in expected_plants:
            assert f"'{p}'" in sql, f"Plant {p} missing from SQL: {sql}"

    def test_plant_order_preserved_in_tables_api(self):
        """Rule 7: Plant 7228 and 1258 must produce Plant 7228 table first, then Plant 1258 table."""
        query = "the bin utilization of plant 7228 and 1258 in detail"
        resp = client.post("/api/chat", json={"message": query})
        assert resp.status_code == 200
        data = resp.json()

        assert data["intent"] == "multi_plant_bin_detail"
        tables = data.get("tables", [])
        assert len(tables) == 2

        # Plant 7228 must be first, Plant 1258 second
        assert tables[0]["plant"] == "7228"
        assert "Plant 7228" in tables[0]["title"]
        assert tables[1]["plant"] == "1258"
        assert "Plant 1258" in tables[1]["title"]

    def test_three_plants_detailed_tables_api(self):
        """Rule 6: 3 plants must generate 3 independent tables with pagination and mini summaries."""
        query = "bin utilization of plant 1258, 7228 and 1268 in detail"
        resp = client.post("/api/chat", json={"message": query})
        assert resp.status_code == 200
        data = resp.json()

        assert data["intent"] == "multi_plant_bin_detail"
        tables = data.get("tables", [])
        assert len(tables) == 3

        plant_order = [t["plant"] for t in tables]
        assert plant_order == ["1258", "7228", "1268"]

        for tbl in tables:
            assert len(tbl["rows"]) > 0
            assert tbl["total_count"] > 0
            assert "mini_summary" in tbl
            assert "mini_summary_markdown" in tbl

    def test_four_plants_detailed_tables_api(self):
        """Rule 6: 4 plants must generate 4 independent tables."""
        query = "compare bin utilization of 1258, 7228, 1268 and 1266 in detail"
        resp = client.post("/api/chat", json={"message": query})
        assert resp.status_code == 200
        data = resp.json()

        assert data["intent"] == "multi_plant_bin_detail"
        tables = data.get("tables", [])
        assert len(tables) == 4

        plant_order = [t["plant"] for t in tables]
        assert plant_order == ["1258", "7228", "1268", "1266"]

    def test_invalid_plants_returns_no_records_found(self):
        """Rule 10: Invalid/non-existent plants return standard 'no records found' message."""
        query = "the bin utilization of plant 1001 and 1002 in detail"
        resp = client.post("/api/chat", json={"message": query})
        assert resp.status_code == 200
        data = resp.json()

        answer = data.get("answer", "")
        # Should gracefully report no records found, NOT invent data
        assert any(k in answer.lower() for k in ["no matching", "not found", "no records"])
