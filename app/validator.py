from dataclasses import dataclass, field
import difflib
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

DANGEROUS_FUNCTIONS = {
    "pg_sleep",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "dblink",
    "lo_import",
    "lo_export",
}

FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,  # catches TRUNCATE, COPY, GRANT, SET, etc.
)

NUMERIC_ONLY_AGGREGATES = (exp.Sum, exp.Avg)

NUMERIC_TYPE_KEYWORDS = (
    "int",
    "bigint",
    "smallint",
    "integer",
    "numeric",
    "decimal",
    "real",
    "double",
    "float",
)

MAX_LIMIT = 100

COLUMN_ALIASES: dict[str, str] = {
    "pricing": "price",
    "prices": "price",
    "cost": "price",
    "shipping": "freight_value",
    "freight": "freight_value",
    "amount": "payment_value",
    "rating": "review_score",
    "score": "review_score",
    "category": "product_category_name_english",
}



@dataclass
class ValidationResult:
    is_valid: bool
    sanitized_sql: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_security(sql: str) -> ValidationResult:
    if not sql or not sql.strip():
        return ValidationResult(is_valid=False, errors=["Query is empty."])

    # 1. Parse SQL into an AST using Postgres syntax rules
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except ParseError as e:
        return ValidationResult(is_valid=False, errors=[f"Invalid SQL syntax: {e}"])

    # 2. Allow only a single statement (blocks stacked queries)
    if len(statements) != 1:
        return ValidationResult(
            is_valid=False,
            errors=["Only a single SQL statement is allowed."],
        )

    stmt = statements[0]

    # 3. Top-level statement must be a SELECT (or UNION of SELECTs)
    if not isinstance(stmt, (exp.Select, exp.Union)):
        return ValidationResult(
            is_valid=False,
            errors=["Only SELECT queries are allowed."],
        )

    # 4. Walk every node in the tree (catches nested writes or risky functions)
    for node in stmt.walk():
        if isinstance(node, FORBIDDEN_NODES):
            return ValidationResult(
                is_valid=False,
                errors=[f"Forbidden SQL operation detected: {type(node).__name__}"],
            )
        if isinstance(node, exp.Anonymous):
            func_name = (node.name or "").lower()
        elif isinstance(node, exp.Func):
            func_name = (node.sql_name() or node.name or "").lower()
        else:
            func_name = ""

        if func_name in DANGEROUS_FUNCTIONS:
            return ValidationResult(
                is_valid=False,
                errors=[f"Function '{func_name}' is not allowed."],
            )

    # 5. Enforce or cap LIMIT
    warnings: list[str] = []
    limit_node = stmt.args.get("limit")
    if limit_node is None:
        stmt = stmt.limit(MAX_LIMIT)
        warnings.append(f"Added default LIMIT {MAX_LIMIT}.")
    elif isinstance(limit_node.expression, exp.Literal) and limit_node.expression.is_int:
        requested = int(limit_node.expression.this)
        if requested > MAX_LIMIT:
            stmt = stmt.limit(MAX_LIMIT)
            warnings.append(f"Capped LIMIT from {requested} to {MAX_LIMIT}.")

    return ValidationResult(
        is_valid=True,
        sanitized_sql=stmt.sql(dialect="postgres"),
        warnings=warnings,
    )


def _resolve_column(
    col_name: str,
    valid_columns: list[str],
    aliases: dict[str, str],
) -> tuple[str | None, str | None]:
    """Resolve a column name via exact, case-insensitive, alias, or fuzzy matching."""
    if col_name in valid_columns:
        return col_name, None

    lower_map = {c.lower(): c for c in valid_columns}
    if col_name.lower() in lower_map:
        real = lower_map[col_name.lower()]
        return real, f"Normalized column '{col_name}' -> '\"{real}\"'."

    alias_target = aliases.get(col_name.lower())
    if alias_target and alias_target.lower() in lower_map:
        real = lower_map[alias_target.lower()]
        return real, f"Mapped alias '{col_name}' -> '\"{real}\"'."

    matches = difflib.get_close_matches(
        col_name.lower(), list(lower_map.keys()), n=1, cutoff=0.6
    )
    if matches:
        real = lower_map[matches[0]]
        return real, f"Fuzzy-matched column '{col_name}' -> '\"{real}\"'."

    return None, None


