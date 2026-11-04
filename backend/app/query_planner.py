"""
Structured Query Understanding, Intent Prioritization, Validation, and Diagnostics Layer.
========================================================================================
Implements:
1. Structured Query Plan extraction (intent, entity, plants, bins, materials, metric, operation, ranking, limit, range, modifiers).
2. Separation of business intent from response modifiers (detail_mode, summary_mode, visualization_mode).
3. Explicit intent/entity priority (business subject determined first).
4. Pre-execution Query-Plan Validation & sanitization.
5. Post-execution Response Validation & mismatch re-routing.
6. Context preservation across multi-turn follow-ups.
7. Ambiguity detection & concise clarification handling.
8. Developer diagnostics pipeline logging.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("warehouse_api.planner")

# Canonical Plant IDs
VALID_PLANTS = {"1258", "1266", "1268", "7228"}

# -----------------------------------------------------------------------------
# 1. HELPER EXTRACTION UTILITIES
# -----------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Normalizes query whitespace, common typos, and casing."""
    if not text:
        return ""
    q = text.strip()
    # Normalize plant references: e.g. plant7228 -> plant 7228, Plant-7228 -> Plant 7228
    q = re.sub(r"\bplants?[-_:]?(\d{4,5})\b", r"plant \1", q, flags=re.IGNORECASE)
    # Common warehouse typo corrections
    typos = {
        r"\butilis\w*\b": "utilization",
        r"\bmatrial\w*\b": "material",
        r"\binvetory\b": "inventory",
        r"\binvntory\b": "inventory",
        r"\bcapacit\w*\b": "capacity",
        r"\bwharehouse\b": "warehouse",
        r"\bcompair\b": "compare",
        r"\bcomapare\b": "compare",
    }
    for pat, repl in typos.items():
        q = re.sub(pat, repl, q, flags=re.IGNORECASE)
    return q


def extract_plants(text: str) -> List[str]:
    """Extracts all explicit valid plant codes from text in order."""
    text_lower = text.lower()
    found: List[str] = []
    # Pattern 1: plant 7228, plants 7228 and 1258, plant #7228
    for m in re.finditer(r"\bplants?\b\s*(?:#|:|-)?\s*(\d{4,5})((?:\s*(?:,|and|&)\s*(?:plant\s*)?\d{4,5})*)", text_lower):
        found.append(m.group(1))
        found.extend(re.findall(r"(?:,|and|&)\s*(?:plant\s*)?(\d{4,5})", m.group(2)))
    # Pattern 2: standalone 4-digit valid plant IDs
    for p in ["7228", "1258", "1268", "1266"]:
        if re.search(r"\b" + p + r"\b", text_lower) and p not in found:
            found.append(p)
    return list(dict.fromkeys(p for p in found if p in VALID_PLANTS))


def extract_specific_bins(text: str) -> List[str]:
    """Extracts bin coordinates from query."""
    matches = re.findall(r"\b([A-Z0-9]{8,12})\b", text.upper())
    valid_bins = [b for b in matches if not b.isdigit() and b not in ["INVENTORY", "WAREHOUSE", "UTILIZATION", "MATERIAL", "CAPACITY"]]
    # Also check B-101 style or S105290412
    if not valid_bins:
        matches2 = re.findall(r"\b([A-Z]\d{2,4}[A-Z0-9]*)\b", text.upper())
        valid_bins = [b for b in matches2 if b not in ["B2B", "RAW", "FGS", "PC", "EA", "NOS"]]
    return list(dict.fromkeys(valid_bins))


