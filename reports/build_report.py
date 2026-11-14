"""
Build the static reconciliation report from the Parquet snapshot.

    python reports/build_report.py        ->  docs/index.html  (served by GitHub Pages)
"""

from __future__ import annotations

import html
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from charts import eur, waterfall  # noqa: E402

DATA = ROOT / "app" / "data"
OUT = ROOT / "docs" / "index.html"


def load():
    return {p.stem: pd.read_parquet(p) for p in DATA.glob("*.parquet")}


def fmt_ts(x):
    return "" if pd.isna(x) else pd.Timestamp(x).strftime("%d %b %H:%M")


def examples_table(lines: pd.DataFrame, difference_type: str, n: int = 3) -> str:
    df = lines[lines["difference_type"] == difference_type].copy()
    df = df.reindex(df["difference_eur"].abs().sort_values(ascending=False).index).head(n)
    rows = []
    for _, r in df.iterrows():
        ref = r["refund_id"] if pd.notna(r["refund_id"]) else (r["event_id"] if pd.notna(r["event_id"]) else "")
        rows.append(
            "<tr>"
            f"<td>{'' if pd.isna(r['order_id']) else int(r['order_id'])}</td>"
            f"<td>{html.escape(str(r['payment_id'] or ''))}</td>"
            f"<td>{html.escape(str(ref))}</td>"
            f"<td>{fmt_ts(r['order_created_at_helsinki'])}</td>"
            f"<td>{fmt_ts(r['money_moved_at_utc'])}</td>"
            f"<td class='num'>{eur(r['dashboard_amount_eur'])}</td>"
            f"<td class='num'>{eur(r['cfo_amount_eur'])}</td>"
            f"<td class='num'><b>{eur(r['difference_eur'], signed=True)}</b></td>"
            "</tr>"
        )
    return (
        "<table class='mini'><thead><tr><th>Order</th><th>Payment</th><th>Refund / event</th>"
        "<th>Ordered (Helsinki)</th><th>Money moved (UTC)</th><th class='num'>Dashboard</th>"
        "<th class='num'>CFO</th><th class='num'>Difference</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def main():
    d = load()
    s = d["recon_summary"].iloc[0]
    bridge = d["recon_bridge"]
    lines = d["recon_line_items"]
    month = pd.Timestamp(s["recon_month"]).strftime("%B %Y")

    light = waterfall(bridge, "light").to_html(full_html=False, include_plotlyjs="cdn", config={"displayModeBar": False})
    dark = waterfall(bridge, "dark").to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": False})

    steps = bridge[bridge["step_type"] == "difference"].sort_values("step_order")
    gross = steps["amount_eur"].abs().sum()
    rows, details = [], []
    for _, r in steps.iterrows():
        n = "" if pd.isna(r["line_count"]) else f"{int(r['line_count']):,}"
        direction = "up" if r["amount_eur"] > 0 else "down" if r["amount_eur"] < 0 else "zero"
        rows.append(
            f"<tr><td><span class='dot {direction}'></span>{html.escape(r['label'])}</td>"
            f"<td class='muted'>{html.escape(r['explanation'] or '')}</td>"
            f"<td class='num'>{n}</td>"
            f"<td class='num'><b>{eur(r['amount_eur'], signed=True)}</b></td>"
            f"<td class='num muted'>{(abs(r['amount_eur']) / gross * 100) if gross else 0:.1f}%</td></tr>"
        )
        if r["difference_type"] != "unexplained":
            details.append(
                f"<details><summary><b>{html.escape(r['label'])}</b> "
                f"<span class='muted'>· {n} lines · {eur(r['amount_eur'], signed=True)}</span></summary>"
                f"<p class='muted'>Largest examples:</p>{examples_table(lines, r['difference_type'])}</details>"
            )

    ok = abs(float(s["unexplained_eur"])) < 0.005
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Revenue reconciliation · {month}</title>
<style>
  :root {{ --surface:#fcfcfb; --page:#f9f9f7; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
           --grid:#e1e0d9; --border:rgba(11,11,11,.10); --up:#2a78d6; --down:#e34948; --good:#006300; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --surface:#1a1a19; --page:#0d0d0d; --ink:#f0efec; --ink2:#c3c2b7; --muted:#898781;
             --grid:#2c2c2a; --border:rgba(255,255,255,.10); --up:#3987e5; --down:#e66767; --good:#0ca30c; }}
    .chart-light {{ display:none; }} .chart-dark {{ display:block !important; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--page); color:var(--ink);
         font:15px/1.55 Inter, system-ui, -apple-system, "Segoe UI", sans-serif; }}
  main {{ max-width:1040px; margin:0 auto; padding:40px 20px 64px; }}
  h1 {{ font-size:28px; margin:0 0 6px; letter-spacing:-.01em; }}
  h2 {{ font-size:18px; margin:40px 0 12px; }}
  .lede {{ color:var(--ink2); max-width:760px; margin:0 0 28px; }}
  .tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:12px; }}
  .tile {{ background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:16px 18px; }}
  .tile .k {{ color:var(--ink2); font-size:13px; }}
  .tile .v {{ font-size:26px; font-weight:650; margin-top:4px; font-variant-numeric:tabular-nums; }}
  .tile .s {{ color:var(--muted); font-size:12px; margin-top:2px; }}
  .tile.ok .v {{ color:var(--good); }}
  .card {{ background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:16px; }}
  table {{ width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }}
  th {{ text-align:left; font-weight:600; color:var(--ink2); font-size:13px; padding:8px 10px; border-bottom:1px solid var(--grid); }}
  td {{ padding:9px 10px; border-bottom:1px solid var(--grid); vertical-align:top; }}
  .num {{ text-align:right; white-space:nowrap; }}
  .muted {{ color:var(--ink2); }}
  .dot {{ display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:8px; background:var(--muted); }}
  .dot.up {{ background:var(--up); }} .dot.down {{ background:var(--down); }}
  details {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:12px 14px; margin:8px 0; }}
  summary {{ cursor:pointer; }}
  table.mini td, table.mini th {{ font-size:13px; padding:6px 8px; }}
  .two {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:12px; }}
  .two h3 {{ margin:0 0 6px; font-size:15px; }}
  .two ul {{ margin:0; padding-left:18px; color:var(--ink2); }}
  .scroll {{ overflow-x:auto; }}
  footer {{ color:var(--muted); font-size:13px; margin-top:48px; }}
  code {{ font-size:13px; }}
