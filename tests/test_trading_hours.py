"""交易時段判斷測試"""

import pytest
from datetime import datetime
import pytz

from src.utils.trading_hours import is_trading_hours, get_session_name, TW_TZ


class TestIsTradingHours:
    """測試 is_trading_hours 函數"""

    def test_morning_session_start(self):
        """早盤開始時間"""
        dt = TW_TZ.localize(datetime(2026, 3, 20, 8, 45, 0))
        assert is_trading_hours(dt) is True

    def test_morning_session_middle(self):
        """早盤中間時間"""
        dt = TW_TZ.localize(datetime(2026, 3, 20, 10, 30, 0))
        assert is_trading_hours(dt) is True

    def test_morning_session_end(self):
        """早盤結束時間"""
        dt = TW_TZ.localize(datetime(2026, 3, 20, 13, 45, 0))
        assert is_trading_hours(dt) is True

    def test_afternoon_break(self):
        """中午休息時間"""
        dt = TW_TZ.localize(datetime(2026, 3, 20, 14, 0, 0))
        assert is_trading_hours(dt) is False

    def test_night_session_start(self):
        """夜盤開始時間"""
        dt = TW_TZ.localize(datetime(2026, 3, 20, 15, 0, 0))
        assert is_trading_hours(dt) is True

    def test_night_session_evening(self):
        """夜盤晚間"""
        dt = TW_TZ.localize(datetime(2026, 3, 20, 22, 0, 0))
        assert is_trading_hours(dt) is True

    def test_night_session_midnight(self):
        """夜盤午夜"""
        dt = TW_TZ.localize(datetime(2026, 3, 21, 0, 30, 0))
        assert is_trading_hours(dt) is True

    def test_night_session_early_morning(self):
        """夜盤凌晨"""
        dt = TW_TZ.localize(datetime(2026, 3, 21, 4, 30, 0))
        assert is_trading_hours(dt) is True

    def test_night_session_end(self):
        """夜盤結束時間"""
        dt = TW_TZ.localize(datetime(2026, 3, 21, 5, 0, 0))
        assert is_trading_hours(dt) is True

    def test_after_night_session(self):
        """夜盤結束後"""
        dt = TW_TZ.localize(datetime(2026, 3, 21, 5, 30, 0))
        assert is_trading_hours(dt) is False

    def test_before_morning_session(self):
        """早盤開始前"""
        dt = TW_TZ.localize(datetime(2026, 3, 20, 8, 30, 0))
        assert is_trading_hours(dt) is False

    def test_naive_datetime(self):
        """無時區資訊的 datetime"""
        dt = datetime(2026, 3, 20, 10, 0, 0)  # naive datetime
        # 應該自動使用台北時區
        assert is_trading_hours(dt) is True


class TestGetSessionName:
    """測試 get_session_name 函數"""

    def test_morning_session(self):
        """早盤名稱"""
        dt = TW_TZ.localize(datetime(2026, 3, 20, 10, 0, 0))
        assert get_session_name(dt) == "早盤"

    def test_night_session(self):
        """夜盤名稱"""
        dt = TW_TZ.localize(datetime(2026, 3, 20, 20, 0, 0))
        assert get_session_name(dt) == "夜盤"

    def test_night_session_early_morning(self):
        """凌晨夜盤名稱"""
        dt = TW_TZ.localize(datetime(2026, 3, 21, 3, 0, 0))
        assert get_session_name(dt) == "夜盤"

    def test_closed_afternoon(self):
        """下午收盤"""
        dt = TW_TZ.localize(datetime(2026, 3, 20, 14, 30, 0))
        assert get_session_name(dt) == "收盤"

    def test_closed_early_morning(self):
        """清晨收盤"""
        dt = TW_TZ.localize(datetime(2026, 3, 21, 7, 0, 0))
        assert get_session_name(dt) == "收盤"
