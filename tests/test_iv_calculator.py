"""IV 計算模組測試 - XQ 相容版本

根據 specs/iv-visualization/spec.md 中定義的 scenarios 編寫測試。
"""

import pytest
import math

from src.indicators.iv_calculator import (
    implied_volatility,
    calc_bollinger_band,
    calc_percent_b,
    calc_civ_from_option_quotes,
    calc_indicator_for_bar,
    calc_simple_moving_average,
    build_sma_series,
    IndicatorResult,
    _bs_call_price,
    _bs_call_price_xq,
    _bisection_iv,
)


class TestBSCallPriceXQ:
    """測試 XQ 相容 Black-Scholes 定價函數"""

    def test_standard_pricing(self):
        """Scenario: 標準定價計算
        WHEN S=22000, K=22000, T=0.0274 (10 天), r_pct=2, b_pct=0, sigma_pct=25
        THEN 回傳值 SHALL 為正數且合理的選擇權價格
        """
        price = _bs_call_price_xq(
            S=22000,
            K=22000,
            T=10 / 365,  # 10 天
            r_pct=2,
            b_pct=0,
            sigma_pct=25
        )
        assert price > 0
        # ATM 選擇權價格應該在合理範圍內
        assert 100 < price < 1000

    def test_zero_volatility(self):
        """Scenario: 零或負波動率
        WHEN sigma_pct <= 0 或 T <= 0
        THEN 回傳值 SHALL 為 max(0, S - K) 內在價值
        """
        # 零波動率，ITM
        price = _bs_call_price_xq(22000, 21000, 0.1, 2, 0, 0)
        assert price == max(0, 22000 - 21000)  # 1000

        # 零波動率，OTM
        price = _bs_call_price_xq(22000, 23000, 0.1, 2, 0, 0)
        assert price == max(0, 22000 - 23000)  # 0

        # 零到期時間
        price = _bs_call_price_xq(22000, 21000, 0, 2, 0, 25)
        assert price == max(0, 22000 - 21000)  # 1000


class TestImpliedVolatility:
    """測試 XQ 相容隱含波動率計算"""

    def test_standard_iv_calculation(self):
        """Scenario: 標準 IV 計算
        WHEN option_price=300, underlying_price=22000, strike=22000, dte=10
        THEN 回傳值 SHALL 為百分比值（例如 23.5），不是小數（0.235）
        """
        iv = implied_volatility(
            option_price=300,
            underlying_price=22000,
            strike=22000,
            dte=10
        )
        # 回傳值應為百分比值（大於 1）
        assert iv > 1  # 不是小數
        assert 10 < iv < 100  # 合理範圍 10% ~ 100%

    def test_invalid_input_returns_zero(self):
        """Scenario: 輸入不合法
        WHEN option_price <= 0
        THEN 回傳值 SHALL 為 0
        """
        # 選擇權價格 <= 0
        assert implied_volatility(0, 22000, 22000, 30) == 0
        assert implied_volatility(-100, 22000, 22000, 30) == 0

        # 標的價格 <= 0
        assert implied_volatility(500, 0, 22000, 30) == 0
        assert implied_volatility(500, -100, 22000, 30) == 0

        # 履約價 <= 0
        assert implied_volatility(500, 22000, 0, 30) == 0
        assert implied_volatility(500, 22000, -100, 30) == 0

        # DTE <= 0
        assert implied_volatility(500, 22000, 22000, 0) == 0
        assert implied_volatility(500, 22000, 22000, -10) == 0

    def test_upper_bound_not_found(self):
        """Scenario: 找不到上界
        WHEN 市場價極高，IV 超過 900%
        THEN 回傳值 SHALL 為 999
        """
        # 極高的選擇權價格，理論上需要極高的 IV
        iv = implied_volatility(
            option_price=20000,  # 接近標的價格
            underlying_price=22000,
            strike=22000,
            dte=1  # 只剩 1 天
        )
        assert iv == 999

    def test_convergence_reasonable(self):
        """Scenario: 收斂成功
        WHEN 兩段式逼近法完成迭代
        THEN 回傳值應產生合理接近市場價的理論價

        注意：XQ 兩段式逼近法精度不如 Newton-Raphson，
        這是對齊 XQ 行為的預期結果。
        """
        option_price = 300
        iv = implied_volatility(
            option_price=option_price,
            underlying_price=22000,
            strike=22000,
            dte=10
        )

        # 驗證收斂：用計算出的 IV 反推理論價
        T = 10 / 365
        theoretical = _bs_call_price_xq(22000, 22000, T, 2.0, 0.0, iv)
        # XQ 兩段式逼近法精度較低，誤差在 2 點內是合理的
        assert abs(theoretical - option_price) < 2.0

    def test_atm_call(self):
        """價平買權 IV 計算"""
        iv = implied_volatility(
            option_price=500,
            underlying_price=22000,
            strike=22000,
            dte=30
        )
        assert 10 < iv < 50  # IV 應在 10% ~ 50% 之間

    def test_itm_call(self):
        """價內買權 IV 計算"""
        iv = implied_volatility(
            option_price=1000,
            underlying_price=22000,
            strike=21500,
            dte=30
        )
        assert 5 < iv < 50

    def test_otm_call(self):
        """價外買權 IV 計算"""
        iv = implied_volatility(
            option_price=200,
            underlying_price=22000,
            strike=22500,
            dte=30
        )
        assert 10 < iv < 60