def extract_specific_materials(text: str) -> List[str]:
    """Extracts material code if explicitly specified."""
    m = re.search(r"\b(?:material|sku|item|code)\s*[:#-]?\s*([a-zA-Z0-9_-]{5,20})\b", text, re.IGNORECASE)
    if m:
        val = m.group(1).upper()
        if val not in ["DIVISION", "GROUP", "TYPE", "DESCRIPTION", "NAME", "MASTER", "TABLE", "PLANT", "STOCK", "QUANTITY", "INVENTORY"]:
            return [val]
    # Check for direct SKU pattern like BGFGBKNS0031
    skus = re.findall(r"\b([A-Z]{4,8}[0-9]{4,8})\b", text.upper())
    return [s for s in skus if s not in ["WAREHOUSE", "INVENTORY"]]


def extract_limit(text: str) -> Optional[int]:
    """Extracts row limit from words like 'top 10', 'first 5', 'lowest 3'."""
    m = re.search(r"\b(?:top|first|limit|lowest|bottom|highest|last|rank)\s*(\d{1,3})\b", text.lower())
    if m:
        try:
            val = int(m.group(1))
            return val if 1 <= val <= 1000 else 10
        except Exception:
            return None
    return None


def extract_range_filter(text: str) -> Optional[Dict[str, Any]]:
    """Extracts range filters e.g. between 10 and 20 ft3, above 80%."""
    q_lower = text.lower()
    # Percent utilization range
    m_pct = re.search(r"\b(?:above|over|greater than|>)\s*(\d{1,3})\s*%", q_lower)
    if m_pct:
        return {"field": "utilization", "operator": "GT", "threshold": float(m_pct.group(1))}
    m_pct_lt = re.search(r"\b(?:below|under|less than|<)\s*(\d{1,3})\s*%", q_lower)
    if m_pct_lt:
        return {"field": "utilization", "operator": "LT", "threshold": float(m_pct_lt.group(1))}
    # Capacity range
    m_cap_btw = re.search(r"\b(?:between)\s*(\d+(?:\.\d+)?)\s*(?:and|to|-)\s*(\d+(?:\.\d+)?)\b", q_lower)
    if m_cap_btw and any(w in q_lower for w in ["capacity", "volume", "ft3", "cubic"]):
        return {
            "field": "capacity",
            "operator": "BETWEEN",
            "lower": float(m_cap_btw.group(1)),
            "upper": float(m_cap_btw.group(2))
        }
    return None


# -----------------------------------------------------------------------------
# 2. BUSINESS INTENT & SUBJECT RECOGNITION (SUBJECT FIRST)
# -----------------------------------------------------------------------------

def is_explicit_inventory_intent(q: str) -> bool:
    """Determines if the business subject is INVENTORY (materials, stock, quantity, SKU).
    
    Intent Priority: Subject First.
    Returns True if user asks for inventory/stock/materials and does NOT ask for bin utilization.
    """
    if not q:
        return False
    q_low = q.lower().strip()

    # Explicit bin utilization keywords override
    has_explicit_bin_util = any(re.search(r"\b" + re.escape(w) + r"\b", q_low) for w in [
        "bin utilization", "utilization of bin", "utilization of bins", "utilized bin",
        "utilized bins", "bin capacity utilization", "utilization percentage",
        "most utilized bins", "least utilized bins", "highest utilized bins", "lowest utilized bins",
        "most utilized bin", "least utilized bin", "highest utilized bin", "lowest utilized bin"
    ]) or ("utiliz" in q_low and any(b in q_low for b in ["bin", "bins"]))
    if has_explicit_bin_util:
        return False

    # Explicit inventory signals
    has_inv = any(re.search(r"\b" + re.escape(w) + r"\b", q_low) for w in [
        "inventory", "stock", "material", "materials", "sku", "skus", "items", "item",
        "material quantity", "stock quantity", "inventory quantity", "inventory details",
        "inventory detail", "material inventory", "inventory report", "inventory summary",
        "available materials", "materials available", "materials present", "materials stored",
        "stock in plant", "inventory of plant", "inventory in plant"
    ])
    return bool(has_inv)


