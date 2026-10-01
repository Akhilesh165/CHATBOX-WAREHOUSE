import pytest
import re
from backend.app.llm import deterministic_warehouse_sql_generator, optimize_response_format, format_deterministic_answer

PUTAWAY_QUESTIONS = [
    # Level 1
    "Show me all empty bins.",
    "List all completely empty bins.",
    "Which bins are currently empty?",
    "Give me a list of available empty bins.",
    "Show all bins with no inventory.",
    "Which bins have zero inventory?",
    "List bins that are currently unused.",
    "Show me all vacant bins.",
    # Level 2
    "Which storage bins are available for new put-away?",
    "Find all bins with no stock currently stored in them.",
    "Identify bins that have zero inventory.",
    "Show all warehouse locations that are completely vacant.",
    "Which bin locations are currently free?",
    "Find available storage bins for the next put-away.",
    "List all bins where the current inventory quantity is zero.",
    "Show bins that can currently accept new inventory.",
    # Level 3
    "Where can I put away new inventory right now?",
    "Which bins can I use for the next put-away?",
    "Do we have any completely empty bins?",
    "Where do we have free bin space?",
    "Find me some completely vacant bins.",
    "Which storage locations are free right now?",
    "Where can I store incoming stock?",
    "Show me the bins that aren't being used.",
    # Level 4
    "Identify all bins with zero occupied quantity.",
    "Return all bin locations where inventory quantity equals zero.",
    "Find warehouse bins with no current stock.",
    "List all bins whose current inventory balance is zero.",
    "Which bins have no inventory assigned to them?",
    "Generate a list of unoccupied bins available for put-away.",
    "Find all storage locations with zero inventory.",
    "Show all bins that are currently unoccupied.",
    # Level 5
    "Where can I place incoming stock without displacing existing inventory?",
    "Give me every storage location that is completely free.",
    "If I need to put away new material right now, which bins can I use?",
    "Show me locations where nothing is currently stored.",
    "Which warehouse positions have no stock in them at present?",
    "I need space for an incoming shipment. Find bins with zero inventory.",
    "What storage locations are vacant and ready to receive inventory?",
    "Find all locations where the current stock level is zero and the bin can be used for put-away"
]

@pytest.mark.parametrize("question", PUTAWAY_QUESTIONS)
def test_all_40_putaway_variants(question: str):
    res = deterministic_warehouse_sql_generator(question)
    assert res["intent"] == "putaway_bins", f"Failed intent for: {question}"
    assert res["output_type"] == "table", f"Failed output_type for: {question}"
    assert "dbo.ZWMS_BIN_MASTER" in res["sql"], f"SQL missing ZWMS_BIN_MASTER for: {question}"
