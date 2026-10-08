"""
WAREHOUSE AI SEMANTIC CONTEXT & BUSINESS KNOWLEDGE ARCHITECTURE
===============================================================
Enforces the Strict 6-Step Priority Hierarchy:
  1. Schema (Tables, Columns, Data Types)
  2. Relationships (Joins, Keys, Multi-Table Links)
  3. Business Definitions (Formulas, Concepts, Calculation Rules)
  4. Intent (Analytical Task, Action, Aggregation)
  5. Scope / Filters (Plant, Bin, Material, Storage Location)
  6. Response Format (Single Line vs Table vs Chart vs KPI Dashboard)
"""

from typing import Any, Dict, List

WAREHOUSE_SEMANTIC_CONTEXT: Dict[str, Any] = {
    # Metadata & Pipeline Priority Sequence
    "pipeline_priority_order": [
        "1. SCHEMA",
        "2. RELATIONSHIPS",
        "3. BUSINESS_DEFINITIONS",
        "4. INTENT",
        "5. SCOPE_FILTERS",
        "6. RESPONSE_FORMAT"
    ],

    # =========================================================================
    # 1. DATABASE SCHEMA (Exact project tables, columns, and data specifications)
    # =========================================================================
    "schema": {
        "inventory_master": {
            "table_name": "dbo.ZWMS_INVENTORY",
            "description": "Current active inventory stored across warehouse bins and plants",
            "columns": {
                "Material": "Material identifier (SKU)",
                "MaterialDescription": "Material descriptive name",
                "Plant": "Facility/Plant code (e.g. 1258, 1266, 1268, 7228)",
                "StorageLocation": "Storage location code within plant (e.g. B2B, RAW)",
                "BinNo": "Storage bin location identifier",
                "UnrestrictedQty": "Unrestricted available stock quantity",
                "BaseUnitOfMeasure": "Unit of measurement (e.g. EA, KG)",
                "Batch": "Inventory batch number"
            }
        },
        "bin_master": {
            "table_name": "dbo.ZWMS_BIN_MASTER",
            "description": "Physical storage bins with maximum physical capacity and volume specs",
            "columns": {
                "Plant": "Facility code owning the bin",
                "BinLocation": "Storage bin identifier (e.g. NRJP2124D2, B001)",
                "StorageLocation": "Storage location category",
                "Volume": "Total physical capacity volume of the bin",
                "VolumeUnit": "Unit of volume (FT3)",
                "PalletType": "Compatible pallet type"
            }
        },
        "volume_master": {
            "table_name": "dbo.ZWMS_MATERIAL_MASTER",
            "description": "Material physical specs, packaging dimensions, and cubic volume",
            "columns": {
                "MaterialCode": "Material identifier matching dbo.ZWMS_INVENTORY.Material",
                "MaterialDescription": "Material name in master",
                "Length": "Physical unit length",
                "Width": "Physical unit width",
                "Height": "Physical unit height",
                "Volume": "Calculated physical unit volume",
                "VUom": "Unit of volume"
            }
        }
    },

    # =========================================================================
    # 2. RELATIONSHIPS (Join keys, Multi-Table links, Cardinalities)
    # =========================================================================
    "relationships": {
        "inventory_to_volume_master": {
            "from_table": "dbo.ZWMS_INVENTORY",
            "to_table": "dbo.ZWMS_MATERIAL_MASTER",
            "join_type": "LEFT JOIN",
            "condition": "dbo.ZWMS_INVENTORY.Material = dbo.ZWMS_MATERIAL_MASTER.MaterialCode",
            "business_key": "Material = MaterialCode",
            "cardinality": "many_to_one"
        },
        "inventory_to_bin_master": {
            "from_table": "dbo.ZWMS_BIN_MASTER",
            "to_table": "dbo.ZWMS_INVENTORY",
            "join_type": "LEFT JOIN",
            "condition": "dbo.ZWMS_BIN_MASTER.BinLocation = dbo.ZWMS_INVENTORY.BinNo AND dbo.ZWMS_BIN_MASTER.Plant = dbo.ZWMS_INVENTORY.Plant",
            "business_key": "BinLocation = BinNo AND Plant = Plant",
            "cardinality": "one_to_many"
        }
    },

    # =========================================================================
    # 3. BUSINESS DEFINITIONS & CALCULATION RULES (Calculation Formulas)
    # =========================================================================
    "business_definitions": {
        "EMPTY_BIN": {
            "meaning": "Storage bin containing zero unrestricted inventory quantity",
            "sql_condition": "(i.BinNo IS NULL OR i.UnrestrictedQty = 0)",
            "synonyms": [
                "empty", "vacant", "unused", "zero-stock", "unoccupied", "free bin",
                "available bin", "available for put-away", "putaway", "put away",
                "where can i put", "without displacing", "place incoming"
            ]
        },
        "OCCUPIED_BIN": {
            "meaning": "Storage bin containing inventory quantity strictly greater than zero",
            "sql_condition": "i.BinNo IS NOT NULL AND i.UnrestrictedQty > 0",
            "synonyms": ["occupied", "active bin", "in use", "filled bin", "currently occupied"]
        },
        "BIN_UTILIZATION": {
            "meaning": "Percentage of occupied bins out of total bins in facility/network",
            "formula": "COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0)",
            "synonyms": [
                "bin utilization", "bin occupancy", "bin fill rate", "facility fill",
                "space utilization rate", "bin fill percentage", "how full are bins"
            ]
        },
        "VOLUME_UTILIZATION": {
            "meaning": "Percentage of occupied physical volume against total bin capacity volume",
            "formula": "SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END) * 100.0 / NULLIF(SUM(b.Volume), 0)",
            "synonyms": [
                "volume utilization", "volumetric utilization", "storage capacity usage",
                "cubic capacity utilization", "occupied volume percentage"
            ]
        },
        "MATERIALS_MISSING_FROM_VOLUME_MASTER": {
            "meaning": "Inventory materials that exist in Inventory Master but have no matching record in Material Volume Master",
            "source_table": "dbo.ZWMS_INVENTORY",
            "reference_table": "dbo.ZWMS_MATERIAL_MASTER",
            "sql_condition": "v.MaterialCode IS NULL",
            "synonyms": [
                "missing from volume master", "missing from the volume master",
                "not in volume master", "exist in inventory master but not",
                "no volume master record", "no corresponding volume master",
                "do not have volume master", "unmatched volume master"
            ]
        },
        "MISSING_DIMENSIONS": {
            "meaning": "Materials in inventory that either have no volume master record or have incomplete/zero Length, Width, Height, or Volume",
            "sql_condition": "m.MaterialCode IS NULL OR m.Length IS NULL OR m.Length = 0 OR m.Width IS NULL OR m.Width = 0 OR m.Height IS NULL OR m.Height = 0 OR m.Volume IS NULL OR m.Volume = 0",
            "synonyms": [
                "missing dimensions", "missing physical", "incomplete dimension", "without dimension",
                "no dimensions", "missing length", "missing width", "missing height", "data quality check"
            ]
        }
    },

    # =========================================================================
    # 4. INTENT & ANALYTICAL TASK (What operation is requested?)
    # =========================================================================
    "intents": {
        "COUNT": "Scalar quantity / frequency evaluation (e.g. How many empty bins?, Count materials)",
        "KPI": "High-level aggregate single value (e.g. Total quantity, Average inventory per bin)",
        "LIST": "Filtered subset of itemized data records without aggregate reduction",
        "RANKING": "Ordered top N or bottom N list based on a metric (e.g. Top 10 most utilized bins)",
        "COMPARISON": "Multi-entity comparative breakdown across plants or categories",
        "DATA_QUALITY": "Identification of anomalous, missing, or corrupt records (e.g. Missing dimensions)",
        "CROSS_TABLE_VALIDATION": "Multi-master consistency exceptions (e.g. Inventory vs Volume Master)",
        "STATUS": "Binary or discrete operational state verification (e.g. Is bin NRJP2124D2 occupied?)"
    },

    # =========================================================================
    # 5. SCOPE & FILTERS (Entity Isolation & Specific Identification)
    # =========================================================================
    "scope_and_filters": {
        "plant": {
            "type": "filter",
            "pattern": r"\b(1258|1266|1268|7228|\d{4})\b",
            "target_column": "Plant",
            "rule": "Filter query strictly by Plant code. Explicitly mention filtered Plant in response. Never describe as overall/warehouse-wide."
        },
        "bin": {
            "type": "filter",
            "pattern": r"(?:bin\s*[:#-]?\s*([a-z0-9_-]{2,25})|\b(b\d{3,5})\b)",
            "target_column": "BinLocation / BinNo",
            "rule": "Isolate query to specific bin identifier (e.g. NRJP2124D2). Output concise statement for lookups (Plant, Occupancy, Quantity) without rendering full tables/dashboards."
        },
        "material": {
            "type": "filter",
            "pattern": r"\b(?:material|sku|item|code)\s*[:#-]?\s*([a-z0-9_-]{5,20})\b",
            "target_column": "Material / MaterialCode",
            "rule": "Isolate query to specific material SKU code."
        },
        "storage_location": {
            "type": "filter",
            "pattern": r"\b(b2b|raw|fgs|sloc\s*[:#-]?\s*[a-z0-9_-]+)\b",
            "target_column": "StorageLocation",
            "rule": "Filter query strictly by specific storage location."
        }
    },

    # =========================================================================
    # 6. RESPONSE FORMAT (Deterministic presentation logic)
    # =========================================================================
    "response_format_rules": {
        "single_line": {
            "triggers": [
                "how many", "what is", "is", "are there", "count",
                "which plant does bin", "is bin occupied", "quantity in bin"
            ],
            "output_type": "text",
            "suppress_table": True,
            "suppress_cards": True,
            "suppress_charts": True,
            "rule": "Return strictly ONE concise sentence with the unit. Suppress dashboard cards, result tables, and export buttons."
        },
        "list": {
            "triggers": ["which", "show me", "list", "give me the materials", "find materials"],
            "output_type": "table",
            "rule": "Render interactive, paginated, searchable Results Data Table with CSV export."
        },
        "ranking": {
            "triggers": ["top", "highest", "lowest", "least", "most", "bottom"],
            "output_type": "table",
            "rule": "Render ordered ranking table with exact capacities and percentages."
        },
        "comparison": {
            "triggers": ["compare", "versus", "across plants", "by plant"],
            "output_type": "bar_chart",
            "rule": "Render interactive Bar Chart and comparison breakdown."
        },
        "summary_dashboard": {
            "triggers": ["summary", "overview", "dashboard", "kpis", "executive overview"],
            "output_type": "kpi",
            "rule": "Render full 4-card Overview Dashboard only when explicitly asked for an overview/summary."
        }
    }
}