def is_explicit_bin_utilization_intent(q: str) -> bool:
    """Determines if the business subject is BIN UTILIZATION."""
    if not q:
        return False
    q_low = q.lower().strip()
    return any(re.search(r"\b" + re.escape(w) + r"\b", q_low) for w in [
        "bin utilization", "utilization of bins", "utilization of bin", "utilized bins",
        "utilized bin", "bin capacity utilization", "utilization percentage", "utilization percent",
        "most utilized bins", "least utilized bins", "highest utilized bins", "lowest utilized bins",
        "highest bin utilization", "lowest bin utilization", "bin occupancy", "bin fill rate",
        "how full are the bins", "bin fullness"
    ]) or ("utiliz" in q_low and any(b in q_low for b in ["bin", "bins"]))


def is_explicit_capacity_intent(q: str) -> bool:
    """Determines if the business subject is CAPACITY / AVAILABLE CAPACITY."""
    if not q:
        return False
    q_low = q.lower().strip()
    if is_explicit_bin_utilization_intent(q_low) or is_explicit_inventory_intent(q_low):
        return False
    return any(re.search(r"\b" + re.escape(w) + r"\b", q_low) for w in [
        "available capacity", "remaining capacity", "free capacity", "unused capacity",
        "capacity range", "total capacity", "bin volume capacity", "free space"
    ]) or ("capacity" in q_low and not any(u in q_low for u in ["utiliz", "occupan"]))


def is_empty_bins_intent(q: str) -> bool:
    """Determines if query asks for empty/vacant bins or put-away."""
    if not q:
        return False
    q_low = q.lower().strip()
    return any(re.search(r"\b" + re.escape(w) + r"\b", q_low) for w in [
        "empty bin", "empty bins", "vacant bin", "vacant bins", "free bin", "free bins",
        "unoccupied bin", "unoccupied bins", "putaway", "put-away", "ready to receive",
        "where can i put", "where can i store incoming", "place incoming stock"
    ])


def is_occupied_bins_intent(q: str) -> bool:
    """Determines if query asks for occupied bins count."""
    if not q:
        return False
    q_low = q.lower().strip()
    return any(re.search(r"\b" + re.escape(w) + r"\b", q_low) for w in [
        "occupied bin", "occupied bins", "bins in use", "active bins", "occupied locations"
    ]) and not is_empty_bins_intent(q_low)


# -----------------------------------------------------------------------------
# 3. RESPONSE MODIFIERS EXTRACTION (SEPARATED FROM INTENT)
# -----------------------------------------------------------------------------

def extract_response_modifiers(q: str) -> Dict[str, bool]:
    """Separates response modifiers from business intent.
    
    Words like 'detailed', 'summary', 'graph' modify response mode only.
    They must NEVER independently change the business intent.
    """
    q_low = q.lower().strip()
    
    detail_mode = any(re.search(r"\b" + re.escape(w) + r"\b", q_low) for w in [
        "detail", "detailed", "in detail", "full details", "full detail",
        "detailed report", "break down", "breakdown", "elaborate", "deep dive",
        "detailed breakdown", "itemized", "granular", "explain in detail",
        "show details", "give details", "show all details"
    ])

    summary_mode = any(re.search(r"\b" + re.escape(w) + r"\b", q_low) for w in [
        "summary", "summarize", "overview", "brief", "high level", "in short", "concise"
    ])

    visualization_mode = any(re.search(r"\b" + re.escape(w) + r"\b", q_low) for w in [
        "graph", "chart", "plot", "visualize", "visualisation", "graphical",
        "bar chart", "line chart", "pie chart", "with graph", "with chart"
    ])

    return {
        "detail_mode": bool(detail_mode),
        "summary_mode": bool(summary_mode),
        "visualization_mode": bool(visualization_mode)
    }


# -----------------------------------------------------------------------------
# 4. AMBIGUITY DETECTION (REQUIREMENT 7)
# -----------------------------------------------------------------------------

