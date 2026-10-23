"""
TEST SUITE: WAREHOUSE CHATBOT MASTER CONTEXT & GOLDEN RULES (Sections 1-61)
===========================================================================
Tests full compliance with the 61-section Master Context:
- Strict Invalid Entity Handling (Plant 99999, Bin ABC999999 -> "No matching warehouse records were found for your query in the database.")
- Singular Winner Queries ("Which plant has the highest utilization?") -> concise single-line winner
- Count vs List ("How many bins" -> scalar count, "List bins" -> itemized table)
- Competition Ranking for Ties (RANK() OVER window functions)
- Displayed-Metric Consistency & Range Validation
- Entity Preservation Rule
"""

import pytest
from backend.app.semantic_context import WAREHOUSE_SEMANTIC_CONTEXT
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    format_deterministic_answer,
)


class TestMasterContextGoldenRules:
    """Verify Master Context Golden Rules in Semantic Context and Pipeline."""

    def test_semantic_context_has_master_context_rules(self):
        """Semantic context must expose master_context_rules with 20 golden rules."""
        assert "master_context_rules" in WAREHOUSE_SEMANTIC_CONTEXT
        master = WAREHOUSE_SEMANTIC_CONTEXT["master_context_rules"]
        assert "golden_rules" in master
        assert len(master["golden_rules"]) >= 20
        assert master["standard_not_found_response"] == "No matching warehouse records were found for your query in the database."
        assert "1258" in master["valid_plants"]
        assert "7228" in master["valid_plants"]

    def test_invalid_plant_capacity_query(self):
        """Querying capacity for non-existent plant (e.g. Plant 99999) returns strict standard message."""
        q = "What is the storage capacity of Plant 99999?"
        res = deterministic_warehouse_sql_generator(q)
        assert res is not None
        assert "Plant = '99999'" in res["sql"] or "Plant" in res["sql"]

        # When executed against DB or empty rows formatted
        ans_empty = format_deterministic_answer(q, [])
        assert ans_empty == "No matching warehouse records were found for your query in the database."

    def test_invalid_plant_utilization_query(self):
        """Querying bin utilization for non-existent plant (Plant 99999) returns strict standard message."""
        q = "Show bin utilization for Plant 99999"
        res = deterministic_warehouse_sql_generator(q)
        assert "99999" in res["sql"]

        ans = format_deterministic_answer(q, [])
        assert ans == "No matching warehouse records were found for your query in the database."

    def test_invalid_plant_materials_count_query(self):
        """Querying materials count for non-existent plant returns strict standard message, never '0 unique materials'."""
        q = "How many materials are in Plant 99999?"
        res = deterministic_warehouse_sql_generator(q)
        assert "99999" in res["sql"]

        # If SQL returns 0 rows
        ans_empty = format_deterministic_answer(q, [])
        assert ans_empty == "No matching warehouse records were found for your query in the database."

        # If aggregate query returns 1 row with 0 count
        ans_zero = format_deterministic_answer(q, [{"Total Unique Materials": 0, "Unique Materials Count": 0}])
        assert ans_zero == "No matching warehouse records were found for your query in the database."

    def test_invalid_bin_query(self):
        """Querying non-existent bin (e.g. ABC999999) returns strict standard message."""
        q = "What is the utilization of bin ABC999999?"
        ans = format_deterministic_answer(q, [])
        assert ans == "No matching warehouse records were found for your query in the database."

    def test_which_plant_highest_utilization_winner_only(self):
        """'Which plant has the highest utilization?' returns single scalar winner statement, not full table."""
        q = "Which plant has the highest utilization?"
        res = deterministic_warehouse_sql_generator(q)
        assert res["query_plan"]["intent"] == "RANKING"
        assert res["query_plan"]["rank_direction"] == "DESC"
        assert res["query_plan"]["limit"] == 1
        assert "TOP 1" in res["sql"]

        mock_rows = [{
            "Rank": 1,
            "Plant": "7228",
            "BinUtilizationPct": 78.5,
            "Bin Utilization %": "78.5%",
            "Occupied Bins": 157,
            "Empty Bins": 43,
            "Total Bins": 200
        }]
        ans = format_deterministic_answer(q, mock_rows)
        assert "**Plant 7228**" in ans
        assert "highest bin utilization" in ans
        assert ("78.50%" in ans or "78.5%" in ans)
        # Must be single crisp statement, not full ranking list
        assert "- **Rank" not in ans

    def test_which_plant_lowest_bin_utilization_winner_only(self):
        """'Which plant has the lowest bin utilization?' returns single scalar winner statement."""
        q = "Which plant has the lowest bin utilization?"
        res = deterministic_warehouse_sql_generator(q)
        assert res["query_plan"]["intent"] == "RANKING"
        assert res["query_plan"]["rank_direction"] == "ASC"
        assert res["query_plan"]["limit"] == 1
        assert "TOP 1" in res["sql"]

        mock_rows = [{
            "Rank": 1,
            "Plant": "1266",
            "BinUtilizationPct": 42.1,
            "Bin Utilization %": "42.1%",
            "Occupied Bins": 84,
            "Empty Bins": 116,
            "Total Bins": 200
        }]
        ans = format_deterministic_answer(q, mock_rows)
        assert "**Plant 1266**" in ans
        assert "lowest bin utilization" in ans
        assert ("42.10%" in ans or "42.1%" in ans)

    def test_count_vs_list_queries(self):
        """'How many' returns scalar count; 'List' returns structured data table."""
        q_count = "How many bins have utilization above 80%?"
        res_count = deterministic_warehouse_sql_generator(q_count)
        assert res_count["output_type"] == "text"
        assert "COUNT" in res_count["sql"]
        ans_count = format_deterministic_answer(q_count, [{"Threshold Bins Count": 35}])
        assert "35 bins" in ans_count

        q_list = "List bins with utilization above 80%"
        res_list = deterministic_warehouse_sql_generator(q_list)
        assert res_list["output_type"] == "table"
        mock_list_rows = [
            {"Bin": "B100", "Plant": "1258", "Bin Capacity": "500 FT3", "Utilization %": "85.0%"},
            {"Bin": "B101", "Plant": "1258", "Bin Capacity": "500 FT3", "Utilization %": "82.5%"}
        ]
        ans_list = format_deterministic_answer(q_list, mock_list_rows)
        assert "### 📦" in ans_list
        assert "Found **2 bins**" in ans_list
        assert "Data Table" in ans_list

    def test_list_bins_single_match_does_not_misclassify_as_bin_details(self):
        """If a list query matches exactly 1 bin, it should not be formatted as a single bin lookup."""
        q_list = "List bins with utilization above 80%"
        single_mock_row = [
            {"Bin": "B100", "Plant": "1258", "Bin Capacity": "500 FT3", "Utilization %": "85.0%"}
        ]
        ans = format_deterministic_answer(q_list, single_mock_row)
        assert "Found **1 bin**" in ans or "Operating at More than 80%" in ans
        assert "Bin B100 Details" not in ans

    def test_ranking_ties_use_rank_over(self):
        """Plant and bin ranking SQL queries use RANK() OVER for competition ranking on ties."""
        q_plant_rank = "Rank plants by occupied volume"
        res_plant = deterministic_warehouse_sql_generator(q_plant_rank)
        assert "RANK() OVER" in res_plant["sql"]

        q_bin_rank = "Rank bins by available capacity"
        res_bin = deterministic_warehouse_sql_generator(q_bin_rank)
        assert "RANK() OVER" in res_bin["sql"]

        q_plant_util_rank = "Rank plants by bin utilization"
        res_plant_util = deterministic_warehouse_sql_generator(q_plant_util_rank)
        assert "RANK() OVER" in res_plant_util["sql"]
