import pytest
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    format_deterministic_answer,
    optimize_response_format,
    extract_and_update_conversation_state
)
from backend.app.db import execute_readonly


def test_plant_ranking_occupied_volume_desc():
    """Rule: Occupied volume sums bin volume for occupied bins. Plant 1268 is #1."""
    q = "Rank all plants by total occupied volume"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "plant_occupied_volume_ranking"
    assert gen["chart_type"] == "none"
    assert gen["output_type"] == "table"
    assert gen["query_plan"]["intent"] == "RANKING"
    assert gen["query_plan"]["rank_direction"] == "DESC"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 4
    # Plant 1268 must be #1 with 776,888 FT3
    assert rows[0]["Plant"] == 1268
    assert rows[0]["Total Occupied Volume (FT3)"] == 776888.0
    assert rows[1]["Plant"] == 7228
    assert rows[2]["Plant"] == 1258
    assert rows[3]["Plant"] == 1266

    ans = format_deterministic_answer(q, rows)
    assert "Plant 1268" in ans
    assert "776,888.00 FT³" in ans

    opt = optimize_response_format(q, rows, gen)
    assert opt["chart_type"] == "none"
    assert opt["output_type"] == "table"


def test_plant_ranking_occupied_volume_singular():
    """Rule: Singular ranking question returns TOP 1 in single-line concise mode."""
    q = "Which plant occupies the most warehouse space?"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "plant_occupied_volume_ranking"
    assert "TOP 1" in gen["sql"]
    assert gen["output_type"] == "text"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 1
    assert rows[0]["Plant"] == 1268

    ans = format_deterministic_answer(q, rows)
    assert "Plant 1268" in ans
    assert "776,888.00 FT³" in ans

    opt = optimize_response_format(q, rows, gen)
    assert opt["output_type"] == "text"
    assert opt["chart_type"] == "none"


def test_plant_ranking_occupied_volume_asc():
    """Rule: Lowest occupied volume sorts ASC. Plant 1266 is #1 lowest."""
    q = "Which plants have the lowest occupied volume?"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "plant_occupied_volume_ranking"
    assert "ASC" in gen["sql"]

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 4
    assert rows[0]["Plant"] == 1266
    assert round(rows[0]["Total Occupied Volume (FT3)"]) == 105982


def test_specific_plant_rank_lookup():
    """Rule: Specific entity rank lookup computes subquery rank and filters WHERE Plant = X."""
    q = "What rank is Plant 1258 by occupied volume?"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "specific_plant_rank_lookup"
    assert gen["output_type"] == "text"
    assert "Plant = '1258'" in gen["sql"] or "Plant = '1258'" in gen["sql"].replace('"', "'")

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 1
    assert rows[0]["Plant"] == 1258
    assert rows[0]["Rank"] == 3
    assert rows[0]["Total Occupied Volume (FT3)"] == 366543.0

    ans = format_deterministic_answer(q, rows)
    assert "Plant 1258" in ans
    assert "#3" in ans
    assert "366,543.00 FT³" in ans

    opt = optimize_response_format(q, rows, gen)
    assert opt["output_type"] == "text"


def test_plant_rank_explanation():
    """Rule: Ranking explanation returns context on why leader is #1."""
    q = "Why is Plant 1268 ranked #1 by occupied volume?"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "plant_rank_explanation"
    assert gen["output_type"] == "text"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 4
    assert rows[0]["Plant"] == 1268

    ans = format_deterministic_answer(q, rows)
    assert "Plant 1268" in ans
    assert "#1" in ans
    assert "776,888.00 FT³" in ans

    opt = optimize_response_format(q, rows, gen)
    assert opt["output_type"] == "text"


def test_plant_subset_ranking():
    """Rule: Subset plant ranking compares only requested plants."""
    q = "Rank Plant 1258 and Plant 7228 by occupied volume"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "plant_subset_ranking"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 2
    # Between 7228 and 1258: 7228 is #1, 1258 is #2
    assert rows[0]["Plant"] == 7228
    assert rows[1]["Plant"] == 1258

    ans = format_deterministic_answer(q, rows)
    assert "Plant 7228" in ans
    assert "Plant 1258" in ans


def test_orthogonal_metrics_distinct_leaders():
    """Rule: Never confuse Occupied Volume with Bin Utilization % or Total Inventory."""
    # 1. Occupied Volume: Plant 1268 is #1
    gen_vol = deterministic_warehouse_sql_generator("Rank plants by occupied volume")
    rows_vol, _ = execute_readonly(gen_vol["sql"])
    assert rows_vol[0]["Plant"] == 1268

    # 2. Bin Utilization %: Plant 7228 is #1
    gen_util = deterministic_warehouse_sql_generator("Which plant has the highest bin utilization?")
    rows_util, _ = execute_readonly(gen_util["sql"])
    assert rows_util[0]["Plant"] == 7228
    util_val = rows_util[0].get("Bin Utilization %", rows_util[0].get("BinUtilizationPct"))
    assert float(str(util_val).replace("%", "")) > 75.0

    # 3. Total Bins: Plant 1268 is #1 (15,582 bins)
    gen_bins = deterministic_warehouse_sql_generator("Rank plants by total bins")
    rows_bins, _ = execute_readonly(gen_bins["sql"])
    assert rows_bins[0]["Plant"] == 1268
    assert rows_bins[0]["Total Bins"] == 15582

    # 4. Total Inventory Quantity: Plant 7228 is #1
    gen_inv = deterministic_warehouse_sql_generator("Rank plants by inventory quantity")
    rows_inv, _ = execute_readonly(gen_inv["sql"])
    assert rows_inv[0]["Plant"] == 7228


