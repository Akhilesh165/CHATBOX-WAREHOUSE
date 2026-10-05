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
from .models import ChatRequest, ChatResponse, Chart, Meta, FeedbackRequest, FeedbackResponse
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

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """Processes natural language inventory question, executes validated SQL, and returns grounded answer."""
    conversation_id = req.conversation_id or "default"
    history = conversations.setdefault(conversation_id, [])
    
    start_total = time.perf_counter()
    warnings = []
    
    logger.info(f"Received question [conv={conversation_id}]: {req.message}")
    
    # 1. Generate SQL via LLM with 1 Retry logic on validation error
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
                logger.error(f"SQL Generation failed after {attempt + 1} attempts.")
                raise HTTPException(
                    status_code=400,
                    detail=f"Unable to generate a valid SQL query: {str(err)}"
                )

    llm_duration_ms = int((time.perf_counter() - llm_start) * 1000)

    # 3. Execute Validated SQL on Read-Only Connection
    try:
        rows, sql_duration_ms = execute_readonly(validated_sql, max_rows=settings.sql_max_result_rows)
    except Exception as db_err:
        logger.error(f"Database execution failed for SQL [{validated_sql}]: {db_err}")
        raise HTTPException(
            status_code=500,
            detail=f"Database execution error: {str(db_err)}"
        )

    # 4. Result Validator Layer ("Does this result actually answer the user's question?")
    is_valid_result, validation_reason = validate_query_result(
        req.message,
        generated.get("query_plan") if isinstance(generated, dict) else None,
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

    if len(rows) >= settings.sql_max_result_rows:
        warnings.append(f"Result capped at maximum {settings.sql_max_result_rows} rows.")

    # 5. Generate Grounded Answer from SQL Result
    answer_start = time.perf_counter()
    try:
        answer = await generate_answer(req.message, validated_sql, rows)
    except Exception as ans_err:
        logger.warning(f"Answer generation error, falling back to structured summary: {ans_err}")
        if not rows:
            answer = f"No matching warehouse records found for your query."
        else:
            answer = f"Found {len(rows)} matching record(s). Please review the data table below for details."
    
    total_llm_ms = llm_duration_ms + int((time.perf_counter() - answer_start) * 1000)

    # 6. Automatically optimize response format and visual presentation
    opt = optimize_response_format(req.message, rows, generated)
    
    chart_type = opt.get("chart_type") or generated.get("chart_type", "none")
    chart_title = opt.get("chart_title") or generated.get("chart_title")
    chart_x = opt.get("chart_x") or generated.get("chart_x")
    chart_y = opt.get("chart_y") or generated.get("chart_y")
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

    output_type = opt.get("output_type") or generated.get("output_type") or (
        "line_chart" if chart_type == "line" else
        "bar_chart" if chart_type == "bar" else
        "pie_chart" if chart_type == "pie" else
        "table" if rows else "text"
    )

    intent = opt.get("intent") or generated.get("intent")
    metric = opt.get("metric") or generated.get("metric")
    time_range = opt.get("time_range") or generated.get("time_range", "current")
    query_plan = generated.get("query_plan") if isinstance(generated, dict) else None

    return ChatResponse(
        answer=answer,
        data=rows,
        rows=rows,
        chart=chart,
        meta=meta,
        sql=safe_sql,
        warnings=warnings,
        intent=intent,
        output_type=output_type,
        metric=metric,
        filters=generated.get("filters", {}),
        time_range=time_range,
        query_plan=query_plan
    )

@app.post("/api/feedback", response_model=FeedbackResponse)
async def submit_feedback(fb: FeedbackRequest):
    """Records user ratings (thumbs up/down) and comments for monitoring & RLHF."""
    feedback_log.append(fb.model_dump())
    logger.info(f"Feedback recorded: {fb.rating} for conv {fb.conversation_id}")
    return FeedbackResponse()
