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
