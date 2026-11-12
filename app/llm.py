from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)
Model = os.getenv("OPENROUTER_MODEL","google/gemini-3.7-flash")


def clean_sql(raw : str):
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    return text


def generate_sql(
    question: str,
    schema_text: str,
    error_feedback: str | None = None,
) -> str:
    system_prompt = (
        "You are a PostgreSQL expert. Convert the user's question into a single "
        "read-only SELECT query using ONLY the tables and columns in the schema.\n"
        "Rules:\n"
        "- If the user asks to create, add, alter, drop, insert, update, or delete "
        "tables, columns, or rows, respond ONLY with: "
        "UNSUPPORTED: This assistant is read-only and cannot modify the database.\n"
        "- Double-quote mixed-case column names (e.g. \"Name\", \"Weight\").\n"
        "- Otherwise return ONLY raw SQL, no markdown, no explanation."
    )


    user_content = f"Schema:\n{schema_text}\n\nQuestion: {question}"
    if error_feedback:
        user_content += (
            f"\n\nYour previous SQL failed validation with this error:\n"
            f"{error_feedback}\nFix the SQL and return only the corrected query."
        )

    response = client.chat.completions.create(
        model=Model,
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    return clean_sql(response.choices[0].message.content or "")





def summarize_results(question: str, sql: str, df) -> str:
    """Turn query results into a concise plain-English answer."""
    if df.empty:
        return "No matching rows were found."

    preview = df.head(20).to_string(index=False)
    response = client.chat.completions.create(
        model=Model,
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": (
                    "Answer the user's question concisely using ONLY the SQL query "
                    "results provided. Do not invent numbers or rows."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\n"
                    f"SQL:\n{sql}\n\n"
                    f"Results (showing up to 20 rows of {len(df)}):\n{preview}"
                ),
            },
        ],
    )
    return (response.choices[0].message.content or "").strip()





if __name__ == "__main__":
    try:
        from app.schema import format_schema_for_llm, get_schema_info
    except ImportError:
        from schema import format_schema_for_llm, get_schema_info

    schema_str = format_schema_for_llm(get_schema_info())
    print(generate_sql("Show me the 5 heaviest pokemon", schema_str))