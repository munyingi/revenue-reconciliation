"""
Snapshot the reconciliation marts to Parquet (app/data/) so the static report and the
Streamlit app can run without warehouse credentials (e.g. on Streamlit Community Cloud).

    python pipeline/export_marts.py --target snowflake
    python pipeline/export_marts.py --target duckdb
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "app" / "data"

TABLES = {
    "recon_summary": "reconciliation.recon_summary",
    "recon_bridge": "reconciliation.recon_bridge",
    "recon_line_items": "reconciliation.recon_line_items",
    "rpt_sales_dashboard__monthly": "reports.rpt_sales_dashboard__monthly",
    "rpt_cfo_revenue__monthly": "reports.rpt_cfo_revenue__monthly",
}


def fetch_duckdb():
    import duckdb

    con = duckdb.connect(str(ROOT / "data" / "warehouse.duckdb"), read_only=True)
    return {name: con.execute(f"select * from {fq}").df() for name, fq in TABLES.items()}


def fetch_snowflake():
    import snowflake.connector

    con = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.environ.get("SNOWFLAKE_ROLE", "RECON_ROLE"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "RECON_WH"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "REVENUE_RECON"),
    )
    out = {}
    for name, fq in TABLES.items():
        df = con.cursor().execute(f"select * from {fq}").fetch_pandas_all()
        df.columns = [c.lower() for c in df.columns]
        out[name] = df
    con.close()
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--target", choices=["duckdb", "snowflake"], default="duckdb")
    args = p.parse_args()
    frames = fetch_duckdb() if args.target == "duckdb" else fetch_snowflake()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in frames.items():
        for col in df.columns:  # Decimal -> float for portable Parquet; values are 2-dp money
            if df[col].dtype == object and len(df) and type(df[col].dropna().iloc[0]).__name__ == "Decimal":
                df[col] = df[col].astype(float)
        df.to_parquet(OUT_DIR / f"{name}.parquet", index=False)
        print(f"{name}: {len(df)} rows -> app/data/{name}.parquet")
