"""資料驗證函數

驗證 DataFrame 結構與缺值處理。
"""

import pandas as pd
from typing import Tuple, List


# 副圖繪製所需的核心欄位
REQUIRED_COLUMNS = ['current_dt', 'civ_pb', 'pb_minus_civ_pb']

# 可選但建議存在的欄位
OPTIONAL_COLUMNS = ['underlying_price', 'civ', 'price_pb', 'iv_spread', 'warnings']


def validate_panel_dataframe(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """驗證 DataFrame 是否可用於繪製副圖

    Args:
        df: 待驗證的 DataFrame

    Returns:
        (is_valid, missing_columns)
        - is_valid: 是否有足夠資料繪圖 (至少有 current_dt)
        - missing_columns: 缺少的欄位列表

    Note:
        即使 civ_pb 或 pb_minus_civ_pb 全部缺失，
        仍可繪製空白副圖，不視為驗證失敗。
    """
    if df is None or df.empty:
        return False, ['DataFrame is empty']

    missing = []
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            missing.append(col)

    # 只要有 current_dt 就算 valid (可繪製空白圖)
    is_valid = 'current_dt' in df.columns

    return is_valid, missing


def check_data_availability(df: pd.DataFrame) -> dict:
    """檢查各欄位的資料可用性

    Args:
        df: DataFrame

    Returns:
        各欄位的統計資訊
    """
    result = {
        'total_rows': len(df),
        'civ_pb_available': 0,
        'pb_minus_civ_pb_available': 0,
        'both_available': 0,
        'neither_available': 0,
    }

    if df.empty:
        return result

    has_civ_pb = df['civ_pb'].notna() if 'civ_pb' in df.columns else pd.Series([False] * len(df))
    has_bar = df['pb_minus_civ_pb'].notna() if 'pb_minus_civ_pb' in df.columns else pd.Series([False] * len(df))

    result['civ_pb_available'] = int(has_civ_pb.sum())
    result['pb_minus_civ_pb_available'] = int(has_bar.sum())
    result['both_available'] = int((has_civ_pb & has_bar).sum())
    result['neither_available'] = int((~has_civ_pb & ~has_bar).sum())

    return result
