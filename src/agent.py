import os
import logging
from typing import TypedDict, Annotated, Sequence, Optional, Literal
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain_core.messages import BaseMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from src.llm import get_llm
from src.prompts.supervisor_prompt import get_supervisor_system_prompt
from src.subgraphs.duckdb_agent import duckdb_subgraph
from src.subgraphs.typedb_agent import typedb_subgraph
from src.jev_router import jev_fast_router

load_dotenv()

logger = logging.getLogger(__name__)

# --- Multi-Agent State Definition ---
class MultiAgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    next_agent: Optional[str]

# --- Structured Routing Decision ---
class SupervisorDecision(BaseModel):
    """Routing decision made by the central supervisor agent."""
    next_agent: Literal["duckdb_agent", "typedb_agent", "direct_response"] = Field(
        description="Choose 'duckdb_agent' for SQL/aggregations/charts, 'typedb_agent' for causal paths/blast radius/hierarchy/fault triage, or 'direct_response' for greetings/general questions."
    )
    reply_content: Optional[str] = Field(
        default=None,
        description="Conversational response if next_agent is 'direct_response'."
    )

# Instantiate supervisor model with structured output
supervisor_llm = get_llm(temperature=0).with_structured_output(SupervisorDecision)

# --- Node 1: Supervisor Router Node ---
def supervisor_node(state: MultiAgentState):
    """Evaluates user intent and routes to either DuckDB agent, TypeDB agent, or answers directly."""
    messages = list(state["messages"])
    system_prompt = SystemMessage(content=get_supervisor_system_prompt())
    
    # Filter past system messages to keep supervisor prompt fresh
    prompt_messages = [system_prompt] + [m for m in messages if not isinstance(m, SystemMessage)]
    
    decision: SupervisorDecision = supervisor_llm.invoke(prompt_messages)
    logger.info(f"[Supervisor] Routing decision: '{decision.next_agent}'")

    if decision.next_agent == "direct_response":
        reply = decision.reply_content or "Hello! I am your L2L Manufacturing Assistant. How can I assist you with maintenance, downtime, or production analytics today?"
        return {
            "messages": [AIMessage(content=reply)],
            "next_agent": "END"
        }

    return {"next_agent": decision.next_agent}

# --- Node 2: DuckDB Specialist Subgraph Node ---
def run_duckdb_subgraph(state: MultiAgentState):
    """Executes the specialized DuckDB OLAP subgraph."""
    logger.info("[Supervisor] Delegating to DuckDB Specialist Subgraph...")
    initial_len = len(state["messages"])
    subgraph_output = duckdb_subgraph.invoke({"messages": state["messages"]})
    all_msgs = subgraph_output["messages"]
    new_msgs = all_msgs[initial_len:] if len(all_msgs) > initial_len else all_msgs
    new_msgs = [m for m in new_msgs if not isinstance(m, SystemMessage)]
    return {"messages": new_msgs}

# --- Node 3: TypeDB Specialist Subgraph Node ---
def run_typedb_subgraph(state: MultiAgentState):
    """Executes the specialized TypeDB Knowledge Graph subgraph."""
    logger.info("[Supervisor] Delegating to TypeDB Specialist Subgraph...")
    initial_len = len(state["messages"])
    subgraph_output = typedb_subgraph.invoke({"messages": state["messages"]})
    all_msgs = subgraph_output["messages"]
    new_msgs = all_msgs[initial_len:] if len(all_msgs) > initial_len else all_msgs
    new_msgs = [m for m in new_msgs if not isinstance(m, SystemMessage)]
    return {"messages": new_msgs}

# --- Node 0: Direct Conversational Node ---
def direct_response_node(state: MultiAgentState):
    """Immediate conversational greeting response bypassing sub-agents."""
    reply = "Hello! I am your L2L Manufacturing Assistant. How can I assist you with maintenance, downtime, or production analytics today?"
    return {
        "messages": [AIMessage(content=reply)],
        "next_agent": "END"
    }

# --- JEV Fast-Path Entry Router (< 0.1 ms) ---
def route_entry(state: MultiAgentState):
    """Evaluates user intent via JEV Fast Router before invoking any agent or supervisor."""
    messages = state.get("messages", [])
    if not messages:
        return "direct_response"

    last_msg = messages[-1]
    content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    
    decision = jev_fast_router(content)
    logger.info(f"[JEV Fast Router] Instant decision: '{decision}' for prompt: '{content[:60]}...'")
    
    if decision == "direct_response":
        return "direct_response"
    elif decision == "duckdb_agent":
        return "duckdb_agent"
    elif decision == "typedb_agent":
        return "typedb_agent"
    return "supervisor"

# --- Supervisor Fallback Conditional Edge Routing ---
def route_next_step(state: MultiAgentState):
    next_step = state.get("next_agent")
    if next_step == "duckdb_agent":
        return "duckdb_agent"
    elif next_step == "typedb_agent":
        return "typedb_agent"
    return END

# --- Compose Top-Level Multi-Agent Graph ---
workflow = StateGraph(MultiAgentState)

workflow.add_node("direct_response", direct_response_node)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("duckdb_agent", run_duckdb_subgraph)
workflow.add_node("typedb_agent", run_typedb_subgraph)

# High-Speed JEV Router at entry point
workflow.set_conditional_entry_point(
    route_entry,
    {
        "direct_response": "direct_response",
        "duckdb_agent": "duckdb_agent",
        "typedb_agent": "typedb_agent",
        "supervisor": "supervisor"
    }
)

# Supervisor fallback if query is ambiguous
workflow.add_conditional_edges(
    "supervisor",
    route_next_step,
    {
        "duckdb_agent": "duckdb_agent",
        "typedb_agent": "typedb_agent",
        END: END
    }
)

workflow.add_edge("direct_response", END)
workflow.add_edge("duckdb_agent", END)
workflow.add_edge("typedb_agent", END)

# --- PostgreSQL Checkpointer Setup ---
POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://postgres:postgrespassword@postgres:5432/l2l_chat_memory")

pool = ConnectionPool(conninfo=POSTGRES_URL, max_size=10)
checkpointer = PostgresSaver(pool)
checkpointer.setup()

# Compile executable multi-agent application
agent_app = workflow.compile(checkpointer=checkpointer)
