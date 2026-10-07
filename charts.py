"""charts.py — soft, theme-matched Altair charts (smooth lines, rounded bars, donuts)."""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

CORAL, ROSE, TEAL, VIOLET, MUTED, TRACK = "#ff7a6b", "#ee5a91", "#4fd1b0", "#8b7cf6", "#9a9bb5", "#222440"


def _style(chart: alt.Chart, height: int) -> alt.Chart:
    return (chart.properties(height=height, background="transparent")
            .configure_view(strokeWidth=0)
            .configure_axis(labelColor=MUTED, titleColor=MUTED, labelFont="Manrope", titleFont="Manrope",
                            gridColor="rgba(255,255,255,0.06)", domain=False, tickSize=0, labelPadding=8)
            .configure_legend(labelColor=MUTED, titleColor=MUTED, labelFont="Manrope", orient="top", title=None))


def show(chart) -> None:
    try:
        st.altair_chart(chart, width="stretch")
    except TypeError:
        st.altair_chart(chart, use_container_width=True)


def trend(df: pd.DataFrame, x: str, series: dict[str, str], height: int = 260) -> alt.Chart:
    """Smooth multi-series line with a soft area under the first series. ``series`` = {column: colour}."""
    long = df.melt(x, list(series), var_name="Series", value_name="Minutes")
    colors = alt.Scale(domain=list(series), range=list(series.values()))
    base = alt.Chart(long).encode(x=alt.X(f"{x}:N", sort=None, axis=alt.Axis(labelAngle=0, title=None)),
                                  y=alt.Y("Minutes:Q", axis=alt.Axis(title=None, tickCount=4)),
                                  color=alt.Color("Series:N", scale=colors))
    first = list(series)[0]
    grad = alt.Gradient(gradient="linear", x1=1, x2=1, y1=1, y2=0,
                        stops=[alt.GradientStop(color="rgba(255,122,107,0)", offset=0),
                               alt.GradientStop(color="rgba(255,122,107,0.35)", offset=1)])
    area = (alt.Chart(long[long["Series"] == first]).mark_area(interpolate="monotone", color=grad)
            .encode(x=alt.X(f"{x}:N", sort=None), y="Minutes:Q"))
    line = base.mark_line(interpolate="monotone", strokeWidth=3, point=alt.OverlayMarkDef(size=60, filled=True))
    return _style(area + line, height)


def bars(df: pd.DataFrame, x: str, y: str, color: str = CORAL, height: int = 240) -> alt.Chart:
    ch = (alt.Chart(df).mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8, color=color, size=28)
          .encode(x=alt.X(f"{x}:N", sort=None, axis=alt.Axis(labelAngle=0, title=None)),
                  y=alt.Y(f"{y}:Q", axis=alt.Axis(title=None, tickCount=4)), tooltip=[x, y]))
    return _style(ch, height)


def hbars(df: pd.DataFrame, label: str, value: str, height: int = 200) -> alt.Chart:
    """Horizontal progress bars (value 0-100) with a track behind."""
    track = alt.Chart(df).mark_bar(cornerRadius=8, color=TRACK, size=16).encode(
        y=alt.Y(f"{label}:N", sort=None, axis=alt.Axis(title=None)), x=alt.X("full:Q", scale=alt.Scale(domain=[0, 100]), axis=None))
    fill = alt.Chart(df).mark_bar(cornerRadius=8, size=16).encode(
        y=alt.Y(f"{label}:N", sort=None), x=alt.X(f"{value}:Q", scale=alt.Scale(domain=[0, 100])),
        color=alt.Color(f"{label}:N", legend=None, scale=alt.Scale(range=[CORAL, VIOLET, TEAL, ROSE, "#f5b94c"])),
        tooltip=[label, value])
    return _style(track + fill, height)


def donut(pct: float, color: str = CORAL, height: int = 170) -> alt.Chart:
    pct = max(0.0, min(100.0, pct))
    df = pd.DataFrame({"part": ["done", "left"], "v": [pct, 100 - pct]})
    arc = alt.Chart(df).mark_arc(innerRadius=58, outerRadius=78, cornerRadius=10).encode(
        theta=alt.Theta("v:Q"), color=alt.Color("part:N", legend=None, scale=alt.Scale(domain=["done", "left"], range=[color, TRACK])),
        order=alt.Order("part:N", sort="descending"))
    text = alt.Chart(pd.DataFrame({"t": [f"{pct:.0f}%"]})).mark_text(fontSize=26, color="#eceaf4", font="Fraunces").encode(text="t:N")
    return (arc + text).properties(height=height, width=height, background="transparent").configure_view(strokeWidth=0)
