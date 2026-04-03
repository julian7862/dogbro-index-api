"""測試資料模型 (IndicatorResult)"""

import pytest
from datetime import datetime
from src.visualization.models import IndicatorResult


class TestIndicatorResult:
    """IndicatorResult dataclass 測試"""

    def test_create_with_required_fields(self):
        """測試只提供必要欄位"""
        result = IndicatorResult(
            current_dt=datetime(2024, 1, 15, 9, 0),
            underlying_price=17500.0,
            dte=30,
            valid_call_iv_count=16,
        )

        assert result.current_dt == datetime(2024, 1, 15, 9, 0)
        assert result.underlying_price == 17500.0
        assert result.dte == 30
        assert result.valid_call_iv_count == 16

        # 可選欄位應為預設值
        assert result.civ is None
        assert result.civ_ma5 is None
        assert result.civ_pb is None
        assert result.price_pb is None
        assert result.pb_minus_civ_pb is None
        assert result.warnings == []
        assert result.iv_spread is None
        assert result.strike_list is None

    def test_create_with_all_fields(self):
        """測試提供所有欄位"""
        result = IndicatorResult(
            current_dt=datetime(2024, 1, 15, 9, 5),
            underlying_price=17520.0,
            dte=29,
            valid_call_iv_count=14,
            civ=0.185,
            civ_ma5=0.180,
            civ_pb=45.5,
            price_pb=52.0,
            pb_minus_civ_pb=6.5,
            warnings=['LOW_VALID_IV_COUNT'],
            iv_spread=0.02,
            strike_list=[17400, 17500, 17600],
            signal_long_candidate=True,
            signal_short_candidate=False,
            regime_state='trending',
        )

        assert result.civ == 0.185
        assert result.civ_ma5 == 0.180
        assert result.civ_pb == 45.5
        assert result.price_pb == 52.0
        assert result.pb_minus_civ_pb == 6.5
        assert result.warnings == ['LOW_VALID_IV_COUNT']
        assert result.iv_spread == 0.02
        assert result.strike_list == [17400, 17500, 17600]
        assert result.signal_long_candidate is True
        assert result.signal_short_candidate is False
        assert result.regime_state == 'trending'

    def test_warnings_default_empty_list(self):
        """測試 warnings 預設為空列表"""
        result = IndicatorResult(
            current_dt=datetime(2024, 1, 15, 9, 0),
            underlying_price=17500.0,
            dte=30,
            valid_call_iv_count=16,
        )

        assert result.warnings == []
        assert isinstance(result.warnings, list)

    def test_warnings_list_independence(self):
        """測試每個實例的 warnings 列表獨立"""
        result1 = IndicatorResult(
            current_dt=datetime(2024, 1, 15, 9, 0),
            underlying_price=17500.0,
            dte=30,
            valid_call_iv_count=16,
        )
        result2 = IndicatorResult(
            current_dt=datetime(2024, 1, 15, 9, 5),
            underlying_price=17510.0,
            dte=30,
            valid_call_iv_count=15,
        )

        result1.warnings.append('TEST_WARNING')

        assert result1.warnings == ['TEST_WARNING']
        assert result2.warnings == []

    def test_optional_indicator_fields_none(self):
        """測試可選指標欄位可為 None"""
        result = IndicatorResult(
            current_dt=datetime(2024, 1, 15, 9, 0),
            underlying_price=17500.0,
            dte=30,
            valid_call_iv_count=5,
            civ=None,
            civ_pb=None,
            pb_minus_civ_pb=None,
        )

        assert result.civ is None
        assert result.civ_pb is None
        assert result.pb_minus_civ_pb is None

    def test_strategy_reserved_fields(self):
        """測試策略預留欄位"""
        result = IndicatorResult(
            current_dt=datetime(2024, 1, 15, 9, 0),
            underlying_price=17500.0,
            dte=30,
            valid_call_iv_count=16,
            signal_long_candidate=True,
            signal_short_candidate=False,
            regime_state='volatile',
        )

        assert result.signal_long_candidate is True
        assert result.signal_short_candidate is False
        assert result.regime_state == 'volatile'
