import pandas as pd
from sqlalchemy import create_engine, inspect

engine = create_engine("postgresql://user:pass@localhost/company_db")
inspector = inspect(engine)


# Auto-discover all tables
def explore_schema():
    schema = {}
    for table_name in inspector.get_table_names():
        columns = inspector.get_columns(table_name)
        row_count = pd.read_sql(f"SELECT COUNT(*) FROM {table_name}", engine).iloc[0, 0]

        schema[table_name] = {
            "columns": [{"name": c["name"], "type": str(c["type"])} for c in columns],
            "row_count": row_count,
        }

    return schema


schema = explore_schema()
for table, info in schema.items():
    print(f"\n📊 {table} ({info['row_count']} rows)")
    for col in info["columns"]:
        print(f"   • {col['name']} ({col['type']})")
