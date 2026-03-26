"""CIV 歷史持久化模組

功能:
- 儲存 CIV 和標的價格歷史到 MongoDB
- 啟動時載入最近 50 筆歷史
- 用於 Bollinger Band 計算
"""

from datetime import datetime
from typing import List, Tuple
import os
import logging

logger = logging.getLogger(__name__)


class CIVHistory:
    """CIV 歷史持久化"""

    COLLECTION_NAME = "civ_history"

    def __init__(self, mongo_uri: str = None, max_history: int = 50):
        """
        Args:
            mongo_uri: MongoDB 連線字串 (預設從環境變數)
            max_history: 保留的歷史筆數 (預設 50)
        """
        self._mongo_uri = mongo_uri or os.getenv('MONGO_URI')
        self._db_name = os.getenv('MONGO_DB', 'market_data')
        self._client = None
        self._collection = None

        self._civ_history: List[float] = []
        self._price_history: List[float] = []
        self._max_history = max_history

        if self._mongo_uri:
            self._init_mongodb()

    def _init_mongodb(self) -> None:
        """初始化 MongoDB 並載入歷史"""
        try:
            from pymongo import MongoClient
            self._client = MongoClient(self._mongo_uri)
            db = self._client[self._db_name]
            self._collection = db[self.COLLECTION_NAME]

            self._collection.create_index([("timestamp", -1)])
            self._load_history()
            logger.info(f"CIVHistory: 載入 {len(self._civ_history)} 筆歷史")
        except Exception as e:
            logger.error(f"CIVHistory: MongoDB 連線失敗: {e}")

    def _load_history(self) -> None:
        """從 MongoDB 載入最近 N 筆"""
        if self._collection is None:
            return

        try:
            docs = list(
                self._collection.find()
                .sort("timestamp", -1)
                .limit(self._max_history)
            )
            docs.reverse()  # 從舊到新

            for doc in docs:
                self._civ_history.append(doc["civ"])
                self._price_history.append(doc["price"])
        except Exception as e:
            logger.error(f"載入 CIV 歷史失敗: {e}")

    def add(self, civ: float, price: float) -> None:
        """新增一筆歷史

        Args:
            civ: CIV 值
            price: 標的價格
        """
        self._civ_history.append(civ)
        self._price_history.append(price)

        # 保留最近 N 筆
        if len(self._civ_history) > self._max_history:
            self._civ_history = self._civ_history[-self._max_history:]
            self._price_history = self._price_history[-self._max_history:]

        # 存入 MongoDB
        self._save(civ, price)

    def _save(self, civ: float, price: float) -> None:
        """儲存到 MongoDB"""
        if self._collection is None:
            return

        try:
            self._collection.insert_one({
                "timestamp": datetime.now(),
                "civ": civ,
                "price": price
            })

            # 清理舊資料 (保留 100 筆)
            count = self._collection.count_documents({})
            if count > 100:
                # 找出最舊的 N 筆並刪除
                oldest = list(
                    self._collection.find()
                    .sort("timestamp", 1)
                    .limit(count - 100)
                )
                if oldest:
                    ids = [doc["_id"] for doc in oldest]
                    self._collection.delete_many({"_id": {"$in": ids}})
        except Exception as e:
            logger.error(f"CIVHistory 儲存失敗: {e}")

    def get_history(self) -> Tuple[List[float], List[float]]:
        """取得 CIV 和價格歷史

        Returns:
            (civ_history, price_history) 兩個列表的 copy
        """
        return self._civ_history.copy(), self._price_history.copy()

    def history_count(self) -> int:
        """取得歷史資料筆數"""
        return len(self._civ_history)

    def close(self) -> None:
        """關閉 MongoDB 連線"""
        if self._client:
            try:
                self._client.close()
                logger.info("CIVHistory: MongoDB 連線已關閉")
            except Exception as e:
                logger.error(f"關閉 CIVHistory MongoDB 連線失敗: {e}")
