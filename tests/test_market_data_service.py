"""Unit tests for Market Data Service

測試內容：
1. 環境變數驗證
2. 服務啟動與停止
3. 錯誤處理
4. 合約訂閱更新
5. 心跳機制
"""

import pytest
import sys
import os
from unittest.mock import Mock, MagicMock, patch, call
from src.services.market_data_service import MarketDataService


class TestMarketDataService:
    """Market Data Service 單元測試"""

    @pytest.fixture
    def mock_gateway_client(self):
        """模擬 Gateway Client"""
        client = Mock()
        client.is_connected.return_value = True
        client.connect = Mock()
        client.disconnect = Mock()
        client.emit = Mock()
        return client

    @pytest.fixture
    def mock_shioaji_client(self):
        """模擬 Shioaji Client"""
        client = Mock()
        client.is_connected.return_value = True
        client.connect = Mock()
        client.disconnect = Mock()
        client.get_api.return_value = Mock()
        client.get_version.return_value = "1.0.0"
        client._config = Mock(simulation=True)
        return client

    @pytest.fixture
    def service(self, mock_gateway_client, mock_shioaji_client):
        """建立測試用的服務實例"""
        return MarketDataService(
            gateway_client=mock_gateway_client,
            shioaji_client=mock_shioaji_client,
            heartbeat_interval=10,
            snapshot_interval=5,
            contract_update_interval=1
        )

    def test_init(self, service):
        """測試服務初始化"""
        assert service is not None
        assert not service.is_running()
        assert service._heartbeat_interval == 10
        assert service._snapshot_interval == 5
        assert service._contract_update_interval == 1

    @patch.dict(os.environ, {
        'SJ_KEY': 'test_key',
        'SJ_SEC': 'test_secret',
        'GATEWAY_URL': 'http://test:3001'
    })
    def test_validate_environment_success(self, service):
        """測試環境變數驗證成功"""
        # 不應該拋出異常
        service._validate_environment()

    @patch.dict(os.environ, {}, clear=True)
    def test_validate_environment_missing_vars(self, service):
        """測試環境變數缺失時的處理"""
        with pytest.raises(SystemExit) as exc_info:
            service._validate_environment()

        assert exc_info.value.code == 1

    @patch.dict(os.environ, {
        'SJ_KEY': 'test_key',
        'SJ_SEC': 'test_secret',
        'GATEWAY_URL': 'http://test:3001'
    })
    def test_emit_ready_status(self, service, mock_gateway_client):
        """測試發送就緒狀態"""
        service._emit_ready_status()

        mock_gateway_client.emit.assert_called_once()
        call_args = mock_gateway_client.emit.call_args

        assert call_args[0][0] == 'shioaji_ready'
        assert call_args[0][1]['status'] == 'ready'
        assert call_args[0][1]['service_type'] == 'market_data'

    def test_send_heartbeat_when_connected(self, service, mock_gateway_client):
        """測試心跳發送（連接時）"""
        mock_gateway_client.is_connected.return_value = True

        service._send_heartbeat()

        mock_gateway_client.emit.assert_called_once_with(
            'heartbeat',
            {
                'status': 'running',
                'shioaji_connected': True,
                'gateway_connected': True,
                'current_price': None,
                'subscribed_contracts': 0,
                'futures_month': None,
                'closing_index': None
            }
        )

    def test_send_heartbeat_when_disconnected(self, service, mock_gateway_client):
        """測試心跳發送（未連接時）"""
        mock_gateway_client.is_connected.return_value = False

        service._send_heartbeat()

        # 未連接時不應該發送
        mock_gateway_client.emit.assert_not_called()

    def test_emit_error_when_connected(self, service, mock_gateway_client):
        """測試錯誤發送（連接時）"""
        mock_gateway_client.is_connected.return_value = True

        service._emit_error("Test error")

        mock_gateway_client.emit.assert_called_once()
        call_args = mock_gateway_client.emit.call_args

        assert call_args[0][0] == 'python_error'
        assert call_args[0][1]['error'] == "Test error"
        assert call_args[0][1]['service'] == 'market_data'

    def test_emit_error_when_disconnected(self, service, mock_gateway_client):
        """測試錯誤發送（未連接時）"""
        mock_gateway_client.is_connected.return_value = False

        service._emit_error("Test error")

        # 未連接時也應該嘗試發送（內部會處理）
        # 但不會拋出異常
        assert True  # 沒有異常就通過

    def test_update_current_price(self, service):
        """測試更新當前價格"""
        # 模擬 tick 資料
        tick = Mock()
        tick.close = 18000.0

        service._update_current_price(tick)

        assert service._current_index_price == 18000.0

    def test_update_current_price_with_invalid_data(self, service):
        """測試更新無效價格"""
        # 模擬無效的 tick 資料
        tick = Mock()
        tick.close = None
        tick.price = None

        service._update_current_price(tick)

        # 價格應該保持 None
        assert service._current_index_price is None

    def test_ensure_subscriptions_without_price(self, service):
        """測試沒有有效價格時的訂閱更新"""
        service._contract_manager = Mock()

        service._ensure_subscriptions()

        # 沒有價格時不應該更新訂閱
        service._contract_manager.update_subscriptions.assert_not_called()

    def test_ensure_subscriptions_with_valid_price(self, service):
        """測試有效價格時的訂閱更新"""
        service._contract_manager = Mock()
        service._current_index_price = 18000.0

        service._ensure_subscriptions()

        # 有價格時應該更新訂閱
        service._contract_manager.update_subscriptions.assert_called_once_with(
            current_price=18000.0,
            range_strikes=8,
            option_type='call'
        )

    def test_stop_service(self, service, mock_gateway_client, mock_shioaji_client):
        """測試停止服務"""
        service._running = True
        service._contract_manager = Mock()

        service.stop()

        assert not service.is_running()
        service._contract_manager.unsubscribe_all.assert_called_once()
        mock_shioaji_client.disconnect.assert_called_once()
        mock_gateway_client.disconnect.assert_called_once()

    def test_stop_service_when_not_running(self, service):
        """測試停止未運行的服務"""
        service._running = False

        # 不應該拋出異常
        service.stop()

        assert not service.is_running()

    @patch('src.services.market_data_service.time')
    @patch('src.services.market_data_service.datetime')
    @patch('sys.exit')
    def test_check_scheduled_restart_trigger(self, mock_exit, mock_datetime, mock_time, service):
        """測試排程重啟觸發（在指定時間）"""
        # Mock 時間為 08:40
        mock_now = Mock()
        mock_now.hour = 8
        mock_now.minute = 40
        mock_datetime.now.return_value = mock_now

        # Mock time.time() 讓 uptime > 120 秒
        mock_time.time.return_value = service._service_start_time + 200

        # Mock service.stop
        service.stop = Mock()

        # 執行檢查
        service._check_scheduled_restart()

        # 驗證 stop 和 exit 都被呼叫
        service.stop.assert_called_once()
        mock_exit.assert_called_once_with(0)

    @patch('src.services.market_data_service.datetime')
    @patch('sys.exit')
    def test_check_scheduled_restart_ignore(self, mock_exit, mock_datetime, service):
        """測試排程重啟忽略（非指定時間）"""
        # Mock 時間為 09:00（非重啟時間）
        mock_now = Mock()
        mock_now.hour = 9
        mock_now.minute = 0
        mock_datetime.now.return_value = mock_now

        # 執行檢查
        service._check_scheduled_restart()

        # 驗證 exit 沒有被呼叫
        mock_exit.assert_not_called()

    @patch('src.services.market_data_service.time')
    @patch('src.services.market_data_service.datetime')
    @patch('sys.exit')
    def test_check_scheduled_restart_no_duplicate_trigger(self, mock_exit, mock_datetime, mock_time, service):
        """測試同一分鐘內不重複觸發重啟"""
        # Mock 時間為 06:30
        mock_now = Mock()
        mock_now.hour = 6
        mock_now.minute = 30
        mock_datetime.now.return_value = mock_now

        # Mock time.time() 讓 uptime > 120 秒
        mock_time.time.return_value = service._service_start_time + 200

        # Mock service.stop
        service.stop = Mock()

        # 第一次呼叫應該觸發重啟
        service._check_scheduled_restart()
        assert mock_exit.call_count == 1

        # 重置 mock
        mock_exit.reset_mock()
        service.stop.reset_mock()

        # 同一分鐘再次呼叫不應該觸發
        service._check_scheduled_restart()
        mock_exit.assert_not_called()
        service.stop.assert_not_called()
