import os
import sys
import logging
import duckdb
import pyarrow
from google.cloud import bigquery
from google.cloud.bigquery import _pyarrow_helpers

# Patch google-cloud-bigquery's internal scalar map to include REST API type aliases
# (In BigQuery REST API, INT64 is reported as 'INTEGER', which is missing in _BQ_TO_ARROW_SCALARS)
_pyarrow_helpers._BQ_TO_ARROW_SCALARS.update({
    "INTEGER": pyarrow.int64,
    "INT64": pyarrow.int64,
    "FLOAT": pyarrow.float64,
    "FLOAT64": pyarrow.float64,
    "STRING": pyarrow.string,
    "BOOLEAN": pyarrow.bool_,
    "BOOL": pyarrow.bool_,
    "TIMESTAMP": _pyarrow_helpers.pyarrow_timestamp,
    "DATETIME": _pyarrow_helpers.pyarrow_datetime,
    "DATE": pyarrow.date32,
    "NUMERIC": _pyarrow_helpers.pyarrow_numeric,
    "BIGNUMERIC": _pyarrow_helpers.pyarrow_bignumeric,
})

logger = logging.getLogger(__name__)

DB_FILE = os.getenv("DUCKDB_PATH", "/mnt/duckdb/cache.duckdb")

def sync_bigquery_to_duckdb(bq_project: str = None, db_path: str = None) -> dict:
    """Streams data from Google BigQuery directly into DuckDB using PyArrow RecordBatches.
    
    Eliminates Pandas memory multiplication by ingesting chunk-by-chunk in zero-copy columnar format.
    Guarantees exact schema compatibility with agent_prompt.py specifications.
    """
    target_db = db_path or DB_FILE
    project_id = bq_project or os.getenv("GCP_PROJECT_ID", "k-qualitytower-0001-p")
    
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id

    logger.info(f"Connecting to BigQuery project '{project_id}'...")
    print(f"Connecting to BigQuery project '{project_id}'...")
    client = bigquery.Client(project=project_id)

    query = """
    SELECT 
        SAFE_CAST(dispatchnumber AS INT64) AS dispatchnumber,
        SAFE_CAST(site AS INT64) AS site,
        CAST(dispatchtype AS STRING) AS dispatchtype,
        CAST(current_dispatchstatus_description AS STRING) AS current_dispatchstatus_description,
        CAST(dispatch_reported AS TIMESTAMP) AS dispatch_reported,
        SAFE_CAST(downtime AS INT64) AS downtime,
        CAST(completed AS TIMESTAMP) AS completed,
        SAFE_CAST(Open AS BOOL) AS Open,
        CAST(tradecode AS STRING) AS tradecode,
        SAFE_CAST(sigdowntime AS INT64) AS sigdowntime,
        CAST(machinecode AS STRING) AS machinecode,
        CAST(lineabbreviation AS STRING) AS lineabbreviation,
        CAST(areacode AS STRING) AS areacode,
        CAST(linecode AS STRING) AS linecode,
        CAST(reasoncode AS STRING) AS reasoncode
    FROM cons_kamos_l2l.f_l2l_dispatches
    """

    print("Submitting query to BigQuery...")
    query_job = client.query(query)
    
    results = query_job.result()
    print("BigQuery query completed. Schema:")
    for field in results.schema:
        print(f"  • {field.name}: {field.field_type}")

    # Obtain Arrow batch iterator from query results
    batch_iterator = results.to_arrow_iterable()

    db_dir = os.path.dirname(target_db)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    print(f"Connecting to DuckDB at '{target_db}'...")
    conn = duckdb.connect(target_db)

    try:
        table_created = False
        batch_count = 0
        total_rows = 0

        print("Streaming Arrow batches directly into DuckDB...")
        for batch in batch_iterator:
            batch_count += 1
            batch_rows = len(batch)
            total_rows += batch_rows

            # Wrap the RecordBatch into a zero-copy PyArrow Table so DuckDB can register it
            arrow_table = pyarrow.Table.from_batches([batch])
            conn.register("current_batch", arrow_table)
            try:
                if not table_created:
                    conn.execute("CREATE OR REPLACE TABLE f_l2l_dispatches AS SELECT * FROM current_batch")
                    table_created = True
                else:
                    conn.execute("INSERT INTO f_l2l_dispatches SELECT * FROM current_batch")
            finally:
                conn.unregister("current_batch")

            if batch_count % 10 == 0:
                print(f"Ingested {batch_count} batches ({total_rows:,} rows so far)...")

        # Handle empty query edge-case
        if not table_created:
            empty_table = results.to_arrow()
            conn.register("empty_table", empty_table)
            try:
                conn.execute("CREATE OR REPLACE TABLE f_l2l_dispatches AS SELECT * FROM empty_table")
            finally:
                conn.unregister("empty_table")
            print("Table created with 0 rows (empty dataset).")
        else:
            print(f"Sync complete: {total_rows:,} rows across {batch_count} batches cached successfully.")

        # Print the final DuckDB schema to verify exact data types
        duckdb_schema = conn.execute("DESCRIBE f_l2l_dispatches").fetchall()
        print("\nFinal DuckDB Table Schema:")
        for col_name, col_type, null_ok, key, dflt, extra in duckdb_schema:
            print(f"  • {col_name:35} {col_type}")

        return {
            "status": "success",
            "total_rows": total_rows,
            "batch_count": batch_count,
            "db_path": target_db
        }

    finally:
        conn.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("--- Starting BigQuery to DuckDB PyArrow Sync ---")
    try:
        result = sync_bigquery_to_duckdb()
        print(f"\nResult: {result}")
    except Exception as e:
        print(f"Sync failed with error: {e}", file=sys.stderr)
        sys.exit(1)