def detect_ambiguity(normalized_query: str, plants: List[str]) -> Tuple[bool, Optional[str]]:
    """Detects whether a query is genuinely ambiguous without a clear business subject.
    
    If intent confidence is genuinely low, do NOT guess.
    Ask a concise clarification question.
    
    Example:
    'Show warehouse details for Plant 7228'
    -> Clarification:
    'Would you like to view the **inventory stock details**, **bin utilization**, **storage capacity**, or a **general plant summary** for Plant 7228?'
    
    Do NOT ask clarification when the intent is already clear (e.g. 'Show detailed inventory for Plant 7228').
    """
    q_low = normalized_query.lower().strip()

    # If explicit subject is clear, it is NOT ambiguous
    if is_explicit_inventory_intent(q_low) or is_explicit_bin_utilization_intent(q_low) or is_empty_bins_intent(q_low) or is_explicit_capacity_intent(q_low):
        return False, None

    # Check for genuine ambiguity: asks for generic "details", "report", or "overview" of a plant/warehouse without subject
    is_generic_query = any(re.search(r"\b" + re.escape(w) + r"\b", q_low) for w in [
        "warehouse details", "details for plant", "details of plant", "plant details",
        "show details for plant", "give details for plant", "tell me about plant",
        "information for plant", "plant report", "warehouse report for plant",
        "overview of plant", "plant overview"
    ]) or (
        ("details" in q_low or "detail" in q_low or "information" in q_low) and
        ("plant" in q_low or len(plants) > 0) and
        not any(s in q_low for s in ["inventory", "material", "stock", "sku", "bin", "utiliz", "capacity", "volume", "occupan"])
    )

    if is_generic_query:
        target_plant = plants[0] if plants else "the warehouse"
        plant_str = f" for Plant {target_plant}" if target_plant != "the warehouse" else ""
        clarification_msg = (
            f"Would you like to view the **inventory stock details**, **bin utilization**, "
            f"**storage capacity**, or a **general warehouse summary**{plant_str}?"
        )
        return True, clarification_msg

    return False, None


# -----------------------------------------------------------------------------
# 5. STRUCTURED QUERY PLAN GENERATOR (REQUIREMENT 1)
# -----------------------------------------------------------------------------

