"""
JEV (Judgment, Evaluation, Verification) Rule Definitions.
Edit these pattern lists to customize router behavior without touching router engine code.
All patterns and keywords are completely case-insensitive.
"""

# Fast-exit greetings
GREETINGS = {
    "hi", "hello", "hey", "help", "good morning", "good afternoon", "greetings"
}

# J - Judgment: Quantitative / OLAP Modifiers (DuckDB)
ANALYTICAL_PATTERNS = [
    r"\btop\s*\d*",                                # "top 5", "top 10", "top"
    r"\b(most|highest|lowest|least|worst|best)\b", # "most downtime", "highest failures"
    r"\b(how many|how much|count|total|sum|average|avg|median)\b",
    r"\b(chart|plot|graph|visualize|trend|breakdown|distribution)\b",
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
    r"\b(this month|last month|this year|last \d+ months|q[1-4]|yesterday|today)\b",
    r"\b(table|tabular|metrics|kpi|kpis|summary)\b",
    r"\b(all(\s+the)?\s+sites?)\b",                # "all the sites", "all sites"
    r"\b(list(\s+all)?\s+sites?)\b",               # "list all sites", "list sites"
    r"\b(what(\s+are)?\s+the\s+sites?)\b"          # "what are the sites"
]

# J - Judgment: Causal / Topological Modifiers (TypeDB)
CAUSAL_PATTERNS = [
    r"\b(blast radius|impact radius)\b",
    r"\b(root cause|why did|reason for failure|cause of failure|failure mode)\b",
    r"\b(who can fix|which trade|skill required|assigned to fix|triage|historical resolution)\b",
    r"\b(which machines belong to|what lines are in|located in|belong to|asset hierarchy|containment|parent location|child asset)\b",
    r"\b((halted|blocked|delayed|disrupted)(\s+by)?\s+order)\b"
]

# E - Evaluation: Explicit SQL Schema Tokens (DuckDB)
DUCKDB_SCHEMA_SIGNALS = [
    "dispatchnumber", "sigdowntime", "f_l2l_dispatches", "event_answers", 
    "dispatchtype", "duration", "hours", "site", "sites", "facility", "facilities"
]

# E - Evaluation: Explicit Knowledge Graph Tokens (TypeDB)
TYPEDB_SCHEMA_SIGNALS = [
    "plant_hierarchy", "maintenance_dispatch", "active_order", 
    "transitive", "inference rule", "hyper-relation"
]
