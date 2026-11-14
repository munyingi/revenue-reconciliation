"""
Load the three raw source extracts into the warehouse RAW schema.

    python pipeline/load_raw.py --target snowflake   # PUT to internal stage + COPY INTO
    python pipeline/load_raw.py --target duckdb      # local file data/warehouse.duckdb

Snowflake credentials come from environment variables (see .env.example).
Tables are created with explicit types so money stays exact (NUMBER(12,2)).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DUCKDB_PATH = ROOT / "data" / "warehouse.duckdb"

TABLES = {
    "shop_orders": [
        ("order_id", "INTEGER"),
        ("order_number", "VARCHAR"),
        ("created_at", "TIMESTAMP"),          # naive, Helsinki wall clock
        ("customer_country", "VARCHAR"),
        ("currency", "VARCHAR"),
        ("order_total_local", "DECIMAL(12,2)"),
        ("order_total_eur", "DECIMAL(12,2)"),
        ("payment_method", "VARCHAR"),
        ("status", "VARCHAR"),
        ("refunded_amount_eur", "DECIMAL(12,2)"),
    ],
    "psp_payment_events": [
        ("event_id", "VARCHAR"),
        ("payment_id", "VARCHAR"),
        ("merchant_reference", "VARCHAR"),
        ("event_type", "VARCHAR"),
        ("payment_method", "VARCHAR"),
        ("currency", "VARCHAR"),
        ("amount_local", "DECIMAL(12,2)"),
        ("settled_amount_eur", "DECIMAL(12,2)"),
        ("event_timestamp_utc", "TIMESTAMP"),
        ("received_at_utc", "TIMESTAMP"),
    ],
    "refunds": [
        ("refund_id", "VARCHAR"),
        ("payment_id", "VARCHAR"),
        ("amount_eur", "DECIMAL(12,2)"),
        ("reason", "VARCHAR"),
        ("requested_at_utc", "TIMESTAMP"),
        ("processed_at_utc", "TIMESTAMP"),
        ("status", "VARCHAR"),
    ],
}


def snowflake_type(t: str) -> str:
    return {"TIMESTAMP": "TIMESTAMP_NTZ", "INTEGER": "NUMBER(38,0)"}.get(t, t.replace("DECIMAL", "NUMBER"))


def load_duckdb():
    import duckdb

    DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DUCKDB_PATH))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    for table, cols in TABLES.items():
        col_types = "{" + ", ".join(f"'{c}': '{t}'" for c, t in cols) + "}"
        con.execute(f"DROP TABLE IF EXISTS raw.{table}")
        con.execute(
            f"""CREATE TABLE raw.{table} AS
                SELECT * FROM read_csv('{RAW_DIR / (table + '.csv')}',
                                       header = true, columns = {col_types})"""
        )
        n = con.execute(f"SELECT count(*) FROM raw.{table}").fetchone()[0]
        print(f"duckdb raw.{table}: {n} rows")
    con.close()


def load_snowflake():
    import snowflake.connector

    con = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.environ.get("SNOWFLAKE_ROLE", "RECON_ROLE"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "RECON_WH"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "REVENUE_RECON"),
        schema="RAW",
    )
    cur = con.cursor()
    cur.execute(
        """CREATE FILE FORMAT IF NOT EXISTS raw_csv
           TYPE = CSV SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"'
           EMPTY_FIELD_AS_NULL = TRUE NULL_IF = ('')"""
    )
    cur.execute("CREATE STAGE IF NOT EXISTS raw_stage FILE_FORMAT = raw_csv")
    for table, cols in TABLES.items():
        ddl = ", ".join(f"{c} {snowflake_type(t)}" for c, t in cols)
        cur.execute(f"CREATE OR REPLACE TABLE {table} ({ddl})")
        path = (RAW_DIR / f"{table}.csv").as_posix()
        cur.execute(f"PUT 'file://{path}' @raw_stage/{table}/ AUTO_COMPRESS = TRUE OVERWRITE = TRUE")
        cur.execute(f"COPY INTO {table} FROM @raw_stage/{table}/ FILE_FORMAT = (FORMAT_NAME = raw_csv) ON_ERROR = ABORT_STATEMENT")
        n = cur.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        print(f"snowflake RAW.{table.upper()}: {n} rows")
    cur.close()
    con.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--target", choices=["duckdb", "snowflake"], default="duckdb")
    args = p.parse_args()
    load_duckdb() if args.target == "duckdb" else load_snowflake()
