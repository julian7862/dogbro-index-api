"""Contract Manager - 動態管理期權合約訂閱

負責：
1. 計算價平附近的履約價範圍
2. 動態訂閱/取消訂閱合約
3. 避免 KeyError 和 IndexError
"""

import logging
from typing import List, Set, Optional, Dict
import shioaji as sj

logger = logging.getLogger(__name__)


class ContractManager:
    """期權合約管理器

    職責：
    - 根據當前價格計算應訂閱的合約範圍
    - 管理訂閱狀態
    - 提供安全的合約查詢機制
    """

    def __init__(self, api: sj.Shioaji, strike_interval: int = 100):
        """初始化合約管理器

        Args:
            api: Shioaji API 實例
            strike_interval: 履約價間隔（大台選擇權通常是 100）
        """
        self._api = api
        self._strike_interval = strike_interval
        self._subscribed_contracts: Set[str] = set()  # 使用 contract code 作為鍵
        self._contract_cache: Dict[str, any] = {}  # contract code -> contract object

    def update_subscriptions(
        self,
        current_price: float,
        range_strikes: int = 8,
        option_type: str = 'call'
    ) -> None:
        """更新合約訂閱（動態追蹤價平附近選擇權）

        Args:
            current_price: 當前大台指數價格
            range_strikes: 價平上下幾檔（預設 8 檔）
            option_type: 選擇權類型 ('call' 或 'put')

        此方法會：
        1. 計算應訂閱的履約價範圍
        2. 找出需要新增/移除的合約
        3. 執行訂閱/取消訂閱操作
        """
        try:
            # 計算 ATM 履約價（四捨五入到最接近的間隔）
            atm_strike = self._calculate_atm_strike(current_price)

            # 計算訂閱範圍
            target_strikes = self._calculate_target_strikes(atm_strike, range_strikes)

            # 找出目標合約
            target_contracts = self._find_contracts_by_strikes(target_strikes, option_type)

            if not target_contracts:
                logger.warning(f"找不到履約價範圍 {target_strikes} 的合約")
                return

            # 計算需要新增/移除的合約
            target_codes = set(c.code for c in target_contracts)
            to_subscribe = target_codes - self._subscribed_contracts
            to_unsubscribe = self._subscribed_contracts - target_codes

            # 執行訂閱操作
            if to_subscribe:
                self._subscribe_contracts([c for c in target_contracts if c.code in to_subscribe])

            # 執行取消訂閱操作
            if to_unsubscribe:
                self._unsubscribe_contracts(to_unsubscribe)

            logger.info(
                f"合約訂閱更新完成 | ATM: {atm_strike} | "
                f"訂閱: {len(self._subscribed_contracts)} 個合約"
            )

        except Exception as e:
            logger.error(f"更新合約訂閱時發生錯誤: {e}", exc_info=True)

    def get_subscribed_contracts(self) -> List:
        """取得當前訂閱的合約列表"""
        return [
            self._contract_cache[code]
            for code in self._subscribed_contracts
            if code in self._contract_cache
        ]

    def unsubscribe_all(self) -> None:
        """取消所有訂閱"""
        if self._subscribed_contracts:
            logger.info(f"正在取消 {len(self._subscribed_contracts)} 個合約的訂閱")
            self._unsubscribe_contracts(self._subscribed_contracts.copy())

    def _calculate_atm_strike(self, price: float) -> int:
        """計算價平履約價（四捨五入到最接近的間隔）

        Args:
            price: 當前價格

        Returns:
            價平履約價
        """
        return round(price / self._strike_interval) * self._strike_interval

    def _calculate_target_strikes(self, atm_strike: int, range_strikes: int) -> List[int]:
        """計算目標履約價列表

        Args:
            atm_strike: 價平履約價
            range_strikes: 上下幾檔

        Returns:
            履約價列表（例如 ATM ± 8 檔）
        """
        strikes = []
        for i in range(-range_strikes, range_strikes + 1):
            strike = atm_strike + (i * self._strike_interval)
            if strike > 0:  # 確保履約價為正數
                strikes.append(strike)
        return strikes

    def _find_contracts_by_strikes(
        self,
        strikes: List[int],
        option_type: str = 'call'
    ) -> List:
        """根據履約價列表查找合約

        Args:
            strikes: 履約價列表
            option_type: 選擇權類型 ('call' 或 'put')

        Returns:
            找到的合約列表

        此方法包含完整的錯誤處理，避免 KeyError 和 IndexError
        """
        contracts = []

        try:
            # 取得期貨選擇權合約
            # 注意：這裡的實作需要根據實際的 Shioaji API 來調整
            # 以下是範例實作

            # 假設我們已經有 fetch_contracts 或類似的方法
            # 這裡需要根據實際情況調整
            if not hasattr(self._api, 'Contracts') or not hasattr(self._api.Contracts, 'Options'):
                logger.error("Shioaji API 結構不符合預期，無法取得選擇權合約")
                return contracts

            # 嘗試取得選擇權合約
            options = self._api.Contracts.Options

            for strike in strikes:
                try:
                    # 這裡需要根據實際的合約命名規則來查找
                    # 以下是範例邏輯，實際需要調整
                    contract_key = self._build_contract_key(strike, option_type)

                    # 安全地查找合約
                    contract = self._safe_get_contract(options, contract_key)

                    if contract:
                        contracts.append(contract)
                        # 快取合約
                        self._contract_cache[contract.code] = contract
                    else:
                        logger.debug(f"找不到履約價 {strike} 的合約")

                except (KeyError, IndexError, AttributeError) as e:
                    logger.debug(f"查找履約價 {strike} 合約時發生錯誤: {e}")
                    continue

        except Exception as e:
            logger.error(f"查找合約時發生錯誤: {e}", exc_info=True)

        return contracts

    def _build_contract_key(self, strike: int, option_type: str) -> str:
        """建立合約查找鍵

        Args:
            strike: 履約價
            option_type: 選擇權類型

        Returns:
            合約鍵（需要根據實際 API 調整）
        """
        # 這裡需要根據實際的 Shioaji 合約命名規則調整
        # 以下是範例
        opt_code = 'C' if option_type == 'call' else 'P'
        # 實際可能需要加上到期月份等資訊
        return f"TXO{strike}{opt_code}"

    def _safe_get_contract(self, options, key: str):
        """安全地取得合約，避免 KeyError

        Args:
            options: 選擇權合約物件
            key: 合約鍵

        Returns:
            合約物件或 None
        """
        try:
            # 根據實際 API 結構調整
            if hasattr(options, key):
                return getattr(options, key)
            elif isinstance(options, dict) and key in options:
                return options[key]
            else:
                return None
        except (KeyError, AttributeError):
            return None

    def _subscribe_contracts(self, contracts: List) -> None:
        """訂閱合約列表

        Args:
            contracts: 要訂閱的合約列表
        """
        if not contracts:
            return

        try:
            # 訂閱 tick 資料
            self._api.quote.subscribe(
                self._api.Contracts.Options[contracts[0].code],
                quote_type=sj.constant.QuoteType.Tick,
                version=sj.constant.QuoteVersion.v1
            )

            # 訂閱委買委賣資料
            self._api.quote.subscribe(
                self._api.Contracts.Options[contracts[0].code],
                quote_type=sj.constant.QuoteType.BidAsk,
                version=sj.constant.QuoteVersion.v1
            )

            # 記錄訂閱
            for contract in contracts:
                self._subscribed_contracts.add(contract.code)
                logger.debug(f"已訂閱合約: {contract.code}")

        except Exception as e:
            logger.error(f"訂閱合約時發生錯誤: {e}", exc_info=True)

    def _unsubscribe_contracts(self, contract_codes: Set[str]) -> None:
        """取消訂閱合約

        Args:
            contract_codes: 要取消訂閱的合約代碼集合
        """
        for code in contract_codes:
            try:
                if code in self._contract_cache:
                    contract = self._contract_cache[code]
                    self._api.quote.unsubscribe(contract)
                    logger.debug(f"已取消訂閱合約: {code}")

                # 從訂閱集合中移除
                self._subscribed_contracts.discard(code)

            except Exception as e:
                logger.warning(f"取消訂閱合約 {code} 時發生錯誤: {e}")
                continue
