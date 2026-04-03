"""MongoDBClient 單元測試"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from src.data.mongodb_client import MongoDBClient


class TestCalculateExpirationDate:
    """測試 _calculate_expiration_date 方法"""

    def test_april_2026(self):
        """2026年4月: 第三個星期三是4/15"""
        client = MongoDBClient()
        result = client._calculate_expiration_date("202604")
        assert result == "20260415"

    def test_may_2026(self):
        """2026年5月: 第三個星期三是5/20"""
        client = MongoDBClient()
        result = client._calculate_expiration_date("202605")
        assert result == "20260520"

    def test_december_2026(self):
        """2026年12月: 第三個星期三是12/16"""
        client = MongoDBClient()
        result = client._calculate_expiration_date("202612")
        assert result == "20261216"

    def test_january_2027(self):
        """2027年1月: 第三個星期三是1/20"""
        client = MongoDBClient()
        result = client._calculate_expiration_date("202701")
        assert result == "20270120"

    def test_march_2026(self):
        """2026年3月: 第三個星期三是3/18"""
        client = MongoDBClient()
        result = client._calculate_expiration_date("202603")
        assert result == "20260318"

    def test_first_day_is_wednesday(self):
        """測試當月第一天就是星期三的情況 (2026年7月)"""
        client = MongoDBClient()
        # 2026年7月1日是星期三，所以第三個星期三是7/15
        result = client._calculate_expiration_date("202607")
        assert result == "20260715"


class TestGetExpirationDateWithRollover:
    """測試 get_expiration_date 含換約邏輯"""

    def test_no_rollover_returns_cached_date(self):
        """未換約時返回快取的到期日"""
        client = MongoDBClient()
        client._expiration_date = "20260318"
        client._futures_month = "202603"

        with patch.object(client, '_should_use_next_month', return_value=False):
            result = client.get_expiration_date()
            assert result == "20260318"

    def test_rollover_calculates_next_month_expiration(self):
        """換約後計算新月份的到期日"""
        client = MongoDBClient()
        client._expiration_date = "20260318"
        client._futures_month = "202603"

        with patch.object(client, '_should_use_next_month', return_value=True):
            result = client.get_expiration_date()
            # 下個月 202604 的到期日是 20260415
            assert result == "20260415"

    def test_december_rollover_to_january(self):
        """12月換約到1月的情況"""
        client = MongoDBClient()
        client._expiration_date = "20261216"
        client._futures_month = "202612"

        with patch.object(client, '_should_use_next_month', return_value=True):
            result = client.get_expiration_date()
            # 下個月 202701 的到期日是 20270120
            assert result == "20270120"


class TestCalculateNextMonth:
    """測試 _calculate_next_month 方法"""

    def test_normal_month(self):
        """一般月份遞增"""
        client = MongoDBClient()
        assert client._calculate_next_month("202603") == "202604"
        assert client._calculate_next_month("202611") == "202612"

    def test_december_to_january(self):
        """12月跨年到1月"""
        client = MongoDBClient()
        assert client._calculate_next_month("202612") == "202701"

    def test_integer_input(self):
        """整數輸入也能正確處理"""
        client = MongoDBClient()
        assert client._calculate_next_month(202603) == "202604"


class TestShouldUseNextMonth:
    """測試 _should_use_next_month 方法"""

    def test_today_after_expiration(self):
        """今天超過到期日"""
        client = MongoDBClient()
        client._expiration_date = "20260318"

        # Mock 今天是 3/20
        with patch('src.data.mongodb_client.datetime') as mock_datetime:
            mock_now = MagicMock()
            mock_now.strftime.return_value = "20260320"
            mock_now.hour = 10
            mock_datetime.now.return_value = mock_now

            assert client._should_use_next_month() is True

    def test_today_is_expiration_after_14(self):
        """今天是到期日且已過 14:00"""
        client = MongoDBClient()
        client._expiration_date = "20260318"

        with patch('src.data.mongodb_client.datetime') as mock_datetime:
            mock_now = MagicMock()
            mock_now.strftime.return_value = "20260318"
            mock_now.hour = 15
            mock_datetime.now.return_value = mock_now

            assert client._should_use_next_month() is True

    def test_today_is_expiration_before_14(self):
        """今天是到期日但未到 14:00"""
        client = MongoDBClient()
        client._expiration_date = "20260318"

        with patch('src.data.mongodb_client.datetime') as mock_datetime:
            mock_now = MagicMock()
            mock_now.strftime.return_value = "20260318"
            mock_now.hour = 10
            mock_datetime.now.return_value = mock_now

            assert client._should_use_next_month() is False

    def test_today_before_expiration(self):
        """今天在到期日之前"""
        client = MongoDBClient()
        client._expiration_date = "20260318"

        with patch('src.data.mongodb_client.datetime') as mock_datetime:
            mock_now = MagicMock()
            mock_now.strftime.return_value = "20260315"
            mock_now.hour = 10
            mock_datetime.now.return_value = mock_now

            assert client._should_use_next_month() is False
