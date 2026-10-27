import logging
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from src.llm import get_llm
from src.tools import query_typedb
from src.prompts.typedb_prompt import get_typedb_system_prompt

logger = logging.getLogger(__name__)

class TypeDBAgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

# Specialist LLM with TypeDB tools
llm = get_llm(temperature=0)
tools = [query_typedb]
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

def call_typedb_worker(state: TypeDBAgentState):
    messages = list(state["messages"])
    system_prompt = SystemMessage(content=get_typedb_system_prompt())
    
    # Prepend or refresh worker system prompt
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [system_prompt] + messages
    else:
        messages[0] = system_prompt

    # Circuit breaker: enforce max 2 tool queries per current user turn
    tool_count = count_current_turn_tools(messages)
    if tool_count >= 2:
        logger.warning(f"[TypeDB Agent] Circuit breaker active: Maximum tool query attempts ({tool_count}) reached for this turn.")
        limit_msg = SystemMessage(
            content="Notice: You have reached the maximum tool query attempts for this turn. "
                    "Do NOT call any more tools. Summarize the findings factually or clearly state what could not be found."
        )
        response = llm.invoke(messages + [limit_msg])
    else:
        response = llm_with_tools.invoke(messages)

    return {"messages": [response]}

def should_continue(state: TypeDBAgentState):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        if count_current_turn_tools(state["messages"]) >= 2:
            logger.warning("[TypeDB Agent] Circuit breaker triggered in edge: terminating tool loop.")
            return END
        return "tools"
    return END

def execute_typedb_tools(state: TypeDBAgentState):
    last_message = state["messages"][-1]
    tool_messages = []
    
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        
        if tool_name == "query_typedb":
            result = query_typedb.invoke(tool_args)
        else:
            result = f"Error: Tool {tool_name} not found in TypeDB agent."
            
        tool_messages.append({
            "role": "tool",
            "content": str(result),
            "tool_call_id": tool_call["id"]
        })
        
    return {"messages": tool_messages}

# Build TypeDB Specialist Subgraph
workflow = StateGraph(TypeDBAgentState)
workflow.add_node("worker", call_typedb_worker)
workflow.add_node("tools", execute_typedb_tools)

workflow.set_entry_point("worker")
workflow.add_conditional_edges("worker", should_continue, ["tools", END])
workflow.add_edge("tools", "worker")

typedb_subgraph = workflow.compile()
