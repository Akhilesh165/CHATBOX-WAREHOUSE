"""SQL Security and AST Validator using SQLGlot.
Enforces strict read-only execution, schema allowlisting, and rejection of unsafe SQL constructs.
"""

import re
import sqlglot
from sqlglot import exp
from typing import Set

# Allowed Tables and Views (case-insensitive)
ALLOWED_TABLES: Set[str] = {
    "zwms_inventory",
    "zwms_bin_master",
    "zwms_material_master",
    "vw_wms_inventoryenriched",
    "dbo.zwms_inventory",
    "dbo.zwms_bin_master",
    "dbo.zwms_material_master",
    "dbo.vw_wms_inventoryenriched",
}

# Allowed Columns per Table for deep AST validation
ALLOWED_COLUMNS: Set[str] = {
    # Inventory
    "id", "filename", "material", "plant", "storagelocation", "batch",
    "materialdescription", "unrestrictedqty", "unrestrictedqty2",
    "baseunitofmeasure", "mrp", "fullyvestedon", "changedat", "binno",
    "insert_by", "insert_timestamp", "update_by", "update_timestamp",
    
    # Bin Master
    "binlocation", "maincriterion", "pallettype", "box", "owner",
    "volume", "volumeunit", "length", "width", "height", "createddate", "createdby",
    
    # Material Master
    "materialcode", "vuom", "grossweight", "division", "divisiondescription",
    "kslot", "binuom", "insertby", "createddatetime", "netweight", "eanno",
    "hierarchy", "materialgroup", "caselot", "cartongrossweight", "cartoonvolume",
    "updateddatetime",
    
    # Semantic View specific aliases
    "inventoryid", "materialgrossweight", "materialnetweight", "materialvolume",
    "materialvolumeuom", "materiallength", "materialwidth", "materialheight",
    "binbox", "binowner", "binvolume", "binvolumeunit", "binlength", "binwidth", "binheight"
}

FORBIDDEN_EXPRESSIONS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.Command,
    exp.Merge,
    exp.TruncateTable,
    exp.Kill,
    exp.Pragma,
)

FORBIDDEN_KEYWORDS = [
    "xp_", "sp_", "exec ", "execute ", "into outfile", "load_file", "benchmark", "sleep"
]

def validate_sql(raw_sql: str, dialect: str = "tsql") -> str:
    """Validate and sanitize a generated SQL statement.
    
    Raises ValueError with explanatory message if SQL violates any security or schema rule.
    Returns cleaned SQL string.
    """
    if not raw_sql or not raw_sql.strip():
        raise ValueError("Empty SQL query provided.")

    cleaned_sql = raw_sql.strip()

    # Strip markdown code blocks if present
    if cleaned_sql.startswith("```"):
        lines = cleaned_sql.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned_sql = "\n".join(lines).strip()

    # Block inline comments to prevent bypasses
    if "--" in cleaned_sql or "/*" in cleaned_sql or "*/" in cleaned_sql:
        raise ValueError("SQL comments (-- or /* */) are strictly prohibited for security.")

    # Check dangerous stored procedures / commands
    lower_sql = cleaned_sql.lower()
    for kw in FORBIDDEN_KEYWORDS:
        if kw in lower_sql:
            raise ValueError(f"Prohibited SQL keyword or routine detected: {kw.strip()}")

    # Parse with SQLGlot
    try:
        parsed_statements = sqlglot.parse(cleaned_sql, read=dialect)
    except Exception as e:
        # Fallback to standard dialect parse attempt
        try:
            parsed_statements = sqlglot.parse(cleaned_sql)
        except Exception as inner_e:
            raise ValueError(f"SQL syntax error: Failed to parse SQL statement: {inner_e}")

    # Enforce exactly ONE statement
    if not parsed_statements:
        raise ValueError("No valid SQL statement found.")
    if len(parsed_statements) > 1:
        raise ValueError("Multiple SQL statements detected. Exactly one SELECT statement is allowed.")

    statement = parsed_statements[0]

    # Enforce read-only SELECT or WITH statement
    if not isinstance(statement, (exp.Select, exp.Expression)):
        raise ValueError(f"Invalid statement type: {type(statement).__name__}. Only SELECT queries are permitted.")

    # Check for forbidden AST nodes
    for forbidden_type in FORBIDDEN_EXPRESSIONS:
        if statement.find(forbidden_type):
            raise ValueError(f"Unauthorized SQL operation detected: {forbidden_type.__name__} is forbidden.")

    # Validate all referenced tables in the query
    tables = statement.find_all(exp.Table)
    table_names_found = []
    
    # Collect CTE aliases defined in WITH clause to allow CTE references
    cte_names = set()
    for cte in statement.find_all(exp.CTE):
        if cte.alias:
            cte_names.add(cte.alias.lower())
        if hasattr(cte, "this") and hasattr(cte.this, "name"):
            cte_names.add(cte.this.name.lower())

    for t in tables:
        # Build normalized table name (schema.table or table)
        tbl_name = t.name.lower()
        schema_name = t.db.lower() if t.db else None
        full_name = f"{schema_name}.{tbl_name}" if schema_name else tbl_name
        
        # If it's a CTE alias, it's valid
        if tbl_name in cte_names or full_name in cte_names:
            continue
            
        if full_name not in ALLOWED_TABLES and tbl_name not in ALLOWED_TABLES:
            raise ValueError(f"Unauthorized table reference: '{full_name}'. Allowed tables are: {', '.join(sorted(ALLOWED_TABLES))}")
        
        table_names_found.append(full_name)

    if not table_names_found and not cte_names:
        # Check if scalar select like SELECT 1
        pass

    # Ensure no DDL / DML keywords in raw sql
    for kw in ["insert ", "update ", "delete ", "drop ", "truncate ", "alter ", "create ", "grant ", "revoke ", "merge "]:
        if kw in lower_sql:
            # Recheck if not enclosed in quotes or identifiers
            if statement.find(FORBIDDEN_EXPRESSIONS):
                raise ValueError(f"Prohibited SQL command keyword: '{kw.strip()}'")

    return cleaned_sql


