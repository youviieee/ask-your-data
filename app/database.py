import os
from dotenv import load_dotenv
import pandas as pd
from sqlalchemy import create_engine, text, URL
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()

POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5433))

database = URL.create(
    username=POSTGRES_USER,
    password=POSTGRES_PASSWORD,
    database=POSTGRES_DB,
    host=POSTGRES_HOST,
    port=POSTGRES_PORT,
    drivername="postgresql+psycopg"
)

engine = create_engine(
    database,
    pool_pre_ping=True,
    connect_args={"options": "-c statement_timeout=5000"},
)


READONLY_USER = os.getenv("POSTGRES_READONLY_USER", POSTGRES_USER)
READONLY_PASSWORD = os.getenv("POSTGRES_READONLY_PASSWORD", POSTGRES_PASSWORD)

readonly_db = URL.create(
    username=READONLY_USER,
    password=READONLY_PASSWORD,
    database=POSTGRES_DB,
    host=POSTGRES_HOST,
    port=POSTGRES_PORT,
    drivername="postgresql+psycopg",
)

readonly_engine = create_engine(
    readonly_db,
    pool_pre_ping=True,
    connect_args={"options": "-c statement_timeout=5000"},
)




def execute_query(sql: str) -> tuple[list[str], list[tuple]]:
    try:
        with readonly_engine.connect() as connection:
            result = connection.execute(text(sql))
            columns = list(result.keys())
            rows = result.fetchall()
            return columns, rows
    except SQLAlchemyError as E:
        print(f"Database error executing query: {E}")
        raise


def query_to_dataframe(sql: str) -> pd.DataFrame:
    try:
        with readonly_engine.connect() as connection:
            return pd.read_sql(text(sql), connection)
    except SQLAlchemyError as E:
        print(f"Database error executing query to DataFrame: {E}")
        raise


if __name__ == "__main__":
    print("Testing database connection...")
    try:
        with engine.connect() as connection:
            version = connection.execute(text("SELECT VERSION()")).scalar()
            print("Connected successfully..")
            print(f"Version: {version}")
            print("\n")

        print("Testing sample query from 'pokemon' table...")
        df_sample = query_to_dataframe('SELECT "Name", "Type1", "Weight" FROM pokemon ORDER BY "Weight" DESC LIMIT 5;')
        print(df_sample)
    except Exception as E:
        print(f"Connection test failed: {E}")
