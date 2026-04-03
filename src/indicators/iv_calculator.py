"""隱含波動率 (IV) 計算模組 - XQ/XS 相容版本

功能:
- Black-Scholes 隱含波動率計算（XQ 相容）
- Bollinger Band 與 %b 計算（0-100 尺度）
- CIV (Call Implied Volatility) 指標
- CIV -> 5MA -> Bollinger -> %b 處理流程

XQ 相容說明:
- 所有百分比參數使用百分比值（例如 2 代表 2%），而非小數（0.02）
- IV 計算使用 XQ 兩段式逼近法，而非 Newton-Raphson
- %b 輸出為 0-100 尺度
"""

import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class IndicatorResult:
    """IV 指標結果

    欄位單位說明:
    - civ: CIV 值，單位為百分比（例如 25.0 代表 25%）
    - civ_ma5: CIV 5 期移動平均，單位為百分比
    - civ_pb: CIV 5MA 的 Bollinger %b，尺度為 0-100
    - price_pb: 價格的 Bollinger %b，尺度為 0-100
    - pb_minus_civ_pb: price_pb - civ_pb，主要輸出信號
    - signal: 等同於 pb_minus_civ_pb（向後相容別名）
    """
    civ: float                      # CIV 值（百分比，例如 25.0 代表 25%）
    civ_ma5: Optional[float]        # CIV 5 期移動平均（百分比）
    civ_pb: float                   # CIV 5MA 的 Bollinger %b（0-100 尺度）
    price_pb: float                 # 價格的 Bollinger %b（0-100 尺度）
    pb_minus_civ_pb: float          # price_pb - civ_pb（主要輸出信號）
    signal: float                   # 等同於 pb_minus_civ_pb（向後相容）
    timestamp: str                  # 計算時間 ISO 格式


def _norm_cdf(z: float) -> float:
    """標準常態分佈累積分佈函數（XQ NormSDist 相容版本）

    此函數完全對齊 XQ NormSDist 的多項式近似公式，
    不使用 scipy，以確保與 XQ 計算結果一致。

    變數命名對齊 XQ 原始碼：
    - value1 = 1 / (1 + gamma * |z|)
    - value2 = exp(-z²/2) / sqrt(2π)
    - value3 = 1 - value2 * poly(value1)

    Args:
        z: 標準常態分佈的 z 值

    Returns:
        累積機率值 P(Z <= z)
    """
    # XQ NormSDist 多項式係數
    a1 = 0.31938153
    a2 = -0.356563782
    a3 = 1.781477937
    a4 = -1.821255978
    a5 = 1.330274429
    sqrtof2pi = 2.506628275
    gamma = 0.2316419

    # 對 abs(z) 做近似
    abs_z = abs(z)

    # value1: 對齊 XQ 的 1 / (1 + gamma * AbsValue(zvalue))
    value1 = 1.0 / (1.0 + gamma * abs_z)

    # value2: 對齊 XQ 的 ExpValue(-Square(zvalue) * 0.5) / sqrtof2pi
    value2 = math.exp(-0.5 * abs_z * abs_z) / sqrtof2pi

    # value3: 對齊 XQ 的 Horner 展開式
    # XQ: 1 - value2 * (((((a5*value1+a4)*value1+a3)*value1+a2)*value1+a1)*value1)
    value3 = 1.0 - value2 * (((((a5 * value1 + a4) * value1 + a3) * value1 + a2) * value1 + a1) * value1)

    # 若 z < 0，利用對稱性回傳 1 - value3
    if z < 0:
        return 1.0 - value3
    else:
        return value3


