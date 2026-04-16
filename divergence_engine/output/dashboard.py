"""Streamlit web dashboard for the Divergence Engine."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# Resolve database path
_project_root = Path(__file__).resolve().parent.parent.parent
_default_db = _project_root / "data" / "divergence.db"


def get_conn() -> sqlite3.Connection:
    db_path = str(_default_db)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# --- Page Config ---
st.set_page_config(
    page_title="Divergence Engine",
    page_icon="📊",
    layout="wide",
)

st.title("Prediction Market × Financial Market Divergence Engine")

# --- Sidebar ---
st.sidebar.header("Filters")
limit = st.sidebar.slider("Top N results", 5, 50, 10)
min_zscore = st.sidebar.slider("Min |Z-Score|", 0.0, 5.0, 0.0, step=0.1)
window_filter = st.sidebar.selectbox("Window (hours)", [24, 48, 72, 168], index=0)

# --- Load Data ---
try:
    conn = get_conn()

    # Top divergences
    df_drift = pd.read_sql_query(
        """SELECT * FROM drift_records
           WHERE ABS(z_score) >= ?
           ORDER BY ABS(z_score) DESC, timestamp DESC
           LIMIT ?""",
        conn,
        params=(min_zscore, limit),
    )

    # Mapping cache
    df_mappings = pd.read_sql_query("SELECT * FROM mapping_cache", conn)

    conn.close()
except Exception as e:
    st.error(f"Database error: {e}")
    st.info("Run `divergence-engine run` first to populate the database.")
    st.stop()

# --- Tab Layout ---
tab_overview, tab_detail, tab_mappings = st.tabs(["Overview", "Detail View", "Mappings"])

# --- Overview Tab ---
with tab_overview:
    if df_drift.empty:
        st.info("No drift records yet. Run the pipeline first: `divergence-engine run`")
    else:
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Records", len(df_drift))
        anomalies = len(df_drift[df_drift["z_score"].abs() >= 2.0]) if "z_score" in df_drift else 0
        col2.metric("Anomalies (|Z|≥2)", anomalies)

        leads = len(df_drift[df_drift["signal_type"] == "lead"])
        col3.metric("Lead Signals", leads)

        divergences = len(df_drift[df_drift["signal_type"] == "divergence"])
        col4.metric("Divergences", divergences)

        # Signal distribution
        st.subheader("Signal Distribution")
        if "signal_type" in df_drift.columns:
            signal_counts = df_drift["signal_type"].value_counts()
            fig_pie = go.Figure(data=[go.Pie(
                labels=signal_counts.index.tolist(),
                values=signal_counts.values.tolist(),
                hole=0.4,
                marker_colors=["#EF553B", "#FECB52", "#00CC96", "#636EFA", "#AB63FA"],
            )])
            fig_pie.update_layout(height=300, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig_pie, use_container_width=True)

        # Top divergences table
        st.subheader("Top Divergences")
        display_cols = [
            "event_slug", "ticker", "delta_p", "delta_a_normalized",
            "drift", "z_score", "signal_type", "window_hours",
        ]
        available = [c for c in display_cols if c in df_drift.columns]
        st.dataframe(
            df_drift[available].style.format({
                "delta_p": "{:.4f}",
                "delta_a_normalized": "{:.4f}",
                "drift": "{:+.4f}",
                "z_score": "{:.2f}",
            }),
            use_container_width=True,
            height=400,
        )

# --- Detail Tab ---
with tab_detail:
    if df_drift.empty:
        st.info("No data available.")
    else:
        # Select event-ticker pair
        pairs = df_drift[["event_slug", "ticker"]].drop_duplicates()
        pair_options = [f"{r['event_slug']} / {r['ticker']}" for _, r in pairs.iterrows()]

        if pair_options:
            selected = st.selectbox("Select Event-Ticker Pair", pair_options)
            slug, ticker = selected.split(" / ")

            try:
                conn = get_conn()

                # Get prediction history
                df_pred = pd.read_sql_query(
                    """SELECT timestamp, probability FROM prediction_snapshots
                       WHERE event_slug = ? ORDER BY timestamp ASC""",
                    conn,
                    params=(slug,),
                )

                # Get asset history
                df_asset = pd.read_sql_query(
                    """SELECT timestamp, close_price FROM asset_snapshots
                       WHERE ticker = ? ORDER BY timestamp ASC""",
                    conn,
                    params=(ticker,),
                )

                # Get drift history
                df_pair_drift = pd.read_sql_query(
                    """SELECT timestamp, drift, z_score, signal_type
                       FROM drift_records
                       WHERE event_slug = ? AND ticker = ?
                       ORDER BY timestamp ASC""",
                    conn,
                    params=(slug, ticker),
                )

                conn.close()

                # Price overlay chart
                if not df_pred.empty and not df_asset.empty:
                    st.subheader(f"Price Overlay: {slug} vs {ticker}")

                    df_pred["datetime"] = pd.to_datetime(df_pred["timestamp"], unit="s")
                    df_asset["datetime"] = pd.to_datetime(df_asset["timestamp"], unit="s")

                    fig = make_subplots(specs=[[{"secondary_y": True}]])
                    fig.add_trace(
                        go.Scatter(
                            x=df_pred["datetime"], y=df_pred["probability"],
                            name="Probability", line=dict(color="#636EFA"),
                        ),
                        secondary_y=False,
                    )
                    fig.add_trace(
                        go.Scatter(
                            x=df_asset["datetime"], y=df_asset["close_price"],
                            name=f"{ticker} Price", line=dict(color="#EF553B"),
                        ),
                        secondary_y=True,
                    )
                    fig.update_yaxes(title_text="Probability", secondary_y=False)
                    fig.update_yaxes(title_text=f"{ticker} Price ($)", secondary_y=True)
                    fig.update_layout(height=400, hovermode="x unified")
                    st.plotly_chart(fig, use_container_width=True)

                # Drift chart
                if not df_pair_drift.empty:
                    st.subheader("Drift & Z-Score Over Time")

                    df_pair_drift["datetime"] = pd.to_datetime(
                        df_pair_drift["timestamp"], unit="s"
                    )

                    fig2 = make_subplots(specs=[[{"secondary_y": True}]])
                    fig2.add_trace(
                        go.Scatter(
                            x=df_pair_drift["datetime"], y=df_pair_drift["drift"],
                            name="Drift", line=dict(color="#00CC96"),
                        ),
                        secondary_y=False,
                    )
                    if "z_score" in df_pair_drift.columns:
                        fig2.add_trace(
                            go.Scatter(
                                x=df_pair_drift["datetime"], y=df_pair_drift["z_score"],
                                name="Z-Score", line=dict(color="#FECB52", dash="dash"),
                            ),
                            secondary_y=True,
                        )
                        # Z-score threshold bands
                        fig2.add_hline(y=2.0, line_dash="dot", line_color="red",
                                       annotation_text="Z=2", secondary_y=True)
                        fig2.add_hline(y=-2.0, line_dash="dot", line_color="red",
                                       annotation_text="Z=-2", secondary_y=True)

                    fig2.update_yaxes(title_text="Drift", secondary_y=False)
                    fig2.update_yaxes(title_text="Z-Score", secondary_y=True)
                    fig2.update_layout(height=400, hovermode="x unified")
                    st.plotly_chart(fig2, use_container_width=True)

            except Exception as e:
                st.error(f"Error loading detail: {e}")

# --- Mappings Tab ---
with tab_mappings:
    if df_mappings.empty:
        st.info("No resolved mappings yet. Run: `divergence-engine resolve`")
    else:
        st.subheader("Resolved Event-Asset Mappings")
        st.dataframe(df_mappings, use_container_width=True)
