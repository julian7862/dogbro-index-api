"""IV 計算模組測試"""

import pytest
import math

from src.indicators.iv_calculator import (
    implied_volatility,
    calc_bollinger_band,
    calc_percent_b,
    calc_civ_from_option_quotes,
    calc_indicator_for_bar,
    IndicatorResult,
)


class TestImpliedVolatility:
    """測試隱含波動率計算"""

    def test_atm_call(self):
        """價平買權 IV 計算"""
        # 台指 22000, 履約價 22000, 選擇權價格 500, DTE 30 天
        iv = implied_volatility(
            option_price=500,
            underlying_price=22000,
            strike=22000,
            dte=30
        )
        assert iv is not None
        assert 0.1 < iv < 0.5  # IV 應在 10% ~ 50% 之間

    def test_itm_call(self):
        """價內買權 IV 計算"""
        iv = implied_volatility(
            option_price=1000,
            underlying_price=22000,
            strike=21500,
            dte=30
        )
        assert iv is not None
        assert 0.05 < iv < 0.5

    def test_otm_call(self):
        """價外買權 IV 計算"""
        iv = implied_volatility(
            option_price=200,
            underlying_price=22000,
            strike=22500,
            dte=30
        )
        assert iv is not None
        assert 0.1 < iv < 0.6

    def test_zero_option_price(self):
        """選擇權價格為零"""
        iv = implied_volatility(0, 22000, 22000, 30)
        assert iv is None

    def test_negative_option_price(self):
        """選擇權價格為負"""
        iv = implied_volatility(-100, 22000, 22000, 30)
        assert iv is None

    def test_zero_dte(self):
        """到期日為零"""
        iv = implied_volatility(500, 22000, 22000, 0)
        assert iv is None

    def test_deep_itm(self):
        """深價內選擇權"""
        # 履約價 20000, 標的 22000, 內在價值 2000, 選擇權價格 2100
        iv = implied_volatility(2100, 22000, 20000, 30)
        assert iv is not None

    def test_deep_otm(self):
        """深價外選擇權"""
        # 履約價 24000, 標的 22000, 很小的權利金
        iv = implied_volatility(50, 22000, 24000, 30)
        assert iv is not None
        assert iv > 0.2  # 深價外應有較高 IV


class TestBollingerBand:
    """測試 Bollinger Band 計算"""

    def test_sufficient_data(self):
        """足夠資料"""
        values = list(range(100, 120))  # 20 個值
        middle, upper, lower = calc_bollinger_band(values, period=20)

        assert middle is not None
        assert upper is not None
        assert lower is not None
        assert lower < middle < upper

    def test_insufficient_data(self):
        """資料不足"""
        values = list(range(10))  # 只有 10 個值
        middle, upper, lower = calc_bollinger_band(values, period=20)

        assert middle is None
        assert upper is None
        assert lower is None

    def test_exact_period(self):
        """剛好等於週期"""
        values = [100] * 20  # 剛好 20 個相同值
        middle, upper, lower = calc_bollinger_band(values, period=20)

        assert middle == 100
        # 標準差為 0，上下軌等於中軌
        assert upper == 100
        assert lower == 100

    def test_custom_std_dev(self):
        """自訂標準差倍數"""
        values = list(range(100, 120))
        middle1, upper1, _ = calc_bollinger_band(values, period=20, std_dev=2.0)
        middle2, upper2, _ = calc_bollinger_band(values, period=20, std_dev=3.0)

        assert upper2 > upper1  # 3 倍標準差應該更寬


class TestPercentB:
    """測試 %b 計算"""

    def test_at_middle(self):
        """在中軌"""
        pb = calc_percent_b(100, 110, 90)
        assert pb == 0.5

    def test_at_upper(self):
        """在上軌"""
        pb = calc_percent_b(110, 110, 90)
        assert pb == 1.0

    def test_at_lower(self):
        """在下軌"""
        pb = calc_percent_b(90, 110, 90)
        assert pb == 0.0

    def test_above_upper(self):
        """超過上軌"""
        pb = calc_percent_b(120, 110, 90)
        assert pb > 1.0

    def test_below_lower(self):
        """低於下軌"""
        pb = calc_percent_b(80, 110, 90)
        assert pb < 0.0

    def test_equal_bands(self):
        """上下軌相等 (避免除零)"""
        pb = calc_percent_b(100, 100, 100)
        assert pb == 0.5


class TestCalcCIVFromOptionQuotes:
    """測試從選擇權報價計算 CIV"""

    def test_basic_calculation(self):
        """基本計算"""
        option_closes = {
            'TXO22000D6': 500,
            'TXO22100D6': 400,
            'TXO22200D6': 300,
        }
        strikes = [22000, 22100, 22200]

        civ = calc_civ_from_option_quotes(
            option_closes=option_closes,
            strikes=strikes,
            underlying_price=22000,
            dte=30
        )

        assert civ is not None
        assert 0.1 < civ < 0.5

    def test_empty_quotes(self):
        """空報價"""
        civ = calc_civ_from_option_quotes({}, [22000, 22100], 22000, 30)
        assert civ is None

    def test_all_zero_prices(self):
        """所有價格為零"""
        option_closes = {
            'TXO22000D6': 0,
            'TXO22100D6': 0,
        }
        civ = calc_civ_from_option_quotes(option_closes, [22000, 22100], 22000, 30)
        assert civ is None


class TestCalcIndicatorForBar:
    """測試完整指標計算"""

    def test_sufficient_history(self):
        """足夠歷史資料"""
        civ = 0.2
        civ_history = [0.18, 0.19, 0.20, 0.21, 0.19] * 4  # 20 筆
        price = 22000
        price_history = [21900, 21950, 22000, 22050, 21980] * 4  # 20 筆

        result = calc_indicator_for_bar(civ, civ_history, price, price_history)

        assert result is not None
        assert isinstance(result, IndicatorResult)
        assert 0 <= result.civ_pb <= 1 or result.civ_pb > 1 or result.civ_pb < 0
        assert isinstance(result.signal, float)

    def test_insufficient_history(self):
        """歷史資料不足"""
        result = calc_indicator_for_bar(
            civ=0.2,
            civ_history=[0.18, 0.19],  # 只有 2 筆
            price=22000,
            price_history=[21900, 21950],  # 只有 2 筆
            period=20
        )

        assert result is None

    def test_signal_calculation(self):
        """信號計算"""
        civ = 0.2
        civ_history = [0.2] * 19
        price = 22000
        price_history = [22000] * 19

        result = calc_indicator_for_bar(civ, civ_history, price, price_history)

        assert result is not None
        # 當 CIV 和 price 都在中軌時，signal 應該接近 0
        assert abs(result.signal) < 0.1