def _bs_call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes Call 選擇權定價（原始小數參數版本）

    .. deprecated::
        此函數使用小數參數（例如 r=0.02 代表 2%），
        建議改用 `_bs_call_price_xq()` 以對齊 XQ 行為。

    Args:
        S: 標的價格
        K: 履約價
        T: 到期時間（年）
        r: 無風險利率（小數，例如 0.02 代表 2%）
        sigma: 波動率（小數，例如 0.25 代表 25%）

    Returns:
        Call 選擇權理論價格
    """
    if T <= 0 or sigma <= 0:
        return max(0, S - K)

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def _bs_call_price_xq(
    S: float,
    K: float,
    T: float,
    r_pct: float,
    b_pct: float,
    sigma_pct: float
) -> float:
    """Black-Scholes Call 選擇權定價（XQ 相容版本，百分比參數）

    使用 Black-Scholes with cost of carry 版本，支援 carry cost 參數。
    期貨選擇權的情境下，通常 b=0。

    公式：
    d1 = (ln(S/K) + (b + 0.5*σ²)*T) / (σ*√T)
    d2 = d1 - σ*√T
    C = S*e^((b-r)*T)*N(d1) - K*e^(-r*T)*N(d2)

    Args:
        S: 標的價格
        K: 履約價
        T: 到期時間（年）
        r_pct: 無風險利率，百分比值（例如 2 代表 2%）
        b_pct: 持有成本率，百分比值（期貨選擇權通常為 0）
        sigma_pct: 波動率，百分比值（例如 25 代表 25%）

    Returns:
        Call 選擇權理論價格
    """
    # 將百分比轉為小數
    r = r_pct / 100.0
    b = b_pct / 100.0
    sigma = sigma_pct / 100.0

    if T <= 0 or sigma <= 0:
        return max(0, S - K)

    d1 = (math.log(S / K) + (b + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    # Black-Scholes with cost of carry
    call_price = S * math.exp((b - r) * T) * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return call_price


def implied_volatility(
    option_price: float,
    underlying_price: float,
    strike: float,
    dte: float,
    risk_free_rate: float = 2.0,
    carry_rate: float = 0.0
) -> float:
    """使用 XQ 兩段式逼近法計算 Call 選擇權隱含波動率

    此函數對齊 XQ `IVolatility` 的行為：
    - 參數使用百分比值（例如 risk_free_rate=2 代表 2%）
    - 回傳值為百分比值（例如 25.0 代表 25%）
    - 使用兩段式逼近法而非 Newton-Raphson

    XQ 兩段式逼近法：
    1. 第一段：從 iv_guess=100 開始，步長 100 找上界，最大 900
    2. 第二段：步長折半逼近，最多 10 次迭代，收斂條件 < 0.005

    Args:
        option_price: Call 選擇權市場價格
        underlying_price: 標的價格（台指期貨價格或現貨指數）
        strike: 履約價
        dte: 距到期天數
        risk_free_rate: 無風險利率，百分比值（預設 2.0 代表 2%）
        carry_rate: 持有成本率，百分比值（預設 0.0，期貨選擇權）

    Returns:
        隱含波動率，百分比值（例如 25.0 代表 25%）
        - 回傳 0：輸入不合法
        - 回傳 999：找不到上界（IV 極高）
    """
    # 輸入檢查：不合法回傳 0
    if option_price <= 0 or underlying_price <= 0 or strike <= 0 or dte <= 0:
        return 0

    T = dte / 365.0
    S = underlying_price
    K = strike
    C_market = option_price

    # 第一段：找上界，從 100 開始，步長 100，最大 900
    iv_guess = 100.0
    while iv_guess <= 900.0:
        C_theory = _bs_call_price_xq(S, K, T, risk_free_rate, carry_rate, iv_guess)
        if C_theory >= C_market:
            break
        iv_guess += 100.0

    # 若找不到上界（理論價始終小於市場價），回傳 999
    if iv_guess > 900.0:
        return 999

    # 第二段：步長折半逼近
    step = 100.0
    max_iterations = 10
    tolerance = 0.005

    for _ in range(max_iterations):
        C_theory = _bs_call_price_xq(S, K, T, risk_free_rate, carry_rate, iv_guess)

        # 收斂檢查
        if abs(C_theory - C_market) < tolerance:
            return iv_guess

        step *= 0.5

        if C_theory > C_market:
            iv_guess -= step
        else:
            iv_guess += step

    # 迭代完成後回傳當前值
    return iv_guess


def _bisection_iv(
    option_price: float,
    underlying_price: float,
    strike: float,
    dte: float,
    risk_free_rate: float
) -> Optional[float]:
    """使用二分法計算隱含波動率（原始版本）

    .. deprecated::
        此函數已不再作為主要 IV 計算方法。
        建議使用 `implied_volatility()` 函數，
        其已改用 XQ 相容的兩段式逼近法。

    Args:
        option_price: 選擇權價格
        underlying_price: 標的價格
        strike: 履約價
        dte: 距到期天數
        risk_free_rate: 無風險利率（小數）

    Returns:
        隱含波動率（小數），計算失敗回傳 None
    """
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


def calc_simple_moving_average(values: List[float], period: int) -> Optional[float]:
    """計算簡單移動平均（SMA）

    與 XQ 的 Average(value, period) 概念一致。

    Args:
        values: 數值列表
        period: 移動平均週期

    Returns:
        最新一期的移動平均值，若資料不足則回傳 None
    """
    if len(values) < period:
        return None

    recent = values[-period:]
    return sum(recent) / period


def build_sma_series(values: List[float], period: int) -> List[Optional[float]]:
    """建構移動平均序列

    對輸入序列的每個位置計算 SMA，資料不足的位置為 None。

    Args:
        values: 數值列表
        period: 移動平均週期

    Returns:
        移動平均序列，長度與輸入相同
    """
    result = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(None)
        else:
            window = values[i - period + 1:i + 1]
            result.append(sum(window) / period)
    return result


def calc_variance_ps(values: List[float], period: int, data_type: int = 1) -> Optional[float]:
    """計算變異數（對齊 XQ VariancePS）

    對齊 XQ VariancePS(thePrice, Length, DataType) 的行為。

    XQ 原始邏輯：
    - Period = Iff(DataType = 1, Length, Length - 1)
    - avg = Average(thePrice, Length)
    - sum = Σ(thePrice[i] - avg)²
    - VariancePS = sum / Period

    Args:
        values: 數值列表
        period: 計算週期（對應 XQ 的 Length）
        data_type: 分母類型
            - data_type=1: 分母 = period（母體變異數）
            - data_type!=1: 分母 = period - 1（樣本變異數）

    Returns:
        變異數，若資料不足或分母為零則回傳 None
    """
    if period <= 0:
        return None

    if len(values) < period:
        return None

    # 取最近 period 筆資料
    recent = values[-period:]

    # 計算平均（對齊 XQ Average）
    avg = sum(recent) / period

    # 計算平方差總和
    sum_sq = sum((x - avg) ** 2 for x in recent)

    # 分母規則對齊 XQ: Iff(DataType = 1, Length, Length - 1)
    period_divisor = period if data_type == 1 else period - 1

    if period_divisor <= 0:
        return None

    return sum_sq / period_divisor


def calc_standard_dev(values: List[float], period: int, data_type: int = 1) -> Optional[float]:
    """計算標準差（對齊 XQ StandardDev）

    對齊 XQ StandardDev(thePrice, Length, DataType) 的行為。

    XQ 原始邏輯：
    - Value1 = VariancePS(thePrice, Length, DataType)
    - if Value1 > 0 then StandardDev = SquareRoot(Value1) else StandardDev = 0

    BollingerBand 使用 data_type=1（母體標準差）。

    Args:
        values: 數值列表
        period: 計算週期
        data_type: 變異數分母類型（傳遞給 calc_variance_ps）

    Returns:
        標準差，若變異數為 None 則回傳 None，若變異數 <= 0 則回傳 0.0
    """
    variance = calc_variance_ps(values, period, data_type)

    if variance is None:
        return None

    if variance <= 0:
        return 0.0

    return math.sqrt(variance)


def calc_bollinger_band(
    values: List[float],
    period: int = 20,
    band: float = 2.0
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """計算 Bollinger Band（對齊 XQ BollingerBand）

    對齊 XQ BollingerBand(price, length, _band) 的行為：
    - 中軌 = Average(price, length)
    - 標準差 = StandardDev(price, length, 1)  # data_type=1 為母體標準差
    - 上軌 = 中軌 + _band * 標準差
    - 下軌 = 中軌 - _band * 標準差

    Args:
        values: 歷史數值列表
        period: 計算週期（預設 20，對應 XQ 的 length）
        band: 標準差倍數（預設 2，對應 XQ 的 _band）

    Returns:
        (middle, upper, lower) 或 (None, None, None) 若資料不足
    """
    # 使用 calc_simple_moving_average 計算中軌（對齊 XQ Average）
    middle = calc_simple_moving_average(values, period)
    if middle is None:
        return None, None, None

    # 使用 calc_standard_dev 計算標準差（對齊 XQ StandardDev，data_type=1）
    std = calc_standard_dev(values, period, data_type=1)
    if std is None:
        return None, None, None

    upper = middle + band * std
    lower = middle - band * std

    return middle, upper, lower


def calc_percent_b(value: float, upper: float, lower: float) -> float:
    """計算 Bollinger %b（XQ 相容，0-100 尺度）

    公式：%b = (value - lower) / (upper - lower) * 100

    尺度說明：
    - %b = 0：落在下軌
    - %b = 50：大致在中間
    - %b = 100：落在上軌
    - %b > 100：突破上軌
    - %b < 0：跌破下軌

    Args:
        value: 當前值
        upper: 上軌
        lower: 下軌

    Returns:
        %b 值（0-100 尺度）
    """
    if upper == lower:
        return 0.0
    return (value - lower) / (upper - lower) * 100.0


def extract_strike_from_code(code: str) -> Optional[int]:
    """從選擇權合約代碼中提取履約價

    支援 TXO 格式: TXO{strike}{month_code}{year}
    例如: TXO33000D6 -> 33000

    不再使用 substring matching，改用 regex 明確提取。

    Args:
        code: 合約代碼字串

    Returns:
        履約價整數，若無法解析則回傳 None
    """
    # TXO 格式: TXO 後接連續數字為履約價，接著是月份代碼和年份
    # 例如: TXO33000D6, TXO22500C6
    match = re.match(r'^TXO(\d+)[A-Z]\d+$', code.upper())
    if match:
        return int(match.group(1))

    # 備用: 嘗試提取 TXO 後的連續數字
    match = re.search(r'TXO(\d+)', code.upper())
    if match:
        return int(match.group(1))

    return None


def build_strike_price_map(option_closes: Dict[str, float]) -> Dict[int, float]:
    """建立履約價到選擇權價格的對應表

    使用 extract_strike_from_code() 從合約代碼提取履約價，
    建立結構化的 {strike: price} mapping。

    不再使用 substring matching (str(strike) in code)。

    Args:
        option_closes: 各合約的選擇權收盤價 {contract_code: close}

    Returns:
        {strike: price} 對應表

    Note:
        若同一 strike 對應多個 code，取第一個有效值（price > 0）
    """
    strike_price_map: Dict[int, float] = {}

    for code, price in option_closes.items():
        strike = extract_strike_from_code(code)
        if strike is None:
            continue

        # 若此 strike 尚未有對應值，或目前值無效但新值有效，則更新
        if strike not in strike_price_map:
            if price and price > 0:
                strike_price_map[strike] = price
        # 若已有值但為 0，而新值有效，則覆蓋
        elif strike_price_map[strike] <= 0 and price and price > 0:
            strike_price_map[strike] = price

    return strike_price_map


def calc_civ_from_option_quotes(
    option_closes: Dict[str, float],
    strikes: List[int],
    underlying_price: float,
    dte: float,
    risk_free_rate: float = 2.0,
    carry_rate: float = 0.0
) -> Optional[float]:
    """從選擇權報價計算平均 CIV（XQ 相容版本）

    回傳值為百分比值（例如 23.5 代表 23.5%）。

    履約價對應方式：
    - 使用 build_strike_price_map() 建立結構化 mapping
    - 不再使用 substring matching (str(strike) in code)

    過濾規則：
    - 排除 IV = 0（輸入無效）
    - 排除 IV = 999（超出範圍）
    - 只納入 0 < IV < 900 的有效值

    Args:
        option_closes: 各合約的選擇權收盤價 {contract_code: close}
        strikes: 履約價列表
        underlying_price: 標的價格
        dte: 距到期天數
        risk_free_rate: 無風險利率，百分比值（預設 2.0）
        carry_rate: 持有成本率，百分比值（預設 0.0）

    Returns:
        平均 CIV（百分比值），若無有效 IV 則回傳 None
    """
    ivs = []

    # 使用結構化 mapping 取代 substring matching
    strike_price_map = build_strike_price_map(option_closes)

    for strike in strikes:
        # 使用 .get() 取得對應價格，若無對應則為 None
        close = strike_price_map.get(strike)

        if close and close > 0:
            iv = implied_volatility(
                close, underlying_price, strike, dte,
                risk_free_rate, carry_rate
            )
            # 過濾：排除 0（無效）和 999（超出範圍），只取 0 < iv < 900
            if iv > 0 and iv < 900:
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
    """計算完整的 IV 指標（XQ 相容版本）

    處理順序（對齊 XQ/XS）：
    1. 構造 civ_series = civ_history + [civ]
    2. 對 civ_series 做 5 期移動平均，得到 civ_ma5
    3. 構造 civ_ma_series（歷史 CIV 的 5MA 序列）
    4. 對 civ_ma_series 做 20 期 Bollinger Band
    5. 對 price_series 做 20 期 Bollinger Band
    6. 計算 civ_pb = calc_percent_b(civ_ma5, civ_upper, civ_lower)
    7. 計算 price_pb = calc_percent_b(price, price_upper, price_lower)
    8. 計算 pb_minus_civ_pb = price_pb - civ_pb

    Args:
        civ: 當前 CIV 值（百分比）
        civ_history: CIV 歷史值列表（百分比）
        price: 當前標的價格
        price_history: 價格歷史列表
        period: Bollinger Band 週期（預設 20）

    Returns:
        IndicatorResult 或 None（若資料不足）
    """
    # 構造完整序列
    civ_series = civ_history + [civ]
    price_series = price_history + [price]

    # 計算 CIV 的 5 期移動平均
    ma_period = 5
    civ_ma5 = calc_simple_moving_average(civ_series, ma_period)
    if civ_ma5 is None:
        # CIV 歷史不足以計算 5MA
        return None

    # 建構 CIV 5MA 序列
    civ_ma_series = build_sma_series(civ_series, ma_period)
    # 過濾掉 None 值
    civ_ma_valid = [v for v in civ_ma_series if v is not None]

    # 對 CIV 5MA 序列做 Bollinger Band
    civ_mid, civ_upper, civ_lower = calc_bollinger_band(civ_ma_valid, period)
    if civ_mid is None:
        # CIV 5MA 序列不足以計算 Bollinger
        return None

    # 對價格序列做 Bollinger Band
    price_mid, price_upper, price_lower = calc_bollinger_band(price_series, period)
    if price_mid is None:
        return None

    # 計算 %b（0-100 尺度）
    civ_pb = calc_percent_b(civ_ma5, civ_upper, civ_lower)
    price_pb = calc_percent_b(price, price_upper, price_lower)

    # 計算信號
    pb_minus_civ_pb = price_pb - civ_pb

    return IndicatorResult(
        civ=civ,
        civ_ma5=civ_ma5,
        civ_pb=civ_pb,
        price_pb=price_pb,
        pb_minus_civ_pb=pb_minus_civ_pb,
        signal=pb_minus_civ_pb,  # 向後相容
        timestamp=datetime.now().isoformat()
    )
