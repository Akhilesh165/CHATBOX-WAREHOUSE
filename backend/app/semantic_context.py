"""
WAREHOUSE AI SEMANTIC CONTEXT & CANONICAL BUSINESS KNOWLEDGE CONTRACT
=====================================================================
Unified structured context contract consumed across all pipeline layers:
Query Analyzer -> QueryPlan -> SQL Generator -> SQL Validator -> Result Validator -> Response Formatter

Canonical Branches:
  1. schema
  2. relationships
  3. business_definitions
  4. intents
  5. scope_rules
  6. range_rules
  7. comparison_rules
  8. ranking_rules
  9. response_depth_rules
  10. response_format_rules
  11. visualization_rules
  12. conversation_state_rules
"""

from typing import Any, Dict, List

WAREHOUSE_SEMANTIC_CONTEXT: Dict[str, Any] = {
    # Pipeline Priority Sequence
    "pipeline_priority_order": [
        "1. SCHEMA",
        "2. RELATIONSHIPS",
        "3. BUSINESS_DEFINITIONS",
        "4. INTENTS",
        "5. SCOPE_RULES",
        "6. RANGE_RULES",
        "7. COMPARISON_RULES",
        "8. RANKING_RULES",
        "9. RESPONSE_DEPTH_RULES",
        "10. RESPONSE_FORMAT_RULES",
        "11. VISUALIZATION_RULES",
        "12. CONVERSATION_STATE_RULES",
        "13. CAPACITY_RULES"
    ],

    # =========================================================================
    # 1. SCHEMA (Exact project tables, columns, and data types)
    # =========================================================================
    "schema": {
        "inventory_master": {
            "table_name": "dbo.ZWMS_INVENTORY",
            "description": "Current active inventory stored across warehouse bins and plants",
            "columns": {
                "Material": "Material identifier (SKU)",
                "MaterialDescription": "Material descriptive name",
                "Plant": "4-digit Plant code (e.g. 1258, 1266, 1268, 7228)",
                "StorageLocation": "Storage location code (e.g. B2B, RAW, FGS)",
                "Batch": "Batch / lot number",
                "UnrestrictedQty": "Active unrestricted inventory quantity (DECIMAL)",
                "UnrestrictedQty2": "Secondary unit quantity (DECIMAL)",
                "BaseUnitOfMeasure": "Unit of measure (e.g. PC, EA, NOS)",
                "Mrp": "Maximum Retail Price (DECIMAL)",
                "FullyVestedOn": "Date inventory fully vested / received (DATETIME)",
                "ChangedAt": "Timestamp of last status modification (DATETIME)",
                "BinNo": "Assigned storage bin location code"
            }
        },
        "bin_master": {
            "table_name": "dbo.ZWMS_BIN_MASTER",
            "description": "Physical master definition of all storage bins across plants",
            "columns": {
                "Plant": "Plant code associated with the bin",
                "BinLocation": "Storage bin unique location coordinate",
                "StorageLocation": "Associated warehouse storage location",
                "PalletType": "Compatible pallet type",
                "Box": "Box classification identifier",
                "Owner": "Designated bin owner / vendor",
                "Volume": "Total physical capacity volume of the bin",
                "VolumeUnit": "Unit of bin volume measurement (e.g. FT3, M3)",
                "Length": "Physical bin length",
                "Width": "Physical bin width",
                "Height": "Physical bin height"
            }
        },
        "material_master": {
            "table_name": "dbo.ZWMS_MATERIAL_MASTER",
            "description": "Material physical characteristics, volume, packaging and divisional metadata",
            "columns": {
                "MaterialCode": "Unique material code matching ZWMS_INVENTORY.Material",
                "MaterialDescription": "Master material description",
                "Division": "Material division identifier",
                "DivisionDescription": "Material division full name",
                "MaterialGroup": "Material grouping code",
                "GrossWeight": "Gross weight per unit",
                "NetWeight": "Net weight per unit",
                "Length": "Physical unit length",
                "Width": "Physical unit width",
                "Height": "Physical unit height",
                "Volume": "Calculated physical unit volume",
                "VUom": "Unit of volume"
            }
        },
        "inventory_enriched_view": {
            "view_name": "dbo.vw_WMS_InventoryEnriched",
            "description": "Enriched reporting view joining Inventory, Bin Master, and Material Master"
        }
    },

    # =========================================================================
    # 2. RELATIONSHIPS (Join keys, Multi-Table links, Cardinalities)
    # =========================================================================
    "relationships": {
        "inventory_to_material_master": {
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
            "condition": "dbo.ZWMS_BIN_MASTER.BinLocation = dbo.ZWMS_INVENTORY.BinNo AND dbo.ZWMS_BIN_MASTER.Plant = dbo.ZWMS_INVENTORY.Plant AND dbo.ZWMS_BIN_MASTER.StorageLocation = dbo.ZWMS_INVENTORY.StorageLocation",
            "business_key": "BinLocation = BinNo AND Plant = Plant AND StorageLocation = StorageLocation",
            "cardinality": "one_to_many"
        }
    },

    # =========================================================================
    # 3. BUSINESS DEFINITIONS & CALCULATION RULES (Authoritative Formulas)
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
            "meaning": "Occupied bins / total applicable bins * 100",
            "formula": "COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0)",
            "synonyms": [
                "bin utilization", "bin occupancy", "bin fill rate", "facility fill",
                "space utilization rate", "bin fill percentage", "how full are bins"
            ],
            "rules": [
                "Overall utilization must use the complete requested scope, not an average of percentages.",
                "Plant and bin filters must be applied before aggregation.",
                "Ranking must calculate the metric at bin granularity before sorting."
            ]
        },
        "VOLUME_UTILIZATION": {
            "meaning": "Total occupied material volume / total bin capacity * 100",
            "formula": "SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END) * 100.0 / NULLIF(SUM(b.Volume), 0)",
            "synonyms": [
                "volume utilization", "volumetric utilization", "storage capacity usage",
                "cubic capacity utilization", "occupied volume percentage", "capacity utilization"
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
        },
        "TOTAL_INVENTORY_QUANTITY": {
            "meaning": "Sum of total unrestricted inventory quantity stored across warehouse bins",
            "metric": "total_inventory_quantity",
            "entity": "inventory",
            "field": "UnrestrictedQty",
            "aggregation": "SUM",
            "formula": "SUM(UnrestrictedQty)",
            "synonyms": [
                "total warehouse inventory", "what is the total inventory",
                "how much inventory is currently in the warehouse", "total stock",
                "what is the total inventory quantity", "how many units are currently in inventory",
                "current warehouse inventory", "total unrestricted inventory", "total units in inventory"
            ]
        },
        "INVENTORY_RECORDS_COUNT": {
            "meaning": "Total count of records / rows in the inventory dataset",
            "metric": "inventory_records_count",
            "entity": "inventory",
            "field": "rows",
            "aggregation": "COUNT",
            "formula": "COUNT(*)",
            "synonyms": [
                "how many inventory records are there", "count of inventory records",
                "total inventory records", "how many inventory rows are there",
                "number of inventory records", "number of inventory rows", "inventory record count"
            ]
        },
        "UNIQUE_MATERIALS_COUNT": {
            "meaning": "Total count of distinct active material SKUs in inventory",
            "metric": "unique_materials_count",
            "entity": "material",
            "field": "Material",
            "aggregation": "COUNT_DISTINCT",
            "formula": "COUNT(DISTINCT Material)",
            "synonyms": [
                "how many materials are in inventory", "how many materials are there",
                "how many unique materials", "how many distinct materials",
                "number of materials in inventory", "count of unique materials"
            ]
        }
    },

    # =========================================================================
    # 4. INTENTS & ANALYTICAL TASKS
    # =========================================================================
    "intents": {
        "KPI": "Single high-level scalar metric evaluation (e.g. Total quantity, Average inventory per bin)",
        "COUNT": "Frequency / row count evaluation (e.g. How many empty bins?, Count materials)",
        "LIST": "Filtered subset of itemized data records without aggregate reduction",
        "FILTER": "Conditional subset based on attributes or thresholds",
        "RANKING": "Ordered top N or bottom N list based on a metric (e.g. Top 10 most utilized bins)",
        "COMPARISON": "Generic multi-entity comparative breakdown across plants, storage locations, or materials",
        "AGGREGATION": "Grouped calculation across dimensions (e.g. Inventory grouped by division)",
        "TREND": "Time-series analysis over dates/months (e.g. Inventory trend over time)",
        "DATA_QUALITY": "Identification of anomalous, missing, or corrupt records (e.g. Missing dimensions)",
        "CROSS_TABLE_VALIDATION": "Multi-master consistency exceptions (e.g. Inventory vs Volume Master)",
        "LOOKUP": "Specific single-entity lookup (e.g. bin -> material/quantity/plant)",
        "STATUS": "Binary or discrete operational state verification (e.g. Is bin NRJP2124D2 occupied?)"
    },

    # =========================================================================
    # 5. SCOPE RULES (Levels, Filters, Isolation)
    # =========================================================================
    "scope_rules": {
        "levels": [
            "warehouse_wide",
            "plant",
            "storage_location",
            "bin",
            "material",
            "batch",
            "multiple_plants",
            "multiple_bins",
            "multiple_materials"
        ],
        "plant": {
            "pattern": r"\b(1258|1266|1268|7228|\d{4})\b",
            "target_column": "Plant",
            "rule": "Filter query strictly by Plant code. Explicitly mention filtered Plant in response. Never assume Plant 1258 as default."
        },
        "bin": {
            "pattern": r"(?:bin\s*[:#-]?\s*([a-z0-9_-]{2,25})|\b(b\d{3,5})\b)",
            "target_column": "BinLocation / BinNo",
            "rule": "Isolate query to specific bin identifier (e.g. NRJP2124D2). Output concise lookup without unrequested full tables."
        },
        "material": {
            "pattern": r"\b(?:material|sku|item|code)\s*[:#-]?\s*([a-z0-9_-]{5,20})\b",
            "target_column": "Material / MaterialCode",
            "rule": "Isolate query to specific material SKU code."
        },
        "storage_location": {
            "pattern": r"\b(b2b|raw|fgs|sloc\s*[:#-]?\s*[a-z0-9_-]+)\b",
            "target_column": "StorageLocation",
            "rule": "Filter query strictly by specific storage location."
        }
    },

    # =========================================================================
    # 6. RANGE RULES (Numeric, Date, Quantity, Percentage, Ordinal)
    # =========================================================================
    "range_rules": {
        "supported_forms": [
            "between 100 and 500 units",
            "100–500 / 100-500",
            "from 100 to 500",
            "at least 100",
            "100 or more",
            "above 100",
            "greater than 100",
            "below 500",
            "under 500",
            "no more than 500",
            "up to 500",
            "10%–30%",
            "last 30 days",
            "from Jan 1 to Mar 31",
            "this month / last month / current quarter / year to date"
        ],
        "field_resolution_rule": "Do not assume the field from a number alone. The entity/metric context must determine whether the range applies to quantity (UnrestrictedQty), utilization (BinUtilizationPct), volume (Volume), date (FullyVestedOn/ChangedAt), or rank.",
        "range_filter_validation_rule": "When the user specifies a numerical range such as 'between 50% and 80% utilization,' the chatbot must filter the final result using the same metric displayed in the response. For an inclusive 'between' request, use 50% <= utilization <= 80%. Every returned row must satisfy the requested range. The chatbot must never display rows outside the requested range, even if the backend returns them. Before presenting the response, validate every returned row against the requested lower and upper bounds. If any row falls outside the range, exclude it or correct the calculation before displaying the result.",
        "displayed_metric_consistency": "The metric used for filtering must be the same metric shown to the user. If the table displays 'Utilization %,' then the range filter must operate on the calculated Utilization % value, not on bin capacity, occupied volume, a raw database field, or another percentage field.",
        "plan_schema": {
            "range_filters": [
                {
                    "field": "UnrestrictedQty | BinUtilizationPct | Volume | FullyVestedOn",
                    "operator": "BETWEEN | GTE | GT | LTE | LT",
                    "lower": "number | date",
                    "upper": "number | date",
                    "inclusive": True
                }
            ]
        }
    },

    # =========================================================================
    # 7. GENERAL COMPARISON CONTEXT & RULES
    # =========================================================================
    "comparison_rules": {
        "description": "Comparison must be a generic analytical capability, not a bin-utilization-only shortcut.",
        "supported_subjects": [
            "total_inventory",
            "materials",
            "unique_materials",
            "bins",
            "bin_utilization",
            "empty_bins",
            "occupied_bins",
            "storage_locations",
            "top_materials",
            "material_volume"
        ],
        "plan_schema": {
            "intent": "COMPARISON",
            "comparison_entities": [
                {"type": "plant", "value": "1258"},
                {"type": "plant", "value": "7228"}
            ],
            "comparison_subject": "materials | total_inventory | unique_materials | bins | bin_utilization | empty_bins | storage_locations",
            "metrics": ["unique_materials", "inventory_quantity", "occupied_bins"],
            "group_by": ["Plant"]
        },
        "ambiguity_rule": "The phrase 'compare Plant A and Plant B' must not automatically mean 'compare bin utilization'. If no subject is specified and no safe default exists, ask a short clarification."
    },

    # =========================================================================
    # 8. UNIVERSAL RANKING CONTEXT & RULES (Master Ranking Pipeline)
    # =========================================================================
    "ranking_rules": {
        "description": "Universal analytical ranking system for all warehouse entities, metrics, directions, filters, and formats.",
        "master_ranking_pipeline": [
            "1. Identify Ranking Intent (rank, sort, order, highest, lowest, leading, lagging)",
            "2. Identify Ranking Entity (Plant, Bin, Material, StorageLocation)",
            "3. Identify Ranking Metric (Occupied Volume, Utilization %, Total Inventory, Bins, Materials, Available Capacity)",
            "4. Identify Aggregation (SUM, COUNT, COUNT DISTINCT, AVG)",
            "5. Extract Filters & Scopes (Plant, StorageLocation, Material)",
            "6. Extract Thresholds / Conditions (> 80%, >= 80%, < 20%, <= 20%, BETWEEN 70 AND 90)",
            "7. Determine Direction (DESC: top/highest/most; ASC: bottom/lowest/least)",
            "8. Determine Result Limit (scalar: 1, top N: N, all: complete population without arbitrary limits)",
            "9. Calculate & Aggregate complete relevant dataset before sorting",
            "10. Assign Competition Rank & Handle Ties (1, 2, 2, 4)",
            "11. Choose Response Format (concise for singular, clean ranked table [Rank, Entity, Metric] for full)",
            "12. Suppress charts unless explicitly requested or required by detail mode"
        ],
        "supported_entities": ["Plant", "Bin", "Material", "StorageLocation"],
        "entity_metric_mappings": {
            "Plant": {
                "Total Occupied Volume": "SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END) [Total Occupied Volume (FT3)]",
                "Bin Utilization %": "ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 1) [Bin Utilization %]",
                "Total Inventory Quantity": "SUM(i.UnrestrictedQty) [Total Inventory Quantity]",
                "Number of Bins": "COUNT(DISTINCT b.BinLocation) [Number of Bins]",
                "Number of Materials": "COUNT(DISTINCT i.Material) [Number of Materials]",
                "Available Capacity": "ROUND(SUM(b.Volume) - SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) [Available Capacity (FT3)]"
            },
            "Bin": {
                "Utilization %": "ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0), 1) [Utilization %]",
                "Available Capacity": "ROUND(b.Volume - COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) [Available Capacity (FT3)]",
                "Total Stock Quantity": "SUM(i.UnrestrictedQty) [Total Stock Quantity]"
            },
            "Material": {
                "Inventory Quantity": "SUM(i.UnrestrictedQty) [Total Stock Quantity]",
                "Occupied Volume Share": "SUM(i.UnrestrictedQty * m.Volume) [Total Material Volume]"
            },
            "StorageLocation": {
                "Total Inventory Quantity": "SUM(i.UnrestrictedQty) [Total Inventory Quantity]",
                "Bin Utilization %": "ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 1) [Bin Utilization %]"
            }
        },
        "critical_distinctions": {
            "occupied_volume_vs_utilization": "Occupied volume measures actual cubic feet used (FT3). Utilization % measures occupied volume relative to capacity (%). A plant with higher occupied volume can have lower utilization %. NEVER confuse or substitute them.",
            "total_vs_average": "Total is SUM(). Average is AVG(). Never substitute average for total.",
            "ranking_vs_filtering": "Ranking orders entities by metric. Filtering restricts dataset by condition. Ranking with threshold filters first, then ranks qualifying entities."
        },
        "direction_rules": {
            "DESC": ["top", "highest", "greatest", "largest", "most", "fullest", "maximum", "best", "leading", "highest occupied", "most utilized", "largest capacity"],
            "ASC": ["bottom", "lowest", "least", "emptiest", "minimum", "worst", "lagging", "least utilized", "lowest occupied", "least inventory", "smallest"]
        },
        "limit_rules": {
            "default": 10,
            "scalar_extreme": "If user asks 'who is #1?', 'what is the highest', 'which plant has the highest occupied volume', 'which bin is the least utilized' -> limit 1 + concise single-line response.",
            "explicit_number": "top 10 -> limit 10, top 5 -> limit 5, bottom 10 -> limit 10",
            "all_entities": "all, every, complete, full ranking -> return all matching entities without arbitrary limit."
        },
        "tie_handling": "Entities with equal metric values receive identical rank using competition ranking (1, 2, 2, 4) with DENSE_RANK() or RANK().",
        "specific_entity_lookup": "Questions like 'what rank is Plant 1258?' or 'where does bin NRJP2124D2 stand?' calculate the entity's position within the full ranking population and return concise rank statement.",
        "explanation_rule": "'Why is Plant X ranked #1?' explains the ranking metric difference compared to the next-ranked entity without unrelated clutter.",
        "visualization_rule": "Do not automatically add a chart to a ranking request. Output format is table / ranking_table unless explicit visualization requested."
    },

    # =========================================================================
    # 9. UNIVERSAL DETAIL / RESPONSE-DEPTH CONTEXT & RULES
    # =========================================================================
    "response_depth_rules": {
        "description": "Detail is a semantic mode, NOT a button.",
        "triggers": [
            "detail", "details", "detailed", "explain", "explain in detail",
            "elaborate", "deep dive", "break it down", "full details",
            "complete breakdown", "comprehensive view", "in-depth",
            "drill down", "granular analysis", "itemized breakdown",
            "show me the details", "give me more detail"
        ],
        "behavior": [
            "Preserve the same intent, scope, and filters.",
            "Increase response depth to DETAILED.",
            "Detailed response contains: 1. detailed summary, 2. relevant KPIs, 3. useful breakdown dimension, 4. relevant chart when meaningful, 5. detailed table.",
            "Do NOT require 'Generate Detailed Analysis' button or manual click."
        ]
    },

    # =========================================================================
    # 10. RESPONSE-FORMAT DECISION ENGINE
    # =========================================================================
    "response_format_rules": {
        "decision_order": [
            "1. User intent",
            "2. Requested granularity",
            "3. Requested depth (concise vs normal vs detailed)",
            "4. Explicit visualization request",
            "5. Result shape",
            "6. Output format mode"
        ],
        "output_modes": [
            "single_line",
            "kpi",
            "table",
            "ranking_table",
            "comparison_table",
            "chart_plus_summary",
            "detail_analysis",
            "narrative",
            "status"
        ],
        "single_line_candidates": [
            "total / overall value",
            "count / how many",
            "percentage",
            "average",
            "minimum / maximum scalar",
            "yes/no status",
            "one specific entity lookup",
            "which plant has the highest...",
            "what is the utilization of Bin X?"
        ],
        "single_line_override_triggers": [
            "one line", "single line", "single statement",
            "just the number", "just the percentage", "briefly"
        ],
        "single_line_suppression": "Single-line mode must suppress unnecessary tables, charts, KPI cards, raw-row previews, and action buttons."
    },

    # =========================================================================
    # 11. VISUALIZATION RULES (Presentation vs Data Intent)
    # =========================================================================
    "visualization_rules": {
        "default": {
            "show_chart": False,
            "architecture": "Summary + Relevant Table / KPI (Clean, uncluttered response)"
        },
        "explicit_triggers": [
            "show a graph for this", "show me a graph", "show graph",
            "visualize the comparison", "give me a chart", "give me a chart of the top 10",
            "visualize this", "plot the trend", "plot this", "chart for this"
        ],
        "chart_suppression_triggers": [
            "without a chart", "no chart", "without chart", "no graph", "just the table", "plain text"
        ],
        "rule": "Graph is a presentation request, NOT a replacement for analytical intent. Default to no chart unless explicitly requested or semantic detail mode explicitly requires it."
    },

    # =========================================================================
    # 12. CONVERSATION STATE RULES (Multi-Turn Persistence)
    # =========================================================================
    "conversation_state_rules": {
        "state_dimensions": [
            "entity",
            "metric",
            "aggregation",
            "filters",
            "ranking_direction",
            "limit",
            "range_filters",
            "comparison_entities",
            "time_range",
            "response_depth",
            "chart_requested"
        ],
        "modification_rule": "Only modify the state dimension mentioned by the user; keep all other dimensions intact."
    },

    # =========================================================================
    # BACKWARD COMPATIBILITY ALIASES & POLICIES
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
            "rule": "Isolate query to specific bin identifier (e.g. NRJP2124D2)."
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

    "response_templates": {
        "plant_bin_utilization_detail": {
            "description": "Multi-tiered template for plant-scoped bin utilization inquiries",
            "trigger": {
                "intent": "BIN_UTILIZATION",
                "scope": "PLANT",
                "detail_request": True
            },
            "default_response": {
                "sections": ["summary", "relevant_kpis", "summary_table"],
                "summary": {
                    "template": "The bin utilization for **Plant {plant}** is **{bin_utilization}%**, with **{occupied_bins:,}** of **{total_bins:,}** total bins currently occupied and **{empty_bins:,}** empty bins available for put-away."
                }
            },
            "detailed_response": {
                "sections": ["detailed_summary", "chart", "detailed_table"],
                "granularity": "STORAGE_LOCATION",
                "chart": {
                    "type": "bar",
                    "title": "Plant {plant} Bin Utilization by Storage Location (%)",
                    "xAxis": "Storage Location",
                    "yAxis": "Bin Utilization %"
                }
            }
        }
    },

    "bin_utilization_policy": {
        "calculation_rules": {
            "bin_utilization_pct": "(COUNT(DISTINCT i.BinNo) * 100.0) / NULLIF(COUNT(DISTINCT b.BinLocation), 0)",
            "volume_utilization_pct": "(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END) * 100.0) / NULLIF(SUM(b.Volume), 0)",
            "overall_warehouse_utilization": "Calculate from total occupied and total capacity for complete requested scope. Do NOT average percentages.",
            "plant_specific": "Apply plant filter before calculating the metric.",
            "rankings": "Calculate metric at bin granularity before sorting."
        }
    },

    # =========================================================================
    # 13. CAPACITY RULES (Capacity-Based Query Context)
    # =========================================================================
    "capacity_rules": {
        "purpose": "Understand and answer all natural-language questions related to warehouse/bin capacity based on the meaning of the query without depending on exact predefined questions.",
        "domain": {
            "total_bin_capacity": "Total physical storage volume assigned to a bin (b.Volume) or warehouse (SUM(b.Volume)).",
            "occupied_volume": "Amount of storage volume currently occupied by inventory (SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0))).",
            "available_capacity": "Unused capacity remaining in a bin or warehouse (Total Capacity - Occupied Volume).",
            "capacity_utilization_pct": "Percentage of capacity currently occupied ((Occupied Volume / Total Capacity) * 100)."
        },
        "query_types": {
            "total_capacity": {
                "description": "Total warehouse or plant capacity requests (e.g. 'What is the total capacity?', 'Show total bin capacity', 'How much capacity does this warehouse have?').",
                "formula": "SUM(b.Volume)",
                "note": "Do NOT confuse total capacity with available capacity. For warehouse: aggregate all bins across all plants without limits."
            },
            "available_capacity": {
                "description": "Available/free/remaining/unused space requests (e.g. 'How much space is left?', 'How much capacity is still available?', 'Which bins have free space?', 'How much unused capacity is there?').",
                "formula": "SUM(b.Volume) - SUM(Occupied Volume)",
                "note": "Words such as unused capacity, free capacity, free space, remaining capacity, spare capacity, available space map to Available Capacity."
            },
            "occupied_volume": {
                "description": "Occupied storage volume requests (e.g. 'How much space is occupied?', 'Show occupied volume', 'How much warehouse capacity is being used?').",
                "formula": "SUM(Occupied Volume)",
                "note": "Interpret as Occupied Volume, not Total Capacity. Do not substitute utilization percentage unless requested."
            },
            "capacity_utilization": {
                "description": "Percentage of capacity used (e.g. 'What percentage of capacity is being used?', 'What is the capacity utilization?').",
                "formula": "(Occupied Volume / Total Capacity) * 100",
                "note": "Overall warehouse/plant utilization must be SUM(Occupied Volume) / SUM(Total Capacity) * 100. Never average percentages."
            },
            "single_bin_capacity": {
                "description": "Specific bin capacity lookup (e.g. 'What is the capacity of bin NRJP2124D2?').",
                "output_fields": ["Bin", "Total Capacity", "Occupied Volume", "Available Capacity", "Utilization %"]
            },
            "capacity_by_plant": {
                "description": "Capacity for a specific plant (e.g. 'Show capacity for Plant 1258', 'What is the storage capacity of Plant 1258?').",
                "table_format": ["Plant", "Total Capacity", "Occupied Volume", "Available Capacity", "Utilization %"]
            },
            "capacity_comparison": {
                "description": "Capacity comparison between plants (e.g. 'Compare capacity between Plant 1258 and Plant 7228', 'Which plant has more available capacity?').",
                "table_format": ["Plant", "Total Capacity", "Occupied Volume", "Available Capacity", "Utilization %"],
                "rule": "Only compare requested plants and provide a concise conclusion."
            },
            "capacity_ranking": {
                "description": "Ranking bins or plants by capacity metrics (e.g. 'Rank bins by available capacity', 'Top 10 bins with most free capacity', 'Show bins with least available capacity').",
                "rule": "Available capacity: most -> DESC, least -> ASC. Total capacity: lowest -> ASC on Total Capacity. Never interchange metrics."
            },
            "capacity_ranges": {
                "description": "Capacity range filtering.",
                "total_capacity_range": "e.g. 'Bins between 400 and 600 FT³' -> 400 <= Total Capacity <= 600 FT³.",
                "available_capacity_range": "e.g. 'Bins with 100 to 300 FT³ free space' -> 100 <= Available Capacity <= 300 FT³.",
                "utilization_range": "e.g. 'Bins between 50% and 80% utilization' -> 50% <= Utilization % <= 80%."
            },
            "empty_bins_capacity": {
                "description": "Capacity of empty bins (e.g. 'How much capacity is available in empty bins?').",
                "formula": "SUM(Total Capacity of empty bins where Occupied Volume = 0)."
            },
            "capacity_summary": {
                "description": "Broad capacity summary request (e.g. 'Give me a capacity summary').",
                "metrics": ["Total Capacity", "Occupied Volume", "Available Capacity", "Utilization %"]
            },
            "compound_capacity_utilization": {
                "description": "COMPOUND CAPACITY + UTILIZATION QUERY: When the user asks for bins using a combination such as 'low capacity but high utilization', 'small bins with high utilization', 'low-capacity highly utilized bins', or semantically equivalent wording, the chatbot must identify the requested entity as Bin and apply BOTH conditions to the same bin records. It must not return plant-level or warehouse-level summaries unless explicitly requested. The query must be processed as: Low Capacity CONDITION AND High Utilization CONDITION. The response must contain the matching individual bins and, at minimum, show: Bin | Capacity | Utilization % (and Occupied Volume if relevant). 'Low' and 'high' must use predefined project thresholds if available. If no thresholds are defined, the chatbot must ask for clarification rather than inventing arbitrary thresholds.",
                "minimum_columns": ["Bin", "Capacity", "Utilization %"],
                "optional_columns": ["Occupied Volume"]
            },
            "entity_preservation": {
                "rule": "ENTITY PRESERVATION RULE: If the user asks 'Find bins…', the final result must be at bin level. Do not replace the requested bin-level result with Plant Breakdown, Warehouse Summary, aggregate statistics, or unrelated charts."
            }
        },
        "response_rules": {
            "single_line": "If user asks for one simple capacity value (e.g. 'What is the total capacity of Plant 1258?'), respond with a crisp single statement.",
            "compact_table": "For multi-entity bin capacity, use compact table [Bin, Total Capacity, Occupied Volume, Available Capacity] without unrelated fields.",
            "chart_rule": "No chart by default unless requested or required by detail mode.",
            "detail_mode": "If user includes detail triggers, automatically activate detail mode with summary, formulas, metrics, breakdown, and chart.",
            "conversation_followup": "Preserve entity=Bin, metric=Available Capacity, adjust limit, adjust direction, add plant filter, resolve pronouns ('they', 'these', 'those')."
        }
    },

    "response_and_intent_rules": [
        "1. Never determine the query type from a single keyword. Interpret the complete user request semantically.",
        "2. 'Inventory' does not automatically mean 'inventory records' or 'material list'.",
        "3. Distinguish: Total inventory quantity = SUM(quantity), Inventory records = COUNT(records), Unique materials = COUNT(DISTINCT material).",
        "4. Do not apply a Plant, Bin, Material, or other filter unless explicitly mentioned by the user or inherited from valid conversation context.",
        "5. If the user asks for a total, count, percentage, KPI, or single value, return the appropriate aggregation instead of a row-level detail table.",
        "6. If the user asks 'which', 'show me materials', 'list', or requests records, use a detail/list response.",
        "7. Default response format should be determined from user intent: KPI/count/value -> concise single-line statement; List/detail -> table; Ranking -> ranking table; Comparison -> comparison output; Explicit graph/chart request -> summary + relevant chart + table.",
        "8. Never show a large table when the user asks only for an aggregate KPI.",
        "9. After query execution, validate that the result matches the user's requested intent, aggregation, scope, and response format.",
        "10. Never invent or assume a Plant, Bin, Material, or other filter.",
        "11. COMPOUND CAPACITY + UTILIZATION QUERY: When the user asks for bins using a combination such as 'low capacity but high utilization', 'small bins with high utilization', 'low-capacity highly utilized bins', or semantically equivalent wording, the chatbot must identify the requested entity as Bin and apply BOTH conditions to the same bin records. It must not return plant-level or warehouse-level summaries unless explicitly requested. The query must be processed as: Low Capacity CONDITION AND High Utilization CONDITION. The response must contain matching individual bins showing at minimum: Bin | Capacity | Utilization % (and Occupied Volume). 'Low' and 'high' must use predefined project thresholds if available. If no thresholds are defined, the chatbot must ask for clarification rather than inventing arbitrary thresholds.",
        "12. ENTITY PRESERVATION RULE: If the user asks 'Find bins…', the final result must be at bin level. Do not replace the requested bin-level result with Plant Breakdown, Warehouse Summary, aggregate statistics, or unrelated charts."
    ]
}

# Predefined project capacity & utilization thresholds (None by default to require explicit clarification unless configured)
PROJECT_CAPACITY_THRESHOLDS: dict[str, float | None] = {
    "low_capacity_threshold": None,
    "high_capacity_threshold": None,
    "high_utilization_threshold": None,
    "low_utilization_threshold": None,
}
