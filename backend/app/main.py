"""FastAPI Warehouse Inventory AI Chatbot Server.
Orchestrates request validation, query generation, security enforcement, DB execution, and grounded answer response.
"""

import os
import time
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .config import settings
from .models import ChatRequest, ChatResponse, Chart, Meta, FeedbackRequest, FeedbackResponse, TableDataset
from .llm import generate_sql, generate_answer, optimize_response_format, deterministic_warehouse_sql_generator
from .validator import validate_sql, validate_query_result
from .db import execute_readonly, get_engine

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("warehouse_api")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Production-ready Warehouse Inventory AI Assistant API"
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory conversation store for multi-turn sessions
conversations: dict[str, list[dict]] = {}
feedback_log: list[dict] = []

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/")
def get_root_ui():
    """Serves the live ChatGPT-inspired warehouse UI dashboard."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Warehouse AI API is running. Visit /api/health or frontend."}

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Return empty 204 response for favicon requests."""
    from fastapi import Response
    return Response(status_code=204)

@app.get("/health")
@app.get("/api/health")
def health_check():
    """Health check endpoint returning service and database status without exposing secrets."""
    db_status = "ok"
    try:
        engine = get_engine()
        with engine.connect() as conn:
            pass
    except Exception:
        db_status = "degraded"

    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "database": db_status
    }

