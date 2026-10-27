import os
import sys

def main():
    print("=" * 65)
    print("    L2L MULTI-AGENT & TYPEDB KNOWLEDGE GRAPH TEST SUITE   ")
    print("=" * 65)
    print("\nRunning test stages...\n")

    # 1. TypeDB Engine & Schema
    print(">>> STAGE 1: Testing TypeDB connectivity & Schema validation")
    ret1 = os.system(f"{sys.executable} tests/test_typedb_connectivity.py")

    # 2. Supervisor Routing
    print("\n>>> STAGE 2: Testing Multi-Agent Supervisor Routing Accuracy")
    ret2 = os.system(f"{sys.executable} tests/test_supervisor_routing.py")

    # 3. End to End Agent & Subgraphs
    print("\n>>> STAGE 3: Testing Subgraphs & End-to-End Execution")
    ret3 = os.system(f"{sys.executable} tests/test_end_to_end_agent.py")

    print("\n" + "=" * 65)
    print("                 TEST EXECUTION SUMMARY                  ")
    print("=" * 65)
    print(f"  Stage 1 (TypeDB & Schema):      {'PASSED' if ret1 == 0 else 'FAILED / SKIPPED'}")
    print(f"  Stage 2 (Supervisor Routing):   {'PASSED' if ret2 == 0 else 'FAILED'}")
    print(f"  Stage 3 (End-to-End Execution): {'PASSED' if ret3 == 0 else 'FAILED'}")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()
