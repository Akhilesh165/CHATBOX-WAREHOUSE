#!/usr/bin/env python3
"""Warehouse Inventory & Master Data Excel Importer

Authoritative Source Rules:
- Inventory source is `Bin Invrntory.xlsx` (Sheet1) ONLY.
- Master data sources are `WMS Bins Data.xlsx`:
    * Sheet `Bin Master` -> dbo.ZWMS_BIN_MASTER
    * Sheet `Material Master` -> dbo.ZWMS_MATERIAL_MASTER
- The sheet `Inventory` inside `WMS Bins Data.xlsx` is strictly ignored.

Usage:
  python scripts/import_excel.py --inventory "data/Bin Invrntory.xlsx" --masters "data/WMS Bins Data.xlsx"
"""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import quote_plus
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Authoritative column definitions
INVENTORY_COLUMNS = [
    'Id', 'FileName', 'Material', 'Plant', 'StorageLocation', 'Batch', 
    'MaterialDescription', 'UnrestrictedQty', 'UnrestrictedQty2', 
    'BaseUnitOfMeasure', 'Mrp', 'FullyVestedOn', 'ChangedAt', 'BinNo', 
    'INSERT_BY', 'INSERT_TIMESTAMP', 'UPDATE_BY', 'UPDATE_TIMESTAMP'
]

BIN_COLUMNS = [
    'Id', 'Plant', 'BinLocation', 'MainCriterion', 'StorageLocation', 
    'PalletType', 'Box', 'Owner', 'Volume', 'VolumeUnit', 
    'Length', 'Width', 'Height', 'CreatedDate', 'CreatedBy'
]

MATERIAL_COLUMNS = [
    'Id', 'MaterialCode', 'MaterialDescription', 'Volume', 'VUom', 
    'GrossWeight', 'Division', 'DivisionDescription', 'Kslot', 'BinUom', 
    'InsertBY', 'CreatedDateTime', 'NetWeight', 'EanNo', 'Hierarchy', 
    'MaterialGroup', 'CaseLot', 'Length', 'Width', 'Height', 
    'CartoonGrossWeight', 'CartoonVolume', 'UpdatedDateTime'
]

def clean_dataframe(df: pd.DataFrame, expected_columns: list[str], dataset_name: str) -> pd.DataFrame:
    """Validate and clean dataframe against required schema."""
    # Standardize column names (strip whitespace)
    df.columns = [str(c).strip() for c in df.columns]
    
    missing = [c for c in expected_columns if c not in df.columns]
    if missing:
        raise ValueError(f"Dataset '{dataset_name}' is missing required columns: {missing}")
    
    cleaned = df[expected_columns].copy()
    
    # Clean string columns
    for col in cleaned.select_dtypes(include=['object']).columns:
        cleaned[col] = cleaned[col].astype(str).str.strip().replace({'nan': None, 'None': None, '': None})
        
    return cleaned

def get_database_engine(custom_url: str | None = None):
    """Build SQLAlchemy engine supporting both SQL Server and SQLite fallback."""
    if custom_url:
        return create_engine(custom_url)

    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return create_engine(database_url)
    
    sql_server = os.getenv("SQL_SERVER")
    sql_database = os.getenv("SQL_DATABASE")
    sql_username = os.getenv("SQL_USERNAME")
    sql_password = os.getenv("SQL_PASSWORD")
    sql_driver = os.getenv("SQL_DRIVER", "ODBC Driver 18 for SQL Server")

    # If SQL Server is configured and not default dummy, use SQL Server
    if sql_server and sql_database and sql_username and sql_password and sql_password != "ChangeThisStrongPassword123!":
        conn = (
            f"DRIVER={{{sql_driver}}};"
            f"SERVER={sql_server};"
            f"DATABASE={sql_database};"
            f"UID={sql_username};"
            f"PWD={sql_password};"
            "TrustServerCertificate=yes;"
        )
        return create_engine("mssql+pyodbc:///?odbc_connect=" + quote_plus(conn), fast_executemany=True)
    
    # Fallback to local SQLite database for local development/testing
    print("Notice: Using local SQLite database (sqlite:///warehouse.db) for development/testing.")
    return create_engine("sqlite:///warehouse.db")

