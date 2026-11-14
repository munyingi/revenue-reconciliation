"""Shared chart + formatting helpers for the static report and the Streamlit app."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# Validated palette (light / dark). Blue = pushes the dashboard number up vs the CFO number,
# red = pulls it down, neutral ink = the two reported totals.
THEME = {
    "light": dict(up="#2a78d6", down="#e34948", total="#52514e", surface="#fcfcfb",
                  ink="#0b0b0b", ink2="#52514e", muted="#898781", grid="#e1e0d9", axis="#c3c2b7"),
    "dark": dict(up="#3987e5", down="#e66767", total="#c3c2b7", surface="#1a1a19",
                 ink="#f0efec", ink2="#c3c2b7", muted="#898781", grid="#2c2c2a", axis="#383835"),
}


def eur(x: float, signed: bool = False) -> str:
    s = f"€{abs(x):,.2f}"
    if signed:
        return ("+" if x > 0 else "−" if x < 0 else "±") + s
    return ("−" if x < 0 else "") + s


def waterfall(bridge: pd.DataFrame, mode: str = "light", height: int = 460) -> go.Figure:
    t = THEME[mode]
    b = bridge.sort_values("step_order")
    measure = ["absolute" if s == "start" else "total" if s == "end" else "relative" for s in b["step_type"]]
    text = [eur(v) if s != "difference" else eur(v, signed=True) for v, s in zip(b["amount_eur"], b["step_type"])]
    counts = ["" if pd.isna(n) else f"{int(n)} lines" for n in b["line_count"]]

    fig = go.Figure(
        go.Waterfall(
            orientation="h",
            y=b["label"],
            x=b["amount_eur"],
            measure=measure,
            text=text,
            textposition="outside",
            textfont=dict(color=t["ink"], size=12),
            customdata=list(zip(counts, b["explanation"].fillna(""))),
            hovertemplate="<b>%{y}</b><br>%{text}  %{customdata[0]}<br><span style='font-size:11px'>%{customdata[1]}</span><extra></extra>",
            increasing=dict(marker=dict(color=t["up"])),
            decreasing=dict(marker=dict(color=t["down"])),
            totals=dict(marker=dict(color=t["total"])),
            connector=dict(line=dict(color=t["axis"], width=1)),
        )
    )
    lo = b["running_total_eur"].min()
    hi = b["running_total_eur"].max()
    pad = (hi - lo) * 0.35
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=30, t=10, b=30),
        paper_bgcolor=t["surface"],
        plot_bgcolor=t["surface"],
        font=dict(family="Inter, system-ui, -apple-system, Segoe UI, sans-serif", color=t["ink2"], size=12),
        showlegend=False,
        hoverlabel=dict(bgcolor=t["surface"], font_color=t["ink"], bordercolor=t["axis"]),
        xaxis=dict(range=[lo - pad, hi + pad * 0.6], gridcolor=t["grid"], zeroline=False,
                   tickprefix="€", tickformat=",.0f", tickfont=dict(color=t["muted"])),
        yaxis=dict(autorange="reversed", tickfont=dict(color=t["ink2"], size=12)),
        bargap=0.35,
    )
    return fig
