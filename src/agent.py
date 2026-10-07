import os
import logging
from typing import TypedDict, Annotated, Sequence
from dotenv import load_dotenv

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from src.tools import query_l2l_database, generate_l2l_chart
from src.prompts.agent_prompt import get_agent_system_prompt

load_dotenv()

logger = logging.getLogger(__name__)

# --- Model Selection ---
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "openai").lower()

if MODEL_PROVIDER == "gemini":
    llm = ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-1.5-pro"),
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0
    )
else:
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        api_key=os.getenv("OPENAI_API_KEY"),
        temperature=0
    )

# Register tools with LLM
tools = [query_l2l_database, generate_l2l_chart]
llm_with_tools = llm.bind_tools(tools)

# --- State Definition ---
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

# --- Node Functions ---
def call_model(state: AgentState):
    messages = list(state["messages"])
    
    # Generate dynamic system prompt on each request for accurate current date/time context
    system_prompt_content = get_agent_system_prompt()
    system_message = SystemMessage(content=system_prompt_content)
    
    # Ensure system prompt is always at the start of the message history
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [system_message] + messages
    else:
        # Update existing system prompt with fresh context
        messages[0] = system_message

    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END

# --- Tool Execution Node ---
def execute_tools(state: AgentState):
    last_message = state["messages"][-1]
    tool_messages = []
    
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        
        if tool_name == "query_l2l_database":
            result = query_l2l_database.invoke(tool_args)
        elif tool_name == "generate_l2l_chart":
            json_str = generate_l2l_chart.invoke(tool_args)
            # Wrap the JSON so the LLM leaves it pristine and the frontend can match it easily
            result = f"```plotly_json\n{json_str}\n```"
        else:
            result = f"Error: Tool {tool_name} not found."
            
        tool_messages.append({
            "role": "tool",
            "content": str(result),
            "tool_call_id": tool_call["id"]
        })
        
    return {"messages": tool_messages}

# --- Graph Workflow Setup ---
workflow = StateGraph(AgentState)

workflow.add_node("agent", call_model)
workflow.add_node("tools", execute_tools)

workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, ["tools", END])
workflow.add_edge("tools", "agent")

# --- PostgreSQL Checkpointer Setup ---
POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://postgres:postgrespassword@postgres:5432/l2l_chat_memory")

pool = ConnectionPool(conninfo=POSTGRES_URL, max_size=10)
checkpointer = PostgresSaver(pool)
checkpointer.setup()

# Compile executable LangGraph application
agent_app = workflow.compile(checkpointer=checkpointer)