def test_bin_ranking_by_available_capacity():
    """Rule: Bins can be ranked by available capacity (Volume - Occupied Volume)."""
    q = "Rank bins by available capacity"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "bin_available_capacity_ranking"
    assert "ORDER BY [Available Capacity (FT3)] DESC" in gen["sql"]

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) > 0
    assert "Available Capacity (FT3)" in rows[0]
    # First bin should have >= capacity of last bin
    assert rows[0]["Available Capacity (FT3)"] >= rows[-1]["Available Capacity (FT3)"]

    opt = optimize_response_format(q, rows, gen)
    assert opt["chart_type"] == "none"
    assert opt["output_type"] == "table"


def test_conversational_followup_polarity_flip_preserves_plant():
    """Rule: 'What about the lowest ones?' preserves Plant entity and Occupied Volume metric."""
    history = [
        {"role": "user", "content": "Which plants have the highest occupied volume?"},
        {"role": "assistant", "content": "Plant 1268 has the highest occupied volume at 776,888 FT³."}
    ]
    gen_followup = deterministic_warehouse_sql_generator("What about the lowest ones?", history=history)
    assert gen_followup["intent"] == "plant_occupied_volume_ranking"
    assert "ASC" in gen_followup["sql"]

    rows, _ = execute_readonly(gen_followup["sql"])
    assert rows[0]["Plant"] == 1266  # Lowest plant


def test_conversational_followup_reverse_ranking():
    """Rule: 'Reverse it' flips active ranking direction."""
    history = [
        {"role": "user", "content": "Rank all plants by total occupied volume"},
        {"role": "assistant", "content": "Here is the ranking of plants by occupied volume."}
    ]
    gen_rev = deterministic_warehouse_sql_generator("Reverse it", history=history)
    assert gen_rev["intent"] == "plant_occupied_volume_ranking"
    assert "ASC" in gen_rev["sql"]

    rows, _ = execute_readonly(gen_rev["sql"])
    assert rows[0]["Plant"] == 1266  # Lowest is first when reversed


def test_conversational_followup_limit_adjustment():
    """Rule: 'Show 5 instead' updates limit preserving entity and metric."""
    history = [
        {"role": "user", "content": "Show the top 10 most utilized bins"},
        {"role": "assistant", "content": "Here are the top 10 most utilized bins."}
    ]
    gen_limit = deterministic_warehouse_sql_generator("Show 5 instead", history=history)
    assert gen_limit["query_plan"]["limit"] == 5
    assert "TOP 5" in gen_limit["sql"]

    rows, _ = execute_readonly(gen_limit["sql"])
    assert len(rows) == 5


def test_chart_suppression_and_explicit_request():
    """Rule: Default ranking does NOT create a chart; explicit request DOES."""
    # Plain ranking -> No chart
    q_plain = "Rank all plants by total occupied volume"
    gen_plain = deterministic_warehouse_sql_generator(q_plain)
    assert gen_plain["chart_type"] == "none"

    rows, _ = execute_readonly(gen_plain["sql"])
    opt_plain = optimize_response_format(q_plain, rows, gen_plain)
    assert opt_plain["chart_type"] == "none"
    assert opt_plain["output_type"] == "table"

    # Explicit request -> Chart
    q_chart = "Rank all plants by total occupied volume with a bar chart"
    gen_chart = deterministic_warehouse_sql_generator(q_chart)
    assert gen_chart["chart_type"] == "bar"

    opt_chart = optimize_response_format(q_chart, rows, gen_chart)
    assert opt_chart["chart_type"] == "bar"
    assert opt_chart["output_type"] == "bar_chart"


