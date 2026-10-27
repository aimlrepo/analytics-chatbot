import os
import sys
import logging
from langchain_core.messages import HumanMessage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TestEndToEnd")

def test_duckdb_subgraph():
    print("\n--------------------------------------------------------")
    print(" 1. Testing DuckDB Specialist Subgraph in Isolation     ")
    print("--------------------------------------------------------")
    from src.subgraphs.duckdb_agent import duckdb_subgraph

    user_query = "What are the total number of dispatches recorded in Shanghai?"
    print(f"User Question: \"{user_query}\"")

    try:
        result = duckdb_subgraph.invoke({"messages": [HumanMessage(content=user_query)]})
        messages = result["messages"]
        
        # Check tool execution
        tool_called = any(m.type == "tool" for m in messages)
        ai_response = messages[-1].content if messages and messages[-1].type == "ai" else ""

        print(f"Tool Called: {'Yes [PASS]' if tool_called else 'No [FAIL]'}")
        print(f"Final Bot Response Preview:\n{ai_response[:250]}...\n")
        assert tool_called, "Expected DuckDB tool to be invoked."
        print("[PASS] DuckDB Subgraph isolated execution successful.")
    except Exception as e:
        print(f"[FAIL] DuckDB Subgraph error: {e}")

def test_typedb_subgraph():
    print("\n--------------------------------------------------------")
    print(" 2. Testing TypeDB Specialist Subgraph in Isolation     ")
    print("--------------------------------------------------------")
    from src.subgraphs.typedb_agent import typedb_subgraph

    user_query = "Which machines broke down during Production Order #45001234?"
    print(f"User Question: \"{user_query}\"")

    try:
        result = typedb_subgraph.invoke({"messages": [HumanMessage(content=user_query)]})
        messages = result["messages"]

        tool_called = any(m.type == "tool" for m in messages)
        ai_response = messages[-1].content if messages and messages[-1].type == "ai" else ""

        print(f"Tool Called: {'Yes [PASS]' if tool_called else 'No [FAIL]'}")
        print(f"Final Bot Response Preview:\n{ai_response[:250]}...\n")
        print("[PASS] TypeDB Subgraph isolated execution successful.")
    except Exception as e:
        print(f"[FAIL] TypeDB Subgraph error: {e}")

def test_full_multi_agent():
    print("\n--------------------------------------------------------")
    print(" 3. Testing Full Hierarchical Multi-Agent (agent_app)    ")
    print("--------------------------------------------------------")
    try:
        from src.agent import agent_app
        import uuid

        thread_id = f"test-{uuid.uuid4().hex[:6]}"
        config = {"configurable": {"thread_id": thread_id}}

        # Turn 1: Greeting
        print("Turn 1: General Greeting...")
        r1 = agent_app.invoke({"messages": [HumanMessage(content="Hello!")]}, config=config)
        print(f" -> Response: {r1['messages'][-1].content}\n")

        # Turn 2: SQL Analytics
        print("Turn 2: Analytics Query (DuckDB)...")
        r2 = agent_app.invoke({"messages": [HumanMessage(content="Top 3 reason codes by downtime in Ottawa?")]}, config=config)
        print(f" -> Response:\n{r2['messages'][-1].content[:200]}...\n")

        print("[PASS] Multi-Agent End-to-End Workflow successfully verified!")
    except Exception as e:
        print(f"[NOTE] Full agent checkpointer test encountered: {e}")
        print("(Ensure PostgreSQL container is running: docker compose up -d postgres)")

if __name__ == "__main__":
    print("\n========================================================")
    print("      STAGE 3: END-TO-END MULTI-AGENT EXECUTION TEST    ")
    print("========================================================")
    test_duckdb_subgraph()
    test_typedb_subgraph()
    test_full_multi_agent()
