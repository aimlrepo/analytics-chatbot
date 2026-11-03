import re
import logging
from typing import Literal

from src.jev_rules import (
    GREETINGS,
    ANALYTICAL_PATTERNS,
    CAUSAL_PATTERNS,
    DUCKDB_SCHEMA_SIGNALS,
    TYPEDB_SCHEMA_SIGNALS
)

logger = logging.getLogger(__name__)

def jev_fast_router(query_text: str) -> Literal["duckdb_agent", "typedb_agent", "direct_response", "supervisor"]:
    """
    High-Speed JEV Router using rule configurations in src/jev_rules.py.
    Fully case-insensitive across all rules, keywords, and user queries.
    """
    if not query_text:
        return "direct_response"
        
    query = query_text.strip()
    query_lower = query.lower()

    # --- 0. FAST EXIT: GREETINGS (Case-insensitive) ---
    clean_greetings = {g.lower().strip() for g in GREETINGS}
    if query_lower in clean_greetings or any(query_lower.startswith(g + " ") for g in clean_greetings):
        return "direct_response"

    # --- 1. J - JUDGMENT (Case-insensitive regex matching) ---
    is_analytical = any(re.search(pat, query, re.IGNORECASE) for pat in ANALYTICAL_PATTERNS)
    is_causal = any(re.search(pat, query, re.IGNORECASE) for pat in CAUSAL_PATTERNS)

    # --- 2. E - EVALUATION (Case-insensitive keyword & word-boundary matching) ---
    has_duckdb_schema = any(
        re.search(rf"\b{re.escape(kw.lower().strip())}\b", query_lower)
        for kw in DUCKDB_SCHEMA_SIGNALS
    )
    has_typedb_schema = any(
        re.search(rf"\b{re.escape(kw.lower().strip())}\b", query_lower)
        for kw in TYPEDB_SCHEMA_SIGNALS
    )

    # --- 3. V - VERIFICATION ---
    # Rule 1: Explicit Causal, Blast Radius, or Hierarchy queries go to TypeDB
    # (even if "site" or "facility" is mentioned, unless the user asked for counts/aggregations/charts)
    if (is_causal or has_typedb_schema) and not is_analytical:
        return "typedb_agent"

    # Rule 2: Aggregations, plots, or SQL schema (site, dispatchtype, etc.) go to DuckDB
    if is_analytical or has_duckdb_schema:
        return "duckdb_agent"

    # Rule 3: Any remaining causal signals
    if is_causal or has_typedb_schema:
        return "typedb_agent"

    # Rule 4: Ambiguous queries fallback to Supervisor
    return "supervisor"
