import pytest
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    extract_and_update_conversation_state,
    is_highest_bin_utilization_intent,
    is_lowest_bin_utilization_intent,
    extract_single_plant_safe,
    extract_explicit_plants,
    normalize_query_typos
)


class TestBinLevelUtilizationSemanticIntent:
    """Test suite covering BIN-LEVEL UTILIZATION INTENT + SEMANTIC WORDING CONTEXT (Sections 1-19)."""

    @pytest.mark.parametrize("query", [
        "Which bin holds the lowest utilization?",
        "Which bin has the lowest utilization?",
        "Which bin has lowest utilization?",
        "Which bin holds the loweat utlization?",
        "Which is the least utilized bin?",
        "Which bin is utilized the least?",
        "Find the bin with minimum utilization.",
        "What bin has the lowest bin utilization?",
        "Show me the least utilized bin.",
        "Which storage bin has the lowest utilization?",
        "Find the bin with the smallest utilization.",
        "What is the least utilized bin?",
        "Which storage location is utilized the least?",
        "Tell me the bin with the smallest utilization percentage.",
    ])
    def test_lowest_bin_utilization_variations(self, query):
        assert is_lowest_bin_utilization_intent(query) is True
        st = extract_and_update_conversation_state(query, [])
        assert st.get("topic") == "LOWEST_BIN_UTILIZATION"
        assert st.get("entity") == "bin"
        assert st.get("metric") == "utilization"
        assert st.get("ranking") == "lowest"

        res = deterministic_warehouse_sql_generator(query)
        assert res.get("intent") == "LOWEST_BIN_UTILIZATION"
        assert res.get("metric") == "bin_utilization"
        assert "TOP 1" in res.get("sql", "") or "LIMIT 1" in res.get("sql", "")
        assert "ASC" in res.get("sql", "")

    @pytest.mark.parametrize("query,expected_plant", [
        ("Which bin holds the lowest utilization in 234?", "234"),
        ("Which bin has the lowest utilization in Plant 234?", "234"),
        ("Which is the least utilized bin in 234?", "234"),
        ("Find the bin with minimum utilization for Plant 234.", "234"),
        ("Which bin holds the lowest utilization in 1268?", "1268"),
        ("Which bin has the lowest utilization in Plant 1268?", "1268"),
        ("Which bin holds the loweat utlization in 234?", "234"),
    ])
    def test_lowest_bin_utilization_plant_filter(self, query, expected_plant):
        assert is_lowest_bin_utilization_intent(query) is True
        st = extract_and_update_conversation_state(query, [])
        assert st.get("topic") == "LOWEST_BIN_UTILIZATION"
        assert st.get("entity") == "bin"
        assert st.get("filters", {}).get("plant") == expected_plant

        res = deterministic_warehouse_sql_generator(query)
        assert res.get("intent") == "LOWEST_BIN_UTILIZATION"
        assert res.get("filters", {}).get("plant") == expected_plant
        assert f"b.Plant = '{expected_plant}'" in res.get("sql", "")

    @pytest.mark.parametrize("query", [
        "Which bin holds the highest utilization?",
        "Which bin has the highest utilization?",
        "Which is the most utilized bin?",
        "Which bin is utilized the most?",
        "Find the bin with maximum utilization.",
        "Which bin holds the higest utilization?",
        "What bin has the greatest utilization?",
        "Which storage bin has the highest utilization?",
        "Which storage location is utilized the most?",
    ])
    def test_highest_bin_utilization_variations(self, query):
        assert is_highest_bin_utilization_intent(query) is True
        st = extract_and_update_conversation_state(query, [])
        assert st.get("topic") == "HIGHEST_BIN_UTILIZATION"
        assert st.get("entity") == "bin"
        assert st.get("metric") == "utilization"
        assert st.get("ranking") == "highest"

        res = deterministic_warehouse_sql_generator(query)
        assert res.get("intent") == "HIGHEST_BIN_UTILIZATION"
        assert res.get("metric") == "bin_utilization"
        assert "TOP 1" in res.get("sql", "") or "LIMIT 1" in res.get("sql", "")
        assert "DESC" in res.get("sql", "")

    def test_negative_routing_rules(self):
        # 1. Plant level query must NOT route to bin level
        q_plant = "Which plant has the lowest utilization?"
        assert is_lowest_bin_utilization_intent(q_plant) is False
        st_plant = extract_and_update_conversation_state(q_plant, [])
        assert st_plant.get("entity") == "plant"
        res_plant = deterministic_warehouse_sql_generator(q_plant)
        assert res_plant.get("intent") == "lowest_bin_utilization"

        # 2. Overall warehouse utilization must NOT route to single bin
        q_overall = "What is the overall warehouse utilization?"
        assert is_lowest_bin_utilization_intent(q_overall) is False
        assert is_highest_bin_utilization_intent(q_overall) is False
        st_overall = extract_and_update_conversation_state(q_overall, [])
        assert st_overall.get("topic") == "warehouse_utilization"
        res_overall = deterministic_warehouse_sql_generator(q_overall)
        assert res_overall.get("intent") == "bin_utilization"

        # 3. Multi-plant comparison must NOT route to single bin
        q_comp = "Compare utilization between Plant 234 and Plant 235."
        assert is_lowest_bin_utilization_intent(q_comp) is False
        assert is_highest_bin_utilization_intent(q_comp) is False
        st_comp = extract_and_update_conversation_state(q_comp, [])
        assert st_comp.get("operation") == "comparison"
        res_comp = deterministic_warehouse_sql_generator(q_comp)
        assert res_comp.get("intent") == "plant_comparison"

    def test_singular_vs_plural_distinction(self):
        # Singular -> Single scalar bin intent
        q_sing = "Which bin has the lowest utilization?"
        st_sing = extract_and_update_conversation_state(q_sing, [])
        assert st_sing.get("topic") == "LOWEST_BIN_UTILIZATION"
        assert st_sing.get("limit") == 1
        assert st_sing.get("aggregation") == "scalar"

        # Plural -> Ranking list intent
        q_plur = "Which bins have the lowest utilization?"
        st_plur = extract_and_update_conversation_state(q_plur, [])
        assert st_plur.get("topic") == "least_utilized_bins"
        assert st_plur.get("aggregation") == "list"

    def test_typo_normalization(self):
        assert normalize_query_typos("loweat") == "lowest"
        assert normalize_query_typos("lowst") == "lowest"
        assert normalize_query_typos("loest") == "lowest"
        assert normalize_query_typos("higest") == "highest"
        assert normalize_query_typos("heighest") == "highest"
        assert normalize_query_typos("utlization") == "utilization"
        assert normalize_query_typos("utliztion") == "utilization"
        assert normalize_query_typos("utiliztion") == "utilization"