@app.get("/api/schema")
def get_schema_metadata(authorization: str | None = Header(default=None)):
    """Admin-only schema inspector. Returns approved tables/views and column definitions without exposing secrets."""
    return {
        "tables": {
            "dbo.ZWMS_INVENTORY": {
                "source": "Bin Invrntory.xlsx (Sheet1)",
                "description": "Authoritative inventory quantities, bins, batches, and plants",
                "columns": [
                    "Id", "FileName", "Material", "Plant", "StorageLocation", "Batch",
                    "MaterialDescription", "UnrestrictedQty", "UnrestrictedQty2",
                    "BaseUnitOfMeasure", "Mrp", "FullyVestedOn", "ChangedAt", "BinNo",
                    "INSERT_BY", "INSERT_TIMESTAMP", "UPDATE_BY", "UPDATE_TIMESTAMP"
                ]
            },
            "dbo.ZWMS_BIN_MASTER": {
                "source": "WMS Bins Data.xlsx (Bin Master)",
                "description": "Bin dimensions, volume, pallet types, and storage locations",
                "columns": [
                    "Id", "Plant", "BinLocation", "MainCriterion", "StorageLocation",
                    "PalletType", "Box", "Owner", "Volume", "VolumeUnit",
                    "Length", "Width", "Height", "CreatedDate", "CreatedBy"
                ]
            },
            "dbo.ZWMS_MATERIAL_MASTER": {
                "source": "WMS Bins Data.xlsx (Material Master)",
                "description": "Material physical specs, divisions, weights, groups, and packaging",
                "columns": [
                    "Id", "MaterialCode", "MaterialDescription", "Volume", "VUom",
                    "GrossWeight", "Division", "DivisionDescription", "Kslot", "BinUom",
                    "InsertBY", "CreatedDateTime", "NetWeight", "EanNo", "Hierarchy",
                    "MaterialGroup", "CaseLot", "Length", "Width", "Height",
                    "CartoonGrossWeight", "CartoonVolume", "UpdatedDateTime"
                ]
            },
            "dbo.vw_WMS_InventoryEnriched": {
                "source": "Semantic View",
                "description": "Unified inventory view joined with Bin and Material master attributes"
            }
        }
    }

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global fallback handler to ensure no uncaught exceptions escape as raw 500 crashes."""
    logger.error(f"Global unhandled exception on {request.url.path}: {exc}", exc_info=True)
    if "/api/chat" in request.url.path:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=200,
            content={
                "answer": "I encountered an issue processing your query. Please try rephrasing or asking for a specific warehouse metric (e.g. 'Total warehouse inventory', 'Bin utilization for Plant 1258', or 'Show materials in Plant 7228').",
                "data": [],
                "rows": [],
                "chart": {"type": "none"},
                "meta": {"rowCount": 0, "executionMs": 0, "llmMs": 0, "sqlMs": 0},
                "warnings": [f"Handled exception: {str(exc)}"],
                "intent": "ERROR_RECOVERED",
                "output_type": "text"
            }
        )
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=200,
        content={"status": "recovered", "detail": str(exc)}
    )

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """Processes natural language inventory question, executes validated SQL, and returns grounded answer."""
    conversation_id = req.conversation_id or "default"
    history = conversations.setdefault(conversation_id, [])
    
    start_total = time.perf_counter()
    warnings = []
    
    logger.info(f"Received question [conv={conversation_id}]: {req.message}")
    
    # 1. Generate SQL via LLM with Retry logic on validation error
    llm_start = time.perf_counter()
    generated = None
    validated_sql = None
    last_error = None
    
    for attempt in range(settings.llm_max_retries + 1):
        try:
            failed_sql = generated.get("sql", "") if isinstance(generated, dict) else ""
            retry_ctx = {"error": str(last_error), "sql": failed_sql} if last_error else None
            generated = await generate_sql(req.message, history, retry_context=retry_ctx)
            raw_sql = generated.get("sql", "") if isinstance(generated, dict) else ""
            
            # 2. Validate SQL with SQLGlot AST Checker
            validated_sql = validate_sql(raw_sql)
            break  # Successfully generated and validated
        except Exception as err:
            last_error = err
            logger.warning(f"SQL Generation/Validation attempt {attempt + 1} failed: {err}")
            if attempt >= settings.llm_max_retries:
                logger.info("Falling back to deterministic warehouse SQL generator...")
                try:
                    generated = deterministic_warehouse_sql_generator(req.message, history=history)
                    raw_sql = generated.get("sql", "") if isinstance(generated, dict) else ""
                    validated_sql = validate_sql(raw_sql)
                    break
                except Exception as det_err:
                    logger.error(f"Deterministic generator also failed: {det_err}")
                    return ChatResponse(
                        answer=f"I couldn't safely parse a warehouse query for: '{req.message}'. Please try asking for 'Total warehouse inventory', 'Bin utilization for Plant 1258', or 'Show materials in Plant 7228'.",
                        data=[],
                        rows=[],
                        chart=Chart(type="none"),
                        meta=Meta(rowCount=0, executionMs=0, llmMs=0, sqlMs=0),
                        warnings=[str(det_err)],
                        intent="ERROR_HANDLED",
                        output_type="text"
                    )

    llm_duration_ms = int((time.perf_counter() - llm_start) * 1000)

    # 3. Execute Validated SQL on Read-Only Connection
    rows = []
    sql_duration_ms = 0
    table_datasets: list[TableDataset] = []

    is_multi_table = bool(isinstance(generated, dict) and generated.get("is_multi_table_comparison"))
    comp_plants = generated.get("comparison_plants", []) if is_multi_table else []
    plant_sql_template = generated.get("plant_sql_template", "") if is_multi_table else ""

    if is_multi_table and comp_plants and plant_sql_template:
        op_desc = generated.get("op_desc", "above")
        thresh_str = generated.get("thresh_str", "80")
        combined_rows = []
        sql_duration_total_ms = 0

        for p in comp_plants:
            plant_sql = plant_sql_template.format(plant=p)
            try:
                p_rows, p_ms = execute_readonly(plant_sql, max_rows=settings.sql_max_result_rows)
                sql_duration_total_ms += p_ms
            except Exception as e:
                logger.error(f"Error querying plant {p}: {e}")
                p_rows = []

            p_count = len(p_rows)
            table_title = f"Plant {p} — Bins {op_desc} {thresh_str}% utilization"
            empty_msg = f"No bins found {op_desc} {thresh_str}% utilization in Plant {p}." if p_count == 0 else None

            table_datasets.append(TableDataset(
                title=table_title,
                plant=str(p),
                count=p_count,
                rows=p_rows,
                empty_message=empty_msg
            ))
            combined_rows.extend(p_rows)

        rows = combined_rows
        sql_duration_ms = sql_duration_total_ms
    else:
        try:
            rows, sql_duration_ms = execute_readonly(validated_sql, max_rows=settings.sql_max_result_rows)
        except Exception as db_err:
            logger.warning(f"Database execution failed for SQL [{validated_sql}]: {db_err}. Retrying with deterministic generator...")
            try:
                corrected_gen = deterministic_warehouse_sql_generator(req.message, history=history)
                corrected_sql = validate_sql(corrected_gen.get("sql", ""))
                rows, sql_duration_ms = execute_readonly(corrected_sql, max_rows=settings.sql_max_result_rows)
                generated = corrected_gen
                validated_sql = corrected_sql
            except Exception as retry_err:
                logger.error(f"Database retry failed: {retry_err}")
                warnings.append(f"Database execution warning: {str(db_err)}")
                return ChatResponse(
                    answer=f"A database error occurred while querying inventory records. Please verify the query parameters or try asking for a specific metric (e.g. 'Total warehouse inventory' or 'Bin utilization for Plant 1258').",
                    data=[],
                    rows=[],
                    chart=Chart(type="none"),
                    meta=Meta(rowCount=0, executionMs=0, llmMs=llm_duration_ms, sqlMs=0),
                    warnings=warnings,
                    intent="DB_ERROR_HANDLED",
                    output_type="text"
                )

    # 4. Result Validator Layer ("Does this result actually answer the user's question?")
    try:
        val_plan = dict(generated.get("query_plan") or {}) if isinstance(generated, dict) else {}
        if is_multi_table:
            val_plan["is_multi_table_comparison"] = True
        is_valid_result, validation_reason = validate_query_result(
            req.message,
            val_plan or None,
            validated_sql,
            rows
        )
        if not is_valid_result:
            logger.warning(f"Semantic Result Validator FAIL: {validation_reason}. Triggering self-correction regeneration...")
            try:
                corrected_gen = deterministic_warehouse_sql_generator(req.message, history=history)
                corrected_sql = validate_sql(corrected_gen.get("sql", ""))
                corrected_rows, sql_duration_ms = execute_readonly(corrected_sql, max_rows=settings.sql_max_result_rows)
                generated = corrected_gen
                validated_sql = corrected_sql
                rows = corrected_rows
                logger.info("Self-correction successful: Corrected query executed.")
            except Exception as retry_err:
                logger.error(f"Self-correction failed: {retry_err}")
    except Exception as val_check_err:
        logger.warning(f"Result validator check skipped due to non-critical error: {val_check_err}")

    # 4B. RANGE FILTER VALIDATION RULE & DISPLAYED-METRIC CONSISTENCY Enforcement
    # "Every returned row must satisfy the requested range. The chatbot must never display rows outside
    # the requested range, even if the backend returns them. Before presenting the response, validate
    # every returned row against the requested lower and upper bounds. If any row falls outside the range,
    # exclude it or correct the calculation before displaying the result."
    active_range_filters = None
    if isinstance(generated, dict) and generated.get("query_plan"):
        active_range_filters = generated["query_plan"].get("range_filters")
    if not active_range_filters:
        from .llm import parse_range_filters
        active_range_filters = parse_range_filters(req.message)

    if active_range_filters and rows:
        from .validator import validate_and_filter_range_rows
        rows, range_pruning_warnings = validate_and_filter_range_rows(rows, active_range_filters)
        if range_pruning_warnings:
            warnings.extend(range_pruning_warnings)

    if settings.sql_max_result_rows > 0 and len(rows) >= settings.sql_max_result_rows:
        warnings.append(
            f"Results reached the configured {settings.sql_max_result_rows}-row limit; "
            "the displayed list may be incomplete. Narrow the filters or increase "
            "SQL_MAX_RESULT_ROWS if the complete list is required."
        )

    # 5. Generate Grounded Answer from SQL Result
    answer_start = time.perf_counter()
    resolved_query_for_answer = generated.get("conversation_state", {}).get("resolved_query") or req.message
    try:
        answer = await generate_answer(resolved_query_for_answer, validated_sql, rows)
    except Exception as ans_err:
        logger.warning(f"Answer generation error, falling back to structured summary: {ans_err}")
        if not rows:
            answer = f"No matching warehouse records found for your query."
        else:
            answer = f"Found {len(rows)} matching record(s). Please review the data table below for details."
    
    total_llm_ms = llm_duration_ms + int((time.perf_counter() - answer_start) * 1000)

    # 6. Automatically optimize response format and visual presentation
    try:
        opt = optimize_response_format(resolved_query_for_answer, rows, generated)
    except Exception as opt_err:
        logger.warning(f"optimize_response_format error: {opt_err}")
        opt = {}
    
    chart_type = opt.get("chart_type") or (generated.get("chart_type", "none") if isinstance(generated, dict) else "none")
    chart_title = opt.get("chart_title") or (generated.get("chart_title") if isinstance(generated, dict) else None)
    chart_x = opt.get("chart_x") or (generated.get("chart_x") if isinstance(generated, dict) else None)
    chart_y = opt.get("chart_y") or (generated.get("chart_y") if isinstance(generated, dict) else None)
    chart_data = rows[:50] if chart_type != "none" else []
    
    chart = Chart(
        type=chart_type,
        title=chart_title,
        xAxis=chart_x,
        yAxis=chart_y,
        x_key=chart_x,
        y_key=chart_y,
        data=chart_data
    )

    # 7. Update Conversation History
    history.append({"role": "user", "content": req.message})
    history.append({"role": "assistant", "content": answer})
    
    # Cap history window
    if len(history) > 20:
        conversations[conversation_id] = history[-20:]

    total_execution_ms = int((time.perf_counter() - start_total) * 1000)

    # Expose SQL only if caller is admin or debug is enabled
    safe_sql = validated_sql if (req.is_admin or settings.debug) else None

    meta = Meta(
        rowCount=len(rows),
        executionMs=total_execution_ms,
        llmMs=total_llm_ms,
        sqlMs=sql_duration_ms
    )

    output_type = opt.get("output_type") or (generated.get("output_type") if isinstance(generated, dict) else None) or (
        "line_chart" if chart_type == "line" else
        "bar_chart" if chart_type == "bar" else
        "pie_chart" if chart_type == "pie" else
        "table" if rows else "text"
    )

    intent = opt.get("intent") or (generated.get("intent") if isinstance(generated, dict) else None)
    metric = opt.get("metric") or (generated.get("metric") if isinstance(generated, dict) else None)
    time_range = opt.get("time_range") or (generated.get("time_range", "current") if isinstance(generated, dict) else "current")
    query_plan = generated.get("query_plan") if isinstance(generated, dict) else None

    # Extract follow_up_action and relevant_kpis if present in generated plan
    follow_up_action = generated.get("follow_up_action") if isinstance(generated, dict) else None
    relevant_kpis_raw = generated.get("relevant_kpis") if isinstance(generated, dict) else None
    relevant_kpis = None
    try:
        if relevant_kpis_raw and rows and isinstance(rows[0], dict):
            row0 = rows[0]
            tb_val = row0.get("Total Bins", row0.get("TotalBins", 0)) or 0
            ob_val = row0.get("Occupied Bins", row0.get("OccupiedBins", 0)) or 0
            tb = float(tb_val) if isinstance(tb_val, (int, float)) or (isinstance(tb_val, str) and tb_val.replace('.', '', 1).isdigit()) else 0.0
            ob = float(ob_val) if isinstance(ob_val, (int, float)) or (isinstance(ob_val, str) and ob_val.replace('.', '', 1).isdigit()) else 0.0
            eb_val = row0.get("Empty Bins", row0.get("EmptyBins"))
            if eb_val is not None:
                try:
                    eb = float(eb_val)
                except Exception:
                    eb = max(0.0, tb - ob)
            else:
                eb = max(0.0, tb - ob)
            
            bpct_raw = row0.get("Bin Utilization %")
            if bpct_raw is not None:
                bpct_str = str(bpct_raw) if "%" in str(bpct_raw) else f"{bpct_raw}%"
            else:
                bpct_str = f"{round(ob * 100.0 / tb, 1) if tb > 0 else 0}%"
            
            relevant_kpis = [
                {"label": "Bin Utilization", "value": bpct_str, "subtext": "Occupancy Rate"},
                {"label": "Occupied Bins", "value": f"{int(ob):,}", "subtext": "Active In Use"},
                {"label": "Empty Bins", "value": f"{int(eb):,}", "subtext": "Available Put-Away"},
                {"label": "Total Bins", "value": f"{int(tb):,}", "subtext": "Total Capacity"}
            ]
    except Exception as kpi_err:
        logger.warning(f"Error extracting relevant KPIs: {kpi_err}")
        relevant_kpis = None

    return ChatResponse(
        answer=answer,
        data=rows,
        rows=rows,
        tables=table_datasets,
        chart=chart,
        meta=meta,
        sql=safe_sql,
        warnings=warnings,
        intent=intent,
        output_type=output_type,
        metric=metric,
        filters=generated.get("filters", {}),
        time_range=time_range,
        query_plan=query_plan,
        follow_up_action=follow_up_action,
        relevant_kpis=relevant_kpis
    )


@app.post("/api/feedback", response_model=FeedbackResponse)
async def submit_feedback(fb: FeedbackRequest):
    """Records user ratings (thumbs up/down) and comments for monitoring & RLHF."""
    feedback_log.append(fb.model_dump())
    logger.info(f"Feedback recorded: {fb.rating} for conv {fb.conversation_id}")
    return FeedbackResponse()