def main():
    parser = argparse.ArgumentParser(description="Import Warehouse Inventory and Master Excel files into SQL Server.")
    parser.add_argument("--inventory", default="data/Bin Invrntory.xlsx", help="Path to Bin Invrntory.xlsx")
    parser.add_argument("--masters", default="data/WMS Bins Data.xlsx", help="Path to WMS Bins Data.xlsx")
    parser.add_argument("--db-url", default=None, help="Custom database URL (e.g. sqlite:///warehouse.db or mssql+pyodbc://...)")
    parser.add_argument("--if-exists", default="replace", choices=["replace", "append", "fail"], help="Table insertion mode")
    parser.add_argument("--chunksize", type=int, default=2000, help="Batch chunk size for database inserts")
    args = parser.parse_args()

    inv_path = Path(args.inventory)
    masters_path = Path(args.masters)

    if not inv_path.exists():
        print(f"Error: Inventory file not found: {inv_path}", file=sys.stderr)
        sys.exit(1)
    if not masters_path.exists():
        print(f"Error: Masters file not found: {masters_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Reading Authoritative Inventory: {inv_path} (Sheet1)...")
    inv_raw = pd.read_excel(inv_path, sheet_name="Sheet1")
    inv_df = clean_dataframe(inv_raw, INVENTORY_COLUMNS, "Inventory")
    print(f"    -> Loaded {len(inv_df)} inventory records.")

    print(f"[*] Reading Master Data: {masters_path}...")
    masters_excel = pd.ExcelFile(masters_path)
    print(f"    -> Sheets found in master file: {masters_excel.sheet_names}")
    
    if "Inventory" in masters_excel.sheet_names:
        print("    -> [CONTRACT COMPLIANCE] Explicitly IGNORING sheet 'Inventory' from master workbook.")

    bins_raw = pd.read_excel(masters_excel, sheet_name="Bin Master")
    bins_df = clean_dataframe(bins_raw, BIN_COLUMNS, "Bin Master")
    print(f"    -> Loaded {len(bins_df)} bin master records.")

    materials_raw = pd.read_excel(masters_excel, sheet_name="Material Master")
    materials_df = clean_dataframe(materials_raw, MATERIAL_COLUMNS, "Material Master")
    print(f"    -> Loaded {len(materials_df)} material master records.")

    engine = get_database_engine(args.db_url)
    is_sqlite = engine.url.get_backend_name() == 'sqlite'

    print(f"[*] Connecting to database engine: {engine.url.get_backend_name()}...")

    # Write to target tables
    print("[*] Inserting into ZWMS_INVENTORY...")
    inv_df.to_sql(
        "ZWMS_INVENTORY",
        engine,
        schema=None if is_sqlite else "dbo",
        if_exists=args.if_exists,
        index=False,
        chunksize=args.chunksize
    )

    print("[*] Inserting into ZWMS_BIN_MASTER...")
    bins_df.to_sql(
        "ZWMS_BIN_MASTER",
        engine,
        schema=None if is_sqlite else "dbo",
        if_exists=args.if_exists,
        index=False,
        chunksize=args.chunksize
    )

    print("[*] Inserting into ZWMS_MATERIAL_MASTER...")
    materials_df.to_sql(
        "ZWMS_MATERIAL_MASTER",
        engine,
        schema=None if is_sqlite else "dbo",
        if_exists=args.if_exists,
        index=False,
        chunksize=args.chunksize
    )

    # If SQLite, create the view as well for local convenience
    if is_sqlite:
        with engine.connect() as conn:
            conn.execute(text("""
            CREATE VIEW IF NOT EXISTS vw_WMS_InventoryEnriched AS
            SELECT 
                i.Id AS InventoryId,
                i.Material,
                COALESCE(i.MaterialDescription, m.MaterialDescription) AS MaterialDescription,
                i.Plant,
                i.StorageLocation,
                i.Batch,
                i.UnrestrictedQty,
                i.UnrestrictedQty2,
                i.BaseUnitOfMeasure,
                i.Mrp,
                i.FullyVestedOn,
                i.ChangedAt,
                i.BinNo,
                m.Division,
                m.DivisionDescription,
                m.MaterialGroup,
                m.GrossWeight AS MaterialGrossWeight,
                m.NetWeight AS MaterialNetWeight,
                m.Volume AS MaterialVolume,
                m.VUom AS MaterialVolumeUom,
                m.Length AS MaterialLength,
                m.Width AS MaterialWidth,
                m.Height AS MaterialHeight,
                m.CaseLot,
                m.EanNo,
                m.Hierarchy,
                b.PalletType,
                b.Box AS BinBox,
                b.Owner AS BinOwner,
                b.Volume AS BinVolume,
                b.VolumeUnit AS BinVolumeUnit,
                b.Length AS BinLength,
                b.Width AS BinWidth,
                b.Height AS BinHeight
            FROM ZWMS_INVENTORY i
            LEFT JOIN ZWMS_MATERIAL_MASTER m
                ON i.Material = m.MaterialCode
            LEFT JOIN ZWMS_BIN_MASTER b
                ON i.BinNo = b.BinLocation 
                AND i.Plant = b.Plant 
                AND i.StorageLocation = b.StorageLocation;
            """))
            conn.commit()

    print("\n[SUCCESS] Import completed successfully:")
    print(f"  - dbo.ZWMS_INVENTORY:       {len(inv_df):,} rows")
    print(f"  - dbo.ZWMS_BIN_MASTER:      {len(bins_df):,} rows")
    print(f"  - dbo.ZWMS_MATERIAL_MASTER: {len(materials_df):,} rows")

if __name__ == "__main__":
    main()
