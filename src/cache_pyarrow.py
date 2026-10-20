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
DEFAULT_PROJECT = os.getenv("GCP_CURATED_PROJECT_ID", os.getenv("GCP_PROJECT_ID", "k-bicloud-curated-0001-p"))


def _stream_query_to_duckdb(
    client: bigquery.Client, 
    query: str, 
    conn: duckdb.DuckDBPyConnection, 
    table_name: str
) -> dict:
    """Helper that streams an arbitrary BigQuery query into a DuckDB table using PyArrow batches."""
    logger.info(f"Submitting BigQuery query for '{table_name}'...")
    print(f"Submitting query for '{table_name}' to BigQuery...")
    query_job = client.query(query)
    results = query_job.result()

    print(f"BigQuery query for '{table_name}' completed. Schema:")
    for field in results.schema:
        print(f"  • {field.name}: {field.field_type}")

    batch_iterator = results.to_arrow_iterable()

    table_created = False
    batch_count = 0
    total_rows = 0

    print(f"Streaming Arrow batches into DuckDB table '{table_name}'...")
    for batch in batch_iterator:
        batch_count += 1
        batch_rows = len(batch)
        total_rows += batch_rows

        arrow_table = pyarrow.Table.from_batches([batch])
        conn.register("current_batch", arrow_table)
        try:
            if not table_created:
                conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM current_batch")
                table_created = True
            else:
                conn.execute(f"INSERT INTO {table_name} SELECT * FROM current_batch")
        finally:
            conn.unregister("current_batch")

        if batch_count % 10 == 0:
            print(f"[{table_name}] Ingested {batch_count} batches ({total_rows:,} rows so far)...")

    # Handle empty query result
    if not table_created:
        empty_table = results.to_arrow()
        conn.register("empty_table", empty_table)
        try:
            conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM empty_table")
        finally:
            conn.unregister("empty_table")
        print(f"[{table_name}] Table created with 0 rows (empty dataset).")
    else:
        print(f"[{table_name}] Ingestion complete: {total_rows:,} rows across {batch_count} batches cached successfully.")

    duckdb_schema = conn.execute(f"DESCRIBE {table_name}").fetchall()
    print(f"\nFinal DuckDB Table Schema for '{table_name}':")
    for col_name, col_type, null_ok, key, dflt, extra in duckdb_schema:
        print(f"  • {col_name:35} {col_type}")

    return {
        "table": table_name,
        "total_rows": total_rows,
        "batch_count": batch_count
    }


