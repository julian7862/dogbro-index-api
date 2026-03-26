"""5 分鐘 K 棒收集器 (含 MongoDB 持久化)

功能:
- 追蹤每個合約的 snapshot close 值
- 每 5 分鐘 (整點: 00, 05, 10, 15...) 記錄當時的 close 為該 K 棒收盤價
- MongoDB 持久化: 啟動時載入歷史資料，新 K 棒存入 MongoDB
- 保留最近 N 根 K 棒資料 (用於 Bollinger Band 計算)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from collections import deque
import os
import logging

logger = logging.getLogger(__name__)


@dataclass
class KBarData:
    """5 分鐘 K 棒資料"""
    timestamp: datetime  # K 棒時間 (整 5 分鐘)
    close: float         # 收盤價


class KBarCollector:
    """5 分鐘 K 棒收集器 (含 MongoDB 持久化)"""

    COLLECTION_NAME = "kbar_5min"

    def __init__(self, max_bars: int = 20, mongo_uri: str = None):
        """
        Args:
            max_bars: 保留的 K 棒數量 (Bollinger Band 預設 20 根)
            mongo_uri: MongoDB 連線字串 (預設從環境變數)
        """
        self._max_bars = max_bars
        self._kbars: Dict[str, deque] = {}
        self._latest_close: Dict[str, float] = {}
        self._last_bar_time: Optional[datetime] = None

        # MongoDB 連線
        self._mongo_uri = mongo_uri or os.getenv('MONGO_URI')
        self._db_name = os.getenv('MONGO_DB', 'market_data')
        self._client = None
        self._collection = None

        if self._mongo_uri is not None:
            self._init_mongodb()

    def _init_mongodb(self) -> None:
        """初始化 MongoDB 連線並載入歷史資料"""
        try:
            from pymongo import MongoClient
            self._client = MongoClient(self._mongo_uri)
            db = self._client[self._db_name]
            self._collection = db[self.COLLECTION_NAME]

            # 建立索引
            self._collection.create_index([
                ("contract_code", 1),
                ("timestamp", -1)
            ])

            # 載入最近 N 根 K 棒
            self._load_history()
            logger.info("KBarCollector: MongoDB 初始化完成")
        except Exception as e:
            logger.error(f"KBarCollector: MongoDB 連線失敗: {e}")

    def _load_history(self) -> None:
        """從 MongoDB 載入歷史 K 棒"""
        if self._collection is None:
            return

        try:
            # 取得所有合約的最近 N 根 K 棒
            pipeline = [
                {"$sort": {"timestamp": -1}},
                {"$group": {
                    "_id": "$contract_code",
                    "bars": {"$push": {"timestamp": "$timestamp", "close": "$close"}}
                }},
                {"$project": {
                    "contract_code": "$_id",
                    "bars": {"$slice": ["$bars", self._max_bars]}
                }}
            ]

            for doc in self._collection.aggregate(pipeline):
                code = doc["contract_code"]
                self._kbars[code] = deque(maxlen=self._max_bars)

                # 反轉順序 (從舊到新)
                for bar in reversed(doc["bars"]):
                    self._kbars[code].append(KBarData(
                        timestamp=bar["timestamp"],
                        close=bar["close"]
                    ))

                logger.info(f"載入 {code} 歷史 K 棒: {len(self._kbars[code])} 根")
        except Exception as e:
            logger.error(f"載入歷史 K 棒失敗: {e}")

    def _save_bar(self, contract_code: str, bar: KBarData) -> None:
        """儲存 K 棒到 MongoDB"""
        if self._collection is None:
            return

        try:
            self._collection.update_one(
                {"contract_code": contract_code, "timestamp": bar.timestamp},
                {"$set": {"close": bar.close}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"儲存 K 棒失敗: {e}")

    def update_close(self, contract_code: str, close: float) -> None:
        """更新合約的最新收盤價 (每次 snapshot 呼叫)

        Args:
            contract_code: 合約代碼
            close: 收盤價
        """
        if close and close > 0:
            self._latest_close[contract_code] = close

    def check_and_record_bar(self) -> Optional[Dict[str, float]]:
        """檢查是否到達 5 分鐘邊界，若是則記錄 K 棒並存入 MongoDB

        Returns:
            若有新 K 棒則回傳 {contract_code: close}，否則 None
        """
        now = datetime.now()
        bar_time = self._get_bar_time(now)

        if self._last_bar_time == bar_time:
            return None

        self._last_bar_time = bar_time
        result = {}

        for code, close in self._latest_close.items():
            if code not in self._kbars:
                self._kbars[code] = deque(maxlen=self._max_bars)

            bar = KBarData(timestamp=bar_time, close=close)
            self._kbars[code].append(bar)
            self._save_bar(code, bar)  # 持久化
            result[code] = close

        if result:
            logger.info(f"記錄新 K 棒 ({bar_time.strftime('%H:%M')}): {len(result)} 個合約")

        return result if result else None

    def _get_bar_time(self, dt: datetime) -> datetime:
        """取得所屬的 5 分 K 時間"""
        minute = (dt.minute // 5) * 5
        return dt.replace(minute=minute, second=0, microsecond=0)

    def get_closes(self, contract_code: str) -> List[float]:
        """取得合約的歷史收盤價列表

        Args:
            contract_code: 合約代碼

        Returns:
            收盤價列表 (從舊到新)
        """
        if contract_code not in self._kbars:
            return []
        return [bar.close for bar in self._kbars[contract_code]]

    def get_latest_bar_close(self, contract_code: str) -> Optional[float]:
        """取得最新一根 K 棒的收盤價

        Args:
            contract_code: 合約代碼

        Returns:
            最新 K 棒收盤價，或 None
        """
        if contract_code not in self._kbars or not self._kbars[contract_code]:
            return None
        return self._kbars[contract_code][-1].close

    def get_all_latest_closes(self) -> Dict[str, float]:
        """取得所有合約的最新 K 棒收盤價

        Returns:
            {contract_code: close}
        """
        result = {}
        for code, bars in self._kbars.items():
            if bars:
                result[code] = bars[-1].close
        return result

    def get_bar_counts(self) -> Dict[str, int]:
        """取得所有合約的 K 棒數量

        Returns:
            {contract_code: bar_count}
        """
        return {code: len(bars) for code, bars in self._kbars.items()}

    def close(self) -> None:
        """關閉 MongoDB 連線"""
        if self._client:
            try:
                self._client.close()
                logger.info("KBarCollector: MongoDB 連線已關閉")
            except Exception as e:
                logger.error(f"關閉 MongoDB 連線失敗: {e}")
