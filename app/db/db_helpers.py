from app.schemas.search_schema import searchDefination


def query_builder(search: searchDefination, table_name: str):
    base_query = f"SELECT * FROM {table_name}"
    conditions = []
    values = []

    if search.filter:
        for f in search.filter:
            for column, value in f.items():

                # Special handling for boolean flags
                if isinstance(value, bool):
                    if value:
                        conditions.append(f"{column} IS NOT NULL")
                    else:
                        conditions.append(f"{column} IS NULL")

                # Normal equality
                else:
                    conditions.append(f"{column} = ?")
                    values.append(value)

    # WHERE clause
    where_clause = ""
    if conditions:
        where_clause = " WHERE " + " AND ".join(conditions)

    # ORDER BY
    order_clause = ""
    if search.sort_by:
        order_parts = []
        for s in search.sort_by:
            for col, direction in s.items():
                order_parts.append(f"{col} {direction.upper()}")
        order_clause = " ORDER BY " + ", ".join(order_parts)

    # Final query
    query = base_query + where_clause + order_clause
    print(query, values, where_clause, order_clause, base_query, sep=":::::")
    return query, tuple(values)