</style>
</head>
<body>
<main>
  <h1>Revenue reconciliation · {month}</h1>
  <p class="lede">Kuura Outdoor Oy (fictional). The Sales dashboard and the CFO report disagree by
  <b>{eur(s['gap_eur'])}</b>. Every euro of that gap is traced to an individual order, payment event or refund
  and labelled with the reason. What is left unexplained: <b>{eur(s['unexplained_eur'])}</b>.</p>

  <div class="tiles">
    <div class="tile"><div class="k">Sales dashboard</div><div class="v">{eur(s['dashboard_total_eur'])}</div><div class="s">Orders placed, Helsinki time</div></div>
    <div class="tile"><div class="k">CFO report</div><div class="v">{eur(s['cfo_total_eur'])}</div><div class="s">Cash captured, UTC</div></div>
    <div class="tile"><div class="k">Gap</div><div class="v">{eur(s['gap_eur'])}</div><div class="s">{int(s['explained_line_count']):,} labelled lines</div></div>
    <div class="tile {'ok' if ok else ''}"><div class="k">Unexplained</div><div class="v">{eur(s['unexplained_eur'])}</div><div class="s">{'✓ Gap fully explained' if ok else '✗ Needs investigation'}</div></div>
  </div>

  <h2>From the CFO number to the dashboard number</h2>
  <div class="card">
    <div class="chart-light">{light}</div>
    <div class="chart-dark" style="display:none">{dark}</div>
  </div>

  <h2>What explains the gap</h2>
  <div class="card scroll">
    <table>
      <thead><tr><th>Difference</th><th>What happened</th><th class="num">Lines</th><th class="num">Impact</th><th class="num">Share of movement</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>
  <p class="muted" style="font-size:13px">Impact = dashboard minus CFO. Positive lines are money the dashboard counts and finance does not.</p>

  <h2>Drill into each difference</h2>
  <div class="scroll">{''.join(details)}</div>

  <h2>How each number is calculated</h2>
  <div class="two">
    <div class="card"><h3>Sales dashboard</h3><ul>
      <li>Source: order system</li>
      <li>Month = order placed, <b>Helsinki</b> wall clock</li>
      <li>Every order counts, paid or not</li>
      <li>Refunds netted when customer service <b>approves</b> them</li></ul></div>
    <div class="card"><h3>CFO report</h3><ul>
      <li>Source: payment provider + refund tool</li>
      <li>Month = money captured, <b>UTC</b></li>
      <li>Every capture event the provider sent, duplicates included</li>
      <li>Refunds deducted when the money is actually <b>returned</b></li></ul></div>
  </div>

  <footer>Generated {generated} by the revenue-reconciliation pipeline (Snowflake + dbt).
  All data is synthetic. Source: <a href="https://github.com/munyingi">github.com/munyingi</a></footer>
</main>
</body>
</html>"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
