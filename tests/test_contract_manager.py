"""Unit tests for Contract Manager

測試內容：
1. ATM 計算
2. 履約價範圍計算
3. 合約查找
4. 訂閱管理
5. 錯誤處理
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from src.trading.contract_manager import ContractManager


class TestContractManager:
    """Contract Manager 單元測試"""

    @pytest.fixture
    def mock_api(self):
        """模擬 Shioaji API"""
        api = Mock()
        api.Contracts = Mock()
        api.Contracts.Options = {}
        api.quote = Mock()
        api.quote.subscribe = Mock()
        api.quote.unsubscribe = Mock()
        return api

    @pytest.fixture
    def manager(self, mock_api):
        """建立測試用的管理器實例"""
        return ContractManager(api=mock_api, strike_interval=100)

    def test_init(self, manager):
        """測試管理器初始化"""
        assert manager is not None
        assert manager._strike_interval == 100
        assert len(manager._subscribed_contracts) == 0

    def test_calculate_atm_strike(self, manager):
        """測試 ATM 履約價計算"""
        # 測試各種價格
        assert manager._calculate_atm_strike(17850) == 17900
        assert manager._calculate_atm_strike(17950) == 18000
        assert manager._calculate_atm_strike(18000) == 18000
        assert manager._calculate_atm_strike(18050) == 18100
        assert manager._calculate_atm_strike(18449) == 18400
        assert manager._calculate_atm_strike(18450) == 18500

    def test_calculate_target_strikes(self, manager):
        """測試目標履約價範圍計算"""
        atm = 18000
        range_strikes = 3

        strikes = manager._calculate_target_strikes(atm, range_strikes)

        # 應該包含 ATM ± 3 檔 = 7 個履約價
        assert len(strikes) == 7
        assert strikes == [17700, 17800, 17900, 18000, 18100, 18200, 18300]

    def test_calculate_target_strikes_boundary(self, manager):
        """測試邊界情況的履約價計算"""
        atm = 100
        range_strikes = 2

        strikes = manager._calculate_target_strikes(atm, range_strikes)

        # 不應該包含負數或零的履約價
        assert all(s > 0 for s in strikes)

    def test_build_contract_key(self, manager):
        """測試合約鍵建立"""
        # 測試 call
        key = manager._build_contract_key(18000, 'call')
        assert 'TXO' in key
        assert '18000' in key
        assert 'C' in key

        # 測試 put
        key = manager._build_contract_key(18000, 'put')
        assert 'TXO' in key
        assert '18000' in key
        assert 'P' in key

    def test_safe_get_contract_with_attribute(self, manager):
        """測試安全取得合約（使用屬性）"""
        options = Mock()
        options.TXO18000C = "contract_object"

        result = manager._safe_get_contract(options, "TXO18000C")

        assert result == "contract_object"

    def test_safe_get_contract_with_dict(self, manager):
        """測試安全取得合約（使用字典）"""
        options = {"TXO18000C": "contract_object"}

        result = manager._safe_get_contract(options, "TXO18000C")

        assert result == "contract_object"

    def test_safe_get_contract_not_found(self, manager):
        """測試安全取得合約（找不到）"""
        options = Mock()

        result = manager._safe_get_contract(options, "TXO99999C")

        assert result is None

    def test_get_subscribed_contracts_empty(self, manager):
        """測試取得訂閱合約（空列表）"""
        contracts = manager.get_subscribed_contracts()

        assert contracts == []

    def test_get_subscribed_contracts_with_cache(self, manager):
        """測試取得訂閱合約（有快取）"""
        # 模擬已訂閱的合約
        contract1 = Mock()
        contract1.code = "TXO18000C"

        contract2 = Mock()
        contract2.code = "TXO18100C"

        manager._subscribed_contracts = {"TXO18000C", "TXO18100C"}
        manager._contract_cache = {
            "TXO18000C": contract1,
            "TXO18100C": contract2
        }

        contracts = manager.get_subscribed_contracts()

        assert len(contracts) == 2
        assert contract1 in contracts
        assert contract2 in contracts

    @patch('src.trading.contract_manager.logger')
    def test_unsubscribe_all(self, mock_logger, manager, mock_api):
        """測試取消所有訂閱"""
        # 設定已訂閱的合約
        contract1 = Mock()
        contract1.code = "TXO18000C"

        manager._subscribed_contracts = {"TXO18000C"}
        manager._contract_cache = {"TXO18000C": contract1}

        manager.unsubscribe_all()

        # 應該嘗試取消訂閱
        mock_api.quote.unsubscribe.assert_called_once_with(contract1)
        assert len(manager._subscribed_contracts) == 0

    @patch('src.trading.contract_manager.logger')
    def test_unsubscribe_all_with_error(self, mock_logger, manager, mock_api):
        """測試取消訂閱時發生錯誤"""
        # 設定已訂閱的合約
        contract1 = Mock()
        contract1.code = "TXO18000C"

        manager._subscribed_contracts = {"TXO18000C"}
        manager._contract_cache = {"TXO18000C": contract1}

        # 模擬取消訂閱失敗
        mock_api.quote.unsubscribe.side_effect = Exception("Unsubscribe error")

        # 不應該拋出異常
        manager.unsubscribe_all()

        # 但應該記錄警告
        assert mock_logger.warning.called

    def test_update_subscriptions_without_contracts(self, manager):
        """測試更新訂閱（找不到合約）"""
        # 模擬找不到合約的情況
        with patch.object(manager, '_find_contracts_by_strikes', return_value=[]):
            manager.update_subscriptions(current_price=18000.0)

            # 不應該拋出異常
            assert len(manager._subscribed_contracts) == 0
