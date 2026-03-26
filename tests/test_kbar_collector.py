"""K 棒收集器測試"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.indicators.kbar_collector import KBarCollector, KBarData


class TestKBarData:
    """測試 KBarData 資料類別"""

    def test_creation(self):
        """建立 KBarData"""
        ts = datetime(2026, 3, 20, 10, 0, 0)
        bar = KBarData(timestamp=ts, close=100.5)

        assert bar.timestamp == ts
        assert bar.close == 100.5


class TestKBarCollector:
    """測試 KBarCollector"""

    def test_init_without_mongo(self):
        """不使用 MongoDB 初始化"""
        collector = KBarCollector(max_bars=20)

        assert collector._max_bars == 20
        assert collector._client is None
        assert collector._collection is None

    def test_update_close(self):
        """更新收盤價"""
        collector = KBarCollector(max_bars=20)

        collector.update_close('TXO22000D6', 500.0)
        collector.update_close('TXO22100D6', 400.0)

        assert collector._latest_close['TXO22000D6'] == 500.0
        assert collector._latest_close['TXO22100D6'] == 400.0

    def test_update_close_ignores_zero(self):
        """更新收盤價忽略零值"""
        collector = KBarCollector(max_bars=20)

        collector.update_close('TXO22000D6', 500.0)
        collector.update_close('TXO22000D6', 0)

        assert collector._latest_close['TXO22000D6'] == 500.0

    def test_get_bar_time(self):
        """取得 K 棒時間"""
        collector = KBarCollector(max_bars=20)

        # 10:03 -> 10:00
        dt1 = datetime(2026, 3, 20, 10, 3, 45)
        assert collector._get_bar_time(dt1) == datetime(2026, 3, 20, 10, 0, 0)

        # 10:07 -> 10:05
        dt2 = datetime(2026, 3, 20, 10, 7, 30)
        assert collector._get_bar_time(dt2) == datetime(2026, 3, 20, 10, 5, 0)

        # 10:59 -> 10:55
        dt3 = datetime(2026, 3, 20, 10, 59, 59)
        assert collector._get_bar_time(dt3) == datetime(2026, 3, 20, 10, 55, 0)

    def test_check_and_record_bar_first_time(self):
        """首次記錄 K 棒"""
        collector = KBarCollector(max_bars=20)

        collector.update_close('TXO22000D6', 500.0)
        collector.update_close('TXO22100D6', 400.0)

        result = collector.check_and_record_bar()

        assert result is not None
        assert 'TXO22000D6' in result
        assert 'TXO22100D6' in result
        assert result['TXO22000D6'] == 500.0

    def test_check_and_record_bar_same_minute(self):
        """同一分鐘內不重複記錄"""
        collector = KBarCollector(max_bars=20)

        collector.update_close('TXO22000D6', 500.0)
        collector.check_and_record_bar()

        # 更新價格但在同一 5 分鐘內
        collector.update_close('TXO22000D6', 510.0)
        result = collector.check_and_record_bar()

        assert result is None

    def test_get_closes(self):
        """取得歷史收盤價"""
        collector = KBarCollector(max_bars=20)

        # 模擬記錄多根 K 棒
        collector.update_close('TXO22000D6', 500.0)
        collector._last_bar_time = None  # 重置以允許記錄
        collector.check_and_record_bar()

        closes = collector.get_closes('TXO22000D6')

        assert len(closes) == 1
        assert closes[0] == 500.0

    def test_get_closes_empty(self):
        """取得空的歷史收盤價"""
        collector = KBarCollector(max_bars=20)

        closes = collector.get_closes('TXO22000D6')

        assert closes == []

    def test_get_latest_bar_close(self):
        """取得最新 K 棒收盤價"""
        collector = KBarCollector(max_bars=20)

        collector.update_close('TXO22000D6', 500.0)
        collector.check_and_record_bar()

        latest = collector.get_latest_bar_close('TXO22000D6')

        assert latest == 500.0

    def test_get_latest_bar_close_none(self):
        """取得不存在的合約"""
        collector = KBarCollector(max_bars=20)

        latest = collector.get_latest_bar_close('TXO99999D6')

        assert latest is None

    def test_max_bars_limit(self):
        """最大 K 棒數量限制"""
        collector = KBarCollector(max_bars=3)

        # 手動加入超過限制的 K 棒
        from collections import deque
        collector._kbars['TXO22000D6'] = deque(maxlen=3)
        for i in range(5):
            collector._kbars['TXO22000D6'].append(
                KBarData(timestamp=datetime(2026, 3, 20, 10, i * 5, 0), close=100 + i)
            )

        closes = collector.get_closes('TXO22000D6')

        assert len(closes) == 3
        # 應該保留最新的 3 根
        assert closes == [102, 103, 104]

    def test_get_all_latest_closes(self):
        """取得所有合約的最新 K 棒收盤價"""
        collector = KBarCollector(max_bars=20)

        collector.update_close('TXO22000D6', 500.0)
        collector.update_close('TXO22100D6', 400.0)
        collector.check_and_record_bar()

        all_closes = collector.get_all_latest_closes()

        assert 'TXO22000D6' in all_closes
        assert 'TXO22100D6' in all_closes
        assert all_closes['TXO22000D6'] == 500.0


class TestKBarCollectorWithMongo:
    """測試 KBarCollector 的 MongoDB 功能 (使用 mock)"""

    @patch('pymongo.MongoClient')
    def test_init_with_mongo(self, mock_mongo_client):
        """使用 MongoDB 初始化"""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = []

        mock_mongo_client.return_value = mock_client
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection

        collector = KBarCollector(max_bars=20, mongo_uri='mongodb://test')

        assert collector._client is not None
        mock_collection.create_index.assert_called_once()

    @patch('pymongo.MongoClient')
    def test_save_bar(self, mock_mongo_client):
        """儲存 K 棒到 MongoDB"""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = []

        mock_mongo_client.return_value = mock_client
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection

        collector = KBarCollector(max_bars=20, mongo_uri='mongodb://test')

        bar = KBarData(timestamp=datetime(2026, 3, 20, 10, 0, 0), close=500.0)
        collector._save_bar('TXO22000D6', bar)

        mock_collection.update_one.assert_called_once()

    @patch('pymongo.MongoClient')
    def test_close(self, mock_mongo_client):
        """關閉 MongoDB 連線"""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = []

        mock_mongo_client.return_value = mock_client
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection

        collector = KBarCollector(max_bars=20, mongo_uri='mongodb://test')
        collector.close()

        mock_client.close.assert_called_once()
