import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.jev_router import jev_fast_router

def run_tests():
    test_cases = [
        # --- Case-insensitivity & Site queries -> DuckDB ---
        ("give me all the sites I have in this application", "duckdb_agent"),
        ("GIVE ME ALL THE SITES", "duckdb_agent"),
        ("what are the sites in this system?", "duckdb_agent"),
        ("list all sites", "duckdb_agent"),
        ("which sites are available", "duckdb_agent"),

        # --- Mixed Case Analytical / OLAP / DuckDB queries ---
        ("GIVE ME TOP 5 AREAS", "duckdb_agent"),
        ("give me top 10 machines with highest downtime", "duckdb_agent"),
        ("Total Downtime in Shanghai Last Month", "duckdb_agent"),
        ("DRAW A BAR CHART OF FAILURE REASONS", "duckdb_agent"),
        ("how many dispatches are currently open in Ottawa?", "duckdb_agent"),

        # --- Mixed Case Semantic Graph / TypeDB queries ---
        ("WHAT PRODUCTION LINES ARE LOCATED IN THE OTTAWA PLANT", "typedb_agent"),
        ("Which machines belong to line L-01 in Shanghai?", "typedb_agent"),
        ("What is the blast radius for production order 45001234?", "typedb_agent"),
        ("What was the root cause of failure for dispatch 10492?", "typedb_agent"),
        ("Who can fix motor overheat on machine M-101?", "typedb_agent"),

        # --- Case-insensitive Greetings ---
        ("HELLO", "direct_response"),
        ("Hi There", "direct_response"),
        ("hey", "direct_response"),

        # --- Ambiguous queries (Fall back to Supervisor) ---
        ("can you tell me something interesting about the factory?", "supervisor"),
    ]

    print("==================================================")
    print("   JEV FAST ROUTER CASE-INSENSITIVE TEST SUITE    ")
    print("==================================================")

    passed = 0
    failed = 0

    for query, expected in test_cases:
        actual = jev_fast_router(query)
        status = "PASSED" if actual == expected else "FAILED"
        if status == "PASSED":
            passed += 1
            print(f"[OK]   '{query}' -> {actual}")
        else:
            failed += 1
            print(f"[FAIL] '{query}' -> Expected: {expected}, Got: {actual}")

    print("==================================================")
    print(f"Total: {len(test_cases)} | Passed: {passed} | Failed: {failed}")
    print("==================================================")

    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
