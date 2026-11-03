import os
import logging
import duckdb
import pandas as pd
import plotly.express as px
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "/mnt/duckdb/cache.duckdb")
TYPEDB_HOST = os.getenv("TYPEDB_HOST", "typedb")
TYPEDB_PORT = os.getenv("TYPEDB_PORT", "1729")
TYPEDB_DATABASE = os.getenv("TYPEDB_DATABASE", "l2l_analytics")

@tool
def query_l2l_database(sql_query: str) -> str:
    """Queries the local DuckDB database tables ('f_l2l_dispatches', 'event_answers') using DuckDB SQL.
    Supports single table queries or joins between dispatches and event_answers.
    Best for numerical aggregations (SUM, COUNT, AVG), group-bys, and filtering flat records.
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
    """Queries DuckDB ('f_l2l_dispatches', 'event_answers') and returns a raw Plotly JSON string."""
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


@tool
def query_typedb(typeql_query: str) -> str:
    """Executes a TypeQL read query against the TypeDB Knowledge Graph.
    Best for:
    - Multi-hop causal paths (e.g. Production Order -> Dispatches -> Affected Machines -> Root Causes -> Trades).
    - Plant asset hierarchy navigation (Site -> Area -> Line -> Machine).
    - Prescriptive triage (what trade or fix historically resolved this fault).
    - Deductive reasoning via inference rules (transitive containment).
    
    Returns a Markdown-formatted table of matched concepts and attributes.
    If the query has syntax or role errors, TypeDB's type-checker returns an explicit compiler error for self-correction.
    """
    try:
        from typedb.driver import TypeDB, SessionType, TransactionType
    except ImportError:
        return "Error: 'typedb-driver' is not installed in the environment."

    driver = None
    try:
        address = f"{TYPEDB_HOST}:{TYPEDB_PORT}"
        try:
            driver = TypeDB.core_driver(address)
        except Exception as conn_err:
            if TYPEDB_HOST != "localhost":
                logger.warning(f"[query_typedb] Failed to connect to '{address}', falling back to 'localhost:{TYPEDB_PORT}': {conn_err}")
                address = f"localhost:{TYPEDB_PORT}"
                driver = TypeDB.core_driver(address)
            else:
                raise conn_err

        if not driver.databases.contains(TYPEDB_DATABASE):
            return f"Error: TypeDB database '{TYPEDB_DATABASE}' does not exist. Please run the sync script first."

        logger.info(f"[query_typedb] Executing TypeQL query:\n{typeql_query.strip()}")

        # Enable rule inference if available in driver
        options = None
        try:
            from typedb.driver import TypeDBOptions
            options = TypeDBOptions()
            options.infer = True
        except Exception:
            options = None

        with driver.session(TYPEDB_DATABASE, SessionType.DATA) as session:
            try:
                # Pass options positionally (Rust/PyO3 bindings reject keyword args)
                tx_ctx = session.transaction(TransactionType.READ, options) if options else session.transaction(TransactionType.READ)
                with tx_ctx as tx:
                    concept_maps = list(tx.query.get(typeql_query))
            except Exception as tx_err:
                # Fallback without options if inference causes driver/rule issues
                if options:
                    logger.warning(f"[query_typedb] Transaction with options failed ({tx_err}), retrying without options...")
                    with session.transaction(TransactionType.READ) as tx:
                        concept_maps = list(tx.query.get(typeql_query))
                else:
                    raise tx_err

        if not concept_maps:
            logger.info("[query_typedb] Query executed successfully, 0 results found.")
            return "No data found matching the specified TypeQL query."

        rows = []
        for cm in concept_maps:
            row = {}
            c_map = cm.map() if callable(cm.map) else cm.map
            for var, concept in c_map.items():
                if hasattr(concept, "is_attribute") and concept.is_attribute():
                    row[var] = concept.get_value()
                elif hasattr(concept, "is_entity") and (concept.is_entity() or concept.is_relation()):
                    row[var] = f"<{concept.get_type().get_label().name()}>"
                elif hasattr(concept, "get_value"):
                    row[var] = concept.get_value()
                else:
                    row[var] = str(concept)
            rows.append(row)

        df = pd.DataFrame(rows)
        logger.info(f"[query_typedb] Returned {len(df)} rows.")
        return df.to_markdown(index=False)

    except Exception as e:
        logger.error(f"[query_typedb] Execution failed: {str(e)}", exc_info=True)
        return f"TypeDB Query Error: {str(e)}"
    finally:
        if driver:
            driver.close()
