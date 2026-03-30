"""Market Data Service - 專門處理期權報價串流的微服務

此服務負責：
1. 從 Shioaji 訂閱期權報價
2. 動態追蹤價平附近的選擇權合約
3. 透過 Socket.IO 推播即時行情給 Node.js Hub
4. 具備完整的錯誤處理與自動重連機制
"""

import sys
import os
import time
import logging
import threading
from typing import Optional, Dict, Set, List
from datetime import datetime
import shioaji as sj

from src.gateway.gateway_client import GatewayClient
from src.trading.shioaji_client import ShioajiClient
from src.trading.contract_manager import ContractManager
from src.trading.market_data_handler import MarketDataHandler
from src.data.mongodb_client import MongoDBClient
from src.utils.strike_calculator import calculate_call_strikes
from src.utils.trading_hours import is_trading_hours, get_session_name, TW_TZ
from src.indicators.kbar_collector import KBarCollector
from src.indicators.civ_history import CIVHistory
from src.indicators.iv_calculator import (
    calc_civ_from_option_quotes,
    calc_indicator_for_bar,
    build_strike_price_map,
    implied_volatility,
)


# 設定 logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(name)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class MarketDataService:
    """期權報價串流服務

    職責：
    - 協調 Gateway 與 Shioaji 客戶端
    - 管理期權合約訂閱
    - 處理即時行情回呼
    - 執行主迴圈與健康檢查
    """

    def __init__(
        self,
        gateway_client: GatewayClient,
        shioaji_client: ShioajiClient,
        heartbeat_interval: int = 10,
        snapshot_interval: int = 10,  # 從 5 秒改為 10 秒
        contract_update_interval: int = 1
    ):
        """初始化市場資料服務

        Args:
            gateway_client: Gateway 客戶端實例
            shioaji_client: Shioaji 客戶端實例
            heartbeat_interval: 心跳間隔（秒）
            snapshot_interval: 快照輪詢間隔（秒）
            contract_update_interval: 合約更新檢查間隔（秒）
        """
        self._gateway = gateway_client
        self._shioaji = shioaji_client
        self._heartbeat_interval = heartbeat_interval
        self._snapshot_interval = snapshot_interval
        self._contract_update_interval = contract_update_interval

        self._running = False
        self._snapshot_thread: Optional[threading.Thread] = None

        # 合約管理器與行情處理器
        self._contract_manager: Optional[ContractManager] = None
        self._market_handler: Optional[MarketDataHandler] = None

        # 當前大台指數價格
        self._current_index_price: Optional[float] = None
        self._index_futures_contracts: List = []
        self._price_lock = threading.Lock()

        # 排程重啟機制
        self._last_restart_minute: Optional[str] = None
        self._service_start_time: float = time.time()  # 記錄服務啟動時間

        # MongoDB 客戶端與市場參數
        self._mongodb_client: Optional[MongoDBClient] = None
        self._current_futures_month: Optional[str] = None
        self._current_closing_index: Optional[float] = None
        self._subscribed_strikes: List[int] = []

        # 5 分 K 棒收集器與 CIV 歷史 (含 MongoDB 持久化)
        self._kbar_collector: Optional[KBarCollector] = None
        self._civ_history: Optional[CIVHistory] = None

    def start(self) -> None:
        """啟動市場資料服務

        執行流程：
        1. 驗證環境變數
        2. 連接到 Gateway
        3. 連接到 Shioaji
        4. 初始化合約管理器
        5. 設定行情回呼
        6. 啟動快照輪詢執行緒
        7. 進入主迴圈

        Raises:
            RuntimeError: 服務已在運行中
            SystemExit: 環境變數驗證失敗
        """
        if self._running:
            raise RuntimeError("服務已在運行中")

        try:
            # 步驟 1: 驗證環境變數（在連接之前）
            self._validate_environment()

            # 步驟 2: 連接到 Gateway
            logger.info("正在啟動市場資料服務...")
            self._gateway.connect()

            # 步驟 3: 連接到 Shioaji
            self._shioaji.connect()

            # 步驟 4: 初始化合約管理器
            api = self._shioaji.get_api()
            if not api:
                raise RuntimeError("無法取得 Shioaji API 實例")

            self._contract_manager = ContractManager(api)
            self._market_handler = MarketDataHandler(
                gateway_client=self._gateway,
                contract_manager=self._contract_manager
            )

            # 步驟 5: 訂閱台指期貨以取得當前價格
            self._subscribe_index_futures()

            # 步驟 5.5: 從 MongoDB 取得資料並訂閱 TXO 選擇權
            self._setup_option_subscriptions()

            # 步驟 5.6: 初始化 K 棒收集器與 CIV 歷史
            self._kbar_collector = KBarCollector(max_bars=20)
            self._civ_history = CIVHistory(max_history=50)
            logger.info(f"K 棒收集器與 CIV 歷史已初始化 (CIV 歷史: {self._civ_history.history_count()} 筆)")

            # 步驟 6: 設定行情回呼
            self._setup_market_callbacks()

            # 步驟 6: 發送就緒狀態
            self._emit_ready_status()

            # 步驟 7: 設定 running 狀態（必須在啟動 snapshot thread 之前）
            self._running = True
            logger.info("市場資料服務啟動成功")

            # 步驟 8: 啟動快照輪詢執行緒
            self._start_snapshot_thread()

            # 步驟 9: 進入主迴圈
            self._run_main_loop()

        except KeyboardInterrupt:
            logger.info("收到關閉信號")
            self.stop()
        except Exception as e:
            logger.error(f"服務錯誤: {e}", exc_info=True)
            self._emit_error(str(e))
            self.stop()
            raise

    def stop(self) -> None:
        """優雅地停止服務

        注意：即使 _running 為 False 也要清理已建立的連線，
        因為 start() 過程中可能在設定 _running=True 之前就發生例外。
        """
        logger.info("正在停止市場資料服務...")

        # 標記停止（讓執行緒知道要退出）
        was_running = self._running
        self._running = False

        # 停止快照執行緒（只在曾經啟動過時才等待）
        if was_running and self._snapshot_thread and self._snapshot_thread.is_alive():
            self._snapshot_thread.join(timeout=5)

        # 取消訂閱（如果有）
        if self._contract_manager:
            try:
                self._contract_manager.unsubscribe_all()
            except Exception as e:
                logger.error(f"取消訂閱失敗: {e}")

        # 關閉 K 棒收集器的 MongoDB 連線
        if self._kbar_collector:
            try:
                self._kbar_collector.close()
            except Exception as e:
                logger.error(f"關閉 KBarCollector 失敗: {e}")

        # 關閉 CIV 歷史的 MongoDB 連線
        if self._civ_history:
            try:
                self._civ_history.close()
            except Exception as e:
                logger.error(f"關閉 CIVHistory 失敗: {e}")

        # 斷開連接（無論 _running 狀態如何都要清理）
        try:
            self._shioaji.disconnect()
        except Exception as e:
            logger.error(f"Shioaji 斷線失敗: {e}")

        try:
            self._gateway.disconnect()
        except Exception as e:
            logger.error(f"Gateway 斷線失敗: {e}")

        logger.info("市場資料服務已停止")

    def is_running(self) -> bool:
        """檢查服務是否運行中"""
        return self._running

    def _validate_environment(self) -> None:
        """驗證必要的環境變數

        檢查：
        - SJ_KEY: Shioaji API Key
        - SJ_SEC: Shioaji Secret Key
        - GATEWAY_URL: Socket Hub URL

        如果缺少任何必要的環境變數，記錄錯誤並終止程式（讓 Docker 重啟）

        Raises:
            SystemExit: 環境變數驗證失敗
        """
        required_vars = {
            'SJ_KEY': 'Shioaji API Key',
            'SJ_SEC': 'Shioaji Secret Key',
            'GATEWAY_URL': 'Socket Hub URL'
        }

        missing_vars = []
        for var_name, description in required_vars.items():
            value = os.getenv(var_name)
            if not value:
                missing_vars.append(f"{var_name} ({description})")

        if missing_vars:
            error_msg = "缺少必要的環境變數：\n" + "\n".join(f"  - {var}" for var in missing_vars)
            logger.error(error_msg)
            logger.error("請在 .env 檔案或 Docker 環境變數中設定這些值")
            logger.error("程式即將終止，等待 Docker 重啟...")
            sys.exit(1)  # 終止程式，讓 Docker restart: always 接管

        logger.info("環境變數驗證通過")

    def _subscribe_index_futures(self) -> None:
        """訂閱台指期貨以取得當前指數價格

        優先訂閱 TXFR1 (近月) 和 TXFR2 (次月)
        """
        api = self._shioaji.get_api()
        if not api:
            return

        try:
            subscribed_contracts = []

            # 從 TXF 列表中尋找 TXFR1 和 TXFR2
            txf_contracts = api.Contracts.Futures.TXF

            # 轉換為列表並記錄可用合約（用於除錯）
            txf_list = list(txf_contracts)
            available_codes = [c.code for c in txf_list]
            logger.info(f"可用的 TXF 合約: {', '.join(available_codes[:10])}...")  # 只顯示前 10 個

            # TXF 是 StreamMultiContract，可以迭代
            for contract in txf_list:
                if contract.code in ['TXFR1', 'TXFR2']:
                    try:
                        # 訂閱 Quote 類型（包含 tick + bidask 所有資料）
                        api.quote.subscribe(
                            contract,
                            quote_type=sj.constant.QuoteType.Quote,
                            version=sj.constant.QuoteVersion.v1
                        )
                        subscribed_contracts.append(contract.code)
                        self._index_futures_contracts.append(contract)
                        logger.info(f"✓ 已訂閱台指期貨 (Quote): {contract.code} - {contract.name} (到期: {contract.delivery_date})")
                    except Exception as e:
                        logger.warning(f"訂閱 {contract.code} 失敗: {e}")

            # 如果沒找到 TXFR1/TXFR2，用第一個 TXF 合約作為 fallback
            if not subscribed_contracts:
                logger.warning("找不到 TXFR1/TXFR2，使用第一個 TXF 合約")
                first_contract = list(txf_contracts)[0] if txf_contracts else None
                if first_contract:
                    api.quote.subscribe(
                        first_contract,
                        quote_type=sj.constant.QuoteType.Quote,
                        version=sj.constant.QuoteVersion.v1
                    )
                    subscribed_contracts.append(first_contract.code)
                    self._index_futures_contracts.append(first_contract)
                    logger.info(f"✓ 已訂閱台指期貨 (Quote): {first_contract.code} - {first_contract.name}")
                else:
                    logger.error("找不到任何可用的台指期貨合約")

            if subscribed_contracts:
                logger.info(f"總共訂閱 {len(subscribed_contracts)} 個期貨合約: {', '.join(subscribed_contracts)}")

        except Exception as e:
            logger.error(f"訂閱台指期貨失敗: {e}", exc_info=True)

    def _setup_option_subscriptions(self) -> None:
        """從 MongoDB 取得資料並訂閱 TXO 選擇權

        此方法在服務啟動時執行一次，功能：
        1. 連接 MongoDB 並取得市場參數
        2. 計算 16 個履約價 (ATM 上下各 8 檔)
        3. 訂閱 TXO CALL 選擇權
        4. 發送 option_metadata 事件給前端
        """
        logger.info("正在設定 TXO 選擇權訂閱...")

        try:
            # 初始化 MongoDB 客戶端
            self._mongodb_client = MongoDBClient()

            # 取得市場參數
            futures_month = self._mongodb_client.get_futures_month()
            closing_index = self._mongodb_client.get_closing_index()

            if not futures_month:
                logger.error("無法取得期貨月份")
                return

            if not closing_index:
                logger.error("無法取得收盤指數")
                return

            logger.info(f"期貨月份: {futures_month}, 收盤指數: {closing_index}")

            # 計算 16 個履約價
            strikes = calculate_call_strikes(closing_index)
            logger.info(f"計算出 {len(strikes)} 個履約價: {strikes}")

            # 訂閱 TXO CALL 選擇權
            subscribed_count = self._contract_manager.subscribe_txo_by_month(
                futures_month=futures_month,
                strikes=strikes,
                option_type='call'
            )

            # 立即取得初始快照（讓前端馬上有 close 值可用）
            if subscribed_count > 0:
                logger.info("正在取得 TXO 選擇權初始快照...")
                subscribed_contracts = self._contract_manager.get_subscribed_contracts()
                self._fetch_snapshots(subscribed_contracts)
                logger.info(f"已取得 {len(subscribed_contracts)} 個合約的初始快照")

            # 儲存市場參數供心跳使用
            self._current_futures_month = futures_month
            self._current_closing_index = closing_index
            self._subscribed_strikes = strikes

            # 發送 option_metadata 事件給前端
            self._gateway.emit('option_metadata', {
                'futures_month': futures_month,
                'closing_index': closing_index,
                'strikes': strikes,
                'subscribed_count': subscribed_count,
                'timestamp': datetime.now().isoformat()
            })

            logger.info(f"TXO 選擇權訂閱完成: {subscribed_count} 個合約")

        except Exception as e:
            logger.error(f"設定 TXO 選擇權訂閱時發生錯誤: {e}", exc_info=True)
            self._emit_error(f"TXO 訂閱失敗: {str(e)}")

    def _setup_market_callbacks(self) -> None:
        """設定 Shioaji 行情回呼函數"""
        api = self._shioaji.get_api()
        if not api or not self._market_handler:
            return

        # 設定 Quote 回呼（包含 tick + bidask 所有資料）
        @api.on_quote_fop_v1()
        def on_quote(exchange, quote):
            try:
                logger.debug(f"收到 Quote: {quote.code}")
                # 處理 Quote 資料（包含 tick 和 bidask）
                self._market_handler.handle_quote(exchange, quote)
                # 更新當前價格（用於動態合約追蹤）
                self._update_current_price(quote)
            except Exception as e:
                logger.error(f"處理 Quote 資料時發生錯誤: {e}", exc_info=True)

        # 設定期權 tick 回呼（當訂閱期權時使用）
        @api.on_tick_fop_v1()
        def on_tick(exchange, tick):
            try:
                self._market_handler.handle_tick(exchange, tick)
                self._update_current_price(tick)
            except Exception as e:
                logger.error(f"處理 tick 資料時發生錯誤: {e}", exc_info=True)

        # 設定期權委買委賣回呼（當訂閱期權時使用）
        @api.on_bidask_fop_v1()
        def on_bidask(exchange, bidask):
            try:
                self._market_handler.handle_bidask(exchange, bidask)
            except Exception as e:
                logger.error(f"處理 bidask 資料時發生錯誤: {e}", exc_info=True)

        logger.info("行情回呼函數設定完成")

    def _update_current_price(self, tick) -> None:
        """從 tick 資料更新當前大台指數價格

        Args:
            tick: Shioaji tick 資料
        """
        # 這裡需要根據實際的 tick 結構來提取價格
        # 假設 tick 有 close 或 price 屬性
        try:
            code = getattr(tick, 'code', '')
            # 僅追蹤台指期貨，避免被 TXO 報價覆蓋造成時間基準錯位
            if not str(code).startswith('TXF'):
                return

            price = getattr(tick, 'close', None) or getattr(tick, 'price', None)
            if price and price > 0:
                with self._price_lock:
                    self._current_index_price = float(price)
        except Exception as e:
            logger.debug(f"更新價格時發生錯誤: {e}")

    def _get_synced_underlying_price(self) -> Optional[float]:
        """取得與 5 分 K 同步的即時標的 close。

        優先使用同一輪 snapshot 時間點抓到的台指期貨 close，
        若抓取失敗再退回最新 quote/tick 的期貨價格。
        """
        api = self._shioaji.get_api()
        if api and self._index_futures_contracts:
            for contract in self._index_futures_contracts:
                try:
                    snapshot = api.snapshots([contract])
                    if snapshot and hasattr(snapshot[0], 'close') and snapshot[0].close:
                        price = float(snapshot[0].close)
                        with self._price_lock:
                            self._current_index_price = price
                        return price
                except Exception as e:
                    logger.debug(f"抓取台指期貨 {contract.code} 快照失敗: {e}")

        with self._price_lock:
            return self._current_index_price

    def _start_snapshot_thread(self) -> None:
        """啟動快照輪詢執行緒"""
        self._snapshot_thread = threading.Thread(
            target=self._snapshot_loop,
            daemon=True,
            name="SnapshotThread"
        )
        self._snapshot_thread.start()
        logger.info(f"快照輪詢執行緒已啟動（間隔 {self._snapshot_interval} 秒）")

    def _snapshot_loop(self) -> None:
        """快照輪詢迴圈（在獨立執行緒中運行）

        定期抓取合約快照資料，即使發生錯誤也會繼續執行
        包含:
        - 交易時段檢查 (非交易時段跳過)
        - 更新 K 棒收集器
        - 檢查 5 分鐘邊界並計算 IV 指標
        """
        while self._running:
            try:
                time.sleep(self._snapshot_interval)

                # 交易時段檢查
                if not is_trading_hours():
                    continue

                if not self._contract_manager:
                    continue

                # 抓取訂閱合約的快照
                contracts = self._contract_manager.get_subscribed_contracts()
                if not contracts:
                    continue

                # 取得快照並更新 K 棒收集器
                snapshots_data = self._fetch_snapshots_with_data(contracts)

                # 更新 K 棒收集器
                if self._kbar_collector and snapshots_data:
                    for code, close in snapshots_data.items():
                        self._kbar_collector.update_close(code, close)

                    # 檢查是否有新的 5 分 K 棒
                    new_bar = self._kbar_collector.check_and_record_bar()
                    if new_bar:
                        self._on_new_kbar(new_bar)

            except Exception as e:
                # 確保即使快照失敗，執行緒也能繼續運行
                logger.error(f"快照輪詢發生錯誤: {e}", exc_info=True)
                continue

    def _fetch_snapshots(self, contracts: List) -> None:
        """抓取合約快照

        Args:
            contracts: 合約列表
        """
        api = self._shioaji.get_api()
        if not api:
            return

        try:
            for contract in contracts:
                try:
                    snapshot = api.snapshots([contract])
                    if snapshot and self._market_handler:
                        self._market_handler.handle_snapshot(snapshot)
                except Exception as e:
                    logger.warning(f"抓取合約 {contract.code} 快照失敗: {e}")
                    # 繼續處理下一個合約
                    continue

        except Exception as e:
            logger.error(f"批次抓取快照失敗: {e}")

    def _fetch_snapshots_with_data(self, contracts: List) -> Dict[str, float]:
        """抓取合約快照並回傳 close 資料

        Args:
            contracts: 合約列表

        Returns:
            {contract_code: close} 字典
        """
        api = self._shioaji.get_api()
        if not api:
            return {}

        result = {}
        try:
            for contract in contracts:
                try:
                    snapshot = api.snapshots([contract])
                    if snapshot and self._market_handler:
                        self._market_handler.handle_snapshot(snapshot)
                        # 提取 close 價格
                        if hasattr(snapshot[0], 'close') and snapshot[0].close:
                            result[contract.code] = float(snapshot[0].close)
                except Exception as e:
                    logger.warning(f"抓取合約 {contract.code} 快照失敗: {e}")
                    continue
        except Exception as e:
            logger.error(f"批次抓取快照失敗: {e}")

        return result

    def _on_new_kbar(self, bar_closes: Dict[str, float]) -> None:
        """處理新的 5 分 K 棒

        Args:
            bar_closes: {contract_code: close} 字典
        """
        # 取得 K 棒對齊時間
        bar_time = self._kbar_collector.get_last_bar_time() if self._kbar_collector else datetime.now(TW_TZ)

        # 1. 發送 kbar_close 事件到前端 (含 bar counts 和對齊時間)
        bar_counts = self._kbar_collector.get_bar_counts() if self._kbar_collector else {}
        self._gateway.emit('kbar_close', {
            'bar_time': bar_time.isoformat() if bar_time else None,
            'timestamp': datetime.now(TW_TZ).isoformat(),
            'closes': bar_closes,
            'bar_counts': bar_counts
        })
        logger.info(f"發送 kbar_close 事件: {len(bar_closes)} 個合約, bar_time={bar_time.strftime('%H:%M:%S') if bar_time else 'N/A'}")

        # 2. 計算 IV 指標
        if not self._civ_history or not self._subscribed_strikes:
            return

        dte = self._calculate_dte()
        if dte <= 0:
            logger.warning("DTE <= 0，跳過 IV 計算")
            return

        # 取得與本次 5 分 K 同步的標的價格
        underlying_price = self._get_synced_underlying_price()
        if not underlying_price:
            logger.warning("無同步標的價格，跳過 IV 計算")
            return

        # 若可計算，先統計有效 Call IV 筆數
        valid_call_iv_count = self._calculate_valid_call_iv_count(
            bar_closes=bar_closes,
            strikes=self._subscribed_strikes,
            underlying_price=underlying_price,
            dte=dte,
        )

        # 計算 CIV
        civ = calc_civ_from_option_quotes(
            bar_closes,
            self._subscribed_strikes,
            underlying_price,
            dte
        )

        if civ is None:
            logger.warning("無法計算 CIV (可能選擇權資料不足)")
            return

        logger.info(f"計算 CIV: {civ * 100:.2f}%")

        # 從 CIVHistory 取得歷史
        civ_hist, price_hist = self._civ_history.get_history()

        # 計算完整指標
        result = calc_indicator_for_bar(
            civ=civ,
            civ_history=civ_hist,
            price=underlying_price,
            price_history=price_hist,
            period=20
        )

        # 儲存到 MongoDB (傳入 K 棒對齊時間)
        self._civ_history.add(civ, underlying_price, bar_time)

        # 發送 IV 指標事件
        if result:
            current_dt = result.timestamp
            self._gateway.emit('iv_indicator', {
                'civ': result.civ,
                'civ_ma5': result.civ_ma5,
                'civ_pb': result.civ_pb,
                'price_pb': result.price_pb,
                'pb_minus_civ_pb': result.pb_minus_civ_pb,
                'dte': dte,
                'valid_call_iv_count': valid_call_iv_count,
                'underlying_price': underlying_price,
                'bar_time': bar_time.isoformat() if bar_time else None,
                'current_dt': current_dt,
                'signal': result.signal,
                'timestamp': result.timestamp
            })
            logger.info(f"發送 iv_indicator: CIV={result.civ*100:.2f}%, Price={underlying_price:.2f}, bar_time={bar_time.strftime('%H:%M:%S') if bar_time else 'N/A'}")
        else:
            logger.info(f"歷史資料不足 ({len(civ_hist)+1}/20)，尚無法計算 Bollinger %b")

    def _calculate_valid_call_iv_count(
        self,
        bar_closes: Dict[str, float],
        strikes: List[int],
        underlying_price: float,
        dte: float,
    ) -> Optional[int]:
        """計算可用於 CIV 的有效 Call IV 筆數。"""
        if not bar_closes or not strikes or underlying_price <= 0 or dte <= 0:
            return None

        try:
            strike_price_map = build_strike_price_map(bar_closes)
            valid_count = 0

            for strike in strikes:
                close = strike_price_map.get(strike)
                if not close or close <= 0:
                    continue

                iv = implied_volatility(close, underlying_price, strike, dte)
                if 0 < iv < 900:
                    valid_count += 1

            return valid_count
        except Exception as e:
            logger.warning(f"計算 valid_call_iv_count 失敗: {e}")
            return None

    def _calculate_dte(self) -> float:
        """計算距到期天數（使用台灣時區）

        Returns:
            距到期天數 (至少 1 天)
        """
        if not self._mongodb_client:
            return 0

        try:
            expiration_date = self._mongodb_client.get_expiration_date()
            if not expiration_date:
                return 0

            # 使用台灣時區日期，避免 UTC 時差導致 off-by-one
            today = datetime.now(TW_TZ).date()

            # expiration_date 格式: YYYYMMDD (int)
            exp_str = str(expiration_date)
            exp_date = datetime.strptime(exp_str, '%Y%m%d').date()

            delta = (exp_date - today).days
            return max(delta, 1)  # 至少 1 天，避免除零
        except Exception as e:
            logger.error(f"計算 DTE 失敗: {e}")
            return 0

    def _run_main_loop(self) -> None:
        """執行主事件迴圈

        功能：
        - 發送定期心跳
        - 檢查並更新合約訂閱（動態追蹤價平附近選擇權）
        - 處理鍵盤中斷
        """
        logger.info("主迴圈已啟動。按 Ctrl+C 退出。")

        last_contract_update = time.time()

        while self._running:
            try:
                current_time = time.time()

                # 發送心跳
                time.sleep(1)  # 短間隔檢查
                if current_time % self._heartbeat_interval < 1:
                    self._send_heartbeat()

                # 檢查排程重啟
                self._check_scheduled_restart()

                # 動態更新合約訂閱（每秒檢查）
                if current_time - last_contract_update >= self._contract_update_interval:
                    self._ensure_subscriptions()
                    last_contract_update = current_time

            except KeyboardInterrupt:
                logger.info("收到鍵盤中斷信號")
                break
            except Exception as e:
                logger.error(f"主迴圈錯誤: {e}", exc_info=True)
                self._emit_error(str(e))

    def _ensure_subscriptions(self) -> None:
        """確保訂閱正確的合約（動態追蹤價平附近選擇權）

        如果當前價格無效，跳過更新
        """
        if not self._contract_manager:
            return

        with self._price_lock:
            current_price = self._current_index_price

        # 如果還沒有有效價格，暫不更新訂閱
        if not current_price or current_price <= 0:
            logger.debug("當前價格無效，跳過合約訂閱更新")
            return

        try:
            # 更新訂閱（價平 ± 8 檔 call）
            self._contract_manager.update_subscriptions(
                current_price=current_price,
                range_strikes=8,
                option_type='call'  # 只訂閱買權
            )
        except Exception as e:
            logger.error(f"更新合約訂閱時發生錯誤: {e}", exc_info=True)

    def _check_scheduled_restart(self) -> None:
        """檢查是否到達排程重啟時間點

        在特定時間點觸發系統重啟，以應對：
        1. 06:30 - 清晨券商系統洗帳後重啟
        2. 08:40 - 日盤開盤前重啟
        3. 14:55 - 夜盤開盤前重啟

        使用 Crash-Only 設計：直接終止進程，由 Docker restart: always 重新啟動

        防止無限重啟：如果服務剛啟動不到 2 分鐘，跳過重啟檢查
        """
        # 防止無限重啟：剛啟動的服務不應該立即重啟
        uptime = time.time() - self._service_start_time
        if uptime < 120:  # 啟動後 2 分鐘內不檢查重啟
            return

        now = datetime.now()
        current_minute = f"{now.hour:02d}:{now.minute:02d}"

        # 定義需要觸發重啟的時間點
        restart_times = [(6, 30), (8, 40), (14, 55)]

        # 檢查是否符合重啟時間且未在本分鐘內觸發過
        if (now.hour, now.minute) in restart_times:
            if self._last_restart_minute != current_minute:
                logger.warning(
                    f"🔄 [排程] 觸發系統換盤重啟 (時間: {current_minute})，準備優雅關閉..."
                )
                self._last_restart_minute = current_minute

                # 優雅關閉（登出 Shioaji、斷開 Gateway）
                self.stop()

                # 終止進程，由 Docker 重新啟動
                sys.exit(0)

    def _emit_ready_status(self) -> None:
        """發送就緒狀態給 Gateway"""
        self._gateway.emit('shioaji_ready', {
            'status': 'ready',
            'simulation': self._shioaji._config.simulation,
            'version': self._shioaji.get_version(),
            'service_type': 'market_data'
        })
        logger.info("已發送就緒狀態")

    def _send_heartbeat(self) -> None:
        """發送心跳給 Gateway"""
        # 只在連接時發送
        if not self._gateway.is_connected():
            return

        try:
            with self._price_lock:
                current_price = self._current_index_price

            # 同時發送 option_metadata (讓後連線的前端也能收到)
            option_metadata = {
                'futures_month': getattr(self, '_current_futures_month', None),
                'closing_index': getattr(self, '_current_closing_index', None),
                'strikes': getattr(self, '_subscribed_strikes', []),
                'subscribed_count': len(self._contract_manager.get_subscribed_contracts()) if self._contract_manager else 0,
            }

            self._gateway.emit('heartbeat', {
                'status': 'running',
                'shioaji_connected': self._shioaji.is_connected(),
                'gateway_connected': self._gateway.is_connected(),
                'current_price': current_price,
                'subscribed_contracts': len(self._contract_manager.get_subscribed_contracts()) if self._contract_manager else 0,
                'futures_month': self._current_futures_month,
                'closing_index': self._current_closing_index
            })

            # 每次心跳都發送 option_metadata，確保後連線的前端能收到
            if option_metadata['futures_month']:
                self._gateway.emit('option_metadata', option_metadata)
        except Exception as e:
            logger.warning(f"發送心跳失敗: {e}")

    def _emit_error(self, error: str) -> None:
        """發送錯誤訊息給 Gateway

        Args:
            error: 錯誤訊息
        """
        if self._gateway.is_connected():
            try:
                self._gateway.emit('python_error', {
                    'error': error,
                    'service': 'market_data'
                })
            except Exception as e:
                logger.error(f"發送錯誤訊息失敗: {e}")
