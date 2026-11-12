from pathlib import Path
import re
import pandas as pd

try:
    from app.database import engine
except ImportError:
    from database import engine

# DATA_DIR = Path(__file__).resolve().parent.parent / "data/raw/archive"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "archive"



def to_table_name(filename: str) -> str:
    """Convert a CSV filename into a clean, lowercase Postgres table name."""
    stem = Path(filename).stem.lower()
    return re.sub(r"[^a-z0-9_]+", "_", stem).strip("_")


def load_all_csvs(data_dir: Path = DATA_DIR) -> list[str]:
    csv_files = sorted(data_dir.rglob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {data_dir}")
        return []

    loaded_tables: list[str] = []
    for csv_path in csv_files:
        table_name = to_table_name(csv_path.name)
        df = pd.read_csv(csv_path)
        df.to_sql(table_name, engine, if_exists="replace", index=False)
        loaded_tables.append(table_name)
        print(f"Loaded {len(df)} rows into '{table_name}' from {csv_path.name}")

    return loaded_tables


if __name__ == "__main__":
    load_all_csvs()
