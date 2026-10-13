import os
import duckdb
from google.cloud import bigquery
import pandas as pd

DB_FILE = "/app/data/l2l_analytics.duckdb"

def sync_bigquery_to_duckdb(bq_project: str = None):
    project_id = bq_project or os.getenv("GCP_PROJECT_ID", "k-qualitytower-0001-p")
    print(f"Fetching data from BigQuery project '{project_id}'...")
    client = bigquery.Client(project=project_id)
    
    query = """
    SELECT 
        dispatchnumber, site, dispatchtype, current_dispatchstatus_description,
        dispatch_reported, downtime, completed, Open, tradecode,
        sigdowntime, machinecode, lineabbreviation, areacode,
        linecode, reasoncode
    FROM cons_kamos_l2l.f_l2l_dispatches
    """
    df = client.query(query).to_dataframe()
    
    df['dispatch_reported'] = pd.to_datetime(df['dispatch_reported'])
    df['completed'] = pd.to_datetime(df['completed'])

    print("Caching data into DuckDB...")
    conn = duckdb.connect(DB_FILE)
    conn.execute("CREATE OR REPLACE TABLE f_l2l_dispatches AS SELECT * FROM df")
    conn.close()
    print("Cache sync complete.")

def run_duckdb_safely(sql_query: str) -> pd.DataFrame:
    conn = duckdb.connect(DB_FILE, read_only=True)
    try:
        conn.execute("SET statement_timeout = '10s'")
        conn.execute("SET max_memory = '2GB'")
        df = conn.execute(sql_query).df()
        return df
    finally:
        conn.close()

def run_duckdb_query(sql: str) -> str:
    try:
        df = run_duckdb_safely(sql)
        if df.empty:
            return "No data returned for this query."
        return df.to_markdown(index=False)
    except Exception as e:
        return f"Database Error: {str(e)}"