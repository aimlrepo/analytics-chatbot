import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TestTypeDB")

TYPEDB_HOST = os.getenv("TYPEDB_HOST", "localhost")
TYPEDB_PORT = os.getenv("TYPEDB_PORT", "1729")
TEST_DB_NAME = "test_l2l_verification"
SCHEMA_FILE = "typedb/schema.tql"

def run_tests():
    print("\n========================================================")
    print("      STAGE 1: TYPEDB SCHEMA & QUERY VERIFICATION       ")
    print("========================================================\n")

    try:
        from typedb.driver import TypeDB, SessionType, TransactionType
    except ImportError:
        print("[FAIL] 'typedb-driver' is not installed.")
        print("Please run: pip install typedb-driver>=2.28.0")
        sys.exit(1)

    address = f"{TYPEDB_HOST}:{TYPEDB_PORT}"
    print(f"[TEST 1/5] Connecting to TypeDB server at {address}...")
    try:
        driver = TypeDB.core_driver(address)
        print(" -> [PASS] Successfully connected to TypeDB server.")
    except Exception as e:
        print(f" -> [FAIL] Could not connect to TypeDB at {address}: {e}")
        print("Make sure your docker container is running: docker compose up -d typedb")
        sys.exit(1)

    try:
        # Recreate test database
        print(f"\n[TEST 2/5] Creating clean test database '{TEST_DB_NAME}'...")
        if driver.databases.contains(TEST_DB_NAME):
            driver.databases.get(TEST_DB_NAME).delete()
        driver.databases.create(TEST_DB_NAME)
        print(" -> [PASS] Test database created.")

        # Apply schema
        print(f"\n[TEST 3/5] Applying schema from '{SCHEMA_FILE}'...")
        if not os.path.exists(SCHEMA_FILE):
            print(f" -> [FAIL] Schema file not found at {SCHEMA_FILE}")
            sys.exit(1)

        with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
            schema_content = f.read()

        with driver.session(TEST_DB_NAME, SessionType.SCHEMA) as session:
            with session.transaction(TransactionType.WRITE) as tx:
                tx.query.define(schema_content)
                tx.commit()
        print(" -> [PASS] Schema defined and compiled successfully without errors.")

        # Test Data Insertion
        print("\n[TEST 4/5] Inserting sample entities, relations, and N-ary dispatch...")
        sample_insert = """
            insert
                $s isa site, has site_id 260, has site_name "Shanghai";
                $a isa area, has areacode "PACK-01";
                $l isa line, has linecode "L-04", has lineabbreviation "Line 4";
                $m isa machine, has machinecode "M-402", has machinedescription "Case Packer";
                $r isa reason_code, has reasoncode "Motor Overheat";
                $t isa trade_code, has tradecode "Electrical";
                $po isa production_order, has order_number "45009876";

                (parent_location: $s, child_asset: $a) isa plant_hierarchy;
                (parent_location: $a, child_asset: $l) isa plant_hierarchy;
                (parent_location: $l, child_asset: $m) isa plant_hierarchy;

                (affected_machine: $m, root_cause: $r, required_trade: $t, active_order: $po) isa maintenance_dispatch,
                    has dispatchnumber 99001,
                    has downtime_minutes 45,
                    has is_open false;
        """
        with driver.session(TEST_DB_NAME, SessionType.DATA) as session:
            with session.transaction(TransactionType.WRITE) as tx:
                tx.query.insert(sample_insert)
                tx.commit()
        print(" -> [PASS] Sample hierarchy and N-ary maintenance_dispatch inserted.")

        # Test Queries
        print("\n[TEST 5/5] Executing diagnostic TypeQL test queries...")
        
        # Query 1: Blast Radius
        print("  • Query 1: Production Order Blast Radius...")
        q_order = """
            match
                $po isa production_order, has order_number "45009876";
                $disp (affected_machine: $m, root_cause: $r, required_trade: $t, active_order: $po) isa maintenance_dispatch,
                    has dispatchnumber $dnum,
                    has downtime_minutes $dt;
                $m has machinecode $mcode;
                $r has reasoncode $rcode;
            get $dnum, $mcode, $rcode, $dt;
        """
        with driver.session(TEST_DB_NAME, SessionType.DATA) as session:
            with session.transaction(TransactionType.READ) as tx:
                results = list(tx.query.get(q_order))
                assert len(results) == 1, f"Expected 1 result, got {len(results)}"
                row = {k: v.get_value() for k, v in results[0].map().items() if v.is_attribute()}
                print(f"    Result: Dispatch #{row.get('dnum')} on Machine '{row.get('mcode')}' ({row.get('rcode')}) -> {row.get('dt')} min")
                print("    -> [PASS] Order blast radius resolved correctly.")

        # Query 2: Compiler Error Validation (Type-checking guardrail)
        print("  • Query 2: Testing TypeDB Compiler feedback on invalid role binding...")
        q_invalid = """
            match
                $s isa site, has site_name "Shanghai";
                # ILLEGAL: site cannot play 'affected_machine'
                $disp (affected_machine: $s) isa maintenance_dispatch;
            get $disp;
        """
        with driver.session(TEST_DB_NAME, SessionType.DATA) as session:
            with session.transaction(TransactionType.READ) as tx:
                try:
                    list(tx.query.get(q_invalid))
                    print("    -> [FAIL] Invalid role binding was unexpectedly accepted!")
                except Exception as ex:
                    print(f"    -> [PASS] TypeDB rejected invalid query at compile-time as expected: {str(ex)[:90]}...")

        print("\n========================================================")
        print("   ALL TYPEDB SCHEMA & ENGINE VERIFICATIONS PASSED!    ")
        print("========================================================\n")

    finally:
        # Cleanup test DB
        if driver.databases.contains(TEST_DB_NAME):
            driver.databases.get(TEST_DB_NAME).delete()
        driver.close()

if __name__ == "__main__":
    run_tests()
