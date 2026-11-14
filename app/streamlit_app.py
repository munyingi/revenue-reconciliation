"""
Revenue reconciliation explorer.

    streamlit run app/streamlit_app.py

Reads the Parquet snapshot in app/data/ (exported from Snowflake or DuckDB by
pipeline/export_marts.py), so it runs on Streamlit Community Cloud without credentials.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from charts import eur, waterfall

DATA = Path(__file__).parent / "data"

st.set_page_config(page_title="Revenue reconciliation", page_icon="📒", layout="wide")


@st.cache_data
def load():
    return {p.stem: pd.read_parquet(p) for p in DATA.glob("*.parquet")}


d = load()
s = d["recon_summary"].iloc[0]
bridge = d["recon_bridge"]
lines = d["recon_line_items"]
month = pd.Timestamp(s["recon_month"]).strftime("%B %Y")

try:
    mode = "dark" if st.context.theme.type == "dark" else "light"
except Exception:
    mode = "light"

st.title(f"Revenue reconciliation · {month}")
st.caption(
    "Kuura Outdoor Oy (fictional). Why the Sales dashboard and the CFO report disagree, "
    "explained down to the individual order, payment event and refund."
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Sales dashboard", eur(s["dashboard_total_eur"]), help="Orders placed (Helsinki month), net of approved refunds")
c2.metric("CFO report", eur(s["cfo_total_eur"]), help="Cash captured (UTC month), net of refunds paid out")
c3.metric("Gap", eur(s["gap_eur"]), help=f"{int(s['explained_line_count']):,} labelled lines")
unexplained = float(s["unexplained_eur"])
c4.metric("Unexplained", eur(unexplained), "Fully explained" if abs(unexplained) < 0.005 else "Needs investigation",
          delta_color="normal" if abs(unexplained) < 0.005 else "inverse")

tab_bridge, tab_lines, tab_months, tab_method = st.tabs(["Bridge", "Line items", "By month", "How it works"])

with tab_bridge:
    st.subheader("From the CFO number to the dashboard number")
    st.plotly_chart(waterfall(bridge, mode), width="stretch", config={"displayModeBar": False})

    steps = bridge[bridge["step_type"] == "difference"].sort_values("step_order")
    table = pd.DataFrame(
        {
            "Difference": steps["label"],
            "What happened": steps["explanation"],
            "Lines": steps["line_count"],
            "Impact (€)": steps["amount_eur"],
        }
    )
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        column_config={"Impact (€)": st.column_config.NumberColumn(format="%+,.2f")},
    )
    st.caption("Impact = dashboard minus CFO. Positive means the dashboard counts money that finance does not.")

with tab_lines:
    st.subheader("Every labelled difference")
    labels = bridge.dropna(subset=["line_count"]).set_index("difference_type")["label"].to_dict()
    f1, f2 = st.columns([2, 1])
    chosen = f1.multiselect("Difference type", options=list(labels), format_func=labels.get, default=list(labels))
    search = f2.text_input("Order, payment or refund ID", placeholder="e.g. 105105 or pay_505105")

    view = lines[lines["difference_type"].isin(chosen)].copy()
    if search.strip():
        q = search.strip().lower()
        view = view[
            view["order_id"].astype("string").str.contains(q, na=False)
            | view["payment_id"].astype("string").str.lower().str.contains(q, na=False)
            | view["refund_id"].astype("string").str.lower().str.contains(q, na=False)
            | view["event_id"].astype("string").str.lower().str.contains(q, na=False)
        ]
    view["difference_type"] = view["difference_type"].map(labels)
    cols = ["difference_type", "order_id", "payment_id", "refund_id", "event_id", "payment_method",
            "order_created_at_helsinki", "money_moved_at_utc", "money_moved_at_helsinki",
            "dashboard_amount_eur", "cfo_amount_eur", "difference_eur"]
    st.caption(f"{len(view):,} lines · net impact {eur(view['difference_eur'].sum(), signed=True)}")
    st.dataframe(
        view[cols].sort_values("difference_eur", key=abs, ascending=False),
        hide_index=True,
        width="stretch",
        height=480,
        column_config={
            "difference_type": "Difference",
            "order_id": st.column_config.NumberColumn("Order", format="%d"),
            "payment_id": "Payment",
            "refund_id": "Refund",
            "event_id": "PSP event",
            "payment_method": "Method",
            "order_created_at_helsinki": st.column_config.DatetimeColumn("Ordered (Helsinki)", format="D MMM HH:mm"),
            "money_moved_at_utc": st.column_config.DatetimeColumn("Money moved (UTC)", format="D MMM HH:mm"),
            "money_moved_at_helsinki": st.column_config.DatetimeColumn("Money moved (Helsinki)", format="D MMM HH:mm"),
            "dashboard_amount_eur": st.column_config.NumberColumn("Dashboard €", format="%,.2f"),
            "cfo_amount_eur": st.column_config.NumberColumn("CFO €", format="%,.2f"),
            "difference_eur": st.column_config.NumberColumn("Difference €", format="%+,.2f"),
        },
    )
    st.download_button("Download CSV", view[cols].to_csv(index=False), file_name="recon_line_items.csv", mime="text/csv")

with tab_months:
    st.subheader("Both reports, month by month")
    dash = d["rpt_sales_dashboard__monthly"][["revenue_month", "net_sales_eur"]]
    cfo = d["rpt_cfo_revenue__monthly"][["revenue_month", "net_revenue_eur"]]
    m = dash.merge(cfo, on="revenue_month", how="outer").sort_values("revenue_month")
    m["gap_eur"] = m["net_sales_eur"].fillna(0) - m["net_revenue_eur"].fillna(0)
    m["revenue_month"] = pd.to_datetime(m["revenue_month"]).dt.strftime("%b %Y")
    st.dataframe(
        m.rename(columns={"revenue_month": "Month", "net_sales_eur": "Sales dashboard €",
                          "net_revenue_eur": "CFO report €", "gap_eur": "Gap €"}),
        hide_index=True,
        width="stretch",
        column_config={c: st.column_config.NumberColumn(format="%,.2f")
                       for c in ["Sales dashboard €", "CFO report €", "Gap €"]},
    )
    st.caption(
        "Only October is closed. September and November are partial (the extract covers 1 Sep to 10 Nov), "
        "which is why their gaps are large. Rerun dbt with --vars '{recon_month: 2026-09-01}' to reconcile another month."
    )

with tab_method:
    st.subheader("Why the two numbers differ")
    a, b = st.columns(2)
    a.markdown(
        """**Sales dashboard**
- Source: order system
- Month = order placed, **Helsinki** wall clock
- Every order counts, paid or not
- Refunds netted when customer service **approves** them"""
    )
    b.markdown(
        """**CFO report**
- Source: payment provider + refund tool
- Month = money captured, **UTC**
- Every capture event the provider sent, duplicates included
- Refunds deducted when the money is actually **returned**"""
    )
    st.markdown(
        """
**Matching logic**
1. Deduplicate provider events on `(payment_id, event_status)`. Extra deliveries become *duplicate payment* lines.
2. Match payments to orders by parsing the provider reference (`ORD00105105` → order `105105`), full outer join so orphans surface.
3. Match refunds to orders through the payment (`refund → payment → order`), because the refund tool never sees order IDs.
4. For every order, payment event and refund, compute what each report counted. Any non-zero difference gets one label.
5. Check: dashboard total − CFO total − sum of labelled differences = **€0.00**. A dbt test fails the build otherwise.
"""
    )
