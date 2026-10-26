"""Tests verifying the Bin Utilization Response Format Rule.

Rule:
For every query whose primary intent is Bin Utilization, the response must show Bin Utilization only.
Remove Volume Utilization percentage, Occupied volume, Total volume capacity, and any volume-based
utilization text appended after Bin Utilization.
"""

import pytest
from backend.app.llm import (
    deterministic_warehouse_sql_generator,
    format_deterministic_answer,
    is_bin_utilization_primary,
    is_volume_utilization_requested,
    optimize_response_format,
)


def test_intent_detection_bin_vs_volume_utilization():
    # 1. Primary Bin Utilization queries
    assert is_bin_utilization_primary("Show bin utilization") is True
    assert is_bin_utilization_primary("Show bin utilization for Plant 7228") is True
    assert is_bin_utilization_primary("Show the bin utilization of all plants") is True
    assert is_bin_utilization_primary("Compare bin utilization between Plant 1258 and Plant 7228") is True
    assert is_bin_utilization_primary("Give detailed bin utilization for Plant 7228") is True
    assert is_bin_utilization_primary("What is the overall bin utilization?") is True
    assert is_bin_utilization_primary("Show all bin utilization percentages.") is True
    assert is_bin_utilization_primary("Which bins are currently most utilized?") is True
    assert is_bin_utilization_primary("Which bins are least utilized?") is True
    assert is_bin_utilization_primary("Show the top 10 most utilized bins.") is True
    assert is_bin_utilization_primary("Show the top 10 least utilized bins.") is True

    # 2. Volume Utilization queries (allowed)
    assert is_volume_utilization_requested("Show volume utilization for Plant 7228") is True
    assert is_bin_utilization_primary("Show volume utilization for Plant 7228") is False

    # 3. Both requested explicitly (show both)
    assert is_volume_utilization_requested("Compare bin utilization and volume utilization") is True
    assert is_bin_utilization_primary("Compare bin utilization and volume utilization") is False


def test_all_plants_bin_utilization_shows_bin_utilization_only():
    """Query: 'Show the bin utilization of all plants'

    The response breakdown must contain:
    - **Plant 7228**: **79.06%** Bin Utilization (7,522 of 9,514 bins occupied).
    And NEVER append Volume Utilization or FT³.
    """
    mock_rows = [
        {
            "Plant": "7228",
            "TotalBins": 9514,
            "OccupiedBins": 7522,
            "EmptyBins": 1992,
            "BinUtilizationPct": 79.06,
            "TotalBinCapacityVolume": 595769.54,
            "OccupiedBinVolume": 483095.68,
            "VolumeUtilizationPct": 81.09,
        },
        {
            "Plant": "1266",
            "TotalBins": 1846,
            "OccupiedBins": 1302,
            "EmptyBins": 544,
            "BinUtilizationPct": 70.53,
            "TotalBinCapacityVolume": 98450.0,
            "OccupiedBinVolume": 69436.78,
            "VolumeUtilizationPct": 70.53,
        },
        {
            "Plant": "1268",
            "TotalBins": 15582,
            "OccupiedBins": 10710,
            "EmptyBins": 4872,
            "BinUtilizationPct": 68.73,
            "TotalBinCapacityVolume": 990690.12,
            "OccupiedBinVolume": 680901.32,
            "VolumeUtilizationPct": 68.73,
        },
    ]

    ans = format_deterministic_answer("Show the bin utilization of all plants", mock_rows)
    
    # Must show Bin Utilization for plants
    assert "Plant 7228" in ans and "79.06%" in ans and "Bin Utilization" in ans
    assert "Plant 1266" in ans and "70.53%" in ans and "Bin Utilization" in ans
    assert "Plant 1268" in ans and "68.73%" in ans and "Bin Utilization" in ans
    
    # Must NOT display Volume Utilization or volume capacity
    assert "Volume Utilization" not in ans
    assert "81.09%" not in ans
    assert "483,095" not in ans
    assert "595,769" not in ans
    assert "FT³" not in ans


