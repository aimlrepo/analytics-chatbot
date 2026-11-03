"""
FastAPI REST API Router for Google Gemini Enterprise & Vertex AI Extensions.
Exposes OpenAPI 3.0 compliant endpoints for end-to-end multi-agent execution and granular tool calling.
"""

import json
import logging
import re
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from src.agent import agent_app
from src.utils.helpers import generate_thread_name
from src.tools import query_l2l_database, generate_l2l_chart, query_typedb
from src.prompts.typedb_prompt import (
    get_typedb_tool_description,
    TYPEDB_SCHEMA_INFO
)
from src.prompts.duckdb_prompt import (
    get_duckdb_tool_description,
    DUCKDB_SCHEMA_INFO
)

logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api/v1", tags=["L2L Manufacturing Analytics - Gemini Enterprise & Vertex AI"])

# -------------------------------------------------------------------
# PYDANTIC DATA MODELS
# -------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(
        ..., 
        description="Natural language question from factory analyst or engineer.",
        example="Top 5 dispatch types with highest downtime in Shanghai"
    )
    thread_id: Optional[str] = Field(
        None, 
        description="Optional session thread ID for conversation memory. If omitted, a timestamped thread ID is auto-generated.",
        example="26Sep26-13:33:00-Top-5-Dispatch"
    )

class ChatResponse(BaseModel):
    response: str = Field(
        ..., 
        description="Synthesized AI response, analytical prose, or formatted Markdown table."
    )
    thread_id: str = Field(
        ..., 
        description="Active session thread ID used for persistent state checkpoints."
    )
    plotly_charts: List[Dict[str, Any]] = Field(
        default_factory=list, 
        description="List of structured Plotly JSON objects (containing 'data' and 'layout') if charts were requested."
    )

class DuckDBQueryRequest(BaseModel):
    sql_query: str = Field(
        ..., 
        description="DuckDB SQL statement to execute against local tables 'f_l2l_dispatches' and 'event_answers'.",
        example="SELECT dispatchtype, SUM(downtime) as total_dt FROM f_l2l_dispatches WHERE site = 260 GROUP BY dispatchtype ORDER BY total_dt DESC LIMIT 5;"
    )

class DuckDBQueryResponse(BaseModel):
    status: str = Field("success", description="Status of query execution.")
    result_markdown: str = Field(..., description="Markdown table formatted query results.")

class DuckDBChartRequest(BaseModel):
    sql_query: str = Field(
        ..., 
        description="DuckDB SQL query that produces the dataset for visualization.",
        example="SELECT dispatchtype, COUNT(*) as count FROM f_l2l_dispatches WHERE site = 260 GROUP BY dispatchtype ORDER BY count DESC LIMIT 5;"
    )
    chart_type: str = Field(
        ..., 
        description="Type of chart to generate: 'bar', 'pie', 'line', or 'scatter'.",
        example="bar"
    )
    x_col: str = Field(..., description="Column name for X-axis / category dimension.", example="dispatchtype")
    y_col: str = Field(..., description="Column name for Y-axis / numerical metric.", example="count")
    title: str = Field(..., description="Descriptive title for chart.", example="Top 5 Dispatch Types - Shanghai")

class DuckDBChartResponse(BaseModel):
    status: str = Field("success", description="Status of chart generation.")
    chart_spec: Dict[str, Any] = Field(..., description="Parsed Plotly JSON chart specification with data and layout.")

class TypeDBQueryRequest(BaseModel):
    typeql_query: str = Field(
        ..., 
        description="TypeQL 2.x read query executing against TypeDB Knowledge Graph with rule inference enabled.",
        example='match $s isa site, has site_name "Shanghai"; (parent_location: $s, child_asset: $m) isa plant_hierarchy; $m has machinecode $mcode; get $mcode;'
    )

class TypeDBQueryResponse(BaseModel):
    status: str = Field("success", description="Status of query execution.")
    result_markdown: str = Field(..., description="Markdown table of matched concepts and attributes.")

class OrderBlastRadiusRequest(BaseModel):
    order_number: str = Field(
        ..., 
        description="Production order number to trace (e.g., '200049708').",
        example="200049708"
    )

class OrderBlastRadiusResponse(BaseModel):
    order_number: str = Field(..., description="Cleaned production order number.")
    blast_radius: str = Field(..., description="Summary of affected lines, site, equipment, failure modes, and trade skills.")

class FaultTriageRequest(BaseModel):
    machine_code: Optional[str] = Field(None, description="Target machine code (e.g. 'M-101').", example="M-101")
    reason_code: Optional[str] = Field(None, description="Diagnosed failure root cause (e.g. 'Motor Overheat').", example="Motor Overheat")
    line_code: Optional[str] = Field(None, description="Production line code (e.g. 'L-1').", example="L-1")

class FaultTriageResponse(BaseModel):
    triage_prescription: str = Field(..., description="Inferred recommended trade skill and historical triage resolution.")

