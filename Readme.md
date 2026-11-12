# Ask Your Data

A read-only, self-correcting **Text-to-SQL** CLI assistant built with Python, PostgreSQL 17, `sqlglot`, and OpenRouter. Ask plain-English questions about your CSV datasets, and the pipeline generates PostgreSQL queries, validates them through a 3-stage AST security and schema gate, executes them over a restricted read-only database role, and summarizes the results.

---

## Architecture

```text
User Question
     │
     ▼
[app/schema.py] ──► Live PostgreSQL schema blueprint
     │
     ▼
[app/llm.py]    ──► OpenRouter (google/gemini-3.7-flash) generates SQL
     │              (or returns UNSUPPORTED: for write/DDL requests)
     ▼
[app/validator.py]
  ├─ 1. Security Gate (sqlglot AST: single SELECT/UNION, blocks DDL & risky functions, caps LIMIT 100)
  ├─ 2. Schema & Alias Mapper (exact → case-insensitive → COLUMN_ALIASES → difflib fuzzy + double-quoting)
  └─ 3. Type Sanity Check (blocks SUM/AVG on non-numeric columns)
     │
     ▼
[app/database.py] ──► Executes via readonly_engine (SELECT-only role + 5s statement_timeout)
     │
     ├──► On error: feeds SQL + error back to app/llm.py (up to 3 retries in app/main.py)
     └──► On success: summarizes returned DataFrame into plain English
```

---

## Project Structure

```text
ask-your-data/
├── app/
│   ├── database.py      # Dual SQLAlchemy engines (admin + readonly_engine with 5s timeout)
│   ├── llm.py           # OpenRouter SQL generation, UNSUPPORTED refusal, & result summarization
│   ├── load_data.py     # Recursive CSV-to-PostgreSQL loader using Pandas to_sql()
│   ├── main.py          # run_safe_query(), ask_your_data() retry loop, & interactive CLI
│   ├── schema.py        # Dynamic SQLAlchemy schema inspector & LLM prompt formatter
│   └── validator.py     # 3-stage sqlglot AST security, semantic alias, & type validator
├── data/
│   └── raw/archived/    # Olist e-commerce CSV datasets (8 tables)
├── csv/                 # Additional sample CSVs (e.g., pokemon.csv)
├── docker-compose.yml   # PostgreSQL 17 container (mapped to host port 5433)
└── requirements.txt     # Python dependencies
```

---

## Key Features

- **Defense-in-Depth SQL Safety:** Combines AST-level allowlisting in Python (`sqlglot`) with a dedicated PostgreSQL `readonly_user` role (`SELECT`-only privileges) and a 5-second `statement_timeout`.
- **Semantic Column Resolution:** Automatically maps business terms (e.g., `pricing` → `price`, `shipping` → `freight_value`, `rating` → `review_score`) and normalizes mixed-case identifiers with PostgreSQL double quotes.
- **Self-Correction Retry Loop:** Automatically feeds validator rejections and PostgreSQL runtime errors back to the LLM for up to 3 attempts before failing.
- **Explicit Write Refusal:** Rejects requests to create, alter, or delete tables/columns instead of fabricating dummy columns.

---

## Setup & Usage

### 1. Clone & Create Virtual Environment
```bash
git clone <your-repo-url>
cd ask-your-data
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file in the project root:
```env
POSTGRES_USER=your_admin_user
POSTGRES_PASSWORD=your_admin_password
POSTGRES_DB=your_db_name
POSTGRES_HOST=localhost
POSTGRES_PORT=5433

POSTGRES_READONLY_USER=readonly_user
POSTGRES_READONLY_PASSWORD=your_readonly_password

OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=google/gemini-3.7-flash
```

### 3. Start PostgreSQL & Create the Read-Only Role
```bash
docker compose up -d
set -a && source .env && set +a
docker exec -i ask-your-data psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" << EOF
CREATE ROLE $POSTGRES_READONLY_USER WITH LOGIN PASSWORD '$POSTGRES_READONLY_PASSWORD';
GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO $POSTGRES_READONLY_USER;
GRANT USAGE ON SCHEMA public TO $POSTGRES_READONLY_USER;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO $POSTGRES_READONLY_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO $POSTGRES_READONLY_USER;
EOF
```

### 4. Load CSV Data & Run
```bash
python app/load_data.py
python app/main.py
```

---

## Example Questions

- *"What are the top 5 product categories by total pricing?"*
- *"What is the average rating by payment type?"*
- *"Which 10 sellers generated the highest item revenue, along with their city?"*