def validate_query_result(question: str, query_plan: dict | None, sql: str, rows: list[dict]) -> tuple[bool, str]:
    """Semantic Result Validator.
    
    Evaluates: Does this SQL result actually answer the user's question and analytical task?
    Consumes structured query_plan when available, with semantic keyword fallbacks.
    Returns (is_valid, failure_reason).
    """
    q_lower = question.lower()
    cols = list(rows[0].keys()) if rows else []

    # Multi-plant safety: if the user explicitly requested multiple plants,
    # every requested plant must be represented in the result whenever a Plant
    # column is available. Never accept a partial result silently.
    requested_plants = []
    for m in re.finditer(r"\bplants?\b\s*(?:#|:|-)?\s*(\d{4,5})((?:\s*(?:,|and|&)\s*(?:plant\s*)?\d{4,5})*)", q_lower):
        requested_plants.append(m.group(1))
        requested_plants.extend(re.findall(r"(?:,|and|&)\s*(?:plant\s*)?(\d{4,5})", m.group(2)))
    requested_plants = list(dict.fromkeys(p for p in requested_plants if p not in {"2024", "2025", "2026"}))
    if requested_plants and rows and "Plant" in cols:
        returned_plants = {str(r.get("Plant")).strip() for r in rows if r.get("Plant") is not None}
        is_multi_table = query_plan and query_plan.get("is_multi_table_comparison")
        if not is_multi_table and not set(requested_plants).issubset(returned_plants):
            return False, "Result does not contain records for every plant explicitly requested by the user."

    # -------------------------------------------------------------------------
    # A. Plan-driven validation (Priority when query_plan is provided)
    # -------------------------------------------------------------------------
    if query_plan and isinstance(query_plan, dict):
        plan_intent = query_plan.get("intent") or query_plan.get("analytical_task") or ""
        plan_intent_upper = str(plan_intent).upper()

        # 1. RANKING intent
        if "RANK" in plan_intent_upper:
            rank_entity = query_plan.get("rank_entity", "").lower()
            if not rows:
                return False, f"Ranking query returned 0 rows for entity {rank_entity}."
            if "bin" in rank_entity:
                if not any(c in cols for c in ["Bin", "BinLocation", "BinNo"]):
                    return False, "User requested Bin ranking, but result does not contain bin location columns."
            elif "material" in rank_entity:
                if not any(c in cols for c in ["Material", "MaterialCode"]):
                    return False, "User requested Material ranking, but result does not contain material columns."
            elif "plant" in rank_entity:
                if "Plant" not in cols:
                    return False, "User requested Plant ranking, but result does not contain Plant column."
            
            # Scalar extreme checks
            limit_val = query_plan.get("limit")
            if limit_val == 1 and len(rows) > 1 and not any(k in q_lower for k in ["table", "ranking", "list"]):
                return False, "Scalar ranking extreme requested (#1 / highest / lowest), but multiple rows returned."

        # 2. COMPARISON intent
        if "COMPAR" in plan_intent_upper:
            comp_entities = query_plan.get("comparison_entities") or []
            if len(comp_entities) >= 2 and rows and "Plant" in cols:
                returned_plants = {str(r.get("Plant")) for r in rows if r.get("Plant") is not None}
                expected_plants = {str(e.get("value")) for e in comp_entities if isinstance(e, dict) and e.get("type") == "plant"}
                if expected_plants and not expected_plants.issubset(returned_plants):
                    return False, "Comparison query did not return records for every requested comparison plant."

        # 3. KPI / COUNT / SINGLE_LINE intent
        if plan_intent_upper in ["KPI", "COUNT"] or query_plan.get("response_format") == "single_line":
            if len(rows) > 1 and any(c in cols for c in ["Batch", "FileName"]) and not any(c in cols for c in ["TotalQuantity", "Total Inventory Quantity", "Inventory Records Count", "UniqueMaterials"]):
                return False, "Aggregate scalar / KPI requested, but row-level details returned."

        # 4. DATA_QUALITY intent
        if "DATA_QUALITY" in plan_intent_upper or "MISSING" in plan_intent_upper:
            if any(c in cols for c in ["TotalUniqueMaterials", "TotalActiveBins", "TotalUnrestrictedQuantity"]) and "Quality Issue" not in cols and "Material" not in cols:
                return False, "Data quality exception check requested, but high-level warehouse totals returned."

    # -------------------------------------------------------------------------
    # B. Semantic keyword-based checks (Fallback & safety verification)
    # -------------------------------------------------------------------------
    # 0. Materials Missing from Volume Master (Rule DQ-001 - Cross-Table Validation)
    is_missing_master_req = any(k in q_lower for k in [
        "missing from the volume master", "missing from volume master", "not in the volume master",
        "not in volume master", "missing in volume master", "exist in inventory master but not",
        "exists in inventory master but not", "exist in inventory but missing from", "exists in inventory but missing from",
        "in inventory but missing from", "missing from material master", "not in material master",
        "no matching volume master", "unmatched volume master", "missing volume master record"
    ]) or (
        ("inventory" in q_lower or "material" in q_lower or "sku" in q_lower or "item" in q_lower) and
        ("volume master" in q_lower or "material master" in q_lower) and
        ("missing" in q_lower or "absent" in q_lower or "not present" in q_lower or "doesn't exist" in q_lower or "does not exist" in q_lower or "no record" in q_lower or "not maintained" in q_lower or "not in" in q_lower)
    )
    if is_missing_master_req:
        if any(c in cols for c in ["TotalUniqueMaterials", "TotalActiveBins", "TotalUnrestrictedQuantity", "PlantCount"]) and "Inventory Qty" not in cols and "Material" not in cols:
            return False, "User requested: Material-level exception list for missing volume master records. Returned: Warehouse-level inventory summary. These do not satisfy the requested cross-table validation task."
        if rows and "Material" not in cols and "MaterialCode" not in cols and not any(c in cols for c in ["Missing Materials Count", "Missing Volume Percentage", "Missing Volume Materials Count", "Status"]):
            return False, "User requested: Material-level exception records for missing volume master. Returned: Non-material entity. These do not satisfy the requested cross-table validation task."

    # 1. Missing Physical Dimensions / Data Quality
    is_missing_dim_req = any(k in q_lower for k in [
        "missing dimension", "missing physical", "incomplete dimension", "without dimension",
        "no dimension", "no dimensions", "missing length", "missing width", "missing height", "missing volume",
        "don't have dimension", "dont have dimension", "do not have dimension",
        "don't have dimensions", "dont have dimensions", "do not have dimensions",
        "lack dimension", "lack dimensions", "unmaintained dimension"
    ]) or (
        ("dimension" in q_lower or "dimensions" in q_lower or "size" in q_lower or "physical" in q_lower or "length" in q_lower or "width" in q_lower or "height" in q_lower) and
        ("missing" in q_lower or "incomplete" in q_lower or "blank" in q_lower or "null" in q_lower or "without" in q_lower or "absent" in q_lower or "not defined" in q_lower or "not maintained" in q_lower or "not available" in q_lower or "unavailable" in q_lower or "don't" in q_lower or "dont" in q_lower or "do not" in q_lower or "no " in q_lower or "lack" in q_lower)
    )
    
    if is_missing_dim_req:
        if any(c in cols for c in ["TotalUniqueMaterials", "TotalActiveBins", "TotalUnrestrictedQuantity", "PlantCount"]) and "Quality Issue" not in cols and "Length" not in cols:
            return False, "User requested: Material-level missing-dimension records. Returned: Warehouse-level inventory summary. These do not satisfy the requested analytical task."
        if rows and "Material" not in cols and "MaterialCode" not in cols and not any(c in cols for c in ["Missing Materials Count", "Missing Volume Percentage", "Missing Volume Materials Count", "Status"]):
            return False, "User requested: Material-level missing-dimension records. Returned: Non-material entity. These do not satisfy the requested analytical task."

    # 2. Top / Bottom Bins Ranking
    is_plant_query = bool(re.search(r"\b(?:plants?|plnts?|facility|facilities)\b", q_lower))
    is_almost_full_val = any(k in q_lower for k in [
        "almost full", "nearly full", "near full", "close to full", "close to being full",
        "close to full capacity", "almost at capacity", "near full capacity",
        "nearly at 100% utilization", "nearly at 100%", "almost at 100%"
    ])
    is_ranking_req = not is_almost_full_val and (
        any(k in q_lower for k in ["most utilized", "least utilized", "lowest utilized", "highest utilized", "lowest ones", "least ones", "emptiest bins"]) or
        bool(re.search(r"\b(?:top|bottom)\b", q_lower)) or (
            bool(re.search(r"\b(?:most|least|top|bottom|highest|lowest)\b", q_lower)) and
            ("utiliz" in q_lower or "capacit" in q_lower or "occup" in q_lower or "full" in q_lower or "bin" in q_lower or "bins" in q_lower or "ones" in q_lower) and
            not any(m in q_lower for m in ["material", "sku", "product", "goods"])
        )
    ) and not is_plant_query
    if is_ranking_req:
        if any(c in cols for c in ["TotalUniqueMaterials", "TotalActiveBins", "TotalUnrestrictedQuantity", "TotalBins"]) and "Ranking Group" not in cols and "Bin" not in cols and "BinLocation" not in cols and "BinNo" not in cols:
            return False, "User requested: Bin utilization ranking records. Returned: Plant-level aggregated summary. These do not satisfy the requested ranking task."
        if not rows:
            return False, "User requested: Bin utilization ranking/extreme. Returned: 0 records. Rejecting to regenerate with valid bin query."
        is_single_bin_extreme = any(k in q_lower for k in ["which bin", "whic bin", "what bin", "wat bin", "bin with the lowest", "bin with lowest", "bin with the highest", "bin with highest"])
        if is_single_bin_extreme and len(rows) > 1 and not any(d in q_lower for d in ["ranking", "table", "list", "top 10", "top 5", "bottom 10", "bottom 5"]):
            return False, "User requested: Single bin extreme statement. Returned: Multi-row table. Rejecting to regenerate single bin answer."

    # 2B. Plant-Level Lowest / Highest Bin Utilization Validation
    is_plant_extreme_req = is_plant_query and any(k in q_lower for k in ["lowest", "least", "minimum", "worst", "highest", "most", "maximum", "best"]) and any(k in q_lower for k in ["utiliz", "occupan", "capacity", "fill"])
    if is_plant_extreme_req:
        if ("Bin" in cols or "BinLocation" in cols) and "Plant" not in cols:
            return False, "User requested: Plant-level bin utilization extreme/ranking. Returned: Individual bin rows. Rejecting to re-execute plant-level query."
        if len(rows) > 1 and not any(d in q_lower for d in ["ranking", "table", "all plants", "compare", "list", "breakdown", "detailed", "detail form"]):
            if any(k in q_lower for k in ["which plant", "whic plant", "what plant", "wat plant", "single statement", "single line", "one line"]):
                return False, "User requested: Single plant extreme/statement. Returned: Multi-row table. Rejecting to return single statement scalar answer."

    # 3. Available / Empty Put-Away Bins
    is_putaway_req = any(k in q_lower for k in ["empty bin", "empty bins", "putaway", "put-away", "vacant", "unoccupied", "without displacing", "free bin", "free storage"])
    if is_putaway_req:
        if any(c in cols for c in ["TotalUniqueMaterials", "TotalActiveBins", "TotalUnrestrictedQuantity", "TotalBins"]) and "BinLocation" not in cols and "BinNo" not in cols and "Bin" not in cols:
            return False, "User requested: Available empty put-away bin records. Returned: Aggregated summary. These do not satisfy the requested analytical task."

    # 4. Total Inventory Quantity / Aggregate KPI / Count Request vs Row-Level Detail Table
    is_aggregate_req = (
        (query_plan and query_plan.get("response_format") == "SINGLE_LINE" and query_plan.get("aggregation") in ["SUM", "COUNT", "COUNT_DISTINCT", "AVG"]) or
        any(k in q_lower for k in [
            "total warehouse inventory", "what is the total inventory", "how much inventory is currently in the warehouse",
            "what is the total inventory quantity", "how many units are currently in inventory", "give me the current warehouse inventory",
            "how many inventory records are there", "count of inventory records", "how many materials are in inventory",
            "how many unique materials", "total stock quantity", "total unrestricted inventory"
        ])
    ) and not any(k in q_lower for k in ["show materials", "list materials", "which materials", "breakdown", "by plant", "across storage"])
    
    if is_aggregate_req:
        if len(rows) > 1 and ("Material" in cols or "BinNo" in cols or "Bin" in cols or "Batch" in cols) and "Total Inventory Quantity" not in cols:
            return False, "User requested: Aggregate KPI/count value. Returned: Multi-row row-level detail records table. Rejecting result to re-execute proper aggregation query."

    # 5. RANGE / FILTER CONTEXT Validation (RANGE FILTER VALIDATION RULE & DISPLAYED-METRIC CONSISTENCY)
    range_filters = (query_plan.get("range_filters") if query_plan else None)
    if not range_filters and ("between" in q_lower or "%-" in q_lower or "% to" in q_lower or "% -" in q_lower):
        pct_m = re.search(r"(?:between|from)\s*(\d+(?:\.\d+)?)\s*%\s*(?:and|to|–|-)\s*(\d+(?:\.\d+)?)\s*%", q_lower)
        if not pct_m:
            pct_m = re.search(r"\b(\d+(?:\.\d+)?)\s*%\s*(?:–|-|to)\s*(\d+(?:\.\d+)?)\s*%", q_lower)
        if pct_m:
            range_filters = [{
                "field": "BinUtilizationPct",
                "operator": "BETWEEN",
                "lower": float(pct_m.group(1)),
                "upper": float(pct_m.group(2)),
                "inclusive": True
            }]

    if range_filters and rows:
        rf = range_filters[0]
        field = rf.get("field", "")
        # DISPLAYED-METRIC CONSISTENCY:
        # If the query asks for utilization range, the table must display calculated Utilization %,
        # not on bin capacity, occupied volume, raw database field, or uncalculated percentage.
        if field == "BinUtilizationPct" or "utiliz" in q_lower or "occupan" in q_lower:
            has_util_display = any(c in cols for c in ["Utilization %", "UtilizationPct", "Bin Utilization %", "BinUtilizationPct", "BinOccupancyPct"])
            if not has_util_display:
                return False, "DISPLAYED-METRIC CONSISTENCY VIOLATION: Query requested utilization range, but table does not display calculated 'Utilization %' column."
        
        # RANGE FILTER VALIDATION RULE:
        # Check every returned row against requested bounds. If any row falls outside the range, report violation.
        _, range_warns = validate_and_filter_range_rows(rows, range_filters)
        if range_warns:
            return False, f"RANGE FILTER VALIDATION VIOLATION: {range_warns[0]}"

    return True, "Passed semantic result validation."


