from sqlalchemy import inspect
from database import engine


def get_schema_info():
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    schema = {}
    for table in table_names :
        columns = inspector.get_columns(table_name=table)
        coln_list = []
        for col in columns:
            coln_list.append({
                "name" : col["name"],
                "type" : str(col["type"])
            })
        schema[table] = coln_list

    return schema



def format_schema_for_llm(schema_info):
    lines = []

    for table_name,columns in schema_info.items():
        lines.append(f"Table : {table_name}")
        for col in columns :
            lines.append(f"  - {col['name']} ({col['type']})")

    return "\n".join(lines)

if __name__ == "__main__":
    print(format_schema_for_llm(get_schema_info()))