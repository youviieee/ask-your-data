from typing import Any
import pandas as pd

try:
    from app.database import query_to_dataframe
    from app.llm import generate_sql, summarize_results
    from app.schema import format_schema_for_llm, get_schema_info
    from app.validator import ValidationResult, validate_query
except ImportError:
    from database import query_to_dataframe
    from llm import generate_sql, summarize_results
    from schema import format_schema_for_llm, get_schema_info
    from validator import ValidationResult, validate_query
from sqlalchemy.exc import SQLAlchemyError



def run_safe_query(
    sql: str,
    schema_info: dict[str, list[dict[str, str]]] | None = None,
    aliases: dict[str, str] | None = None,
) -> dict[str, Any]:

    """Validate SQL for security, schema, and types before executing against Postgres."""
    if schema_info is None:
        schema_info = get_schema_info()

    validation: ValidationResult = validate_query(sql, schema_info, aliases=aliases)
    if not validation.is_valid or validation.sanitized_sql is None:
        return {
            "ok": False,
            "sql": None,
            "errors": validation.errors,
            "warnings": validation.warnings,
            "data": None,
        }


    try:
        df: pd.DataFrame = query_to_dataframe(validation.sanitized_sql)
    except SQLAlchemyError as e:
        return {
            "ok": False,
            "sql": validation.sanitized_sql,
            "errors": [f"Database execution error: {e}"],
            "warnings": validation.warnings,
            "data": None,
        }

    return {
        "ok": True,
        "sql": validation.sanitized_sql,
        "errors": [],
        "warnings": validation.warnings,
        "data": df,
    }





def ask_your_data(question: str, max_retries: int = 3) -> dict[str, Any]:
    schema_info = get_schema_info()
    schema_text = format_schema_for_llm(schema_info)

    error_feedback: str | None = None
    last_errors: list[str] = []

    for attempt in range(1, max_retries + 1):
        sql = generate_sql(question, schema_text, error_feedback=error_feedback)
        if sql.upper().startswith("UNSUPPORTED:"):
            msg = sql.split(":", 1)[1].strip()
            return {
                "ok": False,
                "attempts": attempt,
                "sql": None,
                "errors": [msg],
                "answer": msg,
                "data": None,
            }

        outcome = run_safe_query(sql, schema_info=schema_info)

        if outcome["ok"]:
            answer = summarize_results(question, outcome["sql"], outcome["data"])
            return {
                "ok": True,
                "attempts": attempt,
                "sql": outcome["sql"],
                "warnings": outcome["warnings"],
                "answer": answer,
                "data": outcome["data"],
            }

        last_errors = outcome["errors"]
        error_feedback = (
            f"Attempt {attempt} generated:\n{sql}\n\n"
            f"Errors:\n- " + "\n- ".join(last_errors)
        )

    return {
        "ok": False,
        "attempts": max_retries,
        "sql": None,
        "errors": last_errors,
        "answer": "Could not generate a valid query after multiple attempts.",
        "data": None,
    }





if __name__ == "__main__":
    print("Ask Your Data (type 'exit' to quit)\n")
    while True:
        question = input("Question: ").strip()
        if not question or question.lower() in {"exit", "quit"}:
            break

        result = ask_your_data(question)
        if result["ok"]:
            print(f"\nSQL ({result['attempts']} attempt(s)): {result['sql']}")
            if result["warnings"]:
                print("Warnings:", result["warnings"])
            print(f"\nAnswer:\n{result['answer']}\n")
        else:
            print(f"\nFailed: {result['errors']}\n")
