from __future__ import annotations

import uuid

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .models import ScoredCandidate
from .vcp_detector import segment_swings


def render_candidate_chart_html(frame: pd.DataFrame, candidate: ScoredCandidate) -> str:
    plot_id = f"chart_{candidate.symbol}_{uuid.uuid4().hex[:8]}"
    plot_frame = frame.copy().tail(180)
    swings = segment_swings(plot_frame, min_bars_between_swings=3, pct_reversal=0.04, atr_multiplier=0.2)

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.72, 0.28],
        specs=[[{"secondary_y": False}], [{"secondary_y": False}]],
    )

    fig.add_trace(
        go.Candlestick(
            x=plot_frame['Date'],
            open=plot_frame['Open'],
            high=plot_frame['High'],
            low=plot_frame['Low'],
            close=plot_frame['Close'],
            name='K线',
        ),
        row=1,
        col=1,
    )

    for ma, color in [('SMA50', '#1f77b4'), ('SMA150', '#9467bd'), ('SMA200', '#2ca02c')]:
        if ma in plot_frame.columns:
            fig.add_trace(
                go.Scatter(x=plot_frame['Date'], y=plot_frame[ma], mode='lines', name=ma, line=dict(width=1.2, color=color)),
                row=1,
                col=1,
            )


    if candidate.vcp.pivot_price is not None:
        fig.add_hline(
            y=candidate.vcp.pivot_price,
            line_dash='dash',
            line_color='green',
            annotation_text=f"Pivot {candidate.vcp.pivot_price:.2f}",
            row=1,
            col=1,
        )

    for swing in swings[-8:]:
        color = 'crimson' if swing.kind == 'high' else 'royalblue'
        fig.add_trace(
            go.Scatter(
                x=[plot_frame.iloc[swing.index]['Date']],
                y=[swing.price],
                mode='markers+text',
                text=['H' if swing.kind == 'high' else 'L'],
                textposition='top center',
                marker=dict(size=7, color=color),
                name=f"Swing {swing.kind}",
                showlegend=False,
            ),
            row=1,
            col=1,
        )

    volume_colors = ['#d62728' if c >= o else '#2ca02c' for c, o in zip(plot_frame['Close'], plot_frame['Open'])]
    fig.add_trace(
        go.Bar(x=plot_frame['Date'], y=plot_frame['Volume'], name='成交量', marker_color=volume_colors),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=f"{candidate.symbol} — {candidate.setup_tier} / {candidate.grade}",
        xaxis_rangeslider_visible=False,
        template='plotly_white',
        height=560,
        margin=dict(l=40, r=20, t=50, b=30),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
    )
    fig.update_yaxes(title_text='价格', row=1, col=1)
    fig.update_yaxes(title_text='成交量', row=2, col=1)
    return fig.to_html(include_plotlyjs='cdn', full_html=False, div_id=plot_id)
