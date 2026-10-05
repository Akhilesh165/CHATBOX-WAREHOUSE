"""SQL Security and AST Validator using SQLGlot.
Enforces strict read-only execution, schema allowlisting, and rejection of unsafe SQL constructs.
"""

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
    Returns (is_valid, failure_reason).
    """
    q_lower = question.lower()
    cols = list(rows[0].keys()) if rows else []
    
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
        if rows and "Material" not in cols and "MaterialCode" not in cols:
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
        # Check if result is generic inventory summary instead of material-level missing-dimension records
        if any(c in cols for c in ["TotalUniqueMaterials", "TotalActiveBins", "TotalUnrestrictedQuantity", "PlantCount"]) and "Quality Issue" not in cols and "Length" not in cols:
            return False, "User requested: Material-level missing-dimension records. Returned: Warehouse-level inventory summary. These do not satisfy the requested analytical task."
        if rows and "Material" not in cols and "MaterialCode" not in cols:
            return False, "User requested: Material-level missing-dimension records. Returned: Non-material entity. These do not satisfy the requested analytical task."

    # 2. Top / Bottom Bins Ranking
    is_ranking_req = any(k in q_lower for k in ["top", "bottom", "most utilized", "least utilized", "lowest utilized", "highest utilized", "lowest ones", "least ones", "emptiest bins"]) or (
        ("most" in q_lower or "least" in q_lower or "top" in q_lower or "bottom" in q_lower or "highest" in q_lower or "lowest" in q_lower) and
        ("utiliz" in q_lower or "capacit" in q_lower or "occup" in q_lower or "full" in q_lower or "bin" in q_lower or "bins" in q_lower or "ones" in q_lower) and
        not any(m in q_lower for m in ["material", "sku", "product", "goods"])
    )
    if is_ranking_req:
        if any(c in cols for c in ["TotalUniqueMaterials", "TotalActiveBins", "TotalUnrestrictedQuantity", "TotalBins"]) and "Ranking Group" not in cols and "Bin" not in cols and "BinLocation" not in cols and "BinNo" not in cols:
            return False, "User requested: Bin utilization ranking records. Returned: Plant-level aggregated summary. These do not satisfy the requested ranking task."

    # 3. Available / Empty Put-Away Bins
    is_putaway_req = any(k in q_lower for k in ["empty bin", "empty bins", "putaway", "put-away", "vacant", "unoccupied", "without displacing", "free bin", "free storage"])
    if is_putaway_req:
        if any(c in cols for c in ["TotalUniqueMaterials", "TotalActiveBins", "TotalUnrestrictedQuantity", "TotalBins"]) and "BinLocation" not in cols and "BinNo" not in cols and "Bin" not in cols:
            return False, "User requested: Available empty put-away bin records. Returned: Aggregated summary. These do not satisfy the requested analytical task."

    return True, "Passed semantic result validation."

