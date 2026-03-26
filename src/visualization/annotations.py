"""圖表標註建構

建構圖上方的最新數值顯示文字。
"""

from typing import Optional, List, Dict, Any
import pandas as pd


def build_top_annotations(
    df: pd.DataFrame,
    show_iv_spread: bool = True
) -> List[Dict[str, Any]]:
    """建構圖上方最新數值的 annotation 列表

    Args:
        df: 包含指標資料的 DataFrame
        show_iv_spread: 是否顯示 IV 價差 (若有資料)

    Returns:
        Plotly annotation 字典列表

    顯示內容:
        - C隱含波動率%b: {civ_pb}
        - pb-CIV_pb: {pb_minus_civ_pb}
        - IV價差: {iv_spread} (可選)
    """
    if df.empty:
        return []

    # 取最新一筆資料
    latest = df.iloc[-1]
    annotations = []

    # 基礎 x 位置 (圖表左上角)
    x_positions = [0.01, 0.25, 0.50]
    y_position = 1.02

    # === C隱含波動率%b ===
    civ_pb_value = latest.get('civ_pb')
    civ_pb_text = f"C隱含波動率%b {_format_value(civ_pb_value)}"
    annotations.append(_create_annotation(
        text=civ_pb_text,
        x=x_positions[0],
        y=y_position,
        color='#FFD700'  # 金黃色
    ))

    # === pb-CIV_pb ===
    pb_minus_value = latest.get('pb_minus_civ_pb')
    pb_minus_text = f"pb-CIV_pb {_format_value(pb_minus_value)}"
    # 顏色根據正負值決定
    pb_color = _get_bar_color(pb_minus_value)
    annotations.append(_create_annotation(
        text=pb_minus_text,
        x=x_positions[1],
        y=y_position,
        color=pb_color
    ))

    # === IV價差 (可選) ===
    if show_iv_spread and 'iv_spread' in df.columns:
        iv_spread_value = latest.get('iv_spread')
        if iv_spread_value is not None:
            iv_spread_text = f"IV價差 {_format_value(iv_spread_value)}"
            annotations.append(_create_annotation(
                text=iv_spread_text,
                x=x_positions[2],
                y=y_position,
                color='#AAAAAA'
            ))

    return annotations


def _format_value(value: Optional[float], decimals: int = 2) -> str:
    """格式化數值，缺值顯示 N/A"""
    if value is None or pd.isna(value):
        return 'N/A'
    return f"{value:.{decimals}f}"


def _get_bar_color(value: Optional[float]) -> str:
    """根據數值正負決定顏色"""
    if value is None or pd.isna(value):
        return '#888888'  # 灰色
    if value > 0:
        return '#FF4444'  # 紅色
    if value < 0:
        return '#00FF88'  # 綠色
    return '#888888'  # 零值為灰色


def _create_annotation(
    text: str,
    x: float,
    y: float,
    color: str
) -> Dict[str, Any]:
    """建立 Plotly annotation 字典"""
    return {
        'text': text,
        'xref': 'paper',
        'yref': 'paper',
        'x': x,
        'y': y,
        'showarrow': False,
        'font': {
            'size': 12,
            'color': color
        },
        'xanchor': 'left',
        'yanchor': 'bottom'
    }
