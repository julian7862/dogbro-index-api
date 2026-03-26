"""Plotly 圖表實作 (主力)

繪製 XQ 風格的 5 分 K IV 監控副圖。
"""

import pandas as pd
import plotly.graph_objects as go
from typing import List

from .models import IndicatorResult
from .validators import validate_panel_dataframe
from .annotations import build_top_annotations


# === XQ 風格配色 ===
COLORS = {
    'background': '#1a1a2e',      # 深色背景
    'grid': '#2a3f5f',            # 網格線
    'civ_pb_line': '#FFD700',     # 黃線 (CIV %b)
    'bar_positive': '#FF4444',    # 紅柱 (pb > 0)
    'bar_negative': '#00FF88',    # 綠柱 (pb < 0)
    'bar_zero': '#888888',        # 灰柱 (pb = 0)
    'axis_text': '#CCCCCC',       # 軸文字
    'title': '#00D9FF',           # 標題
}

# Y 軸固定範圍
Y_AXIS_RANGE = [0, 100]


def rows_to_dataframe(rows: List[IndicatorResult]) -> pd.DataFrame:
    """將 IndicatorResult 列表轉換為 DataFrame

    Args:
        rows: IndicatorResult 物件列表

    Returns:
        pd.DataFrame，欄位對應 IndicatorResult 屬性
    """
    if not rows:
        return pd.DataFrame()

    data = []
    for row in rows:
        data.append({
            'current_dt': row.current_dt,
            'underlying_price': row.underlying_price,
            'dte': row.dte,
            'valid_call_iv_count': row.valid_call_iv_count,
            'civ': row.civ,
            'civ_ma5': row.civ_ma5,
            'civ_pb': row.civ_pb,
            'price_pb': row.price_pb,
            'pb_minus_civ_pb': row.pb_minus_civ_pb,
            'warnings': row.warnings,
            'iv_spread': row.iv_spread,
            'strike_list': row.strike_list,
            # 策略預留欄位
            'signal_long_candidate': row.signal_long_candidate,
            'signal_short_candidate': row.signal_short_candidate,
            'regime_state': row.regime_state,
        })

    df = pd.DataFrame(data)
    df = df.sort_values('current_dt').reset_index(drop=True)
    return df


def plot_indicator_panel(
    df: pd.DataFrame,
    title: str = "5分K IV 指標副圖",
    height: int = 400,
    show_annotations: bool = True
) -> go.Figure:
    """繪製 IV 指標副圖

    Args:
        df: 包含指標資料的 DataFrame
        title: 圖表標題
        height: 圖表高度 (像素)
        show_annotations: 是否顯示圖上方數值

    Returns:
        plotly.graph_objects.Figure

    繪製內容:
        1. 黃線: civ_pb (CIV Bollinger %b)
        2. 紅綠柱: pb_minus_civ_pb (price_pb - civ_pb)
        3. 圖上方 annotation: 最新數值

    缺值處理:
        - civ_pb 缺失: 黃線該點中斷
        - pb_minus_civ_pb 缺失: 該根柱體不繪製
        - 全部缺失: 顯示空白副圖
    """
    # 驗證資料
    is_valid, missing = validate_panel_dataframe(df)

    # 建立圖表
    fig = go.Figure()

    if not is_valid or df.empty:
        # 空白圖表
        fig.update_layout(
            title=dict(text=title, font=dict(color=COLORS['title'])),
            paper_bgcolor=COLORS['background'],
            plot_bgcolor=COLORS['background'],
            height=height,
            yaxis=dict(range=Y_AXIS_RANGE),
            annotations=[{
                'text': '無資料',
                'xref': 'paper',
                'yref': 'paper',
                'x': 0.5,
                'y': 0.5,
                'showarrow': False,
                'font': {'size': 20, 'color': '#666666'}
            }]
        )
        return fig

    x_data = df['current_dt']

    # === 繪製紅綠柱 (pb_minus_civ_pb) ===
    if 'pb_minus_civ_pb' in df.columns:
        _add_bar_trace(fig, x_data, df['pb_minus_civ_pb'])

    # === 繪製黃線 (civ_pb) ===
    if 'civ_pb' in df.columns:
        _add_line_trace(fig, x_data, df['civ_pb'])

    # === 圖上方 annotation ===
    annotations = []
    if show_annotations:
        annotations = build_top_annotations(df)

    # === 套用 XQ 風格佈局 ===
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(color=COLORS['title'], size=16),
            x=0.5
        ),
        paper_bgcolor=COLORS['background'],
        plot_bgcolor=COLORS['background'],
        height=height,
        margin=dict(l=50, r=50, t=80, b=50),

        # X 軸
        xaxis=dict(
            showgrid=True,
            gridcolor=COLORS['grid'],
            tickfont=dict(color=COLORS['axis_text']),
            showline=True,
            linecolor=COLORS['grid']
        ),

        # Y 軸 (固定 0-100)
        yaxis=dict(
            range=Y_AXIS_RANGE,
            showgrid=True,
            gridcolor=COLORS['grid'],
            tickfont=dict(color=COLORS['axis_text']),
            side='right',  # Y 軸在右側
            showline=True,
            linecolor=COLORS['grid'],
            dtick=20  # 每 20 一個刻度
        ),

        # 圖例
        showlegend=True,
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='right',
            x=1,
            font=dict(color=COLORS['axis_text'])
        ),

        # Annotation
        annotations=annotations,

        # 互動設定
        hovermode='x unified'
    )

    return fig


