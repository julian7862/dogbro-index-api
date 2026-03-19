"""Strike Calculator - 計算選擇權履約價

根據收盤指數計算 16 個 CALL 選擇權的履約價
"""

from typing import List


def calculate_call_strikes(closing_index: float, num_strikes: int = 8) -> List[int]:
    """計算 CALL 選擇權的履約價列表

    根據收盤指數計算上下各 num_strikes 檔的履約價

    Args:
        closing_index: 收盤指數 (例如 34056.0)
        num_strikes: 上下各幾檔 (預設 8 檔，共 16 個履約價)

    Returns:
        履約價列表 (已排序)

    範例:
        收盤指數 34056
        - base = 34000 (四捨五入到最接近的 100)
        - 上方 8 檔: 34100, 34200, 34300, 34400, 34500, 34600, 34700, 34800
        - 下方 8 檔: 34000, 33900, 33800, 33700, 33600, 33500, 33400, 33300
        - 共 16 個履約價
    """
    # 四捨五入到最接近的 100
    base = round(closing_index / 100) * 100

    strikes = []

    # 從 base - (num_strikes - 1) * 100 到 base + num_strikes * 100
    # 例如 num_strikes = 8 時:
    # -7, -6, -5, -4, -3, -2, -1, 0 (下方 8 檔，含 base)
    # 1, 2, 3, 4, 5, 6, 7, 8 (上方 8 檔)
    for i in range(-(num_strikes - 1), num_strikes + 1):
        strike = int(base + (i * 100))
        if strike > 0:  # 確保履約價為正數
            strikes.append(strike)

    return sorted(strikes)


def calculate_atm_strike(price: float, interval: int = 100) -> int:
    """計算價平履約價 (ATM Strike)

    Args:
        price: 當前價格
        interval: 履約價間隔 (預設 100)

    Returns:
        價平履約價 (四捨五入到最接近的間隔)

    範例:
        - 17850 -> 17900 (50% 往上進位)
        - 17849 -> 17800 (49% 往下捨去)
        - 17950 -> 18000 (50% 往上進位)
    """
    remainder = price % interval
    if remainder >= interval / 2:
        # 往上進位
        return int((price // interval + 1) * interval)
    else:
        # 往下捨去
        return int((price // interval) * interval)
