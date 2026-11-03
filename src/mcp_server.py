import typing
import pydantic._internal._typing_extra as _te

# Compatibility shim: Pydantic removed eval_type_backport in newer releases
if not hasattr(_te, "eval_type_backport"):
    try:
        from eval_type_backport import eval_type_backport as _eval_type_backport
    except ImportError:
        def _eval_type_backport(value, globalns=None, localns=None, type_params=None, **kwargs):
            try:
                return typing._eval_type(value, globalns, localns, type_params=type_params)
            except TypeError:
                return typing._eval_type(value, globalns, localns)
    _te.eval_type_backport = _eval_type_backport

from fastmcp import FastMCP

from src.tools import query_l2l_database, generate_l2l_chart, query_typedb
from src.prompts.typedb_prompt import (
    get_typedb_system_prompt,
    get_typedb_tool_description,
    TYPEDB_SCHEMA_INFO
)
from src.prompts.duckdb_prompt import (
    get_duckdb_system_prompt,
    get_duckdb_tool_description,
    DUCKDB_SCHEMA_INFO
)

mcp = FastMCP("L2L-Analytics-MCP")

# -------------------------------------------------------------------
# MCP PROMPT: Canonical Single Source of Truth for External Clients
# -------------------------------------------------------------------
@mcp.prompt()
def l2l_analytics_assistant() -> str:
    """Master system prompt for L2L Analytics Assistant covering both DuckDB OLAP and TypeDB Knowledge Graph."""
    return f"""You are the L2L Manufacturing Analytics Assistant.
You have access to two complementary engines:
1. **DuckDB (Vectorized OLAP)**: For quantitative aggregations (SUM, COUNT, AVG), downtime metrics, and charts.
2. **TypeDB (Knowledge Graph)**: For causal paths, deductive inference rules, order blast radius, and prescriptive triage.

{get_duckdb_system_prompt()}

---

{get_typedb_system_prompt()}
"""

# -------------------------------------------------------------------
# MCP RESOURCES: Live Schema Discovery on Demand
# -------------------------------------------------------------------
@mcp.resource("schema://typedb")
def get_typedb_schema_resource() -> str:
    """TypeDB Knowledge Graph schema, entities, base/inferred relations, and deductive rules."""
    return TYPEDB_SCHEMA_INFO

@mcp.resource("schema://duckdb")
def get_duckdb_schema_resource() -> str:
    """DuckDB relational database tables, columns, data types, and site mappings."""
    return DUCKDB_SCHEMA_INFO

# -------------------------------------------------------------------
# MCP BASE TOOLS: Dynamically Documented via Prompt SSOT
# -------------------------------------------------------------------
@mcp.tool(description=get_duckdb_tool_description())
def run_l2l_sql(sql_query: str) -> str:
    """Query DuckDB for L2L dispatches and event answers (production orders)."""
    return query_l2l_database.invoke({"sql_query": sql_query})

run_l2l_sql.__doc__ = get_duckdb_tool_description()

@mcp.tool(description=get_typedb_tool_description())
def run_typedb_query(typeql_query: str) -> str:
    """Query TypeDB Knowledge Graph for plant hierarchies, fault triage, and order blast radius."""
    return query_typedb.invoke({"typeql_query": typeql_query})

run_typedb_query.__doc__ = get_typedb_tool_description()

