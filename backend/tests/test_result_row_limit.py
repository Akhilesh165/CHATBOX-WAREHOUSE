"""Regression tests for result limits and Plant 1258 inventory completeness."""

from backend.app.db import execute_readonly


def test_default_result_limit_includes_all_plant_1258_inventory_rows():
    # The bundled warehouse.db currently contains 5,517 Plant 1258 inventory rows.
    rows, _ = execute_readonly(
        "SELECT * FROM ZWMS_INVENTORY WHERE CAST(Plant AS TEXT) = '1258' ORDER BY Material"
    )
    assert len(rows) == 5517


def test_configured_default_limit_is_above_current_plant_1258_row_count():
    from backend.app.config import settings

    assert settings.sql_max_result_rows >= 5517
