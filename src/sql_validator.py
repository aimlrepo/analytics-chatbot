import sqlglot
import sqlglot.expressions as exp

def validate_and_sanitize_sql(sql_query: str) -> str:
    try:
        parsed_expressions = sqlglot.parse(sql_query, read="duckdb")
        
        if len(parsed_expressions) > 1:
            raise ValueError("Multi-statement SQL execution is strictly forbidden.")

        expression = parsed_expressions[0]

        if not isinstance(expression, (exp.Select, exp.Expression)):
            raise ValueError(f"Unauthorized SQL statement type: {expression.key.upper()}. Only SELECT queries are permitted.")
        
        for node in expression.find_all(exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter):
            raise ValueError(f"Unauthorized mutation keyword detected: {node.key.upper()}")

        if not expression.find(exp.Limit):
            expression = expression.limit(500)

        return expression.sql(dialect="duckdb")

    except sqlglot.errors.ParseError as e:
        raise ValueError(f"Invalid SQL Syntax generated: {str(e)}")