import pytest
import pandas as pd
from scripts.import_excel import clean_dataframe, INVENTORY_COLUMNS, BIN_COLUMNS, MATERIAL_COLUMNS

def test_clean_dataframe_valid():
    sample_data = {col: [f"val_{i}"] for i, col in enumerate(INVENTORY_COLUMNS)}
    df = pd.DataFrame(sample_data)
    cleaned = clean_dataframe(df, INVENTORY_COLUMNS, "Inventory")
    assert list(cleaned.columns) == INVENTORY_COLUMNS
    assert len(cleaned) == 1

def test_clean_dataframe_missing_column():
    incomplete_data = {"Id": [1], "Material": ["10001"]}
    df = pd.DataFrame(incomplete_data)
    with pytest.raises(ValueError, match="missing required columns"):
        clean_dataframe(df, INVENTORY_COLUMNS, "Inventory")