def sync_dispatches_to_duckdb(conn: duckdb.DuckDBPyConnection, bq_project: str = None) -> dict:
    """Syncs dispatches from dispatches_240, dispatches_260, and dispatches_276 in BigQuery into DuckDB f_l2l_dispatches."""
    project_id = bq_project or DEFAULT_PROJECT
    logger.info(f"Connecting to BigQuery project '{project_id}' for dispatches (240, 260, 276)...")
    print(f"Connecting to BigQuery project '{project_id}' for dispatches (240, 260, 276)...")
    client = bigquery.Client(project=project_id)

    query = f"""
    SELECT 
        SAFE_CAST(id AS INT64) AS id,
        SAFE_CAST(dispatchnumber AS INT64) AS dispatchnumber,
        240 AS site,
        CAST(dispatchtype AS STRING) AS dispatchtype,
        CAST(reported AS TIMESTAMP) AS dispatch_reported,
        SAFE_CAST(downtime AS INT64) AS downtime,
        CAST(completed AS TIMESTAMP) AS completed,
        SAFE_CAST(open AS BOOL) AS Open,
        CAST(tradecode AS STRING) AS tradecode,
        SAFE_CAST(sigdowntime AS INT64) AS sigdowntime,
        CAST(machinecode AS STRING) AS machinecode,
        CAST(lineabbreviation AS STRING) AS lineabbreviation,
        CAST(areacode AS STRING) AS areacode,
        CAST(linecode AS STRING) AS linecode,
        CAST(reasoncode AS STRING) AS reasoncode
    FROM `{project_id}.l2l.dispatches_240`
    WHERE deleted IS NOT TRUE

    UNION ALL

    SELECT 
        SAFE_CAST(id AS INT64) AS id,
        SAFE_CAST(dispatchnumber AS INT64) AS dispatchnumber,
        260 AS site,
        CAST(dispatchtype AS STRING) AS dispatchtype,
        CAST(reported AS TIMESTAMP) AS dispatch_reported,
        SAFE_CAST(downtime AS INT64) AS downtime,
        CAST(completed AS TIMESTAMP) AS completed,
        SAFE_CAST(open AS BOOL) AS Open,
        CAST(tradecode AS STRING) AS tradecode,
        SAFE_CAST(sigdowntime AS INT64) AS sigdowntime,
        CAST(machinecode AS STRING) AS machinecode,
        CAST(lineabbreviation AS STRING) AS lineabbreviation,
        CAST(areacode AS STRING) AS areacode,
        CAST(linecode AS STRING) AS linecode,
        CAST(reasoncode AS STRING) AS reasoncode
    FROM `{project_id}.l2l.dispatches_260`
    WHERE deleted IS NOT TRUE

    UNION ALL

    SELECT 
        SAFE_CAST(id AS INT64) AS id,
        SAFE_CAST(dispatchnumber AS INT64) AS dispatchnumber,
        276 AS site,
        CAST(dispatchtype AS STRING) AS dispatchtype,
        CAST(reported AS TIMESTAMP) AS dispatch_reported,
        SAFE_CAST(downtime AS INT64) AS downtime,
        CAST(completed AS TIMESTAMP) AS completed,
        SAFE_CAST(open AS BOOL) AS Open,
        CAST(tradecode AS STRING) AS tradecode,
        SAFE_CAST(sigdowntime AS INT64) AS sigdowntime,
        CAST(machinecode AS STRING) AS machinecode,
        CAST(lineabbreviation AS STRING) AS lineabbreviation,
        CAST(areacode AS STRING) AS areacode,
        CAST(linecode AS STRING) AS linecode,
        CAST(reasoncode AS STRING) AS reasoncode
    FROM `{project_id}.l2l.dispatches_276`
    WHERE deleted IS NOT TRUE
    """

    res = _stream_query_to_duckdb(client, query, conn, "f_l2l_dispatches")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dispatches_id ON f_l2l_dispatches(id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dispatches_number ON f_l2l_dispatches(dispatchnumber)")
    return res


def sync_event_answers_to_duckdb(conn: duckdb.DuckDBPyConnection, bq_project: str = None) -> dict:
    """Syncs event_answers from BigQuery into DuckDB."""
    project_id = bq_project or DEFAULT_PROJECT
    logger.info(f"Connecting to BigQuery project '{project_id}' for event_answers...")
    print(f"Connecting to BigQuery project '{project_id}' for event_answers...")
    client = bigquery.Client(project=project_id)

    query = f"""
    SELECT 
        SAFE_CAST(a.id AS INT64) AS id,
        SAFE_CAST(a.site AS INT64) AS site,
        CAST(a.question AS STRING) AS question,
        CAST(a.answer AS STRING) AS answer,
        SAFE_CAST(a.dispatch AS INT64) AS dispatch,
        CAST(a.created AS TIMESTAMP) AS created,
        CAST(a.lastupdated AS TIMESTAMP) AS lastupdated,
        CAST(a.createdby AS STRING) AS createdby
    FROM `{project_id}.l2l.event_answers` a
    WHERE a.createdby = 'PQT_API'
      AND a.question LIKE '%Production order #%'
    ORDER BY a.created DESC
    """

    res = _stream_query_to_duckdb(client, query, conn, "event_answers")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event_answers_dispatch ON event_answers(dispatch)")
    return res


def sync_bigquery_to_duckdb(
    bq_project: str = None, 
    curated_project: str = None,
    db_path: str = None
) -> dict:
    """Streams dispatches (sites 240, 260, 276) and event_answers from Google BigQuery directly into DuckDB using PyArrow RecordBatches.
    
    Eliminates Pandas memory multiplication by ingesting chunk-by-chunk in zero-copy columnar format.
    Guarantees exact schema compatibility with agent_prompt.py specifications.
    """
    target_db = db_path or DB_FILE
    db_dir = os.path.dirname(target_db)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    print(f"Connecting to DuckDB at '{target_db}'...")
    conn = duckdb.connect(target_db)

    try:
        dispatches_info = sync_dispatches_to_duckdb(conn, bq_project=curated_project or bq_project)
        event_answers_info = sync_event_answers_to_duckdb(conn, bq_project=curated_project or bq_project)

        total_rows = dispatches_info["total_rows"] + event_answers_info["total_rows"]
        total_batches = dispatches_info["batch_count"] + event_answers_info["batch_count"]

        return {
            "status": "success",
            "total_rows": total_rows,
            "total_batches": total_batches,
            "tables": {
                "f_l2l_dispatches": dispatches_info,
                "event_answers": event_answers_info
            },
            "db_path": target_db
        }

    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("--- Starting BigQuery to DuckDB PyArrow Sync (Dispatches 240/260/276 & Event Answers) ---")
    try:
        result = sync_bigquery_to_duckdb()
        print(f"\nResult: {result}")
    except Exception as e:
        print(f"Sync failed with error: {e}", file=sys.stderr)
        sys.exit(1)