class TestSimpleMovingAverage:
    """測試簡單移動平均計算"""

    def test_sufficient_data(self):
        """Scenario: 資料充足
        WHEN values=[10, 20, 30, 40, 50], period=5
        THEN 回傳值 SHALL 為 30.0
        """
        result = calc_simple_moving_average([10, 20, 30, 40, 50], 5)
        assert result == 30.0

    def test_insufficient_data(self):
        """Scenario: 資料不足
        WHEN values=[10, 20, 30], period=5
        THEN 回傳值 SHALL 為 None
        """
        result = calc_simple_moving_average([10, 20, 30], 5)
        assert result is None

    def test_more_than_period(self):
        """資料多於週期，取最後 N 筆"""
        result = calc_simple_moving_average([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 5)
        # 最後 5 筆: 6, 7, 8, 9, 10 -> 平均 8.0
        assert result == 8.0


class TestBuildSMASeries:
    """測試移動平均序列建構"""

    def test_build_series(self):
        """建構完整 SMA 序列"""
        values = [10, 20, 30, 40, 50]
        result = build_sma_series(values, 3)

        # 前 2 個位置資料不足
        assert result[0] is None
        assert result[1] is None
        # 第 3 個位置: (10+20+30)/3 = 20
        assert result[2] == 20.0
        # 第 4 個位置: (20+30+40)/3 = 30
        assert result[3] == 30.0
        # 第 5 個位置: (30+40+50)/3 = 40
        assert result[4] == 40.0


class TestBollingerBand:
    """測試 Bollinger Band 計算"""

    def test_standard_calculation(self):
        """Scenario: 標準計算
        WHEN values 長度 >= period
        THEN 回傳值 SHALL 為 (middle, upper, lower) 三元組
        """
        values = list(range(100, 120))  # 20 個值
        middle, upper, lower = calc_bollinger_band(values, period=20)

        assert middle is not None
        assert upper is not None
        assert lower is not None
        assert lower < middle < upper

    def test_insufficient_data(self):
        """Scenario: 資料不足
        WHEN values 長度 < period
        THEN 回傳值 SHALL 為 (None, None, None)
        """
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

    def test_uses_population_std(self):
        """使用母體標準差（除以 N）"""
        # 簡單驗證：使用已知數據
        values = [2, 4, 4, 4, 5, 5, 7, 9]  # 8 個值
        middle, upper, lower = calc_bollinger_band(values, period=8, std_dev=1.0)

        # 平均 = 5, 母體標準差 = 2
        assert middle == 5.0
        assert upper == 7.0  # 5 + 1*2
        assert lower == 3.0  # 5 - 1*2


class TestPercentB:
    """測試 XQ 相容 Bollinger %b 計算（0-100 尺度）"""

    def test_standard_percent_b(self):
        """Scenario: 標準 %b 計算
        WHEN value=50, upper=100, lower=0
        THEN 回傳值 SHALL 為 50.0
        """
        pb = calc_percent_b(50, 100, 0)
        assert pb == 50.0

    def test_at_lower(self):
        """Scenario: 在下軌
        WHEN value=0, upper=100, lower=0
        THEN 回傳值 SHALL 為 0.0
        """
        pb = calc_percent_b(0, 100, 0)
        assert pb == 0.0

    def test_at_upper(self):
        """Scenario: 在上軌
        WHEN value=100, upper=100, lower=0
        THEN 回傳值 SHALL 為 100.0
        """
        pb = calc_percent_b(100, 100, 0)
        assert pb == 100.0

    def test_above_upper(self):
        """Scenario: 突破上軌
        WHEN value=120, upper=100, lower=0
        THEN 回傳值 SHALL 為 120.0
        """
        pb = calc_percent_b(120, 100, 0)
        assert pb == 120.0

    def test_below_lower(self):
        """跌破下軌"""
        pb = calc_percent_b(-20, 100, 0)
        assert pb == -20.0

    def test_equal_bands(self):
        """Scenario: 上下軌相等
        WHEN upper == lower
        THEN 回傳值 SHALL 為 0.0
        """
        pb = calc_percent_b(100, 100, 100)
        assert pb == 0.0


class TestCalcCIVFromOptionQuotes:
    """測試 XQ 相容 CIV 計算"""

    def test_calculate_average_civ(self):
        """Scenario: 計算平均 CIV
        過濾掉 0 和 999，只計算有效 IV 的平均
        """
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
        # 回傳值為百分比
        assert 10 < civ < 50

    def test_all_iv_invalid(self):
        """Scenario: 所有 IV 無效
        WHEN 所有選擇權的 IV 都是 0 或 999
        THEN 回傳值 SHALL 為 None
        """
        # 空報價
        civ = calc_civ_from_option_quotes({}, [22000, 22100], 22000, 30)
        assert civ is None

        # 所有價格為零
        option_closes = {
            'TXO22000D6': 0,
            'TXO22100D6': 0,
        }
        civ = calc_civ_from_option_quotes(option_closes, [22000, 22100], 22000, 30)
        assert civ is None

    def test_filters_out_invalid_iv(self):
        """過濾無效 IV（0 和 999）"""
        option_closes = {
            'TXO22000D6': 500,   # 有效
            'TXO22100D6': 0,     # 無效（價格為 0）
            'TXO22200D6': 400,   # 有效
        }
        strikes = [22000, 22100, 22200]

        civ = calc_civ_from_option_quotes(
            option_closes=option_closes,
            strikes=strikes,
            underlying_price=22000,
            dte=30
        )

        # 應該只計算 2 個有效的 IV
        assert civ is not None


class TestIndicatorResult:
    """測試 IndicatorResult 資料模型"""

    def test_create_full_indicator_result(self):
        """Scenario: 建立完整的 IndicatorResult
        WHEN 使用所有欄位建立 IndicatorResult，civ=25.0, civ_ma5=24.5, civ_pb=60.0, price_pb=70.0
        THEN pb_minus_civ_pb SHALL 等於 10.0
        AND signal SHALL 等於 pb_minus_civ_pb
        """
        result = IndicatorResult(
            civ=25.0,
            civ_ma5=24.5,
            civ_pb=60.0,
            price_pb=70.0,
            pb_minus_civ_pb=10.0,
            signal=10.0,
            timestamp="2026-03-26T12:00:00"
        )

        assert result.pb_minus_civ_pb == 10.0
        assert result.signal == result.pb_minus_civ_pb

    def test_civ_ma5_optional(self):
        """civ_ma5 為 Optional，可以是 None"""
        result = IndicatorResult(
            civ=25.0,
            civ_ma5=None,
            civ_pb=60.0,
            price_pb=70.0,
            pb_minus_civ_pb=10.0,
            signal=10.0,
            timestamp="2026-03-26T12:00:00"
        )

        assert result.civ_ma5 is None


class TestCalcIndicatorForBar:
    """測試 XQ 相容指標計算流程"""

    def test_full_calculation(self):
        """Scenario: 完整計算
        WHEN civ_history 長度 >= 24（5MA 需要 5，Bollinger 需要 20）
        THEN 回傳 IndicatorResult 包含 civ_pb、price_pb、pb_minus_civ_pb
        """
        # 需要至少 24 筆歷史（5MA 需要 4 筆歷史 + 當前，Bollinger 需要 20 筆 5MA）
        civ = 25.0
        civ_history = [24.0 + i * 0.1 for i in range(24)]  # 24 筆
        price = 22000
        price_history = [21900 + i * 5 for i in range(24)]  # 24 筆

        result = calc_indicator_for_bar(civ, civ_history, price, price_history)

        assert result is not None
        assert isinstance(result, IndicatorResult)
        assert result.civ == civ
        assert result.civ_ma5 is not None
        assert isinstance(result.civ_pb, float)
        assert isinstance(result.price_pb, float)
        assert result.pb_minus_civ_pb == result.price_pb - result.civ_pb
        assert result.signal == result.pb_minus_civ_pb

    def test_insufficient_for_5ma(self):
        """Scenario: 資料不足無法計算 5MA
        WHEN civ_history 長度 < 4
        THEN 回傳值 SHALL 為 None
        """
        result = calc_indicator_for_bar(
            civ=25.0,
            civ_history=[24.0, 24.5, 25.0],  # 只有 3 筆，加上當前共 4 筆，不足 5
            price=22000,
            price_history=[21900, 21950, 22000],
            period=20
        )

        assert result is None

    def test_insufficient_for_bollinger(self):
        """Scenario: 資料不足無法計算 Bollinger
        WHEN civ_ma_series 長度 < 20
        THEN 回傳值 SHALL 為 None
        """
        # 10 筆歷史 + 1 當前 = 11 筆
        # 5MA 可算的有 11-4=7 筆，不足 20
        result = calc_indicator_for_bar(
            civ=25.0,
            civ_history=[24.0] * 10,
            price=22000,
            price_history=[21900] * 10,
            period=20
        )

        assert result is None

    def test_civ_5ma_then_bollinger_order(self):
        """驗證 CIV -> 5MA -> Bollinger -> %b 順序"""
        civ = 25.0
        civ_history = [25.0] * 24  # 全部相同
        price = 22000
        price_history = [22000] * 24  # 全部相同

        result = calc_indicator_for_bar(civ, civ_history, price, price_history)

        assert result is not None
        # 當所有值相同時，5MA = 原值，Bollinger 上下軌相等
        assert result.civ_ma5 == 25.0
        # 上下軌相等時，%b = 0
        assert result.civ_pb == 0.0
        assert result.price_pb == 0.0

    def test_pb_minus_civ_pb_calculation(self):
        """驗證 pb_minus_civ_pb = price_pb - civ_pb"""
        # 建構資料使 price 在上軌，civ 在下軌
        civ = 20.0
        civ_history = [25.0] * 24  # 歷史較高，當前較低
        price = 22500
        price_history = [22000] * 24  # 歷史較低，當前較高

        result = calc_indicator_for_bar(civ, civ_history, price, price_history)

        assert result is not None
        assert result.pb_minus_civ_pb == result.price_pb - result.civ_pb


class TestDeprecatedFunctions:
    """測試保留的 deprecated 函數"""

    def test_bs_call_price_still_works(self):
        """Scenario: deprecated 函數仍可呼叫
        WHEN 呼叫 _bs_call_price(22000, 22000, 0.0274, 0.02, 0.25)
        THEN 函數 SHALL 正常執行並回傳結果
        """
        price = _bs_call_price(22000, 22000, 0.0274, 0.02, 0.25)
        assert price > 0
        assert isinstance(price, float)

    def test_bisection_iv_still_works(self):
        """_bisection_iv 仍可正常呼叫"""
        iv = _bisection_iv(
            option_price=500,
            underlying_price=22000,
            strike=22000,
            dte=30,
            risk_free_rate=0.02
        )
        # 回傳小數（舊版行為）
        assert iv is not None
        assert 0.1 < iv < 0.5