def _add_bar_trace(
    fig: go.Figure,
    x_data: pd.Series,
    y_data: pd.Series
) -> None:
    """新增紅綠柱 trace

    顏色規則:
        - y > 0: 紅色
        - y < 0: 綠色
        - y == 0: 灰色
    """
    # 根據值分配顏色
    colors = y_data.apply(lambda v:
        COLORS['bar_positive'] if pd.notna(v) and v > 0
        else COLORS['bar_negative'] if pd.notna(v) and v < 0
        else COLORS['bar_zero']
    )

    fig.add_trace(go.Bar(
        x=x_data,
        y=y_data,
        name='pb-CIV_pb',
        marker=dict(color=colors.tolist()),
        opacity=0.7,
        hovertemplate='%{y:.2f}<extra>pb-CIV_pb</extra>'
    ))


def _add_line_trace(
    fig: go.Figure,
    x_data: pd.Series,
    y_data: pd.Series
) -> None:
    """新增黃線 trace (civ_pb)

    缺值處理: connectgaps=False，缺值點自動中斷
    """
    fig.add_trace(go.Scatter(
        x=x_data,
        y=y_data,
        name='CIV %b',
        mode='lines',
        line=dict(
            color=COLORS['civ_pb_line'],
            width=2
        ),
        connectgaps=False,  # 缺值不連接
        hovertemplate='%{y:.2f}<extra>CIV %b</extra>'
    ))


def render_panel_from_rows(
    rows: List[IndicatorResult],
    title: str = "5分K IV 指標副圖",
    height: int = 400,
    show_annotations: bool = True
) -> go.Figure:
    """一站式入口: 從 IndicatorResult 列表直接生成圖表

    Args:
        rows: IndicatorResult 物件列表
        title: 圖表標題
        height: 圖表高度
        show_annotations: 是否顯示圖上方數值

    Returns:
        plotly.graph_objects.Figure

    使用範例:
        ```python
        from visualization import IndicatorResult, render_panel_from_rows

        rows = [
            IndicatorResult(
                current_dt=datetime(2024, 1, 1, 9, 0),
                underlying_price=17500,
                dte=30,
                valid_call_iv_count=16,
                civ=0.18,
                civ_pb=35.5,
                price_pb=42.0,
                pb_minus_civ_pb=6.5
            ),
            # ... 更多資料
        ]

        fig = render_panel_from_rows(rows)
        fig.show()  # 或 fig.to_html()
        ```
    """
    df = rows_to_dataframe(rows)
    return plot_indicator_panel(
        df=df,
        title=title,
        height=height,
        show_annotations=show_annotations
    )