def test_single_plant_bin_utilization_shows_bin_utilization_only():
    """Query: 'Show bin utilization for Plant 7228'

    Must return:
    Plant 7228: 79.06% Bin Utilization (7,522 of 9,514 bins occupied).
    And NEVER append: | 81.09% Volume Utilization (...)
    """
    mock_rows = [
        {
            "Plant": "7228",
            "TotalBins": 9514,
            "OccupiedBins": 7522,
            "EmptyBins": 1992,
            "BinUtilizationPct": 79.06,
            "TotalBinCapacityVolume": 595769.54,
            "OccupiedBinVolume": 483095.68,
            "VolumeUtilizationPct": 81.09,
        }
    ]

    ans = format_deterministic_answer("Show bin utilization for Plant 7228", mock_rows)
    assert "Plant 7228" in ans
    assert "79.06%" in ans
    assert "Bin Utilization" in ans
    assert "7,522 of 9,514" in ans
    assert "Volume Utilization" not in ans
    assert "81.09%" not in ans
    assert "FT³" not in ans


def test_plant_comparison_bin_utilization_shows_bin_utilization_only():
    """Query: 'Compare bin utilization between Plant 1258 and Plant 7228'

    Must show Bin Utilization comparison only.
    No Occupied Volume or Available Capacity FT³ appended to each plant.
    """
    mock_rows = [
        {
            "Plant": "7228",
            "Bin Utilization %": "79.1%",
            "BinUtilizationPct": 79.06,
            "Occupied Volume": 483095.68,
            "Total Capacity": 595769.54,
            "Available Capacity": 112673.86,
        },
        {
            "Plant": "1258",
            "Bin Utilization %": "20.3%",
            "BinUtilizationPct": 20.29,
            "Occupied Volume": 105011.35,
            "Total Capacity": 517531.0,
            "Available Capacity": 412519.65,
        },
    ]

    ans = format_deterministic_answer("Compare bin utilization between Plant 1258 and Plant 7228", mock_rows)
    assert ("Plant 7228" in ans or "7228" in ans) and ("79.10%" in ans or "79.1%" in ans)
    assert ("Plant 1258" in ans or "1258" in ans) and ("20.30%" in ans or "20.3%" in ans)
    assert "Bin Utilization" in ans
    # Must NOT show volume breakdown lines
    assert "Occupied:" not in ans
    assert "Available Capacity:" not in ans
    assert "FT³" not in ans


def test_detailed_bin_utilization_suppresses_volume_capacity():
    """Query: 'Give detailed bin utilization for Plant 7228'

    Must NOT automatically add Total Storage Capacity volume in FT³.
    """
    mock_rows = [
        {
            "Plant": "7228",
            "Storage Location": "B2B",
            "Bin Utilization %": "85.2%",
            "UtilizationPct": 85.2,
            "Total Bins": 5000,
            "Occupied Bins": 4260,
            "Total Capacity Volume (FT3)": 300000.0,
            "Occupied Volume (FT3)": 255600.0,
        },
        {
            "Plant": "7228",
            "Storage Location": "RAW",
            "Bin Utilization %": "65.0%",
            "UtilizationPct": 65.0,
            "Total Bins": 4514,
            "Occupied Bins": 3262,
            "Total Capacity Volume (FT3)": 295769.54,
            "Occupied Volume (FT3)": 192248.0,
        },
    ]

    ans = format_deterministic_answer("Give detailed bin utilization for Plant 7228", mock_rows)
    assert "Plant 7228" in ans
    assert "SLoc `B2B`" in ans
    assert "85.2%" in ans
    # Must suppress Total Storage Capacity volume line
    assert "Total Storage Capacity:" not in ans
    assert "currently occupied" not in ans
    assert "FT³" not in ans


def test_explicit_volume_utilization_is_allowed():
    """Query: 'Show volume utilization for Plant 7228'

    When explicitly asked for volume utilization, volume utilization is allowed.
    """
    mock_rows = [
        {
            "Plant": "7228",
            "TotalBins": 9514,
            "OccupiedBins": 7522,
            "EmptyBins": 1992,
            "BinUtilizationPct": 79.06,
            "TotalBinCapacityVolume": 595769.54,
            "OccupiedBinVolume": 483095.68,
            "VolumeUtilizationPct": 81.09,
        }
    ]

    ans = format_deterministic_answer("Show volume utilization for Plant 7228", mock_rows)
    assert "Volume Utilization" in ans or "volume utilization" in ans
    assert "81.09%" in ans or "483,095" in ans


