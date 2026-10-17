"""Regression tests for multi-plant scope, physical bin utilization, ranges and invalid scopes."""
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    extract_explicit_plants,
    format_deterministic_answer,
    parse_range_filters,
)


def test_extract_all_plants_from_chained_scope():
    assert extract_explicit_plants("Show bins above 60% utilization in Plant 1258 and 1268") == ["1258", "1268"]
    assert extract_explicit_plants("Compare plants 1258, 1268 and 7228") == ["1258", "1268", "7228"]


def test_multi_plant_threshold_preserves_every_plant():
    q = "Show bins above 60% utilization in Plant 1258 and 1268"
    gen = deterministic_warehouse_sql_generator(q)
    assert "b.Plant IN ('1258', '1268')" in gen["sql"]
    assert "b.Plant AS [Plant]" in gen["sql"]
    assert " > 60.0" in gen["sql"]
    assert gen["filters"]["plants"] == ["1258", "1268"]


def test_multi_plant_range_is_not_misclassified_as_comparison():
    q = "Show bins between 40% and 60% utilization in Plant 1258 and 1268"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["intent"] == "range_query"
    assert gen["query_plan"]["intent"] == "RANGE_QUERY"
    assert "b.Plant IN ('1258', '1268')" in gen["sql"]
    assert "BETWEEN 40.0 AND 60.0" in gen["sql"]


def test_multi_plant_ranking_preserves_scope():
    q = "Show top 10 most utilized bins in Plant 1258 and 1268"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["query_plan"]["intent"] == "RANKING"
    assert gen["query_plan"]["rank_scope"]["Plants"] == ["1258", "1268"]
    assert "b.Plant IN ('1258', '1268')" in gen["sql"]


def test_bin_utilization_comparison_uses_physical_volume():
    q = "Compare bin utilization of Plant 1258 and Plant 1268"
    gen = deterministic_warehouse_sql_generator(q)
    assert gen["query_plan"]["comparison_subject"] == "bin_utilization"
    assert "SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0))" in gen["sql"]
    assert "SUM(b.Volume)" in gen["sql"]
    assert "COUNT(DISTINCT i.BinNo) * 100.0" not in gen["sql"]


def test_invalid_plant_in_multi_scope_is_not_silently_dropped():
    q = "Show bins above 60% utilization in Plant 1258 and 9999"
    rows = [{"Bin": "B1", "Plant": "1258", "Bin Capacity": "100 FT3", "Utilization %": "70%"}]
    assert format_deterministic_answer(q, rows) == "No matching warehouse records were found for your query in the database."


def test_above_and_below_operator_fidelity():
    assert parse_range_filters("bins above 60% utilization")[0]["operator"] == "GT"
    assert parse_range_filters("bins at least 60% utilization")[0]["operator"] == "GTE"
    assert parse_range_filters("bins below 30% utilization")[0]["operator"] == "LT"
    assert parse_range_filters("bins at most 30% utilization")[0]["operator"] == "LTE"
