"""測試資料驗證函數"""

import pytest
import pandas as pd
from datetime import datetime

from src.visualization.validators import (
    validate_panel_dataframe,
    check_data_availability,
    REQUIRED_COLUMNS,
)


class TestValidatePanelDataframe:
    """validate_panel_dataframe 函數測試"""

    def test_valid_dataframe(self):
        """測試有效的 DataFrame"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, 0)],
            'civ_pb': [45.5],
            'pb_minus_civ_pb': [6.5],
        })

        is_valid, missing = validate_panel_dataframe(df)

        assert is_valid is True
        assert missing == []

    def test_empty_dataframe(self):
        """測試空 DataFrame"""
        df = pd.DataFrame()

        is_valid, missing = validate_panel_dataframe(df)

        assert is_valid is False
        assert 'DataFrame is empty' in missing

    def test_none_dataframe(self):
        """測試 None DataFrame"""
        is_valid, missing = validate_panel_dataframe(None)

        assert is_valid is False
        assert 'DataFrame is empty' in missing

    def test_missing_required_columns(self):
        """測試缺少必要欄位"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, 0)],
        })

        is_valid, missing = validate_panel_dataframe(df)

        # 有 current_dt 就算 valid
        assert is_valid is True
        assert 'civ_pb' in missing
        assert 'pb_minus_civ_pb' in missing

    def test_only_current_dt_is_valid(self):
        """測試只有 current_dt 也算 valid (可繪製空白圖)"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, 0)],
        })

        is_valid, missing = validate_panel_dataframe(df)

        assert is_valid is True

    def test_missing_current_dt_is_invalid(self):
        """測試缺少 current_dt 無效"""
        df = pd.DataFrame({
            'civ_pb': [45.5],
            'pb_minus_civ_pb': [6.5],
        })

        is_valid, missing = validate_panel_dataframe(df)

        assert is_valid is False
        assert 'current_dt' in missing


class TestCheckDataAvailability:
    """check_data_availability 函數測試"""

    def test_full_data_availability(self):
        """測試完整資料可用性"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, i) for i in range(5)],
            'civ_pb': [45.5, 46.0, 47.0, 48.5, 50.0],
            'pb_minus_civ_pb': [6.5, 5.0, 4.0, 3.5, 2.0],
        })

        result = check_data_availability(df)

        assert result['total_rows'] == 5
        assert result['civ_pb_available'] == 5
        assert result['pb_minus_civ_pb_available'] == 5
        assert result['both_available'] == 5
        assert result['neither_available'] == 0

    def test_partial_data_availability(self):
        """測試部分資料缺失"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, i) for i in range(5)],
            'civ_pb': [45.5, None, 47.0, None, 50.0],
            'pb_minus_civ_pb': [6.5, 5.0, None, None, 2.0],
        })

        result = check_data_availability(df)

        assert result['total_rows'] == 5
        assert result['civ_pb_available'] == 3
        assert result['pb_minus_civ_pb_available'] == 3
        assert result['both_available'] == 2  # index 0, 4
        assert result['neither_available'] == 1  # index 3

    def test_empty_dataframe_availability(self):
        """測試空 DataFrame 可用性"""
        df = pd.DataFrame()

        result = check_data_availability(df)

        assert result['total_rows'] == 0
        assert result['civ_pb_available'] == 0
        assert result['pb_minus_civ_pb_available'] == 0
        assert result['both_available'] == 0
        assert result['neither_available'] == 0

    def test_all_missing_data(self):
        """測試全部缺失"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, i) for i in range(3)],
            'civ_pb': [None, None, None],
            'pb_minus_civ_pb': [None, None, None],
        })

        result = check_data_availability(df)

        assert result['total_rows'] == 3
        assert result['civ_pb_available'] == 0
        assert result['pb_minus_civ_pb_available'] == 0
        assert result['both_available'] == 0
        assert result['neither_available'] == 3

    def test_missing_columns(self):
        """測試欄位不存在"""
        df = pd.DataFrame({
            'current_dt': [datetime(2024, 1, 15, 9, 0)],
        })

        result = check_data_availability(df)

        assert result['total_rows'] == 1
        assert result['civ_pb_available'] == 0
        assert result['pb_minus_civ_pb_available'] == 0