def validate_schema(
    sql: str,
    schema_info: dict[str, list[dict[str, str]]],
    aliases: dict[str, str] | None = None,
) -> ValidationResult:
    merged_aliases = {**COLUMN_ALIASES, **(aliases or {})}
    stmt = sqlglot.parse_one(sql, read="postgres")
    warnings: list[str] = []
    errors: list[str] = []

    cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}
    table_map = {t.lower(): t for t in schema_info}

    referenced_tables: list[str] = []
    for tbl in stmt.find_all(exp.Table):
        t_name = tbl.name
        if not t_name or t_name.lower() in cte_names:
            continue
        if t_name.lower() not in table_map:
            errors.append(
                f"Unknown table '{t_name}'. Available tables: {', '.join(schema_info.keys())}"
            )
        else:
            referenced_tables.append(table_map[t_name.lower()])

    if errors:
        return ValidationResult(is_valid=False, errors=errors)

    valid_columns: list[str] = []
    for t in referenced_tables:
        valid_columns.extend(col["name"] for col in schema_info[t])

    output_aliases = {
        alias.alias.lower()
        for alias in stmt.find_all(exp.Alias)
        if alias.alias
    }

    for col in stmt.find_all(exp.Column):
        if isinstance(col.this, exp.Star):
            continue
        col_name = col.name
        if col_name.lower() in output_aliases and not col.table:
            continue

        matched, warn = _resolve_column(col_name, valid_columns, merged_aliases)
        if matched is None:
            errors.append(
                f"Unknown column '{col_name}'. Available columns: {', '.join(valid_columns)}"
            )
        else:
            if warn:
                warnings.append(warn)
            col.set("this", exp.to_identifier(matched, quoted=True))

    if errors:
        return ValidationResult(is_valid=False, errors=errors)

    return ValidationResult(
        is_valid=True,
        sanitized_sql=stmt.sql(dialect="postgres"),
        warnings=warnings,
    )


def _is_numeric_type(col_type: str) -> bool:
    lower_t = col_type.lower()
    return any(kw in lower_t for kw in NUMERIC_TYPE_KEYWORDS)


def validate_types(
    sql: str,
    schema_info: dict[str, list[dict[str, str]]],
) -> ValidationResult:
    stmt = sqlglot.parse_one(sql, read="postgres")
    errors: list[str] = []

    col_types: dict[str, str] = {}
    for cols in schema_info.values():
        for col in cols:
            col_types[col["name"]] = col["type"]

    for agg in stmt.find_all(*NUMERIC_ONLY_AGGREGATES):
        target = agg.this
        if isinstance(target, exp.Column):
            col_name = target.name
            col_type = col_types.get(col_name)
            if col_type and not _is_numeric_type(col_type):
                errors.append(
                    f"Cannot apply {agg.sql_name()}() to non-numeric column '{col_name}' ({col_type})."
                )

    if errors:
        return ValidationResult(is_valid=False, errors=errors)

    return ValidationResult(is_valid=True, sanitized_sql=sql)


def validate_query(
    sql: str,
    schema_info: dict[str, list[dict[str, str]]],
    aliases: dict[str, str] | None = None,
) -> ValidationResult:
    sec = validate_security(sql)
    if not sec.is_valid:
        return sec

    sch = validate_schema(sec.sanitized_sql, schema_info, aliases=aliases)
    if not sch.is_valid:
        return sch

    typ = validate_types(sch.sanitized_sql, schema_info)
    if not typ.is_valid:
        return typ

    return ValidationResult(
        is_valid=True,
        sanitized_sql=sch.sanitized_sql,
        warnings=sec.warnings + sch.warnings + typ.warnings,
    )


if __name__ == "__main__":
    mock_schema = {
        "pokemon": [
            {"name": "Name", "type": "TEXT"},
            {"name": "Type1", "type": "TEXT"},
            {"name": "Weight", "type": "DOUBLE PRECISION"},
        ],
        "products": [
            {"name": "item", "type": "TEXT"},
            {"name": "prices", "type": "NUMERIC"},
        ],
    }

    test_queries = [
        "SELECT name, primary_type, weight FROM pokemon",
        "SELECT item, pricing FROM products",
        'SELECT SUM("Name") FROM pokemon',
        "SELECT * FROM pokemon; DROP TABLE pokemon;",
        "DELETE FROM pokemon WHERE \"Name\" = 'Pikachu'",
        "SELECT pg_sleep(10)",
        "SELECT nonexistent FROM pokemon",
        "SELECT * FROM fake_table",
    ]
    for q in test_queries:
        res = validate_query(q, mock_schema)
        print(f"SQL: {q}\n  -> {res}\n")
