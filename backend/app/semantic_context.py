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
        },
        "TOTAL_INVENTORY_QUANTITY": {
            "meaning": "Sum of total unrestricted inventory quantity stored across warehouse bins",
            "metric": "total_inventory_quantity",
            "entity": "inventory",
            "field": "UnrestrictedQty",
            "aggregation": "SUM",
            "scope": "ALL_WAREHOUSE",
            "formula": "SUM(UnrestrictedQty)",
            "synonyms": [
                "total warehouse inventory",
                "what is the total inventory",
                "how much inventory is currently in the warehouse",
                "what is the total inventory quantity",
                "how many units are currently in inventory",
                "give me the current warehouse inventory",
                "how much stock is in the warehouse",
                "what is the total stock",
                "total unrestricted inventory",
                "total units in inventory",
                "how much total inventory",
                "total stock quantity",
                "current warehouse inventory",
                "how many total units",
                "how much inventory do we have",
                "total inventory",
                "total stock"
            ],
            "default_response": {
                "format": "SINGLE_LINE",
                "show_table": False,
                "show_chart": False,
                "example_warehouse": "Total warehouse inventory is 4,464,910 units.",
                "example_plant": "Total inventory in Plant {plant} is {qty} units."
            },
            "if_user_requests_chart": {
                "show": [
                    "summary",
                    "relevant_chart",
                    "supporting_table"
                ],
                "chart_type": "bar",
                "group_by": "Plant"
            }
        },
        "INVENTORY_RECORDS_COUNT": {
            "meaning": "Total physical count of rows / records in the inventory master dataset",
            "metric": "inventory_records_count",
            "entity": "inventory",
            "field": "rows",
            "aggregation": "COUNT",
            "scope": "ALL_WAREHOUSE",
            "formula": "COUNT(*)",
            "synonyms": [
                "how many inventory records are there",
                "count of inventory records",
                "total inventory records",
                "how many inventory rows are there",
                "number of inventory records",
                "number of inventory rows",
                "how many records in inventory",
                "inventory record count",
                "total records in inventory",
                "inventory rows count"
            ],
            "default_response": {
                "format": "SINGLE_LINE",
                "show_table": False,
                "show_chart": False,
                "example_warehouse": "There are 35,419 inventory records.",
                "example_plant": "There are 5,517 inventory records in Plant {plant}."
            }
        },
        "UNIQUE_MATERIALS_COUNT": {
            "meaning": "Total count of distinct active material SKUs in the inventory dataset",
            "metric": "unique_materials_count",
            "entity": "material",
            "field": "Material",
            "aggregation": "COUNT_DISTINCT",
            "scope": "ALL_WAREHOUSE",
            "formula": "COUNT(DISTINCT Material)",
            "synonyms": [
                "how many materials are in inventory",
                "how many materials are there",
                "how many unique materials",
                "how many distinct materials",
                "number of materials in inventory",
                "how many materials do we have",
                "number of unique skus",
                "how many skus in inventory",
                "count of unique materials",
                "unique materials in warehouse"
            ],
            "default_response": {
                "format": "SINGLE_LINE",
                "show_table": False,
                "show_chart": False,
                "example_warehouse": "There are 2,883 unique materials in inventory.",
                "example_plant": "There are {count} unique materials in Plant {plant}."
            }
        },
        "LOWEST_BIN_UTILIZATION": {
            "meaning": "Lowest bin utilization identified across facilities/plants or ranked at the bottom of storage bins",
            "metric": "lowest_bin_utilization",
            "entity": "plant_or_bin",
            "aggregation": "MIN_OR_RANK_ASC",
            "synonyms": [
                "lowest bin utilization", "minimum bin utilization", "least bin utilization",
                "plant with the lowest bin utilization", "which plant has the lowest bin utilization",
                "lowest bin utilization plant", "least utilized plant", "which facility has the lowest bin utilization",
                "least utilized bin", "lowest utilized bin", "bottom bin utilization"
            ],
            "default_response": {
                "format": "SINGLE_LINE_OR_TABLE",
                "single_line_rule": "If user asks scalar question (e.g. 'which plant has the lowest bin utilization', 'what is the lowest bin utilization'), return concise single-line answer with facility and percentage.",
                "detail_rule": "If user requests breakdown, ranking list, or detail, return ordered ranking table.",
                "show_chart": False
            }
        },
        "HIGHEST_BIN_UTILIZATION": {
            "meaning": "Highest bin utilization identified across facilities/plants or ranked at the top of storage bins",
            "metric": "highest_bin_utilization",
            "entity": "plant_or_bin",
            "aggregation": "MAX_OR_RANK_DESC",
            "synonyms": [
                "highest bin utilization", "maximum bin utilization", "most bin utilization", "top bin utilization",
                "plant with the highest bin utilization", "which plant has the highest bin utilization",
                "highest bin utilization plant", "most utilized plant", "which facility has the highest bin utilization",
                "most utilized bin", "highest utilized bin", "top utilized bin"
            ],
            "default_response": {
                "format": "SINGLE_LINE_OR_TABLE",
                "single_line_rule": "If user asks scalar question (e.g. 'which plant has the highest bin utilization', 'what is the highest bin utilization'), return concise single-line answer with facility and percentage.",
                "detail_rule": "If user requests breakdown, ranking list, or detail, return ordered ranking table.",
                "show_chart": False
            }
        },
        "GENERAL_RANKING_SYSTEM": {
            "meaning": "Universal ranking system providing top or bottom rank orders across any warehouse domain (bins, plants, materials, storage locations)",
            "intent": "RANKING",
            "supported_entities": ["bins", "plants", "materials", "storage_locations"],
            "default_response": {
                "format_detection": "If user requests scalar leader/worst ('who is #1', 'top plant', 'single statement'), return single-line summary. If user requests 'ranking', 'list', 'top N', 'bottom N', 'detailed form', return formatted ranking table with Rank, Entity, Metrics.",
                "show_chart": False
            },
            "if_user_requests_chart": {
                "show": ["summary", "relevant_chart", "supporting_table"]
            }
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
    },

    # =========================================================================
    # 7. RESPONSE TEMPLATES (Specialized Multi-Tiered Response Architectures)
    # =========================================================================
    "response_templates": {
        "plant_bin_utilization_detail": {
            "description": "Deterministic multi-tiered template for plant-scoped bin utilization inquiries requesting details",
            "trigger": {
                "intent": "BIN_UTILIZATION",
                "scope": "PLANT",
                "detail_request": True
            },
            "default_response": {
                "sections": [
                    "summary",
                    "relevant_kpis",
                    "summary_table",
                    "detail_offer"
                ],
                "summary": {
                    "max_lines": 2,
                    "template": "The bin utilization for **Plant {plant}** is **{bin_utilization}%**, with **{occupied_bins:,}** of **{total_bins:,}** total bins currently occupied and **{empty_bins:,}** empty bins available for put-away."
                },
                "relevant_kpis": {
                    "metrics": [
                        "bin_utilization",
                        "occupied_bins",
                        "empty_bins",
                        "total_bins"
                    ]
                },
                "table": {
                    "type": "summary",
                    "include": [
                        "Plant",
                        "Total Bins",
                        "Occupied Bins",
                        "Empty Bins",
                        "Bin Utilization %"
                    ]
                },
                "follow_up": {
                    "message": "Would you like me to generate a detailed version of this analysis?",
                    "action": "generate_detail",
                    "action_prompt": "Generate detailed bin utilization analysis for Plant {plant}",
                    "label": "Generate Detailed Analysis"
                }
            },
            "detailed_response": {
                "sections": [
                    "detailed_summary",
                    "chart",
                    "detailed_table"
                ],
                "granularity": "STORAGE_LOCATION",
                "chart": {
                    "type": "bar",
                    "title": "Plant {plant} Bin Utilization by Storage Location (%)",
                    "xAxis": "Storage Location",
                    "yAxis": "Bin Utilization %"
                },
                "table": {
                    "type": "detailed",
                    "include": [
                        "Plant",
                        "Storage Location",
                        "Total Bins",
                        "Occupied Bins",
                        "Empty Bins",
                        "Bin Utilization %",
                        "Total Capacity Volume (FT3)",
                        "Occupied Volume (FT3)"
                    ]
                }
            }
        }
    },

    # =========================================================================
    # 8. VISUALIZATION RULES (Generic Explicit Graph Request Architecture)
    # =========================================================================
    "visualization_rules": {
        "description": "Universal 2-tier visualization framework applicable across ALL warehouse analytical domains.",
        "supported_domains": [
            "BIN_UTILIZATION",
            "MATERIAL_ANALYSIS",
            "PLANT_COMPARISON",
            "EMPTY_BINS",
            "TOP_AND_BOTTOM_BINS",
            "INVENTORY_TRENDS",
            "DIVISION_BREAKDOWN",
            "CONSOLIDATION_CANDIDATES",
            "STORAGE_LOCATION_COMPARISON",
            "DATA_QUALITY_ANOMALIES"
        ],
        "default": {
            "show_chart": False,
            "architecture": "Summary + Relevant Table / KPI (Clean, uncluttered response)"
        },
        "user_explicitly_requests_chart": {
            "triggers": [
                "show me a graph",
                "show graph",
                "give me a chart",
                "visualize this",
                "show this in graph",
                "create a chart",
                "can you graph this",
                "graph for this",
                "chart for this",
                "show this in graphical form",
                "draw a chart",
                "plot this",
                "visualize"
            ],
            "action": [
                "preserve_previous_query_context",
                "generate_relevant_chart",
                "show_summary",
                "show_chart",
                "show_relevant_table"
            ]
        },
        "follow_up_visualization": {
            "examples": [
                "Show me a graph for this",
                "Can you visualize this?",
                "Give me a chart",
                "Show this in graphical form"
            ],
            "action": {
                "reference": "previous_query",
                "do_not_reask_context": True,
                "domain_chart_mappings": {
                    "material_volume_share": {"chart_type": "bar", "x": "Material", "y": "% of Total Bin Volume"},
                    "warehouse_utilization": {"chart_type": "bar", "x": "Plant", "y": "BinUtilizationPct"},
                    "plant_bin_utilization_detail": {"chart_type": "bar", "x": "Storage Location", "y": "UtilizationPct"},
                    "top_utilized_bins": {"chart_type": "bar", "x": "Bin", "y": "Occupied Volume"},
                    "least_utilized_bins": {"chart_type": "bar", "x": "Bin", "y": "Occupied Volume"},
                    "trend_analysis": {"chart_type": "line", "x": "Month", "y": "TotalQuantity"},
                    "division_breakdown": {"chart_type": "pie", "x": "Division", "y": "TotalQuantity"},
                    "consolidation": {"chart_type": "bar", "x": "Material", "y": "ActiveBinCount"},
                    "storage_location_comparison": {"chart_type": "bar", "x": "Storage Location", "y": "Total Inventory Quantity"}
                }
            }
        }
    },

    # =========================================================================
    # 9. RESPONSE AND INTENT MASTER RULES
    # =========================================================================
    "response_and_intent_rules": [
        "1. Never determine the query type from a single keyword. Interpret the complete user request semantically.",
        "2. 'Inventory' does not automatically mean 'inventory records' or 'material list'.",
        "3. Distinguish: Total inventory quantity = SUM(quantity), Inventory records = COUNT(records), Unique materials = COUNT(DISTINCT material).",
        "4. Do not apply a Plant, Bin, Material, or other filter unless explicitly mentioned by the user or inherited from valid conversation context.",
        "5. If the user asks for a total, count, percentage, KPI, or single value, return the appropriate aggregation instead of a row-level detail table.",
        "6. If the user asks 'which', 'show me materials', 'list', or requests records, use a detail/list response.",
        "7. Default response format should be determined from user intent: KPI/count/value -> concise single-line statement; List/detail -> table; Ranking -> ranking table; Comparison -> comparison output; Explicit graph/chart request -> summary + relevant chart + table.",
        "8. Never show a large table when the user asks only for an aggregate KPI.",
        "9. After query execution, validate that the result matches the user's requested intent, aggregation, scope, and response format. If it does not match, reject the result and regenerate the query.",
        "10. Never invent or assume a Plant, Bin, Material, or other filter."
    ],

    # =========================================================================
    # 10. BIN UTILIZATION CONTEXT & RESPONSE POLICY (Complete Specification)
    # =========================================================================
    "bin_utilization_policy": {
        "core_pipeline": "USER QUESTION -> INTENT -> METRIC -> FILTERS -> CALCULATION -> OUTPUT TYPE -> RESPONSE (with CONVERSATION CONTEXT)",
        "concepts": {
            "bin": "A warehouse storage location (bin, storage bin, storage location, location)",
            "bin_utilization": "How much of a bin's capacity is occupied (utilization, used %, occupancy, capacity usage)",
            "occupied_volume": "Volume currently occupied in a bin (used volume, occupied volume, volume used)",
            "total_capacity": "Maximum volume/capacity available in a bin (bin capacity, total capacity, max capacity)",
            "available_capacity": "Capacity still available for use: TOTAL BIN CAPACITY - TOTAL OCCUPIED VOLUME (free space, remaining capacity, available space)",
            "empty_bin": "A bin with zero occupied inventory/volume according to project data definition: UnrestrictedQty = 0 or BinNo IS NULL (empty bin, unused bin, unoccupied bin)",
            "plant": "A warehouse/organizational plant used as a filter (plant, site, warehouse plant)",
            "top_utilized": "Highest utilization percentages (most utilized, highest utilization, fullest)",
            "least_utilized": "Lowest utilization percentages (least utilized, lowest utilization, emptiest by %)"
        },
        "calculation_rules": {
            "bin_utilization_pct": "(TOTAL OCCUPIED VOLUME / TOTAL BIN CAPACITY) * 100",
            "available_capacity": "TOTAL BIN CAPACITY - TOTAL OCCUPIED VOLUME",
            "overall_warehouse_utilization": "Calculate from total occupied volume and total bin capacity for the complete filtered dataset. Do NOT calculate overall utilization as the simple average of individual bin percentages.",
            "plant_specific": "Apply plant filter before calculating the metric.",
            "rankings": "Calculate/obtain each bin's utilization and sort by the requested direction."
        },
        "intent_categories": {
            "single_metric": {"primary_output": "One number + short explanation (1-3 lines)", "avoid": "Unrequested table or chart"},
            "count": {"primary_output": "Count + short criterion", "avoid": "Full record list"},
            "list": {"primary_output": "Compact table/list", "avoid": "Long narrative"},
            "top_bottom_ranking": {"primary_output": "Ranked table with Rank, Bin, Plant, Utilization %", "avoid": "Unrequested charts"},
            "comparison": {"primary_output": "Compact comparison + conclusion", "avoid": "Every underlying row"},
            "capacity_analysis": {"primary_output": "Requested capacity metric(s): Total Capacity, Occupied Volume, Available Capacity", "avoid": "Unrelated inventory details"},
            "lookup": {"primary_output": "One-bin result", "avoid": "Whole warehouse dataset"},
            "detail_request": {"primary_output": "When user includes 'detail', 'explain', 'breakdown', or similar context: automatically recognize the detail intent and return detailed summary -> storage location chart -> detailed breakdown table directly (no manual button required). For normal overview: return clean concise summary table.", "avoid": "Unnecessary confirmation buttons or raw DB dumps"}
        },
        "master_instruction": "BIN UTILIZATION CONTEXT: Understand bin-utilization questions by semantic meaning, not exact question matching. Map synonyms such as most utilized/highest/fullest, least utilized/lowest/least-used, empty/unoccupied/zero inventory, and free/remaining/available capacity to the correct intent. Extract metric, plant filter, bin filter, threshold, ranking direction, limit, aggregation, and requested output style from the user's wording. When the user asks for 'detail', 'details', 'explain', 'explanation', 'breakdown', or 'elaborate', immediately recognize this analytical depth context and return the detailed breakdown with chart visualization and granular data without prompting for manual buttons. Preserve relevant context across follow-up questions; resolve 'ones', 'them', 'those', 'same', and similar references from the latest applicable query. Do not invent filters. If no plant is specified, do not silently select a plant. For overall utilization, calculate total occupied volume divided by total bin capacity, multiplied by 100, using the complete applicable dataset—not the average of row-level percentages. For available capacity, calculate total capacity minus occupied volume. For rankings, sort the requested bins by utilization in the requested direction and apply the requested N after filtering. Choose the minimum response format that fully answers the question: a single value for a single metric, a count for 'how many', a compact table for lists/rankings, a comparison table for comparisons, and a summary/table for analytical requests. Add a chart only when the user asks for one, when detail/explain is requested, or when a distribution/comparison report clearly benefits from one. Never add unrequested metrics, raw rows, or redundant action buttons. Always prioritize correctness, relevance, and concise presentation."
    }
}


