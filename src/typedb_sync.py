import os
import sys
import time
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import duckdb

logger = logging.getLogger(__name__)

# Configurable endpoints
DUCKDB_PATH = os.getenv("DUCKDB_PATH", "data/cache.duckdb")
TYPEDB_HOST = os.getenv("TYPEDB_HOST", "localhost")
TYPEDB_PORT = os.getenv("TYPEDB_PORT", "1729")
TYPEDB_DATABASE = os.getenv("TYPEDB_DATABASE", "l2l_analytics")
SCHEMA_FILE = os.getenv("TYPEDB_SCHEMA_FILE", "typedb/schema.tql")
TYPEDB_INGEST_WORKERS = int(os.getenv("TYPEDB_INGEST_WORKERS", "3"))
TYPEDB_INGEST_BATCH_SIZE = int(os.getenv("TYPEDB_INGEST_BATCH_SIZE", "200"))

SITE_MAP = {
    240: "Stargard",
    260: "Shanghai",
    276: "Ottawa"
}

def escape_tql(val: str) -> str:
    """Escapes special characters in TypeQL string literals."""
    if val is None:
        return ""
    return str(val).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()

def init_typedb_schema(driver, database_name: str, schema_path: str, clean: bool = True):
    """Recreates the database cleanly and applies the schema definition."""
    from typedb.driver import SessionType, TransactionType

    if driver.databases.contains(database_name):
        if clean:
            logger.info(f"Recreating database '{database_name}' to eliminate duplicate entity build-up...")
            try:
                driver.databases.get(database_name).delete()
            except Exception as e:
                logger.warning(f"Could not delete old database '{database_name}': {e}")
            driver.databases.create(database_name)
        else:
            logger.info(f"Database '{database_name}' already exists.")
    else:
        logger.info(f"Database '{database_name}' does not exist. Creating...")
        driver.databases.create(database_name)

    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found at: {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as f:
        schema_text = f.read()

    logger.info("Applying TypeQL schema definition...")
    with driver.session(database_name, SessionType.SCHEMA) as session:
        with session.transaction(TransactionType.WRITE) as tx:
            tx.query.define(schema_text)
            tx.commit()
    logger.info("Schema successfully defined.")


def _ingest_dispatch_chunk(driver, db_name: str, chunk_df, max_retries: int = 3) -> int:
    """Worker function executed concurrently to ingest a slice of dispatches."""
    from typedb.driver import SessionType, TransactionType

    for attempt in range(max_retries):
        try:
            with driver.session(db_name, SessionType.DATA) as session:
                with session.transaction(TransactionType.WRITE) as tx:
                    for _, row in chunk_df.iterrows():
                        dnum = int(row["dispatchnumber"]) if row["dispatchnumber"] is not None else 0
                        mcode = escape_tql(row["machinecode"])
                        rcode = escape_tql(row["reasoncode"])
                        tcode = escape_tql(row["tradecode"])
                        dt = int(row["downtime"]) if row["downtime"] is not None and not (isinstance(row["downtime"], float) and row["downtime"] != row["downtime"]) else 0
                        is_open_val = "true" if bool(row["is_open"]) else "false"
                        onum = escape_tql(row["order_number"]) if row["order_number"] else None

                        if onum:
                            stmt = f"""
                                match 
                                    $m isa machine, has machinecode "{mcode}";
                                    $r isa reason_code, has reasoncode "{rcode}";
                                    $t isa trade_code, has tradecode "{tcode}";
                                    $po isa production_order, has order_number "{onum}";
                                insert 
                                    (affected_machine: $m, root_cause: $r, required_trade: $t, active_order: $po) isa maintenance_dispatch,
                                         has dispatchnumber {dnum},
                                         has downtime_minutes {dt},
                                         has is_open {is_open_val};
                            """
                        else:
                            stmt = f"""
                                match 
                                    $m isa machine, has machinecode "{mcode}";
                                    $r isa reason_code, has reasoncode "{rcode}";
                                    $t isa trade_code, has tradecode "{tcode}";
                                insert 
                                    (affected_machine: $m, root_cause: $r, required_trade: $t) isa maintenance_dispatch,
                                         has dispatchnumber {dnum},
                                         has downtime_minutes {dt},
                                         has is_open {is_open_val};
                            """
                        tx.query.insert(stmt)
                    tx.commit()
            return len(chunk_df)
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            logger.error(f"Error ingesting dispatch chunk: {e}")
            raise


def sync_duckdb_to_typedb(
    duckdb_path: str = None,
    typedb_host: str = None,
    typedb_port: str = None,
    database_name: str = None,
    limit_dispatches: int = None
) -> dict:
    """Extracts relational data from DuckDB and populates TypeDB Knowledge Graph."""
    try:
        from typedb.driver import TypeDB, SessionType, TransactionType
    except ImportError:
        raise ImportError("typedb-driver is not installed. Please run 'pip install typedb-driver>=2.28.0'")

    db_path = duckdb_path or DUCKDB_PATH
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"DuckDB database file not found at {db_path}")

    host = typedb_host or TYPEDB_HOST
    port = typedb_port or TYPEDB_PORT
    db_name = database_name or TYPEDB_DATABASE

    typedb_address = f"{host}:{port}"
    logger.info(f"Connecting to TypeDB server at {typedb_address}...")
    driver = TypeDB.core_driver(typedb_address)

    try:
        # 1. Initialize schema
        init_typedb_schema(driver, db_name, SCHEMA_FILE)

        conn = duckdb.connect(db_path, read_only=True)
        logger.info("Connected to DuckDB successfully.")

        # ----------------------------------------------------
        # 2. Ingest Sites & Plant Hierarchy
        # ----------------------------------------------------
        logger.info("Ingesting Sites, Areas, Lines, and Machines...")
        with driver.session(db_name, SessionType.DATA) as session:
            with session.transaction(TransactionType.WRITE) as tx:
                for site_id, site_name in SITE_MAP.items():
                    tx.query.insert(f'insert $s isa site, has site_id {site_id}, has site_name "{site_name}";')
                tx.commit()

        # Ingest Areas and Site->Area relations
        areas_df = conn.execute("""
            SELECT DISTINCT site, areacode 
            FROM f_l2l_dispatches 
            WHERE areacode IS NOT NULL AND areacode != ''
        """).fetchdf()

        with driver.session(db_name, SessionType.DATA) as session:
            with session.transaction(TransactionType.WRITE) as tx:
                for _, row in areas_df.iterrows():
                    sid = int(row["site"])
                    acode = escape_tql(row["areacode"])
                    tx.query.insert(f"""
                        match $s isa site, has site_id {sid};
                        insert 
                            $a isa area, has areacode "{acode}";
                            (parent_location: $s, child_asset: $a) isa plant_hierarchy;
                    """)
                tx.commit()
        logger.info(f"Ingested {len(areas_df)} Areas.")

        # Ingest Lines and Area->Line relations
        lines_df = conn.execute("""
            SELECT DISTINCT areacode, linecode, lineabbreviation 
            FROM f_l2l_dispatches 
            WHERE linecode IS NOT NULL AND linecode != ''
        """).fetchdf()

        with driver.session(db_name, SessionType.DATA) as session:
            with session.transaction(TransactionType.WRITE) as tx:
                for _, row in lines_df.iterrows():
                    acode = escape_tql(row["areacode"])
                    lcode = escape_tql(row["linecode"])
                    labbr = escape_tql(row["lineabbreviation"])
                    tx.query.insert(f"""
                        match $a isa area, has areacode "{acode}";
                        insert 
                            $l isa line, has linecode "{lcode}", has lineabbreviation "{labbr}";
                            (parent_location: $a, child_asset: $l) isa plant_hierarchy;
                    """)
                tx.commit()
        logger.info(f"Ingested {len(lines_df)} Lines.")

        # Ingest Machines and Line->Machine relations
        machines_df = conn.execute("""
            SELECT DISTINCT linecode, machinecode 
            FROM f_l2l_dispatches 
            WHERE machinecode IS NOT NULL AND machinecode != ''
        """).fetchdf()

        with driver.session(db_name, SessionType.DATA) as session:
            with session.transaction(TransactionType.WRITE) as tx:
                for _, row in machines_df.iterrows():
                    lcode = escape_tql(row["linecode"])
                    mcode = escape_tql(row["machinecode"])
                    tx.query.insert(f"""
                        match $l isa line, has linecode "{lcode}";
                        insert 
                            $m isa machine, has machinecode "{mcode}";
                            (parent_location: $l, child_asset: $m) isa plant_hierarchy;
                    """)
                tx.commit()
        logger.info(f"Ingested {len(machines_df)} Machines.")

        # ----------------------------------------------------
        # 3. Ingest Reason Codes & Trade Codes
        # ----------------------------------------------------
        reasons_df = conn.execute("""
            SELECT DISTINCT reasoncode 
            FROM f_l2l_dispatches 
            WHERE reasoncode IS NOT NULL AND reasoncode != ''
        """).fetchdf()
        with driver.session(db_name, SessionType.DATA) as session:
            with session.transaction(TransactionType.WRITE) as tx:
                for _, row in reasons_df.iterrows():
                    rcode = escape_tql(row["reasoncode"])
                    tx.query.insert(f'insert $r isa reason_code, has reasoncode "{rcode}";')
                tx.commit()
        logger.info(f"Ingested {len(reasons_df)} Reason Codes.")

        trades_df = conn.execute("""
            SELECT DISTINCT tradecode 
            FROM f_l2l_dispatches 
            WHERE tradecode IS NOT NULL AND tradecode != ''
        """).fetchdf()
        with driver.session(db_name, SessionType.DATA) as session:
            with session.transaction(TransactionType.WRITE) as tx:
                for _, row in trades_df.iterrows():
                    tcode = escape_tql(row["tradecode"])
                    tx.query.insert(f'insert $t isa trade_code, has tradecode "{tcode}";')
                tx.commit()
        logger.info(f"Ingested {len(trades_df)} Trade Codes.")

        # ----------------------------------------------------
        # 4. Ingest Production Orders
        # ----------------------------------------------------
        orders_df = conn.execute("""
            SELECT DISTINCT answer AS order_number 
            FROM event_answers 
            WHERE answer IS NOT NULL AND answer != ''
        """).fetchdf()
        order_batch_size = 1000
        for i in range(0, len(orders_df), order_batch_size):
            chunk = orders_df.iloc[i : i + order_batch_size]
            with driver.session(db_name, SessionType.DATA) as session:
                with session.transaction(TransactionType.WRITE) as tx:
                    for _, row in chunk.iterrows():
                        onum = escape_tql(row["order_number"])
                        tx.query.insert(f'insert $po isa production_order, has order_number "{onum}";')
                    tx.commit()
        logger.info(f"Ingested {len(orders_df)} Production Orders.")

        # ----------------------------------------------------
        # 5. Ingest N-ary Maintenance Dispatches (Priority 1 ONLY)
        # ----------------------------------------------------
        # Only ingest dispatches linked to production orders (powers blast-radius & root-cause analysis).
        # Standalone dispatches without orders are excluded from TypeDB.
        limit_clause = f"LIMIT {limit_dispatches}" if limit_dispatches else ""
        dispatches_query = f"""
            SELECT 
                d.dispatchnumber,
                d.machinecode,
                d.reasoncode,
                d.tradecode,
                d.downtime,
                d.Open AS is_open,
                d.dispatch_reported,
                e.answer AS order_number
            FROM f_l2l_dispatches d
            INNER JOIN event_answers e ON d.id = e.dispatch
            WHERE d.machinecode IS NOT NULL AND d.machinecode != ''
              AND d.reasoncode IS NOT NULL AND d.reasoncode != ''
              AND d.tradecode IS NOT NULL AND d.tradecode != ''
              AND e.answer IS NOT NULL AND e.answer != ''
            ORDER BY d.dispatch_reported DESC
            {limit_clause}
        """
        disp_df = conn.execute(dispatches_query).fetchdf()
        workers = TYPEDB_INGEST_WORKERS
        batch_size = TYPEDB_INGEST_BATCH_SIZE
        logger.info(f"Ingesting {len(disp_df)} order-linked N-ary Maintenance Dispatches using {workers} worker threads (batch size: {batch_size})...")

        chunks = [disp_df.iloc[i : i + batch_size] for i in range(0, len(disp_df), batch_size)]
        total_ingested = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_chunk = {
                executor.submit(_ingest_dispatch_chunk, driver, db_name, chunk): len(chunk)
                for chunk in chunks
            }
            for future in as_completed(future_to_chunk):
                chunk_len = future.result()
                total_ingested += chunk_len
                if total_ingested % 1000 < batch_size or total_ingested == len(disp_df):
                    pct = int(total_ingested / len(disp_df) * 100)
                    logger.info(f"Ingested {total_ingested}/{len(disp_df)} dispatches into TypeDB ({pct}%)...")

        conn.close()
        logger.info("DuckDB to TypeDB sync completed successfully!")

        return {
            "status": "success",
            "sites": len(SITE_MAP),
            "areas": len(areas_df),
            "lines": len(lines_df),
            "machines": len(machines_df),
            "reasons": len(reasons_df),
            "trades": len(trades_df),
            "orders": len(orders_df),
            "dispatches_ingested": total_ingested
        }

    finally:
        driver.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("--- Starting DuckDB to TypeDB Knowledge Graph Sync ---")
    res = sync_duckdb_to_typedb()
    print(f"Sync Result: {res}")
