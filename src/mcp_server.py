from fastmcp import FastMCP
from src.tools import query_l2l_database, generate_l2l_chart

mcp = FastMCP("L2L-Analytics-MCP")

@mcp.tool()
def run_l2l_sql(sql_query: str) -> str:
    """Query DuckDB for L2L dispatches."""
    return query_l2l_database.invoke({"sql_query": sql_query})

if __name__ == "__main__":
    mcp.run()