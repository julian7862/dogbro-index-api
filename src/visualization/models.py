"""資料模型定義

此模組定義 IV 指標的資料結構。
所有欄位值由外部模組計算後傳入，本模組不做任何指標運算。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class IndicatorResult:
    """5 分 K IV 指標資料

    欄位說明:
    ---------
    current_dt : datetime
        當前 5 分 K bar 的時間，作為圖表 x 軸
        來源: 外部 5 分 K bar 時間

    underlying_price : float
        台指期近月的 5 分 K close
        來源: 外部提供
        用途: 主圖價格 / annotation / debug

    dte : int
        剩餘到期天數
        來源: 外部模組計算後傳入
        用途: metadata / debug / future extension

    valid_call_iv_count : int
        本根 bar 實際有效的 Call IV 數量
        來源: 外部模組計算後傳入
        用途: 資料品質檢查 / warning

    civ : Optional[float]
        已計算完成的 CIV 值 (Call Implied Volatility)
        來源: 外部已算好
        用途: debug / future extension

    civ_ma5 : Optional[float]
        已計算完成的 CIV 5MA
        來源: 外部已算好
        用途: debug / future extension

    civ_pb : Optional[float]
        已計算完成的 CIV Bollinger %b
        來源: 外部已算好
        用途: 副圖黃線主資料

    price_pb : Optional[float]
        已計算完成的 price Bollinger %b
        來源: 外部已算好
        用途: metadata / validation / future extension

    pb_minus_civ_pb : Optional[float]
        已計算完成的 price_pb - civ_pb
        來源: 外部已算好
        用途: 副圖紅綠柱主資料

    warnings : List[str]
        由外部模組產生的警示訊息列表
        來源: 外部模組
        用途: 資料狀態標記 / future UI warning
        可能值: "LOW_VALID_IV_COUNT", "CIV_MISSING", "CIV_PB_MISSING", "PRICE_PB_MISSING"

    iv_spread : Optional[float]
        (可選) IV 價差
        來源: 外部模組若有提供則帶入
        用途: annotation optional display

    strike_list : Optional[List[int]]
        (可選) 履約價列表
        來源: 外部模組若有提供則帶入
        用途: debug / future basket inspection

    策略預留欄位:
    -------------
    signal_long_candidate : Optional[bool]
        預留: 多方候選訊號

    signal_short_candidate : Optional[bool]
        預留: 空方候選訊號

    regime_state : Optional[str]
        預留: 市場狀態分類 (如 "trending", "ranging", "volatile")
    """

    # === 必要欄位 ===
    current_dt: datetime
    underlying_price: float
    dte: int
    valid_call_iv_count: int

    # === 指標欄位 (由外部計算) ===
    civ: Optional[float] = None
    civ_ma5: Optional[float] = None
    civ_pb: Optional[float] = None
    price_pb: Optional[float] = None
    pb_minus_civ_pb: Optional[float] = None

    # === 警示與可選欄位 ===
    warnings: List[str] = field(default_factory=list)
    iv_spread: Optional[float] = None
    strike_list: Optional[List[int]] = None

    # === 策略預留欄位 ===
    signal_long_candidate: Optional[bool] = None
    signal_short_candidate: Optional[bool] = None
    regime_state: Optional[str] = None