# -------------------------------------------------------------------
# MCP DOMAIN HELPERS: High-Level Pre-Packaged Graph Traversal Tools
# -------------------------------------------------------------------
@mcp.tool(
    description=(
        "Analyzes the cascading disruption and blast radius of a production order across "
        "affected lines (inferred via order_line_impact), machines, root-cause failure modes, "
        "and required trade skills using TypeDB Knowledge Graph reasoning."
    )
)
def get_order_blast_radius(order_number: str) -> str:
    """Analyzes the blast radius of a production order."""
    clean_order = order_number.replace("#", "").strip()
    
    # 1. Query inferred line impact
    query_line = f"""
    match
      $po isa production_order, has order_number "{clean_order}";
      (impacted_order: $po, affected_line: $l, root_cause: $r) isa order_line_impact;
      $l has linecode $lcode;
      $r has reasoncode $rcode;
    get $lcode, $rcode;
    """
    line_res = query_typedb.invoke({"typeql_query": query_line})

    # 2. Query full maintenance dispatch relations
    query_disp = f"""
    match
      $po isa production_order, has order_number "{clean_order}";
      $disp (active_order: $po, affected_machine: $m, root_cause: $r, required_trade: $t) isa maintenance_dispatch,
        has dispatchnumber $dnum,
        has downtime_minutes $dt;
      $m has machinecode $mcode;
      $r has reasoncode $rcode;
      $t has tradecode $tcode;
    get $dnum, $mcode, $rcode, $tcode, $dt;
    """
    disp_res = query_typedb.invoke({"typeql_query": query_disp})

    sections = []
    if "No data found" not in line_res and "Error" not in line_res:
        sections.append(f"### Inferred Production Line Impact\n{line_res}")
    if "No data found" not in disp_res and "Error" not in disp_res:
        sections.append(f"### Dispatches & Affected Equipment\n{disp_res}")

    if sections:
        return "\n\n".join(sections)
    elif "Error" in disp_res:
        return disp_res
    else:
        # Fallback to partial match on machines
        partial_query = f"""
        match
          $po isa production_order, has order_number "{clean_order}";
          $disp (active_order: $po, affected_machine: $m) isa maintenance_dispatch;
          $m has machinecode $mcode;
        get $mcode;
        """
        return query_typedb.invoke({"typeql_query": partial_query})

@mcp.tool(
    description=(
        "Queries TypeDB Knowledge Graph for inferred prescriptive fault triage (recommended trades) "
        "based on historical machine repairs, failure modes, or line-level capabilities."
    )
)
def get_fault_triage(machine_code: str = "", reason_code: str = "", line_code: str = "") -> str:
    """Retrieves recommended trade triage for a machine, reason, or line."""
    m = machine_code.strip()
    r = reason_code.strip()
    l = line_code.strip()

    if m and r:
        tql = f"""
        match
          $m isa machine, has machinecode "{m}";
          $r isa reason_code, has reasoncode "{r}";
          (target_machine: $m, diagnosed_reason: $r, assigned_trade: $t) isa recommended_triage;
          $t has tradecode $tcode;
        get $tcode;
        """
    elif m:
        tql = f"""
        match
          $m isa machine, has machinecode "{m}";
          $disp (affected_machine: $m, required_trade: $t) isa maintenance_dispatch;
          $t has tradecode $tcode;
        get $tcode;
        """
    elif l and r:
        tql = f"""
        match
          $l isa line, has linecode "{l}";
          (target_line: $l, diagnosed_reason: $r, assigned_trade: $t) isa line_recommended_triage;
          $t has tradecode $tcode;
        get $tcode;
        """
    elif r:
        tql = f"""
        match
          $r isa reason_code, has reasoncode "{r}";
          $disp (root_cause: $r, required_trade: $t) isa maintenance_dispatch;
          $t has tradecode $tcode;
        get $tcode;
        """
    else:
        return "Please provide at least a machine code, reason code, or line code to determine fault triage."

    return query_typedb.invoke({"typeql_query": tql})

@mcp.tool(
    description=(
        "Traverses the manufacturing asset hierarchy (Site -> Area -> Line -> Machine) "
        "using TypeDB transitive containment inference rules."
    )
)
def get_plant_asset_hierarchy(site_name: str = "", area_code: str = "", line_code: str = "") -> str:
    """Queries transitive plant asset hierarchy down to machines."""
    s = site_name.strip()
    a = area_code.strip()
    l = line_code.strip()

    if s:
        tql = f"""
        match
          $s isa site, has site_name "{s}";
          (parent_location: $s, child_asset: $m) isa plant_hierarchy;
          $m isa machine, has machinecode $mcode;
        get $mcode;
        """
    elif a:
        tql = f"""
        match
          $a isa area, has areacode "{a}";
          (parent_location: $a, child_asset: $m) isa plant_hierarchy;
          $m isa machine, has machinecode $mcode;
        get $mcode;
        """
    elif l:
        tql = f"""
        match
          $l isa line, has linecode "{l}";
          (parent_location: $l, child_asset: $m) isa plant_hierarchy;
          $m isa machine, has machinecode $mcode;
        get $mcode;
        """
    else:
        return "Please specify a site name (e.g. 'Shanghai', 'Stargard', 'Ottawa'), area code, or line code."

    return query_typedb.invoke({"typeql_query": tql})

if __name__ == "__main__":
    mcp.run()
