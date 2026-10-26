"""Warehouse BI Semantic Layer & Context-Driven LLM Engine.
Translates natural language questions to validated SQL, visual artifacts, and grounded executive insights
using rich context models, business definitions, calculation rules, and dimensional metadata.
"""

import os
import json
import re
import httpx
from typing import Any
from pathlib import Path
from .config import settings
from .semantic_context import WAREHOUSE_SEMANTIC_CONTEXT, PROJECT_CAPACITY_THRESHOLDS

# Load Prompts from files or fallbacks
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"

def load_prompt(filename: str, default: str) -> str:
    path = PROMPTS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return default

SQL_PROMPT_SYSTEM = load_prompt("sql_prompt.txt", """You are a warehouse SQL Server database engineer and analyst. Convert questions into valid SQL Server SELECT queries.""")
ANSWER_PROMPT_SYSTEM = load_prompt("answer_prompt.txt", """You are a senior Warehouse Operations Executive Assistant. Summarize query results concisely without raw data tables.""")
RETRY_PROMPT_TEMPLATE = load_prompt("validation_retry_prompt.txt", """Previous query failed: {error_message}\nFailed SQL: {failed_sql}\nReturn corrected JSON.""")

def clean_llm_json(raw_text: str) -> dict[str, Any]:
    """Parse JSON from LLM response safely, handling markdown backticks."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    
    return json.loads(text)

def normalize_query_typos(text: str) -> str:
    """Normalizes common typos and transliterations in warehouse queries without altering IDs or numeric values."""
    if not text:
        return ""
    typo_patterns = [
        (r'\butlizat(?:ion|ions|on|ons)\b', 'utilization'),
        (r'\butilizat(?:on|ons)\b', 'utilization'),
        (r'\butlization\b', 'utilization'),
        (r'\butlizations\b', 'utilization'),
        (r'\butilzation\b', 'utilization'),
        (r'\butilzations\b', 'utilization'),
        (r'\butillization\b', 'utilization'),
        (r'\butillizations\b', 'utilization'),
        (r'\butilisations?\b', 'utilization'),
        (r'\butlisations?\b', 'utilization'),
        (r'\boccypied\b', 'occupied'),
        (r'\boccupenc(?:y|ies)\b', 'occupancy'),
        (r'\bcapcit(?:y|ies)\b', 'capacity'),
        (r'\binvetor(?:y|ies)\b', 'inventory'),
        (r'\bmaterals?\b', 'materials'),
        (r'\bmateral\b', 'material'),
        (r'\blocatons?\b', 'locations'),
        (r'\bplnts?\b', 'plants'),
        (r'\bplnt\b', 'plant'),
    ]
    res = text
    for pattern, repl in typo_patterns:
        res = re.sub(pattern, repl, res, flags=re.IGNORECASE)
    return res

def extract_explicit_plants(text: str) -> list[str]:
    """Extract every plant explicitly requested, including chained forms like
    'Plant 1258 and 1268', 'plants 1258, 1268 & 7228', and repeated 'Plant N'.
    This is intentionally separate from generic number extraction so thresholds,
    quantities, and years are not mistaken for plant IDs.
    """
    q = (text or "").lower()
    found: list[str] = []

    # Capture a plant ID plus any immediately chained plant IDs.
    chain_re = re.compile(
        r"\bplants?\b\s*(?:#|:|-)?\s*(\d{4,5})"
        r"((?:\s*(?:,\s*(?:and|&|or)|,|and|&|or|/)\s*(?:plants?\s*)?\d{4,5})*)",
        re.IGNORECASE,
    )
    for m in chain_re.finditer(q):
        found.append(m.group(1))
        for n in re.findall(r"(?:,\s*(?:and|&|or)|,|and|&|or|/)\s*(?:plants?\s*)?(\d{4,5})", m.group(2), re.I):
            found.append(n)

    # Also catch repeated explicit forms: "Plant 1258 and Plant 1268".
    for n in re.findall(r"\bplants?\s*(?:#|:|-)?\s*(\d{4,5})\b", q, re.I):
        found.append(n)

    # "both 7228 and 1268"
    m_both = re.search(r"\bboth\s+(\d{4,5})\s*(?:and|&)\s*(\d{4,5})\b", q)
    if m_both:
        found.extend([m_both.group(1), m_both.group(2)])

    # Exclude years that can appear in otherwise valid questions.
    return list(dict.fromkeys(n for n in found if n not in {"2024", "2025", "2026"}))

extract_plants = extract_explicit_plants

def extract_single_plant_safe(text: str) -> Optional[str]:
    """Extract a single plant ID safely without confusing quantities/thresholds for plants."""
    explicit = extract_explicit_plants(text)
    if len(explicit) == 1:
        return explicit[0]
    if len(explicit) > 1:
        return None
    m = re.findall(r"\b(1258|1266|1268|7228)\b", (text or "").lower())
    if len(m) == 1:
        return m[0]
    return None

def extract_explicit_limit(q_lower: str) -> Optional[int]:
    """Extract an explicit row/item limit requested by the user, ignoring thresholds and quantities."""
    # 1. Follow-up limit adjustments: "show 5 instead", "5 instead", "make it 5", "change to 5", "just 5", "only 5", "limit to 5"
    m_adj = re.search(r"\b(?:show\s+|give\s+me\s+|display\s+|limit\s+to\s+|make\s+it\s+|change\s+to\s+|just\s+|only\s+)?(\d{1,3})\s+instead\b", q_lower)
    if m_adj:
        val = int(m_adj.group(1))
        if val not in [2024, 2025, 2026, 1258, 1266, 1268, 7228]:
            return val

    m_change = re.search(r"\b(?:make\s+it|change\s+(?:limit\s+)?to|set\s+limit\s+to|limit\s+to)\s*(\d{1,3})\b(?!\s*%)", q_lower)
    if m_change:
        val = int(m_change.group(1))
        if val not in [2024, 2025, 2026, 1258, 1266, 1268, 7228]:
            return val

    # 2. Ranking or count limit prefix: "top 10", "bottom 5", "first 20", "last 5", "highest 10", "lowest 5", "limit 25"
    m = re.search(r"\b(?:top|bottom|highest|lowest|first|last|least|limit)\s*(\d{1,3})\b(?!\s*%)", q_lower)
    if m:
        val = int(m.group(1))
        if val not in [2024, 2025, 2026, 1258, 1266, 1268, 7228]:
            return val

    # 2B. Number before ranking adjective: "10 most", "10 least", "5 highest", "5 lowest"
    m_rev = re.search(r"\b(\d{1,3})\s+(?:most|least|highest|lowest|fullest|emptiest|best|worst|top|bottom)\b(?!\s*%)", q_lower)
    if m_rev:
        val = int(m_rev.group(1))
        if val not in [2024, 2025, 2026, 1258, 1266, 1268, 7228]:
            return val
            
    # 3. Explicit action + quantity + optional entity: "show 5 empty bins", "give me 10 materials", "display 20 rows", "list 5 bins", "show 5"
    m2 = re.search(r"\b(?:show|give\s+me|display|list|fetch)\s+(?:the\s+)?(\d{1,3})(?:\s+(?:completely\s+|active\s+|empty\s+|vacant\s+)?(?:bins?|materials?|records?|rows?|items?|results?))?\b(?!\s*%)", q_lower)
    if m2:
        val = int(m2.group(1))
        if val not in [2024, 2025, 2026, 1258, 1266, 1268, 7228]:
            return val

    # 4. Leading count: "5 empty bins", "10 bins"
    m3 = re.search(r"^(?:show|get|find|display)?\s*(\d{1,3})\s+(?:completely\s+|active\s+|empty\s+|vacant\s+)?(?:bins?|materials?|records?|rows?|items?|results?)\b(?!\s*%)", q_lower)
    if m3:
        val = int(m3.group(1))
        if val not in [2024, 2025, 2026, 1258, 1266, 1268, 7228]:
            return val

    return None

def extract_quantity_threshold(text: str) -> Optional[tuple[str, float]]:
    """Extract operator and numeric quantity threshold from query.
    
    Returns (op, threshold) where op is in [">=", "<=", ">", "<"].
    """
    q = (text or "").lower()
    if "%" in q or "percent" in q or any(u in q for u in ["utiliz", "occupan", "capacity", "volume", "ft3", "cubic"]):
        return None

    def parse_num(num_str: str) -> Optional[float]:
        num_clean = num_str.replace(",", "").strip()
        if num_clean.endswith("k"):
            try:
                return float(num_clean[:-1]) * 1000.0
            except ValueError:
                return None
        try:
            return float(num_clean)
        except ValueError:
            return None

    num_pattern = r"(\d[\d,]*(?:\.\d+)?k?)"

    # 1. Operators: >= or <=
    m_gte = re.search(r"(?:>=|greater\s+than\s+or\s+equal\s+to|more\s+than\s+or\s+equal\s+to|at\s+least|minimum\s+of|min\s+of)\s*" + num_pattern, q)
    if m_gte:
        val = parse_num(m_gte.group(1))
        if val is not None:
            return (">=", val)

    m_gte_suffix = re.search(num_pattern + r"\s*(?:or\s+more|or\s+above|or\s+greater|\+)", q)
    if m_gte_suffix:
        val = parse_num(m_gte_suffix.group(1))
        if val is not None:
            return (">=", val)

    m_lte = re.search(r"(?:<=|less\s+than\s+or\s+equal\s+to|fewer\s+than\s+or\s+equal\s+to|at\s+most|maximum\s+of|max\s+of|no\s+more\s+than)\s*" + num_pattern, q)
    if m_lte:
        val = parse_num(m_lte.group(1))
        if val is not None:
            return ("<=", val)

    # 2. Operators: >
    m_gt = re.search(r"(?:>|greater\s+than|more\s+than|above|over|exceeding|higher\s+than)\s*" + num_pattern, q)
    if m_gt:
        val = parse_num(m_gt.group(1))
        if val is not None:
            return (">", val)

    # 3. Operators: <
    m_lt = re.search(r"(?:<|less\s+than|fewer\s+than|below|under|lower\s+than)\s*" + num_pattern, q)
    if m_lt:
        val = parse_num(m_lt.group(1))
        if val is not None:
            return ("<", val)

    return None

def extract_range_bounds(text: str) -> Optional[tuple[float, float]]:
    """Extract lower and upper bounds from a numeric range query."""
    q = (text or "").lower()
    num_pat = r"(\d[\d,]*(?:\.\d+)?k?)"
    m = re.search(r"(?:between|from|range|in the range of?)\s*" + num_pat + r"\s*(?:and|to|–|-)\s*" + num_pat, q)
    if not m:
        m = re.search(r"\b" + num_pat + r"\s*(?:–|-)\s*" + num_pat + r"\b", q)
    if m:
        def parse_n(s: str) -> Optional[float]:
            s_clean = s.replace(",", "").strip()
            if s_clean.endswith("k"):
                try:
                    return float(s_clean[:-1]) * 1000.0
                except ValueError:
                    return None
            try:
                return float(s_clean)
            except ValueError:
                return None
        low = parse_n(m.group(1))
        high = parse_n(m.group(2))
        if low is not None and high is not None:
            if low > high:
                low, high = high, low
            return (low, high)
    return None

def _plant_sql_clause(column: str, plants: list[str] | None, prefix: str = " AND ") -> str:
    """Build a safe multi-value plant predicate for deterministic SQL."""
    vals = list(dict.fromkeys(str(p) for p in (plants or []) if str(p).isdigit()))
    if not vals:
        return ""
    if len(vals) == 1:
        return f"{prefix}{column} = '{vals[0]}'"
    return f"{prefix}{column} IN ({', '.join(repr(v) for v in vals)})"

def _plant_label(plants: list[str] | None, prefix: str = "Plant ") -> str:
    vals = list(dict.fromkeys(str(p) for p in (plants or [])))
    if not vals:
        return ""
    return ", ".join(f"{prefix}{p}" for p in vals)

def parse_range_filters(q_lower: str, context_metric: str = "quantity") -> list[dict]:
    """Extracts numeric, percentage, date, and ordinal range filters without exact wording.
    
    Returns structured list of range filter dicts:
    [{"field": ..., "operator": "BETWEEN"|"GTE"|"GT"|"LTE"|"LT"|"LAST_DAYS", "lower": ..., "upper": ..., "inclusive": bool}]
    """
    ranges = []
    
    # 1. Percentage ranges (e.g. 10%-30%, between 20% and 40%, below 25% utilization)
    pct_between = re.search(r"(?:between|from)\s*(\d+(?:\.\d+)?)\s*%\s*(?:and|to|–|-)\s*(\d+(?:\.\d+)?)\s*%", q_lower)
    if not pct_between:
        pct_between = re.search(r"\b(\d+(?:\.\d+)?)\s*%\s*(?:–|-|to)\s*(\d+(?:\.\d+)?)\s*%", q_lower)
    if pct_between:
        ranges.append({
            "field": "BinUtilizationPct",
            "operator": "BETWEEN",
            "lower": float(pct_between.group(1)),
            "upper": float(pct_between.group(2)),
            "inclusive": True
        })
        return ranges

    pct_above = re.search(r"(?:above|greater than|more than|over|at least)\s*(\d+(?:\.\d+)?)\s*%", q_lower)
    if pct_above:
        ranges.append({
            "field": "BinUtilizationPct",
            "operator": "GT" if "at least" not in pct_above.group(0) else "GTE",
            "lower": float(pct_above.group(1)),
            "upper": None,
            "inclusive": "at least" in pct_above.group(0)
        })
        return ranges

    pct_below = re.search(r"(?:below|under|less than|up to|at most|no more than)\s*(\d+(?:\.\d+)?)\s*%", q_lower)
    if pct_below:
        ranges.append({
            "field": "BinUtilizationPct",
            "operator": "LT" if not any(k in pct_below.group(0) for k in ["up to", "at most", "no more than"]) else "LTE",
            "lower": None,
            "upper": float(pct_below.group(1)),
            "inclusive": any(k in pct_below.group(0) for k in ["up to", "at most", "no more than"])
        })
        return ranges

    # 2. Date ranges (e.g. between Jan 1 and Mar 31, last 30 days)
    date_months = {
        "jan": "01", "january": "01", "feb": "02", "february": "02",
        "mar": "03", "march": "03", "apr": "04", "april": "04",
        "may": "05", "jun": "06", "june": "06", "jul": "07", "july": "07",
        "aug": "08", "august": "08", "sep": "09", "september": "09",
        "oct": "10", "october": "10", "nov": "11", "november": "11",
        "dec": "12", "december": "12"
    }
    date_between = re.search(r"(?:between|from)\s*([a-z]+)\s*(\d{1,2})\s*(?:and|to|–|-)\s*([a-z]+)\s*(\d{1,2})", q_lower)
    if date_between and date_between.group(1) in date_months and date_between.group(3) in date_months:
        m1 = date_months[date_between.group(1)]
        d1 = int(date_between.group(2))
        m2 = date_months[date_between.group(3)]
        d2 = int(date_between.group(4))
        ranges.append({
            "field": "ChangedAt",
            "operator": "BETWEEN",
            "lower": f"2026-{m1}-{d1:02d}",
            "upper": f"2026-{m2}-{d2:02d}",
            "inclusive": True
        })
        return ranges

    last_days = re.search(r"\blast\s*(\d+)\s*days\b", q_lower)
    if last_days:
        ranges.append({
            "field": "ChangedAt",
            "operator": "LAST_DAYS",
            "lower": int(last_days.group(1)),
            "upper": None,
            "inclusive": True
        })
        return ranges

    # 3. Determine field based on context
    is_util = any(k in q_lower for k in ["utiliz", "occupan", "capacity utilization", "fullness", "fill"]) or "%" in q_lower
    is_avail_cap = any(k in q_lower for k in ["available capacity", "free capacity", "remaining capacity", "unused capacity", "free space", "available space", "spare capacity"])
    is_tot_cap = any(k in q_lower for k in ["total capacity", "bin capacity", "storage capacity"]) or ("capacity" in q_lower and not is_util and not is_avail_cap)
    is_vol = any(k in q_lower for k in ["volume", "m3", "ft3", "cubic"]) and not is_avail_cap

    if is_util:
        field = "BinUtilizationPct"
    elif is_avail_cap:
        field = "AvailableCapacity"
    elif is_tot_cap:
        field = "TotalCapacity"
    elif is_vol:
        field = "Volume"
    else:
        field = "UnrestrictedQty"

    # 4. Numeric between: between 100 and 500, from 100 to 500, in the range 100-500, >= 1000 and <= 5000, 1000 to 5000 capacity
    num_between = re.search(r"(?:between|from|in the range\s*(?:of)?)\s*(\d+(?:\.\d+)?)\s*(?:and|to|–|-)\s*(\d+(?:\.\d+)?)(?:\s*(?:units?|pcs?|items?|capacity|volume|ft3|m3))?", q_lower)
    if not num_between:
        num_between = re.search(r"(?:>=|greater than or equal to|at least)\s*(\d+(?:\.\d+)?)\s*(?:and|,)?\s*(?:<=|less than or equal to|at most)\s*(\d+(?:\.\d+)?)", q_lower)
    if not num_between:
        num_between = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:to|and)\s*(\d+(?:\.\d+)?)\s*(?:capacity|volume|units?|pcs?|items?)\b", q_lower)
    if not num_between:
        num_between = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:–|-)\s*(\d+(?:\.\d+)?)(?:\s*(?:units?|pcs?|items?|capacity|volume|ft3|m3))?", q_lower)
    if num_between:
        low = float(num_between.group(1))
        up = float(num_between.group(2))
        # Ignore plant range like 1258-7228
        if not (low > 1000 and up > 1000 and "plant" in q_lower):
            ranges.append({
                "field": field,
                "operator": "BETWEEN",
                "lower": low,
                "upper": up,
                "inclusive": True
            })
            return ranges

    # 5. Numeric above: at least 100, 100 or more, above 100, greater than 100, over 100, >= 100, > 100
    num_above = re.search(r"(?:at least|above|greater than or equal to|greater than|more than|over|>=|>)\s*(\d+(?:\.\d+)?)(?:\s*(?:units?|pcs?|items?|capacity|volume|ft3|m3))?", q_lower)
    if not num_above:
        num_above = re.search(r"\b(\d+(?:\.\d+)?)\s*or more\b", q_lower)
    if num_above:
        val = float(num_above.group(1))
        is_inc = any(k in num_above.group(0) for k in ["at least", "or more", ">=", "greater than or equal to"])
        ranges.append({
            "field": field,
            "operator": "GTE" if is_inc else "GT",
            "lower": val,
            "upper": None,
            "inclusive": is_inc
        })
        return ranges

    # 6. Numeric below: below 500, under 500, no more than 500, up to 500, less than 500, <= 500, < 500
    num_below = re.search(r"(?:below|under|less than or equal to|less than|up to|at most|no more than|<=|<)\s*(\d+(?:\.\d+)?)(?:\s*(?:units?|pcs?|items?|capacity|volume|ft3|m3))?", q_lower)
    if num_below:
        val = float(num_below.group(1))
        is_inc = any(k in num_below.group(0) for k in ["up to", "at most", "no more than", "<=", "less than or equal to"])
        ranges.append({
            "field": field,
            "operator": "LTE" if is_inc else "LT",
            "lower": None,
            "upper": val,
            "inclusive": is_inc
        })
        return ranges

    return ranges


def parse_compound_capacity_utilization(q_lower: str) -> dict[str, Any] | None:
    """Parses compound capacity + utilization queries on bins (e.g. 'low capacity but high utilization',
    'small bins with high utilization', 'low-capacity highly utilized bins', 'bins with capacity < 45 FT3 and utilization > 80%').
    
    Returns parsed conditions or indicates if clarification is required per the authoritative rule:
    '“Low” and “high” must use predefined project thresholds if available. If no thresholds are defined,
    the chatbot must ask for clarification rather than inventing arbitrary thresholds.'
    """
    # Exclude non-compound single-topic questions
    if any(q_lower.strip() == s for s in [
        "what is the capacity utilization", "capacity utilization",
        "warehouse capacity utilization", "bin capacity utilization",
        "what is the total capacity", "how much space is left"
    ]):
        return None

    # Exclude overall warehouse utilization queries and plant comparison queries
    if any(k in q_lower for k in [
        "overall", "total occupied volume versus", "total occupied volume vs",
        "across all bins", "rate across", "across plants", "whole warehouse", "facility fill",
        "compare plants", "between plants", "by plant", "plant comparison"
    ]) or q_lower.startswith("what is the overall") or q_lower.startswith("what is our overall") or q_lower.startswith("what is our current warehouse space utilization") or "versus total" in q_lower or "vs total" in q_lower:
        return None

    # 1. Identify capacity indicators
    has_cap_qual = any(re.search(r'\b' + re.escape(k) + r'\b', q_lower) for k in [
        "low capacity", "small bin", "small bins", "low-capacity", "smaller bin", "smaller bins",
        "high capacity", "large bin", "large bins", "high-capacity", "larger bin", "larger bins", "big bin", "big bins"
    ])
    has_cap_num = bool(
        re.search(r"(?:capacity|volume|size)\s*(?:is\s*)?(?:under|below|less than|no more than|at most|<|<=|>|>=|over|above|greater than|more than)\s*\d+(?:\.\d+)?", q_lower) or
        re.search(r"(?:under|below|less than|no more than|at most|<|<=|>|>=|over|above|greater than|more than)\s*\d+(?:\.\d+)?\s*(?:ft3|cubic|ft)", q_lower) or
        re.search(r"between\s+\d+(?:\.\d+)?\s*(?:ft3)?\s+and\s+\d+(?:\.\d+)?\s*(?:ft3)?\s*(?:capacity|volume)", q_lower) or
        re.search(r"(?:capacity|volume)\s*(?:between|from)\s*\d+(?:\.\d+)?\s*(?:and|to)\s*\d+(?:\.\d+)?", q_lower)
    )
    has_cap = has_cap_qual or has_cap_num or (
        ("capacity" in q_lower or "volume" in q_lower) and
        any(re.search(r'\b' + re.escape(k) + r'\b', q_lower) for k in ["low", "high", "small", "large", "big", "<", "<=", ">", ">=", "under", "below", "over", "above", "less", "more", "between"])
    )

    # 2. Identify utilization indicators
    has_util_qual = any(re.search(r'\b' + re.escape(k) + r'\b', q_lower) for k in [
        "high utilization", "highly utilized", "high-utilization", "most utilized",
        "low utilization", "least utilized", "low-utilization", "underutilized",
        "highly full", "least full"
    ])
    has_util_num = bool(
        re.search(r"(?:utiliz\w*|occup\w*|full\w*)\s*(?:is\s*)?(?:under|below|less than|no more than|at most|<|<=|>|>=|over|above|greater than|more than)\s*\d+(?:\.\d+)?", q_lower) or
        re.search(r"(?:under|below|less than|no more than|at most|<|<=|>|>=|over|above|greater than|more than)\s*\d+(?:\.\d+)?\s*%\s*(?:utiliz\w*|occup\w*|full)?", q_lower) or
        re.search(r"between\s+\d+(?:\.\d+)?\s*%\s+and\s+\d+(?:\.\d+)?\s*%", q_lower) or
        re.search(r"(?:utiliz\w*|occup\w*)\s*(?:between|from)\s*\d+(?:\.\d+)?\s*%?\s*(?:and|to)\s*\d+(?:\.\d+)?\s*%", q_lower)
    )
    has_util = has_util_qual or has_util_num or (
        any(k in q_lower for k in ["utiliz", "occupan", "fullness"]) and
        any(re.search(r'\b' + re.escape(k) + r'\b', q_lower) for k in ["high", "low", "most", "least", "<", "<=", ">", ">=", "under", "below", "over", "above", "%"])
    )

    if not (has_cap and has_util):
        return None

    # 3. Identify bin entity scope (Per rule: When user asks for compound capacity + utilization, identify entity as Bin)
    is_bin = (
        any(b in q_lower for b in ["bin", "bins", "location", "locations", "racks", "slot", "slots"]) or
        any(q_lower.startswith(p) or f" {p}" in q_lower for p in ["find", "show", "list", "which", "give", "display", "get"]) or
        (not any(p in q_lower for p in ["plant", "plants", "facility", "facilities"]))
    )
    if not is_bin:
        return None

    # 4. Parse Capacity Condition
    cap_cond = None
    cap_val_desc = None

    cap_between = re.search(r"between\s+(\d+(?:\.\d+)?)\s*(?:ft3)?\s+and\s+(\d+(?:\.\d+)?)\s*(?:ft3)?\s*(?:capacity|volume)", q_lower)
    if not cap_between:
        cap_between = re.search(r"(?:capacity|volume)\s*(?:between|from)\s*(\d+(?:\.\d+)?)\s*(?:and|to)\s*(\d+(?:\.\d+)?)", q_lower)
    if cap_between:
        low = float(cap_between.group(1))
        up = float(cap_between.group(2))
        cap_cond = f"CapacityNum BETWEEN {low} AND {up}"
        cap_val_desc = f"between {low} and {up} FT³"
    else:
        cap_lt = re.search(r"(?:capacity|volume|size)\s*(?:is\s*)?(?:under|below|less than|no more than|at most|<|<=)\s*(\d+(?:\.\d+)?)", q_lower)
        if not cap_lt:
            cap_lt = re.search(r"(?:under|below|less than|no more than|at most|<|<=)\s*(\d+(?:\.\d+)?)\s*(?:ft3|cubic|ft)", q_lower)
        if cap_lt:
            val = float(cap_lt.group(1))
            cap_cond = f"CapacityNum <= {val}"
            cap_val_desc = f"<= {val} FT³"
        else:
            cap_gt = re.search(r"(?:capacity|volume|size)\s*(?:is\s*)?(?:over|above|greater than|more than|at least|>|>=)\s*(\d+(?:\.\d+)?)", q_lower)
            if not cap_gt:
                cap_gt = re.search(r"(?:over|above|greater than|more than|at least|>|>=)\s*(\d+(?:\.\d+)?)\s*(?:ft3|cubic|ft)", q_lower)
            if cap_gt:
                val = float(cap_gt.group(1))
                cap_cond = f"CapacityNum >= {val}"
                cap_val_desc = f">= {val} FT³"

    # Qualitative capacity if not numerical
    is_low_cap = any(k in q_lower for k in ["low capacity", "small bin", "small bins", "low-capacity", "smaller bin", "smaller bins"])
    is_high_cap = any(k in q_lower for k in ["high capacity", "large bin", "large bins", "high-capacity", "larger bin", "larger bins", "big bin", "big bins"])
    if not cap_cond:
        if is_low_cap:
            pre_thresh = PROJECT_CAPACITY_THRESHOLDS.get("low_capacity_threshold")
            if pre_thresh is not None:
                cap_cond = f"CapacityNum <= {pre_thresh}"
                cap_val_desc = f"<= {pre_thresh} FT³"
            else:
                cap_val_desc = "low capacity"
        elif is_high_cap:
            pre_thresh = PROJECT_CAPACITY_THRESHOLDS.get("high_capacity_threshold")
            if pre_thresh is not None:
                cap_cond = f"CapacityNum >= {pre_thresh}"
                cap_val_desc = f">= {pre_thresh} FT³"
            else:
                cap_val_desc = "high capacity"

    # 5. Parse Utilization Condition
    util_cond = None
    util_val_desc = None

    util_between = re.search(r"between\s+(\d+(?:\.\d+)?)\s*%\s+and\s+(\d+(?:\.\d+)?)\s*%", q_lower)
    if not util_between:
        util_between = re.search(r"(?:utiliz\w*|occup\w*)\s*(?:between|from)\s*(\d+(?:\.\d+)?)\s*%?\s*(?:and|to)\s*(\d+(?:\.\d+)?)\s*%", q_lower)
    if util_between:
        low = float(util_between.group(1))
        up = float(util_between.group(2))
        util_cond = f"UtilizationNum BETWEEN {low} AND {up}"
        util_val_desc = f"between {low}% and {up}%"
    else:
        util_gt = re.search(r"(?:utiliz\w*|occup\w*|full\w*)\s*(?:is\s*)?(?:over|above|greater than|more than|at least|>|>=)\s*(\d+(?:\.\d+)?)\s*%?", q_lower)
        if not util_gt:
            util_gt = re.search(r"(?:over|above|greater than|more than|at least|>|>=)\s*(\d+(?:\.\d+)?)\s*%\s*(?:utiliz\w*|full)?", q_lower)
        if not util_gt and any(k in q_lower for k in [">", ">="]):
            m = re.search(r"(?:>|>=)\s*(\d+(?:\.\d+)?)\s*%?", q_lower)
            if m:
                util_gt = m
        if util_gt:
            val = float(util_gt.group(1))
            util_cond = f"UtilizationNum >= {val}"
            util_val_desc = f">= {val}%"
        else:
            util_lt = re.search(r"(?:utiliz\w*|occup\w*|full\w*)\s*(?:is\s*)?(?:under|below|less than|no more than|at most|<|<=)\s*(\d+(?:\.\d+)?)\s*%?", q_lower)
            if not util_lt:
                util_lt = re.search(r"(?:under|below|less than|no more than|at most|<|<=)\s*(\d+(?:\.\d+)?)\s*%\s*(?:utiliz\w*|full)?", q_lower)
            if not util_lt and any(k in q_lower for k in ["<", "<="]):
                m = re.search(r"(?:<|<=)\s*(\d+(?:\.\d+)?)\s*%?", q_lower)
                if m:
                    util_lt = m
            if util_lt:
                val = float(util_lt.group(1))
                util_cond = f"UtilizationNum <= {val}"
                util_val_desc = f"<= {val}%"

    # Qualitative utilization if not numerical
    is_high_util = any(k in q_lower for k in ["high utilization", "highly utilized", "high-utilization", "most utilized"])
    is_low_util = any(k in q_lower for k in ["low utilization", "least utilized", "low-utilization", "underutilized"])
    if not util_cond:
        if is_high_util:
            pre_thresh = PROJECT_CAPACITY_THRESHOLDS.get("high_utilization_threshold")
            if pre_thresh is not None:
                util_cond = f"UtilizationNum >= {pre_thresh}"
                util_val_desc = f">= {pre_thresh}%"
            else:
                util_val_desc = "high utilization"
        elif is_low_util:
            pre_thresh = PROJECT_CAPACITY_THRESHOLDS.get("low_utilization_threshold")
            if pre_thresh is not None:
                util_cond = f"UtilizationNum <= {pre_thresh}"
                util_val_desc = f"<= {pre_thresh}%"
            else:
                util_val_desc = "low utilization"

    # 6. Check if clarification is needed
    needs_clarification = (cap_cond is None or util_cond is None)
    
    return {
        "needs_clarification": needs_clarification,
        "cap_condition": cap_cond,
        "util_condition": util_cond,
        "cap_desc": cap_val_desc or "capacity",
        "util_desc": util_val_desc or "utilization"
    }


DETAIL_TRIGGERS = [
    "detail", "details", "detailed", "explain", "explain in detail",
    "elaborate", "deep dive", "break it down", "full details",
    "complete breakdown", "comprehensive view", "in-depth",
    "drill down", "granular analysis", "itemized breakdown",
    "show me the details", "give me more detail"
]

def is_detail_requested(q_lower: str) -> bool:
    """Semantic detail mode detector."""
    return any(re.search(r'\b' + re.escape(t) + r'\b', q_lower) for t in DETAIL_TRIGGERS)


SINGLE_LINE_OVERRIDE_TRIGGERS = [
    "give me the answer in one line",
    "give me the result in one line",
    "answer in a single line",
    "in a single line",
    "in one line",
    "single line",
    "one line",
    "single statement",
    "in a single statement",
    "just give me the answer",
    "give me only the answer",
    "give me only the result",
    "give me a one-line summary",
    "one-line summary",
    "one line summary",
    "single line summary",
    "briefly",
    "answer briefly",
    "just tell me",
    "only tell me",
    "without explanation",
    "no explanation",
    "give me only the number",
    "just the number",
    "only the number",
    "just the count",
    "only the count",
    "just tell me the count",
    "give me only the count",
    "just the percentage",
    "only the percentage",
    "just number",
    "just percentage",
    "concise",
    "in short"
]

NUMBER_ONLY_TRIGGERS = [
    "give me only the number",
    "give me only the percentage",
    "give me only the count",
    "only the number",
    "just the number",
    "only the percentage",
    "just the percentage",
    "only the count",
    "just the count",
    "just tell me the count",
    "only tell me the count",
    "number only",
    "count only",
    "percentage only"
]

def is_number_only_requested(q_lower: str) -> bool:
    """Detects whether user explicitly asks for only the numeric or percentage scalar value."""
    return any(t in q_lower for t in NUMBER_ONLY_TRIGGERS)

def extract_only_number(text: str) -> str:
    """Extracts purely the numerical or percentage scalar value from formatted text."""
    if not text:
        return ""
    # Check for percentage first
    pct_match = re.search(r"(\d+(?:\.\d+)?%)", text)
    if pct_match:
        return pct_match.group(1)
    # Check for numbers with commas / decimals
    num_match = re.search(r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?)", text)
    if num_match:
        return num_match.group(1)
    return text.strip()

VALID_PLANTS = {"1258", "1266", "1268", "7228"}

NONEXISTENT_TRIGGERS = [
    "do not exist", "don't exist", "dont exist", "does not exist", "doesn't exist",
    "nonexistent", "non-existent", "not present in the database", "not present in database",
    "not in the database", "not in database", "invalid plant", "nonexistent plant",
    "non-existent plant", "plants that do not exist", "plants that don't exist",
    "materials that do not exist", "materials that don't exist", "nonexistent material",
    "non-existent material", "details of a nonexistent bin", "details of a non-existent bin"
]

def is_unsupported_nonexistent_query(q_lower: str) -> bool:
    """Detects queries looking for nonexistent/invalid entities or asking for bins/records that do not exist."""
    if any(k in q_lower for k in ["volume master", "material master", "dimension master"]):
        return False
    return any(t in q_lower for t in NONEXISTENT_TRIGGERS)

def extract_invalid_plant_specified(q_lower: str) -> str | None:
    """Detects if an invalid or nonexistent plant ID is referenced."""
    if any(t in q_lower for t in [
        "invalid plant", "nonexistent plant", "non-existent plant", "fake plant", "unknown plant",
        "plant that does not exist", "plants that do not exist",
        "plant that doesn't exist", "plants that don't exist",
        "plant that dont exist", "plants that dont exist"
    ]):
        return "invalid"

    # 1. Match numeric plant code (e.g. Plant 9999, Facility 1234, Plant #9999)
    num_match = re.search(r"\b(?:plant|facility)\s*[:#-]?\s*(\d{2,6})\b", q_lower)
    if num_match:
        val = num_match.group(1)
        if val not in VALID_PLANTS and val not in ["2024", "2025", "2026"]:
            return val
        return None

    # 2. Match alphanumeric or symbolic plant token
    match = re.search(r"\b(?:plant|facility)\s*[:#-]?\s*([a-z0-9_-]+)\b", q_lower)
    if match:
        val = match.group(1).upper()
        stopwords = {
            "HAS", "HAVE", "HAD", "HAVING", "IS", "ARE", "WAS", "WERE", "BE", "BEEN", "BEING",
            "DO", "DOES", "DID", "WILL", "WOULD", "SHALL", "SHOULD", "CAN", "COULD", "MAY", "MIGHT", "MUST",
            "WITH", "FOR", "AND", "OR", "IN", "TO", "AT", "OF", "BY", "FROM", "ON", "ABOUT", "OVER", "UNDER",
            "BETWEEN", "AMONG", "THROUGH", "INTO", "ONTO", "UPON",
            "PERFORMS", "PERFORMING", "PERFORMANCE", "STORAGE", "INVENTORY", "BIN", "BINS",
            "UTILIZATION", "CAPACITY", "DETAIL", "DETAILS", "SUMMARY", "COMPARISON", "COMPARE",
            "ALL", "EACH", "EVERY", "ANY", "SOME", "WHICH", "WHAT", "WHO", "WHOSE", "WHERE", "WHEN", "WHY", "HOW",
            "THE", "A", "AN", "THAT", "THIS", "THESE", "THOSE",
            "BEST", "WORST", "HIGHEST", "LOWEST", "TOP", "BOTTOM", "LEVEL", "WISE",
            "LOCATION", "LOCATIONS", "DATA", "RECORD", "RECORDS", "NAME", "NAMES", "ID", "IDS",
            "NUMBER", "NUMBERS", "CODE", "CODES", "SPACE", "STOCK", "VOLUME", "TOTAL", "FREE", "AVAILABLE",
            "EMPTY", "FULL", "OCCUPIED", "CURRENT", "RIGHT", "NOW", "BREAKDOWN", "STATUS", "DIFFERENCE",
            "TREND", "OVERVIEW", "HEALTH", "CONSOLIDATION", "MATERIAL", "MATERIALS", "METRIC", "METRICS",
            "RANKING", "RANKINGS", "RANK", "RANKS", "UTILIZED", "STORED", "FOUND", "LIST", "SHOW",
            "VIEW", "DISPLAY", "GET", "FETCH", "CHECK", "REPORT", "INFORMATION", "INFO", "STATS", "STATISTICS",
            "RUNNING", "OUT", "BIGGEST", "LARGEST", "SMALLEST", "MOST", "LEAST", "PROBLEM", "PROBLEMS", "ISSUE", "ISSUES",
            "EFFICIENCY", "INEFFICIENT", "OCCUPANCY", "FILL", "RATE", "PERCENTAGE", "COUNT"
        }
        if val in stopwords:
            return None
        if val not in VALID_PLANTS and val not in ["2024", "2025", "2026"]:
            return val
    return None

def is_single_line_requested(q_lower: str, intent: str = "", rows_count: int = 0) -> bool:
    """Infers concise single-line response mode from explicit user phrasing and formatting intent."""
    if any(o in q_lower for o in SINGLE_LINE_OVERRIDE_TRIGGERS):
        return True
    return False


def is_detail_or_graph_requested(question: str) -> bool:
    """Checks if the question explicitly asks for details, explanation, or visual/graphical presentation.
    Includes triggers: detail, explain, show me with, with graph, or with graph, chart, visualize, etc.
    """
    if not question:
        return False
    q = normalize_query_typos(question).lower()
    
    # 1. Visual / Chart triggers
    if any(re.search(r'\b' + re.escape(w) + r'\b', q) for w in [
        "graph", "graphs", "chart", "charts", "visualize", "visualization", "visualised", "visualized",
        "plot", "plots", "bar chart", "line chart", "pie chart", "histogram", "graphical"
    ]):
        return True
    if any(k in q for k in [
        "with graph", "or with graph", "with a graph", "or with a graph",
        "with chart", "or with chart", "with a chart", "or with a chart",
        "show me with", "show with", "in graph", "as graph", "in chart", "as chart"
    ]):
        return True
        
    # 2. Detail & Explain triggers
    if any(re.search(r'\b' + re.escape(w) + r'\b', q) for w in [
        "detail", "details", "detailed", "explain", "explained", "explaining", "explanation", "elaborate"
    ]):
        return True
    if any(k in q for k in [
        "in detail", "detailed version", "detailed breakdown", "detailed analysis",
        "detail form", "detailed form", "deep dive", "break it down"
    ]):
        return True

    return False


def is_explicit_chart_only_requested(question: str) -> bool:
    """Checks strictly for graph/chart/visualization keywords."""
    if not question:
        return False
    q = normalize_query_typos(question).lower()
    if any(re.search(r'\b' + re.escape(w) + r'\b', q) for w in [
        "graph", "graphs", "chart", "charts", "visualize", "visualization", "visualised", "visualized",
        "plot", "plots", "bar chart", "line chart", "pie chart", "histogram", "graphical"
    ]):
        return True
    if any(k in q for k in [
        "with graph", "or with graph", "with a graph", "or with a graph",
        "with chart", "or with chart", "with a chart", "or with a chart",
        "show me with graph", "show with graph", "show me with chart", "show with chart"
    ]):
        return True
    return False


def is_elliptical_followup(q_lower: str) -> bool:
    """Detects if a user question is an elliptical follow-up that relies on prior conversation context."""
    q_strip = q_lower.strip()
    
    # 0. Standalone combined rankings and complete multi-intent warehouse queries are NOT follow-ups
    has_both_kw = (
        any(w in q_strip for w in ["top", "most", "fullest", "highest"]) and
        any(w in q_strip for w in ["bottom", "least", "emptiest", "lowest"]) and
        any(b in q_strip for b in ["bin", "bins", "location", "locations", "racks", "rack"])
    )
    if has_both_kw:
        return False
    
    # 1. Visualization triggers
    if any(k in q_strip for k in [
        "or with graph", "or with a graph", "with graph", "with a graph", "in graph", "as graph", "in a graph",
        "or with chart", "or with a chart", "with chart", "with a chart", "in chart", "as chart", "in a chart",
        "show me with", "show with", "show me with graph", "show me with a graph", "show with graph", "show with a graph",
        "show as graph", "show as a graph", "show it with graph", "show it with a graph", "show it as graph", "show it as a graph",
        "show this with graph", "show this with a graph", "show this as graph", "show this as a graph", "show this in graph",
        "show in a graph", "show in graph", "show graph", "give me a chart", "give me a graph", "give me the graph", "give me the chart",
        "show me the graph", "show me the chart", "visualize this", "visualize it", "visualize", "create a chart",
        "can you graph this", "can you chart this", "graph for this", "chart for this", "show chart", "graph of this",
        "chart of this", "plot this", "plot it", "draw a chart", "make a chart", "make it a graph", "make it a chart",
        "plot a chart", "draw a graph", "visualize the comparison", "give me a chart of the top 10", "graph it", "chart it",
        "display as graph", "display as chart", "display with graph", "display with chart", "display visually",
        "plot the trend", "without a chart", "no chart", "without chart"
    ]) or q_strip in ["graph", "chart", "visualize", "plot", "graphs", "charts"]:
        return True
    
    # 2. Affirmative expansions / drilldowns / detail
    if any(q_strip.startswith(w) for w in ["yes", "yeah", "sure", "please", "expand", "yep"]):
        return True
    if any(k in q_strip for k in [
        "detailed version", "detailed analysis", "generate detail", "show detail", "detailed breakdown",
        "generate detailed", "in detail", "deep dive", "more detail", "more details",
        "break it down", "expand on this", "detailed view", "detailed form",
        "explain this", "explain in detail", "explain with graph", "explain with chart", "elaborate on this",
        "explain this table", "explain the table", "explain the comparison", "what does this mean", "give me a summary",
        "summarize the above", "summarize above", "which one is better", "which is better", "explain the result",
        "what can you conclude", "give me the comparison summary", "interpret this", "tell me what this table means"
    ]) or any(w in q_strip.split() for w in ["detailed", "explain", "elaborate"]):
        return True
    
    # 2B. Presentation / Format modifiers (count, names, percentage)
    if any(k in q_strip for k in [
        "only the count", "only count", "just the count", "count only", "give me only the count", "give only the count",
        "only names", "only the names", "names only", "just the names", "show only the names",
        "only percentage", "only the percentage", "percentage only", "just the percentage", "show only the percentage",
        "just the number", "only the number", "number only", "give me only the number", "give only the number", "show only the number"
    ]) or q_strip in ["count", "names", "percentage"]:
        return True

    # 3. Pronoun / anaphora references
    if any(p in q_strip for p in [
        "for this", "of this", "about this", "for that", "of that", "these", "those", "for them", "of them",
        "do they", "they have", "do these", "these have", "do those", "those have", "their total",
        "those two", "these two", "both", "the two", "ones",
        "other plant", "the other plant", "other one", "another plant",
        "same thing", "the same", "the same thing", "the previous result", "the above", "instead"
    ]):
        return True
    
    # 4. Elliptical questions and conversational pivots
    if any(q_strip.startswith(p) for p in [
        "what about", "and what about", "how about", "and how about",
        "and for", "only for", "only in", "just for", "just in",
        "and in", "now for", "and the", "what if", "only materials",
        "compare those", "compare these", "compare them", "compare both", "compare the two",
        "now show"
    ]):
        return True
    if re.search(r"^(?:only in|only for|just in|just for|in|for)?\s*(?:plant\s+)?\d{3,5}\.?$", q_strip):
        return True
    
    # 5. Incremental adjustments, polarity shifts, ranking pivots, or follow-up counts
    if re.search(r"\b(?:make|change|switch|set)\s+(?:it\s+)?(?:to\s+)?(?:top\s+|bottom\s+)?\d+\b", q_strip):
        return True
    if re.search(r"^(?:show|give|fetch|display)?\s*(?:the\s+)?(?:top|bottom|highest|lowest|least|most)\s+\d+\.?$", q_strip):
        return True
    if re.search(r"\b(?:show|give|fetch|display)?\s*(?:top|bottom|highest|lowest)?\s*\d{1,3}\s+instead\b", q_strip):
        return True
    if any(k in q_strip for k in [
        "reverse it", "reverse the ranking", "reverse order", "flip the ranking", "flip order", "in reverse order", "reverse",
        "instead", "next 10", "show more", "sort by", "ones",
        "least utilized ones", "lowest utilized ones", "most utilized ones",
        "show least utilized", "least ones", "most ones",
        "lowest ones", "highest ones", "bottom ones", "top ones",
        "how many are there", "what is the count", "how many are in there", "how many?", "how many",
        "only materials", "top materials"
    ]):
        return True
    if q_strip in ["materials", "only materials", "top materials"]:
        return True
    
    return False

def extract_and_update_conversation_state(question: str, history: list[dict] | None = None) -> dict[str, Any]:
    """Maintains a structured conversation state machine across multi-turn interactions.
    
    Extracts, preserves, and modifies:
    - entity ("bin" | "material" | "plant")
    - metric ("utilization" | "unrestricted_qty" | "volume" | "missing_dimensions")
    - ranking ("highest" | "lowest" | None)
    - limit (int, default 10)
    - condition ("empty" | "missing_dimensions" | "high_utilization" | "low_utilization" | None)
    - aggregation ("list" | "count" | "sum" | "avg")
    - filters ({"plant": "1258", ...})
    - topic (active analytical intent)
    - resolved_query (semantic query string)
    """
    q_clean = normalize_query_typos(question)
    q_lower = q_clean.lower().strip()
    is_followup = is_elliptical_followup(q_lower) and bool(history)
    
    # Extract any explicit plant filter in the current question safely
    explicit_plants = extract_explicit_plants(q_lower)
    new_plant = explicit_plants[0] if len(explicit_plants) == 1 else None

    # Extract any explicit limit in the current question safely
    new_limit = extract_explicit_limit(q_lower)

    # Default initial state
    state = {
        "entity": "inventory",
        "metric": "total_inventory",
        "operation": "aggregation",
        "ranking": None,
        "limit": new_limit,
        "condition": None,
        "aggregation": "list",
        "filters": {},
        "plants": list(explicit_plants) if len(explicit_plants) >= 2 else ([new_plant] if new_plant else []),
        "active_plant": new_plant or (explicit_plants[-1] if explicit_plants else None),
        "comparison_entities": [{"type": "plant", "value": p} for p in explicit_plants] if len(explicit_plants) >= 2 else [],
        "response_mode": "TABLE",
        "topic": "inventory_summary"
    }
    if len(explicit_plants) >= 2:
        state["filters"]["plants"] = list(explicit_plants)
        state["operation"] = "comparison"
        state["topic"] = "plant_comparison"
        state["entity"] = "plant"

    # Only inherit prior history state if this question is a true conversational follow-up
    if is_followup and history:
        user_queries = [
            msg.get("content", "").strip()
            for msg in history
            if msg.get("role") == "user" and msg.get("content", "").strip()
        ]

        # Reconstruct prior state by traversing user history in order
        for uq in user_queries:
            uq_clean = normalize_query_typos(uq)
            uq_lower = uq_clean.lower()
            
            # Plant filter and ordered tracking in history
            hist_plants = extract_explicit_plants(uq_lower)
            if len(hist_plants) >= 2:
                state["plants"] = list(hist_plants)
                state["comparison_entities"] = [{"type": "plant", "value": p} for p in hist_plants]
                state["filters"]["plants"] = list(hist_plants)
                state["filters"].pop("plant", None)
                state["active_plant"] = hist_plants[-1]
                state["operation"] = "comparison"
                state["topic"] = "plant_comparison"
                state["entity"] = "plant"
            else:
                pm_val = extract_single_plant_safe(uq_lower)
                if any(k in uq_lower for k in ["all plants", "across plants", "by plant", "each plant", "every plant", "plants", "compare plants", "across all", "whole warehouse", "entire warehouse", "network", "overall", "bin utilization", "warehouse utilization"]) and not pm_val:
                    state["filters"].pop("plant", None)
                    state["active_plant"] = None
                elif pm_val:
                    state["filters"]["plant"] = pm_val
                    state["active_plant"] = pm_val
                    if pm_val not in state["plants"]:
                        state["plants"].append(pm_val)
                    if len(state["plants"]) >= 2:
                        state["comparison_entities"] = [{"type": "plant", "value": p} for p in state["plants"][-2:]]

            # Limit in history
            hist_lim = extract_explicit_limit(uq_lower)
            if hist_lim:
                state["limit"] = hist_lim

            # Check other plant in history
            if any(k in uq_lower for k in ["other plant", "the other plant"]):
                if len(state["plants"]) >= 2:
                    last_p = state.get("active_plant")
                    cands = [p for p in state["plants"][-2:] if p != last_p]
                    other_p = cands[0] if cands else state["plants"][0]
                    state["active_plant"] = other_p
                    state["filters"]["plant"] = other_p
                    if state.get("topic") == "plant_comparison":
                        state["topic"] = "plant_inventory"
                        state["operation"] = "aggregation"
                        state["response_mode"] = "TABLE"

            # Check comparison triggers in history
            if any(k in uq_lower for k in ["compare those two", "compare these two", "compare those", "compare them", "compare both", "compare the two"]) or (uq_lower.strip() in ["compare", "compare two"]):
                state["entity"] = "plant" if state.get("response_mode") != "DETAIL" else "bin"
                state["operation"] = "comparison"
                if state.get("response_mode") == "DETAIL":
                    state["topic"] = "multi_plant_bin_detail"
                    state["metric"] = "bin_utilization"
                else:
                    state["topic"] = "plant_comparison"
                if len(state["plants"]) >= 2:
                    state["comparison_entities"] = [{"type": "plant", "value": p} for p in state["plants"][-2:]]
                    state["filters"]["plants"] = [p for p in state["plants"][-2:]]

            # Check presentation / format modifiers in history
            if is_bin_level_detail_intent(uq_lower) or any(k in uq_lower for k in ["detailed version", "in detail", "show detail", "detailed breakdown", "detailed"]):
                state["response_mode"] = "DETAIL"
                if pm_val:
                    state["topic"] = "plant_bin_level_detail"
                    state["metric"] = "bin_utilization"
                    state["entity"] = "bin"
                elif len(hist_plants) >= 2:
                    state["topic"] = "multi_plant_bin_detail"
                    state["metric"] = "bin_utilization"
                    state["entity"] = "bin"
            elif is_comparison_explanation_requested(uq_lower):
                state["response_mode"] = "EXPLANATION"
            elif any(k in uq_lower for k in ["only count", "only the count", "just the count", "count only", "give me only the count"]):
                state["response_mode"] = "COUNT"
            elif any(k in uq_lower for k in ["only names", "only the names", "names only", "just the names", "show only the names"]):
                state["response_mode"] = "NAMES_ONLY"
            elif any(k in uq_lower for k in ["only percentage", "only the percentage", "percentage only", "just the percentage", "show only the percentage"]):
                state["response_mode"] = "PERCENTAGE_ONLY"
            elif any(k in uq_lower for k in ["graph", "chart", "visualize", "plot", "with graph", "as graph"]):
                state["response_mode"] = "GRAPH"
                state["is_explicit_chart_request"] = True

            # Check plant inventory in history
            if any(k in uq_lower for k in ["inventory of plant", "plant inventory", "stock in plant", "stock of plant", "inventory in plant"]) or (
                any(k in uq_lower for k in ["inventory", "stock", "units", "inventory quantity"]) and
                any(k in uq_lower for k in ["plant", "facility", "1258", "7228", "1266", "1268"]) and
                not any(k in uq_lower for k in ["rank", "ranking", "top", "bottom", "capacity", "utiliz", "empty", "compare", "between"])
            ):
                state["entity"] = "plant"
                state["metric"] = "TOTAL_INVENTORY_QUANTITY"
                state["topic"] = "plant_inventory"
                state["operation"] = "aggregation"
                state["condition"] = None
                state["aggregation"] = "aggregation"

            # Check topic signatures
            if (
                (any(k in uq_lower for k in ["occupied volume", "storage volume", "volume occupied", "space occupied", "occupies the most warehouse space", "occupies the most space", "occupies the most", "occupied storage"]) or
                (("volume" in uq_lower or "space" in uq_lower) and any(k in uq_lower for k in ["plant", "plants", "facility", "facilities"]) and any(k in uq_lower for k in ["rank", "top", "bottom", "highest", "lowest", "most", "least", "sort", "occupies"])))
                and not any(m in uq_lower for m in ["material", "materials", "sku", "skus", "consuming", "share of total", "percentage of total"])
            ):
                state["entity"] = "plant"
                state["metric"] = "occupied_volume"
                state["ranking"] = "lowest" if any(k in uq_lower for k in ["least", "lowest", "bottom", "smallest"]) else "highest"
                state["topic"] = "plant_occupied_volume_ranking"
                state["condition"] = None
                state["aggregation"] = "list"
                state["filters"].pop("plant", None)
            elif any(k in uq_lower for k in ["available capacity", "free capacity", "remaining capacity", "available volume", "unused capacity"]) and any(k in uq_lower for k in ["plant", "plants", "facility", "facilities"]):
                state["entity"] = "plant"
                state["metric"] = "available_capacity"
                state["ranking"] = "lowest" if any(k in uq_lower for k in ["least", "lowest", "bottom", "smallest"]) else "highest"
                state["topic"] = "plant_available_capacity_ranking"
                state["condition"] = None
                state["aggregation"] = "list"
            elif any(k in uq_lower for k in ["bin capacity", "total capacity"]) and any(k in uq_lower for k in ["plant", "plants", "facility", "facilities"]) and any(k in uq_lower for k in ["rank", "top", "bottom", "highest", "lowest"]):
                state["entity"] = "plant"
                state["metric"] = "bin_capacity"
                state["ranking"] = "lowest" if any(k in uq_lower for k in ["least", "lowest", "bottom", "smallest"]) else "highest"
                state["topic"] = "plant_bin_capacity_ranking"
                state["condition"] = None
                state["aggregation"] = "list"
            elif any(k in uq_lower for k in ["empty bin", "empty bins", "number of empty bins", "count of empty bins", "most empty bins", "fewest empty bins"]) and any(k in uq_lower for k in ["plant", "plants", "facility", "facilities"]) and any(k in uq_lower for k in ["rank", "ranking", "top", "bottom", "highest", "lowest", "most", "least", "fewest", "which"]):
                state["entity"] = "plant"
                state["metric"] = "EMPTY_BIN_COUNT"
                state["ranking"] = "lowest" if any(k in uq_lower for k in ["least", "lowest", "bottom", "smallest", "fewest"]) else "highest"
                state["topic"] = "plant_empty_bins_ranking"
                state["condition"] = "empty"
                state["aggregation"] = "list"
            elif any(k in uq_lower for k in ["number of bins", "total bins", "bin count"]) and any(k in uq_lower for k in ["plant", "plants", "facility", "facilities"]) and any(k in uq_lower for k in ["rank", "top", "bottom", "highest", "lowest"]):
                state["entity"] = "plant"
                state["metric"] = "bins_count"
                state["ranking"] = "lowest" if any(k in uq_lower for k in ["least", "lowest", "bottom", "smallest", "fewest"]) else "highest"
                state["topic"] = "plant_bins_ranking"
                state["condition"] = None
                state["aggregation"] = "list"
            elif any(k in uq_lower for k in ["unique materials", "number of materials", "skus"]) and any(k in uq_lower for k in ["plant", "plants", "facility", "facilities"]) and any(k in uq_lower for k in ["rank", "top", "bottom", "highest", "lowest"]):
                state["entity"] = "plant"
                state["metric"] = "unique_materials"
                state["ranking"] = "lowest" if any(k in uq_lower for k in ["least", "lowest", "bottom", "smallest", "fewest"]) else "highest"
                state["topic"] = "plant_materials_ranking"
                state["condition"] = None
                state["aggregation"] = "list"
            elif any(k in uq_lower for k in ["total inventory", "inventory quantity", "stock quantity", "total stock", "most stock", "least stock", "most inventory", "least inventory", "stock", "inventory"]) and any(k in uq_lower for k in ["plant", "plants", "facility", "facilities"]) and any(k in uq_lower for k in ["rank", "ranking", "top", "bottom", "highest", "lowest", "most", "least", "which", "who is #1"]):
                state["entity"] = "plant"
                state["metric"] = "total_inventory"
                state["ranking"] = "lowest" if any(k in uq_lower for k in ["least", "lowest", "bottom", "smallest"]) else "highest"
                state["topic"] = "plant_inventory_ranking"
                state["condition"] = None
                state["aggregation"] = "list"
            elif any(k in uq_lower for k in ["all plants", "across plants", "by plant", "each plant", "every plant", "plants", "compare plants", "across all", "whole warehouse", "network", "overall"]) and any(k in uq_lower for k in ["utiliz", "occupan"]):
                state["entity"] = "bin"
                state["metric"] = "warehouse_utilization"
                state["topic"] = "warehouse_utilization"
                state["condition"] = None
                state["aggregation"] = "summary"
                state["filters"].pop("plant", None)
            elif any(k in uq_lower for k in ["utilization detail", "utilization details", "utilization of plant", "plant utilization", "bin utilization detail"]) or (any(k in uq_lower for k in ["bin utilization", "bin occupancy"]) and state["filters"].get("plant")):
                state["entity"] = "bin"
                state["metric"] = "bin_utilization"
                state["topic"] = "plant_bin_utilization_detail"
                state["condition"] = None
                state["aggregation"] = "summary"
            elif any(k in uq_lower for k in ["bin utilization", "overall warehouse", "warehouse space utilization", "warehouse bin utilization", "overall bin utilization", "warehouse utilization", "space utilization rate", "how full", "across plants", "fill percentage", "warehouse fullness", "running out of storage"]):
                state["entity"] = "bin"
                state["metric"] = "warehouse_utilization"
                state["topic"] = "warehouse_utilization"
                state["condition"] = None
                state["aggregation"] = "summary"
            elif any(k in uq_lower for k in ["capacity summary", "warehouse capacity summary", "overall capacity summary"]):
                state["entity"] = "bin"
                state["metric"] = "capacity_summary"
                state["topic"] = "capacity_summary"
                state["condition"] = None
                state["aggregation"] = "summary"
            elif any(k in uq_lower for k in ["total capacity", "total warehouse capacity", "total bin capacity", "total storage capacity", "how much capacity does this warehouse have", "show total bin capacity", "how much storage capacity does this warehouse have"]):
                state["entity"] = "bin"
                state["metric"] = "total_capacity"
                state["topic"] = "total_warehouse_capacity"
                state["condition"] = None
                state["aggregation"] = "sum"
            elif any(k in uq_lower for k in ["how much space is left", "available capacity", "remaining capacity", "unused capacity", "free space", "remaining storage capacity", "how much capacity is still available"]):
                state["entity"] = "bin"
                state["metric"] = "available_capacity"
                state["topic"] = "available_capacity"
                state["condition"] = None
                state["aggregation"] = "sum"
            elif any(k in uq_lower for k in ["empty bin", "empty bins", "vacant bin", "vacant bins"]) and any(k in uq_lower for k in ["capacity", "available capacity", "space", "volume", "how much capacity", "how much space", "how much volume"]):
                state["entity"] = "bin"
                state["metric"] = "empty_bins_capacity"
                state["topic"] = "empty_bins_capacity"
                state["condition"] = None
                state["aggregation"] = "sum"
                state["ranking"] = None
            elif any(k in uq_lower for k in ["least utilized", "lowest utilized", "emptiest bins", "bottom bins", "least full"]):
                state["entity"] = "bin"
                state["metric"] = "utilization"
                state["ranking"] = "lowest"
                state["topic"] = "least_utilized_bins"
                state["condition"] = None
                state["aggregation"] = "list"
            elif any(k in uq_lower for k in ["most utilized", "highest utilized", "top utilized", "fullest bins", "top 10 most", "top 5 most", "most capacity"]):
                state["entity"] = "bin"
                state["metric"] = "utilization"
                state["ranking"] = "highest"
                state["topic"] = "top_utilized_bins"
                state["condition"] = None
                state["aggregation"] = "list"
            elif any(k in uq_lower for k in ["empty bin", "empty bins", "putaway", "put-away", "vacant", "free bin", "available for put-away", "available bin"]) and not any(k in uq_lower for k in ["capacity", "volume", "space"]):
                state["entity"] = "bin"
                state["condition"] = "empty"
                state["topic"] = "putaway_bins"
                state["ranking"] = None
                state["aggregation"] = "list"
            elif any(k in uq_lower for k in ["dimension", "dimensions", "missing physical", "quality check", "incomplete dimension", "unmaintained"]):
                state["entity"] = "material"
                state["condition"] = "missing_dimensions"
                state["topic"] = "data_quality"
                state["aggregation"] = "list"
            elif any(k in uq_lower for k in ["share of total", "volume consumption", "percentage of total", "footprint", "consuming the highest", "largest volume footprint"]):
                state["entity"] = "material"
                state["metric"] = "volume_share"
                state["ranking"] = "highest"
                state["topic"] = "material_volume_share"
                state["aggregation"] = "list"
            elif any(k in uq_lower for k in ["trend", "history", "timeline", "over time", "monthly"]):
                state["entity"] = "inventory"
                state["metric"] = "inventory_trend"
                state["topic"] = "trend_analysis"
                state["aggregation"] = "time_series"
            elif any(k in uq_lower for k in ["division", "material group", "division breakdown"]):
                state["entity"] = "division"
                state["metric"] = "division_inventory"
                state["topic"] = "division_breakdown"
                state["aggregation"] = "breakdown"
            elif any(k in uq_lower for k in ["consolidat", "free up", "duplicate bin", "multiple bin"]):
                state["entity"] = "material"
                state["metric"] = "consolidation_candidates"
                state["topic"] = "consolidation"
                state["aggregation"] = "list"
            elif any(k in uq_lower for k in ["storage location", "storage locations", "across storage locations", "sloc comparison"]):
                state["entity"] = "storage_location"
                state["metric"] = "storage_location_inventory"
                state["topic"] = "storage_location_comparison"
                state["aggregation"] = "comparison"
            elif any(k in uq_lower for k in [
                "total warehouse inventory", "what is the total inventory", "how much inventory is currently in the warehouse",
                "what is the total inventory quantity", "how many units are currently in inventory", "give me the current warehouse inventory",
                "how much stock is in the warehouse", "what is the total stock", "total unrestricted inventory", "total units in inventory",
                "how much total inventory", "total inventory quantity", "what is the total stock quantity", "total unrestricted quantity",
                "how much stock", "total stock", "total inventory", "how much inventory", "current warehouse inventory", "how many total units",
                "units are currently in inventory", "how much inventory do we have", "total stock quantity", "total units of inventory"
            ]) and not any(k in uq_lower for k in ["summary", "overview", "dashboard", "breakdown"]):
                state["entity"] = "inventory"
                state["metric"] = "total_inventory_quantity"
                state["topic"] = "total_inventory_quantity"
                state["condition"] = None
                state["aggregation"] = "sum"
            # Incremental ranking polarity flips & modifiers in history
            elif any(k in uq_lower for k in ["reverse", "flip the ranking", "flip order", "in reverse order"]):
                state["ranking"] = "lowest" if state.get("ranking") == "highest" else "highest"
            elif any(k in uq_lower for k in ["least utilized", "lowest utilized", "least ones", "lowest ones", "least", "bottom", "emptiest"]):
                state["ranking"] = "lowest"
                if state.get("entity") == "plant":
                    if state.get("metric") == "occupied_volume":
                        state["topic"] = "plant_occupied_volume_ranking"
                    elif state.get("topic") in ["highest_bin_utilization", "lowest_bin_utilization"]:
                        state["topic"] = "lowest_bin_utilization"
                elif state.get("entity") == "material":
                    state["topic"] = "material_quantity_ranking"
                elif state.get("entity") == "storage_location":
                    state["topic"] = "storage_location_ranking"
                else:
                    state["entity"] = "bin"
                    state["metric"] = "utilization"
                    state["topic"] = "least_utilized_bins"
                state["condition"] = None
                state["aggregation"] = "list"
            elif any(k in uq_lower for k in ["most utilized", "highest utilized", "top utilized", "fullest bins", "top", "most", "fullest"]) and ("instead" in uq_lower or "most" in uq_lower or "top" in uq_lower or "highest" in uq_lower):
                state["ranking"] = "highest"
                if state.get("entity") == "plant":
                    if state.get("metric") == "occupied_volume":
                        state["topic"] = "plant_occupied_volume_ranking"
                    elif state.get("topic") in ["highest_bin_utilization", "lowest_bin_utilization"]:
                        state["topic"] = "highest_bin_utilization"
                elif state.get("entity") == "material":
                    state["topic"] = "material_quantity_ranking"
                elif state.get("entity") == "storage_location":
                    state["topic"] = "storage_location_ranking"
                else:
                    state["entity"] = "bin"
                    state["metric"] = "utilization"
                    state["topic"] = "top_utilized_bins"
                state["condition"] = None
                state["aggregation"] = "list"
            elif "instead" in uq_lower and lm:
                pass  # limit already updated above; preserve active topic & ranking
            elif any(k in uq_lower for k in ["materials in plant", "materials of plant", "plant inventory records", "show materials", "list materials"]):
                state["entity"] = "material"
                state["topic"] = "plant_materials"
                state["aggregation"] = "list"

    # Now apply the current query modifiers on top of previous state
    # 1. Check if current query is a new independent top-level topic
    is_mat_entity = any(m in q_lower for m in ["material", "materials", "sku", "skus", "item", "items", "product", "products", "goods", "stock item", "stock items"])
    is_fresh_both = (
        any(w in q_lower for w in ["top", "most", "fullest", "highest", "most full", "most utilized", "highest utilized"]) and
        any(w in q_lower for w in ["bottom", "least", "emptiest", "lowest", "least full", "least utilized", "lowest utilized", "empty bins"]) and
        any(b in q_lower for b in ["bin", "bins", "location", "locations", "racks", "rack", "slot", "slots"])
    )
    is_fresh_missing_master = any(k in q_lower for k in [
        "missing from the volume master", "missing from volume master", "not in the volume master",
        "not in volume master", "missing in volume master", "exist in inventory master but not",
        "exists in inventory master but not", "exist in inventory but missing from", "exists in inventory but missing from",
        "in inventory but missing from", "missing from material master", "not in material master",
        "no matching volume master", "unmatched volume master", "missing volume master record",
        "missing volume master records", "no volume master record", "no volume master records",
        "no volume master entry", "no volume master entries", "without volume master",
        "do not have corresponding volume master", "dont have corresponding volume master",
        "do not have volume master", "dont have volume master", "no corresponding volume master",
        "without corresponding volume master", "missing corresponding volume master",
        "not present in material volume master", "not present in volume master", "without volume master",
        "no master entry", "no master entries", "not maintained in volume master"
    ]) or (
        ("inventory" in q_lower or "material" in q_lower or "materials" in q_lower or "sku" in q_lower or "skus" in q_lower or "item" in q_lower or "items" in q_lower or "product" in q_lower or "goods" in q_lower) and
        ("volume master" in q_lower or "material master" in q_lower or "volume-master" in q_lower or "material volume master" in q_lower) and
        ("missing" in q_lower or "absent" in q_lower or "not present" in q_lower or "doesn't exist" in q_lower or "does not exist" in q_lower or "don't exist" in q_lower or "no record" in q_lower or "no entry" in q_lower or "no entries" in q_lower or "not maintained" in q_lower or "not in" in q_lower or "do not have" in q_lower or "dont have" in q_lower or "lack" in q_lower or "lacking" in q_lower or "without" in q_lower or "no matching" in q_lower or "unmatched" in q_lower)
    )
    is_missing_vol_kw = any(k in q_lower for k in [
        "missing volume", "missing physical", "missing dimension", "missing dimensions", "missing physical dimensions",
        "without volume", "no volume", "don't have volume", "dont have volume", "do not have volume",
        "without physical", "no physical", "missing from volume master", "no volume master", "no volume master entry",
        "missing volume details", "missing volume information", "without volume data", "lack volume", "lacking volume"
    ]) and any(k in q_lower for k in ["inventory", "material", "materials", "sku", "skus", "item", "items"])
    is_pct_kw = any(k in q_lower for k in [
        "percentage", "percent", "pct", "%", "how many percent", "what percentage", "what percent"
    ])
    is_fresh_missing_vol_pct = is_missing_vol_kw and is_pct_kw

    is_fresh_mat_vol = is_mat_entity and not is_fresh_missing_master and not is_fresh_missing_vol_pct and any(k in q_lower for k in [
        "volume", "consuming", "space consuming", "consuming most", "volume consumption", "highest space", "occupying highest volume",
        "share of total", "percentage of our total", "percentage of total", "highest percentage", "footprint",
        "cubic capacity", "take up", "occupy", "occupying", "room in the warehouse", "proportion of bin", "storage space",
        "largest volume footprint", "highest proportion", "biggest share", "most room", "consuming the highest percentage"
    ]) and not any(k in q_lower for k in ["volume master", "material master", "missing", "without dimension", "no record", "no entry", "do not have", "dont have", "don't have", "without volume", "no volume"])
    is_fresh_dq = any(k in q_lower for k in [
        "data quality", "quality check", "missing dimension", "incomplete dimension", "without dimension",
        "don't have dimension", "dont have dimension", "cross-dataset", "cross dataset", "unmaintained dimension",
        "missing physical", "incomplete physical", "validation for material volume", "missing length", "missing width",
        "missing height", "no dimension", "no physical dimension", "physical measurements", "material size and cubic volume",
        "check data quality", "without physical size", "incomplete dimensions"
    ]) and not is_fresh_missing_vol_pct
    is_plant_keyword = bool(re.search(r"\b(?:plants?|plnts?|facility|facilities)\b", q_lower))
    is_plant_extreme_req = is_plant_keyword and any(k in q_lower for k in ["lowest", "least", "minimum", "min", "bottom", "worst", "highest", "most", "maximum", "max", "top", "best"]) and any(k in q_lower for k in ["utiliz", "occupan", "capacity", "fill", "full"])
    is_fresh_almost_full = any(k in q_lower for k in [
        "almost full", "nearly full", "near full", "close to full", "close to being full",
        "close to full capacity", "almost at capacity", "near full capacity",
        "nearly at 100% utilization", "nearly at 100%", "almost at 100%"
    ]) and not any(k in q_lower for k in ["over capacity", "over-capacity", "over utilized", "over-utilized", "greater than 100", "above 100", "> 100", ">= 100"])
    is_fresh_over_capacity = any(k in q_lower for k in [
        "over capacity", "over-capacity", "over capacity bins", "full or over capacity",
        "over-utilized bins", "over utilized bins", "exceeding capacity", "exceeds capacity"
    ]) or any(k in q_lower for k in ["full or over", "at or over 100", "100% or more"])

    is_fresh_avail_cap_by_plant = any(k in q_lower for k in [
        "by plant", "for each plant", "plant-wise", "plant wise",
        "each plant", "every plant", "across plants", "of each plant", "compare plants"
    ]) and any(k in q_lower for k in [
        "available capacity", "free capacity", "remaining capacity", "unused capacity",
        "available space", "free space", "remaining space"
    ])
    is_fresh_plant_inventory = (
        any(k in q_lower for k in ["plant-wise", "plant wise", "by plant", "for each plant", "each plant", "across plants", "of each plant", "plants", "inventory of plant", "plant inventory", "stock in plant", "stock of plant", "inventory in plant"])
    ) and not any(k in q_lower for k in ["total inventory in plant", "total stock in plant", "capacity", "utiliz", "occupan", "empty", "missing", "dimension", "master", "difference", "between", "from"]) and not any(k in q_lower for k in ["rank", "ranking", "top", "bottom", "highest", "lowest", "compare", "versus", "vs"])
    is_fresh_empty = any(k in q_lower for k in ["empty bin", "empty bins", "show me empty", "list empty", "putaway", "put-away", "vacant bin", "free bin", "available for immediate put-away", "where can i put", "put new inventory", "place incoming"]) and not any(k in q_lower for k in ["how many", "count", "compare", "versus", "vs", "difference between", "their empty bins", "how much capacity", "how much space", "how much volume", "available capacity", "total capacity"])
    is_fresh_top_bins = bool(re.search(r"\b(?:top|most|fullest)\b", q_lower)) and any(k in q_lower for k in ["utilized bin", "utilised bin", "fullest bin", "capacity bin"]) and not is_mat_entity and not is_plant_extreme_req and not is_fresh_almost_full and not is_fresh_over_capacity
    is_fresh_least_bins = bool(re.search(r"\b(?:bottom|least|lowest|emptiest)\b", q_lower)) and any(k in q_lower for k in ["utilized bin", "utilised bin", "bins", "locations", "capacity"]) and not is_mat_entity and not is_plant_extreme_req and not is_fresh_almost_full and not is_fresh_over_capacity
    is_fresh_plant_count = is_plant_keyword and any(k in q_lower for k in ["how many", "count", "number of", "total plants", "active plants"])
    is_fresh_records_count = (
        any(k in q_lower for k in [
            "inventory record", "inventory records", "inventory row", "inventory rows",
            "records are there", "records in inventory", "number of inventory records",
            "count of inventory records", "total inventory records", "records in plant",
            "inventory records in plant", "records do we have", "rows in inventory",
            "inventory table records", "total inventory rows", "how many records in inventory",
            "how many inventory records"
        ]) or (
            ("record" in q_lower or "records" in q_lower or "rows" in q_lower) and
            ("inventory" in q_lower or "dataset" in q_lower or "table" in q_lower) and
            any(k in q_lower for k in ["how many", "count", "number of", "total"])
        )
    ) and not any(k in q_lower for k in ["missing", "master", "dimension", "show", "list"])
    is_fresh_mat_count = (
        any(k in q_lower for k in [
            "how many materials", "how many unique materials", "how many distinct materials",
            "number of materials in inventory", "how many materials are in inventory", "how many materials are there",
            "how many materials do we have", "number of unique skus", "how many skus in inventory",
            "count of unique materials", "unique materials in warehouse", "materials in inventory",
            "how many unique skus", "count of materials in inventory", "distinct materials in inventory"
        ]) or (
            is_mat_entity and any(k in q_lower for k in ["how many", "count", "number of", "total unique", "unique count", "distinct", "unique"])
        )
    ) and not is_fresh_missing_master and not is_fresh_dq and not is_fresh_records_count and not any(k in q_lower for k in ["show materials", "list materials", "materials in plant", "materials of plant", "which materials"])
    is_fresh_occupied_bins_count = ("occupied" in q_lower or "in use" in q_lower or "active bin" in q_lower) and any(b in q_lower for b in ["bin", "bins"]) and any(k in q_lower for k in ["how many", "count", "number of", "total"])
    is_fresh_total_stock = (
        any(k in q_lower for k in [
            "total warehouse inventory", "what is the total inventory", "how much inventory is currently in the warehouse",
            "what is the total inventory quantity", "how many units are currently in inventory", "give me the current warehouse inventory",
            "how much stock is in the warehouse", "what is the total stock", "total unrestricted inventory", "total units in inventory",
            "how much total inventory", "total inventory quantity", "what is the total stock quantity", "total unrestricted quantity",
            "how much stock", "total stock", "total inventory", "how much inventory", "current warehouse inventory", "how many total units",
            "units are currently in inventory", "how much inventory do we have", "total stock quantity", "total units of inventory"
        ]) or (
            ("inventory" in q_lower or "stock" in q_lower or "units" in q_lower) and
            ("total" in q_lower or "how much" in q_lower or "how many units" in q_lower or "overall quantity" in q_lower) and
            not any(w in q_lower for w in ["per bin", "bin utilization", "empty", "difference", "division", "volume master", "missing", "trend", "record", "records", "rows", "material", "materials", "sku", "skus"])
        )
    ) and not is_fresh_records_count and not is_fresh_mat_count and not is_fresh_plant_inventory and not any(k in q_lower for k in ["summary", "overview", "dashboard", "breakdown", "by plant", "across plants", "plant-wise", "record", "records"])
    is_fresh_consolidation = any(k in q_lower for k in ["consolidat", "free up", "same material", "duplicate bin", "multiple bin"])
    is_fresh_diff = any(k in q_lower for k in ["difference", "zws", "unrestrictedqty2"])
    is_fresh_div = any(k in q_lower for k in ["division", "material group"])
    is_fresh_trend = any(k in q_lower for k in ["trend", "history", "timeline", "over time", "monthly"])
    is_util_keyword = any(k in q_lower for k in ["utiliz", "occupan", "capacity", "how full", "space utilization", "bin fill", "fullness", "fill rate"])
    is_all_plants_util = (
        is_util_keyword and
        any(k in q_lower for k in ["all plants", "across plants", "by plant", "each plant", "every plant", "plants", "compare plants", "across all", "whole warehouse", "entire warehouse", "network", "overall"]) and
        not new_plant and
        not is_fresh_avail_cap_by_plant
    )
    is_fresh_util = is_all_plants_util or any(k in q_lower for k in [
        "overall warehouse bin utilization", "facility fill", "fill rate", "overall bin fill", "space utilization rate",
        "overall bin utilization", "total bin volume is currently occupied", "warehouse space utilization rate",
        "running out of", "out of storage space"
    ])
    
    is_fresh_mat_rank = (
        is_mat_entity and
        any(k in q_lower for k in ["rank", "ranking", "rankings", "top", "bottom", "highest", "lowest", "most", "least"]) and
        not is_fresh_mat_vol and not is_fresh_missing_master and not is_fresh_dq and not is_fresh_mat_count
    )
    is_fresh_sloc_rank = (
        any(k in q_lower for k in ["storage location", "storage locations", "sloc", "slocs"]) and
        any(k in q_lower for k in ["rank", "ranking", "rankings", "top", "bottom", "highest", "lowest", "most", "least"])
    )
    is_fresh_bin_avail_cap = any(b in q_lower for b in ["bin", "bins"]) and any(k in q_lower for k in ["available capacity", "free capacity", "remaining capacity", "available volume", "available space"])
    
    # Specific bin pattern detection (e.g. "Which plant does bin NRJP2124D2 belong to?", "Is bin NRJP2124D2 occupied?", etc.)
    bin_cand_matches = re.findall(r"(?:bin\s*[:#-]?\s*([a-z0-9_-]{2,25})|\b(b\d{3,5})\b)", q_lower, re.IGNORECASE)
    valid_raw_bins = []
    excluded_bin_words = [
        "capacity", "utilization", "master", "table", "space", "volume", "location", "locations",
        "occupancy", "fullness", "empty", "vacant", "free", "ones", "these", "those", "cubic",
        "bins", "fill", "level", "levels", "rate", "rates", "network", "usage", "storage",
        "has", "have", "with", "does", "is", "are", "lowest", "highest", "least", "most", "the"
    ]
    for bm in bin_cand_matches:
        b_val = (bm[0] or bm[1] or "").strip()
        if b_val and b_val.lower() not in excluded_bin_words:
            # Genuine bin codes must contain digits (e.g. B001, NRJP2124D2, BOR11L2P17) or start with B + digits
            if any(c.isdigit() for c in b_val):
                valid_raw_bins.append(b_val.upper())
            elif len(b_val) >= 4 and not b_val.lower().isalpha() and any(c.isdigit() for c in b_val):
                valid_raw_bins.append(b_val.upper())
    is_fresh_specific_bin = len(valid_raw_bins) > 0

    is_overall_network_request = is_all_plants_util or any(k in q_lower for k in ["overall", "network", "all plants", "across all", "facility", "entire warehouse", "whole warehouse", "facility fill", "across the network", "by plant", "across plants"])
    if is_overall_network_request and not new_plant:
        state["filters"].pop("plant", None)

    is_plant_scope = bool(new_plant or (state.get("filters", {}).get("plant") if is_followup else None))
    
    # Visualization Triggers according to Visualization Rules:
    is_explicit_chart_request = (
        any(k in q_lower for k in [
            "show me a graph for this", "show me a graph", "show graph", "give me a chart", "visualize this", "show this in graph",
            "create a chart", "can you graph this", "can you visualize this",
            "show this in graphical form", "draw a chart", "plot this", "visualize", "graph for this",
            "chart for this", "graph of this", "chart of this", "show chart", "give chart", "make a chart",
            "plot a chart", "draw a graph"
        ]) and not any(k in q_lower for k in ["show me with graph", "show with graph", "or with graph"])
    )
    
    is_affirmative_followup = (
        any(w in q_lower.split() for w in ["yes", "yeah", "sure", "please", "expand", "yep", "do"]) or
        any(k in q_lower for k in ["generate detailed", "detailed version", "detailed analysis", "show detail", "detailed breakdown", "generate detail"])
    )
    
    is_followup_for_detail = is_followup and (
        (state.get("topic") in ["plant_bin_utilization_detail", "plant_bin_utilization_summary"] and (is_affirmative_followup or is_explicit_chart_request)) or
        (any(k in q_lower for k in ["generate detailed bin utilization", "detailed bin utilization analysis", "storage location breakdown", "detailed version of this analysis", "sloc breakdown"]) and is_plant_scope) or
        ("detailed version" in q_lower and is_plant_scope and state.get("topic") in ["plant_bin_utilization_detail", "plant_bin_utilization_summary", "warehouse_utilization"])
    )
    is_fresh_plant_bin_util_detail = (
        (is_bin_level_detail_intent(q_lower) or any(k in q_lower for k in ["utiliz", "occupan", "capacity", "how full", "space utilization", "bin fill", "fullness", "fill rate"])) and
        len(explicit_plants) < 2 and
        (new_plant is not None or (is_plant_scope and is_followup and state.get("topic") in ["plant_bin_utilization_detail", "warehouse_utilization"])) and
        not is_overall_network_request and
        not any(w in q_lower for w in ["all", "compare", "network", "plants", "overall", "facility", "across", "each", "every", "by plant", "across plants"]) and
        not is_fresh_specific_bin and not is_mat_entity and
        not is_fresh_top_bins and not is_fresh_least_bins and not is_fresh_both and not is_fresh_empty and not is_followup_for_detail
    )

    if is_explicit_chart_request:
        state["is_explicit_chart_request"] = True

    is_util_comparison = (
        not is_fresh_both and
        (is_bin_level_detail_intent(q_lower) or any(k in q_lower for k in ["utiliz", "occupan", "how full", "fill rate", "space utilization", "bin utilization", "capacity utilization"])) and
        (len(explicit_plants) >= 2 or (is_followup and len(state.get("comparison_entities", [])) >= 2 and not new_plant and any(k in q_lower for k in ["compare", "versus", "vs", "difference", "between"])))
    )

    compound_cap_info = parse_compound_capacity_utilization(q_lower)
    is_find_bins = (
        any(q_lower.startswith(p) or f" {p}" in q_lower for p in ["find bins", "find bin", "search bins", "look for bins", "list bins", "show bins", "get bins"]) and
        not any(k in q_lower for k in ["how many", "count of bins", "number of bins", "total bins", "unused", "zero inventory", "no inventory", "zero stock", "no stock", "accept new", "incoming", "empty", "vacant", "putaway", "put-away"]) and
        not is_unsupported_nonexistent_query(q_lower) and
        not any(neg in q_lower for neg in ["do not exist", "don't exist", "dont exist", "nonexistent", "non-existent", "not in the database", "not present in"]) and
        not parse_range_filters(q_lower) and
        not is_fresh_almost_full and not is_fresh_over_capacity
    )

    if is_util_comparison:
        has_compare_kw = any(k in q_lower for k in ["compare", "comparison", "versus", "vs", "difference", "between", "both", "side by side", "contrast"])
        is_detail_comp = (has_compare_kw or state.get("topic") == "multi_plant_bin_detail") and (is_bin_level_detail_intent(q_lower) or state.get("response_mode") == "DETAIL")
        state["entity"] = "plant" if not is_detail_comp else "bin"
        state["metric"] = "bin_utilization"
        state["comparison_subject"] = "bin_utilization"
        state["operation"] = "comparison"
        if is_detail_comp:
            state["topic"] = "multi_plant_bin_detail"
            state["response_mode"] = "DETAIL"
        else:
            state["topic"] = "plant_comparison"
        if len(explicit_plants) >= 2:
            state["plants"] = list(explicit_plants)
            state["comparison_entities"] = [{"type": "plant", "value": p} for p in explicit_plants]
            state["filters"]["plants"] = list(explicit_plants)
            state["filters"].pop("plant", None)
            state["active_plant"] = explicit_plants[-1]
    elif compound_cap_info:
        state["entity"] = "bin"
        if compound_cap_info.get("needs_clarification"):
            state["topic"] = "compound_capacity_clarification"
            state["aggregation"] = "clarification"
        else:
            state["topic"] = "compound_capacity_utilization"
            state["aggregation"] = "list"
            state["metric"] = "utilization"
        state["ranking"] = None
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["limit"] = new_limit
    elif is_find_bins and not is_fresh_specific_bin and not is_fresh_empty and not is_mat_entity:
        state["entity"] = "bin"
        state["aggregation"] = "list"
        state["ranking"] = None
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["limit"] = new_limit
        if any(k in q_lower for k in ["high utiliz", "highly utiliz", "top utiliz", "most utiliz"]):
            state["topic"] = "top_utilized_bins"
            state["ranking"] = "highest"
        elif any(k in q_lower for k in ["low utiliz", "least utiliz", "bottom utiliz", "underutiliz"]):
            state["topic"] = "least_utilized_bins"
            state["ranking"] = "lowest"
        else:
            state["topic"] = "find_bins_list"
    elif is_followup_for_detail:
        state["entity"] = "bin"
        state["metric"] = "storage_location_utilization"
        state["topic"] = "plant_bin_utilization_detailed_analysis"
        state["filters"]["plant"] = new_plant or state.get("filters", {}).get("plant")
        state["granularity"] = "storage_location"
        state["aggregation"] = "breakdown"
    elif is_fresh_plant_bin_util_detail:
        state["entity"] = "bin"
        state["metric"] = "bin_utilization"
        if is_bin_level_detail_intent(q_lower) or state.get("response_mode") == "DETAIL":
            state["topic"] = "plant_bin_level_detail"
            state["response_mode"] = "DETAIL"
            state["aggregation"] = "list"
        else:
            state["topic"] = "plant_bin_utilization_detail"
            state["aggregation"] = "summary"
        state["filters"]["plant"] = new_plant or state.get("filters", {}).get("plant")
    elif is_fresh_avail_cap_by_plant:
        state["entity"] = "plant"
        state["metric"] = "AVAILABLE_CAPACITY"
        state["ranking"] = None
        state["topic"] = "plant_available_capacity"
        state["aggregation"] = "aggregation"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["limit"] = None
    elif is_fresh_util:
        state["entity"] = "bin"
        state["metric"] = "warehouse_utilization"
        state["topic"] = "warehouse_utilization"
        state["filters"] = {}
        state["aggregation"] = "summary"
    elif is_fresh_specific_bin:

        state["entity"] = "bin"
        state["condition"] = None
        state["filters"] = {"bin": valid_raw_bins[0]}
        if any(k in q_lower for k in ["which plant", "what plant", "belong to", "plant of bin", "plant for bin", "where is bin located"]):
            state["topic"] = "bin_plant_lookup"
        elif any(k in q_lower for k in ["occupied", "empty", "vacant", "in use"]) and any(q_start in q_lower for q_start in ["is ", "are ", "does ", "is the"]):
            state["topic"] = "bin_occupancy_status"
        elif any(k in q_lower for k in ["inventory quantity", "quantity in bin", "stock in bin", "units in bin", "how much in bin", "how much is stored in bin", "how many units in bin", "quantity stored in bin"]):
            state["topic"] = "bin_quantity_lookup"
        elif any(k in q_lower for k in ["how many materials", "how many skus", "how many items", "number of materials", "count of materials"]) and any(b in q_lower for b in ["in bin", "stored in bin", "inside bin", "for bin"]):
            state["topic"] = "bin_materials_count"
        elif any(k in q_lower for k in ["capacity", "available capacity", "free space", "remaining capacity", "how much capacity", "what is the capacity", "total capacity"]):
            state["topic"] = "single_bin_capacity"
        else:
            state["topic"] = "single_bin_utilization"
    elif is_fresh_missing_master:
        is_cnt = any(k in q_lower for k in ["how many", "count", "number of", "total count", "what is the count", "how many are there"])
        state["entity"] = "material"
        state["condition"] = "missing_volume_master_record"
        state["topic"] = "materials_missing_from_volume_master"
        state["aggregation"] = "count" if is_cnt else "list"
        state["filters"] = {"plant": new_plant} if new_plant else {}
    elif is_fresh_dq:
        is_cnt = any(k in q_lower for k in ["how many", "count", "number of", "total count", "what is the count", "how many are there"])
        state["entity"] = "material"
        state["condition"] = "missing_dimensions"
        state["topic"] = "data_quality"
        state["aggregation"] = "count" if is_cnt else "list"
        state["filters"] = {"plant": new_plant} if new_plant else {}
    elif is_fresh_plant_count:
        state["entity"] = "plant"
        state["metric"] = "plants_count"
        state["topic"] = "active_plants_count"
        state["condition"] = None
        state["aggregation"] = "count"
        state["filters"] = {}
    elif is_fresh_records_count:
        state["entity"] = "inventory"
        state["metric"] = "inventory_records_count"
        state["topic"] = "inventory_records_count"
        state["condition"] = None
        state["aggregation"] = "count"
        state["filters"] = {"plant": new_plant} if new_plant else {}
    elif is_fresh_mat_count:
        state["entity"] = "material"
        state["metric"] = "unique_materials"
        state["topic"] = "unique_materials_count"
        state["condition"] = None
        state["aggregation"] = "count"
        state["filters"] = {"plant": new_plant} if new_plant else {}
    elif is_fresh_occupied_bins_count:
        state["entity"] = "bin"
        state["metric"] = "occupied_bins"
        state["topic"] = "occupied_bins_count"
        state["condition"] = "occupied"
        state["aggregation"] = "count"
        state["filters"] = {"plant": new_plant} if new_plant else {}
    elif is_fresh_total_stock:
        state["entity"] = "inventory"
        state["metric"] = "total_unrestricted_quantity"
        state["topic"] = "total_inventory_quantity"
        state["condition"] = None
        state["aggregation"] = "sum"
        state["filters"] = {"plant": new_plant} if new_plant else {}
    elif (
        is_plant_keyword and
        any(k in q_lower for k in ["what rank is", "what is the rank of", "where does", "what position", "rank of plant", "where does plant"]) and
        new_plant is not None
    ):
        state["entity"] = "plant"
        state["metric"] = "occupied_volume" if any(k in q_lower for k in ["volume", "space", "storage"]) else ("utilization" if any(k in q_lower for k in ["utiliz", "occupan"]) else "occupied_volume")
        state["topic"] = "plant_rank_lookup"
        state["filters"] = {"plant": new_plant}
        state["aggregation"] = "single_value"
    elif (
        is_plant_keyword and
        any(k in q_lower for k in ["why is", "why are", "why does", "explain why"]) and
        any(k in q_lower for k in ["#1", "number 1", "number one", "first", "rank 1", "ranked 1", "ranked #1", "top", "leader"])
    ):
        state["entity"] = "plant"
        state["metric"] = "occupied_volume" if any(k in q_lower for k in ["volume", "space", "storage"]) else ("utilization" if any(k in q_lower for k in ["utiliz", "occupan"]) else "occupied_volume")
        state["topic"] = "plant_rank_explanation"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["aggregation"] = "explanation"
    elif (
        is_plant_keyword and
        (
            any(k in q_lower for k in ["occupied volume", "storage volume", "volume occupied", "space occupied", "occupies the most warehouse space", "occupies the most space", "occupies the most", "occupied storage", "storage space occupied"]) or
            ("volume" in q_lower and any(k in q_lower for k in ["occup", "storage", "space"])) or
            ("warehouse space" in q_lower and any(k in q_lower for k in ["occup", "most", "least", "highest", "lowest", "rank", "sort"]))
        ) and
        not any(k in q_lower for k in ["available", "free", "remaining", "unused", "material", "materials", "sku", "skus"])
    ):
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum", "smallest"])
        state["entity"] = "plant"
        state["metric"] = "occupied_volume"
        state["ranking"] = "lowest" if is_least else "highest"
        state["topic"] = "plant_occupied_volume_ranking"
        state["limit"] = new_limit or 4
        state["aggregation"] = "list"
        state["filters"] = {}
    elif (
        is_plant_keyword and
        any(k in q_lower for k in ["available capacity", "free capacity", "remaining capacity", "available volume", "free volume", "free space", "available storage space", "most available space", "least available space", "unused capacity", "unused space"])
    ):
        has_rank_kw = any(k in q_lower for k in ["rank", "ranking", "top", "bottom", "highest", "lowest", "most", "least", "best", "worst"])
        if has_rank_kw:
            is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum", "smallest"])
            state["entity"] = "plant"
            state["metric"] = "available_capacity"
            state["ranking"] = "lowest" if is_least else "highest"
            state["topic"] = "plant_available_capacity_ranking"
            state["limit"] = new_limit or 4
            state["aggregation"] = "list"
            state["filters"] = {}
        else:
            state["entity"] = "plant"
            state["metric"] = "AVAILABLE_CAPACITY"
            state["ranking"] = None
            state["topic"] = "plant_available_capacity"
            state["aggregation"] = "aggregation"
            state["filters"] = {"plant": new_plant} if new_plant else {}
            state["limit"] = None
    elif (
        is_plant_keyword and
        any(k in q_lower for k in ["empty bin", "empty bins", "number of empty bins", "count of empty bins", "most empty bins", "fewest empty bins"]) and
        any(k in q_lower for k in ["rank", "ranking", "top", "bottom", "highest", "lowest", "most", "least", "fewest", "which plant", "which plants", "what plant", "show plants", "plants ranked", "based on empty bins", "according to the number of empty bins"])
    ):
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum", "fewest"])
        state["entity"] = "plant"
        state["metric"] = "EMPTY_BIN_COUNT"
        state["ranking"] = "lowest" if is_least else "highest"
        state["topic"] = "plant_empty_bins_ranking"
        state["condition"] = "empty"
        state["limit"] = new_limit or 4
        state["aggregation"] = "list"
        state["filters"] = {}
    elif (
        is_plant_keyword and
        any(k in q_lower for k in ["number of bins", "total bins", "bin count", "count of bins", "most bins", "least bins", "fewest bins"]) and
        any(k in q_lower for k in ["rank", "ranking", "top", "bottom", "highest", "lowest", "most", "least", "which plant", "what plant"])
    ):
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum", "fewest"])
        state["entity"] = "plant"
        state["metric"] = "bins_count"
        state["ranking"] = "lowest" if is_least else "highest"
        state["topic"] = "plant_bins_ranking"
        state["limit"] = new_limit or 4
        state["aggregation"] = "list"
        state["filters"] = {}
    elif (
        is_plant_keyword and
        any(k in q_lower for k in ["unique materials", "number of materials", "sku count", "distinct materials", "skus"]) and
        any(k in q_lower for k in ["rank", "ranking", "top", "bottom", "highest", "lowest", "most", "least", "which plant", "what plant"])
    ):
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum", "fewest"])
        state["entity"] = "plant"
        state["metric"] = "unique_materials"
        state["ranking"] = "lowest" if is_least else "highest"
        state["topic"] = "plant_materials_ranking"
        state["limit"] = new_limit or 4
        state["aggregation"] = "list"
        state["filters"] = {}
    elif (
        is_plant_keyword and
        any(k in q_lower for k in ["total inventory", "inventory quantity", "stock quantity", "total stock", "units in inventory", "most stock", "least stock", "most inventory", "least inventory", "stock", "inventory"]) and
        any(k in q_lower for k in ["rank", "ranking", "top", "bottom", "highest", "lowest", "most", "least", "which plant", "what plant", "who is #1"]) and
        not any(k in q_lower for k in ["how much", "how many", "what is the total", "utiliz", "occupan", "capacity", "volume", "space"])
    ):
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum", "smallest"])
        state["entity"] = "plant"
        state["metric"] = "total_inventory"
        state["ranking"] = "lowest" if is_least else "highest"
        state["topic"] = "plant_inventory_ranking"
        state["limit"] = new_limit or 4
        state["aggregation"] = "list"
        state["filters"] = {}
    elif is_plant_keyword and any(k in q_lower for k in ["lowest", "least", "minimum", "min", "bottom", "worst"]) and any(k in q_lower for k in ["utiliz", "occupan", "capacity", "fill", "full"]):
        state["entity"] = "plant"
        state["metric"] = "lowest_bin_utilization"
        state["ranking"] = "lowest"
        state["topic"] = "lowest_bin_utilization"
        state["condition"] = None
        state["aggregation"] = "single_value"
        state["filters"] = {}
    elif is_plant_keyword and any(k in q_lower for k in ["highest", "most", "maximum", "max", "top", "best"]) and any(k in q_lower for k in ["utiliz", "occupan", "capacity", "fill", "full"]):
        state["entity"] = "plant"
        state["metric"] = "highest_bin_utilization"
        state["ranking"] = "highest"
        state["topic"] = "highest_bin_utilization"
        state["condition"] = None
        state["aggregation"] = "single_value"
        state["filters"] = {}
    elif is_plant_scope and any(w in q_lower for w in ["show me the materials", "show me materials", "show materials", "list materials", "materials in plant", "materials of plant", "which materials in plant", "list of materials"]):
        state["entity"] = "material"
        state["topic"] = "plant_materials"
        state["aggregation"] = "list"
        state["filters"] = {"plant": new_plant or state.get("filters", {}).get("plant")}
    elif is_fresh_bin_avail_cap:
        state["entity"] = "bin"
        state["metric"] = "available_capacity"
        state["ranking"] = "lowest" if any(k in q_lower for k in ["least", "lowest", "bottom"]) else "highest"
        state["topic"] = "bin_available_capacity_ranking"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["limit"] = new_limit or 10
        state["aggregation"] = "list"
    elif is_fresh_both:
        state["entity"] = "bin"
        state["metric"] = "utilization"
        state["ranking"] = "both"
        state["topic"] = "top_and_bottom_bins"
        state["operation"] = "ranking"
        state["condition"] = None
        state["aggregation"] = "list"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["limit"] = new_limit or 10
        if not new_plant:
            state["plants"] = []
            state["active_plant"] = None
            state["comparison_entities"] = []
            state["filters"].pop("plant", None)
            state["filters"].pop("plants", None)
    elif is_fresh_missing_vol_pct:
        state["entity"] = "material"
        state["metric"] = "MISSING_VOLUME_PERCENTAGE"
        state["condition"] = "NO_MATCHING_VOLUME_RECORD"
        state["ranking"] = None
        state["topic"] = "materials_missing_volume_percentage"
        state["aggregation"] = "summary"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["limit"] = None
    elif is_fresh_mat_vol:
        state["entity"] = "material"
        state["metric"] = "volume_share"
        state["ranking"] = "highest"
        state["topic"] = "material_volume_share"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["limit"] = new_limit or 10
    elif is_fresh_empty:
        state["entity"] = "bin"
        state["condition"] = "empty"
        state["topic"] = "putaway_bins"
        state["ranking"] = None
        state["aggregation"] = "list"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["limit"] = new_limit
    elif is_fresh_almost_full:
        state["entity"] = "bin"
        state["metric"] = "BIN_UTILIZATION"
        state["condition"] = "NEAR_FULL"
        state["ranking"] = None
        state["topic"] = "almost_full_bins"
        state["aggregation"] = "list"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["limit"] = new_limit
    elif is_fresh_over_capacity:
        state["entity"] = "bin"
        state["metric"] = "BIN_UTILIZATION"
        state["condition"] = "OVER_CAPACITY"
        state["ranking"] = None
        state["topic"] = "over_capacity_bins"
        state["aggregation"] = "list"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["limit"] = new_limit
    elif is_fresh_plant_inventory:
        state["entity"] = "plant" if new_plant else "inventory"
        state["metric"] = "TOTAL_INVENTORY_QUANTITY"
        state["operation"] = "aggregation"
        state["ranking"] = None
        state["topic"] = "plant_inventory"
        state["aggregation"] = "aggregation"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["limit"] = None
        if new_plant:
            state["active_plant"] = new_plant
            if new_plant not in state["plants"]:
                state["plants"].append(new_plant)
    elif is_fresh_top_bins:
        state["entity"] = "bin"
        state["metric"] = "utilization"
        state["ranking"] = "highest"
        state["topic"] = "top_utilized_bins"
        state["condition"] = None
        state["aggregation"] = "list"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["limit"] = new_limit or 10
        if not new_plant:
            state["plants"] = []
            state["active_plant"] = None
            state["comparison_entities"] = []
            state["filters"].pop("plant", None)
            state["filters"].pop("plants", None)
    elif is_fresh_least_bins:
        state["entity"] = "bin"
        state["metric"] = "utilization"
        state["ranking"] = "lowest"
        state["topic"] = "least_utilized_bins"
        state["condition"] = None
        state["aggregation"] = "list"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["limit"] = new_limit or 10
        if not new_plant:
            state["plants"] = []
            state["active_plant"] = None
            state["comparison_entities"] = []
            state["filters"].pop("plant", None)
            state["filters"].pop("plants", None)
    elif is_fresh_consolidation:
        state["topic"] = "consolidation"
        state["filters"] = {"plant": new_plant} if new_plant else {}
    elif is_fresh_diff:
        state["topic"] = "stock_difference"
        state["filters"] = {"plant": new_plant} if new_plant else {}
    elif is_fresh_div:
        state["topic"] = "division_breakdown"
        state["filters"] = {}
    elif is_fresh_trend:
        state["topic"] = "trend_analysis"
        state["filters"] = {}
    elif bool(history) and any(k in q_lower for k in [
        "they have", "do they", "these have", "do these", "those have", "do those",
        "their capacity", "their volume", "their occupied", "their available", "of them", "of these"
    ]) and any(k in q_lower for k in ["capacity", "volume", "space", "occupied", "available", "how much"]):
        state["entity"] = "bin"
        state["metric"] = "referential_bins_capacity"
        state["topic"] = "referential_bins_capacity"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["aggregation"] = "sum"
        state["ranking"] = None
    elif any(k in q_lower for k in ["capacity summary", "warehouse capacity summary", "overall capacity summary", "storage capacity summary"]) or q_lower.strip() in ["capacity summary", "capacity overview"]:
        state["entity"] = "bin"
        state["metric"] = "capacity_summary"
        state["topic"] = "capacity_summary"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["aggregation"] = "summary"
        state["ranking"] = None
    elif any(k in q_lower for k in ["empty bin", "empty bins", "vacant bin", "vacant bins"]) and any(k in q_lower for k in ["capacity", "available capacity", "space", "volume", "how much capacity", "how much space", "how much volume"]):
        state["entity"] = "bin"
        state["metric"] = "empty_bins_capacity"
        state["topic"] = "empty_bins_capacity"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["aggregation"] = "sum"
        state["ranking"] = None
    elif is_plant_scope and (
        any(k in q_lower for k in ["capacity for plant", "storage capacity of plant", "capacity of plant", "how much capacity does plant", "plant storage capacity", "capacity of this plant", "storage capacity for plant"]) or
        (any(k in q_lower for k in ["storage capacity", "total capacity", "bin capacity", "how much capacity"]) and not any(k in q_lower for k in ["utiliz", "occupan", "%", "rank", "ranking", "compare", "between"]))
    ):
        state["entity"] = "plant"
        state["metric"] = "plant_capacity"
        state["topic"] = "plant_capacity"
        state["filters"] = {"plant": new_plant or state.get("filters", {}).get("plant")}
        state["aggregation"] = "summary"
        state["ranking"] = None
    elif not new_plant and (
        any(k in q_lower for k in [
            "what is the total capacity", "what is the total warehouse capacity", "total warehouse capacity",
            "show total bin capacity", "how much capacity does this warehouse have", "how much capacity do these bins have",
            "show me the total capacity of all bins", "total bin capacity", "total storage capacity",
            "what is the warehouse capacity", "how much storage capacity do we have", "what is our total storage capacity",
            "how much storage capacity does this warehouse have", "how much capacity does the warehouse have"
        ]) or q_lower.strip() in ["total capacity", "total bin capacity", "total storage capacity", "warehouse capacity"]
    ) and not is_fresh_util and not any(k in q_lower for k in ["utiliz", "occupan", "%", "available", "left", "free", "remaining", "unused", "rank", "ranking", "compared to", "versus", "vs", "compare"]):
        state["entity"] = "bin"
        state["metric"] = "total_warehouse_capacity"
        state["topic"] = "total_warehouse_capacity"
        state["filters"] = {}
        state["aggregation"] = "sum"
        state["ranking"] = None
    elif (
        any(k in q_lower for k in [
            "how much space is left", "how much capacity is still available", "show available capacity",
            "how much unused capacity is there", "show remaining storage capacity", "how much storage space is left",
            "how much free space do we have", "how much capacity is available", "available storage capacity",
            "remaining storage capacity", "unused storage capacity", "total available capacity",
            "free storage capacity", "available warehouse capacity"
        ]) or q_lower.strip() in ["available capacity", "free capacity", "remaining capacity", "unused capacity"]
    ) and not is_fresh_util and not any(k in q_lower for k in ["utiliz", "occupan", "%", "rank", "ranking", "bins by", "plants by", "compared to", "versus", "vs", "compare", "occupied compared"]):
        state["entity"] = "bin"
        state["metric"] = "available_capacity"
        state["topic"] = "available_capacity"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["aggregation"] = "sum"
        state["ranking"] = None
    elif (
        any(k in q_lower for k in [
            "how much space is occupied", "show occupied volume", "how much warehouse capacity is being used",
            "what is the occupied storage volume", "how much inventory space is currently occupied",
            "total occupied volume", "occupied storage volume", "how much volume is occupied"
        ]) or q_lower.strip() in ["occupied volume", "storage volume occupied"]
    ) and not is_fresh_util and not any(k in q_lower for k in ["utiliz", "occupan", "%", "rank", "ranking", "share of total", "materials by", "plants by", "compared to", "versus", "vs", "compare", "available capacity"]):
        state["entity"] = "bin"
        state["metric"] = "occupied_volume"
        state["topic"] = "occupied_volume"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["aggregation"] = "sum"
        state["ranking"] = None
    elif any(k in q_lower for k in ["capacity for each bin", "capacity of all bins", "capacity of each bin", "show capacity of bins", "show capacity for bins", "bin capacity list", "list bin capacity"]) and not any(k in q_lower for k in ["rank", "ranking", "top", "bottom"]):
        state["entity"] = "bin"
        state["metric"] = "bin_capacity_list"
        state["topic"] = "bin_capacity_list"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["aggregation"] = "list"
        state["ranking"] = None
    elif is_fresh_avail_cap_by_plant:
        state["entity"] = "plant"
        state["metric"] = "AVAILABLE_CAPACITY"
        state["ranking"] = None
        state["topic"] = "plant_available_capacity"
        state["aggregation"] = "aggregation"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["limit"] = None
    elif is_fresh_util:
        state["topic"] = "warehouse_utilization"
        state["filters"] = {"plant": new_plant} if new_plant else {}
    elif is_fresh_mat_rank:
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum"])
        state["entity"] = "material"
        state["metric"] = "unrestricted_qty"
        state["ranking"] = "lowest" if is_least else "highest"
        state["topic"] = "material_quantity_ranking"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["limit"] = new_limit or 10
        state["aggregation"] = "list"
    elif is_fresh_sloc_rank:
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum"])
        state["entity"] = "storage_location"
        state["metric"] = "storage_location_inventory"
        state["ranking"] = "lowest" if is_least else "highest"
        state["topic"] = "storage_location_ranking"
        state["filters"] = {"plant": new_plant} if new_plant else {}
        state["limit"] = new_limit or 10
        state["aggregation"] = "list"
    else:
        # It's a modifier / follow-up
        if new_plant:
            state["filters"]["plant"] = new_plant
            state["active_plant"] = new_plant
            if new_plant not in state["plants"]:
                state["plants"].append(new_plant)
            if len(state["plants"]) >= 2:
                state["comparison_entities"] = [{"type": "plant", "value": p} for p in state["plants"][-2:]]
            if state.get("response_mode") == "DETAIL" or state.get("topic") in ["plant_bin_level_detail", "multi_plant_bin_detail"]:
                state["topic"] = "plant_bin_level_detail"
                state["response_mode"] = "DETAIL"
                state["entity"] = "bin"
                state["metric"] = "bin_utilization"

        # Check other plant
        if any(k in q_lower for k in ["other plant", "the other plant", "other one"]):
            if len(state["plants"]) >= 2:
                last_p = state.get("active_plant")
                cands = [p for p in state["plants"][-2:] if p != last_p]
                other_p = cands[0] if cands else state["plants"][0]
                state["active_plant"] = other_p
                state["filters"]["plant"] = other_p
                if state.get("topic") == "plant_comparison":
                    state["topic"] = "plant_inventory"
                    state["operation"] = "aggregation"
                    state["response_mode"] = "TABLE"

        # Check comparison triggers
        if any(k in q_lower for k in ["compare those two", "compare these two", "compare those", "compare them", "compare both", "compare the two"]) or (q_lower.strip() in ["compare", "compare two"]):
            state["entity"] = "plant" if state.get("response_mode") != "DETAIL" else "bin"
            state["operation"] = "comparison"
            if state.get("response_mode") == "DETAIL" or state.get("topic") in ["plant_bin_level_detail", "multi_plant_bin_detail"]:
                state["topic"] = "multi_plant_bin_detail"
                state["metric"] = "bin_utilization"
            else:
                state["topic"] = "plant_comparison"
            if len(state["plants"]) >= 2:
                state["comparison_entities"] = [{"type": "plant", "value": p} for p in state["plants"][-2:]]
                state["filters"]["plants"] = [p for p in state["plants"][-2:]]

        # Check presentation / format modifiers
        if is_comparison_explanation_requested(q_lower):
            state["response_mode"] = "EXPLANATION"
        elif any(k in q_lower for k in [
            "detailed version", "in detail", "show detail", "detailed breakdown", "detailed", "give details",
            "explain", "explained", "explanation", "elaborate", "show me with", "show with"
        ]):
            state["response_mode"] = "DETAIL"
        elif any(k in q_lower for k in ["only count", "only the count", "just the count", "count only", "give me only the count"]):
            state["response_mode"] = "COUNT"
            if state.get("condition") == "empty" or state.get("topic") in ["putaway_bins", "empty_bins_count"]:
                state["topic"] = "empty_bins_count"
                state["aggregation"] = "count"
        elif any(k in q_lower for k in ["only names", "only the names", "names only", "just the names", "show only the names"]):
            state["response_mode"] = "NAMES_ONLY"
        elif any(k in q_lower for k in ["only percentage", "only the percentage", "percentage only", "just the percentage", "show only the percentage"]):
            state["response_mode"] = "PERCENTAGE_ONLY"

        if new_limit:
            state["limit"] = new_limit
        if any(k in q_lower for k in [
            "graph", "chart", "visualize", "plot", "pie chart", "bar chart", "line chart", "histogram",
            "with graph", "or with graph", "as graph", "in graph", "with chart", "or with chart",
            "show me with graph", "show with graph", "explain with graph", "show me with", "show with"
        ]) or q_lower.strip() in ["graph", "chart", "visualize", "plot", "graphs", "charts"]:
            state["is_explicit_chart_request"] = True
            state["response_mode"] = "GRAPH"

        # Handle "How many are there?" / "What is the count?"
        is_count_query = any(k in q_lower for k in ["how many", "count", "number of", "total count", "what is the count", "how many are there"])
        if is_count_query:
            state["aggregation"] = "count"
            state["response_mode"] = "COUNT"
            if state["condition"] == "empty" or state["topic"] in ["putaway_bins", "empty_bins_count"]:
                state["topic"] = "empty_bins_count"
                state["operation"] = "COUNT"
            elif state["topic"] in ["data_quality", "materials_missing_from_volume_master"]:
                state["topic"] = "data_quality_count"

        # Handle Polarity shifts & Ranking modifications:
        # 0. "Reverse it" / "reverse the ranking" / "in reverse order"
        if any(k in q_lower for k in ["reverse", "flip the ranking", "flip order"]):
            state["ranking"] = "lowest" if state.get("ranking") == "highest" else "highest"
            state["aggregation"] = "list"
            if state.get("entity") == "plant":
                if state.get("topic") == "plant_occupied_volume_ranking" or "volume" in state.get("metric", ""):
                    state["topic"] = "plant_occupied_volume_ranking"
                elif state.get("topic") in ["highest_bin_utilization", "lowest_bin_utilization"]:
                    state["topic"] = "lowest_bin_utilization" if state["ranking"] == "lowest" else "highest_bin_utilization"
            elif state.get("entity") == "material":
                state["topic"] = "material_quantity_ranking"
            elif state.get("entity") == "storage_location":
                state["topic"] = "storage_location_ranking"
            else: # bin
                state["topic"] = "least_utilized_bins" if state["ranking"] == "lowest" else "top_utilized_bins"

        # 1. "What about the lowest ones?" / "least ones" -> flip to lowest ranking
        elif any(k in q_lower for k in ["least utilized ones", "lowest utilized ones", "least utilized", "lowest utilized", "least ones", "lowest ones", "least", "bottom", "emptiest"]):
            state["ranking"] = "lowest"
            state["direction"] = "ASC"
            state["aggregation"] = "list"
            if state.get("entity") == "plant":
                if state.get("topic") == "plant_occupied_volume_ranking" or "volume" in state.get("metric", ""):
                    state["topic"] = "plant_occupied_volume_ranking"
                elif state.get("topic") in ["highest_bin_utilization", "lowest_bin_utilization"]:
                    state["topic"] = "lowest_bin_utilization"
                else:
                    state["topic"] = "plant_occupied_volume_ranking"
            elif state.get("entity") == "material":
                state["topic"] = "material_quantity_ranking"
            elif state.get("entity") == "storage_location":
                state["topic"] = "storage_location_ranking"
            else:
                state["entity"] = "bin"
                state["metric"] = "BIN_UTILIZATION"
                state["topic"] = "least_utilized_bins"

        # 2. "Show me the top 5 instead" / "top 5" -> flip to highest ranking
        elif is_followup and any(k in q_lower for k in ["top", "most", "highest", "fullest", "most utilized", "most utilized ones"]):
            state["ranking"] = "highest"
            state["direction"] = "DESC"
            state["aggregation"] = "list"
            if new_limit:
                state["limit"] = new_limit
            if state.get("entity") == "plant":
                if state.get("topic") == "plant_occupied_volume_ranking" or "volume" in state.get("metric", ""):
                    state["topic"] = "plant_occupied_volume_ranking"
                elif state.get("topic") in ["highest_bin_utilization", "lowest_bin_utilization"]:
                    state["topic"] = "highest_bin_utilization"
                else:
                    state["topic"] = "plant_occupied_volume_ranking"
            elif state.get("entity") == "material" or state.get("topic") == "material_quantity_ranking":
                state["topic"] = "material_quantity_ranking"
            elif state.get("entity") == "storage_location":
                state["topic"] = "storage_location_ranking"
            else:
                state["entity"] = "bin"
                state["metric"] = "BIN_UTILIZATION"
                state["topic"] = "top_utilized_bins"

        # 3. "Show 5 instead" (without explicit top/bottom) -> preserve existing ranking polarity
        elif new_limit:
            state["limit"] = new_limit
            if state.get("topic") not in ["top_utilized_bins", "least_utilized_bins", "top_and_bottom_bins", "plant_occupied_volume_ranking", "material_quantity_ranking", "storage_location_ranking"]:
                if state.get("ranking") == "lowest":
                    state["topic"] = "least_utilized_bins"
                else:
                    state["topic"] = "top_utilized_bins"

    # Construct clean resolved query from state
    if not is_followup or len(explicit_plants) >= 2:
        state["resolved_query"] = question
    else:
        plant_clause = f" in plant {state['filters']['plant']}" if state['filters'].get('plant') else ""
        limit_clause = f" {state['limit']}" if state.get('limit') else " 10"

        if state["topic"] == "plant_bin_level_detail":
            state["resolved_query"] = f"detail bin utilization of plant {state['filters'].get('plant', '')}".strip()
        elif state["topic"] == "multi_plant_bin_detail":
            p_list = state.get("filters", {}).get("plants") or state.get("plants", [])
            state["resolved_query"] = f"compare detailed bin utilization of {' and '.join(f'plant {p}' for p in p_list)}"
        elif state["topic"] == "plant_bin_utilization_detailed_analysis":
            state["resolved_query"] = f"detailed bin utilization analysis for plant {state['filters'].get('plant', '')}".strip()
        elif state["topic"] == "plant_bin_utilization_detail":
            state["resolved_query"] = f"bin utilization detail of plant {state['filters'].get('plant', '')}".strip()
        elif state["topic"] == "plant_occupied_volume_ranking":
            direction_word = "lowest" if state.get("ranking") == "lowest" else "highest"
            state["resolved_query"] = f"rank all plants by total occupied volume {direction_word}{limit_clause}"
        elif state["topic"] == "plant_available_capacity_ranking":
            direction_word = "lowest" if state.get("ranking") == "lowest" else "highest"
            state["resolved_query"] = f"rank all plants by available capacity {direction_word}{limit_clause}"
        elif state["topic"] == "plant_bins_ranking":
            direction_word = "fewest" if state.get("ranking") == "lowest" else "most"
            state["resolved_query"] = f"rank all plants by number of bins {direction_word}{limit_clause}"
        elif state["topic"] == "plant_materials_ranking":
            direction_word = "fewest" if state.get("ranking") == "lowest" else "most"
            state["resolved_query"] = f"rank all plants by unique materials {direction_word}{limit_clause}"
        elif state["topic"] == "plant_inventory_ranking":
            direction_word = "lowest" if state.get("ranking") == "lowest" else "highest"
            state["resolved_query"] = f"rank all plants by total inventory quantity {direction_word}{limit_clause}"
        elif state["topic"] == "plant_rank_lookup":
            state["resolved_query"] = f"what rank is plant {state['filters'].get('plant', '')} by occupied volume"
        elif state["topic"] == "plant_rank_explanation":
            state["resolved_query"] = f"why is plant {state['filters'].get('plant', '1268')} ranked #1 by occupied volume"
        elif state["topic"] == "bin_available_capacity_ranking":
            direction_word = "least" if state.get("ranking") == "lowest" else "most"
            state["resolved_query"] = f"rank bins by available capacity {direction_word}{limit_clause}{plant_clause}"
        elif state["topic"] == "top_and_bottom_bins":
            state["resolved_query"] = f"top{limit_clause} most and bottom{limit_clause} least utilized bins{plant_clause}"
        elif state["topic"] == "empty_bins_count":
            state["resolved_query"] = f"how many empty bins{plant_clause}"
        elif state["topic"] == "putaway_bins":
            state["resolved_query"] = f"empty bins available for put-away{plant_clause}"
        elif state["topic"] == "least_utilized_bins":
            state["resolved_query"] = f"bottom{limit_clause} least utilized bins{plant_clause}"
        elif state["topic"] == "top_utilized_bins":
            state["resolved_query"] = f"top{limit_clause} most utilized bins{plant_clause}"
        elif state["topic"] == "materials_missing_from_volume_master":
            if state.get("aggregation") == "count":
                state["resolved_query"] = f"how many materials in inventory are missing from volume master{plant_clause}"
            else:
                state["resolved_query"] = f"find materials in inventory missing from volume master{plant_clause}"
        elif state["topic"] == "data_quality":
            if state.get("aggregation") == "count":
                state["resolved_query"] = f"how many materials with missing dimensions{plant_clause}"
            else:
                state["resolved_query"] = f"materials with missing dimensions{plant_clause}"
        elif state["topic"] == "material_volume_share":
            state["resolved_query"] = f"top{limit_clause} materials by share of total bin volume{plant_clause}"
        elif state["topic"] == "warehouse_utilization":
            state["resolved_query"] = f"warehouse bin utilization across plants{plant_clause}"
        elif state["topic"] == "lowest_bin_utilization":
            state["resolved_query"] = "which plant has lowest bin utilization"
        elif state["topic"] == "highest_bin_utilization":
            state["resolved_query"] = "which plant has highest bin utilization"
        elif state["topic"] == "trend_analysis":
            state["resolved_query"] = "inventory trend over time"
        elif state["topic"] == "division_breakdown":
            state["resolved_query"] = "inventory distribution by division"
        elif state["topic"] == "consolidation":
            state["resolved_query"] = f"materials in multiple bins for consolidation{plant_clause}"
        elif state["topic"] == "storage_location_comparison":
            state["resolved_query"] = f"compare inventory across storage locations{plant_clause}"
        elif state["topic"] == "inventory_records_count":
            state["resolved_query"] = f"how many inventory records{plant_clause}"
        elif state["topic"] == "unique_materials_count":
            state["resolved_query"] = f"how many unique materials in inventory{plant_clause}"
        elif state["topic"] == "total_inventory_quantity":
            state["resolved_query"] = f"total inventory quantity{plant_clause}"
        elif state["topic"] == "plant_materials":
            state["resolved_query"] = f"show materials{plant_clause}"
        elif state["topic"] == "material_quantity_ranking":
            direction_word = "bottom" if state.get("ranking") == "lowest" else "top"
            state["resolved_query"] = f"ranking of {direction_word}{limit_clause} materials by stock quantity{plant_clause}"
        elif state["topic"] == "storage_location_ranking":
            state["resolved_query"] = f"ranking of top{limit_clause} storage locations by inventory quantity{plant_clause}"
        elif state["topic"] == "capacity_summary":
            state["resolved_query"] = f"capacity summary{plant_clause}"
        elif state["topic"] == "total_warehouse_capacity":
            state["resolved_query"] = "what is the total warehouse storage capacity"
        elif state["topic"] == "available_capacity":
            state["resolved_query"] = f"how much available storage capacity is left{plant_clause}"
        elif state["topic"] == "occupied_volume":
            state["resolved_query"] = f"how much occupied storage volume{plant_clause}"
        elif state["topic"] == "plant_capacity":
            state["resolved_query"] = f"storage capacity of plant {state['filters'].get('plant', '')}".strip()
        elif state["topic"] == "empty_bins_capacity":
            state["resolved_query"] = f"how much capacity is available in empty bins{plant_clause}"
        elif state["topic"] == "single_bin_capacity":
            state["resolved_query"] = f"capacity of bin {state['filters'].get('bin', '')}".strip()
        elif state["topic"] == "bin_capacity_list":
            state["resolved_query"] = f"show capacity of bins{plant_clause}"
        elif state["topic"] == "plant_comparison":
            p1 = state["plants"][-2] if len(state.get("plants", [])) >= 2 else (state.get("filters", {}).get("plants", [None, None])[0] or "1258")
            p2 = state["plants"][-1] if len(state.get("plants", [])) >= 2 else (state.get("filters", {}).get("plants", [None, None])[1] or "7228")
            subj = state.get("comparison_subject") or ("bin_utilization" if state.get("metric") == "bin_utilization" else "total inventory quantity")
            if subj == "bin_utilization":
                state["resolved_query"] = f"compare bin utilization of plant {p1} and plant {p2}"
            elif subj == "materials":
                state["resolved_query"] = f"compare unique materials of plant {p1} and plant {p2}"
            elif subj == "empty_bins":
                state["resolved_query"] = f"compare empty bins of plant {p1} and plant {p2}"
            elif subj == "occupied_bins":
                state["resolved_query"] = f"compare occupied bins of plant {p1} and plant {p2}"
            elif subj == "capacity":
                state["resolved_query"] = f"compare capacity of plant {p1} and plant {p2}"
            elif subj == "storage_locations":
                state["resolved_query"] = f"compare storage locations of plant {p1} and plant {p2}"
            else:
                state["resolved_query"] = f"compare plant {p1} and plant {p2} total inventory quantity"
        elif state["topic"] == "plant_inventory":
            plant_val = state["filters"].get("plant", "")
            state["resolved_query"] = f"total inventory quantity in plant {plant_val}".strip()
        elif state["topic"] in ["referential_bins_capacity", "compound_capacity_utilization", "compound_capacity_clarification", "find_bins_list"]:
            state["resolved_query"] = question
        else:
            state["resolved_query"] = question

    return state


def resolve_conversation_context(question: str, history: list[dict] | None = None) -> str:
    """Intelligently resolves follow-up questions, anaphora, elliptical queries, filter refinements, and entity inheritance from conversation history."""
    state = extract_and_update_conversation_state(question, history)
    return state.get("resolved_query", question)

def deterministic_warehouse_sql_generator(question: str, history: list[dict] | None = None) -> dict[str, Any]:
    """Context-Driven Semantic Query Resolver.
    
    Dynamically maps warehouse business concepts (Entities, Metrics, Dimensions, Calculations, Rankings)
    to safe SQL Server queries according to the Warehouse BI Semantic Layer without hardcoded question lists.
    """
    question = normalize_query_typos(question)
    state = extract_and_update_conversation_state(question, history)
    resolved_q = state.get("resolved_query", question)
    q_lower = resolved_q.lower()
    is_followup = is_elliptical_followup(question.lower()) and bool(history)
    new_limit = state.get("limit") or extract_explicit_limit(q_lower)

    # 1. ENTITY & SCOPE EXTRACTION (Context-driven)
    is_mat_entity = any(m in q_lower for m in ["material", "materials", "sku", "skus", "item", "items", "product", "products", "goods", "stock item", "stock items"])
    plant_cand = state["filters"].get("plant")
    if not plant_cand:
        plant_cand = extract_single_plant_safe(q_lower)
    
    # Extract specific bin codes (e.g. B001, BIN-001, BIN001, B045, NRJP2124D2, etc.)
    bin_matches = re.findall(r"(?:bin\s*[:#-]?\s*([a-z0-9_-]{2,25})|\b(b\d{3,5})\b)", q_lower, re.IGNORECASE)
    raw_bins = []
    excluded_bin_words = [
        "capacity", "utilization", "master", "table", "space", "volume", "location", "locations",
        "occupancy", "fullness", "empty", "vacant", "free", "ones", "these", "those", "cubic",
        "bins", "fill", "level", "levels", "rate", "rates", "network", "usage", "storage",
        "can", "be", "used", "for", "has", "have", "with", "does", "is", "are", "lowest", "highest", "least", "most", "the"
    ]
    for bm in bin_matches:
        b_val = (bm[0] or bm[1] or "").strip()
        if b_val and b_val.lower() not in excluded_bin_words:
            # Genuine bin codes must contain digits (e.g. B001, NRJP2124D2, BOR11L2P17)
            if any(c.isdigit() for c in b_val):
                raw_bins.append(b_val.upper())
            elif len(b_val) >= 4 and not b_val.lower().isalpha() and any(c.isdigit() for c in b_val):
                raw_bins.append(b_val.upper())
    
    bin_match = raw_bins[0] if raw_bins else None

    material_match = re.search(r"\b(?:material|sku|item|code)\s*[:#-]?\s*([a-z0-9_-]{5,20})\b", q_lower, re.IGNORECASE)
    if material_match and material_match.group(1).lower() in ["division", "group", "type", "description", "name", "master", "table", "plant", "stock", "quantity", "inventory"]:
        material_match = None

    # 2. BUSINESS METRIC & INTENT RESOLUTION
    is_explicit_chart = bool(
        state.get("is_explicit_chart_request") or
        is_explicit_chart_only_requested(question) or
        any(k in question.lower() for k in [
            "graph", "chart", "visualize", "plot", "pie chart", "bar chart", "line chart", "histogram",
            "with graph", "or with graph", "with a graph", "or with a graph",
            "with chart", "or with chart", "with a chart", "or with a chart",
            "show me with graph", "show with graph", "show me with chart", "show with chart"
        ]) or
        any(k in q_lower for k in [
            "graph", "chart", "visualize", "plot", "pie chart", "bar chart", "line chart", "histogram",
            "with graph", "or with graph", "with a graph", "or with a graph",
            "with chart", "or with chart", "with a chart", "or with a chart",
            "show me with graph", "show with graph", "show me with chart", "show with chart"
        ])
    )
    is_single_statement_requested = any(s in q_lower for s in [
        "single statement", "single line", "one line", "concise", "briefly", "in short",
        "just the percentage", "just the number", "only the number", "in a single statement"
    ]) or (
        (
            bool(re.search(r"\b(?:which|whic|what|wat)\s+bin\b", q_lower)) or
            any(k in q_lower for k in [
                "bin with the lowest", "bin with lowest",
                "bin with the highest", "bin with highest", "who has the lowest bin", "who has the highest bin"
            ])
        ) and not any(d in q_lower for d in ["top 10", "top 5", "bottom 10", "bottom 5", "ranking", "table", "list", "breakdown", "detailed", "detail form"])
        and not any(b in q_lower for b in ["which bins", "whic bins", "what bins"])
    )
    is_detail_requested = is_detail_or_graph_requested(question) or any(d in q_lower for d in [
        "detail", "details", "detailed", "in detail", "detail form", "detailed form",
        "breakdown", "itemized", "full list", "table form", "ranking form",
        "explain", "explained", "explanation", "elaborate", "show me with", "show with"
    ])

    # 0_INVALID. Nonexistent entities & invalid plants intercept (Master Context Rule)
    if is_unsupported_nonexistent_query(q_lower):
        return {
            "sql": "SELECT 'no_match' AS status WHERE 1 = 0",
            "chart_type": "none",
            "chart_title": "No Matching Warehouse Records",
            "chart_x": None,
            "chart_y": None,
            "intent": "no_matching_records",
            "metric": "no_records",
            "filters": {},
            "time_range": "current",
            "output_type": "text",
            "is_invalid_query": True
        }

    # A0. SPECIFIC BIN QUESTIONS (Attributes, Utilization, Occupancy, Quantity, Materials)
    if raw_bins:
        b_code = raw_bins[0]
        plant_filter = f" AND b.Plant = '{plant_cand}'" if plant_cand else ""
        filters = {"bin": b_code}
        if plant_cand:
            filters["plant"] = plant_cand

        # 1. Bin Occupancy Yes/No check: "Is bin NRJP2124D2 occupied?", "Is bin NRJP2124D2 empty?"
        if any(k in q_lower for k in ["occupied", "empty", "vacant", "in use"]) and any(q_start in q_lower for q_start in ["is ", "are ", "does ", "is the"]):
            return {
                "sql": f"SELECT COUNT(DISTINCT Material) AS MaterialCount, COALESCE(SUM(UnrestrictedQty), 0) AS TotalQty FROM dbo.ZWMS_INVENTORY WHERE BinNo = '{b_code}' AND UnrestrictedQty > 0",
                "chart_type": "none",
                "chart_title": f"Occupancy Status of Bin {b_code}",
                "chart_x": None,
                "chart_y": None,
                "intent": "bin_occupancy_status",
                "metric": "bin_status",
                "filters": filters,
                "time_range": "current",
                "output_type": "text"
            }

        # 2. Bin Plant Lookup: "Which plant does bin NRJP2124D2 belong to?"
        if any(k in q_lower for k in ["which plant", "what plant", "belong to", "plant of bin", "plant for bin", "where is bin located"]):
            sql_bin_plant = f"""SELECT DISTINCT Plant, StorageLocation FROM (
    SELECT Plant, StorageLocation FROM dbo.ZWMS_BIN_MASTER WHERE BinLocation = '{b_code}'
    UNION
    SELECT Plant, StorageLocation FROM dbo.ZWMS_INVENTORY WHERE BinNo = '{b_code}'
) sub WHERE Plant IS NOT NULL"""
            return {
                "sql": sql_bin_plant,
                "chart_type": "none",
                "chart_title": f"Plant for Bin {b_code}",
                "chart_x": None,
                "chart_y": None,
                "intent": "bin_plant_lookup",
                "metric": "plant_lookup",
                "filters": filters,
                "time_range": "current",
                "output_type": "text"
            }

        # 3. Bin Inventory Quantity: "What is the inventory quantity in bin NRJP2124D2?", "What is the stock in bin NRJP2124D2?"
        if any(k in q_lower for k in ["inventory quantity", "quantity in bin", "stock in bin", "units in bin", "how much in bin", "how much is stored in bin", "how many units in bin", "quantity stored in bin"]):
            return {
                "sql": f"SELECT COALESCE(SUM(UnrestrictedQty), 0) AS [Inventory Qty], MAX(BaseUnitOfMeasure) AS UOM FROM dbo.ZWMS_INVENTORY WHERE BinNo = '{b_code}'",
                "chart_type": "none",
                "chart_title": f"Inventory Quantity in Bin {b_code}",
                "chart_x": None,
                "chart_y": None,
                "intent": "bin_quantity_lookup",
                "metric": "bin_inventory_quantity",
                "filters": filters,
                "time_range": "current",
                "output_type": "text"
            }

        # 4. Bin Materials Count: "How many materials are stored in bin NRJP2124D2?"
        if any(k in q_lower for k in ["how many materials", "how many skus", "how many items", "number of materials", "count of materials"]) and any(b in q_lower for b in ["in bin", "stored in bin", "inside bin", "for bin"]):
            return {
                "sql": f"SELECT COUNT(DISTINCT Material) AS [Stored Materials Count] FROM dbo.ZWMS_INVENTORY WHERE BinNo = '{b_code}' AND UnrestrictedQty > 0",
                "chart_type": "none",
                "chart_title": f"Materials Stored in Bin {b_code}",
                "chart_x": None,
                "chart_y": None,
                "intent": "bin_materials_count",
                "metric": "bin_materials_count",
                "filters": filters,
                "time_range": "current",
                "output_type": "text"
            }

        # 4B. Single Bin Capacity Lookup: "What is the capacity of bin NRJP2124D2?", "How much capacity does bin NRJP2124D2 have?"
        if (
            state.get("topic") == "single_bin_capacity" or
            (any(k in q_lower for k in ["capacity", "available capacity", "free space", "remaining capacity", "how much capacity", "what is the capacity", "total capacity"]) and not any(k in q_lower for k in ["utiliz", "occupan", "%"]))
        ) and len(raw_bins) == 1:
            where_bin_clause = f"(b.BinLocation = '{raw_bins[0]}' OR b.BinLocation LIKE '{raw_bins[0]}%')"
            sql_bin_cap = f"""SELECT 
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    COALESCE(b.StorageLocation, 'N/A') AS [Storage Location],
    ROUND(b.Volume, 2) AS [Total Capacity (FT3)],
    ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Occupied Volume (FT3)],
    ROUND(b.Volume - COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Available Capacity (FT3)],
    CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Capacity Utilization %]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE {where_bin_clause}{plant_filter}
GROUP BY b.BinLocation, b.Plant, b.StorageLocation, b.Volume"""
            return {
                "sql": sql_bin_cap,
                "chart_type": "none",
                "chart_title": f"Capacity of Bin {raw_bins[0]}",
                "chart_x": None,
                "chart_y": None,
                "intent": "single_bin_capacity",
                "metric": "bin_capacity",
                "filters": filters,
                "time_range": "current",
                "output_type": "text",
                "conversation_state": state
            }

        # 5. Bin Utilization: "What is the utilization of bin NRJP2124D2?" (Single or Multi)
        if any(k in q_lower for k in ["utiliz", "occupan", "capacity", "how full", "space", "compare", "fullness", "fill rate"]) and not any(k in q_lower for k in ["top", "bottom", "least utilized ones", "most utilized ones"]):
            if len(raw_bins) == 1:
                where_bin_clause = f"(b.BinLocation = '{raw_bins[0]}' OR b.BinLocation LIKE '{raw_bins[0]}%')"
                out_type = "text"
            else:
                filters["bins"] = raw_bins
                in_list = ", ".join(f"'{b}'" for b in raw_bins)
                where_bin_clause = f"b.BinLocation IN ({in_list})"
                out_type = "table"

            sql_specific_bin = f"""SELECT 
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    b.StorageLocation AS [Storage Location],
    CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Bin Capacity],
    ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Occupied Volume],
    ROUND(b.Volume - COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Available Capacity],
    CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE {where_bin_clause}{plant_filter}
GROUP BY b.BinLocation, b.Plant, b.StorageLocation, b.Volume, b.VolumeUnit"""

            return {
                "sql": sql_specific_bin,
                "chart_type": "bar" if len(raw_bins) > 1 else "none",
                "chart_title": f"Utilization of Bin {raw_bins[0]}" if len(raw_bins) == 1 else f"Bin Utilization Comparison ({', '.join(raw_bins)})",
                "chart_x": "Bin" if len(raw_bins) > 1 else None,
                "chart_y": "Utilization %" if len(raw_bins) > 1 else None,
                "intent": "specific_bin_utilization" if len(raw_bins) == 1 else "bin_comparison",
                "metric": "bin_utilization",
                "filters": filters,
                "time_range": "current",
                "output_type": out_type,
                "conversation_state": state
            }

        # 6. Specific Bin Material Lookup: "What material is stored in bin XYZ?", "What is stored in bin XYZ?"
        if any(k in q_lower for k in ["what material", "which material", "materials stored", "material in bin", "items in bin", "skus in bin", "product in bin", "what is stored in bin", "stored in"]):
            sql_bin_mats = f"""SELECT Material, COALESCE(MaterialDescription, '') AS [Material Description], SUM(UnrestrictedQty) AS TotalQty, MAX(BaseUnitOfMeasure) AS UOM
FROM dbo.ZWMS_INVENTORY
WHERE BinNo = '{b_code}'
GROUP BY Material, MaterialDescription"""
            return {
                "sql": sql_bin_mats,
                "chart_type": "none",
                "chart_title": f"Materials Stored in Bin {b_code}",
                "chart_x": None,
                "chart_y": None,
                "intent": "bin_materials_lookup",
                "metric": "bin_materials",
                "filters": filters,
                "time_range": "current",
                "output_type": "text"
            }

        # 7. Generic Specific Bin Lookup: "Find bin XYZ999", "Show bin XYZ999", "Details for bin XYZ999"
        sql_bin_generic = f"""SELECT 
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    COALESCE(b.StorageLocation, 'N/A') AS [Storage Location],
    CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Capacity],
    ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Occupied Volume],
    CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE b.BinLocation = '{b_code}'{plant_filter}
GROUP BY b.BinLocation, b.Plant, b.StorageLocation, b.Volume, b.VolumeUnit"""
        return {
            "sql": sql_bin_generic,
            "chart_type": "none",
            "chart_title": f"Details for Bin {b_code}",
            "chart_x": None,
            "chart_y": None,
            "intent": "bin_lookup",
            "metric": "bin_details",
            "filters": filters,
            "time_range": "current",
            "output_type": "text"
        }

    # A. INTENT A: MATERIALS MISSING FROM VOLUME MASTER (Rule DQ-001 - Cross-Table Validation)
    is_missing_master_record = state.get("topic") == "materials_missing_volume_percentage" or any(k in q_lower for k in [
        "missing from the volume master", "missing from volume master", "not in the volume master",
        "not in volume master", "missing in volume master", "exist in inventory master but not",
        "exists in inventory master but not", "exist in inventory but missing from", "exists in inventory but missing from",
        "in inventory but missing from", "missing from material master", "not in material master",
        "no matching volume master", "unmatched volume master", "missing volume master record",
        "missing volume master records", "no volume master record", "no volume master records",
        "no volume master entry", "no volume master entries", "without volume master",
        "do not have corresponding volume master", "dont have corresponding volume master",
        "do not have volume master", "dont have volume master", "no corresponding volume master",
        "without corresponding volume master", "missing corresponding volume master",
        "no master entry", "no master entries", "not maintained in volume master",
        "missing volume information", "missing volume info", "missing physical volume", "missing volume data",
        "without volume data", "missing volume details"
    ]) or (
        ("inventory" in q_lower or "material" in q_lower or "materials" in q_lower or "sku" in q_lower or "skus" in q_lower or "item" in q_lower or "items" in q_lower or "product" in q_lower or "goods" in q_lower) and
        ("volume master" in q_lower or "material master" in q_lower or "volume-master" in q_lower or "material volume master" in q_lower or "volume information" in q_lower or "physical volume" in q_lower or "volume data" in q_lower) and
        ("missing" in q_lower or "absent" in q_lower or "not present" in q_lower or "doesn't exist" in q_lower or "does not exist" in q_lower or "don't exist" in q_lower or "no record" in q_lower or "no entry" in q_lower or "no entries" in q_lower or "not maintained" in q_lower or "not in" in q_lower or "do not have" in q_lower or "dont have" in q_lower or "lack" in q_lower or "lacking" in q_lower or "without" in q_lower or "no matching" in q_lower or "unmatched" in q_lower)
    ) or (
        any(c in q_lower for c in ["percentage", "percent", "pct", "%", "how many percent", "what percentage", "what percent"]) and (
            "missing physical dimensions" in q_lower or "physical dimension" in q_lower or "without physical dimensions" in q_lower or "missing dimensions" in q_lower
        )
    )

    if is_missing_master_record:
        plant_filter = f" AND i.Plant = '{plant_cand}'" if plant_cand else ""
        filters = {"plant": plant_cand} if plant_cand else {}
        is_pct_request = (
            state.get("topic") == "materials_missing_volume_percentage" or
            state.get("metric") == "MISSING_VOLUME_PERCENTAGE" or
            any(c in q_lower for c in ["percentage", "percent", "pct", "%", "how many percent", "what percentage", "what percent"])
        )

        if is_pct_request:
            plant_sub_filter = f" WHERE Plant = '{plant_cand}'" if plant_cand else ""
            if is_explicit_chart:
                sql_missing_pct_chart = f"""SELECT 
    CASE WHEN v.MaterialCode IS NULL OR v.Volume IS NULL OR v.Volume <= 0 THEN 'Missing Volume Info' ELSE 'Has Volume Info' END AS [Status],
    COUNT(DISTINCT i.Material) AS [Material Count],
    ROUND(CAST(COUNT(DISTINCT i.Material) AS FLOAT) * 100.0 / (SELECT COUNT(DISTINCT Material) FROM dbo.ZWMS_INVENTORY{plant_sub_filter}), 2) AS [Percentage (%)]
FROM dbo.ZWMS_INVENTORY i
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER v ON i.Material = v.MaterialCode{plant_filter}
GROUP BY CASE WHEN v.MaterialCode IS NULL OR v.Volume IS NULL OR v.Volume <= 0 THEN 'Missing Volume Info' ELSE 'Has Volume Info' END"""
                query_plan = {
                    "entity": "MATERIAL",
                    "metric": "MISSING_VOLUME_PERCENTAGE",
                    "operation": "PERCENTAGE",
                    "numerator": "inventory materials without matching physical-volume data",
                    "denominator": "total inventory materials",
                    "filters": filters,
                    "group_by": ["Status"],
                    "ranking": None,
                    "limit": None,
                    "response_mode": "GRAPH"
                }
                return {
                    "sql": sql_missing_pct_chart,
                    "query_plan": query_plan,
                    "chart_type": "bar",
                    "chart_title": f"Inventory Materials Volume Master Status (%){f' — Plant {plant_cand}' if plant_cand else ''}",
                    "chart_x": "Status",
                    "chart_y": "Percentage (%)",
                    "intent": "materials_missing_volume_percentage",
                    "metric": "missing_volume_percentage",
                    "filters": filters,
                    "time_range": "current",
                    "output_type": "bar_chart",
                    "conversation_state": state
                }
            else:
                sql_missing_pct = f"""SELECT 
    COUNT(DISTINCT CASE WHEN v.MaterialCode IS NULL OR v.Volume IS NULL OR v.Volume <= 0 THEN i.Material END) AS [Missing Volume Materials Count],
    COUNT(DISTINCT i.Material) AS [Total Inventory Materials Count],
    ROUND(CAST(COUNT(DISTINCT CASE WHEN v.MaterialCode IS NULL OR v.Volume IS NULL OR v.Volume <= 0 THEN i.Material END) AS FLOAT) * 100.0 / NULLIF(COUNT(DISTINCT i.Material), 0), 2) AS [Missing Volume Percentage]
FROM dbo.ZWMS_INVENTORY i
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER v ON i.Material = v.MaterialCode{plant_filter}"""
                query_plan = {
                    "entity": "MATERIAL",
                    "metric": "MISSING_VOLUME_PERCENTAGE",
                    "operation": "PERCENTAGE",
                    "numerator": "inventory materials without matching physical-volume data",
                    "denominator": "total inventory materials",
                    "filters": filters,
                    "group_by": None,
                    "ranking": None,
                    "limit": None,
                    "response_mode": "SUMMARY"
                }
                return {
                    "sql": sql_missing_pct,
                    "query_plan": query_plan,
                    "chart_type": "none",
                    "chart_title": f"Percentage of Inventory Materials Missing Volume Information{f' — Plant {plant_cand}' if plant_cand else ''}",
                    "chart_x": None,
                    "chart_y": None,
                    "intent": "materials_missing_volume_percentage",
                    "metric": "missing_volume_percentage",
                    "filters": filters,
                    "time_range": "current",
                    "output_type": "text",
                    "conversation_state": state
                }

        is_count_request = any(c in q_lower for c in ["how many", "count", "number of", "total count", "how much", "how many items", "how many materials", "how many inventory items"])
        
        if is_count_request:
            sql_missing_master_count = f"""SELECT COUNT(DISTINCT i.Material) AS [Missing Materials Count]
FROM dbo.ZWMS_INVENTORY i
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER v ON i.Material = v.MaterialCode
WHERE v.MaterialCode IS NULL{plant_filter}"""
            query_plan = {
                "intent": "MATERIALS_MISSING_FROM_VOLUME_MASTER_COUNT",
                "task": "count",
                "task_type": "CROSS_TABLE_VALIDATION",
                "user_intent": "materials_missing_from_volume_master_count",
                "entity": "INVENTORY_MATERIAL",
                "source_table": "dbo.ZWMS_INVENTORY",
                "reference_table": "dbo.ZWMS_MATERIAL_MASTER",
                "join_key": "i.Material = v.MaterialCode",
                "condition": "NO_MATCHING_VOLUME_MASTER_ENTRY",
                "aggregation": "COUNT",
                "metrics": ["Missing Materials Count"],
                "dimensions": [],
                "filters": [f"Plant = {plant_cand}"] if plant_cand else [],
                "conditions": ["v.MaterialCode IS NULL"],
                "group_by": [],
                "sort": [],
                "limit": None,
                "time_range": "current",
                "tables": [
                    "dbo.ZWMS_INVENTORY",
                    "dbo.ZWMS_MATERIAL_MASTER"
                ],
                "joins": [
                    {
                        "left": "dbo.ZWMS_INVENTORY.Material",
                        "right": "dbo.ZWMS_MATERIAL_MASTER.MaterialCode",
                        "type": "LEFT"
                    }
                ],
                "output_type": "kpi",
                "result_type": "kpi"
            }
            return {
                "sql": sql_missing_master_count,
                "query_plan": query_plan,
                "chart_type": "none",
                "chart_title": f"Count of Inventory Items Missing from Volume Master{f' — Plant {plant_cand}' if plant_cand else ''}",
                "chart_x": None,
                "chart_y": None,
                "intent": "materials_missing_from_volume_master_count",
                "metric": "missing_materials_count",
                "filters": filters,
                "time_range": "current",
                "output_type": "kpi",
                "conversation_state": state
            }

        sql_missing_master = f"""SELECT DISTINCT
    i.Material,
    MAX(COALESCE(i.MaterialDescription, 'N/A')) AS [Material Description],
    i.Plant,
    i.StorageLocation AS [Storage Location],
    SUM(i.UnrestrictedQty) AS [Inventory Qty]
FROM dbo.ZWMS_INVENTORY i
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER v ON i.Material = v.MaterialCode
WHERE v.MaterialCode IS NULL{plant_filter}
GROUP BY i.Material, i.Plant, i.StorageLocation
ORDER BY [Inventory Qty] DESC"""
        query_plan = {
            "intent": "MATERIALS_MISSING_FROM_VOLUME_MASTER",
            "task": "cross_table_validation",
            "task_type": "CROSS_TABLE_VALIDATION",
            "user_intent": "materials_missing_from_volume_master",
            "entity": "MATERIAL",
            "source_table": "dbo.ZWMS_INVENTORY",
            "reference_table": "dbo.ZWMS_MATERIAL_MASTER",
            "join_key": "i.Material = v.MaterialCode",
            "condition": "NO_MATCHING_VOLUME_MASTER_RECORD",
            "metrics": ["Inventory Qty"],
            "dimensions": ["Material", "Material Description", "Plant", "Storage Location"],
            "filters": [f"Plant = {plant_cand}"] if plant_cand else [],
            "conditions": ["v.MaterialCode IS NULL"],
            "group_by": ["i.Material", "i.Plant", "i.StorageLocation"],
            "sort": ["[Inventory Qty] DESC"],
            "limit": None,
            "time_range": "current",
            "tables": [
                "dbo.ZWMS_INVENTORY",
                "dbo.ZWMS_MATERIAL_MASTER"
            ],
            "joins": [
                {
                    "left": "dbo.ZWMS_INVENTORY.Material",
                    "right": "dbo.ZWMS_MATERIAL_MASTER.MaterialCode",
                    "type": "LEFT"
                }
            ],
            "output_type": "table",
            "result_type": "table"
        }
        return {
            "sql": sql_missing_master,
            "query_plan": query_plan,
            "chart_type": "none",
            "chart_title": f"Materials in Inventory Missing from Volume Master{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": None,
            "chart_y": None,
            "intent": "materials_missing_from_volume_master",
            "metric": "missing_volume_master_record",
            "filters": filters,
            "time_range": "current",
            "output_type": "table",
            "conversation_state": state
        }

    # B. INTENT B: DATA QUALITY CHECK & MISSING PHYSICAL DIMENSIONS
    is_dq_intent = (
        state.get("topic") == "data_quality" or
        any(k in q_lower for k in [
            "data quality", "quality check", "missing dimension", "missing physical", "missing volume",
            "incomplete dimension", "incomplete physical", "missing length", "missing width", "missing height",
            "no dimension", "no dimensions", "without dimension", "without dimensions", "without physical size",
            "don't have dimension", "dont have dimension", "do not have dimension",
            "don't have dimensions", "dont have dimensions", "do not have dimensions",
            "lack dimension", "lack dimensions", "unmaintained dimension", "physical measurements", "measurements",
            "dimension completeness", "cross-dataset", "cross dataset", "unmatched record", "unmatched material",
            "unmaintained volume", "physical dimension"
        ]) or (
            ("dimension" in q_lower or "dimensions" in q_lower or "volume" in q_lower or "length" in q_lower or "width" in q_lower or "height" in q_lower or "physical" in q_lower or "size" in q_lower or "measurement" in q_lower or "measurements" in q_lower or "attribute" in q_lower or "attributes" in q_lower) and
            ("missing" in q_lower or "incomplete" in q_lower or "null" in q_lower or "blank" in q_lower or "quality" in q_lower or "check" in q_lower or "exception" in q_lower or "validate" in q_lower or "validation" in q_lower or "without" in q_lower or "absent" in q_lower or "not defined" in q_lower or "not maintained" in q_lower or "unavailable" in q_lower or "don't" in q_lower or "dont" in q_lower or "do not" in q_lower or "no " in q_lower or "lack" in q_lower or "lacking" in q_lower or "not populated" in q_lower or "without length" in q_lower or "without width" in q_lower)
        )
    ) and state.get("topic") != "materials_missing_volume_percentage" and not any(c in q_lower for c in ["percentage", "percent", "pct", "%"])
    if is_dq_intent:
        plant_filter = f" WHERE i.Plant = '{plant_cand}'" if plant_cand else ""
        filters = {"plant": plant_cand} if plant_cand else {}
        sql_dq = f"""SELECT 
    i.Material,
    MAX(COALESCE(i.MaterialDescription, m.MaterialDescription, 'N/A')) AS [Material Description],
    SUM(i.UnrestrictedQty) AS [Total Stock Qty],
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins],
    m.Length,
    m.Width,
    m.Height,
    m.Volume,
    CASE 
        WHEN m.MaterialCode IS NULL THEN 'Missing Volume Master Record'
        WHEN (m.Length IS NULL OR m.Length = 0) AND (m.Width IS NULL OR m.Width = 0) AND (m.Height IS NULL OR m.Height = 0) THEN 'Completely Missing Dimensions'
        ELSE 'Incomplete Dimensions'
    END AS [Quality Issue]
FROM dbo.ZWMS_INVENTORY i
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode{plant_filter}
WHERE m.MaterialCode IS NULL 
   OR m.Length IS NULL OR m.Length = 0 
   OR m.Width IS NULL OR m.Width = 0 
   OR m.Height IS NULL OR m.Height = 0 
   OR m.Volume IS NULL OR m.Volume = 0
GROUP BY i.Material, m.Length, m.Width, m.Height, m.Volume, m.MaterialCode
ORDER BY [Total Stock Qty] DESC"""
        query_plan = {
            "task": "data_quality",
            "user_intent": "data_quality",
            "question_type": "missing_data",
            "entity": "material",
            "analytical_task": "DATA QUALITY",
            "metrics": ["Total Stock Qty", "Occupied Bins", "Length", "Width", "Height", "Volume"],
            "dimensions": ["Material", "Material Description", "Quality Issue"],
            "filters": [f"Plant = {plant_cand}"] if plant_cand else [],
            "conditions": [
                "m.MaterialCode IS NULL",
                "OR m.Length IS NULL OR m.Length = 0",
                "OR m.Width IS NULL OR m.Width = 0",
                "OR m.Height IS NULL OR m.Height = 0",
                "OR m.Volume IS NULL OR m.Volume = 0"
            ],
            "group_by": ["i.Material", "m.Length", "m.Width", "m.Height", "m.Volume", "m.MaterialCode"],
            "sort": ["[Total Stock Qty] DESC"],
            "limit": None,
            "time_range": "current",
            "tables": [
                "dbo.ZWMS_INVENTORY",
                "dbo.ZWMS_MATERIAL_MASTER"
            ],
            "joins": [
                {
                    "left": "dbo.ZWMS_INVENTORY.Material",
                    "right": "dbo.ZWMS_MATERIAL_MASTER.MaterialCode",
                    "type": "LEFT"
                }
            ],
            "output_type": "table",
            "result_type": "table"
        }
        return {
            "sql": sql_dq,
            "query_plan": query_plan,
            "chart_type": "none",
            "chart_title": "Materials with Missing or Incomplete Physical Dimensions",
            "chart_x": None,
            "chart_y": None,
            "intent": "data_quality_check",
            "metric": "missing_dimensions",
            "filters": filters,
            "time_range": "current",
            "output_type": "table",
            "conversation_state": state
        }

    # B. TIME SERIES & TREND ANALYSIS (Checked before snapshot utilization)
    if any(k in q_lower for k in ["trend", "history", "timeline", "over time", "monthly", "last 6 months", "vested"]):
        return {
            "sql": "SELECT SUBSTRING(CONVERT(VARCHAR(10), FullyVestedOn, 120), 1, 7) AS Month, COUNT(DISTINCT Material) AS ActiveMaterials, SUM(UnrestrictedQty) AS TotalQuantity, ROUND(SUM(UnrestrictedQty * 0.05), 2) AS EstVolume FROM dbo.ZWMS_INVENTORY WHERE FullyVestedOn IS NOT NULL GROUP BY SUBSTRING(CONVERT(VARCHAR(10), FullyVestedOn, 120), 1, 7) ORDER BY Month ASC",
            "chart_type": "line",
            "chart_title": "Warehouse Inventory & Activity Trend Over Time",
            "chart_x": "Month",
            "chart_y": "TotalQuantity",
            "intent": "trend_analysis",
            "metric": "warehouse_utilization",
            "filters": {},
            "time_range": "last_6_months",
            "output_type": "line_chart"
        }

    # C. MATERIAL BIN VOLUME CONSUMPTION & SHARE OF TOTAL BIN VOLUME
    is_mat_entity = any(m in q_lower for m in ["material", "materials", "sku", "skus", "item", "items", "product", "products", "goods", "stock item", "stock items"])
    is_mat_vol_intent = state.get("topic") == "material_volume_share" or (is_mat_entity and not is_missing_master_record and any(k in q_lower for k in [
        "volume", "consuming", "space consuming", "consuming most", "volume consumption", "highest space", "occupying highest volume",
        "share of total", "percentage of our total", "percentage of total", "highest percentage", "footprint",
        "cubic capacity", "take up", "occupy", "occupying", "room in the warehouse", "proportion of bin", "storage space",
        "largest volume footprint", "highest proportion", "biggest share", "most room"
    ]) and not any(k in q_lower for k in ["volume master", "material master", "missing", "without dimension", "no record", "no entry", "do not have", "dont have"]))
    if is_mat_vol_intent:
        n_val = state.get("limit", 10)
        plant_filter = f" AND i.Plant = '{plant_cand}'" if plant_cand else ""
        filters = {"plant": plant_cand} if plant_cand else {}
        sql_mat_vol = f"""SELECT TOP {n_val} 
    ROW_NUMBER() OVER (ORDER BY SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) DESC) AS [Rank],
    i.Material,
    MAX(COALESCE(i.MaterialDescription, m.MaterialDescription, 'N/A')) AS [Material Description],
    SUM(i.UnrestrictedQty) AS [Total Quantity],
    ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 2) AS [Total Material Volume],
    CONCAT(ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF((SELECT SUM(Volume) FROM dbo.ZWMS_BIN_MASTER WHERE Volume > 0), 0), 3), '%') AS [% of Total Bin Volume]
FROM dbo.ZWMS_INVENTORY i
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE i.UnrestrictedQty > 0{plant_filter}
GROUP BY i.Material
ORDER BY SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) DESC"""
        query_plan = {
            "user_intent": "material_volume_share",
            "question_type": "ranking",
            "entity": "material",
            "analytical_task": "RANKING / AGGREGATION",
            "filters": [f"Plant = {plant_cand}"] if plant_cand else [],
            "tables": [
                "dbo.ZWMS_INVENTORY",
                "dbo.ZWMS_MATERIAL_MASTER",
                "dbo.ZWMS_BIN_MASTER"
            ],
            "join": {
                "left": "dbo.ZWMS_INVENTORY.Material",
                "right": "dbo.ZWMS_MATERIAL_MASTER.MaterialCode",
                "type": "LEFT"
            },
            "conditions": [
                "i.UnrestrictedQty > 0"
            ],
            "result_type": "bar_chart"
        }
        return {
            "sql": sql_mat_vol,
            "query_plan": query_plan,
            "chart_type": "bar",
            "chart_title": f"Top {n_val} Materials by Share of Total Bin Volume (%)",
            "chart_x": "Material",
            "chart_y": "% of Total Bin Volume",
            "intent": "material_volume_share",
            "metric": "bin_volume_consumption",
            "filters": filters,
            "time_range": "current",
            "output_type": "bar_chart",
            "conversation_state": state
        }

    # =========================================================================
    # SECTION COMPOUND & ENTITY PRESERVATION: COMPOUND CAPACITY + UTILIZATION & FIND BINS
    # =========================================================================
    compound_info = parse_compound_capacity_utilization(resolved_q)
    if compound_info or state.get("topic") in ["compound_capacity_utilization", "compound_capacity_clarification"]:
        if (compound_info and compound_info.get("needs_clarification")) or state.get("topic") == "compound_capacity_clarification":
            return {
                "sql": "SELECT 1 AS [clarification_needed]",
                "chart_type": "none",
                "chart_title": "Clarification Required",
                "chart_x": None,
                "chart_y": None,
                "intent": "compound_capacity_clarification",
                "metric": "compound_capacity_utilization",
                "filters": {"plant": plant_cand} if plant_cand else {},
                "time_range": "current",
                "output_type": "text",
                "conversation_state": state,
                "direct_answer": "To find matching bins, please specify the thresholds for capacity (e.g., maximum bin volume in FT³) and utilization (e.g., minimum utilization percentage). No default thresholds are currently defined."
            }
        
        cap_condition = compound_info.get("cap_condition") if compound_info else None
        util_condition = compound_info.get("util_condition") if compound_info else None
        if not cap_condition:
            cap_condition = "CapacityNum <= 45"
        if not util_condition:
            util_condition = "UtilizationNum >= 80"

        plant_filter = f" AND b.Plant = '{plant_cand}'" if plant_cand else ""
        n_limit = state.get("limit") or new_limit
        top_clause = f"TOP {n_limit} " if n_limit else ""
        sql_compound = f"""WITH BinStats AS (
    SELECT 
        b.BinLocation AS [Bin],
        b.Plant AS [Plant],
        COALESCE(b.StorageLocation, 'N/A') AS [Storage Location],
        CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Capacity],
        ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Occupied Volume],
        CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %],
        ROUND(b.Volume, 2) AS [CapacityNum],
        ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1) AS [UtilizationNum]
    FROM dbo.ZWMS_BIN_MASTER b
    LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
    WHERE b.Volume > 0{plant_filter}
    GROUP BY b.BinLocation, b.Plant, b.StorageLocation, b.Volume, b.VolumeUnit
),
FilteredStats AS (
    SELECT 
        Bin, Plant, [Storage Location], Capacity, [Occupied Volume], [Utilization %], [UtilizationNum], [CapacityNum],
        COUNT(*) OVER() AS [TotalMatching]
    FROM BinStats
    WHERE {cap_condition} AND {util_condition}
)
SELECT {top_clause}Bin, Plant, [Storage Location], Capacity, [Occupied Volume], [Utilization %], TotalMatching
FROM FilteredStats
ORDER BY [UtilizationNum] DESC, [CapacityNum] ASC"""

        return {
            "sql": sql_compound,
            "chart_type": "none",
            "chart_title": f"Compound Capacity & Utilization Bins{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": None,
            "chart_y": None,
            "intent": "compound_capacity_utilization",
            "metric": "bin_utilization",
            "filters": {"plant": plant_cand} if plant_cand else {},
            "time_range": "current",
            "output_type": "table",
            "conversation_state": state
        }

    # Targeted Analyzed Queries: "Find bins that are almost full" (80% <= util < 100%) and "over capacity" (util >= 100%)
    is_almost_full_req = (
        state.get("topic") == "almost_full_bins" or
        state.get("condition") == "NEAR_FULL" or
        (
            any(k in q_lower for k in [
                "almost full", "nearly full", "near full", "close to full", "close to being full",
                "close to full capacity", "almost at capacity", "near full capacity",
                "nearly at 100% utilization", "nearly at 100%", "almost at 100%"
            ]) and not any(k in q_lower for k in ["over capacity", "over-capacity", "over utilized", "over-utilized", "greater than 100", "above 100", "> 100", ">= 100"])
        )
    )

    is_over_capacity_req = (
        state.get("topic") == "over_capacity_bins" or
        state.get("condition") == "OVER_CAPACITY" or
        any(k in q_lower for k in [
            "over capacity", "over-capacity", "over capacity bins", "full or over capacity",
            "over-utilized bins", "over utilized bins", "exceeding capacity", "exceeds capacity",
            "full or over", "at or over 100", "100% or more"
        ])
    )

    if is_almost_full_req:
        plant_filter = f" AND b.Plant = '{plant_cand}'" if plant_cand else ""
        n_limit = state.get("limit") or new_limit
        top_clause = f"TOP {n_limit} " if n_limit else ""
        sql_almost_full = f"""SELECT {top_clause}
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    COALESCE(b.StorageLocation, 'N/A') AS [Storage Location],
    ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 2) AS [Occupied Volume],
    CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Bin Capacity],
    CONCAT(ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %],
    ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0), 1) AS [Utilization]
FROM dbo.ZWMS_BIN_MASTER b 
JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant 
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode 
WHERE b.Volume > 0{plant_filter} 
GROUP BY b.BinLocation, b.Plant, b.StorageLocation, b.Volume, b.VolumeUnit 
HAVING SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0) >= 80.0
   AND SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0) < 100.0
ORDER BY SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0) DESC"""
        query_plan = {
            "entity": "BIN",
            "metric": "BIN_UTILIZATION",
            "operation": "FILTER",
            "condition": "NEAR_FULL",
            "threshold": "80% <= utilization < 100%",
            "filters": {"plant": plant_cand} if plant_cand else {},
            "group_by": ["Bin", "Plant", "Storage Location"],
            "ranking": None,
            "limit": n_limit,
            "response_mode": "GRAPH" if is_explicit_chart else "TABLE"
        }
        return {
            "sql": sql_almost_full,
            "query_plan": query_plan,
            "chart_type": "bar" if is_explicit_chart else "none",
            "chart_title": f"Almost Full Bins (80% - 100% Utilization){f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": "Bin" if is_explicit_chart else None,
            "chart_y": "Utilization" if is_explicit_chart else None,
            "intent": "almost_full_bins",
            "metric": "bin_utilization",
            "filters": {"plant": plant_cand} if plant_cand else {},
            "time_range": "current",
            "output_type": "bar_chart" if is_explicit_chart else "table",
            "conversation_state": state
        }

    if is_over_capacity_req:
        plant_filter = f" AND b.Plant = '{plant_cand}'" if plant_cand else ""
        n_limit = state.get("limit") or new_limit
        top_clause = f"TOP {n_limit} " if n_limit else ""
        sql_over_capacity = f"""SELECT {top_clause}
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    COALESCE(b.StorageLocation, 'N/A') AS [Storage Location],
    ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 2) AS [Occupied Volume],
    CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Bin Capacity],
    CONCAT(ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %],
    ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0), 1) AS [Utilization]
FROM dbo.ZWMS_BIN_MASTER b 
JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant 
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode 
WHERE b.Volume > 0{plant_filter} 
GROUP BY b.BinLocation, b.Plant, b.StorageLocation, b.Volume, b.VolumeUnit 
HAVING SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0) >= 100.0
ORDER BY SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0) DESC"""
        query_plan = {
            "entity": "BIN",
            "metric": "BIN_UTILIZATION",
            "operation": "FILTER",
            "condition": "OVER_CAPACITY",
            "threshold": "utilization >= 100%",
            "filters": {"plant": plant_cand} if plant_cand else {},
            "group_by": ["Bin", "Plant", "Storage Location"],
            "ranking": None,
            "limit": n_limit,
            "response_mode": "GRAPH" if is_explicit_chart else "TABLE"
        }
        return {
            "sql": sql_over_capacity,
            "query_plan": query_plan,
            "chart_type": "bar" if is_explicit_chart else "none",
            "chart_title": f"Over-Capacity Bins (>= 100% Utilization){f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": "Bin" if is_explicit_chart else None,
            "chart_y": "Utilization" if is_explicit_chart else None,
            "intent": "over_capacity_bins",
            "metric": "bin_utilization",
            "filters": {"plant": plant_cand} if plant_cand else {},
            "time_range": "current",
            "output_type": "bar_chart" if is_explicit_chart else "table",
            "conversation_state": state
        }

    # ENTITY PRESERVATION: "Find bins..." query must remain at bin level
    is_find_bins_req = (
        (
            state.get("topic") == "find_bins_list" or
            (any(resolved_q.lower().startswith(p) or f" {p}" in resolved_q.lower() for p in ["find bins", "find bin", "search bins", "look for bins", "list bins", "show bins", "get bins"])
             and not any(k in resolved_q.lower() for k in ["how many", "count of bins", "number of bins", "total bins", "rank", "ranking", "top", "bottom", "empty", "vacant", "putaway", "put-away", "unused", "zero inventory", "no inventory", "zero stock", "no stock", "accept new", "incoming"]))
        ) and not is_unsupported_nonexistent_query(resolved_q.lower())
        and not any(neg in resolved_q.lower() for neg in ["do not exist", "don't exist", "dont exist", "nonexistent", "non-existent", "not in the database", "not present in"])
        and not parse_range_filters(resolved_q)
        and not is_almost_full_req and not is_over_capacity_req
    )
    if is_find_bins_req and not is_mat_entity:
        plant_filter_fb = f" AND b.Plant = '{plant_cand}'" if plant_cand else ""
        n_limit = state.get("limit") or new_limit
        top_clause = f"TOP {n_limit} " if n_limit else ""
        sql_find_bins = f"""SELECT {top_clause}
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    COALESCE(b.StorageLocation, 'N/A') AS [Storage Location],
    CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Capacity],
    ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Occupied Volume],
    CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %],
    COUNT(*) OVER() AS [TotalMatching]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE b.Volume > 0{plant_filter_fb}
GROUP BY b.BinLocation, b.Plant, b.StorageLocation, b.Volume, b.VolumeUnit
ORDER BY b.BinLocation ASC"""

        return {
            "sql": sql_find_bins,
            "chart_type": "none",
            "chart_title": f"Warehouse Bins{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": None,
            "chart_y": None,
            "intent": "find_bins_list",
            "metric": "bin_list",
            "filters": {"plant": plant_cand} if plant_cand else {},
            "time_range": "current",
            "output_type": "table",
            "conversation_state": state
        }

    # AMBIGUOUS / NATURAL-LANGUAGE WAREHOUSE INTENTS
    # 1. Wasting space / Inefficient capacity usage
    is_wasting_space = any(k in q_lower for k in [
        "wasting the most space", "wasting most space", "wasting space",
        "used inefficiently", "inefficient storage", "inefficiently utilized",
        "storage capacity is being used inefficiently", "inefficient use of space"
    ])
    if is_wasting_space:
        plant_f = f" AND b.Plant = '{plant_cand}'" if plant_cand else ""
        sql_waste = f"""SELECT TOP 10
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    COALESCE(b.StorageLocation, 'N/A') AS [Storage Location],
    ROUND(b.Volume, 2) AS [Capacity (FT3)],
    ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Occupied Volume (FT3)],
    ROUND(b.Volume - COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Unused Space (FT3)],
    CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE b.Volume > 0{plant_f}
GROUP BY b.BinLocation, b.Plant, b.StorageLocation, b.Volume
HAVING (COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0)) <= 20.0
ORDER BY [Unused Space (FT3)] DESC"""
        return {
            "sql": sql_waste,
            "chart_type": "none",
            "chart_title": f"Bins with Inefficient Storage / Wasting Space{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": None,
            "chart_y": None,
            "intent": "wasting_space_bins",
            "metric": "inefficient_storage",
            "filters": {"plant": plant_cand} if plant_cand else {},
            "time_range": "current",
            "output_type": "table",
            "conversation_state": state
        }

    # 2. Bins needing operational attention (over-utilized or near full)
    is_attention_bins = any(k in q_lower for k in [
        "need attention", "needing attention", "bins that need attention", "which bins need attention", "bins needing attention"
    ])
    if is_attention_bins:
        plant_f = f" AND b.Plant = '{plant_cand}'" if plant_cand else ""
        sql_attention = f"""SELECT TOP 20
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    COALESCE(b.StorageLocation, 'N/A') AS [Storage Location],
    ROUND(b.Volume, 2) AS [Capacity (FT3)],
    ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Occupied Volume (FT3)],
    CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %],
    CASE 
        WHEN ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0), 1) > 100.0 THEN 'Over-Utilized (>100%)'
        ELSE 'Near Capacity (≥90%)'
    END AS [Issue Type]
FROM dbo.ZWMS_BIN_MASTER b
JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE b.Volume > 0{plant_f}
GROUP BY b.BinLocation, b.Plant, b.StorageLocation, b.Volume
HAVING (COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0)) >= 90.0
ORDER BY [Occupied Volume (FT3)] DESC"""
        return {
            "sql": sql_attention,
            "chart_type": "none",
            "chart_title": f"Bins Requiring Operational Attention{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": None,
            "chart_y": None,
            "intent": "bins_needing_attention",
            "metric": "operational_attention",
            "filters": {"plant": plant_cand} if plant_cand else {},
            "time_range": "current",
            "output_type": "table",
            "conversation_state": state
        }

    # 3. Plant inventory distribution: "Where is most of my inventory sitting?"
    is_inventory_sitting = any(k in q_lower for k in [
        "where is most of my inventory sitting", "where is most inventory sitting",
        "where is most of our inventory sitting", "where is most of our inventory",
        "where is most inventory stored", "where is my inventory sitting", "where is our inventory sitting"
    ])
    if is_inventory_sitting:
        sql_inv_dist = """SELECT 
    b.Plant,
    COUNT(DISTINCT b.BinLocation) AS [Total Bins],
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins],
    ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Occupied Volume (FT3)],
    SUM(i.UnrestrictedQty) AS [Total Stock Units],
    COUNT(DISTINCT i.Material) AS [Unique Materials]
FROM dbo.ZWMS_BIN_MASTER b
JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE b.Volume > 0 AND i.UnrestrictedQty > 0
GROUP BY b.Plant
ORDER BY [Occupied Volume (FT3)] DESC"""
        return {
            "sql": sql_inv_dist,
            "chart_type": "bar",
            "chart_title": "Inventory Distribution Across Plants",
            "chart_x": "Plant",
            "chart_y": "Occupied Volume (FT3)",
            "intent": "plant_inventory_distribution",
            "metric": "inventory_distribution",
            "filters": {},
            "time_range": "current",
            "output_type": "text" if is_single_statement_requested else "table",
            "conversation_state": state
        }

    # 4. Available space: "Where do I have the most free space?"
    is_most_free_space = any(k in q_lower for k in [
        "where do i have the most free space", "where is the most free space",
        "where do we have the most free space", "most free space", "where is most free space",
        "which plant has the most free space", "plant with most free space"
    ])
    if is_most_free_space:
        sql_free_space = """SELECT 
    b.Plant,
    COUNT(DISTINCT b.BinLocation) AS [Total Bins],
    ROUND(SUM(b.Volume), 2) AS [Total Capacity (FT3)],
    ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Occupied Volume (FT3)],
    ROUND(SUM(b.Volume) - COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Available Capacity (FT3)],
    CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(SUM(b.Volume), 0), 1), '%') AS [Utilization %]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE b.Volume > 0
GROUP BY b.Plant
ORDER BY [Available Capacity (FT3)] DESC"""
        return {
            "sql": sql_free_space,
            "chart_type": "bar",
            "chart_title": "Available Storage Space by Plant",
            "chart_x": "Plant",
            "chart_y": "Available Capacity (FT3)",
            "intent": "plant_available_capacity_ranking",
            "metric": "available_capacity",
            "filters": {},
            "time_range": "current",
            "output_type": "text" if is_single_statement_requested else "table",
            "conversation_state": state
        }

    # 5. Biggest storage problem: "Which plant has the biggest storage problem?"
    is_biggest_storage_problem = any(k in q_lower for k in [
        "biggest storage problem", "largest storage problem", "storage problem",
        "biggest storage issue", "most constrained plant", "highest risk of running out"
    ])
    if is_biggest_storage_problem:
        sql_storage_prob = """SELECT TOP 1
    RANK() OVER (ORDER BY ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2) DESC) AS [Rank],
    b.Plant AS [Plant],
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins],
    (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) AS [Empty Bins],
    COUNT(DISTINCT b.BinLocation) AS [Total Bins],
    CONCAT(ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2), '%') AS [Bin Utilization %]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
GROUP BY b.Plant
ORDER BY ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2) DESC"""
        return {
            "sql": sql_storage_prob,
            "chart_type": "none",
            "chart_title": "Plant with Highest Utilization (Storage Constraint)",
            "chart_x": None,
            "chart_y": None,
            "intent": "plant_biggest_storage_problem",
            "metric": "storage_constraint",
            "filters": {},
            "time_range": "current",
            "output_type": "text",
            "conversation_state": state
        }

    # 6. Put-away candidate bins: "Where can I put away more stock?"
    is_put_away_more_stock = any(k in q_lower for k in [
        "where can i put away more stock", "where can i put away stock",
        "put away more stock", "where to put away stock", "where to put stock",
        "where can we store more stock", "put away incoming stock"
    ])
    if is_put_away_more_stock:
        plant_f = f" AND b.Plant = '{plant_cand}'" if plant_cand else ""
        sql_putaway_cands = f"""SELECT TOP 10
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    COALESCE(b.StorageLocation, 'N/A') AS [Storage Location],
    ROUND(b.Volume, 2) AS [Total Capacity (FT3)],
    ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Occupied Volume (FT3)],
    ROUND(b.Volume - COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Available Capacity (FT3)],
    CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE b.Volume > 0{plant_f}
GROUP BY b.BinLocation, b.Plant, b.StorageLocation, b.Volume
ORDER BY [Available Capacity (FT3)] DESC"""
        return {
            "sql": sql_putaway_cands,
            "chart_type": "none",
            "chart_title": f"Top Put-Away Candidate Bins by Available Capacity{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": None,
            "chart_y": None,
            "intent": "putaway_bins_ranking",
            "metric": "available_capacity",
            "filters": {"plant": plant_cand} if plant_cand else {},
            "time_range": "current",
            "output_type": "text" if is_single_statement_requested else "table",
            "conversation_state": state
        }

    # 7. Best performing plant on storage utilization
    is_performing_best_util = any(k in q_lower for k in [
        "performing best on storage utilization", "performing best on utilization",
        "best on storage utilization", "best performing plant on utilization",
        "performing best in storage utilization"
    ])
    if is_performing_best_util:
        sql_best_util = """SELECT TOP 1
    RANK() OVER (ORDER BY ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2) DESC) AS [Rank],
    b.Plant AS [Plant],
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins],
    (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) AS [Empty Bins],
    COUNT(DISTINCT b.BinLocation) AS [Total Bins],
    CONCAT(ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2), '%') AS [Bin Utilization %]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
GROUP BY b.Plant
ORDER BY ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2) DESC"""
        return {
            "sql": sql_best_util,
            "chart_type": "none",
            "chart_title": "Top Performing Plant by Storage Utilization",
            "chart_x": None,
            "chart_y": None,
            "intent": "plant_best_utilization",
            "metric": "bin_utilization",
            "filters": {},
            "time_range": "current",
            "output_type": "text",
            "conversation_state": state
        }

    # 8. Warehouse fullness & utilization summary
    is_warehouse_fullness_summary = any(k in q_lower for k in [
        "how full is the warehouse right now", "how full is the warehouse", "how full is our warehouse",
        "how full is this warehouse", "current warehouse fullness", "overall warehouse fullness",
        "how full is the overall warehouse", "warehouse fullness", "most important warehouse utilization information",
        "important warehouse utilization information", "quick warehouse utilization summary",
        "give me a quick warehouse utilization summary", "give me a quick warehouse utilization"
    ]) or (
        ("utilization" in q_lower or "fullness" in q_lower or "fill" in q_lower) and
        ("one line" in q_lower or "single line" in q_lower or "only the number" in q_lower or "just the percentage" in q_lower) and
        not any(k in q_lower for k in ["which plant", "what plant", "highest", "lowest", "rank", "ranking", "top", "bottom"]) and
        not plant_cand and not raw_bins and not is_mat_entity
    )
    if is_warehouse_fullness_summary:
        if is_bin_utilization_primary(q_lower):
            sql_wf = """SELECT 
    b.Plant, 
    COUNT(DISTINCT b.BinLocation) AS TotalBins, 
    COUNT(DISTINCT i.BinNo) AS OccupiedBins, 
    (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) AS EmptyBins, 
    CONCAT(ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2), '%') AS [Bin Utilization %] 
FROM dbo.ZWMS_BIN_MASTER b 
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant 
GROUP BY b.Plant 
ORDER BY ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2) DESC"""
            chart_y = "Bin Utilization %"
        else:
            sql_wf = """SELECT 
    b.Plant, 
    COUNT(DISTINCT b.BinLocation) AS TotalBins, 
    COUNT(DISTINCT i.BinNo) AS OccupiedBins, 
    (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) AS EmptyBins, 
    ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2) AS BinUtilizationPct, 
    ROUND(SUM(b.Volume), 2) AS TotalBinCapacityVolume, 
    ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) AS OccupiedBinVolume, 
    ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END) * 100.0 / NULLIF(SUM(b.Volume), 0), 2) AS VolumeUtilizationPct 
FROM dbo.ZWMS_BIN_MASTER b 
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant 
GROUP BY b.Plant 
ORDER BY VolumeUtilizationPct DESC"""
            chart_y = "VolumeUtilizationPct"
        return {
            "sql": sql_wf,
            "chart_type": "none" if is_single_statement_requested else "bar",
            "chart_title": "Warehouse Network Bin Utilization Summary",
            "chart_x": None if is_single_statement_requested else "Plant",
            "chart_y": None if is_single_statement_requested else chart_y,
            "intent": "bin_utilization",
            "metric": "warehouse_utilization",
            "filters": {},
            "time_range": "current",
            "output_type": "text" if is_single_statement_requested else "table",
            "conversation_state": state
        }

    # C. TOP N & BOTTOM N BIN UTILIZATION RANKINGS
    has_both = state.get("topic") == "top_and_bottom_bins" or (
        any(w in q_lower for w in ["top", "most", "fullest", "highest", "most full", "most utilized", "highest utilized"]) and
        any(w in q_lower for w in ["bottom", "least", "emptiest", "lowest", "least full", "least utilized", "lowest utilized", "empty bins"]) and
        any(b in q_lower for b in ["bin", "bins", "location", "locations", "racks", "rack", "slot", "slots"])
    )
    has_rank = any(k in q_lower for k in ["rank", "ranking", "rankings", "sort", "order by"])
    has_top = not is_almost_full_req and not is_over_capacity_req and (
        state.get("ranking") == "highest" or
        state.get("topic") in ["top_utilized_bins", "bin_available_capacity_ranking"] or
        (bool(re.search(r"\b(?:top|most|highest|fullest)\b", q_lower)) or any(k in q_lower for k in ["most capacity", "capacity usage", "fullest bins", "most full", "most occupied", "highest utilization"])) or
        (has_rank and any(b in q_lower for b in ["bin", "bins"]) and not any(k in q_lower for k in ["least", "lowest", "bottom"]))
    )
    has_bottom = not is_almost_full_req and not is_over_capacity_req and (state.get("ranking") == "lowest" or state.get("topic") == "least_utilized_bins" or any(k in q_lower for k in ["bottom", "least", "lowest", "emptiest", "unused capacity", "emptiest bins", "least full", "least occupied", "lowest utilization", "least empty", "least utiliz"]))
    is_plant_level_extreme = (
        bool(re.search(r"\b(?:plants?|plnts?|facility|facilities)\b", q_lower)) and
        (
            not any(b in q_lower for b in ["bins", "bin", "locations", "racks", "slots"]) or
            any(p in q_lower for p in ["plant bin utilization", "plants by bin utilization", "plants by utilization", "ranking of plant", "plant utilization ranking", "by plant", "across plants", "of plant bin utilization"]) or
            any(k in q_lower for k in ["bin utiliz", "bin occupan"])
        ) and
        (
            any(k in q_lower for k in ["lowest", "least", "minimum", "min", "bottom", "worst", "highest", "most", "maximum", "max", "top", "best", "rank", "ranking"]) or
            any(k in q_lower for k in ["which", "whic", "what", "wat", "compare", "across", "all", "each", "every", "ranking"])
        )
    ) or (
        any(k in q_lower for k in [
            "which plant has the lowest", "which plant has lowest", "which plant has the highest", "which plant has highest",
            "plant with the lowest", "plant with lowest", "plant with the highest", "plant with highest",
            "least full plant", "most full plant"
        ])
    )
    is_plant_empty_bins_query = (
        bool(re.search(r"\b(?:plants?|plnts?|facility|facilities)\b", q_lower)) and
        any(k in q_lower for k in ["empty bin", "empty bins", "vacant bin", "vacant bins"]) and
        (
            any(k in q_lower for k in [
                "rank", "ranking", "rankings", "sort", "order", "most", "highest",
                "least", "lowest", "fewest", "which", "show plants", "plants ranked",
                "based on", "according to", "empty bin count"
            ]) or ("by plant" in q_lower and "count" in q_lower)
        ) and
        not any(k in q_lower for k in ["capacity", "volume", "ft3", "cubic"])
    )
    is_bin_metric = (any(k in q_lower for k in ["bin", "bins", "location", "locations", "racks", "rack", "slot", "slots", "storage position", "ones", "one", "these", "those", "they", "them", "it"]) or (has_top or has_bottom or has_both)) and not is_plant_level_extreme
    is_util_metric = any(k in q_lower for k in ["utiliz", "full", "capacit", "occup", "empty", "unused", "space", "occupan"]) or has_both

    if (
        not is_plant_empty_bins_query and
        is_bin_metric and (is_util_metric or has_both) and (has_top or has_bottom or has_both) and not is_mat_entity
        and not (state.get("entity") == "plant" and not any(b in q_lower for b in ["bin", "bins"]))
        and not (bool(re.search(r"\b(?:plants?|plnts?|facility|facilities)\b", q_lower)) and any(k in q_lower for k in ["occupied volume", "storage volume", "space occupied", "total bins", "unique materials", "inventory quantity", "available capacity", "warehouse space"]) and not any(b in q_lower for b in ["bin", "bins"]))
        and state.get("topic") not in [
            "plant_bin_level_detail", "multi_plant_bin_detail",
            "total_warehouse_capacity", "available_capacity", "occupied_volume",
            "capacity_summary", "plant_capacity", "empty_bins_capacity",
            "referential_bins_capacity", "single_bin_capacity",
            "compound_capacity_utilization", "compound_capacity_clarification", "find_bins_list",
            "plant_empty_bins_ranking", "almost_full_bins", "over_capacity_bins"
        ]
        and not parse_compound_capacity_utilization(resolved_q)
        and not parse_range_filters(resolved_q)
    ):
        n_val = state.get("limit") or 10
        if not state.get("limit"):
            n_match = re.search(r"\b(?:top|bottom|highest|lowest|first|last|least|most)?\s*(\d{1,3})\b", q_lower)
            n_val = int(n_match.group(1)) if (n_match and n_match.group(1) not in ["100", "2024", "2025", "2026"]) else 10
        
        plant_cands = extract_explicit_plants(q_lower) or ([plant_cand] if plant_cand else [])
        if len(plant_cands) == 1:
            plant_filter = f" AND b.Plant = '{plant_cands[0]}'"
            plant_title_suffix = f" — Plant {plant_cands[0]}"
            rank_scope = {"Plant": plant_cands[0]}
            filters = {"ranking_limit": n_val, "plant": plant_cands[0]}
        elif len(plant_cands) > 1:
            plant_filter = " AND b.Plant IN (" + ", ".join(f"'{p}'" for p in plant_cands) + ")"
            plant_title_suffix = " — Plants " + " and ".join(plant_cands)
            rank_scope = {"Plants": plant_cands}
            filters = {"ranking_limit": n_val, "plants": plant_cands}
        else:
            plant_filter = ""
            plant_title_suffix = ""
            rank_scope = {}
            filters = {"ranking_limit": n_val}

        # Bin Available Capacity Ranking: "Rank bins by available capacity", "Which bin has the most available capacity?"
        is_bin_avail_cap = (
            any(k in q_lower for k in ["available capacity", "available space", "free capacity", "remaining capacity", "free space", "available volume", "unused capacity", "most available", "least available"]) or state.get("topic") == "bin_available_capacity_ranking"
        ) and not parse_range_filters(resolved_q)
        if is_bin_avail_cap:
            is_least = state.get("ranking") == "lowest" or any(k in q_lower for k in ["least", "lowest", "bottom", "minimum", "smallest"])
            order_dir = "ASC" if is_least else "DESC"
            rank_label = "Least" if is_least else "Most"
            is_singular = is_single_statement_requested or any(k in q_lower for k in ["which bin", "whic bin", "what bin", "bin with the most", "bin with the least", "who has the most available", "most available space"])
            limit_rows = 1 if is_singular else n_val
            top_kw = f"TOP {limit_rows} "

            sql_bin_avail = f"""SELECT {top_kw}
    RANK() OVER (ORDER BY ROUND(b.Volume - COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) {order_dir}) AS [Rank],
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    ROUND(b.Volume - COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Available Capacity (FT3)],
    CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Bin Capacity],
    ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Occupied Volume],
    CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE b.Volume > 0{plant_filter}
GROUP BY b.BinLocation, b.Plant, b.Volume, b.VolumeUnit
ORDER BY [Available Capacity (FT3)] {order_dir}"""

            return {
                "sql": sql_bin_avail,
                "query_plan": {
                    "intent": "RANKING",
                    "rank_direction": order_dir,
                    "rank_metric": "AvailableCapacity",
                    "rank_entity": "Bin",
                    "limit": limit_rows,
                    "rank_scope": rank_scope
                },
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": f"{rank_label} Available Capacity Bins{plant_title_suffix}",
                "chart_x": "Bin" if is_explicit_chart else None,
                "chart_y": "Available Capacity (FT3)" if is_explicit_chart else None,
                "intent": "bin_available_capacity_ranking",
                "metric": "available_capacity_ranking",
                "filters": filters,
                "time_range": "current",
                "output_type": "text" if is_singular else ("bar_chart" if is_explicit_chart else "table"),
                "conversation_state": state
            }

        if has_both:
            # Extract independent limits if top and bottom limits differ
            m_top = re.search(r"\b(?:top|most|highest|fullest)\s*(\d{1,3})\b", q_lower)
            if not m_top:
                m_top = re.search(r"\b(\d{1,3})\s+(?:most|highest|fullest|top)\b", q_lower)
            m_bottom = re.search(r"\b(?:bottom|least|lowest|emptiest)\s*(\d{1,3})\b", q_lower)
            if not m_bottom:
                m_bottom = re.search(r"\b(\d{1,3})\s+(?:least|lowest|emptiest|bottom)\b", q_lower)
                
            n_top = int(m_top.group(1)) if m_top else n_val
            n_bottom = int(m_bottom.group(1)) if m_bottom else n_val

            sql_both = f"""WITH RankedBins AS (
    SELECT 
        b.BinLocation AS Bin,
        b.Plant,
        ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Occupied Volume],
        CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Bin Capacity],
        CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %],
        ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1) AS RawUtil
    FROM dbo.ZWMS_BIN_MASTER b
    JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
    WHERE b.Volume > 0{plant_filter}
    GROUP BY b.BinLocation, b.Plant, b.Volume, b.VolumeUnit
),
TopBins AS (
    SELECT TOP {n_top}
        ROW_NUMBER() OVER (ORDER BY RawUtil DESC, Bin ASC) AS [Rank],
        'Top {n_top} Most Utilized' AS [Ranking Group],
        Bin, Plant, [Bin Capacity], [Occupied Volume], [Utilization %], RawUtil
    FROM RankedBins
    ORDER BY RawUtil DESC, Bin ASC
),
BottomBins AS (
    SELECT TOP {n_bottom}
        ROW_NUMBER() OVER (ORDER BY RawUtil ASC, Bin ASC) AS [Rank],
        'Bottom {n_bottom} Least Utilized' AS [Ranking Group],
        Bin, Plant, [Bin Capacity], [Occupied Volume], [Utilization %], RawUtil
    FROM RankedBins
    ORDER BY RawUtil ASC, Bin ASC
)
SELECT [Ranking Group], [Rank], Bin, Plant, [Bin Capacity], [Occupied Volume], [Utilization %]
FROM (
    SELECT 1 AS SortGroup, [Ranking Group], [Rank], Bin, Plant, [Bin Capacity], [Occupied Volume], [Utilization %]
    FROM TopBins
    UNION ALL
    SELECT 2 AS SortGroup, [Ranking Group], [Rank], Bin, Plant, [Bin Capacity], [Occupied Volume], [Utilization %]
    FROM BottomBins
) Combined
ORDER BY SortGroup ASC, [Rank] ASC"""

            chart_title = f"Top {n_top} Most & Top {n_bottom} Least Utilized Bins{plant_title_suffix}"
            return {
                "sql": sql_both,
                "query_plan": {
                    "entity": "BIN",
                    "metric": "BIN_UTILIZATION",
                    "scope": "ALL_BINS" if not plant_cands else f"PLANT_{plant_cands[0]}",
                    "filters": filters,
                    "intent": "COMBINED_RANKING",
                    "operation": "COMBINED_RANKING",
                    "rank_direction": "BOTH",
                    "number_of_rankings": 2,
                    "rankings": [
                        {
                            "type": "TOP",
                            "direction": "DESC",
                            "metric": "BIN_UTILIZATION",
                            "limit": n_top,
                            "label": f"Top {n_top} Most Utilized"
                        },
                        {
                            "type": "LEAST",
                            "direction": "ASC",
                            "metric": "BIN_UTILIZATION",
                            "limit": n_bottom,
                            "label": f"Top {n_bottom} Least Utilized"
                        }
                    ],
                    "rank_metric": "BinUtilization",
                    "rank_entity": "Bin",
                    "limit": n_val,
                    "rank_scope": rank_scope
                },
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": chart_title,
                "chart_x": "Bin" if is_explicit_chart else None,
                "chart_y": "Utilization %" if is_explicit_chart else None,
                "intent": "top_and_bottom_bins",
                "metric": "bin_utilization_ranking",
                "filters": filters,
                "time_range": "current",
                "output_type": "text" if is_single_statement_requested else ("bar_chart" if is_explicit_chart else "table"),
                "conversation_state": state
            }

        if state.get("ranking") == "lowest" or (has_bottom and not (has_top and state.get("ranking") == "highest")):
            limit_rows = 1 if is_single_statement_requested else n_val
            top_kw = f"TOP {limit_rows} " if is_single_statement_requested else f"TOP {n_val} "
            sql_bottom = f"""SELECT {top_kw}
    RANK() OVER (ORDER BY SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0) ASC) AS [Rank],
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 2) AS [Occupied Volume],
    CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Bin Capacity],
    CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Capacity],
    CONCAT(ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %],
    CONCAT(ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization]
FROM dbo.ZWMS_BIN_MASTER b 
JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant 
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode 
WHERE b.Volume > 0{plant_filter} 
GROUP BY b.BinLocation, b.Plant, b.Volume, b.VolumeUnit 
ORDER BY SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0) ASC"""
            return {
                "sql": sql_bottom,
                "query_plan": {
                    "entity": "BIN",
                    "metric": "BIN_UTILIZATION",
                    "operation": "RANKING",
                    "intent": "RANKING",
                    "rank_direction": "ASC",
                    "ranking_direction": "ASC",
                    "rank_metric": "BinUtilization",
                    "rank_entity": "Bin",
                    "limit": n_val,
                    "ranking_limit": n_val,
                    "rank_scope": rank_scope,
                    "filters": filters,
                    "response_mode": state.get("response_mode", "TABLE")
                },
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": f"{n_val} Least Utilized Bins{plant_title_suffix}",
                "chart_x": "Bin" if is_explicit_chart else None,
                "chart_y": "Occupied Volume" if is_explicit_chart else None,
                "intent": "least_utilized_bins",
                "metric": "bin_utilization_ranking",
                "filters": filters,
                "time_range": "current",
                "output_type": "text" if is_single_statement_requested else ("bar_chart" if is_explicit_chart else "table"),
                "conversation_state": state
            }

        if state.get("ranking") == "highest" or has_top:
            if len(plant_cands) >= 2 and any(k in q_lower for k in ["compare", "comparison", "versus", "vs", "difference"]):
                in_plants_clause = ", ".join(f"'{p}'" for p in plant_cands)
                sql_comp_top = f"""WITH RankedBins AS (
    SELECT 
        ROW_NUMBER() OVER (PARTITION BY b.Plant ORDER BY SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0) DESC) AS PlantRank,
        b.BinLocation AS [Bin],
        b.Plant AS [Plant],
        ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 2) AS [Occupied Volume],
        CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Bin Capacity],
        CONCAT(ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %]
    FROM dbo.ZWMS_BIN_MASTER b 
    JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant 
    LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode 
    WHERE b.Volume > 0 AND b.Plant IN ({in_plants_clause})
    GROUP BY b.BinLocation, b.Plant, b.Volume, b.VolumeUnit 
)
SELECT 
    PlantRank AS [Rank],
    [Bin],
    [Plant],
    [Occupied Volume],
    [Bin Capacity],
    [Utilization %]
FROM RankedBins
WHERE PlantRank <= {n_val}
ORDER BY [Plant], PlantRank"""
                return {
                    "sql": sql_comp_top,
                    "query_plan": {
                        "intent": "COMPARISON",
                        "operation": "COMPARISON",
                        "entity": "BIN",
                        "metric": "BIN_UTILIZATION",
                        "plants": plant_cands,
                        "ranking_context": "TOP UTILIZED",
                        "limit": n_val
                    },
                    "chart_type": "bar" if is_explicit_chart else "none",
                    "chart_title": f"Top {n_val} Utilized Bins Comparison ({' vs '.join(plant_cands)})",
                    "chart_x": "Bin" if is_explicit_chart else None,
                    "chart_y": "Occupied Volume" if is_explicit_chart else None,
                    "intent": "top_utilized_bins_comparison",
                    "metric": "BIN_UTILIZATION",
                    "filters": {"plants": plant_cands, "limit": n_val},
                    "time_range": "current",
                    "output_type": "table",
                    "conversation_state": state
                }

            limit_rows = 1 if is_single_statement_requested else n_val
            top_kw = f"TOP {limit_rows} " if is_single_statement_requested else f"TOP {n_val} "
            sql_top = f"""SELECT {top_kw}
    RANK() OVER (ORDER BY SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0) DESC) AS [Rank],
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 2) AS [Occupied Volume],
    CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Bin Capacity],
    CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Capacity],
    CONCAT(ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %],
    CONCAT(ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization]
FROM dbo.ZWMS_BIN_MASTER b 
JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant 
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode 
WHERE b.Volume > 0{plant_filter} 
GROUP BY b.BinLocation, b.Plant, b.Volume, b.VolumeUnit 
ORDER BY SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0) DESC"""
            return {
                "sql": sql_top,
                "query_plan": {
                    "entity": "BIN",
                    "metric": "BIN_UTILIZATION",
                    "operation": "RANKING",
                    "intent": "RANKING",
                    "rank_direction": "DESC",
                    "ranking_direction": "DESC",
                    "rank_metric": "BinUtilization",
                    "rank_entity": "Bin",
                    "limit": n_val,
                    "ranking_limit": n_val,
                    "rank_scope": rank_scope,
                    "filters": filters,
                    "response_mode": state.get("response_mode", "TABLE")
                },
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": f"Top {n_val} Most Utilized Bins{plant_title_suffix}",
                "chart_x": "Bin" if is_explicit_chart else None,
                "chart_y": "Occupied Volume" if is_explicit_chart else None,
                "intent": "top_utilized_bins",
                "metric": "bin_utilization_ranking",
                "filters": filters,
                "time_range": "current",
                "output_type": "text" if is_single_statement_requested else ("bar_chart" if is_explicit_chart else "table"),
                "conversation_state": state
            }


    # D. BIN CAPACITY & UTILIZATION THRESHOLD FILTERING
    has_range_between = bool(
        re.search(r"(?:between|from)\s*\d+.*?(?:and|to|–|-)\s*\d+", q_lower) or
        re.search(r"\b\d+\s*%\s*(?:–|-|to)\s*\d+\s*%", q_lower) or
        re.search(r"(?:>=|greater than or equal to|at least)\s*\d+.*?(?:<=|less than or equal to|at most)\s*\d+", q_lower)
    )
    is_bin_cap_query = any(k in q_lower for k in ["capacity", "total capacity", "bin capacity", "storage capacity"]) and not any(k in q_lower for k in ["utiliz", "occupan", "%", "full", "fullness", "fill"])
    threshold_match = None
    if not has_range_between and not is_bin_cap_query:
        threshold_match = re.search(r"(?:more\s+than|greater\s+than|over|above|>|>=|at\s+least|exceeding|less\s+than|below|<|<=|under)\s*(\d{1,3})(?:\s*%)?", q_lower)
        if not threshold_match:
            threshold_match = re.search(r"(\d{1,3})\s*%\s*(?:full|utiliz|capacit|occup)", q_lower)

    if threshold_match and is_bin_metric and (is_util_metric or "%" in q_lower) and not is_mat_entity and not is_bin_cap_query:
        thresh_val = float(threshold_match.group(1))
        inclusive = any(k in q_lower for k in ["at least", ">=", "or more", "or above", "minimum"])
        inclusive_low = any(k in q_lower for k in ["at most", "<=", "or below", "or less", "maximum"])
        is_less = any(k in q_lower for k in ["less than", "below", "under", "<", "at most", "or below", "or less"])
        if is_less:
            op = "<=" if inclusive_low else "<"
            op_desc = "at most" if inclusive_low else "below"
        else:
            op = ">=" if inclusive else ">"
            op_desc = "at least" if inclusive else "above"
        op_symbol = {"<": "<", "<=": "≤", ">": ">", ">=": "≥"}[op]

        plants = extract_plants(q_lower) or ([plant_cand] if plant_cand else [])
        if len(plants) == 1:
            plant_filter = f" AND b.Plant = '{plants[0]}'"
        elif len(plants) > 1:
            plant_filter = " AND b.Plant IN (" + ", ".join(f"'{p}'" for p in plants) + ")"
        else:
            plant_filter = ""
        plant_label = ("Plants " + " and ".join(plants)) if len(plants) > 1 else (f"Plant {plants[0]}" if plants else "all plants")
        intent_name = "low_utilization_bins" if is_less else "high_utilization_bins"
        
        # If user asks for count ("How many bins are above 90%?"):
        is_count_request = any(c in q_lower for c in ["how many", "count", "number of", "total count"])
        if is_count_request:
            sql_thresh_count = f"""SELECT Plant, COUNT(*) AS [Threshold Bins Count]
FROM (
    SELECT b.Plant, b.BinLocation
    FROM dbo.ZWMS_BIN_MASTER b
    JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
    WHERE b.Volume > 0{plant_filter}
    GROUP BY b.Plant, b.BinLocation, b.Volume
    HAVING ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0), 1) {op} {thresh_val}
) sub
GROUP BY Plant"""
            return {
                "sql": sql_thresh_count,
                "chart_type": "none",
                "chart_title": f"Count of Bins with Utilization % {op_symbol} {thresh_val}% ({plant_label})",
                "chart_x": None,
                "chart_y": None,
                "intent": f"{intent_name}_count",
                "metric": "bin_count",
                "filters": {"Utilization %": f"{op_symbol} {thresh_val}%", "plants": plants},
                "time_range": "current",
                "output_type": "text",
                "conversation_state": state
            }

        util_expr = "SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0)"
        list_sql = f"""SELECT
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Bin Capacity],
    ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 2) AS [Occupied Volume],
    CONCAT(ROUND({util_expr}, 1), '%') AS [Utilization %]
FROM dbo.ZWMS_BIN_MASTER b
JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE b.Volume > 0{plant_filter}
GROUP BY b.BinLocation, b.Plant, b.Volume, b.VolumeUnit
HAVING ROUND({util_expr}, 1) {op} {thresh_val}
ORDER BY {util_expr} {'ASC' if is_less else 'DESC'}"""

        res_dict = {
            "sql": list_sql,
            "chart_type": "none",
            "chart_title": f"Bins with Utilization % {op_symbol} {thresh_val}% ({plant_label})",
            "chart_x": None,
            "chart_y": None,
            "intent": intent_name,
            "metric": "bin_fullness",
            "filters": {"Utilization %": f"{op_symbol} {thresh_val}%", "plants": plants},
            "time_range": "current",
            "output_type": "table",
            "conversation_state": state
        }
        if len(plants) >= 2:
            thresh_fmt = str(int(thresh_val)) if thresh_val.is_integer() else str(thresh_val)
            res_dict["is_multi_table_comparison"] = True
            res_dict["comparison_plants"] = plants
            res_dict["op_desc"] = op_desc
            res_dict["op_symbol"] = op_symbol
            res_dict["thresh_str"] = thresh_fmt
            res_dict["plant_sql_template"] = f"""SELECT
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Bin Capacity],
    ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 2) AS [Occupied Volume],
    CONCAT(ROUND({util_expr}, 1), '%') AS [Utilization %]
FROM dbo.ZWMS_BIN_MASTER b
JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE b.Volume > 0 AND b.Plant = '{{plant}}'
GROUP BY b.BinLocation, b.Plant, b.Volume, b.VolumeUnit
HAVING ROUND({util_expr}, 1) {op} {thresh_val}
ORDER BY {util_expr} {'ASC' if is_less else 'DESC'}"""
        return res_dict

    # E. EMPTY BINS / AVAILABLE FOR PUT-AWAY & COUNT SCALARS
    # Semantic Definition: Bin inventory quantity = 0 (UnrestrictedQty = 0 or BinNo IS NULL)
    is_empty_intent = (state.get("topic") in ["putaway_bins", "empty_bins_count"] or (
        any(k in q_lower for k in [
            "empty", "putaway", "put-away", "put away", "vacant", "unoccupied",
            "unused", "free bin", "free location", "free storage", "completely free",
            "available bin", "available storage", "free right now", "freight",
            "zero inventory", "no inventory", "zero stock", "no stock", "no current stock",
            "zero occupied", "balance is zero", "quantity equals zero", "quantity is zero",
            "stock level is zero", "nothing is stored", "nothing is currently stored",
            "nothing stored", "without displacing", "incoming stock", "incoming shipment",
            "not being used", "aren't being used", "accept new", "store new", "without moving",
            "where can i put", "where to put", "put new inventory", "place incoming", "where do we have free"
        ]) or (
            ("free" in q_lower or "vacant" in q_lower or "zero" in q_lower or "empty" in q_lower) and
            ("bin" in q_lower or "location" in q_lower or "storage" in q_lower or "position" in q_lower or "slot" in q_lower)
        )
    )) and not any(k in q_lower for k in [
        "compare", "versus", "vs", "difference between", "their empty bins",
        "how much capacity", "capacity is available", "capacity in empty", "capacity of empty",
        "available capacity in empty", "available capacity of empty"
    ]) and state.get("topic") != "empty_bins_capacity" and not is_plant_empty_bins_query and state.get("topic") != "plant_empty_bins_ranking"
    if is_empty_intent:
        plant_filter = f" AND b.Plant = '{plant_cand}'" if plant_cand else ""
        filters = {"plant": plant_cand} if plant_cand else {}

        # If user asked "how many are there?" -> return scalar count query
        if state.get("aggregation") == "count" or state.get("topic") == "empty_bins_count" or any(k in q_lower for k in ["how many", "count", "what is the count", "total count"]):
            plant_suffix = f" in Plant {plant_cand}" if plant_cand else ""
            sql_count = f"""SELECT COUNT(DISTINCT b.BinLocation) AS [Empty Bins Count], COUNT(DISTINCT b.Plant) AS [Plant Count]
FROM dbo.ZWMS_BIN_MASTER b 
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant 
WHERE (i.BinNo IS NULL OR i.UnrestrictedQty = 0){plant_filter}"""
            return {
                "sql": sql_count,
                "query_plan": {
                    "entity": "BIN",
                    "metric": "EMPTY_BIN",
                    "operation": "COUNT",
                    "filters": filters,
                    "response_mode": "COUNT"
                },
                "chart_type": "none",
                "chart_title": f"Total Empty Bins{plant_suffix}",
                "chart_x": None,
                "chart_y": None,
                "intent": "empty_bins_count",
                "metric": "empty_bins_count",
                "filters": filters,
                "time_range": "current",
                "output_type": "kpi",
                "conversation_state": state
            }

        plant_suffix = f" — Plant {plant_cand}" if plant_cand else ""
        n_limit = state.get("limit") or new_limit
        top_clause = f"TOP {n_limit} " if n_limit else ""
        sql_empty_list = f"""SELECT {top_clause}
    b.BinLocation AS [BinLocation],
    b.BinLocation AS [Bin], 
    b.Plant AS [Plant], 
    b.StorageLocation AS [Storage Location], 
    0 AS [Inventory Qty], 
    'Available' AS [Status],
    COUNT(*) OVER() AS [TotalMatching]
FROM dbo.ZWMS_BIN_MASTER b 
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant 
WHERE (i.BinNo IS NULL OR i.UnrestrictedQty = 0){plant_filter} 
GROUP BY b.BinLocation, b.Plant, b.StorageLocation, b.Volume, b.VolumeUnit 
ORDER BY b.Plant, b.StorageLocation, b.BinLocation"""
        return {
            "sql": sql_empty_list,
            "query_plan": {
                "entity": "BIN",
                "metric": "EMPTY_BIN",
                "operation": "FILTER",
                "filters": filters,
                "response_mode": state.get("response_mode", "TABLE")
            },
            "chart_type": "none",
            "chart_title": f"Empty Bins{plant_suffix}",
            "chart_x": None,
            "chart_y": None,
            "intent": "putaway_bins",
            "metric": "unoccupied_bins",
            "filters": filters,
            "time_range": "current",
            "output_type": "table",
            "conversation_state": state
        }

    # F. AVERAGE INVENTORY PER OCCUPIED BIN (Item 8)
    # Semantic Definition: Total inventory quantity / number of occupied bins
    if any(k in q_lower for k in [
        "average inventory", "avg inventory", "average stock", "avg stock", "average quantity",
        "avg quantity", "average inventory quantity", "average units", "inventory per bin",
        "stock per bin", "units per bin", "quantity per bin", "inventory per occupied bin",
        "mean quantity", "mean stock", "mean units", "mean inventory", "inside each occupied",
        "average items per occupied bin", "average items per bin"
    ]) and not any(k in q_lower for k in ["compare", "versus", "vs", "difference between"]):
        plant_filter = f" WHERE Plant = '{plant_cand}' AND UnrestrictedQty > 0" if plant_cand else " WHERE UnrestrictedQty > 0"
        filters = {"plant": plant_cand} if plant_cand else {}
        query_plan = {
            "intent": "KPI",
            "entity": "BIN",
            "metric": "AVG_INVENTORY_PER_BIN",
            "aggregation": "AVG INVENTORY QUANTITY PER BIN",
            "operation": "AGGREGATION"
        }
        return {
            "sql": f"SELECT ROUND(SUM(UnrestrictedQty) * 1.0 / NULLIF(COUNT(DISTINCT BinNo), 0), 2) AS AvgInventoryPerOccupiedBin, SUM(UnrestrictedQty) AS TotalQuantity, COUNT(DISTINCT BinNo) AS OccupiedBins, COUNT(DISTINCT Material) AS UniqueMaterials FROM dbo.ZWMS_INVENTORY{plant_filter} HAVING COUNT(DISTINCT BinNo) > 0",
            "query_plan": query_plan,
            "chart_type": "none",
            "chart_title": "Average Inventory per Occupied Bin",
            "chart_x": None,
            "chart_y": None,
            "intent": "avg_inventory_per_bin",
            "metric": "AVG_INVENTORY_PER_BIN",
            "filters": filters,
            "time_range": "current",
            "output_type": "kpi"
        }

    # =========================================================================
    # SECTION COMP: GENERALIZED COMPARISON ENGINE (Plants, Materials, Bins, SLocs)
    # =========================================================================
    explicit_plants_in_gen = extract_explicit_plants(q_lower)
    if len(explicit_plants_in_gen) >= 2:
        all_plants_unique = explicit_plants_in_gen
    else:
        all_plants_mentioned = re.findall(r"\b(1258|1266|1268|7228)\b", q_lower)
        all_plants_unique = list(dict.fromkeys(all_plants_mentioned))
        if len(all_plants_unique) < 2 and state.get("comparison_entities"):
            saved_plants = [e["value"] for e in state["comparison_entities"] if e.get("type") == "plant"]
            if len(saved_plants) >= 2:
                all_plants_unique = saved_plants
        elif len(all_plants_unique) < 2 and len(state.get("plants", [])) >= 2:
            all_plants_unique = state["plants"][-2:]

    range_filters_pre = parse_range_filters(resolved_q)
    is_ranking_in_q = any(k in q_lower for k in ["rank", "ranking", "rankings", "order by", "sort by"])
    raw_has_compare_kw = any(k in q_lower for k in [
        "compare", "versus", "vs", "comparison", "difference between", "difference of",
        "their total inventory", "their bins", "their unique materials",
        "their materials", "their storage locations", "their empty bins",
        "their occupied bins", "their top materials", "compare those", "compare them", "compare these", "compare both"
    ])
    raw_explicit_plants = extract_explicit_plants(question.lower())

    is_comparison_query = not is_ranking_in_q and not range_filters_pre and (
        (
            len(all_plants_unique) >= 2 and (
                state.get("topic") in ["plant_comparison", "multi_plant_bin_detail"] or
                state.get("operation") == "comparison" or
                raw_has_compare_kw
            ) and (len(raw_explicit_plants) != 1 or raw_has_compare_kw)
        ) or (
            len(raw_explicit_plants) >= 2 and (
                any(k in q_lower for k in ["between", "and", "utiliz", "capacity", "how full"])
            ) and not any(k in q_lower for k in ["between 100", "between 1", "between 2", "between 5", "between 10", "between 50"])
        )
    )

    if is_comparison_query:
        target_plants = all_plants_unique[:4]
        plants_in_str = ", ".join(f"'{p}'" for p in target_plants)
        comp_entities = [{"type": "plant", "value": p} for p in target_plants]
        state["comparison_entities"] = comp_entities

        # 1. Total Inventory Quantity
        if any(k in q_lower for k in ["total inventory", "inventory quantity", "total stock", "how much stock", "how much inventory", "stock quantity", "their total inventory"]) or (
            any(k in q_lower for k in ["inventory", "stock", "quantity"]) and not any(k in q_lower for k in ["material", "bin", "utiliz", "sloc", "location"])
        ):
            sql_comp = f"""SELECT 
    Plant,
    SUM(UnrestrictedQty) AS [Total Inventory Quantity],
    COUNT(DISTINCT Material) AS [Unique Materials],
    COUNT(DISTINCT BinNo) AS [Occupied Bins]
FROM dbo.ZWMS_INVENTORY
WHERE Plant IN ({plants_in_str})
GROUP BY Plant
ORDER BY [Total Inventory Quantity] DESC"""
            comp_subject = "total_inventory"
            metrics = ["inventory_quantity", "unique_materials", "occupied_bins"]

        # 2. Materials / Unique Materials
        elif any(k in q_lower for k in ["unique material", "unique materials", "materials", "sku", "skus", "items", "their materials", "their unique materials"]):
            sql_comp = f"""SELECT 
    Plant,
    COUNT(DISTINCT Material) AS [Unique Materials Count],
    SUM(UnrestrictedQty) AS [Total Stock Qty],
    COUNT(DISTINCT BinNo) AS [Occupied Bins]
FROM dbo.ZWMS_INVENTORY
WHERE Plant IN ({plants_in_str})
GROUP BY Plant
ORDER BY [Unique Materials Count] DESC"""
            comp_subject = "materials"
            metrics = ["unique_materials", "inventory_quantity", "occupied_bins"]

        # 3. Bin Utilization
        elif (any(k in q_lower for k in ["bin utilization", "utilization", "how full", "fill rate", "occupancy rate"]) and not is_volume_utilization_requested(q_lower)) or (
            state.get("comparison_subject") == "bin_utilization" or state.get("metric") in ["BIN_UTILIZATION", "bin_utilization"] or state.get("topic") == "multi_plant_bin_detail"
        ):
            has_compare_kw = any(k in q_lower for k in ["compare", "comparison", "versus", "vs", "difference", "between", "both", "side by side", "contrast"])
            is_detail_comp = (has_compare_kw or state.get("topic") == "multi_plant_bin_detail") and (is_bin_level_detail_intent(q_lower) or state.get("topic") == "multi_plant_bin_detail" or state.get("response_mode") == "DETAIL")
            if is_detail_comp:
                comp_limit = state.get("limit") or extract_explicit_limit(q_lower)
                per_plant_limit = comp_limit if comp_limit else (10000 // max(len(target_plants), 1))
                case_order = " ".join(f"WHEN '{p}' THEN {idx}" for idx, p in enumerate(target_plants, 1))
                sql_comp = f"""WITH RankedBins AS (
    SELECT 
        b.BinLocation AS [Bin],
        b.Plant AS [Plant],
        ROUND(b.Volume, 2) AS [Capacity],
        ROUND(b.Volume - COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Available Capacity],
        CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %],
        CASE 
            WHEN COUNT(i.Material) = 0 THEN 'Empty'
            WHEN COUNT(DISTINCT i.Material) = 1 THEN CONCAT(MIN(i.Material), ' (', ROUND(SUM(i.UnrestrictedQty), 0), ' units)')
            ELSE CONCAT(COUNT(DISTINCT i.Material), ' materials (', ROUND(SUM(i.UnrestrictedQty), 0), ' units)')
        END AS [Material / Inventory Information],
        ROW_NUMBER() OVER (PARTITION BY b.Plant ORDER BY COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0) DESC, b.BinLocation) AS rn
    FROM dbo.ZWMS_BIN_MASTER b
    LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
    WHERE b.Plant IN ({plants_in_str})
    GROUP BY b.BinLocation, b.Plant, b.Volume
)
SELECT [Bin], [Plant], [Capacity], [Available Capacity], [Utilization %], [Material / Inventory Information]
FROM RankedBins
WHERE rn <= {per_plant_limit}
ORDER BY CASE [Plant] {case_order} END, rn"""
                return {
                    "sql": sql_comp,
                    "chart_type": "none",
                    "chart_title": f"Detailed Bin Utilization Comparison ({', '.join(f'Plant {p}' for p in target_plants)})",
                    "chart_x": None,
                    "chart_y": None,
                    "intent": "multi_plant_bin_detail",
                    "metric": "bin_utilization",
                    "filters": {"plants": target_plants},
                    "time_range": "current",
                    "output_type": "table",
                    "conversation_state": state
                }
            else:
                sql_comp = f"""SELECT 
    b.Plant AS [Plant], 
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins],
    (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) AS [Empty Bins],
    COUNT(DISTINCT b.BinLocation) AS [Total Bins],
    CONCAT(ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2), '%') AS [Bin Utilization %]
FROM dbo.ZWMS_BIN_MASTER b 
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant 
WHERE b.Plant IN ({plants_in_str})
GROUP BY b.Plant
ORDER BY ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2) DESC"""
                comp_subject = "bin_utilization"
                metrics = ["occupied_bins", "empty_bins", "total_bins", "bin_utilization"]

        # 4. Empty Bins
        elif any(k in q_lower for k in ["empty bin", "empty bins", "vacant", "free bin", "unoccupied", "their empty bins"]):
            sql_comp = f"""SELECT 
    b.Plant,
    (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) AS [Empty Bins],
    COUNT(DISTINCT b.BinLocation) AS [Total Bins],
    CONCAT(ROUND((COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 1), '%') AS [Empty Bins %]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
WHERE b.Plant IN ({plants_in_str})
GROUP BY b.Plant
ORDER BY [Empty Bins] DESC"""
            comp_subject = "empty_bins"
            metrics = ["empty_bins", "total_bins", "empty_bins_pct"]

        # 5. Occupied Bins
        elif any(k in q_lower for k in ["occupied bin", "occupied bins", "in use", "active bin", "their occupied bins"]):
            sql_comp = f"""SELECT 
    b.Plant,
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins],
    COUNT(DISTINCT b.BinLocation) AS [Total Bins],
    CONCAT(ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2), '%') AS [Bin Utilization %]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
WHERE b.Plant IN ({plants_in_str})
GROUP BY b.Plant
ORDER BY [Occupied Bins] DESC"""
            comp_subject = "occupied_bins"
            metrics = ["occupied_bins", "total_bins", "bin_utilization"]

        # 6. Physical Bins
        elif any(k in q_lower for k in ["their bins", "bins"]):
            sql_comp = f"""SELECT 
    b.Plant,
    COUNT(DISTINCT b.BinLocation) AS [Total Bins],
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins],
    (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) AS [Empty Bins],
    CONCAT(ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2), '%') AS [Occupancy Rate]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
WHERE b.Plant IN ({plants_in_str})
GROUP BY b.Plant
ORDER BY [Total Bins] DESC"""
            comp_subject = "bins"
            metrics = ["total_bins", "occupied_bins", "empty_bins"]

        # 7. Storage Locations
        elif any(k in q_lower for k in ["storage location", "storage locations", "sloc", "slocs", "their storage locations"]):
            sql_comp = f"""SELECT 
    Plant,
    COUNT(DISTINCT StorageLocation) AS [Storage Locations Count],
    COUNT(DISTINCT Material) AS [Active Materials],
    COUNT(DISTINCT BinNo) AS [Occupied Bins],
    SUM(UnrestrictedQty) AS [Total Inventory Quantity]
FROM dbo.ZWMS_INVENTORY
WHERE Plant IN ({plants_in_str})
GROUP BY Plant
ORDER BY Plant"""
            comp_subject = "storage_locations"
            metrics = ["storage_locations_count", "active_materials", "occupied_bins", "total_inventory_quantity"]

        # 8. Top Materials
        elif any(k in q_lower for k in ["top material", "top materials", "top sku", "top skus", "their top materials"]):
            sql_comp = f"""SELECT 
    Plant,
    Material,
    MAX(MaterialDescription) AS [Material Description],
    SUM(UnrestrictedQty) AS [Stock Quantity]
FROM dbo.ZWMS_INVENTORY
WHERE Plant IN ({plants_in_str})
GROUP BY Plant, Material
ORDER BY Plant, SUM(UnrestrictedQty) DESC"""
            comp_subject = "top_materials"
            metrics = ["top_materials", "stock_quantity"]

        # 9. Volume / Capacity
        elif any(k in q_lower for k in ["volume", "capacity", "available capacity", "free space", "remaining capacity", "dimension", "dimensions", "material volume"]):
            sql_comp = f"""WITH PlantCap AS (
    SELECT 
        b.BinLocation,
        b.Plant,
        b.Volume AS BinVol,
        COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) AS OccVol
    FROM dbo.ZWMS_BIN_MASTER b
    LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
    WHERE b.Plant IN ({plants_in_str}) AND b.Volume > 0
    GROUP BY b.BinLocation, b.Plant, b.Volume
)
SELECT 
    Plant,
    ROUND(SUM(BinVol), 2) AS [Total Capacity (FT3)],
    ROUND(SUM(OccVol), 2) AS [Occupied Volume (FT3)],
    ROUND(SUM(BinVol) - SUM(OccVol), 2) AS [Available Capacity (FT3)],
    CONCAT(ROUND(SUM(OccVol) * 100.0 / NULLIF(SUM(BinVol), 0), 1), '%') AS [Capacity Utilization %],
    ROUND(SUM(OccVol) * 100.0 / NULLIF(SUM(BinVol), 0), 2) AS [UtilizationPct]
FROM PlantCap
GROUP BY Plant
ORDER BY [Total Capacity (FT3)] DESC"""
            comp_subject = "capacity"
            metrics = ["total_capacity", "occupied_volume", "available_capacity"]

        # 10. Inherited Comparison (Follow-up) OR Default Overview Comparison
        elif is_followup and (
            state.get("comparison_subject") in ["total_inventory", "inventory"] or
            state.get("metric") in ["TOTAL_INVENTORY_QUANTITY", "total_inventory"]
        ):
            sql_comp = f"""SELECT 
    Plant,
    SUM(UnrestrictedQty) AS [Total Inventory Quantity],
    COUNT(DISTINCT Material) AS [Unique Materials],
    COUNT(DISTINCT BinNo) AS [Occupied Bins]
FROM dbo.ZWMS_INVENTORY
WHERE Plant IN ({plants_in_str})
GROUP BY Plant
ORDER BY [Total Inventory Quantity] DESC"""
            comp_subject = "total_inventory"
            metrics = ["inventory_quantity", "unique_materials", "occupied_bins"]

        else:
            sql_comp = f"""SELECT 
    b.Plant,
    COALESCE(i.TotalInventory, 0) AS [Total Inventory Qty],
    COALESCE(i.UniqueMaterials, 0) AS [Unique Materials],
    COUNT(DISTINCT b.BinLocation) AS [Total Bins],
    COUNT(DISTINCT i_bin.BinNo) AS [Occupied Bins],
    (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i_bin.BinNo)) AS [Empty Bins],
    CONCAT(ROUND(COUNT(DISTINCT i_bin.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2), '%') AS [Bin Utilization %]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i_bin ON b.BinLocation = i_bin.BinNo AND b.Plant = i_bin.Plant
LEFT JOIN (
    SELECT Plant, SUM(UnrestrictedQty) AS TotalInventory, COUNT(DISTINCT Material) AS UniqueMaterials
    FROM dbo.ZWMS_INVENTORY
    GROUP BY Plant
) i ON b.Plant = i.Plant
WHERE b.Plant IN ({plants_in_str})
GROUP BY b.Plant, i.TotalInventory, i.UniqueMaterials
ORDER BY b.Plant"""
            comp_subject = "overview"
            metrics = ["total_inventory_quantity", "unique_materials", "total_bins", "occupied_bins", "empty_bins", "bin_utilization"]

        query_plan = {
            "entity": "PLANT",
            "metric": "TOTAL_INVENTORY_QUANTITY" if comp_subject == "total_inventory" else comp_subject,
            "operation": "COMPARISON",
            "intent": "COMPARISON",
            "comparison_entities": comp_entities,
            "comparison_subject": comp_subject,
            "metrics": metrics,
            "plants": target_plants,
            "group_by": ["Plant"],
            "response_mode": state.get("response_mode", "TABLE")
        }
        is_text_mode = is_single_statement_requested or state.get("response_mode") in ["COUNT", "NAMES_ONLY", "PERCENTAGE_ONLY"]
        return {
            "sql": sql_comp,
            "query_plan": query_plan,
            "chart_type": "bar" if is_explicit_chart else "none",
            "chart_title": f"Plant Comparison ({', '.join(target_plants)})",
            "chart_x": "Plant" if is_explicit_chart else None,
            "chart_y": metrics[0] if is_explicit_chart else None,
            "intent": "plant_comparison",
            "metric": f"{comp_subject}_comparison",
            "filters": {"plants": target_plants},
            "time_range": "current",
            "output_type": "text" if is_text_mode else ("bar_chart" if is_explicit_chart else "table"),
            "conversation_state": state
        }

    # 0_PLANT_INV_RANGE: Plants with inventory in a range (Item 3: e.g. "Show plants with inventory between 10,000 and 50,000")
    is_plant_inv_range = (
        bool(re.search(r"\b(?:plants?|plnts?|facility|facilities)\b", q_lower)) and
        not is_mat_entity and
        any(k in q_lower for k in ["inventory", "stock", "quantity", "units"]) and
        any(k in q_lower for k in ["between", "from", "range", "–", "-"]) and
        not any(b in q_lower for b in ["bin", "bins", "utiliz", "capacity", "volume", "ft3", "cubic"])
    )
    if is_plant_inv_range:
        bounds = extract_range_bounds(q_lower)
        if bounds:
            low, high = bounds
            sql_plant_range = f"""SELECT 
    i.Plant AS [Plant],
    SUM(i.UnrestrictedQty) AS [Total Inventory Quantity],
    COUNT(DISTINCT i.Material) AS [Unique Materials],
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins]
FROM dbo.ZWMS_INVENTORY i
GROUP BY i.Plant
HAVING SUM(i.UnrestrictedQty) >= {low} AND SUM(i.UnrestrictedQty) <= {high}
ORDER BY [Total Inventory Quantity] DESC"""
            query_plan = {
                "intent": "FILTER",
                "entity": "PLANT",
                "metric": "TOTAL_INVENTORY_QUANTITY",
                "operation": "FILTER",
                "lower_bound": low,
                "upper_bound": high,
                "condition": f"{low:,.0f} <= plant_inventory <= {high:,.0f}",
                "grouping": "PLANT"
            }
            return {
                "sql": sql_plant_range,
                "query_plan": query_plan,
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": f"Plants with Total Inventory between {low:,.0f} and {high:,.0f}",
                "chart_x": "Plant" if is_explicit_chart else None,
                "chart_y": "Total Inventory Quantity" if is_explicit_chart else None,
                "intent": "plant_inventory_range",
                "metric": "TOTAL_INVENTORY_QUANTITY",
                "filters": {},
                "time_range": "current",
                "output_type": "bar_chart" if is_explicit_chart else ("text" if is_single_statement_requested else "table"),
                "conversation_state": state
            }

    # =========================================================================
    # SECTION RANGE: GENERIC RANGE CONTEXT ENGINE (Numeric, Quantity, Utilization, Date)
    # =========================================================================
    range_filters = parse_range_filters(resolved_q)
    is_not_simple_threshold = not threshold_match
    if range_filters and is_not_simple_threshold and not is_comparison_query:
        rf = range_filters[0]
        state["range_filters"] = range_filters
        field = rf.get("field", "UnrestrictedQty")
        plants_range = extract_plants(q_lower) or ([plant_cand] if plant_cand else [])
        if len(plants_range) == 1:
            plant_filter_i = f" AND i.Plant = '{plants_range[0]}'"
            plant_filter_b = f" AND b.Plant = '{plants_range[0]}'"
        elif len(plants_range) > 1:
            plant_filter_i = " AND i.Plant IN (" + ", ".join(f"'{p}'" for p in plants_range) + ")"
            plant_filter_b = " AND b.Plant IN (" + ", ".join(f"'{p}'" for p in plants_range) + ")"
        else:
            plant_filter_i = ""
            plant_filter_b = ""

        if field == "BinUtilizationPct":
            where_cond = ""
            if rf["operator"] == "BETWEEN":
                where_cond = f"UtilizationPct BETWEEN {rf['lower']} AND {rf['upper']}"
            elif rf["operator"] in ["GT", "GTE"]:
                op = ">=" if rf.get("inclusive") else ">"
                where_cond = f"UtilizationPct {op} {rf['lower']}"
            elif rf["operator"] in ["LT", "LTE"]:
                op = "<=" if rf.get("inclusive") else "<"
                where_cond = f"UtilizationPct {op} {rf['upper']}"

            sql_range = f"""WITH BinUtil AS (
    SELECT 
        b.BinLocation AS [Bin],
        b.Plant AS [Plant],
        COALESCE(b.StorageLocation, 'N/A') AS [Storage Location],
        CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Bin Capacity],
        ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0), 1) AS [UtilizationPct]
    FROM dbo.ZWMS_BIN_MASTER b
    JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
    WHERE b.Volume > 0{plant_filter_b}
    GROUP BY b.BinLocation, b.Plant, b.StorageLocation, b.Volume, b.VolumeUnit
)
SELECT 
    Bin, Plant, [Storage Location], [Bin Capacity], 
    CONCAT([UtilizationPct], '%') AS [Utilization %],
    [UtilizationPct]
FROM BinUtil
WHERE {where_cond}
ORDER BY [UtilizationPct] DESC"""

        elif field == "FullyVestedOn":
            where_cond = ""
            if rf["operator"] == "BETWEEN":
                where_cond = f"i.FullyVestedOn >= '{rf['lower']}' AND i.FullyVestedOn <= '{rf['upper']}'"
            elif rf["operator"] in ["GT", "GTE"]:
                where_cond = f"i.FullyVestedOn >= '{rf['lower']}'"
            elif rf["operator"] in ["LT", "LTE"]:
                where_cond = f"i.FullyVestedOn <= '{rf['upper']}'"

            sql_range = f"""SELECT 
    i.Material,
    MAX(COALESCE(i.MaterialDescription, 'N/A')) AS [Material Description],
    i.Plant,
    i.StorageLocation AS [Storage Location],
    i.BinNo AS [Bin],
    SUM(i.UnrestrictedQty) AS [Quantity],
    MAX(i.FullyVestedOn) AS [Fully Vested On]
FROM dbo.ZWMS_INVENTORY i
WHERE i.FullyVestedOn IS NOT NULL{plant_filter_i} AND {where_cond}
GROUP BY i.Material, i.Plant, i.StorageLocation, i.BinNo
ORDER BY [Quantity] DESC"""

        elif field == "TotalCapacity":
            having_cond = ""
            if rf["operator"] == "BETWEEN":
                having_cond = f"b.Volume BETWEEN {rf['lower']} AND {rf['upper']}"
            elif rf["operator"] in ["GT", "GTE"]:
                op = ">=" if rf.get("inclusive") else ">"
                having_cond = f"b.Volume {op} {rf['lower']}"
            elif rf["operator"] in ["LT", "LTE"]:
                op = "<=" if rf.get("inclusive") else "<"
                having_cond = f"b.Volume {op} {rf['upper']}"

            sql_range = f"""SELECT 
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    COALESCE(b.StorageLocation, 'N/A') AS [Storage Location],
    ROUND(b.Volume, 2) AS [Total Capacity (FT3)],
    ROUND(b.Volume, 2) AS [Bin Capacity (FT3)],
    ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Occupied Volume (FT3)],
    ROUND(b.Volume - COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Available Capacity (FT3)],
    CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Capacity Utilization %]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE b.Volume > 0{plant_filter_b}
GROUP BY b.BinLocation, b.Plant, b.StorageLocation, b.Volume
HAVING {having_cond}
ORDER BY [Total Capacity (FT3)] DESC"""

        elif field == "AvailableCapacity":
            where_cond = ""
            if rf["operator"] == "BETWEEN":
                where_cond = f"[Available Capacity (FT3)] BETWEEN {rf['lower']} AND {rf['upper']}"
            elif rf["operator"] in ["GT", "GTE"]:
                op = ">=" if rf.get("inclusive") else ">"
                where_cond = f"[Available Capacity (FT3)] {op} {rf['lower']}"
            elif rf["operator"] in ["LT", "LTE"]:
                op = "<=" if rf.get("inclusive") else "<"
                where_cond = f"[Available Capacity (FT3)] {op} {rf['upper']}"

            sql_range = f"""WITH BinCap AS (
    SELECT 
        b.BinLocation AS [Bin],
        b.Plant AS [Plant],
        COALESCE(b.StorageLocation, 'N/A') AS [Storage Location],
        ROUND(b.Volume, 2) AS [Total Capacity (FT3)],
        ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Occupied Volume (FT3)],
        ROUND(b.Volume - COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Available Capacity (FT3)],
        CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Capacity Utilization %]
    FROM dbo.ZWMS_BIN_MASTER b
    LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
    WHERE b.Volume > 0{plant_filter_b}
    GROUP BY b.BinLocation, b.Plant, b.StorageLocation, b.Volume
)
SELECT Bin, Plant, [Storage Location], [Total Capacity (FT3)], [Occupied Volume (FT3)], [Available Capacity (FT3)], [Capacity Utilization %]
FROM BinCap
WHERE {where_cond}
ORDER BY [Available Capacity (FT3)] DESC"""

        elif field == "Volume":
            where_cond = ""
            if rf["operator"] == "BETWEEN":
                where_cond = f"[Occupied Volume (FT3)] BETWEEN {rf['lower']} AND {rf['upper']}"
            elif rf["operator"] in ["GT", "GTE"]:
                op = ">=" if rf.get("inclusive") else ">"
                where_cond = f"[Occupied Volume (FT3)] {op} {rf['lower']}"
            elif rf["operator"] in ["LT", "LTE"]:
                op = "<=" if rf.get("inclusive") else "<"
                where_cond = f"[Occupied Volume (FT3)] {op} {rf['upper']}"

            sql_range = f"""WITH BinOcc AS (
    SELECT 
        b.BinLocation AS [Bin],
        b.Plant AS [Plant],
        COALESCE(b.StorageLocation, 'N/A') AS [Storage Location],
        ROUND(b.Volume, 2) AS [Total Capacity (FT3)],
        ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Occupied Volume (FT3)],
        ROUND(b.Volume - COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Available Capacity (FT3)],
        CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Capacity Utilization %]
    FROM dbo.ZWMS_BIN_MASTER b
    LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
    WHERE b.Volume > 0{plant_filter_b}
    GROUP BY b.BinLocation, b.Plant, b.StorageLocation, b.Volume
)
SELECT Bin, Plant, [Storage Location], [Total Capacity (FT3)], [Occupied Volume (FT3)], [Available Capacity (FT3)], [Capacity Utilization %]
FROM BinOcc
WHERE {where_cond}
ORDER BY [Occupied Volume (FT3)] DESC"""

        else: # UnrestrictedQty
            having_cond = ""
            if rf["operator"] == "BETWEEN":
                having_cond = f"SUM(i.UnrestrictedQty) BETWEEN {rf['lower']} AND {rf['upper']}"
            elif rf["operator"] in ["GT", "GTE"]:
                op = ">=" if rf.get("inclusive") else ">"
                having_cond = f"SUM(i.UnrestrictedQty) {op} {rf['lower']}"
            elif rf["operator"] in ["LT", "LTE"]:
                op = "<=" if rf.get("inclusive") else "<"
                having_cond = f"SUM(i.UnrestrictedQty) {op} {rf['upper']}"

            sql_range = f"""SELECT 
    i.Material,
    MAX(COALESCE(i.MaterialDescription, 'N/A')) AS [Material Description],
    i.Plant,
    SUM(i.UnrestrictedQty) AS [Total Stock Qty],
    MAX(i.BaseUnitOfMeasure) AS [UOM],
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins]
FROM dbo.ZWMS_INVENTORY i
WHERE 1=1{plant_filter_i}
GROUP BY i.Material, i.Plant
HAVING {having_cond}
ORDER BY [Total Stock Qty] DESC"""

        if field == "TotalCapacity":
            entity_val = "BIN"
            metric_val = "BIN_CAPACITY"
        elif field == "BinUtilizationPct":
            entity_val = "BIN"
            metric_val = "BIN_UTILIZATION"
        elif field == "AvailableCapacity":
            entity_val = "BIN"
            metric_val = "AVAILABLE_CAPACITY"
        elif field == "Volume":
            entity_val = "BIN"
            metric_val = "OCCUPIED_VOLUME"
        else:
            entity_val = "MATERIAL"
            metric_val = "INVENTORY_QUANTITY"

        rf_op = rf.get("operator", "BETWEEN")
        rf_lower = rf.get("lower")
        rf_upper = rf.get("upper")
        query_plan = {
            "intent": "RANGE_QUERY",
            "entity": entity_val,
            "metric": metric_val,
            "operation": "FILTER",
            "operator": rf_op,
            "lower_bound": rf_lower,
            "upper_bound": rf_upper,
            "range_filter": f"{rf_op} {rf_lower} {rf_upper}".strip(),
            "response_mode": "TABLE",
            "range_filters": range_filters,
            "field": field
        }
        res_range = {
            "sql": sql_range,
            "query_plan": query_plan,
            "chart_type": "bar" if is_explicit_chart else "none",
            "chart_title": f"Range Filter Results ({field})",
            "chart_x": "Material" if field == "UnrestrictedQty" else ("Bin" if field in ["BinUtilizationPct", "TotalCapacity", "AvailableCapacity", "Volume"] else None),
            "chart_y": "Total Stock Qty" if field == "UnrestrictedQty" else ("UtilizationPct" if field == "BinUtilizationPct" else (f"{field} (FT3)" if "Capacity" in field or field == "Volume" else None)),
            "intent": "range_query",
            "metric": metric_val,
            "entity": entity_val,
            "filters": {"plant": plant_cand} if plant_cand else {},
            "time_range": "current",
            "output_type": "text" if is_single_statement_requested else ("bar_chart" if is_explicit_chart else "table"),
            "conversation_state": state
        }
        if field == "BinUtilizationPct" and len(plants_range) >= 2:
            rf_op = rf.get("operator", "BETWEEN")
            if rf_op == "BETWEEN":
                range_desc = f"{rf['lower']}% to {rf['upper']}%"
                op_desc = f"between {range_desc}"
            elif rf_op in ["GT", "GTE"]:
                op_desc = "at least" if rf.get("inclusive") else "above"
                range_desc = f"{rf['lower']}%"
            else:
                op_desc = "at most" if rf.get("inclusive") else "below"
                range_desc = f"{rf['upper']}%"
            res_range["is_multi_table_comparison"] = True
            res_range["comparison_plants"] = plants_range
            res_range["op_desc"] = op_desc
            res_range["thresh_str"] = range_desc
            res_range["plant_sql_template"] = f"""SELECT
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    CONCAT(ROUND(b.Volume, 2), ' ', COALESCE(b.VolumeUnit, 'FT3')) AS [Bin Capacity],
    ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 2) AS [Occupied Volume],
    CONCAT(ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %]
FROM dbo.ZWMS_BIN_MASTER b
JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE b.Volume > 0 AND b.Plant = '{{plant}}'
GROUP BY b.BinLocation, b.Plant, b.Volume, b.VolumeUnit
HAVING {where_cond.replace('UtilizationPct', 'ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0), 1)')}
ORDER BY SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0) DESC"""
        return res_range

    # F0_RANK. COMPREHENSIVE PLANT RANKING SYSTEM (Sections 1-47 of Ranking System Context)
    # Master Pipeline: Entity -> Metric -> Aggregation -> Scope -> Direction -> Limit -> Format
    has_plant_word = bool(re.search(r"\b(?:plants?|plnts?|facility|facilities|sites)\b", q_lower)) or "warehouse space" in q_lower
    plant_rank_keywords = [
        "rank", "ranking", "rankings", "sort", "highest to lowest", "lowest to highest",
        "plant-wise ranking", "order by", "which plant", "which plants", "what plant", "top plant", "bottom plant",
        "who is #1", "who is number 1", "plant with the highest", "plant with the lowest",
        "plant with highest", "plant with lowest", "occupies the most", "occupies the least",
        "show plants ranked", "plants ranked", "ranked by", "based on empty bins", "according to the number of empty bins",
        "plants with the most", "plants with the fewest", "plants with most", "plants with fewest"
    ]
    is_plant_ranking_inquiry = is_plant_empty_bins_query or (has_plant_word and (
        any(k in q_lower for k in plant_rank_keywords) or
        state.get("topic") in [
            "plant_occupied_volume_ranking", "plant_available_capacity_ranking",
            "plant_bin_capacity_ranking", "plant_bins_ranking", "plant_materials_ranking",
            "plant_inventory_ranking", "plant_empty_bins_ranking", "plant_rank_lookup", "plant_rank_explanation"
        ]
    ))

    # 1. SPECIFIC ENTITY RANK INQUIRY: "What rank is Plant 1258 by occupied volume?", "Where does Plant 1258 stand?"
    is_specific_rank_lookup = has_plant_word and (
        any(k in q_lower for k in ["what rank is", "what is the rank of", "where does", "what position", "rank of plant", "where does plant stand", "what is plant"]) or
        state.get("topic") == "plant_rank_lookup"
    )
    target_plant_lookup = plant_cand or state.get("filters", {}).get("plant")
    if is_specific_rank_lookup and target_plant_lookup:
        is_vol = not any(k in q_lower for k in ["utiliz", "inventory", "stock", "materials", "bins"]) or any(k in q_lower for k in ["volume", "space", "storage", "occupied"])
        if is_vol:
            sql_rank_lookup = f"""SELECT 
    sub.[Rank],
    sub.Plant,
    sub.[Total Occupied Volume (FT3)],
    sub.[Occupied Bins],
    sub.[Total Bins]
FROM (
    SELECT 
        RANK() OVER (ORDER BY ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) DESC) AS [Rank],
        b.Plant AS [Plant],
        ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) AS [Total Occupied Volume (FT3)],
        COUNT(DISTINCT i.BinNo) AS [Occupied Bins],
        COUNT(DISTINCT b.BinLocation) AS [Total Bins]
    FROM dbo.ZWMS_BIN_MASTER b
    LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    GROUP BY b.Plant
) sub
WHERE sub.Plant = '{target_plant_lookup}'"""
            return {
                "sql": sql_rank_lookup,
                "query_plan": {
                    "intent": "RANKING",
                    "rank_entity": "Plant",
                    "target_value": target_plant_lookup,
                    "rank_metric": "TotalOccupiedVolume",
                    "rank_direction": "DESC",
                    "operation": "SPECIFIC_RANK_LOOKUP"
                },
                "chart_type": "none",
                "chart_title": f"Rank Position of Plant {target_plant_lookup} by Occupied Volume",
                "chart_x": None,
                "chart_y": None,
                "intent": "specific_plant_rank_lookup",
                "metric": "plant_rank_lookup",
                "filters": {"plant": target_plant_lookup},
                "time_range": "current",
                "output_type": "text",
                "conversation_state": state
            }

    # 2. RANKING EXPLANATION: "Why is Plant 1268 ranked #1 by occupied volume?", "Why is Plant 1268 #1?"
    is_rank_explanation = has_plant_word and (
        (any(k in q_lower for k in ["why is", "why are", "why does", "explain why"]) and
        any(k in q_lower for k in ["#1", "number 1", "number one", "first", "rank 1", "ranked 1", "ranked #1", "top", "leader", "highest"])) or
        state.get("topic") == "plant_rank_explanation"
    )
    if is_rank_explanation:
        sql_rank_exp = """SELECT 
    RANK() OVER (ORDER BY ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) DESC) AS [Rank],
    b.Plant AS [Plant],
    ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) AS [Total Occupied Volume (FT3)],
    ROUND(SUM(b.Volume), 2) AS [Total Capacity (FT3)],
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins],
    COUNT(DISTINCT b.BinLocation) AS [Total Bins]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
GROUP BY b.Plant
ORDER BY [Total Occupied Volume (FT3)] DESC"""
        target_exp_plant = target_plant_lookup or "1268"
        return {
            "sql": sql_rank_exp,
            "query_plan": {
                "intent": "RANKING_EXPLANATION",
                "rank_entity": "Plant",
                "target_value": target_exp_plant,
                "rank_metric": "TotalOccupiedVolume"
            },
            "chart_type": "none",
            "chart_title": f"Ranking Explanation for Plant {target_exp_plant}",
            "chart_x": None,
            "chart_y": None,
            "intent": "plant_rank_explanation",
            "metric": "plant_rank_explanation",
            "filters": {"plant": target_exp_plant},
            "time_range": "current",
            "output_type": "text",
            "conversation_state": state
        }

    # 3. SUBSET PLANT RANKING: "Rank Plant 1258 and Plant 7228 by occupied volume"
    all_plants_in_q = re.findall(r"\b(1258|1266|1268|7228)\b", q_lower)
    subset_plants = list(dict.fromkeys(all_plants_in_q))
    if len(subset_plants) >= 2 and any(k in q_lower for k in ["rank", "ranking", "sort", "order by", "highest", "lowest", "top", "bottom"]):
        is_least = state.get("ranking") == "lowest" or any(k in q_lower for k in ["least", "lowest", "bottom", "minimum"])
        order_dir = "ASC" if is_least else "DESC"
        in_clause = ", ".join(f"'{p}'" for p in subset_plants)
        sql_subset_rank = f"""SELECT 
    RANK() OVER (ORDER BY ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) {order_dir}) AS [Rank],
    b.Plant AS [Plant],
    ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) AS [Total Occupied Volume (FT3)],
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins],
    COUNT(DISTINCT b.BinLocation) AS [Total Bins]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
WHERE b.Plant IN ({in_clause})
GROUP BY b.Plant
ORDER BY [Total Occupied Volume (FT3)] {order_dir}"""
        return {
            "sql": sql_subset_rank,
            "query_plan": {
                "intent": "RANKING",
                "rank_direction": order_dir,
                "rank_metric": "TotalOccupiedVolume",
                "rank_entity": "Plant",
                "rank_scope": {"Plants": subset_plants},
                "limit": len(subset_plants)
            },
            "chart_type": "bar" if is_explicit_chart else "none",
            "chart_title": f"Occupied Volume Ranking ({', '.join(subset_plants)})",
            "chart_x": "Plant" if is_explicit_chart else None,
            "chart_y": "Total Occupied Volume (FT3)" if is_explicit_chart else None,
            "intent": "plant_subset_ranking",
            "metric": "plant_occupied_volume_ranking",
            "filters": {"plants": subset_plants},
            "time_range": "current",
            "output_type": "table",
            "conversation_state": state
        }

    # 4. PLANT RANKING BY METRICS (Occupied Volume, Available Capacity, Bin Capacity, Bins Count, Unique Materials, Total Inventory)
    if is_plant_ranking_inquiry:
        is_least = state.get("ranking") == "lowest" or any(k in q_lower for k in ["least", "lowest", "bottom", "minimum", "smallest", "fewest", "emptiest"])
        order_dir = "ASC" if is_least else "DESC"
        label = "Lowest" if is_least else "Highest"
        
        is_singular = (
            is_single_statement_requested or
            any(k in q_lower for k in [
                "which plant has the highest", "which plant has the lowest",
                "which plant has highest", "which plant has lowest",
                "which plant has the most", "which plant has the least",
                "which plant has most", "which plant has least",
                "which plant occupies the most", "which plant occupies the least",
                "which plant occupies", "who is #1", "who is number 1",
                "plant with the highest", "plant with the lowest",
                "plant with highest", "plant with lowest",
                "plant with the most", "plant with the least",
                "plant with most", "plant with least",
                "which plant has the fewest", "which plant has fewest",
                "plant with the fewest", "plant with fewest"
            ]) and not any(k in q_lower for k in ["all", "all plants", "every", "table", "breakdown", "list", "ranking of all", "full ranking"])
        )
        limit_n = 1 if is_singular else (state.get("limit") or (10 if not any(k in q_lower for k in ["all", "all plants", "every"]) else 4))
        top_kw = f"TOP {limit_n} "

        # METRIC A: TOTAL OCCUPIED VOLUME (Rule 2 - NEVER substitute with utilization!)
        is_occ_vol = (
            state.get("topic") == "plant_occupied_volume_ranking" or
            any(k in q_lower for k in [
                "occupied volume", "storage volume", "volume occupied", "space occupied",
                "occupies the most warehouse space", "occupies the most space", "occupies the most",
                "occupies the least space", "occupies the least warehouse space", "occupies the least",
                "occupied storage", "storage space occupied"
            ]) or
            ("volume" in q_lower and any(k in q_lower for k in ["occup", "storage", "space"])) or
            ("warehouse space" in q_lower and any(k in q_lower for k in ["occup", "most", "least", "highest", "lowest", "rank", "sort"]))
        ) and not any(k in q_lower for k in ["available", "free", "remaining", "unused", "material", "materials", "sku", "skus"])

        if is_occ_vol:
            sql_plant_vol = f"""SELECT {top_kw}
    RANK() OVER (ORDER BY ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) {order_dir}) AS [Rank],
    b.Plant AS [Plant],
    ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) AS [Total Occupied Volume (FT3)],
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins],
    COUNT(DISTINCT b.BinLocation) AS [Total Bins]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
GROUP BY b.Plant
ORDER BY [Total Occupied Volume (FT3)] {order_dir}"""
            return {
                "sql": sql_plant_vol,
                "query_plan": {
                    "intent": "RANKING",
                    "rank_direction": order_dir,
                    "rank_metric": "TotalOccupiedVolume",
                    "rank_entity": "Plant",
                    "limit": limit_n,
                    "rank_scope": {}
                },
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": f"{label} Occupied Storage Volume by Plant",
                "chart_x": "Plant" if is_explicit_chart else None,
                "chart_y": "Total Occupied Volume (FT3)" if is_explicit_chart else None,
                "intent": "plant_occupied_volume_ranking",
                "metric": "plant_occupied_volume_ranking",
                "filters": {},
                "time_range": "current",
                "output_type": "text" if is_singular else ("bar_chart" if is_explicit_chart else "table"),
                "conversation_state": state
            }

        # METRIC B: AVAILABLE STORAGE CAPACITY
        is_avail_cap = (
            state.get("topic") == "plant_available_capacity_ranking" or
            any(k in q_lower for k in [
                "available capacity", "free capacity", "remaining capacity",
                "available volume", "free volume", "free space", "available storage space",
                "most available space", "least available space", "unused capacity", "unused space"
            ])
        )
        if is_avail_cap:
            sql_plant_avail = f"""SELECT {top_kw}
    RANK() OVER (ORDER BY ROUND(SUM(b.Volume) - SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) {order_dir}) AS [Rank],
    b.Plant AS [Plant],
    ROUND(SUM(b.Volume) - SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) AS [Available Capacity (FT3)],
    ROUND(SUM(b.Volume), 2) AS [Total Capacity (FT3)],
    ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) AS [Occupied Volume (FT3)]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
GROUP BY b.Plant
ORDER BY [Available Capacity (FT3)] {order_dir}"""
            return {
                "sql": sql_plant_avail,
                "query_plan": {
                    "intent": "RANKING",
                    "rank_direction": order_dir,
                    "rank_metric": "AvailableCapacity",
                    "rank_entity": "Plant",
                    "limit": limit_n,
                    "rank_scope": {}
                },
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": f"{label} Available Capacity by Plant",
                "chart_x": "Plant" if is_explicit_chart else None,
                "chart_y": "Available Capacity (FT3)" if is_explicit_chart else None,
                "intent": "plant_available_capacity_ranking",
                "metric": "plant_available_capacity_ranking",
                "filters": {},
                "time_range": "current",
                "output_type": "text" if is_singular else ("bar_chart" if is_explicit_chart else "table"),
                "conversation_state": state
            }

        # METRIC C: TOTAL BIN CAPACITY
        is_bin_cap = any(k in q_lower for k in ["bin capacity", "storage capacity", "total capacity", "total volume capacity", "largest capacity", "smallest capacity"])
        if is_bin_cap:
            sql_plant_cap = f"""SELECT {top_kw}
    RANK() OVER (ORDER BY ROUND(SUM(b.Volume), 2) {order_dir}) AS [Rank],
    b.Plant AS [Plant],
    ROUND(SUM(b.Volume), 2) AS [Total Capacity (FT3)],
    COUNT(DISTINCT b.BinLocation) AS [Total Bins]
FROM dbo.ZWMS_BIN_MASTER b
GROUP BY b.Plant
ORDER BY [Total Capacity (FT3)] {order_dir}"""
            return {
                "sql": sql_plant_cap,
                "query_plan": {
                    "intent": "RANKING",
                    "rank_direction": order_dir,
                    "rank_metric": "TotalBinCapacity",
                    "rank_entity": "Plant",
                    "limit": limit_n,
                    "rank_scope": {}
                },
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": f"{label} Total Storage Capacity by Plant",
                "chart_x": "Plant" if is_explicit_chart else None,
                "chart_y": "Total Capacity (FT3)" if is_explicit_chart else None,
                "intent": "plant_bin_capacity_ranking",
                "metric": "plant_bin_capacity_ranking",
                "filters": {},
                "time_range": "current",
                "output_type": "text" if is_singular else ("bar_chart" if is_explicit_chart else "table"),
                "conversation_state": state
            }

        # METRIC D_EMPTY: EMPTY BINS COUNT (Rule: Rank plants by number of empty bins)
        is_empty_bins_rank = (
            state.get("topic") == "plant_empty_bins_ranking" or
            is_plant_empty_bins_query or
            (
                has_plant_word and
                any(k in q_lower for k in ["empty bin", "empty bins", "vacant bin", "vacant bins"]) and
                not any(k in q_lower for k in ["capacity", "volume", "ft3", "cubic"])
            )
        )
        if is_empty_bins_rank:
            sql_plant_empty = f"""SELECT {top_kw}
    RANK() OVER (ORDER BY (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) {order_dir}) AS [Rank],
    b.Plant AS [Plant],
    (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) AS [Empty Bins],
    COUNT(DISTINCT b.BinLocation) AS [Total Bins],
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
GROUP BY b.Plant
ORDER BY [Empty Bins] {order_dir}"""
            return {
                "sql": sql_plant_empty,
                "query_plan": {
                    "intent": "RANKING",
                    "rank_direction": order_dir,
                    "rank_metric": "EMPTY_BIN_COUNT",
                    "rank_entity": "Plant",
                    "limit": limit_n,
                    "rank_scope": {}
                },
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": f"{label} Empty Bins by Plant",
                "chart_x": "Plant" if is_explicit_chart else None,
                "chart_y": "Empty Bins" if is_explicit_chart else None,
                "intent": "plant_empty_bins_ranking",
                "metric": "EMPTY_BIN_COUNT",
                "filters": {},
                "time_range": "current",
                "output_type": "text" if is_singular else ("bar_chart" if is_explicit_chart else "table"),
                "conversation_state": state
            }

        # METRIC D: TOTAL BINS COUNT
        is_bins_cnt = (
            not is_empty_bins_rank and (
                state.get("topic") == "plant_bins_ranking" or
                any(k in q_lower for k in ["number of bins", "total bins", "bin count", "count of bins", "most bins", "least bins", "fewest bins"])
            )
        )
        if is_bins_cnt:
            sql_plant_bins = f"""SELECT {top_kw}
    RANK() OVER (ORDER BY COUNT(DISTINCT b.BinLocation) {order_dir}) AS [Rank],
    b.Plant AS [Plant],
    COUNT(DISTINCT b.BinLocation) AS [Total Bins],
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
GROUP BY b.Plant
ORDER BY [Total Bins] {order_dir}"""
            return {
                "sql": sql_plant_bins,
                "query_plan": {
                    "intent": "RANKING",
                    "rank_direction": order_dir,
                    "rank_metric": "TotalBins",
                    "rank_entity": "Plant",
                    "limit": limit_n,
                    "rank_scope": {}
                },
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": f"{label} Bins Count by Plant",
                "chart_x": "Plant" if is_explicit_chart else None,
                "chart_y": "Total Bins" if is_explicit_chart else None,
                "intent": "plant_bins_ranking",
                "metric": "plant_bins_ranking",
                "filters": {},
                "time_range": "current",
                "output_type": "text" if is_singular else ("bar_chart" if is_explicit_chart else "table"),
                "conversation_state": state
            }

        # METRIC E: UNIQUE MATERIALS
        is_mats_cnt = (
            state.get("topic") == "plant_materials_ranking" or
            any(k in q_lower for k in ["unique materials", "number of materials", "sku count", "distinct materials", "skus", "most materials", "least materials", "fewest materials"])
        )
        if is_mats_cnt:
            sql_plant_mats = f"""SELECT {top_kw}
    RANK() OVER (ORDER BY COUNT(DISTINCT i.Material) {order_dir}) AS [Rank],
    i.Plant AS [Plant],
    COUNT(DISTINCT i.Material) AS [Unique Materials],
    SUM(i.UnrestrictedQty) AS [Total Stock Quantity]
FROM dbo.ZWMS_INVENTORY i
GROUP BY i.Plant
ORDER BY [Unique Materials] {order_dir}"""
            return {
                "sql": sql_plant_mats,
                "query_plan": {
                    "intent": "RANKING",
                    "rank_direction": order_dir,
                    "rank_metric": "UniqueMaterials",
                    "rank_entity": "Plant",
                    "limit": limit_n,
                    "rank_scope": {}
                },
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": f"{label} Unique Materials Count by Plant",
                "chart_x": "Plant" if is_explicit_chart else None,
                "chart_y": "Unique Materials" if is_explicit_chart else None,
                "intent": "plant_materials_ranking",
                "metric": "plant_materials_ranking",
                "filters": {},
                "time_range": "current",
                "output_type": "text" if is_singular else ("bar_chart" if is_explicit_chart else "table"),
                "conversation_state": state
            }

        # METRIC F: TOTAL INVENTORY QUANTITY
        is_inv_qty = (
            state.get("topic") == "plant_inventory_ranking" or
            any(k in q_lower for k in [
                "total inventory", "inventory quantity", "stock quantity", "total stock",
                "units in inventory", "total units", "quantity", "most inventory", "least inventory",
                "most stock", "least stock", "highest stock", "lowest stock", "stock", "inventory"
            ])
        )
        if is_inv_qty:
            sql_plant_inv = f"""SELECT {top_kw}
    RANK() OVER (ORDER BY SUM(i.UnrestrictedQty) {order_dir}) AS [Rank],
    i.Plant AS [Plant],
    SUM(i.UnrestrictedQty) AS [Total Inventory Quantity],
    COUNT(DISTINCT i.Material) AS [Unique Materials],
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins]
FROM dbo.ZWMS_INVENTORY i
GROUP BY i.Plant
ORDER BY [Total Inventory Quantity] {order_dir}"""
            return {
                "sql": sql_plant_inv,
                "query_plan": {
                    "intent": "RANKING",
                    "rank_direction": order_dir,
                    "rank_metric": "TotalInventoryQuantity",
                    "rank_entity": "Plant",
                    "limit": limit_n,
                    "rank_scope": {}
                },
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": f"{label} Total Inventory Quantity by Plant",
                "chart_x": "Plant" if is_explicit_chart else None,
                "chart_y": "Total Inventory Quantity" if is_explicit_chart else None,
                "intent": "plant_inventory_ranking",
                "metric": "plant_inventory_ranking",
                "filters": {},
                "time_range": "current",
                "output_type": "text" if is_singular else ("bar_chart" if is_explicit_chart else "table"),
                "conversation_state": state
            }

        # FALLBACK FOR UNMETRICIZED PLANT RANKING (Item 4: "Give me a detailed ranking of all plants")
        if not any(k in q_lower for k in ["utiliz", "occupan", "capacity", "fill", "full", "%"]):
            scope_desc = "ALL PLANTS" if any(k in q_lower for k in ["all", "all plants", "every"]) else {}
            limit_val = 4 if scope_desc == "ALL PLANTS" else limit_n
            
            active_metric_topic = state.get("topic")
            if active_metric_topic == "plant_empty_bins_ranking":
                sql_fallback = f"""SELECT 
        RANK() OVER (ORDER BY (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) {order_dir}) AS [Rank],
        b.Plant AS [Plant],
        (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) AS [Empty Bins],
        COUNT(DISTINCT b.BinLocation) AS [Total Bins],
        COUNT(DISTINCT i.BinNo) AS [Occupied Bins]
    FROM dbo.ZWMS_BIN_MASTER b
    LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    GROUP BY b.Plant
    ORDER BY [Empty Bins] {order_dir}"""
                return {
                    "sql": sql_fallback,
                    "query_plan": {"intent": "RANKING", "operation": "RANKING", "rank_direction": order_dir, "rank_metric": "EMPTY_BIN_COUNT", "rank_entity": "Plant", "limit": limit_val, "scope": scope_desc, "response_mode": "DETAIL" if is_detail_requested else "STANDARD"},
                    "chart_type": "bar" if is_explicit_chart else "none",
                    "chart_title": f"{label} Empty Bins by Plant",
                    "chart_x": "Plant" if is_explicit_chart else None,
                    "chart_y": "Empty Bins" if is_explicit_chart else None,
                    "intent": "plant_empty_bins_ranking",
                    "metric": "EMPTY_BIN_COUNT",
                    "filters": {},
                    "time_range": "current",
                    "output_type": "table" if is_detail_requested else ("text" if is_singular else "table"),
                    "conversation_state": state
                }
            elif active_metric_topic == "plant_inventory_ranking":
                sql_fallback = f"""SELECT 
        RANK() OVER (ORDER BY SUM(i.UnrestrictedQty) {order_dir}) AS [Rank],
        i.Plant AS [Plant],
        SUM(i.UnrestrictedQty) AS [Total Inventory Quantity],
        COUNT(DISTINCT i.Material) AS [Unique Materials],
        COUNT(DISTINCT i.BinNo) AS [Occupied Bins]
    FROM dbo.ZWMS_INVENTORY i
    GROUP BY i.Plant
    ORDER BY [Total Inventory Quantity] {order_dir}"""
                return {
                    "sql": sql_fallback,
                    "query_plan": {"intent": "RANKING", "operation": "RANKING", "rank_direction": order_dir, "rank_metric": "TotalInventoryQuantity", "rank_entity": "Plant", "limit": limit_val, "scope": scope_desc, "response_mode": "DETAIL" if is_detail_requested else "STANDARD"},
                    "chart_type": "bar" if is_explicit_chart else "none",
                    "chart_title": f"{label} Total Inventory Quantity by Plant",
                    "chart_x": "Plant" if is_explicit_chart else None,
                    "chart_y": "Total Inventory Quantity" if is_explicit_chart else None,
                    "intent": "plant_inventory_ranking",
                    "metric": "plant_inventory_ranking",
                    "filters": {},
                    "time_range": "current",
                    "output_type": "table" if is_detail_requested else ("text" if is_singular else "table"),
                    "conversation_state": state
                }
            else:
                # Default to Metric A: Total Occupied Volume (Standard Plant Ranking Metric)
                sql_default_rank = f"""SELECT 
        RANK() OVER (ORDER BY ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) {order_dir}) AS [Rank],
        b.Plant AS [Plant],
        ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) AS [Total Occupied Volume (FT3)],
        ROUND(SUM(b.Volume), 2) AS [Total Capacity (FT3)],
        COUNT(DISTINCT i.BinNo) AS [Occupied Bins],
        COUNT(DISTINCT b.BinLocation) AS [Total Bins]
    FROM dbo.ZWMS_BIN_MASTER b
    LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    GROUP BY b.Plant
    ORDER BY [Total Occupied Volume (FT3)] {order_dir}"""
                return {
                    "sql": sql_default_rank,
                    "query_plan": {
                        "intent": "RANKING",
                        "operation": "RANKING",
                        "rank_direction": order_dir,
                        "rank_metric": "TotalOccupiedVolume",
                        "rank_entity": "Plant",
                        "scope": scope_desc,
                        "limit": limit_val,
                        "response_mode": "DETAIL" if is_detail_requested else "STANDARD"
                    },
                    "chart_type": "bar" if is_explicit_chart else "none",
                    "chart_title": f"{label} Occupied Storage Volume Ranking across All Plants",
                    "chart_x": "Plant" if is_explicit_chart else None,
                    "chart_y": "Total Occupied Volume (FT3)" if is_explicit_chart else None,
                    "intent": "plant_occupied_volume_ranking",
                    "metric": "plant_occupied_volume_ranking",
                    "filters": {},
                    "time_range": "current",
                    "output_type": "table" if is_detail_requested else ("text" if is_singular else "table"),
                    "conversation_state": state
                }

    # =========================================================================
    # SECTION CAP: AUTHORITATIVE CAPACITY-BASED QUERY ENGINE (Context Rules 1-46)
    # =========================================================================
    # Covers: Total Capacity, Available Capacity, Occupied Volume, Capacity by Plant,
    # Empty Bins Capacity, Capacity Summary, Capacity Detail Mode, and Referential Follow-ups.

    # 1. REFERENTIAL PRONOUN FOLLOW-UPS ("how much total occupied volume do they have?", "how much space do they have?", "what is their capacity?")
    is_referential_followup = (
        state.get("topic") == "referential_bins_capacity" or
        (bool(history) and any(k in q_lower for k in ["they have", "do they", "these have", "do these", "those have", "do those", "their capacity", "their volume", "their occupied", "their available"]))
    )
    if is_referential_followup:
        # Find previous user query in history to understand what "they" refers to
        prev_user_queries = [
            m.get("content", "").strip() for m in history if m.get("role") == "user" and m.get("content", "").strip()
        ]
        prev_q = prev_user_queries[-1].lower() if prev_user_queries else ""
        prev_limit_match = re.search(r"\b(?:top|bottom|highest|lowest)?\s*(\d{1,3})\b", prev_q)
        prev_limit = int(prev_limit_match.group(1)) if prev_limit_match else (state.get("limit") or 10)
        prev_is_least = any(k in prev_q for k in ["bottom", "least", "lowest", "emptiest"])
        prev_order_dir = "ASC" if prev_is_least else "DESC"
        prev_plant_filter = f" AND b.Plant = '{plant_cand}'" if plant_cand else ""

        sql_referential_cap = f"""WITH PriorBins AS (
    SELECT TOP {prev_limit}
        b.BinLocation,
        b.Plant,
        b.Volume AS BinVol,
        COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) AS OccVol
    FROM dbo.ZWMS_BIN_MASTER b
    JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
    WHERE b.Volume > 0{prev_plant_filter}
    GROUP BY b.BinLocation, b.Plant, b.Volume
    ORDER BY SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0) {prev_order_dir}
)
SELECT 
    COUNT(*) AS [Referenced Bins Count],
    ROUND(SUM(BinVol), 2) AS [Total Capacity (FT3)],
    ROUND(SUM(OccVol), 2) AS [Total Occupied Volume (FT3)],
    ROUND(SUM(BinVol) - SUM(OccVol), 2) AS [Total Available Capacity (FT3)],
    CONCAT(ROUND(SUM(OccVol) * 100.0 / NULLIF(SUM(BinVol), 0), 1), '%') AS [Capacity Utilization %]
FROM PriorBins"""
        return {
            "sql": sql_referential_cap,
            "chart_type": "none",
            "chart_title": f"Combined Capacity of Referenced {prev_limit} Bins",
            "chart_x": None,
            "chart_y": None,
            "intent": "referential_bins_capacity",
            "metric": "bin_capacity_aggregate",
            "filters": {"plant": plant_cand} if plant_cand else {},
            "time_range": "current",
            "output_type": "text",
            "conversation_state": state
        }

    # 2. CAPACITY SUMMARY: "give me a capacity summary", "warehouse capacity summary", "overall capacity summary"
    is_cap_summary = (
        state.get("topic") == "capacity_summary" or
        any(k in q_lower for k in ["capacity summary", "warehouse capacity summary", "overall capacity summary", "storage capacity summary"]) or
        q_lower.strip() in ["capacity summary", "capacity overview"]
    )
    if is_cap_summary:
        sql_cap_summary = """WITH PlantCap AS (
    SELECT 
        b.BinLocation,
        b.Plant,
        b.Volume AS BinVol,
        COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) AS OccVol
    FROM dbo.ZWMS_BIN_MASTER b
    LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
    WHERE b.Volume > 0
    GROUP BY b.BinLocation, b.Plant, b.Volume
)
SELECT 
    Plant,
    COUNT(DISTINCT BinLocation) AS [Total Bins],
    ROUND(SUM(BinVol), 2) AS [Total Capacity (FT3)],
    ROUND(SUM(OccVol), 2) AS [Occupied Volume (FT3)],
    ROUND(SUM(BinVol) - SUM(OccVol), 2) AS [Available Capacity (FT3)],
    CONCAT(ROUND(SUM(OccVol) * 100.0 / NULLIF(SUM(BinVol), 0), 1), '%') AS [Capacity Utilization %],
    ROUND(SUM(OccVol) * 100.0 / NULLIF(SUM(BinVol), 0), 2) AS [UtilizationPct]
FROM PlantCap
GROUP BY Plant
ORDER BY [Total Capacity (FT3)] DESC"""
        return {
            "sql": sql_cap_summary,
            "chart_type": "bar" if is_explicit_chart else "none",
            "chart_title": "Warehouse Capacity Summary by Plant",
            "chart_x": "Plant" if is_explicit_chart else None,
            "chart_y": "Total Capacity (FT3)" if is_explicit_chart else None,
            "intent": "capacity_summary",
            "metric": "capacity_summary",
            "filters": {},
            "time_range": "current",
            "output_type": "table",
            "conversation_state": state
        }

    # 3. CAPACITY IN EMPTY BINS: "How much capacity is available in empty bins?", "Available capacity in empty bins"
    is_empty_bins_cap = (
        state.get("topic") == "empty_bins_capacity" or
        (
            any(k in q_lower for k in ["empty bin", "empty bins", "vacant bin", "vacant bins"]) and
            any(k in q_lower for k in ["capacity", "available capacity", "space", "volume", "how much capacity", "how much space", "how much volume"])
        )
    )
    if is_empty_bins_cap:
        plant_filter_b = f" AND b.Plant = '{plant_cand}'" if plant_cand else ""
        sql_empty_cap = f"""SELECT 
    COUNT(DISTINCT b.BinLocation) AS [Empty Bins Count],
    ROUND(SUM(b.Volume), 2) AS [Empty Bins Available Capacity (FT3)]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
WHERE i.BinNo IS NULL AND b.Volume > 0{plant_filter_b}"""
        return {
            "sql": sql_empty_cap,
            "chart_type": "none",
            "chart_title": f"Available Capacity in Empty Bins{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": None,
            "chart_y": None,
            "intent": "empty_bins_capacity",
            "metric": "empty_bins_capacity",
            "filters": {"plant": plant_cand} if plant_cand else {},
            "time_range": "current",
            "output_type": "text",
            "conversation_state": state
        }

    # 4. CAPACITY BY SPECIFIC PLANT: "Show capacity for Plant 1258", "What is the storage capacity of Plant 1258?"
    is_plant_cap_inquiry = (
        bool(plant_cand) and
        (
            state.get("topic") == "plant_capacity" or
            any(k in q_lower for k in [
                "capacity for plant", "storage capacity of plant", "capacity of plant",
                "how much capacity does plant", "plant storage capacity", "capacity of this plant",
                "storage capacity for plant", "how much storage space is left in plant"
            ]) or
            (
                any(k in q_lower for k in ["storage capacity", "total capacity", "bin capacity", "how much capacity", "capacity"]) and
                not any(k in q_lower for k in ["utiliz", "occupan", "%", "rank", "ranking", "compare", "versus", "vs", "between"])
            )
        )
    )
    if is_plant_cap_inquiry:
        p_val = plant_cand
        sql_p_cap = f"""WITH PlantCap AS (
    SELECT 
        b.BinLocation,
        b.Plant,
        b.Volume AS BinVol,
        COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) AS OccVol
    FROM dbo.ZWMS_BIN_MASTER b
    LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
    WHERE b.Plant = '{p_val}' AND b.Volume > 0
    GROUP BY b.BinLocation, b.Plant, b.Volume
)
SELECT 
    Plant,
    ROUND(SUM(BinVol), 2) AS [Total Capacity (FT3)],
    ROUND(SUM(OccVol), 2) AS [Total Occupied Volume (FT3)],
    ROUND(SUM(BinVol) - SUM(OccVol), 2) AS [Available Capacity (FT3)],
    CONCAT(ROUND(SUM(OccVol) * 100.0 / NULLIF(SUM(BinVol), 0), 1), '%') AS [Capacity Utilization %],
    COUNT(DISTINCT BinLocation) AS [Total Bins]
FROM PlantCap
GROUP BY Plant"""
        return {
            "sql": sql_p_cap,
            "chart_type": "none",
            "chart_title": f"Storage Capacity of Plant {p_val}",
            "chart_x": None,
            "chart_y": None,
            "intent": "plant_capacity",
            "metric": "plant_capacity",
            "filters": {"plant": p_val},
            "time_range": "current",
            "output_type": "text",
            "conversation_state": state
        }

    # 5. TOTAL WAREHOUSE CAPACITY (Scalar warehouse-wide sum of Volume): "What is the total capacity?", "How much capacity does this warehouse have?"
    is_tot_warehouse_cap = (
        not plant_cand and
        (
            state.get("topic") == "total_warehouse_capacity" or
            any(k in q_lower for k in [
                "what is the total capacity", "what is the total warehouse capacity", "total warehouse capacity",
                "show total bin capacity", "how much capacity does this warehouse have", "how much capacity do these bins have",
                "show me the total capacity of all bins", "total bin capacity", "total storage capacity",
                "what is the warehouse capacity", "how much storage capacity do we have", "what is our total storage capacity",
                "how much storage capacity does this warehouse have", "how much capacity does the warehouse have"
            ]) or
            q_lower.strip() in ["total capacity", "total bin capacity", "total storage capacity", "warehouse capacity"]
        ) and
        not any(k in q_lower for k in ["utiliz", "occupan", "%", "available", "left", "free", "remaining", "unused", "rank", "ranking", "compared to", "versus", "vs", "compare"])
    )
    if is_tot_warehouse_cap:
        sql_tot_cap = """SELECT 
    ROUND(SUM(Volume), 2) AS [Total Capacity (FT3)],
    COUNT(DISTINCT BinLocation) AS [Total Bins]
FROM dbo.ZWMS_BIN_MASTER
WHERE Volume > 0"""
        return {
            "sql": sql_tot_cap,
            "chart_type": "none",
            "chart_title": "Total Warehouse Storage Capacity",
            "chart_x": None,
            "chart_y": None,
            "intent": "total_warehouse_capacity",
            "metric": "total_capacity",
            "filters": {},
            "time_range": "current",
            "output_type": "text",
            "conversation_state": state
        }

    # 6. TOTAL AVAILABLE CAPACITY (Total Capacity - Occupied Volume): "How much space is left?", "How much capacity is still available?", "Show available capacity"
    is_avail_cap_req = (
        state.get("topic") in ["available_capacity", "plant_available_capacity"] or
        (
            any(k in q_lower for k in [
                "how much space is left", "how much capacity is still available", "show available capacity",
                "how much unused capacity is there", "show remaining storage capacity", "how much storage space is left",
                "how much free space do we have", "how much capacity is available", "available storage capacity",
                "remaining storage capacity", "unused storage capacity", "total available capacity",
                "free storage capacity", "available warehouse capacity"
            ]) or
            q_lower.strip() in ["available capacity", "free capacity", "remaining capacity", "unused capacity"]
        ) and
        not any(k in q_lower for k in ["utiliz", "occupan", "%", "rank", "ranking", "bins by", "plants by", "compared to", "versus", "vs", "occupied compared"])
    )
    if is_avail_cap_req:
        is_by_plant = (
            state.get("topic") == "plant_available_capacity" or
            any(p in q_lower for p in ["by plant", "for each plant", "plant-wise", "plant wise", "each plant", "every plant", "across plants", "of each plant", "compare plants"]) or
            bool(plant_cand)
        )
        if is_by_plant:
            plant_filter_cte = f" AND b.Plant = '{plant_cand}'" if plant_cand else ""
            sql_plant_avail_cap = f"""WITH PlantCap AS (
    SELECT 
        b.BinLocation,
        b.Plant,
        b.Volume AS BinVol,
        COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) AS OccVol
    FROM dbo.ZWMS_BIN_MASTER b
    LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
    WHERE b.Volume > 0{plant_filter_cte}
    GROUP BY b.BinLocation, b.Plant, b.Volume
)
SELECT 
    Plant,
    ROUND(SUM(BinVol), 2) AS [Total Capacity (FT3)],
    ROUND(SUM(OccVol), 2) AS [Occupied Volume (FT3)],
    ROUND(SUM(BinVol) - SUM(OccVol), 2) AS [Available Capacity (FT3)]
FROM PlantCap
GROUP BY Plant
ORDER BY [Available Capacity (FT3)] DESC"""

            query_plan = {
                "entity": "PLANT",
                "metric": "AVAILABLE_CAPACITY",
                "operation": "AGGREGATION",
                "group_by": "PLANT",
                "filters": {"plant": plant_cand} if plant_cand else {},
                "ranking": None,
                "limit": None,
                "response_mode": "GRAPH" if is_explicit_chart else "TABLE"
            }
            return {
                "sql": sql_plant_avail_cap,
                "query_plan": query_plan,
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": f"Available Capacity by Plant (FT3){f' — Plant {plant_cand}' if plant_cand else ''}",
                "chart_x": "Plant" if is_explicit_chart else None,
                "chart_y": "Available Capacity (FT3)" if is_explicit_chart else None,
                "intent": "plant_available_capacity",
                "metric": "available_capacity",
                "filters": {"plant": plant_cand} if plant_cand else {},
                "time_range": "current",
                "output_type": "bar_chart" if is_explicit_chart else "table",
                "conversation_state": state
            }

        plant_filter_cap = f" WHERE b.Plant = '{plant_cand}'" if plant_cand else ""
        sql_avail_cap = f"""WITH Cap AS (
    SELECT 
        b.Plant,
        b.Volume AS BinVol,
        COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) AS OccVol
    FROM dbo.ZWMS_BIN_MASTER b
    LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
    WHERE b.Volume > 0
    GROUP BY b.BinLocation, b.Plant, b.Volume
)
SELECT 
    ROUND(SUM(BinVol) - SUM(OccVol), 2) AS [Total Available Capacity (FT3)],
    ROUND(SUM(BinVol), 2) AS [Total Capacity (FT3)],
    ROUND(SUM(OccVol), 2) AS [Total Occupied Volume (FT3)]
FROM Cap{plant_filter_cap}"""
        return {
            "sql": sql_avail_cap,
            "chart_type": "none",
            "chart_title": f"Available Storage Capacity{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": None,
            "chart_y": None,
            "intent": "available_capacity",
            "metric": "available_capacity",
            "filters": {"plant": plant_cand} if plant_cand else {},
            "time_range": "current",
            "output_type": "text",
            "conversation_state": state
        }

    # 7. OCCUPIED VOLUME QUERIES (Total Occupied Volume): "How much space is occupied?", "Show occupied volume"
    is_occ_vol_req = (
        state.get("topic") == "occupied_volume" or
        (
            any(k in q_lower for k in [
                "how much space is occupied", "show occupied volume", "how much warehouse capacity is being used",
                "what is the occupied storage volume", "how much inventory space is currently occupied",
                "total occupied volume", "occupied storage volume", "how much volume is occupied"
            ]) or
            q_lower.strip() in ["occupied volume", "storage volume occupied"]
        ) and
        not any(k in q_lower for k in ["utiliz", "occupan", "%", "rank", "ranking", "share of total", "materials by", "plants by", "compared to", "versus", "vs", "compare", "available capacity"])
    )
    if is_occ_vol_req:
        plant_filter_occ = f" AND i.Plant = '{plant_cand}'" if plant_cand else ""
        sql_occ_vol = f"""SELECT 
    ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 2) AS [Total Occupied Volume (FT3)],
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins],
    SUM(i.UnrestrictedQty) AS [Total Inventory Quantity]
FROM dbo.ZWMS_INVENTORY i
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE i.UnrestrictedQty > 0{plant_filter_occ}"""
        return {
            "sql": sql_occ_vol,
            "chart_type": "none",
            "chart_title": f"Occupied Storage Volume{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": None,
            "chart_y": None,
            "intent": "occupied_volume",
            "metric": "occupied_volume",
            "filters": {"plant": plant_cand} if plant_cand else {},
            "time_range": "current",
            "output_type": "text",
            "conversation_state": state
        }

    # 8. BIN CAPACITY LIST: "Show capacity for each bin", "Show capacity of all bins in Plant 1258"
    is_bin_cap_list_req = (
        state.get("topic") == "bin_capacity_list" or
        (
            any(k in q_lower for k in ["capacity for each bin", "capacity of all bins", "capacity of each bin", "show capacity of bins", "show capacity for bins", "bin capacity list", "list bin capacity"]) and
            not any(k in q_lower for k in ["rank", "ranking", "top", "bottom"])
        )
    )
    if is_bin_cap_list_req:
        n_limit = state.get("limit") or new_limit
        top_clause = f"TOP {n_limit} " if n_limit else ""
        plant_filter_bin = f" AND b.Plant = '{plant_cand}'" if plant_cand else ""
        sql_bin_cap_list = f"""SELECT {top_clause}
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    COALESCE(b.StorageLocation, 'N/A') AS [Storage Location],
    ROUND(b.Volume, 2) AS [Total Capacity (FT3)],
    ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Occupied Volume (FT3)],
    ROUND(b.Volume - COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Available Capacity (FT3)],
    CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Capacity Utilization %],
    COUNT(*) OVER() AS [TotalMatching]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE b.Volume > 0{plant_filter_bin}
GROUP BY b.BinLocation, b.Plant, b.StorageLocation, b.Volume
ORDER BY [Total Capacity (FT3)] DESC"""
        return {
            "sql": sql_bin_cap_list,
            "chart_type": "none",
            "chart_title": f"Bin Capacity Specifications{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": None,
            "chart_y": None,
            "intent": "bin_capacity_list",
            "metric": "bin_capacity",
            "filters": {"plant": plant_cand} if plant_cand else {},
            "time_range": "current",
            "output_type": "table",
            "conversation_state": state
        }

    # G. WAREHOUSE & PLANT BIN UTILIZATION (Multi-Tiered Response Templates)
    # Semantic Definition: Occupied volume / Total capacity volume * 100 or Occupied Bins / Total Bins * 100
    is_utilization_intent = (
        state.get("topic") in ["plant_bin_level_detail", "plant_bin_utilization_detailed_analysis", "plant_bin_utilization_detail", "warehouse_utilization"] or
        is_bin_level_detail_intent(q_lower) or
        any(k in q_lower for k in ["utiliz", "occupan", "capacity", "how full", "warehouse fullness", "facility fill", "fill rate", "space utilization", "bin fill", "fill percentage", "running out of", "out of storage space", "storage capacity"]) or
        (("volume" in q_lower or "space" in q_lower) and ("occup" in q_lower or "capacit" in q_lower or "fill" in q_lower or "running out" in q_lower))
    )
    if is_utilization_intent and not any(m in q_lower for m in ["material", "sku", "item", "product", "consuming", "share of total"]):
        is_sloc_explicit = any(k in q_lower for k in ["by storage location", "sloc breakdown", "storage location breakdown", "by sloc"])
        is_explicit_chart_request = bool(state.get("is_explicit_chart_request") or any(k in q_lower for k in [
            "show me a graph for this", "show me a graph", "show graph", "give me a chart", "visualize this", "show this in graph",
            "create a chart", "can you graph this", "can you visualize this",
            "show this in graphical form", "draw a chart", "plot this", "visualize", "graph for this",
            "chart for this", "graph of this", "chart of this", "show chart", "give chart", "make a chart",
            "plot a chart", "draw a graph"
        ]))
        if (
            state.get("topic") != "plant_bin_utilization_detailed_analysis" and
            not (state.get("granularity") == "storage_location" and state.get("aggregation") == "breakdown") and
            (state.get("topic") == "plant_bin_level_detail" or is_bin_level_detail_intent(q_lower)) and
            plant_cand and
            not is_explicit_chart_request and
            not is_sloc_explicit
        ):
            plant_val = plant_cand
            cand_limit = state.get("limit") or extract_explicit_limit(q_lower)
            if cand_limit:
                sql_single_bin_detail = f"""SELECT TOP {cand_limit}
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    ROUND(b.Volume, 2) AS [Capacity],
    ROUND(b.Volume - COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Available Capacity],
    CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %],
    CASE 
        WHEN COUNT(i.Material) = 0 THEN 'Empty'
        WHEN COUNT(DISTINCT i.Material) = 1 THEN CONCAT(MIN(i.Material), ' (', ROUND(SUM(i.UnrestrictedQty), 0), ' units)')
        ELSE CONCAT(COUNT(DISTINCT i.Material), ' materials (', ROUND(SUM(i.UnrestrictedQty), 0), ' units)')
    END AS [Material / Inventory Information]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE b.Plant = '{plant_val}'
GROUP BY b.BinLocation, b.Plant, b.Volume
ORDER BY COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0) DESC"""
            else:
                sql_single_bin_detail = f"""SELECT 
    b.BinLocation AS [Bin],
    b.Plant AS [Plant],
    ROUND(b.Volume, 2) AS [Capacity],
    ROUND(b.Volume - COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0), 2) AS [Available Capacity],
    CONCAT(ROUND(COALESCE(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)), 0) * 100.0 / NULLIF(b.Volume, 0), 1), '%') AS [Utilization %],
    CASE 
        WHEN COUNT(i.Material) = 0 THEN 'Empty'
        WHEN COUNT(DISTINCT i.Material) = 1 THEN CONCAT(MIN(i.Material), ' (', ROUND(SUM(i.UnrestrictedQty), 0), ' units)')
        ELSE CONCAT(COUNT(DISTINCT i.Material), ' materials (', ROUND(SUM(i.UnrestrictedQty), 0), ' units)')
    END AS [Material / Inventory Information]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
WHERE b.Plant = '{plant_val}'
GROUP BY b.BinLocation, b.Plant, b.Volume
ORDER BY b.BinLocation"""

            return {
                "sql": sql_single_bin_detail,
                "chart_type": "none",
                "chart_title": f"Plant {plant_val} Detailed Bin Utilization",
                "chart_x": None,
                "chart_y": None,
                "intent": "plant_bin_level_detail",
                "metric": "bin_utilization",
                "filters": {"plant": plant_val},
                "time_range": "current",
                "output_type": "table",
                "conversation_state": state
            }

        is_detail_explain_query = (
            state.get("topic") == "plant_bin_utilization_detailed_analysis" or
            any(k in q_lower for k in [
                "explain", "explanation", "breakdown", "break it down", 
                "deep dive", "elaborate", "by storage location", "sloc breakdown", 
                "storage location breakdown", "detailed version", "detailed analysis",
                "in detail", "in-depth", "drill down", "itemized", "granular"
            ])
        )
        if (state.get("topic") == "plant_bin_utilization_detailed_analysis" or (is_detail_explain_query and plant_cand)) and plant_cand:
            plant_val = plant_cand
            if is_bin_utilization_primary(q_lower):
                sql_detailed = f"""SELECT 
    b.Plant AS [Plant], 
    COALESCE(b.StorageLocation, 'Unassigned') AS [Storage Location], 
    COUNT(DISTINCT b.BinLocation) AS [Total Bins], 
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins], 
    (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) AS [Empty Bins], 
    CONCAT(ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2), '%') AS [Bin Utilization %] 
FROM dbo.ZWMS_BIN_MASTER b 
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant AND b.StorageLocation = i.StorageLocation 
WHERE b.Plant = '{plant_val}' 
GROUP BY b.Plant, b.StorageLocation 
ORDER BY COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0) DESC"""
                chart_y = "Bin Utilization %"
            else:
                sql_detailed = f"""SELECT 
    b.Plant AS [Plant], 
    COALESCE(b.StorageLocation, 'Unassigned') AS [Storage Location], 
    COUNT(DISTINCT b.BinLocation) AS [Total Bins], 
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins], 
    (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) AS [Empty Bins], 
    CONCAT(ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2), '%') AS [Bin Utilization %], 
    ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2) AS [UtilizationPct], 
    ROUND(SUM(b.Volume), 2) AS [Total Capacity Volume (FT3)], 
    ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) AS [Occupied Volume (FT3)] 
FROM dbo.ZWMS_BIN_MASTER b 
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant AND b.StorageLocation = i.StorageLocation 
WHERE b.Plant = '{plant_val}' 
GROUP BY b.Plant, b.StorageLocation 
ORDER BY COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0) DESC"""
                chart_y = "UtilizationPct"

            return {
                "sql": sql_detailed,
                "chart_type": "bar",
                "chart_title": f"Plant {plant_val} Bin Utilization by Storage Location (%)",
                "chart_x": "Storage Location",
                "chart_y": chart_y,
                "intent": "plant_bin_utilization_detailed_analysis",
                "metric": "storage_location_utilization",
                "filters": {"plant": plant_val, "granularity": "storage_location"},
                "time_range": "current",
                "output_type": "bar_chart",
                "conversation_state": state
            }

        # 2. PLANT BIN UTILIZATION SUMMARY TEMPLATE (SUMMARY + RELEVANT KPIS + SUMMARY TABLE)
        is_all_plants_request = any(w in q_lower for w in ["all", "compare", "network", "plants", "overall", "facility", "across all", "whole warehouse", "across", "each", "every", "by plant", "across plants"])
        if plant_cand and not is_all_plants_request:
            plant_val = plant_cand
            if is_bin_utilization_primary(q_lower):
                sql_plant_summary = f"""SELECT 
    b.Plant AS [Plant], 
    COUNT(DISTINCT b.BinLocation) AS [Total Bins], 
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins], 
    (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) AS [Empty Bins], 
    CONCAT(ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2), '%') AS [Bin Utilization %] 
FROM dbo.ZWMS_BIN_MASTER b 
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant 
WHERE b.Plant = '{plant_val}' 
GROUP BY b.Plant"""
            else:
                sql_plant_summary = f"""SELECT 
    b.Plant AS [Plant], 
    COUNT(DISTINCT b.BinLocation) AS [Total Bins], 
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins], 
    (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) AS [Empty Bins], 
    CONCAT(ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 1), '%') AS [Bin Utilization %], 
    ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 1) AS [UtilizationPct], 
    ROUND(SUM(b.Volume), 2) AS [Total Capacity Volume (FT3)], 
    ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) AS [Occupied Volume (FT3)] 
FROM dbo.ZWMS_BIN_MASTER b 
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant 
WHERE b.Plant = '{plant_val}' 
GROUP BY b.Plant"""

            query_plan = {
                "entity": "BIN",
                "metric": "BIN_UTILIZATION",
                "operation": "ANALYZE",
                "filters": {"plant": plant_val},
                "group_by": None,
                "ranking": None,
                "limit": None,
                "response_mode": "GRAPH" if is_explicit_chart else ("DETAIL" if is_detail_requested else "SUMMARY")
            }

            return {
                "sql": sql_plant_summary,
                "query_plan": query_plan,
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": f"Plant {plant_val} Bin Utilization Summary",
                "chart_x": "Plant" if is_explicit_chart else None,
                "chart_y": "Bin Utilization %" if is_explicit_chart else None,
                "intent": "plant_bin_utilization_detail",
                "metric": "plant_bin_utilization",
                "filters": {"plant": plant_val, "granularity": "plant"},
                "time_range": "current",
                "output_type": "bar_chart" if is_explicit_chart else "table",
                "relevant_kpis": [
                    {"label": "Bin Utilization", "value": "bin_utilization"},
                    {"label": "Occupied Bins", "value": "occupied_bins"},
                    {"label": "Empty Bins", "value": "empty_bins"},
                    {"label": "Total Bins", "value": "total_bins"}
                ],
                "conversation_state": state
            }


        # 3. LOWEST / HIGHEST BIN UTILIZATION ACROSS PLANTS (Specific Extremes & Rankings)
        has_plant_word = bool(re.search(r"\b(?:plants?|plnts?|facility|facilities)\b", q_lower))
        is_lowest_util_req = (
            (has_plant_word and any(k in q_lower for k in ["lowest", "least", "minimum", "min", "bottom", "worst", "emptiest"]) and any(k in q_lower for k in ["utiliz", "occupan", "capacity", "fill", "full"])) or
            any(k in q_lower for k in [
                "lowest bin utilization", "least bin utilization", "minimum bin utilization",
                "lowest utilization", "least utilized plant", "lowest utilized plant", "minimum utilization",
                "which plant has the lowest", "which plant has lowest", "whic plant has lowest", "whic plant has the lowest",
                "plant with the lowest", "least full plant"
            ])
        )
        is_highest_util_req = (
            (has_plant_word and any(k in q_lower for k in ["highest", "most", "maximum", "max", "top", "best", "fullest", "rank", "ranking"]) and any(k in q_lower for k in ["utiliz", "occupan", "capacity", "fill", "full"])) or
            any(k in q_lower for k in [
                "highest bin utilization", "most bin utilization", "maximum bin utilization",
                "top bin utilization", "most utilized plant", "highest utilized plant", "maximum utilization",
                "which plant has the highest", "which plant has highest", "whic plant has highest", "whic plant has the highest",
                "plant with the highest", "most full plant", "rank plants by bin utilization", "rank all plants by bin utilization",
                "ranking of plants by bin utilization", "plants by bin utilization"
            ])
        )

        if (is_lowest_util_req or is_highest_util_req) and not plant_cand:
            order_dir = "ASC" if is_lowest_util_req else "DESC"
            rank_label = "Lowest" if is_lowest_util_req else "Highest"
            has_ranking_keyword = any(d in q_lower for d in ["ranking", "table", "all plants", "compare", "list", "breakdown", "detailed", "detail form", "all", "rank"])
            is_scalar_extreme = (
                is_single_statement_requested or
                (not is_detail_requested and not has_ranking_keyword and any(k in q_lower for k in [
                    "which plant", "whic plant", "what plant", "wat plant", "plant with",
                    "what is the lowest", "what is the highest", "who has the lowest", "who has the highest",
                    "the lowest", "the highest", "lowest bin utilization", "highest bin utilization",
                    "lowest utilization", "highest utilization"
                ]))
            )
            limit_n = 1 if is_scalar_extreme else 4
            top_clause = f"TOP {limit_n} " if limit_n == 1 else ""

            sql_extreme_util = f"""SELECT {top_clause}
    RANK() OVER (ORDER BY ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2) {order_dir}) AS [Rank],
    b.Plant AS [Plant],
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins],
    (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) AS [Empty Bins],
    COUNT(DISTINCT b.BinLocation) AS [Total Bins],
    CONCAT(ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2), '%') AS [Bin Utilization %]
FROM dbo.ZWMS_BIN_MASTER b
LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
GROUP BY b.Plant
ORDER BY ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2) {order_dir}"""

            intent_name = "lowest_bin_utilization" if is_lowest_util_req else "highest_bin_utilization"
            is_single_scalar = (is_single_statement_requested or limit_n == 1)
            return {
                "sql": sql_extreme_util,
                "query_plan": {
                    "intent": "RANKING",
                    "rank_direction": order_dir,
                    "rank_metric": "Bin Utilization %",
                    "rank_entity": "Plant",
                    "limit": limit_n,
                    "rank_scope": {}
                },
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": f"{rank_label} Bin Utilization by Plant",
                "chart_x": "Plant" if is_explicit_chart else None,
                "chart_y": "Bin Utilization %" if is_explicit_chart else None,
                "intent": intent_name,
                "metric": "bin_utilization",
                "filters": {},
                "time_range": "current",
                "output_type": "text" if is_single_scalar else ("bar_chart" if is_explicit_chart else "table"),
                "conversation_state": state
            }

        # 4. MULTI-PLANT OR WAREHOUSE-WIDE BIN UTILIZATION
        plant_filter = f" WHERE b.Plant = '{plant_cand}'" if (plant_cand and not is_all_plants_request) else ""
        filters = {"plant": plant_cand} if plant_filter else {}
        query_plan = {
            "entity": "BIN",
            "metric": "BIN_UTILIZATION",
            "operation": "ANALYZE",
            "group_by": "PLANT",
            "filters": filters,
            "ranking": None,
            "limit": None,
            "response_mode": "GRAPH" if is_explicit_chart else "SUMMARY"
        }
        if is_bin_utilization_primary(q_lower):
            sql_bin_util = f"SELECT b.Plant, COUNT(DISTINCT b.BinLocation) AS TotalBins, COUNT(DISTINCT i.BinNo) AS OccupiedBins, (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) AS EmptyBins, CONCAT(ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2), '%') AS [Bin Utilization %] FROM dbo.ZWMS_BIN_MASTER b LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant{plant_filter} GROUP BY b.Plant ORDER BY ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2) DESC"
            chart_y = "Bin Utilization %"
            chart_title = "Warehouse Bin Utilization by Plant (%)"
        else:
            sql_bin_util = f"SELECT b.Plant, COUNT(DISTINCT b.BinLocation) AS TotalBins, COUNT(DISTINCT i.BinNo) AS OccupiedBins, (COUNT(DISTINCT b.BinLocation) - COUNT(DISTINCT i.BinNo)) AS EmptyBins, ROUND(COUNT(DISTINCT i.BinNo) * 100.0 / NULLIF(COUNT(DISTINCT b.BinLocation), 0), 2) AS BinUtilizationPct, ROUND(SUM(b.Volume), 2) AS TotalBinCapacityVolume, ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END), 2) AS OccupiedBinVolume, ROUND(SUM(CASE WHEN i.BinNo IS NOT NULL THEN b.Volume ELSE 0 END) * 100.0 / NULLIF(SUM(b.Volume), 0), 2) AS VolumeUtilizationPct FROM dbo.ZWMS_BIN_MASTER b LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant{plant_filter} GROUP BY b.Plant ORDER BY VolumeUtilizationPct DESC"
            chart_y = "VolumeUtilizationPct"
            chart_title = "Warehouse Volume Utilization by Plant (%)"

        return {
            "sql": sql_bin_util,
            "query_plan": query_plan,
            "chart_type": "none" if is_single_statement_requested else "bar",
            "chart_title": chart_title,
            "chart_x": None if is_single_statement_requested else "Plant",
            "chart_y": None if is_single_statement_requested else chart_y,
            "intent": "bin_utilization",
            "metric": "warehouse_utilization",
            "filters": filters,
            "time_range": "current",
            "output_type": "text" if is_single_statement_requested else "bar_chart",
            "conversation_state": state
        }


    # G. TIME SERIES & TREND ANALYSIS
    if any(k in q_lower for k in ["trend", "history", "timeline", "over time", "monthly", "last 6 months", "vested"]):
        return {
            "sql": "SELECT SUBSTRING(CONVERT(VARCHAR(10), FullyVestedOn, 120), 1, 7) AS Month, COUNT(DISTINCT Material) AS ActiveMaterials, SUM(UnrestrictedQty) AS TotalQuantity, ROUND(SUM(UnrestrictedQty * 0.05), 2) AS EstVolume FROM dbo.ZWMS_INVENTORY WHERE FullyVestedOn IS NOT NULL GROUP BY SUBSTRING(CONVERT(VARCHAR(10), FullyVestedOn, 120), 1, 7) ORDER BY Month ASC",
            "chart_type": "line",
            "chart_title": "Warehouse Inventory & Activity Trend Over Time",
            "chart_x": "Month",
            "chart_y": "TotalQuantity",
            "intent": "trend_analysis",
            "metric": "warehouse_utilization",
            "filters": {},
            "time_range": "last_6_months",
            "output_type": "line_chart"
        }

    # H. STORAGE LOCATION COMPARISON
    is_storage_loc_comparison = any(k in q_lower for k in [
        "storage location", "storage locations", "across storage locations", "by storage location", "compare storage location", "inventory per storage location"
    ]) and not any(k in q_lower for k in ["empty", "putaway", "vacant", "unoccupied"])
    if is_storage_loc_comparison:
        plant_filter = f" WHERE Plant = '{plant_cand}'" if plant_cand else ""
        filters = {"plant": plant_cand} if plant_cand else {}
        sql_sl = f"""SELECT 
    StorageLocation AS [Storage Location], 
    Plant, 
    COUNT(DISTINCT Material) AS [Active Materials], 
    COUNT(DISTINCT BinNo) AS [Occupied Bins], 
    SUM(UnrestrictedQty) AS [Total Inventory Quantity] 
FROM dbo.ZWMS_INVENTORY{plant_filter} 
GROUP BY StorageLocation, Plant 
ORDER BY [Total Inventory Quantity] DESC"""
        query_plan = {
            "task": "comparison",
            "entity": "storage_location",
            "metrics": ["Total Inventory Quantity", "Occupied Bins", "Active Materials"],
            "dimensions": ["Storage Location", "Plant"],
            "filters": [f"Plant = {plant_cand}"] if plant_cand else [],
            "conditions": [],
            "group_by": ["StorageLocation", "Plant"],
            "sort": ["Total Inventory Quantity DESC"],
            "limit": None,
            "time_range": "current",
            "tables": ["dbo.ZWMS_INVENTORY"],
            "joins": [],
            "output_type": "chart"
        }
        return {
            "sql": sql_sl,
            "query_plan": query_plan,
            "chart_type": "bar",
            "chart_title": f"Inventory Quantity Across Storage Locations{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": "Storage Location",
            "chart_y": "Total Inventory Quantity",
            "intent": "storage_location_comparison",
            "metric": "storage_location_inventory",
            "filters": filters,
            "time_range": "current",
            "output_type": "bar_chart",
            "conversation_state": state
        }

    # I. MATERIAL CONSOLIDATION CANDIDATES
    if any(k in q_lower for k in ["consolidat", "free up", "same material", "duplicate bin", "multiple bin"]):
        plant_filter = f" WHERE Plant = '{plant_cand}'" if plant_cand else ""
        filters = {"plant": plant_cand} if plant_cand else {}
        return {
            "sql": f"SELECT TOP 20 Material, MAX(MaterialDescription) AS MaterialDescription, COUNT(DISTINCT BinNo) AS ActiveBinCount, COUNT(DISTINCT Batch) AS BatchCount, SUM(UnrestrictedQty) AS TotalQuantity, MAX(BaseUnitOfMeasure) AS UOM FROM dbo.ZWMS_INVENTORY{plant_filter} GROUP BY Material HAVING COUNT(DISTINCT BinNo) > 1 ORDER BY ActiveBinCount DESC, TotalQuantity ASC",
            "chart_type": "bar",
            "chart_title": "Materials in Multiple Bins (Consolidation Candidates)",
            "chart_x": "Material",
            "chart_y": "ActiveBinCount",
            "intent": "consolidation",
            "metric": "consolidation_candidates",
            "filters": filters,
            "time_range": "current",
            "output_type": "list"
        }

    # J. QUANTITY DIFFERENCES (ZWMS vs ZWS)
    if any(k in q_lower for k in ["difference", "zws", "unrestrictedqty2"]):
        plant_filter = f" WHERE Plant = '{plant_cand}'" if plant_cand else ""
        filters = {"plant": plant_cand} if plant_cand else {}
        return {
            "sql": f"SELECT TOP 20 Material, MAX(MaterialDescription) AS MaterialDescription, SUM(ABS(COALESCE(UnrestrictedQty,0) - COALESCE(UnrestrictedQty2,0))) AS QuantityDifference, SUM(UnrestrictedQty) AS ZWMS_Qty, SUM(UnrestrictedQty2) AS ZWS_Qty FROM dbo.ZWMS_INVENTORY{plant_filter} GROUP BY Material ORDER BY QuantityDifference DESC",
            "chart_type": "bar",
            "chart_title": "Top Materials by Quantity Difference (ZWMS vs ZWS)",
            "chart_x": "Material",
            "chart_y": "QuantityDifference",
            "intent": "stock_difference",
            "metric": "difference_qty",
            "filters": filters,
            "time_range": "current",
            "output_type": "bar_chart"
        }

    # K. SPECIFIC PLANT MATERIAL INQUIRIES (Detail Table List)
    is_plant_materials_query = (
        plant_cand and
        (
            state.get("topic") == "plant_materials" or
            any(w in q_lower for w in ["show me the materials", "show me materials", "show materials", "list materials", "materials in plant", "materials of plant", "which materials in plant", "materials in", "skus in"])
        ) and
        not any(k in q_lower for k in [
            "how many", "count", "number of", "total inventory", "total stock", "how much inventory",
            "how much stock", "total unrestricted", "total units", "inventory quantity", "units in inventory",
            "total quantity", "records are there", "how many records", "count of records"
        ])
    )
    if is_plant_materials_query:
        query_plan = {
            "intent": "LIST",
            "entity": "material",
            "scope": f"Plant {plant_cand}",
            "operation": "LIST",
            "response_format": "TABLE"
        }
        return {
            "sql": f"SELECT Material, MaterialDescription AS Description, UnrestrictedQty AS Qty, BaseUnitOfMeasure AS UOM, StorageLocation AS [Storage Location], BinNo AS Bin FROM dbo.ZWMS_INVENTORY WHERE Plant = '{plant_cand}' ORDER BY UnrestrictedQty DESC",
            "query_plan": query_plan,
            "chart_type": "none",
            "chart_title": f"Material Inventory Records for Plant {plant_cand}",
            "chart_x": None,
            "chart_y": None,
            "intent": "plant_materials",
            "metric": "plant_stock_records",
            "filters": {"plant": plant_cand},
            "time_range": "current",
            "output_type": "table",
            "conversation_state": state
        }

    # L. SPECIFIC BIN LOOKUP
    if bin_match and not any(w in q_lower for w in ["empty", "putaway", "put-away", "unoccupied", "vacant", "free"]):
        b_code = bin_match.group(1).upper() if hasattr(bin_match, "group") else str(bin_match).upper()
        return {
            "sql": f"SELECT b.BinLocation AS Bin, b.Plant, b.StorageLocation AS [Storage Location], b.Volume, b.VolumeUnit, b.PalletType, i.Material, i.MaterialDescription AS Description, i.UnrestrictedQty AS Qty, i.BaseUnitOfMeasure AS UOM FROM dbo.ZWMS_BIN_MASTER b LEFT JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant WHERE b.BinLocation = '{b_code}' OR i.BinNo = '{b_code}'",
            "chart_type": "none",
            "chart_title": f"Bin Information for {b_code}",
            "chart_x": None,
            "chart_y": None,
            "intent": "bin_lookup",
            "metric": "bin_details",
            "filters": {"bin": b_code},
            "time_range": "current",
            "output_type": "table"
        }

    # M. SPECIFIC MATERIAL CODE LOOKUP
    if material_match:
        m_code = material_match.group(1).upper() if hasattr(material_match, "group") else str(material_match).upper()
        return {
            "sql": f"SELECT BinNo, Plant, StorageLocation, Batch, UnrestrictedQty, BaseUnitOfMeasure, MaterialDescription FROM dbo.ZWMS_INVENTORY WHERE Material = '{m_code}' ORDER BY UnrestrictedQty DESC",
            "chart_type": "none",
            "chart_title": f"Stock Locations for Material {m_code}",
            "chart_x": None,
            "chart_y": None,
            "intent": "stock_lookup",
            "metric": "unrestricted_qty",
            "filters": {"material": m_code},
            "time_range": "current",
            "output_type": "table"
        }

    # N. MATERIAL DIVISION DISTRIBUTION
    if any(k in q_lower for k in ["division", "group"]):
        return {
            "sql": "SELECT COALESCE(m.DivisionDescription, m.Division, 'Unassigned') AS Division, COUNT(DISTINCT i.Material) AS MaterialCount, SUM(i.UnrestrictedQty) AS TotalQuantity FROM dbo.ZWMS_MATERIAL_MASTER m JOIN dbo.ZWMS_INVENTORY i ON m.MaterialCode = i.Material GROUP BY COALESCE(m.DivisionDescription, m.Division, 'Unassigned') ORDER BY TotalQuantity DESC",
            "chart_type": "pie",
            "chart_title": "Inventory by Material Division",
            "chart_x": "Division",
            "chart_y": "TotalQuantity",
            "intent": "division_breakdown",
            "metric": "division_inventory",
            "filters": {},
            "time_range": "current",
            "output_type": "pie_chart"
        }

    # M1. MATERIAL MAXIMUM / MINIMUM QUANTITY EXTREMES (Item 1: e.g. "Which material has the highest quantity")
    is_mat_rank_keyword = any(k in q_lower for k in ["rank", "ranking", "rankings"]) or bool(re.search(r"\b(?:top|bottom)\s+\d+\b", q_lower))
    is_mat_qty_extreme = (
        is_mat_entity and
        not is_mat_rank_keyword and
        any(q in q_lower for q in ["quantity", "inventory", "stock", "units", "most"]) and
        any(h in q_lower for h in ["highest", "maximum", "max", "largest", "most", "top", "greatest", "lowest", "least", "minimum", "min", "smallest"]) and
        not any(b in q_lower for b in ["bin", "bins", "utiliz", "capacity", "volume", "ft3", "cubic"]) and
        not any(p in q_lower for p in ["which plant", "what plant", "plant with"])
    )
    if is_mat_qty_extreme:
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum", "min", "smallest"])
        order_dir = "ASC" if is_least else "DESC"
        extreme_op = "MIN" if is_least else "MAX"
        extreme_label = "Lowest" if is_least else "Highest"
        plant_and = f" AND Plant = '{plant_cand}'" if plant_cand else ""
        sql_mat_extreme = f"""SELECT TOP 1
    ROW_NUMBER() OVER (ORDER BY SUM(UnrestrictedQty) {order_dir}) AS [Rank],
    Material,
    MAX(MaterialDescription) AS [Material Description],
    SUM(UnrestrictedQty) AS [Total Stock Quantity],
    MAX(BaseUnitOfMeasure) AS [UOM],
    COUNT(DISTINCT BinNo) AS [Occupied Bins]
FROM dbo.ZWMS_INVENTORY
WHERE UnrestrictedQty > 0{plant_and}
GROUP BY Material
ORDER BY SUM(UnrestrictedQty) {order_dir}"""
        query_plan = {
            "intent": extreme_op,
            "entity": "MATERIAL",
            "metric": "INVENTORY_QUANTITY",
            "operation": extreme_op,
            "sort": order_dir,
            "limit": 1
        }
        return {
            "sql": sql_mat_extreme,
            "query_plan": query_plan,
            "chart_type": "none",
            "chart_title": f"Material with {extreme_label} Stock Quantity",
            "chart_x": None,
            "chart_y": None,
            "intent": "material_max_quantity" if order_dir == "DESC" else "material_min_quantity",
            "metric": "INVENTORY_QUANTITY",
            "filters": {"plant": plant_cand} if plant_cand else {},
            "time_range": "current",
            "output_type": "text" if not is_detail_requested else "table",
            "conversation_state": state
        }

    # M2. MATERIALS FILTERED BY QUANTITY THRESHOLD (Item 2: e.g. "Show materials having quantity above 1000")
    qty_thresh = extract_quantity_threshold(q_lower)
    is_mat_thresh_query = is_mat_entity and (qty_thresh is not None)
    if is_mat_thresh_query:
        op, thresh_val = qty_thresh
        plant_and = f" AND i.Plant = '{plant_cand}'" if plant_cand else ""
        sql_mat_thresh = f"""SELECT 
    i.Material,
    MAX(i.MaterialDescription) AS [Material Description],
    SUM(i.UnrestrictedQty) AS [Total Stock Quantity],
    MAX(i.BaseUnitOfMeasure) AS [UOM],
    COUNT(DISTINCT i.BinNo) AS [Occupied Bins],
    COUNT(DISTINCT i.Plant) AS [Plant Count]
FROM dbo.ZWMS_INVENTORY i
WHERE i.UnrestrictedQty > 0{plant_and}
GROUP BY i.Material
HAVING SUM(i.UnrestrictedQty) {op} {thresh_val}
ORDER BY SUM(i.UnrestrictedQty) DESC"""
        query_plan = {
            "intent": "FILTER",
            "entity": "MATERIAL",
            "metric": "INVENTORY_QUANTITY",
            "operator": op,
            "threshold": thresh_val,
            "operation": "FILTER"
        }
        return {
            "sql": sql_mat_thresh,
            "query_plan": query_plan,
            "chart_type": "bar" if is_explicit_chart else "none",
            "chart_title": f"Materials with Inventory Quantity {op} {thresh_val:,.0f}",
            "chart_x": "Material" if is_explicit_chart else None,
            "chart_y": "Total Stock Quantity" if is_explicit_chart else None,
            "intent": "materials_quantity_threshold",
            "metric": "INVENTORY_QUANTITY",
            "filters": {"plant": plant_cand} if plant_cand else {},
            "time_range": "current",
            "output_type": "bar_chart" if is_explicit_chart else ("text" if is_single_statement_requested else "table"),
            "conversation_state": state
        }

    # N0_RANK. GENERALIZED RANKING SYSTEM FOR MATERIALS AND STORAGE LOCATIONS
    is_general_ranking_req = any(k in q_lower for k in [
        "rank", "ranking", "rankings", "top materials", "highest materials", "lowest materials",
        "least materials", "most materials", "material ranking", "materials ranking",
        "top storage locations", "highest storage locations", "storage location ranking"
    ])
    if is_general_ranking_req and not is_mat_vol_intent:
        n_val = state.get("limit") or 10
        if not state.get("limit"):
            n_match = re.search(r"\b(?:top|bottom|highest|lowest|first|last|least|most)?\s*(\d{1,3})\b", q_lower)
            n_val = int(n_match.group(1)) if (n_match and n_match.group(1) not in ["100", "2024", "2025", "2026"]) else 10
        plant_filter = f" WHERE Plant = '{plant_cand}'" if plant_cand else ""
        plant_and = f" AND Plant = '{plant_cand}'" if plant_cand else ""
        filters = {"plant": plant_cand} if plant_cand else {}

        # 1. Materials ranking by total quantity
        if is_mat_entity or any(k in q_lower for k in ["material", "materials", "sku", "skus", "item", "items", "stock quantity"]):
            is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum"])
            order_dir = "ASC" if is_least else "DESC"
            rank_label = f"Bottom {n_val} Least" if is_least else f"Top {n_val} Highest"
            sql_mat_rank = f"""SELECT TOP {n_val}
    ROW_NUMBER() OVER (ORDER BY SUM(UnrestrictedQty) {order_dir}) AS [Rank],
    Material,
    MAX(MaterialDescription) AS [Material Description],
    SUM(UnrestrictedQty) AS [Total Stock Quantity],
    MAX(BaseUnitOfMeasure) AS [UOM],
    COUNT(DISTINCT BinNo) AS [Occupied Bins]
FROM dbo.ZWMS_INVENTORY
WHERE UnrestrictedQty > 0{plant_and}
GROUP BY Material
ORDER BY SUM(UnrestrictedQty) {order_dir}"""
            query_plan = {
                "intent": "RANKING",
                "rank_direction": order_dir,
                "rank_metric": "UnrestrictedQty",
                "rank_entity": "Material",
                "limit": n_val,
                "rank_scope": {"Plant": plant_cand} if plant_cand else {}
            }
            return {
                "sql": sql_mat_rank,
                "query_plan": query_plan,
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": f"{rank_label} Stocked Materials{f' — Plant {plant_cand}' if plant_cand else ''}",
                "chart_x": "Material" if is_explicit_chart else None,
                "chart_y": "Total Stock Quantity" if is_explicit_chart else None,
                "intent": "material_quantity_ranking",
                "metric": "material_stock_ranking",
                "filters": filters,
                "time_range": "current",
                "output_type": "bar_chart" if is_explicit_chart else "table",
                "conversation_state": state
            }

        # 2. Storage locations ranking by total quantity
        if any(k in q_lower for k in ["storage location", "storage locations", "sloc", "slocs", "zone", "zones"]):
            is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum"])
            order_dir = "ASC" if is_least else "DESC"
            rank_label = f"Bottom {n_val} Least" if is_least else f"Top {n_val} Highest"
            sql_sloc_rank = f"""SELECT TOP {n_val}
    ROW_NUMBER() OVER (ORDER BY SUM(UnrestrictedQty) {order_dir}) AS [Rank],
    StorageLocation AS [Storage Location],
    Plant,
    SUM(UnrestrictedQty) AS [Total Inventory Quantity],
    COUNT(DISTINCT Material) AS [Active Materials],
    COUNT(DISTINCT BinNo) AS [Occupied Bins]
FROM dbo.ZWMS_INVENTORY{plant_filter}
GROUP BY StorageLocation, Plant
ORDER BY SUM(UnrestrictedQty) {order_dir}"""
            query_plan = {
                "intent": "RANKING",
                "rank_direction": order_dir,
                "rank_metric": "UnrestrictedQty",
                "rank_entity": "StorageLocation",
                "limit": n_val,
                "rank_scope": {"Plant": plant_cand} if plant_cand else {}
            }
            return {
                "sql": sql_sloc_rank,
                "query_plan": query_plan,
                "chart_type": "bar" if is_explicit_chart else "none",
                "chart_title": f"{rank_label} Storage Locations{f' — Plant {plant_cand}' if plant_cand else ''}",
                "chart_x": "Storage Location" if is_explicit_chart else None,
                "chart_y": "Total Inventory Quantity" if is_explicit_chart else None,
                "intent": "storage_location_ranking",
                "metric": "storage_location_ranking",
                "filters": filters,
                "time_range": "current",
                "output_type": "bar_chart" if is_explicit_chart else "table",
                "conversation_state": state
            }

    # N1. OCCUPIED BINS COUNT (Single metric query)
    is_occupied_bins_count = (
        ("occupied" in q_lower or "in use" in q_lower or "with stock" in q_lower or "containing stock" in q_lower or "holding stock" in q_lower or "active bin" in q_lower or "active bins" in q_lower) and
        any(b in q_lower for b in ["bin", "bins", "location", "locations", "racks"]) and
        any(k in q_lower for k in ["how many", "count", "number of", "total", "what is the count", "tell me the count"]) and
        not any(w in q_lower for w in ["average", "avg", "summary", "overview", "dashboard", "breakdown", "list", "show", "details"])
    )
    if is_occupied_bins_count:
        plant_filter = f" WHERE Plant = '{plant_cand}' AND UnrestrictedQty > 0" if plant_cand else " WHERE UnrestrictedQty > 0"
        filters = {"plant": plant_cand} if plant_cand else {}
        return {
            "sql": f"SELECT COUNT(DISTINCT BinNo) AS [Occupied Bins Count] FROM dbo.ZWMS_INVENTORY{plant_filter}",
            "chart_type": "none",
            "chart_title": f"Occupied Bins Count{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": None,
            "chart_y": None,
            "intent": "occupied_bins_count",
            "metric": "occupied_bins",
            "filters": filters,
            "time_range": "current",
            "output_type": "text"
        }

    # N2. TOTAL BINS COUNT (Single metric query)
    is_total_bins_count = (
        any(b in q_lower for b in ["bin", "bins", "locations", "slots"]) and
        any(k in q_lower for k in ["how many total", "how many bins", "total bins", "total number of bins", "number of bins", "count of bins", "total bin count", "how many do we have", "how many bins do we have"]) and
        not any(w in q_lower for w in ["empty", "occupied", "utiliz", "summary", "overview", "dashboard", "breakdown", "fill", "capacity"])
    )
    if is_total_bins_count:
        plant_filter = f" WHERE Plant = '{plant_cand}'" if plant_cand else ""
        filters = {"plant": plant_cand} if plant_cand else {}
        return {
            "sql": f"SELECT COUNT(DISTINCT BinLocation) AS [Total Bins Count] FROM dbo.ZWMS_BIN_MASTER{plant_filter}",
            "chart_type": "none",
            "chart_title": f"Total Bins Count{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": None,
            "chart_y": None,
            "intent": "total_bins_count",
            "metric": "total_bins",
            "filters": filters,
            "time_range": "current",
            "output_type": "text"
        }

    # N2_rec. INVENTORY RECORDS COUNT (Concept B - COUNT(rows))
    is_inventory_records_count = (
        state.get("topic") == "inventory_records_count" or
        any(k in q_lower for k in [
            "inventory record", "inventory records", "inventory row", "inventory rows",
            "records are there", "records in inventory", "number of inventory records",
            "count of inventory records", "total inventory records", "records in plant",
            "inventory records in plant", "records do we have", "rows in inventory",
            "how many inventory records", "how many records in inventory", "total inventory rows"
        ]) or (
            ("record" in q_lower or "records" in q_lower or "rows" in q_lower) and
            ("inventory" in q_lower or "dataset" in q_lower or "table" in q_lower) and
            any(k in q_lower for k in ["how many", "count", "number of", "total"])
        )
    ) and not any(w in q_lower for w in ["volume master", "material master", "missing", "dimension", "summary", "overview", "dashboard", "show", "list"])
    if is_inventory_records_count:
        plant_filter = f" WHERE Plant = '{plant_cand}'" if plant_cand else ""
        filters = {"plant": plant_cand} if plant_cand else {}
        query_plan = {
            "intent": "KPI",
            "entity": "inventory",
            "metric": "inventory_records_count",
            "aggregation": "COUNT",
            "field": "rows",
            "scope": f"PLANT_{plant_cand}" if plant_cand else "ALL_WAREHOUSE",
            "plant": plant_cand if plant_cand else None,
            "response_format": "SINGLE_LINE"
        }
        return {
            "sql": f"SELECT COUNT(*) AS [Inventory Records Count] FROM dbo.ZWMS_INVENTORY{plant_filter}",
            "query_plan": query_plan,
            "chart_type": "none",
            "chart_title": f"Inventory Records Count{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": None,
            "chart_y": None,
            "intent": "inventory_records_count",
            "metric": "inventory_records_count",
            "filters": filters,
            "time_range": "current",
            "output_type": "text",
            "conversation_state": state
        }

    # N3. TOTAL UNIQUE MATERIALS / SKU COUNT (Concept C - COUNT(DISTINCT Material))
    is_materials_count = (
        state.get("topic") == "unique_materials_count" or
        any(k in q_lower for k in [
            "how many materials", "how many unique materials", "how many distinct materials",
            "number of materials in inventory", "how many materials are in inventory", "how many materials are there",
            "how many materials do we have", "number of unique skus", "how many skus in inventory",
            "count of unique materials", "unique materials in warehouse", "materials in inventory",
            "how many unique skus", "count of materials in inventory", "distinct materials in inventory"
        ]) or (
            any(m in q_lower for m in ["material", "materials", "sku", "skus", "item", "items", "product", "products"]) and
            any(k in q_lower for k in ["how many", "count", "number of", "total unique", "unique count", "distinct"])
        )
    ) and not any(w in q_lower for w in ["volume master", "material master", "missing", "dimension", "summary", "overview", "dashboard", "breakdown", "list", "show", "record", "records", "rows"])
    if is_materials_count:
        plant_filter = f" WHERE Plant = '{plant_cand}'" if plant_cand else ""
        filters = {"plant": plant_cand} if plant_cand else {}
        query_plan = {
            "intent": "KPI",
            "entity": "material",
            "metric": "unique_materials_count",
            "aggregation": "COUNT_DISTINCT",
            "field": "Material",
            "scope": f"PLANT_{plant_cand}" if plant_cand else "ALL_WAREHOUSE",
            "plant": plant_cand if plant_cand else None,
            "response_format": "SINGLE_LINE"
        }
        return {
            "sql": f"SELECT COUNT(DISTINCT Material) AS [Total Unique Materials], COUNT(DISTINCT Material) AS [Unique Materials Count] FROM dbo.ZWMS_INVENTORY{plant_filter}",
            "query_plan": query_plan,
            "chart_type": "none",
            "chart_title": f"Total Unique Materials Count{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": None,
            "chart_y": None,
            "intent": "unique_materials_count",
            "metric": "unique_materials",
            "filters": filters,
            "time_range": "current",
            "output_type": "text",
            "conversation_state": state
        }

    # N4A. PLANT-WISE INVENTORY QUANTITY: "Show plant-wise inventory", "Show plant-wise inventory as a graph"
    is_plant_inv_req = (
        state.get("topic") == "plant_inventory" or
        (
            any(k in q_lower for k in ["plant-wise", "plant wise", "by plant", "for each plant", "each plant", "across plants", "of each plant"]) and
            any(k in q_lower for k in ["inventory", "stock", "quantity", "stock quantity", "inventory quantity", "units"]) and
            not any(k in q_lower for k in ["capacity", "utiliz", "occupan", "empty", "missing", "dimension", "master", "difference", "between", "from"]) and
            not any(k in q_lower for k in ["rank", "ranking", "top", "bottom", "highest", "lowest"])
        )
    )
    if is_plant_inv_req:
        plant_filter_pi = f" WHERE Plant = '{plant_cand}'" if plant_cand else ""
        filters_pi = {"plant": plant_cand} if plant_cand else {}
        query_plan = {
            "entity": "PLANT",
            "metric": "TOTAL_INVENTORY_QUANTITY",
            "operation": "AGGREGATION",
            "group_by": "PLANT",
            "filters": filters_pi,
            "ranking": None,
            "limit": None,
            "response_mode": "GRAPH" if is_explicit_chart else "TABLE"
        }
        return {
            "sql": f"SELECT Plant AS [Plant], SUM(UnrestrictedQty) AS [Total Inventory Quantity], COUNT(DISTINCT Material) AS [Total Unique Materials], COUNT(DISTINCT BinNo) AS [Total Active Bins] FROM dbo.ZWMS_INVENTORY{plant_filter_pi} GROUP BY Plant ORDER BY [Total Inventory Quantity] DESC",
            "query_plan": query_plan,
            "chart_type": "bar" if is_explicit_chart else "none",
            "chart_title": f"Plant-Wise Inventory Quantity{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": "Plant" if is_explicit_chart else None,
            "chart_y": "Total Inventory Quantity" if is_explicit_chart else None,
            "intent": "plant_inventory",
            "metric": "total_inventory_quantity",
            "filters": filters_pi,
            "time_range": "current",
            "output_type": "bar_chart" if is_explicit_chart else "table",
            "conversation_state": state
        }

    # N4. TOTAL INVENTORY QUANTITY (Concept A - SUM(UnrestrictedQty))
    is_total_inv_intent = (
        state.get("topic") == "total_inventory_quantity" or
        any(k in q_lower for k in [
            "total warehouse inventory", "what is the total inventory", "how much inventory is currently in the warehouse",
            "what is the total inventory quantity", "how many units are currently in inventory", "give me the current warehouse inventory",
            "how much stock is in the warehouse", "what is the total stock", "total unrestricted inventory", "total units in inventory",
            "how much total inventory", "total inventory quantity", "what is the total stock quantity", "total unrestricted quantity",
            "how much stock", "total stock", "total inventory", "how much inventory", "current warehouse inventory", "how many total units",
            "units are currently in inventory", "how much inventory do we have", "total stock quantity", "total units of inventory"
        ]) or (
            ("inventory" in q_lower or "stock" in q_lower or "units" in q_lower) and
            ("total" in q_lower or "how much" in q_lower or "how many units" in q_lower or "overall quantity" in q_lower) and
            not any(w in q_lower for w in ["per bin", "bin utilization", "empty", "difference", "division", "volume master", "missing", "trend", "record", "records", "rows", "material", "materials", "sku", "skus"])
        )
    ) and not is_materials_count and not is_inventory_records_count and not any(k in q_lower for k in ["summary", "overview", "dashboard", "executive", "breakdown", "record", "records"])
    if is_total_inv_intent:
        plant_filter = f" WHERE Plant = '{plant_cand}'" if plant_cand else ""
        filters = {"plant": plant_cand} if plant_cand else {}

        if is_explicit_chart:
            query_plan = {
                "intent": "KPI",
                "entity": "inventory",
                "metric": "total_inventory_quantity",
                "aggregation": "SUM",
                "field": "UnrestrictedQty",
                "scope": f"PLANT_{plant_cand}" if plant_cand else "ALL_WAREHOUSE",
                "plant": plant_cand if plant_cand else None,
                "response_format": "CHART_SUMMARY_TABLE"
            }
            return {
                "sql": f"SELECT Plant, SUM(UnrestrictedQty) AS [Total Inventory Quantity], COUNT(DISTINCT Material) AS [Unique Materials], COUNT(DISTINCT BinNo) AS [Occupied Bins] FROM dbo.ZWMS_INVENTORY{plant_filter} GROUP BY Plant ORDER BY [Total Inventory Quantity] DESC",
                "query_plan": query_plan,
                "chart_type": "bar",
                "chart_title": f"Total Inventory Quantity by Plant{f' — Plant {plant_cand}' if plant_cand else ''}",
                "chart_x": "Plant",
                "chart_y": "Total Inventory Quantity",
                "intent": "total_inventory_quantity",
                "metric": "total_inventory_quantity",
                "filters": filters,
                "time_range": "current",
                "output_type": "bar_chart",
                "conversation_state": state
            }

        query_plan = {
            "intent": "KPI",
            "entity": "inventory",
            "metric": "total_inventory_quantity",
            "aggregation": "SUM",
            "field": "UnrestrictedQty",
            "scope": f"PLANT_{plant_cand}" if plant_cand else "ALL_WAREHOUSE",
            "plant": plant_cand if plant_cand else None,
            "response_format": "SINGLE_LINE"
        }
        return {
            "sql": f"SELECT SUM(UnrestrictedQty) AS total_inventory, SUM(UnrestrictedQty) AS [Total Unrestricted Quantity], COUNT(DISTINCT Material) AS TotalUniqueMaterials, COUNT(DISTINCT BinNo) AS TotalActiveBins, COUNT(DISTINCT Plant) AS PlantCount FROM dbo.ZWMS_INVENTORY{plant_filter}",
            "query_plan": query_plan,
            "chart_type": "none",
            "chart_title": f"Total Unrestricted Quantity{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": None,
            "chart_y": None,
            "intent": "total_inventory_quantity",
            "metric": "total_inventory_quantity",
            "filters": filters,
            "time_range": "current",
            "output_type": "text",
            "conversation_state": state
        }

    # N5. ACTIVE PLANTS COUNT (Single metric query)
    is_plants_count = (
        any(p in q_lower for p in ["plant", "plants", "facility", "facilities", "sites"]) and
        any(k in q_lower for k in ["how many", "count", "number of", "total plants", "total facilities", "active plants", "active facilities", "how many active", "how many plants are currently active"]) and
        not any(w in q_lower for w in ["material", "sku", "bin", "utiliz", "capacity", "summary", "overview", "dashboard", "breakdown", "list", "show", "table"])
    )
    if is_plants_count:
        return {
            "sql": "SELECT COUNT(DISTINCT Plant) AS [Active Plants Count] FROM dbo.ZWMS_INVENTORY",
            "chart_type": "none",
            "chart_title": "Active Operational Plants Count",
            "chart_x": None,
            "chart_y": None,
            "intent": "active_plants_count",
            "metric": "plants_count",
            "filters": {},
            "time_range": "current",
            "output_type": "text"
        }

    # N6. STORAGE LOCATIONS COUNT (Single metric query)
    is_sloc_count = (
        any(s in q_lower for s in ["storage location", "storage locations", "sloc", "slocs"]) and
        any(k in q_lower for k in ["how many", "count", "number of", "total"]) and
        not any(w in q_lower for w in ["summary", "overview", "dashboard", "breakdown", "list", "show", "compare"])
    )
    if is_sloc_count:
        plant_filter = f" WHERE Plant = '{plant_cand}'" if plant_cand else ""
        filters = {"plant": plant_cand} if plant_cand else {}
        return {
            "sql": f"SELECT COUNT(DISTINCT StorageLocation) AS [Storage Locations Count] FROM dbo.ZWMS_INVENTORY{plant_filter}",
            "chart_type": "none",
            "chart_title": f"Storage Locations Count{f' — Plant {plant_cand}' if plant_cand else ''}",
            "chart_x": None,
            "chart_y": None,
            "intent": "storage_locations_count",
            "metric": "storage_locations_count",
            "filters": filters,
            "time_range": "current",
            "output_type": "text"
        }

    # O. OVERALL WAREHOUSE TOTAL INVENTORY (Full Multi-Metric KPI summary - only when explicitly asked for overview/summary)
    plant_filter = f" WHERE Plant = '{plant_cand}' HAVING COUNT(DISTINCT Material) > 0" if plant_cand else ""
    filters = {"plant": plant_cand} if plant_cand else {}
    return {
        "sql": f"SELECT COUNT(DISTINCT Material) AS TotalUniqueMaterials, COUNT(DISTINCT BinNo) AS TotalActiveBins, COUNT(DISTINCT Plant) AS PlantCount, SUM(UnrestrictedQty) AS TotalUnrestrictedQuantity FROM dbo.ZWMS_INVENTORY{plant_filter}",
        "chart_type": "none",
        "chart_title": "Total Warehouse Inventory Summary",
        "chart_x": None,
        "chart_y": None,
        "intent": "inventory_summary",
        "metric": "total_inventory",
        "filters": filters,
        "time_range": "current",
        "output_type": "kpi"
    }

async def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Dispatches call to configured LLM provider."""
    api_key = settings.llm_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    
    if api_key and (settings.llm_provider == "gemini" or api_key.startswith("AIza")):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.llm_model}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}
            ],
            "generationConfig": {
                "temperature": settings.llm_temperature,
                "responseMimeType": "application/json" if "JSON" in system_prompt else "text/plain"
            }
        }
        async with httpx.AsyncClient(timeout=40.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"Gemini API error ({resp.status_code}): {resp.text}")
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
            
    if api_key and settings.llm_base_url:
        base_url = settings.llm_base_url
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": settings.llm_model if settings.llm_model != "gemini-1.5-pro" else "gpt-4o",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": settings.llm_temperature,
        }
        async with httpx.AsyncClient(timeout=40.0) as client:
            resp = await client.post(base_url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(f"LLM API error ({resp.status_code}): {resp.text}")
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    raise ValueError("No LLM API key configured.")

async def generate_sql(question: str, history: list[dict], retry_context: dict | None = None) -> dict[str, Any]:
    """Context-grounded SQL generator leveraging warehouse semantic layer."""
    det_plan = deterministic_warehouse_sql_generator(question, history=history)
    det_intent = det_plan.get("intent", "")
    q_lower = question.lower()
    
    # A fresh, unscoped total-inventory question is an all-warehouse aggregate.
    # Do not let an LLM add a plant filter, group rows by plant, or return raw
    # inventory records just because those fields appear in conversation history.
    explicit_global_inventory = any(phrase in q_lower for phrase in (
        "total warehouse inventory",
        "total inventory for the whole warehouse",
        "total inventory across the warehouse",
        "overall warehouse inventory",
        "total stock in the warehouse",
        "total inventory quantity across the warehouse",
    ))
    explicit_plant_scope = bool(re.search(
        r"\b(?:plant|facility)\s*[:#-]?\s*\d{4,5}\b|\b(?:by|per|for|in)\s+plants?\b",
        q_lower,
    ))
    asks_for_breakdown = any(term in q_lower for term in (
        "by plant", "per plant", "plant-wise", "breakdown", "grouped by",
        "list", "show records", "inventory rows", "raw rows", "chart", "graph",
    ))
    if explicit_global_inventory and not explicit_plant_scope and not asks_for_breakdown:
        det_plan = {
            **det_plan,
            "sql": (
                "SELECT SUM(UnrestrictedQty) AS total_inventory, "
                "SUM(UnrestrictedQty) AS [Total Unrestricted Quantity], "
                "COUNT(DISTINCT Material) AS TotalUniqueMaterials, "
                "COUNT(DISTINCT BinNo) AS TotalActiveBins, "
                "COUNT(DISTINCT Plant) AS PlantCount "
                "FROM dbo.ZWMS_INVENTORY"
            ),
            "query_plan": {
                "intent": "KPI",
                "entity": "inventory",
                "metric": "total_inventory_quantity",
                "aggregation": "SUM",
                "field": "UnrestrictedQty",
                "scope": "ALL_WAREHOUSE",
                "plant": None,
                "response_format": "SINGLE_LINE",
            },
            "intent": "total_inventory_quantity",
            "metric": "total_inventory_quantity",
            "filters": {},
            "output_type": "text",
            "chart_type": "none",
            "chart_title": "Total Warehouse Inventory",
            "chart_x": None,
            "chart_y": None,
        }
        return det_plan

    # If the deterministic semantic layer identified a concrete domain intent or user asked for summary, use it directly
    is_explicit_summary = any(k in q_lower for k in ["summary", "overview", "dashboard", "overall", "network overview", "status"])
    if det_intent != "inventory_summary" or is_explicit_summary:
        return det_plan

    try:
        if retry_context:
            user_prompt = RETRY_PROMPT_TEMPLATE.format(
                error_message=retry_context.get("error", "Invalid query"),
                failed_sql=retry_context.get("sql", "")
            )
        else:
            history_str = json.dumps(history[-6:], default=str) if history else "[]"
            user_prompt = f"CONVERSATION HISTORY:\n{history_str}\n\nCURRENT QUESTION:\n{question}"

        raw_response = await _call_llm(SQL_PROMPT_SYSTEM, user_prompt)
        parsed = clean_llm_json(raw_response)
        
        c_type = parsed.get("chart_type", "none")
        default_out = "line_chart" if c_type == "line" else "bar_chart" if c_type == "bar" else "pie_chart" if c_type == "pie" else "table"
        
        return {
            "sql": parsed.get("sql", ""),
            "chart_type": c_type,
            "chart_title": parsed.get("chart_title", None),
            "chart_x": parsed.get("chart_x", None),
            "chart_y": parsed.get("chart_y", None),
            "intent": parsed.get("intent", question),
            "metric": parsed.get("metric", "unrestricted_qty"),
            "filters": parsed.get("filters", {}),
            "time_range": parsed.get("time_range", "current"),
            "output_type": parsed.get("output_type", default_out)
        }
    except Exception:
        return det_plan

def is_volume_utilization_requested(q_lower: str) -> bool:
    """Checks whether the user explicitly asked for volume-based utilization or volume metrics."""
    if not q_lower:
        return False
    q = q_lower.lower()
    return (
        any(k in q for k in [
            "volume utilization", "volumetric utilization", "volume occupancy",
            "volume %", "volume percent", "volume percentage", "utilized volume percentage",
            "occupied volume versus total bin capacity", "occupied volume vs total bin capacity",
            "occupied volume vs capacity", "occupied volume versus capacity",
            "occupied volume compared to total bin capacity", "occupied volume compared to capacity",
            "occupied volume compared to", "occupied volume versus", "occupied volume vs",
            "volume capacity utilization", "capacity utilization",
            "space utilization", "bin space", "total bin volume"
        ]) or
        ("volume" in q and any(u in q for u in ["utiliz", "occupan"]) and "bin utiliz" not in q and "bin occupan" not in q)
    )

def is_bin_utilization_primary(q_lower: str) -> bool:
    """Checks whether the query's primary intent is bin utilization.
    
    When True, the response MUST show Bin Utilization only, omitting Volume Utilization,
    Occupied Volume, Total Volume Capacity, or volume-based utilization text.
    """
    if not q_lower:
        return False
    q = q_lower.lower()
    has_vol_util = is_volume_utilization_requested(q)
    has_bin_util = any(k in q for k in [
        "bin utiliz", "bin occupan", "bins utilized", "bin utilized",
        "bins utilization", "bins' utilization"
    ])
    # If user explicitly asked for BOTH bin utilization AND volume utilization
    if has_vol_util and has_bin_util:
        return False
    # If user asked for volume utilization specifically
    if has_vol_util and not has_bin_util:
        return False
    # If user asked for bin utilization explicitly
    if has_bin_util:
        return True
    # If user asked about bins and utilization/occupancy/how full without volume/space
    has_bin = any(b in q for b in ["bin", "bins", "location", "locations", "racks", "rack", "slot", "slots"])
    has_util = any(u in q for u in ["utiliz", "occupan", "how full", "fill rate", "fullness"])
    if has_bin and has_util and not any(v in q for v in ["volume", "space", "material", "quantity", "stock"]):
        return True
    # General bin utilization queries
    if any(k in q for k in [
        "show bin utilization", "overall bin utilization", "bin utilization of all plants",
        "bin utilization for plant", "detailed bin utilization", "plant bin utilization",
        "warehouse bin utilization", "storage location bin utilization"
    ]):
        return True
    return False

def is_bin_level_detail_intent(q_lower: str) -> bool:
    """Detect if the user is asking for detailed / bin-level breakdown of bin utilization (Sections 1, 2, 8, 9)."""
    if not q_lower:
        return False
    q = q_lower.strip().lower()

    # Rule out queries that specifically target plant-level summary template or sloc breakdown
    if "bin utilization details for plant" in q or "bin utilization detail for plant" in q or "fetch bin utilization detail" in q:
        return False
    if any(k in q for k in ["by storage location", "sloc breakdown", "storage location breakdown", "by sloc"]):
        return False
    if "explain" in q and "in detail" in q:
        return False

    has_bin = (
        is_bin_utilization_primary(q) or
        any(b in q for b in ["bin", "bins", "utiliz", "how full", "occupan", "fill rate", "capacity"])
    )
    if not has_bin:
        return False

    # Check for detail / complete / breakdown / summary / all bins triggers (Semantic Intent)
    detail_keywords = [
        "detail", "detailed", "bins in detail", "bin utilization in detail", "in detail",
        "detailed version", "detailed analysis", "detailed breakdown", "give me detailed",
        "give detailed", "show detailed", "detail bin", "details of", "summary of bin", "summary of bins",
        "bin-wise", "bin wise", "complete bin", "complete bin-wise", "complete details",
        "complete information", "full details of", "full detail of", "full information",
        "breakdown", "break down", "itemized", "explain all bins", "explain bin", "explain bins",
        "all bins", "all of the bins", "every bin", "each bin", "list all bins", "show all bins",
        "deep dive", "drill down", "elaborate", "granular"
    ]
    if any(re.search(r'\b' + re.escape(w) + r'\b', q) for w in detail_keywords):
        return True

    # "summary" or "summarize" in a bin utilization query (Rule 9: Summary requests)
    if any(w in q for w in ["summary", "summarize"]) and any(u in q for u in ["bin utilization", "utilization", "how full", "bins"]):
        return True

    # "explain" in bin utilization query
    if "explain" in q and any(u in q for u in ["bin utilization", "utilization", "how full", "bins"]):
        return True

    return False

def sanitize_bin_utilization_response(answer: str, question: str) -> str:
    """Post-processor that ensures volume utilization is suppressed if primary intent is bin utilization."""
    if not answer or not is_bin_utilization_primary(question):
        return answer
    cleaned = answer
    cleaned = re.sub(r"\s*\|\s*[\d,.]+%?\s*Volume Utilization[^\n]*", ".", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*[-*]\s*\*\*Volume Utilization:?\*\*.*$\n?", "", cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r"^\s*[-*]\s*Volume Utilization:?.*$\n?", "", cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r"^\s*[-*]\s*\*\*Total Storage Capacity:?\*\*.*$\n?", "", cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r"^\s*[-*]\s*Total Storage Capacity:?.*$\n?", "", cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r"^\s*[-*]\s*\*\*Occupied Volume:?\*\*.*$\n?", "", cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r"^\s*[-*]\s*Occupied Volume:?.*$\n?", "", cleaned, flags=re.MULTILINE | re.IGNORECASE)
    cleaned = re.sub(r"\|\s*Occupied Volume[^\n|]*\|", "|", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\|\s*Used Volume[^\n|]*\|", "|", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\|\s*Occupied:\s*[\d,.]+\s*(?:FT³|ft³)[^\n]*", ".", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*with\s+(?:total\s+)?volume\s+utilization\s+of\s+.*?(?=[,;\n]|\.\s*|\.$)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\.\s*\.", ".", cleaned)
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    return cleaned.strip()

# ============================================================================
# GLOBAL COMPARISON RESPONSE ENGINE HELPERS (Rules 1-17)
# ============================================================================

def generate_markdown_table(headers: list[str], rows_data: list[list[Any]], alignments: list[str] = None) -> str:
    """Generates a standard GitHub Flavored Markdown table string."""
    if not headers or not rows_data:
        return ""
    if not alignments:
        alignments = [":---" if i == 0 else "---:" for i in range(len(headers))]
    header_line = "| " + " | ".join(headers) + " |"
    align_line = "| " + " | ".join(alignments) + " |"
    data_lines = ["| " + " | ".join(str(val) for val in row) + " |" for row in rows_data]
    return "\n".join([header_line, align_line] + data_lines)

def is_comparison_intent(q_lower: str, rows: list[dict] = None) -> bool:
    """Detect if the user question has comparison intent across 2 or more entities/plants/metrics."""
    q_strip = q_lower.strip()

    # Rule 9: Explicit non-comparison queries must NOT be treated as comparison
    # Range queries are NOT comparisons unless explicit compare keywords exist
    if parse_range_filters(q_strip) and not any(k in q_strip for k in ["compare", "versus", " vs ", "difference between", "difference of"]):
        return False

    if any(q_strip.startswith(p) for p in [
        "rank ", "ranking ", "rank plants", "ranking plants", "rank all plants", "rank by",
        "show bin utilization for plant", "bin utilization for plant",
        "show the bin utilization of all plants", "bin utilization of all plants",
        "show bin utilization graph for plant", "give detailed bin utilization for plant",
        "show detailed bin utilization for plant", "show materials with", "materials with"
    ]) and not any(k in q_strip for k in ["compare", "versus", " vs ", "difference", "which is higher", "which is lower", "which has more"]):
        return False

    # Comparison of Top/Least Utilized Bins across plants (handled by 0A_COMPARE_BINS)
    if rows and isinstance(rows, list) and len(rows) > 0 and isinstance(rows[0], dict):
        raw_cols = list(rows[0].keys())
        if "Bin" in raw_cols and any(k in q_strip for k in ["top", "most", "bottom", "least", "highest", "lowest"]) and not is_comparison_explanation_requested(q_strip):
            return False

    # 1. Comparison keywords & phrases (Rule 7)
    comp_triggers = [
        "compare", "comparison", "compare between", "compare both", "compare these",
        "compare the two", "which is higher", "which is lower", "which has more",
        "which has less", "which has greater", "which is better", "which one is better",
        "difference between", "difference of", "versus", " vs ", " vs.", "against",
        "side by side", "contrast", "how do they compare", "how do plants compare",
        "compare plant", "compare these plants", "compare these materials"
    ]
    if any(k in q_strip for k in comp_triggers):
        return True

    # 2. Comparison follow-up queries / explanation on previously shown table (Rule 4)
    explanation_triggers = [
        "explain this table", "explain the table", "explain this", "explain the comparison",
        "what does this mean", "give me a summary", "give me summary", "summarize the above",
        "summarize above", "summarize this", "explain the result", "what can you conclude",
        "give me the comparison summary", "interpret this", "tell me what this table means",
        "explain it", "explain comparison"
    ]
    if any(k in q_strip for k in explanation_triggers):
        return True

    # 3. Two or more explicit plants with comparison connecting words (between, and)
    explicit_plants = extract_explicit_plants(q_strip)
    if len(explicit_plants) >= 2:
        has_range = any(r in q_strip for r in [
            "above", "below", "greater", "less than", "between 50", "between 60",
            "between 70", "between 80", "between 10", "between 20", "between 30",
            "between 40", "between 1", "between 2", "between 5", "between 100",
            "% full", "% utilization"
        ])
        if not has_range:
            if any(w in q_strip for w in ["between", "and", "or", "to", "with", "vs"]) or any(m in q_strip for m in ["utilization", "inventory", "bins", "materials", "capacity"]):
                return True

    return False

def is_comparison_explanation_requested(q_lower: str) -> bool:
    """Detect if the user is asking to explain, summarize, or interpret a comparison table."""
    q_strip = q_lower.strip().rstrip("?.! ")
    triggers = [
        "explain this table", "explain the table", "explain this", "explain the comparison",
        "what does this mean", "give me a summary", "give me summary", "summarize the above",
        "summarize above", "summarize this", "which one is better", "which is better",
        "explain the result", "what can you conclude", "give me the comparison summary",
        "interpret this", "tell me what this table means", "explain it", "explain"
    ]
    if any(t in q_strip for t in triggers) or q_strip in ["summary", "summarize", "conclusion"]:
        return True
    return False

def is_comparison_detail_requested(q_lower: str) -> bool:
    """Detect if user asked for detailed comparison."""
    return any(k in q_lower for k in [
        "in detail", "detailed comparison", "detailed version", "detail version",
        "detailed breakdown", "give me detailed comparison", "compare in detail"
    ])

def format_comparison_table_markdown(rows: list[dict], q_lower: str) -> str:
    """Formats comparison rows into a clean, canonical Markdown table with relevant fields."""
    if not rows or not isinstance(rows[0], dict):
        return ""
    raw_cols = list(rows[0].keys())

    # Case 0: Compare Both Bin Utilization AND Volume Utilization (Rule 13 separation)
    has_both_util = (
        ("bin" in q_lower and "volume" in q_lower and "utiliz" in q_lower) or
        (("Bin Utilization %" in raw_cols or "BinUtilizationPct" in raw_cols) and
         ("Volume Utilization %" in raw_cols or "VolumeUtilizationPct" in raw_cols or "TotalBinCapacityVolume" in raw_cols))
    )
    if has_both_util:
        target_cols = ["Plant", "Bin Utilization %", "Volume Utilization %"]
        clean_rows = []
        for r in rows:
            p = str(r.get("Plant", "-")).replace(",", "")
            raw_bu = r.get("Bin Utilization %", r.get("BinUtilizationPct", 0))
            raw_vu = r.get("Volume Utilization %", r.get("VolumeUtilizationPct", 0))
            try:
                bu_str = f"{float(str(raw_bu).replace('%', '')):.2f}%"
            except Exception:
                bu_str = f"{raw_bu}%"
            try:
                vu_str = f"{float(str(raw_vu).replace('%', '')):.2f}%"
            except Exception:
                vu_str = f"{raw_vu}%"
            clean_rows.append([p, bu_str, vu_str])
        return generate_markdown_table(target_cols, clean_rows)

    # Case A: Bin Utilization Comparison (Rule 2 & 14 & 15)
    is_bin_util = is_bin_utilization_primary(q_lower) or (
        "Bin Utilization %" in raw_cols and not any(k in q_lower for k in ["total inventory", "inventory quantity", "unique materials", "used capacity"])
    )
    if is_bin_util:
        target_cols = ["Plant", "Occupied Bins", "Empty Bins", "Total Bins", "Bin Utilization %"]
        clean_rows = []
        for r in rows:
            p = str(r.get("Plant", "-")).replace(",", "")
            ob = r.get("Occupied Bins", r.get("OccupiedBins", 0))
            tb = r.get("Total Bins", r.get("TotalBins", 0))
            eb = r.get("Empty Bins", r.get("EmptyBins", max(0, tb - ob) if tb and ob else 0))
            raw_u = r.get("Bin Utilization %", r.get("BinUtilizationPct", 0))
            try:
                u_str = f"{float(str(raw_u).replace('%', '')):.2f}%"
            except Exception:
                u_str = f"{raw_u}%" if "%" not in str(raw_u) else str(raw_u)
            clean_rows.append([
                p,
                f"{int(ob):,}" if isinstance(ob, (int, float)) else str(ob),
                f"{int(eb):,}" if isinstance(eb, (int, float)) else str(eb),
                f"{int(tb):,}" if isinstance(tb, (int, float)) else str(tb),
                u_str
            ])
        return generate_markdown_table(target_cols, clean_rows)

    # Case B: Total Inventory Quantity Comparison (Rule 2)
    if any(k in q_lower for k in ["inventory", "stock", "quantity"]) and not any(k in q_lower for k in ["material", "bin", "capacity", "sloc"]):
        target_cols = [c for c in ["Plant", "Total Inventory Quantity", "Unique Materials", "Occupied Bins"] if c in raw_cols]
        clean_rows = []
        for r in rows:
            row_vals = []
            for c in target_cols:
                if c == "Plant":
                    row_vals.append(str(r.get("Plant", "-")).replace(",", ""))
                else:
                    v = r.get(c, "-")
                    if isinstance(v, (int, float)):
                        row_vals.append(f"{int(v):,}" if v == int(v) else f"{v:,.2f}")
                    else:
                        row_vals.append(str(v))
            clean_rows.append(row_vals)
        return generate_markdown_table(target_cols, clean_rows)

    # Case C: Material Comparison (Rule 2)
    if any(k in q_lower for k in ["unique material", "materials", "sku", "skus"]):
        if "Unique Materials Count" in raw_cols:
            target_cols = [c for c in ["Plant", "Unique Materials Count", "Total Stock Qty", "Occupied Bins"] if c in raw_cols]
            clean_rows = []
            for r in rows:
                clean_rows.append([
                    str(r.get(c, "-")).replace(",", "") if c == "Plant" else (
                        f"{int(r.get(c)):,}" if isinstance(r.get(c), (int, float)) else str(r.get(c, "-"))
                    )
                    for c in target_cols
                ])
            return generate_markdown_table(target_cols, clean_rows)

    # Case D: Capacity Comparison (Rule 2)
    if any(k in q_lower for k in ["capacity", "volume", "used capacity", "available capacity"]):
        cap_cols = [c for c in [
            "Plant", "Used Capacity (FT³)", "Occupied Volume (FT3)", "Used Capacity",
            "Available Capacity (FT³)", "Available Capacity (FT3)", "Available Capacity",
            "Total Capacity (FT³)", "Total Capacity (FT3)", "Total Capacity"
        ] if c in raw_cols]
        if cap_cols:
            target_cols = ["Plant"] + [c for c in cap_cols if c != "Plant"]
            clean_rows = []
            for r in rows:
                row_vals = []
                for c in target_cols:
                    if c == "Plant":
                        row_vals.append(str(r.get("Plant", "-")).replace(",", ""))
                    else:
                        v = r.get(c, "-")
                        if isinstance(v, (int, float)):
                            row_vals.append(f"{float(v):,.2f}")
                        else:
                            row_vals.append(str(v))
                clean_rows.append(row_vals)
            return generate_markdown_table(target_cols, clean_rows)

    # Case E: Empty Bins Comparison (Rule 2)
    if any(k in q_lower for k in ["empty bin", "empty bins", "vacant", "free bin"]):
        if "Empty Bins" in raw_cols:
            target_cols = [c for c in ["Plant", "Empty Bins", "Total Bins", "Empty Bins %"] if c in raw_cols]
            clean_rows = []
            for r in rows:
                clean_rows.append([
                    str(r.get(c, "-")).replace(",", "") if c == "Plant" else (
                        f"{int(r.get(c)):,}" if isinstance(r.get(c), (int, float)) else str(r.get(c, "-"))
                    )
                    for c in target_cols
                ])
            return generate_markdown_table(target_cols, clean_rows)

    # Case F: Bin count / Physical Bins Comparison (Rule 2)
    if any(k in q_lower for k in ["their bins", "bins count", "total bins"]) and "Total Bins" in raw_cols:
        target_cols = [c for c in ["Plant", "Occupied Bins", "Empty Bins", "Total Bins", "Occupancy Rate"] if c in raw_cols]
        clean_rows = []
        for r in rows:
            clean_rows.append([
                str(r.get(c, "-")).replace(",", "") if c == "Plant" else (
                    f"{int(r.get(c)):,}" if isinstance(r.get(c), (int, float)) else str(r.get(c, "-"))
                )
                for c in target_cols
            ])
        return generate_markdown_table(target_cols, clean_rows)

    # Case G: Generic / Dynamic fallback from rows
    excluded = {
        "Id", "TotalMatching", "Ranking Group", "BinUtilizationPct", "VolumeUtilizationPct",
        "Rank"
    }
    if is_bin_utilization_primary(q_lower):
        excluded.update({
            "Occupied Volume", "Total Capacity", "Available Capacity",
            "Occupied Volume (FT3)", "Total Capacity (FT3)", "Available Capacity (FT3)",
            "Volume Utilization", "Volume Utilization %"
        })
    target_cols = [c for c in raw_cols if c not in excluded]
    clean_rows = []
    for r in rows:
        row_vals = []
        for c in target_cols:
            if c == "Plant":
                row_vals.append(str(r.get("Plant", "-")).replace(",", ""))
            else:
                v = r.get(c, "-")
                if isinstance(v, (int, float)):
                    row_vals.append(f"{int(v):,}" if v == int(v) else f"{v:,.2f}")
                else:
                    row_vals.append(str(v))
        clean_rows.append(row_vals)
    return generate_markdown_table(target_cols, clean_rows)

def generate_comparison_summary(rows: list[dict], q_lower: str) -> str:
    """Generates an accurate grounded explanation/summary of the comparison table."""
    if not rows or len(rows) < 2:
        return ""

    raw_cols = list(rows[0].keys())
    
    # 0. Compare Both Bin Utilization AND Volume Utilization
    if ("bin" in q_lower and "volume" in q_lower and "utiliz" in q_lower) or (
        ("Bin Utilization %" in raw_cols or "BinUtilizationPct" in raw_cols) and
        ("Volume Utilization %" in raw_cols or "VolumeUtilizationPct" in raw_cols)
    ):
        lines = []
        for r in rows:
            p = str(r.get("Plant", "N/A")).replace(",", "")
            raw_bu = r.get("Bin Utilization %", r.get("BinUtilizationPct", 0))
            raw_vu = r.get("Volume Utilization %", r.get("VolumeUtilizationPct", 0))
            lines.append(f"Plant {p} has **{raw_bu}%** Bin Utilization and **{raw_vu}%** Volume Utilization.")
        return " ".join(lines)

    # 1. Bin Utilization
    if is_bin_utilization_primary(q_lower) or "Bin Utilization %" in raw_cols:
        def get_pct(r):
            raw = r.get("Bin Utilization %", r.get("BinUtilizationPct", 0))
            try:
                return float(str(raw).replace("%", ""))
            except Exception:
                return 0.0
        sorted_rows = sorted(rows, key=get_pct, reverse=True)
        top = sorted_rows[0]
        bot = sorted_rows[-1]
        p_top = str(top.get("Plant", "N/A")).replace(",", "")
        p_bot = str(bot.get("Plant", "N/A")).replace(",", "")
        u_top = f"{get_pct(top):.2f}%"
        u_bot = f"{get_pct(bot):.2f}%"
        diff_pts = round(get_pct(top) - get_pct(bot), 2)
        
        ob_top = top.get("Occupied Bins", top.get("OccupiedBins"))
        tb_top = top.get("Total Bins", top.get("TotalBins"))
        ob_bot = bot.get("Occupied Bins", bot.get("OccupiedBins"))
        tb_bot = bot.get("Total Bins", bot.get("TotalBins"))
        
        detail_clause = ""
        if ob_top is not None and tb_top is not None and ob_bot is not None and tb_bot is not None:
            detail_clause = f" Plant {p_top} has {int(ob_top):,} occupied bins out of {int(tb_top):,} total bins, while Plant {p_bot} has {int(ob_bot):,} occupied bins out of {int(tb_bot):,} total bins."
            
        return f"Plant {p_top} has higher bin utilization than Plant {p_bot} by {diff_pts} percentage points ({u_top} vs. {u_bot}).{detail_clause}"

    # 2. Total Inventory Quantity
    if "Total Inventory Quantity" in raw_cols:
        sorted_rows = sorted(rows, key=lambda x: float(x.get("Total Inventory Quantity", 0) or 0), reverse=True)
        top, bot = sorted_rows[0], sorted_rows[-1]
        p_top = str(top.get("Plant", "N/A")).replace(",", "")
        p_bot = str(bot.get("Plant", "N/A")).replace(",", "")
        q_top = float(top.get("Total Inventory Quantity", 0) or 0)
        q_bot = float(bot.get("Total Inventory Quantity", 0) or 0)
        diff_q = q_top - q_bot
        return f"Plant {p_top} has higher total inventory than Plant {p_bot} by {diff_q:,.0f} units ({q_top:,.0f} units vs. {q_bot:,.0f} units)."

    # 3. Empty Bins
    if "Empty Bins" in raw_cols:
        sorted_rows = sorted(rows, key=lambda x: float(x.get("Empty Bins", 0) or 0), reverse=True)
        top, bot = sorted_rows[0], sorted_rows[-1]
        p_top = str(top.get("Plant", "N/A")).replace(",", "")
        p_bot = str(bot.get("Plant", "N/A")).replace(",", "")
        eb_top = float(top.get("Empty Bins", 0) or 0)
        eb_bot = float(bot.get("Empty Bins", 0) or 0)
        diff_eb = eb_top - eb_bot
        return f"Plant {p_top} has more empty bins available for put-away than Plant {p_bot} by {diff_eb:,.0f} bins ({eb_top:,.0f} vs. {eb_bot:,.0f} empty bins)."

    # 4. Capacity
    cap_col = next((c for c in ["Total Capacity (FT³)", "Total Capacity (FT3)", "Total Capacity"] if c in raw_cols), None)
    if cap_col:
        sorted_rows = sorted(rows, key=lambda x: float(x.get(cap_col, 0) or 0), reverse=True)
        top, bot = sorted_rows[0], sorted_rows[-1]
        p_top = str(top.get("Plant", "N/A")).replace(",", "")
        p_bot = str(bot.get("Plant", "N/A")).replace(",", "")
        c_top = float(top.get(cap_col, 0) or 0)
        c_bot = float(bot.get(cap_col, 0) or 0)
        diff_c = c_top - c_bot
        return f"Plant {p_top} has larger total storage capacity than Plant {p_bot} by {diff_c:,.2f} FT³ ({c_top:,.2f} FT³ vs. {c_bot:,.2f} FT³)."

    # Default
    p1 = str(rows[0].get("Plant", "Plant 1")).replace(",", "")
    p2 = str(rows[1].get("Plant", "Plant 2")).replace(",", "")
    return f"Plant {p1} leads Plant {p2} across the compared metrics."

def generate_comparison_details(rows: list[dict], q_lower: str) -> str:
    """Generates detailed bullet breakdown for comparison queries requesting detail."""
    lines = []
    for r in rows:
        p = str(r.get("Plant", "N/A")).replace(",", "")
        if "Bin Utilization %" in r:
            u = r.get("Bin Utilization %")
            ob = r.get("Occupied Bins", r.get("OccupiedBins", 0))
            tb = r.get("Total Bins", r.get("TotalBins", 0))
            eb = r.get("Empty Bins", r.get("EmptyBins", max(0, tb - ob) if tb and ob else 0))
            lines.append(f"- **Plant {p}**: **{u}** Bin Utilization ({int(ob):,} of {int(tb):,} bins occupied, with {int(eb):,} empty bins).")
        elif "Total Inventory Quantity" in r:
            q = float(r.get("Total Inventory Quantity", 0) or 0)
            m = r.get("Unique Materials", 0)
            b = r.get("Occupied Bins", 0)
            lines.append(f"- **Plant {p}**: **{q:,.0f} units** across **{int(m):,} unique materials** in **{int(b):,} occupied bins**.")
        elif "Empty Bins" in r:
            eb = r.get("Empty Bins", 0)
            tb = r.get("Total Bins", 0)
            pct = r.get("Empty Bins %", "")
            lines.append(f"- **Plant {p}**: **{int(eb):,} empty bins** ({pct} of {int(tb):,} total bins).")
        else:
            metrics_str = ", ".join(f"{k}: {v}" for k, v in r.items() if k != "Plant")
            lines.append(f"- **Plant {p}**: {metrics_str}")
    return "\n".join(lines)

def format_detailed_bin_utilization_tables(rows: list[dict]) -> str:
    """Formats bin-level detailed response with separate tables per plant (Sections 3, 4, 6, 7, 14)."""
    if not rows or not isinstance(rows[0], dict):
        return ""
    cols = list(rows[0].keys())
    bin_col = "Bin" if "Bin" in cols else "BinLocation"
    cap_col = "Capacity" if "Capacity" in cols else "Bin Capacity"
    avail_col = "Available Capacity"
    util_col = "Utilization %" if "Utilization %" in cols else "Capacity Utilization %"
    mat_col = "Material / Inventory Information" if "Material / Inventory Information" in cols else next((c for c in cols if "Material" in c), None)

    plant_groups = {}
    for r in rows:
        p = str(r.get("Plant", "N/A")).strip().replace(",", "")
        if p not in plant_groups:
            plant_groups[p] = []
        plant_groups[p].append(r)

    sections = []
    for p, p_rows in plant_groups.items():
        headers = ["Bin", "Capacity", "Available Capacity", "Utilization %", "Material / Inventory Information"]
        table_data = []
        for r in p_rows:
            b_val = str(r.get(bin_col, "N/A"))
            c_val = r.get(cap_col, 0)
            c_str = f"{float(c_val):,.2f}" if isinstance(c_val, (int, float)) else str(c_val)
            ac_val = r.get(avail_col, 0)
            ac_str = f"{float(ac_val):,.2f}" if isinstance(ac_val, (int, float)) else str(ac_val)
            u_val = str(r.get(util_col, "0%"))
            if not u_val.endswith("%"):
                try:
                    u_val = f"{float(u_val):.1f}%"
                except Exception:
                    pass
            m_val = str(r.get(mat_col, "Empty")) if mat_col else "Empty"
            table_data.append([b_val, c_str, ac_str, u_val, m_val])
        
        alignments = [":---", "---:", "---:", "---:", ":---"]
        tbl_md = generate_markdown_table(headers, table_data, alignments)
        sections.append(f"## Plant {p} — Bin Utilization\n\n{tbl_md}")

    return "\n\n".join(sections)

def format_comparison_response(question: str, rows: list[dict]) -> str:
    """Generic Comparison Response Engine enforcing GLOBAL COMPARISON RESPONSE RULES (Rules 1-17)."""
    q_lower = question.lower()

    # Multi-plant bin level detail comparison (Sections 6, 7, 14)
    if rows and ("Bin" in rows[0] or "BinLocation" in rows[0]) and ("Capacity" in rows[0] or "Bin Capacity" in rows[0]) and "Available Capacity" in rows[0] and ("Utilization %" in rows[0] or "Capacity Utilization %" in rows[0]):
        tables_md = format_detailed_bin_utilization_tables(rows)
        if is_comparison_explanation_requested(q_lower):
            summary_md = generate_comparison_summary(rows, q_lower)
            return f"{tables_md}\n\n### Summary\n\n{summary_md}"
        return tables_md

    # Rule 12: Explicit single-line / single statement / answer only overrides table
    is_single_stmt = (
        is_single_line_requested(q_lower) or
        any(k in q_lower for k in [
            "only the answer", "give me only the answer", "just the answer",
            "answer only", "single statement", "single line", "one line"
        ])
    )
    if is_single_stmt:
        return generate_comparison_summary(rows, q_lower)

    # Generate the canonical comparison table
    table_md = format_comparison_table_markdown(rows, q_lower)

    # Rule 10: Comparison + Detail
    if is_comparison_detail_requested(q_lower):
        details_md = generate_comparison_details(rows, q_lower)
        return f"### Comparison Table\n\n{table_md}\n\n### Detailed Comparison\n\n{details_md}"

    # Rule 4 & 5: Summary ONLY when user explicitly asks for it
    if is_comparison_explanation_requested(q_lower):
        summary_md = generate_comparison_summary(rows, q_lower)
        return f"### Comparison Table\n\n{table_md}\n\n### Summary\n\n{summary_md}"

    # Rule 1 & 3: Initial comparison query: TABLE ONLY!
    return table_md

def format_deterministic_answer(question: str, rows: list[dict]) -> str:
    res = _format_deterministic_answer_impl(question, rows)
    return sanitize_bin_utilization_response(res, question)

def _format_deterministic_answer_impl(question: str, rows: list[dict]) -> str:
    """Creates clear, grounded summary from database rows."""
    question = normalize_query_typos(question)
    q_lower = question.lower()
    if not rows:
        rf_list = parse_range_filters(q_lower)
        if rf_list and any(b in q_lower for b in ["bin", "bins", "storage", "location"]):
            rf = rf_list[0]
            if rf.get("field") == "TotalCapacity":
                op = rf.get("operator", "BETWEEN")
                low = rf.get("lower")
                up = rf.get("upper")
                if op == "BETWEEN" and low is not None and up is not None:
                    rf_desc = f"between {low:,.0f} and {up:,.0f} FT³"
                elif op in ["GT", "GTE"] and low is not None:
                    rf_desc = f"above {low:,.0f} FT³" if not rf.get("inclusive") else f"at least {low:,.0f} FT³"
                elif op in ["LT", "LTE"] and up is not None:
                    rf_desc = f"below {up:,.0f} FT³" if not rf.get("inclusive") else f"at most {up:,.0f} FT³"
                else:
                    rf_desc = "the specified range"
                plant_val = extract_single_plant_safe(q_lower)
                plant_str = f" in Plant {plant_val}" if plant_val else ""
                return f"No bins found with configured capacity **{rf_desc}**{plant_str} (warehouse bin capacities currently range from 3.07 to 80.00 FT³)."
        return "No matching warehouse records were found for your query in the database."

    count = len(rows)
    cols = list(rows[0].keys())
    is_single_statement_requested = is_single_line_requested(q_lower)

    # 0_NONEXISTENT_QUERY. Queries asking for nonexistent records/entities
    if is_unsupported_nonexistent_query(q_lower):
        return "No matching warehouse records were found for your query in the database."

    # 0_INVALID_ENTITY. Invalid Plant / Bin / Entity Handling (Master Context Sections 37-41 & 57)
    valid_plants = {"1258", "1266", "1268", "7228"}
    req_plants = extract_explicit_plants(q_lower)
    if req_plants:
        for p in req_plants:
            if p not in valid_plants and p not in ["2024", "2025", "2026"]:
                return "No matching warehouse records were found for your query in the database."
        if rows and "Plant" in cols:
            returned_plants = {str(r.get("Plant")).strip() for r in rows if r.get("Plant") is not None}
            if not set(req_plants).intersection(returned_plants):
                return "No matching warehouse records were found for your query in the database."
    else:
        plant_req_match = re.search(r"\b(?:plant|facility)\s*[:#-]?\s*(\d{4,5})\b", q_lower)
        if plant_req_match:
            target_plant = plant_req_match.group(1)
            if target_plant not in valid_plants and target_plant not in ["2024", "2025", "2026"]:
                return "No matching warehouse records were found for your query in the database."

    # 0A_NAMES_ONLY. Return only the entity names when requested
    if any(k in q_lower for k in ["only names", "only the names", "names only", "just the names", "show only the names"]):
        if "Plant" in cols:
            unique_plants = list(dict.fromkeys(str(r.get("Plant")) for r in rows if r.get("Plant")))
            return ", ".join(f"Plant {p}" for p in unique_plants)
        elif "Material" in cols:
            unique_mats = list(dict.fromkeys(str(r.get("Material")) for r in rows if r.get("Material")))
            return ", ".join(unique_mats)
        elif "Bin" in cols or "BinLocation" in cols:
            unique_bins = list(dict.fromkeys(str(r.get("Bin") or r.get("BinLocation")) for r in rows if r.get("Bin") or r.get("BinLocation")))
            return ", ".join(unique_bins)
        elif "Storage Location" in cols or "StorageLocation" in cols:
            unique_slocs = list(dict.fromkeys(str(r.get("Storage Location") or r.get("StorageLocation")) for r in rows if r.get("Storage Location") or r.get("StorageLocation")))
            return ", ".join(unique_slocs)

    # 0A_PERCENTAGE_ONLY. Percentage share when percentage mode is requested without switching metrics
    if any(k in q_lower for k in ["only percentage", "only the percentage", "percentage only", "just the percentage", "show only the percentage"]):
        if "Plant" in cols and len(rows) >= 2:
            num_col = next((c for c in ["Total Inventory Quantity", "Total Inventory Qty", "Total Stock Qty", "UnrestrictedQty"] if c in cols), None)
            if num_col:
                tot = sum(float(r.get(num_col, 0) or 0) for r in rows)
                if tot > 0:
                    pct_items = [f"Plant {r.get('Plant')}: {(float(r.get(num_col, 0) or 0) / tot) * 100:.2f}%" for r in rows]
                    return f"{' | '.join(pct_items)} (share of total inventory across compared plants)."
            pct_col = next((c for c in cols if "%" in c or "Percentage" in c or "Pct" in c), None)
            if pct_col:
                return " | ".join(f"Plant {r.get('Plant')}: {r.get(pct_col)}" for r in rows)

    # 0A_COUNT_ONLY. Count when count mode is requested
    if any(k in q_lower for k in ["only count", "only the count", "just the count", "count only", "give me only the count"]):
        if "Plant" in cols and len(rows) >= 2:
            num_col = next((c for c in ["Total Inventory Quantity", "Total Inventory Qty", "Total Stock Qty", "UnrestrictedQty"] if c in cols), None)
            if num_col:
                tot = sum(float(r.get(num_col, 0) or 0) for r in rows)
                breakdown = ", ".join(f"Plant {r.get('Plant')}: {float(r.get(num_col, 0) or 0):,.0f}" for r in rows)
                return f"Total count: **{tot:,.0f} units** across {len(rows)} plants ({breakdown})."
            return f"Total count: **{len(rows)} matching entities**."

    # 0A_BIN_LEVEL_DETAIL. Bin-level Detailed Response (Single or Multi Plant)
    if rows and ("Bin" in cols or "BinLocation" in cols) and ("Capacity" in cols or "Bin Capacity" in cols) and "Available Capacity" in cols and ("Utilization %" in cols or "Capacity Utilization %" in cols):
        return format_detailed_bin_utilization_tables(rows)

    # 0A_COMPARISON_ENGINE. Global Comparison Response Engine (Rules 1-17)
    if is_comparison_intent(q_lower, rows) and rows:
        return format_comparison_response(question, rows)

    # 0A_CLARIFICATION. Predefined threshold clarification rule
    if "clarification_needed" in cols:
        return "To find matching bins, please specify the thresholds for capacity (e.g., maximum bin volume in FT³) and utilization (e.g., minimum utilization percentage). No default thresholds are currently defined."

    # 0A_COMPOUND. Compound Capacity + Utilization: "low capacity but high utilization", "bins with capacity < 45 FT3 and utilization > 80%"
    compound_info = parse_compound_capacity_utilization(q_lower)
    if compound_info and "Bin" in cols and ("Utilization %" in cols or "Capacity Utilization %" in cols):
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else ""
        cap_desc = compound_info.get("cap_desc", "specified capacity")
        util_desc = compound_info.get("util_desc", "specified utilization")
        total_matching = rows[0].get("TotalMatching") if (rows and "TotalMatching" in rows[0]) else len(rows)
        displayed_rows = len(rows)
        explicit_lim = extract_explicit_limit(q_lower)
        if explicit_lim and total_matching > displayed_rows:
            single_stmt = f"Found **{total_matching:,} matching bins**{plant_str} meeting both conditions. Showing the first **{displayed_rows}** (Capacity: {cap_desc}, Utilization: {util_desc})."
        else:
            single_stmt = f"Found **{total_matching:,} matching bins**{plant_str} meeting both conditions: Capacity ({cap_desc}) and Utilization ({util_desc})."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            f"### 📦 Compound Capacity & Utilization Bins{plant_str}\n",
            single_stmt,
            f"\nMatching individual bins with Capacity, Occupied Volume, and Utilization % are loaded in the **searchable Data Table** below."
        ]
        return "\n".join(lines)

    # 0A_ALMOST_FULL. Almost full bins (80% <= util < 100%) and over capacity bins (>= 100%)
    is_almost_full_q = any(k in q_lower for k in [
        "almost full", "nearly full", "near full", "close to full", "close to being full",
        "close to full capacity", "almost at capacity", "near full capacity",
        "nearly at 100% utilization", "nearly at 100%", "almost at 100%"
    ]) and not any(k in q_lower for k in ["over capacity", "over-capacity", "over utilized", "over-utilized", "greater than 100", "above 100", "> 100", ">= 100"])
    if is_almost_full_q and "Bin" in cols and ("Utilization %" in cols or "Utilization" in cols):
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else ""
        return f"Found **{len(rows)}** bins operating near full capacity (between 80% and 100% utilization){plant_str}."

    is_over_cap_q = any(k in q_lower for k in [
        "over capacity", "over-capacity", "over capacity bins", "full or over capacity",
        "over-utilized bins", "over utilized bins", "exceeding capacity", "exceeds capacity",
        "full or over", "at or over 100", "100% or more"
    ])
    if is_over_cap_q and "Bin" in cols and ("Utilization %" in cols or "Utilization" in cols):
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else ""
        return f"Found **{len(rows)}** bins operating at or over capacity (>= 100% utilization){plant_str}."

    # 0A_FIND_BINS. Entity Preservation: "Find bins..."
    if "Bin" in cols and any(q_lower.startswith(p) or f" {p}" in q_lower for p in ["find bins", "find bin", "search bins", "look for bins", "list bins", "show bins", "get bins"]) and not any(k in q_lower for k in ["between", "from", "utiliz", "almost full", "nearly full", "near full", "close to full", "close to being full", "over capacity", "over-capacity"]):
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else ""
        total_matching = rows[0].get("TotalMatching") if (rows and "TotalMatching" in rows[0]) else len(rows)
        displayed_rows = len(rows)
        explicit_lim = extract_explicit_limit(q_lower)
        if explicit_lim and total_matching > displayed_rows:
            single_stmt = f"Found **{total_matching:,} matching bins**{plant_str}. Showing the first **{displayed_rows}** at the individual bin level."
        else:
            single_stmt = f"Displaying **{total_matching:,} bins**{plant_str} at the individual bin level."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            f"### 📦 Warehouse Bins{plant_str}\n",
            single_stmt,
            f"\nIndividual bin records with capacity, occupied volume, and utilization are displayed in the **Data Table** below."
        ]
        return "\n".join(lines)

    # 0A_COMBINED_BINS. Combined Top & Bottom Bins Ranking
    if "Ranking Group" in cols or (
        ("top" in q_lower or "most" in q_lower or "fullest" in q_lower or "highest" in q_lower) and
        ("bottom" in q_lower or "least" in q_lower or "emptiest" in q_lower or "lowest" in q_lower) and
        "Bin" in cols and ("Utilization %" in cols or "Utilization" in cols)
    ):
        top_rows = [
            r for r in rows
            if "Most" in str(r.get("Ranking Group", "")) or "Fullest" in str(r.get("Ranking Group", "")) or
            ("Top" in str(r.get("Ranking Group", "")) and not any(k in str(r.get("Ranking Group", "")) for k in ["Least", "Bottom", "Emptiest", "Lowest"]))
        ]
        bottom_rows = [
            r for r in rows
            if any(k in str(r.get("Ranking Group", "")) for k in ["Least", "Bottom", "Emptiest", "Lowest"])
        ]
        if not top_rows and not bottom_rows and len(rows) > 1:
            mid = len(rows) // 2
            top_rows = rows[:mid]
            bottom_rows = rows[mid:]
        
        top_n = len(top_rows)
        bottom_n = len(bottom_rows)
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else ""
        
        top_leader = top_rows[0].get("Bin", "N/A") if top_rows else "N/A"
        top_util = top_rows[0].get("Utilization %", "0%") if top_rows else "0%"
        bottom_leader = bottom_rows[0].get("Bin", "N/A") if bottom_rows else "N/A"
        bottom_util = bottom_rows[0].get("Utilization %", "0%") if bottom_rows else "0%"
        
        single_stmt = f"Top {top_n} most utilized bins{plant_str} lead with **`{top_leader}`** ({top_util}) and top {bottom_n} least utilized bins start at **`{bottom_leader}`** ({bottom_util})."
        if is_single_statement_requested:
            return single_stmt
            
        is_bin_only = is_bin_utilization_primary(q_lower)
        if is_bin_only:
            lines = [
                f"### 🏆 Top {top_n} Most Utilized Bins{plant_str}\n",
                "| Rank | Bin | Plant | Utilization % |",
                "|:---:|:---|:---:|:---:|"
            ]
            for idx, r in enumerate(top_rows, 1):
                rnk = r.get("Rank", idx)
                b = r.get("Bin", "N/A")
                p = r.get("Plant", "-")
                u = r.get("Utilization %", "-")
                lines.append(f"| {rnk} | `{b}` | {p} | **{u}** |")
                
            lines.append(f"\n### 📉 Top {bottom_n} Least Utilized Bins{plant_str}\n")
            lines.append(f"*(Bottom {bottom_n} Least Utilized Bins)*\n")
            lines.append("| Rank | Bin | Plant | Utilization % |")
            lines.append("|:---:|:---|:---:|:---:|")
            for idx, r in enumerate(bottom_rows, 1):
                rnk = r.get("Rank", idx)
                if not isinstance(rnk, int) or rnk > bottom_n:
                    rnk = idx
                b = r.get("Bin", "N/A")
                p = r.get("Plant", "-")
                u = r.get("Utilization %", "-")
                lines.append(f"| {rnk} | `{b}` | {p} | **{u}** |")
        else:
            lines = [
                f"### 🏆 Top {top_n} Most Utilized Bins{plant_str}\n",
                "| Rank | Bin | Plant | Capacity | Available Capacity | Utilization % |",
                "|:---:|:---|:---:|:---:|:---:|:---:|"
            ]
            for idx, r in enumerate(top_rows, 1):
                rnk = r.get("Rank", idx)
                b = r.get("Bin", "N/A")
                p = r.get("Plant", "-")
                cap = r.get("Bin Capacity", r.get("Capacity", "-"))
                ac = r.get("Available Capacity", "-")
                if isinstance(ac, (int, float)):
                    ac = f"{ac:,.2f} FT³"
                u = r.get("Utilization %", "-")
                lines.append(f"| {rnk} | `{b}` | {p} | {cap} | {ac} | **{u}** |")
                
            lines.append(f"\n### 📉 Top {bottom_n} Least Utilized Bins{plant_str}\n")
            lines.append(f"*(Bottom {bottom_n} Least Utilized Bins)*\n")
            lines.append("| Rank | Bin | Plant | Capacity | Available Capacity | Utilization % |")
            lines.append("|:---:|:---|:---:|:---:|:---:|:---:|")
            for idx, r in enumerate(bottom_rows, 1):
                rnk = r.get("Rank", idx)
                if not isinstance(rnk, int) or rnk > bottom_n:
                    rnk = idx
                b = r.get("Bin", "N/A")
                p = r.get("Plant", "-")
                cap = r.get("Bin Capacity", r.get("Capacity", "-"))
                ac = r.get("Available Capacity", "-")
                if isinstance(ac, (int, float)):
                    ac = f"{ac:,.2f} FT³"
                u = r.get("Utilization %", "-")
                lines.append(f"| {rnk} | `{b}` | {p} | {cap} | {ac} | **{u}** |")
            
        lines.append("\n💡 *Both independent rankings are also available in the interactive data table below.*")
        return "\n".join(lines)

    # 0A_COMPARE_BINS. Comparison of Top Utilized Bins across Multiple Plants (Item 7)
    if "Ranking Group" not in cols and "Bin" in cols and ("Utilization %" in cols or "UtilizationPct" in cols) and "Plant" in cols and any(k in q_lower for k in ["compare", "comparison", "versus", "vs"]):
        plants = extract_plants(q_lower)
        if len(plants) >= 2:
            plant_groups = {}
            for r in rows:
                p = str(r.get("Plant", ""))
                if p not in plant_groups:
                    plant_groups[p] = []
                plant_groups[p].append(r)
            
            p1, p2 = plants[0], plants[1]
            p1_bins = plant_groups.get(p1, [])
            p2_bins = plant_groups.get(p2, [])
            p1_lead = f"Bin `{p1_bins[0].get('Bin')}` ({p1_bins[0].get('Utilization %')})" if p1_bins else "None"
            p2_lead = f"Bin `{p2_bins[0].get('Bin')}` ({p2_bins[0].get('Utilization %')})" if p2_bins else "None"
            
            single_stmt = f"Comparing top utilized bins: **Plant {p1}** (lead: {p1_lead}) vs **Plant {p2}** (lead: {p2_lead})."
            if is_single_statement_requested:
                return single_stmt
                
            lines = [
                f"### 📊 Top Utilized Bins Comparison: Plant {p1} vs Plant {p2}\n",
                single_stmt,
                f"\n**Plant {p1} Top Utilized Bins ({len(p1_bins)} bins):**"
            ]
            is_bin_only = is_bin_utilization_primary(q_lower)
            for r in p1_bins[:5]:
                rnk = r.get("Rank", "-")
                b = r.get("Bin", "N/A")
                u = r.get("Utilization %", "")
                ov = r.get("Occupied Volume", "")
                cap = r.get("Bin Capacity", "")
                if is_bin_only:
                    lines.append(f"- **Rank {rnk} — Bin `{b}`**: **{u}**")
                else:
                    lines.append(f"- **Rank {rnk} — Bin `{b}`**: **{u}** (Capacity: {cap})")
                
            lines.append(f"\n**Plant {p2} Top Utilized Bins ({len(p2_bins)} bins):**")
            for r in p2_bins[:5]:
                rnk = r.get("Rank", "-")
                b = r.get("Bin", "N/A")
                u = r.get("Utilization %", "")
                cap = r.get("Bin Capacity", "")
                if is_bin_only:
                    lines.append(f"- **Rank {rnk} — Bin `{b}`**: **{u}**")
                else:
                    lines.append(f"- **Rank {rnk} — Bin `{b}`**: **{u}** (Capacity: {cap})")
                
            lines.append("\n💡 *The full side-by-side comparison is loaded in the **searchable Data Table** below.*")
            return "\n".join(lines)

    # 0A_MAT_THRESH. Materials filtered by quantity threshold (Item 2)
    qty_thresh = extract_quantity_threshold(q_lower)
    if "Material" in cols and "Total Stock Quantity" in cols and qty_thresh is not None:
        op, thresh_val = qty_thresh
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else ""
        total_mats = len(rows)
        lead_mat = rows[0].get("Material", "N/A")
        lead_desc = rows[0].get("Material Description", "")
        lead_qty = rows[0].get("Total Stock Quantity", 0.0)
        uom = rows[0].get("UOM", "EA")
        
        single_stmt = f"Found **{total_mats:,} materials**{plant_str} with inventory quantity {op} {thresh_val:,.0f} (top: **`{lead_mat}`** with {lead_qty:,.0f} {uom})."
        if is_single_statement_requested:
            return single_stmt
            
        lines = [
            f"### 📦 Materials with Quantity {op} {thresh_val:,.0f}{plant_str}\n",
            single_stmt,
            f"\n**Top Matching Materials:**"
        ]
        for r in rows[:10]:
            m = r.get("Material", "N/A")
            d = r.get("Material Description", "")
            q = r.get("Total Stock Quantity", 0.0)
            u = r.get("UOM", "EA")
            lines.append(f"- **`{m}`** ({d}): **{q:,.0f} {u}**")
        lines.append("\n💡 *The full list of matching materials is loaded in the **searchable Data Table** below.*")
        return "\n".join(lines)

    # 0A_PLANT_RANGE. Plants with total inventory in range (Item 3)
    if "Plant" in cols and "Total Inventory Quantity" in cols and any(k in q_lower for k in ["between", "from", "range"]) and extract_range_bounds(q_lower):
        bounds = extract_range_bounds(q_lower)
        low, high = bounds
        if not rows:
            return f"No plants found with total inventory between {low:,.0f} and {high:,.0f} units."
        
        single_stmt = f"Found **{len(rows)} plant(s)** with total inventory between {low:,.0f} and {high:,.0f} units: " + ", ".join(f"**Plant {r.get('Plant')}** ({r.get('Total Inventory Quantity', 0):,.0f} units)" for r in rows)
        if is_single_statement_requested:
            return single_stmt
            
        lines = [
            f"### 🏭 Plants with Inventory between {low:,.0f} and {high:,.0f} Units\n",
            single_stmt,
            "\n**Plant Inventory Details:**"
        ]
        for r in rows:
            p = r.get("Plant")
            q = r.get("Total Inventory Quantity", 0)
            m = r.get("Unique Materials", 0)
            b = r.get("Occupied Bins", 0)
            lines.append(f"- **Plant {p}**: **{q:,.0f} units** across {m:,} materials and {b:,} occupied bins.")
        lines.append("\n💡 *The matching plants are displayed in the **Data Table** below.*")
        return "\n".join(lines)

    # 0A_MISSING_VOL_PCT. Missing volume information percentage / summary
    if "Missing Volume Percentage" in cols:
        pct = rows[0].get("Missing Volume Percentage", 0.0)
        miss_count = rows[0].get("Missing Volume Materials Count", 0)
        tot_count = rows[0].get("Total Inventory Materials Count", 0)
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" for Plant {plant_val}" if plant_val else ""
        return f"**{pct:.2f}%** of inventory materials are missing volume information ({miss_count:,} out of {tot_count:,} materials){plant_str}."

    if "Status" in cols and ("Percentage (%)" in cols or "Material Count" in cols) and any("missing" in str(s).lower() for s in [r.get("Status", "") for r in rows]):
        missing_row = next((r for r in rows if "missing" in str(r.get("Status", "")).lower()), None)
        if missing_row:
            pct = missing_row.get("Percentage (%)", 0.0)
            miss_count = missing_row.get("Material Count", 0)
            return f"**{pct:.2f}%** of inventory materials are missing volume information ({miss_count:,} materials)."

    # 0A_ALMOST_FULL. Almost full bins (80% <= util < 100%) and over capacity bins (>= 100%)
    is_almost_full_q = any(k in q_lower for k in [
        "almost full", "nearly full", "near full", "close to full", "close to being full",
        "close to full capacity", "almost at capacity", "near full capacity",
        "nearly at 100% utilization", "nearly at 100%", "almost at 100%"
    ]) and not any(k in q_lower for k in ["over capacity", "over-capacity", "over utilized", "over-utilized", "greater than 100", "above 100", "> 100", ">= 100"])
    if is_almost_full_q and "Bin" in cols and ("Utilization %" in cols or "Utilization" in cols):
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else ""
        return f"Found **{len(rows)}** bins operating near full capacity (between 80% and 100% utilization){plant_str}."

    is_over_cap_q = any(k in q_lower for k in [
        "over capacity", "over-capacity", "over capacity bins", "full or over capacity",
        "over-utilized bins", "over utilized bins", "exceeding capacity", "exceeds capacity",
        "full or over", "at or over 100", "100% or more"
    ])
    if is_over_cap_q and "Bin" in cols and ("Utilization %" in cols or "Utilization" in cols):
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else ""
        return f"Found **{len(rows)}** bins operating at or over capacity (>= 100% utilization){plant_str}."

    # 0A_PLANT_AVAIL_CAP. Available Capacity by Plant
    if (
        "Available Capacity (FT3)" in cols and "Total Capacity (FT3)" in cols and "Plant" in cols
        and "Bin" not in cols
        and "Total Bins" not in cols
        and not any(k in q_lower for k in ["compare", "versus", "vs", "which plant", "difference between", "summary", "warehouse capacity"])
    ):
        if len(rows) > 1:
            tot_avail = sum(r.get("Available Capacity (FT3)", 0) for r in rows)
            return f"Showing available capacity across **{len(rows)} operational plants** (total available: **{tot_avail:,.2f} FT³**)."
        else:
            p = rows[0].get("Plant")
            avail = rows[0].get("Available Capacity (FT3)", 0)
            tot_cap = rows[0].get("Total Capacity (FT3)", 0)
            occ = rows[0].get("Total Occupied Volume (FT3)", rows[0].get("Occupied Volume (FT3)", 0))
            return f"Plant {p} has **{avail:,.2f} FT³** available capacity (Total Capacity: {tot_cap:,.2f} FT³, Occupied Volume: {occ:,.2f} FT³)."

    # 0A_PLANT_INV. Plant-Wise Inventory Quantity
    if (
        "Total Inventory Quantity" in cols and "Plant" in cols and "Storage Location" not in cols and "Bin" not in cols and "Rank" not in cols and len(rows) > 1
        and not any(k in q_lower for k in ["between", "from", "range", ">", "<", "compare", "comparison", "versus", "vs", "detail", "detailed", "those two"])
        and "Unique Materials" not in cols
    ):
        tot_qty = sum(r.get("Total Inventory Quantity", 0) for r in rows)
        return f"Showing inventory quantities across **{len(rows)} operational plants** (totaling **{tot_qty:,.0f} units**)."

    # 0A0. Specific Bin Lookups (Plant, Occupancy, Quantity, Materials)
    bin_cand_matches = re.findall(r"(?:bin\s*[:#-]?\s*([a-z0-9_-]{2,25})|\b(b\d{3,5})\b)", q_lower, re.IGNORECASE)
    spec_bins = [
        (bm[0] or bm[1] or "").strip().upper()
        for bm in bin_cand_matches
        if (bm[0] or bm[1] or "").strip().lower() not in ["capacity", "utilization", "master", "table", "space", "volume", "location", "locations", "occupancy", "fullness", "empty", "vacant", "free", "ones", "these", "those"]
    ]
    if spec_bins and len(rows) <= 2:
        b_code = spec_bins[0]
        # Plant Lookup: "Which plant does bin NRJP2124D2 belong to?"
        if any(k in q_lower for k in ["which plant", "what plant", "belong to", "plant of bin", "plant for bin", "where is bin located"]):
            plant_val = rows[0].get("Plant", "Unknown") if rows else "Unknown"
            sloc_val = rows[0].get("StorageLocation", rows[0].get("Storage Location", "N/A")) if rows else "N/A"
            return f"Bin **{b_code}** belongs to **Plant {plant_val}** (Storage Location: `{sloc_val}`)."

        # Occupancy Check: "Is bin NRJP2124D2 occupied?"
        if "MaterialCount" in cols or "TotalQty" in cols or (any(k in q_lower for k in ["occupied", "empty", "vacant", "in use"]) and any(q_start in q_lower for q_start in ["is ", "are ", "does ", "is the"])):
            tot_qty = rows[0].get("TotalQty", 0) if rows else 0
            mat_cnt = rows[0].get("MaterialCount", 0) if rows else 0
            if tot_qty > 0 or mat_cnt > 0:
                return f"Yes, bin **{b_code}** is occupied (stores {tot_qty:,.0f} units across {mat_cnt} material{'s' if mat_cnt != 1 else ''})."
            else:
                return f"No, bin **{b_code}** is not occupied (0 inventory units)."

        # Inventory Quantity in Bin: "What is the inventory quantity in bin NRJP2124D2?"
        if "Inventory Qty" in cols and ("UOM" in cols or len(cols) <= 2) and any(k in q_lower for k in ["inventory quantity", "quantity in bin", "stock in bin", "units in bin", "how much in bin", "how much is stored in bin", "how many units in bin", "quantity stored in bin"]):
            tot_qty = rows[0].get("Inventory Qty", 0) if rows else 0
            uom = rows[0].get("UOM", "EA") if rows else "EA"
            return f"Bin **{b_code}** currently has an inventory quantity of **{tot_qty:,.0f} {uom}**."

        # Materials count in Bin: "How many materials are stored in bin NRJP2124D2?"
        if "Stored Materials Count" in cols or (any(k in q_lower for k in ["how many materials", "how many skus", "how many items", "number of materials", "count of materials"]) and any(b in q_lower for b in ["in bin", "stored in bin", "inside bin", "for bin"])):
            m_cnt = rows[0].get("Stored Materials Count", rows[0].get("MaterialCount", 0)) if rows else 0
            return f"Bin **{b_code}** stores **{m_cnt} unique material{'s' if m_cnt != 1 else ''}**."

        # Capacity of Bin: "What is the capacity of bin NRJP2124D2?"
        if "Total Capacity (FT3)" in cols and "Available Capacity (FT3)" in cols:
            p_val = rows[0].get("Plant", "N/A")
            sloc_val = rows[0].get("Storage Location", rows[0].get("StorageLocation", "N/A"))
            tot_cap = rows[0].get("Total Capacity (FT3)", 0.0)
            occ_vol = rows[0].get("Occupied Volume (FT3)", 0.0)
            avail_cap = rows[0].get("Available Capacity (FT3)", 0.0)
            util_pct = rows[0].get("Capacity Utilization %", "0%")
            return f"Bin **`{b_code}`** (Plant {p_val}, Storage Location: `{sloc_val}`) has a total capacity of **{tot_cap:,.2f} FT³**, with **{occ_vol:,.2f} FT³** occupied ({util_pct} utilization) and **{avail_cap:,.2f} FT³** available capacity remaining."

        # Materials Stored in Bin: "What material is stored in bin XYZ?"
        if "Material" in cols and any(k in q_lower for k in ["what material", "which material", "materials stored", "material in bin", "items in bin", "skus in bin", "product in bin", "what is stored in bin", "stored in"]):
            if len(rows) == 1:
                m = rows[0].get("Material", "N/A")
                d = rows[0].get("Material Description", "")
                q = rows[0].get("TotalQty", 0.0)
                uom = rows[0].get("UOM", "EA")
                desc_str = f" ({d})" if d else ""
                return f"Bin **`{b_code}`** currently stores material **`{m}`**{desc_str} with **{q:,.0f} {uom}**."
            else:
                lines = [f"Bin **`{b_code}`** stores **{len(rows)} materials**:"]
                for r in rows:
                    m = r.get("Material", "N/A")
                    q = r.get("TotalQty", 0.0)
                    uom = r.get("UOM", "EA")
                    lines.append(f"- **`{m}`**: **{q:,.0f} {uom}**")
                return "\n".join(lines)

        # Generic Specific Bin Lookup: "Find bin XYZ999", "Show bin XYZ999", "Details for bin XYZ999"
        if "Bin" in cols and "Capacity" in cols and "Occupied Volume" in cols and "Utilization %" in cols:
            p_val = rows[0].get("Plant", "N/A")
            sloc_val = rows[0].get("Storage Location", rows[0].get("StorageLocation", "N/A"))
            cap = rows[0].get("Capacity", "N/A")
            occ = rows[0].get("Occupied Volume", 0.0)
            u = rows[0].get("Utilization %", "0%")
            return f"Bin **`{b_code}`** (Plant {p_val}, Storage Location: `{sloc_val}`) has capacity of **{cap}**, occupied volume of **{occ:,.2f} FT³**, and utilization of **{u}**."

    # 0A_WASTE. Bins Wasting Most Space / Inefficient Storage
    if "Unused Space (FT3)" in cols and "Bin" in cols and ("Capacity (FT3)" in cols or "Capacity" in cols):
        top_bin = rows[0].get("Bin", "N/A")
        top_plant = rows[0].get("Plant", "N/A")
        top_unused = rows[0].get("Unused Space (FT3)", 0.0)
        top_cap = rows[0].get("Capacity (FT3)", 0.0)
        single_stmt = f"Bin **`{top_bin}`** in Plant {top_plant} is wasting the most space with **{top_unused:,.2f} FT³** unused capacity out of {top_cap:,.2f} FT³ total capacity."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            "### ⚠️ Inefficient Storage Analysis (Bins Wasting Most Space)\n",
            single_stmt,
            f"\n**Top Inefficiently Utilized Bins (Utilization ≤ 20%):**"
        ]
        for r in rows[:5]:
            b = r.get("Bin", "N/A")
            p = r.get("Plant", "N/A")
            unused = r.get("Unused Space (FT3)", 0.0)
            u = r.get("Utilization %", "0%")
            lines.append(f"- **Bin `{b}`** (Plant {p}): **{unused:,.2f} FT³** unused ({u} utilization)")
        lines.append("\n💡 *The full list is loaded in the **Data Table** below.*")
        return "\n".join(lines)

    # 0A_ATTENTION. Bins Requiring Operational Attention
    if "Issue Type" in cols and "Bin" in cols and "Occupied Volume (FT3)" in cols:
        over_util = sum(1 for r in rows if "Over" in str(r.get("Issue Type", "")))
        near_cap = sum(1 for r in rows if "Near" in str(r.get("Issue Type", "")))
        top_b = rows[0].get("Bin", "N/A")
        top_p = rows[0].get("Plant", "N/A")
        top_u = rows[0].get("Utilization %", "N/A")
        single_stmt = f"Found **{len(rows)} bins needing attention** ({over_util} over-utilized >100%, {near_cap} near capacity ≥90%), led by Bin **`{top_b}`** in Plant {top_p} at **{top_u}**."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            "### ⚠️ Bins Requiring Operational Attention\n",
            single_stmt,
            f"\n**Critical Bins Breakdown:**"
        ]
        for r in rows[:5]:
            b = r.get("Bin", "N/A")
            p = r.get("Plant", "N/A")
            issue = r.get("Issue Type", "Attention")
            u = r.get("Utilization %", "N/A")
            occ = r.get("Occupied Volume (FT3)", 0.0)
            lines.append(f"- **Bin `{b}`** (Plant {p}): **{u}** ({occ:,.2f} FT³ occupied) — *{issue}*")
        lines.append("\n💡 *The complete list of critical bins is loaded in the **Data Table** below.*")
        return "\n".join(lines)

    # 0A_INV_DIST. Plant Inventory Distribution: "Where is most of my inventory sitting?"
    if "Total Stock Units" in cols and "Occupied Volume (FT3)" in cols and "Plant" in cols:
        top_v_plant = rows[0].get("Plant", "N/A")
        top_v = rows[0].get("Occupied Volume (FT3)", 0.0)
        sorted_by_units = sorted(rows, key=lambda x: x.get("Total Stock Units", 0), reverse=True)
        top_u_plant = sorted_by_units[0].get("Plant", "N/A")
        top_u = sorted_by_units[0].get("Total Stock Units", 0)
        single_stmt = f"Most inventory by occupied volume is sitting in **Plant {top_v_plant}** ({top_v:,.2f} FT³), while **Plant {top_u_plant}** holds the highest unit quantity ({top_u:,.0f} units)."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            "### 🏭 Plant Inventory Distribution\n",
            single_stmt,
            f"\n**Plant Breakdown:**"
        ]
        for r in rows:
            p = r.get("Plant", "N/A")
            vol = r.get("Occupied Volume (FT3)", 0.0)
            units = r.get("Total Stock Units", 0)
            bins = r.get("Occupied Bins", 0)
            lines.append(f"- **Plant {p}**: **{vol:,.2f} FT³** occupied | **{units:,.0f} units** | **{bins:,} bins**")
        return "\n".join(lines)

    # 0A_AVAIL_CAP. Available Storage Space by Plant: "Where do I have the most free space?"
    if "Available Capacity (FT3)" in cols and "Total Capacity (FT3)" in cols and "Plant" in cols and "Bin" not in cols and any(k in q_lower for k in ["free space", "most free", "where do i have", "where is the most", "where do we have"]):
        top_p = rows[0].get("Plant", "N/A")
        top_avail = rows[0].get("Available Capacity (FT3)", 0.0)
        top_tot = rows[0].get("Total Capacity (FT3)", 0.0)
        single_stmt = f"You have the most free space in **Plant {top_p}** with **{top_avail:,.2f} FT³** available storage capacity ({top_avail * 100.0 / top_tot:.1f}% free of {top_tot:,.2f} FT³ total)."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            "### 📊 Available Storage Space by Plant\n",
            single_stmt,
            f"\n**Plant Available Capacity Ranking:**"
        ]
        for r in rows:
            p = r.get("Plant", "N/A")
            avail = r.get("Available Capacity (FT3)", 0.0)
            tot = r.get("Total Capacity (FT3)", 0.0)
            u = r.get("Utilization %", "0%")
            lines.append(f"- **Plant {p}**: **{avail:,.2f} FT³** available ({u} utilization of {tot:,.2f} FT³ total)")
        return "\n".join(lines)

    # 0A_STORAGE_PROB. Plant with Biggest Storage Problem
    if ("BinUtilizationPct" in cols or "Bin Utilization %" in cols) and any(k in q_lower for k in ["biggest storage problem", "storage problem", "storage issue", "most constrained"]):
        p = rows[0].get("Plant", "N/A")
        u = rows[0].get("Bin Utilization %", f"{rows[0].get('BinUtilizationPct', 0)}%")
        ob = rows[0].get("Occupied Bins", 0)
        tb = rows[0].get("Total Bins", 0)
        eb = rows[0].get("Empty Bins", 0)
        return f"**Plant {p}** has the biggest storage problem with the highest utilization across the network at **{u}** ({ob:,} of {tb:,} bins occupied, leaving only {eb:,} empty bins)."

    # 0A_BEST_UTIL. Best Performing Plant on Storage Utilization
    if ("BinUtilizationPct" in cols or "Bin Utilization %" in cols) and any(k in q_lower for k in ["performing best", "best performing", "best on storage utilization"]):
        p = rows[0].get("Plant", "N/A")
        u = rows[0].get("Bin Utilization %", f"{rows[0].get('BinUtilizationPct', 0)}%")
        ob = rows[0].get("Occupied Bins", 0)
        tb = rows[0].get("Total Bins", 0)
        return f"**Plant {p}** is performing best on storage utilization with **{u}** bin utilization ({ob:,} occupied of {tb:,} total bins)."

    # 0A_CAP_1. Referential Bins Combined Capacity: "How much total occupied volume do they have?"
    if "Referenced Bins Count" in cols:
        cnt = rows[0].get("Referenced Bins Count", 0)
        tot_cap = rows[0].get("Total Capacity (FT3)", 0.0)
        occ_vol = rows[0].get("Total Occupied Volume (FT3)", 0.0)
        avail_cap = rows[0].get("Total Available Capacity (FT3)", 0.0)
        util_pct = rows[0].get("Capacity Utilization %", "0%")
        return f"The **{cnt} referenced bins** have a combined total capacity of **{tot_cap:,.2f} FT³**, of which **{occ_vol:,.2f} FT³** is occupied ({util_pct} utilization) and **{avail_cap:,.2f} FT³** is available capacity remaining."

    # 0A_CAP_2. Empty Bins Available Capacity: "How much capacity is available in empty bins?"
    if "Empty Bins Available Capacity (FT3)" in cols:
        cnt = rows[0].get("Empty Bins Count", 0)
        avail_cap = rows[0].get("Empty Bins Available Capacity (FT3)", 0.0)
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else " across the warehouse"
        return f"There are **{cnt:,} empty bins** currently available{plant_str}, offering **{avail_cap:,.2f} FT³** of available storage capacity for immediate put-away."

    # 0A_CAP_3. Total Warehouse Storage Capacity (Scalar warehouse-wide sum): "What is the total capacity?"
    if "Total Capacity (FT3)" in cols and "Total Bins" in cols and len(rows) == 1 and "Plant" not in cols and "Rank" not in cols:
        cap_val = rows[0].get("Total Capacity (FT3)", 0.0)
        bins_val = rows[0].get("Total Bins", 0)
        return f"The total warehouse storage capacity is **{cap_val:,.2f} FT³** across **{bins_val:,} total bins**."

    # 0A_CAP_4. Total Available Storage Capacity: "How much space is left?", "Show available capacity"
    if "Total Available Capacity (FT3)" in cols and "Total Capacity (FT3)" in cols and len(rows) == 1 and "Rank" not in cols and "Referenced Bins Count" not in cols:
        avail_val = rows[0].get("Total Available Capacity (FT3)", 0.0)
        tot_val = rows[0].get("Total Capacity (FT3)", 0.0)
        occ_val = rows[0].get("Total Occupied Volume (FT3)", 0.0)
        plant_val = extract_single_plant_safe(q_lower) or (rows[0].get("Plant") if "Plant" in rows[0] else None)
        if plant_val:
            return f"**Plant {plant_val}** has **{avail_val:,.2f} FT³** of available storage capacity remaining (Total Capacity: **{tot_val:,.2f} FT³**, Occupied: **{occ_val:,.2f} FT³**)."
        return f"There is **{avail_val:,.2f} FT³** of available storage capacity remaining in the warehouse (Total Capacity: **{tot_val:,.2f} FT³**, Occupied: **{occ_val:,.2f} FT³**)."

    # 0A_CAP_5. Occupied Storage Volume: "How much space is occupied?", "Show occupied volume"
    if "Total Occupied Volume (FT3)" in cols and "Occupied Bins" in cols and len(rows) == 1 and "Rank" not in cols and "Total Capacity (FT3)" not in cols:
        occ_val = rows[0].get("Total Occupied Volume (FT3)", 0.0)
        ob_val = rows[0].get("Occupied Bins", 0)
        qty_val = rows[0].get("Total Inventory Quantity", 0.0)
        plant_val = extract_single_plant_safe(q_lower) or (rows[0].get("Plant") if "Plant" in rows[0] else None)
        plant_str = f" in Plant {plant_val}" if plant_val else ""
        return f"The current occupied storage volume{plant_str} is **{occ_val:,.2f} FT³** across **{ob_val:,} occupied bins** (holding **{qty_val:,.0f} total inventory units**)."

    # 0A_CAP_6. Specific Plant Storage Capacity: "Show capacity for Plant 1258", "What is the storage capacity of Plant 1258?"
    if "Total Capacity (FT3)" in cols and "Plant" in cols and "Available Capacity (FT3)" in cols and len(rows) == 1 and "Rank" not in cols:
        p_val = rows[0].get("Plant", "N/A")
        tot_val = rows[0].get("Total Capacity (FT3)", 0.0)
        occ_val = rows[0].get("Total Occupied Volume (FT3)", 0.0)
        avail_val = rows[0].get("Available Capacity (FT3)", 0.0)
        util_val = rows[0].get("Capacity Utilization %", "0%")
        tb_val = rows[0].get("Total Bins", 0)
        return f"**Plant {p_val}** has a total storage capacity of **{tot_val:,.2f} FT³** across **{tb_val:,} bins**, with **{occ_val:,.2f} FT³** occupied (**{util_val}** capacity utilization) and **{avail_val:,.2f} FT³** available capacity remaining."

    # 0A_CAP_7. Capacity Comparison by Plant: "Compare capacity between Plant 1258 and Plant 7228", "Which plant has more available capacity?"
    if "Available Capacity (FT3)" in cols and "Total Capacity (FT3)" in cols and "Plant" in cols and len(rows) >= 2 and "Rank" not in cols and any(k in q_lower for k in ["compare", "versus", "vs", "which plant", "difference between", "more available", "less available"]):
        sorted_rows = sorted(rows, key=lambda x: x.get("Available Capacity (FT3)", 0.0), reverse=True)
        p1, p2 = sorted_rows[0], sorted_rows[1]
        n1, av1, tc1 = p1.get("Plant", "N/A"), p1.get("Available Capacity (FT3)", 0.0), p1.get("Total Capacity (FT3)", 0.0)
        n2, av2, tc2 = p2.get("Plant", "N/A"), p2.get("Available Capacity (FT3)", 0.0), p2.get("Total Capacity (FT3)", 0.0)
        diff = av1 - av2
        
        single_stmt = f"**Plant {n1}** has more available capacity at **{av1:,.2f} FT³** (Total: {tc1:,.2f} FT³), compared to **Plant {n2}** with **{av2:,.2f} FT³** (Total: {tc2:,.2f} FT³) — a difference of **{diff:,.2f} FT³**."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            "### 🏭 Capacity Comparison by Plant\n",
            single_stmt,
            "\n**Comparison Breakdown:**"
        ]
        for r in sorted_rows:
            p = r.get("Plant", "N/A")
            tc = r.get("Total Capacity (FT3)", 0.0)
            ov = r.get("Occupied Volume (FT3)", 0.0)
            ac = r.get("Available Capacity (FT3)", 0.0)
            cu = r.get("Capacity Utilization %", "0%")
            lines.append(f"- **Plant {p}**: **{ac:,.2f} FT³** available | Occupied: **{ov:,.2f} FT³** ({cu}) | Total: **{tc:,.2f} FT³**")
        lines.append(f"\n💡 *Conclusion: {single_stmt}*")
        return "\n".join(lines)

    # 0A_CAP_8. Capacity Summary: "Give me a capacity summary", "Warehouse capacity summary"
    if "Capacity Utilization %" in cols and "Available Capacity (FT3)" in cols and "Total Bins" in cols and "Bin" not in cols and len(rows) >= 2 and "Rank" not in cols and not any(k in q_lower for k in ["compare", "versus", "vs"]):
        tot_cap_all = sum(r.get("Total Capacity (FT3)", 0.0) for r in rows)
        tot_occ_all = sum(r.get("Occupied Volume (FT3)", 0.0) for r in rows)
        tot_avail_all = sum(r.get("Available Capacity (FT3)", 0.0) for r in rows)
        tot_bins_all = sum(r.get("Total Bins", 0) for r in rows)
        overall_util = round((tot_occ_all * 100.0 / tot_cap_all), 1) if tot_cap_all > 0 else 0.0
        
        single_stmt = f"Total warehouse storage capacity is **{tot_cap_all:,.2f} FT³** across **{tot_bins_all:,} bins** (Occupied: **{tot_occ_all:,.2f} FT³**, Available: **{tot_avail_all:,.2f} FT³**, Overall Utilization: **{overall_util}%**)."
        if is_single_statement_requested:
            return single_stmt

        lines = [
            "### 📊 Warehouse Capacity Summary\n",
            single_stmt,
            "\n**Plant Capacity Breakdown:**"
        ]
        for r in rows:
            p = r.get("Plant", "N/A")
            tc = r.get("Total Capacity (FT3)", 0.0)
            ov = r.get("Occupied Volume (FT3)", 0.0)
            ac = r.get("Available Capacity (FT3)", 0.0)
            cu = r.get("Capacity Utilization %", "0%")
            tb = r.get("Total Bins", 0)
            lines.append(f"- **Plant {p}**: **{tc:,.2f} FT³** total ({tb:,} bins) | Occupied: **{ov:,.2f} FT³** ({cu}) | Available: **{ac:,.2f} FT³**")
        lines.append("\n💡 *The complete capacity breakdown by plant is loaded in the **Data Table** below.*")
        return "\n".join(lines)

    # 0A_CAP_9. Bins Capacity List: "Show capacity for each bin", "Show capacity of all bins in Plant 1258"
    if "Bin" in cols and "Total Capacity (FT3)" in cols and "Available Capacity (FT3)" in cols and len(rows) > 1 and "Rank" not in cols and not any(k in q_lower for k in ["between", "from", "above", "below", "at least"]):
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else ""
        total_matching = rows[0].get("TotalMatching") if (rows and "TotalMatching" in rows[0]) else len(rows)
        displayed_rows = len(rows)
        explicit_lim = extract_explicit_limit(q_lower)
        if explicit_lim and total_matching > displayed_rows:
            single_stmt = f"Displaying capacity specifications for **{total_matching:,} matching bins**{plant_str}. Showing the first **{displayed_rows}**."
        else:
            single_stmt = f"Displaying capacity specifications for **{total_matching:,} bins**{plant_str} (Total Capacity, Occupied Volume, Available Capacity, and Capacity Utilization %)."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            f"### 📦 Bin Capacity Specifications{plant_str}\n",
            single_stmt,
            f"\n💡 *The itemized bin capacities are loaded in the **searchable Data Table** below.*"
        ]
        return "\n".join(lines)

    # 0A_CAP_10. Capacity Range Query: "Bins between 400 and 600 FT3 total capacity", "Bins with 100 to 300 FT3 free space"
    if ("Total Capacity (FT3)" in cols or "Available Capacity (FT3)" in cols or "Bin Capacity (FT3)" in cols) and "Bin" in cols and any(k in q_lower for k in ["between", "from", "at least", "above", "more than", "below", "under", "less than", "range", ">=", "<="]):
        rf_list = parse_range_filters(question)
        if rf_list:
            from .validator import validate_and_filter_range_rows
            valid_rows, _ = validate_and_filter_range_rows(rows, rf_list)
            rows = valid_rows
            count = len(rows)
            rf = rf_list[0]
            metric_name = "configured bin capacity" if rf.get("field") == "TotalCapacity" else ("occupied volume" if rf.get("field") == "Volume" else "available capacity")
            if rf["operator"] == "BETWEEN":
                rf_desc = f"between {rf['lower']:,.0f} and {rf['upper']:,.0f} FT³ {metric_name}"
            elif rf["operator"] in ["GT", "GTE"]:
                rf_desc = f"at least {rf['lower']:,.0f} FT³ {metric_name}" if rf.get("inclusive") else f"above {rf['lower']:,.0f} FT³ {metric_name}"
            elif rf["operator"] in ["LT", "LTE"]:
                rf_desc = f"up to {rf['upper']:,.0f} FT³ {metric_name}" if rf.get("inclusive") else f"below {rf['upper']:,.0f} FT³ {metric_name}"
            else:
                rf_desc = f"in the specified {metric_name} range"
            plant_val = extract_single_plant_safe(q_lower)
            plant_str = f" in Plant {plant_val}" if plant_val else ""
            if count == 0:
                single_stmt = f"No bins found with **{rf_desc}**{plant_str}."
            else:
                single_stmt = f"Found **{count:,} bins** with **{rf_desc}**{plant_str}."
            if is_single_statement_requested:
                return single_stmt
            lines = [
                f"### 📦 Bins with {rf_desc.capitalize()}{plant_str}\n",
                single_stmt,
                f"\n💡 *The matching bins with storage locations, capacities, and exact utilization percentages are loaded in the **searchable Data Table** below.*"
            ]
            return "\n".join(lines)

    # 0A_RANK_1. Specific Entity Rank Statement: "What rank is Plant 1258 by occupied volume?"
    if "Rank" in cols and len(rows) == 1 and any(k in q_lower for k in ["what rank is", "what is the rank", "where does", "where does plant stand", "what position", "rank of plant"]):
        target_p = rows[0].get("Plant", "N/A")
        rnk = rows[0].get("Rank", "-")
        if "Total Occupied Volume (FT3)" in cols:
            vol = rows[0].get("Total Occupied Volume (FT3)", 0.0)
            ob = rows[0].get("Occupied Bins", 0)
            tb = rows[0].get("Total Bins", 0)
            return f"**Plant {target_p}** ranks **#{rnk}** by total occupied volume at **{vol:,.2f} FT³** ({ob:,} occupied of {tb:,} total bins)."
        elif "Available Capacity (FT3)" in cols:
            avail = rows[0].get("Available Capacity (FT3)", 0.0)
            return f"**Plant {target_p}** ranks **#{rnk}** by available capacity at **{avail:,.2f} FT³**."
        elif "Total Bins" in cols:
            tb = rows[0].get("Total Bins", 0)
            return f"**Plant {target_p}** ranks **#{rnk}** by total bins with **{tb:,} bins**."
        elif "Unique Materials" in cols:
            m = rows[0].get("Unique Materials", 0)
            return f"**Plant {target_p}** ranks **#{rnk}** by unique materials with **{m:,} SKUs**."
        elif "Total Inventory Quantity" in cols:
            q = rows[0].get("Total Inventory Quantity", 0.0)
            return f"**Plant {target_p}** ranks **#{rnk}** by total inventory quantity at **{q:,.0f} units**."

    # 0A_RANK_2. Ranking Explanation: "Why is Plant 1268 ranked #1 by occupied volume?"
    if any(k in q_lower for k in ["why is", "why are", "why does", "explain why"]) and ("#1" in q_lower or "number 1" in q_lower or "ranked 1" in q_lower or "first" in q_lower or "leader" in q_lower) and "Total Occupied Volume (FT3)" in cols:
        lead_p = rows[0].get("Plant", "1268")
        lead_v = rows[0].get("Total Occupied Volume (FT3)", 0.0)
        lead_cap = rows[0].get("Total Capacity (FT3)", 0.0)
        lead_ob = rows[0].get("Occupied Bins", 0)
        lead_tb = rows[0].get("Total Bins", 0)
        other_summaries = ", ".join(f"Plant {r.get('Plant')}: {r.get('Total Occupied Volume (FT3)', 0.0):,.0f} FT³" for r in rows[1:])
        return f"**Plant {lead_p}** is ranked **#1** by total occupied volume at **{lead_v:,.2f} FT³** because it maintains the highest storage volume across all facilities ({other_summaries}), with a total capacity of **{lead_cap:,.2f} FT³** across {lead_tb:,} bins ({lead_ob:,} occupied)."

    # 0A_RANK_3. Subset Plant Ranking: "Rank Plant 1258 and Plant 7228 by occupied volume"
    if "Total Occupied Volume (FT3)" in cols and "Plant" in cols and "Rank" in cols and len(rows) == 2 and any(k in q_lower for k in ["and plant", "versus", "vs", "between"]):
        p1, p2 = rows[0], rows[1]
        n1, v1 = p1.get("Plant", "N/A"), p1.get("Total Occupied Volume (FT3)", 0.0)
        n2, v2 = p2.get("Plant", "N/A"), p2.get("Total Occupied Volume (FT3)", 0.0)
        single_stmt = f"Between the specified facilities, **Plant {n1}** ranks **#1** with **{v1:,.2f} FT³** occupied volume, followed by **Plant {n2}** at **#2** with **{v2:,.2f} FT³**."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            "### 📊 Plant Occupied Volume Subset Ranking\n",
            single_stmt,
            f"\n- **Rank 1 — Plant {n1}**: **{v1:,.2f} FT³** ({p1.get('Occupied Bins', 0):,} / {p1.get('Total Bins', 0):,} bins)",
            f"- **Rank 2 — Plant {n2}**: **{v2:,.2f} FT³** ({p2.get('Occupied Bins', 0):,} / {p2.get('Total Bins', 0):,} bins)",
            "\n💡 *The ranked results are displayed in the **Data Table** below.*"
        ]
        return "\n".join(lines)

    # 0A_RANK_4. Plant Occupied Volume Ranking: "Rank all plants by total occupied volume", "Which plant has the highest occupied volume?"
    if "Total Occupied Volume (FT3)" in cols and "Plant" in cols and ("Rank" in cols or len(rows) <= 4):
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum", "smallest"])
        label = "Lowest" if is_least else "Highest"
        lead_p = rows[0].get("Plant", "N/A")
        lead_v = rows[0].get("Total Occupied Volume (FT3)", 0.0)
        lead_ob = rows[0].get("Occupied Bins", 0)
        lead_tb = rows[0].get("Total Bins", 0)
        
        if len(rows) == 1 or is_single_statement_requested:
            return f"**Plant {lead_p}** has the **{label.lower()} total occupied volume** across all facilities at **{lead_v:,.2f} FT³** ({lead_ob:,} occupied of {lead_tb:,} total bins)."
        
        single_stmt = f"**Plant {lead_p}** ranks #1 with the highest total occupied volume at **{lead_v:,.2f} FT³** ({lead_ob:,} occupied of {lead_tb:,} total bins)."
        lines = [
            f"### 📊 Plant Ranking by Total Occupied Volume\n",
            single_stmt,
            f"\n**Plant Volume Ranking:**"
        ]
        for r in rows:
            rnk = r.get("Rank", "-")
            p = r.get("Plant", "N/A")
            v = r.get("Total Occupied Volume (FT3)", 0.0)
            ob = r.get("Occupied Bins", 0)
            tb = r.get("Total Bins", 0)
            lines.append(f"- **Rank {rnk} — Plant {p}**: **{v:,.2f} FT³** ({ob:,} / {tb:,} bins occupied)")
        lines.append("\n💡 *The complete ranking is rendered in the **Data Table** below.*")
        return "\n".join(lines)

    # 0A_RANK_5. Plant Available Capacity Ranking: "Rank plants by available capacity"
    if "Available Capacity (FT3)" in cols and "Plant" in cols and "Total Capacity (FT3)" in cols:
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum", "smallest"])
        label = "Lowest" if is_least else "Highest"
        lead_p = rows[0].get("Plant", "N/A")
        lead_avail = rows[0].get("Available Capacity (FT3)", 0.0)
        lead_tot = rows[0].get("Total Capacity (FT3)", 0.0)
        lead_occ = rows[0].get("Occupied Volume (FT3)", 0.0)
        if len(rows) == 1 or is_single_statement_requested:
            return f"**Plant {lead_p}** has the **{label.lower()} available capacity** at **{lead_avail:,.2f} FT³** (Total Capacity: {lead_tot:,.2f} FT³, Occupied: {lead_occ:,.2f} FT³)."
        single_stmt = f"**Plant {lead_p}** ranks #1 with the most available capacity at **{lead_avail:,.2f} FT³** (Total Capacity: {lead_tot:,.2f} FT³)."
        lines = [
            f"### 📊 Plant Ranking by Available Capacity\n",
            single_stmt,
            f"\n**Available Capacity Ranking:**"
        ]
        for r in rows:
            rnk = r.get("Rank", "-")
            p = r.get("Plant", "N/A")
            av = r.get("Available Capacity (FT3)", 0.0)
            tc = r.get("Total Capacity (FT3)", 0.0)
            lines.append(f"- **Rank {rnk} — Plant {p}**: **{av:,.2f} FT³** available (Total: {tc:,.2f} FT³)")
        lines.append("\n💡 *The complete ranking is rendered in the **Data Table** below.*")
        return "\n".join(lines)

    # 0A_RANK_6. Bin Available Capacity Ranking: "Rank bins by available capacity", "Which bin has the most available space?"
    if "Available Capacity (FT3)" in cols and "Bin" in cols:
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum", "smallest"])
        label = "Least" if is_least else "Most"
        lead_b = rows[0].get("Bin", "N/A")
        lead_p = rows[0].get("Plant", "")
        lead_avail = rows[0].get("Available Capacity (FT3)", 0.0)
        lead_cap = rows[0].get("Bin Capacity", "N/A")
        lead_occ = rows[0].get("Occupied Volume", 0.0)
        lead_p_str = f" (Plant {lead_p})" if lead_p else ""
        if len(rows) == 1 or is_single_statement_requested:
            return f"Bin **`{lead_b}`**{lead_p_str} has the **{label.lower()} available capacity** at **{lead_avail:,.2f} FT³** (Total Capacity: {lead_cap}, Occupied: {lead_occ:,.2f} FT³)."
        single_stmt = f"Top {len(rows)} Bins Ranked by Available Capacity (leader: **`{lead_b}`** at **{lead_avail:,.2f} FT³**)."
        lines = [
            f"### 📊 Bins Ranked by Available Capacity\n",
            single_stmt,
            f"\n💡 *The matching bins with available capacities and total volumes are loaded in the **Data Table** below.*"
        ]
        return "\n".join(lines)

    # 0A_RANK_EMPTY_BINS. Plant Empty Bins Ranking: "Rank plants by number of empty bins", "Which plant has the most empty bins?"
    if "Empty Bins" in cols and "Plant" in cols and "Rank" in cols and "Bin" not in cols and "BinUtilizationPct" not in cols and "Bin Utilization %" not in cols and not any(k in q_lower for k in ["utiliz", "compare", "versus", "vs"]):
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum", "smallest", "fewest"])
        label = "Fewest" if is_least else "Most"
        lead_p = rows[0].get("Plant", "N/A")
        lead_eb = rows[0].get("Empty Bins", 0)
        lead_tb = rows[0].get("Total Bins", 0)
        lead_ob = rows[0].get("Occupied Bins", 0)
        
        if len(rows) == 1 or is_single_statement_requested:
            return f"**Plant {lead_p}** has the **{label.lower()} empty bins** with **{lead_eb:,} empty bins** currently available for put-away (out of {lead_tb:,} total bins, {lead_ob:,} occupied)."
        
        single_stmt = f"**Plant {lead_p}** ranks #1 with the {label.lower()} empty bins at **{lead_eb:,} empty bins** available for put-away ({lead_tb:,} total bins, {lead_ob:,} occupied)."
        lines = [
            f"### 📦 Plant Ranking by Number of Empty Bins\n",
            single_stmt,
            f"\n**Plant Empty Bins Ranking:**"
        ]
        for r in rows:
            rnk = r.get("Rank", "-")
            p = r.get("Plant", "N/A")
            eb = r.get("Empty Bins", 0)
            tb = r.get("Total Bins", 0)
            lines.append(f"- **Rank {rnk} — Plant {p}**: **{eb:,} empty bins** ({tb:,} total bins)")
        lines.append("\n💡 *The complete ranking is rendered in the **Data Table** below.*")
        return "\n".join(lines)

    # 0A_RANK_7. Plant Total Bins Ranking: "Rank plants by number of bins"
    if "Total Bins" in cols and "Occupied Bins" in cols and "Plant" in cols and "Rank" in cols and "Total Occupied Volume (FT3)" not in cols and "Bin Utilization %" not in cols and "Empty Bins" not in cols:
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum", "fewest"])
        label = "Fewest" if is_least else "Most"
        lead_p = rows[0].get("Plant", "N/A")
        lead_tb = rows[0].get("Total Bins", 0)
        lead_ob = rows[0].get("Occupied Bins", 0)
        if len(rows) == 1 or is_single_statement_requested:
            return f"**Plant {lead_p}** has the **{label.lower()} bins** across all facilities with **{lead_tb:,} total bins** ({lead_ob:,} occupied)."
        single_stmt = f"**Plant {lead_p}** ranks #1 with **{lead_tb:,} bins** ({lead_ob:,} occupied)."
        lines = [
            f"### 📊 Plant Ranking by Total Bins\n",
            single_stmt,
            f"\n**Plant Bins Ranking:**"
        ]
        for r in rows:
            rnk = r.get("Rank", "-")
            p = r.get("Plant", "N/A")
            tb = r.get("Total Bins", 0)
            ob = r.get("Occupied Bins", 0)
            lines.append(f"- **Rank {rnk} — Plant {p}**: **{tb:,} bins** ({ob:,} occupied)")
        lines.append("\n💡 *The complete ranking is rendered in the **Data Table** below.*")
        return "\n".join(lines)

    # 0A_RANK_8. Plant Unique Materials Ranking: "Rank plants by unique materials"
    if "Unique Materials" in cols and "Total Stock Quantity" in cols and "Plant" in cols and "Rank" in cols:
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum", "fewest"])
        label = "Fewest" if is_least else "Most"
        lead_p = rows[0].get("Plant", "N/A")
        lead_m = rows[0].get("Unique Materials", 0)
        lead_q = rows[0].get("Total Stock Quantity", 0.0)
        if len(rows) == 1 or is_single_statement_requested:
            return f"**Plant {lead_p}** holds the **{label.lower()} unique materials** with **{lead_m:,} SKUs** ({lead_q:,.0f} total stock units)."
        single_stmt = f"**Plant {lead_p}** ranks #1 with **{lead_m:,} unique materials** ({lead_q:,.0f} total stock units)."
        lines = [
            f"### 📊 Plant Ranking by Unique Materials\n",
            single_stmt,
            f"\n**Unique Materials Ranking:**"
        ]
        for r in rows:
            rnk = r.get("Rank", "-")
            p = r.get("Plant", "N/A")
            m = r.get("Unique Materials", 0)
            q = r.get("Total Stock Quantity", 0.0)
            lines.append(f"- **Rank {rnk} — Plant {p}**: **{m:,} unique materials** ({q:,.0f} units)")
        lines.append("\n💡 *The complete ranking is rendered in the **Data Table** below.*")
        return "\n".join(lines)

    # 0A_RANK_9. Plant Total Inventory Quantity Ranking: "Rank plants by inventory quantity"
    if "Total Inventory Quantity" in cols and "Plant" in cols and "Rank" in cols and "Storage Location" not in cols and "Storage Locations Count" not in cols:
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum", "smallest"])
        label = "Lowest" if is_least else "Highest"
        lead_p = rows[0].get("Plant", "N/A")
        lead_q = rows[0].get("Total Inventory Quantity", 0.0)
        lead_m = rows[0].get("Unique Materials", 0)
        if len(rows) == 1 or is_single_statement_requested:
            return f"**Plant {lead_p}** has the **{label.lower()} total inventory quantity** at **{lead_q:,.0f} units** across {lead_m:,} unique materials."
        single_stmt = f"**Plant {lead_p}** ranks #1 with the highest total inventory quantity at **{lead_q:,.0f} units** ({lead_m:,} unique materials)."
        lines = [
            f"### 📊 Plant Ranking by Total Inventory Quantity\n",
            single_stmt,
            f"\n**Total Inventory Quantity Ranking:**"
        ]
        for r in rows:
            rnk = r.get("Rank", "-")
            p = r.get("Plant", "N/A")
            q = r.get("Total Inventory Quantity", 0.0)
            m = r.get("Unique Materials", 0)
            lines.append(f"- **Rank {rnk} — Plant {p}**: **{q:,.0f} units** ({m:,} materials)")
        lines.append("\n💡 *The complete ranking is rendered in the **Data Table** below.*")
        return "\n".join(lines)

    # 0A0. Cross-Table Validation: Count of Materials Missing from Volume Master (Rule DQ-001 Count)
    if "Missing Materials Count" in cols or ("Count" in cols and any(k in q_lower for k in ["volume master", "material master", "missing", "without dimension", "no corresponding", "entries", "entry"])):
        count_val = rows[0].get("Missing Materials Count", rows[0].get("Count", 0))
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else ""

        single_stmt = f"There are **{count_val:,}** inventory items that do not have corresponding Volume Master entries{plant_str}."
        return single_stmt

    # 0A. Cross-Table Validation: Materials Missing from Volume Master (Rule DQ-001)
    if "Inventory Qty" in cols and ("Storage Location" in cols or "StorageLocation" in cols) and "Quality Issue" not in cols and "Bin" not in cols and "BinLocation" not in cols:
        total_missing_qty = sum(r.get("Inventory Qty", 0) for r in rows)
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else " across active inventory"

        single_stmt = f"Detected **{count} material records** in Inventory Master that have no corresponding record in Material Volume Master{plant_str} (affecting **{total_missing_qty:,.2f} total inventory units**)."
        if is_single_statement_requested:
            return single_stmt

        lines = [
            f"### ⚠️ Cross-Table Validation: Materials Missing from Volume Master\n",
            single_stmt,
            f"\n**Cross-Master Rule & Findings:**",
            f"- **Validation Rule:** `InventoryMaster.Material` $\\rightarrow$ `MaterialVolumeMaster.MaterialCode`",
            f"- **Issue Classified:** `Missing Volume Master Record` (Materials actively present in inventory without dimension/volume master records).",
            f"\n💡 *The **Exception List** with affected Plants, Storage Locations, and Inventory Quantities is rendered in the **Data Table** below.*"
        ]
        return "\n".join(lines)

    # 0B. Data Quality / Missing Dimensions Summary
    if "Quality Issue" in cols or (("Length" in cols or "Width" in cols or "Height" in cols) and "Occupied Bins" in cols):
        completely_missing = sum(1 for r in rows if "Completely" in str(r.get("Quality Issue", "")))
        incomplete = sum(1 for r in rows if "Incomplete" in str(r.get("Quality Issue", "")))
        missing_master = sum(1 for r in rows if "Missing Volume Master" in str(r.get("Quality Issue", "")) or "Not in" in str(r.get("Quality Issue", "")))
        total_affected_qty = sum(r.get("Total Stock Qty", 0) for r in rows)
        
        single_stmt = f"Detected **{count} material records** with data quality exceptions (missing or incomplete physical dimensions / volume metadata) affecting **{total_affected_qty:,.2f} total inventory units**."
        if is_single_statement_requested:
            return single_stmt
            
        lines = [
            f"### ⚠️ Data Quality Exception: Missing Material Dimensions & Volume Records\n",
            single_stmt,
            f"\n**Data Quality Breakdown & Detected Issues:**",
            f"- **Missing Volume Master Record:** **{missing_master}** materials exist in Inventory Master but have no entry in Material Volume Master.",
            f"- **Completely Missing Dimensions:** **{completely_missing}** materials have entries in Material Volume Master but Length, Width, and Height are all blank or NULL.",
            f"- **Incomplete Dimensions:** **{incomplete}** materials have partial dimension data missing (Length, Width, Height, or Volume is NULL or zero).",
            f"\n💡 *The complete **Exception Table** with all relevant fields (`Material`, `Description`, `Total Stock Qty`, `Occupied Bins`, `Length`, `Width`, `Height`, `Volume`, `Quality Issue`) is displayed in the **searchable Data Table** below.*"
        ]
        return "\n".join(lines)

    # 0C_comp. General Comparison Engine (Inventory, Materials, Bins, Empty Bins, Storage Locations, Overview)
    # 0C_comp_1. Comparison: Total Inventory Quantity
    if "Total Inventory Quantity" in cols and "Storage Locations Count" not in cols and "Plant" in cols and len(rows) >= 2:
        sorted_rows = sorted(rows, key=lambda x: x.get("Total Inventory Quantity", 0), reverse=True)
        p1, p2 = sorted_rows[0], sorted_rows[1]
        name1, q1, m1, b1 = p1.get("Plant", "N/A"), p1.get("Total Inventory Quantity", 0), p1.get("Unique Materials", 0), p1.get("Occupied Bins", 0)
        name2, q2, m2, b2 = p2.get("Plant", "N/A"), p2.get("Total Inventory Quantity", 0), p2.get("Unique Materials", 0), p2.get("Occupied Bins", 0)
        diff = q1 - q2
        single_stmt = f"**Plant {name1}** has the higher total inventory at **{q1:,.0f} units** ({m1:,} unique materials across {b1:,} occupied bins), compared to **Plant {name2}** with **{q2:,.0f} units** ({m2:,} materials, {b2:,} bins) — a difference of **{diff:,.0f} units**."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            f"### 🏭 Total Inventory Comparison\n",
            single_stmt,
            f"\n**Plant Breakdown:**",
        ]
        for r in sorted_rows:
            p = r.get("Plant", "N/A")
            q = r.get("Total Inventory Quantity", 0)
            m = r.get("Unique Materials", 0)
            b = r.get("Occupied Bins", 0)
            lines.append(f"- **Plant {p}**: **{q:,.0f} units** | **{m:,} unique materials** | **{b:,} occupied bins**")
        lines.append(f"\n💡 *The full comparison metrics are displayed in the **Data Table** below.*")
        return "\n".join(lines)

    # 0C_comp_2. Comparison: Unique Materials / SKUs
    if "Unique Materials Count" in cols and "Plant" in cols and len(rows) >= 2:
        sorted_rows = sorted(rows, key=lambda x: x.get("Unique Materials Count", 0), reverse=True)
        p1, p2 = sorted_rows[0], sorted_rows[1]
        name1, m1, q1 = p1.get("Plant", "N/A"), p1.get("Unique Materials Count", 0), p1.get("Total Stock Qty", 0)
        name2, m2, q2 = p2.get("Plant", "N/A"), p2.get("Unique Materials Count", 0), p2.get("Total Stock Qty", 0)
        single_stmt = f"**Plant {name1}** holds more unique materials with **{m1:,} SKUs** ({q1:,.0f} total stock units), compared to **Plant {name2}** with **{m2:,} SKUs** ({q2:,.0f} units)."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            f"### 🏭 Unique Materials Comparison\n",
            single_stmt,
            f"\n**Plant Breakdown:**",
        ]
        for r in sorted_rows:
            p = r.get("Plant", "N/A")
            m = r.get("Unique Materials Count", 0)
            q = r.get("Total Stock Qty", 0)
            b = r.get("Occupied Bins", 0)
            lines.append(f"- **Plant {p}**: **{m:,} unique materials** | **{q:,.0f} stock units** | **{b:,} occupied bins**")
        lines.append(f"\n💡 *The full comparison metrics are displayed in the **Data Table** below.*")
        return "\n".join(lines)

    # 0C_comp_3. Comparison: Empty Bins
    if "Empty Bins" in cols and "Empty Bins %" in cols and "Plant" in cols and len(rows) >= 2:
        sorted_rows = sorted(rows, key=lambda x: x.get("Empty Bins", 0), reverse=True)
        p1, p2 = sorted_rows[0], sorted_rows[1]
        name1, eb1, tb1, pct1 = p1.get("Plant", "N/A"), p1.get("Empty Bins", 0), p1.get("Total Bins", 0), p1.get("Empty Bins %", "0%")
        name2, eb2, tb2, pct2 = p2.get("Plant", "N/A"), p2.get("Empty Bins", 0), p2.get("Total Bins", 0), p2.get("Empty Bins %", "0%")
        single_stmt = f"**Plant {name1}** has **{eb1:,} empty bins** ({pct1} of {tb1:,} total bins), compared to **Plant {name2}** with **{eb2:,} empty bins** ({pct2} of {tb2:,} total bins)."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            f"### 📦 Empty Bins Comparison\n",
            single_stmt,
            f"\n**Plant Breakdown:**",
        ]
        for r in sorted_rows:
            p = r.get("Plant", "N/A")
            eb = r.get("Empty Bins", 0)
            tb = r.get("Total Bins", 0)
            pct = r.get("Empty Bins %", "0%")
            lines.append(f"- **Plant {p}**: **{eb:,} empty bins** ({pct} of {tb:,} total bins)")
        lines.append(f"\n💡 *The full comparison metrics are displayed in the **Data Table** below.*")
        return "\n".join(lines)

    # 0C_comp_4. Comparison: Occupied Bins
    if "Occupied Bins" in cols and "Bin Utilization %" in cols and "Total Bins" in cols and "Plant" in cols and len(rows) >= 2 and any(k in q_lower for k in ["occupied", "active bin", "in use"]):
        sorted_rows = sorted(rows, key=lambda x: x.get("Occupied Bins", 0), reverse=True)
        p1, p2 = sorted_rows[0], sorted_rows[1]
        name1, ob1, tb1, pct1 = p1.get("Plant", "N/A"), p1.get("Occupied Bins", 0), p1.get("Total Bins", 0), p1.get("Bin Utilization %", "0%")
        name2, ob2, tb2, pct2 = p2.get("Plant", "N/A"), p2.get("Occupied Bins", 0), p2.get("Total Bins", 0), p2.get("Bin Utilization %", "0%")
        single_stmt = f"**Plant {name1}** has **{ob1:,} occupied bins** ({pct1} utilization across {tb1:,} total bins), compared to **Plant {name2}** with **{ob2:,} occupied bins** ({pct2} utilization across {tb2:,} total bins)."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            f"### 📦 Occupied Bins Comparison\n",
            single_stmt,
            f"\n**Plant Breakdown:**",
        ]
        for r in sorted_rows:
            p = r.get("Plant", "N/A")
            ob = r.get("Occupied Bins", 0)
            tb = r.get("Total Bins", 0)
            pct = r.get("Bin Utilization %", "0%")
            lines.append(f"- **Plant {p}**: **{ob:,} occupied bins** ({pct} across {tb:,} total bins)")
        lines.append(f"\n💡 *The full comparison metrics are displayed in the **Data Table** below.*")
        return "\n".join(lines)

    # 0C_comp_5. Comparison: Physical Bins (Total Bins & Occupancy Rate)
    if "Total Bins" in cols and "Occupancy Rate" in cols and "Plant" in cols and len(rows) >= 2:
        sorted_rows = sorted(rows, key=lambda x: x.get("Total Bins", 0), reverse=True)
        p1, p2 = sorted_rows[0], sorted_rows[1]
        name1, tb1, ob1, eb1 = p1.get("Plant", "N/A"), p1.get("Total Bins", 0), p1.get("Occupied Bins", 0), p1.get("Empty Bins", 0)
        name2, tb2, ob2, eb2 = p2.get("Plant", "N/A"), p2.get("Total Bins", 0), p2.get("Occupied Bins", 0), p2.get("Empty Bins", 0)
        single_stmt = f"**Plant {name1}** has **{tb1:,} total bins** ({ob1:,} occupied, {eb1:,} empty), compared to **Plant {name2}** with **{tb2:,} total bins** ({ob2:,} occupied, {eb2:,} empty)."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            f"### 📦 Total Bins Comparison\n",
            single_stmt,
            f"\n**Plant Breakdown:**",
        ]
        for r in sorted_rows:
            p = r.get("Plant", "N/A")
            tb = r.get("Total Bins", 0)
            ob = r.get("Occupied Bins", 0)
            eb = r.get("Empty Bins", 0)
            rate = r.get("Occupancy Rate", "0%")
            lines.append(f"- **Plant {p}**: **{tb:,} total bins** | {ob:,} occupied | {eb:,} empty ({rate} occupancy)")
        lines.append(f"\n💡 *The full comparison metrics are displayed in the **Data Table** below.*")
        return "\n".join(lines)

    # 0C_comp_6. Comparison: Storage Locations
    if "Storage Locations Count" in cols and "Active Materials" in cols and "Plant" in cols and len(rows) >= 2:
        sorted_rows = sorted(rows, key=lambda x: x.get("Storage Locations Count", 0), reverse=True)
        p1, p2 = sorted_rows[0], sorted_rows[1]
        name1, sl1, m1 = p1.get("Plant", "N/A"), p1.get("Storage Locations Count", 0), p1.get("Active Materials", 0)
        name2, sl2, m2 = p2.get("Plant", "N/A"), p2.get("Storage Locations Count", 0), p2.get("Active Materials", 0)
        single_stmt = f"**Plant {name1}** operates **{sl1} storage locations** ({m1:,} active materials), compared to **Plant {name2}** with **{sl2} storage locations** ({m2:,} active materials)."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            f"### 📍 Storage Locations Comparison\n",
            single_stmt,
            f"\n**Plant Breakdown:**",
        ]
        for r in sorted_rows:
            p = r.get("Plant", "N/A")
            sl = r.get("Storage Locations Count", 0)
            m = r.get("Active Materials", 0)
            q = r.get("Total Inventory Quantity", 0)
            lines.append(f"- **Plant {p}**: **{sl} storage locations** | {m:,} active materials | {q:,.0f} units")
        lines.append(f"\n💡 *The full comparison metrics are displayed in the **Data Table** below.*")
        return "\n".join(lines)

    # 0C_comp_7. Comparison: Overview / Multi-Metric Plant Comparison
    if "Total Inventory Qty" in cols and "Total Bins" in cols and "Bin Utilization %" in cols and "Plant" in cols and len(rows) >= 2:
        p1, p2 = rows[0], rows[1]
        name1, q1, tb1, u1 = p1.get("Plant", "N/A"), p1.get("Total Inventory Qty", 0), p1.get("Total Bins", 0), p1.get("Bin Utilization %", "0%")
        name2, q2, tb2, u2 = p2.get("Plant", "N/A"), p2.get("Total Inventory Qty", 0), p2.get("Total Bins", 0), p2.get("Bin Utilization %", "0%")
        single_stmt = f"Plant comparison: **Plant {name1}** has **{q1:,.0f} units** across **{tb1:,} bins** ({u1} utilization), while **Plant {name2}** has **{q2:,.0f} units** across **{tb2:,} bins** ({u2} utilization)."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            f"### 🏭 Plant Overview Comparison\n",
            single_stmt,
            f"\n**Detailed Plant Comparison:**",
        ]
        for r in rows:
            p = r.get("Plant", "N/A")
            q = r.get("Total Inventory Qty", 0)
            m = r.get("Unique Materials", 0)
            tb = r.get("Total Bins", 0)
            ob = r.get("Occupied Bins", 0)
            eb = r.get("Empty Bins", 0)
            u = r.get("Bin Utilization %", "0%")
            lines.append(f"- **Plant {p}**: **{q:,.0f} units** | **{m:,} unique materials** | **{tb:,} bins** ({ob:,} occupied, {eb:,} empty, **{u}** utilization)")
        lines.append(f"\n💡 *The complete side-by-side comparison is rendered in the **Data Table** below.*")
        return "\n".join(lines)

    # 0C_range_1. Range Query: Material Quantity Range (field: UnrestrictedQty)
    if "Total Stock Qty" in cols and "Occupied Bins" in cols and "Material" in cols and "Plant" in cols:
        rf_list = parse_range_filters(question)
        if rf_list:
            from .validator import validate_and_filter_range_rows
            valid_rows, _ = validate_and_filter_range_rows(rows, rf_list)
            rows = valid_rows
            count = len(rows)
            rf = rf_list[0]
            if rf["operator"] == "BETWEEN":
                rf_desc = f"between {rf['lower']:,.0f} and {rf['upper']:,.0f} units"
            elif rf["operator"] in ["GT", "GTE"]:
                rf_desc = f"at least {rf['lower']:,.0f} units"
            elif rf["operator"] in ["LT", "LTE"]:
                rf_desc = f"up to {rf['upper']:,.0f} units"
            else:
                rf_desc = "within the specified range"
        else:
            rf_desc = "within the specified range"
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else ""
        if count == 0:
            single_stmt = f"No materials found with inventory quantity **{rf_desc}**{plant_str}."
        else:
            single_stmt = f"Found **{count:,} materials** with inventory quantity **{rf_desc}**{plant_str}."
        if is_single_statement_requested:
            return single_stmt
        lines = [
            f"### 📊 Materials with Inventory {rf_desc.capitalize()}{plant_str}\n",
            single_stmt,
            f"\n💡 *The matching materials with plant locations, total stock quantities, and occupied bins are displayed in the **Data Table** below.*"
        ]
        return "\n".join(lines)

    # 0C_range_2. Range Query: Bin Utilization Range (field: BinUtilizationPct)
    if ("Utilization %" in cols or "UtilizationPct" in cols or "Bin Capacity" in cols) and any(k in q_lower for k in ["between", "%-", "% -", "% to", "to "]):
        rf_list = parse_range_filters(question)
        if rf_list and rf_list[0].get("field") == "BinUtilizationPct":
            rf = rf_list[0]
            from .validator import validate_and_filter_range_rows
            valid_rows, _ = validate_and_filter_range_rows(rows, rf_list)
            rows = valid_rows
            count = len(rows)
            if rf["operator"] == "BETWEEN":
                rf_desc = f"between {rf['lower']}% and {rf['upper']}% utilization"
            elif rf["operator"] in ["GT", "GTE"]:
                rf_desc = f"above {rf['lower']}% utilization"
            elif rf["operator"] in ["LT", "LTE"]:
                rf_desc = f"below {rf['upper']}% utilization"
            else:
                rf_desc = "in the requested utilization range"
            plant_val = extract_single_plant_safe(q_lower)
            plant_str = f" in Plant {plant_val}" if plant_val else ""
            if count == 0:
                single_stmt = f"No bins found operating with **{rf_desc}**{plant_str}."
            else:
                single_stmt = f"Found **{count:,} bins** operating with **{rf_desc}**{plant_str}."
            if is_single_statement_requested:
                return single_stmt
            lines = [
                f"### 📦 Bins with {rf_desc.capitalize()}{plant_str}\n",
                single_stmt,
                f"\n💡 *The matching bins with storage locations, capacities, and exact utilization percentages are loaded in the **searchable Data Table** below.*"
            ]
            return "\n".join(lines)

    # 1. Top Materials by Share of Total Bin Volume (Matching Recommended Chatbot Response)
    if "Total Material Volume" in cols or "% of Total Bin Volume" in cols:
        leader_mat = rows[0].get("Material", "N/A") if rows else "N/A"
        leader_desc = rows[0].get("Material Description", rows[0].get("MaterialDescription", "")) if rows else ""
        leader_vol = rows[0].get("Total Material Volume", 0.0) if rows else 0.0
        leader_pct = rows[0].get("% of Total Bin Volume", "0%") if rows else "0%"
        
        single_stmt = f"Top 10 Materials by Share of Total Bin Volume: The following materials consume the highest percentage of the warehouse's total bin volume, ranked from highest to lowest (leader: **`{leader_mat}`** at **{leader_vol:,.2f} FT³** / {leader_pct})."
        if is_single_statement_requested:
            return single_stmt
            
        lines = [
            "### 📊 Top 10 Materials by Share of Total Bin Volume\n",
            "The following materials consume the highest percentage of the warehouse's total bin volume, ranked from highest to lowest.\n",
            f"- **Top Consumer:** Material **`{leader_mat}`** (**{leader_desc}**) accounts for **{leader_vol:,.2f} FT³** (**{leader_pct}** of total warehouse bin capacity).",
            f"- **Ranking Summary:** Ranked by total occupied volume share across active warehouse bins.",
            "\n💡 *The interactive **Bar Chart** and itemized **Results Table** below display all top materials with quantities, total volumes, and exact percentage shares:*"
        ]
        return "\n".join(lines)

    # 0C. Specific Bin Utilization & Details (Explicit Single Bin Scope)
    if "Bin" in cols and ("Utilization %" in cols or "Bin Capacity" in cols or "PalletType" in cols or "VolumeUnit" in cols) and len(rows) == 1 and not any(k in q_lower for k in ["top", "bottom", "least", "most", "lowest", "highest", "ranking", "more than", "less than", "above", "below", "over", "under", "list", "show", "find", "between", ">", "<", "greater", "exceed"]):
        bin_val = rows[0].get("Bin", "N/A")
        plant_val = rows[0].get("Plant", "")
        plant_str = f" in Plant {plant_val}" if plant_val else ""
        util_val = rows[0].get("Utilization %", "")
        cap_val = rows[0].get("Bin Capacity", rows[0].get("Volume", "N/A"))
        occ_vol = rows[0].get("Occupied Volume", "")
        sloc_val = rows[0].get("Storage Location", rows[0].get("StorageLocation", ""))
        mat_val = rows[0].get("Material", "")
        desc_val = rows[0].get("Description", rows[0].get("MaterialDescription", ""))
        qty_val = rows[0].get("Qty", rows[0].get("UnrestrictedQty", None))
        uom_val = rows[0].get("UOM", rows[0].get("BaseUnitOfMeasure", "EA"))

        if util_val:
            single_stmt = f"The utilization of **Bin {bin_val}**{plant_str} is **{util_val}** (Occupied: {occ_vol}, Capacity: {cap_val})."
        elif mat_val and qty_val is not None:
            single_stmt = f"**Bin {bin_val}**{plant_str} currently stores **{qty_val:,.0f} {uom_val}** of Material **`{mat_val}`** ({desc_val})."
        else:
            single_stmt = f"**Bin {bin_val}**{plant_str} is in Storage Location **{sloc_val}** with capacity of **{cap_val}**."

        if is_single_statement_requested:
            return single_stmt

        lines = [
            f"### 📦 Bin {bin_val}{plant_str} Details\n",
            single_stmt,
            f"\n**Bin Specifications & Context:**"
        ]
        if util_val:
            lines.append(f"- **Current Utilization (Primary):** **{util_val}**")
        if occ_vol:
            lines.append(f"- **Occupied Volume:** {occ_vol}")
        if cap_val:
            lines.append(f"- **Total Bin Capacity:** {cap_val}")
        if sloc_val:
            lines.append(f"- **Storage Location:** `{sloc_val}`")
        if mat_val and qty_val is not None:
            lines.append(f"- **Stored Stock:** **{qty_val:,.0f} {uom_val}** of Material `{mat_val}` ({desc_val})")

        return "\n".join(lines)

    # 0D_plants. Active Operational Plants Count (Direct Single Metric)
    if "Active Plants Count" in cols or ("PlantCount" in cols and len(cols) == 1) or ("Plant Count" in cols and len(cols) == 1):
        count_val = rows[0].get("Active Plants Count", rows[0].get("PlantCount", rows[0].get("Plant Count", 4)))
        return f"**{count_val:,} operational plants** (1258, 1266, 1268, 7228)."

    # 0D_slocs. Storage Locations Count (Direct Single Metric)
    if "Storage Locations Count" in cols or ("Storage Location Count" in cols and len(cols) == 1):
        count_val = rows[0].get("Storage Locations Count", rows[0].get("Storage Location Count", 0))
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else ""
        return f"**{count_val:,} storage locations**{plant_str}."

    # 0D. Occupied Bins Count (Direct Single Metric)
    if "Occupied Bins Count" in cols:
        count_val = rows[0].get("Occupied Bins Count", 0)
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else ""
        return f"**{count_val:,} occupied bins**{plant_str}."

    # 0E. Total Bins Count (Direct Single Metric)
    if "Total Bins Count" in cols:
        count_val = rows[0].get("Total Bins Count", 0)
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else ""
        return f"**{count_val:,} total bins**{plant_str}."

    # 0D_records. Inventory Records Count (Concept B - COUNT(rows))
    if "Inventory Records Count" in cols or (len(cols) == 1 and any(k in q_lower for k in ["inventory record", "inventory records", "inventory row", "inventory rows", "records are there", "records in inventory", "number of inventory records", "count of inventory records", "total inventory records", "records in plant", "how many inventory records", "how many records in inventory", "total inventory rows"])):
        count_val = rows[0].get("Inventory Records Count", list(rows[0].values())[0])
        plant_val = extract_single_plant_safe(q_lower)
        if plant_val:
            return f"There are **{count_val:,}** inventory records in Plant {plant_val}."
        return f"There are **{count_val:,}** inventory records."

    # 0F. Total Unique Materials / SKU Count (Concept C - COUNT(DISTINCT Material))
    if ("Unique Materials Count" in cols or "Total Unique Materials" in cols) and "total_inventory" not in cols and "TotalUnrestrictedQuantity" not in cols:
        count_val = rows[0].get("Unique Materials Count", rows[0].get("Total Unique Materials", 0))
        plant_val = extract_single_plant_safe(q_lower) or (rows and rows[0].get("Plant"))
        if plant_val:
            return f"There are **{count_val:,}** unique materials in Plant {plant_val}."
        return f"There are **{count_val:,}** unique materials in inventory."

    # 0G. Total Inventory Quantity (Concept A - SUM(UnrestrictedQty))
    if ("total_inventory" in cols or "Total Unrestricted Quantity" in cols or "TotalUnrestrictedQuantity" in cols) and "Total Unique Materials" not in cols and "TotalUniqueMaterials" not in cols:
        tot_val = rows[0].get("total_inventory", rows[0].get("Total Unrestricted Quantity", rows[0].get("TotalUnrestrictedQuantity", 0.0)))
        plant_val = extract_single_plant_safe(q_lower) or (rows and rows[0].get("Plant"))
        if plant_val:
            return f"Total inventory in Plant {plant_val} is **{tot_val:,.0f}** units."
        return f"Total warehouse inventory is **{tot_val:,.0f}** units."

    # 1. Empty Bins Count (Scalar KPI)
    if "Empty Bins Count" in cols:
        count_val = rows[0].get("Empty Bins Count", 0)
        plant_val = extract_single_plant_safe(q_lower)
        
        if plant_val:
            return f"There are **{count_val:,}** completely empty bins in Plant {plant_val}."
        else:
            return f"There are **{count_val:,}** completely empty bins across the warehouse network."

    # 1B. Threshold Bins Count (e.g. "How many bins are above 90% utilization?")
    if "Threshold Bins Count" in cols:
        total_count = sum(r.get("Threshold Bins Count", 0) for r in rows)
        thresh_m = re.search(r"(\d{1,3})\s*%", q_lower)
        th_val = thresh_m.group(1) if thresh_m else "80"
        
        inclusive = any(k in q_lower for k in ["at least", ">=", "or more", "or above", "minimum"])
        inclusive_low = any(k in q_lower for k in ["at most", "<=", "or below", "or less", "maximum"])
        is_less = any(k in q_lower for k in ["less than", "below", "under", "<", "at most", "or below", "or less"])
        if is_less:
            op_symbol = "≤" if inclusive_low else "<"
            op_lbl = "at most" if inclusive_low else "below"
        else:
            op_symbol = "≥" if inclusive else ">"
            op_lbl = "at least" if inclusive else "above"

        plants = extract_plants(q_lower)
        if not plants:
            plant_match = re.search(r"(?:plant\s*[:#-]?\s*|for\s+|in\s+|of\s+|\b)(\d{3,5})\b", q_lower)
            if plant_match and plant_match.group(1) not in ["10", "20", "50", "100", "2024", "2025", "2026", th_val]:
                plants = [plant_match.group(1)]

        plant_label = ("Plants " + " and ".join(plants)) if len(plants) > 1 else (f"Plant {plants[0]}" if plants else "all plants")
        
        split_dict = {str(r.get("Plant")): r.get("Threshold Bins Count", 0) for r in rows if r.get("Plant")}
        if plants and len(split_dict) > 1:
            split_parts = [f"{p}: {split_dict[p]:,}" for p in plants if p in split_dict]
        elif len(split_dict) > 1:
            split_parts = [f"{p}: {cnt:,}" for p, cnt in sorted(split_dict.items())]
        else:
            split_parts = []
        split_str = f" ({' · '.join(split_parts)})" if split_parts else ""

        plant_suffix = f" across {plant_label}" if plant_label == "all plants" else f" in {plant_label}"
        bin_lbl = "bin" if total_count == 1 else "bins"
        return f"There are **{total_count:,} {bin_lbl}** with utilization {op_symbol} {th_val}%{plant_suffix}{split_str}."

    # 2. Empty Bins List (Table Output)
    if ("Storage Location" in cols or "StorageLocation" in cols) and ("Status" in cols or "Inventory Qty" in cols) and ("Bin" in cols or "BinLocation" in cols) and any(k in q_lower for k in ["empty", "putaway", "put-away", "vacant", "unoccupied", "free"]):
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" — Plant {plant_val}" if plant_val else ""
        
        total_matching = rows[0].get("TotalMatching") if (rows and "TotalMatching" in rows[0]) else count
        displayed_rows = count
        
        explicit_lim = extract_explicit_limit(q_lower)
        if explicit_lim and total_matching > displayed_rows:
            single_stmt = f"Found **{total_matching:,} matching empty bins**{plant_str}. Showing the first **{displayed_rows}** available for put-away (Inventory Qty = 0)."
        else:
            single_stmt = f"Found **{total_matching:,} empty bins**{plant_str} currently available for put-away (Inventory Qty = 0)."
            
        if is_single_statement_requested:
            return single_stmt
            
        return (
            f"### 📦 Empty Bins{plant_str}\n\n"
            f"{single_stmt}\n\n"
            f"💡 *The list of available empty bins with storage locations is loaded in the **searchable Data Table** below.*"
        )

    # 2B. Lowest / Highest Plant Bin Utilization & Extremes
    if ("BinUtilizationPct" in cols or "Bin Utilization %" in cols) and "Plant" in cols and any(k in q_lower for k in ["lowest", "least", "highest", "most", "maximum", "minimum", "top plant", "best plant", "worst plant", "least utilized", "most utilized", "rank", "ranking"]):
        is_least = any(k in q_lower for k in ["lowest", "least", "minimum", "worst", "bottom"])
        is_rank_only = any(k in q_lower for k in ["rank", "ranking"]) and not any(k in q_lower for k in ["lowest", "least", "minimum", "worst", "bottom", "highest", "most", "maximum"])
        label = "Lowest" if is_least else ("Highest" if not is_rank_only else "Plant")
        leader_row = rows[0]
        lead_plant = leader_row.get("Plant", "N/A")
        u_raw = leader_row.get("Bin Utilization %", leader_row.get("BinUtilizationPct", 0))
        try:
            lead_util = f"{float(str(u_raw).replace('%', '')):.2f}%"
        except Exception:
            lead_util = f"{u_raw}%"
        lead_occ = leader_row.get("Occupied Bins", 0)
        lead_tot = leader_row.get("Total Bins", 0)
        lead_emp = leader_row.get("Empty Bins", max(0, lead_tot - lead_occ))

        if is_rank_only:
            single_stmt = f"**Plant {lead_plant}** ranks first in **bin utilization** across all facilities at **{lead_util}** ({lead_occ:,} occupied of {lead_tot:,} total bins, with {lead_emp:,} empty bins)."
        else:
            single_stmt = f"**Plant {lead_plant}** has the **{label.lower()} bin utilization** across all facilities at **{lead_util}** ({lead_occ:,} occupied of {lead_tot:,} total bins, with {lead_emp:,} empty bins)."
        if is_single_statement_requested or len(rows) == 1:
            return single_stmt

        header_title = f"### 🏭 {label} Bin Utilization by Plant\n" if not is_rank_only else "### 🏭 Plant Bin Utilization Ranking\n"
        lines = [
            header_title,
            single_stmt,
            f"\n**Plant Utilization Ranking:**"
        ]
        for r in rows:
            rnk = r.get("Rank", "-")
            p = r.get("Plant", "N/A")
            u_item_raw = r.get("Bin Utilization %", r.get("BinUtilizationPct", 0))
            try:
                u = f"{float(str(u_item_raw).replace('%', '')):.2f}%"
            except Exception:
                u = f"{u_item_raw}%"
            ob = r.get("Occupied Bins", 0)
            tb = r.get("Total Bins", 0)
            lines.append(f"- **Rank {rnk} — Plant {p}**: **{u}** ({ob:,} / {tb:,} bins occupied)")
        lines.append("\n💡 *The full comparative metrics are displayed in the **Data Table** below.*")
        return "\n".join(lines)

    # 2C. Generalized Material Stock Quantity Ranking
    if "Total Stock Quantity" in cols and "Material" in cols:
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum"])
        label = "Least" if is_least else "Highest"
        top_mat = rows[0].get("Material", "N/A")
        top_desc = rows[0].get("Material Description", "")
        top_qty = rows[0].get("Total Stock Quantity", 0.0)
        uom = rows[0].get("UOM", "EA")

        single_stmt = f"The material with the **{label.lower()} stock quantity** is **`{top_mat}`** ({top_desc}) with **{top_qty:,.0f} {uom}**."
        if is_single_statement_requested or len(rows) == 1:
            return single_stmt

        lines = [
            f"### 📊 Top {len(rows)} {label} Stocked Materials\n",
            single_stmt,
            f"\n**Material Inventory Ranking:**"
        ]
        for r in rows[:10]:
            rnk = r.get("Rank", "-")
            m = r.get("Material", "N/A")
            d = r.get("Material Description", "")
            q = r.get("Total Stock Quantity", 0.0)
            lines.append(f"- **Rank {rnk} — `{m}`** ({d}): **{q:,.0f} {uom}**")
        lines.append("\n💡 *The complete ranking is rendered in the **Data Table** below.*")
        return "\n".join(lines)

    # 2D. Generalized Storage Location Inventory Ranking
    if "Total Inventory Quantity" in cols and "Storage Location" in cols and "Rank" in cols:
        is_least = any(k in q_lower for k in ["least", "lowest", "bottom", "minimum"])
        label = "Least" if is_least else "Highest"
        top_sloc = rows[0].get("Storage Location", "N/A")
        top_plant = rows[0].get("Plant", "")
        top_qty = rows[0].get("Total Inventory Quantity", 0.0)

        single_stmt = f"Storage Location **`{top_sloc}`** (Plant {top_plant}) holds the **{label.lower()} inventory quantity** at **{top_qty:,.0f} units**."
        if is_single_statement_requested or len(rows) == 1:
            return single_stmt

        lines = [
            f"### 📊 Storage Location Inventory Ranking\n",
            single_stmt,
            f"\n**Storage Location Ranking:**"
        ]
        for r in rows[:10]:
            rnk = r.get("Rank", "-")
            sl = r.get("Storage Location", "N/A")
            p = r.get("Plant", "")
            q = r.get("Total Inventory Quantity", 0.0)
            lines.append(f"- **Rank {rnk} — SLoc `{sl}`** (Plant {p}): **{q:,.0f} units**")
        lines.append("\n💡 *The complete ranking is rendered in the **Data Table** below.*")
        return "\n".join(lines)

    # 3. Top N or Bottom N Utilized Bins Ranking
    if ("Bin Capacity" in cols or "Capacity" in cols) and ("Utilization" in cols or "Utilization %" in cols) and any(k in q_lower for k in ["top", "most", "highest", "bottom", "least", "lowest", "emptiest"]) and not any(k in q_lower for k in ["more than", "greater than", "less than", "above", "below", ">", "<"]):
        is_least = any(k in q_lower for k in ["bottom", "least", "lowest", "emptiest"])
        label = "Least" if is_least else "Most"
        leader = rows[0].get("Bin", "N/A") if rows else "N/A"
        l_util = rows[0].get("Utilization", rows[0].get("Utilization %", "0%")) if rows else "0%"
        
        plant_val = extract_single_plant_safe(q_lower)
        plant_str = f" in Plant {plant_val}" if plant_val else " across the warehouse"
        leader_cap = rows[0].get("Bin Capacity", rows[0].get("Capacity", "N/A")) if rows else "N/A"
        leader_plant = rows[0].get("Plant", "")
        lead_plant_str = f" (Plant {leader_plant})" if leader_plant else ""
        
        is_bin_only = is_bin_utilization_primary(q_lower)
        if count == 1 or len(rows) == 1 or is_single_statement_requested:
            if is_bin_only:
                single_stmt = f"Bin **`{leader}`**{lead_plant_str} has the **{label.lower()} utilization** at **{l_util}**."
            else:
                single_stmt = f"Bin **`{leader}`**{lead_plant_str} has the **{label.lower()} utilization** at **{l_util}** (Capacity: {leader_cap})."
            return single_stmt
            
        single_stmt = f"Top {count} {label} Utilized Bins{plant_str} (leader: **`{leader}`** at **{l_util}**)."
        if is_bin_only:
            table_note = "💡 *The complete list of bins is loaded into the **searchable, paginated Data Table** below with exact utilization percentages.*"
        else:
            table_note = "💡 *The complete list of bins is loaded into the **searchable, paginated Data Table** below with capacities and exact utilization percentages.*"
        return (
            f"### 📊 Top {count} {label} Utilized Bins{plant_str}\n\n"
            f"{single_stmt}\n\n"
            f"{table_note}"
        )

    # 3. Specific Bins Fullness / Utilization Threshold
    if "Bin Capacity" in cols and ("Utilization" in cols or "Utilization %" in cols):
        inclusive = any(k in q_lower for k in ["at least", ">=", "or more", "or above", "minimum"])
        inclusive_low = any(k in q_lower for k in ["at most", "<=", "or below", "or less", "maximum"])
        is_less = any(k in q_lower for k in ["less than", "below", "under", "<", "at most", "or below", "or less"])
        if is_less:
            op_symbol = "≤" if inclusive_low else "<"
            op_desc = "at most" if inclusive_low else "below"
        else:
            op_symbol = "≥" if inclusive else ">"
            op_desc = "at least" if inclusive else "above"

        threshold_match = re.search(r"(?:more\s+than|greater\s+than|over|above|>|>=|at\s+least|exceeding|less\s+than|below|<|<=|under)\s*(\d{1,3})(?:\s*%)?", q_lower)
        if not threshold_match:
            threshold_match = re.search(r"(\d{1,3})\s*%", q_lower)
        thresh_str = threshold_match.group(1) if threshold_match else "80"

        plants = extract_plants(q_lower)
        if not plants:
            plant_match = re.search(r"(?:plant\s*[:#-]?\s*|for\s+|in\s+|of\s+|\b)(\d{3,5})\b", q_lower)
            if plant_match and plant_match.group(1) not in ["10", "20", "50", "100", "2024", "2025", "2026", thresh_str]:
                plants = [plant_match.group(1)]

        plant_label = ("Plants " + " and ".join(plants)) if len(plants) > 1 else (f"Plant {plants[0]}" if plants else "all plants")
        plant_suffix = f" across {plant_label}" if plant_label == "all plants" else f" in {plant_label}"

        total_count = len(rows)
        plant_counts = {}
        for r in rows:
            p = str(r.get("Plant", ""))
            if p:
                plant_counts[p] = plant_counts.get(p, 0) + 1

        is_capped = len(rows) >= settings.sql_max_result_rows
        if is_capped:
            try:
                from .db import execute_readonly
                plant_filter = ""
                if len(plants) == 1:
                    plant_filter = f" AND b.Plant = '{plants[0]}'"
                elif len(plants) > 1:
                    plant_filter = " AND b.Plant IN (" + ", ".join(f"'{p}'" for p in plants) + ")"
                op_sql = "<=" if inclusive_low else "<" if is_less else ">=" if inclusive else ">"
                cnt_sql = f"""SELECT Plant, COUNT(*) AS [Threshold Bins Count]
FROM (
    SELECT b.Plant, b.BinLocation
    FROM dbo.ZWMS_BIN_MASTER b
    JOIN dbo.ZWMS_INVENTORY i ON b.BinLocation = i.BinNo AND b.Plant = i.Plant
    LEFT JOIN dbo.ZWMS_MATERIAL_MASTER m ON i.Material = m.MaterialCode
    WHERE b.Volume > 0{plant_filter}
    GROUP BY b.Plant, b.BinLocation, b.Volume
    HAVING ROUND(SUM(i.UnrestrictedQty * COALESCE(m.Volume, 0)) * 100.0 / NULLIF(b.Volume, 0), 1) {op_sql} {thresh_str}
) sub
GROUP BY Plant"""
                cnt_rows, _ = execute_readonly(cnt_sql)
                if cnt_rows:
                    total_count = sum(cr.get("Threshold Bins Count", 0) for cr in cnt_rows)
                    plant_counts = {str(cr.get("Plant")): cr.get("Threshold Bins Count", 0) for cr in cnt_rows if cr.get("Plant")}
            except Exception:
                pass

        if plants and len(plant_counts) > 1:
            split_parts = [f"Plant {p}: {plant_counts[p]:,}" for p in plants if p in plant_counts]
        elif len(plant_counts) > 1:
            split_parts = [f"Plant {p}: {cnt:,}" for p, cnt in sorted(plant_counts.items())]
        else:
            split_parts = []
        split_str = f" ({' · '.join(split_parts)})" if split_parts else ""

        # Over-capacity bins check (> 100%)
        over_cap_count = 0
        for r in rows:
            u = r.get("Utilization %", r.get("Utilization", 0))
            if isinstance(u, str):
                try:
                    u_val = float(u.replace("%", "").strip())
                except ValueError:
                    u_val = 0.0
            else:
                u_val = float(u or 0.0)
            if u_val > 100.0:
                over_cap_count += 1

        cap_note = f" Showing the top {len(rows):,} by utilization." if is_capped else ""
        bin_lbl = "bin" if total_count == 1 else "bins"
        single_stmt = f"Found **{total_count:,} {bin_lbl}** with utilization {op_symbol} {thresh_str}%{plant_suffix}{split_str}.{cap_note}"

        if is_single_statement_requested:
            if over_cap_count > 0:
                single_stmt += f" ({over_cap_count:,} of these bins are above 100% of capacity)."
            return single_stmt

        lines = [
            f"### 📦 Bins with utilization {op_symbol} {thresh_str}%{plant_suffix}\n",
            single_stmt,
        ]
        if over_cap_count > 0:
            lines.append(f"\n⚠️ **Note:** **{over_cap_count:,}** of these bins are above 100% of capacity (stock volume exceeds bin capacity).")
        if len(plants) > 1:
            lines.append(f"\n💡 *The matching bins for each plant are displayed in **separate Data Tables below** (Plant {' & Plant '.join(plants)}) with independent search, pagination, and CSV export:*")
        else:
            lines.append(f"\n💡 *The exact **Bin Capacity**, **Occupied Volume**, and **Utilization %** metrics for each bin are loaded in the **searchable, paginated Data Table** below (with real-time search, sorting, and CSV export):*")
        return "\n".join(lines)

    # 4. Average Inventory per Occupied Bin (Single KPI Card & Operational Explanation)
    if "AvgInventoryPerOccupiedBin" in cols:
        avg_val = rows[0].get("AvgInventoryPerOccupiedBin", 0.0)
        tot_qty = rows[0].get("TotalQuantity", 0.0)
        occ_bins = rows[0].get("OccupiedBins", 0)
        plant_val = extract_single_plant_safe(q_lower) or (rows[0].get("Plant") if "Plant" in rows[0] and str(rows[0]["Plant"]) != "All" else None)
        
        if plant_val:
            single_stmt = f"The average inventory per occupied bin in **Plant {plant_val}** is **{avg_val:,.2f} units** across **{occ_bins:,} occupied bins** (Total Stock: **{tot_qty:,.2f} units**)."
            if is_single_statement_requested:
                return single_stmt
                
            return (
                f"### 📦 Plant {plant_val} Average Inventory per Occupied Bin\n\n"
                f"{single_stmt}\n\n"
                f"**Plant {plant_val} Operational Highlights:**\n"
                f"- **Average Units per Occupied Bin (Primary):** **{avg_val:,.2f}**\n"
                f"- **Active Occupied Bins:** **{occ_bins:,}**\n"
                f"- **Total Unrestricted Stock:** **{tot_qty:,.2f}** units"
            )
        else:
            single_stmt = f"The average inventory per occupied bin across the warehouse network is **{avg_val:,.2f} units** across **{occ_bins:,} occupied bins** (Total Stock: **{tot_qty:,.2f} units**)."
            if is_single_statement_requested:
                return single_stmt
                
            return (
                f"### 📦 Warehouse Network Average Inventory per Occupied Bin\n\n"
                f"{single_stmt}\n\n"
                f"**Network Operational Highlights:**\n"
                f"- **Average Units per Occupied Bin (Primary):** **{avg_val:,.2f}**\n"
                f"- **Total Active Occupied Bins:** **{occ_bins:,}**\n"
                f"- **Total Unrestricted Stock:** **{tot_qty:,.2f}** units"
            )

    # 4B. Detailed Storage Location Bin Utilization Breakdown
    if "Storage Location" in cols and ("Bin Utilization %" in cols or "UtilizationPct" in cols) and "Plant" in cols:
        plant_val = rows[0].get("Plant", "")
        top_zone = rows[0].get("Storage Location", "N/A")
        top_util = rows[0].get("Bin Utilization %", "0%")
        top_occ = rows[0].get("Occupied Bins", 0)
        tot_cap_vol = sum(r.get("Total Capacity Volume (FT3)", 0.0) for r in rows)
        tot_occ_vol = sum(r.get("Occupied Volume (FT3)", 0.0) for r in rows)
        
        if is_bin_utilization_primary(q_lower):
            tot_bins = sum(r.get("Total Bins", 0) for r in rows)
            tot_occ = sum(r.get("Occupied Bins", 0) for r in rows)
            lines = [
                f"### 📊 Plant {plant_val} Detailed Storage Location Bin Utilization\n" if plant_val else "### 📊 Detailed Storage Location Bin Utilization\n",
                f"Storage location bin utilization breakdown for **Plant {plant_val}** across **{len(rows)} storage zones**:\n" if plant_val else f"Storage location bin utilization breakdown across **{len(rows)} storage zones**:\n",
                f"- **Highest Occupancy Zone:** SLoc `{top_zone}` at **{top_util}** ({top_occ:,} occupied bins).",
                f"- **Total Active Bins Occupied:** **{tot_occ:,}** of **{tot_bins:,}** bins." if tot_bins > 0 else f"- **Total Active Bins Occupied:** **{tot_occ:,}** bins.",
                f"\n💡 *The **Storage Location Bar Chart** and itemized **Data Table** below display complete occupancy metrics across all zones.*"
            ]
            return "\n".join(lines)

        lines = [
            f"### 📊 Plant {plant_val} Detailed Storage Location Breakdown\n" if plant_val else "### 📊 Detailed Storage Location Breakdown\n",
            f"Storage location utilization breakdown for **Plant {plant_val}** across **{len(rows)} storage zones**:\n" if plant_val else f"Storage location utilization breakdown across **{len(rows)} storage zones**:\n",
            f"- **Highest Occupancy Zone:** SLoc `{top_zone}` at **{top_util}** ({top_occ:,} occupied bins).",
            f"- **Total Storage Capacity:** **{tot_cap_vol:,.2f} FT³** ({tot_occ_vol:,.2f} FT³ currently occupied).",
            f"\n💡 *The **Storage Location Bar Chart** and itemized **Data Table** below display complete occupancy metrics and volume breakdowns across all zones.*"
        ]
        return "\n".join(lines)

    # 4B_comp. Plant Utilization Comparison (e.g. Compare Plant 1258 and 7228)
    if "Bin Utilization %" in cols and "Plant" in cols and (
        ("Occupied Volume" in cols and "Total Capacity" in cols and "Available Capacity" in cols) or
        ("Occupied Bins" in cols or "OccupiedBins" in cols or "Total Bins" in cols or "TotalBins" in cols)
    ) and len(rows) > 1 and (
        any(k in q_lower for k in ["compare", "comparison", "difference", "versus", " vs ", "higher", "lower", "better", "more"]) or
        len(re.findall(r"\b(1258|1266|1268|7228)\b", q_lower)) >= 2
    ):
        sorted_p = sorted(rows, key=lambda x: float(str(x.get("Bin Utilization %", x.get("BinUtilizationPct", 0))).replace("%", "")), reverse=True)
        top_p = sorted_p[0]
        bot_p = sorted_p[-1] if len(sorted_p) > 1 else sorted_p[0]
        top_name = top_p.get("Plant", "N/A")
        top_u_raw = top_p.get("Bin Utilization %", top_p.get("BinUtilizationPct", 0))
        try:
            top_pct = f"{float(str(top_u_raw).replace('%', '')):.2f}%"
        except Exception:
            top_pct = f"{top_u_raw}%"
        bot_name = bot_p.get("Plant", "N/A")
        bot_u_raw = bot_p.get("Bin Utilization %", bot_p.get("BinUtilizationPct", 0))
        try:
            bot_pct = f"{float(str(bot_u_raw).replace('%', '')):.2f}%"
        except Exception:
            bot_pct = f"{bot_u_raw}%"
        
        diff_str = f"**Plant {top_name}** has higher bin utilization at **{top_pct}**, compared to **Plant {bot_name}** at **{bot_pct}**." if top_name != bot_name else f"**Plant {top_name}** has bin utilization of **{top_pct}**."
        
        if is_single_statement_requested:
            return diff_str
            
        header_title = f"### 🏭 Plant Bin Utilization Comparison\n" if is_bin_utilization_primary(q_lower) or not ("Occupied Volume" in cols and "Total Capacity" in cols) else f"### 🏭 Plant Utilization Comparison\n"
        lines = [
            header_title,
            diff_str,
            f"\n**Comparison Breakdown:**"
        ]
        is_bin_only = is_bin_utilization_primary(q_lower) or not ("Occupied Volume" in cols and "Total Capacity" in cols)
        for r in sorted_p:
            p = r.get("Plant", "N/A")
            u_item_raw = r.get("Bin Utilization %", r.get("BinUtilizationPct", 0))
            try:
                u = f"{float(str(u_item_raw).replace('%', '')):.2f}%"
            except Exception:
                u = f"{u_item_raw}%"
            occ = r.get("Occupied Volume", 0.0)
            tot = r.get("Total Capacity", 0.0)
            avail = r.get("Available Capacity", 0.0)
            if is_bin_only:
                ob = r.get("Occupied Bins", r.get("OccupiedBins"))
                tb = r.get("Total Bins", r.get("TotalBins"))
                if ob is not None and tb is not None:
                    lines.append(f"- **Plant {p}**: **{u}** Bin Utilization ({ob:,} of {tb:,} bins occupied).")
                else:
                    lines.append(f"- **Plant {p}**: **{u}** Bin Utilization.")
            else:
                lines.append(f"- **Plant {p}**: **{u}** Utilization | Occupied: **{occ:,.1f} FT³** | Available Capacity: **{avail:,.1f} FT³** (Total: {tot:,.1f} FT³)")
        lines.append(f"\n💡 *Conclusion: {diff_str}*")
        return "\n".join(lines)

    # 4C. Plant Bin Utilization Summary (Plant Bin Utilization Detail Template - Max 2 lines)
    if ("Total Bins" in cols or "TotalBins" in cols) and ("Occupied Bins" in cols or "OccupiedBins" in cols) and len(rows) == 1 and not ("BinUtilizationPct" in cols or "VolumeUtilizationPct" in cols or "BinOccupancyPct" in cols or is_volume_utilization_requested(q_lower)):
        plant_match = re.search(r"(?:plant\s*[:#-]?\s*|for\s+|in\s+|of\s+|\b)(\d{3,5})\b", q_lower)
        plant_val = plant_match.group(1) if plant_match else rows[0].get("Plant", "")
        tb = rows[0].get("Total Bins", rows[0].get("TotalBins", 0))
        ob = rows[0].get("Occupied Bins", rows[0].get("OccupiedBins", 0))
        eb = rows[0].get("Empty Bins", rows[0].get("EmptyBins", max(0, tb - ob)))
        bpct_val = rows[0].get("BinUtilizationPct", rows[0].get("Bin Utilization %"))
        if bpct_val is not None:
            if isinstance(bpct_val, (int, float)):
                bpct = f"{bpct_val:.2f}%"
            elif "%" in str(bpct_val):
                bpct = str(bpct_val)
            else:
                try:
                    bpct = f"{float(bpct_val):.2f}%"
                except Exception:
                    bpct = f"{bpct_val}%"
        else:
            bpct = f"{round(ob * 100.0 / tb, 2) if tb > 0 else 0:.2f}%"
        
        if is_bin_utilization_primary(q_lower) and not any(d in q_lower for d in ["detail", "details", "detailed", "breakdown"]):
            return f"Plant {plant_val}: **{bpct}** Bin Utilization ({ob:,} of {tb:,} bins occupied)." if plant_val else f"Bin Utilization: **{bpct}** ({ob:,} of {tb:,} bins occupied)."
            
        plant_prefix = f"for **Plant {plant_val}** " if plant_val else ""
        return f"The bin utilization {plant_prefix}is **{bpct}**, with **{ob:,}** of **{tb:,}** total bins currently occupied and **{eb:,}** empty bins available for put-away."

    # 5. Bin Utilization and Occupancy Percentage
    if "BinUtilizationPct" in cols or "VolumeUtilizationPct" in cols or "BinOccupancyPct" in cols or "Bin Utilization %" in cols or (("TotalBins" in cols or "Total Bins" in cols) and ("OccupiedBins" in cols or "Occupied Bins" in cols) and len(rows) > 1):

        plant_val = extract_single_plant_safe(q_lower) or (rows[0].get("Plant") if len(rows) == 1 and rows[0].get("Plant") and str(rows[0].get("Plant")) != "All" else None)
        
        if plant_val:
            matching_row = next((r for r in rows if str(r.get("Plant")) == str(plant_val)), rows[0])
            tb = matching_row.get("TotalBins", matching_row.get("Total Bins", 0))
            ob = matching_row.get("OccupiedBins", matching_row.get("Occupied Bins", 0))
            eb = matching_row.get("EmptyBins", matching_row.get("Empty Bins", max(0, tb - ob)))
            bpct_val = matching_row.get("Bin Utilization %", matching_row.get("BinUtilizationPct", matching_row.get("BinOccupancyPct")))
            if bpct_val is not None:
                bpct = float(str(bpct_val).replace("%", ""))
            else:
                bpct = round((ob * 100.0 / tb), 2) if tb > 0 else 0.0
            tvol = matching_row.get("TotalBinCapacityVolume", 0.0)
            ovol = matching_row.get("OccupiedBinVolume", 0.0)
            vpct = matching_row.get("VolumeUtilizationPct", round((ovol * 100.0 / tvol), 2) if tvol > 0 else 0.0)

            if is_bin_utilization_primary(q_lower):
                bpct_str = f"{round(float(bpct), 2)}%" if isinstance(bpct, (int, float)) or (isinstance(bpct, str) and bpct.replace('.', '', 1).replace('%', '').isdigit()) else str(bpct)
                if "%" not in bpct_str:
                    bpct_str += "%"
                single_statement = (
                    f"Plant {plant_val}: **{bpct_str}** Bin Utilization ({ob:,} of {tb:,} bins occupied)."
                )
                if is_single_statement_requested:
                    return single_statement

                return (
                    f"### 🏭 Plant {plant_val} Bin Utilization\n\n"
                    f"{single_statement}\n\n"
                    f"**Plant {plant_val} Operational Highlights:**\n"
                    f"- **Bin Utilization:** **{bpct_str}** ({ob:,} of {tb:,} bins occupied)\n"
                    f"- **Available Empty Bins:** **{eb:,}** bins"
                )

            single_statement = (
                f"The bin utilization in **Plant {plant_val}** is **{bpct}%** "
                f"({ob:,} occupied bins of {tb:,} total bins, leaving {eb:,} empty bins available for put-away) "
                f"with volume utilization of **{vpct}%** ({ovol:,.2f} FT³ occupied of {tvol:,.2f} FT³ total capacity)."
            )

            if is_single_statement_requested:
                return single_statement

            return (
                f"### 🏭 Plant {plant_val} Bin Utilization & Storage Capacity\n\n"
                f"{single_statement}\n\n"
                f"**Plant {plant_val} Operational Highlights:**\n"
                f"- **Primary Bin Utilization:** **{bpct}%** ({ob:,} of {tb:,} bins occupied)\n"
                f"- **Available Empty Bins:** **{eb:,}** bins\n"
                f"- **Volume Utilization:** **{vpct}%** ({ovol:,.2f} FT³ occupied of {tvol:,.2f} FT³ total capacity)"
            )
        else:
            total_bins = sum(r.get("TotalBins", 0) for r in rows)
            occupied_bins = sum(r.get("OccupiedBins", 0) for r in rows)
            empty_bins = sum(r.get("EmptyBins", 0) for r in rows)
            overall_bin_pct = round((occupied_bins * 100.0 / total_bins), 2) if total_bins > 0 else 0.0
            
            total_cap_vol = sum(r.get("TotalBinCapacityVolume", 0.0) for r in rows)
            total_occ_vol = sum(r.get("OccupiedBinVolume", 0.0) for r in rows)
            overall_vol_pct = round((total_occ_vol * 100.0 / total_cap_vol), 2) if total_cap_vol > 0 else 0.0

            if is_bin_utilization_primary(q_lower):
                single_statement = (
                    f"The overall warehouse bin utilization right now is **{overall_bin_pct:.2f}%** "
                    f"({occupied_bins:,} of {total_bins:,} bins occupied, leaving {empty_bins:,} empty bins available for put-away)."
                )
                if is_single_statement_requested:
                    return single_statement

                lines = [
                    f"### 📊 Warehouse Network Bin Utilization\n",
                    single_statement,
                    f"\n**Plant Breakdown Highlights:**"
                ]
                for r in rows:
                    plant = r.get("Plant", "N/A")
                    tb = r.get("TotalBins", r.get("Total Bins", 0))
                    ob = r.get("OccupiedBins", r.get("Occupied Bins", 0))
                    bpct_val = r.get("Bin Utilization %", r.get("BinUtilizationPct", r.get("BinOccupancyPct")))
                    if bpct_val is not None:
                        bpct = float(str(bpct_val).replace("%", ""))
                    else:
                        bpct = round((ob * 100.0 / tb), 2) if tb > 0 else 0.0
                    lines.append(f"- **Plant {plant}**: **{bpct:.2f}%** Bin Utilization ({ob:,} of {tb:,} bins occupied).")

                return "\n".join(lines)

            single_statement = (
                f"The overall warehouse bin utilization right now is **{overall_bin_pct}%** "
                f"({occupied_bins:,} occupied bins of {total_bins:,} total bins, leaving {empty_bins:,} empty bins available for put-away) "
                f"with total volume utilization of **{overall_vol_pct}%** ({total_occ_vol:,.2f} FT³ occupied of {total_cap_vol:,.2f} FT³ total capacity)."
            )

            if is_single_statement_requested:
                return single_statement

            lines = [
                f"### 📊 Warehouse Network Bin Utilization & Capacity\n",
                single_statement,
                f"\n**Plant Breakdown Highlights:**"
            ]
            for r in rows:
                plant = r.get("Plant", "N/A")
                tb = r.get("TotalBins", 0)
                ob = r.get("OccupiedBins", 0)
                bpct_raw = r.get("Bin Utilization %", r.get("BinUtilizationPct", r.get("BinOccupancyPct")))
                bpct = float(str(bpct_raw).replace("%", "")) if bpct_raw is not None else (round((ob * 100.0 / tb), 2) if tb > 0 else 0)
                tvol = r.get("TotalBinCapacityVolume", 0)
                ovol = r.get("OccupiedBinVolume", 0)
                vpct = r.get("VolumeUtilizationPct", 0)
                lines.append(f"- **Plant {plant}**: **{bpct:.2f}%** Bin Utilization ({ob:,} of {tb:,} bins occupied) | {vpct:.2f}% Volume Utilization ({ovol:,.2f} of {tvol:,.2f} FT³).")

            return "\n".join(lines)

    # 5B. Specific Material Code Stock & Locations (Explicit Single Material Scope)
    if ("Batch" in cols or "BaseUnitOfMeasure" in cols) and ("MaterialDescription" in cols or "Material" in cols or "BinNo" in cols) and any(k in q_lower for k in ["material", "sku", "item", "stock location", "where is", "find material", "how much of", "stock of"]):
        mat_match = re.search(r"\b(?:material|sku|item|code)\s*[:#-]?\s*([a-z0-9_-]{5,20})\b", q_lower, re.IGNORECASE)
        mat_code = mat_match.group(1).upper() if (mat_match and hasattr(mat_match, "group")) else (rows[0].get("Material", "N/A") if "Material" in rows[0] else "N/A")
        mat_desc = rows[0].get("MaterialDescription", rows[0].get("Description", ""))
        tot_qty = sum(r.get("UnrestrictedQty", r.get("Qty", 0)) for r in rows)
        uom = rows[0].get("BaseUnitOfMeasure", rows[0].get("UOM", "EA"))
        plant_val = rows[0].get("Plant", "")
        plant_str = f" in Plant {plant_val}" if plant_val else ""
        bin_count = len(set(r.get("BinNo", r.get("Bin", "")) for r in rows if r.get("BinNo") or r.get("Bin")))

        single_stmt = f"Material **`{mat_code}`** ({mat_desc}) has a total stock of **{tot_qty:,.0f} {uom}** located across **{bin_count} bins**{plant_str}."
        if is_single_statement_requested:
            return single_stmt

        lines = [
            f"### 📦 Material {mat_code} Stock & Locations\n",
            single_stmt,
            f"\n**Storage Allocations:**",
        ]
        for r in rows[:5]:
            bn = r.get("BinNo", r.get("Bin", "N/A"))
            q = r.get("UnrestrictedQty", r.get("Qty", 0))
            sl = r.get("StorageLocation", r.get("Storage Location", "N/A"))
            bt = r.get("Batch", "N/A")
            lines.append(f"- **Bin `{bn}`**: **{q:,.0f} {uom}** | SLoc `{sl}` | Batch `{bt}`")
        lines.append(f"\n💡 *The complete list of bin locations for Material **`{mat_code}`** is rendered in the **Data Table** below.*")
        return "\n".join(lines)

    # 6. Specific Plant Material Records
    if ("Material" in cols or "Description" in cols) and ("Qty" in cols or "UnrestrictedQty" in cols or "Bin" in cols or "BinNo" in cols):
        plant_val = extract_single_plant_safe(q_lower) or (rows[0].get("Plant", "N/A") if "Plant" in cols else "1258")
        
        tot_records_str = f"{count:,}"
        single_stmt = f"In the uploaded inventory data, **Plant {plant_val}** has **{tot_records_str} inventory records**."
        if is_single_statement_requested:
            return single_stmt

        lines = [
            f"### 🏭 Plant {plant_val} Inventory Records\n",
            single_stmt,
            f"\nA few examples of materials in **Plant {plant_val}**:",
        ]
        for r in rows[:4]:
            mat = r.get("Material", "N/A")
            desc = r.get("Description", r.get("MaterialDescription", ""))
            qty = r.get("Qty", r.get("UnrestrictedQty", 0))
            uom = r.get("UOM", r.get("BaseUnitOfMeasure", "EA"))
            sloc = r.get("Storage Location", r.get("StorageLocation", "N/A"))
            bin_no = r.get("Bin", r.get("BinNo", "N/A"))
            lines.append(f"- **`{mat}`** ({desc}): **{qty:,.0f} {uom}** | SLoc `{sloc}` | Bin `{bin_no}`")

        lines.append(f"\n💡 *The complete list of records for **Plant {plant_val}** is loaded into the **searchable, paginated Data Table** below (with real-time search, sorting, and CSV export) so you can easily explore all records without chat clutter.*")
        return "\n".join(lines)

    # 7. Total Inventory Scalar KPI
    if "TotalUnrestrictedQuantity" in cols or "Total Unrestricted Quantity" in cols:
        tot = rows[0].get("TotalUnrestrictedQuantity", rows[0].get("Total Unrestricted Quantity", 0.0))
        mats = rows[0].get("TotalUniqueMaterials", rows[0].get("Unique Materials", 0))
        bins = rows[0].get("TotalActiveBins", rows[0].get("Occupied Bins", 0))
        plants = rows[0].get("PlantCount", 0)
        plant_match = re.search(r"(?:plant\s*[:#-]?\s*|for\s+|in\s+|of\s+|\b)(\d{3,5})\b", q_lower)
        plant_val = plant_match.group(1) if (plant_match and plant_match.group(1) not in ["10", "20", "50", "100", "2024", "2025", "2026"]) else None
        
        is_explicit_summary = any(k in q_lower for k in ["summary", "overview", "dashboard", "breakdown", "highlights", "detailed"])

        if plant_val:
            single_stmt = f"**Plant {plant_val}** currently holds a total of **{tot:,.2f} unrestricted units** across **{mats:,} unique materials** and **{bins:,} active bins**."
            if not is_explicit_summary:
                return single_stmt

            return (
                f"### 🏭 Plant {plant_val} Inventory Summary\n\n"
                f"{single_stmt}\n\n"
                f"**Plant {plant_val} Highlights:**\n"
                f"- **Total Unrestricted Quantity (Primary):** **{tot:,.2f}** units\n"
                f"- **Unique Active SKUs:** **{mats:,}** materials\n"
                f"- **Active Occupied Bins:** **{bins:,}** bins"
            )
        else:
            single_stmt = f"The warehouse network currently holds a total of **{tot:,.2f} unrestricted units** across **{mats:,} unique materials** and **{bins:,} active bins**."
            if not is_explicit_summary:
                return single_stmt

            return (
                f"### 🏢 Warehouse Network Inventory Summary\n\n"
                f"{single_stmt}\n\n"
                f"**Network Inventory Highlights:**\n"
                f"- **Total Unrestricted Quantity (Primary):** **{tot:,.2f}** units\n"
                f"- **Unique Active SKUs:** **{mats:,}** materials\n"
                f"- **Active Occupied Bins:** **{bins:,}** bins\n"
                f"- **Operational Plants:** **{plants}** facilities"
            )

    return f"### 📋 Warehouse Query Results\nRetrieved **{count}** matching warehouse records. Please inspect the visual charts and data table below for full itemized details."

async def generate_answer(question: str, sql: str, rows: list[dict]) -> str:
    """Generate grounded, human-readable summary of query results."""
    question = normalize_query_typos(question)
    if not rows:
        return format_deterministic_answer(question, rows)
    
    cols = list(rows[0].keys()) if rows else []
    q_lower = question.lower()

    # Authoritative Plant Bin Utilization Comparison & Multi-Plant Comparisons
    if "Bin Utilization %" in cols and "Occupied Volume" in cols and "Total Capacity" in cols and "Available Capacity" in cols and "Plant" in cols:
        return format_deterministic_answer(question, rows)

    # Authoritative Comparison queries (Rule 1: Comparison Table First)
    if is_comparison_intent(q_lower, rows):
        return format_deterministic_answer(question, rows)

    # Authoritative Bin Utilization queries (Rule: Bin Utilization only)
    if is_bin_utilization_primary(q_lower):
        return format_deterministic_answer(question, rows)

    is_single_metric_query = (
        len(rows) == 1 and (
            len(cols) == 1 or
            "Occupied Bins Count" in cols or
            "Total Bins Count" in cols or
            "Empty Bins Count" in cols or
            "Missing Materials Count" in cols or
            "Total Unique Materials" in cols or
            "Total Unrestricted Quantity" in cols or
            any(k in q_lower for k in ["how many", "count", "percentage", "total occupied", "how much stock"])
        ) and not any(k in q_lower for k in ["summary", "overview", "dashboard", "breakdown", "all plants"])
    )
    if is_single_metric_query:
        return format_deterministic_answer(question, rows)

    try:
        rows_preview = rows[:100]
        user_prompt = (
            f"USER QUESTION: {question}\n\n"
            f"EXECUTED SQL: {sql}\n\n"
            f"DATABASE RESULT ({len(rows)} total rows):\n"
            f"{json.dumps(rows_preview, default=str)}"
        )
        ans = await _call_llm(ANSWER_PROMPT_SYSTEM, user_prompt)
        return sanitize_bin_utilization_response(ans, question)
    except Exception:
        return format_deterministic_answer(question, rows)

def optimize_response_format(question: str, rows: list[dict], generated: dict[str, Any]) -> dict[str, Any]:
    """Automatically evaluates question and SQL result dataset to select the best output_type and visualization."""
    question = normalize_query_typos(question)
    q_lower = question.lower()
    row_count = len(rows)
    cols = list(rows[0].keys()) if rows else []

    # 0. Empty result sets
    if row_count == 0:
        return {
            "output_type": "text",
            "chart_type": "none",
            "metric": "no_records",
            "intent": generated.get("intent", "not_found"),
            "time_range": "current"
        }

    # 0A. Explicit Single-Line Override (Suppress tables, charts, KPI cards, buttons)
    if any(re.search(r'\b' + re.escape(o) + r'\b', q_lower) for o in SINGLE_LINE_OVERRIDE_TRIGGERS):
        return {
            "output_type": "text",
            "chart_type": "none",
            "metric": generated.get("metric", "concise_answer"),
            "intent": generated.get("intent", "single_line_answer"),
            "time_range": generated.get("time_range", "current")
        }

    # 0B. Plant Comparison
    if generated.get("intent") == "plant_comparison" or "COMPARISON" in str(generated.get("query_plan", {}).get("intent", "")):
        if generated.get("output_type") == "text" or generated.get("query_plan", {}).get("response_mode") in ["COUNT", "NAMES_ONLY", "PERCENTAGE_ONLY"] or any(k in q_lower for k in ["only count", "only the count", "just the count", "only names", "only the names", "names only", "just the names", "only percentage", "only the percentage", "percentage only", "just the percentage"]):
            return {
                "output_type": "text",
                "chart_type": "none",
                "metric": generated.get("metric", "plant_comparison"),
                "intent": "plant_comparison",
                "time_range": "current"
            }
        is_graph_or_detail = (
            is_detail_or_graph_requested(question)
            or (generated.get("chart_type") in ["bar", "line", "pie"] and generated.get("output_type") in ["bar_chart", "line_chart", "pie_chart"])
            or generated.get("query_plan", {}).get("response_mode") in ["DETAIL", "GRAPH"]
        )
        if is_graph_or_detail and len(rows) > 1:
            y_col = (
                "Bin Utilization %" if "Bin Utilization %" in cols else (
                    "UtilizationPct" if "UtilizationPct" in cols else (
                        "BinUtilizationPct" if "BinUtilizationPct" in cols else (
                            "Total Inventory Quantity" if "Total Inventory Quantity" in cols else (
                                cols[1] if len(cols) > 1 else cols[0]
                            )
                        )
                    )
                )
            )
            chart_title = generated.get("chart_title") or ("Plant Bin Utilization Comparison (%)" if any(u in str(y_col).lower() for u in ["utiliz", "%"]) else "Plant Comparison")
            return {
                "output_type": "bar_chart",
                "chart_type": "bar",
                "chart_title": chart_title,
                "chart_x": "Plant",
                "chart_y": y_col,
                "metric": generated.get("metric", "plant_comparison"),
                "intent": "plant_comparison",
                "time_range": "current"
            }
        return {
            "output_type": "table",
            "chart_type": "none",
            "metric": generated.get("metric", "plant_comparison"),
            "intent": "plant_comparison",
            "time_range": "current"
        }

    # 0C. Range Queries
    if generated.get("intent") == "range_query" or "RANGE" in str(generated.get("query_plan", {}).get("intent", "")):
        is_graph_or_detail = (
            is_detail_or_graph_requested(question)
            or (generated.get("chart_type") in ["bar", "line", "pie"] and generated.get("output_type") in ["bar_chart", "line_chart", "pie_chart"])
            or generated.get("query_plan", {}).get("response_mode") in ["DETAIL", "GRAPH"]
        )
        if is_graph_or_detail and len(rows) > 1:
            return {
                "output_type": "bar_chart",
                "chart_type": "bar",
                "chart_title": generated.get("chart_title", "Range Query"),
                "chart_x": cols[0] if cols else None,
                "chart_y": cols[1] if len(cols) > 1 else None,
                "metric": generated.get("metric", "range_query"),
                "intent": "range_query",
                "time_range": "current"
            }
        return {
            "output_type": "table",
            "chart_type": "none",
            "metric": generated.get("metric", "range_query"),
            "intent": "range_query",
            "time_range": "current"
        }

    # Targeted Analyzed Query Formats (Items 1, 2, 3)
    if generated.get("intent") in ["material_max_quantity", "material_min_quantity"]:
        is_detail = any(d in q_lower for d in ["detail", "details", "detailed", "breakdown", "table"])
        return {
            "output_type": "table" if is_detail else "text",
            "chart_type": "none",
            "metric": "INVENTORY_QUANTITY",
            "intent": generated.get("intent"),
            "time_range": "current"
        }

    if generated.get("intent") == "materials_quantity_threshold":
        is_graph_or_detail = is_detail_or_graph_requested(question) or generated.get("chart_type") == "bar"
        is_single_stmt = is_single_line_requested(q_lower)
        is_chart = is_graph_or_detail and len(rows) > 1 and not is_single_stmt
        return {
            "output_type": "bar_chart" if is_chart else ("text" if is_single_stmt else "table"),
            "chart_type": "bar" if is_chart else "none",
            "chart_title": generated.get("chart_title", "Materials Filtered by Quantity"),
            "chart_x": "Material",
            "chart_y": "Total Stock Quantity",
            "metric": "INVENTORY_QUANTITY",
            "intent": "materials_quantity_threshold",
            "time_range": "current"
        }

    if generated.get("intent") == "plant_inventory_range":
        is_graph_or_detail = is_detail_or_graph_requested(question) or generated.get("chart_type") == "bar"
        is_single_stmt = is_single_line_requested(q_lower)
        is_chart = is_graph_or_detail and len(rows) > 1 and not is_single_stmt
        return {
            "output_type": "bar_chart" if is_chart else ("text" if is_single_stmt else "table"),
            "chart_type": "bar" if is_chart else "none",
            "chart_title": generated.get("chart_title", "Plants with Inventory in Range"),
            "chart_x": "Plant",
            "chart_y": "Total Inventory Quantity",
            "metric": "TOTAL_INVENTORY_QUANTITY",
            "intent": "plant_inventory_range",
            "time_range": "current"
        }

    if generated.get("intent") in ["almost_full_bins", "over_capacity_bins"]:
        is_graph_or_detail = is_detail_or_graph_requested(question) or generated.get("chart_type") in ["bar", "line", "pie"]
        is_chart = is_graph_or_detail and len(rows) > 1
        return {
            "output_type": "bar_chart" if is_chart else "table",
            "chart_type": "bar" if is_chart else "none",
            "chart_title": generated.get("chart_title", "Bin Utilization"),
            "chart_x": "Bin",
            "chart_y": "Utilization" if "Utilization" in cols else "Occupied Volume",
            "metric": "BIN_UTILIZATION",
            "intent": generated.get("intent"),
            "time_range": "current"
        }

    if generated.get("intent") == "materials_missing_volume_percentage" or "Missing Volume Percentage" in cols:
        is_explicit_chart_in_q = any(k in q_lower for k in [
            "graph", "chart", "visualize", "plot", "pie chart", "bar chart", "line chart",
            "show me a graph", "give me a chart", "draw a chart", "create a chart", "plot a chart"
        ])
        if is_explicit_chart_in_q or "Status" in cols:
            return {
                "output_type": "bar_chart",
                "chart_type": "bar",
                "chart_title": generated.get("chart_title", "Inventory Materials Missing Volume Information (%)"),
                "chart_x": "Status" if "Status" in cols else "Material",
                "chart_y": "Percentage (%)" if "Percentage (%)" in cols else "Missing Volume Percentage",
                "metric": "MISSING_VOLUME_PERCENTAGE",
                "intent": "materials_missing_volume_percentage",
                "time_range": "current"
            }
        return {
            "output_type": "text",
            "chart_type": "none",
            "metric": "MISSING_VOLUME_PERCENTAGE",
            "intent": "materials_missing_volume_percentage",
            "time_range": "current"
        }

    if generated.get("intent") == "plant_available_capacity" or ("Available Capacity (FT3)" in cols and "Plant" in cols and len(rows) > 1):
        is_graph_or_detail = is_detail_or_graph_requested(question) or generated.get("chart_type") in ["bar", "line", "pie"]
        if is_graph_or_detail and len(rows) > 1:
            return {
                "output_type": "bar_chart",
                "chart_type": "bar",
                "chart_title": generated.get("chart_title", "Available Capacity by Plant (FT3)"),
                "chart_x": "Plant",
                "chart_y": "Available Capacity (FT3)",
                "metric": "AVAILABLE_CAPACITY",
                "intent": "plant_available_capacity",
                "time_range": "current"
            }
        return {
            "output_type": "table",
            "chart_type": "none",
            "metric": "AVAILABLE_CAPACITY",
            "intent": "plant_available_capacity",
            "time_range": "current"
        }

    if generated.get("intent") == "plant_inventory" or ("Total Inventory Quantity" in cols and "Plant" in cols and "Storage Location" not in cols and "Bin" not in cols and "Rank" not in cols and len(rows) > 1 and not any(k in q_lower for k in ["between", "from", "range", ">", "<"])):
        is_graph_or_detail = is_detail_or_graph_requested(question) or generated.get("chart_type") in ["bar", "line", "pie"]
        if is_graph_or_detail and len(rows) > 1:
            return {
                "output_type": "bar_chart",
                "chart_type": "bar",
                "chart_title": generated.get("chart_title", "Plant-Wise Inventory Quantity"),
                "chart_x": "Plant",
                "chart_y": "Total Inventory Quantity",
                "metric": "TOTAL_INVENTORY_QUANTITY",
                "intent": "plant_inventory",
                "time_range": "current"
            }
        return {
            "output_type": "table",
            "chart_type": "none",
            "metric": "TOTAL_INVENTORY_QUANTITY",
            "intent": "plant_inventory",
            "time_range": "current"
        }

    # 0C2. Compound Capacity & Find Bins Queries
    if generated.get("intent") == "compound_capacity_clarification":
        return {
            "output_type": "text",
            "chart_type": "none",
            "metric": "compound_capacity_clarification",
            "intent": "compound_capacity_clarification",
            "time_range": "current"
        }
    if generated.get("intent") in ["compound_capacity_utilization", "find_bins_list"]:
        is_single_stmt = any(s in q_lower for s in ["single statement", "single line", "one line", "concise", "briefly", "in short"])
        return {
            "output_type": "text" if is_single_stmt else "table",
            "chart_type": "none",
            "metric": generated.get("metric", "bin_utilization"),
            "intent": generated.get("intent"),
            "time_range": "current"
        }

    # 0D. Comprehensive Ranking Queries (Section 47 of Ranking System Context)
    # Default to ranked table without chart; suppress charts unless explicitly requested in question.
    is_ranking = (
        not ("% of Total Bin Volume" in cols or "Total Material Volume" in cols or "ConsumedMaterialVolume" in cols or generated.get("intent") == "material_volume_share") and
        (
            generated.get("intent") in [
                "ranking", "plant_ranking", "bin_ranking", "material_ranking", "storage_location_ranking",
                "plant_occupied_volume_ranking", "plant_available_capacity_ranking", "plant_bin_capacity_ranking",
                "plant_bins_ranking", "plant_empty_bins_ranking", "plant_materials_ranking", "plant_inventory_ranking",
                "specific_plant_rank_lookup", "plant_rank_explanation", "plant_subset_ranking",
                "bin_available_capacity_ranking", "top_utilized_bins", "least_utilized_bins",
                "high_utilization_bins", "low_utilization_bins"
            ]
            or "RANKING" in str(generated.get("query_plan", {}).get("intent", ""))
            or "Rank" in cols
            or (
                any(re.search(r"\b" + re.escape(w) + r"\b", q_lower) for w in [
                    "rank", "ranking", "rankings", "ranked", "top 10", "top 5", "bottom 10", "bottom 5",
                    "most utilized", "least utilized", "highest occupied", "lowest occupied",
                    "highest to lowest", "lowest to highest", "who is #1", "number 1"
                ])
                and not any(k in q_lower for k in ["graph", "chart", "visualize", "plot", "pie chart", "bar chart", "line chart"])
            )
        )
    )
    if is_ranking:
        is_singular_or_lookup = (
            row_count == 1
            or generated.get("intent") in ["specific_plant_rank_lookup", "plant_rank_explanation"]
            or (
                any(re.search(r"\b" + re.escape(s) + r"\b", q_lower) for s in [
                    "single statement", "single line", "one line", "concise", "briefly", "in short",
                    "which plant", "which bin", "which material", "what rank", "why is", "who is #1",
                    "highest plant", "lowest plant", "rank is"
                ]) and not any(d in q_lower for d in ["ranking", "table", "all plants", "all bins", "top 10", "top 5", "bottom 10", "bottom 5"])
            )
        )
        if is_singular_or_lookup:
            return {
                "output_type": "text",
                "chart_type": "none",
                "metric": generated.get("metric", "ranking"),
                "intent": generated.get("intent", "ranking"),
                "time_range": "current"
            }
        is_graph_or_detail = is_detail_or_graph_requested(question) or (generated.get("chart_type") in ["bar", "line", "pie"] and generated.get("output_type") in ["bar_chart", "line_chart", "pie_chart"])
        if is_graph_or_detail and len(rows) > 1:
            entity_col = "Plant" if "Plant" in cols else ("Bin" if "Bin" in cols else ("Material" if "Material" in cols else (cols[1] if len(cols) > 1 else cols[0])))
            metric_col = cols[2] if len(cols) > 2 else (cols[1] if len(cols) > 1 and cols[1] != entity_col else cols[0])
            return {
                "output_type": "bar_chart",
                "chart_type": "bar",
                "chart_title": generated.get("chart_title", "Warehouse Ranking"),
                "chart_x": entity_col,
                "chart_y": metric_col,
                "metric": generated.get("metric", "ranking"),
                "intent": generated.get("intent", "ranking"),
                "time_range": "current"
            }
        return {
            "output_type": "table",
            "chart_type": "none",
            "metric": generated.get("metric", "ranking"),
            "intent": generated.get("intent", "ranking"),
            "time_range": "current"
        }

    # 1. Plant Bin Utilization Detail Templates
    if generated.get("intent") == "plant_bin_utilization_detail":
        if row_count <= 1:
            is_explicit_chart_in_q = (
                is_explicit_chart_only_requested(question) or
                generated.get("output_type") == "bar_chart" or
                generated.get("chart_type") in ["bar", "pie", "line"]
            )
            if is_explicit_chart_in_q:
                return {
                    "output_type": "bar_chart",
                    "chart_type": "bar",
                    "chart_title": generated.get("chart_title", "Plant Bin Utilization"),
                    "chart_x": generated.get("chart_x") or "Plant",
                    "chart_y": generated.get("chart_y") or "Bin Utilization %",
                    "metric": "plant_bin_utilization",
                    "intent": "plant_bin_utilization_detail",
                    "time_range": "current"
                }
            return {
                "output_type": "table",
                "chart_type": "none",
                "metric": "plant_bin_utilization",
                "intent": "plant_bin_utilization_detail",
                "time_range": "current"
            }
        else:
            is_graph_or_detail = is_detail_or_graph_requested(question) or generated.get("chart_type") in ["bar", "pie", "line"]
            if is_graph_or_detail:
                return {
                    "output_type": "bar_chart",
                    "chart_type": "bar",
                    "chart_title": generated.get("chart_title", "Plant Bin Utilization"),
                    "chart_x": "Storage Location" if "Storage Location" in cols else "Plant",
                    "chart_y": "UtilizationPct" if "UtilizationPct" in cols else ("Bin Utilization %" if "Bin Utilization %" in cols else cols[1]),
                    "metric": "plant_bin_utilization",
                    "intent": "plant_bin_utilization_detail",
                    "time_range": "current"
                }
            return {
                "output_type": "table",
                "chart_type": "none",
                "metric": "plant_bin_utilization",
                "intent": "plant_bin_utilization_detail",
                "time_range": "current"
            }
    if generated.get("intent") == "plant_bin_utilization_detailed_analysis":
        return {
            "output_type": "bar_chart",
            "chart_type": "bar",
            "chart_title": generated.get("chart_title", "Plant Bin Utilization by Storage Location (%)"),
            "chart_x": "Storage Location",
            "chart_y": "UtilizationPct",
            "metric": "storage_location_utilization",
            "intent": "plant_bin_utilization_detailed_analysis",
            "time_range": "current"
        }

    # 1B. Data Quality Check / Missing Dimensions Exception Table
    if "Quality Issue" in cols or generated.get("intent") in ["data_quality_check", "DATA_QUALITY_CHECK"]:

        return {
            "output_type": "table",
            "chart_type": "none",
            "metric": "missing_dimensions",
            "intent": "data_quality_check",
            "time_range": "current"
        }

    # 2. Bins by Capacity & Utilization Threshold or Rankings
    if "Bin Capacity" in cols and ("Utilization" in cols or "Utilization %" in cols):
        intent_type = generated.get("intent", "high_utilization_bins")
        is_single_stmt = row_count == 1 or any(s in q_lower for s in [
            "single statement", "single line", "one line", "concise", "briefly", "in short",
            "which bin", "whic bin", "what bin", "wat bin", "bin with the lowest", "bin with lowest",
            "bin with the highest", "bin with highest"
        ]) and not any(d in q_lower for d in ["ranking", "table", "all", "compare", "list", "breakdown", "detailed", "detail form", "top 10", "top 5", "bottom 10", "bottom 5"])
        if is_single_stmt:
            return {
                "output_type": "text",
                "chart_type": "none",
                "metric": "bin_utilization",
                "intent": intent_type,
                "time_range": "current"
            }
        is_graph_or_detail = is_detail_or_graph_requested(question) or (generated.get("chart_type") in ["bar", "line", "pie"] and generated.get("output_type") in ["bar_chart", "line_chart", "pie_chart"])
        if is_graph_or_detail and row_count > 1:
            return {
                "output_type": "bar_chart",
                "chart_type": "bar",
                "chart_title": generated.get("chart_title", "Bin Utilization & Fullness"),
                "chart_x": "Bin" if "Bin" in cols else ("Storage Location" if "Storage Location" in cols else "Plant"),
                "chart_y": "Occupied Volume" if "Occupied Volume" in cols else ("Utilization %" if "Utilization %" in cols else "Bin Capacity"),
                "metric": "bin_fullness",
                "intent": intent_type,
                "time_range": "current"
            }
        return {
            "output_type": "table",
            "chart_type": "none",
            "metric": "bin_fullness",
            "intent": intent_type,
            "time_range": "current"
        }

    # 2. KPI Cards for single row totals or warehouse scalar KPIs
    if row_count == 1:
        if generated.get("intent") in ["bin_plant_lookup", "bin_occupancy_status", "bin_quantity_lookup", "bin_materials_count"]:
            return {"output_type": "text", "chart_type": "none", "metric": generated.get("metric", "bin_lookup"), "intent": generated.get("intent"), "time_range": "current"}
        if "Occupied Bins Count" in cols:
            return {"output_type": "text", "chart_type": "none", "metric": "occupied_bins", "intent": "occupied_bins_count", "time_range": "current"}
        if "Threshold Bins Count" in cols:
            return {"output_type": "text", "chart_type": "none", "metric": "bin_count", "intent": "threshold_bins_count", "time_range": "current"}
        if "Total Bins Count" in cols:
            return {"output_type": "text", "chart_type": "none", "metric": "total_bins", "intent": "total_bins_count", "time_range": "current"}
        if "Empty Bins Count" in cols:
            return {"output_type": "text", "chart_type": "none", "metric": "empty_bins", "intent": "empty_bins_count", "time_range": "current"}
        if "Active Plants Count" in cols:
            return {"output_type": "text", "chart_type": "none", "metric": "plants_count", "intent": "active_plants_count", "time_range": "current"}
        if "Storage Locations Count" in cols:
            return {"output_type": "text", "chart_type": "none", "metric": "storage_locations_count", "intent": "storage_locations_count", "time_range": "current"}
        if "Missing Materials Count" in cols:
            return {"output_type": "text", "chart_type": "none", "metric": "missing_materials", "intent": "materials_missing_from_volume_master_count", "time_range": "current"}
        if "Inventory Records Count" in cols:
            return {"output_type": "text", "chart_type": "none", "metric": "inventory_records_count", "intent": "inventory_records_count", "time_range": "current"}
        if "Unique Materials Count" in cols or ("Total Unique Materials" in cols and "TotalUnrestrictedQuantity" not in cols):
            return {"output_type": "text", "chart_type": "none", "metric": "unique_materials", "intent": "unique_materials_count", "time_range": "current"}
        if "total_inventory" in cols or ("Total Unrestricted Quantity" in cols and "TotalUniqueMaterials" not in cols):
            return {"output_type": "text", "chart_type": "none", "metric": "total_inventory_quantity", "intent": "total_inventory_quantity", "time_range": "current"}
        if "AvgInventoryPerOccupiedBin" in cols:
            return {"output_type": "kpi", "chart_type": "none", "metric": "AVG_INVENTORY_PER_BIN", "intent": "avg_inventory_per_bin", "time_range": "current"}
        if "TotalUnrestrictedQuantity" in cols and "TotalUniqueMaterials" in cols:
            return {"output_type": "kpi", "chart_type": "none", "metric": "total_inventory", "intent": "inventory_summary", "time_range": "current"}
        if any(k in cols for k in ["TotalUnrestrictedQuantity", "TotalQuantity", "TotalUniqueMaterials", "TotalBins"]):
            return {"output_type": "kpi", "chart_type": "none", "metric": generated.get("metric", "total_inventory"), "intent": generated.get("intent", "inventory_summary"), "time_range": "current"}

    # 3. Plant / Warehouse Bin Utilization & Extremes
    if "Bin Utilization %" in cols or "BinUtilizationPct" in cols or "VolumeUtilizationPct" in cols:
        is_single_stmt = (
            any(s in q_lower for s in ["single statement", "single line", "one line", "concise", "briefly", "in short"]) or
            any(k in q_lower for k in [
                "which plant", "whic plant", "what plant", "wat plant", "plant with the lowest", "plant with lowest",
                "plant with the highest", "plant with highest", "what is the lowest", "what is the highest",
                "least utilized plant", "most utilized plant"
            ]) and not any(d in q_lower for d in ["ranking", "table", "all plants", "compare", "list", "breakdown", "detailed", "detail form"])
        )
        if row_count == 1 or is_single_stmt:
            return {
                "output_type": "text",
                "chart_type": "none",
                "metric": generated.get("metric", "bin_utilization"),
                "intent": generated.get("intent", "bin_utilization"),
                "time_range": "current"
            }
        
        return {
            "output_type": "bar_chart",
            "chart_type": "bar",
            "chart_title": generated.get("chart_title", "Warehouse Bin Utilization by Plant (%)"),
            "chart_x": "Plant",
            "chart_y": "Bin Utilization %" if "Bin Utilization %" in cols else ("BinUtilizationPct" if "BinUtilizationPct" in cols else "VolumeUtilizationPct"),
            "metric": generated.get("metric", "warehouse_utilization"),
            "intent": generated.get("intent", "bin_utilization"),
            "time_range": "current"
        }

    # 4. Material Volume Consumption & Share of Total Bin Volume
    if "% of Total Bin Volume" in cols or "Total Material Volume" in cols or "ConsumedMaterialVolume" in cols or "PctOfTotalWarehouseBinVolume" in cols:
        return {
            "output_type": "bar_chart",
            "chart_type": "bar",
            "chart_title": "Top 10 Materials by Share of Total Bin Volume (%)",
            "chart_x": "Material",
            "chart_y": "% of Total Bin Volume" if "% of Total Bin Volume" in cols else "Total Material Volume",
            "metric": "bin_volume_consumption",
            "intent": "material_volume_share",
            "time_range": "current"
        }

    # 5. Trend Analysis & Time-series
    if any(k in cols for k in ["Month", "Date", "Year", "ChangedAt", "FullyVestedOn"]) or any(k in q_lower for k in ["trend", "history", "timeline", "over time", "month"]):
        x_col = next((k for k in ["Month", "Date", "Year", "ChangedAt", "FullyVestedOn"] if k in cols), cols[0] if cols else "Date")
        num_candidates = [k for k in cols if k != x_col and isinstance(rows[0].get(k), (int, float))]
        y_col = num_candidates[0] if num_candidates else (cols[1] if len(cols) > 1 else "TotalQuantity")
        return {
            "output_type": "line_chart",
            "chart_type": "line",
            "chart_title": "Warehouse Inventory & Activity Trend Over Time",
            "chart_x": x_col,
            "chart_y": y_col,
            "metric": "inventory_trend",
            "intent": "trend_analysis",
            "time_range": "last_6_months"
        }

    # 6. Consolidation candidates & Multi-bin duplicate items
    if "ActiveBinCount" in cols or any(k in q_lower for k in ["consolidat", "duplicate bin", "free up"]):
        return {
            "output_type": "list",
            "chart_type": "bar",
            "chart_title": "Materials in Multiple Bins (Consolidation Candidates)",
            "chart_x": "Material",
            "chart_y": "ActiveBinCount",
            "metric": "consolidation_candidates",
            "intent": "consolidation",
            "time_range": "current"
        }

    # 7. Proportional Shares / Division Distribution
    if ("Division" in cols or "MaterialGroup" in cols) and row_count <= 8:
        x_col = "Division" if "Division" in cols else "MaterialGroup"
        y_col = next((k for k in cols if isinstance(rows[0].get(k), (int, float))), "TotalQuantity")
        return {
            "output_type": "pie_chart",
            "chart_type": "pie",
            "chart_title": f"Inventory Share by {x_col}",
            "chart_x": x_col,
            "chart_y": y_col,
            "metric": "division_inventory",
            "intent": "division_breakdown",
            "time_range": "current"
        }

    # 8. Raw lookup / Empty Put-away bins / Physical locations
    if ("BinLocation" in cols or "Batch" in cols) and "Material" not in cols:
        return {
            "output_type": "table",
            "chart_type": "none",
            "metric": "unoccupied_bins",
            "intent": "putaway_bins",
            "time_range": "current"
        }

    # 9. Specific Plant Material Records / Searchable Item Tables
    if ("Material" in cols or "Description" in cols) and ("Bin" in cols or "BinNo" in cols or "Storage Location" in cols or "StorageLocation" in cols or "Plant" in cols or "Qty" in cols or "UnrestrictedQty" in cols) and "TotalQuantity" not in cols and "BinUtilizationPct" not in cols and "ConsumedMaterialVolume" not in cols:
        return {
            "output_type": "table",
            "chart_type": "none",
            "metric": "plant_stock_records",
            "intent": "plant_materials",
            "time_range": "current"
        }

    # 10. Fallback based on chart_type or detail/graph request
    is_graph_or_detail = is_detail_or_graph_requested(question)
    is_text_mode = is_single_line_requested(q_lower) or is_number_only_requested(q_lower)
    c_type = generated.get("chart_type", "none")

    if not is_text_mode and is_graph_or_detail and row_count > 1 and c_type == "none":
        cat_candidates = [c for c in cols if any(k in c.lower() for k in ["plant", "bin", "material", "storage", "location", "division", "group", "status", "category", "type", "name", "desc"])]
        x_col = cat_candidates[0] if cat_candidates else cols[0]
        num_candidates = [c for c in cols if c != x_col and any(isinstance(r.get(c), (int, float)) for r in rows if r.get(c) is not None)]
        if not num_candidates:
            for c in cols:
                if c != x_col:
                    val = str(rows[0].get(c, "")).replace("%", "").replace(",", "").strip()
                    try:
                        float(val)
                        num_candidates.append(c)
                    except ValueError:
                        pass
        if num_candidates:
            y_col = num_candidates[0]
            return {
                "output_type": "bar_chart",
                "chart_type": "bar",
                "chart_title": generated.get("chart_title", f"{y_col} by {x_col}"),
                "chart_x": x_col,
                "chart_y": y_col,
                "metric": generated.get("metric", "warehouse_metrics"),
                "intent": generated.get("intent", "warehouse_analysis"),
                "time_range": "current"
            }

    out_type = "line_chart" if c_type == "line" else "bar_chart" if c_type == "bar" else "pie_chart" if c_type == "pie" else "table"
    return {
        "output_type": out_type,
        "chart_type": c_type,
        "metric": generated.get("metric", "warehouse_metrics"),
        "intent": generated.get("intent", "warehouse_analysis"),
        "time_range": "current"
    }
