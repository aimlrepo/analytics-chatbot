import os
import duckdb
import pandas as pd
import plotly.express as px
from langchain_core.tools import tool

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "/mnt/duckdb/cache.duckdb")

@tool
def query_l2l_database(sql_query: str) -> str:
    """Queries the local DuckDB database table 'f_l2l_dispatches' using DuckDB SQL.
    Returns a Markdown-formatted table of the results.
    """
    if not os.path.exists(DUCKDB_PATH):
        return "Error: Local DuckDB database file does not exist. Please run /sync-cache first."

    conn = None
    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)
        df = conn.execute(sql_query).fetchdf()

        if df.empty:
            return "No data found matching the specified query criteria."

        return df.to_markdown(index=False)
    except Exception as e:
        return f"SQL Query Execution Error: {str(e)}"
    finally:
        if conn:
            conn.close()


@tool
def generate_l2l_chart(sql_query: str, chart_type: str, x_col: str, y_col: str, title: str) -> str:
    """Queries DuckDB and returns a raw Plotly JSON string."""
    if not os.path.exists(DUCKDB_PATH):
        return "Error: Local DuckDB database file does not exist."

    conn = None
    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)
        df = conn.execute(sql_query).fetchdf()

        if df.empty:
            return "No data available to construct the requested chart."

        ctype = chart_type.lower().strip()
        if ctype == "bar":
            fig = px.bar(df, x=x_col, y=y_col, title=title)
        elif ctype == "line":
            fig = px.line(df, x=x_col, y=y_col, title=title)
        elif ctype == "pie":
            fig = px.pie(df, names=x_col, values=y_col, title=title)
        else:
            fig = px.scatter(df, x=x_col, y=y_col, title=title)

        fig.update_layout(template="plotly_dark", margin=dict(l=20, r=20, t=40, b=20))
        
        # Return pure JSON string only
        return fig.to_json()
    except Exception as e:
        return f"Chart Generation Error: {str(e)}"
    finally:
        if conn:
            conn.close()