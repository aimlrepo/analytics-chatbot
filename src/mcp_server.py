import typing
import pydantic._internal._typing_extra as _te

# Compatibility shim: Pydantic removed eval_type_backport in newer releases
if not hasattr(_te, "eval_type_backport"):
    try:
        from eval_type_backport import eval_type_backport as _eval_type_backport
    except ImportError:
        def _eval_type_backport(value, globalns=None, localns=None, type_params=None, **kwargs):
            try:
                return typing._eval_type(value, globalns, localns, type_params=type_params)
            except TypeError:
                return typing._eval_type(value, globalns, localns)
    _te.eval_type_backport = _eval_type_backport

from fastmcp import FastMCP
from src.tools import query_l2l_database, generate_l2l_chart

mcp = FastMCP("L2L-Analytics-MCP")

@mcp.tool()
def run_l2l_sql(sql_query: str) -> str:
    """Query DuckDB for L2L dispatches."""
    return query_l2l_database.invoke({"sql_query": sql_query})

if __name__ == "__main__":
    mcp.run()