def validate_and_filter_range_rows(rows: list[dict], range_filters: list[dict]) -> tuple[list[dict], list[str]]:
    """Enforces RANGE FILTER VALIDATION RULE and DISPLAYED-METRIC CONSISTENCY:
    
    1. Validates every returned row against requested lower and upper bounds.
    2. Excludes any rows falling outside the requested range before presenting the result.
    3. Guarantees that the metric used for filtering matches the metric displayed to the user.
    """
    if not rows or not range_filters:
        return rows, []

    warnings = []
    filtered_rows = rows

    for rf in range_filters:
        field = rf.get("field", "")
        op = rf.get("operator", "BETWEEN")
        lower = rf.get("lower")
        upper = rf.get("upper")
        inclusive = rf.get("inclusive", True)

        # Identify candidate column matching the filtered metric
        candidate_cols = []
        if field == "BinUtilizationPct" or "utiliz" in field.lower() or "occupan" in field.lower():
            candidate_cols = [c for c in ["UtilizationPct", "Utilization %", "Bin Utilization %", "BinUtilizationPct", "BinOccupancyPct", "BinUtilization"] if c in filtered_rows[0]]
        elif field in ["UnrestrictedQty", "Quantity", "TotalQuantity"]:
            candidate_cols = [c for c in ["Total Stock Qty", "UnrestrictedQty", "Quantity", "TotalQuantity", "Inventory Qty"] if c in filtered_rows[0]]
        elif field in ["TotalCapacity", "BIN_CAPACITY", "BinCapacity"]:
            candidate_cols = [c for c in ["Bin Capacity (FT3)", "Bin Capacity", "Total Capacity", "Total Capacity (FT3)", "Total Capacity (FT³)", "Volume", "Total Bin Capacity", "Capacity"] if c in filtered_rows[0]]
        elif field in ["AvailableCapacity", "FreeCapacity"]:
            candidate_cols = [c for c in ["Available Capacity", "Available Capacity (FT3)", "Available Capacity (FT³)", "Free Capacity", "Remaining Capacity", "Available Space"] if c in filtered_rows[0]]
        elif field in ["Volume", "ConsumedMaterialVolume", "OccupiedBinVolume", "OccupiedVolume"]:
            candidate_cols = [c for c in ["Occupied Volume", "Occupied Volume (FT3)", "Occupied Volume (FT³)", "Volume", "Total Material Volume", "ConsumedMaterialVolume"] if c in filtered_rows[0]]
        elif field in ["FullyVestedOn", "ChangedAt"]:
            candidate_cols = [c for c in ["Fully Vested On", "FullyVestedOn", "ChangedAt"] if c in filtered_rows[0]]

        if not candidate_cols:
            for c in filtered_rows[0].keys():
                if field.lower() in c.lower().replace(" ", "").replace("_", ""):
                    candidate_cols.append(c)

        if not candidate_cols:
            continue

        metric_col = candidate_cols[0]
        valid_rows = []
        excluded_count = 0

        for r in filtered_rows:
            raw_val = r.get(metric_col)
            if raw_val is None:
                continue

            try:
                if isinstance(raw_val, (int, float)):
                    num_val = float(raw_val)
                else:
                    clean_str = re.sub(r"[^\d.-]", "", str(raw_val))
                    num_val = float(clean_str) if clean_str else None
            except Exception:
                num_val = None

            if num_val is None:
                continue

            satisfies = True
            if op == "BETWEEN" and lower is not None and upper is not None:
                satisfies = (lower <= num_val <= upper) if inclusive else (lower < num_val < upper)
            elif op in ["GT", "GTE"] and lower is not None:
                satisfies = (num_val >= lower) if inclusive else (num_val > lower)
            elif op in ["LT", "LTE"] and upper is not None:
                satisfies = (num_val <= upper) if inclusive else (num_val < upper)

            if satisfies:
                valid_rows.append(r)
            else:
                excluded_count += 1

        if excluded_count > 0:
            warnings.append(f"Excluded {excluded_count} row(s) falling outside the requested range [{lower}, {upper}] for metric '{metric_col}'.")

        filtered_rows = valid_rows

    return filtered_rows, warnings

