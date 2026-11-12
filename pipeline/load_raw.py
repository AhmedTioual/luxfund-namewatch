"""Step 1 - load the GLEIF extract files into the DuckDB warehouse (schema `raw`).

Every load is logged with the file fingerprint and row count, so a dashboard
figure can always be traced back to the exact file it came from.

    python -m pipeline.load_raw
"""

import hashlib
import sys
from datetime import UTC, datetime

import duckdb

from pipeline.config import CLASSIFICATIONS_FILE, OPTIONAL_FILES, RAW_DIR, RAW_FILES, WAREHOUSE

REQUIRED_COLUMNS = {
    "funds": {"lei", "legal_name", "entity_status", "initial_registration"},
    "name_changes": {"lei", "date", "old_name", "new_name"},
    "history_checked": {"lei"},
}


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(con: duckdb.DuckDBPyConnection) -> dict:
    con.execute("create schema if not exists raw")
    con.execute(
        """create table if not exists raw.load_log (
             loaded_at timestamp, table_name varchar, source_file varchar, sha256 varchar, row_count bigint)"""
    )
    loaded_at = datetime.now(UTC).replace(tzinfo=None)
    summary = {}
    for table, filename in RAW_FILES.items():
        path = RAW_DIR / filename
        if not path.exists():
            if table == "history_checked":
                # Older extracts have no history_checked.csv: assume the funds with a change were checked.
                con.execute(
                    "create or replace table raw.history_checked as "
                    "select distinct lei, count(*) over (partition by lei) as name_changes from raw.name_changes"
                )
                summary[table] = "derived from renames.csv (history_checked.csv not found)"
                continue
            sys.exit(f"Missing {path}. Copy the files produced by extract/gleif_extract.py into {RAW_DIR}.")
        cur = con.execute(f"select * from read_csv_auto('{path.as_posix()}', all_varchar=true) limit 0")
        cols = {d[0] for d in cur.description}
        missing = REQUIRED_COLUMNS[table] - cols
        if missing:
            sys.exit(f"{filename} is missing columns: {sorted(missing)}")
        con.execute(
            f"create or replace table raw.{table} as "
            f"select * from read_csv_auto('{path.as_posix()}', all_varchar=true, header=true)"
        )
        if table == "name_changes":  # older extracts have no `field` column
            con.execute("alter table raw.name_changes add column if not exists field varchar")
        n = con.execute(f"select count(*) from raw.{table}").fetchone()[0]
        con.execute("insert into raw.load_log values (?, ?, ?, ?, ?)", [loaded_at, table, filename, sha256(path), n])
        summary[table] = n

    # Optional relationship files: empty tables when they have not been extracted yet.
    for table, (filename, columns) in OPTIONAL_FILES.items():
        path = RAW_DIR / filename
        if path.exists():
            con.execute(
                f"create or replace table raw.{table} as "
                f"select * from read_csv_auto('{path.as_posix()}', all_varchar=true, header=true)"
            )
            n = con.execute(f"select count(*) from raw.{table}").fetchone()[0]
            log_row = [loaded_at, table, filename, sha256(path), n]
            con.execute("insert into raw.load_log values (?, ?, ?, ?, ?)", log_row)
            summary[table] = n
        else:
            con.execute(f"create or replace table raw.{table} ({columns})")
            summary[table] = f"0 ({filename} not found: run extract/gleif_extract.py --relationships)"

    # Optional AI classifications (written by ai/classify_names.py). An empty table keeps dbt happy.
    if CLASSIFICATIONS_FILE.exists():
        con.execute(
            "create or replace table raw.name_classifications as "
            f"select * from read_csv_auto('{CLASSIFICATIONS_FILE.as_posix()}', all_varchar=true, header=true)"
        )
    else:
        con.execute(
            """create or replace table raw.name_classifications (
                 lei varchar, change_date varchar, old_name varchar, new_name varchar, category varchar,
                 old_is_esg varchar, new_is_esg varchar, confidence varchar, rationale varchar, model varchar)"""
        )
    summary["name_classifications"] = con.execute("select count(*) from raw.name_classifications").fetchone()[0]
    return summary


def main() -> None:
    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(WAREHOUSE)) as con:
        for table, n in load(con).items():
            print(f"  raw.{table}: {n}")


if __name__ == "__main__":
    main()
