"""Market Data Handler - 處理 Shioaji 行情回呼

負責：
1. 處理 tick 資料回呼
2. 處理委買委賣資料回呼
3. 處理快照資料
4. 推播行情給 Gateway（含錯誤處理）
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from src.gateway.gateway_client import GatewayClient
from src.trading.contract_manager import ContractManager

logger = logging.getLogger(__name__)


class MarketDataHandler:
    """行情資料處理器

    職責：
    - 處理來自 Shioaji 的行情回呼
    - 整理行情資料格式
    - 安全地推播給 Gateway
    - 維護行情狀態
    """

    def __init__(
        self,
        gateway_client: GatewayClient,
        contract_manager: ContractManager
    ):
        """初始化行情處理器

        Args:
            gateway_client: Gateway 客戶端
            contract_manager: 合約管理器
        """
        self._gateway = gateway_client
        self._contract_manager = contract_manager

        # 行情狀態快取（避免重複推送相同資料）
        self._last_tick_time: Dict[str, float] = {}
        self._last_bidask_time: Dict[str, float] = {}

    def handle_tick(self, exchange: str, tick: Any) -> None:
        """處理 tick 資料回呼

        Args:
            exchange: 交易所代碼
            tick: Tick 資料物件

        此方法包含完整的錯誤處理，確保不會因為資料問題而 crash
        """
        try:
            # 提取 tick 資料
            tick_data = self._extract_tick_data(exchange, tick)

            if not tick_data:
                logger.debug("Tick 資料為空，跳過")
                return

            # 檢查 Socket 連接狀態
            if not self._gateway.is_connected():
                logger.debug("Gateway 未連接，無法推送 tick 資料")
                return

            # 推播給 Gateway
            self._gateway.emit('market_tick', tick_data)

            # 更新最後推送時間
            contract_code = tick_data.get('code', 'unknown')
            self._last_tick_time[contract_code] = datetime.now().timestamp()

        except Exception as e:
            logger.error(f"處理 tick 資料時發生錯誤: {e}", exc_info=True)
            # 不要 raise，讓程式繼續運行

    def handle_bidask(self, exchange: str, bidask: Any) -> None:
        """處理委買委賣資料回呼

        Args:
            exchange: 交易所代碼
            bidask: 委買委賣資料物件

        此方法包含完整的錯誤處理，確保不會因為資料問題而 crash
        """
        try:
            # 提取委買委賣資料
            bidask_data = self._extract_bidask_data(exchange, bidask)

            if not bidask_data:
                logger.debug("委買委賣資料為空，跳過")
                return

            # 檢查 Socket 連接狀態
            if not self._gateway.is_connected():
                logger.debug("Gateway 未連接，無法推送委買委賣資料")
                return

            # 推播給 Gateway
            self._gateway.emit('market_bidask', bidask_data)

            # 更新最後推送時間
            contract_code = bidask_data.get('code', 'unknown')
            self._last_bidask_time[contract_code] = datetime.now().timestamp()

        except Exception as e:
            logger.error(f"處理委買委賣資料時發生錯誤: {e}", exc_info=True)
            # 不要 raise，讓程式繼續運行

    def handle_snapshot(self, snapshots: Any) -> None:
        """處理快照資料

        Args:
            snapshots: 快照資料（可能是列表或單一物件）

        此方法包含完整的錯誤處理
        """
        try:
            # 快照可能是列表或單一物件
            snapshot_list = snapshots if isinstance(snapshots, list) else [snapshots]

            for snapshot in snapshot_list:
                snapshot_data = self._extract_snapshot_data(snapshot)

                if snapshot_data and self._gateway.is_connected():
                    self._gateway.emit('market_snapshot', snapshot_data)

        except Exception as e:
            logger.error(f"處理快照資料時發生錯誤: {e}", exc_info=True)

    def _extract_tick_data(self, exchange: str, tick: Any) -> Optional[Dict[str, Any]]:
        """從 tick 物件提取資料

        Args:
            exchange: 交易所代碼
            tick: Tick 物件

        Returns:
            整理後的 tick 資料字典，如果資料無效則返回 None

        此方法安全地提取資料，避免 AttributeError
        """
        try:
            # 安全地提取各個欄位
            data = {
                'exchange': exchange,
                'code': self._safe_getattr(tick, 'code'),
                'datetime': self._safe_getattr(tick, 'datetime'),
                'open': self._safe_getattr(tick, 'open'),
                'high': self._safe_getattr(tick, 'high'),
                'low': self._safe_getattr(tick, 'low'),
                'close': self._safe_getattr(tick, 'close'),
                'price': self._safe_getattr(tick, 'close'),  # 當前價格
                'volume': self._safe_getattr(tick, 'volume'),
                'total_volume': self._safe_getattr(tick, 'total_volume'),
                'timestamp': datetime.now().isoformat()
            }

            # 檢查必要欄位
            if not data.get('code'):
                logger.warning("Tick 資料缺少 code 欄位")
                return None

            return data

        except Exception as e:
            logger.error(f"提取 tick 資料時發生錯誤: {e}")
            return None

    def _extract_bidask_data(self, exchange: str, bidask: Any) -> Optional[Dict[str, Any]]:
        """從委買委賣物件提取資料

        Args:
            exchange: 交易所代碼
            bidask: 委買委賣物件

        Returns:
            整理後的委買委賣資料字典，如果資料無效則返回 None
        """
        try:
            data = {
                'exchange': exchange,
                'code': self._safe_getattr(bidask, 'code'),
                'datetime': self._safe_getattr(bidask, 'datetime'),
                'bid_price': self._safe_getattr(bidask, 'bid_price'),
                'bid_volume': self._safe_getattr(bidask, 'bid_volume'),
                'ask_price': self._safe_getattr(bidask, 'ask_price'),
                'ask_volume': self._safe_getattr(bidask, 'ask_volume'),
                'timestamp': datetime.now().isoformat()
            }

            # 檢查必要欄位
            if not data.get('code'):
                logger.warning("委買委賣資料缺少 code 欄位")
                return None

            return data

        except Exception as e:
            logger.error(f"提取委買委賣資料時發生錯誤: {e}")
            return None

    def _extract_snapshot_data(self, snapshot: Any) -> Optional[Dict[str, Any]]:
        """從快照物件提取資料

        Args:
            snapshot: 快照物件

        Returns:
            整理後的快照資料字典
        """
        try:
            data = {
                'code': self._safe_getattr(snapshot, 'code'),
                'name': self._safe_getattr(snapshot, 'name'),
                'open': self._safe_getattr(snapshot, 'open'),
                'high': self._safe_getattr(snapshot, 'high'),
                'low': self._safe_getattr(snapshot, 'low'),
                'close': self._safe_getattr(snapshot, 'close'),
                'volume': self._safe_getattr(snapshot, 'volume'),
                'amount': self._safe_getattr(snapshot, 'amount'),
                'total_volume': self._safe_getattr(snapshot, 'total_volume'),
                'timestamp': datetime.now().isoformat()
            }

            if not data.get('code'):
                return None

            return data

        except Exception as e:
            logger.error(f"提取快照資料時發生錯誤: {e}")
            return None

    def _safe_getattr(self, obj: Any, attr: str, default: Any = None) -> Any:
        """安全地取得物件屬性

        Args:
            obj: 物件
            attr: 屬性名稱
            default: 預設值

        Returns:
            屬性值或預設值

        避免 AttributeError
        """
        try:
            return getattr(obj, attr, default)
        except (AttributeError, TypeError):
            return default

    def get_stats(self) -> Dict[str, Any]:
        """取得處理器統計資訊

        Returns:
            統計資訊字典
        """
        return {
            'tick_contracts_tracked': len(self._last_tick_time),
            'bidask_contracts_tracked': len(self._last_bidask_time),
            'last_tick_update': max(self._last_tick_time.values()) if self._last_tick_time else None,
            'last_bidask_update': max(self._last_bidask_time.values()) if self._last_bidask_time else None
        }
