"""測試繪圖函數"""

import pytest
import pandas as pd
from datetime import datetime

from src.visualization.models import IndicatorResult
from src.visualization.plotly_chart import (
    rows_to_dataframe,
    plot_indicator_panel,
    render_panel_from_rows,
    COLORS,
    Y_AXIS_RANGE,
)
from src.visualization.annotations import (
    build_top_annotations,
    _format_value,
    _get_bar_color,
)


class TestRowsToDataframe:
    """rows_to_dataframe 函數測試"""

    def test_empty_rows(self):
        """測試空列表"""
        df = rows_to_dataframe([])

        assert df.empty

    def test_single_row(self):
        """測試單筆資料"""
        rows = [
            IndicatorResult(
                current_dt=datetime(2024, 1, 15, 9, 0),
                underlying_price=17500.0,
                dte=30,
                valid_call_iv_count=16,
                civ_pb=45.5,
                pb_minus_civ_pb=6.5,
            )
        ]

        df = rows_to_dataframe(rows)

        assert len(df) == 1
        assert df.iloc[0]['current_dt'] == datetime(2024, 1, 15, 9, 0)
        assert df.iloc[0]['underlying_price'] == 17500.0
        assert df.iloc[0]['civ_pb'] == 45.5
        assert df.iloc[0]['pb_minus_civ_pb'] == 6.5

    def test_multiple_rows_sorted(self):
        """測試多筆資料排序"""
        rows = [
            IndicatorResult(
                current_dt=datetime(2024, 1, 15, 9, 10),
                underlying_price=17510.0,
                dte=30,
                valid_call_iv_count=16,
            ),
            IndicatorResult(
                current_dt=datetime(2024, 1, 15, 9, 0),
                underlying_price=17500.0,
                dte=30,
                valid_call_iv_count=16,
            ),
            IndicatorResult(
                current_dt=datetime(2024, 1, 15, 9, 5),
                underlying_price=17505.0,
                dte=30,
                valid_call_iv_count=16,
            ),
        ]

        df = rows_to_dataframe(rows)

        assert len(df) == 3
        # 確認按時間排序
        assert df.iloc[0]['current_dt'] == datetime(2024, 1, 15, 9, 0)
        assert df.iloc[1]['current_dt'] == datetime(2024, 1, 15, 9, 5)
        assert df.iloc[2]['current_dt'] == datetime(2024, 1, 15, 9, 10)

    def test_all_columns_present(self):
        """測試所有欄位都存在"""
        rows = [
            IndicatorResult(
                current_dt=datetime(2024, 1, 15, 9, 0),
                underlying_price=17500.0,
                dte=30,
                valid_call_iv_count=16,
            )
        ]

        df = rows_to_dataframe(rows)

        expected_columns = [
            'current_dt', 'underlying_price', 'dte', 'valid_call_iv_count',
            'civ', 'civ_ma5', 'civ_pb', 'price_pb', 'pb_minus_civ_pb',
            'warnings', 'iv_spread', 'strike_list',
            'signal_long_candidate', 'signal_short_candidate', 'regime_state',
        ]

        for col in expected_columns:
            assert col in df.columns


