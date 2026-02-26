"""Unit tests for Market Data Handler

測試內容：
1. Tick 資料處理
2. 委買委賣資料處理
3. 快照資料處理
4. 錯誤處理
5. Socket 連接檢查
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from src.trading.market_data_handler import MarketDataHandler


class TestMarketDataHandler:
    """Market Data Handler 單元測試"""

    @pytest.fixture
    def mock_gateway_client(self):
        """模擬 Gateway Client"""
        client = Mock()
        client.is_connected.return_value = True
        client.emit = Mock()
        return client

    @pytest.fixture
    def mock_contract_manager(self):
        """模擬 Contract Manager"""
        manager = Mock()
        return manager

    @pytest.fixture
    def handler(self, mock_gateway_client, mock_contract_manager):
        """建立測試用的處理器實例"""
        return MarketDataHandler(
            gateway_client=mock_gateway_client,
            contract_manager=mock_contract_manager
        )

    def test_init(self, handler):
        """測試處理器初始化"""
        assert handler is not None
        assert len(handler._last_tick_time) == 0
        assert len(handler._last_bidask_time) == 0

    def test_handle_tick_success(self, handler, mock_gateway_client):
        """測試處理 tick 資料成功"""
        # 模擬 tick 資料
        tick = Mock()
        tick.code = "TXO18000C"
        tick.datetime = "2026-02-26 12:00:00"
        tick.open = 100.0
        tick.high = 105.0
        tick.low = 99.0
        tick.close = 103.0
        tick.volume = 10
        tick.total_volume = 100

        handler.handle_tick("TAIFEX", tick)

        # 應該呼叫 emit
        mock_gateway_client.emit.assert_called_once()
        call_args = mock_gateway_client.emit.call_args

        assert call_args[0][0] == 'market_tick'
        assert call_args[0][1]['code'] == "TXO18000C"
        assert call_args[0][1]['close'] == 103.0

    def test_handle_tick_when_disconnected(self, handler, mock_gateway_client):
        """測試 Gateway 未連接時處理 tick"""
        mock_gateway_client.is_connected.return_value = False

        tick = Mock()
        tick.code = "TXO18000C"
        tick.close = 103.0

        handler.handle_tick("TAIFEX", tick)

        # 不應該呼叫 emit
        mock_gateway_client.emit.assert_not_called()

    def test_handle_tick_with_exception(self, handler, mock_gateway_client):
        """測試處理 tick 時發生異常"""
        # 模擬異常
        mock_gateway_client.emit.side_effect = Exception("Emit error")

        tick = Mock()
        tick.code = "TXO18000C"
        tick.close = 103.0

        # 不應該拋出異常（內部處理）
        handler.handle_tick("TAIFEX", tick)

    def test_handle_bidask_success(self, handler, mock_gateway_client):
        """測試處理委買委賣資料成功"""
        # 模擬委買委賣資料
        bidask = Mock()
        bidask.code = "TXO18000C"
        bidask.datetime = "2026-02-26 12:00:00"
        bidask.bid_price = [102.0]
        bidask.bid_volume = [5]
        bidask.ask_price = [103.0]
        bidask.ask_volume = [3]

        handler.handle_bidask("TAIFEX", bidask)

        # 應該呼叫 emit
        mock_gateway_client.emit.assert_called_once()
        call_args = mock_gateway_client.emit.call_args

        assert call_args[0][0] == 'market_bidask'
        assert call_args[0][1]['code'] == "TXO18000C"

    def test_handle_bidask_when_disconnected(self, handler, mock_gateway_client):
        """測試 Gateway 未連接時處理委買委賣"""
        mock_gateway_client.is_connected.return_value = False

        bidask = Mock()
        bidask.code = "TXO18000C"

        handler.handle_bidask("TAIFEX", bidask)

        # 不應該呼叫 emit
        mock_gateway_client.emit.assert_not_called()

    def test_handle_snapshot_single(self, handler, mock_gateway_client):
        """測試處理單個快照"""
        snapshot = Mock()
        snapshot.code = "TXO18000C"
        snapshot.name = "台指選擇權"
        snapshot.open = 100.0
        snapshot.high = 105.0
        snapshot.low = 99.0
        snapshot.close = 103.0
        snapshot.volume = 100
        snapshot.amount = 10300.0
        snapshot.total_volume = 1000

        handler.handle_snapshot(snapshot)

        mock_gateway_client.emit.assert_called_once()

    def test_handle_snapshot_list(self, handler, mock_gateway_client):
        """測試處理快照列表"""
        snapshot1 = Mock()
        snapshot1.code = "TXO18000C"
        snapshot1.close = 103.0

        snapshot2 = Mock()
        snapshot2.code = "TXO18100C"
        snapshot2.close = 95.0

        handler.handle_snapshot([snapshot1, snapshot2])

        # 應該呼叫 emit 兩次
        assert mock_gateway_client.emit.call_count == 2

    def test_extract_tick_data_success(self, handler):
        """測試提取 tick 資料成功"""
        tick = Mock()
        tick.code = "TXO18000C"
        tick.datetime = "2026-02-26 12:00:00"
        tick.open = 100.0
        tick.high = 105.0
        tick.low = 99.0
        tick.close = 103.0
        tick.volume = 10
        tick.total_volume = 100

        data = handler._extract_tick_data("TAIFEX", tick)

        assert data is not None
        assert data['code'] == "TXO18000C"
        assert data['close'] == 103.0
        assert data['exchange'] == "TAIFEX"

    def test_extract_tick_data_missing_code(self, handler):
        """測試提取缺少 code 的 tick 資料"""
        tick = Mock()
        tick.code = None
        tick.close = 103.0

        data = handler._extract_tick_data("TAIFEX", tick)

        # 應該返回 None
        assert data is None

    def test_extract_bidask_data_success(self, handler):
        """測試提取委買委賣資料成功"""
        bidask = Mock()
        bidask.code = "TXO18000C"
        bidask.datetime = "2026-02-26 12:00:00"
        bidask.bid_price = [102.0]
        bidask.bid_volume = [5]
        bidask.ask_price = [103.0]
        bidask.ask_volume = [3]

        data = handler._extract_bidask_data("TAIFEX", bidask)

        assert data is not None
        assert data['code'] == "TXO18000C"
        assert data['exchange'] == "TAIFEX"

    def test_safe_getattr_success(self, handler):
        """測試安全取得屬性成功"""
        obj = Mock()
        obj.test_attr = "test_value"

        result = handler._safe_getattr(obj, "test_attr")

        assert result == "test_value"

    def test_safe_getattr_missing_attribute(self, handler):
        """測試安全取得不存在的屬性"""
        obj = Mock()

        result = handler._safe_getattr(obj, "missing_attr", default="default")

        assert result == "default"

    def test_safe_getattr_with_exception(self, handler):
        """測試取得屬性時發生異常"""
        obj = Mock()
        # 模擬 getattr 拋出異常
        type(obj).test_attr = property(lambda self: 1/0)

        result = handler._safe_getattr(obj, "test_attr", default="default")

        assert result == "default"

    def test_get_stats(self, handler):
        """測試取得統計資訊"""
        # 模擬一些追蹤資料
        handler._last_tick_time = {
            "TXO18000C": 1234567890.0,
            "TXO18100C": 1234567895.0
        }
        handler._last_bidask_time = {
            "TXO18000C": 1234567891.0
        }

        stats = handler.get_stats()

        assert stats['tick_contracts_tracked'] == 2
        assert stats['bidask_contracts_tracked'] == 1
        assert stats['last_tick_update'] == 1234567895.0
        assert stats['last_bidask_update'] == 1234567891.0
