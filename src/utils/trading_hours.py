"""交易時段判斷工具

判斷當前時間是否在台灣期權交易時段：
- 早盤: 08:45 - 13:45
- 夜盤: 15:00 - 次日 05:00
"""

from datetime import datetime, time
import pytz

TW_TZ = pytz.timezone('Asia/Taipei')


def is_trading_hours(dt: datetime = None) -> bool:
    """判斷是否在交易時段

    Args:
        dt: 要判斷的時間 (預設為現在)

    Returns:
        True 若在交易時段
    """
    if dt is None:
        dt = datetime.now(TW_TZ)
    elif dt.tzinfo is None:
        dt = TW_TZ.localize(dt)

    t = dt.time()

    # 早盤: 08:45 - 13:45
    morning_start = time(8, 45)
    morning_end = time(13, 45)

    # 夜盤: 15:00 - 05:00 (跨日)
    night_start = time(15, 0)
    night_end = time(5, 0)

    # 早盤
    if morning_start <= t <= morning_end:
        return True

    # 夜盤 (15:00 - 23:59 或 00:00 - 05:00)
    if t >= night_start or t <= night_end:
        return True

    return False


def get_session_name(dt: datetime = None) -> str:
    """取得當前交易時段名稱

    Args:
        dt: 要判斷的時間 (預設為現在)

    Returns:
        "早盤", "夜盤", 或 "收盤"
    """
    if dt is None:
        dt = datetime.now(TW_TZ)
    elif dt.tzinfo is None:
        dt = TW_TZ.localize(dt)

    t = dt.time()

    if time(8, 45) <= t <= time(13, 45):
        return "早盤"
    if t >= time(15, 0) or t <= time(5, 0):
        return "夜盤"
    return "收盤"