class PlantHierarchyRequest(BaseModel):
    site_name: Optional[str] = Field(None, description="Production site name ('Shanghai', 'Stargard', 'Ottawa').", example="Shanghai")
    area_code: Optional[str] = Field(None, description="Specific area code.", example="A-10")
    line_code: Optional[str] = Field(None, description="Specific production line code.", example="L-1")

class PlantHierarchyResponse(BaseModel):
    hierarchy_markdown: str = Field(..., description="Transitive asset containment hierarchy matching criteria.")

class HealthCheckResponse(BaseModel):
    status: str = Field("healthy", description="Application health status.")
    engines: Dict[str, str] = Field(..., description="Operational status of storage engines.")


# -------------------------------------------------------------------
# ENDPOINTS FOR GEMINI ENTERPRISE & VERTEX AI AGENT BUILDER
# -------------------------------------------------------------------

@api_router.post(
    "/chat",
    response_model=ChatResponse,
    operation_id="ask_l2l_analytics_assistant",
    summary="Chat with L2L Manufacturing Analytics Assistant",
    description=(
        "Unified conversational entrypoint for Google Gemini Enterprise and Vertex AI. "
        "Executes hierarchical multi-agent supervisor orchestrating DuckDB OLAP calculations, "
        "TypeDB Knowledge Graph reasoning, and dynamic Plotly chart generation with session checkpoint persistence."
    )
)
async def api_chat(req: ChatRequest):
    user_input = req.message.strip()
    clean_thread_id = (req.thread_id or "").strip()
    if not clean_thread_id or clean_thread_id in ("None", "session-1") or clean_thread_id.endswith("-NewChat"):
        clean_thread_id = generate_thread_name(user_input)

    config = {"configurable": {"thread_id": clean_thread_id}}

    try:
        response_state = agent_app.invoke(
            {"messages": [("user", user_input)]}, 
            config=config
        )
        messages = response_state.get("messages", [])

        bot_text = ""
        if messages and messages[-1].type == "ai":
            bot_text = messages[-1].content

        # Extract ToolMessages containing Plotly JSON ONLY from current turn
        last_user_idx = -1
        for idx in range(len(messages) - 1, -1, -1):
            if messages[idx].type == "human":
                last_user_idx = idx
                break

        plotly_charts = []
        if last_user_idx != -1:
            for msg in messages[last_user_idx + 1:]:
                if msg.type == "tool":
                    raw_content = str(msg.content)
                    clean_json = re.sub(r"^```(?:plotly_json|json)?\s*|\s*```$", "", raw_content.strip(), flags=re.MULTILINE)
                    if '"data"' in clean_json and '"layout"' in clean_json:
                        try:
                            parsed_chart = json.loads(clean_json)
                            plotly_charts.append(parsed_chart)
                        except Exception as parse_err:
                            logger.warning(f"Failed to parse Plotly JSON: {parse_err}")

        # Clean redundant text when charts are present
        if plotly_charts and ("Plotly JSON string" in bot_text or "Jupyter notebook" in bot_text):
            bot_text = "Here are the requested charts:" if len(plotly_charts) > 1 else "Here is the requested chart:"

        # Strip hallucinated base64 images
        bot_text = re.sub(r"!\[.*?\]\(data:image\/[a-zA-Z]+;base64,[^\)]*\)", "", bot_text).strip()

        return ChatResponse(
            response=bot_text,
            thread_id=clean_thread_id,
            plotly_charts=plotly_charts
        )

    except Exception as e:
        logger.error(f"Error executing API chat turn: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent execution error: {str(e)}")


@api_router.post(
    "/tools/duckdb/query",
    response_model=DuckDBQueryResponse,
    operation_id="query_duckdb_sql",
    summary="Execute Analytical DuckDB SQL Query",
    description=get_duckdb_tool_description()
)
async def api_duckdb_query(req: DuckDBQueryRequest):
    result = query_l2l_database.invoke({"sql_query": req.sql_query})
    if result.startswith("SQL Query Execution Error") or result.startswith("Error:"):
        raise HTTPException(status_code=400, detail=result)
    return DuckDBQueryResponse(status="success", result_markdown=result)


@api_router.post(
    "/tools/duckdb/chart",
    response_model=DuckDBChartResponse,
    operation_id="generate_duckdb_chart",
    summary="Generate Plotly Visualization Specification from DuckDB",
    description=(
        "Executes a DuckDB SQL aggregation query and returns a structured Plotly chart specification "
        "('bar', 'pie', 'line', 'scatter') ready for frontend rendering."
    )
)
async def api_duckdb_chart(req: DuckDBChartRequest):
    result = generate_l2l_chart.invoke({
        "sql_query": req.sql_query,
        "chart_type": req.chart_type,
        "x_col": req.x_col,
        "y_col": req.y_col,
        "title": req.title
    })
    if result.startswith("Chart Generation Error") or result.startswith("Error:"):
        raise HTTPException(status_code=400, detail=result)
    
    try:
        spec = json.loads(result)
        return DuckDBChartResponse(status="success", chart_spec=spec)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse generated chart specification: {str(e)}")


