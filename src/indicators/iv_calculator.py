"""隱含波動率 (IV) 計算模組

功能:
- Black-Scholes 隱含波動率計算
- Bollinger Band 與 %b 計算
- CIV (Call Implied Volatility) 指標
"""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class IndicatorResult:
    """IV 指標結果"""
    civ: float              # Call Implied Volatility (平均 IV)
    civ_pb: float           # CIV 的 Bollinger %b
    price_pb: float         # 標的價格的 Bollinger %b
    signal: float           # price_pb - civ_pb (主要輸出信號)
    timestamp: str          # 計算時間


def _norm_cdf(x: float) -> float:
    """標準常態分佈累積分佈函數 (不依賴 scipy)

    使用 Abramowitz and Stegun 近似公式
    """
    a1 = 0.254829592
    a2 = -0.284496736
    a3 = 1.421413741
    a4 = -1.453152027
    a5 = 1.061405429
    p = 0.3275911

    sign = 1 if x >= 0 else -1
    x = abs(x)

    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x / 2)

    return 0.5 * (1.0 + sign * y)


def _bs_call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes Call 選擇權定價

    Args:
        S: 標的價格
        K: 履約價
        T: 到期時間 (年)
        r: 無風險利率
        sigma: 波動率

    Returns:
        Call 選擇權理論價格
    """
    if T <= 0 or sigma <= 0:
        return max(0, S - K)

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def implied_volatility(
    option_price: float,
    underlying_price: float,
    strike: float,
    dte: float,
    risk_free_rate: float = 0.01
) -> Optional[float]:
    """使用 Black-Scholes 模型反推 Call 選擇權隱含波動率

    使用 Newton-Raphson 方法迭代求解

    Args:
        option_price: Call 選擇權價格
        underlying_price: 標的價格 (台指期貨價格或現貨指數)
        strike: 履約價
        dte: 距到期天數
        risk_free_rate: 無風險利率 (預設 1%)

    Returns:
        隱含波動率 (0.0 ~ 2.0 範圍)，計算失敗回傳 None
    """
    if option_price <= 0 or underlying_price <= 0 or dte <= 0:
        return None

    T = dte / 365.0
    S = underlying_price
    K = strike
    r = risk_free_rate
    C_market = option_price

    # 內在價值檢查 (Call)
    intrinsic = max(0, S - K)
    if C_market < intrinsic:
        return None

    # Newton-Raphson 迭代
    sigma = 0.3  # 初始猜測
    max_iterations = 100
    tolerance = 1e-6

    for _ in range(max_iterations):
        try:
            # 計算理論價格
            C_theory = _bs_call_price(S, K, T, r, sigma)

            # 計算 Vega (對波動率的偏導數)
            d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
            vega = S * math.sqrt(T) * math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)

            if vega < 1e-10:
                break

            # Newton-Raphson 更新
            diff = C_theory - C_market
            sigma = sigma - diff / vega

            # 限制範圍
            if sigma <= 0.001:
                sigma = 0.001
            elif sigma > 2.0:
                sigma = 2.0

            if abs(diff) < tolerance:
                return sigma

        except (ValueError, ZeroDivisionError):
            break

    # 如果 Newton-Raphson 失敗，使用二分法
    return _bisection_iv(option_price, underlying_price, strike, dte, risk_free_rate)


def _bisection_iv(
    option_price: float,
    underlying_price: float,
    strike: float,
    dte: float,
    risk_free_rate: float
) -> Optional[float]:
    """使用二分法計算隱含波動率"""
    T = dte / 365.0
    S = underlying_price
    K = strike
    r = risk_free_rate
    C_market = option_price

    low = 0.001
    high = 2.0
    tolerance = 1e-6
    max_iterations = 100

    for _ in range(max_iterations):
        mid = (low + high) / 2
        C_theory = _bs_call_price(S, K, T, r, mid)

        if abs(C_theory - C_market) < tolerance:
            return mid

        if C_theory > C_market:
            high = mid
        else:
            low = mid

    return None


def calc_bollinger_band(
    values: List[float],
    period: int = 20,
    std_dev: float = 2.0
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """計算 Bollinger Band

    Args:
        values: 歷史數值列表
        period: 計算週期 (預設 20)
        std_dev: 標準差倍數 (預設 2)

    Returns:
        (middle, upper, lower) 或 (None, None, None) 若資料不足
    """
    if len(values) < period:
        return None, None, None

    recent = values[-period:]
    middle = sum(recent) / period
    variance = sum((x - middle) ** 2 for x in recent) / period
    std = math.sqrt(variance)

    upper = middle + std_dev * std
    lower = middle - std_dev * std

    return middle, upper, lower


def calc_percent_b(value: float, upper: float, lower: float) -> float:
    """計算 Bollinger %b

    %b = (價格 - 下軌) / (上軌 - 下軌)
    - %b > 1: 價格在上軌之上
    - %b < 0: 價格在下軌之下
    - %b = 0.5: 價格在中軌

    Args:
        value: 當前值
        upper: 上軌
        lower: 下軌

    Returns:
        %b 值
    """
    if upper == lower:
        return 0.5
    return (value - lower) / (upper - lower)


def calc_civ_from_option_quotes(
    option_closes: Dict[str, float],
    strikes: List[int],
    underlying_price: float,
    dte: float
) -> Optional[float]:
    """從選擇權報價計算平均 CIV

    Args:
        option_closes: 各合約的選擇權收盤價 {contract_code: close}
        strikes: 履約價列表
        underlying_price: 標的價格
        dte: 距到期天數

    Returns:
        平均 IV (排除計算失敗的履約價)
    """
    ivs = []

    for strike in strikes:
        # 找到對應的合約
        close = None
        for code, price in option_closes.items():
            if str(strike) in code:
                close = price
                break

        if close and close > 0:
            iv = implied_volatility(close, underlying_price, strike, dte)
            if iv is not None and 0.01 < iv < 1.5:  # 合理範圍: 1% ~ 150%
                ivs.append(iv)

    if not ivs:
        return None

    return sum(ivs) / len(ivs)


def calc_indicator_for_bar(
    civ: float,
    civ_history: List[float],
    price: float,
    price_history: List[float],
    period: int = 20
) -> Optional[IndicatorResult]:
    """計算完整的 IV 指標

    Args:
        civ: 當前 CIV 值
        civ_history: CIV 歷史值列表
        price: 當前標的價格
        price_history: 價格歷史列表
        period: Bollinger Band 週期

    Returns:
        IndicatorResult 或 None (若資料不足)
    """
    # 計算 CIV 的 Bollinger Band
    civ_mid, civ_upper, civ_lower = calc_bollinger_band(civ_history + [civ], period)
    if civ_mid is None:
        return None

    # 計算價格的 Bollinger Band
    price_mid, price_upper, price_lower = calc_bollinger_band(price_history + [price], period)
    if price_mid is None:
        return None

    # 計算 %b
    civ_pb = calc_percent_b(civ, civ_upper, civ_lower)
    price_pb = calc_percent_b(price, price_upper, price_lower)

    return IndicatorResult(
        civ=civ,
        civ_pb=civ_pb,
        price_pb=price_pb,
        signal=price_pb - civ_pb,
        timestamp=datetime.now().isoformat()
    )