def test_compare_bin_utilization_and_volume_utilization_shows_both():
    """Query: 'Compare bin utilization and volume utilization'

    When user asks for both, both must be preserved.
    """
    mock_rows = [
        {
            "Plant": "7228",
            "TotalBins": 9514,
            "OccupiedBins": 7522,
            "EmptyBins": 1992,
            "BinUtilizationPct": 79.06,
            "TotalBinCapacityVolume": 595769.54,
            "OccupiedBinVolume": 483095.68,
            "VolumeUtilizationPct": 81.09,
        }
    ]

    ans = format_deterministic_answer("Compare bin utilization and volume utilization", mock_rows)
    assert "79.06%" in ans
    assert "81.09%" in ans or "Volume Utilization" in ans


def test_bin_utilization_metrics_columns_removed_from_table():
    """Query: 'Show the bin utilization of all plants'

    Verifies that the generated SQL keeps [Bin Utilization %] (with % symbol instead of pct),
    Plant, TotalBins, OccupiedBins, EmptyBins, and completely removes BinUtilizationPct,
    BinOccupancyPct, and volume metrics (TotalBinCapacityVolume, OccupiedBinVolume, VolumeUtilizationPct)
    from the table metrics.
    """
    plan = deterministic_warehouse_sql_generator("Show the bin utilization of all plants")
    sql = plan["sql"]
    assert "TotalBins" in sql
    assert "OccupiedBins" in sql
    assert "EmptyBins" in sql
    assert "[Bin Utilization %]" in sql
    assert "BinUtilizationPct" not in sql
    assert "TotalBinCapacityVolume" not in sql
    assert "OccupiedBinVolume" not in sql
    assert "VolumeUtilizationPct" not in sql
    assert "BinOccupancyPct" not in sql


def test_final_acceptance_queries_canonical_bin_utilization():
    """Rule 14 Final Acceptance Test:
    All bin utilization queries must return the same canonical Bin Utilization value
    (Occupied Bins / Total Bins * 100) for Plant 7228 (approx 79.06%) and Plant 1268 (approx 68.73%).
    Never 49.1% or 33.5%.
    """
    from backend.app.db import execute_readonly

    queries = [
        "Show bin utilization for Plant 7228",
        "Show the bin utilization of all plants",
        "Compare the bin utilization of Plant 7228 and Plant 1268",
        "Rank plants by bin utilization",
        "Bin utilization for Plant 7228",
        "Show bin utilization graph for Plant 7228",
    ]

    for q in queries:
        plan = deterministic_warehouse_sql_generator(q)
        rows, _ = execute_readonly(plan["sql"])
        assert len(rows) > 0

        # Plant 7228 verification
        p7228 = [r for r in rows if str(r.get("Plant")) == "7228"]
        assert len(p7228) == 1, f"Plant 7228 missing in query: {q}"
        assert p7228[0]["Bin Utilization %"] == "79.06%"
        assert "49.1%" not in p7228[0]["Bin Utilization %"]

        # If Plant 1268 is present, check canonical 68.73%
        p1268 = [r for r in rows if str(r.get("Plant")) == "1268"]
        if p1268:
            assert p1268[0]["Bin Utilization %"] == "68.73%"
            assert "33.5%" not in p1268[0]["Bin Utilization %"]

        # Volume columns must NOT be in the result table
        cols = list(rows[0].keys())
        assert "Occupied Volume" not in cols, f"Occupied Volume found in table for query: {q}"
        assert "Total Capacity" not in cols, f"Total Capacity found in table for query: {q}"
        assert "Available Capacity" not in cols, f"Available Capacity found in table for query: {q}"
        assert "Total Capacity Volume (FT3)" not in cols
        assert "Occupied Volume (FT3)" not in cols
        assert "Volume Utilization" not in cols
        assert "VolumeUtilizationPct" not in cols