class TestPlotIndicatorPanel:
    """plot_indicator_panel 函數測試"""

    def test_empty_dataframe(self):
        """測試空 DataFrame 生成空白圖"""
        df = pd.DataFrame()

        fig = plot_indicator_panel(df)

        assert fig is not None
        # 確認有「無資料」annotation
        assert any('無資料' in str(ann.text) for ann in fig.layout.annotations)

    def test_valid_data_creates_traces(self):
        """測試有效資料產生 traces"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, i * 5) for i in range(5)],
            'civ_pb': [45.5, 46.0, 47.0, 48.5, 50.0],
            'pb_minus_civ_pb': [6.5, 5.0, -4.0, 3.5, -2.0],
        })

        fig = plot_indicator_panel(df)

        assert fig is not None
        assert len(fig.data) == 2  # bar + line

    def test_y_axis_range_fixed(self):
        """測試 Y 軸固定 0-100"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, 0)],
            'civ_pb': [45.5],
            'pb_minus_civ_pb': [6.5],
        })

        fig = plot_indicator_panel(df)

        assert list(fig.layout.yaxis.range) == [0, 100]

    def test_dark_background(self):
        """測試深色背景"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, 0)],
            'civ_pb': [45.5],
            'pb_minus_civ_pb': [6.5],
        })

        fig = plot_indicator_panel(df)

        assert fig.layout.paper_bgcolor == COLORS['background']
        assert fig.layout.plot_bgcolor == COLORS['background']

    def test_custom_title(self):
        """測試自訂標題"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, 0)],
            'civ_pb': [45.5],
            'pb_minus_civ_pb': [6.5],
        })

        fig = plot_indicator_panel(df, title="Custom Title")

        assert fig.layout.title.text == "Custom Title"

    def test_custom_height(self):
        """測試自訂高度"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, 0)],
            'civ_pb': [45.5],
            'pb_minus_civ_pb': [6.5],
        })

        fig = plot_indicator_panel(df, height=600)

        assert fig.layout.height == 600


class TestRenderPanelFromRows:
    """render_panel_from_rows 函數測試"""

    def test_empty_rows(self):
        """測試空列表"""
        fig = render_panel_from_rows([])

        assert fig is not None

    def test_full_workflow(self):
        """測試完整流程"""
        rows = [
            IndicatorResult(
                current_dt=datetime(2024, 1, 15, 9, i * 5),
                underlying_price=17500.0 + i * 10,
                dte=30,
                valid_call_iv_count=16,
                civ=0.18,
                civ_pb=45.5 + i,
                price_pb=52.0 + i,
                pb_minus_civ_pb=6.5 - i,
            )
            for i in range(10)
        ]

        fig = render_panel_from_rows(rows)

        assert fig is not None
        assert len(fig.data) == 2  # bar + line


class TestAnnotations:
    """annotation 函數測試"""

    def test_format_value_normal(self):
        """測試正常值格式化"""
        assert _format_value(45.5) == "45.50"
        assert _format_value(0.0) == "0.00"
        assert _format_value(-10.5) == "-10.50"

    def test_format_value_none(self):
        """測試 None 值格式化"""
        assert _format_value(None) == "N/A"

    def test_format_value_nan(self):
        """測試 NaN 值格式化"""
        import math
        assert _format_value(float('nan')) == "N/A"

    def test_get_bar_color_positive(self):
        """測試正值顏色"""
        assert _get_bar_color(10.0) == '#FF4444'  # 紅色

    def test_get_bar_color_negative(self):
        """測試負值顏色"""
        assert _get_bar_color(-10.0) == '#00FF88'  # 綠色

    def test_get_bar_color_zero(self):
        """測試零值顏色"""
        assert _get_bar_color(0.0) == '#888888'  # 灰色

    def test_get_bar_color_none(self):
        """測試 None 顏色"""
        assert _get_bar_color(None) == '#888888'  # 灰色

    def test_build_top_annotations_empty(self):
        """測試空 DataFrame"""
        df = pd.DataFrame()

        annotations = build_top_annotations(df)

        assert annotations == []

    def test_build_top_annotations_with_data(self):
        """測試有資料時產生 annotations"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, 0)],
            'civ_pb': [45.5],
            'pb_minus_civ_pb': [6.5],
        })

        annotations = build_top_annotations(df)

        assert len(annotations) >= 2
        # 確認包含 civ_pb 和 pb_minus_civ_pb 文字
        texts = [ann['text'] for ann in annotations]
        assert any('C隱含波動率%b' in t for t in texts)
        assert any('pb-CIV_pb' in t for t in texts)


class TestMissingDataHandling:
    """缺值處理測試"""

    def test_civ_pb_all_missing(self):
        """測試 civ_pb 全部缺失"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, i * 5) for i in range(5)],
            'civ_pb': [None, None, None, None, None],
            'pb_minus_civ_pb': [6.5, 5.0, -4.0, 3.5, -2.0],
        })

        fig = plot_indicator_panel(df)

        assert fig is not None
        # 應該至少有 bar trace
        assert len(fig.data) >= 1

    def test_pb_minus_all_missing(self):
        """測試 pb_minus_civ_pb 全部缺失"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, i * 5) for i in range(5)],
            'civ_pb': [45.5, 46.0, 47.0, 48.5, 50.0],
            'pb_minus_civ_pb': [None, None, None, None, None],
        })

        fig = plot_indicator_panel(df)

        assert fig is not None
        # 應該至少有 line trace
        assert len(fig.data) >= 1

    def test_both_all_missing(self):
        """測試兩者全部缺失"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, i * 5) for i in range(5)],
            'civ_pb': [None, None, None, None, None],
            'pb_minus_civ_pb': [None, None, None, None, None],
        })

        fig = plot_indicator_panel(df)

        assert fig is not None

    def test_partial_missing(self):
        """測試部分缺失"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, i * 5) for i in range(5)],
            'civ_pb': [45.5, None, 47.0, None, 50.0],
            'pb_minus_civ_pb': [6.5, 5.0, None, None, -2.0],
        })

        fig = plot_indicator_panel(df)

        assert fig is not None
        assert len(fig.data) == 2  # bar + line
