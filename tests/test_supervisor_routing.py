import os
import sys
from langchain_core.messages import HumanMessage, SystemMessage
from src.llm import get_llm
from src.prompts.supervisor_prompt import get_supervisor_system_prompt
from pydantic import BaseModel, Field
from typing import Literal, Optional

class SupervisorDecision(BaseModel):
    next_agent: Literal["duckdb_agent", "typedb_agent", "direct_response"]
    reply_content: Optional[str] = None

supervisor_llm = get_llm(temperature=0).with_structured_output(SupervisorDecision)

BENCHMARK_CASES = [
    # 1. DuckDB OLAP / Metrics
    {
        "query": "What is the total downtime in Shanghai for 2025?",
        "expected": "duckdb_agent",
        "category": "OLAP / Aggregation"
    },
    {
        "query": "Show me the top 5 reason codes with the highest downtime in Ottawa.",
        "expected": "duckdb_agent",
        "category": "OLAP / Top-N Table"
    },
    {
        "query": "Draw a bar chart comparing downtime across sites 240, 260, and 276.",
        "expected": "duckdb_agent",
        "category": "Visualization / Plotly"
    },
    {
        "query": "How many dispatches were opened last month in Stargard?",
        "expected": "duckdb_agent",
        "category": "OLAP / Count Metric"
    },
    
    # 2. TypeDB Knowledge Graph / Causal Reasoning
    {
        "query": "Which machines broke down during Production Order #45001234 and what were their root causes?",
        "expected": "typedb_agent",
        "category": "KG / Order Blast Radius"
    },
    {
        "query": "Machine M-101 in Ottawa just reported a Motor Overheat fault. Historically, who resolved this and what was the average downtime?",
        "expected": "typedb_agent",
        "category": "KG / Prescriptive Fault Triage"
    },
    {
        "query": "What lines and machines belong to Area Assembly in Shanghai?",
        "expected": "typedb_agent",
        "category": "KG / Plant Hierarchy Traversal"
    },
    {
        "query": "What trade skill was dispatched for machine M-402 during the last order?",
        "expected": "typedb_agent",
        "category": "KG / Multi-hop Causal Path"
    },

    # 3. Direct Conversational Responses
    {
        "query": "Hello! How can you help me today?",
        "expected": "direct_response",
        "category": "Chitchat / Greeting"
    },
    {
        "query": "What are your capabilities as a manufacturing assistant?",
        "expected": "direct_response",
        "category": "General Capability Inquiry"
    }
]

def run_routing_tests():
    print("\n========================================================")
    print("      STAGE 2: SUPERVISOR ROUTING BENCHMARK TEST        ")
    print("========================================================\n")

    passed = 0
    total = len(BENCHMARK_CASES)

    for idx, test in enumerate(BENCHMARK_CASES, 1):
        query = test["query"]
        expected = test["expected"]
        cat = test["category"]

        messages = [
            SystemMessage(content=get_supervisor_system_prompt()),
            HumanMessage(content=query)
        ]

        decision: SupervisorDecision = supervisor_llm.invoke(messages)
        routed = decision.next_agent

        status = "[PASS]" if routed == expected else "[FAIL]"
        if routed == expected:
            passed += 1

        print(f"[{idx:02d}/{total:02d}] {status} [{cat}]")
        print(f"       Query:    \"{query}\"")
        print(f"       Expected: {expected} | Actual: {routed}")
        if routed != expected:
            print(f"       MISMATCH!")
        print("-" * 56)

    success_rate = (passed / total) * 100
    print(f"\nFinal Score: {passed}/{total} Passed ({success_rate:.1f}% Accuracy)")
    print("========================================================\n")

    if success_rate < 90:
        print("[WARNING] Supervisor routing accuracy below 90%. Review supervisor prompt.")
        sys.exit(1)
    else:
        print("[SUCCESS] Supervisor routing meets production accuracy standards!")

if __name__ == "__main__":
    run_routing_tests()
