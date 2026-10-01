"""Database Connection and Read-Only Execution Engine.
Handles connection pooling, dialect transpilation (T-SQL to SQLite when in local dev), query timeouts, and row limiting.
"""

import time
import os
import sqlglot
from decimal import Decimal
from datetime import datetime, date
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from .config import settings

_engine: Engine | None = None

def get_engine() -> Engine:
    """Initialize and retrieve SQLAlchemy engine singleton."""
    global _engine
    if _engine is not None:
        return _engine

    if settings.database_url:
        _engine = create_engine(
            settings.database_url,
            pool_size=settings.sql_pool_size,
            max_overflow=settings.sql_max_overflow,
            pool_pre_ping=True,
            pool_recycle=1800
        )
    elif os.path.exists("warehouse.db") and (not settings.sql_password or settings.sql_password == "ChangeThisStrongPassword123!"):
        # Development SQLite fallback
        _engine = create_engine("sqlite:///warehouse.db")
    else:
        # SQL Server ODBC connection
        conn_str = (
            f"DRIVER={{{settings.sql_driver}}};"
            f"SERVER={settings.sql_server};"
            f"DATABASE={settings.sql_database};"
            f"UID={settings.sql_username};"
            f"PWD={settings.sql_password};"
            "TrustServerCertificate=yes;"
        )
        _engine = create_engine(
            "mssql+pyodbc:///?odbc_connect=" + quote_plus(conn_str),
            pool_size=settings.sql_pool_size,
            max_overflow=settings.sql_max_overflow,
            pool_pre_ping=True,
            pool_recycle=1800,
            fast_executemany=True
        )
    return _engine

def serialize_value(val):
    """Serialize database values into JSON-compatible formats."""
    if isinstance(val, (Decimal, float)):
        return float(val) if val is not None else 0.0
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    return val

def execute_readonly(sql: str, max_rows: int = 1000) -> tuple[list[dict], int]:
    """Execute a read-only SQL query and return normalized row dictionaries and execution time in ms.
    
    Returns (rows, execution_duration_ms)
    """
    engine = get_engine()
    start_time = time.perf_counter()
    
    executable_sql = sql
    
    # If executing against SQLite, transpile T-SQL constructs like TOP N to LIMIT N and remove dbo. prefix
    if engine.url.get_backend_name() == "sqlite":
        try:
            transpiled = sqlglot.transpile(sql, read="tsql", write="sqlite")
            if transpiled and transpiled[0]:
                executable_sql = transpiled[0].replace("dbo.", "")
        except Exception:
            # Fallback simple replacement if transpile fails
            executable_sql = sql.replace("dbo.", "")

    with engine.connect() as conn:
        try:
            conn.execution_options(timeout=settings.sql_query_timeout_sec)
        except Exception:
            pass

        result = conn.execute(text(executable_sql))
        
        rows = []
        for i, row in enumerate(result):
            if i >= max_rows:
                break
            row_dict = {col: serialize_value(val) for col, val in row._mapping.items()}
            rows.append(row_dict)

    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
    return rows, elapsed_ms