def build_structured_query_plan(question: str, history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Converts every user query into a clean, canonical structured query plan.
    
    Components:
    - intent (INVENTORY, BIN_UTILIZATION, RANKING, COMPARISON, CAPACITY, EMPTY_BINS, OCCUPIED_BINS, MATERIAL_AVAILABILITY, CLARIFICATION)
    - entity (MATERIAL, BIN, PLANT, STORAGE_LOCATION, WAREHOUSE, INVENTORY)
    - plants (list of plant IDs)
    - bins (list of bin IDs)
    - materials (list of material IDs)
    - metric (INVENTORY_QUANTITY, BIN_UTILIZATION, AVAILABLE_CAPACITY, EMPTY_BINS, etc.)
    - operation (LIST, AGGREGATION, RANKING, COMPARISON, DETAILED_REPORT, SUMMARY, CLARIFICATION)
    - ranking_direction (ASC, DESC, BOTH, NONE)
    - limit (int | None)
    - range_filter (dict | None)
    - detail_mode (bool)
    - summary_mode (bool)
    - visualization_mode (bool)
    - comparison_mode (bool)
    """
    raw_query = question.strip()
    norm_query = normalize_text(raw_query)
    q_low = norm_query.lower()

    # 1. Extract physical entities & scope
    plants = extract_plants(norm_query)
    bins = extract_specific_bins(norm_query)
    materials = extract_specific_materials(norm_query)
    limit_val = extract_limit(norm_query)
    range_filter = extract_range_filter(norm_query)
    modifiers = extract_response_modifiers(norm_query)

    # 2. Check Ambiguity First (Requirement 7)
    is_ambiguous, clarification_prompt = detect_ambiguity(norm_query, plants)
    if is_ambiguous:
        return {
            "intent": "CLARIFICATION",
            "entity": "PLANT" if plants else "WAREHOUSE",
            "plants": plants,
            "bins": bins,
            "materials": materials,
            "metric": "CLARIFICATION",
            "operation": "CLARIFICATION",
            "ranking_direction": "NONE",
            "limit": None,
            "range_filter": None,
            "detail_mode": modifiers["detail_mode"],
            "summary_mode": modifiers["summary_mode"],
            "visualization_mode": modifiers["visualization_mode"],
            "comparison_mode": False,
            "ambiguity_detected": True,
            "clarification_question": clarification_prompt,
            "normalized_query": norm_query,
            "raw_query": raw_query,
            "filters": {"plants": plants} if plants else {}
        }

    # 3. Check for Conversational Follow-up (Requirement 6)
    is_followup = bool(history and len(history) > 0 and (
        any(q_low.startswith(w) for w in ["what about", "how about", "what if", "and for", "only", "and in", "what of", "now show", "instead", "what are the"]) or
        q_low in ["lowest ones", "highest ones", "what about the lowest", "what about the lowest ones", "what about the highest", "lowest", "highest"] or
        any(k in q_low for k in ["lowest ones", "highest ones", "what about the lowest", "what about the highest", "only plant", "for plant", "in plant"]) or
        (len(plants) == 1 and len(q_low.split()) <= 4 and not any(w in q_low for w in ["show", "list", "give", "display", "tell", "explain"])) or
        (modifiers["detail_mode"] and len(q_low.split()) <= 3) or
        (modifiers["visualization_mode"] and len(q_low.split()) <= 4)
    ))

    # Reconstruct prior query plan from history if it is a follow-up
    prior_plan: Optional[Dict[str, Any]] = None
    if is_followup and history:
        for idx in range(len(history) - 1, -1, -1):
            msg = history[idx]
            if msg.get("role") == "user" and msg.get("content"):
                prior_q = msg.get("content")
                if prior_q != question:
                    prior_hist = history[:idx]
                    prior_plan = build_structured_query_plan(prior_q, history=prior_hist)
                    if prior_plan.get("intent") != "CLARIFICATION":
                        break

    # 4. Determine Operation & Ranking Direction
    is_comp_word = any(re.search(r"\b" + re.escape(w) + r"\b", q_low) for w in ["compare", "comparison", "versus", "vs", "between", "against", "difference between"])
    comparison_mode = bool(is_comp_word or len(plants) >= 2)

    has_rank_highest = any(re.search(r"\b" + re.escape(w) + r"\b", q_low) for w in ["top", "highest", "most", "maximum", "max", "best", "fullest"])
    has_rank_lowest = any(re.search(r"\b" + re.escape(w) + r"\b", q_low) for w in ["bottom", "lowest", "least", "minimum", "min", "worst", "fewest", "emptiest"])
    
    ranking_direction = "NONE"
    if has_rank_highest and has_rank_lowest:
        ranking_direction = "BOTH"
    elif has_rank_lowest:
        ranking_direction = "ASC"
    elif has_rank_highest:
        ranking_direction = "DESC"

    is_ranking = ranking_direction != "NONE" or bool(re.search(r"\b(?:rank|ranking|rankings)\b", q_low))

    # 5. Core Intent & Entity Resolution (SUBJECT FIRST - Requirement 3)
    if is_explicit_inventory_intent(norm_query):
        intent = "INVENTORY"
        entity = "MATERIAL" if (materials or any(m in q_low for m in ["material", "materials", "sku", "skus"])) else "INVENTORY"
        metric = "INVENTORY_DETAIL" if modifiers["detail_mode"] else (
            "INVENTORY_QUANTITY" if is_ranking else "TOTAL_INVENTORY"
        )
        if comparison_mode:
            operation = "COMPARISON"
            metric = "INVENTORY_COMPARISON"
        elif is_ranking:
            operation = "RANKING"
        elif modifiers["detail_mode"]:
            operation = "DETAILED_REPORT"
        else:
            operation = "AGGREGATION" if not any(w in q_low for w in ["list", "show", "all"]) else "LIST"

    elif is_explicit_bin_utilization_intent(norm_query):
        intent = "BIN_UTILIZATION"
        entity = "BIN"
        metric = "BIN_UTILIZATION"
        if comparison_mode:
            operation = "COMPARISON"
            metric = "BIN_UTILIZATION_COMPARISON"
        elif is_ranking:
            operation = "RANKING"
        elif modifiers["detail_mode"]:
            operation = "DETAILED_REPORT"
        else:
            operation = "SUMMARY" if modifiers["summary_mode"] else "AGGREGATION"

    elif is_empty_bins_intent(norm_query):
        intent = "EMPTY_BINS"
        entity = "BIN"
        metric = "EMPTY_BINS"
        operation = "RANKING" if is_ranking else "LIST"

    elif is_occupied_bins_intent(norm_query):
        intent = "OCCUPIED_BINS"
        entity = "BIN"
        metric = "OCCUPIED_BINS"
        operation = "AGGREGATION"

    elif is_explicit_capacity_intent(norm_query):
        intent = "CAPACITY"
        entity = "BIN"
        metric = "AVAILABLE_CAPACITY"
        operation = "RANKING" if is_ranking else "AGGREGATION"

    elif is_followup and prior_plan and not any(m in q_low for m in ["material", "materials", "sku", "skus", "bin", "bins", "storage location"]):
        # Elliptical follow-up without a new entity explicitly specified:
        # e.g. "What about the lowest ones?", "Only Plant 1258", "What about Plant 1258?", "Show top 5 instead"
        intent = prior_plan["intent"]
        entity = prior_plan["entity"]
        metric = prior_plan["metric"]
        operation = prior_plan["operation"]
        limit_val = limit_val or prior_plan.get("limit")
        range_filter = range_filter or prior_plan.get("range_filter")

        # Handle dimension updates:
        # 1. Reverse ranking direction (e.g. "What about the lowest ones?")
        if has_rank_lowest:
            ranking_direction = "ASC"
            operation = "RANKING"
        elif has_rank_highest:
            ranking_direction = "DESC"
            operation = "RANKING"
        else:
            ranking_direction = ranking_direction if ranking_direction != "NONE" else prior_plan.get("ranking_direction", "NONE")

        # 2. Plant filter update (e.g. "Only Plant 1258", "What about Plant 1258?")
        if not plants and prior_plan.get("plants"):
            plants = prior_plan["plants"]

        # 3. Modifiers inheritance/extension
        modifiers["detail_mode"] = modifiers["detail_mode"] or prior_plan.get("detail_mode", False)
        modifiers["visualization_mode"] = modifiers["visualization_mode"] or prior_plan.get("visualization_mode", False)

    elif is_ranking:
        intent = "RANKING"
        entity = "MATERIAL" if any(m in q_low for m in ["material", "sku", "item"]) else "BIN"
        metric = "INVENTORY_QUANTITY" if entity == "MATERIAL" else "BIN_UTILIZATION"
        operation = "RANKING"

    elif comparison_mode:
        intent = "COMPARISON"
        entity = "PLANT"
        metric = "BIN_UTILIZATION_COMPARISON" if any(u in q_low for u in ["utiliz", "fill", "full"]) else "INVENTORY_COMPARISON"
        operation = "COMPARISON"

    else:
        # Default fallback to warehouse inventory summary
        intent = "INVENTORY"
        entity = "INVENTORY"
        metric = "TOTAL_INVENTORY"
        operation = "SUMMARY" if modifiers["summary_mode"] else "AGGREGATION"

    plan = {
        "intent": intent,
        "entity": entity,
        "plants": plants,
        "bins": bins,
        "materials": materials,
        "metric": metric,
        "operation": operation,
        "ranking_direction": ranking_direction,
        "limit": limit_val or (10 if operation == "RANKING" else None),
        "range_filter": range_filter,
        "detail_mode": modifiers["detail_mode"],
        "summary_mode": modifiers["summary_mode"],
        "visualization_mode": modifiers["visualization_mode"],
        "comparison_mode": comparison_mode,
        "ambiguity_detected": False,
        "clarification_question": None,
        "normalized_query": norm_query,
        "raw_query": raw_query,
        "filters": {"plants": plants} if plants else {}
    }

    return plan


# -----------------------------------------------------------------------------
# 6. PRE-EXECUTION QUERY-PLAN VALIDATION (REQUIREMENT 4)
# -----------------------------------------------------------------------------

def validate_and_sanitize_query_plan(plan: Dict[str, Any], raw_query: str) -> Tuple[Dict[str, Any], List[str]]:
    """Validates that the selected intent, entity, metric and requested operation are compatible.
    
    If the planner produces:
    intent = BIN_UTILIZATION for 'Show detailed inventory for Plant 7228'
    this is invalid because the query explicitly requests inventory.
    The system corrects/reclassifies the intent before execution.
    """
    warnings: List[str] = []
    sanitized = dict(plan)
    q_low = raw_query.lower()

    # Rule 1: Explicit Inventory Request MUST NOT be classified as BIN_UTILIZATION
    if is_explicit_inventory_intent(raw_query) and sanitized.get("intent") == "BIN_UTILIZATION":
        logger.warning(f"Plan Validation Correction: Query explicitly asks for inventory, but intent was BIN_UTILIZATION. Correcting to INVENTORY.")
        sanitized["intent"] = "INVENTORY"
        sanitized["entity"] = "MATERIAL" if any(m in q_low for m in ["material", "sku", "item"]) else "PLANT"
        sanitized["metric"] = "INVENTORY_DETAIL" if sanitized.get("detail_mode") else "TOTAL_INVENTORY"
        if sanitized.get("detail_mode"):
            sanitized["operation"] = "DETAILED_REPORT"
        warnings.append("Auto-corrected intent from BIN_UTILIZATION to INVENTORY based on explicit inventory subject priority.")

    # Rule 2: Explicit Bin Utilization Request MUST NOT be classified as INVENTORY
    if is_explicit_bin_utilization_intent(raw_query) and sanitized.get("intent") == "INVENTORY":
        logger.warning(f"Plan Validation Correction: Query explicitly asks for bin utilization, but intent was INVENTORY. Correcting to BIN_UTILIZATION.")
        sanitized["intent"] = "BIN_UTILIZATION"
        sanitized["entity"] = "BIN"
        sanitized["metric"] = "BIN_UTILIZATION"
        if sanitized.get("detail_mode"):
            sanitized["operation"] = "DETAILED_REPORT"
        warnings.append("Auto-corrected intent from INVENTORY to BIN_UTILIZATION based on explicit bin utilization subject priority.")

    # Rule 3: Ranking operation without direction or metric
    if sanitized.get("operation") == "RANKING":
        if sanitized.get("ranking_direction") == "NONE":
            sanitized["ranking_direction"] = "DESC"  # Default to top/highest
        if not sanitized.get("metric"):
            sanitized["metric"] = "INVENTORY_QUANTITY" if sanitized.get("entity") == "MATERIAL" else "BIN_UTILIZATION"

    # Rule 4: Comparison operation requires multiple entities or plants
    if sanitized.get("operation") == "COMPARISON" and len(sanitized.get("plants", [])) < 2:
        if not any(w in q_low for w in ["all plants", "across plants", "each plant"]):
            # If only 1 plant was extracted, comparison might be single plant vs another in context
            pass

    return sanitized, warnings


# -----------------------------------------------------------------------------
# 7. POST-EXECUTION RESPONSE VALIDATION (REQUIREMENT 5)
# -----------------------------------------------------------------------------

def validate_response_match(plan: Dict[str, Any], rows: List[Dict[str, Any]], answer: str) -> Tuple[bool, str, Optional[str]]:
    """Validates that the returned response matches the requested business subject/intent.
    
    Example:
    Expected: INVENTORY
    Returned data contains only:
    - Bin Utilization
    - Utilized Bins
    - Empty Bins
    - Average Utilization
    
    This mismatch is detected, and this function signals 'reroute_to_inventory'.
    """
    expected_intent = plan.get("intent")
    cols = list(rows[0].keys()) if rows else []
    ans_low = answer.lower()

    # Check 1: Expected INVENTORY, but result contains exclusively Bin Utilization
    if expected_intent == "INVENTORY":
        bin_util_only_cols = {"Bin Utilization %", "BinUtilizationPct", "Utilization %", "Capacity Utilization %", "Occupied Bins", "Empty Bins"}
        has_inv_cols = any(c in cols for c in ["Material", "Material Description", "MaterialDescription", "Total Stock Quantity", "UnrestrictedQty", "Total Inventory Quantity"])
        is_bin_util_header = "bin utilization" in ans_low and "detailed inventory report" not in ans_low
        
        if (not has_inv_cols and any(c in cols for c in bin_util_only_cols)) or (is_bin_util_header and not has_inv_cols):
            logger.warning("Response Validation Mismatch: Expected INVENTORY, but response contains exclusively Bin Utilization data!")
            return False, "Response contains Bin Utilization instead of requested Inventory.", "reroute_to_inventory"

    # Check 2: Protect Rule 8 - Bin Utilization responses MUST NOT show 'Occupied Volume'
    if expected_intent == "BIN_UTILIZATION":
        if any("occupied volume" in str(c).lower() for c in cols):
            logger.warning("Response Validation Mismatch: Bin Utilization response contains forbidden 'Occupied Volume' column.")
            return False, "Bin utilization response contained forbidden Occupied Volume metric.", "sanitize_columns"

    return True, "Response matches requested query plan intent.", None


# -----------------------------------------------------------------------------
# 8. DEVELOPER DIAGNOSTICS PIPELINE LOGGER (REQUIREMENT 10)
# -----------------------------------------------------------------------------

def log_pipeline_diagnostics(
    raw_query: str,
    plan: Dict[str, Any],
    handler_name: str,
    validation_status: str,
    final_summary: str
) -> None:
    """Logs the structured query pipeline trace for developer diagnostics only.
    
    Trace format:
    USER QUERY -> NORMALIZED QUERY -> INTENT -> ENTITY -> FILTERS -> METRIC -> OPERATION -> RESPONSE MODE -> HANDLER -> VALIDATION -> FINAL RESPONSE
    """
    norm = plan.get("normalized_query", "")
    intent = plan.get("intent", "UNKNOWN")
    entity = plan.get("entity", "UNKNOWN")
    filters = plan.get("filters", {})
    metric = plan.get("metric", "UNKNOWN")
    operation = plan.get("operation", "UNKNOWN")
    resp_mode = "GRAPH" if plan.get("visualization_mode") else ("DETAIL" if plan.get("detail_mode") else ("SUMMARY" if plan.get("summary_mode") else "STANDARD"))
    
    diagnostic_trace = (
        f"\n[QUERY PIPELINE DIAGNOSTIC]\n"
        f"  USER QUERY        : '{raw_query}'\n"
        f"  NORMALIZED QUERY  : '{norm}'\n"
        f"  INTENT            : {intent}\n"
        f"  ENTITY            : {entity}\n"
        f"  FILTERS           : {filters}\n"
        f"  METRIC            : {metric}\n"
        f"  OPERATION         : {operation}\n"
        f"  RESPONSE MODE     : {resp_mode}\n"
        f"  HANDLER           : {handler_name}\n"
        f"  VALIDATION        : {validation_status}\n"
        f"  FINAL RESPONSE    : {final_summary[:120]}...\n"
    )
    logger.info(diagnostic_trace)