def test_plant_ranking_empty_bins_desc():
    """Rule: 'Rank plants by number of empty bins' ranks plants by empty bin count DESC."""
    variations = [
        "Rank plants by number of empty bins",
        "Rank plants by empty bins",
        "Show plants ranked by empty bin count",
        "Rank the plants based on empty bins",
        "Rank plants according to the number of empty bins"
    ]
    for q in variations:
        gen = deterministic_warehouse_sql_generator(q)
        assert gen["intent"] == "plant_empty_bins_ranking", f"Failed intent for: {q}"
        assert gen["metric"] == "EMPTY_BIN_COUNT", f"Failed metric for: {q}"
        assert gen["query_plan"]["intent"] == "RANKING"
        assert gen["query_plan"]["rank_metric"] == "EMPTY_BIN_COUNT"
        assert gen["query_plan"]["rank_direction"] == "DESC"
        assert "Empty Bins" in gen["sql"]
        assert "ORDER BY [Empty Bins] DESC" in gen["sql"]
        # Must NOT be hijacked by bin utilization or 80% threshold
        assert "utilization" not in gen["sql"].lower() or "sum(i.unrestrictedqty" not in gen["sql"].lower()
        assert "> 80" not in gen["sql"] and "0.8" not in gen["sql"]

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 4
    # Plant 1268 has the most empty bins (4,872)
    assert rows[0]["Plant"] == 1268
    assert rows[0]["Empty Bins"] == 4872
    assert rows[1]["Plant"] == 1258
    assert rows[1]["Empty Bins"] == 2425
    assert rows[2]["Plant"] == 7228
    assert rows[2]["Empty Bins"] == 1992
    assert rows[3]["Plant"] == 1266
    assert rows[3]["Empty Bins"] == 544

    ans = format_deterministic_answer(q, rows)
    assert "Plant 1268" in ans
    assert "4,872 empty bins" in ans
    assert "Plant Ranking by Number of Empty Bins" in ans

    opt = optimize_response_format(q, rows, gen)
    assert opt["chart_type"] == "none"
    assert opt["output_type"] == "table"


def test_plant_ranking_empty_bins_singular_most():
    """Rule: 'Which plant has the most empty bins?' returns TOP 1 in singular text mode."""
    variations = [
        "Which plant has the most empty bins?",
        "Which plant has the highest number of empty bins?"
    ]
    for q in variations:
        gen = deterministic_warehouse_sql_generator(q)
        assert gen["intent"] == "plant_empty_bins_ranking", f"Failed intent for: {q}"
        assert gen["metric"] == "EMPTY_BIN_COUNT"
        assert "TOP 1" in gen["sql"]
        assert gen["output_type"] == "text"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 1
    assert rows[0]["Plant"] == 1268
    assert rows[0]["Empty Bins"] == 4872

    ans = format_deterministic_answer(q, rows)
    assert "Plant 1268" in ans
    assert "4,872 empty bins" in ans
    assert "most empty bins" in ans

    opt = optimize_response_format(q, rows, gen)
    assert opt["output_type"] == "text"
    assert opt["chart_type"] == "none"


def test_plant_ranking_empty_bins_plural_most():
    """Rule: Plural questions like 'Which plants have the most empty bins?' return all plants ranked."""
    variations = [
        "Which plants have the most empty bins?",
        "Show me the plants with the most empty bins."
    ]
    for q in variations:
        gen = deterministic_warehouse_sql_generator(q)
        assert gen["intent"] == "plant_empty_bins_ranking", f"Failed intent for: {q}"
        assert gen["metric"] == "EMPTY_BIN_COUNT"
        assert gen["output_type"] == "table"

        rows, _ = execute_readonly(gen["sql"])
        assert len(rows) == 4
        assert rows[0]["Plant"] == 1268
        assert rows[0]["Empty Bins"] == 4872


def test_plant_ranking_empty_bins_singular_fewest():
    """Rule: 'Which plant has the fewest empty bins?' sorts ASC and returns TOP 1."""
    q = "Which plant has the fewest empty bins?"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "plant_empty_bins_ranking"
    assert gen["metric"] == "EMPTY_BIN_COUNT"
    assert "TOP 1" in gen["sql"]
    assert "ASC" in gen["sql"]
    assert gen["output_type"] == "text"

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 1
    assert rows[0]["Plant"] == 1266
    assert rows[0]["Empty Bins"] == 544

    ans = format_deterministic_answer(q, rows)
    assert "Plant 1266" in ans
    assert "544 empty bins" in ans
    assert "fewest empty bins" in ans


def test_plant_ranking_empty_bins_reverse_asc():
    """Rule: 'Rank plants by number of empty bins from lowest to highest' sorts ASC."""
    q = "Rank plants by number of empty bins from lowest to highest"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "plant_empty_bins_ranking"
    assert "ORDER BY [Empty Bins] ASC" in gen["sql"]

    rows, _ = execute_readonly(gen["sql"])
    assert len(rows) == 4
    assert rows[0]["Plant"] == 1266
    assert rows[0]["Empty Bins"] == 544
    assert rows[1]["Plant"] == 7228
    assert rows[1]["Empty Bins"] == 1992
    assert rows[2]["Plant"] == 1258
    assert rows[2]["Empty Bins"] == 2425
    assert rows[3]["Plant"] == 1268
    assert rows[3]["Empty Bins"] == 4872


def test_plant_ranking_empty_bins_single_line():
    """Rule: Single line mode returns concise single statement without tables."""
    q = "Give me the plant with the most empty bins in one line"
    gen = deterministic_warehouse_sql_generator(q)
    rows, _ = execute_readonly(gen["sql"])
    ans = format_deterministic_answer(q, rows)
    assert "Plant 1268" in ans
    assert "4,872 empty bins" in ans
    assert "\n" not in ans.strip()

