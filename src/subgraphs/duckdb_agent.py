import logging
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from src.llm import get_llm
from src.tools import query_l2l_database, generate_l2l_chart
from src.prompts.duckdb_prompt import get_duckdb_system_prompt

logger = logging.getLogger(__name__)

class DuckDBAgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

# Specialist LLM with DuckDB tools
llm = get_llm(temperature=0)
tools = [query_l2l_database, generate_l2l_chart]
llm_with_tools = llm.bind_tools(tools)

def count_current_turn_tools(messages: Sequence[BaseMessage]) -> int:
    """Counts tool result messages ONLY within the current user turn."""
    last_human_idx = -1
    for idx in range(len(messages) - 1, -1, -1):
        msg = messages[idx]
        msg_type = getattr(msg, "type", None) or (msg.get("role") if isinstance(msg, dict) else None)
        if msg_type in ("human", "user"):
            last_human_idx = idx
            break
            
    if last_human_idx == -1:
        current_turn_msgs = messages
    else:
        current_turn_msgs = messages[last_human_idx + 1:]
        
    return sum(
        1 for m in current_turn_msgs
        if (getattr(m, "type", None) == "tool") or (isinstance(m, dict) and m.get("role") == "tool")
    )

def call_duckdb_worker(state: DuckDBAgentState):
    messages = list(state["messages"])
    system_prompt = SystemMessage(content=get_duckdb_system_prompt())
    
    # Prepend or refresh worker system prompt
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [system_prompt] + messages
    else:
        messages[0] = system_prompt

    # Circuit breaker: enforce max 2 tool queries per current user turn
    tool_count = count_current_turn_tools(messages)
    if tool_count >= 2:
        logger.warning(f"[DuckDB Agent] Circuit breaker active: Maximum tool query attempts ({tool_count}) reached for this turn.")
        limit_msg = SystemMessage(
            content="Notice: You have reached the maximum tool query attempts for this turn. "
                    "Do NOT call any more tools. Summarize the findings factually or clearly state what could not be found."
        )
        response = llm.invoke(messages + [limit_msg])
    else:
        response = llm_with_tools.invoke(messages)

    return {"messages": [response]}

def should_continue(state: DuckDBAgentState):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        if count_current_turn_tools(state["messages"]) >= 2:
            logger.warning("[DuckDB Agent] Circuit breaker triggered in edge: terminating tool loop.")
            return END
        return "tools"
    return END

def execute_duckdb_tools(state: DuckDBAgentState):
    last_message = state["messages"][-1]
    tool_messages = []
    
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        
        if tool_name == "query_l2l_database":
            result = query_l2l_database.invoke(tool_args)
        elif tool_name == "generate_l2l_chart":
            json_str = generate_l2l_chart.invoke(tool_args)
            result = f"```plotly_json\n{json_str}\n```"
        else:
            result = f"Error: Tool {tool_name} not found in DuckDB agent."
            
        tool_messages.append({
            "role": "tool",
            "content": str(result),
            "tool_call_id": tool_call["id"]
        })
        
    return {"messages": tool_messages}

# Build DuckDB Specialist Subgraph
workflow = StateGraph(DuckDBAgentState)
workflow.add_node("worker", call_duckdb_worker)
workflow.add_node("tools", execute_duckdb_tools)

workflow.set_entry_point("worker")
workflow.add_conditional_edges("worker", should_continue, ["tools", END])
workflow.add_edge("tools", "worker")

duckdb_subgraph = workflow.compile()