@api_router.post(
    "/tools/typedb/query",
    response_model=TypeDBQueryResponse,
    operation_id="query_typedb_knowledge_graph",
    summary="Execute Read Query on TypeDB Knowledge Graph",
    description=get_typedb_tool_description()
)
async def api_typedb_query(req: TypeDBQueryRequest):
    result = query_typedb.invoke({"typeql_query": req.typeql_query})
    if result.startswith("TypeDB Query Error") or result.startswith("Error:"):
        raise HTTPException(status_code=400, detail=result)
    return TypeDBQueryResponse(status="success", result_markdown=result)


@api_router.post(
    "/tools/typedb/order-blast-radius",
    response_model=OrderBlastRadiusResponse,
    operation_id="get_order_blast_radius",
    summary="Analyze Production Order Blast Radius and Cascading Disruption",
    description=(
        "Queries TypeDB Knowledge Graph to evaluate operational disruption for a given production order. "
        "Identifies affected production lines (inferred via order_line_impact), machines, root causes, "
        "and required trade skills."
    )
)
async def api_order_blast_radius(req: OrderBlastRadiusRequest):
    clean_order = req.order_number.replace("#", "").strip()

    # 1. Inferred Line Impact
    query_line = f"""
    match
      $po isa production_order, has order_number "{clean_order}";
      (impacted_order: $po, affected_line: $l, root_cause: $r) isa order_line_impact;
      $l has linecode $lcode;
      $r has reasoncode $rcode;
    get $lcode, $rcode;
    """
    line_res = query_typedb.invoke({"typeql_query": query_line})

    # 2. Detailed Dispatches
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
        sections.append(f"### Inferred Production Line Disruption\n{line_res}")
    if "No data found" not in disp_res and "Error" not in disp_res:
        sections.append(f"### Dispatches & Affected Equipment\n{disp_res}")

    if sections:
        summary = "\n\n".join(sections)
    else:
        # Fallback to partial matching on machines
        partial_query = f"""
        match
          $po isa production_order, has order_number "{clean_order}";
          $disp (active_order: $po, affected_machine: $m) isa maintenance_dispatch;
          $m has machinecode $mcode;
        get $mcode;
        """
        summary = query_typedb.invoke({"typeql_query": partial_query})

    return OrderBlastRadiusResponse(order_number=clean_order, blast_radius=summary)


@api_router.post(
    "/tools/typedb/fault-triage",
    response_model=FaultTriageResponse,
    operation_id="get_prescriptive_fault_triage",
    summary="Query Prescriptive Fault Triage and Recommended Trades",
    description=(
        "Queries TypeDB Knowledge Graph for inferred recommended trade skills based on historical repairs, "
        "machine codes, failure root causes, or line capabilities."
    )
)
async def api_fault_triage(req: FaultTriageRequest):
    m = (req.machine_code or "").strip()
    r = (req.reason_code or "").strip()
    l = (req.line_code or "").strip()

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
        raise HTTPException(
            status_code=400, 
            detail="Please provide at least a machine_code, reason_code, or line_code to determine triage."
        )

    res = query_typedb.invoke({"typeql_query": tql})
    return FaultTriageResponse(triage_prescription=res)


@api_router.post(
    "/tools/typedb/plant-hierarchy",
    response_model=PlantHierarchyResponse,
    operation_id="get_plant_asset_hierarchy",
    summary="Traverse Manufacturing Asset Hierarchy",
    description="Traverses plant asset containment (Site -> Area -> Line -> Machine) using TypeDB transitive inference."
)
async def api_plant_hierarchy(req: PlantHierarchyRequest):
    s = (req.site_name or "").strip()
    a = (req.area_code or "").strip()
    l = (req.line_code or "").strip()

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
        raise HTTPException(status_code=400, detail="Please specify a site_name, area_code, or line_code.")

    res = query_typedb.invoke({"typeql_query": tql})
    return PlantHierarchyResponse(hierarchy_markdown=res)


@api_router.get(
    "/health",
    response_model=HealthCheckResponse,
    operation_id="check_api_health",
    summary="API Health & Readiness Probe",
    description="Returns service availability and storage engine readiness status."
)
async def api_health():
    import os
    from src.tools import DUCKDB_PATH, TYPEDB_HOST, TYPEDB_PORT

    duckdb_status = "ready" if os.path.exists(DUCKDB_PATH) else "cache_missing"
    return HealthCheckResponse(
        status="healthy",
        engines={
            "duckdb": f"{duckdb_status} ({DUCKDB_PATH})",
            "typedb": f"configured ({TYPEDB_HOST}:{TYPEDB_PORT})"
        }
    )
